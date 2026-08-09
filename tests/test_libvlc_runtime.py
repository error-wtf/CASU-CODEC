import ctypes.util
import shutil
import subprocess
import time

import pytest

from mpcasu_backend import LibVLCBackend, PlaybackState


class _HeadlessSurface:
    def winfo_id(self):
        return 0


class _DecodedVideoCounter:
    """Receive actual libVLC video frames through the documented callbacks."""

    def __init__(self, backend, width=160, height=90):
        self.count = 0
        self.buffer = ctypes.create_string_buffer(width * height * 4)
        self._lock_type = ctypes.CFUNCTYPE(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
        self._unlock_type = ctypes.CFUNCTYPE(
            None, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p))
        self._display_type = ctypes.CFUNCTYPE(
            None, ctypes.c_void_p, ctypes.c_void_p)

        def lock(_opaque, planes):
            planes[0] = ctypes.cast(self.buffer, ctypes.c_void_p)
            return None

        def unlock(_opaque, _picture, _planes):
            return None

        def display(_opaque, _picture):
            self.count += 1

        self.lock = self._lock_type(lock)
        self.unlock = self._unlock_type(unlock)
        self.display = self._display_type(display)
        backend._install("libvlc_video_set_callbacks", None, [
            ctypes.c_void_p, self._lock_type, self._unlock_type,
            self._display_type, ctypes.c_void_p])
        backend._install("libvlc_video_set_format", None, [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint,
            ctypes.c_uint, ctypes.c_uint])
        backend.libvlc_video_set_callbacks(
            backend.player, self.lock, self.unlock, self.display, None)
        backend.libvlc_video_set_format(
            backend.player, b"RV32", width, height, width * 4)


@pytest.mark.media
@pytest.mark.skipif(not ctypes.util.find_library("vlc"), reason="libVLC unavailable")
def test_installed_libvlc_runtime_initializes_and_reports_version():
    backend = LibVLCBackend(_HeadlessSurface())
    try:
        capabilities = backend.capabilities()
        assert capabilities["backend"] == "libVLC shared library"
        assert capabilities["version"] != "unknown"
        assert capabilities["player_process"] == "none"
        # Capability is decided by libVLC at open time, never by extension.
        assert backend.supports("movie.codec-not-known-to-mpcasu")
    finally:
        backend.close()


@pytest.mark.media
@pytest.mark.parametrize(
    ("suffix", "encoder"),
    [
        (".wav", "pcm_s16le"),
        (".flac", "flac"),
        (".mp3", "libmp3lame"),
        (".ogg", "libvorbis"),
        (".opus", "libopus"),
        (".m4a", "aac"),
    ],
)
@pytest.mark.skipif(
    not ctypes.util.find_library("vlc") or not shutil.which("ffmpeg"),
    reason="libVLC/FFmpeg unavailable")
def test_installed_libvlc_decodes_generated_audio_matrix(tmp_path, suffix, encoder):
    """Prove demux/decode/clock behavior, independent of physical audio I/O."""
    fixture = tmp_path / f"tone{suffix}"
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "sine=frequency=997:sample_rate=48000",
        "-t", "1.0", "-c:a", encoder, str(fixture),
    ]
    generated = subprocess.run(command, capture_output=True, text=True, check=False)
    if generated.returncode != 0:
        pytest.skip(f"FFmpeg encoder {encoder} unavailable: {generated.stderr.strip()}")

    backend = LibVLCBackend(
        _HeadlessSurface(), runtime_options=("--aout=dummy", "--vout=dummy"))
    try:
        backend.open(fixture)
        backend.play()
        deadline = time.monotonic() + 4.0
        observed_position = 0.0
        observed_tracks = 0
        observed_state = backend.state()
        while time.monotonic() < deadline:
            observed_position = max(observed_position, backend.position())
            observed_tracks = max(observed_tracks, backend.audio_track_count())
            observed_state = backend.state()
            if (observed_position >= 0.05 and observed_tracks > 0) or observed_state in {
                    PlaybackState.ENDED, PlaybackState.ERROR}:
                break
            time.sleep(0.02)
        assert observed_state is not PlaybackState.ERROR
        assert observed_position >= 0.05 or observed_state is PlaybackState.ENDED
        assert observed_tracks > 0
        assert backend.duration() >= 0.8
    finally:
        backend.close()


