# AGENTS.md — Repo-Status und Arbeitsregeln (VERBINDLICH)

## Stand: FINALE Linux-Release-Version (v2.0.0) — Repo GEFROREN

Dieses Repository ist ab sofort **eingefroren**. Der aktuelle `main` ist die
finale Linux-Release-Version dieses Projekts. Es gilt:

- **Keine Änderungen** am bestehenden Code/Inhalt des Repos.
- Reiner **Referenz-Code** — das Repo dient nur noch als Vorlage für das,
  was in den beiden Arbeitsordnern entsteht.
- `web-casu`, `mpcasu_qt`, `mpcasu_backend.py`, `casu/`, `tests/`, `docs/`,
  `packaging/`, `dist/` usw. werden **nicht mehr angefasst**.

## Einzige erlaubte Ausnahmen

1. **Finale `.deb`-Builds** über `packaging/build_debs.sh` — nur auf
   ausdrückliche Anfrage, nur um Release-Artefakte zu regenerieren.
2. **Arbeit nur noch in diesen zwei Ordnern:**
   - `/home/error/Codec-Casu/pure-web-release`
   - `/home/error/Codec-Casu/win-release`

Alle zukünftige Entwicklung/Release-Arbeit findet ausschließlich in diesen
beiden Ordnern statt. Alles andere im Repo bleibt unangetastet und ist reine
Referenz.

## Online-Release

- GitHub-Repo: `error-wtf/CASU-CODEC` (Branch `main`)
- GitHub-Release: `v2.0.0` „MPCASU Final 2.0.0 — Linux Release"
- Release-Artefakte (`.deb` + `SHA256SUMS`) spiegeln den eingefrorenen Stand.
- Git-Zugriff: Token in `/home/error/gittoken.env` (nie im Klartext loggen).
