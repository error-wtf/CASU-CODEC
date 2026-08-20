# FEATURE_MATRIX — Windows ↔ Linux-Referenz (Parität)

Legende: ✅ fertig+verifiziert · 🟡 teilweise (MSVC-only) · 🔲 geplant · ❌ nein

| Feature | Linux-Referenz | Windows |
|---------|---------------|---------|
| Container CASUNAT1/NAT2/MP5 (zstd+zlib) | ✅ | ✅ (Golden byte-identisch) |
| CLI `casu` (alle Subcommands) | ✅ | ✅ |
| Converter (Qt-GUI, Batch, Presets) | ✅ | ✅ |
| Player MPCASU (libVLC) | ✅ | ✅ (echter Decode unter Wine) |
| YouTube (yt-dlp → Loopback → libVLC) | ✅ | ✅ (Live-Gate: Full-Stream 28,5 MB byte-exakt) |
| Web-Backend `/api/*` + Stream-Proxy | ✅ | ✅ |
| Pure Web (frozen, byte-identical) | ✅ | ✅ (SHA verifiziert) |
| Playlist-Formate (M3U/PLS/WPL/XSPF/…+ JSON) | ✅ | ✅ |
| Playlist-Gruppen sichtbar (nie aufgelöst) | ✅ | ✅ |
| Logische Sequenz (Gruppen + lose Dateien/URLs gemischt durchgespielt) | ✅ | ✅ |
| Gruppen verschiebbar (↑/↓, Kontextmenü) | ✅ | ✅ |
| Mehrfachauswahl verschiebbar (Strg/Shift, Block-Move) | ✅ | ✅ |
| Markierung dauerhaft (bleibt nach Verschieben/Entfernen; Esc löscht) | ✅ | ✅ |
| Einsortieren: Auswahl → Playlist ("Save selection…"/"Move to playlist…") | ✅ | ✅ |
| Aussortieren: Kind aus Playlist ("Remove from playlist") | ✅ | ✅ |
| Loses Material ein-/aussortierbar + überall abspielbar | ✅ | ✅ |
| Batch-Dedup (Playlist + eigene Dateien → kein Doppelt-Laden) | ✅ | ✅ |
| Playlist-Play ohne Ausklappen (ganze Liste durchspielen) | ✅ | ✅ |
| Merge: Dateien/URLs in Playlist (dedupliziert) | ✅ | ✅ |
| Gemischte Queue (Playlists+Dateien+URLs) | ✅ | ✅ |
| Absturzsicherheit (kaputte Playlists etc.) | ✅ | ✅ |
| Visualizer (gedrosselt, kein CPU-Pegel) | ✅ | ✅ |
| **UI-Parität v3.1 (Aufbau + Funktionen identisch)** | | |
| DiagnosticsBar (4 Karten: SEGMENTED/LIVE GUIDE/INTEGRITY/CASU) | ✅ | ✅ |
| Drop-Overlay „DROP TO PLAY / ADD TO QUEUE" (Dateien + URLs) | ✅ | ✅ |
| Toast-Repositionierung + Screen-Clamp (resize/move/show) | ✅ | ✅ |
| Queue-Rename (✎ inline, `display_titles_`) | ✅ | ✅ |
| Rec-Settings-Dialog (Speicherort/Format/Split) im Transport-⋯ | ✅ | ✅ |
| Options: yt-dlp-Cache leeren + Provider-Status live (✓/✗) | ✅ | ✅ |
| Shuffle-Highlight via `[on=true]` + Status | ✅ | ✅ |
| Volume/Mute/Rate live persistiert (sofortiges Speichern) | ✅ | ✅ |
| Badges-Spalte in Playlist-View (YT/STREAM/MP3/CASU/…) | ✅ | ✅ |
| Now-Playing-EPG-Zeile (`channel · now: …` im Titel) | ✅ | ✅ |
| Sources: YouTube-Suche (yt-dlp) + Playlist-Expand + Consent-Gate | ✅ | ✅ |
| Tag-Titel „title — artist" (`casu::media::metadata_for`) | ✅ | ✅ |
| EPG: M3U-Katalog + URL-Load + Karten-Grid (3/Zeile) + Klick-Play | ✅ | ✅ |
| Media-Info: CASU-Manifest (CASUNAT1/2 verified) | ✅ | ✅ |
| Library: Suche/Modi (Artists/Albums/Genres/Favorites)/Splitter/Ordner/Scan | ✅ | ✅ |
| Chapters-Menü (`set_chapter`) | ✅ | ✅ |
| Track-Menüs Audio/Video/Subtitles | ✅ | ✅ |
| Audio-Device-Auswahl (VLC-Device-Liste) | ✅ | ✅ |
| A/V-Delay-Dialoge + externes Untertitel + Frame-Step | ✅ | ✅ |
| MIME/Dateitypen `.casu`/`.mp5` | ✅ (MIME-DB) | ✅ (Registry, unter Wine getestet; echt nur Windows) |
| PATH-Registrierung `casu` | — (n/a) | ✅ (Uninstall-Fix verifiziert) |
| Web-Player-Tabs (Spotify/Hearthis/Tidal/Netflix/Browse) | ✅ (eingebetteter QtWebEngine) | 🟡 MinGW=Stub-Tabs; echt nur MSVC-Build |
| Installer | `.deb` | ✅ NSIS setup.exe |
| **web-casu** (Backend-Player `/web/`) | ✅ (DEB web-casu) | ✅ (serviert im Paket) |
| **Pure Web** (`MPCASU-PURE-WEB-3.0.0.zip`) | ✅ | ✅ (byte-identisch im Paket) |
| MF/DirectShow-Decoder (CODEC-001) | — | 🔲 geplant (BLOCKER-005) |
| GNU/Linux-Build | ✅ | ✅ (Cross-Compile + Wine) |
| macOS | — | 🔲 geplant (Mac-OS/) |
| Android | — | 🔲 geplant (Android/) |

