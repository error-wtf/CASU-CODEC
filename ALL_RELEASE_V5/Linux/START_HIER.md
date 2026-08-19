# START_HIER — Start-Prompt für die nächste Linux-Session (v5.0)

Öffne eine NEUE Session in `/home/error/Codec-Casu` und gib den folgenden Text
als ersten Prompt ein.

================================================================================
PROMPT:
================================================================================

Setze die Linux-Release-Arbeit an CASU-CODEC / MPCASU fort. v3.0.0 ist
veröffentlicht; die nächste Version ist **v5.0.0** (v4.x wird übersprungen).

Lies ZUERST, in dieser Reihenfolge:
1. `ALL_RELEASE_V5/README.md` — Versionspolitik + Struktur
2. `ALL_RELEASE_V5/Linux/PORT_STATUS.md` — aktueller Stand / nächster Schritt
3. `ALL_RELEASE_V5/Linux/RUN_CHECKLIST.md` — Gates
4. `ALL_RELEASE_V5/Linux/PREREQUISITES.md` — Toolchain

Grundregeln:
- Code: `mpcasu_qt/`, `casu/`, `web-casu/`, `packaging/` (Nutzer-Referenz;
  Änderungen erlaubt — Nutzer hat sie freigegeben).
- Vor jeder Änderung: `./win-release/scripts/safe-guard.sh backup <tag>`.
- Nach jeder Änderung: `pytest tests/test_playlist.py tests/test_player_ui.py -q`
  und `./win-release/scripts/test-guard.sh run` — nur wenn grün: weiter.
- Nie ein Release bauen, solange Tests nicht grün sind.
- Secrets: Token NUR in `/home/error/gittoken.env` (nie loggen, nie committen).
- Versionierung: beim Versionsbump ALLE "3.0.0" → "5.0.0" (DEB-Versionen,
  Doku, Release-Body, SHA256SUMS).
- `build_debs.sh` leert `dist/` → PURE-WEB-ZIP wiederherstellen
  (`git checkout -- dist/MPCASU-PURE-WEB-3.0.0.zip`), SHA256SUMS neu.

Nächster Schritt laut PORT_STATUS: Versionsbump auf 5.0.0, DEBs bauen, Release.
================================================================================
ENDE PROMPT
================================================================================