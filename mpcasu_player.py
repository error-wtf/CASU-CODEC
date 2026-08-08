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
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover - optional presentation enhancement
    Image = ImageTk = None

from casu.core import CasuError, resolve_casu_source, ffprobe
from casu.schema import validate_manifest
from casu.scheduler import CasuScheduler
from mpcasu_backend import BackendError, CasuBackend, LibVLCBackend, PlaybackState
from mpcasu_playback import PlaybackController


MEDIA = {".mp4", ".mp3", ".mkv", ".m4v", ".mov", ".flac", ".wav", ".ogg", ".webm", ".m4a", ".aac", ".opus", ".aiff", ".alac", ".casu"}

BG = "#090B0D"
PANEL = "#111418"
PANEL_ALT = "#14181D"
RED = "#FF1E2D"
RED_DARK = "#3A1015"
TEXT = "#F2F2F2"
SECONDARY = "#A7ABB0"
MUTED = "#686E75"


def _asset_path(name: str) -> Path:
    """Resolve bundled assets for source trees, wheels and Debian installs."""
    local = Path(__file__).resolve().parent / "assets" / name
    if local.is_file():
        return local
    for root in (Path("/usr/share/casu-codec/assets"), Path("/usr/local/share/casu-codec/assets")):
        candidate = root / name
        if candidate.is_file():
            return candidate
    return local


def presentation_mode(probe: dict) -> str:
    """Return a stream-derived presentation mode without mistaking cover art for video."""
    kinds = {
        item.get("codec_type")
        for item in probe.get("streams", [])
        if isinstance(item, dict)
        # MP3/M4A cover art is exposed by ffprobe as an attached PNG/JPEG
        # video stream, but it must not replace the audio presentation mode.
        and not (item.get("codec_type") == "video" and item.get("disposition", {}).get("attached_pic"))
    }
    if "video" in kinds:
        return "VIDEO"
    if "audio" in kinds:
        return "AUDIO"
    return "ERROR"