## Paritätsregel
"Exakt gleiche Apps" heißt: gleiche Container, gleiche CLI, gleicher Player,
gleiche Playlist-Queue-Semantik, gleicher eingebetteter Browser (MSVC-Build).
Kein Feature still entfernen; Abweichungen hier dokumentieren (BLOCKED statt verschwinden).

## Playlist-Gruppen-Semantik (verbindlich)
Nicht-destruktive Gruppen-Queue wie im Linux-Referenzplayer (siehe
`README.md` → "Playlist-Gruppen-Semantik"): Playlists bleiben als sichtbare,
verschiebbare Gruppen im Queue (nie aufgelöst); die logische Sequenz spielt
Gruppen + lose Dateien/URLs in Reihenfolge durch; Gruppen und Mehrfachauswahlen
(Strg/Shift) sind per ↑/↓ und Kontextmenü verschiebbar; Einträge sind ein-
("Save selection…"/"Move to playlist…") und aussortierbar ("Remove from
playlist"); Batch-Dedup verhindert Doppelt-Laden. Abgedeckt durch
`win-release/tests/casu_playlist_test.cpp`.

## Web-Player (web-casu + Pure Web) — Gruppen-Semantik (verbindlich)
- Identische, nicht-destruktive Gruppen-Queue wie Desktop-Player: Playlists
  bleiben als sichtbare, auf-/zuklappbare Gruppen (nie aufgelöst), die flache
  Wiedergabesequenz spielt Gruppen + lose Dateien/URLs in Reihenfolge durch.
- Gruppen-Tools im Header (▶ spielen, ↑/↓ verschieben, × entfernen) + eigenes
  Kontextmenü (Rechtsklick): Expand/Collapse, Move, Remove, "Remove ALL entries
  from playlist (keep in queue)".
- Mehrfachauswahl (Strg/Shift-Klick, gestrichelt markiert) über die Footer-
  Tasten ↑/↓/× (Block-Move mit Rand-Bounds-Check, nie Item-Verlust).
- **Dauerhafte Markierung:** Die Markierung überlebt Verschieben (Block-Move
  und Gruppen-Move) und Entfernen (nur Überlebende bleiben markiert); die
  Queue-Zusammenfassung zeigt "N marked", **Esc** löscht die Markierung.
- "Save selection to playlist…": neue Gruppe (Ans Ende) oder in bestehende
  Gruppe einsortieren (dedupliziert, verschiebt die gewählten Items).
- "Remove from playlist": Eintrag bleibt lose in der Queue.
- Re-Add einer bereits geladenen Playlist wird übersprungen (Toast); lokale
  Medien dedupliziert nach relativen Pfaden.
- Geprüft: Node-Unit-Harness (pure-web 25 Checks, web-casu 19 Checks,
  ALL PASS) + Playwright-Browser-Smoke `tools/smoke_web_playlist.py`
  (Gruppen-Tools, Block-Move, Mehrfachauswahl, rein/raus, Save-selection;
  mehrfach grün).