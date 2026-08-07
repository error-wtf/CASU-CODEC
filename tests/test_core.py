import json
import shutil
from pathlib import Path

import pytest

from casu.core import analyze


VIDEO = Path("/home/error/Videos/giancarlo.mp4")


@pytest.mark.skipif(not VIDEO.exists() or not shutil.which("ffmpeg"), reason="test video/ffmpeg unavailable")
def test_giancarlo_manifest_preserves_source_metadata(tmp_path):
    manifest = analyze(VIDEO, analysis_fps=2.0)
    assert manifest["source"]["duration_s"] > 100
    assert manifest["streams"][0]["codec_type"] == "video"
    assert manifest["streams"][1]["codec_type"] == "audio"
    assert manifest["integrity"]["timestamps_are_source_of_truth"] is True
    assert manifest["video"]["state_is_hint_only"] is True
    assert manifest["audio"]["state_is_hint_only"] is True


def test_manifest_json_roundtrip(tmp_path):
    payload = {"state": "HOLD", "start_s": 0.0, "end_s": 1.0}
    target = tmp_path / "state.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    assert json.loads(target.read_text(encoding="utf-8")) == payload
