// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CASU-Converter — conversion engine (port of casu/jobs.py ConversionEngine +
// casu/transcode.py). Headless C++20; the GUI worker supplies a streaming
// ffmpeg executor so progress and cancel work on a live subprocess.
#pragma once

#include <functional>
#include <stdexcept>
#include <string>
#include <vector>

namespace casu::conv {

enum class Direction { MediaToMedia, ToCasu, FromCasu };
enum class CasuContainer { Sidecar, Native, Mp5 };

struct ConversionProfile {
    Direction direction = Direction::MediaToMedia;
    CasuContainer casu_container = CasuContainer::Native;
    std::string media_preset = "balanced";   // remux|balanced|high|small|lossless
    std::string video_codec = "auto";
    std::string audio_codec = "auto";
    std::string subtitle_mode = "auto";
    bool all_tracks = true;
    bool preserve_metadata = true;
    std::string output_extension = ".mp4";   // media output extension (leading dot)
    bool force = false;
};

struct ConversionJob {
    std::string source;
    std::string output;
    ConversionProfile profile;
};

struct ConversionResult {
    std::string source;
    std::string output;
    std::string status;            // converted | exported | failed
    std::string container;
    std::string error;
    double conversion_seconds = 0.0;
    long long output_size = -1;
    std::string output_sha256;
    std::string verification;
    bool resumed = false;
};

struct ConversionProgress {
    int job_index = 0;
    int job_count = 0;
    std::string source;
    double fraction = 0.0;         // current job 0..1
    double overall = 0.0;          // batch 0..1
    double elapsed_seconds = 0.0;
    double eta_seconds = -1.0;     // <0 = unknown
    std::string state = "RUNNING";
};

class ConversionCancelled : public std::runtime_error {
public:
    ConversionCancelled() : std::runtime_error("conversion cancelled") {}
};

struct RunOutcome {
    bool ok = false;
    std::string error;             // last ffmpeg error line when !ok
    std::string stdout_data;       // captured progress/stat output
};

// Executor contract: run one ffmpeg command array (no program name in args).
// `duration_seconds` (>0) lets the executor normalize `-progress pipe:1`
// out_time_us values into a 0..1 fraction. The executor must poll `cancelled`
// (may throw ConversionCancelled) and report per-job progress via `progress`.
using FfmpegExecutor = std::function<RunOutcome(
    const std::vector<std::string>& args,
    double duration_seconds,
    const std::function<void(double)>& progress,
    const std::function<bool()>& cancelled)>;

std::string container_name(const ConversionProfile& profile);

class ConversionEngine {
public:
    // Supported media output extensions (mirror of casu/transcode.py).
    static const std::vector<std::string>& output_extensions();

    // Deterministic target mapping (source stem + extension) mirroring the
    // reference plan_format_targets / _target_for.
    static std::string plan_output(const std::string& source,
                                   const std::string& output_dir,
                                   const ConversionProfile& profile);

    // ffmpeg arguments (no program name) for a media->media job, built via
    // casu::codec::build_transcode_command. Throws casu::CasuError.
    static std::vector<std::string> build_ffmpeg_args(const ConversionJob& job);

    // Run a whole batch. Result order matches job order. Throws
    // ConversionCancelled when the caller requests cancellation.
    std::vector<ConversionResult> run(const std::vector<ConversionJob>& jobs,
                                      const FfmpegExecutor& executor,
                                      const std::function<void(const ConversionProgress&)>& progress,
                                      const std::function<bool()>& cancelled);
};

// Blocking executor backed by casu::codec::Ffmpeg::run_checked (no live
// progress, no mid-run cancel). Used by the headless engine test.
FfmpegExecutor sync_ffmpeg_executor();

}  // namespace casu::conv