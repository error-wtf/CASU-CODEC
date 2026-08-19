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

    std::printf(failures == 0 ? "ALL PASS\n" : "%d FAILURES\n", failures);
    return failures == 0 ? 0 : 1;
}