"""Regression checks for the single native MPCASU player window."""

from pathlib import Path


def test_native_sibling_policy_is_applied_before_qapplication_creation():
    source = (Path(__file__).parents[1] / "mpcasu_qt" / "app.py").read_text(
        encoding="utf-8")
    policy = "QApplication.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)"
    creation = "app = QApplication(sys.argv)"
    assert source.count(policy) == 1
    assert source.index(policy) < source.index(creation)
