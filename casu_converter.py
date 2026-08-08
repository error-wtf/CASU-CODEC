# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Small, accessible Tk front-end for the CASU converter.

The CLI remains the automation/reference interface; this window only collects
the same explicit options and runs the converter without changing the source.
"""
from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from casu.core import ANALYSIS_MODES, CasuError, analyze


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
        self._build()

    def _build(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="CASU Converter", font=("TkDefaultFont", 22, "bold")).pack(anchor="w")
        ttk.Label(root, text="Codec for All Segmented Units · source media remains untouched").pack(anchor="w", pady=(0, 18))
        for label, variable, command in (("Source media", self.source, self.choose_source), ("CASU output", self.output, self.choose_output)):
            row = ttk.Frame(root); row.pack(fill="x", pady=5)
            ttk.Label(row, text=label, width=16).pack(side="left")
            ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Browse…", command=command).pack(side="left", padx=(8, 0))
        options = ttk.Frame(root); options.pack(fill="x", pady=12)
        ttk.Label(options, text="Analysis mode").pack(side="left")
        ttk.Combobox(options, textvariable=self.mode, values=sorted(ANALYSIS_MODES), state="readonly", width=18).pack(side="left", padx=8)
        ttk.Label(options, text="FPS").pack(side="left")
        ttk.Spinbox(options, from_=0.1, to=120.0, increment=0.5, textvariable=self.fps, width=8).pack(side="left", padx=8)
        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.pack(fill="x", pady=(8, 4))
        ttk.Label(root, textvariable=self.status, wraplength=680).pack(anchor="w", pady=5)
        actions = ttk.Frame(root); actions.pack(anchor="e", pady=(12, 0))
        ttk.Button(actions, text="Convert", command=self.convert).pack(side="left")
        ttk.Button(actions, text="Close", command=self.destroy).pack(side="left", padx=8)

    def choose_source(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Media", "*.mp4 *.mp3 *.mkv *.mov *.m4a *.wav"), ("All files", "*.*")])
        if path:
            self.source.set(path)
            if not self.output.get(): self.output.set(path + ".casu")

    def choose_output(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".casu", filetypes=[("CASU manifest", "*.casu")])
        if path: self.output.set(path)

    def convert(self) -> None:
        source = Path(self.source.get()).expanduser()
        output = Path(self.output.get()).expanduser()
        if not source.is_file():
            messagebox.showerror("CASU", "Choose an existing source media file first."); return
        if output.exists() and not messagebox.askyesno("Replace output?", f"Replace {output.name}?"): return
        self.progress.start(12); self.status.set("Analyzing decoded source activity…")
        threading.Thread(target=self._worker, args=(source, output), daemon=True).start()

    def _worker(self, source: Path, output: Path) -> None:
        try:
            result = analyze(source, float(self.fps.get()), self.mode.get())
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            self.after(0, lambda: self._done(f"Wrote {output} without modifying the source."))
        except (CasuError, OSError, ValueError) as exc:
            self.after(0, lambda: self._done(f"Conversion failed: {exc}", error=True))

    def _done(self, message: str, error: bool = False) -> None:
        self.progress.stop(); self.status.set(message)
        (messagebox.showerror if error else messagebox.showinfo)("CASU Converter", message)


def main() -> int:
    CASUConverter().mainloop(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
