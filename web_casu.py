#!/usr/bin/env python3
"""Local, dependency-free launcher for the installed MPCASU web player."""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

from casu.epg import EpgError, MAX_XMLTV_BYTES, fetch_document
from casu.locations import (LocationResolutionError, is_youtube_url,
                            resolve_media_location)
from casu.search import SearchError, search_music, search_youtube
from casu.spotify import (SpotifyError, fetch_spotify_metadata, is_spotify_url,
                          spotify_playback_notice)

from casu.export import CasuExportError, export_casu


class WebPlayerError(RuntimeError):
    pass


MAX_UPLOAD_BYTES = 16 * 1024 * 1024 * 1024
MAX_SESSIONS = 64
NETWORK_SCHEMES = {"http", "https", "ftp", "ftps", "rtsp", "rtsps", "rtmp",
                   "rtmps", "rtp", "udp", "srt", "rist", "smb", "mmsh", "mmst"}


def _redacted_location(source: str | Path) -> str:
    text = str(source)
    try:
        parsed = urllib.parse.urlsplit(text)
    except ValueError:
        return text
    if not parsed.username and not parsed.password:
        return text
    host = parsed.hostname or ""
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port is not None:
        host += f":{port}"
    return urllib.parse.urlunsplit((parsed.scheme, host, parsed.path,
                                    parsed.query, parsed.fragment))


def _media_shape(source: str | Path) -> tuple[bool, bool]:
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_streams", "-of", "json",
            str(source),
        ], capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WebPlayerError(f"media probe failed: {exc}") from exc
    if result.returncode:
        detail = result.stderr.strip().splitlines()
        message = detail[-1] if detail else "FFmpeg cannot open this media"
        message = message.replace(str(source), _redacted_location(source))
        try:
            credentials = urllib.parse.urlsplit(str(source))
            for secret in (credentials.username, credentials.password):
                if secret:
                    message = message.replace(secret, "***")
        except ValueError:
            pass
        raise WebPlayerError(message)
    try:
        streams = json.loads(result.stdout).get("streams", [])
    except (json.JSONDecodeError, AttributeError) as exc:
        raise WebPlayerError("media probe returned invalid data") from exc
    video = any(item.get("codec_type") == "video"
                and not item.get("disposition", {}).get("attached_pic")
                for item in streams if isinstance(item, dict))
    audio = any(item.get("codec_type") == "audio"
                for item in streams if isinstance(item, dict))
    if not video and not audio:
        raise WebPlayerError("source has no playable audio or video stream")
    return video, audio


def _transcode_command(source: str | Path, *, video: bool, audio: bool,
                       output: str, target: str = "mp4") -> list[str]:
    if target not in {"mp4", "webm"}:
        raise WebPlayerError("unsupported browser transcode target")
    command = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(source),
               "-map", "0:v:0?", "-map", "0:a:0?"]
    if video:
        command += (["-c:v", "libvpx-vp9", "-deadline", "realtime",
                     "-cpu-used", "6", "-crf", "30", "-b:v", "0"]
                    if target == "webm" else
                    ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                     "-pix_fmt", "yuv420p"])
    else:
        command += ["-vn"]
    if audio:
        command += (["-c:a", "libopus", "-b:a", "160k"] if target == "webm"
                    else ["-c:a", "aac", "-b:a", "192k"])
    else:
        command += ["-an"]
    command += ["-sn", "-dn"]
    if output == "pipe:1":
        command += (["-cluster_time_limit", "1000", "-f", "webm", output]
                    if target == "webm" else
                    ["-movflags", "frag_keyframe+empty_moov+default_base_moof",
                     "-f", "mp4", output])
    else:
        if target == "mp4":
            command += ["-movflags", "+faststart"]
        command += ["-y", output]
    return command


