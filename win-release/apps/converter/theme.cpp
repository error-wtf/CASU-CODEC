// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "theme.hpp"

namespace casu::conv {

namespace {
DesignTokens g_tokens;
bool g_init = false;
}  // namespace

const DesignTokens& design_tokens() {
    if (!g_init) {
        g_tokens = DesignTokens();
        g_init = true;
    }
    return g_tokens;
}

std::string application_stylesheet() {
    const DesignTokens& t = design_tokens();
    std::string css;
    css += "QMainWindow, QDialog { background: " + t.bg + "; }\n";
    css += "QWidget { color: " + t.text + "; font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px; }\n";
    css += "QLabel { color: " + t.secondary + "; }\n";
    css += "QLabel#Title { color: " + t.red + "; font-size: 22px; font-weight: 700; }\n";
    css += "QLabel#PanelHeading { color: " + t.red + "; font-size: 10px; font-weight: 700; }\n";
    css += "QLabel#Hint { color: " + t.muted + "; font-size: 11px; }\n";
    css += "QLabel#Status { color: " + t.secondary + "; }\n";
    css += "QFrame#Panel { background: " + t.panel + "; border-radius: 10px; }\n";
    css += "QFrame#Sidebar { background: " + t.sidebar + "; }\n";
    css += "QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: " + t.input_bg +
           "; color: " + t.text + "; border: 1px solid " + t.input_border +
           "; border-radius: 7px; padding: 5px 8px; }\n";
    css += "QLineEdit:focus, QComboBox:focus { border: 1px solid " + t.red + "; }\n";
    css += "QComboBox::drop-down { border: none; width: 20px; }\n";
    css += "QComboBox::down-arrow { image: none; border-left: 5px solid transparent; "
           "border-right: 5px solid transparent; border-top: 6px solid " + t.secondary + "; }\n";
    css += "QComboBox QAbstractItemView { background: " + t.panel2 + "; color: " + t.text +
           "; border: 1px solid " + t.line + "; selection-background-color: " + t.red_dark + "; }\n";
    css += "QPushButton { background: " + t.button + "; color: " + t.button_text +
           "; border: none; border-radius: 7px; padding: 7px 14px; }\n";
    css += "QPushButton:hover { background: " + t.red_dark + "; }\n";
    css += "QPushButton:pressed { background: " + t.red + "; }\n";
    css += "QPushButton:disabled { color: " + t.muted + "; background: " + t.panel + "; }\n";
    css += "QPushButton#Primary { background: " + t.red + "; color: #ffffff; font-weight: 700; padding: 10px 22px; }\n";
    css += "QPushButton#Primary:hover { background: #ff3a47; }\n";
    css += "QPushButton#Primary:disabled { background: " + t.red_dark + "; color: " + t.muted + "; }\n";
    css += "QListWidget { background: " + t.input_bg + "; color: " + t.text +
           "; border: 1px solid " + t.input_border + "; border-radius: 7px; padding: 4px; }\n";
    css += "QListWidget::item { padding: 3px 6px; border-radius: 4px; }\n";
    css += "QListWidget::item:selected { background: " + t.red_dark + "; color: " + t.text + "; }\n";
    css += "QListWidget::item:hover { background: " + t.panel2 + "; }\n";
    css += "QProgressBar { background: " + t.line + "; border: none; border-radius: 4px; "
           "text-align: center; color: " + t.text + "; height: 16px; }\n";
    css += "QProgressBar::chunk { background: " + t.red + "; border-radius: 4px; }\n";
    css += "QCheckBox, QRadioButton { color: " + t.secondary + "; }\n";
    css += "QCheckBox::indicator, QRadioButton::indicator { width: 15px; height: 15px; }\n";
    css += "QCheckBox::indicator:checked { background: " + t.red + "; }\n";
    css += "QRadioButton::indicator:checked { border: 4px solid " + t.red + "; background: " + t.bg + "; }\n";
    css += "QScrollBar:vertical { background: " + t.bg + "; width: 10px; }\n";
    css += "QScrollBar::handle:vertical { background: " + t.scrollbar + "; border-radius: 4px; min-height: 24px; }\n";
    css += "QScrollBar::add-line, QScrollBar::sub-line { height: 0; }\n";
    css += "QScrollBar:horizontal { background: " + t.bg + "; height: 10px; }\n";
    css += "QScrollBar::handle:horizontal { background: " + t.scrollbar + "; border-radius: 4px; min-width: 24px; }\n";
    css += "QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }\n";
    css += "QMessageBox { background: " + t.panel + "; }\n";
    css += "QMenuBar { background: " + t.bg + "; }\n";
    css += "QMenu { background: " + t.panel2 + "; border: 1px solid " + t.line + "; }\n";
    css += "QMenu::item:selected { background: " + t.red_dark + "; }\n";
    css += "QStatusBar { background: " + t.sidebar + "; color: " + t.muted + "; }\n";
    css += "QLabel#Toast { background: " + t.toast_bg + "; color: " + t.text +
           "; border: 1px solid " + t.toast_border + "; border-radius: 7px; padding: 9px 14px; }\n";
    css += "QLabel#ToastError { background: " + t.toast_bg + "; color: #ffb4b4; "
           "border: 1px solid " + t.red + "; border-radius: 7px; padding: 9px 14px; }\n";
    return css;
}

}  // namespace casu::conv