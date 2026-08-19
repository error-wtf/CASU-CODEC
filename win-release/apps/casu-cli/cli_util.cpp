// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "cli_util.hpp"

#include "casu/manifest.hpp"
#include "casu/media/mediainfo.hpp"
#include "casu/sha256.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <stdexcept>

namespace casu::cli {

using casu::CasuError;
using casu::JsonValue;

namespace {

std::string lowercase(const std::string& value) {
    std::string out = value;
    for (char& c : out)
        if (c >= 'A' && c <= 'Z') c = char(c + ('a' - 'A'));
    return out;
}

std::string sha256_hex(const std::string& path) {
    const std::string digest = casu::sha256_file(path);
    if (digest.empty()) throw CasuError("could not read file for SHA-256: " + path);
    return digest;
}

// --- JSON string escaping (matches casu json.cpp escape_string) -----------
std::string escape_string(const std::string& s) {
    std::string out;
    out.reserve(s.size() + 2);
    out.push_back('"');
    for (unsigned char c : s) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (c < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof(buf), "\\u%04x", c);
                    out += buf;
                } else {
                    out.push_back(char(c));
                }
        }
    }
    out.push_back('"');
    return out;
}

// --- number formatting (matches casu json.cpp / Python json repr) ---------
std::string number_repr(const JsonValue& v) {
    if (v.is_int()) return std::to_string(v.as_int());
    const double d = v.as_double();
    if (!std::isfinite(d)) return "null";
    char buf[40];
    auto res = std::to_chars(buf, buf + sizeof(buf), d);
    std::string s(buf, res.ptr);
    if (s.find('.') == std::string::npos && s.find('e') == std::string::npos &&
        s.find('E') == std::string::npos)
        s += ".0";
    return s;
}

void indent(int depth, std::string& out) { out.append(std::size_t(depth) * 2, ' '); }

void pretty(const JsonValue& v, int depth, std::string& out) {
    switch (v.kind()) {
        case JsonValue::Kind::Null: out += "null"; break;
        case JsonValue::Kind::Bool: out += v.as_bool() ? "true" : "false"; break;
        case JsonValue::Kind::Int:
        case JsonValue::Kind::Double: out += number_repr(v); break;
        case JsonValue::Kind::String: out += escape_string(v.as_string()); break;
        case JsonValue::Kind::Array: {
            const auto& items = v.as_array().items;
            if (items.empty()) { out += "[]"; break; }
            out += "[\n";
            for (std::size_t i = 0; i < items.size(); ++i) {
                indent(depth + 1, out);
                pretty(items[i], depth + 1, out);
                if (i + 1 < items.size()) out += ",";
                out += "\n";
            }
            indent(depth, out);
            out += "]";
            break;
        }
        case JsonValue::Kind::Object: {
            const auto& items = v.as_object().items;
            if (items.empty()) { out += "{}"; break; }
            out += "{\n";
            bool first = true;
            for (const auto& [key, value] : items) {
                if (!first) out += ",\n";
                first = false;
                indent(depth + 1, out);
                out += escape_string(key);
                out += ": ";
                pretty(value, depth + 1, out);
            }
            out += "\n";
            indent(depth, out);
            out += "}";
            break;
        }
    }
}

JsonValue json_null() { return JsonValue(std::nullptr_t{}); }

JsonValue json_string_or_null(const char* value) {
    return value ? JsonValue(std::string(value)) : json_null();
}

// --- manifest building helpers --------------------------------------------
JsonValue stream_entry(const JsonValue& stream) {
    JsonObject entry;
    static const char* keys[] = {"index", "codec_type", "codec_name", "width",
                                 "height", "sample_rate", "time_base"};
    for (const char* key : keys) {
        const JsonValue* value = stream.find(key);
        if (value && !value->is_null()) entry.items[key] = *value;
        else entry.items[key] = json_null();
    }
    return JsonValue(std::make_shared<JsonObject>(std::move(entry)));
}

