// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Typed ffprobe result (WP-MEDIA-001). Port of casu/probe.py + the stream
// selection helpers of casu/core.py (ffprobe/stream/duration).
#pragma once
#include "casu/json.hpp"

#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace casu::media {

class MediaProbeError : public std::runtime_error {
public:
    explicit MediaProbeError(const std::string& msg) : std::runtime_error(msg) {}
};

struct MediaStreamInfo {
    int index = -1;
    std::string codec_type;
    std::string codec_name;
    long long width = 0;
    long long height = 0;
    long long sample_rate = 0;
    long long channels = 0;
    std::string time_base;
    std::string pix_fmt;
    double duration = 0.0;
    bool attached_pic = false;
    std::map<std::string, std::string> tags;
};

struct MediaFormatInfo {
    std::string format_name;
    std::string format_long_name;
    double duration = 0.0;
    long long size_bytes = 0;
    long long bit_rate = 0;
    std::map<std::string, std::string> tags;
};

struct MediaInfo {
    std::string path;
    std::vector<MediaStreamInfo> streams;
    MediaFormatInfo format;
    JsonValue raw;  // full ffprobe JSON, kept for callers that need it
};

// Probe a media file via ffprobe into a typed MediaInfo. Throws
// MediaProbeError on tool/failure conditions.
MediaInfo probe(const std::string& path);

// Stream helpers (fail-closed; no throw).
bool has_stream(const MediaInfo& info, const std::string& codec_type);
// First playable stream of a kind (video skips attached_pic), or nullptr.
const MediaStreamInfo* first_playable(const MediaInfo& info,
                                      const std::string& codec_type);
double duration_s(const MediaInfo& info);

}  // namespace casu::media
