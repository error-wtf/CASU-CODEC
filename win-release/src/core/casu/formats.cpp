// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/formats.hpp"
#include "casu/sha256.hpp"
#include <cstdio>
#include <cstring>
#include <fstream>

namespace casu {

namespace {
inline uint16_t be16(const uint8_t* p) {
    return uint16_t(p[0]) << 8 | uint16_t(p[1]);
}
inline uint32_t be32(const uint8_t* p) {
    return uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 | uint32_t(p[2]) << 8 | uint32_t(p[3]);
}
inline uint64_t be64(const uint8_t* p) {
    uint64_t v = 0;
    for (int i = 0; i < 8; ++i) v = (v << 8) | uint64_t(p[i]);
    return v;
}
inline int64_t be64s(const uint8_t* p) { return static_cast<int64_t>(be64(p)); }

std::vector<uint8_t> read_prefix(const std::string& path, std::size_t n) {
    std::vector<uint8_t> out;
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) throw CasuError("could not read media source: " + path);
    out.resize(n);
    std::size_t got = std::fread(out.data(), 1, n, f);
    out.resize(got);
    std::fclose(f);
    return out;
}
}  // namespace

CasuKind detect_casu_kind(const std::string& path) {
    std::vector<uint8_t> prefix = read_prefix(path, 4096);
    if (prefix.size() >= 8) {
        if (std::memcmp(prefix.data(), "CASUNAT1", 8) == 0) return CasuKind::Casunat1;
        if (std::memcmp(prefix.data(), "CASUNAT2", 8) == 0) return CasuKind::Casunat2;
        if (std::memcmp(prefix.data(), "CASUMP5\0", 8) == 0) return CasuKind::Mp5;
    }
    // Sidecar JSON manifests start with '{' (bounded; full validation is
    // implemented by the manifest layer).
    std::size_t i = 0;
    while (i < prefix.size() && (prefix[i] == ' ' || prefix[i] == '\t' || prefix[i] == '\r' || prefix[i] == '\n')) ++i;
    if (i < prefix.size() && prefix[i] == '{') return CasuKind::Sidecar;
    return CasuKind::None;
}

namespace casunat2 {

Header parse_header(const uint8_t* p, std::size_t n) {
    if (n < HEADER_SIZE) throw CasuError("CASUNAT2 header is truncated");
    if (std::memcmp(p, "CASUNAT2", 8) != 0) throw CasuError("not a CASU NAT2 file (bad magic)");
    Header h;
    h.version = be16(p + 8);
    h.flags = be16(p + 10);
    h.manifest_length = be64(p + 12);
    if (h.version != VERSION) throw CasuError("unsupported CASUNAT2 version");
    if (h.flags != 0) throw CasuError("unsupported CASUNAT2 header flags");
    return h;
}

ChunkHeader parse_chunk_header(const uint8_t* p, std::size_t n, uint64_t chunk_start) {
    if (n < CHUNK_HEADER_SIZE) throw CasuError("CASUNAT2 chunk header is truncated");
    ChunkHeader c;
    c.chunk_type = p[0];
    c.stream_id = p[1];
    c.flags = be16(p + 2);
    c.pts = be64s(p + 4);
    c.payload_length = be64(p + 12);
    c.uncompressed_length = be64(p + 20);
    c.offset = chunk_start + CHUNK_HEADER_SIZE;
    return c;
}

uint64_t validate_file(const std::string& path, const CasuLimits& limits) {
    std::FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) throw CasuError("could not read CASUNAT2 file: " + path);
    std::fseek(f, 0, SEEK_END);
    long fsize = std::ftell(f);
    if (fsize < 0 || static_cast<uint64_t>(fsize) > limits.max_file_bytes) {
        std::fclose(f);
        throw CasuError("CASUNAT2 file exceeds safety limit");
    }
    std::fseek(f, 0, SEEK_SET);
    uint8_t header[HEADER_SIZE];
    if (std::fread(header, 1, HEADER_SIZE, f) != HEADER_SIZE) {
        std::fclose(f);
        throw CasuError("CASUNAT2 header is truncated");
    }
    Header h;
    try {
        h = parse_header(header, HEADER_SIZE);
    } catch (const CasuError&) {
        std::fclose(f);
        throw;
    }
    if (h.manifest_length > limits.max_manifest_bytes) {
        std::fclose(f);
        throw CasuError("CASUNAT2 manifest exceeds safety limit");
    }
    uint64_t pos = HEADER_SIZE + h.manifest_length;
    if (pos > static_cast<uint64_t>(fsize)) {
        std::fclose(f);
        throw CasuError("CASUNAT2 manifest length exceeds file size");
    }
    std::fseek(f, static_cast<long>(pos), SEEK_SET);

    uint64_t chunks = 0;
    bool ended = false;
    while (pos + CHUNK_HEADER_SIZE <= static_cast<uint64_t>(fsize)) {
        uint8_t chdr[CHUNK_HEADER_SIZE];
        if (std::fread(chdr, 1, CHUNK_HEADER_SIZE, f) != CHUNK_HEADER_SIZE) break;
        ChunkHeader c;
        try {
            c = parse_chunk_header(chdr, CHUNK_HEADER_SIZE, pos);
        } catch (const CasuError&) {
            std::fclose(f);
            throw;
        }
        if (c.payload_length > limits.max_chunk_bytes) {
            std::fclose(f);
            throw CasuError("CASUNAT2 chunk exceeds safety limit");
        }
        if (c.chunk_type == END) { ended = true; break; }
        pos += CHUNK_HEADER_SIZE + c.payload_length;
        if (pos > static_cast<uint64_t>(fsize)) {
            std::fclose(f);
            throw CasuError("CASUNAT2 chunk extends past end of file");
        }
        if (++chunks > limits.max_chunks) {
            std::fclose(f);
            throw CasuError("CASUNAT2 chunk count exceeds safety limit");
        }
        std::fseek(f, static_cast<long>(pos), SEEK_SET);
    }
    std::fclose(f);
    if (!ended) throw CasuError("CASUNAT2 file is missing the END marker");
    return chunks;
}

}  // namespace casunat2

namespace mp5 {
bool looks_like_mp5(const uint8_t* p, std::size_t n) {
    return n >= 8 && std::memcmp(p, "CASUMP5\0", 8) == 0;
}
}  // namespace mp5

}  // namespace casu
