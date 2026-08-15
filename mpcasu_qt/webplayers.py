# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Tabbed embedded web-player views (Spotify/Hearthis/Tidal/Netflix).

Each provider gets its own tab with an embedded Chromium (QtWebEngine) view, a
URL/search field and the official web player loaded through it. Direct URLs and
searches open in the matching tab; the user logs in with their normal account.
"""
from __future__ import annotations

from PySide6.QtCore import QUrl, Qt
from PySide6.QtWidgets import QLineEdit, QTabWidget, QVBoxLayout, QWidget

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    _HAVE_WEBENGINE = True
except ImportError:
    QWebEngineView = None
    _HAVE_WEBENGINE = False

from casu.webproviders import WEB_PLAYERS, web_player_url


class WebPlayerTabs(QWidget):
    """Tab widget with one embedded web player per provider."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("WebPlayers")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._views: dict[str, QWebEngineView] = {}
        self._entries: dict[str, QLineEdit] = {}
        for key, spec in WEB_PLAYERS.items():
            page = QWidget()
            page.setStyleSheet("background: transparent;")
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(6, 6, 6, 6)
            page_layout.setSpacing(6)
            entry = QLineEdit()
            entry.setObjectName("IconButton")
            entry.setPlaceholderText(f"{spec['label']} URL oder Suchbegriff…")
            entry.returnPressed.connect(lambda k=key: self._submit(k))
            page_layout.addWidget(entry)
            if _HAVE_WEBENGINE:
                view = QWebEngineView()
                page_layout.addWidget(view)
            else:
                view = None
            self._entries[key] = entry
            self._views[key] = view
            self._tabs.addTab(page, spec["label"])
        layout.addWidget(self._tabs)

    @property
    def tabs(self) -> QTabWidget:
        return self._tabs

    def _submit(self, key: str):
        text = self._entries[key].text().strip()
        if not text:
            return
        if "://" in text and "." in text:
            self.open(key, url=text)
        else:
            self.open(key, query=text)

    def open(self, provider: str, *, query: str = "", url: str = ""):
        """Load a provider's web player at a search query or direct URL."""
        keys = list(WEB_PLAYERS)
        if provider not in self._views:
            provider = "spotify"
        self._tabs.setCurrentIndex(keys.index(provider))
        if query:
            self._entries[provider].setText(query)
        target = web_player_url(provider, query=query, url=url)
        view = self._views[provider]
        if view is not None:
            view.load(QUrl(target))

    def focus_entry(self, provider: str):
        if provider in self._entries:
            self._entries[provider].setFocus()
            self._entries[provider].selectAll()
