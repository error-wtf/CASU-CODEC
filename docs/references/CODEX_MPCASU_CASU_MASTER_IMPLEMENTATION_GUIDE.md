# CODEX MASTER-AUFTRAG — CASU CODEC, CASU CONVERTER UND MPCASU PLAYER PRODUKTIONSREIF MACHEN

## Kontext und Priorität

Dieser Auftrag hat Vorrang vor kosmetischen Minimalimplementierungen, Demo-Scaffolding und dem bloßen Abhaken sichtbarer UI-Elemente.

Der aktuelle Repository-Stand wurde auditiert. Er ist ein brauchbarer Forschungs-/Kompatibilitätsprototyp, aber **noch kein vollständiger CASU-Codec, kein produktionsreifer Converter und kein vollwertiger MPCASU-Media-Player**.

Arbeite nicht darauf hin, möglichst schnell viele Punkte als „implemented“ zu markieren. Arbeite darauf hin, dass jede sichtbare Funktion technisch real, robust, getestet, responsiv und visuell sauber umgesetzt ist.

**Keine Attrappen. Keine Fake-Werte. Kein ffplay. Kein VLC.exe. Keine generischen Ersatzlogos.**

Die vom Auftraggeber gelieferten offiziellen Assets sind verbindlich:

- offizielles rotes **CASU-Logo**
- offizielles rotes **MPCASU-Player-Logo**
- offizielles **MPCASU-Player-Icon**
- offizielles **CASU-Converter-Icon**
- rotes MPCASU-UI-Mockup als visuelle Sollreferenz

Diese Assets müssen tatsächlich verwendet werden und dürfen nicht durch selbst erzeugte Ersatzgrafiken ersetzt werden.

---

# TEIL A — BESTANDSAUDIT: WAS IM AKTUELLEN CODE NOCH FEHLT

## A1. CASU ist aktuell noch ein JSON-Sidecar, kein nativer Codec/Container

Der aktuelle `.casu`-Output ist im Kern ein JSON-Manifest, das auf die Originaldatei verweist.

Das ist als Legacy-Kompatibilitätsschicht sinnvoll, aber es ist noch **kein eigenständiger nativer Mediencontainer mit eigener Nutzlast, Seek-Index, Recovery-Blöcken, Segment-Payloads und nativer Decoder-Pipeline**.

Daher:

- den aktuellen Sidecar-Stand nicht als endgültigen nativen CASU-Codec behandeln;
- Sidecar-Kompatibilität erhalten;
- einen klar getrennten nativen CASU-Formatpfad entwickeln;
- keine Behauptung „native CASU 1.0 complete“, bevor dieser Pfad existiert.

Empfohlene Trennung:

```text
CASU Sidecar Compatibility 0.x
CASU Native Container 1.x
```

oder eine andere explizite Versionsgrenze.

---

## A2. Die drei Analysemodi sind derzeit faktisch nur Labels

Aktuell existieren:

```text
strict
visually_lossless
adaptive
```

Der Modus wird gespeichert und validiert, aber die eigentliche Video-/Audioanalyse verwendet derzeit dieselben Schwellen und denselben Algorithmus.

Das muss geändert werden.

### STRICT

STRICT darf ein Segment nur als unverändert markieren, wenn die relevante rekonstruierte Information tatsächlich identisch ist.

Für Video:

- Quellauflösung berücksichtigen;
- kanonisches Pixel-/Plane-Format definieren;
- per Tile echte Byte-/Pixelidentität prüfen;
- keine downscaled grayscale Näherung als „strict pixel identical“ deklarieren.

### VISUALLY_LOSSLESS

Eigene dokumentierte Metriken:

- SSIM / MS-SSIM oder äquivalent;
- PSNR als Zusatzmetrik;
- Farbabweichung sinnvoll berücksichtigen;
- Schwellen explizit dokumentieren;
- niemals Default.

### ADAPTIVE

Experimentell:

- Inhalt;
- Bewegung;
- visuelle Relevanz;
- Segmentgröße;
- verfügbare Rechenleistung

dürfen berücksichtigt werden.

Dieser Modus muss klar als verlustbehaftet/experimentell gekennzeichnet bleiben, sofern er Information zusammenfasst.

---

## A3. Die aktuelle räumliche Segmentierung speichert keine echte Tile-State-Map

