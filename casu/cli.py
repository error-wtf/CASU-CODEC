# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

from .core import ANALYSIS_MODES, CasuError, analyze, play, resolve_casu_source
from .schema import validate_manifest
from .native import NativeCasuError, read_native, write_native
from .native_v2 import (NativeConversionError, NativeV2Error,
                        convert_media_to_native_v2, read_native_v2,
                        repair_native_v2)
from . import __version__
from .jobs import (ConversionEngine, ConversionJob, ConversionProfile,
                   MAX_REPORT_RESULTS, conversion_journal_path)
from .export import CasuExportError, export_casu
from .filetypes import detect_casu_kind
from .transcode import MEDIA_OUTPUT_EXTENSIONS, MEDIA_PRESETS, SUBTITLE_MODES


def plan_conversion_inputs(items: list[Path]) -> list[tuple[Path, Path]]:
    """Expand files/folders while retaining safe relative batch layout."""
    planned: list[tuple[Path, Path]] = []
    seen: set[Path] = set()
    for item in items:
        candidate = item.expanduser().resolve()
        if candidate.is_dir():
            segment_start = len(planned)
            for path in candidate.rglob("*"):
                if not path.is_file():
                    continue
                source = path.resolve()
                if source in seen:
                    continue
                try:
                    relative = source.relative_to(candidate)
                except ValueError:
                    # Do not let a file symlink escape the selected tree.
                    continue
                if detect_casu_kind(source) is not None:
                    continue
                seen.add(source)
                planned.append((source, relative))
                if len(planned) > MAX_REPORT_RESULTS:
                    raise CasuError(f"batch exceeds {MAX_REPORT_RESULTS} input files")
            planned[segment_start:] = sorted(
                planned[segment_start:], key=lambda entry: str(entry[1]))
        elif candidate.is_file():
            if detect_casu_kind(candidate) is not None:
                raise CasuError(f"conversion input is already CASU content: {candidate}")
            if candidate not in seen:
                seen.add(candidate)
                planned.append((candidate, Path(candidate.name)))
                if len(planned) > MAX_REPORT_RESULTS:
                    raise CasuError(f"batch exceeds {MAX_REPORT_RESULTS} input files")
        else:
            raise CasuError(f"input media does not exist: {candidate}")
    return planned


def plan_conversion_targets(planned: list[tuple[Path, Path]],
                            output_dir: Path) -> list[Path]:
    """Preserve subfolders and deterministically disambiguate collisions."""
    targets = [(output_dir / relative).with_suffix(".casu").resolve()
               for _source, relative in planned]
    groups: dict[Path, list[int]] = {}
    for index, target in enumerate(targets):
        groups.setdefault(target, []).append(index)
    for indexes in groups.values():
        if len(indexes) < 2:
            continue
        for index in indexes:
            source = planned[index][0]
            identity = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:8]
            targets[index] = targets[index].with_name(
                f"{targets[index].stem}-{identity}.casu")
    return targets


def plan_export_inputs(items: list[Path]) -> list[tuple[Path, Path]]:
    """Expand verified-CASU export inputs while preserving folder layout."""
    planned: list[tuple[Path, Path]] = []
    seen: set[Path] = set()
    for item in items:
        candidate = item.expanduser().resolve()
        if candidate.is_dir():
            segment_start = len(planned)
            for path in candidate.rglob("*"):
                if not path.is_file():
                    continue
                source = path.resolve()
                if source in seen:
                    continue
                try:
                    relative = source.relative_to(candidate)
                except ValueError:
                    continue
                if detect_casu_kind(source) is None:
                    continue
                seen.add(source); planned.append((source, relative))
                if len(planned) > MAX_REPORT_RESULTS:
                    raise CasuError(f"batch exceeds {MAX_REPORT_RESULTS} input files")
            planned[segment_start:] = sorted(
                planned[segment_start:], key=lambda entry: str(entry[1]))
        elif candidate.is_file():
            if detect_casu_kind(candidate) is None:
                raise CasuError(f"export input is not a valid CASU file: {candidate}")
            if candidate not in seen:
                seen.add(candidate); planned.append((candidate, Path(candidate.name)))
                if len(planned) > MAX_REPORT_RESULTS:
                    raise CasuError(f"batch exceeds {MAX_REPORT_RESULTS} input files")
        else:
            raise CasuError(f"export input does not exist: {candidate}")
    return planned


