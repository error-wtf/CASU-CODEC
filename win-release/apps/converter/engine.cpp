// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "engine.hpp"
#include "manifest.hpp"

#include "casu/codec/export.hpp"
#include "casu/codec/ffmpeg.hpp"
#include "casu/codec/presets.hpp"
#include "casu/formats.hpp"
#include "casu/json.hpp"
#include "casu/media/mediainfo.hpp"
#include "casu/mp5.hpp"
#include "casu/native.hpp"
#include "casu/sha256.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <map>
#include <random>
#include <set>
#include <thread>
#include <tuple>
#include <utility>
#include <vector>

namespace casu::conv {

namespace fs = std::filesystem;

using casu::CasuError;
using casu::JsonValue;

namespace {

const std::set<std::string>& output_extension_set() {
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

std::string unique_temp_path(const fs::path& dir, const std::string& prefix,
                             const std::string& suffix) {
    static std::mt19937_64 gen(std::random_device{}());
    for (int attempt = 0; attempt < 32; ++attempt) {
        const fs::path candidate = dir / (prefix + std::to_string(gen()) + suffix);
        std::error_code ec;
        if (!fs::exists(candidate, ec)) return candidate.string();
    }
    throw CasuError("could not allocate a temporary output path");
}

void atomic_write_text(const std::string& path, const std::string& payload) {
    fs::path target = fs::absolute(path);
    std::error_code ec;
    fs::create_directories(target.parent_path(), ec);
    const fs::path temporary = target.parent_path() / ("." + target.filename().string() + ".tmp");
    {
        FILE* f = std::fopen(temporary.string().c_str(), "wb");
        if (!f) throw CasuError("could not create output file: " + path);
        const bool wrote = std::fwrite(payload.data(), 1, payload.size(), f) == payload.size();
        std::fflush(f);
        std::fclose(f);
        if (!wrote) {
            fs::remove(temporary, ec);
            throw CasuError("could not write output file: " + path);
        }
    }
    fs::remove(target, ec);
    fs::rename(temporary, target, ec);
    if (ec) {
        fs::remove(temporary, ec);
        throw CasuError("could not finalize output file: " + path);
    }
}

void atomic_rename(const std::string& source, const std::string& destination) {
    std::error_code ec;
    fs::remove(destination, ec);
    fs::rename(source, destination, ec);
    if (ec) {
        fs::remove(source, ec);
        throw CasuError("could not finalize output: " + destination);
    }
}

std::string file_identity_sha256(const std::string& path, long long& size) {
    size = -1;
    std::error_code ec;
    if (!fs::exists(path, ec)) return {};
    size = (long long)fs::file_size(path, ec);
    return casu::sha256_file(path);
}

double probe_duration_seconds(const JsonValue& probe) {
    const JsonValue* format = probe.find("format");
    const JsonValue* duration = format ? format->find("duration") : nullptr;
    if (duration && duration->is_number() && duration->as_double() > 0)
        return duration->as_double();
    if (const JsonValue* streams = probe.find("streams"))
        if (streams->is_array())
            for (const JsonValue& stream : streams->as_array().items) {
                const JsonValue* d = stream.find("duration");
                if (d && d->is_number() && d->as_double() > 0) return d->as_double();
            }
    return 0.0;
}

void write_mp5_container(const std::string& source, const std::string& output,
                         const std::string& mode) {
    constexpr std::size_t kPartBytes = 16ULL * 1024 * 1024;
    std::error_code ec;
    const std::uintmax_t size = fs::file_size(source, ec);
    if (ec) throw CasuError("could not stat source: " + source);
    if (size > 512ULL * 1024 * 1024)
        throw CasuError("source too large for a single-part MP5 attachment");
    FILE* f = std::fopen(source.c_str(), "rb");
    if (!f) throw CasuError("could not read source: " + source);
    std::vector<uint8_t> data((std::size_t)size);
    const bool ok = std::fread(data.data(), 1, data.size(), f) == data.size();
    std::fclose(f);
    if (!ok) throw CasuError("could not read source: " + source);

    const JsonValue manifest = build_casu_manifest(source, mode);
    casu::media::MediaInfo info;
    try {
        info = casu::media::probe(source);
    } catch (const casu::media::MediaProbeError& exc) {
        throw CasuError(std::string("media probe failed: ") + exc.what());
    }

    std::vector<std::tuple<casu::mp5::ChunkType, uint8_t, uint32_t, std::vector<uint8_t>>> chunks;
    int stream_id = 1;
    for (const casu::media::MediaStreamInfo& stream : info.streams) {
        if (stream.codec_type != "video" && stream.codec_type != "audio") continue;
        if (stream.codec_type == "video" && stream.attached_pic) continue;
        casu::JsonObject config;
        config.items["stream_id"] = JsonValue((int64_t)stream_id);
        config.items["type"] = JsonValue(stream.codec_type);
        config.items["codec"] = JsonValue(stream.codec_name);
        config.items["width"] = stream.codec_type == "video"
                                    ? JsonValue((int64_t)stream.width)
                                    : JsonValue(std::nullptr_t{});
        config.items["height"] = stream.codec_type == "video"
                                     ? JsonValue((int64_t)stream.height)
                                     : JsonValue(std::nullptr_t{});
        config.items["channels"] = stream.codec_type == "audio"
                                       ? JsonValue((int64_t)stream.channels)
                                       : JsonValue(std::nullptr_t{});
        config.items["sample_rate"] = stream.codec_type == "audio"
                                          ? JsonValue(stream.sample_rate > 0
                                                          ? std::to_string(stream.sample_rate)
                                                          : std::string("0"))
                                          : JsonValue(std::nullptr_t{});
        const std::string config_json =
            casu::dump_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(config))));
        chunks.emplace_back(casu::mp5::STREAM_CONFIG, (uint8_t)stream_id, 0,
                            std::vector<uint8_t>(config_json.begin(), config_json.end()));
        ++stream_id;
    }
    if (stream_id == 1) throw CasuError("input contains no playable audio or video stream");

