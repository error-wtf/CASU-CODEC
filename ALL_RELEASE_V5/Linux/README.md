# MPCASU / CASU-CODEC — Linux Release-Planung (ALL_RELEASE_V5)

Ziel: **Linux x86_64 (Debian/Ubuntu)**, Python/Qt-Desktop-Player
(`mpcasu_qt/`), C++-CLI/Codec (`casu/`), Web-Player (`web-casu/`, Pure Web),
paketiert als `.deb`.

Kanonischer Code: Repo-Root (`mpcasu_qt/`, `casu/`, `web-casu/`,
`packaging/`). Dieser Ordner ist die Release-Planung mit denselben
Hilfsdateien wie der Windows-Port.

## Status (2026-08-20)

- **v3.0.0 VERÖFFENTLICHT** — 4 DEB-Pakete + `MPCASU-PURE-WEB-3.0.0.zip` +
  kombinierte SHA256SUMS im GitHub-Release v3.0.0.
- **Playlist-Gruppen-Semantik (nicht-destruktiv, implementiert + getestet):**
  Playlist-Gruppen bleiben im Queue sichtbar und werden beim Spielen **nie
  aufgelöst**; die Wiedergabe läuft über die logische Sequenz (`_play_seq` —
  Gruppen laufen in ihre Einträge auf, lose Dateien/URLs werden dazwischen
  mitgespielt, inkl. Shuffle/Repeat). Gruppen + Mehrfachauswahlen (Strg/Shift)
  sind verschiebbar (↑/↓, Kontextmenü "Move up/down"); Einträge sind
  einsortierbar ("Save selection to playlist…", "Move to playlist…",
  dedupliziert) und aussortierbar ("Remove from playlist"); Batch-Dedup
  verhindert Doppelt-Laden bei gemeinsamer Auswahl von Playlist + eigener
  Dateien. Tests: `tests/test_playlist.py` (move_many) +
  `tests/test_queue_playback_behavior.py` (Gruppen-Play, Verschieben,
  Ein-/Aussortieren, loses Material) — Gesamtlauf **432 passed, 12 skipped**.
- **Web-Player (web-casu `/web/` + Pure Web) tragen dieselbe Gruppen-Semantik**
  (implementiert + getestet): Gruppen bleiben sichtbar (auf-/zuklappbar),
  Gruppen-Tools im Header (▶/↑/↓/×) + Kontextmenü, Mehrfachauswahl Block-Move,
  "Save selection to playlist…" (rein), "Remove from playlist" (raus),
  Re-Add-Dedup. Geprüft: Node-Unit-Harness ALL PASS (17 + 12 Checks) +
  Playwright-Smoke `tools/smoke_web_playlist.py` (mehrfach grün).
  `MPCASU-PURE-WEB-3.0.0.zip` neu erzeugt (SHA `6d6d7bf8…`).
- MIME-Assoziation `.casu` via `packaging/casu-codec-mime.xml` (postinst:
  update-mime-database + update-desktop-database), im DEB verifiziert.
- **Nächste Version: v5.0.0** (v4.x übersprungen).

## Playlist-Gruppen-Semantik (Kurzform)

1. Playlist wählen → EINE Gruppenzeile "[Playlist] Name" (auf-/zuklappbar).
2. Spielen → Gruppe bleibt stehen; Einträge laufen in Reihenfolge (Next/Prev).
3. ↑/↓ bzw. Kontextmenü verschiebt Gruppen und Mehrfachauswahlen (Block).
4. "Save selection to playlist…"/"Move to playlist…" sortiert ein (rein);
   "Remove from playlist" sortiert Kinder aus (raus).
5. Lose Dateien/URLs (ohne Playlist) werden überall in der Queue mitgespielt.
6. Playlist + eigene Dateien zusammen gewählt → kein Doppelt-Laden (Batch-Dedup).

Details: siehe `ALL_RELEASE_V5/README.md` → "Playlist-Gruppen-Semantik".

## Build (Linux → DEBs)

```sh
bash packaging/build_debs.sh    # baut 4 DEBs nach dist/ (ACHTUNG: leert dist/!)
```

Pakete: `casu-codec`, `casu-converter`, `mpcasu`, `web-casu` (Version 3.0.0;
bei v5.0: 5.0.0). Hinweis: `build_debs.sh` löscht `dist/` — nach dem Bauen das
PURE-WEB-ZIP aus `pure-web-release/` neu erzeugen
(`dist/MPCASU-PURE-WEB-3.0.0.zip`, 18 Dateien, ohne `.htaccess`) und
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