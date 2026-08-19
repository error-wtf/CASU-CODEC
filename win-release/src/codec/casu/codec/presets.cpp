// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/codec/presets.hpp"

#include "casu/codec/ffmpeg.hpp"
#include "casu/codec/ffprobe.hpp"

#include <filesystem>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace casu::codec {

namespace {

const std::set<std::string>& media_presets() {
    static const std::set<std::string> value = {
        "remux", "balanced", "high", "small", "lossless",
    };
    return value;
}

const std::set<std::string>& subtitle_modes() {
    static const std::set<std::string> value = {"auto", "copy", "drop"};
    return value;
}

const std::set<std::string>& audio_extensions() {
    static const std::set<std::string> value = {
        ".aac", ".aif", ".aiff", ".alac", ".flac", ".m4a", ".mka", ".mp2",
        ".mp3", ".oga", ".ogg", ".opus", ".wav", ".wma",
    };
    return value;
}

const std::set<std::string>& video_extensions() {
    static const std::set<std::string> value = {
        ".3g2", ".3gp", ".asf", ".avi", ".f4v", ".flv", ".m2ts", ".m4v",
        ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".mts", ".ogv", ".ts",
        ".webm", ".wmv",
    };
    return value;
}

bool valid_codec_name(const std::string& name) {
    if (name.empty() || name.size() > 64) return false;
    for (char c : name) {
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || c == '_' || c == '+' || c == '.' || c == '-'))
            return false;
    }
    return true;
}

std::string lowercase_extension(const std::string& destination) {
    std::string ext = std::filesystem::path(destination).extension().string();
    for (char& c : ext) {
        if (c >= 'A' && c <= 'Z') c = char(c + ('a' - 'A'));
    }
    return ext;
}

struct AutomaticCodecs {
    std::string video;
    std::string audio;
    std::string subtitle;
};

const std::map<std::string, AutomaticCodecs>& automatic_codecs_table() {
    static const std::map<std::string, AutomaticCodecs> value = {
        {".mp4", {"libx264", "aac", "mov_text"}}, {".m4v", {"libx264", "aac", "mov_text"}},
        {".mov", {"libx264", "aac", "mov_text"}}, {".3gp", {"libx264", "aac", "mov_text"}},
        {".3g2", {"libx264", "aac", "mov_text"}}, {".mkv", {"libx264", "aac", "ass"}},
        {".webm", {"libvpx-vp9", "libopus", "webvtt"}},
        {".avi", {"mpeg4", "libmp3lame", {}}},
        {".ts", {"libx264", "aac", {}}}, {".mts", {"libx264", "aac", {}}},
        {".m2ts", {"libx264", "aac", {}}}, {".mpeg", {"mpeg2video", "mp2", {}}},
        {".mpg", {"mpeg2video", "mp2", {}}}, {".flv", {"flv", "libmp3lame", {}}},
        {".f4v", {"libx264", "aac", {}}}, {".ogv", {"libtheora", "libvorbis", {}}},
        {".wmv", {"wmv2", "wmav2", {}}}, {".asf", {"wmv2", "wmav2", {}}},
        {".mp3", {{}, "libmp3lame", {}}}, {".mp2", {{}, "mp2", {}}},
        {".flac", {{}, "flac", {}}}, {".wav", {{}, "pcm_s16le", {}}},
        {".aif", {{}, "pcm_s16be", {}}}, {".aiff", {{}, "pcm_s16be", {}}},
        {".ogg", {{}, "libvorbis", {}}}, {".oga", {{}, "libvorbis", {}}},
        {".opus", {{}, "libopus", {}}}, {".m4a", {{}, "aac", {}}},
        {".aac", {{}, "aac", {}}}, {".alac", {{}, "alac", {}}},
        {".mka", {{}, "flac", {}}}, {".wma", {{}, "wmav2", {}}},
    };
    return value;
}

const std::set<std::string>& multitrack_audio_containers() {
    static const std::set<std::string> value = {
        ".3g2", ".3gp", ".asf", ".avi", ".m4a", ".m4v", ".mka", ".mkv",
        ".mov", ".mp4", ".ts", ".mts", ".m2ts", ".webm", ".wmv",
    };
    return value;
}

long long stream_index(const JsonValue& stream) {
    const JsonValue* index = stream.find("index");
    if (index && index->is_number()) return static_cast<long long>(index->as_double());
    return -1;
}

