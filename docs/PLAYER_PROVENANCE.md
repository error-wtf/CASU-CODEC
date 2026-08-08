<!-- SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4 | SPDX-FileCopyrightText: 2026 Lino Casu -->
# MPCASU player provenance and licensing boundary

MPCASU is an independent player implementation. Its layout and interaction
goals are informed by two public traditions, but this repository does not copy
source code from either project:

- VLC is the VideoLAN media player project. Its source is hosted by VideoLAN
  and is distributed under GPL-family terms with component-specific notices.
  See the [official source repository](https://github.com/videolan/vlc) and
  [VideoLAN legal information](https://www.videolan.org/legal.html).
- The historical Winamp source release used the Winamp Collaborative License,
  which is source-available but includes restrictions on modified distribution.
  It is therefore not treated as an open-source code dependency here.

MPCASU uses the system's FFmpeg/FFplay binaries as an external decoder/player
process. It does not embed VLC or Winamp code. Any distribution of a packaged
MPCASU build must ship the applicable FFmpeg/FFplay notices and licenses for
the exact binaries included by that distribution.

The clean-room boundary is intentional: MPCASU may learn from general player
concepts such as playlists, transport controls, skins and library views, but
all CASU integration, manifest validation, source-resolution and fallback code
is authored independently in this repository.

The built-in visualizer is an explanatory decoded-activity animation. It is
not presented as a waveform, a perceptual-quality score or an energy-saving
measurement. CASU state labels remain hints, while FFmpeg/FFplay remains the
canonical full-fidelity playback path.
