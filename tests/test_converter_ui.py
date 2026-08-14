from __future__ import annotations

import json
import os
import threading
import time

import pytest

import casu_converter
from casu_converter import CASUConverter
from casu.jobs import ConversionCancelled


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


def test_converter_cancel_reaches_engine_and_publishes_cancelled_report(
        tmp_path, monkeypatch):
    source = tmp_path / "input.mp4"; source.write_bytes(b"input")

    class CancellingEngine:
        def __init__(self, **_kwargs):
            pass

        def run(self, jobs, **kwargs):
            assert kwargs["cancel"].is_set()
            job = tuple(jobs)[0]
            raise ConversionCancelled(active_job=job, attempts=1)

    monkeypatch.setattr(casu_converter, "ConversionEngine", CancellingEngine)
    app = CASUConverter()
    try:
        app._busy = True
        app.cancel()
        app._worker([source], tmp_path, 10.0, "strict", True, False, 0)
        app.update()
        payload = json.loads((tmp_path / "casu_batch_report.json").read_text())
        assert payload["state"] == "CANCELLED"
        assert payload["files"][0]["status"] == "cancelled"
        assert payload["files"][0]["attempts"] == 1
        assert not (tmp_path / "input.casu").exists()
        assert "no incomplete" in app.status.get().lower()
    finally:
        app.destroy()


def test_converter_from_casu_exports_multiple_files_and_report(tmp_path, monkeypatch):
    sources = [tmp_path / "one.casu", tmp_path / "two.casu"]
    for source in sources:
        source.write_bytes(b"CASUNAT2")

    def fake_export(source, output):
        output.write_bytes(Path(source).stem.encode("ascii"))
        return output

    from pathlib import Path
    monkeypatch.setattr(casu_converter, "export_casu", fake_export)
    monkeypatch.setattr(casu_converter.messagebox, "showinfo", lambda *_args, **_kwargs: None)
    app = CASUConverter()
    try:
        app.direction.set("from-casu")
        app.export_format.set("flac")
        app._export_worker(sources, tmp_path)
        app.update()
        assert (tmp_path / "one.flac").read_bytes() == b"one"
        assert (tmp_path / "two.flac").read_bytes() == b"two"
        report = json.loads((tmp_path / "casu_batch_report.json").read_text())
        assert [item["status"] for item in report["files"]] == ["exported", "exported"]
    finally:
        app.destroy()


def test_converter_cancel_wakes_paused_queue():
    app = CASUConverter()
    try:
        app._busy = True
        app._pause_event.clear()
        app.cancel()
        assert app._cancel_event.is_set()
        assert app._pause_event.is_set()
    finally:
        app.destroy()


def test_converter_verifies_exported_media_mode(tmp_path, monkeypatch):
    exported = tmp_path / "movie.mp4"
    exported.write_bytes(b"media")
    monkeypatch.setattr(casu_converter, "ffprobe",
                        lambda _path: {"streams": [{"codec_type": "video"}]})
    monkeypatch.setattr(casu_converter.messagebox, "showinfo", lambda *_args, **_kwargs: None)
    app = CASUConverter()
    try:
        app.direction.set("media-to-media")
        app.export_format.set("mp4")
        app.output.set(str(tmp_path))
        app.verify_output()
        report = json.loads((tmp_path / "casu_media_verify_report.json").read_text())
        assert report == {"version": 1, "checked": 1, "passed": 1,
                          "failed": 0, "errors": []}
    finally:
        app.destroy()


def test_converter_media_worker_uses_full_profile_and_target(tmp_path, monkeypatch):
    source = tmp_path / "input.mkv"; source.write_bytes(b"input")
    captured = {}

    class FakeEngine:
        def __init__(self, **_kwargs):
            pass

        def run(self, jobs, **_kwargs):
            job = tuple(jobs)[0]
            captured["job"] = job
            return ()

    monkeypatch.setattr(casu_converter, "ConversionEngine", FakeEngine)
    monkeypatch.setattr(casu_converter.messagebox, "showinfo", lambda *_args, **_kwargs: None)
    app = CASUConverter()
    try:
        app.export_format.set("webm")
        app.media_preset.set("small")
        app.video_codec.set("libvpx-vp9")
        app.audio_codec.set("libopus")
        app.subtitle_mode.set("drop")
        app.all_tracks.set(False)
        app.preserve_metadata.set(False)
        app.tile_size.set(96)
        app.key_interval_seconds.set(1.5)
        app._worker([source], tmp_path / "out", 10.0, "strict", False,
                    True, 2, media_to_media=True)
        app.update()
        job = captured["job"]
        assert job.output == tmp_path / "out" / "input.webm"
        assert job.profile.container == "media"
        assert job.profile.media_preset == "small"
        assert job.profile.video_codec == "libvpx-vp9"
        assert job.profile.audio_codec == "libopus"
        assert job.profile.subtitle_mode == "drop"
        assert job.profile.all_tracks is False
        assert job.profile.preserve_metadata is False
        assert job.profile.tile_size == 96
        assert job.profile.key_interval_seconds == 1.5
        report = json.loads((tmp_path / "out" / "casu_batch_report.json").read_text())
        assert report["mode"] == "media-transcode"
        assert report["container"] == "webm"
        assert report["preset"] == "small"
        assert report["tile_size"] == 96
        assert report["key_interval_seconds"] == 1.5
    finally:
        app.destroy()


def test_converter_source_inspection_never_blocks_tk_thread(tmp_path, monkeypatch):
    source = tmp_path / "slow.mkv"; source.write_bytes(b"input")
    entered = threading.Event(); release = threading.Event()

    def slow_probe(_path):
        entered.set()
        assert release.wait(2.0)
        return {"streams": [{"codec_type": "video", "width": 320,
                             "height": 180, "pix_fmt": "yuv420p"}],
                "format": {"duration": "2.0"}, "chapters": []}

    monkeypatch.setattr(casu_converter, "detect_casu_kind", lambda _path: None)
    monkeypatch.setattr(casu_converter, "ffprobe", slow_probe)
    app = CASUConverter()
    try:
        started = time.monotonic()
        app.inspect_source(source)
        assert time.monotonic() - started < 0.2
        assert entered.wait(0.5)
        app.update()
        assert "Inspecting" in app.source_info.get()
        release.set()
        deadline = time.monotonic() + 1.0
        while "streams" not in app.source_info.get() and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        assert "1 streams" in app.source_info.get()
        assert "320×180" in app.source_info.get()
    finally:
        release.set()
        app.destroy()


def test_converter_rejects_unsafe_custom_export_extension():
    app = CASUConverter()
    try:
        app.export_format.set("../mp4")
        with pytest.raises(ValueError, match="filename extension"):
            app._export_extension()
    finally:
        app.destroy()
