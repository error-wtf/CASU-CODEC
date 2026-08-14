"""Bounded lossless CASUNAT2 attachment payload."""
from __future__ import annotations

import hashlib
import json
import struct
import zlib
from dataclasses import dataclass

from .jsonutil import StrictJsonError, strict_json_loads


_U32 = struct.Struct(">I")
MAX_ATTACHMENT_BYTES = 64 * 1024 * 1024
MAX_ATTACHMENT_METADATA_BYTES = 64 * 1024


class AttachmentPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class Attachment:
    filename: str
    media_type: str
    data: bytes
    sha256: str
    role: str | None = None


def encode_attachment(filename: str, media_type: str, data: bytes, *,
                      role: str | None = None) -> bytes:
    original_name = str(filename)
    name = original_name.replace("\\", "/").rsplit("/", 1)[-1]
    raw = bytes(data)
    media = str(media_type or "application/octet-stream")
    if (not name or name in {".", ".."} or name != original_name
            or len(name.encode("utf-8")) > 4096
            or len(media.encode("utf-8")) > 1024):
        raise AttachmentPayloadError("attachment filename must be a safe basename")
    if len(raw) > MAX_ATTACHMENT_BYTES:
        raise AttachmentPayloadError("attachment exceeds size limit")
    compressed = zlib.compress(raw, 9)
    meta = {"version": 1, "filename": name,
            "media_type": media,
            "raw_length": len(raw), "compressed_length": len(compressed),
            "compression": "zlib", "sha256": hashlib.sha256(raw).hexdigest()}
    if role is not None:
        normalized_role = str(role).strip()
        if not normalized_role or len(normalized_role) > 64:
            raise AttachmentPayloadError("attachment role is invalid")
        meta["role"] = normalized_role
    header = json.dumps(meta, sort_keys=True, separators=(",", ":"),
                        allow_nan=False).encode("utf-8")
    return _U32.pack(len(header)) + header + compressed


def decode_attachment(payload: bytes) -> Attachment:
    if len(payload) < _U32.size:
        raise AttachmentPayloadError("truncated attachment")
    length = _U32.unpack_from(payload)[0]
    if length > len(payload) - _U32.size or length > MAX_ATTACHMENT_METADATA_BYTES:
        raise AttachmentPayloadError("invalid attachment metadata length")
    try:
        meta = strict_json_loads(payload[_U32.size:_U32.size + length])
        expected = int(meta["raw_length"])
        if (meta.get("version") != 1 or meta.get("compression", "zlib") != "zlib"
                or expected < 0 or expected > MAX_ATTACHMENT_BYTES):
            raise ValueError
        compressed = payload[_U32.size + length:]
        if len(compressed) != int(meta["compressed_length"]):
            raise ValueError
        decoder = zlib.decompressobj()
        raw = decoder.decompress(compressed, expected + 1)
        if len(raw) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError
        filename = str(meta["filename"])
        media_type = str(meta["media_type"])
        if (filename != filename.replace("\\", "/").rsplit("/", 1)[-1]
                or filename in {"", ".", ".."}
                or len(filename.encode("utf-8")) > 4096
                or len(media_type.encode("utf-8")) > 1024):
            raise ValueError
        digest = str(meta["sha256"])
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError
        role_value = meta.get("role")
        if role_value is not None and (not isinstance(role_value, str)
                                       or not role_value.strip()
                                       or len(role_value) > 64):
            raise ValueError
        return Attachment(filename, media_type, raw, digest,
                          role_value)
    except (KeyError, TypeError, ValueError, StrictJsonError, zlib.error) as exc:
        raise AttachmentPayloadError("invalid attachment payload") from exc
