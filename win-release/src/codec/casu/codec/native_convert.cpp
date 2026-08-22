// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Full port of casu/native_v2/converter.py (see header for parity notes).
#include "casu/codec/native_convert.hpp"

#include "casu/sha256.hpp"
#include "casu/codec/tools.hpp"
#include "casu/native_v2.hpp"

#include <QDateTime>
#include <QElapsedTimer>
#include <QProcess>
#include <QTemporaryFile>

#include <algorithm>
#include <deque>
#include <iomanip>
#ifndef _WIN32
#include <unistd.h>
#else
#include <process.h>
#endif
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <map>
#include <optional>
#include <set>
#include <sstream>

namespace fs = std::filesystem;

namespace casu::natconv {

using natv2::CanonicalFrame;
using strict::Rational;
using strict::StrictFrame;

namespace {

[[noreturn]] void fail(const std::string& msg) {
    throw NativeConversionError(msg);
}

std::string json_str_or(const JsonValue* v, const char* fallback) {
    return v && v->is_string() ? v->as_string() : std::string(fallback);
}

std::string coerce_text(const JsonValue* v) {
    if (!v || v->is_null()) return {};
    switch (v->kind()) {
        case JsonValue::Kind::String: return v->as_string();
        case JsonValue::Kind::Int: return std::to_string(v->as_int());
        case JsonValue::Kind::Bool: return v->as_bool() ? "True" : "False";
        default:
            return {};  // containers are not str()-coercible here
    }
}

bool truthy(const JsonValue* v) {
    if (!v || v->is_null()) return false;
    if (v->is_bool()) return v->as_bool();
    if (v->is_int()) return v->as_int() != 0;
    if (v->is_double()) return v->as_double() != 0.0;
    if (v->is_string()) return !v->as_string().empty();
    return true;  // non-empty array/object
}

std::optional<int64_t> to_int(const JsonValue* v);

std::optional<int64_t> parse_int_text(const std::string& s) {
    try {
        std::size_t idx = 0;
        const long long parsed = std::stoll(s, &idx, 10);
        while (idx < s.size() && std::isspace(static_cast<unsigned char>(s[idx])))
            ++idx;
        if (idx != s.size()) return std::nullopt;
        return static_cast<int64_t>(parsed);
    } catch (const std::exception&) {
        return std::nullopt;
    }
}

std::optional<int64_t> to_int(const JsonValue* v) {
    if (!v || v->is_null() || v->is_array() || v->is_object()) return std::nullopt;
    if (v->is_int()) return v->as_int();
    if (v->is_double())
        return static_cast<int64_t>(v->as_double());  // truncation
    if (v->is_bool()) return std::nullopt;            // int(True) guarded by caller
    return parse_int_text(v->as_string());
}

std::string ascii_fold(const std::string& s) {
    std::string out = s;
    for (char& c : out)
        if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
    return out;
}

JsonValue make_object(
    std::initializer_list<std::pair<std::string, JsonValue>> items) {
    auto o = std::make_shared<JsonObject>();
    for (auto& [k, val] : items) o->items[k] = std::move(val);
    return JsonValue(std::move(o));
}

JsonValue make_array(std::vector<JsonValue> items) {
    auto a = std::make_shared<JsonArray>();
    a->items = std::move(items);
    return JsonValue(std::move(a));
}

// --- _bounded_tags -----------------------------------------------------------
JsonValue bounded_tags(const JsonValue* value) {
    if (!value || value->is_null()) return make_object({});
    if (!value->is_object() ||
        value->as_object().items.size() > 256)
        fail("source metadata exceeds tag count limit");
    std::vector<std::pair<std::string, std::string>> pairs;
    uint64_t total = 0;
    for (const auto& [raw_key, raw_value] : value->as_object().items) {
        std::string key = raw_key;
        // str(key).strip()
        const auto is_space = [](unsigned char c) {
            return c == ' ' || c == '\t' || c == '\n' || c == '\r' ||
                   c == '\f' || c == '\v';
        };
        key.erase(key.begin(), std::find_if_not(key.begin(), key.end(), is_space));
        key.erase(std::find_if_not(key.rbegin(), key.rend(), is_space).base(),
                  key.end());
        const std::string item = coerce_text(&raw_value);
        if (key.empty() || key.size() > 128)
            fail("source metadata key is invalid");
        if (item.size() > 4096)
            fail("source metadata value exceeds limit");
        total += key.size() + item.size();
        if (total > 1024ULL * 1024)
            fail("source metadata exceeds total size limit");
        pairs.emplace_back(key, item);
    }
    std::stable_sort(pairs.begin(), pairs.end(),
                     [](const auto& a, const auto& b) {
                         return ascii_fold(a.first) < ascii_fold(b.first);
                     });
    auto o = std::make_shared<JsonObject>();
    for (auto& [k, v] : pairs) o->items[k] = JsonValue(v);
    return JsonValue(std::move(o));
}

// --- _disposition ------------------------------------------------------------
JsonValue disposition_value(const JsonValue* value) {
    auto o = std::make_shared<JsonObject>();
    if (!value || !value->is_object())
        return JsonValue(std::move(o));
    for (const auto& [key, enabled] : value->as_object().items)
        o->items[key] = JsonValue(truthy(&enabled));
    return JsonValue(std::move(o));
}

// --- _fraction ---------------------------------------------------------------
std::pair<int64_t, int64_t> fraction_pair(const std::string& text) {
    try {
        const std::size_t slash = text.find('/');
        if (slash == std::string::npos) throw std::invalid_argument("");
        const auto num = parse_int_text(text.substr(0, slash));
        const auto den = parse_int_text(text.substr(slash + 1));
        if (!num || !den || *num <= 0 || *den <= 0)
            throw std::invalid_argument("");
        return {*num, *den};
    } catch (const std::invalid_argument&) {
        fail("invalid source time base");
    }
}

// --- _frame_pts --------------------------------------------------------------
std::vector<JsonValue> frame_pts_list(const JsonArray& frames) {
    std::vector<JsonValue> result;
    result.reserve(frames.items.size());
    for (const JsonValue& frame : frames.items) {
        if (!frame.is_object())
            fail("decoded frame has no presentation timestamp");
        const JsonValue* pts_value = frame.find("best_effort_timestamp");
        if (!pts_value || pts_value->is_null())
            pts_value = frame.find("pts");
        const auto pts = to_int(pts_value);
        if (!pts)
            fail("decoded frame has no presentation timestamp");
        const JsonValue* duration = frame.find("pkt_duration");
        if (!duration || duration->is_null())
            duration = frame.find("duration");
        std::optional<int64_t> duration_pts;
        if (duration && !duration->is_null() &&
            !(duration->is_string() && duration->as_string() == "N/A"))
            duration_pts = to_int(duration);
        JsonObject entry;
        entry.items["pts"] = JsonValue(*pts);
        entry.items["duration_pts"] =
            duration_pts ? JsonValue(*duration_pts) : JsonValue(nullptr);
        result.push_back(JsonValue(std::make_shared<JsonObject>(
            std::move(entry))));
    }
    return result;
}

// --- bounded subprocess runner -----------------------------------------------
class BoundedRunError : public std::runtime_error {
public:
    explicit BoundedRunError(const std::string& m)
        : std::runtime_error(m) {}
};

// Runs the command capturing stdout up to max_output_bytes; mirrors the
// reference run_bounded contract closely enough for its call sites.
std::string run_bounded(const QStringList& args,
                        uint64_t max_output_bytes,
                        int timeout_ms) {
    QProcess proc;
    proc.setProgram(QString::fromStdString(casu::codec::ffmpeg_path()));
    proc.setArguments(args);
    proc.setProcessChannelMode(QProcess::SeparateChannels);
    QTemporaryFile err_file;
    err_file.open();
    proc.setStandardErrorFile(err_file.fileName());
    proc.start();
    if (!proc.waitForStarted(10000)) throw BoundedRunError("process failed to start");
    QByteArray out;
    while (true) {
        const QByteArray chunk =
            proc.read(static_cast<qint64>(max_output_bytes - out.size() + 1));
        if (!chunk.isEmpty()) {
            out += chunk;
            if (static_cast<uint64_t>(out.size()) > max_output_bytes)
                break;
        }
        if (proc.state() != QProcess::Running &&
            proc.bytesAvailable() == 0)
            break;
        if (!proc.waitForReadyRead(30000) &&
            proc.state() != QProcess::Running &&
            proc.bytesAvailable() == 0)
            break;
    }
    // Under Wine/Qt the finished signal may already have been processed by
    // an earlier waitForReadyRead; only wait while still running.
    if (proc.state() != QProcess::NotRunning &&
        !proc.waitForFinished(timeout_ms)) {
        proc.kill();
        proc.waitForFinished(5000);
        throw BoundedRunError("subprocess timed out");
    }
    if (static_cast<uint64_t>(out.size()) > max_output_bytes)
        throw BoundedRunError("bounded subprocess output exceeded limit");
    if (proc.exitCode() != 0) throw BoundedRunError("subprocess failed");
    return std::string(out.constData(), static_cast<std::size_t>(out.size()));
}

JsonValue run_probe_json(const std::vector<std::string>& args) {
    QProcess proc;
    const QString program = QString::fromStdString(
        casu::codec::ffprobe_path().empty() ? std::string("ffprobe")
                                            : casu::codec::ffprobe_path());
    QStringList qargs;
    for (const auto& a : args) qargs << QString::fromStdString(a);
    proc.start(program, qargs);
    if (!proc.waitForStarted(10000)) fail("media probe failed");
    QByteArray out;
    while (proc.waitForReadyRead(30000) || proc.bytesAvailable() > 0 ||
           proc.state() == QProcess::Running) {
        out += proc.readAllStandardOutput();
        if (proc.state() != QProcess::Running && proc.bytesAvailable() == 0)
            break;
    }
    proc.waitForFinished(60000);
    if (proc.exitCode() != 0) fail("media probe failed");
    try {
        return parse_json(out.toStdString());
    } catch (const JsonError&) {
        fail("media probe failed");
    }
}

// --- _inventory --------------------------------------------------------------
std::pair<JsonObject, std::vector<JsonValue>> inventory(
    const std::string& source, const std::string& selector) {
    JsonValue data = run_probe_json({
        "-v", "error", "-select_streams", selector, "-show_entries",
        "stream=width,height,pix_fmt,time_base,color_space,color_transfer,"
        "color_primaries,color_range,chroma_location,sample_rate,channels,"
        "channel_layout:"
        "frame=best_effort_timestamp,pts,pkt_duration,duration,nb_samples,"
        "width,height,pix_fmt",
        "-of", "json", source,
    });
    const JsonValue* streams = data.find("streams");
    if (!streams || !streams->is_array() ||
        streams->as_array().items.size() != 1)
        fail("probe selector " + selector +
             " did not resolve one stream");
    if (!streams->as_array().items[0].is_object())
        fail("probe selector " + selector + " did not resolve one stream");
    std::vector<JsonValue> frames;
    if (const JsonValue* f = data.find("frames"); f && f->is_array())
        frames = f->as_array().items;
    return {streams->as_array().items[0].as_object(), std::move(frames)};
}

// --- WebVTT cue timing (port of _VTT_TIME/_vtt_milliseconds) -----------------
namespace {

struct VttMatch {
    int64_t start_ms = 0;
    int64_t end_ms = 0;
};

bool digits_at(const std::string& s, std::size_t pos, std::size_t count,
               int64_t& value) {
    if (pos + count > s.size()) return false;
    int64_t acc = 0;
    for (std::size_t i = 0; i < count; ++i) {
        const char c = s[pos + i];
        if (c < '0' || c > '9') return false;
        acc = acc * 10 + (c - '0');
    }
    value = acc;
    return true;
}

bool is_space_char(char c) { return c == ' ' || c == '\t'; }

// Parses MM:SS.mms after the optional hour part; mirrors regex backtracking
// of (?:(\d{2}):)?(\d{2}):(\d{2})\.(\d{3}).
bool timestamp_tail(const std::string& s, std::size_t& pos, int64_t& minutes,
                    int64_t& seconds, int64_t& millis) {
    const std::size_t start = pos;
    if (!digits_at(s, pos, 2, minutes)) { pos = start; return false; }
    if (pos + 2 >= s.size() || s[pos + 2] != ':') { pos = start; return false; }
    pos += 3;
    if (!digits_at(s, pos, 2, seconds)) { pos = start; return false; }
    if (pos + 2 >= s.size() || s[pos + 2] != '.') { pos = start; return false; }
    pos += 3;
    if (!digits_at(s, pos, 3, millis)) { pos = start; return false; }
    pos += 3;
    return true;
}

bool timestamp_shape(const std::string& s, std::size_t& pos, int64_t& ms) {
    const std::size_t start = pos;
    int64_t hours = 0, minutes = 0, seconds = 0, millis = 0;
    // Attempt 1: consume the optional HH: prefix.
    if (digits_at(s, pos, 2, hours) && pos + 2 < s.size() &&
        s[pos + 2] == ':') {
        std::size_t tail_pos = pos + 3;
        if (timestamp_tail(s, tail_pos, minutes, seconds, millis)) {
            pos = tail_pos;
            ms = ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis;
            return true;
        }
    }
    // Attempt 2: backtrack — no hours present.
    hours = 0;
    std::size_t tail_pos = start;
    if (timestamp_tail(s, tail_pos, minutes, seconds, millis)) {
        pos = tail_pos;
        ms = ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis;
        return true;
    }
    pos = start;
    return false;
}

std::optional<VttMatch> match_vtt_times(const std::string& line) {
    for (std::size_t i = 0; i + 12 <= line.size(); ++i) {
        std::size_t pos = i;
        int64_t start = 0, end = 0;
        if (!timestamp_shape(line, pos, start)) continue;
        std::size_t j = pos;
        while (j < line.size() && is_space_char(line[j])) ++j;
        if (j == pos) continue;                       // \s+ requires one
        if (line.compare(j, 3, "-->") != 0) continue;
        j += 3;
        const std::size_t after_arrow = j;
        while (j < line.size() && is_space_char(line[j])) ++j;
        if (j == after_arrow) continue;
        if (!timestamp_shape(line, j, end)) continue;
        return VttMatch{start, end};
    }
    return std::nullopt;
}

}  // namespace

// --- _video_chunks -----------------------------------------------------------
namespace {

void append_video_chunks(const std::string& source, int64_t stream_id,
                         int relative_index, const Rational& max_key_interval,
                         int64_t tile_width, int64_t tile_height,
                         std::vector<natv2::StrictTileState>* /*unused*/,
                         std::vector<casunat2::Chunk>& out) {
    std::optional<CanonicalFrame> previous;
    std::optional<Rational> last_key_time;
    std::map<std::array<int64_t, 4>, std::string> previous_hashes;
    bool have_hashes = false;

    strict::FrameSource source_frames(source, relative_index);
    StrictFrame current;
    while (source_frames.next(current)) {
        const Rational now{current.pts * current.time_base_num,
                           current.time_base_den};
        const bool format_change =
            !previous.has_value() ||
            !(previous->format_identity() == current.frame.format_identity());
        bool key_due = true;
        if (last_key_time.has_value()) {
            const Rational elapsed{
                now.num * last_key_time->den - last_key_time->num * now.den,
                now.den * last_key_time->den};
            key_due = elapsed >= max_key_interval;
        }
        if (previous.has_value() && format_change) {
            casunat2::Chunk chunk;
            chunk.chunk_type = casunat2::VIDEO_FORMAT_CHANGE;
            chunk.stream_id = static_cast<uint8_t>(stream_id);
            chunk.pts = current.pts;
            chunk.payload = natv2::encode_format_change(current.frame);
            out.push_back(std::move(chunk));
        }
        if (format_change || key_due) {
            casunat2::Chunk chunk;
            chunk.chunk_type = casunat2::VIDEO_KEY_STATE;
            chunk.stream_id = static_cast<uint8_t>(stream_id);
            chunk.pts = current.pts;
            chunk.payload = natv2::encode_key_state(current.frame);
            out.push_back(std::move(chunk));
            last_key_time = now;
            have_hashes = false;
            previous_hashes.clear();
        } else {
            const std::vector<natv2::StrictTileState> states =
                natv2::compare_frames(&*previous, current.frame, tile_width,
                                      tile_height,
                                      have_hashes ? &previous_hashes : nullptr);
            previous_hashes.clear();
            have_hashes = true;
            for (const natv2::StrictTileState& state : states) {
                previous_hashes[{state.x, state.y, state.w, state.h}] =
                    state.state_hash;
                if (state.state != "UPDATE") continue;
                casunat2::Chunk chunk;
                chunk.chunk_type = casunat2::VIDEO_TILE_UPDATE;
                chunk.stream_id = static_cast<uint8_t>(stream_id);
                chunk.pts = current.pts;
                chunk.payload = natv2::encode_tile_update(
                    current.frame, state.x, state.y, state.w, state.h,
                    state.has_reference ? state.reference_hash.c_str()
                                        : nullptr);
                out.push_back(std::move(chunk));
            }
        }
        previous = current.frame;
    }
}

// --- _audio_chunks -----------------------------------------------------------
class AudioPipe {
public:
    AudioPipe(const std::string& source, int relative_index, int64_t channels,
              int64_t sample_rate)
        : channels_(channels) {
        QStringList args{
            QStringLiteral("-v"), QStringLiteral("error"),
            QStringLiteral("-i"), QString::fromStdString(source),
            QString::fromStdString("-map"),
            QString::fromStdString("0:a:" + std::to_string(relative_index)),
            QStringLiteral("-vn"), QStringLiteral("-sn"), QStringLiteral("-dn"),
            QStringLiteral("-ac"),
            QString::fromStdString(std::to_string(channels)),
            QStringLiteral("-ar"),
            QString::fromStdString(std::to_string(sample_rate)),
            QStringLiteral("-f"), QStringLiteral("s16le"),
            QStringLiteral("-acodec"), QStringLiteral("pcm_s16le"),
            QStringLiteral("pipe:1")};
        process_.setProgram(QString::fromStdString(
            casu::codec::ffmpeg_path().empty() ? std::string("ffmpeg")
                                               : casu::codec::ffmpeg_path()));
        process_.setArguments(args);
        process_.setProcessChannelMode(QProcess::SeparateChannels);
        error_file_.open();
        process_.setStandardErrorFile(error_file_.fileName());
        process_.start();
        if (!process_.waitForStarted(10000))
            fail("audio decoder failed: could not open FFmpeg process");
    }

