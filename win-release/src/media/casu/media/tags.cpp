// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/media/tags.hpp"

#include "casu/codec/ffmpeg.hpp"
#include "casu/codec/ffprobe.hpp"
#include "casu/media/mediainfo.hpp"

#include <algorithm>
#include <filesystem>
#include <regex>
#include <set>
#include <string>

namespace casu::media {

namespace {

const std::set<std::string>& media_extensions() {
    static const std::set<std::string> value = {
        ".mp3", ".mp4", ".m4a", ".m4v", ".mov", ".mkv", ".webm", ".flac",
        ".wav", ".ogg", ".opus", ".aac", ".aiff", ".alac", ".wma", ".mpg",
        ".mpeg", ".ts", ".m2ts", ".avi", ".casu", ".mp5",
    };
    return value;
}

const std::vector<std::string>& tag_keys() {
    static const std::vector<std::string> value = {
        "title", "artist", "album_artist", "album", "genre",
        "track", "date", "year", "comment",
    };
    return value;
}

std::string lowercase_extension(const std::string& path) {
    std::string ext = std::filesystem::path(path).extension().string();
    for (char& c : ext) {
        if (c >= 'A' && c <= 'Z') c = char(c + ('a' - 'A'));
    }
    return ext;
}

std::string leading_track(const std::string& title, std::string& rest) {
    static const std::regex pattern(R"(^(\d{1,3})\s*[-._)\s]+\s*(.+)$)");
    std::smatch match;
    if (std::regex_search(title, match, pattern) && match.size() == 3) {
        rest = match[2].str();
        return match[1].str();
    }
    return {};
}

std::string year_at_end(const std::string& text) {
    static const std::regex pattern(R"([(\[]?(\d{4})[)\]]?\s*$)");
    std::smatch match;
    if (std::regex_search(text, match, pattern) && match.size() == 2)
        return match[1].str();
    return {};
}

void parse_filename(const std::string& path, std::map<std::string, std::string>& result) {
    const std::filesystem::path fs_path(path);
    const std::string name = fs_path.stem().string();
    std::vector<std::string> parts;
    for (const std::filesystem::path& part : fs_path.parent_path())
        parts.push_back(part.string());

    if (name.find(" - ") != std::string::npos) {
        const std::size_t sep = name.find(" - ");
        std::string artist = name.substr(0, sep);
        std::string title = name.substr(sep + 3);
        while (!artist.empty() && artist.back() == ' ') artist.pop_back();
        while (!title.empty() && title.front() == ' ') title.erase(title.begin());
        result.emplace("artist", artist);
        result.emplace("title", title);
    } else {
        result.emplace("title", name);
    }

    std::string rest;
    const std::string track = leading_track(result.at("title"), rest);
    if (!track.empty()) {
        result.emplace("track", track);
        result["title"] = rest;
    }

    if (!parts.empty()) result.emplace("album", parts.back());
    if (parts.size() >= 2) result.emplace("artist", parts[parts.size() - 2]);

    const std::string year = year_at_end(result.at("title"));
    if (!year.empty()) {
        result.emplace("year", year);
    } else if (result.count("year") == 0 && !parts.empty()) {
        const std::string album_year = year_at_end(parts.back());
        if (!album_year.empty()) result.emplace("year", album_year);
    }

    if (result.count("artist") == 0 && parts.size() >= 3)
        result.emplace("artist", parts[parts.size() - 3]);
}

std::string trim(const std::string& value) {
    std::size_t begin = 0;
    while (begin < value.size() && (value[begin] == ' ' || value[begin] == '\t' ||
                                    value[begin] == '\r' || value[begin] == '\n'))
        ++begin;
    std::size_t end = value.size();
    while (end > begin && (value[end - 1] == ' ' || value[end - 1] == '\t' ||
                           value[end - 1] == '\r' || value[end - 1] == '\n'))
        --end;
    return value.substr(begin, end - begin);
}

}  // namespace

std::map<std::string, std::string> metadata_for(const std::string& path) {
    std::map<std::string, std::string> result;
    const std::string extension = lowercase_extension(path);
    if (media_extensions().count(extension) == 0) return result;

    try {
        const MediaInfo info = probe(path);
        std::map<std::string, std::string> tags = info.format.tags;
        for (const MediaStreamInfo& stream : info.streams) {
            if (stream.codec_type != "audio") continue;
            for (const char* key : {"title", "artist", "album_artist", "album",
                                    "genre", "track", "date"}) {
                if (tags.count(key) == 0) {
                    const auto it = stream.tags.find(key);
                    if (it != stream.tags.end()) tags[key] = it->second;
                }
            }
        }
        for (const std::string& key : tag_keys()) {
            const auto it = tags.find(key);
            const std::string value = it == tags.end() ? std::string{} : trim(it->second);
            if (!value.empty()) result[key] = value;
        }
        if (info.format.duration > 0)
            result["duration"] = std::to_string(info.format.duration);
    } catch (const MediaProbeError&) {
        // Best effort: filename fallback only.
    }

    parse_filename(path, result);
    if (result.count("year") == 0) {
        const auto date = result.find("date");
        if (date != result.end()) {
            static const std::regex year_in(R"((\d{4}))");
            std::smatch match;
            if (std::regex_search(date->second, match, year_in) && match.size() == 2)
                result.emplace("year", match[1].str());
        }
    }
    return result;
}

bool extract_cover(const std::string& path, const std::string& output_path) {
    int cover_index = -1;
    try {
        const MediaInfo info = probe(path);
        for (const MediaStreamInfo& stream : info.streams) {
            if (stream.codec_type == "video" && stream.attached_pic) {
                cover_index = stream.index;
                break;
            }
        }
    } catch (const MediaProbeError&) {
        return false;
    }
    if (cover_index < 0) return false;
    try {
        casu::codec::Ffmpeg ffmpeg;
        const std::vector<std::string> args = {
            "-v", "error", "-y", "-i", path,
            "-map", "0:" + std::to_string(cover_index),
            "-frames:v", "1", "-c:v", "png", output_path,
        };
        casu::codec::ProcessResult result = ffmpeg.run_checked(args);
        std::error_code ec;
        return result.exit_code == 0 && std::filesystem::is_regular_file(output_path, ec);
    } catch (const casu::codec::MediaTranscodeError&) {
        return false;
    }
}

}  // namespace casu::media
