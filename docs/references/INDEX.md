# Project reference bundle

This directory contains the supplied design, format and development references
used to reconcile CASU, the converter and MPCASU. The files are preserved as
reference material; they are not copied into runtime code or treated as
implemented features by themselves.

## Normative visual assets

The visual references in `visual/` are retained for regression comparison.
Runtime branding uses the canonical files in `assets/`:

- `assets/casu_codec_icon.png`
- `assets/casu_converter_icon.png`
- `assets/mpcasu_player_icon.png`
- `assets/mpcasu_player_logo.png`

## Engineering references

- `CODEX_MASTER_PROMPT_CASU_MPCASU.txt`
- `CODEX_MPCASU_CASU_MASTER_IMPLEMENTATION_GUIDE.md`
- `01_CODEX_IDEE_SEGMENTED_STATE_DISPLAY.md`
- `02_CODEX_MOEGLICHER_ENTWICKLUNGSWEG.md`
- `03_CODEX_BEDINGUNGEN_LEGACY_MP4.md`
- `FORMAT_SPEC.md`
- `README(8).md`
- `ssc_codec.py` (historical/reference implementation only)

The active implementation and its honest completion status remain documented
in `CASU_CODEC_DEEP_AUDIT.md`, `CASU_CONVERTER_DEEP_AUDIT.md` and
`MPCASU_PLAYER_DEEP_AUDIT.md`.
