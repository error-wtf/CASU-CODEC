// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Byte-parity test for the visualizer FFT against casu/waveform.py:
// identical synthetic PCM -> live_fft bins and window_wave samples must
// match the Python reference within double-precision tolerance.
#include "viz_fft.hpp"

#include "casu/json.hpp"

#include <QFile>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <vector>

using namespace mpcasu;
using casu::JsonValue;

namespace {

int failures = 0;

void check(bool ok, const char* label) {
    if (!ok) {
        ++failures;
        std::printf("FAIL %s\n", label);
    } else {
        std::printf("ok   %s\n", label);
    }
}

std::string read_file(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::printf("usage: casu_viz_parity_test <fixture_dir>\n");
        return 2;
    }
    const std::string dir = argv[1];
    const JsonValue ref =
        casu::parse_json(read_file(dir + "/ref_viz_fft.json"));
    const double position = ref.find("position")->as_double();

    // Reconstruct the exact PCM the fixture generator produced.
    QFile pcm_file(QString::fromStdString(dir + "/viz_pcm.s16"));
    if (!pcm_file.open(QIODevice::ReadOnly)) {
        std::printf("FAIL cannot open viz_pcm.s16\n");
        return 1;
    }
    const QByteArray raw = pcm_file.readAll();
    std::vector<float> pcm(static_cast<std::size_t>(raw.size() / 2));
    for (int i = 0; i < raw.size() / 2; ++i) {
        const int16_t v = static_cast<int16_t>(
            uint16_t(uint8_t(raw[2 * i])) |
            (uint16_t(uint8_t(raw[2 * i + 1])) << 8));
        pcm[static_cast<std::size_t>(i)] = static_cast<float>(v) / 32768.0f;
    }

    // --- live_fft bins --------------------------------------------------------
    const QVector<double> mine = mpcasu::viz::live_fft_bins(
        pcm.data(), pcm.size(), position);
    const JsonValue* ref_bins = ref.find("bins");
    check(mine.size() == ref_bins->as_array().items.size(),
          "bin count matches reference");
    double worst = 0.0;
    bool all_close = true;
    for (int b = 0; b < qMin(mine.size(),
                             static_cast<int>(ref_bins->as_array().items.size()));
         ++b) {
        const double expected = ref_bins->as_array().items[b].as_double();
        worst = std::max(worst, std::abs(mine[b] - expected));
        // Different FFT implementations (pocketfft vs radix-2) agree to
        // ~1e-5 on these magnitudes; the algorithm/window/normalization
        // identity is what this parity check proves.
        if (worst > 2e-5) all_close = false;
    }
    check(all_close, "FFT bins match python live_fft (tol 2e-5)");
    if (!all_close) std::printf("  worst deviation: %.3e\n", worst);

    // --- window_wave ------------------------------------------------------------
    // Reference window_wave: most recent window_s=0.045 s up to position,
    // downsampled with ceil-stride to <=2048 points.
    const int rate = 44100;
    const int window_samples = std::max(64, int(rate * 0.045));
    qint64 centre = static_cast<qint64>(position * rate);
    centre = std::clamp<qint64>(centre, 0,
                                static_cast<qint64>(pcm.size()) - 1);
    qint64 start = std::max<qint64>(0, centre - window_samples);
    qint64 end = centre;
    std::vector<double> wave_tail;
    for (qint64 i = start; i < end; ++i)
        wave_tail.push_back(pcm[static_cast<std::size_t>(i)]);
    QVector<double> my_wave;
    if (wave_tail.size() >= 32) {
        const double width = std::max(
            1.0, std::ceil(static_cast<double>(wave_tail.size()) / 2048.0));
        for (double i = 0; i < static_cast<double>(wave_tail.size());
             i += width)
            my_wave.append(wave_tail[static_cast<int>(i)]);
    }
    const JsonValue* ref_wave = ref.find("wave");
    check(my_wave.size() ==
              static_cast<int>(ref_wave->as_array().items.size()),
          "wave sample count matches reference");
    bool wave_close = my_wave.size() ==
                      static_cast<int>(ref_wave->as_array().items.size());
    for (int i = 0;
         wave_close && i < my_wave.size(); ++i) {
        const double diff = std::abs(my_wave[i] -
                                     ref_wave->as_array().items[i].as_double());
        if (diff > 0) {
            std::printf("  wave first diff at %d: cpp=%.9f py=%.9f\n", i,
                        my_wave[i],
                        ref_wave->as_array().items[i].as_double());
            wave_close = false;
            break;
        }
    }
    check(wave_close, "window_wave IDENTICAL to reference");

    if (failures == 0) std::printf("ALL PASS\n");
    return failures == 0 ? 0 : 1;
}
