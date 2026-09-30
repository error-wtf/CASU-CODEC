// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Legal web-player integrations (port of casu/webproviders.py). Each
// provider's official web player is opened in an embedded browser at the
// relevant URL (home / search / item). No streams are scraped/downloaded.
#pragma once
#include <string>
#include <vector>

namespace casu::web {

struct WebPlayerSpec {
    std::string key;    // "hearthis" | "netflix"
    std::string label;  // display label
    std::string home;   // home URL
    std::string icon;   // glyph
};

// All providers in display order (Hearthis/Netflix).
const std::vector<WebPlayerSpec>& web_players();

// Provider a URL belongs to (by domain), or empty.
std::string provider_for_url(const std::string& url);

// home / search / item URL for a provider.
std::string web_player_url(const std::string& provider,
                           const std::string& query = {},
                           const std::string& url = {});

// The general browser start page (DuckDuckGo).
std::string browse_url();

}  // namespace casu::web