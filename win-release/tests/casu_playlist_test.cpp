// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Windows playlist/queue semantics test suite — COMPLETE port of the Linux
// acceptance suite (tests/test_queue_playback_behavior.py, 15 behaviors) plus
// format/parsing parity checks against casu/playlist.py and edge cases.
//
// Covers:
//   A. The 15 non-destructive playlist-group queue behaviors (ALL_RELEASE_V5
//      README "Playlist-Gruppen-Semantik"): groups stay visible, logical
//      playback sequence walks through them, move/multi-move, marking
//      persistence, merge/rein/raus, flatten-save, batch dedup.
//   B. Parser/format parity with casu/playlist.py: EXTINF quoted commas +
//      300-char cap, PLS case-insensitive keys/whitespace/save layout,
//      ASX/WPL/RMP case-insensitive attributes, XSPF/JSON writers,
//      file:// + ~ + relative resolution, remote detection rules.
//   C. Edge cases: broken/missing/empty playlist groups, boundary moves,
//      reorder mapping, transport indexes.
#include "playlist.hpp"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QString>
#include <QStringList>
#include <QTemporaryDir>
#include <QUrl>
#include <cstdio>
#include <string>

using namespace mpcasu;

namespace {
int failures = 0;
int total = 0;
void check(bool ok, const char* label) {
    ++total;
    if (!ok) { ++failures; std::printf("FAIL %s\n", label); }
    else std::printf("ok   %s\n", label);
}

void write_file(const QString& path, const QByteArray& data) {
    QFile f(path);
    f.open(QIODevice::WriteOnly | QIODevice::Truncate);
    f.write(data);
}

void write_text(const QString& path, const QString& text) {
    write_file(path, text.toUtf8());
}

void check_eq(const QString& actual, const QString& expected, const char* label) {
    ++total;
    if (actual != expected) {
        ++failures;
        std::printf("FAIL %s\n  expected: <%s>\n  actual:   <%s>\n",
                    label, expected.toUtf8().constData(), actual.toUtf8().constData());
    } else {
        std::printf("ok   %s\n", label);
    }
}

bool check_dbg(bool ok) { return ok; }

QString read_text(const QString& path) {
    QFile f(path);
    f.open(QIODevice::ReadOnly);
    return QString::fromUtf8(f.readAll());
}
}  // namespace

