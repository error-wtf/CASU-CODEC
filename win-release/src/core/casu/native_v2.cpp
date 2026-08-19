// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/native_v2.hpp"
#include "casu/formats.hpp"
#include "casu/sha256.hpp"
#include <cstdio>
#include <cstring>
#include <set>

namespace casu {
namespace casunat2 {

using casu::CasuError;

namespace {

uint16_t be16(const uint8_t* p) { return uint16_t(p[0]) << 8 | uint16_t(p[1]); }
uint64_t be64(const uint8_t* p) { uint64_t v = 0; for (int i = 0; i < 8; ++i) v = (v << 8) | p[i]; return v; }
int64_t be64s(const uint8_t* p) { return static_cast<int64_t>(be64(p)); }

bool is_hex64(const std::string& s) {
    if (s.size() != 64) return false;
    for (char c : s) {
        bool hex = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
        if (!hex) return false;
    }
    return true;
}

}  // namespace

Container read_native_v2(const std::string& path, bool load_payloads) {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) throw CasuError("could not read CASUNAT2 file: " + path);
    std::fseek(f, 0, SEEK_END);
    long fsize = std::ftell(f);
    if (fsize < 0) { std::fclose(f); throw CasuError("could not stat CASUNAT2 file"); }
    uint64_t size = (uint64_t)fsize;
    std::fseek(f, 0, SEEK_SET);

    Container c;
    c.path = path;

    // Header.
    uint8_t header[HEADER_SIZE];
    if (std::fread(header, 1, HEADER_SIZE, f) != HEADER_SIZE) { std::fclose(f); throw CasuError("truncated CASUNAT2 header"); }
    if (std::memcmp(header, "CASUNAT2", 8) != 0) { std::fclose(f); throw CasuError("unsupported CASUNAT2 header/version"); }
    uint16_t version = be16(header + 8);
    uint16_t header_flags = be16(header + 10);
    uint64_t manifest_length = be64(header + 12);
    if (version != VERSION || header_flags != 0) { std::fclose(f); throw CasuError("unsupported CASUNAT2 header/version"); }
    if (manifest_length > 64ULL * 1024 * 1024 || manifest_length > size - HEADER_SIZE) {
        std::fclose(f); throw CasuError("invalid CASUNAT2 manifest length");
    }
    std::string manifest_bytes(manifest_length, '\0');
    if (manifest_length > 0 && std::fread(&manifest_bytes[0], 1, manifest_length, f) != manifest_length) {
        std::fclose(f); throw CasuError("truncated CASUNAT2 manifest");
    }
    try {
        c.manifest = parse_json(manifest_bytes);
    } catch (const JsonError&) {
        std::fclose(f); throw CasuError("invalid CASUNAT2 manifest");
    }

    Sha256 digest;
    digest.update(header, HEADER_SIZE);
    digest.update(manifest_bytes);

    bool seen_integrity = false;
    uint64_t pos = HEADER_SIZE + manifest_length;
    std::fseek(f, (long)pos, SEEK_SET);
    std::vector<std::pair<uint64_t, std::string>> observed_chunk_hashes;
    uint64_t integrity_offset = 0;
    std::string integrity_expected;

