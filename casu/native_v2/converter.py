"""Reference source-media to standalone CASUNAT2 conversion pipeline."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import re
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from casu.strict import StrictDecoderError, StrictFrame, iter_source_frames
from casu.strict.tiles import compare_frames
from casu.probe import ProbeError, run_bounded, run_json

from .audio import encode_audio_block
from .bitmap import encode_bitmap_subtitle
from .format import ChunkType, NativeChunk
from .text import SubtitlePacket, encode_chapter_table, encode_subtitle_packet
from .attachment import encode_attachment
from .video import encode_format_change, encode_key_state, encode_tile_update
from .writer import write_native_v2


class NativeConversionError(RuntimeError):
    pass


def _bounded_tags(value: Any, *, max_entries: int = 256,
                  max_total_bytes: int = 1024 * 1024) -> dict[str, str]:
    """Canonicalize untrusted demuxer tags before placing them in a manifest."""
    if value is None:
        return {}
    if not isinstance(value, dict) or len(value) > max_entries:
        raise NativeConversionError("source metadata exceeds tag count limit")
    result: dict[str, str] = {}
    total = 0
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip()
        item = str(raw_value)
        if not key or len(key.encode("utf-8")) > 128:
            raise NativeConversionError("source metadata key is invalid")
        encoded = item.encode("utf-8")
        if len(encoded) > 4096:
            raise NativeConversionError("source metadata value exceeds limit")
        total += len(key.encode("utf-8")) + len(encoded)
        if total > max_total_bytes:
            raise NativeConversionError("source metadata exceeds total size limit")
        result[key] = item
    return dict(sorted(result.items(), key=lambda pair: pair[0].casefold()))


def _disposition(value: Any) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    return dict(sorted((str(key), bool(enabled)) for key, enabled in value.items()))


def _run_json(command: list[str]) -> dict:
    try:
        return run_json(command)
    except ProbeError as exc:
        raise NativeConversionError("media probe failed") from exc


def _inventory(source: Path, selector: str) -> tuple[dict, list[dict]]:
    data = _run_json([
        "ffprobe", "-v", "error", "-select_streams", selector,
        "-show_entries",
        "stream=width,height,pix_fmt,time_base,color_space,color_transfer,color_primaries,color_range,chroma_location,sample_rate,channels,channel_layout:"
        "frame=best_effort_timestamp,pts,pkt_duration,duration,nb_samples,width,height,pix_fmt",
        "-of", "json", str(source),
    ])
    streams = data.get("streams") or []
    if len(streams) != 1:
        raise NativeConversionError(f"probe selector {selector} did not resolve one stream")
    return streams[0], list(data.get("frames") or [])


def _fraction(text: str) -> tuple[int, int]:
    try:
        numerator, denominator = (int(value) for value in text.split("/", 1))
    except (AttributeError, TypeError, ValueError) as exc:
        raise NativeConversionError("invalid source time base") from exc
    if numerator <= 0 or denominator <= 0:
        raise NativeConversionError("invalid source time base")
    return numerator, denominator


def _frame_pts(frames: list[dict]) -> list[dict[str, int | None]]:
    result = []
    for frame in frames:
        pts = frame.get("best_effort_timestamp", frame.get("pts"))
        if pts is None:
            raise NativeConversionError("decoded frame has no presentation timestamp")
        duration = frame.get("pkt_duration", frame.get("duration"))
        result.append({"pts": int(pts),
                       "duration_pts": int(duration) if duration not in (None, "N/A") else None})
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stream_config_payload(descriptor: dict) -> bytes:
    return json.dumps(descriptor, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _video_chunks(source: Path, stream_id: int, relative_index: int,
                  max_key_interval: Fraction, tile_width: int,
                  tile_height: int, cancel: Any | None) -> Iterator[NativeChunk]:
    previous: StrictFrame | None = None
    last_key_time: Fraction | None = None
    previous_hashes: dict[tuple[int, int, int, int], str] | None = None
    for current in iter_source_frames(source, stream_index=relative_index):
        if cancel is not None and getattr(cancel, "is_set", lambda: False)():
            raise NativeConversionError("native conversion cancelled")
        now = current.time.fraction
        format_change = previous is None or previous.frame.format_identity != current.frame.format_identity
        key_due = last_key_time is None or now - last_key_time >= max_key_interval
        if previous is not None and format_change:
            yield NativeChunk(ChunkType.VIDEO_FORMAT_CHANGE, stream_id,
                              current.pts,
                              encode_format_change(current.frame))
        if format_change or key_due:
            yield NativeChunk(ChunkType.VIDEO_KEY_STATE, stream_id, current.pts,
                              encode_key_state(current.frame))
            last_key_time = now
            previous_hashes = None
        else:
            states = compare_frames(previous.frame, current.frame,
                                    valid_from=current.time,
                                    tile_width=tile_width, tile_height=tile_height,
                                    previous_hashes=previous_hashes)
            previous_hashes = {
                (state.region["x"], state.region["y"],
                 state.region["w"], state.region["h"]): state.state_hash
                for state in states
            }
            for state in states:
                if state.state != "UPDATE":
                    continue
                region = state.region
                yield NativeChunk(
                    ChunkType.VIDEO_TILE_UPDATE, stream_id, current.pts,
                    encode_tile_update(current.frame, x=region["x"], y=region["y"],
                                       width=region["w"], height=region["h"],
                                       base_state_hash=state.reference_hash,
                                       new_state_hash=state.state_hash),
                )
        previous = current


def _audio_chunks(source: Path, stream_id: int, relative_index: int,
                  stream: dict, frames: list[dict], cancel: Any | None) -> Iterator[NativeChunk]:
    sample_rate = int(stream.get("sample_rate") or 0)
    channels = int(stream.get("channels") or 0)
    if sample_rate <= 0 or channels <= 0:
        raise NativeConversionError("invalid source audio format")
    time_base_num, time_base_den = _fraction(str(stream.get("time_base")))
    command = ["ffmpeg", "-v", "error", "-i", str(source), "-map", f"0:a:{relative_index}",
               "-vn", "-sn", "-dn", "-ac", str(channels), "-ar", str(sample_rate),
               "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1"]
    errors = tempfile.TemporaryFile(mode="w+b")
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
    try:
        assert process.stdout is not None
        for info in frames:
            if cancel is not None and getattr(cancel, "is_set", lambda: False)():
                raise NativeConversionError("native conversion cancelled")
            pts = info.get("best_effort_timestamp", info.get("pts"))
            samples = int(info.get("nb_samples") or 0)
            if pts is None or samples <= 0:
                raise NativeConversionError("decoded audio frame lacks PTS/sample count")
            length = samples * channels * 2
            pcm = process.stdout.read(length)
            if len(pcm) != length:
                raise NativeConversionError("audio decoder ended before a complete PCM block")
            payload = encode_audio_block(
                pcm=pcm, pts=int(pts), time_base_num=time_base_num,
                time_base_den=time_base_den, sample_rate=sample_rate,
                channels=channels, channel_layout=stream.get("channel_layout"),
                sample_format="s16le", sample_count=samples,
            )
            yield NativeChunk(ChunkType.AUDIO_BLOCK, stream_id, int(pts), payload)
        if process.stdout.read(1):
            raise NativeConversionError("audio decoder produced more samples than its frame inventory")
    finally:
        if process.stdout:
            process.stdout.close()
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=5)
        errors.seek(0)
        message = errors.read().decode("utf-8", errors="replace").strip()
        errors.close()
        if process.returncode not in (0, None) and "cancelled" not in message:
            raise NativeConversionError(f"audio decoder failed: {message or process.returncode}")


_VTT_TIME = re.compile(
    r"(?:(?P<sh>\d{2}):)?(?P<sm>\d{2}):(?P<ss>\d{2})\.(?P<sms>\d{3})\s+-->\s+"
    r"(?:(?P<eh>\d{2}):)?(?P<em>\d{2}):(?P<es>\d{2})\.(?P<ems>\d{3})")


def _vtt_milliseconds(match: re.Match[str], prefix: str) -> int:
    return (((int(match[f"{prefix}h"] or 0) * 60 + int(match[f"{prefix}m"])) * 60
             + int(match[f"{prefix}s"])) * 1000 + int(match[f"{prefix}ms"]))


def _subtitle_chunks(source: Path, stream_id: int, relative_index: int,
                     language: str, cancel: Any | None) -> Iterator[NativeChunk]:
    """Decode a text subtitle stream to deterministic UTF-8 packets at 1/1000."""
    if cancel is not None and getattr(cancel, "is_set", lambda: False)():
        raise NativeConversionError("native conversion cancelled")
    command = ["ffmpeg", "-v", "error", "-i", str(source), "-map", f"0:s:{relative_index}",
               "-f", "webvtt", "pipe:1"]
    try:
        text = run_bounded(command, max_output_bytes=64 * 1024 * 1024,
                           timeout_seconds=600).decode("utf-8")
    except (ProbeError, UnicodeDecodeError) as exc:
        raise NativeConversionError(
            "subtitle stream cannot be represented by the native text reference codec") from exc
    lines = text.replace("\r\n", "\n").split("\n")
    index = 0
    while index < len(lines):
        match = _VTT_TIME.search(lines[index])
        if not match:
            index += 1
            continue
        index += 1
        values = []
        while index < len(lines) and lines[index].strip():
            values.append(lines[index]); index += 1
        cue = "\n".join(values).strip()
        if cue:
            start = _vtt_milliseconds(match, "s")
            end = _vtt_milliseconds(match, "e")
            packet = SubtitlePacket(start, end, cue, language or "und", "webvtt-text")
            yield NativeChunk(ChunkType.SUBTITLE_PACKET, stream_id, start,
                              encode_subtitle_packet(packet))


def _rich_subtitle_source_chunk(source: Path, stream_id: int,
                                relative_index: int, stream: dict,
                                cancel: Any | None) -> NativeChunk | None:
    """Preserve bounded ASS/SSA styling beside the playable text fallback."""
    codec = str(stream.get("codec_name") or "").lower()
    if codec not in {"ass", "ssa"}:
        return None
    if cancel is not None and getattr(cancel, "is_set", lambda: False)():
        raise NativeConversionError("native conversion cancelled")
    command = [
        "ffmpeg", "-v", "error", "-i", str(source),
        "-map", f"0:s:{relative_index}", "-c:s", "copy", "-f", "ass", "pipe:1",
    ]
    try:
        data = run_bounded(command, max_output_bytes=64 * 1024 * 1024,
                           timeout_seconds=600)
        data.decode("utf-8")
    except (ProbeError, UnicodeDecodeError) as exc:
        raise NativeConversionError("could not preserve rich subtitle source") from exc
    return NativeChunk(
        ChunkType.ATTACHMENT, stream_id, 0,
        encode_attachment(f"subtitle-{stream_id}.ass", "text/x-ssa", data,
                          role="subtitle-source"),
    )


_BITMAP_SUBTITLE_CODECS = {"hdmv_pgs_subtitle", "dvd_subtitle",
                           "dvb_subtitle", "xsub"}


def _bitmap_canvas_size(stream: dict, overview: dict) -> tuple[int, int] | None:
    """Resolve the subtitle coordinate system before FFmpeg creates sub2video."""
    width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
    if width > 0 and height > 0:
        return width, height
    videos = [item for item in overview.get("streams", [])
              if item.get("codec_type") == "video"
              and not item.get("disposition", {}).get("attached_pic")]
    video = videos[0] if videos else {}
    codec = str(stream.get("codec_name") or "").lower()
    if codec == "dvd_subtitle":
        video_height = int(video.get("height") or 0)
        try:
            rate = Fraction(str(video.get("avg_frame_rate") or "0/1"))
        except (ValueError, ZeroDivisionError):
            rate = Fraction(0)
        # DVD SPU coordinates use a full D1 canvas even when the accompanying
        # MPEG video is a half-D1/VCD-sized PAL or NTSC stream.
        return (720, 480) if video_height in {240, 480} or rate > 27 else (720, 576)
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    return (width, height) if width > 0 and height > 0 else None


def _packed_rgba(frame: StrictFrame) -> np.ndarray:
    height, width = frame.frame.shape
    packed = frame.frame.planes[0].reshape(height, width, 4)
    orders = {"rgba": (0, 1, 2, 3), "bgra": (2, 1, 0, 3),
              "argb": (1, 2, 3, 0), "abgr": (3, 2, 1, 0)}
    order = orders.get(frame.frame.pixel_format)
    if order is None:
        raise NativeConversionError(
            f"bitmap subtitle renderer returned {frame.frame.pixel_format!r}, expected RGBA")
    return np.ascontiguousarray(packed[..., list(order)])


def _bitmap_subtitle_chunks(source: Path, stream_id: int, relative_index: int,
                            duration_seconds: float,
                            cancel: Any | None,
                            canvas_size: tuple[int, int] | None = None) -> Iterator[NativeChunk]:
    """Decode PGS/DVD/DVB/XSub through FFmpeg sub2video to bounded RGBA states."""
    if cancel is not None and getattr(cancel, "is_set", lambda: False)():
        raise NativeConversionError("native conversion cancelled")
    duration_ms = max(1, round(max(0.0, duration_seconds) * 1000))
    with tempfile.TemporaryDirectory(prefix="casu-bitmap-subtitle-") as directory:
        rendered = Path(directory) / "overlay.mkv"
        command = ["ffmpeg", "-v", "error"]
        if canvas_size is not None:
            width, height = (int(value) for value in canvas_size)
            if (width <= 0 or height <= 0 or width > 16_384 or height > 16_384
                    or width * height * 4 > 256 * 1024 * 1024):
                raise NativeConversionError("bitmap subtitle canvas exceeds limits")
            command.extend([f"-canvas_size:s:{relative_index}", f"{width}x{height}"])
        command.extend([
            "-i", str(source),
            "-filter_complex", f"[0:s:{relative_index}]format=rgba[out]",
            "-map", "[out]", "-fps_mode", "passthrough", "-c:v", "ffv1",
            "-pix_fmt", "rgba", "-y", str(rendered),
        ])
        try:
            run_bounded(command, max_output_bytes=1024 * 1024,
                        timeout_seconds=600,
                        watched_paths=((rendered, 2 * 1024 * 1024 * 1024),))
            decoded = list(iter_source_frames(rendered, engine="ffmpeg"))
        except (ProbeError, OSError, StrictDecoderError) as exc:
            raise NativeConversionError("could not decode bitmap subtitle stream") from exc
    by_pts: dict[int, np.ndarray] = {}
    for frame in decoded:
        if cancel is not None and getattr(cancel, "is_set", lambda: False)():
            raise NativeConversionError("native conversion cancelled")
        pts_ms = round(frame.time.fraction * 1000)
        if 0 <= pts_ms <= duration_ms:
            by_pts[pts_ms] = _packed_rgba(frame)
    states: list[tuple[int, np.ndarray]] = []
    previous_digest: str | None = None
    for pts, rgba in sorted(by_pts.items()):
        digest = hashlib.sha256(rgba.tobytes()).hexdigest()
        if digest == previous_digest:
            continue
        states.append((pts, rgba)); previous_digest = digest
    for index, (start, rgba) in enumerate(states):
        end = states[index + 1][0] if index + 1 < len(states) else duration_ms
        if end <= start:
            continue
        alpha_y, alpha_x = np.nonzero(rgba[..., 3])
        if not len(alpha_x):
            continue
        left, right = int(alpha_x.min()), int(alpha_x.max()) + 1
        top, bottom = int(alpha_y.min()), int(alpha_y.max()) + 1
        crop = np.ascontiguousarray(rgba[top:bottom, left:right])
        payload = encode_bitmap_subtitle(
            start_pts=start, end_pts=end, canvas_width=rgba.shape[1],
            canvas_height=rgba.shape[0], x=left, y=top,
            width=right - left, height=bottom - top, rgba=crop.tobytes())
        yield NativeChunk(ChunkType.SUBTITLE_BITMAP, stream_id, start, payload)


def _chapter_chunk(chapters: list[dict]) -> NativeChunk | None:
    values = []
    for index, chapter in enumerate(chapters):
        try:
            start = int(Fraction(str(chapter.get("start_time", "0"))) * 1_000_000_000)
            end = int(Fraction(str(chapter.get("end_time", chapter.get("start_time", "0"))))
                      * 1_000_000_000)
        except (ValueError, ZeroDivisionError) as exc:
            raise NativeConversionError("invalid chapter timeline") from exc
        title = str(chapter.get("tags", {}).get("title") or f"Chapter {index + 1}")
        language = str(chapter.get("tags", {}).get("language") or "und")
        values.append({"start_pts": start, "end_pts": end, "title": title,
                       "language": language})
    if not values:
        return None
    return NativeChunk(ChunkType.CHAPTER_TABLE, 0, 0, encode_chapter_table(values))


def _attachment_chunk(source: Path, stream_id: int, relative_index: int,
                      stream: dict, cancel: Any | None) -> NativeChunk:
    if cancel is not None and getattr(cancel, "is_set", lambda: False)():
        raise NativeConversionError("native conversion cancelled")
    with tempfile.TemporaryDirectory(prefix="casu-attachment-") as directory:
        extracted = Path(directory) / "attachment.bin"
        command = ["ffmpeg", "-v", "error", "-dump_attachment:t:" + str(relative_index),
                   str(extracted), "-i", str(source), "-f", "null", "-"]
        try:
            run_bounded(command, max_output_bytes=1024 * 1024,
                        timeout_seconds=600,
                        watched_paths=((extracted, 64 * 1024 * 1024),))
            data = extracted.read_bytes()
        except (ProbeError, OSError) as exc:
            raise NativeConversionError("could not extract source attachment") from exc
    filename = str(stream.get("tags", {}).get("filename") or f"attachment-{relative_index}.bin")
    media_type = str(stream.get("tags", {}).get("mimetype") or "application/octet-stream")
    suffix = Path(filename).suffix.lower()
    role = ("subtitle-font" if media_type.lower().startswith("font/")
            or media_type.lower() in {"application/x-truetype-font", "application/vnd.ms-opentype",
                                      "application/font-sfnt", "application/font-woff"}
            or suffix in {".ttf", ".otf", ".ttc", ".woff", ".woff2"} else None)
    return NativeChunk(ChunkType.ATTACHMENT, stream_id, 0,
                       encode_attachment(filename, media_type, data, role=role))


def _cover_art_chunk(source: Path, stream_id: int, source_index: int,
                     stream: dict, cancel: Any | None) -> NativeChunk:
    """Normalize an attached-picture stream to a bounded standalone PNG."""
    if cancel is not None and getattr(cancel, "is_set", lambda: False)():
        raise NativeConversionError("native conversion cancelled")
    width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
    if (width <= 0 or height <= 0 or width > 8192 or height > 8192
            or width * height * 4 > 256 * 1024 * 1024):
        raise NativeConversionError("cover art geometry exceeds decode limits")
    with tempfile.TemporaryDirectory(prefix="casu-cover-") as directory:
        extracted = Path(directory) / "cover.png"
        command = [
            "ffmpeg", "-v", "error", "-i", str(source),
            "-map", f"0:{source_index}", "-frames:v", "1", "-an", "-sn", "-dn",
            "-c:v", "png", "-f", "image2", "-update", "1", "-y", str(extracted),
        ]
        try:
            run_bounded(command, max_output_bytes=1024 * 1024,
                        timeout_seconds=120,
                        watched_paths=((extracted, 64 * 1024 * 1024),))
            if extracted.stat().st_size > 64 * 1024 * 1024:
                raise NativeConversionError("cover art exceeds attachment size limit")
            data = extracted.read_bytes()
        except (ProbeError, OSError) as exc:
            raise NativeConversionError("could not decode attached cover art") from exc
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise NativeConversionError("decoded cover art is not PNG")
    title = str(stream.get("tags", {}).get("title") or "cover")
    safe_title = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-.") or "cover"
    filename = f"{safe_title[:80]}.png"
    return NativeChunk(ChunkType.ATTACHMENT, stream_id, 0,
                       encode_attachment(filename, "image/png", data,
                                         role="cover-art"))


def convert_media_to_native_v2(source: str | Path, target: str | Path, *,
                               tile_width: int = 64, tile_height: int = 64,
                               max_key_interval_seconds: float = 3.0,
                               recovery_interval: int = 32,
                               cancel: Any | None = None,
                               progress: Any | None = None) -> Path:
    """Convert decoded video/audio states into a standalone CASUNAT2 file."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise NativeConversionError("ffmpeg and ffprobe are required")
    src = Path(source).expanduser().resolve()
    if not src.is_file():
        raise NativeConversionError(f"source does not exist: {src}")
    if tile_width <= 0 or tile_height <= 0 or max_key_interval_seconds <= 0:
        raise NativeConversionError("tile dimensions and key interval must be positive")
    def notify(value: float) -> None:
        if progress is not None:
            progress(max(0.0, min(1.0, float(value))))
    notify(0.0)
    overview = _run_json(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                          "-show_chapters",
                          "-of", "json", str(src)])
    notify(0.05)
    source_streams: list[tuple[dict, str, int]] = []
    relative_seen = {"video": 0, "audio": 0, "subtitle": 0, "attachment": 0}
    for value in overview.get("streams", []):
        source_kind = value.get("codec_type")
        if source_kind not in relative_seen:
            continue
        relative = relative_seen[source_kind]
        relative_seen[source_kind] += 1
        kind = ("cover-art" if source_kind == "video"
                and value.get("disposition", {}).get("attached_pic") else source_kind)
        source_streams.append((value, kind, relative))
    if not any(kind in {"video", "audio"} for _stream, kind, _relative in source_streams):
        raise NativeConversionError("source has no decodable video or audio stream")

    descriptors: list[dict] = []
    ignored_streams: list[dict] = []
    inventories: dict[int, list[dict]] = {}
    mappings: list[tuple[int, str, int, dict]] = []
    for stream_id, (stream, kind, relative) in enumerate(source_streams, start=1):
        if kind in {"subtitle", "attachment"}:
            probed, frames = stream, []
        elif kind == "cover-art":
            probed, frames = stream, []
        else:
            probed, frames = _inventory(src, f"{kind[0]}:{relative}")
        effective = dict(stream)
        effective.update(probed)
        if kind == "audio" and (int(effective.get("sample_rate") or 0) <= 0
                                or int(effective.get("channels") or 0) <= 0):
            ignored_streams.append({
                "source_index": int(stream.get("index", relative)),
                "type": "audio", "codec_origin": stream.get("codec_name"),
                "reason": "decoder reported no usable sample rate/channels",
            })
            continue
        inventories[stream_id] = frames
        descriptor = {
            "stream_id": stream_id,
            "type": "attachment" if kind == "cover-art" else kind,
            "source_index": int(effective.get("index", relative)),
            "codec_origin": effective.get("codec_name"),
            "time_base": ([1, 1000] if kind == "subtitle" else
                          [1, 1] if kind in {"attachment", "cover-art"} else
                          list(_fraction(str(probed.get("time_base"))))),
            "language": effective.get("tags", {}).get("language"),
            "default": bool(effective.get("disposition", {}).get("default")),
            "forced": bool(effective.get("disposition", {}).get("forced")),
            "frame_timeline": _frame_pts(frames),
            "disposition": _disposition(effective.get("disposition")),
            "tags": _bounded_tags(effective.get("tags")),
        }
        if kind == "cover-art":
            descriptor["role"] = "cover-art"
        if kind == "subtitle" and str(effective.get("codec_name") or "").lower() in {"ass", "ssa"}:
            descriptor["rich_source_attachment"] = True
            descriptor["playback_fallback"] = "utf8-webvtt-text"
        if kind == "subtitle" and str(effective.get("codec_name") or "").lower() in _BITMAP_SUBTITLE_CODECS:
            descriptor["canonical_format"] = "rgba-bitmap-region"
            canvas = _bitmap_canvas_size(effective, overview)
            if canvas is not None:
                descriptor["canvas_size"] = list(canvas)
        for key in ("width", "height", "pix_fmt", "color_range", "color_space",
                    "color_transfer", "color_primaries", "chroma_location",
                    "sample_rate", "channels", "channel_layout"):
            if effective.get(key) is not None:
                descriptor[key] = effective[key]
        descriptors.append(descriptor)
        mappings.append((stream_id, kind, relative, effective))
        notify(0.05 + 0.15 * stream_id / len(source_streams))

    if not any(item["type"] in {"video", "audio"} for item in descriptors):
        raise NativeConversionError("source has no usable video or audio stream")

    manifest = {
        "format": "CASUNAT2",
        "version": 2,
        "source_provenance": {"filename": src.name, "size_bytes": src.stat().st_size,
                              "sha256": _sha256(src),
                              "duration_s": float(overview.get("format", {}).get("duration") or 0.0)},
        "metadata": _bounded_tags(overview.get("format", {}).get("tags")),
        "ignored_streams": ignored_streams,
        "streams": descriptors,
        "video_policy": {"fidelity": "SOURCE_RESOLUTION_STRICT",
                         "tile_size": [tile_width, tile_height],
                         "max_key_interval_seconds": max_key_interval_seconds},
        "audio_policy": {"canonical_format": "s16le", "timing": "source PTS"},
        "subtitle_policy": {"canonical_format": "utf8-webvtt-text", "time_base": [1, 1000]},
        "chapter_time_base": [1, 1_000_000_000],
    }
    interval = Fraction(str(max_key_interval_seconds))

    def chunks() -> Iterator[NativeChunk]:
        chapter = _chapter_chunk(list(overview.get("chapters") or []))
        if chapter is not None:
            yield chapter
        for stream_number, (stream_id, kind, relative, stream) in enumerate(mappings):
            notify(0.20 + 0.75 * stream_number / len(mappings))
            if kind == "video":
                yield from _video_chunks(src, stream_id, relative, interval,
                                         tile_width, tile_height, cancel)
            elif kind == "audio":
                yield from _audio_chunks(src, stream_id, relative, stream,
                                         inventories[stream_id], cancel)
            elif kind == "subtitle":
                codec = str(stream.get("codec_name") or "").lower()
                if codec in _BITMAP_SUBTITLE_CODECS:
                    yield from _bitmap_subtitle_chunks(
                        src, stream_id, relative,
                        float(overview.get("format", {}).get("duration") or 0.0), cancel,
                        _bitmap_canvas_size(stream, overview))
                else:
                    rich = _rich_subtitle_source_chunk(src, stream_id, relative,
                                                       stream, cancel)
                    if rich is not None:
                        yield rich
                    yield from _subtitle_chunks(src, stream_id, relative,
                                                str(stream.get("tags", {}).get("language") or "und"),
                                                cancel)
            elif kind == "cover-art":
                yield _cover_art_chunk(src, stream_id,
                                       int(stream.get("index", relative)), stream, cancel)
            else:
                yield _attachment_chunk(src, stream_id, relative, stream, cancel)
            notify(0.20 + 0.75 * (stream_number + 1) / len(mappings))

    result = write_native_v2(target, manifest, chunks(), recovery_interval=recovery_interval)
    notify(1.0)
    return result
