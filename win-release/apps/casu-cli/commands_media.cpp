// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// casu-cli — media subcommands: analyze, convert, benchmark, play, transcode,
// export. Outputs and exit codes mirror casu/cli.py.
#include "cli_util.hpp"
#include "journal.hpp"

#include "casu/codec/export.hpp"
#include "casu/codec/ffmpeg.hpp"
#include "casu/codec/presets.hpp"
#include "casu/formats.hpp"
#include "casu/json.hpp"
#include "casu/manifest.hpp"
#include "casu/native.hpp"
#include "casu/sidecar.hpp"
#include "casu/sha256.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <set>
#include <string>
#include <vector>

namespace casu::cli {

using casu::CasuError;
using casu::JsonObject;
using casu::JsonValue;

namespace {

const std::set<std::string>& media_output_extensions() {
    static const std::set<std::string> value = {
        ".3g2", ".3gp", ".aac", ".aif", ".aiff", ".alac", ".asf", ".avi",
        ".f4v", ".flac", ".flv", ".m2ts", ".m4a", ".m4v", ".mka", ".mkv",
        ".mov", ".mp2", ".mp3", ".mp4", ".mpeg", ".mpg", ".mts", ".oga",
        ".ogg", ".ogv", ".opus", ".ts", ".wav", ".webm", ".wma", ".wmv",
    };
    return value;
}

std::string lowercase(const std::string& value) {
    std::string out = value;
    for (char& c : out)
        if (c >= 'A' && c <= 'Z') c = char(c + ('a' - 'A'));
    return out;
}

double round6(double value) { return std::round(value * 1e6) / 1e6; }

JsonValue json_null() { return JsonValue(std::nullptr_t{}); }

double manifest_duration(const JsonValue& manifest) {
    const JsonValue* source = manifest.find("source");
    const JsonValue* duration = source ? source->find("duration_s") : nullptr;
    return duration && duration->is_number() ? duration->as_double() : 0.0;
}

int segment_count(const JsonValue& manifest, const char* section) {
    const JsonValue* section_v = manifest.find(section);
    const JsonValue* segments = section_v ? section_v->find("segments") : nullptr;
    return segments && segments->is_array() ? (int)segments->as_array().items.size() : 0;
}

bool path_has_suffix(const std::string& path, const std::string& suffix) {
    std::error_code ec;
    const std::filesystem::path p(path);
    return p.extension().string() == suffix;
}

JsonValue conversion_result_entry(const std::string& source, const std::string& output,
                                  const std::string& status, const std::string& container,
                                  const std::string& error, double seconds,
                                  long long output_size, long long source_size,
                                  const std::string& source_sha256,
                                  const std::string& output_sha256,
                                  const std::string& verification,
                                  int attempts = 1) {
    JsonObject entry;
    entry.items["source"] = JsonValue(source);
    entry.items["output"] = JsonValue(output);
    entry.items["status"] = JsonValue(status);
    entry.items["container"] = JsonValue(container);
    entry.items["duration_s"] = json_null();
    entry.items["error"] = error.empty() ? json_null() : JsonValue(error);
    // Linux parity (jobs.py): failed entries carry the failure diagnostics.
    entry.items["attempts"] = JsonValue((int64_t)std::max(1, attempts));
    entry.items["output_size"] = output_size < 0 ? json_null() : JsonValue((int64_t)output_size);
    entry.items["output_sha256"] = output_sha256.empty() ? json_null() : JsonValue(output_sha256);
    entry.items["resumed"] = JsonValue(false);
    entry.items["conversion_seconds"] = JsonValue(seconds);
    entry.items["source_size"] = source_size < 0 ? json_null() : JsonValue((int64_t)source_size);
    entry.items["source_sha256"] = source_sha256.empty() ? json_null() : JsonValue(source_sha256);
    entry.items["profile_sha256"] = json_null();
    entry.items["tool_versions"] = json_null();
    entry.items["frame_count"] = json_null();
    entry.items["key_states"] = json_null();
    entry.items["tile_updates"] = json_null();
    entry.items["hold_count"] = json_null();
    entry.items["audio_blocks"] = json_null();
    entry.items["subtitle_packets"] = json_null();
    entry.items["verification_result"] = verification.empty() ? json_null() : JsonValue(verification);
    auto warnings = std::make_shared<casu::JsonArray>();
    entry.items["warnings"] = JsonValue(std::move(warnings));
    return JsonValue(std::make_shared<casu::JsonObject>(std::move(entry)));
}

long long path_size(const std::string& path) {
    std::error_code ec;
    const std::uintmax_t size = std::filesystem::file_size(path, ec);
    return ec ? -1 : (long long)size;
}

void write_report(const std::string& report_path, const JsonValue& payload) {
    if (report_path.empty()) return;
    atomic_write_text(report_path, pretty_json(payload) + "\n");
}

// Full ConversionProfile dict (mirrors casu/jobs.py asdict of the profile used
// by `convert`). Values must serialize identically to the reference for the
// journal identity hash and job-match validation.
JsonValue convert_profile(const std::string& container, const std::string& mode,
                          double analysis_fps) {
    JsonObject profile;
    profile.items["container"] = JsonValue(container);
    profile.items["mode"] = JsonValue(mode);
    profile.items["analysis_fps"] = JsonValue(analysis_fps);
    profile.items["tile_size"] = JsonValue(int64_t(64));
    profile.items["key_interval_seconds"] = JsonValue(3.0);
    profile.items["media_preset"] = JsonValue(std::string("balanced"));
    profile.items["video_codec"] = JsonValue(std::string("auto"));
    profile.items["audio_codec"] = JsonValue(std::string("auto"));
    profile.items["subtitle_mode"] = JsonValue(std::string("auto"));
    profile.items["all_tracks"] = JsonValue(true);
    profile.items["preserve_metadata"] = JsonValue(true);
    return JsonValue(std::make_shared<JsonObject>(std::move(profile)));
}

JsonValue transcode_profile(const std::string& preset, const std::string& video_codec,
                            const std::string& audio_codec, const std::string& subtitle_mode,
                            bool all_tracks, bool preserve_metadata) {
    JsonObject profile;
    profile.items["container"] = JsonValue(std::string("media"));
    profile.items["mode"] = JsonValue(std::string("strict"));
    profile.items["analysis_fps"] = JsonValue(10.0);
    profile.items["tile_size"] = JsonValue(int64_t(64));
    profile.items["key_interval_seconds"] = JsonValue(3.0);
    profile.items["media_preset"] = JsonValue(preset);
    profile.items["video_codec"] = JsonValue(video_codec);
    profile.items["audio_codec"] = JsonValue(audio_codec);
    profile.items["subtitle_mode"] = JsonValue(subtitle_mode);
    profile.items["all_tracks"] = JsonValue(all_tracks);
    profile.items["preserve_metadata"] = JsonValue(preserve_metadata);
    return JsonValue(std::make_shared<JsonObject>(std::move(profile)));
}

}  // namespace

int cmd_analyze(const Args& args) {
    const std::string input = args.positional.at(0);
    const double analysis_fps = args.get_double("--analysis-fps", 10.0);
    if (analysis_fps <= 0) throw CasuError("analysis FPS must be positive");
    const std::string mode = args.get("--mode", "strict");
    const std::string source = abs_path(input);
    std::error_code ec;
    if (!std::filesystem::exists(source, ec))
        throw CasuError("input not found: " + input);
    if (casu::detect_casu_kind(source) != casu::CasuKind::None)
        throw CasuError("input is already a CASU manifest; convert the original MP4/MP3 media instead");

    std::filesystem::path output =
        args.has("-o") || args.has("--output")
            ? std::filesystem::path(abs_path(args.get("-o", args.get("--output", ""))))
            : std::filesystem::path(source + std::filesystem::path(source).extension().string() + ".casu");
    output = output.lexically_normal();
    if (output.string() == source)
        throw CasuError("output must differ from the source media; refusing to overwrite input");

    const JsonValue manifest = build_manifest(source, mode, analysis_fps);
    atomic_write_text(output.string(), compact_json(manifest));

    JsonObject summary;
    summary.items["manifest"] = JsonValue(output.string());
    summary.items["duration_s"] = JsonValue(manifest_duration(manifest));
    summary.items["video_segments"] = JsonValue((int64_t)segment_count(manifest, "video"));
    summary.items["audio_segments"] = JsonValue((int64_t)segment_count(manifest, "audio"));
    summary.items["mode"] = JsonValue(mode);
    std::printf("%s\n", pretty_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(summary)))).c_str());
    return 0;
}

