# Gate 6 — Formatrobustheit, Integrity, Recovery und Fuzzing

## Ziel

Ein `.casu`-Parser verarbeitet untrusted input.

Kein beschädigtes File darf:

- unbounded RAM allozieren;
- endlos laufen;
- außerhalb erlaubter Ziele schreiben;
- Integer Overflows erzeugen;
- unkontrolliert Dateien öffnen;
- Crash/Segfault verursachen.

## Integrity Ebenen

CASUNAT2:

1. Header Hash/CRC.
2. Manifest SHA-256.
3. Jeder Payload Chunk:
   - Länge;
   - CRC32 für schnelle Korruptionserkennung;
   - SHA-256 oder BLAKE3 in Integrity Table.
4. Seek Index Hash.
5. Footer Hash über kritische Struktur.

Keine Signatur mit Integrity verwechseln.

Kryptographische Autoren-Signatur ist optional und separat.

## Reader Limits

Zentrale `CasuLimits`:

```python
@dataclass(frozen=True)
class CasuLimits:
    max_manifest_bytes: int
    max_streams: int
    max_chunks: int
    max_chunk_bytes: int
    max_attachment_bytes: int
    max_total_uncompressed_frame_bytes: int
    max_width: int
    max_height: int
    max_channels: int
    max_sample_rate: int
    max_dependency_depth: int
```

Jede Allokation gegen Limits prüfen **bevor** Speicher reserviert wird.

## Chunk Validation

Prüfen:

```text
offset within file
length within file
no integer overflow
stream id exists
chunk type allowed for stream type
PTS finite/in range
dependency exists
dependency precedes use
tile region inside frame
hash encoding valid
uncompressed length plausible
```

## Recovery

Writer setzt periodische `RECOVERY_POINT`s.

Recovery Point enthält:

```text
last complete key-state offsets
last complete audio block offsets
partial index snapshot
integrity checkpoint
```

Bei Truncation:

Reader darf optional:

```text
recover_until_last_verified_point()
```

liefern.

Nie beschädigte Bytes als gültige Zustände erfinden.

Status:

```text
FULLY_VERIFIED
RECOVERED_PREFIX
FAILED
```

## Footer

Footer enthält:

```text
magic
file_version
manifest_offset
stream_table_offset
seek_index_offset
integrity_offset
last_recovery_offset
file_length
footer checksum
```

Damit kann Reader bei intaktem Footer schnell öffnen.

Bei kaputtem Footer optional Recovery Scan mit hartem Budget.

## Atomic Writer

Weiterverwenden, was `CASUNAT1` bereits gut macht:

```text
temp file
→ write
→ fsync
→ final metadata
→ fsync
→ os.replace
```

## Fuzzing

Python:

```text
atheris
```

oder vergleichbarer Fuzzer.

Targets:

```text
header parser
chunk header parser
manifest parser
seek index
integrity table
tile update parser
subtitle parser
```

Corpus:

- gültige minimale CASU-Datei;
- gültige Multi-Stream-Datei;
- Datei mit mehreren Key States.

Mutationen:

```text
truncated header
huge lengths
unknown versions
duplicate stream IDs
invalid offsets
overlapping chunks
cycle dependencies
bad hashes
invalid UTF-8
zip-bomb-like compressed payload
huge dimensions
negative/overflow timestamps
```

## Property Tests

Hypothesis:

- serialize → parse roundtrip;
- index sorted;
- seek plan never references future dependency;
- applying same update twice is detected/rejected where appropriate;
- corrupt one byte ⇒ verification fails;
- reader never returns unverified payload as VERIFIED.

## Abnahme

Gate PASS erst wenn Fuzzing über ein dokumentiertes Budget läuft, z. B.:

```text
>= several million parser executions or defined wall-clock campaign
0 crashes
0 hangs
0 uncontrolled allocations
```

und alle bekannten corrupt fixtures sauber fehlschlagen/recovern.
