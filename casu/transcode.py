"""Atomic, cancellable FFmpeg media-to-media transcoding."""
from __future__ import annotations

import os
import re
import selectors
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from .core import CasuCancelled, CasuError, require_tool
from .probe import ProbeError, run_json


class MediaTranscodeError(CasuError):
    pass


MEDIA_PRESETS = frozenset({"remux", "balanced", "high", "small", "lossless"})
SUBTITLE_MODES = frozenset({"auto", "copy", "drop"})
AUDIO_EXTENSIONS = frozenset({
    ".aac", ".aif", ".aiff", ".alac", ".flac", ".m4a", ".mka", ".mp2",
    ".mp3", ".oga", ".ogg", ".opus", ".wav", ".wma",
})
VIDEO_EXTENSIONS = frozenset({
    ".3g2", ".3gp", ".asf", ".avi", ".f4v", ".flv", ".m2ts", ".m4v",
    ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".mts", ".ogv", ".ts",
    ".webm", ".wmv",
})
MEDIA_OUTPUT_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
_CODEC_NAME = re.compile(r"[A-Za-z0-9_+.-]{1,64}\Z")


def _probe(source: str | Path) -> dict[str, Any]:
    require_tool("ffprobe")
    try:
        return run_json([
            "ffprobe", "-v", "error", "-show_streams", "-show_format",
            "-of", "json", str(source),
        ], max_output_bytes=16 * 1024 * 1024, timeout_seconds=30)
    except ProbeError as exc:
        raise MediaTranscodeError(f"media probe failed: {exc}") from exc


def _playable_streams(probe: dict[str, Any]) -> tuple[list[dict], list[dict], list[dict]]:
    streams = [item for item in probe.get("streams", []) if isinstance(item, dict)]
    videos = [item for item in streams if item.get("codec_type") == "video"
              and not item.get("disposition", {}).get("attached_pic")]
    audios = [item for item in streams if item.get("codec_type") == "audio"]
    subtitles = [item for item in streams if item.get("codec_type") == "subtitle"]
    return videos, audios, subtitles


def _automatic_codecs(extension: str) -> tuple[str | None, str | None, str | None]:
    table = {
        ".mp4": ("libx264", "aac", "mov_text"), ".m4v": ("libx264", "aac", "mov_text"),
        ".mov": ("libx264", "aac", "mov_text"), ".3gp": ("libx264", "aac", "mov_text"),
        ".3g2": ("libx264", "aac", "mov_text"), ".mkv": ("libx264", "aac", "ass"),
        ".webm": ("libvpx-vp9", "libopus", "webvtt"),
        ".avi": ("mpeg4", "libmp3lame", None), ".ts": ("libx264", "aac", None),
        ".mts": ("libx264", "aac", None), ".m2ts": ("libx264", "aac", None),
        ".mpeg": ("mpeg2video", "mp2", None), ".mpg": ("mpeg2video", "mp2", None),
        ".flv": ("flv", "libmp3lame", None), ".f4v": ("libx264", "aac", None),
        ".ogv": ("libtheora", "libvorbis", None), ".wmv": ("wmv2", "wmav2", None),
        ".asf": ("wmv2", "wmav2", None), ".mp3": (None, "libmp3lame", None),
        ".mp2": (None, "mp2", None), ".flac": (None, "flac", None),
        ".wav": (None, "pcm_s16le", None), ".aif": (None, "pcm_s16be", None),
        ".aiff": (None, "pcm_s16be", None), ".ogg": (None, "libvorbis", None),
        ".oga": (None, "libvorbis", None), ".opus": (None, "libopus", None),
        ".m4a": (None, "aac", None), ".aac": (None, "aac", None),
        ".alac": (None, "alac", None), ".mka": (None, "flac", None),
        ".wma": (None, "wmav2", None),
    }
    try:
        return table[extension]
    except KeyError as exc:
        raise MediaTranscodeError(
            f"unsupported output extension: {extension or '(none)'}") from exc


def _quality_options(codec: str | None, preset: str, *, audio: bool = False) -> list[str]:
    if codec in {None, "copy"}:
        return []
    if audio:
        if codec in {"flac", "alac", "pcm_s16le", "pcm_s16be"}:
            return []
        if codec == "libvorbis":
            return ["-q:a", {"high": "8", "small": "3"}.get(preset, "6")]
        return ["-b:a", {"high": "256k", "small": "96k"}.get(preset, "192k")]
    if codec == "libx264":
        if preset == "lossless":
            return ["-preset", "medium", "-qp", "0", "-pix_fmt", "yuv420p"]
        return ["-preset", "medium", "-crf",
                {"high": "16", "small": "28"}.get(preset, "20"),
                "-pix_fmt", "yuv420p"]
    if codec == "libvpx-vp9":
        return ["-crf", {"high": "22", "small": "36"}.get(preset, "30"),
                "-b:v", "0", "-row-mt", "1"]
    if codec in {"mpeg4", "mjpeg"}:
        return ["-q:v", {"high": "2", "small": "7"}.get(preset, "4")]
    return []


