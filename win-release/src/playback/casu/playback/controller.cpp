// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/playback/controller.hpp"

#include <algorithm>
#include <utility>

namespace casu::playback {

void CppPlaybackController::attach(std::shared_ptr<PlaybackBackend> backend,
                                   std::string source) {
    if (!backend)
        throw PlaybackError("attach requires a non-null backend");
    close();
    set_state(PlaybackState::LOADING);
    backend_ = std::move(backend);
    source_ = std::move(source);
    try {
        set_state(PlaybackState::READY);
    } catch (...) {
        last_error_ = "media backend failed while attaching";
        set_state(PlaybackState::ERROR);
        throw;
    }
}

void CppPlaybackController::play() {
    if (!backend_)
        throw PlaybackError("no media backend is attached");
    backend_->play();
    set_state(PlaybackState::PLAYING);
}

void CppPlaybackController::pause_or_resume() {
    if (!backend_)
        throw PlaybackError("no media backend is attached");
    if (state_ == PlaybackState::PAUSED) {
        backend_->resume();
        set_state(PlaybackState::PLAYING);
    } else {
        backend_->pause();
        set_state(PlaybackState::PAUSED);
    }
}

void CppPlaybackController::stop() {
    if (backend_)
        backend_->stop();
    set_state(backend_ ? PlaybackState::STOPPED : PlaybackState::EMPTY);
}

void CppPlaybackController::seek(double seconds) {
    if (!backend_)
        throw PlaybackError("no media backend is attached");
    backend_->seek(std::max(0.0, seconds));
}

double CppPlaybackController::position() const {
    return backend_ ? backend_->position() : 0.0;
}

double CppPlaybackController::duration() const {
    return backend_ ? backend_->duration() : 0.0;
}

void CppPlaybackController::close() {
    if (backend_)
        backend_->close();
    backend_.reset();
    source_.clear();
    last_error_.clear();
    set_state(PlaybackState::EMPTY);
}

std::shared_ptr<PlaybackBackend> CppPlaybackController::detach() {
    auto backend = backend_;
    backend_.reset();
    source_.clear();
    set_state(PlaybackState::EMPTY);
    return backend;
}

void CppPlaybackController::notify_backend_state(PlaybackState s) {
    switch (s) {
        case PlaybackState::PLAYING:
        case PlaybackState::PAUSED:
        case PlaybackState::STOPPED:
            set_state(s);
            break;
        case PlaybackState::ENDED:
            set_state(PlaybackState::ENDED);
            break;
        case PlaybackState::ERROR:
            if (backend_)
                last_error_ = backend_->last_error();
            set_state(PlaybackState::ERROR);
            break;
        default:
            break;  // EMPTY/LOADING/READY are controller-requested
    }
}

void CppPlaybackController::poll() {
    if (!backend_)
        return;
    PlaybackState s = backend_->state();
    if (s != PlaybackState::EMPTY && s != PlaybackState::LOADING &&
        s != PlaybackState::READY)
        notify_backend_state(s);
}

}  // namespace casu::playback
