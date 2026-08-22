# HANDOVER — CASU / MPCASU (Stand: 21.08.2026, spät)

Repo: `/home/error/Codec-Casu` (Branch `main`, Remote `https://github.com/error-wtf/CASU-CODEC.git`)
Token: `/home/error/gittoken.env` (nie im Klartext loggen)

---

## 0. AKTUELLER STAND (diese Session, abgeschlossen)

1. **v3.0.0 Windows-Parität abgeschlossen + online repariert** (Commit `775fd91`):
   - Web-Player-Tabs ECHT via **WebView2** (MinGW, DRM-fähig), persistente
     Provider-Profile, Fallback-Panel.
   - Installer: **Per-App-Icons** (EXE-Ressourcen + Shortcuts + Datei-Assoziation),
     `assets/assets`-Bug behoben; **Auto-Update** in-place (beide Scopes,
     taskkill vor Overwrite); **Non-Admin**-Modus (highest + HKCU/
     LocalAppData-Fallback).
   - Converter: Journal + Resume (casu::journal in casu_core), Advanced-
     Optionen fließen in Manifest/MP5/Report.
   - Web-Backend: Security-Headers wie web_casu.py.
   - Verifikation: ctest 16/16 (VLC-Probe jetzt deterministisch via
     CASU_VLC_OPTIONS=--aout=dummy), Gate PASS, Wine Install/Update/Uninstall OK.
   - Release v3.0.0 Assets erneuert (--clobber) + Notes Update (IV).

2. **v5.0.0 Windows + Linux gebaut** (v4 übersprungen, Referenz=v3):
   - Versionen überall auf 5.0.0 (setup.nsi, packaging.cmake, release_gate.sh,
     pyproject.toml, build_debs.sh, casu/__init__, GUI-Anzeigen, README,
     RELEASE_GATE_STATUS.json, web/index.html ?v=).
   - **WICHTIG (Design):** CASU-Containerformat bleibt `3.0.0`
     (`CASU_FORMAT_VERSION` in casu/core.py, C++ manifest.cpp schreibt fest
     "3.0.0") — ältere Player akzeptieren neue Dateien weiter. Test
     test_schema_accepts_current_version auf neue Invariante umgestellt.
   - Linux: pytest 425 passed (Chromium-Umgebungstest pre-existing rot —
     NICHT versionsbedingt), DEBs gebaut, Pure-Web-Zip aus GitHub-Release
     wiederhergestellt (build_debs.sh leert dist/!).
   - Windows: Pipeline PASS, MPCASU-Setup-5.0.0.exe + Zip neu.

3. **NÄCHSTE SCHRITTE:** GitHub-Release `v5.0.0` anlegen (Assets: 4 DEBs +
   Pure-Web-Zip + SHA256SUMS aus `/home/error/Codec-Casu/dist`; Windows-Zip +
   Setup aus `win-release/dist`). Danach Android (Nutzer-Entscheidungen
   getroffen: APK-Sideload only, yt-dlp bundled, Touch-UI erwünscht) —
   ABER: Platte nur noch ~28 GB frei → erst aufräumen, dann SDK/NDK/Qt-
   for-Android (~10–17 GB). Mac-OS danach.

---

## 0b. VOLLSTÄNDIGES ZEILEN-AUDIT (10/10 Paare abgeschlossen, Stand 22.08.)

