// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Media library (WP-MPCASU-031, pragmatic JSON-file version). Stores entries
// (path, title, kind, added timestamp) in a JSON document under the config
// dir; play/remove/add/clear against the player.
#pragma once
#include <QString>
#include <QVector>

namespace mpcasu {

struct LibraryEntry {
    QString path;
    QString title;
    QString kind;  // "video" | "audio" | "playlist" | "stream"
    qint64 added_ms = 0;
};

class MediaLibrary {
public:
    explicit MediaLibrary(QString path) : path_(std::move(path)) {}

    void load();
    void save();
    void add(const QString& path, const QString& title);
    void remove(int index);
    void clear();
    const QVector<LibraryEntry>& entries() const { return entries_; }

private:
    QString path_;
    QVector<LibraryEntry> entries_;
};

}  // namespace mpcasu
