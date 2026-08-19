# RUN_CHECKLIST — fehlerfreier Ablauf (Android, Plan)

Ein WP nach dem anderen, derselbe Loop. "VERIFIED" nur mit Nachweis.

## Pro WP — der Loop
1. **ANALYSIS**: Referenz lesen (Linux-Player + Windows-Port als Oracle).
2. **BACKUP**: safe-guard.sh (erweitert um Android-Pfade).
3. **IMPLEMENTIEREN**: nur im Android-Release-Baum.
4. **BUILD**: NDK-Cross-Compile (ABI) → `.so`/APK; Exit 0.
5. **TEST**: Host-Unit-Tests (ABI-kompatibel) + ADB-Instrumented-Tests.
6. **COMPATIBILITY**: Golden-Vergleich (Hashes/JSON) Android ↔ Linux ↔ Windows.
7. **VERIFIED** nur bei grünen Gates → `PORT_STATUS.md` + `FEATURE_MATRIX.md`.

## Harte Gates (Plan)
- APK startet auf Emulator + echtem Gerät (arm64-v8a + x86_64).
- Codec/Format: Golden-Tests (Hashes/JSON) — gleiche Resultate wie Desktop.
- YouTube/Netzwerk: echter Stream (Transport-Entscheidung nötig).
- Playlist-Queue: Play ohne Ausklappen + Merge + gemischte Queue.
- Clean-Install: frisches Gerät/Emulator, nur APK-Inhalt.
- Keine falschen PASS: "APK baut" ≠ "APK läuft".

## Fehlerbehandlung
- Lösen ODER BLOCKED loggen. Nie still Feature weglassen.

## Stolperfallen
- Touch-UI vs Desktop-Parität (Playlist-Pane, EPG, Tabs).
- ABI-Vielfalt (arm64/armv7/x86_64) → APK-Größe, libVLC-Plugins.
- Android-Lebenszyklus (Activity pausiert → Playback pausieren).