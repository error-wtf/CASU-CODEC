// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Playlist model + M3U/M3U8/PLS parsing for MPCASU. Pragmatic port of the
// queue semantics (casu/playlist.py): ordered items, shuffle/repeat,
// next/prev, load/save M3U/PLS. Unicode/space-safe paths.
#pragma once
#include <QString>
#include <QStringList>
#include <QVector>

#include <random>
#include <string>
#include <vector>

namespace mpcasu {

struct PlaylistItem {
    QString path;   // local path or stream URL
    QString title;  // EXTINF / entry title or derived name
    bool is_url = false;
};

class PlaylistModel {
public:
    void clear();
    void add(const QString& path, const QString& title = QString());
    void add_files(const QStringList& paths);
    void remove(int index);
    void move(int from, int to);
    const QVector<PlaylistItem>& items() const { return items_; }
    int size() const { return items_.size(); }
    bool empty() const { return items_.isEmpty(); }
    int index_of(const QString& path) const;

    int current_index() const { return current_; }
    void set_current(int index) { current_ = index; }

    // Transport logic.
    int next_index(bool automatic_end) const;
    int previous_index() const;

    bool shuffle = false;
    enum class RepeatMode { Off, All, One };
    RepeatMode repeat = RepeatMode::Off;

    // Load/save. Returns error string (empty = ok).
    static std::string load_m3u(const QString& file, PlaylistModel* out);
    static std::string load_pls(const QString& file, PlaylistModel* out);
    static std::string load_file(const QString& file, PlaylistModel* out);
    static std::string save_m3u(const QString& file, const PlaylistModel& model);
    static std::string save_pls(const QString& file, const PlaylistModel& model);
    static bool looks_like_playlist(const QString& path);

private:
    QVector<PlaylistItem> items_;
    int current_ = -1;
    mutable std::mt19937 rng_{std::random_device{}()};
};

QString display_title_for_path(const QString& path);

}  // namespace mpcasu