ALLES verglichen: (1) main_window-UI, (2) Queue-Semantik, (3) web_casu↔web-backend,
(4) cli.py↔casu-cli, (5) casu_converter↔Converter, (6) Playback-Backends,
(7) playlist.py, (8) core.py+strict/*+tiles+probe (Analyse-Kern),
(9) native_v2/* ALLE 12 Dateien, (10) settings/recording/epg/library +
theme.py-VOLLSTYLESHEET + app.py-Entry + alle mpcasu_qt-Module inkl.
Rückrichtung (C++-Dateien ohne Python-Pendant: keine außer dokumentierte).

GEFIXT (Commits 775fd91..45c4139): Queue-Semantik komplett + 126-Check-Suite,
Playlist-Parser/Format-Byte-Parität, move_children-Datenverlust, Child-Play,
Merge-Staleness, Markierungspersistenz, Delay-µs-Bug, CLI --retry/transcode
atomar+force+verification_result, Web-Access-Log, Versionstrings, Seek ±10s.

### TIER 1 — ABGESCHLOSSEN ✅ (2026-08-22: CASU-0..5 `9fb279d`+`e64ed63`, ANA-STRICT `7c873e2`, EPG `3142918`)
1. **CASUNAT2 gesamt** (Audit 9): C++ hat nur „Integrity-Reader light“.
   FEHLEND: NativeV2PayloadValidator (feed/finalize: Topologie+Semantik),
   _decode_recovery_point (checkpoint/prefix-hash/offset-ref-Checks),
   digest_before_chunk-Snapshot, Seek-Cross-Checks (R21/R23), finalize(
   require_system) [Datei ohne SEEK_INDEX gilt als ok!], read_chunk_at/
   read_audio_block_meta_at/seek_video/reconstruct_video+TileStateCache
   [Video-Seek unmöglich], recover_native_v2/repair_native_v2, WRITER gesamt
   (writer.py 201Z: kanonische STREAM_CONFIGs, recovery_interval=32-
   Checkpoints mit checkpoint_sha256-Doppeltserialisierung, INTEGRITY_TABLE
   pts=index_offset), CONVERTER gesamt (converter.py 611Z: nativ-pixfmt-
   rawvideo-Pipe, Tile-Vergleich mit previous_hashes-Memo, key_due-Fraction,
   AUDIO s16le-Pipe, WebVTT-Reencode+ASS-Attachment, Bitmap sub2video ffv1-
   rgba, CHAPTER ns, Cover-Normalisierung). Payload-Binärformate vollständig
   spezifiziert im Audit (Umschlag [u32 BE meta_len][JSON][zlib-Blobs]).
   KRITISCH für Byte-Kompatibilität: Tile-Hash nutzt Python-repr(shape/
   color_metadata) mit Präfix „CASU-STRICT-TILE-v1\0“ — C++ muss repr()
   replizieren; dump_json braucht ensure_ascii=False-Modus.
   Reader-Härtung zusätzlich: JSON-Duplikat-Keys werden akzeptiert (müssen
   abgelehnt werden), strtoll ohne errno (Clamping statt Fehler), ftell>2GiB
   auf MinGW (32-bit long!), Limits hartkodiert statt CasuLimits-Struct,
   positioneller statt offset-keyed Hash-Vergleich, max_file_bytes ungeprüft.
2. **Analyse-Kern** (Audit 8) — ✅ TEILWEISE ERLIEDIGT (Commit 895b5ca):
   Preview-Pfad + Audio-Analyse + RLE + Tile-Vergleiche + Seek-Index aus
   echten Segmentgrenzen jetzt REAL in src/codec/casu/analyze.{hpp,cpp};
   gegen Python-Referenz verifiziert (mean_delta 8-Dekimalen identisch,
   1419 Tiles identisch). P0-Fixes drin (channels, format-only duration,
   mode-Validierung, fps-Plumbing). VERBLEIBT: strict-Pipeline (native-
   pixfmt-Rawvideo-Decodierung + CanonicalFrame/PlaneLayouts + Identity-
   Metadata; decoder.py/canonical.py/state_builder.py) — alle Modi laufen
   bis dahin ehrlich über die Hint-only-Pipeline. Flaky-Hinweis: Wine-GUI-
   Tests (smoke/converter) unter Desktop-Last zeitouten — serial + idle
   laufen lassen; kein Codefehler.
   URSPRÜNGLICH: cli_util build_manifest schrieb Fake-Segment
   „active“ statt echter Segmentierung. FEHLEND: strict-Pipeline (decoder.py
   Pixelformattabelle ~30 Formate, rawvideo-Pipe NATIV pix_fmt, CanonicalFrame
   PlaneLayouts, SHA256-Tile-Digest HOLD/UPDATE, iter_state_map 3er-Fenster,
   valid_until-Logik), Preview-Pfad (gray8-Pipe fps/scale/format=gray, MAD-
   Schwellen motion≥0.010/low_motion≥0.0015/static, Tile-Schwellen
   {strict:0.0,vl:0.01,adaptive:0.05}, Grid {0.01,0.03,0.08}, Intervall-Dedup),
   Audio-Analyse (f32le-Pipe, 20ms-RMS-dBFS, −55/−38dB), rle/interval mit
   Banker's-Rounding, seek_entries aus ALLEN Segmentgrenzen sortiert,
   Manifest-Felder video.*/audio.* (state_map/state_counts/decoded_frame_count/
   spatial_analysis/strict_pixel_identical_available...). Blaupause P0–P9 im
   Audit (~3–4 PW); P0-Schnellfixe: channels-Feld fehlt in streams-Projektion,
   Dauerpolitik duration_s()=max(streams) statt format-only, Modus-/isfinite-
   Validierung.
