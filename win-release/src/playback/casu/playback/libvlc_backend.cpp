// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/playback/libvlc_backend.hpp"

#include "casu/playback/controller.hpp"
#include "casu/libvlc_bind.h"
#include "casu/formats.hpp"
#include "casu/mp5.hpp"
#include "casu/native.hpp"
#include "casu/native_v2.hpp"
#include "casu/sidecar.hpp"

#include <atomic>
#include <cctype>
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <system_error>

namespace fs = std::filesystem;

// libVLC 3.0 track-description layout (opaque in the bind header; we only
// read the documented fields). Same ABI in 2.x/3.x/4.x.
struct libvlc_track_description_t_impl {
    int i_id;
    char* psz_name;
    libvlc_track_description_t* p_next;
};

// libVLC 3.0 event struct: the leading `type` int is all the state mapping
// needs; the union that follows is never touched.
struct libvlc_event_t_impl {
    int type;
    void* p_obj;
};

namespace casu::playback {
namespace {

constexpr int EVENT_OPENING = 0x102;
constexpr int EVENT_BUFFERING = 0x103;
constexpr int EVENT_PLAYING = 0x104;
constexpr int EVENT_PAUSED = 0x105;
constexpr int EVENT_STOPPED = 0x106;
constexpr int EVENT_END_REACHED = 0x109;
constexpr int EVENT_ERROR = 0x10a;

void vlc_event_callback(const libvlc_event_t* event, void* user_data) {
    auto* self = static_cast<LibVLCBackend*>(user_data);
    const auto* ev = reinterpret_cast<const libvlc_event_t_impl*>(event);
    self->handle_event(ev ? ev->type : 0);
}

std::string strip(const std::string& s) {
    std::size_t b = 0, e = s.size();
    while (b < e && std::isspace(static_cast<unsigned char>(s[b]))) ++b;
    while (e > b && std::isspace(static_cast<unsigned char>(s[e - 1]))) --e;
    return s.substr(b, e - b);
}

std::string to_utf8(const char* p) {
    return p ? std::string(p) : std::string();
}

bool is_windows_drive(const std::string& value) {
    if (value.size() < 3) return false;
    if (!std::isalpha(static_cast<unsigned char>(value[0]))) return false;
    return value[1] == ':' && (value[2] == '/' || value[2] == '\\');
}

// The Windows libVLC media_new_path requires backslash separators for
// absolute drive paths (forward slashes after the drive letter are rejected).
std::string to_native_path(std::string path) {
    for (char& c : path)
        if (c == '/') c = '\\';
    return path;
}

std::string temp_sink_path(const std::string& suffix) {
    std::error_code ec;
    fs::path dir = fs::temp_directory_path(ec);
    static std::atomic<unsigned> seq{0};
    std::string base = "mpcasu-" + std::to_string(seq.fetch_add(1)) + "-" + suffix;
    return (dir / base).string();
}

std::string extract_mp5_source(const std::string& path) {
    auto [filename, payload] = casu::mp5::extract_attachment(path);
    std::string suffix = ".bin";
    std::string::size_type dot = filename.rfind('.');
    if (dot != std::string::npos && filename.size() - dot <= 8)
        suffix = filename.substr(dot);
    std::string out = temp_sink_path(suffix);
    std::ofstream f(out, std::ios::binary);
    if (!f) throw PlaybackError("could not create temp file for MP5 extraction");
    f.write(reinterpret_cast<const char*>(payload.data()),
            static_cast<std::streamsize>(payload.size()));
    f.close();
    return out;
}

std::string extract_casunat1_source(const std::string& path) {
    casu::casunat1::Container container = casu::casunat1::read_native(path, true);
    std::string filename = "media.bin";
    if (container.manifest.is_object()) {
        const casu::JsonValue* src = container.manifest.find("source");
        if (src && src->is_object()) {
            const casu::JsonValue* fname = src->find("filename");
            if (fname && fname->is_string()) filename = fname->as_string();
        }
    }
    std::string suffix = ".bin";
    std::string::size_type dot = filename.rfind('.');
    if (dot != std::string::npos && filename.size() - dot <= 8)
        suffix = filename.substr(dot);
    std::string out = temp_sink_path(suffix);
    container.extract_payload(out);
    return out;
}

}  // namespace

LibVLCBackend::LibVLCBackend(void* hwnd, std::vector<std::string> runtime_options)
    : hwnd_(hwnd), runtime_options_(std::move(runtime_options)) {
    std::vector<const char*> argv;
    argv.push_back("mpcasu");
    argv.push_back("--no-video-title-show");
    for (const auto& opt : runtime_options_) argv.push_back(opt.c_str());
    instance_ = libvlc_new(static_cast<int>(argv.size()), argv.data());
    if (!instance_)
        throw PlaybackError("libVLC could not be initialized");
}

LibVLCBackend::~LibVLCBackend() {
    cleanup_temp_sinks();
    close();
}

bool LibVLCBackend::is_location(const std::string& value) {
    if (value.empty()) return false;
    std::string::size_type colon = value.find(':');
    if (colon == std::string::npos || colon == 0) return false;
    std::string scheme = value.substr(0, colon);
    if (is_windows_drive(value)) return false;
    if (scheme == "file") return false;
    for (char c : scheme)
        if (!std::isalpha(static_cast<unsigned char>(c)))
            return false;
    return true;
}



std::string LibVLCBackend::version_string() const {
    if (!libvlc_get_version) return {};
    const char* v = libvlc_get_version();
    return v ? std::string(v) : std::string();
}
void LibVLCBackend::cleanup_temp_sinks() {
    for (const std::string& sink : temp_sinks_) {
        std::error_code ec;
        fs::remove(sink, ec);
    }
    temp_sinks_.clear();
}

void LibVLCBackend::apply_source(const std::string& source) {
    // Previous extraction sinks are stale once the media changes.
    cleanup_temp_sinks();
    detach_events();
    if (player_) {
        libvlc_media_player_stop(player_);
        libvlc_media_player_release(player_);
        player_ = nullptr;
    }
    if (media_) {
        libvlc_media_release(media_);
        media_ = nullptr;
    }
    last_error_detail_.clear();
    play_requested_at_ = -1.0;

    if (source.rfind("file://", 0) == 0) {
        // file:// URIs were broken at the backend (VLC needs a proper
        ///C:/ form on Windows); route them through the native-path branch.
        std::string path = source.substr(7);
        if (path.rfind("localhost/", 0) == 0) path = path.substr(10);
        if (!path.empty() && path[0] != '/') path.insert(path.begin(), '/');
#ifdef _WIN32
        if (path.size() >= 3 && path[0] == '/' && path[2] == ':')
            path.erase(0, 1);  // /C:/... -> C:/...
#endif
        std::replace(path.begin(), path.end(), '/', '\\');
        media_ = libvlc_media_new_path(instance_, path.c_str());
    } else if (is_location(source)) {
        media_ = libvlc_media_new_location(instance_, source.c_str());
    } else {
        std::string native = to_native_path(source);
        media_ = libvlc_media_new_path(instance_, native.c_str());
    }
    if (!media_) {
        state_ = PlaybackState::ERROR;
        last_error_detail_ = "libVLC could not create the media object for the source";
        throw PlaybackError("libVLC could not open the media source");
    }
    // Reference SAFE_MEDIA_OPTIONS parity: some VLC 3 builds let the
    // persisted user preference override the instance argument, so the
    // safety setting is repeated as a per-media option.
    if (libvlc_media_add_option)
        libvlc_media_add_option(media_, ":avcodec-hw=none");

    player_ = libvlc_media_player_new_from_media(media_);
    if (!player_) {
        state_ = PlaybackState::ERROR;
        last_error_detail_ = "libVLC could not create the media player";
        libvlc_media_release(media_);
        media_ = nullptr;
        throw PlaybackError("libVLC could not create the media player");
    }
    // Only bind a native window when an embedded video output is used. The
    // dummy vout (headless/Wine tests) must not receive the HWND: libVLC's
    // dummy vout still blocks in stop() when given a real HWND under Wine.
    bool embedded = true;
    for (const auto& opt : runtime_options_)
        if (opt.rfind("--vout=", 0) == 0 && opt.find("dummy") != std::string::npos)
            embedded = false;
    if (hwnd_ && embedded)
        libvlc_media_player_set_hwnd(player_, hwnd_);
    attach_events();
    state_ = PlaybackState::READY;
}

void LibVLCBackend::open_source(const std::string& source) {
    if (source.empty() || source.find('\0') != std::string::npos)
        throw PlaybackError("unsupported media source");
    state_ = PlaybackState::LOADING;
    apply_source(source);
}

void LibVLCBackend::open_casu(const std::string& path) {
    if (!fs::exists(path))
        throw PlaybackError("CASU file does not exist");
    state_ = PlaybackState::LOADING;
    switch (casu::detect_casu_kind(path)) {
        case casu::CasuKind::Mp5: {
            const std::string sink = extract_mp5_source(path);
            temp_sinks_.push_back(sink);
            apply_source(sink);
            break;
        }
        case casu::CasuKind::Casunat1: {
            const std::string sink = extract_casunat1_source(path);
            temp_sinks_.push_back(sink);
            apply_source(sink);
            break;
        }
        case casu::CasuKind::Casunat2: {
            // Container integrity is still verified; native decode of the
            // enhanced payloads is a separate backend (NativeCasuBackend).
            casu::casunat2::read_native_v2(path, false);
            state_ = PlaybackState::ERROR;
            last_error_detail_ =
                "CASUNAT2 native playback requires the native decoder, "
                "which is not yet available in the Windows port";
            throw PlaybackError(last_error_detail_);
        }
        case casu::CasuKind::Sidecar: {
            std::string resolved = casu::resolve_casu_source(path);
            apply_source(resolved);
            break;
        }
        default: {
            state_ = PlaybackState::ERROR;
            last_error_detail_ = "not a recognised CASU container";
            throw PlaybackError(last_error_detail_);
        }
    }
}

void LibVLCBackend::attach_events() {
    if (!player_) return;
    event_manager_ = libvlc_media_player_event_manager(player_);
    if (!event_manager_) return;
    const int event_types[] = {EVENT_OPENING, EVENT_BUFFERING, EVENT_PLAYING,
                               EVENT_PAUSED,  EVENT_STOPPED,   EVENT_END_REACHED,
                               EVENT_ERROR};
    for (int t : event_types)
        libvlc_event_attach(event_manager_, t, vlc_event_callback, this);
}

void LibVLCBackend::detach_events() {
    if (!player_ || !event_manager_) return;
    const int event_types[] = {EVENT_OPENING, EVENT_BUFFERING, EVENT_PLAYING,
                               EVENT_PAUSED,  EVENT_STOPPED,   EVENT_END_REACHED,
                               EVENT_ERROR};
    for (int t : event_types)
        libvlc_event_detach(event_manager_, t, vlc_event_callback, this);
    event_manager_ = nullptr;
}

void LibVLCBackend::handle_event(int event_type) {
    switch (event_type) {
        case EVENT_OPENING:
        case EVENT_BUFFERING:
            state_ = PlaybackState::LOADING;
            break;
        case EVENT_PLAYING:
            state_ = PlaybackState::PLAYING;
            break;
        case EVENT_PAUSED:
            state_ = PlaybackState::PAUSED;
            break;
        case EVENT_STOPPED:
            state_ = PlaybackState::STOPPED;
            break;
        case EVENT_END_REACHED:
            state_ = PlaybackState::ENDED;
            break;
        case EVENT_ERROR:
            note_error();
            state_ = PlaybackState::ERROR;
            break;
        default:
            return;
    }
    if (on_event)
        on_event(state_);
}

void LibVLCBackend::play() {
    if (!player_)
        throw PlaybackError("no media is open");
    if (libvlc_media_player_play(player_) != 0)
        throw PlaybackError("libVLC playback could not start");
    play_requested_at_ = static_cast<double>(
        std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now().time_since_epoch())
            .count()) /
        1000.0;
    state_ = PlaybackState::PLAYING;
}

