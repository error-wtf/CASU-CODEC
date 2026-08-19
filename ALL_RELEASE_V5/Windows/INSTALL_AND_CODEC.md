# INSTALL_AND_CODEC — Installation + Dateitypen (Windows)

## Installation
1. **Empfohlen:** `MPCASU-Setup-3.0.0.exe` (NSIS, CASU-Icon).
   - Installiert nach `%ProgramFiles%\MPCASU`.
   - Registriert `casu` systemweit im PATH (AddToSystemPath).
   - Registriert Dateitypen `.casu` und `.mp5` → MPCASU.
   - Startmenü- + Desktop-Verknüpfungen, Uninstaller (entfernt PATH-Einträge
     korrekt, ohne andere Einträge zu leeren — unter Wine verifiziert).
2. **Portabel:** ZIP entpacken → `MPCASU.exe` starten.

## Verifikation nach Installation
- `casu kind file.mp5` aus beliebigem Verzeichnis (PATH).
- `.casu`/`.mp5`-Datei → Doppelklick öffnet MPCASU.
- Uninstall → PATH-Segmente anderer Programme bleiben erhalten.

## Endgültige Verifikation
- PATH/Registry-Verhalten nur auf **echtem Windows** endgültig verifizierbar
  (BLOCKER-004); Wine-Test ist Vorab-Check.

## Media-Codec (CODEC-001, geplant für v5.0)
- Geplant: CASU/MP5 als **Media-Foundation-/DirectShow-Decoder** registrieren,
  damit die Container auch in beliebigen Windows-Playern/Direktoren dekodieren.
- Status: **nicht gebaut** (BLOCKER-005). Entscheidung des Nutzers: "Auch als
  Media-Codec (MF/DirectShow)" — Umsetzung im v5.0-Zug.

## Linux-Kompatibilität
- Gleiche Container wie Linux (CASUNAT1/NAT2/MP5), gleiche CLI/CLI-Ergebnisse
  (Golden byte-identisch), gleiche Playlist-Queue-Semantik.
- Pure-Web im Paket byte-identisch zur Linux-Fassung.