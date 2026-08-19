// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "library.hpp"

#include <QDateTime>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>

namespace mpcasu {

void MediaLibrary::load() {
    entries_.clear();
    QFile f(path_);
    if (!f.open(QIODevice::ReadOnly)) return;
    QJsonParseError err;
    const QJsonDocument doc = QJsonDocument::fromJson(f.readAll(), &err);
    if (err.error != QJsonParseError::NoError || !doc.isArray()) return;
    for (const QJsonValue& v : doc.array()) {
        const QJsonObject o = v.toObject();
        LibraryEntry e;
        e.path = o.value("path").toString();
        e.title = o.value("title").toString();
        e.kind = o.value("kind").toString();
        e.added_ms = o.value("added_ms").toVariant().toLongLong();
        if (!e.path.isEmpty()) entries_.append(e);
    }
}

void MediaLibrary::save() {
    QJsonArray arr;
    for (const LibraryEntry& e : entries_) {
        QJsonObject o;
        o["path"] = e.path;
        o["title"] = e.title;
        o["kind"] = e.kind;
        o["added_ms"] = qint64(e.added_ms);
        arr.append(o);
    }
    QFile f(path_);
    if (!f.open(QIODevice::WriteOnly)) return;
    f.write(QJsonDocument(arr).toJson(QJsonDocument::Indented));
}

void MediaLibrary::add(const QString& path, const QString& title) {
    for (const LibraryEntry& e : entries_)
        if (e.path == path) return;  // already present
    LibraryEntry e;
    e.path = path;
    e.title = title.isEmpty() ? QFileInfo(path).fileName() : title;
    e.added_ms = QDateTime::currentMSecsSinceEpoch();
    if (path.contains("://")) e.kind = "stream";
    else if (path.toLower().endsWith(".m3u") || path.toLower().endsWith(".pls")) e.kind = "playlist";
    else e.kind = "media";
    entries_.append(e);
    save();
}

void MediaLibrary::remove(int index) {
    if (index < 0 || index >= entries_.size()) return;
    entries_.removeAt(index);
    save();
}

void MediaLibrary::clear() {
    entries_.clear();
    save();
}

}  // namespace mpcasu
