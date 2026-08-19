// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/media/mediainfo.hpp"

#include "casu/codec/ffprobe.hpp"

#include <exception>
#include <string>

namespace casu::media {

namespace {

std::string json_str(const JsonValue& v, const char* key, const std::string& fallback = {}) {
    const JsonValue* p = v.find(key);
    if (!p || !p->is_string()) return fallback;
    return p->as_string();
}

double json_num(const JsonValue& v, const char* key, double fallback = 0.0) {
    const JsonValue* p = v.find(key);
    if (!p) return fallback;
    if (p->is_number()) return p->as_double();
    if (p->is_string()) {
        const std::string& text = p->as_string();
        try {
            std::size_t consumed = 0;
            const double parsed = std::stod(text, &consumed);
            if (consumed == text.size()) return parsed;
        } catch (const std::exception&) {
        }
    }
    return fallback;
}

long long json_int(const JsonValue& v, const char* key, long long fallback = 0) {
    const double value = json_num(v, key, double(fallback));
    return static_cast<long long>(value);
}

std::map<std::string, std::string> tags_from(const JsonValue& object) {
    std::map<std::string, std::string> out;
    const JsonValue* tags = object.find("tags");
    if (!tags || !tags->is_object()) return out;
    for (const auto& [key, value] : tags->as_object().items)
        if (value.is_string()) out[key] = value.as_string();
    return out;
}

}  // namespace

MediaInfo probe(const std::string& path) {
    JsonValue raw;
    try {
        raw = casu::codec::probe_json(path);
    } catch (const casu::codec::MediaProbeError& exc) {
        throw MediaProbeError(exc.what());
    }
    MediaInfo info;
    info.path = path;
    info.raw = raw;

    if (const JsonValue* format = raw.find("format")) {
        MediaFormatInfo f;
        f.format_name = json_str(*format, "format_name");
        f.format_long_name = json_str(*format, "format_long_name");
        f.duration = json_num(*format, "duration");
        f.size_bytes = json_int(*format, "size");
        f.bit_rate = json_int(*format, "bit_rate");
        f.tags = tags_from(*format);
        info.format = std::move(f);
    }

    if (const JsonValue* streams = raw.find("streams")) {
        if (streams->is_array()) {
            for (const JsonValue& item : streams->as_array().items) {
                MediaStreamInfo s;
                s.index = static_cast<int>(json_int(item, "index", -1));
                s.codec_type = json_str(item, "codec_type");
                s.codec_name = json_str(item, "codec_name");
                s.width = json_int(item, "width");
                s.height = json_int(item, "height");
                s.sample_rate = json_int(item, "sample_rate");
                s.channels = json_int(item, "channels");
                s.time_base = json_str(item, "time_base");
                s.pix_fmt = json_str(item, "pix_fmt");
                s.duration = json_num(item, "duration");
                s.tags = tags_from(item);
                if (const JsonValue* disposition = item.find("disposition")) {
                    if (const JsonValue* pic = disposition->find("attached_pic"))
                        if (pic->is_int() && pic->as_int() != 0) s.attached_pic = true;
                }
                info.streams.push_back(std::move(s));
            }
        }
    }
    return info;
}

bool has_stream(const MediaInfo& info, const std::string& codec_type) {
    return first_playable(info, codec_type) != nullptr;
}

const MediaStreamInfo* first_playable(const MediaInfo& info,
                                      const std::string& codec_type) {
    for (const MediaStreamInfo& stream : info.streams) {
        if (stream.codec_type != codec_type) continue;
        if (codec_type == "video" && stream.attached_pic) continue;
        return &stream;
    }
    return nullptr;
}

double duration_s(const MediaInfo& info) {
    double best = info.format.duration;
    for (const MediaStreamInfo& stream : info.streams)
        if (stream.duration > best) best = stream.duration;
    return best;
}

}  // namespace casu::media
