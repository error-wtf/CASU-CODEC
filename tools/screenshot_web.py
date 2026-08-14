# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Screenshot driver for the web-casu player (headless Chromium)."""
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "screenshots" / "web-casu.png"


def main() -> int:
    server = subprocess.Popen(
        ["/usr/bin/python3", str(REPO / "web_casu.py"), "--port", "8895", "--no-browser"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)
    code = 0
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1560, "height": 900})
            page.goto("http://127.0.0.1:8895/web/", timeout=30_000)
            page.wait_for_selector("#queue", timeout=15_000)
            m3u = REPO / "test_media" / "demo_playlist.m3u"
            media = REPO / "test_media" / "demo_clip.mp4"
            page.set_input_files("#file-input", [str(m3u), str(media)])
            page.wait_for_timeout(1500)
            page.click("#queue li.queue-group")
            page.wait_for_timeout(400)
            page.screenshot(path=str(OUT))
            browser.close()
        print(f"saved {OUT}")
    except Exception as exc:
        print(f"web screenshot failed: {exc}")
        code = 1
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
