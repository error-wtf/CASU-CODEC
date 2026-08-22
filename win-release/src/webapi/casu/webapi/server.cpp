// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/webapi/server.hpp"

#include "casu/codec/ffprobe.hpp"
#include "casu/json.hpp"
#include "casu/network/http.hpp"
#include "casu/network/network_error.hpp"
#include "casu/network/providers.hpp"
#include "casu/network/range.hpp"
#include "casu/network/spotify.hpp"
#include "casu/network/url.hpp"
#include "casu/network/ytdlp.hpp"
#include "casu/webapi/media_serve.hpp"
#include "casu/webapi/webapi_error.hpp"

#include <QCoreApplication>
#include <QDir>
#include <QByteArray>
#include <QFile>
#include <QHostAddress>

#include <cstdio>
#include <algorithm>
#include <QTcpServer>
#include <QTcpSocket>

#include <cctype>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <map>
#include <string>
#include <vector>

namespace casu::webapi {

namespace {

std::string to_lower(const std::string& s) {
    std::string r = s;
    for (char& c : r) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return r;
}

bool equals_ignore_case(const std::string& a, const std::string& b) {
    return to_lower(a) == to_lower(b);
}

std::string trim(const std::string& s) {
    std::string r = s;
    while (!r.empty() && std::isspace(static_cast<unsigned char>(r.front()))) r.erase(r.begin());
    while (!r.empty() && std::isspace(static_cast<unsigned char>(r.back()))) r.pop_back();
    return r;
}

std::string from_qbytes(const QByteArray& b) {
    return std::string(b.constData(), static_cast<size_t>(b.size()));
}

casu::JsonValue jstr(const std::string& s) { return casu::JsonValue(s); }
casu::JsonValue jnum(double d) { return casu::JsonValue(d); }
casu::JsonValue jnull() { return casu::JsonValue(nullptr); }

casu::JsonValue jobj(std::map<std::string, casu::JsonValue> items) {
    return casu::JsonValue(std::make_shared<casu::JsonObject>(casu::JsonObject{std::move(items)}));
}

casu::JsonValue jarr(std::vector<casu::JsonValue> items) {
    return casu::JsonValue(std::make_shared<casu::JsonArray>(casu::JsonArray{std::move(items)}));
}

std::string json_error(const std::string& msg) {
    return casu::dump_json(jobj({{"error", jstr(msg)}}));
}

casu::JsonValue parse_body(const std::string& body_json) {
    if (trim(body_json).empty()) throw casu::JsonError("empty request body");
    return casu::parse_json(body_json);
}

std::string body_string(const casu::JsonValue& obj, const char* key,
                        const std::string& fallback = "") {
    const casu::JsonValue* v = obj.find(key);
    if (v && v->is_string()) return v->as_string();
    return fallback;
}

std::string query_param(const std::string& query, const std::string& name) {
    std::string target = name + "=";
    size_t pos = 0;
    while (pos <= query.size()) {
        size_t amp = query.find('&', pos);
        std::string item = query.substr(pos, amp == std::string::npos ? std::string::npos : amp - pos);
        if (item.rfind(target, 0) == 0) {
            return casu::network::url_decode(item.substr(target.size()));
        }
        if (amp == std::string::npos) break;
        pos = amp + 1;
    }
    return {};
}

std::string content_type_for(const std::string& path) {
    size_t dot = path.find_last_of('.');
    std::string ext = dot == std::string::npos ? std::string() : to_lower(path.substr(dot));
    if (ext == ".html" || ext == ".htm") return "text/html; charset=utf-8";
    if (ext == ".css") return "text/css; charset=utf-8";
    if (ext == ".js" || ext == ".mjs") return "application/javascript; charset=utf-8";
    if (ext == ".json") return "application/json; charset=utf-8";
    if (ext == ".txt" || ext == ".m3u" || ext == ".m3u8") return "text/plain; charset=utf-8";
    if (ext == ".xml") return "application/xml; charset=utf-8";
    if (ext == ".svg") return "image/svg+xml";
    if (ext == ".png") return "image/png";
    if (ext == ".jpg" || ext == ".jpeg") return "image/jpeg";
    if (ext == ".webp") return "image/webp";
    if (ext == ".ico") return "image/x-icon";
    if (ext == ".mp3") return "audio/mpeg";
    if (ext == ".mp4") return "video/mp4";
    if (ext == ".webm") return "video/webm";
    if (ext == ".wasm") return "application/wasm";
    return "application/octet-stream";
}

}  // namespace

// --- EndpointHandler default: unimplemented endpoints answer 501 -----------


// casu/web_casu.py _media_shape parity: probe a location and classify it.
// Returns "video"/"audio"; sets ok=false when nothing playable was found.
static std::string media_kind_of(const std::string& location, bool* ok) {
    *ok = false;
    try {
        const casu::JsonValue probe = casu::codec::probe_json(location);
        bool video = false, audio = false;
        if (const casu::JsonValue* streams = probe.find("streams");
            streams && streams->is_array()) {
            for (const casu::JsonValue& s : streams->as_array().items) {
                if (!s.is_object()) continue;
                const casu::JsonValue* kind = s.find("codec_type");
                if (!kind || !kind->is_string()) continue;
                if (kind->as_string() == "video") {
                    const casu::JsonValue* disp = s.find("disposition");
                    const casu::JsonValue* pic =
                        disp && disp->is_object() ? disp->find("attached_pic")
                                                  : nullptr;
                    if (!(pic && pic->is_int() && pic->as_int() == 1))
                        video = true;
                } else if (kind->as_string() == "audio") {
                    audio = true;
                }
            }
        }
        if (!video && !audio) return {};
        *ok = true;
        return video ? "video" : "audio";
    } catch (const std::exception&) {
        return {};
    }
}


HttpResponse EndpointHandler::handle_version(const HttpRequestHead&) {
    return json_response(501, json_error("not implemented"));
}
HttpResponse EndpointHandler::handle_resolve(const HttpRequestHead&, const std::string&) {
    return json_response(501, json_error("not implemented"));
}
HttpResponse EndpointHandler::handle_search(const HttpRequestHead&, const std::string&) {
    return json_response(501, json_error("not implemented"));
}
HttpResponse EndpointHandler::handle_youtube_title(const HttpRequestHead&, const std::string&) {
    return json_response(501, json_error("not implemented"));
}
HttpResponse EndpointHandler::handle_spotify_metadata(const HttpRequestHead&, const std::string&) {
    return json_response(501, json_error("not implemented"));
}
HttpResponse EndpointHandler::handle_catalog_url(const HttpRequestHead&, const std::string&) {
    return json_response(501, json_error("not implemented"));
}
HttpResponse EndpointHandler::handle_transcode_url(const HttpRequestHead&, const std::string&) {
    return json_response(501, json_error("not implemented"));
}
HttpResponse EndpointHandler::handle_transcode_file(const HttpRequestHead&, const uint8_t*, size_t,
                                                    const std::string&, const std::string&) {
    return json_response(501, json_error("not implemented"));
}
HttpResponse EndpointHandler::handle_stream_proxy(const HttpRequestHead&, const std::string&) {
    return json_response(501, json_error("not implemented"));
}
HttpResponse EndpointHandler::handle_media(const HttpRequestHead&, const std::string&) {
    return json_response(501, json_error("not implemented"));
}

// --- BasicEndpointHandler: wire the core endpoints to casu_network ---------

HttpResponse BasicEndpointHandler::handle_version(const HttpRequestHead&) {
    return json_response(200, casu::dump_json(jobj({{"version", jstr(kWebApiVersion)}})));
}

HttpResponse BasicEndpointHandler::handle_resolve(const HttpRequestHead&,
                                                  const std::string& body_json) {
    casu::JsonValue body;
    try {
        body = parse_body(body_json);
        if (!body.is_object()) throw casu::JsonError("resolve request must be a JSON object");
        std::string url = trim(body_string(body, "url"));
        if (url.empty()) throw casu::JsonError("resolve request needs a url");
        std::string resolved;
        if (casu::network::is_spotify_url(url)) {
            resolved = casu::network::resolve_spotify_url(
                url, 60000, trim(body_string(body, "title")), trim(body_string(body, "artist")));
        } else if (casu::network::is_youtube_url(url)) {
            resolved = casu::network::resolve_media_location(url);
        } else {
            throw casu::JsonError("only YouTube and Spotify URLs can be resolved");
        }
        return json_response(200, casu::dump_json(jobj({{"url", jstr(resolved)}})));
    } catch (const casu::network::NetworkError& e) {
        return json_response(400, json_error(e.what()));
    } catch (const casu::JsonError& e) {
        return json_response(400, json_error(e.what()));
    }
}

HttpResponse BasicEndpointHandler::handle_search(const HttpRequestHead&,
                                                 const std::string& body_json) {
    casu::JsonValue body;
    try {
        body = parse_body(body_json);
        if (!body.is_object()) throw casu::JsonError("search request must be a JSON object");
        std::string query = trim(body_string(body, "query"));
        if (query.empty()) throw casu::JsonError("search query must not be empty");
        std::string source = to_lower(body_string(body, "source", "youtube"));
        int limit = 12;
        const casu::JsonValue* lim = body.find("limit");
        if (lim && lim->is_int()) {
            long v = static_cast<long>(lim->as_int());
            if (v >= 1 && v <= 25) limit = static_cast<int>(v);
        }
        if (source == "spotify") {
            auto found = casu::network::search_spotify(query, limit, 90000);
            std::vector<casu::JsonValue> items;
            for (const auto& r : found) {
                casu::JsonValue dur = r.has_duration ? jnum(r.duration) : jnull();
                items.push_back(jobj({
                    {"title", jstr(r.title)},
                    {"url", jstr(r.url)},
                    {"duration", dur},
                    {"uploader", jstr(r.artist.empty() ? "Spotify" : r.artist)},
                    {"source", jstr("spotify")},
                }));
            }
            return json_response(200, casu::dump_json(jobj({{"results", jarr(std::move(items))}})));
        }
        auto found = casu::network::YtDlp().search(query, limit, 30000);
        std::vector<casu::JsonValue> items;
        for (const auto& r : found) {
            casu::JsonValue dur = r.has_duration ? jnum(r.duration) : jnull();
            items.push_back(jobj({
                {"title", jstr(r.title)},
                {"url", jstr(r.url)},
                {"duration", dur},
                {"uploader", jstr(r.uploader)},
                {"source", jstr(r.source)},
                {"thumbnail", jstr(r.thumbnail)},
            }));
        }
        return json_response(200, casu::dump_json(jobj({{"results", jarr(std::move(items))}})));
    } catch (const casu::network::NetworkError& e) {
        return json_response(400, json_error(e.what()));
    } catch (const casu::JsonError& e) {
        return json_response(400, json_error(e.what()));
    }
}

HttpResponse BasicEndpointHandler::handle_youtube_title(const HttpRequestHead&,
                                                        const std::string& body_json) {
    try {
        casu::JsonValue body = parse_body(body_json);
        if (!body.is_object()) throw casu::JsonError("title request must be a JSON object");
        std::string url = trim(body_string(body, "url"));
        if (url.empty() || !casu::network::is_youtube_url(url)) {
            throw casu::JsonError("title request needs a YouTube url");
        }
        auto t = casu::network::YtDlp().title(url, 25000);
        return json_response(200, casu::dump_json(jobj({
            {"title", jstr(t.first)},
            {"uploader", jstr(t.second)},
        })));
    } catch (const casu::network::NetworkError& e) {
        return json_response(400, json_error(e.what()));
    } catch (const casu::JsonError& e) {
        return json_response(400, json_error(e.what()));
    }
}

HttpResponse BasicEndpointHandler::handle_spotify_metadata(const HttpRequestHead&,
                                                           const std::string& body_json) {
    try {
        casu::JsonValue body = parse_body(body_json);
        if (!body.is_object()) throw casu::JsonError("metadata request must be a JSON object");
        std::string url = trim(body_string(body, "url"));
        if (url.empty()) throw casu::JsonError("metadata request needs a url");
        casu::network::SpotifyMetadata meta = casu::network::fetch_spotify_metadata(url, 15000);
        return json_response(200, casu::dump_json(jobj({
            {"title", jstr(meta.title)},
            {"kind", jstr(meta.kind)},
        })));
    } catch (const casu::network::NetworkError& e) {
        return json_response(400, json_error(e.what()));
    } catch (const casu::JsonError& e) {
        return json_response(400, json_error(e.what()));
    }
}

HttpResponse BasicEndpointHandler::handle_catalog_url(const HttpRequestHead&,
                                                      const std::string& body_json) {
    try {
        casu::JsonValue body = parse_body(body_json);
        if (!body.is_object()) throw casu::JsonError("catalog URL request must be a JSON object");
        std::string url = trim(body_string(body, "url"));
        if (url.empty()) throw casu::JsonError("catalog URL request needs a url");
        casu::network::HttpRequest req;
        req.url = url;
        req.user_agent = "MPCASU/3.0";
        req.timeout_ms = 20000;
        casu::network::HttpResponse resp = casu::network::HttpClient().request(req);
        if (resp.status != 200) {
            throw casu::network::NetworkError("catalog fetch failed (HTTP " +
                                              std::to_string(resp.status) + ")");
        }
        constexpr size_t kMaxCatalog = 32 * 1024 * 1024;
        if (resp.body.size() > kMaxCatalog) {
            throw casu::network::NetworkError("catalog document exceeds 32 MiB");
        }
        HttpResponse out;
        out.status = 200;
        out.add("Content-Type", "application/octet-stream");
        out.body = std::move(resp.body);
        return out;
    } catch (const casu::network::NetworkError& e) {
        return json_response(400, json_error(e.what()));
    } catch (const casu::JsonError& e) {
        return json_response(400, json_error(e.what()));
    }
}

HttpResponse BasicEndpointHandler::handle_transcode_url(const HttpRequestHead&,
                                                        const std::string& body_json) {
    try {
        casu::JsonValue body = parse_body(body_json);
        if (!body.is_object()) throw casu::JsonError("URL request must be a JSON object");
        std::string url = trim(body_string(body, "url"));
        std::string target = to_lower(body_string(body, "target", "mp4"));
        if (target != "mp4" && target != "webm") {
            throw casu::webapi::WebApiError("unsupported browser transcode target");
        }
        bool shape_ok = false;
        const std::string kind = media_kind_of(url, &shape_ok);
        if (!shape_ok)
            throw casu::webapi::WebApiError(
                "source has no playable audio or video stream");
        std::string token = store_.register_url(url, "video/mp4", target);
        return json_response(200, casu::dump_json(jobj({
            {"url", jstr("/api/media/" + token)},
            {"kind", jstr(kind)},
        })));
    } catch (const casu::webapi::WebApiError& e) {
        return json_response(400, json_error(e.what()));
    } catch (const casu::JsonError& e) {
        return json_response(400, json_error(e.what()));
    }
}

HttpResponse BasicEndpointHandler::handle_transcode_file(const HttpRequestHead&,
                                                         const uint8_t* data, size_t n,
                                                         const std::string& filename,
                                                         const std::string& target) {
    try {
        std::string t = to_lower(target);
        if (t != "mp4" && t != "webm") {
            throw casu::webapi::WebApiError("unsupported browser transcode target");
        }
        std::string token = store_.upload(data, n, filename, t);
        TranscodeSession session;
        std::string kind = "video";
        if (store_.get(token, &session)) {
            bool shape_ok = false;
            kind = media_kind_of(session.path, &shape_ok);
            if (!shape_ok) kind = t == "webm" ? "video" : "audio";
        }
        return json_response(200, casu::dump_json(jobj({
            {"url", jstr("/api/media/" + token)},
            {"kind", jstr(kind)},
        })));
    } catch (const casu::webapi::WebApiError& e) {
        return json_response(400, json_error(e.what()));
    }
}

HttpResponse BasicEndpointHandler::handle_transcode_file_spilled(
    const HttpRequestHead&, const std::string& spilled_path,
    const std::string& filename, const std::string& target) {
    try {
        std::string t = to_lower(target);
        if (t != "mp4" && t != "webm") {
            throw casu::webapi::WebApiError(
                "unsupported browser transcode target");
        }
        std::string token = store_.upload_from_file(spilled_path, filename, t);
        TranscodeSession session;
        std::string kind = t == "webm" ? "video" : "audio";
        if (store_.get(token, &session)) {
            bool shape_ok = false;
            kind = media_kind_of(session.path, &shape_ok);
            if (!shape_ok) kind = t == "webm" ? "video" : "audio";
        }
        return json_response(200, casu::dump_json(jobj({
            {"url", jstr("/api/media/" + token)},
            {"kind", jstr(kind)},
        })));
    } catch (const casu::webapi::WebApiError& e) {
        return json_response(400, json_error(e.what()));
    }
}

HttpResponse BasicEndpointHandler::handle_stream_proxy(const HttpRequestHead&,
                                                       const std::string& target_url) {
    std::string target = trim(target_url);
    if (!is_allowed_proxy_target(target, policy_)) {
        return json_response(403, json_error("stream proxy target not allowed"));
    }
    casu::network::HttpRequest req;
    req.url = target;
    req.user_agent = "mpcasu-web/1.0";
    req.timeout_ms = 20000;
    req.headers.emplace_back("Icy-MetaData", "0");
    casu::network::HttpResponse upstream = casu::network::HttpClient().request(req);
    if (upstream.status != 200) {
        return json_response(502, json_error("upstream unavailable: " + upstream.error));
    }
    HttpResponse out;
    out.status = 200;
    std::string ct = upstream.header("content-type");
    out.add("Content-Type", ct.empty() ? "application/octet-stream" : ct);
    out.add("Cache-Control", "no-store");
    std::string cl = upstream.header("content-length");
    if (!cl.empty() && cl.find_first_not_of("0123456789") == std::string::npos) {
        out.add("Content-Length", cl);
    }
    out.body = std::move(upstream.body);
    return out;
}

HttpResponse BasicEndpointHandler::handle_media(const HttpRequestHead& req,
                                                const std::string& token) {
    TranscodeSession session;
    if (!store_.get(token, &session)) {
        return text_response(404, "not found");
    }
    if (session.kind != "file" || session.path.empty()) {
        return json_response(405, json_error("live transcoding requires GET"));
    }
    std::error_code ec;
    int64_t size = std::filesystem::file_size(session.path, ec);
    if (ec) return text_response(404, "not found");
    MediaPlan plan = plan_media_response(req.header("Range"), size, session.content_type);
    HttpResponse out;
    out.status = plan.status;
    for (const auto& h : plan.headers) out.add(h.first, h.second);
    if (plan.status == 206 || plan.status == 200) {
        out.file_path = session.path;
        out.file_offset = plan.start;
        out.file_length = plan.length;
    }
    return out;
}

// --- HTTPServer ------------------------------------------------------------

class HTTPServer::Impl : public QObject {
public:
    QTcpServer server;
    std::map<QTcpSocket*, QByteArray> buffers;
    std::shared_ptr<EndpointHandler> handler = std::make_shared<BasicEndpointHandler>();
    RequestLimits limits;
    std::string static_root;
    uint16_t port = 0;

