// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Integration test for the web-casu backend server (Phase C4). Starts the
// HTTPServer in-process on 127.0.0.1 (port 8497) with the BasicEndpointHandler
// and the deployed frontend as static root, then drives it with real HTTP:
// version/static/security (DNS rebinding) and Range media serving.
#include "casu/network/http.hpp"
#include "casu/network/url.hpp"
#include "casu/webapi/http.hpp"
#include "casu/webapi/server.hpp"
#include "casu/webapi/transcode_store.hpp"

#include <QCoreApplication>
#include <QEventLoop>
#include <QHostAddress>
#include <QTcpSocket>
#include <QTimer>

#include <cstdio>
#include <filesystem>
#include <string>
#include <vector>

using namespace casu::webapi;

namespace {

int failures = 0;
void check(bool ok, const char* label) {
    if (!ok) { ++failures; std::printf("FAIL %s\n", label); }
    else std::printf("ok   %s\n", label);
}

bool contains(const std::string& text, const std::string& needle) {
    return text.find(needle) != std::string::npos;
}

std::string raw_request(const std::string& payload, uint16_t port) {
    QEventLoop loop;
    QTcpSocket sock;
    QByteArray resp;
    QObject::connect(&sock, &QTcpSocket::readyRead, [&] { resp += sock.readAll(); });
    QObject::connect(&sock, &QTcpSocket::disconnected, &loop, &QEventLoop::quit);
    QTimer deadline;
    deadline.setSingleShot(true);
    QObject::connect(&deadline, &QTimer::timeout, &loop, &QEventLoop::quit);
    sock.connectToHost(QHostAddress::LocalHost, port);
    if (!sock.waitForConnected(3000)) return {"<no-connect>"};
    sock.write(payload.data(), static_cast<qint64>(payload.size()));
    deadline.start(6000);
    loop.exec();
    resp += sock.readAll();
    return std::string(resp.constData(), static_cast<size_t>(resp.size()));
}

}  // namespace

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);

    constexpr uint16_t kPort = 8497;
    std::string site = QCoreApplication::applicationDirPath().toStdString() + "/site";
    if (!std::filesystem::is_directory(site)) {
        std::printf("FAIL site root missing: %s\n", site.c_str());
        return 1;
    }

    HTTPServer server;
    auto handler = std::make_shared<BasicEndpointHandler>();
    server.set_handler(handler);
    server.set_static_root(site);
    std::string error;
    if (!server.listen(kPort, &error)) {
        std::printf("FAIL cannot bind: %s\n", error.c_str());
        return 1;
    }

    casu::network::HttpClient client;
    const std::string base = "http://127.0.0.1:" + std::to_string(kPort);

    // --- /api/version ---
    {
        casu::network::HttpResponse r = client.get(base + "/api/version");
        check(r.status == 200, "GET /api/version -> 200");
        check(contains(r.text(), "\"version\""), "version payload has version field");
        check(contains(r.text(), "3.0.0"), "version payload is 3.0.0");
    }

    // --- static index + frontend ---
    {
        casu::network::HttpResponse root = client.get(base + "/");
        check(root.status == 200, "GET / -> static index 200");
        check(contains(root.text(), "WEB CASU Player"), "index serves the frontend shell");

        casu::network::HttpResponse web = client.get(base + "/web/");
        check(web.status == 200, "GET /web/ -> frontend 200");
        check(contains(web.text(), "WEB CASU Player"), "/web/ serves index.html");

        casu::network::HttpResponse css = client.get(base + "/web/styles.css");
        check(css.status == 200 && contains(css.header("content-type"), "text/css"),
              "/web/styles.css served as CSS");

        casu::network::HttpResponse asset = client.get(base + "/assets/web_casu_icon.png");
        check(asset.status == 200 && contains(asset.header("content-type"), "image/png"),
              "/assets/web_casu_icon.png served as PNG");

        casu::network::HttpResponse missing = client.get(base + "/nope");
        check(missing.status == 404, "GET unknown path -> 404");

        casu::network::HttpResponse traverse = client.get(base + "/web/../secret");
        check(traverse.status == 403 || traverse.status == 404, "path traversal rejected");
    }

    // --- DNS-rebinding host rejection (raw Host header) ---
    {
        std::string resp = raw_request(
            "GET /api/version HTTP/1.1\r\nHost: evil.example.com:" + std::to_string(kPort) +
                "\r\nConnection: close\r\n\r\n",
            kPort);
        check(contains(resp, "421"), "DNS-rebinding Host -> 421");

        resp = raw_request(
            "POST /api/resolve HTTP/1.1\r\nHost: evil.example.com:" +
                std::to_string(kPort) +
                "\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}",
            kPort);
        check(contains(resp, "421"), "DNS-rebinding POST -> 421");
    }

    // --- /api/resolve contract (no network) ---
    {
        casu::network::HttpRequest req;
        req.url = base + "/api/resolve";
        req.method = "POST";
        req.headers.emplace_back("Content-Type", "application/json");
        req.body = std::vector<uint8_t>({'e', 'm', 'p', 't', 'y'});
        casu::network::HttpResponse r = client.request(req);
        check(r.status == 400, "POST /api/resolve with no JSON body -> 400");
        check(contains(r.text(), "\"error\""), "resolve error is JSON");
    }

    // --- Range media serving via a real token ---
    {
        std::string token = handler->store().upload(std::string("0123456789abcdef"),
                                                    "clip.mp4", "mp4");
        casu::network::HttpRequest req;
        req.url = base + "/api/media/" + token;
        req.headers.emplace_back("Range", "bytes=0-3");
        casu::network::HttpResponse part = client.request(req);
        check(part.status == 206 && part.text() == "0123", "media range bytes=0-3 -> 206/0123");
        check(contains(part.header("content-range"), "bytes 0-3/16"), "media content-range");

        req.headers.clear();
        req.headers.emplace_back("Range", "bytes=999-");
        casu::network::HttpResponse over = client.request(req);
        check(over.status == 416, "unsatisfiable media range -> 416");

        req.headers.clear();
        req.headers.emplace_back("Range", "bytes=abc");
        casu::network::HttpResponse bad = client.request(req);
        check(bad.status == 416, "malformed media range -> 416");

        casu::network::HttpResponse missing =
            client.get(base + "/api/media/does-not-exist");
        check(missing.status == 404, "unknown media token -> 404");
    }

    handler->store().close();
    server.stop();

    std::printf(failures == 0 ? "ALL PASS\n" : "%d FAILURES\n", failures);
    return failures == 0 ? 0 : 1;
}
