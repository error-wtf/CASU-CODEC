// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// yt-dlp wrapper (resolve/search/title) and media-location resolution (ports
// of casu/locations.py + casu/search.py). Runs yt-dlp through QProcess with
// argument arrays (never shell strings) and a hard timeout (WP-NET-002).
#pragma once
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace casu::network {

struct SearchResult {
    std::string title;
    std::string url;
    double duration = -1.0;
    bool has_duration = false;
    std::string uploader;
    std::string source;
    std::string thumbnail;
};

class YtDlp {
public:
    YtDlp();
    explicit YtDlp(std::string path);
    void set_path(std::string path);
    const std::string& path() const;

    std::string resolve(const std::string& target, int timeout_ms = 30000,
                        const std::string& format = "");
    std::vector<SearchResult> search(const std::string& query, int limit = 12,
                                     int timeout_ms = 30000);
    std::vector<SearchResult> search_music(const std::string& query, int limit = 12,
                                           int timeout_ms = 30000);
    std::vector<SearchResult> expand_playlist(const std::string& url, int limit = 100,
                                              int timeout_ms = 60000);
    std::pair<std::string, std::string> title(const std::string& url,
                                              int timeout_ms = 25000);

    static std::string find_binary();

private:
    std::string path_;
};

// Port of casu/locations.py resolve_media_location: Spotify -> spotDL match,
// YouTube -> yt-dlp direct URL, everything else returned unchanged.
std::string resolve_media_location(const std::string& value, int timeout_ms = 30000);

}  // namespace casu::network