    void on_new_connection() {
        while (server.hasPendingConnections()) {
            QTcpSocket* socket = server.nextPendingConnection();
            if (!socket) continue;
            buffers[socket] = QByteArray();
            QObject::connect(socket, &QTcpSocket::readyRead, this, [this, socket] {
                on_ready_read(socket);
            });
            QObject::connect(socket, &QTcpSocket::disconnected, this, [this, socket] {
                on_disconnected(socket);
            });
        }
    }

    // Large-upload disk spill: bodies above kInlineBodyLimit go straight to
    // a temp file instead of buffering up to 16 GiB in RAM (HANDOVER fix).
    struct Spill {
        HttpRequestHead head;
        std::string path;
        QFile file;
        uint64_t length = 0;
        uint64_t received = 0;
    };
    std::map<QTcpSocket*, Spill> spills;
    static constexpr uint64_t kInlineBodyLimit = 64ULL * 1024 * 1024;

    void finish_spill(QTcpSocket* socket) {
        auto it = spills.find(socket);
        if (it == spills.end()) return;
        Spill& spill = it->second;
        spill.file.close();
        HttpResponse resp;
        try {
            resp = handler->handle_transcode_file_spilled(
                spill.head, spill.path,
                trim(spill.head.header("X-MPCASU-Filename")),
                to_lower(trim(spill.head.header("X-MPCASU-Target"))));
        } catch (const std::exception&) {
            resp = text_response(400, "upload failed");
        }
        std::error_code rm_ec;
        std::filesystem::remove(spill.path, rm_ec);
        spills.erase(it);
        send(socket, spill.head, resp);
        close_after_response(socket);
    }

