// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "main_window.hpp"

#include "casu/codec/tools.hpp"
#include "casu/formats.hpp"
#include "casu/network/url.hpp"
#include "casu/network/ytdlp.hpp"
#include "casu/web/webproviders.hpp"

#include "theme.hpp"
#include "video_surface.hpp"
#include "visualizer.hpp"

#include <QCheckBox>
#include <QCloseEvent>
#include <QComboBox>
#include <QDateTime>
#include <QDir>
#include <QDoubleSpinBox>
#include <QDragEnterEvent>
#include <QDropEvent>
#include <QFileDialog>
#include <QFileInfo>
#include <QFrame>
#include <QGridLayout>
#include <QGuiApplication>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QInputDialog>
#include <QKeyEvent>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMenu>
#include <QMessageBox>
#include <QMimeData>
#include <QPushButton>
#include <QScreen>
#include <QSlider>
#include <QSpinBox>
#include <QStackedLayout>
#include <QStackedWidget>
#include <QStatusBar>
#include <QTableWidget>
#include <QTabWidget>
#include <QTime>
#include <QTimer>
#include <QVBoxLayout>

#include <algorithm>
#include <cstdlib>
#include <set>

namespace mpcasu {
namespace {

const std::set<QString> kAudioExtensions = {
    "mp3", "wav", "flac", "ogg", "oga", "m4a", "aac", "opus", "wma", "caf", "mp2", "alac",
};

bool is_audio_ext(const QString& path) {
    QString ext = QFileInfo(path).suffix().toLower();
    return kAudioExtensions.count(ext) > 0;
}

bool is_casu_container(const QString& path) {
    QString ext = QFileInfo(path).suffix().toLower();
    return ext == "casu" || ext == "mp5";
}

bool is_network_like(const QString& value) {
    return value.contains("://") || value.startsWith("spotify:") || value.startsWith("ytdl:");
}

QString default_output_dir() {
    QString d = QDir::homePath() + "/Videos/MPCASU";
    if (QDir().mkpath(d)) return d;
    return QDir::currentPath();
}

}  // namespace

MainWindow::MainWindow(const QStringList& initial_files, bool force_proxy,
                       QString vout, QString aout, QWidget* parent)
    : QMainWindow(parent), force_proxy_(force_proxy), vout_(std::move(vout)),
      aout_(std::move(aout)) {
    setWindowTitle(QStringLiteral("MPCASU Media Player"));
    const QScreen* screen = QGuiApplication::primaryScreen();
    const QRect avail = screen ? screen->availableGeometry() : QRect(0, 0, 1600, 1000);
    setMinimumSize(qMin(980, avail.width()), qMin(620, avail.height()));
    resize(qMin(1360, avail.width() - 24), qMin(820, avail.height() - 24));
    setAcceptDrops(true);
    setObjectName("Root");
    setStyleSheet(application_stylesheet());

    bridge_ = new BackendEventBridge(this);
    controller_ = new casu::playback::CppPlaybackController();
    yt_proxy_ = new YoutubeProxy(this);
    recorder_ = new RecordingController(this);
    library_ = new MediaLibrary(app_config_dir() + "/library.json");
    library_->load();
    settings_ = new SettingsStore(app_config_dir() + "/settings.json");
    app_settings_ = settings_->load();
    volume_ = app_settings_.volume;
    muted_ = app_settings_.muted;
    rate_ = app_settings_.rate;
    playlist_.shuffle = app_settings_.shuffle;
    playlist_.repeat = app_settings_.repeat == "one"
                           ? PlaylistModel::RepeatMode::One
                           : (app_settings_.repeat == "all"
                                  ? PlaylistModel::RepeatMode::All
                                  : PlaylistModel::RepeatMode::Off);
    output_dir_ = app_settings_.record_dir.isEmpty() ? default_output_dir()
                                                     : app_settings_.record_dir;

    build_ui();

    surface_->on_double_click = [this] { toggle_fullscreen(); };
    surface_->on_click = [this] { toggle_playback(); };
    bridge_->on_state = [this](casu::playback::PlaybackState s) {
        on_backend_state(s);
    };
    recorder_->on_state_changed = [this] {
        const char* label = "Idle";
        switch (recorder_->state()) {
            case RecordingController::State::Starting: label = "Starting…"; break;
            case RecordingController::State::Recording: label = "Recording…"; break;
            case RecordingController::State::Stopping: label = "Stopping…"; break;
            case RecordingController::State::Failed: label = "Failed"; break;
            default: break;
        }
        record_status_->setText(QStringLiteral("Recording: %1").arg(label));
        record_btn_->setChecked(recorder_->is_recording());
    };
    recorder_->on_finished = [this](const QString& out, bool ok, const QString& detail) {
        toast(ok ? QStringLiteral("Recording saved: %1").arg(out)
                 : QStringLiteral("Recording failed: %1").arg(detail));
    };

    poll_timer_ = new QTimer(this);
    poll_timer_->setInterval(200);
    connect(poll_timer_, &QTimer::timeout, this, &MainWindow::poll);
    poll_timer_->start();

    connect(seek_slider_, &QSlider::sliderPressed, this, [this] {
        pause();  // freeze UI position while dragging (kept paused until release)
    });
    connect(seek_slider_, &QSlider::sliderReleased, this, [this] {
        seek_to(seek_slider_->value() / 1000.0);
        resume_after_seek();
    });

    if (!initial_files.isEmpty()) {
        add_files(initial_files);
        QTimer::singleShot(300, this, [this] { play_queue_index(playlist_.current_index() < 0 ? 0 : playlist_.current_index(), false); });
    }
}

MainWindow::~MainWindow() {
    stop_playback();
    if (controller_) delete controller_;
    delete bridge_;
    delete library_;
    delete settings_;
}

// ------------------------------------------------------------------ UI

void MainWindow::build_ui() {
    auto* central = new QWidget(this);
    setCentralWidget(central);
    auto* main_layout = new QHBoxLayout(central);
    main_layout->setContentsMargins(0, 0, 0, 0);
    main_layout->setSpacing(0);

    build_sidebar();
    main_layout->addWidget(sidebar_);

    pages_ = new QStackedWidget(this);
    build_player_page();
    build_library_page();
    build_settings_page();
    build_epg_page();
    build_recording_page();
    build_visualizer_page();
    build_youtube_page();
    build_web_players_page();
    main_layout->addWidget(pages_, 1);

    build_playlist_pane();
    main_layout->addWidget(playlist_view_->parentWidget());

    status_label_ = new QLabel(QStringLiteral("Ready"), this);
    status_label_->setObjectName("StatusBar");
    statusBar()->addWidget(status_label_);
    statusBar()->setSizeGripEnabled(false);
    statusBar()->setStyleSheet(QStringLiteral("background-color: %1; border-top: 1px solid %2; color: %3;")
                                   .arg(mpcasu::palette().panel, mpcasu::palette().line, mpcasu::palette().muted));}

void MainWindow::build_sidebar() {
    sidebar_ = new QFrame(this);
    sidebar_->setObjectName("Sidebar");
    sidebar_->setFixedWidth(metrics().sidebar_width);
    auto* layout = new QVBoxLayout(sidebar_);
    layout->setContentsMargins(12, 16, 12, 12);
    layout->setSpacing(4);

    auto* logo = new QLabel(QStringLiteral("MPCASU"), sidebar_);
    logo->setObjectName("NowPlayingTitle");
    layout->addWidget(logo);
    auto* sub = new QLabel(QStringLiteral("Media Player · Windows port"), sidebar_);
    sub->setObjectName("NowPlayingMeta");
    layout->addWidget(sub);
    layout->addSpacing(16);

    const QStringList groups = {"NOW PLAYING", "LIBRARY", "YOUTUBE", "EPG",
                                "VISUALIZER", "RECORDING", "SETTINGS", "WEB PLAYERS"};
    for (const QString& name : groups) {
        auto* btn = new QPushButton(name, sidebar_);
        btn->setObjectName("NavButton");
        btn->setCheckable(true);
        btn->setToolTip(name);
        btn->setCursor(Qt::PointingHandCursor);
        layout->addWidget(btn);
        nav_buttons_.append(btn);
        nav_map_[name] = btn;
        connect(btn, &QPushButton::clicked, this,
                [this, name] { navigate(name); });
    }
    layout->addStretch();
    auto* backend = new QLabel(QStringLiteral("libVLC backend"), sidebar_);
    backend->setObjectName("NowPlayingMeta");
    layout->addWidget(backend);
}

void MainWindow::build_player_page() {
    player_page_ = new QWidget(this);
    auto* col = new QVBoxLayout(player_page_);
    col->setContentsMargins(0, 0, 0, 0);
    col->setSpacing(0);

    // TopBar: NOW PLAYING is a fixed heading; the dynamic title is separate.
    auto* topbar = new QFrame(player_page_);
    topbar->setObjectName("TopBar");
    topbar->setFixedHeight(metrics().topbar_height);
    auto* tb = new QHBoxLayout(topbar);
    tb->setContentsMargins(12, 0, 12, 0);
    tb->setSpacing(8);
    auto* heading = new QLabel(QStringLiteral("NOW PLAYING"), topbar);
    heading->setObjectName("NowPlayingTitle");
    tb->addWidget(heading);
    topbar_title_ = new QLabel(QStringLiteral("No media loaded"), topbar);
    topbar_title_->setObjectName("NowPlayingMeta");
    topbar_title_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    tb->addWidget(topbar_title_, 1);
    tb->addStretch();
    col->addWidget(topbar);

    // Stage: video surface + visualizer switch.
    auto* stage = new QWidget(player_page_);
    stage_stack_ = new QStackedLayout(stage);
    stage_stack_->setContentsMargins(0, 0, 0, 0);
    surface_ = new VideoSurface(stage);
    visualizer_ = new VisualizerWidget(stage);
    stage_stack_->addWidget(surface_);
    stage_stack_->addWidget(visualizer_);
    col->addWidget(stage, 1);

    build_transport();
    col->addWidget(transport_frame_);
    pages_->addWidget(player_page_);
}

// ------------------------------------------------------------------ transport

namespace {
QPushButton* make_transport_button(const QString& text, QWidget* parent, const QString& tooltip) {
    auto* b = new QPushButton(text, parent);
    b->setObjectName("TransportButton");
    b->setToolTip(tooltip);
    return b;
}
}  // namespace

void MainWindow::build_transport() {
    auto* frame = new QFrame(player_page_);
    frame->setObjectName("Panel");
    auto* layout = new QVBoxLayout(frame);
    layout->setContentsMargins(14, 6, 14, 8);
    layout->setSpacing(4);

    seek_slider_ = new QSlider(Qt::Horizontal, frame);
    seek_slider_->setRange(0, 0);
    seek_slider_->setCursor(Qt::PointingHandCursor);
    layout->addWidget(seek_slider_);

    auto* time_row = new QHBoxLayout();
    time_current_ = new QLabel(QStringLiteral("00:00"), frame);
    time_current_->setObjectName("TimeLabel");
    time_total_ = new QLabel(QStringLiteral("00:00"), frame);
    time_total_->setObjectName("TimeLabel");
    time_row->addWidget(time_current_);
    time_row->addStretch();
    time_row->addWidget(time_total_);
    layout->addLayout(time_row);

    auto* controls = new QHBoxLayout();
    controls->setSpacing(6);

    shuffle_btn_ = make_transport_button(QStringLiteral("⤨"), frame, QStringLiteral("Shuffle"));
    shuffle_btn_->setCheckable(true);
    shuffle_btn_->setChecked(playlist_.shuffle);
    connect(shuffle_btn_, &QPushButton::toggled, this, [this](bool on) {
        playlist_.shuffle = on;
        app_settings_.shuffle = on;
        settings_->save(app_settings_);
    });
    controls->addWidget(shuffle_btn_);

    auto* prev_btn = make_transport_button(QStringLiteral("«"), frame, QStringLiteral("Previous"));
    connect(prev_btn, &QPushButton::clicked, this, &MainWindow::play_previous);
    controls->addWidget(prev_btn);

    play_btn_ = make_transport_button(QStringLiteral("▶"), frame, QStringLiteral("Play / Pause"));
    play_btn_->setObjectName("PlayButton");
    play_btn_->setFixedSize(metrics().play_button, metrics().play_button);
    connect(play_btn_, &QPushButton::clicked, this, &MainWindow::toggle_playback);
    controls->addWidget(play_btn_);

    auto* next_btn = make_transport_button(QStringLiteral("»"), frame, QStringLiteral("Next"));
    connect(next_btn, &QPushButton::clicked, this, [this] { play_next(false); });
    controls->addWidget(next_btn);

    repeat_btn_ = make_transport_button(
        QStringLiteral("↻"), frame, QStringLiteral("Repeat off / all / one"));
    connect(repeat_btn_, &QPushButton::clicked, this, &MainWindow::cycle_repeat);
    controls->addWidget(repeat_btn_);

    auto* snapshot_btn = make_transport_button(QStringLiteral("▧"), frame, QStringLiteral("Snapshot"));
    connect(snapshot_btn, &QPushButton::clicked, this, &MainWindow::save_snapshot);
    controls->addWidget(snapshot_btn);

    rate_btn_ = make_transport_button(QStringLiteral("1×"), frame, QStringLiteral("Playback speed"));
    connect(rate_btn_, &QPushButton::clicked, this, &MainWindow::cycle_rate);
    controls->addWidget(rate_btn_);

    viz_btn_ = make_transport_button(QStringLiteral("〰"), frame, QStringLiteral("Visualizer"));
    viz_btn_->setCheckable(true);
    connect(viz_btn_, &QPushButton::clicked, this, &MainWindow::on_visualizer_toggle);
    controls->addWidget(viz_btn_);

    record_btn_ = make_transport_button(QStringLiteral("●"), frame, QStringLiteral("Record"));
    record_btn_->setCheckable(true);
    connect(record_btn_, &QPushButton::clicked, this, &MainWindow::on_recording_toggle);
    controls->addWidget(record_btn_);

    controls->addStretch();

    mute_btn_ = new QPushButton(muted_ ? QStringLiteral("×") : QStringLiteral("♪"), frame);
    mute_btn_->setObjectName("IconButton");
    mute_btn_->setFixedSize(32, 32);
    mute_btn_->setToolTip(QStringLiteral("Mute / Unmute"));
    connect(mute_btn_, &QPushButton::clicked, this, &MainWindow::toggle_mute);
    controls->addWidget(mute_btn_);

    volume_slider_ = new QSlider(Qt::Horizontal, frame);
    volume_slider_->setObjectName("VolumeSlider");
    volume_slider_->setRange(0, 200);
    volume_slider_->setValue(volume_);
    volume_slider_->setFixedWidth(100);
    connect(volume_slider_, &QSlider::valueChanged, this, &MainWindow::set_volume);
    controls->addWidget(volume_slider_);

    auto* fullscreen_btn = make_transport_button(QStringLiteral("□"), frame, QStringLiteral("Fullscreen (F)"));
    connect(fullscreen_btn, &QPushButton::clicked, this, &MainWindow::toggle_fullscreen);
    controls->addWidget(fullscreen_btn);

    auto* more_btn = make_transport_button(QStringLiteral("⋯"), frame, QStringLiteral("More controls"));
    auto* more_menu = new QMenu(frame);
    more_menu->addAction(QStringLiteral("■ Stop"), this, &MainWindow::stop_playback);
    more_menu->addAction(QStringLiteral("‹ Rewind 10s"), this, [this] { seek_to(qMax(0.0, controller_->position() - 10.0)); });
    more_menu->addAction(QStringLiteral("› Forward 10s"), this, [this] { seek_to(controller_->position() + 10.0); });
    more_menu->addAction(QStringLiteral("Open file…"), this, &MainWindow::choose_files);
    more_menu->addAction(QStringLiteral("Add URL…"), this, &MainWindow::add_url);
    more_btn->setMenu(more_menu);
    controls->addWidget(more_btn);

    layout->addLayout(controls);
    frame->setObjectName("Panel");
    transport_frame_ = frame;
}

// ------------------------------------------------------------------ playlist pane

void MainWindow::build_playlist_pane() {
    auto* pane = new QFrame(this);
    pane->setObjectName("PlaylistPane");
    pane->setFixedWidth(metrics().right_panel_width);
    auto* layout = new QVBoxLayout(pane);
    layout->setContentsMargins(10, 12, 10, 10);
    layout->setSpacing(6);

    auto* title = new QLabel(QStringLiteral("QUEUE"), pane);
    title->setObjectName("NowPlayingTitle");
    layout->addWidget(title);

    auto* buttons = new QHBoxLayout();
    auto* choose_btn = new QPushButton(QStringLiteral("Choose files"), pane);
    choose_btn->setObjectName("IconButton");
    connect(choose_btn, &QPushButton::clicked, this, &MainWindow::choose_files);
    buttons->addWidget(choose_btn);
    auto* url_btn = new QPushButton(QStringLiteral("Add URL"), pane);
    url_btn->setObjectName("IconButton");
    connect(url_btn, &QPushButton::clicked, this, &MainWindow::add_url);
    buttons->addWidget(url_btn);
    layout->addLayout(buttons);

    playlist_view_ = new QListWidget(pane);
    playlist_view_->setSelectionMode(QAbstractItemView::ExtendedSelection);
    playlist_view_->setContextMenuPolicy(Qt::CustomContextMenu);
    connect(playlist_view_, &QListWidget::itemDoubleClicked, this,
            &MainWindow::playlist_double_clicked);
    connect(playlist_view_, &QListWidget::customContextMenuRequested, this,
            &MainWindow::playlist_context_menu);
    layout->addWidget(playlist_view_, 1);

    auto* tools = new QHBoxLayout();
    auto* up_btn = new QPushButton(QStringLiteral("↑"), pane);
    auto* down_btn = new QPushButton(QStringLiteral("↓"), pane);
    auto* remove_btn = new QPushButton(QStringLiteral("×"), pane);
    auto* load_btn = new QPushButton(QStringLiteral("Load"), pane);
    auto* save_btn = new QPushButton(QStringLiteral("Save"), pane);
    for (auto* b : {up_btn, down_btn, remove_btn, load_btn, save_btn}) {
        b->setObjectName("IconButton");
        tools->addWidget(b);
    }
    connect(up_btn, &QPushButton::clicked, this, [this] {
        int row = playlist_view_->currentRow();
        if (row > 0) { playlist_.move(row, row - 1); refresh_playlist(); playlist_view_->setCurrentRow(row - 1); }
    });
    connect(down_btn, &QPushButton::clicked, this, [this] {
        int row = playlist_view_->currentRow();
        if (row >= 0 && row + 1 < playlist_.size()) { playlist_.move(row, row + 1); refresh_playlist(); playlist_view_->setCurrentRow(row + 1); }
    });
    connect(remove_btn, &QPushButton::clicked, this, [this] {
        int row = playlist_view_->currentRow();
        if (row >= 0) { playlist_.remove(row); refresh_playlist(); }
    });
    connect(load_btn, &QPushButton::clicked, this, &MainWindow::load_playlist_file);
    connect(save_btn, &QPushButton::clicked, this, &MainWindow::save_playlist_file);
    layout->addLayout(tools);
}

// ------------------------------------------------------------------ other pages

void MainWindow::build_library_page() {
    auto* page = new QWidget(this);
    auto* layout = new QVBoxLayout(page);
    layout->setContentsMargins(20, 20, 20, 20);
    layout->setSpacing(10);
    auto* title = new QLabel(QStringLiteral("LIBRARY"), page);
    title->setObjectName("NowPlayingTitle");
    layout->addWidget(title);
    auto* hint = new QLabel(QStringLiteral("Saved media (JSON store). Add the current item or play a saved entry."), page);
    hint->setObjectName("NowPlayingMeta");
    layout->addWidget(hint);

    library_view_ = new QListWidget(page);
    layout->addWidget(library_view_, 1);

    auto* buttons = new QHBoxLayout();
    auto* play_btn = new QPushButton(QStringLiteral("▶ Play selected"), page);
    play_btn->setObjectName("IconButton");
    connect(play_btn, &QPushButton::clicked, this, &MainWindow::on_library_play);
    buttons->addWidget(play_btn);
    auto* add_btn = new QPushButton(QStringLiteral("＋ Add current"), page);
    add_btn->setObjectName("IconButton");
    connect(add_btn, &QPushButton::clicked, this, &MainWindow::on_library_add_current);
    buttons->addWidget(add_btn);
    auto* del_btn = new QPushButton(QStringLiteral("× Remove"), page);
    del_btn->setObjectName("IconButton");
    connect(del_btn, &QPushButton::clicked, this, [this] {
        int row = library_view_->currentRow();
        if (row >= 0) { library_->remove(row); refresh_library(); }
    });
    buttons->addWidget(del_btn);
    layout->addLayout(buttons);
    refresh_library();
    pages_->addWidget(page);
}

void MainWindow::build_settings_page() {
    auto* page = new QWidget(this);
    auto* layout = new QVBoxLayout(page);
    layout->setContentsMargins(24, 24, 24, 24);
    layout->setSpacing(12);
    auto* title = new QLabel(QStringLiteral("SETTINGS"), page);
    title->setObjectName("NowPlayingTitle");
    layout->addWidget(title);

    auto* grid = new QGridLayout();
    grid->setHorizontalSpacing(12);
    grid->setVerticalSpacing(8);

    grid->addWidget(new QLabel(QStringLiteral("Volume"), page), 0, 0);
    settings_volume_ = new QSlider(Qt::Horizontal, page);
    settings_volume_->setRange(0, 200);
    settings_volume_->setValue(volume_);
    grid->addWidget(settings_volume_, 0, 1);

    grid->addWidget(new QLabel(QStringLiteral("Rate"), page), 1, 0);
    settings_rate_ = new QDoubleSpinBox(page);
    settings_rate_->setRange(0.25, 4.0);
    settings_rate_->setSingleStep(0.25);
    settings_rate_->setValue(rate_);
    grid->addWidget(settings_rate_, 1, 1);

    grid->addWidget(new QLabel(QStringLiteral("Shuffle"), page), 2, 0);
    settings_shuffle_ = new QCheckBox(page);
    settings_shuffle_->setChecked(playlist_.shuffle);
    grid->addWidget(settings_shuffle_, 2, 1);

    grid->addWidget(new QLabel(QStringLiteral("Repeat"), page), 3, 0);
    settings_repeat_ = new QComboBox(page);
    settings_repeat_->addItems({"off", "all", "one"});
    settings_repeat_->setCurrentText(app_settings_.repeat);
    grid->addWidget(settings_repeat_, 3, 1);

    grid->addWidget(new QLabel(QStringLiteral("Record dir"), page), 4, 0);
    settings_record_dir_ = new QLineEdit(output_dir_, page);
    grid->addWidget(settings_record_dir_, 4, 1);

    layout->addLayout(grid);

    auto* info = new QLabel(page);
    info->setObjectName("NowPlayingMeta");
    info->setWordWrap(true);
    info->setText(QStringLiteral("Backend: in-process libVLC 3.0 (no external player). "
                                "Settings are stored in config/settings.json."));
    layout->addWidget(info);
    backend_info_label_ = info;

    auto* save_btn = new QPushButton(QStringLiteral("Save settings"), page);
    save_btn->setObjectName("PlayButton");
    connect(save_btn, &QPushButton::clicked, this, &MainWindow::on_settings_save);
    layout->addWidget(save_btn, 0, Qt::AlignLeft);
    layout->addStretch();
    pages_->addWidget(page);
}

void MainWindow::build_epg_page() {
    auto* page = new QWidget(this);
    auto* layout = new QVBoxLayout(page);
    layout->setContentsMargins(20, 20, 20, 20);
    layout->setSpacing(10);
    auto* title = new QLabel(QStringLiteral("EPG / IPTV"), page);
    title->setObjectName("NowPlayingTitle");
    layout->addWidget(title);

    auto* row = new QHBoxLayout();
    auto* load_btn = new QPushButton(QStringLiteral("Load XMLTV file…"), page);
    load_btn->setObjectName("IconButton");
    connect(load_btn, &QPushButton::clicked, this, &MainWindow::on_epg_load);
    row->addWidget(load_btn);
    epg_channel_ = new QComboBox(page);
    epg_channel_->setMinimumWidth(220);
    connect(epg_channel_, &QComboBox::currentTextChanged, this, [this] {
        if (!epg_table_) return;
        QString channel = epg_channel_->currentData().toString();
        qint64 now = QDateTime::currentMSecsSinceEpoch();
        QVector<EpgProgram> picks = now_and_next(epg_, channel, now);
        epg_table_->setRowCount(picks.size());
        for (int i = 0; i < picks.size(); ++i) {
            epg_table_->setItem(i, 0, new QTableWidgetItem(
                QDateTime::fromMSecsSinceEpoch(picks[i].start_ms).toString("HH:mm")));
            epg_table_->setItem(i, 1, new QTableWidgetItem(picks[i].title));
            epg_table_->setItem(i, 2, new QTableWidgetItem(picks[i].subtitle));
        }
    });
    row->addWidget(epg_channel_, 1);
    layout->addLayout(row);

    epg_table_ = new QTableWidget(0, 3, page);
    epg_table_->setHorizontalHeaderLabels({"Start", "Title", "Sub-title"});
    epg_table_->horizontalHeader()->setStretchLastSection(true);
    layout->addWidget(epg_table_, 1);
    auto* hint = new QLabel(QStringLiteral("Load an XMLTV (.xml) file to browse now/next listings per channel."), page);
    hint->setObjectName("NowPlayingMeta");
    layout->addWidget(hint);
    pages_->addWidget(page);
}

void MainWindow::build_recording_page() {
    auto* page = new QWidget(this);
    auto* layout = new QVBoxLayout(page);
    layout->setContentsMargins(24, 24, 24, 24);
    layout->setSpacing(12);
    auto* title = new QLabel(QStringLiteral("RECORDING"), page);
    title->setObjectName("NowPlayingTitle");
    layout->addWidget(title);

    auto* hint = new QLabel(QStringLiteral("Records the current source with ffmpeg "
                                           "(-c copy) into the output directory."), page);
    hint->setObjectName("NowPlayingMeta");
    hint->setWordWrap(true);
    layout->addWidget(hint);

    auto* row = new QHBoxLayout();
    row->addWidget(new QLabel(QStringLiteral("Output dir"), page));
    record_dir_ = new QLineEdit(output_dir_, page);
    row->addWidget(record_dir_, 1);
    auto* browse = new QPushButton(QStringLiteral("…"), page);
    browse->setObjectName("IconButton");
    connect(browse, &QPushButton::clicked, this, [this] {
        QString dir = QFileDialog::getExistingDirectory(this, QStringLiteral("Recording folder"), output_dir_);
        if (!dir.isEmpty()) { record_dir_->setText(dir); output_dir_ = dir; }
    });
    row->addWidget(browse);
    layout->addLayout(row);

    record_status_ = new QLabel(QStringLiteral("Recording: Idle"), page);
    record_status_->setObjectName("NowPlayingMeta");
    layout->addWidget(record_status_);

    auto* toggle = new QPushButton(QStringLiteral("Start / Stop recording"), page);
    toggle->setObjectName("PlayButton");
    connect(toggle, &QPushButton::clicked, this, &MainWindow::on_recording_toggle);
    layout->addWidget(toggle, 0, Qt::AlignLeft);
    layout->addStretch();
    pages_->addWidget(page);
}

void MainWindow::build_visualizer_page() {
    auto* page = new QWidget(this);
    auto* layout = new QVBoxLayout(page);
    layout->setContentsMargins(20, 20, 20, 20);
    layout->setSpacing(10);
    auto* title = new QLabel(QStringLiteral("VISUALIZER"), page);
    title->setObjectName("NowPlayingTitle");
    layout->addWidget(title);
    auto* hint = new QLabel(QStringLiteral("Decorative spectrum (libVLC owns the audio output, so "
                                           "a real FFT needs a native audio sink)."), page);
    hint->setObjectName("NowPlayingMeta");
    hint->setWordWrap(true);
    layout->addWidget(hint);
    auto* page_viz = new VisualizerWidget(page);
    page_viz->set_playing(false);
    layout->addWidget(page_viz, 1);
    pages_->addWidget(page);
}

void MainWindow::build_youtube_page() {
    auto* page = new QWidget(this);
    auto* layout = new QVBoxLayout(page);
    layout->setContentsMargins(20, 20, 20, 20);
    layout->setSpacing(12);
    auto* title = new QLabel(QStringLiteral("YOUTUBE / NETWORK"), page);
    title->setObjectName("NowPlayingTitle");
    layout->addWidget(title);

    auto* hint = new QLabel(QStringLiteral(
        "Enter a YouTube URL (resolved via yt-dlp, then streamed through the "
        "loopback Range/206 transport) or an existing local file path to test "
        "the loopback transport offline."), page);
    hint->setObjectName("NowPlayingMeta");
    hint->setWordWrap(true);
    layout->addWidget(hint);

    youtube_url_ = new QLineEdit(page);
    youtube_url_->setPlaceholderText(QStringLiteral("https://www.youtube.com/watch?v=…  or  C:\\media\\clip.mp4"));
    layout->addWidget(youtube_url_);

    auto* row = new QHBoxLayout();
    auto* play = new QPushButton(QStringLiteral("▶ Play via loopback transport"), page);
    play->setObjectName("PlayButton");
    connect(play, &QPushButton::clicked, this, &MainWindow::on_youtube_play);
    row->addWidget(play);
    layout->addLayout(row);

    youtube_status_ = new QLabel(QStringLiteral("Idle"), page);
    youtube_status_->setObjectName("NowPlayingMeta");
    youtube_status_->setWordWrap(true);
    layout->addWidget(youtube_status_);
    layout->addStretch();
    pages_->addWidget(page);
}

void MainWindow::build_web_players_page() {
    auto* page = new QWidget(this);
    auto* layout = new QVBoxLayout(page);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);
    web_player_tabs_ = new WebPlayerTabs(page);
    layout->addWidget(web_player_tabs_, 1);
    pages_->addWidget(page);
}

