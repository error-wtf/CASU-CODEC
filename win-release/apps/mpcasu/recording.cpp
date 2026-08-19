// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "recording.hpp"

#include "casu/codec/tools.hpp"

namespace mpcasu {

RecordingController::RecordingController(QObject* parent) : QObject(parent) {}

RecordingController::~RecordingController() {
    if (proc_ && proc_->state() != QProcess::NotRunning) {
        proc_->terminate();
        if (!proc_->waitForFinished(3000)) proc_->kill();
    }
}

bool RecordingController::start(const QString& source, const QString& output_path,
                                QString* error) {
    if (proc_ && proc_->state() != QProcess::NotRunning) stop();
    const std::string exe = casu::codec::ffmpeg_path();
    if (exe.empty()) {
        if (error) *error = "ffmpeg is not available";
        return false;
    }
    state_ = State::Starting;
    output_path_ = output_path;
    proc_ = new QProcess(this);
    proc_->setProgram(QString::fromStdString(exe));
    proc_->setArguments(QStringList{
        "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
        "-i", source, "-map", "0", "-c", "copy", output_path});
    connect(proc_, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            this, &RecordingController::handle_finished);
    proc_->start();
    if (!proc_->waitForStarted(10000)) {
        if (error) *error = "ffmpeg could not be started";
        state_ = State::Failed;
        if (on_state_changed) on_state_changed();
        return false;
    }
    state_ = State::Recording;
    if (on_state_changed) on_state_changed();
    return true;
}

void RecordingController::stop() {
    if (!proc_ || proc_->state() == QProcess::NotRunning) return;
    state_ = State::Stopping;
    if (on_state_changed) on_state_changed();
    proc_->terminate();
    if (!proc_->waitForFinished(6000)) proc_->kill();
}

void RecordingController::kill() {
    if (proc_ && proc_->state() != QProcess::NotRunning) proc_->kill();
}

void RecordingController::handle_finished(int code, QProcess::ExitStatus status) {
    const QString out = output_path_;
    const bool ok = state_ == State::Stopping ||
                    (status == QProcess::NormalExit && code == 0);
    state_ = State::Idle;
    if (on_state_changed) on_state_changed();
    if (on_finished) on_finished(out, ok, QString("ffmpeg exit %1").arg(code));
}

}  // namespace mpcasu
