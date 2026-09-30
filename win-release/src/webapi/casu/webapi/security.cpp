// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/webapi/security.hpp"

#include "casu/network/url.hpp"

#include <QHostAddress>
#include <QHostInfo>

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

// Parses a strict dotted-quad ("a.b.c.d", 0-255 each). No hex/octal tricks.
bool parse_ipv4(const std::string& s, uint32_t* out) {
    size_t start = 0;
    uint32_t value = 0;
    int octets = 0;
    for (int i = 0; i < 4; ++i) {
        size_t dot = (i < 3) ? s.find('.', start) : std::string::npos;
        if (i < 3 && dot == std::string::npos) return false;
        const std::string part = (dot == std::string::npos) ? s.substr(start)
                                                            : s.substr(start, dot - start);
        if (part.empty() || part.size() > 3 || !is_digits(part)) return false;
        long v = std::strtol(part.c_str(), nullptr, 10);
        if (v < 0 || v > 255) return false;
        value = (value << 8) | static_cast<uint32_t>(v);
        ++octets;
        if (dot == std::string::npos) {
            start = s.size();
            break;
        }
        start = dot + 1;
    }
    if (octets != 4 || start != s.size()) return false;  // trailing junk
    if (out) *out = value;
    return true;
}

bool ipv4_in_cidr(uint32_t ip, uint32_t net, int prefix) {
    if (prefix <= 0) return true;
    if (prefix > 32) return false;
    const uint32_t mask = (prefix == 32) ? 0xffffffffu : ~((1u << (32 - prefix)) - 1u);
    return (ip & mask) == (net & mask);
}

// Parses an IPv6 literal (with "::" compression and optional embedded IPv4
// tail) into 8 groups. Returns false on malformed input.
bool parse_ipv6(const std::string& s, uint16_t groups[8]) {
    std::string text = s;
    // Strip a zone id ("fe80::1%eth0") — never a target we want to allow.
    const size_t zone = text.find('%');
    if (zone != std::string::npos) text = text.substr(0, zone);
    if (text.empty()) return false;
    size_t double_colon = text.find("::");
    if (double_colon != std::string::npos) {
        if (text.find("::", double_colon + 1) != std::string::npos) return false;
    }
    // Split head/tail around "::" (if any).
    std::string head = text, tail;
    bool compressed = double_colon != std::string::npos;
    if (compressed) {
        head = text.substr(0, double_colon);
        tail = text.substr(double_colon + 2);
    }
    auto parse_part = [](const std::string& part, uint16_t out[8], int& count,
                         bool& has_v4_tail, uint32_t* v4) -> bool {
        count = 0;
        has_v4_tail = false;
        if (part.empty()) return true;
        size_t start = 0;
        while (start <= part.size()) {
            size_t colon = part.find(':', start);
            std::string piece = colon == std::string::npos ? part.substr(start)
                                                           : part.substr(start, colon - start);
            if (piece.find('.') != std::string::npos) {
                // Embedded IPv4 tail ("::ffff:1.2.3.4") — only valid last piece.
                if (colon != std::string::npos) return false;
                if (!parse_ipv4(piece, v4)) return false;
                has_v4_tail = true;
                ++count;  // counts as two groups
                break;
            }
            if (piece.empty() || piece.size() > 4) return false;
            for (char c : piece) {
                if (!std::isxdigit(static_cast<unsigned char>(c))) return false;
            }
            if (count >= 8) return false;
            out[count++] = static_cast<uint16_t>(std::strtoul(piece.c_str(), nullptr, 16));
            if (colon == std::string::npos) break;
            start = colon + 1;
            if (start == part.size()) return false;  // "1::2:" style junk
        }
        return true;
    };
    uint16_t hg[8] = {0}, tg[8] = {0};
    int hc = 0, tc = 0;
    bool hv4 = false, tv4 = false;
    uint32_t hv4a = 0, tv4a = 0;
    if (!parse_part(head, hg, hc, hv4, &hv4a)) return false;
    if (!parse_part(tail, tg, tc, tv4, &tv4a)) return false;
    int total = hc + tc + (hv4 ? 1 : 0) + (tv4 ? 1 : 0);
    if (hv4 && tv4) return false;
    if (compressed) {
        if (total > 7) return false;  // "::" must stand for at least one group
    } else if (total != 8) {
        return false;
    }
    for (int i = 0; i < hc; ++i) groups[i] = hg[i];
    int fill = compressed ? 8 - total : 0;
    for (int i = 0; i < fill; ++i) groups[hc + i] = 0;
    for (int i = 0; i < tc; ++i) groups[hc + fill + i] = tg[i];
    if (hv4) {
        groups[6] = static_cast<uint16_t>(hv4a >> 16);
        groups[7] = static_cast<uint16_t>(hv4a & 0xffff);
    } else if (tv4) {
        groups[6] = static_cast<uint16_t>(tv4a >> 16);
        groups[7] = static_cast<uint16_t>(tv4a & 0xffff);
    }
    return true;
}

