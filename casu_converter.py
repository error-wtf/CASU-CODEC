# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Small, accessible Tk front-end for the CASU converter.

The CLI remains the automation/reference interface; this window only collects
the same explicit options and runs the converter without changing the source.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from casu.core import ANALYSIS_MODES, CasuError, analyze, ffprobe, duration

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
        self.mode = tk.StringVar(value="strict")
        self.fps = tk.DoubleVar(value=10.0)
        self.status = tk.StringVar(value="Choose an MP4 or MP3 source.")
        self.source_info = tk.StringVar(value="No source inspected")
        self.output_info = tk.StringVar(value="The original source is never modified.")
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
        for label, variable, command in (("Source media", self.source, self.choose_source), ("CASU output", self.output, self.choose_output)):
            row = ttk.Frame(root); row.pack(fill="x", pady=5)
            tk.Label(row, text=label, width=16, bg=BG, fg=TEXT, anchor="w").pack(side="left")
            ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Browse…", style="CASU.TButton", command=command).pack(side="left", padx=(8, 0))
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
        self.progress = ttk.Progressbar(root, mode="determinate", maximum=100.0)
        self.progress.pack(fill="x", pady=(8, 4))
        tk.Label(root, textvariable=self.status, wraplength=680, bg=BG, fg=SECONDARY, anchor="w", justify="left").pack(fill="x", pady=5)
        actions = tk.Frame(root, bg=BG); actions.pack(anchor="e", pady=(12, 0))
        ttk.Button(actions, text="Convert", style="CASU.TButton", command=self.convert).pack(side="left")
        ttk.Button(actions, text="Close", style="CASU.TButton", command=self.destroy).pack(side="left", padx=8)

    def choose_source(self) -> None:
        # Let ffprobe/libVLC decide support; a short extension whitelist would
        # hide valid legacy formats before the universal backend can inspect
        # them.
        path = filedialog.askopenfilename(filetypes=[("All media and files", "*.*"), ("All files", "*")])
        if path:
            self.source.set(path)
            if not self.output.get(): self.output.set(path + ".casu")
            self.inspect_source(Path(path))

    def choose_output(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".casu", filetypes=[("CASU manifest", "*.casu")])
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
        source = Path(self.source.get()).expanduser()
        output = Path(self.output.get()).expanduser()
        if not source.is_file():
            messagebox.showerror("CASU", "Choose an existing source media file first."); return
        try:
            if output.resolve() == source.resolve():
                messagebox.showerror("CASU", "The output must differ from the source media.")
                return
        except OSError:
            messagebox.showerror("CASU", "The source or output path could not be resolved.")
            return
        if output.exists() and not messagebox.askyesno("Replace output?", f"Replace {output.name}?"): return
        try:
            fps = float(self.fps.get())
        except (TypeError, ValueError):
            messagebox.showerror("CASU", "FPS must be a finite positive number."); return
        if fps <= 0:
            messagebox.showerror("CASU", "FPS must be positive."); return
        mode = self.mode.get()
        self.progress.configure(value=0.0)
        self.status.set("Analyzing decoded source activity…")
        threading.Thread(target=self._worker, args=(source, output, fps, mode), daemon=True).start()

    def _worker(self, source: Path, output: Path, fps: float, mode: str) -> None:
        try:
            def report(value: float) -> None:
                # Tk widgets are only touched by the UI thread.  The analysis
                # worker emits measured progress; it never runs a repaint or
                # blocks on a modal dialog.
                self.after(0, lambda: self.progress.configure(value=max(0.0, min(100.0, value * 100.0))))

            result = analyze(source, fps, mode, progress=report)
            output.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
            fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent, text=True)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload); handle.flush(); os.fsync(handle.fileno())
                os.replace(temporary, output)
            finally:
                if os.path.exists(temporary): os.unlink(temporary)
            self.after(0, lambda: self._done(f"Wrote {output} without modifying the source."))
        except (CasuError, OSError, ValueError) as exc:
            self.after(0, lambda: self._done(f"Conversion failed: {exc}", error=True))

    def _done(self, message: str, error: bool = False) -> None:
        self.progress.configure(value=0.0 if error else 100.0)
        self.status.set(message)
        (messagebox.showerror if error else messagebox.showinfo)("CASU Converter", message)


def main() -> int:
    CASUConverter().mainloop(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
