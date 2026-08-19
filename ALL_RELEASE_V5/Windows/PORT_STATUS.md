# PORT_STATUS — Windows (ALL_RELEASE_V5)

| Field | Value |
|-------|-------|
| Current version | **v3.0.0 veröffentlicht** (GitHub-Release v3.0.0) |
| Next version | **v5.0.0** (v4.x übersprungen) |
| Reference tree modified | NO |
| Baseline | HEAD `2367dcbc`, 400 tests PASS (Linux-Referenz) |
| Pure Web Release | 3.0.0 frozen (SHA `b71b5d0b…`) |
| ctest (Wine) | **16/16 grün** (inkl. casu_playlist_test, 14 Checks) |
| Release-Gate | **14/14 PASS** — `win-release/dist/WINDOWS_RELEASE_GATE.json` (generated_utc 2026-08-19T10:48:55Z) |
| Golden | 8 PASS (verify_golden.sh) |
| Installer | setup.exe gebaut + install/uninstall unter Wine verifiziert (PATH bleibt) |
| Playlist-Queue | Playlist-Play + Merge im ZIP/setup.exe verifiziert (strings) |
| Offen | MSVC/QtWebEngine-Endbuild (nur auf echtem Windows); BLOCKER-004 (PATH/Registry auf echtem Windows); BLOCKER-005 (MF/DirectShow-Decoder geplant, nicht gebaut) |

## Nächste Schritte (v5.0.0)
1. Versionsbump 3.0.0 → 5.0.0 überall (setup.nsi, Paketversion, Doku).
2. MSVC/QtWebEngine-Endbuild auf Windows-PC (`scripts/build-msvc.bat`) — echter
   eingebetteter Browser (MinGW = Stub).
3. BLOCKER-004 auf echtem Windows verifizieren (PATH + `.casu`/`.mp5`-Registry).
4. BLOCKER-005: MF/DirectShow-Decoder (CODEC-001) — geplant.
5. Release-Pipeline wie in v3.0.0 (SAFE-GUARD.md Abschnitt 6), dann GitHub-Release.

## Verlauf (v3.0.0)
- Phase A Foundation, B Shared-Core, C Apps, D Packaging+Gate — alle VERIFIED.
- Web-Provider-Tabs (QtWebEngine-Pfad, CASU_HAVE_WEBENGINE) + setup.exe ergänzt.
- Playlist-Queue-Feature (Playlist-Play + Merge) auf Windows portiert + Tests.