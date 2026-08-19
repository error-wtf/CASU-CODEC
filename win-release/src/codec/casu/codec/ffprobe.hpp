// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// ffprobe wrapper (WP-CODEC-003). Runs ffprobe with an argument array and
// parses its JSON output (format/streams/chapters) into the core JsonValue.
#pragma once
#include "casu/json.hpp"

#include <string>

namespace casu::codec {

class MediaProbeError : public std::runtime_error {
public:
    explicit MediaProbeError(const std::string& msg) : std::runtime_error(msg) {}
};

// Probe a media file; returns the parsed ffprobe JSON object. Throws
// MediaProbeError when the tool is missing, the probe fails, or the output
// is not a JSON object.
JsonValue probe_json(const std::string& path, int timeout_seconds = 30);

// Convenience helpers over a probe JSON object (fail-closed, no throw).
bool probe_has_stream(const JsonValue& probe, const std::string& codec_type);
double probe_duration(const JsonValue& probe);
// First playable stream object of a kind (video skips attached_pic), or null.
const JsonValue* first_playable_stream(const JsonValue& probe,
                                       const std::string& codec_type);

}  // namespace casu::codec
