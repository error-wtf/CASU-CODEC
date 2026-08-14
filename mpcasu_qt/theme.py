# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu
"""MPCASU dark/red visual theme.

Single source of truth for every colour, radius and metric used by the Qt
player. Keeping this in one module means the whole application restyles
consistently and the values can be asserted in tests.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    """Immutable colour set matching the MPCASU product design."""

    # Structural surfaces, darkest to lightest.
    window: str = "#0a0a0c"
    sidebar: str = "#0d0d10"
    surface: str = "#121217"
    surface_alt: str = "#16161c"
    card: str = "#141419"
    border: str = "#232329"
    border_strong: str = "#2e2e36"

    # Brand accent.
    accent: str = "#e01020"
    accent_hot: str = "#ff2436"
    accent_dim: str = "#8c0a16"
    accent_wash: str = "#1d0c10"

    # Text.
    text: str = "#f2f2f5"
    text_muted: str = "#9a9aa6"
    text_faint: str = "#66666f"
    text_on_accent: str = "#ffffff"

    # Semantic states.
    ok: str = "#25c065"
    warn: str = "#e0a010"
    error: str = "#ff4040"


@dataclass(frozen=True)
class Metrics:
    """Layout constants shared by the widgets."""

    sidebar_width: int = 236
    playlist_width: int = 320
    radius: int = 8
    radius_small: int = 6
    radius_large: int = 12
    control_height: int = 34
    transport_button: int = 42
    play_button: int = 58
    pad: int = 12
    pad_small: int = 8
    pad_large: int = 18
    thumbnail_width: int = 64
    thumbnail_height: int = 38


PALETTE = Palette()
METRICS = Metrics()


def stylesheet(palette: Palette = PALETTE, metrics: Metrics = METRICS) -> str:
    """Build the complete application stylesheet."""
    p, m = palette, metrics
    return f"""
QWidget {{
    background-color: {p.window};
    color: {p.text};
    font-family: "Inter", "Segoe UI", "Ubuntu", "DejaVu Sans", sans-serif;
    font-size: 13px;
}}
QMainWindow, QDialog {{ background-color: {p.window}; }}

/* ---------- Sidebar ---------- */
#Sidebar {{
    background-color: {p.sidebar};
    border-right: 1px solid {p.border};
}}
#SidebarSection {{
    color: {p.text_faint};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.4px;
    padding: 14px 16px 6px 16px;
    background: transparent;
}}
#BrandName {{
    color: {p.text};
    font-size: 21px;
    font-weight: 800;
    letter-spacing: 0.5px;
    background: transparent;
}}
#BrandSub {{
    color: {p.accent};
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 4px;
    background: transparent;
}}

QPushButton#NavItem {{
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    color: {p.text_muted};
    text-align: left;
    padding: 9px 14px 9px 15px;
    font-size: 13px;
    border-radius: 0px;
}}
QPushButton#NavItem:hover {{
    background-color: {p.surface};
    color: {p.text};
}}
QPushButton#NavItem:checked {{
    background-color: {p.accent_wash};
    border-left: 3px solid {p.accent};
    color: {p.text};
    font-weight: 600;
}}

/* ---------- Top bar ---------- */
#TopBar {{
    background-color: {p.surface};
    border-bottom: 1px solid {p.border};
}}
#BreadcrumbLabel {{ color: {p.accent}; font-weight: 600; background: transparent; }}

QLineEdit {{
    background-color: {p.surface_alt};
    border: 1px solid {p.border_strong};
    border-radius: {m.radius_small}px;
    padding: 6px 10px;
    color: {p.text};
    selection-background-color: {p.accent};
    selection-color: {p.text_on_accent};
}}
QLineEdit:focus {{ border: 1px solid {p.accent}; }}

QComboBox {{
    background-color: {p.surface_alt};
    border: 1px solid {p.border_strong};
    border-radius: {m.radius_small}px;
    padding: 5px 10px;
    color: {p.text};
    min-height: 22px;
}}
QComboBox:hover {{ border: 1px solid {p.accent_dim}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background-color: {p.surface};
    border: 1px solid {p.border_strong};
    selection-background-color: {p.accent};
    selection-color: {p.text_on_accent};
    outline: none;
}}

