// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CASUNAT2 payload layer — full port of casu/native_v2/{video,audio,text,
// bitmap,attachment}.py plus casu/strict/{canonical,tiles}.py identity
// hashing. Byte-parity notes:
//  - Envelope: [u32 BE meta_len][sorted-keys JSON][concatenated zlib blobs].
//  - Tile digests hash the Python repr() of tuples/strings ("CASU-STRICT-TILE-v1\0"
//    prefix) so hashes match the reference bit-for-bit.
#pragma once
#include "casu/formats.hpp"
#include "casu/json.hpp"
#include <array>
#include <map>
#include <optional>
#include <set>

namespace casu::natv2 {

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------
class VideoPayloadError : public CasuError {
public:
    explicit VideoPayloadError(const std::string& m) : CasuError(m) {}
};
class AudioPayloadError : public CasuError {
public:
    explicit AudioPayloadError(const std::string& m) : CasuError(m) {}
};
class TextPayloadError : public CasuError {
public:
    explicit TextPayloadError(const std::string& m) : CasuError(m) {}
};
class BitmapSubtitleError : public CasuError {
public:
    explicit BitmapSubtitleError(const std::string& m) : CasuError(m) {}
};
class AttachmentPayloadError : public CasuError {
public:
    explicit AttachmentPayloadError(const std::string& m) : CasuError(m) {}
};
class NativeV2ValidationError : public CasuError {
public:
    explicit NativeV2ValidationError(const std::string& m) : CasuError(m) {}
};

constexpr uint64_t MAX_DECODED_PLANE_BYTES = 512ULL * 1024 * 1024;
constexpr uint64_t MAX_VIDEO_METADATA_BYTES = 1024ULL * 1024;
constexpr uint64_t MAX_DECODED_AUDIO_BYTES = 256ULL * 1024 * 1024;
constexpr uint64_t MAX_AUDIO_METADATA_BYTES = 64ULL * 1024;
constexpr uint64_t MAX_BITMAP_RAW_BYTES = 256ULL * 1024 * 1024;
constexpr uint32_t MAX_BITMAP_DIMENSION = 16'384;
constexpr uint32_t MAX_VIDEO_DIMENSION = 32'768;
constexpr uint64_t MAX_ATTACHMENT_BYTES = 64ULL * 1024 * 1024;
constexpr uint64_t MAX_SUBTITLE_TEXT_BYTES = 1024ULL * 1024;
constexpr uint64_t MAX_CHAPTERS = 100'000;
constexpr uint64_t MAX_CHAPTER_TABLE_BYTES = 64ULL * 1024 * 1024;

// zlib-exact inflate: output must decompress to exactly `expected` bytes,
// stream must end cleanly (no trailing garbage, no truncated input).
std::vector<uint8_t> decompress_exact(const uint8_t* data, std::size_t size,
                                      uint64_t expected);
std::vector<uint8_t> compress_zlib(const uint8_t* data, std::size_t size);

// ---------------------------------------------------------------------------
// Canonical frames (casu/strict/canonical.py)
// ---------------------------------------------------------------------------
struct PlaneLayout {
    int index = 0;
    int width = 0;
    int height = 0;
    int bit_depth = 8;
    int bytes_per_sample = 1;
    int subsample_x = 0;
    int subsample_y = 0;
    int components = 1;

    std::array<int64_t, 8> identity() const {
        return {index, width, height, bit_depth, bytes_per_sample,
                subsample_x, subsample_y, components};
    }
};

struct CanonicalPlane {
    std::vector<uint8_t> data;   // row-major, itemsize-sized samples
    int64_t rows = 0;
    int64_t cols = 0;            // in samples (components included)
    int itemsize = 1;            // 1 or 2
};

struct FormatSpec {
    int bit_depth = 8;
    int bytes_per_sample = 1;
    std::vector<std::array<int, 3>> specs;  // per plane {sub_x, sub_y, components}
};
FormatSpec format_spec(const std::string& pixel_format);

struct CanonicalFrame {
    std::vector<CanonicalPlane> planes;
    std::string pixel_format;
    // Sorted (key, value) pairs == tuple(sorted(color_metadata.items())).
    std::vector<std::pair<std::string, std::string>> color_metadata;
    bool has_source_shape = false;
    int64_t source_width = 0;
    int64_t source_height = 0;
    std::vector<PlaneLayout> plane_layouts;

