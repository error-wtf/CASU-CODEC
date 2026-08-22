// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Full port of casu/strict/decoder.py (ffmpeg CLI adapter) + model.py time
// helpers. Byte-parity notes: the probe/decode command lines, the fail-closed
// format table and the error messages mirror the reference exactly.
#include "casu/codec/strict_frames.hpp"

#include "casu/codec/tools.hpp"

#include <QProcess>
#include <QTemporaryFile>

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <numeric>
#include <sstream>

namespace casu::strict {

using natv2::CanonicalFrame;
using natv2::CanonicalPlane;

namespace {

[[noreturn]] void fail(const std::string& msg) { throw StrictDecoderError(msg); }

std::string json_to_str(const JsonValue* v) {
    if (!v || v->is_null()) return {};
    switch (v->kind()) {
        case JsonValue::Kind::String: return v->as_string();
        case JsonValue::Kind::Int: return std::to_string(v->as_int());
        case JsonValue::Kind::Bool: return v->as_bool() ? "True" : "False";
        case JsonValue::Kind::Double: {
            std::ostringstream ss;
            ss << v->as_double();
            return ss.str();
        }
        default: return {};
    }
}

std::optional<int64_t> json_to_int(const JsonValue* v) {
    if (!v || v->is_null()) return std::nullopt;
    if (v->is_int()) return v->as_int();
    if (v->is_double())
        return static_cast<int64_t>(v->as_double());
    const std::string s = json_to_str(v);
    try {
        std::size_t consumed = 0;
        const long long parsed = std::stoll(s, &consumed, 10);
        if (consumed != s.size()) return std::nullopt;
        return static_cast<int64_t>(parsed);
    } catch (const std::exception&) {
        return std::nullopt;
    }
}

struct PlaneDim {
    int64_t height = 0;
    int64_t width = 0;  // in samples (components included)
};

struct FormatEntry {
    int bytes_per_sample = 1;
    // Plane dims as functions of (w, h), mirroring the _FORMATS lambdas.
    bool gray = false;          // single (h, w) plane
    bool packed3 = false;       // (h, w*3)
    bool packed4 = false;       // (h, w*4)
    bool yuv420 = false;        // (h,w) + 2x ((h+1)/2,(w+1)/2)
    bool yuv422 = false;        // (h,w) + 2x (h,(w+1)/2)
    bool yuv444 = false;        // 3x (h,w)
    bool yuva420 = false;       // yuv420 + (h,w) alpha
    bool gbrp = false;          // 3x (h,w)
};

const std::map<std::string, FormatEntry>& format_table() {
    static const std::map<std::string, FormatEntry> table = {
        {"gray", {1, true, false, false, false, false, false, false, false}},
        {"gray8", {1, true, false, false, false, false, false, false, false}},
        {"gray16le", {2, true, false, false, false, false, false, false, false}},
        {"rgb24", {1, false, true, false, false, false, false, false, false}},
        {"bgr24", {1, false, true, false, false, false, false, false, false}},
        {"rgba", {1, false, false, true, false, false, false, false, false}},
        {"bgra", {1, false, false, true, false, false, false, false, false}},
        {"argb", {1, false, false, true, false, false, false, false, false}},
        {"abgr", {1, false, false, true, false, false, false, false, false}},
        {"yuv420p", {1, false, false, false, true, false, false, false, false}},
        {"yuv420p10le", {2, false, false, false, true, false, false, false, false}},
        {"yuv420p12le", {2, false, false, false, true, false, false, false, false}},
        {"yuv420p16le", {2, false, false, false, true, false, false, false, false}},
        {"yuv422p", {1, false, false, false, false, true, false, false, false}},
        {"yuv422p10le", {2, false, false, false, false, true, false, false, false}},
        {"yuv422p12le", {2, false, false, false, false, true, false, false, false}},
        {"yuv422p16le", {2, false, false, false, false, true, false, false, false}},
        {"yuva420p", {1, false, false, false, false, false, false, true, false}},
        {"yuva420p10le", {2, false, false, false, false, false, false, true, false}},
        {"yuva420p12le", {2, false, false, false, false, false, false, true, false}},
        {"yuva420p16le", {2, false, false, false, false, false, false, true, false}},
        {"yuv444p", {1, false, false, false, false, false, true, false, false}},
        {"yuv444p10le", {2, false, false, false, false, false, true, false, false}},
        {"yuv444p12le", {2, false, false, false, false, false, true, false, false}},
        {"yuv444p16le", {2, false, false, false, false, false, true, false, false}},
        {"gbrp", {1, false, false, false, false, false, false, false, true}},
        {"gbrp10le", {2, false, false, false, false, false, false, false, true}},
        {"gbrp12le", {2, false, false, false, false, false, false, false, true}},
        {"gbrp16le", {2, false, false, false, false, false, false, false, true}},
        {"rgba64le", {2, false, false, true, false, false, false, false, false}},
    };
    return table;
}

std::vector<PlaneDim> plane_dims(const FormatEntry& entry, int64_t w, int64_t h) {
    std::vector<PlaneDim> planes;
    if (entry.gray) {
        planes.push_back({h, w});
    } else if (entry.packed3) {
        planes.push_back({h, w * 3});
    } else if (entry.packed4) {
        planes.push_back({h, w * 4});
    } else if (entry.yuv420) {
        planes.push_back({h, w});
        planes.push_back({(h + 1) / 2, (w + 1) / 2});
        planes.push_back({(h + 1) / 2, (w + 1) / 2});
    } else if (entry.yuv422) {
        planes.push_back({h, w});
        planes.push_back({h, (w + 1) / 2});
        planes.push_back({h, (w + 1) / 2});
    } else if (entry.yuv444 || entry.gbrp) {
        planes.push_back({h, w});
        planes.push_back({h, w});
        planes.push_back({h, w});
    } else if (entry.yuva420) {
        planes.push_back({h, w});
        planes.push_back({(h + 1) / 2, (w + 1) / 2});
        planes.push_back({(h + 1) / 2, (w + 1) / 2});
        planes.push_back({h, w});
    }
    return planes;
}

int64_t frame_bytes_of(const FormatEntry& entry, int64_t w, int64_t h) {
    int64_t total = 0;
    for (const PlaneDim& p : plane_dims(entry, w, h))
        total += p.height * p.width * entry.bytes_per_sample;
    return total;
}

JsonValue run_ffprobe_json(const std::vector<std::string>& args) {
    QProcess proc;
    const QString program = QString::fromStdString(
        casu::codec::ffprobe_path().empty() ? std::string("ffprobe")
                                            : casu::codec::ffprobe_path());
    QStringList qargs;
    for (const auto& a : args) qargs << QString::fromStdString(a);
    proc.start(program, qargs);
    if (!proc.waitForStarted(10000))
        fail("unable to probe source video");
    QByteArray out;
    while (proc.waitForReadyRead(30000) || proc.bytesAvailable() > 0 ||
           proc.state() == QProcess::Running) {
        out += proc.readAllStandardOutput();
        if (proc.state() != QProcess::Running && proc.bytesAvailable() == 0)
            break;
    }
    proc.waitForFinished(60000);
    if (proc.exitCode() != 0)
        fail("unable to probe source video");
    try {
        return parse_json(out.toStdString());
    } catch (const JsonError&) {
        fail("unable to probe source video");
    }
}

}  // namespace

// ---------------------------------------------------------------------------
// Rational
// ---------------------------------------------------------------------------
Rational Rational::parse(const std::string& text) {
    try {
        const std::size_t slash = text.find('/');
        if (slash != std::string::npos) {
            const int64_t n = std::stoll(text.substr(0, slash));
            const int64_t d = std::stoll(text.substr(slash + 1));
            if (d <= 0) throw std::invalid_argument("den");
            return Rational{n, d};
        }
        const std::size_t dot = text.find('.');
        if (dot == std::string::npos)
            return Rational{std::stoll(text), 1};
        const int64_t whole = std::stoll(text.substr(0, dot));
        std::string frac = text.substr(dot + 1);
        // Strip trailing zeros the way Fraction(str(x)) normalizes.
        while (!frac.empty() && frac.back() == '0') frac.pop_back();
        if (frac.empty()) return Rational{whole, 1};
        int64_t den = 1;
        for (std::size_t i = 0; i < frac.size(); ++i) den *= 10;
        const int64_t num = std::stoll(frac);
        Rational value{whole * den + num, den};
        const int64_t g = std::gcd(value.num < 0 ? -value.num : value.num,
                                   value.den);
        if (g > 1) {
            value.num /= g;
            value.den /= g;
        }
        return value;
    } catch (const std::exception&) {
        fail("invalid rational value: " + text);
    }
}

bool Rational::operator<(const Rational& o) const {
    __int128 lhs = static_cast<__int128>(num) * o.den;
    __int128 rhs = static_cast<__int128>(o.num) * den;
    return lhs < rhs;
}

bool Rational::operator>=(const Rational& o) const { return !(*this < o); }

double StrictFrame::timestamp_s() const {
    return static_cast<double>(pts * time_base_num) /
           static_cast<double>(time_base_den);
}

// ---------------------------------------------------------------------------
// FrameSource
// ---------------------------------------------------------------------------
struct FrameSource::Impl {
    struct ProbeResult {
        FormatEntry entry;
        std::string pixel_format;
        int64_t width = 0;
        int64_t height = 0;
        int64_t tb_num = 0;
        int64_t tb_den = 0;
        JsonArray frames;
        JsonObject stream;
    };

