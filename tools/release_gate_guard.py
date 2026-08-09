#!/usr/bin/env python3
"""Fail-closed repository release-gate guard.

Use ``--gate strict`` after Phase 1. The default checks global release blockers
and therefore remains non-zero until all product gates are complete.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    try:
        return (ROOT / relative).read_text(encoding="utf-8")
    except OSError:
        return ""


def _status() -> dict:
    try:
        return json.loads(_read("RELEASE_GATE_STATUS.json"))
    except json.JSONDecodeError:
        return {}


def strict_findings() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    required = [
        "casu/strict/model.py", "casu/strict/decoder.py", "casu/strict/canonical.py",
        "casu/strict/tiles.py", "casu/strict/state_builder.py",
    ]
    for relative in required:
        if not (ROOT / relative).is_file():
            errors.append(f"required STRICT module missing: {relative}")
    core = _read("casu/core.py")
    if "mode == \"strict\"" not in core or "analyze_strict_video(" not in core:
        errors.append("production analyze path does not select source-resolution STRICT")
    strict_block = core[core.find("def analyze_strict_video"):core.find("def analyze_audio")]
    for forbidden in ("fps=", "scale=160:90", "frame_index / analysis_fps"):
        if forbidden in strict_block:
            errors.append(f"STRICT production block contains forbidden preview logic: {forbidden}")
    if not (ROOT / "tests/test_strict_acceptance.py").is_file():
        errors.append("STRICT behavior acceptance tests missing")
    status = _status()
    gates = {item.get("id"): item for item in status.get("gates", [])
             if isinstance(item, dict)} if isinstance(status, dict) else {}
    strict = gates.get(1, {})
    if strict.get("status") != "PASS" or not strict.get("evidence"):
        errors.append("STRICT gate lacks PASS status with evidence")
    if "160:90" in core or "width: int = 160" in core:
        warnings.append("reduced activity preview remains (allowed only outside STRICT)")
    return errors, warnings


def _is_source_string_assert(test: ast.expr) -> bool:
    """Recognize source-text membership assertions without flagging runtime state.

    The prohibited shape is a literal string searched directly in a variable
    conventionally holding source text (``source`` or ``player``). Attribute
    access such as ``player.status.value`` is observable runtime behavior.
    """
    candidates = [test]
    if isinstance(test, ast.BoolOp):
        candidates = list(test.values)
    for candidate in candidates:
        if not isinstance(candidate, ast.Compare):
            continue
        left = candidate.left
        for operator, comparator in zip(candidate.ops, candidate.comparators):
            if (isinstance(operator, (ast.In, ast.NotIn))
                    and isinstance(left, ast.Constant)
                    and isinstance(left.value, str)
                    and isinstance(comparator, ast.Name)
                    and comparator.id in {"source", "player"}):
                return True
            left = comparator
    return False


def global_findings() -> tuple[list[str], list[str]]:
    errors, warnings = strict_findings()
    status = _status()
    gates = status.get("gates", []) if isinstance(status, dict) else []
    if any(item.get("status") != "PASS" for item in gates if isinstance(item, dict)):
        errors.append("one or more release gates are not PASS")
    versions = _read("casu/__init__.py") + _read("pyproject.toml") + _read("packaging/build_debs.sh")
    stable = re.compile(r"(?<!rc)(?<!-rc)1\.0\.0(?!rc)(?!-rc)")
    if stable.search(versions):
        errors.append("stable 1.0.0 appears in active version declarations while gates are open")
    player = _read("mpcasu_player.py")
    if "view not available in this release" in player:
        errors.append("visible placeholder navigation remains")
    pseudo = 0
    for path in (ROOT / "tests").glob("test_*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert) and _is_source_string_assert(node.test):
                pseudo += 1
    if pseudo:
        errors.append(f"source-string pseudo acceptance assertions remain: {pseudo}")
    backend = _read("mpcasu_backend.py")
    if "class CasuBackend(LibVLCBackend)" in backend:
        warnings.append("CASUNAT1 compatibility backend still inherits LibVLCBackend")
    return list(dict.fromkeys(errors)), list(dict.fromkeys(warnings))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", choices=("strict", "all"), default="all")
    args = parser.parse_args()
    errors, warnings = strict_findings() if args.gate == "strict" else global_findings()
    print("CASU RELEASE GATE GUARD")
    for heading, values in (("ERROR", errors), ("WARNING", warnings)):
        if values:
            print(f"\n{heading}:")
            for value in values:
                print(value)
    if not errors:
        print(f"\nPASS: {args.gate}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
