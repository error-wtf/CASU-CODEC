# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Small, accessible Tk front-end for the CASU converter.

The CLI remains the automation/reference interface; this window only collects
the same explicit options and runs the converter without changing the source.
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

BG = "#090B0D"
PANEL = "#111418"
PANEL_ALT = "#14181D"
RED = "#FF1E2D"
TEXT = "#F2F2F2"
SECONDARY = "#A7ABB0"


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
        self.geometry("980x700")
        self.minsize(600, 360)
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
        self.status = tk.StringVar(value="Choose media or CASU source files.")
        self.source_info = tk.StringVar(value="No source inspected")
        self.output_info = tk.StringVar(value="The original source is never modified.")
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._busy = False
        self._paused = False
        self._inspection_generation = 0
        self._ui_queue: queue.SimpleQueue[object] = queue.SimpleQueue()
        self._destroying = False
        self._ui_after_id: str | None = None
        self._build()
        self._ui_after_id = self.after(40, self._drain_ui_queue)

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
        super().destroy()

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
        ttk.Label(options, text="Direction").pack(side="left")
        ttk.Combobox(options, textvariable=self.direction,
                     values=("media-to-media", "to-casu", "from-casu"),
                     state="readonly", width=15).pack(side="left", padx=(8, 14))
        ttk.Label(options, text="Analysis mode").pack(side="left")
        ttk.Combobox(options, textvariable=self.mode, values=sorted(ANALYSIS_MODES), state="readonly", width=18).pack(side="left", padx=8)
        ttk.Label(options, text="FPS").pack(side="left")
        ttk.Spinbox(options, from_=0.1, to=120.0, increment=0.5, textvariable=self.fps, width=8).pack(side="left", padx=8)
        ttk.Label(options, text="Retries").pack(side="left")
        ttk.Spinbox(options, from_=0, to=10, increment=1,
                    textvariable=self.retries, width=4).pack(side="left", padx=6)
        ttk.Checkbutton(options, text="Standalone segmented CASUNAT2", variable=self.native_output).pack(side="left", padx=12)
        ttk.Checkbutton(options, text="Resume verified jobs", variable=self.resume_jobs).pack(side="left", padx=4)
        segmentation = tk.Frame(root, bg=BG); segmentation.pack(fill="x", pady=(0, 6))
        ttk.Label(segmentation, text="CASU tile size").pack(side="left")
        ttk.Spinbox(segmentation, from_=8, to=1024, increment=8,
                    textvariable=self.tile_size, width=7).pack(side="left", padx=(8, 14))
        ttk.Label(segmentation, text="Key-state interval (s)").pack(side="left")
        ttk.Spinbox(segmentation, from_=0.1, to=3600.0, increment=0.5,
                    textvariable=self.key_interval_seconds, width=8).pack(side="left", padx=8)
        ttk.Label(segmentation,
                  text="Used by standalone CASUNAT2 encoding and recorded in the report.").pack(side="left")
        export_options = tk.Frame(root, bg=BG); export_options.pack(fill="x", pady=(0, 6))
        ttk.Label(export_options, text="Output format").pack(side="left")
        ttk.Combobox(export_options, textvariable=self.export_format,
                     values=tuple(sorted(extension.lstrip(".")
                                         for extension in MEDIA_OUTPUT_EXTENSIONS)),
                     state="normal",
                     width=10).pack(side="left", padx=8)
        ttk.Label(export_options,
                  text="Used for From-CASU and Media-to-Media batches.").pack(side="left")
        media_options = tk.Frame(root, bg=BG); media_options.pack(fill="x", pady=(0, 6))
        ttk.Label(media_options, text="Media profile").pack(side="left")
        ttk.Combobox(media_options, textvariable=self.media_preset,
                     values=tuple(sorted(MEDIA_PRESETS)), state="readonly",
                     width=10).pack(side="left", padx=(8, 12))
        ttk.Label(media_options, text="Video codec").pack(side="left")
        ttk.Combobox(media_options, textvariable=self.video_codec,
                     values=("auto", "libx264", "libx265", "libvpx-vp9",
                             "libaom-av1", "ffv1", "mpeg4", "mpeg2video"),
                     state="normal", width=12).pack(side="left", padx=(6, 12))
        ttk.Label(media_options, text="Audio codec").pack(side="left")
        ttk.Combobox(media_options, textvariable=self.audio_codec,
                     values=("auto", "aac", "libmp3lame", "libopus",
                             "libvorbis", "flac", "alac", "pcm_s16le"),
                     state="normal", width=12).pack(side="left", padx=(6, 12))
        ttk.Label(media_options, text="Subtitles").pack(side="left")
        ttk.Combobox(media_options, textvariable=self.subtitle_mode,
                     values=tuple(sorted(SUBTITLE_MODES)), state="readonly",
                     width=7).pack(side="left", padx=6)
        preservation = tk.Frame(root, bg=BG); preservation.pack(fill="x", pady=(0, 6))
        ttk.Checkbutton(preservation, text="All compatible tracks",
                        variable=self.all_tracks).pack(side="left")
        ttk.Checkbutton(preservation, text="Preserve metadata and chapters",
                        variable=self.preserve_metadata).pack(side="left", padx=12)
        ttk.Label(preservation,
                  text="Remux copies codecs; Lossless uses lossless codecs where the container permits.").pack(side="left")
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
            from_casu = self.direction.get() == "from-casu"
            try:
                self._set_sources(collect_folder_sources(folder, from_casu=from_casu))
            except CasuError as exc:
                messagebox.showerror("CASU", str(exc))

    def _set_sources(self, paths: list[Path]) -> None:
        self._sources = list(dict.fromkeys(path.expanduser().resolve() for path in paths if path.is_file()))
        if len(self._sources) > MAX_REPORT_RESULTS:
            self._sources = []
            messagebox.showerror("CASU", f"A batch is limited to {MAX_REPORT_RESULTS} files.")
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

    def convert(self) -> None:
        if self._busy:
            return
        sources = self._sources or []
        if not sources and self.source.get() and Path(self.source.get()).is_file():
            sources = [Path(self.source.get()).expanduser().resolve()]
        if not sources:
            messagebox.showerror("CASU", "Choose one or more existing source files first."); return
        direction = self.direction.get()
        from_casu = direction == "from-casu"
        media_to_media = direction == "media-to-media"
        try:
            casu_inputs = [detect_casu_kind(path) is not None for path in sources]
        except CasuError as exc:
            messagebox.showerror("CASU", str(exc)); return
        if from_casu and not all(casu_inputs):
            messagebox.showerror("CASU", "From-CASU mode accepts only verified CASU content."); return
        if not from_casu and any(casu_inputs):
            messagebox.showerror("CASU", "This mode expects ordinary media; use From-CASU for CASU content."); return
        if from_casu or media_to_media:
            try:
                extension = self._export_extension()
            except ValueError as exc:
                messagebox.showerror("CASU", str(exc)); return
            if extension not in MEDIA_OUTPUT_EXTENSIONS:
                messagebox.showerror("CASU", "The selected media output format is unsupported."); return
        output_dir = Path(self.output.get()).expanduser() if self.output.get() else sources[0].parent
        if output_dir.exists() and not output_dir.is_dir():
            messagebox.showerror("CASU", "Output must be a directory."); return
        output_dir.mkdir(parents=True, exist_ok=True)
        outputs = ([self._export_target_for(source, output_dir) for source in sources]
                   if from_casu or media_to_media else
                   [self._target_for(source, output_dir) for source in sources])
        if len(set(outputs)) != len(outputs):
            messagebox.showerror("CASU", "Multiple sources map to the same output name. Choose a different output folder or convert them separately.")
            return
        source_paths = {path.expanduser().resolve() for path in sources}
        if any(path.expanduser().resolve() in source_paths for path in outputs):
            messagebox.showerror(
                "CASU",
                "An output would overwrite its source. Choose another output "
                "folder or a different output format.",
            )
            return
        existing = [item for item in outputs if item.exists()]
        if existing and not messagebox.askyesno(
                "Replace output?", f"Replace {len(existing)} existing output file(s)?"):
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
        try:
            tile_size = int(self.tile_size.get())
            key_interval = float(self.key_interval_seconds.get())
        except (TypeError, ValueError, tk.TclError):
            messagebox.showerror("CASU", "Tile size and key-state interval must be numbers."); return
        if tile_size < 8 or tile_size > 1024:
            messagebox.showerror("CASU", "Tile size must be between 8 and 1024 pixels."); return
        if not math.isfinite(key_interval) or key_interval < 0.1 or key_interval > 3600.0:
            messagebox.showerror("CASU", "Key-state interval must be between 0.1 and 3600 seconds."); return
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
            self._post_ui(lambda: self._done(f"Conversion failed: {exc}", error=True))

    def verify_output(self) -> None:
        """Verify every CASU file in the selected output directory."""
        directory = Path(self.output.get()).expanduser() if self.output.get() else None
        if directory is None or not directory.is_dir():
            messagebox.showerror("CASU", "Choose an existing output folder first.")
            return
        if self.direction.get() in {"from-casu", "media-to-media"}:
            try:
                extension = self._export_extension()
            except ValueError as exc:
                messagebox.showerror("CASU Verify", str(exc))
                return
            files = sorted(directory.rglob(f"*{extension}"))
            if not files:
                messagebox.showinfo("CASU Verify", f"No {extension} exports found in the output folder.")
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
                messagebox.showerror("CASU Verify", f"{len(files) - len(failures)}/{len(files)} exports passed. Details: {report}")
            else:
                messagebox.showinfo("CASU Verify", f"{len(files)} exported media file(s) verified.\nReport: {report}")
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
        ttk.Label(controls, text="Filter").pack(side="left")
        search = ttk.Entry(controls, textvariable=query, width=38)
        search.pack(side="left", padx=(7, 12))
        ttk.Label(controls, text="Status").pack(side="left")
        status_box = ttk.Combobox(controls, textvariable=selected_status,
                                  values=("all", *statuses), state="readonly", width=14)
        status_box.pack(side="left", padx=7)
        count = tk.StringVar()
        tk.Label(controls, textvariable=count, bg=BG, fg=SECONDARY).pack(side="right")

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
                messagebox.showerror("CASU Report", str(exc), parent=dialog)
            else:
                messagebox.showinfo("CASU Report", f"Exported: {exported}", parent=dialog)

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
        (messagebox.showerror if error else messagebox.showinfo)("CASU Converter", message)


def main() -> int:
    CASUConverter().mainloop(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
