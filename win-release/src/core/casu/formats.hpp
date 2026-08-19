// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CASU container format primitives: content-based kind detection, header and
// chunk parsing for CASUNAT1/CASUNAT2/MP5. Ported from casu/ (reference).
#pragma once
#include <cstdint>
#include <cstddef>
#include <string>
#include <vector>
#include <stdexcept>

namespace casu {

// ---------------------------------------------------------------------------
// Typed errors
// ---------------------------------------------------------------------------
class CasuError : public std::runtime_error {
public:
    explicit CasuError(const std::string& msg) : std::runtime_error(msg) {}
};

// ---------------------------------------------------------------------------
// Content-based representation kind detection
// ---------------------------------------------------------------------------
enum class CasuKind {
    None,         // not a recognised CASU container
    Casunat1,     // "CASUNAT1"
    Casunat2,     // "CASUNAT2"
    Mp5,          // "CASUMP5\0"
    Sidecar,      // JSON sidecar manifest
};

// Returns the kind from the leading bytes of a file (bounded read).
CasuKind detect_casu_kind(const std::string& path);

// ---------------------------------------------------------------------------
// Fail-closed limits (mirror of casu/native_v2/format.py CasuLimits)
// ---------------------------------------------------------------------------
struct CasuLimits {
    uint64_t max_file_bytes = 4ULL * 1024 * 1024 * 1024;
    uint64_t max_manifest_bytes = 64ULL * 1024 * 1024;
    uint32_t max_streams = 255;
    uint64_t max_chunks = 10'000'000;
    uint64_t max_chunk_bytes = 512ULL * 1024 * 1024;
    uint64_t max_attachment_bytes = 64ULL * 1024 * 1024;
    uint64_t max_total_uncompressed_frame_bytes = 512ULL * 1024 * 1024;
    uint32_t max_width = 32'768;
    uint32_t max_height = 32'768;
    uint32_t max_channels = 64;
    uint32_t max_sample_rate = 768'000;
};

// ---------------------------------------------------------------------------
// CASUNAT2 binary layout (big-endian)
//   HEADER       : magic[8] "CASUNAT2" | version u16 | flags u16 | manifest_len u64  (20 B)
//   CHUNK_HEADER : type u8 | stream u8 | flags u16 | pts i64 | payload_len u64 | uncompressed_len u64 (27 B)
// ---------------------------------------------------------------------------
namespace casunat2 {
constexpr uint64_t MAGIC_LO = 0x43415355;  // "CASU"
constexpr uint64_t MAGIC_HI = 0x4E415432;  // "NAT2"
constexpr uint16_t VERSION = 2;
constexpr std::size_t HEADER_SIZE = 20;
// CHUNK_HEADER is ">BBHqQQ" = 1+1+2+8+8+8 = 28 bytes (big-endian).
constexpr std::size_t CHUNK_HEADER_SIZE = 28;

enum ChunkType : uint8_t {
    STREAM_CONFIG = 1,
    VIDEO_KEY_STATE = 16,
    VIDEO_TILE_UPDATE = 17,
    VIDEO_FORMAT_CHANGE = 18,
    AUDIO_BLOCK = 32,
    SUBTITLE_PACKET = 48,
    SUBTITLE_BITMAP = 49,
    CHAPTER_TABLE = 64,
    ATTACHMENT = 65,
    RECOVERY_POINT = 224,
    SEEK_INDEX = 240,
    INTEGRITY_TABLE = 241,
    END = 255,
};

struct Header {
    uint16_t version = 0;
    uint16_t flags = 0;
    uint64_t manifest_length = 0;
};

struct ChunkHeader {
    uint8_t chunk_type = 0;
    uint8_t stream_id = 0;
    uint16_t flags = 0;
    int64_t pts = 0;
    uint64_t payload_length = 0;
    uint64_t uncompressed_length = 0;
    uint64_t offset = 0;  // file offset of the payload
};

// Parse the 20-byte CASUNAT2 file header (big-endian).
Header parse_header(const uint8_t* p, std::size_t n);

// Parse a 27-byte chunk header (big-endian). Returns the payload offset.
ChunkHeader parse_chunk_header(const uint8_t* p, std::size_t n, uint64_t chunk_start);

// Validate a file as CASUNAT2: header magic/version, bounded manifest length,
// and walk chunk headers to the END marker (bounded by limits). Returns the
// number of chunks, or throws CasuError on structural failure.
uint64_t validate_file(const std::string& path, const CasuLimits& limits = CasuLimits());
}  // namespace casunat2

// ---------------------------------------------------------------------------
// MP5 layout (mirror of casu/mp5/format.py): MAGIC "CASUMP5\0", version u16,
// flags u16, manifest_len u32, reserved u32 (HEADER = "<8sHHII" = 20 B)
// ---------------------------------------------------------------------------
namespace mp5 {
constexpr std::size_t HEADER_SIZE = 20;
bool looks_like_mp5(const uint8_t* p, std::size_t n);
}

}  // namespace casu
