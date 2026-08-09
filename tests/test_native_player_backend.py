from __future__ import annotations

import time
import ctypes
import threading

import numpy as np
import pytest

from casu.native_v2 import (ChunkType, NativeChunk, decode_audio_block,
                            encode_attachment, encode_audio_block,
                            encode_bitmap_subtitle,
                            encode_chapter_table, encode_key_state,
                            encode_subtitle_packet, SubtitlePacket,
                            write_native_v2)


STYLED_ASS = b"""[Script Info]
ScriptType: v4.00+
PlayResX: 320
PlayResY: 180
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CASU,DejaVu Sans,28,&H0000FFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:01.00,CASU,,0,0,0,,Styled CASU
"""


def libass_available():
    try:
        ctypes.CDLL("libass.so.9")
        return True
    except OSError:
        return False
from casu.strict import canonical_frame
from casu.media import MediaBackend, TrackKind
from mpcasu_backend import BackendError, PlaybackState
from mpcasu_native_backend import (NativeCasuBackend, canonical_to_rgb,
                                   resample_audio_block)


class InstrumentedVideoSink:
    def __init__(self):
        self.frames = []
        self.invalidations = 0
        self.subtitles = []
        self.covers = []
        self.rich_subtitles = []
        self.subtitle_clears = 0

    def present(self, frame, pts_seconds):
        self.frames.append((pts_seconds, frame.digest()))

    def invalidate(self):
        self.invalidations += 1

    def present_subtitle(self, text, pts_seconds):
        self.subtitles.append((pts_seconds, text))

    def present_cover(self, data, media_type):
        self.covers.append((data, media_type))

    def present_subtitle_rgba(self, rgba, pts_seconds):
        self.rich_subtitles.append((pts_seconds, rgba.copy()))

    def clear_subtitle(self):
        self.subtitle_clears += 1

    def close(self):
        pass


class InstrumentedAudioSink:
    def __init__(self):
        self.blocks = []
        self.flushes = 0
        self.volume = 100
        self.muted = False

    def write(self, block):
        self.blocks.append(block)

    def flush(self):
        self.flushes += 1

    def close(self):
        pass

    def set_volume(self, value):
        self.volume = value

    def set_mute(self, muted):
        self.muted = muted

    def latency_seconds(self):
        return None


def _native_fixture(path):
    first = canonical_frame(np.zeros((2, 6), dtype=np.uint8),
                            pixel_format="rgb24", source_shape=(2, 2))
    second = canonical_frame(np.full((2, 6), 255, dtype=np.uint8),
                             pixel_format="rgb24", source_shape=(2, 2))
    manifest = {
        "format": "CASUNAT2", "version": 2,
        "streams": [
            {"stream_id": 1, "type": "video", "codec_origin": "test",
             "time_base": [1, 1000], "frame_timeline": [
                 {"pts": 0, "duration_pts": 10}, {"pts": 10, "duration_pts": 10}]},
            {"stream_id": 2, "type": "audio", "codec_origin": "test",
             "time_base": [1, 1000], "sample_rate": 1000, "channels": 1,
             "frame_timeline": [{"pts": 0, "duration_pts": 10}]},
            {"stream_id": 3, "type": "subtitle", "codec_origin": "srt",
             "time_base": [1, 1000], "language": "de", "frame_timeline": []},
        ],
        "chapter_time_base": [1, 1_000_000_000],
    }
    audio = encode_audio_block(pcm=b"\0\0" * 10, pts=0, time_base_num=1,
                               time_base_den=1000, sample_rate=1000, channels=1,
                               sample_count=10)
    write_native_v2(path, manifest, [
        NativeChunk(ChunkType.VIDEO_KEY_STATE, 1, 0, encode_key_state(first)),
        NativeChunk(ChunkType.AUDIO_BLOCK, 2, 0, audio),
        NativeChunk(ChunkType.VIDEO_KEY_STATE, 1, 10, encode_key_state(second)),
        NativeChunk(ChunkType.SUBTITLE_PACKET, 3, 0, encode_subtitle_packet(
            SubtitlePacket(0, 10, "Hallo", "de", "text"))),
        NativeChunk(ChunkType.CHAPTER_TABLE, 0, 0, encode_chapter_table([
            {"start_pts": 0, "end_pts": 20_000_000, "title": "Intro"}])),
    ])
    return first, second


