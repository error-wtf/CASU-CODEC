# INSTALL_AND_CODEC — Installation + Dateitypen (macOS, Plan)

## Installation (Ziel)
- `MPCASU-macOS-5.0.0.dmg` öffnen → `MPCASU.app` nach `/Applications` ziehen
  (oder Installer-Paket `.pkg`).
- Gatekeeper: App ist Developer-ID-signiert + notarisiert
  (kein "Unbekannter Entwickler"-Dialog).
- Portabel: `.app`-Bundle von überall startbar.

## Dateitypen (Ziel)
- `.casu`/`.mp5` → `MPCASU.app` via `CFBundleDocumentTypes` in Info.plist +
  LaunchServices (`lsregister`). Doppelklick im Finder öffnet den Player.

## Verifikation nach Installation (Ziel)
- `casu kind file.mp5` im Terminal (Binary im Bundle: `MPCASU.app/Contents/MacOS/`).
- `.casu`-Doppelklick → MPCASU.
- `CASU-Web-Backend.app` → `http://127.0.0.1:8497/web/`.

## Media-Codec (CODEC-001, geplant für v5.0)
- macOS-Pendant: AVFoundation-/CoreMedia-Decoder oder GStreamer-Filter für
  CASU/MP5 (geplant; wie bei Windows MF/DirectShow und Linux GStreamer).