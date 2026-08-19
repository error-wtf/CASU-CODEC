// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// casu-cli Wine tests (Phase C1). Runs the cross-built casu.exe against the
// shared fixtures and checks exit codes plus key stdout output for the core
// subcommands. Usage: casu_cli_test <casu.exe> <fixtures-dir> [work-dir].
#include "casu/codec/subprocess.hpp"

#include <chrono>
#include <cstdio>
#include <filesystem>
#include <string>
#include <vector>

namespace {

int failures = 0;

void check(bool ok, const char* label) {
    if (!ok) { ++failures; std::printf("FAIL %s\n", label); }
    else std::printf("ok   %s\n", label);
}

// Converts a POSIX absolute path into a Wine Z:-path for the spawned CLI.
std::string wine_path(const std::string& path) {
    if (!path.empty() && path[0] == '/') return "Z:" + path;
    return path;
}

// Runs casu.exe with `args`; returns exit code and captures stdout.
int run_casu(const std::string& casu_exe, const std::vector<std::string>& args,
             std::string& stdout_data) {
    casu::codec::Subprocess proc(casu_exe, std::chrono::seconds(180));
    const casu::codec::ProcessResult result = proc.run(args);
    stdout_data = result.stdout_data;
    return result.started ? result.exit_code : -999;
}

void expect_ok_and_contains(const std::string& casu_exe, const std::string& label,
                            const std::vector<std::string>& args,
                            const char* needle) {
    std::string out;
    const int rc = run_casu(casu_exe, args, out);
    check(rc == 0, (label + ": exit 0").c_str());
    if (needle && *needle) check(out.find(needle) != std::string::npos,
                                 (label + ": stdout contains " + needle).c_str());
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 3) {
        std::printf("usage: casu_cli_test <casu.exe> <fixtures-dir> [work-dir]\n");
        return 1;
    }
    const std::string casu_exe = argv[1];
    const std::string fixtures = argv[2];
    const std::string work = argc >= 4 ? argv[3] : std::string("/tmp");

    const std::string mp4 = wine_path(fixtures + "/demo_clip.mp4");
    const std::string mp5 = wine_path(fixtures + "/demo.mp5");
    const std::string nat2 = wine_path(fixtures + "/demo_casunat2.casu");
    const std::string nat1 = wine_path(fixtures + "/demo_clip.mp4.casu");
    const std::string out_nat1 = wine_path(work + "/casu_cli_test_pack.casu");
    const std::string out_mp5 = wine_path(work + "/casu_cli_test_pack.mp5");
    const std::string out_export = wine_path(work + "/casu_cli_test_export.mp4");

    // kind detection
    {
        std::string out;
        int rc = run_casu(casu_exe, {"kind", mp4}, out);
        check(rc == 0 && out.find("none") != std::string::npos, "kind demo_clip.mp4 = none");
        rc = run_casu(casu_exe, {"kind", nat2}, out);
        check(rc == 0 && out.find("casunat2") != std::string::npos, "kind demo_casunat2 = casunat2");
        rc = run_casu(casu_exe, {"kind", nat1}, out);
        check(rc == 0 && out.find("casunat1") != std::string::npos, "kind demo_clip.mp4.casu = casunat1");
        rc = run_casu(casu_exe, {"kind", mp5}, out);
        check(rc == 0 && out.find("mp5") != std::string::npos, "kind demo.mp5 = mp5");
    }

    // sha256 (win extension)
    {
        std::string out;
        int rc = run_casu(casu_exe, {"sha256", nat1}, out);
        check(rc == 0 && out.size() >= 64, "sha256 of native container");
    }

    // validate / verify on native representations
    expect_ok_and_contains(casu_exe, "validate CASUNAT1",
                           {"validate", nat1}, "native CASU container and payload integrity verified");
    expect_ok_and_contains(casu_exe, "verify CASUNAT1",
                           {"verify", nat1}, "native CASU container and payload integrity verified");
    expect_ok_and_contains(casu_exe, "validate CASUNAT2",
                           {"validate", nat2}, "CASUNAT2 structure, seek index, and integrity verified");
    expect_ok_and_contains(casu_exe, "verify CASUNAT2",
                           {"verify", nat2}, "CASUNAT2 structure, seek index, and integrity verified");

    // info (JSON)
    {
        std::string out;
        int rc = run_casu(casu_exe, {"info", nat1}, out);
        check(rc == 0 && out.find("\"valid\": true") != std::string::npos, "info CASUNAT1 valid JSON");
        rc = run_casu(casu_exe, {"info", nat2}, out);
        check(rc == 0 && out.find("\"native_version\": 2") != std::string::npos, "info CASUNAT2 valid JSON");
    }

    // native-info
    {
        std::string out;
        int rc = run_casu(casu_exe, {"native-info", nat1}, out);
        check(rc == 0 && out.find("\"native_version\": 1") != std::string::npos, "native-info CASUNAT1");
        rc = run_casu(casu_exe, {"native-info", nat2}, out);
        check(rc == 0 && out.find("\"native_version\": 2") != std::string::npos, "native-info CASUNAT2");
    }

