// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/codec/ffprobe.hpp"

#include "casu/codec/subprocess.hpp"
#include "casu/codec/tools.hpp"

#include <exception>
#include <string>
#include <vector>

namespace casu::codec {

namespace {

std::string strip_ws(const std::string& text) {
    std::size_t begin = 0;
    while (begin < text.size() && (text[begin] == ' ' || text[begin] == '\t' ||
                                   text[begin] == '\r' || text[begin] == '\n'))
        ++begin;
    std::size_t end = text.size();
    while (end > begin && (text[end - 1] == ' ' || text[end - 1] == '\t' ||
                           text[end - 1] == '\r' || text[end - 1] == '\n'))
        --end;
    return text.substr(begin, end - begin);
}

// ffprobe emits several numeric fields (duration, size, bit_rate, ...) as
// JSON strings; accept both real numbers and numeric strings.
double json_number(const JsonValue& value) {
    if (value.is_number()) return value.as_double();
    if (value.is_string()) {
        const std::string& text = value.as_string();
        try {
            std::size_t consumed = 0;
            const double parsed = std::stod(text, &consumed);
            if (consumed == text.size()) return parsed;
        } catch (const std::exception&) {
        }
    }
    return 0.0;
}

}  // namespace

JsonValue probe_json(const std::string& path, int timeout_seconds) {
    std::string executable = ffprobe_path();
    if (executable.empty())
        throw MediaProbeError("required tool not found: ffprobe");
    Subprocess proc(std::move(executable),
                    std::chrono::seconds(timeout_seconds < 1 ? 1 : timeout_seconds));
    const std::vector<std::string> args = {
        "-v", "error", "-show_streams", "-show_format", "-show_chapters",
        "-of", "json", path,
    };
    ProcessResult result = proc.run(args, 32 * 1024 * 1024, 8 * 1024 * 1024);
    if (!result.started)
        throw MediaProbeError(result.stderr_data.empty() ? "could not start ffprobe"
                                                         : result.stderr_data);
    if (result.timed_out) throw MediaProbeError("media probe timed out");
    if (result.exit_code != 0) {
        std::string detail = result.stderr_data;
        if (detail.empty()) detail = "ffprobe exited with code " + std::to_string(result.exit_code);
        throw MediaProbeError("media probe failed: " + detail);
    }
    try {
        JsonValue value = parse_json(strip_ws(result.stdout_data));
        if (!value.is_object()) throw MediaProbeError("media probe JSON root must be an object");
        return value;
    } catch (const JsonError& exc) {
        throw MediaProbeError(std::string("media probe returned invalid JSON: ") + exc.what());
    }
}

bool probe_has_stream(const JsonValue& probe, const std::string& codec_type) {
    return first_playable_stream(probe, codec_type) != nullptr;
}

double probe_duration(const JsonValue& probe) {
    const JsonValue* format = probe.find("format");
    double best = 0.0;
    if (format) {
        if (const JsonValue* d = format->find("duration"))
            if (d->is_number() || d->is_string()) {
                const double parsed = json_number(*d);
                if (parsed > best) best = parsed;
            }
    }
    const JsonValue* streams = probe.find("streams");
    if (streams && streams->is_array()) {
        for (const JsonValue& item : streams->as_array().items) {
            if (const JsonValue* d = item.find("duration"))
                if (d->is_number() || d->is_string()) {
                    const double parsed = json_number(*d);
                    if (parsed > best) best = parsed;
                }
        }
    }
    return best;
}

const JsonValue* first_playable_stream(const JsonValue& probe,
                                       const std::string& codec_type) {
    const JsonValue* streams = probe.find("streams");
    if (!streams || !streams->is_array()) return nullptr;
    for (const JsonValue& item : streams->as_array().items) {
        const JsonValue* type = item.find("codec_type");
        if (!type || !type->is_string() || type->as_string() != codec_type) continue;
        if (codec_type == "video") {
            const JsonValue* disposition = item.find("disposition");
            if (disposition && disposition->is_object()) {
                const JsonValue* pic = disposition->find("attached_pic");
                if (pic && pic->is_int() && pic->as_int() != 0) continue;
            }
        }
        return &item;
    }
    return nullptr;
}

}  // namespace casu::codec
