// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/network/providers.hpp"

#include "casu/network/url.hpp"

#include <cctype>
#include <string>
#include <vector>

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

std::string substitute_query(const std::string& tpl, const std::string& query) {
    std::string out = tpl;
    size_t pos = out.find("{q}");
    if (pos != std::string::npos) {
        out.replace(pos, 3, url_encode(query));
    }
    return out;
}

}  // namespace

const std::vector<WebPlayerSpec>& web_player_specs() {
    static const std::vector<WebPlayerSpec> kSpecs = {
        {"spotify", "SPOTIFY", "https://open.spotify.com/",
         "https://open.spotify.com/search/{q}", "♪"},
        {"hearthis", "HEARTHIS", "https://hearthis.at/",
         "https://hearthis.at/search/?q={q}", "↗"},
        {"tidal", "TIDAL", "https://tidal.com/",
         "https://tidal.com/search?q={q}", "▤"},
        {"netflix", "NETFLIX", "https://www.netflix.com/browse",
         "https://www.netflix.com/search?q={q}", "▣"},
    };
    return kSpecs;
}

const WebPlayerSpec* web_player_spec(const std::string& provider) {
    std::string p = to_lower(trim(provider));
    for (const auto& spec : web_player_specs()) {
        if (spec.provider == p) return &spec;
    }
    return nullptr;
}

std::string web_player_url(const std::string& provider, const std::string& query,
                           const std::string& url) {
    const WebPlayerSpec* spec = web_player_spec(provider);
    if (!spec) spec = &web_player_specs()[0];
    if (!trim(url).empty()) return trim(url);
    if (!trim(query).empty()) return substitute_query(spec->search_template, query);
    return spec->home;
}

std::string provider_for_url(const std::string& url) {
    std::string low = to_lower(trim(url));
    for (const auto& spec : web_player_specs()) {
        std::string host = spec.home;
        size_t scheme = host.find("://");
        if (scheme != std::string::npos) host = host.substr(scheme + 3);
        size_t slash = host.find('/');
        if (slash != std::string::npos) host = host.substr(0, slash);
        if (low.find(host) != std::string::npos) return spec.provider;
    }
    return {};
}

std::string spotify_embed_url(const std::string& url) {
    std::string text = trim(url);
    Url u;
    if (!parse_url(text, &u) || u.scheme != "http" && u.scheme != "https") return text;
    std::string host = to_lower(u.host);
    if (host != "open.spotify.com") return text;
    std::string p = u.path;
    if (p.rfind("/embed/", 0) == 0) return text;
    size_t a = p.find('/');
    if (a == std::string::npos) return text;
    size_t b = p.find('/', a + 1);
    if (b == std::string::npos) return text;
    std::string kind = p.substr(a + 1, b - a - 1);
    std::string id = p.substr(b + 1);
    if (kind.empty() || id.empty()) return text;
    for (char c : id) {
        if (!std::isalnum(static_cast<unsigned char>(c))) return text;
    }
    return "https://open.spotify.com/embed/" + kind + "/" + id;
}

bool is_external_provider(const std::string& provider) {
    std::string p = to_lower(trim(provider));
    return p == "spotify" || p == "tidal";
}

}  // namespace casu::network