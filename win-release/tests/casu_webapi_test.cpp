// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Unit tests for casu_webapi: HTTP request parsing + size caps, loopback host
// validation, Range/HEAD media planning, security helpers and the
// TranscodeStore token registry. Offline and runs under Wine.
#include "casu/webapi/http.hpp"
#include "casu/webapi/media_serve.hpp"
#include "casu/webapi/security.hpp"
#include "casu/webapi/server.hpp"
#include "casu/webapi/transcode_store.hpp"
#include "casu/webapi/webapi_error.hpp"
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

using namespace casu::webapi;

namespace {
int failures = 0;
void check(bool ok, const char* label) {
    if (!ok) { ++failures; std::printf("FAIL %s\n", label); }
    else std::printf("ok   %s\n", label);
}

std::string read_file_text(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    return std::string((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
}

bool has_header(const HttpResponse& r, const std::string& name, const std::string& value) {
    for (const auto& h : r.headers) {
        if (h.name == name && h.value == value) return true;
    }
    return false;
}
}  // namespace

int main() {
    RequestLimits lim;

    // --- HTTP request head parsing (WP-WEBAPI-001) ---
    {
        const char* raw = "GET /api/version HTTP/1.1\r\nHost: 127.0.0.1:8765\r\n\r\n";
        HttpRequestHead h;
        ParseStatus st = parse_request_head(reinterpret_cast<const uint8_t*>(raw),
                                            std::strlen(raw), lim, &h);
        check(st == ParseStatus::Complete && h.ok, "parse GET request head");
        check(h.method == "GET" && h.path == "/api/version" && h.query.empty(), "request method/path");
        check(h.header("Host") == "127.0.0.1:8765", "request Host header");
        check(h.content_length() == 0, "request content-length absent -> 0");
        check(h.head_bytes == std::strlen(raw), "request head_bytes");
    }
    {
        const char* raw = "POST /api/search HTTP/1.1\r\nHost: localhost:9000\r\n"
                          "Content-Length: 7\r\n\r\n{\"q\":1}";
        HttpRequestHead h;
        ParseStatus st = parse_request_head(reinterpret_cast<const uint8_t*>(raw),
                                            std::strlen(raw), lim, &h);
        check(st == ParseStatus::Complete && h.content_length() == 7, "POST content-length");
        check(h.path == "/api/search", "POST path");
    }
    {
        const char* raw = "GET /api/version HTTP/1.1\r\nHo";
        HttpRequestHead h;
        ParseStatus st = parse_request_head(reinterpret_cast<const uint8_t*>(raw),
                                            std::strlen(raw), lim, &h);
        check(st == ParseStatus::Incomplete, "partial head incomplete");
    }
    {
        std::string big;
        for (int i = 0; i < 50000; ++i) big += "X-Header: value\r\n";
        HttpRequestHead h;
        ParseStatus st = parse_request_head(reinterpret_cast<const uint8_t*>(big.data()),
                                            big.size(), lim, &h);
        check(st == ParseStatus::Error && h.error.find("too large") != std::string::npos,
              "header size cap enforced");
    }
    {
        std::string raw = "GET " + std::string(9000, 'a') + " HTTP/1.1\r\n\r\n";
        HttpRequestHead h;
        ParseStatus st = parse_request_head(reinterpret_cast<const uint8_t*>(raw.data()),
                                            raw.size(), lim, &h);
        check(st == ParseStatus::Error && h.error.find("request line") != std::string::npos,
              "request line cap enforced");
    }
    {
        const char* raw = "GET /api/version HTTP/1.1\r\nBadHeader\r\n\r\n";
        HttpRequestHead h;
        ParseStatus st = parse_request_head(reinterpret_cast<const uint8_t*>(raw),
                                            std::strlen(raw), lim, &h);
        check(st == ParseStatus::Error && h.error.find("malformed header") != std::string::npos,
              "malformed header line rejected");
    }

    // --- loopback host validation / DNS-rebinding (WP-WEBAPI-001) ---
    {
        check(is_trusted_loopback_host("127.0.0.1:8765", 8765), "host 127.0.0.1:8765 trusted");
        check(is_trusted_loopback_host("localhost:8765", 8765), "host localhost:8765 trusted");
        check(is_trusted_loopback_host("[::1]:8765", 8765), "host [::1]:8765 trusted");
        check(!is_trusted_loopback_host("evil.com:8765", 8765), "host evil.com rejected");
        check(!is_trusted_loopback_host("127.0.0.1:9", 8765), "host wrong port rejected");
        check(!is_trusted_loopback_host("127.0.0.1", 8765), "host without port rejected");
        check(!is_trusted_loopback_host("127.0.0.1:8765.", 8765), "host trailing dot rejected");
        check(!is_trusted_loopback_host("", 8765), "host empty rejected");
    }

    // --- Range/HEAD media planning (WP-WEBAPI-004) ---
    {
        MediaPlan p = plan_media_response("", 1000, "audio/mpeg");
        check(p.status == 200 && p.start == 0 && p.length == 1000 && p.file_size == 1000,
              "media plan 200 full");
        check(!p.headers.empty(), "media plan has headers");
        MediaPlan p206 = plan_media_response("bytes=0-99", 1000, "audio/mpeg");
        check(p206.status == 206 && p206.partial && p206.start == 0 && p206.length == 100,
              "media plan 206 range");
        MediaPlan ptail = plan_media_response("bytes=-50", 1000, "audio/mpeg");
        check(ptail.status == 206 && ptail.start == 950 && ptail.length == 50,
              "media plan 206 suffix");
        MediaPlan p416 = plan_media_response("bytes=5000-", 1000, "audio/mpeg");
        check(p416.status == 416, "media plan 416 unsatisfiable");
        MediaPlan pbad = plan_media_response("bytes=a-b", 1000, "audio/mpeg");
        check(pbad.status == 416, "media plan 416 malformed");
        MediaPlan pmulti = plan_media_response("bytes=0-1,2-3", 1000, "audio/mpeg");
        check(pmulti.status == 416, "media plan 416 multi-range");
        MediaPlan pnf = plan_media_response("", -1, "audio/mpeg");
        check(pnf.status == 404, "media plan 404 unknown size");
    }

    // --- security helpers (WP-WEBAPI-005) ---
    {
        check(is_safe_path_segment("index.html"), "safe segment");
        check(is_safe_path_segment("a.b-c_d"), "safe segment chars");
        check(!is_safe_path_segment(".."), ".. rejected");
        check(!is_safe_path_segment("."), ". rejected");
        check(!is_safe_path_segment("a/b"), "slash rejected");
        check(!is_safe_path_segment("a\\b"), "backslash rejected");
        check(!is_safe_path_segment(""), "empty segment rejected");
        check(is_within_root("/a/b.txt", "/a"), "path within root");
        check(is_within_root("/a", "/a"), "path equals root");
        check(!is_within_root("/a/../x", "/a"), "traversal normalized out of root");
        check(!is_within_root("/ab", "/a"), "sibling prefix not within root");
        check(sanitize_filename("../../etc/passwd") == "passwd", "sanitize strips traversal");
        check(sanitize_filename("..\\evil.mp4") == "evil.mp4", "sanitize strips backslash");
        check(sanitize_filename("a%2Fb.mp3") == "b.mp3", "sanitize decodes + strips path");
        check(sanitize_filename("") == "media", "sanitize empty -> media");
        check(sanitize_filename("../") == "media", "sanitize traversal-only -> media");
    }

    // --- stream-proxy allow-list / SSRF (WP-WEBAPI-005) ---
    {
        ProxyPolicy policy;
        policy.allowed_hosts = {"stream.example.com"};
        check(is_allowed_proxy_target("https://stream.example.com/live.mp3", policy),
              "allowlisted https target");
        check(is_allowed_proxy_target("https://sub.stream.example.com/x", policy),
              "allowlisted subdomain target");
        check(!is_allowed_proxy_target("https://other.com/x", policy), "non-allowlisted rejected");
        check(!is_allowed_proxy_target("http://other.com/x", policy), "http not allow-any");
        check(!is_allowed_proxy_target("ssh://stream.example.com/x", policy), "non-http scheme rejected");
        check(!is_allowed_proxy_target("https://user:pass@stream.example.com/x", policy),
              "credentials rejected");
        check(!is_allowed_proxy_target("https://127.0.0.1/x", policy), "loopback IP rejected");
        check(!is_allowed_proxy_target("https://10.0.0.1/x", policy), "private IP rejected");
        ProxyPolicy open_https;
        open_https.allow_any_https = true;
        check(is_allowed_proxy_target("https://public.example.org/x", open_https),
              "allow_any_https open");
    }

    // --- TranscodeStore (WP-WEBAPI-003) ---
    {
        TranscodeStore store;
        std::string src = store.root() + "/src.bin";
        {
            std::ofstream f(src, std::ios::binary);
            f.write("0123456789", 10);
        }
        std::string t = store.register_file(src, "audio/mpeg");
        check(!t.empty() && store.size() == 1, "register_file adds token");
        TranscodeSession s;
        check(store.get(t, &s) && s.kind == "file" && s.path == src && s.size_bytes == 10,
              "session get returns file record");

        std::string up = store.upload(std::string("hello world"), "clip.mp4", "mp4");
        TranscodeSession us;
        check(store.get(up, &us) && us.size_bytes == 11, "upload registers session");
        check(read_file_text(us.path) == "hello world", "upload wrote exact bytes");
        check(std::filesystem::exists(us.path), "upload file on disk");

        bool threw = false;
        try { store.upload(std::string(), "x.mp4"); }
        catch (const WebApiError&) { threw = true; }
        check(threw, "empty upload rejected");

        std::vector<std::string> toks = store.tokens();
        check(toks.size() == 2, "two sessions registered");

        bool removed = store.remove(up);
        check(removed && store.size() == 1 && !std::filesystem::exists(us.path),
              "remove deletes file and session");

        store.sweep(1);
        check(store.size() <= 1, "sweep evicts to cap");

        store.close();
        check(!std::filesystem::exists(store.root()), "close removes temp root");
    }

    // --- endpoint contract basics (WP-WEBAPI-002) ---
    {
        BasicEndpointHandler handler;
        HttpRequestHead req;
        HttpResponse v = handler.handle_version(req);
        check(v.status == 200 && has_header(v, "Content-Type", "application/json; charset=utf-8"),
              "version endpoint returns JSON");
        check(std::string(v.body.begin(), v.body.end()).find("\"version\"") != std::string::npos,
              "version payload has version field");

        HttpResponse notimpl = EndpointHandler().handle_catalog_url(req, "{\"url\":\"x\"}");
        check(notimpl.status == 501, "unimplemented endpoint answers 501");

        std::string token = handler.store().upload(std::string("0123456789"), "clip.mp4", "mp4");
        HttpRequestHead media_req;
        media_req.method = "GET";
        media_req.headers.emplace_back("range", "bytes=2-5");
        HttpResponse media = handler.handle_media(media_req, token);
        check(media.status == 206 && media.file_length == 4 && !media.file_path.empty(),
              "media token round-trip with range");
    }

    // --- response rendering ---
    {
        HttpResponse r = json_response(200, "{\"a\":1}");
        std::vector<uint8_t> bytes = render_response(r);
        std::string text(bytes.begin(), bytes.end());
        check(text.rfind("HTTP/1.1 200 OK\r\n", 0) == 0, "render status line");
        check(text.find("Content-Type: application/json; charset=utf-8\r\n") != std::string::npos,
              "render content-type");
        check(text.find("Content-Length: 7\r\n") != std::string::npos, "render content-length");
        check(text.substr(text.size() - 7) == "{\"a\":1}", "render body tail");
        check(std::string(reason_phrase(206)) == "Partial Content", "reason phrase 206");
    }

    std::printf(failures == 0 ? "ALL PASS\n" : "%d FAILURES\n", failures);
    return failures == 0 ? 0 : 1;
}