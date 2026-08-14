"""Content-based CASU file classification shared by desktop and converter."""
from __future__ import annotations

from pathlib import Path

from .core import CasuError
from .fileio import read_bounded_json
from .schema import validate_manifest

CASUNAT1 = "casunat1"
CASUNAT2 = "casunat2"
CASU_SIDECAR = "casu-sidecar"
MAX_SIDECAR_BYTES = 64 * 1024 * 1024


def detect_casu_kind(path: str | Path) -> str | None:
    """Return a CASU representation from bounded content, never its suffix."""
    source = Path(path).expanduser().resolve()
    try:
        with source.open("rb") as handle:
            prefix = handle.read(4096)
    except OSError as exc:
        raise CasuError(f"could not read media source: {source}") from exc
    if prefix[:8] == b"CASUNAT1":
        return CASUNAT1
    if prefix[:8] == b"CASUNAT2":
        return CASUNAT2
    if not prefix.lstrip().startswith(b"{"):
        return None
    try:
        manifest = read_bounded_json(source, max_bytes=MAX_SIDECAR_BYTES,
                                     label="CASU sidecar")
    except CasuError:
        return None
    return CASU_SIDECAR if not validate_manifest(manifest) else None
