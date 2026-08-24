# MPCASU / CASU-CODEC — Android (ALL_RELEASE_V5)

Ziel: **Android** (arm64-v8a, armeabi-v7a, x86_64) — WebView-Shell um die
pure-web Touch-UI, same-origin LoopbackServer aus APK-Assets, byte-
paritätischer casu_core per NDK (JNI), Plattform-MediaSession + AppWidget +
Media-Notification. Signiertes Release-APK.

Status: **v5.0.0 ONLINE** (24.08.2026) — siehe
https://github.com/error-wtf/CASU-CODEC/releases/tag/v5.0.0
(`MPCASU-Android-5.0.0.apk`, SHA256 in `SHA256SUMS-android.txt`).

## Status (2026-08-24)

- **APK gebaut + signiert** (keystore/mpcasu-release.jks, CN=MPCASU),
  minSdk 24, targetSdk 34, 3 ABIs, ~5.1 MB.
- **On-Device verifiziert** (Emulator casu-test, x86_64):
  - Installation, Start, Web-UI rendert, Radio-Stream spielt.
  - **MediaSession** = aktive Media-Button-Session; Hardware-Tasten
    (PLAY_PAUSE/NEXT/PREVIOUS) steuern die Wiedergabe physisch.
  - **Media-Notification** (VLC-Stil): DecoratedMediaCustomViewStyle mit
    MediaSession-Token, ⏮ ▶/⏸ ⏭ im Benachrichtigungs-Panel — Screenshot-
    bewiesen („ERRORCOMPANY - LIVE" mit Pause-Glyph + Progress).
  - **AppWidget 4×1**: Titel, Playing/Paused-State, ⏮ ▶/⏸; Broadcasts →
    PlayerBridge → `next(±1)` / `#play`-Klick; Provider im appwidget-
    Service gebunden.
  - **JNI-Crash-Fix** (ecbfdc4): detectKind ließ casu::CasuError durchschießen
    (SIGABRT ~15 s nach jedem Start) — jetzt ERROR-String wie die
    Geschwister-Calls.
  - **LIVE-Zeitanzeige** (bf7f430) in assets/web/app.js.

## Architektur

| Komponente | Datei | Zweck |
|---|---|---|
| WebView-Shell | `MainActivity.java` | LoopbackServer (same-origin) + WebView, JS/DOM-storage, autoplay |
| Native Core | `CasuCore.java` + `cpp/casu_jni.cpp` | detectKind / verifyCasunat2 / extractToCache — byte-paritätische Core-Quellen (win-release/src/core) per NDK |
| Same-Origin-Server | `LoopbackServer.java` | Serviert APK-Assets unter 127.0.0.1:<port> |
| MediaSession | `McasuMediaSession.java` | Plattform-API (kein androidx), Callbacks → JS-Forwarding, PlaybackState/Metadata-Mirror |
| Notification | `PlaybackNotificationService.java` | Foreground-Service (mediaPlayback), DecoratedMediaCustomViewStyle + Session-Token, ⏮ ▶/⏸ ⏭ als PendingIntents |
| Widget | `McasuWidgetProvider.java` | 4×1 RemoteViews, Broadcast-Buttons |
| Bridge | `PlayerBridge.java` | 1-s-Poll von #title/#play → Widget+Session+Notification; JS-Forwarding raus |

## Build

```sh
cd android
ANDROID_HOME=/opt/android-sdk JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
  gradle assembleRelease
# → app/build/outputs/apk/release/app-release.apk (signiert)
```

Emulator (headless, KVM): `emulator -avd casu-test -no-window -no-audio
-no-boot-anim -gpu swiftshader_indirect`. ⚠️ Auf dem Build-Host teilt sich
KVM die VM mit Windows-QEMU — hängende QEMU-Threads → Kill + Retry
(gpu off hilft gelegentlich).

## Nächste Schritte (v5.0.1+)

- `.aab` für Play Store (bundleRelease) + Play-Integrity.
- Widget-Vorschau-Image (previewImage) + Widget im Launcher-Setup.
- Audio-Fokus-Handling (AUDIOFOCUS_GAIN) + Pausing bei Anruf.
- Chromecast/Output-Switcher-Tiefe (System-Dialog vorhanden).
- Optional: ExoPlayer-Pfad für HLS-Streams (aktuell WebView-media).