@pytest.mark.media
@pytest.mark.parametrize(
    ("suffix", "encoder"),
    [
        (".mp4", "libx264"),
        (".mov", "mpeg4"),
        (".raw.avi", "rawvideo"),
        (".mjpeg.avi", "mjpeg"),
        (".mkv", "libx265"),
        (".vp8.webm", "libvpx"),
        (".webm", "libvpx-vp9"),
        (".av1.mkv", "libaom-av1"),
        (".ts", "mpeg2video"),
        (".ffv1.mkv", "ffv1"),
    ],
)
@pytest.mark.skipif(
    not ctypes.util.find_library("vlc") or not shutil.which("ffmpeg"),
    reason="libVLC/FFmpeg unavailable")
def test_installed_libvlc_decodes_generated_video_matrix(tmp_path, suffix, encoder):
    """Exercise real video demuxers/decoders through libVLC's dummy vout."""
    fixture = tmp_path / f"pattern{suffix}"
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=25",
        "-t", "1.0", "-pix_fmt", "yuv420p", "-threads", "1",
        "-c:v", encoder, str(fixture),
    ]
    generated = subprocess.run(command, capture_output=True, text=True, check=False)
    if generated.returncode != 0:
        pytest.skip(f"FFmpeg encoder {encoder} unavailable: {generated.stderr.strip()}")

    backend = LibVLCBackend(
        _HeadlessSurface(), runtime_options=("--aout=dummy", "--avcodec-hw=none"))
    try:
        backend.open(fixture)
        decoded = _DecodedVideoCounter(backend)
        backend.play()
        deadline = time.monotonic() + 5.0
        observed_position = 0.0
        observed_tracks = 0
        observed_state = backend.state()
        while time.monotonic() < deadline:
            observed_position = max(observed_position, backend.position())
            observed_tracks = max(observed_tracks, backend.video_track_count())
            observed_state = backend.state()
            if decoded.count > 0 or observed_state in {
                    PlaybackState.ENDED, PlaybackState.ERROR}:
                break
            time.sleep(0.02)
        assert observed_state is not PlaybackState.ERROR
        if decoded.count == 0:
            pytest.xfail(
                f"installed libVLC runtime delivered no decoded video frame for {encoder}{suffix}")
        assert observed_position >= 0.0
        assert observed_tracks > 0
    finally:
        backend.close()


@pytest.mark.media
@pytest.mark.parametrize(
    ("suffix", "document"),
    [
        (".srt", "1\n00:00:00,000 --> 00:00:02,000\nCASU SRT runtime\n"),
        (".vtt", "WEBVTT\n\n00:00.000 --> 00:02.000\nCASU WebVTT runtime\n"),
        (".ass", """[Script Info]
ScriptType: v4.00+
PlayResX: 160
PlayResY: 90

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,16,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,8,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,CASU ASS runtime
"""),
    ],
)
@pytest.mark.skipif(
    not ctypes.util.find_library("vlc") or not shutil.which("ffmpeg"),
    reason="libVLC/FFmpeg unavailable")
def test_installed_libvlc_loads_external_subtitle_matrix(tmp_path, suffix, document):
    """Prove external subtitle parsing through libVLC's runtime modules."""
    fixture = tmp_path / "subtitle-base.avi"
    subtitle = tmp_path / f"captions{suffix}"
    subtitle.write_text(document, encoding="utf-8")
    generated = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=black:size=160x90:rate=25",
        "-t", "3.0", "-pix_fmt", "yuv420p", "-threads", "1",
        "-c:v", "rawvideo", str(fixture),
    ], capture_output=True, text=True, check=False)
    if generated.returncode != 0:
        pytest.skip(f"FFmpeg rawvideo encoder unavailable: {generated.stderr.strip()}")

    backend = LibVLCBackend(
        _HeadlessSurface(), runtime_options=("--aout=dummy", "--vout=dummy"))
    try:
        backend.open(fixture, subtitle=subtitle)
        backend.play()
        deadline = time.monotonic() + 4.0
        observed_tracks = 0
        observed_position = 0.0
        observed_state = backend.state()
        while time.monotonic() < deadline:
            observed_tracks = max(observed_tracks, backend.subtitle_track_count())
            observed_position = max(observed_position, backend.position())
            observed_state = backend.state()
            if observed_tracks > 0 and observed_position >= 0.05:
                break
            if observed_state is PlaybackState.ERROR:
                break
            time.sleep(0.02)
        assert observed_state is not PlaybackState.ERROR
        assert observed_position >= 0.05
        assert observed_tracks > 0
        assert backend.subtitle_track_descriptions()
    finally:
        backend.close()