JsonValue segment_json(const std::string& type, double start, double end) {
    JsonObject seg;
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
    return JsonValue(std::make_shared<JsonObject>(std::move(seg)));
}

JsonValue segments_section(const std::vector<const casu::media::MediaStreamInfo*>& streams,
                           double duration) {
    JsonObject section;
    if (duration > 0) {
        auto holder = std::make_shared<JsonArray>();
        for (std::size_t i = 0; i < streams.size(); ++i)
            holder->items.push_back(segment_json(streams[i]->codec_type, 0.0, duration));
        section.items["segments"] = JsonValue(std::move(holder));
    } else {
        section.items["segments"] = JsonValue(std::make_shared<JsonArray>());
    }
    return JsonValue(std::make_shared<JsonObject>(std::move(section)));
}

}  // namespace

// ---------------------------------------------------------------------------
long long Args::get_long(const std::string& name, long long fallback) const {
    auto it = options.find(name);
    if (it == options.end() || it->second.empty()) return fallback;
    try {
        std::size_t consumed = 0;
        const long long value = std::stoll(it->second, &consumed);
        if (consumed == it->second.size()) return value;
    } catch (const std::exception&) {
    }
    return fallback;
}

double Args::get_double(const std::string& name, double fallback) const {
    auto it = options.find(name);
    if (it == options.end() || it->second.empty()) return fallback;
    try {
        std::size_t consumed = 0;
        const double value = std::stod(it->second, &consumed);
        if (consumed == it->second.size()) return value;
    } catch (const std::exception&) {
    }
    return fallback;
}

Args parse_args(const std::vector<std::string>& tokens) {
    Args args;
    for (std::size_t i = 0; i < tokens.size(); ++i) {
        const std::string& token = tokens[i];
        if (token.size() >= 2 && token[0] == '-' && token[1] == '-') {
            std::size_t eq = token.find('=');
            std::string name = eq == std::string::npos ? token : token.substr(0, eq);
            if (eq != std::string::npos) {
                args.options[name] = token.substr(eq + 1);
            } else if (i + 1 < tokens.size() && !tokens[i + 1].empty() &&
                       tokens[i + 1][0] != '-') {
                args.options[name] = tokens[++i];
            } else {
                args.options[name] = "";
            }
        } else if (token.size() == 2 && token[0] == '-') {
            // Short option "-o <value>".
            if (i + 1 < tokens.size() && !tokens[i + 1].empty() &&
                tokens[i + 1][0] != '-')
                args.options[token] = tokens[++i];
            else
                args.options[token] = "";
        } else {
            args.positional.push_back(token);
        }
    }
    return args;
}

// ---------------------------------------------------------------------------
std::string pretty_json(const JsonValue& value) {
    std::string out;
    pretty(value, 0, out);
    return out;
}

std::string compact_json(const JsonValue& value) {
    return casu::dump_json(value) + "\n";
}

void atomic_write_text(const std::string& path, const std::string& payload) {
    std::filesystem::path target = std::filesystem::absolute(path);
    std::error_code ec;
    std::filesystem::create_directories(target.parent_path(), ec);
    const std::filesystem::path temporary =
        target.parent_path() / ("." + target.filename().string() + ".tmp");
    {
        FILE* f = std::fopen(temporary.string().c_str(), "wb");
        if (!f) throw CasuError("could not create output file: " + path);
        const bool wrote = std::fwrite(payload.data(), 1, payload.size(), f) == payload.size();
        std::fflush(f);
        std::fclose(f);
        if (!wrote) {
            std::filesystem::remove(temporary, ec);
            throw CasuError("could not write output file: " + path);
        }
    }
    std::filesystem::remove(target, ec);
    std::filesystem::rename(temporary, target, ec);
    if (ec) {
        std::filesystem::remove(temporary, ec);
        throw CasuError("could not finalize output file: " + path);
    }
}

