// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Spotify provider via spotDL + yt-dlp matching (ports of casu/spotify.py,
// WP-NET-003). Metadata is fetched through the public Spotify oEmbed
// endpoint; track matching/playback always uses an open provider, never a
// Spotify DRM stream.
#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace casu::network {

struct SpotifyMetadata {
    std::string kind;
    std::string title;
    std::string url;
};

SpotifyMetadata fetch_spotify_metadata(const std::string& url, int timeout_ms = 15000);
std::string resolve_spotify_url(const std::string& url, int timeout_ms = 60000,
                                const std::string& title = "",
                                const std::string& artist = "");
std::string youtube_handoff_query(const SpotifyMetadata& meta);

struct SpotifySearchResult {
    std::string title;
    std::string artist;
    std::string url;
    double duration = -1.0;
    bool has_duration = false;
};

std::vector<SpotifySearchResult> search_spotify(const std::string& query, int limit = 12,
                                                int timeout_ms = 90000);
std::vector<SpotifySearchResult> expand_spotify(const std::string& url, int limit = 100,
                                                int timeout_ms = 120000);

}  // namespace casu::network