"""Reusable crash-aware conversion jobs for CLI and GUI front ends."""
from __future__ import annotations

import json
import hashlib
import csv
import functools
import os
import platform
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable

from .core import CasuCancelled, CasuError, analyze
from .fileio import read_bounded_json
from .native import read_native, write_native
from .native_v2 import ChunkType, convert_media_to_native_v2, read_native_v2
from .transcode import MEDIA_PRESETS, SUBTITLE_MODES, transcode_media


@dataclass(frozen=True)
class ConversionProfile:
    container: str = "native-v2"
    mode: str = "strict"
    analysis_fps: float = 10.0
    tile_size: int = 64
    key_interval_seconds: float = 3.0
    media_preset: str = "balanced"
    video_codec: str = "auto"
    audio_codec: str = "auto"
    subtitle_mode: str = "auto"
    all_tracks: bool = True
    preserve_metadata: bool = True

    def validate(self) -> None:
        if self.container not in {"sidecar", "native", "native-v2", "media"}:
            raise ValueError("unsupported conversion container")
        if self.analysis_fps <= 0 or self.tile_size <= 0 or self.key_interval_seconds <= 0:
            raise ValueError("conversion profile values must be positive")
        if self.media_preset not in MEDIA_PRESETS:
            raise ValueError("unsupported media conversion preset")
        if self.subtitle_mode not in SUBTITLE_MODES:
            raise ValueError("unsupported subtitle conversion mode")


@dataclass(frozen=True)
class ConversionJob:
    source: Path
    output: Path
    profile: ConversionProfile = ConversionProfile()


@dataclass(frozen=True)
class ConversionResult:
    source: str
    output: str
    status: str
    container: str
    duration_s: float | None = None
    error: str | None = None
    attempts: int = 1
    output_size: int | None = None
    output_sha256: str | None = None
    resumed: bool = False
    conversion_seconds: float | None = None
    source_size: int | None = None
    source_sha256: str | None = None
    profile_sha256: str | None = None
    tool_versions: dict[str, str] | None = None
    frame_count: int | None = None
    key_states: int | None = None
    tile_updates: int | None = None
    hold_count: int | None = None
    audio_blocks: int | None = None
    subtitle_packets: int | None = None
    verification_result: str | None = None
    warnings: tuple[str, ...] = ()


class ConversionCancelled(CasuCancelled):
    """Cancellation carrying the verified results completed before the stop."""
    def __init__(self, results: Iterable[ConversionResult] = (), *,
                 active_job: ConversionJob | None = None,
                 attempts: int = 0) -> None:
        super().__init__("conversion cancelled")
        self.results = tuple(results)
        self.active_job = active_job
        self.attempts = max(0, int(attempts))


@dataclass(frozen=True)
class ConversionProgress:
    job_index: int
    job_count: int
    source: str
    fraction: float
    overall_fraction: float
    elapsed_seconds: float
    eta_seconds: float | None
    state: str = "RUNNING"


class ConversionProgressTracker:
    """Monotonic batch-throughput estimator shared by every front end."""
    def __init__(self, job_count: int, *, clock: Callable[[], float] = time.monotonic):
        self.job_count = max(0, int(job_count))
        self.clock = clock
        self.started = float(clock())
        self._overall = 0.0

    def update(self, job_index: int, job: ConversionJob, fraction: float, *,
               state: str = "RUNNING") -> ConversionProgress:
        index = max(0, min(max(0, self.job_count - 1), int(job_index)))
        value = max(0.0, min(1.0, float(fraction)))
        raw = ((index + value) / self.job_count) if self.job_count else 1.0
        self._overall = max(self._overall, min(1.0, raw))
        elapsed = max(0.0, float(self.clock()) - self.started)
        eta = None
        if self._overall >= 1.0:
            eta = 0.0
        elif self._overall > 0.0 and elapsed > 0.0:
            eta = elapsed * (1.0 - self._overall) / self._overall
        return ConversionProgress(index, self.job_count, str(job.source), value,
                                  self._overall, elapsed, eta, state)


