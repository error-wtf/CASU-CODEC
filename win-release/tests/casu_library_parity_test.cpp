// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Parity tests for the media library port (apps/mpcasu/library.cpp) against
// casu/library.py semantics: extension whitelist, resume dur-5 clamp,
// bookmark upsert + default label, ±5000 ms delay clamps, casefold search,
// legacy-array migration, group-key fallback.
#include "library.hpp"

#include "casu/json.hpp"

#include <QTemporaryDir>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <sstream>

using namespace mpcasu;
using casu::JsonValue;

namespace {

int failures = 0;

void check(bool ok, const char* label) {
    if (!ok) {
        ++failures;
        std::printf("FAIL %s\n", label);
    } else {
        std::printf("ok   %s\n", label);
    }
}

std::string read_file(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::printf("usage: casu_library_parity_test <fixture_dir>\n");
        return 2;
    }
    QTemporaryDir tmp;

    // --- Extension whitelist parity -----------------------------------------
    {
        const QStringList mine = media_extensions();
        const JsonValue ref =
            casu::parse_json(read_file(std::string(argv[1]) +
                                       "/ref_library_extensions.json"));
        QStringList ref_list;
        for (const JsonValue& v : ref.as_array().items)
            ref_list.append(QString::fromStdString(v.as_string()));
        QStringList sorted_mine = mine;
        sorted_mine.sort();
        check(sorted_mine == ref_list,
              "media extension whitelist IDENTICAL to reference");
    }

    MediaLibrary lib(tmp.filePath("library.json"));

    // --- Resume clamp (dur - 5 rule) ------------------------------------------
    const QString media = tmp.filePath("clip.mp4");
    { QFile f(media); f.open(QIODevice::WriteOnly); f.write("x"); }
    lib.add(media, QStringLiteral("Clip"));
    lib.record_progress(media, 94.0, 100.0);
    const LibraryEntry* e = &lib.entries()[lib.index_of(media)];
    check(e->resume_seconds == 94.0 && e->has_duration &&
              e->duration_seconds == 100.0,
          "resume keeps position below dur-5");
    lib.record_progress(media, 98.5, 100.0);
    e = &lib.entries()[lib.index_of(media)];
    check(e->resume_seconds == 0.0, "position >= dur-5 resets resume to 0");
    lib.record_progress(media, std::nan(""), std::nullopt);
    e = &lib.entries()[lib.index_of(media)];
    check(e->resume_seconds == 0.0, "non-finite position is ignored");

    // --- Bookmarks: upsert + default label -------------------------------------
    const int id1 = lib.add_bookmark(media, 42.0);
    const int id2 = lib.add_bookmark(media, 42.0, QStringLiteral("Intro"));
    check(id1 > 0 && id2 == id1, "bookmark upsert returns same id");
    QVector<MediaBookmark> bms = lib.bookmarks(media);
    check(bms.size() == 1 && bms.first().label == QStringLiteral("Intro"),
          "bookmark label updated on conflict");
    const int id3 = lib.add_bookmark(media, 7.25);
    bms = lib.bookmarks(media);
    check(bms.size() == 2 && bms.first().label == QStringLiteral("7.2 s") &&
              bms.first().position_seconds == 7.25,
          "default bookmark label uses one-decimal seconds");
    check(lib.add_bookmark(media, -1.0) == -1 &&
              lib.add_bookmark(media, std::nan("")) == -1,
          "invalid bookmark positions rejected");

    // --- Saved playlists --------------------------------------------------------
    lib.save_playlist(QStringLiteral("Favoriten"),
                      {QStringLiteral("/a.mkv"), QStringLiteral("/b.mp3")});
    lib.save_playlist(QStringLiteral("favoriten"),
                      {QStringLiteral("/c.ogg")});  // distinct name
    check(lib.playlist_names().size() == 2,
          "playlist names are case-sensitive like the reference UNIQUE");
    check(lib.load_playlist(QStringLiteral("Favoriten")).size() == 2,
          "saved playlist round-trip");

    // --- Delay clamps -------------------------------------------------------------
    PlaybackPreferences prefs;
    prefs.audio_delay_ms = 99999.0;
    prefs.subtitle_delay_ms = -123456.0;
    prefs.audio_track = 2;
    lib.set_playback_preferences(media, prefs);
    const PlaybackPreferences back = lib.playback_preferences(media);
    check(back.audio_delay_ms == 5000.0 &&
              back.subtitle_delay_ms == -5000.0 && back.audio_track == 2,
          "A/V delays clamped to ±5000 ms");

    // --- Search casefold + ordering -------------------------------------------------
    LibraryEntry* entry = nullptr;
    for (LibraryEntry& it : const_cast<QVector<LibraryEntry>&>(lib.entries()))
        if (it.path == media) entry = &it;
    if (entry) entry->metadata.insert(QStringLiteral("artist"),
                                      QStringLiteral("Künstler"));
    const QVector<LibraryEntry> hits = lib.search(QStringLiteral("kÜNSTLER"));
    check(hits.size() == 1, "search matches metadata casefolded");

    // --- Legacy bare-array migration --------------------------------------------------
    {
        const QString legacy = tmp.filePath("legacy.json");
        QFile f(legacy);
        f.open(QIODevice::WriteOnly);
        f.write(QByteArray(
            "[{\"path\":\"/old.mp3\",\"title\":\"Old\",\"kind\":\"audio\","
            "\"added_ms\":123,\"favorite\":true}]"));
        f.close();
        MediaLibrary old_lib(legacy);
        old_lib.load();
        check(old_lib.entries().size() == 1 &&
                  old_lib.entries().first().favorite,
              "legacy array library file loads");
    }

    // --- Group key fallback --------------------------------------------------------------
    check(library_group_key(QStringLiteral("")) ==
                  QStringLiteral("(unknown)") &&
              library_group_key(QStringLiteral("  ")) ==
                  QStringLiteral("(unknown)") &&
              library_group_key(QStringLiteral(" Rock ")) ==
                  QStringLiteral("Rock"),
          "group key '(unknown)' fallback");

    // --- Persistence round-trip incl. new fields -------------------------------------------
    lib.save();
    MediaLibrary reloaded(tmp.filePath("library.json"));
    reloaded.load();
    check(reloaded.entries().size() == lib.entries().size() &&
              reloaded.bookmarks(media).size() == 2 &&
              reloaded.load_playlist(QStringLiteral("Favoriten")).size() == 2,
          "library file round-trips entries+bookmarks+playlists");

    if (failures == 0) std::printf("ALL PASS\n");
    return failures == 0 ? 0 : 1;
}
