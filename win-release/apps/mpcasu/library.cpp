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
        e.favorite = o.value("favorite").toBool();
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
        o["favorite"] = e.favorite;
        arr.append(o);
    }
    QFile f(path_);
    if (!f.open(QIODevice::WriteOnly)) return;
    f.write(QJsonDocument(arr).toJson(QJsonDocument::Indented));
}

void MediaLibrary::set_favorite(const QString& path, bool favorite) {
    for (LibraryEntry& e : entries_)
        if (e.path == path) {
            e.favorite = favorite;
            save();
            return;
        }
}

int MediaLibrary::index_of(const QString& path) const {
    for (int i = 0; i < entries_.size(); ++i)
        if (entries_[i].path == path) return i;
    return -1;
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

// --- per-media playback preferences (Linux parity) -------------------------

void MediaLibrary::load_prefs() const {
    if (prefs_loaded_) return;
    prefs_loaded_ = true;
    QFile f(path_ + ".prefs.json");
    if (!f.open(QIODevice::ReadOnly)) return;
    const QJsonDocument doc = QJsonDocument::fromJson(f.readAll());
    if (!doc.isObject()) return;
    const QJsonObject root = doc.object();
    for (auto it = root.begin(); it != root.end(); ++it) {
        const QJsonObject o = it.value().toObject();
        PlaybackPreferences p;
        p.audio_track = o.value("audio_track").toInt(-1);
        p.video_track = o.value("video_track").toInt(-1);
        p.subtitle_track = o.value("subtitle_track").toInt(-1);
        p.audio_delay_ms = o.value("audio_delay_ms").toDouble(0.0);
        p.subtitle_delay_ms = o.value("subtitle_delay_ms").toDouble(0.0);
        prefs_.insert(it.key(), p);
    }
}

PlaybackPreferences MediaLibrary::playback_preferences(const QString& path) const {
    load_prefs();
    return prefs_.value(path);
}

void MediaLibrary::set_playback_preferences(const QString& path,
                                            const PlaybackPreferences& prefs) {
    load_prefs();
    prefs_.insert(path, prefs);
    QJsonObject root;
    for (auto it = prefs_.begin(); it != prefs_.end(); ++it) {
        QJsonObject o;
        o["audio_track"] = it->audio_track;
        o["video_track"] = it->video_track;
        o["subtitle_track"] = it->subtitle_track;
        o["audio_delay_ms"] = it->audio_delay_ms;
        o["subtitle_delay_ms"] = it->subtitle_delay_ms;
        root[it.key()] = o;
    }
    QFile f(path_ + ".prefs.json");
    if (!f.open(QIODevice::WriteOnly)) return;
    f.write(QJsonDocument(root).toJson(QJsonDocument::Indented));
}

}  // namespace mpcasu
