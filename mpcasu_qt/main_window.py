# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""MPCASU Qt main window — full-featured media player UI."""
from __future__ import annotations

import json
import math
import os
import random
import threading
import time
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve, QObject, QPropertyAnimation, QRect, Qt, QTimer, Signal, Slot,
    QSize,
)
from PySide6.QtGui import (
    QAction, QColor, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap,
    QTextDocument, QImage, QLinearGradient, QBrush, QGuiApplication,
)
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox,
    QStackedWidget, QStatusBar, QTextBrowser, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget, QDoubleSpinBox, QGridLayout,
)

from casu.core import CasuError, ffprobe, resolve_casu_source
from casu.locations import (
    LocationResolutionError, is_youtube_url, resolve_media_location,
)
from casu.schema import validate_manifest
from casu.scheduler import CasuScheduler
from casu.library import MediaLibrary, PlaybackPreferences
from casu.media import TrackKind
from casu.playlist import (
    PlaylistError, PlaylistModel, detect_entry_type, detect_media_type,
    load_playlist_file, playlist_names, save_playlist_file,
)
from casu.settings import SettingsStore
from casu.spotify import (SpotifyError, expand_spotify, fetch_spotify_metadata,
                          is_spotify_url, resolve_spotify_url, search_spotify,
                          spotify_kind, youtube_handoff_query)
from casu.thumbnail import thumbnail_for
from casu.waveform import decode_all_pcm, live_spectrum, window_peaks
from casu.recording import MediaRecorder, RecordingError

from casu.native import NativeCasuError, read_native
from casu.native_v2 import ChunkType, NativeV2Error, read_native_v2

from mpcasu_backend import (
    BackendError, CasuBackend, LibVLCBackend, PlaybackState,
    display_media_source,
)
from mpcasu_native_backend import NativeCasuBackend, PulseAudioSink
from mpcasu_playback import PlaybackController

from mpcasu_qt.theme import PALETTE, METRICS, format_duration, stylesheet
from mpcasu_qt.videoframe import QtVideoSurfaceSink, VideoSurface

MEDIA_EXTENSIONS = {".mp4", ".mp3", ".mkv", ".m4v", ".mov", ".flac", ".wav", ".ogg", ".webm", ".m4a", ".aac", ".opus", ".aiff", ".alac", ".casu"}

AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".opus", ".aiff", ".alac"}


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
        self.setFixedWidth(METRICS.sidebar_width)
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
        sub.setContentsMargins(16, 0, 16, 12)
        layout.addWidget(sub)

        logo_path = Path(__file__).resolve().parent.parent / "assets" / "mpcasu_player_logo_header.png"
        if logo_path.is_file():
            logo = QLabel()
            logo.setContentsMargins(16, 0, 16, 10)
            pixmap = QPixmap(str(logo_path))
            if not pixmap.isNull():
                logo.setPixmap(pixmap.scaledToWidth(150, Qt.SmoothTransformation))
                logo.setFixedHeight(44)
                layout.addWidget(logo)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {PALETTE.border}; max-height: 1px;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        nav_items = [
            ("LIBRARY", ["NOW PLAYING", "LOCAL FILES", "WEB & STREAMS",
                         "PLAYLISTS", "IPTV / EPG"]),
            ("SEARCH", ["YOUTUBE", "SPOTIFY"]),
            ("CASU", ["CASU FILES"]),
            ("SYSTEM", ["OPTIONS", "ABOUT"]),
        ]
        self.NAV_ICONS = {
            "NOW PLAYING": "▶",
            "LOCAL FILES": "▣",
            "WEB & STREAMS": "▤",
            "PLAYLISTS": "≡",
            "IPTV / EPG": "▦",
            "YOUTUBE": "▷",
            "SPOTIFY": "♪",
            "CASU FILES": "◈",
            "OPTIONS": "⚙",
            "ABOUT": "ⓘ",
        }
        self._nav_buttons: list[QPushButton] = []
        self._rail_hidden: list = [sub]
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for section_title, items in nav_items:
            section = QLabel(section_title)
            section.setObjectName("SidebarSection")
            layout.addWidget(section)
            self._rail_hidden.append(section)
            for item in items:
                btn = QPushButton(item)
                btn.setObjectName("NavItem")
                btn.setCheckable(True)
                btn.setProperty("nav_name", item)
                btn.setToolTip(item)
                btn.setCursor(Qt.PointingHandCursor)
                btn.clicked.connect(lambda checked=False, name=item: self.navRequested.emit(name))
                self._nav_group.addButton(btn)
                self._nav_buttons.append(btn)
                layout.addWidget(btn)

        layout.addStretch()

        version = QLabel("MPCASU 1.0.6")
        version.setObjectName("NowPlayingMeta")
        version.setContentsMargins(16, 8, 16, 8)
        version.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        layout.addWidget(version)
        self._rail_hidden.append(version)
        self._rail = False

    def set_rail(self, on: bool):
        if on == self._rail:
            return
        self._rail = on
        self.setFixedWidth(70 if on else METRICS.sidebar_width)
        for widget in self._rail_hidden:
            widget.setVisible(not on)
        for btn in self._nav_buttons:
            name = str(btn.property("nav_name"))
            btn.setText(self.NAV_ICONS.get(name, name[0]) if on else name)

    def select(self, name: str):
        for btn in self._nav_buttons:
            if btn.property("nav_name") == name:
                btn.setChecked(True)
                return

    def set_active(self, entry: str):
        for btn in self._nav_buttons:
            btn.setChecked(btn.property("nav_name") == entry)


