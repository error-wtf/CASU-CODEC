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
| `Windows/` | Windows x86_64 | `MPCASU-Setup-5.0.0.exe`, `MPCASU-Windows-x86_64.zip` | **v3.0.0 fertig** (14/14 Gate PASS), v5.0 geplant |
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

## Regeln

- `win-release/` bleibt die kanonische Windows-Arbeitskopie; `ALL_RELEASE_V5/Windows/`
  spiegelt deren Hilfsdateien als Release-Planung (bei Abweichung gilt `win-release/`).
- Keine Secrets in diesem oder irgendeinem Unterordner (Token liegen NUR in
  `/home/error/gittoken.env`, `.gitignore` schließt sie aus).
- Jede neue Version: erst `SAFE-GUARD`-Backup, dann Tests, dann Pakete, dann
  Release-Update (Workflow siehe `Windows/SAFE-GUARD.md`).