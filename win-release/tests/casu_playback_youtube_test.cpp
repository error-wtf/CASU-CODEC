// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// YouTube loopback transport test (WP-MPCASU-041). Starts the app's
// YoutubeProxy in local-file mode (offline), fetches the loopback URL with
// Range requests via Qt6Network, and asserts 206 + Content-Range + correct
// byte ranges. Validates the Range/206 transport the app feeds to
// LibVLCBackend for YouTube, without needing the network.
#include "casu/network/range.hpp"
#include "youtube_proxy.hpp"

#include <QCoreApplication>
#include <QEventLoop>
#include <QFile>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QUrl>

#include <cstdio>

using namespace mpcasu;
using namespace casu::network::range;

namespace {
int failures = 0;
void check(bool ok, const char* label) {
    if (!ok) { ++failures; std::printf("FAIL %s\n", label); }
    else std::printf("ok   %s\n", label);
}
}  // namespace

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    if (argc < 2) {
        std::printf("FAIL usage: casu_playback_youtube_test <media_file>\n");
        return 2;
    }
    const QString media = QString::fromLocal8Bit(argv[1]);

    YoutubeProxy proxy;
    QString err;
    check(proxy.start_local(media, &err), "proxy start_local");
    if (!proxy.is_running()) {
        std::printf("proxy error: %s\n", err.toUtf8().constData());
        return 1;
    }
    const QString url = proxy.media_url();
    check(url.startsWith("http://127.0.0.1:"), "loopback URL on 127.0.0.1");
    const QUrl parsed(url);
    check(parsed.port() == proxy.port(), "URL port matches server");

    QNetworkAccessManager nam;
    QEventLoop loop;

    // Full fetch with an open range.
    {
        QNetworkRequest req{QUrl(url)};
        req.setRawHeader("Range", "bytes=0-");
        QNetworkReply* reply = nam.get(req);
        QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
        loop.exec();
        const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        const QByteArray body = reply->readAll();
        check(status == 200, "open range returns 200 for full file");
        QFile f(media);
        f.open(QIODevice::ReadOnly);
        const QByteArray expected = f.readAll();
        f.close();
        check(body == expected, "open range serves full file bytes");
        reply->deleteLater();
    }

    // Partial range: bytes=100-199.
    {
        QNetworkRequest req{QUrl(url)};
        req.setRawHeader("Range", "bytes=100-199");
        QNetworkReply* reply = nam.get(req);
        QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
        loop.exec();
        const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        const QByteArray cr = reply->rawHeader("Content-Range");
        const QByteArray body = reply->readAll();
        check(status == 206, "partial range returns 206");
        check(body.size() == 100, "partial range returns 100 bytes");
        ContentRange parsed_cr = parse_content_range(cr.toStdString());
        check(parsed_cr.ok && parsed_cr.start == 100 && parsed_cr.end == 199,
              "Content-Range header 100-199");
        QFile f(media);
        f.open(QIODevice::ReadOnly);
        const QByteArray all = f.readAll();
        f.close();
        check(body == all.mid(100, 100), "partial range byte-exact");
        reply->deleteLater();
    }

    // Suffix range: bytes=-64 (last 64 bytes).
    {
        QFile f(media);
        f.open(QIODevice::ReadOnly);
        f.close();
        QNetworkRequest req{QUrl(url)};
        req.setRawHeader("Range", "bytes=-64");
        QNetworkReply* reply = nam.get(req);
        QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
        loop.exec();
        const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        const QByteArray body = reply->readAll();
        check(status == 206, "suffix range returns 206");
        check(body.size() == 64, "suffix range returns 64 bytes");
        reply->deleteLater();
    }

    // HEAD request.
    {
        QNetworkRequest req{QUrl(url)};
        QNetworkReply* reply = nam.head(req);
        QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
        loop.exec();
        const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        check(status == 200, "HEAD returns 200");
        reply->deleteLater();
    }

    proxy.stop();
    check(!proxy.is_running(), "proxy stops");

    std::printf(failures == 0 ? "ALL PASS\n" : "%d FAILURES\n", failures);
    return failures == 0 ? 0 : 1;
}
