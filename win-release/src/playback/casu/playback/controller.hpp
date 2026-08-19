// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CppPlaybackController — playback state/control boundary (port of
// mpcasu_playback.py PlaybackController). Owns the lifecycle/transport
// semantics; concrete backends own decoding.
#pragma once
#include "casu/playback/backend.hpp"
#include "casu/playback/state.hpp"

#include <memory>
#include <stdexcept>
#include <string>

namespace casu::playback {

class PlaybackError : public std::runtime_error {
public:
    explicit PlaybackError(const std::string& msg) : std::runtime_error(msg) {}
};

class CppPlaybackController {
public:
    CppPlaybackController() = default;
    ~CppPlaybackController() = default;
    CppPlaybackController(const CppPlaybackController&) = delete;
    CppPlaybackController& operator=(const CppPlaybackController&) = delete;

    // Close any previous backend, then LOADING -> READY. The caller must have
    // already opened the media on the backend (open_source/open_casu).
    void attach(std::shared_ptr<PlaybackBackend> backend, std::string source);
    void play();
    void pause_or_resume();
    void stop();
    void seek(double seconds);
    double position() const;
    double duration() const;
    void close();
    // Give ownership back without closing the backend.
    std::shared_ptr<PlaybackBackend> detach();

    // Sync terminal/non-terminal states reported by the backend (event
    // callback or poll); ERROR also records backend->last_error().
    void notify_backend_state(PlaybackState s);
    // Ask the backend for its state and fold the result into ours.
    void poll();

    PlaybackState state() const { return state_; }
    const std::string& source() const { return source_; }
    const std::string& last_error() const { return last_error_; }
    bool has_backend() const { return static_cast<bool>(backend_); }
    PlaybackBackend* backend() const { return backend_.get(); }
    std::shared_ptr<PlaybackBackend> backend_ptr() const { return backend_; }

private:
    void set_state(PlaybackState s) { state_ = s; }

    std::shared_ptr<PlaybackBackend> backend_;
    std::string source_;
    PlaybackState state_ = PlaybackState::EMPTY;
    std::string last_error_;
};

}  // namespace casu::playback