    while (pos < size) {
        if (c.chunks.size() >= 10'000'000) { std::fclose(f); throw CasuError("excessive CASUNAT2 chunks"); }
        uint64_t offset = pos;
        uint8_t chdr[CHUNK_HEADER_SIZE];
        if (std::fread(chdr, 1, CHUNK_HEADER_SIZE, f) != CHUNK_HEADER_SIZE) { std::fclose(f); throw CasuError("truncated CASUNAT2 chunk header"); }
        uint8_t kind = chdr[0];
        uint8_t stream_id = chdr[1];
        uint16_t flags = be16(chdr + 2);
        int64_t pts = be64s(chdr + 4);
        uint64_t payload_length = be64(chdr + 12);
        uint64_t uncompressed = be64(chdr + 20);
        if (payload_length > 512ULL * 1024 * 1024 || payload_length > size - pos - CHUNK_HEADER_SIZE ||
            uncompressed < payload_length || uncompressed > 512ULL * 1024 * 1024) {
            std::fclose(f); throw CasuError("invalid CASUNAT2 chunk length");
        }
        std::string payload(payload_length, '\0');
        if (payload_length > 0 && std::fread(&payload[0], 1, payload_length, f) != payload_length) {
            std::fclose(f); throw CasuError("truncated CASUNAT2 chunk payload");
        }
        if (kind == END || kind == STREAM_CONFIG || kind == VIDEO_KEY_STATE || kind == VIDEO_TILE_UPDATE ||
            kind == VIDEO_FORMAT_CHANGE || kind == AUDIO_BLOCK || kind == SUBTITLE_PACKET ||
            kind == SUBTITLE_BITMAP || kind == CHAPTER_TABLE || kind == ATTACHMENT || kind == RECOVERY_POINT ||
            kind == SEEK_INDEX || kind == INTEGRITY_TABLE) {
            // valid known type
        } else {
            std::fclose(f); throw CasuError("unknown CASUNAT2 chunk type");
        }
        if (seen_integrity && kind != END) { std::fclose(f); throw CasuError("CASUNAT2 contains data after integrity table"); }

        if (kind == INTEGRITY_TABLE) {
            if (seen_integrity) { std::fclose(f); throw CasuError("duplicate CASUNAT2 integrity table"); }
            seen_integrity = true;
            integrity_offset = offset;
        } else if (!seen_integrity) {
            digest.update(chdr, CHUNK_HEADER_SIZE);
            digest.update(payload.data(), payload.size());
            // Reference hashes chunk_header+payload concatenated.
            std::string combined;
            combined.reserve(CHUNK_HEADER_SIZE + payload.size());
            combined.append((const char*)chdr, CHUNK_HEADER_SIZE);
            combined.append(payload);
            observed_chunk_hashes.emplace_back(offset, Sha256::oneshot(combined));
        }

        Chunk chunk;
        chunk.chunk_type = kind;
        chunk.stream_id = stream_id;
        chunk.flags = flags;
        chunk.pts = pts;
        chunk.payload_length = payload_length;
        chunk.uncompressed_length = uncompressed;
        chunk.offset = offset;
        if (load_payloads || kind == SEEK_INDEX || kind == INTEGRITY_TABLE ||
            kind == RECOVERY_POINT || kind == END)
            chunk.payload = std::move(payload);
        c.chunks.push_back(std::move(chunk));
        c.offsets.push_back(offset);

        // Seek index.
        if (kind == SEEK_INDEX && load_payloads) {
            try {
                JsonValue v = parse_json(c.chunks.back().payload);
                const JsonValue* entries = v.find("entries");
                if (!entries || !entries->is_array()) throw JsonError("no entries");
                for (const auto& item : entries->as_array().items) {
                    if (!item.is_object()) throw JsonError("entry not object");
                    const JsonValue* si = item.find("stream_id");
                    const JsonValue* tp = item.find("target_pts");
                    const JsonValue* kp = item.find("key_state_pts");
                    const JsonValue* ko = item.find("key_state_offset");
                    const JsonValue* fo = item.find("first_update_offset");
                    if (!si || !tp || !kp || !ko || !fo) throw JsonError("missing field");
                    if (!si->is_int() || !tp->is_int() || !kp->is_int() || !ko->is_int() || !fo->is_int())
                        throw JsonError("non-int field");
                    SeekEntry e{si->as_int(), tp->as_int(), kp->as_int(), ko->as_int(), fo->as_int()};
                    c.seek_entries.push_back(e);
                }
            } catch (const JsonError&) {
                std::fclose(f); throw CasuError("invalid CASUNAT2 seek index");
            }
        }
        // Integrity table.
        if (kind == INTEGRITY_TABLE && load_payloads) {
            try {
                JsonValue v = parse_json(c.chunks.back().payload);
                const JsonValue* sha = v.find("sha256_before_integrity");
                if (!sha || !sha->is_string() || !is_hex64(sha->as_string())) throw JsonError("bad sha");
                integrity_expected = sha->as_string();
                const JsonValue* hashes = v.find("chunk_sha256");
                if (hashes && hashes->is_array()) {
                    for (const auto& item : hashes->as_array().items) {
                        if (!item.is_object()) throw JsonError("hash entry not object");
                        const JsonValue* off = item.find("offset");
                        const JsonValue* h = item.find("sha256");
                        if (!off || !h || !off->is_int() || !h->is_string() || !is_hex64(h->as_string()))
                            throw JsonError("bad hash entry");
                        c.chunk_hashes.emplace_back((uint64_t)off->as_int(), h->as_string());
                    }
                }
            } catch (const JsonError&) {
                std::fclose(f); throw CasuError("invalid CASUNAT2 integrity table");
            }
        }
        // Recovery point.
        if (kind == RECOVERY_POINT && load_payloads) {
            try {
                JsonValue v = parse_json(c.chunks.back().payload);
                RecoveryPoint rp; rp.offset = offset; rp.payload = std::move(v);
                c.recovery_points.push_back(std::move(rp));
            } catch (const JsonError&) {
                std::fclose(f); throw CasuError("invalid CASUNAT2 recovery point");
            }
        }

        pos += CHUNK_HEADER_SIZE + payload_length;
        if (kind == END) {
            if (pos != size) { std::fclose(f); throw CasuError("trailing bytes after CASUNAT2 END"); }
            break;
        }
        if (std::fseek(f, (long)pos, SEEK_SET) != 0) { std::fclose(f); throw CasuError("CASUNAT2 seek failed"); }
    }
    std::fclose(f);

    if (c.chunks.empty() || c.chunks.back().chunk_type != END)
        throw CasuError("CASUNAT2 is missing END chunk");
    if (!seen_integrity || integrity_expected.empty())
        throw CasuError("CASUNAT2 is missing integrity table");
    c.integrity_verified = (digest.hexdigest() == integrity_expected);
    if (!c.integrity_verified)
        throw CasuError("CASUNAT2 integrity verification failed");

    // Chunk hash table must cover every pre-integrity chunk.
    std::set<uint64_t> expected_offsets;
    for (uint64_t o : c.offsets) expected_offsets.insert(o);
    // remove integrity + end offsets
    for (const auto& ch : c.chunks)
        if (ch.chunk_type == INTEGRITY_TABLE || ch.chunk_type == END)
            expected_offsets.erase(ch.offset);
    std::set<uint64_t> table_offsets;
    for (const auto& [o, h] : c.chunk_hashes) table_offsets.insert(o);
    if (table_offsets != expected_offsets || c.chunk_hashes.size() != table_offsets.size())
        throw CasuError("CASUNAT2 chunk hash table does not cover the verified prefix");
    // The observed hashes must equal the table hashes.
    if (c.chunk_hashes.size() != observed_chunk_hashes.size())
        throw CasuError("CASUNAT2 chunk hash table size mismatch");
    for (std::size_t i = 0; i < c.chunk_hashes.size(); ++i) {
        if (c.chunk_hashes[i] != observed_chunk_hashes[i]) {
            throw CasuError("CASUNAT2 chunk hash table does not match observed chunks");
        }
    }
    return c;
}

}  // namespace casunat2
}  // namespace casu