int cmd_convert(const Args& args) {
    const double analysis_fps = args.get_double("--analysis-fps", 10.0);
    if (analysis_fps <= 0) throw CasuError("analysis FPS must be positive");
    if (args.get_long("--retry", 0) < 0) throw CasuError("retry count must not be negative");
    const std::string mode = args.get("--mode", "strict");
    const std::string container = args.get("--container", "sidecar");
    const bool force = args.flag("--force");
    const long long retries = args.get_long("--retry", 0);

    const auto planned = plan_inputs(args.positional, false);
    if (planned.empty()) throw CasuError("no source files found in the requested inputs");
    std::vector<std::string> sources;
    for (const auto& [source, relative] : planned) sources.push_back(source);

    const bool has_output = args.has("-o") || args.has("--output");
    const std::string output_arg = args.get("-o", args.get("--output", ""));
    std::string output_dir;
    if (has_output) {
        const std::string output = abs_path(output_arg);
        if (sources.size() > 1 && path_has_suffix(output, ".casu"))
            throw CasuError("multiple inputs require an output directory, not one .casu file");
        output_dir = (sources.size() > 1 || !path_has_suffix(output, ".casu"))
                         ? output
                         : std::filesystem::path(output).parent_path().string();
    } else {
        output_dir = std::filesystem::path(sources[0]).parent_path().string();
    }
    std::error_code ec;
    std::filesystem::create_directories(output_dir, ec);

    std::vector<std::string> targets;
    if (sources.size() == 1 && has_output && path_has_suffix(output_arg, ".casu")) {
        targets.push_back(abs_path(output_arg));
    } else if (sources.size() == 1 && !has_output) {
        targets.push_back(sources[0] + std::filesystem::path(sources[0]).extension().string() + ".casu");
    } else {
        targets = plan_casu_targets(planned, output_dir);
    }

    auto files = std::make_shared<casu::JsonArray>();
    const JsonValue profile = convert_profile(container, mode, analysis_fps);
    std::vector<JournalJob> jobs;
    for (std::size_t i = 0; i < sources.size(); ++i)
        jobs.push_back(JournalJob{sources[i], targets[i], profile});
    const std::string journal_path = conversion_journal_path(output_dir, jobs);
    const std::map<std::pair<std::string, std::string>, JsonValue> resumed =
        args.flag("--resume") ? load_resume(journal_path, jobs)
                              : std::map<std::pair<std::string, std::string>, JsonValue>{};

    for (std::size_t i = 0; i < sources.size(); ++i) {
        const std::string& source = sources[i];
        const std::string& target = targets[i];
        auto reuse_it = resumed.find({source, target});
        if (reuse_it != resumed.end()) {
            files->items.push_back(reuse_it->second);
            write_journal(journal_path, "RUNNING", jobs, JsonValue(files));
            continue;
        }
        // Linux parity (jobs.py run): failed jobs are retried up to `retries`
        // times; every attempt is recorded in the result entry.
        int attempts = 0;
        double seconds = 0.0;
        std::string error;
        std::string verification;
        while (true) {
            ++attempts;
            const auto started = std::chrono::steady_clock::now();
            try {
                if (container == "native-v2")
                    throw CasuError("convert --container native-v2: CASUNAT2 writer folgt "
                                    "(casu_core provides a CASUNAT2 reader only; the segmented "
                                    "writer is a later port step)");
                if (path_size(target) >= 0 && !force)
                    throw CasuError("output exists (use force): " + target);
                const JsonValue manifest = build_manifest(source, mode, analysis_fps);
                if (container == "sidecar") {
                    atomic_write_text(target, compact_json(manifest));
                    // jobs.py: sidecar results are MANIFEST_VALIDATED.
                    verification = "MANIFEST_VALIDATED";
                } else if (container == "native") {
                    casu::casunat1::write_native(target, source, manifest);
                    // jobs.py: native containers are re-read and verified
                    // after writing (read_native verify_payload=True).
                    casu::casunat1::read_native(target, true);
                    verification = "CASUNAT1_FULLY_VERIFIED";
                } else {
                    throw CasuError("unknown conversion container: " + container);
                }
            } catch (const std::exception& exc) {
                error = exc.what();
                verification.clear();
                if (attempts <= retries) continue;  // retry
            }
            seconds = std::chrono::duration<double>(
                          std::chrono::steady_clock::now() - started)
                          .count();
            break;
        }
        long long output_size = error.empty() ? path_size(target) : -1;
        std::string source_sha256;
        if (error.empty()) source_sha256 = casu::sha256_file(source);
        files->items.push_back(conversion_result_entry(
            source, target, error.empty() ? "converted" : "failed", container, error,
            round6(seconds), output_size, path_size(source), source_sha256,
            error.empty() && !verification.empty() ? casu::sha256_file(target) : "",
            verification.empty() && !error.empty() ? "FAILED" : verification,
            attempts));
        write_journal(journal_path, "RUNNING", jobs, JsonValue(files));
    }
    write_journal(journal_path, "COMPLETE", jobs, JsonValue(files));

    JsonObject payload;
    payload.items["version"] = JsonValue(int64_t(1));
    payload.items["mode"] = JsonValue(mode);
    payload.items["container"] = JsonValue(container);
    payload.items["analysis_fps"] = JsonValue(analysis_fps);
    payload.items["files"] = JsonValue(std::move(files));
    const JsonValue payload_value = JsonValue(std::make_shared<casu::JsonObject>(std::move(payload)));
    write_report(args.get("--report"), payload_value);
    std::printf("%s\n", pretty_json(payload_value).c_str());
    return error_all_ok(payload_value) ? 0 : 1;
}