std::string abs_path(const std::string& path) {
    std::error_code ec;
    return std::filesystem::absolute(path, ec).lexically_normal().string();
}

std::string basename(const std::string& path) {
    return std::filesystem::path(path).filename().string();
}

bool read_magic(const std::string& path, std::string& magic) {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) return false;
    char buf[8];
    const std::size_t got = std::fread(buf, 1, 8, f);
    std::fclose(f);
    if (got < 8) return false;
    magic.assign(buf, 8);
    return true;
}

std::string kind_name(casu::CasuKind kind) {
    switch (kind) {
        case casu::CasuKind::Casunat1: return "casunat1";
        case casu::CasuKind::Casunat2: return "casunat2";
        case casu::CasuKind::Mp5: return "mp5";
        case casu::CasuKind::Sidecar: return "sidecar";
        default: return "none";
    }
}

// ---------------------------------------------------------------------------
// Batch planning
// ---------------------------------------------------------------------------
namespace {

constexpr long long MAX_REPORT_RESULTS = 10000;

struct Entry {
    std::string source;
    std::string relative;
};

bool is_casu_file(const std::string& source) {
    try {
        return casu::detect_casu_kind(source) != casu::CasuKind::None;
    } catch (...) {
        return false;
    }
}

}  // namespace

std::vector<std::pair<std::string, std::string>> plan_inputs(
    const std::vector<std::string>& items, bool casu_only) {
    std::vector<Entry> planned;
    // Paths keyed by absolute source to de-duplicate.
    std::vector<std::string> seen;
    auto already_seen = [&](const std::string& p) {
        for (const std::string& s : seen) if (s == p) return true;
        return false;
    };

    for (const std::string& item : items) {
        std::error_code ec;
        std::filesystem::path candidate = std::filesystem::absolute(item, ec);
        if (ec || !std::filesystem::exists(candidate, ec))
            throw CasuError("input media does not exist: " + item);
        if (std::filesystem::is_directory(candidate, ec)) {
            std::vector<std::string> found;
            for (const auto& dir_entry :
                 std::filesystem::recursive_directory_iterator(
                     candidate, std::filesystem::directory_options::skip_permission_denied,
                     ec)) {
                if (ec) break;
                if (!dir_entry.is_regular_file()) continue;
                std::string source = dir_entry.path().string();
                if (already_seen(source)) continue;
                if (casu_only != is_casu_file(source)) continue;
                std::string relative = dir_entry.path().lexically_relative(candidate).string();
                if (relative.empty()) continue;
                seen.push_back(source);
                found.push_back(relative);
                if (planned.size() + found.size() > MAX_REPORT_RESULTS)
                    throw CasuError("batch exceeds " + std::to_string(MAX_REPORT_RESULTS) +
                                    " input files");
            }
            std::sort(found.begin(), found.end());
            for (const std::string& relative : found)
                planned.push_back({(candidate / relative).string(), relative});
        } else {
            std::string source = candidate.string();
            if (casu_only != is_casu_file(source))
                throw CasuError(casu_only
                                    ? "export input is not a valid CASU file: " + item
                                    : "conversion input is already CASU content: " + item);
            if (!already_seen(source)) {
                seen.push_back(source);
                planned.push_back({source, std::filesystem::path(source).filename().string()});
                if (planned.size() > MAX_REPORT_RESULTS)
                    throw CasuError("batch exceeds " + std::to_string(MAX_REPORT_RESULTS) +
                                    " input files");
            }
        }
    }
    std::vector<std::pair<std::string, std::string>> out;
    out.reserve(planned.size());
    for (const Entry& entry : planned) out.emplace_back(entry.source, entry.relative);
    return out;
}

