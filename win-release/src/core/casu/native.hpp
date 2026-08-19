// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CASUNAT1 native lossless container (WP-CORE-003). Port of casu/native.py.
//   MAGIC "CASUNAT1", version 1
//   HEADER struct "<8sHHQQ32s32s" = 92 bytes:
//     magic(8) | version u16 | reserved u16 | manifest_length u64 |
//     payload_length u64 | manifest_sha256(32) | payload_sha256(32)
//   layout: header | JSON manifest | original media payload (byte-exact).
#pragma once
#include "casu/json.hpp"
#include <cstdint>
#include <string>
#include <vector>

namespace casu {

namespace casunat1 {
constexpr std::size_t HEADER_SIZE = 92;
constexpr std::size_t MAGIC_LEN = 8;
constexpr uint16_t VERSION = 1;
constexpr uint64_t MAX_MANIFEST_BYTES = 64ULL * 1024 * 1024;
constexpr uint64_t MAX_PAYLOAD_BYTES = 16ULL * 1024 * 1024 * 1024;

struct Header {
    uint16_t version = 0;
    uint64_t manifest_length = 0;
    uint64_t payload_length = 0;
    std::string manifest_sha256;  // hex
    std::string payload_sha256;   // hex
};

// A read/open native container.
struct Container {
    std::string path;
    JsonValue manifest;
    uint64_t payload_offset = 0;   // byte offset of payload in file
    uint64_t payload_length = 0;
    std::string payload_sha256;    // hex

    // Stream the payload in bounded chunks, hashing as it goes.
    // Returns false if payload sha256 does not match (integrity failure).
    bool verify_payload() const;
    // Extract payload to destination atomically (temp + rename), verifying
    // sha256. Returns destination on success; throws CasuError on mismatch.
    void extract_payload(const std::string& destination) const;
};

// Write a standalone lossless native CASU container atomically. `manifest`
// is deep-copied and augmented with format.kind/native_version and
// native_payload.encoding (mirrors write_native). Throws CasuError.
void write_native(const std::string& output, const std::string& source,
                  const JsonValue& manifest);

// Read + validate a native container. If verify_payload is true the payload
// is streamed and its sha256 checked. Throws CasuError on any integrity
// failure.
Container read_native(const std::string& path, bool verify_payload = true);

}  // namespace casunat1

}  // namespace casu
