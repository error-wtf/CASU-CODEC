# FEATURE_MATRIX — Linux (Referenz = Linux-Referenzplayer selbst)

Die Linux-Version ist der **Referenzstand** — hier gilt: kein Feature fehlt
per Definition; die Matrix dient dem Abgleich mit Windows und der Doku.

| Feature | Linux | Windows (Parität) |
|---------|-------|-------------------|
| Container CASUNAT1/NAT2/MP5 | ✅ | ✅ (Golden byte-identisch) |
| CLI `casu` | ✅ | ✅ |
| Converter Qt-GUI | ✅ | ✅ |
| Player MPCASU (libVLC) | ✅ | ✅ |
| YouTube (yt-dlp→Loopback→libVLC) | ✅ | ✅ (Live-Gate) |
| Web-Backend `/api/*` | ✅ | ✅ |
| Pure Web (frozen) | ✅ | ✅ (byte-identisch) |
| Playlist-Formate + Queue + Merge | ✅ | ✅ |
| Playlist-Gruppen sichtbar (nie aufgelöst) | ✅ | ✅ |
| Logische Sequenz (Gruppen + lose Dateien/URLs gemischt durchgespielt) | ✅ | ✅ |
| Gruppen verschiebbar (↑/↓, Kontextmenü) | ✅ | ✅ |
| Mehrfachauswahl verschiebbar (Strg/Shift, Block-Move) | ✅ | ✅ |
| Einsortieren: Auswahl → Playlist ("Save selection…"/"Move to playlist…") | ✅ | ✅ |
| Aussortieren: Kind aus Playlist ("Remove from playlist") | ✅ | ✅ |
| Loses Material ein-/aussortierbar + überall abspielbar | ✅ | ✅ |
| Batch-Dedup (Playlist + eigene Dateien → kein Doppelt-Laden) | ✅ | ✅ |
| Visualizer gedrosselt | ✅ | ✅ |
| MIME `.casu`/`.mp5` | ✅ (MIME-DB) | ✅ (Registry) |
| Eingebetteter Browser (QtWebEngine) | ✅ | 🟡 MinGW=Stub, MSVC=echt |
| Installer | ✅ DEB | ✅ NSIS setup.exe |
| **web-casu** (Backend-Player `/web/`) | ✅ (DEB web-casu) | ✅ (serviert im Paket) |
| **Pure Web** (`MPCASU-PURE-WEB-3.0.0.zip`) | ✅ | ✅ (byte-identisch im Paket) |

## Web-Player (web-casu + Pure Web) — Gruppen-Semantik (verbindlich)
- Identische, nicht-destruktive Gruppen-Queue wie Desktop-Player: Playlists
  bleiben als sichtbare, auf-/zuklappbare Gruppen (nie aufgelöst), die flache
  Wiedergabesequenz spielt Gruppen + lose Dateien/URLs in Reihenfolge durch.
- Gruppen-Tools im Header (▶ spielen, ↑/↓ verschieben, × entfernen) + eigenes
  Kontextmenü (Rechtsklick): Expand/Collapse, Move, Remove, "Remove ALL entries
  from playlist (keep in queue)".
- Mehrfachauswahl (Strg/Shift-Klick, gestrichelt markiert) über die Footer-
  Tasten ↑/↓/× (Block-Move mit Rand-Bounds-Check, nie Item-Verlust).
- "Save selection to playlist…": neue Gruppe (Ans Ende) oder in bestehende
  Gruppe einsortieren (dedupliziert, verschiebt die gewählten Items).
- "Remove from playlist": Eintrag bleibt lose in der Queue.
- Re-Add einer bereits geladenen Playlist wird übersprungen (Toast); lokale
  Medien dedupliziert nach relativen Pfaden.
- Geprüft: Node-Unit-Harness (pure-web 17 Checks, web-casu 12 Checks,
  ALL PASS) + Playwright-Browser-Smoke `tools/smoke_web_playlist.py`
  (Gruppen-Tools, Block-Move, Mehrfachauswahl, rein/raus, Save-selection;
  mehrfach grün).

## Verhaltens-Parität (verbindlich)
- Gleiche Container/CLI-Ergebnisse (Golden byte-identisch).
- Gleiche Playlist-Queue-Semantik (Playlist-Play, Merge dedupliziert, gemischte
  Queue, Absturzsicherheit).
- **Nicht-destruktive Gruppen-Queue** (siehe `README.md` → "Playlist-Gruppen-
  Semantik"): Playlist-Gruppen bleiben beim Spielen sichtbar, logische Sequenz
  spielt Gruppen + lose Dateien/URLs in Reihenfolge, Gruppen und
  Mehrfachauswahlen sind verschiebbar, Einträge ein- ("rein") und aussortierbar
  ("raus") — identisch in Linux- und Windows-Player.
- Gleicher eingebetteter Browser (nur MSVC-Build hat echten Chromium).