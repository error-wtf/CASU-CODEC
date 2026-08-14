"""Headless smoke for Session-4 upgrades: hero, toast, badges, MP5 playback."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mpcasu_player
from casu import mp5


def make_clip(target: Path) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         "testsrc=duration=3:size=160x120:rate=10",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
         "-shortest", str(target)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return target


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="casu-smoke-"))
    clip = make_clip(tmp / "smoke.mp4")
    mp5_file = mp5.convert_to_mp5(clip, tmp / "smoke.mp5")
    assert mp5.verify_mp5(mp5_file) == [], "MP5 must verify clean"

    app = mpcasu_player.MPCASUPlayer()
    app.update_idletasks()
    app.update()

    app._draw_visualizer()
    app.update()
    assert app._empty_cta_bbox is not None, "empty-state hero must set CTA"
    viz_items = app.canvas.find_withtag("viz")
    assert len(viz_items) >= 5, f"hero should draw several items, got {len(viz_items)}"
    print("OK empty-state hero:", len(viz_items), "items, CTA", app._empty_cta_bbox)

    app._toast("Smoke toast")
    app.update()
    assert app._toast_label.winfo_ismapped(), "toast must be visible"
    print("OK toast visible")

    app.add_files([mp5_file])
    app.update()
    app.play_selected()
    deadline = time.time() + 15
    reached = 0.0
    while time.time() < deadline:
        app.update()
        if app.backend is not None:
            reached = max(reached, app.backend.position())
            if reached > 1.0:
                break
        time.sleep(0.2)
    badges = (app._format_badge, app._integrity_badge)
    print("OK badges:", badges)
    assert badges == ("MP5", "VERIFIED"), f"unexpected badges {badges}"
    print("OK MP5 playback position:", round(reached, 2), "s")
    assert reached > 1.0, "MP5 must play beyond 1 s"

    app._draw_visualizer()
    app.update()
    app._retire_backend()
    app.update()
    app._shutdown()
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
