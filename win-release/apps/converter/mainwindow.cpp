// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "mainwindow.hpp"
#include <cmath>

#include "theme.hpp"
#include "worker.hpp"

#include "casu/formats.hpp"
#include "casu/json.hpp"
#include "casu/media/mediainfo.hpp"
#include "casu/native.hpp"

#include <QCheckBox>
#include <QCloseEvent>
#include <QComboBox>
#include <QDialog>
#include <QDialogButtonBox>
#include <QDir>
#include <QDirIterator>
#include <QDragEnterEvent>
#include <QDropEvent>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMessageBox>
#include <QMimeData>
#include <QProgressBar>
#include <QPushButton>
#include <QDoubleSpinBox>
#include <QSpinBox>
#include <QTextEdit>
#include <QTimer>
#include <QVBoxLayout>

#include <algorithm>
#include <cstring>
#include <fstream>
#include <set>
#include <string>
#include <vector>

namespace casu::conv {

namespace {

QFrame* make_panel(QWidget* parent) {
    auto* panel = new QFrame(parent);
    panel->setObjectName("Panel");
    return panel;
}

QLabel* heading(QWidget* parent, const QString& text) {
    auto* label = new QLabel(text, parent);
    label->setObjectName("PanelHeading");
    return label;
}

QLabel* hint(QWidget* parent, const QString& text) {
    auto* label = new QLabel(text, parent);
    label->setObjectName("Hint");
    return label;
}

QComboBox* make_combo(QWidget* parent) {
    auto* combo = new QComboBox(parent);
    combo->setMinimumWidth(130);
    return combo;
}

QString state_name(const std::string& state) {
    if (state == "RUNNING") return QStringLiteral("Running");
    if (state == "DONE") return QStringLiteral("Done");
    if (state == "EXPORTED") return QStringLiteral("Exported");
    if (state == "FAILED") return QStringLiteral("Failed");
    return QString::fromStdString(state);
}

}  // namespace

MainWindow::MainWindow(QWidget* parent) : QMainWindow(parent) {
    setWindowTitle("CASU Full Media Converter");
    resize(1000, 720);
    setMinimumSize(680, 420);
    setAcceptDrops(true);

    auto* central = new QWidget(this);
    auto* root = new QVBoxLayout(central);
    root->setContentsMargins(24, 18, 24, 18);
    root->setSpacing(12);
    setCentralWidget(central);

    auto* title = new QLabel("CASU CONVERTER", central);
    title->setObjectName("Title");
    root->addWidget(title);
    auto* subtitle = hint(central, "Codec for All Segmented Units · source media remains untouched");
    root->addWidget(subtitle);

    // --- Step 1: sources ---
    auto* step1 = make_panel(central);
    auto* step1_layout = new QVBoxLayout(step1);
    step1_layout->setContentsMargins(16, 12, 16, 12);
    step1_layout->addWidget(heading(step1, "1 · SOURCES"));

    auto* actions = new QHBoxLayout();
    auto* add_files = new QPushButton("Add files…", step1);
    auto* add_folder = new QPushButton("Add folder…", step1);
    auto* remove_selected = new QPushButton("Remove selected", step1);
    auto* clear_queue = new QPushButton("Clear queue", step1);
    actions->addWidget(add_files);
    actions->addWidget(add_folder);
    actions->addWidget(remove_selected);
    actions->addWidget(clear_queue);
    actions->addWidget(hint(step1, "Drop files anywhere in the window."), 1);
    step1_layout->addLayout(actions);

    queue_ = new QListWidget(step1);
    queue_->setMinimumHeight(110);
    queue_->setSelectionMode(QAbstractItemView::ExtendedSelection);
    step1_layout->addWidget(queue_);

    auto* output_row = new QHBoxLayout();
    output_row->addWidget(hint(step1, "Output folder"));
    output_dir_ = new QLineEdit(step1);
    output_dir_->setPlaceholderText("Where converted files are written (defaults to the source folder)");
    auto* browse_output = new QPushButton("Browse…", step1);
    output_row->addWidget(output_dir_, 1);
    output_row->addWidget(browse_output);
    step1_layout->addLayout(output_row);

    source_info_ = new QLabel(step1);
    source_info_->setWordWrap(true);
    source_info_->setText("No source inspected.");
    step1_layout->addWidget(source_info_);
    root->addWidget(step1);

    // --- Step 2: direction ---
    auto* step2 = make_panel(central);
    auto* step2_layout = new QVBoxLayout(step2);
    step2_layout->setContentsMargins(16, 12, 16, 12);
    step2_layout->addWidget(heading(step2, "2 · DIRECTION"));
    auto* dir_row = new QHBoxLayout();
    dir_row->addWidget(hint(step2, "Mode"));
    direction_ = make_combo(step2);
    direction_->addItem("Media → Media", QVariant((int)Direction::MediaToMedia));
    direction_->addItem("Media → CASU", QVariant((int)Direction::ToCasu));
    direction_->addItem("CASU → Media", QVariant((int)Direction::FromCasu));
    dir_row->addWidget(direction_);
    dir_row->addWidget(hint(step2, "Transcode between legacy formats · pack media into CASU · export CASU back to media."), 1);
    step2_layout->addLayout(dir_row);
    root->addWidget(step2);

    // --- Step 3: direction-aware options ---
    auto* step3 = make_panel(central);
    auto* step3_layout = new QVBoxLayout(step3);
    step3_layout->setContentsMargins(16, 12, 16, 12);
    step3_layout->addWidget(heading(step3, "3 · OPTIONS"));

    media_options_ = new QWidget(step3);
    auto* media_layout = new QVBoxLayout(media_options_);
    media_layout->setContentsMargins(0, 0, 0, 0);
    media_layout->setSpacing(8);
    auto* row_a = new QHBoxLayout();
    row_a->addWidget(hint(media_options_, "Output format"));
    format_ = make_combo(media_options_);
    format_->setEditable(true);
    for (const std::string& ext : ConversionEngine::output_extensions())
        format_->addItem(QString::fromStdString(ext.substr(1)));
    format_->setCurrentText("mp4");
    row_a->addWidget(format_);
    row_a->addWidget(hint(media_options_, "Container used for the exported media."), 1);
    media_layout->addLayout(row_a);

    auto* preset_row = new QHBoxLayout();
    preset_row->addWidget(hint(media_options_, "Media profile"));
    preset_ = make_combo(media_options_);
    preset_->addItems({"balanced", "high", "lossless", "remux", "small"});
    preset_->setCurrentText("balanced");
    preset_row->addWidget(preset_);
    preset_row->addWidget(hint(media_options_,
        "Remux copies codecs; Lossless uses lossless codecs where the container permits."), 1);
    media_layout->addLayout(preset_row);

    // Linux parity: collapsible "▸ Advanced options" section.
    advanced_btn_ = new QPushButton("▸ Advanced options", step3);
    advanced_btn_->setObjectName("IconButton");
    advanced_btn_->setFlat(true);
    advanced_btn_->setStyleSheet("text-align:left; font-weight:600; border:none;");
    media_layout->addWidget(advanced_btn_);
    advanced_frame_ = new QWidget(step3);
    auto* adv = new QVBoxLayout(advanced_frame_);
    adv->setContentsMargins(14, 8, 14, 8);
    adv->setSpacing(6);

    auto* adv_row_a = new QHBoxLayout();
    adv_row_a->addWidget(hint(advanced_frame_, "Analysis mode"));
    analysis_mode_ = make_combo(advanced_frame_);
    analysis_mode_->addItems({"adaptive", "strict", "visually_lossless"});
    analysis_mode_->setCurrentText("strict");
    adv_row_a->addWidget(analysis_mode_);
    adv_row_a->addWidget(hint(advanced_frame_, "Analysis FPS"));
    analysis_fps_ = new QDoubleSpinBox(advanced_frame_);
    analysis_fps_->setRange(0.1, 120.0);
    analysis_fps_->setSingleStep(0.5);
    analysis_fps_->setValue(10.0);
    adv_row_a->addWidget(analysis_fps_);
    adv_row_a->addWidget(hint(advanced_frame_, "Retries"));
    retries_ = new QSpinBox(advanced_frame_);
    retries_->setRange(0, 10);
    retries_->setValue(0);
    adv_row_a->addWidget(retries_);
    adv_row_a->addStretch(1);
    adv->addLayout(adv_row_a);

    auto* adv_row_b = new QHBoxLayout();
    adv_row_b->addWidget(hint(advanced_frame_, "CASU tile size"));
    tile_size_ = new QSpinBox(advanced_frame_);
    tile_size_->setRange(8, 1024);
    tile_size_->setSingleStep(8);
    tile_size_->setValue(64);
    adv_row_b->addWidget(tile_size_);
    adv_row_b->addWidget(hint(advanced_frame_, "Key-state interval (s)"));
    key_interval_ = new QDoubleSpinBox(advanced_frame_);
    key_interval_->setRange(0.1, 3600.0);
    key_interval_->setSingleStep(0.5);
    key_interval_->setValue(3.0);
    adv_row_b->addWidget(key_interval_);
    adv_row_b->addStretch(1);
    adv->addLayout(adv_row_b);

    auto* adv_row_c = new QHBoxLayout();
    adv_row_c->addWidget(hint(advanced_frame_, "Video codec"));
    video_codec_ = make_combo(advanced_frame_);
    video_codec_->setEditable(true);
    video_codec_->addItems({"auto", "libx264", "libx265", "libvpx-vp9", "libaom-av1", "ffv1", "mpeg4", "mpeg2video"});
    adv_row_c->addWidget(video_codec_);
    adv_row_c->addWidget(hint(advanced_frame_, "Audio codec"));
    audio_codec_ = make_combo(advanced_frame_);
    audio_codec_->setEditable(true);
    audio_codec_->addItems({"auto", "aac", "libmp3lame", "libopus", "libvorbis", "flac", "alac", "pcm_s16le"});
    adv_row_c->addWidget(audio_codec_);
    adv_row_c->addWidget(hint(advanced_frame_, "Subtitles"));
    subtitle_mode_ = make_combo(advanced_frame_);
    subtitle_mode_->addItems({"auto", "copy", "drop"});
    adv_row_c->addWidget(subtitle_mode_);
    adv_row_c->addStretch(1);
    adv->addLayout(adv_row_c);

    auto* adv_row_d = new QHBoxLayout();
    all_tracks_ = new QCheckBox("All compatible tracks", advanced_frame_);
    all_tracks_->setChecked(true);
    adv_row_d->addWidget(all_tracks_);
    preserve_metadata_ = new QCheckBox("Preserve metadata and chapters", advanced_frame_);
    preserve_metadata_->setChecked(true);
    adv_row_d->addWidget(preserve_metadata_);
    resume_jobs_ = new QCheckBox("Resume verified jobs", advanced_frame_);
    resume_jobs_->setChecked(true);
    adv_row_d->addWidget(resume_jobs_);
    adv_row_d->addStretch(1);
    adv->addLayout(adv_row_d);

    media_layout->addWidget(advanced_frame_);
    step3_layout->addWidget(media_options_);

    casu_options_ = new QWidget(step3);
    auto* casu_layout = new QHBoxLayout(casu_options_);
    casu_layout->setContentsMargins(0, 0, 0, 0);
    casu_layout->addWidget(hint(casu_options_, "CASU container"));
    container_ = make_combo(casu_options_);
    container_->addItem("Native (CASUNAT1)", QVariant((int)CasuContainer::Native));
    container_->addItem("Sidecar manifest", QVariant((int)CasuContainer::Sidecar));
    container_->addItem("MP5", QVariant((int)CasuContainer::Mp5));
    casu_layout->addWidget(container_);
    casu_layout->addStretch(1);
    step3_layout->addWidget(casu_options_);
    root->addWidget(step3);

    // --- Inline overwrite confirmation (Linux parity: red bar, no popup) ---
    confirm_frame_ = new QFrame(central);
    confirm_frame_->setObjectName("ConfirmBar");
    confirm_frame_->setStyleSheet(
        "QFrame#ConfirmBar { background:#3a0d12; border:1px solid #ff1e2d;"
        " border-radius:6px; }");
    auto* confirm_layout = new QHBoxLayout(confirm_frame_);
    confirm_layout->setContentsMargins(14, 8, 14, 8);
    confirm_label_ = new QLabel(confirm_frame_);
    confirm_layout->addWidget(confirm_label_, 1);
    auto* keep_btn = new QPushButton("Keep existing", confirm_frame_);
    auto* replace_btn = new QPushButton("Replace files", confirm_frame_);
    replace_btn->setObjectName("Primary");
    confirm_layout->addWidget(keep_btn);
    confirm_layout->addWidget(replace_btn);
    confirm_frame_->hide();

    // --- Actions + progress (Linux parity order) ---
    auto* action_row = new QHBoxLayout();
    convert_button_ = new QPushButton("Convert", central);
    convert_button_->setObjectName("Primary");
    auto* verify_button = new QPushButton("Verify output", central);
    auto* report_button = new QPushButton("Last report", central);
    action_row->addWidget(convert_button_);
    action_row->addWidget(verify_button);
    action_row->addWidget(report_button);
    action_row->addStretch(1);
    pause_button_ = new QPushButton("Pause queue", central);
    pause_button_->setEnabled(false);
    cancel_button_ = new QPushButton("Cancel", central);
    cancel_button_->setEnabled(false);
    action_row->addWidget(cancel_button_);
    action_row->addWidget(pause_button_);
    root->addLayout(action_row);

    progress_ = new QProgressBar(central);
    progress_->setRange(0, 1000);
    progress_->setValue(0);
    progress_->setTextVisible(false);
    root->addWidget(progress_);

    status_ = new QLabel("Step 1 — choose media or CASU source files.", central);
    status_->setObjectName("Status");
    status_->setWordWrap(true);
    root->addWidget(status_);

    toast_ = new QLabel(central);
    toast_->setObjectName("Toast");
    toast_->setWordWrap(true);
    toast_->hide();
    root->addWidget(toast_, 0, Qt::AlignHCenter);

    // Connections (new-style: real Qt signals -> plain member functions/lambdas).
    connect(add_files, &QPushButton::clicked, this, [this]() { chooseFiles(); });
    connect(add_folder, &QPushButton::clicked, this, [this]() { chooseFolder(); });
    connect(remove_selected, &QPushButton::clicked, this, [this]() { removeSelected(); });
    connect(clear_queue, &QPushButton::clicked, this, [this]() { clearQueue(); });
    connect(browse_output, &QPushButton::clicked, this, [this]() { chooseOutputDir(); });
    connect(direction_, QOverload<int>::of(&QComboBox::currentIndexChanged), this,
            [this](int) { syncDirectionOptions(); });
    connect(convert_button_, &QPushButton::clicked, this, [this]() { startConversion(); });
    connect(cancel_button_, &QPushButton::clicked, this, [this]() { cancelConversion(); });
    connect(pause_button_, &QPushButton::clicked, this, [this]() { pauseQueue(); });
    connect(verify_button, &QPushButton::clicked, this, [this]() { verifyOutput(); });
    connect(report_button, &QPushButton::clicked, this, [this]() { showLastReport(); });
    // Linux parity: "▸ Advanced options" collapses the advanced frame.
    advanced_frame_->setVisible(false);
    connect(advanced_btn_, &QPushButton::clicked, this, [this]() {
        const bool show = !advanced_frame_->isVisible();
        advanced_frame_->setVisible(show);
        advanced_btn_->setText(show ? "▾ Advanced options" : "▸ Advanced options");
    });
    // Inline overwrite confirmation (Linux parity: no popup).
    connect(keep_btn, &QPushButton::clicked, this, [this]() {
        confirm_frame_->hide();
        pending_jobs_.clear();
        status_->setText("Replace cancelled — existing outputs were kept.");
    });
    connect(replace_btn, &QPushButton::clicked, this, [this]() {
        confirm_frame_->hide();
        if (!pending_jobs_.empty()) runJobs(pending_jobs_);
        pending_jobs_.clear();
    });

    syncDirectionOptions();
}

// --- Source selection ------------------------------------------------------

void MainWindow::chooseFiles() {
    const QStringList paths = QFileDialog::getOpenFileNames(
        this, "Choose media or CASU source files", QString(),
        "All files (*.*);;All files (*)");
    if (!paths.isEmpty()) addSources(paths);
}

void MainWindow::chooseFolder() {
    const QString folder = QFileDialog::getExistingDirectory(this, "Choose a folder of sources", QString());
    if (folder.isEmpty()) return;
    // Linux parity (collect_folder_sources): recursive scan.
    QStringList paths;
    QDirIterator it(folder, QDir::Files | QDir::NoDotAndDotDot, QDirIterator::Subdirectories);
    while (it.hasNext()) paths.append(it.next());
    paths.sort();
    addSources(paths);
}

void MainWindow::chooseOutputDir() {
    const QString folder = QFileDialog::getExistingDirectory(
        this, "Choose the output folder", output_dir_->text().trimmed());
    if (!folder.isEmpty()) output_dir_->setText(folder);
}

void MainWindow::removeSelected() {
    const QList<QListWidgetItem*> selected = queue_->selectedItems();
    for (QListWidgetItem* item : selected) delete item;
    source_info_->setText(queue_->count() == 0 ? "No source files selected."
                                               : QString("%1 file(s) queued.").arg(queue_->count()));
}

void MainWindow::clearQueue() {
    queue_->clear();
    source_info_->setText("No source files selected.");
}

void MainWindow::addSources(const QStringList& paths) {
    std::set<QString> seen;
    for (int i = 0; i < queue_->count(); ++i) seen.insert(queue_->item(i)->text());
    for (const QString& path : paths) {
        const QFileInfo info(path);
        if (!info.isFile()) continue;
        const QString canonical = info.canonicalFilePath();
        if (canonical.isEmpty() || !seen.insert(canonical).second) continue;
        queue_->addItem(canonical);
    }
    if (queue_->count() > 0 && output_dir_->text().trimmed().isEmpty())
        output_dir_->setText(QFileInfo(queue_->item(0)->text()).dir().path());
    source_info_->setText(QString("%1 file(s) queued.").arg(queue_->count()));
}

QStringList MainWindow::currentSources() const {
    QStringList out;
    for (int i = 0; i < queue_->count(); ++i) out.append(queue_->item(i)->text());
    return out;
}

// --- Drag & drop -----------------------------------------------------------

void MainWindow::dragEnterEvent(QDragEnterEvent* event) {
    if (event->mimeData() && event->mimeData()->hasUrls()) event->acceptProposedAction();
}

void MainWindow::dropEvent(QDropEvent* event) {
    QStringList paths;
    const QList<QUrl> urls = event->mimeData()->urls();
    for (const QUrl& url : urls) {
        if (url.isLocalFile()) paths.append(url.toLocalFile());
    }
    if (!paths.isEmpty()) addSources(paths);
    event->acceptProposedAction();
}

void MainWindow::closeEvent(QCloseEvent* event) {
    if (busy_) {
        cancel_->store(true);
        if (worker_thread_.joinable()) worker_thread_.join();
    }
    QMainWindow::closeEvent(event);
}

// --- Direction / profile ---------------------------------------------------

void MainWindow::syncDirectionOptions() {
    const Direction dir = currentDirection();
    media_options_->setVisible(dir == Direction::MediaToMedia || dir == Direction::FromCasu);
    casu_options_->setVisible(dir == Direction::ToCasu);
    if (dir == Direction::FromCasu)
        source_info_->setText("From-CASU mode accepts only verified CASU content.");
    else if (dir == Direction::ToCasu)
        source_info_->setText("Pack media into a CASU container (native / sidecar / MP5).");
    else
        source_info_->setText(QString("%1 file(s) queued.").arg(queue_->count()));
}

Direction MainWindow::currentDirection() const {
    return (Direction)direction_->currentData().toInt();
}

CasuContainer MainWindow::currentCasuContainer() const {
    return (CasuContainer)container_->currentData().toInt();
}

ConversionProfile MainWindow::currentProfile() const {
    ConversionProfile p;
    p.direction = currentDirection();
    p.casu_container = currentCasuContainer();
    p.media_preset = preset_->currentText().trimmed().toStdString();
    p.video_codec = video_codec_->currentText().trimmed().toStdString();
    p.audio_codec = audio_codec_->currentText().trimmed().toStdString();
    p.subtitle_mode = subtitle_mode_->currentText().trimmed().toStdString();
    p.output_extension = "." + format_->currentText().trimmed().toLower().toStdString();
    // Linux parity: jobs always run with force=True once the user confirmed
    // the inline "Replace files" bar; there is no permanent overwrite flag.
    p.force = true;
    // Advanced options (Linux parity).
    p.analysis_mode = analysis_mode_->currentText().trimmed().toStdString();
    p.analysis_fps = analysis_fps_->value();
    p.tile_size = tile_size_->value();
    p.key_interval_seconds = key_interval_->value();
    p.all_tracks = all_tracks_->isChecked();
    p.preserve_metadata = preserve_metadata_->isChecked();
    if (p.video_codec.empty()) p.video_codec = "auto";
    if (p.audio_codec.empty()) p.audio_codec = "auto";
    if (p.subtitle_mode.empty()) p.subtitle_mode = "auto";
    return p;
}

// --- Conversion ------------------------------------------------------------

bool MainWindow::prepareJobs(std::vector<ConversionJob>& jobs, QString& error) const {
    const QStringList sources = currentSources();
    if (sources.isEmpty()) {
        error = "Choose one or more existing source files first.";
        return false;
    }
    const QString output_dir = output_dir_->text().trimmed();
    if (output_dir.isEmpty()) {
        error = "Choose an output folder first.";
        return false;
    }
    const ConversionProfile profile = currentProfile();
    const Direction dir = profile.direction;

    for (const QString& src : sources) {
        const std::string source = src.toUtf8().toStdString();
        casu::CasuKind kind = casu::CasuKind::None;
        try {
            kind = casu::detect_casu_kind(source);
        } catch (const std::exception& exc) {
            error = QString("Could not inspect %1: %2").arg(src).arg(QString::fromUtf8(exc.what()));
            return false;
        }
        const bool is_casu = kind != casu::CasuKind::None;
        if (dir == Direction::FromCasu && !is_casu) {
            error = QString("From-CASU mode accepts only verified CASU content: %1").arg(src);
            return false;
        }
        if (dir != Direction::FromCasu && is_casu) {
            error = QString("This mode expects ordinary media; use From-CASU for CASU content: %1").arg(src);
            return false;
        }
        std::string output;
        try {
            output = ConversionEngine::plan_output(source, output_dir.toUtf8().toStdString(), profile);
        } catch (const std::exception& exc) {
            error = QString::fromUtf8(exc.what());
            return false;
        }
        if (output == source) {
            error = QString("An output would overwrite its source: %1").arg(src);
            return false;
        }
        jobs.push_back(ConversionJob{source, output, profile});
    }
    std::set<std::string> outputs;
    for (const ConversionJob& job : jobs) {
        if (!outputs.insert(job.output).second) {
            error = "Multiple sources map to the same output name. Choose a different output "
                    "folder or convert them separately.";
            return false;
        }
    }
    return true;
}

void MainWindow::startConversion() {
    if (busy_) return;
    std::vector<ConversionJob> jobs;
    QString error;
    if (!prepareJobs(jobs, error)) {
        showToast(error, true);
        status_->setText(error);
        return;
    }

    // Linux parity ("Resume verified jobs"): reuse hash-verified results from
    // a previous identical batch via the conversion journal inside the engine.
    // The job set stays complete so the journal identity matches.
    bool any_exists = false;
    for (const ConversionJob& job : jobs) {
        std::error_code ec;
        if (std::filesystem::exists(job.output, ec)) {
            any_exists = true;
            break;
        }
    }
    if (any_exists) {
        // Linux parity: inline red confirmation bar instead of a popup.
        pending_jobs_ = jobs;
        confirm_label_->setText(
            QString("%1 output file(s) already exist. Replace them?").arg((int)jobs.size()));
        confirm_frame_->show();
        status_->setText("Existing outputs detected — choose Replace files or Keep existing.");
        return;
    }
    runJobs(jobs);
}

void MainWindow::runJobs(std::vector<ConversionJob> jobs) {
    busy_ = true;
    paused_ = false;
    cancel_->store(false);
    pause_->store(false);
    progress_->setValue(0);
    status_->setText("Preparing verified conversion jobs…");
    convert_button_->setEnabled(false);
    cancel_button_->setEnabled(true);
    pause_button_->setEnabled(true);
    pause_button_->setText("Pause queue");

    results_ = std::make_shared<std::vector<ConversionResult>>();
    worker_thread_ = std::thread(
        [this, jobs = std::move(jobs)]() mutable {
            ConversionProfile profile = jobs.empty() ? ConversionProfile{} : jobs.front().profile;
            const int retries = retries_ ? retries_->value() : 0;
            QString summary;
            try {
                *results_ = ConversionEngine{}.run(
                    jobs, sync_ffmpeg_executor(),
                    [this](const ConversionProgress& p) { onProgress(p); },
                    [this]() { return cancel_->load(); },
                    [this]() { return pause_->load(); }, retries,
                    resume_jobs_ && resume_jobs_->isChecked(),
                    output_dir_->text().trimmed().toUtf8().toStdString());
                write_batch_report(output_dir_->text().trimmed().toUtf8().toStdString(),
                                   "COMPLETE", profile, retries, *results_);
                summary = "done";
                QMetaObject::invokeMethod(this, [this, summary] { onFinished(summary); },
                                          Qt::QueuedConnection);
            } catch (const ConversionCancelled&) {
                write_batch_report(output_dir_->text().trimmed().toUtf8().toStdString(),
                                   "CANCELLED", profile, retries, *results_);
                summary = "Conversion cancelled";
                QMetaObject::invokeMethod(this, [this, summary] { onFinished(summary); },
                                          Qt::QueuedConnection);
            } catch (const std::exception& exc) {
                write_batch_report(output_dir_->text().trimmed().toUtf8().toStdString(),
                                   "FAILED", profile, retries, *results_);
                summary = QString("Conversion failed: %1").arg(QString::fromUtf8(exc.what()));
                QMetaObject::invokeMethod(this, [this, summary] { onFinished(summary); },
                                          Qt::QueuedConnection);
            }
        });
}

void MainWindow::pauseQueue() {
    if (!busy_) return;
    paused_ = !paused_;
    pause_->store(paused_);
    pause_button_->setText(paused_ ? "Resume queue" : "Pause queue");
    status_->setText(paused_ ? "Queue paused — converting resumes on demand."
                             : "Queue resumed.");
}

// Linux parity (verify_output): verify every output file in the output
// directory and write a JSON report next to it.
void MainWindow::verifyOutput() {
    const QDir directory(output_dir_->text().trimmed());
    if (!directory.exists()) {
        showToast("Choose an existing output folder first.", true);
        return;
    }
    const bool from_casu_or_media =
        currentDirection() != Direction::ToCasu;
    int checked = 0, passed = 0;
    QStringList failures;

    if (from_casu_or_media) {
        QString ext = format_->currentText().trimmed().toLower();
        if (ext.isEmpty()) ext = "mp4";
        const QStringList files = directory.entryList(
            QStringList{QString("*.%1").arg(ext)}, QDir::Files, QDir::Name);
        if (files.isEmpty()) {
            showToast(QString("No .%1 exports found in the output folder.").arg(ext), false);
            return;
        }
        for (const QString& name : files) {
            ++checked;
            const std::string path = directory.filePath(name).toUtf8().toStdString();
            try {
                casu::media::MediaInfo info = casu::media::probe(path);
                bool playable = false;
                for (const auto& s : info.streams)
                    if (s.codec_type == "audio" || s.codec_type == "video") playable = true;
                if (!playable) throw std::runtime_error("no playable audio/video stream");
                ++passed;
            } catch (const std::exception& exc) {
                failures << QString("%1: %2").arg(name, QString::fromUtf8(exc.what()));
            }
        }
    } else {
        const QStringList files = directory.entryList(QStringList{"*.casu"},
                                                      QDir::Files, QDir::Name);
        if (files.isEmpty()) {
            showToast("No .casu files found in the output folder.", false);
            return;
        }
        for (const QString& name : files) {
            ++checked;
            const std::string path = directory.filePath(name).toUtf8().toStdString();
            try {
                std::ifstream in(path, std::ios::binary);
                char magic[8] = {};
                in.read(magic, 8);
                if (std::memcmp(magic, "CASUNAT1", 8) == 0) {
                    casu::casunat1::read_native(path, true);
                } else {
                    // sidecar manifest: parse + basic validation
                    const std::string payload((std::istreambuf_iterator<char>(in)),
                                              std::istreambuf_iterator<char>());
                    const JsonValue doc = casu::parse_json(payload);
                    if (!doc.is_object() || doc.find("source") == nullptr)
                        throw std::runtime_error("invalid CASU sidecar manifest");
                }
                ++passed;
            } catch (const std::exception& exc) {
                failures << QString("%1: %2").arg(name, QString::fromUtf8(exc.what()));
            }
        }
    }

    // Report files mirror the Linux names.
    const QString report_name = from_casu_or_media ? "casu_media_verify_report.json"
                                                   : "casu_verify_report.json";
    QFile report(directory.filePath(report_name));
    if (report.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        const QString payload = QString(
            "{\"version\":1,\"checked\":%1,\"passed\":%2,\"failed\":%3}")
            .arg(checked).arg(passed).arg(failures.size());
        report.write(payload.toUtf8());
    }
    if (!failures.isEmpty()) {
        showToast(QString("%1/%2 file(s) passed. Details: %3")
                      .arg(passed).arg(checked).arg(report.fileName()), true);
    } else {
        showToast(QString("%1/%2 file(s) verified successfully. Report: %3")
                      .arg(passed).arg(checked).arg(report.fileName()), false);
    }
}

// Linux parity (show_last_report): summarize casu_batch_report.json.
void MainWindow::showLastReport() {
    const QDir directory(output_dir_->text().trimmed());
    if (!directory.exists()) {
        showToast("Choose an existing output folder first.", true);
        return;
    }
    QFile report(directory.filePath("casu_batch_report.json"));
    if (!report.open(QIODevice::ReadOnly)) {
        showToast(QString("No batch report found in %1").arg(directory.path()), true);
        return;
    }
    const QJsonDocument doc = QJsonDocument::fromJson(report.readAll());
    if (!doc.isObject()) {
        showToast("Batch report is unreadable.", true);
        return;
    }
    const QJsonObject payload = doc.object();
    const QJsonArray files = payload.value("files").toArray();
    QDialog dlg(this);
    dlg.setWindowTitle("CASU · Last conversion report");
    dlg.resize(1050, 540);
    auto* layout = new QVBoxLayout(&dlg);
    const QString heading = QString("State: %1  ·  Container: %2  ·  Mode: %3  ·  Files: %4")
                                .arg(payload.value("state").toString("COMPLETE"),
                                     payload.value("container").toString("unknown"),
                                     payload.value("mode").toString("unknown"))
                                .arg(files.size());
    auto* head = new QLabel(heading, &dlg);
    layout->addWidget(head);
    auto* text = new QTextEdit(&dlg);
    text->setReadOnly(true);
    text->setPlainText(QString::fromUtf8(QJsonDocument(payload).toJson()));
    layout->addWidget(text);
    auto* buttons = new QDialogButtonBox(QDialogButtonBox::Close, &dlg);
    connect(buttons, &QDialogButtonBox::accepted, &dlg, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, &dlg, &QDialog::reject);
    layout->addWidget(buttons);
    dlg.exec();
}

void MainWindow::cancelConversion() {
    if (!busy_) return;
    cancel_->store(true);
    cancel_button_->setEnabled(false);
    status_->setText("Cancellation requested — stopping converter…");
}

void MainWindow::onProgress(const ConversionProgress& p) {
    progress_->setValue(int(p.overall * 1000.0));
    const QString name = QFileInfo(QString::fromUtf8(p.source.c_str())).fileName();
    // Reference report() parity: "<State> <name> (i/n) · <elapsed> s · ETA <x> s".
    const QString eta = p.eta_seconds < 0.0
                            ? QStringLiteral("ETA --")
                            : QStringLiteral("ETA %1 s")
                                  .arg(int(std::lround(p.eta_seconds)));
    status_->setText(QString("%1 %2 (%3/%4) · %5 s · %6")
                         .arg(state_name(p.state))
                         .arg(name)
                         .arg(p.job_index + 1)
                         .arg(p.job_count)
                         .arg(p.elapsed_seconds, 0, 'f', 1)
                         .arg(eta));
}

void MainWindow::onFinished(const QString& summary) {
    busy_ = false;
    paused_ = false;
    pause_->store(false);
    convert_button_->setEnabled(true);
    cancel_button_->setEnabled(false);
    pause_button_->setEnabled(false);
    pause_button_->setText("Pause queue");

    QString detail = summary;
    if (results_) {
        int ok = 0, failed = 0;
        for (const ConversionResult& r : *results_) {
            if (r.status == "converted" || r.status == "exported") ++ok;
            else ++failed;
        }
        detail = QString("Converted %1/%2 file(s); %3 failed.")
                     .arg(ok)
                     .arg((int)results_->size())
                     .arg(failed);
    }
    progress_->setValue(1000);
    status_->setText(detail);
    if (!summary.startsWith("Conversion cancelled")) showToast(detail, detail.contains("failed"));
    if (worker_thread_.joinable()) worker_thread_.join();
}

void MainWindow::showToast(const QString& text, bool error) {
    toast_->setObjectName(error ? "ToastError" : "Toast");
    toast_->setText(text);
    toast_->show();
    QTimer::singleShot(2600, toast_, [this]() { toast_->hide(); });
}

}  // namespace casu::conv