class MPCASUPlayer(tk.Tk):
    def __init__(self, initial: Path | list[Path] | None = None):
        super().__init__()
        self.title("MPCASU Media Player")
        self.geometry("1360x820")
        self.minsize(980, 620)
        self.configure(bg=BG)
        self.backend: LibVLCBackend | None = None
        self.controller = PlaybackController()
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
        self._scheduler = None
        self._logo_image = None
        self._icon_image = None
        self._volume = 100
        self._muted = False
        self._rate = 1.0
        self._diagnostic_vars: dict[str, tk.StringVar] = {}
        self._diagnostic_cards: list[tk.Frame] = []
        self._layout_mode = "wide"
        self._advancing = False
        self._end_handled = False
        self._session_file = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "mpcasu" / "session.json"
        self._build()
        self._restore_session()
        if initial:
            self.add_files(initial if isinstance(initial, list) else [initial])
            # A file supplied to the application is an explicit play request,
            # not merely a request to populate the queue.  Start after Tk has
            # mapped the video surface so libVLC can bind its native renderer.
            self.after_idle(self.play_selected)
        self.protocol("WM_DELETE_WINDOW", self._shutdown)

    def _build(self):
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("MPC.TButton", background=PANEL_ALT, foreground=TEXT, borderwidth=0, padding=(10, 6))
        style.map("MPC.TButton", background=[("active", RED_DARK)])
        style.configure("MPC.Horizontal.TScale", troughcolor="#24282d", background=RED)
        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True)
        top = tk.Frame(root, bg=BG, height=76); top.pack(fill="x", padx=18, pady=(10, 6)); top.pack_propagate(False)
        logo = tk.Frame(top, bg=BG); logo.pack(side="left")
        icon_path = _asset_path("mpcasu_player_icon.png")
        if icon_path.is_file() and Image is not None:
            try:
                icon = Image.open(icon_path).convert("RGBA")
                icon.thumbnail((64, 64), Image.Resampling.LANCZOS)
                self._icon_image = ImageTk.PhotoImage(icon)
                self.iconphoto(True, self._icon_image)
            except (OSError, ValueError):
                self._icon_image = None
        logo_path = _asset_path("mpcasu_player_logo_header.png")
        try:
            if logo_path.is_file():
                if Image is not None:
                    source_logo = Image.open(logo_path).convert("RGBA")
                    source_logo.thumbnail((170, 58), Image.Resampling.LANCZOS)
                    self._logo_image = ImageTk.PhotoImage(source_logo)
                else:
                    source_logo = tk.PhotoImage(file=str(logo_path))
                    factor = max(1, max(source_logo.width() // 170, source_logo.height() // 58))
                    self._logo_image = source_logo.subsample(factor, factor)
                if self._icon_image is None:
                    self.iconphoto(True, self._logo_image)
                tk.Label(logo, image=self._logo_image, bg=BG).pack(anchor="w")
            else:
                raise tk.TclError("logo asset unavailable")
        except tk.TclError:
            tk.Label(logo, text="◈ MPCASU", bg=BG, fg=RED, font=("TkDefaultFont", 19, "bold")).pack(anchor="w")
            tk.Label(logo, text="PLAYER", bg=BG, fg=SECONDARY, font=("TkDefaultFont", 8, "bold")).pack(anchor="w", padx=(30, 0))
        ttk.Button(top, text="‹", style="MPC.TButton", command=lambda: self.status.set("Navigation back is not applicable in the player view")).pack(side="left", padx=(24, 4))
        self.now_playing = tk.Label(top, text="NOW PLAYING · NO MEDIA SELECTED", bg=BG, fg=RED, font=("TkDefaultFont", 10, "bold")); self.now_playing.pack(side="left", padx=8)
        tk.Label(top, text="CASU · LEGACY SAFE", bg=BG, fg=MUTED, font=("TkDefaultFont", 9)).pack(side="right")

        body = tk.Frame(root, bg=BG); body.pack(fill="both", expand=True, padx=18)
        left_shell = tk.Frame(body, bg=PANEL, width=220); left_shell.pack(side="left", fill="y", padx=(0, 10)); left_shell.pack_propagate(False)
        self.left_shell = left_shell
        left_canvas = tk.Canvas(left_shell, bg=PANEL, highlightthickness=0, borderwidth=0)
        left_scroll = ttk.Scrollbar(left_shell, orient="vertical", command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_canvas.pack(side="left", fill="both", expand=True)
        left_scroll.pack(side="right", fill="y")
        left = tk.Frame(left_canvas, bg=PANEL)
        left_window = left_canvas.create_window((0, 0), window=left, anchor="nw")
        left.bind("<Configure>", lambda _event: left_canvas.configure(scrollregion=left_canvas.bbox("all")))
        left_canvas.bind("<Configure>", lambda event: left_canvas.itemconfigure(left_window, width=event.width))
        left_canvas.bind_all("<MouseWheel>", lambda event: left_canvas.yview_scroll(-int(event.delta / 120), "units"))
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
        ttk.Button(actions, text="↗ Open URL", style="MPC.TButton", command=self.open_url_dialog).pack(fill="x", pady=(5, 0))
        ttk.Button(actions, text="− Remove", style="MPC.TButton", command=self.remove_selected).pack(fill="x", pady=(5, 0))
        ttk.Button(actions, text="▣ Save playlist", style="MPC.TButton", command=self.save_playlist).pack(fill="x", pady=(5, 0))
        ttk.Button(actions, text="□ Load playlist", style="MPC.TButton", command=self.load_playlist).pack(fill="x", pady=(5, 0))

        # A real compact navigation rail keeps navigation available when the
        # full sidebar would steal too much video width.  It is deliberately
        # icon-only and uses the same actions as the expanded navigation.
        compact_nav = tk.Frame(body, bg=PANEL, width=54)
        compact_nav.pack_propagate(False)
        for symbol, name in (("▶", "Now Playing"), ("▦", "Library"), ("◆", "CASU Files"), ("♫", "Music"), ("☷", "Playlists")):
            ttk.Button(
                compact_nav, text=symbol, width=3, style="MPC.TButton",
                command=lambda label=name: self.status.set(f"{label}: compact navigation"),
            ).pack(fill="x", padx=7, pady=5)
        self.compact_nav = compact_nav

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
        for label, command in (("Previous", self.play_previous), ("−10 s", lambda: self.seek_by(-10)), ("Play / Pause", self.toggle_playback), ("Stop", self.stop), ("+10 s", lambda: self.seek_by(10)), ("Next", self.play_next)):
            ttk.Button(bar, text=label, style="MPC.TButton", command=command).pack(side="left", padx=3)
        ttk.Button(bar, text="Mute", style="MPC.TButton", command=self.toggle_mute).pack(side="right", padx=3)
        ttk.Button(bar, text="1×", style="MPC.TButton", command=self.cycle_rate).pack(side="right", padx=3)
        ttk.Button(bar, text="Audio", style="MPC.TButton", command=self.cycle_audio_track).pack(side="right", padx=3)
        ttk.Button(bar, text="Subtitles", style="MPC.TButton", command=self.cycle_subtitle_track).pack(side="right", padx=3)
        ttk.Button(bar, text="Info", style="MPC.TButton", command=self.show_media_info).pack(side="right", padx=3)
        ttk.Button(bar, text="Fullscreen", style="MPC.TButton", command=lambda: self.attributes("-fullscreen", not self.attributes("-fullscreen"))).pack(side="right", padx=3)
        tk.Label(center, textvariable=self.status, bg=PANEL, fg=SECONDARY, anchor="w").pack(fill="x", padx=14, pady=(0, 8))

        right = tk.Frame(body, bg=PANEL, width=285); right.pack(side="right", fill="y", padx=(10, 0)); right.pack_propagate(False)
        self.right_shell = right
        playlist_header = tk.Frame(right, bg=PANEL); playlist_header.pack(fill="x", padx=12, pady=(14, 8))
        tk.Label(playlist_header, text="PLAYLIST", bg=PANEL, fg=TEXT, font=("TkDefaultFont", 11, "bold"), anchor="w").pack(anchor="w")
        tk.Label(playlist_header, text="Queue · source metadata", bg=PANEL, fg=MUTED, font=("TkDefaultFont", 8), anchor="w").pack(anchor="w", pady=(2, 0))
        self.queue = tk.Listbox(right, bg=PANEL_ALT, fg=SECONDARY, selectbackground=RED_DARK, selectforeground=TEXT, relief="flat", highlightthickness=0, activestyle="none", exportselection=False)
        self.queue.pack(fill="both", expand=True, padx=10, pady=(0, 8)); self.queue.bind("<Double-Button-1>", self._play_queue_item)
        self.queue_empty_label = tk.Label(
            right, text="No media queued\nAdd files or drop a playlist here",
            bg=PANEL, fg=MUTED, justify="center", font=("TkDefaultFont", 9),
        )
        self.queue_empty_label.pack(fill="x", padx=12, pady=(0, 10))
        tk.Label(right, text="QUEUE · SHUFFLE · REPEAT", bg=PANEL, fg=MUTED, font=("TkDefaultFont", 8)).pack(anchor="w", padx=12, pady=(0, 12))

        diagnostics = tk.Frame(root, bg=BG); diagnostics.pack(fill="x", padx=18, pady=(10, 4))
        self.diagnostics = diagnostics
        for title, text in (("SEGMENTED PLAYBACK", "unavailable"), ("ENERGY SAVE", "unavailable"), ("INTEGRITY MODE", "unavailable"), ("CASU SUPPORT", "Legacy backend")):
            card = tk.Frame(diagnostics, bg=PANEL_ALT, padx=12, pady=8); card.pack(side="left", fill="x", expand=True, padx=(0, 8))
            self._diagnostic_cards.append(card)
            tk.Label(card, text=title, bg=PANEL_ALT, fg=RED, font=("TkDefaultFont", 8, "bold")).pack(anchor="w")
            variable = tk.StringVar(value=text)
            self._diagnostic_vars[title] = variable
            tk.Label(card, textvariable=variable, bg=PANEL_ALT, fg=SECONDARY, font=("TkDefaultFont", 9)).pack(anchor="w", pady=(3, 0))
        statusbar = tk.Frame(root, bg=BG); statusbar.pack(fill="x", padx=18, pady=(4, 10))
        self.statusbar = statusbar
        tk.Label(statusbar, text="MPCASU 1.0.0  ● Ready", bg=BG, fg=SECONDARY).pack(side="left")
        tk.Label(statusbar, text="Optimized for performance and integrity", bg=BG, fg=MUTED).pack(side="left", padx=28)
        tk.Label(statusbar, text="CPU/RAM telemetry unavailable", bg=BG, fg=MUTED).pack(side="right")
        self.bind("<space>", lambda _event: self.pause())
        self.bind("<Control-o>", lambda _event: self.add_dialog())
        self.bind("<Control-l>", lambda _event: self.open_url_dialog())
        self.bind("<Control-i>", lambda _event: self.show_media_info())
        self.bind("<Left>", lambda _event: self.seek_by(-10))
        self.bind("<Right>", lambda _event: self.seek_by(10))
        self.bind("<Up>", lambda _event: self.change_volume(5))
        self.bind("<Down>", lambda _event: self.change_volume(-5))
        self.bind("f", lambda _event: self.toggle_fullscreen())
        self.bind("F", lambda _event: self.toggle_fullscreen())
        self.bind("m", lambda _event: self.toggle_mute())
        self.bind("M", lambda _event: self.toggle_mute())
        self.bind("s", lambda _event: self.stop())
        self.bind("S", lambda _event: self.stop())
        self.bind("<Escape>", lambda _event: self.attributes("-fullscreen", False))
        self.canvas.bind("<Double-Button-1>", lambda _event: self.toggle_fullscreen())
        self.bind("<Configure>", self._responsive_layout)
        self.after(500, self._poll)
        self.after(50, self._visual_tick)

    def _nav(self, parent, heading: str, entries: list[str]) -> None:
        tk.Label(parent, text=heading, bg=PANEL, fg=MUTED, font=("TkDefaultFont", 8, "bold"), anchor="w").pack(fill="x", padx=14, pady=(14, 5))
        for entry in entries:
            row = tk.Frame(parent, bg=PANEL, height=27); row.pack(fill="x", padx=7, pady=1); row.pack_propagate(False)
            label = tk.Label(row, text="◆", bg=PANEL, fg=RED if entry == "Now Playing" else MUTED, width=3, anchor="e")
            label.pack(side="left")
            text_label = tk.Label(row, text=entry, bg=PANEL, fg=TEXT if entry == "Now Playing" else SECONDARY, anchor="w")
            text_label.pack(side="left", padx=6)
            for widget in (row, label, text_label):
                widget.bind("<Button-1>", lambda _event, name=entry: self.status.set(f"{name}: view not available in this release"))

    def _responsive_layout(self, event=None):
        """Keep the video viewport usable instead of clipping side panels."""
        width = int(getattr(event, "width", self.winfo_width()))
        height = int(getattr(event, "height", self.winfo_height()))
        if width >= 1280:
            mode = "wide"
        elif width >= 1080:
            mode = "medium"
        else:
            mode = "compact"
        if mode != self._layout_mode:
            self._layout_mode = mode
            if mode == "wide":
                if self.compact_nav.winfo_ismapped():
                    self.compact_nav.pack_forget()
                if not self.right_shell.winfo_ismapped():
                    self.right_shell.pack(side="right", fill="y", padx=(10, 0))
                if not self.left_shell.winfo_ismapped():
                    self.left_shell.pack(side="left", fill="y", padx=(0, 10), before=self.canvas.master)
            elif mode == "medium":
                if self.compact_nav.winfo_ismapped():
                    self.compact_nav.pack_forget()
                if self.right_shell.winfo_ismapped():
                    self.right_shell.pack_forget()
                if not self.left_shell.winfo_ismapped():
                    self.left_shell.pack(side="left", fill="y", padx=(0, 10), before=self.canvas.master)
            else:
                if self.right_shell.winfo_ismapped():
                    self.right_shell.pack_forget()
                if self.left_shell.winfo_ismapped():
                    self.left_shell.pack_forget()
                if not self.compact_nav.winfo_ismapped():
                    self.compact_nav.pack(side="left", fill="y", padx=(0, 8), before=self.canvas.master)
        # At low heights the diagnostics row is collapsed rather than clipped.
        if height < 700:
            if self.diagnostics.winfo_ismapped():
                self.diagnostics.pack_forget()
        elif not self.diagnostics.winfo_ismapped():
            self.diagnostics.pack(fill="x", padx=18, pady=(10, 4), before=self.statusbar)

    def _set_diagnostics(self, *, support: str | None = None, integrity: str | None = None,
                         segmented: str | None = None, energy: str | None = None) -> None:
        values = {
            "CASU SUPPORT": support,
            "INTEGRITY MODE": integrity,
            "SEGMENTED PLAYBACK": segmented,
            "ENERGY SAVE": energy,
        }
        for key, value in values.items():
            if value is not None and key in self._diagnostic_vars:
                self._diagnostic_vars[key].set(value)

    def _play_queue_item(self, _event=None):
        selected = self.queue.curselection()
        if selected:
            self.library.selection_clear(0, "end"); self.library.selection_set(selected[0]); self.play_selected()

    def play_next(self):
        """Advance to the next queued media item."""
        selected = self.library.curselection()
        index = selected[0] if selected else -1
        if index + 1 >= self.library.size():
            self.status.set("End of playlist")
            return
        self.library.selection_clear(0, "end")
        self.library.selection_set(index + 1)
        self.library.see(index + 1)
        self.play_selected()

    def play_previous(self):
        """Return to the previous queued media item."""
        selected = self.library.curselection()
        index = selected[0] if selected else 0
        if index <= 0:
            self.status.set("Beginning of playlist")
            return
        self.library.selection_clear(0, "end")
        self.library.selection_set(index - 1)
        self.library.see(index - 1)
        self.play_selected()

    def add_dialog(self):
        paths = filedialog.askopenfilenames(filetypes=[("Media and streams", "*"), ("Known media", " ".join(f"*{x}" for x in sorted(MEDIA))), ("All files", "*.*")])
        self.add_files([Path(p) for p in paths])

    def open_url_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Open network URL")
        dialog.configure(bg=BG)
        dialog.transient(self)
        tk.Label(dialog, text="HTTP(S), HLS, RTSP, RTP, UDP, FTP or SMB URL", bg=BG, fg=SECONDARY).pack(anchor="w", padx=16, pady=(16, 6))
        value = tk.StringVar()
        entry = ttk.Entry(dialog, textvariable=value, width=64)
        entry.pack(fill="x", padx=16); entry.focus_set()
        def open_source():
            url = value.get().strip()
            if url:
                self._open_external_source(url)
                dialog.destroy()
        ttk.Button(dialog, text="Open", style="MPC.TButton", command=open_source).pack(anchor="e", padx=16, pady=14)
        entry.bind("<Return>", lambda _event: open_source())

    def _open_external_source(self, source: str):
        self.stop()
        self._end_handled = False
        self.current = None
        self.now_playing.configure(text=source)
        try:
            self.backend = LibVLCBackend(self.canvas)
            self.backend.open_source(source)
            self.controller.attach(self.backend, source)
            self.controller.play()
            self._rate = self.backend.set_rate(self._rate)
            self._set_diagnostics(support="Legacy network backend", integrity="unavailable", segmented="unavailable", energy="unavailable — not measured")
            self.duration = self.backend.duration()
            self.timeline.configure(to=max(self.duration, 1.0))
            capabilities = self.backend.capabilities()
            self.status.set(f"Playing network source · {capabilities.get('version', 'libVLC')} · timing owned by libVLC")
        except (BackendError, OSError) as exc:
            self.controller.close()
            self.backend = None
            self.status.set(f"Could not open network source: {exc}")
            messagebox.showerror("MPCASU", str(exc))

    def add_files(self, paths: list[Path]):
        for path in paths:
            if path.exists() and str(path) not in self.library.get(0, "end"):
                self.library.insert("end", str(path))
                self.queue.insert("end", path.name)
        self._sync_queue_empty()

    def _sync_queue_empty(self):
        """Keep the playlist panel informative instead of showing dead empty space."""
        if self.queue.size():
            if self.queue_empty_label.winfo_ismapped():
                self.queue_empty_label.pack_forget()
        elif not self.queue_empty_label.winfo_ismapped():
            self.queue_empty_label.pack(fill="x", padx=12, pady=(0, 10), before=self.queue.master.winfo_children()[-1])

    def _restore_session(self):
        try:
            payload = json.loads(self._session_file.read_text(encoding="utf-8"))
            self.add_files([Path(value) for value in payload.get("playlist", []) if Path(value).is_file()])
            self._volume = max(0, min(200, int(payload.get("volume", self._volume))))
            self._muted = bool(payload.get("muted", False))
            self._rate = max(0.25, min(4.0, float(payload.get("rate", 1.0))))
            geometry = payload.get("geometry")
            if isinstance(geometry, str) and geometry:
                self.geometry(geometry)
        except (OSError, ValueError, TypeError):
            pass

    def _shutdown(self):
        try:
            self._session_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._session_file.with_suffix(".tmp")
            temporary.write_text(json.dumps({
                "playlist": list(self.library.get(0, "end")),
                "volume": self._volume,
                "muted": self._muted,
                "rate": self._rate,
                "geometry": self.geometry(),
            }, indent=2) + "\n", encoding="utf-8")
            temporary.replace(self._session_file)
        except OSError:
            pass
        self.controller.close()
        self.backend = None
        self.destroy()

    def _load_visual_state(self, path: Path):
        self._visual_state = "legacy"
        self._visual_segments = []
        self._visual_video_segments = []
        self._visual_audio_segments = []
        self._scheduler = None
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
            self._scheduler = CasuScheduler.from_manifest(manifest, "video" if self._visual_video_segments else "audio")
            self._visual_state = "CASU state map" if self._visual_segments else "CASU empty map"
        except (OSError, ValueError, TypeError):
            self._visual_state = "invalid CASU"

    def _state_at_position(self) -> str:
        # Prefer decoded video activity for a video, otherwise use audio. The
        # old combined list made a continuously-active soundtrack mask the
        # actual picture state in the visualizer.
        if self._scheduler is not None:
            active = self._scheduler.state_at(self.position.get())
            if active is not None:
                return active.state
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
        # The canvas is the libVLC video surface during playback. Never paint
        # an invented waveform over a real video (or pretend that a timer is
        # an audio signal). A future PCM-backed audio visualizer must provide
        # measured samples before it is enabled.
        if self.backend and self.backend.state() in {
            PlaybackState.LOADING, PlaybackState.READY, PlaybackState.PLAYING,
            PlaybackState.PAUSED,
        }:
            return
        baseline = height - 54
        state = self._state_at_position()
        label = "Measured audio visualization unavailable"
        if self._visual_state.startswith("CASU"):
            label = f"CASU state map · {state}"
        self.canvas.create_text(width // 2, height // 2, anchor="center", text=label,
                                fill=MUTED, font=("TkDefaultFont", 11), tags="viz")

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
        self._sync_queue_empty()

    def save_playlist(self):
        target = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("MPCASU playlist", "*.json"), ("All files", "*.*")])
        if not target:
            return
        try:
            Path(target).write_text(json.dumps({"version": 1, "items": list(self.library.get(0, "end"))}, indent=2) + "\n", encoding="utf-8")
            self.status.set(f"Playlist saved · {Path(target).name}")
        except OSError as exc:
            messagebox.showerror("MPCASU", f"Could not save playlist: {exc}")

    def load_playlist(self):
        source = filedialog.askopenfilename(filetypes=[("MPCASU playlist", "*.json"), ("All files", "*.*")])
        if not source:
            return
        try:
            payload = json.loads(Path(source).read_text(encoding="utf-8"))
            items = payload.get("items", [])
            if not isinstance(items, list):
                raise ValueError("items must be an array")
            self.add_files([Path(item) for item in items if isinstance(item, str)])
            self.status.set(f"Playlist loaded · {Path(source).name}")
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror("MPCASU", f"Could not load playlist: {exc}")

    def show_media_info(self):
        path = self.current or self.selected_path()
        if not path or not path.is_file():
            self.status.set("No local media selected for information")
            return
        try:
            source = self._source_for(path)
            probe = ffprobe(source)
            lines = [f"File: {path.name}", f"Source: {source.name}",
                     f"Container: {probe.get('format', {}).get('format_name', 'unknown')}",
                     f"Duration: {probe.get('format', {}).get('duration', 'unknown')} s",
                     f"Size: {probe.get('format', {}).get('size', 'unknown')} bytes"]
            if path.suffix.lower() == ".casu":
                lines.extend(["CASU: validated manifest", f"Segment hints: {len(self._visual_segments)}"])
            for index, stream in enumerate(probe.get("streams", [])):
                details = [f"stream {index}: {stream.get('codec_type', 'unknown')}", str(stream.get('codec_name', 'unknown'))]
                if stream.get("tags", {}).get("language"):
                    details.append(f"language={stream['tags']['language']}")
                if stream.get("width") and stream.get("height"): details.append(f"{stream['width']}×{stream['height']}")
                if stream.get("sample_rate"): details.append(f"{stream['sample_rate']} Hz")
                if stream.get("channels"): details.append(f"{stream['channels']} channels")
                if stream.get("avg_frame_rate") and stream.get("avg_frame_rate") != "0/0": details.append(f"fps={stream['avg_frame_rate']}")
                lines.append(" · ".join(details))
            dialog = tk.Toplevel(self); dialog.title("Media information"); dialog.configure(bg=BG); dialog.transient(self)
            text = tk.Text(dialog, width=76, height=max(8, len(lines) + 2), bg=PANEL_ALT, fg=TEXT, relief="flat", wrap="word")
            text.insert("1.0", "\n".join(lines)); text.configure(state="disabled"); text.pack(padx=16, pady=16)
        except (CasuError, OSError, ValueError) as exc:
            messagebox.showerror("MPCASU", f"Media information unavailable: {exc}")

    def selected_path(self) -> Path | None:
        selected = self.library.curselection()
        if not selected:
            if self.current:
                return self.current
            # Opening a file from the command line or file manager populates
            # the queue without creating a Listbox selection.  The first queue
            # item is the deterministic playback target in that case.
            if self.library.size():
                return Path(self.library.get(0))
            return None
        return Path(self.library.get(selected[0]))

    def _sidecar(self, path: Path) -> Path:
        return path.with_suffix(path.suffix + ".casu")

    def play_selected(self):
        path = self.selected_path()
        if not path:
            messagebox.showinfo("MPCASU", "Add a media file first.")
            return
        self.stop()
        self._end_handled = False
        self.current = path
        self.now_playing.configure(text=path.name.upper())
        selected = self.library.curselection()
        if selected:
            self.queue.selection_clear(0, "end")
            self.queue.selection_set(selected[0])
            self.queue.see(selected[0])
        sidecar = path if path.suffix.lower() == ".casu" else self._sidecar(path)
        self._load_visual_state(sidecar if sidecar.exists() else path)
        if path.suffix.lower() == ".casu":
            self._set_diagnostics(
                # The current .casu format is a validated sidecar compatibility
                # manifest. Do not present it as a native decoded CASU payload.
                support="CASU sidecar + legacy backend",
                integrity="verified source manifest" if not self._visual_state.startswith("invalid") else "failed manifest validation",
                segmented=f"{len(self._visual_segments)} segments" if self._visual_segments else "no segment data",
            )
        elif sidecar.exists():
            self._set_diagnostics(support="Legacy + CASU sidecar", integrity="sidecar available; source checked on load", segmented=f"{len(self._visual_segments)} segments" if self._visual_segments else "no segment data")
        else:
            self._set_diagnostics(support="Legacy backend", integrity="unavailable", segmented="unavailable")
        self._set_diagnostics(energy="unavailable — not measured")
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
            self.controller.attach(self.backend, path)
            self.controller.play()
            self._rate = self.backend.set_rate(self._rate)
            self.duration = self.backend.duration()
            self.timeline.configure(to=max(self.duration, 1.0))
            capabilities = self.backend.capabilities()
            self.status.set(f"{path.name} · {state} · {capabilities.get('version', 'libVLC')}")
            # libVLC can accept a media object while a decoder later fails.
            # Check local playback after its asynchronous pipeline had time to
            # announce streams; never leave the UI claiming PLAYING forever
            # when no timed media was produced.
            self.after(1500, self._check_playback_start)
        except (BackendError, CasuError, OSError) as exc:
            self.controller.close()
            self.backend = None
            self.status.set("Cannot play — internal media backend unavailable")
            messagebox.showerror("MPCASU", f"Could not start internal playback: {exc}")
            return
        self._paused = False
        self._update_presentation(path)

    def _check_playback_start(self):
        if not self.backend or not self.current or self._paused:
            return
        if self.current.as_uri().startswith(("http:", "https:", "rtsp:")):
            return
        if self.backend.state() == PlaybackState.PLAYING and not self.backend.is_actively_playing():
            self.status.set("Playback unavailable — libVLC did not enter active playback")
            self._set_diagnostics(support="backend opened; decoder or output unavailable")

    def _update_presentation(self, path: Path):
        """Choose a presentation mode from probed streams, not file suffixes."""
        try:
            # A CASU sidecar is metadata; stream presentation comes from the
            # immutable source it references, never from the JSON manifest.
            source = self._source_for(path)
            probe = ffprobe(source)
            streams = probe.get("streams", [])
            kinds = {item.get("codec_type") for item in streams}
            mode = presentation_mode(probe)
            if mode == "VIDEO":
                self.canvas.itemconfigure("title", text=path.name)
                audio_note = " + audio" if "audio" in kinds else ""
                self.canvas.itemconfigure("subtitle", text=f"Video stream{audio_note} · original timestamps preserved")
            elif mode == "AUDIO":
                self.canvas.itemconfigure("title", text="AUDIO MODE")
                self.canvas.itemconfigure("subtitle", text="Audio stream · visualization unavailable until PCM analysis is enabled")
            else:
                self.canvas.itemconfigure("title", text="UNSUPPORTED PRESENTATION")
                self.canvas.itemconfigure("subtitle", text="No video or audio stream was reported by the probe")
        except (CasuError, OSError, ValueError):
            self.status.set("Stream presentation metadata unavailable")

    def toggle_playback(self):
        if not self.backend:
            self.play_selected()
        else:
            self.pause()

    def change_volume(self, delta: int):
        self._volume = max(0, min(200, self._volume + delta))
        if self.backend:
            try: self._volume = self.backend.set_volume(self._volume)
            except BackendError as exc: self.status.set(str(exc)); return
        self.status.set(f"Volume {self._volume}%")

    def toggle_mute(self):
        self._muted = not self._muted
        if self.backend:
            try: self.backend.set_mute(self._muted)
            except BackendError as exc: self.status.set(str(exc)); return
        self.status.set("Muted" if self._muted else f"Volume {self._volume}%")

    def cycle_rate(self):
        """Apply a real libVLC playback rate; never fake a speed label."""
        rates = (0.5, 1.0, 1.25, 1.5, 2.0)
        next_rate = rates[(rates.index(self._rate) + 1) % len(rates)] if self._rate in rates else 1.0
        if not self.backend:
            self._rate = next_rate
            self.status.set(f"Playback rate {self._rate:g}× (applies on next media)")
            return
        try:
            self._rate = self.backend.set_rate(next_rate)
            self.status.set(f"Playback rate {self._rate:g}×")
        except BackendError as exc:
            self.status.set(f"Playback rate unavailable: {exc}")

    def cycle_audio_track(self):
        if not self.backend:
            self.status.set("No active media backend")
            return
        try:
            count = self.backend.audio_track_count()
            if count <= 0:
                self.status.set("No selectable audio tracks reported by libVLC")
                return
            current = self.backend.audio_track()
            next_track = (current + 1) % count
            self.backend.set_audio_track(next_track)
            labels = self.backend.audio_track_descriptions()
            label = next((name for identifier, name in labels if identifier == next_track), f"Track {next_track + 1}")
            self.status.set(f"Audio: {label} ({next_track + 1}/{count})")
        except BackendError as exc:
            self.status.set(str(exc))

    def cycle_subtitle_track(self):
        if not self.backend:
            self.status.set("No active media backend")
            return
        try:
            count = self.backend.subtitle_track_count()
            if count <= 0:
                self.status.set("No selectable subtitle tracks reported by libVLC")
                return
            current = self.backend.subtitle_track()
            next_track = (current + 1) % count
            self.backend.set_subtitle_track(next_track)
            labels = self.backend.subtitle_track_descriptions()
            label = next((name for identifier, name in labels if identifier == next_track), f"Track {next_track + 1}")
            self.status.set(f"Subtitle: {label} ({next_track + 1}/{count})")
        except BackendError as exc:
            self.status.set(str(exc))

    def toggle_fullscreen(self):
        self.attributes("-fullscreen", not bool(self.attributes("-fullscreen")))

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
                self.controller.pause_or_resume()
                self._paused = False
                self.status.set("Playing — source timing is preserved")
            else:
                self._sync_position()
                self.controller.pause_or_resume()
                self._paused = True
                self.status.set("Paused — source timing is preserved")

    def stop(self):
        if self.backend:
            self.controller.stop()
            self.controller.close()
        self.backend = None
        self._paused = False
        self._set_diagnostics(support="Legacy backend", integrity="unavailable", segmented="unavailable", energy="unavailable — not measured")

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
                self.controller.seek(offset)
                self.controller.play()
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
            if self.backend.state() == PlaybackState.ENDED and not self._advancing and not self._end_handled:
                self._end_handled = True
                self._advancing = True
                try:
                    self.play_next()
                finally:
                    self._advancing = False
        self.after(500, self._poll)


def main() -> int:
    initial = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else None
    MPCASUPlayer(initial).mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
