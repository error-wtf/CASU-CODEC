"""Verified CASU extraction and transcoding."""
from __future__ import annotations

import os
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from .core import CasuError, ffprobe, require_tool, resolve_casu_source
from .native import NativeCasuError, read_native
from .native_v2 import (ChunkType, NativeV2Error, TileStateCache,
                        decode_attachment, decode_audio_block, decode_chapter_table,
                        decode_bitmap_subtitle, decode_subtitle_packet,
                        read_native_v2)


class CasuExportError(CasuError):
    pass


_AUDIO_EXTENSIONS = {".aac", ".aiff", ".alac", ".flac", ".m4a", ".mka", ".mp3",
                     ".oga", ".ogg", ".opus", ".wav", ".wma"}


def _atomic_ffmpeg(command: list[str], destination: Path) -> Path:
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{destination.stem}.",
                                suffix=destination.suffix or ".media",
                                dir=destination.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        process = subprocess.run(command[:-1] + [str(temporary)], text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if process.returncode:
            detail = process.stderr.strip().splitlines()
            raise CasuExportError(detail[-1] if detail else "FFmpeg export failed")
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise CasuExportError("FFmpeg produced an empty export")
        os.replace(temporary, destination)
        return destination
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _codec_options(destination: Path, *, has_video: bool, has_audio: bool,
                   has_subtitles: bool = False,
                   has_rich_subtitles: bool = False) -> list[str]:
    extension = destination.suffix.lower()
    if not has_video:
        return {
            ".mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
            ".flac": ["-c:a", "flac"],
            ".wav": ["-c:a", "pcm_s16le"],
            ".ogg": ["-c:a", "libvorbis", "-q:a", "6"],
            ".oga": ["-c:a", "libvorbis", "-q:a", "6"],
            ".opus": ["-c:a", "libopus", "-b:a", "160k"],
            ".m4a": ["-c:a", "aac", "-b:a", "192k"],
            ".aac": ["-c:a", "aac", "-b:a", "192k"],
        }.get(extension, [])
    video = {
        ".webm": ["-c:v", "libvpx-vp9", "-crf", "24", "-b:v", "0"],
        ".avi": ["-c:v", "mpeg4", "-q:v", "3"],
    }.get(extension, ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p"])
    if not has_audio:
        result = video
    else:
        audio = (["-c:a", "libopus", "-b:a", "160k"] if extension == ".webm"
                 else ["-c:a", "aac", "-b:a", "192k"])
        result = video + audio
    if has_subtitles:
        result += (["-c:s", "webvtt"] if extension == ".webm" else
                   ["-c:s", "mov_text"] if extension in {".mp4", ".m4v", ".mov"} else
                   ["-c:s", "ass"] if has_rich_subtitles else
                   ["-c:s", "srt"])
    return result


def _legacy_source(casu_path: Path, temporary_directory: Path) -> Path | None:
    with casu_path.open("rb") as handle:
        magic = handle.read(8)
    if magic == b"CASUNAT1":
        container = read_native(casu_path, verify_payload=True)
        source_name = Path(str(container.manifest.get("source", {}).get("filename")
                               or "payload.bin")).name
        if not source_name or source_name in {".", ".."}:
            raise CasuExportError("CASUNAT1 source filename is invalid")
        return container.extract_payload(temporary_directory / source_name)
    if magic == b"CASUNAT2":
        return None
    return resolve_casu_source(casu_path)


def _native_bitmap_subtitles(container, stream_ids: set[int]) -> list:
    packets = []
    for offset, summary in zip(container.offsets, container.chunks):
        if (summary.stream_id in stream_ids
                and summary.chunk_type == ChunkType.SUBTITLE_BITMAP):
            chunk, _following = container.read_chunk_at(offset)
            packets.append(decode_bitmap_subtitle(chunk.payload))
    return sorted(packets, key=lambda packet: (packet.start_pts, packet.end_pts))


def _burn_bitmap_subtitles(rgb: np.ndarray, seconds: float, packets: list) -> np.ndarray:
    """Alpha-composite active native bitmap cues into one reconstructed frame."""
    result = np.asarray(rgb, dtype=np.uint8).copy()
    frame_height, frame_width = result.shape[:2]
    milliseconds = seconds * 1000.0
    for packet in packets:
        if not packet.start_pts <= milliseconds < packet.end_pts:
            continue
        x0 = max(0, min(frame_width, round(packet.x * frame_width /
                                           packet.canvas_width)))
        y0 = max(0, min(frame_height, round(packet.y * frame_height /
                                            packet.canvas_height)))
        x1 = max(x0, min(frame_width, round((packet.x + packet.width) *
                                            frame_width / packet.canvas_width)))
        y1 = max(y0, min(frame_height, round((packet.y + packet.height) *
                                             frame_height / packet.canvas_height)))
        if x1 <= x0 or y1 <= y0:
            continue
        source = np.frombuffer(packet.rgba, dtype=np.uint8).reshape(
            packet.height, packet.width, 4)
        rows = np.minimum(packet.height - 1,
                          np.arange(y1 - y0) * packet.height // (y1 - y0))
        columns = np.minimum(packet.width - 1,
                             np.arange(x1 - x0) * packet.width // (x1 - x0))
        scaled = source[rows[:, None], columns[None, :]]
        alpha = scaled[:, :, 3:4].astype(np.uint16)
        target = result[y0:y1, x0:x1].astype(np.uint16)
        result[y0:y1, x0:x1] = ((scaled[:, :, :3].astype(np.uint16) * alpha
                                 + target * (255 - alpha) + 127) // 255).astype(np.uint8)
    return result


def _write_native_video(container, directory: Path, descriptor: dict,
                        bitmap_subtitles: list | None = None) -> Path:
    from mpcasu_native_backend import canonical_to_rgb

    stream_id = int(descriptor["stream_id"])
    timeline = descriptor.get("frame_timeline") or []
    if not timeline:
        raise CasuExportError("CASUNAT2 video stream has no frame timeline")
    relevant = []
    for offset, summary in zip(container.offsets, container.chunks):
        if (summary.stream_id == stream_id and summary.chunk_type in
                {ChunkType.VIDEO_KEY_STATE, ChunkType.VIDEO_TILE_UPDATE}):
            relevant.append((summary.pts, offset, summary.chunk_type))
    relevant.sort(key=lambda item: (item[0], item[1]))
    cache = TileStateCache()
    chunk_index = 0
    prefix = f"video-{stream_id}"
    concat = directory / f"{prefix}.ffconcat"
    lines = ["ffconcat version 1.0"]
    for index, entry in enumerate(timeline):
        pts = int(entry["pts"])
        while chunk_index < len(relevant) and relevant[chunk_index][0] <= pts:
            _chunk_pts, offset, kind = relevant[chunk_index]
            chunk, _following = container.read_chunk_at(offset)
            if kind == ChunkType.VIDEO_KEY_STATE:
                cache.apply_key_state(chunk.payload)
            else:
                cache.apply_tile_update(chunk.payload)
            chunk_index += 1
        if cache.frame is None:
            raise CasuExportError("CASUNAT2 timeline precedes its first key state")
        rgb = canonical_to_rgb(cache.frame)
        num, den = (int(value) for value in descriptor["time_base"])
        rgb = _burn_bitmap_subtitles(rgb, pts * num / den,
                                     bitmap_subtitles or [])
        height, width, _channels = rgb.shape
        frame_name = f"{prefix}-frame-{index:09d}.ppm"
        (directory / frame_name).write_bytes(
            f"P6\n{width} {height}\n255\n".encode("ascii") + rgb.tobytes())
        duration_pts = int(entry.get("duration_pts") or 0)
        duration = duration_pts * num / den
        lines.append(f"file '{frame_name}'")
        if duration > 0:
            lines.append(f"duration {duration:.12f}")
    lines.append(f"file '{prefix}-frame-{len(timeline) - 1:09d}.ppm'")
    concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return concat


def _write_native_audio(container, directory: Path, descriptor: dict) -> Path:
    stream_id = int(descriptor["stream_id"])
    blocks = []
    for offset, summary in zip(container.offsets, container.chunks):
        if summary.stream_id == stream_id and summary.chunk_type == ChunkType.AUDIO_BLOCK:
            chunk, _following = container.read_chunk_at(offset)
            blocks.append(decode_audio_block(chunk.payload))
    if not blocks:
        raise CasuExportError("CASUNAT2 audio stream has no PCM blocks")
    blocks.sort(key=lambda block: block.pts * block.time_base_num / block.time_base_den)
    sample_rate, channels = blocks[0].sample_rate, blocks[0].channels
    target = directory / f"audio-{stream_id}.wav"
    cursor = 0
    with wave.open(str(target), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        for block in blocks:
            if (block.sample_rate, block.channels, block.sample_format) != (sample_rate, channels, "s16le"):
                raise CasuExportError("CASUNAT2 audio format changes are not exportable")
            start = round((block.pts * block.time_base_num / block.time_base_den) * sample_rate)
            if start > cursor:
                output.writeframesraw(b"\0" * ((start - cursor) * channels * 2))
                cursor = start
            skip = max(0, cursor - start)
            if skip < block.sample_count:
                output.writeframesraw(block.pcm[skip * channels * 2:])
                cursor += block.sample_count - skip
    return target


def _srt_time(milliseconds: int) -> str:
    value = max(0, int(milliseconds))
    hours, remainder = divmod(value, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _write_native_subtitle(container, directory: Path,
                           descriptor: dict) -> tuple[Path, bool] | None:
    stream_id = int(descriptor["stream_id"])
    if descriptor.get("rich_source_attachment"):
        rich = []
        for offset, summary in zip(container.offsets, container.chunks):
            if (summary.stream_id == stream_id and
                    summary.chunk_type == ChunkType.ATTACHMENT):
                chunk, _following = container.read_chunk_at(offset)
                attachment = decode_attachment(chunk.payload)
                if attachment.role == "subtitle-source":
                    rich.append(attachment)
        if len(rich) != 1:
            raise CasuExportError(
                "CASUNAT2 rich subtitle stream lacks one verified source attachment")
        target = directory / f"subtitle-{stream_id}.ass"
        target.write_bytes(rich[0].data)
        return target, True
    packets = []
    for offset, summary in zip(container.offsets, container.chunks):
        if (summary.stream_id == stream_id and
                summary.chunk_type == ChunkType.SUBTITLE_PACKET):
            chunk, _following = container.read_chunk_at(offset)
            packets.append(decode_subtitle_packet(chunk.payload))
    if not packets:
        return None
    packets.sort(key=lambda packet: (packet.start_pts, packet.end_pts))
    target = directory / f"subtitle-{stream_id}.srt"
    lines = []
    for index, packet in enumerate(packets, start=1):
        lines.extend([str(index),
                      f"{_srt_time(packet.start_pts)} --> {_srt_time(packet.end_pts)}",
                      packet.text, ""])
    target.write_text("\n".join(lines), encoding="utf-8")
    return target, False


def _ffmetadata_value(value: str) -> str:
    return (value.replace("\\", "\\\\").replace("\n", "\\\n")
            .replace("=", "\\=").replace(";", "\\;").replace("#", "\\#"))


def _write_native_chapters(container, directory: Path) -> Path | None:
    tables = []
    for offset, summary in zip(container.offsets, container.chunks):
        if summary.chunk_type == ChunkType.CHAPTER_TABLE:
            chunk, _following = container.read_chunk_at(offset)
            tables.append(decode_chapter_table(chunk.payload))
    if not tables:
        return None
    if len(tables) != 1:
        raise CasuExportError("CASUNAT2 contains multiple chapter tables")
    target = directory / "chapters.ffmetadata"
    lines = [";FFMETADATA1"]
    for chapter in tables[0]:
        lines.extend([
            "[CHAPTER]", "TIMEBASE=1/1000000000",
            f"START={int(chapter['start_pts'])}",
            f"END={int(chapter['end_pts'])}",
            f"title={_ffmetadata_value(str(chapter['title']))}",
            f"language={_ffmetadata_value(str(chapter.get('language') or 'und'))}",
        ])
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def export_casu(source: str | Path, destination: str | Path) -> Path:
    """Verify and export any supported CASU representation to an FFmpeg format."""
    require_tool("ffmpeg")
    source_path = Path(source).expanduser().resolve()
    destination_path = Path(destination).expanduser().resolve()
    if not source_path.is_file():
        raise CasuExportError("export input must be an existing CASU file")
    if destination_path == source_path or not destination_path.suffix:
        raise CasuExportError("export destination must use a media-file extension")
    try:
        with tempfile.TemporaryDirectory(prefix="casu-export-") as name:
            directory = Path(name)
            legacy = _legacy_source(source_path, directory)
            if legacy is not None:
                is_audio = destination_path.suffix.lower() in _AUDIO_EXTENSIONS
                overview = ffprobe(legacy)
                stream_types = [item.get("codec_type")
                                for item in overview.get("streams", [])]
                has_video = "video" in stream_types and not is_audio
                has_audio = "audio" in stream_types
                has_subtitles = "subtitle" in stream_types and not is_audio
                command = ["ffmpeg", "-v", "error", "-y", "-i", str(legacy)]
                command += (["-map", "0:a:0"] if is_audio else [
                    "-map", "0:v?", "-map", "0:a?", "-map", "0:s?",
                    "-map_chapters", "0",
                ])
                command += _codec_options(destination_path, has_video=has_video,
                                          has_audio=has_audio,
                                          has_subtitles=has_subtitles)
                return _atomic_ffmpeg(command + [str(destination_path)], destination_path)

            container = read_native_v2(source_path, load_payloads=False)
            streams = [item for item in container.manifest.get("streams", [])
                       if isinstance(item, dict)]
            videos = [item for item in streams if item.get("type") == "video"]
            audios = [item for item in streams if item.get("type") == "audio"]
            subtitles = [item for item in streams if item.get("type") == "subtitle"]
            if destination_path.suffix.lower() in _AUDIO_EXTENSIONS:
                videos = []
                audios = audios[:1]
                subtitles = []
            if not videos and not audios:
                raise CasuExportError("CASUNAT2 has no exportable audio/video stream")
            inputs: list[str] = []
            maps: list[str] = []
            input_index = 0
            bitmap_descriptors = [
                item for item in subtitles
                if (item.get("canonical_format") == "rgba-bitmap-region"
                    or str(item.get("codec_origin") or "").lower() in {
                        "hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"
                    })
            ]
            # A flattened video can contain one visible subtitle language. Honour
            # the container default, otherwise use the first stable stream order.
            selected_bitmap = next(
                (item for item in bitmap_descriptors
                 if item.get("default") or item.get("disposition", {}).get("default")),
                bitmap_descriptors[0] if bitmap_descriptors else None,
            )
            bitmap_streams = ({int(selected_bitmap["stream_id"])}
                              if selected_bitmap is not None else set())
            bitmap_packets = _native_bitmap_subtitles(container, bitmap_streams)
            for video in videos:
                inputs += ["-f", "concat", "-safe", "0", "-i",
                           str(_write_native_video(container, directory, video,
                                                   bitmap_packets))]
                maps += ["-map", f"{input_index}:v:0"]
                input_index += 1
            for audio in audios:
                inputs += ["-i", str(_write_native_audio(container, directory, audio))]
                maps += ["-map", f"{input_index}:a:0"]
                input_index += 1
            written_subtitles = []
            has_rich_subtitles = False
            for subtitle in subtitles:
                written = _write_native_subtitle(container, directory, subtitle)
                if written is None:
                    continue
                subtitle_path, rich = written
                inputs += ["-i", str(subtitle_path)]
                maps += ["-map", f"{input_index}:s:0"]
                written_subtitles.append(subtitle_path)
                has_rich_subtitles = has_rich_subtitles or rich
                input_index += 1
            chapters = _write_native_chapters(container, directory)
            chapter_input = None
            if chapters is not None:
                inputs += ["-f", "ffmetadata", "-i", str(chapters)]
                chapter_input = input_index
                input_index += 1
            command = ["ffmpeg", "-v", "error", "-y"] + inputs + maps
            if chapter_input is not None:
                command += ["-map_chapters", str(chapter_input)]
            command += _codec_options(destination_path, has_video=bool(videos),
                                      has_audio=bool(audios),
                                      has_subtitles=bool(written_subtitles),
                                      has_rich_subtitles=has_rich_subtitles)
            return _atomic_ffmpeg(command + [str(destination_path)], destination_path)
    except (OSError, ValueError, CasuError, NativeCasuError, NativeV2Error) as exc:
        if isinstance(exc, CasuExportError):
            raise
        raise CasuExportError(f"CASU export failed: {exc}") from exc
