// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// MPCASU GUI smoke test. Launches the cross-built MPCASU.exe under the Wine
// test harness and asserts:
//  1. --smoke run: the process starts (no missing DLL), the window becomes
//     visible, and it exits cleanly with code 0.
//  2. --play-test run (when a media file is given): the player kernel opens
//     the media and reaches PLAYING/LOADING without error.
#include <QCoreApplication>
#include <QDir>
#include <QProcess>
#include <QStringList>

#include <cstdio>

namespace {
// Convert a POSIX path into the Wine drive form libVLC can open
// (Z:\ = the root drive; media_new_path requires backslashes).
QString wine_path(const QString& path) {
    QString p = QDir::toNativeSeparators(path);
    if (p.startsWith('\\') || p.startsWith('/'))
        p = QStringLiteral("Z:") + p;
    return p;
}

bool run_app(const QString& exe, const QStringList& args, int timeout_ms,
             const QByteArray& marker, int* exit_code, QByteArray* output) {
    QProcess p;
    p.setProgram(exe);
    p.setArguments(args);
    p.start();
    if (!p.waitForStarted(20000)) {
        std::printf("FAIL MPCASU could not be started (missing DLL?)\n");
        return false;
    }
    if (!p.waitForFinished(timeout_ms)) {
        p.kill();
        std::printf("FAIL MPCASU run timed out\n");
        return false;
    }
    *output = p.readAll();
    *exit_code = p.exitCode();
    return marker.isEmpty() || output->contains(marker);
}
}  // namespace

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    if (argc < 2) {
        std::printf("FAIL usage: mpcasu_smoke_test <MPCASU.exe> [media]\n");
        return 1;
    }
    const QString exe = QString::fromLocal8Bit(argv[1]);
    const bool has_media = argc >= 3;
    int failures = 0;

    {
        QStringList args{ QStringLiteral("--smoke"), QStringLiteral("--vout"), QStringLiteral("dummy"),
                          QStringLiteral("--aout"), QStringLiteral("dummy") };
        if (has_media) args << wine_path(QString::fromLocal8Bit(argv[2]));
        int rc = -1;
        QByteArray out;
        const bool ok = run_app(exe, args, 90000, "MPCASU_SMOKE_CLEAN_EXIT", &rc, &out);
        const bool visible = out.contains("MPCASU_WINDOW_VISIBLE=1");        const bool pass = ok && rc == 0 && visible;
        std::printf("%s smoke run exit=%d visible=%s\n",
                    pass ? "PASS" : "FAIL", rc, visible ? "yes" : "no");
        if (!pass) { ++failures; std::printf("%s\n", out.constData()); }
    }

    if (has_media) {
        QStringList args{ QStringLiteral("--play-test"), QStringLiteral("--vout"), QStringLiteral("dummy"),
                          QStringLiteral("--aout"), QStringLiteral("dummy"),
                          wine_path(QString::fromLocal8Bit(argv[2])) };
        int rc = -1;
        QByteArray out;
        const bool ok = run_app(exe, args, 90000, "MPCASU_PLAY_STATE=", &rc, &out);
        const bool pass = ok && rc == 0;
        std::printf("%s play-test exit=%d (%s)\n",
                    pass ? "PASS" : "FAIL", rc,
                    out.mid(out.indexOf("MPCASU_PLAY_STATE="), 60).trimmed().constData());
        if (!pass) { ++failures; std::printf("%s\n", out.constData()); }
    }

    std::printf(failures == 0 ? "ALL PASS\n" : "%d FAILURES\n", failures);
    return failures == 0 ? 0 : 1;
}