    std::vector<uint8_t> read_exact(int64_t length) {
        std::vector<uint8_t> pcm(static_cast<std::size_t>(length));
        std::size_t filled = 0;
        while (filled < pcm.size()) {
            const QByteArray chunk =
                process_.read(static_cast<qint64>(pcm.size() - filled));
            if (!chunk.isEmpty()) {
                std::memcpy(pcm.data() + filled, chunk.constData(),
                            static_cast<std::size_t>(chunk.size()));
                filled += static_cast<std::size_t>(chunk.size());
                continue;
            }
            if (process_.bytesAvailable() == 0 &&
                process_.state() != QProcess::Running)
                break;
            if (!process_.waitForReadyRead(30000)) {
                if (process_.state() != QProcess::Running &&
                    process_.bytesAvailable() == 0)
                    break;
            }
        }
        if (filled != pcm.size())
            fail("audio decoder ended before a complete PCM block");
        return pcm;
    }

    std::vector<uint8_t> drain_one_byte() {
        QByteArray data = process_.read(1);
        return std::vector<uint8_t>(data.constBegin(), data.constEnd());
    }

    void finish(bool cancelled) {
        if (process_.state() == QProcess::Running) {
            process_.terminate();
            if (!process_.waitForFinished(5000)) process_.kill();
            process_.waitForFinished(5000);
        }
        error_file_.flush();
        QFile ef(error_file_.fileName());
        std::string message;
        if (ef.open(QIODevice::ReadOnly))
            message = ef.readAll().toStdString();
        while (!message.empty() &&
               (message.back() == '\n' || message.back() == '\r' ||
                message.back() == ' '))
            message.pop_back();
        if (process_.exitCode() != 0 && !cancelled &&
            message.find("cancelled") == std::string::npos)
            fail("audio decoder failed: " +
                 (message.empty()
                      ? std::to_string(process_.exitCode())
                      : message.substr(0, message.find('\n'))));
        finished_ = true;
    }

private:
    QProcess process_;
    QTemporaryFile error_file_;
    int64_t channels_;
    bool finished_ = false;
};

void append_audio_chunks(const std::string& source, int64_t stream_id,
                         int relative_index, const JsonObject& stream,
                         const std::vector<JsonValue>& frames,
                         std::vector<casunat2::Chunk>& out) {
    const auto sample_rate = to_int(stream.items.count("sample_rate")
                                        ? &stream.items.at("sample_rate")
                                        : nullptr)
                                 .value_or(0);
    const auto channels =
        to_int(stream.items.count("channels") ? &stream.items.at("channels")
                                              : nullptr)
            .value_or(0);
    if (sample_rate <= 0 || channels <= 0)
        fail("invalid source audio format");
    auto tb_field = stream.items.count("time_base")
                        ? stream.items.at("time_base")
                        : JsonValue{};
    const auto [tb_num, tb_den] =
        fraction_pair(coerce_text(tb_field.is_null() ? nullptr : &tb_field));
    std::string channel_layout_value;
    if (auto layout = stream.items.find("channel_layout");
        layout != stream.items.end())
        channel_layout_value = coerce_text(&layout->second);

    AudioPipe pipe(source, relative_index, channels, sample_rate);
    for (const JsonValue& info : frames) {
        const JsonValue* pts_value = info.find("best_effort_timestamp");
        if (!pts_value || pts_value->is_null()) pts_value = info.find("pts");
        const auto pts = to_int(pts_value);
        const auto samples = to_int(info.find("nb_samples")).value_or(0);
        if (!pts || samples <= 0)
            fail("decoded audio frame lacks PTS/sample count");
        const int64_t length = samples * channels * 2;
        const std::vector<uint8_t> pcm = pipe.read_exact(length);
        casunat2::Chunk chunk;
        chunk.chunk_type = casunat2::AUDIO_BLOCK;
        chunk.stream_id = static_cast<uint8_t>(stream_id);
        chunk.pts = *pts;
        chunk.payload = natv2::encode_audio_block(
            pcm, *pts, tb_num, tb_den, sample_rate, channels, "s16le",
            channel_layout_value.empty() ? nullptr
                                         : channel_layout_value.c_str(),
            samples);
        out.push_back(std::move(chunk));
    }
    const bool extra = !pipe.drain_one_byte().empty();
    pipe.finish(false);
    if (extra)
        fail("audio decoder produced more samples than its frame inventory");
}

// --- _subtitle_chunks (text) --------------------------------------------------
namespace {

std::vector<casunat2::Chunk> text_subtitle_chunks(const std::string& source,
                                                  int64_t stream_id,
                                                  int relative_index,
                                                  const std::string& language) {
    QStringList args{
        QStringLiteral("-nostdin"),
        QStringLiteral("-v"), QStringLiteral("error"),
        QStringLiteral("-i"), QString::fromStdString(source),
        QString::fromStdString("-map"),
        QString::fromStdString("0:s:" + std::to_string(relative_index)),
        QStringLiteral("-f"), QStringLiteral("webvtt"), QStringLiteral("pipe:1")};
    std::string text;
    try {
        text = run_bounded(args, 64ULL * 1024 * 1024, 600000);
    } catch (const BoundedRunError&) {
        fail("subtitle stream cannot be represented by the native text "
             "reference codec");
    }
    // Normalize CRLF and split.
    std::vector<std::string> lines;
    {
        std::string normalized;
        normalized.reserve(text.size());
        for (std::size_t i = 0; i < text.size(); ++i) {
            if (text[i] == '\r' && i + 1 < text.size() && text[i + 1] == '\n')
                continue;
            normalized.push_back(text[i] == '\r' ? '\n' : text[i]);
        }
        std::istringstream ss(normalized);
        std::string line;
        while (std::getline(ss, line)) lines.push_back(line);
    }
    std::vector<casunat2::Chunk> out;
    std::size_t index = 0;
    while (index < lines.size()) {
        const auto match = match_vtt_times(lines[index]);
        if (!match) { ++index; continue; }
        ++index;
        std::vector<std::string> values;
        while (index < lines.size() &&
               !lines[index].empty() &&
               lines[index].find_first_not_of(" \t\r") != std::string::npos) {
            values.push_back(lines[index]);
            ++index;
        }
        std::string cue;
        for (std::size_t i = 0; i < values.size(); ++i) {
            if (i) cue += "\n";
            cue += values[i];
        }
        // strip()
        const auto is_space = [](unsigned char c) {
            return c == ' ' || c == '\t' || c == '\n' || c == '\r' ||
                   c == '\f' || c == '\v';
        };
        cue.erase(cue.begin(), std::find_if_not(cue.begin(), cue.end(), is_space));
        cue.erase(std::find_if_not(cue.rbegin(), cue.rend(), is_space).base(),
                  cue.end());
        if (cue.empty()) continue;
        natv2::SubtitlePacket packet;
        packet.start_pts = match->start_ms;
        packet.end_pts = match->end_ms;
        packet.text = cue;
        packet.language = language.empty() ? "und" : language;
        packet.format = "webvtt-text";
        casunat2::Chunk chunk;
        chunk.chunk_type = casunat2::SUBTITLE_PACKET;
        chunk.stream_id = static_cast<uint8_t>(stream_id);
        chunk.pts = match->start_ms;
        chunk.payload = natv2::encode_subtitle_packet(packet);
        out.push_back(std::move(chunk));
    }
    return out;
}

// --- _rich_subtitle_source_chunk ----------------------------------------------
std::optional<casunat2::Chunk> rich_subtitle_source_chunk(
    const std::string& source, int64_t stream_id, int relative_index,
    const JsonObject& stream) {
    const std::string codec = json_str_or(
        stream.items.count("codec_name") ? &stream.items.at("codec_name")
                                         : nullptr,
        "");
    std::string lowered = codec;
    std::transform(lowered.begin(), lowered.end(), lowered.begin(),
                   [](unsigned char c) { return char(std::tolower(c)); });
    if (lowered != "ass" && lowered != "ssa") return std::nullopt;
    QStringList args{
        QStringLiteral("-v"), QStringLiteral("error"),
        QStringLiteral("-i"), QString::fromStdString(source),
        QString::fromStdString("-map"),
        QString::fromStdString("0:s:" + std::to_string(relative_index)),
        QString::fromStdString("-c:s"), QStringLiteral("copy"),
        QStringLiteral("-f"), QStringLiteral("ass"), QStringLiteral("pipe:1")};
    std::string data;
    try {
        data = run_bounded(args, 64ULL * 1024 * 1024, 600000);
    } catch (const BoundedRunError&) {
        fail("could not preserve rich subtitle source");
    }
    casunat2::Chunk chunk;
    chunk.chunk_type = casunat2::ATTACHMENT;
    chunk.stream_id = static_cast<uint8_t>(stream_id);
    chunk.pts = 0;
    chunk.payload = natv2::encode_attachment(
        "subtitle-" + std::to_string(stream_id) + ".ass", "text/x-ssa",
        std::vector<uint8_t>(data.begin(), data.end()), "subtitle-source");
    return chunk;
}

// --- bitmap subtitle helpers --------------------------------------------------
namespace {

// round(Fraction(num, den)) with banker's rounding like Python.
int64_t rational_round_half_even(__int128 num, int64_t den) {
    bool negative = num < 0;
    __int128 n = negative ? -num : num;
    __int128 q = n / den;
    __int128 r = n % den;
    const __int128 twice = r * 2;
    if (twice > den || (twice == den && (q & 1) == 1)) ++q;
    return static_cast<int64_t>(negative ? -q : q);
}

// Truncation toward zero like int(Fraction).
int64_t rational_truncate(__int128 num, int64_t den) {
    return static_cast<int64_t>(num / den);
}

std::vector<uint8_t> packed_rgba(const CanonicalFrame& frame) {
    const auto [height, width] = frame.shape();
    std::vector<uint8_t> out;
    out.reserve(static_cast<std::size_t>(height * width * 4));
    std::array<int, 4> order{0, 1, 2, 3};
    if (frame.pixel_format == "bgra") order = {2, 1, 0, 3};
    else if (frame.pixel_format == "argb") order = {1, 2, 3, 0};
    else if (frame.pixel_format == "abgr") order = {3, 2, 1, 0};
    else if (frame.pixel_format != "rgba")
        fail("bitmap subtitle renderer returned '" + frame.pixel_format +
             "', expected RGBA");
    const natv2::CanonicalPlane& plane = frame.planes.at(0);
    for (int64_t row = 0; row < height; ++row) {
        for (int64_t col = 0; col < width; ++col) {
            const std::size_t base =
                static_cast<std::size_t>(row * width + col) * 4;
            for (int c = 0; c < 4; ++c)
                out.push_back(plane.data[base + static_cast<std::size_t>(order[c])]);
        }
    }
    return out;
}

std::vector<casunat2::Chunk> bitmap_subtitle_chunks(
    const std::string& source, int64_t stream_id, int relative_index,
    double duration_seconds,
    const std::optional<std::pair<int64_t, int64_t>>& canvas_size) {
    double clamped = duration_seconds > 0.0 ? duration_seconds : 0.0;
    int64_t duration_ms =
        std::max<int64_t>(1,
                          static_cast<int64_t>(clamped * 1000.0 + 0.5));
    fs::path directory = fs::temp_directory_path() /
                         ("casu-bitmap-subtitle-" + std::to_string(::getpid()) +
                          "-" + std::to_string(QDateTime::currentMSecsSinceEpoch()));
    fs::create_directories(directory);
    const fs::path rendered = directory / "overlay.mkv";
    QStringList args{
        QStringLiteral("-v"), QStringLiteral("error")};
    if (canvas_size.has_value()) {
        const auto [cw, chh] = *canvas_size;
        if (cw <= 0 || chh <= 0 || cw > 16'384 || chh > 16'384 ||
            static_cast<__int128>(cw) * chh * 4 > 256LL * 1024 * 1024)
            fail("bitmap subtitle canvas exceeds limits");
        args << QString::fromStdString(
            "-canvas_size:s:" + std::to_string(relative_index));
        args << QString::fromStdString(std::to_string(cw) + "x" +
                                       std::to_string(chh));
    }
    args << QStringLiteral("-i") << QString::fromStdString(source)
         << QString::fromStdString("-filter_complex")
         << QString::fromStdString("[0:s:" + std::to_string(relative_index) +
                                   "]format=rgba[out]")
         << QString::fromStdString("-map") << QStringLiteral("[out]")
         << QStringLiteral("-fps_mode") << QStringLiteral("passthrough")
         << QStringLiteral("-c:v") << QStringLiteral("ffv1")
         << QStringLiteral("-pix_fmt") << QStringLiteral("rgba")
         << QStringLiteral("-y")
         << QString::fromStdString(rendered.string());
    {
        QProcess proc;
        proc.setProgram(QString::fromStdString(
            casu::codec::ffmpeg_path().empty() ? std::string("ffmpeg")
                                               : casu::codec::ffmpeg_path()));
        proc.setArguments(args);
        proc.setProcessChannelMode(QProcess::SeparateChannels);
        proc.start();
        if (!proc.waitForStarted(10000))
            fail("could not decode bitmap subtitle stream");
        while (true) {
            std::error_code ec;
            if (fs::exists(rendered, ec)) {
                const uintmax_t size = fs::file_size(rendered, ec);
                if (!ec && size > 2ULL * 1024 * 1024 * 1024) {
                    proc.kill();
                    fail("could not decode bitmap subtitle stream");
                }
            }
            if (!proc.waitForReadyRead(1000)) {
                if (proc.state() != QProcess::Running) break;
            }
        }
        if (proc.exitCode() != 0)
            fail("could not decode bitmap subtitle stream");
    }
    std::vector<StrictFrame> decoded;
    try {
        decoded = strict::read_all_frames(rendered.string(), 0);
    } catch (const CasuError&) {
        fail("could not decode bitmap subtitle stream");
    }
    std::error_code ec;
    fs::remove_all(directory, ec);

    struct BitmapState {
        std::vector<uint8_t> rgba;
        int64_t canvas_w = 0;
        int64_t canvas_h = 0;
    };
    std::map<int64_t, BitmapState> by_pts;
    for (const StrictFrame& frame : decoded) {
        const Rational frac = frame.time();
        const int64_t pts_ms = rational_round_half_even(
            static_cast<__int128>(frac.num) * 1000, frac.den);
        if (pts_ms >= 0 && pts_ms <= duration_ms) {
            BitmapState state;
            state.rgba = packed_rgba(frame.frame);
            const auto [fh, fw] = frame.frame.shape();
            state.canvas_w = fw;
            state.canvas_h = fh;
            by_pts[pts_ms] = std::move(state);  // last frame per PTS wins
        }
    }
    std::vector<std::pair<int64_t, const BitmapState*>> states;
    std::string previous_digest;
    bool have_previous = false;
    for (const auto& [pts, state] : by_pts) {
        const std::string digest =
            Sha256::oneshot(state.rgba.data(), state.rgba.size());
        if (have_previous && digest == previous_digest) continue;
        states.emplace_back(pts, &state);
        previous_digest = digest;
        have_previous = true;
    }
    std::vector<casunat2::Chunk> out;
    for (std::size_t index = 0; index < states.size(); ++index) {
        const int64_t start = states[index].first;
        const BitmapState& state = *states[index].second;
        const std::vector<uint8_t>& rgba = state.rgba;
        const int64_t end = index + 1 < states.size()
                                ? states[index + 1].first
                                : duration_ms;
        if (end <= start) continue;
        const int64_t canvas_w = state.canvas_w;
        const int64_t canvas_h = state.canvas_h;
        const std::size_t pixels =
            static_cast<std::size_t>(canvas_w) *
            static_cast<std::size_t>(canvas_h);
        int64_t left = -1, right = -1, top = -1, bottom = -1;
        for (std::size_t p = 0; p < pixels; ++p) {
            if (rgba[p * 4 + 3] != 0) {
                const int64_t x = static_cast<int64_t>(
                    p % static_cast<std::size_t>(canvas_w));
                const int64_t y = static_cast<int64_t>(
                    p / static_cast<std::size_t>(canvas_w));
                if (left < 0 || x < left) left = x;
                if (x >= right) right = x + 1;
                if (top < 0 || y < top) top = y;
                if (y >= bottom) bottom = y + 1;
            }
        }
        if (left < 0) continue;  // fully transparent
        std::vector<uint8_t> crop;
        crop.reserve(static_cast<std::size_t>((right - left) *
                                              (bottom - top) * 4));
        for (int64_t row = top; row < bottom; ++row) {
            const std::size_t offset =
                static_cast<std::size_t>(row * canvas_w + left) * 4;
            crop.insert(crop.end(), rgba.begin() + offset,
                        rgba.begin() + offset +
                            static_cast<std::size_t>((right - left) * 4));
        }
        casunat2::Chunk chunk;
        chunk.chunk_type = casunat2::SUBTITLE_BITMAP;
        chunk.stream_id = static_cast<uint8_t>(stream_id);
        chunk.pts = start;
        chunk.payload = natv2::encode_bitmap_subtitle(
            start, end, canvas_w, canvas_h, left, top, crop.data(),
            crop.size(), right - left, bottom - top);
        out.push_back(std::move(chunk));
    }
    return out;
}

// --- _chapter_chunk -----------------------------------------------------------
namespace {

std::optional<casunat2::Chunk> chapter_chunk(const JsonArray& chapters) {
    std::vector<natv2::Chapter> values;
    int64_t index = 0;
    for (const JsonValue& entry : chapters.items) {
        if (!entry.is_object()) fail("invalid chapter timeline");
        auto chapter_time = [&](const char* key) -> Rational {
            const JsonValue* v = entry.find(key);
            if (!v || v->is_null()) return Rational{0, 1};
            return Rational::parse(coerce_text(v));
        };
        const Rational start_r = chapter_time("start_time");
        const JsonValue* end_field = entry.find("end_time");
        const Rational end_r =
            (end_field && !end_field->is_null())
                ? chapter_time("end_time")
                : start_r;
        // int(Fraction * 1_000_000_000), truncating toward zero.
        const int64_t start = rational_truncate(
            static_cast<__int128>(start_r.num) * 1'000'000'000LL, start_r.den);
        const int64_t end = rational_truncate(
            static_cast<__int128>(end_r.num) * 1'000'000'000LL, end_r.den);
        const JsonValue* tags = entry.find("tags");
        const JsonValue* title_value =
            tags && tags->is_object() ? tags->find("title") : nullptr;
        std::string title =
            title_value && !title_value->is_null()
                ? coerce_text(title_value)
                : "Chapter " + std::to_string(index + 1);
        const JsonValue* language_value =
            tags && tags->is_object() ? tags->find("language") : nullptr;
        std::string language =
            language_value && !language_value->is_null()
                ? coerce_text(language_value)
                : "und";
        values.push_back(natv2::Chapter{start, end, title, language});
        ++index;
    }
    if (values.empty()) return std::nullopt;
    casunat2::Chunk chunk;
    chunk.chunk_type = casunat2::CHAPTER_TABLE;
    chunk.stream_id = 0;
    chunk.pts = 0;
    chunk.payload = natv2::encode_chapter_table(values);
    return chunk;
}

// Bounded run that watches one output file's growth (watched_paths port).
void run_ffmpeg_watching_file(const QStringList& args,
                              const fs::path& watched,
                              uint64_t max_bytes,
                              int timeout_ms) {
    QProcess proc;
    proc.setProgram(QString::fromStdString(
        casu::codec::ffmpeg_path().empty() ? std::string("ffmpeg")
                                           : casu::codec::ffmpeg_path()));
    proc.setArguments(args);
    proc.setProcessChannelMode(QProcess::SeparateChannels);
    proc.start();
    if (!proc.waitForStarted(10000))
        throw BoundedRunError("process failed to start");
    QElapsedTimer timer;
    timer.start();
    while (true) {
        std::error_code ec;
        if (fs::exists(watched, ec)) {
            const uintmax_t size = fs::file_size(watched, ec);
            if (!ec && size > max_bytes) {
                proc.kill();
                proc.waitForFinished(5000);
                throw BoundedRunError("watched output exceeded limit");
            }
        }
        if (!proc.waitForReadyRead(250)) {
            if (proc.state() != QProcess::Running) break;
        }
        if (timer.elapsed() > timeout_ms) {
            proc.kill();
            proc.waitForFinished(5000);
            throw BoundedRunError("subprocess timed out");
        }
    }
    if (proc.exitCode() != 0) throw BoundedRunError("subprocess failed");
}

// --- _attachment_chunk ---------------------------------------------------------
casunat2::Chunk attachment_chunk(const std::string& source,
                                 int64_t stream_id, int relative_index,
                                 const JsonObject& stream) {
    fs::path directory = fs::temp_directory_path() /
                         ("casu-attachment-" + std::to_string(::getpid()) +
                          "-" + std::to_string(QDateTime::currentMSecsSinceEpoch()));
    fs::create_directories(directory);
    const fs::path extracted = directory / "attachment.bin";
    QStringList args{
        QStringLiteral("-v"), QStringLiteral("error"),
        QString::fromStdString("-dump_attachment:t:" +
                               std::to_string(relative_index)),
        QString::fromStdString(extracted.string()),
        QStringLiteral("-i"), QString::fromStdString(source),
        QStringLiteral("-f"), QStringLiteral("null"), QStringLiteral("-")};
    try {
        run_ffmpeg_watching_file(args, extracted,
                                 64ULL * 1024 * 1024, 600000);
    } catch (const BoundedRunError&) {
        fail("could not extract source attachment");
    }
    std::vector<uint8_t> data;
    {
        std::ifstream in(extracted, std::ios::binary);
        data.assign(std::istreambuf_iterator<char>(in),
                    std::istreambuf_iterator<char>());
    }
    std::error_code ec;
    fs::remove_all(directory, ec);

    const JsonValue* tags = stream.items.count("tags")
                                ? &stream.items.at("tags")
                                : nullptr;
    std::string filename;
    if (tags && tags->is_object())
        filename = coerce_text(tags->find("filename"));
    if (filename.empty())
        filename = "attachment-" + std::to_string(relative_index) + ".bin";
    std::string media_type;
    if (tags && tags->is_object())
        media_type = coerce_text(tags->find("mimetype"));
    if (media_type.empty()) media_type = "application/octet-stream";
    std::string suffix;
    {
        const std::size_t dot = filename.rfind('.');
        if (dot != std::string::npos) suffix = filename.substr(dot);
        for (char& c : suffix)
            c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    std::string lowered_media = media_type;
    for (char& c : lowered_media)
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    static const std::set<std::string> font_mime = {
        "application/x-truetype-font", "application/vnd.ms-opentype",
        "application/font-sfnt", "application/font-woff"};
    static const std::set<std::string> font_suffix = {
        ".ttf", ".otf", ".ttc", ".woff", ".woff2"};
    const bool is_font = lowered_media.rfind("font/", 0) == 0 ||
                         font_mime.count(lowered_media) ||
                         font_suffix.count(suffix);
    casunat2::Chunk chunk;
    chunk.chunk_type = casunat2::ATTACHMENT;
    chunk.stream_id = static_cast<uint8_t>(stream_id);
    chunk.pts = 0;
    chunk.payload = natv2::encode_attachment(
        filename, media_type, data, is_font ? "subtitle-font" : nullptr);
    return chunk;
}

// --- _cover_art_chunk ----------------------------------------------------------
casunat2::Chunk cover_art_chunk(const std::string& source, int64_t stream_id,
                                int64_t source_index,
                                const JsonObject& stream) {
    const auto width =
        to_int(stream.items.count("width") ? &stream.items.at("width")
                                           : nullptr)
            .value_or(0);
    const auto height =
        to_int(stream.items.count("height") ? &stream.items.at("height")
                                            : nullptr)
            .value_or(0);
    if (width <= 0 || height <= 0 || width > 8192 || height > 8192 ||
        static_cast<__int128>(width) * height * 4 > 256LL * 1024 * 1024)
        fail("cover art geometry exceeds decode limits");
    fs::path directory = fs::temp_directory_path() /
                         ("casu-cover-" + std::to_string(::getpid()) +
                          "-" + std::to_string(QDateTime::currentMSecsSinceEpoch()));
    fs::create_directories(directory);
    const fs::path extracted = directory / "cover.png";
    QStringList args{
        QStringLiteral("-v"), QStringLiteral("error"),
        QStringLiteral("-i"), QString::fromStdString(source),
        QString::fromStdString("-map"),
        QString::fromStdString("0:" + std::to_string(source_index)),
        QStringLiteral("-frames:v") , QStringLiteral("1"),
        QStringLiteral("-an"), QStringLiteral("-sn"), QStringLiteral("-dn"),
        QStringLiteral("-c:v"), QStringLiteral("png"),
        QStringLiteral("-f"), QStringLiteral("image2"),
        QStringLiteral("-update"), QStringLiteral("1"),
        QStringLiteral("-y"), QString::fromStdString(extracted.string())};
    try {
        run_ffmpeg_watching_file(args, extracted,
                                 64ULL * 1024 * 1024, 120000);
    } catch (const BoundedRunError&) {
        fail("could not decode attached cover art");
    }
    std::vector<uint8_t> data;
    {
        std::ifstream in(extracted, std::ios::binary);
        data.assign(std::istreambuf_iterator<char>(in),
                    std::istreambuf_iterator<char>());
    }
    if (data.size() > 64ULL * 1024 * 1024)
        fail("cover art exceeds attachment size limit");
    std::error_code ec;
    fs::remove_all(directory, ec);
    static const uint8_t png_magic[8] = {0x89, 'P', 'N', 'G',
                                         '\r', '\n', 0x1A, '\n'};
    if (data.size() < 8 ||
        std::memcmp(data.data(), png_magic, 8) != 0)
        fail("decoded cover art is not PNG");
    const JsonValue* tags = stream.items.count("tags")
                                ? &stream.items.at("tags")
                                : nullptr;
    std::string title;
    if (tags && tags->is_object())
        title = coerce_text(tags->find("title"));
    if (title.empty()) title = "cover";
    std::string safe_title;
    for (char c : title) {
        const unsigned char u = static_cast<unsigned char>(c);
        if (std::isalnum(u) || c == '.' || c == '_' || c == '-')
            safe_title.push_back(c);
        else
            safe_title.push_back('-');
    }
    // strip leading/trailing '-' '.' like re .strip("-.")
    const auto strip_one = [&](std::string& s) {
        while (!s.empty() && (s.front() == '-' || s.front() == '.'))
            s.erase(s.begin());
        while (!s.empty() && (s.back() == '-' || s.back() == '.'))
            s.pop_back();
    };
    strip_one(safe_title);
    if (safe_title.empty()) safe_title = "cover";
    safe_title = safe_title.substr(0, 80);
    casunat2::Chunk chunk;
    chunk.chunk_type = casunat2::ATTACHMENT;
    chunk.stream_id = static_cast<uint8_t>(stream_id);
    chunk.pts = 0;
    chunk.payload = natv2::encode_attachment(safe_title + ".png",
                                             "image/png", data,
                                             "cover-art");
    return chunk;
}

// --- streaming chunk providers -------------------------------------------------
namespace casunat2 = casu::casunat2;
using ChunkProvider = std::function<std::optional<casunat2::Chunk>()>;

class VideoStreamProvider {
public:
    VideoStreamProvider(const std::string& source, int64_t stream_id,
                        int relative_index, const Rational& max_key_interval,
                        int64_t tile_width, int64_t tile_height)
        : source_(source, relative_index),
          stream_id_(stream_id),
          max_key_interval_(max_key_interval),
          tile_width_(tile_width),
          tile_height_(tile_height) {}

    std::optional<casunat2::Chunk> next() {
        while (pending_.empty()) {
            StrictFrame current;
            if (!source_.next(current)) return std::nullopt;
            produce(current);
        }
        casunat2::Chunk chunk = std::move(pending_.front());
        pending_.pop_front();
        return chunk;
    }

private:
    void produce(const StrictFrame& current) {
        const Rational now{current.pts * current.time_base_num,
                           current.time_base_den};
        bool format_change = !previous_.has_value();
        if (previous_.has_value() &&
            !(previous_->format_identity() ==
              current.frame.format_identity()))
            format_change = true;
        bool key_due = !last_key_time_.has_value();
        if (last_key_time_.has_value()) {
            const Rational elapsed{now.num * last_key_time_->den -
                                       last_key_time_->num * now.den,
                                   now.den * last_key_time_->den};
            key_due = elapsed >= max_key_interval_;
        }
        if (previous_.has_value() && format_change) {
            casunat2::Chunk chunk;
            chunk.chunk_type = casunat2::VIDEO_FORMAT_CHANGE;
            chunk.stream_id = static_cast<uint8_t>(stream_id_);
            chunk.pts = current.pts;
            chunk.payload = natv2::encode_format_change(current.frame);
            pending_.push_back(std::move(chunk));
        }
        if (format_change || key_due) {
            casunat2::Chunk chunk;
            chunk.chunk_type = casunat2::VIDEO_KEY_STATE;
            chunk.stream_id = static_cast<uint8_t>(stream_id_);
            chunk.pts = current.pts;
            chunk.payload = natv2::encode_key_state(current.frame);
            pending_.push_back(std::move(chunk));
            last_key_time_ = now;
            have_hashes_ = false;
            previous_hashes_.clear();
        } else {
            const std::vector<natv2::StrictTileState> states =
                natv2::compare_frames(&*previous_, current.frame,
                                      tile_width_, tile_height_,
                                      have_hashes_ ? &previous_hashes_
                                                   : nullptr);
            previous_hashes_.clear();
            have_hashes_ = true;
            for (const natv2::StrictTileState& state : states) {
                previous_hashes_[{state.x, state.y, state.w, state.h}] =
                    state.state_hash;
                if (state.state != "UPDATE") continue;
                casunat2::Chunk chunk;
                chunk.chunk_type = casunat2::VIDEO_TILE_UPDATE;
                chunk.stream_id = static_cast<uint8_t>(stream_id_);
                chunk.pts = current.pts;
                chunk.payload = natv2::encode_tile_update(
                    current.frame, state.x, state.y, state.w, state.h,
                    state.has_reference ? state.reference_hash.c_str()
                                        : nullptr);
                pending_.push_back(std::move(chunk));
            }
        }
        previous_ = current.frame;
    }

    strict::FrameSource source_;
    int64_t stream_id_;
    Rational max_key_interval_;
    int64_t tile_width_;
    int64_t tile_height_;
    std::optional<CanonicalFrame> previous_;
    std::optional<Rational> last_key_time_;
    std::map<std::array<int64_t, 4>, std::string> previous_hashes_;
    bool have_hashes_ = false;
    std::deque<casunat2::Chunk> pending_;
};

class AudioStreamProvider {
public:
    AudioStreamProvider(const std::string& source, int64_t stream_id,
                        int relative_index, const JsonObject& stream,
                        std::vector<JsonValue> frames)
        : pipe_(source, relative_index, channels_of(stream),
                sample_rate_of(stream)),
          stream_id_(stream_id),
          frames_(std::move(frames)),
          stream_(stream) {
        auto tb_field = stream_.items.count("time_base")
                            ? stream_.items.at("time_base")
                            : JsonValue{};
        std::tie(tb_num_, tb_den_) =
            fraction_pair(coerce_text(tb_field.is_null() ? nullptr : &tb_field));
        if (auto layout = stream_.items.find("channel_layout");
            layout != stream_.items.end())
            channel_layout_ = coerce_text(&layout->second);
    }

    ~AudioStreamProvider() {
        if (!finished_) {
            try { pipe_.finish(false); } catch (...) {}
        }
    }

    std::optional<casunat2::Chunk> next() {
        if (done_) return std::nullopt;
        if (index_ >= frames_.size()) {
            done_ = true;
            const bool extra = !pipe_.drain_one_byte().empty();
            pipe_.finish(false);
            finished_ = true;
            if (extra)
                fail("audio decoder produced more samples than its frame "
                     "inventory");
            return std::nullopt;
        }
        const JsonValue& info = frames_[index_++];
        const JsonValue* pts_value = info.find("best_effort_timestamp");
        if (!pts_value || pts_value->is_null()) pts_value = info.find("pts");
        const auto pts = to_int(pts_value);
        const auto samples = to_int(info.find("nb_samples")).value_or(0);
        if (!pts || samples <= 0)
            fail("decoded audio frame lacks PTS/sample count");
        const auto channels = channels_of(stream_);
        const int64_t length = samples * channels * 2;
        const std::vector<uint8_t> pcm = pipe_.read_exact(length);
        casunat2::Chunk chunk;
        chunk.chunk_type = casunat2::AUDIO_BLOCK;
        chunk.stream_id = static_cast<uint8_t>(stream_id_);
        chunk.pts = *pts;
        chunk.payload = natv2::encode_audio_block(
            pcm, *pts, tb_num_, tb_den_,
            sample_rate_of(stream_), channels, "s16le",
            channel_layout_.empty() ? nullptr : channel_layout_.c_str(),
            samples);
        return chunk;
    }

private:
    static int64_t sample_rate_of(const JsonObject& s) {
        return to_int(s.items.count("sample_rate")
                          ? &s.items.at("sample_rate")
                          : nullptr)
            .value_or(0);
    }
    static int64_t channels_of(const JsonObject& s) {
        return to_int(s.items.count("channels") ? &s.items.at("channels")
                                                : nullptr)
            .value_or(0);
    }
    AudioPipe pipe_;
    int64_t stream_id_;
    std::vector<JsonValue> frames_;
    JsonObject stream_;
    int64_t tb_num_ = 0;
    int64_t tb_den_ = 0;
    std::string channel_layout_;
    std::size_t index_ = 0;
    bool done_ = false;
    bool finished_ = false;
};

// Pull-chain over a list of providers.
class ChainProvider {
public:
    void add(ChunkProvider provider) { links_.push_back(std::move(provider)); }
    std::optional<casunat2::Chunk> next() {
        while (position_ < links_.size()) {
            auto chunk = links_[position_]();
            if (chunk.has_value()) return chunk;
            ++position_;
        }
        return std::nullopt;
    }

private:
    std::vector<ChunkProvider> links_;
    std::size_t position_ = 0;
};

// _bitmap_canvas_size port.
std::optional<std::pair<int64_t, int64_t>> bitmap_canvas_size(
    const JsonObject& stream, const JsonValue& overview) {
    const auto width = to_int(stream.items.count("width")
                                  ? &stream.items.at("width")
                                  : nullptr).value_or(0);
    const auto height = to_int(stream.items.count("height")
                                   ? &stream.items.at("height")
                                   : nullptr).value_or(0);
    if (width > 0 && height > 0) return std::make_pair(width, height);
    const JsonValue* streams = overview.find("streams");
    JsonObject video;
    if (streams && streams->is_array()) {
        for (const JsonValue& item : streams->as_array().items) {
            if (!item.is_object()) continue;
            const std::string kind = json_str_or(item.find("codec_type"), "");
            const JsonValue* disp = item.find("disposition");
            const bool attached_pic =
                disp && disp->is_object() &&
                truthy(disp->find("attached_pic"));
            if (kind == "video" && !attached_pic) {
                video = item.as_object();
                break;
            }
        }
    }
    std::string codec = json_str_or(stream.items.count("codec_name")
                                        ? &stream.items.at("codec_name")
                                        : nullptr,
                                    "");
    std::transform(codec.begin(), codec.end(), codec.begin(),
                   [](unsigned char c) { return char(std::tolower(c)); });
    if (codec == "dvd_subtitle") {
        const auto video_height =
            to_int(video.items.count("height") ? &video.items.at("height")
                                               : nullptr).value_or(0);
        Rational rate{0, 1};
        try {
            const std::string text = json_str_or(
                video.items.count("avg_frame_rate")
                    ? &video.items.at("avg_frame_rate")
                    : nullptr,
                "0/1");
            rate = Rational::parse(text.empty() ? "0/1" : text);
        } catch (const CasuError&) {
            rate = Rational{0, 1};
        }
        if (video_height == 240 || video_height == 480 ||
            rate > Rational{27, 1})  // reference compares rate > 27 exactly
            return std::make_pair(int64_t(720), int64_t(480));
        return std::make_pair(int64_t(720), int64_t(576));
    }
    const auto vw = to_int(video.items.count("width")
                               ? &video.items.at("width")
                               : nullptr).value_or(0);
    const auto vh = to_int(video.items.count("height")
                               ? &video.items.at("height")
                               : nullptr).value_or(0);
    if (vw > 0 && vh > 0) return std::make_pair(vw, vh);
    return std::nullopt;
}

}  // anonymous helper scope
}  // anonymous helper scope
}  // anonymous helper scope
}  // anonymous helper scope
}  // anonymous helper scope

// --- main conversion -----------------------------------------------------------
std::string convert_media_to_native_v2(const std::string& source,
                                       const std::string& target,
                                       const NativeConvertOptions& options,
                                       const ProgressFn& progress) {
    auto notify = [&](double value) {
        if (progress)
            progress(std::max(0.0, std::min(1.0, value)));
    };
    if (casu::codec::ffmpeg_path().empty() || casu::codec::ffprobe_path().empty())
        fail("ffmpeg and ffprobe are required");
    std::error_code fec;
    fs::path src = fs::weakly_canonical(fs::path(source), fec);
    if (fec) src = fs::path(source);
    if (!fs::is_regular_file(src, fec))
        fail("source does not exist: " + src.string());
    if (options.tile_width <= 0 || options.tile_height <= 0 ||
        !(options.max_key_interval_seconds > 0.0))
        fail("tile dimensions and key interval must be positive");
    notify(0.0);
    const JsonValue overview = run_probe_json({
        "-v", "error", "-show_streams", "-show_format", "-show_chapters",
        "-of", "json", src.string()});
    notify(0.05);

    // Stream classification with per-kind relative indices.
    struct Classified {
        JsonObject stream;
        std::string kind;  // video|audio|subtitle|attachment|cover-art
        int relative = 0;
    };
    std::vector<Classified> source_streams;
    std::map<std::string, int> relative_seen{
        {"video", 0}, {"audio", 0}, {"subtitle", 0}, {"attachment", 0}};
    const JsonValue* overview_streams = overview.find("streams");
    if (!overview_streams || !overview_streams->is_array())
        fail("media probe failed");
    for (const JsonValue& value : overview_streams->as_array().items) {
        if (!value.is_object()) continue;
        const std::string source_kind =
            json_str_or(value.find("codec_type"), "");
        if (!relative_seen.count(source_kind)) continue;
        const int relative = relative_seen[source_kind];
        relative_seen[source_kind] = relative + 1;
        bool attached_pic = false;
        if (const JsonValue* disp = value.find("disposition");
            disp && disp->is_object())
            attached_pic = truthy(disp->find("attached_pic"));
        const std::string kind =
            (source_kind == "video" && attached_pic) ? "cover-art"
                                                     : source_kind;
        source_streams.push_back({value.as_object(), kind, relative});
    }
    {
        bool decodable = false;
        for (const Classified& c : source_streams)
            if (c.kind == "video" || c.kind == "audio") decodable = true;
        if (!decodable)
            fail("source has no decodable video or audio stream");
    }

    std::vector<JsonValue> descriptors;
    std::vector<JsonValue> ignored_streams;
    std::map<int64_t, std::vector<JsonValue>> inventories;
    struct Mapping {
        int64_t stream_id = 0;
        std::string kind;
        int relative = 0;
        JsonObject effective;
    };
    std::vector<Mapping> mappings;

    int64_t stream_id = 0;
    for (const Classified& classified : source_streams) {
        ++stream_id;
        JsonObject probed;
        std::vector<JsonValue> frames;
        if (classified.kind == "video" || classified.kind == "audio") {
            auto inv = inventory(
                src.string(),
                std::string(1, classified.kind[0]) + ":" +
                    std::to_string(classified.relative));
            probed = std::move(inv.first);
            frames = std::move(inv.second);
        } else {
            probed = classified.stream;  // subtitle/attachment/cover-art
        }
        // effective = dict(stream); update(probed)
        JsonObject effective = classified.stream;
        for (const auto& [k, v] : probed.items) effective.items[k] = v;
        if (classified.kind == "audio") {
            const auto rate = to_int(effective.items.count("sample_rate")
                                         ? &effective.items.at("sample_rate")
                                         : nullptr).value_or(0);
            const auto chans =
                to_int(effective.items.count("channels")
                           ? &effective.items.at("channels")
                           : nullptr).value_or(0);
            if (rate <= 0 || chans <= 0) {
                auto entry = std::make_shared<JsonObject>();
                entry->items["source_index"] = JsonValue(to_int(
                    effective.items.count("index")
                        ? &effective.items.at("index")
                        : nullptr).value_or(classified.relative));
                entry->items["type"] = JsonValue(std::string("audio"));
                entry->items["codec_origin"] =
                    JsonValue(json_str_or(effective.items.count("codec_name")
                                              ? &effective.items.at("codec_name")
                                              : nullptr,
                                          ""));
                entry->items["reason"] = JsonValue(std::string(
                    "decoder reported no usable sample rate/channels"));
                ignored_streams.push_back(JsonValue(entry));
                continue;
            }
        }
        inventories[stream_id] = frames;
        auto descriptor = std::make_shared<JsonObject>();
        descriptor->items["stream_id"] = JsonValue(stream_id);
        descriptor->items["type"] = JsonValue(
            classified.kind == "cover-art" ? std::string("attachment")
                                           : classified.kind);
        descriptor->items["source_index"] = JsonValue(to_int(
            effective.items.count("index") ? &effective.items.at("index")
                                           : nullptr).value_or(classified.relative));
        descriptor->items["codec_origin"] =
            effective.items.count("codec_name")
                ? effective.items.at("codec_name")
                : JsonValue(nullptr);
        JsonValue time_base_value;
        if (classified.kind == "subtitle") {
            time_base_value = make_array({JsonValue(int64_t(1)),
                                          JsonValue(int64_t(1000))});
        } else if (classified.kind == "attachment" ||
                   classified.kind == "cover-art") {
            time_base_value = make_array(
                {JsonValue(int64_t(1)), JsonValue(int64_t(1))});
        } else {
            const auto [n, d] = fraction_pair(json_str_or(
                probed.items.count("time_base") ? &probed.items.at("time_base")
                                                : nullptr,
                ""));
            time_base_value = make_array({JsonValue(n), JsonValue(d)});
        }
        descriptor->items["time_base"] = time_base_value;
        const JsonValue* tags = effective.items.count("tags")
                                    ? &effective.items.at("tags")
                                    : nullptr;
        descriptor->items["language"] =
            tags && tags->is_object() && tags->find("language")
                ? *tags->find("language")
                : JsonValue(nullptr);
        bool default_flag = false;
        bool forced_flag = false;
        if (const JsonValue* disp = effective.items.count("disposition")
                                        ? &effective.items.at("disposition")
                                        : nullptr;
            disp && disp->is_object()) {
            default_flag = truthy(disp->find("default"));
            forced_flag = truthy(disp->find("forced"));
        }
        descriptor->items["default"] = JsonValue(default_flag);
        descriptor->items["forced"] = JsonValue(forced_flag);
        {
            auto timeline = std::make_shared<JsonArray>();
            timeline->items = frame_pts_list(
                frames.empty() ? JsonArray{} : JsonArray{frames});
            descriptor->items["frame_timeline"] = JsonValue(timeline);
        }
        descriptor->items["disposition"] = disposition_value(
            effective.items.count("disposition")
                ? &effective.items.at("disposition")
                : nullptr);
        descriptor->items["tags"] = bounded_tags(tags);
        if (classified.kind == "cover-art")
            descriptor->items["role"] = JsonValue(std::string("cover-art"));
        std::string codec_lower = json_str_or(
            effective.items.count("codec_name")
                ? &effective.items.at("codec_name")
                : nullptr,
            "");
        std::transform(codec_lower.begin(), codec_lower.end(),
                       codec_lower.begin(),
                       [](unsigned char c) { return char(std::tolower(c)); });
        if (classified.kind == "subtitle" &&
            (codec_lower == "ass" || codec_lower == "ssa")) {
            descriptor->items["rich_source_attachment"] = JsonValue(true);
            descriptor->items["playback_fallback"] =
                JsonValue(std::string("utf8-webvtt-text"));
        }
        static const std::set<std::string> bitmap_codecs = {
            "hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"};
        if (classified.kind == "subtitle" && bitmap_codecs.count(codec_lower)) {
            descriptor->items["canonical_format"] =
                JsonValue(std::string("rgba-bitmap-region"));
            const auto canvas = bitmap_canvas_size(effective, overview);
            if (canvas.has_value()) {
                descriptor->items["canvas_size"] = make_array(
                    {JsonValue(canvas->first), JsonValue(canvas->second)});
            }
        }
        for (const char* key :
             {"width", "height", "pix_fmt", "color_range", "color_space",
              "color_transfer", "color_primaries", "chroma_location",
              "sample_rate", "channels", "channel_layout"}) {
            if (effective.items.count(key) &&
                !effective.items.at(key).is_null())
                descriptor->items[key] = effective.items.at(key);
        }
        descriptors.push_back(JsonValue(descriptor));
        mappings.push_back(
            {stream_id, classified.kind, classified.relative,
             std::move(effective)});
        notify(0.05 + 0.15 * static_cast<double>(stream_id) /
                         static_cast<double>(source_streams.size()));
    }

    bool usable = false;
    for (const JsonValue& d : descriptors) {
        const std::string type = json_str_or(d.find("type"), "");
        if (type == "video" || type == "audio") usable = true;
    }
    if (!usable) fail("source has no usable video or audio stream");

    double duration_s = 0.0;
    if (const JsonValue* format = overview.find("format");
        format && format->is_object()) {
        if (auto dur = to_int(format->find("duration")); dur)
            duration_s = static_cast<double>(*dur);
        else if (const JsonValue* dv = format->find("duration");
                 dv && dv->is_double())
            duration_s = dv->as_double();
        else if (const JsonValue* sv = format->find("duration");
                 sv && sv->is_string())
            try { duration_s = std::stod(sv->as_string()); } catch (...) {}
    }
    uint64_t size_bytes = 0;
    std::error_code ec;
    auto st = fs::status(src, ec);
    if (!ec && fs::exists(st)) size_bytes = fs::file_size(src, ec);

    auto manifest_obj = std::make_shared<JsonObject>();
    manifest_obj->items["format"] = JsonValue(std::string("CASUNAT2"));
    manifest_obj->items["version"] = JsonValue(int64_t(2));
    {
        auto provenance = std::make_shared<JsonObject>();
        provenance->items["filename"] = JsonValue(src.filename().string());
        provenance->items["size_bytes"] =
            JsonValue(static_cast<int64_t>(size_bytes));
        provenance->items["sha256"] = JsonValue(casu::sha256_file(src.string()));
        provenance->items["duration_s"] = JsonValue(duration_s);
        manifest_obj->items["source_provenance"] =
            JsonValue(std::move(provenance));
    }
    manifest_obj->items["metadata"] = bounded_tags(
        overview.find("format") && overview.find("format")->is_object()
            ? overview.find("format")->find("tags")
            : nullptr);
    {
        auto arr = std::make_shared<JsonArray>();
        arr->items = ignored_streams;
        manifest_obj->items["ignored_streams"] = JsonValue(arr);
    }
    {
        auto arr = std::make_shared<JsonArray>();
        arr->items = descriptors;
        manifest_obj->items["streams"] = JsonValue(arr);
    }
    {
        auto policy = std::make_shared<JsonObject>();
        policy->items["fidelity"] =
            JsonValue(std::string("SOURCE_RESOLUTION_STRICT"));
        policy->items["tile_size"] = make_array(
            {JsonValue(options.tile_width), JsonValue(options.tile_height)});
        policy->items["max_key_interval_seconds"] =
            JsonValue(options.max_key_interval_seconds);
        manifest_obj->items["video_policy"] = JsonValue(policy);
    }
    {
        auto policy = std::make_shared<JsonObject>();
        policy->items["canonical_format"] =
            JsonValue(std::string("s16le"));
        policy->items["timing"] = JsonValue(std::string("source PTS"));
        manifest_obj->items["audio_policy"] = JsonValue(policy);
    }
    {
        auto policy = std::make_shared<JsonObject>();
        policy->items["canonical_format"] =
            JsonValue(std::string("utf8-webvtt-text"));
        policy->items["time_base"] = make_array(
            {JsonValue(int64_t(1)), JsonValue(int64_t(1000))});
        manifest_obj->items["subtitle_policy"] = JsonValue(policy);
    }
    manifest_obj->items["chapter_time_base"] = make_array(
        {JsonValue(int64_t(1)), JsonValue(int64_t(1'000'000'000))});

    // Chunk providers in the exact reference order.
    ChainProvider chain;
    if (auto chapters_field = overview.find("chapters");
        chapters_field && chapters_field->is_array() &&
        !chapters_field->as_array().items.empty()) {
        auto chapter_opt = chapter_chunk(chapters_field->as_array());
        if (chapter_opt.has_value()) {
            casunat2::Chunk chunk = std::move(*chapter_opt);
            chain.add([chunk]() -> std::optional<casunat2::Chunk> {
                return chunk;
            });
        }
    }
    const std::size_t mapping_count = mappings.size();
    std::size_t mapping_number = 0;
    for (const Mapping& mapping : mappings) {
        notify(0.20 + 0.75 * static_cast<double>(mapping_number) /
                         static_cast<double>(mapping_count));
        const int64_t sid = mapping.stream_id;
        if (mapping.kind == "video") {
            auto provider = std::make_shared<VideoStreamProvider>(
                src.string(), sid, mapping.relative,
                Rational::parse([](double v) {
                    std::ostringstream ss;
                    ss << std::fixed << std::setprecision(6) << v;
                    std::string s = ss.str();
                    while (s.back() == '0') s.pop_back();
                    if (s.back() == '.') s.push_back('0');
                    return s;
                }(options.max_key_interval_seconds)),
                options.tile_width, options.tile_height);
            chain.add([provider]() { return provider->next(); });
        } else if (mapping.kind == "audio") {
            auto provider = std::make_shared<AudioStreamProvider>(
                src.string(), sid, mapping.relative, mapping.effective,
                inventories.at(sid));
            chain.add([provider]() { return provider->next(); });
        } else if (mapping.kind == "subtitle") {
            std::string codec_lower = json_str_or(
                mapping.effective.items.count("codec_name")
                    ? &mapping.effective.items.at("codec_name")
                    : nullptr,
                "");
            std::transform(codec_lower.begin(), codec_lower.end(),
                           codec_lower.begin(),
                           [](unsigned char c) {
                               return char(std::tolower(c));
                           });
            static const std::set<std::string> bitmap_codecs = {
                "hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"};
            if (bitmap_codecs.count(codec_lower)) {
                auto chunks_vec = std::make_shared<
                    std::vector<casunat2::Chunk>>(bitmap_subtitle_chunks(
                    src.string(), sid, mapping.relative, duration_s,
                    bitmap_canvas_size(mapping.effective, overview)));
                auto index = std::make_shared<std::size_t>(0);
                chain.add([chunks_vec, index]()
                              -> std::optional<casunat2::Chunk> {
                    if (*index >= chunks_vec->size()) return std::nullopt;
                    return (*chunks_vec)[(*index)++];
                });
            } else {
                std::string language = "und";
                if (auto t = mapping.effective.items.find("tags");
                    t != mapping.effective.items.end() &&
                    t->second.is_object()) {
                    language = coerce_text(t->second.find("language"));
                    if (language.empty()) language = "und";
                }
                auto rich = std::make_shared<
                    std::optional<casunat2::Chunk>>(
                    rich_subtitle_source_chunk(src.string(), sid,
                                               mapping.relative,
                                               mapping.effective));
                auto cues = std::make_shared<std::vector<casunat2::Chunk>>(
                    text_subtitle_chunks(src.string(), sid, mapping.relative,
                                         language));
                auto index = std::make_shared<std::size_t>(0);
                chain.add([rich, cues, index]()
                              -> std::optional<casunat2::Chunk> {
                    if (rich->has_value()) {
                        casunat2::Chunk out_chunk =
                            std::move(**rich);
                        rich->reset();
                        return out_chunk;
                    }
                    if (*index >= cues->size()) return std::nullopt;
                    return (*cues)[(*index)++];
                });
            }
        } else if (mapping.kind == "cover-art") {
            const int64_t source_index = to_int(
                mapping.effective.items.count("index")
                    ? &mapping.effective.items.at("index")
                    : nullptr).value_or(mapping.relative);
            chain.add([=]() -> std::optional<casunat2::Chunk> {
                return cover_art_chunk(src.string(), sid, source_index,
                                       mapping.effective);
            });
        } else {
            chain.add([=]() -> std::optional<casunat2::Chunk> {
                return attachment_chunk(src.string(), sid, mapping.relative,
                                        mapping.effective);
            });
        }
        ++mapping_number;
        notify(0.20 + 0.75 * static_cast<double>(mapping_number) /
                         static_cast<double>(mapping_count));
    }

    const std::string result = casunat2::write_native_v2_streamed(
        target, JsonValue(manifest_obj),
        [&chain]() { return chain.next(); }, options.recovery_interval);
    notify(1.0);
    return result;
}
}  // namespace casu::natconv
