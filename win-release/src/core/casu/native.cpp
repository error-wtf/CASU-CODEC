// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/native.hpp"
#include "casu/formats.hpp"
#include "casu/manifest.hpp"
#include "casu/sha256.hpp"
#include <cstdio>
#include <cstring>
#include <fstream>
#include <stdexcept>

namespace casu {
namespace casunat1 {

using casu::CasuError;

namespace {

const uint8_t MAGIC[8] = {'C', 'A', 'S', 'U', 'N', 'A', 'T', '1'};

void put_le16(uint8_t* p, uint16_t v) { p[0] = uint8_t(v); p[1] = uint8_t(v >> 8); }
void put_le64(uint8_t* p, uint64_t v) { for (int i = 0; i < 8; ++i) { p[i] = uint8_t(v); v >>= 8; } }
uint16_t get_le16(const uint8_t* p) { return uint16_t(p[0]) | uint16_t(p[1]) << 8; }
uint64_t get_le64(const uint8_t* p) { uint64_t v = 0; for (int i = 7; i >= 0; --i) v = (v << 8) | p[i]; return v; }
bool hex_to_bytes(const std::string& hex, uint8_t* out, std::size_t n);

void pack_header(uint8_t* out, uint16_t version, uint64_t manifest_length,
                 uint64_t payload_length, const std::string& manifest_digest_hex,
                 const std::string& payload_digest_hex) {
    std::memset(out, 0, HEADER_SIZE);
    std::memcpy(out, MAGIC, 8);
    put_le16(out + 8, version);
    put_le16(out + 10, 0);  // reserved
    put_le64(out + 12, manifest_length);
    put_le64(out + 20, payload_length);
    uint8_t mbuf[32] = {0}, pbuf[32] = {0};
    hex_to_bytes(manifest_digest_hex, mbuf, 32);
    hex_to_bytes(payload_digest_hex, pbuf, 32);
    std::memcpy(out + 28, mbuf, 32);
    std::memcpy(out + 60, pbuf, 32);
}

std::string bytes_to_hex(const uint8_t* p, std::size_t n) {
    static const char* hex = "0123456789abcdef";
    std::string out;
    out.reserve(n * 2);
    for (std::size_t i = 0; i < n; ++i) {
        out.push_back(hex[p[i] >> 4]);
        out.push_back(hex[p[i] & 0xF]);
    }
    return out;
}

bool hex_to_bytes(const std::string& hex, uint8_t* out, std::size_t n) {
    if (hex.size() != n * 2) return false;
    for (std::size_t i = 0; i < n; ++i) {
        auto nib = [](char c) -> int {
            if (c >= '0' && c <= '9') return c - '0';
            if (c >= 'a' && c <= 'f') return c - 'a' + 10;
            if (c >= 'A' && c <= 'F') return c - 'A' + 10;
            return -1;
        };
        int hi = nib(hex[i * 2]), lo = nib(hex[i * 2 + 1]);
        if (hi < 0 || lo < 0) return false;
        out[i] = uint8_t((hi << 4) | lo);
    }
    return true;
}

std::string file_sha256(const std::string& path, uint64_t limit) {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) throw CasuError("could not open source media: " + path);
    Sha256 ctx;
    uint8_t buf[1024 * 1024];
    uint64_t total = 0;
    std::size_t n;
    while ((n = std::fread(buf, 1, sizeof(buf), f)) > 0) {
        ctx.update(buf, n);
        total += n;
        if (total > limit) { std::fclose(f); throw CasuError("source exceeds native CASU payload limit"); }
    }
    bool ok = !std::ferror(f);
    std::fclose(f);
    if (!ok) throw CasuError("could not read source media: " + path);
    return ctx.hexdigest();
}

}  // namespace

bool Container::verify_payload() const {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) throw CasuError("could not read native CASU: " + path);
    if (std::fseek(f, (long)payload_offset, SEEK_SET) != 0) { std::fclose(f); throw CasuError("native CASU payload seek failed"); }
    Sha256 ctx;
    uint8_t buf[1024 * 1024];
    uint64_t remaining = payload_length;
    while (remaining > 0) {
        std::size_t want = remaining > sizeof(buf) ? sizeof(buf) : (std::size_t)remaining;
        std::size_t got = std::fread(buf, 1, want, f);
        if (got == 0) { std::fclose(f); throw CasuError("native CASU payload is truncated"); }
        ctx.update(buf, got);
        remaining -= got;
    }
    std::fclose(f);
    return ctx.hexdigest() == payload_sha256;
}

