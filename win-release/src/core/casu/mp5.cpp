// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/mp5.hpp"
#include "casu/formats.hpp"
#include "casu/sha256.hpp"
#include <cstdio>
#include <cstring>
#include <map>
#include <zlib.h>
#ifdef CASU_HAVE_ZSTD
#include <zstd.h>
#endif

namespace casu {
namespace mp5 {

using casu::CasuError;

namespace {

const uint8_t MAGIC[8] = {'C', 'A', 'S', 'U', 'M', 'P', '5', 0};
constexpr uint64_t MAX_CHUNK_PAYLOAD = 64ULL * 1024 * 1024;
constexpr uint64_t MAX_MANIFEST_BYTES = 64ULL * 1024 * 1024;

uint16_t get_le16(const uint8_t* p) { return uint16_t(p[0]) | uint16_t(p[1]) << 8; }
uint32_t get_le32(const uint8_t* p) { return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24; }
uint64_t get_le64(const uint8_t* p) { uint64_t v = 0; for (int i = 7; i >= 0; --i) v = (v << 8) | p[i]; return v; }

void put_le16(uint8_t* p, uint16_t v) { p[0] = uint8_t(v); p[1] = uint8_t(v >> 8); }
void put_le32(uint8_t* p, uint32_t v) { p[0] = uint8_t(v); p[1] = uint8_t(v >> 8); p[2] = uint8_t(v >> 16); p[3] = uint8_t(v >> 24); }

// Decompress a chunk payload. Mirrors the reference `_decompress`
// (casu/mp5/reader.py:47): when zstd is available try it first, then fall
// back to zlib. This reads both zstd-compressed MP5 files (produced with the
// Python zstd package) and the zlib-compressed golden fixtures.
std::vector<uint8_t> decompress(const uint8_t* data, std::size_t n) {
#ifdef CASU_HAVE_ZSTD
    {
        // Standard frames (Python zstd.compress) report their content size;
        // streaming/unknown-size frames go through the bounded stream API.
        unsigned long long est = ZSTD_getFrameContentSize(data, n);
        if (est == ZSTD_CONTENTSIZE_ERROR) { /* not a zstd frame -> zlib */ }
        else if (est <= MAX_CHUNK_PAYLOAD) {
            std::vector<uint8_t> out(est ? (std::size_t)est : 1);
            std::size_t got = ZSTD_decompress(out.data(), out.size(), data, n);
            if (!ZSTD_isError(got)) { out.resize(got); return out; }
        } else if (est == ZSTD_CONTENTSIZE_UNKNOWN) {
            std::vector<uint8_t> out(MAX_CHUNK_PAYLOAD);
            ZSTD_DStream* ds = ZSTD_createDStream();
            if (ds) {
                ZSTD_initDStream(ds);
                ZSTD_inBuffer in{data, n, 0};
                ZSTD_outBuffer ob{out.data(), out.size(), 0};
                std::size_t rc = ZSTD_decompressStream(ds, &ob, &in);
                ZSTD_freeDStream(ds);
                if (!ZSTD_isError(rc) && ob.pos > 0) { out.resize(ob.pos); return out; }
            }
        }
    }
#endif
    // Try raw inflate (zlib format) first.
    uLongf dest_len = MAX_CHUNK_PAYLOAD;
    std::vector<uint8_t> out(MAX_CHUNK_PAYLOAD);
    int rc = uncompress(out.data(), &dest_len, data, (uLong)n);
    if (rc == Z_OK) { out.resize(dest_len); return out; }
    // Fall back to raw DEFLATE (no zlib header).
    {
        z_stream zs;
        std::memset(&zs, 0, sizeof(zs));
        if (inflateInit2(&zs, -MAX_WBITS) != Z_OK)
            throw CasuError("chunk payload decompression failed");
        zs.next_in = const_cast<Bytef*>(data);
        zs.avail_in = (uInt)n;
        std::vector<uint8_t> raw(MAX_CHUNK_PAYLOAD);
        zs.next_out = raw.data();
        zs.avail_out = (uInt)MAX_CHUNK_PAYLOAD;
        int zrc = inflate(&zs, Z_FINISH);
        inflateEnd(&zs);
        if (zrc != Z_STREAM_END && zrc != Z_OK)
            throw CasuError("chunk payload decompression failed");
        raw.resize(raw.size() - zs.avail_out);
        return raw;
    }
}

std::vector<uint8_t> compress(const uint8_t* data, std::size_t n) {
    // Mirror reference _compress(data, level=3) via zlib deflate.
    uLongf dest_len = compressBound((uLong)n);
    std::vector<uint8_t> out(dest_len);
    if (compress2(out.data(), &dest_len, data, (uLong)n, 3) != Z_OK)
        throw CasuError("chunk payload compression failed");
    out.resize(dest_len);
    return out;
}

}  // namespace

std::vector<uint8_t> Container::read_chunk_payload(const ChunkSummary& c) const {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) throw CasuError("could not read MP5 file: " + path);
    if (std::fseek(f, (long)(c.offset + CHUNK_HEADER_SIZE), SEEK_SET) != 0) { std::fclose(f); throw CasuError("MP5 seek failed"); }
    std::vector<uint8_t> comp(c.comp_length);
    if (c.comp_length > 0 && std::fread(comp.data(), 1, c.comp_length, f) != c.comp_length) {
        std::fclose(f); throw CasuError("truncated MP5 chunk payload");
    }
    std::fclose(f);
    return decompress(comp.data(), comp.size());
}

Container read_mp5(const std::string& path) {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) throw CasuError("could not read MP5 file: " + path);
    std::fseek(f, 0, SEEK_END);
    long sz = std::ftell(f);
    if (sz < 0) { std::fclose(f); throw CasuError("could not stat MP5 file"); }
    uint64_t size = (uint64_t)sz;
    std::fseek(f, 0, SEEK_SET);