void LibVLCBackend::pause() {
    if (player_) {
        libvlc_media_player_set_pause(player_, 1);
        state_ = PlaybackState::PAUSED;
    }
}

void LibVLCBackend::resume() {
    if (player_) {
        libvlc_media_player_set_pause(player_, 0);
        state_ = PlaybackState::PLAYING;
    }
}

void LibVLCBackend::stop() {
    if (player_) libvlc_media_player_stop(player_);
    state_ = PlaybackState::STOPPED;
}

void LibVLCBackend::seek(double seconds) {
    if (player_)
        libvlc_media_player_set_time(player_,
                                     static_cast<libvlc_time_t>(seconds * 1000.0));
}

double LibVLCBackend::position() {
    if (!player_) return 0.0;
    libvlc_time_t t = libvlc_media_player_get_time(player_);
    return t > 0 ? static_cast<double>(t) / 1000.0 : 0.0;
}

double LibVLCBackend::duration() {
    if (!player_) return 0.0;
    libvlc_time_t t = libvlc_media_player_get_length(player_);
    return t > 0 ? static_cast<double>(t) / 1000.0 : 0.0;
}

PlaybackState LibVLCBackend::state() {
    if (!player_) return state_;
    int player_state = libvlc_media_player_get_state(player_);
    if (player_state == 7) {
        note_error();
        state_ = PlaybackState::ERROR;
    } else if (player_state == 6 && state_ != PlaybackState::ERROR) {
        state_ = PlaybackState::ENDED;
    }
    if (media_) {
        int media_state = libvlc_media_get_state(media_);
        if (media_state == 7) {
            note_error();
            state_ = PlaybackState::ERROR;
        } else if (media_state == 6 && state_ != PlaybackState::ERROR) {
            state_ = PlaybackState::ENDED;
        }
    }
    if (state_ == PlaybackState::PLAYING && !libvlc_media_player_is_playing(player_)) {
        double dur = duration();
        if (dur > 0.0 && position() >= dur - 0.2)
            state_ = PlaybackState::ENDED;
    }
    if (state_ == PlaybackState::ENDED && position() == 0.0 && duration() == 0.0 &&
        audio_track_count() == 0 && video_track_count() == 0 &&
        play_requested_at_ >= 0.0) {
        double now = static_cast<double>(
            std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now().time_since_epoch())
                .count()) /
                     1000.0;
        if (now - play_requested_at_ >= 0.5) {
            // VLC 3 can report Ended instead of Error for an access failure
            // (e.g. HTTP 404) that never opened a stream.
            note_error();
            state_ = PlaybackState::ERROR;
        }
    }
    return state_;
}