    const std::string filename = fs::path(source).filename().string();
    const int parts = (int)((data.size() + kPartBytes - 1) / kPartBytes);
    for (int part = 0; part < parts; ++part) {
        const std::size_t offset = (std::size_t)part * kPartBytes;
        const std::size_t length = std::min(kPartBytes, data.size() - offset);
        casu::JsonObject meta;
        meta.items["filename"] = JsonValue(filename);
        meta.items["part"] = JsonValue((int64_t)part);
        meta.items["parts"] = JsonValue((int64_t)parts);
        const std::string meta_json =
            casu::dump_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(meta))));
        std::vector<uint8_t> payload;
        payload.push_back(uint8_t(meta_json.size() & 0xFF));
        payload.push_back(uint8_t((meta_json.size() >> 8) & 0xFF));
        payload.insert(payload.end(), meta_json.begin(), meta_json.end());
        payload.insert(payload.end(), data.begin() + (std::ptrdiff_t)offset,
                       data.begin() + (std::ptrdiff_t)(offset + length));
        chunks.emplace_back(casu::mp5::ATTACHMENT, 0, 0, std::move(payload));
    }

    const std::string digest = casu::sha256_file(source);
    casu::JsonObject integrity;
    integrity.items["source_sha256"] = JsonValue(digest);
    integrity.items["attachment_sha256"] = JsonValue(digest);
    integrity.items["attachment_parts"] = JsonValue((int64_t)parts);
    integrity.items["chunk_count"] = JsonValue((int64_t)chunks.size());
    const std::string integrity_json =
        casu::dump_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(integrity))));
    chunks.emplace_back(casu::mp5::INTEGRITY_TABLE, 0, 0,
                        std::vector<uint8_t>(integrity_json.begin(), integrity_json.end()));

    casu::JsonObject metadata;
    metadata.items["converted_by"] = JsonValue(std::string("casu.converter"));
    metadata.items["mode"] = JsonValue(mode);
    const std::string metadata_json =
        casu::dump_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(metadata))));
    chunks.emplace_back(casu::mp5::METADATA, 0, 0,
                        std::vector<uint8_t>(metadata_json.begin(), metadata_json.end()));
    chunks.emplace_back(casu::mp5::END, 0, 0, std::vector<uint8_t>{});

    casu::mp5::write_mp5(output, manifest, chunks);
    const std::vector<std::string> problems = casu::mp5::verify_mp5(output);
    if (!problems.empty()) throw CasuError("MP5 verification failed: " + problems[0]);
}