3. **EPG-Zeitoffset-Bug** (epg.cpp:44–50): XMLTV start/stop „+0200“ wird
   ignoriert → Guide 2h versetzt. Plus: kein Extended-M3U (tvg-id/tvg-name/
   group-title/tvg-logo/url-tvg), kein tvg-id-Matching (M3U-Kanal-id=Pfad!),
   keine Limits (32MB/10k/100k), icon-src fälschlich als Stream-URL,
   stop≤start-Filter fehlt, Sortierung fehlt, category fehlt (sub-title
   stattdessen), naiver Attribut-/Entity-Parser.

### OFFEN — TIER 2 (App-Features)
4. **Recording**: -map_metadata/-map_chapters fehlen; KEIN Temp-Write+
   ffprobe-Verify+atomarer Publish (direkt ins Ziel); record_format-Setting
   wirkungslos (Quell-Suffix!); Splitting (record_split_minutes) komplett
   ohne Wirkung (kein Timer/partNNN); Namensschema ohne Stem; keine Suffix-
   Whitelist {.mkv,.mp4,.mov,.ts,.m2ts,.webm,.ogg,.mp3,.flac,.wav}; kein
   Selbstüberschreibschutz; SIGTERM falsch-negativ.
5. **Settings**: audio_device-Key fehlt ganz; session.json nicht getrennt;
   keine Versionshülle {"version":1,"player":{}}; Save NICHT atomar (kein
   tmp+fsync+replace), Lesen ohne 1MiB-Bound; rate ohne 0.25–4.0-Klemme beim
   Load; cache_limit-Klemme [64,8192]≠[0,65536]; Keys record_dir/repeat ≠
   recordings_dir/repeat_mode; watched_folders ohne 100er-Limit/Validierung.
6. **Library**: Felder size_bytes/modified_ns/resume_seconds/duration_seconds/
   last_played_ns/last_seen_ns fehlen (Resume-Datenmodell!); Bookmarks+
   gespeicherte Playlists fehlen; Scan-Extensions lückenhaft (.ts .m2ts .mpg
   .mpeg .wma .aiff .alac .m4v .casu .mp5 fehlen; .m3u/.pls fälschlich drin);
   kein 100k-Cap; keine "(unknown)"-Gruppe; Gruppierung case-sensitiv
   (casefold!); Delays ungeklammt ±5000ms; Prefs nicht atomar.
7. **Web-Backend**: stream-proxy Policy nie gesetzt → IMMER 403 (Radio-Proxy
   tot; Port von _allowed_proxy_target nötig); trusted_request(mutation)-
   Sec-Fetch-Site/Origin-Check fehlt bei POSTs; /api/media URL-Token-Session
   wird bei GET gelöscht → Seek/Retry 404; Session-Eviction(64)/Leak;
   Upload puffert bis 16GiB im RAM; Port-Takeover+--check/--no-browser Flags;
   kind:"media"→"video"/"audio"; Content-Type-Tabelle erweitern.
8. **Visualizer**: synthetische Sinus-Animation statt echter FFT über dekodiertes
   PCM (decode_all_pcm/window_wave/live_fft 2048→1024bins); Stream-Viz-Pipe
   (~40Hz ffmpeg s16le) fehlt; Sichtbarkeits-/Pause-Drossel des CPU-Fixes.
9. **Playback**: Consent-Gate nur Suche, PLAYBACK resolved ungefragt;
   --avcodec-hw=none + SAFE_MEDIA_OPTIONS nie gesetzt (media_add_option tot);
   file://-URIs defekt am Backend; yt-dlp-Resolve BLOCKIERT GUI bis 45s
   (async+Generations-Guard nötig); Resume-Obergrenze dur−5 fehlt; ERROR-State
   teardown statt Diagnose stehenlassen; Equalizer-API; Temp-Sinks nie
   gelöscht; QtVideoSurfaceSink (nativer CASUNAT2/MP5 Untertitel/Cover-Pfad,
   videoframe.py:177-262) fehlt; Wheel-Volume über Video fehlt.
