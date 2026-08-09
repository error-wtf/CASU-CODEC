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
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover - optional presentation enhancement
    Image = ImageTk = None

from casu.core import CasuError, resolve_casu_source, ffprobe
from casu.schema import validate_manifest
from casu.scheduler import CasuScheduler
from casu.library import MediaLibrary, PlaybackPreferences
from casu.media import TrackKind
from casu.playlist import PlaylistError, PlaylistModel
from casu.settings import PlayerSettings, SettingsStore
from casu.thumbnail import thumbnail_for
from mpcasu_backend import BackendError, CasuBackend, LibVLCBackend, PlaybackState
from casu.native import NativeCasuError, read_native
from casu.native_v2 import ChunkType, NativeV2Error, read_native_v2
from mpcasu_native_backend import NativeCasuBackend, PulseAudioSink, TkCanvasVideoSink
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


def chapter_marker_positions(chapters, duration: float, width: int):
    """Return bounded pixel positions for backend-neutral chapter descriptors."""
    duration, width = float(duration), int(width)
    if not math.isfinite(duration) or duration <= 0 or width <= 0:
        return ()
    markers = []
    for chapter in chapters:
        start = float(chapter.start_seconds)
        if not math.isfinite(start):
            continue
        start = max(0.0, min(duration, start))
        markers.append((int(chapter.identifier), start / duration * width,
                        str(chapter.title), start))
    return tuple(markers)