int cmd_benchmark(const Args& args) {
    const double analysis_fps = args.get_double("--analysis-fps", 10.0);
    if (analysis_fps <= 0) throw CasuError("analysis FPS must be positive");
    const std::string mode = args.get("--mode", "strict");
    const std::string input = args.positional.at(0);
    const std::string source = abs_path(input);
    std::error_code ec;
    if (!std::filesystem::exists(source, ec))
        throw CasuError("input media does not exist: " + input);

    const auto started = std::chrono::steady_clock::now();
    const JsonValue manifest = build_manifest(source, mode, analysis_fps);
    const double elapsed =
        std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    const JsonValue* source_info = manifest.find("source");

    JsonObject report;
    report.items["report"] = JsonValue(std::string("casu-benchmark-1"));
    report.items["input"] = JsonValue(source);
    if (source_info) {
        const JsonValue* size = source_info->find("size_bytes");
        report.items["source_size_bytes"] = size ? *size : json_null();
        const JsonValue* duration = source_info->find("duration_s");
        report.items["duration_s"] = duration ? *duration : json_null();
    } else {
        report.items["source_size_bytes"] = json_null();
        report.items["duration_s"] = json_null();
    }
    report.items["analysis_fps"] = JsonValue(analysis_fps);
    report.items["analysis_mode"] = JsonValue(mode);
    report.items["conversion_analysis_seconds"] = JsonValue(round6(elapsed));
    report.items["video_segments"] = JsonValue((int64_t)segment_count(manifest, "video"));
    report.items["audio_segments"] = JsonValue((int64_t)segment_count(manifest, "audio"));
    report.items["energy_measurement"] = JsonValue(std::string("unavailable"));
    auto notes = std::make_shared<casu::JsonArray>();
    notes->items.push_back(JsonValue(
        std::string("This report measures analysis cost; it does not claim energy savings.")));
    report.items["notes"] = JsonValue(std::move(notes));
    const JsonValue payload = JsonValue(std::make_shared<casu::JsonObject>(std::move(report)));
    const std::string text = pretty_json(payload) + "\n";
    if (args.has("-o")) atomic_write_text(abs_path(args.get("-o")), text);
    std::printf("%s", text.c_str());
    return 0;
}