Aktuell wird zwar eine geänderte Tile-Quote berechnet, aber es werden nicht die tatsächlichen räumlichen Tile-Zustände über die Zeit gespeichert.

Benötigt wird mindestens:

```text
tile_id
x
y
width
height
start_pts
end_pts
state
reference_state
change_type
priority
deadline
hash / integrity
```

Die eigentliche CASU-Idee benötigt:

```text
f(x, y, t)
```

nicht nur einen globalen Wert wie:

```text
mean_changed_tile_ratio
```

Implementiere deshalb echte räumlich-zeitliche State Maps.

---

## A4. Der Scheduler ist aktuell nur ein linearer Zeitintervall-Lookup

Der aktuelle Scheduler kennt im Wesentlichen nur:

```text
start
end
state
```

und durchsucht Intervalle linear.

Benötigt werden:

- Segment-ID;
- Tile-/Region-ID;
- Lifecycle;
- Dependencies;
- Key States;
- Seek Index;
- Invalidierung;
- Cache;
- Deadline;
- Priorität;
- Recovery;
- effiziente Suche.

Lifecycle mindestens:

```text
CREATE
UPDATE
HOLD
MOVE
REPLACE
INVALIDATE
RELEASE
```

Für Lookup keine lineare O(n)-Suche bei großen Dateien verwenden.

Verwende einen Index nach Zeit und Segment-ID.

---

## A5. Es fehlt ein echter nativer CASU Reader/Writer

Neue Module bauen:

```text
casu/format/constants.py
casu/format/model.py
casu/format/reader.py
casu/format/writer.py
casu/format/index.py
casu/format/integrity.py
casu/format/recovery.py
```

Ein nativer Container benötigt mindestens:

```text
MAGIC
VERSION
FEATURE FLAGS
STREAM TABLE
METADATA
STATE KEY BLOCKS
SEGMENT UPDATE BLOCKS
AUDIO BLOCKS
SUBTITLE BLOCKS
ATTACHMENTS
SEEK INDEX
INTEGRITY TABLE
FOOTER
```

Reader muss unbekannte neuere Pflichtfeatures sicher ablehnen.

---

## A6. Format-Magic und Identität sauber trennen

CASU ist der Codec/Container.

MPCASU ist der Player.

Die native CASU-Signatur darf daher nicht semantisch so aussehen, als sei MPCASU der Dateiformatname.

Definiere eine eindeutige CASU-Magic für das native Format, z. B. konzeptionell:

```text
CASU\0
```

plus Version/Feature-Bits.

Bestehende Sidecar-Kompatibilität kann weiterhin ihre alte Kennung verstehen, aber neue native Dateien müssen eindeutig CASU sein.

---

## A7. Source-Provenance ist gut, aber Portabilität fehlt

Der aktuelle Sidecar speichert einen absoluten Quellpfad.

Benötigt:

- relative Quelle bevorzugen, falls Quelle neben Manifest liegt;
- optional absolute Provenance nur als Hinweis;
- source UUID/hash;
- robustes Relocation-Verhalten;
- klare Suchreihenfolge;
- keine überraschende Bindung an einen alten absoluten Pfad.

---

## A8. Audioanalyse lädt derzeit komplette PCM-Ausgabe in den RAM

Für lange Audio-/Videodateien ist das nicht skalierbar.

Audioanalyse als Streaming-Pipeline bauen:

```text
ffmpeg/libav decode
→ chunk
→ window analysis
→ state accumulation
→ chunk freigeben
```

Nicht:

```text
entire decoded PCM
→ RAM
→ analyze
```

Unterstütze mehrstündige Dateien ohne RAM-Explosion.

---

## A9. FFmpeg-Prozesse brauchen robuste Prozesskontrolle

Die Analyse benutzt externe `ffmpeg`/`ffprobe`-Werkzeuge. Das ist für den Converter okay, aber die Prozessschicht muss professionell werden:

- Timeout;
- Cancel;
- Progress;
- stderr-drain;
- Exit-Code;
- Signal/Terminate/Kill;
- saubere Temp-Dateien;
- keine Shell-Interpolation;
- klare Fehlerobjekte.

Neue Abstraktion:

```text
casu/legacy/ffmpeg_process.py
```

---

