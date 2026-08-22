# RUN_CHECKLIST — fehlerfreier Ablauf (Windows)

Ein WP nach dem anderen, immer derselbe Loop. "VERIFIED" nur mit Nachweis.

## Pro Sitzung — Start (immer)
1. `cd /home/error/Codec-Casu`
2. `git status --short` → KEINE Fremdänderung außerhalb erlaubter Bereiche.
3. `PORT_STATUS.md` lesen → aktueller Schritt.
4. `git rev-parse HEAD` + `git diff --check` protokollieren.

## Pro WP — der Loop
1. **ANALYSIS**: Referenz gezielt lesen (`REFERENCE_LOOKUP`-Legende im
   `win-release/`-Baum → `sed -n '<a>,<b>p'`). Nicht mehr lesen als nötig.
2. **IMPLEMENTING**: Code NUR unter `win-release/`.
3. **CROSS-COMPILE**:
   `cmake -S . -B build-win64 -G Ninja -DCMAKE_TOOLCHAIN_FILE=cmake/mingw64-toolchain.cmake -DCMAKE_BUILD_TYPE=Release`
   `cmake --build build-win64` → Exit 0, `file <exe>` = PE32+.
4. **UNIT**: ctest auf Linux-Host (Core) UND unter Wine (cross-compiled).
5. **WINE**: `WINEPREFIX=win-release/.wine-test`, `xvfb-run wine <exe>`,
   Logs → `test-results/wine/`. Missing-DLL → `objdump -p` → bündeln/fix.
6. **COMPATIBILITY**: Vergleich Linux-Referenz vs Wine (Hashes/JSON/Exit).
7. **VERIFIED** NUR wenn alle Gates grün.
8. Aktualisieren: `PORT_STATUS.md`, `FEATURE_MATRIX.md`.
9. Nächster freigegebener Schritt aus `MASTER_GESAMTFAHRPLAN.md`.

## Harte Gates (nie überspringen)
- YouTube/Netzwerk: echtes YouTube/CDN unter Wine (nicht nur Mock).
- GUI/Playback: echter Windows-Build unter Wine + Screenshot-Vergleich.
- Codec/Converter: Golden-Vergleich (Hashes/JSON) Linux↔Wine.
- Clean-Prefix: gepacktes Release in NEUEM WINEPREFIX; nur Paket-Inhalt.
- Keine falschen PASS: "kompiliert" ≠ "Unit grün" ≠ "funktioniert".
- **Playlist-Gruppen-Parität (nicht-destruktiv, wie Linux):** Playlists bleiben
  als sichtbare Gruppen im Queue (nie aufgelöst); logische Sequenz spielt
  Gruppen + lose Dateien/URLs gemischt durch; Gruppen + Mehrfachauswahlen
  (Strg/Shift) verschiebbar (↑/↓, Kontextmenü); Einträge ein- ("Save
  selection…"/"Move to playlist…") und aussortierbar ("Remove from playlist");
  Batch-Dedup. Abgedeckt durch `casu_playlist_test.exe` (ALL PASS, Stand
  2026-08-20) — nach jeder Änderung an `main_window.cpp`/`playlist.cpp` neu
  ausführen.
- **ctest unter Wine:** 14/14 grün (ohne `casu_playback_vlc_test`/
  `casu_playback_youtube_live_test` — kein Audio-Gerät/kein Live-Netz) —
  `WINEPREFIX=/tmp/opencode/wine-prefix WINEDEBUG=-all ctest --test-dir build-win64 -j2`.
- **Web-Player (web-casu + Pure Web):** Node-Harness ALL PASS
  (`/tmp/opencode/webapp_queue_test.js` + `pureweb_queue_test.js`) +
  `python3 tools/smoke_web_playlist.py` mehrfach grün; `win-release/web/pure/`
  muss byte-identisch mit `pure-web-release/` sein (diff -rq leer).

## Fehlerbehandlung
- Ursache verstehen (Referenz/Ownership/Logs) → lösen ODER `BLOCKED` in
  `win-release/roadmap/BLOCKERS.md` loggen (ID/Blocker/betroffene WPs/next action).
- Nie still Feature weglassen → `BLOCKED` statt verschwinden.

## Häufige Stolperfallen
- **Gruppen bleiben sichtbar:** `playlist_view_` ist ein QTreeWidget — oberste
  Zeilen sind Gruppen (is_playlist), Kinder sind deren Einträge. Wiedergabe
  läuft über die logische Sequenz (`logical_sequence()`), nicht über das
  Modell; `seq_valid_` bei jeder Mutation invalidierten (invalidate_seq).
- **QTreeWidget-Kinder:** Beim `refresh_playlist()` werden Gruppen mit
  Platzhalter-Kind angelegt; echte Kinder erst bei Expand
  (`expand_playlist_group`). `refresh_playlist_group(path)` lädt nur die
  betroffene Gruppe neu (erhält Expand-Zustand).
- libVLC 6/7-State + zero-time-EOF (mpcasu_backend.py:600-627).
- YouTube-Lifecycle: stop old → start proxy → open; nie Proxy vor open killen.
- VideoSurface: keine Qt-Overlays aufs native Video (Flicker).
- HWND-Lifetime, qwindows.dll, vlc/plugins, ffmpeg arg-arrays, Unicode/Spaces.
- Threading: Qt-GUI nur GUI-Thread, Worker→Signals. Audio: WASAPI/Qt.
- Wine ≠ Windows: Wine-Workarounds nicht als universelle Lösung coden.
## CASUNAT2-Paritätstests (ab 2026-08-22 verbindlich)

Nach jedem Build zusätzlich zu ctest:

```bash
cd win-release/build-win64
export CASU_FFMPEG='Z:\home\error\Codec-Casu\win-release\third_party\tools\ffmpeg.exe'
export CASU_FFPROBE='Z:\home\error\Codec-Casu\win-release\third_party\tools\ffprobe.exe'
wine ./tests/casu_natv2_parity_test.exe 'Z:\...\tests\fixtures\natv2'   # 19 Checks
wine ./tests/casu_natv2_convert_test.exe 'Z:\...\tests\fixtures\natv2'  # Byte-Identität zur Python-Konvertierung
```

Beide müssen ALL PASS melden — sie sind der Paritätsnachweis für den
CASUNAT2-Stack (§0b Tier 1.1 + CASU-5). Fixtures: `tests/fixtures/natv2/`
(gen1/gen2 = Writer-Vergleich, convert_source.mkv = lossless Konvertier-Fixture).
