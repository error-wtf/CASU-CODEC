"""Session-4 web UX smoke: views, back button, queue scroll, stream proxy."""
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from playwright.sync_api import sync_playwright


def main() -> int:
    server = subprocess.Popen(
        ["/usr/bin/python3", str(REPO / "web_casu.py"), "--port", "8891", "--no-browser"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto("http://127.0.0.1:8891/web/", timeout=30_000)
            page.wait_for_selector("#queue", timeout=15_000)

            m3u = Path(tempfile.mkdtemp()) / "demo.m3u"
            m3u.write_text(
                "#EXTM3U\n"
                '#EXTINF:-1 tvg-id="a" group-title="Radio",Alpha FM\n'
                "http://127.0.0.1:8891/none1\n"
                '#EXTINF:-1 tvg-id="b" group-title="Radio",Beta FM\n'
                "http://127.0.0.1:8891/none2\n", encoding="utf-8")
            page.set_input_files("#file-input", [str(m3u)])
            page.wait_for_timeout(700)
            summary = page.text_content("#queue-summary")
            print("queue summary:", summary)
            assert "2/2" in summary, summary

            page.click("#open-playlist")
            page.wait_for_timeout(200)
            assert page.text_content("#view-title") == "PLAYLISTS"
            assert "2/2" in page.text_content("#queue-summary")

            page.click("#open-files")
            page.wait_for_timeout(200)
            assert "0/2" in page.text_content("#queue-summary"), "files view must filter streams out"

            page.click("#back-button")
            page.wait_for_timeout(200)
            assert page.text_content("#view-title") == "NOW PLAYING"
            assert "2/2" in page.text_content("#queue-summary")

            proxied = page.evaluate(
                "fetch('/api/stream-proxy?url=http%3A%2F%2F127.0.0.1%3A8891%2Fweb%2Fstyles.css')"
                ".then(r => r.status)")
            print("proxy self-fetch status:", proxied)
            assert proxied == 200

            browser.close()
        print("WEB NAV SMOKE OK")
        return 0
    finally:
        server.terminate()
        server.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
