// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/webapi/transcode_store.hpp"

#include "casu/sha256.hpp"
#include "casu/network/url.hpp"
#include "casu/webapi/security.hpp"
#include "casu/webapi/webapi_error.hpp"

#include <chrono>
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <random>
#include <string>
#include <vector>

namespace casu::webapi {

namespace {

std::string trim(const std::string& s) {
    std::string r = s;
    while (!r.empty() && (r.front() == ' ' || r.front() == '\t' || r.front() == '\r' || r.front() == '\n')) r.erase(r.begin());
    while (!r.empty() && (r.back() == ' ' || r.back() == '\t' || r.back() == '\r' || r.back() == '\n')) r.pop_back();
    return r;
}

std::string env(const char* name) {
    const char* v = std::getenv(name);
    return v ? std::string(v) : std::string();
}

std::string random_hex(size_t bytes) {
    std::random_device rd;
    std::uniform_int_distribution<int> dist(0, 255);
    static const char* hexdig = "0123456789abcdef";
    std::string out;
    out.reserve(bytes * 2);
    for (size_t i = 0; i < bytes; ++i) {
        int v = dist(rd);
        out += hexdig[(v >> 4) & 0xF];
        out += hexdig[v & 0xF];
    }
    return out;
}

std::string file_suffix(const std::string& filename) {
    std::string f = filename;
    size_t dot = f.find_last_of('.');
    if (dot == std::string::npos || dot == 0 || dot + 1 >= f.size()) return {};
    std::string suf = f.substr(dot);
    if (suf.size() > 16) return {};
    for (char c : suf) {
        if (!std::isalnum(static_cast<unsigned char>(c)) && c != '.') return {};
    }
    return suf;
}

}  // namespace

TranscodeStore::TranscodeStore() : root_(create_temp_root()) {}
TranscodeStore::TranscodeStore(const std::string& root_dir) : root_(root_dir) {
    if (!root_.empty()) {
        std::error_code ec;
        std::filesystem::create_directories(root_, ec);
    }
}
TranscodeStore::~TranscodeStore() { close(); }

int64_t TranscodeStore::now_ms() const {
    using namespace std::chrono;
    return duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
}

std::string TranscodeStore::create_temp_root() {
    std::error_code ec;
    std::filesystem::path base = std::filesystem::temp_directory_path(ec);
    if (ec) base = std::filesystem::current_path();
    std::string dir = (base / ("casu-webapi-" + random_hex(6))).string();
    std::filesystem::create_directories(dir, ec);
    return dir;
}

std::string TranscodeStore::new_token() const {
    std::string material = random_hex(24) + "-" + std::to_string(now_ms());
    std::string digest = casu::Sha256::oneshot(material);
    return digest.substr(0, 32);
}

void TranscodeStore::add_locked(TranscodeSession session) {
    session.created_ms = now_ms();
    sessions_[session.token] = std::move(session);
}

std::string TranscodeStore::register_file(const std::string& path,
                                          const std::string& content_type,
                                          const std::string& target) {
    std::error_code ec;
    int64_t size = std::filesystem::file_size(path, ec);
    std::string token = new_token();
    TranscodeSession s;
    s.token = token;
    s.kind = "file";
    s.path = path;
    s.content_type = content_type;
    s.target = target;
    s.size_bytes = ec ? -1 : size;
    std::lock_guard<std::mutex> lock(mtx_);
    add_locked(std::move(s));
    return token;
}

std::string TranscodeStore::register_url(const std::string& url,
                                         const std::string& content_type,
                                         const std::string& target) {
    std::string clean = trim(url);
    casu::network::Url u;
    if (!casu::network::parse_url(clean, &u) ||
        !casu::network::is_network_scheme(u.scheme) || u.host.empty()) {
        throw WebApiError("only explicit network media URLs can be transcoded");
    }
    std::string token = new_token();
    TranscodeSession s;
    s.token = token;
    s.kind = "url";
    s.source = clean;
    s.content_type = content_type;
    s.target = target;
    s.live = true;
    std::lock_guard<std::mutex> lock(mtx_);
    add_locked(std::move(s));
    return token;
}

std::string TranscodeStore::upload(const uint8_t* data, uint64_t length,
                                   const std::string& filename, const std::string& target) {
    const uint64_t kMaxUpload = 16ULL * 1024 * 1024 * 1024;
    if (length == 0 || length > kMaxUpload) {
        throw WebApiError("upload size is invalid or exceeds 16 GiB");
    }
    std::string token = new_token();
    std::string suffix = file_suffix(sanitize_filename(filename));
    std::string path = root_ + "/upload-" + token + (suffix.empty() ? ".media" : suffix);
    {
        std::ofstream out(path, std::ios::binary | std::ios::trunc);
        if (!out) throw WebApiError("upload could not be stored");
        out.write(reinterpret_cast<const char*>(data), static_cast<std::streamsize>(length));
        if (!out) {
            out.close();
            std::remove(path.c_str());
            throw WebApiError("upload could not be stored");
        }
    }
    TranscodeSession s;
    s.token = token;
    s.kind = "file";
    s.path = path;
    s.target = target;
    s.size_bytes = static_cast<int64_t>(length);
    std::lock_guard<std::mutex> lock(mtx_);
    add_locked(std::move(s));
    return token;
}

std::string TranscodeStore::upload(const std::string& bytes, const std::string& filename,
                                   const std::string& target) {
    return upload(reinterpret_cast<const uint8_t*>(bytes.data()), bytes.size(), filename, target);
}

bool TranscodeStore::get(const std::string& token, TranscodeSession* out) const {
    std::lock_guard<std::mutex> lock(mtx_);
    auto it = sessions_.find(token);
    if (it == sessions_.end()) return false;
    if (out) *out = it->second;
    return true;
}

bool TranscodeStore::remove(const std::string& token) {
    std::lock_guard<std::mutex> lock(mtx_);
    auto it = sessions_.find(token);
    if (it == sessions_.end()) return false;
    if (it->second.kind == "file" && !it->second.path.empty()) {
        std::remove(it->second.path.c_str());
    }
    sessions_.erase(it);
    return true;
}

void TranscodeStore::sweep(size_t max_sessions) {
    std::lock_guard<std::mutex> lock(mtx_);
    while (sessions_.size() >= max_sessions) {
        std::string oldest;
        int64_t oldest_created = INT64_MAX;
        for (const auto& kv : sessions_) {
            if (kv.second.created_ms < oldest_created) {
                oldest_created = kv.second.created_ms;
                oldest = kv.first;
            }
        }
        if (oldest.empty()) break;
        auto it = sessions_.find(oldest);
        if (it->second.kind == "file" && !it->second.path.empty()) {
            std::remove(it->second.path.c_str());
        }
        sessions_.erase(it);
    }
}

void TranscodeStore::close() {
    std::lock_guard<std::mutex> lock(mtx_);
    for (auto& kv : sessions_) {
        if (kv.second.kind == "file" && !kv.second.path.empty()) {
            std::remove(kv.second.path.c_str());
        }
    }
    sessions_.clear();
    if (!root_.empty()) {
        std::error_code ec;
        std::filesystem::remove_all(root_, ec);
    }
}

std::vector<std::string> TranscodeStore::tokens() const {
    std::lock_guard<std::mutex> lock(mtx_);
    std::vector<std::string> out;
    out.reserve(sessions_.size());
    for (const auto& kv : sessions_) out.push_back(kv.first);
    return out;
}

size_t TranscodeStore::size() const {
    std::lock_guard<std::mutex> lock(mtx_);
    return sessions_.size();
}

}  // namespace casu::webapi