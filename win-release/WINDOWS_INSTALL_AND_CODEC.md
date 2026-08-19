# WINDOWS_INSTALL_AND_CODEC.md — Windows-Installation + Media-Codec-Entscheidungen

Zweck: Bei späteren Upgrades NICHT wieder die gleichen Probleme haben. Dieses
Dokument fasst die **verifizierten** Installations-Entscheidungen und die
**geplanten** Media-Codec-Optionen für den Windows-Port zusammen. Pfade relativ
zu `win-release/`.

## 1. Was "Codec installieren" hier BEDEUTET (WICHTIG)

Die Linux-Referenz (`packaging/build_debs.sh`) registriert **KEINEN**
Media-Codec-Filter (kein GStreamer/VLC-Plugin). Sie installiert die Programme
als **systemweite Kommandos** in `/usr/bin` (`casu`, `casu-converter`, `mpcasu`,
`web-casu`) + App-Assets unter `/usr/share/casu-codec/`.

⇒ Die Linux-Parität für Windows ist: **`casu.exe` ins System-PATH + Startmenü/
Desktop-Verknüpfungen + `.casu`/`.mp5`-Dateityp-Assoziation**. KEIN Media-Foundation/
DirectShow-Filter nötig, um "exakt gleich" zu sein.

- Installer: `scripts/setup.nsi` (NSIS) → `dist/MPCASU-Setup-3.0.0.exe`
- PATH-Registrierung: `AddToSystemPath` (HKLM ...\Session Manager\Environment\Path)
  + `WM_SETTINGCHANGE`-Broadcast. Entfernung: `un.RemoveFromSystemPath`.
- Dateitypen: `HKLM\Software\Classes\.casu` / `.mp5` → `MPCASU.Container`
  (DefaultIcon + shell\open → MPCASU.exe "%1").

## 2. Optionale, ZUKÜNFTIGE Media-Codec-Registrierung (MF/DirectShow) — GEBAUT NOCH NICHT

Der Nutzer entschied bei Frage "systemweit als Codec?" → **"Auch als
Media-Codec (MF/DirectShow)"**. Das ist ein eigenständiges Groß-Projekt, das in
späteren Versionen gebaut werden kann. WICHTIGE Erkenntnisse für den Bau:

### 2.1 Was decodiert werden muss (CASUNAT2)
Der Windows-Port decodiert CASUNAT2 derzeit **nicht nativ** (nur Reader in
`src/core/casu/native_v2.cpp`; CASUNAT1/MP5 werden via Quell-Extraktion + libVLC
abgespielt). Ein MF/DirectShow-Decoder braucht zuerst den **CASUNAT2-Decoder**
(portiert aus `mpcasu_native_backend.py`, ~1280 Zeilen Python).

### 2.2 Video-Decode-Modell (aus casu/native_v2/video.py) — der Kern
- **Key-State** (`VIDEO_KEY_STATE`): vollständiges Frame. Payload =
  JSON-Meta + zlib-komprimierte RGBA-Ebenen. Format:
  `<u32 header_len><json meta><zlib plane>...`
  - Meta: `pixel_format`, `source_shape`, `color_metadata`, `planes[]`
    (shape, dtype, compressed_length).
  - Referenz: `casu/native_v2/video.py decode_key_state / _unpack / _decompress_exact`.
- **Tile-Update** (`VIDEO_TILE_UPDATE`): ersetzt Region `(x,y,width,height)`
  im gecachten Key-State-Frame. Meta enthält `region`, `base_state_hash`,
  `new_state_hash`; Ebenen-Daten zlib-komprimiert (RGBA).
  - Referenz: `casu/native_v2/video.py TileStateCache.apply_tile_update`.
  - Frame-Aufbau: `frame[y0:y1, x0:x1] = tile` je Ebene (`_bounds`).