std::vector<std::string> plan_casu_targets(
    const std::vector<std::pair<std::string, std::string>>& planned,
    const std::string& output_dir) {
    std::vector<std::string> targets;
    std::map<std::string, std::vector<std::size_t>> groups;
    for (std::size_t i = 0; i < planned.size(); ++i) {
        std::filesystem::path relative = std::filesystem::path(planned[i].second);
        relative.replace_extension(".casu");
        std::string target = abs_path((std::filesystem::path(output_dir) / relative).string());
        targets.push_back(target);
        groups[target].push_back(i);
    }
    for (const auto& [target, indexes] : groups) {
        if (indexes.size() < 2) continue;
        for (std::size_t index : indexes) {
            std::string source = planned[index].first;
            std::string digest = casu::Sha256::oneshot(source).substr(0, 8);
            std::filesystem::path path(target);
            std::string name = path.stem().string() + "-" + digest + ".casu";
            targets[index] = (path.parent_path() / name).string();
        }
    }
    return targets;
}

std::vector<std::string> plan_format_targets(
    const std::vector<std::pair<std::string, std::string>>& planned,
    const std::string& output_dir, const std::string& extension) {
    std::string normalized = lowercase(extension);
    if (!normalized.empty() && normalized[0] == '.') normalized.erase(normalized.begin());
    bool valid = !normalized.empty() && normalized.size() <= 12;
    for (char c : normalized)
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9'))) valid = false;
    if (!valid)
        throw CasuError("export format must be a 1-12 character filename extension");
    std::vector<std::string> targets;
    std::map<std::string, std::vector<std::size_t>> groups;
    for (std::size_t i = 0; i < planned.size(); ++i) {
        std::filesystem::path relative = std::filesystem::path(planned[i].second);
        relative.replace_extension("." + normalized);
        std::string target = abs_path((std::filesystem::path(output_dir) / relative).string());
        targets.push_back(target);
        groups[target].push_back(i);
    }
    for (const auto& [target, indexes] : groups) {
        if (indexes.size() < 2) continue;
        for (std::size_t index : indexes) {
            std::string digest = casu::Sha256::oneshot(planned[index].first).substr(0, 8);
            std::filesystem::path path(target);
            std::string name = path.stem().string() + "-" + digest + "." + normalized;
            targets[index] = (path.parent_path() / name).string();
        }
    }
    return targets;
}

