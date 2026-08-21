// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CASU-Converter — main window (Qt Widgets GUI, red/black design). Three
// steps mirroring casu_converter.py: sources -> direction -> options, then
// convert with live progress + cancel on a std::thread (no Q_OBJECT/moc).
#pragma once

#include "engine.hpp"

#include <QMainWindow>

#include <atomic>
#include <memory>
#include <thread>
#include <vector>

class QCheckBox;
class QComboBox;
class QDoubleSpinBox;
class QFrame;
class QLabel;
class QLineEdit;
class QListWidget;
class QProgressBar;
class QPushButton;
class QSpinBox;

namespace casu::conv {

class MainWindow : public QMainWindow {
public:
    explicit MainWindow(QWidget* parent = nullptr);

protected:
    void dragEnterEvent(QDragEnterEvent* event) override;
    void dropEvent(QDropEvent* event) override;
    void closeEvent(QCloseEvent* event) override;

private:
    void chooseFiles();
    void chooseFolder();
    void chooseOutputDir();
    void removeSelected();
    void clearQueue();
    void syncDirectionOptions();
    void startConversion();
    void runJobs(std::vector<ConversionJob> jobs);
    void cancelConversion();
    void pauseQueue();
    void verifyOutput();
    void showLastReport();
    void onProgress(const ConversionProgress& progress);
    void onFinished(const QString& summary);

    void addSources(const QStringList& paths);
    QStringList currentSources() const;
    Direction currentDirection() const;
    CasuContainer currentCasuContainer() const;
    ConversionProfile currentProfile() const;
    bool prepareJobs(std::vector<ConversionJob>& jobs, QString& error) const;
    void showToast(const QString& text, bool error);

    QLineEdit* output_dir_ = nullptr;
    QListWidget* queue_ = nullptr;
    QLabel* source_info_ = nullptr;
    QLabel* status_ = nullptr;
    QLabel* toast_ = nullptr;
    QComboBox* direction_ = nullptr;
    QComboBox* format_ = nullptr;
    QComboBox* preset_ = nullptr;
    QComboBox* container_ = nullptr;
    QComboBox* video_codec_ = nullptr;
    QComboBox* audio_codec_ = nullptr;
    QComboBox* subtitle_mode_ = nullptr;
    QCheckBox* overwrite_ = nullptr;
    QWidget* media_options_ = nullptr;
    QWidget* casu_options_ = nullptr;
    // Linux parity: collapsible "Advanced options" frame.
    QPushButton* advanced_btn_ = nullptr;
    QWidget* advanced_frame_ = nullptr;
    QComboBox* analysis_mode_ = nullptr;
    QDoubleSpinBox* analysis_fps_ = nullptr;
    QSpinBox* retries_ = nullptr;
    QSpinBox* tile_size_ = nullptr;
    QDoubleSpinBox* key_interval_ = nullptr;
    QCheckBox* all_tracks_ = nullptr;
    QCheckBox* preserve_metadata_ = nullptr;
    QCheckBox* resume_jobs_ = nullptr;
    // Inline overwrite confirmation (Linux parity: no popup).
    QFrame* confirm_frame_ = nullptr;
    QLabel* confirm_label_ = nullptr;
    QProgressBar* progress_ = nullptr;
    QPushButton* convert_button_ = nullptr;
    QPushButton* cancel_button_ = nullptr;
    QPushButton* pause_button_ = nullptr;

    bool busy_ = false;
    bool paused_ = false;
    std::vector<ConversionJob> pending_jobs_;  // awaiting "Replace files" confirm
    std::thread worker_thread_;
    std::shared_ptr<std::atomic<bool>> cancel_ = std::make_shared<std::atomic<bool>>(false);
    std::shared_ptr<std::atomic<bool>> pause_ = std::make_shared<std::atomic<bool>>(false);
    std::shared_ptr<std::vector<ConversionResult>> results_;
};

}  // namespace casu::conv