ConversionResult result_base(const ConversionJob& job) {
    ConversionResult out;
    out.source = job.source;
    out.output = job.output;
    out.container = container_name(job.profile);
    return out;
}

ConversionResult convert_media(const ConversionJob& job, const FfmpegExecutor& executor,
                               const std::function<void(double)>& job_progress,
                               const std::function<bool()>& cancelled) {
    if (!executor) throw CasuError("no ffmpeg executor configured");
    fs::path parent = fs::path(job.output).parent_path();
    if (parent.empty()) parent = ".";
    const std::string suffix = fs::path(job.output).extension().string();
    const std::string temporary =
        unique_temp_path(parent, "." + fs::path(job.output).stem().string() + ".", suffix);

    casu::codec::TranscodeOptions options;
    options.preset = job.profile.media_preset;
    options.video_codec = job.profile.video_codec;
    options.audio_codec = job.profile.audio_codec;
    options.subtitle_mode = job.profile.subtitle_mode;
    options.all_tracks = job.profile.all_tracks;
    options.preserve_metadata = job.profile.preserve_metadata;

    casu::codec::BuiltTranscodeCommand built;
    try {
        built = casu::codec::build_transcode_command(job.source, temporary, options);
    } catch (const std::exception& exc) {
        throw CasuError(std::string("transcode build failed: ") + exc.what());
    }
    const double duration = probe_duration_seconds(built.probe);
    const RunOutcome outcome = executor(built.args, duration, job_progress, cancelled);
    if (!outcome.ok)
        throw CasuError(outcome.error.empty() ? "FFmpeg conversion failed" : outcome.error);

    std::error_code ec;
    if (!fs::exists(temporary, ec) || fs::file_size(temporary, ec) <= 0) {
        fs::remove(temporary, ec);
        throw CasuError("FFmpeg produced an empty output");
    }
    if (job.profile.force) fs::remove(job.output, ec);
    fs::rename(temporary, job.output, ec);
    if (ec) {
        fs::remove(temporary, ec);
        throw CasuError("could not finalize output: " + job.output);
    }
    ConversionResult out = result_base(job);
    out.status = "converted";
    out.verification = "FFPROBE_VERIFIED";
    out.output_sha256 = file_identity_sha256(job.output, out.output_size);
    return out;
}

ConversionResult convert_to_casu(const ConversionJob& job,
                                 const std::function<bool()>& cancelled) {
    if (cancelled && cancelled()) throw ConversionCancelled{};
    const std::string mode = job.profile.analysis_mode.empty()
                                 ? "strict"
                                 : job.profile.analysis_mode;
    const JsonValue manifest = build_casu_manifest(job.source, mode);
    if (cancelled && cancelled()) throw ConversionCancelled{};
    if (job.profile.casu_container == CasuContainer::Sidecar) {
        atomic_write_text(job.output, casu::dump_json(manifest));
    } else if (job.profile.casu_container == CasuContainer::Native) {
        casu::casunat1::write_native(job.output, job.source, manifest);
        casu::casunat1::read_native(job.output, true);
    } else {
        write_mp5_container(job.source, job.output, mode);
    }
    ConversionResult out = result_base(job);
    out.status = "converted";
    out.verification = "VERIFIED";
    out.output_sha256 = file_identity_sha256(job.output, out.output_size);
    return out;
}

ConversionResult export_from_casu(const ConversionJob& job,
                                  const std::function<bool()>& cancelled) {
    if (cancelled && cancelled()) throw ConversionCancelled{};
    casu::codec::export_casu(job.source, job.output);
    ConversionResult out = result_base(job);
    out.status = "exported";
    out.verification = "EXPORTED";
    out.output_sha256 = file_identity_sha256(job.output, out.output_size);
    return out;
}

}  // namespace

