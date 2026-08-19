// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "web_player_tabs.hpp"

#include <QDir>
#include <QHBoxLayout>
#include <QLineEdit>
#include <QTabWidget>
#include <QVBoxLayout>
#include <QUrl>

#if defined(CASU_HAVE_WEBENGINE)
#include <QtWebEngineWidgets/QWebEnginePage>
#include <QtWebEngineWidgets/QWebEngineProfile>
#include <QtWebEngineWidgets/QWebEngineView>
#include <QStandardPaths>
#endif

namespace mpcasu {

namespace {

// Directory holding the persistent QtWebEngine profile (cookies/logins) so
// provider sessions survive restarts, mirroring _persistent_profile in the
// reference (XDG_CONFIG_HOME on Linux -> %APPDATA% on Windows).
QString profile_storage_dir() {
#if defined(CASU_HAVE_WEBENGINE)
    const QString base = QStandardPaths::writableLocation(QStandardPaths::AppDataLocation);
    if (base.isEmpty()) return QString();
    return base + QLatin1String("/webengine");
#else
    return QString();
#endif
}

}  // namespace

WebPlayerTabs::WebPlayerTabs(QWidget* parent) : QWidget(parent) {
    setObjectName(QStringLiteral("WebPlayers"));
    build_tabs();
}

void WebPlayerTabs::build_tabs() {
    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);
    tabs_ = new QTabWidget(this);
    tabs_->setDocumentMode(true);
    layout->addWidget(tabs_);

#if defined(CASU_HAVE_WEBENGINE)
    QWebEngineProfile* profile = new QWebEngineProfile(QStringLiteral("mpcasu"), this);
    profile->setPersistentCookiesPolicy(QWebEngineProfile::ForcePersistentCookies);
    const QString storage = profile_storage_dir();
    if (!storage.isEmpty()) {
        QDir().mkpath(storage);
        profile->setPersistentStoragePath(storage);
    }
    profile->setHttpCacheType(QWebEngineProfile::DiskHttpCache);
#else
    void* profile = nullptr;  // unused when the embedded engine is unavailable
#endif

    for (const casu::web::WebPlayerSpec& spec : casu::web::web_players()) {
        QLineEdit* entry = nullptr;
        QWidget* page = make_page(QString::fromStdString(spec.label), &entry);
        entry->setPlaceholderText(
            QStringLiteral("%1 URL oder Suchbegriff…")
                .arg(QString::fromStdString(spec.label)));
        const QString key = QString::fromStdString(spec.key);
        QObject::connect(entry, &QLineEdit::returnPressed,
                         this, [this, key] { submit(key); });
        entries_[key] = entry;
#if defined(CASU_HAVE_WEBENGINE)
        auto* view = new QWebEngineView(page);
        view->setPage(new QWebEnginePage(
            static_cast<QWebEngineProfile*>(profile), view));
        views_[key] = view;
        qobject_cast<QVBoxLayout*>(page->layout())->addWidget(view);
#else
        views_[key] = nullptr;
#endif
        tabs_->addTab(page, QString::fromStdString(spec.label));
    }

    // BROWSE tab: a general embedded browser (loads any site directly).
    QLineEdit* browse_entry = nullptr;
    QWidget* browse_page = make_page(QStringLiteral("BROWSE"), &browse_entry);
    browse_entry->setPlaceholderText(
        QStringLiteral("Browse — URL oder DuckDuckGo-Suche…"));
    QObject::connect(browse_entry, &QLineEdit::returnPressed,
                     this, [this] { submit_browse(); });
    entries_[QStringLiteral("browse")] = browse_entry;
#if defined(CASU_HAVE_WEBENGINE)
    auto* browse_view = new QWebEngineView(browse_page);
    browse_view->setPage(new QWebEnginePage(
        static_cast<QWebEngineProfile*>(profile), browse_view));
    views_[QStringLiteral("browse")] = browse_view;
    qobject_cast<QVBoxLayout*>(browse_page->layout())->addWidget(browse_view);
#else
    views_[QStringLiteral("browse")] = nullptr;
#endif
    tabs_->addTab(browse_page, QStringLiteral("BROWSE"));
}

