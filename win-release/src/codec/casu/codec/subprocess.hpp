// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Bounded subprocess runner (WP-CODEC-002). Runs external tools with argument
// arrays, never shell strings (REQ-WIN-001). Uses Qt6 QProcess when
// CASU_HAS_QT is defined, otherwise a _popen fallback with Windows argv
// quoting.
#pragma once
#include <chrono>
#include <cstddef>
#include <string>
#include <vector>

namespace casu::codec {

struct ProcessResult {
    bool started = false;
    bool timed_out = false;
    int exit_code = -1;
    std::string stdout_data;
    std::string stderr_data;
};

class Subprocess {
public:
    explicit Subprocess(std::string program,
                        std::chrono::milliseconds timeout = std::chrono::seconds(60));
    // Runs program with args; stdout/stderr are captured with byte budgets.
    // Throws nothing; failure is reported through the result fields.
    ProcessResult run(const std::vector<std::string>& args,
                      std::size_t max_stdout = 64 * 1024 * 1024,
                      std::size_t max_stderr = 8 * 1024 * 1024) const;

    const std::string& program() const { return program_; }

private:
    std::string program_;
    std::chrono::milliseconds timeout_;
};

}  // namespace casu::codec