void write_batch_report(const std::string& output_dir, const std::string& state,
                        const ConversionProfile& profile, int retries,
                        const std::vector<ConversionResult>& results) {
    casu::JsonObject root;
    root.items["version"] = JsonValue((int64_t)1);
    root.items["state"] = JsonValue(state);
    root.items["mode"] = JsonValue(profile.analysis_mode);
    root.items["container"] = JsonValue(container_name(profile));
    if (profile.direction == Direction::MediaToMedia)
        root.items["preset"] = JsonValue(profile.media_preset);
    root.items["analysis_fps"] = JsonValue(profile.analysis_fps);
    root.items["retries"] = JsonValue((int64_t)retries);
    root.items["tile_size"] = JsonValue((int64_t)profile.tile_size);
    root.items["key_interval_seconds"] = JsonValue(profile.key_interval_seconds);
    casu::JsonArray files;
    for (const ConversionResult& r : results) {
        casu::JsonObject entry;
        entry.items["source"] = JsonValue(r.source);
        entry.items["output"] = JsonValue(r.output);
        entry.items["status"] = JsonValue(r.status);
        entry.items["container"] = JsonValue(r.container);
        if (!r.error.empty()) entry.items["error"] = JsonValue(r.error);
        if (!r.output_sha256.empty())
            entry.items["output_sha256"] = JsonValue(r.output_sha256);
        if (r.output_size >= 0) entry.items["output_size"] = JsonValue(r.output_size);
        files.items.push_back(
            JsonValue(std::make_shared<casu::JsonObject>(std::move(entry))));
    }
    root.items["files"] =
        JsonValue(std::make_shared<casu::JsonArray>(std::move(files)));
    atomic_write_text((fs::path(output_dir) / "casu_batch_report.json").string(),
                      casu::dump_json(JsonValue(std::make_shared<casu::JsonObject>(
                          std::move(root)))));
}

std::string container_name(const ConversionProfile& profile) {
    switch (profile.direction) {
        case Direction::MediaToMedia:
        case Direction::FromCasu: {
            std::string ext = lowercase(profile.output_extension);
            if (!ext.empty() && ext[0] == '.') ext.erase(ext.begin());
            return ext;
        }
        case Direction::ToCasu:
            switch (profile.casu_container) {
                case CasuContainer::Sidecar: return "sidecar";
                case CasuContainer::Native: return "native";
                case CasuContainer::Mp5: return "mp5";
            }
            return "casu";
    }
    return "media";
}

const std::vector<std::string>& ConversionEngine::output_extensions() {
    static const std::vector<std::string> value(output_extension_set().begin(),
                                                output_extension_set().end());
    return value;
}

std::string ConversionEngine::plan_output(const std::string& source,
                                          const std::string& output_dir,
                                          const ConversionProfile& profile) {
    std::string ext;
    if (profile.direction == Direction::ToCasu) {
        ext = ".casu";
    } else {
        ext = lowercase(profile.output_extension);
        if (!ext.empty() && ext[0] != '.') ext = "." + ext;
        if (output_extension_set().count(ext) == 0)
            throw CasuError("unsupported media output extension: " + profile.output_extension);
    }
    const std::string stem = fs::path(source).stem().string();
    return (fs::path(output_dir) / (stem + ext)).string();
}

std::vector<std::string> ConversionEngine::build_ffmpeg_args(const ConversionJob& job) {
    casu::codec::TranscodeOptions options;
    options.preset = job.profile.media_preset;
    options.video_codec = job.profile.video_codec;
    options.audio_codec = job.profile.audio_codec;
    options.subtitle_mode = job.profile.subtitle_mode;
    options.all_tracks = job.profile.all_tracks;
    options.preserve_metadata = job.profile.preserve_metadata;
    const casu::codec::BuiltTranscodeCommand built =
        casu::codec::build_transcode_command(job.source, job.output, options);
    return built.args;
}

