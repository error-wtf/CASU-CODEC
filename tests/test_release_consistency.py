# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Release metadata consistency regression.

A release named X must not ship stale version strings or a mismatched
release status anywhere in the authoritative metadata locations.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import casu

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_version_consistent_across_release_files():
    version = casu.__version__
    assert re.search(rf'^version = "{re.escape(version)}"', _read("pyproject.toml"),
                     re.M), "pyproject.toml version differs"
    assert re.search(rf"^version={re.escape(version)}$", _read("packaging/build_debs.sh"),
                     re.M), "build_debs.sh version differs"
    gate = json.loads(_read("RELEASE_GATE_STATUS.json"))
    assert gate["product_version"] == version, "RELEASE_GATE_STATUS product_version differs"
    expected_status = "RELEASE_" + version.replace(".", "_")
    assert gate["release_status"] == expected_status, (
        f"release_status {gate['release_status']} does not match {expected_status}")
    readme = _read("README.md")
    assert f"`{version}`" in readme, "README version badge differs"
    assert f"casu-codec_{version}_all.deb" in readme, "README DEB filenames differ"
    html = _read("web/index.html")
    assert f"?v={version}" in html, "web asset version query differs"
    qt = _read("mpcasu_qt/main_window.py")
    assert f"MPCASU {version}" in qt, "Qt visible version differs"


def test_schema_accepts_current_version():
    from casu.core import CASU_FORMAT_VERSION
    from casu.schema import SUPPORTED_CASU_VERSIONS

    # The CONTAINER format version (written into manifests) must stay a
    # supported CASU version. It is deliberately decoupled from the app
    # release version: the format did not change with 5.0.0, and older
    # players must keep accepting newly written files.
    assert CASU_FORMAT_VERSION in SUPPORTED_CASU_VERSIONS
    assert CASU_FORMAT_VERSION == "3.0.0"