10. **UI/Rest**: YouTube-Ergebnis nicht in Queue eingereiht (+async Titel-
    nachlauf); Rail-Modus <1200px fehlt; Topbar-Seitentitel/Back-Sichtbarkeit;
    A-B-Toasttexte/Semantik (B vor A → Fehlermeldung nicht Reset); Snapshot-
    Präfix snapshot-<stamp>.png; Statusmeldungen Repeat/Shuffle/Mute/Rate;
    Queue-leer-Text wortgleich; Startstatus „{name} · {state} · {vlc-version}“;
    format_duration truncation statt llround; Esc verlässt Vollbild nicht
    richtig; Ctrl+L SourcesView statt Modal; right_panel_width 310 vs 370
    (Queue-Pane 60px schmaler!); FsOverlay-Styling (#07090bdd/r8 vs opak);
    Single-Instance ohne IPC-Dateiweiterleitung; Stage-Routing ohne ffprobe-
    Audio/Video-Gating (Visualizer kann über Video liegen); Sidebar-Fußzeile
    Versionslabel; Converter: Streaming-Executor tot/Live-Fortschritt/ETA-
    Zeile/Ordnerhierarchie(_source_root)/Replace-Bar zählt existierende/
    attempts+resumed-Felder/Advanced auch bei To-CASU/Source-Inspection/
    Fensterhöhe 720vs760/Listbg PANEL vs input_bg; CLI: Fehler auf stderr
    statt stdout, benchmark --output-Langform defekt, pack-mp5 512MB-Cap+
    STREAM_CONFIG-Metadaten, argparse-Strenge (unbekannte Flags geschluckt).

ANDROID-TOOLCHAIN-STAND (22.08., installiert unter /opt/android-sdk):
cmdline-tools latest ✓ · platform-tools ✓ · platforms;android-34 ✓ ·
build-tools;34.0.0 ✓ · NDK 26.3.11579264 ✓ · JDK 25 (System) ✓.
GESAMT nur 2,5 GB (Platte: 72 GB frei). NOCH OFFEN: Qt 6 for Android
(aqtinstall, ABIs arm64-v8a + armeabi-v7a + x86_64; WebEngine nur arm64
sinnvoll) + libVLC-Android-Binaries + Gradle via androiddeployqt.
NÄCHSTER ANDROID-SCHRITT: aqt install-qt android qt_6_8_3 (?) → Hello-APK
nach ALL_RELEASE_V5/Android/RUN_CHECKLIST Gate 1.

START-PROMPT NÄCHSTE SESSION (kopieren):
„Lies /home/error/HANDOVER.md §0b. Arbeitet die Tier-Liste ab:
(1) CASUNAT2-Stack nach Blaupause Audit-9 (Stufe 0: JSON-Duplikat-Keys+
    strtoll-errno+Surrogates+zlib-exact+CasuLimits; Stufe 1: Tile-Hash mit
    Python-repr-Kompatibilität; Stufe 2: Validator feed/finalize; Stufe 3:
    Writer; Stufe 4: Reader seek_video/reconstruct/recover; Stufe 5:
    Converter-Pipeline). Danach (2) STRICT-Analyse-Pipeline nach Blaupause
    Audit-8 P2-P5. Dann Tier 2 Items 3-10. Wine-GUI-Tests nur bei ruhigem
    Desktop serial fahren (ZapZap-Last = Flaky-Timeouts). Erst bei
    vollständig grünem Gate + ctest 16/16: GitHub-Release v5.0.0 anlegen,
    dann Android (APK-Sideload, yt-dlp-bundled, Touch-UI) und macOS.“

STATUS V5-VERSIONEN: Windows+Linux v5.0.0 GEBAUT (Version-Bump komplett,
Assets lokal in win-release/dist + dist/) — aber BEWUSST noch NICHT als
GitHub-Release veröffentlicht (Tag v5.0.0 existiert nicht), bis Tier-Liste
abgearbeitet ist. Android/Mac-OS: Planungsdokumente komplett in
ALL_RELEASE_V5/{Android,Mac-OS}/, keine Builds yet.

HARTE REGEL (NUTZER, VERBINDLICH ab 22.08.):
VOLLSTÄNDIGE PARITÄT ZUERST. Keine Android-/macOS-Arbeit, kein v5.0.0-
GitHub-Release und keine neuen Features, BEVOR die komplette §0b-Tier-Liste
abgearbeitet ist und Linux↔Windows deckungsgleich sind (Nachweis: ctest
16/16 + neue Paritätstests + Audit-Checkliste je Punkt abgehakt).
Erst danach: Release v5.0.0 → Android → macOS.

REIHENFOLGE nächste Sessions: Tier 1 (1 CASUNAT2-Stack, 2 Analyse-Kern,
3 EPG-Fixes schnell), dann Tier 2 (4→10). Erst bei Abschluss: GitHub-Release
v5.0.0 anlegen (Tag existiert bewusst NICHT). Danach Android (Entscheide §0).

## 1. AKUTE LAGE (URSPRÜNGLICH, GELÖST)

> „der mpcasu windows und alle windows programme sind noch broken und in mpcasu
> ruft er die webseiten netflix, spotify, tidal und hearthis nicht innerhalb des
> players auf und spielt null nada ab - das ist nicht exakt wie in linux"

**Root Cause (verifiziert):**
- `win-release/apps/mpcasu/web_player_tabs.cpp`: echter eingebetteter Browser
  NUR hinter `#if defined(CASU_HAVE_WEBENGINE)`.
- Der Windows-Build ist **MinGW**, und QtWebEngine gibt es offiziell nur für
  MSVC → Build läuft ohne `CASU_HAVE_WEBENGINE` → Tabs SPOTIFY/HEARTHIS/TIDAL/
  NETFLIX/BROWSE sind ein **Stub**: Seite öffnet sich nicht im Player, nichts
  spielt ab. Linux (`mpcasu_qt/webplayers.py`) nutzt QWebEngineView mit
  persistentem Profil (Cookies/Logins bleiben erhalten).
- Alle bisherigen „Parität"-Commits haben UI-Struktur/Navigations/Features
  nachgezogen, aber DIESE zentrale Funktion ist im MinGW-Paket nicht echt.
  Die Screenshots/Wine-Verifikation haben nur die Tab-Leiste geprüft, nicht
  den eingebetteten Browser-Inhalt.

**Nutzer-Direktiven (kumulativ, verbindlich):**
1. Linux-App(s) und Windows-App(s) müssen IDENTISCH sein in Aufbau UND Funktion.
2. ALLE Apps prüfen (nicht nur mpcasu): converter, web-backend, casu-cli.
3. Erst wenn alles perfekt identisch ist UND funktioniert → neu builden,
   Repo pushen, GitHub-Release aktualisieren (Token in `/home/error/gittoken.env`).
4. Nicht in Wiederholungs-Loops hängen; zügig handeln.

---

## 2. LÖSUNGSWEGE WEB-PLAYER (Entscheidung nötig / umzusetzen)

### Option A — MSVC + QtWebEngine (dokumentierter Plan, BLOCKER in PORT_STATUS.md)
- `scripts/build-msvc.bat` existiert laut Doku; braucht MSVC-Toolchain +
  Qt-MSVC-Kit mit WebEngine (third_party/qt hat aktuell nur `mingw_64`!).
- Auf dieser Linux-Kiste nur via msvc-wine (msvc-wine Projekt) machbar —
  aufwendig, aber dokumentiert als Ziel für v5.0.0.
- Achtung: QtWebEngine-Chromium bringt KEIN Widevine mit → Netflix bleibt
  schwarz, Spotify Web ok. Parität „Funktion" also NICHT voll gegeben.

### Option B — Microsoft Edge WebView2 embedden (EMPFOHLEN)
- WebView2 = Edge-Runtime, auf Win10/11 praktisch immer vorhanden, hat
  **Widevine DRM** → Netflix/Tidal/Spotify spielen WIRKLICH ab (besser als
  QtWebEngine-Lösung).
- Machbar aus MinGW ohne MSVC:
  - Header `WebView2.h` (+ `WebView2EnvironmentOptions.h`) aus dem
    WebView2-SDK (NuGet „Microsoft.Web.WebView2", nur Header nötig) vendorieren
    nach `win-release/third_party/webview2/`.
  - Loader `WebView2Loader.dll` (x64, redistributable) zur Laufzeit per
    `LoadLibraryW` + `GetProcAddress("CreateCoreWebView2EnvironmentWithOptions")`
    laden → kein Import-Lib-Problem.
  - C++-Hostklasse `WebContainerWidget` (QWidget): native Child-HWND
    (`CreateWindowExW`), Controller/CompositionController, Resize folgt
    QWidget-Geometry, `Navigate(url)`.
  - In `web_player_tabs.cpp` neuen Zweig `#elif defined(CASU_HAVE_WEBVIEW2)`
    bauen: pro Tab eigener Container, gleiche URLs/Handoff wie webplayers.py,
    persistentes User-Data-Folder `%APPDATA%/CASU/webview2/<provider>`
    (Logins bleiben wie bei Linux-Profil).
  - Fallback: wenn Runtime/Loader fehlt → Hinweis-Panel im Tab + Button
    „im Standardbrowser öffnen" (heutiges Stub-Verhalten).
- Package: `webview2_loader.dll` ins NSIS/Zip aufnehmen; optional Bootstrapper-
  Link (MicrosoftWebView2Installer) in About/Settings.

### Sofortmaßnahme unabhängig von A/B (damit „nichts tot" wirkt):
- Stub-Zweig heute so umbauen, dass er offen den Fallback zeigt (Label
  „Embedded browser requires WebView2 runtime" + extern öffnen), statt leerer
  Tab-Fläche — Transparenz gegenüber Nutzer.

---

## 3. „ALLE ANDEREN APPS ÜBERPRÜFEN" — Status & Restarbeiten

| App | Windows | Linux-Referenz | Status |
|---|---|---|---|
| mpcasu | `win-release/apps/mpcasu` | `mpcasu_qt/main_window.py` | Struktur/Features weitgehend paritätisch (siehe §4), **ABER: Web-Player broken (§2)**, und Endverifikation auf echtem Windows fehlt |
| converter | `win-release/apps/converter` | `linux-release/casu_converter.py` | UI+Engine weitgehend portiert (76055f4); **offen:** tile_size/key_interval/analysis_fps fließen NICHT in native-v2-Encoding ein (C++ packt CASUNAT1/sidecar/MP5, kein native-v2-Encoder wie Python); Pause/Resume/Retries implementiert, Resume liest Report NOCH NICHT (filtert nur existierende Outputs); Journal (conversion_journal_path) fehlt |
| web-backend | `win-release/apps/web-backend` | `web_casu.py` | Endpoint-Surface identisch + Static-Serving ✓; **prüfen:** Range/206-Details, Security-Headers (Linux setzt konservative Browser-Header), Pure-Web-Dateien im Paket unter `web/pure` |
| casu-cli | `win-release/apps/casu-cli` (casu.exe) | `casu/cli.py` | Befehlssuperset ✓; Details/Output-Formate nicht 1:1 gegengetestet |

Zusätzliche Prüfpunkte für „broken"-Meldung auf echtem Windows:
1. **ffmpeg/ffprobe/yt-dlp.exe** liegen unter `<install>/tools/` — werden sie
   gefunden? (`main.cpp` setzt Tool-Env über `exe_dir + "/tools/"`; verifizieren,
   dass MPCASU denselben Mechanismus nutzt wie web-backend).
2. **DLL-Set** im Zip/NSIS: Qt6*DLLs, libcrypto/libssl, libgcc/libstdc++/
   libwinpthread (static-Flags gesetzt, aber DLLs liegen trotzdem bei),
   VLC-Plugins? Falls LibVLC genutzt wird: `libvlc.dll` + `plugins/` nötig.
3. **SmartScreen/AV**: Setup ist unsigniert → Windows blockt evtl. Start
   („app doesn't start" könnte auch das sein). Unbundled-Zip alternativ testen.
4. Echtes Windows-Log sammeln: `MPCASU.exe` per CMD starten und Fehlermeldung
   erfassen (fehlende DLL wird dort benannt).

---

## 4. WAS BEREITS ERLEDIGT IST (Kontext)

Commits (alle gepusht):
- `123911b` 21 UI-Paritäts-Lücken · `9a71dc1` Queue-Rest · `106a9af`
  Navigations-Fix (Seiten-Indizes!) + Playlist-Formate (XSPF/WPL/JSPF/ASX/RMP/
  RAM/MPCASU-JSON) · `97c9d55` Sidebar identisch · `ac2b7e8` Topbar/Statusbar/
  PLAYLIST-Pane/„Drop media here"/Thumbnails/Per-Media-Preferences/Spotify-URL-
  Expansion · `02dfddf` Doku · `76055f4` Converter-Parität.

Release v3.0.0: Assets 6× mit --clobber erneuert (Zip, Setup.exe, SHA256SUMS,
Gate-JSON, Screenshot); Notes mit Updates 2026-08-20/21 (I)(II)(III).
Letzter Gate: PASS, `generated_utc 2026-08-21T17:36:30Z`; ctest zuletzt 16/16
(inkl. youtube_live). Frische Silent-Installation unter Wine ok.

WICHTIG: Wine-Verifikation ≠ echtes Windows. Der Nutzer testet auf echtem
Windows — dort ist der Web-Player-Stub sofort sichtbar. Wine-Grün heißt nur
„Start/DLLs/API ok".

---

## 5. TECHNISCHE NOTIZEN (für Weiterarbeit)

- Build: `cd win-release/build-win64 && cmake --build . --target <tgt> -- -j$(nproc)`
  Targets: casu_mpcasu, casu_converter, casu_web_backend(?), casu_cli(→casu.exe).
- Full build: `cmake --build . -- -j$(nproc)`; ctest:
  `WINEPREFIX=/tmp/opencode/wine-prefix WINEDEBUG=-all ctest --test-dir build-win64`
  (youtube_live kann netzwerk-flaky sein → Rerun).
- Release: `cd win-release && SKIP_WINE=0 bash scripts/build-windows-release.sh`
  → dist/MPCASU-Windows-x86_64.zip, MPCASU-Setup-3.0.0.exe, SHA256SUMS,
  WINDOWS_RELEASE_GATE.json.
- Screenshots: MPCASU + Converter unterstützen `--screenshot Z:\tmp\...png`
  (Converter seit 76055f4); OCR via tesseract; Geometrie via tesseract TSV.
  Linux-App startbar: PySide6 installiert; Helper
  `/tmp/opencode/shots/run_linux_app.py` (xvfb-run, `_navigate(page)`).
- Push: `TOKEN=$(cat /home/error/gittoken.env) && git push
  "https://x-access-token:${TOKEN}@github.com/error-wtf/CASU-CODEC.git" main`
  (gh auth login schlägt fehl — read:org fehlt; `GH_TOKEN=$TOKEN` reicht für
  gh release upload/edit).
- Seiten-Indizes player-page Stack: 0 NOW PLAYING, 1 ABOUT, 2 LIBRARY,
  3 SETTINGS, 4 EPG, 5 RECORDING, 6 VISUALIZER, 7 YOUTUBE, 8 WEB PLAYERS.
  Stage-Stack: 0 VideoSurface, 1 Visualizer, 2 stage_empty_ (Drop media here);
  Routing über `stage_media_active_` + `update_stage()`.
- Kein `is_video_ext()` in main_window.cpp! Vorhandene Helfer: `is_audio_ext`,
  `is_casu_container`, `is_network_like`.
- Backend-Delays geben void zurück (anders als Python-API).
- Library-Preferences: separate Datei `<library>.prefs.json`
  (`PlaybackPreferences`, apply bei Play, persist bei Track/Delay/Close).
- Thumbnails: `request_queue_thumbnails()/apply_thumb()`,
  `casu::media::thumbnail_for` → PPM-Cache unter `$HOME/.cache/mpcasu/thumbnails`
  (unter Wine im Prefix-HOME), Icons 54×38 KeepAspectRatioByExpanding.
- AGENTS.md beachten: Linux-Entwicklung in `linux-release/` (gitignored),
  Windows strikt getrennt unter `win-release/`.

---

## 6. NÄCHSTE SCHRITTE (Reihenfolge)

1. **Web-Player echt machen** (Option B WebView2 bevorzugen):
   - third_party/webview2 Headers + Loader-DLL beschaffen (NuGet-Paket
     entpacken; Loader-DLL x64 redistributable).
   - `WebContainerWidget` (HWND-Host) + `#elif defined(CASU_HAVE_WEBVIEW2)`
     in `web_player_tabs.cpp/.hpp`; persistente Profile je Provider;
     URLs/Search-Handoff exakt wie `mpcasasu_qt/webplayers.py` übernehmen.
   - Fallback-Panel + extern-öffnen-Button im Stub-Zweig.
   - NSIS/CMake: Loader-DLL paketieren; CMake-Option `CASU_HAVE_WEBVIEW2=ON`
     im MinGW-Build setzen.
2. **Echtes Windows-Diagnose**: Nutzer bitten, MPCASU.exe per CMD zu starten
   bzw. Zip-Variante zu testen → konkrete Fehlermeldung (fehlende DLL?
   SmartScreen?). Parallel: DLL-Audit des Pakets automatisieren (dumpbin-los:
   objdump -p | grep "DLL Name" über alle Exes + alle DLLs rekursiv prüfen).
3. Converter-Restpunkte: native-v2-Encoding-Parameter wirksam machen ODER
   ehrlich deklarieren; Resume aus Report lesen; Journal-Datei schreiben;
   tile/key-interval in MP5/native-Manifest eintragen (Metadaten).
4. web-backend: Security-Headers + Range-Verhalten gegen `web_casu.py`
   diffen; pure-web Pfad im Installer prüfen.
5. casu-cli: Output-Formate je Befehl gegen cli.py snapshot-testen.
6. Erst danach: Full Build + ctest + Gate + frische Installation (Wine) +
   Commit/Push/Asset-Upload/Notes/Doku (Nutzer-Vorgabe: erst bei perfekter
   Parität releasen).

Kontakt-Punkte im Repo: `ALL_RELEASE_V5/Windows/PORT_STATUS.md`,
`SESSION_HANDOVER.md`, `AGENTS.md`.

## 0c. EXECUTION CONTRACT (maximal bindend)
Pro Punkt aus §0b gilt ABNAHME nur bei: (a) vollständige Portierung laut
Blaupause — keine Stubs/TODOs; (b) Verhalten gegen Python-Referenz
gegentestet (gleiche Inputs → identische Outputs/Felder); (c) ctest 16/16
grün; (d) Eintrag hier mit ✅+Commit-Hash. Reihenfolge zwingend:
1.CASUNAT2 Stufe 0→5  2.Strict P2–P5  3.EPG  4–10 Tier2  → Gate → v5.0.0.
Checkliste (abzuhaken):
[x] CASU-0 JSON-Härtung ✅ `9fb279d` (Duplikat-Keys/Surrogates/errno/ensure_ascii/CasuLimits; Tests in casu_natv2_parity_test)
[x] CASU-1 Tile-Hash/repr ✅ `9fb279d` (CASU-STRICT-TILE-v1\0, Tuple-repr exakt, digest()-"None"-Suffix)
[x] CASU-2 Validator ✅ `9fb279d` (validate_manifest + feed/finalize, exakte Referenz-Semantik)
[x] CASU-3 Writer ✅ `9fb279d` (kanon. STREAM_CONFIGs, Recovery-Checkpoint-Doppeltserialisierung, INTEGRITY_TABLE pts=index_offset) — Writer-Ausgabe BYTE-IDENTISCH zur Referenz (gen1/gen2)
[x] CASU-4 Reader(seek/reconstruct/recover) ✅ `9fb279d` (R21/R23, offset-keyed Hash-Vergleich, read_chunk_at/audio_meta, TileStateCache, recover/repair)
[x] CASU-5 Converter ✅ `e64ed63` (converter.py-Komplettport über strict::FrameSource; Konvertierung BYTE-IDENTISCH auf lossless-Fixture — casu_natv2_convert_test ALL PASS)
[x] ANA-STRICT decoder/canonical/state_builder ✅ `7c873e2` — iter_state_map 3er-Fenster + valid_until + as_dict-Records RECORD-IDENTISCH zur Python-Referenz (120/120 auf Fixture); analyze_strict_video-Struktur komplett; CLI mode=strict läuft jetzt produktiv
[x] EPG-offset+tvg ✅ `3142918` — Extended-M3U+XMLTV-Komplettport; UTC-Offsets, tvg-Matching, Sortierung, Limits, Entities; casu_epg_parity_test IDENTISCH zur Referenz
[ ] REC verify/split/format [ ] SET atomic/audio_device/session
[ ] LIB felder/extensions/casefold [ ] WEB proxy-policy/trusted/media-token
[ ] VIZ FFT [ ] PLAYBACK consent/hw/async [ ] UI-Texte+Breite370
