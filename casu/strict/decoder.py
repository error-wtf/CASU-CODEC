"""Source-resolution FFmpeg decoder boundary for Gate 2.

The adapter deliberately emits the decoder's presentation timestamps and the
native plane layout instead of an fps-filtered preview.  Unsupported pixel
formats fail closed rather than silently converting to a lossy analysis plane.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .canonical import canonical_frame
from .model import StrictFrame


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
    "gray8": lambda w, h: _Format(w, h, "gray8", ((h, w),), "uint8", 1),
    "gray16le": lambda w, h: _Format(w, h, "gray16le", ((h, w),), "<u2", 2),
    "rgb24": lambda w, h: _Format(w, h, "rgb24", ((h, w * 3),), "uint8", 1),
    "rgba": lambda w, h: _Format(w, h, "rgba", ((h, w * 4),), "uint8", 1),
    "yuv420p": lambda w, h: _Format(w, h, "yuv420p", ((h, w), ((h + 1)//2, (w + 1)//2),
                                                        ((h + 1)//2, (w + 1)//2)), "uint8", 1),
    "yuv420p10le": lambda w, h: _Format(w, h, "yuv420p10le", ((h, w), ((h + 1)//2, (w + 1)//2),
                                                                  ((h + 1)//2, (w + 1)//2)), "<u2", 2),
    "yuv420p12le": lambda w, h: _Format(w, h, "yuv420p12le", ((h, w), ((h + 1)//2, (w + 1)//2),
                                                                  ((h + 1)//2, (w + 1)//2)), "<u2", 2),
    "yuva420p": lambda w, h: _Format(w, h, "yuva420p", ((h, w), ((h + 1)//2, (w + 1)//2),
                                                        ((h + 1)//2, (w + 1)//2), (h, w)), "uint8", 1),
    "yuva420p10le": lambda w, h: _Format(w, h, "yuva420p10le", ((h, w), ((h + 1)//2, (w + 1)//2),
                                                                  ((h + 1)//2, (w + 1)//2), (h, w)), "<u2", 2),
    "yuv444p": lambda w, h: _Format(w, h, "yuv444p", ((h, w), (h, w), (h, w)), "uint8", 1),
    "yuv444p10le": lambda w, h: _Format(w, h, "yuv444p10le", ((h, w), (h, w), (h, w)), "<u2", 2),
    "yuv444p12le": lambda w, h: _Format(w, h, "yuv444p12le", ((h, w), (h, w), (h, w)), "<u2", 2),
    "gbrp": lambda w, h: _Format(w, h, "gbrp", ((h, w), (h, w), (h, w)), "uint8", 1),
    "gbrp10le": lambda w, h: _Format(w, h, "gbrp10le", ((h, w), (h, w), (h, w)), "<u2", 2),
    "rgba64le": lambda w, h: _Format(w, h, "rgba64le", ((h, w * 4),), "<u2", 2),
}


def _require_tools() -> None:
    if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
        raise StrictDecoderError("ffprobe and ffmpeg are required for source-resolution decoding")


def _probe(path: Path, stream_index: int) -> tuple[_Format, int, int, list[dict], dict]:
    _require_tools()
    command = ["ffprobe", "-v", "error", "-select_streams", f"v:{stream_index}",
               "-show_streams", "-show_frames", "-of", "json", str(path)]
    try:
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        data = json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise StrictDecoderError(f"unable to probe source video: {path}") from exc
    streams = data.get("streams") or []
    if not streams:
        raise StrictDecoderError("source has no selected video stream")
    stream = streams[0]
    width, height = int(stream.get("width", 0)), int(stream.get("height", 0))
    pix_fmt = str(stream.get("pix_fmt", ""))
    if width <= 0 or height <= 0 or pix_fmt not in _FORMATS:
        raise StrictDecoderError(f"unsupported native source format: {pix_fmt!r} {width}x{height}")
    time_base = str(stream.get("time_base", "0/1"))
    num, den = (int(value) for value in time_base.split("/", 1))
    if den <= 0:
        raise StrictDecoderError("source stream has invalid time base")
    frames = data.get("frames") or []
    return _FORMATS[pix_fmt](width, height), num, den, frames, stream


def iter_source_frames(path: str | Path, *, stream_index: int = 0,
                       max_frames: int | None = None) -> Iterator[StrictFrame]:
    """Yield native decoded planes paired with source presentation timestamps."""
    source = Path(path)
    fmt, num, den, frame_info, stream = _probe(source, stream_index)
    command = ["ffmpeg", "-v", "error", "-i", str(source), "-map", f"0:v:{stream_index}",
               "-an", "-sn", "-dn", "-vsync", "0", "-f", "rawvideo",
               "-pix_fmt", fmt.pixel_format, "pipe:1"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        assert process.stdout is not None
        for index, info in enumerate(frame_info):
            if max_frames is not None and index >= max_frames:
                break
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
            metadata = {key: str(stream[key]) for key in
                        ("color_space", "color_transfer", "color_primaries", "color_range")
                        if stream.get(key) not in (None, "")}
            frame = canonical_frame(tuple(planes), pixel_format=fmt.pixel_format,
                                    source_shape=(fmt.height, fmt.width), color_metadata=metadata)
            yield StrictFrame(pts, num, den, frame)
    finally:
        if process.stdout:
            process.stdout.close()
        process.terminate()
        process.wait(timeout=5)


def validate_source_frames(frames: Iterable[StrictFrame]) -> list[StrictFrame]:
    values = list(frames)
    if any(values[index].timestamp_s > values[index + 1].timestamp_s
           for index in range(len(values) - 1)):
        raise ValueError("source PTS must be monotonic")
    return values
