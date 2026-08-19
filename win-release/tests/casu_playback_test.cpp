// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Unit tests for casu::playback::CppPlaybackController: every documented
// state transition (EMPTY/LOADING/READY/PLAYING/PAUSED/STOPPED/ENDED/ERROR),
// delegation to the backend, and defensive boundaries. Runs offline under
// Wine. Uses a scripted mock backend (no libVLC instance is created).
#include "casu/playback/controller.hpp"
#include "casu/playback/state.hpp"

#include <cstdio>
#include <memory>
#include <string>
#include <vector>

using namespace casu::playback;

namespace {
int failures = 0;

void check(bool ok, const char* label) {
    if (!ok) { ++failures; std::printf("FAIL %s\n", label); }
    else std::printf("ok   %s\n", label);
}

// Scripted mock: records every call and honours configured failure modes.
class MockBackend final : public PlaybackBackend {
public:
    bool fail_open = false;
    bool fail_play = false;
    PlaybackState reported = PlaybackState::READY;
    std::vector<std::string> calls;

    void open_source(const std::string&) override { calls.push_back("open_source"); if (fail_open) throw PlaybackError("mock open failed"); }
    void open_casu(const std::string&) override { calls.push_back("open_casu"); }
    void play() override { calls.push_back("play"); if (fail_play) throw PlaybackError("mock play failed"); }
    void pause() override { calls.push_back("pause"); }
    void resume() override { calls.push_back("resume"); }
    void stop() override { calls.push_back("stop"); }
    void seek(double s) override { calls.push_back("seek:" + std::to_string(static_cast<int>(s))); }
    double position() override { return 12.5; }
    double duration() override { return 60.0; }
    PlaybackState state() override { return reported; }
    int set_volume(int v) override { return v; }
    int volume() override { return 100; }
    void set_mute(bool) override {}
    bool is_muted() override { return false; }
    double set_rate(double r) override { return r; }
    double rate() override { return 1.0; }
    int audio_track_count() override { return 1; }
    int audio_track() override { return 0; }
    void set_audio_track(int) override {}
    std::vector<TrackInfo> audio_track_descriptions() override { return {{0, "a"}}; }
    int video_track_count() override { return 1; }
    int video_track() override { return 0; }
    void set_video_track(int) override {}
    std::vector<TrackInfo> video_track_descriptions() override { return {{0, "v"}}; }
    int subtitle_track_count() override { return 0; }
    int subtitle_track() override { return -1; }
    void set_subtitle_track(int) override {}
    std::vector<TrackInfo> subtitle_track_descriptions() override { return {}; }
    std::vector<ChapterInfo> chapters() override { return {}; }
    void snapshot(const std::string&) override {}
    std::string last_error() override { return "mock error detail"; }
    bool is_actively_playing() override { return true; }
    void close_media() override { calls.push_back("close_media"); }
    void close() override { calls.push_back("close"); }
};
}  // namespace

