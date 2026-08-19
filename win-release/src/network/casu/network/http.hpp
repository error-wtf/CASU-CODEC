// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Synchronous HTTP(S) client over Qt6Network (QNetworkAccessManager) with
// timeouts and redirect following (WP-NET-001). Requires a QCoreApplication
// instance to be present when request() runs (standard Qt rule for event
// loops); request() fails fast with a clear error otherwise.
#pragma once
#include <cstdint>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace casu::network {

struct HttpResponse {
    int status = 0;
    std::vector<std::pair<std::string, std::string>> headers;
    std::vector<uint8_t> body;
    std::string error;

    std::string header(const std::string& name) const;
    std::string text() const;
};

struct HttpRequest {
    std::string url;
    std::string method = "GET";
    std::vector<std::pair<std::string, std::string>> headers;
    std::vector<uint8_t> body;
    std::string user_agent = "CASU-MPCASU/3.0";
    int timeout_ms = 20000;
    int max_redirects = 5;
};

class HttpClient {
public:
    HttpClient();
    ~HttpClient();
    HttpClient(const HttpClient&) = delete;
    HttpClient& operator=(const HttpClient&) = delete;

    HttpResponse request(const HttpRequest& req);
    HttpResponse get(const std::string& url, int timeout_ms = 20000);

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

}  // namespace casu::network