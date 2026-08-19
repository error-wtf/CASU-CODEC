// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Web-player URL builders (port of casu/webproviders.py, WP-NET-004).
// Pure C++, no Qt.
#pragma once
#include <string>
#include <vector>

namespace casu::network {

struct WebPlayerSpec {
    std::string provider;
    std::string label;
    std::string home;
    std::string search_template;  // "{q}" is percent-encoded when substituted
    std::string icon;
};

const std::vector<WebPlayerSpec>& web_player_specs();
const WebPlayerSpec* web_player_spec(const std::string& provider);

std::string web_player_url(const std::string& provider, const std::string& query = "",
                           const std::string& url = "");
std::string provider_for_url(const std::string& url);
std::string spotify_embed_url(const std::string& url);
bool is_external_provider(const std::string& provider);

}  // namespace casu::network