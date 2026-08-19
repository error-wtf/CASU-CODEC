// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// casu-cli — shared helpers for the subcommand implementations.
#pragma once

#include "casu/formats.hpp"
#include "casu/json.hpp"

#include <cstdint>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace casu::cli {

// ---------------------------------------------------------------------------
// Argument model (argparse-like subset)
// ---------------------------------------------------------------------------
struct Args {
    std::vector<std::string> positional;
    std::map<std::string, std::string> options;  // "--name" -> value ("" = bare flag)

    bool has(const std::string& name) const { return options.count(name) != 0; }
    std::string get(const std::string& name, const std::string& fallback = {}) const {
        auto it = options.find(name);
        return it == options.end() ? fallback : it->second;
    }
    bool flag(const std::string& name) const {
        auto it = options.find(name);
        return it != options.end() && it->second.empty();
    }
    long long get_long(const std::string& name, long long fallback = 0) const;
    double get_double(const std::string& name, double fallback = 0.0) const;
};

// Parses argv starting after the command name. Tokens of the form "--x=v",
// "--x v", "-x v" and bare flags are supported; everything else is positional.
Args parse_args(const std::vector<std::string>& tokens);

// ---------------------------------------------------------------------------
// JSON / filesystem helpers
// ---------------------------------------------------------------------------
// Pretty print with indent=2, "key": value, ", " separators and UTF-8 output
// (semantically identical to the reference json.dumps(indent=2,
// ensure_ascii=False)).
std::string pretty_json(const JsonValue& value);

// Compact canonical JSON (casu::dump_json) plus a trailing newline.
std::string compact_json(const JsonValue& value);

// Atomic text write (temp + rename) mirroring atomic_write_text.
void atomic_write_text(const std::string& path, const std::string& payload);

// Absolute lexical path string (for JSON containers/inputs).
std::string abs_path(const std::string& path);
std::string basename(const std::string& path);

// First 8 bytes of a file (for CASUNAT1/CASUNAT2 magic dispatch). Returns
// false on read failure.
bool read_magic(const std::string& path, std::string& magic);

std::string kind_name(casu::CasuKind kind);

// ---------------------------------------------------------------------------
// Batch planning (mirrors cli.py plan_conversion_inputs / plan_export_inputs)
// ---------------------------------------------------------------------------
// Expands files/folders into (source, relative) pairs, skipping CASU content.
// When `casu_only` is true only CASU representations are collected.
std::vector<std::pair<std::string, std::string>> plan_inputs(
    const std::vector<std::string>& items, bool casu_only);

// Mirrors plan_conversion_targets: target = output_dir/relative with .casu
// suffix, disambiguating collisions by a deterministic source digest.
std::vector<std::string> plan_casu_targets(
    const std::vector<std::pair<std::string, std::string>>& planned,
    const std::string& output_dir);

// Mirrors plan_export_targets for an arbitrary extension.
std::vector<std::string> plan_format_targets(
    const std::vector<std::pair<std::string, std::string>>& planned,
    const std::string& output_dir, const std::string& extension);

// ---------------------------------------------------------------------------
// Probe-based CASU analysis (reduced reference `analyze`)
// ---------------------------------------------------------------------------
// Builds a valid CASU manifest from an ffprobe of the source. Temporal
// segmentation is reduced to one whole-duration segment per playable stream
// (the reference's numpy/ffmpeg state analysis is a separate port step).
// Throws casu::CasuError.
casu::JsonValue build_manifest(const std::string& source, const std::string& mode);

// A report payload is a JSON object with a "files" array of entries that carry
// a "status" field. Returns true when no entry has status "failed".
bool error_all_ok(const casu::JsonValue& payload);

}  // namespace casu::cli
