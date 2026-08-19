// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// EPG support (WP-MPCASU-033, pragmatic XMLTV parser). Loads an XMLTV file,
// builds a channel list + program table with start/stop/title/subtitle; the
// UI shows now/next per channel and can play a channel stream URL.
#pragma once
#include <QString>
#include <QVector>

namespace mpcasu {

struct EpgProgram {
    QString channel_id;
    qint64 start_ms = 0;
    qint64 stop_ms = 0;
    QString title;
    QString subtitle;
    QString description;
};

struct EpgChannel {
    QString id;
    QString name;
    QString url;  // optional stream URL from <icon> or custom attr
};

struct EpgCatalog {
    QVector<EpgChannel> channels;
    QVector<EpgProgram> programs;
};

// Parse XMLTV. Returns error string (empty = ok). Uses a lightweight,
// dependency-free XML scan of <channel>/<programme> elements.
QString parse_xmltv(const QByteArray& data, EpgCatalog* out);

// Programs of a channel overlapping `now_ms`.
QVector<EpgProgram> now_and_next(const EpgCatalog& cat, const QString& channel_id,
                                 qint64 now_ms);

}  // namespace mpcasu
