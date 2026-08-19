# BLOCKERS — offene Blocker während des Ports

Eintrag pro Blocker:
```
ID: BLOCKER-001
Blocker: ...
Betroffene WPs: ...
Research performed: ...
Next action: ...
```

Aktuell:
- **BLOCKER-000 (gelöst):** Windows-Runtime-Binaries
  (Qt6-MinGW, libVLC-Windows, ffmpeg/ffprobe/yt-dlp.exe) beschafft und in
  `win-release/third_party/` abgelegt (Lizenzen in THIRD_PARTY_LICENSES/).

- **BLOCKER-001 (gelöst):** MinGW **libzstd** — am 2026-08-18 aus offizieller
  Quelle (zstd-1.5.7.tar.gz, facebook/zstd v1.5.7) mit der Cross-Toolchain
  gebaut (`libzstd.a` statisch) und nach `/usr/x86_64-w64-mingw32/{include,lib}`
  installiert. MP5-`decompress` versucht jetzt zstd zuerst, dann zlib-Fallback
  (Referenz `casu/mp5/reader.py:47`); Writer bleibt zlib (byte-identische
  Golden-Fixtures). WP-CORE-007 VERIFIED (Unit unter Wine grün, 13/13 ctest).

- **BLOCKER-002 (gelöst):** Echter-YouTube-Wine-Test.
  Am 2026-08-18 VERIFIED (HARTES GATE): `casu_playback_youtube_live_test`
  resolvt echtes Video via gebündeltem yt-dlp.exe, proxy-t durch den
  Loopback-Transport und vergleicht Range/206-Bytes byte-exakt gegen den
  Live-CDN (28,5 MB Full-Stream). Voraussetzungen dabei behoben:
  - OpenSSL 3.4.1 für MinGW aus Quelle gebaut (DLLs `libssl-3-x64.dll`/
    `libcrypto-3-x64.dll`) + Qt-TLS-Plugin `plugins/tls/qopensslbackend.dll`
    gebündelt (Qt6Network braucht beides für HTTPS).
  - yt-dlp-Wrapper: `--extractor-args youtube:player_client=android`
    (android_vr-URLs 403; git-Historik-Lektion).
  - YoutubeProxy: Headers vor Body + readyRead-Pump (Streaming-Fix).
  - Betroffene WPs: WP-MPCASU-040..042 (STEP-032), WP-NET-002, WP-MPCASU-041.

- **BLOCKER-003 (offen, kein Design-Blocker):** Pure-Web-Windows-Browser-Test
  (WP-PURE-004) fehlt — kein Browser unter Wine verfügbar. Bündelung selbst
  (STEP-038) ist VERIFIED.

- **BLOCKER-004 (offen, Verifikation):** Installer-Registrierung unter Wine
  prüfen. Der NSIS-Installer (`setup.nsi`) registriert `casu` im System-PATH
  (AddToSystemPath → HKLM Environment) und `.casu`/`.mp5`-Dateitypen. Silent-
  Install/Uninstall sind unter Wine getestet, aber die tatsächliche
  PATH-/Dateityp-Änderung an der echten Windows-Registry ist nur auf echtem
  Windows verifizierbar (Wine-Prefix-Registry ≠ Windows-Registry-Verhalten bei
  HKLM + WM_SETTINGCHANGE). 
  - Next action: auf echtem Windows installieren und prüfen, dass `casu` aus
    jeder Konsole läuft und Doppelklick auf .casu MPCASU öffnet.

- **BLOCKER-005 (geplant, NICHT gebaut):** Media-Foundation/DirectShow-Decoder
  für CASUNAT2. Der Nutzer entschied bei der Installations-Frage → "Auch als
  Media-Codec (MF/DirectShow)". Dies ist ein eigenständiges Groß-Projekt:
  (1) CASUNAT2-Decoder in C++ (portiert aus `mpcasu_native_backend.py`, ~1280
  Zeilen Python; Video-State→RGB + PCM), (2) IMFTransform-COM-Gerüst + CLSID/
  MFT-Registrierung, (3) Verifikation nur auf echtem Windows. Aktuell wird nur
  die Linux-Parität geliefert (PATH + Dateitypen + Startmenü) — das ist die
  korrekte, verifizierte Installation. Architektur + Video-Decode-Modell:
  `WINDOWS_INSTALL_AND_CODEC.md`. Betroffen: neue WPs (noch nicht nummeriert).

- **BLOCKER-006 (gelöst):** QtWebEngine-Codepfad. Web-Provider-Tabs portiert
  (`web_player_tabs.{hpp,cpp}` + `webproviders.{hpp,cpp}`); QtWebEngine existiert
  nur für MSVC → `CASU_HAVE_WEBENGINE`; MinGW baut Stub, MSVC-Build
  (`scripts/build-msvc.bat` + `CMakePresets.json`) aktiviert den echten
  eingebetteten Chromium. QtWebEngine-Codepfad mit Stub-Headers syntaxgeprüft
  (kompiliert sauber). Nativer MSVC-Endbuild auf Windows ausstehend.
