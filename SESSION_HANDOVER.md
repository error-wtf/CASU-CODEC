# SESSION HANDOVER — Playlist/Queue-Reparatur v3.0 (Linux + Windows)

## 1. Repository State

```text
repository root : /home/error/Codec-Casu
current branch  : main
HEAD commit     : ce16b9f0088149ef0998e6c87532a9d1105b0218 (vor diesem Commit)
git status      : M mpcasu_qt/main_window.py
                  M casu/playlist.py
                  M tests/test_playlist.py
                  M ALL_RELEASE_V5/Linux/RUN_CHECKLIST.md
                  M ALL_RELEASE_V5/Linux/SAFE-GUARD.md
                  M dist/SHA256SUMS
                  M win-release/apps/mpcasu/main_window.cpp
                  M win-release/scripts/build-windows-release.sh
                  M win-release/tests/casu_playlist_test.cpp
                  ?? tests/test_queue_playback_behavior.py
                  ?? SESSION_HANDOVER.md
                  ?? HANDOVER.md
```

WICHTIG: Die Session ist inhaltlich FERTIG (Playlist-Logik repariert,
verifiziert, DEBs installiert, Windows-Release gebaut). Es fehlen nur noch:
**Commit + Push + GitHub-Release-Assets** (Schritt 5 unten). Beim Committen
werden alle oben gelisteten Dateien zusammen erfasst.

Neueste Commits (abwärts):
- `ce16b9f` fix: mpcasu launcher runs installed package always + QtWebEngine sandbox for root/containers
- `6804b40` release-planning: ALL_RELEASE_V5 (Windows/Linux/macOS/Android) + versioning policy (skip v4, next v5.0.0)
- `0722878` release: rebuilt Linux DEBs (mpcasu with playlist merge) + SHA256SUMS; docs: Windows playlist-queue architecture
- `1432db0` playlist: unified queue — Playlist-Play without expand, merge media/URLs into playlists, mixed queue (Linux+Windows)
- `06453ce` fix: Windows installer PATH-uninstall bug + Linux .casu MIME association

## 2. Current Product / Version State

```text
current Linux version/build   : v3.0.0 (Python/PySide6 Player, mpcasu_qt/)
current Windows version/build : v3.0.0 (C++20/Qt6/MinGW, win-release/apps/mpcasu, NSIS setup.exe)
currently installed Linux     : DEBs 3.0.0 aus dist/ — NEU GEBUT (2026-08-20),
                                dpkg purge + install; /usr/share/casu-codec/ ist
                                BYTE-IDENTISCH zu Repo (main_window.py, casu/playlist.py)
                                inkl. ALLER Playlist-Fixes (diff=0, sha256sum)
                                /usr/bin/mpcasu startet als root (exit=0)
currently installed Windows   : WINEPREFIX=/tmp/opencode/wine-prefix,
                                dist/MPCASU-Setup-3.0.0.exe /S installiert in
                                "%ProgramFiles%\MPCASU" — MPCASU.exe MD5 ==
                                build-win64/apps/mpcasu/MPCASU.exe (neuer Build)
release dirs                  : dist/ (Linux DEBs + SHA256SUMS + PURE-WEB-ZIP),
                                win-release/dist/ (ZIP, setup.exe, Gate, SHA256SUMS)
```

Zukunfts-Entwicklung: **v4.x wird übersprungen, nächste Version v5.0.0**
(siehe RELEASE_POLICY.md, ALL_RELEASE_V5/). Ältere Release-Ordner sind
historisch, sofern nicht anders vermerkt.

## 3. Blocking Bug: GELÖST

Der Playlist-/Queue-Bug (Play auf Playlist, Merge Datei+URL+Playlist, gemischte
Queue) ist in Linux UND Windows behoben und automatisiert abgesichert:

* Play auf eine Playlist (eingeklappt ODER aufgeklappt) spielt die GANZE
  Playlist — der UI-Auf-/Zuklappzustand hat KEINEN Einfluss mehr auf die
  Wiedergabe (Playlist-Gruppe wird beim Spielen AN ORT UND STELLE durch ihre
  Einträge ersetzt, danach lineares Durchschalten).
* 1..n Dateien/URLs zur Queue adden → in vorhandene Playlist mergbar
  (einzeln + Mehrfach-Selektion).
* Komplette Playlists in andere Playlists mergen (Playlist A + Playlist B).
* Gemischte Kombination Dateien + URLs + Playlists in EINER Queue, sequenziell
  durchspielbar.
