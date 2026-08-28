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
import queue
import random
import subprocess
import threading
import time
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
try:
    import resource
except ImportError:  # pragma: no cover - Windows has no stdlib resource module
    resource = None
try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover - optional presentation enhancement
    Image = ImageTk = None

from casu.design import (BG, PANEL, PANEL_ALT, LINE, RED, RED_DARK, TEXT,
                          SECONDARY, MUTED, STAGE, TOAST_BG, TOAST_BORDER,
                          BADGE_BG, BADGE_BORDER, INPUT_BG, INPUT_BORDER,
                          SCROLLBAR, SIDEBAR, TOKENS)
from casu.core import CasuError, resolve_casu_source, ffprobe
from casu.schema import validate_manifest
from casu.scheduler import CasuScheduler
from casu.library import MediaLibrary, PlaybackPreferences
from casu.media import TrackKind
from casu.fileio import atomic_write_json, read_bounded_json
from casu.epg import (EpgError, EpgGuide, StreamCatalog, StreamChannel,
                      fetch_m3u, fetch_xmltv, load_m3u, load_xmltv)
from casu.filetypes import (CASUNAT1 as LOCAL_CASUNAT1,
                            CASUNAT2 as LOCAL_CASUNAT2,
                            CASU_SIDECAR as LOCAL_CASU_SIDECAR,
                            CASUMP5 as LOCAL_MP5,
                            MAX_SIDECAR_BYTES, detect_casu_kind)
from casu.playlist import (MAX_PLAYLIST_FILE_BYTES, PLAYLIST_SUFFIXES,
                           PlaylistError,
                           PlaylistModel, detect_entry_type, detect_media_type,
                           detect_playlist_format,
                           load_playlist_file, save_playlist_file)
from casu.settings import PlayerSettings, SettingsStore
from casu.recording import MediaRecorder, RecordingError
from casu.thumbnail import thumbnail_for
from casu.locations import (LocationResolutionError, is_youtube_url,
                            resolve_media_location)
from casu.spotify import is_spotify_url
from casu.waveform import (WaveformError, decode_all_pcm, live_spectrum,
                           spectrum_bands, waveform_peaks, window_peaks)
from mpcasu_backend import (BackendError, CasuBackend, LibVLCBackend,
                            PlaybackState, display_media_source)
from casu.native import NativeCasuError, read_native
from casu.native_v2 import ChunkType, NativeV2Error, read_native_v2
from mpcasu_native_backend import NativeCasuBackend, PulseAudioSink, TkCanvasVideoSink
from mpcasu_playback import PlaybackController


MEDIA = {
    ".3g2", ".3gp", ".aac", ".ac3", ".aiff", ".alac", ".amr", ".ape",
    ".asf", ".au", ".avi", ".caf", ".casu", ".cue", ".divx", ".dts",
    ".dv", ".f4v", ".flac", ".flv", ".m2ts", ".m2v", ".m3u", ".m3u8",
    ".m4a", ".m4v", ".mid", ".midi", ".mka", ".mkv", ".mod", ".mov",
    ".mp2", ".mp3", ".mp4", ".mpc", ".mpeg", ".mpg", ".mts", ".mxf",
    ".oga", ".ogg", ".ogm", ".ogv", ".opus", ".pls", ".ra", ".rm",
    ".rmvb", ".s3m", ".spx", ".ts", ".tta", ".vob", ".voc", ".wav",
    ".webm", ".wma", ".wmv", ".wv", ".xm", ".mp5",
}

LOCAL_MEDIA = "media"


def detect_local_playback_kind(path: str | Path) -> str:
    """Classify local playback by verified content, using suffix only to fail closed.

    Native CASU files are therefore routed correctly even after a rename. A
    valid JSON sidecar can likewise be recognized without relying on `.casu`.
    Ordinary media is never parsed beyond a small signature unless it begins
    like JSON and remains within the sidecar size bound.
    """
    source = Path(path).expanduser().resolve()
    route = detect_casu_kind(source)
    if route is not None:
        return route
    if source.suffix.lower() in {".casu", ".mp5"}:
        # A user or download manager may have given ordinary media a misleading
        # extension. Accept it only after the bounded production probe proves a
        # real timed audio/video stream; malformed CASU still fails closed.
        try:
            streams = ffprobe(source).get("streams", [])
        except CasuError:
            streams = []
        if any(isinstance(item, dict) and item.get("codec_type") in {"audio", "video"}
               for item in streams):
            return LOCAL_MEDIA
        raise CasuError("invalid CASU/MP5 container or sidecar: unknown CASU signature")
    return LOCAL_MEDIA


def discover_vlc_plugin_path() -> str | None:
    """Locate the VLC plugin directory across common distributions."""
    candidates = (
        "/usr/lib/x86_64-linux-gnu/vlc/plugins",
        "/usr/lib/aarch64-linux-gnu/vlc/plugins",
        "/usr/lib64/vlc/plugins",
        "/usr/lib/vlc/plugins",
        "/usr/local/lib/vlc/plugins",
        "/snap/vlc/current/usr/lib/vlc/plugins",
    )
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return None


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


def process_resource_snapshot(previous_cpu: float, previous_wall: float,
                              *, cpu_now: float | None = None,
                              wall_now: float | None = None,
                              max_rss: int | None = None) -> tuple[str, float, float]:
    """Return truthful process CPU/RAM telemetry and the next sample state."""
    current_cpu = time.process_time() if cpu_now is None else float(cpu_now)
    current_wall = time.monotonic() if wall_now is None else float(wall_now)
    wall_delta = max(1e-9, current_wall - float(previous_wall))
    cpu_percent = max(0.0, (current_cpu - float(previous_cpu)) / wall_delta * 100.0)
    resident = (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                if max_rss is None and resource is not None else int(max_rss or 0))
    # Linux reports KiB; macOS/BSD report bytes.
    resident_mib = resident / (1024 * 1024 if sys.platform == "darwin" else 1024)
    ram = f"RAM {resident_mib:.1f} MiB" if resident else "RAM unavailable"
    return f"CPU {cpu_percent:.1f}% · {ram}", current_cpu, current_wall


