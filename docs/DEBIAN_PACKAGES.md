<!-- SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu -->
# Debian packages

Build the three coordinated `1.0.0-rc8` packages on Debian/Ubuntu:

```bash
./packaging/build_debs.sh
sha256sum -c dist/SHA256SUMS
```

The result is:

- `casu-codec_1.0.0-rc8_all.deb` — STRICT/CASUNAT2 code, CLI and docs;
- `casu-converter_1.0.0-rc8_all.deb` — Tk converter interface;
- `mpcasu_1.0.0-rc8_all.deb` — MPCASU libVLC/native player interface.

The packages deliberately depend on distribution FFmpeg, NumPy and Tk rather
than bundling third-party decoders. The MPCASU package explicitly requires
`libvlc5`, `vlc-plugin-base`, `vlc-plugin-video-output` and `libpulse0` so an
installed shared library is not mistaken for a usable codec/output runtime.
It also requires `libass9` for the native ASS/SSA RGBA subtitle renderer.
Ordinary formats use that installed libVLC module set; CASUNAT2 uses its
independent key-state/tile/PCM decoder. Stable 1.0 remains blocked until every
gate in `RELEASE_GATE_STATUS.json` passes.