# TEIL B — MPCASU PLAYER: AKTUELLER CODE MUSS ARCHITEKTONISCH UMGESTELLT WERDEN

## B1. `mpcasu_player.py` ist derzeit eine große monolithische UI-Klasse

Die aktuelle Player-UI liegt weitgehend in einer einzigen sehr großen Tk-Klasse.

Das ist nicht die Zielarchitektur.

Aufteilen:

```text
mpcasu/
    app.py
    playback/
        controller.py
        state.py
        events.py
        tracks.py
        backend.py
        libvlc_backend.py
        casu_backend.py
    ui/
        main_window.py
        video_view.py
        audio_view.py
        empty_view.py
        error_view.py
        sidebar.py
        playlist.py
        transport.py
        timeline.py
        diagnostics.py
        settings.py
        media_info.py
        fullscreen_overlay.py
        mini_player.py
    library/
        database.py
        scanner.py
        metadata.py
        thumbnails.py
    settings/
        store.py
    platform/
        linux.py
        windows.py
        macos.py
```

---

## B2. Für eine hochwertige responsive UI Tkinter nicht weiter aufblasen

Der aktuelle Tkinter-Prototyp kann als Funktionsreferenz erhalten bleiben.

Für den produktionsreifen Player ist eine Migration auf **PySide6 / Qt** stark zu bevorzugen.

Warum:

- echte responsive Layouts;
- Splitter;
- Model/View für große Playlists;
- HiDPI;
- native Menüs;
- bessere Icons;
- Drag & Drop;
- Fullscreen-Overlay;
- QSettings;
- Multithreading/Signals;
- bessere Accessibility;
- professionelleres Styling.

Bevorzugt:

```text
PySide6 + Qt Widgets
```

oder QML, falls sauber beherrscht.

Kein Web-Dashboard als Ersatz für einen Desktop-Media-Player.

---

## B3. Das offizielle MPCASU-Logo muss korrekt und uncropped benutzt werden

Aktueller Fehler: Header-Logo kann durch feste Containermaße abgeschnitten werden.

Regeln:

```text
preserve aspect ratio
contain, never crop
no stretch
HiDPI source
transparent alpha preserved
minimum padding
```

Verwende das gelieferte Logo.

Nicht neu zeichnen.

Das gelieferte MPCASU-Player-Icon verwenden für:

- Fenstericon;
- Taskbar;
- Desktop;
- Installer;
- About;
- Startmenü.

---

## B4. Das offizielle CASU-Converter-Icon fehlt im aktuellen Asset-Set

Das neu gelieferte Converter-Icon als eigenes Asset aufnehmen:

```text
assets/casu_converter_icon.png
```

Nicht das CASU-Logo als einziges App-Icon missbrauchen.

Converter:

```text
CASU Logo = Branding
CASU Converter Icon = Application Icon
```

---

## B5. Aktuell sind viele Sidebar-Einträge nur Platzhalter

Navigationseinträge dürfen nur sichtbar sein, wenn die Seite real existiert.

Entweder vollständig implementieren oder bis dahin ausblenden:

```text
Library
CASU Files
Movies
TV Shows
Music
Playlists
Local Disk
Media Drive
Network Share
CASU Hub
Web Videos
Podcasts
Favorites
Recently Added
4K Collection
Workout Mix
```

Kein Klick darf nur:

```text
"view not available in this release"
```

melden, wenn die Funktion als normaler Hauptmenüpunkt dargestellt wird.

---

## B6. libVLC-Backend ist aktuell Linux-/X11-spezifisch und zu fragil

Aktuell sind harte Annahmen enthalten:

```text
libvlc.so.5
/usr/lib/x86_64-linux-gnu/vlc/plugins
set_xwindow
```

Das ist nicht cross-platform.

Implementiere saubere Runtime-Discovery:

Linux:

```text
set_xwindow
```

Windows:

```text
set_hwnd
```

macOS:

```text
set_nsobject
```

Keine hardcodierte x86_64-Debian-Pfadannahme im Core.

VLC Plugin Path dynamisch entdecken oder Distribution kontrolliert bundeln.

---

## B7. Nicht weiter manuell nur einen kleinen Teil der libVLC-API per ctypes nachbauen

Bevorzugt entweder:

