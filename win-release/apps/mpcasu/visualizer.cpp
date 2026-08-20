// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "visualizer.hpp"

#include "theme.hpp"

#include <QPainter>
#include <QtMath>

namespace mpcasu {

namespace {

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
    timer_.setInterval(33);
    connect(&timer_, &QTimer::timeout, this, &VisualizerWidget::tick);
    timer_.start();
}

void VisualizerWidget::set_playing(bool playing) {
    playing_ = playing;
}

void VisualizerWidget::set_active(bool active) {
    active_ = active;
    if (!active_) timer_.stop();
    else timer_.start();
}

void VisualizerWidget::set_mode(const QString& mode) {
    mode_ = mode;
    update();
}

void VisualizerWidget::tick() {
    phase_ += 0.06;
    update();
}

void VisualizerWidget::paintEvent(QPaintEvent* event) {
    Q_UNUSED(event);
    const Palette& P = mpcasu::palette();
    QPainter p(this);
    p.fillRect(rect(), QColor(P.stage));

    if (!active_ || mode_ == "off") {
        p.setPen(QColor(P.muted));
        p.drawText(rect(), Qt::AlignCenter, QStringLiteral("Visualizer disabled"));
        return;
    }

    // Linux parity (VisualizerWidget): radial gradient stage background.
    QRadialGradient bg(rect().center(), qMax(width(), height()) * 0.75);
    bg.setColorAt(0.0, QColor(P.bg));
    bg.setColorAt(1.0, QColor(P.stage));
    p.fillRect(rect(), bg);

    const bool show_bars = mode_ == "spectrum" || mode_ == "both";
    const bool show_wave = mode_ == "waveform" || mode_ == "both";

    if (show_bars) {
        // 128 raw FFT bars, alternating #ff1e2d / #3a1015, 0.7 h, 1 px gap.
        const int bars = 128;
        const double gap = 1.0;
        const double w = (double(width()) - gap * (bars - 1)) / bars;
        const double mid = height() * 0.75;
        QVector<double> fresh;
        fresh.resize(bars);
        for (int i = 0; i < bars; ++i) {
            const double base = playing_
                                    ? (0.35 + 0.4 * qSin(phase_ * 1.3 + i * 0.28) +
                                       0.25 * qSin(phase_ * 2.9 + i * 0.11))
                                    : 0.04 + 0.03 * qAbs(qSin(phase_ * 0.5 + i * 0.2));
            fresh[i] = qBound(0.02, base, 1.0);
        }
        smooth_bands(&smoothed_bands_, fresh);
        for (int i = 0; i < bars; ++i) {
            const double h = smoothed_bands_[i] * (height() - 40.0) * 0.7;
            const double x = i * (w + gap);
            const QColor color = (i % 2 == 0) ? QColor(P.red) : QColor(P.red_dark);
            p.fillRect(QRectF(x, mid - h, w, h), color);
        }
    }

    if (show_wave) {
        // 256-point oscilloscope line, y = v*0.5h + 0.75h, red @ 0x88.
        const int samples = 256;
        QPolygonF wave;
        for (int i = 0; i < samples; ++i) {
            const double t = double(i) / samples;
            const double v = playing_
                                 ? 0.5 * qSin(phase_ * 2.5 + t * 18.0) +
                                       0.25 * qSin(phase_ * 1.7 + t * 41.0) +
                                       0.25 * qSin(phase_ * 3.1 + t * 7.0)
                                 : 0.08 * qSin(phase_ * 1.2 + t * 18.0);
            const double x = double(i) * width() / samples;
            const double y = v * 0.5 * height() + 0.75 * height();
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
               QStringLiteral("Visualizer: decorative (libVLC owns audio; "
                              "FFT requires a native audio sink)"));
}

}  // namespace mpcasu