class TranscodeStore:
    """Bounded temporary media owned by one loopback web-player server."""

    def __init__(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(prefix="mpcasu-web-")
        self.root = Path(self._temporary.name)
        self._lock = threading.Lock()
        self._sessions: dict[str, dict] = {}

    def close(self) -> None:
        self._temporary.cleanup()

    def _add(self, record: dict) -> str:
        with self._lock:
            while len(self._sessions) >= MAX_SESSIONS:
                oldest = min(self._sessions, key=lambda key:
                             self._sessions[key]["created"])
                stale = self._sessions.pop(oldest)
                path = stale.get("path")
                if isinstance(path, Path):
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
            token = secrets.token_urlsafe(24)
            record["created"] = time.monotonic()
            self._sessions[token] = record
            return token

    def get(self, token: str) -> dict | None:
        with self._lock:
            return self._sessions.get(token)

    def transcode_upload(self, handle, length: int, filename: str,
                         target: str = "mp4") -> tuple[str, str]:
        if length <= 0 or length > MAX_UPLOAD_BYTES:
            raise WebPlayerError("upload size is invalid or exceeds 16 GiB")
        suffix = Path(filename).suffix.lower()
        if len(suffix) > 16 or not all(char.isalnum() or char == "." for char in suffix):
            suffix = ".media"
        token = secrets.token_urlsafe(18)
        source = self.root / f"upload-{token}{suffix or '.media'}"
        destination: Path | None = None
        published = False
        try:
            remaining = length
            with source.open("wb") as output:
                while remaining:
                    block = handle.read(min(1024 * 1024, remaining))
                    if not block:
                        raise WebPlayerError("upload ended before Content-Length")
                    output.write(block)
                    remaining -= len(block)
            try:
                with source.open("rb") as candidate:
                    casu_magic = candidate.read(8)
            except OSError as exc:
                raise WebPlayerError(f"could not inspect uploaded media: {exc}") from exc
            if casu_magic in {b"CASUNAT1", b"CASUNAT2"}:
                if target not in {"mp4", "webm"}:
                    raise WebPlayerError("unsupported browser transcode target")
                destination = self.root / f"media-{token}.{target}"
                try:
                    export_casu(source, destination)
                except (CasuExportError, OSError, ValueError) as exc:
                    raise WebPlayerError(f"CASU browser fallback failed: {exc}") from exc
                video, audio = _media_shape(destination)
                session = self._add({
                    "kind": "file", "path": destination,
                    "content_type": (("video/webm" if video else "audio/webm")
                                     if target == "webm" else
                                     ("video/mp4" if video else "audio/mp4")),
                })
                published = True
                return session, "video" if video else "audio"
            video, audio = _media_shape(source)
            if target not in {"mp4", "webm"}:
                raise WebPlayerError("unsupported browser transcode target")
            destination = self.root / f"media-{token}.{target if video else ('webm' if target == 'webm' else 'm4a')}"
            result = subprocess.run(
                _transcode_command(source, video=video, audio=audio,
                                   output=str(destination), target=target),
                capture_output=True, text=True, check=False)
            if result.returncode or not destination.is_file() or not destination.stat().st_size:
                detail = result.stderr.strip().splitlines()
                raise WebPlayerError(detail[-1] if detail else "FFmpeg transcoding failed")
            session = self._add({"kind": "file", "path": destination,
                                 "content_type": (("video/webm" if video else "audio/webm")
                                                  if target == "webm" else
                                                  ("video/mp4" if video else "audio/mp4"))})
            published = True
            return session, "video" if video else "audio"
        finally:
            try:
                source.unlink()
            except FileNotFoundError:
                pass
            if destination is not None and not published:
                try:
                    destination.unlink()
                except FileNotFoundError:
                    pass

    def register_url(self, source: str, target: str = "mp4") -> tuple[str, str]:
        parsed = urllib.parse.urlsplit(source)
        if parsed.scheme.lower() not in NETWORK_SCHEMES or not parsed.netloc:
            raise WebPlayerError("only explicit network media URLs can be transcoded")
        if target not in {"mp4", "webm"}:
            raise WebPlayerError("unsupported browser transcode target")
        video, audio = _media_shape(source)
        token = self._add({"kind": "url", "source": source, "video": video,
                           "audio": audio, "target": target,
                           "content_type": (("video/webm" if video else "audio/webm")
                                            if target == "webm" else
                                            ("video/mp4" if video else "audio/mp4"))})
        return token, "video" if video else "audio"



def _listening_inodes(port: int) -> set[str]:
    """Return socket inodes of local processes LISTENing on *port*."""
    inodes: set[str] = set()
    target = f":{port:04X}"
    for name in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(name, "r", encoding="ascii", errors="replace") as handle:
                next(handle, None)
                for line in handle:
                    fields = line.split()
                    if len(fields) < 10 or fields[3] != "0A":
                        continue
                    if fields[1].upper().endswith(target):
                        inodes.add(fields[9])
        except OSError:
            continue
    return inodes


def _pids_for_inodes(inodes: set[str]) -> set[int]:
    """Map socket inodes to owning PIDs without external tools."""
    if not inodes:
        return set()
    wanted = {f"socket:[{inode}]" for inode in inodes}
    pids: set[int] = set()
    try:
        entries = os.listdir("/proc")
    except OSError:
        return pids
    for entry in entries:
        if not entry.isdigit():
            continue
        directory = f"/proc/{entry}/fd"
        try:
            descriptors = os.listdir(directory)
        except OSError:
            continue
        for descriptor in descriptors:
            try:
                if os.readlink(f"{directory}/{descriptor}") in wanted:
                    pids.add(int(entry))
                    break
            except OSError:
                continue
    return pids


def free_port(port: int, *, timeout: float = 5.0) -> list[int]:
    """Stop a previous local instance holding *port* so only one runs."""
    if not 1 <= int(port) <= 65535:
        return []
    victims = sorted(_pids_for_inodes(_listening_inodes(port)) - {os.getpid()})
    if not victims:
        return []
    for pid in victims:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.monotonic() + max(0.5, float(timeout))
    while time.monotonic() < deadline:
        if not _listening_inodes(port):
            return victims
        time.sleep(0.1)
    for pid in victims:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if not _listening_inodes(port):
            break
        time.sleep(0.1)
    return victims


class MPCASUWebServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler):
        self.transcodes = TranscodeStore()
        try:
            super().__init__(address, handler)
        except BaseException:
            self.transcodes.close()
            raise

    def server_close(self) -> None:
        super().server_close()
        self.transcodes.close()


