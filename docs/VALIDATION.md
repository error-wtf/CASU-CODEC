<!-- SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu -->
# CASU validation contract

The repository has three independent validation layers:

1. **Schema validation** checks the manifest structure, timing intervals,
   source metadata and integrity flags without decoding media.
2. **Source verification** resolves the recorded source and compares its
   byte size and SHA-256 digest. A mismatch is a hard failure.
3. **Reference analysis** decodes the owner-authorized MP4 and MP3 fixtures
   with FFmpeg and checks stream metadata plus the generated state hints.

Run the complete local check from the repository root:

```bash
python -m pip install -e .
pytest -q
casu validate test_media/lino_lol_test_pattern.casu --verify-source
casu validate test_media/lino_casu_error.casu --verify-source
```

The expected reference result is **17 passing tests** when FFmpeg and both
fixtures are available. The state map is deliberately advisory: passing these
checks proves parser/converter consistency and source preservation, not visual
power savings or perceptual identity.

The GitHub Actions workflow repeats the same checks on Python 3.10–3.13 with
FFmpeg installed. Any future native CASU decoder must retain the same
full-fidelity fallback and source-timestamp contract.
