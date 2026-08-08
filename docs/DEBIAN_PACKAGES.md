<!-- SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu -->
# Debian packages

Build the three independent version-1.0 packages on Debian/Ubuntu:

```bash
./packaging/build_debs.sh
sha256sum -c dist/SHA256SUMS
```

The result is:

- `casu-codec_1.0.0_all.deb` — schema, analyzer, converter CLI and docs;
- `casu-converter_1.0.0_all.deb` — Tk converter interface;
- `mpcasu_1.0.0_all.deb` — MPCASU player interface.

The packages deliberately depend on distribution FFmpeg, NumPy and Tk rather
than bundling third-party decoders. CASU remains a sidecar/state layer and
legacy media remains the canonical full-fidelity source.
