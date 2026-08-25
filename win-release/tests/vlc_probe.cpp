// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Live libVLC test for casu_playback: opens and plays a real media file
// through LibVLCBackend under Wine and asserts the backend decodes (the
// media clock advances). This is the core "player kernel works" gate.
#include "casu/playback/libvlc_backend.hpp"
#include "casu/playback/state.hpp"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <thread>
#include <vector>

namespace {
// Convert a POSIX path into the Wine drive form libVLC's media_new_path
// accepts (Z:\ with backslashes; forward-slash absolute paths are rejected).
std::string wine_path(const std::string& p) {
    if (p.empty()) return p;
    std::string out = p;
    for (char& c : out) if (c == '/') c = '\\';
    if (out[0] == '\\')
        out.insert(0, "Z:");
    return out;
}
}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::printf("usage: casu_playback_vlc_test <media>\n");
        return 2;
    }
    // libvlc_new returns NULL unless the plugin path is resolvable; the CMake
    // staging places plugins/ beside the exe, so point libVLC at it.
    std::string exe_dir = argv[0];
    std::string::size_type slash = exe_dir.find_last_of("/\\");
    if (slash != std::string::npos) exe_dir = exe_dir.substr(0, slash);
    _putenv_s("VLC_PLUGIN_PATH", (exe_dir + "\\plugins").c_str());

    const std::string media = wine_path(argv[1]);
    std::printf("probe media=%s\n", media.c_str());
    // Optional extra libVLC options (semicolon-separated). The Wine test
    // harness sets CASU_VLC_OPTIONS=--aout=dummy so playback verification does
    // not depend on a working host audio stack (decode + clock is the point).
    std::vector<std::string> options;
    if (const char* extra = std::getenv("CASU_VLC_OPTIONS")) {
        std::string current;
        for (const char* p = extra;; ++p) {
            if (*p == ';' || *p == '\0') {
                if (!current.empty()) options.push_back(current);
                current.clear();
                if (*p == '\0') break;
            } else {
                current.push_back(*p);
            }
        }
    }
    try {
        casu::playback::LibVLCBackend backend(nullptr, options);
        std::printf("libvlc version=%s\n", backend.backend_version().c_str());
        std::printf("opening...\n");
        backend.open_source(media);
        std::printf("opened state=%s duration=%.2f\n",
                    casu::playback::state_name(backend.state()), backend.duration());
        backend.play();
        std::printf("play requested\n");
        bool saw_playing = false;
        bool clock_moved = false;
        bool finished_clean = false;
        double last_pos = 0.0;
        for (int i = 0; i < 14; ++i) {
            std::this_thread::sleep_for(std::chrono::milliseconds(1000));
            auto st = backend.state();
            double pos = backend.position();
            if (st == casu::playback::PlaybackState::PLAYING) saw_playing = true;
            if (pos > 0.05 && pos > last_pos + 0.05) clock_moved = true;
            if (st == casu::playback::PlaybackState::ENDED) finished_clean = true;
            last_pos = pos;
            std::printf("t+%ds state=%s pos=%.2f dur=%.2f playing=%d\n",
                        i + 1, casu::playback::state_name(st), pos,
                        backend.duration(), backend.is_actively_playing() ? 1 : 0);
            if (clock_moved && (finished_clean || saw_playing)) break;
        }
        backend.close();
        // Decode and state-machine proof: the clock must advance and the
        // backend must reconcile late Buffering events to PLAYING at least
        // once.  A moving clock with permanent LOADING is a UI regression.
        const bool ok = clock_moved && saw_playing;
        std::printf(ok ? "RESULT PASS (decoded, clock moved, PLAYING observed)\n"
                       : "RESULT FAIL (clock/state mismatch)\n");
        return ok ? 0 : 1;
    } catch (const std::exception& e) {
        std::printf("EXCEPTION: %s\n", e.what());
        return 1;
    }
}
