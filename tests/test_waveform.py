from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from casu.native_v2 import convert_media_to_native_v2
from casu.waveform import WaveformError, spectrum_bands, waveform_peaks


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg unavailable")
def test_waveform_uses_measured_pcm_for_legacy_and_native(tmp_path: Path):
    source = tmp_path / "tone.wav"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=8000:duration=0.2", "-y", str(source),
    ], check=True)
    legacy = waveform_peaks(source, points=64)
    assert 16 <= len(legacy) <= 64
    assert max(legacy) > 0.05

    native = convert_media_to_native_v2(source, tmp_path / "tone.casu")
    native_peaks = waveform_peaks(native, points=64)
    assert 16 <= len(native_peaks) <= 64
    assert max(native_peaks) > 0.05
    legacy_spectrum = spectrum_bands(source, bands=24)
    native_spectrum = spectrum_bands(native, bands=24)
    assert len(legacy_spectrum) == len(native_spectrum) == 24
    assert max(legacy_spectrum) == pytest.approx(1.0)
    assert max(native_spectrum) == pytest.approx(1.0)


def test_waveform_rejects_invalid_point_budget(tmp_path: Path):
    source = tmp_path / "audio.wav"; source.write_bytes(b"x")
    with pytest.raises(WaveformError, match="point count"):
        waveform_peaks(source, points=4)