    Impl(const std::string& path, int stream_index,
         std::optional<int64_t> max_frames)
        : source(path), max_frames_(max_frames) {
        probe(stream_index);
        start_decoder(stream_index);
    }

    void probe(int stream_index) {
        const std::string selector = "v:" + std::to_string(stream_index);
        JsonValue data = run_ffprobe_json({
            "-v", "error", "-select_streams", selector, "-show_entries",
            "stream=width,height,pix_fmt,time_base,color_space,color_transfer,"
            "color_primaries,color_range,chroma_location:"
            "frame=best_effort_timestamp,pts,pkt_duration,duration,width,"
            "height,pix_fmt,color_space,color_transfer,color_primaries,"
            "color_range,chroma_location",
            "-of", "json", source,
        });
        const JsonValue* streams = data.find("streams");
        if (!streams || !streams->is_array() ||
            streams->as_array().items.empty())
            fail("source has no selected video stream");
        const JsonValue& stream_value = streams->as_array().items[0];
        if (!stream_value.is_object())
            fail("source has no selected video stream");
        const JsonObject& stream = stream_value.as_object();
        auto width_field = stream_value.find("width");
        auto height_field = stream_value.find("height");
        auto pix_field = stream_value.find("pix_fmt");
        const int64_t width = json_to_int(width_field).value_or(0);
        const int64_t height = json_to_int(height_field).value_or(0);
        const std::string pix_fmt =
            pix_field && pix_field->is_string() ? pix_field->as_string() : "";
        auto it = format_table().find(pix_fmt);
        if (width <= 0 || height <= 0 || it == format_table().end())
            fail("unsupported native source format: '" + pix_fmt + "' " +
                 std::to_string(width) + "x" + std::to_string(height));
        probed.entry = it->second;
        probed.pixel_format = pix_fmt;
        probed.width = width;
        probed.height = height;
        if (width > 32768 || height > 32768 ||
            frame_bytes_of(probed.entry, width, height) >
                512LL * 1024 * 1024)
            fail("source video exceeds decoded frame resource limits");
        auto tb_field = stream_value.find("time_base");
        const std::string time_base =
            tb_field && tb_field->is_string() ? tb_field->as_string() : "0/1";
        const std::size_t slash = time_base.find('/');
        if (slash == std::string::npos)
            fail("source stream has invalid time base");
        probed.tb_num = std::atoll(time_base.substr(0, slash).c_str());
        probed.tb_den = std::atoll(time_base.substr(slash + 1).c_str());
        if (probed.tb_den <= 0)
            fail("source stream has invalid time base");
        if (auto frames = data.find("frames"); frames && frames->is_array())
            probed.frames = frames->as_array();
        probed.stream = stream;
        stream_value.as_object();  // keep reference semantics clear
    }