def test_native_playback_creates_no_legacy_tempfile(tmp_path, monkeypatch):
    source = tmp_path / "native.casu"
    first, second = _native_fixture(source)
    video, audio = InstrumentedVideoSink(), InstrumentedAudioSink()
    monkeypatch.setattr("tempfile.mkstemp", lambda *args, **kwargs:
                        (_ for _ in ()).throw(AssertionError("legacy tempfile created")))
    backend = NativeCasuBackend(video, audio)
    backend.open_casu(source)
    assert backend.capabilities()["temporary_legacy_file"] == "none"
    backend.play()
    deadline = time.monotonic() + 1
    while backend.state() not in {PlaybackState.ENDED, PlaybackState.ERROR} and time.monotonic() < deadline:
        time.sleep(0.005)
    assert backend.state() == PlaybackState.ENDED
    assert video.frames == [(0.0, first.digest()), (0.01, second.digest())]
    assert len(audio.blocks) == 1 and audio.blocks[0].pcm == b"\0\0" * 10
    backend.close()


def test_native_av_sync_with_instrumented_sinks(tmp_path):
    source = tmp_path / "native.casu"
    first, second = _native_fixture(source)
    video, audio = InstrumentedVideoSink(), InstrumentedAudioSink()
    backend = NativeCasuBackend(video, audio)
    backend.open_casu(source); backend.play()
    deadline = time.monotonic() + 1
    while backend.state() not in {PlaybackState.ENDED, PlaybackState.ERROR} and time.monotonic() < deadline:
        time.sleep(0.005)
    assert backend.state() == PlaybackState.ENDED
    assert video.frames == [(0.0, first.digest()), (0.01, second.digest())]
    assert [(block.pts, block.time_base_num, block.time_base_den)
            for block in audio.blocks] == [(0, 1, 1000)]
    assert video.subtitles == [(0.0, "Hallo"), (0.01, None)]
    backend.close()


def test_native_seek_invalidates_tile_cache(tmp_path):
    source = tmp_path / "native.casu"; _native_fixture(source)
    video, audio = InstrumentedVideoSink(), InstrumentedAudioSink()
    backend = NativeCasuBackend(video, audio)
    backend.open_casu(source)
    backend.seek(0.005)
    assert backend.position() == 0.005
    assert video.invalidations == 1
    assert audio.flushes == 1
    backend.next_frame()
    assert video.frames and video.frames[-1][0] == 0.01
    backend.close()


def test_native_audio_only_player_presents_embedded_cover(tmp_path):
    source = tmp_path / "album.casu"
    audio = encode_audio_block(pcm=b"\0\0" * 10, pts=0, time_base_num=1,
                               time_base_den=1000, sample_rate=1000, channels=1,
                               sample_count=10)
    write_native_v2(source, {
        "format": "CASUNAT2", "version": 2,
        "streams": [
            {"stream_id": 1, "type": "audio", "time_base": [1, 1000],
             "sample_rate": 1000, "channels": 1},
            {"stream_id": 2, "type": "attachment", "role": "cover-art",
             "time_base": [1, 1]},
        ],
    }, [
        NativeChunk(ChunkType.AUDIO_BLOCK, 1, 0, audio),
        NativeChunk(ChunkType.ATTACHMENT, 2, 0,
                    encode_attachment("cover.png", "image/png", b"png-bytes",
                                      role="cover-art")),
    ])
    video = InstrumentedVideoSink()
    backend = NativeCasuBackend(video, InstrumentedAudioSink())
    backend.open_casu(source)
    assert backend.video_track_count() == 0
    assert video.covers == [(b"png-bytes", "image/png")]
    backend.seek(0.005)
    assert video.covers[-1] == (b"png-bytes", "image/png")
    backend.close()


