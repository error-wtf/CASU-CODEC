<!-- SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu -->
# CASU/MPCASU 1.0.0

This release contains the first complete compatibility slice:

- CASU manifest schema with source SHA-256, timing/deadline validation and
  full-fidelity fallback;
- MP4/MP3 analysis and atomic conversion through the CLI and Tk converter;
- MPCASU Tk player with CASU sidecar provenance, safe manifest validation,
  seek/pause controls and activity visualization;
- owner-authorized MP4/MP3 fixtures and verified `.casu` manifests;
- Debian packages for codec, converter and player;
- Python 3.10–3.13 CI with FFmpeg-backed tests.

This is a compatibility/state layer, not a replacement for H.264, AAC, MP3 or
FFmpeg. State labels remain advisory and never alter source timestamps.