class MPCASUPlayer(tk.Tk):
    def __init__(self, initial: Path | list[Path] | None = None):
        super().__init__()
        self.title("MPCASU Media Player")
        self.geometry("1360x820")
        self.minsize(980, 620)
        self.configure(bg=BG)
        self.backend: LibVLCBackend | NativeCasuBackend | None = None
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
        self._audio_delay_ms = 0.0
        self._subtitle_delay_ms = 0.0
        self._resume_source: str | None = None
        self._resume_position = 0.0
        self._diagnostic_vars: dict[str, tk.StringVar] = {}
        self._diagnostic_cards: list[tk.Frame] = []
        self._layout_mode = "wide"
        self._advancing = False
        self._end_handled = False
        self.playlist_model = PlaylistModel()
        self._session_file = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "mpcasu" / "session.json"
        self.settings_store = SettingsStore(self._session_file.parent / "settings.json")
        effective_settings = self.settings_store.load()
        self._volume = effective_settings.volume
        self._muted = effective_settings.muted
        self._rate = effective_settings.rate
        self._audio_device = effective_settings.audio_device
        self._watched_folders = list(effective_settings.watched_folders)
        self.media_library = MediaLibrary(self._session_file.parent / "library.sqlite3")
        self._thumbnail_directory = self._session_file.parent / "thumbnails"
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
        self._nav(left, "LIBRARY", ["Now Playing", "Library", "CASU Files", "Video", "Music", "Playlists"])
        self._nav(left, "SOURCES", ["Local Files", "Network Stream"])
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
        ttk.Button(actions, text="⌕ Search library", style="MPC.TButton", command=self.show_library_dialog).pack(fill="x", pady=(5, 0))
        ttk.Button(actions, text="＋ Watch folder", style="MPC.TButton", command=self.add_watched_folder).pack(fill="x", pady=(5, 0))

        # A real compact navigation rail keeps navigation available when the
        # full sidebar would steal too much video width.  It is deliberately
        # icon-only and uses the same actions as the expanded navigation.
        compact_nav = tk.Frame(body, bg=PANEL, width=54)
        compact_nav.pack_propagate(False)
        for symbol, name in (("▶", "Now Playing"), ("▦", "Library"), ("◆", "CASU Files"), ("♫", "Music"), ("☷", "Playlists")):
            ttk.Button(
                compact_nav, text=symbol, width=3, style="MPC.TButton",
                command=lambda label=name: self._navigate(label),
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
        self.chapter_timeline = tk.Canvas(center, height=15, background=PANEL,
                                          highlightthickness=0)
        self.chapter_timeline.pack(fill="x", padx=14)
        self.chapter_timeline.bind("<Configure>", lambda _event: self._draw_chapter_markers())
        bar = tk.Frame(center, bg=PANEL)
        bar.pack(fill="x", pady=8)
        for label, command in (("Previous", self.play_previous), ("−10 s", lambda: self.seek_by(-10)), ("Play / Pause", self.toggle_playback), ("Stop", self.stop), ("+10 s", lambda: self.seek_by(10)), ("Next", self.play_next)):
            ttk.Button(bar, text=label, style="MPC.TButton", command=command).pack(side="left", padx=3)
        ttk.Button(bar, text="Mute", style="MPC.TButton", command=self.toggle_mute).pack(side="right", padx=3)
        self.rate_button = ttk.Button(bar, text=f"{self._rate:g}×",
                                      style="MPC.TButton", command=self.cycle_rate)
        self.rate_button.pack(side="right", padx=3)
        self._track_menus = {}
        self._track_vars = {}
        self._make_track_menu(bar, "Audio", TrackKind.AUDIO)
        self._make_track_menu(bar, "Video", TrackKind.VIDEO)
        self._make_track_menu(bar, "Subtitles", TrackKind.SUBTITLE)
        self._make_audio_device_menu(bar)
        self._make_chapter_menu(bar)
        self._make_sync_menu(bar)
        ttk.Button(bar, text="Load subtitle", style="MPC.TButton", command=self.load_external_subtitle).pack(side="right", padx=3)
        ttk.Button(bar, text="Frame", style="MPC.TButton", command=self.next_frame).pack(side="right", padx=3)
        ttk.Button(bar, text="Info", style="MPC.TButton", command=self.show_media_info).pack(side="right", padx=3)
        ttk.Button(bar, text="Fullscreen", style="MPC.TButton", command=self.toggle_fullscreen).pack(side="right", padx=3)
        tk.Label(center, textvariable=self.status, bg=PANEL, fg=SECONDARY, anchor="w").pack(fill="x", padx=14, pady=(0, 8))

        right = tk.Frame(body, bg=PANEL, width=285); right.pack(side="right", fill="y", padx=(10, 0)); right.pack_propagate(False)
        self.right_shell = right
        playlist_header = tk.Frame(right, bg=PANEL); playlist_header.pack(fill="x", padx=12, pady=(14, 8))
        tk.Label(playlist_header, text="PLAYLIST", bg=PANEL, fg=TEXT, font=("TkDefaultFont", 11, "bold"), anchor="w").pack(anchor="w")
        tk.Label(playlist_header, text="Queue · source metadata", bg=PANEL, fg=MUTED, font=("TkDefaultFont", 8), anchor="w").pack(anchor="w", pady=(2, 0))
        self.queue = tk.Listbox(right, bg=PANEL_ALT, fg=SECONDARY, selectbackground=RED_DARK, selectforeground=TEXT, relief="flat", highlightthickness=0, activestyle="none", exportselection=False)
        self.queue.pack(fill="both", expand=True, padx=10, pady=(0, 8)); self.queue.bind("<Double-Button-1>", self._play_queue_item)
        queue_actions = tk.Frame(right, bg=PANEL)
        queue_actions.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Button(queue_actions, text="↑", width=3, style="MPC.TButton", command=lambda: self.move_queue(-1)).pack(side="left")
        ttk.Button(queue_actions, text="↓", width=3, style="MPC.TButton", command=lambda: self.move_queue(1)).pack(side="left", padx=4)
        ttk.Button(queue_actions, text="Clear", style="MPC.TButton", command=self.clear_playlist).pack(side="right")
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
        tk.Label(statusbar, text="MPCASU 1.0.0rc8  ● Pre-release", bg=BG, fg=SECONDARY).pack(side="left")
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

    def _menu_button(self, parent, text: str) -> tuple[tk.Menubutton, tk.Menu]:
        button = tk.Menubutton(parent, text=text, bg=PANEL_ALT, fg=TEXT,
                               activebackground=RED_DARK, activeforeground=TEXT,
                               relief="flat", padx=8, pady=5, highlightthickness=0)
        menu = tk.Menu(button, tearoff=False, bg=PANEL_ALT, fg=TEXT,
                       activebackground=RED_DARK, activeforeground=TEXT)
        button.configure(menu=menu); button.pack(side="right", padx=3)
        return button, menu

    def _make_track_menu(self, parent, label: str, kind: TrackKind) -> None:
        button, menu = self._menu_button(parent, label)
        variable = tk.IntVar(value=-1)
        menu.configure(postcommand=lambda kind=kind: self._refresh_track_menu(kind))
        self._track_menus[kind] = menu
        self._track_vars[kind] = variable

    def _refresh_track_menu(self, kind: TrackKind) -> None:
        menu = self._track_menus[kind]; menu.delete(0, "end")
        if not self.backend:
            menu.add_command(label="No active media", state="disabled"); return
        descriptors = self.backend.track_descriptors(kind)
        current = {TrackKind.AUDIO: self.backend.audio_track,
                   TrackKind.VIDEO: self.backend.video_track,
                   TrackKind.SUBTITLE: self.backend.subtitle_track}[kind]()
        self._track_vars[kind].set(current)
        if kind is TrackKind.SUBTITLE:
            menu.add_radiobutton(label="Off", variable=self._track_vars[kind], value=-1,
                                 command=lambda: self._select_track(kind, -1))
        if not descriptors:
            menu.add_command(label="No tracks reported", state="disabled")
        for item in descriptors:
            details = [item.label]
            if item.language and item.language not in item.label:
                details.append(item.language)
            if item.codec and item.codec not in item.label:
                details.append(item.codec)
            menu.add_radiobutton(label=" · ".join(details), variable=self._track_vars[kind],
                                 value=item.identifier,
                                 command=lambda value=item.identifier, kind=kind:
                                 self._select_track(kind, value))

    def _select_track(self, kind: TrackKind, identifier: int) -> None:
        if not self.backend:
            return
        setters = {TrackKind.AUDIO: self.backend.set_audio_track,
                   TrackKind.VIDEO: self.backend.set_video_track,
                   TrackKind.SUBTITLE: self.backend.set_subtitle_track}
        try:
            setters[kind](identifier)
            self._persist_media_preferences()
            self.status.set(f"{kind.value.title()} track selected: {identifier}")
        except BackendError as exc:
            self.status.set(str(exc))

    def _make_audio_device_menu(self, parent) -> None:
        button, menu = self._menu_button(parent, "Output")
        self._audio_device_menu = menu
        menu.configure(postcommand=self._refresh_audio_devices)

    def _make_chapter_menu(self, parent) -> None:
        _button, menu = self._menu_button(parent, "Chapters")
        self._chapter_menu = menu
        menu.configure(postcommand=self._refresh_chapters)

    def _make_sync_menu(self, parent) -> None:
        _button, menu = self._menu_button(parent, "Sync")
        menu.add_command(label="Audio delay…", command=self.set_audio_delay_dialog)
        menu.add_command(label="Subtitle delay…", command=self.set_subtitle_delay_dialog)

    def set_audio_delay_dialog(self) -> None:
        value = simpledialog.askfloat(
            "Audio delay", "Milliseconds (-5000 to 5000):",
            initialvalue=self._audio_delay_ms, minvalue=-5000, maxvalue=5000,
            parent=self,
        )
        if value is not None:
            self._set_media_delay("audio", value)

    def set_subtitle_delay_dialog(self) -> None:
        value = simpledialog.askfloat(
            "Subtitle delay", "Milliseconds (-5000 to 5000):",
            initialvalue=self._subtitle_delay_ms, minvalue=-5000, maxvalue=5000,
            parent=self,
        )
        if value is not None:
            self._set_media_delay("subtitle", value)

    def _set_media_delay(self, kind: str, milliseconds: float) -> None:
        value = max(-5000.0, min(5000.0, float(milliseconds)))
        if self.backend:
            try:
                if kind == "audio":
                    value = self.backend.set_audio_delay(value)
                else:
                    value = self.backend.set_subtitle_delay(value)
            except BackendError as exc:
                self.status.set(str(exc)); return
        if kind == "audio":
            self._audio_delay_ms = value
        else:
            self._subtitle_delay_ms = value
        self._persist_media_preferences()
        self.status.set(f"{kind.title()} delay {value:+g} ms")

    def _refresh_chapters(self) -> None:
        self._chapter_menu.delete(0, "end")
        if not self.backend:
            self._chapter_menu.add_command(label="No active media", state="disabled")
            return
        chapters = self.backend.chapter_descriptors()
        if not chapters:
            self._chapter_menu.add_command(label="No chapters reported", state="disabled")
            return
        for chapter in chapters:
            minutes, seconds = divmod(max(0, int(chapter.start_seconds)), 60)
            self._chapter_menu.add_command(
                label=f"{minutes:02d}:{seconds:02d} · {chapter.title}",
                command=lambda identifier=chapter.identifier:
                self._select_chapter(identifier),
            )
        self._draw_chapter_markers(chapters)

    def _draw_chapter_markers(self, chapters=None) -> None:
        canvas = getattr(self, "chapter_timeline", None)
        if canvas is None:
            return
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        canvas.create_line(0, 2, width, 2, fill=MUTED)
        if chapters is None:
            if not self.backend:
                return
            try:
                chapters = self.backend.chapter_descriptors()
            except BackendError:
                return
        try:
            active = self.backend.chapter() if self.backend else -1
        except BackendError:
            active = -1
        for identifier, x, title, start in chapter_marker_positions(
                chapters, self.duration, width):
            color = RED if identifier == active else SECONDARY
            item = canvas.create_polygon(x - 4, 3, x + 4, 3, x, 13,
                                         fill=color, outline="", tags="chapter-marker")
            canvas.tag_bind(item, "<Button-1>",
                            lambda _event, value=identifier: self._select_chapter(value))
            canvas.tag_bind(item, "<Enter>",
                            lambda _event, value=title, seconds=start:
                            self.status.set(f"Chapter · {seconds:.1f} s · {value}"))

    def _select_chapter(self, identifier: int) -> None:
        if not self.backend:
            return
        try:
            self.backend.set_chapter(identifier)
            self.status.set(f"Chapter selected: {identifier + 1}")
            self.position.set(self.backend.position())
            self._draw_chapter_markers()
        except BackendError as exc:
            self.status.set(str(exc))

    def _refresh_audio_devices(self) -> None:
        self._audio_device_menu.delete(0, "end")
        if not self.backend:
            self._audio_device_menu.add_command(label="No active media", state="disabled"); return
        devices = self.backend.audio_devices()
        if not devices:
            self._audio_device_menu.add_command(label="Runtime reported no devices", state="disabled")
        for device in devices:
            self._audio_device_menu.add_command(
                label=device.label,
                command=lambda identifier=device.identifier: self._select_audio_device(identifier))

    def _select_audio_device(self, identifier: str) -> None:
        if not self.backend:
            return
        try:
            self.backend.set_audio_device(identifier)
            self._audio_device = identifier
            self.status.set(f"Audio output selected: {identifier}")
        except BackendError as exc:
            self.status.set(str(exc))

    def _nav(self, parent, heading: str, entries: list[str]) -> None:
        tk.Label(parent, text=heading, bg=PANEL, fg=MUTED, font=("TkDefaultFont", 8, "bold"), anchor="w").pack(fill="x", padx=14, pady=(14, 5))
        for entry in entries:
            row = tk.Frame(parent, bg=PANEL, height=27); row.pack(fill="x", padx=7, pady=1); row.pack_propagate(False)
            label = tk.Label(row, text="◆", bg=PANEL, fg=RED if entry == "Now Playing" else MUTED, width=3, anchor="e")
            label.pack(side="left")
            text_label = tk.Label(row, text=entry, bg=PANEL, fg=TEXT if entry == "Now Playing" else SECONDARY, anchor="w")
            text_label.pack(side="left", padx=6)
            for widget in (row, label, text_label):
                widget.bind("<Button-1>", lambda _event, name=entry: self._navigate(name))

    def _navigate(self, name: str) -> None:
        """Route every visible navigation entry to a concrete player action."""
        if name == "Now Playing":
            if self.current:
                self.canvas.focus_set()
                self.status.set(f"Now playing · {self.current.name}")
            else:
                self.status.set("No media is currently playing")
        elif name == "Library":
            self.show_library_dialog()
        elif name == "CASU Files":
            self._add_dialog_filter("CASU media", "*.casu")
        elif name == "Video":
            self._add_dialog_filter("Video media", "*.mp4 *.mkv *.mov *.m4v *.webm *.avi")
        elif name == "Music":
            self._add_dialog_filter("Audio media", "*.mp3 *.flac *.wav *.ogg *.opus *.m4a *.aac *.aiff")
        elif name == "Playlists":
            self.load_playlist()
        elif name == "Local Files":
            self.add_dialog()
        elif name == "Network Stream":
            self.open_url_dialog()

    def _add_dialog_filter(self, label: str, pattern: str) -> None:
        paths = filedialog.askopenfilenames(filetypes=[(label, pattern), ("All files", "*.*")])
        self.add_files([Path(path) for path in paths])

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

    def _render_playlist(self, selected: int | None = None) -> None:
        self.library.delete(0, "end")
        self.queue.delete(0, "end")
        for path in self.playlist_model.items:
            self.library.insert("end", str(path))
            self.queue.insert("end", path.name)
        if selected is not None and 0 <= selected < len(self.playlist_model):
            self.library.selection_set(selected); self.library.see(selected)
            self.queue.selection_set(selected); self.queue.see(selected)
        self._sync_queue_empty()

    def move_queue(self, delta: int) -> None:
        """Reorder the real playlist and keep its display models aligned."""
        selected = self.queue.curselection()
        if not selected:
            return
        index = selected[0]
        target = index + int(delta)
        try:
            target = self.playlist_model.move(index, delta)
        except PlaylistError as exc:
            self.status.set(str(exc)); return
        self._render_playlist(target)

    def clear_playlist(self) -> None:
        if self.backend:
            self.stop()
        self.playlist_model.clear()
        self._render_playlist()
        self.current = None
        self.now_playing.configure(text="NOW PLAYING · NO MEDIA SELECTED")
        self.status.set("Playlist cleared")
        self._sync_queue_empty()

    def play_next(self):
        """Advance to the next queued media item."""
        selected = self.library.curselection()
        current_index = self.playlist_model.index_of(self.current) if self.current else None
        index = selected[0] if selected else (-1 if current_index is None else current_index)
        if index + 1 >= len(self.playlist_model):
            self.status.set("End of playlist")
            return
        self.library.selection_clear(0, "end")
        self.library.selection_set(index + 1)
        self.library.see(index + 1)
        self.play_selected()

    def play_previous(self):
        """Return to the previous queued media item."""
        selected = self.library.curselection()
        current_index = self.playlist_model.index_of(self.current) if self.current else None
        index = selected[0] if selected else (0 if current_index is None else current_index)
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
            self.backend.on_event = self._backend_event
            self.backend.open_source(source)
            self.controller.attach(self.backend, source)
            self.controller.play()
            self._apply_playback_rate()
            self._apply_backend_settings()
            self._set_diagnostics(support="Legacy network backend", integrity="unavailable", segmented="unavailable", energy="unavailable — not measured")
            self.duration = self.backend.duration()
            self.timeline.configure(to=max(self.duration, 1.0))
            self._draw_chapter_markers()
            capabilities = self.backend.capabilities()
            self.status.set(f"Playing network source · {capabilities.get('version', 'libVLC')} · timing owned by libVLC")
        except (BackendError, OSError) as exc:
            self.controller.close()
            self.backend = None
            self.status.set(f"Could not open network source: {exc}")
            messagebox.showerror("MPCASU", str(exc))

    def add_files(self, paths: list[Path]):
        added: list[Path] = []
        for path in paths:
            if path.is_file():
                try:
                    if self.playlist_model.add((path,), existing_only=True):
                        added.append(path.expanduser().resolve())
                except PlaylistError as exc:
                    self.status.set(str(exc)); break
        for path in added:
            try:
                self.media_library.upsert(path)
            except OSError:
                pass
        self._render_playlist()

    def add_watched_folder(self):
        selected = filedialog.askdirectory(mustexist=True)
        if not selected:
            return
        folder = str(Path(selected).expanduser().resolve())
        if folder not in self._watched_folders:
            self._watched_folders.append(folder)
        try:
            scanned = self.media_library.scan([folder])
            self._save_effective_settings()
            self.status.set(f"Library scan complete · {len(scanned)} file(s) seen")
        except (OSError, ValueError) as exc:
            self.status.set(f"Library scan failed: {exc}")
        self.show_library_dialog()

    def refresh_watched_folders(self):
        if not self._watched_folders:
            self.status.set("No watched folders configured")
            return
        try:
            scanned = self.media_library.scan(self._watched_folders)
            self.status.set(f"Library refreshed · {len(scanned)} file(s) seen")
        except (OSError, ValueError) as exc:
            self.status.set(f"Library refresh failed: {exc}")

    def show_library_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("MPCASU Library")
        dialog.geometry("760x480")
        dialog.configure(bg=BG)
        query = tk.StringVar()
        top = tk.Frame(dialog, bg=BG, padx=12, pady=12); top.pack(fill="x")
        tk.Label(top, text="Search", bg=BG, fg=TEXT).pack(side="left")
        entry = ttk.Entry(top, textvariable=query); entry.pack(side="left", fill="x", expand=True, padx=8)
        results = tk.Listbox(dialog, bg=PANEL_ALT, fg=TEXT,
                             selectbackground=RED_DARK, relief="flat")
        results.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        preview = tk.Label(dialog, text="Select media for preview", bg=PANEL,
                           fg=MUTED, height=10)
        preview.pack(fill="x", padx=12, pady=(0, 8))
        paths: list[Path] = []
        preview_generation = [0]
        preview_image = [None]

        def refresh(*_args):
            paths.clear(); results.delete(0, "end")
            for item in self.media_library.search(query.get()):
                paths.append(item.path)
                marker = "★ " if item.favorite else ""
                resume = f" · resume {item.resume_seconds:.1f}s" if item.resume_seconds else ""
                results.insert("end", f"{marker}{item.path.name}{resume}  —  {item.path.parent}")

        def add_selected(_event=None):
            selected = results.curselection()
            if selected:
                self.add_files([paths[selected[0]]])
                dialog.destroy()

        def load_preview(_event=None):
            selected = results.curselection()
            if not selected:
                return
            source = paths[selected[0]]
            preview_generation[0] += 1
            generation = preview_generation[0]
            preview.configure(image="", text="Decoding thumbnail…")

            def worker():
                thumbnail = thumbnail_for(source, self._thumbnail_directory)
                def present():
                    if (generation != preview_generation[0] or
                            not dialog.winfo_exists()):
                        return
                    if thumbnail is None:
                        preview.configure(image="", text="No video thumbnail available")
                        return
                    try:
                        image = tk.PhotoImage(file=str(thumbnail))
                    except (tk.TclError, OSError):
                        preview.configure(image="", text="Thumbnail could not be displayed")
                        return
                    preview_image[0] = image
                    preview.configure(image=image, text="")
                try:
                    self.after(0, present)
                except tk.TclError:
                    pass
            threading.Thread(target=worker, name="mpcasu-thumbnail",
                             daemon=True).start()

        controls = tk.Frame(dialog, bg=BG, padx=12, pady=8); controls.pack(fill="x")
        ttk.Button(controls, text="Refresh watched folders", style="MPC.TButton",
                   command=lambda: (self.refresh_watched_folders(), refresh())).pack(side="left")
        ttk.Button(controls, text="Add selected", style="MPC.TButton",
                   command=add_selected).pack(side="right")
        results.bind("<Double-Button-1>", add_selected)
        results.bind("<<ListboxSelect>>", load_preview)
        query.trace_add("write", refresh)
        refresh(); entry.focus_set()

    def _save_effective_settings(self) -> None:
        self.settings_store.save(PlayerSettings(
            self._volume, self._muted, self._rate, self._audio_device,
            tuple(self._watched_folders),
        ))

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
            self._resume_source = str(payload.get("current", "")) or None
            self._resume_position = max(0.0, float(payload.get("position", 0.0)))
            geometry = payload.get("geometry")
            if isinstance(geometry, str) and geometry:
                self.geometry(geometry)
        except (OSError, ValueError, TypeError):
            pass

    def _shutdown(self):
        resume_position = self.backend.position() if self.backend else self.position.get()
        self._persist_media_preferences()
        try:
            self._session_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._session_file.with_suffix(".tmp")
            temporary.write_text(json.dumps({
                "playlist": [str(item) for item in self.playlist_model.items],
                "volume": self._volume,
                "muted": self._muted,
                "rate": self._rate,
                "current": str(self.current) if self.current else None,
                "position": resume_position,
                "geometry": self.geometry(),
            }, indent=2) + "\n", encoding="utf-8")
            temporary.replace(self._session_file)
        except OSError:
            pass
        if self.current and self.current.is_file():
            try:
                self.media_library.record_progress(self.current, resume_position,
                                                   self.duration or None)
            except OSError:
                pass
        try:
            self._save_effective_settings()
        except OSError:
            pass
        self.controller.close()
        self.backend = None
        self.media_library.close()
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
            with path.open("rb") as handle:
                magic = handle.read(8)
            if magic == b"CASUNAT2":
                container = read_native_v2(path)
                self._visual_state = "CASUNAT2 native state stream"
                self._visual_segments = [
                    {"start_s": 0.0, "end_s": 0.0, "state": chunk.chunk_type.name}
                    for chunk in container.chunks
                    if chunk.chunk_type in {ChunkType.VIDEO_KEY_STATE,
                                            ChunkType.VIDEO_TILE_UPDATE}
                ]
                self._visual_video_segments = list(self._visual_segments)
                return
            manifest = (read_native(path, verify_payload=True).manifest if magic == b"CASUNAT1"
                        else json.loads(path.read_text(encoding="utf-8")))
            errors = validate_manifest(manifest)
            if errors:
                self._visual_state = "invalid CASU: " + errors[0]
                return
            self._visual_video_segments = [segment for segment in manifest.get("video", {}).get("segments", []) if isinstance(segment, dict)]
            self._visual_audio_segments = [segment for segment in manifest.get("audio", {}).get("segments", []) if isinstance(segment, dict)]
            self._visual_segments = self._visual_video_segments + self._visual_audio_segments
            self._scheduler = CasuScheduler.from_manifest(manifest, "video" if self._visual_video_segments else "audio")
            self._visual_state = "CASU state map" if self._visual_segments else "CASU empty map"
        except (OSError, ValueError, TypeError, NativeCasuError, NativeV2Error):
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

    def remove_selected(self):
        selected = list(self.library.curselection())
        try:
            self.playlist_model.remove(selected)
        except PlaylistError as exc:
            self.status.set(str(exc)); return
        self._render_playlist()

    def save_playlist(self):
        target = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("MPCASU playlist", "*.json"), ("All files", "*.*")])
        if not target:
            return
        try:
            Path(target).write_text(json.dumps(self.playlist_model.to_payload(),
                                               indent=2) + "\n", encoding="utf-8")
            self.status.set(f"Playlist saved · {Path(target).name}")
        except OSError as exc:
            messagebox.showerror("MPCASU", f"Could not save playlist: {exc}")

    def load_playlist(self):
        source = filedialog.askopenfilename(filetypes=[("MPCASU playlist", "*.json"), ("All files", "*.*")])
        if not source:
            return
        try:
            payload = json.loads(Path(source).read_text(encoding="utf-8"))
            loaded = PlaylistModel.from_payload(payload, existing_only=True)
            self.add_files(list(loaded.items))
            self.status.set(f"Playlist loaded · {Path(source).name}")
        except (OSError, PlaylistError, ValueError, TypeError) as exc:
            messagebox.showerror("MPCASU", f"Could not load playlist: {exc}")

    def show_media_info(self):
        path = self.current or self.selected_path()
        if not path or not path.is_file():
            self.status.set("No local media selected for information")
            return
        try:
            native = False
            native_v2 = False
            if path.suffix.lower() == ".casu":
                with path.open("rb") as handle:
                    magic = handle.read(8)
                    native = magic == b"CASUNAT1"
                    native_v2 = magic == b"CASUNAT2"
            if native_v2:
                container = read_native_v2(path)
                manifest = container.manifest
                source = path
                streams = []
                for item in manifest.get("streams", []):
                    stream = dict(item)
                    stream["codec_type"] = stream.get("type")
                    stream["codec_name"] = "casu-" + str(stream.get("type", "data"))
                    streams.append(stream)
                probe = {"streams": streams,
                         "format": {"format_name": "CASUNAT2 segmented media",
                                    "duration": self.backend.duration() if isinstance(self.backend, NativeCasuBackend) else "unknown",
                                    "size": path.stat().st_size,
                                    "tags": manifest.get("metadata", {})}}
            elif native:
                manifest = read_native(path, verify_payload=True).manifest
                source = path
                probe = {"streams": manifest.get("streams", []),
                         "format": {"format_name": "CASU native container",
                                    "duration": manifest.get("source", {}).get("duration_s", "unknown"),
                                    "size": path.stat().st_size}}
            else:
                source = self._source_for(path)
                probe = ffprobe(source)
            lines = [f"File: {path.name}", f"Source: {source.name}",
                     f"Container: {probe.get('format', {}).get('format_name', 'unknown')}",
                     f"Duration: {probe.get('format', {}).get('duration', 'unknown')} s",
                     f"Size: {probe.get('format', {}).get('size', 'unknown')} bytes"]
            metadata = probe.get("format", {}).get("tags", {})
            if isinstance(metadata, dict):
                for key in ("title", "artist", "album", "album_artist", "date", "genre"):
                    value = metadata.get(key)
                    if value not in (None, ""):
                        lines.append(f"{key.replace('_', ' ').title()}: {value}")
            if path.suffix.lower() == ".casu":
                lines.extend(["CASU: verified native CASUNAT2" if native_v2 else
                              "CASU: verified CASUNAT1 compatibility envelope" if native else
                              "CASU: validated sidecar manifest",
                              f"Segment hints: {len(self._visual_segments)}"])
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
        except (CasuError, NativeCasuError, NativeV2Error, OSError, ValueError) as exc:
            messagebox.showerror("MPCASU", f"Media information unavailable: {exc}")

    def selected_path(self) -> Path | None:
        selected = self.library.curselection()
        if not selected:
            if self.current:
                return self.current
            # Opening a file from the command line or file manager populates
            # the queue without creating a Listbox selection.  The first queue
            # item is the deterministic playback target in that case.
            if len(self.playlist_model):
                return self.playlist_model.item(0)
            return None
        try:
            return self.playlist_model.item(selected[0])
        except PlaylistError:
            return None

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
        selected_index = (selected[0] if selected
                          else self.playlist_model.index_of(path))
        if selected_index is not None:
            self.library.selection_clear(0, "end")
            self.library.selection_set(selected_index)
            self.library.see(selected_index)
            self.queue.selection_clear(0, "end")
            self.queue.selection_set(selected_index)
            self.queue.see(selected_index)
        sidecar = path if path.suffix.lower() == ".casu" else self._sidecar(path)
        self._load_visual_state(sidecar if sidecar.exists() else path)
        if path.suffix.lower() == ".casu":
            magic = b""
            try:
                magic = path.read_bytes()[:8]
                native = magic in {b"CASUNAT1", b"CASUNAT2"}
            except OSError:
                native = False
            self._set_diagnostics(
                # The current .casu format is a validated sidecar compatibility
                # manifest. Do not present it as a native decoded CASU payload.
                support=("CASUNAT2 native key-state/tile/PCM" if magic == b"CASUNAT2" else
                         "CASUNAT1 compatibility + libVLC" if native else
                         "CASU sidecar + libVLC"),
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
            if path.suffix.lower() == ".casu" and NativeCasuBackend.supports(path):
                try:
                    audio_sink = PulseAudioSink()
                except BackendError:
                    # Video-only/headless systems still get native CASU video.
                    audio_sink = None
                self.backend = NativeCasuBackend(TkCanvasVideoSink(self.canvas), audio_sink)
            else:
                self.backend = CasuBackend(self.canvas) if path.suffix.lower() == ".casu" else LibVLCBackend(self.canvas)
            self.backend.on_event = self._backend_event
            if path.suffix.lower() == ".casu": self.backend.open_casu(path)
            else: self.backend.open(source)
            self.controller.attach(self.backend, path)
            if isinstance(self.backend, NativeCasuBackend):
                self._apply_media_preferences()
            self.controller.play()
            self._apply_playback_rate()
            self._apply_backend_settings()
            self.duration = self.backend.duration()
            self.timeline.configure(to=max(self.duration, 1.0))
            self._draw_chapter_markers()
            if (self._resume_source and str(path) == self._resume_source
                    and 5.0 < self._resume_position < max(5.0, self.duration - 5.0)):
                self.controller.seek(self._resume_position)
                self.position.set(self._resume_position)
                self.status.set(f"Resumed {path.name} at {self._resume_position:.1f} s")
            else:
                self._resume_position = 0.0
            capabilities = self.backend.capabilities()
            self.status.set(f"{path.name} · {state} · {capabilities.get('version', 'libVLC')}")
            # libVLC can accept a media object while a decoder later fails.
            # Check local playback after its asynchronous pipeline had time to
            # announce streams; never leave the UI claiming PLAYING forever
            # when no timed media was produced.
            if isinstance(self.backend, LibVLCBackend):
                self.after(500, self._apply_media_preferences)
                self.after(1500, self._check_playback_start)
        except (BackendError, CasuError, OSError) as exc:
            self.controller.close()
            self.backend = None
            self.status.set("Cannot play — internal media backend unavailable")
            messagebox.showerror("MPCASU", f"Could not start internal playback: {exc}")
            return
        self._paused = False
        self._update_presentation(path)

    def _apply_backend_settings(self) -> None:
        if not self.backend:
            return
        self._volume = self.backend.set_volume(self._volume)
        self.backend.set_mute(self._muted)
        if self._audio_device:
            try:
                self.backend.set_audio_device(self._audio_device)
            except BackendError:
                # A stored device may have been unplugged; playback continues
                # on the backend default and the stale choice is discarded.
                self._audio_device = None

    def _apply_playback_rate(self) -> None:
        if not self.backend:
            return
        try:
            self._rate = self.backend.set_rate(self._rate)
        except BackendError:
            if not isinstance(self.backend, NativeCasuBackend):
                raise
            self._rate = self.backend.set_rate(1.0)
        self.rate_button.configure(text=f"{self._rate:g}×")

    def _apply_media_preferences(self) -> None:
        if not self.backend or not self.current or not self.current.is_file():
            return
        preferences = self.media_library.playback_preferences(self.current)
        for identifier, setter in (
            (preferences.audio_track, self.backend.set_audio_track),
            (preferences.video_track, self.backend.set_video_track),
            (preferences.subtitle_track, self.backend.set_subtitle_track),
        ):
            if identifier is not None:
                try:
                    setter(identifier)
                except BackendError:
                    pass
        self._audio_delay_ms = preferences.audio_delay_ms
        self._subtitle_delay_ms = preferences.subtitle_delay_ms
        try:
            self._audio_delay_ms = self.backend.set_audio_delay(self._audio_delay_ms)
        except BackendError:
            self._audio_delay_ms = 0.0
        try:
            self._subtitle_delay_ms = self.backend.set_subtitle_delay(
                self._subtitle_delay_ms
            )
        except BackendError:
            self._subtitle_delay_ms = 0.0

    def _persist_media_preferences(self) -> None:
        if not self.backend or not self.current or not self.current.is_file():
            return
        try:
            audio_track = self.backend.audio_track()
            video_track = self.backend.video_track()
            preferences = PlaybackPreferences(
                audio_track=audio_track if audio_track >= 0 else None,
                video_track=video_track if video_track >= 0 else None,
                subtitle_track=self.backend.subtitle_track(),
                audio_delay_ms=self._audio_delay_ms,
                subtitle_delay_ms=self._subtitle_delay_ms,
            )
            self.media_library.set_playback_preferences(self.current, preferences)
        except (BackendError, OSError, ValueError):
            pass

    def _backend_event(self, state: PlaybackState) -> None:
        """Receive libVLC events without touching Tk from its worker thread."""
        try:
            self.after(0, lambda state=state: self._apply_backend_event(state))
        except tk.TclError:
            # Shutdown can race an asynchronous backend callback.
            pass

    def _apply_backend_event(self, state: PlaybackState) -> None:
        if state == PlaybackState.PLAYING:
            self._paused = False
        elif state == PlaybackState.PAUSED:
            self._paused = True
        elif state == PlaybackState.ERROR:
            self.status.set("Playback error — decoder or output failed")
            self._set_diagnostics(support="backend error; inspect media information/logs")
        elif state == PlaybackState.ENDED and not self._advancing and not self._end_handled:
            self._end_handled = True
            self._advancing = True
            try:
                self.play_next()
            finally:
                self._advancing = False

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
            native = False
            native_v2 = False
            if path.suffix.lower() == ".casu":
                with path.open("rb") as handle:
                    magic = handle.read(8)
                    native = magic == b"CASUNAT1"
                    native_v2 = magic == b"CASUNAT2"
            if native_v2:
                manifest = read_native_v2(path).manifest
                streams = [{**item, "codec_type": item.get("type")}
                           for item in manifest.get("streams", [])]
                probe = {"streams": streams, "format": {}}
            elif native:
                manifest = read_native(path, verify_payload=False).manifest
                streams = manifest.get("streams", [])
                probe = {"streams": streams, "format": {"duration": manifest.get("source", {}).get("duration_s", 0)}}
            else:
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
        except (CasuError, OSError, ValueError, NativeCasuError, NativeV2Error):
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
            self.rate_button.configure(text=f"{self._rate:g}×")
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

    def cycle_video_track(self):
        if not self.backend:
            self.status.set("No active media backend")
            return
        try:
            count = self.backend.video_track_count()
            if count <= 0:
                self.status.set("No selectable video tracks reported by libVLC")
                return
            current = self.backend.video_track()
            next_track = (current + 1) % count
            self.backend.set_video_track(next_track)
            labels = self.backend.video_track_descriptions()
            label = next((name for identifier, name in labels if identifier == next_track), f"Track {next_track + 1}")
            self.status.set(f"Video: {label} ({next_track + 1}/{count})")
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

    def load_external_subtitle(self):
        if not self.backend or not self.current:
            self.status.set("Open local media before loading an external subtitle")
            return
        subtitle = filedialog.askopenfilename(
            filetypes=[("Subtitle files", "*.srt *.ass *.ssa *.vtt *.sub"), ("All files", "*.*")]
        )
        if not subtitle:
            return
        try:
            position = self.backend.position()
            paused = self._paused
            self.backend.add_external_subtitle(Path(subtitle))
            self.duration = self.backend.duration()
            self.timeline.configure(to=max(self.duration, 1.0))
            self._draw_chapter_markers()
            self.backend.seek(position)
            if not paused:
                self.backend.play()
            self.status.set(f"External subtitle loaded · {Path(subtitle).name}")
        except (BackendError, OSError) as exc:
            self.status.set(f"Could not load subtitle: {exc}")

    def next_chapter(self):
        if not self.backend:
            self.status.set("No active media backend")
            return
        try:
            count = self.backend.chapter_count()
            if count <= 0:
                self.status.set("No chapters reported by libVLC")
                return
            current = self.backend.chapter()
            self.backend.set_chapter((current + 1) % count)
            self.status.set(f"Chapter {(current + 1) % count + 1}/{count}")
        except BackendError as exc:
            self.status.set(str(exc))

    def next_frame(self):
        if not self.backend:
            self.status.set("No active media backend")
            return
        try:
            self.backend.next_frame()
            self._paused = True
            self.status.set("Advanced one decoded frame")
        except BackendError as exc:
            self.status.set(str(exc))

    def toggle_fullscreen(self):
        self.attributes("-fullscreen", not bool(self.attributes("-fullscreen")))

    def _source_for(self, path: Path) -> Path:
        if path.suffix.lower() != ".casu":
            return path
        try:
            with path.open("rb") as handle:
                if handle.read(8) in {b"CASUNAT1", b"CASUNAT2"}:
                    # Native containers are verified and extracted by
                    # CasuBackend; do not attempt to parse their binary bytes
                    # as a JSON sidecar here.
                    return path
        except OSError as exc:
            raise CasuError(f"could not read CASU container: {path}") from exc
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
            self._persist_media_preferences()
            self.controller.stop()
            self.controller.close()
        self.backend = None
        self._draw_chapter_markers(())
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
