# CODEX MASTER EXECUTION PROMPT

Arbeite die sechs dokumentierten CASU/MPCASU Release-Gates vollständig ab.
Behandle den aktuellen Repository-Stand als wertvolle Grundlage, aber nicht als
fertiges Produkt.

Lies zuerst diese Hilfsdateien in Reihenfolge:

1. `00_README_FIRST.md`
2. `01_GATE_SOURCE_RESOLUTION_STRICT.md`
3. `02_GATE_NATIVE_PAYLOAD_KEYSTATES_SEEK.md`
4. `06_GATE_INTEGRITY_RECOVERY_FUZZING.md`
5. `03_GATE_NATIVE_PLAYER_PATH.md`
6. `04_GATE_MEDIA_MANAGEMENT.md`
7. `05_GATE_PRODUCT_LIBRARY_SETTINGS_TESTS.md`
8. `07_CONVERTER_COMPLETION_PLAN.md`
9. `08_CURRENT_TO_TARGET_MIGRATION_MAP.md`
10. `09_RELEASE_ACCEPTANCE_MATRIX.md`

## Harte Regeln

- CASUNAT1-Kompatibilität erhalten.
- CASUNAT1 nicht fälschlich zum segmentierten Codec umdeklarieren.
- Source-resolution STRICT arbeitet auf echten Source-PTS und kanonischen
  source-resolution Planes.
- Die bestehende 160x90 Gray8-Analyse bleibt nur Activity Hint.
- Kein `frame_index / analysis_fps` als Source-Timeline für STRICT.
- Native CASU benötigt echte Key-States, Tile-Updates und Byte-Offset Seek Index.
- CASUNAT2 muss standalone sein.
- Der native Player darf für CASUNAT2 keine Original-MP4/MP3 temporär extrahieren.
- Native CASU-Backend und LibVLC-Backend strikt trennen.
- Legacy-Kompatibilität bleibt über libVLC.
- Wenn libVLC einen Legacy-Input unterstützt, darf MPCASU ihn nicht durch eine
  eigene kleine Extension-Liste künstlich blockieren.
- Keine Fake-Metriken.
- Keine Fake-Waveforms.
- Keine UI-Funktion ohne Backend.
- Offizielle vom Auftraggeber gelieferte Logos und Icons verwenden:
  CASU Logo, CASU Codec Icon, CASU Converter Icon, MPCASU Logo, MPCASU Icon.
- Keine Ersatzgrafiken generieren.
- Keine Behauptung COMPLETE ohne Tests.

## Technische Priorität

```text
P0A canonical source-resolution frame model
P0B PTS-aware STRICT
P0C CASUNAT2 format/chunks
P0D key states + tile payloads
P0E seek index + integrity/recovery
P0F native reader reconstruction
P0G NativeCasuBackend without extraction

P1 media management
P2 converter engine completion
P3 library/settings/Qt UI
P4 exhaustive regression/fuzz/performance
```

## Nach jeder Phase

Führe aus und dokumentiere:

```text
python -m compileall
fast unit tests
targeted media integration tests
clean wheel build/install
clean Debian build/install where applicable
git diff --check
```

## Kein Abkürzen

Nicht akzeptabel:

```text
CASUNAT2 = Originaldatei erneut als ein Blob
STRICT = downscaled gray threshold
native player = payload to temp + libVLC
seek index = nur Sekunden ohne Byte-Offsets
recovery = nur Fehlermeldung
library = Listbox
settings = Konstanten
media tracks = next-track cycle only
```

## Abschlussartefakte

Aktualisiere nach realem Stand:

```text
RELEASE_POLICY.md
MPCASU_FEATURE_COMPLETION_MATRIX.md
MPCASU_IMPLEMENTATION_AUDIT.md
CASU_FORMAT_SPECIFICATION.md
IMPLEMENTATION_REPORT.md
TEST_REPORT.md
FUZZ_REPORT.md
```

Jedes Gate erhält:

```text
OPEN
PARTIAL
PASS
```

mit konkreter Testevidenz.

Wenn ein Gate nicht PASS ist, sage das explizit und arbeite weiter, statt den
Release als fertig zu markieren.
