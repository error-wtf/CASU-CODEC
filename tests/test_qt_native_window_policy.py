"""Regression checks for the single native MPCASU player window."""

from pathlib import Path


def test_native_sibling_policy_matches_verified_release_placement():
    """The verified v5.0.0 release applies the attribute AFTER app creation.

    Qt documents the attribute as pre-application-only, but the pre-app
    placement shipped in a later build regressed the embedded video
    surface on real desktops. This test pins the release placement so the
    policy cannot silently drift again.
    """
    source = (Path(__file__).parents[1] / "mpcasu_qt" / "app.py").read_text(
        encoding="utf-8")
    policy = "app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)"
    creation = "app = QApplication(sys.argv)"
    assert source.count(policy) == 1
    assert source.index(policy) > source.index(creation)


def test_desktop_visualizer_is_bounded_wave_only_at_30_fps():
    source = (Path(__file__).parents[1] / "mpcasu_qt" / "main_window.py").read_text(
        encoding="utf-8")
    assert "self._viz_timer.setInterval(33)" in source
    assert "points = max(64, min(128" in source
    assert "mode = \"off\" if settings.visualizer != \"off\" else \"waveform\"" in source
    assert "live_fft(" not in source
    assert "_paint_bottom_bars" not in source
