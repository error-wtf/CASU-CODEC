// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "visualizer.hpp"

#include "theme.hpp"

#include <QPainter>
#include <QtMath>

namespace mpcasu {

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

void VisualizerWidget::tick() {
    phase_ += 0.06;
    update();
}

void VisualizerWidget::paintEvent(QPaintEvent* event) {
    Q_UNUSED(event);
    QPainter p(this);
    p.fillRect(rect(), QColor(mpcasu::palette().stage));

    if (!active_) {
        p.setPen(QColor(mpcasu::palette().muted));
        p.drawText(rect(), Qt::AlignCenter, QStringLiteral("Visualizer disabled"));
        return;
    }

    const int bars = 48;
    const int gap = 3;
    const double w = (double(width()) - gap * (bars - 1)) / bars;
    const double mid = height() * 0.75;
    for (int i = 0; i < bars; ++i) {
        double env = 0.5 + 0.5 * qSin(phase_ * 2.0 + i * 0.35);
        double h = playing_ ? env * (8.0 + qAbs(qSin(phase_ + i * 0.1)) * (height() - 24.0))
                            : 4.0 + 2.0 * qAbs(qSin(phase_ * 0.5 + i * 0.2));
        double x = i * (w + gap);
        QColor color = (i % 7 == 0) ? QColor(mpcasu::palette().red) : QColor(mpcasu::palette().secondary);
        p.fillRect(QRectF(x, mid - h / 2.0, w, h), color);
    }

    p.setPen(QColor(mpcasu::palette().muted));
    QFont f = p.font();
    f.setPointSize(9);
    p.setFont(f);
    p.drawText(rect().adjusted(8, 0, -8, -4), Qt::AlignBottom | Qt::AlignLeft,
               QStringLiteral("Visualizer: decorative (libVLC owns audio; "
                              "FFT requires a native audio sink)"));
}

}  // namespace mpcasu
