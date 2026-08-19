// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// ffmpeg wrapper (WP-CODEC-002). Runs ffmpeg with argument arrays via the
// shared Subprocess runner; never builds shell command strings.
#pragma once
#include "casu/codec/subprocess.hpp"

#include <string>
#include <vector>

namespace casu::codec {

class MediaTranscodeError : public std::runtime_error {
public:
    explicit MediaTranscodeError(const std::string& msg) : std::runtime_error(msg) {}
};

struct FfmpegRunOptions {
    int timeout_seconds = 120;
    std::size_t max_stdout = 64 * 1024 * 1024;
    std::size_t max_stderr = 8 * 1024 * 1024;
};

class Ffmpeg {
public:
    // `program` defaults to the bundled ffmpeg (empty -> resolved lazily).
    explicit Ffmpeg(std::string program = {});

    // Run program+args; throws MediaTranscodeError when the tool is missing
    // or the process could not be started. Returned result carries the exit
    // code and captured output.
    ProcessResult run(const std::vector<std::string>& args,
                      const FfmpegRunOptions& options = {}) const;

    // Like run, but throws MediaTranscodeError for non-zero exits and
    // timeouts, with the last stderr line in the message.
    ProcessResult run_checked(const std::vector<std::string>& args,
                              const FfmpegRunOptions& options = {}) const;

    const std::string& program() const { return program_; }

private:
    std::string program_;
};

}  // namespace casu::codec
