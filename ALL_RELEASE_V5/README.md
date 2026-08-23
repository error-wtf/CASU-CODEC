# ALL_RELEASE_V5 — Release-Planung für alle Ziel-Betriebssysteme

Diese Sammlung ist die **zentrale Release-Struktur für zukünftige Versionen**.
Jeder Unterordner gehört zu einem Betriebssystem, für das wir je eine Version
bauen wollen. In jedem Unterordner liegen die **äquivalenten Hilfsdateien**
(dieselbe Grundstruktur wie beim Windows-Port, angepasst an das jeweilige OS).

## Versionspolitik (VERBINDLICH, ab 2026-08-19)

- Die nächste Release-Version ist **v5.0.0**.
- **v4.x wird bewusst übersprungen** (kein v4.0.0, keine v4.x-Reihe).
- Die aktuelle veröffentlichte Version bleibt **v3.0.0** (Linux + Windows,
  siehe GitHub-Release `v3.0.0`); der nächste Release-Versionssprung ist
  direkt **v3.0.0 → v5.0.0**.
- Gründe für den Sprung: v4.x ist intern für die v5-Planung reserviert
  (Konzepte/Design-Dokus, die niemals als v4 veröffentlicht werden).
- Überall, wo heute "3.0.0" steht (setup.nsi, CMake-Paketversion, DEB-Version,
  Doku), wird bei der v5.0.0-Arbeit auf "5.0.0" angehoben.

## Ordnerstruktur

| Unterordner | OS | Zielartefakt | Status |
|-------------|----|--------------|--------|
| `Windows/` | Windows x86_64 | `MPCASU-Setup-5.0.0.exe`, `MPCASU-Windows-x86_64.zip` | **v5.0.0 VERÖFFENTLICHT** (23.08.): §0b komplett, Gate 14/14 PASS, ctest 21/21 — https://github.com/error-wtf/CASU-CODEC/releases/tag/v5.0.0 |
| `Linux/` | Linux (Debian/Ubuntu, x86_64) | `.deb`-Pakete (casu-codec, casu-converter, mpcasu, web-casu) + Pure-Web-ZIP | **v3.0.0 fertig**, v5.0 geplant |
| `Mac-OS/` | macOS (arm64 + x86_64) | `.dmg` (geplant) | geplant, noch nicht gebaut |
| `Android/` | Android (arm64-v8a, armeabi-v7a, x86_64) | `.apk` / `.aab` (geplant) | geplant, noch nicht gebaut |

## Grundstruktur der Hilfsdateien (je OS äquivalent)

Die Windows-Version (`win-release/`) ist die Vorlage. In JEDEM Unterordner
liegen äquivalente Dateien (gleiche Namen, OS-spezifischer Inhalt):

| Datei | Zweck |
|-------|-------|
| `README.md` | Übersicht, Zielarchitektur, Build, Deliverable, Installation, Status |
| `PREREQUISITES.md` | Toolchain + Beschaffung vor dem Bauen (SCHRITT 0) |
| `RUN_CHECKLIST.md` | Arbeits-Loop + harte Gates (kein falscher PASS) |
| `SAFE-GUARD.md` | Backups + Regressionstests (nichts zerstören) |
| `PORT_STATUS.md` | aktueller Stand / nächster Schritt |
| `FEATURE_MATRIX.md` | Feature-Parität zum Linux-Referenzplayer |
| `INSTALL_AND_CODEC.md` | Installation + Dateityp-/Codec-Verhalten je OS |
| `START_HIER.md` | Start-Prompt für die nächste Session |

## HARTE REGEL (VERBINDLICH, Nutzer-Direktive ab 2026-08-22)