    void abort_spill(QTcpSocket* socket) {
        auto it = spills.find(socket);
        if (it == spills.end()) return;
        it->second.file.close();
        std::error_code rm_ec;
        std::filesystem::remove(it->second.path, rm_ec);
        spills.erase(it);
    }

    void on_ready_read(QTcpSocket* socket) {
        QByteArray& buf = buffers[socket];
        buf.append(socket->readAll());
        if (spills.count(socket)) {
            auto it = spills.find(socket);
            const qint64 remaining =
                static_cast<qint64>(it->second.length - it->second.received);
            const QByteArray chunk =
                buf.mid(0, static_cast<int>(std::min<qint64>(
                                buf.size(), remaining)));
            it->second.file.write(chunk);
            it->second.received += static_cast<uint64_t>(chunk.size());
            buf.remove(0, chunk.size());
            if (it->second.received >= it->second.length)
                finish_spill(socket);
            return;
        }
        process_buffer(socket);
    }

    void on_disconnected(QTcpSocket* socket) {
        abort_spill(socket);
        buffers.erase(socket);
        socket->deleteLater();
    }

    void close_after_response(QTcpSocket* socket) {
        socket->flush();
        socket->disconnectFromHost();
    }

    void process_buffer(QTcpSocket* socket) {
        QByteArray& buf = buffers[socket];
        HttpRequestHead head;
        ParseStatus st = parse_request_head(reinterpret_cast<const uint8_t*>(buf.constData()),
                                            static_cast<size_t>(buf.size()), limits, &head);
        if (st == ParseStatus::Incomplete) {
            const uint64_t declared_length =
                head.error.empty() ? head.content_length() : 0;
            if (head.path == "/api/transcode-file" &&
                declared_length > kInlineBodyLimit &&
                declared_length <= body_cap(head)) {
                Spill& spill = spills[socket];
                spill.head = head;
                spill.length = declared_length;
                spill.path = QDir::tempPath().toStdString() +
                             "/mpcasu-web-upload-" +
                             std::to_string(
                                 QCoreApplication::applicationPid()) +
                             "-" +
                             std::to_string(
                                 reinterpret_cast<uintptr_t>(socket)) +
                             ".spill";
                spill.received = 0;
                spill.file.setFileName(QString::fromStdString(spill.path));
                if (!spill.file.open(QIODevice::WriteOnly |
                                     QIODevice::Truncate)) {
                    spills.erase(socket);
                } else {
                    const QByteArray first =
                        buf.mid(static_cast<int>(head.head_bytes));
                    spill.file.write(first);
                    spill.received += static_cast<uint64_t>(first.size());
                    buf.clear();
                    if (spill.received >= spill.length) finish_spill(socket);
                    return;
                }
            }
            if (buf.size() > limits.max_header_bytes + 64 * 1024) {
                send(socket, head, text_response(413, "request too large"));
                close_after_response(socket);
            }
            return;
        }
        if (st == ParseStatus::Error) {
            send(socket, head, text_response(400, head.error));
            close_after_response(socket);
            return;
        }

        uint64_t length = head.content_length();
        uint64_t cap = body_cap(head);
        if (length > cap) {
            send(socket, head, text_response(413, "request body exceeds size cap"));
            close_after_response(socket);
            return;
        }
        if (buf.size() < head.head_bytes + length) {
            return;
        }
        QByteArray body = buf.mid(static_cast<int>(head.head_bytes), static_cast<int>(length));
        HttpResponse resp = route(head, body);
        send(socket, head, resp);
        close_after_response(socket);
    }

