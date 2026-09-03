from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QComboBox

from mpcasu_qt.theme import PALETTE, apply_dark_combo_popup, stylesheet


def test_combo_popup_uses_explicit_dark_palette_and_selection():
    app = QApplication.instance() or QApplication([])
    combo = QComboBox()
    combo.addItems(["Continuous", "Time", "Track", "Tags"])
    apply_dark_combo_popup(combo)

    palette = combo.view().palette()
    assert palette.color(QPalette.Active, QPalette.Base).name() == PALETTE.input_bg
    assert palette.color(QPalette.Active, QPalette.Text).name() == PALETTE.text
    assert palette.color(QPalette.Active, QPalette.Highlight).name() == PALETTE.accent_dim
    assert palette.color(QPalette.Active, QPalette.HighlightedText).name() == PALETTE.text_on_accent
    assert PALETTE.input_bg in combo.view().styleSheet()
    assert PALETTE.accent_dim in combo.view().styleSheet()
    assert "QComboBox QAbstractItemView::item:selected" in stylesheet()

    combo.deleteLater()
    assert app is not None
