# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""MPCASU Qt main window — full-featured media player UI."""
from __future__ import annotations

import json
import math
import os
import random
import threading
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer, Signal, Slot,
)
from PySide6.QtGui import (
    QAction, QColor, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap,
    QTextDocument, QImage,
)
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox,
    QStackedWidget, QStatusBar, QTextBrowser, QVBoxLayout, QWidget,
    QDoubleSpinBox, QGridLayout,
)

from casu.core import CasuError, ffprobe, resolve_casu_source
from casu.schema import validate_manifest
from casu.scheduler import CasuScheduler
from casu.library import MediaLibrary, PlaybackPreferences
from casu.media import TrackKind
from casu.playlist import PlaylistError, PlaylistModel
from casu.settings import PlayerSettings, SettingsStore
from casu.thumbnail import thumbnail_for

from casu.native import NativeCasuError, read_native
from casu.native_v2 import ChunkType, NativeV2Error, read_native_v2

from mpcasu_backend import (
    BackendError, CasuBackend, LibVLCBackend, PlaybackState,
    display_media_source,
)
from mpcasu_native_backend import NativeCasuBackend, PulseAudioSink
from mpcasu_playback import PlaybackController

from mpcasu_qt.theme import PALETTE, METRICS, format_duration, stylesheet
from mpcasu_qt.videoframe import VideoSurface

MEDIA_EXTENSIONS = {".mp4", ".mp3", ".mkv", ".m4v", ".mov", ".flac", ".wav", ".ogg", ".webm", ".m4a", ".aac", ".opus", ".aiff", ".alac", ".casu"}


class ChapterTimeline(QSlider):
    """Seek slider with chapter markers painted on top."""

    chaptersChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setObjectName("Timeline")
        self.setRange(0, 1000)
        self._chapters: list = []
        self._active_chapter = -1
        self._dragging = False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)

    def set_chapters(self, chapters, active=-1):
        self._chapters = list(chapters)
        self._active_chapter = int(active)
        self.update()

    def clear_chapters(self):
        self._chapters = []
        self._active_chapter = -1
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._chapters:
            return
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            groove_rect = self.style().subControlRect(
                self.style().CC_Slider, self.style().SC_SliderGroove, self
            ) if hasattr(self.style(), 'CC_Slider') else self.rect()
            if groove_rect.isNull() or groove_rect.width() <= 0:
                return
            width = max(1, groove_rect.width() - 16)
            offset = groove_rect.x() + 8
            for chapter in self._chapters:
                try:
                    identifier = int(chapter.identifier)
                    start = float(chapter.start_seconds) if hasattr(chapter, 'start_seconds') else 0.0
                    title = str(chapter.title) if hasattr(chapter, 'title') else ""
                except (AttributeError, ValueError, TypeError):
                    continue
                duration = max(1.0, float(self.maximum()))
                x = offset + int((start / duration) * width) if duration > 0 else offset
                x = max(offset, min(offset + width, x))
                color = QColor(PALETTE.accent) if identifier == self._active_chapter else QColor(PALETTE.text_faint)
                painter.setPen(QPen(color, 1.5))
                painter.setBrush(color)
                painter.drawRect(x - 2, groove_rect.y() + 2, 4, groove_rect.height() - 4)
        finally:
            painter.end()


class NowPlayingBar(QFrame):
    """Top bar showing current media metadata."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setFixedHeight(62)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)

        self.title_label = QLabel("NOW PLAYING · NO MEDIA SELECTED")
        self.title_label.setObjectName("BreadcrumbLabel")
        layout.addWidget(self.title_label)

        layout.addStretch()

        self.diagnostics_label = QLabel("CASU · LEGACY SAFE")
        self.diagnostics_label.setObjectName("NowPlayingMeta")
        layout.addWidget(self.diagnostics_label)

    def set_now_playing(self, text: str):
        self.title_label.setText(text.upper() if text else "NOW PLAYING · NO MEDIA SELECTED")

    def set_diagnostics_text(self, text: str):
        self.diagnostics_label.setText(text)


class Sidebar(QFrame):
    """Left navigation sidebar."""

    navRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(220)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        brand = QLabel("MPCASU")
        brand.setObjectName("BrandName")
        brand.setFixedHeight(32)
        brand.setContentsMargins(16, 16, 16, 0)
        layout.addWidget(brand)

        sub = QLabel("PLAYER")
        sub.setObjectName("BrandSub")
        sub.setFixedHeight(16)
        sub.setContentsMargins(44, 0, 16, 12)
        layout.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {PALETTE.border}; max-height: 1px;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        nav_items = [
            ("LIBRARY", ["LIBRARY", "PLAYLIST", "CASU FILES"]),
            ("SETTINGS", ["SETTINGS", "ABOUT"]),
        ]
        self._nav_buttons: list[QPushButton] = []
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for section_title, items in nav_items:
            section = QLabel(section_title)
            section.setObjectName("SidebarSection")
            layout.addWidget(section)
            for item in items:
                btn = QPushButton(item)
                btn.setObjectName("NavItem")
                btn.setCheckable(True)
                btn.setCursor(Qt.PointingHandCursor)
                btn.clicked.connect(lambda checked=False, name=item: self.navRequested.emit(name))
                self._nav_group.addButton(btn)
                self._nav_buttons.append(btn)
                layout.addWidget(btn)

        layout.addStretch()

        version = QLabel("MPCASU 1.0.0rc9")
        version.setObjectName("NowPlayingMeta")
        version.setContentsMargins(16, 8, 16, 8)
        version.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        layout.addWidget(version)

    def select(self, name: str):
        for btn in self._nav_buttons:
            if btn.text() == name:
                btn.setChecked(True)
                return

    def set_active(self, entry: str):
        for btn in self._nav_buttons:
            btn.setChecked(btn.text() == entry)


class PlaylistPane(QFrame):
    """Right-side playlist drawer."""

    playRequested = Signal(int)
    removeRequested = Signal(list)
    moveRequested = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PlaylistPane")
        self.setFixedWidth(285)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("TopBar")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(12, 14, 12, 8)
        title = QLabel("PLAYLIST")
        title.setObjectName("NowPlayingTitle")
        title.setStyleSheet(f"font-size: 14px; background: transparent;")
        header_layout.addWidget(title)
        sub = QLabel("Queue · source metadata")
        sub.setObjectName("NowPlayingMeta")
        header_layout.addWidget(sub)
        layout.addWidget(header)

        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(False)
        self.list_widget.setSelectionMode(QListWidget.SingleSelection)
        self.list_widget.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.list_widget, 1)

        controls = QFrame()
        controls.setObjectName("TopBar")
        cl = QHBoxLayout(controls)
        cl.setContentsMargins(10, 8, 10, 8)
        up_btn = QPushButton("↑")
        up_btn.setObjectName("IconButton")
        up_btn.setFixedWidth(32)
        up_btn.clicked.connect(lambda: self.moveRequested.emit(-1, self._selected_row()))
        cl.addWidget(up_btn)
        down_btn = QPushButton("↓")
        down_btn.setObjectName("IconButton")
        down_btn.setFixedWidth(32)
        down_btn.clicked.connect(lambda: self.moveRequested.emit(1, self._selected_row()))
        cl.addWidget(down_btn)
        cl.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("IconButton")
        clear_btn.clicked.connect(lambda: self.removeRequested.emit([]))
        cl.addWidget(clear_btn)
        layout.addWidget(controls)

        self.empty_label = QLabel("No media queued\nAdd files or drop a playlist here")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setObjectName("NowPlayingMeta")
        self.empty_label.setStyleSheet(f"color: {PALETTE.text_faint}; padding: 20px; background: transparent;")
        layout.addWidget(self.empty_label)

        footer = QFrame()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 4, 12, 12)
        self.shuffle_btn = QPushButton("Shuffle off")
        self.shuffle_btn.setObjectName("IconButton")
        self.shuffle_btn.setCheckable(True)
        footer_layout.addWidget(self.shuffle_btn)
        self.repeat_btn = QPushButton("Repeat off")
        self.repeat_btn.setObjectName("IconButton")
        footer_layout.addWidget(self.repeat_btn)
        footer_layout.addStretch()
        layout.addWidget(footer)

    def _selected_row(self) -> int:
        items = self.list_widget.selectedItems()
        return self.list_widget.row(items[0]) if items else -1

    def _on_double_click(self, item):
        row = self.list_widget.row(item)
        if row >= 0:
            self.playRequested.emit(row)

    def populate(self, names: list[str], selected: int = -1):
        self.list_widget.clear()
        for name in names:
            self.list_widget.addItem(name)
        if 0 <= selected < len(names):
            self.list_widget.setCurrentRow(selected)
        self.empty_label.setVisible(len(names) == 0)

    def clear(self):
        self.list_widget.clear()
        self.empty_label.setVisible(True)


class SeekSliderWithChapters(QWidget):
    """Custom seek bar with chapter markers."""

    seekRequested = Signal(float)
    seekStarted = Signal()
    seekFinished = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Timeline")
        self.setFixedHeight(28)
        self.setMouseTracking(True)
        self._position = 0.0
        self._duration = 0.0
        self._chapters: list = []
        self._active_chapter = -1
        self._dragging = False
        self._hover_x = -1

    def set_position(self, pos: float):
        self._position = max(0.0, pos)
        self.update()

    def set_duration(self, dur: float):
        self._duration = max(1.0, dur)
        self.update()

    def set_chapters(self, chapters, active=-1):
        self._chapters = list(chapters)
        self._active_chapter = int(active)
        self.update()

    def clear_chapters(self):
        self._chapters = []
        self._active_chapter = -1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            w, h = self.width(), self.height()
            groove_y = h // 2 - 2
            groove_h = 4

            painter.fillRect(0, groove_y, w, groove_h, QColor(PALETTE.border_strong))
            if self._duration > 0:
                fill_w = int((self._position / self._duration) * w)
                painter.fillRect(0, groove_y, fill_w, groove_h, QColor(PALETTE.accent))

            handle_x = int((self._position / self._duration) * w) if self._duration > 0 else 0
            handle_x = max(0, min(w - 1, handle_x))
            painter.setBrush(QColor(PALETTE.accent))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(handle_x - 6, groove_y - 4, 12, 12)

            for chapter in self._chapters:
                try:
                    cid = int(chapter.identifier)
                    start = float(chapter.start_seconds)
                except (AttributeError, ValueError, TypeError):
                    continue
                x = int((start / self._duration) * w) if self._duration > 0 else 0
                x = max(0, min(w - 1, x))
                color = QColor(PALETTE.accent) if cid == self._active_chapter else QColor(PALETTE.text_faint)
                painter.setPen(QPen(color, 2))
                painter.drawLine(x, groove_y - 4, x, groove_y + groove_h + 4)
        finally:
            painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._duration > 0:
            self._dragging = True
            pos = max(0.0, min(self._duration, (event.position().x() / self.width()) * self._duration))
            self.seekStarted.emit()
            self.seekRequested.emit(pos)

    def mouseMoveEvent(self, event):
        if self._dragging and self._duration > 0:
            pos = max(0.0, min(self._duration, (event.position().x() / self.width()) * self._duration))
            self.seekRequested.emit(pos)
        self._hover_x = int(event.position().x())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            if self._duration > 0:
                pos = max(0.0, min(self._duration, (event.position().x() / self.width()) * self._duration))
                self.seekFinished.emit(pos)

    def is_dragging(self) -> bool:
        return self._dragging


class DiagnosticsBar(QFrame):
    """Diagnostic info cards row."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        self._labels: dict[str, QLabel] = {}
        for title, default in [
            ("SEGMENTED PLAYBACK", "unavailable"),
            ("ENERGY SAVE", "unavailable"),
            ("INTEGRITY MODE", "unavailable"),
            ("CASU SUPPORT", "Legacy backend"),
        ]:
            card = QFrame()
            card.setObjectName("Panel")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 8, 12, 8)
            cl.setSpacing(3)
            t = QLabel(title)
            t.setObjectName("PanelTitle")
            cl.addWidget(t)
            v = QLabel(default)
            v.setObjectName("PanelValue")
            cl.addWidget(v)
            layout.addWidget(card)
            self._labels[title] = v

    def set_values(self, *, support=None, integrity=None, segmented=None, energy=None):
        mapping = {
            "SEGMENTED PLAYBACK": segmented,
            "ENERGY SAVE": energy,
            "INTEGRITY MODE": integrity,
            "CASU SUPPORT": support,
        }
        for key, value in mapping.items():
            if value is not None and key in self._labels:
                self._labels[key].setText(value)


