# START_HIER — Start-Prompt für die nächste Windows-Session (v5.0)

Öffne eine NEUE Session in `/home/error/Codec-Casu` und gib den folgenden Text
als ersten Prompt ein.

================================================================================
PROMPT:
================================================================================

Setze die Windows-Release-Arbeit an CASU-CODEC / MPCASU fort. Die v3.0.0 ist
veröffentlicht; die nächste Version ist **v5.0.0** (v4.x wird übersprungen).
STAND 2026-08-22: Der komplette CASUNAT2-Stack (CASU-0..4) und die native-v2-
Converter-Pipeline (CASU-5 + Strict-Decoder) sind portiert und **byte-paritätisch
gegen den Python-Referenzbaum verifiziert** (Commits `9fb279d`, `e64ed63`;
Tests `casu_natv2_parity_test` 19/19 + `casu_natv2_convert_test` ALL PASS).

Lies ZUERST, in dieser Reihenfolge:
1. `/home/error/HANDOVER.md` §0b/§0c — Tier-Liste + Execution Contract (BINDEND)
2. `ALL_RELEASE_V5/README.md` — Versionspolitik + Struktur
3. `ALL_RELEASE_V5/Windows/PORT_STATUS.md` — aktueller Stand / nächster Schritt
4. `win-release/PORT_STATUS.md` + `AGENTS.md` — Details + Arbeitsregeln

Grundregeln:
- **HARTE REGEL**: VOLLSTÄNDIGE PARITÄT ZUERST. Keine Android-/macOS-Arbeit,
  kein v5.0.0-GitHub-Release, keine neuen Features, BEVOR die §0b-Tierliste
  abgearbeitet ist (Nachweis: ctest grün + Paritätstests + Audit-Checkliste).
- Nächste Tier-Schritte: ANA-STRICT P2–P5 → EPG-Fixes → Tier 2 Items 4–10.
- Code NUR unter `win-release/` schreiben; der Referenzbaum (`mpcasu_qt/`,
  `casu/`, `packaging/`) ist die Python-Referenz — nur mit Nutzer-Freigabe.
- Jede Portierung: Verhalten gegen Python-Referenz gegentesten (gleiche Inputs
  → identische Outputs/Felder), KEINE Stubs/TODOs (Abnahmekriterium §0c).
- Vor jeder Änderung: `./win-release/scripts/safe-guard.sh backup <tag>`.
- Nach jeder Änderung: Build + ctest unter Wine (GUI-Tests serial bei ruhigem
  Desktop); Paritätstests: `casu_natv2_parity_test` + `casu_natv2_convert_test`
  (env CASU_FFMPEG/CASU_FFPROBE auf gebündelte Tools setzen).
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