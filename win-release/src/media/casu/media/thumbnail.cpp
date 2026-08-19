// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/media/thumbnail.hpp"

#include "casu/codec/ffmpeg.hpp"
#include "casu/sha256.hpp"

#include <cstdio>
#include <filesystem>
#include <string>
#include <vector>

namespace casu::media {

namespace {

constexpr std::size_t kMaxThumbnailBytes = 4 * 1024 * 1024;

bool looks_like_ppm(const std::string& path) {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) return false;
    char magic[2] = {0, 0};
    const std::size_t n = std::fread(magic, 1, 2, f);
    std::fclose(f);
    return n == 2 && magic[0] == 'P' && magic[1] == '6';
}

}  // namespace

std::string thumbnail_for(const std::string& source, const std::string& cache_directory) {
    std::error_code ec;
    const std::filesystem::path media(source);
    if (!std::filesystem::is_regular_file(media, ec)) return {};

    const std::string size_str = std::to_string(std::filesystem::file_size(media, ec));
    const std::filesystem::file_time_type mtime = std::filesystem::last_write_time(media, ec);
    const auto mtime_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
        mtime.time_since_epoch()).count();
    const std::string identity =
        std::filesystem::absolute(media, ec).lexically_normal().string() + "\0" +
        size_str + "\0" + std::to_string(mtime_ns);
    const std::string name = casu::Sha256::oneshot(identity) + ".ppm";

    std::filesystem::create_directories(cache_directory, ec);
    const std::filesystem::path target = std::filesystem::path(cache_directory) / name;
    if (std::filesystem::is_regular_file(target, ec)) {
        const std::uintmax_t size = std::filesystem::file_size(target, ec);
        if (size > 0 && size <= kMaxThumbnailBytes) return target.string();
    }

    const std::string temporary =
        (std::filesystem::path(cache_directory) / ("." + name + ".tmp")).string();
    try {
        casu::codec::Ffmpeg ffmpeg;
        casu::codec::FfmpegRunOptions options;
        options.timeout_seconds = 20;
        const std::vector<std::string> args = {
            "-v", "error", "-ss", "1", "-i", source, "-map", "0:v:0",
            "-frames:v", "1", "-vf", "scale=320:180:force_original_aspect_ratio=decrease",
            "-f", "image2", "-vcodec", "ppm", "-y", temporary,
        };
        casu::codec::ProcessResult result = ffmpeg.run(args, options);
        if (result.exit_code != 0) {
            std::error_code ec2;
            std::filesystem::remove(temporary, ec2);
            return {};
        }
        const std::uintmax_t size = std::filesystem::file_size(temporary, ec);
        if (size == 0 || size > kMaxThumbnailBytes || !looks_like_ppm(temporary)) {
            std::error_code ec2;
            std::filesystem::remove(temporary, ec2);
            return {};
        }
        std::filesystem::remove(target, ec);
        std::filesystem::rename(temporary, target, ec);
        return ec ? std::string{} : target.string();
    } catch (const casu::codec::MediaTranscodeError&) {
        std::error_code ec2;
        std::filesystem::remove(temporary, ec2);
        return {};
    }
}

}  // namespace casu::media
