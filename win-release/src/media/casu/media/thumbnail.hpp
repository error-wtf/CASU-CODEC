// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Bounded, source-versioned media thumbnails (WP-MEDIA-002). Port of
// casu/thumbnail.py: cached 320x180 PPM extraction via ffmpeg. Native
// CASUNAT2 cover-art decoding is not yet available in this phase.
#pragma once
#include <string>

namespace casu::media {

// Return a cached PPM thumbnail path for `source`, or an empty string for
// non-video/failed input. The cache key binds path + size + mtime.
std::string thumbnail_for(const std::string& source, const std::string& cache_directory);

}  // namespace casu::media