MAX_JOURNAL_BYTES = 8 * 1024 * 1024
MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_REPORT_RESULTS = 10_000


@functools.lru_cache(maxsize=1)
def conversion_tool_versions() -> dict[str, str]:
    """Return bounded real tool versions used by conversion reports."""
    versions = {"python": platform.python_version()}
    for name in ("ffmpeg", "ffprobe"):
        executable = shutil.which(name)
        if not executable:
            versions[name] = "unavailable"
            continue
        try:
            result = subprocess.run([executable, "-version"], check=False,
                                    capture_output=True, text=True, timeout=5)
            first = (result.stdout or result.stderr).splitlines()
            versions[name] = (first[0][:300] if first else "unknown")
        except (OSError, subprocess.TimeoutExpired):
            versions[name] = "unavailable"
    return versions


def _profile_sha256(profile: ConversionProfile) -> str:
    payload = json.dumps(asdict(profile), sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_report_payload(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise CasuError("conversion report has an invalid structure")
    files = payload.get("files")
    if (payload.get("version") != 1 or not isinstance(files, list)
            or len(files) > MAX_REPORT_RESULTS
            or not all(isinstance(item, dict) for item in files)
            or ("state" in payload
                and payload["state"] not in {"COMPLETE", "CANCELLED", "FAILED"})):
        raise CasuError("conversion report has an invalid structure")
    return payload


def load_conversion_report(path: str | Path) -> dict:
    """Load a bounded converter report for CLI/GUI inspection."""
    source = Path(path).expanduser().resolve()
    try:
        payload = read_bounded_json(source, max_bytes=MAX_REPORT_BYTES,
                                    label="conversion report")
    except (OSError, json.JSONDecodeError, CasuError) as exc:
        raise CasuError("conversion report is unavailable or invalid") from exc
    return _validate_report_payload(payload)


def _file_identity(path: Path, cancel: Any | None = None) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            if cancel is not None and getattr(cancel, "is_set", lambda: False)():
                raise CasuCancelled("conversion cancelled")
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def conversion_journal_path(directory: str | Path,
                            jobs: Iterable[ConversionJob]) -> Path:
    """Return a stable, collision-resistant journal path for one exact batch."""
    identity = [{
        "source": str(job.source.expanduser().resolve()),
        "output": str(job.output.expanduser().resolve()),
        "profile": asdict(job.profile),
    } for job in jobs]
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    suffix = hashlib.sha256(encoded).hexdigest()[:16]
    return Path(directory).expanduser().resolve() / f".casu-conversion-{suffix}.json"


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def write_conversion_report(path: str | Path, payload: dict) -> None:
    """Validate and atomically publish a bounded GUI/CLI conversion report."""
    validated = _validate_report_payload(payload)
    encoded = (json.dumps(validated, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_REPORT_BYTES:
        raise CasuError("conversion report exceeds safety limit")
    _atomic_json(Path(path).expanduser().resolve(), validated)


def filter_conversion_report(payload: dict, *, status: str = "all",
                             query: str = "") -> tuple[dict, ...]:
    """Return report rows matching a status and a case-insensitive text query.

    The report is validated first so callers can safely use this helper with
    data loaded from anywhere, not only :func:`load_conversion_report`.
    """
    validated = _validate_report_payload(payload)
    wanted = str(status or "all").strip().casefold()
    needle = str(query or "").strip().casefold()
    rows: list[dict] = []
    for item in validated["files"]:
        item_status = str(item.get("status", "unknown")).strip().casefold()
        if wanted not in {"", "all"} and item_status != wanted:
            continue
        if needle:
            searchable = "\n".join(str(item.get(field, "")) for field in (
                "source", "output", "status", "container", "error"))
            if needle not in searchable.casefold():
                continue
        rows.append(item)
    return tuple(rows)


def export_conversion_report_csv(payload: dict, path: str | Path, *,
                                 status: str = "all", query: str = "") -> Path:
    """Atomically export the selected report rows as a spreadsheet-safe CSV."""
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = filter_conversion_report(payload, status=status, query=query)
    fields = ("source", "output", "status", "container", "attempts",
              "duration_s", "conversion_seconds", "source_size",
              "source_sha256", "profile_sha256", "output_size",
              "output_sha256", "frame_count", "key_states", "tile_updates",
              "hold_count", "audio_blocks", "subtitle_packets",
              "verification_result", "resumed", "error")
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for item in rows:
                # Prevent spreadsheet formula injection without changing the
                # underlying JSON report. Paths beginning with these characters
                # are valid on POSIX systems and must remain data when opened.
                row = {field: item.get(field, "") for field in fields}
                for field in ("source", "output", "status", "container", "error"):
                    value = str(row[field] if row[field] is not None else "")
                    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
                        value = "'" + value
                    row[field] = value
                writer.writerow(row)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        try:
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return target


def export_conversion_report_markdown(payload: dict, path: str | Path, *,
                                      status: str = "all", query: str = "") -> Path:
    """Atomically export selected report rows as a bounded Markdown table."""
    target = Path(path).expanduser().resolve()
    rows = filter_conversion_report(payload, status=status, query=query)
    fields = ("source", "output", "status", "container", "attempts",
              "conversion_seconds", "output_size", "verification_result",
              "error")

    def cell(value: object) -> str:
        text = str("" if value is None else value).replace("\r", " ").replace("\n", " ")
        return text.replace("\\", "\\\\").replace("|", "\\|")[:4096]

    lines = ["# CASU conversion report", "", "| " + " | ".join(fields) + " |",
             "| " + " | ".join("---" for _ in fields) + " |"]
    lines.extend("| " + " | ".join(cell(item.get(field, "")) for field in fields) + " |"
                 for item in rows)
    encoded = ("\n".join(lines) + "\n").encode("utf-8")
    if len(encoded) > MAX_REPORT_BYTES:
        raise CasuError("Markdown conversion report exceeds safety limit")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
    return target


class ConversionEngine:
    def __init__(self, *, journal: str | Path | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.journal = Path(journal).expanduser().resolve() if journal else None
        self.clock = clock

    def run(self, jobs: Iterable[ConversionJob], *, force: bool = False,
            retries: int = 0, cancel: Any | None = None, pause: Any | None = None,
            progress: Callable[[ConversionJob, float], None] | None = None,
            progress_detail: Callable[[ConversionProgress], None] | None = None,
            resume: bool = False,
            ) -> tuple[ConversionResult, ...]:
        if retries < 0:
            raise ValueError("conversion retries must not be negative")
        values = tuple(jobs)
        outputs: set[Path] = set()
        for job in values:
            job.profile.validate()
            source = job.source.expanduser().resolve()
            output = job.output.expanduser().resolve()
            if source == output:
                raise CasuError("conversion output must differ from source")
            if output in outputs:
                raise CasuError(f"multiple jobs map to the same output: {output}")
            outputs.add(output)
        resumed = self._load_resume(values) if resume else {}
        results: list[ConversionResult] = []
        tracker = ConversionProgressTracker(len(values), clock=self.clock)

        def notify(index: int, job: ConversionJob, value: float,
                   state: str = "RUNNING") -> None:
            if progress:
                progress(job, max(0.0, min(1.0, float(value))))
            if progress_detail:
                progress_detail(tracker.update(index, job, value, state=state))

        def abort(job: ConversionJob | None = None, attempts: int = 0) -> None:
            self._journal(values, results, "CANCELLED")
            raise ConversionCancelled(results, active_job=job, attempts=attempts)

        self._journal(values, results, "RUNNING")
        for job_index, job in enumerate(values):
            if cancel is not None and getattr(cancel, "is_set", lambda: False)():
                abort(job)
            if pause is not None:
                while not pause.wait(0.1):
                    if cancel is not None and getattr(cancel, "is_set", lambda: False)():
                        abort(job)
            previous = resumed.get((str(job.source.expanduser().resolve()),
                                    str(job.output.expanduser().resolve())))
            if previous is not None:
                results.append(previous)
                notify(job_index, job, 1.0, "RESUMED")
                self._journal(values, results, "RUNNING")
                continue
            attempt = 0
            while True:
                attempt += 1
                job_started = float(self.clock())
                try:
                    result = self._convert(job, force=force, cancel=cancel,
                                           progress=(lambda value, index=job_index, job=job:
                                                     notify(index, job, value)))
                    result = ConversionResult(**{
                        **asdict(result), "attempts": attempt,
                        "conversion_seconds": max(0.0, float(self.clock()) - job_started),
                    })
                    break
                except CasuCancelled:
                    abort(job, attempt)
                except Exception as exc:
                    if cancel is not None and getattr(cancel, "is_set", lambda: False)():
                        try:
                            abort(job, attempt)
                        except ConversionCancelled as cancelled:
                            raise cancelled from exc
                    if attempt <= max(0, int(retries)):
                        continue
                    failure_details: dict[str, Any] = {
                        "profile_sha256": _profile_sha256(job.profile),
                        "tool_versions": dict(conversion_tool_versions()),
                        "verification_result": "FAILED",
                    }
                    try:
                        size, digest = _file_identity(job.source.expanduser().resolve())
                        failure_details.update(source_size=size,
                                               source_sha256=digest)
                    except OSError:
                        pass
                    result = ConversionResult(str(job.source), str(job.output), "failed",
                                              job.profile.container, error=str(exc),
                                              attempts=attempt,
                                              conversion_seconds=max(
                                                  0.0, float(self.clock()) - job_started),
                                              **failure_details)
                    break
            results.append(result)
            notify(job_index, job, 1.0, result.status.upper())
            self._journal(values, results, "RUNNING")
        self._journal(values, results, "COMPLETE")
        return tuple(results)

    def _convert(self, job: ConversionJob, *, force: bool, cancel: Any | None,
                 progress: Callable[[float], None] | None) -> ConversionResult:
        source = job.source.expanduser().resolve()
        output = job.output.expanduser().resolve()
        if not source.is_file():
            raise CasuError(f"input media does not exist: {source}")
        if output.exists() and not force:
            raise CasuError(f"output exists (use force): {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        profile = job.profile
        source_size, source_sha256 = _file_identity(source, cancel)
        details: dict[str, Any] = {
            "source_size": source_size,
            "source_sha256": source_sha256,
            "profile_sha256": _profile_sha256(profile),
            "tool_versions": dict(conversion_tool_versions()),
            "verification_result": "VERIFIED",
        }
        if profile.container == "media":
            converted = transcode_media(
                source, output, preset=profile.media_preset,
                video_codec=profile.video_codec, audio_codec=profile.audio_codec,
                subtitle_mode=profile.subtitle_mode,
                all_tracks=profile.all_tracks,
                preserve_metadata=profile.preserve_metadata,
                cancel=cancel, progress=progress)
            duration = converted.get("format", {}).get("duration")
            details.update({
                "frame_count": sum(int(item.get("nb_frames") or 0)
                                   for item in converted.get("streams", [])
                                   if item.get("codec_type") == "video") or None,
                "verification_result": "FFPROBE_VERIFIED",
            })
        elif profile.container == "native-v2":
            convert_media_to_native_v2(
                source, output, tile_width=profile.tile_size,
                tile_height=profile.tile_size,
                max_key_interval_seconds=profile.key_interval_seconds,
                cancel=cancel, progress=progress)
            container = read_native_v2(output, load_payloads=False)
            duration = container.manifest.get("source_provenance", {}).get("duration_s")
            counts = {kind: sum(chunk.chunk_type == kind for chunk in container.chunks)
                      for kind in (ChunkType.VIDEO_KEY_STATE,
                                   ChunkType.VIDEO_TILE_UPDATE,
                                   ChunkType.AUDIO_BLOCK,
                                   ChunkType.SUBTITLE_PACKET,
                                   ChunkType.SUBTITLE_BITMAP)}
            video_pts = {chunk.pts for chunk in container.chunks if chunk.chunk_type in
                         {ChunkType.VIDEO_KEY_STATE, ChunkType.VIDEO_TILE_UPDATE}}
            frame_count = sum(len(stream.get("frame_timeline") or [])
                              for stream in container.manifest.get("streams", [])
                              if stream.get("type") == "video")
            details.update({
                "frame_count": frame_count or None,
                "key_states": counts[ChunkType.VIDEO_KEY_STATE],
                "tile_updates": counts[ChunkType.VIDEO_TILE_UPDATE],
                "hold_count": max(0, frame_count - len(video_pts)) if frame_count else None,
                "audio_blocks": counts[ChunkType.AUDIO_BLOCK],
                "subtitle_packets": (counts[ChunkType.SUBTITLE_PACKET]
                                     + counts[ChunkType.SUBTITLE_BITMAP]),
                "verification_result": ("FULLY_VERIFIED" if container.integrity_verified
                                        else "FAILED"),
                "warnings": tuple(str(item)[:4096] for item in
                                  container.manifest.get("ignored_streams", [])),
            })
        else:
            manifest = analyze(source, profile.analysis_fps, profile.mode,
                               progress=progress, cancel=cancel)
            duration = manifest["source"].get("duration_s")
            spatial = manifest.get("video", {}).get("spatial_analysis", {})
            states = spatial.get("state_counts", {})
            details.update({
                "frame_count": manifest.get("video", {}).get("decoded_frame_count"),
                "key_states": states.get("KEY_STATE"),
                "tile_updates": states.get("UPDATE"),
                "hold_count": states.get("HOLD"),
                "audio_blocks": len(manifest.get("audio", {}).get("segments", [])),
                "verification_result": "MANIFEST_VALIDATED",
            })
            if profile.container == "native":
                write_native(output, source, manifest)
                read_native(output, verify_payload=True)
                details["verification_result"] = "CASUNAT1_FULLY_VERIFIED"
            else:
                _atomic_json(output, manifest)
        output_size, output_sha256 = _file_identity(output, cancel)
        return ConversionResult(str(source), str(output), "converted",
                                profile.container,
                                float(duration) if duration is not None else None,
                                output_size=output_size,
                                output_sha256=output_sha256, **details)

    def _load_resume(self, jobs: tuple[ConversionJob, ...]) -> dict[tuple[str, str], ConversionResult]:
        if self.journal is None or not self.journal.is_file():
            return {}
        try:
            payload = read_bounded_json(self.journal, max_bytes=MAX_JOURNAL_BYTES,
                                        label="conversion journal")
            recorded_jobs = payload["jobs"]
            recorded_results = payload["results"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError, CasuError) as exc:
            raise CasuError("conversion journal is invalid") from exc
        expected_jobs = [
            {"source": str(job.source), "output": str(job.output),
             "profile": asdict(job.profile)} for job in jobs
        ]
        if recorded_jobs != expected_jobs:
            raise CasuError("conversion journal does not match the requested jobs")
        reusable: dict[tuple[str, str], ConversionResult] = {}
        for item in recorded_results:
            try:
                result = ConversionResult(**item)
                output = Path(result.output).expanduser().resolve()
                expected_size = int(result.output_size)
                expected_digest = str(result.output_sha256)
            except (TypeError, ValueError, KeyError):
                continue
            if result.status != "converted" or len(expected_digest) != 64 or not output.is_file():
                continue
            size, digest = _file_identity(output)
            if size == expected_size and digest == expected_digest:
                reusable[(str(Path(result.source).expanduser().resolve()), str(output))] = replace(
                    result, resumed=True
                )
        return reusable

    def _journal(self, jobs: tuple[ConversionJob, ...],
                 results: list[ConversionResult], state: str) -> None:
        if self.journal is None:
            return
        _atomic_json(self.journal, {
            "version": 1, "state": state, "updated_ns": time.time_ns(),
            "jobs": [{"source": str(job.source), "output": str(job.output),
                      "profile": asdict(job.profile)} for job in jobs],
            "results": [asdict(result) for result in results],
        })
