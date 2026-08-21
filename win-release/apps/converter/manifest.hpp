// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CASU-Converter — probe-based CASU manifest builder (reduced reference
// `analyze`, mirror of casu-cli build_manifest).
#pragma once

#include "casu/json.hpp"

#include <string>

namespace casu::conv {

// Builds a structurally-valid CASU manifest from an ffprobe of the source.
// Temporal segmentation is reduced to one whole-duration segment per playable
// stream. Throws casu::CasuError on probe/validation failure.
casu::JsonValue build_casu_manifest(const std::string& source, const std::string& mode,
                                    double fps = 10.0, int tile_size = 64,
                                    double key_interval_seconds = 3.0);

}  // namespace casu::conv