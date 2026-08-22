// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Real-FFT visualizer (see header). FFT: iterative radix-2 Cooley–Tukey,
// matching numpy rfft magnitudes for the 2048-sample Hann window.
#include "visualizer.hpp"
#include "viz_fft.hpp"

#include "casu/codec/tools.hpp"
#include "theme.hpp"

#include <QCoreApplication>
#include <QDir>
#include <QEvent>
#include <QFile>
#include <QPainter>
#include <QPainterPath>
#include <QPixmap>

#include <algorithm>
#include <cmath>
#include <complex>
#include <fstream>
#include <thread>

namespace mpcasu {

namespace {

using namespace mpcasu::viz;

// Web analyser smoothing (smoothingTimeConstant = 0.85) for the bars.
void smooth_bands(QVector<double>* out, const QVector<double>& fresh) {
    if (out->isEmpty()) {
        *out = fresh;
        return;
    }
    const int n = qMax(out->size(), fresh.size());
    out->resize(n);
    for (int i = 0; i < n; ++i) {
        const double value = i < fresh.size() ? fresh[i] : 0.0;
        (*out)[i] = 0.85 * (*out)[i] + 0.15 * value;
    }
}

}  // namespace

VisualizerWidget::VisualizerWidget(QWidget* parent) : QWidget(parent) {
    setMinimumHeight(120);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    timer_.setInterval(33);  // ~30 fps; stream pipe reads here (~40 Hz class)
    connect(&timer_, &QTimer::timeout, this, &VisualizerWidget::tick);
    if (active_ && visible_) timer_.start();
}

void VisualizerWidget::set_playing(bool playing) {
    playing_ = playing;
    // CPU-throttle parity: freeze updates when paused.
    if (playing_ && active_ && visible_) timer_.start();
    else timer_.stop();
}

void VisualizerWidget::set_active(bool active) {
    active_ = active;
    if (!active_) timer_.stop();
    else if (visible_ && playing_) timer_.start();
    update();
}

bool VisualizerWidget::event(QEvent* event) {
    if (event->type() == QEvent::Show ||
        event->type() == QEvent::Hide) {
        visible_ = event->type() == QEvent::Show;
        // CPU-throttle parity: no ticking while hidden.
        if (visible_ && active_ && playing_) timer_.start();
        else if (!visible_) timer_.stop();
    }
    return QWidget::event(event);
}

void VisualizerWidget::set_mode(const QString& mode) {
    mode_ = mode;
    update();
}

void VisualizerWidget::set_cover(const QPixmap* pixmap) {
    cover_ = pixmap;
    update();
}

void VisualizerWidget::clear_audio() {
    if (stream_pipe_) {
        if (stream_pipe_->state() != QProcess::NotRunning) {
            stream_pipe_->terminate();
            if (!stream_pipe_->waitForFinished(2000)) stream_pipe_->kill();
        }
        stream_pipe_->deleteLater();
        stream_pipe_ = nullptr;
    }
    pcm_.clear();
    stream_ring_.assign(stream_ring_.size(), 0.0f);
    ring_write_pos_ = 0;
    pcm_source_.clear();
    current_bars_.fill(0.02);
    current_wave_.clear();
    update();
}

void VisualizerWidget::set_audio_file(const QString& path) {
    if (pcm_source_ == path && !pcm_.empty()) return;
    clear_audio();
    pcm_source_ = path;
    if (path.isEmpty() || !QFile::exists(path)) return;
    if (decoding_.exchange(true)) return;
    const QString source = path;
    // decode_all_pcm: ffmpeg -> mono s16le @44100 -> float32 in [-1,1].
    std::thread([this, source] {
        QProcess proc;
        proc.setProgram(QString::fromStdString(
            casu::codec::ffmpeg_path().empty()
                ? std::string("ffmpeg")
                : casu::codec::ffmpeg_path()));
        proc.setArguments(QStringList{
            QStringLiteral("-nostdin"), QStringLiteral("-v"),
            QStringLiteral("error"), QStringLiteral("-i"), source,
            QStringLiteral("-map"), QStringLiteral("0:a:0"),
            QStringLiteral("-ac"), QStringLiteral("1"),
            QStringLiteral("-ar"), QStringLiteral("44100"),
            QStringLiteral("-f"), QStringLiteral("s16le"),
            QStringLiteral("-acodec"), QStringLiteral("pcm_s16le"),
            QStringLiteral("pipe:1")});
        proc.setProcessChannelMode(QProcess::SeparateChannels);
        proc.start();
        std::vector<float> decoded;
        if (proc.waitForStarted(10000)) {
            while (true) {
                const QByteArray chunk =
                    proc.read(64 * 1024 * 4);
                if (!chunk.isEmpty()) {
                    const int16_t* samples =
                        reinterpret_cast<const int16_t*>(chunk.constData());
                    const qsizetype count = chunk.size() / 2;
                    decoded.reserve(decoded.size() +
                                    static_cast<std::size_t>(count));
                    for (qsizetype i = 0; i < count; ++i)
                        decoded.push_back(
                            static_cast<float>(samples[i]) / 32768.0f);
                    if (decoded.size() > 8'000'000) break;  // reference cap
                    continue;
                }
                if (proc.state() != QProcess::Running &&
                    proc.bytesAvailable() == 0)
                    break;
                proc.waitForReadyRead(500);
            }
            proc.terminate();
            if (!proc.waitForFinished(3000)) proc.kill();
        }
        sample_rate_ = 44100;
        pcm_ = std::move(decoded);
        decoding_ = false;
    }).detach();
}

const float* VisualizerWidget::ring_tail(std::size_t* count) const {
    *count = stream_ring_.size();
    return stream_ring_.data();
}

void VisualizerWidget::set_stream_url(const QString& url) {
    clear_audio();
    if (url.isEmpty()) return;
    const std::string exe = casu::codec::ffmpeg_path().empty()
                                ? std::string("ffmpeg")
                                : casu::codec::ffmpeg_path();
    stream_pipe_ = new QProcess(this);
    stream_pipe_->setProgram(QString::fromStdString(exe));
    stream_pipe_->setArguments(QStringList{
        QStringLiteral("-nostdin"), QStringLiteral("-v"),
        QStringLiteral("error"), QStringLiteral("-i"), url,
        QStringLiteral("-map"), QStringLiteral("0:a:0"),
        QStringLiteral("-ac"), QStringLiteral("1"),
        QStringLiteral("-ar"), QStringLiteral("44100"),
        QStringLiteral("-f"), QStringLiteral("s16le"),
        QStringLiteral("-acodec"), QStringLiteral("pcm_s16le"),
        QStringLiteral("pipe:1")});
    stream_pipe_->setProcessChannelMode(QProcess::SeparateChannels);
    stream_pipe_->start();
    constexpr std::size_t kRingSeconds = 10;
    constexpr std::size_t kRingCapacity = 44100 * kRingSeconds;
    stream_ring_.assign(kRingCapacity, 0.0f);
    ring_write_pos_ = 0;
    // ~40 Hz drain of the pipe into the ring buffer.
    connect(&stream_timer_, &QTimer::timeout, this, [this] {
        if (!stream_pipe_ ||
            stream_pipe_->state() == QProcess::NotRunning)
            return;
        const QByteArray chunk = stream_pipe_->readAll();
        if (chunk.isEmpty()) return;
        const int16_t* samples =
            reinterpret_cast<const int16_t*>(chunk.constData());
        const qsizetype count = chunk.size() / 2;
        for (qsizetype i = 0; i < count; ++i) {
            stream_ring_[ring_write_pos_] =
                static_cast<float>(samples[i]) / 32768.0f;
            ring_write_pos_ = (ring_write_pos_ + 1) % stream_ring_.size();
        }
    });
    stream_timer_.setInterval(25);
    stream_timer_.start();
}

void VisualizerWidget::tick() {
    phase_ += 0.06;
    if (playing_) compute_frame();
    update();
}

void VisualizerWidget::compute_frame() {
    // Assemble the analysis tail: prefer decoded file PCM ending at playhead;
    // fall back to the live stream ring buffer's most recent samples.
    const double position = position_ ? position_() : 0.0;
    QVector<double> tail;
    if (!pcm_.empty()) {
        qint64 centre = static_cast<qint64>(position * sample_rate_);
        centre = std::clamp<qint64>(centre, 0,
                                    static_cast<qint64>(pcm_.size()) - 1);
        const qint64 start =
            std::max<qint64>(0, centre - static_cast<qint64>(kFftSize));
        for (qint64 i = start; i <= centre &&
                                tail.size() < kFftSize;
             ++i)
            tail.append(pcm_[static_cast<std::size_t>(i)]);
    } else if (!stream_ring_.empty()) {
        // Most recent samples up to write cursor (wrap-aware).
        const std::size_t n = stream_ring_.size();
        std::size_t count = std::min<std::size_t>(n, kFftSize);
        tail.reserve(static_cast<int>(count));
        std::size_t idx =
            (ring_write_pos_ + n - count % n) % n;
        for (std::size_t i = 0; i < count; ++i) {
            tail.append(stream_ring_[(idx + i) % n]);
        }
    }
    if (tail.size() < 64) {
        current_bars_.fill(0.04);
        current_wave_.clear();
        return;
    }

    // live_fft via the shared reference-parity implementation.
    if (mode_ == "spectrum" || mode_ == "both") {
        QVector<double> fresh;
        if (!pcm_.empty()) {
            fresh = viz::live_fft_bins(pcm_.data(), pcm_.size(), position);
        } else if (!stream_ring_.empty()) {
            std::vector<float> ordered(stream_ring_.begin(),
                                       stream_ring_.end());
            // Rotate so the write cursor is the end (live buffer semantics).
            std::rotate(ordered.begin(),
                        ordered.begin() +
                            static_cast<std::ptrdiff_t>(
                                ring_write_pos_ % ordered.size()),
                        ordered.end());
            fresh = viz::live_fft_bins(ordered.data(), ordered.size(),
                                       position);
        }
        if (!fresh.isEmpty()) smooth_bands(&smoothed_bands_, fresh);
        current_bars_ = smoothed_bands_;
    }

    // window_wave: most recent 45 ms up to playhead, downsampled.
    if (mode_ == "waveform" || mode_ == "both") {
        const int window_samples =
            std::max(64, static_cast<int>(sample_rate_ * kWelchWindowS));
        QVector<double> wave_tail;
        const qint64 total = tail.size();
        const qint64 start =
            std::max<qint64>(0, total - window_samples);
        for (qint64 i = start; i < total; ++i)
            wave_tail.append(tail[int(i)]);
        current_wave_.clear();
        if (wave_tail.size() >= 32) {
            const double width = std::max(
                1.0, std::ceil(double(wave_tail.size()) / kWavePoints));
            for (double i = 0; i < wave_tail.size(); i += width)
                current_wave_.append(wave_tail[int(i)]);
        }
    }
}

QVector<double> VisualizerWidget::live_fft_bars(int bins) const {
    Q_UNUSED(bins);
    return current_bars_;
}

QVector<double> VisualizerWidget::wave_samples(int points) const {
    Q_UNUSED(points);
    return current_wave_;
}

void VisualizerWidget::paintEvent(QPaintEvent* event) {
    Q_UNUSED(event);
    const Palette& P = mpcasu::palette();
    QPainter p(this);
    p.fillRect(rect(), QColor(P.stage));

    if (!active_ || mode_ == "off") {
        p.setPen(QColor(P.muted));
        p.drawText(rect(), Qt::AlignCenter,
                   QStringLiteral("Visualizer disabled"));
        return;
    }

    QRadialGradient bg(rect().center(), qMax(width(), height()) * 0.75);
    bg.setColorAt(0.0, QColor(P.bg));
    bg.setColorAt(1.0, QColor(P.stage));
    p.fillRect(rect(), bg);

    if (cover_ && !cover_->isNull()) {
        const int size = qBound(40, int(qMin(width(), height()) * 0.44), 480);
        const QPixmap scaled = cover_->scaled(size, size, Qt::KeepAspectRatio,
                                              Qt::SmoothTransformation);
        const int px = (width() - scaled.width()) / 2;
        const int py = (height() - scaled.height()) / 2;
        QPainterPath clip;
        clip.addRoundedRect(QRectF(px, py, scaled.width(), scaled.height()),
                            10.0, 10.0);
        p.save();
        p.setClipPath(clip);
        p.drawPixmap(px, py, scaled);
        p.restore();
    }

    const bool show_bars = mode_ == "spectrum" || mode_ == "both";
    const bool show_wave = mode_ == "waveform" || mode_ == "both";

    if (show_bars) {
        // 128 raw FFT bins (live_fft output), alternating red/dark-red.
        const int bars = 128;
        const double gap = 1.0;
        const double w = (double(width()) - gap * (bars - 1)) / bars;
        const double mid = height() * 0.75;
        for (int i = 0; i < bars; ++i) {
            double h = 0.02;
            if (i < current_bars_.size())
                h = qBound(0.02, current_bars_[i], 1.0);
            const double height_px = h * (height() - 40.0) * 0.7;
            const double x = i * (w + gap);
            const QColor color =
                (i % 2 == 0) ? QColor(P.red) : QColor(P.red_dark);
            p.fillRect(QRectF(x, mid - height_px, w, height_px), color);
        }
    }

    if (show_wave && !current_wave_.isEmpty()) {
        const int samples = current_wave_.size();
        QPolygonF wave;
        for (int i = 0; i < samples; ++i) {
            const double x = double(i) * width() /
                             std::max(1, samples - 1);
            const double y = current_wave_[i] * 0.5 * height() +
                             0.75 * height();
            wave.append(QPointF(x, y));
        }
        QColor scope(P.red);
        scope.setAlpha(0x88);
        p.setPen(QPen(scope, 2.0));
        p.drawPolyline(wave);
    }

    p.setPen(QColor(P.muted));
    QFont f = p.font();
    f.setPointSize(9);
    p.setFont(f);
    p.drawText(rect().adjusted(8, 0, -8, -4), Qt::AlignBottom | Qt::AlignLeft,
               pcm_.empty() && stream_pipe_ == nullptr
                   ? QStringLiteral(
                         "Visualizer: open media to enable the spectrum")
                   : QStringLiteral("FFT 2048 · 128 bins · decoded PCM"));
}

}  // namespace mpcasu