@pytest.mark.skipif(not libass_available(), reason="libass runtime unavailable")
def test_native_player_renders_preserved_ass_source(tmp_path):
    source = tmp_path / "styled.casu"
    write_native_v2(source, {
        "format": "CASUNAT2", "version": 2,
        "streams": [{"stream_id": 1, "type": "subtitle", "time_base": [1, 1000],
                     "language": "en", "codec_origin": "ass"}],
    }, [
        NativeChunk(ChunkType.ATTACHMENT, 1, 0,
                    encode_attachment("subtitle-1.ass", "text/x-ssa", STYLED_ASS,
                                      role="subtitle-source")),
        NativeChunk(ChunkType.SUBTITLE_PACKET, 1, 0, encode_subtitle_packet(
            SubtitlePacket(0, 1000, "Styled CASU", "en", "webvtt-text"))),
    ])
    video = InstrumentedVideoSink()
    backend = NativeCasuBackend(video, InstrumentedAudioSink())
    backend.open_casu(source); backend.play()
    deadline = time.monotonic() + 2
    while backend.state() not in {PlaybackState.ENDED, PlaybackState.ERROR} and time.monotonic() < deadline:
        time.sleep(0.005)
    assert backend.state() == PlaybackState.ENDED
    assert video.rich_subtitles
    assert np.count_nonzero(video.rich_subtitles[0][1][..., 3]) > 0
    assert not [text for _pts, text in video.subtitles if text]
    backend.set_subtitle_track(-1)
    assert video.subtitle_clears >= 1
    backend.close()


def test_native_player_presents_bitmap_subtitle_and_seek_overlap(tmp_path):
    source = tmp_path / "bitmap.casu"
    rgba = bytes([0, 255, 0, 255] * 6)
    write_native_v2(source, {
        "format": "CASUNAT2", "version": 2,
        "streams": [{"stream_id": 1, "type": "subtitle", "time_base": [1, 1000],
                     "language": "en", "codec_origin": "hdmv_pgs_subtitle",
                     "canonical_format": "rgba-bitmap-region"}],
    }, [NativeChunk(ChunkType.SUBTITLE_BITMAP, 1, 100,
                    encode_bitmap_subtitle(
                        start_pts=100, end_pts=900, canvas_width=10,
                        canvas_height=8, x=2, y=3, width=3, height=2,
                        rgba=rgba))])
    video = InstrumentedVideoSink()
    backend = NativeCasuBackend(video, InstrumentedAudioSink())
    backend.open_casu(source)
    backend.seek(0.5); backend.play()
    deadline = time.monotonic() + 1
    while not video.rich_subtitles and time.monotonic() < deadline:
        time.sleep(0.005)
    assert video.rich_subtitles
    overlay = video.rich_subtitles[0][1]
    assert overlay.shape == (8, 10, 4)
    assert overlay[3:5, 2:5].tobytes() == rgba
    backend.close()


def test_native_seek_trims_overlapping_pcm_block(tmp_path):
    source = tmp_path / "native.casu"; _native_fixture(source)
    video, audio = InstrumentedVideoSink(), InstrumentedAudioSink()
    backend = NativeCasuBackend(video, audio)
    backend.open_casu(source)
    backend.seek(0.005)
    backend.play()
    deadline = time.monotonic() + 1
    while backend.state() not in {PlaybackState.ENDED, PlaybackState.ERROR} and time.monotonic() < deadline:
        time.sleep(0.005)
    assert backend.state() == PlaybackState.ENDED
    assert len(audio.blocks) == 1
    assert audio.blocks[0].sample_count == 5
    assert len(audio.blocks[0].pcm) == 10
    backend.close()


