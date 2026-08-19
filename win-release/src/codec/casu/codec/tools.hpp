// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Bundled helper-tool resolution (ffmpeg/ffprobe). Resolution order:
//   1. CASU_FFMPEG / CASU_FFPROBE environment override
//   2. <cwd>/third_party/tools/<name>.exe (the bundled tree)
//   3. <name> on PATH
#pragma once
#include <string>

namespace casu::codec {

// Returns the resolved tool path or an empty string when not found.
std::string find_tool(const std::string& name);

// Convenience wrappers (empty when unavailable).
std::string ffmpeg_path();
std::string ffprobe_path();

}  // namespace casu::codec
