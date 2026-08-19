// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Content-based CASU classification (WP-MEDIA-005). Reuses the core
// casu::detect_casu_kind; the wrapper keeps the media API self-contained.
#pragma once
#include "casu/formats.hpp"

#include <string>

namespace casu::media {

// Content-based representation kind of a file (never its suffix).
CasuKind detect_kind(const std::string& path);

std::string kind_name(CasuKind kind);

}  // namespace casu::media
