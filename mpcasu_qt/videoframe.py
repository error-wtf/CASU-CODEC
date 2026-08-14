# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu
"""Qt video surface and the adapter that embeds libVLC output into it.

``LibVLCBackend`` was written against a Tk widget and calls ``winfo_id()`` to
obtain the native window handle. Rather than modify that tested backend, this
module supplies a tiny adapter object exposing the same single method backed by
``QWidget.winId()``. The backend therefore embeds into Qt unchanged.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget


class NativeHandleAdapter:
    """Expose ``winfo_id()`` for a Qt widget so libVLC can embed into it.

    ``LibVLCBackend`` only ever needs the native window id, so mirroring that
    one method keeps the backend completely unaware of the toolkit in use.
    """

    __slots__ = ("_widget",)

    def __init__(self, widget: QWidget) -> None:
        self._widget = widget

    def winfo_id(self) -> int:
        """Return the platform window handle of the wrapped widget."""
        return int(self._widget.winId())

    @property
    def widget(self) -> QWidget:
        return self._widget


class VideoSurface(QWidget):
    """Native window that libVLC renders into directly.

    The widget uses a native window id and paints nothing itself while video is
    active, avoiding flicker from Qt repainting over the video overlay. When no
    video is present it shows either cover art or the MPCASU wordmark.
    """

    doubleClicked = Signal()
    clicked = Signal()
    wheelScrolled = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("VideoSurface")
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(320, 180)
        self._video_active = False
        self._cover: QPixmap | None = None
        self._placeholder = "MPCASU"
        self.handle = NativeHandleAdapter(self)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    def set_video_active(self, active: bool) -> None:
        """Mark whether libVLC is currently drawing into this surface."""
        if self._video_active != bool(active):
            self._video_active = bool(active)
            self.update()

    def is_video_active(self) -> bool:
        return self._video_active

    def set_cover(self, pixmap: QPixmap | None) -> None:
        """Display cover art for audio-only playback."""
        self._cover = pixmap
        self.update()

    def cover(self) -> QPixmap | None:
        return self._cover

    def clear(self) -> None:
        """Reset to the idle placeholder state."""
        self._video_active = False
        self._cover = None
        self.update()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._video_active:
            # libVLC owns the surface; painting would flicker over the video.
            return
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), QColor("#000000"))
            if self._cover is not None and not self._cover.isNull():
                scaled = self._cover.scaled(
                    self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                x = (self.width() - scaled.width()) // 2
                y = (self.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
            else:
                painter.setPen(QColor("#2a2a32"))
                font = painter.font()
                font.setPointSize(max(16, min(46, self.width() // 16)))
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(self.rect(), Qt.AlignCenter, self._placeholder)
        finally:
            painter.end()

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt naming
        delta = event.angleDelta().y()
        if delta:
            self.wheelScrolled.emit(1 if delta > 0 else -1)
            event.accept()
            return
        super().wheelEvent(event)
