// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Abstract playback backend interface for casu_playback. Concrete backends
// own decoding (libVLC, native CASU); the controller owns lifecycle and
// transport semantics (port of mpcasu_backend.py's backend protocol).
#pragma once
#include "casu/playback/state.hpp"

#include <string>
#include <vector>

namespace casu::playback {

struct TrackInfo {
    int id = -1;
    std::string name;
};

struct ChapterInfo {
    int index = 0;
    std::string name;
};

class PlaybackBackend {
public:
    virtual ~PlaybackBackend() = default;

    // Open a local file path or a media URL/location.
    virtual void open_source(const std::string& source) = 0;
    // Open a CASU container (CASUNAT1/CASUNAT2/MP5/sidecar manifest).
    virtual void open_casu(const std::string& path) = 0;

    virtual void play() = 0;
    virtual void pause() = 0;
    virtual void resume() = 0;
    virtual void stop() = 0;
    virtual void seek(double seconds) = 0;
    virtual double position() = 0;
    virtual double duration() = 0;
    virtual PlaybackState state() = 0;

    virtual int set_volume(int value) = 0;
    virtual int volume() = 0;
    virtual void set_mute(bool muted) = 0;
    virtual bool is_muted() = 0;
    virtual double set_rate(double rate) = 0;
    virtual double rate() = 0;

    virtual int audio_track_count() = 0;
    virtual int audio_track() = 0;
    virtual void set_audio_track(int track) = 0;
    virtual std::vector<TrackInfo> audio_track_descriptions() = 0;

    virtual int video_track_count() = 0;
    virtual int video_track() = 0;
    virtual void set_video_track(int track) = 0;
    virtual std::vector<TrackInfo> video_track_descriptions() = 0;

    virtual int subtitle_track_count() = 0;
    virtual int subtitle_track() = 0;
    virtual void set_subtitle_track(int track) = 0;
    virtual std::vector<TrackInfo> subtitle_track_descriptions() = 0;

    virtual std::vector<ChapterInfo> chapters() = 0;
    virtual void snapshot(const std::string& path) = 0;

    virtual std::string last_error() = 0;
    virtual bool is_actively_playing() = 0;

    // Release all media resources; the instance may remain usable.
    virtual void close_media() = 0;
    // Full teardown (instance too). Safe to call multiple times.
    virtual void close() = 0;
};

}  // namespace casu::playback
