import json
import threading
from pathlib import Path

import pytest

from casu.core import CasuCancelled, CasuError
from casu.jobs import (ConversionCancelled, ConversionEngine, ConversionJob,
                       ConversionProfile, ConversionProgressTracker,
                       conversion_journal_path, load_conversion_report,
                       write_conversion_report)


def test_conversion_engine_sidecar_journal_and_failure_isolation(tmp_path, monkeypatch):
    good = tmp_path / "good.bin"; good.write_bytes(b"good")
    missing = tmp_path / "missing.bin"
    manifest = {"source": {"duration_s": 1.25}}
    monkeypatch.setattr("casu.jobs.analyze", lambda *_args, **_kwargs: manifest)
    engine = ConversionEngine(journal=tmp_path / "journal.json")
    results = engine.run([
        ConversionJob(good, tmp_path / "good.casu", ConversionProfile(container="sidecar")),
        ConversionJob(missing, tmp_path / "missing.casu", ConversionProfile(container="sidecar")),
    ])
    assert [item.status for item in results] == ["converted", "failed"]
    assert (tmp_path / "good.casu").is_file()
    assert '"state": "COMPLETE"' in (tmp_path / "journal.json").read_text(encoding="utf-8")


def test_conversion_engine_cancellation_is_fail_closed(tmp_path):
    source = tmp_path / "source.bin"; source.write_bytes(b"source")
    cancel = threading.Event(); cancel.set()
    engine = ConversionEngine(journal=tmp_path / "journal.json")
    with pytest.raises(CasuCancelled):
        engine.run([ConversionJob(source, tmp_path / "output.casu")], cancel=cancel)
    assert not (tmp_path / "output.casu").exists()


def test_conversion_engine_translates_native_cancellation(tmp_path, monkeypatch):
    source = tmp_path / "source.bin"; source.write_bytes(b"source")
    cancel = threading.Event()

    def cancelled_converter(*_args, **_kwargs):
        cancel.set()
        raise RuntimeError("native conversion cancelled")

    monkeypatch.setattr("casu.jobs.convert_media_to_native_v2", cancelled_converter)
    engine = ConversionEngine(journal=tmp_path / "journal.json")
    with pytest.raises(ConversionCancelled) as raised:
        engine.run([ConversionJob(source, tmp_path / "output.casu")], cancel=cancel)
    assert raised.value.active_job.source == source
    assert raised.value.attempts == 1 and raised.value.results == ()
    assert '"state": "CANCELLED"' in (tmp_path / "journal.json").read_text(encoding="utf-8")
    assert not (tmp_path / "output.casu").exists()


def test_conversion_cancellation_preserves_completed_batch_evidence(tmp_path, monkeypatch):
    first = tmp_path / "first.bin"; first.write_bytes(b"first")
    second = tmp_path / "second.bin"; second.write_bytes(b"second")
    cancel = threading.Event()

    def analyze_until_cancel(source, *_args, **_kwargs):
        if Path(source).name == "second.bin":
            cancel.set()
            raise CasuCancelled("conversion cancelled")
        return {"source": {"duration_s": 1.0}}

    monkeypatch.setattr("casu.jobs.analyze", analyze_until_cancel)
    profile = ConversionProfile(container="sidecar")
    jobs = [ConversionJob(first, tmp_path / "first.casu", profile),
            ConversionJob(second, tmp_path / "second.casu", profile)]
    engine = ConversionEngine(journal=tmp_path / "journal.json")
    with pytest.raises(ConversionCancelled) as raised:
        engine.run(jobs, cancel=cancel)
    assert [item.status for item in raised.value.results] == ["converted"]
    assert raised.value.active_job == jobs[1] and raised.value.attempts == 1
    assert (tmp_path / "first.casu").is_file()
    assert not (tmp_path / "second.casu").exists()
    journal = json.loads((tmp_path / "journal.json").read_text(encoding="utf-8"))
    assert journal["state"] == "CANCELLED"
    assert [item["status"] for item in journal["results"]] == ["converted"]


