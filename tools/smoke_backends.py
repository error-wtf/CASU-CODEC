"""Playback smoke across every backend path (Session 4)."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_CONFIG_HOME = tempfile.mkdtemp(prefix="casu-smoke-config-")
os.environ["XDG_CONFIG_HOME"] = _CONFIG_HOME

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mpcasu_player
from casu import mp5


def make_clip(target: Path, seconds: int = 3) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"testsrc=duration={seconds}:size=160x120:rate=10",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
         "-shortest", str(target)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return target


def play_until(app, path: Path, timeout: float = 15.0) -> float:
    app.add_files([path])
    app.update()
    index = len(app.playlist_model) - 1
    app.library.selection_clear(0, "end")
    app.library.selection_set(index)
    app.queue.selection_clear(0, "end")
    app.queue.selection_set(index)
    app.update()
    app.play_selected()
    deadline = time.time() + timeout
    reached = 0.0
    while time.time() < deadline:
        app.update()
        if app.backend is not None:
            reached = max(reached, app.backend.position())
            if reached > 1.0:
                break
        time.sleep(0.15)
    backend_name = type(app.backend).__name__ if app.backend else "None"
    app.stop()
    app.update()
    return reached, backend_name


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="casu-backend-smoke-"))
    clip = make_clip(tmp / "movie.mp4")

    # CASUNAT2 native container (packed fresh).
    nat2 = tmp / "movie.casu"
    subprocess.run([sys.executable, "-m", "casu", "pack-v2", str(clip),
                    "-o", str(nat2)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   cwd=str(Path(__file__).resolve().parent.parent))

    # MP5 enhanced container.
    mp5_file = mp5.convert_to_mp5(clip, tmp / "movie.mp5")

    app = mpcasu_player.MPCASUPlayer()
    app.update_idletasks()
    app.update()

    results = {}
    pos, backend = play_until(app, clip)
    results["MP4/LibVLC"] = (round(pos, 2), backend)
    pos, backend = play_until(app, nat2)
    results["CASUNAT2/Native"] = (round(pos, 2), backend)
    pos, backend = play_until(app, mp5_file)
    results["MP5/LegacyCasu"] = (round(pos, 2), backend)

    app._shutdown()
    for name, (pos, backend) in results.items():
        status = "OK " if pos > 1.0 else "FAIL"
        print(f"{status} {name}: pos={pos}s backend={backend}")
    assert all(pos > 1.0 for pos, _ in results.values()), "a backend path failed"
    print("ALL BACKEND PATHS OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
