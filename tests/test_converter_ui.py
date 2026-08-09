from __future__ import annotations

import json
import os

import pytest

import casu_converter
from casu_converter import CASUConverter


pytestmark = [pytest.mark.media,
              pytest.mark.skipif(not os.environ.get("DISPLAY"),
                                 reason="Tk display unavailable")]


def test_converter_worker_passes_gui_retry_count_to_shared_engine(tmp_path, monkeypatch):
    source = tmp_path / "input.mp4"; source.write_bytes(b"input")
    captured = {}

    class FakeEngine:
        def __init__(self, **_kwargs):
            pass

        def run(self, _jobs, **kwargs):
            captured.update(kwargs)
            return ()

    monkeypatch.setattr(casu_converter, "ConversionEngine", FakeEngine)
    monkeypatch.setattr(casu_converter.messagebox, "showinfo", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(casu_converter.messagebox, "showerror", lambda *_args, **_kwargs: None)
    app = CASUConverter()
    try:
        app._worker([source], tmp_path, 10.0, "strict", True, False, 3)
        app.update()
        assert captured["retries"] == 3
        payload = json.loads((tmp_path / "casu_batch_report.json").read_text())
        assert payload["retries"] == 3
    finally:
        app.destroy()


def test_converter_opens_bounded_last_report_view(tmp_path):
    (tmp_path / "casu_batch_report.json").write_text(json.dumps({
        "version": 1, "mode": "strict", "container": "native-v2", "retries": 2,
        "files": [{"source": "/tmp/input.mkv", "status": "converted",
                   "attempts": 2, "conversion_seconds": 1.25}],
    }), encoding="utf-8")
    app = CASUConverter()
    try:
        app.output.set(str(tmp_path))
        app.show_last_report(); app.update()
        reports = [child for child in app.winfo_children()
                   if child.winfo_class() == "Toplevel"
                   and child.title() == "CASU · Last conversion report"]
        assert len(reports) == 1
    finally:
        app.destroy()