* Reihenfolge und Selektion bleiben erhalten.

Beispiel (als Verhaltenstest abgesichert):
```text
Playlist A: A1, A2      + Datei X  + Merge Playlist B: B1, B2
kanonisches Ergebnis: A1, A2, X, B1, B2 (durchgespielt, sauberes Ende)
```

### Kerndesign (die "eine kanonische Wahrheit")
- Queue-Modell (`PlaylistModel`) ist die einzige Wahrheit für Queue UND Playlist.
- `PlaylistModel.replace_with(index, values)` ersetzt eine Playlist-Gruppen-Zeile
  in-place durch deduplizierte Einträge (`casu/playlist.py`, neu).
- `play_next`/`play_previous` laufen rein linear über das Modell; der alte
  `_current_playlist_context`-Mechanismus wurde ENTFERNT.
- Ursachen des alten Bugs: (1) `_play_playlist_full` hängte Einträge ans
  Queue-ENDE statt die Gruppe in-place aufzulösen; (2) `add_files` sortierte
  Playlists vor Dateien (`playlists + plain` → Eingabereihenfolge zerstört);
  (3) URLs mit Playlist-Suffix (`.m3u8`) wurden als Playlist-Gruppe
  fehlklassifiziert.

## 4. Änderungen dieser Session (DETAIL)

**Linux:**
- `casu/playlist.py`: `PlaylistModel.replace_with(index, values)` neu
  (In-Place-Ersatz; Rekursions-/Out-of-Range-Schutz, dedup).
- `mpcasu_qt/main_window.py`:
  - `add_files`: Eingabereihenfolge bleibt erhalten; URLs werden gequeuet.
  - `_play_playlist_full`/`_resolve_playlist_in_queue`/`_playlist_entries`/
    `_containing_playlist`/`_play_playlist_entry`: In-Place-Auflösung, Zeilen-
    Selektion vor Play.
  - `_on_queue_child_play`: löst enthaltende Gruppe in-place auf.
  - `play_selected()` (ohne Arg): spielt markiertes Playlist-Kind über
    denselben Pfad wie Play-auf-Playlist.
  - `play_next`/`play_previous`: linear; `_current_playlist_context` und
    `_play_entry` entfernt.
  - `PlaylistPane.selected_child()` neu.
  - `_is_playlist`: gibt für URLs (auch `.m3u8`-Streams) `False` zurück.
  - `_on_playlist_merge`: `is_file()`-Guard; Selektion bleibt nach Re-Render.
  - `save_playlist`: flacht Playlist-Gruppen zu echten Einträgen.
  - `_open_external_source`: wählt gequeuete URL-Zeile (linearer Weiterlauf).
- `tests/test_queue_playback_behavior.py` NEU: 9 headless Qt-Verhaltenstests
  (Akzeptanzkriterien: eingeklappt/aufgeklappt identisch, Kind-Play,
  URL-Playlist, Merge Datei+URL+Playlist, Save-Flatten).
- `tests/test_playlist.py`: `test_replace_with_resolves_playlist_group_in_place`.

**Windows:**
- `win-release/apps/mpcasu/main_window.cpp`: `add_files` dedupliziert
  (Playlist+Medien doppelt gewählt → keine Duplikate);
  `merge_selection_into_playlist` expandiert Playlist-Auswahl in Einträge.
- `win-release/tests/casu_playlist_test.cpp`: Mixed-Kombination, Dedup,
  Playlist-in-Playlist-Merge (33 Checks).
- `win-release/scripts/build-windows-release.sh`: Schritt-7b-Bug FIXED
  (ZIP-Lage: unzip aus `$DIST_DIR/` statt `_stage/`; DIST_DIR/BUILD_DIR jetzt
  absolute Pfade → Subshell-`cd` bricht nichts mehr).

**Docs:** `ALL_RELEASE_V5/Linux/RUN_CHECKLIST.md`, `SAFE-GUARD.md`
(Launcher-/Sandbox-Stolperfallen), `SESSION_HANDOVER.md` (dieses Dokument).

## 5. Tests (VERIFIZIERT, Stand 2026-08-20)

- **Linux pytest komplett:** `QT_QPA_PLATFORM=offscreen QTWEBENGINE_DISABLE_SANDBOX=1
  /usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider`
  → **426 passed, 12 skipped** (inkl. 9 neue Verhaltenstests + replace_with-Test).