- **Audio**: PCM, `decode_audio_block` (`casu/native_v2/audio.py`, 95 Zeilen).
- Integrität: `tile_digest_with_prefix`, `frame_identity_prefix`
  (`casu/strict/tiles.py`). Limits: MAX_DECODED_PLANE_BYTES 512 MiB,
  MAX_VIDEO_DIMENSION 32768, MAX_VIDEO_PLANES 8.

### 2.3 MF/DirectShow-Architektur (geplant)
- COM-DLL (`casu_mft.dll`, x86_64) mit **IMFTransform** (Media Foundation
  Transform), CLSID registriert via `MFTRegister` / HKLM\Software\Classes\CLSID.
  Video-Output: RGBA (oder YUV) Media-Foundation-Samples; Audio: PCM.
- ODER klassischer **DirectShow-Filter** (IBaseFilter/IGraphBuilder) + `regsvr32`.
- Registrierung im `setup.nsi` (nur wenn Decoder-DLL gebaut wird).
- Verifikation NUR auf echtem Windows möglich (Windows Media Player o.ä. lädt
  den Filter); unter Wine nur COM-Registrierung testbar.

## 3. Installer — Verifikations-Status (2026-08-19)
- `makensis scripts/setup.nsi` → `dist/MPCASU-Setup-3.0.0.exe` (PE32, lzma).
- Unter Wine getestet: Silent-Install (`/S /D=...`), installierte `MPCASU.exe
  --smoke` OK, Silent-Uninstall entfernt Verzeichnis. PATH + Dateityp-
  Registrierung im Installer (seit 2026-08-19; Verifikation der Registry-Einträge
  unter Wine als offener Punkt → BLOCKER-004).
- Icon: `assets/casu-installer-icon.ico` (aus `/home/error/casu-installer-icon.png`).

## 4. Zu beachten bei Upgrades
- **QtWebEngine existiert nur für MSVC**, nicht für MinGW. Web-Provider-Tabs
  (Spotify/Hearthis/Tidal/Netflix/BROWSE) → `CASU_HAVE_WEBENGINE`; MinGW=Stub,
  MSVC=`scripts/build-msvc.bat`. Siehe `roadmap/tools/mpcasu/PORT_ROADMAP.md`.
- **YouTube ist KEIN Browser-Tab** — yt-dlp → Loopback → libVLC.
- PATH-Registrierung nie doppelt anhängen (StrStr-Check); nie ohne
  `WM_SETTINGCHANGE` (sonst übernimmt die laufende Shell den neuen PATH nicht).
- Die Windows-Pakete (`dist/`) werden NICHT committet (`.gitignore`), sondern
  als GitHub-Release-Assets hochgeladen.
## 5. Playlist-Queue-Architektur (einheitlich, seit 2026-08-19)
- **Linux-Model ist FLACH** (casu/playlist.py PlaylistModel = Liste von Path/str);
  Playlist-**Gruppen** sind reine UI-Konstrukte im PlaylistPane (QTreeWidget).
  `load_playlist` addet NUR die Einträge; die Gruppe entsteht, wenn die .m3u
  selbst als Item ins Model kommt (Drag&Drop).
- **Einheitliche gemischte Queue**: Playlists + Dateien + URLs koexistieren.
- **Playlist-Play ohne Ausklappen**: `_play_playlist_full` (Linux) / flaches
  Auflösen + play_next (Windows) — spielt ALLE Einträge durch.
- **Merge**: `_on_playlist_merge` (Linux, Kontextmenü + mergeRequested-Signal) /
  `merge_selection_into_playlist` (Windows, Kontextmenü + Mehrfachauswahl) —
  speichert markierte Dateien/URLs in eine bestehende oder neue Playlist
  (dedupliziert). Siehe Commit 1432db0.
- **Absturzsicherheit**: leere/kaputte Playlists (PlaylistError), fehlende
  Dateien (existing_only), leere Merge-Auswahl → Toast, kein Crash.
- Tests: Linux `tests/test_playlist.py` (20), Windows `casu_playlist_test`
  (14 Checks unter Wine).