    uint8_t header[HEADER_SIZE];
    if (std::fread(header, 1, HEADER_SIZE, f) != HEADER_SIZE) { std::fclose(f); throw CasuError("file too small for MP5 header"); }
    if (std::memcmp(header, MAGIC, 8) != 0) { std::fclose(f); throw CasuError("not a CASU MP5 file"); }
    uint16_t version = get_le16(header + 8);
    uint16_t flags = get_le16(header + 10);
    uint32_t manifest_length = get_le32(header + 12);
    if (version != VERSION) { std::fclose(f); throw CasuError("unsupported MP5 version"); }
    if (flags != 0 || manifest_length > MAX_MANIFEST_BYTES || manifest_length > size - HEADER_SIZE) {
        std::fclose(f); throw CasuError("invalid MP5 header");
    }
    std::string manifest_bytes(manifest_length, '\0');
    if (manifest_length > 0 && std::fread(&manifest_bytes[0], 1, manifest_length, f) != manifest_length) {
        std::fclose(f); throw CasuError("truncated MP5 manifest");
    }
    JsonValue manifest;
    try { manifest = parse_json(manifest_bytes); }
    catch (const JsonError&) { std::fclose(f); throw CasuError("invalid MP5 manifest"); }

    Container c;
    c.path = path;
    c.manifest = std::move(manifest);
    c.size = size;