std::vector<ConversionResult> ConversionEngine::run(
    const std::vector<ConversionJob>& jobs, const FfmpegExecutor& executor,
    const std::function<void(const ConversionProgress&)>& progress,
    const std::function<bool()>& cancelled, const std::function<bool()>& paused,
    int retries) {
    if (retries < 0) retries = 0;
    if (retries > 10) retries = 10;
    auto wait_while_paused = [&]() {
        while (paused && paused() && !(cancelled && cancelled()))
            std::this_thread::sleep_for(std::chrono::milliseconds(120));
    };
    std::vector<ConversionResult> results;
    results.reserve(jobs.size());
    const int count = (int)jobs.size();
    const auto started_at = std::chrono::steady_clock::now();
    double overall = 0.0;

    auto notify = [&](int index, const std::string& source, double fraction,
                      const std::string& state) {
        if (!progress) return;
        double raw = count > 0 ? (index + fraction) / count : 1.0;
        overall = std::max(overall, std::min(1.0, raw));
        ConversionProgress p;
        p.job_index = index;
        p.job_count = count;
        p.source = source;
        p.fraction = std::max(0.0, std::min(1.0, fraction));
        p.overall = overall;
        p.elapsed_seconds =
            std::chrono::duration<double>(std::chrono::steady_clock::now() - started_at).count();
        p.eta_seconds = (overall >= 1.0)
                            ? 0.0
                            : (overall > 0.0 && p.elapsed_seconds > 0.0
                                   ? p.elapsed_seconds * (1.0 - overall) / overall
                                   : -1.0);
        p.state = state;
        progress(p);
    };

    for (int i = 0; i < count; ++i) {
        if (cancelled && cancelled()) throw ConversionCancelled{};
        wait_while_paused();
        if (cancelled && cancelled()) throw ConversionCancelled{};
        const ConversionJob& job = jobs[(std::size_t)i];
        notify(i, job.source, 0.0, "RUNNING");
        const auto job_started = std::chrono::steady_clock::now();
        ConversionResult result;
        // Linux parity: failed jobs are retried up to `retries` times.
        for (int attempt = 0; attempt <= retries; ++attempt) {
            try {
                if (job.profile.direction == Direction::FromCasu)
                    result = export_from_casu(job, cancelled);
                else if (job.profile.direction == Direction::ToCasu)
                    result = convert_to_casu(job, cancelled);
                else
                    result = convert_media(
                        job, executor,
                        [&](double fraction) { notify(i, job.source, fraction, "RUNNING"); },
                        [&] {
                            wait_while_paused();
                            return cancelled && cancelled();
                        });
                result.conversion_seconds = std::chrono::duration<double>(
                    std::chrono::steady_clock::now() - job_started)
                                                .count();
                break;
            } catch (const ConversionCancelled&) {
                throw;
            } catch (const std::exception& exc) {
                if (attempt == retries) {
                    result = result_base(job);
                    result.status = "failed";
                    result.error = exc.what();
                    result.conversion_seconds = std::chrono::duration<double>(
                        std::chrono::steady_clock::now() - job_started)
                                                    .count();
                } else {
                    wait_while_paused();
                    if (cancelled && cancelled()) throw ConversionCancelled{};
                }
            }
        }
        results.push_back(result);
        const std::string state =
            result.status == "failed" ? "FAILED" : (result.status == "exported" ? "EXPORTED" : "DONE");
        notify(i, job.source, 1.0, state);
    }
    return results;
}

FfmpegExecutor sync_ffmpeg_executor() {
    return [](const std::vector<std::string>& args, double, const std::function<void(double)>&,
              const std::function<bool()>&) -> RunOutcome {
        try {
            casu::codec::Ffmpeg ffmpeg;
            const casu::codec::ProcessResult result = ffmpeg.run_checked(args);
            return RunOutcome{true, {}, result.stdout_data};
        } catch (const std::exception& exc) {
            return RunOutcome{false, exc.what(), {}};
        }
    };
}

}  // namespace casu::conv