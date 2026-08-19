// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/webapi/security.hpp"

#include "casu/network/url.hpp"

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

bool is_digits(const std::string& s) {
    if (s.empty()) return false;
    for (char c : s) {
        if (!std::isdigit(static_cast<unsigned char>(c))) return false;
    }
    return true;
}

bool is_private_ipv4(const std::string& host) {
    if (host == "0.0.0.0") return true;
    size_t a = host.find('.');
    if (a == std::string::npos) return false;
    std::string first = host.substr(0, a);
    if (!is_digits(first)) return false;
    long octet = std::strtol(first.c_str(), nullptr, 10);
    if (octet == 127 || octet == 10) return true;
    if (octet == 192) {
        size_t b = host.find('.', a + 1);
        if (b != std::string::npos && host.substr(a + 1, b - a - 1) == "168") return true;
    }
    if (octet == 172) {
        size_t b = host.find('.', a + 1);
        if (b != std::string::npos) {
            std::string second = host.substr(a + 1, b - a - 1);
            if (is_digits(second)) {
                long o2 = std::strtol(second.c_str(), nullptr, 10);
                if (o2 >= 16 && o2 <= 31) return true;
            }
        }
    }
    if (octet == 169) {
        size_t b = host.find('.', a + 1);
        if (b != std::string::npos && host.substr(a + 1, b - a - 1) == "254") return true;
    }
    return false;
}

bool host_allowed(const std::string& host, const std::vector<std::string>& allowed) {
    std::string h = to_lower(host);
    for (const auto& a : allowed) {
        std::string rule = to_lower(a);
        if (rule.empty()) continue;
        if (h == rule) return true;
        if (h.size() > rule.size() && h.compare(h.size() - rule.size() - 1, rule.size() + 1,
                                                 "." + rule) == 0) {
            return true;
        }
    }
    return false;
}

}  // namespace

bool is_trusted_loopback_host(const std::string& host_header, uint16_t port) {
    std::string host = to_lower(trim(host_header));
    std::string p = std::to_string(port);
    return host == "127.0.0.1:" + p || host == "localhost:" + p || host == "[::1]:" + p;
}

bool is_loopback_or_private_host(const std::string& host) {
    std::string h = to_lower(trim(host));
    if (h.empty()) return true;
    if (h == "localhost" || h == "::1" || h == "[::1]" || h == "::" || h == "0.0.0.0") return true;
    size_t end = h.find(']');
    if (h[0] == '[' && end != std::string::npos) {
        return h.substr(0, end + 1) == "[::1]" || h.substr(0, end + 1) == "[::]";
    }
    if (h.find(':') != std::string::npos) {
        return h == "::1" || h == "::";
    }
    return is_private_ipv4(h);
}

bool is_allowed_proxy_target(const std::string& url, const ProxyPolicy& policy) {
    casu::network::Url u;
    if (!casu::network::parse_url(url, &u)) return false;
    if (u.scheme != "http" && u.scheme != "https") return false;
    if (!u.userinfo.empty()) return false;
    std::string host = to_lower(u.host);
    if (host.empty()) return false;
    if (host[0] == '[') {
        std::string inner = host.substr(1, host.find(']') == std::string::npos ? std::string::npos : host.find(']') - 1);
        host = inner.empty() ? host : inner;
    }
    if (is_loopback_or_private_host(host)) return false;
    if (host_allowed(host, policy.allowed_hosts)) return true;
    if (u.scheme == "http" && policy.allow_any_http) return true;
    if (u.scheme == "https" && policy.allow_any_https) return true;
    return false;
}

bool is_safe_path_segment(const std::string& seg) {
    if (seg.empty() || seg == "." || seg == "..") return false;
    if (seg.find('\0') != std::string::npos) return false;
    for (char c : seg) {
        if (c == '/' || c == '\\') return false;
    }
    return true;
}

std::string normalize_path(const std::string& p) {
    std::string s = p;
    for (char& c : s) {
        if (c == '\\') c = '/';
    }
    std::vector<std::string> parts;
    std::string cur;
    for (char c : s) {
        if (c == '/') {
            if (!cur.empty()) {
                parts.push_back(cur);
                cur.clear();
            }
        } else {
            cur += c;
        }
    }
    if (!cur.empty()) parts.push_back(cur);
    std::vector<std::string> out;
    for (const auto& part : parts) {
        if (part == ".") continue;
        if (part == "..") {
            if (!out.empty()) out.pop_back();
            continue;
        }
        out.push_back(part);
    }
    std::string result;
    for (size_t i = 0; i < out.size(); ++i) {
        result += "/";
        result += out[i];
    }
    return result.empty() ? "/" : result;
}

bool is_within_root(const std::string& path, const std::string& root) {
    std::string n = normalize_path(path);
    std::string r = normalize_path(root);
    if (r == "/") return true;
    if (n == r) return true;
    return n.size() > r.size() && n.compare(0, r.size(), r) == 0 && n[r.size()] == '/';
}

std::string sanitize_filename(const std::string& name) {
    std::string text = casu::network::url_decode(name);
    std::string base = text;
    for (size_t i = base.size(); i > 0; --i) {
        if (base[i - 1] == '/' || base[i - 1] == '\\') {
            base = base.substr(i);
            break;
        }
    }
    base = trim(base);
    if (base.empty() || base == "." || base == "..") base = "media";
    std::string clean;
    for (char c : base) {
        if (c == '/' || c == '\\' || c == '\0') continue;
        clean += c;
    }
    if (clean.empty()) clean = "media";
    if (clean.size() > 128) clean.resize(128);
    return clean;
}

}  // namespace casu::webapi