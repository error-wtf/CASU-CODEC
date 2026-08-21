// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CASU-Converter — Qt Widgets GUI entry point. `--smoke-test` opens the main
// window and auto-quits after a short delay so the Wine harness can verify a
// clean start (no missing DLLs) without hanging.
#include "mainwindow.hpp"
#include "theme.hpp"

#include <QApplication>
#include <QPixmap>
#include <QStringList>
#include <QTimer>

#include <cstdio>

int main(int argc, char** argv) {
    QApplication app(argc, argv);
    QApplication::setApplicationName("CASU-Converter");
    QApplication::setOrganizationName("CASU");
    app.setStyleSheet(QString::fromStdString(casu::conv::application_stylesheet()));

    casu::conv::MainWindow window;
    window.show();

    const QStringList args = app.arguments();
    const bool smoke_test = args.contains("--smoke-test");
    QString screenshot;
    for (int i = 1; i < args.size(); ++i) {
        if (args[i] == "--screenshot" && i + 1 < args.size()) {
            screenshot = args[++i];
            break;
        }
    }
    if (smoke_test) {
        std::printf("SMOKE converter window shown\n");
        std::fflush(stdout);
        QTimer::singleShot(1500, &app, &QCoreApplication::quit);
    }
    if (!screenshot.isEmpty()) {
        QTimer::singleShot(1500, &window, [&app, &window, screenshot] {
            const bool ok = window.grab().save(screenshot, "PNG");
            std::printf("MPCASU_SCREENSHOT=%s ok=%d\n", qPrintable(screenshot), ok ? 1 : 0);
            std::fflush(stdout);
            app.exit(ok ? 0 : 3);
        });
    }
    return app.exec();
}