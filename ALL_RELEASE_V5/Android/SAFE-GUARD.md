# SAFE-GUARD — Absicherung (Android) — noch nicht anwendbar

Der Loop gilt, sobald ein Android-Build existiert. Vorbereitend:

1. **Backup**: `./win-release/scripts/safe-guard.sh backup android-<tag>`
   (Skript um Android-Pfade erweitern, wenn Android-Code entsteht).
2. **Tests**: Android-spezifisch: Instrumented-Tests (Espresso/ADB) + Core-Lib-
   Unit-Tests auf Host (die .so sind auf x86_64-Host lauffähig, wo ABI passt).
3. **Parität**: `./win-release/scripts/test-guard.sh run` weiterhin grün halten.

## Android-spezifische Gates (Plan)
- APK startet auf Emulator + echtem Gerät (arm64 + x86_64).
- Core-Lib-Tests (SHA256/Formate/MP5) auf Host + Gerät identisch.
- Golden-Vergleich: CLI-Kern-Funktionen als .so-Tests (Android kennt kein CLI).
- Playlist-Queue + Merge funktionieren touch-gerecht.
- WebEngine-Tabs laden Web-Provider.
- Keine falschen PASS: "APK baut" ≠ "APK läuft".

## Stolperfallen (voraussichtlich)
- QtWebEngine auf Android: ABI-Mismatch, .so-Größen (APK >100 MB).
- libVLC-Android: Plugin-Set reduziert; Hardware-Decode-Profile.
- yt-dlp auf Android: Python nicht verfügbar → Transport neu bewerten.