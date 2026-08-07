# CODEX BRIEF 02 — Möglicher Entwicklungsweg

## Ziel des ersten Prototyps

Baue einen reproduzierbaren Software-Prototypen, der vorhandene MP4-/MP3-Dateien und klassische framebasierte Ausgaben verarbeitet und eine zusätzliche segmentierte Zustandskarte erzeugt.

Der Prototyp muss zunächst beweisen:

1. Legacy-Daten können unverändert verarbeitet werden.
2. Statische oder redundante Bereiche können zuverlässig erkannt werden.
3. Segmentinformationen können ohne Zeit- oder Inhaltsverfälschung erzeugt werden.
4. Potenzielle Einsparungen bei Rendering, Speicherverkehr und Display-Updates können gemessen werden.

---

# Phase 0 — Messbare Baseline

Bevor optimiert wird, erfasse Referenzwerte.

Für Video:

- Auflösung
- FPS / VFR-Zeitstempel
- Codec
- Bitrate
- Anzahl Frames
- Frame-Timestamps
- A/V-Synchronität
- CPU-Zeit
- Speicherbandbreite soweit messbar
- Decoding-Zeit
- Rendering-/Copy-Zeit
- Energieverbrauch soweit das System Messwerte liefert

Für Audio:

- Sample Rate
- Kanalzahl
- Codec
- Bitrate
- Dauer
- Packet-/Frame-Timestamps

Die Baseline muss gespeichert werden, damit jede Optimierung gegen dieselbe Quelle verglichen werden kann.

---

# Phase 1 — Legacy Decoder Layer

Nutze zunächst etablierte Decoder, z. B. FFmpeg/libavcodec.

Keine eigene MP4- oder MP3-Decodierung erfinden.

Pipeline:

```text
MP4 / MP3
   ↓
Standarddecoder
   ↓
Frames / Audio Samples + originale Timestamps
   ↓
Segment Analyzer
```

Wichtig:

Der Decoder bleibt die Quelle der Wahrheit für die zeitliche Reihenfolge.

---

# Phase 2 — Tile-basierte Change Detection

Zerlege Videoframes in Tiles, beispielsweise:

- 16×16
- 32×32
- 64×64

Die Tilegröße soll konfigurierbar sein.

Für jedes Tile berechne mindestens:

- Pixel-Differenz
- Luminanz-Differenz
- Farb-Differenz
- strukturelle Differenz
- optional Motion-Vektor-Hinweise des Videodecoders

Beispielzustände:

```text
UNCHANGED
MINOR_CHANGE
LOW_MOTION
MOTION
HIGH_MOTION
CRITICAL
```

Wichtig:

`UNCHANGED` darf nur verwendet werden, wenn das Ergebnis innerhalb einer streng definierten Toleranz liegt.

Es soll zusätzlich einen vollständig verlustfreien Modus geben:

```text
pixel-identical only
```

Dort gilt ein Tile nur dann als unverändert, wenn es tatsächlich identisch ist.

---

# Phase 3 — Temporal State Map

Erzeuge eine Datenstruktur für jedes Segment.

Beispiel:

```json
{
  "tile_id": 42,
  "rect": [640, 320, 64, 64],
  "state": "HOLD",
  "valid_from_us": 12000000,
  "valid_until_us": 12166667,
  "priority": "normal",
  "max_latency_us": 16667,
  "source": "video"
}
```

Die Zustandskarte soll getrennt vom Originalmedium gespeichert werden können:

```text
movie.mp4
movie.ssc.json
```

Damit bleibt das Original vollständig kompatibel.

---

# Phase 4 — Scheduler

Der Scheduler entscheidet aus den Zustandskarten, welche Regionen tatsächlich neue Arbeit benötigen.

Grundregeln:

```text
HOLD:
    keinen neuen Zustand berechnen, wenn nicht erforderlich

LOW_RATE:
    nur bei echter Änderung aktualisieren

MOTION:
    originale Medien-Timestamps respektieren

REALTIME:
    minimale Latenz

LOSSLESS_REALTIME:
    keinerlei zeitliche Optimierung
```

Der Scheduler soll keine Bildinformation erraten.

---

# Phase 5 — Legacy Rendering Adapter

