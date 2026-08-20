"""Verhaltenstests der Playlist-/Queue-Reparatur (Linux Qt, headless).

Akzeptanzkriterien (v3.0):
- Play auf eine Playlist (auf- ODER eingeklappt) spielt die GANZE Playlist
  und führt danach linear durch die gemischte Queue (Dateien + URLs +
  weitere Playlists) — kanonisches Ergebnis A1, A2, X, B1, B2.
- Die Playlist-GRUPPEN bleiben dabei immer sichtbar: sie werden beim Spielen
  NIE in ihre Einträge aufgelöst, sondern nur logisch durchlaufen.
- Playlists lassen sich in der Queue hin und her verschieben (ganze Gruppe).
- Das Auf-/Zuklappen der Playlist-Gruppen beeinflusst die Wiedergabe nie.
- Dateien/URLs werden wie Playlists in die Queue gequeuet und können in
  vorhandene Playlists gemerged werden (einzeln + Mehrfach-Selektion);
  Kinder können aus einer Playlist entfernt oder in eine andere verschoben
  werden ("rein und raus").
- Komplette Playlists lassen sich in andere Playlists mergen; Reihenfolge
  und Selektion bleiben erhalten.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

pytest.importorskip("PySide6")

import PySide6.QtWidgets as QW  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from casu.playlist import PlaylistModel, load_playlist_file, save_playlist_file  # noqa: E402
from mpcasu_qt.main_window import MainWindow, PlaylistPane  # noqa: E402

NETWORK_PREFIXES = ("http://", "https://", "rtsp://", "rtmp://")


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture()
def window(qapp, tmp_path, monkeypatch):
    """MainWindow headless mit Playback-Stubs: getestet wird die
    Queue-/Playlist-Logik, nicht die Audio-Pipeline."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    win = MainWindow()
    played: list[str] = []
    win._played = played

    def fake_play_selected(path=None):
        if path is None:
            # Mirror the real play_selected: a selected playlist child plays
            # through the group-resolution path.
            child = win._playlist_pane.selected_child()
            if child is not None:
                win._on_queue_child_play(child)
                return
            path = win.selected_path()
            if path is None:
                return
        text = str(path)
        if Path(text).is_file() and Path(text).suffix.lower() in PlaylistPane.PLAYLIST_SUFFIXES:
            win._play_playlist_full(Path(text))
            return
        played.append(text)
        win.current = None if text.startswith(NETWORK_PREFIXES) else Path(text)

    def fake_resolve(source, *, display_label=None):
        played.append(str(source))
        win.current = None

    win.play_selected = fake_play_selected
    win._resolve_and_open_external_source = fake_resolve
    yield win
    win.close()


