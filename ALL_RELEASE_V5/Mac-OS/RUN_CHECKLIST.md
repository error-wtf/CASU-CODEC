# RUN_CHECKLIST — fehlerfreier Ablauf (macOS, Plan)

Ein WP nach dem anderen, derselbe Loop wie Windows/Linux. "VERIFIED" nur mit
Nachweis.

## Pro WP — der Loop
1. **ANALYSIS**: Referenz lesen (Linux-Player + Windows-Port als Oracle).
2. **BACKUP**: safe-guard.sh (erweitert um macOS-Pfade).
3. **IMPLEMENTIEREN**: nur im macOS-Release-Baum.
4. **BUILD**: `cmake -S . -B build-macos -G Ninja -DCMAKE_BUILD_TYPE=Release`
   + `cmake --build build-macos` → Exit 0, `file` = Mach-O (arm64/x86_64).
5. **TEST**: QtTest/catch2 nativ auf macOS; GUI-Test analog xvfb (macOS:
   `-platform offscreen`).
6. **COMPATIBILITY**: Golden-Vergleich (Hashes/JSON) macOS ↔ Linux ↔ Windows.
7. **VERIFIED** nur bei grünen Gates → `PORT_STATUS.md` + `FEATURE_MATRIX.md`.

## Harte Gates (Plan)
- YouTube/Netzwerk: echtes YouTube/CDN auf macOS (nicht nur Mock).
- GUI/Playback: echter macOS-Build + Screenshot-Vergleich mit Linux.
- Codec/Converter: Golden-Vergleich (Hashes/JSON).
- Clean-Install: gepacktes .dmg in NEUER macOS-User-Umgebung; nur Paket-Inhalt.
- Codesign + Notarisierung ok.
- Keine falschen PASS: kompiliert ≠ Unit grün ≠ funktioniert.

## Fehlerbehandlung
- Lösen ODER BLOCKED loggen (BLOCKERS.md). Nie still Feature weglassen.

## Stolperfallen (voraussichtlich)
- QtWebEngine auf macOS: Sandbox/App-Transparency-Anforderungen.
- libVLC auf macOS: Framework-Bundling + Gatekeeper (Quarantine).
- OpenSSL vs macOS-SecureTransport: TLS-Backendwahl in Qt6Network.
- Mach-O Universal: beide Architekturen einzeln bauen + lipo kombinieren.