int cmd_play(const Args& args) {
    const std::string input = args.positional.at(0);
    const std::string source = abs_path(input);
    std::error_code ec;
    if (!std::filesystem::exists(source, ec))
        throw CasuError("media not found: " + input);
    if (std::filesystem::path(source).extension().string() == ".casu") {
        try {
            const JsonValue parsed = casu::parse_json(
                [&]() {
                    FILE* f = std::fopen(source.c_str(), "rb");
                    if (!f) throw CasuError("invalid CASU manifest: " + input);
                    std::fseek(f, 0, SEEK_END);
                    long size = std::ftell(f);
                    std::fseek(f, 0, SEEK_SET);
                    if (size < 0) { std::fclose(f); throw CasuError("invalid CASU manifest: " + input); }
                    std::string text((std::size_t)size, '\0');
                    if (size > 0 && std::fread(&text[0], 1, (std::size_t)size, f) != (std::size_t)size) {
                        std::fclose(f); throw CasuError("invalid CASU manifest: " + input);
                    }
                    std::fclose(f);
                    return text;
                }());
            if (!casu::validate_manifest(parsed).empty())
                throw CasuError("invalid CASU manifest: " + input);
            casu::resolve_casu_source(source);
        } catch (const casu::CasuError&) {
            throw CasuError("invalid CASU manifest: " + input);
        }
    }
    throw CasuError("external playback is not supported; use the MPCASU in-process player");
}

