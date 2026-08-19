// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Tabbed embedded web-player views (Spotify/Hearthis/Tidal/Netflix/BROWSE).
// Exact port of mpcasu_qt/webplayers.py using the same embedded browser
// technology as Linux: QtWebEngine (Chromium in-process). No external
// browser, no link-out.
//
// QtWebEngine is only shipped by Qt for MSVC toolchains, so this compiles
// only when the target provides QtWebEngine (the Windows MSVC build). On the
// MinGW cross build (which lacks QtWebEngine) the tabs are compiled in a
// disabled stub so the app still builds and runs; the MSVC build enables the
// real embedded browser. Enabled/disabled is decided at CMake time via
// CASU_HAVE_WEBENGINE.
#pragma once

#include "casu/web/webproviders.hpp"

#include <QMap>
#include <QString>
#include <QWidget>

class QLineEdit;
class QTabWidget;

namespace mpcasu {

class WebPlayerTabs final : public QWidget {
public:
    explicit WebPlayerTabs(QWidget* parent = nullptr);

    // Load a provider's web player at a search query or direct URL.
    void open(const QString& provider, const QString& query = {},
              const QString& url = {});

    // Switch to a provider's entry field (select-all + focus).
    void focus_entry(const QString& provider);

    QTabWidget* tabs() const { return tabs_; }

private:
    void build_tabs();
    void submit(const QString& key);
    void submit_browse();
    QWidget* make_page(const QString& label, QLineEdit** entry_out);

    QTabWidget* tabs_ = nullptr;
    // provider key -> URL/search entry
    QMap<QString, QLineEdit*> entries_;
    // provider key -> embedded view (opaque; owned by the page widget)
    QMap<QString, QWidget*> views_;
};

}  // namespace mpcasu