// ---------------------------------------------------------------------------
// Probe-based analysis
// ---------------------------------------------------------------------------
JsonValue build_manifest(const std::string& source, const std::string& mode) {
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
    const std::string abs_str = ec ? abs_path(source) : abs_source.lexically_normal().string();
    const long long size_bytes =
        std::filesystem::exists(abs_source, ec)
            ? (long long)std::filesystem::file_size(abs_source, ec)
            : 0;
    const std::string digest = sha256_hex(source);
    const double duration = casu::media::duration_s(info);

    JsonObject casu_identity;
    casu_identity.items["name"] = JsonValue(std::string("CASU"));
    casu_identity.items["acronym"] = JsonValue(std::string("Codec for All Segmented Units"));
    casu_identity.items["short_name"] = JsonValue(std::string("CASU"));
    casu_identity.items["container_extension"] = JsonValue(std::string(".casu"));
    casu_identity.items["version"] = JsonValue(std::string("3.0.0"));
    casu_identity.items["analysis_mode"] = JsonValue(mode);
    casu_identity.items["compatibility"] =
        JsonValue(std::string("legacy media remains canonical; sidecar is optional"));

    JsonObject format;
    format.items["magic"] = JsonValue(std::string("MPCASU\\0"));
    format.items["kind"] = JsonValue(std::string("CASU sidecar manifest"));
    format.items["schema"] = JsonValue(std::string("0.2"));

    JsonObject source_obj;
    source_obj.items["filename"] = JsonValue(std::filesystem::path(abs_str).filename().string());
    source_obj.items["path"] = JsonValue(abs_str);
    source_obj.items["size_bytes"] = JsonValue((int64_t)size_bytes);
    source_obj.items["sha256"] = JsonValue(digest);
    const JsonValue* format_name = info.raw.find("format");
    if (format_name && format_name->find("format_name"))
        source_obj.items["format_name"] = *format_name->find("format_name");
    source_obj.items["duration_s"] = JsonValue(duration);

    auto streams = std::make_shared<JsonArray>();
    if (const JsonValue* raw_streams = info.raw.find("streams"))
        if (raw_streams->is_array())
            for (const JsonValue& stream : raw_streams->as_array().items)
                streams->items.push_back(stream_entry(stream));

    JsonObject seek_index;
    seek_index.items["method"] = JsonValue(std::string("deterministic segment-boundary index"));
    auto seek_entries = std::make_shared<JsonArray>();
    if (duration > 0) {
        for (const auto* stream : video_streams) {
            JsonObject entry;
            entry.items["timestamp_s"] = JsonValue(0.0);
            entry.items["stream"] = JsonValue(std::string("video"));
            entry.items["segment_id"] = JsonValue(std::string("video-000000"));
            entry.items["state"] = JsonValue(std::string("active"));
            seek_entries->items.push_back(JsonValue(std::make_shared<JsonObject>(std::move(entry))));
        }
        for (const auto* stream : audio_streams) {
            JsonObject entry;
            entry.items["timestamp_s"] = JsonValue(0.0);
            entry.items["stream"] = JsonValue(std::string("audio"));
            entry.items["segment_id"] = JsonValue(std::string("audio-000000"));
            entry.items["state"] = JsonValue(std::string("active"));
            seek_entries->items.push_back(JsonValue(std::make_shared<JsonObject>(std::move(entry))));
        }
    }
    seek_index.items["entries"] = JsonValue(std::move(seek_entries));
    seek_index.items["native_key_states"] = JsonValue(false);
    seek_index.items["note"] = JsonValue(std::string(
        "sidecar navigation hints only; decoder keyframe seeking remains backend-owned"));

    JsonObject integrity;
    integrity.items["timestamps_are_source_of_truth"] = JsonValue(true);
    integrity.items["optimization_is_hint_only"] = JsonValue(true);
    integrity.items["mode_is_not_quality_proof"] = JsonValue(true);
    integrity.items["fallback"] =
        JsonValue(std::string("full-frame/full-fidelity legacy playback"));

    JsonObject root;
    root.items["format"] = JsonValue(std::make_shared<JsonObject>(std::move(format)));
    root.items["casu"] = JsonValue(std::make_shared<JsonObject>(std::move(casu_identity)));
    root.items["source"] = JsonValue(std::make_shared<JsonObject>(std::move(source_obj)));
    root.items["streams"] = JsonValue(std::move(streams));
    if (video_streams.empty())
        root.items["video"] = segments_section({}, duration);
    else
        root.items["video"] = segments_section(video_streams, duration);
    if (audio_streams.empty())
        root.items["audio"] = segments_section({}, duration);
    else
        root.items["audio"] = segments_section(audio_streams, duration);
    root.items["seek_index"] = JsonValue(std::make_shared<JsonObject>(std::move(seek_index)));
    root.items["integrity"] = JsonValue(std::make_shared<JsonObject>(std::move(integrity)));

    JsonValue manifest = JsonValue(std::make_shared<JsonObject>(std::move(root)));
    const std::vector<std::string> errors = casu::validate_manifest(manifest);
    if (!errors.empty())
        throw CasuError("internal manifest validation failed: " + errors[0]);
    return manifest;
}

bool error_all_ok(const casu::JsonValue& payload) {
    const casu::JsonValue* files = payload.find("files");
    if (!files || !files->is_array()) return true;
    for (const casu::JsonValue& entry : files->as_array().items) {
        const casu::JsonValue* status = entry.find("status");
        if (status && status->is_string() && status->as_string() == "failed") return false;
    }
    return true;
}

}  // namespace casu::cli
