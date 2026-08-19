// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CASU MP5 container reader/writer (WP-CORE-005). Port of casu/mp5/.
//   MAGIC "CASUMP5\0", version 1
//   HEADER "<8sHHII" = 24 bytes: magic(8)|version u16|flags u16|
//     manifest_length u32|reserved u32
//   CHUNK_HEADER "<BHII" = 11 bytes: chunk_type u8|stream_id u8|pts u32|
//     comp_length u32
//   payloads compressed (zstd with zlib fallback in the reference; this port
//   uses zlib, the reference behaviour when zstd is unavailable)
//   FOOTER "<I32s" = 36 bytes: chunk_count u32|manifest_sha256(32)
#pragma once
#include "casu/json.hpp"
#include <cstdint>
#include <string>
#include <vector>

namespace casu {
namespace mp5 {

// HEADER_SIZE (24) is defined in formats.hpp (casu::mp5 namespace).
constexpr std::size_t CHUNK_HEADER_SIZE = 11;
constexpr std::size_t FOOTER_SIZE = 36;
constexpr uint16_t VERSION = 1;

// Chunk types (mirror of casu/mp5/format.py ChunkType).
enum ChunkType : uint8_t {
    STREAM_CONFIG = 0x01,
    VIDEO_KEY_STATE = 0x10,
    VIDEO_TILE_UPDATE = 0x11,
    VIDEO_FORMAT_CHANGE = 0x12,
    AUDIO_BLOCK = 0x20,
    SUBTITLE_PACKET = 0x30,
    SUBTITLE_BITMAP = 0x31,
    CHAPTER_TABLE = 0x40,
    ATTACHMENT = 0x50,
    SEEK_INDEX = 0x60,
    INTEGRITY_TABLE = 0x70,
    RECOVERY_POINT = 0x71,
    METADATA = 0x80,
    END = 0xFF,
};

struct ChunkSummary {
    ChunkType chunk_type = END;
    uint8_t stream_id = 0;
    uint32_t pts = 0;
    uint32_t comp_length = 0;
    uint64_t offset = 0;
};

struct Container {
    std::string path;
    JsonValue manifest;
    std::vector<ChunkSummary> chunks;
    uint64_t size = 0;

    // Decompress + read a single chunk's payload.
    std::vector<uint8_t> read_chunk_payload(const ChunkSummary& c) const;
};

// Read the MP5 header + chunk table (no full payload load).
Container read_mp5(const std::string& path);

// Write an MP5 file with zlib-compressed chunk payloads + footer.
// `chunks` = (chunk_type, stream_id, pts, raw_payload). Throws CasuError.
void write_mp5(const std::string& output, const JsonValue& manifest,
               const std::vector<std::tuple<ChunkType, uint8_t, uint32_t, std::vector<uint8_t>>>& chunks);

// Extract the embedded original source (attachment chunks), verifying sha256.
// Returns (filename, payload_bytes).
std::pair<std::string, std::vector<uint8_t>> extract_attachment(const std::string& path);

// Integrity check; returns problems (empty = valid).
std::vector<std::string> verify_mp5(const std::string& path);

}  // namespace mp5
}  // namespace casu
