# Release Acceptance Matrix

| Gate | PASS-Kriterium | Automatischer Nachweis |
|---|---|---|
| 1 Native Payload | CASUNAT2 enthält segmentierte Video-/Audio-Payload, Key-States, byte-offset Seek Index | source löschen, native Datei roundtrip |
| 2 STRICT | Source-resolution, Plane-aware, PTS-aware, exakt | one-sample mutation tests, VFR tests |
| 3 Native Player | CASUNAT2 spielt ohne Payload-Extraktion | temp-dir assertion + video/audio test sinks |
| 4 Media Management | Tracks/Subtitles/Chapters/Audio Devices vollständig | multi-track fixture + device mock |
| 5 Product | Library/Settings/Resume + responsive UI + Playback regression | DB tests + GUI smoke + format matrix |
| 6 Robustness | Integrity/Recovery/Fuzzing/Resource limits | corrupt corpus + fuzz campaign |

## P0 Fixtures

Erzeuge kleine, redistributable Testmedien automatisiert:

```text
rgb24_cfr.mp4
yuv420p_vfr.mp4
yuv420p10_hevc.mkv
h264_aac.mp4
h265_aac.mkv
vp9_opus.webm
av1_opus.mkv
audio_multi_track.mkv
subtitles_multi.mkv
chapters.mkv
audio.flac
audio.mp3
```

## Gate 1 Tests

```text
native header/version
stream table
key state count > 0
tile update count > 0 on moving source
seek index offsets valid
delete source → reader still works
roundtrip frame hashes equal
roundtrip PCM hashes equal
```

## Gate 2 Tests

```text
same source tile = HOLD
one sample difference = UPDATE
10-bit difference detected
chroma-only difference detected
alpha-only difference detected
PTS exact
VFR exact
unsupported plane layout fails closed
```

## Gate 3 Tests

```text
play native
pause
resume
seek 10%
seek 90%
seek backward
rapid seek
EOF
no restored legacy tempfile
cache invalidated on seek
audio/video presentation PTS within documented tolerance
```

## Gate 4 Tests

```text
list/select audio track
list/select subtitle
external SRT
forced subtitle metadata
chapter select
audio device list/set
track selections persist per media
```

## Gate 5 Tests

```text
add library folder
incremental rescan
history
resume
settings persistence
playlist persistence
resize 1024x600 → 2560x1440
HiDPI
legacy H264/H265/VP9/AV1/MP3/FLAC playback
network URL smoke
```

## Gate 6 Tests

```text
truncation
bad hash
bad index offset
unknown mandatory chunk
oversized declared allocation
dependency cycle
invalid tile region
invalid stream id
corrupt compressed payload
recovery to last verified point
fuzz no crash/hang
```

## Release Rule

Keine `1.0 native complete`-Bezeichnung, solange irgendein Gate `PARTIAL` oder
`OPEN` ist.

Development/RC-Packages dürfen existieren, müssen ihren Status sichtbar und
ehrlich kennzeichnen.