    uint64_t body_cap(const HttpRequestHead& head) {
        if (head.method == "POST" && head.path == "/api/transcode-file") return limits.max_upload_bytes;
        if (head.method == "POST" && head.path == "/api/catalog-url") return limits.max_catalog_bytes;
        return limits.max_json_bytes;
    }

    static std::string rstrip_slash_lower(std::string v) {
        while (!v.empty() && (v.back() == '/' || v.back() == ' ' ||
                              v.back() == '\t' || v.back() == '\r'))
            v.pop_back();
        for (char& c : v)
            c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        return v;
    }

    // web_casu.py _trusted_request(mutation=True): reject cross-site writes
    // to loopback APIs via Sec-Fetch-Site / Origin.
    HttpResponse check_mutation(const HttpRequestHead& head) {
        const std::string host =
            to_lower(trim(head.header("Host")));
        const std::string fetch_site =
            to_lower(trim(head.header("Sec-Fetch-Site")));
        const std::string origin = trim(head.header("Origin"));
        if (fetch_site == "cross-site")
            return text_response(403, "cross-origin API request rejected");
        if (!origin.empty() &&
            rstrip_slash_lower(origin) != "http://" + host)
            return text_response(403, "cross-origin API request rejected");
        return HttpResponse{};
    }


    HttpResponse route(const HttpRequestHead& head, const QByteArray& body) {
        if (!is_trusted_loopback_host(head.header("Host"), port)) {
            return text_response(421, "untrusted loopback host");
        }
        if (head.method == "POST") {
            HttpResponse rejected = check_mutation(head);
            if (rejected.status == 403) return rejected;
        }
        if (head.method == "POST") {
            HttpResponse rejected = check_mutation(head);
            if (rejected.status == 403) return rejected;
        }
        std::string p = head.path;
        if (head.method == "GET" || head.method == "HEAD") {
            if (p == "/api/version") return handler->handle_version(head);
            if (p == "/api/stream-proxy") {
                std::string target = query_param(head.query, "url");
                return handler->handle_stream_proxy(head, target);
            }
            if (p.rfind("/api/media/", 0) == 0 && p.size() > std::string("/api/media/").size()) {
                return handler->handle_media(head, p.substr(std::string("/api/media/").size()));
            }
            if (!static_root.empty()) return serve_static(head);
            return text_response(404, "not found");
        }
        if (head.method == "POST") {
            if (p == "/api/transcode-file") {
                std::string filename = trim(head.header("X-MPCASU-Filename"));
                if (filename.empty()) filename = "media";
                std::string target = to_lower(trim(head.header("X-MPCASU-Target")));
                if (target.empty()) target = "mp4";
                return handler->handle_transcode_file(
                    head, reinterpret_cast<const uint8_t*>(body.constData()),
                    static_cast<size_t>(body.size()), filename, target);
            }
            if (p == "/api/search") return handler->handle_search(head, from_qbytes(body));
            if (p == "/api/resolve") return handler->handle_resolve(head, from_qbytes(body));
            if (p == "/api/youtube-title") return handler->handle_youtube_title(head, from_qbytes(body));
            if (p == "/api/spotify-metadata") return handler->handle_spotify_metadata(head, from_qbytes(body));
            if (p == "/api/catalog-url") return handler->handle_catalog_url(head, from_qbytes(body));
            if (p == "/api/transcode-url") return handler->handle_transcode_url(head, from_qbytes(body));
            return text_response(404, "not found");
        }
        return text_response(405, "method not allowed");
    }

