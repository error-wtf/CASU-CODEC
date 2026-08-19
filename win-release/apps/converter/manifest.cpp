// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "manifest.hpp"

#include "casu/formats.hpp"
#include "casu/manifest.hpp"
#include "casu/media/mediainfo.hpp"
#include "casu/sha256.hpp"

#include <filesystem>
#include <string>
#include <vector>

namespace casu::conv {

using casu::CasuError;
using casu::JsonValue;

namespace {

JsonValue json_null() { return JsonValue(std::nullptr_t{}); }

std::string sha256_hex(const std::string& path) {
    const std::string digest = casu::sha256_file(path);
    if (digest.empty()) throw CasuError("could not read file for SHA-256: " + path);
    return digest;
}

JsonValue stream_entry(const JsonValue& stream) {
    casu::JsonObject entry;
    static const char* keys[] = {"index", "codec_type", "codec_name", "width",
                                 "height", "sample_rate", "time_base"};
    for (const char* key : keys) {
        const JsonValue* value = stream.find(key);
        if (value && !value->is_null()) entry.items[key] = *value;
        else entry.items[key] = json_null();
    }
    return JsonValue(std::make_shared<casu::JsonObject>(std::move(entry)));
}

JsonValue segment_json(const std::string& type, double start, double end) {
    casu::JsonObject seg;
    seg.items["start_s"] = JsonValue(start);
    seg.items["end_s"] = JsonValue(end);
    seg.items["duration_s"] = JsonValue(end - start);
    seg.items["state"] = JsonValue(std::string("active"));
    seg.items["lifecycle"] = JsonValue(std::string("CREATE"));
    seg.items["segment_id"] = JsonValue(type + "-000000");
    seg.items["priority"] = JsonValue(int64_t(0));
    seg.items["change_type"] = JsonValue(std::string("initial_state"));
    seg.items["deadline_s"] = JsonValue(end);
    seg.items["valid_until_s"] = JsonValue(end);
    return JsonValue(std::make_shared<casu::JsonObject>(std::move(seg)));
}

JsonValue segments_section(const std::vector<const casu::media::MediaStreamInfo*>& streams,
                           double duration) {
    casu::JsonObject section;
    if (duration > 0) {
        auto holder = std::make_shared<casu::JsonArray>();
        for (std::size_t i = 0; i < streams.size(); ++i)
            holder->items.push_back(segment_json(streams[i]->codec_type, 0.0, duration));
        section.items["segments"] = JsonValue(std::move(holder));
    } else {
        section.items["segments"] = JsonValue(std::make_shared<casu::JsonArray>());
    }
    return JsonValue(std::make_shared<casu::JsonObject>(std::move(section)));
}

}  // namespace

JsonValue build_casu_manifest(const std::string& source, const std::string& mode) {
    casu::media::MediaInfo info;
    try {
        info = casu::media::probe(source);
    } catch (const casu::media::MediaProbeError& exc) {
        throw CasuError(std::string("media probe failed: ") + exc.what());
    }

    std::vector<const casu::media::MediaStreamInfo*> video_streams;
    std::vector<const casu::media::MediaStreamInfo*> audio_streams;
    for (const casu::media::MediaStreamInfo& stream : info.streams) {
        if (stream.codec_type == "video" && stream.attached_pic) continue;
        if (stream.codec_type == "video") video_streams.push_back(&stream);
        else if (stream.codec_type == "audio") audio_streams.push_back(&stream);
    }
    if (video_streams.empty() && audio_streams.empty())
        throw CasuError("input contains no playable audio or video stream");

    std::error_code ec;
    std::filesystem::path abs_source = std::filesystem::absolute(source, ec);
    const std::string abs_str = ec ? source : abs_source.lexically_normal().string();
    const long long size_bytes =
        std::filesystem::exists(abs_source, ec)
            ? (long long)std::filesystem::file_size(abs_source, ec)
            : 0;
    const std::string digest = sha256_hex(source);
    const double duration = casu::media::duration_s(info);

    casu::JsonObject casu_identity;
    casu_identity.items["name"] = JsonValue(std::string("CASU"));
    casu_identity.items["acronym"] = JsonValue(std::string("Codec for All Segmented Units"));
    casu_identity.items["short_name"] = JsonValue(std::string("CASU"));
    casu_identity.items["container_extension"] = JsonValue(std::string(".casu"));
    casu_identity.items["version"] = JsonValue(std::string("3.0.0"));
    casu_identity.items["analysis_mode"] = JsonValue(mode);
    casu_identity.items["compatibility"] =
        JsonValue(std::string("legacy media remains canonical; sidecar is optional"));

    casu::JsonObject format;
    format.items["magic"] = JsonValue(std::string("MPCASU\\0"));
    format.items["kind"] = JsonValue(std::string("CASU sidecar manifest"));
    format.items["schema"] = JsonValue(std::string("0.2"));

    casu::JsonObject source_obj;
    source_obj.items["filename"] = JsonValue(std::filesystem::path(abs_str).filename().string());
    source_obj.items["path"] = JsonValue(abs_str);
    source_obj.items["size_bytes"] = JsonValue((int64_t)size_bytes);
    source_obj.items["sha256"] = JsonValue(digest);
    const JsonValue* format_name = info.raw.find("format");
    if (format_name && format_name->find("format_name"))
        source_obj.items["format_name"] = *format_name->find("format_name");
    source_obj.items["duration_s"] = JsonValue(duration);

    auto streams = std::make_shared<casu::JsonArray>();
    if (const JsonValue* raw_streams = info.raw.find("streams"))
        if (raw_streams->is_array())
            for (const JsonValue& stream : raw_streams->as_array().items)
                streams->items.push_back(stream_entry(stream));

    casu::JsonObject seek_index;
    seek_index.items["method"] = JsonValue(std::string("deterministic segment-boundary index"));
    auto seek_entries = std::make_shared<casu::JsonArray>();
    if (duration > 0) {
        for (const auto* stream : video_streams) {
            casu::JsonObject entry;
            entry.items["timestamp_s"] = JsonValue(0.0);
            entry.items["stream"] = JsonValue(std::string("video"));
            entry.items["segment_id"] = JsonValue(std::string("video-000000"));
            entry.items["state"] = JsonValue(std::string("active"));
            seek_entries->items.push_back(JsonValue(std::make_shared<casu::JsonObject>(std::move(entry))));
        }
        for (const auto* stream : audio_streams) {
            casu::JsonObject entry;
            entry.items["timestamp_s"] = JsonValue(0.0);
            entry.items["stream"] = JsonValue(std::string("audio"));
            entry.items["segment_id"] = JsonValue(std::string("audio-000000"));
            entry.items["state"] = JsonValue(std::string("active"));
            seek_entries->items.push_back(JsonValue(std::make_shared<casu::JsonObject>(std::move(entry))));
        }
    }
    seek_index.items["entries"] = JsonValue(std::move(seek_entries));
    seek_index.items["native_key_states"] = JsonValue(false);
    seek_index.items["note"] = JsonValue(std::string(
        "sidecar navigation hints only; decoder keyframe seeking remains backend-owned"));

    casu::JsonObject integrity;
    integrity.items["timestamps_are_source_of_truth"] = JsonValue(true);
    integrity.items["optimization_is_hint_only"] = JsonValue(true);
    integrity.items["mode_is_not_quality_proof"] = JsonValue(true);
    integrity.items["fallback"] =
        JsonValue(std::string("full-frame/full-fidelity legacy playback"));

    casu::JsonObject root;
    root.items["format"] = JsonValue(std::make_shared<casu::JsonObject>(std::move(format)));
    root.items["casu"] = JsonValue(std::make_shared<casu::JsonObject>(std::move(casu_identity)));
    root.items["source"] = JsonValue(std::make_shared<casu::JsonObject>(std::move(source_obj)));
    root.items["streams"] = JsonValue(std::move(streams));
    if (video_streams.empty())
        root.items["video"] = segments_section({}, duration);
    else
        root.items["video"] = segments_section(video_streams, duration);
    if (audio_streams.empty())
        root.items["audio"] = segments_section({}, duration);
    else
        root.items["audio"] = segments_section(audio_streams, duration);
    root.items["seek_index"] = JsonValue(std::make_shared<casu::JsonObject>(std::move(seek_index)));
    root.items["integrity"] = JsonValue(std::make_shared<casu::JsonObject>(std::move(integrity)));

    JsonValue manifest = JsonValue(std::make_shared<casu::JsonObject>(std::move(root)));
    const std::vector<std::string> errors = casu::validate_manifest(manifest);
    if (!errors.empty())
        throw CasuError("internal manifest validation failed: " + errors[0]);
    return manifest;
}

}  // namespace casu::conv