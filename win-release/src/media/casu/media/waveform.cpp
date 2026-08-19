// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/media/waveform.hpp"

#include "casu/codec/ffmpeg.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <vector>

namespace casu::media {

namespace {

constexpr double kPi = 3.14159265358979323846;

std::vector<int16_t> decode_s16le(const std::string& data) {
    std::vector<int16_t> samples;
    samples.reserve(data.size() / 2);
    for (std::size_t i = 0; i + 1 < data.size(); i += 2) {
        const std::uint16_t lo = std::uint8_t(data[i]);
        const std::uint16_t hi = std::uint16_t(std::uint8_t(data[i + 1])) << 8;
        samples.push_back(int16_t(lo | hi));
    }
    return samples;
}

PcmData decode_audio(const std::string& path, int rate, std::size_t max_bytes,
                     double seconds = 0.0) {
    PcmData pcm;
    try {
        casu::codec::Ffmpeg ffmpeg;
        casu::codec::FfmpegRunOptions options;
        options.max_stdout = max_bytes;
        options.timeout_seconds = 60;
        std::vector<std::string> args = {
            "-v", "error", "-i", path, "-map", "0:a:0",
            "-ac", "1", "-ar", std::to_string(rate), "-f", "s16le", "pipe:1",
        };
        if (seconds > 0.0) {
            std::string seconds_text = std::to_string(seconds);
            args.insert(args.begin() + 2, {seconds_text});
            args.insert(args.begin() + 2, {"-t"});
        }
        casu::codec::ProcessResult result = ffmpeg.run(args, options);
        if (!result.started || result.timed_out || result.exit_code != 0) return pcm;
        const std::vector<int16_t> raw = decode_s16le(result.stdout_data);
        pcm.samples.reserve(raw.size());
        for (int16_t sample : raw) pcm.samples.push_back(float(sample) / 32768.0f);
        pcm.sample_rate = rate;
        pcm.channels = 1;
    } catch (const casu::codec::MediaTranscodeError&) {
        pcm = PcmData();
    }
    return pcm;
}

std::vector<float> peaks_from_samples(const std::vector<int16_t>& samples, int points) {
    if (samples.empty()) return {};
    const std::size_t width = std::max<std::size_t>(
        1, (samples.size() + std::size_t(points) - 1) / std::size_t(points));
    std::vector<float> out;
    out.reserve(points);
    for (std::size_t start = 0; start < samples.size(); start += width) {
        int peak = 0;
        const std::size_t end = std::min(samples.size(), start + width);
        for (std::size_t i = start; i < end; ++i) {
            int value = int(samples[i]);
            if (value < 0) value = -value;
            if (value > peak) peak = value;
        }
        out.push_back(std::min(1.0f, float(peak) / 32768.0f));
    }
    if (out.size() > std::size_t(points)) out.resize(points);
    return out;
}

void apply_hanning(std::vector<double>& values) {
    const std::size_t n = values.size();
    if (n <= 1) return;
    for (std::size_t i = 0; i < n; ++i)
        values[i] *= 0.5 * (1.0 - std::cos(2.0 * kPi * double(i) / double(n - 1)));
}

struct Complex {
    double re = 0.0, im = 0.0;
};

void fft_radix2(std::vector<Complex>& a) {
    const std::size_t n = a.size();
    for (std::size_t i = 1, j = 0; i < n; ++i) {
        std::size_t bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) std::swap(a[i], a[j]);
    }
    for (std::size_t len = 2; len <= n; len <<= 1) {
        const double angle = -2.0 * kPi / double(len);
        const Complex wlen{std::cos(angle), std::sin(angle)};
        for (std::size_t i = 0; i < n; i += len) {
            Complex w{1.0, 0.0};
            for (std::size_t k = 0; k < len / 2; ++k) {
                const Complex u = a[i + k];
                const Complex v{a[i + k + len / 2].re * w.re - a[i + k + len / 2].im * w.im,
                                a[i + k + len / 2].re * w.im + a[i + k + len / 2].im * w.re};
                a[i + k] = {u.re + v.re, u.im + v.im};
                a[i + k + len / 2] = {u.re - v.re, u.im - v.im};
                const Complex next{w.re * wlen.re - w.im * wlen.im,
                                   w.re * wlen.im + w.im * wlen.re};
                w = next;
            }
        }
    }
}

// Zero-padded radix-2 magnitude spectrum (Nyquist bin included). The pad
// makes every input length work; for power-of-two windows it matches numpy
// rfft exactly.
struct Spectrum {
    std::vector<double> magnitudes;
    double bin_width = 0.0;
};

Spectrum rfft_magnitudes(const std::vector<double>& values, int rate) {
    const std::size_t n = values.size();
    std::size_t m = 1;
    while (m < n) m <<= 1;
    std::vector<Complex> buf(m, Complex{0.0, 0.0});
    for (std::size_t i = 0; i < n; ++i) buf[i] = {values[i], 0.0};
    fft_radix2(buf);
    Spectrum out;
    out.magnitudes.reserve(m / 2 + 1);
    for (std::size_t i = 0; i <= m / 2; ++i)
        out.magnitudes.push_back(std::hypot(buf[i].re, buf[i].im));
    out.bin_width = double(rate) / double(m);
    return out;
}

std::vector<double> geomspace(double first, double last, int count) {
    std::vector<double> out;
    out.reserve(std::size_t(count));
    if (count <= 0) return out;
    if (count == 1) {
        out.push_back(first);
        return out;
    }
    const double log_first = std::log(first);
    const double step = (std::log(last) - log_first) / double(count - 1);
    for (int i = 0; i < count; ++i) out.push_back(std::exp(log_first + step * double(i)));
    return out;
}

int searchsorted_right(const std::vector<double>& sorted, double value) {
    return int(std::upper_bound(sorted.begin(), sorted.end(), value) - sorted.begin());
}

double rms(const std::vector<double>& values, std::size_t begin, std::size_t end) {
    if (begin >= end) return 0.0;
    double sum = 0.0;
    for (std::size_t i = begin; i < end; ++i) sum += values[i] * values[i];
    return std::sqrt(sum / double(end - begin));
}

std::vector<float> normalize(const std::vector<double>& values) {
    double maximum = 0.0;
    for (double value : values)
        if (value > maximum) maximum = value;
    std::vector<float> out;
    out.reserve(values.size());
    for (double value : values) out.push_back(maximum > 0 ? float(value / maximum) : 0.0f);
    return out;
}

std::vector<float> log_spectrum_bands(const std::vector<double>& values, int rate,
                                      int bands, double low_edge, double high_edge) {
    std::vector<double> windowed(values.size());
    for (std::size_t i = 0; i < values.size(); ++i) windowed[i] = values[i];
    apply_hanning(windowed);
    Spectrum spectrum = rfft_magnitudes(windowed, rate);
    std::vector<double> freqs(spectrum.magnitudes.size());
    for (std::size_t i = 0; i < freqs.size(); ++i)
        freqs[i] = double(i) * spectrum.bin_width;
    const std::vector<double> edges = geomspace(low_edge, high_edge, bands + 1);
    std::vector<double> output;
    output.reserve(std::size_t(bands));
    for (int band = 0; band < bands; ++band) {
        const int low = std::max(0, searchsorted_right(freqs, edges[std::size_t(band)]) - 1);
        const int high = std::max(low + 1, searchsorted_right(freqs, edges[std::size_t(band) + 1]) - 1);
        const std::size_t high_idx = std::min(std::size_t(high), spectrum.magnitudes.size());
        output.push_back(rms(spectrum.magnitudes, std::size_t(low), high_idx));
    }
    return normalize(output);
}

}  // namespace

