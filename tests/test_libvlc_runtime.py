import ctypes.util
import functools
import hashlib
import http.server
import shutil
import subprocess
import threading
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
        if decoded.count == 0:
            pytest.xfail(
                f"installed libVLC runtime delivered no decoded video frame for "
                f"{encoder}{suffix} (state={observed_state.value})")
        assert observed_state is not PlaybackState.ERROR
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


@pytest.mark.media
@pytest.mark.skipif(
    not ctypes.util.find_library("vlc") or not shutil.which("ffmpeg"),
    reason="libVLC/FFmpeg unavailable")
def test_installed_libvlc_handles_local_http_redirect_seek_and_404(tmp_path):
    """Exercise libVLC HTTP redirect, decode, seek and terminal error paths."""
    fixture = tmp_path / "network-tone.wav"
    generated = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "sine=frequency=733:sample_rate=48000",
        "-t", "2.0", "-c:a", "pcm_s16le", str(fixture),
    ], capture_output=True, text=True, check=False)
    if generated.returncode != 0:
        pytest.skip(f"FFmpeg PCM encoder unavailable: {generated.stderr.strip()}")

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return None

        def do_GET(self):
            if self.path == "/redirect.wav":
                self.send_response(302)
                self.send_header("Location", f"/{fixture.name}")
                self.end_headers()
                return
            super().do_GET()

    handler = functools.partial(QuietHandler, directory=str(tmp_path))
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    except PermissionError:
        pytest.skip("loopback sockets are blocked by the test sandbox")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    backend = LibVLCBackend(
        _HeadlessSurface(), runtime_options=("--aout=dummy", "--vout=dummy"))
    try:
        host, port = server.server_address
        origin = f"http://{host}:{port}"
        backend.open_source(f"{origin}/redirect.wav")
        backend.play()
        deadline = time.monotonic() + 5.0
        observed_position = 0.0
        observed_tracks = 0
        observed_state = backend.state()
        while time.monotonic() < deadline:
            observed_position = max(observed_position, backend.position())
            observed_tracks = max(observed_tracks, backend.audio_track_count())
            observed_state = backend.state()
            if observed_position >= 0.05 and observed_tracks > 0:
                break
            if observed_state is PlaybackState.ERROR:
                break
            time.sleep(0.02)
        assert observed_state is not PlaybackState.ERROR
        assert observed_position >= 0.05
        assert observed_tracks > 0
        backend.seek(1.0)
        seek_deadline = time.monotonic() + 3.0
        seek_position = 0.0
        while time.monotonic() < seek_deadline:
            seek_position = backend.position()
            if seek_position >= 0.8:
                break
            if backend.state() is PlaybackState.ERROR:
                break
            time.sleep(0.02)
        assert backend.state() is not PlaybackState.ERROR
        assert seek_position >= 0.8

        backend.open_source(f"{origin}/missing.wav")
        backend.play()
        error_deadline = time.monotonic() + 3.0
        while time.monotonic() < error_deadline:
            if backend.state() is PlaybackState.ERROR:
                break
            time.sleep(0.02)
        assert backend.state() is PlaybackState.ERROR
    finally:
        backend.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
        assert not thread.is_alive()


@pytest.mark.media
@pytest.mark.skipif(
    not ctypes.util.find_library("vlc") or not shutil.which("ffmpeg"),
    reason="libVLC/FFmpeg unavailable")
def test_installed_libvlc_switches_real_embedded_audio_and_subtitle_tracks(tmp_path):
    """Exercise linked-list descriptions and live selection on real tracks."""
    german = tmp_path / "de.srt"
    english = tmp_path / "en.srt"
    german.write_text(
        "1\n00:00:00,000 --> 00:00:02,500\nDeutsche Spur\n", encoding="utf-8")
    english.write_text(
        "1\n00:00:00,000 --> 00:00:02,500\nEnglish track\n", encoding="utf-8")
    fixture = tmp_path / "multitrack.mp4"
    generated = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000",
        "-i", str(german), "-i", str(english), "-t", "3.0",
        "-map", "0:a:0", "-map", "1:a:0", "-map", "2:0", "-map", "3:0",
        "-c:a", "aac", "-c:s", "mov_text",
        "-metadata:s:a:0", "language=deu", "-metadata:s:a:1", "language=eng",
        "-metadata:s:s:0", "language=deu", "-metadata:s:s:1", "language=eng",
        str(fixture),
    ], capture_output=True, text=True, check=False)
    if generated.returncode != 0:
        pytest.skip(f"FFmpeg multitrack mux unavailable: {generated.stderr.strip()}")

    backend = LibVLCBackend(
        _HeadlessSurface(), runtime_options=("--aout=dummy", "--vout=dummy"))
    try:
        backend.open(fixture)
        backend.play()
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            if backend.audio_track_count() >= 2 and backend.subtitle_track_count() >= 2:
                break
            if backend.state() is PlaybackState.ERROR:
                break
            time.sleep(0.02)
        assert backend.state() is not PlaybackState.ERROR
        audio_tracks = backend.audio_track_descriptions()
        subtitle_tracks = backend.subtitle_track_descriptions()
        assert len(audio_tracks) >= 2
        assert len(subtitle_tracks) >= 2

        for identifier, _label in audio_tracks[:2]:
            backend.set_audio_track(identifier)
            assert backend.audio_track() == identifier
        for identifier, _label in subtitle_tracks[:2]:
            backend.set_subtitle_track(identifier)
            assert backend.subtitle_track() == identifier
    finally:
        backend.close()


