// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "settings.hpp"

#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QJsonArray>
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
    s.visualizer = o.value("visualizer").toString("spectrum");
    s.resume_playback = o.value("resume_playback").toBool(true);
    s.cache_limit_mib = qBound(64, o.value("cache_limit_mib").toInt(512), 8192);
    s.watched_folders.clear();
    for (const QJsonValue& v : o.value("watched_folders").toArray())
        s.watched_folders.append(v.toString());
    s.record_split_minutes = o.value("record_split_minutes").toInt(0);
    s.record_format = o.value("record_format").toString("mkv");
    s.ytdlp_consent = o.value("ytdlp_consent").toBool(false);
    s.session_queue.clear();
    for (const QJsonValue& v : o.value("session_queue").toArray())
        s.session_queue.append(v.toString());
    s.session_index = o.value("session_index").toInt(-1);
    s.session_position = o.value("session_position").toDouble(-1.0);
    s.geometry = QByteArray::fromBase64(o.value("geometry").toString().toLatin1());
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
    o["visualizer"] = s.visualizer;
    o["resume_playback"] = s.resume_playback;
    o["cache_limit_mib"] = s.cache_limit_mib;
    QJsonArray folders;
    for (const QString& folder : s.watched_folders) folders.append(folder);
    o["watched_folders"] = folders;
    o["record_split_minutes"] = s.record_split_minutes;
    o["record_format"] = s.record_format;
    o["ytdlp_consent"] = s.ytdlp_consent;
    QJsonArray queue;
    for (const QString& item : s.session_queue) queue.append(item);
    o["session_queue"] = queue;
    o["session_index"] = s.session_index;
    o["session_position"] = s.session_position;
    o["geometry"] = QString::fromLatin1(s.geometry.toBase64());
    QFile f(path_);
    if (!f.open(QIODevice::WriteOnly)) return;
    f.write(QJsonDocument(o).toJson(QJsonDocument::Indented));
}

}  // namespace mpcasu
