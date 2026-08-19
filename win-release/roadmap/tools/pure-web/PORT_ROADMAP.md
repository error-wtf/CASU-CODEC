# Pure Web — Windows Integration Roadmap (Tool: TOOL-PURE-WEB)

Pure Web is **frozen** (`MPCASU-PURE-WEB-2.0.0.zip`, SHA256
`64143894217b34d23571535848210c0ad871a19a5d8730d7782234966fa2e754`).
No C++ rewrite. Windows scope = correct, byte-identical integration into the
package + a start mechanism. Status "PORTED" = integrated & verified, not
rewritten (REQ-PURE-001, REQ-PORT-002).

Reference: `pure-web-release/` (frozen), released zip in `dist/`.

## WP-PURE-001 Verify frozen reference + SHA256
- Confirm zip/bytes unchanged; record SHA256. STATUS: VERIFIED (2026-08-18).
  Release `MPCASU-PURE-WEB-3.0.0.zip` SHA256
  `b71b5d0b3ecde8dd7d2098665f94c4381abd6815a9727019adcc009f68ebf8de`;
  `pure-web-release/` == Zip + `.htaccess` (diff -rq leer).

## WP-PURE-002 Copy to win-release/web/pure byte-identical + SHA256 compare
- Copy must match the published release exactly (no edits; packaging-only
  needs are documented, not applied silently). STATUS: VERIFIED (2026-08-18).
  `cp -a pure-web-release/. web/pure/`; `diff -rq` leer; per-file-SHA256 der
  Kopie == Release-Zip-Manifest.

## WP-PURE-003 Start documentation (Windows)
- How to open (double-click index.html or via a small launcher/exe that
  serves it over loopback for full YouTube/CORS). Document both.
  STATUS: VERIFIED (README_WINDOWS.md Abschnitt "Pure Web").

## WP-PURE-004 Windows browser test
- Open in Wine browser (and real browser on Windows): playlist preloads,
  YouTube via IFrame API, HLS, no console errors. STATUS: NOT_STARTED.
  (Benötigt Browser unter Wine; kein Windows-Browser verfügbar.)

## WP-PURE-005 Packaging integration (into Windows zip)
- web/pure/ present in package; README_WINDOWS explains usage.
  STATUS: VERIFIED (2026-08-18) — `install(DIRECTORY web/pure/ …)` in
  packaging.cmake; Zip-Inhalt `MPCASU-Windows-x86_64/web/pure/*` byte-identisch
  mit dem Frozen-Release.

## Acceptance
- SHA256 of shipped web/pure == published release. Browser test PASS.
- Never modify the frozen files; any needed change → documented + excluded,
  never silent.
