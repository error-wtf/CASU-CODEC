# Current → Target Migration Map

## `casu/native.py`

### Heute

`CASUNAT1`:

```text
manifest + original source blob
```

### Behalten

- atomic writing;
- size limits;
- payload hash;
- backwards reader.

### Ergänzen

Neue Revision / Module:

```text
casu/native_v2/
    format.py
    reader.py
    writer.py
    chunks.py
    index.py
    integrity.py
    recovery.py
```

`native.py` kann Factory/Compatibility Entry Point werden.

---

## `casu/tiles.py`

### Heute

- uint8 ndarray;
- exact hash in strict mode;
- 2D/3D tile geometry.

### Ziel

Plane-aware:

```text
CanonicalVideoFrame
CanonicalPlane
PlaneTile
```

8/10/12-bit, YUV/RGB/alpha.

Preview-Analyzer bleibt getrennt.

---

## `casu/core.py`

### Heute

- ffprobe;
- preview video analyzer;
- audio RMS analyzer;
- Sidecar manifest.

### Ziel

Aufteilen:

```text
casu/legacy_analysis.py
casu/probe.py
casu/strict/...
```

`analyze_video` weiterhin als `preview/activity analysis`.

Nicht mehr als native STRICT benutzen.

---

## `casu/scheduler.py`

### Heute

Globaler Segment-Lookup mit Bisect.

### Ziel

Behalten als Sidecar-Scheduler.

Neu:

```text
casu/runtime/state_scheduler.py
casu/runtime/cache.py
casu/runtime/reconstruction.py
```

für Tile/PTS/Dependency/Key-State.

---

## `mpcasu_backend.py`

### Heute

LibVLC + CasuBackend, wobei CASUNAT1 temporär extrahiert wird.

### Ziel

Aufteilen:

```text
mpcasu/backends/base.py
mpcasu/backends/libvlc.py
mpcasu/backends/casu_compat.py
mpcasu/backends/casu_native.py
```

`casu_native.py` erbt **nicht** von LibVLC.

---

## `mpcasu_playback.py`

Controller ausbauen:

```text
OPENING
BUFFERING
SEEKING
ENDED
ERROR
```

Event Queue / backend-neutral.

---

## `mpcasu_player.py`

### Heute

Große Tk-Klasse.

### Ziel

Funktionskern nicht wegwerfen.

Schrittweise Qt UI:

```text
mpcasu/ui/*
```

Erst entfernen, wenn Feature-Parität.

---

## `casu_converter.py`

### Heute

Batch GUI besitzt Business Logic.

### Ziel

Engine in `casu/converter/` verschieben.

Tk/Qt GUI wird nur Client.

---

# Commit-Reihenfolge

Empfohlene kleine Commits:

1. `Introduce canonical frame model`
2. `Add PTS-aware strict decoder`
3. `Integrate source-resolution strict tile states`
4. `Define CASUNAT2 chunk model`
5. `Write native key-state and tile chunks`
6. `Build byte-offset seek index`
7. `Add per-chunk integrity and recovery points`
8. `Add native CASU reader reconstruction`
9. `Add NativeCasuBackend without extraction`
10. `Add native video renderer`
11. `Add native PCM audio path`
12. `Complete media track/device model`
13. `Extract converter engine`
14. `Add library/settings persistence`
15. `Add full regression/fuzz gates`

Nach jedem Commit:

```text
compile
fast tests
targeted integration test
git diff --check
```
