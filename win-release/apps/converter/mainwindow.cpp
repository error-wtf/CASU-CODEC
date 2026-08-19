// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "mainwindow.hpp"

#include "theme.hpp"
#include "worker.hpp"

#include "casu/formats.hpp"

#include <QCheckBox>
#include <QCloseEvent>
#include <QComboBox>
#include <QDir>
#include <QDragEnterEvent>
#include <QDropEvent>
#include <QFileDialog>
#include <QFileInfo>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMessageBox>
#include <QMimeData>
#include <QProgressBar>
#include <QPushButton>
#include <QTimer>
#include <QVBoxLayout>

#include <algorithm>
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
    row_a->addWidget(hint(media_options_, "Preset"));
    preset_ = make_combo(media_options_);
    preset_->addItems({"remux", "balanced", "high", "small", "lossless"});
    preset_->setCurrentText("balanced");
    row_a->addWidget(preset_);
    row_a->addWidget(hint(media_options_, "Overwrite existing outputs"));
    overwrite_ = new QCheckBox(media_options_);
    row_a->addWidget(overwrite_);
    row_a->addStretch(1);
    media_layout->addLayout(row_a);

    auto* row_b = new QHBoxLayout();
    row_b->addWidget(hint(media_options_, "Video codec"));
    video_codec_ = make_combo(media_options_);
    video_codec_->setEditable(true);
    video_codec_->addItems({"auto", "libx264", "libx265", "libvpx-vp9", "libaom-av1", "ffv1", "mpeg4", "mpeg2video"});
    row_b->addWidget(video_codec_);
    row_b->addWidget(hint(media_options_, "Audio codec"));
    audio_codec_ = make_combo(media_options_);
    audio_codec_->setEditable(true);
    audio_codec_->addItems({"auto", "aac", "libmp3lame", "libopus", "libvorbis", "flac", "alac", "pcm_s16le"});
    row_b->addWidget(audio_codec_);
    row_b->addWidget(hint(media_options_, "Subtitles"));
    subtitle_mode_ = make_combo(media_options_);
    subtitle_mode_->addItems({"auto", "copy", "drop"});
    row_b->addWidget(subtitle_mode_);
    row_b->addStretch(1);
    media_layout->addLayout(row_b);
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
    casu_layout->addWidget(hint(casu_options_, "Overwrite existing outputs"));
    auto* casu_overwrite = new QCheckBox(casu_options_);
    casu_layout->addWidget(casu_overwrite);
    casu_layout->addStretch(1);
    step3_layout->addWidget(casu_options_);
    root->addWidget(step3);

    // --- Actions + progress ---
    auto* action_row = new QHBoxLayout();
    convert_button_ = new QPushButton("Convert", central);
    convert_button_->setObjectName("Primary");
    cancel_button_ = new QPushButton("Cancel", central);
    cancel_button_->setEnabled(false);
    action_row->addWidget(convert_button_);
    action_row->addWidget(cancel_button_);
    action_row->addStretch(1);
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
    connect(casu_overwrite, &QCheckBox::toggled, this,
            [this](bool checked) { overwrite_->setChecked(checked); });

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
    QStringList paths;
    const QDir root(folder);
    const QStringList entries = root.entryList(QDir::Files | QDir::NoDotAndDotDot, QDir::Name);
    for (const QString& name : entries) paths.append(root.filePath(name));
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
    p.force = overwrite_->isChecked();
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

    bool any_exists = false;
    for (const ConversionJob& job : jobs) {
        std::error_code ec;
        if (std::filesystem::exists(job.output, ec)) {
            any_exists = true;
            break;
        }
    }
    if (any_exists && !jobs.front().profile.force) {
        const QMessageBox::StandardButton answer = QMessageBox::question(
            this, "Overwrite outputs",
            QString("%1 output file(s) already exist. Replace them?").arg((int)jobs.size()),
            QMessageBox::Yes | QMessageBox::No, QMessageBox::No);
        if (answer != QMessageBox::Yes) {
            status_->setText("Replace cancelled — existing outputs were kept.");
            return;
        }
    }

    busy_ = true;
    cancel_->store(false);
    progress_->setValue(0);
    status_->setText("Preparing verified conversion jobs…");
    convert_button_->setEnabled(false);
    cancel_button_->setEnabled(true);

    results_ = std::make_shared<std::vector<ConversionResult>>();
    worker_thread_ = std::thread([this, jobs = std::move(jobs)]() mutable {
        run_conversion_jobs(std::move(jobs), cancel_, results_, this,
                            [this](const ConversionProgress& p) { onProgress(p); },
                            [this](const QString& s) { onFinished(s); });
    });
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
    status_->setText(QString("%1 · %2 (%3/%4)")
                         .arg(state_name(p.state))
                         .arg(name)
                         .arg(p.job_index + 1)
                         .arg(p.job_count));
}

void MainWindow::onFinished(const QString& summary) {
    busy_ = false;
    convert_button_->setEnabled(true);
    cancel_button_->setEnabled(false);

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