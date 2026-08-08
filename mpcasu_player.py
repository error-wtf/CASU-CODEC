# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
#!/usr/bin/env python3
"""MPCASU — an in-process media player using the libVLC shared-library API.

MPCASU owns the window, playback state, CASU validation, clock polling and
transport controls. It does not launch an external player executable.
"""
from __future__ import annotations

import sys
import json
import math
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from casu.core import CasuError, resolve_casu_source
from casu.schema import validate_manifest
from mpcasu_backend import BackendError, CasuBackend, LibVLCBackend, PlaybackState


MEDIA = {".mp4", ".mp3", ".mkv", ".m4v", ".mov", ".flac", ".wav", ".ogg", ".webm", ".m4a", ".aac", ".opus", ".aiff", ".alac", ".casu"}

BG = "#090B0D"
PANEL = "#111418"
PANEL_ALT = "#14181D"
RED = "#FF1E2D"
RED_DARK = "#3A1015"
TEXT = "#F2F2F2"
SECONDARY = "#A7ABB0"
MUTED = "#686E75"


class MPCASUPlayer(tk.Tk):
    def __init__(self, initial: Path | list[Path] | None = None):
        super().__init__()
        self.title("MPCASU Media Player")
        self.geometry("1360x820")
        self.minsize(980, 620)
        self.configure(bg=BG)
        self.backend: LibVLCBackend | None = None
        self.current: Path | None = None
        self.duration = 0.0
        self.position = tk.DoubleVar(value=0.0)
        self.status = tk.StringVar(value="Ready — CASU and legacy media")
        self._dragging = False
        self._paused = False
        self._started_at = 0.0
        self._start_offset = 0.0
        self._visual_phase = 0.0
        self._visual_state = "idle"
        self._visual_segments: list[dict] = []
        self._visual_video_segments: list[dict] = []
        self._visual_audio_segments: list[dict] = []
        self._logo_image = None
        self._build()
        if initial:
            self.add_files(initial if isinstance(initial, list) else [initial])

    def _build(self):
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("MPC.TButton", background=PANEL_ALT, foreground=TEXT, borderwidth=0, padding=(10, 6))
        style.map("MPC.TButton", background=[("active", RED_DARK)])
        style.configure("MPC.Horizontal.TScale", troughcolor="#24282d", background=RED)
        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True)
        top = tk.Frame(root, bg=BG, height=62); top.pack(fill="x", padx=18, pady=(12, 6)); top.pack_propagate(False)
        logo = tk.Frame(top, bg=BG); logo.pack(side="left")
        logo_path = Path(__file__).resolve().parent / "assets" / "mpcasu_player_logo_header.png"
        try:
            if logo_path.is_file():
                source_logo = tk.PhotoImage(file=str(logo_path))
                self._logo_image = source_logo.subsample(max(1, source_logo.width() // 140), max(1, source_logo.height() // 60))
                tk.Label(logo, image=self._logo_image, bg=BG).pack(anchor="w")
            else:
                raise tk.TclError("logo asset unavailable")
        except tk.TclError:
            tk.Label(logo, text="◈ MPCASU", bg=BG, fg=RED, font=("TkDefaultFont", 19, "bold")).pack(anchor="w")
            tk.Label(logo, text="PLAYER", bg=BG, fg=SECONDARY, font=("TkDefaultFont", 8, "bold")).pack(anchor="w", padx=(30, 0))
        self.now_playing = tk.Label(top, text="NO MEDIA SELECTED", bg=BG, fg=SECONDARY, font=("TkDefaultFont", 10, "bold")); self.now_playing.pack(side="left", padx=42)
        tk.Label(top, text="CASU · LEGACY SAFE", bg=BG, fg=MUTED, font=("TkDefaultFont", 9)).pack(side="right")

        body = tk.Frame(root, bg=BG); body.pack(fill="both", expand=True, padx=18)
        left = tk.Frame(body, bg=PANEL, width=220); left.pack(side="left", fill="y", padx=(0, 10)); left.pack_propagate(False)
        self._nav(left, "LIBRARY", ["Now Playing", "Library", "CASU Files", "Movies", "TV Shows", "Music", "Playlists"])
        self._nav(left, "DEVICES", ["Local Disk", "Media Drive", "Network Share"])
        self._nav(left, "ONLINE", ["CASU Hub", "Web Videos", "Podcasts"])
        self._nav(left, "PLAYLISTS", ["Favorites", "Recently Added", "4K Collection", "Workout Mix"])
        tk.Label(left, text="LOADED MEDIA", bg=PANEL, fg=MUTED, font=("TkDefaultFont", 8, "bold"), anchor="w").pack(fill="x", padx=14, pady=(12, 4))
        self.library = tk.Listbox(left, height=4, bg=PANEL_ALT, fg=SECONDARY, selectbackground=RED_DARK, selectforeground=TEXT, relief="flat", highlightthickness=0, activestyle="none", exportselection=False)
        self.library.pack(fill="x", padx=10)
        self.library.bind("<Double-Button-1>", lambda _event: self.play_selected())
        actions = tk.Frame(left, bg=PANEL); actions.pack(fill="x", padx=12, pady=(12, 12))
        ttk.Button(actions, text="＋ Add media", style="MPC.TButton", command=self.add_dialog).pack(fill="x")
        ttk.Button(actions, text="− Remove", style="MPC.TButton", command=self.remove_selected).pack(fill="x", pady=(5, 0))

        center = tk.Frame(body, bg=PANEL); center.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(center, background="#0D1013", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(20, 20, anchor="nw", text="MPCASU", fill=TEXT, font=("TkDefaultFont", 24, "bold"), tags="title")
        self.canvas.create_text(20, 58, anchor="nw", text="Legacy-safe playback · CASU state/provenance", fill=SECONDARY, tags="subtitle")
        self.canvas.create_text(20, 92, anchor="nw", text="Decoded activity hint — not a waveform or quality meter", fill=MUTED, tags="viz-label")
        self.canvas.bind("<Configure>", lambda _event: self._draw_visualizer())
        self.timeline = ttk.Scale(center, from_=0, to=1, variable=self.position, command=self.seek_preview, style="MPC.Horizontal.TScale")
        self.timeline.pack(fill="x", padx=14, pady=(10, 0))
        self.timeline.bind("<ButtonPress-1>", lambda _event: setattr(self, "_dragging", True))
        self.timeline.bind("<ButtonRelease-1>", lambda _event: (setattr(self, "_dragging", False), self.seek_restart()))
        bar = tk.Frame(center, bg=PANEL)
        bar.pack(fill="x", pady=8)
        for label, command in (("−10 s", lambda: self.seek_by(-10)), ("Back", lambda: self.seek_by(-10)), ("Play / Pause", self.toggle_playback), ("Stop", self.stop), ("Forward", lambda: self.seek_by(10))):
            ttk.Button(bar, text=label, style="MPC.TButton", command=command).pack(side="left", padx=3)
        ttk.Button(bar, text="Audio", style="MPC.TButton", command=lambda: self.status.set("Audio track selection is unavailable in this backend")).pack(side="right", padx=3)
        ttk.Button(bar, text="Fullscreen", style="MPC.TButton", command=lambda: self.attributes("-fullscreen", not self.attributes("-fullscreen"))).pack(side="right", padx=3)
        tk.Label(center, textvariable=self.status, bg=PANEL, fg=SECONDARY, anchor="w").pack(fill="x", padx=14, pady=(0, 8))

        right = tk.Frame(body, bg=PANEL, width=285); right.pack(side="right", fill="y", padx=(10, 0)); right.pack_propagate(False)
        tk.Label(right, text="PLAYLIST", bg=PANEL, fg=TEXT, font=("TkDefaultFont", 11, "bold"), anchor="w").pack(fill="x", padx=12, pady=(14, 8))
        self.queue = tk.Listbox(right, bg=PANEL_ALT, fg=SECONDARY, selectbackground=RED_DARK, selectforeground=TEXT, relief="flat", highlightthickness=0, activestyle="none", exportselection=False)
        self.queue.pack(fill="both", expand=True, padx=10, pady=(0, 8)); self.queue.bind("<Double-Button-1>", self._play_queue_item)
        tk.Label(right, text="QUEUE · SHUFFLE · REPEAT", bg=PANEL, fg=MUTED, font=("TkDefaultFont", 8)).pack(anchor="w", padx=12, pady=(0, 12))

        diagnostics = tk.Frame(root, bg=BG); diagnostics.pack(fill="x", padx=18, pady=(10, 4))
        for title, text in (("SEGMENTED PLAYBACK", "Segment data unavailable"), ("ENERGY SAVE", "Telemetry unavailable"), ("INTEGRITY MODE", "Checked on CASU load"), ("CASU SUPPORT", "Legacy fallback ready")):
            card = tk.Frame(diagnostics, bg=PANEL_ALT, padx=12, pady=8); card.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Label(card, text=title, bg=PANEL_ALT, fg=RED, font=("TkDefaultFont", 8, "bold")).pack(anchor="w")
            tk.Label(card, text=text, bg=PANEL_ALT, fg=SECONDARY, font=("TkDefaultFont", 9)).pack(anchor="w", pady=(3, 0))
        statusbar = tk.Frame(root, bg=BG); statusbar.pack(fill="x", padx=18, pady=(4, 10))
        tk.Label(statusbar, text="MPCASU 1.0.0  ● Ready", bg=BG, fg=SECONDARY).pack(side="left")
        tk.Label(statusbar, text="Optimized for performance and integrity", bg=BG, fg=MUTED).pack(side="left", padx=28)
        tk.Label(statusbar, text="CPU/RAM telemetry unavailable", bg=BG, fg=MUTED).pack(side="right")
        self.bind("<space>", lambda _event: self.pause())
        self.bind("<Left>", lambda _event: self.seek_by(-10))
        self.bind("<Right>", lambda _event: self.seek_by(10))
        self.bind("<Up>", lambda _event: self.status.set("Volume control is not available in this backend yet"))
        self.bind("<Down>", lambda _event: self.status.set("Volume control is not available in this backend yet"))
        self.bind("<Escape>", lambda _event: self.attributes("-fullscreen", False))
        self.after(500, self._poll)
        self.after(50, self._visual_tick)

    def _nav(self, parent, heading: str, entries: list[str]) -> None:
        tk.Label(parent, text=heading, bg=PANEL, fg=MUTED, font=("TkDefaultFont", 8, "bold"), anchor="w").pack(fill="x", padx=14, pady=(14, 5))
        for entry in entries:
            row = tk.Frame(parent, bg=PANEL, height=27); row.pack(fill="x", padx=7, pady=1); row.pack_propagate(False)
            tk.Label(row, text="◆", bg=PANEL, fg=RED if entry == "Now Playing" else MUTED, width=3, anchor="e").pack(side="left")
            tk.Label(row, text=entry, bg=PANEL, fg=TEXT if entry == "Now Playing" else SECONDARY, anchor="w").pack(side="left", padx=6)

    def _play_queue_item(self, _event=None):
        selected = self.queue.curselection()
        if selected:
            self.library.selection_clear(0, "end"); self.library.selection_set(selected[0]); self.play_selected()

    def add_dialog(self):
        paths = filedialog.askopenfilenames(filetypes=[("Media", " ".join(f"*{x}" for x in sorted(MEDIA))), ("All files", "*.*")])
        self.add_files([Path(p) for p in paths])

    def add_files(self, paths: list[Path]):
        for path in paths:
            if path.exists() and path.suffix.lower() in MEDIA and str(path) not in self.library.get(0, "end"):
                self.library.insert("end", str(path))
                self.queue.insert("end", path.name)

    def _load_visual_state(self, path: Path):
        self._visual_state = "legacy"
        self._visual_segments = []
        self._visual_video_segments = []
        self._visual_audio_segments = []
        if path.suffix.lower() != ".casu":
            return
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            errors = validate_manifest(manifest)
            if errors:
                self._visual_state = "invalid CASU: " + errors[0]
                return
            self._visual_video_segments = [segment for segment in manifest.get("video", {}).get("segments", []) if isinstance(segment, dict)]
            self._visual_audio_segments = [segment for segment in manifest.get("audio", {}).get("segments", []) if isinstance(segment, dict)]
            self._visual_segments = self._visual_video_segments + self._visual_audio_segments
            self._visual_state = "CASU state map" if self._visual_segments else "CASU empty map"
        except (OSError, ValueError, TypeError):
            self._visual_state = "invalid CASU"

    def _state_at_position(self) -> str:
        # Prefer decoded video activity for a video, otherwise use audio. The
        # old combined list made a continuously-active soundtrack mask the
        # actual picture state in the visualizer.
        segments = self._visual_video_segments or self._visual_audio_segments
        for segment in segments:
            try:
                if float(segment["start_s"]) <= self.position.get() < float(segment["end_s"]):
                    return str(segment.get("state", "unknown"))
            except (KeyError, TypeError, ValueError):
                continue
        return self._visual_state

    def _draw_visualizer(self):
        width = max(120, self.canvas.winfo_width())
        height = max(160, self.canvas.winfo_height())
        self.canvas.delete("viz")
        baseline = height - 54
        bars = 32
        gap = 4
        bar_width = max(3, (width - 40 - gap * (bars - 1)) / bars)
        state = self._state_at_position()
        for index in range(bars):
            wave = 0.5 + 0.5 * math.sin(self._visual_phase + index * 0.43)
            envelope = 0.25 + 0.75 * wave
            if state in {"static", "silence"}:
                envelope *= 0.22
            elif state in {"low_motion", "low_level"}:
                envelope *= 0.55
            elif state in {"motion", "active"}:
                envelope *= 1.0
            elif self._visual_state == "legacy":
                envelope *= 0.7
            bar_height = 12 + envelope * min(150, height * 0.34)
            x0 = 20 + index * (bar_width + gap)
            self.canvas.create_rectangle(x0, baseline - bar_height, x0 + bar_width, baseline,
                                         fill="#4aa3c7" if index % 3 else "#d3a84c",
                                         outline="", tags="viz")
        self.canvas.create_line(20, baseline, width - 20, baseline, fill="#29495a", tags="viz")
        self.canvas.create_text(20, baseline + 14, anchor="nw", text=f"{self._visual_state} · {self._state_at_position()}",
                                fill="#8ca8b8", tags="viz")

    def _visual_tick(self):
        if self.backend and self.backend.state() == PlaybackState.PLAYING and not self._paused:
            self._visual_phase += 0.16
        self._draw_visualizer()
        self.after(50, self._visual_tick)

    def remove_selected(self):
        selected = list(self.library.curselection())
        for index in reversed(selected):
            self.library.delete(index)
            if index < self.queue.size():
                self.queue.delete(index)

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
        self.now_playing.configure(text=path.name.upper())
        selected = self.library.curselection()
        if selected:
            self.queue.selection_clear(0, "end")
            self.queue.selection_set(selected[0])
            self.queue.see(selected[0])
        sidecar = path if path.suffix.lower() == ".casu" else self._sidecar(path)
        self._load_visual_state(sidecar if sidecar.exists() else path)
        try:
            source = self._source_for(path)
        except CasuError as exc:
            messagebox.showerror("MPCASU", str(exc))
            self.status.set("Cannot play — safe fallback refused an invalid CASU manifest")
            return
        state = "CASU manifest selected" if path.suffix.lower() == ".casu" else ("CASU sidecar found" if sidecar.exists() else "legacy fallback — no CASU sidecar")
        self.status.set(f"{path.name} · {state}")
        try:
            self.backend = CasuBackend(self.canvas) if path.suffix.lower() == ".casu" else LibVLCBackend(self.canvas)
            if path.suffix.lower() == ".casu": self.backend.open_casu(path)
            else: self.backend.open(source)
            self.backend.play()
            self.duration = self.backend.duration()
            self.timeline.configure(to=max(self.duration, 1.0))
        except (BackendError, CasuError, OSError) as exc:
            if self.backend: self.backend.close()
            self.backend = None
            self.status.set("Cannot play — internal media backend unavailable")
            messagebox.showerror("MPCASU", f"Could not start internal playback: {exc}")
            return
        self._paused = False

    def toggle_playback(self):
        if not self.backend:
            self.play_selected()
        else:
            self.pause()

    def _source_for(self, path: Path) -> Path:
        if path.suffix.lower() != ".casu":
            return path
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            errors = validate_manifest(manifest)
        except (OSError, ValueError, TypeError) as exc:
            raise CasuError(f"invalid CASU manifest: {path}") from exc
        if errors:
            raise CasuError(f"invalid CASU manifest: {errors[0]}")
        try:
            return resolve_casu_source(path)
        except CasuError as exc:
            raise CasuError(f"CASU source unavailable: {exc}") from exc

    def pause(self):
        if self.backend and self.backend.state() not in {PlaybackState.EMPTY, PlaybackState.STOPPED, PlaybackState.ENDED}:
            if self._paused:
                self.backend.resume()
                self._paused = False
                self.status.set("Playing — source timing is preserved")
            else:
                self._sync_position()
                self.backend.pause()
                self._paused = True
                self.status.set("Paused — source timing is preserved")

    def stop(self):
        if self.backend:
            self.backend.close()
        self.backend = None
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
        try:
            if self.backend:
                self.backend.seek(offset)
                self.backend.play()
        except (BackendError, CasuError, OSError) as exc:
            self.status.set(f"Cannot seek — internal media backend failed: {exc}")
            return
        self._paused = False

    def _sync_position(self):
        if self.backend and not self._paused:
            self.position.set(min(self.duration, self.backend.position()))

    def _poll(self):
        if self.backend and not self._dragging and not self._paused:
            self._sync_position()
        self.after(500, self._poll)


def main() -> int:
    initial = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else None
    MPCASUPlayer(initial).mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
