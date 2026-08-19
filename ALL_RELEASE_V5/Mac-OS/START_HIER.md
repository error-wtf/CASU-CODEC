# START_HIER — Start-Prompt für die macOS-Session (v5.0)

Öffne eine NEUE Session in `/home/error/Codec-Casu` und gib den folgenden Text
als ersten Prompt ein.

================================================================================
PROMPT:
================================================================================

Starte den macOS-Port von CASU-CODEC / MPCASU (Version **v5.0.0**; v4.x wird
übersprungen). Ziel: Universal-Binary (arm64 + x86_64), .dmg, eingebetteter
QtWebEngine-Browser (voll, kein Stub), Golden-Parität zu Linux/Windows.

Lies ZUERST:
1. `ALL_RELEASE_V5/README.md` — Versionspolitik + Struktur
2. `ALL_RELEASE_V5/Mac-OS/PORT_STATUS.md` — Stand + nächste Schritte
3. `ALL_RELEASE_V5/Mac-OS/PREREQUISITES.md` — Beschaffung (SCHRITT 0)
4. `ALL_RELEASE_V5/Mac-OS/RUN_CHECKLIST.md` — Gates
5. `win-release/` als Portierungs-Vorlage (C++20/Qt6, bereits fertig)

Grundregeln:
- Vor jeder Änderung Backup; nach jeder Änderung Tests; nie Release ohne grüne
  Gates. Keine falschen PASS.
- Secrets: Token NUR in `/home/error/gittoken.env` (nie loggen, nie committen).
- Nutzer muss Build-Host klären (eigener Mac oder CI) und Codesign/Notarisierung
  bereitstellen — vorher fragen, nicht annehmen.
- Erst Hello-Mach-O, dann Core-Libs, dann Apps, dann Packaging (.dmg).

Nächster Schritt: PREREQUISITES beschaffen + ersten Build-Host klären.
================================================================================
ENDE PROMPT
================================================================================