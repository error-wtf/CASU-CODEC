// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/codec/export.hpp"

#include "casu/codec/ffmpeg.hpp"
#include "casu/codec/ffprobe.hpp"
#include "casu/formats.hpp"
#include "casu/json.hpp"
#include "casu/mp5.hpp"
#include "casu/native.hpp"
#include "casu/sidecar.hpp"

#include <chrono>
#include <cstdio>
#include <filesystem>
#include <map>
#include <random>
#include <set>
#include <string>
#include <vector>

namespace casu::codec {

namespace {

const std::set<std::string>& audio_extensions() {
    static const std::set<std::string> value = {
        ".aac", ".aiff", ".alac", ".flac", ".m4a", ".mka", ".mp3",
        ".oga", ".ogg", ".opus", ".wav", ".wma",
    };
    return value;
}

std::string lowercase_extension(const std::string& path) {
    std::string ext = std::filesystem::path(path).extension().string();
    for (char& c : ext) {
        if (c >= 'A' && c <= 'Z') c = char(c + ('a' - 'A'));
    }
    return ext;
}

std::string unique_temp_path(const std::filesystem::path& dir, const std::string& prefix,
                             const std::string& suffix) {
    static std::mt19937_64 gen(std::random_device{}());
    for (int attempt = 0; attempt < 16; ++attempt) {
        const std::filesystem::path candidate =
            dir / (prefix + std::to_string(gen()) + suffix);
        std::error_code ec;
        if (!std::filesystem::exists(candidate, ec)) return candidate.string();
    }
    throw CasuExportError("could not allocate a temporary path in " + dir.string());
}

void remove_file(const std::string& path) {
    std::error_code ec;
    std::filesystem::remove(path, ec);
}

std::vector<std::string> codec_options(const std::string& destination, bool has_video,
                                       bool has_audio, bool has_subtitles,
                                       bool has_rich_subtitles) {
    if (!has_video) {
        static const std::map<std::string, std::vector<std::string>> audio_table = {
            {".mp3", {"-c:a", "libmp3lame", "-q:a", "2"}},
            {".flac", {"-c:a", "flac"}},
            {".wav", {"-c:a", "pcm_s16le"}},
            {".ogg", {"-c:a", "libvorbis", "-q:a", "6"}},
            {".oga", {"-c:a", "libvorbis", "-q:a", "6"}},
            {".opus", {"-c:a", "libopus", "-b:a", "160k"}},
            {".m4a", {"-c:a", "aac", "-b:a", "192k"}},
            {".aac", {"-c:a", "aac", "-b:a", "192k"}},
        };
        const auto it = audio_table.find(lowercase_extension(destination));
        return it == audio_table.end() ? std::vector<std::string>{} : it->second;
    }
    const std::string ext = lowercase_extension(destination);
    std::vector<std::string> video =
        ext == ".webm" ? std::vector<std::string>{"-c:v", "libvpx-vp9", "-crf", "24", "-b:v", "0"}
        : ext == ".avi" ? std::vector<std::string>{"-c:v", "mpeg4", "-q:v", "3"}
                        : std::vector<std::string>{"-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p"};
    std::vector<std::string> result = video;
    if (has_audio) {
        const std::vector<std::string> audio =
            ext == ".webm" ? std::vector<std::string>{"-c:a", "libopus", "-b:a", "160k"}
                           : std::vector<std::string>{"-c:a", "aac", "-b:a", "192k"};
        result.insert(result.end(), audio.begin(), audio.end());
    }
    if (has_subtitles) {
        const std::vector<std::string> subtitle =
            ext == ".webm" ? std::vector<std::string>{"-c:s", "webvtt"}
            : (ext == ".mp4" || ext == ".m4v" || ext == ".mov")
                ? std::vector<std::string>{"-c:s", "mov_text"}
                : has_rich_subtitles ? std::vector<std::string>{"-c:s", "ass"}
                                     : std::vector<std::string>{"-c:s", "srt"};
        result.insert(result.end(), subtitle.begin(), subtitle.end());
    }
    return result;
}

bool path_has_stream(const JsonValue& probe, const std::string& codec_type) {
    const JsonValue* streams = probe.find("streams");
    if (!streams || !streams->is_array()) return false;
    for (const JsonValue& item : streams->as_array().items) {
        const JsonValue* type = item.find("codec_type");
        if (type && type->is_string() && type->as_string() == codec_type) return true;
    }
    return false;
}

std::string safe_source_name(const JsonValue& manifest) {
    const JsonValue* source = manifest.find("source");
    if (!source || !source->is_object()) throw CasuExportError("CASUNAT1 source is invalid");
    const JsonValue* filename = source->find("filename");
    if (!filename || !filename->is_string()) throw CasuExportError("CASUNAT1 source filename is invalid");
    const std::string raw = std::filesystem::path(filename->as_string()).filename().string();
    if (raw.empty() || raw == "." || raw == "..")
        throw CasuExportError("CASUNAT1 source filename is invalid");
    return raw;
}

// Extract the embedded original media from a supported CASU representation
// into a temporary file. Returns the temporary file path.
std::string legacy_source(const std::string& casu_path,
                          const std::filesystem::path& work_dir) {
    const casu::CasuKind kind = casu::detect_casu_kind(casu_path);
    if (kind == casu::CasuKind::Casunat1) {
        const casunat1::Container container = casunat1::read_native(casu_path, true);
        const std::string source_name = safe_source_name(container.manifest);
        const std::string out = (work_dir / source_name).string();
        container.extract_payload(out);
        return out;
    }
    if (kind == casu::CasuKind::Sidecar) return casu::resolve_casu_source(casu_path);
    if (kind == casu::CasuKind::Mp5) {
        const std::pair<std::string, std::vector<uint8_t>> attachment =
            casu::mp5::extract_attachment(casu_path);
        std::string filename = std::filesystem::path(attachment.first).filename().string();
        if (filename.empty()) filename = "payload.bin";
        const std::string out = (work_dir / filename).string();
        FILE* f = std::fopen(out.c_str(), "wb");
        if (!f) throw CasuExportError("could not create temp media: " + out);
        const std::vector<uint8_t>& data = attachment.second;
        const bool wrote = std::fwrite(data.data(), 1, data.size(), f) == data.size();
        std::fclose(f);
        if (!wrote) {
            remove_file(out);
            throw CasuExportError("could not write temp media: " + out);
        }
        return out;
    }
    if (kind == casu::CasuKind::Casunat2)
        throw CasuExportError(
            "CASUNAT2 native export requires the native decoder (planned; "
            "not yet implemented in this phase)");
    throw CasuExportError("input is not a recognised CASU representation");
}

// Run ffmpeg to a temporary file in the destination directory, verify the
// output, then atomically rename it over the destination.
std::string atomic_ffmpeg_impl(const std::vector<std::string>& args,
                               const std::string& destination,
                               bool append_output_arg) {
    const std::filesystem::path dest(destination);
    std::filesystem::path parent = dest.parent_path();
    if (parent.empty()) parent = ".";
    const std::string suffix = lowercase_extension(destination).empty() ? ".media" : dest.extension().string();
    const std::string temporary =
        unique_temp_path(parent, "." + dest.stem().string() + ".", suffix);
    std::vector<std::string> command = args;
    if (append_output_arg) command.push_back(temporary);
    else if (!command.empty()) command.back() = temporary;  // replace output arg
    try {
        Ffmpeg ffmpeg;
        ffmpeg.run_checked(command);
        std::error_code ec;
        if (!std::filesystem::exists(temporary, ec) ||
            std::filesystem::file_size(temporary, ec) == 0)
            throw CasuExportError("FFmpeg produced an empty export");
        JsonValue output_probe;
        try {
            output_probe = probe_json(temporary);
        } catch (const MediaProbeError& exc) {
            throw CasuExportError(std::string("exported output is unreadable: ") + exc.what());
        }
        if (!path_has_stream(output_probe, "video") && !path_has_stream(output_probe, "audio"))
            throw CasuExportError("converted output has no playable stream");
        remove_file(destination);
        std::filesystem::rename(temporary, dest, ec);
        if (ec) {
            remove_file(temporary);
            throw CasuExportError("could not finalize export: " + destination);
        }
        return destination;
    } catch (...) {
        remove_file(temporary);
        throw;
    }
}
}

// Public transcode_media parity entry point: args carry the FINAL output as
// last argument (build_transcode_command form); it is swapped for a temp path
// and published atomically after verification.
std::string transcode_atomic(const std::vector<std::string>& args,
                             const std::string& destination) {
    return atomic_ffmpeg_impl(args, destination, /*append_output_arg=*/false);
}

void export_casu(const std::string& source, const std::string& destination) {
    std::error_code ec;
    const std::filesystem::path source_abs = std::filesystem::absolute(source, ec).lexically_normal();
    const std::filesystem::path dest_abs = std::filesystem::absolute(destination, ec).lexically_normal();
    if (ec || !std::filesystem::is_regular_file(source_abs, ec))
        throw CasuExportError("export input must be an existing CASU file");
    if (dest_abs == source_abs || dest_abs.extension().empty())
        throw CasuExportError("export destination must use a media-file extension");

    std::filesystem::path work_dir;
    for (int attempt = 0; attempt < 8; ++attempt) {
        static std::mt19937_64 gen(std::random_device{}());
        work_dir = std::filesystem::temp_directory_path() /
                   ("casu-export-" + std::to_string(gen()));
        if (std::filesystem::create_directory(work_dir, ec)) break;
    }
    if (ec || !std::filesystem::exists(work_dir, ec))
        throw CasuExportError("could not create export working directory");

    try {
        const std::string legacy = legacy_source(source_abs.string(), work_dir);
        const bool is_audio = audio_extensions().count(lowercase_extension(dest_abs.string())) != 0;
        JsonValue overview;
        try {
            overview = probe_json(legacy);
        } catch (const MediaProbeError& exc) {
            throw CasuExportError(std::string("media probe failed: ") + exc.what());
        }
        const bool has_video = path_has_stream(overview, "video") && !is_audio;
        const bool has_audio = path_has_stream(overview, "audio");
        const bool has_subtitles = path_has_stream(overview, "subtitle") && !is_audio;

        std::vector<std::string> args = {"-v", "error", "-y", "-i", legacy};
        if (is_audio) {
            args.push_back("-map"), args.push_back("0:a:0");
        } else {
            args.push_back("-map"), args.push_back("0:v?");
            args.push_back("-map"), args.push_back("0:a?");
            args.push_back("-map"), args.push_back("0:s?");
            args.push_back("-map_chapters"), args.push_back("0");
        }
        const std::vector<std::string> options =
            codec_options(dest_abs.string(), has_video, has_audio, has_subtitles, false);
        args.insert(args.end(), options.begin(), options.end());
        atomic_ffmpeg_impl(args, dest_abs.string(), /*append_output_arg=*/true);
    } catch (...) {
        std::error_code cleanup;
        std::filesystem::remove_all(work_dir, cleanup);
        throw;
    }
    std::error_code cleanup;
    std::filesystem::remove_all(work_dir, cleanup);
}

}  // namespace casu::codec
