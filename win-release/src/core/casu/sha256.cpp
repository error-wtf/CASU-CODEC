// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Self-contained SHA-256 implementation (public-domain FIPS 180-4 algorithm).
#include "casu/sha256.hpp"
#include <cstdio>
#include <cstring>

namespace casu {

namespace {
inline uint32_t rotr(uint32_t x, unsigned n) { return (x >> n) | (x << (32 - n)); }
}  // namespace

Sha256::Sha256() {
    h_[0] = 0x6a09e667; h_[1] = 0xbb67ae85; h_[2] = 0x3c6ef372; h_[3] = 0xa54ff53a;
    h_[4] = 0x510e527f; h_[5] = 0x9b05688c; h_[6] = 0x1f83d9ab; h_[7] = 0x5be0cd19;
}

static const uint32_t K[64] = {
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};

void Sha256::transform(const uint8_t block[64]) {
    uint32_t w[64];
    for (int i = 0; i < 16; ++i)
        w[i] = (uint32_t(block[i * 4]) << 24) | (uint32_t(block[i * 4 + 1]) << 16) |
               (uint32_t(block[i * 4 + 2]) << 8) | uint32_t(block[i * 4 + 3]);
    for (int i = 16; i < 64; ++i) {
        uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
        uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = h_[0], b = h_[1], c = h_[2], d = h_[3];
    uint32_t e = h_[4], f = h_[5], g = h_[6], h = h_[7];
    for (int i = 0; i < 64; ++i) {
        uint32_t S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        uint32_t ch = (e & f) ^ (~e & g);
        uint32_t t1 = h + S1 + ch + K[i] + w[i];
        uint32_t S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        uint32_t t2 = S0 + maj;
        h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    h_[0] += a; h_[1] += b; h_[2] += c; h_[3] += d;
    h_[4] += e; h_[5] += f; h_[6] += g; h_[7] += h;
}

void Sha256::update(const void* data, std::size_t length) {
    const uint8_t* p = static_cast<const uint8_t*>(data);
    while (length > 0) {
        std::size_t space = 64 - buffer_len_;
        std::size_t take = length < space ? length : space;
        std::memcpy(buffer_ + buffer_len_, p, take);
        buffer_len_ += take;
        p += take; length -= take;
        if (buffer_len_ == 64) { transform(buffer_); bit_len_ += 512; buffer_len_ = 0; }
    }
}

void Sha256::update(const std::vector<uint8_t>& data) { update(data.data(), data.size()); }
void Sha256::update(const std::string& data) { update(data.data(), data.size()); }

std::string Sha256::oneshot(const void* data, std::size_t length) {
    Sha256 ctx;
    ctx.update(data, length);
    return ctx.hexdigest();
}

std::vector<uint8_t> Sha256::digest() {
    // Finalize (pad) once; subsequent calls recompute on the same state.
    uint64_t total_bits = bit_len_ + buffer_len_ * 8;
    uint8_t pad = 0x80;
    update(&pad, 1);
    std::size_t zeros = (buffer_len_ <= 56) ? (56 - buffer_len_) : (120 - buffer_len_);
    std::vector<uint8_t> z(zeros, 0);
    update(z.data(), z.size());
    uint8_t len[8];
    for (int i = 0; i < 8; ++i) len[i] = uint8_t(total_bits >> (56 - i * 8));
    update(len, 8);

    std::vector<uint8_t> out(32);
    for (int i = 0; i < 8; ++i) {
        out[i * 4 + 0] = uint8_t(h_[i] >> 24);
        out[i * 4 + 1] = uint8_t(h_[i] >> 16);
        out[i * 4 + 2] = uint8_t(h_[i] >> 8);
        out[i * 4 + 3] = uint8_t(h_[i]);
    }
    return out;
}

std::string Sha256::hexdigest() {
    std::vector<uint8_t> d = digest();
    std::string out;
    static const char* hex = "0123456789abcdef";
    for (uint8_t b : d) {
        out.push_back(hex[b >> 4]);
        out.push_back(hex[b & 0xF]);
    }
    return out;
}

std::string sha256_file(const std::string& path) {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) return {};
    Sha256 ctx;
    uint8_t buf[1024 * 1024];
    std::size_t n;
    while ((n = std::fread(buf, 1, sizeof(buf), f)) > 0) ctx.update(buf, n);
    bool ok = !std::ferror(f);
    std::fclose(f);
    return ok ? ctx.hexdigest() : std::string();
}

}  // namespace casu
