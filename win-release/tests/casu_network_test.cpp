// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Unit tests for casu_network: URL/scheme handling, Spotify detection,
// provider URL builders, HTTP Range/206 primitives and media-location
// resolution. Offline (no network, no subprocess) and runs under Wine.
#include "casu/network/http.hpp"
#include "casu/network/network_error.hpp"
#include "casu/network/providers.hpp"
#include "casu/network/range.hpp"
#include "casu/network/url.hpp"
#include "casu/network/ytdlp.hpp"
#include <cstdio>
#include <cstring>
#include <string>

using namespace casu::network;
using casu::network::range::ParsedRange;

namespace {
int failures = 0;
void check(bool ok, const char* label) {
    if (!ok) { ++failures; std::printf("FAIL %s\n", label); }
    else std::printf("ok   %s\n", label);
}

void check_range(const std::string& header, int64_t size, bool ok, bool unsat,
                 int64_t start, int64_t end, const char* label) {
    ParsedRange r = range::parse_bytes_range(header, size);
    bool fields_ok = !ok || (r.start == start && r.end == end);
    check(r.ok == ok && r.unsatisfiable == unsat && fields_ok, label);
}
}  // namespace

int main() {
    // --- URL parsing ---
    {
        Url u;
        check(parse_url("https://www.youtube.com/watch?v=abc123&t=5", &u),
              "parse_url https youtube");
        check(u.scheme == "https" && u.host == "www.youtube.com" && u.path == "/watch" &&
              u.query == "v=abc123&t=5", "url fields scheme/host/path/query");
        check(!parse_url("youtu.be/abc", &u), "parse_url rejects scheme-less text");
        check(!parse_url("", &u), "parse_url rejects empty");
        Url p;
        check(parse_url("http://open.spotify.com/track/x", &p) && p.host == "open.spotify.com",
              "parse_url http spotify host");
    }

    // --- YouTube URL detection (locations.py) ---
    {
        check(is_youtube_url("https://www.youtube.com/watch?v=abc"), "youtube www host");
        check(is_youtube_url("http://youtube.com/x"), "youtube bare host");
        check(is_youtube_url("https://m.youtube.com/x"), "youtube mobile host");
        check(is_youtube_url("https://music.youtube.com/x"), "youtube music host");
        check(is_youtube_url("https://youtu.be/abc"), "youtube youtu.be");
        check(is_youtube_url("https://www.youtube-nocookie.com/x"), "youtube nocookie host");
        check(!is_youtube_url("https://youtube.com.evil.com/x"), "youtube suffix spoof rejected");
        check(!is_youtube_url("ftp://youtube.com/x"), "youtube non-http scheme rejected");
        check(!is_youtube_url(""), "youtube empty rejected");
        check(!is_youtube_url("https://example.com/youtube"), "youtube path false positive rejected");
    }

    // --- Spotify URL detection / id / kind (spotify.py) ---
    {
        const char* track = "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC";
        check(is_spotify_url(track), "spotify track URL");
        check(is_spotify_url("open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC"), "spotify scheme-less URL");
        check(is_spotify_url("https://open.spotify.com/album/4uLU6hMCjMI75M1A2tKUQC?si=x"), "spotify album with query");
        check(is_spotify_url("https://open.spotify.com/playlist/4uLU6hMCjMI75M1A2tKUQC"), "spotify playlist URL");
        check(!is_spotify_url("https://open.spotify.com/track/4uLU6hMCjMI75M1A2"), "spotify short id rejected");
        check(!is_spotify_url("https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC!"), "spotify bad id char rejected");
        check(!is_spotify_url("https://evil.open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC"), "spotify wrong host rejected");
        check(!is_spotify_url("https://open.spotify.com/"), "spotify missing id rejected");
        check(spotify_id(track) == "4uLU6hMCjMI75M1A2tKUQC", "spotify_id extract");
        check(spotify_kind(track) == "track", "spotify_kind track");
        check(spotify_kind("https://open.spotify.com/album/4uLU6hMCjMI75M1A2tKUQC") == "album", "spotify_kind album");
    }

    // --- percent-encoding ---
    {
        check(url_encode("a b&c/d") == "a%20b%26c%2Fd", "url_encode spaces and slash");
        check(url_decode("a%20b%26c%2Fd") == "a b&c/d", "url_decode round-trip");
        check(url_decode("plain") == "plain", "url_decode plain");
    }

    // --- HTTP Range/206 primitives (WP-NET-005) ---
    {
        check_range("bytes=0-499", 1000, true, false, 0, 499, "range 0-499");
        check_range("bytes=500-", 1000, true, false, 500, 999, "range 500- open");
        check_range("bytes=-100", 1000, true, false, 900, 999, "range -100 suffix");
        check_range("bytes=-1000", 500, true, false, 0, 499, "range suffix larger than size");
        check_range("bytes=0-0", 10, true, false, 0, 0, "range single byte");
        check_range("bytes=900-2000", 1000, true, false, 900, 999, "range end clamped");
        check_range("bytes=100-50", 1000, false, true, 0, 0, "range reversed rejected");
        check_range("bytes=5000-", 1000, false, true, 0, 0, "range start beyond size");
        check_range("bytes=a-b", 1000, false, false, 0, 0, "range non-digit rejected");
        check_range("bytes=-", 1000, false, false, 0, 0, "range empty spec rejected");
        check_range("bytes=-0", 1000, false, true, 0, 0, "range zero suffix unsatisfiable");
        check_range("bytes=0-1,2-3", 1000, false, false, 0, 0, "range multi-range rejected");
        check_range("items=0-1", 1000, false, false, 0, 0, "range non-bytes unit rejected");
        check_range("", 1000, false, false, 0, 0, "range empty header rejected");
        check(range::parse_content_length("123") == 123, "content-length 123");
        check(range::parse_content_length("") == -1, "content-length empty -> -1");
        check(range::parse_content_length("-1") == -1, "content-length negative rejected");
        auto cr = range::parse_content_range("bytes 0-499/1000");
        check(cr.ok && cr.start == 0 && cr.end == 499 && cr.total == 1000, "content-range parse");
        auto crw = range::parse_content_range("bytes 0-499/*");
        check(crw.ok && crw.start == 0 && crw.end == 499 && crw.total == -1,
              "content-range wildcard total");
        check(!range::parse_content_range("nonsense").ok, "content-range malformed rejected");
        check(range::accepts_ranges("bytes"), "accept-ranges bytes");
        check(!range::accepts_ranges("none"), "accept-ranges none");
        check(range::is_partial_content(206) && !range::is_partial_content(200), "is_partial_content 206");
        check(range::content_range_header(0, 499, 1000) == "bytes 0-499/1000", "content-range header build");
        check(range::unsatisfied_range_header(1000) == "bytes */1000", "unsatisfied range header");
    }

    // --- webproviders URL builders (WP-NET-004) ---
    {
        check(web_player_url("spotify") == "https://open.spotify.com/", "spotify home URL");
        check(web_player_url("spotify", "queen") == "https://open.spotify.com/search/queen", "spotify search URL");
        check(web_player_url("hearthis", "a b") == "https://hearthis.at/search/?q=a%20b", "hearthis search URL encoded");
        check(web_player_url("tidal", "", "https://tidal.com/track/1") == "https://tidal.com/track/1", "tidal item URL passthrough");
        check(provider_for_url("https://open.spotify.com/track/x") == "spotify", "provider_for_url spotify");
        check(provider_for_url("https://tidal.com/") == "tidal", "provider_for_url tidal");
        check(provider_for_url("https://example.com/") == "", "provider_for_url unknown empty");
        check(is_external_provider("spotify") && is_external_provider("tidal"), "external providers spotify+tidal");
        check(!is_external_provider("hearthis"), "hearthis not external");
        check(spotify_embed_url("https://open.spotify.com/track/abc123") ==
                  "https://open.spotify.com/embed/track/abc123",
              "spotify embed URL");
        check(spotify_embed_url("https://notspotify.com/track/x") == "https://notspotify.com/track/x",
              "spotify embed passthrough");
    }

    // --- media location resolution (locations.py) ---
    {
        check(resolve_media_location("https://example.com/stream.mp3") ==
                  "https://example.com/stream.mp3",
              "non-youtube location returned unchanged");
        bool threw = false;
        try { resolve_media_location(""); }
        catch (const NetworkError&) { threw = true; }
        check(threw, "empty media location rejected");
        bool threw_nul = false;
        try { resolve_media_location(std::string("https://example.com/a") + '\0' + "b"); }
        catch (const NetworkError&) { threw_nul = true; }
        check(threw_nul, "NUL byte in media location rejected");
    }

    // --- HTTP client guard (no QCoreApplication -> fail fast, no crash) ---
    {
        HttpClient client;
        HttpResponse resp = client.get("https://example.com/", 1000);
        check(resp.status == 0 && resp.error.find("QCoreApplication") != std::string::npos,
              "HttpClient fails fast without QCoreApplication");
    }

    std::printf(failures == 0 ? "ALL PASS\n" : "%d FAILURES\n", failures);
    return failures == 0 ? 0 : 1;
}