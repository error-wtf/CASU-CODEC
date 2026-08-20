# START_HIER — Start-Prompt für die nächste Windows-Session (v5.0)

Öffne eine NEUE Session in `/home/error/Codec-Casu` und gib den folgenden Text
als ersten Prompt ein.

================================================================================
PROMPT:
================================================================================

Setze die Windows-Release-Arbeit an CASU-CODEC / MPCASU fort. Die v3.0.0 ist
veröffentlicht; die nächste Version ist **v5.0.0** (v4.x wird übersprungen).

Lies ZUERST, in dieser Reihenfolge:
1. `ALL_RELEASE_V5/README.md` — Versionspolitik + Struktur
2. `ALL_RELEASE_V5/Windows/PORT_STATUS.md` — aktueller Stand / nächster Schritt
3. `ALL_RELEASE_V5/Windows/PREREQUISITES.md` — Toolchain
4. `win-release/PORT_STATUS.md` + `win-release/roadmap/BLOCKERS.md` — Details
5. `ALL_RELEASE_V5/Windows/RUN_CHECKLIST.md` — Gates

Grundregeln:
- Code NUR unter `win-release/` schreiben; Referenzbaum (`mpcasu_qt/`,
  `casu/`, `packaging/`) ist der Nutzer-Referenzbaum — Änderungen nur nach
  Freigabe des Nutzers (vorher explizit fragen).
- Pure Web: `pure-web-release/` ist die kanonische Quelle; nach Änderungen
  `win-release/web/pure/` byte-identisch neu kopieren (Zip neu bauen, SHA256
  aktualisieren in `ALL_RELEASE_V5/Windows/PORT_STATUS.md`).
- Vor jeder Änderung: `./win-release/scripts/safe-guard.sh backup <tag>`.
- Nach jeder Änderung: `./win-release/scripts/test-guard.sh run` (ctest unter
  Wine ohne VLC-Live/YouTube-Live → **14/14 grün**, inkl. `casu_playlist_test`
  Gruppen-Semantik) — nur wenn grün: weiter.
- Keine falschen PASS: kompiliert ≠ Unit grün ≠ funktioniert (Wine-Lauf,
  Golden-Vergleich, echtes YouTube/CDN).
- Secrets: Token NUR in `/home/error/gittoken.env` (nie loggen, nie committen).
- Versionierung: beim Versionsbump ALLE "3.0.0" → "5.0.0" (setup.nsi,
  CMake-Paketversion, DEB-Versionen, Doku, Release-Body).
- Windows-Release nach Web-Änderungen neu bauen (`SKIP_WINE=1
  build-windows-release.sh`), damit neues MPCASU.exe + `web/pure/` im
  ZIP/setup.exe landen (byte-identisch verifizieren).

Nächster Schritt laut PORT_STATUS: Versionsbump auf 5.0.0, dann MSVC/
QtWebEngine-Endbuild bzw. BLOCKER-004/005 abarbeiten (Reihenfolge nach
Nutzer-Freigabe).
================================================================================
ENDE PROMPT
================================================================================