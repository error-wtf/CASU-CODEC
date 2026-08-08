# CASU Converter — Completion Plan auf Basis des aktuellen Codes

## Bereits vorhanden

Nicht neu bauen:

- Multi-file Auswahl;
- recursive folder scan;
- Queue List;
- deterministic output naming;
- pause between jobs;
- cancellation event;
- progress callback;
- native-envelope checkbox;
- verify output;
- JSON batch report.

## Jetzt umbauen

Die Conversion-Engine darf nicht in der Tk-Klasse bleiben.

Neue Library:

```text
casu/converter/
    job.py
    queue.py
    engine.py
    progress.py
    profiles.py
    report.py
    journal.py
```

GUI und CLI benutzen dieselbe Engine.

## Job

```python
@dataclass
class ConversionJob:
    source: Path
    output: Path
    profile: ConversionProfile
    status: JobStatus
    phase: JobPhase
    progress: float
    error: str | None
```

Phasen:

```text
PROBE
CANONICAL_DECODE
STRICT_STATE_BUILD
AUDIO_BUILD
SUBTITLE_BUILD
NATIVE_WRITE
INDEX
INTEGRITY
VERIFY
DONE
```

## Realer Fortschritt

Keine pauschalen 55/35-Prozentblöcke als Endzustand.

Progress soll nach Möglichkeit aus:

- Source Duration / PTS;
- decoded frame PTS;
- decoded audio samples;
- writer bytes;
- verification bytes

berechnet werden.

Jede Phase darf ein Gewicht haben, aber ihre interne Progresszahl ist real.

## Pause

Der heutige Pause-Button pausiert praktisch zwischen Jobs.

Das ehrlich benennen:

```text
Pause queue
```

Wenn Pause *innerhalb* eines laufenden Jobs gewünscht wird, Decoder/Writer
müssen echte cooperative checkpoints besitzen.

Nicht so tun als sei laufende FFmpeg-Decodierung pausiert, wenn sie weiterläuft.

## Cancel

Bestehende Cancellation beibehalten und auf Native Writer erweitern.

Bei Cancel:

- decoder stop;
- writer close;
- temp output löschen;
- journal aktualisieren;
- keine finale `.casu`.

## Journal / Resume

Optionaler Job-Journal:

```json
{
  "source_hash": "...",
  "profile": "...",
  "completed_key_states": [...],
  "last_verified_chunk": 123
}
```

Resume nur, wenn Source Hash und Profile exakt passen.

## Profiles

Technisch definieren:

### STRICT_REFERENCE

- source-resolution;
- exact tiles;
- lossless video states;
- lossless audio;
- no perceptual thresholds.

### VISUALLY_LOSSLESS

Erst aktivieren, wenn eigenständig validiert.

### ADAPTIVE

Experimentell markieren.

### LOW_POWER

Betrifft Converter-Ressourcennutzung, nicht Medienqualität:

- lower worker concurrency;
- process priority where safe.

## Analyze View

Vor Conversion:

```text
streams
duration
resolution
pixel format
bit depth
audio tracks
subtitles
chapters
attachments
estimated key-state count
estimated tile updates
```

Schätzungen als `ESTIMATE` markieren.

## Verify View

Native:

```text
Header
Manifest
Streams
Chunks
Seek Index
Integrity
Recovery
Roundtrip sample checks
```

## Reports

Pro Job:

```text
source hash
profile
tool versions
duration
frame count
key states
tile updates
hold count
audio blocks
subtitle packets
output bytes
elapsed
verification result
warnings
```

Exports:

```text
JSON
CSV
Markdown
```

## GUI

Converter-Icon:
offizielles bereitgestelltes Converter-Icon.

Header:
offizielles CASU-Logo.

Kein selbst erzeugtes Branding.

## Qt Migration

Converter darf zunächst Tk bleiben, solange Engine ausgelagert ist.

Danach dieselben Qt Theme Tokens wie MPCASU verwenden.

## Acceptance

Batch mit 20 Dateien:

- 3 unsupported/corrupt;
- 17 valide.

Erwartung:

- 17 Outputs;
- 3 saubere Failure-Einträge;
- keine Queue-Abstürze;
- Cancel hinterlässt keine halbfertige finale Datei;
- Verify findet absichtlich korrumpierte Datei.