int cmd_transcode(const Args& args) {
    if (args.get_long("--retry", 0) < 0) throw CasuError("retry count must not be negative");
    const std::string preset = args.get("--preset", "balanced");
    if (!casu::codec::is_known_preset(preset))
        throw CasuError("unsupported media conversion preset: " + preset);
    const std::string subtitle_mode = args.get("--subtitles", "auto");
    if (!casu::codec::is_known_subtitle_mode(subtitle_mode))
        throw CasuError("unsupported subtitle conversion mode: " + subtitle_mode);

    const auto planned = plan_inputs(args.positional, false);
    if (planned.empty()) throw CasuError("no media files found in the requested inputs");
    std::vector<std::string> sources;
    for (const auto& [source, relative] : planned) sources.push_back(source);

    const std::string destination = abs_path(args.get("-o", args.get("--output", "")));
    if (destination.empty()) throw CasuError("transcode requires an output path (-o/--output)");
    const bool force = args.flag("--force");
    const int retries = static_cast<int>(args.get_long("--retry", 0));

    bool single_file = sources.size() == 1 && args.positional.size() == 1 &&
                       std::filesystem::is_regular_file(sources[0]) &&
                       !std::filesystem::path(destination).extension().string().empty() &&
                       !args.has("--format");
    std::string selected_format;
    std::string output_dir;
    std::vector<std::string> targets;
    if (single_file) {
        const std::string ext = std::filesystem::path(destination).extension().string();
        if (media_output_extensions().count(lowercase(ext)) == 0)
            throw CasuError("unsupported media output extension");
        targets.push_back(destination);
        output_dir = std::filesystem::path(destination).parent_path().string();
        selected_format = std::filesystem::path(destination).extension().string().substr(1);
    } else {
        if (!std::filesystem::path(destination).extension().string().empty())
            throw CasuError("multiple media inputs require an output directory");
        const std::string format = args.get("--format");
        if (format.empty()) throw CasuError("multiple media inputs require --format");
        std::string extension = lowercase(format);
        if (!extension.empty() && extension[0] != '.') extension = "." + extension;
        if (media_output_extensions().count(extension) == 0)
            throw CasuError("unsupported media output extension");
        std::error_code ec;
        std::filesystem::create_directories(destination, ec);
        targets = plan_format_targets(planned, destination, extension);
        output_dir = destination;
        selected_format = extension.substr(1);
    }

    casu::codec::TranscodeOptions options;
    options.preset = preset;
    options.video_codec = args.get("--video-codec", "auto");
    options.audio_codec = args.get("--audio-codec", "auto");
    options.subtitle_mode = subtitle_mode;
    options.all_tracks = !args.flag("--first-tracks");
    options.preserve_metadata = !args.flag("--strip-metadata");

    auto files = std::make_shared<casu::JsonArray>();
    const JsonValue profile = transcode_profile(preset, options.video_codec, options.audio_codec,
                                                options.subtitle_mode, options.all_tracks,
                                                options.preserve_metadata);
    std::vector<JournalJob> jobs;
    for (std::size_t i = 0; i < sources.size(); ++i)
        jobs.push_back(JournalJob{sources[i], targets[i], profile});
    const std::string journal_path = conversion_journal_path(output_dir, jobs);
    const std::map<std::pair<std::string, std::string>, JsonValue> resumed =
        args.flag("--resume") ? load_resume(journal_path, jobs)
                              : std::map<std::pair<std::string, std::string>, JsonValue>{};

    for (std::size_t i = 0; i < sources.size(); ++i) {
        const std::string& source = sources[i];
        const std::string& target = targets[i];
        auto reuse_it = resumed.find({source, target});
        if (reuse_it != resumed.end()) {
            files->items.push_back(reuse_it->second);
            write_journal(journal_path, "RUNNING", jobs, JsonValue(files));
            continue;
        }
        // Linux parity (jobs.py): --force gates the overwrite, failed jobs
        // are retried up to `retries` times.
        int attempts = 0;
        double seconds = 0.0;
        double duration = 0.0;
        std::string error;
        while (true) {
            ++attempts;
            const auto started = std::chrono::steady_clock::now();
            try {
                if (path_size(target) >= 0 && !force)
                    throw CasuError("output exists (use force): " + target);
                casu::codec::BuiltTranscodeCommand built;
                try {
                    built = casu::codec::build_transcode_command(source, target, options);
                } catch (const casu::codec::MediaTranscodeError& exc) {
                    throw CasuError(std::string("transcode build failed: ") + exc.what());
                }
                if (const JsonValue* format = built.probe.find("format"))
                    if (const JsonValue* d = format->find("duration"))
                        if (d->is_number()) duration = d->as_double();
                // transcode_media parity: temp file + verify + atomic publish
                // (never expose a partial destination).
                casu::codec::transcode_atomic(built.args, target);
            } catch (const std::exception& exc) {
                error = exc.what();
                if (attempts <= retries) continue;  // retry
            }
            seconds = std::chrono::duration<double>(
                          std::chrono::steady_clock::now() - started)
                          .count();
            break;
        }
        long long output_size = error.empty() ? path_size(target) : -1;
JsonObject entry = conversion_result_entry(
            source, target, error.empty() ? "converted" : "failed", selected_format, error,
            round6(seconds), output_size, path_size(source), error.empty() ? casu::sha256_file(source) : "",
            error.empty() ? casu::sha256_file(target) : "",
            error.empty() ? "FFPROBE_VERIFIED" : "", attempts).as_object_mut();
        entry.items["duration_s"] = JsonValue(duration);
        files->items.push_back(JsonValue(std::make_shared<JsonObject>(std::move(entry))));
        write_journal(journal_path, "RUNNING", jobs, JsonValue(files));
    }
    write_journal(journal_path, "COMPLETE", jobs, JsonValue(files));

    JsonObject payload;
    payload.items["version"] = JsonValue(int64_t(1));
    payload.items["state"] = JsonValue(std::string("COMPLETE"));
    payload.items["mode"] = JsonValue(std::string("media-transcode"));
    payload.items["container"] = JsonValue(selected_format);
    payload.items["preset"] = JsonValue(preset);
    payload.items["files"] = JsonValue(std::move(files));
    const JsonValue payload_value = JsonValue(std::make_shared<casu::JsonObject>(std::move(payload)));
    write_report(args.get("--report"), payload_value);
    std::printf("%s\n", pretty_json(payload_value).c_str());
    return error_all_ok(payload_value) ? 0 : 1;
}