1. offizielle/stabile Python-libVLC-Bindings sauber kapseln, oder
2. eine vollständige eigene FFI-Schicht mit klarer Versionsprüfung.

In beiden Fällen:

```text
LibVLCBackend
```

bleibt hinter einem eigenen Interface.

UI kennt libVLC nicht direkt.

---

## B8. LibVLC-Event-System verwenden, nicht nur Polling

Benötigt Events für:

```text
Opening
Playing
Paused
Stopped
Buffering
TimeChanged
LengthChanged
EndReached
EncounteredError
MediaChanged
```

500-ms-Polling darf höchstens ergänzend für Telemetrie dienen.

Playback-State muss event-driven sein.

---

## B9. PlaybackController ist derzeit zu dünn

Benötigt vollständige Zustandsmaschine:

```text
EMPTY
LOADING
OPENING
READY
PLAYING
PAUSED
BUFFERING
SEEKING
STOPPED
ENDED
ERROR
```

Dazu:

- concurrency-safe transitions;
- event queue;
- cancellation;
- source replacement;
- end-of-file;
- seek transaction;
- backend fallback;
- error classification.

---

## B10. Echte A/V-Sync- und Clock-Strategie definieren

Wenn libVLC die interne Synchronisation übernimmt, das klar als Backend-Verantwortung dokumentieren und echte Backend-Metriken verwenden.

Wenn CASU später einen eigenen Decoder/Renderer besitzt:

- Audio Clock als Master, wo sinnvoll;
- Video PTS dagegen synchronisieren;
- VFR;
- B-Frames;
- device latency;
- dropped/late frames;
- seek/pause/resume.

Keine eigenen `sleep(1/fps)`-Loops.

---

## B11. Video muss auf allen Plattformen real im MPCASU-Viewport erscheinen

Acceptance Gate:

```text
MP4 H.264/AAC
→ MPCASU window
→ real video
→ real audio
```

Nicht:

- Waveform statt Video;
- externes Fenster;
- ffplay;
- VLC.exe.

---

## B12. Audio-Ausgabe und Device Selection ausbauen

Implementieren:

- volume;
- mute;
- audio track list mit Namen/Sprache;
- audio output device;
- audio delay;
- channel layout;
- passthrough, falls unterstützt;
- device hotplug/fallback.

UI muss reale Geräte anzeigen.

---

## B13. Tracks nicht nur per numerischem „cycle“ bedienen

Echte Track-Modelle:

```text
TrackDescriptor:
    id
    type
    codec
    language
    description
    channels
    default
    forced
```

UI-Menüs:

```text
Audio
Subtitles
Video
```

mit Namen statt „Track 2/3“.

---

## B14. Externe Untertitel fehlen

Implementieren:

- SRT;
- ASS/SSA;
- WebVTT;
- Backend-supported embedded subtitles;
- Drag & Drop `.srt`;
- delay;
- styling;
- enable/disable.

---

## B15. Chapters fehlen

Implementieren:

- chapter discovery;
- chapter menu;
- next/previous chapter;
- markers in timeline.

---

## B16. Playlist ist noch kein vollwertiges Modell

Erstellen:

```text
PlaylistModel
PlaylistItem
QueueController
```

Funktionen:

- add;
- remove;
- reorder;
- multi-select;
- drag/drop;
- save/load;
- shuffle;
- repeat;
- repeat-one;
- play-next;
- search;
- thumbnails;
- metadata;
- persistence.

Qt Model/View verwenden, falls Migration erfolgt.

---

## B17. Media Library fehlt

SQLite-basierte Library:

```text
media
folders
play_history
resume_positions
favorites
playlists
artwork_cache
```

Scanner:

- inkrementell;
- keine Komplettanalyse bei jedem Start;
- Background Worker;
- cancelable;
- cache thumbnails/metadata.

---

## B18. Resume/History/Bookmarks fehlen

Speichern:

- letzte Position;
- zuletzt geöffnet;
- Audio Track;
- Subtitle Track;
- Playback Rate;
- Window State.

Optional Bookmarks/A-B repeat.

---

## B19. Settings fehlen

Eigener Settings Store.

Bereiche:

```text
General
Playback
Video
Audio
Subtitles
Library
CASU
Hardware
Network
Interface
Hotkeys
Diagnostics
```

