// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Source-media to standalone CASUNAT2 conversion — full port of
// casu/native_v2/converter.py. Produces byte-identical manifests/chunks to
// the reference for identical sources (strict decoder, tile memo, WebVTT
// text fallback, ASS attachment, bitmap sub2video pipeline, chapters in ns,
// cover-art normalization, bounded tags).
#pragma once
#include "casu/codec/strict_frames.hpp"
#include <functional>

namespace casu::natconv {

class NativeConversionError : public CasuError {
public:
    explicit NativeConversionError(const std::string& m) : CasuError(m) {}
};

struct NativeConvertOptions {
    int64_t tile_width = 64;
    int64_t tile_height = 64;
    double max_key_interval_seconds = 3.0;
    uint64_t recovery_interval = 32;
};

using ProgressFn = std::function<void(double)>;

// Convert `source` into a standalone CASUNAT2 file at `target`. Returns the
// target path. Throws NativeConversionError on any failure (mirrors the
// reference error messages).
std::string convert_media_to_native_v2(
    const std::string& source, const std::string& target,
    const NativeConvertOptions& options = NativeConvertOptions(),
    const ProgressFn& progress = {});

}  // namespace casu::natconv
