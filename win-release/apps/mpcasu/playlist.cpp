// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "playlist.hpp"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QRegularExpression>
#include <QTextStream>
#include <QUrl>

namespace mpcasu {

QString display_title_for_path(const QString& path) {
    if (path.contains("://")) return path;
    const QFileInfo info(path);
    return info.fileName().isEmpty() ? path : info.fileName();
}

void PlaylistModel::clear() {
    items_.clear();
    current_ = -1;
}

void PlaylistModel::add(const QString& path, const QString& title) {
    PlaylistItem item;
    item.path = path;
    item.is_url = path.contains("://");
    item.title = title.isEmpty() ? display_title_for_path(path) : title;
    item.is_playlist = looks_like_playlist(path) && QFileInfo::exists(path);
    items_.append(item);
}

void PlaylistModel::add_files(const QStringList& paths) {
    for (const QString& p : paths) add(p);
}

void PlaylistModel::remove(int index) {
    if (index < 0 || index >= items_.size()) return;
    items_.removeAt(index);
    if (current_ > index) --current_;
    else if (current_ == index) current_ = -1;
}

void PlaylistModel::remove_many(const QVector<int>& indices) {
    QVector<int> rows;
    for (int i : indices)
        if (i >= 0 && i < items_.size()) rows.append(i);
    std::sort(rows.begin(), rows.end(), std::greater<int>());
    for (int r : rows) remove(r);
}

void PlaylistModel::move(int from, int to) {
    if (from < 0 || from >= items_.size() || to < 0 || to >= items_.size() || from == to)
        return;
    items_.move(from, to);
}

void PlaylistModel::move_many(const QVector<int>& indices, int delta) {
    QVector<int> rows;
    for (int i : indices)
        if (i >= 0 && i < items_.size()) rows.append(i);
    std::sort(rows.begin(), rows.end());
    if (delta > 0) {
        for (auto it = rows.rbegin(); it != rows.rend(); ++it) move(*it, *it + 1);
    } else if (delta < 0) {
        for (int r : rows) move(r, r - 1);
    }
}

int PlaylistModel::index_of(const QString& path) const {
    for (int i = 0; i < items_.size(); ++i)
        if (items_[i].path == path) return i;
    return -1;
}

int PlaylistModel::next_index(bool automatic_end) const {
    if (items_.isEmpty()) return -1;
    if (current_ < 0) return 0;
    if (repeat == RepeatMode::One && automatic_end) return current_;
    int n = current_ + 1;
    if (n >= items_.size()) {
        if (repeat == RepeatMode::All || shuffle) n = 0;
        else return -1;
    }
    if (shuffle) {
        std::uniform_int_distribution<int> dist(0, items_.size() - 1);
        n = dist(rng_);
    }
    return n;
}

int PlaylistModel::previous_index() const {
    if (items_.isEmpty()) return -1;
    if (current_ < 0) return 0;
    int n = current_ - 1;
    if (n < 0) n = items_.size() - 1;
    return n;
}

std::string PlaylistModel::load_m3u(const QString& file, PlaylistModel* out) {
    QFile f(file);
    if (!f.open(QIODevice::ReadOnly))
        return ("could not open playlist: " + file).toStdString();
    QTextStream ts(&f);
    ts.setEncoding(QStringConverter::Utf8);
    QString pending_title;
    const QDir base = QFileInfo(file).absoluteDir();
    out->clear();
    while (!ts.atEnd()) {
        QString line = ts.readLine().trimmed();
        if (line.isEmpty()) continue;
        if (line.startsWith('#')) {
            if (line.startsWith("#EXTINF:") && line.contains(',')) {
                pending_title = line.section(',', 1).trimmed();
            }
            continue;
        }
        QString target = line;
        if (target.startsWith("file://")) {
            target = QUrl(target).toLocalFile();
        } else if (!target.contains("://")) {
            QFileInfo cand(target);
            if (cand.isRelative())
                target = QFileInfo(base.filePath(target)).absoluteFilePath();
        }
        out->add(target, pending_title);
        pending_title.clear();
    }
    return {};
}

std::string PlaylistModel::load_pls(const QString& file, PlaylistModel* out) {
    QFile f(file);
    if (!f.open(QIODevice::ReadOnly))
        return ("could not open playlist: " + file).toStdString();
    QTextStream ts(&f);
    ts.setEncoding(QStringConverter::Utf8);
    QVector<std::pair<int, QString>> entries;
    QMap<int, QString> titles;
    const QDir base = QFileInfo(file).absoluteDir();
    while (!ts.atEnd()) {
        QString line = ts.readLine().trimmed();
        QRegularExpression reFile("^File(\\d+)=(.*)$");
        QRegularExpression reTitle("^Title(\\d+)=(.*)$");
        auto m = reFile.match(line);
        if (m.hasMatch()) {
            QString target = m.captured(2).trimmed();
            if (target.startsWith("file://")) target = QUrl(target).toLocalFile();
            else if (!target.contains("://") && QFileInfo(target).isRelative())
                target = QFileInfo(base.filePath(target)).absoluteFilePath();
            entries.append({m.captured(1).toInt(), target});
            continue;
        }
        m = reTitle.match(line);
        if (m.hasMatch()) titles[m.captured(1).toInt()] = m.captured(2).trimmed();
    }
    std::sort(entries.begin(), entries.end(),
              [](const auto& a, const auto& b) { return a.first < b.first; });
    out->clear();
    for (const auto& [idx, target] : entries)
        out->add(target, titles.value(idx));
    return {};
}

std::string PlaylistModel::load_file(const QString& file, PlaylistModel* out) {
    QString lower = file.toLower();
    if (lower.endsWith(".pls")) return load_pls(file, out);
    return load_m3u(file, out);
}

std::string PlaylistModel::save_m3u(const QString& file, const PlaylistModel& model) {
    QFile f(file);
    if (!f.open(QIODevice::WriteOnly | QIODevice::Text))
        return ("could not write playlist: " + file).toStdString();
    QTextStream ts(&f);
    ts.setEncoding(QStringConverter::Utf8);
    ts << "#EXTM3U\n";
    for (const PlaylistItem& item : model.items()) {
        ts << "#EXTINF:-1," << item.title << "\n";
        ts << item.path << "\n";
    }
    return {};
}

std::string PlaylistModel::save_pls(const QString& file, const PlaylistModel& model) {
    QFile f(file);
    if (!f.open(QIODevice::WriteOnly | QIODevice::Text))
        return ("could not write playlist: " + file).toStdString();
    QTextStream ts(&f);
    ts.setEncoding(QStringConverter::Utf8);
    ts << "[playlist]\n";
    for (int i = 0; i < model.items().size(); ++i) {
        ts << "File" << (i + 1) << "=" << model.items()[i].path << "\n";
        ts << "Title" << (i + 1) << "=" << model.items()[i].title << "\n";
    }
    ts << "NumberOfEntries=" << model.items().size() << "\n";
    ts << "Version=2\n";
    return {};
}

bool PlaylistModel::looks_like_playlist(const QString& path) {
    QString lower = path.toLower();
    return lower.endsWith(".m3u") || lower.endsWith(".m3u8") || lower.endsWith(".pls");
}

}  // namespace mpcasu
