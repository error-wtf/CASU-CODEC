# HANDOVER — CASU-CODEC / MPCASU 3.0.0 (Linux + Windows)

Stand: **2026-08-19, ~11:00 UTC — ALLES REPARIERT, Release aktuell**
Zweck: Exakter Zustand + nächste Schritte für die nächste Session.

---

## 1. Projekt & Ziele

- Repo: `error-wtf/CASU-CODEC` (lokal: `/home/error/Codec-Casu`, Branch `main`)
- Ziel erreicht: **Exakt gleiche Apps auf Linux und Windows** (CASU-Codec,
  MPCASU-Player, Converter, Web-Backend), eingebetteter Browser (QtWebEngine,
  MSVC-only), setup.exe-Installer, Online-Repo aktuell.
- Nutzer erlaubt Änderungen am Linux-Referenzbaum (`mpcasu_qt/`, `packaging/`).
- Git-Token: `/home/error/gittoken.env` — via `GH_TOKEN="$(cat /home/error/gittoken.env)"`.

## 2. AKTUELLER ZUSTAND (alles grün)

- **Git `main` ist gepusht** bis `0722878` (enthält `1432db0` Playlist-Queue-Feature
  + `0722878` Release-DEBs/Doku). Remote = `06453ce..0722878`.
- **Linux-DEBs** (`dist/`): 4 Pakete, frisch gebaut (11:23 UTC) — mpcasu-DEB mit
  Playlist-Feature, casu-codec mit MIME-Association. Hashes in `dist/SHA256SUMS`
  (committet in `0722878`).
- **Windows-Artefakte** (`win-release/dist/`), KOMPLETT NEU gebaut (12:39–12:48):
  - `MPCASU-Windows-x86_64.zip` (249009070 B) — enthält MPCASU.exe **mit**
    Playlist-Merge (verifiziert via strings)
  - `MPCASU-Setup-3.0.0.exe` (177222233 B) — neu aus neuem ZIP gebaut,
    enthält das Feature (verifiziert)
  - `WINDOWS_RELEASE_GATE.json` — **14/14 PASS**, generated_utc 2026-08-19T10:48:55Z
  - `win-release/dist/SHA256SUMS` — ZIP + Setup-Hashes
- **Golden-Tests**: 8 PASS (verify_golden.sh). ctest Windows: 16/16 grün
  (inkl. neuem `casu_playlist_test`).
- **GitHub-Release v3.0.0** „CASU / MPCASU 3.0.0 — Playlist Everywhere (Linux + Windows)":
  - Alle 7 Assets + kombinierte `SHA256SUMS` (635 B, hochgeladen 10:55 UTC) sind
    AKTUELL; komb. SHA256SUMS wurde aus den hochgeladenen Assets berechnet
    (Download → sha256sum → Upload), DEB-Hashes mit lokalen Dateien verifiziert.
  - Release-Body aktualisiert: 16/16 ctest, unified playlist queue + Merge-Feature.
- **Backups** (safe-guard.sh): `v3-before-playlist-feature`,
  `v3-after-linux-playlist-fixes`, `v3-linux-playlist-merge-done`,
  `v3-playlist-feature-complete`.

## 3. NICHT GEBAUT / OFFEN (bewusst)

- **QtWebEngine-Realbuild nur unter Windows/MSVC** (MinGW = Stub).
  MSVC-Build auf echtem Windows: `scripts/build-msvc.bat` + `CMakePresets.json`.
- BLOCKER-004: PATH/Dateityp-Registry nur auf echtem Windows verifizierbar (Wine ok).
- BLOCKER-005: MF/DirectShow-Decoder (CODEC-001) geplant, **nicht gebaut**.
- WP-PURE-004: kein Browser unter Wine → Browser-Test nur auf echtem Windows.

## 4. NÄCHSTE SCHRITTE (nur falls weitergearbeitet wird)

1. Bei neuem Feature: Backup (`./win-release/scripts/safe-guard.sh backup <name>`),
   dann `./win-release/scripts/test-guard.sh run` (Linux-Tests + Windows-Build).
2. Release neu bauen NUR wenn nötig:
   ```bash
   cd /home/error/Codec-Casu/win-release
   # Vorsicht: Hintergrund starten, Tool-Timeout killt sonst den Prozess:
   setsid nohup ./scripts/build-windows-release.sh > test-results/release-build.log 2>&1 < /dev/null &
   ```
   **Skript-Bug Schritt 7b ist seit 2026-08-20 GEFIXT** (ZIP wird aus `dist/`
   entpackt statt `_stage/`; BUILD_DIR/DIST_DIR sind absolut). Kein manueller
   Workaround mehr nötig. Ohne funktionierendes Audio-Gerät: `SKIP_WINE=1`
   setzen (Player-Smoke/Golden hängen sonst), ctest separat mit
   `-E "casu_playback_vlc_test|casu_playback_youtube_live_test"`.
3. DEBs: `bash packaging/build_debs.sh` — **Achtung: leert `dist/`** (inkl.
   PURE-WEB-ZIP!). Danach wiederherstellen: `git checkout -- dist/MPCASU-PURE-WEB-3.0.0.zip`
   und `dist/SHA256SUMS` neu erzeugen.
4. Release-Update: `gh release upload v3.0.0 <datei> --clobber`; danach IMMER
   kombinierte SHA256SUMS aus den hochgeladenen Assets neu berechnen + hochladen:
   ```bash
   rm -rf /tmp/opencode/rel3 && mkdir -p /tmp/opencode/rel3 && cd /tmp/opencode/rel3
   for a in $(gh release view v3.0.0 --repo error-wtf/CASU-CODEC --json assets --jq '.assets[].name'); do
     gh release download v3.0.0 --repo error-wtf/CASU-CODEC --pattern "$a" --clobber; done
   sha256sum <alle-assets> | sort -k2 > SHA256SUMS
   gh release upload v3.0.0 --repo error-wtf/CASU-CODEC SHA256SUMS --clobber
   ```

## 5. SCHLÜSSELDATEIEN

- `win-release/apps/mpcasu/main_window.cpp` — `playlist_context_menu` +
  `merge_selection_into_playlist` (nach `playlist_double_clicked`)
- `win-release/apps/mpcasu/playlist.{hpp,cpp}` — `PlaylistModel`
- `mpcasu_qt/main_window.py` — Linux: `_play_playlist_full`,
  `_current_playlist_context`, `_on_playlist_merge`, `_resolve_playlist_target`
- `tests/test_playlist.py` (20), `win-release/tests/casu_playlist_test.cpp` (14)
- `win-release/scripts/{safe-guard,test-guard,build-windows-release,release_gate}.sh`
- `packaging/build_debs.sh` + `packaging/casu-codec-mime.xml`
- `win-release/scripts/setup.nsi` + `win-release/assets/casu-installer-icon.ico`
- `HANDOVER.md` (diese Datei, im Repo-Root)