bool ipv6_prefix_matches(const uint16_t g[8], const uint16_t prefix[8], int bits) {
    int full = bits / 16, rem = bits % 16;
    for (int i = 0; i < full && i < 8; ++i) {
        if (g[i] != prefix[i]) return false;
    }
    if (rem > 0 && full < 8) {
        const uint16_t mask = static_cast<uint16_t>(~((1u << (16 - rem)) - 1u));
        if (static_cast<uint16_t>(g[full] & mask) != prefix[full]) return false;
    }
    return true;
}

bool ipv4_is_private_or_reserved(uint32_t ip) {
    // Parity with the PHP catalog.php guard (FILTER_FLAG_NO_PRIV_RANGE |
    // FILTER_FLAG_NO_RES_RANGE) plus explicit cloud-metadata coverage.
    if (ipv4_in_cidr(ip, 0x00000000u, 8)) return true;    // 0.0.0.0/8 "this network"
    if (ipv4_in_cidr(ip, 0x0A000000u, 8)) return true;    // 10.0.0.0/8 private
    if (ipv4_in_cidr(ip, 0x64400000u, 10)) return true;   // 100.64.0.0/10 CGNAT
    if (ipv4_in_cidr(ip, 0x7F000000u, 8)) return true;    // 127.0.0.0/8 loopback
    if (ipv4_in_cidr(ip, 0xA9FE0000u, 16)) return true;   // 169.254.0.0/16 link-local + metadata
    if (ipv4_in_cidr(ip, 0xAC100000u, 12)) return true;   // 172.16.0.0/12 private
    if (ipv4_in_cidr(ip, 0xC0A80000u, 16)) return true;   // 192.168.0.0/16 private
    if (ipv4_in_cidr(ip, 0xC0000000u, 24)) return true;   // 192.0.0.0/24 IETF protocol
    if (ipv4_in_cidr(ip, 0xC0000200u, 24)) return true;   // 192.0.2.0/24 TEST-NET-1
    if (ipv4_in_cidr(ip, 0xC6120000u, 15)) return true;   // 198.18.0.0/15 benchmark
    if (ipv4_in_cidr(ip, 0xC6336400u, 24)) return true;   // 198.51.100.0/24 TEST-NET-2
    if (ipv4_in_cidr(ip, 0xCB007100u, 24)) return true;   // 203.0.113.0/24 TEST-NET-3
    if (ipv4_in_cidr(ip, 0xF0000000u, 4)) return true;    // 240.0.0.0/4 reserved/future
    if (ip == 0xFFFFFFFFu) return true;                   // 255.255.255.255 broadcast
    return false;
}

