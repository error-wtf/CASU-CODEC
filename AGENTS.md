# AGENTS.md — Repo-Status und Arbeitsregeln (VERBINDLICH)

## Stand: FINALE Release-Version (v2.0.0) — Repo GEFROREN / READ ONLY

Dieses Repository ist ab sofort **eingefroren (READ ONLY)**. Der aktuelle
`main` ist die finale Linux-Release-Version inkl. `Pure Web Release 2.0.0`.
Es gilt:

- **Keine Änderungen** an bestehendem Code/Inhalt des Repos.
- Alles Bestehende ist die **frozen reference implementation** (Executable
  Specification / Test-Oracle / Designreferenz) für den Windows-Port.
- Bestehender Code darf **ausschließlich gelesen/analysiert/ausgeführt**
  werden — nie verändert.
- `web-casu`, `pure-web-release`, `mpcasu_qt`, `mpcasu_backend.py`, `casu/`,
  `tests/`, `docs/`, `packaging/`, `dist/` usw. werden **nicht mehr angefasst**.

## Einzige erlaubte Ausnahmen

1. **Finale `.deb`-Builds** über `packaging/build_debs.sh` — nur auf
   ausdrückliche Anfrage, nur um Release-Artefakte zu regenerieren.
2. **Arbeit ausschließlich in:**
   - `/home/error/Codec-Casu/win-release`   ← Windows-Port (Schreibgebiet)
   - `/home/error/Codec-Casu/pure-web-release` ← nur Lesen; veröffentlichtes ZIP ist FROZEN

Die gesamte zukünftige Entwicklung ist der **Windows-Port (C++20/Qt6/MinGW)**
unter `win-release/`. Alles andere im Repo bleibt unangetastet und ist reine
Referenz.

## Online-Release

- GitHub-Repo: `error-wtf/CASU-CODEC` (Branch `main`)
- GitHub-Release: `v2.0.0` „MPCASU Final 2.0.0 — Linux Release"
  - Assets: `.deb`-Pakete + `SHA256SUMS` + `MPCASU-PURE-WEB-2.0.0.zip` (Pure Web)
- Release-Artefakte spiegeln den eingefrorenen Stand.
- Git-Zugriff: Token in `/home/error/gittoken.env` (nie im Klartext loggen).
