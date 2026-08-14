# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Accessible Tk front-end for the CASU converter (red/black design system).

The CLI remains the automation/reference interface; this window collects the
same explicit options and runs the converter without changing the source.

UX goals: three clear steps (source → direction → convert), direction-aware
options, advanced settings collapsed by default, and no modal popups — all
feedback is given as in-window toasts, status text or the inline replace bar.
"""
from __future__ import annotations

import json
import math
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from casu.design import (BG, PANEL, PANEL_ALT, LINE, RED, RED_DARK, TEXT,
                         SECONDARY, MUTED, TOAST_BG, TOAST_BORDER, INPUT_BG,
                         INPUT_BORDER, SCROLLBAR, TOKENS)
from casu.core import ANALYSIS_MODES, CasuCancelled, CasuError, ffprobe, duration
from casu.jobs import (ConversionCancelled, ConversionEngine, ConversionJob,
                       ConversionProfile, ConversionProgress,
                       MAX_REPORT_BYTES, MAX_REPORT_RESULTS,
                       conversion_journal_path, export_conversion_report_csv,
                       export_conversion_report_markdown,
                       filter_conversion_report, load_conversion_report,
                       write_conversion_report)
from casu.native import NativeCasuError, read_native
from casu.native_v2 import NativeV2Error, read_native_v2
from casu.schema import validate_manifest
from casu.export import CasuExportError, export_casu
from casu.fileio import atomic_write_json, read_bounded_json
from casu.filetypes import MAX_SIDECAR_BYTES, detect_casu_kind
from casu.transcode import MEDIA_OUTPUT_EXTENSIONS, MEDIA_PRESETS, SUBTITLE_MODES


def collect_folder_sources(folder: str | Path, *, from_casu: bool) -> list[Path]:
    """Collect a bounded, symlink-contained batch using verified file content."""
    root = Path(folder).expanduser().resolve()
    result: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        source = path.resolve()
        try:
            source.relative_to(root)
        except ValueError:
            continue
        if (detect_casu_kind(source) is not None) != from_casu:
            continue
        result.append(source)
        if len(result) > MAX_REPORT_RESULTS:
            raise CasuError(f"folder contains more than {MAX_REPORT_RESULTS} eligible files")
    return sorted(set(result))


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
        self.title("CASU Full Media Converter")
        self.geometry("1000x760")
        self.minsize(680, 420)
        self.source = tk.StringVar()
        self.output = tk.StringVar()
        self._sources: list[Path] = []
        self._source_root: Path | None = None
        self.mode = tk.StringVar(value="strict")
        self.direction = tk.StringVar(value="media-to-media")
        self.export_format = tk.StringVar(value="mp4")
        self.media_preset = tk.StringVar(value="balanced")
        self.video_codec = tk.StringVar(value="auto")
        self.audio_codec = tk.StringVar(value="auto")
        self.subtitle_mode = tk.StringVar(value="auto")
        self.all_tracks = tk.BooleanVar(value=True)
        self.preserve_metadata = tk.BooleanVar(value=True)
        # Native CASUNAT2 is standalone and the preferred CASU output. The
        # sidecar remains available by explicitly clearing this option.
        self.native_output = tk.BooleanVar(value=True)
        self.resume_jobs = tk.BooleanVar(value=True)
        self.fps = tk.DoubleVar(value=10.0)
        self.tile_size = tk.IntVar(value=64)
        self.key_interval_seconds = tk.DoubleVar(value=3.0)
        self.retries = tk.IntVar(value=0)
        self.status = tk.StringVar(value="Step 1 — choose media or CASU source files.")
        self.source_info = tk.StringVar(value="No source inspected")
        self.output_info = tk.StringVar(value="The original source is never modified.")
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._busy = False
        self._paused = False
        self._inspection_generation = 0
        self._pending_start = None
        self._packed_rows: set = set()
        self._toast_after_id: str | None = None
        self._ui_queue: queue.SimpleQueue[object] = queue.SimpleQueue()
        self._destroying = False
        self._ui_after_id: str | None = None
        self._build()
        self._ui_after_id = self.after(40, self._drain_ui_queue)

    # --- UI plumbing ---

    def _post_ui(self, callback) -> None:
        if threading.current_thread() is threading.main_thread() and not self._destroying:
            callback()
            return
        self._ui_queue.put(callback)

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                callback = self._ui_queue.get_nowait()
                callback()
        except queue.Empty:
            pass
        if not self._destroying:
            try:
                self._ui_after_id = self.after(40, self._drain_ui_queue)
            except tk.TclError:
                self._ui_after_id = None

    def destroy(self) -> None:
        self._destroying = True
        if self._ui_after_id is not None:
            try:
                self.after_cancel(self._ui_after_id)
            except tk.TclError:
                pass
            self._ui_after_id = None
        if self._toast_after_id is not None:
            try:
                self.after_cancel(self._toast_after_id)
            except tk.TclError:
                pass
            self._toast_after_id = None
        super().destroy()

    def toast(self, text: str, *, error: bool = False) -> None:
        """Web-player style transient message — replaces modal popups."""
        if self._destroying:
            return
        self._toast.configure(text=str(text),
                              fg=TOKENS.text if not error else "#ffb4b4",
                              highlightbackground=RED if error else TOAST_BORDER)
        self._toast.update_idletasks()
        width = min(self._toast.winfo_reqwidth(), max(360, self.winfo_width() - 48))
        x = max(24, (self.winfo_width() - width) // 2)
        y = max(12, self.winfo_height() - self._toast.winfo_reqheight() - 46)
        self._toast.place(x=x, y=y, width=width)
        self._toast.lift()
        if self._toast_after_id is not None:
            try:
                self.after_cancel(self._toast_after_id)
            except tk.TclError:
                pass
        self._toast_after_id = self.after(TOKENS.toast_ms, self._toast.place_forget)

    # --- Layout ---

    def _build(self) -> None:
        self.configure(bg=BG)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("CASU.TButton", background=PANEL_ALT, foreground=TEXT,
                        borderwidth=0, padding=(12, 7))
        style.map("CASU.TButton", background=[("active", RED_DARK), ("disabled", PANEL)],
                  foreground=[("disabled", MUTED)])
        style.configure("CASU.Primary.TButton", background=RED, foreground="#ffffff",
                        borderwidth=0, padding=(22, 10), font=("TkDefaultFont", 11, "bold"))
        style.map("CASU.Primary.TButton", background=[("active", "#ff3a47"), ("disabled", RED_DARK)],
                  foreground=[("disabled", MUTED)])
        style.configure("CASU.TEntry", fieldbackground=INPUT_BG, foreground=TEXT,
                        bordercolor=INPUT_BORDER, insertcolor=TEXT)
        style.configure("TEntry", fieldbackground=INPUT_BG, foreground=TEXT,
                        bordercolor=INPUT_BORDER, insertcolor=TEXT)
        style.configure("TCombobox", fieldbackground=INPUT_BG, background=PANEL_ALT,
                        foreground=TEXT, arrowcolor=SECONDARY, bordercolor=INPUT_BORDER)
        style.map("TCombobox", fieldbackground=[("readonly", INPUT_BG)],
                  foreground=[("readonly", TEXT)])
        style.configure("TSpinbox", fieldbackground=INPUT_BG, background=PANEL_ALT,
                        foreground=TEXT, arrowcolor=SECONDARY, bordercolor=INPUT_BORDER)
        style.configure("TCheckbutton", background=BG, foreground=SECONDARY)
        style.map("TCheckbutton", background=[("active", BG)])
        style.configure("CASU.TRadiobutton", background=BG, foreground=TEXT,
                        indicatorcolor=RED, font=("TkDefaultFont", 10, "bold"))
        style.map("CASU.TRadiobutton", background=[("active", BG)])
        style.configure("CASU.Horizontal.TProgressbar", background=RED, troughcolor=LINE,
                        bordercolor=LINE, lightcolor=RED, darkcolor=RED_DARK)
        style.configure("Vertical.TScrollbar", background=PANEL_ALT, troughcolor=BG,
                        bordercolor=BG, arrowcolor=SECONDARY)
        style.map("Vertical.TScrollbar", background=[("active", RED_DARK)])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=TEXT, rowheight=24, borderwidth=0)
        style.configure("Treeview.Heading", background=PANEL_ALT, foreground=RED,
                        borderwidth=0, font=("TkDefaultFont", 8, "bold"))

        root = tk.Frame(self, bg=BG, padx=24, pady=18)
        root.pack(fill="both", expand=True)

        logo_path = _asset_path("casu_codec_logo_header.png")
        self._logo_image = None
        try:
            image = tk.PhotoImage(file=str(logo_path))
            self._logo_image = image.subsample(max(1, image.width() // 140),
                                               max(1, image.height() // 60))
            self.iconphoto(True, self._logo_image)
            tk.Label(root, image=self._logo_image, bg=BG).pack(anchor="w")
        except (tk.TclError, OSError):
            tk.Label(root, text="CASU CONVERTER", bg=BG, fg=RED,
                     font=("TkDefaultFont", 22, "bold")).pack(anchor="w")
        tk.Label(root, text="Codec for All Segmented Units · source media remains untouched",
                 bg=BG, fg=MUTED).pack(anchor="w", pady=(0, 14))

        # --- Step 1: sources ---
        step1 = tk.Frame(root, bg=PANEL, padx=16, pady=12)
        step1.pack(fill="x")
        tk.Label(step1, text="1 · SOURCES", bg=PANEL, fg=RED,
                 font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
        for label, variable, command in (("Source files", self.source, self.choose_source),
                                         ("Output folder", self.output, self.choose_output)):
            row = tk.Frame(step1, bg=PANEL)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=label, width=14, bg=PANEL, fg=SECONDARY, anchor="w").pack(side="left")
            ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Browse…", style="CASU.TButton", command=command).pack(side="left", padx=(8, 0))
        folder_actions = tk.Frame(step1, bg=PANEL)
        folder_actions.pack(fill="x", pady=(4, 2))
        ttk.Button(folder_actions, text="Add folder (recursive)", style="CASU.TButton",
                   command=self.choose_folder).pack(side="left")
        ttk.Button(folder_actions, text="Remove selected", style="CASU.TButton",
                   command=self.remove_selected).pack(side="left", padx=6)
        ttk.Button(folder_actions, text="Clear queue", style="CASU.TButton",
                   command=self.clear_queue).pack(side="left")
        tk.Label(folder_actions, text="Each file is probed independently.",
                 bg=PANEL, fg=MUTED).pack(side="left", padx=10)
        self.queue = tk.Listbox(step1, height=4, bg=INPUT_BG, fg=TEXT,
                                selectbackground=RED_DARK, selectforeground=TEXT,
                                relief="flat", highlightthickness=0, activestyle="none",
                                exportselection=False)
        self.queue.pack(fill="x", pady=(4, 6))
        tk.Label(step1, text="SOURCE INSPECTION", bg=PANEL, fg=RED,
                 font=("TkDefaultFont", 8, "bold")).pack(anchor="w")
        tk.Label(step1, textvariable=self.source_info, bg=PANEL, fg=TEXT,
                 anchor="w", justify="left", wraplength=880).pack(fill="x", pady=(2, 0))
        tk.Label(step1, textvariable=self.output_info, bg=PANEL, fg=MUTED,
                 anchor="w").pack(fill="x", pady=(2, 0))

        # --- Step 2: direction ---
        step2 = tk.Frame(root, bg=PANEL, padx=16, pady=12)
        step2.pack(fill="x", pady=(10, 0))
        tk.Label(step2, text="2 · DIRECTION", bg=PANEL, fg=RED,
                 font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
        directions = tk.Frame(step2, bg=PANEL)
        directions.pack(fill="x", pady=(6, 0))
        for text, value, hint in (
                ("Media → Media", "media-to-media", "transcode between legacy formats"),
                ("To CASU", "to-casu", "pack media into segmented CASU"),
                ("From CASU", "from-casu", "export CASU back to media")):
            cell = tk.Frame(directions, bg=PANEL)
            cell.pack(side="left", padx=(0, 26))
            ttk.Radiobutton(cell, text=text, value=value, variable=self.direction,
                            style="CASU.TRadiobutton",
                            command=self._sync_direction).pack(anchor="w")
            tk.Label(cell, text=hint, bg=PANEL, fg=MUTED,
                     font=("TkDefaultFont", 8)).pack(anchor="w", padx=(24, 0))

        # --- Step 3: direction-aware options ---
        step3 = tk.Frame(root, bg=PANEL, padx=16, pady=12)
        step3.pack(fill="x", pady=(10, 0))
        tk.Label(step3, text="3 · OPTIONS", bg=PANEL, fg=RED,
                 font=("TkDefaultFont", 9, "bold")).pack(anchor="w")

        self._casu_row = tk.Frame(step3, bg=PANEL)
        ttk.Checkbutton(self._casu_row, text="Standalone segmented CASUNAT2 (recommended)",
                        variable=self.native_output).pack(side="left")
        tk.Label(self._casu_row, text="Sidecar output remains available by clearing this option.",
                 bg=PANEL, fg=MUTED).pack(side="left", padx=12)

        self._fmt_row = tk.Frame(step3, bg=PANEL)
        ttk.Label(self._fmt_row, text="Output format", background=PANEL,
                  foreground=SECONDARY).pack(side="left")
        ttk.Combobox(self._fmt_row, textvariable=self.export_format,
                     values=tuple(sorted(extension.lstrip(".")
                                         for extension in MEDIA_OUTPUT_EXTENSIONS)),
                     state="normal", width=10).pack(side="left", padx=(8, 12))
        tk.Label(self._fmt_row, text="Container used for the exported media.",
                 bg=PANEL, fg=MUTED).pack(side="left")

        self._preset_row = tk.Frame(step3, bg=PANEL)
        ttk.Label(self._preset_row, text="Media profile", background=PANEL,
                  foreground=SECONDARY).pack(side="left")
        ttk.Combobox(self._preset_row, textvariable=self.media_preset,
                     values=tuple(sorted(MEDIA_PRESETS)), state="readonly",
                     width=10).pack(side="left", padx=(8, 12))
        tk.Label(self._preset_row,
                 text="Remux copies codecs; Lossless uses lossless codecs where the container permits.",
                 bg=PANEL, fg=MUTED).pack(side="left")

        self._advanced_btn = tk.Label(step3, text="▸ Advanced options", bg=PANEL, fg=SECONDARY,
                                      cursor="hand2", font=("TkDefaultFont", 9, "bold"))
        self._advanced_btn.pack(anchor="w", pady=(8, 0))
        self._advanced_btn.bind("<Button-1>", lambda _event: self._toggle_advanced())

        self._advanced_frame = tk.Frame(step3, bg=PANEL_ALT, padx=14, pady=10)
        row_a = tk.Frame(self._advanced_frame, bg=PANEL_ALT)
        row_a.pack(fill="x", pady=2)
        ttk.Label(row_a, text="Analysis mode", background=PANEL_ALT, foreground=SECONDARY).pack(side="left")
        ttk.Combobox(row_a, textvariable=self.mode, values=sorted(ANALYSIS_MODES),
                     state="readonly", width=18).pack(side="left", padx=(8, 18))
        ttk.Label(row_a, text="Analysis FPS", background=PANEL_ALT, foreground=SECONDARY).pack(side="left")
        ttk.Spinbox(row_a, from_=0.1, to=120.0, increment=0.5,
                    textvariable=self.fps, width=8).pack(side="left", padx=(8, 18))
        ttk.Label(row_a, text="Retries", background=PANEL_ALT, foreground=SECONDARY).pack(side="left")
        ttk.Spinbox(row_a, from_=0, to=10, increment=1,
                    textvariable=self.retries, width=4).pack(side="left", padx=(8, 0))
        row_b = tk.Frame(self._advanced_frame, bg=PANEL_ALT)
        row_b.pack(fill="x", pady=2)
        ttk.Label(row_b, text="CASU tile size", background=PANEL_ALT, foreground=SECONDARY).pack(side="left")
        ttk.Spinbox(row_b, from_=8, to=1024, increment=8,
                    textvariable=self.tile_size, width=7).pack(side="left", padx=(8, 18))
        ttk.Label(row_b, text="Key-state interval (s)", background=PANEL_ALT,
                  foreground=SECONDARY).pack(side="left")
        ttk.Spinbox(row_b, from_=0.1, to=3600.0, increment=0.5,
                    textvariable=self.key_interval_seconds, width=8).pack(side="left", padx=(8, 0))
        row_c = tk.Frame(self._advanced_frame, bg=PANEL_ALT)
        row_c.pack(fill="x", pady=2)
        ttk.Label(row_c, text="Video codec", background=PANEL_ALT, foreground=SECONDARY).pack(side="left")
        ttk.Combobox(row_c, textvariable=self.video_codec,
                     values=("auto", "libx264", "libx265", "libvpx-vp9",
                             "libaom-av1", "ffv1", "mpeg4", "mpeg2video"),
                     state="normal", width=12).pack(side="left", padx=(8, 18))
        ttk.Label(row_c, text="Audio codec", background=PANEL_ALT, foreground=SECONDARY).pack(side="left")
        ttk.Combobox(row_c, textvariable=self.audio_codec,
                     values=("auto", "aac", "libmp3lame", "libopus",
                             "libvorbis", "flac", "alac", "pcm_s16le"),
                     state="normal", width=12).pack(side="left", padx=(8, 18))
        ttk.Label(row_c, text="Subtitles", background=PANEL_ALT, foreground=SECONDARY).pack(side="left")
        ttk.Combobox(row_c, textvariable=self.subtitle_mode,
                     values=tuple(sorted(SUBTITLE_MODES)), state="readonly",
                     width=7).pack(side="left", padx=(8, 0))
        row_d = tk.Frame(self._advanced_frame, bg=PANEL_ALT)
        row_d.pack(fill="x", pady=2)
        ttk.Checkbutton(row_d, text="All compatible tracks", variable=self.all_tracks).pack(side="left")
        ttk.Checkbutton(row_d, text="Preserve metadata and chapters",
                        variable=self.preserve_metadata).pack(side="left", padx=14)
        ttk.Checkbutton(row_d, text="Resume verified jobs", variable=self.resume_jobs).pack(side="left")

        # --- Inline replace confirmation (no popup) ---
        self._confirm_frame = tk.Frame(root, bg=RED_DARK, padx=14, pady=8)
        self._confirm_label = tk.Label(self._confirm_frame, text="", bg=RED_DARK, fg=TEXT)
        self._confirm_label.pack(side="left")
        ttk.Button(self._confirm_frame, text="Keep existing", style="CASU.TButton",
                   command=self._cancel_replace).pack(side="right")
        ttk.Button(self._confirm_frame, text="Replace files", style="CASU.Primary.TButton",
                   command=self._confirm_replace).pack(side="right", padx=(0, 8))

        # --- Actions + progress ---
        actions = tk.Frame(root, bg=BG)
        self._actions_frame = actions
        actions.pack(fill="x", pady=(14, 0))
        self.convert_button = ttk.Button(actions, text="Convert", style="CASU.Primary.TButton",
                                         command=self.convert)
        self.convert_button.pack(side="left")
        ttk.Button(actions, text="Verify output", style="CASU.TButton",
                   command=self.verify_output).pack(side="left", padx=(10, 0))
        ttk.Button(actions, text="Last report", style="CASU.TButton",
                   command=self.show_last_report).pack(side="left", padx=(10, 0))
        self.pause_button = ttk.Button(actions, text="Pause queue", style="CASU.TButton",
                                       command=self.pause_queue, state="disabled")
        self.pause_button.pack(side="right", padx=(10, 0))
        self.cancel_button = ttk.Button(actions, text="Cancel", style="CASU.TButton",
                                        command=self.cancel, state="disabled")
        self.cancel_button.pack(side="right")

        self.progress = ttk.Progressbar(root, mode="determinate", maximum=100.0,
                                        style="CASU.Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(12, 4))
        tk.Label(root, textvariable=self.status, wraplength=920, bg=BG, fg=SECONDARY,
                 anchor="w", justify="left").pack(fill="x", pady=4)

        self._toast = tk.Label(self, text="", bg=TOAST_BG, fg=TEXT, padx=14, pady=9,
                               wraplength=640, justify="left", relief="solid",
                               borderwidth=1, highlightthickness=1,
                               highlightbackground=TOAST_BORDER)
        self._toast.place_forget()

        self._sync_direction()

    def _sync_direction(self) -> None:
        direction = self.direction.get()
        for frame, visible in ((self._casu_row, direction == "to-casu"),
                               (self._fmt_row, direction in {"from-casu", "media-to-media"}),
                               (self._preset_row, direction == "media-to-media")):
            packed = frame in self._packed_rows
            if visible and not packed:
                frame.pack(fill="x", pady=3)
                self._packed_rows.add(frame)
            elif not visible and packed:
                frame.pack_forget()
                self._packed_rows.discard(frame)

    def _toggle_advanced(self) -> None:
        if self._advanced_frame.winfo_ismapped():
            self._advanced_frame.pack_forget()
            self._advanced_btn.configure(text="▸ Advanced options")
        else:
            self._advanced_frame.pack(fill="x", pady=(6, 0))
            self._advanced_btn.configure(text="▾ Advanced options")

    # --- Source selection ---

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
            from_casu = self.direction.get() == "from-casu"
            try:
                self._set_sources(collect_folder_sources(folder, from_casu=from_casu))
            except CasuError as exc:
                self.toast(str(exc), error=True)
                self.status.set(f"Folder rejected: {exc}")

    def _set_sources(self, paths: list[Path]) -> None:
        self._sources = list(dict.fromkeys(path.expanduser().resolve() for path in paths if path.is_file()))
        if len(self._sources) > MAX_REPORT_RESULTS:
            self._sources = []
            self.toast(f"A batch is limited to {MAX_REPORT_RESULTS} files.", error=True)
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
        if path:
            self.output.set(path)

    def inspect_source(self, path: Path) -> None:
        self._inspection_generation += 1
        generation = self._inspection_generation
        try:
            key_interval = max(.001, float(self.key_interval_seconds.get()))
        except (tk.TclError, TypeError, ValueError):
            key_interval = 3.0
        self.source_info.set(f"Inspecting {path.name}…")

        def worker() -> None:
            try:
                if detect_casu_kind(path) is not None:
                    text = (f"{path.name} · CASU content detected · "
                            f"{path.stat().st_size} bytes · use Verify output for full integrity")
                else:
                    probe = ffprobe(path)
                    streams = probe.get("streams", [])
                    videos = [item for item in streams if item.get("codec_type") == "video"
                              and not item.get("disposition", {}).get("attached_pic")]
                    audio = sum(item.get("codec_type") == "audio" for item in streams)
                    subtitles = sum(item.get("codec_type") == "subtitle" for item in streams)
                    attachments = sum(bool(item.get("codec_type") == "attachment" or
                                           item.get("disposition", {}).get("attached_pic"))
                                      for item in streams)
                    length = duration(probe); video = videos[0] if videos else {}
                    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
                    pixel = str(video.get("pix_fmt") or "n/a")
                    bit_match = re.search(r"p(\d{2})(?:le|be)?$", pixel)
                    depth = int(video.get("bits_per_raw_sample") or
                                (bit_match.group(1) if bit_match else 8)) if video else 0
                    key_estimate = sum(max(1, math.ceil(length / key_interval))
                                       for _ in videos)
                    text = (f"{path.name} · {len(streams)} streams · {length:.3f} s · "
                            f"video {len(videos)} ({width}×{height}, {pixel}, {depth}-bit) · "
                            f"audio {audio} · subtitles {subtitles} · "
                            f"chapters {len(probe.get('chapters', []))} · attachments {attachments} · "
                            f"ESTIMATE ≥{key_estimate} periodic key states; tile updates require exact analysis")
            except (CasuError, OSError, ValueError, TypeError) as exc:
                text = f"Inspection unavailable: {exc}"

            def present() -> None:
                if generation == self._inspection_generation:
                    self.source_info.set(text)
            self._post_ui(present)
        threading.Thread(target=worker, name="casu-source-inspection", daemon=True).start()

    # --- Conversion entry point ---

    def convert(self) -> None:
        if self._busy:
            return
        sources = self._sources or []
        if not sources and self.source.get() and Path(self.source.get()).is_file():
            sources = [Path(self.source.get()).expanduser().resolve()]
        if not sources:
            self.toast("Choose one or more existing source files first.", error=True)
            self.status.set("Step 1 — choose media or CASU source files.")
            return
        direction = self.direction.get()
        from_casu = direction == "from-casu"
        media_to_media = direction == "media-to-media"
        try:
            casu_inputs = [detect_casu_kind(path) is not None for path in sources]
        except CasuError as exc:
            self.toast(str(exc), error=True)
            return
        if from_casu and not all(casu_inputs):
            self.toast("From-CASU mode accepts only verified CASU content.", error=True)
            return
        if not from_casu and any(casu_inputs):
            self.toast("This mode expects ordinary media; use From-CASU for CASU content.", error=True)
            return
        if from_casu or media_to_media:
            try:
                extension = self._export_extension()
            except ValueError as exc:
                self.toast(str(exc), error=True)
                return
            if extension not in MEDIA_OUTPUT_EXTENSIONS:
                self.toast("The selected media output format is unsupported.", error=True)
                return
        output_dir = Path(self.output.get()).expanduser() if self.output.get() else sources[0].parent
        if output_dir.exists() and not output_dir.is_dir():
            self.toast("Output must be a directory.", error=True)
            return
        output_dir.mkdir(parents=True, exist_ok=True)
        outputs = ([self._export_target_for(source, output_dir) for source in sources]
                   if from_casu or media_to_media else
                   [self._target_for(source, output_dir) for source in sources])
        if len(set(outputs)) != len(outputs):
            self.toast("Multiple sources map to the same output name. Choose a different "
                       "output folder or convert them separately.", error=True)
            return
        source_paths = {path.expanduser().resolve() for path in sources}
        if any(path.expanduser().resolve() in source_paths for path in outputs):
            self.toast("An output would overwrite its source. Choose another output "
                       "folder or a different output format.", error=True)
            return
        try:
            fps = float(self.fps.get())
        except (TypeError, ValueError):
            self.toast("FPS must be a finite positive number.", error=True)
            return
        if not math.isfinite(fps) or fps <= 0:
            self.toast("FPS must be positive.", error=True)
            return
        try:
            retries = int(self.retries.get())
        except (TypeError, ValueError, tk.TclError):
            self.toast("Retries must be an integer from 0 to 10.", error=True)
            return
        if retries < 0 or retries > 10:
            self.toast("Retries must be between 0 and 10.", error=True)
            return
        try:
            tile_size = int(self.tile_size.get())
            key_interval = float(self.key_interval_seconds.get())
        except (TypeError, ValueError, tk.TclError):
            self.toast("Tile size and key-state interval must be numbers.", error=True)
            return
        if tile_size < 8 or tile_size > 1024:
            self.toast("Tile size must be between 8 and 1024 pixels.", error=True)
            return
        if not math.isfinite(key_interval) or key_interval < 0.1 or key_interval > 3600.0:
            self.toast("Key-state interval must be between 0.1 and 3600 seconds.", error=True)
            return
        existing = [item for item in outputs if item.exists()]
        start = lambda: self._start_conversion(  # noqa: E731 - deferred start hook
            sources, output_dir, outputs, from_casu, media_to_media,
            fps, retries, tile_size, key_interval)
        if existing:
            self._pending_start = start
            self._confirm_label.configure(
                text=f"{len(existing)} output file(s) already exist — replace them?")
            self._confirm_frame.pack(fill="x", pady=(10, 0),
                                     before=self._actions_frame)
            self.status.set("Waiting for replace confirmation.")
            return
        start()

    def _confirm_replace(self) -> None:
        self._confirm_frame.pack_forget()
        start, self._pending_start = self._pending_start, None
        if start is not None:
            start()

    def _cancel_replace(self) -> None:
        self._confirm_frame.pack_forget()
        self._pending_start = None
        self.status.set("Replace cancelled — existing outputs were kept.")

    def _start_conversion(self, sources: list[Path], output_dir: Path,
                          outputs: list[Path], from_casu: bool,
                          media_to_media: bool, fps: float, retries: int,
                          tile_size: int, key_interval: float) -> None:
        mode = self.mode.get()
        self._cancel_event.clear()
        self._pause_event.set()
        self._paused = False
        self._busy = True
        self.cancel_button.configure(state="normal")
        self.pause_button.configure(state="normal", text="Pause queue")
        self.progress.configure(value=0.0)
        self.status.set("Preparing verified conversion jobs…")
        if from_casu:
            threading.Thread(target=self._export_worker,
                             args=(sources, output_dir, outputs,
                                   self.export_format.get()), daemon=True).start()
            return
        profile = ConversionProfile(
            container=("media" if media_to_media else
                       "native-v2" if self.native_output.get() else "sidecar"),
            mode=mode, analysis_fps=fps, tile_size=tile_size,
            key_interval_seconds=key_interval,
            media_preset=self.media_preset.get(),
            video_codec=self.video_codec.get().strip(),
            audio_codec=self.audio_codec.get().strip(),
            subtitle_mode=self.subtitle_mode.get(),
            all_tracks=self.all_tracks.get(),
            preserve_metadata=self.preserve_metadata.get(),
        )
        threading.Thread(target=self._worker, args=(
            sources, output_dir, fps, mode, self.native_output.get(),
            self.resume_jobs.get(), retries, media_to_media, profile, outputs,
            self.export_format.get()), daemon=True).start()

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

    def _export_target_for(self, source: Path, output_dir: Path) -> Path:
        extension = self._export_extension()
        if self._source_root is not None:
            try:
                relative = source.expanduser().resolve().relative_to(self._source_root)
            except ValueError:
                relative = Path(source.name)
            return (output_dir / relative).with_suffix(extension)
        return output_dir / f"{source.stem}{extension}"

    def _export_extension(self) -> str:
        value = self.export_format.get().strip().lower().lstrip(".")
        if not re.fullmatch(r"[a-z0-9]{1,12}", value):
            raise ValueError("Export format must be a 1–12 character filename extension.")
        return "." + value

    def _export_worker(self, sources: list[Path], output_dir: Path,
                       targets: list[Path] | None = None,
                       report_format: str | None = None) -> None:
        results = []
        total = len(sources)
        targets = targets or [self._export_target_for(source, output_dir)
                              for source in sources]
        report_format = report_format or self.export_format.get()
        try:
            for index, (source, target) in enumerate(zip(sources, targets)):
                if self._cancel_event.is_set():
                    break
                self._pause_event.wait()
                if self._cancel_event.is_set():
                    break
                started = time.monotonic()
                try:
                    export_casu(source, target)
                    results.append({"source": str(source), "output": str(target),
                                    "status": "exported",
                                    "conversion_seconds": round(time.monotonic() - started, 6)})
                except (CasuError, CasuExportError, OSError, ValueError) as exc:
                    results.append({"source": str(source), "output": str(target),
                                    "status": "failed", "error": str(exc),
                                    "conversion_seconds": round(time.monotonic() - started, 6)})
                fraction = (index + 1) / total
                position = index + 1
                self._post_ui(lambda fraction=fraction, source=source, position=position: (
                    self.progress.configure(value=fraction * 100),
                    self.status.set(f"Exported {source.name} ({position}/{total})"),
                ))
            cancelled = self._cancel_event.is_set()
            state = "CANCELLED" if cancelled else "COMPLETE"
            for source, target in zip(sources[len(results):], targets[len(results):]):
                results.append({"source": str(source),
                                "output": str(target),
                                "status": "cancelled"})
            write_conversion_report(output_dir / "casu_batch_report.json", {
                "version": 1, "state": state, "mode": "export",
                "container": report_format, "retries": 0,
                "files": results,
            })
            passed = sum(item["status"] == "exported" for item in results)
            self._post_ui(lambda: self._done(
                ("Export cancelled; completed files were retained." if cancelled else
                 f"Exported {passed}/{total} CASU file(s) to {output_dir}."),
                cancelled=cancelled))
        except Exception as exc:
            self._post_ui(lambda exc=exc: self._done(f"CASU export failed: {exc}", error=True))

    def _worker(self, sources: list[Path], output_dir: Path, fps: float, mode: str,
                native: bool, resume: bool, retries: int,
                media_to_media: bool = False,
                profile: ConversionProfile | None = None,
                targets: list[Path] | None = None,
                report_format: str | None = None) -> None:
        report_path = output_dir / "casu_batch_report.json"
        jobs: list[ConversionJob] = []
        try:
            total = len(sources)
            profile = profile or ConversionProfile(
                container=("media" if media_to_media else
                           "native-v2" if native else "sidecar"),
                mode=mode, analysis_fps=fps, tile_size=self.tile_size.get(),
                key_interval_seconds=self.key_interval_seconds.get(),
                media_preset=self.media_preset.get(), video_codec=self.video_codec.get().strip(),
                audio_codec=self.audio_codec.get().strip(), subtitle_mode=self.subtitle_mode.get(),
                all_tracks=self.all_tracks.get(), preserve_metadata=self.preserve_metadata.get(),
            )
            targets = targets or [(self._export_target_for(source, output_dir)
                                   if media_to_media else self._target_for(source, output_dir))
                                  for source in sources]
            report_format = report_format or (self.export_format.get() if media_to_media
                                               else profile.container)
            jobs = [ConversionJob(source, target, profile)
                    for source, target in zip(sources, targets)]
            def report(event: ConversionProgress) -> None:
                eta = ("ETA --" if event.eta_seconds is None else
                       f"ETA {int(round(event.eta_seconds))} s")
                name = Path(event.source).name
                self._post_ui(lambda event=event, name=name, eta=eta: (
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
                "version": 1, "state": "COMPLETE",
                "mode": "media-transcode" if media_to_media else mode,
                "container": report_format,
                "preset": profile.media_preset if media_to_media else None,
                "analysis_fps": fps, "retries": retries, "files": results,
                "tile_size": profile.tile_size,
                "key_interval_seconds": profile.key_interval_seconds,
            })
            converted = sum(item["status"] == "converted" for item in results)
            failed = len(results) - converted
            self._post_ui(lambda: self._done(
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
                "version": 1, "state": "CANCELLED",
                "mode": "media-transcode" if media_to_media else mode,
                "container": report_format,
                "analysis_fps": fps, "retries": retries,
                "tile_size": profile.tile_size,
                "key_interval_seconds": profile.key_interval_seconds,
                "files": completed + cancelled,
            })
            self._post_ui(lambda: self._done(
                "Conversion cancelled; no incomplete output was kept.",
                error=False, cancelled=True))
        except CasuCancelled:
            self._post_ui(lambda: self._done(
                "Conversion cancelled; no incomplete output was kept.",
                error=False, cancelled=True))
        except (CasuError, NativeCasuError, NativeV2Error, OSError, ValueError) as exc:
            self._post_ui(lambda exc=exc: self._done(f"Conversion failed: {exc}", error=True))

    def verify_output(self) -> None:
        """Verify every CASU file in the selected output directory."""
        directory = Path(self.output.get()).expanduser() if self.output.get() else None
        if directory is None or not directory.is_dir():
            self.toast("Choose an existing output folder first.", error=True)
            return
        if self.direction.get() in {"from-casu", "media-to-media"}:
            try:
                extension = self._export_extension()
            except ValueError as exc:
                self.toast(str(exc), error=True)
                return
            files = sorted(directory.rglob(f"*{extension}"))
            if not files:
                self.toast(f"No {extension} exports found in the output folder.")
                return
            failures = []
            for path in files:
                try:
                    overview = ffprobe(path)
                    if not any(item.get("codec_type") in {"audio", "video"}
                               for item in overview.get("streams", [])):
                        raise CasuError("no playable audio/video stream")
                except (CasuError, OSError, ValueError) as exc:
                    failures.append(f"{path.name}: {exc}")
            report = directory / "casu_media_verify_report.json"
            atomic_write_json(report, {"version": 1, "checked": len(files),
                                       "passed": len(files) - len(failures),
                                       "failed": len(failures), "errors": failures},
                              max_bytes=MAX_REPORT_BYTES)
            if failures:
                self.toast(f"{len(files) - len(failures)}/{len(files)} exports passed. "
                           f"Details: {report}", error=True)
            else:
                self.toast(f"{len(files)} exported media file(s) verified. Report: {report}")
            return
        files = sorted(directory.rglob("*.casu"))
        if not files:
            self.toast("No .casu files found in the output folder.")
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
                    manifest = read_bounded_json(path, max_bytes=MAX_SIDECAR_BYTES,
                                                 label="CASU sidecar")
                    errors = validate_manifest(manifest)
                    if errors:
                        raise ValueError(errors[0])
                passed += 1
            except (OSError, ValueError, json.JSONDecodeError, NativeCasuError,
                    NativeV2Error) as exc:
                failures.append(f"{path.name}: {exc}")
        report = directory / "casu_verify_report.json"
        atomic_write_json(report, {"version": 1, "checked": len(files),
                                   "passed": passed, "failed": len(failures),
                                   "errors": failures}, max_bytes=MAX_REPORT_BYTES)
        if failures:
            self.toast(f"{passed}/{len(files)} files passed. Details: {report}", error=True)
        else:
            self.toast(f"{passed}/{len(files)} files verified successfully. Report: {report}")

    def show_last_report(self) -> None:
        directory = Path(self.output.get()).expanduser() if self.output.get() else None
        if directory is None or not directory.is_dir():
            self.toast("Choose an existing output folder first.", error=True)
            return
        report = directory / "casu_batch_report.json"
        try:
            payload = load_conversion_report(report)
        except CasuError as exc:
            self.toast(str(exc), error=True)
            return
        dialog = tk.Toplevel(self); dialog.title("CASU · Last conversion report")
        dialog.geometry("1050x540"); dialog.minsize(700, 320)
        dialog.configure(bg=BG); dialog.transient(self)
        heading = (f"State: {payload.get('state', 'COMPLETE')}  ·  "
                   f"Container: {payload.get('container', 'unknown')}  ·  "
                   f"Mode: {payload.get('mode', 'unknown')}  ·  "
                   f"Retries: {payload.get('retries', 0)}")
        tk.Label(dialog, text=heading, bg=BG, fg=TEXT, anchor="w").pack(
            fill="x", padx=16, pady=(14, 8))

        controls = tk.Frame(dialog, bg=BG); controls.pack(fill="x", padx=16)
        query = tk.StringVar()
        statuses = sorted({str(item.get("status", "unknown"))
                           for item in payload["files"]}, key=str.casefold)
        selected_status = tk.StringVar(value="all")
        tk.Label(controls, text="Filter", bg=BG, fg=SECONDARY).pack(side="left")
        search = ttk.Entry(controls, textvariable=query, width=38)
        search.pack(side="left", padx=(7, 12))
        tk.Label(controls, text="Status", bg=BG, fg=SECONDARY).pack(side="left")
        status_box = ttk.Combobox(controls, textvariable=selected_status,
                                  values=("all", *statuses), state="readonly", width=14)
        status_box.pack(side="left", padx=7)
        count = tk.StringVar()
        tk.Label(controls, textvariable=count, bg=BG, fg=MUTED).pack(side="right")

        frame = tk.Frame(dialog, bg=BG); frame.pack(fill="both", expand=True, padx=16, pady=10)
        columns = ("status", "source", "output", "attempts", "time", "error")
        table = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        widths = {"status": 95, "source": 220, "output": 220,
                  "attempts": 70, "time": 85, "error": 300}
        for column in columns:
            table.heading(column, text=column.title())
            table.column(column, width=widths[column], minwidth=55,
                         stretch=column in {"source", "output", "error"})
        vertical = ttk.Scrollbar(frame, orient="vertical", command=table.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=table.xview)
        table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        table.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1); frame.columnconfigure(0, weight=1)

        def filtered() -> tuple[dict, ...]:
            return filter_conversion_report(payload, status=selected_status.get(),
                                            query=query.get())

        def refresh(*_args: object) -> None:
            table.delete(*table.get_children())
            rows = filtered()
            for item in rows:
                elapsed = item.get("conversion_seconds")
                try:
                    timing = "--" if elapsed is None else f"{float(elapsed):.2f} s"
                except (TypeError, ValueError):
                    timing = "--"
                table.insert("", "end", values=(
                    str(item.get("status", "unknown")).upper(),
                    str(item.get("source", "")), str(item.get("output", "")),
                    item.get("attempts", 0), timing, str(item.get("error") or "")))
            count.set(f"{len(rows)} / {len(payload['files'])} files")

        def export_visible(kind: str = "csv") -> None:
            markdown = kind == "markdown"
            target = filedialog.asksaveasfilename(parent=dialog,
                title="Export filtered conversion report",
                defaultextension=".md" if markdown else ".csv",
                initialfile=f"casu_batch_report.{('md' if markdown else 'csv')}",
                filetypes=(("Markdown", "*.md"), ("All files", "*")) if markdown
                else (("CSV spreadsheet", "*.csv"), ("All files", "*")))
            if not target:
                return
            try:
                exporter = (export_conversion_report_markdown if markdown
                            else export_conversion_report_csv)
                exported = exporter(payload, target, status=selected_status.get(),
                                    query=query.get())
            except (OSError, CasuError) as exc:
                self.toast(str(exc), error=True)
            else:
                self.toast(f"Exported: {exported}")

        actions = tk.Frame(dialog, bg=BG); actions.pack(fill="x", padx=16, pady=(0, 14))
        ttk.Button(actions, text="Export filtered CSV…", style="CASU.TButton",
                   command=export_visible).pack(side="left")
        ttk.Button(actions, text="Export filtered Markdown…", style="CASU.TButton",
                   command=lambda: export_visible("markdown")).pack(side="left", padx=8)
        ttk.Button(actions, text="Close", style="CASU.TButton",
                   command=dialog.destroy).pack(side="right")
        query.trace_add("write", refresh); status_box.bind("<<ComboboxSelected>>", refresh)
        refresh(); search.focus_set()

    def cancel(self) -> None:
        if self._busy:
            self._cancel_event.set()
            # Wake a paused batch so it can observe cancellation immediately.
            self._pause_event.set()
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
        self.toast(message, error=error)


def main() -> int:
    CASUConverter().mainloop(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
