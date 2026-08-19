# MPCASU / CASU-CODEC — Android Release-Planung (ALL_RELEASE_V5)

Ziel: **Android** (arm64-v8a, armeabi-v7a, x86_64), C++20 + Qt 6 for Android
(Qt bietet QtWebEngine für Android → eingebetteter Browser möglich),
libVLC-Android (libVLC.so + plugins), `.apk`/`.aab`.

Status: **geplant, noch nicht gebaut.** Dieser Ordner ist die Vorbereitung.

## Status (2026-08-19)

- Kein Android-Build vorhanden. Android SDK/NDK + Qt for Android nötig.
- Zielartefakt: `MPCASU-Android-5.0.0.apk` (bzw. `.aab` für Play Store).
- Besonderheit: Mobile-UI (Touch), kein Desktop-Fenster → UI-Anpassung des
  Qt-Players (Playlist-Pane, EPG, Web-Tabs als Fullscreen-Screens).

## Build (Plan)

```sh
# Qt for Android (aqtinstall): qtbase+qtwebengine (android_arm64_v8a, …)
# Android SDK + NDK (sdkmanager), JDK 17
cmake -S . -B build-android -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/build/cmake/android.toolchain.cmake \
    -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-24
cmake --build build-android
# APK-Bundling via Qt (androiddeployqt) → MPCASU-Android-5.0.0.apk
```

- libVLC: vlc-android-Builds oder prebuilt `libvlc.so` + plugins/ (ABI-spezifisch).
- ffmpeg: gebündelte .so für Media-Engines (oder libVLC nutzt eigene).
- yt-dlp: Android via Termux/urllib? — YouTube-Transport auf Android neu
  bewerten (yt-dlp braucht Python; Alternativen: innertube/yt-dlp-compiled).
  **Entscheidungsbedarf** (siehe PORT_STATUS).

## Apps (Ziel)

| App | Form | Anmerkung |
|-----|------|-----------|
| CLI `casu` | nicht sinnvoll (kein Shell) → Core-Libs als .so | ggf. Termux-Addon |
| Player MPCASU | `.apk` | Qt-GUI (Touch), libVLC, WebEngine-Tabs |
| Converter | `.apk` (optional) | Batch-Presets touchgerecht |
| Web-Backend | in-App (Loopback) | für Web-Provider-Streaming |

## Offene Punkte (v5.0, nach Nutzer-Freigabe)
- YouTube-Transport auf Android (yt-dlp-Frage).
- UI-Anpassung (Touch) vs Desktop-Parität.
- Play-Store vs Side-Load (Signing).