void MainWindow::open_web_player(const QString& provider, const QString& query,
                                 const QString& url) {
    if (!web_player_tabs_) return;
    web_player_tabs_->open(provider, query, url);
    navigate(QStringLiteral("WEB PLAYERS"));
    // Mirror the reference toast "X geöffnet im eingebetteten Browser".
    QString label = provider.toUpper();
    for (const auto& spec : casu::web::web_players())
        if (QString::fromStdString(spec.key) == provider)
            label = QString::fromStdString(spec.label);
    if (provider == QLatin1String("browse")) label = QStringLiteral("BROWSE");
    status(QStringLiteral("%1 geöffnet im eingebetteten Browser").arg(label));
}

void MainWindow::navigate(const QString& page) {
    static const QMap<QString, int> pages = {
        {"NOW PLAYING", 0}, {"LIBRARY", 1}, {"YOUTUBE", 2}, {"EPG", 3},
        {"VISUALIZER", 4}, {"RECORDING", 5}, {"SETTINGS", 6}, {"WEB PLAYERS", 7},
    };
    int idx = pages.value(page, 0);
    pages_->setCurrentIndex(idx);
    for (QPushButton* b : nav_buttons_) b->setChecked(false);
    if (QPushButton* b = nav_map_.value(page)) b->setChecked(true);
    if (page == "YOUTUBE" && youtube_url_ && youtube_status_) {
        youtube_status_->setText(QStringLiteral("Enter a YouTube URL (resolved via yt-dlp) or a "
                                                "local file path (loopback transport test)."));
    }
}

