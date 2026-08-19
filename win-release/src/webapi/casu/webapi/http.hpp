// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// HTTP request-head parsing and response rendering for the loopback web API
// (WP-WEBAPI-001). Pure C++, no Qt, so request/limits/range logic is unit
// testable without an event loop. Enforces request size caps and rejects
// malformed headers fail-closed.
#pragma once
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace casu::webapi {

struct RequestLimits {
    uint64_t max_json_bytes = 64 * 1024;              // JSON request bodies
    uint64_t max_catalog_bytes = 32 * 1024 * 1024;    // catalog-url documents
    uint64_t max_upload_bytes = 16ULL * 1024 * 1024 * 1024;  // transcode-file uploads
    uint64_t max_request_line = 8 * 1024;
    uint64_t max_header_bytes = 32 * 1024;
    size_t max_header_count = 128;
};

struct HttpRequestHead {
    bool ok = false;
    std::string error;   // reason when !ok
    std::string method;
    std::string target;
    std::string version;
    std::vector<std::pair<std::string, std::string>> headers;
    std::string path;    // target without query
    std::string query;
    size_t head_bytes = 0;  // bytes consumed up to end of the header block

    std::string header(const std::string& name) const;
    uint64_t content_length() const;
};

enum class ParseStatus { Incomplete, Error, Complete };

ParseStatus parse_request_head(const uint8_t* data, size_t n,
                               const RequestLimits& limits, HttpRequestHead* out);

struct HttpHeader {
    std::string name;
    std::string value;
};

struct HttpResponse {
    int status = 501;
    std::vector<HttpHeader> headers;
    std::vector<uint8_t> body;
    std::string file_path;    // when set the body is streamed from this file
    int64_t file_offset = 0;
    int64_t file_length = 0;

    HttpResponse& add(const std::string& name, const std::string& value);
    HttpResponse& json(const std::string& body_text);
};

const char* reason_phrase(int status);
std::vector<uint8_t> render_response(const HttpResponse& r);
HttpResponse json_response(int status, const std::string& body_text);
HttpResponse text_response(int status, const std::string& body_text,
                           const std::string& content_type = "text/plain; charset=utf-8");

}  // namespace casu::webapi