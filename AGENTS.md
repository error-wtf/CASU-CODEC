# AGENTS.md — Repo-Status und Arbeitsregeln (VERBINDLICH)

## Stand: Release v7.8.0 (aktueller `main`)

Der aktuelle `main` ist die **Release-Version 7.8.0**. Das Repository ist die
kanonische Referenz für Linux, Windows, Android, iOS/macOS und Web.
Der Player-only Ableger lebt in `error-wtf/Casu-Player` und ist für die
geteilten Module per Test an `main` gepinnt
(`tests/test_shared_module_identity.py`).

## v7.8.0 Highlights

- Vollständige Test-Suite grün (647 + 31 Tests, 0 Failures) — inklusive
  ffmpeg `-fps_mode`-Kompatibilität (ffmpeg 5.1+ / 9.x) und
  Shared-Module-Identitäts-Pins zwischen beiden Repos.
- CASUNAT2-Replay-Cache: sequentielle Wiedergabe ~10× schneller
  (kein Key-State-Rebuild pro Frame).
- Video-Responsiveness über alle Plattformen: Android TV/Landscape-Layout
  mit Overlay-Transport (FireTV), Aspect-Fit-TextureView, Immersive
  Fullscreen, Web `100dvh`/`:fullscreen`, iOS aspectRatio + Fullscreen-Cover,
  Windows-Fullscreen-Exit restauriert Bar-Zustände.
- Security: `catalog.php` SSRF-Härtung; pure-web-release index.html/styles.css
  synchronisiert (Deploy war funktionsunfähig).
- Dokumentation: `CHANGELOG.md` (Keep a Changelog) ist ab 7.8.0 die
  verbindliche Änderungshistorie; `RELEASE_GATE_STATUS.json` bleibt der
  autoritative Gate-Status. Ältere RELEASE_NOTES/Deep-Audits sind
  historische Snapshots.

## Arbeitsregeln

- **Beide Repos synchron pflegen**: 35 Module sind byte-identisch zwischen
  `CASU-CODEC` und `Casu-Player` — der Identitätstest schlägt fehl, wenn eine
  Seite driftet. Web-Assets existieren in mehreren Kopien (web/,
  pure-web-release/, win-release/…): Änderungen immer in allen Kopien oder
  per Sync-Script.
- Android-Builds: **JDK 21** verwenden (JDK 25 bricht die Kotlin-Toolchain).
  `ANDROID_HOME` setzen, `./gradlew assembleDebug`.
- Der **Windows-Port** (C++20/Qt6/MinGW) läuft unter `win-release/` und bleibt
  separat. Größere Linux-Arbeiten erfolgen in einer Arbeitskopie und werden
  als Release in `main` eingespielt.
- Container-Format bleibt `CASU_FORMAT_VERSION 3.0.0` — Produkt- und
  Formatversion sind entkoppelt.

## Online-Release

- GitHub-Repo: `error-wtf/CASU-CODEC` (Branch `main`)
- Release-Ablauf: Doku → Tag → `SHA256SUMS` regenerieren → GitHub-Release
  (Reihenfolge in RELEASE_POLICY.md).
- Git-Zugriff: Credentials ausschließlich über `gh` CLI oder Umgebungsvariablen
  — keine Token-Pfade in Repo-Dateien committen.
