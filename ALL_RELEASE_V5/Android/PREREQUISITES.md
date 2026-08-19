# PREREQUISITES — Toolchain + Beschaffung (Android)

Status: **noch nichts beschafft** (Projekt geplant).

## Benötigt (Beschaffungsliste für den ersten Android-Build)
| Komponente | Bezugsquelle | Zweck |
|------------|--------------|-------|
| Android SDK + NDK (r26+) | sdkmanager / developer.android.com | Build-Toolchain |
| JDK 17+ | OpenJDK | APK-Bundling |
| Qt 6 for Android (arm64-v8a, armeabi-v7a, x86_64) inkl. **QtWebEngine** | qt.io (aqtinstall) | GUI + eingebetteter Browser |
| libVLC Android (libvlc.so + plugins) | videolan.org (vlc-android, prebuilt) | Playback |
| CMake + Ninja (Host) | vorhanden | Build |
| Gradle (via Qt androiddeployqt) | automatisch | APK |
| Signing-Key (Keystore) | Nutzer | APK-Signierung |

## Host-Erweiterung (dieser Linux-Rechner)
- Android SDK/NDK können auf diesem Ubuntu-Host installiert werden
  (Cross-Compile wie beim Windows-Port) — Android-Emulator für Tests optional.

## Lizenz-Hinweis
Qt LGPL, VLC GPL/LGPL, FFmpeg GPL/LGPL, zstd BSD, SQLite Public Domain,
yt-dlp Unlicense → `THIRD_PARTY_LICENSES/` im APK (Gate `licenses`).