// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/codec/ffmpeg.hpp"

#include "casu/codec/tools.hpp"

#include <sstream>

namespace casu::codec {

namespace {

std::string last_error_line(const ProcessResult& result) {
    std::string detail = result.stderr_data;
    if (detail.empty()) return {};
    while (!detail.empty() && (detail.back() == '\n' || detail.back() == '\r'))
        detail.pop_back();
    const std::size_t nl = detail.rfind('\n');
    return nl == std::string::npos ? detail : detail.substr(nl + 1);
}

}  // namespace

Ffmpeg::Ffmpeg(std::string program) : program_(std::move(program)) {}

ProcessResult Ffmpeg::run(const std::vector<std::string>& args,
                          const FfmpegRunOptions& options) const {
    std::string executable = program_;
    if (executable.empty()) executable = ffmpeg_path();
    if (executable.empty())
        throw MediaTranscodeError("required tool not found: ffmpeg");
    Subprocess proc(std::move(executable),
                    std::chrono::seconds(options.timeout_seconds < 1 ? 1 : options.timeout_seconds));
    return proc.run(args, options.max_stdout, options.max_stderr);
}

ProcessResult Ffmpeg::run_checked(const std::vector<std::string>& args,
                                  const FfmpegRunOptions& options) const {
    ProcessResult result = run(args, options);
    if (!result.started)
        throw MediaTranscodeError(result.stderr_data.empty()
                                      ? "could not start ffmpeg"
                                      : result.stderr_data);
    if (result.timed_out) throw MediaTranscodeError("ffmpeg exceeded configured time limit");
    if (result.exit_code != 0) {
        std::string detail = last_error_line(result);
        if (detail.empty())
            detail = "FFmpeg failed with exit code " + std::to_string(result.exit_code);
        throw MediaTranscodeError(std::move(detail));
    }
    return result;
}

}  // namespace casu::codec
