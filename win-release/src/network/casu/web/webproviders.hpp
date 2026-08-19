// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Legal web-player integrations (port of casu/webproviders.py). Each
// provider's official web player is opened in an embedded browser at the
// relevant URL (home / search / item). No streams are scraped/downloaded.
#pragma once
#include <string>
#include <vector>

namespace casu::web {

struct WebPlayerSpec {
    std::string key;    // "spotify" | "hearthis" | "tidal" | "netflix"
    std::string label;  // display label
    std::string home;   // home URL
    std::string icon;   // glyph
};

// All providers in display order (Spotify/Hearthis/Tidal/Netflix).
const std::vector<WebPlayerSpec>& web_players();

// Spotify and Tidal encrypt audio with Widevine DRM, which the embedded
// QtWebEngine build does not bundle; they open in the system browser instead
// (see casu/webproviders.py EXTERNAL_PROVIDERS).
bool is_external_provider(const std::string& provider);

// Provider a URL belongs to (by domain), or empty.
std::string provider_for_url(const std::string& url);

// Convert a Spotify item URL to its official embed URL; unchanged otherwise.
std::string spotify_embed_url(const std::string& url);

// home / search / item URL for a provider.
std::string web_player_url(const std::string& provider,
                           const std::string& query = {},
                           const std::string& url = {});

// The general browser start page (DuckDuckGo).
std::string browse_url();

}  // namespace casu::web