    uint64_t pos = HEADER_SIZE + manifest_length;
    while (pos + CHUNK_HEADER_SIZE <= size) {
        uint8_t chdr[CHUNK_HEADER_SIZE];
        if (std::fseek(f, (long)pos, SEEK_SET) != 0) { std::fclose(f); throw CasuError("MP5 seek failed"); }
        if (std::fread(chdr, 1, CHUNK_HEADER_SIZE, f) != CHUNK_HEADER_SIZE) { std::fclose(f); throw CasuError("truncated MP5 chunk header"); }
        // CHUNK_HEADER "<BHII": type u8 | stream_id u16 LE | pts u32 LE |
        // comp_length u32 LE
        uint8_t ct = chdr[0];
        uint16_t stream_id = get_le16(chdr + 1);
        uint32_t pts = get_le32(chdr + 3);
        uint32_t comp_length = get_le32(chdr + 7);
        bool known = (ct == END || ct == STREAM_CONFIG || ct == VIDEO_KEY_STATE ||
                      ct == VIDEO_TILE_UPDATE || ct == VIDEO_FORMAT_CHANGE || ct == AUDIO_BLOCK ||
                      ct == SUBTITLE_PACKET || ct == SUBTITLE_BITMAP || ct == CHAPTER_TABLE ||
                      ct == ATTACHMENT || ct == SEEK_INDEX || ct == INTEGRITY_TABLE ||
                      ct == RECOVERY_POINT || ct == METADATA);
        if (!known) break;
        if (ct == END) break;  // END terminates the chunk table (not included)
        ChunkSummary cs;
        cs.chunk_type = (ChunkType)ct;
        cs.stream_id = (uint8_t)stream_id;
        cs.pts = pts;
        cs.comp_length = comp_length;
        cs.offset = pos;
        c.chunks.push_back(cs);
        pos += CHUNK_HEADER_SIZE + comp_length;
        if (comp_length > MAX_CHUNK_PAYLOAD || pos > size) break;
    }
    std::fclose(f);
    return c;
}

void write_mp5(const std::string& output, const JsonValue& manifest,
               const std::vector<std::tuple<ChunkType, uint8_t, uint32_t, std::vector<uint8_t>>>& chunks) {
    std::string manifest_bytes = dump_json(manifest);
    if (manifest_bytes.size() > MAX_MANIFEST_BYTES)
        throw CasuError("manifest exceeds size limit");
    Sha256 ctx;
    ctx.update(manifest_bytes);
    std::vector<uint8_t> manifest_digest = ctx.digest();

    FILE* f = std::fopen(output.c_str(), "wb");
    if (!f) throw CasuError("could not create MP5 output: " + output);
    uint8_t header[HEADER_SIZE];
    std::memset(header, 0, sizeof(header));
    std::memcpy(header, MAGIC, 8);
    put_le16(header + 8, VERSION);
    put_le16(header + 10, 0);
    put_le32(header + 12, (uint32_t)manifest_bytes.size());
    put_le32(header + 16, 0);  // reserved
    std::fwrite(header, 1, HEADER_SIZE, f);
    std::fwrite(manifest_bytes.data(), 1, manifest_bytes.size(), f);

    for (const auto& [ct, stream_id, pts, payload] : chunks) {
        uint8_t chdr[CHUNK_HEADER_SIZE];
        std::memset(chdr, 0, sizeof(chdr));
        // "<BHII": type u8 | stream_id u16 LE | pts u32 LE | comp_length u32 LE
        chdr[0] = (uint8_t)ct;
        put_le16(chdr + 1, stream_id);
        put_le32(chdr + 3, pts);
        if (ct == END) {
            put_le32(chdr + 7, 0);
            std::fwrite(chdr, 1, CHUNK_HEADER_SIZE, f);
        } else {
            std::vector<uint8_t> comp = compress(payload.data(), payload.size());
            if (comp.size() > MAX_CHUNK_PAYLOAD) { std::fclose(f); throw CasuError("compressed chunk exceeds size limit"); }
            put_le32(chdr + 7, (uint32_t)comp.size());
            std::fwrite(chdr, 1, CHUNK_HEADER_SIZE, f);
            std::fwrite(comp.data(), 1, comp.size(), f);
        }
    }
    // Footer: count(4) + manifest_digest(32).
    uint8_t footer[FOOTER_SIZE];
    put_le32(footer, (uint32_t)chunks.size());
    std::memcpy(footer + 4, manifest_digest.data(), 32);
    std::fwrite(footer, 1, FOOTER_SIZE, f);
    std::fclose(f);}