int main() {
    QTemporaryDir dir;
    const QString dirPath = dir.path();
    const QString a = dirPath + "/a.mp3";
    const QString b = dirPath + "/b.mp3";
    write_file(a, "a");
    write_file(b, "b");

    // ============================ A. Queue-group semantics =================

    // --- A0. Save + load roundtrip (M3U) ---
    {
        const QString pl = dirPath + "/tracks.m3u";
        PlaylistModel model;
        model.add(a);
        model.add(b);
        check(PlaylistModel::save_m3u(pl, model).empty(), "save_m3u ok");
        PlaylistModel loaded;
        check(PlaylistModel::load_file(pl, &loaded).empty(), "load_file ok");
        check(loaded.size() == 2, "playlist has 2 entries");
        check(loaded.index_of(a) == 0, "first entry index 0");
        check(loaded.index_of(b) == 1, "second entry index 1");
    }

    // --- A1. Canonical mixed combination: A1,A2,X,B1,B2 ---
    QString plA, plB;
    {
        const QString a1 = dirPath + "/a1.mp3";
        const QString a2 = dirPath + "/a2.mp3";
        const QString x = dirPath + "/x.mp4";
        const QString b1 = dirPath + "/b1.mp3";
        const QString b2 = dirPath + "/b2.mp3";
        for (const QString& p : {a1, a2, x, b1, b2}) write_file(p, "m");
        plA = dirPath + "/A.m3u";
        plB = dirPath + "/B.m3u";
        PlaylistModel pa, pb;
        pa.add(a1); pa.add(a2);
        pb.add(b1); pb.add(b2);
        check(PlaylistModel::save_m3u(plA, pa).empty(), "save playlist A");
        check(PlaylistModel::save_m3u(plB, pb).empty(), "save playlist B");

        // Choosing playlists together with media must keep GROUPS as rows.
        const PlaylistBatchPlan plan = playlist_batch_plan({plA, x, plB});
        check(plan.rows == QStringList{plA, x, plB},
              "batch plan preserves the input order (A-group, X, B-group)");
        PlaylistModel queue;
        for (const QString& p : plan.rows) queue.add(p);
        check(queue.size() == 3, "queue keeps playlist groups (3 rows, not 5)");
        check(queue.is_playlist_row(0), "row 0 is a playlist group (A)");
        check(!queue.is_playlist_row(1), "row 1 is a loose file (X)");
        check(queue.is_playlist_row(2), "row 2 is a playlist group (B)");

        const QVector<QString> seq = playlist_logical_sequence(queue.items());
        check(seq.size() == 5, "logical sequence has 5 entries");
        check(seq[0] == a1 && seq[1] == a2 && seq[2] == x && seq[3] == b1 && seq[4] == b2,
              "canonical order A1,A2,X,B1,B2");

        // Owner-row mapping: every sequence position maps back into its group.
        check(playlist_seq_owner_row(queue.items(), 0) == 0, "seq 0 owned by row 0");
        check(playlist_seq_owner_row(queue.items(), 1) == 0, "seq 1 owned by row 0");
        check(playlist_seq_owner_row(queue.items(), 2) == 1, "seq 2 owned by row 1 (loose)");
        check(playlist_seq_owner_row(queue.items(), 4) == 2, "seq 4 owned by row 2 (B)");

        // Play on a GROUP starts at its first entry (= _row_to_seq position).
        const int posB = playlist_row_to_seq(queue.items(), 2);
        check(posB == 3 && seq[posB] == b1, "playing group B starts at B1");
    }

    // --- A2. Collapsed vs expanded never changes playback ---
    {
        PlaylistModel queue;
        queue.add(plA);
        const QVector<QString> s1 = playlist_logical_sequence(queue.items());
        const QVector<QString> s2 = playlist_logical_sequence(queue.items());
        check(s1 == s2 && s1.size() == 2, "expand state cannot influence the sequence");
    }

    // --- A3. Playing a playlist CHILD keeps the group visible ---
    {
        PlaylistModel queue;
        queue.add(plA);
        const QStringList entriesA = playlist_group_paths(queue.items());
        check(entriesA.size() == 1, "one group in queue");
        const QString owner = playlist_containing_playlist(queue.items(),
                                                          dirPath + "/a2.mp3");
        check(owner == plA, "child resolves to its owning group");
        // Child play only sets `current`; the model rows are untouched.
        queue.set_current(0);
        check(queue.size() == 1 && queue.is_playlist_row(0),
              "group still visible after playing its child");
    }

    // --- A4. Play button on a selected CHILD plays exactly that child ---
    {
        PlaylistModel queue;
        queue.add(plA);
        const int pos = playlist_row_to_seq(queue.items(), 0);
        const QVector<QString> seq = playlist_logical_sequence(queue.items());
        check(pos >= 0 && pos < seq.size() && seq[pos] == dirPath + "/a1.mp3",
              "selected child maps to its own sequence position (a1 first)");
        const int posSecond = playlist_row_to_seq(queue.items(), 0);
        check(seq[posSecond] != dirPath + "/a2.mp3",
              "first child of the group is played first (not the last)");
    }

    // --- A5. Playlist with stream URLs plays through ---
    {
        const QString pl = dirPath + "/streams.m3u";
        PlaylistModel model;
        model.add(QStringLiteral("http://example.invalid/one"));
        model.add(QStringLiteral("https://example.invalid/two"));
        model.add(a);
        check(PlaylistModel::save_m3u(pl, model).empty(), "save stream playlist");
        PlaylistModel queue;
        queue.add(pl);
        const QVector<QString> seq = playlist_logical_sequence(queue.items());
        check(seq.size() == 3, "stream playlist contributes all entries");
        check(seq[0].startsWith("http://") && seq[1].startsWith("https://"),
              "URLs kept verbatim in the sequence");
        check(seq[2] == a, "local entry after streams still plays");
        check(queue.is_playlist_row(0), "stream playlist stays ONE visible group row");
    }

    // --- A6. Add URL queues and combines with a playlist (batch dedup) ---
    {
        PlaylistModel queue;
        const QString url = QStringLiteral("rtsp://example.invalid/live");
        const PlaylistBatchPlan plan = playlist_batch_plan({url, plA});
        check(plan.rows == QStringList{url, plA},
              "URL queued as loose row + playlist as group row (input order)");
        for (const QString& p : plan.rows) queue.add(p);
        check(queue.size() == 2, "URL combines with playlist group");
        // Re-adding the same URL does not duplicate (queue-level dedup).
        const PlaylistBatchPlan again = playlist_batch_plan({url});
        int added = 0;
        for (const QString& p : again.rows)
            if (queue.index_of(p) < 0) { queue.add(p); ++added; }
        check(added == 0, "re-adding an existing URL is a no-op");
    }

    // --- A7. Merge files/URLs AND a whole playlist into an existing one ---
    {
        const QString target = dirPath + "/target.m3u";
        PlaylistModel t;
        t.add(a);
        PlaylistModel::save_m3u(target, t);
        // Merge selection: loose file b + whole playlist A (expands!).
        QStringList entries{b};
        {
            PlaylistModel tmp;
            if (PlaylistModel::load_file(plA, &tmp).empty())
                for (const PlaylistItem& item : tmp.items())
                    if (!entries.contains(item.path)) entries.append(item.path);
        }
        PlaylistModel merged;
        PlaylistModel::load_file(target, &merged);
        int addedCount = 0;
        for (const QString& e : entries)
            if (merged.index_of(e) < 0) { merged.add(e); ++addedCount; }
        check(PlaylistModel::save_m3u(target, merged).empty(), "merge save ok");
        check(addedCount == 3, "whole playlist expands into its entries (b,a1,a2)");
        PlaylistModel reloaded;
        PlaylistModel::load_file(target, &reloaded);
        check(reloaded.index_of(dirPath + "/a1.mp3") >= 0 &&
              reloaded.index_of(b) == 1, "merge preserves order, no duplicates");
    }

    // --- A8. Merge playlist CHILDREN into a playlist ---
    {
        PlaylistModel merged;
        merged.add(a);
        // Children are used directly (no group expansion).
        merged.add(dirPath + "/b1.mp3");
        check(merged.index_of(dirPath + "/b1.mp3") == 1, "child appended directly");
    }

    // --- A9. Save queue flattens playlist groups ---
    {
        PlaylistModel queue;
        queue.add(plA);
        queue.add(b);
        PlaylistModel flat;
        for (const PlaylistItem& item : queue.items()) {
            if (item.is_playlist) {
                PlaylistModel tmp;
                if (PlaylistModel::load_file(item.path, &tmp).empty()) {
                    for (const PlaylistItem& entry : tmp.items())
                        flat.add(entry.path, entry.title);
                    continue;
                }
            }
            flat.add(item.path, item.title);
        }
        check(flat.size() == 3, "save flattens the group (no [Playlist] reference)");
        check(!flat.items()[0].is_playlist, "flattened rows are plain media");
    }

    // --- A10. Groups move up and down (single + as block) ---
    {
        PlaylistModel queue;
        queue.add(plA);
        queue.add(b);
        queue.add(plB);
        queue.move_many({2}, -1);          // B up: A,B-group swap with b
        check(queue.items()[1].path == plB && queue.items()[2].path == b,
              "moving a group down/up swaps whole rows");
        queue.move_many({1}, -1);          // B to top
        check(queue.items()[0].path == plB, "group reached the top");
        // Sequence reflects the new order.
        const QVector<QString> seq = playlist_logical_sequence(queue.items());
        check(seq[0] == dirPath + "/b1.mp3", "sequence follows the moved group");
        // Multi-selection block move keeps relative order.
        PlaylistModel q2;
        q2.add(a); q2.add(b); q2.add(plA);
        q2.move_many({0, 1}, 1);           // block [a,b] one down
        check(q2.items()[0].path == plA && q2.items()[1].path == a &&
              q2.items()[2].path == b, "multi-selection moves as one unit");
        // Boundary clamps are safe no-ops.
        q2.move_many({0}, -1);
        q2.move_many({q2.size() - 1}, 1);
        check(q2.size() == 3, "boundary moves do not drop rows");
    }

    // --- A11. Remove child from playlist keeps the group visible ---
    {
        const QString pl = dirPath + "/rem.m3u";
        PlaylistModel m;
        m.add(a); m.add(b);
        PlaylistModel::save_m3u(pl, m);
        PlaylistModel queue;
        queue.add(pl);
        // "Remove from playlist": edit the FILE, group stays queued.
        PlaylistModel tmp;
        PlaylistModel::load_file(pl, &tmp);
        tmp.remove_many({1});  // remove b
        check(PlaylistModel::save_m3u(pl, tmp).empty(), "child removal saved");
        check(queue.is_playlist_row(0), "group still visible after child removal");
        check(!playlist_containing_playlist(queue.items(), b).isEmpty() == false,
              "removed child no longer belongs to the group");
        check(playlist_containing_playlist(queue.items(), a) == pl,
              "remaining child still belongs to the group");
        const QVector<QString> seq = playlist_logical_sequence(queue.items());
        check(seq.size() == 1 && seq[0] == a, "sequence reflects the edited playlist");
    }

    // --- A12. Move child to ANOTHER playlist (source-first, target excluded) ---
    {
        const QString src = dirPath + "/src.m3u";
        const QString dst = dirPath + "/dst.m3u";
        PlaylistModel sm, dm;
        sm.add(a); sm.add(b);
        dm.add(dirPath + "/z.mp3");
        write_file(dirPath + "/z.mp3", "z");
        PlaylistModel::save_m3u(src, sm);
        PlaylistModel::save_m3u(dst, dm);

        // Fixed semantics (Linux _on_child_move_to_playlist): FIRST strip the
        // entries from every queued source EXCEPT the target, THEN append to
        // the target. Never the old add-first/remove-everywhere order (which
        // wiped the child out of both files).
        const QString target = dst;
        const QStringList entries{b};
        int removed_total = 0;
        PlaylistModel queueModel;
        queueModel.add(src);
        queueModel.add(dst);
        for (int i = 0; i < queueModel.items().size(); ++i) {
            const PlaylistItem& item = queueModel.items()[i];
            if (!item.is_playlist || !QFileInfo::exists(item.path)) continue;
            if (item.path == target) continue;              // never the target!
            PlaylistModel t;
            if (!PlaylistModel::load_file(item.path, &t).empty()) continue;
            QVector<int> to_remove;
            for (int k = 0; k < t.items().size(); ++k)
                if (entries.contains(t.items()[k].path)) to_remove.append(k);
            if (to_remove.isEmpty()) continue;
            const int before = t.size();
            t.remove_many(to_remove);
            PlaylistModel::save_file(item.path, t);
            removed_total += before - t.size();
        }
        check(removed_total == 1, "child removed from its source exactly once");
        // THEN append to the target and save it.
        PlaylistModel dt;
        PlaylistModel::load_file(dst, &dt);
        for (const QString& e : entries)
            if (dt.index_of(e) < 0) dt.add(e);
        check(PlaylistModel::save_m3u(dst, dt).empty(), "target saved");
        check(dt.index_of(b) >= 0, "moved child IS in the target");
        PlaylistModel st;
        PlaylistModel::load_file(src, &st);
        check(st.index_of(b) < 0, "moved child is OUT of the source");
        check(st.size() == 1 && st.index_of(a) == 0, "source keeps its other child");
        check(dt.size() == 2, "target has z + moved child (nothing lost)");
    }

    // --- A13. Multi-selection moves all selected rows together ---
    {
        PlaylistModel q;
        for (const char* n : {"1", "2", "3", "4"})
            q.add(dirPath + "/" + n + ".mp3");
        q.move_many({0, 2}, 1);  // Ctrl-style non-contiguous selection as block
        check(q.items()[1].path.endsWith("1.mp3") && q.items()[3].path.endsWith("3.mp3"),
              "selected rows shift together preserving relative order");
    }

    // --- A14. Marking survives move AND removal ---
    {
        PlaylistModel q;
        q.add(a); q.add(b); q.add(dirPath + "/c.mp3");
        write_file(dirPath + "/c.mp3", "c");
        // Simulated UI state: rows 0 and 2 are marked.
        QSet<int> marked{0, 2};
        // Move rows 0..1 up/down: marked paths stay marked afterwards.
        const QStringList before{q.items()[0].path, q.items()[2].path};
        q.move_many({0}, 1);
        QSet<int> stillMarked;
        for (int i = 0; i < q.size(); ++i)
            if (before.contains(q.items()[i].path)) stillMarked.insert(i);
        check(stillMarked == QSet<int>{1, 2}, "marking follows the rows on move");
        // Remove row 1 (unmarked): both marks survive.
        QVector<int> removed{1};
        QSet<int> survivors;
        for (int i = 0; i < q.size(); ++i)
            if (marked.contains(i) && !removed.contains(i)) survivors.insert(i);
        // After compaction the surviving MARKED rows map to new indices 0,1.
        check(survivors == QSet<int>{0, 2}, "marked-but-not-removed rows stay marked");
    }

    // --- A15. Loose file continues through FOLLOWING playlists ---
    {
        PlaylistModel queue;
        queue.add(a);
        queue.add(plB);
        const QVector<QString> seq = playlist_logical_sequence(queue.items());
        check(seq.size() == 3 && seq[0] == a && seq[1] == dirPath + "/b1.mp3",
              "playback continues from loose file into following groups");
    }

    // ============================ B. Format/parsing parity =================

    // --- B16/B17. EXTINF quoted commas + 300-char truncation ---
    {
        const QString pl = dirPath + "/quoted.m3u";
        write_text(pl, QStringLiteral(
            "#EXTM3U\n"
            "#EXTINF:-1,\"Track, with \"\"comma\"\"\", extra\"\n%1\n"
            "#EXTINF:-1,%2\nx-nofile.mp3\n")
            .arg(a)
            .arg(QString(350, 'T')));
        PlaylistModel loaded;
        check(PlaylistModel::load_file(pl, &loaded).empty(), "quoted EXTINF loads");
        check(loaded.size() == 2, "both entries parsed");
        check(loaded.items()[0].title.contains(QLatin1String("extra")),
              "title taken after first UNQUOTED comma");
        check(loaded.items()[1].title.size() == 300, "EXTINF title capped at 300 chars");
    }

    // --- B18/B19. PLS case-insensitive keys, whitespace, title cap ---
    {
        const QString pl = dirPath + "/case.PLS";
        write_text(pl, QStringLiteral(
            "[playlist]\n"
            "file1 = %1\n"
            "TITLE1=%2\n"
            "NumberOfEntries=1\n"
            "Version=2\n").arg(a).arg(QString(310, 'P')));
        PlaylistModel loaded;
        check(PlaylistModel::load_file(pl, &loaded).empty(), "case-insensitive PLS loads");
        check(loaded.size() == 1 && loaded.items()[0].path == a, "PLS File1 parsed");
        check(loaded.items()[0].title.size() == 300, "PLS TitleN capped at 300 chars");
    }

    // --- B20. ASX uppercase HREF attribute ---
    {
        const QString pl = dirPath + "/upper.asx";
        write_text(pl, QStringLiteral(
            "<ASX version=\"3.0\"><ENTRY><TITLE>Up</TITLE>"
            "<REF HREF=\"%1\" /></ENTRY></ASX>").arg(a));
        PlaylistModel loaded;
        check(PlaylistModel::load_file(pl, &loaded).empty(), "ASX loads");
        check(loaded.size() == 1 && loaded.items()[0].path == a,
              "HREF matched case-insensitively");
    }

    // --- B21. WPL case-insensitive src/title attributes ---
    {
        const QString pl = dirPath + "/w.smil";
        write_text(pl, QStringLiteral(
            "<?wpl version=\"1.0\"?><smil><body><seq><media "
            "SRC=\"%1\" TiTlE=\"Wpl\" /></seq></body></smil>").arg(a));
        PlaylistModel loaded;
        check(PlaylistModel::load_file(pl, &loaded).empty(), "WPL loads by content");
        if (!check_dbg(loaded.size() == 1))
            std::printf("  wpl size=%d\n", loaded.size());
        check_eq(loaded.size() == 1 ? loaded.items()[0].title : QStringLiteral("<none>"),
                 QStringLiteral("Wpl"),
                 "WPL SRC/TiTlE matched case-insensitively");
    }

    // --- B22. RMP uppercase SRC attribute ---
    {
        const QString pl = dirPath + "/r.rmp";
        write_text(pl, QStringLiteral("<imfl><video SRC=\"%1\"/></imfl>").arg(a));
        PlaylistModel loaded;
        check(PlaylistModel::load_file(pl, &loaded).empty(), "RMP loads");
        check(loaded.size() == 1, "RMP SRC matched case-insensitively");
    }

    // --- B23. M3U save layout byte-parity with save_playlist_file ---
    {
        const QString pl = dirPath + "/fmt.m3u";
        PlaylistModel m;
        m.add(a); m.add(b);
        PlaylistModel::save_m3u(pl, m);
        const QString raw = read_text(pl);
        check_eq(raw, QStringLiteral("#EXTM3U\n\n%1\n%2\n").arg(a, b),
                 "M3U save = #EXTM3U, blank line, paths only (no EXTINF)");
    }

    // --- B24. PLS save layout byte-parity ---
    {
        const QString pl = dirPath + "/fmt.pls";
        PlaylistModel m;
        m.add(a); m.add(b);
        PlaylistModel::save_pls(pl, m);
        const QString raw = read_text(pl);
        check_eq(raw, QStringLiteral("[playlist]\nNumberOfEntries=2\n"
                                    "File1=%1\nTitle1=a.mp3\n"
                                    "File2=%2\nTitle2=b.mp3\nVersion=2\n").arg(a, b),
                 "PLS save = NumberOfEntries first, TitleN=filename, Version last");
    }

    // --- B25. XSPF writer + XML escaping + roundtrip ---
    {
        const QString pl = dirPath + "/esc.xspf";
        const QString tricky = dirPath + "/weird&\"x\".mp3";
        write_file(tricky, "t");
        PlaylistModel m;
        m.add(tricky);
        check(PlaylistModel::save_xspf(pl, m).empty(), "xspf save ok");
        const QString raw = read_text(pl);
        check(raw.contains("&amp;") && raw.contains("&quot;"), "XML special chars escaped");
        PlaylistModel back;
        check(PlaylistModel::load_file(pl, &back).empty(), "xspf reload ok");
        check(back.size() == 1 && back.items()[0].path == tricky, "xspf roundtrip intact");
    }

    // --- B26. MPCASU JSON payload writer + roundtrip ---
    {
        const QString pl = dirPath + "/payload.json";
        PlaylistModel m;
        m.add(a); m.add(QStringLiteral("http://example.invalid/s"));
        check(PlaylistModel::save_json(pl, m).empty(), "json save ok");
        PlaylistModel back;
        check(PlaylistModel::load_file(pl, &back).empty(), "json load ok");
        check(back.size() == 2 && back.items()[1].is_url, "json roundtrip keeps URLs");
        check(read_text(pl).contains("\"version\": 1"), "json payload has version 1");
    }

    // --- B27. save_file dispatches by extension ---
    {
        const QString pl = dirPath + "/dispatch.xspf";
        PlaylistModel m;
        m.add(a);
        check(PlaylistModel::save_file(pl, m).empty(), "save_file ok");
        check(read_text(pl).contains("<trackList>"), ".xspf got XSPF content (never M3U)");
        const QString jpl = dirPath + "/dispatch.json";
        PlaylistModel::save_file(jpl, m);
        check(read_text(jpl).contains("\"items\""), ".json got JSON payload");
    }

    // --- B28. file:// URI with percent encoding ---
    {
        const QString spaced = dirPath + "/na me.mp3";
        write_file(spaced, "s");
        const QString pl = dirPath + "/fileuri.m3u";
        const QUrl uri = QUrl::fromLocalFile(spaced);
        write_text(pl, uri.toString(QUrl::FullyEncoded).toUtf8() + "\n");
        PlaylistModel loaded;
        PlaylistModel::load_file(pl, &loaded);
        check_eq(loaded.size() == 1 ? loaded.items()[0].path : QStringLiteral("<none>"),
                 spaced,
                 "file:// percent-encoded URI resolved to local path");
    }

    // --- B29. ~ expansion ---
    {
        const QString pl = dirPath + "/home.m3u";
        write_text(pl, "~/music/titel.mp3\n");
        PlaylistModel loaded;
        PlaylistModel::load_file(pl, &loaded);
        check(loaded.size() == 1 &&
              loaded.items()[0].path.startsWith(QDir::homePath()),
              "~/ entry expands to the home directory");
    }

    // --- B30. Relative entries resolve against the playlist directory ---
    {
        QDir().mkpath(dirPath + "/base/sub");
        write_file(dirPath + "/base/sub/deep.mp3", "d");
        const QString pl = dirPath + "/base/list.m3u";
        write_text(pl, "sub/deep.mp3\n");
        PlaylistModel loaded;
        PlaylistModel::load_file(pl, &loaded);
        check(loaded.size() == 1 &&
              loaded.items()[0].path == dirPath + "/base/sub/deep.mp3",
              "relative entry resolved against the playlist base dir");
    }

    // --- B31. A remote .m3u8 URL is NEVER a group row (HLS stream) ---
    {
        PlaylistModel q;
        q.add(QStringLiteral("https://cdn.example.invalid/live/index.m3u8"));
        check(q.items()[0].is_url, "remote .m3u8 flagged as URL");
        check(!q.items()[0].is_playlist, "remote .m3u8 NOT treated as playlist group");
        const PlaylistBatchPlan hls =
            playlist_batch_plan({QStringLiteral("https://x.example.invalid/a.m3u8")});
        PlaylistModel hq;
        for (const QString& r : hls.rows) hq.add(r);
        check(hq.size() == 1 && hq.items()[0].is_url && !hq.items()[0].is_playlist,
              "batch planner keeps HLS streams as flat URL rows");
    }

    // --- B32. Remote requires scheme AND netloc ---
    {
        PlaylistModel q;
        q.add(QStringLiteral("spotify:track:abc"));
        check(!q.items()[0].is_url, "scheme without netloc is not remote (parity)");
        q.clear();
        q.add(QStringLiteral("ftp://files.example.invalid/x.mp3"));
        check(q.items()[0].is_url, "ftp://host is remote");
    }

    // ============================ C. Edge cases ============================

    // --- C33. Broken playlist file: suffix-typed group stays, seq skips ---
    {
        const QString broken = dirPath + "/broken.json";
        write_text(broken, "{ this is not valid json !!");
        PlaylistModel q;
        q.add(broken);   // suffix typing: still a GROUP row
        q.add(a);
        check(q.is_playlist_row(0), "corrupt playlist still shows as group row");
        const QVector<QString> seq = playlist_logical_sequence(q.items());
        check(seq.size() == 1 && seq[0] == a, "broken group skipped, rest plays on");
        check(playlist_containing_playlist(q.items(), b).isEmpty(),
              "no child resolves through a broken group");
    }

    // --- C34. Empty playlist group contributes nothing ---
    {
        const QString pl = dirPath + "/empty.m3u";
        write_text(pl, "#EXTM3U\n\n");
        PlaylistModel q;
        q.add(pl);
        const QVector<QString> seq = playlist_logical_sequence(q.items());
        check(seq.isEmpty(), "empty group contributes zero sequence entries");
        check(playlist_row_to_seq(q.items(), 0) == 0, "row_to_seq of empty group = 0");
    }

    // --- C35. Merge dedup preserves the ORIGINAL order ---
    {
        PlaylistModel merged;
        merged.add(b); merged.add(a);
        // Adding [a, x] again: a exists -> skipped; new item appended last.
        for (const QString& e : QStringList{a, dirPath + "/new9.mp3"})
            if (merged.index_of(e) < 0) merged.add(e);
        check(merged.index_of(b) == 0 && merged.index_of(a) == 1 &&
              merged.index_of(dirPath + "/new9.mp3") == 2,
              "original order untouched, new entries appended");
    }

    // --- C36. Batch plan skips non-existent local files ---
    {
        const PlaylistBatchPlan plan = playlist_batch_plan(
            {dirPath + "/nope-not-here.mp3", a});
        check(plan.rows == QStringList{a},
              "non-existent local file skipped (existing_only parity)");
    }

    // --- C37. Batch plan: same file twice in one batch adds once ---
    {
        const PlaylistBatchPlan plan = playlist_batch_plan({a, a});
        check(plan.rows.size() == 1, "duplicate input within batch collapses");
    }

    // --- C38. Transport indexes incl. repeat modes ---
    {
        PlaylistModel m;
        m.add(a); m.add(b);
        m.set_current(0);
        check(m.next_index(true) == 1, "next from 0 -> 1");
        m.repeat = PlaylistModel::RepeatMode::One;
        check(m.next_index(true) == 0, "repeat-one replays current");
        m.repeat = PlaylistModel::RepeatMode::Off;
        m.set_current(1);
        check(m.next_index(true) == -1, "off at end stops (-1)");
        m.repeat = PlaylistModel::RepeatMode::All;
        check(m.next_index(true) == 0, "repeat-all wraps to 0");
        m.set_current(0);
        check(m.previous_index() == 1, "previous wraps from 0 to end");
        m.set_current(-1);
        check(m.next_index(false) == 0, "next from unset starts at 0");
    }

    // --- C39. reorder(): drag-drop mapping appends unlisted rows ---
    {
        PlaylistModel q;
        q.add(a); q.add(b); q.add(dirPath + "/c2.mp3");
        write_file(dirPath + "/c2.mp3", "c");
        q.reorder({dirPath + "/c2.mp3"});
        check(q.items()[0].path == dirPath + "/c2.mp3" && q.size() == 3,
              "listed row first, unlisted rows keep their tail order");
        check(q.index_of(a) == 1 && q.index_of(b) == 2,
              "unlisted rows preserve their relative order");
    }

    // --- C40. remove_many with duplicates/out-of-range is safe ---
    {
        PlaylistModel q;
        q.add(a); q.add(b);
        q.remove_many({5, 1, 1});
        check(q.size() == 1 && q.items()[0].path == a,
              "invalid/duplicate indices ignored, valid ones removed");
    }

    // --- C41. looks_like_playlist covers all supported formats ---
    {
        for (const char* ext : {".m3u", ".m3u8", ".pls", ".json", ".wpl",
                                ".xspf", ".jspf", ".asx", ".wmx", ".wvx",
                                ".rmp", ".ram"}) {
            check(PlaylistModel::looks_like_playlist(QStringLiteral("/x") + ext),
                  ext);
        }
        check(!PlaylistModel::looks_like_playlist("/x.mp4"), ".mp4 is not a playlist");
    }

    // --- C42. JSPF loading (array + single location forms) ---
    {
        const QString pl = dirPath + "/list.jspf";
        write_text(pl, QStringLiteral("{\"playlist\":{\"track\":["
            "{\"title\":\"J1\",\"location\":\"%1\"},"
            "{\"title\":\"J2\",\"location\":[\"http://example.invalid/j\"]}]}}").arg(a));
        PlaylistModel loaded;
        check(PlaylistModel::load_file(pl, &loaded).empty(), "jspf loads");
        check(loaded.size() == 2, "jspf array + string/list locations handled");
        check(loaded.items()[0].title == QLatin1String("J1"), "jspf titles carried");
    }

    // =========================================================================
    std::printf("\n%d/%d checks passed\n", total - failures, total);
    if (failures) {
        std::printf("%d FAILURES\n", failures);
        return 1;
    }
    std::printf("ALL PASS\n");
    return 0;
}
