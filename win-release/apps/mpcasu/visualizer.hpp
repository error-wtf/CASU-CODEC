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

namespace mpcasu {

class VisualizerWidget final : public QWidget {
public:
    explicit VisualizerWidget(QWidget* parent = nullptr);

    void set_playing(bool playing);
    void set_active(bool active);

protected:
    void paintEvent(QPaintEvent* event) override;

private:
    void tick();

    QTimer timer_;
    bool playing_ = false;
    bool active_ = true;
    double phase_ = 0.0;
};

}  // namespace mpcasu
