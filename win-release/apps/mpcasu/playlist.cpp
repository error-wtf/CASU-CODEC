// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "playlist.hpp"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QRegularExpression>
#include <QSet>
#include <QTextStream>
#include <QUrl>
#include <QXmlStreamReader>

#include "casu/json.hpp"

namespace mpcasu {

// Resolve one playlist entry against the playlist's base directory,
// mirroring casu/playlist.py _entry: remote URLs stay verbatim, file:// and
// relative paths are resolved against base. Empty input yields an empty
// QString (skip). Uses a side-channel to detect "skip".
namespace {
QString resolve_entry(QString text, const QDir& base) {
    text = text.trimmed();
    if (text.isEmpty()) return QString();
    if (text.contains("://")) return text;
    if (text.startsWith("file://")) {
        text = QUrl(text).toLocalFile();
    }
    QFileInfo cand(text);
    if (cand.isRelative()) {
        text = QFileInfo(base.filePath(text)).absoluteFilePath();
    }
    return text;
}
}  // namespace

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

void PlaylistModel::reorder(const QStringList& paths) {
    QVector<PlaylistItem> reordered;
    for (const QString& path : paths) {
        const int idx = index_of(path);
        if (idx >= 0) reordered.append(items_[idx]);
    }
    for (const PlaylistItem& item : items_) {
        if (!paths.contains(item.path)) reordered.append(item);
    }
    items_ = std::move(reordered);
    current_ = qBound(-1, current_, static_cast<int>(items_.size()) - 1);
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
        QString target = resolve_entry(line, base);
        if (!target.isEmpty()) out->add(target, pending_title);
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
            QString target = resolve_entry(m.captured(2), base);
            if (!target.isEmpty()) entries.append({m.captured(1).toInt(), target});
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
    if (lower.endsWith(".xspf")) return load_xspf(file, out);
    if (lower.endsWith(".wpl")) return load_wpl(file, out);
    if (lower.endsWith(".jspf")) return load_jspf(file, out);
    if (lower.endsWith(".asx") || lower.endsWith(".wmx") ||
        lower.endsWith(".wvx") || lower.endsWith(".axs")) return load_asx(file, out);
    if (lower.endsWith(".rmp")) return load_rmp(file, out);
    if (lower.endsWith(".ram")) return load_ram(file, out);
    if (lower.endsWith(".json")) return load_mpcasu_json(file, out);
    return load_m3u(file, out);
}

// XSPF (http://xspf.org/ns/0/) — casu/playlist.py _parse_xspf_entries.
std::string PlaylistModel::load_xspf(const QString& file, PlaylistModel* out) {
    QFile f(file);
    if (!f.open(QIODevice::ReadOnly))
        return ("could not open playlist: " + file).toStdString();
    const QDir base = QFileInfo(file).absoluteDir();
    QXmlStreamReader xml(&f);
    out->clear();
    QString title;
    while (!xml.atEnd()) {
        xml.readNext();
        if (xml.isStartElement()) {
            const auto name = xml.name();
            if (name == QLatin1String("title")) {
                title = xml.readElementText().trimmed().left(300);
            } else if (name == QLatin1String("location")) {
                const QString target = resolve_entry(xml.readElementText(), base);
                if (!target.isEmpty()) out->add(target, title);
            }
        } else if (xml.isEndElement() && xml.name() == QLatin1String("track")) {
            title.clear();
        }
    }
    if (xml.hasError() && xml.error() != QXmlStreamReader::PrematureEndOfDocumentError)
        return ("invalid XSPF playlist: " + file).toStdString();
    return {};
}

// WPL (Windows Media Player) — casu/playlist.py _parse_wpl_entries.
std::string PlaylistModel::load_wpl(const QString& file, PlaylistModel* out) {
    QFile f(file);
    if (!f.open(QIODevice::ReadOnly))
        return ("could not open playlist: " + file).toStdString();
    const QDir base = QFileInfo(file).absoluteDir();
    QXmlStreamReader xml(&f);
    out->clear();
    while (!xml.atEnd()) {
        xml.readNext();
        if (xml.isStartElement() && xml.name() == "media") {
            const QString src = xml.attributes().value("src").toString();
            QString t = xml.attributes().value("title").toString().trimmed().left(300);
            const QString target = resolve_entry(src, base);
            if (!target.isEmpty()) out->add(target, t);
        }
    }
    if (xml.hasError() && xml.error() != QXmlStreamReader::PrematureEndOfDocumentError)
        return ("invalid WPL playlist: " + file).toStdString();
    return {};
}

// JSPF (JSON XSPF) — casu/playlist.py _parse_jspf_entries.
std::string PlaylistModel::load_jspf(const QString& file, PlaylistModel* out) {
    QFile f(file);
    if (!f.open(QIODevice::ReadOnly))
        return ("could not open playlist: " + file).toStdString();
    const QByteArray raw = f.readAll();
    const QDir base = QFileInfo(file).absoluteDir();
    out->clear();
    casu::JsonValue doc;
    try {
        doc = casu::parse_json(raw.constData(), static_cast<std::size_t>(raw.size()));
    } catch (const casu::JsonError& e) {
        return ("invalid JSPF playlist: " + file).toStdString();
    }
    const casu::JsonValue* playlist = doc.is_object() ? doc.find("playlist") : nullptr;
    const casu::JsonValue* tracks = nullptr;
    if (playlist && playlist->is_object()) tracks = playlist->find("track");
    if (!tracks) tracks = doc.is_object() ? doc.find("track") : nullptr;
    if (tracks && tracks->is_array()) {
        for (const casu::JsonValue& track : tracks->as_array().items) {
            if (!track.is_object()) continue;
            const casu::JsonValue* tv = track.find("title");
            QString title = tv && tv->is_string()
                ? QString::fromStdString(tv->as_string()).trimmed().left(300) : QString();
            const casu::JsonValue* loc = track.find("location");
            if (loc && loc->is_array()) {
                for (const casu::JsonValue& item : loc->as_array().items) {
                    if (!item.is_string()) continue;
                    const QString target = resolve_entry(QString::fromStdString(item.as_string()), base);
                    if (!target.isEmpty()) out->add(target, title);
                }
            } else if (loc && loc->is_string()) {
                const QString target = resolve_entry(QString::fromStdString(loc->as_string()), base);
                if (!target.isEmpty()) out->add(target, title);
            }
        }
    }
    return {};
}

// ASX/WMX/WVX — casu/playlist.py _parse_asx_entries.
std::string PlaylistModel::load_asx(const QString& file, PlaylistModel* out) {
    QFile f(file);
    if (!f.open(QIODevice::ReadOnly))
        return ("could not open playlist: " + file).toStdString();
    const QDir base = QFileInfo(file).absoluteDir();
    QXmlStreamReader xml(&f);
    out->clear();
    QSet<QString> seen;

    struct AsxSource { QString title; QString target; };
    QVector<AsxSource> collected;

    // Walk <entry> nodes. For each, capture its <title> then all descendant
    // <ref href> and <param name=url value> as sources.
    while (!xml.atEnd()) {
        xml.readNext();
        if (xml.isStartElement()) {
            const QString name = xml.name().toString().toLower();
            if (name != "entry") continue;
            QString entryTitle;
            QVector<QString> sources;
            while (!xml.atEnd()) {
                xml.readNext();
                if (xml.isEndElement() && xml.name().toString().toLower() == "entry") break;
                if (!xml.isStartElement()) continue;
                const QString cname = xml.name().toString().toLower();
                if (cname == "title") {
                    entryTitle = xml.readElementText().trimmed().left(300);
                } else if (cname == "ref") {
                    const QString href = xml.attributes().value("href").toString();
                    if (!href.isEmpty()) sources.append(href);
                } else if (cname == "param") {
                    const QString pname = xml.attributes().value("name").toString().toLower();
                    const QString pval = xml.attributes().value("value").toString();
                    if (pname == "url" && !pval.isEmpty()) sources.append(pval);
                }
            }
            for (const QString& s : sources) {
                const QString target = resolve_entry(s, base);
                if (!target.isEmpty() && !seen.contains(target)) {
                    seen.insert(target);
                    collected.append({entryTitle, target});
                }
            }
        }
    }

    // Fall back to root-level <ref href> only if no entry produced anything.
    if (collected.isEmpty()) {
        QXmlStreamReader xml2(&f);
        while (!xml2.atEnd()) {
            xml2.readNext();
            if (xml2.isStartElement() && xml2.name().toString().toLower() == "ref") {
                const QString href = xml2.attributes().value("href").toString();
                const QString target = resolve_entry(href, base);
                if (!target.isEmpty() && !seen.contains(target)) {
                    seen.insert(target);
                    collected.append({QString(), target});
                }
            }
        }
    }

    for (const AsxSource& s : collected) out->add(s.target, s.title);
    if (xml.hasError() && xml.error() != QXmlStreamReader::PrematureEndOfDocumentError)
        return ("invalid ASX playlist: " + file).toStdString();
    return {};
}

// RMP (RealMedia metafile, XML) — casu/playlist.py _parse_rmp_entries; on
// parse failure falls back to RAM (plain text).
std::string PlaylistModel::load_rmp(const QString& file, PlaylistModel* out) {
    QFile f(file);
    if (!f.open(QIODevice::ReadOnly))
        return ("could not open playlist: " + file).toStdString();
    const QByteArray raw = f.readAll();
    const QDir base = QFileInfo(file).absoluteDir();
    out->clear();
    QXmlStreamReader xml(raw);
    while (!xml.atEnd()) {
        xml.readNext();
        if (xml.isStartElement()) {
            const QString name = xml.name().toString().toLower();
            const bool isRef = name.endsWith("ref") || name == "audio" ||
                               name == "video" || name == "media" || name == "entry";
            if (isRef) {
                QString src = xml.attributes().value("src").toString();
                if (src.isEmpty()) src = xml.attributes().value("href").toString();
                const QString target = resolve_entry(src, base);
                if (!target.isEmpty()) out->add(target, QString());
            }
        }
    }
    if (xml.hasError() && xml.error() != QXmlStreamReader::PrematureEndOfDocumentError)
        return load_ram(file, out);  // not XML → treat as RAM text
    return {};
}

// RAM (RealAudio metafile, plain text) — casu/playlist.py _parse_ram_entries.
std::string PlaylistModel::load_ram(const QString& file, PlaylistModel* out) {
    QFile f(file);
    if (!f.open(QIODevice::ReadOnly))
        return ("could not open playlist: " + file).toStdString();
    QTextStream ts(&f);
    ts.setEncoding(QStringConverter::Utf8);
    const QDir base = QFileInfo(file).absoluteDir();
    out->clear();
    while (!ts.atEnd()) {
        QString line = ts.readLine().trimmed();
        if (line.isEmpty() || line.startsWith('#')) continue;
        const QString target = resolve_entry(line, base);
        if (!target.isEmpty()) out->add(target, QString());
    }
    return {};
}

// MPCASU JSON — casu/playlist.py PlaylistModel.from_payload
// ({ "version": 1, "items": [...] }).
std::string PlaylistModel::load_mpcasu_json(const QString& file, PlaylistModel* out) {
    QFile f(file);
    if (!f.open(QIODevice::ReadOnly))
        return ("could not open playlist: " + file).toStdString();
    const QByteArray raw = f.readAll();
    const QDir base = QFileInfo(file).absoluteDir();
    out->clear();
    casu::JsonValue doc;
    try {
        doc = casu::parse_json(raw.constData(), static_cast<std::size_t>(raw.size()));
    } catch (const casu::JsonError& e) {
        return ("invalid playlist document: " + file).toStdString();
    }
    if (!doc.is_object() || !doc.find("items") || !doc.find("items")->is_array())
        return ("unsupported playlist document: " + file).toStdString();
    const casu::JsonValue* version = doc.find("version");
    if (!version || !version->is_int() || version->as_int() != 1)
        return ("unsupported playlist document: " + file).toStdString();
    for (const casu::JsonValue& item : doc.find("items")->as_array().items) {
        if (!item.is_string()) continue;
        const QString target = resolve_entry(QString::fromStdString(item.as_string()), base);
        if (!target.isEmpty()) out->add(target, QString());
    }
    return {};
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
    return lower.endsWith(".m3u") || lower.endsWith(".m3u8") || lower.endsWith(".pls") ||
           lower.endsWith(".xspf") || lower.endsWith(".wpl") || lower.endsWith(".jspf") ||
           lower.endsWith(".asx") || lower.endsWith(".wmx") || lower.endsWith(".wvx") ||
           lower.endsWith(".rmp") || lower.endsWith(".ram") || lower.endsWith(".json");
}

}  // namespace mpcasu