int cmd_export(const Args& args) {
    const auto planned = plan_inputs(args.positional, true);
    if (planned.empty()) throw CasuError("no .casu files found in the requested export inputs");
    std::vector<std::string> sources;
    for (const auto& [source, relative] : planned) sources.push_back(source);

    const std::string destination = abs_path(args.get("-o", args.get("--output", "")));
    if (destination.empty()) throw CasuError("export requires an output path (-o/--output)");

    bool single_file = sources.size() == 1 && args.positional.size() == 1 &&
                       std::filesystem::is_regular_file(sources[0]) &&
                       !std::filesystem::path(destination).extension().string().empty() &&
                       !args.has("--format");
    std::string export_format;
    std::vector<std::string> targets;
    if (single_file) {
        targets.push_back(destination);
        export_format = std::filesystem::path(destination).extension().string().substr(1);
    } else {
        if (!std::filesystem::path(destination).extension().string().empty())
            throw CasuError("multiple export inputs require an output directory");
        const std::string format = args.get("--format");
        if (format.empty()) throw CasuError("multiple export inputs require --format");
        std::error_code ec;
        std::filesystem::create_directories(destination, ec);
        std::string extension = lowercase(format);
        if (!extension.empty() && extension[0] != '.') extension = "." + extension;
        targets = plan_format_targets(planned, destination, extension);
        export_format = extension.substr(1);
    }

    auto files = std::make_shared<casu::JsonArray>();
    for (std::size_t i = 0; i < sources.size(); ++i) {
        const std::string& source = sources[i];
        const std::string& target = targets[i];
        const auto started = std::chrono::steady_clock::now();
        std::string error;
        try {
            casu::codec::export_casu(source, target);
        } catch (const std::exception& exc) {
            error = exc.what();
        }
        const double seconds =
            std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
        JsonObject entry;
        entry.items["source"] = JsonValue(source);
        entry.items["output"] = JsonValue(target);
        entry.items["status"] = JsonValue(error.empty() ? std::string("exported") : std::string("failed"));
        if (!error.empty()) entry.items["error"] = JsonValue(error);
        entry.items["conversion_seconds"] = JsonValue(round6(seconds));
        files->items.push_back(JsonValue(std::make_shared<casu::JsonObject>(std::move(entry))));
    }

    JsonObject payload;
    payload.items["version"] = JsonValue(int64_t(1));
    payload.items["state"] = JsonValue(std::string("COMPLETE"));
    payload.items["mode"] = JsonValue(std::string("export"));
    payload.items["container"] = JsonValue(export_format);
    payload.items["files"] = JsonValue(std::move(files));
    const JsonValue payload_value = JsonValue(std::make_shared<casu::JsonObject>(std::move(payload)));
    write_report(args.get("--report"), payload_value);
    std::printf("%s\n", pretty_json(payload_value).c_str());
    return error_all_ok(payload_value) ? 0 : 1;
}

}  // namespace casu::cli