std::pair<std::string, std::vector<uint8_t>> extract_attachment(const std::string& path) {
    Container c = read_mp5(path);
    JsonValue integrity;
    bool has_integrity = false;
    std::map<int, std::vector<uint8_t>> parts;
    std::string filename = "media.bin";
    int expected_parts = 1;
    for (const auto& cs : c.chunks) {
        if (cs.chunk_type == INTEGRITY_TABLE) {
            auto pl = c.read_chunk_payload(cs);
            try { integrity = parse_json(std::string((char*)pl.data(), pl.size())); has_integrity = true; }
            catch (const JsonError&) {}
        } else if (cs.chunk_type == ATTACHMENT) {
            auto pl = c.read_chunk_payload(cs);
            if (pl.size() < 2) throw CasuError("attachment chunk too small");
            uint16_t meta_len = uint16_t(pl[0]) | uint16_t(pl[1]) << 8;
            if (pl.size() < 2 + meta_len) throw CasuError("truncated attachment metadata");
            std::string meta_str((char*)pl.data() + 2, meta_len);
            JsonValue meta;
            try { meta = parse_json(meta_str); } catch (const JsonError&) { throw CasuError("invalid attachment metadata"); }
            if (meta.find("filename") && meta.find("filename")->is_string())
                filename = meta.find("filename")->as_string();
            if (meta.find("parts") && meta.find("parts")->is_int())
                expected_parts = (int)meta.find("parts")->as_int();
            int part = meta.find("part") && meta.find("part")->is_int()
                       ? (int)meta.find("part")->as_int()
                       : (int)cs.pts;
            parts[part] = std::vector<uint8_t>(pl.begin() + 2 + meta_len, pl.end());
        }
    }
    if (parts.empty())
        throw CasuError("MP5 container carries no attachment payload");
    if ((int)parts.size() != expected_parts)
        throw CasuError("MP5 attachment incomplete: " + std::to_string(parts.size()) + "/" + std::to_string(expected_parts) + " parts");
    std::vector<uint8_t> payload_bytes;
    for (int i = 0; i < expected_parts; ++i) {
        auto it = parts.find(i);
        if (it == parts.end()) throw CasuError("MP5 attachment incomplete");
        payload_bytes.insert(payload_bytes.end(), it->second.begin(), it->second.end());
    }
    if (has_integrity) {
        const JsonValue* exp = integrity.find("attachment_sha256");
        if (exp && exp->is_string()) {
            std::string expected = exp->as_string();
            if (expected.size() == 64 && Sha256::oneshot(payload_bytes) != expected)
                throw CasuError("MP5 attachment failed SHA-256 verification");
        }
    }
    return {filename, payload_bytes};
}

std::vector<std::string> verify_mp5(const std::string& path) {
    std::vector<std::string> issues;
    Container c;
    try { c = read_mp5(path); }
    catch (const CasuError& e) { issues.push_back(e.what()); return issues; }
    FILE* f = std::fopen(path.c_str(), "rb");
    if (f) {
        std::fseek(f, -36, SEEK_END);
        uint8_t tail[36];
        std::size_t got = std::fread(tail, 1, 36, f);
        std::fclose(f);
        if (got != 36) {
            issues.push_back("missing footer");
        } else {
            uint32_t count = get_le32(tail);
            std::vector<uint8_t> footer_digest(tail + 4, tail + 36);
            std::string manifest_bytes = dump_json(c.manifest);
            Sha256 ctx;
            ctx.update(manifest_bytes);
            if (ctx.digest() != footer_digest)
                issues.push_back("manifest digest mismatch");
            if (count != c.chunks.size() && count != c.chunks.size() + 1)
                issues.push_back("footer chunk count mismatch");
        }
    }
    try { extract_attachment(path); }
    catch (const CasuError& e) { issues.push_back("attachment: " + std::string(e.what())); }
    return issues;
}

}  // namespace mp5
}  // namespace casu
