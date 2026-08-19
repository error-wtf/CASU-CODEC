// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CASU-Converter — Qt Widgets GUI entry point. `--smoke-test` opens the main
// window and auto-quits after a short delay so the Wine harness can verify a
// clean start (no missing DLLs) without hanging.
#include "mainwindow.hpp"
#include "theme.hpp"

#include <QApplication>
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

    const bool smoke_test = app.arguments().contains("--smoke-test");
    if (smoke_test) {
        std::printf("SMOKE converter window shown\n");
        std::fflush(stdout);
        QTimer::singleShot(1500, &app, &QCoreApplication::quit);
    }
    return app.exec();
}