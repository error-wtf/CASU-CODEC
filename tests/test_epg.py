from __future__ import annotations

import functools
import http.server
import threading
from datetime import datetime, timezone

import pytest

import casu.epg as epg
from casu.epg import EpgError, fetch_m3u, parse_m3u, parse_xmltv


def test_extended_m3u_preserves_channel_epg_group_and_url():
    catalog = parse_m3u(b'''#EXTM3U x-tvg-url="https://guide.test/epg.xml"
#EXTINF:-1 tvg-id="news.de" tvg-name="News HD" tvg-logo="https://img.test/n.png" group-title="News",News Live
https://stream.test/live.m3u8
#EXTINF:-1 tvg-id="radio.de" group-title="Radio",Radio One
udp://@239.1.2.3:1234
''')
    assert catalog.epg_urls == ("https://guide.test/epg.xml",)
    assert [(item.name, item.epg_id, item.group) for item in catalog.channels] == [
        ("News Live", "news.de", "News"), ("Radio One", "radio.de", "Radio")]
    assert catalog.channels[1].url == "udp://@239.1.2.3:1234"


def test_m3u_resolves_local_relative_entries_and_bounds_lines(tmp_path, monkeypatch):
    catalog = parse_m3u("#EXTM3U\n#EXTINF:-1,Clip\nmedia/clip.mp4\n", base=tmp_path)
    assert catalog.channels[0].url == str((tmp_path / "media/clip.mp4").resolve())
    monkeypatch.setattr(epg, "MAX_LINE_BYTES", 8)
    with pytest.raises(EpgError, match="line exceeds"):
        parse_m3u("#EXTM3U\n" + "a" * 9)


def test_xmltv_now_next_and_invalid_entity_rejection():
    guide = parse_xmltv(b'''<?xml version="1.0" encoding="UTF-8"?>
<tv><channel id="news.de"><display-name>News HD</display-name></channel>
<programme start="20260813190000 +0200" stop="20260813200000 +0200" channel="news.de"><title>Evening News</title><desc>Headlines</desc><category>News</category></programme>
<programme start="20260813200000 +0200" stop="20260813210000 +0200" channel="news.de"><title>Documentary</title></programme></tv>''')
    now = datetime(2026, 8, 13, 17, 30, tzinfo=timezone.utc)
    current, following = guide.now_next("news.de", now=now)
    assert current and current.title == "Evening News"
    assert following and following.title == "Documentary"
    assert guide.channel_names["news.de"] == "News HD"
    with pytest.raises(EpgError, match="DTD/entities"):
        parse_xmltv(b'<!DOCTYPE tv [<!ENTITY x "bad">]><tv/>')


def test_remote_playlist_fetch_is_http_only_bounded_and_finite(tmp_path):
    (tmp_path / "channels.m3u").write_text(
        "#EXTM3U\n#EXTINF:-1 tvg-id=one,One\nhttps://stream.test/one\n",
        encoding="utf-8")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        catalog = fetch_m3u(
            f"http://127.0.0.1:{server.server_address[1]}/channels.m3u")
        assert catalog.channels[0].epg_id == "one"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
    with pytest.raises(EpgError, match="HTTP or HTTPS"):
        fetch_m3u("file:///etc/passwd")