// ------------------------------------------------------------------ status/toast

void MainWindow::status(const QString& text) {
    if (status_label_) status_label_->setText(text);
}

void MainWindow::toast(const QString& text) {
    status(text);
}

// ------------------------------------------------------------------ playback core

void MainWindow::stop_playback() {
    if (yt_proxy_) yt_proxy_->stop();
    if (recorder_->is_recording()) recorder_->stop();
    if (backend_) {
        controller_->stop();
        controller_->close();
    }
    backend_.reset();
    controller_->poll();
    if (surface_) {
        surface_->set_video_active(false);
        surface_->clear();
    }
    paused_ = false;
    end_handled_ = false;
    duration_ = 0.0;
    seek_slider_->setRange(0, 0);
    seek_slider_->setValue(0);
    time_current_->setText(QStringLiteral("00:00"));
    time_total_->setText(QStringLiteral("00:00"));
    if (visualizer_) static_cast<VisualizerWidget*>(visualizer_)->set_playing(false);
    update_play_button();
    status(QStringLiteral("Stopped"));
}

void MainWindow::open_backend_and_play(const QString& source, const QString& title) {
    end_handled_ = false;
    current_source_ = source;
    current_title_ = title.isEmpty() ? display_title_for_path(source) : title;
    topbar_title_->setText(current_title_);

    bool audio = !is_network_like(source) && is_audio_ext(source);
    surface_->set_video_active(!audio);
    if (visualizer_) static_cast<VisualizerWidget*>(visualizer_)->set_playing(true);
    if (audio) surface_->clear();

    std::vector<std::string> runtime_options;
    if (!vout_.isEmpty())
        runtime_options.push_back(("--vout=" + vout_).toStdString());
    if (!aout_.isEmpty())
        runtime_options.push_back(("--aout=" + aout_).toStdString());
    auto backend = std::make_shared<casu::playback::LibVLCBackend>(
        surface_->native_handle(), std::move(runtime_options));
    backend->on_event = [this](casu::playback::PlaybackState s) { bridge_->post(s); };
    backend_ = backend;
    try {
        if (!is_network_like(source) && is_casu_container(source))
            backend->open_casu(source.toStdString());
        else
            backend->open_source(source.toStdString());
        controller_->attach(backend, source.toStdString());
        controller_->play();
        apply_backend_settings();
        status(QStringLiteral("Playing · %1").arg(current_title_));
    } catch (const casu::playback::PlaybackError& e) {
        surface_->set_video_active(false);
        backend_ = nullptr;
        controller_->close();
        status(QStringLiteral("Playback error: %1").arg(QString::fromStdString(e.what())));
    } catch (const casu::CasuError& e) {
        surface_->set_video_active(false);
        backend_ = nullptr;
        controller_->close();
        status(QStringLiteral("CASU error: %1").arg(QString::fromStdString(e.what())));
    }
    update_play_button();
}

