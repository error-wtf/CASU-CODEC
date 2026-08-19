// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// HTTP Range/206 primitives shared by the YouTube loopback transport and the
// web-backend media server (WP-NET-005 / WP-WEBAPI-004). Pure C++, no Qt.
// Mirrors web_casu.py _serve_transcoded_file range handling plus the
// "bytes=-K" suffix form required by the transport contract.
#pragma once
#include <cstdint>
#include <string>

namespace casu::network {
namespace range {

struct ParsedRange {
    bool ok = false;            // syntactically valid single bytes= range
    bool unsatisfiable = false; // valid syntax but no overlap with the size
    int64_t start = 0;
    int64_t end = -1;           // inclusive; -1 resolves to size-1
};

ParsedRange parse_bytes_range(const std::string& header, int64_t size);

struct ContentRange {
    bool ok = false;
    int64_t start = 0;
    int64_t end = -1;
    int64_t total = -1;         // -1 = unknown
};

ContentRange parse_content_range(const std::string& header);

int64_t parse_content_length(const std::string& header);
bool accepts_ranges(const std::string& header);
bool is_partial_content(int status);

std::string content_range_header(int64_t start, int64_t end, int64_t total);
std::string unsatisfied_range_header(int64_t total);

}  // namespace range
}  // namespace casu::network