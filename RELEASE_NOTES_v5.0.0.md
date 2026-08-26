# RELEASE NOTES v5.0.0 — „Perfect Parity Everywhere"

**Freigabe:** 2026-08-21 · **Vorgänger:** v3.0.0 (**v4.x wird übersprungen**)

v5.0.0 ist der erste Release-Zug der ALL_RELEASE_V5-Ära: Windows und Linux
bauen auf dem abgeschlossenen, verifizierten v3-Stand auf (Referenz-Code) und
heben die Produktversion auf 5.0.0. Alle v3-Paritäts- und Installer-Fixes sind
vollständig enthalten.

## Windows (MPCASU-Windows-x86_64.zip / MPCASU-Setup-5.0.0.exe)

1. **Echter eingebetteter Web-Player:** Microsoft Edge **WebView2** im
   MinGW-Paket (DRM/Widevine → Spotify/Tidal/Netflix spielen wirklich im
   Player), persistente Logins je Provider, transparenter Fallback falls die
   Runtime fehlt.
2. **Per-App-Icons:** Jede App hat ihr eigenes Icon — in der EXE-Ressource,
   auf allen Verknüpfungen und in der Datei-Assoziation.
3. **Auto-Update:** Erneutes Ausführen des Setups erkennt eine bestehende
   Installation und aktualisiert **in-place**.
4. **Kein Administrator nötig:** Admin → Machine-Installation; Standardbenutzer
   → Per-User-Installation inkl. Fallback-Logik.
5. **Converter-Journal/Resume**, Advanced-Optionen fließen in CASU-Manifest ein.
6. **Web-Backend-Security-Headers** exakt wie `web_casu.py`.
7. **Queue-Klick → Now Playing:** Doppelklick auf Queue-Item springt direkt
   auf die Now Playing-Seite.
8. **YouTube-Thumbnails:** YouTube-Suchergebnisse zeigen Vorschaubilder
   (QNetworkAccessManager, Hintergrund-Thread).
9. **★ Favoriten in Queue + Library:** Rechtsklick → "☆ Mark as favorite" /
    "★ Remove favorite" — in Queue UND Library.
10. **Doppelklick für Wiedergabe:** Queue-Items werden per Doppelklick
     abgespielt (Single-Click nur Expand/Selekt).
11. **Library Multi-Select:** Strg/Shift-Klick für Mehrfachauswahl; Kontextmenü
     "Add to queue (N)" und "★ Toggle (N)" für mehrere Items.
12. **YouTube-Ergebnisse APK-artig:** Größere Thumbnails (120×68), zweizeiliges
     Layout (Titel + Uploader · Dauer ▶).

## Linux (casu-codec / casu-converter / mpcasu / web-casu 5.0.0 DEBs)

1. Produktversion 5.0.0 in pyproject/CLI/GUI-Anzeige/DEBs.
2. **Format-Version entkoppelt:** Geschriebene CASU-Manifeste tragen weiterhin
   Container-Version `3.0.0` (`CASU_FORMAT_VERSION`) — ältere Player bleiben
   kompatibel.
3. Pure Web bleibt als eingefrorenes `MPCASU-PURE-WEB-3.0.0.zip` erhalten.
4. **Doppelklick für Wiedergabe:** Queue-Items werden per Doppelklick
   abgespielt (Single-Click nur Expand/Selekt).
5. **YouTube-Ergebnisse APK-artig:** Größere Thumbnails (120×68), zweizeiliges
   Layout (Titel + Uploader · Dauer ▶).
6. **★ Favoriten in Queue + Library:** Rechtsklick-Kontextmenü in Queue (Play/★/Remove)
   und Library (★ Toggle + Add to queue) in allen Frontends (Qt + Tk).
7. **Tk Player DB-Finder:** Rechtsklick → ★ Toggle / Add to queue.
8. **Library Multi-Select:** Strg/Shift-Klick für Mehrfachauswahl; Kontextmenü
   "Add to queue (N)" und "★ Toggle (N)" für mehrere Items.
9. **Sidebar-Icons:** Optimierte Unicode-Symbole in der linken Navigation.

## Android (CASU-5.0.0.apk)

1. **StreamRecorder:** MediaExtractor/Muxer-basierte Aufnahme (MP4/M4A/OGG/Copy),
   automatischer MUXER→COPY-Fallback für Live-fMP4/DASH-Streams, SAF-Ordnerwahl.
2. **ANR-Fix:** `CasuBridge.warmUp()` auf Hintergrund-Thread verschoben.
3. **YouTube-Thumbnails** in Suchergebnissen.
4. **Multi-Select Queue** mit Favoriten-Toggle.
5. **Provider-Tab** (OAuth/Downloads/Uploads) mit Tab-Layout.
6. **Library Multi-Select:** Long-Press → Multi-Select-Modus mit ◉/○-Check,
   Batch "▶ Queue" + "★" Toggle + Select All/Deselect.
7. **Launcher-Icon vergrößert:** Foreground füllt ~57% der Canvas (vorher 17%).

## Geplant (Folge-Releases derselben v5-Reihe)

- **macOS**: `.dmg`-Build (siehe `ALL_RELEASE_V5/Mac-OS/`).