Nur funktionierende Optionen anzeigen.

---

## B20. Fullscreen ist aktuell nur Fenster-Flag

Produktionsreif:

- echtes Video Fullscreen;
- Controls Overlay;
- Auto Hide;
- Cursor Hide;
- ESC;
- Doppelklick;
- Multi-Monitor-Verhalten.

---

## B21. Mini Player / Audio Mode fehlen

Audio-Only:

- Cover;
- Title;
- Artist;
- Album;
- Timeline;
- real waveform optional.

Mini Player separat entwerfen, nicht nur Hauptfenster verkleinern.

---

# TEIL C — „ALLE FORMATE WIE VLC“ RICHTIG UMSETZEN

## C1. Zielvertrag

Für Legacy-Medien gilt:

> Wenn der mit MPCASU ausgelieferte bzw. verwendete libVLC-Build eine Quelle erfolgreich öffnen und dekodieren kann, darf MPCASU sie nicht durch eine eigene kleine Extension-Whitelist künstlich blockieren.

Das native `.casu`-Format läuft separat über `CasuBackend`.

---

## C2. Keine Extension-Whitelist als Hauptlogik

Aktuell existiert eine kleine `MEDIA`-Menge.

Diese darf nicht die Backend-Kompatibilität definieren.

Open Dialog:

```text
Supported Media
All Files
```

Formatentscheidung durch Probe/Backend.

---

## C3. Netzwerkquellen erweitern

Nicht statisch nur einige Schemes erlauben, wenn libVLC mehr kann.

Capability- und Sicherheitslayer entwickeln.

Unter anderem testen:

- HTTP/HTTPS;
- HLS;
- RTSP;
- RTP;
- UDP;
- SMB;
- UPnP, falls Build unterstützt.

---

## C4. Backend-Fallback kontrolliert

Pipeline:

```text
CASU source
→ CASU backend

Legacy source
→ libVLC backend
→ optional secondary library backend only when explicitly designed
```

Kein unkontrolliertes Backend-Flapping während Playback.

---

# TEIL D — CASU CONVERTER KOMPLETT AUSBAUEN

## D1. Aktuell ist der Converter nur Single-File + JSON-Manifest

Der aktuelle Converter bietet im Wesentlichen:

- Source;
- Output;
- Mode;
- FPS;
- indeterminate progress;
- Convert.

Das reicht nicht.

---

## D2. Eigenständige modulare Converter-Engine

Neue Struktur:

```text
casu/converter/
    job.py
    queue.py
    pipeline.py
    progress.py
    profiles.py
    report.py
    cancellation.py
    benchmark.py
```

GUI benutzt diese Engine.

CLI benutzt dieselbe Engine.

Keine doppelte Conversion-Logik.

---

## D3. Batch Queue

Implementieren:

- Add Files;
- Add Folder;
- recursive scan;
- multiple selection;
- reorder queue;
- start;
- pause queue;
- cancel job;
- retry failed;
- remove;
- clear;
- persisted queue optional.

---

## D4. Reale Progress-Anzeige

Nicht `indeterminate` als endgültige Lösung.

Phasen:

```text
PROBE
HASH
VIDEO ANALYSIS
AUDIO ANALYSIS
STATE BUILD
WRITE
VERIFY
FINALIZE
```

Fortschritt aus echten Frames/Samples/Bytes.

ETA nur bei brauchbarer Schätzung.

---

## D5. Cancel

Jeder lange Job muss abbrechbar sein.

- Worker Event;
- ffmpeg terminate;
- temp cleanup;
- keine halbgültige `.casu`.

---

## D6. Converter-Logo und Icon

Verwende:

- offizielles CASU-Logo im Header;
- offizielles neues CASU-Converter-Icon als Fenster-/Desktop-/Installer-Icon.

Das aktuell erzeugte Header-Branding darf nicht abgeschnitten werden.

---

## D7. Converter UI responsiv

Keine fixe 720×430-Logik als Endzustand.

Testen:

```text
1024x600
1280x720
1920x1080
125/150/200 % DPI
```

---

## D8. Analyze / Convert / Verify / Repair / Benchmark getrennte Funktionen

Tabs oder Views:

```text
Convert
Analyze
Verify
Benchmark
Reports
Settings
```

`Repair` erst anbieten, wenn technisch real.

