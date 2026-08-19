// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CASU sidecar resolve (WP-CORE-006). Port of casu/core.py resolve_casu_source:
// locate the original media next to a .casu sidecar and verify size + sha256.
// No path traversal is allowed (basename only, must stay in the manifest dir).
#pragma once
#include "casu/json.hpp"
#include <cstdint>
#include <string>

namespace casu {

// Resolve a CASU sidecar manifest to its original media source, verifying
// size_bytes and sha256 when present. Returns the absolute source path.
// Throws CasuError on any structural/integrity failure.
std::string resolve_casu_source(const std::string& manifest_path);

}  // namespace casu
