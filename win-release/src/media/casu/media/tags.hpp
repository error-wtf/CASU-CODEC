// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Lightweight media-tag extraction (WP-MEDIA-004). Port of casu/tags.py:
// ffprobe tags (incl. embedded ID3v2/APIC cover presence) with a sensible
// filename/path-structure fallback.
#pragma once
#include <map>
#include <string>

namespace casu::media {

// Best-effort metadata for `path` (tags first, filename fallback). Returns
// keys like title/artist/album/genre/track/year/comment/duration; empty for
// non-media suffixes or unreadable input.
std::map<std::string, std::string> metadata_for(const std::string& path);

// Extract an embedded cover picture (attached_pic stream) to `output_path`
// (PNG). Returns true on success; false when there is no cover or decoding
// fails.
bool extract_cover(const std::string& path, const std::string& output_path);

}  // namespace casu::media