Nichts erfinden.

---

## D9. Presets real implementieren

Nicht nur Namen speichern.

```text
STRICT
VISUALLY LOSSLESS
ADAPTIVE
ARCHIVE
STREAMING
LOW POWER
```

Jedes Preset muss konkrete Parameter setzen.

---

## D10. Reports

Nach Job:

- input;
- output;
- duration;
- segment count;
- tile count;
- hold ratio;
- changed area;
- source hash;
- integrity;
- processing time;
- CPU/GPU stats, falls real;
- warnings.

Export:

```text
JSON
CSV
Markdown
```

---

# TEIL E — PACKAGING-BUGS, DIE KONKRET REPARIERT WERDEN MÜSSEN

## E1. `pyproject.toml` paketiert derzeit nicht alle Player-Module

Die `py-modules`-Liste enthält aktuell nicht sämtliche importierten MPCASU-Module.

Alle Runtime-Module müssen in Wheel/sdist enthalten sein.

Besser:

MPCASU in ein echtes Package verschieben:

```text
mpcasu/
```

statt mehrere lose Top-Level-Module.

Dann Setuptools-Packages korrekt konfigurieren.

Baue und teste:

```text
python -m build
pip install dist/*.whl
mpcasu
casu-converter
```

in einer frischen virtuellen Umgebung.

Editable Install zählt nicht als Packaging-Test.

---

## E2. Converter-Paket enthält aktuell nicht alle Branding-Assets, die die GUI erwartet

Der installierte Converter muss seine Header-/Logo-/Icon-Dateien tatsächlich besitzen.

Assets nicht nur in `/usr/share/icons` installieren, wenn die Python-GUI relativ unter `assets/...` danach sucht.

Saubere Resource-Verwaltung bauen:

```text
importlib.resources
```

oder Qt Resources.

---

## E3. Player-Paket muss Image/Logo-Abhängigkeiten sauber deklarieren

Wenn Pillow für die echte Logo-/Icon-Verarbeitung nötig ist:

- als Dependency deklarieren

oder UI-Framework-native Ressourcen verwenden.

Keine Funktion soll nur in der Entwicklerumgebung funktionieren.

---

## E4. CI testet aktuell den echten libVLC-Playbackpfad nicht

CI muss libVLC/VLC installieren.

Zusätzlich:

- GUI Smoke über Xvfb auf Linux;
- Backend init;
- open;
- play;
- audio/video stream discovery;
- seek;
- stop;
- no external process.

---

# TEIL F — TESTS KOMPLETT NEU STRUKTURIEREN

## F1. Fast Unit Tests und Slow Media Tests trennen

Die aktuelle Suite analysiert große Medien mehrfach und kann dadurch sehr langsam werden.

Markers:

```text
unit
media
slow
gui
network
```

CI:

```text
fast tests on every commit
media integration tests once per job
full long-run separately
```

Kleine synthetische Fixtures generieren.

---

## F2. Player-Acceptance Tests

P0:

```text
MP4 H264 AAC
MP3
FLAC
MKV H265
WebM VP9/Opus
AV1/Opus
```

Jeweils prüfen:

- open;
- duration;
- play;
- pause;
- seek;
- actual backend state;
- tracks;
- EOF;
- stop.

---

## F3. Video+Audio muss real getestet werden

Nicht nur prüfen, dass kein `ffplay`-String im Code steht.

Benötigt echte Integration:

```text
libVLC opens fixture
video stream exists
audio stream exists
play starts
time advances
seek changes time
end/stop works
```

Für Audio-Ausgabe in CI ggf. Dummy/PulseAudio/PipeWire Sink.

---

## F4. CASU Tests

Mindestens:

- exact tile identity;
- changed tile detection;
- lifecycle;
- seek index;
- corrupt header;
- corrupt segment;
- unknown version;
- checksum failure;
- recovery;
- huge declared sizes;
- circular references;
- truncated file;
- source relocation;
- deterministic write.

---

## F5. Fuzzing

Native Reader fuzz-testen.

Parser darf bei manipulierter Eingabe nicht:

- crashen;
- unbounded memory reservieren;
- endlose Loops erzeugen.

---

# TEIL G — PERFORMANCE UND ENERGY SAVING REAL MACHEN

