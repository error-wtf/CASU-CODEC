# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Web acceptance matrix — real browser E2E against the INSTALLED web-casu.

Run:  python3 tools/acceptance_web.py   (needs playwright chromium)
"""
from __future__ import annotations

import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "test_media"
PORT = 8899
HTTP_PORT = 8898

RESULTS: list[tuple[str, bool]] = []


def check(name: str, ok: bool):
    RESULTS.append((name, bool(ok)))
    print(f"[{'OK' if ok else 'FAIL'}] {name}", flush=True)


class _Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(MEDIA), **kwargs)

    def log_message(self, *args):
        pass


class _Server(socketserver.TCPServer):
    allow_reuse_address = True


def main() -> int:
    httpd = _Server(("127.0.0.1", HTTP_PORT), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    executable = os.environ.get("WEB_CASU_EXECUTABLE")
    command = ([executable] if executable else [sys.executable, str(ROOT / "web_casu.py")])
    server = subprocess.Popen(
        [*command, "--no-browser", "--port", str(PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1560, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text)
                    if m.type == "error" and "Failed to load resource" not in m.text else None)
            page.goto(f"http://127.0.0.1:{PORT}/web/")
            page.wait_for_selector("#queue-open", timeout=10000)
            try:
                page.wait_for_function(
                    "() => document.querySelector('#queue-open').onclick !== null",
                    timeout=5000)
            except Exception as exc:
                scripts = page.eval_on_selector_all(
                    "script[src]", "nodes => nodes.map(node => node.src)")
                raise RuntimeError(
                    f"web application did not bind input handlers; "
                    f"scripts={scripts}; browser_errors={errors}") from exc

            # choose files -> queue -> playback
            with page.expect_file_chooser() as fc:
                page.click("#queue-open")
            fc.value.set_files([str(MEDIA / "demo_clip.mp4")])
            page.wait_for_timeout(1500)
            check("choose files queues item",
                  page.eval_on_selector_all("#queue li", "e=>e.length") >= 1)
            t0 = time.time()
            advanced = False
            while time.time() - t0 < 15:
                cur = page.evaluate("document.getElementById('media').currentTime")
                if cur > 1.0:
                    advanced = True
                    break
                page.wait_for_timeout(500)
            check("file playback clock advances", advanced)

            # video centered inside stage
            geo = page.evaluate("""() => {
                const stage = document.querySelector('.stage').getBoundingClientRect();
                const media = document.getElementById('media').getBoundingClientRect();
                return {sx: stage.x + stage.width/2, sy: stage.y + stage.height/2,
                        mx: media.x + media.width/2, my: media.y + media.height/2,
                        inside: media.left >= stage.left - 2 && media.right <= stage.right + 2 &&
                                media.top >= stage.top - 2 && media.bottom <= stage.bottom + 2};
            }""")
            check("video centered in stage",
                  geo["inside"] and abs(geo["sx"] - geo["mx"]) < 8 and abs(geo["sy"] - geo["my"]) < 8)

            # repeated selection / add more
            with page.expect_file_chooser() as fc:
                page.click("#add-more")
            fc.value.set_files([str(MEDIA / "lino_casu_error.mp3")])
            page.wait_for_timeout(800)
            check("add more appends", page.eval_on_selector_all("#queue li", "e=>e.length") >= 2)

            # cancel chooser leaves no dead state
            with page.expect_file_chooser() as fc:
                page.click("#queue-open")
            fc.value.set_files([])
            page.wait_for_timeout(400)
            with page.expect_file_chooser() as fc:
                page.click("#queue-open")
            fc.value.set_files([str(MEDIA / "demo.mp5")])
            page.wait_for_timeout(800)
            check("chooser cancel then reopen works",
                  page.eval_on_selector_all("#queue li", "e=>e.length") >= 3)

            # playlist expansion + child playback
            with page.expect_file_chooser() as fc:
                page.click("#queue-open")
            fc.value.set_files([str(MEDIA / "demo_playlist.m3u")])
            page.wait_for_timeout(1200)
            groups = page.eval_on_selector_all("#queue li.queue-group", "e=>e.length")
            expanded = page.eval_on_selector_all("#queue li.queue-group.open", "e=>e.length")
            check("playlist group visible and expanded", groups >= 1 and expanded >= 1)
            children = page.eval_on_selector_all("#queue li.queue-group.open ~ li", "e=>e.length")
            check("playlist children visible", children >= 1)

            # URL dialog: cancel + reopen + valid http url
            page.click("#queue-url")
            page.wait_for_selector("#url-dialog[open]", timeout=5000)
            page.click("#url-dialog button[value='cancel']")
            page.wait_for_timeout(300)
            check("url dialog cancel closes",
                  page.evaluate("!document.getElementById('url-dialog').open"))
            page.click("#queue-url")
            page.wait_for_selector("#url-dialog[open]", timeout=5000)
            page.fill("#url-value", f"http://127.0.0.1:{HTTP_PORT}/lino_casu_error.mp3")
            page.click("#url-confirm")
            page.wait_for_timeout(500)
            check("url dialog closes after open",
                  page.evaluate("!document.getElementById('url-dialog').open"))
            li = page.eval_on_selector_all("#queue li", "e=>e.length")
            check("http url queued", li >= 4)
            page.eval_on_selector_all("#queue li", "e=>{e[e.length-1].click()}")
            t0 = time.time()
            advanced = False
            while time.time() - t0 < 15:
                cur = page.evaluate("document.getElementById('media').currentTime")
                if cur > 1.0:
                    advanced = True
                    break
                page.wait_for_timeout(500)
            check("http stream clock advances", advanced)

            # malformed url surfaces error, no crash
            page.click("#queue-url")
            page.wait_for_selector("#url-dialog[open]", timeout=5000)
            page.fill("#url-value", "not a url")
            page.click("#url-confirm")
            page.wait_for_timeout(400)
            still_open = page.evaluate("document.getElementById('url-dialog').open")
            page.click("#url-dialog button[value='cancel']")
            page.wait_for_timeout(300)
            closed = page.evaluate("!document.getElementById('url-dialog').open")
            check("malformed url rejected and dialog recoverable",
                  still_open and closed)

            # fullscreen toggle both ways
            page.click("#fullscreen")
            page.wait_for_timeout(600)
            in_fs = page.evaluate("!!document.fullscreenElement")
            page.click("#fullscreen")
            page.wait_for_timeout(600)
            out_fs = page.evaluate("!!document.fullscreenElement")
            check("fullscreen enters and exits", in_fs and not out_fs)

            # visualizer for audio-only
            page.evaluate("""() => {
                const items = [...document.querySelectorAll('#queue li')];
                const mp3 = items.find(li => li.textContent.includes('lino_casu_error'));
                if (mp3) mp3.click();
            }""")
            t0 = time.time()
            viz = False
            while time.time() - t0 < 12:
                viz = page.evaluate("!document.getElementById('viz-canvas').hidden")
                if viz:
                    break
                page.wait_for_timeout(500)
            check("visualizer visible for audio", viz)

            # spotify honesty: resolve must refuse with notice
            resp = page.evaluate("""async () => {
                const r = await fetch('/api/resolve', {method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({url:'https://open.spotify.com/track/0VjIjW4GlUZAMYB2vXMi3b'})});
                return {ok: r.ok, body: await r.json()};
            }""")
            check("spotify resolve refuses honestly",
                  not resp["ok"] and "Spotify" in resp["body"].get("error", ""))

            check("no uncaught js exceptions", not errors)
            if errors:
                print("JS ERRORS:", errors[:5], flush=True)
            browser.close()
    finally:
        server.terminate()
        httpd.shutdown()
    failed = [n for n, ok in RESULTS if not ok]
    print(f"ACCEPTANCE WEB: {len(RESULTS) - len(failed)}/{len(RESULTS)}", flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
