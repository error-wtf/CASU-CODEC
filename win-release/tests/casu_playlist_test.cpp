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

    // --- Mixed combination: playlist A + file X + playlist B in one queue ---
    // Canonical order: A1, A2, X, B1, B2 — plays through in sequence.
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

        // Simulate MainWindow::add_files (flat expansion + dedup).
        PlaylistModel queue;
        auto add_source = [&](const QString& p) {
            if (PlaylistModel::looks_like_playlist(p) && QFileInfo::exists(p)) {
                PlaylistModel tmp;
                if (PlaylistModel::load_file(p, &tmp).empty()) {
                    for (const PlaylistItem& item : tmp.items())
                        if (queue.index_of(item.path) < 0) queue.add(item.path, item.title);
                    return;
                }
            }
            if (queue.index_of(p) < 0) queue.add(p);
        };
        add_source(plA);
        add_source(x);
        add_source(plB);
        check(queue.size() == 5, "mixed queue has 5 entries");
        check(queue.index_of(a1) == 0, "mixed queue order: A1 first");
        check(queue.index_of(a2) == 1, "mixed queue order: A2 second");
        check(queue.index_of(x) == 2, "mixed queue order: X in the middle");
        check(queue.index_of(b1) == 3, "mixed queue order: B1 fourth");
        check(queue.index_of(b2) == 4, "mixed queue order: B2 last");

        // The combined queue plays through in order and ends cleanly.
        queue.set_current(0);
        int expected = 1;
        for (; expected < 5; ++expected) {
            int next = queue.next_index(true);
            check(next == expected, "mixed queue advances in order");
            queue.set_current(next);
        }
        check(queue.next_index(true) == -1, "mixed queue ends after last entry");

        // Re-adding a playlist (or its media) must not duplicate rows.
        add_source(plA);
        add_source(a1);
        check(queue.size() == 5, "re-add of playlist/media deduplicates");
        check(queue.index_of(a1) == 0 && queue.index_of(b2) == 4, "dedup keeps order");
    }

    // --- Merge a whole playlist into another playlist ---
    {
        const QString a1 = dirPath + "/merge-a1.mp3";
        const QString a2 = dirPath + "/merge-a2.mp3";
        { QFile f(a1); f.open(QIODevice::WriteOnly); f.write("m"); }
        { QFile f(a2); f.open(QIODevice::WriteOnly); f.write("m"); }
        const QString plA = dirPath + "/MergeA.m3u";
        const QString plB = dirPath + "/MergeB.m3u";
        PlaylistModel pa, pb;
        pa.add(a1); pa.add(a2);
        check(PlaylistModel::save_m3u(plA, pa).empty(), "merge source playlist saved");
        pb.add(dirPath + "/existing.mp3");
        check(PlaylistModel::save_m3u(plB, pb).empty(), "merge target playlist saved");

        // Simulate merge_selection_into_playlist: the selection contains the
        // playlist path; its entries are expanded and appended (dedup).
        QStringList selection = {plA};
        PlaylistModel merged;
        PlaylistModel::load_file(plB, &merged);
        for (const QString& path : selection) {
            if (PlaylistModel::looks_like_playlist(path) && QFileInfo::exists(path)) {
                PlaylistModel tmp;
                if (PlaylistModel::load_file(path, &tmp).empty()) {
                    for (const PlaylistItem& item : tmp.items())
                        if (merged.index_of(item.path) < 0) merged.add(item.path, item.title);
                    continue;
                }
            }
            if (merged.index_of(path) < 0) merged.add(path);
        }
        check(merged.size() == 3, "playlist-into-playlist merge adds all entries");
        check(merged.index_of(a1) == 1 && merged.index_of(a2) == 2,
              "merged playlist entries keep order after existing content");
        check(PlaylistModel::save_m3u(plB, merged).empty(), "merged playlist persisted");
    }

    std::printf(failures == 0 ? "ALL PASS\n" : "%d FAILURES\n", failures);
    return failures == 0 ? 0 : 1;
}