**VOLLSTÄNDIGE PARITÄT ZUERST.** Keine Android-/macOS-Arbeit, kein
v5.0.0-GitHub-Release und keine neuen Features, BEVOR die §0b-Tierliste aus
`HANDOVER.md` vollständig abgearbeitet ist und Linux↔Windows deckungsgleich
sind (Nachweis: ctest grün + neue Paritätstests + Audit-Checkliste je Punkt).
Reihenfolge: CASUNAT2 (erledigt ✅) → Strict-Analyse → EPG → Tier 2 Items
4–10. Erst danach: Release v5.0.0 → Android → macOS.

## Regeln

- `win-release/` bleibt die kanonische Windows-Arbeitskopie; `ALL_RELEASE_V5/Windows/`
  spiegelt deren Hilfsdateien als Release-Planung (bei Abweichung gilt `win-release/`).
- Keine Secrets in diesem oder irgendeinem Unterordner (Token liegen NUR in
  `/home/error/gittoken.env`, `.gitignore` schließt sie aus).
- Jede neue Version: erst `SAFE-GUARD`-Backup, dann Tests, dann Pakete, dann
  Release-Update (Workflow siehe `Windows/SAFE-GUARD.md`).

## Playlist-Gruppen-Semantik (VERBINDLICH für alle Ziel-OS)

Seit dem v3.0.0-Nachfolger gilt in **jedem** Player (Linux + Windows +
**web-casu** + **Pure Web**) die nicht-destruktive Queue-Semantik — Playlists
werden beim Abspielen **nie aufgelöst**:

1. **Gruppen bleiben sichtbar:** Eine Playlist erscheint als EINE Zeile
   ("[Playlist] Name") im Queue. Sie wird beim Spielen nicht in ihre Einträge
   aufgelöst, sondern bleibt als verschiebbare Gruppe stehen (zusammen-
  /aufklappbar).
2. **Logische Wiedergabe-Sequenz:** Abgespielt wird die flache Sequenz der
   Einträge — Playlist-Gruppen laufen in ihre Einträge auf, lose Dateien und
   URLs (die keiner Playlist angehören) stehen dazwischen und werden ebenfalls
   komplett durchgespielt (Next/Previous, Shuffle, Repeat).
3. **Verschieben:** Ganze Gruppen UND Mehrfachauswahlen (Strg wahllos, Shift
   in Reihe) sind per ↑/↓-Button und Kontextmenü ("Move up/down") frei
   verschiebbar; eine Selektion bewegt sich als Block.
8. **Dauerhafte Markierung:** Die (Mehrfach-)Auswahl bleibt nach dem
   Verschieben UND nach dem Entfernen erhalten — man kann also wiederholt
   verschieben/entfernen, ohne neu zu markieren; überlebende Zeilen einer
   Entfernung bleiben markiert. Erst eine leere Auswahl bzw. **Esc** löscht
   die Markierung.
4. **Einsortieren ("rein"):** Auswahl (Dateien, URLs, ganze Gruppen — diese
   werden in ihre Einträge expandiert) kann per "Save selection to
   playlist…"/"Move to playlist…" in eine Playlist einsortiert werden
   (dedupliziert, bestehende Reihenfolge bleibt).
5. **Aussortieren ("raus"):** Kinder (Einträge) können per "Remove from
   playlist" aus ihrer Gruppe entfernt werden; die Gruppe bleibt bestehen.
6. **Loses Material:** Dateien/URLs ohne Playlist sind ein-/aussortierbar und
   werden in jeder Position der Queue abgespielt (vorne, zwischen Gruppen,
   hinten).
7. **Kein Doppelt-Laden:** Wird eine Playlist zusammen mit ihren eigenen
   Dateien gewählt, kommen deren Pfade nur einmal vor (Batch-Dedup). Eine
   bereits geladene Playlist wird bei erneutem Wählen übersprungen.

Diese Semantik ist in `FEATURE_MATRIX.md` je OS als Paritätsmerkmal
dokumentiert und durch Tests abgedeckt (Linux `tests/test_queue_playback_behavior.py`,
Windows `win-release/tests/casu_playlist_test.cpp`, Web `tools/smoke_web_playlist.py`).