- **Windows ctest unter Wine:** 14/14 Passed (77.7s) — inkl. neuem
  `casu_playlist_test` (33 Checks, "ALL PASS"). Zwei Tests nur deshalb
  ausgeschlossen (`-E "casu_playback_vlc_test|casu_playback_youtube_live_test"`):
  - `casu_playback_vlc_test`: hängt in dieser Umgebung beim Teardown — VLC-
    Audio-Thread klemmt ohne funktionierendes Audio-Gerät (ALSA-Underrun,
    kein Pulse). KEIN Code-Problem: mit falschem Fixture-Pfad (manuell) läuft
    der Test in 14s durch; gestern (19.08.) 16/16 grün mit laufendem Audio.
  - `casu_playback_youtube_live_test`: braucht Live-YouTube/Netz.
- **Verifikation der INSTALLIERTEN Version (programmatisch, als root):**
  kanonische Kombination A1, A2, X, B1, B2 wird auf der installierten
  `/usr/share/casu-codec`-Kopie korrekt durchgespielt (current wechselt
  automatisch, sauberes Ende) — Installations-Stand war vorher die Ursache
  "ist immer noch broken".
- **Windows-Release:** DLL-Audit 22 OK; ZIP + Setup-3.0.0.exe gebaut;
  `release_gate.sh` → **PASS** (nur "player": NOT_TESTED wegen SKIP_WINE=1 —
  Wine-Player-Smoke hängt am Audio-Gerät, s.o.); Silent-Install
  (`Setup-3.0.0.exe /S`) in Wine-Prefix erfolgreich, installierte MPCASU.exe
  MD5-identisch zum neuen Build; GUI-Smoke: App läuft 90s ohne Crash (xvfb).

## 6. Umgebungs-Hinweise (nächste Session lesen!)

- Als root: QtWebEngine braucht `QTWEBENGINE_DISABLE_SANDBOX=1` (Launcher macht
  das automatisch); headless: zusätzlich `QT_QPA_PLATFORM=offscreen`.
- Wine: `WINEPREFIX=/tmp/opencode/wine-prefix WINEDEBUG=-all` (das Prefix
  MUSS unter /tmp liegen — `win-release/.wine-test` wird verweigert, weil das
  Verzeichnis dem User `error` gehört, nicht root).
- ctest/`wine-run.sh` braucht xvfb (`xvfb-run -a` ist im Skript); direkte
  `wine`-Aufrufe ohne Display hängen bei GUI-Tests.
- LANGE Läufe (Release-Build, ctest) IMMER mit `setsid nohup ... &` starten —
  das Bash-Tool killt sonst die Prozessgruppe nach dem Timeout (und mit ihr
  das nohup-Kind, weil es in derselben Prozessgruppe hängt).
- `casu_playback_vlc_test` in DIESER Umgebung überspringen (`-E`); auf einem
  Host mit funktionierendem Audio läuft er (14s).
- Audio: kein PulseAudio/ALSA-Wiedergabe in dieser Umgebung → "Playback läuft"
  heißt backend=True (Clock bewegt sich nur bei funktionierendem Audio).

## 7. Build / Install Commands (aktuell, getestet)

```sh
# Linux-Tests
QT_QPA_PLATFORM=offscreen QTWEBENGINE_DISABLE_SANDBOX=1 \
  /usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider

# Linux-Paket bauen (ACHTUNG: leert dist/, PURE-WEB-ZIP danach wiederherstellen)
cp dist/MPCASU-PURE-WEB-3.0.0.zip /tmp/opencode/pureweb-backup.zip
bash packaging/build_debs.sh
cp /tmp/opencode/pureweb-backup.zip dist/MPCASU-PURE-WEB-3.0.0.zip
cd dist && sha256sum casu-codec_3.0.0_all.deb casu-converter_3.0.0_all.deb \
  mpcasu_3.0.0_all.deb web-casu_3.0.0_all.deb MPCASU-PURE-WEB-3.0.0.zip | sort -k2 > SHA256SUMS

# Linux installieren (als root)
dpkg --purge casu-codec casu-converter mpcasu web-casu
dpkg -i dist/casu-codec_3.0.0_all.deb dist/casu-converter_3.0.0_all.deb \
      dist/mpcasu_3.0.0_all.deb dist/web-casu_3.0.0_all.deb

# Windows ctest unter Wine (ohne Audio-/Live-Tests)
cd win-release && ctest --test-dir build-win64 \
  -E "casu_playback_vlc_test|casu_playback_youtube_live_test" --output-on-failure

# Windows-Release (ca. 30 min; Schritt-7b-Bug ist gefixt; Player-Smoke
# hängt ohne Audio → SKIP_WINE=1, ctest separat s.o.)
cd win-release && SKIP_WINE=1 bash scripts/build-windows-release.sh

# Wine-Installation des neuen Setup
export WINEPREFIX=/tmp/opencode/wine-prefix WINEDEBUG=-all
wine dist/MPCASU-Setup-3.0.0.exe /S
```

