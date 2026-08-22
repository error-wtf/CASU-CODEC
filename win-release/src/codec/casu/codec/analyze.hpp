// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Real temporal segmentation core — port of casu/core.py preview path,
// casu/core.py analyze_audio, casu/core.py rle/_interval and casu/tiles.py
// compare_tile_frames/tile_digest/tile_regions.
//
// Fidelity contract (mirrors the reference docstrings): these functions are
// activity hints on a decoded gray8 analysis plane. They NEVER claim
// source-resolution pixel identity — records carry
// strict_pixel_identical_available=false / state_is_hint_only=true.
#pragma once
#include "casu/json.hpp"

#include <functional>
#include <string>
#include <vector>

namespace casu::analyze {

// casu/core.py duration(): ONLY format.duration (stream durations ignored).
double manifest_duration(const JsonValue& probe);

// casu/core.py rle()+_interval(): run-length segments with 6-decimal
// banker's-rounded boundaries, segment_id "<prefix>-<ordinal:06d>",
// CREATE only for ordinal 0, final interval clamped to end_s (dropped when
// empty).
JsonValue rle(const std::vector<std::string>& states, double step,
              bool clamp_end, double end_s, const std::string& id_prefix);

// casu/tiles.py compare_tile_frames() over canonical uint8 gray8 planes
// (row-major, width*height). previous may be empty for the first frame.
// Thresholds: strict=0.0, visually_lossless=0.01, adaptive=0.05.
// Tile digest = sha256(str(shape) ascii || raw tile bytes) — byte-identical
// to the reference (Python tuple repr "(h, w)").
std::vector<JsonValue> compare_tile_frames(const std::vector<uint8_t>& previous,
                                           const std::vector<uint8_t>& current,
                                           int width, int height,
                                           int tile_width, int tile_height,
                                           const std::string& mode,
                                           double timestamp_s);

// casu/core.py preview_activity_analysis(): decoded grayscale temporal
// activity hint. Streams `ffmpeg -map 0:v:N -an -vf
// fps=<fps>,scale=160:90:flags=area,format=gray -f rawvideo -pix_fmt gray`.
JsonValue preview_activity_analysis(const std::string& path,
                                    const JsonValue& probe,
                                    double analysis_fps,
                                    const std::string& mode);

// casu/core.py analyze_audio(): decoded PCM RMS activity hint. Streams
// `ffmpeg -map 0:a:0 -vn -ac 1 -ar 16000 -f f32le`; 20 ms RMS-dBFS windows,
// thresholds silence<-55 dB / low_level<-38 dB / active.
JsonValue analyze_audio(const std::string& path, const JsonValue& probe,
                        int sample_rate = 16000, int window_ms = 20);

// casu/core.py analyze_strict_video(): production source-resolution,
// plane-aware STRICT state map (iter_state_map three-frame window over
// strict::FrameSource). Records carry state_is_hint_only=false /
// strict_pixel_identical_available=true. Throws on decoder failure.
JsonValue strict_activity_analysis(const std::string& path,
                                   const JsonValue& probe,
                                   int64_t tile_width = 64,
                                   int64_t tile_height = 64,
                                   const std::function<void(double)>& progress = {});

}  // namespace casu::analyze
