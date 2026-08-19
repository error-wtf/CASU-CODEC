// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CASUNAT2 native v2 reader (WP-CORE-004). Port of casu/native_v2/reader.py
// integrity surface: header/manifest strict parse, chunk walk with running
// sha256 digest, integrity table (sha256_before_integrity + chunk_sha256
// table) verification, seek index parse, recovery points, END + no trailing
// bytes. Full video/audio topology validation is handled by the codec layer
// (WP-CODEC); here we guarantee container integrity fail-closed.
#pragma once
#include "casu/json.hpp"
#include "casu/formats.hpp"
#include <cstdint>
#include <string>
#include <vector>

namespace casu {
namespace casunat2 {

// HEADER_SIZE/CHUNK_HEADER_SIZE/VERSION and the ChunkType enum come from
// formats.hpp (casu::casunat2 namespace).

struct Chunk {
    uint8_t chunk_type = 0;
    uint8_t stream_id = 0;
    uint16_t flags = 0;
    int64_t pts = 0;
    uint64_t payload_length = 0;
    uint64_t uncompressed_length = 0;
    uint64_t offset = 0;
    std::string payload;  // loaded only when load_payloads=true (or for
                          // SEEK_INDEX/INTEGRITY_TABLE/RECOVERY_POINT/END)
};

struct SeekEntry {
    int64_t stream_id = 0;
    int64_t target_pts = 0;
    int64_t key_state_pts = 0;
    int64_t key_state_offset = 0;
    int64_t first_update_offset = 0;
};

struct RecoveryPoint {
    uint64_t offset = 0;
    JsonValue payload;
};

struct Container {
    std::string path;
    JsonValue manifest;
    std::vector<Chunk> chunks;
    std::vector<uint64_t> offsets;
    std::vector<SeekEntry> seek_entries;
    bool integrity_verified = false;
    std::vector<RecoveryPoint> recovery_points;
    // (offset, sha256hex) of every pre-integrity chunk from the integrity table.
    std::vector<std::pair<uint64_t, std::string>> chunk_hashes;
};

// Read + integrity-verify a CASUNAT2 file (fail-closed). Mirrors
// read_native_v2(verify_payloads=<load_payloads>). Throws CasuError on any
// structural/integrity failure.
Container read_native_v2(const std::string& path, bool load_payloads = true);

}  // namespace casunat2
}  // namespace casu
