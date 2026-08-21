# RELEASE NOTES v5.0.0 — „Perfect Parity Everywhere"

**Freigabe:** 2026-08-21 · **Vorgänger:** v3.0.0 (**v4.x wird übersprungen**)

v5.0.0 ist der erste Release-Zug der ALL_RELEASE_V5-Ära: Windows und Linux
bauen auf dem abgeschlossenen, verifizierten v3-Stand auf (Referenz-Code) und
heben die Produktversion auf 5.0.0. Alle v3-Paritäts- und Installer-Fixes sind
vollständig enthalten.

## Windows (MPCASU-Windows-x86_64.zip / MPCASU-Setup-5.0.0.exe)

Gegenüber v3.0.0 (Stand 2026-08-21, Commit `775fd91`):

1. **Echter eingebetteter Web-Player:** Microsoft Edge **WebView2** im
   MinGW-Paket (DRM/Widevine → Spotify/Tidal/Netflix spielen wirklich im
   Player), persistente Logins je Provider, transparenter Fallback falls die
   Runtime fehlt. MSVC/QtWebEngine-Pfad bleibt erhalten.
2. **Per-App-Icons:** Jede App hat ihr eigenes Icon — in der EXE-Ressource,
   auf allen Verknüpfungen und in der Datei-Assoziation (identisch zu den
   Linux-Desktop-Einträgen). Setup-Icon wird nicht mehr für alle Apps
   wiederverwendet; `assets/assets`-Packaging-Fehler behoben.
3. **Auto-Update:** Erneutes Ausführen des Setups erkennt eine bestehende
   Installation (Machine- UND Per-User-Scope) und aktualisiert **in-place**
   (laufende Instanzen werden sauber beendet).
4. **Kein Administrator nötig:** Kein erzwungener UAC-Prompt. Admin →
   Machine-Installation (`Program Files`, HKLM); Standardbenutzer →
   vollwertige Per-User-Installation (`%LocalAppData%\MPCASU`, HKCU,
   Benutzer-PATH) inkl. Fallback-Logik.
5. **Converter-Journal/Resume** (`.casu-conversion-*.json`, hash-verifiziert),
   Advanced-Optionen fließen in CASU-Manifest/MP5/Batch-Report ein.
6. **Web-Backend-Security-Headers** exakt wie `web_casu.py`.

Verifikation: ctest **16/16** unter Wine · Release-Gate **PASS** ·
Silent-Install / Re-Install-in-place / Uninstall unter Wine verifiziert ·
Shortcut-Icons je App verifiziert.

## Linux (casu-codec / casu-converter / mpcasu / web-casu 5.0.0 DEBs)

1. Produktversion 5.0.0 in pyproject/CLI/GUI-Anzeige/DEBs.
2. **Format-Version entkoppelt:** Geschriebene CASU-Manifeste tragen weiterhin
   Container-Version `3.0.0` (`CASU_FORMAT_VERSION`) — ältere Player bleiben
   kompatibel, Plattformen bleiben byte-kompatibel.
3. Pure Web bleibt als eingefrorenes `MPCASU-PURE-WEB-3.0.0.zip` erhalten
   (byte-identisch, SHA256-verifiziert).

Verifikation: pytest **425 passed** (1 Umgebungs-Test Chromium ausgenommen) ·
DEB-Build reproduzierbar (`SOURCE_DATE_EPOCH=0`).

## Geplant (Folge-Releases derselben v5-Reihe)

- **Android** (APK-Sideload): Qt-for-Android + libVLC + yt-dlp-bundled,
  Touch-UI-Umbau des Players (siehe `ALL_RELEASE_V5/Android/`).
- **macOS**: `.dmg`-Build (siehe `ALL_RELEASE_V5/Mac-OS/`).
