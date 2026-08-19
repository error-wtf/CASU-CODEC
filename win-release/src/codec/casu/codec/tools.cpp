// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/codec/tools.hpp"

#include <cstdlib>
#include <filesystem>
#include <string>
#include <vector>

#ifdef _WIN32
#include <windows.h>
#endif

namespace casu::codec {

namespace {
std::string uppercase(const std::string& value) {
    std::string out = value;
    for (char& c : out) {
        if (c >= 'a' && c <= 'z') c = char(c - ('a' - 'A'));
    }
    return out;
}

bool looks_executable(const std::filesystem::path& p) {
    std::error_code ec;
    const bool exists = std::filesystem::is_regular_file(p, ec);
    return exists && !ec;
}

// Directory of the running executable (so bundled helpers are found
// regardless of the current working directory — required by the packaged
// layout where tools/ sits next to the .exe).
std::string executable_dir() {
#ifdef _WIN32
    char buffer[MAX_PATH];
    const DWORD n = GetModuleFileNameA(nullptr, buffer, MAX_PATH);
    if (n > 0 && n < MAX_PATH) {
        std::filesystem::path exe(buffer);
        std::error_code ec;
        std::filesystem::path dir = exe.parent_path();
        return ec ? std::string() : dir.string();
    }
#endif
    return {};
}

std::string search_path_for(const std::string& exe_name) {
    const char* raw = std::getenv("PATH");
    if (!raw || !*raw) return {};
    const std::string path = raw;
    std::size_t pos = 0;
    while (pos <= path.size()) {
        std::size_t sep = path.find_first_of(";:", pos);
        const std::size_t len = (sep == std::string::npos) ? std::string::npos : (sep - pos);
        const std::string dir = path.substr(pos, len);
        if (!dir.empty()) {
            std::filesystem::path candidate = std::filesystem::path(dir) / exe_name;
            if (looks_executable(candidate)) {
                std::error_code ec;
                std::filesystem::path absolute = std::filesystem::absolute(candidate, ec);
                return ec ? candidate.string() : absolute.string();
            }
        }
        if (sep == std::string::npos) break;
        pos = sep + 1;
    }
    return {};
}
}  // namespace

std::string find_tool(const std::string& name) {
    const std::string env_key = "CASU_" + uppercase(name);
    if (const char* value = std::getenv(env_key.c_str())) {
        if (value && *value && looks_executable(value)) return value;
    }
    const std::string exe_name = name + ".exe";
    // 1) Packaged layout: <exe_dir>/tools/<name>.exe
    // 2) Dev layout:      <exe_dir>/third_party/tools/<name>.exe
    // 3) Dev layout (cwd): third_party/tools/<name>.exe
    // 4) PATH
    std::vector<std::filesystem::path> candidates;
    const std::string exe_dir = executable_dir();
    if (!exe_dir.empty()) {
        candidates.emplace_back(std::filesystem::path(exe_dir) / "tools" / exe_name);
        candidates.emplace_back(std::filesystem::path(exe_dir) / "third_party" / "tools" / exe_name);
    }
    candidates.emplace_back(std::filesystem::path("third_party") / "tools" / exe_name);
    for (const std::filesystem::path& candidate : candidates) {
        if (looks_executable(candidate)) {
            std::error_code ec;
            std::filesystem::path absolute = std::filesystem::absolute(candidate, ec);
            return ec ? candidate.string() : absolute.string();
        }
    }
    return search_path_for(exe_name);
}

std::string ffmpeg_path() { return find_tool("ffmpeg"); }
std::string ffprobe_path() { return find_tool("ffprobe"); }

}  // namespace casu::codec