def test_native_seek_refuses_restart_while_old_audio_write_is_blocked(tmp_path):
    source = tmp_path / "native.casu"; _native_fixture(source)
    entered, release = threading.Event(), threading.Event()
    operations = []

    class BlockingAudioSink(InstrumentedAudioSink):
        def write(self, block):
            operations.append("write-enter")
            entered.set()
            release.wait(1.0)
            super().write(block)
            operations.append("write-exit")

        def flush(self):
            operations.append("flush")
            super().flush()

    video, audio = InstrumentedVideoSink(), BlockingAudioSink()
    backend = NativeCasuBackend(video, audio)
    backend._worker_stop_timeout = 0.05
    backend.open_casu(source); backend.play()
    assert entered.wait(0.5)
    with pytest.raises(BackendError, match="restart refused"):
        backend.seek(0.005)
    assert backend.state() == PlaybackState.ERROR
    assert video.invalidations == 0 and audio.flushes == 0

    release.set()
    deadline = time.monotonic() + 1
    while backend._thread is not None and backend._thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.005)
    backend.seek(0.005)
    assert video.invalidations == 1 and audio.flushes == 1
    assert operations[:3] == ["write-enter", "write-exit", "flush"]
    backend.close()


def test_native_rapid_seek_delivers_only_final_generation(tmp_path):
    source = tmp_path / "native.casu"; _native_fixture(source)
    video, audio = InstrumentedVideoSink(), InstrumentedAudioSink()
    backend = NativeCasuBackend(video, audio)
    backend.open_casu(source); backend.play()
    for target in (0.015, 0.0, 0.015, 0.005):
        backend.seek(target)
    frame_start, audio_start = len(video.frames), len(audio.blocks)
    deadline = time.monotonic() + 1
    while backend.state() not in {PlaybackState.ENDED, PlaybackState.ERROR} and time.monotonic() < deadline:
        time.sleep(0.005)
    assert backend.state() == PlaybackState.ENDED
    assert [pts for pts, _digest in video.frames[frame_start:]] == [0.01]
    assert [(block.pts, block.sample_count) for block in audio.blocks[audio_start:]] == [(5, 5)]
    assert video.invalidations == 4 and audio.flushes == 4
    backend.close()


def test_native_pause_stop_and_close_flush_audio(tmp_path):
    source = tmp_path / "native.casu"; _native_fixture(source)
    video, audio = InstrumentedVideoSink(), InstrumentedAudioSink()
    backend = NativeCasuBackend(video, audio)
    backend.open_casu(source)
    backend.play(); backend.pause()
    after_pause = audio.flushes
    backend.stop()
    after_stop = audio.flushes
    backend.close()
    assert after_pause >= 1
    assert after_stop > after_pause
    assert audio.flushes > after_stop


def test_native_backend_track_controls_are_behavioral(tmp_path):
    source = tmp_path / "native.casu"; _native_fixture(source)
    backend = NativeCasuBackend(InstrumentedVideoSink(), InstrumentedAudioSink())
    backend.open_casu(source)
    assert isinstance(backend, MediaBackend)
    assert backend.video_track_descriptions() == [(1, "test")]
    assert backend.audio_track_descriptions() == [(2, "test")]
    backend.set_video_track(1)
    backend.set_audio_track(2)
    assert backend.video_track() == 1 and backend.audio_track() == 2
    assert backend.track_descriptors(TrackKind.VIDEO)[0].codec == "test"
    assert backend.subtitle_track_descriptions() == [(3, "de")]
    backend.set_subtitle_track(3)
    assert backend.chapter_count() == 1 and backend.chapter() == 0
    assert backend.chapter_descriptors()[0].title == "Intro"
    assert backend.chapter_descriptors()[0].end_seconds == 0.02
    backend.set_chapter(0)
    assert backend.audio_devices()[0].identifier == "default"
    backend.set_audio_device("default")
    assert backend.set_volume(125) == 125
    backend.set_mute(True)
    backend.close()


def test_native_display_conversion_preserves_source_dimensions():
    plane = np.array([[255, 0, 0, 0, 255, 0]], dtype=np.uint8)
    frame = canonical_frame(plane, pixel_format="rgb24", source_shape=(1, 2))
    rgb = canonical_to_rgb(frame)
    assert rgb.shape == (1, 2, 3)
    assert rgb.tolist() == [[[255, 0, 0], [0, 255, 0]]]


