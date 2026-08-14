# SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
# SPDX-FileCopyrightText: 2026 Lino Casu
"""Behavior tests for the CASU MP5 enhanced container."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
from pathlib import Path

import pytest

from casu import mp5
from casu.filetypes import CASUMP5, detect_casu_kind
from casu.mp5.converter import _attachment_payload
from casu.mp5.format import ChunkType
from casu.mp5.reader import (Mp5Error, extract_attachment, read_mp5,
                             verify_mp5)
from casu.mp5.writer import write_mp5


def _make_small_clip(tmp_path: Path) -> Path:
    """Generate a 1-second audio/video clip so envelope tests stay fast."""
    clip = tmp_path / "clip-source.mp4"
    import subprocess
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         "testsrc=duration=1:size=128x96:rate=10",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
         "-shortest", str(clip)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return clip


def _container_with_attachment(payload: bytes, filename: str = "inner.bin",
                               parts: int = 1, tmp_path: Path | None = None,
                               name: str = "demo.mp5") -> Path:
    chunks: list[tuple[ChunkType, int, int, bytes]] = [
        (ChunkType.STREAM_CONFIG, 0, 0,
         json.dumps({"stream_id": 0, "type": "video"}).encode("utf-8")),
    ]
    digest = hashlib.sha256()
    piece = max(1, len(payload) // parts)
    for index in range(parts):
        data = payload[index * piece:(index + 1) * piece] if index < parts - 1 else payload[index * piece:]
        digest.update(data)
        chunks.append((ChunkType.ATTACHMENT, 0, index,
                       _attachment_payload(filename, index, parts, data)))
    integrity = {"attachment_sha256": digest.hexdigest(),
                 "attachment_parts": parts}
    chunks.append((ChunkType.INTEGRITY_TABLE, 0, 0,
                   json.dumps(integrity).encode("utf-8")))
    chunks.append((ChunkType.END, 0, 0, b""))
    target = (tmp_path or Path(".")) / name
    return write_mp5(target, {"format": {"kind": "CASU MP5"}, "source": {}},
                     chunks)


def test_detect_casu_kind_recognizes_mp5_magic(tmp_path):
    target = tmp_path / "sample.mp5"
    target.write_bytes(b"CASUMP5\x00" + b"\x00" * 64)
    assert detect_casu_kind(target) == CASUMP5


def test_roundtrip_single_part(tmp_path):
    payload = os.urandom(4096)
    container = _container_with_attachment(payload, tmp_path=tmp_path)
    assert detect_casu_kind(container) == CASUMP5
    filename, data = extract_attachment(container)
    assert filename == "inner.bin"
    assert data == payload
    assert verify_mp5(container) == []


def test_roundtrip_multi_part_reassembles_in_order(tmp_path):
    payload = os.urandom(10_000)
    container = _container_with_attachment(payload, parts=3,
                                           tmp_path=tmp_path)
    parsed = read_mp5(container)
    attachment_chunks = [chunk for chunk in parsed.chunks
                         if chunk[0] == ChunkType.ATTACHMENT]
    assert len(attachment_chunks) == 3
    filename, data = extract_attachment(container)
    assert data == payload


def test_corrupted_attachment_payload_fails_verification(tmp_path):
    payload = os.urandom(2048)
    container = _container_with_attachment(payload, tmp_path=tmp_path)
    raw = bytearray(container.read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    container.write_bytes(bytes(raw))
    issues = verify_mp5(container)
    assert issues, "corruption must be reported"


def test_missing_attachment_is_reported(tmp_path):
    chunks = [(ChunkType.STREAM_CONFIG, 0, 0, b"{}"),
              (ChunkType.END, 0, 0, b"")]
    target = write_mp5(tmp_path / "empty.mp5", {"format": {}}, chunks)
    issues = verify_mp5(target)
    assert any("attachment" in issue for issue in issues)


def test_wrong_magic_rejected(tmp_path):
    target = tmp_path / "not-mp5.bin"
    target.write_bytes(b"CASUMP9\x00" + b"\x00" * 32)
    with pytest.raises(Mp5Error):
        read_mp5(target)
    assert detect_casu_kind(target) is None


def test_truncated_file_rejected(tmp_path):
    payload = os.urandom(1024)
    container = _container_with_attachment(payload, tmp_path=tmp_path)
    raw = container.read_bytes()
    container.write_bytes(raw[: len(raw) // 2])
    with pytest.raises(Mp5Error):
        extract_attachment(container)


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="ffmpeg unavailable")
def test_convert_to_mp5_produces_playable_verified_envelope(tmp_path):
    source = _make_small_clip(tmp_path)
    output = tmp_path / "clip.mp5"
    produced = mp5.convert_to_mp5(source, output)
    assert produced == output.resolve()
    assert detect_casu_kind(produced) == CASUMP5
    assert verify_mp5(produced) == []
    filename, data = extract_attachment(produced)
    assert filename == source.name
    assert hashlib.sha256(data).hexdigest() == hashlib.sha256(
        source.read_bytes()).hexdigest()
    parsed = read_mp5(produced)
    assert parsed.manifest["format"]["kind"] == "CASU MP5 enhanced container"
    assert any(chunk[0] == ChunkType.STREAM_CONFIG for chunk in parsed.chunks)


@pytest.mark.media
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="ffmpeg unavailable")
def test_player_routes_mp5_through_content_detection(tmp_path):
    import mpcasu_player
    source = _make_small_clip(tmp_path)
    output = tmp_path / "clip.mp5"
    mp5.convert_to_mp5(source, output)
    assert mpcasu_player.detect_local_playback_kind(output) == CASUMP5
    renamed = tmp_path / "clip.dat"
    shutil.copy(output, renamed)
    assert mpcasu_player.detect_local_playback_kind(renamed) == CASUMP5
