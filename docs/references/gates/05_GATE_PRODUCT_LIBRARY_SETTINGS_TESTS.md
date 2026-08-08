# Gate 5 — Produktreife: Library, Settings, Responsive UI, Regression

## UI-Entscheidung

Der heutige Tkinter-Code hat echte Funktionalität und dient als Referenz.

Für das Ziel-Mockup und langfristige Wartbarkeit:

```text
PySide6 / Qt Widgets
```

bevorzugen.

Keine Big-Bang-Neuschreibung des Playback-Kerns.

Migration:

```text
Backend/Core stabilisieren
→ neue Qt UI gegen dieselben Interfaces
→ Tk UI entfernen, wenn Feature-Parität erreicht
```

## Zielstruktur

```text
mpcasu/
    app.py
    playback/
    media_model.py
    ui/
        main_window.py
        video_view.py
        audio_view.py
        playlist_view.py
        sidebar.py
        transport.py
        timeline.py
        diagnostics.py
        settings_dialog.py
        media_info.py
        fullscreen.py
    library/
        db.py
        scanner.py
        repository.py
        thumbnails.py
    settings/
        store.py
```

## Library

SQLite.

Minimal schema:

```sql
media(
  id INTEGER PRIMARY KEY,
  canonical_uri TEXT UNIQUE,
  file_size INTEGER,
  mtime_ns INTEGER,
  duration_ms INTEGER,
  title TEXT,
  media_type TEXT,
  container TEXT,
  video_codec TEXT,
  audio_codec TEXT,
  width INTEGER,
  height INTEGER,
  added_at INTEGER,
  last_seen_at INTEGER
);

play_history(
  media_id INTEGER PRIMARY KEY,
  last_position_ms INTEGER,
  last_played_at INTEGER,
  play_count INTEGER
);

favorites(
  media_id INTEGER PRIMARY KEY
);

watched_folders(
  path TEXT PRIMARY KEY,
  recursive INTEGER
);
```

Playlists dürfen eigene Tabellen erhalten.

## Scanner

- background worker;
- cancellable;
- inkrementell über `size + mtime`;
- keine Komplettanalyse bei jedem Start;
- ffprobe/libVLC Metadata;
- Thumbnail Cache;
- entfernte Dateien markieren statt sofort blind löschen.

## Settings

QSettings oder klarer JSON/TOML Store.

Bereiche:

```text
General
Playback
Video
Audio
Subtitles
Library
CASU
Hardware
Network
Interface
Hotkeys
Diagnostics
```

Keine Einstellung ohne reale Wirkung.

## Resume

Persistieren:

```text
media identity
last position
selected audio track
selected subtitle
audio/subtitle delay
playback rate
```

Resume nur anbieten, wenn:

```text
position > threshold
and position < duration - threshold
```

## Responsive Regeln

Groß:

```text
Sidebar + Video + Playlist + Diagnostics
```

Mittel:

```text
Sidebar + Video + collapsible Playlist
```

Klein:

```text
Icon sidebar + Video
```

Audio-only:

```text
dedicated Audio View
```

Kein Cropping des offiziellen Logos.

## Regressionstest-Pyramide

### Fast unit

Unter 10 Sekunden:

- state models;
- manifest/native structures;
- scheduler;
- settings;
- database;
- queue.

### Media integration

Synthetische kleine Medien generieren:

- H264/AAC;
- H265/AAC;
- VP9/Opus;
- AV1/Opus;
- MP3;
- FLAC;
- VFR;
- multi-audio;
- subtitles;
- chapters.

### GUI smoke

Linux CI:

```text
Xvfb
+ dummy audio sink
```

Prüfen:

- main window opens;
- file opens;
- video backend attaches;
- time advances;
- play/pause/seek;
- menus;
- resize.

## A/V Sync Tests

Für den native CASU-Backend eine instrumentierbare Test-Sink bauen.

Audio-Sink meldet:

```text
presented sample PTS
```

Video-Sink meldet:

```text
presented frame PTS
```

Assertion z. B.:

```text
abs(video_pts - audio_clock) < documented tolerance
```

Nicht bloß UI-Position vergleichen.

## Long Run

Mindestens 1–2 Stunden synthetischer Loop im Nightly-Test.

Messen:

- RSS growth;
- open file descriptors;
- threads;
- dropped frames;
- queue growth;
- A/V drift.

## VLC-Kompatibilitätsvertrag

Keine statische Behauptung „alle VLC-Formate“.

Testregel:

```text
if bundled/current libVLC opens fixture
and MPCASU refuses/fails it
→ MPCASU compatibility bug
```

Extensions dürfen den Open-Dialog nicht begrenzen.

## Abnahme

Gate PASS wenn Library/Settings nicht mehr Platzhalter sind und die
P0-Playback-Matrix automatisiert reproduzierbar grün ist.