std::vector<const JsonValue*> collect_streams(const JsonValue& probe,
                                              const std::string& codec_type,
                                              bool skip_attached_pic) {
    std::vector<const JsonValue*> out;
    const JsonValue* streams = probe.find("streams");
    if (!streams || !streams->is_array()) return out;
    for (const JsonValue& item : streams->as_array().items) {
        const JsonValue* type = item.find("codec_type");
        if (!type || !type->is_string() || type->as_string() != codec_type) continue;
        if (skip_attached_pic) {
            const JsonValue* disposition = item.find("disposition");
            if (disposition && disposition->is_object()) {
                const JsonValue* pic = disposition->find("attached_pic");
                if (pic && pic->is_int() && pic->as_int() != 0) continue;
            }
        }
        out.push_back(&item);
    }
    return out;
}

}  // namespace

bool is_known_preset(const std::string& preset) {
    return media_presets().count(preset) != 0;
}

bool is_known_subtitle_mode(const std::string& mode) {
    return subtitle_modes().count(mode) != 0;
}

std::vector<std::string> quality_options(const std::string& codec,
                                         const std::string& preset, bool audio) {
    if (codec.empty() || codec == "copy") return {};
    const bool high = preset == "high";
    const bool small = preset == "small";
    if (audio) {
        if (codec == "flac" || codec == "alac" || codec == "pcm_s16le" ||
            codec == "pcm_s16be")
            return {};
        if (codec == "libvorbis")
            return {"-q:a", high ? "8" : (small ? "3" : "6")};
        return {"-b:a", high ? "256k" : (small ? "96k" : "192k")};
    }
    if (codec == "libx264") {
        if (preset == "lossless")
            return {"-preset", "medium", "-qp", "0", "-pix_fmt", "yuv420p"};
        return {"-preset", "medium", "-crf", high ? "16" : (small ? "28" : "20"),
                "-pix_fmt", "yuv420p"};
    }
    if (codec == "libvpx-vp9")
        return {"-crf", high ? "22" : (small ? "36" : "30"), "-b:v", "0", "-row-mt", "1"};
    if (codec == "mpeg4" || codec == "mjpeg")
        return {"-q:v", high ? "2" : (small ? "7" : "4")};
    return {};
}

