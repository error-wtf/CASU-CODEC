// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Full port of casu/native_v2 payload codecs + casu/strict identity hashing.
// Encoders emit byte-identical output to the Python reference (sorted-keys
// compact JSON with Python json.dumps escaping rules, zlib level 9,
// big-endian envelope). Decoders enforce identical fail-closed limits.
#include "casu/native_v2_payloads.hpp"
#include "casu/sha256.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <sstream>
#include <stdexcept>
#include <zlib.h>

namespace casu::natv2 {

using namespace casu::casunat2;

namespace {

[[noreturn]] void fail(const std::string& msg) { throw CasuError(msg); }

// --- zlib -------------------------------------------------------------------
std::vector<uint8_t> compress_zlib_impl(const uint8_t* data, std::size_t size) {
    z_stream strm{};
    // windowBits 15 + memLevel 8 == Python zlib.compress(level=9) defaults.
    if (deflateInit2(&strm, 9, Z_DEFLATED, 15, 8, Z_DEFAULT_STRATEGY) != Z_OK)
        fail("zlib deflate init failed");
    std::vector<uint8_t> out(deflateBound(&strm, static_cast<uLong>(size)) + 16);
    strm.next_in = const_cast<Bytef*>(data);
    strm.avail_in = static_cast<uInt>(size);
    strm.next_out = out.data();
    strm.avail_out = static_cast<uInt>(out.size());
    const int rc = deflate(&strm, Z_FINISH);
    const std::size_t produced = out.size() - strm.avail_out;
    deflateEnd(&strm);
    if (rc != Z_STREAM_END) fail("zlib deflate failed");
    out.resize(produced);
    return out;
}

}  // namespace

std::vector<uint8_t> compress_zlib(const uint8_t* data, std::size_t size) {
    return compress_zlib_impl(data, size);
}

// Port of zlib.decompressobj().decompress(data, expected+1) plus the exact
// acceptance check: exact output length, clean stream end, no trailing input.
std::vector<uint8_t> decompress_exact(const uint8_t* data, std::size_t size,
                                      uint64_t expected) {
    if (expected > MAX_DECODED_PLANE_BYTES)
        fail("decoded stream exceeds safety limit");
    z_stream strm{};
    if (inflateInit2(&strm, 15) != Z_OK) fail("zlib inflate init failed");
    strm.next_in = const_cast<Bytef*>(data);
    strm.avail_in = static_cast<uInt>(size);
    const std::size_t cap = static_cast<std::size_t>(expected);
    std::vector<uint8_t> out;
    out.reserve(cap + 1);
    uint8_t buf[65536];
    bool stream_end = false;
    while (true) {
        strm.next_out = buf;
        strm.avail_out = sizeof(buf);
        const int rc = inflate(&strm, Z_NO_FLUSH);
        if (rc == Z_STREAM_END) { stream_end = true; }
        else if (rc != Z_OK && rc != Z_BUF_ERROR) {
            inflateEnd(&strm);
            fail("invalid compressed stream");
        }
        out.insert(out.end(), buf, buf + (sizeof(buf) - strm.avail_out));
        if (stream_end || out.size() > cap || strm.avail_in == 0) break;
        // Guard against a stalled decoder that neither consumes nor produces.
        if (rc == Z_BUF_ERROR && sizeof(buf) - strm.avail_out == 0) break;
    }
    const bool unused_input = strm.avail_in != 0;
    inflateEnd(&strm);
    if (out.size() != cap || !stream_end || unused_input)
        fail("decompressed length mismatch");
    return out;
}

// --- Python-compatible repr --------------------------------------------------
namespace {

void append_repr_str(std::string& out, const std::string& s) {
    const bool has_single = s.find('\'') != std::string::npos;
    const bool has_double = s.find('"') != std::string::npos;
    const char quote = (has_single && !has_double) ? '"' : '\'';
    out.push_back(quote);
    for (unsigned char c : s) {
        if (c == quote || c == '\\') {
            out.push_back('\\');
            out.push_back(char(c));
        } else if (c == '\n') {
            out += "\\n";
        } else if (c == '\r') {
            out += "\\r";
        } else if (c == '\t') {
            out += "\\t";
        } else if (c < 0x20 || c == 0x7F) {
            char buf[8];
            std::snprintf(buf, sizeof(buf), "\\x%02x", c);
            out += buf;
        } else {
            out.push_back(char(c));
        }
    }
    out.push_back(quote);
}

std::string join_tuple(std::vector<std::string> parts) {
    if (parts.empty()) return "()";
    if (parts.size() == 1) return "(" + parts[0] + ",)";
    std::string out = "(";
    for (std::size_t i = 0; i < parts.size(); ++i) {
        if (i) out += ", ";
        out += parts[i];
    }
    out += ")";
    return out;
}

}  // namespace

std::string py_repr_str(const std::string& value) {
    std::string out;
    append_repr_str(out, value);
    return out;
}

std::string py_repr_int_tuple(const std::vector<int64_t>& values) {
    std::vector<std::string> parts;
    parts.reserve(values.size());
    for (int64_t v : values) parts.push_back(std::to_string(v));
    return join_tuple(std::move(parts));
}

std::string py_repr_str_tuple(const std::vector<std::string>& values) {
    std::vector<std::string> parts;
    parts.reserve(values.size());
    for (const std::string& v : values) parts.push_back(py_repr_str(v));
    return join_tuple(std::move(parts));
}

std::string py_repr_region(int64_t x, int64_t y, int64_t w, int64_t h) {
    return py_repr_int_tuple({x, y, w, h});
}

namespace {

// repr(tuple((k, v), ...)) for sorted color metadata pairs.
std::string repr_color_metadata(
    const std::vector<std::pair<std::string, std::string>>& metadata) {
    std::vector<std::string> pairs;
    pairs.reserve(metadata.size());
    for (const auto& [k, v] : metadata)
        pairs.push_back("(" + py_repr_str(k) + ", " + py_repr_str(v) + ")");
    return join_tuple(std::move(pairs));
}

std::string identity_bytes(const CanonicalFrame& frame) {
    std::string out;
    out.reserve(64);
    // b"CASU-STRICT-TILE-v1\0" (20 bytes including NUL).
    out += "CASU-STRICT-TILE-v1";
    out.push_back('\0');
    out += frame.pixel_format;
    out += py_repr_int_tuple({frame.shape().first, frame.shape().second});
    out += repr_color_metadata(frame.color_metadata);
    std::vector<std::string> layouts;
    layouts.reserve(frame.plane_layouts.size());
    for (const PlaneLayout& l : frame.plane_layouts) {
        const auto id = l.identity();
        layouts.push_back(py_repr_int_tuple({id[0], id[1], id[2], id[3], id[4],
                                             id[5], id[6], id[7]}));
    }
    out += join_tuple(std::move(layouts));
    return out;
}

void update_tile_bytes(Sha256& digest, const CanonicalFrame& frame,
                       int64_t x, int64_t y, int64_t width, int64_t height) {
    for (std::size_t index = 0; index < frame.planes.size(); ++index) {
        const CanonicalPlane& plane = frame.planes[index];
        const PlaneLayout& layout = frame.plane_layouts[index];
        int64_t x0 = (x >> layout.subsample_x) * layout.components;
        int64_t y0 = y >> layout.subsample_y;
        int64_t x1 = ((x + width + (1LL << layout.subsample_x) - 1) >>
                      layout.subsample_x) * layout.components;
        int64_t y1 = (y + height + (1LL << layout.subsample_y) - 1) >>
                     layout.subsample_y;
        x0 = std::max<int64_t>(x0, 0);
        y0 = std::max<int64_t>(y0, 0);
        const int64_t row_end = std::min(y1, plane.rows);
        const int64_t col_end = std::min(x1, plane.cols);
        for (int64_t row = y0; row < row_end; ++row) {
            const std::size_t offset =
                static_cast<std::size_t>(row * plane.cols + x0) *
                static_cast<std::size_t>(plane.itemsize);
            const std::size_t count =
                static_cast<std::size_t>(std::max<int64_t>(0, col_end - x0)) *
                static_cast<std::size_t>(plane.itemsize);
            digest.update(plane.data.data() + offset, count);
        }
    }
}

}  // namespace

std::string frame_identity_prefix(const CanonicalFrame& frame) {
    return identity_bytes(frame);
}

std::string canonical_tile_hash(const CanonicalFrame& frame, int64_t x,
                                int64_t y, int64_t width, int64_t height) {
    Sha256 d;
    d.update(identity_bytes(frame));
    d.update(py_repr_region(x, y, width, height));
    update_tile_bytes(d, frame, x, y, width, height);
    return d.hexdigest();
}

std::string tile_digest_with_prefix(const CanonicalFrame& frame, int64_t x,
                                    int64_t y, int64_t width, int64_t height,
                                    const std::string& prefix) {
    Sha256 d;
    d.update(prefix);
    d.update(py_repr_region(x, y, width, height));
    update_tile_bytes(d, frame, x, y, width, height);
    return d.hexdigest();
}

// --- format spec -------------------------------------------------------------
FormatSpec format_spec(const std::string& pixel_format) {
    std::string fmt = pixel_format;
    std::transform(fmt.begin(), fmt.end(), fmt.begin(),
                   [](unsigned char c) { return char(std::tolower(c)); });
    FormatSpec spec;
    struct PackedEntry {
        const char* name;
        int depth;
        int bps;
        int comps;
    };
    static constexpr PackedEntry packed[] = {
        {"rgb24", 8, 1, 3}, {"bgr24", 8, 1, 3}, {"rgba", 8, 1, 4},
        {"bgra", 8, 1, 4},  {"argb", 8, 1, 4},  {"abgr", 8, 1, 4},
        {"rgba64le", 16, 2, 4},
    };
    for (const PackedEntry& e : packed) {
        if (fmt == e.name) {
            spec.bit_depth = e.depth;
            spec.bytes_per_sample = e.bps;
            spec.specs = {{std::array<int, 3>{0, 0, e.comps}}};
            return spec;
        }
    }
    if (fmt == "gray" || fmt == "gray8") {
        spec.bit_depth = 8;
        spec.bytes_per_sample = 1;
        spec.specs = {{std::array<int, 3>{0, 0, 1}}};
        return spec;
    }
    if (fmt == "gray16le") {
        spec.bit_depth = 16;
        spec.bytes_per_sample = 2;
        spec.specs = {{std::array<int, 3>{0, 0, 1}}};
        return spec;
    }
    int depth = 8;
    for (int candidate : {16, 14, 12, 10, 9}) {
        if (fmt.find(std::to_string(candidate)) != std::string::npos) {
            depth = candidate;
            break;
        }
    }
    const int bps = depth <= 8 ? 1 : 2;
    const bool alpha = fmt.rfind("yuva", 0) == 0;
    auto starts = [&](const char* p) { return fmt.rfind(p, 0) == 0; };
    std::vector<std::array<int, 3>> layouts;
    if (starts("yuv420") || starts("yuva420")) {
        layouts = {{0, 0, 1}, {1, 1, 1}, {1, 1, 1}};
    } else if (starts("yuv422") || starts("yuva422")) {
        layouts = {{0, 0, 1}, {1, 0, 1}, {1, 0, 1}};
    } else if (starts("yuv444") || starts("yuva444")) {
        layouts = {{0, 0, 1}, {0, 0, 1}, {0, 0, 1}};
    } else if (starts("gbrp")) {
        layouts = {{0, 0, 1}, {0, 0, 1}, {0, 0, 1}};
    } else {
        throw VideoPayloadError("unsupported canonical pixel format: " +
                                pixel_format);
    }
    if (alpha) layouts.push_back({0, 0, 1});
    spec.bit_depth = depth;
    spec.bytes_per_sample = bps;
    spec.specs = std::move(layouts);
    return spec;
}

namespace {

int ceil_shift(int64_t value, int shift) {
    return static_cast<int>((value + (1LL << shift) - 1) >> shift);
}

uint64_t plane_max_sample(const CanonicalPlane& plane) {
    uint64_t max_value = 0;
    for (std::size_t i = 0; i + static_cast<std::size_t>(plane.itemsize) <=
                            plane.data.size();
         i += static_cast<std::size_t>(plane.itemsize)) {
        const uint64_t v =
            plane.itemsize == 1
                ? static_cast<uint64_t>(plane.data[i])
                : static_cast<uint64_t>(plane.data[i]) |
                      (static_cast<uint64_t>(plane.data[i + 1]) << 8);
        if (v > max_value) max_value = v;
    }
    return max_value;
}

}  // namespace

CanonicalFrame canonical_frame(
    std::vector<CanonicalPlane> planes, const std::string& pixel_format,
    const std::map<std::string, std::string>& color_metadata,
    std::optional<std::pair<int64_t, int64_t>> source_shape) {
    if (planes.empty())
        throw VideoPayloadError("at least one decoded plane is required");
    const FormatSpec spec = format_spec(pixel_format);
    if (planes.size() != spec.specs.size())
        throw VideoPayloadError(pixel_format + " requires " +
                                std::to_string(spec.specs.size()) +
                                " planes, got " +
                                std::to_string(planes.size()));
    int64_t source_height = 0, source_width = 0;
    if (!source_shape.has_value()) {
        const CanonicalPlane& first = planes[0];
        const int components = spec.specs[0][2];
        if (first.rows <= 0 || components <= 0 ||
            first.cols % components != 0)
            throw VideoPayloadError(
                "cannot derive source geometry from first plane");
        source_height = first.rows;
        source_width = first.cols / components;
    } else {
        if (source_shape->first <= 0 || source_shape->second <= 0)
            throw VideoPayloadError("source_shape must be (height, width)");
        source_height = source_shape->first;
        source_width = source_shape->second;
    }

    CanonicalFrame frame;
    frame.pixel_format = pixel_format;
    std::transform(frame.pixel_format.begin(), frame.pixel_format.end(),
                   frame.pixel_format.begin(),
                   [](unsigned char c) { return char(std::tolower(c)); });
    frame.color_metadata.assign(color_metadata.begin(), color_metadata.end());
    frame.has_source_shape = true;
    frame.source_width = source_width;
    frame.source_height = source_height;

    for (std::size_t index = 0; index < planes.size(); ++index) {
        CanonicalPlane& array = planes[index];
        const auto [sub_x, sub_y, components] = spec.specs[index];
        const int expected_h = ceil_shift(source_height, sub_y);
        const int expected_w = ceil_shift(source_width, sub_x);
        const int64_t exp_cols = static_cast<int64_t>(expected_w) * components;
        if (array.rows != expected_h || array.cols != exp_cols)
            throw VideoPayloadError("plane " + std::to_string(index) +
                                    " shape does not match active geometry");
        if (array.itemsize != spec.bytes_per_sample)
            throw VideoPayloadError("plane " + std::to_string(index) +
                                    " must use unsigned " +
                                    std::to_string(spec.bytes_per_sample * 8) +
                                    "-bit storage");
        if (spec.bit_depth < spec.bytes_per_sample * 8 && !array.data.empty() &&
            plane_max_sample(array) >= (1ULL << spec.bit_depth))
            throw VideoPayloadError("plane " + std::to_string(index) +
                                    " contains samples outside " +
                                    std::to_string(spec.bit_depth) +
                                    "-bit range");
        PlaneLayout layout;
        layout.index = static_cast<int>(index);
        layout.width = expected_w;
        layout.height = expected_h;
        layout.bit_depth = spec.bit_depth;
        layout.bytes_per_sample = spec.bytes_per_sample;
        layout.subsample_x = sub_x;
        layout.subsample_y = sub_y;
        layout.components = components;
        frame.plane_layouts.push_back(layout);
        frame.planes.push_back(std::move(array));
    }
    return frame;
}

std::tuple<int64_t, int64_t, std::string,
           std::vector<std::pair<std::string, std::string>>,
           std::vector<std::array<int64_t, 8>>>
CanonicalFrame::format_identity() const {
    std::vector<std::array<int64_t, 8>> ids;
    ids.reserve(plane_layouts.size());
    for (const PlaneLayout& l : plane_layouts) ids.push_back(l.identity());
    return {shape().second, shape().first, pixel_format, color_metadata, ids};
}

std::string CanonicalFrame::digest() const {
    Sha256 d;
    // The reference appends repr(region) unconditionally; digest() passes
    // region=None, so the literal "None" is part of the identity input.
    d.update(identity_bytes(*this));
    d.update("None");
    for (const CanonicalPlane& p : planes)
        d.update(p.data.data(), p.data.size());
    return d.hexdigest();
}

// --- JSON coercion helpers (mirror Python int()/str() semantics) -------------
namespace {

bool j_is_bool(const JsonValue& v) { return v.is_bool(); }

// Python int(x): bool -> TypeError; int -> value; float -> truncate (finite
// only); str -> decimal with optional sign/whitespace; null/container -> TypeError.
std::optional<int64_t> coerce_int(const JsonValue* v) {
    if (!v || v->is_null() || v->is_array() || v->is_object()) return std::nullopt;
    if (v->is_bool()) return std::nullopt;
    if (v->is_int()) return v->as_int();
    if (v->is_double()) {
        const double d = v->as_double();
        if (!std::isfinite(d)) return std::nullopt;
        if (d > 9.2233720368547758e18 || d < -9.2233720368547758e18)
            return std::nullopt;
        return static_cast<int64_t>(d);  // truncation toward zero
    }
    const std::string& s = v->as_string();
    try {
        std::size_t idx = 0;
        const long long parsed = std::stoll(s, &idx, 10);
        // Python allows surrounding whitespace but rejects trailing garbage.
        while (idx < s.size() && (s[idx] == ' ' || s[idx] == '\t' ||
                                  s[idx] == '\n' || s[idx] == '\r'))
            ++idx;
        if (idx != s.size()) return std::nullopt;
        return static_cast<int64_t>(parsed);
    } catch (const std::exception&) {
        return std::nullopt;
    }
}

std::string coerce_str(const JsonValue& v) {
    switch (v.kind()) {
        case JsonValue::Kind::String: return v.as_string();
        case JsonValue::Kind::Int: return std::to_string(v.as_int());
        case JsonValue::Kind::Bool: return v.as_bool() ? "True" : "False";
        case JsonValue::Kind::Null: return "None";
        default: throw CasuError("value is not string-coercible");
    }
}

std::string dump_sorted(const JsonValue& v, bool ensure_ascii) {
    return dump_json(v, true, ensure_ascii);
}

JsonValue make_object(std::initializer_list<std::pair<std::string, JsonValue>> items) {
    auto o = std::make_shared<JsonObject>();
    for (auto& [k, val] : items) o->items[k] = std::move(val);
    return JsonValue(std::move(o));
}

JsonValue make_array(std::vector<JsonValue> items) {
    auto a = std::make_shared<JsonArray>();
    a->items = std::move(items);
    return JsonValue(std::move(a));
}

JsonValue json_color_metadata(
    const std::vector<std::pair<std::string, std::string>>& metadata) {
    auto o = std::make_shared<JsonObject>();
    for (const auto& [k, v] : metadata) o->items[k] = JsonValue(v);
    return JsonValue(std::move(o));
}

std::map<std::string, std::string> parse_color_metadata(const JsonValue* v) {
    std::map<std::string, std::string> out;
    if (!v || v->is_null()) return out;
    if (!v->is_object()) throw CasuError("color metadata must be an object");
    for (const auto& [k, val] : v->as_object().items) {
        if (val.is_null()) continue;  // reference filters None values
        out[k] = coerce_str(val);
    }
    return out;
}

constexpr char U32_SIZE = 4;

void put_u32be(std::string& out, uint32_t value) {
    out.push_back(char((value >> 24) & 0xFF));
    out.push_back(char((value >> 16) & 0xFF));
    out.push_back(char((value >> 8) & 0xFF));
    out.push_back(char(value & 0xFF));
}

uint32_t get_u32be(const std::string& payload, std::size_t pos) {
    return (uint32_t(uint8_t(payload[pos])) << 24) |
           (uint32_t(uint8_t(payload[pos + 1])) << 16) |
           (uint32_t(uint8_t(payload[pos + 2])) << 8) |
           uint32_t(uint8_t(payload[pos + 3]));
}

// Envelope pack used by video/audio/bitmap/attachment payloads:
// [u32 BE header_len][sorted-keys JSON][concatenated blobs].
std::string envelope_pack(const JsonValue& meta,
                          const std::vector<std::string>& blobs) {
    const std::string header = dump_sorted(meta, true);
    std::string out;
    put_u32be(out, static_cast<uint32_t>(header.size()));
    out += header;
    for (const std::string& b : blobs) out += b;
    return out;
}

struct BlobView {
    const uint8_t* data = nullptr;
    std::size_t size = 0;
};

struct VideoEnvelope {
    JsonValue meta;
    std::vector<BlobView> blobs;
};

VideoEnvelope envelope_unpack_video(const std::string& payload) {
    if (payload.size() < U32_SIZE)
        throw VideoPayloadError("truncated video payload");
    const uint32_t length = get_u32be(payload, 0);
    if (uint64_t(length) > payload.size() - U32_SIZE ||
        length > MAX_VIDEO_METADATA_BYTES)
        throw VideoPayloadError("invalid video payload header length");
    JsonValue meta;
    try {
        meta = parse_strict_json(payload.data() + U32_SIZE, length);
    } catch (const JsonError&) {
        throw VideoPayloadError("invalid video payload metadata");
    }
    const JsonValue* planes = meta.find("planes");
    if (!meta.is_object() || !planes || !planes->is_array() ||
        planes->as_array().items.empty() ||
        planes->as_array().items.size() > 8)
        throw VideoPayloadError("invalid video payload metadata");
    std::size_t pos = U32_SIZE + length;
    VideoEnvelope env;
    env.meta = meta;
    for (const JsonValue& plane : planes->as_array().items) {
        if (!plane.is_object())
            throw VideoPayloadError("invalid video payload metadata");
        const JsonValue* cl = plane.find("compressed_length");
        const auto compressed = coerce_int(cl);
        if (!compressed || *compressed < 0 ||
            uint64_t(*compressed) > payload.size() - pos)
            throw VideoPayloadError("invalid compressed plane length");
        BlobView view{reinterpret_cast<const uint8_t*>(payload.data()) + pos, static_cast<std::size_t>(*compressed)};
        env.blobs.push_back(view);
        pos += static_cast<std::size_t>(*compressed);
    }
    if (pos != payload.size())
        throw VideoPayloadError("trailing bytes in video payload");
    return env;
}

}  // namespace

// --- video payloads ----------------------------------------------------------
namespace {

// numpy dtype aliases accepted by np.dtype() for unsigned 8/16-bit planes.
int dtype_itemsize(const std::string& dtype) {
    static const std::set<std::string> u8 = {"uint8", "u1", "ubyte"};
    static const std::set<std::string> u16 = {"uint16", "u2", "ushort"};
    if (u8.count(dtype)) return 1;
    if (u16.count(dtype)) return 2;
    return 0;
}

std::string dtype_name(int itemsize) {
    return itemsize == 1 ? "uint8" : "uint16";
}

CanonicalPlane make_plane(std::vector<uint8_t> raw, int64_t rows, int64_t cols,
                          int itemsize) {
    CanonicalPlane p;
    p.data = std::move(raw);
    p.rows = rows;
    p.cols = cols;
    p.itemsize = itemsize;
    return p;
}

}  // namespace

void slice_plane_bounds(const PlaneLayout& layout, int64_t x, int64_t y,
                        int64_t w, int64_t h, int64_t& x0, int64_t& y0,
                        int64_t& x1, int64_t& y1) {
    x0 = (x >> layout.subsample_x) * layout.components;
    y0 = y >> layout.subsample_y;
    x1 = ((x + w + (1LL << layout.subsample_x) - 1) >> layout.subsample_x) *
         layout.components;
    y1 = (y + h + (1LL << layout.subsample_y) - 1) >> layout.subsample_y;
}

std::string encode_key_state(const CanonicalFrame& frame) {
    const auto [height, width] = frame.shape();
    uint64_t total_bytes = 0;
    for (const CanonicalPlane& p : frame.planes)
        total_bytes += static_cast<uint64_t>(p.data.size());
    if (std::max(height, width) > MAX_VIDEO_DIMENSION ||
        total_bytes > MAX_DECODED_PLANE_BYTES)
        throw VideoPayloadError("video key state exceeds safety limit");
    std::vector<JsonValue> plane_entries;
    plane_entries.reserve(frame.planes.size());
    for (const CanonicalPlane& p : frame.planes) {
        plane_entries.push_back(make_object({
            {"shape", make_array({JsonValue(p.rows), JsonValue(p.cols)})},
            {"dtype", JsonValue(dtype_name(p.itemsize))},
        }));
    }
    const std::shared_ptr<JsonObject> meta = std::make_shared<JsonObject>();
    meta->items["pixel_format"] = JsonValue(frame.pixel_format);
    meta->items["source_shape"] =
        make_array({JsonValue(height), JsonValue(width)});
    meta->items["color_metadata"] = json_color_metadata(frame.color_metadata);
    meta->items["planes"] = make_array(std::move(plane_entries));
    std::vector<std::string> blobs;
    blobs.reserve(frame.planes.size());
    for (std::size_t index = 0; index < frame.planes.size(); ++index) {
        const CanonicalPlane& p = frame.planes[index];
        const std::vector<uint8_t> compressed =
            compress_zlib_impl(p.data.data(), p.data.size());
        JsonObject& entry =
            meta->items["planes"].as_array_mut().items[index].as_object_mut();
        entry.items["raw_length"] = JsonValue(int64_t(p.data.size()));
        entry.items["compressed_length"] =
            JsonValue(int64_t(compressed.size()));
        entry.items["compression"] = JsonValue("zlib");
        blobs.emplace_back(compressed.begin(), compressed.end());
    }
    return envelope_pack(JsonValue(meta), blobs);
}

CanonicalFrame decode_key_state(const std::string& payload,
                                const CasuLimits& limits) {
    const VideoEnvelope env = envelope_unpack_video(payload);
    const JsonValue* planes = env.meta.find("planes");
    CanonicalFrame result;
    result.pixel_format = coerce_str(*env.meta.find("pixel_format"));
    result.color_metadata = [&] {
        const auto md = parse_color_metadata(env.meta.find("color_metadata"));
        return std::vector<std::pair<std::string, std::string>>(md.begin(),
                                                                md.end());
    }();
    uint64_t total_decoded = 0;
    std::vector<CanonicalPlane> decoded_planes;
    const JsonValue* source_shape = env.meta.find("source_shape");
    if (!source_shape || !source_shape->is_array() ||
        source_shape->as_array().items.size() != 2)
        throw VideoPayloadError("invalid decoded plane shape");
    std::vector<CanonicalPlane> planes_in;
    std::size_t index = 0;
    for (const JsonValue& descriptor : planes->as_array().items) {
        const JsonValue* compression = descriptor.find("compression");
        if ((compression && !compression->is_null() &&
             compression->as_string() != "zlib") ||
            (compression && compression->is_null()))
            throw VideoPayloadError("unsupported video plane compression");
        const JsonValue* shape = descriptor.find("shape");
        if (!shape || !shape->is_array() ||
            shape->as_array().items.size() != 2)
            throw VideoPayloadError("invalid decoded plane shape");
        std::array<int64_t, 2> dims{};
        for (int i = 0; i < 2; ++i) {
            const auto v = coerce_int(&shape->as_array().items[i]);
            if (!v || *v <= 0)
                throw VideoPayloadError("invalid decoded plane shape");
            dims[i] = *v;
        }
        const JsonValue* dt = descriptor.find("dtype");
        if (!dt || !dt->is_string())
            throw VideoPayloadError("invalid decoded plane dtype");
        const int itemsize = dtype_itemsize(dt->as_string());
        if (itemsize == 0)
            throw VideoPayloadError("invalid decoded plane dtype");
        int64_t expected = dims[0] * dims[1] * itemsize;
        const bool over_dim = std::max(dims[0], dims[1]) > limits.max_width ||
                              std::max(dims[0], dims[1]) > limits.max_height;
        if (over_dim || expected < 0 ||
            total_decoded + uint64_t(expected) >
                MAX_DECODED_PLANE_BYTES)
            throw VideoPayloadError("decoded video frame exceeds safety limit");
        total_decoded += static_cast<uint64_t>(expected);
        const JsonValue* rl = descriptor.find("raw_length");
        const auto raw_length = coerce_int(rl);
        if (!raw_length || *raw_length != expected)
            throw VideoPayloadError("video plane metadata length mismatch");
        const BlobView& blob = env.blobs.at(index);
        std::vector<uint8_t> raw =
            decompress_exact(blob.data, blob.size, uint64_t(expected));
        planes_in.push_back(
            make_plane(std::move(raw), dims[0], dims[1], itemsize));
        ++index;
    }
    const auto h = coerce_int(&source_shape->as_array().items[0]);
    const auto w = coerce_int(&source_shape->as_array().items[1]);
    if (!h || !w)
        throw VideoPayloadError("invalid decoded plane shape");
    return canonical_frame(std::move(planes_in), result.pixel_format,
                           parse_color_metadata(env.meta.find("color_metadata")),
                           std::make_optional(std::make_pair(*h, *w)));
}

std::string encode_format_change(const CanonicalFrame& frame) {
    const auto [height, width] = frame.shape();
    const JsonValue value = make_object({
        {"version", JsonValue(int64_t(1))},
        {"pixel_format", JsonValue(frame.pixel_format)},
        {"source_shape", make_array({JsonValue(height), JsonValue(width)})},
        {"color_metadata", json_color_metadata(frame.color_metadata)},
    });
    return dump_sorted(value, true);
}

JsonValue decode_format_change(const std::string& payload) {
    if (payload.size() > MAX_VIDEO_METADATA_BYTES)
        throw VideoPayloadError("video format change exceeds safety limit");
    try {
        const JsonValue value = parse_strict_json(payload);
        if (!value.is_object())
            throw VideoPayloadError("invalid video format change");
        const JsonValue* version = value.find("version");
        if (!version || !version->is_int() || version->as_int() != 1)
            throw VideoPayloadError("invalid video format change");
        const JsonValue* shape = value.find("source_shape");
        if (!shape || !shape->is_array() ||
            shape->as_array().items.size() != 2 ||
            shape->as_array().items[0].is_bool() ||
            shape->as_array().items[1].is_bool())
            throw VideoPayloadError("invalid video format change");
        const auto h = coerce_int(&shape->as_array().items[0]);
        const auto w = coerce_int(&shape->as_array().items[1]);
        if (!h || !w)
            throw VideoPayloadError("invalid video format change");
        const JsonValue* pf = value.find("pixel_format");
        if (!pf || !pf->is_string() || pf->as_string().empty() ||
            pf->as_string().size() > 64)
            throw VideoPayloadError("invalid video format change");
        const JsonValue* color = value.find("color_metadata");
        if (color && !color->is_null() && !color->is_object())
            throw VideoPayloadError("invalid video format change");
        const int64_t height = *h, width = *w;
        if (!(0 < width && width <= MAX_VIDEO_DIMENSION) ||
            !(0 < height && height <= MAX_VIDEO_DIMENSION))
            throw VideoPayloadError("invalid video format change");
        return make_object({
            {"version", JsonValue(int64_t(1))},
            {"pixel_format", JsonValue(pf->as_string())},
            {"source_shape",
             make_array({JsonValue(height), JsonValue(width)})},
            {"color_metadata",
             color && color->is_object() ? JsonValue(*color)
                                         : make_object({})},
        });
    } catch (const JsonError&) {
        throw VideoPayloadError("invalid video format change");
    }
}

std::string encode_tile_update(const CanonicalFrame& frame, int64_t x,
                               int64_t y, int64_t width, int64_t height,
                               const char* base_state_hash) {
    const auto [fheight, fwidth] = frame.shape();
    if (x < 0 || y < 0 || width <= 0 || height <= 0 ||
        x + width > fwidth || y + height > fheight)
        throw VideoPayloadError("tile is outside source frame");
    uint64_t total_part_bytes = 0;
    struct Part {
        std::vector<uint8_t> bytes;
        int64_t rows = 0;
        int64_t cols = 0;
        int itemsize = 1;
    };
    std::vector<Part> parts(frame.planes.size());
    for (std::size_t index = 0; index < frame.planes.size(); ++index) {
        const CanonicalPlane& plane = frame.planes[index];
        const PlaneLayout& layout = frame.plane_layouts[index];
        int64_t x0, y0, x1, y1;
        slice_plane_bounds(layout, x, y, width, height, x0, y0, x1, y1);
        const int64_t row_end = std::min(y1, plane.rows);
        const int64_t col_end = std::min(x1, plane.cols);
        Part part;
        part.itemsize = plane.itemsize;
        part.rows = std::max<int64_t>(0, row_end - y0);
        part.cols = std::max<int64_t>(0, col_end - x0);
        const std::size_t row_bytes =
            static_cast<std::size_t>(part.cols) *
            static_cast<std::size_t>(plane.itemsize);
        part.bytes.reserve(static_cast<std::size_t>(part.rows) * row_bytes);
        for (int64_t row = y0; row < row_end; ++row) {
            const std::size_t offset =
                static_cast<std::size_t>(row * plane.cols + x0) *
                static_cast<std::size_t>(plane.itemsize);
            part.bytes.insert(
                part.bytes.end(), plane.data.begin() +
                                      static_cast<std::ptrdiff_t>(offset),
                plane.data.begin() + static_cast<std::ptrdiff_t>(
                                         offset + row_bytes));
        }
        total_part_bytes += part.bytes.size();
        parts[index] = std::move(part);
    }
    if (total_part_bytes > MAX_DECODED_PLANE_BYTES)
        throw VideoPayloadError("video tile update exceeds safety limit");
    const std::string new_state_hash =
        canonical_tile_hash(frame, x, y, width, height);
    const std::shared_ptr<JsonObject> meta = std::make_shared<JsonObject>();
    meta->items["pixel_format"] = JsonValue(frame.pixel_format);
    meta->items["source_shape"] =
        make_array({JsonValue(fheight), JsonValue(fwidth)});
    meta->items["color_metadata"] = json_color_metadata(frame.color_metadata);
    meta->items["region"] = make_array({JsonValue(x), JsonValue(y),
                                       JsonValue(width), JsonValue(height)});
    meta->items["base_state_hash"] =
        base_state_hash ? JsonValue(std::string(base_state_hash))
                        : JsonValue(nullptr);
    meta->items["new_state_hash"] = JsonValue(new_state_hash);
    std::vector<JsonValue> plane_entries;
    std::vector<std::string> blobs;
    for (std::size_t index = 0; index < parts.size(); ++index) {
        const Part& part = parts[index];
        const std::string compressed = [&] {
            const std::vector<uint8_t> c =
                compress_zlib_impl(part.bytes.data(), part.bytes.size());
            return std::string(c.begin(), c.end());
        }();
        plane_entries.push_back(make_object({
            {"shape",
             make_array({JsonValue(part.rows), JsonValue(part.cols)})},
            {"dtype", JsonValue(dtype_name(part.itemsize))},
            {"raw_length", JsonValue(int64_t(part.bytes.size()))},
            {"compressed_length", JsonValue(int64_t(compressed.size()))},
            {"compression", JsonValue("zlib")},
        }));
        blobs.push_back(compressed);
    }
    meta->items["planes"] = make_array(std::move(plane_entries));
    return envelope_pack(JsonValue(meta), blobs);
}

// --- TileStateCache ----------------------------------------------------------
void TileStateCache::set_frame(CanonicalFrame frame) {
    frame_ = std::move(frame);
    prefix_.reset();
}

const std::string& TileStateCache::identity_prefix() {
    if (!prefix_.has_value()) {
        if (!frame_.has_value())
            throw VideoPayloadError("tile update requires a key state");
        prefix_ = frame_identity_prefix(*frame_);
    }
    return *prefix_;
}

CanonicalFrame TileStateCache::apply_key_state(const std::string& payload,
                                               const CasuLimits& limits) {
    CanonicalFrame decoded = decode_key_state(payload, limits);
    set_frame(std::move(decoded));
    return *frame_;
}

CanonicalFrame TileStateCache::apply_tile_update(const std::string& payload,
                                                 const CasuLimits& limits) {
    if (!frame_.has_value())
        throw VideoPayloadError("tile update requires a key state");
    CanonicalFrame& frame = *frame_;
    const VideoEnvelope env = envelope_unpack_video(payload);
    const JsonValue* planes = env.meta.find("planes");
    if (!planes || !planes->is_array() ||
        planes->as_array().items.size() != frame.planes.size())
        throw VideoPayloadError(
            "tile update plane count differs from key state");
    const JsonValue* source_shape = env.meta.find("source_shape");
    bool shape_matches = false;
    if (source_shape && source_shape->is_array() &&
        source_shape->as_array().items.size() == 2) {
        const auto h = coerce_int(&source_shape->as_array().items[0]);
        const auto w = coerce_int(&source_shape->as_array().items[1]);
        shape_matches = h && w && frame.shape().first == *h &&
                        frame.shape().second == *w;
    }
    if (!shape_matches ||
        env.meta.find("pixel_format") == nullptr ||
        !env.meta.find("pixel_format")->is_string() ||
        env.meta.find("pixel_format")->as_string() != frame.pixel_format)
        throw VideoPayloadError(
            "tile update format differs from cached key state");
    const JsonValue* region = env.meta.find("region");
    std::array<int64_t, 4> region_values{};
    if (!region || !region->is_array() ||
        region->as_array().items.size() != 4)
        throw VideoPayloadError("invalid tile region");
    for (int i = 0; i < 4; ++i) {
        const auto v = coerce_int(&region->as_array().items[i]);
        if (!v) throw VideoPayloadError("invalid tile region");
        region_values[i] = *v;
    }
    const auto [rx, ry, rw, rh] = region_values;
    const std::string prefix = identity_prefix();
    const JsonValue* expected_base = env.meta.find("base_state_hash");
    if (expected_base && !expected_base->is_null()) {
        if (!expected_base->is_string() ||
            tile_digest_with_prefix(frame, rx, ry, rw, rh, prefix) !=
                expected_base->as_string())
            throw VideoPayloadError("tile update base state hash mismatch");
    }
    uint64_t total_decoded = 0;
    std::size_t index = 0;
    for (const JsonValue& descriptor : planes->as_array().items) {
        const JsonValue* compression = descriptor.find("compression");
        if (compression && !compression->is_null() &&
            compression->as_string() != "zlib")
            throw VideoPayloadError("unsupported tile plane compression");
        const JsonValue* shape = descriptor.find("shape");
        if (!shape || !shape->is_array() ||
            shape->as_array().items.size() != 2)
            throw VideoPayloadError("invalid tile plane shape");
        std::array<int64_t, 2> dims{};
        for (int i = 0; i < 2; ++i) {
            const auto v = coerce_int(&shape->as_array().items[i]);
            if (!v || *v <= 0)
                throw VideoPayloadError("invalid tile plane shape");
            dims[i] = *v;
        }
        const JsonValue* dt = descriptor.find("dtype");
        if (!dt || !dt->is_string())
            throw VideoPayloadError("invalid tile plane layout");
        const int itemsize = dtype_itemsize(dt->as_string());
        if (itemsize == 0)
            throw VideoPayloadError("invalid tile plane layout");
        const int64_t expected = dims[0] * dims[1] * itemsize;
        const JsonValue* rl = descriptor.find("raw_length");
        const auto raw_length = coerce_int(rl);
        if (itemsize == 0 || !raw_length || *raw_length != expected ||
            std::max(dims[0], dims[1]) > limits.max_width ||
            std::max(dims[0], dims[1]) > limits.max_height ||
            total_decoded + uint64_t(expected) > MAX_DECODED_PLANE_BYTES)
            throw VideoPayloadError("invalid tile plane layout");
        total_decoded += static_cast<uint64_t>(expected);
        const BlobView& blob = env.blobs.at(index);
        std::vector<uint8_t> raw =
            decompress_exact(blob.data, blob.size, uint64_t(expected));
        CanonicalPlane& target = frame.planes[index];
        const PlaneLayout& layout = frame.plane_layouts[index];
        if (target.itemsize != itemsize)
            throw VideoPayloadError(
                "tile plane dtype differs from key state");
        // Bit-depth range check on decoded samples.
        if (layout.bit_depth < layout.bytes_per_sample * 8 && !raw.empty()) {
            uint64_t max_value = 0;
            for (std::size_t i2 = 0; i2 < raw.size(); ++i2) {
                const uint64_t v =
                    itemsize == 1
                        ? raw[i2]
                        : uint64_t(raw[i2]) | (uint64_t(raw[i2 + 1]) << 8);
                max_value = std::max(max_value, v);
                i2 += itemsize - 1;
            }
            if (max_value >= (1ULL << layout.bit_depth))
                throw VideoPayloadError(
                    "tile plane samples outside bit depth range");
        }
        int64_t x0, y0, x1, y1;
        slice_plane_bounds(layout, rx, ry, rw, rh, x0, y0, x1, y1);
        const int64_t row_end = std::min(y1, target.rows);
        const int64_t col_end = std::min(x1, target.cols);
        const int64_t view_rows = std::max<int64_t>(0, row_end - y0);
        const int64_t view_cols = std::max<int64_t>(0, col_end - x0);
        if (view_rows != dims[0] || view_cols != dims[1])
            throw VideoPayloadError("tile plane shape mismatch");
        for (int64_t r = 0; r < dims[0]; ++r) {
            const std::size_t dst_offset =
                static_cast<std::size_t>((y0 + r) * target.cols + x0) *
                static_cast<std::size_t>(target.itemsize);
            const std::size_t src_offset =
                static_cast<std::size_t>(r * dims[1]) *
                static_cast<std::size_t>(itemsize);
            std::memcpy(target.data.data() + dst_offset, raw.data() + src_offset,
                        static_cast<std::size_t>(dims[1]) *
                            static_cast<std::size_t>(itemsize));
        }
        ++index;
    }
    const JsonValue* expected_new = env.meta.find("new_state_hash");
    if (!expected_new || !expected_new->is_string() ||
        tile_digest_with_prefix(frame, rx, ry, rw, rh, prefix) !=
            expected_new->as_string())
        throw VideoPayloadError("tile update new state hash mismatch");
    return frame;
}

// --- audio payloads ----------------------------------------------------------
std::string encode_audio_block(const std::vector<uint8_t>& pcm, int64_t pts,
                               int64_t tb_num, int64_t tb_den,
                               int64_t sample_rate, int64_t channels,
                               const std::string& sample_format,
                               const char* channel_layout,
                               int64_t sample_count) {
    if (tb_num <= 0 || tb_den <= 0 || sample_rate <= 0 ||
        sample_rate > 768'000 || channels <= 0 || channels > 64 ||
        sample_count < 0)
        throw AudioPayloadError("invalid audio timing or format");
    if (sample_format != "s16le" ||
        pcm.size() > MAX_DECODED_AUDIO_BYTES ||
        static_cast<int64_t>(pcm.size()) !=
            sample_count * channels * 2)
        throw AudioPayloadError(
            "PCM byte length does not match samples/channels/format");
    const std::vector<uint8_t> compressed =
        compress_zlib_impl(pcm.data(), pcm.size());
    const std::shared_ptr<JsonObject> meta = std::make_shared<JsonObject>();
    meta->items["pts"] = JsonValue(pts);
    meta->items["time_base"] =
        make_array({JsonValue(tb_num), JsonValue(tb_den)});
    meta->items["sample_rate"] = JsonValue(sample_rate);
    meta->items["channels"] = JsonValue(channels);
    meta->items["channel_layout"] =
        channel_layout ? JsonValue(std::string(channel_layout))
                       : JsonValue(nullptr);
    meta->items["sample_format"] = JsonValue(sample_format);
    meta->items["sample_count"] = JsonValue(sample_count);
    meta->items["raw_length"] = JsonValue(int64_t(pcm.size()));
    meta->items["compressed_length"] = JsonValue(int64_t(compressed.size()));
    meta->items["compression"] = JsonValue("zlib");
    std::vector<std::string> blobs{std::string(compressed.begin(),
                                               compressed.end())};
    return envelope_pack(JsonValue(meta), blobs);
}

AudioBlock decode_audio_block(const std::string& payload) {
    try {
        if (payload.size() < U32_SIZE)
            throw AudioPayloadError("truncated audio block");
        const uint32_t length = get_u32be(payload, 0);
        if (uint64_t(length) > payload.size() - U32_SIZE ||
            length > MAX_AUDIO_METADATA_BYTES)
            throw AudioPayloadError("invalid audio block metadata length");
        const JsonValue meta =
            parse_strict_json(payload.data() + U32_SIZE, length);
        if (!meta.is_object())
            throw CasuError("metadata is not an object");
        const JsonValue* compression = meta.find("compression");
        if ((compression && !compression->is_null() &&
             compression->as_string() != "zlib"))
            throw CasuError("unsupported compression");
        const JsonValue* tb = meta.find("time_base");
        if (!tb || !tb->is_array() || tb->as_array().items.size() != 2)
            throw CasuError("missing time base");
        const auto num = coerce_int(&tb->as_array().items[0]);
        const auto den = coerce_int(&tb->as_array().items[1]);
        if (!num || !den) throw CasuError("bad time base");
        const auto expected_opt = coerce_int(meta.find("raw_length"));
        if (!expected_opt) throw CasuError("missing raw length");
        const int64_t expected = *expected_opt;
        if (expected < 0 || uint64_t(expected) > MAX_DECODED_AUDIO_BYTES)
            throw AudioPayloadError(
                "decoded audio block exceeds safety limit");
        const BlobView blob{
            reinterpret_cast<const uint8_t*>(payload.data()) + U32_SIZE +
                length,
            payload.size() - U32_SIZE - length};
        std::vector<uint8_t> raw = decompress_exact(blob.data, blob.size,
                                                    uint64_t(expected));
        AudioBlock block;
        const auto pts = coerce_int(meta.find("pts"));
        const auto rate = coerce_int(meta.find("sample_rate"));
        const auto chans = coerce_int(meta.find("channels"));
        const auto count = coerce_int(meta.find("sample_count"));
        const JsonValue* sf = meta.find("sample_format");
        if (!pts || !rate || !chans || !count || !sf || !sf->is_string())
            throw CasuError("incomplete audio metadata");
        block.pts = *pts;
        block.time_base_num = *num;
        block.time_base_den = *den;
        block.sample_rate = *rate;
        block.channels = *chans;
        const JsonValue* layout = meta.find("channel_layout");
        if (layout && !layout->is_null()) {
            block.has_channel_layout = true;
            block.channel_layout = coerce_str(*layout);
        }
        block.sample_format = coerce_str(*sf);
        block.sample_count = *count;
        block.pcm = std::move(raw);
        // Exact container-length accounting.
        const JsonValue* cl = meta.find("compressed_length");
        const auto compressed_length = cl ? coerce_int(cl) : std::nullopt;
        if (!compressed_length ||
            static_cast<int64_t>(payload.size()) !=
                int64_t(U32_SIZE) + int64_t(length) + *compressed_length)
            throw AudioPayloadError("audio block length mismatch");
        if (block.time_base_num <= 0 || block.time_base_den <= 0 ||
            block.sample_rate <= 0 || block.sample_rate > 768'000 ||
            block.channels <= 0 || block.channels > 64)
            throw AudioPayloadError("invalid audio block format");
        if (block.sample_format != "s16le" ||
            static_cast<int64_t>(block.pcm.size()) !=
                block.sample_count * block.channels * 2)
            throw AudioPayloadError(
                "audio PCM layout does not match sample metadata");
        return block;
    } catch (const AudioPayloadError&) {
        throw;
    } catch (const JsonError&) {
        throw AudioPayloadError("invalid audio block");
    } catch (const CasuError&) {
        throw AudioPayloadError("invalid audio block");
    }
}

// --- text payloads -----------------------------------------------------------
namespace {

std::string json_bytes_no_ascii(const JsonValue& value) {
    return dump_json(value, true, false);  // ensure_ascii=False
}

}  // namespace

std::string encode_subtitle_packet(const SubtitlePacket& p) {
    if (p.end_pts < p.start_pts)
        throw TextPayloadError("subtitle end_pts precedes start_pts");
    if (p.text.empty())
        throw TextPayloadError("subtitle text must not be empty");
    if (p.text.size() > MAX_SUBTITLE_TEXT_BYTES || p.language.size() > 64 ||
        p.format.size() > 64)
        throw TextPayloadError("subtitle metadata/text exceeds limit");
    const JsonValue value = make_object({
        {"version", JsonValue(int64_t(1))},
        {"start_pts", JsonValue(p.start_pts)},
        {"end_pts", JsonValue(p.end_pts)},
        {"text", JsonValue(p.text)},
        {"language", JsonValue(p.language)},
        {"format", JsonValue(p.format)},
    });
    return json_bytes_no_ascii(value);
}

SubtitlePacket decode_subtitle_packet(const std::string& payload) {
    try {
        if (payload.size() > MAX_SUBTITLE_TEXT_BYTES + 16 * 1024)
            throw TextPayloadError("subtitle payload exceeds limit");
        const JsonValue value = parse_strict_json(payload);
        if (!value.is_object())
            throw CasuError("payload is not an object");
        const JsonValue* version = value.find("version");
        if (!version || !version->is_int() || version->as_int() != 1)
            throw CasuError("bad version");
        SubtitlePacket p;
        const auto start = coerce_int(value.find("start_pts"));
        const auto end = coerce_int(value.find("end_pts"));
        const JsonValue* text = value.find("text");
        if (!start || !end || !text)
            throw CasuError("missing subtitle fields");
        p.start_pts = *start;
        p.end_pts = *end;
        p.text = coerce_str(*text);
        const JsonValue* language = value.find("language");
        p.language = language ? coerce_str(*language) : "und";
        const JsonValue* format = value.find("format");
        p.format = format ? coerce_str(*format) : "text";
        if (p.end_pts < p.start_pts || p.text.empty() ||
            p.text.size() > MAX_SUBTITLE_TEXT_BYTES ||
            p.language.size() > 64 || p.format.size() > 64)
            throw CasuError("subtitle bounds/limits violated");
        return p;
    } catch (const TextPayloadError&) {
        throw;
    } catch (const JsonError&) {
        throw TextPayloadError("invalid subtitle payload");
    } catch (const CasuError&) {
        throw TextPayloadError("invalid subtitle payload");
    }
}

std::string encode_chapter_table(const std::vector<Chapter>& chapters) {
    if (chapters.size() > MAX_CHAPTERS)
        throw TextPayloadError("chapter count exceeds limit");
    std::vector<JsonValue> normalized;
    normalized.reserve(chapters.size());
    for (const Chapter& chapter : chapters) {
        if (chapter.end_pts < chapter.start_pts || chapter.title.empty() ||
            chapter.title.size() > 4096 || chapter.language.size() > 64)
            throw TextPayloadError("invalid chapter bounds/title");
        normalized.push_back(make_object({
            {"start_pts", JsonValue(chapter.start_pts)},
            {"end_pts", JsonValue(chapter.end_pts)},
            {"title", JsonValue(chapter.title)},
            {"language", JsonValue(chapter.language)},
        }));
    }
    const JsonValue value = make_object({
        {"version", JsonValue(int64_t(1))},
        {"chapters", make_array(std::move(normalized))},
    });
    const std::string encoded = json_bytes_no_ascii(value);
    if (encoded.size() > MAX_CHAPTER_TABLE_BYTES)
        throw TextPayloadError("chapter table exceeds limit");
    return encoded;
}

std::vector<Chapter> decode_chapter_table(const std::string& payload) {
    try {
        if (payload.size() > MAX_CHAPTER_TABLE_BYTES)
            throw TextPayloadError("chapter table exceeds limit");
        const JsonValue value = parse_strict_json(payload);
        if (!value.is_object())
            throw CasuError("payload is not an object");
        const JsonValue* version = value.find("version");
        if (!version || !version->is_int() || version->as_int() != 1)
            throw CasuError("bad version");
        const JsonValue* chapters = value.find("chapters");
        if (!chapters || !chapters->is_array() ||
            chapters->as_array().items.size() > MAX_CHAPTERS)
            throw CasuError("bad chapters");
        std::vector<Chapter> result;
        for (const JsonValue& entry : chapters->as_array().items) {
            if (!entry.is_object()) throw CasuError("bad chapter");
            Chapter c;
            const auto start = coerce_int(entry.find("start_pts"));
            const auto end = coerce_int(entry.find("end_pts"));
            const JsonValue* title = entry.find("title");
            if (!start || !end || !title) throw CasuError("bad chapter");
            c.start_pts = *start;
            c.end_pts = *end;
            c.title = coerce_str(*title);
            const JsonValue* language = entry.find("language");
            c.language = language ? coerce_str(*language) : "und";
            if (c.end_pts < c.start_pts || c.title.empty() ||
                c.title.size() > 4096 || c.language.size() > 64)
                throw CasuError("bad chapter bounds/title");
            result.push_back(std::move(c));
        }
        return result;
    } catch (const TextPayloadError&) {
        throw;
    } catch (const JsonError&) {
        throw TextPayloadError("invalid chapter table");
    } catch (const CasuError&) {
        throw TextPayloadError("invalid chapter table");
    }
}

// --- bitmap subtitles --------------------------------------------------------
std::string encode_bitmap_subtitle(int64_t start_pts, int64_t end_pts,
                                   int64_t canvas_width, int64_t canvas_height,
                                   int64_t x, int64_t y,
                                   const uint8_t* rgba, std::size_t rgba_size,
                                   int64_t width, int64_t height) {
    const int64_t expected =
        width * height * 4;  // overflow-checked below against raw size
    if (end_pts < start_pts || canvas_width <= 0 || canvas_height <= 0 ||
        canvas_width > MAX_BITMAP_DIMENSION ||
        canvas_height > MAX_BITMAP_DIMENSION ||
        uint64_t(canvas_width) * uint64_t(canvas_height) * 4 >
            MAX_BITMAP_RAW_BYTES ||
        width <= 0 || height <= 0 || x < 0 || y < 0 ||
        x + width > canvas_width || y + height > canvas_height ||
        expected != static_cast<int64_t>(rgba_size) ||
        uint64_t(expected) > MAX_BITMAP_RAW_BYTES)
        throw BitmapSubtitleError("invalid bitmap subtitle geometry/timing");
    const std::vector<uint8_t> compressed = compress_zlib_impl(rgba, rgba_size);
    const std::shared_ptr<JsonObject> meta = std::make_shared<JsonObject>();
    meta->items["version"] = JsonValue(int64_t(1));
    meta->items["start_pts"] = JsonValue(start_pts);
    meta->items["end_pts"] = JsonValue(end_pts);
    meta->items["time_base"] = make_array({JsonValue(int64_t(1)),
                                          JsonValue(int64_t(1000))});
    meta->items["canvas_width"] = JsonValue(canvas_width);
    meta->items["canvas_height"] = JsonValue(canvas_height);
    meta->items["x"] = JsonValue(x);
    meta->items["y"] = JsonValue(y);
    meta->items["width"] = JsonValue(width);
    meta->items["height"] = JsonValue(height);
    meta->items["pixel_format"] = JsonValue(std::string("rgba"));
    meta->items["raw_length"] = JsonValue(int64_t(rgba_size));
    meta->items["compressed_length"] = JsonValue(int64_t(compressed.size()));
    meta->items["compression"] = JsonValue(std::string("zlib"));
    meta->items["sha256"] =
        JsonValue(Sha256::oneshot(rgba, rgba_size));
    std::vector<std::string> blobs{std::string(compressed.begin(),
                                               compressed.end())};
    return envelope_pack(JsonValue(meta), blobs);
}

BitmapSubtitle decode_bitmap_subtitle(const std::string& payload) {
    try {
        if (payload.size() < U32_SIZE)
            throw BitmapSubtitleError("truncated bitmap subtitle");
        const uint32_t length = get_u32be(payload, 0);
        if (uint64_t(length) > payload.size() - U32_SIZE ||
            length > 64 * 1024)
            throw BitmapSubtitleError(
                "invalid bitmap subtitle metadata length");
        const JsonValue meta =
            parse_strict_json(payload.data() + U32_SIZE, length);
        if (!meta.is_object())
            throw CasuError("metadata is not an object");
        const auto ivalue = [&](const char* key) -> int64_t {
            const auto v = coerce_int(meta.find(key));
            if (!v) throw CasuError(std::string("missing field ") + key);
            return *v;
        };
        const JsonValue* version = meta.find("version");
        const JsonValue* pf = meta.find("pixel_format");
        const JsonValue* compression = meta.find("compression");
        const bool compression_ok = compression == nullptr ||
                                    (compression->is_string() &&
                                     compression->as_string() == "zlib");
        const JsonValue* tb = meta.find("time_base");
        const bool tb_ok = tb && tb->is_array() &&
                           tb->as_array().items.size() == 2 &&
                           tb->as_array().items[0].is_int() &&
                           tb->as_array().items[0].as_int() == 1 &&
                           tb->as_array().items[1].is_int() &&
                           tb->as_array().items[1].as_int() == 1000;
        if (!version || !version->is_int() || version->as_int() != 1 ||
            !pf || !pf->is_string() || pf->as_string() != "rgba" ||
            !compression_ok || !tb_ok)
            throw CasuError("bitmap header mismatch");
        BitmapSubtitle s;
        s.start_pts = ivalue("start_pts");
        s.end_pts = ivalue("end_pts");
        s.canvas_width = ivalue("canvas_width");
        s.canvas_height = ivalue("canvas_height");
        s.x = ivalue("x");
        s.y = ivalue("y");
        s.width = ivalue("width");
        s.height = ivalue("height");
        const int64_t raw_length = ivalue("raw_length");
        const int64_t compressed_length = ivalue("compressed_length");
        if (s.end_pts < s.start_pts || s.canvas_width <= 0 ||
            s.canvas_height <= 0 || s.canvas_width > MAX_BITMAP_DIMENSION ||
            s.canvas_height > MAX_BITMAP_DIMENSION ||
            uint64_t(s.canvas_width) * uint64_t(s.canvas_height) * 4 >
                MAX_BITMAP_RAW_BYTES ||
            s.width <= 0 || s.height <= 0 || s.x < 0 || s.y < 0 ||
            s.x + s.width > s.canvas_width ||
            s.y + s.height > s.canvas_height ||
            raw_length != s.width * s.height * 4 ||
            uint64_t(raw_length) > MAX_BITMAP_RAW_BYTES ||
            compressed_length < 0 ||
            uint64_t(compressed_length) >
                MAX_BITMAP_RAW_BYTES + 1024ULL * 1024)
            throw CasuError("bitmap geometry/limits violated");
        const BlobView blob{
            reinterpret_cast<const uint8_t*>(payload.data()) + U32_SIZE +
                length,
            payload.size() - U32_SIZE - length};
        if (blob.size != static_cast<std::size_t>(compressed_length))
            throw CasuError("compressed length mismatch");
        std::vector<uint8_t> raw = decompress_exact(blob.data, blob.size,
                                                    uint64_t(raw_length));
        const JsonValue* sha = meta.find("sha256");
        if (!sha || !sha->is_string() || sha->as_string().size() != 64 ||
            Sha256::oneshot(raw.data(), raw.size()) != sha->as_string())
            throw CasuError("bitmap digest mismatch");
        s.rgba = std::move(raw);
        s.sha256 = sha->as_string();
        return s;
    } catch (const BitmapSubtitleError&) {
        throw;
    } catch (const JsonError&) {
        throw BitmapSubtitleError("invalid bitmap subtitle payload");
    } catch (const CasuError&) {
        throw BitmapSubtitleError("invalid bitmap subtitle payload");
    }
}

// --- attachments -------------------------------------------------------------
std::string encode_attachment(const std::string& filename,
                              const std::string& media_type,
                              const std::vector<uint8_t>& data,
                              const char* role) {
    const std::string original_name = filename;
    // Basename after normalizing backslashes (encode rejects any separator).
    const std::string normalized = [&] {
        std::string s = original_name;
        std::replace(s.begin(), s.end(), '\\', '/');
        const std::size_t slash = s.rfind('/');
        return slash == std::string::npos ? s : s.substr(slash + 1);
    }();
    if (normalized.empty() || normalized == "." || normalized == ".." ||
        normalized != original_name || normalized.size() > 4096 ||
        media_type.size() > 1024)
        throw AttachmentPayloadError(
            "attachment filename must be a safe basename");
    if (data.size() > MAX_ATTACHMENT_BYTES)
        throw AttachmentPayloadError("attachment exceeds size limit");
    const std::vector<uint8_t> compressed =
        compress_zlib_impl(data.data(), data.size());
    const std::shared_ptr<JsonObject> meta = std::make_shared<JsonObject>();
    meta->items["version"] = JsonValue(int64_t(1));
    meta->items["filename"] = JsonValue(normalized);
    meta->items["media_type"] = JsonValue(media_type);
    meta->items["raw_length"] = JsonValue(int64_t(data.size()));
    meta->items["compressed_length"] = JsonValue(int64_t(compressed.size()));
    meta->items["compression"] = JsonValue(std::string("zlib"));
    meta->items["sha256"] = JsonValue(Sha256::oneshot(data.data(), data.size()));
    if (role != nullptr) {
        const std::string normalized_role = [&] {
            std::string r = role;
            std::size_t b = r.find_first_not_of(" \t\n\r\f\v");
            std::size_t e = r.find_last_not_of(" \t\n\r\f\v");
            return b == std::string::npos
                       ? std::string()
                       : r.substr(b, e - b + 1);
        }();
        if (normalized_role.empty() || normalized_role.size() > 64)
            throw AttachmentPayloadError("attachment role is invalid");
        meta->items["role"] = JsonValue(normalized_role);
    }
    std::vector<std::string> blobs{std::string(compressed.begin(),
                                               compressed.end())};
    return envelope_pack(JsonValue(meta), blobs);
}

Attachment decode_attachment(const std::string& payload) {
    try {
        if (payload.size() < U32_SIZE)
            throw AttachmentPayloadError("truncated attachment");
        const uint32_t length = get_u32be(payload, 0);
        if (uint64_t(length) > payload.size() - U32_SIZE ||
            length > MAX_AUDIO_METADATA_BYTES)
            throw AttachmentPayloadError("invalid attachment metadata length");
        const JsonValue meta =
            parse_strict_json(payload.data() + U32_SIZE, length);
        if (!meta.is_object())
            throw CasuError("metadata is not an object");
        const auto expected_opt = coerce_int(meta.find("raw_length"));
        if (!expected_opt) throw CasuError("missing raw length");
        const int64_t expected = *expected_opt;
        const JsonValue* version = meta.find("version");
        const JsonValue* compression = meta.find("compression");
        const bool compression_ok =
            compression == nullptr ||
            (compression->is_string() && compression->as_string() == "zlib");
        if (!version || !version->is_int() || version->as_int() != 1 ||
            !compression_ok || expected < 0 ||
            uint64_t(expected) > MAX_ATTACHMENT_BYTES)
            throw CasuError("attachment header mismatch");
        const JsonValue* cl = meta.find("compressed_length");
        const auto compressed_length = cl ? coerce_int(cl) : std::nullopt;
        const BlobView blob{
            reinterpret_cast<const uint8_t*>(payload.data()) + U32_SIZE +
                length,
            payload.size() - U32_SIZE - length};
        if (!compressed_length ||
            static_cast<int64_t>(blob.size) != *compressed_length)
            throw CasuError("compressed length mismatch");
        std::vector<uint8_t> raw = decompress_exact(blob.data, blob.size,
                                                    uint64_t(expected));
        const JsonValue* fn = meta.find("filename");
        const JsonValue* mt = meta.find("media_type");
        if (!fn || !fn->is_string() || !mt)
            throw CasuError("missing attachment fields");
        const std::string filename = fn->as_string();
        std::string basename_check = filename;
        std::replace(basename_check.begin(), basename_check.end(), '\\', '/');
        const std::size_t slash = basename_check.rfind('/');
        const std::string base = slash == std::string::npos
                                     ? basename_check
                                     : basename_check.substr(slash + 1);
        if (base != filename || filename.empty() || filename == "." ||
            filename == ".." || filename.size() > 4096 ||
            mt->as_string().size() > 1024)
            throw CasuError("unsafe attachment filename/media type");
        const JsonValue* sha = meta.find("sha256");
        if (!sha || !sha->is_string() ||
            Sha256::oneshot(raw.data(), raw.size()) != sha->as_string())
            throw CasuError("attachment digest mismatch");
        Attachment a;
        a.filename = filename;
        a.media_type = coerce_str(*mt);
        a.data = std::move(raw);
        a.sha256 = sha->as_string();
        const JsonValue* role_value = meta.find("role");
        if (role_value && !role_value->is_null()) {
            if (!role_value->is_string()) throw CasuError("bad role");
            const std::string role = role_value->as_string();
            std::size_t b = role.find_first_not_of(" \t\n\r\f\v");
            if (b == std::string::npos || role.size() > 64)
                throw CasuError("bad role");
            a.has_role = true;
            a.role = role;
        }
        return a;
    } catch (const AttachmentPayloadError&) {
        throw;
    } catch (const JsonError&) {
        throw AttachmentPayloadError("invalid attachment payload");
    } catch (const CasuError&) {
        throw AttachmentPayloadError("invalid attachment payload");
    }
}

// --- structural + semantic validation ---------------------------------------
namespace {

// Port of _bounded_json_tree: node/depth/string-byte limits over a parsed
// document. Integer range and float finiteness are already enforced by the
// hardened parser.
void bounded_json_tree(const JsonValue& value, const CasuLimits& limits) {
    struct Frame {
        const JsonValue* value;
        uint32_t depth;
    };
    std::vector<Frame> stack;
    stack.push_back({&value, 0});
    uint64_t nodes = 0;
    uint64_t string_bytes = 0;
    while (!stack.empty()) {
        const Frame frame = stack.back();
        stack.pop_back();
        ++nodes;
        if (nodes > limits.max_json_nodes || frame.depth > limits.max_json_depth)
            throw NativeV2ValidationError(
                "CASUNAT2 JSON structure exceeds limits");
        if (frame.value->is_object()) {
            for (const auto& [k, child] : frame.value->as_object().items) {
                string_bytes += k.size();
                if (string_bytes > limits.max_manifest_bytes)
                    throw NativeV2ValidationError(
                        "CASUNAT2 JSON strings exceed limits");
                stack.push_back({&child, frame.depth + 1});
            }
        } else if (frame.value->is_array()) {
            for (const JsonValue& child : frame.value->as_array().items)
                stack.push_back({&child, frame.depth + 1});
        } else if (frame.value->is_string()) {
            string_bytes += frame.value->as_string().size();
            if (string_bytes > limits.max_manifest_bytes)
                throw NativeV2ValidationError(
                    "CASUNAT2 JSON strings exceed limits");
        }
    }
}

std::pair<int64_t, int64_t> time_base(const JsonValue* value) {
    if (!value || !value->is_array() ||
        value->as_array().items.size() != 2 ||
        value->as_array().items[0].is_bool() ||
        value->as_array().items[1].is_bool())
        throw NativeV2ValidationError(
            "CASUNAT2 stream has an invalid time base");
    const auto n = coerce_int(&value->as_array().items[0]);
    const auto d = coerce_int(&value->as_array().items[1]);
    if (!n || !d || *n <= 0 || *d <= 0 ||
        std::max(*n, *d) > INT64_MAX)
        throw NativeV2ValidationError(
            "CASUNAT2 stream has an invalid time base");
    return {*n, *d};
}

}  // namespace

bool json_equal(const JsonValue& a, const JsonValue& b) {
    auto numeric = [](const JsonValue& v) -> bool {
        return v.is_int() || v.is_double();
    };
    auto as_double = [](const JsonValue& v) -> double {
        return v.is_int() ? static_cast<double>(v.as_int()) : v.as_double();
    };
    if (a.kind() == JsonValue::Kind::Null ||
        b.kind() == JsonValue::Kind::Null)
        return a.is_null() && b.is_null();
    if (numeric(a) && numeric(b)) {
        if (a.is_int() && b.is_int()) return a.as_int() == b.as_int();
        return as_double(a) == as_double(b);
    }
    if (a.kind() != b.kind()) return false;
    switch (a.kind()) {
        case JsonValue::Kind::Bool: return a.as_bool() == b.as_bool();
        case JsonValue::Kind::String: return a.as_string() == b.as_string();
        case JsonValue::Kind::Array: {
            const auto& x = a.as_array().items;
            const auto& y = b.as_array().items;
            if (x.size() != y.size()) return false;
            for (std::size_t i = 0; i < x.size(); ++i)
                if (!json_equal(x[i], y[i])) return false;
            return true;
        }
        case JsonValue::Kind::Object: {
            const auto& x = a.as_object().items;
            const auto& y = b.as_object().items;
            if (x.size() != y.size()) return false;
            auto xi = x.begin();
            auto yi = y.begin();
            for (; xi != x.end(); ++xi, ++yi) {
                if (xi->first != yi->first) return false;
                if (!json_equal(xi->second, yi->second)) return false;
            }
            return true;
        }
        default: return false;
    }
}

std::map<int64_t, JsonValue> validate_manifest(const JsonValue& manifest,
                                               const CasuLimits& limits) {
    limits.validate();
    if (!manifest.is_object())
        throw NativeV2ValidationError("CASUNAT2 manifest must be an object");
    bounded_json_tree(manifest, limits);
    const JsonValue* format = manifest.find("format");
    const JsonValue* version = manifest.find("version");
    if (!format || !format->is_string() || format->as_string() != "CASUNAT2" ||
        !version || !version->is_int() || version->as_int() != 2)
        throw NativeV2ValidationError(
            "CASUNAT2 manifest format/version is invalid");
    const JsonValue* streams = manifest.find("streams");
    if (!streams || !streams->is_array() ||
        streams->as_array().items.size() > limits.max_streams)
        throw NativeV2ValidationError(
            "CASUNAT2 manifest stream table is invalid");
    std::map<int64_t, JsonValue> descriptors;
    static const std::set<std::string> valid_kinds = {"video", "audio",
                                                      "subtitle", "attachment"};
    for (const JsonValue& descriptor : streams->as_array().items) {
        if (!descriptor.is_object())
            throw NativeV2ValidationError(
                "CASUNAT2 stream descriptor is invalid");
        const JsonValue* sid = descriptor.find("stream_id");
        // Strict int (no coercion, no bool).
        if (!sid || sid->is_bool() || !sid->is_int())
            throw NativeV2ValidationError(
                "CASUNAT2 stream id is invalid or duplicated");
        const int64_t stream_id = sid->as_int();
        if (stream_id <= 0 || uint64_t(stream_id) > limits.max_streams ||
            descriptors.count(stream_id))
            throw NativeV2ValidationError(
                "CASUNAT2 stream id is invalid or duplicated");
        const JsonValue* kind_value = descriptor.find("type");
        if (!kind_value || !kind_value->is_string() ||
            !valid_kinds.count(kind_value->as_string()))
            throw NativeV2ValidationError("CASUNAT2 stream type is invalid");
        time_base(descriptor.find("time_base"));
        const std::string kind = kind_value->as_string();
        if (kind == "audio") {
            const auto rate = coerce_int(descriptor.find("sample_rate"));
            const auto channels = coerce_int(descriptor.find("channels"));
            if (!rate || !channels)
                throw NativeV2ValidationError(
                    "CASUNAT2 audio descriptor is incomplete");
            if (!(*rate > 0 && uint64_t(*rate) <= limits.max_sample_rate &&
                  *channels > 0 && uint64_t(*channels) <= limits.max_channels))
                throw NativeV2ValidationError(
                    "CASUNAT2 audio descriptor exceeds limits");
        }
        if (kind == "video") {
            const JsonValue* width = descriptor.find("width");
            const JsonValue* height = descriptor.find("height");
            if (width != nullptr || height != nullptr) {
                const auto w = coerce_int(width);
                const auto h = coerce_int(height);
                if (!w || !h)
                    throw NativeV2ValidationError(
                        "CASUNAT2 video geometry is invalid");
                if (!(*w > 0 && uint64_t(*w) <= limits.max_width && *h > 0 &&
                      uint64_t(*h) <= limits.max_height))
                    throw NativeV2ValidationError(
                        "CASUNAT2 video geometry exceeds limits");
            }
        }
        const JsonValue* timeline_value =
            descriptor.find("frame_timeline");
        static const JsonValue kEmptyTimeline =
            make_array(std::vector<JsonValue>{});
        if (timeline_value == nullptr)
            timeline_value = &kEmptyTimeline;  // default [] in the reference
        if (!timeline_value->is_array()) {
            throw NativeV2ValidationError(
                "CASUNAT2 frame timeline is invalid");
        } else {
            const JsonArray& timeline = timeline_value->as_array();
            if (timeline.items.size() > limits.max_chunks)
                throw NativeV2ValidationError(
                    "CASUNAT2 frame timeline is invalid");
            bool has_previous = false;
            int64_t previous_pts = 0;
            for (const JsonValue& frame : timeline.items) {
                if (!frame.is_object())
                    throw NativeV2ValidationError(
                        "CASUNAT2 frame timeline entry is invalid");
                const JsonValue* pts_value = frame.find("pts");
                if (!pts_value || pts_value->is_bool())
                    throw NativeV2ValidationError(
                        "CASUNAT2 frame timeline entry is invalid");
                const auto pts = coerce_int(pts_value);
                if (!pts)
                    throw NativeV2ValidationError(
                        "CASUNAT2 frame timeline entry is invalid");
                const JsonValue* duration = frame.find("duration_pts");
                if (duration && !duration->is_null()) {
                    const auto d = coerce_int(duration);
                    if (!d || *d < 0)
                        throw NativeV2ValidationError(
                            "CASUNAT2 frame timeline entry is invalid");
                }
                if (has_previous && *pts < previous_pts)
                    throw NativeV2ValidationError(
                        "CASUNAT2 frame timeline is not ordered");
                previous_pts = *pts;
                has_previous = true;
            }
        }
        descriptors[stream_id] = descriptor;
    }
    const JsonValue* provenance = manifest.find("source_provenance");
    if (provenance && provenance->is_object()) {
        if (provenance->find("path") || provenance->find("source_path") ||
            provenance->find("absolute_path"))
            throw NativeV2ValidationError(
                "CASUNAT2 source provenance must not contain a path");
        const JsonValue* filename = provenance->find("filename");
        if (filename && !filename->is_null()) {
            if (!filename->is_string() || filename->as_string().empty())
                throw NativeV2ValidationError(
                    "CASUNAT2 source filename is unsafe");
            std::string name = filename->as_string();
            std::replace(name.begin(), name.end(), '\\', '/');
            const std::size_t slash = name.rfind('/');
            const std::string base = slash == std::string::npos
                                         ? name
                                         : name.substr(slash + 1);
            if (base != filename->as_string())
                throw NativeV2ValidationError(
                    "CASUNAT2 source filename is unsafe");
        }
    }
    return descriptors;
}

NativeV2PayloadValidator::NativeV2PayloadValidator(const JsonValue& manifest,
                                                   const CasuLimits& limits,
                                                   bool semantic)
    : limits_(limits), semantic_(semantic) {
    descriptors_ = validate_manifest(manifest, limits_);
    for (const auto& [stream_id, descriptor] : descriptors_) {
        const JsonValue* type = descriptor.find("type");
        if (type && type->is_string() && type->as_string() == "video") {
            video_[stream_id];
            video_needs_key_[stream_id] = false;
            video_dependency_depth_[stream_id] = 0;
        }
    }
}

namespace {

const char* chunk_type_name(uint8_t kind) {
    switch (kind) {
        case STREAM_CONFIG: return "STREAM_CONFIG";
        case VIDEO_KEY_STATE: return "VIDEO_KEY_STATE";
        case VIDEO_TILE_UPDATE: return "VIDEO_TILE_UPDATE";
        case VIDEO_FORMAT_CHANGE: return "VIDEO_FORMAT_CHANGE";
        case AUDIO_BLOCK: return "AUDIO_BLOCK";
        case SUBTITLE_PACKET: return "SUBTITLE_PACKET";
        case SUBTITLE_BITMAP: return "SUBTITLE_BITMAP";
        case CHAPTER_TABLE: return "CHAPTER_TABLE";
        case ATTACHMENT: return "ATTACHMENT";
        case RECOVERY_POINT: return "RECOVERY_POINT";
        case SEEK_INDEX: return "SEEK_INDEX";
        case INTEGRITY_TABLE: return "INTEGRITY_TABLE";
        case END: return "END";
        default: return "UNKNOWN";
    }
}

bool is_global_chunk(uint8_t kind) {
    switch (kind) {
        case CHAPTER_TABLE:
        case RECOVERY_POINT:
        case SEEK_INDEX:
        case INTEGRITY_TABLE:
        case END:
            return true;
        default:
            return false;
    }
}

// Expected stream kinds per stream-chunk type (empty = STREAM_CONFIG).
std::string expected_stream_kind(uint8_t kind) {
    switch (kind) {
        case VIDEO_KEY_STATE:
        case VIDEO_TILE_UPDATE:
        case VIDEO_FORMAT_CHANGE:
            return "video";
        case AUDIO_BLOCK:
            return "audio";
        case SUBTITLE_PACKET:
        case SUBTITLE_BITMAP:
            return "subtitle";
        case ATTACHMENT:
            return "attachment|subtitle";  // either is valid
        default:
            return {};
    }
}

}  // namespace

void NativeV2PayloadValidator::feed(uint8_t chunk_type, uint8_t stream_id,
                                    uint16_t flags, int64_t pts,
                                    const std::string& payload,
                                    std::optional<uint64_t> uncompressed_length,
                                    bool allow_system) {
    if (flags != 0)
        throw NativeV2ValidationError("CASUNAT2 chunk uses unknown flags");
    if (uncompressed_length.has_value()) {
        const uint64_t value = *uncompressed_length;
        if (value < payload.size() || value > limits_.max_chunk_bytes)
            throw NativeV2ValidationError(
                "CASUNAT2 uncompressed chunk length is invalid");
    }
    const uint8_t kind = chunk_type;
    if (is_global_chunk(kind)) {
        if (stream_id != 0)
            throw NativeV2ValidationError(
                "CASUNAT2 global chunk has a stream id");
        if (!allow_system && (kind == RECOVERY_POINT || kind == SEEK_INDEX ||
                              kind == INTEGRITY_TABLE || kind == END))
            throw NativeV2ValidationError(
                "reserved CASUNAT2 chunk supplied to writer");
        if (kind == SEEK_INDEX || kind == INTEGRITY_TABLE || kind == END) {
            if (system_seen_.count(kind))
                throw NativeV2ValidationError(
                    "duplicate CASUNAT2 structural chunk");
            system_seen_.insert(kind);
        }
        if (kind == CHAPTER_TABLE) {
            if (chapter_seen_)
                throw NativeV2ValidationError(
                    "duplicate CASUNAT2 chapter table");
            chapter_seen_ = true;
            if (semantic_) decode_chapter_table(payload);
        }
        return;
    }
    if (kind == STREAM_CONFIG) {
        if (!descriptors_.count(stream_id))
            throw NativeV2ValidationError(
                "CASUNAT2 chunk references an unknown stream");
    } else if (!descriptors_.count(stream_id)) {
        throw NativeV2ValidationError(
            "CASUNAT2 chunk references an unknown stream");
    }
    const JsonValue& descriptor = descriptors_.at(stream_id);
    const std::string expected_kind = expected_stream_kind(kind);
    if (!expected_kind.empty()) {
        const JsonValue* type = descriptor.find("type");
        const std::string actual =
            type && type->is_string() ? type->as_string() : std::string();
        bool matches = false;
        if (kind == ATTACHMENT)
            matches = actual == "attachment" || actual == "subtitle";
        else
            matches = actual == expected_kind;
        if (!matches)
            throw NativeV2ValidationError(
                "CASUNAT2 chunk type does not match its stream");
    }
    if (kind == STREAM_CONFIG) {
        if (stream_configs_.count(stream_id))
            throw NativeV2ValidationError("duplicate CASUNAT2 stream config");
        stream_configs_.insert(stream_id);
        if (semantic_) {
            try {
                const JsonValue configured =
                    parse_strict_json(payload);
                if (!json_equal(configured, descriptor))
                    throw NativeV2ValidationError(
                        "CASUNAT2 stream config differs from manifest");
            } catch (const JsonError&) {
                throw NativeV2ValidationError(
                    "invalid CASUNAT2 stream config");
            }
        }
        return;
    }
    if (kind != ATTACHMENT) {
        auto previous = last_pts_.find(stream_id);
        if (previous != last_pts_.end() && pts < previous->second)
            throw NativeV2ValidationError(
                "CASUNAT2 stream chunks are not PTS ordered");
        last_pts_[stream_id] = pts;
    }
    if (kind == VIDEO_FORMAT_CHANGE) {
        if (video_needs_key_[stream_id])
            throw NativeV2ValidationError(
                "video format change is not followed by a key state");
        video_needs_key_[stream_id] = true;
    } else if (kind == VIDEO_KEY_STATE) {
        video_needs_key_[stream_id] = false;
        video_dependency_depth_[stream_id] = 0;
    } else if (kind == VIDEO_TILE_UPDATE &&
               video_needs_key_[stream_id]) {
        throw NativeV2ValidationError(
            "video format change is not followed by a key state");
    } else if (kind == VIDEO_TILE_UPDATE) {
        int64_t depth = 0;
        auto it = video_dependency_depth_.find(stream_id);
        if (it != video_dependency_depth_.end()) depth = it->second;
        ++depth;
        if (depth > int64_t(limits_.max_dependency_depth))
            throw NativeV2ValidationError(
                "CASUNAT2 video dependency depth exceeds limit");
        video_dependency_depth_[stream_id] = depth;
    }
    if (!semantic_) return;

    // Semantic payload decoding — errors are wrapped like the reference.
    try {
        switch (kind) {
            case VIDEO_KEY_STATE: {
                CanonicalFrame frame =
                    decode_key_state(payload, limits_);
                video_.at(stream_id).set_frame(std::move(frame));
                const CanonicalFrame& stored = *video_.at(stream_id).frame();
                JsonValue override_format;
                auto oit = video_format_override_.find(stream_id);
                if (oit != video_format_override_.end()) {
                    override_format = oit->second;
                    video_format_override_.erase(oit);
                }
                const JsonValue* width_field = descriptor.find("width");
                const JsonValue* height_field = descriptor.find("height");
                const JsonValue* pixfmt_field = descriptor.find("pix_fmt");
                std::optional<int64_t> expected_width;
                std::optional<int64_t> expected_height;
                std::optional<std::string> expected_pixel_format;
                if (!override_format.is_null()) {
                    const JsonValue* shape =
                        override_format.find("source_shape");
                    if (shape && shape->is_array() &&
                        shape->as_array().items.size() == 2) {
                        expected_width =
                            coerce_int(&shape->as_array().items[1]);
                        expected_height =
                            coerce_int(&shape->as_array().items[0]);
                    }
                    const JsonValue* pf =
                        override_format.find("pixel_format");
                    if (pf && pf->is_string())
                        expected_pixel_format = pf->as_string();
                } else {
                    if (width_field)
                        expected_width = coerce_int(width_field);
                    if (height_field)
                        expected_height = coerce_int(height_field);
                    if (pixfmt_field && pixfmt_field->is_string())
                        expected_pixel_format = pixfmt_field->as_string();
                }
                if (expected_width.has_value() &&
                    (stored.shape().second != *expected_width ||
                     stored.shape().first != *expected_height))
                    throw NativeV2ValidationError(
                        "video key state geometry differs from manifest");
                if (expected_pixel_format.has_value() &&
                    stored.pixel_format != *expected_pixel_format)
                    throw NativeV2ValidationError(
                        "video key state format differs from manifest");
                break;
            }
            case VIDEO_TILE_UPDATE:
                video_.at(stream_id).apply_tile_update(payload, limits_);
                break;
            case VIDEO_FORMAT_CHANGE: {
                const JsonValue value = decode_format_change(payload);
                video_format_override_[stream_id] = value;
                video_.at(stream_id).clear_frame();
                break;
            }
            case AUDIO_BLOCK: {
                const AudioBlock block = decode_audio_block(payload);
                bool differs = block.pts != pts;
                if (!differs) {
                    const JsonValue* tb = descriptor.find("time_base");
                    if (!tb || !tb->is_array() ||
                        tb->as_array().items.size() != 2)
                        throw CasuError("descriptor lacks time base");
                    const auto n = coerce_int(&tb->as_array().items[0]);
                    const auto d = coerce_int(&tb->as_array().items[1]);
                    differs = !n || !d ||
                              block.time_base_num != *n ||
                              block.time_base_den != *d;
                }
                if (!differs) {
                    const auto rate =
                        coerce_int(descriptor.find("sample_rate"));
                    const auto channels =
                        coerce_int(descriptor.find("channels"));
                    differs = !rate || !channels ||
                              block.sample_rate != *rate ||
                              block.channels != *channels;
                }
                if (differs)
                    throw NativeV2ValidationError(
                        "audio block differs from stream descriptor");
                break;
            }
            case SUBTITLE_PACKET: {
                const SubtitlePacket packet =
                    decode_subtitle_packet(payload);
                if (packet.start_pts != pts)
                    throw NativeV2ValidationError(
                        "subtitle packet PTS differs from chunk");
                break;
            }
            case SUBTITLE_BITMAP: {
                const BitmapSubtitle packet =
                    decode_bitmap_subtitle(payload);
                if (packet.start_pts != pts)
                    throw NativeV2ValidationError(
                        "bitmap subtitle PTS differs from chunk");
                break;
            }
            case ATTACHMENT: {
                const Attachment attachment = decode_attachment(payload);
                const JsonValue* role = descriptor.find("role");
                if (role && !role->is_null()) {
                    if (!role->is_string() || attachment.role != role->as_string())
                        throw NativeV2ValidationError(
                            "attachment role differs from descriptor");
                }
                break;
            }
            default:
                break;
        }
    } catch (const NativeV2ValidationError&) {
        throw;
    } catch (const CasuError&) {
        throw NativeV2ValidationError("invalid CASUNAT2 " +
                                      std::string(chunk_type_name(kind)) +
                                      " payload");
    }
}

void NativeV2PayloadValidator::finalize(bool require_system) {
    for (const auto& [stream_id, needs_key] : video_needs_key_) {
        if (needs_key)
            throw NativeV2ValidationError(
                "video format change is not followed by a key state");
    }
    if (require_system &&
        !(system_seen_.count(SEEK_INDEX) && system_seen_.count(INTEGRITY_TABLE) &&
          system_seen_.count(END)))
        throw NativeV2ValidationError(
            "CASUNAT2 structural chunks are incomplete");
}


std::vector<StrictTileState> compare_frames(
    const CanonicalFrame* previous, const CanonicalFrame& current,
    int64_t tile_width, int64_t tile_height,
    const std::map<std::array<int64_t, 4>, std::string>* previous_hashes) {
    if (tile_width <= 0 || tile_height <= 0)
        throw CasuError("tile dimensions must be positive");
    bool format_change = previous == nullptr;
    if (previous != nullptr &&
        !(previous->format_identity() == current.format_identity()))
        format_change = true;
    const std::string current_prefix = frame_identity_prefix(current);
    std::optional<std::string> previous_prefix;
    if (previous != nullptr && !format_change && previous_hashes == nullptr)
        previous_prefix = frame_identity_prefix(*previous);
    std::vector<StrictTileState> result;
    const auto [height, width] = current.shape();
    int64_t ordinal = 0;
    for (int64_t y = 0; y < height; y += tile_height) {
        for (int64_t x = 0; x < width; x += tile_width) {
            const int64_t tw = std::min(tile_width, width - x);
            const int64_t th = std::min(tile_height, height - y);
            char tile_id[32];
            std::snprintf(tile_id, sizeof(tile_id), "tile-%08lld",
                          static_cast<long long>(ordinal));
            ++ordinal;
            StrictTileState state;
            state.tile_id = tile_id;
            state.x = x;
            state.y = y;
            state.w = tw;
            state.h = th;
            state.state_hash =
                tile_digest_with_prefix(current, x, y, tw, th, current_prefix);
            state.plane_count = static_cast<int>(current.planes.size());
            state.format_change = format_change;
            if (previous != nullptr && !format_change) {
                const std::array<int64_t, 4> region{x, y, tw, th};
                if (previous_hashes != nullptr) {
                    auto it = previous_hashes->find(region);
                    if (it != previous_hashes->end()) {
                        state.has_reference = true;
                        state.reference_hash = it->second;
                    } else {
                        state.has_reference = true;
                        state.reference_hash =
                            canonical_tile_hash(*previous, x, y, tw, th);
                    }
                } else if (previous_prefix.has_value()) {
                    state.has_reference = true;
                    state.reference_hash = tile_digest_with_prefix(
                        *previous, x, y, tw, th, *previous_prefix);
                }
                state.state = state.state_hash == state.reference_hash
                                  ? "HOLD"
                                  : "UPDATE";
            } else {
                state.state = "KEY_STATE";
            }
            result.push_back(std::move(state));
        }
    }
    return result;
}

}  // namespace casu::natv2
