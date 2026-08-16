# Tool Dependency Graph + Per-Tool Roadmap Audit + Port Status

## Dependency graph (per tool)

```
                     casu_core ──┬─▶ casu_codec ──┬─▶ TOOL-CONVERTER
(container/manifest/            │                  └─▶ TOOL-CASU-CLI (pack/export)
 native_v2/mp5/zstd)            ├─▶ casu_media ──┬─▶ TOOL-MPCASU (viz/cover)
                                 │               └─▶ TOOL-CONVERTER
                                 └─▶ casu_playback ──▶ TOOL-MPCASU
casu_network ──┬─▶ TOOL-MPCASU (net streams, YouTube transport)
               └─▶ casu_webapi ──▶ TOOL-WEB-BACKEND
casu_media / casu_codec ──▶ TOOL-CONVERTER, TOOL-CASU-CLI
web/pure (frozen) ──▶ TOOL-PURE-WEB (bundled)
helpers yt-dlp.exe/ffmpeg.exe/ffprobe.exe ──▶ QProcess from MPCASU/CLI/Web-backend
release tools ──▶ build-windows-release.sh wraps all
```

Build order: casu_core → casu_codec/casu_media → casu_network →
casu_playback → casu_webapi → apps (CLI → Converter → MPCASU → Web-Backend)
→ Pure-Web integration → packaging/release.

## Per-tool roadmap audit

| Tool | Roadmap | Features | Shared-core reuse | Wine plan | Acceptance gate | Status |
|------|---------|----------|-------------------|-----------|-----------------|--------|
| TOOL-MPCASU | roadmap/tools/mpcasu | 22 features | casu_playback/core/network | full matrix | ACCEPTANCE_GATE.md | NOT_STARTED |
| TOOL-CONVERTER | roadmap/tools/converter | full GUI | casu_codec/media/core | matrix | – | NOT_STARTED |
| TOOL-WEB-BACKEND | roadmap/tools/web-backend | per-endpoint | casu_webapi/network | matrix | security | NOT_STARTED |
| TOOL-PURE-WEB | roadmap/tools/pure-web | integration | (frozen) | browser | SHA256 | NOT_STARTED |
| TOOL-CASU-CLI | roadmap/tools/casu-cli | per-subcommand | casu_core/codec | stdout+exit | identical | NOT_STARTED |
| TOOL-SMOKE* etc | roadmap/tools/dev-tools | classified | – | harness | – | NOT_STARTED |
| TOOL-RELEASE | roadmap/tools/release-tools | build/pkg/gate | – | clean prefix | gate JSON | NOT_STARTED |
| lib casu_core/codec/media/network/playback/webapi | roadmap/libraries/* | per-WP | – | unit+wine | golden | NOT_STARTED |

No duplicate shared logic planned; every tool links the libraries. No tool
left without a roadmap. Reference tree stays read-only.

## TOOL_PORT_STATUS

| Tool | Analysis | Roadmap | Impl | Build | Wine | Final |
|------|----------|---------|------|-------|------|-------|
| MPCASU | done | done | – | – | – | NOT_STARTED |
| Converter | done | done | – | – | – | NOT_STARTED |
| Web-Backend | done | done | – | – | – | NOT_STARTED |
| Pure-Web | done | done | – | – | – | NOT_STARTED |
| CASU-CLI | done | done | – | – | – | NOT_STARTED |
| Dev-tools | done | done | – | – | – | NOT_STARTED |
| Release-tools | done | done | – | – | – | NOT_STARTED |