BuiltTranscodeCommand build_transcode_command(const std::string& source,
                                              const std::string& destination,
                                              const TranscodeOptions& options) {
    if (!is_known_preset(options.preset))
        throw MediaTranscodeError("unsupported media conversion preset");
    if (!is_known_subtitle_mode(options.subtitle_mode))
        throw MediaTranscodeError("unsupported subtitle conversion mode");
    for (const std::string* name : {&options.video_codec, &options.audio_codec}) {
        if (*name != "auto" && !valid_codec_name(*name))
            throw MediaTranscodeError("codec name is invalid");
    }

    const std::string extension = lowercase_extension(destination);
    const bool known_ext =
        audio_extensions().count(extension) != 0 || video_extensions().count(extension) != 0;
    if (!known_ext)
        throw MediaTranscodeError("unsupported output extension: " + extension);

    JsonValue probe;
    try {
        probe = probe_json(source);
    } catch (const MediaProbeError& exc) {
        throw MediaTranscodeError(std::string("media probe failed: ") + exc.what());
    }

    const std::vector<const JsonValue*> videos =
        collect_streams(probe, "video", true);
    const std::vector<const JsonValue*> audios =
        collect_streams(probe, "audio", false);
    const std::vector<const JsonValue*> subtitles =
        collect_streams(probe, "subtitle", false);

    const bool audio_only = audio_extensions().count(extension) != 0;
    if (videos.empty() && audios.empty())
        throw MediaTranscodeError("source has no playable audio or video stream");
    if (audio_only && audios.empty())
        throw MediaTranscodeError("audio output requires an audio stream");

    const AutomaticCodecs automatic = automatic_codecs_table().at(extension);
    std::string chosen_video;
    if (!audio_only && !videos.empty()) {
        if (options.preset == "remux") chosen_video = "copy";
        else if (options.video_codec == "auto") chosen_video = automatic.video;
        else chosen_video = options.video_codec;
    }
    std::string chosen_audio;
    if (!audios.empty()) {
        if (options.preset == "remux") chosen_audio = "copy";
        else if (options.audio_codec == "auto") chosen_audio = automatic.audio;
        else chosen_audio = options.audio_codec;
    }

    std::string video = chosen_video;
    std::string audio = chosen_audio;
    if (options.preset == "lossless" && options.video_codec == "auto" && !video.empty()) {
        if (extension == ".mkv") video = "ffv1";
        else if (extension == ".mov" || extension == ".mp4" || extension == ".m4v") video = "libx264";
        else if (extension == ".avi") video = "ffv1";
        else throw MediaTranscodeError(
            "lossless video preset requires MKV, MOV, MP4, M4V or AVI");
    }
    if (options.preset == "lossless" && options.audio_codec == "auto" && !audio.empty()) {
        if (extension == ".mkv" || extension == ".mka" || extension == ".flac") audio = "flac";
        else if (extension == ".mov" || extension == ".mp4" || extension == ".m4v" ||
                 extension == ".m4a" || extension == ".alac") audio = "alac";
        else if (extension == ".wav" || extension == ".avi") audio = "pcm_s16le";
        else if (extension == ".aif" || extension == ".aiff") audio = "pcm_s16be";
        else throw MediaTranscodeError(
            "lossless audio preset is incompatible with the target container");
    }

    std::vector<std::string> args = {
        "-nostdin", "-hide_banner", "-v", "error", "-y", "-i", source,
    };

    const std::size_t video_count = options.all_tracks ? videos.size() : 1;
    const std::size_t audio_count =
        (options.all_tracks && multitrack_audio_containers().count(extension))
            ? audios.size() : 1;

    if (!video.empty()) {
        for (std::size_t i = 0; i < video_count && i < videos.size(); ++i)
            args.push_back("-map"), args.push_back("0:" + std::to_string(stream_index(*videos[i])));
    }
    if (!audio.empty()) {
        for (std::size_t i = 0; i < audio_count && i < audios.size(); ++i)
            args.push_back("-map"), args.push_back("0:" + std::to_string(stream_index(*audios[i])));
    }

    std::string subtitle_codec;
    if (!audio_only && !subtitles.empty() && options.subtitle_mode != "drop" &&
        !automatic.subtitle.empty()) {
        const std::size_t subtitle_count = options.all_tracks ? subtitles.size() : 1;
        for (std::size_t i = 0; i < subtitle_count && i < subtitles.size(); ++i)
            args.push_back("-map"), args.push_back("0:" + std::to_string(stream_index(*subtitles[i])));
        subtitle_codec = (options.subtitle_mode == "copy" || options.preset == "remux")
            ? "copy" : automatic.subtitle;
    }

    if (extension == ".mkv" && options.all_tracks) {
        args.push_back("-map"), args.push_back("0:t?"), args.push_back("-c:t"), args.push_back("copy");
    }

    if (options.preserve_metadata) {
        args.push_back("-map_metadata"), args.push_back("0");
        if (!audio_only || extension == ".m4a" || extension == ".mka")
            args.push_back("-map_chapters"), args.push_back("0");
        else
            args.push_back("-map_chapters"), args.push_back("-1");
    } else {
        args.push_back("-map_metadata"), args.push_back("-1");
        args.push_back("-map_chapters"), args.push_back("-1");
    }

    if (!video.empty()) {
        args.push_back("-c:v");
        args.push_back(video);
        const std::vector<std::string> vq = quality_options(video, options.preset);
        args.insert(args.end(), vq.begin(), vq.end());
    } else {
        args.push_back("-vn");
    }

    if (!audio.empty()) {
        args.push_back("-c:a");
        args.push_back(audio);
        const std::vector<std::string> aq = quality_options(audio, options.preset, true);
        args.insert(args.end(), aq.begin(), aq.end());
        if ((extension == ".flv" && audio == "libmp3lame") || audio == "mp2")
            args.push_back("-ar:a"), args.push_back("44100");
    } else {
        args.push_back("-an");
    }

    if (!subtitle_codec.empty())
        args.push_back("-c:s"), args.push_back(subtitle_codec);
    else
        args.push_back("-sn");

    args.push_back("-dn");
    args.push_back("-progress"), args.push_back("pipe:1");
    args.push_back("-nostats");

    if (extension == ".alac") args.push_back("-f"), args.push_back("ipod");

    args.push_back(destination);

    BuiltTranscodeCommand built;
    built.args = std::move(args);
    built.probe = std::move(probe);
    return built;
}

}  // namespace casu::codec
