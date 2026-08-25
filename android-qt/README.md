# MPCASU on Android — der echte Linux-Player (PySide6-on-Android)

**Architektur-Entscheidung:** Android bekommt den **echten Linux-MPCASU**
(`mpcasu_qt` + `casu`-Module, PySide6) — nicht pure-web, nicht web-casu, nicht
eine WebView-Shell. Nur das UI bekommt Small-Screen-Verbesserungen (Rail/
Drawer, wie bei anderen Playern).

## Status (24.08.2026)

| Phase | Umfang | Status |
|---|---|---|
| 1. Toolchain-Proof | pyside6-android-deploy → minimale APK | **BLOCKIERT** — siehe „Der fehlende Baustein" |
| 2. mpcasu_qt bootet | Import-Shims (ffprobe-Ersatz, App-Dirs) | Scaffold fertig (`main.py`, `shims/android_compat.py`) |
| 3. libVLC-Android | ctypes → libvlc.so (AAR), Backend-Bindings | offen (libVLC-Android AAR beschaffen) |
| 4. ffprobe/ffmpeg-Ersatz | MediaMetadataRetriever (Probes/Tags/Cover), libVLC-PCM (VIZ) | Shim-Skelett fertig, Ausbau offen |
| 5. Small-Screen-UI | Rail/Drawer/Touch im Qt-UI | offen |
| 6. Feature-Parität | EPG/IPTV/Library/YouTube (yt-dlp läuft in bundled Python!) | offen; Recording/Converter später |

## Der fehlende Baustein (Phase 1)

`pyside6-android-deploy` ist installiert und funktionsfähig — aber er braucht
die **PySide6- und shiboken6-Android-Wheels** (arm64-v8a, zur Host-Version
passend). Diese sind in öffentlichen Kanälen NICHT verfügbar (geprüft):
- PyPI: keine Android-Wheels (6.8.2–6.11.2 alle geprüft)
- download.qt.io/official_releases/QtForPython: nur src-Tarballs
- aqt-Metadaten: Android endet bei 6.7.3, Arch-Download fehlerhaft

**Beschaffung (einer von zwei Wegen):**
1. **Qt-Account:** Qt-Online-Installer → Komponente „PySide6 for Android"
   (Wheels liegen hinter dem Installer-Login).
2. **Selbstbau:** qt/pyside-Quelle + python-for-android Toolchain
   (mehrtägig, Anleitung: wiki.qt.io/QtForPython/Android).

Liegen die Wheels in diesem Ordner, baut `./build.sh` die APK.

## Build (sobald Wheels da sind)

```sh
./build.sh                      # findet die Wheels automatisch
# oder explizit:
./build.sh PySide6-6.11.2-…-android_aarch64.whl shiboken6-6.11.2-…-android_aarch64.whl
```

Der Deploy packt `mpcasu_qt/` + `casu/` + Backend-Module aus dem Repo-Root
(das echte Linux-Player-Codebase) plus `main.py` + `shims/`.