class WebPlayerHandler(http.server.SimpleHTTPRequestHandler):
    """Serve static assets with conservative browser security headers."""

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "img-src 'self' blob: data:; media-src 'self' blob: http: https:; "
                         "connect-src 'self' http: https:; frame-src https://www.youtube.com "
                         "https://www.youtube-nocookie.com; object-src 'none'; base-uri 'none'; "
                         "form-action 'self'; frame-ancestors 'none'")
        self.send_header("Permissions-Policy",
                         "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, pattern: str, *args: object) -> None:
        print(f"MPCASU Web: {pattern % args}", file=sys.stderr)

    @property
    def _store(self) -> TranscodeStore:
        store = getattr(self.server, "transcodes", None)
        if not isinstance(store, TranscodeStore):
            raise WebPlayerError("transcoding is unavailable on this server")
        return store

    def _trusted_request(self, *, mutation: bool = False) -> bool:
        """Reject DNS-rebinding hosts and cross-site writes to loopback APIs."""
        port = int(self.server.server_address[1])
        host = self.headers.get("Host", "").strip().lower()
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        if host not in allowed:
            self.send_error(421, "untrusted loopback host")
            return False
        if mutation:
            fetch_site = self.headers.get("Sec-Fetch-Site", "").lower()
            origin = self.headers.get("Origin")
            if fetch_site == "cross-site" or (origin is not None and
                                                origin.rstrip("/").lower() !=
                                                f"http://{host}"):
                self.send_error(403, "cross-origin API request rejected")
                return False
        return True

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _catalog(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        if not self._trusted_request(mutation=True):
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if self.path == "/api/transcode-file":
                raw_name = self.headers.get("X-MPCASU-Filename", "media")
                filename = urllib.parse.unquote(raw_name)
                target = self.headers.get("X-MPCASU-Target", "mp4").lower()
                token, kind = self._store.transcode_upload(
                    self.rfile, length, Path(filename).name, target)
            elif self.path == "/api/transcode-url":
                if length <= 0 or length > 64 * 1024:
                    raise WebPlayerError("URL request size is invalid")
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise WebPlayerError("URL request must be a JSON object")
                token, kind = self._store.register_url(
                    str(request.get("url", "")), str(request.get("target", "mp4")))
            elif self.path == "/api/catalog-url":
                if length <= 0 or length > 64 * 1024:
                    raise WebPlayerError("catalog URL request size is invalid")
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise WebPlayerError("catalog URL request must be a JSON object")
                try:
                    body = fetch_document(str(request.get("url", "")),
                                          max_bytes=MAX_XMLTV_BYTES)
                except EpgError as exc:
                    raise WebPlayerError(str(exc)) from exc
                self._catalog(body)
                return
            elif self.path == "/api/search":
                if length <= 0 or length > 64 * 1024:
                    raise WebPlayerError("search request size is invalid")
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise WebPlayerError("search request must be a JSON object")
                self._search(request)
                return
            elif self.path == "/api/resolve":
                if length <= 0 or length > 64 * 1024:
                    raise WebPlayerError("resolve request size is invalid")
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise WebPlayerError("resolve request must be a JSON object")
                self._resolve(request)
                return
            elif self.path == "/api/spotify-metadata":
                if length <= 0 or length > 64 * 1024:
                    raise WebPlayerError("metadata request size is invalid")
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise WebPlayerError("metadata request must be a JSON object")
                self._spotify_metadata(request)
                return
            else:
                self.send_error(404)
                return
            self._json(200, {"url": f"/api/media/{token}", "kind": kind})
        except (BrokenPipeError, json.JSONDecodeError, OSError, ValueError,
                WebPlayerError) as exc:
            self._json(400, {"error": str(exc)[:1000]})

    def _search(self, request: dict) -> None:
        """YouTube/music search via yt-dlp; metadata only, no downloads."""
        query = str(request.get("query", "")).strip()
        source = str(request.get("source", "youtube")).lower()
        try:
            limit = int(request.get("limit", 12))
        except (TypeError, ValueError):
            limit = 12
        if not query:
            raise WebPlayerError("search query must not be empty")
        engine = search_music if source == "spotify" else search_youtube
        try:
            results = engine(query, limit=limit)
        except SearchError as exc:
            raise WebPlayerError(str(exc)) from exc
        self._json(200, {"results": [item.as_dict() for item in results]})

    def _resolve(self, request: dict) -> None:
        """Resolve a YouTube or Spotify URL to a direct playable stream URL.

        Spotify goes through the spotDL provider (Spotify Web API + YouTube
        matching); on failure the client is told honestly and can use the
        explicit YouTube handoff.
        """
        url = str(request.get("url", "")).strip()
        if not url:
            raise WebPlayerError("resolve request needs a url")
        try:
            if is_spotify_url(url):
                from casu.spotify import resolve_spotify_url
                resolved = resolve_spotify_url(url)
            elif is_youtube_url(url):
                resolved = resolve_media_location(url)
            else:
                raise WebPlayerError("only YouTube and Spotify URLs can be resolved")
        except (LocationResolutionError, SpotifyError) as exc:
            raise WebPlayerError(str(exc)) from exc
        self._json(200, {"url": resolved})

    def _spotify_metadata(self, request: dict) -> None:
        """Honest Spotify provider: public oEmbed title for the handoff."""
        url = str(request.get("url", "")).strip()
        if not url:
            raise WebPlayerError("metadata request needs a url")
        try:
            meta = fetch_spotify_metadata(url)
        except SpotifyError as exc:
            raise WebPlayerError(str(exc)) from exc
        self._json(200, {"title": meta.title, "kind": meta.kind})

    def _stream_proxy(self, parsed) -> None:
        """Relay an HTTP(S) stream same-origin so the Web Audio analyser can read it.

        Browsers silence `createMediaElementSource` for cross-origin media without
        CORS headers, which kills the FFT visualizer for radio streams.  Serving
        the bytes from this loopback origin keeps playback and analysis working.
        """
        query = urllib.parse.parse_qs(parsed.query)
        target = (query.get("url") or [""])[0].strip()
        try:
            remote = urllib.parse.urlsplit(target)
        except ValueError:
            remote = None
        if not target or remote is None or remote.scheme not in {"http", "https"} or not remote.hostname:
            self._json(400, {"error": "only HTTP(S) stream URLs can be proxied"})
            return
        request = urllib.request.Request(
            target, headers={"User-Agent": "mpcasu-web/1.0", "Icy-MetaData": "0"})
        try:
            upstream = urllib.request.urlopen(request, timeout=20)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            self._json(502, {"error": f"upstream unavailable: {exc}"[:1000]})
            return
        content_type = upstream.headers.get("Content-Type") or "application/octet-stream"
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            length = upstream.headers.get("Content-Length")
            if length and length.isdigit():
                self.send_header("Content-Length", length)
            self.end_headers()
            while block := upstream.read(128 * 1024):
                self.wfile.write(block)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            upstream.close()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if not self._trusted_request():
            return
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/api/version":
            from casu import __version__
            self._json(200, {"version": __version__})
            return
        if parsed.path == "/api/stream-proxy":
            self._stream_proxy(parsed)
            return
        if not parsed.path.startswith("/api/media/"):
            super().do_GET()
            return
        token = parsed.path.removeprefix("/api/media/")
        record = self._store.get(token)
        if record is None:
            self.send_error(404)
            return
        if record["kind"] == "file":
            self._serve_transcoded_file(record)
            return
        command = _transcode_command(record["source"], video=record["video"],
                                     audio=record["audio"], output="pipe:1",
                                     target=record["target"])
        process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL)
        try:
            self.send_response(200)
            self.send_header("Content-Type", record["content_type"])
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            assert process.stdout is not None
            while block := process.stdout.read(256 * 1024):
                self.wfile.write(block)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
        if not self._trusted_request():
            return
        parsed = urllib.parse.urlsplit(self.path)
        if not parsed.path.startswith("/api/media/"):
            super().do_HEAD()
            return
        record = self._store.get(parsed.path.removeprefix("/api/media/"))
        if record is None:
            self.send_error(404)
        elif record["kind"] != "file":
            self.send_error(405, "live transcoding requires GET")
        else:
            self._serve_transcoded_file(record, head_only=True)

    def _serve_transcoded_file(self, record: dict, *, head_only: bool = False) -> None:
        path = record["path"]
        try:
            size = path.stat().st_size
            start, end, status = 0, size - 1, 200
            requested = self.headers.get("Range")
            if requested:
                if not requested.startswith("bytes=") or "," in requested:
                    self.send_error(416)
                    return
                first, separator, last = requested[6:].partition("-")
                if not separator or not first.isdigit() or (last and not last.isdigit()):
                    self.send_error(416)
                    return
                start = int(first)
                end = min(size - 1, int(last)) if last else size - 1
                if start >= size or end < start:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                status = 206
            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", record["content_type"])
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if head_only:
                return
            with path.open("rb") as source:
                source.seek(start)
                remaining = length
                while remaining:
                    block = source.read(min(1024 * 1024, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


def resolve_web_root(explicit: Path | None = None) -> Path:
    candidates = ([explicit] if explicit is not None else []) + [
        Path(__file__).resolve().parent / "web",
        Path("/usr/share/casu-codec/web"),
    ]
    for candidate in candidates:
        if candidate is not None:
            root = candidate.expanduser().resolve()
            if all((root / name).is_file() for name in
                   ("index.html", "styles.css", "app.js", "casu-native.js")):
                return root
    raise WebPlayerError("MPCASU web assets are incomplete or not installed")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Launch MPCASU Web locally")
    result.add_argument("--port", type=int, default=8765,
                        help="local TCP port (0 chooses a free port)")
    result.add_argument("--no-browser", action="store_true",
                        help="serve without opening the default browser")
    result.add_argument("--no-takeover", action="store_true",
                        help="fail instead of replacing a running instance")
    result.add_argument("--check", action="store_true",
                        help="verify installed assets and exit")
    result.add_argument("--web-root", type=Path, help=argparse.SUPPRESS)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser().error("--port must be between 0 and 65535")
    try:
        root = resolve_web_root(args.web_root)
    except WebPlayerError as exc:
        print(f"web-casu: error: {exc}", file=sys.stderr)
        return 2
    if args.check:
        print(f"WEB CASU assets verified: {root}")
        return 0
    # ``index.html`` deliberately references shared package assets with
    # ``../assets``.  Serve the package/repository root and enter through
    # /web/ so those URLs resolve identically in development and in the DEB.
    site_root = root.parent
    handler = functools.partial(WebPlayerHandler, directory=str(site_root))
    if args.port and not args.no_takeover:
        stopped = free_port(args.port)
        if stopped:
            print(f"web-casu: replaced running instance (PID {', '.join(str(p) for p in stopped)})",
                  flush=True)
    try:
        server = MPCASUWebServer(("127.0.0.1", args.port), handler)
    except OSError as exc:
        print(f"web-casu: error: cannot bind local server: {exc}", file=sys.stderr)
        return 2
    port = int(server.server_address[1])
    url = f"http://127.0.0.1:{port}/web/"
    print(f"WEB CASU running at {url}", flush=True)
    if not args.no_browser:
        webbrowser.open(url, new=2)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