void LibVLCBackend::note_error() {
    if (state_ == PlaybackState::ERROR) return;
    try {
        double dur = duration();
        double pos = position();
        int a = audio_track_count();
        int v = video_track_count();
        int media_state = media_ ? libvlc_media_get_state(media_) : -1;
        last_error_detail_ = "libVLC access/demux failed · media_state=" +
                             std::to_string(media_state) + " duration=" +
                             std::to_string(static_cast<int>(dur)) +
                             "s position=" + std::to_string(static_cast<int>(pos)) +
                             "s audio_tracks=" + std::to_string(a) +
                             " video_tracks=" + std::to_string(v);
    } catch (...) {
        last_error_detail_ = "libVLC access/demux failed";
    }
}

int LibVLCBackend::set_volume(int value) {
    if (!player_) return 0;
    value = value < 0 ? 0 : (value > 200 ? 200 : value);
    if (libvlc_audio_set_volume(player_, value) != 0)
        throw PlaybackError("libVLC rejected the requested volume");
    return value;
}

int LibVLCBackend::volume() {
    if (!player_) return 0;
    int v = libvlc_audio_get_volume(player_);
    return v < 0 ? 0 : v;
}

void LibVLCBackend::set_mute(bool muted) {
    if (player_) libvlc_audio_set_mute(player_, muted ? 1 : 0);
}

