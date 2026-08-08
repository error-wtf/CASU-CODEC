# Gate 2 — Source-resolution STRICT

## Ziel

STRICT ist die Vertrauensbasis von CASU.

Der bestehende Preview-Analyzer:

```text
ffmpeg
→ fps filter
→ 160x90
→ gray8
```

bleibt als schneller **Activity Analyzer** erhalten.

Er darf aber niemals die Grundlage von `STRICT` sein.

## Neue Architektur

Neue Module:

```text
casu/strict/
    model.py
    decoder.py
    canonical.py
    tiles.py
    state_builder.py
```

### Bevorzugte Decoder-Schnittstelle

Für die Referenzimplementierung PyAV/libav verwenden, weil pro decodiertem
Frame benötigt werden:

```text
PTS
time_base
pixel format
width/height
planes
color metadata
frame metadata
```

Keinen künstlichen `fps=`-Filter einsetzen.

Kein Raten von Zeitstempeln aus:

```text
frame_index / fps
```

STRICT benutzt die tatsächlichen Präsentationszeitpunkte der Quelle.

## CanonicalVideoFrame

Definiere ein unveränderliches Modell:

```python
@dataclass(frozen=True)
class CanonicalPlane:
    index: int
    width: int
    height: int
    bytes_per_sample: int
    bit_depth: int
    subsample_x: int
    subsample_y: int
    data: bytes

@dataclass(frozen=True)
class CanonicalVideoFrame:
    pts: int
    time_base_num: int
    time_base_den: int
    duration: int | None
    width: int
    height: int
    pixel_format: str
    color_range: str | None
    color_primaries: str | None
    color_transfer: str | None
    color_space: str | None
    chroma_location: str | None
    planes: tuple[CanonicalPlane, ...]
```

### Wichtige Regel

Stride-/Padding-Bytes sind **nicht** Teil der visuellen Nutzdaten.

Pro Plane nur aktive Samples zeilenweise in eine deterministische,
paddingfreie Bytefolge übernehmen.

## Pixel-Format-Regel

Keine heimliche Farbraumkonvertierung.

Für STRICT gilt:

- wenn der Decoder native Planes zuverlässig liefert: native Plane-Geometrie
  und Samples kanonisieren;
- 8/10/12/16-Bit erhalten;
- YUV-Subsampling erhalten;
- Alpha erhalten;
- Farbraum-Metadaten in den Frame-State-Hash aufnehmen.

Wenn sich Pixel-Format, Auflösung oder relevante Farbraum-Metadaten ändern:

```text
FORCE KEY STATE
```

## Tile Mapping

Tile-Koordinaten werden im Luma-/Display-Raster definiert.

Beispiel 64x64 Display-Tile.

Für jede Plane wird die Region anhand des Subsamplings abgebildet:

```text
YUV420:
Y  : 64x64
Cb : 32x32
Cr : 32x32
```

Ein Tile-State-Hash muss enthalten:

```text
tile coordinates
plane layout
active plane bytes
pixel format
relevant color metadata
```

## STRICT-Regel

```text
HOLD ⇔ current_state_hash == previous_state_hash
```

Keine Schwelle.

Keine SSIM.

Keine Mean Absolute Difference.

Keine Wahrnehmungsheuristik.

## Zeitmodell

Speichere Zeit grundsätzlich rational:

```text
pts
time_base_num
time_base_den
```

`seconds` nur als abgeleitete UI-Darstellung.

Dies verhindert Rundungsfehler.

## StateBuilder

Für jeden präsentierten Frame:

1. Frame kanonisieren.
2. Falls erster Frame / Formatwechsel / Key-State-Zwang:
   - `KEY_STATE`
3. Sonst Tile-Hashes berechnen.
4. Unveränderte Tiles:
   - `HOLD`
5. Geänderte Tiles:
   - `UPDATE`
6. Gültigkeit endet beim nächsten Source-PTS.
7. Keine künstlichen Zwischenzeitpunkte erzeugen.

## Tests

Pflichtfixtures synthetisch erzeugen:

1. RGB24 identisch.
2. Ein Pixel verändert.
3. Änderung nur in Chroma.
4. YUV420 8-bit.
5. YUV420P10.
6. Alpha-Änderung.
7. Farbraum-Metadatenwechsel.
8. Auflösungswechsel.
9. VFR:
   - 0 ms
   - 41 ms
   - 83 ms
   - 200 ms
10. B-Frame-Quelle.

Assertions:

```text
identical tile → HOLD
1 changed source sample → UPDATE
source PTS preserved exactly
no fps-filter timestamps
unsupported canonicalization → fail closed
```

## Abnahme

Gate ist erst bestanden, wenn der Produktionspfad `STRICT` tatsächlich diesen
Decoder/StateBuilder benutzt.

`casu.tiles` kann als Primitive weiterverwendet werden, muss aber von reinem
`uint8 ndarray` auf ein Plane-aware CanonicalFrame-Modell erweitert werden.