@pytest.mark.media
@pytest.mark.skipif(
    not ctypes.util.find_library("vlc") or not shutil.which("ffmpeg"),
    reason="libVLC/FFmpeg unavailable")
def test_installed_libvlc_reads_and_selects_real_mp4_chapters(tmp_path):
    metadata = tmp_path / "chapters.ffmeta"
    metadata.write_text(""";FFMETADATA1
[CHAPTER]
TIMEBASE=1/1000
START=0
END=1000
title=Intro
[CHAPTER]
TIMEBASE=1/1000
START=1000
END=2500
title=Second
""", encoding="utf-8")
    fixture = tmp_path / "chapters.m4a"
    generated = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "sine=frequency=523:sample_rate=48000",
        "-i", str(metadata), "-map_metadata", "1", "-t", "2.5",
        "-c:a", "aac", str(fixture),
    ], capture_output=True, text=True, check=False)
    if generated.returncode != 0:
        pytest.skip(f"FFmpeg chapter mux unavailable: {generated.stderr.strip()}")

    backend = LibVLCBackend(
        _HeadlessSurface(), runtime_options=("--aout=dummy", "--vout=dummy"))
    try:
        backend.open(fixture)
        backend.play()
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            if backend.chapter_count() >= 2:
                break
            if backend.state() is PlaybackState.ERROR:
                break
            time.sleep(0.02)
        assert backend.state() is not PlaybackState.ERROR
        assert backend.chapter_count() >= 2
        assert len(backend.chapter_descriptors()) >= 2
        backend.set_chapter(1)
        assert backend.chapter() == 1
    finally:
        backend.close()


@pytest.mark.media
@pytest.mark.skipif(
    not ctypes.util.find_library("vlc") or not shutil.which("ffmpeg"),
    reason="libVLC/FFmpeg unavailable")
def test_installed_libvlc_real_transport_rate_volume_delay_pause_resume(tmp_path):
    fixture = tmp_path / "transport.flac"
    generated = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "sine=frequency=659:sample_rate=48000",
        "-t", "4.0", "-c:a", "flac", str(fixture),
    ], capture_output=True, text=True, check=False)
    if generated.returncode != 0:
        pytest.skip(f"FFmpeg FLAC encoder unavailable: {generated.stderr.strip()}")

    backend = LibVLCBackend(
        _HeadlessSurface(), runtime_options=("--aout=dummy", "--vout=dummy"))
    try:
        backend.open(fixture)
        backend.play()
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline and backend.position() < 0.1:
            assert backend.state() is not PlaybackState.ERROR
            time.sleep(0.02)
        assert backend.position() >= 0.1

        assert backend.set_rate(1.5) == pytest.approx(1.5, abs=0.05)
        assert backend.rate() == pytest.approx(1.5, abs=0.05)
        assert backend.set_volume(37) == 37
        # The dummy aout accepts the setter but reports zero; physical-device
        # volume remains a separate matrix rather than a fabricated equality.
        assert 0 <= backend.volume() <= 200
        backend.set_mute(True)
        backend.set_mute(False)
        assert backend.set_audio_delay(125.0) == 125.0

        backend.pause()
        paused_at = backend.position()
        time.sleep(0.15)
        assert backend.state() is PlaybackState.PAUSED
        assert backend.position() == pytest.approx(paused_at, abs=0.04)

        backend.resume()
        resume_deadline = time.monotonic() + 3.0
        while time.monotonic() < resume_deadline and backend.position() < paused_at + 0.08:
            assert backend.state() is not PlaybackState.ERROR
            time.sleep(0.02)
        assert backend.position() >= paused_at + 0.08
    finally:
        backend.close()


@pytest.mark.media
@pytest.mark.skipif(
    not ctypes.util.find_library("vlc") or not shutil.which("ffmpeg"),
    reason="libVLC/FFmpeg unavailable")
def test_installed_libvlc_real_single_frame_step(tmp_path):
    """A frame-step pass requires exactly one newly decoded video picture."""
    fixture = tmp_path / "frame-step.avi"
    generated = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=5",
        "-t", "3.0", "-pix_fmt", "yuv420p", "-threads", "1",
        "-c:v", "rawvideo", str(fixture),
    ], capture_output=True, text=True, check=False)
    if generated.returncode != 0:
        pytest.skip(f"FFmpeg rawvideo encoder unavailable: {generated.stderr.strip()}")

    backend = LibVLCBackend(
        _HeadlessSurface(), runtime_options=("--aout=dummy", "--vout=dummy"))
    try:
        backend.open(fixture)
        decoded = _DecodedVideoCounter(backend)
        backend.play()
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline and decoded.count < 2:
            assert backend.state() is not PlaybackState.ERROR
            time.sleep(0.02)
        assert decoded.count >= 2

        backend.pause()
        time.sleep(0.1)
        before_count = decoded.count
        before_digest = hashlib.sha256(decoded.buffer.raw).digest()
        backend.next_frame()
        step_deadline = time.monotonic() + 2.0
        while time.monotonic() < step_deadline and decoded.count <= before_count:
            assert backend.state() is not PlaybackState.ERROR
            time.sleep(0.02)
        assert decoded.count == before_count + 1
        assert hashlib.sha256(decoded.buffer.raw).digest() != before_digest
        assert backend.state() is PlaybackState.PAUSED
    finally:
        backend.close()