bool LibVLCBackend::is_muted() {
    return player_ ? libvlc_audio_get_mute(player_) != 0 : false;
}

double LibVLCBackend::set_rate(double rate) {
    if (!player_) throw PlaybackError("no active media player");
    if (rate < 0.25) rate = 0.25;
    if (rate > 4.0) rate = 4.0;
    if (libvlc_media_player_set_rate(player_, static_cast<float>(rate)) == -1)
        throw PlaybackError("libVLC rejected playback rate");
    return static_cast<double>(libvlc_media_player_get_rate(player_));
}

double LibVLCBackend::rate() {
    return player_ ? static_cast<double>(libvlc_media_player_get_rate(player_)) : 1.0;
}

int LibVLCBackend::audio_track_count() {
    if (!player_) return 0;
    int n = libvlc_audio_get_track_count(player_);
    return n < 0 ? 0 : n;
}

int LibVLCBackend::audio_track() {
    return player_ ? libvlc_audio_get_track(player_) : -1;
}

void LibVLCBackend::set_audio_track(int track) {
    if (player_ && libvlc_audio_set_track(player_, track) != 0)
        throw PlaybackError("libVLC rejected the audio track");
}

int LibVLCBackend::video_track_count() {
    if (!player_) return 0;
    int n = libvlc_video_get_track_count(player_);
    return n < 0 ? 0 : n;
}