Auf bestehenden Monitoren kann der physische Panel-Refresh nicht vollständig kontrolliert werden.

Trotzdem kann Software sparen durch:

- Dirty Rectangles
- Damage Tracking
- Tile Cache
- weniger Compositing
- weniger GPU-Draws
- weniger VRAM-Kopien
- Vermeidung identischer Renderpasses
- gegebenenfalls VRR/PSR verwenden, wenn das System es unterstützt

Wichtig:

Ein alter 60-Hz-Monitor bleibt ein 60-Hz-Monitor.

Die erste Softwareversion optimiert vor allem die Rechen- und Datenpipeline.

---

# Phase 6 — Video-spezifische Optimierung

Nutze Informationen, die ein Videocodec bereits besitzt:

- I/P/B-Frame-Struktur
- Block-/Motion-Vektoren
- Residualinformation
- Scene Changes
- Macroblock-/Coding-Unit-Aktivität

Aber:

Decoder-Motion-Vektoren sind Hinweise und keine alleinige Wahrheit für die visuelle Ausgabe.

Die endgültige Entscheidung muss mit dem tatsächlich decodierten Bild übereinstimmen.

---

# Phase 7 — Audio

MP3 soll zunächst vollständig korrekt dekodiert werden.

Audio ist bereits zeitlich anders strukturiert als Video und muss nicht künstlich in Display-Tiles gezwungen werden.

Mögliche Analyse:

- Stille
- sehr niedriger Pegel
- aktive Bereiche
- Packet-/Frame-Grenzen

Aber standardmäßig:

> Keine zeitliche Veränderung des Audiostreams.

Kein Time-Stretching, keine Pitch-Korrektur, kein Entfernen kurzer „unwichtiger“ Audioereignisse.

---

# Phase 8 — Energie-/Leistungsmessung

Für jeden Testfall erfassen:

- CPU utilization
- GPU utilization
- GPU busy time
- RAM/VRAM transfer soweit verfügbar
- Anzahl verarbeiteter Tiles
- Anzahl HOLD-Tiles
- tatsächlich neu gerenderte Pixel
- durchschnittliche aktive Fläche
- Energieaufnahme / Batterieverbrauch soweit verfügbar
- Latenz
- Dropped Frames
- A/V-Sync
- Qualitätsabweichung

Ausgabe als reproduzierbarer Benchmark-Report.

---

# Phase 9 — Native segmentierte Datenstruktur

Erst nachdem der Legacy-Prototyp funktioniert, kann ein eigenes Binärformat entstehen.

Mögliche Hauptobjekte:

```text
GLOBAL_HEADER
STREAM_INFO
STATE_KEYFRAME
SEGMENT_UPDATE
SEGMENT_HOLD
MOTION_MAP
TIMING_MAP
AUDIO_PACKET
METADATA
INDEX
```

Ein kompletter neuer Key-State wird nur benötigt:

- beim Start
- bei Seek
- nach Fehlern
- bei Scene Changes
- in konfigurierbaren Abständen zur Robustheit

Dazwischen werden Zustandsänderungen übertragen.

---

# Phase 10 — Native Hardware

Später mögliche Hardwareziele:

- Memory-in-Pixel
- Partial Refresh
- LTPO
- Panel Self Refresh
- reflektive LCDs
- bistabile / ePaper-artige Panels
- tileweise unabhängige Refresh-Domänen

Dann kann dieselbe Zustandskarte direkt physische Panel-Updates steuern.

---

## MVP

Der erste ernsthafte MVP soll:

1. `input.mp4` lesen.
2. Frames und originale Timestamps dekodieren.
3. Frames in Tiles zerlegen.
4. unveränderte Tiles erkennen.
5. eine `.ssc.json` oder `.ssc.bin` Map schreiben.
6. dieselbe MP4 korrekt wiedergeben.
7. während der Wiedergabe nur geänderte Tiles im eigenen Renderer neu zeichnen.
8. gegen einen normalen Full-Frame-Renderer benchmarken.
9. beweisen, dass Output und Timing gleich bleiben.
10. Einsparungen oder Mehrkosten offen reporten.

Wenn der Prototyp keinen Vorteil bringt, muss er dies ehrlich messen und anzeigen. Keine geschönten Benchmarks.
