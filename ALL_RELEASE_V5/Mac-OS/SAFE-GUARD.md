# SAFE-GUARD — Absicherung (macOS) — noch nicht anwendbar

Der Loop gilt, sobald ein macOS-Build existiert. Vorbereitend:

1. **Backup**: `./win-release/scripts/safe-guard.sh backup macos-<tag>`
   (Skript um macOS-Dateien erweitern, wenn macOS-Code entsteht).
2. **Tests**: macOS-spezifische Tests analog Linux (`test_player_ui.py`-Stil
   unter macOS) + Golden-Parität (Hashes/JSON) gegen Linux-Referenz.
3. **Windows/Linux nicht brechen**: `./win-release/scripts/test-guard.sh run`
   weiterhin ausführen (Cross-Plattform-Regression).

## macOS-spezifische Gates (Plan)
- Codesign/Notarisierung erfolgreich (`spctl --assess`, `xcrun notarytool`).
- Universal-Binary (arm64 + x86_64) startet auf beiden Architekturen.
- Eingebetteter QtWebEngine-Tab lädt Web-Provider (Spotify etc.).
- Golden-Vergleich: CLI-Ausgaben/Hashes identisch zu Linux/Windows.
- `.casu`/`.mp5`-Dateitypen: macOS kündigt via Info.plist
  (CFBundleDocumentTypes) + LaunchServices an.