    HttpResponse serve_static(const HttpRequestHead& head) {
        std::string p = head.path;
        if (p.empty() || p[0] != '/') return text_response(404, "not found");
        if (p == "/") p = "/web/index.html";
        std::string rel;
        size_t pos = 1;
        bool safe = true;
        while (pos < p.size()) {
            size_t slash = p.find('/', pos);
            std::string seg = p.substr(pos, slash == std::string::npos ? std::string::npos : slash - pos);
            if (seg.empty()) {
                if (slash == std::string::npos) break;
                pos = slash + 1;
                continue;
            }
            if (!is_safe_path_segment(seg)) {
                safe = false;
                break;
            }
            rel += "/" + seg;
            if (slash == std::string::npos) break;
            pos = slash + 1;
        }
        if (!safe || rel.empty()) return text_response(403, "forbidden");
        if (p.size() > 1 && p.back() == '/') rel += "/index.html";
        std::string full = static_root + rel;
        if (!is_within_root(full, static_root)) return text_response(403, "forbidden");
        std::error_code ec;
        if (!std::filesystem::is_regular_file(full, ec)) return text_response(404, "not found");
        std::ifstream f(full, std::ios::binary);
        if (!f) return text_response(404, "not found");
        std::string data((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
        HttpResponse out;
        out.status = 200;
        out.add("Content-Type", content_type_for(full));
        out.body.assign(data.begin(), data.end());
        return out;
    }

    void send(QTcpSocket* socket, const HttpRequestHead& head, HttpResponse resp) {
        // Linux parity (web_casu.py end_headers): every response carries the
        // conservative browser security headers. Existing values win.
        auto ensure = [&resp](const std::string& name, const std::string& value) {
            for (const auto& h : resp.headers) {
                if (equals_ignore_case(h.name, name)) return;
            }
            resp.add(name, value);
        };
        ensure("X-Content-Type-Options", "nosniff");
        ensure("Referrer-Policy", "no-referrer");
        ensure("Cross-Origin-Opener-Policy", "same-origin");
        ensure("Content-Security-Policy",
               "default-src 'self'; script-src 'self'; style-src 'self'; "
               "img-src 'self' blob: data:; media-src 'self' blob: http: https:; "
               "connect-src 'self' http: https:; frame-src https://www.youtube.com "
               "https://www.youtube-nocookie.com; object-src 'none'; base-uri 'none'; "
               "form-action 'self'; frame-ancestors 'none'");
        ensure("Permissions-Policy",
               "camera=(), microphone=(), geolocation=(), payment=()");
        ensure("Cache-Control", "no-store");
        resp.add("Access-Control-Allow-Origin", "*");
        resp.add("Connection", "close");
        // Linux parity (web_casu.py log_message): access log on stderr.
        std::fprintf(stderr, "MPCASU Web: %s %s %d\n",
                     head.method.c_str(), head.path.c_str(), resp.status);
        std::fflush(stderr);
        std::vector<uint8_t> bytes = render_response(resp);
        socket->write(reinterpret_cast<const char*>(bytes.data()),
                      static_cast<qint64>(bytes.size()));
        if (!resp.file_path.empty() && head.method != "HEAD" && resp.file_length > 0) {
            std::ifstream f(resp.file_path, std::ios::binary);
            if (f) {
                f.seekg(resp.file_offset);
                std::vector<char> chunk(256 * 1024);
                int64_t remaining = resp.file_length;
                while (remaining > 0) {
                    int64_t want = std::min<int64_t>(remaining, static_cast<int64_t>(chunk.size()));
                    f.read(chunk.data(), static_cast<std::streamsize>(want));
                    std::streamsize got = f.gcount();
                    if (got <= 0) break;
                    socket->write(chunk.data(), got);
                    remaining -= got;
                }
            }
        }
    }
};

HTTPServer::HTTPServer() : impl_(new Impl) {}
HTTPServer::~HTTPServer() { stop(); }

bool HTTPServer::listen(uint16_t port, std::string* error) {
    if (!impl_->server.listen(QHostAddress::LocalHost, port)) {
        if (error) *error = impl_->server.errorString().toStdString();
        return false;
    }
    impl_->port = impl_->server.serverPort();
    QObject::connect(&impl_->server, &QTcpServer::newConnection, impl_.get(),
                     [this] { impl_->on_new_connection(); });
    return true;
}

uint16_t HTTPServer::port() const { return impl_->port; }

void HTTPServer::set_handler(std::shared_ptr<EndpointHandler> handler) {
    impl_->handler = handler ? std::move(handler) : std::make_shared<BasicEndpointHandler>();
}

void HTTPServer::set_limits(const RequestLimits& limits) { impl_->limits = limits; }

void HTTPServer::set_static_root(const std::string& root) { impl_->static_root = root; }

void HTTPServer::stop() {
    if (impl_->server.isListening()) impl_->server.close();
}

}  // namespace casu::webapi