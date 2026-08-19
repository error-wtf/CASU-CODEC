// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "worker.hpp"

#include "casu/codec/tools.hpp"

#include <QByteArray>
#include <QMetaObject>
#include <QObject>
#include <QProcess>
#include <QStringList>

#include <algorithm>
#include <utility>

namespace casu::conv {

namespace {

std::string last_error_line(const QByteArray& error) {
    QByteArray line = error;
    while (line.endsWith('\n') || line.endsWith('\r')) line.chop(1);
    const int idx = line.lastIndexOf('\n');
    return (idx >= 0 ? line.mid(idx + 1) : line).toStdString();
}

// Streaming ffmpeg runner: argument arrays (never shell strings), live
// progress from `-progress pipe:1` and clean cancellation (kill on demand).
RunOutcome run_ffmpeg_streaming(const std::vector<std::string>& args,
                                double duration_seconds,
                                const std::function<void(double)>& progress,
                                const std::function<bool()>& cancelled) {
    const std::string executable = casu::codec::ffmpeg_path();
    if (executable.empty()) return RunOutcome{false, "required tool not found: ffmpeg", {}};

    QProcess proc;
    proc.setProcessChannelMode(QProcess::SeparateChannels);
    proc.setProgram(QString::fromUtf8(executable.c_str()));
    QStringList qargs;
    qargs.reserve(int(args.size()));
    for (const auto& arg : args) qargs << QString::fromUtf8(arg.c_str());
    proc.setArguments(qargs);
    proc.start();
    if (!proc.waitForStarted(10000))
        return RunOutcome{false, "could not start ffmpeg: " + executable, {}};

    QByteArray buffer;
    while (proc.state() == QProcess::Running) {
        if (cancelled && cancelled()) {
            proc.kill();
            proc.waitForFinished(5000);
            throw ConversionCancelled{};
        }
        proc.waitForReadyRead(60);
        buffer += proc.readAllStandardOutput();
        int nl = -1;
        while ((nl = buffer.indexOf('\n')) >= 0) {
            const QByteArray line = buffer.left(nl);
            buffer.remove(0, nl + 1);
            if (line.startsWith("out_time_us=") && duration_seconds > 0.0) {
                bool ok = false;
                const qint64 us = line.mid(12).toLongLong(&ok);
                if (ok && us >= 0)
                    progress(std::min(0.98, std::max(0.0, (double)us / 1e6 / duration_seconds)));
            }
        }
        proc.readAllStandardError();
    }
    proc.waitForFinished(5000);
    const QByteArray rest = proc.readAllStandardOutput();
    const QByteArray err = proc.readAllStandardError();
    if (proc.exitCode() != 0)
        return RunOutcome{false, last_error_line(err),
                          std::string(rest.constData(), (std::size_t)rest.size())};
    return RunOutcome{true, {}, std::string(rest.constData(), (std::size_t)rest.size())};
}

}  // namespace

void run_conversion_jobs(std::vector<ConversionJob> jobs,
                         std::shared_ptr<std::atomic<bool>> cancel,
                         std::shared_ptr<std::vector<ConversionResult>> results,
                         QObject* ui,
                         std::function<void(const ConversionProgress&)> ui_progress,
                         std::function<void(const QString&)> ui_finished) {
    auto to_ui = [ui](auto callback) {
        if (ui) QMetaObject::invokeMethod(ui, callback, Qt::QueuedConnection);
    };

    const auto cancelled = [cancel]() { return cancel && cancel->load(); };
    const FfmpegExecutor streaming =
        [cancelled](const std::vector<std::string>& args, double duration,
                    const std::function<void(double)>& progress,
                    const std::function<bool()>&) -> RunOutcome {
        return run_ffmpeg_streaming(args, duration, progress, cancelled);
    };

    bool cancelled_flag = false;
    try {
        ConversionEngine engine;
        std::vector<ConversionResult> completed = engine.run(
            jobs, streaming,
            [&](const ConversionProgress& p) {
                to_ui([p, ui_progress]() { if (ui_progress) ui_progress(p); });
            },
            cancelled);
        *results = std::move(completed);
    } catch (const ConversionCancelled&) {
        cancelled_flag = true;
    } catch (const std::exception& exc) {
        to_ui([ui_finished, exc]() {
            if (ui_finished) ui_finished(QString::fromUtf8(exc.what()));
        });
        return;
    }
    to_ui([ui_finished, cancelled_flag]() {
        if (ui_finished)
            ui_finished(cancelled_flag
                            ? QStringLiteral("Conversion cancelled; no incomplete output was kept.")
                            : QStringLiteral("Conversion complete."));
    });
}

}  // namespace casu::conv