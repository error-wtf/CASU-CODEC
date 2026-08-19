// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CASU-Converter Wine smoke test. Starts CASU-Converter.exe (which opens the
// main window and auto-quits in --smoke-test mode) under xvfb via wine and
// checks that it started cleanly: exit 0, the window marker was printed, and
// no missing-DLL / platform-plugin startup error was reported.
// Usage: casu_converter_test <converter-exe>
#include "casu/codec/subprocess.hpp"

#include <chrono>
#include <cstdio>
#include <string>
#include <vector>

namespace {

int failures = 0;

void check(bool ok, const char* label) {
    if (!ok) { ++failures; std::printf("FAIL %s\n", label); }
    else std::printf("ok   %s\n", label);
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::printf("usage: casu_converter_test <converter-exe>\n");
        return 1;
    }
    const std::string exe = argv[1];

    casu::codec::Subprocess proc(exe, std::chrono::seconds(90));
    const casu::codec::ProcessResult result =
        proc.run({"--smoke-test"}, 4 * 1024 * 1024, 4 * 1024 * 1024);

    check(result.started, "CASU-Converter.exe started under wine");
    if (!result.started) {
        std::printf("stderr: %s\n", result.stderr_data.c_str());
        std::printf("%d FAILURES\n", failures);
        return 1;
    }
    check(result.exit_code == 0, "CASU-Converter.exe exited cleanly");
    check(result.stdout_data.find("SMOKE converter window shown") != std::string::npos,
          "main window appeared (SMOKE marker)");

    const std::string combined = result.stdout_data + "\n" + result.stderr_data;
    const bool missing_dll = combined.find("failed to load") != std::string::npos ||
                             combined.find("DLL") != std::string::npos ||
                             combined.find("platform plugin") != std::string::npos ||
                             combined.find("could not find or load the Qt platform") != std::string::npos;
    check(!missing_dll, "no missing DLL / platform-plugin errors");

    if (!result.stdout_data.empty()) std::printf("-- stdout --\n%s\n", result.stdout_data.c_str());
    if (!result.stderr_data.empty()) std::printf("-- stderr --\n%s\n", result.stderr_data.c_str());

    std::printf(failures == 0 ? "ALL PASS\n" : "%d FAILURES\n", failures);
    return failures == 0 ? 0 : 1;
}