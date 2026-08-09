"""Source-resolution FFmpeg decoder boundary for Gate 2.

The adapter deliberately emits the decoder's presentation timestamps and the
native plane layout instead of an fps-filtered preview.  Unsupported pixel
formats fail closed rather than silently converting to a lossy analysis plane.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .canonical import canonical_frame
from .model import StrictFrame
from casu.probe import ProbeError, run_json


class StrictDecoderError(RuntimeError):
    pass


@dataclass(frozen=True)
class _Format:
    width: int
    height: int
    pixel_format: str
    planes: tuple[tuple[int, int], ...]
    dtype: str
    bytes_per_sample: int

    @property
    def frame_bytes(self) -> int:
        return sum(h * w * self.bytes_per_sample for h, w in self.planes)


_FORMATS = {
    "gray": lambda w, h: _Format(w, h, "gray", ((h, w),), "uint8", 1),
    "gray8": lambda w, h: _Format(w, h, "gray8", ((h, w),), "uint8", 1),
    "gray16le": lambda w, h: _Format(w, h, "gray16le", ((h, w),), "<u2", 2),
    "rgb24": lambda w, h: _Format(w, h, "rgb24", ((h, w * 3),), "uint8", 1),
    "bgr24": lambda w, h: _Format(w, h, "bgr24", ((h, w * 3),), "uint8", 1),
    "rgba": lambda w, h: _Format(w, h, "rgba", ((h, w * 4),), "uint8", 1),
    "bgra": lambda w, h: _Format(w, h, "bgra", ((h, w * 4),), "uint8", 1),
    "argb": lambda w, h: _Format(w, h, "argb", ((h, w * 4),), "uint8", 1),
    "abgr": lambda w, h: _Format(w, h, "abgr", ((h, w * 4),), "uint8", 1),
    "yuv420p": lambda w, h: _Format(w, h, "yuv420p", ((h, w), ((h + 1)//2, (w + 1)//2),
                                                        ((h + 1)//2, (w + 1)//2)), "uint8", 1),
    "yuv420p10le": lambda w, h: _Format(w, h, "yuv420p10le", ((h, w), ((h + 1)//2, (w + 1)//2),
                                                                  ((h + 1)//2, (w + 1)//2)), "<u2", 2),
    "yuv420p12le": lambda w, h: _Format(w, h, "yuv420p12le", ((h, w), ((h + 1)//2, (w + 1)//2),
                                                                  ((h + 1)//2, (w + 1)//2)), "<u2", 2),
    "yuv420p16le": lambda w, h: _Format(w, h, "yuv420p16le", ((h, w), ((h + 1)//2, (w + 1)//2),
                                                                  ((h + 1)//2, (w + 1)//2)), "<u2", 2),
    "yuv422p": lambda w, h: _Format(w, h, "yuv422p", ((h, w), (h, (w + 1)//2),
                                                        (h, (w + 1)//2)), "uint8", 1),
    "yuv422p10le": lambda w, h: _Format(w, h, "yuv422p10le", ((h, w), (h, (w + 1)//2),
                                                                  (h, (w + 1)//2)), "<u2", 2),
    "yuv422p12le": lambda w, h: _Format(w, h, "yuv422p12le", ((h, w), (h, (w + 1)//2),
                                                                  (h, (w + 1)//2)), "<u2", 2),
    "yuv422p16le": lambda w, h: _Format(w, h, "yuv422p16le", ((h, w), (h, (w + 1)//2),
                                                                  (h, (w + 1)//2)), "<u2", 2),
    "yuva420p": lambda w, h: _Format(w, h, "yuva420p", ((h, w), ((h + 1)//2, (w + 1)//2),
                                                        ((h + 1)//2, (w + 1)//2), (h, w)), "uint8", 1),
    "yuva420p10le": lambda w, h: _Format(w, h, "yuva420p10le", ((h, w), ((h + 1)//2, (w + 1)//2),
                                                                  ((h + 1)//2, (w + 1)//2), (h, w)), "<u2", 2),
    "yuva420p12le": lambda w, h: _Format(w, h, "yuva420p12le", ((h, w), ((h + 1)//2, (w + 1)//2),
                                                                  ((h + 1)//2, (w + 1)//2), (h, w)), "<u2", 2),
    "yuva420p16le": lambda w, h: _Format(w, h, "yuva420p16le", ((h, w), ((h + 1)//2, (w + 1)//2),
                                                                  ((h + 1)//2, (w + 1)//2), (h, w)), "<u2", 2),
    "yuv444p": lambda w, h: _Format(w, h, "yuv444p", ((h, w), (h, w), (h, w)), "uint8", 1),
    "yuv444p10le": lambda w, h: _Format(w, h, "yuv444p10le", ((h, w), (h, w), (h, w)), "<u2", 2),
    "yuv444p12le": lambda w, h: _Format(w, h, "yuv444p12le", ((h, w), (h, w), (h, w)), "<u2", 2),
    "yuv444p16le": lambda w, h: _Format(w, h, "yuv444p16le", ((h, w), (h, w), (h, w)), "<u2", 2),
    "gbrp": lambda w, h: _Format(w, h, "gbrp", ((h, w), (h, w), (h, w)), "uint8", 1),
    "gbrp10le": lambda w, h: _Format(w, h, "gbrp10le", ((h, w), (h, w), (h, w)), "<u2", 2),
    "gbrp12le": lambda w, h: _Format(w, h, "gbrp12le", ((h, w), (h, w), (h, w)), "<u2", 2),
    "gbrp16le": lambda w, h: _Format(w, h, "gbrp16le", ((h, w), (h, w), (h, w)), "<u2", 2),
    "rgba64le": lambda w, h: _Format(w, h, "rgba64le", ((h, w * 4),), "<u2", 2),
}


def _require_tools() -> None:
    if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
        raise StrictDecoderError("ffprobe and ffmpeg are required for source-resolution decoding")


def _probe(path: Path, stream_index: int) -> tuple[_Format, int, int, list[dict], dict]:
    _require_tools()
    command = [
        "ffprobe", "-v", "error", "-select_streams", f"v:{stream_index}",
        "-show_entries",
        "stream=width,height,pix_fmt,time_base,color_space,color_transfer,color_primaries,color_range,chroma_location:"
        "frame=best_effort_timestamp,pts,pkt_duration,duration,width,height,pix_fmt,color_space,color_transfer,color_primaries,color_range,chroma_location",
        "-of", "json", str(path),
    ]
    try:
        data = run_json(command)
    except ProbeError as exc:
        raise StrictDecoderError(f"unable to probe source video: {path}") from exc
    streams = data.get("streams") or []
    if not streams:
        raise StrictDecoderError("source has no selected video stream")
    stream = streams[0]
    width, height = int(stream.get("width", 0)), int(stream.get("height", 0))
    pix_fmt = str(stream.get("pix_fmt", ""))
    if width <= 0 or height <= 0 or pix_fmt not in _FORMATS:
        raise StrictDecoderError(f"unsupported native source format: {pix_fmt!r} {width}x{height}")
    fmt = _FORMATS[pix_fmt](width, height)
    if width > 32768 or height > 32768 or fmt.frame_bytes > 512 * 1024 * 1024:
        raise StrictDecoderError("source video exceeds decoded frame resource limits")
    time_base = str(stream.get("time_base", "0/1"))
    num, den = (int(value) for value in time_base.split("/", 1))
    if den <= 0:
        raise StrictDecoderError("source stream has invalid time base")
    frames = data.get("frames") or []
    return fmt, num, den, frames, stream


def _iter_ffmpeg_frames(path: str | Path, *, stream_index: int = 0,
                        max_frames: int | None = None) -> Iterator[StrictFrame]:
    """CLI fallback adapter used when the optional PyAV binding is absent."""
    source = Path(path)
    fmt, num, den, frame_info, stream = _probe(source, stream_index)
    if max_frames is not None and max_frames < 0:
        raise ValueError("max_frames must be non-negative")
    command = ["ffmpeg", "-v", "error", "-i", str(source), "-map", f"0:v:{stream_index}",
               "-an", "-sn", "-dn", "-vsync", "0", "-f", "rawvideo",
               "-pix_fmt", fmt.pixel_format, "pipe:1"]
    error_stream = tempfile.TemporaryFile(mode="w+b")
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=error_stream)
    stopped_early = False
    try:
        assert process.stdout is not None
        for index, info in enumerate(frame_info):
            if max_frames is not None and index >= max_frames:
                stopped_early = True
                break
            frame_width = int(info.get("width", fmt.width))
            frame_height = int(info.get("height", fmt.height))
            frame_format = str(info.get("pix_fmt", fmt.pixel_format))
            if (frame_width, frame_height, frame_format) != (fmt.width, fmt.height, fmt.pixel_format):
                raise StrictDecoderError(
                    "mid-stream native format change requires a decoder restart/key state")
            payload = process.stdout.read(fmt.frame_bytes)
            if len(payload) != fmt.frame_bytes:
                raise StrictDecoderError("decoder ended before a complete source frame")
            offset = 0
            planes = []
            for height, width in fmt.planes:
                count = height * width * fmt.bytes_per_sample
                array = np.frombuffer(payload, dtype=fmt.dtype, count=height * width,
                                      offset=offset).reshape((height, width)).copy()
                planes.append(array)
                offset += count
            pts_text = info.get("best_effort_timestamp", info.get("pts"))
            if pts_text is None:
                raise StrictDecoderError("source frame has no presentation timestamp")
            pts = int(pts_text)
            metadata = {}
            for key in ("color_space", "color_transfer", "color_primaries", "color_range",
                        "chroma_location"):
                value = info.get(key, stream.get(key))
                if value not in (None, ""):
                    metadata[key] = str(value)
            duration_text = info.get("pkt_duration", info.get("duration"))
            duration_pts = int(duration_text) if duration_text not in (None, "N/A") else None
            frame = canonical_frame(tuple(planes), pixel_format=fmt.pixel_format,
                                    source_shape=(fmt.height, fmt.width), color_metadata=metadata)
            yield StrictFrame(pts, num, den, frame, duration_pts)
        if not stopped_early and process.stdout.read(1):
            raise StrictDecoderError("decoder produced more frames than the timestamp inventory")
    except GeneratorExit:
        # A caller may intentionally stop after enough frames. Closing the pipe
        # makes FFmpeg report EPIPE; this is cancellation, not decoder failure.
        stopped_early = True
        raise
    finally:
        if process.stdout:
            process.stdout.close()
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        error_stream.seek(0)
        error = error_stream.read().decode("utf-8", errors="replace").strip()
        error_stream.close()
        if not stopped_early and process.returncode not in (0, None) and not error.startswith("av_interleaved_write_frame"):
            raise StrictDecoderError(f"source decoder failed: {error or process.returncode}")


def _iter_pyav_frames(path: str | Path, *, stream_index: int = 0,
                      max_frames: int | None = None) -> Iterator[StrictFrame]:
    """Library-level libav adapter preserving active plane bytes and frame PTS."""
    try:
        import av  # type: ignore[import-not-found]
    except ImportError as exc:
        raise StrictDecoderError("PyAV source adapter is unavailable") from exc
    if max_frames is not None and max_frames < 0:
        raise ValueError("max_frames must be non-negative")
    try:
        container = av.open(str(Path(path)))
    except Exception as exc:
        raise StrictDecoderError(f"unable to open source through PyAV: {path}") from exc
    try:
        videos = list(container.streams.video)
        if stream_index < 0 or stream_index >= len(videos):
            raise StrictDecoderError("source has no selected video stream")
        stream = videos[stream_index]
        for index, decoded in enumerate(container.decode(stream)):
            if max_frames is not None and index >= max_frames:
                break
            pixel_format = str(decoded.format.name)
            factory = _FORMATS.get(pixel_format)
            if factory is None:
                raise StrictDecoderError(
                    f"unsupported native source format: {pixel_format!r} "
                    f"{decoded.width}x{decoded.height}")
            fmt = factory(int(decoded.width), int(decoded.height))
            if len(decoded.planes) != len(fmt.planes):
                raise StrictDecoderError("PyAV returned an unexpected native plane count")
            planes = []
            for plane, (height, width) in zip(decoded.planes, fmt.planes):
                active_bytes = width * fmt.bytes_per_sample
                line_size = int(plane.line_size)
                if line_size < active_bytes:
                    raise StrictDecoderError("PyAV plane stride is below active row width")
                padded = memoryview(plane)
                active = b"".join(bytes(padded[row * line_size:row * line_size + active_bytes])
                                   for row in range(height))
                planes.append(np.frombuffer(active, dtype=fmt.dtype).reshape(height, width).copy())
            if decoded.pts is None:
                raise StrictDecoderError("source frame has no presentation timestamp")
            time_base = decoded.time_base or stream.time_base
            if time_base is None or int(time_base.denominator) <= 0:
                raise StrictDecoderError("source stream has invalid time base")
            metadata = {}
            for output, attribute in (("color_space", "colorspace"),
                                      ("color_range", "color_range"),
                                      ("color_primaries", "color_primaries"),
                                      ("color_transfer", "color_trc"),
                                      ("chroma_location", "chroma_location")):
                value = getattr(decoded, attribute, None)
                if value not in (None, "", 0):
                    metadata[output] = str(value)
            frame = canonical_frame(tuple(planes), pixel_format=pixel_format,
                                    source_shape=(fmt.height, fmt.width),
                                    color_metadata=metadata)
            duration = getattr(decoded, "duration", None)
            yield StrictFrame(int(decoded.pts), int(time_base.numerator),
                              int(time_base.denominator), frame,
                              int(duration) if duration is not None else None)
    except StrictDecoderError:
        raise
    except Exception as exc:
        raise StrictDecoderError(f"PyAV source decode failed: {exc}") from exc
    finally:
        container.close()


def iter_source_frames(path: str | Path, *, stream_index: int = 0,
                       max_frames: int | None = None,
                       engine: str = "auto") -> Iterator[StrictFrame]:
    """Yield source frames through PyAV when available, with a tested CLI fallback."""
    if engine not in {"auto", "pyav", "ffmpeg"}:
        raise ValueError("engine must be auto, pyav or ffmpeg")
    if engine in {"auto", "pyav"}:
        try:
            import av  # type: ignore[import-not-found]  # noqa: F401
        except ImportError:
            if engine == "pyav":
                raise StrictDecoderError("PyAV source adapter is unavailable")
        else:
            yield from _iter_pyav_frames(path, stream_index=stream_index,
                                         max_frames=max_frames)
            return
    yield from _iter_ffmpeg_frames(path, stream_index=stream_index,
                                   max_frames=max_frames)


def validate_source_frames(frames: Iterable[StrictFrame]) -> list[StrictFrame]:
    values = list(frames)
    if any(values[index].time.fraction > values[index + 1].time.fraction
           for index in range(len(values) - 1)):
        raise ValueError("source PTS must be monotonic in presentation order")
    return values
