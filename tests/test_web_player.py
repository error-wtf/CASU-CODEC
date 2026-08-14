from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


WEB = Path(__file__).resolve().parents[1] / "web"


def test_web_player_has_functional_control_surface():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    script = (WEB / "app.js").read_text(encoding="utf-8")
    for identifier in ("media", "youtube", "native-canvas", "native-subtitle",
                       "chapter-select", "file-input", "seek", "volume", "queue",
                       "open-url", "fullscreen", "video-track", "audio-track",
                       "subtitle-track", "open-epg", "epg-dialog", "epg-now"):
        assert f'id="{identifier}"' in html
    for behavior in ("addFiles", "parseCasu", "digestHex", "addPlaylist",
                     "localFileRole",
                     "requestPictureInPicture", "requestFullscreen",
                     "transcodeFallback", "addEpg", "epgFor", "renderEpgDialog",
                     "transcodeFallback", "/api/transcode-file",
                     "/api/transcode-url"):
        assert behavior in script
    for bound in ("MAX_PLAYLIST_BYTES", "MAX_PLAYLIST_ENTRIES",
                  "MAX_PLAYLIST_LINE"):
        assert bound in script
    native = (WEB / "casu-native.js").read_text(encoding="utf-8")
    for behavior in ("CASUNAT2 integrity verification failed", "applyTile",
                     "DecompressionStream", "AudioContext", "ImageData",
                     "onSubtitle", "this.chapters", "yieldToBrowser",
                     "this.offscreen", "while(low<high)", "bitmapBlock",
                     "trackOptions", "selectTrack"):
        assert behavior in native


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js unavailable")
def test_web_player_javascript_is_syntactically_valid():
    for script in ("app.js", "casu-native.js", "native-smoke.js"):
        subprocess.run(["node", "--check", str(WEB / script)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
