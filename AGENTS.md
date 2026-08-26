# AGENTS.md — Repo-Status und Arbeitsregeln (VERBINDLICH)

## Stand: Release v5.0.0 — „Perfect Parity Everywhere" (aktueller `main`)

Der aktuelle `main` ist die **Release-Version 5.0.0** inkl.
`Pure Web Release 3.0.0` (frozen). Das Repository ist die kanonische
Referenz für Linux, Windows und Android.

## v5.0.0 Highlights

- **Alle 3 Plattformen** (Linux Qt/Tk, Windows Qt, Android) mit Feature-Parität:
  Queue-Klick → Now Playing, YouTube-Thumbnails, ★ Favoriten in Queue + Library.
- **Container-Format** bleibt `3.0.0` (CASU_FORMAT_VERSION) — vollständig
  backward-kompatibel.
- Android: StreamRecorder, Provider-Tab, ANR-Fix.

## Arbeitsregeln

- Der **Windows-Port** (C++20/Qt6/MinGW) läuft unter `win-release/` und bleibt
  separat.
- Größere Entwicklungsarbeiten am Linux-Code erfolgen in einer Arbeitskopie
  (`linux-release/`, gitignored) und werden als Release in `main` eingespielt;
  sie berühren `win-release/` nicht.

## Online-Release

- GitHub-Repo: `error-wtf/CASU-CODEC` (Branch `main`)
- GitHub-Release: `v5.0.0` „CASU / MPCASU 5.0.0 — Perfect Parity Everywhere"
  - Assets: DEBs + Setup.exe + Zip + APK + SHA256SUMS
- Git-Zugriff: Token in `/home/error/gittoken.env` (nie im Klartext loggen).