    // mp5-info on the reference MP5 fixture
    {
        std::string out;
        int rc = run_casu(casu_exe, {"mp5-info", mp5}, out);
        check(rc == 0 && out.find("\"issues\": []") != std::string::npos, "mp5-info reference fixture valid");
        check(rc == 0 && out.find("\"payload_bytes\": 139073") != std::string::npos, "mp5-info payload_bytes");
    }

    // pack (CASUNAT1) + verify the produced container
    expect_ok_and_contains(casu_exe, "pack demo_clip.mp4",
                           {"pack", mp4, "-o", out_nat1}, "\"native_version\": 1");
    expect_ok_and_contains(casu_exe, "verify packed CASUNAT1",
                           {"verify", out_nat1}, "native CASU container and payload integrity verified");

    // pack-mp5 + mp5-info on the produced container
    expect_ok_and_contains(casu_exe, "pack-mp5 demo_clip.mp4",
                           {"pack-mp5", mp4, "-o", out_mp5}, "\"mp5_version\": 1");
    {
        std::string out;
        int rc = run_casu(casu_exe, {"mp5-info", out_mp5}, out);
        check(rc == 0 && out.find("\"issues\": []") != std::string::npos, "mp5-info packed container valid");
    }

    // export a native container back to MP4 (ffmpeg-backed)
    expect_ok_and_contains(casu_exe, "export CASUNAT1 to mp4",
                           {"export", nat1, "-o", out_export}, "\"status\": \"exported\"");

    // benchmark (probe-based analysis JSON)
    expect_ok_and_contains(casu_exe, "benchmark demo_clip.mp4",
                           {"benchmark", mp4}, "\"report\": \"casu-benchmark-1\"");

    // clear-error paths: pack-v2 (CASUNAT2 writer not ported yet)
    {
        std::string out;
        int rc = run_casu(casu_exe, {"pack-v2", mp4, "-o", out_nat1}, out);
        check(rc == 2, "pack-v2 exits 2 (CASUNAT2 writer folgt)");
    }

    // journal / resume for convert batches (WP-CLI-016)
    {
        const std::string out_resume = wine_path(work + "/casu_cli_test_resume.casu");
        std::error_code cleanup_ec;
        std::filesystem::remove("/tmp/casu_cli_test_resume.casu", cleanup_ec);
        for (const auto& entry : std::filesystem::directory_iterator("/tmp")) {
            const std::string name = entry.path().filename().string();
            if (name.rfind(".casu-conversion-", 0) == 0 &&
                name.compare(name.size() - 5, 5, ".json") == 0)
                std::filesystem::remove(entry.path(), cleanup_ec);
        }
        // First run writes the journal and records output_size/output_sha256.
        std::string out;
        int rc = run_casu(casu_exe, {"convert", mp4, "-o", out_resume}, out);
        check(rc == 0 && out.find("\"status\": \"converted\"") != std::string::npos,
              "convert first run converted");
        check(rc == 0 && out.find("\"resumed\": false") != std::string::npos,
              "convert first run not resumed");
        check(rc == 0 && out.find("\"output_sha256\":") != std::string::npos &&
                  out.find("\"output_sha256\": null") == std::string::npos,
              "convert first run records output_sha256");
        // A matching --resume reuses the hash-verified output.
        rc = run_casu(casu_exe, {"convert", mp4, "-o", out_resume, "--resume"}, out);
        check(rc == 0 && out.find("\"resumed\": true") != std::string::npos,
              "convert --resume reuses completed output");
        // A tampered output fails the hash check and is re-converted (with
        // --force, since the output still exists — mirroring the reference).
        {
            FILE* t = std::fopen("/tmp/casu_cli_test_resume.casu", "wb");
            std::fwrite("tampered", 1, 8, t);
            std::fclose(t);
        }
        rc = run_casu(casu_exe, {"convert", mp4, "-o", out_resume, "--resume", "--force"}, out);
        check(rc == 0 && out.find("\"status\": \"converted\"") != std::string::npos,
              "convert --resume re-converts tampered output");
        check(rc == 0 && out.find("\"resumed\": false") != std::string::npos,
              "convert --resume does not reuse tampered output");
        // A journal file for the batch must exist in the work dir.
        bool journal_found = false;
        for (const auto& entry : std::filesystem::directory_iterator("/tmp")) {
            const std::string name = entry.path().filename().string();
            if (name.rfind(".casu-conversion-", 0) == 0 && name.size() > 8 &&
                name.compare(name.size() - 5, 5, ".json") == 0)
                journal_found = true;
        }
        check(journal_found, "conversion journal file written to output dir");
    }

    std::printf(failures == 0 ? "ALL PASS\n" : "%d FAILURES\n", failures);
    return failures == 0 ? 0 : 1;
}