int LibVLCBackend::video_track() {
    return player_ ? libvlc_video_get_track(player_) : -1;
}

void LibVLCBackend::set_video_track(int track) {
    if (player_ && libvlc_video_set_track(player_, track) != 0)
        throw PlaybackError("libVLC rejected the video track");
}

int LibVLCBackend::subtitle_track_count() {
    if (!player_) return 0;
    int n = libvlc_video_get_spu_count(player_);
    return n < 0 ? 0 : n;
}

int LibVLCBackend::subtitle_track() {
    return player_ ? libvlc_video_get_spu(player_) : -1;
}

void LibVLCBackend::set_subtitle_track(int track) {
    if (player_ && libvlc_video_set_spu(player_, track) != 0)
        throw PlaybackError("libVLC rejected the subtitle track");
}

namespace {
using TrackGetter = libvlc_track_description_t* (*)(libvlc_media_player_t*);

std::vector<TrackInfo> collect_tracks(libvlc_media_player_t* player, TrackGetter getter) {
    std::vector<TrackInfo> out;
    if (!player) return out;
    libvlc_track_description_t* head = getter(player);
    if (!head) return out;
    auto* cur = reinterpret_cast<libvlc_track_description_t_impl*>(head);
    int seen = 0;
    while (cur && seen < 256) {
        // libVLC commonly prepends a synthetic -1 "Disable" entry; it is not
        // a media track but must not terminate traversal.
        if (cur->i_id >= 0)
            out.push_back(TrackInfo{cur->i_id, to_utf8(cur->psz_name)});
        cur = reinterpret_cast<libvlc_track_description_t_impl*>(cur->p_next);
        ++seen;
    }
    libvlc_track_description_release(head);
    return out;
}
}  // namespace

std::vector<TrackInfo> LibVLCBackend::audio_track_descriptions() {
    return collect_tracks(player_, libvlc_audio_get_track_description);
}

std::vector<TrackInfo> LibVLCBackend::video_track_descriptions() {
    return collect_tracks(player_, libvlc_video_get_track_description);
}

std::vector<TrackInfo> LibVLCBackend::subtitle_track_descriptions() {
    return collect_tracks(player_, libvlc_video_get_spu_description);
}

std::vector<ChapterInfo> LibVLCBackend::chapters() {
    std::vector<ChapterInfo> out;
    if (!player_) return out;
    int count = libvlc_media_player_get_chapter_count(player_);
    if (count < 0) count = 0;
    for (int i = 0; i < count && i < 256; ++i)
        out.push_back(ChapterInfo{i, "Chapter " + std::to_string(i + 1)});
    return out;
}

