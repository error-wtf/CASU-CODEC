// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/media/kind.hpp"

#include <stdexcept>

namespace casu::media {

CasuKind detect_kind(const std::string& path) {
    try {
        return casu::detect_casu_kind(path);
    } catch (const casu::CasuError&) {
        return CasuKind::None;
    }
}

std::string kind_name(CasuKind kind) {
    switch (kind) {
        case CasuKind::Casunat1: return "casunat1";
        case CasuKind::Casunat2: return "casunat2";
        case CasuKind::Mp5: return "mp5";
        case CasuKind::Sidecar: return "casu-sidecar";
        case CasuKind::None: return "";
    }
    return "";
}

}  // namespace casu::media
