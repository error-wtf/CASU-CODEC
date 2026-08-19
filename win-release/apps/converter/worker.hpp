// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CASU-Converter — background conversion runner. Runs the headless
// ConversionEngine on a std::thread with a streaming ffmpeg executor (live
// progress from `-progress pipe:1`, clean kill on cancel). Progress and
// completion are marshalled to the GUI thread via queued functor invokeMethod
// (no Q_OBJECT/moc required in this AUTOMOC-free cross build).
#pragma once

#include "engine.hpp"

#include <QString>

#include <atomic>
#include <functional>
#include <memory>
#include <vector>

class QObject;

namespace casu::conv {

// Runs the batch on the calling thread; `ui_progress` / `ui_finished` are
// invoked on the GUI (UI) thread through a queued connection to `ui`.
void run_conversion_jobs(std::vector<ConversionJob> jobs,
                         std::shared_ptr<std::atomic<bool>> cancel,
                         std::shared_ptr<std::vector<ConversionResult>> results,
                         QObject* ui,
                         std::function<void(const ConversionProgress&)> ui_progress,
                         std::function<void(const QString&)> ui_finished);

}  // namespace casu::conv