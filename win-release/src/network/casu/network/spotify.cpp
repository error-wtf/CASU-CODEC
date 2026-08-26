// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define NOGDI
#include <windows.h>  // CREATE_NO_WINDOW: keep GUI child processes silent
#endif
#include "casu/network/spotify.hpp"

#include "casu/json.hpp"
#include "casu/network/http.hpp"
#include "casu/network/network_error.hpp"
#include "casu/network/url.hpp"
#include "casu/network/ytdlp.hpp"

#include <QProcess>
#include <QStringList>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cctype>
#include <fstream>
#include <string>
#include <thread>
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

std::string env(const char* name) {
    const char* v = std::getenv(name);
    return v ? std::string(v) : std::string();
}

std::string find_spotdl() {
    std::string from_env = trim(env("CASU_SPOTDL"));
    if (!from_env.empty()) return from_env;
    return "spotdl";
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

bool read_file(const std::string& path, std::string* out) {
    std::ifstream f(path, std::ios::binary);
    if (!f) return false;
    f.seekg(0, std::ios::end);
    std::streamoff n = f.tellg();
    f.seekg(0, std::ios::beg);
    if (n < 0) return false;
    out->resize(static_cast<size_t>(n));
    if (n > 0) f.read(&(*out)[0], n);
    return f.good() || f.eof();
}

int64_t now_ms() {
    using namespace std::chrono;
    return duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
}

std::string temp_spotdl_path() {
    const char* tmp = std::getenv("TMP");
    std::string base = (tmp && *tmp) ? tmp : "/tmp";
    static int counter = 0;
    ++counter;
#ifdef _WIN32
    const char* user = std::getenv("USERNAME");
#else
    const char* user = std::getenv("USER");
#endif
    std::string stem = user ? user : "casu";
    return base + "/casu-spotify-" + stem + "-" + std::to_string(now_ms()) + "-" +
           std::to_string(counter) + ".spotdl";
}

// Runs `spotdl save <input> --save-file <file>` and polls the save file until
// it parses as JSON (spotDL may hang on shutdown; the process is killed once
// the data is available or the deadline passes).
casu::JsonValue spotdl_save(const std::string& input, int timeout_ms) {
    std::string binary = find_spotdl();
    if (binary.empty()) throw NetworkError("spotDL is not installed");
    std::string save_file = temp_spotdl_path();
    QProcess p;
    p.setProgram(to_qstring(binary));
    p.setArguments({QStringLiteral("save"), to_qstring(input),
                    QStringLiteral("--save-file"), to_qstring(save_file)});
    p.setStandardOutputFile(QProcess::nullDevice());
    p.setStandardErrorFile(QProcess::nullDevice());
#ifdef Q_OS_WIN
    // GUI app: never flash a console window for spotDL.
    p.setCreateProcessArgumentsModifier(
        [](QProcess::CreateProcessArguments* a) { a->flags |= CREATE_NO_WINDOW; });
#endif
    p.start();
    if (!p.waitForStarted(15000)) {
        std::remove(save_file.c_str());
        throw NetworkError("spotDL failed to start");
    }
    int64_t deadline = now_ms() + (timeout_ms < 30000 ? 30000 : timeout_ms);
    casu::JsonValue payload;
    bool got = false;
    while (now_ms() < deadline) {
        std::string text;
        if (read_file(save_file, &text) && text.size() > 4) {
            try {
                payload = casu::parse_json(text);
                got = true;
                break;
            } catch (const casu::JsonError&) {
            }
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(400));
    }
    p.kill();
    p.waitForFinished(2000);
    std::remove(save_file.c_str());
    if (!got) throw NetworkError("spotDL search timed out or failed");
    return payload;
}

std::vector<SpotifySearchResult> parse_spotdl_document(const casu::JsonValue& doc, int limit) {
    std::vector<SpotifySearchResult> results;
    const casu::JsonValue* payload = &doc;
    if (doc.is_object()) {
        const casu::JsonValue* songs = doc.find("songs");
        if (songs && songs->is_array()) payload = songs;
    }
    if (!payload->is_array()) {
        throw NetworkError("spotDL returned an unexpected save document");
    }
    for (const auto& data : payload->as_array().items) {
        if (!data.is_object()) continue;
        std::string url = json_str(data, "url", json_str(data, "spotify_url", ""));
        if (url.find("spotify.com/") == std::string::npos) continue;
        SpotifySearchResult res;
        res.url = url;
        res.title = json_str(data, "name", json_str(data, "title", "Spotify track"));
        if (res.title.size() > 300) res.title.resize(300);
        std::string artist;
        const casu::JsonValue* arts = data.find("artists");
        if (arts && arts->is_array()) {
            std::vector<std::string> names;
            for (const auto& a : arts->as_array().items) {
                if (a.is_object()) {
                    std::string n = json_str(a, "name", "");
                    if (!n.empty()) names.push_back(n);
                } else if (a.is_string()) {
                    names.push_back(a.as_string());
                }
            }
            for (size_t i = 0; i < names.size(); ++i) {
                if (i) artist += ", ";
                artist += names[i];
            }
        } else if (arts && arts->is_string()) {
            artist = arts->as_string();
        } else {
            artist = json_str(data, "artist", "");
        }
        if (artist.size() > 200) artist.resize(200);
        res.artist = artist;
        double dur = -1.0;
        if (json_num(data, "duration", &dur)) {
            res.duration = dur;
            res.has_duration = true;
        }
        results.push_back(std::move(res));
        if (static_cast<int>(results.size()) >= limit) break;
    }
    return results;
}

}  // namespace

