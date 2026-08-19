// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Bounded temporary media owned by one loopback web-player server (port of
// web_casu.py TranscodeStore, WP-WEBAPI-003). Token registry with eviction,
// bounded uploads, URL registration and temp-dir cleanup. The FFmpeg/CASU
// transcode step itself is supplied by the app phase (casu_codec/casu_media).
#pragma once
#include <cstdint>
#include <map>
#include <mutex>
#include <string>
#include <vector>

namespace casu::webapi {

struct TranscodeSession {
    std::string token;
    std::string kind;         // "file" | "url"
    std::string path;         // file path (kind == "file")
    std::string source;       // media URL (kind == "url")
    std::string content_type;
    std::string target;       // "mp4"/"webm"
    int64_t size_bytes = -1;
    int64_t created_ms = 0;
    bool live = false;        // live-transcoded stream (kind == "url")
};

class TranscodeStore {
public:
    TranscodeStore();
    explicit TranscodeStore(const std::string& root_dir);
    ~TranscodeStore();
    TranscodeStore(const TranscodeStore&) = delete;
    TranscodeStore& operator=(const TranscodeStore&) = delete;

    const std::string& root() const { return root_; }
    size_t size() const;

    std::string register_file(const std::string& path, const std::string& content_type,
                              const std::string& target = "");
    std::string register_url(const std::string& url, const std::string& content_type,
                             const std::string& target = "mp4");
    std::string upload(const uint8_t* data, uint64_t length, const std::string& filename,
                       const std::string& target = "mp4");
    std::string upload(const std::string& bytes, const std::string& filename,
                       const std::string& target = "mp4");

    bool get(const std::string& token, TranscodeSession* out) const;
    bool remove(const std::string& token);
    void sweep(size_t max_sessions = 64);
    void close();
    std::vector<std::string> tokens() const;

private:
    std::string new_token() const;
    void add_locked(TranscodeSession session);
    static std::string create_temp_root();
    static std::string append_suffix(const std::string& filename, const std::string& fallback);
    int64_t now_ms() const;

    std::string root_;
    mutable std::mutex mtx_;
    std::map<std::string, TranscodeSession> sessions_;
};

}  // namespace casu::webapi