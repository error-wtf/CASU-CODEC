// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// casu-cli — conversion journal / resume (WP-CLI-016). Port of
// casu/jobs.py conversion_journal_path / ConversionEngine._journal /
// ConversionEngine._load_resume: a crash-aware, hash-verified batch journal
// keyed by a deterministic identity of the exact job set.
#pragma once

#include "casu/json.hpp"

#include <map>
#include <string>
#include <utility>
#include <vector>

namespace casu::cli {

// One batch job as recorded in a journal (source/output/profile).
struct JournalJob {
    std::string source;                       // absolute, normalized
    std::string output;                       // absolute, normalized
    casu::JsonValue profile;                  // full ConversionProfile dict
};

// Stable, collision-resistant journal path for one exact batch
// (`.casu-conversion-<sha256[:16]>.json` in `directory`).
std::string conversion_journal_path(const std::string& directory,
                                    const std::vector<JournalJob>& jobs);

// Atomically write the journal payload
// {version, state, updated_ns, jobs, results}.
void write_journal(const std::string& path, const std::string& state,
                   const std::vector<JournalJob>& jobs,
                   const casu::JsonValue& results);

// Load a matching journal and return the reusable, hash-verified results
// keyed by (source, output). Throws casu::CasuError when the journal is
// invalid or does not match the requested jobs. Each reused result has its
// "resumed" flag set to true.
std::map<std::pair<std::string, std::string>, casu::JsonValue> load_resume(
    const std::string& path, const std::vector<JournalJob>& jobs);

}  // namespace casu::cli