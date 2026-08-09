from __future__ import annotations

import sys

import pytest

from casu.probe import ProbeError, run_bounded, run_json


def test_bounded_probe_accepts_object_and_rejects_non_object():
    assert run_json([sys.executable, "-c", "print('{\"ok\": true}')"],
                    max_output_bytes=1024, timeout_seconds=2) == {"ok": True}
    with pytest.raises(ProbeError, match="root"):
        run_json([sys.executable, "-c", "print('[]')"],
                 max_output_bytes=1024, timeout_seconds=2)


def test_bounded_probe_kills_excessive_output_and_timeout():
    with pytest.raises(ProbeError, match="output exceeds"):
        run_json([sys.executable, "-c", "print('x' * 1000000)"],
                 max_output_bytes=1024, timeout_seconds=2)
    with pytest.raises(ProbeError, match="time limit"):
        run_json([sys.executable, "-c", "import time; time.sleep(2)"],
                 max_output_bytes=1024, timeout_seconds=0.05)


def test_bounded_subprocess_kills_growing_output_file(tmp_path):
    target = tmp_path / "output.bin"
    with pytest.raises(ProbeError, match="file output exceeds"):
        run_bounded([
            sys.executable, "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(b'x'*1000000)",
            str(target),
        ], max_output_bytes=1024, timeout_seconds=2,
            watched_paths=((target, 1024),))