bool ipv6_is_private_or_reserved(const uint16_t g[8]) {
    static const uint16_t kUnspecified[8] = {0};
    if (ipv6_prefix_matches(g, kUnspecified, 128)) return true;   // ::
    static const uint16_t kLoopback[8] = {0, 0, 0, 0, 0, 0, 0, 1};
    if (ipv6_prefix_matches(g, kLoopback, 128)) return true;      // ::1
    static const uint16_t kV4Mapped[8] = {0, 0, 0, 0, 0, 0xFFFF, 0, 0};
    if (ipv6_prefix_matches(g, kV4Mapped, 96)) {                  // ::ffff:0:0/96
        // Classify the embedded IPv4 with the same rules.
        const uint32_t v4 = (static_cast<uint32_t>(g[6]) << 16) | g[7];
        return ipv4_is_private_or_reserved(v4);
    }
    static const uint16_t kUla[8] = {0xFC00, 0, 0, 0, 0, 0, 0, 0};
    if (ipv6_prefix_matches(g, kUla, 7)) return true;             // fc00::/7 ULA
    static const uint16_t kLinkLocal[8] = {0xFE80, 0, 0, 0, 0, 0, 0, 0};
    if (ipv6_prefix_matches(g, kLinkLocal, 10)) return true;      // fe80::/10 link-local
    static const uint16_t kDiscard[8] = {0x0100, 0, 0, 0, 0, 0, 0, 0};
    if (ipv6_prefix_matches(g, kDiscard, 64)) return true;        // 100::/64 discard-only
    static const uint16_t kDoc[8] = {0x2001, 0x0DB8, 0, 0, 0, 0, 0, 0};
    if (ipv6_prefix_matches(g, kDoc, 32)) return true;            // 2001:db8::/32 doc
    static const uint16_t kMulticast[8] = {0xFF00, 0, 0, 0, 0, 0, 0, 0};
    if (ipv6_prefix_matches(g, kMulticast, 8)) return true;       // ff00::/8 multicast
    static const uint16_t kV4Compat[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    if (ipv6_prefix_matches(g, kV4Compat, 96)) {                  // ::/96 IPv4-compatible
        const uint32_t v4 = (static_cast<uint32_t>(g[6]) << 16) | g[7];
        if (v4 != 0) return ipv4_is_private_or_reserved(v4);
    }
    return false;
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

bool is_private_or_reserved_ip(const std::string& ip) {
    // IPv6 literals contain ':'; anything else must be a dotted quad. Brackets
    // from URL hosts ("[::1]") are stripped here.
    std::string text = ip;
    if (!text.empty() && text.front() == '[' && text.back() == ']') {
        text = text.substr(1, text.size() - 2);
    }
    if (text.find(':') != std::string::npos) {
        uint16_t groups[8];
        if (!parse_ipv6(text, groups)) return true;  // unparseable → reject
        return ipv6_is_private_or_reserved(groups);
    }
    uint32_t v4 = 0;
    if (!parse_ipv4(text, &v4)) return true;         // unparseable → reject
    return ipv4_is_private_or_reserved(v4);
}

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
        // Full IPv6 literal classification (ULA fc00::/7, link-local fe80::/10,
        // IPv4-mapped, multicast, documentation …) — v7.8.1 hardening.
        return is_private_or_reserved_ip(h);
    }
    return is_private_ipv4(h);
}

bool resolves_to_public_addresses_only(const std::string& host) {
    // DNS-rebinding guard (PHP catalog.php parity): resolve the hostname and
    // reject if ANY resolved address is private/reserved. Uses QHostInfo's
    // blocking lookup — callers run this off the GUI thread or accept the
    // lookup cost (the web backend is a separate process with its own loop).
    std::string h = to_lower(trim(host));
    if (h.empty()) return false;
    if (!h.empty() && h.front() == '[' && h.back() == ']') {
        h = h.substr(1, h.size() - 2);
    }
    // Literal IP: classify directly.
    if (h.find(':') != std::string::npos ||
        (h.find('.') != std::string::npos &&
         h.find_first_not_of("0123456789.") == std::string::npos)) {
        return !is_private_or_reserved_ip(h);
    }
    if (h == "localhost") return false;
    const QHostInfo info = QHostInfo::fromName(QString::fromStdString(h));
    if (info.error() != QHostInfo::NoError) return false;  // fail closed
    const QList<QHostAddress> addresses = info.addresses();
    if (addresses.isEmpty()) return false;
    for (const QHostAddress& a : addresses) {
        if (is_private_or_reserved_ip(a.toString().toStdString())) return false;
    }
    return true;
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

bool is_allowed_catalog_target(const std::string& url) {
    // SSRF guard for /api/catalog-url (PHP catalog.php parity, v7.8.1):
    // http(s) only, no userinfo, and every resolved address of the host must
    // be public — literal IPs are classified directly, hostnames are resolved
    // and checked (DNS-rebinding: any private/reserved A/AAAA rejects).
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
    if (host == "localhost") return false;
    return resolves_to_public_addresses_only(host);
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