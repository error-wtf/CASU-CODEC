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
    # media_a and media_b are referenced by `playlist`, so Choose-files must
    # NOT add them again as separate top-level rows — only the playlist group
    # (with its children) is queued. This prevents double-loading.
    check("playlist added as single top-level group (no double-load)",
          tree.topLevelItemCount() == 1)
    check("playlist entry is expandable", tree.topLevelItem(0).childCount() >= 1)

    tree.topLevelItem(0).setExpanded(True)
    app.processEvents()
    check("playlist expanded to 3 children (2 files + 1 stream)",
          tree.topLevelItem(0).childCount() == 3)
    badges = [tree.topLevelItem(0).child(i).text(1)
              for i in range(tree.topLevelItem(0).childCount())]
    check("children carry badges", all(bool(b.strip()) for b in badges))

    # A file that is NOT referenced by a playlist is still added normally.
    extra = work / "extra.mp3"; extra.write_bytes(b"ID3fake")
    window.add_files([extra])
    app.processEvents()
    check("unreferenced file added as its own row",
          tree.topLevelItemCount() == 2)

    played: list[str] = []
    window._on_queue_child_play = lambda source: played.append(source)
    window._playlist_pane.childPlayRequested.emit("https://ice.bassdrive.net/stream")
    check("child activation emits play request",
          played == ["https://ice.bassdrive.net/stream"])

    # Playing a playlist must start from its FIRST track, and next/previous
    # must step through the playlist's children (not jump or get stuck).
    adv: list[str] = []
    real_play_selected = window.play_selected
    def record_play(path=None):
        sel = path if path is not None else window.selected_path()
        if sel is not None:
            window.current = Path(sel)
            adv.append(str(Path(sel).resolve()))
    window.play_selected = record_play
    window._play_playlist_row(0)
    app.processEvents()
    check("play starts from playlist track 1",
          adv and Path(adv[0]) == media_a.resolve())
    window.play_next(automatic=True); app.processEvents()
    check("next goes to playlist track 2",
          len(adv) >= 2 and Path(adv[1]) == media_b.resolve())
    window.play_previous(); app.processEvents()
    check("previous returns to playlist track 1",
          len(adv) >= 3 and Path(adv[2]) == media_a.resolve())
    window.play_selected = real_play_selected

    target = work / "saved.m3u"
    save_playlist_file(target, window.playlist_model)
    check("queue saveable as M3U", target.is_file()
          and "#EXTM3U" in target.read_text(encoding="utf-8"))
    target_pls = work / "saved.pls"
    save_playlist_file(target_pls, window.playlist_model)
    check("queue saveable as PLS", "[playlist]" in target_pls.read_text(encoding="utf-8"))

    order = [str(extra), str(playlist)]
    window._apply_queue_order(order)
    check("drag-reorder applied to model",
          [str(p) for p in window.playlist_model.items] == order)

    window._on_playlist_remove([0])
    check("remove edits queue", len(window.playlist_model) == 1)

    window._on_playlist_remove([])
    check("clear empties queue", len(window.playlist_model) == 0)

    window.close()
    app.processEvents()
    print(f"smoke_qt_playlist: {'PASS' if not issues else 'FAIL'} ({len(issues)} issues)")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