/* ---------- Buttons ---------- */
QPushButton {{
    background-color: {p.surface_alt};
    border: 1px solid {p.border_strong};
    border-radius: {m.radius_small}px;
    padding: 6px 12px;
    color: {p.text};
}}
QPushButton:hover {{ background-color: {p.card}; border-color: {p.accent_dim}; }}
QPushButton:pressed {{ background-color: {p.accent_wash}; }}
QPushButton:disabled {{ color: {p.text_faint}; border-color: {p.border}; }}
QPushButton:checked {{
    background-color: {p.accent_wash};
    border-color: {p.accent};
    color: {p.text};
}}

QPushButton#IconButton {{
    background: transparent;
    border: none;
    border-radius: {m.radius_small}px;
    padding: 6px;
    color: {p.text_muted};
    font-size: 15px;
}}
QPushButton#IconButton:hover {{ background-color: {p.surface_alt}; color: {p.text}; }}
QPushButton#IconButton:checked {{ color: {p.accent}; background-color: {p.accent_wash}; }}

QPushButton#TransportButton {{
    background: transparent;
    border: none;
    color: {p.accent};
    font-size: 20px;
    padding: 0px;
}}
QPushButton#TransportButton:hover {{ color: {p.accent_hot}; }}
QPushButton#TransportButton:disabled {{ color: {p.text_faint}; }}

QPushButton#PlayButton {{
    background-color: transparent;
    border: 2px solid {p.accent};
    border-radius: {m.play_button // 2}px;
    color: {p.accent};
    font-size: 20px;
    padding: 0px;
}}
QPushButton#PlayButton:hover {{
    border-color: {p.accent_hot};
    color: {p.accent_hot};
    background-color: {p.accent_wash};
}}
QPushButton#PlayButton:disabled {{ border-color: {p.text_faint}; color: {p.text_faint}; }}

/* ---------- Video stage ---------- */
#VideoStage {{ background-color: #000000; border: none; }}
#VideoSurface {{ background-color: #000000; }}

#OverlayBadge {{
    background-color: rgba(10, 10, 12, 200);
    border: 1px solid {p.border_strong};
    border-radius: {m.radius_small}px;
    color: {p.text};
    font-size: 10px;
    font-weight: 700;
    padding: 3px 7px;
}}
#OverlayBadgeAccent {{
    background-color: rgba(224, 16, 32, 40);
    border: 1px solid {p.accent};
    border-radius: {m.radius_small}px;
    color: {p.accent};
    font-size: 10px;
    font-weight: 700;
    padding: 3px 7px;
}}
#NowPlayingTitle {{
    color: {p.text};
    font-size: 17px;
    font-weight: 700;
    background: transparent;
}}
#NowPlayingMeta {{ color: {p.text_muted}; font-size: 11px; background: transparent; }}
#TimeLabel {{
    color: {p.text_muted};
    font-size: 11px;
    font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;
    background: transparent;
}}

/* ---------- Sliders ---------- */
QSlider::groove:horizontal {{
    height: 4px;
    background: {p.border_strong};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {p.accent};
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}}
QSlider::handle:horizontal:hover {{ background: {p.accent_hot}; }}
QSlider::groove:vertical {{ width: 4px; background: {p.border_strong}; border-radius: 2px; }}
QSlider::sub-page:vertical {{ background: {p.border_strong}; }}
QSlider::add-page:vertical {{ background: {p.accent}; border-radius: 2px; }}
QSlider::handle:vertical {{
    background: {p.accent}; height: 12px; margin: 0 -4px; border-radius: 6px;
}}

/* ---------- Panels / cards ---------- */
#Panel {{
    background-color: {p.card};
    border: 1px solid {p.border};
    border-radius: {m.radius}px;
}}
#PanelTitle {{
    color: {p.text_muted};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.1px;
    background: transparent;
}}
#PanelValue {{ color: {p.accent}; font-size: 12px; font-weight: 700; background: transparent; }}
#PanelHint {{ color: {p.text_faint}; font-size: 10px; background: transparent; }}