void MainWindow::open_network_source(const QString& source, const QString& title) {
    // Provider URLs (Spotify/Hearthis/Tidal/Netflix) open the official web
    // player in the embedded browser — never linked out, never a second
    // player. Mirrors main_window.py _play_network_source.
    const std::string provider = casu::web::provider_for_url(source.toStdString());
    if (!provider.empty()) {
        open_web_player(QString::fromStdString(provider), QString(), source);
        return;
    }
    stop_playback();  // stop old session incl. any old proxy (order matters)
    QString effective = source;
    if (casu::network::is_youtube_url(source.toStdString())) {
        youtube_status_->setText(QStringLiteral("Resolving YouTube via yt-dlp…"));
        try {
            std::string resolved = casu::network::YtDlp().resolve(source.toStdString(), 45000);
            QString err;
            if (!yt_proxy_->start_remote(
                    QString::fromStdString(resolved),
                    [this, source] {
                        return QString::fromStdString(
                            casu::network::YtDlp().resolve(source.toStdString(), 45000));
                    },
                    &err)) {
                status(QStringLiteral("Transport error: %1").arg(err));
                return;
            }
            effective = yt_proxy_->media_url();
            youtube_status_->setText(QStringLiteral("Loopback transport on port %1").arg(yt_proxy_->port()));
        } catch (const std::exception& e) {
            youtube_status_->setText(QStringLiteral("YouTube resolve failed: %1").arg(QString::fromStdString(e.what())));
            status(QStringLiteral("YouTube resolve failed: %1").arg(QString::fromStdString(e.what())));
            return;
        }
    } else if (QFileInfo::exists(source) && force_proxy_) {
        // Loopback transport test: serve a local file over the proxy.
        QString err;
        if (!yt_proxy_->start_local(source, &err)) {
            status(QStringLiteral("Transport error: %1").arg(err));
            return;
        }
        effective = yt_proxy_->media_url();
    }
    open_backend_and_play(effective, title);
}

