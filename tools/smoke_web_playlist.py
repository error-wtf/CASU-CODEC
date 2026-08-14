# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Web player smoke: expandable playlist groups + save-as-M3U."""
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from playwright.sync_api import sync_playwright


def main() -> int:
    issues = []
    server = subprocess.Popen(
        ["/usr/bin/python3", str(REPO / "web_casu.py"), "--port", "8893", "--no-browser"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto("http://127.0.0.1:8893/web/", timeout=30_000)
            page.wait_for_selector("#queue", timeout=15_000)

            work = Path(tempfile.mkdtemp())
            m3u = work / "radio.m3u"
            m3u.write_text(
                "#EXTM3U\n"
                '#EXTINF:-1 tvg-id="a" group-title="Radio",Alpha FM\n'
                "http://127.0.0.1:8893/none1\n"
                '#EXTINF:-1 tvg-id="b" group-title="Radio",Beta FM\n'
                "http://127.0.0.1:8893/none2\n", encoding="utf-8")
            page.set_input_files("#file-input", [str(m3u)])
            page.wait_for_selector("#queue li.queue-group", timeout=10_000)

            header = page.locator("#queue li.queue-group").first
            if "radio.m3u" not in header.inner_text():
                issues.append("group header missing playlist name")
            if "2 entries" not in header.inner_text():
                issues.append("group header missing entry count")

            entries = page.locator("#queue li:not(.queue-group)").count()
            if entries != 2:
                issues.append(f"expected 2 expanded entries, saw {entries}")

            header.click()
            time.sleep(0.3)
            entries_collapsed = page.locator("#queue li:not(.queue-group)").count()
            if entries_collapsed != 0:
                issues.append(f"collapse failed, still {entries_collapsed} entries")

            header.click()
            time.sleep(0.3)
            if page.locator("#queue li:not(.queue-group)").count() != 2:
                issues.append("re-expand failed")

            with page.expect_download(timeout=10_000) as download_info:
                page.click("#save-pl")
            download = download_info.value
            target = work / download.suggested_filename
            download.save_as(str(target))
            text = target.read_text(encoding="utf-8")
            if "#EXTM3U" not in text or "none1" not in text or "none2" not in text:
                issues.append("saved M3U incomplete")

            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    for issue in issues:
        print(f"[FAIL] {issue}")
    if not issues:
        print("queue group header + expand/collapse + save-as-M3U OK")
        print("WEB PLAYLIST SMOKE OK")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