QWidget* WebPlayerTabs::make_page(const QString& label, QLineEdit** entry_out) {
    Q_UNUSED(label);
    auto* page = new QWidget(this);
    page->setStyleSheet(QStringLiteral("background: transparent;"));
    auto* page_layout = new QVBoxLayout(page);
    page_layout->setContentsMargins(6, 6, 6, 6);
    page_layout->setSpacing(6);
    auto* entry = new QLineEdit(page);
    entry->setObjectName(QStringLiteral("IconButton"));
    page_layout->addWidget(entry);
    if (entry_out) *entry_out = entry;
    return page;
}

void WebPlayerTabs::submit(const QString& key) {
    QLineEdit* entry = entries_.value(key);
    if (!entry) return;
    QString text = entry->text().trimmed();
    if (text.isEmpty()) return;
    const bool is_url = text.contains(QLatin1String("://")) && text.contains(QLatin1Char('.'));
    if (key == QLatin1String("spotify") && is_url) {
        text = QString::fromStdString(casu::web::spotify_embed_url(text.toStdString()));
    }
    open(key, is_url ? QString() : text, is_url ? text : QString());
}

void WebPlayerTabs::submit_browse() {
    QLineEdit* entry = entries_.value(QStringLiteral("browse"));
    if (!entry) return;
    QString text = entry->text().trimmed();
    if (text.isEmpty()) return;
    QString target;
    if (text.contains(QLatin1String("://")) && text.contains(QLatin1Char('.'))) {
        target = text;
    } else {
        QString q = text;
        q.replace(QLatin1Char(' '), QLatin1String("+"));
        target = QStringLiteral("https://duckduckgo.com/?q=") + q;
    }
#if defined(CASU_HAVE_WEBENGINE)
    if (auto* view = static_cast<QWebEngineView*>(views_.value(QStringLiteral("browse"))))
        view->load(QUrl(target));
#endif
}

void WebPlayerTabs::open(const QString& provider, const QString& query,
                         const QString& url) {
    QString key = provider;
    int browse_index = tabs_->count() - 1;
    if (key == QLatin1String("browse")) {
        tabs_->setCurrentIndex(browse_index);
#if defined(CASU_HAVE_WEBENGINE)
        if (auto* view = static_cast<QWebEngineView*>(views_.value(key))) {
            QString target = url;
            if (target.isEmpty())
                target = query.isEmpty()
                             ? QString::fromStdString(casu::web::browse_url())
                             : QStringLiteral("https://duckduckgo.com/?q=") +
                                   QString(query).replace(QLatin1Char(' '), QLatin1String("+"));
            view->load(QUrl(target));
        }
#endif
        return;
    }
    // Default unknown providers to spotify, matching WEB_PLAYERS.get(...).
    if (!entries_.contains(key)) key = QStringLiteral("spotify");
    int index = 0;
    const auto specs = casu::web::web_players();
    for (std::size_t i = 0; i < specs.size(); ++i) {
        if (QString::fromStdString(specs[i].key) == key) { index = int(i); break; }
    }
    tabs_->setCurrentIndex(index);
    if (QLineEdit* entry = entries_.value(key))
        if (!query.isEmpty()) entry->setText(query);
    const std::string target =
        casu::web::web_player_url(key.toStdString(), query.toStdString(), url.toStdString());
#if defined(CASU_HAVE_WEBENGINE)
    if (auto* view = static_cast<QWebEngineView*>(views_.value(key)))
        view->load(QUrl(QString::fromStdString(target)));
#endif
}

void WebPlayerTabs::focus_entry(const QString& provider) {
    if (QLineEdit* entry = entries_.value(provider)) {
        entry->setFocus();
        entry->selectAll();
    }
}

}  // namespace mpcasu