void MainWindow::apply_backend_settings() {
    if (!backend_) return;
    try {
        backend_->set_volume(volume_);
        backend_->set_mute(muted_);
        if (rate_ != 1.0) backend_->set_rate(rate_);
    } catch (const casu::playback::PlaybackError&) {
        // settings are best-effort; playback continues
    }
}

void MainWindow::toggle_playback() {
    if (!backend_) {
        if (playlist_.empty()) { status(QStringLiteral("Add a media file first.")); return; }
        int idx = playlist_.current_index() < 0 ? 0 : playlist_.current_index();
        play_queue_index(idx, false);
        return;
    }
    if (controller_->state() == casu::playback::PlaybackState::PAUSED) {
        controller_->pause_or_resume();
        paused_ = false;
    } else if (controller_->state() == casu::playback::PlaybackState::PLAYING) {
        controller_->pause_or_resume();
        paused_ = true;
    } else {
        controller_->play();
        paused_ = false;
    }
    update_play_button();
    if (visualizer_) static_cast<VisualizerWidget*>(visualizer_)->set_playing(!paused_);
}

void MainWindow::pause() {
    if (!backend_) return;
    if (controller_->state() == casu::playback::PlaybackState::PLAYING) {
        controller_->pause_or_resume();
        paused_ = true;
        update_play_button();
    }
}

