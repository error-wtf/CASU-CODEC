// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Unit tests for casu_media: typed ffprobe probe, kind detection,
// waveform/spectrum helpers (incl. a synthetic-sine FFT check), tags + cover
// extraction, and cached thumbnail extraction.
#include "casu/media.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <map>
#include <string>
#include <vector>

using namespace casu;
using namespace casu::media;

namespace {
int failures = 0;
void check(bool ok, const char* label) {
    if (!ok) { ++failures; std::printf("FAIL %s\n", label); }
    else std::printf("ok   %s\n", label);
}

bool in_unit_interval(const std::vector<float>& values) {
    for (float value : values)
        if (value < 0.0f || value > 1.0f) return false;
    return true;
}

std::vector<float> make_sine(int rate, double seconds, double frequency) {
    std::vector<float> out;
    const std::size_t count = std::size_t(double(rate) * seconds);
    out.reserve(count);
    for (std::size_t i = 0; i < count; ++i)
        out.push_back(float(std::sin(2.0 * 3.141592653589793 * frequency * double(i) / double(rate))));
    return out;
}
}  // namespace

int main() {
    const std::string clip = "tests/fixtures/demo_clip.mp4";
    const std::string nat1 = "tests/fixtures/demo_clip.mp4.casu";
    const std::string mp5 = "tests/fixtures/demo.mp5";
    const std::string nat2 = "tests/fixtures/demo_casunat2.casu";
    const std::string audio = "tests/fixtures/lino_casu_error.mp3";

    // --- typed probe (WP-MEDIA-001) ---
    {
        MediaInfo info = probe(clip);
        check(has_stream(info, "video"), "probe has video");
        check(has_stream(info, "audio"), "probe has audio");
        const MediaStreamInfo* video = first_playable(info, "video");
        check(video != nullptr && video->codec_name == "h264", "video codec h264");
        const double duration = duration_s(info);
        check(duration > 5.0 && duration < 7.0, "probe duration ~6s");
        check(info.format.format_name.find("mov") != std::string::npos, "format is mp4/mov");
        check(info.raw.is_object(), "raw ffprobe JSON kept");
    }

    // --- kind detection (WP-MEDIA-005) ---
    check(detect_kind(nat2) == CasuKind::Casunat2, "kind CASUNAT2");
    check(detect_kind(mp5) == CasuKind::Mp5, "kind MP5");
    check(detect_kind(nat1) == CasuKind::Casunat1, "kind CASUNAT1");
    check(detect_kind(clip) == CasuKind::None, "kind none for plain media");
    check(kind_name(CasuKind::Casunat2) == "casunat2", "kind_name");

    // --- waveform helpers (WP-MEDIA-003) ---
    {
        const std::vector<float> peaks = waveform_peaks(clip, 64);
        check(peaks.size() == 64, "waveform_peaks point count");
        check(in_unit_interval(peaks), "waveform_peaks in [0,1]");
        const float max_peak = *std::max_element(peaks.begin(), peaks.end());
        check(max_peak > 0.01f, "waveform has audible peaks");
        bool threw = false;
        try { waveform_peaks(clip, 4); }
        catch (const WaveformError&) { threw = true; }
        check(threw, "waveform invalid point count rejected");
    }
    {
        const std::vector<float> bands = spectrum_bands(clip, 32, 3.0);
        check(bands.size() == 32, "spectrum_bands band count");
        check(in_unit_interval(bands), "spectrum_bands in [0,1]");
    }
    {
        PcmData pcm = decode_all_pcm(clip);
        check(!pcm.samples.empty(), "decode_all_pcm non-empty");
        check(pcm.sample_rate == 44100, "decode_all_pcm rate 44100");
        const std::vector<float> window = window_peaks(pcm, 1.0);
        check(!window.empty() && window.size() <= 320 && in_unit_interval(window),
              "window_peaks returns up to 320 peaks");
        const std::vector<float> wave = window_wave(pcm, 1.0, 0.045, 512);
        check(!wave.empty(), "window_wave returns samples");
        const std::vector<float> fft = live_fft(pcm, 1.0);
        check(fft.size() == 1024 && in_unit_interval(fft), "live_fft 1024 bins");
        const std::vector<float> spectrum = live_spectrum(pcm, 1.0);
        check(spectrum.size() == 32 && in_unit_interval(spectrum), "live_spectrum 32 bands");
    }
    // Synthetic sine: dominant FFT bin must land at the right frequency.
    {
        PcmData pcm;
        pcm.samples = make_sine(44100, 1.0, 440.0);
        pcm.sample_rate = 44100;
        const std::vector<float> fft = live_fft(pcm, 0.8, 2048, 1024);
        check(fft.size() == 1024, "sine live_fft bin count");
        const std::size_t argmax = std::size_t(
            std::max_element(fft.begin(), fft.end()) - fft.begin());
        check(argmax >= 18 && argmax <= 23, "sine FFT dominant bin near 440 Hz");
        check(fft[argmax] > 0.5f, "sine FFT dominant magnitude");
    }

    // --- tags + cover (WP-MEDIA-004) ---
    {
        std::map<std::string, std::string> meta = metadata_for(audio);
        check(meta.count("title") != 0, "mp3 metadata has title");
        check(meta.count("duration") != 0, "mp3 metadata has duration");
        std::map<std::string, std::string> plain = metadata_for(clip);
        check(plain.count("title") != 0 && plain.at("title") == "demo_clip",
              "filename fallback title");
    }
    {
        check(extract_cover(audio, "/tmp/casu_cover.png"), "mp3 cover extracted");
        check(std::filesystem::is_regular_file("/tmp/casu_cover.png") &&
                  std::filesystem::file_size("/tmp/casu_cover.png") > 0,
              "cover file written");
        check(!extract_cover(clip, "/tmp/casu_cover_none.png"), "no cover on plain clip");
    }

    // --- thumbnail (WP-MEDIA-002) ---
    {
        const std::string thumb = thumbnail_for(clip, "/tmp/casu_thumbs");
        check(!thumb.empty(), "thumbnail produced");
        check(std::filesystem::is_regular_file(thumb), "thumbnail file exists");
        FILE* f = std::fopen(thumb.c_str(), "rb");
        bool magic = false;
        if (f) {
            char head[2] = {0, 0};
            if (std::fread(head, 1, 2, f) == 2 && head[0] == 'P' && head[1] == '6') magic = true;
            std::fclose(f);
        }
        check(magic, "thumbnail is a P6 PPM");
    }

    std::printf(failures == 0 ? "ALL PASS\n" : "%d FAILURES\n", failures);
    return failures == 0 ? 0 : 1;
}
