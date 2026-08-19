# PORT_STATUS — macOS (ALL_RELEASE_V5)

| Field | Value |
|-------|-------|
| Current version | — (kein macOS-Build) |
| Next version | **v5.0.0** (erster macOS-Release-Zug; v4.x übersprungen) |
| Build-Host | fehlt (macOS-PC oder CI `macos-latest` nötig) |
| Code-Basis | Linux-Referenz + Windows-Port als Vorlage |
| QtWebEngine | verfügbar für macOS → echte Browser-Parität möglich |
| Offen | alles (erstes WP: PREREQUISITES + Hello-Mach-O) |

## Nächste Schritte (v5.0.0, nach Nutzer-Freigabe)
1. Build-Host klären (eigener Mac oder GitHub Actions `macos-latest`).
2. PREREQUISITES beschaffen (Qt6+WebEngine, libVLC, ffmpeg, yt-dlp, zstd, OpenSSL).
3. Erster Build: Hello-Mach-O (Universal), dann Core-Libs (casu_core→codec→…).
4. Apps: CLI → Converter → MPCASU (mit WebEngine-Tabs) → Web-Backend.
5. Packaging: .dmg + Codesign/Notarisierung.
6. Gate: Golden-Parität gegen Linux/Windows.

## Entscheidungsbedarf (Nutzer)
- Bevorzugt eigner Mac oder CI?
- Einheitliche Versionierung v5.0.0 für alle OS gleichzeitig?