# CODEX BRIEF 01 — Idee: Segmented State Display / Codec

## Ziel

Baue eine Software-Architektur, die klassische framebasierte Medien- und Displaydaten weiterhin vollständig versteht, intern aber nicht mehr jeden vollständigen Frame als gleichwertige Grundeinheit behandelt.

Die zentrale Idee lautet:

> **Nicht der Frame ist die fundamentale Einheit, sondern die relevante Zustandsänderung eines räumlich-zeitlichen Segments.**

Ein statischer Bildbereich soll seinen Zustand behalten können, ohne ständig neu gerendert, kopiert, übertragen oder – bei geeigneter Hardware – physikalisch neu geschrieben zu werden. Bewegte oder interaktive Bereiche erhalten dagegen genau die zeitliche Auflösung, die sie benötigen.

Das System soll zunächst als reine Software auf vorhandener Hardware funktionieren und später von Panels mit lokalem Speicher, Partial Refresh, LTPO, Memory-in-Pixel, reflektiven oder bistabilen Technologien stärker profitieren können.

---

## Problem heutiger Systeme

Klassische Grafikpipelines arbeiten weitgehend frameorientiert:

1. Anwendung erzeugt oder verändert Inhalte.
2. Compositor/GPU erzeugt ein vollständiges Bild.
3. Ein vollständiger Frame wird übertragen.
4. Das Display arbeitet mit einer globalen Refresh-Logik.

Damit wird häufig auch dort Arbeit wiederholt, wo sich visuell nichts geändert hat.

Beispiel:

- 95 % einer Webseite sind statisch.
- Nur der Mauszeiger oder ein kleines Video verändert sich.
- Trotzdem wird ein vollständiger Framezyklus behandelt.

Die Architektur soll daher redundante Arbeit erkennen und vermeiden.

---

## Kernmodell

Teile die Ausgabefläche in Segmente oder Tiles:

\[
S_i = (x, y, w, h)
\]

Jedes Segment besitzt einen zeitabhängigen Zustand:

\[
S_i(t)
\]

und eine Update-Klasse, zum Beispiel:

- `HOLD` — Zustand unverändert halten.
- `LOW_RATE` — seltene Änderungen.
- `MOTION` — normale Bewegung.
- `REALTIME` — Interaktion, Maus, Spiel, kritische Animation.
- `LOSSLESS_REALTIME` — keine Optimierung zulässig, nur unveränderte Weitergabe.

Die lokale benötigte Aktualisierungsrate wird damit zu:

\[
f = f(x,y,t)
\]

anstatt einer einzigen globalen Aussage wie „das Display läuft mit 120 Hz“.

---

## Segmented State Codec

Ein möglicher Datenstrom soll nicht nur vollständige Frames enthalten, sondern Zustände und Änderungen.

Prinzip:

\[
S_0 + \Delta S_1 + \Delta S_2 + \ldots
\]

Mögliche Informationen pro Segment:

- Position und Größe
- Zeitstempel
- Gültigkeitsdauer
- Änderung gegenüber vorherigem Zustand
- Motion-Klasse
- Priorität
- maximale zulässige Latenz
- benötigte zeitliche Auflösung
- Qualitätsklasse
- optional Farb-/Luminanzänderungen
- optional Herkunft der Information, z. B. Video, Text, UI, Cursor

---

## Display Data Firewall

Für alte Systeme wird eine Kompatibilitätsschicht benötigt.

Pipeline:

```text
Legacy Input
    ↓
Decoder / Compositor
    ↓
Display Data Firewall
    ↓
Change Detection
    ↓
Spatial + Temporal Segmentation
    ↓
Scheduler
    ↓
bestehender Displaypfad oder natives segmentiertes Panel
```

Die Firewall darf alte Formate annehmen, darunter insbesondere:

- MP4
- MP3
- klassische Desktop-Frames
- Browserausgabe
- alte Spiele und Programme

Sie analysiert den Datenstrom und erzeugt intern eine segmentierte Zustandsdarstellung.

---

## Wichtigstes Prinzip: Informationsintegrität

Die Optimierung darf Redundanz entfernen.

Sie darf **keine neue Information erfinden**.

Insbesondere standardmäßig verboten:

- künstliche Zwischenbilder
- Motion Interpolation
- künstliche Beschleunigung
- künstliche Verzögerung
- zeitliche Umordnung
- Audio-Time-Stretching
- Pitch-Veränderung
- Verlust von kurzen, aber echten Bildänderungen
- unaufgefordertes Glätten von Bewegung
- versteckte Veränderung von Farbe, Helligkeit oder Kontrast
- Veränderung des A/V-Synchronismus

Kurz:

> **Keine Designer-Drogen für das Signal.**

Die Display-Zeitstruktur soll die Zeitstruktur der Information respektieren.

---

## Zwei Optimierungsziele

### 1. Leistung und Energie

Reduziere soweit möglich:

- CPU-Arbeit
- GPU-Arbeit
- Compositing
- Speicherbandbreite
- VRAM-Transfers
- Display-Link-Transfers
- Panel-Updates
- unnötige Lichtmodulation

### 2. Neurovisuelle Neutralität

Optional kann ein separater Comfort-/Safety-Layer unnötige technische Modulation erkennen oder vermeiden, zum Beispiel:

- vermeidbares PWM/Flicker
- unnötige Helligkeitssprünge
- technisch verursachtes temporales Dithering
- überflüssige UI-Animation

Dieser Layer darf Inhalte nur verändern, wenn ein expliziter Benutzer-Modus dies erlaubt. Standardmodus bleibt originalgetreu.

---

## Grundsatz für Codex

Implementiere zuerst eine **messbare, konservative Software-Version**.

Nicht versuchen, sofort eine neue Displayhardware zu simulieren.

Erste Frage:

> Wie viel redundante Grafikarbeit kann auf einem normalen Rechner vermieden werden, ohne dass das ausgegebene Bild oder der Ton vom Original abweicht?

Danach kann die Architektur schrittweise auf native segmentierte Displays erweitert werden.
