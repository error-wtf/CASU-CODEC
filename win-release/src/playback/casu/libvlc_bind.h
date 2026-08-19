// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Minimal libVLC 3.0 C bindings for the Windows port (MPCASU / casu_playback).
//
// IMPORTANT (ABI decision): the headers under /home/error/vlc/include are for
// libVLC 4.0 (LIBVLC_VERSION_MAJOR=4), but the bundled Windows DLL is libVLC
// 3.0.21. The libVLC 4.0 headers are NOT ABI-compatible with the 3.0.21 DLL:
// in 4.0 the media-creation functions take no libvlc_instance_t* (the instance
// is implicit), while in 3.0 they DO take it as the first parameter.
//
// To avoid stack/ABI corruption we declare here the functions we need with the
// 3.0 signatures (verified against the 3.0.21 DLL via `gendef`/`dlltool`).
// The rest of the player functions have the same signature in 3.0 and 4.0.
#pragma once
#include <cstddef>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct libvlc_instance_t libvlc_instance_t;
typedef struct libvlc_media_t libvlc_media_t;
typedef struct libvlc_media_player_t libvlc_media_player_t;
typedef struct libvlc_track_description_t libvlc_track_description_t;
typedef struct libvlc_media_track_info_t libvlc_media_track_info_t;
typedef struct libvlc_event_manager_t libvlc_event_manager_t;
typedef struct libvlc_event_t libvlc_event_t;
typedef struct libvlc_media_stats_t libvlc_media_stats_t;
typedef struct libvlc_media_track_t libvlc_media_track_t;
typedef struct libvlc_audio_output_device_t libvlc_audio_output_device_t;

typedef int64_t libvlc_time_t;
typedef long long libvlc_time_t_ll;

typedef enum libvlc_state_t {
    libvlc_NothingSpecial = 0,
    libvlc_Opening,
    libvlc_Buffering,
    libvlc_Playing,
    libvlc_Paused,
    libvlc_Stopped,
    libvlc_Ended,
    libvlc_Error
} libvlc_state_t;

// Event ids use the libVLC 3.0 enumeration (0x100 base for media-player
// events). The 3.0.21 DLL reports these values; the 4.0 headers use 0x200.
typedef enum libvlc_event_e {
    libvlc_MediaPlayerMediaChanged = 0x100,
    libvlc_MediaPlayerNothingSpecial = 0x101,
    libvlc_MediaPlayerOpening = 0x102,
    libvlc_MediaPlayerBuffering = 0x103,
    libvlc_MediaPlayerPlaying = 0x104,
    libvlc_MediaPlayerPaused = 0x105,
    libvlc_MediaPlayerStopped = 0x106,
    libvlc_MediaPlayerForward = 0x107,
    libvlc_MediaPlayerBackward = 0x108,
    libvlc_MediaPlayerEndReached = 0x109,
    libvlc_MediaPlayerEncounteredError = 0x10a,
    libvlc_MediaPlayerTimeChanged = 0x10b,
    libvlc_MediaPlayerPositionChanged = 0x10c,
    libvlc_MediaPlayerSeekableChanged = 0x10d,
    libvlc_MediaPlayerPausableChanged = 0x10e,
    libvlc_MediaPlayerTitleChanged = 0x10f,
    libvlc_MediaPlayerSnapshotTaken = 0x110,
    libvlc_MediaPlayerLengthChanged = 0x111,
    libvlc_MediaPlayerVout = 0x112,
    libvlc_MediaPlayerScrambledChanged = 0x113,
    libvlc_MediaPlayerESAdded = 0x114,
    libvlc_MediaPlayerESDeleted = 0x115,
    libvlc_MediaPlayerESSelected = 0x116,
    libvlc_MediaPlayerCorked = 0x117,
    libvlc_MediaPlayerUncorked = 0x118,
    libvlc_MediaPlayerMuted = 0x119,
    libvlc_MediaPlayerUnmuted = 0x11a,
    libvlc_MediaPlayerAudioVolume = 0x11b,
    libvlc_MediaPlayerAudioDevice = 0x11c,
    libvlc_MediaPlayerChapterChanged = 0x11d,
} libvlc_event_e;

typedef void (*libvlc_callback_t)(const libvlc_event_t*, void*);

// --- instance / version ---
const char* libvlc_get_version(void);
const char* libvlc_get_compiler(void);
const char* libvlc_get_changeset(void);
libvlc_instance_t* libvlc_new(int argc, const char* const* argv);
void libvlc_release(libvlc_instance_t*);

// --- media (3.0 signatures: take libvlc_instance_t* first) ---
libvlc_media_t* libvlc_media_new_location(libvlc_instance_t* p_instance, const char* psz_mrl);
libvlc_media_t* libvlc_media_new_path(libvlc_instance_t* p_instance, const char* psz_path);
void libvlc_media_release(libvlc_media_t* p_meta_desc);
void libvlc_media_add_option(libvlc_media_t* p_md, const char* psz_options);
libvlc_media_t* libvlc_media_player_get_media(libvlc_media_player_t* p_mi);
void libvlc_media_player_set_media(libvlc_media_player_t* p_mi, libvlc_media_t* p_md);

