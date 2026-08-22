// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Full port of casu/recording.py MediaRecorder semantics (see header).
#include "recording.hpp"

#include "casu/codec/ffprobe.hpp"
#include "casu/codec/tools.hpp"
#include "casu/formats.hpp"
#include "casu/json.hpp"
#include <QPointer>

#include <QDateTime>
#include <QDir>
#include <QFile>

#include <cmath>
#include <filesystem>
#include <thread>

namespace fs = std::filesystem;

namespace mpcasu {

namespace {

// casu/recording.py destination whitelist.
bool format_allowed(const QString& suffix) {
    static const QStringList allowed = {
        ".mkv", ".mp4", ".mov", ".ts", ".m2ts",
        ".webm", ".ogg", ".mp3", ".flac", ".wav"};
    return allowed.contains(suffix.toLower());
}

QString resolved_path(const QString& raw) {
    return QDir::cleanPath(QDir::current().absoluteFilePath(raw));
}

}  // namespace

RecordingController::RecordingController(QObject* parent) : QObject(parent) {}

RecordingController::~RecordingController() {
    if (proc_ && proc_->state() != QProcess::NotRunning) {
        proc_->terminate();
        if (!proc_->waitForFinished(3000)) proc_->kill();
    }
    cleanup_temp();
}

QString RecordingController::temporary_for(
    const QString& destination) const {
    const QFileInfo info(destination);
    const QString stem = info.completeBaseName();
    const QString suffix = info.suffix().isEmpty()
                               ? QString()
                               : QStringLiteral(".") + info.suffix();
    return info.absoluteDir().filePath(
        QStringLiteral(".%1.recording-%2%3")
            .arg(stem)
            .arg(QDateTime::currentMSecsSinceEpoch())
            .arg(suffix));
}

void RecordingController::cleanup_temp() {
    if (!temporary_.isEmpty() && QFile::exists(temporary_))
        QFile::remove(temporary_);
    temporary_.clear();
}

bool RecordingController::start(const QString& source,
                                const QString& destination, QString* error) {
    auto fail = [&](const char* msg) {
        if (error) *error = QString::fromLatin1(msg);
        state_ = State::Failed;
        if (on_state_changed) on_state_changed();
        return false;
    };
    // Source validation (reference ctor).
    if (source.isEmpty() || source.contains(u'\0') ||
        source.toUtf8().size() > 8192)
        return fail("recording source is invalid");
    // Destination format whitelist.
    const QFileInfo dest_info(destination);
    if (dest_info.suffix().isEmpty() ||
        !format_allowed(QStringLiteral(".") + dest_info.suffix()))
        return fail("recording destination format is unsupported");
    // Self-overwrite protection.
    if (resolved_path(source) == resolved_path(destination))
        return fail("recording cannot overwrite its source");

    QDir().mkpath(dest_info.absolutePath());
    if (proc_ && proc_->state() != QProcess::NotRunning) stop();

    const std::string exe = casu::codec::ffmpeg_path();
    if (exe.empty()) return fail("FFmpeg is required for recording");
    source_ = source;
    destination_ = QDir::cleanPath(destination);
    temporary_ = temporary_for(destination_);

    state_ = State::Starting;
    proc_ = new QProcess(this);
    proc_->setProgram(QString::fromStdString(exe));
    proc_->setArguments(QStringList{
        QStringLiteral("-nostdin"), QStringLiteral("-hide_banner"),
        QStringLiteral("-loglevel"), QStringLiteral("error"),
        QStringLiteral("-i"), source_,
        QStringLiteral("-map"), QStringLiteral("0"),
        QStringLiteral("-map_metadata"), QStringLiteral("0"),
        QStringLiteral("-map_chapters"), QStringLiteral("0"),
        QStringLiteral("-c"), QStringLiteral("copy"),
        QStringLiteral("-y"), temporary_});
    connect(proc_, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            this, &RecordingController::handle_finished);
    proc_->start();
    if (!proc_->waitForStarted(10000)) {
        cleanup_temp();
        return fail("could not start recording");
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
    cleanup_temp();
}

void RecordingController::handle_finished(int code,
                                          QProcess::ExitStatus status) {
    (void)status;
    // The muxed file and its probe are authoritative: a clean SIGTERM shows
    // up as exit 255 in some builds and must NOT mark the recording failed
    // (reference finish() semantics).
    publish_async();
}

void RecordingController::publish_async() {
    const QString temporary = temporary_;
    const QString destination = destination_;
    QPointer<RecordingController> guard(this);
    std::thread([guard, temporary, destination] {
        bool ok = false;
        QString detail;
        QString published;
        do {
            QFile tmp_file(temporary);
            if (!tmp_file.exists() || tmp_file.size() <= 0) {
                detail = QStringLiteral("recording produced no media");
                break;
            }
            casu::JsonValue probe;
            try {
                probe = casu::codec::probe_json(temporary.toStdString());
            } catch (const std::exception& exc) {
                detail = QStringLiteral("recording verification failed: %1")
                             .arg(QString::fromStdString(exc.what()));
                break;
            }
            bool playable = false;
            if (const casu::JsonValue* streams = probe.find("streams");
                streams && streams->is_array()) {
                for (const casu::JsonValue& s : streams->as_array().items) {
                    const casu::JsonValue* kind =
                        s.is_object() ? s.find("codec_type") : nullptr;
                    if (kind && kind->is_string() &&
                        (kind->as_string() == "audio" ||
                         kind->as_string() == "video")) {
                        playable = true;
                        break;
                    }
                }
            }
            if (!playable) {
                detail =
                    QStringLiteral("recording has no playable audio/video stream");
                break;
            }
            QFile::remove(destination);  // replace-existing rename
            std::error_code ec;
            fs::rename(temporary.toStdString(), destination.toStdString(), ec);
            if (ec) {
                detail = QStringLiteral("recording publish failed: %1")
                             .arg(QString::fromStdString(ec.message()));
                break;
            }
            ok = true;
            published = destination;
            detail = QStringLiteral("verified");
        } while (false);
        if (!ok) {
            QFile::remove(temporary);
        }
        if (!guard) return;
        QMetaObject::invokeMethod(guard, [guard, ok, published, detail] {
            if (!guard) return;
            guard->temporary_.clear();
            guard->state_ = State::Idle;
            if (guard->on_state_changed) guard->on_state_changed();
            if (guard->on_finished)
                guard->on_finished(published, ok, detail);
        });
    }).detach();
}

}  // namespace mpcasu
