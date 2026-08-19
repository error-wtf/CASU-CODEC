// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Unit tests for casu_codec: preset/quality selection, the ffprobe wrapper,
// the ffmpeg wrapper (arg-array transcode) and CASU export (NAT1/MP5/sidecar;
// NAT2 fails explicitly).
#include "casu/codec.hpp"

#include <cstdio>
#include <filesystem>
#include <string>
#include <vector>

using namespace casu;
using namespace casu::codec;

namespace {
int failures = 0;
void check(bool ok, const char* label) {
    if (!ok) { ++failures; std::printf("FAIL %s\n", label); }
    else std::printf("ok   %s\n", label);
}

bool contains(const std::vector<std::string>& args, const std::string& expected) {
    for (const auto& arg : args) if (arg == expected) return true;
    return false;
}

// Locate the value following a flag, or an empty string.
std::string arg_after(const std::vector<std::string>& args, const std::string& flag) {
    for (std::size_t i = 0; i + 1 < args.size(); ++i)
        if (args[i] == flag) return args[i + 1];
    return {};
}
}  // namespace

int main() {
    const std::string clip = "tests/fixtures/demo_clip.mp4";
    const std::string nat1 = "tests/fixtures/demo_clip.mp4.casu";
    const std::string mp5 = "tests/fixtures/demo.mp5";
    const std::string nat2 = "tests/fixtures/demo_casunat2.casu";

    // --- presets + quality selection (WP-CODEC-004) ---
    for (const char* preset : {"remux", "balanced", "high", "small", "lossless"})
        check(is_known_preset(preset), "preset known");
    check(!is_known_preset("bogus"), "unknown preset rejected");
    check(is_known_subtitle_mode("auto") && is_known_subtitle_mode("copy") &&
          is_known_subtitle_mode("drop"), "subtitle modes known");
    check(!is_known_subtitle_mode("burn"), "unknown subtitle mode rejected");
    check(quality_options("libx264", "high") ==
          std::vector<std::string>({"-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p"}),
          "libx264 high quality options");
    check(quality_options("libx264", "small") ==
          std::vector<std::string>({"-preset", "medium", "-crf", "28", "-pix_fmt", "yuv420p"}),
          "libx264 small quality options");
    check(quality_options("libx264", "lossless") ==
          std::vector<std::string>({"-preset", "medium", "-qp", "0", "-pix_fmt", "yuv420p"}),
          "libx264 lossless options");
    check(quality_options("libvorbis", "balanced", true) ==
          std::vector<std::string>({"-q:a", "6"}), "libvorbis audio quality");
    check(quality_options("aac", "balanced", true) ==
          std::vector<std::string>({"-b:a", "192k"}), "aac audio bitrate");
    check(quality_options("copy", "balanced").empty(), "copy -> no quality options");

    // --- build_transcode_command ---
    bool threw = false;
    try { build_transcode_command(clip, "/tmp/x.mp4", TranscodeOptions{.preset = "bogus"}); }
    catch (const MediaTranscodeError&) { threw = true; }
    check(threw, "unknown preset rejected by builder");
    threw = false;
    try { build_transcode_command(clip, "/tmp/x.xyz"); }
    catch (const MediaTranscodeError&) { threw = true; }
    check(threw, "unsupported output extension rejected");
    {
        BuiltTranscodeCommand built = build_transcode_command(clip, "/tmp/casu_test.mkv");
        check(built.args.size() > 2, "transcode command built");
        check(built.args.front() == "-nostdin", "command starts with -nostdin");
        check(built.args.back() == "/tmp/casu_test.mkv", "destination is last arg");
        check(contains(built.args, "libx264"), "balanced mkv uses libx264");
        check(arg_after(built.args, "-crf") == "20", "balanced crf 20");
        check(arg_after(built.args, "-c:a") == "aac", "balanced aac audio");
        check(probe_has_stream(built.probe, "video") && probe_has_stream(built.probe, "audio"),
              "built command probe has video+audio");
    }

    // --- ffprobe wrapper (WP-CODEC-003) ---
    {
        JsonValue probe = probe_json(clip);
        check(probe.is_object(), "ffprobe returns an object");
        check(probe_has_stream(probe, "video"), "probe has video stream");
        check(probe_has_stream(probe, "audio"), "probe has audio stream");
        const double duration = probe_duration(probe);
        check(duration > 5.0 && duration < 7.0, "probe duration ~6s");
        const JsonValue* video = first_playable_stream(probe, "video");
        check(video != nullptr && video->find("codec_name") &&
              video->find("codec_name")->is_string(), "first video stream readable");
    }
    {
        bool threw = false;
        try { probe_json("/nonexistent/definitely_missing.mp4"); }
        catch (const MediaProbeError&) { threw = true; }
        check(threw, "missing input rejected by ffprobe wrapper");
    }

    // --- ffmpeg wrapper + real transcode (WP-CODEC-002) ---
    {
        BuiltTranscodeCommand built = build_transcode_command(clip, "/tmp/casu_codec_out.mp4");
        Ffmpeg ffmpeg;
        ProcessResult result = ffmpeg.run_checked(built.args);
        check(result.exit_code == 0, "transcode via arg array succeeded");
        check(std::filesystem::is_regular_file("/tmp/casu_codec_out.mp4"), "output file exists");
        JsonValue out_probe = probe_json("/tmp/casu_codec_out.mp4");
        check(probe_has_stream(out_probe, "video") && probe_has_stream(out_probe, "audio"),
              "transcoded output has playable streams");
    }

    // --- export (WP-CODEC-005) ---
    {
        export_casu(nat1, "/tmp/casu_export_out.mp4");
        check(std::filesystem::is_regular_file("/tmp/casu_export_out.mp4"), "NAT1 export exists");
        JsonValue out_probe = probe_json("/tmp/casu_export_out.mp4");
        check(probe_has_stream(out_probe, "video") && probe_has_stream(out_probe, "audio"),
              "NAT1 export has playable streams");
    }
    {
        export_casu(mp5, "/tmp/casu_export_mp5.mp4");
        check(std::filesystem::is_regular_file("/tmp/casu_export_mp5.mp4"), "MP5 export exists");
        JsonValue out_probe = probe_json("/tmp/casu_export_mp5.mp4");
        check(probe_has_stream(out_probe, "video") && probe_has_stream(out_probe, "audio"),
              "MP5 export has playable streams");
    }
    {
        bool threw = false;
        try { export_casu(clip, "/tmp/casu_export_plain.mp4"); }
        catch (const CasuExportError&) { threw = true; }
        check(threw, "plain media rejected as CASU export input");
    }
    {
        bool threw = false;
        try { export_casu(nat1, "/tmp/casu_export_noext"); }
        catch (const CasuExportError&) { threw = true; }
        check(threw, "extension-less destination rejected");
    }
    {
        bool threw = false;
        try { export_casu(nat2, "/tmp/casu_export_nat2.mp4"); }
        catch (const CasuExportError& exc) {
            threw = true;
            check(std::string(exc.what()).find("native decoder") != std::string::npos,
                  "NAT2 export fails with explicit message");
        }
        check(threw, "CASUNAT2 export fails explicitly");
    }

    std::printf(failures == 0 ? "ALL PASS\n" : "%d FAILURES\n", failures);
    return failures == 0 ? 0 : 1;
}