void LibVLCBackend::set_chapter(int index) {
    if (!player_) throw PlaybackError("no active media player");
    libvlc_media_player_set_chapter(player_, index);
}

void LibVLCBackend::next_frame() {
    if (!player_) throw PlaybackError("no active media player");
    libvlc_media_player_next_frame(player_);
}

void LibVLCBackend::set_audio_delay(double milliseconds) {
    if (!player_) throw PlaybackError("no active media player");
    // Linux parity (mpcasu_backend.py): libVLC delay APIs expect MICROSECONDS,
    // the UI layer works in milliseconds.
    const long long microseconds = static_cast<long long>(milliseconds * 1000.0);
    if (libvlc_audio_set_delay(player_, static_cast<int>(microseconds)) != 0)
        throw PlaybackError("libVLC rejected the audio delay");
}

void LibVLCBackend::set_subtitle_delay(double milliseconds) {
    if (!player_) throw PlaybackError("no active media player");
    // Linux parity: milliseconds -> microseconds for libVLC.
    const long long microseconds = static_cast<long long>(milliseconds * 1000.0);
    if (libvlc_video_set_spu_delay(player_, static_cast<int>(microseconds)) != 0)
        throw PlaybackError("libVLC rejected the subtitle delay");
}

bool LibVLCBackend::load_subtitle_file(const std::string& path) {
    if (!player_) throw PlaybackError("no active media player");
    // VLC 3 add_slave takes a URI; convert a plain path to a file:// URI.
    std::string uri = path;
    if (uri.find("://") == std::string::npos) {
        uri = "file://";
        for (char c : path) {
            if (c == '\\') uri += '/';
            else uri += c;
        }
    }
    return libvlc_media_player_add_slave(
               player_, libvlc_media_slave_type_subtitle, uri.c_str(), true) == 0;
}

std::vector<TrackInfo> LibVLCBackend::audio_devices() {
    std::vector<TrackInfo> out;
    if (!instance_) return out;
    libvlc_audio_output_device_t* list =
        libvlc_audio_output_device_list_get(instance_, nullptr);
    for (libvlc_audio_output_device_t* d = list; d; d = d->p_next) {
        if (!d->psz_device) continue;
        out.push_back(TrackInfo{0, d->psz_device});
    }
    libvlc_audio_output_device_list_release(list);
    return out;
}

void LibVLCBackend::set_audio_device(const std::string& device) {
    if (!player_) throw PlaybackError("no active media player");
    libvlc_audio_output_device_set(player_, nullptr, device.c_str());
}

void LibVLCBackend::snapshot(const std::string& path) {
    if (!player_) throw PlaybackError("no active media player");
    if (path.size() < 4) throw PlaybackError("video snapshots must use a .png destination");
    std::string lower = path.substr(path.size() - 4);
    for (char& c : lower) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    if (lower != ".png") throw PlaybackError("video snapshots must use a .png destination");
    std::error_code ec;
    fs::create_directories(fs::path(path).parent_path(), ec);
    if (libvlc_video_take_snapshot(player_, 0, path.c_str(), 0, 0) != 0)
        throw PlaybackError("libVLC could not capture the current video frame");
}

std::string LibVLCBackend::last_error() {
    return last_error_detail_.empty() ? "libVLC reported an access/demux failure"
                                      : last_error_detail_;
}

bool LibVLCBackend::is_actively_playing() {
    return player_ ? libvlc_media_player_is_playing(player_) != 0 : false;
}

void LibVLCBackend::close_media() {
    detach_events();
    if (player_) {
        libvlc_media_player_stop(player_);
        libvlc_media_player_release(player_);
        player_ = nullptr;
    }
    if (media_) {
        libvlc_media_release(media_);
        media_ = nullptr;
    }
}
void LibVLCBackend::close() {
    close_media();
    if (instance_) {
        libvlc_release(instance_);
        instance_ = nullptr;
    }
    state_ = PlaybackState::EMPTY;
}
std::string LibVLCBackend::backend_version() const {
    const char* v = libvlc_get_version();
    return to_utf8(v);
}

}  // namespace casu::playback
