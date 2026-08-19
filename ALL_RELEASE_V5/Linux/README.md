# MPCASU / CASU-CODEC — Linux Release-Planung (ALL_RELEASE_V5)

Ziel: **Linux x86_64 (Debian/Ubuntu)**, Python/Qt-Desktop-Player
(`mpcasu_qt/`), C++-CLI/Codec (`casu/`), Web-Player (`web-casu/`, Pure Web),
paketiert als `.deb`.

Kanonischer Code: Repo-Root (`mpcasu_qt/`, `casu/`, `web-casu/`,
`packaging/`). Dieser Ordner ist die Release-Planung mit denselben
Hilfsdateien wie der Windows-Port.

## Status (2026-08-19)

- **v3.0.0 VERÖFFENTLICHT** — 4 DEB-Pakete + `MPCASU-PURE-WEB-3.0.0.zip` +
  kombinierte SHA256SUMS im GitHub-Release v3.0.0.
- Playlist-Queue-Feature fertig: `_play_playlist_full`, `_current_playlist_context`
  (Durchspielen ohne Ausklappen), `_on_playlist_merge` (Kontextmenü
  "Save selection to playlist…", dedupliziert) — Tests: `tests/test_playlist.py`
  (20), `tests/test_player_ui.py` (9) grün.
- MIME-Assoziation `.casu` via `packaging/casu-codec-mime.xml` (postinst:
  update-mime-database + update-desktop-database), im DEB verifiziert.
- **Nächste Version: v5.0.0** (v4.x übersprungen).

## Build (Linux → DEBs)

```sh
bash packaging/build_debs.sh    # baut 4 DEBs nach dist/ (ACHTUNG: leert dist/!)
```

Pakete: `casu-codec`, `casu-converter`, `mpcasu`, `web-casu` (Version 3.0.0;
bei v5.0: 5.0.0). Hinweis: `build_debs.sh` löscht `dist/` — nach dem Bauen
`git checkout -- dist/MPCASU-PURE-WEB-3.0.0.zip` (falls benötigt) und
`dist/SHA256SUMS` neu erzeugen.

## Installieren (Linux)

```sh
sudo apt install ./dist/casu-codec_3.0.0_all.deb ./dist/casu-converter_3.0.0_all.deb \
                 ./dist/mpcasu_3.0.0_all.deb ./dist/web-casu_3.0.0_all.deb
```

- Apps: `mpcasu` (Qt-Player), `casu` (CLI), `casu-converter`, `web-casu`.
- Dateitypen: `.casu`/`.mp5` → MPCASU über MIME-DB (postinst registriert).

## Apps

| App | Start | Anmerkung |
|-----|-------|-----------|
| CLI | `casu` | kind/verify/info/pack/pack-mp5/mp5-info/export/media/validate/… |
| Converter | `casu-converter` | Qt-GUI, Batch, Presets |
| Player | `mpcasu` | Qt-GUI, Playlist/Library/EPG/Visualizer, YouTube via yt-dlp→Loopback |
| Web | `web-casu` | Loopback-HTTP `/api/*`; Pure Web über `http://127.0.0.1:8497/web/` |

## Pure Web (frozen)

`MPCASU-PURE-WEB-3.0.0.zip` (SHA `b71b5d0b…`) — identisch in Linux- und
Windows-Paket (byte-identical).

## Working method

1. Feature → Backup (`win-release/scripts/safe-guard.sh backup <tag>`).
2. Implementieren → `tests/test_playlist.py` + `test_player_ui.py` grün.
3. `./win-release/scripts/test-guard.sh run` (Linux + Windows-Build).
4. DEBs bauen + SHA256SUMS → commit → push → Release-Update.