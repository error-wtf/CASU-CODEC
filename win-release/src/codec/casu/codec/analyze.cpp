// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/codec/analyze.hpp"

#include "casu/sha256.hpp"
#include "casu/codec/tools.hpp"

#include <QProcess>
#include <QTemporaryFile>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <sstream>
#include <stdexcept>

namespace casu::analyze {

namespace {

using casu::JsonValue;

[[noreturn]] void fail(const std::string& msg) { throw std::runtime_error(msg); }

double json_num(const JsonValue* v, double fallback = 0.0) {
    return v && v->is_number() ? v->as_double() : fallback;
}

std::string json_str(const JsonValue* v) {
    return v && v->is_string() ? v->as_string() : std::string();
}

// Python round(): banker's rounding (half to even), then quantized here to
// `decimals` like round(x, 6)/round(x, 8) in the reference.
double pyround(double value, int decimals) {
    const double scale = std::pow(10.0, decimals);
    const double scaled = value * scale;
    // std::nearbyint honours the default FE_TONEAREST = half-to-even.
    return std::nearbyint(scaled) / scale;
}

// numpy.percentile(values, p, method="linear").
double percentile(std::vector<double> values, double p) {
    if (values.empty()) return 0.0;
    std::sort(values.begin(), values.end());
    const double n = static_cast<double>(values.size());
    if (values.size() == 1) return values[0];
    const double rank = (n - 1.0) * (p / 100.0);
    const double lo = std::floor(rank);
    const double hi = std::ceil(rank);
    const double frac = rank - lo;
    const std::size_t i = static_cast<std::size_t>(lo);
    const std::size_t j = static_cast<std::size_t>(hi);
    if (i >= values.size()) return values.back();
    if (j >= values.size()) return values[i];
    return values[i] + (values[j] - values[i]) * frac;
}

std::string ffmpeg_program() {
    // Same resolution order as the Ffmpeg wrapper (find_tool): env override,
    // bundled tools/ tree, then PATH.
    std::string resolved = casu::codec::ffmpeg_path();
    return resolved.empty() ? std::string("ffmpeg") : resolved;
}

int stream_ordinal(const JsonValue& probe, const std::string& kind) {
    int ordinal = -1;
    if (const JsonValue* streams = probe.find("streams"); streams && streams->is_array()) {
        for (const JsonValue& item : streams->as_array().items) {
            const JsonValue* type = item.find("codec_type");
            if (!type || !type->is_string() || type->as_string() != kind) continue;
            ++ordinal;
            if (kind == "video") {
                const JsonValue* disp = item.find("disposition");
                const JsonValue* pic = disp ? disp->find("attached_pic") : nullptr;
                if (pic && pic->is_int() && pic->as_int() == 1) continue;  // cover art
            }
            return ordinal;
        }
    }
    fail("selected " + kind + " stream is absent from probe");
}

const JsonValue* first_stream(const JsonValue& probe, const std::string& kind) {
    if (const JsonValue* streams = probe.find("streams"); streams && streams->is_array()) {
        for (const JsonValue& item : streams->as_array().items) {
            const JsonValue* type = item.find("codec_type");
            if (!type || !type->is_string() || type->as_string() != kind) continue;
            if (kind == "video") {
                const JsonValue* disp = item.find("disposition");
                const JsonValue* pic = disp ? disp->find("attached_pic") : nullptr;
                if (pic && pic->is_int() && pic->as_int() == 1) continue;
            }
            return &item;
        }
    }
    return nullptr;
}

bool has_stream(const JsonValue& probe, const std::string& kind) {
    return first_stream(probe, kind) != nullptr;
}

// Streaming pipe reader with stderr parked in a temp file (deadlock-safe,
// mirrors the TemporaryFile pattern of the reference).
class PipeReader {
public:
    PipeReader(const std::vector<std::string>& args) {
        proc_.setProgram(QString::fromStdString(ffmpeg_program()));
        QStringList qargs;
        for (const auto& a : args) qargs << QString::fromStdString(a);
        proc_.setArguments(qargs);
        proc_.setProcessChannelMode(QProcess::SeparateChannels);
        error_file_.open();
        proc_.setStandardErrorFile(error_file_.fileName());
        proc_.start();
        if (!proc_.waitForStarted(10000))
            fail("could not open FFmpeg process");
    }

