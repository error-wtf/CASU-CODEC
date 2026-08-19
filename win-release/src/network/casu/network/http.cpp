// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/network/http.hpp"

#include <QCoreApplication>
#include <QEventLoop>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QTimer>
#include <QUrl>
#include <QByteArray>

#include <cctype>
#include <string>

namespace casu::network {

namespace {

std::string to_lower(const std::string& s) {
    std::string r = s;
    for (char& c : r) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return r;
}

QByteArray to_qbytes(const std::string& s) {
    return QByteArray(s.data(), static_cast<int>(s.size()));
}

std::string from_bytes(const QByteArray& b) {
    return std::string(b.constData(), static_cast<size_t>(b.size()));
}

std::vector<uint8_t> to_bytes(const QByteArray& b) {
    const char* p = b.constData();
    return std::vector<uint8_t>(p, p + b.size());
}

}  // namespace

std::string HttpResponse::header(const std::string& name) const {
    std::string n = to_lower(name);
    for (const auto& h : headers) {
        if (to_lower(h.first) == n) return h.second;
    }
    return {};
}

std::string HttpResponse::text() const {
    return std::string(body.begin(), body.end());
}

class HttpClient::Impl {
public:
    QNetworkAccessManager nam;
};

HttpClient::HttpClient() : impl_(new Impl) {}
HttpClient::~HttpClient() = default;

HttpResponse HttpClient::request(const HttpRequest& req) {
    HttpResponse resp;
    if (!QCoreApplication::instance()) {
        resp.error = "HttpClient requires a QCoreApplication instance";
        return resp;
    }
    if (req.url.empty()) {
        resp.error = "empty request URL";
        return resp;
    }
    QUrl url(to_qbytes(req.url));
    if (!url.isValid()) {
        resp.error = "invalid request URL";
        return resp;
    }
    if (url.scheme() != "http" && url.scheme() != "https") {
        resp.error = "unsupported scheme: " + url.scheme().toStdString();
        return resp;
    }

    QNetworkRequest qr(url);
    qr.setTransferTimeout(req.timeout_ms);
    qr.setMaximumRedirectsAllowed(req.max_redirects);
    for (const auto& h : req.headers) {
        qr.setRawHeader(to_qbytes(h.first), to_qbytes(h.second));
    }
    qr.setRawHeader("User-Agent", to_qbytes(req.user_agent));
    if (!req.body.empty()) {
        qr.setHeader(QNetworkRequest::ContentLengthHeader, qint64(req.body.size()));
    }

    std::string method = req.method.empty() ? "GET" : req.method;
    QNetworkReply* reply = nullptr;
    const QByteArray body((const char*)req.body.data(), (int)req.body.size());
    if (method == "POST") {
        reply = impl_->nam.post(qr, body);
    } else if (method == "PUT") {
        reply = impl_->nam.put(qr, body);
    } else if (method == "DELETE") {
        reply = impl_->nam.deleteResource(qr);
    } else {
        reply = impl_->nam.get(qr);
    }

    QEventLoop loop;
    QTimer timer;
    timer.setSingleShot(true);
    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timer, &QTimer::timeout, &loop, &QEventLoop::quit);
    timer.start(req.timeout_ms);
    loop.exec();

    if (!reply->isFinished()) {
        resp.error = "request timed out";
    } else {
        int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        resp.status = status;
        resp.headers.clear();
        const auto pairs = reply->rawHeaderPairs();
        for (const auto& p : pairs) {
            resp.headers.emplace_back(from_bytes(p.first), from_bytes(p.second));
        }
        resp.body = to_bytes(reply->readAll());
        if (reply->error() != QNetworkReply::NoError) {
            resp.error = reply->errorString().toStdString();
        }
    }
    reply->deleteLater();
    return resp;
}

HttpResponse HttpClient::get(const std::string& url, int timeout_ms) {
    HttpRequest req;
    req.url = url;
    req.timeout_ms = timeout_ms;
    return request(req);
}

}  // namespace casu::network