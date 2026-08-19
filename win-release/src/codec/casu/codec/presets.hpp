// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Media conversion presets + ffmpeg argument builder (WP-CODEC-004). Port of
// casu/transcode.py: MEDIA_PRESETS, quality options and build_transcode_command.
#pragma once
#include "casu/json.hpp"

#include <string>
#include <vector>

namespace casu::codec {

class MediaTranscodeError;

struct TranscodeOptions {
    std::string preset = "balanced";           // remux|balanced|high|small|lossless
    std::string video_codec = "auto";
    std::string audio_codec = "auto";
    std::string subtitle_mode = "auto";        // auto|copy|drop
    bool all_tracks = true;
    bool preserve_metadata = true;
};

struct BuiltTranscodeCommand {
    std::vector<std::string> args;   // ffmpeg arguments (no program name)
    JsonValue probe;                 // verified source probe
};

// Set membership checks (throw MediaTranscodeError from the builder).
bool is_known_preset(const std::string& preset);
bool is_known_subtitle_mode(const std::string& mode);

// Mirrors transcode._quality_options.
std::vector<std::string> quality_options(const std::string& codec,
                                         const std::string& preset, bool audio = false);

// Build one mapped ffmpeg command for source -> destination. Runs ffprobe on
// the source, selects streams/codecs from the preset and options, and returns
// the argument list plus the verified probe. Throws MediaTranscodeError.
BuiltTranscodeCommand build_transcode_command(const std::string& source,
                                              const std::string& destination,
                                              const TranscodeOptions& options = {});

}  // namespace casu::codec