def test_native_audio_clock_uses_measured_sink_latency():
    now = [5.0]

    class LatencySink(InstrumentedAudioSink):
        def latency_seconds(self):
            return 0.1

    backend = NativeCasuBackend(InstrumentedVideoSink(), LatencySink(),
                                clock=lambda: now[0])
    backend._state = PlaybackState.PLAYING
    block = decode_audio_block(encode_audio_block(
        pcm=b"\0\0" * 10, pts=0, time_base_num=1, time_base_den=1000,
        sample_rate=1000, channels=1, sample_count=10,
    ))
    backend._observe_audio_clock(block)
    assert backend._scheduler_position() == pytest.approx(-0.09)
    assert backend.position() == 0.0
    now[0] += 0.1
    assert backend._scheduler_position() == pytest.approx(0.01)
    backend._rate = 2.0
    backend._observe_audio_clock(block, media_end_seconds=0.2)
    assert backend._scheduler_position() == pytest.approx(0.0)
    now[0] += 0.05
    assert backend._scheduler_position() == pytest.approx(0.1)


def test_native_audio_rate_resamples_pcm_and_restarts_transactionally(tmp_path):
    source = tmp_path / "native.casu"
    audio_payload = encode_audio_block(
        pcm=b"\0\0" * 10, pts=200, time_base_num=1, time_base_den=1000,
        sample_rate=1000, channels=1, sample_count=10,
    )
    write_native_v2(source, {
        "format": "CASUNAT2", "version": 2,
        "streams": [{"stream_id": 1, "type": "audio", "time_base": [1, 1000],
                     "sample_rate": 1000, "channels": 1}],
    }, [NativeChunk(ChunkType.AUDIO_BLOCK, 1, 200, audio_payload)])
    video, audio = InstrumentedVideoSink(), InstrumentedAudioSink()
    backend = NativeCasuBackend(video, audio)
    backend.open_casu(source); backend.play()
    assert backend.is_actively_playing()
    assert backend.set_rate(2.0) == 2.0
    deadline = time.monotonic() + 1
    while backend.state() not in {PlaybackState.ENDED, PlaybackState.ERROR} and time.monotonic() < deadline:
        time.sleep(0.005)
    assert backend.state() == PlaybackState.ENDED
    assert audio.flushes == 1 and video.invalidations == 1
    assert audio.blocks[-1].sample_count == 5
    assert len(audio.blocks[-1].pcm) == 10
    backend.close()


def test_native_audio_resampler_preserves_channel_alignment_and_bounds():
    pcm = np.array([[0, 1000], [1000, 2000], [2000, 3000], [3000, 4000]],
                   dtype="<i2").tobytes()
    block = decode_audio_block(encode_audio_block(
        pcm=pcm, pts=7, time_base_num=1, time_base_den=1000,
        sample_rate=1000, channels=2, sample_count=4,
    ))
    fast = resample_audio_block(block, 2.0)
    assert fast.pts == 7 and fast.sample_count == 2
    assert np.frombuffer(fast.pcm, dtype="<i2").reshape(-1, 2).tolist() == [
        [0, 1000], [2000, 3000]]
    slow = resample_audio_block(block, 0.5)
    assert slow.sample_count == 8 and len(slow.pcm) == 32
    with pytest.raises(BackendError, match="finite"):
        resample_audio_block(block, float("nan"))


def test_native_media_delays_are_bounded_and_affect_audio_clock():
    now = [1.0]

    class LatencySink(InstrumentedAudioSink):
        def latency_seconds(self): return 0.1

    backend = NativeCasuBackend(InstrumentedVideoSink(), LatencySink(),
                                clock=lambda: now[0])
    assert backend.set_audio_delay(9000) == 5000
    assert backend.set_subtitle_delay(-9000) == -5000
    assert backend.set_audio_delay(50) == 50
    block = decode_audio_block(encode_audio_block(
        pcm=b"\0\0" * 10, pts=0, time_base_num=1, time_base_den=1000,
        sample_rate=1000, channels=1, sample_count=10,
    ))
    backend._observe_audio_clock(block)
    assert backend._audio_clock_media == pytest.approx(-0.04)