    // Reads exactly `size` bytes (or fewer at EOF).
    QByteArray read(std::size_t size) {
        QByteArray out;
        out.reserve(static_cast<int>(size));
        while (out.size() < static_cast<qint64>(size)) {
            const QByteArray chunk =
                proc_.read(static_cast<qint64>(size) - out.size());
            if (!chunk.isEmpty()) {
                out.append(chunk);
                continue;
            }
            if (proc_.bytesAvailable() == 0 && proc_.state() != QProcess::Running)
                break;
            if (!proc_.waitForReadyRead(30000)) {
                if (proc_.state() != QProcess::Running) break;
            }
        }
        return out;
    }

    // finish() -> (returncode, stderr text)
    std::pair<int, std::string> finish() {
        proc_.closeReadChannel(QProcess::StandardOutput);
        proc_.waitForFinished(60000);
        error_file_.flush();
        const QString path = error_file_.fileName();
        QFile f(path);
        std::string err;
        if (f.open(QIODevice::ReadOnly)) err = f.readAll().toStdString();
        return {proc_.exitCode(), err};
    }

private:
    QProcess proc_;
    QTemporaryFile error_file_;
};

JsonValue dict_ratio_counts(const std::vector<std::string>& states,
                            const std::vector<std::string>& names) {
    auto obj = std::make_shared<casu::JsonObject>();
    const double total = std::max<std::size_t>(1, states.size());
    for (const std::string& name : names) {
        const double count = std::count(states.begin(), states.end(), name);
        obj->items[name] = JsonValue(pyround(count / total, 6));
    }
    return JsonValue(std::move(obj));
}

}  // namespace

double manifest_duration(const JsonValue& probe) {
    const JsonValue* format = probe.find("format");
    const JsonValue* duration = format ? format->find("duration") : nullptr;
    try {
        if (duration && duration->is_number()) return duration->as_double();
        if (duration && duration->is_string())
            return std::stod(duration->as_string());
    } catch (const std::exception&) {
    }
    return 0.0;
}

JsonValue rle(const std::vector<std::string>& states, double step,
              bool clamp_end, double end_s, const std::string& id_prefix) {
    auto array = std::make_shared<casu::JsonArray>();
    if (states.empty()) return JsonValue(std::move(array));
    std::size_t start = 0;
    std::string current = states[0];
    auto push_interval = [&](std::size_t begin, std::size_t end,
                             const std::string& state, std::size_t ordinal) {
        auto o = std::make_shared<casu::JsonObject>();
        char ordinal_text[16];
        std::snprintf(ordinal_text, sizeof(ordinal_text), "%06zu", ordinal);
        const double start_s = pyround(static_cast<double>(begin) * step, 6);
        const double end_v = pyround(static_cast<double>(end) * step, 6);
        o->items["start_s"] = JsonValue(start_s);
        o->items["end_s"] = JsonValue(end_v);
        o->items["duration_s"] = JsonValue(pyround(end_v - start_s, 6));
        o->items["state"] = JsonValue(state);
        o->items["segment_id"] =
            JsonValue(id_prefix + "-" + std::string(ordinal_text));
        o->items["lifecycle"] = JsonValue(std::string(ordinal == 0 ? "CREATE" : "UPDATE"));
        o->items["valid_until_s"] = JsonValue(end_v);
        o->items["deadline_s"] = JsonValue(end_v);
        o->items["priority"] = JsonValue((int64_t)0);
        o->items["change_type"] =
            JsonValue(std::string(begin == 0 ? "initial_state" : "state_change"));
        array->items.push_back(JsonValue(std::move(o)));
    };
    for (std::size_t i = 1; i < states.size(); ++i) {
        if (states[i] != current) {
            push_interval(start, i, current, array->items.size());
            start = i;
            current = states[i];
        }
    }
    push_interval(start, states.size(), current, array->items.size());
    if (clamp_end && !array->items.empty()) {
        JsonValue& last = array->items.back();
        JsonObject o = last.as_object_mut();
        const double clamped =
            pyround(std::min(o.items["end_s"].as_double(), end_s), 6);
        const double start_s = o.items["start_s"].as_double();
        o.items["end_s"] = JsonValue(clamped);
        o.items["duration_s"] = JsonValue(pyround(std::max(0.0, clamped - start_s), 6));
        o.items["valid_until_s"] = JsonValue(clamped);
        o.items["deadline_s"] = JsonValue(clamped);
        last = JsonValue(std::make_shared<casu::JsonObject>(std::move(o)));
        if (clamped <= start_s) array->items.pop_back();
    }
    return JsonValue(std::move(array));
}

std::vector<JsonValue> compare_tile_frames(const std::vector<uint8_t>& previous,
                                           const std::vector<uint8_t>& current,
                                           int width, int height,
                                           int tile_width, int tile_height,
                                           const std::string& mode,
                                           double timestamp_s) {
    static const std::map<std::string, double> thresholds{
        {"strict", 0.0}, {"visually_lossless", 0.01}, {"adaptive", 0.05}};
    auto it = thresholds.find(mode);
    if (it == thresholds.end()) fail("unsupported tile comparison mode: " + mode);
    const double threshold = it->second;
    if (static_cast<int>(current.size()) != width * height)
        fail("decoded frame must be a non-empty 2D or 3D array");

    std::vector<JsonValue> result;
    int ordinal = 0;
    for (int y = 0; y < height; y += tile_height) {
        for (int x = 0; x < width; x += tile_width) {
            const int tw = std::min(tile_width, width - x);
            const int th = std::min(tile_height, height - y);
            char tile_id[32];
            std::snprintf(tile_id, sizeof(tile_id), "tile-%08d", ordinal++);
            // tile_digest: sha256(str(shape) || raw bytes); str((h,w))="(h, w)".
            std::ostringstream shape;
            shape << "(" << th << ", " << tw << ")";
            casu::Sha256 digest;
            digest.update(shape.str());
            std::vector<uint8_t> cur_tile(tw * th), prev_tile(tw * th);
            for (int r = 0; r < th; ++r) {
                std::copy_n(current.begin() + (y + r) * width + x, tw,
                            cur_tile.begin() + r * tw);
                if (!previous.empty())
                    std::copy_n(previous.begin() + (y + r) * width + x, tw,
                                prev_tile.begin() + r * tw);
            }
            digest.update(cur_tile);
            const std::string cur_hash = digest.hexdigest();
            std::string prev_hash;
            double difference = 1.0;
            std::string state = "UPDATE", lifecycle = "CREATE";
            if (!previous.empty()) {
                casu::Sha256 pd;
                pd.update(shape.str());
                pd.update(prev_tile);
                prev_hash = pd.hexdigest();
                if (mode == "strict") {
                    const bool identical = prev_hash == cur_hash;
                    state = lifecycle = identical ? "HOLD" : "UPDATE";
                    difference = identical ? 0.0 : 1.0;
                } else {
                    double acc = 0.0;
                    for (std::size_t k = 0; k < cur_tile.size(); ++k)
                        acc += std::abs(int(cur_tile[k]) - int(prev_tile[k]));
                    difference = acc / 255.0 / static_cast<double>(cur_tile.size());
                    const bool identical = difference <= threshold;
                    state = lifecycle = identical ? "HOLD" : "UPDATE";
                }
            }
            char seg_id[96];
            std::snprintf(seg_id, sizeof(seg_id), "%s@%.6f", tile_id, timestamp_s);
            auto o = std::make_shared<casu::JsonObject>();
            o->items["segment_id"] = JsonValue(std::string(seg_id));
            o->items["tile_id"] = JsonValue(std::string(tile_id));
            auto region = std::make_shared<casu::JsonObject>();
            region->items["tile_id"] = JsonValue(std::string(tile_id));
            region->items["x"] = JsonValue((int64_t)x);
            region->items["y"] = JsonValue((int64_t)y);
            region->items["w"] = JsonValue((int64_t)tw);
            region->items["h"] = JsonValue((int64_t)th);
            o->items["region"] = JsonValue(std::move(region));
            o->items["valid_from_s"] = JsonValue(timestamp_s);
            o->items["valid_until_s"] = JsonValue(nullptr);
            o->items["state"] = JsonValue(state);
            o->items["lifecycle"] = JsonValue(lifecycle);
            o->items["base_state_hash"] =
                prev_hash.empty() ? JsonValue(nullptr) : JsonValue(prev_hash);
            o->items["state_hash"] = JsonValue(cur_hash);
            o->items["difference_ratio"] = JsonValue(pyround(difference, 8));
            o->items["fidelity_class"] =
                JsonValue(std::string(mode == "strict" ? "LOSSLESS_REALTIME"
                                                       : "VISUALLY_LOSSLESS"));
            result.push_back(JsonValue(std::move(o)));
        }
    }
    return result;
}

JsonValue preview_activity_analysis(const std::string& path,
                                    const JsonValue& probe,
                                    double analysis_fps,
                                    const std::string& mode) {
    if (!std::isfinite(analysis_fps) || analysis_fps <= 0.0)
        fail("analysis FPS must be finite and positive");
    constexpr int width = 160, height = 90;
    if (mode != "strict" && mode != "visually_lossless" && mode != "adaptive")
        fail("unknown video analysis mode: " + mode);
    const JsonValue* video = first_stream(probe, "video");
    if (!video) {
        auto empty = std::make_shared<casu::JsonArray>();
        return JsonValue(std::move(empty));  // falsy {} in the reference
    }
    const int video_ordinal = stream_ordinal(probe, "video");
    std::ostringstream filter;
    filter << "fps=" << analysis_fps
           << ",scale=" << width << ":" << height << ":flags=area,format=gray";
    // NOTE: PipeReader sets the program itself; args start at argv[1].
    PipeReader proc({"-v", "error", "-i", path,
                     "-map", "0:v:" + std::to_string(video_ordinal), "-an",
                     "-vf", filter.str(), "-f", "rawvideo", "-pix_fmt", "gray",
                     "pipe:1"});
    constexpr std::size_t frame_size = static_cast<std::size_t>(width) * height;
    const int tile_width = std::max(1, std::min(16, width / 8));   // 16
    const int tile_height = std::max(1, std::min(16, height / 8)); // 11
    const double total_duration = manifest_duration(probe);
    const double expected_frames = std::max(1.0, total_duration * analysis_fps);

    std::vector<uint8_t> previous, current(frame_size);
    std::vector<double> deltas, tile_changes;
    std::vector<std::string> states;
    std::map<std::string, JsonValue> active_tiles;
    std::vector<JsonValue> tile_intervals;
    long long frame_index = 0;

    while (true) {
        const QByteArray raw = proc.read(frame_size);
        if (static_cast<std::size_t>(raw.size()) != frame_size) break;
        std::copy_n(raw.constData(), frame_size, current.begin());
        double delta;
        if (previous.empty()) delta = 1.0;
        else {
            double acc = 0.0;
            for (std::size_t k = 0; k < frame_size; ++k)
                acc += std::abs(int(current[k]) - int(previous[k]));
            delta = acc / 255.0 / static_cast<double>(frame_size);
        }
        double changed_ratio = 1.0;
        if (!previous.empty()) {
            const double grid_threshold = mode == "strict"     ? 0.01
                                          : mode == "visually_lossless" ? 0.03
                                                                        : 0.08;
            int changed = 0, total_tiles = 0;
            for (int gy = 0; gy < height; gy += tile_height) {
                for (int gx = 0; gx < width; gx += tile_width) {
                    const int gw = std::min(tile_width, width - gx);
                    const int gh = std::min(tile_height, height - gy);
                    double tacc = 0.0;
                    for (int r = 0; r < gh; ++r)
                        for (int c = 0; c < gw; ++c) {
                            const std::size_t idx =
                                static_cast<std::size_t>(gy + r) * width + gx + c;
                            tacc += std::abs(int(current[idx]) - int(previous[idx]));
                        }
                    if (tacc / 255.0 / static_cast<double>(gw * gh) > grid_threshold)
                        ++changed;
                    ++total_tiles;
                }
            }
            changed_ratio = changed / std::max(1, total_tiles);
        }
        const double timestamp_s =
            static_cast<double>(frame_index) / analysis_fps;
        // Tile state map with the reference dedup semantics.
        for (JsonValue& record :
             compare_tile_frames(previous, current, width, height,
                                 tile_width, tile_height, mode, timestamp_s)) {
            JsonObject rec = record.as_object_mut();
            const std::string tile_id = rec.items["tile_id"].as_string();
            const std::string state_hash = rec.items["state_hash"].as_string();
            const std::string state = rec.items["state"].as_string();
            auto prior_it = active_tiles.find(tile_id);
            if (prior_it != active_tiles.end()) {
                JsonObject prior = prior_it->second.as_object_mut();
                if (prior.items["state_hash"].as_string() == state_hash &&
                    prior.items["state"].as_string() == state)
                    continue;  // unchanged tile — record dropped
                prior.items["valid_until_s"] =
                    JsonValue(pyround(timestamp_s, 6));
                tile_intervals.push_back(JsonValue(std::make_shared<casu::JsonObject>(std::move(prior))));
            }
            active_tiles[tile_id] = JsonValue(std::make_shared<casu::JsonObject>(std::move(rec)));
        }
        const std::string state = delta >= 0.010   ? "motion"
                                  : delta >= 0.0015 ? "low_motion"
                                                    : "static";
        deltas.push_back(delta);
        tile_changes.push_back(changed_ratio);
        states.push_back(state);
        previous = current;
        ++frame_index;
    }
    const auto [code, err] = proc.finish();
    if (code != 0) fail("video analysis failed: " + err);

    const double end_s = total_duration;
    for (auto& [_, v] : active_tiles) {
        JsonObject rec = v.as_object_mut();
        rec.items["valid_until_s"] = JsonValue(pyround(end_s, 6));
        tile_intervals.push_back(
            JsonValue(std::make_shared<casu::JsonObject>(std::move(rec))));
    }
    std::sort(tile_intervals.begin(), tile_intervals.end(),
              [](const JsonValue& a, const JsonValue& b) {
                  const double ta = a.as_object().items.at("valid_from_s").as_double();
                  const double tb = b.as_object().items.at("valid_from_s").as_double();
                  if (ta != tb) return ta < tb;
                  return a.as_object().items.at("tile_id").as_string() <
                         b.as_object().items.at("tile_id").as_string();
              });

    auto build = std::make_shared<casu::JsonObject>();
    build->items["method"] =
        JsonValue(std::string("decoded grayscale temporal activity hint"));
    build->items["analysis_mode"] = JsonValue(mode);
    build->items["analysis_fps"] = JsonValue(analysis_fps);
    auto res = std::make_shared<casu::JsonArray>();
    res->items.push_back(JsonValue((int64_t)width));
    res->items.push_back(JsonValue((int64_t)height));
    build->items["analysis_resolution"] = JsonValue(std::move(res));
    build->items["source_width"] = video->find("width")
                                       ? JsonValue(*video->find("width"))
                                       : JsonValue(nullptr);
    build->items["source_height"] = video->find("height")
                                        ? JsonValue(*video->find("height"))
                                        : JsonValue(nullptr);
    build->items["source_codec"] = video->find("codec_name")
                                       ? JsonValue(*video->find("codec_name"))
                                       : JsonValue(nullptr);
    build->items["source_time_base"] = video->find("time_base")
                                           ? JsonValue(*video->find("time_base"))
                                           : JsonValue(nullptr);
    build->items["sample_count"] = JsonValue((int64_t)states.size());
    build->items["activity_ratio"] = dict_ratio_counts(
        states, {"static", "low_motion", "motion"});
    double dmean = 0.0;
    for (double d : deltas) dmean += d;
    build->items["mean_frame_delta"] = JsonValue(
        pyround(deltas.empty() ? 0.0 : dmean / deltas.size(), 8));
    build->items["p95_frame_delta"] =
        JsonValue(pyround(percentile(deltas, 95.0), 8));

    auto spatial = std::make_shared<casu::JsonObject>();
    spatial->items["method"] =
        JsonValue(std::string("decoded grayscale tile change ratio"));
    auto tsz = std::make_shared<casu::JsonArray>();
    tsz->items.push_back(JsonValue((int64_t)tile_width));
    tsz->items.push_back(JsonValue((int64_t)tile_height));
    spatial->items["tile_size"] = JsonValue(std::move(tsz));
    auto grid = std::make_shared<casu::JsonArray>();
    grid->items.push_back(
        JsonValue((int64_t)std::ceil(double(width) / tile_width)));
    grid->items.push_back(
        JsonValue((int64_t)std::ceil(double(height) / tile_height)));
    spatial->items["tile_grid"] = JsonValue(std::move(grid));
    double tc_mean = 0.0;
    for (double d : tile_changes) tc_mean += d;
    spatial->items["mean_changed_tile_ratio"] =
        JsonValue(pyround(tile_changes.empty() ? 0.0 : tc_mean / tile_changes.size(), 8));
    spatial->items["p95_changed_tile_ratio"] =
        JsonValue(pyround(percentile(tile_changes, 95.0), 8));
    spatial->items["strict_pixel_identical_available"] = JsonValue(false);
    spatial->items["strict_pixel_identity_note"] = JsonValue(std::string(
        "requires canonical-resolution pixel/plane tile comparison; this "
        "reduced preview is not an identity proof"));
    spatial->items["mode_threshold"] =
        JsonValue(mode == "strict"     ? 0.01
                  : mode == "visually_lossless" ? 0.03
                                                : 0.08);
    spatial->items["state_is_hint_only"] = JsonValue(true);
    auto smap = std::make_shared<casu::JsonArray>();
    for (const JsonValue& v : tile_intervals) smap->items.push_back(v);
    spatial->items["state_map"] = JsonValue(std::move(smap));
    spatial->items["state_map_count"] = JsonValue((int64_t)tile_intervals.size());
    spatial->items["state_map_coordinate_system"] =
        JsonValue(std::string("analysis-plane-pixels"));
    spatial->items["state_map_identity_scope"] =
        JsonValue(std::string("decoded gray8 analysis plane only"));
    build->items["spatial_analysis"] = JsonValue(std::move(spatial));
    build->items["segments"] =
        rle(states, 1.0 / analysis_fps, true, total_duration, "video");
    build->items["state_is_hint_only"] = JsonValue(true);
    return JsonValue(std::move(build));
}

JsonValue analyze_audio(const std::string& path, const JsonValue& probe,
                        int sample_rate, int window_ms) {
    if (sample_rate <= 0 || window_ms <= 0)
        fail("audio sample rate and window must be positive");
    const JsonValue* audio = first_stream(probe, "audio");
    if (!audio) {
        auto empty = std::make_shared<casu::JsonArray>();
        return JsonValue(std::move(empty));
    }
    PipeReader proc({"-v", "error", "-i", path, "-map", "0:a:0",
                     "-vn", "-ac", "1", "-ar", std::to_string(sample_rate),
                     "-f", "f32le", "pipe:1"});
    const std::size_t window = std::max<size_t>(
        1, static_cast<std::size_t>(sample_rate * window_ms / 1000));
    const std::size_t window_bytes = window * sizeof(float);
    std::vector<std::string> states;
    std::vector<double> db_values;
    std::vector<float> pending;
    const auto consume = [&](const float* samples, std::size_t count) {
        // One padded window (reference tail handling).
        double acc = 0.0;
        for (std::size_t i = 0; i < count; ++i) acc += double(samples[i]) * samples[i];
        for (std::size_t i = count; i < window; ++i) acc += 0.0;
        const double rms = std::sqrt(acc / window + 1e-12) + 1e-12;
        const double db = 20.0 * std::log10(rms);
        db_values.push_back(db);
        states.push_back(db < -55.0 ? "silence"
                         : db < -38.0 ? "low_level"
                                      : "active");
    };
    while (true) {
        const QByteArray chunk =
            proc.read(std::max(window_bytes, std::size_t(64 * 1024)));
        if (chunk.isEmpty()) break;
        const float* data = reinterpret_cast<const float*>(chunk.constData());
        const std::size_t incoming = chunk.size() / sizeof(float);
        pending.insert(pending.end(), data, data + incoming);
        const std::size_t complete = (pending.size() / window) * window;
        if (!complete) continue;
        for (std::size_t w = 0; w + window <= complete; w += window) {
            double acc = 0.0;
            for (std::size_t i = 0; i < window; ++i)
                acc += double(pending[w + i]) * pending[w + i];
            const double rms = std::sqrt(acc / window + 1e-12) + 1e-12;
            const double db = 20.0 * std::log10(rms);
            db_values.push_back(db);
            states.push_back(db < -55.0 ? "silence"
                             : db < -38.0 ? "low_level"
                                          : "active");
        }
        pending.erase(pending.begin(), pending.begin() + complete);
    }
    if (!pending.empty()) consume(pending.data(), pending.size());
    const auto [code, err] = proc.finish();
    if (code != 0) fail("audio analysis failed: " + err);

    auto build = std::make_shared<casu::JsonObject>();
    const std::size_t count = states.size();
    if (!count) {
        build->items["source_codec"] = audio->find("codec_name")
                                           ? JsonValue(*audio->find("codec_name"))
                                           : JsonValue(nullptr);
        build->items["segments"] = rle({}, 1.0, false, 0.0, "audio");
        return JsonValue(std::move(build));
    }
    build->items["method"] =
        JsonValue(std::string("decoded PCM RMS activity hint"));
    build->items["source_codec"] = audio->find("codec_name")
                                       ? JsonValue(*audio->find("codec_name"))
                                       : JsonValue(nullptr);
    build->items["sample_rate"] = JsonValue((int64_t)sample_rate);
    build->items["window_ms"] = JsonValue((int64_t)window_ms);
    build->items["sample_windows"] = JsonValue((int64_t)count);
    build->items["activity_ratio"] =
        dict_ratio_counts(states, {"silence", "low_level", "active"});
    double mean = 0.0;
    for (double d : db_values) mean += d;
    build->items["mean_dbfs"] =
        JsonValue(pyround(db_values.empty() ? 0.0 : mean / db_values.size(), 3));
    build->items["segments"] =
        rle(states, window_ms / 1000.0, true, manifest_duration(probe), "audio");
    build->items["state_is_hint_only"] = JsonValue(true);
    return JsonValue(std::move(build));
}

}  // namespace casu::analyze
