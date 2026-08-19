// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "settings.hpp"

#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QStandardPaths>

namespace mpcasu {

QString app_config_dir() {
    const QString base = QCoreApplication::applicationDirPath();
    QDir dir(base + "/config");
    if (!dir.exists()) dir.mkpath(".");
    return dir.absolutePath();
}

AppSettings SettingsStore::load() const {
    AppSettings s;
    QFile f(path_);
    if (!f.open(QIODevice::ReadOnly)) return s;
    QJsonParseError err;
    const QJsonDocument doc = QJsonDocument::fromJson(f.readAll(), &err);
    if (err.error != QJsonParseError::NoError || !doc.isObject()) return s;
    const QJsonObject o = doc.object();
    s.volume = o.value("volume").toInt(100);
    s.volume = qBound(0, s.volume, 200);
    s.muted = o.value("muted").toBool(false);
    s.rate = o.value("rate").toDouble(1.0);
    s.shuffle = o.value("shuffle").toBool(false);
    s.repeat = o.value("repeat").toString("off");
    s.snapshot_dir = o.value("snapshot_dir").toString();
    s.record_dir = o.value("record_dir").toString();
    s.library_dir = o.value("library_dir").toString();
    s.last_playlist = o.value("last_playlist").toString();
    return s;
}

void SettingsStore::save(const AppSettings& s) const {
    QJsonObject o;
    o["volume"] = s.volume;
    o["muted"] = s.muted;
    o["rate"] = s.rate;
    o["shuffle"] = s.shuffle;
    o["repeat"] = s.repeat;
    o["snapshot_dir"] = s.snapshot_dir;
    o["record_dir"] = s.record_dir;
    o["library_dir"] = s.library_dir;
    o["last_playlist"] = s.last_playlist;
    QFile f(path_);
    if (!f.open(QIODevice::WriteOnly)) return;
    f.write(QJsonDocument(o).toJson(QJsonDocument::Indented));
}

}  // namespace mpcasu