void Container::extract_payload(const std::string& destination) const {
    FILE* src = std::fopen(path.c_str(), "rb");
    if (!src) throw CasuError("could not read native CASU: " + path);
    if (std::fseek(src, (long)payload_offset, SEEK_SET) != 0) { std::fclose(src); throw CasuError("native CASU payload seek failed"); }
    // Atomic write: temp + rename.
    std::string tmp = destination + ".tmp";
    FILE* dst = std::fopen(tmp.c_str(), "wb");
    if (!dst) { std::fclose(src); throw CasuError("could not create output: " + destination); }
    Sha256 ctx;
    uint8_t buf[1024 * 1024];
    uint64_t remaining = payload_length;
    bool ok = true;
    while (remaining > 0) {
        std::size_t want = remaining > sizeof(buf) ? sizeof(buf) : (std::size_t)remaining;
        std::size_t got = std::fread(buf, 1, want, src);
        if (got == 0) { ok = false; break; }
        if (std::fwrite(buf, 1, got, dst) != got) { ok = false; break; }
        ctx.update(buf, got);
        remaining -= got;
    }
    std::fflush(dst);
    std::fclose(dst);
    std::fclose(src);
    if (!ok || ctx.hexdigest() != payload_sha256) {
        std::remove(tmp.c_str());
        throw CasuError("native CASU payload integrity mismatch");
    }
    // On Windows, rename does not overwrite an existing destination (the
    // reference uses os.replace which always overwrites). Remove first.
    std::remove(destination.c_str());
    if (std::rename(tmp.c_str(), destination.c_str()) != 0) {
        std::remove(tmp.c_str());
        throw CasuError("could not finalize output: " + destination);
    }
}

void write_native(const std::string& output, const std::string& source,
                  const JsonValue& manifest) {
    if (!manifest.is_object())
        throw CasuError("manifest must be an object");
    uint64_t payload_length = 0;
    {
        FILE* s = std::fopen(source.c_str(), "rb");
        if (!s) throw CasuError("source media does not exist: " + source);
        std::fseek(s, 0, SEEK_END);
        long sz = std::ftell(s);
        std::fclose(s);
        if (sz < 0) throw CasuError("could not stat source: " + source);
        payload_length = (uint64_t)sz;
        if (payload_length > MAX_PAYLOAD_BYTES)
            throw CasuError("source exceeds native CASU payload limit");
    }
    auto errors = validate_manifest(manifest);
    if (!errors.empty())
        throw CasuError("manifest is invalid: " + errors[0]);

    // Deep-copy and augment the manifest (mirror write_native).
    std::string manifest_bytes = dump_json(manifest);
    // Insert format.kind / format.native_version / native_payload.encoding via
    // parse-modify-dump on the compact canonical form.
    {
        JsonValue copy = parse_json(manifest_bytes);
        JsonObject* root = &copy.as_object_mut();
        auto format_it = root->items.find("format");
        JsonObject format;
        if (format_it != root->items.end() && format_it->second.is_object())
            format = format_it->second.as_object();
        format.items["kind"] = JsonValue(std::string("CASU native lossless container"));
        format.items["native_version"] = JsonValue(int64_t(VERSION));
        root->items["format"] = JsonValue(std::make_shared<JsonObject>(std::move(format)));
        JsonObject native_payload;
        native_payload.items["encoding"] = JsonValue(std::string("original-byte-lossless"));
        root->items["native_payload"] = JsonValue(std::make_shared<JsonObject>(std::move(native_payload)));
        manifest_bytes = dump_json(copy);
    }
    if (manifest_bytes.size() > MAX_MANIFEST_BYTES)
        throw CasuError("native CASU manifest exceeds safety limit");
    std::string manifest_digest = Sha256::oneshot(manifest_bytes);

    // Compute payload digest while writing (streaming).
    uint8_t header[HEADER_SIZE];
    std::string payload_digest;
    FILE* dst = std::fopen(output.c_str(), "wb");
    if (!dst) throw CasuError("could not create output: " + output);
    // Write a placeholder header first (payload digest unknown until streamed).
    pack_header(header, VERSION, manifest_bytes.size(), payload_length, manifest_digest, std::string());
    std::fwrite(header, 1, HEADER_SIZE, dst);
    std::fwrite(manifest_bytes.data(), 1, manifest_bytes.size(), dst);
    {
        FILE* src = std::fopen(source.c_str(), "rb");
        if (!src) { std::fclose(dst); std::remove(output.c_str()); throw CasuError("could not read source: " + source); }
        Sha256 ctx;
        uint8_t buf[1024 * 1024];
        std::size_t n;
        while ((n = std::fread(buf, 1, sizeof(buf), src)) > 0) { std::fwrite(buf, 1, n, dst); ctx.update(buf, n); }
        std::fclose(src);
        payload_digest = ctx.hexdigest();
    }
    // Rewrite header with the real payload digest (atomic-ish).
    std::fflush(dst);
    if (std::fseek(dst, 0, SEEK_SET) != 0) { std::fclose(dst); std::remove(output.c_str()); throw CasuError("native CASU header rewrite failed"); }
    pack_header(header, VERSION, manifest_bytes.size(), payload_length, manifest_digest, payload_digest);
    std::fwrite(header, 1, HEADER_SIZE, dst);
    std::fflush(dst);
    std::fclose(dst);
}

