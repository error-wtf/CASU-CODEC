#!/usr/bin/env python3
"""MPCASU — a small, dependency-light media player built around FFplay.

The player intentionally delegates decoding to FFplay/FFmpeg. MPCASU owns the
library, CASU sidecar discovery, transport controls and safe fallback; it does
not reimplement mature MP4/MP3 decoders.
"""
from __future__ import annotations

import signal
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from casu.core import CasuError, resolve_casu_source
from casu.schema import validate_manifest


MEDIA = {".mp4", ".mp3", ".mkv", ".m4v", ".mov", ".flac", ".wav", ".ogg", ".webm", ".casu"}


class MPCASUPlayer(tk.Tk):
    def __init__(self, initial: Path | None = None):
        super().__init__()
        self.title("MPCASU Media Player")
        self.geometry("920x580")
        self.process: subprocess.Popen[str] | None = None
        self.current: Path | None = None
        self.duration = 0.0
        self.position = tk.DoubleVar(value=0.0)
        self.status = tk.StringVar(value="Ready — CASU and legacy media")
        self._dragging = False
        self._paused = False
        self._build()
        if initial:
            self.add_files([initial])

    def _build(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        left = ttk.Frame(root, width=260)
        left.pack(side="left", fill="y", padx=(0, 12))
        ttk.Label(left, text="MPCASU", font=("TkDefaultFont", 18, "bold")).pack(anchor="w")
        ttk.Label(left, text="CASU + MP4 · MP3 · MKV · FLAC", foreground="#607080").pack(anchor="w", pady=(0, 10))
        self.library = tk.Listbox(left, activestyle="dotbox", exportselection=False)
        self.library.pack(fill="both", expand=True)
        self.library.bind("<Double-Button-1>", lambda _event: self.play_selected())
        controls = ttk.Frame(left)
        controls.pack(fill="x", pady=(10, 0))
        ttk.Button(controls, text="Add", command=self.add_dialog).pack(side="left")
        ttk.Button(controls, text="Remove", command=self.remove_selected).pack(side="left", padx=5)

        right = ttk.Frame(root)
        right.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(right, background="#101418", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(20, 20, anchor="nw", text="MPCASU", fill="#d8e7f3", font=("TkDefaultFont", 24, "bold"), tags="title")
        self.canvas.create_text(20, 58, anchor="nw", text="Decoding is delegated to FFmpeg/FFplay; CASU controls state and provenance.", fill="#9eb2c2", tags="subtitle")
        self.timeline = ttk.Scale(right, from_=0, to=1, variable=self.position, command=self.seek_preview)
        self.timeline.pack(fill="x", pady=(10, 0))
        self.timeline.bind("<ButtonPress-1>", lambda _event: setattr(self, "_dragging", True))
        self.timeline.bind("<ButtonRelease-1>", lambda _event: (setattr(self, "_dragging", False), self.seek_restart()))
        bar = ttk.Frame(right)
        bar.pack(fill="x", pady=8)
        ttk.Button(bar, text="Play", command=self.play_selected).pack(side="left")
        ttk.Button(bar, text="Pause", command=self.pause).pack(side="left", padx=5)
        ttk.Button(bar, text="Stop", command=self.stop).pack(side="left")
        ttk.Button(bar, text="−10 s", command=lambda: self.seek_by(-10)).pack(side="left", padx=(18, 2))
        ttk.Button(bar, text="+10 s", command=lambda: self.seek_by(10)).pack(side="left")
        ttk.Label(right, textvariable=self.status).pack(anchor="w")
        self.bind("<space>", lambda _event: self.pause())
        self.bind("<Left>", lambda _event: self.seek_by(-10))
        self.bind("<Right>", lambda _event: self.seek_by(10))
        self.after(500, self._poll)

    def add_dialog(self):
        paths = filedialog.askopenfilenames(filetypes=[("Media", " ".join(f"*{x}" for x in sorted(MEDIA))), ("All files", "*.*")])
        self.add_files([Path(p) for p in paths])

    def add_files(self, paths: list[Path]):
        for path in paths:
            if path.exists() and path.suffix.lower() in MEDIA and str(path) not in self.library.get(0, "end"):
                self.library.insert("end", str(path))

    def remove_selected(self):
        selected = list(self.library.curselection())
        for index in reversed(selected):
            self.library.delete(index)

    def selected_path(self) -> Path | None:
        selected = self.library.curselection()
        if not selected:
            return self.current
        return Path(self.library.get(selected[0]))

    def _sidecar(self, path: Path) -> Path:
        return path.with_suffix(path.suffix + ".casu")

    def play_selected(self):
        path = self.selected_path()
        if not path:
            messagebox.showinfo("MPCASU", "Add a media file first.")
            return
        self.stop()
        self.current = path
        try:
            source = self._source_for(path)
        except CasuError as exc:
            messagebox.showerror("MPCASU", str(exc))
            self.status.set("Cannot play — safe fallback refused an invalid CASU manifest")
            return
        self.duration = self._probe_duration(source)
        self.timeline.configure(to=max(self.duration, 1.0))
        sidecar = path if path.suffix.lower() == ".casu" else self._sidecar(path)
        state = "CASU manifest selected" if path.suffix.lower() == ".casu" else ("CASU sidecar found" if sidecar.exists() else "legacy fallback — no CASU sidecar")
        self.status.set(f"{path.name} · {state}")
        self.process = subprocess.Popen(["ffplay", "-hide_banner", "-autoexit", "-window_title", "MPCASU — " + source.name, str(source)], text=True)
        self._paused = False

    def _source_for(self, path: Path) -> Path:
        if path.suffix.lower() != ".casu":
            return path
        source = resolve_casu_source(path)
        try:
            import json
            manifest = json.loads(path.read_text(encoding="utf-8"))
            errors = validate_manifest(manifest)
        except (OSError, ValueError, TypeError) as exc:
            raise CasuError(f"invalid CASU manifest: {path}") from exc
        if errors:
            raise CasuError(f"invalid CASU manifest: {errors[0]}")
        return source

    def _probe_duration(self, path: Path) -> float:
        try:
            out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], text=True)
            return max(0.0, float(out.strip()))
        except (OSError, ValueError, subprocess.CalledProcessError):
            return 0.0

    def pause(self):
        if self.process and self.process.poll() is None:
            if self._paused:
                self.process.send_signal(signal.SIGCONT)
                self._paused = False
                self.status.set("Playing — source timing is preserved")
            else:
                self.process.send_signal(signal.SIGSTOP)
                self._paused = True
                self.status.set("Paused — source timing is preserved")

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        self._paused = False

    def seek_by(self, seconds: float):
        self.position.set(max(0.0, min(self.duration, self.position.get() + seconds)))
        self.seek_restart()

    def seek_preview(self, _value):
        if self._dragging:
            return

    def seek_restart(self):
        if not self.current:
            return
        path = self.current
        offset = self.position.get()
        try:
            source = self._source_for(path)
        except CasuError as exc:
            self.status.set(str(exc))
            return
        self.stop()
        self.process = subprocess.Popen(["ffplay", "-hide_banner", "-autoexit", "-ss", f"{offset:.3f}", "-window_title", "MPCASU — " + source.name, str(source)], text=True)

    def _poll(self):
        if self.process and self.process.poll() is not None:
            self.process = None
        self.after(500, self._poll)


def main() -> int:
    initial = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else None
    MPCASUPlayer(initial).mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