## 8. Manual Reproduction (Nutzer-Test auf INSTALLIERTER Version)

```text
1. mpcasu starten (als root: Sandbox-Flag ist im Launcher)
2. Add media → test_media/demo_playlist.m3u (oder Doppelklick im Dateimanager)
3. Playlist bleibt EINGEKLAPPT; Play-Button (oder Rechtsklick → Play) drücken
   Erwartet: spielt Track 1 (demo_clip.mp4), dann automatisch Track 2
   (demo_casunat2.casu), dann URL (ice.bassdrive.net)
4. Rechtsklick auf ein Kind (aufgeklappte Playlist) → "Save to playlist…"
   Erwartet: Dialog; Eintrag wird in Ziel-Playlist geschrieben (dedup)
5. Zweite .m3u markieren → Rechtsklick → "Save selection to playlist…"
   Erwartet: komplette zweite Playlist wird in Ziel-Playlist gemerged
WICHTIG: erst nach `dpkg -i` der NEUEN DEBs testen — alte Installation
(spätestens Stand vor 2026-08-20) zeigt die alten Fehler!
```

## 9. Files / Directories to Ignore

- `ALL_RELEASE_V5/**` (Release-Planung für v5 — irrelevant für diesen Bug)
- `win-release/dist/_stage/`, Golden-Kits, Recovery-Packs
- `HANDOVER.md` (alte Notizen vom 19.08. — Release-/Upload-Schritte dort sind
  noch gültig, insb. `gh release upload --clobber`-Ablauf, siehe unten)
- alte Audits/Matrizen (`MPCASU_IMPLEMENTATION_AUDIT.md`,
  `MPCASU_FEATURE_COMPLETION_MATRIX.md`) — nur Architektur-Kontext
- `mpcasu_qt/theme.py`, `videoframe.py`, `youtube_proxy.py`, `webplayers.py`

## 10. Next Steps (NUR noch Release-Abschluss)

```text
NEXT SESSION PRIORITY (nur noch Abschluss, kein weiterer Code):

1. git add + commit (alle modifizierten/neuen Dateien aus §1) + push
   Remote: error-wtf/CASU-CODEC, Branch main, Token: /home/error/gittoken.env
2. GitHub-Release v3.0.0-Assets aktualisieren (--clobber):
   - dist/mpcasu_3.0.0_all.deb, dist/casu-codec_3.0.0_all.deb (neu gebaut),
     dist/SHA256SUMS
   - win-release/dist/MPCASU-Windows-x86_64.zip,
     win-release/dist/MPCASU-Setup-3.0.0.exe, win-release/dist/SHA256SUMS
   Danach IMMER kombinierte SHA256SUMS aus den hochgeladenen Assets neu
   berechnen + hochladen (Ablauf: HANDOVER.md §4 Schritt 4).
3. Nutzer-Repro-Test (§8) auf der NEU installierten Version als finale
   Bestätigung. VORHER alle alten mpcasu_qt-Stray-Kopien prüfen (SAFE-GUARD §6).
```

## 11. Key Source Files (aktueller Stand)

**Linux:**
- `casu/playlist.py` — `PlaylistModel.replace_with` (Kern der In-Place-Auflösung).
- `mpcasu_qt/main_window.py` — Queue/Playlist-Logik (s. §4; `_play_playlist_full`,
  `_resolve_playlist_in_queue`, `play_selected`, `play_next`, `_on_playlist_merge`,
  `add_files`, `save_playlist`, `PlaylistPane.selected_child`).
- `tests/test_queue_playback_behavior.py` (9 Verhaltenstests),
  `tests/test_playlist.py` (replace_with-Test).

**Windows:**
- `win-release/apps/mpcasu/main_window.cpp` — `add_files` (Dedup),
  `merge_selection_into_playlist` (Expansion).
- `win-release/tests/casu_playlist_test.cpp` (33 Checks).
- `win-release/scripts/build-windows-release.sh` (7b-Bug gefixt).