# Gate 1 — Native segmentierte CASU-Payload, Key-States und Seek-Index

## Ausgangspunkt

`CASUNAT1` ist nützlich und soll lesbar bleiben.

Es ist aber ein Envelope:

```text
Header
Manifest
Originaldatei als Blob
```

Das ist noch keine segmentierte native Payload.

## Migrationsentscheidung

`CASUNAT1` weiterhin **read-only kompatibel** unterstützen.

Für den segmentierten Referenzcodec eine neue native Revision verwenden,
z. B.:

```text
CASUNAT2
```

Die endgültige Magic/Version in der Format-Spezifikation festschreiben.

Nicht das alte Format stillschweigend umdefinieren.

## Ziel des ersten echten nativen Codecs

Noch nicht auf maximale Kompressionsrate optimieren.

Erstes Ziel:

```text
korrekt
standalone
deterministisch
seekbar
verlustfrei
segmentiert
```

Erst danach Performance-/Kompressionsoptimierung.

## Empfohlene Chunk-Architektur

```text
FILE HEADER
MANIFEST
STREAM TABLE
CHUNKS...
SEEK INDEX
INTEGRITY TABLE
FOOTER
```

### Chunk-Typen

Mindestens:

```text
STREAM_CONFIG
VIDEO_KEY_STATE
VIDEO_TILE_UPDATE
VIDEO_FORMAT_CHANGE
AUDIO_BLOCK
SUBTITLE_PACKET
CHAPTER_TABLE
ATTACHMENT
SEEK_INDEX
INTEGRITY_TABLE
RECOVERY_POINT
END
```

## Video-Referenzpayload

### VIDEO_KEY_STATE

Enthält einen vollständig rekonstruierbaren `CanonicalVideoFrame`.

Für jede Plane:

```text
plane index
width
height
bit depth
bytes/sample
compression
uncompressed length
compressed length
payload
```

Lossless komprimieren, z. B. Zstandard.

Falls Zstandard als Dependency nicht gewünscht ist, zuerst `zlib` als
Referenz verwenden und später ersetzen. Die Containerstruktur darf nicht von
einem einzigen Kompressor abhängen.

### VIDEO_TILE_UPDATE

Enthält nur geänderte Tiles:

```text
frame PTS
tile id
region
base state hash
new state hash
plane slices
lossless compressed payload
```

Ein `HOLD` braucht keine Pixel-Payload.

## Key-State-Strategie

Key-State erzwingen bei:

- Streamstart;
- Formatwechsel;
- Auflösungswechsel;
- beschädigter Dependency Chain;
- konfigurierbarem Maximalabstand;
- optional Scene Cut zur Begrenzung von Seek-Kosten.

Reference default:

```text
max key-state interval: 2–5 seconds
```

aber nicht auf Frame-Rate basieren; in Source-PTS planen.

## Audio

Für die erste native Referenzversion Korrektheit vor Dateigröße.

Option A — empfohlen für Reference Codec:

```text
decoded canonical PCM blocks
+ original timing
+ channel layout
+ sample format
+ sample rate
+ lossless compression
```

Damit ist der native Player unabhängig vom ursprünglichen Audiocodec.

Später kann ein Packet-Preservation-Modus folgen.

Mehrere Audio-Streams getrennt behandeln.

## Subtitles

Textuntertitel:

```text
start PTS
duration
codec/type
language
forced/default
UTF-8/text or format payload
```

Bitmap-Untertitel als Payload-Block erhalten.

## Manifest / Stream Table

Pro Stream mindestens:

```text
stream_id
type
source_index
codec/origin
time_base
language
default
forced
width/height or sample_rate/channels
pixel/sample format
extradata if needed
```

## Seek Index

Ein echter Index benötigt Byte-Offets.

Entry:

```text
stream_id
target_pts
key_state_pts
key_state_chunk_offset
first_dependency_chunk_offset
```

Globaler Zeitseek:

1. Zielzeit in Stream-Timebase umrechnen.
2. Nächsten Key-State <= Ziel suchen.
3. Direkt zu Byte-Offset springen.
4. Key-State laden.
5. Updates bis Ziel anwenden.
6. Audio/Subtitles ab passendem Index lesen.

Kein lineares Lesen vom Dateianfang.

## Writer-API

Vorschlag:

```python
class NativeCasuWriter:
    add_stream(config) -> stream_id
    write_video_key_state(stream_id, frame)
    write_video_update(stream_id, update)
    write_audio_block(stream_id, block)
    write_subtitle(stream_id, packet)
    add_chapters(...)
    add_attachment(...)
    finalize() -> Path
```

Writer schreibt zunächst in Temp-Datei.

Erst `finalize()`:

- Index schreiben;
- Integrity Table schreiben;
- Footer schreiben;
- fsync;
- atomar ersetzen.

## Reader-API

```python
class NativeCasuReader:
    streams() -> list[StreamDescriptor]
    seek(target_time) -> ReconstructionPlan
    read_key_state(plan)
    iter_updates(plan)
    iter_audio(...)
    iter_subtitles(...)
    verify(...)
```

## Native v1 nicht löschen

`read_native()` für CASUNAT1 erhalten.

Neue Reader-Factory:

```python
open_casu(path)
```

entscheidet:

```text
JSON sidecar
CASUNAT1 envelope
CASUNAT2 segmented
```

und liefert einen expliziten Typ.

## Abnahme

Native Gate PASS nur wenn:

```text
source
→ strict converter
→ CASUNAT2
→ delete/rename original source
→ read CASUNAT2
→ reconstruct video/audio
```

funktioniert.

Keine temporäre Wiederherstellung der Original-MP4 als Abkürzung.
