# CODEX BRIEF 03 — Harte Bedingungen für alte MP4-Dateien

## Aufgabe

Alte, normale MP4-Dateien sollen **ohne Konvertierungszwang** mit der neuen segmentierten Architektur dargestellt werden können.

Die vorhandene MP4-Datei bleibt die kanonische Quelle.

Die Verbesserung erfolgt durch eine zusätzliche Analyse-, Cache-, Scheduler- und Rendering-Schicht.

---

# 1. Backward Compatibility ist Pflicht

Eine vorhandene Datei:

```text
video.mp4
```

muss weiterhin:

- mit normalen Playern funktionieren
- unverändert kopierbar sein
- unverändert archiviert werden können
- ihren ursprünglichen Codec behalten dürfen
- keine proprietäre Neucodierung benötigen

Optional darf erzeugt werden:

```text
video.mp4
video.ssc
```

oder:

```text
video.mp4
video.ssc.json
```

Die Sidecar-Datei enthält nur Optimierungsinformationen.

Fehlt sie, muss das Video trotzdem normal funktionieren.

---

# 2. Die MP4-Zeitachse ist die Quelle der Wahrheit

Es dürfen keine eigenen Zeiten erfunden werden.

Zu respektieren sind insbesondere:

- PTS
- DTS
- Time Base
- Edit Lists
- Variable Frame Rate
- Audio-Timestamps
- Untertitel-Timestamps

Ein Frame, der laut Quelle zu Zeitpunkt \(t\) sichtbar sein soll, darf nicht willkürlich früher oder später erscheinen.

---

# 3. Keine künstliche Bewegungsmanipulation

Standardmäßig verboten:

- Frame Interpolation
- Optical-Flow-Zwischenbilder
- künstliche 24→60-fps-Bewegung
- künstliches Motion Smoothing
- Zeitraffer
- Zeitlupe
- Frame-Reordering außerhalb der Codec-/Containerlogik
- Zusammenziehen unterschiedlicher Frames nur weil sie „ähnlich“ wirken

Zulässig ist:

> Einen bereits bestehenden Zustand länger zu halten, **wenn das Original in diesem Zeitraum tatsächlich keine darstellungsrelevante Änderung verlangt**.

---

# 4. Keine versteckte Bildveränderung

Standardmodus muss visuell originalgetreu sein.

Nicht ohne explizite Option verändern:

- Farbraum
- Transferfunktion
- Gamma
- HDR-Metadaten
- Peak Brightness
- Chroma
- Schärfe
- Kontrast
- Grain
- Dithering
- Untertitel
- Overlays

Folgende Metadaten müssen soweit möglich erhalten und korrekt interpretiert werden:

- BT.601 / BT.709 / BT.2020
- SDR / HDR10 / HLG / Dolby-Vision-relevante Metadaten soweit die Decoderpipeline sie unterstützt
- Full / Limited Range
- Pixel Aspect Ratio
- Rotation / Display Matrix
- Color Primaries
- Matrix Coefficients
- Transfer Characteristics

---

# 5. Audio darf nicht aus dem Takt geraten

MP3-, AAC- oder andere Audiostreams innerhalb bzw. neben einem MP4 müssen synchron bleiben.

Mindestbedingung:

\[
|A/V\ Sync\ Error| \leq \text{konfigurierbarer Grenzwert}
\]

Der Prototyp soll den gemessenen A/V-Sync-Fehler protokollieren.

Standardmäßig verboten:

- Audio beschleunigen
- Audio verlangsamen
- Pitch verändern
- Stille entfernen und dadurch Zeit verschieben
- Audiosegmente wegen „geringer Bedeutung“ überspringen

---

# 6. Seek muss korrekt funktionieren

Bei Sprung zu einem Zeitpunkt \(t\):

1. Decoder korrekt zum geeigneten Keyframe zurücksetzen.
2. notwendige Referenzframes dekodieren.
3. Segmentcache invalidieren, wenn sein Zustand nicht sicher gültig ist.
4. Zielbild rekonstruieren.
5. erst danach HOLD-/Delta-Optimierung wieder aktivieren.

Niemals veraltete Tiles nach einem Seek weiterverwenden.

---

# 7. Scene Changes erzwingen konservatives Verhalten

Bei einem harten Szenenwechsel:

```text
invalidate current spatial state
```

und einen neuen vollständigen Zustand etablieren.

Ein Scene Change darf nicht durch alte HOLD-Tiles „durchscheinen“.

---