    void start_decoder(int stream_index) {
        const FormatEntry& entry = probed.entry;
        QStringList args{
            QStringLiteral("-v"), QStringLiteral("error"),
            QStringLiteral("-i"), QString::fromStdString(source),
            QString::fromStdString("-map"),
            QString::fromStdString("0:v:" + std::to_string(stream_index)),
            QStringLiteral("-an"), QStringLiteral("-sn"), QStringLiteral("-dn"),
            // Passthrough frame timing (identical semantics to the
            // reference's deprecated -vsync 0).
            QStringLiteral("-fps_mode"), QStringLiteral("passthrough"),
            QStringLiteral("-f"), QStringLiteral("rawvideo"),
            QStringLiteral("-pix_fmt"),
            QString::fromStdString(probed.pixel_format),
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
            fail("source decoder failed: could not open FFmpeg process");
        frame_bytes_ = static_cast<std::size_t>(
            frame_bytes_of(entry, probed.width, probed.height));
    }

    bool next(StrictFrame& out) {
        if (stopped_early_) return false;
        if (index_ >= static_cast<int64_t>(probed.frames.items.size()))
            return finish(false);
        if (max_frames_.has_value() && index_ >= *max_frames_) {
            stopped_early_ = true;
            return false;
        }
        const JsonValue& info = probed.frames.items[index_];
        ++index_;
        if (!info.is_object()) fail("decoder inventory entry is invalid");
        const FormatEntry& entry = probed.entry;
        const auto fw = json_to_int(info.find("width"))
                            .value_or(probed.width);
        const auto fh = json_to_int(info.find("height"))
                            .value_or(probed.height);
        auto pf = info.find("pix_fmt");
        const std::string fpf = pf && pf->is_string()
                                    ? pf->as_string()
                                    : probed.pixel_format;
        if (fw != probed.width || fh != probed.height ||
            fpf != probed.pixel_format)
            fail("mid-stream native format change requires a decoder "
                 "restart/key state");

        std::vector<uint8_t> payload(frame_bytes_);
        std::size_t filled = 0;
        while (filled < frame_bytes_) {
            const QByteArray chunk =
                process_.read(static_cast<qint64>(frame_bytes_ - filled));
            if (!chunk.isEmpty()) {
                std::memcpy(payload.data() + filled, chunk.constData(),
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
        if (filled != frame_bytes_)
            fail("decoder ended before a complete source frame");

        const std::vector<PlaneDim> dims =
            plane_dims(entry, probed.width, probed.height);
        std::vector<CanonicalPlane> planes;
        std::size_t offset = 0;
        for (const PlaneDim& dim : dims) {
            CanonicalPlane plane;
            plane.rows = dim.height;
            plane.cols = dim.width;
            plane.itemsize = entry.bytes_per_sample;
            const std::size_t count =
                static_cast<std::size_t>(dim.height * dim.width) *
                static_cast<std::size_t>(entry.bytes_per_sample);
            plane.data.assign(payload.begin() +
                                  static_cast<std::ptrdiff_t>(offset),
                              payload.begin() +
                                  static_cast<std::ptrdiff_t>(offset + count));
            offset += count;
            planes.push_back(std::move(plane));
        }

        auto pts_value = info.find("best_effort_timestamp");
        if (!pts_value || pts_value->is_null())
            pts_value = info.find("pts");
        const auto pts = json_to_int(pts_value);
        if (!pts) fail("source frame has no presentation timestamp");
        std::map<std::string, std::string> metadata;
        for (const char* key : {"color_space", "color_transfer",
                                "color_primaries", "color_range",
                                "chroma_location"}) {
            const JsonValue* frame_value = info.find(key);
            const JsonValue* stream_value = probed.stream.items.count(key)
                                                ? &probed.stream.items.at(key)
                                                : nullptr;
            const JsonValue* chosen =
                frame_value && !frame_value->is_null() ? frame_value
                                                       : stream_value;
            const std::string text = chosen ? json_to_str(chosen) : "";
            if (!text.empty()) metadata[key] = text;
        }
        auto duration_field = info.find("pkt_duration");
        if (!duration_field || duration_field->is_null())
            duration_field = info.find("duration");
        std::optional<int64_t> duration_pts;
        if (duration_field && !duration_field->is_null()) {
            if (duration_field->is_string() &&
                duration_field->as_string() == "N/A") {
                duration_pts = std::nullopt;
            } else {
                duration_pts = json_to_int(duration_field);
            }
        }

        CanonicalFrame frame = natv2::canonical_frame(
            std::move(planes), probed.pixel_format, metadata,
            std::make_optional(std::make_pair(probed.height, probed.width)));
        out.pts = *pts;
        out.time_base_num = probed.tb_num;
        out.time_base_den = probed.tb_den;
        out.frame = std::move(frame);
        out.duration_pts = duration_pts;
        return true;
    }

    bool finish(bool early) {
        stopped_early_ = stopped_early_ || early;
        if (process_.state() == QProcess::Running) {
            process_.closeWriteChannel();
            process_.terminate();
            if (!process_.waitForFinished(5000)) process_.kill();
            process_.waitForFinished(5000);
        }
        error_file_.flush();
        QFile ef(error_file_.fileName());
        std::string error;
        if (ef.open(QIODevice::ReadOnly)) {
            error = ef.readAll().toStdString();
        }
        // Drain any residual stdout so "more frames" detection still works.
        if (!stopped_early_) {
            const QByteArray extra = process_.readAllStandardOutput();
            if (!extra.isEmpty())
                fail("decoder produced more frames than the timestamp "
                     "inventory");
        }
        if (!stopped_early_ && process_.exitCode() != 0 &&
            error.rfind("av_interleaved_write_frame", 0) != 0) {
            fail(std::string("source decoder failed: ") +
                 (error.empty() ? std::to_string(process_.exitCode())
                                : error.substr(0, error.find('\n'))));
        }
        return false;
    }

    ~Impl() {
        if (process_.state() == QProcess::Running) {
            process_.kill();
            process_.waitForFinished(2000);
        }
    }

    std::string source;
    std::optional<int64_t> max_frames_;
    ProbeResult probed;
    QProcess process_;
    QTemporaryFile error_file_;
    std::size_t frame_bytes_ = 0;
    int64_t index_ = 0;
    bool stopped_early_ = false;
};

FrameSource::FrameSource(const std::string& path, int stream_index,
                         std::optional<int64_t> max_frames)
    : impl_(std::make_unique<Impl>(path, stream_index, max_frames)) {}

FrameSource::~FrameSource() = default;

bool FrameSource::next(StrictFrame& out) { return impl_->next(out); }

std::vector<StrictFrame> read_all_frames(const std::string& path,
                                         int stream_index) {
    std::vector<StrictFrame> frames;
    FrameSource source(path, stream_index);
    StrictFrame frame;
    while (source.next(frame)) frames.push_back(frame);
    return frames;
}


// ---------------------------------------------------------------------------
// iter_state_map (casu/strict/state_builder.py)
// ---------------------------------------------------------------------------
}  // namespace casu::strict

namespace casu::strict {

std::vector<JsonValue> iter_state_map(
    const std::function<bool(StrictFrame&)>& pull, int64_t tile_width,
    int64_t tile_height) {
    std::vector<JsonValue> out;
    StrictFrame current;
    if (!pull(current)) return out;
    std::optional<StrictFrame> previous;
    while (true) {
        StrictFrame following_frame;
        const bool has_following = pull(following_frame);
        if (previous.has_value() &&
            current.time() < previous->time())
            throw StrictDecoderError(
                "source PTS must be monotonic in presentation order");
        if (has_following && following_frame.time() < current.time())
            throw StrictDecoderError(
                "source PTS must be monotonic in presentation order");
        // valid_until: following frame time, else pts+duration_pts when set.
        std::optional<std::pair<int64_t, int64_t>> valid_until_pts;
        int64_t vu_num = 0, vu_den = 1;
        bool have_valid_until = false;
        int64_t vu_pts = 0;
        if (has_following) {
            vu_pts = following_frame.pts;
            vu_num = following_frame.time_base_num;
            vu_den = following_frame.time_base_den;
            have_valid_until = true;
        } else if (current.duration_pts.has_value() &&
                   *current.duration_pts > 0) {
            vu_pts = current.pts + *current.duration_pts;
            vu_num = current.time_base_num;
            vu_den = current.time_base_den;
            have_valid_until = true;
        }
        (void)valid_until_pts;
        const CanonicalFrame* prev_frame =
            previous.has_value() ? &previous->frame : nullptr;
        const std::vector<natv2::StrictTileState> states = natv2::compare_frames(
            prev_frame, current.frame, tile_width, tile_height, nullptr);
        for (const natv2::StrictTileState& st : states) {
            auto record = std::make_shared<JsonObject>();
            record->items["tile_id"] = JsonValue(st.tile_id);
            auto region = std::make_shared<JsonObject>();
            region->items["x"] = JsonValue(st.x);
            region->items["y"] = JsonValue(st.y);
            region->items["w"] = JsonValue(st.w);
            region->items["h"] = JsonValue(st.h);
            record->items["region"] = JsonValue(std::move(region));
            record->items["state"] = JsonValue(st.state);
            record->items["lifecycle"] = JsonValue(st.state);
            auto vf = std::make_shared<JsonObject>();
            vf->items["pts"] = JsonValue(current.pts);
            vf->items["time_base_num"] = JsonValue(current.time_base_num);
            vf->items["time_base_den"] = JsonValue(current.time_base_den);
            record->items["valid_from"] = JsonValue(std::move(vf));
            if (have_valid_until) {
                auto vu = std::make_shared<JsonObject>();
                vu->items["pts"] = JsonValue(vu_pts);
                vu->items["time_base_num"] = JsonValue(vu_num);
                vu->items["time_base_den"] = JsonValue(vu_den);
                record->items["valid_until"] = JsonValue(std::move(vu));
            } else {
                record->items["valid_until"] = JsonValue(nullptr);
            }
            const double vfs = static_cast<double>(current.pts *
                                                   current.time_base_num) /
                               static_cast<double>(current.time_base_den);
            record->items["valid_from_s"] = JsonValue(vfs);
            if (have_valid_until)
                record->items["valid_until_s"] = JsonValue(
                    static_cast<double>(vu_pts * vu_num) /
                    static_cast<double>(vu_den));
            else
                record->items["valid_until_s"] = JsonValue(nullptr);
            record->items["state_hash"] = JsonValue(st.state_hash);
            record->items["reference_hash"] =
                st.has_reference ? JsonValue(st.reference_hash)
                                 : JsonValue(nullptr);
            record->items["plane_count"] = JsonValue(int64_t(st.plane_count));
            record->items["format_change"] = JsonValue(st.format_change);
            record->items["fidelity"] =
                JsonValue(std::string("SOURCE_RESOLUTION_STRICT"));
            out.push_back(JsonValue(std::make_shared<JsonObject>(
                std::move(*record))));
        }
        if (!has_following) break;
        previous = std::move(current);
        current = std::move(following_frame);
    }
    return out;
}
}  // namespace casu::strict
