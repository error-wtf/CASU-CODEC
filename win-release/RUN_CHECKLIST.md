# RUN_CHECKLIST — fehlerfreier Ablauf für den Portierungs-Run

Dieses Dokument ist die konkrete Operation-Anleitung. Ein WP nach dem anderen,
immer derselbe Loop. "VERIFIED" nur mit Nachweis.

## Pro Sitzung — Start (immer)
1. `cd /home/error/Codec-Casu`
2. `git status --short` → prüfen: KEINE Fremdänderung außerhalb `win-release/`.
   Sollte etwas anderes geändert sein: NICHT zurücksetzen, in
   `win-release/audit/session-start.txt` dokumentieren.
3. `PORT_STATUS.md` lesen → aktueller STEP/WP.
4. `git rev-parse HEAD` + `git diff --check` protokollieren.

## Pro WP — der Loop (eine Wiederholung = ein STEP)
1. **STATUS = ANALYSIS**: referenz gezielt lesen.
   - `REFERENCE_LOOKUP.md` → Datei:Zeile → `sed -n '<a>,<b>p' <datei>`.
   - Zusätzlich das eine relevante research-Dokument (`NAVIGATION.md` sagt
     welches). Nicht mehr lesen als nötig.
2. Bei Verständnis-/Architekturfrage: `research/external-research-log.md`
   Eintrag (QUESTION/SOURCES/FINDING/DECISION) anlegen; ggf. Deep-Research.
3. **STATUS = IMPLEMENTING**: Code NUR unter `win-release/`.
4. **Cross-Compile**:
   `cmake -S . -B build-win64 -G Ninja -DCMAKE_TOOLCHAIN_FILE=cmake/mingw64-toolchain.cmake -DCMAKE_BUILD_TYPE=Release`
   `cmake --build build-win64`
   → Erfolg = Exit 0 + keine relevanten Warnings. `file <exe>` = PE32+.
5. **UNIT**: `ctest` / QtTest laufen unter Linux-Host (C++-Core auch ohne
   Windows sinnvoll testbar) UND unter Wine (cross-compiled test-exe).
6. **WINE**: isoliertes Prefix `WINEPREFIX=win-release/.wine-test`,
   `xvfb-run wine <exe>`. Logs nach `test-results/wine/`.
   - Bei Missing-DLL: `objdump -p <exe>` → DLLs notieren → bündeln/fix.
7. **COMPATIBILITY**: Vergleich Linux-Referenz vs Wine-Ergebnis
   (Dateien/Hashes/JSON/Exit-Codes/APIs) → `test-results/compatibility/*.json`.
8. **STATUS = VERIFIED** NUR wenn alle Gates des WP grün.
9. Aktualisieren: dieses Dokument (Checkbox), `PORT_STATUS.md`,
   `WINDOWS_PORT_FEATURE_MATRIX.md`, ggf. Tool-Feature-Matrix.
10. Nächster freigegebener STEP aus `MASTER_GESAMTFAHRPLAN.md`.

## Harte Gates (nie überspringen)
- **YouTube / Netzwerk**: echtes YouTube/CDN unter Wine (nicht nur Mock).
- **GUI/Playback**: echter Windows-Build unter Wine + Screenshot-Vergleich
  Linux↔Wine.
- **Codec/Converter**: Golden-Vergleich (Hashes/JSON) Linux↔Wine.
- **Clean-Prefix**: gepacktes Release in NEUEM WINEPREFIX; nur Paket-Inhalt.
  Läuft nur im Dev-Prefix → FAIL.
- **Keine falschen PASS**: "kompiliert" ≠ "Unit grün" ≠ "funktioniert".

## Fehlerbehandlung
- WP-Fehler: Ursache verstehen (Referenz/Ownership/Logs/Deep-Research), lösen
  ODER als `BLOCKED` in `roadmap/BLOCKERS.md` (ID/Blocker/betroffene WPs/
  Research/next action). Dann nächsten freigegebenen STEP.
- Nie still Feature weglassen → `BLOCKED` statt verschwinden.

## Häufige Stolperfallen (aus den Prompts)
- libVLC 6/7-State + zero-time-EOF: mpcasu_backend.py:600-627.
- YouTube-Lifecycle: stop old → start proxy → open. Nie Proxy vor open killen.
- VideoSurface: keine Qt-Overlays aufs native Video (Flicker).
- HWND-Lifetime, qwindows.dll, vlc/plugins, ffmpeg arg-arrays, Unicode/Spaces.
- Threading: Qt-GUI nur GUI-Thread, Worker→Signals.
- Audio: kein PulseAudio → WASAPI/Qt.
- Wine ≠ Windows: nicht Wine-spezifisch als universelle Lösung coden.

## Token-/Harness-Disziplin
- Pro WP nur gezielt lesen (Lookup), nie den ganzen Baum.
- Ergebnisse/Entscheidungen in Hilfsdateien persistieren (nicht im Kopf).
- `NAVIGATION.md` ist die Karte, `REFERENCE_LOOKUP.md` die Legende,
  `MASTER_GESAMTFAHRPLAN.md` der Weg, dieses Dokument die Checkliste.
