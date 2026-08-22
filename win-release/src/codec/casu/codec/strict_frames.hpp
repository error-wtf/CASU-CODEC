// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Source-resolution strict frame decoding — full port of
// casu/strict/{decoder,model}.py (CLI ffmpeg fallback adapter). Emits the
// decoder's presentation timestamps and native plane layout instead of an
// fps-filtered preview; unsupported pixel formats fail closed.
#pragma once
#include "casu/native_v2_payloads.hpp"
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace casu::strict {

class StrictDecoderError : public CasuError {
public:
    explicit StrictDecoderError(const std::string& m) : CasuError(m) {}
};

// Exact rational (mirrors fractions.Fraction usage).
struct Rational {
    int64_t num = 0;
    int64_t den = 1;
    // Parse a decimal string like the reference Fraction(str(value)):
    // "3" -> 3/1, "2.5" -> 5/2, "1/1500" -> 1/1500.
    static Rational parse(const std::string& text);
    bool operator<(const Rational& o) const;
    bool operator>=(const Rational& o) const;
    bool operator>(const Rational& o) const { return o < *this; }
    bool operator<=(const Rational& o) const { return !(o < *this); }
};

struct StrictFrame {
    int64_t pts = 0;
    int64_t time_base_num = 0;
    int64_t time_base_den = 0;
    natv2::CanonicalFrame frame;
    std::optional<int64_t> duration_pts;

    Rational time() const {
        return Rational{pts * time_base_num, time_base_den};
    }
    double timestamp_s() const;
};

// Streaming source-resolution frame iterator over an ffmpeg rawvideo pipe.
class FrameSource {
public:
    // engine selection mirrors iter_source_frames(engine="ffmpeg").
    FrameSource(const std::string& path, int stream_index,
                std::optional<int64_t> max_frames = std::nullopt);
    ~FrameSource();
    FrameSource(const FrameSource&) = delete;
    FrameSource& operator=(const FrameSource&) = delete;

    // Returns false at end of stream. Throws StrictDecoderError on failure.
    bool next(StrictFrame& out);

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

// One-shot convenience: decode up to max_frames frames into a vector.
std::vector<StrictFrame> read_all_frames(const std::string& path,
                                         int stream_index = 0);

}  // namespace casu::strict
