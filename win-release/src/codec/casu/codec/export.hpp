// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Verified CASU export (WP-CODEC-005). Port of casu/export.py: verify a CASU
// representation and export it to an FFmpeg media file. CASUNAT1 envelopes,
// MP5 containers and sidecar manifests are supported; CASUNAT2 native export
// requires the native decoder and fails explicitly.
#pragma once
#include <stdexcept>
#include <string>

namespace casu::codec {

class CasuExportError : public std::runtime_error {
public:
    explicit CasuExportError(const std::string& msg) : std::runtime_error(msg) {}
};

// Export source (CASUNAT1 / MP5 / sidecar manifest) to destination. Throws
// CasuExportError on any verification or encoding failure.
void export_casu(const std::string& source, const std::string& destination);

}  // namespace casu::codec
