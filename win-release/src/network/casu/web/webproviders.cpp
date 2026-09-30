// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/web/webproviders.hpp"

#include <cctype>
#include <regex>

namespace casu::web {

namespace {

struct Provider {
    const char* key;
    const char* label;
    const char* home;
    const char* icon;
};

const Provider kProviders[] = {
    {"hearthis", "HEARTHIS", "https://hearthis.at/", "\u2197"},
    {"netflix", "NETFLIX", "https://www.netflix.com/browse", "\u25A3"},
};

std::string lower(std::string s) {
    for (char& c : s)
        if (c >= 'A' && c <= 'Z') c = char(c - 'A' + 'a');
    return s;
}

std::string url_quote(const std::string& s) {
    // Minimal percent-encoding matching urllib.parse.quote for the characters
    // used in search queries (spaces and common punctuation). Only the
    // characters that break a URL are encoded.
    std::string out;
    const char* hex = "0123456789ABCDEF";
    for (unsigned char c : s) {
        bool safe = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                    (c >= '0' && c <= '9') || c == '-' || c == '_' ||
                    c == '.' || c == '~' || c == '/';
        if (safe) {
            out.push_back(char(c));
        } else {
            out.push_back('%');
            out.push_back(hex[c >> 4]);
            out.push_back(hex[c & 0xF]);
        }
    }
    return out;
}

}  // namespace

const std::vector<WebPlayerSpec>& web_players() {
    static const std::vector<WebPlayerSpec> value = [] {
        std::vector<WebPlayerSpec> out;
        for (const Provider& p : kProviders)
            out.push_back({p.key, p.label, p.home, p.icon});
        return out;
    }();
    return value;
}

std::string provider_for_url(const std::string& url) {
    std::string low = lower(url);
    for (const WebPlayerSpec& spec : web_players()) {
        std::string domain;
        if (spec.key == "hearthis") domain = "hearthis.at";
        else if (spec.key == "netflix") domain = "netflix.com";
        if (low.find(domain) != std::string::npos) return spec.key;
    }
    return {};
}


std::string web_player_url(const std::string& provider, const std::string& query,
                           const std::string& url) {
    const WebPlayerSpec* spec = nullptr;
    for (const WebPlayerSpec& s : web_players())
        if (s.key == provider) { spec = &s; break; }
    if (!spec) spec = &web_players()[0];  // default spotify
    if (!url.empty()) return url;
    if (!query.empty()) {
        if (provider == "spotify") return "https://open.spotify.com/search/" + url_quote(query);
        if (provider == "hearthis") return "https://hearthis.at/search/?q=" + url_quote(query);
        if (provider == "tidal") return "https://tidal.com/search?q=" + url_quote(query);
        if (provider == "netflix") return "https://www.netflix.com/search?q=" + url_quote(query);
    }
    return spec->home;
}

std::string browse_url() { return "https://duckduckgo.com/"; }

}  // namespace casu::web