    std::pair<int64_t, int64_t> shape() const {  // (height, width)
        if (has_source_shape) return {source_height, source_width};
        return {planes.at(0).rows, planes.at(0).cols /
                                       std::max<int64_t>(1, plane_layouts.empty()
                                                    ? 1 : plane_layouts[0].components)};
    }
    std::tuple<int64_t, int64_t, std::string,
               std::vector<std::pair<std::string, std::string>>,
               std::vector<std::array<int64_t, 8>>> format_identity() const;
    // SHA-256 over identity + every plane's raw bytes.
    std::string digest() const;
};

CanonicalFrame canonical_frame(std::vector<CanonicalPlane> planes,
                               const std::string& pixel_format,
                               const std::map<std::string, std::string>& color_metadata,
                               std::optional<std::pair<int64_t, int64_t>> source_shape);

// ---------------------------------------------------------------------------
// Python-repr compatible identity/tile hashing (casu/strict/tiles.py)
// ---------------------------------------------------------------------------
std::string py_repr_int_tuple(const std::vector<int64_t>& values);
std::string py_repr_str_tuple(const std::vector<std::string>& values);
std::string py_repr_str(const std::string& value);
std::string py_repr_region(int64_t x, int64_t y, int64_t w, int64_t h);

std::string frame_identity_prefix_hexless(const CanonicalFrame& frame);  // bytes as std::string
std::string frame_identity_prefix(const CanonicalFrame& frame);
// canonical_tile_hash: sha256(identity + region + tile bytes).
std::string canonical_tile_hash(const CanonicalFrame& frame,
                                int64_t x, int64_t y, int64_t width, int64_t height);
std::string tile_digest_with_prefix(const CanonicalFrame& frame,
                                    int64_t x, int64_t y, int64_t width, int64_t height,
                                    const std::string& prefix);

// ---------------------------------------------------------------------------
// Video payloads (casu/native_v2/video.py)
// ---------------------------------------------------------------------------
std::string encode_key_state(const CanonicalFrame& frame);
CanonicalFrame decode_key_state(const std::string& payload, const CasuLimits& limits);
std::string encode_format_change(const CanonicalFrame& frame);
JsonValue decode_format_change(const std::string& payload);
// Returns packed tile update for a display-space region.
std::string encode_tile_update(const CanonicalFrame& frame,
                               int64_t x, int64_t y, int64_t width, int64_t height,
                               const char* base_state_hash /* nullable */);
void slice_plane_bounds(const PlaneLayout& layout, int64_t x, int64_t y,
                        int64_t w, int64_t h, int64_t& x0, int64_t& y0,
                        int64_t& x1, int64_t& y1);

// TileStateCache: reconstruct a source-resolution frame incrementally.
class TileStateCache {
public:
    void set_frame(CanonicalFrame frame);
    // Clears the cached frame (Python: cache.frame = None).
    void clear_frame() {
        frame_.reset();
        prefix_.reset();
    }
    const CanonicalFrame* frame() const { return frame_.has_value() ? &*frame_ : nullptr; }
    CanonicalFrame apply_key_state(const std::string& payload, const CasuLimits& limits);
    CanonicalFrame apply_tile_update(const std::string& payload, const CasuLimits& limits);

private:
    std::optional<CanonicalFrame> frame_;
    mutable std::optional<std::string> prefix_;
    const std::string& identity_prefix();
};

// ---------------------------------------------------------------------------
// Audio payloads (casu/native_v2/audio.py)
// ---------------------------------------------------------------------------
struct AudioBlock {
    int64_t pts = 0;
    int64_t time_base_num = 0;
    int64_t time_base_den = 0;
    int64_t sample_rate = 0;
    int64_t channels = 0;
    bool has_channel_layout = false;
    std::string channel_layout;
    std::string sample_format;
    int64_t sample_count = 0;
    std::vector<uint8_t> pcm;
};
std::string encode_audio_block(const std::vector<uint8_t>& pcm, int64_t pts,
                               int64_t tb_num, int64_t tb_den, int64_t sample_rate,
                               int64_t channels, const std::string& sample_format,
                               const char* channel_layout, int64_t sample_count);
AudioBlock decode_audio_block(const std::string& payload);

// ---------------------------------------------------------------------------
// Text payloads (casu/native_v2/text.py)
// ---------------------------------------------------------------------------
struct SubtitlePacket {
    int64_t start_pts = 0;
    int64_t end_pts = 0;
    std::string text;
    std::string language = "und";
    std::string format = "text";
};
std::string encode_subtitle_packet(const SubtitlePacket& p);
SubtitlePacket decode_subtitle_packet(const std::string& payload);

struct Chapter {
    int64_t start_pts = 0;
    int64_t end_pts = 0;
    std::string title;
    std::string language = "und";
};
std::string encode_chapter_table(const std::vector<Chapter>& chapters);
std::vector<Chapter> decode_chapter_table(const std::string& payload);

// ---------------------------------------------------------------------------
// Bitmap subtitle payloads (casu/native_v2/bitmap.py)
// ---------------------------------------------------------------------------
struct BitmapSubtitle {
    int64_t start_pts = 0;
    int64_t end_pts = 0;
    int64_t canvas_width = 0;
    int64_t canvas_height = 0;
    int64_t x = 0;
    int64_t y = 0;
    int64_t width = 0;
    int64_t height = 0;
    std::vector<uint8_t> rgba;
    std::string sha256;
};
std::string encode_bitmap_subtitle(int64_t start_pts, int64_t end_pts,
                                   int64_t canvas_width, int64_t canvas_height,
                                   int64_t x, int64_t y,
                                   const uint8_t* rgba, std::size_t rgba_size,
                                   int64_t width, int64_t height);
BitmapSubtitle decode_bitmap_subtitle(const std::string& payload);

// ---------------------------------------------------------------------------
// Attachment payloads (casu/native_v2/attachment.py)
// ---------------------------------------------------------------------------
struct Attachment {
    std::string filename;
    std::string media_type;
    std::vector<uint8_t> data;
    std::string sha256;
    bool has_role = false;
    std::string role;
};
std::string encode_attachment(const std::string& filename,
                              const std::string& media_type,
                              const std::vector<uint8_t>& data,
                              const char* role);
Attachment decode_attachment(const std::string& payload);

// ---------------------------------------------------------------------------
// Structural + semantic validation (casu/native_v2/validation.py)
// ---------------------------------------------------------------------------
// validate_manifest returns the stream descriptor table keyed by stream_id.
std::map<int64_t, JsonValue> validate_manifest(const JsonValue& manifest,
                                               const CasuLimits& limits);

class NativeV2PayloadValidator {
public:
    NativeV2PayloadValidator(const JsonValue& manifest, const CasuLimits& limits,
                             bool semantic);
    // feed one chunk; allow_system=false rejects reserved structural chunks
    // (writer path).
    void feed(uint8_t chunk_type, uint8_t stream_id, uint16_t flags,
              int64_t pts, const std::string& payload,
              std::optional<uint64_t> uncompressed_length,
              bool allow_system);
    void finalize(bool require_system);
    // Validated stream descriptor table (keyed by stream id) — the writer
    // emits canonical STREAM_CONFIG payloads from these.
    const std::map<int64_t, JsonValue>& descriptors() const {
        return descriptors_;
    }

private:
    CasuLimits limits_;
    std::map<int64_t, JsonValue> descriptors_;
    bool semantic_ = false;
    std::map<int64_t, TileStateCache> video_;
    std::map<int64_t, JsonValue> video_format_override_;
    std::map<int64_t, bool> video_needs_key_;
    std::map<int64_t, int64_t> video_dependency_depth_;
    std::map<int64_t, int64_t> last_pts_;
    std::set<int64_t> stream_configs_;
    bool chapter_seen_ = false;
    std::set<uint8_t> system_seen_;
};

// Deep JSON equality mirroring Python == semantics (Int 2 == Double 2.0).
bool json_equal(const JsonValue& a, const JsonValue& b);

}  // namespace casu::natv2