int main() {
    // --- initial state ---
    {
        CppPlaybackController c;
        check(c.state() == PlaybackState::EMPTY, "initial state EMPTY");
        check(!c.has_backend(), "no backend initially");
        check(c.position() == 0.0 && c.duration() == 0.0, "position/duration 0 without backend");
    }

    // --- attach: EMPTY -> LOADING -> READY ---
    {
        CppPlaybackController c;
        auto b = std::make_shared<MockBackend>();
        c.attach(b, "clip.mp4");
        check(c.state() == PlaybackState::READY, "attach -> READY");
        check(c.has_backend(), "attach keeps backend");
        check(c.source() == "clip.mp4", "attach records source");
        check(b->calls.empty(), "attach does not call backend open");
    }

    // --- attach closes an old backend: PLAYING -> EMPTY -> LOADING -> READY ---
    {
        CppPlaybackController c;
        auto b1 = std::make_shared<MockBackend>();
        c.attach(b1, "one");
        c.play();
        check(c.state() == PlaybackState::PLAYING, "play -> PLAYING");
        auto b2 = std::make_shared<MockBackend>();
        c.attach(b2, "two");
        check(c.state() == PlaybackState::READY, "re-attach -> READY");
        check(!b1->calls.empty() && b1->calls.back() == "close", "attach closes old backend");
    }

    // --- attach with a backend whose open failed is surfaced before attach ---
    {
        CppPlaybackController c;
        auto b = std::make_shared<MockBackend>();
        b->fail_open = true;
        bool threw = false;
        try { b->open_source("x"); } catch (const PlaybackError&) { threw = true; }
        check(threw, "backend open failure throws PlaybackError");
    }

    // --- attach with null backend is rejected ---
    {
        CppPlaybackController c;
        bool threw = false;
        try { c.attach(nullptr, "x"); }
        catch (const PlaybackError&) { threw = true; }
        check(threw, "attach(nullptr) throws");
        check(c.state() == PlaybackState::EMPTY, "attach(nullptr) keeps EMPTY");
    }

    // --- play / pause_or_resume transitions ---
    {
        CppPlaybackController c;
        auto b = std::make_shared<MockBackend>();
        c.attach(b, "clip.mp4");
        c.play();
        check(c.state() == PlaybackState::PLAYING, "play -> PLAYING");
        c.pause_or_resume();
        check(c.state() == PlaybackState::PAUSED, "pause_or_resume -> PAUSED");
        check(!b->calls.empty() && b->calls.back() == "pause", "pause called on backend");
        c.pause_or_resume();
        check(c.state() == PlaybackState::PLAYING, "pause_or_resume -> PLAYING (resume)");
        check(!b->calls.empty() && b->calls.back() == "resume", "resume called on backend");
    }

    // --- play failure: backend throws, controller records error state via event ---
    {
        CppPlaybackController c;
        auto b = std::make_shared<MockBackend>();
        c.attach(b, "clip.mp4");
        b->fail_play = true;
        bool threw = false;
        try { c.play(); } catch (const PlaybackError&) { threw = true; }
        check(threw, "play propagates backend failure");
        c.notify_backend_state(PlaybackState::ERROR);
        check(c.state() == PlaybackState::ERROR, "backend error -> ERROR");
        check(c.last_error() == "mock error detail", "ERROR records backend last_error");
    }

    // --- stop: PLAYING -> STOPPED ---
    {
        CppPlaybackController c;
        auto b = std::make_shared<MockBackend>();
        c.attach(b, "clip.mp4");
        c.play();
        c.stop();
        check(c.state() == PlaybackState::STOPPED, "stop -> STOPPED");
        check(c.has_backend(), "stop keeps backend attached");
        check(!b->calls.empty() && b->calls.back() == "stop", "stop called on backend");
    }

    // --- stop with no backend -> EMPTY ---
    {
        CppPlaybackController c;
        c.stop();
        check(c.state() == PlaybackState::EMPTY, "stop without backend -> EMPTY");
    }

    // --- close: any state -> EMPTY; backend closed ---
    {
        CppPlaybackController c;
        auto b = std::make_shared<MockBackend>();
        c.attach(b, "clip.mp4");
        c.play();
        c.close();
        check(c.state() == PlaybackState::EMPTY, "close -> EMPTY");
        check(!c.has_backend(), "close detaches backend");
        check(!b->calls.empty() && b->calls.back() == "close", "close closes backend");
    }

    // --- detach returns ownership without closing ---
    {
        CppPlaybackController c;
        auto b = std::make_shared<MockBackend>();
        c.attach(b, "clip.mp4");
        c.play();
        auto returned = c.detach();
        check(returned == b, "detach returns the backend");
        check(c.state() == PlaybackState::EMPTY, "detach -> EMPTY");
        bool closed = false;
        for (const std::string& call : b->calls)
            if (call == "close") closed = true;
        check(!closed, "detach does not close the backend");
    }

    // --- seek / position / duration delegate ---
    {
        CppPlaybackController c;
        auto b = std::make_shared<MockBackend>();
        c.attach(b, "clip.mp4");
        c.seek(30.0);
        check(!b->calls.empty() && b->calls.back() == "seek:30", "seek delegates");
        c.seek(-5.0);
        check(!b->calls.empty() && b->calls.back() == "seek:0", "seek clamps negatives");
        check(c.position() == 12.5, "position delegates");
        check(c.duration() == 60.0, "duration delegates");
        bool threw = false;
        CppPlaybackController empty;
        try { empty.seek(5.0); } catch (const PlaybackError&) { threw = true; }
        check(threw, "seek without backend throws");
        try { empty.play(); } catch (const PlaybackError&) { threw = threw && true; }
        check(threw, "play without backend throws");
        try { empty.pause_or_resume(); } catch (const PlaybackError&) { threw = threw && true; }
        check(threw, "pause_or_resume without backend throws");
    }

    // --- backend event notifications ---
    {
        CppPlaybackController c;
        auto b = std::make_shared<MockBackend>();
        c.attach(b, "clip.mp4");
        c.play();
        c.notify_backend_state(PlaybackState::ENDED);
        check(c.state() == PlaybackState::ENDED, "event ENDED -> ENDED");
        c.notify_backend_state(PlaybackState::ERROR);
        check(c.state() == PlaybackState::ERROR, "event ERROR -> ERROR");
    }

    // --- poll folds the backend's reported state in ---
    {
        CppPlaybackController c;
        auto b = std::make_shared<MockBackend>();
        c.attach(b, "clip.mp4");
        c.play();
        b->reported = PlaybackState::ENDED;
        c.poll();
        check(c.state() == PlaybackState::ENDED, "poll picks up backend ENDED");
        b->reported = PlaybackState::ERROR;
        c.poll();
        check(c.state() == PlaybackState::ERROR, "poll picks up backend ERROR");
    }

    std::printf(failures == 0 ? "ALL PASS\n" : "%d FAILURES\n", failures);
    return failures == 0 ? 0 : 1;
}
