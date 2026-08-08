"""Deterministic subtitle and chapter payloads for CASUNAT2."""
from __future__ import annotations

import json
from dataclasses import dataclass


class TextPayloadError(ValueError):
    pass


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class SubtitlePacket:
    start_pts: int
    end_pts: int
    text: str
    language: str = "und"
    format: str = "text"


def encode_subtitle_packet(packet: SubtitlePacket) -> bytes:
    if packet.end_pts < packet.start_pts:
        raise TextPayloadError("subtitle end_pts precedes start_pts")
    if not packet.text:
        raise TextPayloadError("subtitle text must not be empty")
    return _json_bytes({"version": 1, "start_pts": packet.start_pts,
                        "end_pts": packet.end_pts, "text": packet.text,
                        "language": packet.language, "format": packet.format})


def decode_subtitle_packet(payload: bytes) -> SubtitlePacket:
    try:
        value = json.loads(payload)
        if value.get("version") != 1:
            raise ValueError
        packet = SubtitlePacket(int(value["start_pts"]), int(value["end_pts"]),
                                str(value["text"]), str(value.get("language", "und")),
                                str(value.get("format", "text")))
        if packet.end_pts < packet.start_pts or not packet.text:
            raise ValueError
        return packet
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise TextPayloadError("invalid subtitle payload") from exc


def encode_chapter_table(chapters: list[dict]) -> bytes:
    normalized = []
    for chapter in chapters:
        try:
            start = int(chapter["start_pts"]); end = int(chapter["end_pts"])
            title = str(chapter["title"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TextPayloadError("invalid chapter") from exc
        if end < start or not title:
            raise TextPayloadError("invalid chapter bounds/title")
        normalized.append({"start_pts": start, "end_pts": end, "title": title,
                           "language": str(chapter.get("language", "und"))})
    return _json_bytes({"version": 1, "chapters": normalized})


def decode_chapter_table(payload: bytes) -> list[dict]:
    try:
        value = json.loads(payload)
        if value.get("version") != 1 or not isinstance(value["chapters"], list):
            raise ValueError
        result = []
        for chapter in value["chapters"]:
            start = int(chapter["start_pts"]); end = int(chapter["end_pts"])
            title = str(chapter["title"])
            if end < start or not title:
                raise ValueError
            result.append({"start_pts": start, "end_pts": end, "title": title,
                           "language": str(chapter.get("language", "und"))})
        return result
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise TextPayloadError("invalid chapter table") from exc
