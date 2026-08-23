// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// LibVLCBackend — in-process libVLC backend for MPCASU (port of
// mpcasu_backend.py LibVLCBackend). RAII ownership of the libVLC
// instance/media/player; renders into a caller-provided HWND. Uses the
// bundled 3.0 ABI bindings (casu/libvlc_bind.h), never an external vlc.exe.
#pragma once
#include "casu/playback/backend.hpp"

#include <functional>
#include <string>
#include <vector>

struct libvlc_instance_t;
struct libvlc_media_t;
struct libvlc_media_player_t;
struct libvlc_event_t;
struct libvlc_track_description_t;
struct libvlc_event_manager_t;
typedef struct libvlc_event_manager_t libvlc_event_manager_t;

namespace casu::playback {

class LibVLCBackend final : public PlaybackBackend {
public:
    // `hwnd` is the native window handle libVLC draws into (may be null for
    // audio-only / offscreen use). `runtime_options` are libVLC argv options.
    explicit LibVLCBackend(void* hwnd, std::vector<std::string> runtime_options = {});
    ~LibVLCBackend() override;
    LibVLCBackend(const LibVLCBackend&) = delete;
    LibVLCBackend& operator=(const LibVLCBackend&) = delete;

    // Fired from the libVLC event thread with the new backend state; connect
    // to a Qt queued-signal bridge, never call Qt directly from it.
    std::function<void(PlaybackState)> on_event;

    void open_source(const std::string& source) override;
    void open_casu(const std::string& path) override;

    void play() override;
    void pause() override;
    void resume() override;
    void stop() override;
    void seek(double seconds) override;
    double position() override;
    double duration() override;
    PlaybackState state() override;

    int set_volume(int value) override;
    int volume() override;
    void set_mute(bool muted) override;
    bool is_muted() override;
    double set_rate(double rate) override;
    double rate() override;

    int audio_track_count() override;
    int audio_track() override;
    void set_audio_track(int track) override;
    std::vector<TrackInfo> audio_track_descriptions() override;

    int video_track_count() override;
    int video_track() override;
    void set_video_track(int track) override;
    std::vector<TrackInfo> video_track_descriptions() override;

    int subtitle_track_count() override;
    int subtitle_track() override;
    void set_subtitle_track(int track) override;
    std::vector<TrackInfo> subtitle_track_descriptions() override;

    std::vector<ChapterInfo> chapters() override;
    void set_chapter(int index) override;
    void next_frame() override;
    void set_audio_delay(double milliseconds) override;
    void set_subtitle_delay(double milliseconds) override;
    bool load_subtitle_file(const std::string& path) override;
    std::vector<TrackInfo> audio_devices() override;
    void set_audio_device(const std::string& device) override;
    void snapshot(const std::string& path) override;

    std::string last_error() override;
    bool is_actively_playing() override;
    void close_media() override;
    void close() override;

    std::string backend_version() const;

    // Called from the libVLC event thread by the C event trampoline; must
    // only update backend state and invoke on_event (never Qt directly).
    void handle_event(int event_type);

private:
    void attach_events();
    void note_error();
    void detach_events();
    static bool is_location(const std::string& value);
    void apply_source(const std::string& source);

    void* hwnd_ = nullptr;
    std::vector<std::string> runtime_options_;
    libvlc_instance_t* instance_ = nullptr;
    libvlc_media_t* media_ = nullptr;
    libvlc_media_player_t* player_ = nullptr;
    libvlc_event_manager_t* event_manager_ = nullptr;
    double play_requested_at_ = -1.0;
    PlaybackState state_ = PlaybackState::EMPTY;
    std::string last_error_detail_;
    std::vector<std::string> temp_sinks_;
    void cleanup_temp_sinks();

public:
    std::string last_error_detail() const override {
        return last_error_detail_;
    }
};

}  // namespace casu::playback