void MainWindow::resume_after_seek() {
    if (!backend_) return;
    if (paused_ && controller_->state() == casu::playback::PlaybackState::PAUSED) {
        controller_->pause_or_resume();
        paused_ = false;
        update_play_button();
    }
}

void MainWindow::play_queue_index(int index, bool automatic) {
    if (index < 0 || index >= playlist_.size()) return;
    playlist_.set_current(index);
    const PlaylistItem& item = playlist_.items()[index];
    refresh_playlist();
    if (item.is_url || is_network_like(item.path)) {
        open_network_source(item.path, item.title);
    } else {
        stop_playback();
        open_backend_and_play(item.path, item.title);
    }
}

void MainWindow::play_selected_path(const QString& path) {
    int idx = playlist_.index_of(path);
    if (idx >= 0) { play_queue_index(idx, false); return; }
    stop_playback();
    open_backend_and_play(path, display_title_for_path(path));
}

void MainWindow::play_next(bool automatic) {
    if (playlist_.empty()) { stop_playback(); return; }
    int next = playlist_.next_index(automatic);
    if (next < 0) { stop_playback(); return; }
    play_queue_index(next, automatic);
}

void MainWindow::play_previous() {
    if (playlist_.empty()) return;
    int prev = playlist_.previous_index();
    play_queue_index(prev, false);
}

void MainWindow::handle_end() {
    if (end_handled_ || advancing_ || !backend_) return;
    end_handled_ = true;
    advancing_ = true;
    play_next(true);
    advancing_ = false;
}

void MainWindow::seek_to(double seconds) {
    if (!backend_ || seconds < 0) return;
    try {
        controller_->seek(seconds);
        int ms = qBound(0, static_cast<int>(seconds * 1000.0), 0x7fffffff);
        seek_slider_->setValue(ms);
        time_current_->setText(format_duration(seconds));
    } catch (const casu::playback::PlaybackError& e) {
        status(QStringLiteral("Cannot seek — %1").arg(QString::fromStdString(e.what())));
    }
}

void MainWindow::set_volume(int value) {
    volume_ = qBound(0, value, 200);
    if (volume_slider_ && volume_slider_->value() != volume_) volume_slider_->setValue(volume_);
    if (backend_) {
        try { backend_->set_volume(volume_); } catch (const casu::playback::PlaybackError&) {}
    }
}

void MainWindow::toggle_mute() {
    muted_ = !muted_;
    if (backend_) {
        try { backend_->set_mute(muted_); } catch (const casu::playback::PlaybackError&) {}
    }
    mute_btn_->setText(muted_ ? QStringLiteral("×") : QStringLiteral("♪"));
}

void MainWindow::cycle_rate() {
    const double rates[] = {0.5, 1.0, 1.25, 1.5, 2.0};
    double next = 1.0;
    for (double r : rates) {
        if (qAbs(r - rate_) < 0.01) { next = r; break; }
    }
    int i = 0;
    for (; i < 5; ++i) if (qAbs(rates[i] - next) < 0.01) break;
    next = rates[(i + 1) % 5];
    rate_ = next;
    rate_btn_->setText(QString("%1×").arg(rate_, 0, 'g', 3));
    if (backend_) {
        try { backend_->set_rate(rate_); } catch (const casu::playback::PlaybackError&) {}
    }
}

void MainWindow::toggle_fullscreen() {
    if (isFullScreen()) showNormal();
    else showFullScreen();
}

void MainWindow::save_snapshot() {
    if (!backend_) { status(QStringLiteral("No media loaded")); return; }
    QString dir = app_settings_.snapshot_dir.isEmpty() ? output_dir_ : app_settings_.snapshot_dir;
    QDir().mkpath(dir);
    QString name = QDateTime::currentDateTime().toString("yyyyMMdd-HHmmss") + ".png";
    try {
        backend_->snapshot((dir + "/" + name).toStdString());
        status(QStringLiteral("Snapshot saved: %1/%2").arg(dir, name));
    } catch (const casu::playback::PlaybackError& e) {
        status(QStringLiteral("Snapshot failed: %1").arg(QString::fromStdString(e.what())));
    }
}

void MainWindow::cycle_repeat() {
    using R = PlaylistModel::RepeatMode;
    if (playlist_.repeat == R::Off) playlist_.repeat = R::All;
    else if (playlist_.repeat == R::All) playlist_.repeat = R::One;
    else playlist_.repeat = R::Off;
    repeat_btn_->setText(playlist_.repeat == R::Off ? QStringLiteral("↻")
                         : playlist_.repeat == R::One ? QStringLiteral("↻1")
                                                      : QStringLiteral("↻∞"));
    app_settings_.repeat = playlist_.repeat == R::Off ? "off"
                           : playlist_.repeat == R::One ? "one" : "all";
    settings_->save(app_settings_);
}

void MainWindow::on_backend_state(casu::playback::PlaybackState s) {
    switch (s) {
        case casu::playback::PlaybackState::ENDED:
            handle_end();
            break;
        case casu::playback::PlaybackState::ERROR:
            status(QStringLiteral("Playback error detected"));
            surface_->set_video_active(false);
            break;
        case casu::playback::PlaybackState::PLAYING:
            paused_ = false;
            update_play_button();
            break;
        case casu::playback::PlaybackState::PAUSED:
            paused_ = true;
            update_play_button();
            break;
        default:
            break;
    }
}

void MainWindow::poll() {
    if (!backend_) return;
    controller_->poll();
    const double pos = controller_->position();
    const double dur = controller_->duration();
    if (dur > 0.0 && qAbs(duration_ - dur) > 0.5) {
        duration_ = dur;
        seek_slider_->setRange(0, static_cast<int>(dur * 1000.0));
    }
    if (!seek_slider_->isSliderDown()) {
        int ms = qBound(0, static_cast<int>(pos * 1000.0), 0x7fffffff);
        seek_slider_->setValue(ms);
        time_current_->setText(format_duration(pos));
        time_total_->setText(format_duration(duration_));
    }
    if (duration_ > 0.0 && pos >= duration_ - 0.25 && !paused_) handle_end();
    const casu::playback::PlaybackState st = controller_->state();
    if (st == casu::playback::PlaybackState::ERROR) {
        status(QStringLiteral("Playback error detected"));
        surface_->set_video_active(false);
        stop_playback();
    }
}

