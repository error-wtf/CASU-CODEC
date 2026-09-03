// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Byte-parity tests for the settings module (apps/mpcasu/settings.cpp)
// against the Python reference casu/settings.py:
//  - save() output is BYTE-IDENTICAL to the reference writer
//  - load() round-trips every field from the reference-written file
//  - validated() applies the exact reference clamps
//  - session.json round-trips (Linux format incl. WxH+X+Y geometry).
#include "settings.hpp"

#include <QTemporaryDir>
#include <cstdio>
#include <fstream>
#include <sstream>

using namespace mpcasu;

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

PlayerSettings fixture_settings() {
    PlayerSettings s;
    s.volume = 137;
    s.muted = true;
    s.rate = 1.75;
    s.audio_device = QStringLiteral("pulse:alsa_output.test");
    s.watched_folders = QStringList{QStringLiteral("/home/tester/Musik"),
                                    QStringLiteral("/home/tester/Videos")};
    s.ytdlp_consent = true;
    s.visualizer = QStringLiteral("waveform");
    s.resume_playback = false;
    s.cache_limit_mib = 4096;
    s.recordings_dir = QStringLiteral("/home/tester/Aufnahmen");
    s.record_split_minutes = 30;
    s.record_format = QStringLiteral("mp3");
    s.shuffle = true;
    s.repeat_mode = QStringLiteral("one");
    return s;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::printf("usage: casu_settings_parity_test <fixture_dir>\n");
        return 2;
    }
    QTemporaryDir tmp;
    const QString out_path = tmp.filePath(QStringLiteral("settings.json"));
    SettingsStore store(out_path, tmp.filePath(QStringLiteral("session.json")));

    // --- save(): byte-identical to the reference writer ----------------------
    store.save(fixture_settings());
    const std::string mine =
        read_file(out_path.toStdString());
    const std::string ref =
        read_file(std::string(argv[1]) + "/ref_settings.json");
    if (mine != ref) {
        std::printf("sizes mine=%zu ref=%zu\n", mine.size(), ref.size());
        for (std::size_t i = 0; i < std::min(mine.size(), ref.size()); ++i) {
            if (mine[i] != ref[i]) {
                std::printf("first diff at byte %zu\nCPP: %.90s\nPY : %.90s\n",
                            i, mine.substr(i, 90).c_str(),
                            ref.substr(i, 90).c_str());
                break;
            }
        }
    }
    check(mine == ref, "settings.json BYTE-IDENTICAL to python writer");

    // --- load(): full field round-trip ---------------------------------------
    const PlayerSettings back = store.load();
    bool fields_ok = back.volume == 137 && back.muted && back.rate == 1.75 &&
                     back.audio_device ==
                         QStringLiteral("pulse:alsa_output.test") &&
                     back.watched_folders.size() == 2 &&
                     back.ytdlp_consent &&
                     back.visualizer == QStringLiteral("waveform") &&
                     !back.resume_playback && back.cache_limit_mib == 4096 &&
                     back.recordings_dir ==
                         QStringLiteral("/home/tester/Aufnahmen") &&
                     back.record_split_minutes == 30 &&
                     back.record_format == QStringLiteral("mp3") && back.shuffle &&
                     back.repeat_mode == QStringLiteral("one");
    check(fields_ok, "load() round-trips reference file");

    // --- validated() clamps ---------------------------------------------------
    PlayerSettings wild;
    wild.volume = 300;
    wild.rate = 9.0;
    wild.cache_limit_mib = -5;
    wild.record_split_minutes = 5000;
    wild.record_format = QStringLiteral("AVI");
    wild.repeat_mode = QStringLiteral("loop");
    wild.visualizer = QStringLiteral("bars");
    const PlayerSettings clamped = wild.validated();
    check(clamped.volume == 200 && clamped.rate == 4.0 &&
              clamped.cache_limit_mib == 0 &&
              clamped.record_split_minutes == 1440 &&
              clamped.record_format == QStringLiteral("mkv") &&
              clamped.repeat_mode == QStringLiteral("off") &&
              clamped.visualizer == QStringLiteral("waveform"),
          "validated() clamp parity");

    PlayerSettings nan_case;
    nan_case.rate = std::nan("");
    check(nan_case.validated().rate == 1.0, "non-finite rate -> 1.0");

    // --- version envelope enforcement ----------------------------------------
    {
        QFile bad(tmp.filePath(QStringLiteral("bad_version.json")));
        bad.open(QIODevice::WriteOnly);
        bad.write("{\"version\":2,\"player\":{\"volume\":77}}");
        bad.close();
        SettingsStore s2(bad.fileName());
        check(s2.load().volume == 100, "wrong envelope version -> defaults");
    }
    {
        QFile big(tmp.filePath(QStringLiteral("big.json")));
        big.open(QIODevice::WriteOnly);
        big.write(QByteArray(1024 * 1024 + 10, ' '));
        big.close();
        SettingsStore s3(big.fileName());
        check(s3.load().volume == 100, "oversized settings file -> defaults");
    }

    // --- watched folder cap ----------------------------------------------------
    PlayerSettings many;
    for (int i = 0; i < 101; ++i)
        many.watched_folders.append(QString("/f/%1").arg(i));
    check(many.validated().watched_folders.isEmpty(),
          ">100 watched folders dropped");

    // --- session round-trip -----------------------------------------------------
    SessionState state;
    state.playlist = QStringList{QStringLiteral("/a.mkv"),
                                 QStringLiteral("/b.mp3")};
    state.current = QStringLiteral("/a.mkv");
    state.position = 12.5;
    state.volume = 88;
    state.muted = true;
    state.rate = 1.25;
    state.width = 1280;
    state.height = 720;
    state.x = 10;
    state.y = 20;
    state.snapshot_dir = QStringLiteral("/shots");
    state.library_dir = QStringLiteral("/lib");
    state.last_playlist = QStringLiteral("/pl.m3u");
    store.save_session(state);
    const SessionState back_state = store.load_session();
    check(back_state.playlist == state.playlist &&
              back_state.current == state.current &&
              back_state.position == 12.5 && back_state.volume == 88 &&
              back_state.muted && back_state.rate == 1.25 &&
              back_state.width == 1280 && back_state.height == 720 &&
              back_state.x == 10 && back_state.y == 20 &&
              back_state.snapshot_dir == QStringLiteral("/shots") &&
              back_state.library_dir == QStringLiteral("/lib") &&
              back_state.last_playlist == QStringLiteral("/pl.m3u"),
          "session.json round-trip");

    if (failures == 0) std::printf("ALL PASS\n");
    return failures == 0 ? 0 : 1;
}