def _media(tmp_path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(b"media")
    return path


def _make_playlist(tmp_path, name: str, entries) -> Path:
    target = tmp_path / name
    save_playlist_file(target, PlaylistModel(entries))
    return target


def _items(window) -> list[str]:
    return [str(item) for item in window.playlist_model.items]


def test_canonical_mixed_combination_plays_through_in_order(window, tmp_path):
    """Playlist A + Datei X + Playlist B in EINER Queue: Play auf A (row 0)
    spielt A1, A2, dann X, dann B1, B2 — nie 'entweder Playlist oder Datei'.
    Die Playlist-Gruppen bleiben dabei sichtbar (Modell wird nie aufgelöst)."""
    a1 = _media(tmp_path, "a1.mp3")
    a2 = _media(tmp_path, "a2.mp3")
    x = _media(tmp_path, "x.mp4")
    b1 = _media(tmp_path, "b1.mp3")
    b2 = _media(tmp_path, "b2.mp3")
    plA = _make_playlist(tmp_path, "A.m3u", [a1, a2])
    plB = _make_playlist(tmp_path, "B.m3u", [b1, b2])

    window.add_files([plA, x, plB])
    assert _items(window) == [str(plA.resolve()), str(x.resolve()), str(plB.resolve())]

    # Play auf die (eingeklappte) Playlist A: Gruppe bleibt im Modell!
    window._play_playlist_row(0)
    assert _items(window) == [str(plA.resolve()), str(x.resolve()), str(plB.resolve())]
    assert window._played == [str(a1.resolve())]

    window.play_next(automatic=True)
    assert window._played[-1] == str(a2.resolve())
    window.play_next(automatic=True)
    assert window._played[-1] == str(x.resolve())

    # Beim Erreichen der Playlist-B-Zeile läuft die Wiedergabe durch deren
    # Einträge weiter — die Gruppe bleibt weiterhin sichtbar.
    window.play_next(automatic=True)
    assert _items(window) == [str(plA.resolve()), str(x.resolve()), str(plB.resolve())]
    assert window._played[-1] == str(b1.resolve())
    window.play_next(automatic=True)
    assert window._played[-1] == str(b2.resolve())
    # …und die Kombination endet sauber (kein Sprung zurück zu A1).
    window.play_next(automatic=True)
    assert window._played[-1] == str(b2.resolve())
    assert len(window.playlist_model) == 3  # Gruppen nie aufgelöst


def test_collapsed_and_expanded_playlist_play_identically(window, tmp_path):
    """Auf-/Zuklappen darf die Wiedergabe nie bestimmen: Play liefert in
    beiden Zuständen exakt dieselbe Spielreihenfolge — und die Gruppe bleibt
    in beiden Fällen sichtbar."""
    a1 = _media(tmp_path, "a1.mp3")
    a2 = _media(tmp_path, "a2.mp3")
    x = _media(tmp_path, "x.mp4")
    plA = _make_playlist(tmp_path, "A.m3u", [a1, a2])

    window.add_files([plA, x])
    pane = window._playlist_pane
    top = pane.tree.topLevelItem(0)
    pane._on_collapsed(top)  # Playlist bleibt eingeklappt
    top.setExpanded(False)
    assert not top.isExpanded()

    window._play_playlist_row(0)
    assert _items(window) == [str(plA.resolve()), str(x.resolve())]
    assert window._played == [str(a1.resolve())]
    window.play_next(automatic=True)
    assert window._played[-1] == str(a2.resolve())
    window.play_next(automatic=True)
    assert window._played[-1] == str(x.resolve())

    # Identisches Verhalten bei aufgeklappter Playlist (frische Queue).
    window.playlist_model.clear()
    window._invalidate_play_seq()
    window._played.clear()
    window.add_files([plA, x])
    top = pane.tree.topLevelItem(0)
    pane._expand_playlist_item(top)
    top.setExpanded(True)
    window._play_playlist_row(0)
    assert _items(window) == [str(plA.resolve()), str(x.resolve())]
    assert window._played == [str(a1.resolve())]
    window.play_next(automatic=True)
    assert window._played[-1] == str(a2.resolve())
    window.play_next(automatic=True)
    assert window._played[-1] == str(x.resolve())


def test_playing_a_playlist_child_keeps_the_group_visible(window, tmp_path):
    """Doppelklick/Play auf ein Kind einer Playlist-Gruppe spielt genau
    dieses Kind; die Gruppe bleibt sichtbar, danach läuft die Wiedergabe
    linear durch die Queue weiter."""
    a1 = _media(tmp_path, "a1.mp3")
    a2 = _media(tmp_path, "a2.mp3")
    x = _media(tmp_path, "x.mp4")
    plA = _make_playlist(tmp_path, "A.m3u", [a1, a2])

    window.add_files([plA, x])
    window._on_queue_child_play(str(a2.resolve()))
    assert _items(window) == [str(plA.resolve()), str(x.resolve())]
    assert window._played[-1] == str(a2.resolve())
    window.play_next(automatic=True)
    assert window._played[-1] == str(x.resolve())
    window.play_next(automatic=True)
    assert window._played[-1] == str(x.resolve())  # Ende


def test_play_button_on_selected_child_plays_the_child(window, tmp_path):
    """Play-Button bei markiertem Kind (aufgeklappte Gruppe) spielt genau
    dieses Kind — die Gruppe bleibt sichtbar."""
    a1 = _media(tmp_path, "a1.mp3")
    a2 = _media(tmp_path, "a2.mp3")
    plA = _make_playlist(tmp_path, "A.m3u", [a1, a2])

    window.add_files([plA])
    pane = window._playlist_pane
    top = pane.tree.topLevelItem(0)
    pane._expand_playlist_item(top)
    pane.tree.setCurrentItem(top.child(1))
    window.play_selected()
    assert window._played[-1] == str(a2.resolve())
    assert _items(window) == [str(plA.resolve())]


def test_playlist_with_stream_url_plays_through(window, tmp_path):
    """Playlist mit lokalem Track + Stream-URL spielt komplett durch — die
    Gruppe bleibt sichtbar und die Wiedergabe endet nach der URL sauber."""
    a1 = _media(tmp_path, "a1.mp3")
    url = "https://ice.example/radio/stream"
    plA = _make_playlist(tmp_path, "A.m3u", [a1, url])

    window.add_files([plA])
    window._play_playlist_row(0)
    assert _items(window) == [str(plA.resolve())]
    assert window._played == [str(a1.resolve())]
    window.play_next(automatic=True)
    assert window._played[-1] == url
    window.play_next(automatic=True)
    assert window._played[-1] == url  # Ende nach dem Stream


def test_add_url_queues_and_combines_with_playlist(window, tmp_path):
    """Eine per URL-Add gequeuete Stream-URL kombiniert mit einer Playlist:
    Play auf die Playlist spielt Playlist UND URL hintereinander."""
    a1 = _media(tmp_path, "a1.mp3")
    a2 = _media(tmp_path, "a2.mp3")
    url = "https://ice.example/radio/stream"
    plA = _make_playlist(tmp_path, "A.m3u", [a1, a2])

    window.add_files([plA, url])
    assert _items(window) == [str(plA.resolve()), url]
    window._play_playlist_row(0)
    assert _items(window) == [str(plA.resolve()), url]
    assert window._played == [str(a1.resolve())]
    window.play_next(automatic=True)
    assert window._played[-1] == str(a2.resolve())
    window.play_next(automatic=True)
    assert window._played[-1] == url
    window.play_next(automatic=True)
    assert window._played[-1] == url  # Ende


def test_merge_files_urls_and_playlist_into_existing_playlist(
        window, tmp_path, monkeypatch):
    """Mehrfach-Selektion (Datei + URL + komplette Playlist) wird in eine
    vorhandene Playlist gemerged — Reihenfolge und Selektion bleiben sichtbar."""
    a = _media(tmp_path, "a.mp3")
    x = _media(tmp_path, "x.mp4")
    b1 = _media(tmp_path, "b1.mp3")
    b2 = _media(tmp_path, "b2.mp3")
    url = "https://example.com/live/stream.m3u8"
    plA = _make_playlist(tmp_path, "A.m3u", [a])
    plB = _make_playlist(tmp_path, "B.m3u", [b1, b2])

    window.add_files([plA, x, url, plB])
    assert _items(window) == [str(plA.resolve()), str(x.resolve()), url,
                              str(plB.resolve())]

    def fake_get_item(parent, title, label, items, current=0, editable=False):
        return str(plA.resolve()), True

    monkeypatch.setattr(QW.QInputDialog, "getItem", staticmethod(fake_get_item))
    # x (Row 1), URL (Row 2) und die komplette Playlist B (Row 3) mergen.
    window._on_playlist_merge([1, 2, 3])

    restored = load_playlist_file(plA)
    assert [str(i) for i in restored.items] == [
        str(a.resolve()), str(x.resolve()), url,
        str(b1.resolve()), str(b2.resolve())]
    # Selektion bleibt nach dem Re-Render erhalten (Row 1 = x).
    assert window._playlist_pane.selected_row() == 1


def test_merge_playlist_children_into_playlist(window, tmp_path, monkeypatch):
    """Auch einzelne Kinder (aus aufgeklappter Gruppe) lassen sich mergen —
    der Kontextmenü-Pfad sendet URLs statt Row-Indizes."""
    a = _media(tmp_path, "a.mp3")
    b1 = _media(tmp_path, "b1.mp3")
    b2 = _media(tmp_path, "b2.mp3")
    plA = _make_playlist(tmp_path, "A.m3u", [a])
    plB = _make_playlist(tmp_path, "B.m3u", [b1, b2])

    window.add_files([plA, plB])

    def fake_get_item(parent, title, label, items, current=0, editable=False):
        return str(plA.resolve()), True

    monkeypatch.setattr(QW.QInputDialog, "getItem", staticmethod(fake_get_item))
    # Kinder von B direkt (als str-URLs) mergen.
    window._on_playlist_merge([str(b1.resolve()), str(b2.resolve())])
    restored = load_playlist_file(plA)
    assert [str(i) for i in restored.items] == [
        str(a.resolve()), str(b1.resolve()), str(b2.resolve())]


def test_save_queue_flattens_playlist_groups(window, tmp_path, monkeypatch):
    """Save speichert die gemischte Queue flach (echte Einträge, keine
    Playlist-Datei-Referenzen)."""
    a1 = _media(tmp_path, "a1.mp3")
    a2 = _media(tmp_path, "a2.mp3")
    x = _media(tmp_path, "x.mp4")
    plA = _make_playlist(tmp_path, "A.m3u", [a1, a2])

    window.add_files([plA, x])
    target = tmp_path / "out.m3u"

    def fake_exec(self):
        return True

    def fake_files(self):
        return [str(target)]

    def fake_filter(self):
        return "M3U playlist (*.m3u)"

    monkeypatch.setattr(QW.QFileDialog, "exec", fake_exec)
    monkeypatch.setattr(QW.QFileDialog, "selectedFiles", fake_files)
    monkeypatch.setattr(QW.QFileDialog, "selectedNameFilter", fake_filter)
    window.save_playlist()

    saved = load_playlist_file(target)
    assert [str(i) for i in saved.items] == [
        str(a1.resolve()), str(a2.resolve()), str(x.resolve())]
    assert str(plA.resolve()) not in [str(i) for i in saved.items]


def test_playlist_groups_can_be_moved_up_and_down(window, tmp_path):
    """Mehrere Playlists in einer Queue lassen sich hin und her verschieben:
    die ganze Gruppe wandert als EIN Eintrag, die Wiedergabe folgt der neuen
    Reihenfolge — Gruppen werden nie aufgelöst."""
    a1 = _media(tmp_path, "a1.mp3")
    a2 = _media(tmp_path, "a2.mp3")
    x = _media(tmp_path, "x.mp4")
    b1 = _media(tmp_path, "b1.mp3")
    b2 = _media(tmp_path, "b2.mp3")
    plA = _make_playlist(tmp_path, "A.m3u", [a1, a2])
    plB = _make_playlist(tmp_path, "B.m3u", [b1, b2])

    window.add_files([plA, x, plB])
    assert _items(window) == [str(plA.resolve()), str(x.resolve()), str(plB.resolve())]

    # Playlist B (Row 2) nach oben, dann Playlist A (Row 0) nach unten.
    window._on_playlist_move(-1, [2])
    assert _items(window) == [str(plA.resolve()), str(plB.resolve()), str(x.resolve())]
    window._on_playlist_move(1, [0])
    assert _items(window) == [str(plB.resolve()), str(plA.resolve()), str(x.resolve())]

    # Wiedergabe folgt der neuen Reihenfolge: B1, B2, A1, A2, X.
    window._played.clear()
    window._play_playlist_row(0)
    assert _items(window) == [str(plB.resolve()), str(plA.resolve()), str(x.resolve())]
    assert window._played == [str(b1.resolve())]
    window.play_next(automatic=True)
    assert window._played[-1] == str(b2.resolve())
    window.play_next(automatic=True)
    assert window._played[-1] == str(a1.resolve())
    window.play_next(automatic=True)
    assert window._played[-1] == str(a2.resolve())
    window.play_next(automatic=True)
    assert window._played[-1] == str(x.resolve())
    window.play_next(automatic=True)
    assert window._played[-1] == str(x.resolve())  # Ende


def test_remove_child_from_playlist_keeps_group_visible(window, tmp_path):
    """'Remove from playlist': ein Kind wird aus der Playlist-DATEI entfernt,
    die Gruppe bleibt aber als Zeile in der Queue sichtbar."""
    a1 = _media(tmp_path, "a1.mp3")
    a2 = _media(tmp_path, "a2.mp3")
    x = _media(tmp_path, "x.mp4")
    plA = _make_playlist(tmp_path, "A.m3u", [a1, a2])

    window.add_files([plA, x])
    window._on_child_remove_from_playlist([str(a1.resolve())])

    restored = load_playlist_file(plA)
    assert [str(i) for i in restored.items] == [str(a2.resolve())]
    # Gruppe bleibt sichtbar, Modell unverändert.
    assert _items(window) == [str(plA.resolve()), str(x.resolve())]
    # Wiedergabe nutzt den neuen Dateiinhalt.
    window._played.clear()
    window._play_playlist_row(0)
    assert window._played == [str(a2.resolve())]
    window.play_next(automatic=True)
    assert window._played[-1] == str(x.resolve())


def test_move_child_to_other_playlist(window, tmp_path, monkeypatch):
    """'Move to playlist': ein Kind wandert von Playlist B in Playlist A
    (raus aus B, rein in A) — beide Gruppen bleiben sichtbar."""
    a = _media(tmp_path, "a.mp3")
    b1 = _media(tmp_path, "b1.mp3")
    b2 = _media(tmp_path, "b2.mp3")
    plA = _make_playlist(tmp_path, "A.m3u", [a])
    plB = _make_playlist(tmp_path, "B.m3u", [b1, b2])

    window.add_files([plA, plB])

    def fake_get_item(parent, title, label, items, current=0, editable=False):
        assert title == "Move to playlist"
        return str(plA.resolve()), True

    monkeypatch.setattr(QW.QInputDialog, "getItem", staticmethod(fake_get_item))
    window._on_child_move_to_playlist([str(b1.resolve())])

    restored_a = load_playlist_file(plA)
    restored_b = load_playlist_file(plB)
    assert [str(i) for i in restored_a.items] == [str(a.resolve()), str(b1.resolve())]
    assert [str(i) for i in restored_b.items] == [str(b2.resolve())]
    # Beide Gruppen bleiben sichtbar.
    assert _items(window) == [str(plA.resolve()), str(plB.resolve())]


def test_multi_selection_move_moves_all_selected_rows_together(window, tmp_path):
    """Strg/Shift-Mehrfachauswahl (lose Dateien + Playlist-Gruppen gemischt)
    wandert als Block — Wiedergabe folgt der neuen Reihenfolge."""
    a1 = _media(tmp_path, "a1.mp3")
    x = _media(tmp_path, "x.mp4")
    y = _media(tmp_path, "y.mp4")
    b1 = _media(tmp_path, "b1.mp3")
    b2 = _media(tmp_path, "b2.mp3")
    plA = _make_playlist(tmp_path, "A.m3u", [a1])
    plB = _make_playlist(tmp_path, "B.m3u", [b1, b2])

    window.add_files([plA, x, y, plB])
    assert _items(window) == [str(plA.resolve()), str(x.resolve()),
                              str(y.resolve()), str(plB.resolve())]

    # Row 0 (Playlist A) + Row 1 (x) zusammen nach unten verschieben.
    window._on_playlist_move(1, [0, 1])
    assert _items(window) == [str(y.resolve()), str(plA.resolve()),
                              str(x.resolve()), str(plB.resolve())]
    # Row 2 (x) + Row 3 (Playlist B) zusammen nach oben: die nicht-selektierte
    # Zeile (y, plA) wird nach unten verdrängt, der Block wandert als Ganzes.
    window._on_playlist_move(-1, [2, 3])
    assert _items(window) == [str(y.resolve()), str(x.resolve()),
                              str(plB.resolve()), str(plA.resolve())]

    # Wiedergabe folgt der neuen Reihenfolge: y, x, B1, B2, A1.
    window._played.clear()
    window._play_playlist_row(2)
    assert window._played == [str(b1.resolve())]
    window.play_next(automatic=True)
    assert window._played[-1] == str(b2.resolve())
    window.play_next(automatic=True)
    assert window._played[-1] == str(a1.resolve())
    window.play_next(automatic=True)
    assert window._played[-1] == str(a1.resolve())  # Ende


def test_marking_survives_move_and_removal(window, tmp_path):
    """Persistente Markierung (v3.0.0-Nachfolger): nach dem Verschieben und
    Entfernen bleibt die Markierung erhalten — mehrfaches Verschieben ohne
    erneutes Markieren; nur Esc/leere Auswahl löscht sie."""
    a1 = _media(tmp_path, "a1.mp3")
    x = _media(tmp_path, "x.mp4")
    y = _media(tmp_path, "y.mp4")
    b1 = _media(tmp_path, "b1.mp3")
    plA = _make_playlist(tmp_path, "A.m3u", [a1])
    plB = _make_playlist(tmp_path, "B.m3u", [b1])

    window.add_files([plA, x, y, plB])
    assert _items(window) == [str(plA.resolve()), str(x.resolve()),
                              str(y.resolve()), str(plB.resolve())]
    pane = window._playlist_pane

    # Playlist A + x markieren und nach unten verschieben
    pane.select_rows([0, 1])
    assert pane.selected_rows() == [0, 1]
    window._on_playlist_move(1, [0, 1])
    assert _items(window) == [str(y.resolve()), str(plA.resolve()),
                              str(x.resolve()), str(plB.resolve())]
    # Markierung überlebt den Re-Render: Zeilen 1+2 sind weiterhin markiert
    assert pane.selected_rows() == [1, 2]
    # erneutes Verschieben (nach oben) — Markierung bleibt erhalten
    window._on_playlist_move(-1, [1, 2])
    assert _items(window) == [str(plA.resolve()), str(x.resolve()),
                              str(y.resolve()), str(plB.resolve())]
    assert pane.selected_rows() == [0, 1]

    # Entfernen einer markierten Zeile: die übrigen bleiben markiert
    window._on_playlist_remove([0])
    assert _items(window) == [str(x.resolve()), str(y.resolve()),
                              str(plB.resolve())]
    assert pane.selected_rows() == [0]


def test_loose_file_play_continues_through_following_playlists(window, tmp_path):
    """Play auf ein loses mp3 (gehört zu keiner Playlist) in der Mitte der
    Queue spielt von dort ALLES bis zum Ende weiter — inkl. aller folgenden
    Playlist-Gruppen und weiterer losen Dateien."""
    a1 = _media(tmp_path, "a1.mp3")
    a2 = _media(tmp_path, "a2.mp3")
    x = _media(tmp_path, "x.mp4")
    y = _media(tmp_path, "y.mp4")
    b1 = _media(tmp_path, "b1.mp3")
    b2 = _media(tmp_path, "b2.mp3")
    plA = _make_playlist(tmp_path, "A.m3u", [a1, a2])
    plB = _make_playlist(tmp_path, "B.m3u", [b1, b2])

    window.add_files([plA, x, y, plB])
    # Loses x (Row 1) spielen: x -> y -> B1 -> B2, dann Ende.
    window._play_playlist_row(1)
    assert window._played == [str(x.resolve())]
    window.play_next(automatic=True)
    assert window._played[-1] == str(y.resolve())
    window.play_next(automatic=True)
    assert window._played[-1] == str(b1.resolve())
    window.play_next(automatic=True)
    assert window._played[-1] == str(b2.resolve())
    window.play_next(automatic=True)
    assert window._played[-1] == str(b2.resolve())  # Ende
    # Gruppen bleiben sichtbar.
    assert _items(window) == [str(plA.resolve()), str(x.resolve()),
                              str(y.resolve()), str(plB.resolve())]