Container read_native(const std::string& path, bool verify_payload) {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) throw CasuError("could not read native CASU: " + path);
    uint8_t header[HEADER_SIZE];
    if (std::fread(header, 1, HEADER_SIZE, f) != HEADER_SIZE) { std::fclose(f); throw CasuError("native CASU header is truncated"); }
    if (std::memcmp(header, MAGIC, 8) != 0) { std::fclose(f); throw CasuError("unsupported native CASU version or magic"); }
    uint16_t version = get_le16(header + 8);
    uint64_t manifest_length = get_le64(header + 12);
    uint64_t payload_length = get_le64(header + 20);
    if (version != VERSION) { std::fclose(f); throw CasuError("unsupported native CASU version or magic"); }
    if (manifest_length > MAX_MANIFEST_BYTES || payload_length > MAX_PAYLOAD_BYTES) {
        std::fclose(f); throw CasuError("native CASU section exceeds safety limit");
    }
    std::string manifest_digest_hex = bytes_to_hex(header + 28, 32);
    std::string payload_digest_hex = bytes_to_hex(header + 60, 32);

    std::string manifest_bytes(manifest_length, '\0');
    if (manifest_length > 0 && std::fread(&manifest_bytes[0], 1, manifest_length, f) != manifest_length) {
        std::fclose(f); throw CasuError("native CASU manifest is truncated");
    }
    std::fclose(f);
    if (Sha256::oneshot(manifest_bytes) != manifest_digest_hex)
        throw CasuError("native CASU manifest integrity mismatch");

    JsonValue manifest;
    try {
        manifest = parse_json(manifest_bytes);
    } catch (const JsonError&) {
        throw CasuError("native CASU manifest is invalid");
    }
    auto errors = validate_manifest(manifest);
    if (!errors.empty())
        throw CasuError("native CASU manifest is invalid: " + errors[0]);

    // File size must match exactly.
    {
        FILE* s = std::fopen(path.c_str(), "rb");
        std::fseek(s, 0, SEEK_END);
        long sz = std::ftell(s);
        std::fclose(s);
        uint64_t expected = HEADER_SIZE + manifest_length + payload_length;
        if (sz < 0 || (uint64_t)sz != expected)
            throw CasuError("native CASU file size does not match header");
    }

    Container c;
    c.path = path;
    c.manifest = std::move(manifest);
    c.payload_offset = HEADER_SIZE + manifest_length;
    c.payload_length = payload_length;
    c.payload_sha256 = payload_digest_hex;
    if (verify_payload && !c.verify_payload())
        throw CasuError("native CASU payload integrity mismatch");
    return c;
}

}  // namespace casunat1
}  // namespace casu
