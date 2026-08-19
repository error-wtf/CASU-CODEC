// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// MPCASU main window (port of mpcasu_qt/main_window.py). Layout per
// ui-style-bible.md: Sidebar(240) | Workspace (topbar 72, stage, transport
// 66) | Playlist(310). Single-player pipeline:
//   UI -> CppPlaybackController -> PlaybackBackend -> VideoSurface.
#pragma once
#include "casu/playback/controller.hpp"
#include "casu/playback/libvlc_backend.hpp"
#include "casu/playback/state.hpp"

#include "epg.hpp"
#include "library.hpp"
#include "playlist.hpp"
#include "recording.hpp"
#include "settings.hpp"
#include "web_player_tabs.hpp"
#include "youtube_proxy.hpp"

#include <QMainWindow>
#include <QObject>
#include <QTimer>

#include <memory>

class QLabel;
class QLineEdit;
class QListWidget;
class QPushButton;
class QSlider;
class QStackedWidget;
class QTableWidget;
class QTreeWidget;
class QComboBox;
class QCheckBox;
class QSpinBox;
class QDoubleSpinBox;
class QFrame;
class QStackedLayout;

namespace casu::playback {
class CppPlaybackController;
}

namespace mpcasu {

class VideoSurface;

// Marshals libVLC event-thread callbacks onto the GUI thread via a queued
// QMetaObject::invokeMethod functor. No Q_OBJECT (the bundled Qt is Windows
// only, so this cross build has no host moc).
class BackendEventBridge {
public:
    using State = casu::playback::PlaybackState;
    explicit BackendEventBridge(QObject* context) : context_(context) {}
    void post(State s) {
        QMetaObject::invokeMethod(context_, [this, s] {
            if (on_state) on_state(s);
        }, Qt::QueuedConnection);
    }
    std::function<void(State)> on_state;

private:
    QObject* context_ = nullptr;
};

class MainWindow final : public QMainWindow {
public:
    explicit MainWindow(const QStringList& initial_files = {},
                        bool force_proxy = false, QString vout = {},
                        QString aout = {}, QWidget* parent = nullptr);
    ~MainWindow() override;

    void add_files(const QStringList& paths);
    void play_selected_path(const QString& path);

    // Wine verification helpers (--play-test): report the current backend
    // state/position without exposing the controller.
    const char* playback_state_name() const {
        return casu::playback::state_name(controller_->state());
    }
    double playback_position() const { return controller_->position(); }
    double playback_duration() const { return controller_->duration(); }
    bool has_playback_backend() const { return static_cast<bool>(backend_); }

protected:
    void dragEnterEvent(QDragEnterEvent* event) override;
    void dropEvent(QDropEvent* event) override;
    void closeEvent(QCloseEvent* event) override;
    void keyPressEvent(QKeyEvent* event) override;

private:
    void build_ui();
    void build_sidebar();
    void build_playlist_pane();
    void build_player_page();
    void build_transport();
    void build_library_page();
    void build_settings_page();
    void build_epg_page();
    void build_recording_page();
    void build_visualizer_page();
    void build_youtube_page();
    void build_web_players_page();

    void status(const QString& text);
    void toast(const QString& text);
    void navigate(const QString& page);

    void open_backend_and_play(const QString& source, const QString& title);
    void open_network_source(const QString& source, const QString& title);
    void open_web_player(const QString& provider, const QString& query = {},
                         const QString& url = {});
    void play_queue_index(int index, bool automatic);
    void stop_playback();
    void handle_end();
    void apply_backend_settings();
    void update_play_button();
    void refresh_library();
    void refresh_playlist();

    // transport
    void toggle_playback();
    void pause();
    void resume_after_seek();
    void play_next(bool automatic = false);
    void play_previous();
    void seek_to(double seconds);
    void set_volume(int value);
    void toggle_mute();
    void cycle_rate();
    void toggle_fullscreen();
    void save_snapshot();
    void cycle_repeat();
    void on_backend_state(casu::playback::PlaybackState);
    void poll();

    // playlist pane
    void choose_files();
    void add_url();
    void load_playlist_file();
    void save_playlist_file();
    void playlist_double_clicked();
    void playlist_context_menu(const QPoint& pos);
    void merge_selection_into_playlist();

    // pages
    void on_library_play();
    void on_library_add_current();
    void on_settings_save();
    void on_epg_load();
    void on_recording_toggle();
    void on_visualizer_toggle();
    void on_youtube_play();

    VideoSurface* surface_ = nullptr;
    QStackedLayout* stage_stack_ = nullptr;
    QFrame* transport_frame_ = nullptr;
    QFrame* sidebar_ = nullptr;
    BackendEventBridge* bridge_ = nullptr;
    casu::playback::CppPlaybackController* controller_ = nullptr;
    std::shared_ptr<casu::playback::PlaybackBackend> backend_;
    PlaylistModel playlist_;
    MediaLibrary* library_ = nullptr;
    SettingsStore* settings_ = nullptr;
    AppSettings app_settings_;
    YoutubeProxy* yt_proxy_ = nullptr;
    WebPlayerTabs* web_player_tabs_ = nullptr;
    RecordingController* recorder_ = nullptr;
    EpgCatalog epg_;
    QString current_source_;
    QString current_title_;
    QString output_dir_;
    QString vout_;
    QString aout_;
    bool force_proxy_ = false;
    bool paused_ = false;
    bool end_handled_ = false;
    bool advancing_ = false;
    double duration_ = 0.0;
    int volume_ = 100;
    bool muted_ = false;
    double rate_ = 1.0;
    QTimer* poll_timer_ = nullptr;
    QStackedWidget* pages_ = nullptr;
    QWidget* player_page_ = nullptr;

    // player page widgets
    QLabel* topbar_title_ = nullptr;
    QLabel* time_current_ = nullptr;
    QLabel* time_total_ = nullptr;
    QSlider* seek_slider_ = nullptr;
    QPushButton* play_btn_ = nullptr;
    QPushButton* mute_btn_ = nullptr;
    QSlider* volume_slider_ = nullptr;
    QPushButton* rate_btn_ = nullptr;
    QPushButton* repeat_btn_ = nullptr;
    QPushButton* shuffle_btn_ = nullptr;
    QPushButton* record_btn_ = nullptr;
    QPushButton* viz_btn_ = nullptr;
    QLabel* status_label_ = nullptr;
    QWidget* visualizer_ = nullptr;

    // playlist pane
    QListWidget* playlist_view_ = nullptr;

    // sidebar
    QList<QPushButton*> nav_buttons_;
    QMap<QString, QPushButton*> nav_map_;

    // library page
    QListWidget* library_view_ = nullptr;

    // settings page
    QSlider* settings_volume_ = nullptr;
    QDoubleSpinBox* settings_rate_ = nullptr;
    QCheckBox* settings_shuffle_ = nullptr;
    QComboBox* settings_repeat_ = nullptr;
    QLineEdit* settings_record_dir_ = nullptr;
    QLabel* backend_info_label_ = nullptr;

    // epg page
    QComboBox* epg_channel_ = nullptr;
    QTableWidget* epg_table_ = nullptr;

    // recording page
    QLabel* record_status_ = nullptr;
    QLineEdit* record_dir_ = nullptr;

    // youtube page
    QLineEdit* youtube_url_ = nullptr;
    QLabel* youtube_status_ = nullptr;
};

}  // namespace mpcasu