/* ---------- Playlist ---------- */
#PlaylistPane {{
    background-color: {p.sidebar};
    border-left: 1px solid {p.border};
}}
QListWidget {{
    background-color: transparent;
    border: none;
    outline: none;
}}
QListWidget::item {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: {m.radius_small}px;
    padding: 0px;
    margin: 2px 6px;
}}
QListWidget::item:hover {{ background-color: {p.surface}; }}
QListWidget::item:selected {{
    background-color: {p.accent_wash};
    border: 1px solid {p.accent};
}}

QTableWidget {{
    background-color: {p.window};
    border: none;
    gridline-color: {p.border};
    outline: none;
}}
QTableWidget::item {{ padding: 6px; border: none; }}
QTableWidget::item:selected {{ background-color: {p.accent_wash}; color: {p.text}; }}
QHeaderView::section {{
    background-color: {p.surface};
    color: {p.text_muted};
    border: none;
    border-bottom: 1px solid {p.border};
    padding: 7px;
    font-size: 11px;
    font-weight: 600;
}}

/* ---------- Status bar ---------- */
#StatusBar {{
    background-color: {p.surface};
    border-top: 1px solid {p.border};
}}
#StatusText {{ color: {p.text_muted}; font-size: 11px; background: transparent; }}
#StatusAccent {{ color: {p.accent}; font-size: 11px; font-weight: 600; background: transparent; }}

QProgressBar {{
    background-color: {p.border};
    border: none;
    border-radius: 2px;
    height: 4px;
    text-align: center;
}}
QProgressBar::chunk {{ background-color: {p.accent}; border-radius: 2px; }}

/* ---------- Menus ---------- */
QMenu {{
    background-color: {p.surface};
    border: 1px solid {p.border_strong};
    border-radius: {m.radius_small}px;
    padding: 4px;
}}
QMenu::item {{ padding: 7px 26px 7px 22px; border-radius: 4px; color: {p.text}; }}
QMenu::item:selected {{ background-color: {p.accent}; color: {p.text_on_accent}; }}
QMenu::item:disabled {{ color: {p.text_faint}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 4px 8px; }}
QMenu::indicator {{ width: 14px; height: 14px; left: 6px; }}

QMenuBar {{ background-color: {p.surface}; border-bottom: 1px solid {p.border}; }}
QMenuBar::item {{ padding: 6px 11px; background: transparent; color: {p.text_muted}; }}
QMenuBar::item:selected {{ background-color: {p.surface_alt}; color: {p.text}; }}

/* ---------- Scrollbars ---------- */
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {p.border_strong}; border-radius: 4px; min-height: 26px;
}}
QScrollBar::handle:vertical:hover {{ background: {p.accent_dim}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: {p.border_strong}; border-radius: 4px; min-width: 26px;
}}
QScrollBar::handle:horizontal:hover {{ background: {p.accent_dim}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}

/* ---------- Misc ---------- */
QToolTip {{
    background-color: {p.surface};
    color: {p.text};
    border: 1px solid {p.accent_dim};
    border-radius: 4px;
    padding: 5px 8px;
}}
QSplitter::handle {{ background-color: {p.border}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:hover {{ background-color: {p.accent_dim}; }}
QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
QCheckBox::indicator:unchecked {{
    border: 1px solid {p.border_strong};
    border-radius: 3px;
    background: {p.surface_alt};
}}
QCheckBox::indicator:checked {{
    border: 1px solid {p.accent};
    border-radius: 3px;
    background: {p.accent};
}}
QSpinBox, QDoubleSpinBox {{
    background-color: {p.surface_alt};
    border: 1px solid {p.border_strong};
    border-radius: {m.radius_small}px;
    padding: 5px 7px;
    color: {p.text};
}}
QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {p.accent}; }}
QTabWidget::pane {{ border: 1px solid {p.border}; border-radius: {m.radius}px; top: -1px; }}
QTabBar::tab {{
    background: transparent;
    color: {p.text_muted};
    padding: 8px 16px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {p.text}; border-bottom: 2px solid {p.accent}; }}
QTabBar::tab:hover {{ color: {p.text}; }}
"""


def format_duration(seconds: float | None) -> str:
    """Format seconds as H:MM:SS or MM:SS; unknown values become ``--:--``."""
    if seconds is None:
        return "--:--"
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return "--:--"
    if value < 0 or value != value or value in (float("inf"), float("-inf")):
        return "--:--"
    total = int(value)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
