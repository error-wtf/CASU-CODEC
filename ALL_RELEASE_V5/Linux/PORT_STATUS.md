# PORT_STATUS — Linux (ALL_RELEASE_V5)

| Field | Value |
|-------|-------|
| Current version | **v3.0.0 veröffentlicht** (GitHub-Release v3.0.0) |
| Next version | **v5.0.0** (v4.x übersprungen) |
| Reference HEAD | `edb51f1` (main, gepusht) + uncommitted Playlist-Gruppen-Arbeit |
| Tests | Gesamtsuite **432 passed / 12 skipped** (Stand 2026-08-20, inkl. `test_playlist.py` move_many + `test_queue_playback_behavior.py` Gruppen-Play/Verschieben/Ein-/Aussortieren) |
| Playlist-Queue (nicht-destruktiv) | Gruppen bleiben sichtbar, logische Sequenz `_play_seq`, Gruppen + Mehrfachauswahl verschiebbar (move_many), Einträge ein-/aussortierbar, loses Material überall abspielbar, Batch-Dedup — fertig |
| MIME | `.casu` registriert (casu-codec-mime.xml, postinst) — verifiziert im DEB |
| DEBs | casu-codec/casu-converter/mpcasu/web-casu 3.0.0 — gebaut + Release hochgeladen (DEB-Neubau nach Gruppen-Arbeit läuft/offen) |
| Pure Web | 3.0.0 frozen (SHA `b71b5d0b…`), byte-identisch in Windows-Paket |
| Offen | optional: AppImage/Snap/Flatpak, arm64 (Nutzer-Entscheid); v5.0-Versionsbump |

## Nächste Schritte (v5.0.0)
1. Versionsbump 3.0.0 → 5.0.0 (DEB-Versionen, Doku, Release-Body).
2. Release-Pipeline: Backup → Tests → `bash packaging/build_debs.sh` →
   PURE-WEB-ZIP wiederherstellen → `dist/SHA256SUMS` neu → commit → push →
   GitHub-Release v5.0.0 (4 DEBs + PURE-WEB + kombinierte SHA256SUMS).
3. Optional (Nutzer-Entscheid): AppImage/Snap/Flatpak, arm64.

## Verlauf (v3.0.0 + Gruppen-Arbeit)
- Playlist-Formate (M3U/PLS/WPL/XSPF/JSPF/ASX/RMP/RAM/JSON) nativ in allen Playern.
- Absturz/Hänger-Fixes (Visualizer-Repaint, Dateidialog, Doppelt-Laden).
- **Playlist-Gruppen-Semantik (nicht-destruktiv, 2026-08-20):** Playlists
  bleiben beim Spielen sichtbar; Wiedergabe über logische Sequenz (`_play_seq`);
  `move_many` (Block-Move, Mehrfachauswahl Strg/Shift); "Move to playlist…"/
  "Remove from playlist" für Kinder; loses Material ein-/aussortierbar +
  überall abspielbar; Batch-Dedup. Tests entsprechend erweitert (432 passed).
- Multi-Select in Queue + formatbewusster Save-Dialog.