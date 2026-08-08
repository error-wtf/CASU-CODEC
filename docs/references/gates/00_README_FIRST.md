# CASU / MPCASU — Release-Gate Implementation Kit

## Zweck

Dieses Paket ist ein konkreter Arbeitsauftrag für Codex auf Basis des aktuellen
Repository-Stands vom 8. August 2026.

Es ersetzt **nicht** die bestehende Release Policy. Es erklärt, wie die sechs
Release-Gates technisch umgesetzt werden sollen und welche vorhandenen
Grundlagen weiterverwendet werden müssen.

## Nicht neu erfinden — das ist bereits vorhanden

Der aktuelle Code besitzt bereits brauchbare Grundlagen:

- `casu.native`
  - `CASUNAT1`
  - atomarer Writer
  - Manifest-Hash
  - Payload-SHA-256
  - standalone Envelope mit eingebetteten Originalbytes
- `casu.tiles`
  - deterministische Tile-Regionen
  - exakte `uint8`-Tile-Hashes
  - `HOLD`/`UPDATE`-Primitive
  - erste `S(x,y,t)`-Struktur für kanonische Arrays
- `casu.core`
  - FFmpeg/ffprobe Legacy-Analyse
  - streaming/chunked Audioanalyse
  - Cancellation
  - Fortschrittscallback
  - reduzierte Gray8-Analyse-State-Map
- `casu.scheduler`
  - indexierter globaler Zeitintervall-Lookup
- `CASUConverter`
  - mehrere Dateien
  - rekursive Ordner
  - Queue
  - Pause zwischen Jobs
  - Cancel
  - deterministische Ziele
  - Sidecar/native-envelope Umschaltung
  - Verify
  - JSON Batch Report
- `LibVLCBackend`
  - in-process libVLC
  - Linux/X11, Windows/HWND, macOS/NSObject Ansätze
  - Lifecycle-Events teilweise
  - Audio/Video/Subtitle-Track-Grundlagen
  - externe Untertitel-Grundlage
  - Chapter-Grundlage
  - Frame Step
  - Playback Rate
- `MPCASU`
  - Playlist-Grundlagen
  - Resume-Grundlage
  - tatsächliche libVLC-Wiedergabe
  - offizielles Branding

Diese Teile **erweitern**, nicht blind wegwerfen.

## Was die sechs Gates wirklich bedeuten

1. **Native CASU-Payload**  
   Nicht mehr nur eine Originaldatei als Blob in `CASUNAT1`, sondern ein
   eigenständiger segmentierter Medienzustand mit Key-States und echtem
   Random-Access-Index.

2. **Source-resolution STRICT**  
   Keine `160x90 gray8`-Analyse als STRICT-Grundlage. Exakte, PTS-aware,
   source-resolution dekodierte Plane-/Tile-Zustände.

3. **Nativer Playerpfad**  
   `.casu → Reader → Scheduler → State Cache → Renderer/Audio`, ohne
   temporäres Extrahieren des Legacy-Payloads.

4. **Vollständiges Media Management**  
   Reale Track-Modelle, Subtitles, Chapters, Audio Devices, externe
   Untertitel, Language/Default/Forced-Metadaten.

5. **Produktreife**  
   Library, Settings, Resume/History, responsive UI und echte
   Playback-Regressions.

6. **Formatrobustheit**  
   Conformance, Integrity, Recovery, Fuzzing und Resource-Limits.

## Strikte Reihenfolge

Nicht sechs Baustellen gleichzeitig halb implementieren.

```text
Gate 2 STRICT
   ↓
Gate 1 Native Payload
   ↓
Gate 6 Integrity/Recovery-Grundlage
   ↓
Gate 3 Native Player
   ↓
Gate 4 Media Management
   ↓
Gate 5 Product / Regression
```

Gate 2 kommt technisch vor Gate 1, weil der native Writer ohne eine
vertrauenswürdige kanonische State-Erzeugung nur falsche Payloads persistent
machen würde.

## Definition COMPLETE

Ein Gate ist nur COMPLETE, wenn:

```text
implementation
+ unit tests
+ integration tests
+ negative tests
+ clean package install
+ documented format/API
+ real fixture validation
```

vorhanden sind.

Keine Funktion aufgrund eines Buttons oder einer Klasse als fertig markieren.
