// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Loopback HTTP server skeleton for the web API (WP-WEBAPI-001/002).
// Binds 127.0.0.1 only, validates the Host header against DNS rebinding,
// enforces request size caps and routes to an EndpointHandler. Range/HEAD
// media serving reuses the shared casu_network primitives via media_serve.
// The full endpoint logic (transcode pipelines, EPG catalog) is completed by
// the app phase (casu_web_backend) on top of this contract.
#pragma once
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "casu/webapi/http.hpp"
#include "casu/webapi/security.hpp"
#include "casu/webapi/transcode_store.hpp"

namespace casu::webapi {

inline constexpr const char* kWebApiVersion = "3.0.0";

class EndpointHandler {
public:
    virtual ~EndpointHandler() = default;

    virtual HttpResponse handle_version(const HttpRequestHead& req);
    virtual HttpResponse handle_resolve(const HttpRequestHead& req, const std::string& body_json);
    virtual HttpResponse handle_search(const HttpRequestHead& req, const std::string& body_json);
    virtual HttpResponse handle_youtube_title(const HttpRequestHead& req, const std::string& body_json);
    virtual HttpResponse handle_spotify_metadata(const HttpRequestHead& req, const std::string& body_json);
    virtual HttpResponse handle_catalog_url(const HttpRequestHead& req, const std::string& body_json);
    virtual HttpResponse handle_transcode_url(const HttpRequestHead& req, const std::string& body_json);
    virtual HttpResponse handle_transcode_file(const HttpRequestHead& req, const uint8_t* data,
                                               size_t n, const std::string& filename,
                                               const std::string& target);
    virtual HttpResponse handle_stream_proxy(const HttpRequestHead& req, const std::string& target_url);
    virtual HttpResponse handle_media(const HttpRequestHead& req, const std::string& token);
};

class BasicEndpointHandler : public EndpointHandler {
public:
    BasicEndpointHandler() = default;

    TranscodeStore& store() { return store_; }
    const ProxyPolicy& proxy_policy() const { return policy_; }
    void set_proxy_policy(const ProxyPolicy& p) { policy_ = p; }

    HttpResponse handle_version(const HttpRequestHead& req) override;
    HttpResponse handle_resolve(const HttpRequestHead& req, const std::string& body_json) override;
    HttpResponse handle_search(const HttpRequestHead& req, const std::string& body_json) override;
    HttpResponse handle_youtube_title(const HttpRequestHead& req, const std::string& body_json) override;
    HttpResponse handle_spotify_metadata(const HttpRequestHead& req, const std::string& body_json) override;
    HttpResponse handle_catalog_url(const HttpRequestHead& req, const std::string& body_json) override;
    HttpResponse handle_transcode_url(const HttpRequestHead& req, const std::string& body_json) override;
    HttpResponse handle_transcode_file(const HttpRequestHead& req, const uint8_t* data,
                                       size_t n, const std::string& filename,
                                       const std::string& target) override;
    HttpResponse handle_stream_proxy(const HttpRequestHead& req, const std::string& target_url) override;
    HttpResponse handle_media(const HttpRequestHead& req, const std::string& token) override;

private:
    TranscodeStore store_;
    ProxyPolicy policy_;
};

class HTTPServer {
public:
    HTTPServer();
    ~HTTPServer();
    HTTPServer(const HTTPServer&) = delete;
    HTTPServer& operator=(const HTTPServer&) = delete;

    bool listen(uint16_t port, std::string* error = nullptr);
    uint16_t port() const;
    void set_handler(std::shared_ptr<EndpointHandler> handler);
    void set_limits(const RequestLimits& limits);
    void set_static_root(const std::string& root);
    void stop();

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

}  // namespace casu::webapi