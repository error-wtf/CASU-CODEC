// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Visualizer widget (WP-MPCASU-034). Documented placeholder: libVLC owns the
// audio output, so no QAudioBuffer is available for a real spectrum; the
// widget draws animated spectrum bars while playback is active as visual
// feedback, with a documented note in the UI. A real FFT path can be wired
// when a native audio sink (NativeCasuBackend/QAudioSink) is active.
#pragma once
#include <QTimer>
#include <QWidget>

#include <vector>

class QPixmap;

namespace mpcasu {

class VisualizerWidget final : public QWidget {
public:
    explicit VisualizerWidget(QWidget* parent = nullptr);

    void set_playing(bool playing);
    void set_active(bool active);
    void set_mode(const QString& mode);
    void set_cover(const QPixmap* pixmap);  // borrowed; drawn centered when set

protected:
    void paintEvent(QPaintEvent* event) override;

private:
    void tick();

    QTimer timer_;
    bool playing_ = false;
    bool active_ = true;
    QString mode_ = "spectrum";
    double phase_ = 0.0;
    QVector<double> smoothed_bands_;  // analyser 0.85 smoothing
    const QPixmap* cover_ = nullptr; // non-owning; owned by MainWindow
};

}  // namespace mpcasu