SpotifyMetadata fetch_spotify_metadata(const std::string& url, int timeout_ms) {
    std::string clean = trim(url);
    if (!is_spotify_url(clean)) throw NetworkError("Invalid Spotify URL");
    if (clean.rfind("http", 0) != 0) clean = "https://" + clean;
    std::string endpoint = "https://open.spotify.com/oembed?url=" + url_encode(clean);
    HttpRequest req;
    req.url = endpoint;
    req.user_agent = "MPCASU/1.0";
    req.timeout_ms = timeout_ms < 3000 ? 3000 : timeout_ms;
    HttpResponse resp = HttpClient().request(req);
    if (resp.status != 200) {
        throw NetworkError("Spotify metadata fetch failed: open.spotify.com may be blocked on this network");
    }
    casu::JsonValue data;
    try {
        data = casu::parse_json(resp.text());
    } catch (const casu::JsonError&) {
        throw NetworkError("Spotify metadata fetch failed: invalid response");
    }
    if (!data.is_object()) throw NetworkError("Spotify metadata fetch failed: invalid response");
    std::string title = trim(json_str(data, "title", ""));
    if (title.empty()) throw NetworkError("Spotify returned no title for this URL");
    SpotifyMetadata meta;
    meta.kind = spotify_kind(clean);
    meta.title = title.size() > 300 ? title.substr(0, 300) : title;
    meta.url = clean;
    return meta;
}

std::string youtube_handoff_query(const SpotifyMetadata& meta) { return meta.title; }

std::string resolve_spotify_url(const std::string& url, int timeout_ms,
                                const std::string& title, const std::string& artist) {
    std::string clean = trim(url);
    if (!is_spotify_url(clean)) throw NetworkError("Invalid Spotify URL");
    if (spotify_kind(clean) != "track") {
        throw NetworkError("Spotify " + spotify_kind(clean) +
                           " must be expanded into tracks before playback");
    }
    std::string binary = find_spotdl();
    if (binary.empty()) throw NetworkError("spotDL is not installed");
    std::string save_file = temp_spotdl_path();
    QProcess p;
    p.setProgram(to_qstring(binary));
    p.setArguments({QStringLiteral("url"), to_qstring(clean)});
    p.setStandardOutputFile(to_qstring(save_file));
    p.setStandardErrorFile(QProcess::nullDevice());
    p.start();
    std::string direct;
    if (p.waitForStarted(15000)) {
        int64_t deadline = now_ms() + (timeout_ms > 15000 ? 15000 : (timeout_ms < 8000 ? 8000 : timeout_ms));
        std::string text;
        while (now_ms() < deadline) {
            if (read_file(save_file, &text) && !text.empty()) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(400));
        }
        size_t pos = 0;
        while (pos < text.size()) {
            size_t nl = text.find('\n', pos);
            std::string line = text.substr(pos, nl == std::string::npos ? std::string::npos : nl - pos);
            pos = nl == std::string::npos ? text.size() : nl + 1;
            line = trim(line);
            if (line.rfind("http://", 0) == 0 || line.rfind("https://", 0) == 0) {
                direct = line;
                break;
            }
        }
    }
    p.kill();
    p.waitForFinished(2000);
    std::remove(save_file.c_str());
    if (!direct.empty()) return direct;

    std::string match_title = title;
    if (match_title.empty()) {
        match_title = fetch_spotify_metadata(clean, timeout_ms < 10000 ? timeout_ms : 10000).title;
    }
    std::string query = trim(match_title + " " + artist);
    if (query.empty()) throw NetworkError("no title or artist available for matching");
    return YtDlp().resolve("ytsearch1:" + query, timeout_ms, "bestaudio");
}

std::vector<SpotifySearchResult> search_spotify(const std::string& query, int limit,
                                                int timeout_ms) {
    std::string q = trim(query);
    if (q.empty()) throw NetworkError("search query must not be empty");
    if (limit < 1) limit = 1;
    if (limit > 25) limit = 25;
    casu::JsonValue doc = spotdl_save(q, timeout_ms);
    std::vector<SpotifySearchResult> results = parse_spotdl_document(doc, limit);
    if (results.empty()) throw NetworkError("spotDL found no Spotify results");
    return results;
}

std::vector<SpotifySearchResult> expand_spotify(const std::string& url, int limit,
                                                int timeout_ms) {
    std::string clean = trim(url);
    std::string kind = spotify_kind(clean);
    if (kind.empty()) throw NetworkError("Invalid Spotify URL");
    if (kind != "track" && kind != "album" && kind != "playlist") {
        throw NetworkError("Spotify " + kind + " cannot be expanded into tracks before playback");
    }
    if (limit < 1) limit = 1;
    if (limit > 200) limit = 200;
    casu::JsonValue doc = spotdl_save(clean, timeout_ms);
    std::vector<SpotifySearchResult> results = parse_spotdl_document(doc, limit);
    if (results.empty()) throw NetworkError("spotDL found no Spotify results");
    return results;
}

}  // namespace casu::network