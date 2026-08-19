// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Bounded measured audio waveform/spectrum extraction (WP-MEDIA-003). Port of
// casu/waveform.py: 7 helpers for the visualizer (waveform_peaks,
// spectrum_bands, decode_all_pcm, window_peaks, window_wave, live_fft,
// live_spectrum).
#pragma once
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace casu::media {

class WaveformError : public std::runtime_error {
public:
    explicit WaveformError(const std::string& msg) : std::runtime_error(msg) {}
};

struct PcmData {
    std::vector<float> samples;  // mono, roughly in [-1.0, 1.0]
    int sample_rate = 0;
    int channels = 0;
};

// Decode the entire audio file into mono float PCM (bounded). Returns empty
// samples on any failure (best effort, never throws).
PcmData decode_all_pcm(const std::string& path);

// Normalized measured peaks for the whole file (bounded 1 kHz decode).
// Throws WaveformError for invalid sources/point counts.
std::vector<float> waveform_peaks(const std::string& path, int points = 320);

// Logarithmic measured FFT bands from a bounded decoded PCM window.
// Throws WaveformError for invalid arguments.
std::vector<float> spectrum_bands(const std::string& path, int bands = 32,
                                  double seconds = 15.0);

// Window helpers over an already-decoded PCM buffer; return {} on invalid
// arguments or too-short windows.
std::vector<float> window_peaks(const PcmData& pcm, double position_s,
                                double window_s = 0.6, int points = 320);
std::vector<float> window_wave(const PcmData& pcm, double position_s,
                               double window_s = 0.045, int points = 2048);
std::vector<float> live_fft(const PcmData& pcm, double position_s,
                            int fft_size = 2048, int bins = 1024);
std::vector<float> live_spectrum(const PcmData& pcm, double position_s,
                                 int fft_size = 2048, int bands = 32);

}  // namespace casu::media