class LibraryDialog(QDialog):
    """Searchable media library dialog."""

    def __init__(self, media_library, thumbnail_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MPCASU Library")
        self.setMinimumSize(760, 520)
        self.setObjectName("Dialog")
        self._media_library = media_library
        self._thumbnail_dir = thumbnail_dir
        self._paths: list[Path] = []
        self._preview_gen = 0
        self._preview_pixmap: QPixmap | None = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        top = QHBoxLayout()
        search_label = QLabel("Search")
        search_label.setObjectName("PanelTitle")
        top.addWidget(search_label)
        self._search_entry = QLineEdit()
        self._search_entry.setPlaceholderText("Type to search library...")
        self._search_entry.textChanged.connect(self._refresh)
        top.addWidget(self._search_entry)
        layout.addLayout(top)

        self._results = QListWidget()
        self._results.setMinimumHeight(200)
        self._results.itemDoubleClicked.connect(self._add_selected)
        self._results.currentItemChanged.connect(self._load_preview)
        layout.addWidget(self._results, 1)

        self._preview = QLabel("Select media for preview")
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setFixedHeight(160)
        self._preview.setObjectName("Panel")
        self._preview.setStyleSheet(f"background-color: {PALETTE.surface}; border-radius: 8px; padding: 12px;")
        layout.addWidget(self._preview)

        bottom = QHBoxLayout()
        refresh_btn = QPushButton("Refresh watched folders")
        refresh_btn.clicked.connect(self._on_refresh)
        bottom.addWidget(refresh_btn)
        bottom.addStretch()
        add_btn = QPushButton("Add selected")
        add_btn.setObjectName("NavItem")
        add_btn.setStyleSheet(f"background-color: {PALETTE.accent}; color: white;")
        add_btn.clicked.connect(self._add_selected)
        bottom.addWidget(add_btn)
        layout.addLayout(bottom)

    def _refresh(self):
        self._paths.clear()
        self._results.clear()
        query = self._search_entry.text()
        for item in self._media_library.search(query):
            self._paths.append(item.path)
            marker = "★ " if item.favorite else ""
            resume = f" · resume {item.resume_seconds:.1f}s" if item.resume_seconds else ""
            self._results.addItem(f"{marker}{item.path.name}{resume}  —  {item.path.parent}")

    def _add_selected(self):
        item = self._results.currentItem()
        if item is None:
            return
        row = self._results.row(item)
        if 0 <= row < len(self._paths):
            self.accept()

    def selected_paths(self) -> list[Path]:
        item = self._results.currentItem()
        if item is None:
            return []
        row = self._results.row(item)
        if 0 <= row < len(self._paths):
            return [self._paths[row]]
        return []

    def _load_preview(self, current, previous):
        if current is None:
            return
        row = self._results.row(current)
        if row < 0 or row >= len(self._paths):
            return
        source = self._paths[row]
        self._preview_gen += 1
        gen = self._preview_gen
        self._preview.setText("Decoding thumbnail…")

        def worker():
            thumb = thumbnail_for(source, self._thumbnail_dir)
            def present():
                if gen != self._preview_gen or not self.isVisible():
                    return
                if thumb is None:
                    self._preview.setText("No video thumbnail available")
                    return
                pix = QPixmap(str(thumb))
                if pix.isNull():
                    self._preview.setText("Thumbnail could not be displayed")
                    return
                scaled = pix.scaled(320, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self._preview_pixmap = scaled
                self._preview.setPixmap(scaled)
            QTimer.singleShot(0, present)
        threading.Thread(target=worker, daemon=True).start()

    def _on_refresh(self):
        if isinstance(self.parent(), MainWindow):
            self.parent().refresh_watched_folders()
        self._refresh()


class SettingsDialog(QDialog):
    """Settings dialog for audio device, rate, and folders."""

    def __init__(self, settings_store, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MPCASU Settings")
        self.setMinimumSize(500, 380)
        self._settings_store = settings_store
        self._settings = settings_store.load()
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Settings")
        title.setObjectName("NowPlayingTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(8)

        row = 0
        grid.addWidget(QLabel("Volume:"), row, 0)
        self._volume_spin = QSpinBox()
        self._volume_spin.setRange(0, 200)
        self._volume_spin.setValue(self._settings.volume)
        grid.addWidget(self._volume_spin, row, 1)

        row += 1
        self._muted_cb = QCheckBox("Muted")
        self._muted_cb.setChecked(self._settings.muted)
        grid.addWidget(self._muted_cb, row, 0, 1, 2)

        row += 1
        grid.addWidget(QLabel("Playback rate:"), row, 0)
        self._rate_spin = QDoubleSpinBox()
        self._rate_spin.setRange(0.25, 4.0)
        self._rate_spin.setSingleStep(0.25)
        self._rate_spin.setValue(self._settings.rate)
        grid.addWidget(self._rate_spin, row, 1)

        row += 1
        grid.addWidget(QLabel("Watched folders:"), row, 0)
        self._folders_text = QLabel("\n".join(self._settings.watched_folders) if self._settings.watched_folders else "None")
        self._folders_text.setObjectName("NowPlayingMeta")
        self._folders_text.setWordWrap(True)
        grid.addWidget(self._folders_text, row, 1)

        layout.addLayout(grid)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save_and_accept(self):
        self._settings = PlayerSettings(
            volume=self._volume_spin.value(),
            muted=self._muted_cb.isChecked(),
            rate=self._rate_spin.value(),
            audio_device=self._settings.audio_device,
            watched_folders=tuple(self._settings.watched_folders),
        )
        self._settings_store.save(self._settings)
        self.accept()

    def settings(self) -> PlayerSettings:
        return self._settings


class AboutDialog(QDialog):
    """About MPCASU."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About MPCASU")
        self.setFixedSize(420, 280)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("MPCASU")
        title.setObjectName("BrandName")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("PLAYER")
        sub.setObjectName("BrandSub")
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)

        layout.addSpacing(12)

        info = QLabel("Version 1.0.0rc9\nMedia Player for CASU & Legacy Media\nIn-process playback · No external player")
        info.setObjectName("NowPlayingMeta")
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)

        layout.addSpacing(12)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 0, Qt.AlignCenter)


class MainWindow(QMainWindow):
    """MPCASU Qt main window — full media player."""

    def __init__(self, initial: list[Path] | None = None):
        super().__init__()
        self.setWindowTitle("MPCASU Media Player")
        self.setMinimumSize(980, 620)
        self.resize(1360, 820)
        self.setStyleSheet(stylesheet())

        self.backend: LibVLCBackend | NativeCasuBackend | None = None
        self.controller = PlaybackController()
        self.current: Path | None = None
        self.duration = 0.0
        self._paused = False
        self._dragging = False
        self._advancing = False
        self._end_handled = False
        self._started_at = 0.0
        self._start_offset = 0.0
        self._visual_phase = 0.0
        self._visual_state = "idle"
        self._visual_segments: list[dict] = []
        self._visual_video_segments: list[dict] = []
        self._visual_audio_segments: list[dict] = []
        self._scheduler = None
        self._volume = 100
        self._muted = False
        self._rate = 1.0
        self._audio_delay_ms = 0.0
        self._subtitle_delay_ms = 0.0
        self._resume_source: str | None = None
        self._resume_position = 0.0
        self._fullscreen = False
        self._layout_mode = "wide"

        config_dir = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "mpcasu"
        config_dir.mkdir(parents=True, exist_ok=True)
        self._session_file = config_dir / "session.json"

        self.settings_store = SettingsStore(config_dir / "settings.json")
        effective = self.settings_store.load()
        self._volume = effective.volume
        self._muted = effective.muted
        self._rate = effective.rate
        self._audio_device = effective.audio_device
        self._watched_folders = list(effective.watched_folders)
        self.media_library = MediaLibrary(config_dir / "library.sqlite3")
        self._thumbnail_dir = config_dir / "thumbnails"
        self._thumbnail_dir.mkdir(parents=True, exist_ok=True)
        self.playlist_model = PlaylistModel()

        self._build_ui()
        self._restore_session()
        self._setup_shortcuts()

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(500)

        if initial:
            self.add_files(initial)
            QTimer.singleShot(300, self.play_selected)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._now_playing_bar = NowPlayingBar()
        main_layout.addWidget(self._now_playing_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._sidebar = Sidebar()
        self._sidebar.navRequested.connect(self._navigate)
        body.addWidget(self._sidebar)

        center_column = QVBoxLayout()
        center_column.setContentsMargins(0, 0, 0, 0)
        center_column.setSpacing(0)

        self._video_surface = VideoSurface()
        self._video_surface.doubleClicked.connect(self.toggle_fullscreen)
        center_column.addWidget(self._video_surface, 1)

        transport_container = QFrame()
        transport_container.setObjectName("Panel")
        tc_layout = QVBoxLayout(transport_container)
        tc_layout.setContentsMargins(14, 6, 14, 6)
        tc_layout.setSpacing(4)

        self._seek_slider = SeekSliderWithChapters()
        self._seek_slider.seekRequested.connect(self._on_seek_preview)
        self._seek_slider.seekStarted.connect(self._on_seek_start)
        self._seek_slider.seekFinished.connect(self._on_seek_finish)
        tc_layout.addWidget(self._seek_slider)

        time_row = QHBoxLayout()
        time_row.setContentsMargins(0, 0, 0, 4)
        self._time_current = QLabel("00:00")
        self._time_current.setObjectName("TimeLabel")
        time_row.addWidget(self._time_current)
        time_row.addStretch()
        self._time_total = QLabel("00:00")
        self._time_total.setObjectName("TimeLabel")
        time_row.addWidget(self._time_total)
        tc_layout.addLayout(time_row)

        controls = QHBoxLayout()
        controls.setSpacing(3)

        self._prev_btn = QPushButton("⏮")
        self._prev_btn.setObjectName("TransportButton")
        self._prev_btn.clicked.connect(self.play_previous)
        self._prev_btn.setToolTip("Previous track")
        controls.addWidget(self._prev_btn)

        self._seek_back_btn = QPushButton("⏪")
        self._seek_back_btn.setObjectName("TransportButton")
        self._seek_back_btn.clicked.connect(lambda: self.seek_by(-10))
        self._seek_back_btn.setToolTip("Rewind 10s")
        controls.addWidget(self._seek_back_btn)

        self._play_btn = QPushButton("▶")
        self._play_btn.setObjectName("PlayButton")
        self._play_btn.setFixedSize(44, 44)
        self._play_btn.clicked.connect(self.toggle_playback)
        self._play_btn.setToolTip("Play / Pause")
        controls.addWidget(self._play_btn)

        self._stop_btn = QPushButton("⏹")
        self._stop_btn.setObjectName("TransportButton")
        self._stop_btn.clicked.connect(self.stop)
        self._stop_btn.setToolTip("Stop")
        controls.addWidget(self._stop_btn)

        self._seek_fwd_btn = QPushButton("⏩")
        self._seek_fwd_btn.setObjectName("TransportButton")
        self._seek_fwd_btn.clicked.connect(lambda: self.seek_by(10))
        self._seek_fwd_btn.setToolTip("Forward 10s")
        controls.addWidget(self._seek_fwd_btn)

        self._next_btn = QPushButton("⏭")
        self._next_btn.setObjectName("TransportButton")
        self._next_btn.clicked.connect(self.play_next)
        self._next_btn.setToolTip("Next track")
        controls.addWidget(self._next_btn)

        controls.addStretch()

        volume_layout = QHBoxLayout()
        volume_layout.setSpacing(4)
        self._mute_btn = QPushButton("🔊")
        self._mute_btn.setObjectName("IconButton")
        self._mute_btn.setFixedSize(32, 32)
        self._mute_btn.clicked.connect(self.toggle_mute)
        self._mute_btn.setToolTip("Mute / Unmute")
        volume_layout.addWidget(self._mute_btn)

        self._volume_slider = QSlider(Qt.Horizontal)
        self._volume_slider.setObjectName("VolumeSlider")
        self._volume_slider.setRange(0, 200)
        self._volume_slider.setValue(self._volume)
        self._volume_slider.setFixedWidth(100)
        self._volume_slider.valueChanged.connect(self._on_volume_slider)
        self._volume_slider.setToolTip("Volume")
        volume_layout.addWidget(self._volume_slider)
        controls.addLayout(volume_layout)

        self._rate_btn = QPushButton(f"{self._rate:g}×")
        self._rate_btn.setObjectName("IconButton")
        self._rate_btn.clicked.connect(self.cycle_rate)
        self._rate_btn.setToolTip("Playback speed")
        controls.addWidget(self._rate_btn)

        track_section = QHBoxLayout()
        track_section.setSpacing(3)

        self._audio_track_menu = QPushButton("Audio")
        self._audio_track_menu.setObjectName("IconButton")
        self._audio_track_menu.setMenu(QMenu(self))
        self._audio_track_menu.menu().aboutToShow.connect(lambda: self._refresh_track_menu(TrackKind.AUDIO))
        self._audio_track_menu.setToolTip("Audio track")
        controls.addWidget(self._audio_track_menu)

        self._video_track_menu = QPushButton("Video")
        self._video_track_menu.setObjectName("IconButton")
        self._video_track_menu.setMenu(QMenu(self))
        self._video_track_menu.menu().aboutToShow.connect(lambda: self._refresh_track_menu(TrackKind.VIDEO))
        self._video_track_menu.setToolTip("Video track")
        controls.addWidget(self._video_track_menu)

        self._subtitle_track_menu = QPushButton("Subtitles")
        self._subtitle_track_menu.setObjectName("IconButton")
        self._subtitle_track_menu.setMenu(QMenu(self))
        self._subtitle_track_menu.menu().aboutToShow.connect(lambda: self._refresh_track_menu(TrackKind.SUBTITLE))
        self._subtitle_track_menu.setToolTip("Subtitle track")
        controls.addWidget(self._subtitle_track_menu)

        self._audio_device_menu = QPushButton("Output")
        self._audio_device_menu.setObjectName("IconButton")
        self._audio_device_menu.setMenu(QMenu(self))
        self._audio_device_menu.menu().aboutToShow.connect(self._refresh_audio_devices)
        self._audio_device_menu.setToolTip("Audio output device")
        controls.addWidget(self._audio_device_menu)

        self._chapter_menu = QPushButton("Chapters")
        self._chapter_menu.setObjectName("IconButton")
        self._chapter_menu.setMenu(QMenu(self))
        self._chapter_menu.menu().aboutToShow.connect(self._refresh_chapters)
        self._chapter_menu.setToolTip("Chapters")
        controls.addWidget(self._chapter_menu)

        sync_menu_btn = QPushButton("Sync")
        sync_menu_btn.setObjectName("IconButton")
        sync_menu = QMenu(self)
        sync_menu.addAction("Audio delay…", self.set_audio_delay_dialog)
        sync_menu.addAction("Subtitle delay…", self.set_subtitle_delay_dialog)
        sync_menu_btn.setMenu(sync_menu)
        sync_menu_btn.setToolTip("Audio / subtitle sync")
        controls.addWidget(sync_menu_btn)

        load_sub_btn = QPushButton("Load subtitle")
        load_sub_btn.setObjectName("IconButton")
        load_sub_btn.clicked.connect(self.load_external_subtitle)
        controls.addWidget(load_sub_btn)

        frame_btn = QPushButton("Frame")
        frame_btn.setObjectName("IconButton")
        frame_btn.clicked.connect(self.next_frame)
        controls.addWidget(frame_btn)

        info_btn = QPushButton("Info")
        info_btn.setObjectName("IconButton")
        info_btn.clicked.connect(self.show_media_info)
        controls.addWidget(info_btn)

        fullscreen_btn = QPushButton("⛶")
        fullscreen_btn.setObjectName("IconButton")
        fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        controls.addWidget(fullscreen_btn)

        tc_layout.addLayout(controls)

        self._status_label = QLabel("Ready — CASU and legacy media")
        self._status_label.setObjectName("StatusText")
        self._status_label.setFixedHeight(24)
        self._status_label.setContentsMargins(14, 2, 14, 2)
        tc_layout.addWidget(self._status_label)

        center_column.addWidget(transport_container)

        self._diagnostics_bar = DiagnosticsBar()
        center_column.addWidget(self._diagnostics_bar)

        body.addLayout(center_column, 1)

        self._playlist_pane = PlaylistPane()
        self._playlist_pane.playRequested.connect(self._play_playlist_row)
        self._playlist_pane.removeRequested.connect(self._on_playlist_remove)
        self._playlist_pane.moveRequested.connect(self._on_playlist_move)
        self._shuffle = False
        self._repeat_mode = "off"
        self._random = random.SystemRandom()
        self._playlist_pane.shuffle_btn.toggled.connect(self._toggle_shuffle)
        self._playlist_pane.repeat_btn.clicked.connect(self._cycle_repeat)
        body.addWidget(self._playlist_pane)

        main_layout.addLayout(body)

        status_bar = QStatusBar()
        status_bar.setObjectName("StatusBar")
        self._status_left = QLabel("MPCASU 1.0.0rc9  ● Pre-release")
        self._status_left.setObjectName("StatusText")
        self._status_left.setStyleSheet(f"color: {PALETTE.text_muted};")
        status_bar.addWidget(self._status_left)
        self._status_center = QLabel("Optimized for performance and integrity")
        self._status_center.setObjectName("StatusText")
        self._status_center.setStyleSheet(f"color: {PALETTE.text_faint};")
        status_bar.addWidget(self._status_center)
        self._status_right = QLabel("CPU/RAM telemetry unavailable")
        self._status_right.setObjectName("StatusText")
        self._status_right.setStyleSheet(f"color: {PALETTE.text_faint};")
        status_bar.addPermanentWidget(self._status_right)
        self.setStatusBar(status_bar)

    def _setup_shortcuts(self):
        space = QAction("Play/Pause", self)
        space.setShortcut(QKeySequence(Qt.Key_Space))
        space.triggered.connect(self.toggle_playback)
        self.addAction(space)

        ctrl_o = QAction("Open file", self)
        ctrl_o.setShortcut(QKeySequence("Ctrl+O"))
        ctrl_o.triggered.connect(self.add_dialog)
        self.addAction(ctrl_o)

        ctrl_l = QAction("Open URL", self)
        ctrl_l.setShortcut(QKeySequence("Ctrl+L"))
        ctrl_l.triggered.connect(self.open_url_dialog)
        self.addAction(ctrl_l)

        ctrl_i = QAction("Media info", self)
        ctrl_i.setShortcut(QKeySequence("Ctrl+I"))
        ctrl_i.triggered.connect(self.show_media_info)
        self.addAction(ctrl_i)

        left = QAction("Seek back", self)
        left.setShortcut(QKeySequence(Qt.Key_Left))
        left.triggered.connect(lambda: self.seek_by(-10))
        self.addAction(left)

        right = QAction("Seek forward", self)
        right.setShortcut(QKeySequence(Qt.Key_Right))
        right.triggered.connect(lambda: self.seek_by(10))
        self.addAction(right)

        up = QAction("Volume up", self)
        up.setShortcut(QKeySequence(Qt.Key_Up))
        up.triggered.connect(lambda: self.change_volume(5))
        self.addAction(up)

        down = QAction("Volume down", self)
        down.setShortcut(QKeySequence(Qt.Key_Down))
        down.triggered.connect(lambda: self.change_volume(-5))
        self.addAction(down)

        f_action = QAction("Fullscreen", self)
        f_action.setShortcut(QKeySequence(Qt.Key_F))
        f_action.triggered.connect(self.toggle_fullscreen)
        self.addAction(f_action)

        m_action = QAction("Mute", self)
        m_action.setShortcut(QKeySequence(Qt.Key_M))
        m_action.triggered.connect(self.toggle_mute)
        self.addAction(m_action)

        s_action = QAction("Stop", self)
        s_action.setShortcut(QKeySequence(Qt.Key_S))
        s_action.triggered.connect(self.stop)
        self.addAction(s_action)

        esc = QAction("Exit fullscreen", self)
        esc.setShortcut(QKeySequence(Qt.Key_Escape))
        esc.triggered.connect(self._exit_fullscreen)
        self.addAction(esc)

    def _navigate(self, name: str):
        if name == "LIBRARY":
            self.show_library_dialog()
        elif name == "PLAYLIST":
            self._playlist_pane.setVisible(not self._playlist_pane.isVisible())
        elif name == "CASU FILES":
            self._add_dialog_filter("CASU media", "*.casu")
        elif name == "SETTINGS":
            dlg = SettingsDialog(self.settings_store, self)
            if dlg.exec() == QDialog.Accepted:
                s = dlg.settings()
                self._volume = s.volume
                self._muted = s.muted
                self._rate = s.rate
                self._watched_folders = list(s.watched_folders)
                self._volume_slider.setValue(self._volume)
                self._rate_btn.setText(f"{self._rate:g}×")
                self.status(f"Settings updated")
        elif name == "ABOUT":
            dlg = AboutDialog(self)
            dlg.exec()

    def status(self, text: str):
        self._status_label.setText(str(text))

    # --- Playback control ---

    def toggle_playback(self):
        if not self.backend:
            self.play_selected()
        else:
            self.pause()

    def pause(self):
        if self.backend and self.backend.state() not in {PlaybackState.EMPTY, PlaybackState.STOPPED, PlaybackState.ENDED}:
            if self._paused:
                self.controller.pause_or_resume()
                self._paused = False
                self.status("Playing — source timing is preserved")
                self._play_btn.setText("▶")
            else:
                self._sync_position()
                self.controller.pause_or_resume()
                self._paused = True
                self.status("Paused — source timing is preserved")
                self._play_btn.setText("⏸")

    def stop(self):
        if self.backend:
            self._persist_media_preferences()
            self.controller.stop()
            self.controller.close()
        self.backend = None
        self._seek_slider.clear_chapters()
        self._paused = False
        self._play_btn.setText("▶")
        self._diagnostics_bar.set_values(
            support="Legacy backend", integrity="unavailable",
            segmented="unavailable", energy="unavailable — not measured",
        )
        self.status("Stopped")
        self._video_surface.set_video_active(False)
        self._video_surface.clear()

    def seek_by(self, seconds: float):
        pos = max(0.0, min(self.duration, self._seek_slider._position + seconds))
        self._seek_slider.set_position(pos)
        self._do_seek(pos)

    def _on_seek_preview(self, pos: float):
        if not self._dragging:
            self._seek_slider.set_position(pos)
            self._update_time_labels(pos)

    def _on_seek_start(self):
        self._dragging = True

    def _on_seek_finish(self, pos: float):
        self._dragging = False
        self._do_seek(pos)

    def _do_seek(self, pos: float):
        if not self.current:
            return
        try:
            if self.backend:
                self.controller.seek(pos)
                self.controller.play()
                self._paused = False
                self._play_btn.setText("▶")
        except (BackendError, CasuError, OSError) as exc:
            self.status(f"Cannot seek — {exc}")

    def change_volume(self, delta: int):
        self._volume = max(0, min(200, self._volume + delta))
        self._volume_slider.setValue(self._volume)
        if self.backend:
            try:
                self._volume = self.backend.set_volume(self._volume)
            except BackendError as exc:
                self.status(str(exc))
                return
        self.status(f"Volume {self._volume}%")

    def _on_volume_slider(self, value: int):
        self._volume = value
        if self.backend:
            try:
                self._volume = self.backend.set_volume(value)
            except BackendError:
                pass
        self.status(f"Volume {self._volume}%")

    def toggle_mute(self):
        self._muted = not self._muted
        if self.backend:
            try:
                self.backend.set_mute(self._muted)
            except BackendError as exc:
                self.status(str(exc))
                return
        self.status("Muted" if self._muted else f"Volume {self._volume}%")
        self._mute_btn.setText("🔇" if self._muted else "🔊")

    def cycle_rate(self):
        rates = (0.5, 1.0, 1.25, 1.5, 2.0)
        next_rate = rates[(rates.index(self._rate) + 1) % len(rates)] if self._rate in rates else 1.0
        if not self.backend:
            self._rate = next_rate
            self.status(f"Playback rate {self._rate:g}× (applies on next media)")
            return
        try:
            self._rate = self.backend.set_rate(next_rate)
            self._rate_btn.setText(f"{self._rate:g}×")
            self.status(f"Playback rate {self._rate:g}×")
        except BackendError as exc:
            self.status(f"Playback rate unavailable: {exc}")

    def play_selected(self):
        path = self.selected_path()
        if not path:
            self.status("Add a media file first.")
            return
        self.stop()
        self._end_handled = False
        self.current = path
        self._now_playing_bar.set_now_playing(path.name)
        selected_index = self.playlist_model.index_of(path)
        if selected_index is not None:
            self._playlist_pane.populate([p.name for p in self.playlist_model.items], selected_index)

        sidecar = path if path.suffix.lower() == ".casu" else path.with_suffix(path.suffix + ".casu")
        self._load_visual_state(sidecar if sidecar.exists() else path)

        if path.suffix.lower() == ".casu":
            magic = b""
            try:
                magic = path.read_bytes()[:8]
                native = magic in {b"CASUNAT1", b"CASUNAT2"}
            except OSError:
                native = False
            self._diagnostics_bar.set_values(
                support=("CASUNAT2 native key-state/tile/PCM" if magic == b"CASUNAT2" else
                         "CASUNAT1 compatibility + libVLC" if native else
                         "CASU sidecar + libVLC"),
                integrity="verified source manifest" if not self._visual_state.startswith("invalid") else "failed manifest validation",
                segmented=f"{len(self._visual_segments)} segments" if self._visual_segments else "no segment data",
            )
        elif sidecar.exists():
            self._diagnostics_bar.set_values(
                support="Legacy + CASU sidecar",
                integrity="sidecar available; source checked on load",
                segmented=f"{len(self._visual_segments)} segments" if self._visual_segments else "no segment data",
            )
        else:
            self._diagnostics_bar.set_values(
                support="Legacy backend", integrity="unavailable", segmented="unavailable",
            )
        self._diagnostics_bar.set_values(energy="unavailable — not measured")

        try:
            source = self._source_for(path)
        except CasuError as exc:
            QMessageBox.critical(self, "MPCASU", str(exc))
            self.status("Cannot play — safe fallback refused an invalid CASU manifest")
            return

        state = ("CASU manifest selected" if path.suffix.lower() == ".casu"
                 else ("CASU sidecar found" if sidecar.exists() else "legacy fallback — no CASU sidecar"))
        self.status(f"{path.name} · {state}")

        try:
            if path.suffix.lower() == ".casu" and NativeCasuBackend.supports(path):
                try:
                    audio_sink = PulseAudioSink()
                except BackendError:
                    audio_sink = None
                self.backend = NativeCasuBackend(self._video_surface.handle, audio_sink)
            else:
                self.backend = (CasuBackend(self._video_surface.handle)
                                if path.suffix.lower() == ".casu"
                                else LibVLCBackend(self._video_surface.handle))
            self.backend.on_event = self._backend_event
            if path.suffix.lower() == ".casu":
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
            self._seek_slider.set_duration(self.duration)
            self._draw_chapter_markers()
            if (self._resume_source and str(path) == self._resume_source
                    and 5.0 < self._resume_position < max(5.0, self.duration - 5.0)):
                self.controller.seek(self._resume_position)
                self._seek_slider.set_position(self._resume_position)
                self.status(f"Resumed {path.name} at {self._resume_position:.1f} s")
            else:
                self._resume_position = 0.0
            capabilities = self.backend.capabilities()
            self.status(f"{path.name} · {state} · {capabilities.get('version', 'libVLC')}")
            self._video_surface.set_video_active(True)
            if isinstance(self.backend, LibVLCBackend):
                QTimer.singleShot(500, self._apply_media_preferences)
                QTimer.singleShot(1500, self._check_playback_start)
        except (BackendError, CasuError, OSError) as exc:
            self.controller.close()
            self.backend = None
            self.status("Cannot play — internal media backend unavailable")
            QMessageBox.critical(self, "MPCASU", f"Could not start internal playback: {exc}")
            return
        self._paused = False
        self._play_btn.setText("⏸")

    def _toggle_shuffle(self, checked: bool) -> None:
        self._shuffle = checked
        self._playlist_pane.shuffle_btn.setText("Shuffle on" if checked else "Shuffle off")
        self.status(f"Shuffle {'on' if checked else 'off'}")

    def _cycle_repeat(self) -> None:
        values = ("off", "all", "one")
        self._repeat_mode = values[(values.index(self._repeat_mode) + 1) % len(values)]
        self._playlist_pane.repeat_btn.setText(f"Repeat {self._repeat_mode}")
        self.status(f"Repeat mode: {self._repeat_mode}")

    def play_next(self, automatic: bool = False):
        count = len(self.playlist_model)
        if automatic and self._repeat_mode == "one" and self.current and self.backend:
            self.controller.seek(0.0)
            return
        if not count:
            self.status("Playlist is empty")
            return
        selected_index = self._selected_playlist_row()
        current_index = self.playlist_model.index_of(self.current) if self.current else None
        index = selected_index if selected_index >= 0 else (-1 if current_index is None else current_index)
        if self._shuffle and count > 1:
            choices = [value for value in range(count) if value != index]
            target = self._random.choice(choices)
        else:
            target = index + 1
        if target >= count and self._repeat_mode == "all":
            target = 0
        if target >= count:
            self.status("End of playlist")
            return
        self._playlist_pane.list_widget.setCurrentRow(target)
        self.play_selected()

    def play_previous(self):
        count = len(self.playlist_model)
        if not count:
            self.status("Playlist is empty")
            return
        selected_index = self._selected_playlist_row()
        current_index = self.playlist_model.index_of(self.current) if self.current else None
        index = selected_index if selected_index >= 0 else (0 if current_index is None else current_index)
        target = index - 1
        if target < 0 and self._repeat_mode == "all":
            target = count - 1
        if target < 0:
            self.status("Beginning of playlist")
            return
        self._playlist_pane.list_widget.setCurrentRow(target)
        self.play_selected()

    def _selected_playlist_row(self) -> int:
        items = self._playlist_pane.list_widget.selectedItems()
        return self._playlist_pane.list_widget.row(items[0]) if items else -1

    def selected_path(self) -> Path | None:
        selected = self._selected_playlist_row()
        if selected < 0:
            if self.current:
                return self.current
            if len(self.playlist_model):
                return self.playlist_model.item(0)
            return None
        try:
            return self.playlist_model.item(selected)
        except PlaylistError:
            return None

    # --- Track menus ---

    def _refresh_track_menu(self, kind: TrackKind):
        menu_map = {
            TrackKind.AUDIO: self._audio_track_menu.menu(),
            TrackKind.VIDEO: self._video_track_menu.menu(),
            TrackKind.SUBTITLE: self._subtitle_track_menu.menu(),
        }
        menu = menu_map[kind]
        menu.clear()
        if not self.backend:
            menu.addAction("No active media").setEnabled(False)
            return
        descriptors = self.backend.track_descriptors(kind)
        getters = {
            TrackKind.AUDIO: self.backend.audio_track,
            TrackKind.VIDEO: self.backend.video_track,
            TrackKind.SUBTITLE: self.backend.subtitle_track,
        }
        current = getters[kind]()
        if kind is TrackKind.SUBTITLE:
            act = menu.addAction("Off")
            act.setCheckable(True)
            act.setChecked(current == -1)
            act.triggered.connect(lambda checked=False, k=kind, v=-1: self._select_track(k, v))
        if not descriptors:
            menu.addAction("No tracks reported").setEnabled(False)
        for item in descriptors:
            details = [item.label]
            if item.language and item.language not in item.label:
                details.append(item.language)
            if item.codec and item.codec not in item.label:
                details.append(item.codec)
            label = " · ".join(details)
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(current == item.identifier)
            act.triggered.connect(lambda checked=False, k=kind, v=item.identifier: self._select_track(k, v))

    def _select_track(self, kind: TrackKind, identifier: int):
        if not self.backend:
            return
        setters = {
            TrackKind.AUDIO: self.backend.set_audio_track,
            TrackKind.VIDEO: self.backend.set_video_track,
            TrackKind.SUBTITLE: self.backend.set_subtitle_track,
        }
        try:
            setters[kind](identifier)
            self._persist_media_preferences()
            self.status(f"{kind.value.title()} track selected: {identifier}")
        except BackendError as exc:
            self.status(str(exc))

    # --- Audio devices ---

    def _refresh_audio_devices(self):
        menu = self._audio_device_menu.menu()
        menu.clear()
        if not self.backend:
            menu.addAction("No active media").setEnabled(False)
            return
        devices = self.backend.audio_devices()
        if not devices:
            menu.addAction("Runtime reported no devices").setEnabled(False)
            return
        for device in devices:
            act = menu.addAction(device.label)
            act.triggered.connect(lambda checked=False, did=device.identifier: self._select_audio_device(did))

    def _select_audio_device(self, identifier: str):
        if not self.backend:
            return
        try:
            self.backend.set_audio_device(identifier)
            self._audio_device = identifier
            self.status(f"Audio output selected: {identifier}")
        except BackendError as exc:
            self.status(str(exc))

    # --- Chapters ---

    def _refresh_chapters(self):
        menu = self._chapter_menu.menu()
        menu.clear()
        if not self.backend:
            menu.addAction("No active media").setEnabled(False)
            return
        chapters = self.backend.chapter_descriptors()
        if not chapters:
            menu.addAction("No chapters reported").setEnabled(False)
            return
        for chapter in chapters:
            minutes, seconds = divmod(max(0, int(chapter.start_seconds)), 60)
            act = menu.addAction(f"{minutes:02d}:{seconds:02d} · {chapter.title}")
            act.triggered.connect(lambda checked=False, cid=chapter.identifier: self._select_chapter(cid))

    def _select_chapter(self, identifier: int):
        if not self.backend:
            return
        try:
            self.backend.set_chapter(identifier)
            self.status(f"Chapter selected: {identifier + 1}")
            self._seek_slider.set_position(self.backend.position())
            self._draw_chapter_markers()
        except BackendError as exc:
            self.status(str(exc))

    def _draw_chapter_markers(self, chapters=None):
        if chapters is None:
            if not self.backend:
                self._seek_slider.clear_chapters()
                return
            try:
                chapters = self.backend.chapter_descriptors()
            except BackendError:
                self._seek_slider.clear_chapters()
                return
        try:
            active = self.backend.chapter() if self.backend else -1
        except BackendError:
            active = -1
        self._seek_slider.set_chapters(chapters, active)

    # --- Subtitle ---

    def load_external_subtitle(self):
        if not self.backend or not self.current:
            self.status("Open local media before loading an external subtitle")
            return
        from PySide6.QtWidgets import QFileDialog
        subtitle, _ = QFileDialog.getOpenFileName(
            self, "Load subtitle",
            filter="Subtitle files (*.srt *.ass *.ssa *.vtt *.sub);;All files (*.*)"
        )
        if not subtitle:
            return
        try:
            position = self.backend.position()
            paused = self._paused
            self.backend.add_external_subtitle(Path(subtitle))
            self.duration = self.backend.duration()
            self._seek_slider.set_duration(self.duration)
            self._draw_chapter_markers()
            self.backend.seek(position)
            if not paused:
                self.backend.play()
            self.status(f"External subtitle loaded · {Path(subtitle).name}")
        except (BackendError, OSError) as exc:
            self.status(f"Could not load subtitle: {exc}")

    # --- Frame step ---

    def next_frame(self):
        if not self.backend:
            self.status("No active media backend")
            return
        try:
            self.backend.next_frame()
            self._paused = True
            self._play_btn.setText("▶")
            self.status("Advanced one decoded frame")
        except BackendError as exc:
            self.status(str(exc))

    # --- Fullscreen ---

    def toggle_fullscreen(self):
        if self._fullscreen:
            self._exit_fullscreen()
        else:
            self._fullscreen = True
            self.showFullScreen()

    def _exit_fullscreen(self):
        self._fullscreen = False
        self.showNormal()

    # --- Playlist management ---

    def add_files(self, paths: list[Path | str]):
        added: list[Path] = []
        for path in paths:
            path = Path(path)
            if path.is_file():
                try:
                    if self.playlist_model.add((path,), existing_only=True):
                        added.append(path.expanduser().resolve())
                except PlaylistError as exc:
                    self.status(str(exc))
                    break
        for path in added:
            try:
                self.media_library.upsert(path)
            except OSError:
                pass
        self._render_playlist()

    def add_dialog(self):
        from PySide6.QtWidgets import QFileDialog
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add media",
            filter="Media and streams (*);;Known media ({});;All files (*.*)".format(
                " ".join(f"*{x}" for x in sorted(MEDIA_EXTENSIONS)))
        )
        self.add_files([Path(p) for p in paths])

    def _add_dialog_filter(self, label: str, pattern: str):
        from PySide6.QtWidgets import QFileDialog
        paths, _ = QFileDialog.getOpenFileNames(
            self, f"Add {label}",
            filter=f"{label} ({pattern});;All files (*.*)"
        )
        self.add_files([Path(p) for p in paths])

    def open_url_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Open network URL")
        dialog.setMinimumWidth(520)
        dialog.setStyleSheet(stylesheet())
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        label = QLabel("HTTP(S), HLS, RTSP, RTP, UDP, FTP or SMB URL")
        label.setObjectName("NowPlayingMeta")
        layout.addWidget(label)
        entry = QLineEdit()
        entry.setPlaceholderText("https://...")
        layout.addWidget(entry)

        def open_source():
            url = entry.text().strip()
            if url:
                self._open_external_source(url)
                dialog.accept()

        btn = QPushButton("Open")
        btn.clicked.connect(open_source)
        layout.addWidget(btn, 0, Qt.AlignRight)
        entry.returnPressed.connect(open_source)
        entry.setFocus()
        dialog.exec()

    def _open_external_source(self, source: str):
        self.stop()
        self._end_handled = False
        self.current = None
        display_source = display_media_source(source)
        self._now_playing_bar.set_now_playing(display_source)
        try:
            self.backend = LibVLCBackend(self._video_surface.handle)
            self.backend.on_event = self._backend_event
            self.backend.open_source(source)
            self.controller.attach(self.backend, display_source)
            self.controller.play()
            self._apply_playback_rate()
            self._apply_backend_settings()
            self._diagnostics_bar.set_values(
                support="Legacy network backend", integrity="unavailable",
                segmented="unavailable", energy="unavailable — not measured",
            )
            self.duration = self.backend.duration()
            self._seek_slider.set_duration(self.duration)
            self._draw_chapter_markers()
            capabilities = self.backend.capabilities()
            self.status(f"Playing network source · {capabilities.get('version', 'libVLC')} · timing owned by libVLC")
            self._video_surface.set_video_active(True)
        except (BackendError, OSError) as exc:
            self.controller.close()
            self.backend = None
            self.status(f"Could not open network source: {exc}")
            QMessageBox.critical(self, "MPCASU", str(exc))

    def _render_playlist(self, selected: int = -1):
        names = [p.name for p in self.playlist_model.items]
        self._playlist_pane.populate(names, selected)

    def _play_playlist_row(self, row: int):
        self._playlist_pane.list_widget.setCurrentRow(row)
        self.play_selected()

    def _on_playlist_remove(self, indices):
        if not indices:
            if self.backend:
                self.stop()
            self.playlist_model.clear()
            self._render_playlist()
            self.current = None
            self._now_playing_bar.set_now_playing("")
            self.status("Playlist cleared")
            return
        try:
            self.playlist_model.remove(indices)
        except PlaylistError as exc:
            self.status(str(exc))
            return
        self._render_playlist()

    def _on_playlist_move(self, delta: int, index: int):
        if index < 0:
            return
        try:
            target = self.playlist_model.move(index, delta)
        except PlaylistError as exc:
            self.status(str(exc))
            return
        self._render_playlist(target)

    def remove_selected(self):
        selected = self._selected_playlist_row()
        if selected < 0:
            return
        try:
            self.playlist_model.remove([selected])
        except PlaylistError as exc:
            self.status(str(exc))
            return
        self._render_playlist()

    def save_playlist(self):
        from PySide6.QtWidgets import QFileDialog
        target, _ = QFileDialog.getSaveFileName(
            self, "Save playlist", filter="MPCASU playlist (*.json);;All files (*.*)"
        )
        if not target:
            return
        try:
            Path(target).write_text(json.dumps(self.playlist_model.to_payload(), indent=2) + "\n", encoding="utf-8")
            self.status(f"Playlist saved · {Path(target).name}")
        except OSError as exc:
            QMessageBox.critical(self, "MPCASU", f"Could not save playlist: {exc}")

    def load_playlist(self):
        from PySide6.QtWidgets import QFileDialog
        source, _ = QFileDialog.getOpenFileName(
            self, "Load playlist", filter="MPCASU playlist (*.json);;All files (*.*)"
        )
        if not source:
            return
        try:
            payload = json.loads(Path(source).read_text(encoding="utf-8"))
            loaded = PlaylistModel.from_payload(payload, existing_only=True)
            self.add_files(list(loaded.items))
            self.status(f"Playlist loaded · {Path(source).name}")
        except (OSError, PlaylistError, ValueError, TypeError) as exc:
            QMessageBox.critical(self, "MPCASU", f"Could not load playlist: {exc}")

    def add_watched_folder(self):
        from PySide6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "Select folder to watch")
        if not folder:
            return
        folder = str(Path(folder).expanduser().resolve())
        if folder not in self._watched_folders:
            self._watched_folders.append(folder)
        try:
            scanned = self.media_library.scan([folder])
            self._save_effective_settings()
            self.status(f"Library scan complete · {len(scanned)} file(s) seen")
        except (OSError, ValueError) as exc:
            self.status(f"Library scan failed: {exc}")
        self.show_library_dialog()

    def refresh_watched_folders(self):
        if not self._watched_folders:
            self.status("No watched folders configured")
            return
        try:
            scanned = self.media_library.scan(self._watched_folders)
            self.status(f"Library refreshed · {len(scanned)} file(s) seen")
        except (OSError, ValueError) as exc:
            self.status(f"Library refresh failed: {exc}")

    def show_library_dialog(self):
        dlg = LibraryDialog(self.media_library, self._thumbnail_dir, self)
        if dlg.exec() == QDialog.Accepted:
            for p in dlg.selected_paths():
                self.add_files([p])

    def show_media_info(self):
        path = self.current or self.selected_path()
        if not path or not path.is_file():
            self.status("No local media selected for information")
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
                probe = {
                    "streams": streams,
                    "format": {
                        "format_name": "CASUNAT2 segmented media",
                        "duration": self.backend.duration() if isinstance(self.backend, NativeCasuBackend) else "unknown",
                        "size": path.stat().st_size,
                        "tags": manifest.get("metadata", {}),
                    },
                }
            elif native:
                manifest = read_native(path, verify_payload=True).manifest
                source = path
                probe = {
                    "streams": manifest.get("streams", []),
                    "format": {
                        "format_name": "CASU native container",
                        "duration": manifest.get("source", {}).get("duration_s", "unknown"),
                        "size": path.stat().st_size,
                    },
                }
            else:
                source = self._source_for(path)
                probe = ffprobe(source)

            lines = [
                f"File: {path.name}",
                f"Source: {source.name}",
                f"Container: {probe.get('format', {}).get('format_name', 'unknown')}",
                f"Duration: {probe.get('format', {}).get('duration', 'unknown')} s",
                f"Size: {probe.get('format', {}).get('size', 'unknown')} bytes",
            ]
            metadata = probe.get("format", {}).get("tags", {})
            if isinstance(metadata, dict):
                for key in ("title", "artist", "album", "album_artist", "date", "genre"):
                    value = metadata.get(key)
                    if value not in (None, ""):
                        lines.append(f"{key.replace('_', ' ').title()}: {value}")
            if path.suffix.lower() == ".casu":
                lines.extend([
                    "CASU: verified native CASUNAT2" if native_v2 else
                    "CASU: verified CASUNAT1 compatibility envelope" if native else
                    "CASU: validated sidecar manifest",
                    f"Segment hints: {len(self._visual_segments)}",
                ])
            for index, stream in enumerate(probe.get("streams", [])):
                details = [
                    f"stream {index}: {stream.get('codec_type', 'unknown')}",
                    str(stream.get('codec_name', 'unknown')),
                ]
                if stream.get("tags", {}).get("language"):
                    details.append(f"language={stream['tags']['language']}")
                if stream.get("width") and stream.get("height"):
                    details.append(f"{stream['width']}×{stream['height']}")
                if stream.get("sample_rate"):
                    details.append(f"{stream['sample_rate']} Hz")
                if stream.get("channels"):
                    details.append(f"{stream['channels']} channels")
                if stream.get("avg_frame_rate") and stream.get("avg_frame_rate") != "0/0":
                    details.append(f"fps={stream['avg_frame_rate']}")
                lines.append(" · ".join(details))

            dlg = QDialog(self)
            dlg.setWindowTitle("Media information")
            dlg.setMinimumSize(600, 400)
            dlg.setStyleSheet(stylesheet())
            layout = QVBoxLayout(dlg)
            browser = QTextBrowser()
            browser.setPlainText("\n".join(lines))
            browser.setObjectName("Panel")
            layout.addWidget(browser)
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dlg.accept)
            layout.addWidget(close_btn, 0, Qt.AlignRight)
            dlg.exec()

        except (CasuError, NativeCasuError, NativeV2Error, OSError, ValueError) as exc:
            QMessageBox.critical(self, "MPCASU", f"Media information unavailable: {exc}")

    # --- Sync delays ---

    def set_audio_delay_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Audio delay")
        dlg.setStyleSheet(stylesheet())
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Milliseconds (-5000 to 5000):"))
        spin = QDoubleSpinBox()
        spin.setRange(-5000, 5000)
        spin.setValue(self._audio_delay_ms)
        layout.addWidget(spin)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(lambda: (self._set_media_delay("audio", spin.value()), dlg.accept()))
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        dlg.exec()

    def set_subtitle_delay_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Subtitle delay")
        dlg.setStyleSheet(stylesheet())
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Milliseconds (-5000 to 5000):"))
        spin = QDoubleSpinBox()
        spin.setRange(-5000, 5000)
        spin.setValue(self._subtitle_delay_ms)
        layout.addWidget(spin)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(lambda: (self._set_media_delay("subtitle", spin.value()), dlg.accept()))
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        dlg.exec()

    def _set_media_delay(self, kind: str, milliseconds: float):
        value = max(-5000.0, min(5000.0, float(milliseconds)))
        if self.backend:
            try:
                if kind == "audio":
                    value = self.backend.set_audio_delay(value)
                else:
                    value = self.backend.set_subtitle_delay(value)
            except BackendError as exc:
                self.status(str(exc))
                return
        if kind == "audio":
            self._audio_delay_ms = value
        else:
            self._subtitle_delay_ms = value
        self._persist_media_preferences()
        self.status(f"{kind.title()} delay {value:+g} ms")

    # --- CASU visual state ---

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
                    if chunk.chunk_type in {ChunkType.VIDEO_KEY_STATE, ChunkType.VIDEO_TILE_UPDATE}
                ]
                self._visual_video_segments = list(self._visual_segments)
                return
            manifest = (read_native(path, verify_payload=True).manifest if magic == b"CASUNAT1"
                        else json.loads(path.read_text(encoding="utf-8")))
            errors = validate_manifest(manifest)
            if errors:
                self._visual_state = "invalid CASU: " + errors[0]
                return
            self._visual_video_segments = [s for s in manifest.get("video", {}).get("segments", []) if isinstance(s, dict)]
            self._visual_audio_segments = [s for s in manifest.get("audio", {}).get("segments", []) if isinstance(s, dict)]
            self._visual_segments = self._visual_video_segments + self._visual_audio_segments
            self._scheduler = CasuScheduler.from_manifest(manifest, "video" if self._visual_video_segments else "audio")
            self._visual_state = "CASU state map" if self._visual_segments else "CASU empty map"
        except (OSError, ValueError, TypeError, NativeCasuError, NativeV2Error):
            self._visual_state = "invalid CASU"

    # --- Settings persistence ---

    def _apply_backend_settings(self):
        if not self.backend:
            return
        self._volume = self.backend.set_volume(self._volume)
        self.backend.set_mute(self._muted)
        if self._audio_device:
            try:
                self.backend.set_audio_device(self._audio_device)
            except BackendError:
                self._audio_device = None

    def _apply_playback_rate(self):
        if not self.backend:
            return
        try:
            self._rate = self.backend.set_rate(self._rate)
        except BackendError:
            if not isinstance(self.backend, NativeCasuBackend):
                raise
            self._rate = self.backend.set_rate(1.0)
        self._rate_btn.setText(f"{self._rate:g}×")

    def _apply_media_preferences(self):
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
            self._subtitle_delay_ms = self.backend.set_subtitle_delay(self._subtitle_delay_ms)
        except BackendError:
            self._subtitle_delay_ms = 0.0

    def _persist_media_preferences(self):
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

    def _save_effective_settings(self):
        self.settings_store.save(PlayerSettings(
            self._volume, self._muted, self._rate, self._audio_device,
            tuple(self._watched_folders),
        ))

    # --- Session ---

    def _restore_session(self):
        try:
            payload = json.loads(self._session_file.read_text(encoding="utf-8"))
            self.add_files([Path(v) for v in payload.get("playlist", []) if Path(v).is_file()])
            self._resume_source = str(payload.get("current", "")) or None
            self._resume_position = max(0.0, float(payload.get("position", 0.0)))
            geometry = payload.get("geometry")
            if isinstance(geometry, str) and geometry:
                try:
                    vals = geometry.split("+")
                    if len(vals) >= 3:
                        self.resize(int(vals[0].split("x")[0]), int(vals[0].split("x")[1]))
                except (ValueError, IndexError):
                    pass
        except (OSError, ValueError, TypeError):
            pass

    def closeEvent(self, event):
        resume_position = self.backend.position() if self.backend else self._seek_slider._position
        self._persist_media_preferences()
        try:
            self._session_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._session_file.with_suffix(".tmp")
            tmp.write_text(json.dumps({
                "playlist": [str(item) for item in self.playlist_model.items],
                "volume": self._volume,
                "muted": self._muted,
                "rate": self._rate,
                "current": str(self.current) if self.current else None,
                "position": resume_position,
                "geometry": f"{self.width()}x{self.height()}+{self.x()}+{self.y()}",
            }, indent=2) + "\n", encoding="utf-8")
            tmp.replace(self._session_file)
        except OSError:
            pass
        if self.current and self.current.is_file():
            try:
                self.media_library.record_progress(self.current, resume_position, self.duration or None)
            except OSError:
                pass
        try:
            self._save_effective_settings()
        except OSError:
            pass
        self.controller.close()
        self.backend = None
        self.media_library.close()
        event.accept()

    # --- Backend events ---

    def _backend_event(self, state: PlaybackState):
        QTimer.singleShot(0, lambda s=state: self._apply_backend_event(s))
    def _apply_backend_event(self, state: PlaybackState):
        if state == PlaybackState.PLAYING:
            self._paused = False
            self._play_btn.setText("⏸")
        elif state == PlaybackState.PAUSED:
            self._paused = True
            self._play_btn.setText("▶")
        elif state == PlaybackState.ERROR:
            detail_reader = getattr(self.backend, "last_error", None)
            detail = detail_reader() if callable(detail_reader) else None
            self.status("Playback error — " + (detail or "decoder or output failed"))
            self._diagnostics_bar.set_values(support="backend error; inspect media information/logs")
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
            self.status("Playback unavailable — libVLC did not enter active playback")
            self._diagnostics_bar.set_values(support="backend opened; decoder or output unavailable")

    def _source_for(self, path: Path) -> Path:
        if path.suffix.lower() != ".casu":
            return path
        try:
            with path.open("rb") as handle:
                if handle.read(8) in {b"CASUNAT1", b"CASUNAT2"}:
                    return path
        except OSError as exc:
            raise CasuError(f"could not read CASU container: {path}") from exc
        manifest = json.loads(path.read_text(encoding="utf-8"))
        errors = validate_manifest(manifest)
        if errors:
            raise CasuError(f"invalid CASU manifest: {errors[0]}")
        return resolve_casu_source(path)

    # --- Polling ---

    def _sync_position(self):
        if self.backend and not self._paused:
            pos = min(self.duration, self.backend.position())
            self._seek_slider.set_position(pos)
            self._update_time_labels(pos)

    def _update_time_labels(self, pos: float):
        self._time_current.setText(format_duration(pos))
        self._time_total.setText(format_duration(self.duration if self.duration > 0 else None))

    def _poll(self):
        if self.backend and not self._dragging and not self._paused:
            self._sync_position()
            state = self.backend.state()
            if state == PlaybackState.ENDED and not self._advancing and not self._end_handled:
                self._end_handled = True
                self._advancing = True
                try:
                    self.play_next(automatic=True)
                finally:
                    self._advancing = False
            elif state == PlaybackState.ERROR:
                self.status("Playback error detected")
                self._video_surface.set_video_active(False)


    def _backend_event(self, state: PlaybackState):
        QTimer.singleShot(0, lambda s=state: self._apply_backend_event(s))
