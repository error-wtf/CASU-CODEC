from __future__ import annotations

import functools
import http.server
import socket
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
        # Loopback source with the SSRF guard explicitly lifted (local test
        # server) — exercises the bounded-fetch path itself.
        catalog = epg.fetch_document(
            f"http://127.0.0.1:{server.server_address[1]}/channels.m3u",
            max_bytes=epg.MAX_PLAYLIST_BYTES, allow_private_target=True)
        assert parse_m3u(catalog).channels[0].epg_id == "one"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
    with pytest.raises(EpgError, match="HTTP or HTTPS"):
        fetch_m3u("file:///etc/passwd")


def test_remote_fetch_refuses_private_and_reserved_targets():
    """SSRF guard: loopback/private/link-local/metadata targets are refused."""
    for url in (
        "http://127.0.0.1/guide.xml",
        "http://127.0.0.1:8080/guide.xml",
        "http://localhost/guide.xml",
        "http://10.0.0.5/playlist.m3u",
        "http://10.0.0.5:8080/playlist.m3u",
        "http://172.16.0.1/x.m3u",
        "http://172.31.255.254/x.m3u",
        "http://192.168.1.10/x.m3u",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.64.0.1/x.m3u",
        "http://0.0.0.0/x.m3u",
        "http://[::1]/guide.xml",
        "http://[fe80::1]/guide.xml",
        "http://[fd12:3456:789a:1::1]/guide.xml",
        "http://[fc00::1]/guide.xml",
        "http://[::ffff:127.0.0.1]/guide.xml",
        "http://[::ffff:169.254.169.254]/guide.xml",
        "https://user:secret@127.0.0.1/guide.xml",
    ):
        with pytest.raises(EpgError):
            fetch_m3u(url)
        with pytest.raises(EpgError):
            epg.fetch_xmltv(url)


def test_remote_fetch_refuses_private_dns_name(monkeypatch):
    """A hostname whose DNS record points inward is refused (rebinding)."""
    def fake_getaddrinfo(host, port, *args, **kwargs):
        assert host == "rebind.example"
        family = socket.AF_INET
        return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                 ("10.0.0.7", port))]
    monkeypatch.setattr(epg.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(EpgError, match="private network"):
        fetch_m3u("http://rebind.example/playlist.m3u")


def test_remote_fetch_allows_public_dns_name(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        family = socket.AF_INET
        return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                 ("93.184.216.34", port))]
    monkeypatch.setattr(epg.socket, "getaddrinfo", fake_getaddrinfo)

    class Unreachable(OSError):
        pass
    monkeypatch.setattr(epg.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(Unreachable()))
    # Public DNS target passes the guard; the (mocked) fetch then fails as a
    # plain network error — NOT as an SSRF rejection.
    with pytest.raises(EpgError, match="could not download catalog"):
        fetch_m3u("http://public.example/playlist.m3u")
