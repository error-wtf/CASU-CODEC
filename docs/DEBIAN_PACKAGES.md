<!-- SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu -->
# Debian packages

Build the four coordinated `1.0.0-rc8` packages on Debian/Ubuntu:

```bash
./packaging/build_debs.sh
(cd dist && sha256sum -c SHA256SUMS)
```

The result is:

- `casu-codec_1.0.0-rc8_all.deb` — STRICT/CASUNAT2 code, CLI and docs;
- `casu-converter_1.0.0-rc8_all.deb` — full Tk audio/video/CASU batch converter;
- `mpcasu_1.0.0-rc8_all.deb` — MPCASU libVLC/native player interface;
- `mpcasu-web_1.0.0-rc8_all.deb` — localhost-only browser player launcher.

The web launcher owns the executable/server while its exact-version
`casu-codec` dependency owns the shared `web/` assets. This keeps the desktop,
codec and web packages on one verified asset version; rebuilding either change
therefore rebuilds all four packages and `SHA256SUMS`.

The packages deliberately depend on distribution FFmpeg, NumPy, PyAV and Tk rather
than bundling third-party decoders. The MPCASU package explicitly requires
`libvlc5`, `vlc-plugin-base`, `vlc-plugin-video-output` and `libpulse0` so an
installed shared library is not mistaken for a usable codec/output runtime.
It also requires `libass9` for the native ASS/SSA RGBA subtitle renderer.
Ordinary formats use that installed libVLC module set; CASUNAT2 uses its
independent key-state/tile/PCM decoder. Package launchers explicitly use
`/usr/bin/python3`, matching these declared distribution dependencies even when
a Conda or virtual-environment Python appears earlier in `PATH`. Stable 1.0 remains blocked until every
gate in `RELEASE_GATE_STATUS.json` passes.
