// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CASUNAT2 container I/O — full port of casu/native_v2/{reader,writer}.py:
// strict manifest parse, incremental topology validation, integrity table +
// chunk-hash cross-checks (offset-keyed), seek-index verification (R21/R23),
// recovery points with checkpoint hashes, atomic deterministic writer,
// recover/repair for truncated files, video reconstruction via TileStateCache.
#pragma once
#include "casu/json.hpp"
#include "casu/formats.hpp"
#include "casu/native_v2_payloads.hpp"
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace casu {
namespace casunat2 {

// HEADER_SIZE/CHUNK_HEADER_SIZE/VERSION and the ChunkType enum come from
// formats.hpp (casu::casunat2 namespace).

class NativeV2Error : public CasuError {
public:
    explicit NativeV2Error(const std::string& msg) : CasuError(msg) {}
};

struct Chunk {
    uint8_t chunk_type = 0;
    uint8_t stream_id = 0;
    uint16_t flags = 0;
    int64_t pts = 0;
    uint64_t payload_length = 0;
    // Mirrors the Optional uncompressed_length of the reference; nullopt for
    // writer-side chunks that did not declare one.
    std::optional<uint64_t> uncompressed_length;
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

    bool operator==(const SeekEntry& other) const {
        return stream_id == other.stream_id &&
               target_pts == other.target_pts &&
               key_state_pts == other.key_state_pts &&
               key_state_offset == other.key_state_offset &&
               first_update_offset == other.first_update_offset;
    }
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
    CasuLimits limits;

    // All chunks with pts >= target (optionally one stream).
    std::vector<const Chunk*> chunks_at_or_after(int64_t pts,
                                                 int stream_id = -1) const;

    // Real file-seek reads; hash-verified against the integrity table.
    Chunk read_chunk_at(uint64_t offset) const;
    // Metadata-only fast path for audio blocks (PCM stays on disk).
    JsonValue read_audio_block_meta_at(uint64_t offset) const;
};

struct ReconstructionPlan {
    int64_t stream_id = 0;
    int64_t target_pts = 0;
    int64_t key_state_pts = 0;
    int64_t key_state_offset = 0;
    int64_t first_update_offset = 0;
};

// Byte-indexed seek over the verified seek index.
ReconstructionPlan seek_video(const Container& container, int64_t stream_id,
                              int64_t target_pts);
// Reconstruct the source-resolution canonical frame at target_pts.
natv2::CanonicalFrame reconstruct_video(const Container& container,
                                        int64_t stream_id,
                                        int64_t target_pts);

struct NativeV2Recovery {
    std::string path;
    JsonValue manifest;
    std::vector<Chunk> chunks;
    JsonValue recovery_point;
    int64_t complete_chunk_offset = 0;
};

// Read + integrity-verify a CASUNAT2 file (fail-closed). Mirrors
// read_native_v2(verify_payloads=<load_payloads>). Throws on any
// structural/integrity failure.
Container read_native_v2(const std::string& path, bool load_payloads = true);
Container read_native_v2(const std::string& path, const CasuLimits& limits,
                         bool load_payloads = true);

// Recover the last complete prefix from a truncated file (writer-emitted
// RECOVERY_POINT required as resume boundary).
NativeV2Recovery recover_native_v2(const std::string& path);

// Finalize the recovered prefix into a new verified file.
std::string repair_native_v2(const std::string& source,
                             const std::string& target);

// Deterministic atomic writer (recovery_interval=32 like the reference;
// 0 disables recovery points). Returns the target path.
std::string write_native_v2(
    const std::string& path, const JsonValue& manifest,
    const std::vector<Chunk>& chunks,
    uint64_t recovery_interval = 32, const CasuLimits* limits = nullptr);

}  // namespace casunat2
}  // namespace casu
