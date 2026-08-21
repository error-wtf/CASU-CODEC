// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Media library (WP-MPCASU-031, pragmatic JSON-file version). Stores entries
// (path, title, kind, added timestamp) in a JSON document under the config
// dir; play/remove/add/clear against the player.
#pragma once
#include <QMap>
#include <QString>
#include <QVector>

namespace mpcasu {

struct LibraryEntry {
    QString path;
    QString title;
    QString kind;  // "video" | "audio" | "playlist" | "stream"
    qint64 added_ms = 0;
    bool favorite = false;  // Linux parity: favorites mode
};

// Linux parity (casu.library.PlaybackPreferences): per-media track and A/V
// delay recall, persisted next to the library JSON.
struct PlaybackPreferences {
    int audio_track = -1;
    int video_track = -1;
    int subtitle_track = -1;
    double audio_delay_ms = 0.0;
    double subtitle_delay_ms = 0.0;
};

class MediaLibrary {
public:
    explicit MediaLibrary(QString path) : path_(std::move(path)) {}

    void load();
    void save();
    void add(const QString& path, const QString& title);
    void remove(int index);
    void clear();
    void set_favorite(const QString& path, bool favorite);
    int index_of(const QString& path) const;
    const QVector<LibraryEntry>& entries() const { return entries_; }

    PlaybackPreferences playback_preferences(const QString& path) const;
    void set_playback_preferences(const QString& path, const PlaybackPreferences& prefs);

private:
    void load_prefs() const;

    QString path_;
    QVector<LibraryEntry> entries_;
    mutable QMap<QString, PlaybackPreferences> prefs_;
    mutable bool prefs_loaded_ = false;
};

}  // namespace mpcasu
