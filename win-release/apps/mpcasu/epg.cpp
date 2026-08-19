// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "epg.hpp"

#include <QDateTime>
#include <QTimeZone>

namespace mpcasu {

namespace {
QString unescape(const QString& s) {
    QString out;
    out.reserve(s.size());
    for (int i = 0; i < s.size(); ++i) {
        if (s[i] == '&' && i + 1 < s.size()) {
            if (s.mid(i, 6) == "&quot;") { out += '"'; i += 5; continue; }
            if (s.mid(i, 5) == "&apos;") { out += '\''; i += 4; continue; }
            if (s.mid(i, 4) == "&lt;") { out += '<'; i += 3; continue; }
            if (s.mid(i, 4) == "&gt;") { out += '>'; i += 3; continue; }
            if (s.mid(i, 5) == "&amp;") { out += '&'; i += 4; continue; }
        }
        out += s[i];
    }
    return out;
}

QString attr(const QString& tag, const QString& name) {
    const int pos = tag.indexOf(name + "=\"");
    if (pos < 0) return {};
    int start = pos + name.size() + 2;
    int end = tag.indexOf('"', start);
    if (end < 0) return {};
    return tag.mid(start, end - start);
}

QString element_text(const QString& tag) {
    const int gt = tag.indexOf('>');
    if (gt < 0) return {};
    QString rest = tag.mid(gt + 1);
    const int lt = rest.indexOf('<');
    if (lt >= 0) rest = rest.left(lt);
    return unescape(rest.trimmed());
}

qint64 xmltv_time(const QString& s) {
    // 20260818120000 +0000
    QDateTime dt = QDateTime::fromString(s.left(14), "yyyyMMddHHmmss");
    if (!dt.isValid()) return 0;
    dt.setTimeZone(QTimeZone::utc());
    return dt.toMSecsSinceEpoch();
}
}  // namespace

QString parse_xmltv(const QByteArray& data, EpgCatalog* out) {
    out->channels.clear();
    out->programs.clear();
    if (!data.contains("<tv")) return "not an XMLTV document";

    // Scan element by element (channel + programme only).
    const QByteArray content = data;
    int pos = 0;
    int depth = 0;
    while (pos < content.size()) {
        int open = content.indexOf('<', pos);
        if (open < 0) break;
        int close = content.indexOf('>', open);
        if (close < 0) break;
        QByteArray raw = content.mid(open, close - open + 1);
        pos = close + 1;
        QString tag = QString::fromUtf8(raw).trimmed();
        if (tag.isEmpty()) continue;
        if (tag.startsWith("<!--") || tag.startsWith("<?")) continue;
        if (tag.startsWith("</")) {
            --depth;
            continue;
        }
        bool self_closing = tag.endsWith("/>");
        if (!self_closing) ++depth;
        tag.remove("<?xml");
        QString name = tag.mid(1);
        int sp = name.indexOf(' ');
        if (sp > 0) name = name.left(sp);
        if (name == "channel" && !self_closing) {
            // Gather until </channel>.
            int end = content.indexOf("</channel>", pos);
            if (end < 0) end = content.size();
            QByteArray body = content.mid(pos, end - pos);
            pos = end + 10;
            EpgChannel ch;
            ch.id = attr(QString::fromUtf8(raw), "id");
            const int dn = body.indexOf("<display-name");
            if (dn >= 0) {
                int dn_end = body.indexOf('>', dn);
                int dn_close = body.indexOf("</display-name>", dn_end);
                if (dn_end >= 0 && dn_close > dn_end)
                    ch.name = unescape(QString::fromUtf8(body.mid(dn_end + 1, dn_close - dn_end - 1)).trimmed());
            }
            const int ic = body.indexOf("<icon");
            if (ic >= 0) {
                QByteArray icon_raw = body.mid(ic, body.indexOf('>', ic) - ic + 1);
                ch.url = attr(QString::fromUtf8(icon_raw), "src");
            }
            if (!ch.id.isEmpty()) out->channels.append(ch);
        } else if (name == "programme" && !self_closing) {
            int end = content.indexOf("</programme>", pos);
            if (end < 0) end = content.size();
            QByteArray body = content.mid(pos, end - pos);
            pos = end + 11;
            EpgProgram p;
            p.channel_id = attr(QString::fromUtf8(raw), "channel");
            p.start_ms = xmltv_time(attr(QString::fromUtf8(raw), "start"));
            p.stop_ms = xmltv_time(attr(QString::fromUtf8(raw), "stop"));
            const int ti = body.indexOf("<title");
            if (ti >= 0) p.title = element_text(QString::fromUtf8(body.mid(ti)));
            const int su = body.indexOf("<sub-title");
            if (su >= 0) p.subtitle = element_text(QString::fromUtf8(body.mid(su)));
            const int de = body.indexOf("<desc");
            if (de >= 0) p.description = element_text(QString::fromUtf8(body.mid(de)));
            if (!p.channel_id.isEmpty() && p.start_ms > 0)
                out->programs.append(p);
        }
    }
    if (out->channels.isEmpty() && out->programs.isEmpty())
        return "no channels or programs found in XMLTV data";
    return {};
}

QVector<EpgProgram> now_and_next(const EpgCatalog& cat, const QString& channel_id,
                                 qint64 now_ms) {
    QVector<EpgProgram> result;
    for (const EpgProgram& p : cat.programs) {
        if (p.channel_id != channel_id) continue;
        if (p.start_ms <= now_ms && (p.stop_ms <= 0 || p.stop_ms > now_ms)) {
            result.prepend(p);
        } else if (p.start_ms > now_ms && result.size() < 2) {
            result.append(p);
        }
    }
    return result;
}

}  // namespace mpcasu
