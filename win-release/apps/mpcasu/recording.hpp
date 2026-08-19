// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// RecordingController (WP-MPCASU-035) — long-running ffmpeg QProcess with
// argument arrays (never shell strings). Records the current source to the
// configured output dir as mkv (copy stream). Start/stop + status.
// No Q_OBJECT (cross build without host moc): results via std::function.
#pragma once
#include <QProcess>
#include <QString>

#include <functional>

namespace mpcasu {

class RecordingController final : public QObject {
public:
    explicit RecordingController(QObject* parent = nullptr);
    ~RecordingController() override;

    // Start recording `source` (path or URL) to `output_path`. Returns false
    // + error when ffmpeg is missing or could not be started.
    bool start(const QString& source, const QString& output_path, QString* error);
    void stop();  // graceful terminate
    void kill();
    bool is_recording() const { return state() == State::Recording; }
    QString output_path() const { return output_path_; }

    enum class State { Idle, Starting, Recording, Stopping, Failed };
    State state() const { return state_; }

    std::function<void()> on_state_changed;
    std::function<void(const QString&, bool, const QString&)> on_finished;

private:
    void handle_finished(int code, QProcess::ExitStatus status);

    QProcess* proc_ = nullptr;
    State state_ = State::Idle;
    QString output_path_;
};

}  // namespace mpcasu
