// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Portable settings store for MPCASU (WP-MPCASU-032). JSON file beside the
// config dir, never the Windows registry. Persists volume/mute/rate,
// shuffle/repeat, output folders and session data.
#pragma once
#include <QString>
#include <QStringList>

namespace mpcasu {

struct AppSettings {
    int volume = 100;
    bool muted = false;
    double rate = 1.0;
    bool shuffle = false;
    QString repeat = "off";
    QString snapshot_dir;
    QString record_dir;
    QString library_dir;
    QString last_playlist;
};

class SettingsStore {
public:
    explicit SettingsStore(QString path) : path_(std::move(path)) {}

    AppSettings load() const;
    void save(const AppSettings& s) const;
    void apply(AppSettings* s) const { *s = load(); }

private:
    QString path_;
};

// Config directory (beside the exe for portability).
QString app_config_dir();

}  // namespace mpcasu
