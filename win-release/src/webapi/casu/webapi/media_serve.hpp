// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Range/HEAD media serving plan (WP-WEBAPI-004). Reuses the shared HTTP
// Range/206 primitives from casu_network and mirrors web_casu.py
// _serve_transcoded_file. Pure C++, no Qt.
#pragma once
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace casu::webapi {

struct MediaPlan {
    int status = 200;
    int64_t start = 0;
    int64_t length = 0;
    int64_t file_size = 0;
    bool partial = false;
    std::vector<std::pair<std::string, std::string>> headers;
};

MediaPlan plan_media_response(const std::string& range_header, int64_t file_size,
                              const std::string& content_type);

}  // namespace casu::webapi