## G1. CASU-Einsparung nicht aus Dateigröße ableiten

Getrennte Metriken:

```text
storage reduction
decode workload
render workload
memory traffic
changed area
state reuse
measured energy
estimated energy
```

Keine Vermischung.

---

## G2. Legacy Display Data Firewall implementieren

Für decodierte Legacy-Frames:

```text
decoded frame
→ canonical tile representation
→ hash/change map
→ state cache
→ dirty regions
→ renderer
```

Zunächst STRICT.

Messen:

```text
tiles_total
tiles_changed
tiles_held
pixels_redrawn
frame time
```

---

## G3. Native CASU Renderer

Langfristig:

```text
CASU state stream
→ scheduler
→ state cache
→ dirty region renderer
```

Erst dann ist CASU im Player mehr als Sidecar-Diagnostik.

---

# TEIL H — RESPONSIVE DESIGN GATES

Das gelieferte rote Mockup ist normative visuelle Referenz.

Das aktuelle reale Fenster ist nur Istzustand, keine Referenz.

Testgrößen:

```text
980×620 minimum
1024×600
1280×720
1366×768
1600×900
1920×1080
2560×1440
```

DPI:

```text
100
125
150
175
200 %
```

Regeln:

- Logo nie crop;
- Sidebar scrollt oder kollabiert;
- Playlist Drawer bei wenig Breite;
- Diagnostics Grid/Collapse;
- Transport Controls umbrechen oder in kompakte Iconleiste wechseln;
- Video View bekommt Priorität;
- keine Widgets außerhalb des Fensters;
- keine überlappenden Texte.

---

# TEIL I — KONKRETE NEUE ARCHITEKTUR

Empfohlene Zielstruktur:

```text
casu/
    __init__.py

    format/
        constants.py
        records.py
        reader.py
        writer.py
        index.py
        integrity.py
        recovery.py

    analysis/
        video.py
        audio.py
        tiles.py
        perceptual.py

    runtime/
        state_graph.py
        scheduler.py
        cache.py

    converter/
        pipeline.py
        job.py
        queue.py
        profiles.py
        progress.py
        report.py

    legacy/
        ffmpeg.py
        probe.py

mpcasu/
    app.py

    playback/
        controller.py
        state.py
        events.py
        tracks.py
        base_backend.py
        libvlc_backend.py
        casu_backend.py

    ui/
        main_window.py
        theme.py
        video_view.py
        audio_view.py
        empty_view.py
        error_view.py
        sidebar.py
        playlist.py
        transport.py
        timeline.py
        diagnostics.py
        settings.py
        media_info.py
        fullscreen_overlay.py
        mini_player.py

    library/
        database.py
        scanner.py
        metadata.py

    platform/
        linux.py
        windows.py
        macos.py

tests/
    unit/
    media/
    gui/
    format/
    fuzz/
```

---

# TEIL J — IMPLEMENTIERUNGSREIHENFOLGE

## P0 — Build/Packaging wahr machen

1. Repo inventarisieren.
2. Version/Status korrigieren.
3. Package-Struktur reparieren.
4. Assets vollständig aufnehmen.
5. offizielles CASU-/MPCASU-Branding verbindlich integrieren.
6. Wheel + Debian Install in Clean Environment testen.

## P1 — Legacy Player muss wirklich funktionieren

1. libVLC Backend cross-platform abstrahieren.
2. Events.
3. Video.
4. Audio.
5. Seek.
6. Volume/Mute.
7. Track Enumeration.
8. Subtitles.
9. Fullscreen.
10. URL/Network.
11. Tests.

**Kein weiterer Visualizer vor Abschluss dieses Gates.**

## P2 — UI Produktionsreif

1. PySide6/Qt Migration.
2. responsive Layout.
3. Playlist Model.
4. Settings.
5. Audio View.
6. Mini Player.
7. Library.
8. offizielle Logos/Icons überall.

## P3 — Converter

1. Shared Engine.
2. Queue.
3. Progress.
4. Cancel.
5. Profiles.
6. Analyze/Verify/Benchmark.
7. Reports.
8. Converter Icon/Branding.
9. tests.

## P4 — Echte räumlich-zeitliche CASU-State-Engine

1. strict tile identity.
2. per-tile map.
3. segment lifecycle.
4. seek index.
5. cache.
6. native scheduler.
7. player integration.
8. benchmark.

