// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/sidecar.hpp"
#include "casu/formats.hpp"
#include "casu/sha256.hpp"
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <sys/stat.h>

namespace casu {

namespace {

std::string read_file(const std::string& path, uint64_t limit) {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) throw CasuError("CASU manifest is unavailable: " + path);
    std::fseek(f, 0, SEEK_END);
    long sz = std::ftell(f);
    std::fseek(f, 0, SEEK_SET);
    if (sz < 0 || (uint64_t)sz > limit) { std::fclose(f); throw CasuError("CASU manifest exceeds its safety limit: " + path); }
    std::string out(sz, '\0');
    if (sz > 0 && std::fread(&out[0], 1, (std::size_t)sz, f) != (std::size_t)sz) {
        std::fclose(f); throw CasuError("could not read CASU manifest: " + path);
    }
    std::fclose(f);
    return out;
}

// Directory component of a path (no trailing separator), or empty.
std::string dirname(const std::string& path) {
    std::size_t slash = path.find_last_of("/\\");
    if (slash == std::string::npos) return "";
    return path.substr(0, slash);
}

// Basename component of a path.
std::string basename(const std::string& path) {
    std::size_t slash = path.find_last_of("/\\");
    if (slash == std::string::npos) return path;
    return path.substr(slash + 1);
}

bool file_exists(const std::string& path) {
    struct stat st;
    return stat(path.c_str(), &st) == 0;
}

uint64_t file_size(const std::string& path) {
    struct stat st;
    if (stat(path.c_str(), &st) != 0) throw CasuError("could not stat file: " + path);
    return (uint64_t)st.st_size;
}

}  // namespace

std::string resolve_casu_source(const std::string& manifest_path) {
    std::string manifest_str = read_file(manifest_path, 64ULL * 1024 * 1024);
    JsonValue manifest;
    try {
        manifest = parse_json(manifest_str);
    } catch (const JsonError&) {
        throw CasuError("invalid CASU manifest: " + manifest_path);
    }
    if (!manifest.is_object())
        throw CasuError("invalid CASU manifest: " + manifest_path);
    const JsonValue* source = manifest.find("source");
    if (!source || !source->is_object())
        throw CasuError("CASU manifest has no source: " + manifest_path);
    const JsonValue* source_path_v = source->find("path");
    const JsonValue* filename_v = source->find("filename");
    if (!source_path_v || !source_path_v->is_string() || !filename_v || !filename_v->is_string())
        throw CasuError("CASU source path/filename missing: " + manifest_path);
    std::string source_path = source_path_v->as_string();
    std::string filename = filename_v->as_string();

    // The recorded source basename must match the recorded filename.
    if (basename(source_path) != filename)
        throw CasuError("CASU source path does not match recorded filename: " + manifest_path);

    std::string candidate;
    if (file_exists(source_path)) {
        candidate = source_path;
    } else {
        // Fall back to the manifest directory + filename.
        std::string base = dirname(manifest_path);
        candidate = base.empty() ? filename : base + "/" + filename;
        if (!file_exists(candidate))
            throw CasuError("CASU source media not found: " + manifest_path);
        // The resolved candidate must stay inside the manifest directory.
        if (basename(candidate) != filename)
            throw CasuError("CASU source filename escapes manifest directory: " + manifest_path);
    }

    const JsonValue* size_v = source->find("size_bytes");
    if (size_v && !size_v->is_null() && size_v->is_number()) {
        if (file_size(candidate) != (uint64_t)size_v->as_double())
            throw CasuError("CASU source size mismatch: " + candidate);
    }
    const JsonValue* sha_v = source->find("sha256");
    if (sha_v && !sha_v->is_null() && sha_v->is_string()) {
        std::string expected = sha_v->as_string();
        if (expected.size() == 64 && sha256_file(candidate) != expected)
            throw CasuError("CASU source integrity mismatch: " + candidate);
    }
    return candidate;
}

}  // namespace casu
