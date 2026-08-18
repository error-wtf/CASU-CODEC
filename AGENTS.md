# AGENTS.md — Repo-Status und Arbeitsregeln (VERBINDLICH)

## Stand: Release v3.0.0 — Linux Release (aktueller `main`)

Der aktuelle `main` ist die **Linux-Release-Version 3.0.0** inkl.
`Pure Web Release 3.0.0`. Das Repository ist die kanonische Linux-Referenz.

## 3.0.0 — „Playlist Everywhere"

3.0.0 bringt native, formatbewusste Playlist-Unterstützung in allen Playern
(Qt-Desktop, `web-casu`, Pure Web) plus Stabilitäts- und UX-Fixes:

- **Playlist-Formate:** M3U/M3U8, PLS, WPL, XSPF, JSPF, ASX/WMX/WVX, RMP/RAM,
  MPCASU JSON — relative + URL-kodierte Pfade, `file://`, Eintragstitel.
- **Absturz/Hänger behoben:** Visualizer-Repaint-Schleife gedrosselt
  (kein CPU-Pegel im Leerlauf), in-process Dateidialog statt Portal-Dialog.
- **Kein Doppelt-Laden** beim gemeinsamen Wählen einer Playlist + ihrer Medien.
- **Playlist spielt ab Track 1** und schaltet in Reihenfolge durch die Titel
  der Playlist weiter (Next/Previous).
- **Multi-Select** (Shift/Ctrl) in der Queue; formatbewusster Save-Dialog.
- **Wayland & X11:** Launcher wählt die Plattform je Session.

## Arbeitsregeln

- Der **Windows-Port** (C++20/Qt6/MinGW) läuft unter `win-release/` und bleibt
  separat.
- Größere Entwicklungsarbeiten am Linux-Code erfolgen in einer Arbeitskopie
  (`linux-release/`, gitignored) und werden als Release in `main` eingespielt;
  sie berühren `win-release/` nicht.

## Online-Release

- GitHub-Repo: `error-wtf/CASU-CODEC` (Branch `main`)
- GitHub-Release: `v3.0.0` „CASU / MPCASU 3.0.0 — Playlist Everywhere (Linux Release)"
  - Assets: `.deb`-Pakete + `SHA256SUMS` + `MPCASU-PURE-WEB-3.0.0.zip` (Pure Web)
- Git-Zugriff: Token in `/home/error/gittoken.env` (nie im Klartext loggen).
