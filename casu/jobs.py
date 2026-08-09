"""Reusable crash-aware conversion jobs for CLI and GUI front ends."""
from __future__ import annotations

import json
import hashlib
import os
import tempfile
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable

from .core import CasuCancelled, CasuError, analyze
from .native import write_native
from .native_v2 import convert_media_to_native_v2, read_native_v2


@dataclass(frozen=True)
class ConversionProfile:
    container: str = "native-v2"
    mode: str = "strict"
    analysis_fps: float = 10.0
    tile_size: int = 64
    key_interval_seconds: float = 3.0

    def validate(self) -> None:
        if self.container not in {"sidecar", "native", "native-v2"}:
            raise ValueError("unsupported conversion container")
        if self.analysis_fps <= 0 or self.tile_size <= 0 or self.key_interval_seconds <= 0:
            raise ValueError("conversion profile values must be positive")


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


MAX_JOURNAL_BYTES = 8 * 1024 * 1024


def _file_identity(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
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


class ConversionEngine:
    def __init__(self, *, journal: str | Path | None = None):
        self.journal = Path(journal).expanduser().resolve() if journal else None

    def run(self, jobs: Iterable[ConversionJob], *, force: bool = False,
            retries: int = 0, cancel: Any | None = None, pause: Any | None = None,
            progress: Callable[[ConversionJob, float], None] | None = None,
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
        self._journal(values, results, "RUNNING")
        for job in values:
            if cancel is not None and getattr(cancel, "is_set", lambda: False)():
                self._journal(values, results, "CANCELLED")
                raise CasuCancelled("conversion cancelled")
            if pause is not None:
                while not pause.wait(0.1):
                    if cancel is not None and getattr(cancel, "is_set", lambda: False)():
                        self._journal(values, results, "CANCELLED")
                        raise CasuCancelled("conversion cancelled")
            previous = resumed.get((str(job.source.expanduser().resolve()),
                                    str(job.output.expanduser().resolve())))
            if previous is not None:
                results.append(previous)
                if progress:
                    progress(job, 1.0)
                self._journal(values, results, "RUNNING")
                continue
            attempt = 0
            while True:
                attempt += 1
                try:
                    result = self._convert(job, force=force, cancel=cancel,
                                           progress=(lambda value, job=job: progress(job, value))
                                           if progress else None)
                    result = ConversionResult(**{**asdict(result), "attempts": attempt})
                    break
                except CasuCancelled:
                    self._journal(values, results, "CANCELLED")
                    raise
                except Exception as exc:
                    if cancel is not None and getattr(cancel, "is_set", lambda: False)():
                        self._journal(values, results, "CANCELLED")
                        raise CasuCancelled("conversion cancelled") from exc
                    if attempt <= max(0, int(retries)):
                        continue
                    result = ConversionResult(str(job.source), str(job.output), "failed",
                                              job.profile.container, error=str(exc),
                                              attempts=attempt)
                    break
            results.append(result)
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
        if profile.container == "native-v2":
            convert_media_to_native_v2(
                source, output, tile_width=profile.tile_size,
                tile_height=profile.tile_size,
                max_key_interval_seconds=profile.key_interval_seconds,
                cancel=cancel, progress=progress)
            container = read_native_v2(output, load_payloads=False)
            duration = container.manifest.get("source_provenance", {}).get("duration_s")
        else:
            manifest = analyze(source, profile.analysis_fps, profile.mode,
                               progress=progress, cancel=cancel)
            duration = manifest["source"].get("duration_s")
            if profile.container == "native":
                write_native(output, source, manifest)
            else:
                _atomic_json(output, manifest)
        output_size, output_sha256 = _file_identity(output)
        return ConversionResult(str(source), str(output), "converted",
                                profile.container,
                                float(duration) if duration is not None else None,
                                output_size=output_size,
                                output_sha256=output_sha256)

    def _load_resume(self, jobs: tuple[ConversionJob, ...]) -> dict[tuple[str, str], ConversionResult]:
        if self.journal is None or not self.journal.is_file():
            return {}
        if self.journal.stat().st_size > MAX_JOURNAL_BYTES:
            raise CasuError("conversion journal exceeds safety limit")
        try:
            payload = json.loads(self.journal.read_text(encoding="utf-8"))
            recorded_jobs = payload["jobs"]
            recorded_results = payload["results"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
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
