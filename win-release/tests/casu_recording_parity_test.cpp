// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Parity tests for the recording port (apps/mpcasu/recording.cpp) against
// casu/recording.py semantics:
//  - source validation + destination suffix whitelist + self-overwrite guard
//  - hidden temporary file in the destination directory
//  - SIGTERM-safe finish with ffprobe verification and atomic publish
#include "recording.hpp"

#include <QCoreApplication>
#include <QEventLoop>
#include <QFile>
#include <QTemporaryDir>
#include <QTimer>

#include <cstdio>

using namespace mpcasu;

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

}  // namespace

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    if (argc < 3) {
        std::printf("usage: casu_recording_parity_test <fixture_dir> <media>\n");
        return 2;
    }
    const QString media =
        QString::fromUtf8(argv[1]) + QStringLiteral("/convert_source.mkv");
    QTemporaryDir tmp;

    RecordingController controller;

    // --- validation ----------------------------------------------------------
    QString err;
    check(!controller.start(QString(), tmp.filePath("a.mkv"), &err) &&
              err == QStringLiteral("recording source is invalid"),
          "empty source rejected");
    err.clear();
    const QString huge(9000, u'x');
    check(!controller.start(huge, tmp.filePath("a.mkv"), &err) &&
              err == QStringLiteral("recording source is invalid"),
          "oversized source rejected");
    err.clear();
    check(!controller.start(media, tmp.filePath("noext"), &err) &&
              err == QStringLiteral("recording destination format is unsupported"),
          "suffix-less destination rejected");
    err.clear();
    check(!controller.start(media, tmp.filePath("out.avi"), &err) &&
              err == QStringLiteral("recording destination format is unsupported"),
          "unsupported container (.avi) rejected");
    err.clear();
    const QString same = tmp.filePath("same.mkv");
    { QFile f(same); f.open(QIODevice::WriteOnly); f.write("x"); }
    check(!controller.start(same, same, &err) &&
              err == QStringLiteral("recording cannot overwrite its source"),
          "self-overwrite rejected");

    // --- end-to-end: copy-record the lossless fixture, then verify+publish ---
    QEventLoop loop;
    const QString destination = tmp.filePath("recorded.mkv");
    bool done = false;
    bool published_ok = false;
    QString published_path;
    bool stop_requested = false;
    RecordingController runner;
    runner.on_finished = [&](const QString& out, bool ok,
                             const QString& detail) {
        if (!stop_requested) return;
        Q_UNUSED(detail);
        published_ok = ok && QFile::exists(out);
        published_path = out;
        done = true;
        loop.quit();
    };
    if (!runner.start(media, destination, &err)) {
        std::printf("FAIL recording could not start: %s\n",
                    err.toStdString().c_str());
        ++failures;
        return 1;
    }
    QFile dst_probe(destination);
    check(!dst_probe.exists(), "destination not created before verification");

    QTimer::singleShot(300, [&] {
        stop_requested = true;
        runner.stop();
    });
    QTimer killer;
    killer.setSingleShot(true);
    QObject::connect(&killer, &QTimer::timeout, [&] { loop.quit(); });
    killer.start(60000);
    loop.exec();

    check(done, "finish callback fired");
    check(published_ok, "recording verified and atomically published");
    check(QFile::exists(published_path) && published_path == destination,
          "published path equals destination");
    bool stray_temp = false;
    for (const QString& entry : QDir(tmp.path()).entryList(QDir::Files))
        if (entry.contains(QStringLiteral(".recording-"))) stray_temp = true;
    check(!stray_temp, "no temporary recording files remain");

    if (failures == 0) std::printf("ALL PASS\n");
    return failures == 0 ? 0 : 1;
}
