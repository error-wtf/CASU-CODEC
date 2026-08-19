// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// URL parsing, scheme validation and provider URL detection (ports of
// casu/locations.py + casu/spotify.py + casu/webproviders.py). Pure C++,
// no Qt, so it is usable by every shared library.
#pragma once
#include <cstdint>
#include <string>

namespace casu::network {

struct Url {
    std::string scheme;
    std::string host;
    std::string userinfo;
    std::string path;
    std::string query;
    std::string fragment;
    uint16_t port = 0;   // 0 = not specified
    std::string raw;
};

bool parse_url(const std::string& text, Url* out);
std::string url_encode(const std::string& s);
std::string url_decode(const std::string& s);
bool is_http_url(const std::string& s);
bool is_network_scheme(const std::string& scheme);
bool is_youtube_url(const std::string& s);
bool is_spotify_url(const std::string& s);
std::string spotify_id(const std::string& s);
std::string spotify_kind(const std::string& s);

}  // namespace casu::network