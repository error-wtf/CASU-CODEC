// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CASU-Converter conversion-engine Wine test (non-GUI). Exercises the shared
// engine (ffmpeg arg building via casu::codec, media->media transcode,
// Media->CASU native/sidecar, CASU->media export) on a small real fixture.
// Usage: casu_converter_engine_test <fixtures-dir> [work-dir]
#include "engine.hpp"
#include "manifest.hpp"

#include "casu/formats.hpp"
#include "casu/json.hpp"
#include "casu/manifest.hpp"
#include "casu/native.hpp"

#include <chrono>
#include <cstdio>
#include <filesystem>
#include <set>
#include <string>
#include <vector>

namespace fs = std::filesystem;
using casu::conv::CasuContainer;
using casu::conv::ConversionEngine;
using casu::conv::ConversionJob;
using casu::conv::ConversionProfile;
using casu::conv::Direction;

namespace {

int failures = 0;

void check(bool ok, const char* label) {
    if (!ok) { ++failures; std::printf("FAIL %s\n", label); }
    else std::printf("ok   %s\n", label);
}

std::string wine_path(const std::string& path) {
    if (!path.empty() && path[0] == '/') return "Z:" + path;
    return path;
}

bool contains(const std::vector<std::string>& args, const std::string& value) {
    for (const std::string& arg : args)
        if (arg == value) return true;
    return false;
}

std::string arg_after(const std::vector<std::string>& args, const std::string& flag) {
    for (std::size_t i = 0; i + 1 < args.size(); ++i)
        if (args[i] == flag) return args[i + 1];
    return {};
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::printf("usage: casu_converter_engine_test <fixtures-dir> [work-dir]\n");
        return 1;
    }
    const std::string fixtures = wine_path(argv[1]);
    const std::string work =
        (argc >= 3 ? wine_path(argv[2]) : std::string("Z:\\tmp")) + "\\casu_conv_test_" +
        std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());
    std::error_code ec;
    fs::create_directories(work, ec);

    const std::string mp4 = fixtures + "\\demo_clip.mp4";
    const std::string nat1 = fixtures + "\\demo_clip.mp4.casu";

    // 1. Supported output extensions
    {
        const std::vector<std::string>& exts = ConversionEngine::output_extensions();
        bool has_mp4 = false, has_mp3 = false;
        for (const std::string& ext : exts) {
            if (ext == ".mp4") has_mp4 = true;
            if (ext == ".mp3") has_mp3 = true;
        }
        check(has_mp4 && has_mp3, "output extensions include mp4 and mp3");
    }

    // 2. Deterministic output planning
    {
        ConversionProfile profile;
        profile.direction = Direction::MediaToMedia;
        profile.output_extension = ".mp3";
        const std::string out = ConversionEngine::plan_output(mp4, work, profile);
        const std::string expect = work + "\\demo_clip.mp3";
        check(out == expect, "plan_output maps source stem + extension");
    }

    // 3. ffmpeg argument structure via casu::codec (balanced / remux)
    {
        ConversionJob job;
        job.source = mp4;
        job.output = work + "\\demo_bal.mp4";
        job.profile.direction = Direction::MediaToMedia;
        job.profile.media_preset = "balanced";
        job.profile.output_extension = ".mp4";
        std::vector<std::string> args;
        try {
            args = ConversionEngine::build_ffmpeg_args(job);
        } catch (const std::exception& exc) {
            check(false, (std::string("balanced arg build: ") + exc.what()).c_str());
            args.clear();
        }
        if (!args.empty()) {
            check(args.front() == "-nostdin" || args.front() == "-y",
                  "balanced args start with ffmpeg switches");
            check(contains(args, "-i") && arg_after(args, "-i") == mp4,
                  "balanced args map the source via -i");
            check(arg_after(args, "-c:v") == "libx264", "balanced args pick libx264 for video");
            check(arg_after(args, "-c:a") == "aac", "balanced args pick aac for audio");
            check(!args.empty() && args.back() == job.output, "balanced args end with destination");
            bool has_progress = false;
            for (const std::string& a : args) if (a == "-progress") has_progress = true;
            check(has_progress, "balanced args request -progress pipe:1");
        }
    }
    {
        ConversionJob job;
        job.source = mp4;
        job.output = work + "\\demo_remux.mp4";
        job.profile.direction = Direction::MediaToMedia;
        job.profile.media_preset = "remux";
        job.profile.output_extension = ".mp4";
        std::vector<std::string> args;
        try {
            args = ConversionEngine::build_ffmpeg_args(job);
        } catch (const std::exception& exc) {
            check(false, (std::string("remux arg build: ") + exc.what()).c_str());
            args.clear();
        }
        if (!args.empty()) {
            check(arg_after(args, "-c:v") == "copy", "remux args copy video streams");
            check(arg_after(args, "-c:a") == "copy", "remux args copy audio streams");
        }
    }

    // 4. Full media->media conversion (mp4 -> mp3) with the headless engine
    {
        ConversionProfile profile;
        profile.direction = Direction::MediaToMedia;
        profile.media_preset = "balanced";
        profile.output_extension = ".mp3";
        const std::string out = work + "\\demo_clip.mp3";
        std::vector<ConversionJob> jobs{ConversionJob{mp4, out, profile}};
        std::vector<casu::conv::ConversionResult> results;
        try {
            results = ConversionEngine().run(jobs, casu::conv::sync_ffmpeg_executor(), {}, {});
        } catch (const std::exception& exc) {
            check(false, (std::string("media->media run: ") + exc.what()).c_str());
            results.clear();
        }
        if (!results.empty()) {
            check(results[0].status == "converted", "media->media result status converted");
            check(results[0].verification == "FFPROBE_VERIFIED", "media->media verification set");
            std::error_code size_ec;
            const bool exists = fs::is_regular_file(out, size_ec);
            const std::uintmax_t size = exists ? fs::file_size(out, size_ec) : 0;
            check(exists && size > 0, "media->media produced a non-empty output");
            check(!results[0].output_sha256.empty(), "media->media output sha256 recorded");
        }
    }

    // 5. Media->CASU native (CASUNAT1) + payload verification
    {
        ConversionProfile profile;
        profile.direction = Direction::ToCasu;
        profile.casu_container = CasuContainer::Native;
        const std::string out = work + "\\demo_clip_native.casu";
        std::vector<ConversionJob> jobs{ConversionJob{mp4, out, profile}};
        std::vector<casu::conv::ConversionResult> results;
        try {
            results = ConversionEngine().run(jobs, casu::conv::sync_ffmpeg_executor(), {}, {});
        } catch (const std::exception& exc) {
            check(false, (std::string("to-casu native run: ") + exc.what()).c_str());
            results.clear();
        }
        if (!results.empty()) {
            check(results[0].status == "converted", "to-casu native result status converted");
            check(casu::detect_casu_kind(out) == casu::CasuKind::Casunat1,
                  "to-casu native output kind CASUNAT1");
            bool verified = false;
            try {
                casu::casunat1::read_native(out, true);
                verified = true;
            } catch (const std::exception& exc) {
                std::printf("note: native verify failed: %s\n", exc.what());
            }
            check(verified, "to-casu native payload verifies");
        }
    }

    // 6. Media->CASU sidecar manifest validates
    {
        ConversionProfile profile;
        profile.direction = Direction::ToCasu;
        profile.casu_container = CasuContainer::Sidecar;
        const std::string out = work + "\\demo_clip_sidecar.casu";
        std::vector<ConversionJob> jobs{ConversionJob{mp4, out, profile}};
        std::vector<casu::conv::ConversionResult> results;
        try {
            results = ConversionEngine().run(jobs, casu::conv::sync_ffmpeg_executor(), {}, {});
        } catch (const std::exception& exc) {
            check(false, (std::string("to-casu sidecar run: ") + exc.what()).c_str());
            results.clear();
        }
        if (!results.empty()) {
            check(results[0].status == "converted", "to-casu sidecar result status converted");
            check(casu::detect_casu_kind(out) == casu::CasuKind::Sidecar,
                  "to-casu sidecar output kind Sidecar");
            bool valid = false;
            try {
                std::string text;
                FILE* f = std::fopen(out.c_str(), "rb");
                if (f) {
                    std::fseek(f, 0, SEEK_END);
                    long n = std::ftell(f);
                    std::fseek(f, 0, SEEK_SET);
                    if (n > 0) {
                        text.resize((std::size_t)n);
                        if (std::fread(&text[0], 1, (std::size_t)n, f) == (std::size_t)n)
                            valid = casu::validate_manifest(casu::parse_json(text)).empty();
                    }
                    std::fclose(f);
                }
            } catch (const std::exception& exc) {
                std::printf("note: sidecar parse failed: %s\n", exc.what());
            }
            check(valid, "to-casu sidecar manifest validates");
        }
    }

    // 7. CASU->media export (CASUNAT1 -> mp4)
    {
        ConversionProfile profile;
        profile.direction = Direction::FromCasu;
        profile.output_extension = ".mp4";
        const std::string out = work + "\\demo_export.mp4";
        std::vector<ConversionJob> jobs{ConversionJob{nat1, out, profile}};
        std::vector<casu::conv::ConversionResult> results;
        try {
            results = ConversionEngine().run(jobs, casu::conv::sync_ffmpeg_executor(), {}, {});
        } catch (const std::exception& exc) {
            check(false, (std::string("from-casu export run: ") + exc.what()).c_str());
            results.clear();
        }
        if (!results.empty()) {
            check(results[0].status == "exported", "from-casu export result status exported");
            std::error_code size_ec;
            const bool exists = fs::is_regular_file(out, size_ec);
            check(exists && fs::file_size(out, size_ec) > 0, "from-casu export produced media");
        }
    }

    std::printf(failures == 0 ? "ALL PASS\n" : "%d FAILURES\n", failures);
    return failures == 0 ? 0 : 1;
}