def plan_export_targets(planned: list[tuple[Path, Path]], output_dir: Path,
                        extension: str) -> list[Path]:
    normalized = extension.lower().lstrip(".")
    if not normalized.isalnum() or len(normalized) > 12:
        raise CasuError("export format must be a 1–12 character filename extension")
    targets = [(output_dir / relative).with_suffix(f".{normalized}").resolve()
               for _source, relative in planned]
    groups: dict[Path, list[int]] = {}
    for index, target in enumerate(targets):
        groups.setdefault(target, []).append(index)
    for indexes in groups.values():
        if len(indexes) > 1:
            for index in indexes:
                digest = hashlib.sha256(str(planned[index][0]).encode()).hexdigest()[:8]
                targets[index] = targets[index].with_name(
                    f"{targets[index].stem}-{digest}.{normalized}")
    return targets


def atomic_write_text(path: Path, payload: str) -> None:
    """Write reports/manifests without exposing a partial destination file."""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="casu", description="CASU — Codec for All Segmented Units: legacy-compatible MP4/MP3 segmented-state layer")
    p.add_argument("--version", action="version", version=f"CASU Codec for All Segmented Units {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze", help="write a CASU temporal-state sidecar")
    a.add_argument("input", type=Path)
    a.add_argument("-o", "--output", type=Path)
    a.add_argument("--analysis-fps", type=float, default=10.0)
    a.add_argument("--mode", choices=sorted(ANALYSIS_MODES), default="strict",
                   help="state-analysis policy; strict is the reference mode")
    c = sub.add_parser("convert", help="convert legacy media to CASU output without changing the source")
    c.add_argument("input", type=Path, nargs="+")
    c.add_argument("-o", "--output", type=Path)
    c.add_argument("--report", type=Path, help="write the machine-readable batch report to this path")
    c.add_argument("--analysis-fps", type=float, default=10.0)
    c.add_argument("--mode", choices=sorted(ANALYSIS_MODES), default="strict",
                   help="state-analysis policy; strict is the reference mode")
    c.add_argument("--container", choices=("sidecar", "native", "native-v2"), default="sidecar",
                   help="sidecar, CASUNAT1 compatibility envelope ('native'), or segmented CASUNAT2")
    c.add_argument("--force", action="store_true", help="replace an existing output atomically")
    c.add_argument("--retry", type=int, default=0,
                   help="retry each failed conversion this many times (default: 0)")
    c.add_argument("--resume", action="store_true",
                   help="reuse hash-verified completed outputs from a matching journal")
    n = sub.add_parser("pack", help="write a standalone native CASU container with a lossless source payload")
    n.add_argument("input", type=Path)
    n.add_argument("-o", "--output", type=Path, required=True)
    n.add_argument("--analysis-fps", type=float, default=10.0)
    n.add_argument("--mode", choices=sorted(ANALYSIS_MODES), default="strict")
    n2 = sub.add_parser("pack-v2", help="convert video/audio to standalone segmented CASUNAT2")
    n2.add_argument("input", type=Path)
    n2.add_argument("-o", "--output", type=Path, required=True)
    n2.add_argument("--tile-size", type=int, default=64)
    n2.add_argument("--key-interval", type=float, default=3.0)
    ni = sub.add_parser("native-info", help="verify and inspect a native CASU container")
    ni.add_argument("input", type=Path)
    repair = sub.add_parser("repair-v2", help="finalize the last declared complete CASUNAT2 prefix")
    repair.add_argument("input", type=Path)
    repair.add_argument("-o", "--output", type=Path, required=True)
    export = sub.add_parser("export", help="convert verified CASU back to an FFmpeg-supported media format")
    export.add_argument("input", type=Path, nargs="+")
    export.add_argument("-o", "--output", type=Path, required=True,
                        help="target filename; its extension selects the output format")
    export.add_argument("--format", dest="export_format",
                        help="target extension for multiple files or folders")
    export.add_argument("--report", type=Path,
                        help="write a machine-readable batch export report")
    media = sub.add_parser(
        "transcode", help="convert any FFmpeg-decodable media to another media format")
    media.add_argument("input", type=Path, nargs="+")
    media.add_argument("-o", "--output", type=Path, required=True,
                       help="target file for one input, or output directory for a batch")
    media.add_argument("--format", dest="media_format",
                       help="target extension required for multiple files/folders")
    media.add_argument("--preset", choices=sorted(MEDIA_PRESETS), default="balanced")
    media.add_argument("--video-codec", default="auto")
    media.add_argument("--audio-codec", default="auto")
    media.add_argument("--subtitles", choices=sorted(SUBTITLE_MODES), default="auto")
    media.add_argument("--first-tracks", action="store_true",
                       help="convert only the first video/audio/subtitle stream")
    media.add_argument("--strip-metadata", action="store_true")
    media.add_argument("--force", action="store_true")
    media.add_argument("--retry", type=int, default=0)
    media.add_argument("--resume", action="store_true")
    media.add_argument("--report", type=Path)
    v = sub.add_parser("play", help="validate a media path for MPCASU in-process playback")
    v.add_argument("input", type=Path)
    x = sub.add_parser("validate", help="validate a .casu manifest")
    x.add_argument("manifest", type=Path)
    x.add_argument("--verify-source", action="store_true",
                   help="also resolve the recorded source and verify its SHA-256 digest")
    vfy = sub.add_parser("verify", help="validate a .casu manifest and verify its recorded source")
    vfy.add_argument("manifest", type=Path)
    info = sub.add_parser("info", help="print machine-readable CASU manifest information")
    info.add_argument("manifest", type=Path)
    b = sub.add_parser("benchmark", help="measure deterministic CASU analysis cost and emit a JSON report")
    b.add_argument("input", type=Path)
    b.add_argument("-o", "--output", type=Path, help="write the report JSON to this path")
    b.add_argument("--analysis-fps", type=float, default=10.0)
    b.add_argument("--mode", choices=sorted(ANALYSIS_MODES), default="strict")
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "benchmark":
            if args.analysis_fps <= 0:
                raise CasuError("analysis FPS must be positive")
            if not args.input.is_file():
                raise CasuError(f"input media does not exist: {args.input}")
            started = time.perf_counter()
            result = analyze(args.input, args.analysis_fps, args.mode)
            elapsed = time.perf_counter() - started
            report = {
                "report": "casu-benchmark-1",
                "input": str(args.input.expanduser().resolve()),
                "source_size_bytes": result["source"].get("size_bytes"),
                "duration_s": result["source"].get("duration_s"),
                "analysis_fps": args.analysis_fps,
                "analysis_mode": args.mode,
                "conversion_analysis_seconds": round(elapsed, 6),
                "video_segments": len(result.get("video", {}).get("segments", [])),
                "audio_segments": len(result.get("audio", {}).get("segments", [])),
                "energy_measurement": "unavailable",
                "notes": ["This report measures analysis cost; it does not claim energy savings."],
            }
            payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
            if args.output:
                atomic_write_text(args.output, payload)
            print(payload, end="")
            return 0
        if args.command == "pack":
            if args.analysis_fps <= 0:
                raise CasuError("analysis FPS must be positive")
            source = args.input.expanduser().resolve()
            output = args.output.expanduser().resolve()
            manifest = analyze(source, args.analysis_fps, args.mode)
            native = write_native(output, source, manifest)
            print(json.dumps({"container": str(native), "native_version": 1,
                              "payload_bytes": source.stat().st_size,
                              "mode": args.mode}, indent=2))
            return 0
        if args.command == "pack-v2":
            output = convert_media_to_native_v2(
                args.input, args.output, tile_width=args.tile_size,
                tile_height=args.tile_size,
                max_key_interval_seconds=args.key_interval,
            )
            container_v2 = read_native_v2(output)
            print(json.dumps({"container": str(output), "native_version": 2,
                              "streams": len(container_v2.manifest.get("streams", [])),
                              "chunks": len(container_v2.chunks),
                              "seek_entries": len(container_v2.seek_entries),
                              "integrity_verified": container_v2.integrity_verified}, indent=2))
            return 0
        if args.command == "native-info":
            container = read_native(args.input)
            print(json.dumps({"container": str(container.path), "native_version": 1,
                              "payload_bytes": container.payload_length,
                              "payload_sha256": container.payload_sha256,
                              "manifest": container.manifest}, indent=2, ensure_ascii=False))
            return 0
        if args.command == "repair-v2":
            output = repair_native_v2(args.input, args.output)
            repaired = read_native_v2(output)
            print(json.dumps({"container": str(output), "native_version": 2,
                              "recovery": repaired.manifest.get("recovery"),
                              "chunks": len(repaired.chunks),
                              "integrity_verified": repaired.integrity_verified}, indent=2))
            return 0
        if args.command == "export":
            planned = plan_export_inputs(args.input)
            if not planned:
                raise CasuError("no .casu files found in the requested export inputs")
            destination = args.output.expanduser().resolve()
            single_file = (len(planned) == 1 and len(args.input) == 1
                           and args.input[0].expanduser().resolve().is_file()
                           and destination.suffix and not args.export_format)
            if single_file:
                targets = [destination]
            else:
                if destination.suffix:
                    raise CasuError("multiple export inputs require an output directory")
                if not args.export_format:
                    raise CasuError("multiple export inputs require --format")
                destination.mkdir(parents=True, exist_ok=True)
                targets = plan_export_targets(planned, destination,
                                              args.export_format)
            results = []
            for (source, _relative), target in zip(planned, targets):
                started = time.monotonic()
                try:
                    output = export_casu(source, target)
                    results.append({"source": str(source), "output": str(output),
                                    "status": "exported",
                                    "conversion_seconds": round(
                                        time.monotonic() - started, 6)})
                except (CasuError, CasuExportError, OSError, ValueError) as exc:
                    results.append({"source": str(source), "output": str(target),
                                    "status": "failed", "error": str(exc),
                                    "conversion_seconds": round(
                                        time.monotonic() - started, 6)})
            payload = {"version": 1, "state": "COMPLETE", "mode": "export",
                       "container": (targets[0].suffix.lstrip(".")
                                     if targets else args.export_format),
                       "files": results}
            if args.report:
                atomic_write_text(args.report,
                                  json.dumps(payload, indent=2,
                                             ensure_ascii=False) + "\n")
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0 if all(item["status"] == "exported" for item in results) else 1
        if args.command == "transcode":
            if args.retry < 0:
                raise CasuError("retry count must not be negative")
            planned = plan_conversion_inputs(args.input)
            if not planned:
                raise CasuError("no media files found in the requested inputs")
            destination = args.output.expanduser().resolve()
            single_file = (len(planned) == 1 and len(args.input) == 1
                           and args.input[0].expanduser().resolve().is_file()
                           and destination.suffix and not args.media_format)
            if single_file:
                if destination.suffix.lower() not in MEDIA_OUTPUT_EXTENSIONS:
                    raise CasuError("unsupported media output extension")
                targets = [destination]
                output_dir = destination.parent
                selected_format = destination.suffix.lstrip(".")
            else:
                if destination.suffix:
                    raise CasuError("multiple media inputs require an output directory")
                if not args.media_format:
                    raise CasuError("multiple media inputs require --format")
                extension = "." + args.media_format.lower().lstrip(".")
                if extension not in MEDIA_OUTPUT_EXTENSIONS:
                    raise CasuError("unsupported media output extension")
                destination.mkdir(parents=True, exist_ok=True)
                targets = plan_export_targets(planned, destination, extension)
                output_dir = destination
                selected_format = extension.lstrip(".")
            profile = ConversionProfile(
                container="media", media_preset=args.preset,
                video_codec=args.video_codec, audio_codec=args.audio_codec,
                subtitle_mode=args.subtitles, all_tracks=not args.first_tracks,
                preserve_metadata=not args.strip_metadata)
            jobs = [ConversionJob(source, target, profile)
                    for (source, _relative), target in zip(planned, targets)]
            results = ConversionEngine(
                journal=conversion_journal_path(output_dir, jobs)).run(
                    jobs, force=args.force, retries=args.retry, resume=args.resume)
            payload = {
                "version": 1, "state": "COMPLETE", "mode": "media-transcode",
                "container": selected_format, "preset": args.preset,
                "files": [item.__dict__ for item in results],
            }
            if args.report:
                atomic_write_text(args.report, json.dumps(
                    payload, indent=2, ensure_ascii=False) + "\n")
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0 if all(item.status == "converted" for item in results) else 1
        if args.command == "analyze":
            if args.analysis_fps <= 0:
                raise CasuError("analysis FPS must be positive")
            result = analyze(args.input, args.analysis_fps, args.mode)
            output = args.output or args.input.with_suffix(args.input.suffix + ".casu")
            output = output.expanduser().resolve()
            source_path = args.input.expanduser().resolve()
            if output == source_path:
                raise CasuError("output must differ from the source media; refusing to overwrite input")
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists() and args.command == "convert" and not args.force:
                raise CasuError(f"output exists (use --force): {output}")
            payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
            atomic_write_text(output, payload)
            print(json.dumps({"manifest": str(output), "duration_s": result["source"]["duration_s"],
                              "video_segments": len(result["video"].get("segments", [])),
                              "audio_segments": len(result["audio"].get("segments", [])),
                              "mode": result["casu"]["analysis_mode"]}, indent=2))
            return 0
        if args.command == "convert":
            if args.analysis_fps <= 0:
                raise CasuError("analysis FPS must be positive")
            if args.retry < 0:
                raise CasuError("retry count must not be negative")
            planned = plan_conversion_inputs(args.input)
            inputs = [source for source, _relative in planned]
            if not planned:
                raise CasuError("no source files found in the requested inputs")
            if args.output:
                output = args.output.expanduser().resolve()
                if len(inputs) > 1 and output.suffix.lower() == ".casu":
                    raise CasuError("multiple inputs require an output directory, not one .casu file")
                output_dir = output if len(inputs) > 1 or output.suffix.lower() != ".casu" else output.parent
            else:
                output_dir = inputs[0].parent
            output_dir.mkdir(parents=True, exist_ok=True)
            if len(inputs) == 1 and args.output and args.output.suffix.lower() == ".casu":
                targets = [args.output.expanduser().resolve()]
            elif len(inputs) == 1 and not args.output:
                targets = [inputs[0].with_suffix(inputs[0].suffix + ".casu")]
            else:
                targets = plan_conversion_targets(planned, output_dir)
            jobs: list[ConversionJob] = []
            for source, target in zip(inputs, targets):
                jobs.append(ConversionJob(
                    source, target,
                    ConversionProfile(args.container, args.mode, args.analysis_fps)))
            journal = conversion_journal_path(output_dir, jobs)
            results = ConversionEngine(journal=journal).run(
                jobs, force=args.force, retries=args.retry, resume=args.resume
            )
            report = [item.__dict__ for item in results]
            payload = json.dumps({"version": 1, "mode": args.mode, "container": args.container,
                                  "analysis_fps": args.analysis_fps,
                                  "files": report}, indent=2, ensure_ascii=False) + "\n"
            if args.report:
                atomic_write_text(args.report, payload)
            print(payload, end="")
            return 0 if all(item.status == "converted" for item in results) else 1
        if args.command == "play":
            play(args.input)
            return 0
        if args.command in {"validate", "verify", "info"}:
            # Native containers have a binary header and are verified through
            # the same integrity-aware reader as the converter GUI.
            try:
                with args.manifest.expanduser().open("rb") as handle:
                    magic = handle.read(8)
            except OSError as exc:
                raise CasuError(f"could not read manifest {args.manifest}: {exc}") from exc
            if magic == b"CASUNAT2":
                try:
                    container_v2 = read_native_v2(args.manifest)
                except NativeV2Error as exc:
                    if args.command == "info":
                        print(json.dumps({"valid": False, "native": True,
                                          "native_version": 2, "errors": [str(exc)]}, indent=2))
                        return 1
                    print(f"INVALID: {exc}")
                    return 1
                if args.command == "info":
                    print(json.dumps({"valid": True, "native": True, "native_version": 2,
                                      "streams": container_v2.manifest.get("streams", []),
                                      "chunks": len(container_v2.chunks),
                                      "seek_entries": len(container_v2.seek_entries),
                                      "integrity_verified": container_v2.integrity_verified},
                                     indent=2, ensure_ascii=False))
                else:
                    print("VALID: CASUNAT2 structure, seek index, and integrity verified")
                return 0
            if magic == b"CASUNAT1":
                try:
                    container = read_native(args.manifest, verify_payload=True)
                except NativeCasuError as exc:
                    if args.command == "info":
                        print(json.dumps({"valid": False, "native": True, "errors": [str(exc)]}, indent=2))
                        return 1
                    print(f"INVALID: {exc}")
                    return 1
                if args.command == "info":
                    print(json.dumps({"valid": True, "native": True,
                                      "payload_bytes": container.payload_length,
                                      "manifest": container.manifest}, indent=2, ensure_ascii=False))
                else:
                    print("VALID: native CASU container and payload integrity verified")
                return 0
            try:
                manifest = json.loads(args.manifest.expanduser().read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise CasuError(f"could not read manifest {args.manifest}: {exc}") from exc
            errors = validate_manifest(manifest)
            if errors:
                if args.command == "info":
                    print(json.dumps({"valid": False, "errors": errors}, indent=2))
                    return 1
                for error in errors:
                    print(f"INVALID: {error}")
                return 1
            verify_source = args.command == "verify" or getattr(args, "verify_source", False)
            if verify_source:
                try:
                    source = resolve_casu_source(args.manifest)
                except CasuError as exc:
                    if args.command == "info":
                        print(json.dumps({"valid": False, "errors": [str(exc)]}, indent=2))
                        return 1
                    print(f"INVALID: {exc}")
                    return 1
                if args.command == "info":
                    print(json.dumps({"source_verified": str(source)}, indent=2))
                    return 0
                print(f"VERIFIED source: {source}")
            if args.command == "info":
                print(json.dumps({
                    "valid": True,
                    "manifest": str(args.manifest.expanduser().resolve()),
                    "format": manifest.get("format", {}),
                    "source": manifest.get("source", {}),
                    "streams": manifest.get("streams", []),
                    "video_segments": len(manifest.get("video", {}).get("segments", [])),
                    "audio_segments": len(manifest.get("audio", {}).get("segments", [])),
                    "seek_index_entries": len(manifest.get("seek_index", {}).get("entries", [])),
                    "native_payload": manifest.get("seek_index", {}).get("native_key_states", False),
                    "integrity": manifest.get("integrity", {}),
                }, indent=2, ensure_ascii=False))
                return 0
            print(f"VALID CASU manifest: {args.manifest}")
            return 0
        raise CasuError("unknown command")
    except (CasuError, CasuExportError, NativeCasuError, NativeConversionError, NativeV2Error) as exc:
        print(f"casu: error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