## P5 — Nativer CASU Container

1. binary/native reader/writer.
2. key states.
3. index.
4. checksums.
5. recovery.
6. streams.
7. subtitles.
8. metadata.
9. attachments.
10. deterministic tests.

---

# TEIL K — HARTE ACCEPTANCE GATES

## K1. Player

Öffne eine normale MP4 H.264/AAC:

```text
PASS only if:
- real video visible
- real sound audible
- pause/resume
- stop
- seek
- volume
- mute
- fullscreen
- duration correct
- timeline correct
- A/V sync acceptable
- no ffplay
- no vlc.exe
- no external player window
```

## K2. Audio

MP3/FLAC:

```text
PASS only if:
- sound
- seek
- metadata
- cover art where present
- real waveform only if enabled
```

## K3. VLC compatibility

Für Testkorpus:

```text
If bundled libVLC = PASS
and MPCASU = FAIL
→ MPCASU compatibility bug
```

## K4. CASU

`.casu`:

```text
PASS only if:
- native CASU path is identifiable
- integrity works
- state scheduler works
- video/audio output works
- seek works
- diagnostics are real
```

## K5. Converter

```text
PASS only if:
- queue works
- progress real
- cancel works
- temp cleanup works
- output validates
- report generated
- official CASU logo used
- official converter icon used
```

---

# TEIL L — VERBOTENE ABKÜRZUNGEN

Nicht akzeptabel:

```text
ffplay subprocess
vlc.exe subprocess
external player embedding
fake waveform
fake FFT
fake CPU %
fake energy %
fake integrity "verified"
hardcoded demo metadata
buttons without backend
navigation to placeholder pages
analysis modes that only change a label
"strict pixel identical" based only on scaled grayscale threshold
full-file PCM loading for arbitrarily long input
Linux-only X11 code presented as cross-platform
hardcoded /usr/lib/x86_64-linux-gnu/vlc/plugins as universal solution
```

---

# TEIL M — ABSCHLUSSBERICHT VON CODEX

Nach Umsetzung einen Bericht erzeugen:

```text
IMPLEMENTATION_REPORT.md
```

mit:

1. geänderten Dateien;
2. neuen Modulen;
3. entfernten Prototypwegen;
4. Playback-Matrix;
5. Format-Matrix;
6. CASU-Status;
7. Converter-Status;
8. UI-Status;
9. Packaging-Status;
10. Tests;
11. Benchmarks;
12. bekannte offene Punkte.

Zusätzlich:

```text
git diff --check
python -m compileall
pytest fast
pytest media
clean wheel install
clean Debian install
```

Keine Behauptung „fertig“, solange ein P0-Gate rot ist.

---

# KURZER MASTER-PROMPT FÜR CODEX

Auditiere zuerst den gesamten vorhandenen CASU/MPCASU-Code und behandle ihn als Prototyp, nicht als fertiges Produkt. Implementiere anschließend nach diesem Dokument einen echten, modularen CASU-Codec/State-Layer, einen professionellen CASU-Converter und einen vollständigen MPCASU-Media-Player. Priorität haben reale Video-/Audio-Wiedergabe, vollständige libVLC-Kompatibilität für Legacy-Medien, native CASU-Integration, responsive professionelle UI, echte Track-/Subtitle-/Playlist-/Library-Funktionen, robuste Packaging- und Testpfade sowie echte räumlich-zeitliche Segmentzustände. Entferne keine Quelltreue zugunsten kosmetischer Tricks. Kein ffplay, kein VLC.exe, keine Fremdplayer-UI, keine Fake-Werte, keine Fake-Visualisierungen und keine Buttons ohne Backend. Verwende zwingend die vom Auftraggeber bereitgestellten offiziellen CASU- und MPCASU-Logos, das MPCASU-Player-Icon, das CASU-Converter-Icon und das rote UI-Mockup; erfinde keine Ersatzgrafiken. Implementiere in klaren Phasen, führe nach jeder Phase Builds, Tests und Regressionen aus und markiere eine Funktion nur dann als COMPLETE, wenn Backend, UI, Fehlerbehandlung, Persistenz soweit nötig, automatisierte Tests und manuelle Validierung wirklich vorhanden sind.
