# PORT_STATUS — Linux (v5.0.0, Stand 24.08.2026)

**ONLINE:** https://github.com/error-wtf/CASU-CODEC/releases/tag/v5.0.0 (4 DEBs + Pure-Web-ZIP)

## Enthaltene Features (über v3.0.0 hinaus)
- **MPRIS D-Bus** (`org.mpris.MediaPlayer2.casu`): GNOME-Shell-Mediamenü +
  playerctl — Play/Pause/Next/Prev, Metadata, Volume, Loop/Shuffle,
  PropertiesChanged, Seeked. Wie bei VLC/co in den Benachrichtigungen
  steuerbar (DesktopEntry=mpcasu passt zu packaging/mpcasu.desktop).
- **Gezeichnete Nav-Icons** (QPainter): keine Unicode-Tofu-Boxen mehr,
  identisch zu Windows.
- Sidebar scrollt bei knappen Fensterhöhen (keine geclippten Labels).
- Live-Streams: „LIVE"-Zeitanzeige; Cover/Thumbnail-Kette: Cache →
  CASUNAT2 → thumbnail_for → ffmpeg-Extrakt (Stream-Seek).
- Playlist-Gruppen, Multi-Select, Converter-ETA, Recording, Library,
  EPG Extended-M3U/XMLTV (v5.0.0 Full-Parity-Umfang).

## Verification
- pytest **441 passed / 0 failed** (inkl. test_mpris.py 9 Checks,
  test_live_time_parity.py 6 Checks).
- MPRIS live verifiziert (dbus-run-session + gdbus/busctl + Wire-Capture),
  auch für die INSTALLIERTE DEB-Kopie.

## Nächste Schritte
- Equalizer-API (libvlc_audio_equalizer_*, P3).
- QtVideoSurfaceSink für CASUNAT2-native Untertitel/Cover (P3).