# 8. Fehlerfall = sicherer Fallback

Bei Unsicherheit:

```text
FALLBACK_TO_FULL_FRAME
```

Das System soll lieber kurzfristig mehr Energie verbrauchen als falsche Bildinformation auszugeben.

Beispiele für Fallback:

- beschädigte Sidecar-Daten
- fehlende Referenz
- Timestamp-Konflikt
- unbekanntes Pixel Format
- Decoderfehler
- nicht unterstützte HDR-Metadaten
- Cache-Inkonsistenz
- unklare Änderungsklassifikation

---

# 9. Vergleichsmodus ist Pflicht

Jede optimierte Wiedergabe soll gegen einen Referenzpfad vergleichbar sein:

```text
Reference:
MP4 → Standard Decode → Full Frame Render

Optimized:
MP4 → Standard Decode → Segment Analyzer → State Cache → Partial Render
```

Messwerte:

- Frame-Timestamps
- Pixel-Differenzen
- A/V-Sync
- Dropped Frames
- Rendered Pixel Count
- Tile Updates
- CPU/GPU-Zeit
- Speichertransfers
- Energie soweit verfügbar

---

# 10. Drei Qualitätsmodi

## STRICT_LOSSLESS

Ein Segment darf nur gehalten werden, wenn der nächste dargestellte Zustand pixelidentisch ist oder die Pipeline exakt denselben finalen Pixelzustand erzeugt.

Keine wahrnehmungsbasierte Entscheidung.

## VISUALLY_LOSSLESS

Nur optional.

Sehr kleine Unterschiede dürfen nach einer transparent definierten Metrik zusammengefasst werden.

Muss abschaltbar sein.

## ADAPTIVE

Experimenteller Modus.

Darf stärker optimieren, aber nur nach ausdrücklicher Benutzerwahl.

Nie Default.

---

# 11. Priorität

Reihenfolge der Ziele:

1. korrekter Inhalt
2. korrektes Timing
3. korrekter A/V-Sync
4. Stabilität
5. niedrige Latenz
6. Energie-/Leistungseinsparung

Energieeinsparung darf niemals Ziel 1–4 brechen.

---

# 12. Was „verbessert darstellen“ bedeutet

„Verbessert“ bedeutet in diesem Projekt nicht:

- schöner erfinden
- flüssiger erfinden
- Frames hinzufügen
- Inhalte glätten
- Bewegung umdeuten

Sondern:

> **Dasselbe MP4 mit möglichst wenig unnötiger Rechen-, Transfer- und Displayarbeit korrekt darstellen.**

Das zentrale Optimierungsziel lautet:

\[
\min(\text{unnötige Arbeit})
\]

unter den Nebenbedingungen:

\[
\text{Bildtreue} = \text{Original}
\]

\[
\text{Zeitstruktur} = \text{Original}
\]

\[
\text{A/V-Sync} = \text{Original}
\]

soweit technisch exakt bzw. innerhalb dokumentierter Systemtoleranzen.

---

# 13. Legacy-Filter / Display Data Firewall

Der Legacy-Filter ist die Brücke zwischen alten Medien und der neuen Architektur.

Er soll:

1. MP4 normal dekodieren.
2. originale Zeitinformation übernehmen.
3. tatsächliche Bildänderungen erkennen.
4. lokale Segmentzustände erzeugen.
5. unveränderte Zustände cachen.
6. nur notwendige Bereiche erneut rendern.
7. bei Unsicherheit auf Full-Frame zurückfallen.
8. optional eine wiederverwendbare Sidecar-Datei erzeugen.

Er darf nicht:

1. den Quellinhalt umschreiben, sofern nicht ausdrücklich angefordert.
2. neue Frames erfinden.
3. echte Frames stillschweigend entfernen.
4. die Zeitachse verändern.
5. Inhalte aufgrund semantischer Vermutungen verwerfen.

---

# 14. Zielbild für eine spätere native Implementierung

Langfristig:

```text
old MP4
   ↓
standard decoder
   ↓
legacy display firewall
   ↓
segmented state stream
   ↓
smart scheduler
   ↓
tile/pixel state memory
   ↓
partial / local refresh panel
```

Auf alter Hardware endet die Optimierung früher:

```text
old MP4
   ↓
standard decoder
   ↓
legacy display firewall
   ↓
partial software rendering / reduced GPU work
   ↓
normal display output
```

Damit entsteht ein sinnvoller Übergangspfad von heutiger Hardware zu zukünftigen segmentierten Displays.
