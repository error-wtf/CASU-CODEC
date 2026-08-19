# PORT_STATUS — Android (ALL_RELEASE_V5)

| Field | Value |
|-------|-------|
| Current version | — (kein Android-Build) |
| Next version | **v5.0.0** (erster Android-Release-Zug; v4.x übersprungen) |
| Build-Host | Android SDK/NDK + Qt-for-Android nötig (dieser Ubuntu-Host möglich) |
| Code-Basis | Linux-Referenz + Windows-Port als Vorlage |
| Offen | alles (erstes WP: PREREQUISITES + Hello-APK) |

## Nächste Schritte (v5.0.0, nach Nutzer-Freigabe)
1. SDK/NDK/JDK + Qt-for-Android (inkl. WebEngine) installieren.
2. Hello-APK (leere Qt-App, startet auf Emulator) — Gate: läuft.
3. Core-Libs als .so (casu_core→codec→media→network→playback→webapi) + Host-Tests.
4. Player-APK mit libVLC + WebEngine-Tabs (Touch-UI).
5. Converter-APK (optional). Web-Backend in-App (Loopback).
6. Packaging: APK/AAB + Signing; Play-Store vs Side-Load-Entscheidung.

## Entscheidungsbedarf (Nutzer)
- YouTube-Transport auf Android (yt-dlp braucht Python → Alternative wählen:
  innertube-API direkt, yt-dlp-Android-Port, oder WebView-Youtube?).
- Play-Store-Veröffentlichung (Konto + Signing) oder nur APK-Download?
- UI: Touch-Umbau erlaubt oder strikte Desktop-Parität?