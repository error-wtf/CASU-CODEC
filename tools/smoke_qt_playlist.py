# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Qt playlist pane smoke — expandable playlists, editing, save/load."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="mpcasu-qt-pl-")

from PySide6.QtWidgets import QApplication  # noqa: E402
from mpcasu_qt.main_window import MainWindow  # noqa: E402
from casu.playlist import PlaylistModel, save_playlist_file  # noqa: E402

issues: list[str] = []


def check(name: str, ok: bool):
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    if not ok:
        issues.append(name)


def main() -> int:
    app = QApplication([])
    work = Path(tempfile.mkdtemp(prefix="mpcasu-pl-"))
    media_a = work / "alpha.mp3"; media_a.write_bytes(b"ID3fake")
    media_b = work / "beta.mp4"; media_b.write_bytes(b"fake")
    playlist = work / "radio.m3u"
    save_playlist_file(playlist, PlaylistModel([media_a, media_b,
                                                "https://ice.bassdrive.net/stream"]))

    window = MainWindow()
    window.show()
    app.processEvents()

    window.add_files([media_a, playlist, media_b])
    app.processEvents()
    tree = window._playlist_pane.tree
    check("queue shows 3 top-level items", tree.topLevelItemCount() == 3)
    check("playlist entry is expandable", tree.topLevelItem(1).childCount() >= 1)

    tree.topLevelItem(1).setExpanded(True)
    app.processEvents()
    check("playlist expanded to 3 children (2 files + 1 stream)",
          tree.topLevelItem(1).childCount() == 3)
    labels = [tree.topLevelItem(1).child(i).text(0)
              for i in range(tree.topLevelItem(1).childCount())]
    check("children carry badges", all(label.startswith("[") for label in labels))

    played: list[str] = []
    window._on_queue_child_play = lambda source: played.append(source)
    window._playlist_pane.childPlayRequested.emit("https://ice.bassdrive.net/stream")
    check("child activation emits play request",
          played == ["https://ice.bassdrive.net/stream"])

    target = work / "saved.m3u"
    save_playlist_file(target, window.playlist_model)
    check("queue saveable as M3U", target.is_file()
          and "#EXTM3U" in target.read_text(encoding="utf-8"))
    target_pls = work / "saved.pls"
    save_playlist_file(target_pls, window.playlist_model)
    check("queue saveable as PLS", "[playlist]" in target_pls.read_text(encoding="utf-8"))

    window._apply_queue_order([str(media_b), str(playlist), str(media_a)])
    check("drag-reorder applied to model",
          [Path(str(p)).name for p in window.playlist_model.items]
          == ["beta.mp4", "radio.m3u", "alpha.mp3"])

    window._on_playlist_remove([0])
    check("remove edits queue", len(window.playlist_model) == 2)

    window._on_playlist_remove([])
    check("clear empties queue", len(window.playlist_model) == 0)

    window.close()
    app.processEvents()
    print(f"smoke_qt_playlist: {'PASS' if not issues else 'FAIL'} ({len(issues)} issues)")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