class QueueTree(QTreeWidget):
    """Queue list with drag-reorder, Delete removal and a context menu."""

    orderChanged = Signal(list)
    removePressed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setColumnCount(2)
        self.setColumnWidth(0, METRICS.playlist_width - 90)
        self.setRootIsDecorated(True)
        self.setUniformRowHeights(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {PALETTE.surface_alt};
                border: 0; outline: 0; font-size: 12px;
            }}
            QTreeWidget::item {{
                background: transparent;
                border-bottom: 1px solid {PALETTE.border};
                padding: 7px 6px; color: {PALETTE.text};
            }}
            QTreeWidget::item:hover {{ background-color: #171b20; }}
            QTreeWidget::item:selected {{
                background-color: {PALETTE.accent_wash};
                color: {PALETTE.accent};
            }}
            QTreeWidget::branch {{ background: transparent; }}
            QScrollBar:vertical {{ background: {PALETTE.surface}; width: 10px; }}
            QScrollBar::handle:vertical {{ background: {PALETTE.border_strong}; border-radius: 5px; }}
        """)

    def dropEvent(self, event):
        super().dropEvent(event)
        order = []
        for index in range(self.topLevelItemCount()):
            order.append(self.topLevelItem(index).data(0, Qt.UserRole))
        self.orderChanged.emit(order)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            rows = sorted({self.indexOfTopLevelItem(item)
                           for item in self.selectedItems()
                           if self.indexOfTopLevelItem(item) >= 0}, reverse=True)
            if rows:
                self.removePressed.emit(rows)
                return
        super().keyPressEvent(event)


class PlaylistPane(QFrame):
    """Right-side playlist drawer with expandable playlists."""

    playRequested = Signal(int)
    removeRequested = Signal(list)
    moveRequested = Signal(int, int)
    orderChanged = Signal(list)
    childPlayRequested = Signal(str)
    saveRequested = Signal()
    loadRequested = Signal()
    addRequested = Signal()
    urlRequested = Signal()
    renameRequested = Signal(int)

    PLAYLIST_SUFFIXES = {".m3u", ".m3u8", ".pls", ".json"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PlaylistPane")
        self.setFixedWidth(METRICS.playlist_width)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("TopBar")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(12, 14, 12, 8)
        title = QLabel("PLAYLIST")
        title.setObjectName("NowPlayingTitle")
        title.setStyleSheet("font-size: 14px; background: transparent;")
        header_layout.addWidget(title)
        sub = QLabel("Queue · expandable · drag to reorder")
        sub.setObjectName("NowPlayingMeta")
        header_layout.addWidget(sub)
        self._view_combo = QComboBox()
        self._view_combo.setObjectName("IconButton")
        for label, key in [("All items", "all"), ("Local files", "files"),
                           ("Streams / IPTV", "streams"), ("Playlists", "playlists"),
                           ("CASU", "casu"), ("YouTube", "youtube"),
                           ("Spotify", "spotify")]:
            self._view_combo.addItem(label, key)
        self._view_combo.currentIndexChanged.connect(lambda *_: self._apply_view_filter())
        header_layout.addWidget(self._view_combo)
        actions = QHBoxLayout()
        actions.setSpacing(6)
        choose_btn = QPushButton("Choose files")
        choose_btn.setObjectName("PrimaryButton")
        choose_btn.setToolTip("Add media files to the queue (Ctrl+O)")
        choose_btn.clicked.connect(lambda: self.addRequested.emit())
        actions.addWidget(choose_btn, 1)
        url_btn = QPushButton("Add URL")
        url_btn.setObjectName("IconButton")
        url_btn.setToolTip("Add a network stream URL (Ctrl+L)")
        url_btn.clicked.connect(lambda: self.urlRequested.emit())
        actions.addWidget(url_btn)
        header_layout.addLayout(actions)
        layout.addWidget(header)

        self.tree = QueueTree(self)
        self._collapsed: set = set()
        self._all_paths: list = []
        self._display_titles: dict = {}
        self._search = ""
        self._thumb_bridge = _ThreadBridge()
        self._thumb_bridge.resultReady.connect(self._apply_thumb)
        self._thumb_dir = Path.home() / ".cache" / "mpcasu" / "thumbnails"
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemExpanded.connect(self._on_expanded)
        self.tree.itemCollapsed.connect(self._on_collapsed)
        self.tree.orderChanged.connect(lambda order: self.orderChanged.emit(order))
        self.tree.removePressed.connect(lambda rows: self.removeRequested.emit(rows))
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tree.setIconSize(QSize(METRICS.thumbnail_width, METRICS.thumbnail_height))
        layout.addWidget(self.tree, 1)

        controls = QFrame()
        controls.setObjectName("TopBar")
        cl = QHBoxLayout(controls)
        cl.setContentsMargins(10, 8, 10, 8)
        up_btn = QPushButton("↑")
        up_btn.setObjectName("IconButton")
        up_btn.setFixedWidth(30)
        up_btn.setToolTip("Move up")
        up_btn.clicked.connect(lambda: self.moveRequested.emit(-1, self.selected_row()))
        cl.addWidget(up_btn)
        down_btn = QPushButton("↓")
        down_btn.setObjectName("IconButton")
        down_btn.setFixedWidth(30)
        down_btn.setToolTip("Move down")
        down_btn.clicked.connect(lambda: self.moveRequested.emit(1, self.selected_row()))
        cl.addWidget(down_btn)
        remove_btn = QPushButton("×")
        remove_btn.setObjectName("IconButton")
        remove_btn.setFixedWidth(30)
        remove_btn.setToolTip("Remove selected entry (Del)")
        remove_btn.clicked.connect(lambda: self.removeRequested.emit([self.selected_row()])
                                   if self.selected_row() >= 0 else None)
        cl.addWidget(remove_btn)
        rename_btn = QPushButton("✎")
        rename_btn.setObjectName("IconButton")
        rename_btn.setFixedWidth(30)
        rename_btn.setToolTip("Rename the selected queue entry")
        rename_btn.clicked.connect(lambda: self.renameRequested.emit(self.selected_row()))
        cl.addWidget(rename_btn)
        cl.addStretch()
        load_btn = QPushButton("Load")
        load_btn.setObjectName("IconButton")
        load_btn.setFixedWidth(46)
        load_btn.setToolTip("Load M3U/PLS/JSON playlist")
        load_btn.clicked.connect(lambda: self.loadRequested.emit())
        cl.addWidget(load_btn)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("IconButton")
        save_btn.setFixedWidth(46)
        save_btn.setToolTip("Save queue as M3U/PLS/JSON playlist")
        save_btn.clicked.connect(lambda: self.saveRequested.emit())
        cl.addWidget(save_btn)
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

    # --- public API used by MainWindow ---

    def select_row(self, row: int):
        if 0 <= row < self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(row))

    def selected_row(self) -> int:
        items = self.tree.selectedItems()
        for item in items:
            row = self.tree.indexOfTopLevelItem(item)
            if row >= 0:
                return row
        return -1

    def populate(self, paths: list, selected: int = -1):
        self._all_paths = list(paths)
        view = str(self._view_combo.currentData() or "all")
        visible = [(index, path) for index, path in enumerate(self._all_paths)
                   if self._matches(path, view)]
        self.tree.blockSignals(True)
        self.tree.clear()
        for _index, path in visible:
            item = QTreeWidgetItem([self._label_for(path)])
            item.setData(0, Qt.UserRole, str(path))
            item.setToolTip(0, str(path))
            item.setText(1, self._badge_for(path))
            item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            item.setForeground(1, QBrush(QColor(PALETTE.text_faint)))
            item.setFont(1, QFont(item.font(0).family(), max(8, item.font(0).pointSize() - 1)))
            item.setIcon(0, QIcon(self._thumb_for(path)))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled
                          | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
            self.tree.addTopLevelItem(item)
            if self._is_playlist(path):
                placeholder = QTreeWidgetItem(["…"])
                placeholder.setFlags(Qt.NoItemFlags)
                item.addChild(placeholder)
                item.setExpanded(str(path) not in self._collapsed)
        self.tree.blockSignals(False)
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            if item.isExpanded() and self._is_playlist(item.data(0, Qt.UserRole) or ""):
                self._expand_playlist_item(item)
                item.setExpanded(True)
        if 0 <= selected < len(self._all_paths):
            want = str(self._all_paths[selected])
            for index in range(self.tree.topLevelItemCount()):
                if str(self.tree.topLevelItem(index).data(0, Qt.UserRole)) == want:
                    self.tree.setCurrentItem(self.tree.topLevelItem(index))
                    break
        if self._search:
            self._apply_search()
        self._request_thumbnails()
        self.empty_label.setVisible(len(self._all_paths) == 0)

    def set_search(self, text: str):
        self._search = (text or "").strip().lower()
        self._apply_search()

    def set_view(self, key: str):
        index = self._view_combo.findData(key)
        if index >= 0:
            self._view_combo.setCurrentIndex(index)
        self._apply_view_filter()

    def _apply_search(self):
        query = self._search
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            label = item.text(0).lower()
            child_hits = 0
            if query and self._is_playlist(item.data(0, Qt.UserRole) or ""):
                if not item.isExpanded():
                    item.setExpanded(True)
                for c in range(item.childCount()):
                    child = item.child(c)
                    hit = bool(query) and query in child.text(0).lower()
                    child.setHidden(bool(query) and not hit)
                    child_hits += 1 if hit else 0
            item.setHidden(bool(query) and query not in label and child_hits == 0)

    def _request_thumbnails(self):
        jobs = []
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            path = str(item.data(0, Qt.UserRole) or "")
            if not path or path.startswith(("http://", "https://", "rtsp://", "rtmp://")):
                continue
            if Path(path).suffix.lower() not in {".mp4", ".mkv", ".webm", ".mov", ".avi"}:
                continue
            jobs.append(path)
        if not jobs:
            return
        bridge = self._thumb_bridge
        cache = str(self._thumb_dir)

        def worker():
            from casu.thumbnail import thumbnail_for
            for path in jobs:
                try:
                    thumb = thumbnail_for(path, cache)
                except Exception:  # noqa: BLE001 - thumbnails are optional
                    thumb = None
                if thumb is not None:
                    bridge.resultReady.emit((path, str(thumb)))
        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _apply_thumb(self, payload):
        path, thumb = payload
        pix = QPixmap(thumb)
        if pix.isNull():
            return
        scaled = pix.scaled(METRICS.thumbnail_width, METRICS.thumbnail_height,
                            Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            if str(item.data(0, Qt.UserRole) or "") == path:
                item.setIcon(0, QIcon(scaled))

    def _apply_view_filter(self):
        current = self.tree.currentItem()
        sel = -1
        if current is not None and current.parent() is None:
            want = str(current.data(0, Qt.UserRole))
            if want in [str(p) for p in self._all_paths]:
                sel = [str(p) for p in self._all_paths].index(want)
        self.populate(self._all_paths, sel)

    def _matches(self, path, view: str) -> bool:
        s = str(path)
        low = s.lower()
        is_url = low.startswith(("http://", "https://", "rtsp://", "rtmp://"))
        if view == "all":
            return True
        if view == "playlists":
            return self._is_playlist(path)
        if view == "files":
            return not is_url and not self._is_playlist(path)
        if view == "casu":
            return low.endswith((".casu", ".mp5"))
        if view == "youtube":
            return "youtube.com" in low or "youtu.be" in low
        if view == "spotify":
            return "spotify.com" in low
        if view == "streams":
            return is_url and not self._is_playlist(path)
        return True

    def clear(self):
        self.tree.clear()
        self.empty_label.setVisible(True)

    # --- internals ---

    def _thumb_for(self, path) -> QPixmap:
        """Web-style 54x38 thumbnail: red/dark gradient + format glyph."""
        pixmap = QPixmap(METRICS.thumbnail_width, METRICS.thumbnail_height)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        gradient = QLinearGradient(0, 0, METRICS.thumbnail_width, METRICS.thumbnail_height)
        gradient.setColorAt(0.0, QColor("#391119"))
        gradient.setColorAt(1.0, QColor("#080b0f"))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, METRICS.thumbnail_width, METRICS.thumbnail_height, 5, 5)
        glyph = self._badge_for(path)
        short = {"MP4": "▶", "MP3": "♪", "CASU": "◈", "MP5": "◉", "PLAYLIST": "≡",
                 "STREAM": "∿", "YT": "▶", "RTSP": "∿", "RTMP": "∿", "HLS": "∿"}.get(glyph, "•")
        painter.setPen(QPen(QColor(PALETTE.text), 15))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, short)
        painter.end()
        return pixmap

    @staticmethod
    def _is_playlist(path) -> bool:
        try:
            return Path(str(path)).suffix.lower() in PlaylistPane.PLAYLIST_SUFFIXES
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _badge_for(path) -> str:
        text = str(path)
        if text.startswith(("http://", "https://", "rtsp://", "rtmp://")):
            try:
                etype = detect_entry_type(text)
            except (ValueError, TypeError):
                etype = "http-stream"
            return {"youtube": "YT", "http-stream": "STREAM",
                    "rtsp-stream": "RTSP", "rtmp-stream": "RTMP"}.get(
                etype, "STREAM")
        try:
            return detect_media_type(path)
        except (OSError, ValueError, TypeError):
            return "MEDIA"

    def _label_for(self, path) -> str:
        text = str(path)
        display = self._display_titles.get(text, "")
        if display:
            return display
        return (Path(text).name if not text.startswith(("http://", "https://")) else text)

    @staticmethod
    def _child_badge(entry) -> str:
        text = str(entry)
        try:
            etype = detect_entry_type(text)
        except (ValueError, TypeError):
            etype = "local-file"
        return {"local-file": detect_media_type(text) if Path(text).suffix else "FILE",
                "casu": "CASU", "mp5": "MP5", "playlist": "PL",
                "http-stream": "STREAM", "youtube": "YT",
                "rtsp-stream": "RTSP", "rtmp-stream": "RTMP"}.get(etype, "MEDIA")

    @staticmethod
    def _child_label(entry, display: str = "") -> str:
        text = str(entry)
        name = display or (Path(text).name if not text.startswith(("http://", "https://", "rtsp://")) else text)
        return name

    def _on_clear(self):
        rows = sorted({self.tree.indexOfTopLevelItem(item)
                       for item in self.tree.selectedItems()
                       if self.tree.indexOfTopLevelItem(item) >= 0}, reverse=True)
        self.removeRequested.emit(rows)

    def _on_double_click(self, item, _column):
        if item.parent() is None and self._is_playlist(item.data(0, Qt.UserRole) or ""):
            item.setExpanded(not item.isExpanded())
            return
        row = self.tree.indexOfTopLevelItem(item)
        if row >= 0:
            self.playRequested.emit(row)
            return
        parent = item.parent()
        if parent is not None and item.data(0, Qt.UserRole):
            self.childPlayRequested.emit(str(item.data(0, Qt.UserRole)))

    def _on_item_clicked(self, item, _column):
        if item.parent() is None and self._is_playlist(item.data(0, Qt.UserRole) or ""):
            item.setExpanded(not item.isExpanded())

    def _on_expanded(self, item):
        self._collapsed.discard(item.data(0, Qt.UserRole))
        self._expand_playlist_item(item)

    def _on_collapsed(self, item):
        self._collapsed.add(item.data(0, Qt.UserRole))

    def _expand_playlist_item(self, item):
        if item.childCount() and item.child(0).data(0, Qt.UserRole):
            return
        source = str(item.data(0, Qt.UserRole))
        while item.childCount():
            item.removeChild(item.child(0))
        try:
            loaded = load_playlist_file(source)
        except (PlaylistError, OSError, ValueError) as exc:
            error_item = QTreeWidgetItem([f"Could not expand: {exc}"])
            error_item.setFlags(Qt.NoItemFlags)
            item.addChild(error_item)
            return
        entries = list(loaded.items)
        if not entries:
            empty_item = QTreeWidgetItem(["(empty playlist)"])
            empty_item.setFlags(Qt.NoItemFlags)
            item.addChild(empty_item)
            return
        names = playlist_names(source)
        for entry in entries:
            display = names.get(str(entry), "")
            child = QTreeWidgetItem([self._child_label(entry, display)])
            child.setData(0, Qt.UserRole, str(entry))
            if display:
                child.setData(0, Qt.UserRole + 1, display)
            child.setText(1, self._child_badge(entry))
            child.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            child.setForeground(1, QBrush(QColor(PALETTE.text_faint)))
            child.setFont(1, QFont(child.font(0).family(), max(8, child.font(0).pointSize() - 1)))
            child.setToolTip(0, str(entry))
            child.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            item.addChild(child)

    def name_for(self, url: str) -> str:
        """Display name for a queued stream URL (from playlist EXTINF names)."""
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            for c in range(parent.childCount()):
                child = parent.child(c)
                if str(child.data(0, Qt.UserRole)) == str(url):
                    return str(child.data(0, Qt.UserRole + 1) or "").strip()
        return ""

    def _context_menu(self, position):
        item = self.tree.itemAt(position)
        menu = QMenu(self)
        if item is None:
            menu.addAction("Clear queue", lambda: self.removeRequested.emit([]))
            menu.exec(self.tree.viewport().mapToGlobal(position))
            return
        row = self.tree.indexOfTopLevelItem(item)
        if row >= 0:
            menu.addAction("Play", lambda: self.playRequested.emit(row))
            if item.childCount() or self._is_playlist(str(item.data(0, Qt.UserRole))):
                if item.isExpanded():
                    menu.addAction("Collapse", item.setCollapsed)
                else:
                    menu.addAction("Expand", item.setExpanded)
            menu.addSeparator()
            menu.addAction("Move up", lambda: self.moveRequested.emit(-1, row))
            menu.addAction("Move down", lambda: self.moveRequested.emit(1, row))
            menu.addAction("Remove", lambda: self.removeRequested.emit([row]))
        else:
            parent = item.parent()
            if parent is not None and item.data(0, Qt.UserRole):
                menu.addAction("Play", lambda: self.childPlayRequested.emit(
                    str(item.data(0, Qt.UserRole))))
        menu.exec(self.tree.viewport().mapToGlobal(position))


class VisualizerWidget(QWidget):
    """Web-style audio visualizer overlay: red spectrum bars + waveform + cursor.

    Renders measured PCM peaks/spectrum (casu.waveform) for audio-only media,
    mirroring the web player's canvas visualizer. Hidden while real video is
    on screen or when the visualizer mode is "off".
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()
        self._peaks: tuple[float, ...] = ()
        self._bands: tuple[float, ...] = ()
        self._live: tuple[float, ...] | None = None
        self._mode = "spectrum"
        self._position = 0.0
        self._duration = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(66)
        self._timer.timeout.connect(self.update)
        self._timer.start()

    def configure(self, mode: str, peaks, bands, duration: float):
        self._mode = mode
        self._peaks = tuple(peaks or ())
        self._bands = tuple(bands or ())
        self._duration = max(0.0, float(duration or 0.0))
        visible = mode != "off" and (self._peaks or self._bands)
        self.setVisible(bool(visible))
        self.update()

    def set_position(self, position: float):
        self._position = float(position or 0.0)

    def set_live(self, bands):
        self._live = tuple(bands)
        if self._live and self._mode != "off":
            self.setVisible(True)
        self.update()

    def clear_live(self):
        self._live = None
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt naming
        if self._mode == "off":
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width, height = self.width(), self.height()
        bands = self._live or self._bands
        if self._mode in ("spectrum", "both") and bands:
            count = len(bands)
            bar_w = max(2, width // max(1, count) - 2)
            for index, value in enumerate(bands):
                bar_h = max(2, int(value * (height - 6)))
                x = index * (width // count)
                color = QColor(PALETTE.accent) if index % 2 == 0 else QColor(PALETTE.accent_dim)
                painter.fillRect(x, height - bar_h, bar_w, bar_h, color)
        if self._mode in ("waveform", "both") and self._peaks:
            pen = QPen(QColor(PALETTE.accent_hot), 1.5)
            painter.setPen(pen)
            count = len(self._peaks)
            mid = height // 2
            previous = None
            for index, value in enumerate(self._peaks):
                x = int(index * width / max(1, count - 1))
                amp = max(1, int(value * (height // 2 - 3)))
                point = (x, mid - amp)
                if previous is not None:
                    painter.drawLine(previous[0], previous[1], x, mid + amp)
                previous = (x, mid - amp)
            painter.setPen(QPen(QColor(PALETTE.text_muted), 1))
            for index, value in enumerate(self._peaks):
                x = int(index * width / max(1, count - 1))
                amp = max(1, int(value * (height // 2 - 3)))
                painter.drawLine(x, mid - amp, x, mid + amp)
        if self._duration > 0:
            cursor_x = int(min(1.0, self._position / self._duration) * width)
            painter.fillRect(cursor_x, 0, 2, height, QColor(PALETTE.text))
        painter.end()


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
            ("LIVE GUIDE", "no EPG loaded"),
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

    def set_values(self, *, support=None, integrity=None, segmented=None, guide=None):
        mapping = {
            "SEGMENTED PLAYBACK": segmented,
            "LIVE GUIDE": guide,
            "INTEGRITY MODE": integrity,
            "CASU SUPPORT": support,
        }
        for key, value in mapping.items():
            if value is not None and key in self._labels:
                self._labels[key].setText(value)


class LibraryPage(QFrame):
    """In-window searchable media library (no popup)."""

    addRequested = Signal(list)
    refreshRequested = Signal()

    def __init__(self, media_library, thumbnail_dir, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self._media_library = media_library
        self._thumbnail_dir = thumbnail_dir
        self._paths: list[Path] = []
        self._preview_gen = 0
        self._preview_pixmap: QPixmap | None = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 16)
        layout.setSpacing(10)

        top = QHBoxLayout()
        self._search_entry = QLineEdit()
        self._search_entry.setPlaceholderText("Search the media database…")
        self._search_entry.textChanged.connect(self._refresh)
        top.addWidget(self._search_entry, 1)
        refresh_btn = QPushButton("Refresh watched folders")
        refresh_btn.setObjectName("IconButton")
        refresh_btn.clicked.connect(self._on_refresh)
        top.addWidget(refresh_btn)
        layout.addLayout(top)

        self._results = QListWidget()
        self._results.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._results.itemDoubleClicked.connect(self._add_selected)
        self._results.currentItemChanged.connect(self._load_preview)
        layout.addWidget(self._results, 1)

        self._preview = QLabel("Select media for preview")
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setFixedHeight(160)
        self._preview.setObjectName("Panel")
        layout.addWidget(self._preview)

        bottom = QHBoxLayout()
        bottom.addStretch()
        add_btn = QPushButton("Add to queue")
        add_btn.setObjectName("PrimaryButton")
        add_btn.clicked.connect(self._add_selected)
        bottom.addWidget(add_btn)
        layout.addLayout(bottom)

    backRequested = Signal()

    def _refresh(self):
        self._paths.clear()
        self._results.clear()
        query = self._search_entry.text()
        for item in self._media_library.search(query):
            self._paths.append(item.path)
            marker = "★ " if item.favorite else ""
            resume = f" · resume {item.resume_seconds:.1f}s" if item.resume_seconds else ""
            self._results.addItem(f"{marker}{item.path.name}{resume}  —  {item.path.parent}")

    def _add_selected(self, *_args):
        item = self._results.currentItem()
        if item is None:
            return
        row = self._results.row(item)
        if 0 <= row < len(self._paths):
            self.addRequested.emit([self._paths[row]])

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
        self.refreshRequested.emit()
        self._refresh()


class OptionsPage(QFrame):
    """In-window options area (replaces the settings popup)."""

    applied = Signal(object)
    actionRequested = Signal(str)
    backRequested = Signal()

    def __init__(self, settings_store, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self._settings_store = settings_store
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(14)

        def section(label_text):
            label = QLabel(label_text)
            label.setObjectName("SidebarSection")
            label.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(label)

        settings = self._settings_store.load()

        section("PLAYBACK")
        row = QHBoxLayout()
        row.addWidget(QLabel("Volume"))
        self._volume_spin = QSpinBox()
        self._volume_spin.setObjectName("IconButton")
        self._volume_spin.setRange(0, 200)
        self._volume_spin.setValue(settings.volume)
        row.addWidget(self._volume_spin)
        row.addSpacing(18)
        row.addWidget(QLabel("Rate"))
        self._rate_spin = QDoubleSpinBox()
        self._rate_spin.setObjectName("IconButton")
        self._rate_spin.setRange(0.25, 4.0)
        self._rate_spin.setSingleStep(0.25)
        self._rate_spin.setValue(settings.rate)
        row.addWidget(self._rate_spin)
        row.addStretch()
        layout.addLayout(row)
        self._muted_cb = QCheckBox("Muted")
        self._muted_cb.setChecked(settings.muted)
        layout.addWidget(self._muted_cb)
        self._resume_cb = QCheckBox("Resume playback on startup")
        self._resume_cb.setChecked(settings.resume_playback)
        layout.addWidget(self._resume_cb)

        section("VISUALIZER")
        viz_row = QHBoxLayout()
        self._viz_combo = QComboBox()
        self._viz_combo.setObjectName("IconButton")
        for label, value in [("Spectrum", "spectrum"), ("Waveform", "waveform"),
                             ("Both", "both"), ("Off", "off")]:
            self._viz_combo.addItem(label, value)
        index = self._viz_combo.findData(settings.visualizer)
        self._viz_combo.setCurrentIndex(max(0, index))
        viz_row.addWidget(self._viz_combo)
        viz_row.addStretch()
        layout.addLayout(viz_row)

        section("CACHE")
        cache_row = QHBoxLayout()
        self._cache_spin = QSpinBox()
        self._cache_spin.setObjectName("IconButton")
        self._cache_spin.setRange(64, 8192)
        self._cache_spin.setSuffix(" MiB")
        self._cache_spin.setValue(settings.cache_limit_mib)
        cache_row.addWidget(self._cache_spin)
        clear_btn = QPushButton("Clear yt-dlp temp cache")
        clear_btn.setObjectName("IconButton")
        clear_btn.clicked.connect(lambda: self.actionRequested.emit("clear-cache"))
        cache_row.addWidget(clear_btn)
        cache_row.addStretch()
        layout.addLayout(cache_row)

        section("DATABASE")
        self._folders_label = QLabel("\n".join(settings.watched_folders)
                                     if settings.watched_folders else "No watched folders yet")
        self._folders_label.setObjectName("NowPlayingMeta")
        self._folders_label.setWordWrap(True)
        layout.addWidget(self._folders_label)
        db_btn = QPushButton("Refresh watched folders")
        db_btn.setObjectName("IconButton")
        db_btn.clicked.connect(lambda: self.actionRequested.emit("refresh-db"))
        layout.addWidget(db_btn, 0, Qt.AlignLeft)

        section("RECORDINGS & SNAPSHOTS")
        rec_row = QHBoxLayout()
        self._recordings_entry = QLineEdit()
        self._recordings_entry.setObjectName("IconButton")
        self._recordings_entry.setPlaceholderText("Default folder for recordings and snapshots (empty = ~/Videos/MPCASU)")
        self._recordings_entry.setText(settings.recordings_dir)
        rec_row.addWidget(self._recordings_entry, 1)
        rec_btn = QPushButton("Choose folder…")
        rec_btn.setObjectName("IconButton")
        rec_btn.clicked.connect(self._pick_recordings_dir)
        rec_row.addWidget(rec_btn)
        layout.addLayout(rec_row)
        split_row = QHBoxLayout()
        split_row.addWidget(QLabel("Split recordings every"))
        self._split_spin = QSpinBox()
        self._split_spin.setObjectName("IconButton")
        self._split_spin.setRange(0, 24 * 60)
        self._split_spin.setSuffix(" min")
        self._split_spin.setSpecialValueText("no splitting")
        self._split_spin.setValue(settings.record_split_minutes)
        split_row.addWidget(self._split_spin)
        split_row.addSpacing(12)
        split_row.addWidget(QLabel("Format"))
        self._format_combo = QComboBox()
        self._format_combo.setObjectName("IconButton")
        for fmt in ("mkv", "mp4", "ts", "webm", "ogg", "mp3", "flac", "wav"):
            self._format_combo.addItem(fmt)
        index = self._format_combo.findText(settings.record_format)
        self._format_combo.setCurrentIndex(max(0, index))
        split_row.addWidget(self._format_combo)
        split_row.addStretch()
        layout.addLayout(split_row)

        section("LEGAL")
        self._consent_cb = QCheckBox("I understand that YouTube uses yt-dlp and Spotify uses spotDL (personal use only)")
        self._consent_cb.setChecked(settings.ytdlp_consent)
        layout.addWidget(self._consent_cb)

        section("PROVIDERS")
        providers = QLabel(self._provider_status())
        providers.setObjectName("NowPlayingMeta")
        providers.setWordWrap(True)
        providers.setTextFormat(Qt.PlainText)
        layout.addWidget(providers)

        apply_row = QHBoxLayout()
        apply_row.addStretch()
        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("PrimaryButton")
        apply_btn.clicked.connect(self._apply)
        apply_row.addWidget(apply_btn)
        layout.addLayout(apply_row)
        layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

    def _apply(self):
        settings = self._settings_store.load()
        updated = replace(settings,
                          volume=self._volume_spin.value(),
                          muted=self._muted_cb.isChecked(),
                          rate=self._rate_spin.value(),
                          ytdlp_consent=self._consent_cb.isChecked(),
                          visualizer=str(self._viz_combo.currentData()),
                          resume_playback=self._resume_cb.isChecked(),
                          cache_limit_mib=self._cache_spin.value(),
                          recordings_dir=self._recordings_entry.text().strip(),
                          record_split_minutes=self._split_spin.value(),
                          record_format=str(self._format_combo.currentText()))
        self._settings_store.save(updated)
        self.applied.emit(updated)

    def _pick_recordings_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Recordings & snapshots folder")
        if folder:
            self._recordings_entry.setText(folder)

    @staticmethod
    def _provider_status() -> str:
        import shutil
        from glob import glob
        vlc = bool(shutil.which("vlc")) or bool(glob("/usr/lib/*/libvlc.so*"))
        lines = [
            f"libVLC (legacy playback): {'✓' if vlc else '✗ missing'}",
            f"FFmpeg (convert/analysis): {'✓' if shutil.which('ffmpeg') else '✗ missing'}",
            f"yt-dlp (YouTube provider): {'✓' if shutil.which('yt-dlp') else '✗ missing'}",
        ]
        from casu.spotify import spotdl_binary
        if spotdl_binary():
            lines.append("spotDL (Spotify provider): ✓")
        else:
            lines.append("spotDL (Spotify provider): ✗ not installed — "
                         "python3 -m venv /opt/casu-spotdl && "
                         "/opt/casu-spotdl/bin/pip install spotdl")
        lines.append(f"Deno (optional spotDL helper): {'✓' if shutil.which('deno') else '– optional'}")
        return "\n".join(lines)

    def reload(self):
        settings = self._settings_store.load()
        self._volume_spin.setValue(settings.volume)
        self._muted_cb.setChecked(settings.muted)
        self._rate_spin.setValue(settings.rate)
        self._resume_cb.setChecked(settings.resume_playback)
        self._consent_cb.setChecked(settings.ytdlp_consent)
        self._cache_spin.setValue(settings.cache_limit_mib)
        self._recordings_entry.setText(settings.recordings_dir)
        self._split_spin.setValue(settings.record_split_minutes)
        index = self._format_combo.findText(settings.record_format)
        self._format_combo.setCurrentIndex(max(0, index))
        index = self._viz_combo.findData(settings.visualizer)
        self._viz_combo.setCurrentIndex(max(0, index))
        self._folders_label.setText("\n".join(settings.watched_folders)
                                      if settings.watched_folders else "No watched folders yet")


class EpgPage(QFrame):
    """In-window Live TV / EPG guide (M3U + XMLTV), web-style channel cards."""

    channelActivated = Signal(object)
    backRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self._catalog = None
        self._guide = None
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 16)
        outer.setSpacing(10)

        source_row = QHBoxLayout()
        self._source_entry = QLineEdit()
        self._source_entry.setPlaceholderText("M3U / XMLTV path or http(s) URL…")
        source_row.addWidget(self._source_entry, 1)
        load_file_btn = QPushButton("Load file")
        load_file_btn.setObjectName("IconButton")
        load_file_btn.clicked.connect(self._load_file)
        source_row.addWidget(load_file_btn)
        load_url_btn = QPushButton("Load URL")
        load_url_btn.setObjectName("IconButton")
        load_url_btn.clicked.connect(lambda: self._load_source(self._source_entry.text().strip()))
        source_row.addWidget(load_url_btn)
        outer.addLayout(source_row)

        self._status = QLabel("Load an Extended-M3U playlist (and optional XMLTV guide) to browse channels.")
        self._status.setObjectName("NowPlayingMeta")
        outer.addWidget(self._status)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._grid_host = QWidget()
        self._grid_host.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._grid_host)
        self._grid.setSpacing(8)
        self._scroll.setWidget(self._grid_host)
        outer.addWidget(self._scroll, 1)

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load playlist / guide", str(Path.home()),
            "Playlists & guides (*.m3u *.m3u8 *.pls *.xml *.xmltv);;All files (*)")
        if path:
            self._load_source(path)

    def _load_source(self, source: str):
        if not source:
            return
        try:
            if source.endswith((".xml", ".xmltv")):
                from casu.epg import load_xmltv, fetch_xmltv
                self._guide = fetch_xmltv(source) if source.startswith(("http://", "https://")) else load_xmltv(source)
                self._status.setText(f"Guide loaded: {len(self._guide.entries) if hasattr(self._guide, 'entries') else ''} programmes")
                self._sync_host_epg()
                self._render()
                return
            from casu.epg import load_m3u, fetch_m3u
            self._catalog = fetch_m3u(source) if source.startswith(("http://", "https://")) else load_m3u(source)
            self._status.setText(f"{len(self._catalog.channels)} channels loaded")
            self._sync_host_epg()
            self._render()
        except Exception as exc:  # noqa: BLE001 - show any loader failure inline
            self._status.setText(f"Load failed: {exc}")

    def _sync_host_epg(self):
        host = self.parent()
        if host is None or not hasattr(host, "_epg_catalog"):
            return
        host._epg_catalog = self._catalog
        host._epg_guide = self._guide
        host._diagnostics_bar.set_values(guide=host._epg_now_next())

    def _now_next(self, channel):
        if self._guide is None:
            return ""
        try:
            programmes = self._guide.for_channel(getattr(channel, "tvg_id", "") or channel.name)
        except Exception:  # noqa: BLE001
            return ""
        current = next((p for p in programmes if p.current), None) if programmes else None
        if current is not None:
            return f"{current.title}"
        return ""

    def _render(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if self._catalog is None:
            return
        for index, channel in enumerate(self._catalog.channels):
            card = QFrame()
            card.setObjectName("EpgChannel")
            card.setCursor(Qt.PointingHandCursor)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 10, 12, 10)
            name = QLabel(channel.name)
            name.setObjectName("NowPlayingTitle")
            name.setStyleSheet("font-size: 13px;")
            name.setWordWrap(True)
            cl.addWidget(name)
            now = self._now_next(channel)
            meta = QLabel(now or (getattr(channel, "group", "") or ""))
            meta.setObjectName("NowPlayingMeta")
            meta.setWordWrap(True)
            cl.addWidget(meta)
            card.mousePressEvent = lambda event, ch=channel: self.channelActivated.emit(ch)
            self._grid.addWidget(card, index // 3, index % 3)


class AboutPage(QFrame):
    """In-window about view (no popup)."""

    backRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setAlignment(Qt.AlignCenter)

        brand = QLabel("MPCASU")
        brand.setObjectName("BrandName")
        brand.setAlignment(Qt.AlignCenter)
        layout.addWidget(brand)
        sub = QLabel("PLAYER")
        sub.setObjectName("BrandSub")
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)
        layout.addSpacing(12)
        info = QLabel("Version 1.0.6\nMedia Player for CASU & Legacy Media\nIn-process playback · No external player")
        info.setObjectName("NowPlayingMeta")
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)
        layout.addSpacing(12)
        note = QLabel("Design inspired by VLC and Webamp — independent original code.\nAnti-Capitalist License 1.4 · Lino Casu")
        note.setObjectName("NowPlayingMeta")
        note.setAlignment(Qt.AlignCenter)
        note.setWordWrap(True)
        layout.addWidget(note)
class _ThreadBridge(QObject):
    """Marshals worker-thread results onto the Qt event loop (no popups)."""

    resultReady = Signal(object)
    errorReady = Signal(object)


class SourcesView(QFrame):
    """In-window view for YouTube/Spotify search and network stream URLs.

    Replaces modal dialogs: consent gate, search entry, yt-dlp result list
    and status line all live inside the main window.
    """

    MODES = {
        "youtube": {
            "title": "YOUTUBE",
            "hint": "YouTube URL or search term — e.g. https://www.youtube.com/watch?v=…",
            "search": True,
        },
        "spotify": {
            "title": "SPOTIFY",
            "hint": "Spotify URL — fetches the track title, then explicit “Find on YouTube” handoff",
            "search": True,
        },
        "url": {
            "title": "NETWORK STREAM",
            "hint": "HTTP(S), HLS, RTSP, RTP, UDP, FTP or SMB URL",
            "search": False,
        },
    }

    sourceActivated = Signal(object)
    consentAccepted = Signal()
    closeRequested = Signal()

    def __init__(self, settings_store, parent=None):
        super().__init__(parent)
        self.setObjectName("SourcesView")
        self._settings_store = settings_store
        self._mode = "youtube"
        self._results: list = []
        self._searching = False
        self._bridge = _ThreadBridge()
        self._bridge.resultReady.connect(self._present_results)
        self._bridge.errorReady.connect(self._present_error)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 16)
        layout.setSpacing(10)

        self._consent_frame = QFrame()
        self._consent_frame.setObjectName("Panel")
        cf_layout = QVBoxLayout(self._consent_frame)
        cf_layout.setContentsMargins(14, 12, 14, 12)
        cf_layout.setSpacing(8)
        notice = QLabel(
            "Legal notice — YouTube search/playback uses yt-dlp (GNU GPL); "
            "Spotify uses spotDL: Spotify metadata matched on YouTube "
            "(metadata → match → YouTube audio source).\n"
            "Stream URLs are resolved temporarily and never stored or "
            "redistributed. Personal use only.")
        notice.setObjectName("NowPlayingMeta")
        notice.setWordWrap(True)
        cf_layout.addWidget(notice)
        accept_btn = QPushButton("Accept and enable yt-dlp features")
        accept_btn.setObjectName("NavItem")
        accept_btn.setStyleSheet(
            f"background-color: {PALETTE.accent}; color: {PALETTE.text_on_accent}; font-weight: 600;")
        accept_btn.clicked.connect(self._accept_consent)
        cf_layout.addWidget(accept_btn, 0, Qt.AlignLeft)
        layout.addWidget(self._consent_frame)

        entry_row = QHBoxLayout()
        self._entry = QLineEdit()
        self._entry.setFixedHeight(34)
        self._entry.returnPressed.connect(self._open_typed)
        entry_row.addWidget(self._entry, 1)
        self._go_btn = QPushButton("Play / search")
        self._go_btn.setObjectName("NavItem")
        self._go_btn.setStyleSheet(
            f"background-color: {PALETTE.accent}; color: {PALETTE.text_on_accent}; font-weight: 600;")
        self._go_btn.clicked.connect(self._open_typed)
        entry_row.addWidget(self._go_btn)
        layout.addLayout(entry_row)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(
            lambda item: self._play_row(self._list.row(item)))
        layout.addWidget(self._list, 1)

        self._status = QLabel("Search uses yt-dlp (GNU GPL) · personal use only")
        self._status.setObjectName("NowPlayingMeta")
        self._status.setStyleSheet(f"color: {PALETTE.text_faint};")
        layout.addWidget(self._status)

    def set_mode(self, mode: str):
        if mode not in self.MODES:
            mode = "youtube"
        self._mode = mode
        spec = self.MODES[mode]
        self._entry.setPlaceholderText(spec["hint"])
        self._entry.clear()
        self._list.clear()
        self._results = []
        self._searching = False
        self._go_btn.setText("Play / search" if spec["search"] else "Play")
        self._consent_frame.setVisible(not self._consent_given())
        self._status.setText(
            "Search uses yt-dlp (GNU GPL) · personal use only" if spec["search"]
            else "Opens directly in the internal libVLC backend — no external player")
        self._entry.setFocus()

    def _consent_given(self) -> bool:
        try:
            return bool(self._settings_store.load().ytdlp_consent)
        except (OSError, ValueError, TypeError):
            return False

    def _accept_consent(self):
        try:
            settings = self._settings_store.load()
            self._settings_store.save(replace(settings, ytdlp_consent=True))
        except (OSError, ValueError, TypeError):
            pass
        self._consent_frame.setVisible(False)
        self.consentAccepted.emit()

    def _open_typed(self):
        text = self._entry.text().strip()
        if not text:
            return
        if self._mode == "spotify":
            kind = spotify_kind(text)
            if kind:
                if kind == "track":
                    self._fetch_spotify_handoff(text)
                else:
                    self._expand_spotify_url(text)
                return
        if is_youtube_url(text) and "list=" in text:
            self._expand_youtube_playlist(text)
            return
        is_url = text.startswith(("http://", "https://", "rtsp://", "rtmp://",
                                  "udp://", "rtp://", "ftp://", "smb://"))
        if not is_url and self.MODES[self._mode]["search"]:
            if not self._consent_given():
                self._status.setText("Accept the yt-dlp legal notice above to enable search")
                return
            self._run_search(text)
            return
        self.sourceActivated.emit(text)

    def _expand_spotify_url(self, url: str):
        if self._searching:
            return
        self._searching = True
        self._list.clear()
        self._results = []
        self._status.setText("Expanding Spotify playlist via spotDL…")

        def worker():
            from casu.search import SearchResult
            try:
                found = [SearchResult(
                    title=r.title, url=r.url, duration=r.duration,
                    uploader=r.artist or "Spotify", source="spotify")
                    for r in expand_spotify(url)]
            except SpotifyError as exc:
                self._bridge.errorReady.emit(str(exc))
            else:
                self._bridge.resultReady.emit(found)
        threading.Thread(target=worker, daemon=True).start()

    def _expand_youtube_playlist(self, url: str):
        if self._searching:
            return
        self._searching = True
        self._list.clear()
        self._results = []
        self._status.setText("Expanding YouTube playlist…")

        def worker():
            from casu.search import SearchError, search_youtube_playlist
            try:
                found = search_youtube_playlist(url)
            except SearchError as exc:
                self._bridge.errorReady.emit(str(exc))
            else:
                self._bridge.resultReady.emit(found)
        threading.Thread(target=worker, daemon=True).start()

    def _fetch_spotify_handoff(self, url: str):
        if self._searching:
            return
        self._searching = True
        self._list.clear()
        self._results = []
        self._status.setText("Resolving Spotify via spotDL…")

        def worker():
            from casu.search import SearchResult
            try:
                resolved = resolve_spotify_url(url)
            except SpotifyError:
                resolved = None
            if resolved:
                self._bridge.resultReady.emit([SearchResult(
                    title="Spotify track · matched on YouTube by spotDL",
                    url=resolved, duration=None,
                    uploader="SPOTIFY via spotDL", source="spotify")])
                return
            try:
                meta = fetch_spotify_metadata(url)
            except SpotifyError as exc:
                self._bridge.errorReady.emit(str(exc))
            else:
                self._bridge.resultReady.emit([SearchResult(
                    title=youtube_handoff_query(meta),
                    url="handoff:youtube",
                    duration=None,
                    uploader=f"Spotify {meta.kind} · original title",
                    source="handoff")])
        threading.Thread(target=worker, daemon=True).start()

    def _run_search(self, query: str):
        if self._searching:
            return
        self._searching = True
        self._list.clear()
        self._results = []
        preset = "YouTube music preset" if self._mode == "spotify" else "YouTube"
        self._status.setText(f"Searching {preset} via yt-dlp…")
        mode = self._mode

        def worker():
            try:
                from casu.search import SearchResult, search_youtube
                if mode == "spotify":
                    found = [SearchResult(title=r.title, url=r.url,
                                          duration=r.duration,
                                          uploader=r.artist or "Spotify",
                                          source="spotify")
                             for r in search_spotify(query, limit=12)]
                else:
                    found = search_youtube(query, limit=12)
            except Exception as exc:  # noqa: BLE001 - surface any engine failure
                self._bridge.errorReady.emit(str(exc))
            else:
                self._bridge.resultReady.emit(found)
        threading.Thread(target=worker, daemon=True).start()

    def _present_results(self, found):
        self._searching = False
        self._results = list(found)
        self._list.clear()
        for item in self._results:
            duration = (f"{int(item.duration // 60)}:{int(item.duration % 60):02d}"
                        if item.duration else "live")
            tag = "FIND ON YOUTUBE" if item.source == "handoff" else item.source.upper()
            self._list.addItem(
                f"[{tag}] {item.title}  ·  {item.uploader or 'unknown'}  ·  {duration}")
        self._status.setText(f"{len(self._results)} results — double-click or press Enter to play")

    def _present_error(self, detail):
        self._searching = False
        self._status.setText(f"Search failed: {detail}")

    def _play_row(self, row: int):
        if 0 <= row < len(self._results):
            item = self._results[row]
            if item.source == "handoff":
                if not self._consent_given():
                    self._status.setText("Accept the yt-dlp legal notice above to enable the YouTube handoff")
                    return
                self._status.setText(f"Handoff to YouTube provider: {item.title}")
                self._run_search(item.title)
                return
            self.sourceActivated.emit(item)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return and self._list.hasFocus():
            self._play_row(self._list.currentRow())
            return
        if event.key() == Qt.Key_Escape:
            self.closeRequested.emit()
            return
        super().keyPressEvent(event)


class MainWindow(QMainWindow):
    """MPCASU Qt main window — full media player."""

    def __init__(self, initial: list[Path] | None = None):
        super().__init__()
        self.setWindowTitle("MPCASU Media Player")
        avail = QGuiApplication.primaryScreen().availableGeometry()
        self.setMinimumSize(min(980, avail.width()), min(620, avail.height()))
        self.resize(min(1360, avail.width() - 24), min(820, avail.height() - 24))
        self.move(avail.x() + max(0, (avail.width() - self.width()) // 2),
                  avail.y() + max(0, (avail.height() - self.height()) // 2))
        self.setAcceptDrops(True)
        self.setStyleSheet(stylesheet())

        self.backend: LibVLCBackend | NativeCasuBackend | None = None
        self._native_sink: QtVideoSurfaceSink | None = None
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
        self._shuffle = False
        self._repeat_mode = "off"
        self._recorder = None
        self._recording_finishing = False
        self._ab_a: float | None = None
        self._ab_b: float | None = None
        self._network_source: str | None = None
        self._epg_catalog = None
        self._epg_guide = None
        self._sidebar_rail = False
        self._playlist_auto_hidden = False
        self._queue_drawer = False
        self._audio_stage = False
        self._viz_pcm = None
        self._viz_rate = 0
        self._viz_generation = 0
        self._viz_timer = QTimer(self)
        self._viz_timer.setInterval(50)  # 20 FPS
        self._viz_timer.timeout.connect(self._tick_visualizer)

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

        self._resolve_generation = 0
        self._resolve_bridge = _ThreadBridge()
        self._resolve_bridge.resultReady.connect(self._on_resolve_ready)
        self._resolve_bridge.errorReady.connect(self._on_resolve_failed)

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
        self._now_playing_bar.hide()

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self._body_layout = body

        self._sidebar = Sidebar()
        self._sidebar.navRequested.connect(self._navigate)
        body.addWidget(self._sidebar)

        player_page = QWidget()
        center_column = QVBoxLayout(player_page)
        center_column.setContentsMargins(0, 0, 0, 0)
        center_column.setSpacing(0)

        topbar = QFrame()
        topbar.setObjectName("TopBar")
        topbar.setFixedHeight(METRICS.topbar_height)
        tb_layout = QHBoxLayout(topbar)
        tb_layout.setContentsMargins(10, 0, 10, 0)
        self._back_btn = QPushButton("‹")
        self._back_btn.setObjectName("IconButton")
        self._back_btn.setFixedSize(40, 40)
        self._back_btn.setToolTip("Back to Now Playing")
        self._back_btn.clicked.connect(self._show_player_page)
        tb_layout.addWidget(self._back_btn)
        self._topbar_title = QLabel("NOW PLAYING")
        self._topbar_title.setObjectName("NowPlayingTitle")
        tb_layout.addWidget(self._topbar_title)
        tb_layout.addStretch()
        self._queue_filter = QLineEdit()
        self._queue_filter.setPlaceholderText("Search queue…")
        self._queue_filter.setFixedWidth(220)
        self._queue_filter.setFixedHeight(34)
        self._queue_filter.textChanged.connect(self._filter_queue)
        tb_layout.addWidget(self._queue_filter)
        self._nav_toggle = QPushButton("☰")
        self._nav_toggle.setObjectName("IconButton")
        self._nav_toggle.setFixedSize(40, 40)
        self._nav_toggle.setToolTip("Toggle navigation")
        self._nav_toggle.clicked.connect(
            lambda: self._sidebar.setVisible(not self._sidebar.isVisible()))
        tb_layout.addWidget(self._nav_toggle)
        self._queue_toggle = QPushButton("☷")
        self._queue_toggle.setObjectName("IconButton")
        self._queue_toggle.setFixedSize(40, 40)
        self._queue_toggle.setToolTip("Toggle playlist panel")
        self._queue_toggle.clicked.connect(self._toggle_queue_pane)
        tb_layout.addWidget(self._queue_toggle)
        self._topbar = topbar
        center_column.addWidget(topbar)

        self._video_surface = VideoSurface()
        self._video_surface.doubleClicked.connect(self.toggle_fullscreen)
        center_column.addWidget(self._video_surface, 1)

        self._badges_label = QLabel(self._video_surface)
        self._badges_label.setStyleSheet(
            "background-color: #090b0ddd; border: 1px solid #383d43; color: #f4f5f7;"
            " font-size: 11px; font-weight: 800; padding: 5px 8px;")
        self._badges_label.hide()
        self._caption_label = QLabel(self._video_surface)
        self._caption_label.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 transparent,"
            " stop:1 #050607e8); color: #f4f5f7; font-size: 14px; font-weight: 700;"
            " padding: 40px 18px 12px 18px; border: none;")
        self._caption_label.hide()
        self._empty_hint = QFrame(self._video_surface)
        self._empty_hint.setStyleSheet(
            "background: qradialgradient(cx:0.5, cy:0.5, radius:0.9, "
            "stop:0 #291014, stop:1 #0b0d10); border: none;")
        eh_layout = QVBoxLayout(self._empty_hint)
        eh_layout.setContentsMargins(24, 24, 24, 24)
        eh_layout.setSpacing(6)
        eh_layout.addStretch()
        icon_label = QLabel()
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "web_casu_icon.png"
        if icon_path.is_file():
            pix = QPixmap(str(icon_path))
            if not pix.isNull():
                icon_label.setPixmap(pix.scaledToWidth(72, Qt.SmoothTransformation))
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("background: transparent;")
        eh_layout.addWidget(icon_label)
        eh_title = QLabel("Drop media here")
        eh_title.setObjectName("NowPlayingTitle")
        eh_title.setStyleSheet("background: transparent; font-size: 18px;")
        eh_title.setAlignment(Qt.AlignCenter)
        eh_layout.addWidget(eh_title)
        eh_meta = QLabel("Audio, video, CASU, playlists and streams — "
                         "“Choose files” in the playlist panel, or drag & drop")
        eh_meta.setObjectName("NowPlayingMeta")
        eh_meta.setStyleSheet("background: transparent;")
        eh_meta.setAlignment(Qt.AlignCenter)
        eh_meta.setWordWrap(True)
        eh_layout.addWidget(eh_meta)
        eh_layout.addStretch()

        self._visualizer = VisualizerWidget(self._video_surface)
        self._viz_bridge = _ThreadBridge()
        self._viz_bridge.resultReady.connect(self._apply_viz)

        self._toast_label = QLabel(self._video_surface)
        self._toast_label.setObjectName("Toast")
        self._toast_label.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast_label.hide)

        self._drop_overlay = QLabel("DROP TO PLAY / ADD TO QUEUE", self._video_surface)
        self._drop_overlay.setAlignment(Qt.AlignCenter)
        self._drop_overlay.setStyleSheet(
            "background: #07090bcc; border: 2px solid #ff1e2d; border-radius: 10px;"
            " color: #ff1e2d; font-size: 16px; font-weight: 800;")
        self._drop_overlay.hide()

        self._fs_overlay = QFrame(self._video_surface)
        self._fs_overlay.setStyleSheet(
            "background: #07090bdd; border: 1px solid #252a30; border-radius: 8px;")
        fsl = QHBoxLayout(self._fs_overlay)
        fsl.setContentsMargins(10, 6, 10, 6)
        fsl.setSpacing(6)
        self._fs_play_btn = QPushButton("▶")
        self._fs_play_btn.setObjectName("TransportButton")
        self._fs_play_btn.clicked.connect(self.toggle_playback)
        fsl.addWidget(self._fs_play_btn)
        self._fs_time = QLabel("00:00 / 00:00")
        self._fs_time.setObjectName("TimeLabel")
        fsl.addWidget(self._fs_time)
        fsl.addStretch()
        self._fs_vol = QSlider(Qt.Horizontal)
        self._fs_vol.setObjectName("VolumeSlider")
        self._fs_vol.setRange(0, 200)
        self._fs_vol.setValue(self._volume)
        self._fs_vol.setFixedWidth(90)
        self._fs_vol.valueChanged.connect(self._on_volume_slider)
        fsl.addWidget(self._fs_vol)
        self._fs_exit_btn = QPushButton("□")
        self._fs_exit_btn.setObjectName("IconButton")
        self._fs_exit_btn.clicked.connect(self.toggle_fullscreen)
        fsl.addWidget(self._fs_exit_btn)
        self._fs_overlay.hide()
        self._fs_hide_timer = QTimer(self)
        self._fs_hide_timer.setSingleShot(True)
        self._fs_hide_timer.setInterval(2500)
        self._fs_hide_timer.timeout.connect(self._fs_overlay.hide)

        transport_container = QFrame()
        self._transport_container = transport_container
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
        controls.setSpacing(6)

        self._prev_btn = QPushButton("«")
        self._prev_btn.setObjectName("TransportButton")
        self._prev_btn.clicked.connect(self.play_previous)
        self._prev_btn.setToolTip("Previous track")
        controls.addWidget(self._prev_btn)

        self._play_btn = QPushButton("▶")
        self._play_btn.setObjectName("PlayButton")
        self._play_btn.setFixedSize(METRICS.play_button, METRICS.play_button)
        self._play_btn.clicked.connect(self.toggle_playback)
        self._play_btn.setToolTip("Play / Pause")
        controls.addWidget(self._play_btn)

        self._next_btn = QPushButton("»")
        self._next_btn.setObjectName("TransportButton")
        self._next_btn.clicked.connect(self.play_next)
        self._next_btn.setToolTip("Next track")
        controls.addWidget(self._next_btn)

        self._shuffle_btn = QPushButton("⤨")
        self._shuffle_btn.setObjectName("TransportButton")
        self._shuffle_btn.setCheckable(True)
        self._shuffle_btn.setChecked(self._shuffle)
        self._shuffle_btn.toggled.connect(self._toggle_shuffle)
        self._shuffle_btn.setToolTip("Shuffle")
        controls.addWidget(self._shuffle_btn)

        self._repeat_btn = QPushButton("↻")
        self._repeat_btn.setObjectName("TransportButton")
        self._repeat_btn.clicked.connect(self._cycle_repeat)
        self._repeat_btn.setToolTip("Repeat off / all / one")
        controls.addWidget(self._repeat_btn)

        self._ab_btn = QPushButton("A–B")
        self._ab_btn.setObjectName("IconButton")
        self._ab_btn.clicked.connect(self.cycle_ab_loop)
        self._ab_btn.setToolTip("A/B loop")
        controls.addWidget(self._ab_btn)

        self._snapshot_btn = QPushButton("▧")
        self._snapshot_btn.setObjectName("IconButton")
        self._snapshot_btn.clicked.connect(self.save_snapshot)
        self._snapshot_btn.setToolTip("Save current video frame")
        controls.addWidget(self._snapshot_btn)

        self._rate_btn = QPushButton(f"{self._rate:g}×")
        self._rate_btn.setObjectName("IconButton")
        self._rate_btn.clicked.connect(self.cycle_rate)
        self._rate_btn.setToolTip("Playback speed")
        controls.addWidget(self._rate_btn)

        self._viz_btn = QPushButton("〰")
        self._viz_btn.setObjectName("IconButton")
        self._viz_btn.clicked.connect(self.toggle_visualizer)
        self._viz_btn.setToolTip("Visualizer on/off")
        controls.addWidget(self._viz_btn)

        controls.addStretch()

        volume_layout = QHBoxLayout()
        volume_layout.setSpacing(4)
        self._mute_btn = QPushButton("♪")
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

        self._fullscreen_btn = QPushButton("□")
        self._fullscreen_btn.setObjectName("IconButton")
        self._fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        self._fullscreen_btn.setToolTip("Fullscreen (F)")
        controls.addWidget(self._fullscreen_btn)

        self._more_btn = QPushButton("⋯")
        self._more_btn.setObjectName("IconButton")
        self._more_btn.setCheckable(True)
        self._more_btn.setToolTip("More controls")
        controls.addWidget(self._more_btn)

        tc_layout.addLayout(controls)

        self._more_panel = QFrame()
        self._more_panel.setObjectName("Panel")
        secondary = QHBoxLayout(self._more_panel)
        secondary.setSpacing(3)

        self._stop_btn = QPushButton("■")
        self._stop_btn.setObjectName("TransportButton")
        self._stop_btn.clicked.connect(self.stop)
        self._stop_btn.setToolTip("Stop")
        secondary.addWidget(self._stop_btn)

        self._seek_back_btn = QPushButton("‹")
        self._seek_back_btn.setObjectName("TransportButton")
        self._seek_back_btn.clicked.connect(lambda: self.seek_by(-10))
        self._seek_back_btn.setToolTip("Rewind 10s")
        secondary.addWidget(self._seek_back_btn)

        self._seek_fwd_btn = QPushButton("›")
        self._seek_fwd_btn.setObjectName("TransportButton")
        self._seek_fwd_btn.clicked.connect(lambda: self.seek_by(10))
        self._seek_fwd_btn.setToolTip("Forward 10s")
        secondary.addWidget(self._seek_fwd_btn)

        self._record_btn = QPushButton("●")
        self._record_btn.setObjectName("IconButton")
        self._record_btn.clicked.connect(self.toggle_recording)
        self._record_btn.setToolTip("Record stream / source")
        secondary.addWidget(self._record_btn)

        self._audio_track_menu = QPushButton("Audio")
        self._audio_track_menu.setObjectName("IconButton")
        self._audio_track_menu.setMenu(QMenu(self))
        self._audio_track_menu.menu().aboutToShow.connect(lambda: self._refresh_track_menu(TrackKind.AUDIO))
        self._audio_track_menu.setToolTip("Audio track")
        secondary.addWidget(self._audio_track_menu)

        self._video_track_menu = QPushButton("Video")
        self._video_track_menu.setObjectName("IconButton")
        self._video_track_menu.setMenu(QMenu(self))
        self._video_track_menu.menu().aboutToShow.connect(lambda: self._refresh_track_menu(TrackKind.VIDEO))
        self._video_track_menu.setToolTip("Video track")
        secondary.addWidget(self._video_track_menu)

        self._subtitle_track_menu = QPushButton("Subtitles")
        self._subtitle_track_menu.setObjectName("IconButton")
        self._subtitle_track_menu.setMenu(QMenu(self))
        self._subtitle_track_menu.menu().aboutToShow.connect(lambda: self._refresh_track_menu(TrackKind.SUBTITLE))
        self._subtitle_track_menu.setToolTip("Subtitle track")
        secondary.addWidget(self._subtitle_track_menu)

        self._audio_device_menu = QPushButton("Output")
        self._audio_device_menu.setObjectName("IconButton")
        self._audio_device_menu.setMenu(QMenu(self))
        self._audio_device_menu.menu().aboutToShow.connect(self._refresh_audio_devices)
        self._audio_device_menu.setToolTip("Audio output device")
        secondary.addWidget(self._audio_device_menu)

        self._chapter_menu = QPushButton("Chapters")
        self._chapter_menu.setObjectName("IconButton")
        self._chapter_menu.setMenu(QMenu(self))
        self._chapter_menu.menu().aboutToShow.connect(self._refresh_chapters)
        self._chapter_menu.setToolTip("Chapters")
        secondary.addWidget(self._chapter_menu)

        sync_menu_btn = QPushButton("Sync")
        sync_menu_btn.setObjectName("IconButton")
        sync_menu = QMenu(self)
        sync_menu.addAction("Audio delay…", self.set_audio_delay_dialog)
        sync_menu.addAction("Subtitle delay…", self.set_subtitle_delay_dialog)
        sync_menu_btn.setMenu(sync_menu)
        sync_menu_btn.setToolTip("Audio / subtitle sync")
        secondary.addWidget(sync_menu_btn)

        load_sub_btn = QPushButton("Load subtitle")
        load_sub_btn.setObjectName("IconButton")
        load_sub_btn.clicked.connect(self.load_external_subtitle)
        secondary.addWidget(load_sub_btn)

        frame_btn = QPushButton("Frame")
        frame_btn.setObjectName("IconButton")
        frame_btn.clicked.connect(self.next_frame)
        secondary.addWidget(frame_btn)

        info_btn = QPushButton("Info")
        info_btn.setObjectName("IconButton")
        info_btn.clicked.connect(self.show_media_info)
        secondary.addWidget(info_btn)

        self._more_panel.hide()
        self._more_btn.toggled.connect(self._more_panel.setVisible)
        tc_layout.addWidget(self._more_panel)

        center_column.addWidget(transport_container)

        self._diagnostics_bar = DiagnosticsBar()
        center_column.addWidget(self._diagnostics_bar)

        self._sources_view = SourcesView(self.settings_store)
        self._sources_view.sourceActivated.connect(self._on_source_activated)
        self._sources_view.closeRequested.connect(self._show_player_page)
        self._sources_view.consentAccepted.connect(
            lambda: self.status("yt-dlp consent saved — YouTube/Spotify enabled"))

        self._center_stack = QStackedWidget()
        self._center_stack.addWidget(player_page)
        self._center_stack.addWidget(self._sources_view)
        self._pages: list = []
        self._library_page = LibraryPage(self.media_library, self._thumbnail_dir, self)
        self._library_page.addRequested.connect(lambda paths: self.add_files(paths))
        self._library_page.refreshRequested.connect(self.refresh_watched_folders)
        self._library_page.backRequested.connect(self._show_player_page)
        self._options_page = OptionsPage(self.settings_store, self)
        self._options_page.applied.connect(self._apply_settings)
        self._options_page.actionRequested.connect(self._options_action)
        self._options_page.backRequested.connect(self._show_player_page)
        self._epg_page = EpgPage(self)
        self._epg_page.channelActivated.connect(self._on_epg_channel)
        self._epg_page.backRequested.connect(self._show_player_page)
        self._about_page = AboutPage(self)
        self._about_page.backRequested.connect(self._show_player_page)
        body.addWidget(self._center_stack, 1)

        self._playlist_pane = PlaylistPane()
        self._playlist_pane.addRequested.connect(self.add_dialog)
        self._playlist_pane.urlRequested.connect(lambda: self.show_sources("url"))
        self._playlist_pane.renameRequested.connect(self._rename_queue_row)
        self._playlist_pane.playRequested.connect(self._play_playlist_row)
        self._playlist_pane.removeRequested.connect(self._on_playlist_remove)
        self._playlist_pane.moveRequested.connect(self._on_playlist_move)
        self._playlist_pane.orderChanged.connect(self._apply_queue_order)
        self._playlist_pane.childPlayRequested.connect(self._on_queue_child_play)
        self._playlist_pane.saveRequested.connect(self.save_playlist)
        self._playlist_pane.loadRequested.connect(self.load_playlist)
        self._random = random.SystemRandom()
        self._playlist_pane.shuffle_btn.toggled.connect(self._toggle_shuffle)
        self._playlist_pane.repeat_btn.clicked.connect(self._cycle_repeat)
        body.addWidget(self._playlist_pane)

        main_layout.addLayout(body)

        status_bar = QStatusBar()
        status_bar.setObjectName("StatusBar")
        self._status_left = QLabel("MPCASU 1.0.6")
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
        if name == "NOW PLAYING":
            self._show_player_page()
            self._sidebar.set_active("NOW PLAYING")
            return
        if name == "LOCAL FILES":
            self._library_page._refresh()
            self._show_page(self._library_page, "LOCAL FILES")
            self._sidebar.set_active("LOCAL FILES")
            return
        if name == "WEB & STREAMS":
            self.show_sources("url")
            return
        if name == "PLAYLISTS":
            self._show_player_page()
            self._playlist_pane.setVisible(True)
            self._playlist_pane.set_view("playlists")
            self._sidebar.set_active("PLAYLISTS")
            return
        if name == "IPTV / EPG":
            self._show_page(self._epg_page, "IPTV / EPG")
            self._sidebar.set_active("IPTV / EPG")
            return
        if name == "YOUTUBE":
            self.show_sources("youtube")
            return
        if name == "SPOTIFY":
            self.show_sources("spotify")
            return
        if name == "CASU FILES":
            self._show_player_page()
            self._playlist_pane.setVisible(True)
            self._playlist_pane.set_view("casu")
            self._sidebar.set_active("CASU FILES")
            return
        if name == "OPTIONS":
            self._options_page.reload()
            self._show_page(self._options_page, "OPTIONS")
            self._sidebar.set_active("OPTIONS")
            return
        if name == "ABOUT":
            self._show_page(self._about_page, "ABOUT")
            self._sidebar.set_active("ABOUT")
            return
        self._show_player_page()

    def status(self, text: str):
        if hasattr(self, "_status_center"):
            self._status_center.setText(str(text))
        if hasattr(self, "_status_label"):
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
                self._play_btn.setText("| |")

    def stop(self):
        self._stop_stream_viz()
        self._viz_timer.stop()
        self._viz_pcm = None
        self._viz_rate = 0
        self._viz_generation += 1
        self._audio_stage = False
        self._reposition_overlays()
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
            segmented="unavailable",
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
        self._mute_btn.setText("×" if self._muted else "♪")

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
        self._stop_stream_viz()
        self._end_handled = False
        self.current = path
        self._network_source = None
        self._now_playing_bar.set_now_playing(path.name)
        self._set_caption(path.name, path)
        selected_index = self.playlist_model.index_of(path)
        if selected_index is not None:
            self._playlist_pane.populate(list(self.playlist_model.items), selected_index)

        sidecar = path if path.suffix.lower() == ".casu" else path.with_suffix(path.suffix + ".casu")
        self._load_visual_state(sidecar if sidecar.exists() else path)
        self._audio_stage = path.suffix.lower() in AUDIO_EXTENSIONS
        self._load_visualizer(path)
        self._probe_stage(path)

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
                         "CASUNAT1 container + libVLC"),
                integrity="verified source manifest" if not self._visual_state.startswith("invalid") else "failed manifest validation",
                segmented=f"{len(self._visual_segments)} segments" if self._visual_segments else "no segment data",
            )
        elif path.suffix.lower() == ".mp5":
            self._diagnostics_bar.set_values(
                support="MP5 enhanced container + libVLC",
                integrity="SHA-256 verified attachment",
                segmented=f"{len(self._visual_segments)} segments" if self._visual_segments else "no segment data",
            )
        elif sidecar.exists():
            self._diagnostics_bar.set_values(
                support="CASUNAT1 + CASUNAT2",
                integrity="CASUNAT1 envelope verified on load",
                segmented=f"{len(self._visual_segments)} segments" if self._visual_segments else "no segment data",
            )
        else:
            self._diagnostics_bar.set_values(
                support="Legacy backend", integrity="unavailable", segmented="unavailable",
            )
        self._diagnostics_bar.set_values(guide=self._epg_now_next())

        try:
            source = self._source_for(path)
        except CasuError as exc:
            self.toast(f"{path.name}: {exc} — if this is an old or invalid .casu file, "
                       "re-convert it with the converter (CASUNAT2 recommended)")
            self.status("Cannot play — the CASU manifest failed validation")
            return

        state = ("CASU manifest selected" if path.suffix.lower() == ".casu"
                 else ("MP5 container selected" if path.suffix.lower() == ".mp5"
                       else ("CASU envelope found" if sidecar.exists() else "legacy media — no CASU envelope")))
        self.status(f"{path.name} · {state}")

        is_casu_container = path.suffix.lower() in {".casu", ".mp5"}
        try:
            if path.suffix.lower() == ".casu" and NativeCasuBackend.supports(path):
                audio_sink = None
                if PulseAudioSink.probe():
                    try:
                        audio_sink = PulseAudioSink()
                    except BackendError:
                        audio_sink = None
                self._native_sink = QtVideoSurfaceSink(self._video_surface)
                self.backend = NativeCasuBackend(self._native_sink, audio_sink)
            else:
                self.backend = (CasuBackend(self._video_surface.handle)
                                if is_casu_container
                                else LibVLCBackend(self._video_surface.handle))
            self.backend.on_event = self._backend_event
            if is_casu_container:
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
            self._video_surface.set_video_active(not self._audio_stage)
            if isinstance(self.backend, LibVLCBackend):
                QTimer.singleShot(500, self._apply_media_preferences)
                QTimer.singleShot(1500, self._check_playback_start)
        except (BackendError, CasuError, OSError) as exc:
            self.controller.close()
            self.backend = None
            self.status(f"Cannot play — {exc}")
            self.toast(f"{path.name}: {exc}")
            self.toast(f"Could not start internal playback: {exc}")
            return
        self._paused = False
        self._play_btn.setText("| |")

    def _toggle_shuffle(self, checked: bool) -> None:
        self._shuffle = checked
        self._playlist_pane.shuffle_btn.setText("Shuffle on" if checked else "Shuffle off")
        if hasattr(self, "_shuffle_btn"):
            self._shuffle_btn.setProperty("on", "true" if checked else "false")
            self._shuffle_btn.style().unpolish(self._shuffle_btn)
            self._shuffle_btn.style().polish(self._shuffle_btn)
            self._shuffle_btn.setChecked(checked)
        self.status(f"Shuffle {'on' if checked else 'off'}")

    def _cycle_repeat(self) -> None:
        values = ("off", "all", "one")
        self._repeat_mode = values[(values.index(self._repeat_mode) + 1) % len(values)]
        self._playlist_pane.repeat_btn.setText(f"Repeat {self._repeat_mode}")
        if hasattr(self, "_repeat_btn"):
            self._repeat_btn.setText("↻" if self._repeat_mode == "off" else
                                     ("↻1" if self._repeat_mode == "one" else "↻∞"))
            self._repeat_btn.setProperty("on", "true" if self._repeat_mode != "off" else "false")
            self._repeat_btn.style().unpolish(self._repeat_btn)
            self._repeat_btn.style().polish(self._repeat_btn)
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
        self._playlist_pane.select_row(target)
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
        self._playlist_pane.select_row(target)
        self.play_selected()

    def _selected_playlist_row(self) -> int:
        return self._playlist_pane.selected_row()

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
        if self.isFullScreen():
            self.showNormal()
            if getattr(self, "_saved_geometry", None):
                self.setGeometry(self._saved_geometry)
            self._exit_fs_ui()
        else:
            self._saved_geometry = self.geometry()
            self._enter_fs_ui()
            self.showFullScreen()
        self._fullscreen = self.isFullScreen()

    def _enter_fs_ui(self):
        self._fs_saved = {
            "sidebar": self._sidebar.isVisible(),
            "playlist": self._playlist_pane.isVisible(),
            "topbar": self._topbar.isVisible(),
            "transport": self._transport_container.isVisible(),
            "diag": self._diagnostics_bar.isVisible(),
        }
        self._sidebar.hide()
        self._playlist_pane.hide()
        self._topbar.hide()
        self._transport_container.hide()
        self._diagnostics_bar.hide()
        self.statusBar().hide()
        self._fs_overlay.show()
        self._fs_hide_timer.start()

    def _exit_fs_ui(self):
        self._fs_hide_timer.stop()
        self._fs_overlay.hide()
        saved = getattr(self, "_fs_saved", None) or {}
        self._sidebar.setVisible(saved.get("sidebar", True))
        self._playlist_pane.setVisible(saved.get("playlist", True))
        self._topbar.setVisible(saved.get("topbar", True))
        self._transport_container.setVisible(saved.get("transport", True))
        self._diagnostics_bar.setVisible(saved.get("diag", True))
        self.statusBar().show()

    def _exit_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        self._exit_fs_ui()
        self._fullscreen = False

    def mouseMoveEvent(self, event):
        if self.isFullScreen():
            self._fs_overlay.show()
            self._fs_hide_timer.start()
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self._center_stack.currentWidget() is not None and \
                    self._center_stack.currentIndex() != 0:
                self._show_player_page()
                return
            if self.isFullScreen():
                self.toggle_fullscreen()
                return
        super().keyPressEvent(event)

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

    def open_url_dialog(self):
        self.show_sources("url")

    def show_sources(self, mode: str):
        """Switch the center area to the in-window sources view (no popup)."""
        self._sources_view.set_mode(mode)
        self._center_stack.setCurrentWidget(self._sources_view)
        self._topbar_title.setText(self._sources_view.MODES[mode]["title"])
        self._back_btn.show()

    def _show_player_page(self):
        self._center_stack.setCurrentIndex(0)
        self._topbar_title.setText("NOW PLAYING")
        self._back_btn.hide()
        if self._queue_drawer:
            self._close_queue_drawer()

    def _toggle_queue_pane(self):
        if self.width() < 1100:
            if self._queue_drawer:
                self._close_queue_drawer()
            else:
                self._open_queue_drawer()
            return
        if self._queue_drawer:
            self._close_queue_drawer()
        else:
            self._playlist_pane.setVisible(not self._playlist_pane.isVisible())

    def _open_queue_drawer(self):
        pane = self._playlist_pane
        if pane.parent() is self.centralWidget():
            self._body_layout.removeWidget(pane)
        pane.setParent(self.centralWidget())
        width = min(320, int(self.width() * 0.88))
        pane.setFixedWidth(width)
        pane.setGeometry(self.width() - width, 0, width, self.height())
        pane.raise_()
        pane.show()
        self._queue_drawer = True

    def _close_queue_drawer(self):
        pane = self._playlist_pane
        pane.hide()
        if pane.parent() is self.centralWidget():
            self._body_layout.addWidget(pane)
        pane.setFixedWidth(METRICS.playlist_width)
        self._queue_drawer = False
        self._body_layout.invalidate()

    def _position_queue_drawer(self):
        if not self._queue_drawer:
            return
        pane = self._playlist_pane
        width = pane.width()
        pane.setGeometry(self.width() - width, 0, width, self.height())
        pane.raise_()

    def toast(self, text: str):
        """Web-player style transient toast over the stage (no popup)."""
        self._toast_label.setText(str(text))
        self._toast_label.adjustSize()
        stage = self._video_surface
        width = min(self._toast_label.width(), max(240, stage.width() - 32))
        self._toast_label.setFixedWidth(width)
        self._toast_label.setWordWrap(True)
        self._toast_label.adjustSize()
        x = max(16, (stage.width() - self._toast_label.width()) // 2)
        y = max(8, stage.height() - self._toast_label.height() - 18)
        self._toast_label.move(x, y)
        self._toast_label.raise_()
        self._toast_label.show()
        self._toast_timer.start(2600)

    def _set_caption(self, text: str, path=None):
        if not text:
            self._caption_label.hide()
            self._badges_label.hide()
            self._empty_hint.show()
            return
        self._empty_hint.hide()
        display = ""
        if str(text).startswith(("http://", "https://", "rtsp://", "rtmp://")):
            display = self._playlist_pane.name_for(str(text))
        self._caption_label.setText(display or str(text))
        self._caption_label.show()
        badge = ""
        if path is not None:
            suffix = Path(str(path)).suffix.lower()
            badge = {"casu": "CASU", "mp5": "MP5", "mp3": "MP3", "mp4": "MP4"}.get(
                suffix.lstrip("."), suffix.lstrip(".").upper() or "MEDIA")
        else:
            badge = "STREAM"
        self._badges_label.setText(badge)
        self._badges_label.show()
        self._reposition_overlays()

    def _reposition_overlays(self):
        stage = self._video_surface
        self._badges_label.move(16, 16)
        self._caption_label.setGeometry(0, max(0, stage.height() - 72),
                                         stage.width(), 72)
        ew = min(480, max(200, stage.width() - 60))
        eh = min(300, max(140, stage.height() - 60))
        self._empty_hint.setGeometry((stage.width() - ew) // 2,
                                     (stage.height() - eh) // 2, ew, eh)
        if self._audio_stage:
            self._visualizer.setGeometry(0, 0, stage.width(), stage.height())
        else:
            self._visualizer.setGeometry(12, max(0, stage.height() - 108),
                                         max(0, stage.width() - 24), 96)
        self._visualizer.raise_()
        self._caption_label.raise_()
        self._badges_label.raise_()
        self._empty_hint.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = self.width()
        if width < 1200 and not self._sidebar_rail:
            self._sidebar.set_rail(True)
            self._sidebar_rail = True
        elif width >= 1250 and self._sidebar_rail:
            self._sidebar.set_rail(False)
            self._sidebar_rail = False
        if self._queue_drawer:
            if width >= 1100:
                self._close_queue_drawer()
                self._playlist_pane.setVisible(True)
            else:
                self._position_queue_drawer()
        elif width < 1000 and self._playlist_pane.isVisible() and not self._playlist_auto_hidden:
            self._playlist_pane.hide()
            self._playlist_auto_hidden = True
        elif width >= 1050 and self._playlist_auto_hidden:
            self._playlist_pane.show()
            self._playlist_auto_hidden = False
        self._reposition_overlays()

    def showEvent(self, event):
        super().showEvent(event)
        self._clamp_to_screen()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._clamp_to_screen()

    def _clamp_to_screen(self):
        if self.isFullScreen() or getattr(self, "_clamping", False):
            return
        self._clamping = True
        try:
            avail = QGuiApplication.primaryScreen().availableGeometry()
            geo = self.geometry()
            width = min(geo.width(), avail.width())
            height = min(geo.height(), avail.height())
            if (width, height) != (geo.width(), geo.height()):
                self.resize(width, height)
                geo = self.geometry()
            x = min(max(geo.x(), avail.x()), avail.x() + max(0, avail.width() - geo.width()))
            y = min(max(geo.y(), avail.y()), avail.y() + max(0, avail.height() - geo.height()))
            if (x, y) != (geo.x(), geo.y()):
                self.move(x, y)
        finally:
            self._clamping = False

    def _filter_queue(self, text: str):
        self._playlist_pane.set_search(text)

    def _rename_queue_row(self, row: int):
        if row < 0:
            return
        item = self._playlist_pane.tree.topLevelItem(row)
        if item is None:
            return
        current = item.text(0)
        entry = QLineEdit(self._playlist_pane)
        entry.setText(current)
        entry.setObjectName("IconButton")
        self._playlist_pane.tree.setItemWidget(item, 0, entry)
        entry.returnPressed.connect(lambda: self._commit_rename(item, entry))
        entry.editingFinished.connect(lambda: self._commit_rename(item, entry))
        entry.setFocus()
        entry.selectAll()

    def _commit_rename(self, item, entry):
        text = entry.text().strip()
        self._playlist_pane.tree.removeItemWidget(item, 0)
        if text:
            url = str(item.data(0, Qt.UserRole) or "")
            self._playlist_pane._display_titles[url] = text
            item.setText(0, self._playlist_pane._label_for(url))

    def _apply_settings(self, settings):
        self._volume = settings.volume
        self._muted = settings.muted
        self._rate = settings.rate
        self._watched_folders = list(settings.watched_folders)
        self._volume_slider.setValue(self._volume)
        self._rate_btn.setText(f"{self._rate:g}×")
        self.toast("Settings saved")
        self.status("Settings updated")

    def _load_visualizer(self, path):
        mode = str(self.settings_store.load().visualizer)

        self._viz_generation += 1
        generation = self._viz_generation

        self._viz_timer.stop()
        self._viz_pcm = None
        self._viz_rate = 0

        if mode == "off" or path is None:
            self._visualizer.configure("off", (), (), 0.0)
            return

        source = Path(str(path))

        if not source.is_file():
            return

        def worker():
            pcm, rate, _channels = decode_all_pcm(source)
            self._viz_bridge.resultReady.emit(
                ("pcm", generation, mode, pcm, rate)
            )

        threading.Thread(target=worker, daemon=True).start()

    def _apply_viz(self, payload):
        if not payload:
            return

        if payload[0] == "pcm":
            _, generation, mode, pcm, rate = payload

            if generation != self._viz_generation:
                return

            self._viz_pcm = pcm
            self._viz_rate = rate

            self._visualizer.configure(
                mode, (), (), self.duration or 0.0
            )

            if pcm is not None and rate > 0:
                self._viz_timer.start()

            return

        if payload[0] == "stage":
            _, generation, has_audio, has_video = payload

            if generation != self._viz_generation:
                return

            self._audio_stage = bool(has_audio) and not bool(has_video)
            self._video_surface.set_video_active(not self._audio_stage)
            self._reposition_overlays()
            return

        if payload[0] == "live":
            self._visualizer.set_live(payload[1])

    def _tick_visualizer(self):
        if (
            self._viz_pcm is None
            or self._viz_rate <= 0
            or not self.backend
            or self._paused
        ):
            return

        mode = str(self.settings_store.load().visualizer)

        if mode == "off":
            return

        try:
            position = float(self.backend.position())
        except Exception:  # noqa: BLE001 - visualizer is optional
            return

        peaks = ()
        bands = ()

        if mode in ("waveform", "both"):
            peaks = window_peaks(
                self._viz_pcm,
                self._viz_rate,
                position,
                points=240,
            )

        if mode in ("spectrum", "both"):
            bands = live_spectrum(
                self._viz_pcm,
                self._viz_rate,
                position,
                bands=48,
            )

        self._visualizer.configure(
            mode,
            peaks,
            bands,
            self.duration or 0.0,
        )

    def _probe_stage(self, source):
        generation = self._viz_generation
        probe_source = str(source)

        def worker():
            has_audio, has_video = self._probe_media_streams(probe_source)
            self._viz_bridge.resultReady.emit(
                ("stage", generation, has_audio, has_video)
            )

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _probe_media_streams(source: str) -> tuple[bool, bool]:
        raw = str(source)
        try:
            path = Path(raw)
        except (TypeError, ValueError):
            return False, False
        if path.is_file() and path.suffix.lower() in {".casu", ".mp5"}:
            try:
                with path.open("rb") as handle:
                    magic = handle.read(8)
                if magic == b"CASUNAT2":
                    container = read_native_v2(path, load_payloads=False)
                    types = [str(stream.get("type", ""))
                             for stream in container.manifest.get("streams", [])]
                    return ("audio" in types), ("video" in types)
            except (OSError, ValueError, NativeV2Error):
                return False, False
        try:
            probe = ffprobe(raw)
            streams = probe.get("streams", []) if isinstance(probe, dict) else []
            has_audio = any(isinstance(s, dict) and s.get("codec_type") == "audio"
                            for s in streams)
            has_video = any(
                isinstance(s, dict) and s.get("codec_type") == "video"
                and not (isinstance(s.get("disposition"), dict)
                         and s["disposition"].get("attached_pic"))
                for s in streams)
            return has_audio, has_video
        except Exception:  # noqa: BLE001 - stage detection is best effort
            return False, False

    def _recordings_root(self) -> Path:
        folder = str(self.settings_store.load().recordings_dir or "").strip()
        root = Path(folder).expanduser() if folder else Path.home() / "Videos" / "MPCASU"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _recording_source(self) -> str:
        if getattr(self, "_network_source", None):
            return str(self._network_source)
        if self.current is not None and self.current.is_file():
            if self.current.suffix.lower() in {".casu", ".mp5"}:
                raise RecordingError("CASU sources are stored already — use Export instead")
            return str(self.current)
        raise RecordingError("Open a local file or network stream first")

    def toggle_recording(self) -> None:
        if self._recorder is not None:
            self._record_timer.stop()
            self._finish_recording_async()
            return
        try:
            source = self._recording_source()
        except (RecordingError, OSError) as exc:
            self.toast(str(exc))
            return
        settings = self.settings_store.load()
        self._record_format = str(settings.record_format)
        self._record_split_minutes = int(settings.record_split_minutes)
        self._record_part = 1
        self._record_stem = time.strftime("%Y%m%d-%H%M%S") + "-" + (
            self.current.stem if self.current else "stream")
        if not self._start_recording_part(source):
            return
        self._record_timer = QTimer(self)
        self._record_timer.setSingleShot(True)
        self._record_timer.timeout.connect(self._rotate_recording)
        if self._record_split_minutes > 0:
            self._record_timer.start(self._record_split_minutes * 60 * 1000)
        self._record_btn.setProperty("on", "true")
        self._record_btn.style().unpolish(self._record_btn)
        self._record_btn.style().polish(self._record_btn)

    def _record_destination(self) -> Path:
        suffix = f".{self._record_format}"
        if self._record_split_minutes > 0:
            return self._recordings_root() / (
                f"{self._record_stem}-part{self._record_part:03d}{suffix}")
        return self._recordings_root() / f"{self._record_stem}{suffix}"

    def _start_recording_part(self, source: str) -> bool:
        destination = self._record_destination()
        try:
            recorder = MediaRecorder(source, destination)
            recorder.start()
        except (RecordingError, OSError) as exc:
            self.toast(f"Record failed: {exc}")
            return False
        self._recorder = recorder
        self.toast(f"Recording · {destination.name}"
                   + (f" · split every {self._record_split_minutes} min"
                      if self._record_split_minutes > 0 else ""))
        return True

    def _rotate_recording(self) -> None:
        if self._recorder is None:
            return
        self._finish_recording_async(quiet=True)
        self._record_part += 1
        try:
            source = self._recording_source()
        except (RecordingError, OSError) as exc:
            self.toast(str(exc))
            return
        if self._start_recording_part(source) and self._record_split_minutes > 0:
            self._record_timer.start(self._record_split_minutes * 60 * 1000)

    def _finish_recording_async(self) -> None:
        recorder = self._recorder
        if recorder is None or self._recording_finishing:
            return
        self._recording_finishing = True
        self._record_btn.setEnabled(False)
        self.toast("Finalizing and verifying recording…")

        def worker():
            try:
                result, error = recorder.finish(timeout=5), None
            except (RecordingError, OSError) as exc:
                result, error = None, exc

            def present():
                self._recorder = None
                self._recording_finishing = False
                self._record_btn.setEnabled(True)
                self._record_btn.setProperty("on", "false")
                self._record_btn.style().unpolish(self._record_btn)
                self._record_btn.style().polish(self._record_btn)
                if error is None:
                    self.toast(f"Recording saved · {Path(result).name}")
                else:
                    self.toast(f"Recording failed: {error}")
            QTimer.singleShot(0, present)
        threading.Thread(target=worker, daemon=True).start()

    def cycle_ab_loop(self) -> None:
        position = self.backend.position() if self.backend else 0.0
        if self._ab_a is None:
            self._ab_a = position
            self._ab_btn.setProperty("on", "true")
            self._ab_btn.style().unpolish(self._ab_btn)
            self._ab_btn.style().polish(self._ab_btn)
            self.toast(f"A point set at {position:.1f}s")
        elif self._ab_b is None:
            if position <= self._ab_a:
                self.toast("B point must be after A point")
                return
            self._ab_b = position
            self.toast(f"A–B loop active · {self._ab_a:.1f}s – {position:.1f}s")
        else:
            self._ab_a = self._ab_b = None
            self._ab_btn.setProperty("on", "false")
            self._ab_btn.style().unpolish(self._ab_btn)
            self._ab_btn.style().polish(self._ab_btn)
            self.toast("A–B loop off")

    def save_snapshot(self) -> None:
        backend = self.backend
        if backend is None or not hasattr(backend, "take_snapshot"):
            self.toast("Snapshot needs an active libVLC video")
            return
        stamp = time.strftime("%Y%m%d-%H%M%S")
        destination = self._recordings_root() / f"snapshot-{stamp}.png"
        try:
            backend.take_snapshot(destination)
            self.toast(f"Snapshot saved · {destination.name}")
        except (BackendError, OSError) as exc:
            self.toast(f"Snapshot failed: {exc}")

    def toggle_visualizer(self) -> None:
        settings = self.settings_store.load()
        mode = "off" if settings.visualizer != "off" else "spectrum"
        self.settings_store.save(replace(settings, visualizer=mode))
        self._viz_btn.setProperty("on", "true" if mode != "off" else "false")
        self._viz_btn.style().unpolish(self._viz_btn)
        self._viz_btn.style().polish(self._viz_btn)
        if mode == "off":
            self._stop_stream_viz()
            self._viz_timer.stop()
            self._viz_pcm = None
            self._viz_rate = 0
            self._visualizer.configure("off", (), (), 0.0)
        elif self._network_source:
            self._visualizer.configure(
                mode, (), (), self.duration or 0.0)
            self._start_stream_viz(self._network_source)
        elif self.current is not None:
            self._load_visualizer(self.current)
        else:
            self._visualizer.configure(mode, (), (), 0.0)
        self.toast(f"Visualizer: {mode}")

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            self._drop_overlay.show()
            self._drop_overlay.raise_()
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._drop_overlay.hide()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self._drop_overlay.hide()
        targets = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            targets.append(local if local else url.toString())
        targets = [t for t in targets if t]
        if targets:
            self.add_files(targets)
            event.acceptProposedAction()

    def _start_stream_viz(self, source: str):
        import shutil
        import subprocess
        if not shutil.which("ffmpeg"):
            return
        self._stop_stream_viz()
        proc = subprocess.Popen(
            ["ffmpeg", "-v", "quiet", "-i", source, "-map", "0:a:0",
             "-ac", "1", "-ar", "22050", "-f", "s16le", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._stream_viz_proc = proc
        bridge = self._viz_bridge

        def reader():
            import numpy as np
            while True:
                try:
                    data = proc.stdout.read(4410)
                except (OSError, ValueError):
                    break
                if not data:
                    break
                samples = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
                if len(samples) < 1024:
                    continue
                windowed = samples[:1024] * np.hanning(1024)
                spectrum = np.abs(np.fft.rfft(windowed))[1:49]
                peak = float(spectrum.max()) if spectrum.size else 0.0
                if peak <= 1e-6:
                    bands = tuple(0.0 for _ in spectrum)
                else:
                    bands = tuple(
                        float(max(0.0, min(1.0, (value / peak) *
                                           (0.35 + 0.65 * np.log10(index + 2) / np.log10(50)))))
                        for index, value in enumerate(spectrum))
                bridge.resultReady.emit(("live", bands))
        import threading
        self._stream_viz_thread = threading.Thread(target=reader, daemon=True)
        self._stream_viz_thread.start()

    def _stop_stream_viz(self):
        proc = getattr(self, "_stream_viz_proc", None)
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass
            self._stream_viz_proc = None
        self._visualizer.clear_live()

    def _epg_now_next(self) -> str:
        if self._epg_catalog is None and self._epg_guide is None:
            return "no EPG loaded"
        url = str(self._network_source or self.current or "")
        if self._epg_catalog is not None:
            channel = next((c for c in self._epg_catalog.channels
                            if getattr(c, "url", "") == url), None)
            if channel is not None:
                if self._epg_guide is not None:
                    try:
                        programmes = self._epg_guide.for_channel(
                            getattr(channel, "tvg_id", "") or channel.name)
                        now = next((p for p in programmes
                                    if getattr(p, "current", False)), None)
                        if now is not None:
                            return f"{channel.name} · now: {now.title}"
                    except Exception:  # noqa: BLE001 - guide lookup is best effort
                        pass
                return str(channel.name)
        return "EPG loaded"

    def _options_action(self, action: str):
        if action == "clear-cache":
            import shutil, tempfile
            cache_dir = Path(tempfile.gettempdir()) / "yt-dlp"
            if cache_dir.is_dir():
                shutil.rmtree(cache_dir, ignore_errors=True)
                self.toast(f"Cleared {cache_dir}")
            else:
                self.toast("No yt-dlp cache found")
        elif action == "refresh-db":
            self.refresh_watched_folders()

    def _on_epg_channel(self, channel):
        url = getattr(channel, "url", None) or ""
        name = getattr(channel, "name", str(channel))
        if url:
            self._resolve_and_open_external_source(url, display_label=name)

    def _on_source_activated(self, payload):
        if isinstance(payload, str):
            self._resolve_and_open_external_source(payload)
        else:
            self._resolve_and_open_external_source(payload.url,
                                                   display_label=payload.title)

    def _resolve_and_open_external_source(self, source: str, *,
                                          display_label: str | None = None):
        """Resolve web sources off the GUI thread, then hand a direct URL to libVLC."""
        if is_youtube_url(source):
            if not self.settings_store.load().ytdlp_consent:
                self.show_sources("youtube")
                self.status("YouTube playback requires yt-dlp consent — accept in the view above")
                return
        self._resolve_generation += 1
        generation = self._resolve_generation
        self.status("Resolving network media…")

        def worker():
            try:
                resolved = resolve_media_location(source)
            except (LocationResolutionError, SpotifyError, OSError, ValueError) as exc:
                self._resolve_bridge.errorReady.emit((generation, str(exc)))
                return
            self._resolve_bridge.resultReady.emit(
                (generation, resolved, display_label or source))
        threading.Thread(target=worker, daemon=True).start()

    def _on_resolve_ready(self, payload):
        generation, resolved, label = payload
        if generation != self._resolve_generation:
            return
        self._open_external_source(resolved, display_label=label)

    def _on_resolve_failed(self, payload):
        generation, detail = payload
        if generation != self._resolve_generation:
            return
        self.status(f"Could not resolve network source: {detail}")
        self.toast(f"Could not resolve network source: {detail}")

    def _open_external_source(self, source: str, *, display_label: str | None = None):
        self._show_player_page()
        self.stop()
        self._end_handled = False
        self.current = None
        visible_source = display_media_source(display_label or source)
        self._now_playing_bar.set_now_playing(visible_source)
        self._set_caption(visible_source)
        try:
            self.backend = LibVLCBackend(self._video_surface.handle)
            self.backend.on_event = self._backend_event
            self.backend.open_source(source)
            self.controller.attach(self.backend, visible_source)
            self.controller.play()
            self._apply_playback_rate()
            self._apply_backend_settings()
            self._diagnostics_bar.set_values(
                support="Legacy network backend", integrity="unavailable",
                segmented="unavailable",
            )
            self.duration = self.backend.duration()
            self._seek_slider.set_duration(self.duration)
            self._draw_chapter_markers()
            capabilities = self.backend.capabilities()
            self.status(f"Playing network source · {capabilities.get('version', 'libVLC')} · timing owned by libVLC")
            self._video_surface.set_video_active(True)
            self._network_source = source
            mode = str(self.settings_store.load().visualizer)
            self._visualizer.configure(
                mode,
                (),
                (),
                self.duration or 0.0,
            )
            if mode != "off" and str(source).startswith(("http://", "https://")):
                self._start_stream_viz(source)
            self._probe_stage(source)
        except (BackendError, OSError) as exc:
            self.controller.close()
            self.backend = None
            self.status(f"Could not open network source: {exc}")
            self.toast(f"Could not open network source: {exc}")

    def _render_playlist(self, selected: int = -1):
        self._playlist_pane.populate(list(self.playlist_model.items), selected)

    def _play_playlist_row(self, row: int):
        self._playlist_pane.select_row(row)
        self.play_selected()

    def _on_playlist_remove(self, indices):
        if not indices:
            if self.backend:
                self.stop()
            self.playlist_model.clear()
            self._render_playlist()
            self.current = None
            self._now_playing_bar.set_now_playing("")
            self._set_caption("")
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
        if not len(self.playlist_model):
            self.toast("The queue is empty — nothing to save")
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "Save playlist",
            filter="M3U playlist (*.m3u);;PLS playlist (*.pls);;MPCASU JSON (*.json);;All files (*.*)",
        )
        if not target:
            return
        try:
            saved = save_playlist_file(target, self.playlist_model)
        except (PlaylistError, OSError) as exc:
            self.toast(f"Could not save playlist: {exc}")
            return
        self.status(f"Playlist saved · {saved.name}")
        self.toast(f"Playlist saved · {saved}")

    def load_playlist(self):
        from PySide6.QtWidgets import QFileDialog
        source, _ = QFileDialog.getOpenFileName(
            self, "Load playlist",
            filter="Playlists (*.m3u *.m3u8 *.pls *.json);;All files (*.*)",
        )
        if not source:
            return
        try:
            loaded = load_playlist_file(source)
            added = self.playlist_model.add(list(loaded.items))
        except (PlaylistError, OSError, ValueError) as exc:
            self.toast(f"Could not load playlist: {exc}")
            return
        self._render_playlist()
        self.status(f"Playlist loaded · {Path(source).name} · {added} item(s) added")
        self.toast(f"Playlist loaded · {added} item(s) added")

    def _apply_queue_order(self, order: list):
        values = [value for value in order if value]
        if len(values) != len(self.playlist_model):
            return
        try:
            self.playlist_model = PlaylistModel.from_payload(
                {"version": 1, "items": [str(value) for value in values]})
        except PlaylistError:
            return
        if self.current is not None:
            index = self.playlist_model.index_of(self.current)
            if index is not None:
                self._playlist_pane.select_row(index)
        self.status("Queue reordered")

    def _on_queue_child_play(self, source: str):
        if source.startswith(("http://", "https://", "rtsp://", "rtmp://",
                              "udp://", "rtp://", "ftp://", "smb://")):
            self._resolve_and_open_external_source(source)
            return
        path = Path(source)
        if not path.is_file():
            self.toast(f"Local file not found: {path.name}")
            return
        self.add_files([path])
        index = self.playlist_model.index_of(path)
        if index is not None:
            self._playlist_pane.select_row(index)
            self.play_selected()

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
        self._library_page._refresh()
        self._show_page(self._library_page, "LOCAL FILES")
        self._sidebar.set_active("LOCAL FILES")

    def _show_page(self, page, title: str):
        if page not in self._pages:
            self._center_stack.addWidget(page)
            self._pages.append(page)
        self._center_stack.setCurrentWidget(page)
        if hasattr(self, "_topbar_title"):
            self._topbar_title.setText(title)
        if hasattr(self, "_back_btn"):
            self._back_btn.show()

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
                    "CASU: validated envelope manifest",
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
            self.toast(f"Media information unavailable: {exc}")

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
        current = self.settings_store.load()
        updated = replace(
            current,
            volume=self._volume,
            muted=self._muted,
            rate=self._rate,
            audio_device=self._audio_device,
            watched_folders=tuple(self._watched_folders),
        )
        self.settings_store.save(updated)

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
            self._play_btn.setText("| |")
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
        self._visualizer.set_position(pos)
        if self._ab_a is not None and self._ab_b is not None and self.backend is not None:
            if pos >= self._ab_b - 0.05:
                self.controller.seek(self._ab_a)
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
