// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "theme.hpp"

#include <QTime>
#include <cmath>

namespace mpcasu {

QString format_duration(double seconds) {
    if (seconds < 0.0) return "00:00";
    const int total = static_cast<int>(std::llround(seconds));
    const int h = total / 3600;
    const int m = (total % 3600) / 60;
    const int s = total % 60;
    if (h > 0)
        return QString("%1:%2:%3").arg(h).arg(m, 2, 10, QChar('0')).arg(s, 2, 10, QChar('0'));
    return QString("%1:%2").arg(m, 2, 10, QChar('0')).arg(s, 2, 10, QChar('0'));
}

QString application_stylesheet() {
    const Palette& P = palette();
    const QString bg = P.bg, panel = P.panel, panel2 = P.panel2, line = P.line;
    const QString red = P.red, red_dark = P.red_dark, muted = P.muted, text = P.text;
    const QString secondary = P.secondary, stage = P.stage, sidebar = P.sidebar;
    const QString button = P.button, button_text = P.button_text, input_bg = P.input_bg;
    const QString input_border = P.input_border, toast_bg = P.toast_bg, toast_border = P.toast_border;
    const QString badge_bg = P.badge_bg, badge_border = P.badge_border, scrollbar = P.scrollbar;

    return QString(R"QSS(
QMainWindow, QWidget#Root { background-color: %1; color: %2; }
QWidget { color: %2; font-family: "Segoe UI", "Inter", sans-serif; font-size: 13px; }
QFrame#TopBar { background-color: %3; border-bottom: 1px solid %4; }
QFrame#Panel { background-color: %3; border: 1px solid %4; border-radius: 10px; }
QFrame#Sidebar { background-color: %5; border-right: 1px solid %4; }
QFrame#PlaylistPane { background-color: %5; border-left: 1px solid %4; }

QLabel#NowPlayingTitle { color: %2; font-size: 16px; font-weight: 800; background: transparent; }
QLabel#NowPlayingMeta { color: %6; font-size: 12px; }
QLabel#TimeLabel { color: %6; font-size: 11px; font-family: "Consolas", monospace; }
QLabel#StatusBar { color: %6; font-size: 11px; background: %3; border-top: 1px solid %4; padding: 4px 10px; }
QLabel#Toast { color: %2; background-color: %7; border: 1px solid %8; border-radius: 8px; padding: 10px 16px; font-size: 12px; font-weight: 600; }

QPushButton { background-color: %9; color: %10; border: 1px solid %4; border-radius: 7px; padding: 4px 10px; }
QPushButton:hover { background-color: %11; }
QPushButton:pressed { background-color: %12; }
QPushButton:checked { background-color: %11; border-color: %13; color: %2; }
QPushButton:disabled { color: %6; }
QPushButton#TransportButton { background-color: transparent; border: 1px solid %4; border-radius: 7px; min-width: 40px; min-height: 40px; font-size: 14px; }
QPushButton#TransportButton:hover { background-color: %11; }
QPushButton#IconButton { background-color: transparent; border: none; border-radius: 7px; padding: 4px 8px; min-width: 36px; min-height: 36px; font-size: 14px; }
QPushButton#IconButton:hover { background-color: %11; }
QPushButton#PlayButton { background-color: %13; color: #ffffff; border: none; border-radius: 26px; font-size: 18px; }
QPushButton#PlayButton:hover { background-color: #ff3b48; }
QPushButton#NavButton { text-align: left; padding-left: 16px; background-color: transparent; border: none; border-radius: 7px; font-weight: 600; color: %14; }
QPushButton#NavButton:hover { background-color: %11; }
QPushButton#NavButton:checked { background-color: %11; color: %2; border-left: 3px solid %13; }

QLineEdit, QComboBox, QSpinBox { background-color: %15; border: 1px solid %16; border-radius: 7px; padding: 5px 8px; color: %2; selection-background-color: %13; }
QLineEdit:focus, QComboBox:focus { border-color: %13; }
QSlider::groove:horizontal { height: 4px; background: %16; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; background: %13; }
QSlider#VolumeSlider::groove:horizontal { height: 4px; background: %16; border-radius: 2px; }
QSlider#VolumeSlider::handle:horizontal { width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: %14; }

QTreeWidget, QListWidget, QTableWidget { background-color: %17; border: 1px solid %4; border-radius: 8px; outline: none; }
QTreeWidget::item, QListWidget::item, QTableWidget::item { padding: 4px; }
QTreeWidget::item:selected, QListWidget::item:selected, QTableWidget::item:selected { background-color: %11; color: %2; }
QHeaderView::section { background-color: %3; border: none; border-bottom: 1px solid %4; padding: 5px; color: %6; }

QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: %18; border-radius: 5px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 10px; }
QScrollBar::handle:horizontal { background: %18; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QMenu { background-color: %3; border: 1px solid %4; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 6px 20px; border-radius: 5px; }
QMenu::item:selected { background-color: %11; }
QTabWidget::pane { border: 1px solid %4; border-radius: 8px; background: %17; }
QTabBar::tab { background: %3; border: 1px solid %4; padding: 6px 14px; border-bottom: none; border-top-left-radius: 7px; border-top-right-radius: 7px; color: %6; }
QTabBar::tab:selected { background: %11; color: %2; }
QMessageBox { background-color: %3; }
)QSS")
        .arg(bg, text, panel, line, sidebar, muted, toast_bg, toast_border,
             button, button_text, red_dark, bg, red, secondary, input_bg,
             input_border, badge_bg, scrollbar);
}

}  // namespace mpcasu
