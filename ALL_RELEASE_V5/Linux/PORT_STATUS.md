# PORT_STATUS — Linux (ALL_RELEASE_V5)

| Field | Value |
|-------|-------|
| Current version | **v3.0.0 veröffentlicht** (GitHub-Release v3.0.0) |
| Next version | **v5.0.0** (v4.x übersprungen) |
| Reference HEAD | `0722878` (main, gepusht) |
| Tests | `test_playlist.py` 20 PASS · `test_player_ui.py` 9 PASS · Gesamtsuite 409 passed/14 skipped |
| Playlist-Queue | `_play_playlist_full`, `_current_playlist_context`, `_on_playlist_merge` — fertig |
| MIME | `.casu` registriert (casu-codec-mime.xml, postinst) — verifiziert im DEB |
| DEBs | casu-codec/casu-converter/mpcasu/web-casu 3.0.0 — gebaut + Release hochgeladen |
| Pure Web | 3.0.0 frozen (SHA `b71b5d0b…`), byte-identisch in Windows-Paket |
| Offen | optional: AppImage/Snap/Flatpak, arm64 (Nutzer-Entscheid); v5.0-Versionsbump |

## Nächste Schritte (v5.0.0)
1. Versionsbump 3.0.0 → 5.0.0 (DEB-Versionen, Doku, Release-Body).
2. Release-Pipeline: Backup → Tests → `bash packaging/build_debs.sh` →
   PURE-WEB-ZIP wiederherstellen → `dist/SHA256SUMS` neu → commit → push →
   GitHub-Release v5.0.0 (4 DEBs + PURE-WEB + kombinierte SHA256SUMS).
3. Optional (Nutzer-Entscheid): AppImage/Snap/Flatpak, arm64.

## Verlauf (v3.0.0)
- Playlist-Formate (M3U/PLS/WPL/XSPF/JSPF/ASX/RMP/RAM/JSON) nativ in allen Playern.
- Absturz/Hänger-Fixes (Visualizer-Repaint, Dateidialog, Doppelt-Laden).
- Playlist-Play ab Track 1 + Durchschalten (Next/Previous).
- Multi-Select in Queue + formatbewusster Save-Dialog.
- Playlist-Queue-Feature (Play ohne Ausklappen + Merge) — Tests erweitert (20).