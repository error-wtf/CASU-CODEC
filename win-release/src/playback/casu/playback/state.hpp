// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Shared playback states for casu_playback (port of mpcasu_playback.py).
#pragma once
#include <string>

namespace casu::playback {

enum class PlaybackState {
    EMPTY,
    LOADING,
    READY,
    PLAYING,
    PAUSED,
    STOPPED,
    ENDED,
    ERROR,
};

inline const char* state_name(PlaybackState s) {
    switch (s) {
        case PlaybackState::EMPTY: return "EMPTY";
        case PlaybackState::LOADING: return "LOADING";
        case PlaybackState::READY: return "READY";
        case PlaybackState::PLAYING: return "PLAYING";
        case PlaybackState::PAUSED: return "PAUSED";
        case PlaybackState::STOPPED: return "STOPPED";
        case PlaybackState::ENDED: return "ENDED";
        case PlaybackState::ERROR: return "ERROR";
    }
    return "UNKNOWN";
}

}  // namespace casu::playback
