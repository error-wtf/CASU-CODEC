# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Small, accessible Tk front-end for the CASU converter.

The CLI remains the automation/reference interface; this window only collects
the same explicit options and runs the converter without changing the source.
"""
from __future__ import annotations

import json
import math
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from casu.core import ANALYSIS_MODES, CasuCancelled, CasuError, ffprobe, duration
from casu.jobs import (ConversionCancelled, ConversionEngine, ConversionJob,
                       ConversionProfile, ConversionProgress,
                       conversion_journal_path, load_conversion_report,
                       write_conversion_report)
from casu.native import NativeCasuError, read_native
from casu.native_v2 import NativeV2Error, read_native_v2
from casu.schema import validate_manifest

BG = "#090B0D"
PANEL = "#111418"
PANEL_ALT = "#14181D"
RED = "#FF1E2D"
TEXT = "#F2F2F2"
SECONDARY = "#A7ABB0"


def _asset_path(name: str) -> Path:
    """Resolve bundled assets from a source tree or installed wheel."""
    local = Path(__file__).resolve().parent / "assets" / name
    if local.is_file():
        return local
    for root in (Path("/usr/share/casu-codec/assets"), Path("/usr/local/share/casu-codec/assets")):
        candidate = root / name
        if candidate.is_file():
            return candidate
    return local


class CASUConverter(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("CASU Converter")
        self.geometry("760x470")
        self.minsize(600, 360)
        self.source = tk.StringVar()
        self.output = tk.StringVar()
        self._sources: list[Path] = []
        self._source_root: Path | None = None
        self.mode = tk.StringVar(value="strict")
        # Sidecar remains the safe default until the native envelope is wired
        # into the player's CASU reader; users can explicitly opt into it.
        self.native_output = tk.BooleanVar(value=False)
        self.resume_jobs = tk.BooleanVar(value=True)
        self.fps = tk.DoubleVar(value=10.0)
        self.retries = tk.IntVar(value=0)
        self.status = tk.StringVar(value="Choose an MP4 or MP3 source.")
        self.source_info = tk.StringVar(value="No source inspected")
        self.output_info = tk.StringVar(value="The original source is never modified.")
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._busy = False
        self._paused = False
        self._build()

    def _build(self) -> None:
        self.configure(bg=BG)
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("CASU.TButton", background=PANEL_ALT, foreground=TEXT, borderwidth=0, padding=(10, 6))
        style.map("CASU.TButton", background=[("active", "#3A1015")])
        root = tk.Frame(self, bg=BG, padx=22, pady=20)
        root.pack(fill="both", expand=True)
        logo_path = _asset_path("casu_codec_logo_header.png")
        self._logo_image = None
        try:
            image = tk.PhotoImage(file=str(logo_path)); self._logo_image = image.subsample(max(1, image.width() // 140), max(1, image.height() // 60))
            self.iconphoto(True, self._logo_image)
            tk.Label(root, image=self._logo_image, bg=BG).pack(anchor="w")
        except (tk.TclError, OSError):
            tk.Label(root, text="CASU CONVERTER", bg=BG, fg=RED, font=("TkDefaultFont", 22, "bold")).pack(anchor="w")
        tk.Label(root, text="Codec for All Segmented Units · source media remains untouched", bg=BG, fg=SECONDARY).pack(anchor="w", pady=(0, 18))
        for label, variable, command in (("Source files", self.source, self.choose_source), ("Output folder", self.output, self.choose_output)):
            row = ttk.Frame(root); row.pack(fill="x", pady=5)
            tk.Label(row, text=label, width=16, bg=BG, fg=TEXT, anchor="w").pack(side="left")
            ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Browse…", style="CASU.TButton", command=command).pack(side="left", padx=(8, 0))
        folder_actions = tk.Frame(root, bg=BG); folder_actions.pack(fill="x", pady=(0, 4))
        ttk.Button(folder_actions, text="Add folder (recursive)", style="CASU.TButton", command=self.choose_folder).pack(side="left")
        ttk.Button(folder_actions, text="Remove selected", style="CASU.TButton", command=self.remove_selected).pack(side="left", padx=6)
        ttk.Button(folder_actions, text="Clear queue", style="CASU.TButton", command=self.clear_queue).pack(side="left")
        tk.Label(folder_actions, text="Each file is probed independently.", bg=BG, fg=SECONDARY).pack(side="left", padx=10)
        self.queue = tk.Listbox(root, height=4, bg=PANEL_ALT, fg=TEXT, selectbackground="#3A1015",
                                relief="flat", highlightthickness=0, activestyle="none", exportselection=False)
        self.queue.pack(fill="x", pady=(2, 6))
        info = tk.Frame(root, bg=PANEL_ALT, padx=14, pady=10)
        info.pack(fill="x", pady=(8, 4))
        tk.Label(info, text="SOURCE INSPECTION", bg=PANEL_ALT, fg=RED, font=("TkDefaultFont", 8, "bold")).pack(anchor="w")
        tk.Label(info, textvariable=self.source_info, bg=PANEL_ALT, fg=TEXT, anchor="w", justify="left").pack(fill="x", pady=(4, 0))
        tk.Label(info, textvariable=self.output_info, bg=PANEL_ALT, fg=SECONDARY, anchor="w").pack(fill="x", pady=(3, 0))
        options = tk.Frame(root, bg=BG); options.pack(fill="x", pady=12)
        ttk.Label(options, text="Analysis mode").pack(side="left")
        ttk.Combobox(options, textvariable=self.mode, values=sorted(ANALYSIS_MODES), state="readonly", width=18).pack(side="left", padx=8)
        ttk.Label(options, text="FPS").pack(side="left")
        ttk.Spinbox(options, from_=0.1, to=120.0, increment=0.5, textvariable=self.fps, width=8).pack(side="left", padx=8)
        ttk.Label(options, text="Retries").pack(side="left")
        ttk.Spinbox(options, from_=0, to=10, increment=1,
                    textvariable=self.retries, width=4).pack(side="left", padx=6)
        ttk.Checkbutton(options, text="Standalone segmented CASUNAT2", variable=self.native_output).pack(side="left", padx=12)
        ttk.Checkbutton(options, text="Resume verified jobs", variable=self.resume_jobs).pack(side="left", padx=4)
        self.progress = ttk.Progressbar(root, mode="determinate", maximum=100.0)
        self.progress.pack(fill="x", pady=(8, 4))
        tk.Label(root, textvariable=self.status, wraplength=680, bg=BG, fg=SECONDARY, anchor="w", justify="left").pack(fill="x", pady=5)
        actions = tk.Frame(root, bg=BG); actions.pack(anchor="e", pady=(12, 0))
        ttk.Button(actions, text="Convert", style="CASU.TButton", command=self.convert).pack(side="left")
        ttk.Button(actions, text="Verify output", style="CASU.TButton", command=self.verify_output).pack(side="left", padx=8)
        ttk.Button(actions, text="Last report", style="CASU.TButton",
                   command=self.show_last_report).pack(side="left", padx=(0, 8))
        self.pause_button = ttk.Button(actions, text="Pause queue", style="CASU.TButton", command=self.pause_queue, state="disabled")
        self.pause_button.pack(side="left", padx=(0, 8))
        self.cancel_button = ttk.Button(actions, text="Cancel", style="CASU.TButton", command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left")
        ttk.Button(actions, text="Close", style="CASU.TButton", command=self.destroy).pack(side="left")

    def choose_source(self) -> None:
        # Let ffprobe/libVLC decide support; a short extension whitelist would
        # hide valid legacy formats before the universal backend can inspect
        # them.
        paths = filedialog.askopenfilenames(filetypes=[("All media and files", "*.*"), ("All files", "*")])
        if paths:
            self._source_root = None
            self._set_sources([Path(path) for path in paths])

    def choose_folder(self) -> None:
        folder = filedialog.askdirectory(mustexist=True)
        if folder:
            self._source_root = Path(folder).expanduser().resolve()
            self._set_sources(sorted(path for path in Path(folder).rglob("*")
                                     if path.is_file() and path.suffix.lower() != ".casu"))

    def _set_sources(self, paths: list[Path]) -> None:
        self._sources = list(dict.fromkeys(path.expanduser().resolve() for path in paths if path.is_file()))
        self.queue.delete(0, "end")
        for path in self._sources:
            self.queue.insert("end", str(path))
        self.source.set(f"{len(self._sources)} file(s) selected" if self._sources else "")
        if len(self._sources) == 1:
            self.inspect_source(self._sources[0])
        elif self._sources:
            self.source_info.set(f"{len(self._sources)} files queued for conversion")
        else:
            self.source_info.set("No source files selected")

    def remove_selected(self) -> None:
        selected = set(self.queue.curselection())
        if not selected:
            return
        self._set_sources([path for index, path in enumerate(self._sources) if index not in selected])

    def clear_queue(self) -> None:
        self._source_root = None
        self._set_sources([])

    def choose_output(self) -> None:
        path = filedialog.askdirectory(mustexist=True)
        if path: self.output.set(path)

    def inspect_source(self, path: Path) -> None:
        try:
            probe = ffprobe(path)
            streams = probe.get("streams", [])
            kinds = ", ".join(sorted({str(item.get("codec_type", "unknown")) for item in streams})) or "no streams"
            codecs = ", ".join(str(item.get("codec_name")) for item in streams if item.get("codec_name")) or "unknown codec"
            self.source_info.set(f"{path.name}  ·  {kinds}  ·  {codecs}  ·  {duration(probe):.3f} s")
        except (CasuError, OSError, ValueError) as exc:
            self.source_info.set(f"Inspection unavailable: {exc}")

    def convert(self) -> None:
        if self._busy:
            return
        sources = self._sources or []
        if not sources and self.source.get() and Path(self.source.get()).is_file():
            sources = [Path(self.source.get()).expanduser().resolve()]
        if not sources:
            messagebox.showerror("CASU", "Choose one or more existing source files first."); return
        output_dir = Path(self.output.get()).expanduser() if self.output.get() else sources[0].parent
        if output_dir.exists() and not output_dir.is_dir():
            messagebox.showerror("CASU", "Output must be a directory."); return
        output_dir.mkdir(parents=True, exist_ok=True)
        outputs = [self._target_for(source, output_dir) for source in sources]
        if len(set(outputs)) != len(outputs):
            messagebox.showerror("CASU", "Multiple sources map to the same output name. Choose a different output folder or convert them separately.")
            return
        existing = [item for item in outputs if item.exists()]
        if existing and not messagebox.askyesno("Replace output?", f"Replace {len(existing)} existing CASU file(s)?"):
            return
        try:
            fps = float(self.fps.get())
        except (TypeError, ValueError):
            messagebox.showerror("CASU", "FPS must be a finite positive number."); return
        if not math.isfinite(fps) or fps <= 0:
            messagebox.showerror("CASU", "FPS must be positive."); return
        try:
            retries = int(self.retries.get())
        except (TypeError, ValueError, tk.TclError):
            messagebox.showerror("CASU", "Retries must be an integer from 0 to 10."); return
        if retries < 0 or retries > 10:
            messagebox.showerror("CASU", "Retries must be between 0 and 10."); return
        mode = self.mode.get()
        self._cancel_event.clear()
        self._pause_event.set()
        self._paused = False
        self._busy = True
        self.cancel_button.configure(state="normal")
        self.pause_button.configure(state="normal", text="Pause queue")
        self.progress.configure(value=0.0)
        self.status.set("Analyzing decoded source activity…")
        threading.Thread(target=self._worker, args=(sources, output_dir, fps, mode,
                                                    self.native_output.get(),
                                                    self.resume_jobs.get(), retries), daemon=True).start()

    def _target_for(self, source: Path, output_dir: Path) -> Path:
        """Map a source to a deterministic output without flattening folders."""
        source = source.expanduser().resolve()
        if self._source_root is not None:
            try:
                relative = source.relative_to(self._source_root)
            except ValueError:
                relative = Path(source.name)
            return (output_dir / relative).with_suffix(".casu")
        return output_dir / f"{source.stem}.casu"

    def _worker(self, sources: list[Path], output_dir: Path, fps: float, mode: str,
                native: bool, resume: bool, retries: int) -> None:
        report_path = output_dir / "casu_batch_report.json"
        jobs: list[ConversionJob] = []
        try:
            total = len(sources)
            profile = ConversionProfile(
                container="native-v2" if native else "sidecar",
                mode=mode,
                analysis_fps=fps,
            )
            jobs = [ConversionJob(source, self._target_for(source, output_dir), profile)
                    for source in sources]
            def report(event: ConversionProgress) -> None:
                eta = ("ETA --" if event.eta_seconds is None else
                       f"ETA {int(round(event.eta_seconds))} s")
                name = Path(event.source).name
                self.after(0, lambda event=event, name=name, eta=eta: (
                    self.progress.configure(value=event.overall_fraction * 100.0),
                    self.status.set(
                        f"{event.state.title()} {name} "
                        f"({event.job_index + 1}/{event.job_count}) · "
                        f"{event.elapsed_seconds:.1f} s · {eta}"
                    ),
                ))

            engine = ConversionEngine(
                journal=conversion_journal_path(output_dir, jobs)
            )
            converted_results = engine.run(
                jobs,
                force=True,
                cancel=self._cancel_event,
                pause=self._pause_event,
                progress_detail=report,
                resume=resume,
                retries=retries,
            )
            results = [item.__dict__ for item in converted_results]
            write_conversion_report(report_path, {
                "version": 1, "state": "COMPLETE", "mode": mode,
                "container": "native-v2" if native else "sidecar",
                "analysis_fps": fps, "retries": retries, "files": results,
            })
            converted = sum(item["status"] == "converted" for item in results)
            failed = len(results) - converted
            self.after(0, lambda: self._done(
                f"Converted {converted}/{total} file(s) to {output_dir}; {failed} failed."
            ))
        except ConversionCancelled as exc:
            completed = [item.__dict__ for item in exc.results]
            completed_outputs = {
                str(Path(item["output"]).expanduser().resolve()) for item in completed
            }
            cancelled = []
            for job in jobs:
                resolved_output = str(job.output.expanduser().resolve())
                if resolved_output in completed_outputs:
                    continue
                cancelled.append({
                    "source": str(job.source.expanduser().resolve()),
                    "output": resolved_output,
                    "status": "cancelled", "container": job.profile.container,
                    "attempts": exc.attempts if job == exc.active_job else 0,
                })
            write_conversion_report(report_path, {
                "version": 1, "state": "CANCELLED", "mode": mode,
                "container": "native-v2" if native else "sidecar",
                "analysis_fps": fps, "retries": retries,
                "files": completed + cancelled,
            })
            self.after(0, lambda: self._done("Conversion cancelled; no incomplete CASU output was kept.", error=False, cancelled=True))
        except CasuCancelled:
            self.after(0, lambda: self._done("Conversion cancelled; no incomplete CASU output was kept.", error=False, cancelled=True))
        except (CasuError, NativeCasuError, NativeV2Error, OSError, ValueError) as exc:
            self.after(0, lambda: self._done(f"Conversion failed: {exc}", error=True))

    def verify_output(self) -> None:
        """Verify every CASU file in the selected output directory."""
        directory = Path(self.output.get()).expanduser() if self.output.get() else None
        if directory is None or not directory.is_dir():
            messagebox.showerror("CASU", "Choose an existing output folder first.")
            return
        files = sorted(directory.rglob("*.casu"))
        if not files:
            messagebox.showinfo("CASU Verify", "No .casu files found in the output folder.")
            return
        passed = 0
        failures: list[str] = []
        for path in files:
            try:
                with path.open("rb") as handle:
                    magic = handle.read(8)
                if magic == b"CASUNAT1":
                    read_native(path, verify_payload=True)
                elif magic == b"CASUNAT2":
                    read_native_v2(path)
                else:
                    manifest = json.loads(path.read_text(encoding="utf-8"))
                    errors = validate_manifest(manifest)
                    if errors:
                        raise ValueError(errors[0])
                passed += 1
            except (OSError, ValueError, json.JSONDecodeError, NativeCasuError,
                    NativeV2Error) as exc:
                failures.append(f"{path.name}: {exc}")
        report = directory / "casu_verify_report.json"
        report.write_text(json.dumps({"version": 1, "checked": len(files),
                                      "passed": passed, "failed": len(failures),
                                      "errors": failures}, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
        if failures:
            messagebox.showerror("CASU Verify", f"{passed}/{len(files)} files passed. Details: {report}")
        else:
            messagebox.showinfo("CASU Verify", f"{passed}/{len(files)} files verified successfully.\nReport: {report}")

    def show_last_report(self) -> None:
        directory = Path(self.output.get()).expanduser() if self.output.get() else None
        if directory is None or not directory.is_dir():
            messagebox.showerror("CASU Report", "Choose an existing output folder first.")
            return
        report = directory / "casu_batch_report.json"
        try:
            payload = load_conversion_report(report)
        except CasuError as exc:
            messagebox.showerror("CASU Report", str(exc)); return
        lines = [
            f"State: {payload.get('state', 'COMPLETE')}",
            f"Container: {payload.get('container', 'unknown')}",
            f"Mode: {payload.get('mode', 'unknown')}",
            f"Configured retries: {payload.get('retries', 0)}",
            "",
        ]
        for index, item in enumerate(payload["files"], start=1):
            source = Path(str(item.get("source", "unknown"))).name
            status = str(item.get("status", "unknown")).upper()
            attempts = int(item.get("attempts") or 0)
            elapsed = item.get("conversion_seconds")
            timing = "--" if elapsed is None else f"{float(elapsed):.2f} s"
            lines.append(f"{index}. {status} · {source} · attempts={attempts} · {timing}")
            if item.get("error"):
                lines.append(f"   {str(item['error'])[:1000]}")
        dialog = tk.Toplevel(self); dialog.title("CASU · Last conversion report")
        dialog.configure(bg=BG); dialog.transient(self)
        text = tk.Text(dialog, width=92, height=min(30, max(10, len(lines) + 2)),
                       bg=PANEL_ALT, fg=TEXT, relief="flat", wrap="word")
        text.insert("1.0", "\n".join(lines)); text.configure(state="disabled")
        text.pack(fill="both", expand=True, padx=16, pady=16)

    def cancel(self) -> None:
        if self._busy:
            self._cancel_event.set()
            self.status.set("Cancellation requested — stopping decoder…")
            self.cancel_button.configure(state="disabled")

    def pause_queue(self) -> None:
        if not self._busy:
            return
        if self._paused:
            self._paused = False
            self._pause_event.set()
            self.pause_button.configure(text="Pause queue")
            self.status.set("Queue resumed.")
        else:
            self._paused = True
            self._pause_event.clear()
            self.pause_button.configure(text="Resume queue")
            self.status.set("Queue paused after the current file.")

    def _done(self, message: str, error: bool = False, cancelled: bool = False) -> None:
        self._busy = False
        self._paused = False
        self._pause_event.set()
        self.cancel_button.configure(state="disabled")
        self.pause_button.configure(state="disabled", text="Pause queue")
        self.progress.configure(value=0.0 if error else 100.0)
        self.status.set(message)
        if cancelled:
            return
        (messagebox.showerror if error else messagebox.showinfo)("CASU Converter", message)


def main() -> int:
    CASUConverter().mainloop(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
