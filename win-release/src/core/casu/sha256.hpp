// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Self-contained SHA-256 (public-domain algorithm) used by the CASU core for
// integrity digests. No external dependency so it works on Windows/MinGW.
#pragma once
#include <cstdint>
#include <cstddef>
#include <string>
#include <vector>

namespace casu {

class Sha256 {
public:
    Sha256();
    void update(const void* data, std::size_t length);
    void update(const std::vector<uint8_t>& data);
    void update(const std::string& data);
    std::string hexdigest();
    // Raw 32-byte digest (after finalization).
    std::vector<uint8_t> digest();

    // One-shot hex digest of a byte buffer.
    static std::string oneshot(const void* data, std::size_t length);
    static std::string oneshot(const std::string& data) {
        return oneshot(data.data(), data.size());
    }
    static std::string oneshot(const std::vector<uint8_t>& data) {
        return oneshot(data.data(), data.size());
    }

private:
    void transform(const uint8_t block[64]);
    uint32_t h_[8];
    uint64_t bit_len_ = 0;
    uint8_t buffer_[64];
    std::size_t buffer_len_ = 0;
};

// Convenience: sha256 of a file read in bounded chunks. Returns hex string,
// or empty string on read failure.
std::string sha256_file(const std::string& path);

}  // namespace casu
