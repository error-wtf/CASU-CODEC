"""Static lifecycle contracts for the native Windows YouTube adapter."""

from pathlib import Path


SOURCE = (Path(__file__).parents[1] / "win-release" / "apps" / "mpcasu"
          / "main_window.cpp").read_text(encoding="utf-8")


def _function(name: str, next_name: str) -> str:
    start = SOURCE.index(f"void MainWindow::{name}")
    end = SOURCE.index(f"void MainWindow::{next_name}", start)
    return SOURCE[start:end]


def test_windows_stop_invalidates_resolver_and_closes_consumer_before_proxy():
    body = _function("stop_playback()", "open_backend_and_play")
    assert "++resolve_generation_;" in body
    assert body.index("controller_->close();") < body.index("yt_proxy_->stop();")


def test_windows_backend_open_failure_stops_youtube_transport():
    body = _function("open_backend_and_play", "open_network_source")
    assert body.count("if (yt_proxy_) yt_proxy_->stop();") == 2
