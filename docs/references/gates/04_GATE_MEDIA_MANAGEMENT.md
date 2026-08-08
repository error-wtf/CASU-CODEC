# Gate 4 — Vollständiges Media Management

## Ziel

Aus numerischem „Track cycling“ wird ein echtes Media-Modell.

## Gemeinsames Datenmodell

Neue Datei:

```text
mpcasu/media_model.py
```

Modelle:

```python
@dataclass(frozen=True)
class TrackDescriptor:
    id: int
    stream_index: int | None
    kind: Literal["video", "audio", "subtitle"]
    name: str
    language: str | None
    codec: str | None
    default: bool
    forced: bool
    channels: int | None = None
    channel_layout: str | None = None
    sample_rate: int | None = None
    width: int | None = None
    height: int | None = None

@dataclass(frozen=True)
class ChapterDescriptor:
    index: int
    title: str
    start_s: float
    end_s: float | None

@dataclass(frozen=True)
class AudioDeviceDescriptor:
    id: str
    name: str
    backend: str
```

Beide Backends liefern dieselben Modelle.

## Legacy / libVLC

Vorhandene Track-Description-Funktionen erweitern.

Wenn libVLC-Version APIs mit Sprache/Codec bereitstellt:

- verwenden;
- runtime-detect;
- keine erfundenen Metadaten.

Wenn nur Name/ID verfügbar:

- unbekannte Felder `None`;
- nicht aus Dateinamen raten.

## Audio Devices

libVLC Audio Output Device Enumeration kapseln.

Benötigt:

```text
list_audio_devices()
current_audio_device()
set_audio_device(id)
```

UI:

```text
Audio
  Output Device
    System Default
    HDMI
    USB DAC
    ...
```

Hotplug:

- mindestens beim Öffnen des Menüs neu enumerieren;
- später event-basiert, falls Plattform-API verfügbar.

## External Subtitles

Die vorhandene `add_external_subtitle()`-Grundlage erweitern.

Bevorzugt:

- libVLC slave/subtitle API nutzen, falls Runtime verfügbar;
- nur als Fallback Media reopen;
- aktuelle Position und Playback-State erhalten.

Unterstützung:

```text
Open subtitle…
Drag & Drop subtitle
Subtitle delay
Enable/disable
```

Kein stilles Verlusten der Wiedergabeposition.

## Chapters

Der vorhandene Chapter Count/Set-Code ist nur der Anfang.

UI braucht:

```text
Chapter 1 — Intro
Chapter 2 — ...
```

Wenn libVLC nur Nummern liefert:

```text
Chapter 1
Chapter 2
```

Keine Fantasietitel.

Timeline bekommt Marker, sofern Startzeiten verfügbar sind.

## CASU Native

Stream Table aus CASUNAT2 erzeugt dieselben `TrackDescriptor`s.

Track-Wechsel darf die Backend-Abstraktion nicht brechen.

## Track Menüs

Kein Button „Audio → cycle“.

Echte Menüs / Popover:

```text
Audio
  ✓ German — AC-3 5.1
    English — AAC Stereo
    Commentary — Stereo

Subtitles
  ✓ Off
    German
    English Forced

Video
  ✓ Main Video
```

## Delay

Benutzerfunktionen:

```text
Audio delay ±
Subtitle delay ±
Reset
```

Werte persistent pro Media-ID speichern.

## Abnahme

Gate PASS, wenn Testmedien mit:

- 2 Audio-Tracks;
- 2 Subtitle-Tracks;
- forced subtitle;
- chapters;
- externer SRT;
- mehreren Audio Devices;

vollständig in UI und Backend getestet sind.
