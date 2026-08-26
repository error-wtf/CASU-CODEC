// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define NOGDI
#include <windows.h>  // CREATE_NO_WINDOW: keep GUI child processes silent
#endif
#include "casu/network/ytdlp.hpp"

#include "casu/json.hpp"
#include "casu/network/network_error.hpp"
#include "casu/network/spotify.hpp"
#include "casu/network/url.hpp"

#include <QProcess>
#include <QStringList>

#include <cstdlib>
#include <cctype>
#include <string>
#include <vector>

namespace casu::network {

namespace {

std::string trim(const std::string& s) {
    std::string r = s;
    while (!r.empty() && std::isspace(static_cast<unsigned char>(r.front()))) r.erase(r.begin());
    while (!r.empty() && std::isspace(static_cast<unsigned char>(r.back()))) r.pop_back();
    return r;
}

QString to_qstring(const std::string& s) {
    return QString::fromUtf8(s.data(), static_cast<int>(s.size()));
}

std::string from_qbytes(const QByteArray& b) {
    return std::string(b.constData(), static_cast<size_t>(b.size()));
}

std::string env(const char* name) {
    const char* v = std::getenv(name);
    return v ? std::string(v) : std::string();
}

struct ProcResult {
    bool started = false;
    bool timeout = false;
    int exit_code = -1;
    std::string out;
    std::string err;
};

ProcResult run_process(const std::string& program, const std::vector<std::string>& args,
                       int timeout_ms) {
    ProcResult r;
    QProcess p;
    p.setProgram(to_qstring(program));
    QStringList qargs;
    for (const auto& a : args) qargs << to_qstring(a);
    p.setArguments(qargs);
#ifdef Q_OS_WIN
    // GUI app: never flash a console window for yt-dlp.exe.
    p.setCreateProcessArgumentsModifier(
        [](QProcess::CreateProcessArguments* a) { a->flags |= CREATE_NO_WINDOW; });
#endif
    p.start();
    if (!p.waitForStarted(timeout_ms)) {
        return r;
    }
    r.started = true;
    if (!p.waitForFinished(timeout_ms)) {
        p.kill();
        p.waitForFinished(2000);
        r.timeout = true;
        r.out = from_qbytes(p.readAllStandardOutput());
        r.err = from_qbytes(p.readAllStandardError());
        return r;
    }
    r.exit_code = p.exitCode();
    r.out = from_qbytes(p.readAllStandardOutput());
    r.err = from_qbytes(p.readAllStandardError());
    return r;
}

std::string json_str(const casu::JsonValue& obj, const char* key, const std::string& fallback) {
    const casu::JsonValue* v = obj.find(key);
    if (v && v->is_string()) return v->as_string();
    return fallback;
}

bool json_num(const casu::JsonValue& obj, const char* key, double* out) {
    const casu::JsonValue* v = obj.find(key);
    if (v && v->is_number()) {
        *out = v->as_double();
        return true;
    }
    return false;
}

SearchResult from_entry(const casu::JsonValue& entry, const std::string& source) {
    SearchResult res;
    res.source = source;
    std::string id = json_str(entry, "id", "");
    std::string url = json_str(entry, "url", "");
    if (url.empty() && !id.empty()) url = "https://www.youtube.com/watch?v=" + id;
    if (url.empty()) return res;
    res.url = url;
    res.title = json_str(entry, "title", id.empty() ? url : id);
    if (res.title.size() > 300) res.title.resize(300);
    double dur = -1.0;
    if (json_num(entry, "duration", &dur)) {
        res.duration = dur;
        res.has_duration = true;
    }
    res.uploader = json_str(entry, "uploader", json_str(entry, "channel", ""));
    if (res.uploader.size() > 200) res.uploader.resize(200);
    res.thumbnail = json_str(entry, "thumbnail", "");
    if (res.thumbnail.empty() && !id.empty()) {
        res.thumbnail = "https://i.ytimg.com/vi/" + id + "/mqdefault.jpg";
    }
    if (res.thumbnail.size() > 500) res.thumbnail.resize(500);
    return res;
}

std::vector<SearchResult> parse_dump_json(const std::string& stdout_text,
                                          const std::string& source, int limit) {
    std::vector<SearchResult> results;
    size_t pos = 0;
    while (pos < stdout_text.size()) {
        size_t nl = stdout_text.find('\n', pos);
        std::string line = stdout_text.substr(pos, nl == std::string::npos ? std::string::npos : nl - pos);
        pos = nl == std::string::npos ? stdout_text.size() : nl + 1;
        line = trim(line);
        if (line.empty()) continue;
        casu::JsonValue entry;
        try {
            entry = casu::parse_json(line);
        } catch (const casu::JsonError&) {
            continue;
        }
        if (!entry.is_object()) continue;
        SearchResult res = from_entry(entry, source);
        if (res.url.empty()) continue;
        results.push_back(std::move(res));
        if (static_cast<int>(results.size()) >= limit) break;
    }
    return results;
}

void require_binary(const std::string& path, const char* what) {
    if (path.empty()) throw NetworkError(std::string(what) + " requires yt-dlp");
}

std::string check_single_url(const std::string& out, const std::string& detail) {
    std::vector<std::string> urls;
    size_t pos = 0;
    while (pos < out.size()) {
        size_t nl = out.find('\n', pos);
        std::string line = out.substr(pos, nl == std::string::npos ? std::string::npos : nl - pos);
        pos = nl == std::string::npos ? out.size() : nl + 1;
        line = trim(line);
        if (!line.empty()) urls.push_back(line);
    }
    if (urls.size() != 1 || !is_http_url(urls[0])) {
        throw NetworkError("yt-dlp returned no valid media location" +
                           (detail.empty() ? std::string() : ": " + detail));
    }
    return urls[0];
}

std::string last_stderr_line(const std::string& err) {
    std::string e = trim(err);
    if (e.empty()) return {};
    size_t nl = e.find_last_of('\n');
    if (nl != std::string::npos) e = e.substr(nl + 1);
    e = trim(e);
    if (e.size() > 300) e.resize(300);
    return e;
}

}  // namespace

YtDlp::YtDlp() : path_(find_binary()) {}
YtDlp::YtDlp(std::string path) : path_(std::move(path)) {}
void YtDlp::set_path(std::string path) { path_ = std::move(path); }
const std::string& YtDlp::path() const { return path_; }

std::string YtDlp::find_binary() {
    std::string from_env = trim(env("CASU_YTDLP"));
    if (!from_env.empty()) return from_env;
    return "yt-dlp";
}

std::string YtDlp::resolve(const std::string& target, int timeout_ms,
                           const std::string& format_override) {
    std::string source = trim(target);
    if (source.empty() || source.find('\0') != std::string::npos) {
        throw NetworkError("media URL is empty or invalid");
    }
    require_binary(path_, "YouTube stream resolution");
    std::string format = format_override.empty()
        ? "best[protocol^=http][vcodec!=none][acodec!=none]/best[protocol^=http]/best"
        : format_override;
    // android client is proven for all test videos (see git log: android_vr
    // CDN URLs get 403s). Explicit extractor args pin the client so the
    // resolved CDN URL accepts the browser-profile request the transport
    // sends.
    std::vector<std::string> args = {
        "--no-playlist", "--no-warnings", "--no-progress", "--socket-timeout", "15",
        "--extractor-args", "youtube:player_client=android",
        "--get-url", "--format", format, source};
    ProcResult r = run_process(path_, args, timeout_ms);
    if (!r.started) throw NetworkError("yt-dlp is unavailable or failed to start");
    if (r.timeout) throw NetworkError("YouTube stream resolution timed out");
    std::string detail = last_stderr_line(r.err);
    if (r.exit_code != 0) {
        throw NetworkError("YouTube stream resolution failed" +
                           (detail.empty() ? std::string() : ": " + detail));
    }
    return check_single_url(r.out, detail);
}

std::vector<SearchResult> YtDlp::search(const std::string& query, int limit,
                                        int timeout_ms) {
    std::string q = trim(query);
    if (q.empty()) throw NetworkError("search query must not be empty");
    require_binary(path_, "search");
    if (limit < 1) limit = 1;
    if (limit > 25) limit = 25;
    std::vector<std::string> args = {
        "--no-warnings", "--flat-playlist", "--dump-json", "--socket-timeout", "10",
        "ytsearch" + std::to_string(limit) + ":" + q};
    ProcResult r = run_process(path_, args, timeout_ms);
    if (!r.started) throw NetworkError("search requires yt-dlp (unavailable)");
    if (r.timeout) throw NetworkError("search failed: timed out");
    std::vector<SearchResult> results = parse_dump_json(r.out, "youtube", limit);
    if (results.empty()) {
        std::string detail = last_stderr_line(r.err);
        throw NetworkError(detail.empty() ? "search returned no results" : detail);
    }
    return results;
}

std::vector<SearchResult> YtDlp::search_music(const std::string& query, int limit,
                                              int timeout_ms) {
    return search(query, limit, timeout_ms);
}

std::vector<SearchResult> YtDlp::expand_playlist(const std::string& url, int limit,
                                                 int timeout_ms) {
    std::string u = trim(url);
    if (u.empty()) throw NetworkError("playlist URL must not be empty");
    require_binary(path_, "playlist expansion");
    if (limit < 1) limit = 1;
    if (limit > 200) limit = 200;
    std::vector<std::string> args = {
        "--flat-playlist", "--no-warnings", "--dump-json", "--socket-timeout", "15", u};
    ProcResult r = run_process(path_, args, timeout_ms);
    if (!r.started) throw NetworkError("playlist expansion requires yt-dlp (unavailable)");
    if (r.timeout) throw NetworkError("playlist expansion timed out");
    std::vector<SearchResult> results = parse_dump_json(r.out, "youtube", limit);
    if (results.empty()) {
        std::string detail = last_stderr_line(r.err);
        throw NetworkError(detail.empty() ? "playlist returned no videos" : detail);
    }
    return results;
}

std::pair<std::string, std::string> YtDlp::title(const std::string& url,
                                                 int timeout_ms) {
    std::string u = trim(url);
    if (u.empty() || !is_youtube_url(u)) {
        throw NetworkError("title request needs a YouTube URL");
    }
    require_binary(path_, "title lookup");
    std::vector<std::string> args = {
        "--no-playlist", "--no-warnings", "--skip-download",
        "--print", "%(title)s", "--print", "%(uploader)s", u};
    ProcResult r = run_process(path_, args, timeout_ms);
    if (!r.started) throw NetworkError("title lookup requires yt-dlp (unavailable)");
    if (r.timeout) throw NetworkError("title lookup timed out");
    std::vector<std::string> lines;
    size_t pos = 0;
    while (pos < r.out.size()) {
        size_t nl = r.out.find('\n', pos);
        std::string line = r.out.substr(pos, nl == std::string::npos ? std::string::npos : nl - pos);
        pos = nl == std::string::npos ? r.out.size() : nl + 1;
        line = trim(line);
        if (!line.empty()) lines.push_back(line);
    }
    if (r.exit_code != 0 || lines.empty()) {
        throw NetworkError("title lookup returned no result");
    }
    return {lines[0], lines.size() > 1 ? lines[1] : std::string()};
}

std::string resolve_media_location(const std::string& value, int timeout_ms) {
    std::string source = trim(value);
    if (source.empty() || source.find('\0') != std::string::npos) {
        throw NetworkError("media URL is empty or invalid");
    }
    if (is_spotify_url(source)) {
        return resolve_spotify_url(source, timeout_ms);
    }
    if (!is_youtube_url(source)) {
        return source;
    }
    return YtDlp().resolve(source, timeout_ms);
}

}  // namespace casu::network