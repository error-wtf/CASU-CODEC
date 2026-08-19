// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CASU manifest parse/validate + limits (WP-CORE-002). Mirrors
// casu/schema.py validate_manifest + the bounded parser limits.
#pragma once
#include "casu/json.hpp"
#include <cstdint>
#include <string>
#include <vector>

namespace casu {

// Defensive parser bounds (mirror of casu/schema.py).
struct ManifestLimits {
    uint64_t max_segments_per_stream = 1'000'000;
    uint32_t max_streams = 256;
    uint32_t max_metadata_keys = 256;
    uint32_t max_text_length = 4096;
    int64_t max_segment_priority = 1'000'000;
    uint64_t max_seek_entries = 2'000'000;
};

// Validates a parsed manifest object. Returns all structural problems
// (mirrors casu/schema.py validate_manifest which returns a list of errors).
// An empty result means the manifest is structurally valid. Never throws
// for malformed content; malformed content is reported as errors.
std::vector<std::string> validate_manifest(const JsonValue& manifest,
                                           const ManifestLimits& limits = ManifestLimits());

// Convenience: parse + validate in one step. Throws JsonError on unparseable
// JSON; returns the structural problems otherwise.
std::vector<std::string> parse_and_validate_manifest(const std::string& json_text);

}  // namespace casu
