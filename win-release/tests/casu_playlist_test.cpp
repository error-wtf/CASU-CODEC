// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Windows PlaylistModel unit tests (Playlist-Play + Merge-Feature).
// Verifies the core merge/play-queue logic used by the "Save selection to
// playlist…" feature: load existing playlist, append selected entries
// (deduplicated), save back; and that a playlist resolves to ordered queue
// items that play through (next_index advances).
#include "playlist.hpp"

#include <QDir>
#include <QFile>
#include <QString>
#include <QStringList>
#include <QTemporaryDir>
#include <cstdio>
#include <string>

using namespace mpcasu;

namespace {
int failures = 0;
void check(bool ok, const char* label) {
    if (!ok) { ++failures; std::printf("FAIL %s\n", label); }
    else std::printf("ok   %s\n", label);
}
}  // namespace

int main() {
    QTemporaryDir dir;
    const QString dirPath = dir.path();
    const QString a = dirPath + "/a.mp3";
    const QString b = dirPath + "/b.mp3";
    { QFile f(a); f.open(QIODevice::WriteOnly); f.write("a"); }
    { QFile f(b); f.open(QIODevice::WriteOnly); f.write("b"); }

    // --- Save + load roundtrip (M3U) ---
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

    // --- Merge into existing playlist (deduplicated) ---
    {
        const QString pl = dirPath + "/merge.m3u";
        PlaylistModel existing;
        existing.add(a);
        PlaylistModel::save_m3u(pl, existing);

        // Merge: load existing, append b (new) + a (dup, skipped).
        PlaylistModel merged;
        PlaylistModel::load_file(pl, &merged);
        if (merged.index_of(b) < 0) merged.add(b);
        if (merged.index_of(a) < 0) merged.add(a);
        check(merged.size() == 2, "merge deduplicates (a not duplicated)");
        check(merged.index_of(a) == 0 && merged.index_of(b) == 1, "merge preserves order");
        check(PlaylistModel::save_m3u(pl, merged).empty(), "merge save ok");
        PlaylistModel restored;
        PlaylistModel::load_file(pl, &restored);
        check(restored.size() == 2, "merged playlist persisted");
    }

    // --- Play through: next_index advances through the playlist ---
    {
        PlaylistModel model;
        model.add(a);
        model.add(b);
        model.set_current(0);
        int next = model.next_index(true);
        check(next == 1, "next_index from 0 -> 1");
        model.set_current(1);
        next = model.next_index(true);
        check(next == -1 || next == 0, "next_index at end (off -> -1 / all -> 0)");
    }

    // --- Playlist file detection ---
    {
        check(PlaylistModel::looks_like_playlist(dirPath + "/x.m3u"), "detect .m3u");
        check(PlaylistModel::looks_like_playlist(dirPath + "/x.pls"), "detect .pls");
        check(PlaylistModel::looks_like_playlist(dirPath + "/x.mp4") == false, "not a playlist for .mp4");
    }

    // --- Mixed combination: playlist group + file + playlist group in queue ---
    // Playlist files are added as ONE visible GROUP row (never flattened);
    // the logical playback sequence is A1, A2, X, B1, B2.
    {
        const QString a1 = dirPath + "/a1.mp3";
        const QString a2 = dirPath + "/a2.mp3";
        const QString x = dirPath + "/x.mp4";
        const QString b1 = dirPath + "/b1.mp3";
        const QString b2 = dirPath + "/b2.mp3";
        for (const QString& p : {a1, a2, x, b1, b2}) {
            QFile f(p); f.open(QIODevice::WriteOnly); f.write("m");
        }
        const QString plA = dirPath + "/A.m3u";
        const QString plB = dirPath + "/B.m3u";
        PlaylistModel pa, pb;
        pa.add(a1); pa.add(a2);
        pb.add(b1); pb.add(b2);
        check(PlaylistModel::save_m3u(plA, pa).empty(), "save playlist A");
        check(PlaylistModel::save_m3u(plB, pb).empty(), "save playlist B");

        // Simulate MainWindow::add_files: playlist => group row, media/URLs
        // appended flat, deduplicated by path. A media file that is a child
        // of a playlist chosen in the SAME batch is covered (not double-added).
        PlaylistModel queue;
        auto add_batch = [&](const QStringList& batch) {
            QStringList covered;
            for (const QString& p : batch) {
                if (PlaylistModel::looks_like_playlist(p) && QFileInfo::exists(p)) {
                    PlaylistModel tmp;
                    if (PlaylistModel::load_file(p, &tmp).empty())
                        for (const PlaylistItem& item : tmp.items()) covered.append(item.path);
                }
            }
            for (const QString& p : batch) {
                if (PlaylistModel::looks_like_playlist(p) && QFileInfo::exists(p)) {
                    if (queue.index_of(p) < 0) queue.add(p);
                    continue;
                }
                if (!covered.contains(p) && queue.index_of(p) < 0) queue.add(p);
            }
        };
        add_batch({plA, x, plB});
        check(queue.size() == 3, "queue keeps playlist groups (3 rows, not 5)");
        check(queue.is_playlist_row(0), "row 0 is a playlist group (A)");
        check(!queue.is_playlist_row(1), "row 1 is a loose file (X)");
        check(queue.is_playlist_row(2), "row 2 is a playlist group (B)");

        // Logical playback sequence walks groups into their entries.
        QVector<QString> seq;
        for (int i = 0; i < queue.items().size(); ++i) {
            const PlaylistItem& item = queue.items()[i];
            if (item.is_playlist) {
                PlaylistModel tmp;
                if (PlaylistModel::load_file(item.path, &tmp).empty()) {
                    for (const PlaylistItem& entry : tmp.items()) seq.append(entry.path);
                    continue;
                }
            }
            seq.append(item.path);
        }
        check(seq.size() == 5, "logical sequence has 5 entries");
        check(seq[0] == a1 && seq[1] == a2 && seq[2] == x && seq[3] == b1 && seq[4] == b2,
              "logical sequence order: A1 A2 X B1 B2");

        // Re-adding a playlist (or its media) must not duplicate rows — even in
        // the same batch as the playlist itself.
        add_batch({plA, a1});
        check(queue.size() == 3, "re-add of playlist/media deduplicates (still 3 rows)");
    }

    // --- move_many: multi-selection moves as a block; others shift ---
    {
        PlaylistModel m;
        m.add(dirPath + "/1.mp3");
        m.add(dirPath + "/2.mp3");
        m.add(dirPath + "/3.mp3");
        m.add(dirPath + "/4.mp3");
        // Move rows {0,1} down by 1: block 0,1 -> 1,2; row 2 shifts up to 0.
        QVector<int> sel = {0, 1};
        m.move_many(sel, 1);
        check(m.items()[0].path.endsWith("/3.mp3"), "move_many down: 3 to top");
        check(m.items()[1].path.endsWith("/1.mp3"), "move_many down: 1 second");
        check(m.items()[2].path.endsWith("/2.mp3"), "move_many down: 2 third");
        check(m.items()[3].path.endsWith("/4.mp3"), "move_many down: 4 last");
        // Move rows {0,1} up by 1 (now containing 3 and 1).
        sel = {0, 1};
        m.move_many(sel, -1);
        check(m.items()[0].path.endsWith("/3.mp3") == false, "move_many up: block moved");
        check(m.items()[0].path.endsWith("/1.mp3"), "move_many up: 1 to top");
        check(m.items()[1].path.endsWith("/3.mp3"), "move_many up: 3 second");
    }

    // --- remove_many: children/rows removed at once ---
    {
        PlaylistModel m;
        m.add(dirPath + "/r1.mp3");
        m.add(dirPath + "/r2.mp3");
        m.add(dirPath + "/r3.mp3");
        m.remove_many({0, 2});
        check(m.size() == 1, "remove_many removes both rows");
        check(m.items()[0].path.endsWith("/r2.mp3"), "remove_many keeps the middle row");
    }

    // --- Move children out of a playlist ("sort out") ---
    {
        const QString a1 = dirPath + "/s-a1.mp3";
        const QString a2 = dirPath + "/s-a2.mp3";
        { QFile f(a1); f.open(QIODevice::WriteOnly); f.write("m"); }
        { QFile f(a2); f.open(QIODevice::WriteOnly); f.write("m"); }
        const QString plS = dirPath + "/S.m3u";
        PlaylistModel ps;
        ps.add(a1); ps.add(a2);
        check(PlaylistModel::save_m3u(plS, ps).empty(), "save playlist S");

        // Load the group, remove a2 from the file, persist, reload.
        PlaylistModel group;
        check(PlaylistModel::load_file(plS, &group).empty(), "load group S");
        QVector<int> to_remove;
        for (int k = 0; k < group.items().size(); ++k)
            if (group.items()[k].path == a2) to_remove.append(k);
        group.remove_many(to_remove);
        check(group.size() == 1, "child removed from playlist model");
        check(PlaylistModel::save_m3u(plS, group).empty(), "playlist S persisted after removal");
        PlaylistModel reloaded;
        PlaylistModel::load_file(plS, &reloaded);
        check(reloaded.size() == 1 && reloaded.index_of(a2) < 0, "removed child gone after reload");
    }

    // --- Move children into another playlist ("sort in") ---
    {
        const QString c1 = dirPath + "/c1.mp3";
        const QString c2 = dirPath + "/c2.mp3";
        { QFile f(c1); f.open(QIODevice::WriteOnly); f.write("m"); }
        { QFile f(c2); f.open(QIODevice::WriteOnly); f.write("m"); }
        const QString srcPl = dirPath + "/Src.m3u";
        const QString dstPl = dirPath + "/Dst.m3u";
        PlaylistModel src;
        src.add(c1); src.add(c2);
        check(PlaylistModel::save_m3u(srcPl, src).empty(), "save source playlist");
        PlaylistModel dst;
        dst.add(dirPath + "/existing.mp3");
        check(PlaylistModel::save_m3u(dstPl, dst).empty(), "save target playlist");

        // Append c1 (dedup: existing content stays first).
        PlaylistModel target;
        PlaylistModel::load_file(dstPl, &target);
        if (target.index_of(c1) < 0) target.add(c1);
        check(target.size() == 2 && target.index_of(c1) == 1, "child appended to target playlist");
        check(PlaylistModel::save_m3u(dstPl, target).empty(), "target playlist persisted");
    }

    // --- Extra playlist formats (Linux parity: XSPF/WPL/JSPF/ASX/RAM/JSON) ---
    {
        // XSPF
        const QString xspf = dirPath + "/p.xspf";
        { QFile f(xspf); f.open(QIODevice::WriteOnly);
          f.write("<playlist xmlns=\"http://xspf.org/ns/0/\"><trackList>"
                  "<track><title>T1</title><location>a.mp3</location></track>"
                  "<track><title>T2</title><location>b.mp3</location></track>"
                  "</trackList></playlist>"); }
        PlaylistModel mX;
        check(PlaylistModel::load_file(xspf, &mX).empty(), "load XSPF ok");
        check(mX.size() == 2 && mX.index_of(a) == 0 && mX.index_of(b) == 1,
              "XSPF resolves relative entries against base dir");

        // WPL
        const QString wpl = dirPath + "/p.wpl";
        { QFile f(wpl); f.open(QIODevice::WriteOnly);
          f.write("<smil><body><seq>"
                  "<media src=\"a.mp3\" title=\"W1\"/>"
                  "<media src=\"b.mp3\" title=\"W2\"/>"
                  "</seq></body></smil>"); }
        PlaylistModel mW;
        check(PlaylistModel::load_file(wpl, &mW).empty(), "load WPL ok");
        check(mW.size() == 2 && mW.items()[0].title == "W1", "WPL titles read");

        // JSPF
        const QString jspf = dirPath + "/p.jspf";
        { QFile f(jspf); f.open(QIODevice::WriteOnly);
          f.write("{\"playlist\":{\"track\":["
                  "{\"title\":\"J1\",\"location\":\"a.mp3\"},"
                  "{\"title\":\"J2\",\"location\":\"b.mp3\"}"
                  "]}}"); }
        PlaylistModel mJ;
        check(PlaylistModel::load_file(jspf, &mJ).empty(), "load JSPF ok");
        check(mJ.size() == 2 && mJ.index_of(a) == 0 && mJ.index_of(b) == 1,
              "JSPF tracks parsed");

        // MPCASU JSON
        const QString json = dirPath + "/p.json";
        { QFile f(json); f.open(QIODevice::WriteOnly);
          f.write("{\"version\":1,\"items\":[\"a.mp3\",\"b.mp3\"]}"); }
        PlaylistModel mJson;
        check(PlaylistModel::load_file(json, &mJson).empty(), "load MPCASU JSON ok");
        check(mJson.size() == 2 && mJson.index_of(a) == 0, "MPCASU JSON items parsed");

        // ASX
        const QString asx = dirPath + "/p.asx";
        { QFile f(asx); f.open(QIODevice::WriteOnly);
          f.write("<asx version=\"3.0\"><title>P</title>"
                  "<entry><title>A1</title><ref href=\"a.mp3\"/></entry>"
                  "<entry><title>A2</title><ref href=\"b.mp3\"/></entry>"
                  "</asx>"); }
        PlaylistModel mA;
        check(PlaylistModel::load_file(asx, &mA).empty(), "load ASX ok");
        check(mA.size() == 2 && mA.index_of(a) == 0 && mA.index_of(b) == 1,
              "ASX entries parsed");

        // RAM (plain text)
        const QString ram = dirPath + "/p.ram";
        { QFile f(ram); f.open(QIODevice::WriteOnly);
          f.write("# comment\na.mp3\nb.mp3\n"); }
        PlaylistModel mR;
        check(PlaylistModel::load_file(ram, &mR).empty(), "load RAM ok");
        check(mR.size() == 2 && mR.index_of(a) == 0, "RAM entries parsed");

        check(PlaylistModel::looks_like_playlist(xspf) &&
              PlaylistModel::looks_like_playlist(json) &&
              PlaylistModel::looks_like_playlist(asx), "new formats recognized as playlists");
    }

    std::printf(failures == 0 ? "ALL PASS\n" : "%d FAILURES\n", failures);
    return failures == 0 ? 0 : 1;
}