def _duration_seconds(probe: dict[str, Any]) -> float:
    values = [probe.get("format", {}).get("duration")]
    values.extend(item.get("duration") for item in probe.get("streams", [])
                  if isinstance(item, dict))
    durations = []
    for value in values:
        try:
            parsed = float(value)
            if parsed > 0:
                durations.append(parsed)
        except (TypeError, ValueError):
            pass
    return max(durations, default=0.0)


def build_transcode_command(source: str | Path, destination: str | Path, *,
                            preset: str = "balanced", video_codec: str = "auto",
                            audio_codec: str = "auto", subtitle_mode: str = "auto",
                            all_tracks: bool = True,
                            preserve_metadata: bool = True) -> tuple[list[str], dict]:
    """Build one mapped FFmpeg command and return its verified source probe."""
    if preset not in MEDIA_PRESETS:
        raise MediaTranscodeError("unsupported media conversion preset")
    if subtitle_mode not in SUBTITLE_MODES:
        raise MediaTranscodeError("unsupported subtitle conversion mode")
    for name in (video_codec, audio_codec):
        if name != "auto" and not _CODEC_NAME.fullmatch(name):
            raise MediaTranscodeError("codec name is invalid")
    extension = Path(destination).suffix.lower()
    if extension not in MEDIA_OUTPUT_EXTENSIONS:
        raise MediaTranscodeError(f"unsupported output extension: {extension or '(none)'}")
    probe = _probe(source)
    videos, audios, subtitles = _playable_streams(probe)
    audio_only = extension in AUDIO_EXTENSIONS
    if not videos and not audios:
        raise MediaTranscodeError("source has no playable audio or video stream")
    if audio_only and not audios:
        raise MediaTranscodeError("audio output requires an audio stream")
    automatic_video, automatic_audio, automatic_subtitle = _automatic_codecs(extension)
    chosen_video = None if audio_only or not videos else (
        "copy" if preset == "remux" else
        automatic_video if video_codec == "auto" else video_codec)
    chosen_audio = None if not audios else (
        "copy" if preset == "remux" else
        automatic_audio if audio_codec == "auto" else audio_codec)
    if preset == "lossless" and video_codec == "auto" and chosen_video:
        if extension == ".mkv": chosen_video = "ffv1"
        elif extension in {".mov", ".mp4", ".m4v"}: chosen_video = "libx264"
        elif extension == ".avi": chosen_video = "ffv1"
        else: raise MediaTranscodeError(
            "lossless video preset requires MKV, MOV, MP4, M4V or AVI")
    if preset == "lossless" and audio_codec == "auto" and chosen_audio:
        if extension in {".mkv", ".mka", ".flac"}: chosen_audio = "flac"
        elif extension in {".mov", ".mp4", ".m4v", ".m4a", ".alac"}: chosen_audio = "alac"
        elif extension in {".wav", ".avi"}: chosen_audio = "pcm_s16le"
        elif extension in {".aif", ".aiff"}: chosen_audio = "pcm_s16be"
        else: raise MediaTranscodeError(
            "lossless audio preset is incompatible with the target container")
    command = [require_tool("ffmpeg"), "-nostdin", "-hide_banner", "-v", "error",
               "-y", "-i", str(source)]
    selected_videos = videos if all_tracks else videos[:1]
    # Elementary/single-program audio containers cannot represent several
    # independent audio streams. M4A and Matroska audio can do so.
    multitrack_audio_containers = {
        ".3g2", ".3gp", ".asf", ".avi", ".m4a", ".m4v", ".mka", ".mkv",
        ".mov", ".mp4", ".ts", ".mts", ".m2ts", ".webm", ".wmv",
    }
    selected_audios = (audios if all_tracks and extension in multitrack_audio_containers
                       else audios[:1])
    if chosen_video:
        for item in selected_videos:
            command += ["-map", f"0:{int(item['index'])}"]
    if chosen_audio:
        for item in selected_audios:
            command += ["-map", f"0:{int(item['index'])}"]
    subtitle_codec = None
    if (not audio_only and subtitles and subtitle_mode != "drop"
            and automatic_subtitle is not None):
        for item in (subtitles if all_tracks else subtitles[:1]):
            command += ["-map", f"0:{int(item['index'])}"]
        subtitle_codec = ("copy" if subtitle_mode == "copy" or preset == "remux"
                          else automatic_subtitle)
    if extension == ".mkv" and all_tracks:
        command += ["-map", "0:t?", "-c:t", "copy"]
    # Chapters are not valid in elementary/single-program audio outputs and
    # some muxers interpret them as an additional data stream.
    if preserve_metadata:
        command += ["-map_metadata", "0"]
        if not audio_only or extension in {".m4a", ".mka"}:
            command += ["-map_chapters", "0"]
        else:
            command += ["-map_chapters", "-1"]
    else:
        command += ["-map_metadata", "-1", "-map_chapters", "-1"]
    if chosen_video:
        command += ["-c:v", chosen_video] + _quality_options(chosen_video, preset)
    else: command += ["-vn"]
    if chosen_audio:
        command += ["-c:a", chosen_audio] + _quality_options(chosen_audio, preset, audio=True)
        # The legacy FLV muxer only accepts a small fixed sample-rate set for
        # MP3. Normalize unusual source rates (for example 16 kHz speech) so
        # otherwise valid inputs do not fail while the header is written.
        if ((extension == ".flv" and chosen_audio == "libmp3lame")
                or chosen_audio == "mp2"):
            command += ["-ar:a", "44100"]
    else: command += ["-an"]
    command += ["-c:s", subtitle_codec] if subtitle_codec else ["-sn"]
    command += ["-dn", "-progress", "pipe:1", "-nostats"]
    # ALAC is a codec rather than a standalone container. Keep the friendly
    # .alac target while explicitly using its standard MP4 audio envelope.
    if extension == ".alac":
        command += ["-f", "ipod"]
    command += [str(destination)]
    return command, probe