void MainWindow::update_play_button() {
    if (!play_btn_) return;
    const casu::playback::PlaybackState st = controller_->state();
    play_btn_->setText(st == casu::playback::PlaybackState::PLAYING && !paused_
                           ? QStringLiteral("| |")
                           : QStringLiteral("▶"));
}

// ------------------------------------------------------------------ playlist UI actions

void MainWindow::choose_files() {
    const QStringList files = QFileDialog::getOpenFileNames(
        this, QStringLiteral("Choose media"), QDir::homePath(),
        QStringLiteral("Media (*.mp4 *.mkv *.webm *.avi *.mov *.mp3 *.flac *.wav *.ogg *.m4a *.aac "
                       "*.opus *.casu *.mp5 *.m3u *.m3u8 *.pls);;All files (*.*)"));
    if (files.isEmpty()) return;
    add_files(files);
}

void MainWindow::add_url() {
    bool ok = false;
    QString url = QInputDialog::getText(this, QStringLiteral("Add URL"),
                                        QStringLiteral("Stream URL or YouTube link"),
                                        QLineEdit::Normal, QString(), &ok);
    if (!ok || url.trimmed().isEmpty()) return;
    add_files({url.trimmed()});
}

void MainWindow::load_playlist_file() {
    QString file = QFileDialog::getOpenFileName(this, QStringLiteral("Load playlist"),
                                                QDir::homePath(),
                                                QStringLiteral("Playlists (*.m3u *.m3u8 *.pls)"));
    if (file.isEmpty()) return;
    PlaylistModel tmp;
    std::string err = PlaylistModel::load_file(file, &tmp);
    if (!err.empty()) { status(QStringLiteral("Playlist error: %1").arg(QString::fromStdString(err))); return; }
    playlist_.clear();
    for (const PlaylistItem& item : tmp.items()) playlist_.add(item.path, item.title);
    app_settings_.last_playlist = file;
    settings_->save(app_settings_);
    refresh_playlist();
    status(QStringLiteral("Loaded %1 entries from %2").arg(playlist_.size()).arg(QFileInfo(file).fileName()));
}

void MainWindow::save_playlist_file() {
    if (playlist_.empty()) return;
    QString file = QFileDialog::getSaveFileName(this, QStringLiteral("Save playlist"),
                                                QDir::homePath() + "/queue.m3u",
                                                QStringLiteral("M3U (*.m3u);;PLS (*.pls)"));
    if (file.isEmpty()) return;
    std::string err = file.toLower().endsWith(".pls") ? PlaylistModel::save_pls(file, playlist_)
                                                      : PlaylistModel::save_m3u(file, playlist_);
    if (!err.empty()) status(QStringLiteral("Playlist error: %1").arg(QString::fromStdString(err)));
    else status(QStringLiteral("Playlist saved"));
}

void MainWindow::playlist_double_clicked() {
    int row = playlist_view_->currentRow();
    if (row >= 0) play_queue_index(row, false);
}

void MainWindow::playlist_context_menu(const QPoint& pos) {
    QMenu menu(this);
    const QList<QListWidgetItem*> sel = playlist_view_->selectedItems();
    if (!sel.isEmpty()) {
        const int count = sel.size();
        QString label = count == 1 ? QStringLiteral("Play") :
                                     QStringLiteral("Play (%1 items)").arg(count);
        menu.addAction(label, this, [this, sel] {
            int row = playlist_view_->row(sel.first());
            if (row >= 0) play_queue_index(row, false);
        });
        QString merge_label = count == 1
            ? QStringLiteral("Save selection to playlist…")
            : QStringLiteral("Save %1 items to playlist…").arg(count);
        menu.addAction(merge_label, this, &MainWindow::merge_selection_into_playlist);
        menu.addSeparator();
        menu.addAction(QStringLiteral("Remove selected"), this, [this, sel] {
            QList<int> rows;
            for (auto* it : sel) rows.append(playlist_view_->row(it));
            std::sort(rows.begin(), rows.end(), std::greater<int>());
            for (int r : rows) playlist_.remove(r);
            refresh_playlist();
        });
    }
    menu.exec(playlist_view_->viewport()->mapToGlobal(pos));
}

void MainWindow::merge_selection_into_playlist() {
    const QList<QListWidgetItem*> sel = playlist_view_->selectedItems();
    if (sel.isEmpty()) { status(QStringLiteral("Select items to save to a playlist first.")); return; }

    // Collect the selected media paths / URLs (deduplicated).
    QStringList entries;
    for (auto* it : sel) {
        const QString path = it->data(Qt::UserRole).toString();
        if (!path.isEmpty() && !entries.contains(path)) entries.append(path);
    }
    if (entries.isEmpty()) { status(QStringLiteral("Nothing to merge: no playable item selected.")); return; }

    // Choose target: extend an existing playlist (last used) or create a new one.
    QString target = app_settings_.last_playlist;
    if (!target.isEmpty() && QFileInfo::exists(target)) {
        QMessageBox box(this);
        box.setWindowTitle(QStringLiteral("Merge into playlist"));
        box.setText(QStringLiteral("Append %1 item(s) to the existing playlist\n%2 ?")
                        .arg(entries.size()).arg(QFileInfo(target).fileName()));
        QPushButton* yes = box.addButton(QStringLiteral("Merge"), QMessageBox::AcceptRole);
        box.addButton(QStringLiteral("New playlist…"), QMessageBox::ActionRole);
        box.addButton(QMessageBox::Cancel);
        box.exec();
        if (box.clickedButton() == yes) {
            // fall through to merge into `target`
        } else if (box.clickedButton()->text() == QStringLiteral("New playlist…")) {
            target = QFileDialog::getSaveFileName(this, QStringLiteral("New playlist"),
                                                  QDir::homePath() + "/queue.m3u",
                                                  QStringLiteral("M3U (*.m3u);;PLS (*.pls)"));
            if (target.isEmpty()) return;
        } else {
            return;  // cancel
        }
    } else {
        target = QFileDialog::getSaveFileName(this, QStringLiteral("Save playlist"),
                                              QDir::homePath() + "/queue.m3u",
                                              QStringLiteral("M3U (*.m3u);;PLS (*.pls)"));
        if (target.isEmpty()) return;
    }

    // Merge: load existing playlist (if any), append selected entries (dedup),
    // then save back in the original format.
    PlaylistModel merged;
    std::string err;
    if (QFileInfo::exists(target)) {
        err = PlaylistModel::load_file(target, &merged);
        if (!err.empty()) { status(QStringLiteral("Could not read playlist: %1").arg(QString::fromStdString(err))); return; }
    }
    int added = 0;
    for (const QString& entry : entries) {
        if (merged.index_of(entry) < 0) { merged.add(entry); ++added; }
    }
    err = target.toLower().endsWith(".pls")
              ? PlaylistModel::save_pls(target, merged)
              : PlaylistModel::save_m3u(target, merged);
    if (!err.empty()) { status(QStringLiteral("Could not save playlist: %1").arg(QString::fromStdString(err))); return; }
    app_settings_.last_playlist = target;
    settings_->save(app_settings_);
    status(QStringLiteral("Added %1 item(s) to %2").arg(added).arg(QFileInfo(target).fileName()));
    toast(QStringLiteral("Playlist updated · %1").arg(QFileInfo(target).fileName()));
}

