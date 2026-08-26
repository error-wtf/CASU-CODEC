# ANDROID REWRITE PLAN — MPCASU Native (v6)

Stand: 26.08.2026. Auftrag: komplette Neuentwicklung der Android-APK von Grund auf.
Referenz = MPCASU Qt Linux (mpcasu_qt/ + casu/). Kein WebView-Player mehr.
Alter Code: android-legacy-backup/ (nur Notfall-Referenz, gilt als broken).

## 1. ARCHITEKTUR

Native Java-App, null externe Dependencies:
- PlayerService (Foreground) besitzt PlayerEngine (MediaPlayer-Wrapper),
  MediaSession, Notification, Widget-Bridge.
- MainActivity = Single-Activity, 5 Bottom-Nav-Tabs (Symbole):
  PLAY / QUEUE / LIBRARY / WEB / SETTINGS.
- Kein Loopback-Server: MediaPlayer spielt file://, content://, http(s)://,
  rtsp:// direkt. YouTube direkt ueber Innertube-Resolve (ANDROID-Client).
- CASU via casucore-JNI: detect/verify + NEU extractCasunat2Audio
  (decode_audio_block -> WAV in Cache) -> MediaPlayer.
- Persistenz: JSON in filesDir (queue.json, settings.json, favorites.json).
  Queue-Fix: Persistenz im SERVICE (ueberlebt Activity-Tod), Save bei jeder
  Mutation + onStop/onDestroy, atomic writes.

## 2. FEATURE-MATRIX Qt -> Android

| Qt-Funktion | Android | Plan |
|---|---|---|
| Formate mp3/flac/wav/ogg/m4a/aac/opus/mp4/mkv/mov/webm | MediaPlayer (API 29+) | V1 |
| .casu/.mp5 | JNI detect/verify/extract -> WAV/resolved | V1 Audio |
| Streams http/HLS/RTSP | MediaPlayer direkt | V1 |
| YouTube Search | Innertube search (ANDROID client) | V1 |
| YouTube Playback | Innertube player -> URL -> MediaPlayer | V1 |
| Spotify/Tidal/HearThis/Netflix/Browse | Provider-WebView (Login) | V1 |
| Queue add/remove/move/rename/multi/search/clear | RecyclerView + ActionMode | V1 |
| Playlist-Gruppen (expandierbar) | Gruppen-Rows, Play-all | V1 |
| Playlists M3U/M3U8/PLS/XSPF/JSPF/ASX/WPL/RAM/JSON | PlaylistIO Parser/Writer | V1 |
| Shuffle/Repeat off-all-one | Engine-Modes, persistent | V1 |
| Seek/+-10s/Stop/Rate/Mute/Volume | MediaPlayer+PlaybackParams | V1 |
| A-B-Loop | Engine-Timer | V1 |
| Snapshot | MediaMetadataRetriever -> Pictures/MPCASU | V1 |
| Frame step | seek(+0.04)+pause | V1 |
| Untertitel srt/vtt extern | Parser + Overlay-Rendering | V1 |
| Track-Wahl Audio/Video/Subtitle | getTrackInfo/selectTrack | V1 |
| Chapters | MediaPlayer liefert keine -> P2 | P2 |
| Audio-Delay | P2 (Subtitle-Delay V1) | P2 |
| Visualizer (nur Welle) | audiofx.Visualizer -> WaveView | V1 |
| Cover | embedded art + MediaStore | V1 |
| Library Suche/Artists/Albums/Genres/Favoriten | MediaStore + JSON-Favoriten | V1 |
| Watched folders | SAF persistente Grants + Scan | V1 |
| IPTV/EPG (M3U + XMLTV now/next) | M3U-Channels + XMLTV-Miniparser | V1 |
| Recording (Stream->Datei, Split) | Byte-Copy nach Music/MPCASU | V1 |
| Converter | braucht ffmpeg -> P2, ehrlich | P2 |
| Widget 4x1 | RemoteViews prev/play/next/title | V1 |
| Notification/MediaSession | MediaStyle + Seek + SeekTo | V1 |
| Oeffnen-mit/Share | VIEW/SEND -> Queue+Play | V1 |
| Settings-Persistenz | settings.json | V1 |
| Session-Restore Queue+Position | queue.json + position | V1 |
| MPRIS | = MediaSession (Aequivalent) | V1 |
| Info/Diagnostics | Info-Dialog | V1 |
| About | Settings-Sektion | V1 |
| CASU-Video-Tiles | P2 (Audio V1) | P2 |

## 3. UI (symbol-basiert, schoen, touch-first)

Palette: BG #0b0d10 / Surface #12151a / Accent #ff1e2d / Text #f2f4f7 /
Muted #9aa3ad / Border #262b31. Rounded 12dp.
- BottomNav 5 Tabs: PLAY / QUEUE / LIBRARY / WEB / SETTINGS (48dp Targets).
- NowPlaying: Cover/Video-Karte, Titel, rote Seekbar, Zeit, Transport
  (prev/play/next, 72dp Play), Sekundaerzeile (shuffle/repeat/A-B/snapshot/
  record/rate), Volume.
- Queue: Rows mit Badge (MP3/STREAM/YT/CASU), aktiv rot, Swipe-x, Header
  (+ / URL / save / load), Shuffle+Repeat-Footer, Suche.
- Library: Suche + Chips (All/Artists/Albums/Genres/Favorites).
- Web: Provider-Grid -> WebView mit Top-Bar (Name + x).
- Settings: PLAYBACK / VISUALIZER / LEGAL / ABOUT.
- Responsiv: Phone portrait Bottom-Nav; Landscape/Tablet breit = 2 Spalten;
  Video fullscreen mit Rotation.

## 4. KOMPONENTEN

org/casu/mpcasu/: PlayerEngine, MediaItem, QueueStore, PlaylistIO,
YouTubeClient, SubtitleLoader, EpgLoader, Library, WaveView, CasuBridge,
PlayerService, McasuMediaSession, McasuWidgetProvider, MainActivity,
ProviderActivity. res/: layouts, vector drawables, themes.
cpp/: casu_jni.cpp erweitert um extractCasunat2Audio.

## 5. BAU-REIHENFOLGE (jeder Schritt lauffaehig)

1. Manifest/Gradle/Theme-Grundgeruest
2. MediaItem+QueueStore+PlayerEngine (+Unit-Tests)
3. PlaylistIO (+Format-Fixture-Tests)
4. PlayerService+Session+Notification+Widget
5. MainActivity: Nav+NowPlaying(Audio)+Queue
6. Video (TextureView, Fullscreen, Rotation)
7. Library+SAF+Favoriten
8. YouTubeClient(+Tests)+Such-Tab
9. Provider-WebView+EPG
10. Visualizer+Cover+Subtitles+Snapshot+A-B+Rate+Recording
11. Settings+Session-Restore
12. On-Device-Tests (adb), Unit-Suite, APK -> dist -> Release

## 6. FEHLER-TAXONOMIE (nie Haenger, klare Toasts)

invalid-url, unsupported-source, network-offline, timeout, http-error,
consent-required, geo-blocked, auth-required, resolver-changed,
codec-unsupported, file-missing, permission-denied, playback-failed.
Jede Resolve-/Open-Aktion mit Timeout + try/catch -> Toast + Status.
