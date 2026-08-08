# Gate 3 — Nativer CASU-Playerpfad ohne Payload-Extraktion

## Ausgangspunkt

Aktuell:

```text
CASUNAT1
→ verify
→ extract original payload to /tmp
→ libVLC opens temp file
```

Das ist eine korrekte Kompatibilitätsbrücke, aber **kein nativer CASU-Pfad**.

## Ziel

```text
CASUNAT2
→ NativeCasuReader
→ Reconstruction Scheduler
→ Tile State Cache
→ Video Renderer

CASUNAT2
→ Audio Reader
→ Audio Clock / Audio Sink
```

Ohne MP4/MKV/MP3 zu extrahieren.

## Backend-Trennung

Nicht `CasuBackend(LibVLCBackend)` für native CASU weiterverwenden.

Stattdessen:

```python
class MediaBackend(Protocol):
    open(...)
    play()
    pause()
    stop()
    seek(...)
    position()
    duration()
    tracks(...)
    close()

class LibVLCBackend(MediaBackend):
    ...

class NativeCasuBackend(MediaBackend):
    ...
```

Sidecar/CASUNAT1 dürfen weiterhin über Legacy Compatibility laufen.

CASUNAT2 muss `NativeCasuBackend` wählen.

## Thread-Modell

Mindestens:

```text
UI THREAD
CONTROL / STATE
CASU READ / DECOMPRESS
VIDEO RECONSTRUCTION
AUDIO FEED
```

Keine Disk-I/O/Decompression im UI-Thread.

## TileStateCache

Schlüssel:

```text
(stream_id, tile_id)
```

Wert:

```text
state_hash
plane data
valid_from_pts
valid_until_pts
```

Funktionen:

```text
apply_key_state
apply_update
hold
invalidate
clear_stream
snapshot_frame
```

Bounded Memory:

- Max-Cache-Budget konfigurierbar;
- niemals unbounded Tile-History halten;
- nur benötigten aktuellen Rekonstruktionszustand plus begrenzten Seek-Puffer.

## Scheduler

Der bestehende `CasuScheduler` ist für globale Sidecar-Intervalle nützlich.

Für native CASU neuen Scheduler:

```text
CasuStateScheduler
```

Der Scheduler arbeitet auf:

```text
PTS
stream_id
tile_id
dependency/reference hash
deadline
lifecycle
```

nicht nur auf `start_s/end_s`.

## Seek

Seek-Transaktion:

1. Playback Clock pausieren.
2. Audio Queue flush.
3. Video Reconstruction Queue flush.
4. Reader Seek Index abfragen.
5. Tile Cache invalidieren.
6. Key-State laden.
7. Updates bis Target PTS anwenden.
8. Audio beim passenden Block positionieren.
9. Subtitle-State rekonstruieren.
10. Clock auf Ziel setzen.
11. Wiedergabe fortsetzen.

Kein stale Tile darf nach Seek sichtbar bleiben.

## Video Renderer

Für die erste Referenzimplementierung ist CPU korrekt genug.

Bei Qt:

```text
Canonical reconstructed frame
→ QImage
→ VideoView
```

Später GPU texture upload / partial dirty-region updates.

Wichtig:

Die Architektur muss bereits `dirty_regions` aus dem Scheduler übergeben,
damit ein späterer GPU-Renderer nicht neu erfunden werden muss.

Renderer API:

```python
present(frame, pts, dirty_regions)
```

## Audio

Für nativen Reference Codec:

```text
canonical PCM block
→ bounded audio queue
→ QAudioSink / platform sink
```

Audio Clock ist bei Audio+Video Master.

Video präsentiert Frame entsprechend Source-PTS gegen diese Clock.

Video-only:

```text
monotonic playback clock
```

## Keine Zeitmanipulation

Standard:

```text
NO interpolation
NO smoothing
NO duplicated synthetic frames
NO time stretch
NO pitch shift
```

Display Refresh und Source Timeline bleiben getrennt.

## Backend-Auswahl

```text
CASUNAT2 → NativeCasuBackend
CASUNAT1 → CompatibilityBackend
JSON sidecar → CompatibilityBackend
legacy media → LibVLCBackend
```

In Diagnostics exakt anzeigen.

## Tests

1. Native video-only.
2. Native audio-only.
3. Native A/V.
4. Pause/resume.
5. seek forward/backward.
6. rapid seeks.
7. target immediately after key-state.
8. target immediately before next key-state.
9. corrupt update → fail/recover.
10. EOF.
11. cache invalidation.
12. no tempfile extraction assertion.

## Harte Assertion

Test muss Prozess-/Filesystem-Ebene prüfen:

```text
CASUNAT2 playback creates no restored .mp4/.mkv/.mp3 temp file
```

## Abnahme

Gate PASS wenn der Player das originale Legacy-Medium vollständig löschen oder
umbenennen kann und CASUNAT2 weiterhin direkt abspielt.
