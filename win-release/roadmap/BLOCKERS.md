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