def test_conversion_engine_rejects_negative_retries(tmp_path):
    engine = ConversionEngine()
    with pytest.raises(ValueError, match="retries"):
        engine.run([], retries=-1)


def test_conversion_engine_resumes_only_hash_verified_output(tmp_path, monkeypatch):
    source = tmp_path / "source.bin"; source.write_bytes(b"source")
    output = tmp_path / "output.casu"
    calls = []

    def analyze_once(*_args, **_kwargs):
        calls.append(True)
        return {"source": {"duration_s": 1.0}}

    monkeypatch.setattr("casu.jobs.analyze", analyze_once)
    engine = ConversionEngine(journal=tmp_path / "journal.json")
    job = ConversionJob(source, output, ConversionProfile(container="sidecar"))
    first = engine.run([job])
    second = engine.run([job], resume=True)
    assert len(calls) == 1
    assert first[0].resumed is False
    assert second[0].status == "converted" and second[0].resumed is True

    output.write_text("tampered", encoding="utf-8")
    third = engine.run([job], force=True, resume=True)
    assert len(calls) == 2
    assert third[0].resumed is False


def test_conversion_engine_rejects_mismatched_resume_journal(tmp_path):
    first = tmp_path / "first.bin"; first.write_bytes(b"first")
    second = tmp_path / "second.bin"; second.write_bytes(b"second")
    engine = ConversionEngine(journal=tmp_path / "journal.json")
    engine.run([ConversionJob(first, tmp_path / "first.casu",
                              ConversionProfile(container="sidecar"))])
    with pytest.raises(CasuError, match="does not match"):
        engine.run([ConversionJob(second, tmp_path / "second.casu")], resume=True)


def test_conversion_batches_get_stable_distinct_journals(tmp_path):
    profile = ConversionProfile(container="native-v2")
    first = [ConversionJob(tmp_path / "a.mkv", tmp_path / "a.casu", profile)]
    second = [ConversionJob(tmp_path / "b.mkv", tmp_path / "b.casu", profile)]
    assert conversion_journal_path(tmp_path, first) == conversion_journal_path(tmp_path, first)
    assert conversion_journal_path(tmp_path, first) != conversion_journal_path(tmp_path, second)


def test_conversion_progress_eta_is_batch_level_and_monotonic(tmp_path):
    now = [0.0]
    tracker = ConversionProgressTracker(2, clock=lambda: now[0])
    job = ConversionJob(tmp_path / "input.mkv", tmp_path / "output.casu")
    now[0] = 10.0
    first = tracker.update(0, job, 0.25)
    assert first.overall_fraction == 0.125
    assert first.elapsed_seconds == 10.0
    assert first.eta_seconds == 70.0
    now[0] = 12.0
    regressed = tracker.update(0, job, 0.1)
    assert regressed.overall_fraction == first.overall_fraction
    finished = tracker.update(1, job, 1.0, state="CONVERTED")
    assert finished.overall_fraction == 1.0
    assert finished.eta_seconds == 0.0 and finished.state == "CONVERTED"


def test_conversion_report_loader_is_bounded_and_validated(tmp_path):
    report = tmp_path / "casu_batch_report.json"
    report.write_text('{"version":1,"files":[{"status":"converted"}]}',
                      encoding="utf-8")
    assert load_conversion_report(report)["files"][0]["status"] == "converted"
    report.write_text('{"version":2,"files":[]}', encoding="utf-8")
    with pytest.raises(CasuError, match="structure"):
        load_conversion_report(report)
    report.write_text('[]', encoding="utf-8")
    with pytest.raises(CasuError, match="structure"):
        load_conversion_report(report)


def test_conversion_report_writer_is_atomic_and_records_cancelled_state(tmp_path):
    report = tmp_path / "casu_batch_report.json"
    write_conversion_report(report, {
        "version": 1, "state": "CANCELLED",
        "files": [{"source": "input.mkv", "status": "cancelled"}],
    })
    assert load_conversion_report(report)["state"] == "CANCELLED"
    assert not list(tmp_path.glob(".casu_batch_report.json.*"))
