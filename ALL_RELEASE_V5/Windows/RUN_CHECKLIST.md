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

## Fehlerbehandlung
- Ursache verstehen (Referenz/Ownership/Logs) → lösen ODER `BLOCKED` in
  `win-release/roadmap/BLOCKERS.md` loggen (ID/Blocker/betroffene WPs/next action).
- Nie still Feature weglassen → `BLOCKED` statt verschwinden.

## Häufige Stolperfallen
- libVLC 6/7-State + zero-time-EOF (mpcasu_backend.py:600-627).
- YouTube-Lifecycle: stop old → start proxy → open; nie Proxy vor open killen.
- VideoSurface: keine Qt-Overlays aufs native Video (Flicker).
- HWND-Lifetime, qwindows.dll, vlc/plugins, ffmpeg arg-arrays, Unicode/Spaces.
- Threading: Qt-GUI nur GUI-Thread, Worker→Signals. Audio: WASAPI/Qt.
- Wine ≠ Windows: Wine-Workarounds nicht als universelle Lösung coden.