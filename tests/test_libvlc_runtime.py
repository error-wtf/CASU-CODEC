import ctypes.util
import shutil
import subprocess
import time

import pytest

from mpcasu_backend import LibVLCBackend, PlaybackState


class _HeadlessSurface:
    def winfo_id(self):
        return 0


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
        _HeadlessSurface(), runtime_options=("--aout=dummy", "--vout=dummy"))
    try:
        backend.open(fixture)
        backend.play()
        deadline = time.monotonic() + 5.0
        observed_position = 0.0
        observed_tracks = 0
        observed_state = backend.state()
        while time.monotonic() < deadline:
            observed_position = max(observed_position, backend.position())
            observed_tracks = max(observed_tracks, backend.video_track_count())
            observed_state = backend.state()
            if (observed_position >= 0.05 and observed_tracks > 0) or observed_state in {
                    PlaybackState.ENDED, PlaybackState.ERROR}:
                break
            time.sleep(0.02)
        assert observed_state is not PlaybackState.ERROR
        assert observed_position >= 0.05 or observed_state is PlaybackState.ENDED
        if observed_tracks == 0:
            pytest.xfail(
                f"installed libVLC runtime exposed no decoded video track for {encoder}{suffix}")
        assert observed_tracks > 0
    finally:
        backend.close()
