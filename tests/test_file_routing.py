from __future__ import annotations

import pytest

from casu.cli import plan_conversion_inputs, plan_export_inputs
from casu.core import CasuError
from casu_converter import collect_folder_sources


def test_batch_file_routing_uses_content_after_rename(tmp_path):
    media = tmp_path / "ordinary.casu"; media.write_bytes(b"ordinary media")
    native = tmp_path / "renamed.mp4"; native.write_bytes(b"CASUNAT2payload")
    conversion = plan_conversion_inputs([tmp_path])
    exported = plan_export_inputs([tmp_path])
    assert [source for source, _relative in conversion] == [media.resolve()]
    assert [source for source, _relative in exported] == [native.resolve()]
    assert collect_folder_sources(tmp_path, from_casu=False) == [media.resolve()]
    assert collect_folder_sources(tmp_path, from_casu=True) == [native.resolve()]


def test_explicit_batch_direction_rejects_wrong_content(tmp_path):
    media = tmp_path / "ordinary.bin"; media.write_bytes(b"media")
    native = tmp_path / "native.bin"; native.write_bytes(b"CASUNAT1payload")
    with pytest.raises(CasuError, match="already CASU"):
        plan_conversion_inputs([native])
    with pytest.raises(CasuError, match="not a valid CASU"):
        plan_export_inputs([media])


def test_recursive_cli_batches_enforce_limit_while_walking(tmp_path, monkeypatch):
    import casu.cli as cli
    (tmp_path / "a.mp3").write_bytes(b"a")
    (tmp_path / "b.mp3").write_bytes(b"b")
    monkeypatch.setattr(cli, "MAX_REPORT_RESULTS", 1)
    with pytest.raises(CasuError, match="batch exceeds 1"):
        plan_conversion_inputs([tmp_path])
