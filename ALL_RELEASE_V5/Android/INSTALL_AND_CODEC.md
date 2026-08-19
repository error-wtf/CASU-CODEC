# INSTALL_AND_CODEC — Installation + Dateitypen (Android, Plan)

## Installation (Ziel)
- `.apk` direkt installieren (Sideload) ODER via Play Store (`.aab`).
- Berechtigungen: Storage (Playlists/Medien), Internet (Streaming), optional
  Media-Library-Scan.

## Dateitypen (Ziel)
- `.casu`/`.mp5` → MPCASU via Intent-Filter (ACTION_VIEW) in
  `AndroidManifest.xml`; Datei aus Dateimanager/Downloads öffnet den Player.

## Verifikation nach Installation (Ziel)
- APK startet; Playlist importieren + durchspielen; Web-Tabs laden Provider.
- `.casu`-Datei aus Download ordnet sich MPCASU zu.

## Media-Codec (CODEC-001, geplant für v5.0)
- Android-Pendant: MediaCodec-Decoder oder libVLC-Access für CASU/MP5
  (geplant; wie Windows MF/DirectShow und Linux GStreamer).