class MPCASUPlayer(tk.Tk):
    def __init__(self, initial: Path | list[Path] | None = None):
        super().__init__()
        self.title("MPCASU Media Player")
        initial_width = min(1420, max(920, self.winfo_screenwidth() - 60))
        initial_height = min(860, max(600, self.winfo_screenheight() - 100))
        self.geometry(f"{initial_width}x{initial_height}")
        self.minsize(860, 560)
        self.configure(bg=BG)
        self.backend: LibVLCBackend | NativeCasuBackend | None = None
        self.controller = PlaybackController()
        self.current: Path | None = None
        self._network_source: str | None = None
        self._network_display: str | None = None
        self._stream_channel: StreamChannel | None = None
        self._location_generation = 0
        self._stream_catalog = StreamCatalog(())
        self._epg_guide = EpgGuide({}, ())
        self._last_epg_minute: int | None = None
        self.duration = 0.0
        self.position = tk.DoubleVar(value=0.0)
        self.status = tk.StringVar(value="Ready — CASU and legacy media")
        self.resource_status = tk.StringVar(value="CPU 0.0% · RAM measuring…")
        self._resource_cpu = time.process_time()
        self._resource_wall = time.monotonic()
        self._dragging = False
        self._paused = False
        self._started_at = 0.0
        self._start_offset = 0.0
        self._visual_phase = 0.0
        self._visual_state = "idle"
        self._visual_segments: list[dict] = []
        self._visual_video_segments: list[dict] = []
        self._visual_audio_segments: list[dict] = []
        self._waveform: tuple[float, ...] = ()
        self._spectrum: tuple[float, ...] = ()
        self._waveform_generation = 0
        self._pcm_buffer: tuple[np.ndarray | None, int, int] = (None, 0, 0)
        self._spectrum_peak_fall: list[float] = []
        self._presentation_mode = "UNKNOWN"
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
        self._mini_mode = False
        self._pre_mini_geometry = ""
        self._advancing = False
        self._end_handled = False
        self._shuffle = False
        self._repeat_mode = "off"
        self._ab_start: float | None = None
        self._ab_end: float | None = None
        self._random = random.SystemRandom()
        self._recorder: MediaRecorder | None = None
        self._recording_finishing = False
        self._backend_events: queue.SimpleQueue[PlaybackState] = queue.SimpleQueue()
        self._toast_job: str | None = None
        self._format_badge = "MPCASU"
        self._integrity_badge = "READY"
        self.playlist_model = PlaylistModel()
        # URL rows → resolved display titles (YouTube etc.), Tk twin of the
        # Qt PlaylistPane._display_titles dict.
        self._display_titles: dict[str, str] = {}
        self._session_file = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "mpcasu" / "session.json"
        self.settings_store = SettingsStore(self._session_file.parent / "settings.json")
        effective_settings = self.settings_store.load()
        self._volume = effective_settings.volume
        self._muted = effective_settings.muted
        self._rate = effective_settings.rate
        self._audio_device = effective_settings.audio_device
        self._watched_folders = list(effective_settings.watched_folders)
        self._visualizer_mode = effective_settings.visualizer
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
        style.map("MPC.TButton", background=[("active", RED_DARK)],
                  foreground=[("active", TEXT)])
        style.configure("MPC.Horizontal.TScale", troughcolor=LINE, background=RED)
        style.configure("TNotebook", background=PANEL, borderwidth=0,
                        tabmargins=(6, 4, 6, 0))
        style.configure("TNotebook.Tab", background=PANEL_ALT, foreground=SECONDARY,
                        padding=(12, 6), borderwidth=0,
                        font=("TkDefaultFont", 8, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", RED_DARK)],
                  foreground=[("selected", RED)],
                  expand=[("selected", (0, 0, 0, 2))])
        style.configure("TEntry", fieldbackground=INPUT_BG, foreground=TEXT,
                        insertcolor=RED, bordercolor=INPUT_BORDER,
                        lightcolor=INPUT_BORDER, darkcolor=INPUT_BORDER)
        style.configure("TRadiobutton", background=PANEL, foreground=SECONDARY)
        style.map("TRadiobutton", background=[("active", PANEL)],
                  foreground=[("active", TEXT)])
        style.configure("TCheckbutton", background=PANEL, foreground=SECONDARY)
        style.map("TCheckbutton", background=[("active", PANEL)])
        style.configure("Vertical.TScrollbar", background=PANEL_ALT,
                        troughcolor=PANEL, borderwidth=0, arrowsize=10)
        style.map("Vertical.TScrollbar",
                  background=[("active", SCROLLBAR), ("pressed", SCROLLBAR)])
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
        self._nav(left, "SOURCES", ["Local Files", "Network Stream", "YouTube", "Spotify", "Live TV & EPG"])
        tk.Label(left, text="PLAYLIST", bg=PANEL, fg=MUTED, font=("TkDefaultFont", 8, "bold"), anchor="w").pack(fill="x", padx=14, pady=(12, 4))
        self.library = tk.Listbox(left, height=4, bg=PANEL_ALT, fg=SECONDARY, selectbackground=RED_DARK, selectforeground=TEXT, relief="flat", highlightthickness=0, activestyle="none", exportselection=False)
        self.library.pack(fill="x", padx=10)
        self.library.bind("<Double-Button-1>", lambda _event: self.play_selected())
        self.library.bind("<Return>", lambda _event: self.play_selected())
        actions = tk.Frame(left, bg=PANEL); actions.pack(fill="x", padx=12, pady=(12, 12))
        ttk.Button(actions, text="＋ Add media", style="MPC.TButton", command=self.add_dialog).pack(fill="x")
        ttk.Button(actions, text="＋ Add folder", style="MPC.TButton", command=self.add_folder_dialog).pack(fill="x", pady=(5, 0))
        ttk.Button(actions, text="↗ Open URL", style="MPC.TButton", command=self.open_url_dialog).pack(fill="x", pady=(5, 0))
        ttk.Button(actions, text="◉ Disc & capture", style="MPC.TButton", command=self.show_capture_dialog).pack(fill="x", pady=(5, 0))
        ttk.Button(actions, text="◫ Live TV & EPG", style="MPC.TButton", command=self.show_epg_dialog).pack(fill="x", pady=(5, 0))
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
        for symbol, name in (("▶", "Now Playing"), ("▦", "Library"), ("◆", "CASU Files"), ("♫", "Music"), ("☷", "Playlists"), ("⚙", "Settings")):
            ttk.Button(
                compact_nav, text=symbol, width=3, style="MPC.TButton",
                command=lambda label=name: self._navigate(label),
            ).pack(fill="x", padx=7, pady=5)
        self.compact_nav = compact_nav

        center = tk.Frame(body, bg=PANEL); center.pack(side="left", fill="both", expand=True)
        self.center_shell = center
        self.canvas = tk.Canvas(center, background=STAGE, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._empty_cta_bbox = None
        self.canvas.bind("<Configure>", lambda _event: self._draw_visualizer())
        self.canvas.bind("<Button-1>", self._on_stage_click)
        self._enable_drag_drop()
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
        for label, command in (("◀◀", self.play_previous), ("−10 s", lambda: self.seek_by(-10)), ("▶ / ❚❚", self.toggle_playback), ("■", self.stop), ("+10 s", lambda: self.seek_by(10)), ("▶▶", self.play_next)):
            ttk.Button(bar, text=label, style="MPC.TButton", command=command).pack(side="left", padx=3)
        self.shuffle_button = ttk.Button(bar, text="Shuffle off", style="MPC.TButton",
                                         command=self.toggle_shuffle)
        self.shuffle_button.pack(side="left", padx=3)
        self.repeat_button = ttk.Button(bar, text="Repeat off", style="MPC.TButton",
                                        command=self.cycle_repeat)
        self.repeat_button.pack(side="left", padx=3)
        self.record_button = ttk.Button(bar, text="● Record", style="MPC.TButton",
                                        command=self.toggle_recording)
        self.record_button.pack(side="left", padx=3)
        ttk.Button(bar, text="Mute", style="MPC.TButton", command=self.toggle_mute).pack(side="right", padx=3)
        self.rate_button = ttk.Button(bar, text=f"{self._rate:g}×",
                                      style="MPC.TButton", command=self.cycle_rate)
        self.rate_button.pack(side="right", padx=3)
        tools = tk.Frame(center, bg=PANEL)
        tools.pack(fill="x", padx=8, pady=(0, 6))
        self._track_menus = {}
        self._track_vars = {}
        self._make_track_menu(tools, "Audio", TrackKind.AUDIO)
        self._make_track_menu(tools, "Video", TrackKind.VIDEO)
        self._make_track_menu(tools, "Subtitles", TrackKind.SUBTITLE)
        self._make_audio_device_menu(tools)
        self._make_audio_controls_menu(tools)
        self._make_chapter_menu(tools)
        self._make_sync_menu(tools)
        self._make_video_controls_menu(tools)
        self._make_bookmark_menu(tools)
        ttk.Button(tools, text="A–B", style="MPC.TButton", command=self.cycle_ab_loop).pack(side="right", padx=3)
        ttk.Button(tools, text="Go to", style="MPC.TButton", command=self.goto_time_dialog).pack(side="right", padx=3)
        ttk.Button(tools, text="Snapshot", style="MPC.TButton", command=self.take_snapshot).pack(side="right", padx=3)
        ttk.Button(tools, text="Load subtitle", style="MPC.TButton", command=self.load_external_subtitle).pack(side="right", padx=3)
        ttk.Button(tools, text="Frame", style="MPC.TButton", command=self.next_frame).pack(side="right", padx=3)
        ttk.Button(tools, text="Info", style="MPC.TButton", command=self.show_media_info).pack(side="right", padx=3)
        ttk.Button(tools, text="Fullscreen", style="MPC.TButton", command=self.toggle_fullscreen).pack(side="right", padx=3)
        ttk.Button(tools, text="Mini", style="MPC.TButton", command=self.toggle_mini_player).pack(side="right", padx=3)
        tk.Label(center, textvariable=self.status, bg=PANEL, fg=SECONDARY, anchor="w").pack(fill="x", padx=14, pady=(0, 8))

        right = tk.Frame(body, bg=PANEL, width=320)
        # Pack the fixed-width panel BEFORE the expanding center frame so
        # pack allocates its 320 px first; packing it after an expand=True
        # slave squeezes the whole panel down to a single pixel.
        right.pack(side="right", fill="y", padx=(10, 0), before=center)
        right.pack_propagate(False)
        self.right_shell = right
        rnb = ttk.Notebook(right)
        rnb.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        self._right_notebook = rnb

        fb_frame = tk.Frame(rnb, bg=PANEL)
        rnb.add(fb_frame, text="Files")
        fb_top = tk.Frame(fb_frame, bg=PANEL)
        fb_top.pack(fill="x", padx=6, pady=(6, 2))
        self._fb_search_var = tk.StringVar()
        self._fb_search_var.trace_add("write", lambda *_: self._refresh_file_browser())
        tk.Label(fb_top, text="⌕", bg=PANEL, fg=MUTED).pack(side="left")
        ttk.Entry(fb_top, textvariable=self._fb_search_var, width=18).pack(side="left", fill="x", expand=True, padx=(4, 0))
        self._fb_path_var = tk.StringVar(value=str(Path.home()))
        fb_path_entry = ttk.Entry(fb_frame, textvariable=self._fb_path_var, width=30)
        fb_path_entry.pack(fill="x", padx=6, pady=1)
        fb_path_entry.bind("<Return>", lambda _: self._refresh_file_browser())
        fb_nav = tk.Frame(fb_frame, bg=PANEL)
        fb_nav.pack(fill="x", padx=6, pady=1)
        ttk.Button(fb_nav, text="▲ Up", width=5, style="MPC.TButton", command=lambda: self._fb_navigate("..")).pack(side="left")
        ttk.Button(fb_nav, text="⌂ Home", width=5, style="MPC.TButton", command=lambda: (self._fb_path_var.set(str(Path.home())), self._refresh_file_browser())).pack(side="left", padx=3)
        ttk.Button(fb_nav, text="↻", width=3, style="MPC.TButton", command=self._refresh_file_browser).pack(side="right")
        fb_scroll = ttk.Scrollbar(fb_frame, orient="vertical")
        self._fb_list = tk.Listbox(fb_frame, bg=PANEL_ALT, fg=SECONDARY, selectbackground=RED_DARK, selectforeground=TEXT, relief="flat", highlightthickness=0, activestyle="none", exportselection=False, yscrollcommand=fb_scroll.set)
        fb_scroll.config(command=self._fb_list.yview)
        self._fb_list.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=(2, 4))
        fb_scroll.pack(side="right", fill="y", pady=(2, 4))
        self._fb_list.bind("<Double-Button-1>", lambda _: self._on_fb_activate())
        fb_status = tk.Frame(fb_frame, bg=PANEL)
        fb_status.pack(fill="x", padx=6, pady=(0, 4))
        self._fb_count_var = tk.StringVar(value="No folder selected")
        tk.Label(fb_status, textvariable=self._fb_count_var, bg=PANEL, fg=MUTED, font=("TkDefaultFont", 7)).pack(side="left")
        ttk.Button(fb_status, text="+ Add all", width=7, style="MPC.TButton", command=self._fb_add_all).pack(side="right")

        db_frame = tk.Frame(rnb, bg=PANEL)
        rnb.add(db_frame, text="Database")
        db_top = tk.Frame(db_frame, bg=PANEL)
        db_top.pack(fill="x", padx=6, pady=(6, 2))
        self._db_search_var = tk.StringVar()
        self._db_search_var.trace_add("write", lambda *_: self._refresh_db_finder())
        tk.Label(db_top, text="⌕", bg=PANEL, fg=MUTED).pack(side="left")
        ttk.Entry(db_top, textvariable=self._db_search_var, width=18).pack(side="left", fill="x", expand=True, padx=(4, 0))
        db_filter_frame = tk.Frame(db_frame, bg=PANEL)
        db_filter_frame.pack(fill="x", padx=6, pady=1)
        self._db_filter_var = tk.StringVar(value="all")
        for fname, fval in [("All","all"), ("Video","video"), ("Audio","audio"), ("Fav","fav")]:
            ttk.Radiobutton(db_filter_frame, text=fname, variable=self._db_filter_var, value=fval, command=self._refresh_db_finder).pack(side="left", padx=1)
        db_scroll = ttk.Scrollbar(db_frame, orient="vertical")
        self._db_list = tk.Listbox(db_frame, bg=PANEL_ALT, fg=SECONDARY, selectbackground=RED_DARK, selectforeground=TEXT, relief="flat", highlightthickness=0, activestyle="none", exportselection=False, yscrollcommand=db_scroll.set)
        db_scroll.config(command=self._db_list.yview)
        self._db_list.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=(2, 4))
        db_scroll.pack(side="right", fill="y", pady=(2, 4))
        self._db_list.bind("<Double-Button-1>", lambda _: self._add_db_selected())
        self._db_list.bind("<Button-3>", self._db_context_menu)
        db_status = tk.Frame(db_frame, bg=PANEL)
        db_status.pack(fill="x", padx=6, pady=(0, 4))
        self._db_count_var = tk.StringVar(value="0 files · 0 shown")
        tk.Label(db_status, textvariable=self._db_count_var, bg=PANEL, fg=MUTED, font=("TkDefaultFont", 7)).pack(side="left")
        ttk.Button(db_status, text="↻ Refresh", width=7, style="MPC.TButton", command=self._refresh_db_finder).pack(side="right")
        ttk.Button(db_status, text="+ Add", width=4, style="MPC.TButton", command=self._add_db_selected).pack(side="right", padx=2)

        pl_frame = tk.Frame(rnb, bg=PANEL)
        rnb.add(pl_frame, text="Queue")
        self._pl_search_var = tk.StringVar()
        self._pl_search_var.trace_add("write", lambda *_: self._render_playlist())
        pl_search_frame = tk.Frame(pl_frame, bg=PANEL)
        pl_search_frame.pack(fill="x", padx=6, pady=(6, 2))
        tk.Label(pl_search_frame, text="⌕", bg=PANEL, fg=MUTED).pack(side="left")
        ttk.Entry(pl_search_frame, textvariable=self._pl_search_var, width=18).pack(side="left", fill="x", expand=True, padx=(4, 0))
        pl_scroll = ttk.Scrollbar(pl_frame, orient="vertical")
        self.queue = tk.Listbox(pl_frame, bg=PANEL_ALT, fg=SECONDARY, selectbackground=RED_DARK, selectforeground=TEXT, relief="flat", highlightthickness=0, activestyle="none", exportselection=False, yscrollcommand=pl_scroll.set)
        pl_scroll.config(command=self.queue.yview)
        self.queue.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=(0, 4))
        pl_scroll.pack(side="right", fill="y", pady=(0, 4))
        self.queue.bind("<Double-Button-1>", self._play_queue_item)
        self.queue.bind("<Return>", self._play_queue_item)
        self.queue.bind("<Button-3>", self._queue_context_menu)
        pl_actions = tk.Frame(pl_frame, bg=PANEL)
        pl_actions.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(pl_actions, text="↑", width=3, style="MPC.TButton", command=lambda: self.move_queue(-1)).pack(side="left")
        ttk.Button(pl_actions, text="↓", width=3, style="MPC.TButton", command=lambda: self.move_queue(1)).pack(side="left", padx=3)
        ttk.Button(pl_actions, text="Clear", style="MPC.TButton", command=self.clear_playlist).pack(side="right")
        ttk.Button(pl_actions, text="Save", style="MPC.TButton", command=self.save_playlist).pack(side="right", padx=3)
        pl_footer = tk.Frame(pl_frame, bg=PANEL)
        pl_footer.pack(fill="x", padx=6, pady=(0, 6))
        self._pl_count_var = tk.StringVar(value="0 items")
        tk.Label(pl_footer, textvariable=self._pl_count_var, bg=PANEL, fg=MUTED, font=("TkDefaultFont", 7)).pack(side="left")
        tk.Label(pl_footer, text="SHUFFLE · REPEAT", bg=PANEL, fg=MUTED, font=("TkDefaultFont", 7)).pack(side="right")

        rnb.select(2)  # Default to Queue tab (only after all tabs exist)

        diagnostics = tk.Frame(root, bg=BG); diagnostics.pack(fill="x", padx=18, pady=(10, 4))
        self.diagnostics = diagnostics
        for title, text in (("SEGMENTED PLAYBACK", "unavailable"), ("RESOURCE USE", "measuring…"), ("INTEGRITY MODE", "unavailable"), ("CASU SUPPORT", "Legacy backend")):
            card = tk.Frame(diagnostics, bg=PANEL_ALT, padx=12, pady=8); card.pack(side="left", fill="x", expand=True, padx=(0, 8))
            self._diagnostic_cards.append(card)
            tk.Label(card, text=title, bg=PANEL_ALT, fg=RED, font=("TkDefaultFont", 8, "bold")).pack(anchor="w")
            variable = tk.StringVar(value=text)
            self._diagnostic_vars[title] = variable
            tk.Label(card, textvariable=variable, bg=PANEL_ALT, fg=SECONDARY, font=("TkDefaultFont", 9)).pack(anchor="w", pady=(3, 0))
        statusbar = tk.Frame(root, bg=BG); statusbar.pack(fill="x", padx=18, pady=(4, 10))
        self.statusbar = statusbar
        tk.Label(statusbar, text="MPCASU 1.0.0", bg=BG, fg=SECONDARY).pack(side="left")
        tk.Label(statusbar, text="Optimized for performance and integrity", bg=BG, fg=MUTED).pack(side="left", padx=28)
        tk.Label(statusbar, textvariable=self.resource_status, bg=BG, fg=MUTED).pack(side="right")
        self.bind("<space>", lambda _event: self.pause())
        self.bind("<Control-o>", lambda _event: self.add_dialog())
        self.bind("<Control-l>", lambda _event: self.open_url_dialog())
        self.bind("<Control-i>", lambda _event: self.show_media_info())
        self.bind("<Control-t>", lambda _event: self.goto_time_dialog())
        self.bind("<Control-q>", lambda _event: self._shutdown())
        self.bind("<Key-m>", lambda _event: self.toggle_mute())
        self.bind("<Key-s>", lambda _event: self.stop())
        self.bind("<Key-p>", lambda _event: self.play_previous())
        self.bind("<Key-f>", lambda _event: self.toggle_fullscreen())
        self.bind("<Left>", lambda _event: self.seek_by(-10))
        self.bind("<Right>", lambda _event: self.seek_by(10))
        self.bind("<Up>", lambda _event: self.change_volume(5))
        self.bind("<Down>", lambda _event: self.change_volume(-5))
        self.bind("f", lambda _event: self.toggle_fullscreen())
        self.bind("F", lambda _event: self.toggle_fullscreen())
        self.bind("m", lambda _event: self.toggle_mute())
        self.bind("M", lambda _event: self.toggle_mute())
        self.bind("n", lambda _event: self.toggle_mini_player())
        self.bind("N", lambda _event: self.toggle_mini_player())
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

    def _make_audio_controls_menu(self, parent) -> None:
        _button, menu = self._menu_button(parent, "Audio mode")
        channels = tk.Menu(menu, tearoff=False, bg=PANEL_ALT, fg=TEXT,
                           activebackground=RED_DARK, activeforeground=TEXT)
        for label, value in (("Stereo", 1), ("Reverse stereo", 2),
                             ("Left only", 3), ("Right only", 4),
                             ("Dolby", 5)):
            channels.add_command(
                label=label, command=lambda label=label, value=value:
                self._apply_audio_channel(label, value))
        menu.add_cascade(label="Stereo mode", menu=channels)
        equalizer = tk.Menu(menu, tearoff=False, bg=PANEL_ALT, fg=TEXT,
                            activebackground=RED_DARK, activeforeground=TEXT)
        self._equalizer_menu = equalizer
        equalizer.configure(postcommand=self._refresh_equalizer_menu)
        menu.add_cascade(label="Equalizer preset", menu=equalizer)

    def _apply_audio_channel(self, label: str, value: int) -> None:
        if not self.backend or not hasattr(self.backend, "set_audio_channel"):
            self.status.set("Audio channel control is unavailable")
            return
        try:
            self.backend.set_audio_channel(value)
            self.status.set(f"Audio mode · {label}")
        except BackendError as exc:
            self.status.set(str(exc))

    def _refresh_equalizer_menu(self) -> None:
        menu = self._equalizer_menu
        menu.delete(0, "end")
        if not self.backend or not hasattr(self.backend, "equalizer_presets"):
            menu.add_command(label="Unavailable", state="disabled")
            return
        try:
            presets = self.backend.equalizer_presets()
        except BackendError:
            presets = ()
        if not presets:
            menu.add_command(label="Runtime reported no presets", state="disabled")
            return
        menu.add_command(label="Off", command=lambda: self._set_equalizer(None))
        menu.add_separator()
        for index, label in enumerate(presets):
            menu.add_command(label=label,
                             command=lambda index=index: self._set_equalizer(index))

    def _set_equalizer(self, preset: int | None) -> None:
        if not self.backend or not hasattr(self.backend, "set_equalizer_preset"):
            return
        try:
            name = self.backend.set_equalizer_preset(preset)
            self.status.set(f"Equalizer · {name}")
        except BackendError as exc:
            self.status.set(str(exc))

    def _make_chapter_menu(self, parent) -> None:
        _button, menu = self._menu_button(parent, "Chapters")
        self._chapter_menu = menu
        menu.configure(postcommand=self._refresh_chapters)

    def _make_sync_menu(self, parent) -> None:
        _button, menu = self._menu_button(parent, "Sync")
        menu.add_command(label="Audio delay…", command=self.set_audio_delay_dialog)
        menu.add_command(label="Subtitle delay…", command=self.set_subtitle_delay_dialog)

    def _make_video_controls_menu(self, parent) -> None:
        _button, menu = self._menu_button(parent, "Display")
        aspect = tk.Menu(menu, tearoff=False, bg=PANEL_ALT, fg=TEXT,
                         activebackground=RED_DARK, activeforeground=TEXT)
        for value in ("default", "16:9", "4:3", "1:1", "2.35:1"):
            aspect.add_command(label=value, command=lambda value=value:
                               self._apply_video_control("set_aspect_ratio", value,
                                                         f"Aspect ratio {value}"))
        menu.add_cascade(label="Aspect ratio", menu=aspect)
        crop = tk.Menu(menu, tearoff=False, bg=PANEL_ALT, fg=TEXT,
                       activebackground=RED_DARK, activeforeground=TEXT)
        for value in ("default", "16:9", "4:3", "1:1", "2.35:1"):
            crop.add_command(label=value, command=lambda value=value:
                             self._apply_video_control("set_crop_geometry", value,
                                                       f"Crop {value}"))
        menu.add_cascade(label="Crop", menu=crop)
        zoom = tk.Menu(menu, tearoff=False, bg=PANEL_ALT, fg=TEXT,
                       activebackground=RED_DARK, activeforeground=TEXT)
        for label, value in (("Fit", 0.0), ("0.5×", .5), ("1×", 1.0),
                             ("1.5×", 1.5), ("2×", 2.0)):
            zoom.add_command(label=label, command=lambda value=value, label=label:
                             self._apply_video_control("set_scale", value,
                                                       f"Video zoom {label}"))
        menu.add_cascade(label="Zoom", menu=zoom)
        deinterlace = tk.Menu(menu, tearoff=False, bg=PANEL_ALT, fg=TEXT,
                              activebackground=RED_DARK, activeforeground=TEXT)
        for value in ("off", "auto", "bob", "linear", "yadif", "yadif2x"):
            deinterlace.add_command(label=value, command=lambda value=value:
                                    self._apply_video_control("set_deinterlace", value,
                                                              f"Deinterlace {value}"))
        menu.add_cascade(label="Deinterlace", menu=deinterlace)
        menu.add_separator()
        menu.add_command(label="Previous title", command=lambda: self.change_title(-1))
        menu.add_command(label="Next title", command=lambda: self.change_title(1))

    def _make_bookmark_menu(self, parent) -> None:
        _button, menu = self._menu_button(parent, "Bookmarks")
        self._bookmark_menu = menu
        menu.configure(postcommand=self._refresh_bookmark_menu)

    def _apply_video_control(self, method: str, value, success: str) -> None:
        if not self.backend or not hasattr(self.backend, method):
            self.status.set("This video control is unavailable for the active backend")
            return
        try:
            getattr(self.backend, method)(value)
            self.status.set(success)
        except (BackendError, ValueError, OSError) as exc:
            self.status.set(str(exc))

    def change_title(self, delta: int) -> None:
        if not self.backend or not all(hasattr(self.backend, name)
                                       for name in ("title", "title_count", "set_title")):
            self.status.set("Title navigation is unavailable")
            return
        try:
            count = self.backend.title_count()
            if count < 2:
                self.status.set("No alternate titles reported"); return
            target = (self.backend.title() + int(delta)) % count
            self.backend.set_title(target)
            self.status.set(f"Title {target + 1}/{count}")
        except BackendError as exc:
            self.status.set(str(exc))

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
            self._choose_playlist_load()
        elif name == "Local Files":
            self.add_dialog()
        elif name == "Network Stream":
            self.open_url_dialog()
        elif name == "YouTube":
            self.open_youtube_dialog()
        elif name == "Spotify":
            self.open_spotify_dialog()
        elif name == "Live TV & EPG":
            self.show_epg_dialog()
        elif name == "Settings":
            self.show_settings_dialog()

    def _add_dialog_filter(self, label: str, pattern: str) -> None:
        paths = filedialog.askopenfilenames(filetypes=[(label, pattern), ("All files", "*.*")])
        self.add_files([Path(path) for path in paths])

    def _responsive_layout(self, event=None):
        if self._mini_mode:
            return
        if event is not None and getattr(event, "widget", self) is not self:
            return
        width = int(getattr(event, "width", self.winfo_width()))
        height = int(getattr(event, "height", self.winfo_height()))
        # Right panel is ALWAYS visible regardless of width
        if width >= 1000:
            if hasattr(self, "compact_nav") and self.compact_nav.winfo_ismapped():
                self.compact_nav.pack_forget()
            self.right_shell.pack(side="right", fill="y", padx=(10, 0),
                                  before=self.center_shell)
            if not self.left_shell.winfo_ismapped():
                self.left_shell.pack(side="left", fill="y", padx=(0, 10), before=self.canvas.master)
        else:
            self.right_shell.pack(side="right", fill="y", padx=(10, 0),
                                  before=self.center_shell)
            if self.left_shell.winfo_ismapped():
                self.left_shell.pack_forget()
            if hasattr(self, "compact_nav") and not self.compact_nav.winfo_ismapped():
                self.compact_nav.pack(side="left", fill="y", padx=(0, 8), before=self.canvas.master)
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
            "RESOURCE USE": energy,
        }
        for key, value in values.items():
            if value is not None and key in self._diagnostic_vars:
                self._diagnostic_vars[key].set(value)

    def _play_queue_item(self, _event=None):
        selected = self.queue.curselection()
        if selected:
            view = getattr(self, "_queue_view", None)
            index = (view[selected[0]]
                     if view and selected[0] < len(view) else selected[0])
            self.library.selection_clear(0, "end"); self.library.selection_set(index)
            self.canvas.focus_set(); self.play_selected()

    def _queue_context_menu(self, event):
        selected = self.queue.curselection()
        if not selected:
            return
        view = getattr(self, "_queue_view", None)
        idx = (view[selected[0]]
               if view and selected[0] < len(view) else selected[0])
        path = self.playlist[idx] if 0 <= idx < len(self.playlist) else None
        menu = tk.Menu(self.root, tearoff=0, bg=PANEL, fg=TEXT,
                       activebackground=RED_DARK, activeforeground=TEXT,
                       relief="flat")
        menu.add_command(label="Play", command=lambda: (
            self.library.selection_clear(0, "end"),
            self.library.selection_set(idx),
            self.canvas.focus_set(),
            self.play_selected()))
        if path:
            lib_item = self.media_library.get(path)
            is_fav = bool(lib_item.favorite) if lib_item else False
            fav_label = "★ Remove favorite" if is_fav else "☆ Mark as favorite"
            menu.add_command(label=fav_label,
                             command=lambda p=path, fav=is_fav: (
                                 self.media_library.set_favorite(p, not fav),
                                 self._render_playlist()))
        menu.add_separator()
        menu.add_command(label="Remove",
                         command=lambda: self.remove_selected_queue(selected))
        menu.tk_popup(event.x_root, event.y_root)

    def _render_playlist(self, selected: int | None = None) -> None:
        self.library.delete(0, "end")
        self.queue.delete(0, "end")
        query = ""
        if hasattr(self, "_pl_search_var"):
            query = self._pl_search_var.get().strip().lower()
        self._queue_view = []
        for index, path in enumerate(self.playlist_model.items):
            self.library.insert("end", str(path))
            if query and query not in str(path).lower():
                continue
            mtype = detect_media_type(path)
            etype = detect_entry_type(path)
            badge = {"local-file": mtype.upper(), "casu": "CASU", "mp5": "MP5",
                     "playlist": "PL", "http-stream": "STREAM", "youtube": "YT",
                     "spotify": "SPOTIFY", "rtsp-stream": "RTSP",
                     "rtmp-stream": "RTMP", "mms-stream": "MMS",
                     "udp-stream": "UDP", "network-stream": "STREAM"}.get(
                         etype, mtype.upper())
            if isinstance(path, str):
                # Remote URL row: show the resolved title, never the raw URL.
                label = f"[{badge}] {self._display_titles.get(path, path)}"
            else:
                fav_marker = ""
                lib_item = self.media_library.get(path)
                if lib_item and lib_item.favorite:
                    fav_marker = "★ "
                label = f"{fav_marker}[{badge}] {path.name}"
            self.queue.insert("end", label)
            self._queue_view.append(index)
        if selected is not None and 0 <= selected < len(self.playlist_model):
            self.library.selection_set(selected); self.library.see(selected)
            self.queue.selection_set(selected); self.queue.see(selected)
        self._sync_queue_empty()

    def move_queue(self, delta: int) -> None:
        """Reorder the real playlist and keep its display models aligned."""
        selected = self.queue.curselection()
        if not selected:
            return
        view = getattr(self, "_queue_view", None)
        if view is not None and len(view) != len(self.playlist_model):
            self.status.set("Clear the queue search to reorder items")
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

    def remove_selected_queue(self, indices) -> None:
        if not indices:
            return
        for idx in sorted(indices, reverse=True):
            if 0 <= idx < len(self.playlist):
                self.playlist_model.remove([idx])
        self._render_playlist()

    def toggle_shuffle(self) -> None:
        self._shuffle = not self._shuffle
        self.shuffle_button.configure(text=f"Shuffle {'on' if self._shuffle else 'off'}")
        self.status.set(f"Shuffle {'enabled' if self._shuffle else 'disabled'}")

    def cycle_repeat(self) -> None:
        values = ("off", "all", "one")
        self._repeat_mode = values[(values.index(self._repeat_mode) + 1) % len(values)]
        self.repeat_button.configure(text=f"Repeat {self._repeat_mode}")
        self.status.set(f"Repeat mode: {self._repeat_mode}")

    def play_next(self, *, automatic: bool = False):
        """Advance to the next queued media item."""
        if automatic and self._repeat_mode == "one" and self.current:
            self.position.set(0.0); self.seek_restart(); return
        selected = self.library.curselection()
        current_index = self.playlist_model.index_of(self.current) if self.current else None
        index = selected[0] if selected else (-1 if current_index is None else current_index)
        if not len(self.playlist_model):
            self.status.set("Playlist is empty"); return
        if self._shuffle and len(self.playlist_model) > 1:
            choices = [value for value in range(len(self.playlist_model)) if value != index]
            target = self._random.choice(choices)
        else:
            target = index + 1
        if target >= len(self.playlist_model) and self._repeat_mode == "all":
            target = 0
        if target >= len(self.playlist_model):
            self.status.set("End of playlist")
            return
        self.library.selection_clear(0, "end")
        self.library.selection_set(target)
        self.library.see(target)
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

    def add_folder_dialog(self) -> None:
        selected = filedialog.askdirectory(mustexist=True, parent=self)
        if not selected: return
        root = Path(selected).expanduser().resolve()
        self.status.set("Scanning media folder…")
        def worker() -> None:
            values: list[Path] = []
            try:
                for item in root.rglob("*"):
                    if not item.is_file(): continue
                    resolved = item.resolve()
                    try: resolved.relative_to(root)
                    except ValueError: continue
                    values.append(resolved)
                    if len(values) > 10_000:
                        raise PlaylistError("folder contains more than 10000 files")
            except (OSError, PlaylistError) as exc:
                self.after(0, lambda exc=exc: self.status.set(f"Folder scan failed: {exc}")); return
            values.sort()
            self.after(0, lambda: (self.add_files(values),
                                   self.status.set(f"Folder added · {len(values)} files")))
        threading.Thread(target=worker, name="mpcasu-folder-scan", daemon=True).start()

    def show_capture_dialog(self) -> None:
        dialog = tk.Toplevel(self); dialog.bind("<Escape>", lambda _event, _dialog=dialog: _dialog.destroy()); dialog.title("MPCASU · Disc and capture")
        dialog.configure(bg=BG); dialog.transient(self)
        tk.Label(dialog, text="DISC · CAMERA · SCREEN · AUDIO CAPTURE", bg=BG,
                 fg=RED, font=("TkDefaultFont", 10, "bold")).pack(anchor="w", padx=16, pady=(16, 6))
        value = tk.StringVar(value="/dev/sr0")
        entry = ttk.Entry(dialog, textvariable=value, width=58); entry.pack(fill="x", padx=16)
        options = tk.Frame(dialog, bg=BG); options.pack(fill="x", padx=16, pady=12)
        def open_mrl(prefix: str, default: str = "", *, use_device: bool = True) -> None:
            location = (value.get().strip() if use_device else default) or default
            if "\0" in location or len(location.encode("utf-8")) > 4096:
                messagebox.showerror("MPCASU", "Capture source is invalid", parent=dialog); return
            mrl = prefix + location if prefix else location
            dialog.destroy(); self._resolve_and_open_external_source(mrl, display_label=mrl)
        for label, prefix, default, use_device in (
                ("DVD", "dvd://", "/dev/sr0", True),
                ("Audio CD", "cdda://", "/dev/sr0", True),
                ("Camera", "v4l2://", "/dev/video0", False),
                ("Screen", "", "screen://", False),
                ("Pulse input", "", "pulse://", False)):
            ttk.Button(options, text=label, style="MPC.TButton",
                       command=lambda prefix=prefix, default=default, use_device=use_device:
                       open_mrl(prefix, default, use_device=use_device)).pack(side="left", padx=3)
        ttk.Button(dialog, text="Open custom MRL", style="MPC.TButton",
                   command=lambda: open_mrl("", "", use_device=True)).pack(
                       anchor="e", padx=16, pady=(0, 8))
        tk.Label(dialog, text="Enter a device path or complete libVLC MRL. Availability depends on installed VLC access modules.",
                 bg=BG, fg=MUTED, wraplength=520, justify="left").pack(fill="x", padx=16, pady=(0, 16))

    def show_settings_dialog(self):
        dialog = tk.Toplevel(self); dialog.bind("<Escape>", lambda _event, _dialog=dialog: _dialog.destroy())
        dialog.title("MPCASU · Options")
        dialog.configure(bg=BG)
        dialog.transient(self)
        dialog.geometry("560x600")
        settings = self.settings_store.load()

        body = tk.Frame(dialog, bg=BG)
        body.pack(fill="both", expand=True)

        frame = tk.Frame(body, bg=BG)
        frame.pack(fill="x", padx=16, pady=(16, 4))
        tk.Label(frame, text="PLAYBACK", bg=BG, fg=RED,
                 font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
        resume_var = tk.BooleanVar(value=settings.resume_playback)
        tk.Checkbutton(frame, text="Resume playback on startup", variable=resume_var,
                       bg=BG, fg=TEXT, selectcolor=PANEL_ALT,
                       activebackground=BG, activeforeground=TEXT).pack(anchor="w")
        vol_var = tk.IntVar(value=settings.volume)
        vol_frame = tk.Frame(frame, bg=BG)
        vol_frame.pack(fill="x", pady=4)
        tk.Label(vol_frame, text="Volume", bg=BG, fg=SECONDARY).pack(side="left")
        tk.Scale(vol_frame, from_=0, to=200, orient="horizontal", variable=vol_var,
                 bg=BG, fg=TEXT, troughcolor=PANEL_ALT, highlightthickness=0,
                 length=320).pack(side="left", fill="x", expand=True, padx=(8, 0))

        frame2 = tk.Frame(body, bg=BG)
        frame2.pack(fill="x", padx=16, pady=(16, 4))
        tk.Label(frame2, text="VISUALIZER", bg=BG, fg=RED,
                 font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
        viz_var = tk.StringVar(value=settings.visualizer)
        for label, value in (("Spectrum", "spectrum"), ("Waveform", "waveform"),
                             ("Both", "both"), ("Off", "off")):
            tk.Radiobutton(frame2, text=label, variable=viz_var, value=value,
                           bg=BG, fg=TEXT, selectcolor=PANEL_ALT,
                           activebackground=BG, activeforeground=TEXT).pack(anchor="w")

        frame3 = tk.Frame(body, bg=BG)
        frame3.pack(fill="x", padx=16, pady=(16, 4))
        tk.Label(frame3, text="CACHE", bg=BG, fg=RED,
                 font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
        cache_var = tk.IntVar(value=settings.cache_limit_mib)
        cache_frame = tk.Frame(frame3, bg=BG)
        cache_frame.pack(fill="x", pady=4)
        tk.Label(cache_frame, text="Limit (MiB)", bg=BG, fg=SECONDARY).pack(side="left")
        tk.Scale(cache_frame, from_=0, to=4096, orient="horizontal", variable=cache_var,
                 bg=BG, fg=TEXT, troughcolor=PANEL_ALT, highlightthickness=0,
                 length=320).pack(side="left", fill="x", expand=True, padx=(8, 0))

        def clear_cache():
            import shutil
            import tempfile
            cleared = 0
            for candidate in (Path(tempfile.gettempdir()) / "yt-dlp",
                              Path.home() / ".cache" / "yt-dlp"):
                if candidate.is_dir():
                    shutil.rmtree(candidate, ignore_errors=True)
                    cleared += 1
            self.status.set("Cleared yt-dlp cache" if cleared
                            else "No yt-dlp cache found")
        ttk.Button(frame3, text="Clear yt-dlp temp cache", style="MPC.TButton",
                   command=clear_cache).pack(anchor="w", pady=4)

        frame4 = tk.Frame(body, bg=BG)
        frame4.pack(fill="x", padx=16, pady=(16, 4))
        tk.Label(frame4, text="DATABASE", bg=BG, fg=RED,
                 font=("TkDefaultFont", 9, "bold")).pack(anchor="w")

        def refresh_db():
            self.refresh_watched_folders()
            self._refresh_db_finder()
            self.status.set("Database refreshed from watched folders")
        ttk.Button(frame4, text="Refresh watched folders", style="MPC.TButton",
                   command=refresh_db).pack(anchor="w", pady=4)

        frame5 = tk.Frame(body, bg=BG)
        frame5.pack(fill="x", padx=16, pady=(16, 4))
        tk.Label(frame5, text="LEGAL NOTICES", bg=BG, fg=RED,
                 font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
        consent_var = tk.BooleanVar(value=settings.ytdlp_consent)
        tk.Checkbutton(frame5,
                       text="I understand that yt-dlp (GNU GPL) resolves YouTube and\n"
                            "Spotify stream URLs for personal use only. Resolved URLs\n"
                            "are temporary and are never stored or redistributed.",
                       variable=consent_var, bg=BG, fg=SECONDARY,
                       selectcolor=PANEL_ALT, activebackground=BG,
                       activeforeground=SECONDARY, justify="left").pack(anchor="w")

        btn_frame = tk.Frame(dialog, bg=BG)
        btn_frame.pack(fill="x", padx=16, pady=12)

        def apply_settings():
            new_settings = PlayerSettings(
                volume=vol_var.get(),
                muted=settings.muted,
                rate=settings.rate,
                audio_device=settings.audio_device,
                watched_folders=settings.watched_folders,
                ytdlp_consent=consent_var.get(),
                visualizer=viz_var.get(),
                resume_playback=resume_var.get(),
                cache_limit_mib=cache_var.get(),
            ).validated()
            self.settings_store.save(new_settings)
            self._volume = new_settings.volume
            if self.backend:
                try:
                    self._volume = self.backend.set_volume(self._volume)
                except BackendError:
                    pass
            self._visualizer_mode = new_settings.visualizer
            self._draw_visualizer()
            dialog.destroy()
            self.status.set("Settings saved")
        ttk.Button(btn_frame, text="Apply", style="MPC.TButton",
                   command=apply_settings).pack(side="right")
        ttk.Button(btn_frame, text="Cancel", style="MPC.TButton",
                   command=dialog.destroy).pack(side="right", padx=8)

    def _ytdlp_consent_ok(self) -> bool:
        """Shared yt-dlp consent gate (GPL notice, personal use only)."""
        settings = self.settings_store.load()
        if settings.ytdlp_consent:
            return True
        if not messagebox.askyesno(
                "MPCASU · Legal Notice",
                "YouTube and Spotify playback and search require yt-dlp to "
                "resolve stream URLs.\n\n"
                "yt-dlp is open-source software (GNU GPL). Stream URLs are "
                "resolved\n temporarily and are never stored or redistributed.\n\n"
                "This feature is intended for personal use only.\n\n"
                "Do you accept these terms?",
                icon="question", parent=self):
            return False
        self.settings_store.save(replace(settings, ytdlp_consent=True))
        return True

    def open_youtube_dialog(self):
        self._open_search_dialog("MPCASU · YouTube", "youtube",
                                 "URL or search term — e.g. "
                                 "https://www.youtube.com/watch?v=…")

    def open_spotify_dialog(self):
        self._open_search_dialog("MPCASU · Spotify", "spotify",
                                 "URL or search term — e.g. "
                                 "https://open.spotify.com/track/…")

    def _open_search_dialog(self, title: str, source: str, placeholder: str) -> None:
        """YouTube/Spotify dialog: direct URL playback plus yt-dlp search."""
        from casu.search import SearchError, search_music, search_youtube
        dialog = tk.Toplevel(self); dialog.bind("<Escape>", lambda _event, _dialog=dialog: _dialog.destroy())
        dialog.title(title)
        dialog.configure(bg=BG)
        dialog.transient(self)
        dialog.geometry("780x580")
        kind_label = "YouTube" if source == "youtube" else "Spotify"
        tk.Label(dialog, text=f"{kind_label} URL or search term:", bg=BG, fg=TEXT,
                 font=("TkDefaultFont", 11, "bold")).pack(anchor="w", padx=16, pady=(16, 4))
        tk.Label(dialog, text=placeholder, bg=BG, fg=SECONDARY).pack(anchor="w", padx=16, pady=(0, 8))
        value = tk.StringVar()
        entry = ttk.Entry(dialog, textvariable=value, width=72)
        entry.pack(fill="x", padx=16); entry.focus_set()
        dialog_status = tk.StringVar(value="Search uses yt-dlp (GNU GPL) · personal use only")
        results: list = []
        thumb_images: dict = {}
        style = ttk.Style(dialog)
        style.configure("YT.Treeview", background=PANEL_ALT, foreground=SECONDARY,
                         fieldbackground=PANEL_ALT, rowheight=56, font=("TkDefaultFont", 9))
        style.map("YT.Treeview", background=[("selected", RED_DARK)],
                  foreground=[("selected", TEXT)])
        columns = ("title", "channel", "duration")
        tree = ttk.Treeview(dialog, columns=columns, show="tree headings",
                            selectmode="browse", style="YT.Treeview", height=12)
        tree.heading("#0", text=""); tree.column("#0", width=80, minwidth=80, stretch=False)
        tree.heading("title", text="Title"); tree.column("title", minwidth=200, stretch=True)
        tree.heading("channel", text="Channel"); tree.column("channel", width=180, minwidth=100, stretch=False)
        tree.heading("duration", text="Length"); tree.column("duration", width=70, minwidth=60, stretch=False)
        tree.pack(fill="both", expand=True, padx=16, pady=(10, 4))

        def open_typed():
            text = value.get().strip()
            if not text:
                return
            if self._is_expandable_youtube(text):
                dialog.destroy()
                self._expand_youtube_input(text)
                return
            if text.startswith(("http://", "https://")):
                dialog.destroy()
                self._queue_and_play(text)
                return
            run_search()

        def play_selected_result(_event=None):
            sel = tree.selection()
            if not sel:
                return
            iid = sel[0]
            idx = tree.index(iid)
            if idx >= len(results):
                return
            result = results[idx]
            dialog.destroy()
            self._queue_and_play(result.url, result.title)

        def run_search():
            query = value.get().strip()
            if not query:
                dialog_status.set("Type a search term first")
                return
            if not self._ytdlp_consent_ok():
                dialog_status.set("Search requires yt-dlp consent")
                return
            dialog_status.set(f"Searching {kind_label} via yt-dlp…")
            for item in tree.get_children():
                tree.delete(item)
            thumb_images.clear()

            def present(payload):
                if dialog.winfo_exists() == 0:
                    return
                kind, data = payload
                if kind == "error":
                    dialog_status.set(f"Search failed: {data}")
                    return
                results.clear()
                results.extend(data)
                for row, item in enumerate(data):
                    duration = (f"{int(item.duration // 60)}:{int(item.duration % 60):02d}"
                                if item.duration else "live")
                    tree.insert("", "end", values=(item.title, item.uploader or "unknown", duration))
                dialog_status.set(f"{len(data)} results — double-click to play")
                _load_dialog_thumbs(data)

            holder: dict = {}

            def worker():
                try:
                    engine = search_youtube if source == "youtube" else search_music
                    found = engine(query, limit=12)
                except Exception as exc:
                    holder["payload"] = ("error", str(exc))
                else:
                    holder["payload"] = ("ok", found)

            threading.Thread(target=worker, daemon=True).start()

            def poll():
                if dialog.winfo_exists() == 0:
                    return
                if "payload" in holder:
                    present(holder["payload"])
                else:
                    dialog.after(150, poll)

            dialog.after(150, poll)

        def _load_dialog_thumbs(data):
            def worker():
                import io, urllib.request
                from PIL import Image, ImageTk
                for idx, item in enumerate(data):
                    url = getattr(item, "thumbnail", "") or ""
                    if not url.startswith("http"):
                        continue
                    try:
                        req = urllib.request.Request(url, headers={"User-Agent": "MPCASU/1.0"})
                        raw = urllib.request.urlopen(req, timeout=8).read(512 * 1024)
                        pil = Image.open(io.BytesIO(raw)).convert("RGBA").resize((72, 40), Image.LANCZOS)
                        img = ImageTk.PhotoImage(pil)
                        thumb_images[idx] = img
                        dialog.after(0, lambda i=idx, im=img: _apply_thumb(i, im))
                    except Exception:
                        continue

            def _apply_thumb(idx, img):
                iid = None
                for child in tree.get_children():
                    if tree.index(child) == idx:
                        iid = child
                        break
                if iid:
                    tree.item(iid, image=img)

            threading.Thread(target=worker, daemon=True).start()

        ttk.Button(dialog, text=f"Play / search", style="MPC.TButton",
                   command=open_typed).pack(anchor="e", padx=16, pady=(0, 6))
        tree.bind("<Double-Button-1>", play_selected_result)
        tree.bind("<Return>", play_selected_result)
        entry.bind("<Return>", lambda _event: open_typed())
        tk.Label(dialog, textvariable=dialog_status, bg=BG, fg=MUTED,
                 font=("TkDefaultFont", 8)).pack(anchor="w", padx=16, pady=(2, 10))

    def open_url_dialog(self):
        dialog = tk.Toplevel(self); dialog.bind("<Escape>", lambda _event, _dialog=dialog: _dialog.destroy())
        dialog.title("Open network URL")
        dialog.configure(bg=BG)
        dialog.transient(self)
        tk.Label(dialog, text="YouTube, HTTP(S), HLS, RTSP, RTP, UDP, FTP or SMB URL", bg=BG, fg=SECONDARY).pack(anchor="w", padx=16, pady=(16, 6))
        value = tk.StringVar()
        entry = ttk.Entry(dialog, textvariable=value, width=64)
        entry.pack(fill="x", padx=16); entry.focus_set()
        def open_source():
            url = value.get().strip()
            if url:
                dialog.destroy()
                self._resolve_and_open_external_source(url)
        ttk.Button(dialog, text="Open", style="MPC.TButton", command=open_source).pack(anchor="e", padx=16, pady=14)
        entry.bind("<Return>", lambda _event: open_source())

    def _is_expandable_youtube(self, text: str) -> bool:
        from casu.search import split_youtube_input, youtube_playlist_id
        tokens = split_youtube_input(text)
        if not tokens:
            return False
        youtube = [t for t in tokens if is_youtube_url(t)]
        if not youtube:
            return False
        return len(youtube) > 1 or any(youtube_playlist_id(t) for t in youtube)

    def _expand_youtube_input(self, text: str) -> None:
        """Qt parity: expand a playlist and/or several pasted YouTube videos
        into individual queue entries and start the first one."""
        from casu.search import SearchError, expand_youtube_input
        holder: dict = {}

        def worker() -> None:
            try:
                found = expand_youtube_input(text)
            except SearchError as exc:
                holder["error"] = str(exc)
            else:
                holder["found"] = found

        threading.Thread(target=worker, daemon=True).start()

        def poll() -> None:
            if "found" not in holder and "error" not in holder:
                self.after(150, poll)
                return
            if "error" in holder:
                self.status.set(f"Could not expand YouTube: {holder['error']}")
                messagebox.showerror("MPCASU", holder["error"])
                return
            found = holder["found"]
            if not found:
                return
            urls: list = []
            titles: dict = {}
            for item in found:
                url = str(getattr(item, "url", "") or "").strip()
                if not url:
                    continue
                title = str(getattr(item, "title", "") or "").strip()
                if title and title != url:
                    titles[url] = title
                urls.append(url)
            if not urls:
                return
            self._display_titles.update(titles)
            try:
                self.playlist_model.add(urls)
            except PlaylistError:
                pass
            self._render_playlist()
            self._resolve_and_open_external_source(
                urls[0], display_label=titles.get(urls[0], urls[0]))
            for url in urls:
                self._tag_queue_title(url)
            self.status.set(f"{len(urls)} video(s) added to the queue — playing now")

        self.after(150, poll)

    def _queue_and_play(self, url: str, label: str = "") -> None:
        """Qt parity (_queue_and_play): the URL lands IN the queue (with its
        title), the queue re-renders, then playback starts through the
        normal resolve path."""
        if label:
            self._display_titles[url] = label
        try:
            self.playlist_model.add((url,))
        except PlaylistError:
            pass
        self._render_playlist()
        self._resolve_and_open_external_source(
            url, display_label=self._display_titles.get(url, label or url))
        self._tag_queue_title(url)

    def _tag_queue_title(self, url: str) -> None:
        """Qt parity (_tag_queue_title): fetch the real YouTube title in the
        background and rewrite the queue row + NOW PLAYING."""
        if not is_youtube_url(url):
            return
        holder: dict = {}

        def worker() -> None:
            try:
                proc = subprocess.run(
                    ["yt-dlp", "--no-warnings", "--no-playlist",
                     "--skip-download", "--print", "%(title)s", url],
                    capture_output=True, text=True, timeout=25)
                title = (proc.stdout.strip().splitlines() or [""])[0].strip() \
                    if proc.returncode == 0 else ""
            except Exception:  # noqa: BLE001 - title tagging is best-effort
                title = ""
            holder["title"] = title

        threading.Thread(target=worker, daemon=True).start()

        def poll() -> None:
            if "title" not in holder:
                self.after(150, poll)
                return
            title = holder["title"]
            if not title:
                return
            self._display_titles[url] = title
            self._render_playlist()
            if self._network_source and url in self._network_source:
                self.now_playing.configure(text=title.upper())
                self._network_display = title

        self.after(150, poll)

    def _resolve_and_open_external_source(self, source: str, *,
                                          display_label: str | None = None,
                                          channel: StreamChannel | None = None) -> None:
        """Resolve web pages off the Tk thread, then hand a direct URL to libVLC."""
        if is_youtube_url(source) or is_spotify_url(source):
            if not self._ytdlp_consent_ok():
                self.status.set("YouTube/Spotify playback requires consent")
                return
        self._location_generation += 1
        generation = self._location_generation
        self._stream_channel = channel
        self.status.set("Resolving network media…")
        def worker() -> None:
            try:
                resolved = resolve_media_location(source)
            except LocationResolutionError as exc:
                def failed(exc=exc) -> None:
                    if generation != self._location_generation:
                        return
                    self.status.set(f"Could not resolve network source: {exc}")
                    messagebox.showerror("MPCASU", str(exc))
                self.after(0, failed)
                return
            def present() -> None:
                if generation == self._location_generation:
                    self._open_external_source(resolved,
                                               display_label=display_label or source)
            self.after(0, present)
        threading.Thread(target=worker, daemon=True).start()

    def _open_external_source(self, source: str, *, display_label: str | None = None):
        self.stop()
        self._end_handled = False
        self.current = None
        self._network_source = source
        self._network_display = display_label or source
        self._waveform_generation += 1
        self._waveform = ()
        self._spectrum = ()
        self._ab_start = self._ab_end = None
        self._presentation_mode = "UNKNOWN"
        visible_source = display_media_source(display_label or source)
        self.now_playing.configure(text=visible_source)
        try:
            self._try_libvlc_network(source, visible_source)
        except (BackendError, OSError) as exc:
            self.status.set(f"libVLC failed ({exc})")
            try:
                self._try_ffmpeg_network(source, visible_source)
            except Exception as fb_exc:
                self._retire_backend()
                self.status.set(f"Could not open network source: {fb_exc}")
                self._toast("Network source could not be opened")
                messagebox.showerror("MPCASU", str(fb_exc))

    def _try_libvlc_network(self, source: str, visible_source: str) -> None:
        plugin_path = discover_vlc_plugin_path()
        if plugin_path:
            os.environ.setdefault("VLC_PLUGIN_PATH", plugin_path)
        self.backend = LibVLCBackend(self.canvas)
        self.backend.on_event = self._backend_event
        self.backend.open_source(source)
        self.controller.attach(self.backend, visible_source)
        self.controller.play()
        self._apply_playback_rate()
        self._apply_backend_settings()
        self._set_diagnostics(support="Legacy network backend", integrity="unavailable", segmented="unavailable", energy="unavailable \u2014 not measured")
        self.duration = self.backend.duration()
        self.timeline.configure(to=max(self.duration, 1.0))
        self._draw_chapter_markers()
        capabilities = self.backend.capabilities()
        self.status.set(f"Playing network source \u00b7 {capabilities.get('version', 'libVLC')} \u00b7 timing owned by libVLC")
        backend = self.backend
        self.after(20_000, lambda: self._check_network_playback_start(backend))

    def _try_ffmpeg_network(self, source: str, visible_source: str) -> None:
        # MPCASU never launches an external player window.  When libVLC cannot
        # open a network source the stream is refused in-process with an
        # actionable message instead of handing control to ffplay/mpv.
        raise BackendError(
            "network source refused: libVLC could not open it and MPCASU "
            "does not start external players (check the URL, codec support "
            "and network access)")

    def _check_network_playback_start(self, expected_backend) -> None:
        """Fail a stream that never leaves buffering without touching a newer one."""
        if not expected_backend or self.backend is not expected_backend or self._paused:
            return
        state = expected_backend.state()
        progressed = expected_backend.position() > 0.05
        active = (expected_backend.is_actively_playing()
                  if hasattr(expected_backend, "is_actively_playing") else False)
        if state in {PlaybackState.LOADING, PlaybackState.READY} and not (progressed or active):
            self._retire_backend(expected_backend)
            self._paused = True
            self.status.set("Network stream timed out while buffering")
            self._set_diagnostics(support="stream buffering timeout")

    def _play_stream_channel(self, channel: StreamChannel) -> None:
        self._last_epg_minute = None
        self._resolve_and_open_external_source(channel.url,
                                               display_label=channel.name,
                                               channel=channel)

    def show_epg_dialog(self) -> None:
        """Open a real Extended-M3U/XMLTV browser with current/next programmes."""
        dialog = tk.Toplevel(self); dialog.bind("<Escape>", lambda _event, _dialog=dialog: _dialog.destroy()); dialog.title("MPCASU · Live TV & EPG")
        dialog.configure(bg=BG); dialog.transient(self); dialog.geometry("980x620")
        toolbar = tk.Frame(dialog, bg=BG, padx=14, pady=12); toolbar.pack(fill="x")
        search = tk.StringVar(); guide_hint = tk.StringVar(value="No XMLTV guide loaded")
        channels: list[StreamChannel] = []
        visible: list[StreamChannel] = []
        body = tk.Frame(dialog, bg=BG); body.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        left = tk.Frame(body, bg=PANEL); left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=PANEL, width=420); right.pack(side="right", fill="both", padx=(10, 0)); right.pack_propagate(False)
        tk.Label(left, text="CHANNELS", bg=PANEL, fg=RED,
                 font=("TkDefaultFont", 10, "bold")).pack(anchor="w", padx=12, pady=(12, 5))
        channel_list = tk.Listbox(left, bg=PANEL_ALT, fg=TEXT,
                                  selectbackground=RED_DARK, selectforeground=TEXT,
                                  relief="flat", exportselection=False)
        channel_list.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        tk.Label(right, text="PROGRAM GUIDE", bg=PANEL, fg=RED,
                 font=("TkDefaultFont", 10, "bold")).pack(anchor="w", padx=12, pady=(12, 5))
        now_label = tk.Label(right, text="Select a channel", bg=PANEL_ALT, fg=TEXT,
                             justify="left", anchor="nw", wraplength=380, padx=12, pady=10)
        now_label.pack(fill="x", padx=10)
        schedule = tk.Listbox(right, bg=PANEL, fg=SECONDARY,
                              selectbackground=RED_DARK, relief="flat")
        schedule.pack(fill="both", expand=True, padx=10, pady=8)
        tk.Label(right, textvariable=guide_hint, bg=PANEL, fg=MUTED,
                 anchor="w", wraplength=380).pack(fill="x", padx=12, pady=(0, 8))

        def refresh_channels(*_args) -> None:
            needle = search.get().strip().casefold()
            visible[:] = [item for item in channels if not needle or needle in
                          f"{item.name} {item.group} {item.epg_id}".casefold()]
            channel_list.delete(0, "end")
            for item in visible:
                group = f"  ·  {item.group}" if item.group else ""
                channel_list.insert("end", f"{item.name}{group}")

        def selected_channel() -> StreamChannel | None:
            selected = channel_list.curselection()
            return visible[selected[0]] if selected and selected[0] < len(visible) else None

        def refresh_schedule(_event=None) -> None:
            channel = selected_channel(); schedule.delete(0, "end")
            if channel is None:
                now_label.configure(text="Select a channel"); return
            identifier = channel.epg_id
            current, following = self._epg_guide.now_next(identifier) if identifier else (None, None)
            if current:
                minutes = max(0, int((current.stop - current.start).total_seconds() // 60))
                now_label.configure(text=f"NOW · {current.title}\n{current.start.astimezone():%H:%M}–{current.stop.astimezone():%H:%M} · {minutes} min\n{current.description}")
            else:
                now_label.configure(text=f"{channel.name}\nNo current programme in the loaded guide")
            for item in self._epg_guide.schedule(identifier):
                schedule.insert("end", f"{item.start.astimezone():%a %H:%M}  {item.title}")
            if following:
                guide_hint.set(f"Next: {following.start.astimezone():%H:%M} · {following.title}")

        def install_catalog(catalog: StreamCatalog, label: str) -> None:
            self._stream_catalog = catalog; channels[:] = list(catalog.channels)
            refresh_channels()
            suggestion = f" · guide advertised: {catalog.epg_urls[0]}" if catalog.epg_urls else ""
            guide_hint.set(f"{len(channels)} channels loaded from {label}{suggestion}")

        def load_catalog_file() -> None:
            path = filedialog.askopenfilename(parent=dialog,
                filetypes=[("Extended M3U", "*.m3u *.m3u8"), ("All files", "*.*")])
            if not path: return
            try: install_catalog(load_m3u(path), Path(path).name)
            except EpgError as exc: messagebox.showerror("MPCASU EPG", str(exc), parent=dialog)

        def load_guide_file() -> None:
            path = filedialog.askopenfilename(parent=dialog,
                filetypes=[("XMLTV guide", "*.xml *.xmltv *.tv"), ("All files", "*.*")])
            if not path: return
            try:
                self._epg_guide = load_xmltv(path)
                guide_hint.set(f"{len(self._epg_guide.programmes)} programmes loaded")
                refresh_schedule()
            except EpgError as exc: messagebox.showerror("MPCASU EPG", str(exc), parent=dialog)

        def load_remote(kind: str) -> None:
            value = simpledialog.askstring("MPCASU EPG", f"HTTP(S) {kind} URL:", parent=dialog)
            if not value: return
            guide_hint.set(f"Loading {kind}…")
            def worker() -> None:
                try:
                    result = fetch_m3u(value) if kind == "playlist" else fetch_xmltv(value)
                except EpgError as exc:
                    self.after(0, lambda: messagebox.showerror("MPCASU EPG", str(exc), parent=dialog)); return
                def present() -> None:
                    if not dialog.winfo_exists(): return
                    if kind == "playlist": install_catalog(result, "remote URL")
                    else:
                        self._epg_guide = result
                        guide_hint.set(f"{len(result.programmes)} programmes loaded")
                        refresh_schedule()
                self.after(0, present)
            threading.Thread(target=worker, name="mpcasu-epg-fetch", daemon=True).start()

        ttk.Entry(toolbar, textvariable=search, width=30).pack(side="left", padx=(0, 8))
        for text_value, command in (("Open M3U", load_catalog_file),
                                    ("M3U URL", lambda: load_remote("playlist")),
                                    ("Open XMLTV", load_guide_file),
                                    ("XMLTV URL", lambda: load_remote("guide"))):
            ttk.Button(toolbar, text=text_value, style="MPC.TButton", command=command).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Play channel", style="MPC.TButton",
                   command=lambda: selected_channel() and self._play_stream_channel(selected_channel())).pack(side="right")
        channel_list.bind("<<ListboxSelect>>", refresh_schedule)
        channel_list.bind("<Double-Button-1>", lambda _event: selected_channel() and self._play_stream_channel(selected_channel()))
        search.trace_add("write", refresh_channels)
        channels[:] = list(self._stream_catalog.channels); refresh_channels()

    def add_files(self, paths: list):
        # A media file already covered by a playlist in the selection must not
        # be added a second time as a top-level row (Choose files double-load).
        playlists: list[Path] = []
        plain: list[Path] = []
        remote: list[str] = []
        for value in paths:
            if isinstance(value, str):
                # Remote URL rows (queue/session restore) stay strings.
                remote.append(value)
                continue
            path = value.expanduser().resolve()
            if path.is_file() and path.suffix.lower() in PLAYLIST_SUFFIXES:
                playlists.append(path)
            elif path.is_file():
                plain.append(path)
        covered: set[str] = set()
        for playlist in playlists:
            try:
                loaded = load_playlist_file(playlist)
                covered.update(str(item) for item in loaded.items)
            except (PlaylistError, OSError, ValueError):
                pass
        added: list[Path] = []
        for path in playlists + plain:
            if path in added or str(path) in covered:
                continue
            try:
                if self.playlist_model.add((path,), existing_only=True):
                    added.append(path)
            except PlaylistError as exc:
                self.status.set(str(exc)); break
        for url in remote:
            try:
                self.playlist_model.add((url,))
            except PlaylistError:
                pass
        try:
            self.media_library.upsert_many(added)
        except (OSError, ValueError):
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
        dialog = tk.Toplevel(self); dialog.bind("<Escape>", lambda _event, _dialog=dialog: _dialog.destroy())
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

        def _lib_context_menu(event):
            sel = results.curselection()
            if not sel or sel[0] >= len(paths):
                return
            idx = sel[0]
            item_path = paths[idx]
            lib_item = self.media_library.get(item_path)
            is_fav = bool(lib_item.favorite) if lib_item else False
            menu = tk.Menu(dialog, tearoff=0, bg=PANEL, fg=TEXT,
                           activebackground=RED_DARK, activeforeground=TEXT,
                           relief="flat")
            fav_label = "★ Remove favorite" if is_fav else "☆ Mark as favorite"
            menu.add_command(label=fav_label, command=lambda: (
                self.media_library.set_favorite(item_path, not is_fav),
                refresh()))
            menu.add_separator()
            menu.add_command(label="Add to queue", command=lambda: (
                self.add_files([item_path]), dialog.destroy()))
            menu.tk_popup(event.x_root, event.y_root)

        results.bind("<Button-3>", _lib_context_menu)
        query.trace_add("write", refresh)
        refresh(); entry.focus_set()

    def _save_effective_settings(self) -> None:
        current = self.settings_store.load()
        self.settings_store.save(PlayerSettings(
            self._volume, self._muted, self._rate, self._audio_device,
            tuple(self._watched_folders),
            current.ytdlp_consent, self._visualizer_mode,
            current.resume_playback, current.cache_limit_mib,
        ))

    def _sync_queue_empty(self):
        pass


    def _refresh_file_browser(self):
        path = Path(self._fb_path_var.get()).expanduser().resolve()
        if not path.is_dir():
            self._fb_count_var.set("Invalid directory")
            return
        search = self._fb_search_var.get().strip().lower()
        self._fb_list.delete(0, "end")
        items = []
        try:
            entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            self._fb_count_var.set("Permission denied")
            return
        MEDIA_EXTS = frozenset({".mp3",".mp4",".flac",".wav",".aac",".ogg",".opus",".m4a",".wma",
                      ".mkv",".webm",".avi",".mov",".m4v",".flv",".wmv",".mpeg",".mpg",
                      ".m2ts",".ts",".vob",".ogv",".3gp",".divx",".rm",".mxf",".asf",
                      ".aiff",".alac",".ape",".wv",".dts",".mpc",
                      ".casu",".mp5",".m3u",".m3u8",".pls",".json"})
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if search and search not in entry.name.lower():
                continue
            if entry.is_dir():
                self._fb_list.insert("end", "[DIR] " + entry.name + "/")
                items.append(("dir", entry))
            elif entry.suffix.lower() in MEDIA_EXTS:
                etype = detect_entry_type(entry)
                icon = {"local-file":"[FILE]", "casu":"[CASU]", "mp5":"[MP5]", "playlist":"[PL]",
                        "http-stream":"[NET]", "youtube":"[YT]",
                        "rtsp-stream":"[RTSP]", "rtmp-stream":"[RTMP]"}.get(etype, "[MEDIA]")
                label = icon + " " + entry.name
                self._fb_list.insert("end", label)
                items.append(("file", entry))
        self._fb_items = items
        count = sum(1 for t, _ in items if t == "file")
        self._fb_count_var.set(f"{count} files in {path.name}")

    def _on_fb_activate(self):
        sel = self._fb_list.curselection()
        if not sel or not hasattr(self, "_fb_items") or sel[0] >= len(self._fb_items):
            return
        kind, entry = self._fb_items[sel[0]]
        if kind == "dir":
            self._fb_path_var.set(str(entry))
            self._fb_search_var.set("")
            self._refresh_file_browser()
        else:
            self.add_files([entry])

    def _fb_navigate(self, target):
        current = Path(self._fb_path_var.get()).expanduser().resolve()
        if target == "..":
            parent = current.parent
            if parent != current:
                self._fb_path_var.set(str(parent))
                self._refresh_file_browser()

    def _fb_add_all(self):
        if not hasattr(self, "_fb_items"):
            return
        files = [entry for kind, entry in self._fb_items if kind == "file"]
        if files:
            self.add_files(files)
            self.status.set(f"Added {len(files)} file(s) to queue")

    def _refresh_db_finder(self):
        query = self._db_search_var.get().strip()
        filt = self._db_filter_var.get()
        favorites_only = filt == "fav"
        items = self.media_library.search(query, favorites_only=favorites_only, limit=500)
        self._db_list.delete(0, "end")
        self._db_visible_items = []
        shown = 0
        for item in items:
            ext = item.path.suffix.lower()
            if filt == "video" and ext not in {".mp4",".mkv",".webm",".avi",".mov",".m4v",".flv",".wmv",".mpeg",".mpg"}:
                continue
            if filt == "audio" and ext not in {".mp3",".flac",".wav",".aac",".ogg",".opus",".m4a",".wma"}:
                continue
            if filt == "casu" and ext != ".casu" and ext != ".mp5":
                continue
            marker = "\u2605 " if item.favorite else ""
            dur = f" {item.duration_seconds:.0f}s" if item.duration_seconds else ""
            label = marker + item.path.name + dur
            self._db_list.insert("end", label)
            self._db_visible_items.append(item)
            shown += 1
        total = len(self.media_library.items())
        self._db_count_var.set(f"{total} files \u00b7 {shown} shown")

    def _add_db_selected(self):
        sel = self._db_list.curselection()
        if not sel:
            return
        items = getattr(self, "_db_visible_items", [])
        if sel[0] < len(items):
            self.add_files([items[sel[0]].path])

    def _db_context_menu(self, event):
        sel = self._db_list.curselection()
        if not sel:
            return
        items = getattr(self, "_db_visible_items", [])
        if sel[0] >= len(items):
            return
        item = items[sel[0]]
        menu = tk.Menu(self.root, tearoff=0, bg=PANEL, fg=TEXT,
                       activebackground=RED_DARK, activeforeground=TEXT,
                       relief="flat")
        fav_label = "★ Remove favorite" if item.favorite else "☆ Mark as favorite"
        menu.add_command(label=fav_label, command=lambda: (
            self.media_library.set_favorite(item.path, not item.favorite),
            self._refresh_db_finder()))
        menu.add_separator()
        menu.add_command(label="Add to queue",
                         command=lambda: self.add_files([item.path]))
        menu.tk_popup(event.x_root, event.y_root)

    def _restore_session(self):
        try:
            payload = read_bounded_json(self._session_file,
                                        max_bytes=MAX_PLAYLIST_FILE_BYTES,
                                        label="player session")
            if not isinstance(payload, dict):
                raise ValueError("session must be an object")
            values = payload.get("playlist", [])
            loaded = PlaylistModel.from_payload(
                {"version": 1, "items": values}, existing_only=True)
            self.add_files(list(loaded.items))
            self._resume_source = str(payload.get("current", "")) or None
            self._resume_position = max(0.0, float(payload.get("position", 0.0)))
            geometry = payload.get("geometry")
            if isinstance(geometry, str) and 0 < len(geometry) <= 128:
                self.geometry(geometry)
        except (CasuError, PlaylistError, OSError, ValueError, TypeError, tk.TclError):
            pass

    def _shutdown(self):
        resume_position = self.backend.position() if self.backend else self.position.get()
        self._persist_media_preferences()
        try:
            atomic_write_json(self._session_file, {
                "playlist": [str(item) for item in self.playlist_model.items],
                "volume": self._volume,
                "muted": self._muted,
                "rate": self._rate,
                "current": str(self.current) if self.current else None,
                "position": resume_position,
                "geometry": self.geometry(),
            }, max_bytes=MAX_PLAYLIST_FILE_BYTES)
        except (CasuError, OSError):
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
        if self._recorder is not None:
            recorder, self._recorder = self._recorder, None
            try:
                recorder.finish(timeout=3)
            except (RecordingError, OSError):
                recorder.abort()
        self._retire_backend()
        self.media_library.close()
        self.destroy()

    def _load_visual_state(self, path: Path):
        self._visual_state = "legacy"
        self._visual_segments = []
        self._visual_video_segments = []
        self._visual_audio_segments = []
        self._scheduler = None
        try:
            route = detect_local_playback_kind(path)
        except CasuError:
            return
        if route == LOCAL_MEDIA:
            return
        try:
            with path.open("rb") as handle:
                magic = handle.read(8)
            if route == LOCAL_CASUNAT2:
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
            if route == LOCAL_MP5:
                from casu.mp5 import Mp5Error, read_mp5
                try:
                    manifest = read_mp5(path).manifest
                except Mp5Error:
                    self._visual_state = "invalid CASU MP5"
                    return
                self._visual_state = "CASU MP5 enhanced container"
            else:
                manifest = (read_native(path, verify_payload=True).manifest if route == LOCAL_CASUNAT1
                            else read_bounded_json(path, max_bytes=MAX_SIDECAR_BYTES,
                                                   label="CASU sidecar"))
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

    def _enable_drag_drop(self) -> None:
        """OS-level drag & drop when tkdnd is available; dialogs stay the fallback."""
        try:
            from tkinterdnd2 import DND_FILES
        except ImportError:
            return
        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
        except (tk.TclError, AttributeError):
            pass

    def _on_drop(self, event) -> None:
        import re
        paths: list[Path] = []
        for braced, plain in re.findall(r"\{(.+?)\}|(\S+)", event.data or ""):
            candidate = Path((braced or plain)).expanduser()
            if candidate.exists():
                paths.append(candidate)
        if paths:
            self.add_files(paths)
            self._toast(f"{len(paths)} file(s) added from drop")

    def _on_stage_click(self, event) -> None:
        if self._stage_is_empty() and self._empty_cta_bbox:
            x0, y0, x1, y1 = self._empty_cta_bbox
            if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                self.add_dialog()

    def _stage_is_empty(self) -> bool:
        if self.backend is not None:
            return False
        return not self._waveform and self._pcm_buffer[0] is None

    def _toast(self, message: str) -> None:
        """Non-blocking web-style toast: bottom-center, red accent, auto-hide."""
        if getattr(self, "_toast_label", None) is None:
            self._toast_label = tk.Label(
                self.center_shell, text="", bg=TOAST_BG, fg=TEXT,
                padx=14, pady=8, font=("TkDefaultFont", 9),
                highlightthickness=1, highlightbackground=TOAST_BORDER)
            self._toast_label.bind("<Button-1>", lambda _e: self._hide_toast())
        if self._toast_job is not None:
            self.after_cancel(self._toast_job)
        self._toast_label.configure(text=message)
        self._toast_label.place(relx=0.5, rely=1.0, anchor="s", y=-25)
        self._toast_job = self.after(TOKENS.toast_ms, self._hide_toast)

    def _hide_toast(self) -> None:
        self._toast_job = None
        if getattr(self, "_toast_label", None) is not None:
            self._toast_label.place_forget()

    def _draw_empty_state(self, width: int, height: int) -> None:
        """Web-player hero: icon, drop hint and a clickable choose-files CTA."""
        cx, cy = width // 2, max(150, height // 2 - 40)
        self.canvas.create_oval(cx - 190, cy - 130, cx + 190, cy + 52,
                                fill="#160a0e", outline="", tags="viz")
        self.canvas.create_oval(cx - 46, cy - 96, cx + 46, cy - 4,
                                outline=RED, width=2, tags="viz")
        self.canvas.create_polygon(cx - 12, cy - 70, cx - 12, cy - 30,
                                   cx + 22, cy - 50, fill=RED, outline="", tags="viz")
        self.canvas.create_text(cx, cy + 32, text="Drop media here",
                                fill=TEXT, font=("TkDefaultFont", 16, "bold"), tags="viz")
        self.canvas.create_text(cx, cy + 58,
                                text="Audio · Video · Streams · Playlists · CASU · MP5",
                                fill=MUTED, font=("TkDefaultFont", 10), tags="viz")
        bw, bh = 150, 40
        x0, y0 = cx - bw // 2, cy + 84
        x1, y1 = cx + bw // 2, cy + 84 + bh
        self.canvas.create_rectangle(x0, y0, x1, y1, fill=RED_DARK,
                                     outline=RED, width=2, tags="viz")
        self.canvas.create_text(cx, y0 + bh // 2, text="Choose files",
                                fill=TEXT, font=("TkDefaultFont", 10, "bold"), tags="viz")
        self._empty_cta_bbox = (x0, y0, x1, y1)

    def _draw_overlay_badges(self, width: int) -> None:
        """Web-player style format/integrity chips floating over the stage."""
        x = 16
        for text, accent in ((self._format_badge, False),
                             (self._integrity_badge, True)):
            if not text:
                continue
            w = 14 + 7 * len(text)
            self.canvas.create_rectangle(x, 14, x + w, 36, fill=BADGE_BG,
                                         outline=RED if accent else BADGE_BORDER,
                                         width=1, tags="viz")
            self.canvas.create_text(x + w // 2, 25, text=text,
                                    fill=RED if accent else SECONDARY,
                                    font=("TkDefaultFont", 8, "bold"), tags="viz")
            x += w + 8

    def _draw_visualizer(self):
        width = max(120, self.canvas.winfo_width())
        height = max(160, self.canvas.winfo_height())
        self.canvas.delete("viz")
        self._empty_cta_bbox = None
        if self._stage_is_empty():
            self._draw_empty_state(width, height)
            return
        if self.backend is not None and self._presentation_mode != "VIDEO":
            self._draw_overlay_badges(width)
        if self._visualizer_mode == "off":
            return
        show_spectrum = self._visualizer_mode in ("spectrum", "both")
        show_waveform = self._visualizer_mode in ("waveform", "both")
        if self._presentation_mode == "VIDEO" and self.backend and self.backend.state() in {
            PlaybackState.LOADING, PlaybackState.READY, PlaybackState.PLAYING,
            PlaybackState.PAUSED,
        }:
            return

        pcm_buf, pcm_rate, _pcm_ch = self._pcm_buffer
        has_live_data = pcm_buf is not None and pcm_rate > 0
        pos = self.position.get()

        if self._presentation_mode == "AUDIO" and (self._waveform or has_live_data):
            left, right = 24, width - 24
            center = max(125, height // 2 + 30)
            amplitude = max(25, min(125, height // 3))

            idle = self._paused or not self.backend
            breathe = 1.0
            if idle and has_live_data:
                breathe = 1.0 + 0.04 * math.sin(self._visual_phase * 0.08)

            for fraction in (.25, .5, .75):
                y = center - amplitude + fraction * amplitude * 2
                self.canvas.create_line(left, y, right, y, fill="#242A30",
                                        dash=(2, 5), tags="viz")

            if has_live_data:
                live_wave = window_peaks(pcm_buf, pcm_rate, pos,
                                         window_s=0.6, points=320)
                live_spec = (live_spectrum(pcm_buf, pcm_rate, pos,
                                           fft_size=2048, bands=32)
                             if show_spectrum else ())
                if live_spec:
                    fall = list(self._spectrum_peak_fall)
                    if len(fall) != len(live_spec):
                        fall = [0.0] * len(live_spec)
                    updated = []
                    for idx, val in enumerate(live_spec):
                        fall[idx] = max(fall[idx] * 0.88, val)
                        updated.append(fall[idx])
                    self._spectrum_peak_fall = updated
                    baseline = height - 46
                    spec_height = min(86, max(35, height // 6))
                    gap = 3
                    bar_width = max(2, (right - left) / len(live_spec) - gap)
                    for idx, val in enumerate(live_spec):
                        x = left + idx * (right - left) / len(live_spec)
                        bar_h = min(val, updated[idx]) * spec_height * breathe
                        self.canvas.create_rectangle(
                            x, baseline - bar_h, x + bar_width, baseline,
                            fill=RED if idx % 2 == 0 else RED_DARK,
                            outline=LINE,
                            width=1, tags="viz")
                        peak_y = baseline - updated[idx] * spec_height * breathe
                        self.canvas.create_line(
                            x, peak_y, x + bar_width, peak_y,
                            fill=RED, width=2, tags="viz")
                    if live_wave:
                        overlay: list[float] = []
                        count = len(live_wave)
                        mid = baseline - spec_height / 2
                        for idx, peak in enumerate(live_wave):
                            x = left + (right - left) * idx / max(1, count - 1)
                            overlay.extend((x, mid - peak * spec_height * 0.45))
                        if overlay:
                            self.canvas.create_line(*overlay, fill=RED,
                                                    width=1, tags="viz")
                if live_wave:
                    phase_offset = int(self._visual_phase) % len(live_wave)
                    rolled = live_wave[phase_offset:] + live_wave[:phase_offset]
                    rolled = tuple(v * breathe for v in rolled)
                    count = len(rolled)
                    coordinates = []
                    for idx, peak in enumerate(rolled):
                        x = left + (right - left) * idx / max(1, count - 1)
                        coordinates.extend((x, center - peak * amplitude))
                    for idx in range(count - 1, -1, -1):
                        x = left + (right - left) * idx / max(1, count - 1)
                        coordinates.extend((x, center + rolled[idx] * amplitude))
                    self.canvas.create_polygon(*coordinates, fill=RED_DARK,
                                               outline=RED, width=1, tags="viz")
                    fraction = pos / self.duration if self.duration > 0 else 0
                    play_x = left + (right - left) * max(0.0, min(1.0, fraction))
                    self.canvas.create_line(play_x, center - amplitude - 8,
                                            play_x, center + amplitude + 8,
                                            fill=TEXT, tags="viz")
                    label = ("Animated PCM waveform · Live FFT spectrum"
                             if not idle else
                             "Paused · Animated PCM waveform · Live FFT spectrum")
                    self.canvas.create_text(width // 2, center + amplitude + 24,
                                            text=label, fill=SECONDARY, tags="viz")
                    return
                if live_spec:
                    self.canvas.create_text(width // 2, height - 18,
                                            text="Live FFT spectrum",
                                            fill=SECONDARY, tags="viz")
                    return
            if self._waveform and show_waveform:
                count = len(self._waveform)
                coordinates = []
                for idx, peak in enumerate(self._waveform):
                    x = left + (right - left) * idx / max(1, count - 1)
                    coordinates.extend((x, center - peak * amplitude))
                for idx in range(count - 1, -1, -1):
                    x = left + (right - left) * idx / max(1, count - 1)
                    coordinates.extend((x, center + self._waveform[idx] * amplitude))
                self.canvas.create_polygon(*coordinates, fill=RED_DARK, outline=RED,
                                           width=1, tags="viz")
                fraction = pos / self.duration if self.duration > 0 else 0
                play_x = left + (right - left) * max(0.0, min(1.0, fraction))
                self.canvas.create_line(play_x, center - amplitude - 8, play_x,
                                        center + amplitude + 8, fill=TEXT, tags="viz")
                self.canvas.create_text(width // 2, center + amplitude + 24,
                                        text="Measured PCM waveform · FFT spectrum",
                                        fill=SECONDARY, tags="viz")
                return
        state = self._state_at_position()
        label = ("Decoding measured PCM waveform…" if self._presentation_mode == "AUDIO"
                 else "No decoded visualization data")
        if self._visual_state.startswith("CASU"):
            label = f"CASU state map · {state}"
        self.canvas.create_text(width // 2, height // 2, anchor="center", text=label,
                                fill=MUTED, font=("TkDefaultFont", 11), tags="viz")

    def _load_waveform(self, path: Path, mode: str) -> None:
        self._waveform_generation += 1
        generation = self._waveform_generation
        self._waveform = ()
        self._spectrum = ()
        self._pcm_buffer = (None, 0, 0)
        self._spectrum_peak_fall = []
        self._visual_phase = 0.0
        self._presentation_mode = mode
        self._draw_visualizer()
        if mode != "AUDIO":
            return

        def worker() -> None:
            try:
                source = path
                route = detect_local_playback_kind(path)
                if route == LOCAL_CASU_SIDECAR:
                    source = resolve_casu_source(path)
                peaks = waveform_peaks(source)
                spectrum = spectrum_bands(source)
                pcm_buffer, pcm_rate, pcm_channels = decode_all_pcm(source)
            except (CasuError, OSError, WaveformError):
                peaks = ()
                spectrum = ()
                pcm_buffer, pcm_rate, pcm_channels = None, 0, 0

            def present() -> None:
                if generation != self._waveform_generation or self.current != path:
                    return
                self._waveform = peaks
                self._spectrum = spectrum
                self._pcm_buffer = (pcm_buffer, pcm_rate, pcm_channels)
                if pcm_buffer is not None and pcm_buffer.size > 0:
                    self._spectrum_peak_fall = [0.0] * len(
                        live_spectrum(pcm_buffer, pcm_rate, 0.0))
                self._draw_visualizer()
            self.after(0, present)
        threading.Thread(target=worker, daemon=True).start()

    def remove_selected(self):
        selected = list(self.library.curselection())
        active_removed = (self.current is not None and any(
            self.playlist_model.item(index) == self.current for index in selected))
        if active_removed:
            self.stop()
            self.current = None
            self.now_playing.configure(text="NOW PLAYING · NO MEDIA SELECTED")
        try:
            self.playlist_model.remove(selected)
        except PlaylistError as exc:
            self.status.set(str(exc)); return
        next_index = min(selected[0], len(self.playlist_model) - 1) if selected and len(self.playlist_model) else None
        self._render_playlist(next_index)
        if active_removed:
            self.status.set("Active file removed; playback stopped safely")

    def save_playlist(self):
        target = filedialog.asksaveasfilename(
            defaultextension=".m3u",
            filetypes=[("M3U playlist", "*.m3u"), ("PLS playlist", "*.pls"),
                       ("XSPF playlist", "*.xspf"), ("MPCASU JSON", "*.json"),
                       ("All files", "*.*")])
        if not target:
            return
        if not Path(target).suffix:
            target = target + ".m3u"
        try:
            save_playlist_file(target, self.playlist_model)
            self.status.set(f"Playlist saved · {Path(target).name}")
        except (OSError, PlaylistError) as exc:
            messagebox.showerror("MPCASU", f"Could not save playlist: {exc}")

    def load_playlist(self):
        source = filedialog.askopenfilename(
            filetypes=[("Playlists", "*.m3u *.m3u8 *.pls *.json *.wpl *.xspf "
                                     "*.jspf *.asx *.wmx *.wvx *.rmp *.ram"),
                       ("M3U", "*.m3u *.m3u8"), ("PLS", "*.pls"),
                       ("XSPF", "*.xspf"), ("WPL", "*.wpl"),
                       ("ASX", "*.asx *.wmx *.wvx"), ("RealMedia", "*.rmp *.ram"),
                       ("JSON", "*.json"), ("All files", "*.*")])
        if not source:
            return
        try:
            fmt = detect_playlist_format(source)
            loaded = load_playlist_file(source, existing_only=True)
            self.add_files(list(loaded.items))
            self.status.set(f"Playlist loaded ({fmt.upper()}) · {Path(source).name}")
        except (OSError, PlaylistError) as exc:
            messagebox.showerror("MPCASU", f"Could not load playlist: {exc}")

    def show_media_info(self):
        path = self.current or self.selected_path()
        if not path or not path.is_file():
            self.status.set("No local media selected for information")
            return
        try:
            route = detect_local_playback_kind(path)
            native = route == LOCAL_CASUNAT1
            native_v2 = route == LOCAL_CASUNAT2
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
            if route != LOCAL_MEDIA:
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
            dialog = tk.Toplevel(self); dialog.bind("<Escape>", lambda _event, _dialog=dialog: _dialog.destroy()); dialog.title("Media information"); dialog.configure(bg=BG); dialog.transient(self)
            text = tk.Text(dialog, width=76, height=max(8, len(lines) + 2), bg=PANEL_ALT, fg=TEXT, relief="flat", wrap="word")
            text.insert("1.0", "\n".join(lines)); text.configure(state="disabled"); text.pack(padx=16, pady=16)
        except (CasuError, NativeCasuError, NativeV2Error, OSError, ValueError) as exc:
            messagebox.showerror("MPCASU", f"Media information unavailable: {exc}")

    def selected_item(self):
        selected = self.library.curselection()
        if not selected:
            if self.current:
                return str(self.current) if isinstance(self.current, str) else self.current
            if len(self.playlist_model):
                item = self.playlist_model.item(0)
                return str(item) if isinstance(item, str) else item
            return None
        try:
            item = self.playlist_model.item(selected[0])
            return str(item) if isinstance(item, str) else item
        except PlaylistError:
            return None

    def selected_path(self) -> Path | None:
        item = self.selected_item()
        if isinstance(item, str):
            return None
        return item
    def _sidecar(self, path: Path) -> Path:
        return path.with_suffix(path.suffix + ".casu")

    def play_selected(self):
        item = self.selected_item()
        if not item:
            messagebox.showinfo("MPCASU", "Add a media file first.")
            return
        if isinstance(item, str):
            # URL row: show the resolved title (never the raw URL).
            self._resolve_and_open_external_source(
                item, display_label=self._display_titles.get(item, item))
            return
        path = item
        if not path:
            messagebox.showinfo("MPCASU", "Add a media file first.")
            return
        try:
            route = detect_local_playback_kind(path)
        except CasuError as exc:
            messagebox.showerror("MPCASU", str(exc))
            self.status.set("Cannot play \u2014 source type or CASU integrity is invalid")
            return
        self.stop()
        self._location_generation += 1
        self._network_source = None
        self._network_display = None
        self._stream_channel = None
        self._end_handled = False
        self.current = path
        self._ab_start = self._ab_end = None
        self.now_playing.configure(text=path.name.upper())
        self._format_badge = {
            LOCAL_CASUNAT1: "CASUNAT1", LOCAL_CASUNAT2: "CASUNAT2",
            LOCAL_CASU_SIDECAR: "CASU", LOCAL_MP5: "MP5",
        }.get(route, path.suffix.lstrip(".").upper() or "MEDIA")
        self._integrity_badge = ("VERIFIED"
                                 if route in {LOCAL_CASUNAT1, LOCAL_CASUNAT2,
                                              LOCAL_CASU_SIDECAR, LOCAL_MP5}
                                 else "READY")
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
        if route in {LOCAL_CASUNAT1, LOCAL_CASUNAT2}:
            self._set_diagnostics(
                support=("CASUNAT2 native key-state/tile/PCM"
                         if route == LOCAL_CASUNAT2
                         else "CASUNAT1 compatibility + libVLC"),
                integrity="verified native container",
                segmented=(f"{len(self._visual_segments)} segments"
                           if self._visual_segments else "no segment data"),
            )
        elif route == LOCAL_CASU_SIDECAR:
            self._set_diagnostics(
                support="CASU sidecar + libVLC",
                integrity=("verified source manifest"
                           if not self._visual_state.startswith("invalid")
                           else "failed manifest validation"),
                segmented=(f"{len(self._visual_segments)} segments"
                           if self._visual_segments else "no segment data"),
            )
        elif route == LOCAL_MP5:
            self._set_diagnostics(
                support="CASU MP5 envelope + libVLC",
                integrity="verified MP5 container",
                segmented=(f"{len(self._visual_segments)} segments"
                           if self._visual_segments else "no segment data"),
            )
        else:
            self._set_diagnostics(support="Legacy backend",
                                  integrity="unavailable",
                                  segmented="unavailable")
        self._set_diagnostics(energy="unavailable \u2014 not measured")
        try:
            source = self._source_for(path, route)
        except CasuError as exc:
            messagebox.showerror("MPCASU", str(exc))
            self.status.set("Cannot play \u2014 safe fallback refused an invalid CASU manifest")
            return
        state = ("CASU native container" if route in {LOCAL_CASUNAT1, LOCAL_CASUNAT2}
                 else "CASU MP5 container" if route == LOCAL_MP5
                 else "CASU sidecar found" if route == LOCAL_CASU_SIDECAR
                 else "legacy fallback \u2014 no CASU sidecar")
        self.status.set(f"{path.name} \u00b7 {state}")
        try:
            if route == LOCAL_CASUNAT2 and NativeCasuBackend.supports(path):
                try:
                    audio_sink = PulseAudioSink() if PulseAudioSink.probe() else None
                except BackendError:
                    # Video-only/headless systems still get native CASU video.
                    audio_sink = None
                self.backend = NativeCasuBackend(TkCanvasVideoSink(self.canvas),
                                                 audio_sink)
            elif route in {LOCAL_CASUNAT1, LOCAL_CASU_SIDECAR, LOCAL_MP5}:
                self.backend = CasuBackend(self.canvas)
            else:
                self.backend = LibVLCBackend(self.canvas)
            self.backend.on_event = self._backend_event
            if route in {LOCAL_CASUNAT1, LOCAL_CASUNAT2, LOCAL_CASU_SIDECAR, LOCAL_MP5}:
                self.backend.open_casu(path)
            else:
                self.backend.open(source)
            self.controller.attach(self.backend, path)
            if isinstance(self.backend, NativeCasuBackend):
                self._apply_media_preferences()
            self.controller.play()
            self._apply_playback_rate()
            self._apply_backend_settings()
            self.duration = self.backend.duration()
            self.timeline.configure(to=max(self.duration, 1.0))
            self._draw_chapter_markers()
            settings = self.settings_store.load()
            if (settings.resume_playback and self._resume_source
                    and str(path) == self._resume_source
                    and 5.0 < self._resume_position < max(5.0, self.duration - 5.0)):
                self.controller.seek(self._resume_position)
                self.position.set(self._resume_position)
                self.status.set(f"Resumed {path.name} at {self._resume_position:.1f} s")
            else:
                self._resume_position = 0.0
            capabilities = self.backend.capabilities()
            self.status.set(f"{path.name} \u00b7 {state} \u00b7 "
                            f"{capabilities.get('version', 'libVLC')}")
            # libVLC can accept a media object while a decoder later fails.
            # Check local playback after its asynchronous pipeline had time to
            # announce streams; never leave the UI claiming PLAYING forever
            # when no timed media was produced.
            if isinstance(self.backend, LibVLCBackend):
                self.after(500, self._apply_media_preferences)
                self.after(1500, self._check_playback_start)
            backend = self.backend
            self.after(15_000, lambda: self._check_local_playback_timeout(backend))
        except (BackendError, CasuError, OSError) as exc:
            self.controller.close()
            self.backend = None
            self.status.set("Cannot play \u2014 internal media backend unavailable")
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
        """Receive backend events without entering Tcl from a worker thread."""
        self._backend_events.put(state)

    def _drain_backend_events(self) -> None:
        while True:
            try:
                state = self._backend_events.get_nowait()
            except queue.Empty:
                return
            self._apply_backend_event(state)

    def _apply_backend_event(self, state: PlaybackState) -> None:
        if state == PlaybackState.PLAYING:
            self._paused = False
        elif state == PlaybackState.PAUSED:
            self._paused = True
        elif state == PlaybackState.ERROR:
            detail_reader = getattr(self.backend, "last_error", None)
            detail = detail_reader() if callable(detail_reader) else None
            stopper = getattr(self.backend, "stop", None)
            if callable(stopper):
                try:
                    stopper()
                except (BackendError, OSError):
                    pass
            self._paused = True
            self.status.set("Playback error — " + (detail or "decoder or output failed"))
            self._set_diagnostics(support="backend error; inspect media information/logs")
        elif state == PlaybackState.ENDED and not self._advancing and not self._end_handled:
            self._end_handled = True
            self._advancing = True
            try:
                self.play_next(automatic=True)
            finally:
                self._advancing = False

    def _check_playback_start(self):
        if not self.backend or not self.current or self._paused:
            return
        if self.current.as_uri().startswith(("http:", "https:", "rtsp:")):
            return
        if self.backend.state() == PlaybackState.PLAYING and not self.backend.is_actively_playing():
            self._retire_backend(self.backend)
            self._paused = True
            self.status.set("Playback unavailable — libVLC did not enter active playback")
            self._set_diagnostics(support="backend opened; decoder or output unavailable")

    def _check_local_playback_timeout(self, expected_backend) -> None:
        if self.backend is not expected_backend or self._paused:
            return
        state = expected_backend.state()
        progressed = expected_backend.position() > 0.05
        active = (expected_backend.is_actively_playing()
                  if hasattr(expected_backend, "is_actively_playing") else False)
        if state in {PlaybackState.LOADING, PlaybackState.READY} and not (progressed or active):
            self._retire_backend(expected_backend)
            self._paused = True
            self.status.set("Playback stopped — decoder or audio/video output did not become ready")
            self._set_diagnostics(support="local playback startup timeout")

    def _update_presentation(self, path: Path):
        """Choose a presentation mode from probed streams, not file suffixes."""
        try:
            # A CASU sidecar is metadata; stream presentation comes from the
            # immutable source it references, never from the JSON manifest.
            route = detect_local_playback_kind(path)
            native = route == LOCAL_CASUNAT1
            native_v2 = route == LOCAL_CASUNAT2
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
            self._load_waveform(path, mode)
            if mode == "VIDEO":
                self.canvas.itemconfigure("title", text=path.name)
                audio_note = " + audio" if "audio" in kinds else ""
                self.canvas.itemconfigure("subtitle", text=f"Video stream{audio_note} · original timestamps preserved")
            elif mode == "AUDIO":
                self.canvas.itemconfigure("title", text="AUDIO MODE")
                self.canvas.itemconfigure("subtitle", text="Audio stream · measured PCM waveform")
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
        self._cycle_reported_track(
            "Audio", "audio_track_descriptions", "audio_track", "set_audio_track")

    def cycle_video_track(self):
        self._cycle_reported_track(
            "Video", "video_track_descriptions", "video_track", "set_video_track")

    def cycle_subtitle_track(self):
        self._cycle_reported_track(
            "Subtitle", "subtitle_track_descriptions", "subtitle_track",
            "set_subtitle_track")

    def _cycle_reported_track(self, kind, descriptions_name, current_name, setter_name):
        """Cycle concrete backend identifiers instead of inventing indices."""
        if not self.backend:
            self.status.set("No active media backend")
            return
        try:
            descriptions = getattr(self.backend, descriptions_name)()
            tracks = []
            seen = set()
            for identifier, label in descriptions:
                identifier = int(identifier)
                if identifier < 0 or identifier in seen:
                    continue
                tracks.append((identifier, str(label) or f"Track {identifier}"))
                seen.add(identifier)
            if not tracks:
                self.status.set(f"No selectable {kind.lower()} tracks reported by backend")
                return
            identifiers = [identifier for identifier, _label in tracks]
            current = int(getattr(self.backend, current_name)())
            index = (identifiers.index(current) + 1) % len(tracks) if current in identifiers else 0
            identifier, label = tracks[index]
            getattr(self.backend, setter_name)(identifier)
            self.status.set(f"{kind}: {label} ({index + 1}/{len(tracks)})")
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

    def goto_time_dialog(self) -> None:
        if not self.backend:
            self.status.set("No active media backend"); return
        maximum = self.duration if self.duration > 0 else 7 * 24 * 60 * 60
        value = simpledialog.askfloat("Go to time", "Position in seconds:",
                                      initialvalue=self.position.get(), minvalue=0,
                                      maxvalue=maximum, parent=self)
        if value is not None:
            self.position.set(value); self.seek_restart()

    def cycle_ab_loop(self) -> None:
        if not self.backend:
            self.status.set("No active media for A–B repeat"); return
        position = self.backend.position()
        if self._ab_start is None:
            self._ab_start = position; self._ab_end = None
            self.status.set(f"A–B repeat: A = {position:.3f} s")
        elif self._ab_end is None:
            if position <= self._ab_start:
                self.status.set("A–B repeat: B must be after A"); return
            self._ab_end = position
            self.status.set(f"A–B repeat active · {self._ab_start:.3f}–{position:.3f} s")
        else:
            self._ab_start = self._ab_end = None
            self.status.set("A–B repeat cleared")

    def take_snapshot(self) -> None:
        if not self.backend or not hasattr(self.backend, "take_snapshot"):
            self.status.set("Snapshots are unavailable for the active backend"); return
        default = ((self.current.stem if self.current else "stream") +
                   f"-{int(self.position.get() * 1000):010d}.png")
        target = filedialog.asksaveasfilename(parent=self, defaultextension=".png",
            initialfile=default, filetypes=[("PNG image", "*.png")])
        if not target: return
        try:
            result = self.backend.take_snapshot(target)
            self.status.set(f"Snapshot saved · {result}")
        except (BackendError, OSError) as exc:
            messagebox.showerror("MPCASU snapshot", str(exc), parent=self)

    def _refresh_bookmark_menu(self) -> None:
        menu = self._bookmark_menu; menu.delete(0, "end")
        if not self.current:
            menu.add_command(label="Bookmarks require local media", state="disabled"); return
        menu.add_command(label="Add bookmark here…", command=self.add_bookmark_dialog)
        bookmarks = self.media_library.bookmarks(self.current)
        if not bookmarks:
            menu.add_command(label="No saved bookmarks", state="disabled"); return
        menu.add_separator()
        remove = tk.Menu(menu, tearoff=False, bg=PANEL_ALT, fg=TEXT,
                         activebackground=RED_DARK, activeforeground=TEXT)
        for item in bookmarks:
            minutes, seconds = divmod(int(item.position_seconds), 60)
            label = f"{minutes:02d}:{seconds:02d} · {item.label}"
            menu.add_command(label=label, command=lambda position=item.position_seconds:
                             self._seek_bookmark(position))
            remove.add_command(label=label, command=lambda identifier=item.identifier:
                               self._remove_bookmark(identifier))
        menu.add_cascade(label="Remove bookmark", menu=remove)

    def add_bookmark_dialog(self) -> None:
        if not self.current: return
        position = self.backend.position() if self.backend else self.position.get()
        label = simpledialog.askstring("Add bookmark", "Bookmark label:",
                                       initialvalue=f"Bookmark at {position:.1f} s",
                                       parent=self)
        if label is None: return
        try:
            self.media_library.add_bookmark(self.current, position, label)
            self.status.set(f"Bookmark saved at {position:.1f} s")
        except (OSError, ValueError) as exc:
            self.status.set(f"Could not save bookmark: {exc}")

    def _seek_bookmark(self, position: float) -> None:
        self.position.set(position); self.seek_restart()

    def _remove_bookmark(self, identifier: int) -> None:
        self.media_library.remove_bookmark(identifier)
        self.status.set("Bookmark removed")

    def toggle_fullscreen(self):
        self.attributes("-fullscreen", not bool(self.attributes("-fullscreen")))

    def toggle_mini_player(self) -> None:
        """Switch to compact transport without interrupting the active backend."""
        if not self._mini_mode:
            self._pre_mini_geometry = self.geometry()
            self._mini_mode = True
            self.left_shell.pack_forget()
            self.right_shell.pack_forget()
            self.diagnostics.pack_forget()
            self.statusbar.pack_forget()
            self.minsize(620, 210)
            self.geometry("720x260")
            self.attributes("-topmost", True)
            self.status.set("Mini player · press N or Mini to restore")
            return
        self._mini_mode = False
        self.attributes("-topmost", False)
        self.minsize(860, 560)
        if self._pre_mini_geometry:
            self.geometry(self._pre_mini_geometry)
        self.left_shell.pack(side="left", fill="y", padx=(0, 10),
                             before=self.center_shell)
        self.right_shell.pack(side="right", fill="y", padx=(10, 0),
                              before=self.center_shell)
        self.statusbar.pack(fill="x", padx=18, pady=(4, 10))
        self.diagnostics.pack(fill="x", padx=18, pady=(10, 4),
                              before=self.statusbar)
        # Apply the restored geometry only after every sibling referenced by
        # responsive pack(before=...) callbacks is mapped again.
        self.update_idletasks()
        self._responsive_layout()
        self.status.set("Full player restored")

    def _source_for(self, path: Path, route: str | None = None) -> Path:
        route = route or detect_local_playback_kind(path)
        if route == LOCAL_MEDIA:
            return path
        if route in {LOCAL_CASUNAT1, LOCAL_CASUNAT2, LOCAL_MP5}:
            return path
        try:
            manifest = read_bounded_json(path, max_bytes=MAX_SIDECAR_BYTES,
                                         label="CASU sidecar")
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

    def _recording_source(self) -> str:
        if self._network_source:
            return self._network_source
        if not self.current:
            raise RecordingError("open a local file or network stream first")
        route = detect_local_playback_kind(self.current)
        if route in {LOCAL_CASUNAT1, LOCAL_CASUNAT2}:
            raise RecordingError(
                "native CASU playback is already a stored source; use Convert/Export instead")
        source = self._source_for(self.current, route)
        return str(source)

    def toggle_recording(self) -> None:
        """Start or safely finalize an independent all-stream recording."""
        if self._recorder is not None:
            self._finish_recording_async()
            return
        try:
            source = self._recording_source()
        except (CasuError, RecordingError, OSError) as exc:
            messagebox.showerror("MPCASU · Record", str(exc), parent=self)
            return
        initial = (self.current.stem if self.current else "network-recording") + ".mkv"
        destination = filedialog.asksaveasfilename(
            parent=self, title="Save recording", initialfile=initial,
            defaultextension=".mkv",
            filetypes=[("Matroska", "*.mkv"), ("MPEG-4", "*.mp4"),
                       ("MPEG transport stream", "*.ts"), ("WebM", "*.webm"),
                       ("Audio", "*.ogg *.mp3 *.flac *.wav"), ("All files", "*.*")])
        if not destination:
            return
        try:
            recorder = MediaRecorder(source, destination)
            recorder.start()
        except (RecordingError, OSError) as exc:
            messagebox.showerror("MPCASU · Record", str(exc), parent=self)
            return
        self._recorder = recorder
        self.record_button.configure(text="■ Stop record")
        self.status.set(f"Recording all compatible streams · {Path(destination).name}")

    def _finish_recording_async(self) -> None:
        recorder = self._recorder
        if recorder is None or self._recording_finishing:
            return
        self._recording_finishing = True
        self.record_button.configure(text="Finalizing…", state="disabled")
        self.status.set("Finalizing and verifying recording…")

        def worker() -> None:
            try:
                result, error = recorder.finish(timeout=5), None
            except (RecordingError, OSError) as exc:
                result, error = None, exc

            def present() -> None:
                if self._recorder is recorder:
                    self._recorder = None
                self._recording_finishing = False
                self.record_button.configure(text="● Record", state="normal")
                if error is None:
                    self.status.set(f"Recording saved and verified · {result.name}")
                else:
                    self.status.set(f"Recording failed verification: {error}")
                    messagebox.showerror("MPCASU · Record", str(error), parent=self)
            try:
                self.after(0, present)
            except tk.TclError:
                pass
        threading.Thread(target=worker, name="mpcasu-record-finalize", daemon=True).start()

    def stop(self):
        if self._recorder is not None and not self._recording_finishing:
            self._finish_recording_async()
        if self.backend:
            self._persist_media_preferences()
            self._retire_backend()
        self._draw_chapter_markers(())
        self._paused = False
        self._set_diagnostics(support="Legacy backend", integrity="unavailable", segmented="unavailable", energy="unavailable — not measured")

    def _retire_backend(self, expected=None) -> None:
        """Detach immediately and release libVLC off Tk's event thread.

        Some output modules block in libvlc_media_player_stop when an audio
        server disappears. Keeping that third-party teardown off Tk prevents
        the entire player from freezing while the OS/runtime unwinds it.
        """
        if expected is not None and self.backend is not expected:
            return
        backend = self.controller.detach()
        if backend is None:
            backend = self.backend
        if backend is None:
            return
        if getattr(backend, "on_event", None) is not None:
            backend.on_event = None
        if self.backend is backend:
            self.backend = None

        def cleanup() -> None:
            try:
                backend.close()
            except (BackendError, OSError, RuntimeError):
                pass
        threading.Thread(target=cleanup, name="mpcasu-backend-close",
                         daemon=True).start()

    def seek_by(self, seconds: float):
        self.position.set(max(0.0, min(self.duration, self.position.get() + seconds)))
        self.seek_restart()

    def seek_preview(self, _value):
        if self._dragging:
            return

    def seek_restart(self):
        if not self.current and not self._network_source:
            return
        offset = self.position.get()
        if self.current:
            try:
                self._source_for(self.current)
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

    def _update_stream_epg(self) -> None:
        channel = self._stream_channel
        if channel is None or not channel.epg_id:
            return
        minute = int(time.time() // 60)
        if minute == self._last_epg_minute:
            return
        self._last_epg_minute = minute
        current, following = self._epg_guide.now_next(channel.epg_id)
        if current:
            self.now_playing.configure(
                text=f"LIVE · {channel.name} · {current.title}".upper())
            self.status.set(
                f"EPG now · {current.start.astimezone():%H:%M}–{current.stop.astimezone():%H:%M} · "
                f"next: {following.title if following else 'not listed'}")

    def _sync_position(self):
        if self.backend and not self._paused:
            self.position.set(min(self.duration, self.backend.position()))

    def _update_resource_telemetry(self) -> None:
        text, self._resource_cpu, self._resource_wall = process_resource_snapshot(
            self._resource_cpu, self._resource_wall)
        self.resource_status.set(text)
        variable = self._diagnostic_vars.get("RESOURCE USE")
        if variable is not None:
            variable.set(text)

    def _poll(self):
        self._drain_backend_events()
        self._update_resource_telemetry()
        self._update_stream_epg()
        self._visual_phase += 1.5
        if (self._recorder is not None and not self._recorder.active and
                not self._recording_finishing):
            self._finish_recording_async()
        if self.backend and not self._dragging and not self._paused:
            self._sync_position()
            if self.backend.state() == PlaybackState.ENDED and not self._advancing and not self._end_handled:
                self._end_handled = True
                self._advancing = True
                try:
                    self.play_next(automatic=True)
                finally:
                    self._advancing = False
            if self._presentation_mode == "AUDIO":
                self._draw_visualizer()
            if (self._ab_start is not None and self._ab_end is not None and
                    self.backend.position() >= self._ab_end):
                try:
                    self.controller.seek(self._ab_start)
                    self.position.set(self._ab_start)
                except (BackendError, OSError, RuntimeError):
                    self._ab_start = self._ab_end = None
                    self.status.set("A–B repeat stopped because seeking failed")
        self.after(500, self._poll)


def main() -> int:
    initial = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else None
    MPCASUPlayer(initial).mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