def transcode_media(source: str | Path, destination: str | Path, *,
                    preset: str = "balanced", video_codec: str = "auto",
                    audio_codec: str = "auto", subtitle_mode: str = "auto",
                    all_tracks: bool = True, preserve_metadata: bool = True,
                    cancel: Any | None = None,
                    progress: Callable[[float], None] | None = None) -> dict:
    """Transcode without exposing a partial destination; verify before publish."""
    source_path = Path(source).expanduser().resolve()
    destination_path = Path(destination).expanduser().resolve()
    if not source_path.is_file():
        raise MediaTranscodeError(f"input media does not exist: {source_path}")
    if source_path == destination_path:
        raise MediaTranscodeError("conversion output must differ from source")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination_path.stem}.", suffix=destination_path.suffix,
        dir=destination_path.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    command, source_probe = build_transcode_command(
        source_path, temporary, preset=preset, video_codec=video_codec,
        audio_codec=audio_codec, subtitle_mode=subtitle_mode,
        all_tracks=all_tracks, preserve_metadata=preserve_metadata)
    duration = _duration_seconds(source_probe)
    if progress: progress(0.0)
    try:
        with tempfile.TemporaryFile(mode="w+b") as errors:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
            assert process.stdout is not None
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            buffer = b""
            while process.poll() is None:
                if cancel is not None and getattr(cancel, "is_set", lambda: False)():
                    process.terminate()
                    try: process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait(timeout=2)
                    raise CasuCancelled("conversion cancelled")
                for key, _mask in selector.select(timeout=0.1):
                    block = os.read(key.fd, 65536)
                    if not block: continue
                    buffer += block
                    lines = buffer.split(b"\n"); buffer = lines.pop()
                    for line in lines:
                        if not line.startswith(b"out_time_us=") or not progress or duration <= 0:
                            continue
                        try: seconds = int(line.split(b"=", 1)[1]) / 1_000_000
                        except ValueError: continue
                        progress(min(0.98, max(0.0, seconds / duration)))
            selector.close()
            returncode = process.wait()
            if returncode:
                end = errors.seek(0, os.SEEK_END)
                errors.seek(max(0, end - 64 * 1024))
                detail = errors.read().decode("utf-8", errors="replace").strip().splitlines()
                raise MediaTranscodeError(detail[-1] if detail else
                                          f"FFmpeg failed with exit code {returncode}")
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            raise MediaTranscodeError("FFmpeg produced an empty output")
        output_probe = _probe(temporary)
        output_video, output_audio, _subtitles = _playable_streams(output_probe)
        if not output_video and not output_audio:
            raise MediaTranscodeError("converted output has no playable stream")
        os.replace(temporary, destination_path)
        if progress: progress(1.0)
        return output_probe
    except BaseException:
        try: temporary.unlink()
        except FileNotFoundError: pass
        raise
