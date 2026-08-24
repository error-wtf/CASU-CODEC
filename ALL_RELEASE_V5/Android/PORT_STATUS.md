# PORT_STATUS — Android (v5.0.0, Stand 24.08.2026)

**ONLINE:** MPCASU-Android-5.0.0.apk (SHA256SUMS-android.txt) — ERSTMALS im Release.

## Enthaltene Features
- WebView-Player (pure-web, same-origin) + casu_core JNI (detect/verify/extract).
- **AppWidget 4×1** (⏮ ▶/⏸ ⏭ + Titel + State) — Broadcasts → JS-Forwarding.
- **MediaSession** (Plattform-API) — Hardware-Keys/Lockscreen steuern physisch.
- **Media-Notification** (VLC-Stil): DecoratedMediaCustomViewStyle +
  Session-Token, ⏮ ▶/⏸ ⏭ im Panel — Screenshot-bewiesen.
- JNI-Crash-Fix (SIGABRT nach ~15 s auf jedem Start).
- LIVE-Zeitanzeige; POST_NOTIFICATIONS-Runtime-Request.

## Verification
- On-Device (Emulator): Installation/Start/Wiedergabe/Media-Keys/
  Widget-Broadcasts/Notification — crash-frei; Screenshots im Repo-Log.
- aapt: Service (mediaPlayback-Typ) + Permissions + Widget-Receiver.

## Nächste Schritte
- .aab + Play-Integrity; Widget-Preview-Image; Audio-Fokus; ExoPlayer-HLS.