// --- media player ---
libvlc_media_player_t* libvlc_media_player_new(libvlc_instance_t* p_instance);
libvlc_media_player_t* libvlc_media_player_new_from_media(libvlc_media_t* p_md);
void libvlc_media_player_release(libvlc_media_player_t* p_mi);
int libvlc_media_player_play(libvlc_media_player_t* p_mi);
void libvlc_media_player_set_pause(libvlc_media_player_t* mp, int do_pause);
void libvlc_media_player_pause(libvlc_media_player_t* p_mi);
void libvlc_media_player_stop(libvlc_media_player_t* p_mi);
void libvlc_media_player_set_time(libvlc_media_player_t* p_mi, libvlc_time_t i_time);
libvlc_time_t libvlc_media_player_get_time(libvlc_media_player_t* p_mi);
libvlc_time_t libvlc_media_player_get_length(libvlc_media_player_t* p_mi);
void libvlc_media_player_set_position(libvlc_media_player_t* p_mi, float f_pos);
float libvlc_media_player_get_position(libvlc_media_player_t* p_mi);
int libvlc_media_player_set_rate(libvlc_media_player_t* p_mi, float rate);
float libvlc_media_player_get_rate(libvlc_media_player_t* p_mi);
libvlc_state_t libvlc_media_player_get_state(libvlc_media_player_t* p_mi);
void libvlc_media_player_set_hwnd(libvlc_media_player_t* p_mi, void* drawable);
void libvlc_media_player_set_xwindow(libvlc_media_player_t* p_mi, unsigned long drawable);
unsigned libvlc_media_player_has_vout(libvlc_media_player_t* p_mi);
int libvlc_audio_set_volume(libvlc_media_player_t* p_mi, int i_volume);
int libvlc_audio_get_volume(libvlc_media_player_t* p_mi);
int libvlc_media_player_is_seekable(libvlc_media_player_t* p_mi);
int libvlc_media_player_is_playing(libvlc_media_player_t* p_mi);
int libvlc_media_player_can_pause(libvlc_media_player_t* p_mi);
void libvlc_audio_set_mute(libvlc_media_player_t* p_mi, int mute);
int libvlc_audio_get_mute(libvlc_media_player_t* p_mi);

// --- events ---
libvlc_event_manager_t* libvlc_media_player_event_manager(libvlc_media_player_t* p_mi);
int libvlc_event_attach(libvlc_event_manager_t* p_event_manager, int i_event_type,
                        libvlc_callback_t f_callback, void* user_data);
void libvlc_event_detach(libvlc_event_manager_t* p_event_manager, int i_event_type,
                         libvlc_callback_t f_callback, void* user_data);

// --- tracks ---
int libvlc_video_get_track_count(libvlc_media_player_t* p_mi);
int libvlc_video_get_track(libvlc_media_player_t* p_mi);
int libvlc_video_set_track(libvlc_media_player_t* p_mi, int i_track);
int libvlc_audio_get_track_count(libvlc_media_player_t* p_mi);
int libvlc_audio_get_track(libvlc_media_player_t* p_mi);
int libvlc_audio_set_track(libvlc_media_player_t* p_mi, int i_track);
int libvlc_video_get_spu_count(libvlc_media_player_t* p_mi);
int libvlc_video_get_spu(libvlc_media_player_t* p_mi);
int libvlc_video_set_spu(libvlc_media_player_t* p_mi, int i_spu);
int libvlc_video_take_snapshot(libvlc_media_player_t* p_mi, unsigned num,
                               const char* psz_filepath, unsigned i_width, unsigned i_height);
libvlc_track_description_t* libvlc_audio_get_track_description(libvlc_media_player_t* p_mi);
libvlc_track_description_t* libvlc_video_get_track_description(libvlc_media_player_t* p_mi);
libvlc_track_description_t* libvlc_video_get_spu_description(libvlc_media_player_t* p_mi);
void libvlc_track_description_release(libvlc_track_description_t* p_track_description);

// --- titles / chapters ---
int libvlc_media_player_get_title_count(libvlc_media_player_t* p_mi);
int libvlc_media_player_get_title(libvlc_media_player_t* p_mi);
void libvlc_media_player_set_title(libvlc_media_player_t* p_mi, int i_title);
int libvlc_media_player_get_chapter_count(libvlc_media_player_t* p_mi);
int libvlc_media_player_get_chapter(libvlc_media_player_t* p_mi);
void libvlc_media_player_set_chapter(libvlc_media_player_t* p_mi, int i_chapter);

// --- media ---
libvlc_time_t libvlc_media_get_duration(libvlc_media_t* p_md);
int libvlc_media_is_parsed(libvlc_media_t* p_md);
int libvlc_media_get_state(libvlc_media_t* p_md);

#ifdef __cplusplus
}
#endif