PcmData decode_all_pcm(const std::string& path) {
    std::error_code ec;
    if (!std::filesystem::is_regular_file(path, ec)) return {};
    return decode_audio(path, 44100, 176'400'000);
}

std::vector<float> waveform_peaks(const std::string& path, int points) {
    std::error_code ec;
    if (!std::filesystem::is_regular_file(path, ec) || points < 16 || points > 2048)
        throw WaveformError("waveform source or point count is invalid");
    PcmData pcm = decode_audio(path, 1000, 16 * 1024 * 1024);
    if (pcm.samples.empty())
        throw WaveformError("could not decode audio waveform");
    std::vector<int16_t> raw;
    raw.reserve(pcm.samples.size());
    for (float sample : pcm.samples) {
        int value = int(sample * 32768.0f);
        if (value < -32768) value = -32768;
        if (value > 32767) value = 32767;
        raw.push_back(int16_t(value));
    }
    return peaks_from_samples(raw, points);
}

std::vector<float> spectrum_bands(const std::string& path, int bands, double seconds) {
    std::error_code ec;
    if (!std::filesystem::is_regular_file(path, ec) || bands < 8 || bands > 128 ||
        seconds < 1.0 || seconds > 30.0)
        throw WaveformError("spectrum source, band count or duration is invalid");
    const int rate = 16000;
    const std::size_t max_bytes = std::size_t(rate * (seconds + 1.0) * 2.0);
    PcmData pcm = decode_audio(path, rate, max_bytes, seconds);
    if (pcm.samples.size() < 64) return {};
    std::vector<double> values;
    values.reserve(pcm.samples.size());
    for (float sample : pcm.samples) values.push_back(double(sample));
    double mean = 0.0;
    for (double value : values) mean += value;
    mean /= double(values.size());
    for (double& value : values) value -= mean;
    const double low = 20.0;
    const double high = std::max(21.0, std::min(double(rate) / 2.0, 20'000.0));
    return log_spectrum_bands(values, rate, bands, low, high);
}

std::vector<float> window_peaks(const PcmData& pcm, double position_s,
                                double window_s, int points) {
    if (pcm.samples.empty() || pcm.sample_rate <= 0 || points < 8) return {};
    const std::size_t window_samples =
        std::max<std::size_t>(64, std::size_t(double(pcm.sample_rate) * window_s));
    std::size_t centre = std::size_t(double(pcm.sample_rate) * position_s);
    centre = std::min(centre, pcm.samples.size() - 1);
    const std::size_t half = window_samples / 2;
    const std::size_t start = centre > half ? centre - half : 0;
    const std::size_t end = std::min(pcm.samples.size(), start + window_samples);
    if (end - start < 64) return {};
    const std::size_t width = std::max<std::size_t>(
        1, (end - start + std::size_t(points) - 1) / std::size_t(points));
    std::vector<float> out;
    out.reserve(std::size_t(points));
    for (std::size_t i = start; i < end; i += width) {
        float peak = 0.0f;
        const std::size_t stop = std::min(end, i + width);
        for (std::size_t j = i; j < stop; ++j) {
            float value = pcm.samples[j];
            if (value < 0) value = -value;
            if (value > peak) peak = value;
        }
        out.push_back(std::min(1.0f, peak));
    }
    if (out.size() > std::size_t(points)) out.resize(points);
    return out;
}

std::vector<float> window_wave(const PcmData& pcm, double position_s,
                               double window_s, int points) {
    if (pcm.samples.empty() || pcm.sample_rate <= 0 || points < 8) return {};
    const std::size_t window_samples =
        std::max<std::size_t>(64, std::size_t(double(pcm.sample_rate) * window_s));
    std::size_t centre = std::size_t(double(pcm.sample_rate) * position_s);
    centre = std::min(centre, pcm.samples.size() - 1);
    const std::size_t start = centre > window_samples ? centre - window_samples : 0;
    const std::size_t end = centre;
    if (end - start < 32) return {};
    const std::size_t width = std::max<std::size_t>(
        1, (end - start + std::size_t(points) - 1) / std::size_t(points));
    std::vector<float> out;
    out.reserve(std::size_t(points));
    for (std::size_t i = start; i < end; i += width) out.push_back(pcm.samples[i]);
    if (out.size() > std::size_t(points)) out.resize(points);
    return out;
}

std::vector<float> live_fft(const PcmData& pcm, double position_s,
                            int fft_size, int bins) {
    if (pcm.samples.empty() || pcm.sample_rate <= 0 || bins < 8) return {};
    const std::size_t size = std::min(pcm.samples.size(),
                                      std::size_t(std::max(64, fft_size)));
    std::size_t centre = std::size_t(double(pcm.sample_rate) * position_s);
    centre = std::min(centre, pcm.samples.size() - 1);
    const std::size_t start = centre > size ? centre - size : 0;
    const std::size_t end = centre;
    if (end - start < 64) return {};
    std::vector<float> chunk(pcm.samples.begin() + std::ptrdiff_t(start),
                             pcm.samples.begin() + std::ptrdiff_t(end));
    double mean = 0.0;
    for (float value : chunk) mean += double(value);
    mean /= double(chunk.size());
    std::vector<double> windowed(chunk.size());
    for (std::size_t i = 0; i < chunk.size(); ++i) windowed[i] = double(chunk[i]) - mean;
    apply_hanning(windowed);
    const Spectrum spectrum = rfft_magnitudes(windowed, pcm.sample_rate);
    const std::size_t count = std::min(std::size_t(bins), spectrum.magnitudes.size());
    return normalize(std::vector<double>(spectrum.magnitudes.begin(),
                                         spectrum.magnitudes.begin() + std::ptrdiff_t(count)));
}

std::vector<float> live_spectrum(const PcmData& pcm, double position_s,
                                 int fft_size, int bands) {
    if (pcm.samples.empty() || pcm.sample_rate <= 0 || bands < 4) return {};
    const std::size_t size = std::min(pcm.samples.size(),
                                      std::size_t(std::max(64, fft_size)));
    std::size_t centre = std::size_t(double(pcm.sample_rate) * position_s);
    centre = std::min(centre, pcm.samples.size() - 1);
    const std::size_t half = size / 2;
    const std::size_t start = centre > half ? centre - half : 0;
    const std::size_t end = std::min(pcm.samples.size(), start + size);
    if (end - start < 32) return {};
    std::vector<float> chunk(pcm.samples.begin() + std::ptrdiff_t(start),
                             pcm.samples.begin() + std::ptrdiff_t(end));
    double mean = 0.0;
    for (float value : chunk) mean += double(value);
    mean /= double(chunk.size());
    std::vector<double> windowed(chunk.size());
    for (std::size_t i = 0; i < chunk.size(); ++i) windowed[i] = double(chunk[i]) - mean;
    apply_hanning(windowed);
    const double low = 20.0;
    const double high = std::min(double(pcm.sample_rate) / 2.0, 20'000.0);
    return log_spectrum_bands(windowed, pcm.sample_rate, bands, low, high);
}

}  // namespace casu::media
