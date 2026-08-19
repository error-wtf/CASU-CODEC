// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/manifest.hpp"
#include <cmath>
#include <cstring>
#include <set>

namespace casu {

namespace {

bool is_hex64(const std::string& s) {
    if (s.size() != 64) return false;
    for (char c : s) {
        bool hex = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
        if (!hex) return false;
    }
    return true;
}

bool supported_version(const std::string& v) {
    static const char* supported[] = {
        "1.0.0", "1.0.1", "1.0.2", "1.0.3", "1.0.4", "1.0.5", "1.0.6",
        "2.0.0", "3.0.0",
        "1.0.0rc1", "1.0.0rc2", "1.0.0rc3", "1.0.0rc4", "1.0.0rc5",
        "1.0.0rc6", "1.0.0rc7", "1.0.0rc8", "1.0.0rc9",
    };
    for (const char* s : supported) if (v == s) return true;
    return false;
}

double to_double(const JsonValue* v, bool* ok) {
    *ok = v && v->is_number();
    return *ok ? v->as_double() : 0.0;
}

// basename check: no path traversal, no backslash, not "." or "..".
bool basename_ok(const std::string& name) {
    if (name.empty() || name.size() > 4096) return false;
    if (name.find('\\') != std::string::npos) return false;
    if (name.find('/') != std::string::npos) return false;
    if (name == "." || name == "..") return false;
    return true;
}

}  // namespace

std::vector<std::string> validate_manifest(const JsonValue& manifest,
                                           const ManifestLimits& limits) {
    std::vector<std::string> errors;
    if (!manifest.is_object()) {
        errors.emplace_back("manifest must be an object");
        return errors;
    }
    const auto& root = manifest.as_object();

    const JsonValue* identity_v = nullptr;
    auto it = root.items.find("casu");
    if (it != root.items.end()) identity_v = &it->second;
    const JsonValue* format_v = nullptr;
    it = root.items.find("format");
    if (it != root.items.end()) format_v = &it->second;

    if (identity_v && !identity_v->is_object()) {
        errors.emplace_back("casu must be an object");
        identity_v = nullptr;
    }
    if (format_v && !format_v->is_object()) {
        errors.emplace_back("format must be an object");
        format_v = nullptr;
    }

    if (format_v) {
        const JsonValue* magic = format_v->find("magic");
        if (magic && magic->is_string() && magic->as_string() != "MPCASU\\0")
            errors.emplace_back("format.magic must be MPCASU\\0 when present");
        const JsonValue* schema = format_v->find("schema");
        if (schema && !(schema->is_string() && schema->as_string() == "0.2"))
            errors.emplace_back("format.schema is not supported");
    }

    if (identity_v) {
        const JsonValue* name = identity_v->find("name");
        if (!name || !name->is_string() || name->as_string() != "CASU")
            errors.emplace_back("casu.name must be CASU");
        const JsonValue* ext = identity_v->find("container_extension");
        if (!ext || !ext->is_string() || ext->as_string() != ".casu")
            errors.emplace_back("casu.container_extension must be .casu");
        const JsonValue* version = identity_v->find("version");
        if (!version || !version->is_string() || !supported_version(version->as_string()))
            errors.emplace_back("casu.version must be a supported CASU version");
        const JsonValue* mode = identity_v->find("analysis_mode");
        if (mode && !mode->is_null()) {
            if (!mode->is_string() ||
                (mode->as_string() != "strict" && mode->as_string() != "visually_lossless" &&
                 mode->as_string() != "adaptive"))
                errors.emplace_back("casu.analysis_mode is not a supported CASU mode");
        }
    }

    const JsonValue* source_v = nullptr;
    it = root.items.find("source");
    if (it != root.items.end()) source_v = &it->second;
    if (!source_v || !source_v->is_object()) {
        errors.emplace_back("source must be an object");
        source_v = nullptr;
    }

    if (source_v) {
        const JsonValue* filename = source_v->find("filename");
        if (!filename || !filename->is_string() || filename->as_string().empty())
            errors.emplace_back("source.filename must be a non-empty string");
        else if (filename->as_string().size() > limits.max_text_length ||
                 !basename_ok(filename->as_string()))
            errors.emplace_back("source.filename must be a bounded basename without path traversal");
        const JsonValue* path = source_v->find("path");
        if (path && !path->is_null()) {
            if (!path->is_string() || path->as_string().empty() ||
                path->as_string().size() > limits.max_text_length)
                errors.emplace_back("source.path must be a bounded string when present");
            else if (filename && filename->is_string()) {
                std::string p = path->as_string();
                std::size_t slash = p.find_last_of("/\\");
                std::string base = slash == std::string::npos ? p : p.substr(slash + 1);
                if (base != filename->as_string())
                    errors.emplace_back("source.path basename must match source.filename");
            }
        }
        if (!source_v->find("duration_s"))
            errors.emplace_back("source.duration_s is required");
        bool ok = false;
        double duration = to_double(source_v->find("duration_s"), &ok);
        if (!ok) errors.emplace_back("source.duration_s must be numeric");
        else if (!std::isfinite(duration) || duration < 0)
            errors.emplace_back("source.duration_s must be finite and non-negative");

        const JsonValue* size = source_v->find("size_bytes");
        if (size && !size->is_null()) {
            bool size_ok = false;
            double sz = to_double(size, &size_ok);
            if (!size_ok || !std::isfinite(sz) || sz < 0)
                errors.emplace_back("source.size_bytes must be finite and non-negative");
        }
        const JsonValue* sha = source_v->find("sha256");
        if (sha && !sha->is_null()) {
            if (!sha->is_string() || !is_hex64(sha->as_string()))
                errors.emplace_back("source.sha256 must be a 64-character hex digest when present");
        }

        // duration is used by the segment/seek checks below.
        const JsonValue* streams_v = nullptr;
        it = root.items.find("streams");
        if (it != root.items.end()) streams_v = &it->second;
        if (!streams_v || !streams_v->is_array())
            errors.emplace_back("streams must be an array");
        else {
            const auto& streams = streams_v->as_array().items;
            if (streams.size() > limits.max_streams)
                errors.emplace_back("streams exceeds safety limit of " + std::to_string(limits.max_streams));
            for (std::size_t i = 0; i < streams.size() && i < limits.max_streams; ++i) {
                const JsonValue& stream = streams[i];
                if (!stream.is_object()) {
                    errors.emplace_back("streams[" + std::to_string(i) + "] must be an object");
                    continue;
                }
                const JsonValue* codec_type = stream.find("codec_type");
                if (codec_type && codec_type->is_string()) {
                    const std::string& ct = codec_type->as_string();
                    if (ct != "video" && ct != "audio" && ct != "subtitle" &&
                        ct != "attachment" && ct != "data")
                        errors.emplace_back("streams[" + std::to_string(i) + "].codec_type is unsupported");
                }
                const JsonValue* codec_name = stream.find("codec_name");
                if (codec_name && !codec_name->is_null()) {
                    if (!codec_name->is_string() ||
                        codec_name->as_string().size() > limits.max_text_length)
                        errors.emplace_back("streams[" + std::to_string(i) + "].codec_name is invalid");
                }
            }
        }

        const JsonValue* metadata_v = nullptr;
        it = root.items.find("metadata");
        if (it != root.items.end()) metadata_v = &it->second;
        if (metadata_v && !metadata_v->is_null()) {
            if (!metadata_v->is_object())
                errors.emplace_back("metadata must be an object");
            else if (metadata_v->as_object().items.size() > limits.max_metadata_keys)
                errors.emplace_back("metadata exceeds safety limit of " +
                                    std::to_string(limits.max_metadata_keys) + " keys");
            else {
                for (const auto& [k, v] : metadata_v->as_object().items) {
                    if (k.size() > limits.max_text_length)
                        errors.emplace_back("metadata keys must be bounded strings");
                    if (!v.is_string() && !v.is_int() && !v.is_number() && !v.is_bool() && !v.is_null())
                        errors.emplace_back("metadata values must be scalar values");
                }
            }
        }

        for (const char* media_key : {"video", "audio"}) {
            const JsonValue* section = nullptr;
            it = root.items.find(media_key);
            if (it != root.items.end()) section = &it->second;
            if (section && !section->is_object()) {
                errors.emplace_back(std::string(media_key) + " must be an object");
                continue;
            }
            if (!section) continue;
            const JsonValue* segments = section->find("segments");
            if (!segments || !segments->is_array()) {
                errors.emplace_back(std::string(media_key) + ".segments must be an array");
                continue;
            }
            const auto& segs = segments->as_array().items;
            if (segs.size() > limits.max_segments_per_stream) {
                errors.emplace_back(std::string(media_key) + ".segments exceeds safety limit of " +
                                    std::to_string(limits.max_segments_per_stream));
                continue;
            }
            double previous_end = 0.0;
            std::set<std::string> segment_ids;
            for (std::size_t i = 0; i < segs.size(); ++i) {
                const JsonValue& seg = segs[i];
                if (!seg.is_object()) {
                    errors.emplace_back(std::string(media_key) + ".segments[" + std::to_string(i) + "] must be an object");
                    continue;
                }
                bool s_ok = false, e_ok = false;
                double start = to_double(seg.find("start_s"), &s_ok);
                double end = to_double(seg.find("end_s"), &e_ok);
                if (!s_ok || !e_ok)
                    errors.emplace_back(std::string(media_key) + ".segments[" + std::to_string(i) + "] lacks numeric start/end");
                else {
                    if (!std::isfinite(start) || !std::isfinite(end) || start < 0 || end <= start ||
                        end > duration + 0.5)
                        errors.emplace_back(std::string(media_key) + ".segments[" + std::to_string(i) + "] is outside source duration");
                    if (start < previous_end - 1e-6)
                        errors.emplace_back(std::string(media_key) + ".segments[" + std::to_string(i) + "] overlaps the preceding segment");
                    previous_end = previous_end > end ? previous_end : end;
                }
                const JsonValue* dur = seg.find("duration_s");
                if (dur) {
                    bool d_ok = false;
                    double d = to_double(dur, &d_ok);
                    if (!d_ok || !std::isfinite(d) || d < 0)
                        errors.emplace_back(std::string(media_key) + ".segments[" + std::to_string(i) + "].duration_s must be finite and non-negative");
                    else if (s_ok && e_ok && std::fabs(d - (end - start)) > 1e-5)
                        errors.emplace_back(std::string(media_key) + ".segments[" + std::to_string(i) + "].duration_s must equal end_s-start_s");
                }
                const JsonValue* state = seg.find("state");
                if (!state || !state->is_string() || state->as_string().empty() ||
                    state->as_string().size() > limits.max_text_length)
                    errors.emplace_back(std::string(media_key) + ".segments[" + std::to_string(i) + "].state must be a non-empty bounded string");
                const JsonValue* segment_id = seg.find("segment_id");
                if (segment_id && !segment_id->is_null()) {
                    if (!segment_id->is_string() || segment_id->as_string().empty() ||
                        segment_id->as_string().size() > limits.max_text_length)
                        errors.emplace_back(std::string(media_key) + ".segments[" + std::to_string(i) + "].segment_id must be a bounded non-empty string");
                    else if (!segment_ids.insert(segment_id->as_string()).second)
                        errors.emplace_back(std::string(media_key) + ".segments[" + std::to_string(i) + "].segment_id must be unique");
                }
                const JsonValue* lifecycle = seg.find("lifecycle");
                std::string lc = lifecycle && lifecycle->is_string() ? lifecycle->as_string() : "UPDATE";
                static const char* valid_lc[] = {"CREATE", "UPDATE", "HOLD", "MOVE", "REPLACE", "INVALIDATE", "RELEASE"};
                bool lc_ok = false;
                for (const char* v : valid_lc) if (lc == v) lc_ok = true;
                if (!lc_ok)
                    errors.emplace_back(std::string(media_key) + ".segments[" + std::to_string(i) + "].lifecycle is unsupported");
                const JsonValue* priority = seg.find("priority");
                if (priority && !priority->is_null()) {
                    if (!priority->is_int() || std::llabs(priority->as_int()) > limits.max_segment_priority)
                        errors.emplace_back(std::string(media_key) + ".segments[" + std::to_string(i) + "].priority must be a bounded integer");
                }
                const JsonValue* ref = seg.find("reference_state");
                if (ref && !ref->is_null()) {
                    if (!ref->is_string() || ref->as_string().size() > limits.max_text_length)
                        errors.emplace_back(std::string(media_key) + ".segments[" + std::to_string(i) + "].reference_state is invalid");
                }
                const JsonValue* region = seg.find("region");
                if (region && !region->is_null()) {
                    if (!region->is_object())
                        errors.emplace_back(std::string(media_key) + ".segments[" + std::to_string(i) + "].region must be an object");
                    else {
                        for (const char* rk : {"x", "y", "w", "h"}) {
                            const JsonValue* rv = region->find(rk);
                            if (rv && (!rv->is_int() || rv->as_int() < 0))
                                errors.emplace_back(std::string(media_key) + ".segments[" + std::to_string(i) + "].region." + rk + " must be a non-negative integer");
                        }
                    }
                }
                for (const char* tk : {"valid_until_s", "deadline_s"}) {
                    const JsonValue* tv = seg.find(tk);
                    if (tv) {
                        bool t_ok = false;
                        double t = to_double(tv, &t_ok);
                        if (!t_ok || !std::isfinite(t) || t < start)
                            errors.emplace_back(std::string(media_key) + ".segments[" + std::to_string(i) + "]." + tk + " must be finite and >= start_s");
                        else if (s_ok && e_ok && std::fabs(t - end) > 1e-5)
                            errors.emplace_back(std::string(media_key) + ".segments[" + std::to_string(i) + "]." + tk + " must equal end_s");
                    }
                }
            }
        }

        const JsonValue* seek = nullptr;
        it = root.items.find("seek_index");
        if (it != root.items.end()) seek = &it->second;
        if (seek && !seek->is_null()) {
            if (!seek->is_object())
                errors.emplace_back("seek_index must be an object");
            else {
                const JsonValue* nks = seek->find("native_key_states");
                if (nks && !nks->is_bool())
                    errors.emplace_back("seek_index.native_key_states must be boolean");
                const JsonValue* entries = seek->find("entries");
                if (!entries || !entries->is_array())
                    errors.emplace_back("seek_index.entries must be an array");
                else if (entries->as_array().items.size() > limits.max_seek_entries)
                    errors.emplace_back("seek_index.entries exceeds safety limit of " +
                                        std::to_string(limits.max_seek_entries));
                else {
                    double previous_ts = -1.0;
                    const auto& arr = entries->as_array().items;
                    for (std::size_t i = 0; i < arr.size(); ++i) {
                        const JsonValue& entry = arr[i];
                        if (!entry.is_object()) {
                            errors.emplace_back("seek_index.entries[" + std::to_string(i) + "] must be an object");
                            continue;
                        }
                        bool t_ok = false;
                        double ts = to_double(entry.find("timestamp_s"), &t_ok);
                        if (!t_ok)
                            errors.emplace_back("seek_index.entries[" + std::to_string(i) + "].timestamp_s must be numeric");
                        else {
                            if (!std::isfinite(ts) || ts < 0 || ts > duration + 0.5)
                                errors.emplace_back("seek_index.entries[" + std::to_string(i) + "].timestamp_s is outside source duration");
                            if (ts < previous_ts - 1e-6)
                                errors.emplace_back("seek_index.entries must be sorted by timestamp_s");
                            previous_ts = previous_ts > ts ? previous_ts : ts;
                        }
                        const JsonValue* stream = entry.find("stream");
                        if (!stream || !stream->is_string() ||
                            (stream->as_string() != "video" && stream->as_string() != "audio"))
                            errors.emplace_back("seek_index.entries[" + std::to_string(i) + "].stream is unsupported");
                        const JsonValue* segid = entry.find("segment_id");
                        if (segid && !segid->is_null() &&
                            (!segid->is_string() || segid->as_string().empty() ||
                             segid->as_string().size() > limits.max_text_length))
                            errors.emplace_back("seek_index.entries[" + std::to_string(i) + "].segment_id is invalid");
                    }
                }
            }
        }

        const JsonValue* integrity_v = nullptr;
        it = root.items.find("integrity");
        if (it != root.items.end()) integrity_v = &it->second;
        if (!integrity_v || !integrity_v->is_object()) {
            errors.emplace_back("integrity must be an object");
            integrity_v = nullptr;
        }
        if (integrity_v) {
            const JsonValue* source_of_truth = integrity_v->find("timestamps_are_source_of_truth");
            if (!source_of_truth || !source_of_truth->is_bool() || !source_of_truth->as_bool())
                errors.emplace_back("integrity.timestamps_are_source_of_truth must be true");
        }
    }
    return errors;
}

std::vector<std::string> parse_and_validate_manifest(const std::string& json_text) {
    JsonValue manifest = parse_json(json_text);
    return validate_manifest(manifest);
}

}  // namespace casu
