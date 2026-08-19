// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/webapi/http.hpp"

#include <cctype>
#include <cstdint>
#include <string>
#include <vector>

namespace casu::webapi {

namespace {

std::string to_lower(const std::string& s) {
    std::string r = s;
    for (char& c : r) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return r;
}

std::string trim(const std::string& s) {
    std::string r = s;
    while (!r.empty() && std::isspace(static_cast<unsigned char>(r.front()))) r.erase(r.begin());
    while (!r.empty() && std::isspace(static_cast<unsigned char>(r.back()))) r.pop_back();
    return r;
}

size_t find_header_end(const uint8_t* data, size_t n, size_t* term_len) {
    for (size_t i = 0; i + 1 < n; ++i) {
        if (data[i] == '\r' && data[i + 1] == '\n' && i + 3 < n &&
            data[i + 2] == '\r' && data[i + 3] == '\n') {
            *term_len = 4;
            return i;
        }
        if (data[i] == '\n' && i + 1 < n && data[i + 1] == '\n') {
            *term_len = 2;
            return i;
        }
    }
    return std::string::npos;
}

bool valid_header_name(const std::string& name) {
    if (name.empty()) return false;
    for (char c : name) {
        if (c <= ' ' || c == ':' || c == '\r' || c == '\n') return false;
    }
    return true;
}

}  // namespace

std::string HttpRequestHead::header(const std::string& name) const {
    std::string n = to_lower(name);
    for (const auto& h : headers) {
        if (to_lower(h.first) == n) return h.second;
    }
    return {};
}

uint64_t HttpRequestHead::content_length() const {
    std::string v = trim(header("content-length"));
    if (v.empty()) return 0;
    for (char c : v) {
        if (!std::isdigit(static_cast<unsigned char>(c))) return 0;
    }
    uint64_t total = 0;
    for (char c : v) {
        total = total * 10 + static_cast<uint64_t>(c - '0');
    }
    return total;
}

ParseStatus parse_request_head(const uint8_t* data, size_t n,
                               const RequestLimits& limits, HttpRequestHead* out) {
    size_t term_len = 0;
    size_t end = find_header_end(data, n, &term_len);
    if (end == std::string::npos) {
        if (n >= limits.max_header_bytes) {
            if (out) {
                out->ok = false;
                out->error = "request headers too large";
            }
            return ParseStatus::Error;
        }
        return ParseStatus::Incomplete;
    }

    HttpRequestHead h;
    h.head_bytes = end + term_len;

    std::string block(reinterpret_cast<const char*>(data), end);
    size_t line_start = 0;
    std::vector<std::string> lines;
    while (line_start <= block.size()) {
        size_t nl = block.find('\n', line_start);
        std::string line = block.substr(
            line_start, nl == std::string::npos ? std::string::npos : nl - line_start);
        if (!line.empty() && line.back() == '\r') line.pop_back();
        lines.push_back(line);
        if (nl == std::string::npos) break;
        line_start = nl + 1;
    }
    if (lines.empty()) {
        h.ok = false;
        h.error = "empty request";
        *out = h;
        return ParseStatus::Error;
    }

    if (lines[0].size() > limits.max_request_line) {
        h.ok = false;
        h.error = "request line too long";
        *out = h;
        return ParseStatus::Error;
    }

    size_t s1 = lines[0].find(' ');
    size_t s2 = lines[0].rfind(' ');
    if (s1 == std::string::npos || s2 == s1) {
        h.ok = false;
        h.error = "malformed request line";
        *out = h;
        return ParseStatus::Error;
    }
    h.method = lines[0].substr(0, s1);
    h.target = lines[0].substr(s1 + 1, s2 - s1 - 1);
    h.version = lines[0].substr(s2 + 1);
    for (char& c : h.method) {
        c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    }

    if (lines.size() - 1 > limits.max_header_count) {
        h.ok = false;
        h.error = "too many headers";
        *out = h;
        return ParseStatus::Error;
    }
    for (size_t i = 1; i < lines.size(); ++i) {
        std::string& line = lines[i];
        if (line.empty()) continue;
        size_t colon = line.find(':');
        if (colon == std::string::npos) {
            h.ok = false;
            h.error = "malformed header line";
            *out = h;
            return ParseStatus::Error;
        }
        std::string name = line.substr(0, colon);
        if (!valid_header_name(name)) {
            h.ok = false;
            h.error = "malformed header name";
            *out = h;
            return ParseStatus::Error;
        }
        std::string value = trim(line.substr(colon + 1));
        h.headers.emplace_back(to_lower(name), value);
    }

    size_t q = h.target.find('?');
    if (q != std::string::npos) {
        h.path = h.target.substr(0, q);
        h.query = h.target.substr(q + 1);
    } else {
        h.path = h.target;
    }
    h.ok = true;
    *out = h;
    return ParseStatus::Complete;
}

HttpResponse& HttpResponse::add(const std::string& name, const std::string& value) {
    headers.push_back({name, value});
    return *this;
}

HttpResponse& HttpResponse::json(const std::string& body_text) {
    add("Content-Type", "application/json; charset=utf-8");
    body.assign(body_text.begin(), body_text.end());
    return *this;
}

const char* reason_phrase(int status) {
    switch (status) {
        case 200: return "OK";
        case 206: return "Partial Content";
        case 400: return "Bad Request";
        case 403: return "Forbidden";
        case 404: return "Not Found";
        case 405: return "Method Not Allowed";
        case 413: return "Payload Too Large";
        case 414: return "URI Too Long";
        case 416: return "Range Not Satisfiable";
        case 421: return "Misdirected Request";
        case 431: return "Request Header Fields Too Large";
        case 501: return "Not Implemented";
        case 502: return "Bad Gateway";
        default: return "Unknown";
    }
}

std::vector<uint8_t> render_response(const HttpResponse& r) {
    std::string head = "HTTP/1.1 " + std::to_string(r.status) + " " +
                       reason_phrase(r.status) + "\r\n";
    bool has_length = false;
    for (const auto& h : r.headers) {
        head += h.name + ": " + h.value + "\r\n";
        if (to_lower(h.name) == "content-length") has_length = true;
    }
    uint64_t length = static_cast<uint64_t>(r.body.size());
    if (!r.file_path.empty() && r.file_length >= 0) {
        length = static_cast<uint64_t>(r.file_length);
    }
    if (!has_length) head += "Content-Length: " + std::to_string(length) + "\r\n";
    head += "\r\n";

    std::vector<uint8_t> out;
    out.reserve(head.size() + r.body.size());
    out.insert(out.end(), head.begin(), head.end());
    out.insert(out.end(), r.body.begin(), r.body.end());
    return out;
}

HttpResponse json_response(int status, const std::string& body_text) {
    HttpResponse r;
    r.status = status;
    r.json(body_text);
    return r;
}

HttpResponse text_response(int status, const std::string& body_text,
                           const std::string& content_type) {
    HttpResponse r;
    r.status = status;
    r.add("Content-Type", content_type);
    r.body.assign(body_text.begin(), body_text.end());
    return r;
}

}  // namespace casu::webapi