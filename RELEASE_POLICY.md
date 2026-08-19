# CASU / MPCASU Release Policy

## Versionspolitik (VERBINDLICH, ab 2026-08-19)

- Nächste Release-Version ist **v5.0.0**; **v4.x wird bewusst übersprungen**
  (kein v4.0.0, keine v4.x-Reihe).
- Veröffentlicht: **v3.0.0** (Linux + Windows). Nächster Sprung: 3.0.0 → 5.0.0.
- v4.x ist intern für die v5-Planung reserviert (Konzepte/Design-Dokus), wird
  aber nie als Release veröffentlicht.
- Alle OS (Windows, Linux, macOS, Android) teilen sich die Versionsnummer
  (Release-Zug gemeinsam, siehe `ALL_RELEASE_V5/README.md`).

## Reife-Gates

CASU/MPCASU darf erst als fertiger 1.0-Codec/Player bezeichnet werden, wenn
alle folgenden Gates implementiert, automatisiert getestet und auf realen
Medien validiert sind:

1. **Native CASU-Payload** — echte segmentierte Nutzdaten, Key-States und
   Seek-Index.
2. **Source-resolution STRICT** — exakte Identität ohne Downscale- oder
   Threshold-Ersatz.
3. **Nativer Playerpfad** — `.casu → Reader → Scheduler → Cache → Renderer`,
   ohne Rückgriff auf extrahierte Legacy-Payload.
4. **Vollständiges Media Management** — Tracks, Untertitel, Kapitel und
   Audio-Geräte.
5. **Produktreife** — Library, Settings und reale Playback-Regressionen.
6. **Formatrobustheit** — Versionierung, Conformance, Checksums/Integrity,
   beschädigte Dateien, Recovery, Fuzzing und deterministische Reader/Writer-
   Tests.

Bis dahin ist das System ein Entwicklungs- bzw. Release-Candidate-System.
Eine GUI, ein Sidecar oder eine grüne Teiltestsuite genügt nicht als
Fertigstellungsnachweis.
