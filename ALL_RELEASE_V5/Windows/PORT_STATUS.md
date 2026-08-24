# PORT_STATUS — Windows (v5.0.0, Stand 24.08.2026)

**ONLINE:** https://github.com/error/wtf-placeholder — Setup-5.0.0.exe +
MPCASU-Windows-x86_64.zip (Gate 14/14 PASS, 24.08.-Build).

## Enthaltene Fixes (Nutzer-Reports 23./24.08.)
- **Admin-Modus:** Config/Lock/Session in %APPDATA%\Lino-Codec\MPCASU
  (Migration, Lock nie migriert, stale-Lock-Entfernung vor tryLock) —
  Normalmodus läuft.
- **Responsive:** Min-Size 980×620; Sidebar-ScrollArea (Labels wurden bei
  <820 px Höhe halb geclippt — Wine-Screenshot-Beweis); Diagnose-Karten
  wrappen (FlowLayout); Recording/YouTube/Settings/EPG-Scroll-Areas.
- **VIZ-Defaults:** Audio → Visualizer IMMER an + Cover standardmäßig
  sichtbar (Thumbnail-Fallback) — Wine-Audio-Playtest bewiesen.
- **Gezeichnete Nav-Icons** (QPainter, font-unabhängig — identisch zu Linux).
- LIVE-Zeitanzeige; Web-Backend/Pure-Web im Paket auf v5-Stand.

## Verification
- wine ctest 21/21 PASSED; Release-Gate 14/14 PASS.
- Wine-Screenshots: Seiten bei 980×620, Audio-Playtest (FFT + Cover).

## Nächste Schritte
- SMTC (Win+G-Media-Overlay) braucht cppwinrt → MSVC-only (P4, dokumentiert).
- Converter: Streaming-Executor/Ordnerhierarchie/Replace-Bar (P4).