void MainWindow::refresh_playlist() {
    if (!playlist_view_) return;
    playlist_view_->clear();
    for (int i = 0; i < playlist_.items().size(); ++i) {
        const PlaylistItem& item = playlist_.items()[i];
        QString label = item.title.isEmpty() ? item.path : item.title;
        if (i == playlist_.current_index()) label = QStringLiteral("▶ ") + label;
        auto* it = new QListWidgetItem(label, playlist_view_);
        it->setData(Qt::UserRole, item.path);
        it->setToolTip(item.path);
    }
}

void MainWindow::add_files(const QStringList& paths) {
    for (const QString& path : paths) {
        if (PlaylistModel::looks_like_playlist(path) && QFileInfo::exists(path)) {
            PlaylistModel tmp;
            std::string err = PlaylistModel::load_file(path, &tmp);
            if (err.empty()) {
                for (const PlaylistItem& item : tmp.items()) playlist_.add(item.path, item.title);
                continue;
            }
        }
        playlist_.add(path);
    }
    refresh_playlist();
    status(QStringLiteral("%1 item(s) in queue").arg(playlist_.size()));
}

// ------------------------------------------------------------------ page actions

void MainWindow::on_library_play() {
    int row = library_view_->currentRow();
    if (row < 0) { status(QStringLiteral("Select a library entry first.")); return; }
    const LibraryEntry& e = library_->entries()[row];
    playlist_.clear();
    playlist_.add(e.path, e.title);
    refresh_playlist();
    play_queue_index(0, false);
}

void MainWindow::on_library_add_current() {
    if (current_source_.isEmpty()) { status(QStringLiteral("Nothing playing yet.")); return; }
    library_->add(current_source_, current_title_);
    refresh_library();
    status(QStringLiteral("Added to library: %1").arg(current_title_));
}

void MainWindow::refresh_library() {
    if (!library_view_) return;
    library_view_->clear();
    for (const LibraryEntry& e : library_->entries())
        library_view_->addItem(e.title.isEmpty() ? e.path : e.title);
}

void MainWindow::on_settings_save() {
    app_settings_.volume = settings_volume_->value();
    app_settings_.rate = settings_rate_->value();
    app_settings_.shuffle = settings_shuffle_->isChecked();
    app_settings_.repeat = settings_repeat_->currentText();
    app_settings_.record_dir = settings_record_dir_->text().trimmed();
    settings_->save(app_settings_);
    volume_ = app_settings_.volume;
    rate_ = app_settings_.rate;
    playlist_.shuffle = app_settings_.shuffle;
    playlist_.repeat = app_settings_.repeat == "one"
                           ? PlaylistModel::RepeatMode::One
                           : (app_settings_.repeat == "all"
                                  ? PlaylistModel::RepeatMode::All
                                  : PlaylistModel::RepeatMode::Off);
    output_dir_ = app_settings_.record_dir;
    if (record_dir_) record_dir_->setText(output_dir_);
    if (volume_slider_) volume_slider_->setValue(volume_);
    shuffle_btn_->setChecked(playlist_.shuffle);
    if (playlist_.repeat == PlaylistModel::RepeatMode::Off) repeat_btn_->setText(QStringLiteral("↻"));
    else if (playlist_.repeat == PlaylistModel::RepeatMode::One) repeat_btn_->setText(QStringLiteral("↻1"));
    else repeat_btn_->setText(QStringLiteral("↻∞"));
    status(QStringLiteral("Settings saved"));
}

void MainWindow::on_epg_load() {
    QString file = QFileDialog::getOpenFileName(this, QStringLiteral("Load XMLTV"),
                                                QDir::homePath(), QStringLiteral("XMLTV (*.xml)"));
    if (file.isEmpty()) return;
    QFile f(file);
    if (!f.open(QIODevice::ReadOnly)) { status(QStringLiteral("Could not read %1").arg(file)); return; }
    QString err = parse_xmltv(f.readAll(), &epg_);
    if (!err.isEmpty()) { status(QStringLiteral("EPG error: %1").arg(err)); return; }
    epg_channel_->clear();
    for (const EpgChannel& ch : epg_.channels)
        epg_channel_->addItem(ch.name.isEmpty() ? ch.id : ch.name, ch.id);
    status(QStringLiteral("EPG: %1 channels, %2 programs").arg(epg_.channels.size()).arg(epg_.programs.size()));
}

void MainWindow::on_recording_toggle() {
    if (recorder_->is_recording()) {
        recorder_->stop();
        return;
    }
    if (current_source_.isEmpty()) { status(QStringLiteral("Nothing to record.")); return; }
    QString dir = record_dir_ ? record_dir_->text().trimmed() : output_dir_;
    if (dir.isEmpty()) dir = output_dir_;
    QDir().mkpath(dir);
    QString base = QDateTime::currentDateTime().toString("yyyyMMdd-HHmmss");
    QString ext = current_source_.contains("://") ? "mkv" : QFileInfo(current_source_).suffix();
    if (ext.isEmpty()) ext = "mkv";
    QString out = dir + "/" + base + "." + ext;
    QString err;
    if (!recorder_->start(current_source_, out, &err)) status(QStringLiteral("Recording start failed: %1").arg(err));
    else status(QStringLiteral("Recording to %1").arg(out));
}

void MainWindow::on_visualizer_toggle() {
    if (stage_stack_) {
        stage_stack_->setCurrentIndex(viz_btn_->isChecked() ? 1 : 0);
        static_cast<VisualizerWidget*>(visualizer_)->set_active(viz_btn_->isChecked());
    }
}

void MainWindow::on_youtube_play() {
    QString input = youtube_url_->text().trimmed();
    if (input.isEmpty()) { status(QStringLiteral("Enter a URL or file path.")); return; }
    open_network_source(input, input);
}

// ------------------------------------------------------------------ window events

void MainWindow::dragEnterEvent(QDragEnterEvent* event) {
    if (event->mimeData()->hasUrls()) event->acceptProposedAction();
}

void MainWindow::dropEvent(QDropEvent* event) {
    QStringList paths;
    for (const QUrl& url : event->mimeData()->urls()) paths << url.toLocalFile();
    if (paths.isEmpty()) return;
    add_files(paths);
    event->acceptProposedAction();
}

void MainWindow::keyPressEvent(QKeyEvent* event) {
    switch (event->key()) {
        case Qt::Key_Space:
            toggle_playback();
            event->accept();
            return;
        case Qt::Key_F:
            toggle_fullscreen();
            event->accept();
            return;
        case Qt::Key_Right:
            if (event->modifiers() & Qt::ShiftModifier) seek_to(controller_->position() + 10.0);
            else seek_to(controller_->position() + 5.0);
            event->accept();
            return;
        case Qt::Key_Left:
            seek_to(controller_->position() - 5.0);
            event->accept();
            return;
        default:
            break;
    }
    QMainWindow::keyPressEvent(event);
}

void MainWindow::closeEvent(QCloseEvent* event) {
    stop_playback();
    if (recorder_) recorder_->kill();
    if (poll_timer_) poll_timer_->stop();
    event->accept();
}

}  // namespace mpcasu
