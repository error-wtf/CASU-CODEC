// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/network/url.hpp"

#include <cctype>
#include <cstdlib>
#include <set>
#include <string>

namespace casu::network {

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

bool parse_u16(const std::string& s, uint16_t* out) {
    if (s.empty() || s.size() > 5) return false;
    for (char c : s) if (!std::isdigit(static_cast<unsigned char>(c))) return false;
    long v = std::strtol(s.c_str(), nullptr, 10);
    if (v < 0 || v > 65535) return false;
    *out = static_cast<uint16_t>(v);
    return true;
}

int hex_val(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

bool parse_spotify(const std::string& s, std::string* kind, std::string* id) {
    std::string text = trim(s);
    if (text.find('\0') != std::string::npos) return false;
    const std::string prefix_http = "http://", prefix_https = "https://";
    if (text.rfind(prefix_http, 0) == 0) text = text.substr(prefix_http.size());
    else if (text.rfind(prefix_https, 0) == 0) text = text.substr(prefix_https.size());
    const std::string host = "open.spotify.com/";
    if (text.rfind(host, 0) != 0) return false;
    text = text.substr(host.size());
    auto slash = text.find('/');
    if (slash == std::string::npos || slash == 0) return false;
    std::string k = text.substr(0, slash);
    text = text.substr(slash + 1);
    if (text.size() < 22) return false;
    std::string i = text.substr(0, 22);
    for (char c : i) if (!std::isalnum(static_cast<unsigned char>(c))) return false;
    std::string rest = text.substr(22);
    if (!rest.empty() && rest[0] != '?' && rest[0] != '#') return false;
    if (kind) *kind = k;
    if (id) *id = i;
    return true;
}

}  // namespace

bool parse_url(const std::string& text, Url* out) {
    if (!out || text.empty()) return false;
    Url u;
    u.raw = text;
    std::string rest = text;
    size_t hash = rest.find('#');
    if (hash != std::string::npos) {
        u.fragment = rest.substr(hash + 1);
        rest = rest.substr(0, hash);
    }
    size_t colon = rest.find(':');
    bool has_scheme = false;
    if (colon != std::string::npos && colon > 0) {
        std::string cand = rest.substr(0, colon);
        bool valid = std::isalpha(static_cast<unsigned char>(cand[0])) != 0;
        for (size_t i = 1; i < cand.size() && valid; ++i) {
            unsigned char c = static_cast<unsigned char>(cand[i]);
            if (!std::isalnum(c) && c != '+' && c != '-' && c != '.') valid = false;
        }
        if (valid) {
            u.scheme = to_lower(cand);
            rest = rest.substr(colon + 1);
            has_scheme = true;
        }
    }
    if (!has_scheme) return false;

    if (rest.rfind("//", 0) == 0) {
        rest = rest.substr(2);
        size_t slash = rest.find('/');
        std::string auth = slash == std::string::npos ? rest : rest.substr(0, slash);
        rest = slash == std::string::npos ? std::string() : rest.substr(slash);
        size_t at = auth.rfind('@');
        if (at != std::string::npos) {
            u.userinfo = auth.substr(0, at);
            auth = auth.substr(at + 1);
        }
        if (!auth.empty() && auth[0] == '[') {
            size_t close = auth.find(']');
            if (close == std::string::npos) return false;
            u.host = auth.substr(0, close + 1);
            if (close + 1 < auth.size()) {
                if (auth[close + 1] != ':') return false;
                if (!parse_u16(auth.substr(close + 2), &u.port)) return false;
            }
        } else {
            size_t c = auth.rfind(':');
            if (c != std::string::npos) {
                if (!parse_u16(auth.substr(c + 1), &u.port)) return false;
                auth = auth.substr(0, c);
            }
            u.host = auth;
        }
    }
    size_t q = rest.find('?');
    if (q != std::string::npos) {
        u.query = rest.substr(q + 1);
        rest = rest.substr(0, q);
    }
    u.path = rest.empty() ? "/" : rest;
    *out = u;
    return true;
}

std::string url_encode(const std::string& s) {
    static const char* hexdig = "0123456789ABCDEF";
    std::string out;
    out.reserve(s.size() * 3);
    for (unsigned char c : s) {
        bool unreserved = std::isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~';
        if (unreserved) {
            out += static_cast<char>(c);
        } else {
            out += '%';
            out += hexdig[c >> 4];
            out += hexdig[c & 0x0F];
        }
    }
    return out;
}

std::string url_decode(const std::string& s) {
    std::string out;
    out.reserve(s.size());
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] == '%' && i + 2 < s.size()) {
            int hi = hex_val(s[i + 1]), lo = hex_val(s[i + 2]);
            if (hi >= 0 && lo >= 0) {
                out += static_cast<char>((hi << 4) | lo);
                i += 2;
                continue;
            }
        }
        out += s[i];
    }
    return out;
}

bool is_http_url(const std::string& s) {
    Url u;
    if (!parse_url(s, &u)) return false;
    return (u.scheme == "http" || u.scheme == "https") && !u.host.empty();
}

bool is_network_scheme(const std::string& scheme) {
    static const std::set<std::string> kNetworkSchemes = {
        "http", "https", "ftp", "ftps", "rtsp", "rtsps", "rtmp", "rtmps",
        "rtp", "udp", "srt", "rist", "smb", "mmsh", "mmst"};
    return kNetworkSchemes.count(to_lower(scheme)) > 0;
}

bool is_youtube_url(const std::string& s) {
    static const std::set<std::string> kYoutubeHosts = {
        "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
        "youtu.be", "www.youtu.be", "youtube-nocookie.com",
        "www.youtube-nocookie.com"};
    Url u;
    if (!parse_url(s, &u)) return false;
    if (u.scheme != "http" && u.scheme != "https") return false;
    return kYoutubeHosts.count(to_lower(u.host)) > 0;
}

bool is_spotify_url(const std::string& s) {
    return parse_spotify(s, nullptr, nullptr);
}

std::string spotify_id(const std::string& s) {
    std::string id;
    parse_spotify(s, nullptr, &id);
    return id;
}

std::string spotify_kind(const std::string& s) {
    std::string kind;
    parse_spotify(s, &kind, nullptr);
    return kind;
}

}  // namespace casu::network