// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CASU-Web-Backend — Windows-native web-casu loopback server (Phase C4).
// Binds 127.0.0.1, registers the web-casu endpoint handler (version/resolve/
// search/youtube-title/spotify-metadata/catalog-url/transcode/stream-proxy/
// media), serves the unmodified web/ frontend from next to the exe and shuts
// down cleanly on SIGINT/SIGTERM (stop server, temp-store cleanup).
#include "casu/codec.hpp"
#include "casu/json.hpp"
#include "casu/media.hpp"
#include "casu/network/network_error.hpp"
#include "casu/network/url.hpp"
#include "casu/webapi/http.hpp"
#include "casu/webapi/media_serve.hpp"
#include "casu/webapi/server.hpp"
#include "casu/webapi/transcode_store.hpp"
#include "casu/webapi/webapi_error.hpp"

#include <QCoreApplication>
#include <QTimer>

#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

namespace {
constexpr int kDefaultPort = 8765;
volatile std::sig_atomic_t g_shutdown = 0;
void handle_signal(int) { g_shutdown = 1; }
}  // namespace

namespace casu::webapi {
namespace {

std::string to_lower(const std::string& s) {
    std::string r = s;
    for (char& c : r) {
        if (c >= 'A' && c <= 'Z') c = static_cast<char>(c + ('a' - 'A'));
    }
    return r;
}

std::string error_json(const std::string& msg) {
    return casu::dump_json(casu::JsonValue(std::make_shared<casu::JsonObject>(
        casu::JsonObject{{{"error", casu::JsonValue(msg)}}})));
}

bool read_first_bytes(const std::string& path, char* out, size_t n) {
    std::ifstream f(path, std::ios::binary);
    if (!f) return false;
    f.read(out, static_cast<std::streamsize>(n));
    return f.gcount() == static_cast<std::streamsize>(n);
}

std::string media_content_type(bool video, bool audio, const std::string& target) {
    if (target == "webm") {
        return (video ? "video/webm" : (audio ? "audio/webm" : "application/octet-stream"));
    }
    return video ? "video/mp4" : (audio ? "audio/mp4" : "application/octet-stream");
}

// Mirrors web_casu.py _transcode_command for file-output transcodes.
std::vector<std::string> transcode_args(const std::string& source,
                                        bool video, bool audio,
                                        const std::string& output,
                                        const std::string& target) {
    std::vector<std::string> args = {
        "-nostdin", "-v", "error", "-i", source, "-map", "0:v:0?", "-map", "0:a:0?"};
    if (video) {
        if (target == "webm") {
            args.insert(args.end(),
                        {"-c:v", "libvpx-vp9", "-deadline", "realtime",
                         "-cpu-used", "6", "-crf", "30", "-b:v", "0"});
        } else {
            args.insert(args.end(),
                        {"-c:v", "libx264", "-preset", "veryfast",
                         "-crf", "20", "-pix_fmt", "yuv420p"});
        }
    } else {
        args.push_back("-vn");
    }
    if (audio) {
        if (target == "webm") {
            args.insert(args.end(), {"-c:a", "libopus", "-b:a", "160k"});
        } else {
            args.insert(args.end(), {"-c:a", "aac", "-b:a", "192k"});
        }
    } else {
        args.push_back("-an");
    }
    args.insert(args.end(), {"-sn", "-dn"});
    if (target == "mp4") args.insert(args.end(), {"-movflags", "+faststart"});
    args.insert(args.end(), {"-y", output});
    return args;
}

class WebBackendHandler : public BasicEndpointHandler {
public:
    HttpResponse handle_transcode_file(const HttpRequestHead& req, const uint8_t* data,
                                       size_t n, const std::string& filename,
                                       const std::string& target) override;
    HttpResponse handle_media(const HttpRequestHead& req,
                              const std::string& token) override;

private:
    std::string transcode_to(const std::string& source, bool video, bool audio,
                             const std::string& token, const std::string& target);
};

std::string WebBackendHandler::transcode_to(const std::string& source, bool video,
                                            bool audio, const std::string& token,
                                            const std::string& target) {
    std::string out = store().root() + "/media-" + token + "." + target;
    casu::codec::FfmpegRunOptions options;
    options.timeout_seconds = 600;
    try {
        casu::codec::Ffmpeg().run_checked(transcode_args(source, video, audio, out, target),
                                          options);
    } catch (const casu::codec::MediaTranscodeError& e) {
        std::error_code ec;
        std::filesystem::remove(out, ec);
        throw WebApiError(std::string("FFmpeg transcoding failed: ") + e.what());
    }
    std::error_code ec;
    if (!std::filesystem::is_regular_file(out, ec) ||
        std::filesystem::file_size(out, ec) == 0) {
        std::filesystem::remove(out, ec);
        throw WebApiError("FFmpeg transcoding produced no output");
    }
    return out;
}

HttpResponse WebBackendHandler::handle_transcode_file(const HttpRequestHead&, const uint8_t* data,
                                                      size_t n, const std::string& filename,
                                                      const std::string& target) {
    try {
        std::string t = to_lower(target);
        if (t != "mp4" && t != "webm") {
            throw WebApiError("unsupported browser transcode target");
        }
        std::string token = store().upload(data, n, filename, t);
        TranscodeSession uploaded;
        if (!store().get(token, &uploaded)) {
            throw WebApiError("upload could not be stored");
        }

        char magic[8] = {};
        const bool is_casu = read_first_bytes(uploaded.path, magic, sizeof(magic)) &&
                             (std::memcmp(magic, "CASUNAT1", 8) == 0 ||
                              std::memcmp(magic, "CASUNAT2", 8) == 0);

        std::string destination;
        bool video = false;
        bool audio = false;
        if (is_casu) {
            destination = store().root() + "/media-" + token + "." + t;
            try {
                casu::codec::export_casu(uploaded.path, destination);
            } catch (const casu::codec::CasuExportError& e) {
                throw WebApiError(std::string("CASU browser fallback failed: ") + e.what());
            }
            try {
                casu::media::MediaInfo info = casu::media::probe(destination);
                video = casu::media::has_stream(info, "video");
                audio = casu::media::has_stream(info, "audio");
            } catch (const casu::media::MediaProbeError&) {
                throw WebApiError("transcoded output could not be probed");
            }
        } else {
            casu::media::MediaInfo info;
            try {
                info = casu::media::probe(uploaded.path);
            } catch (const casu::media::MediaProbeError& e) {
                throw WebApiError(std::string("source has no probeable media: ") + e.what());
            }
            video = casu::media::has_stream(info, "video");
            audio = casu::media::has_stream(info, "audio");
            if (!video && !audio) {
                throw WebApiError("source has no playable audio or video stream");
            }
            destination = transcode_to(uploaded.path, video, audio, token, t);
        }
        store().remove(token);

        std::string content_type = media_content_type(video, audio, t);
        std::string final_token = store().register_file(destination, content_type, t);
        return json_response(200, casu::dump_json(casu::JsonValue(std::make_shared<casu::JsonObject>(
                                     casu::JsonObject{{{"url", casu::JsonValue("/api/media/" + final_token)},
                                                       {"kind", casu::JsonValue(video ? "video" : "audio")}}}))));
    } catch (const WebApiError& e) {
        return json_response(400, error_json(e.what()));
    } catch (const casu::media::MediaProbeError& e) {
        return json_response(400, error_json(e.what()));
    }
}

HttpResponse WebBackendHandler::handle_media(const HttpRequestHead& req,
                                             const std::string& token) {
    TranscodeSession session;
    if (!store().get(token, &session)) {
        return text_response(404, "not found");
    }
    if (session.kind == "url") {
        if (req.method != "GET") {
            return json_response(405, error_json("live transcoding requires GET"));
        }
        // Live transcode: pull the network source through ffmpeg into the temp
        // store, then serve it with full Range support like a file session.
        try {
            casu::media::MediaInfo info = casu::media::probe(session.source);
            bool video = casu::media::has_stream(info, "video");
            bool audio = casu::media::has_stream(info, "audio");
            if (!video && !audio) {
                throw WebApiError("source has no playable audio or video stream");
            }
            std::string target = session.target.empty() ? "mp4" : session.target;
            if (target != "mp4" && target != "webm") target = "mp4";
            std::string out = transcode_to(session.source, video, audio, token, target);
            std::string content_type = media_content_type(video, audio, target);
            store().remove(token);
            std::string final_token = store().register_file(out, content_type, target);
            return BasicEndpointHandler::handle_media(req, final_token);
        } catch (const WebApiError& e) {
            return json_response(502, error_json(e.what()));
        } catch (const casu::media::MediaProbeError& e) {
            return json_response(502, error_json(e.what()));
        }
    }
    return BasicEndpointHandler::handle_media(req, token);
}

}  // namespace
}  // namespace casu::webapi

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    QCoreApplication::setApplicationName("CASU-Web-Backend");
    QCoreApplication::setApplicationVersion("7.0.0");

    int port = kDefaultPort;
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--port") {
            if (i + 1 < argc) {
                port = std::atoi(argv[++i]);
            } else {
                std::fprintf(stderr, "web-casu: error: --port needs a value\n");
                return 2;
            }
        } else if (arg == "--help" || arg == "-h") {
            std::printf("usage: CASU-Web-Backend [--port <0-65535>]\n");
            return 0;
        } else if (arg.rfind("--port=", 0) == 0) {
            port = std::atoi(arg.c_str() + 7);
        }
    }
    if (port < 0 || port > 65535) {
        std::fprintf(stderr, "web-casu: error: --port must be between 0 and 65535\n");
        return 2;
    }

    std::string exe_dir = QCoreApplication::applicationDirPath().toStdString();

    // Point the bundled helper tools at next-to-exe binaries when present.
    auto set_tool_env = [&exe_dir](const char* env_key, const char* exe) {
        std::string candidate = exe_dir + "/tools/" + exe;
        std::error_code ec;
        if (std::filesystem::is_regular_file(candidate, ec)) {
            std::string v = env_key + std::string("=") + candidate;
            _putenv(v.data());
        }
    };
    set_tool_env("CASU_YTDLP", "yt-dlp.exe");
    set_tool_env("CASU_FFMPEG", "ffmpeg.exe");
    set_tool_env("CASU_FFPROBE", "ffprobe.exe");

    auto handler = std::make_shared<casu::webapi::WebBackendHandler>();
    casu::webapi::HTTPServer server;
    server.set_handler(handler);
    // Radio/stream proxy parity (web_casu.py _stream_proxy): relay any
    // http(s) target. The hardened ProxyPolicy keeps its SSRF guard for
    // loopback/private hosts.
    casu::webapi::ProxyPolicy proxy_policy;
    proxy_policy.allow_any_http = true;
    proxy_policy.allow_any_https = true;
    handler->set_proxy_policy(proxy_policy);
    server.set_static_root(exe_dir);

    std::string error;
    if (!server.listen(static_cast<uint16_t>(port), &error)) {
        std::fprintf(stderr, "web-casu: error: cannot bind local server: %s\n", error.c_str());
        return 2;
    }
    const uint16_t actual = server.port();
    std::printf("WEB CASU running at http://127.0.0.1:%u/web/\n", actual);
    std::fflush(stdout);

    std::signal(SIGINT, handle_signal);
    std::signal(SIGTERM, handle_signal);

    QTimer poll;
    QObject::connect(&poll, &QTimer::timeout, [&app] {
        if (g_shutdown) app.quit();
    });
    poll.start(200);

    QObject::connect(&app, &QCoreApplication::aboutToQuit, [&server, &handler] {
        server.stop();
        handler->store().close();
    });

    const int rc = app.exec();
    return rc == 0 ? 0 : rc;
}
