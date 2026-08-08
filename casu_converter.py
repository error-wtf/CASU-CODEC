# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Small, accessible Tk front-end for the CASU converter.

The CLI remains the automation/reference interface; this window only collects
the same explicit options and runs the converter without changing the source.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from casu.core import ANALYSIS_MODES, CasuCancelled, CasuError, analyze, ffprobe, duration
from casu.native import NativeCasuError, read_native, write_native
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
        self.geometry("720x430")
        self.minsize(600, 360)
        self.source = tk.StringVar()
        self.output = tk.StringVar()
        self._sources: list[Path] = []
        self._source_root: Path | None = None
        self.mode = tk.StringVar(value="strict")
        # Sidecar remains the safe default until the native envelope is wired
        # into the player's CASU reader; users can explicitly opt into it.
        self.native_output = tk.BooleanVar(value=False)
        self.fps = tk.DoubleVar(value=10.0)
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
        ttk.Checkbutton(options, text="Standalone native CASU (experimental)", variable=self.native_output).pack(side="left", padx=12)
        self.progress = ttk.Progressbar(root, mode="determinate", maximum=100.0)
        self.progress.pack(fill="x", pady=(8, 4))
        tk.Label(root, textvariable=self.status, wraplength=680, bg=BG, fg=SECONDARY, anchor="w", justify="left").pack(fill="x", pady=5)
        actions = tk.Frame(root, bg=BG); actions.pack(anchor="e", pady=(12, 0))
        ttk.Button(actions, text="Convert", style="CASU.TButton", command=self.convert).pack(side="left")
        ttk.Button(actions, text="Verify output", style="CASU.TButton", command=self.verify_output).pack(side="left", padx=8)
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
        mode = self.mode.get()
        self._cancel_event.clear()
        self._pause_event.set()
        self._paused = False
        self._busy = True
        self.cancel_button.configure(state="normal")
        self.pause_button.configure(state="normal", text="Pause queue")
        self.progress.configure(value=0.0)
        self.status.set("Analyzing decoded source activity…")
        threading.Thread(target=self._worker, args=(sources, output_dir, fps, mode, self.native_output.get()), daemon=True).start()

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

    def _worker(self, sources: list[Path], output_dir: Path, fps: float, mode: str, native: bool) -> None:
        try:
            total = len(sources)
            results: list[dict[str, object]] = []
            for index, source in enumerate(sources):
                while not self._pause_event.wait(0.1):
                    if self._cancel_event.is_set():
                        raise CasuCancelled("conversion cancelled")
                output = self._target_for(source, output_dir)
                output.parent.mkdir(parents=True, exist_ok=True)
                def report(value: float, index=index, source=source) -> None:
                    overall = (index + max(0.0, min(1.0, value))) / total
                    self.after(0, lambda overall=overall, source=source: (
                        self.progress.configure(value=overall * 100.0),
                        self.status.set(f"Converting {source.name} ({index + 1}/{total})"),
                    ))
                try:
                    self.after(0, lambda source=source, index=index: self.status.set(f"Analyzing {source.name} ({index + 1}/{total})"))
                    result = analyze(source, fps, mode, progress=report, cancel=self._cancel_event)
                    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
                    self.after(0, lambda source=source, index=index: self.status.set(f"Writing {source.name} ({index + 1}/{total})"))
                    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent, text=True)
                    try:
                        if native:
                            os.close(fd)
                            os.unlink(temporary)
                            write_native(output, source, result)
                        else:
                            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                                handle.write(payload); handle.flush(); os.fsync(handle.fileno())
                            os.replace(temporary, output)
                    finally:
                        if os.path.exists(temporary): os.unlink(temporary)
                    results.append({"source": str(source), "output": str(output), "status": "converted",
                                    "container": "native" if native else "sidecar",
                                    "duration_s": result["source"].get("duration_s")})
                except CasuCancelled:
                    raise
                except (CasuError, NativeCasuError, OSError, ValueError) as exc:
                    # One unsupported/corrupt file must not discard successful
                    # conversions from the same folder job.
                    results.append({"source": str(source), "output": str(output),
                                    "status": "failed", "error": str(exc)})
            report_path = output_dir / "casu_batch_report.json"
            report_path.write_text(json.dumps({"version": 1, "mode": mode,
                                               "container": "native" if native else "sidecar",
                                               "analysis_fps": fps, "files": results},
                                              indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            converted = sum(item["status"] == "converted" for item in results)
            failed = len(results) - converted
            self.after(0, lambda: self._done(
                f"Converted {converted}/{total} file(s) to {output_dir}; {failed} failed."
            ))
        except CasuCancelled:
            self.after(0, lambda: self._done("Conversion cancelled; no incomplete CASU output was kept.", error=False, cancelled=True))
        except (CasuError, NativeCasuError, OSError, ValueError) as exc:
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
                else:
                    manifest = json.loads(path.read_text(encoding="utf-8"))
                    errors = validate_manifest(manifest)
                    if errors:
                        raise ValueError(errors[0])
                passed += 1
            except (OSError, ValueError, json.JSONDecodeError, NativeCasuError) as exc:
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
