# REFERENCE_LOOKUP — Schlüsselwort → exakte Stelle

Damit beim Portieren nie gelesen werden muss, wo etwas steht: Hier ist das
Abbild vom Referenzcode auf Datei:Zeile. Relative zu `/home/error/Codec-Casu`.

## Formate
| Was | Datei:Zeile |
|-----|-------------|
| CASUNAT1 Magic | casu/native.py:25 `MAGIC=b"CASUNAT1"` |
| CASUNAT1 Header `"<8sHHQQ32s32s"` (92B) | casu/native.py:27 |
| NAT1 Limits (manifest 64 MiB, payload 16 GiB) | casu/native.py:28-29, 95, 105, 146 |
| MP5 Magic | casu/mp5/format.py:10 `CASUMP5\0` |
| MP5 Header `"<8sHHII"` | casu/mp5/format.py:12 |
| MP5 Chunk header `"<BHII"` | casu/mp5/format.py:13 |
| MP5 zstd+zlib fallback | casu/mp5/reader.py:47 `_decompress` |
| MP5 Footer (count+sha256) | casu/mp5/reader.py:145 `verify_mp5` (161-167) |
| CASU sidecar Magic `MPCASU\0` | casu/core.py:574 |

## Player
| Was | Datei:Zeile |
|-----|-------------|
| ControllerState enum | mpcasu_playback.py:14-22 |
| attach/play/pause/stop/close | mpcasu_playback.py:32/44/49/58/73 |
| libVLC event map 0x109=ENDED, 0x10A=ERROR | mpcasu_backend.py:77-78 |
| state(): media 6=Ended, 7=Error, zero-time-EOF→ERROR | mpcasu_backend.py:600-627 |
| last_error / _note_error | mpcasu_backend.py (state-Methode) |
| set_xwindow (Linux) | mpcasu_backend.py `open_source` |
| VideoSurface (WA_NativeWindow, winId) | mpcasu_qt/videoframe.py |

## YouTube
| Was | Datei:Zeile |
|-----|-------------|
| is_youtube_url / resolve_media_location (shared resolver) | casu/locations.py:18 / :26 |
| resolver invokes `yt-dlp --get-url` | casu/locations.py:52 |
| Proxy RETRYABLE 403/410 | mpcasu_qt/youtube_proxy.py:61 |
| proxy start / refresh / preflight / media handler | :73 / :128 / :170 / :223 |
| Range→206 + Content-Range relay | mpcasu_qt/youtube_proxy.py:249 |
| MainWindow _play_youtube / _on_resolve_ready / _open_external_source | mpcasu_qt/main_window.py:4466 / 4491 / 4538 |
| _stop_yt_transport (stop(stop_youtube=...)) | mpcasu_qt/main_window.py |

## Web-Backend
| Was | Datei:Zeile |
|-----|-------------|
| do_POST routing (alle /api/*) | web_casu.py:402-469 |
| do_GET (/api/version, stream-proxy, /api/media) | web_casu.py:603-617 |
| Range/HEAD media serving | web_casu.py:_serve_transcoded_file (663+) |
| allow-list stream-proxy | web_casu.py `_stream_proxy` |
| TranscodeStore (tokens/upload) | web_casu.py TranscodeStore |

## Converter
| Was | Datei:Zeile |
|-----|-------------|
| ConversionEngine run/_convert/journal | casu/jobs.py |
| MEDIA_PRESETS {remux,balanced,high,small,lossless} | casu/transcode.py:20 |
| quality options + ffmpeg arg builder | casu/transcode.py:82-156 |
| GUI (Tk) | casu_converter.py (1061 Zeilen) |

## CLI
| Was | Datei:Zeile |
|-----|-------------|
| alle Subcommands (analyze…benchmark) | casu/cli.py:162-242 |
| convert subcommand args | casu/cli.py:169-182 |

## UI-Design
| Was | Datei:Zeile |
|-----|-------------|
| DesignTokens: sidebar 240, right_panel 370, topbar 72, transport 66 | casu/design.py:45-48 |
| RED/BG/TOAST/INPUT tokens | casu/design.py:55-69 |
| Palette/Metrics (Qt-Mirror) | mpcasu_qt/theme.py |

## Zu beachten (Fallen)
- **libVLC state-Mapping** 6/7 + zero-time-EOF: mpcasu_backend.py:600-627 — sonst
  erfolgreiches Playback sieht wie Fehler aus.
- **YouTube-Lifecycle** (stop old → start proxy → open): main_window
  _play_youtube/_on_resolve_ready — nie Proxy vor open zerstören.
- **NOW PLAYING** feste Überschrift, Titel separat: main_window topbar.
- **VideoSurface-Overlays** verstecken im Video-Modus: videoframe + main_window
  _reposition_overlays.
- **PulseAudio nur Linux** (NativeCasuBackend) → WASAPI/Qt auf Windows.

## Nachschlag-Reihenfolge (Token-effizient)
1. `REFERENCE_LOOKUP.md` → Datei:Zeile
2. gezielt `sed -n '<start>,<end>p' <datei>` lesen
3. nötigenfalls `grep` auf Schlüsselwort
Nur bei ungelösten Fragen: research-Dokument + Deep-Research.
