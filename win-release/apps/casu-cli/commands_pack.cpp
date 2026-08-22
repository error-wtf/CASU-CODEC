// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// casu-cli — container-writing subcommands: pack (CASUNAT1), pack-mp5,
// pack-v2 and repair-v2. pack-v2/repair-v2 fail with a clear, documented
// error: casu_core ships a CASUNAT2 reader but no writer yet.
#include "cli_util.hpp"

#include "casu/formats.hpp"
#include "casu/json.hpp"
#include "casu/media/mediainfo.hpp"
#include "casu/mp5.hpp"
#include "casu/native.hpp"
#include "casu/sha256.hpp"

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <string>
#include <tuple>
#include <vector>

namespace casu::cli {

using casu::CasuError;
using casu::JsonValue;

namespace {

constexpr std::size_t MP5_PART_BYTES = 16ULL * 1024 * 1024;

std::vector<uint8_t> read_source(const std::string& source) {
    std::error_code ec;
    const std::uintmax_t size = std::filesystem::file_size(source, ec);
    if (ec) throw CasuError("could not stat source: " + source);
    if (size > 512ULL * 1024 * 1024)
        throw CasuError("source too large for a single-part MP5 attachment");
    FILE* f = std::fopen(source.c_str(), "rb");
    if (!f) throw CasuError("could not read source: " + source);
    std::vector<uint8_t> data((std::size_t)size);
    const bool ok = std::fread(data.data(), 1, data.size(), f) == data.size();
    std::fclose(f);
    if (!ok) throw CasuError("could not read source: " + source);
    return data;
}

void put_le16(std::vector<uint8_t>& out, uint16_t value) {
    out.push_back(uint8_t(value));
    out.push_back(uint8_t(value >> 8));
}

// Attachment chunk payload: meta_len(2, LE) + JSON metadata + source bytes.
std::vector<uint8_t> attachment_payload(const std::vector<uint8_t>& bytes,
                                        std::size_t offset, std::size_t length,
                                        const std::string& filename, int part, int parts) {
    JsonObject meta;
    meta.items["filename"] = JsonValue(filename);
    meta.items["part"] = JsonValue((int64_t)part);
    meta.items["parts"] = JsonValue((int64_t)parts);
    const std::string meta_json = casu::dump_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(meta))));
    std::vector<uint8_t> payload;
    put_le16(payload, (uint16_t)meta_json.size());
    payload.insert(payload.end(), meta_json.begin(), meta_json.end());
    payload.insert(payload.end(), bytes.begin() + (std::ptrdiff_t)offset,
                   bytes.begin() + (std::ptrdiff_t)(offset + length));
    return payload;
}

}  // namespace

int cmd_pack(const Args& args) {
    const std::string source = args.positional.at(0);
    const std::string output = args.get("-o", args.get("--output", ""));
    if (output.empty()) throw CasuError("pack requires an output path (-o/--output)");
    const double analysis_fps = args.get_double("--analysis-fps", 10.0);
    if (analysis_fps <= 0) throw CasuError("analysis FPS must be positive");
    const std::string mode = args.get("--mode", "strict");

    const std::string source_abs = abs_path(source);
    const std::string output_abs = abs_path(output);
    if (source_abs == output_abs)
        throw CasuError("native CASU output must differ from source");
    std::error_code ec;
    if (!std::filesystem::exists(source_abs, ec))
        throw CasuError("source media does not exist: " + source);
    const std::uintmax_t size = std::filesystem::file_size(source_abs, ec);

    const JsonValue manifest = build_manifest(source_abs, mode, analysis_fps);
    casu::casunat1::write_native(output_abs, source_abs, manifest);

    JsonObject summary;
    summary.items["container"] = JsonValue(output_abs);
    summary.items["native_version"] = JsonValue(int64_t(1));
    summary.items["payload_bytes"] = JsonValue((int64_t)size);
    summary.items["mode"] = JsonValue(mode);
    std::printf("%s\n", pretty_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(summary)))).c_str());
    return 0;
}

int cmd_pack_mp5(const Args& args) {
    const double analysis_fps = args.get_double("--analysis-fps", 10.0);

    const std::string source = args.positional.at(0);
    const std::string output = args.get("-o", args.get("--output", ""));
    if (output.empty()) throw CasuError("pack-mp5 requires an output path (-o/--output)");
    const std::string mode = args.get("--mode", "strict");

    const std::string source_abs = abs_path(source);
    const std::string output_abs = abs_path(output);
    std::error_code ec;
    if (!std::filesystem::exists(source_abs, ec))
        throw CasuError("source media does not exist: " + source);
    const std::uintmax_t size = std::filesystem::file_size(source_abs, ec);

    const JsonValue manifest = build_manifest(source_abs, mode, analysis_fps);
    const std::vector<uint8_t> source_bytes = read_source(source_abs);
    const std::string filename = std::filesystem::path(source_abs).filename().string();

    casu::media::MediaInfo info;
    try {
        info = casu::media::probe(source_abs);
    } catch (const casu::media::MediaProbeError& exc) {
        throw CasuError(std::string("media probe failed: ") + exc.what());
    }

    std::vector<std::tuple<casu::mp5::ChunkType, uint8_t, uint32_t, std::vector<uint8_t>>> chunks;
    int stream_id = 1;
    for (const casu::media::MediaStreamInfo& stream : info.streams) {
        if (stream.codec_type != "video" && stream.codec_type != "audio") continue;
        if (stream.codec_type == "video" && stream.attached_pic) continue;
        JsonObject config;
        config.items["stream_id"] = JsonValue((int64_t)stream_id);
        config.items["type"] = JsonValue(stream.codec_type);
        config.items["codec"] = JsonValue(stream.codec_name);
        config.items["width"] = stream.codec_type == "video"
                                    ? JsonValue((int64_t)stream.width)
                                    : JsonValue(std::nullptr_t{});
        config.items["height"] = stream.codec_type == "video"
                                     ? JsonValue((int64_t)stream.height)
                                     : JsonValue(std::nullptr_t{});
        config.items["channels"] = stream.codec_type == "audio"
                                       ? JsonValue((int64_t)stream.channels)
                                       : JsonValue(std::nullptr_t{});
        config.items["sample_rate"] = stream.codec_type == "audio"
                                          ? JsonValue(stream.sample_rate > 0
                                                          ? std::to_string(stream.sample_rate)
                                                          : std::string("0"))
                                          : JsonValue(std::nullptr_t{});
        const std::string config_json =
            casu::dump_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(config))));
        chunks.emplace_back(casu::mp5::STREAM_CONFIG, (uint8_t)stream_id, 0,
                            std::vector<uint8_t>(config_json.begin(), config_json.end()));
        ++stream_id;
    }
    if (stream_id == 1) throw CasuError("input contains no playable audio or video stream");

    const int parts = (int)((source_bytes.size() + MP5_PART_BYTES - 1) / MP5_PART_BYTES);
    for (int part = 0; part < parts; ++part) {
        const std::size_t offset = (std::size_t)part * MP5_PART_BYTES;
        const std::size_t length = std::min(MP5_PART_BYTES, source_bytes.size() - offset);
        chunks.emplace_back(casu::mp5::ATTACHMENT, 0, 0,
                            attachment_payload(source_bytes, offset, length, filename, part, parts));
    }

    const std::string digest = casu::sha256_file(source_abs);
    JsonObject integrity;
    integrity.items["source_sha256"] = JsonValue(digest);
    integrity.items["attachment_sha256"] = JsonValue(digest);
    integrity.items["attachment_parts"] = JsonValue((int64_t)parts);
    integrity.items["chunk_count"] = JsonValue((int64_t)chunks.size());
    const std::string integrity_json =
        casu::dump_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(integrity))));
    chunks.emplace_back(casu::mp5::INTEGRITY_TABLE, 0, 0,
                        std::vector<uint8_t>(integrity_json.begin(), integrity_json.end()));

    JsonObject metadata;
    metadata.items["converted_by"] = JsonValue(std::string("casu.mp5"));
    metadata.items["mode"] = JsonValue(mode);
    metadata.items["tile_width"] = JsonValue(int64_t(64));
    metadata.items["tile_height"] = JsonValue(int64_t(64));
    metadata.items["key_interval_seconds"] = JsonValue(3.0);
    const std::string metadata_json =
        casu::dump_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(metadata))));
    chunks.emplace_back(casu::mp5::METADATA, 0, 0,
                        std::vector<uint8_t>(metadata_json.begin(), metadata_json.end()));
    chunks.emplace_back(casu::mp5::END, 0, 0, std::vector<uint8_t>{});

    casu::mp5::write_mp5(output_abs, manifest, chunks);
    const casu::mp5::Container container = casu::mp5::read_mp5(output_abs);

    JsonObject summary;
    summary.items["container"] = JsonValue(output_abs);
    summary.items["mp5_version"] = JsonValue(int64_t(1));
    summary.items["chunks"] = JsonValue((int64_t)container.chunks.size());
    summary.items["payload_bytes"] = JsonValue((int64_t)size);
    summary.items["mode"] = JsonValue(mode);
    std::printf("%s\n", pretty_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(summary)))).c_str());
    return 0;
}

int cmd_pack_v2(const Args& args) {
    (void)args;
    throw CasuError("pack-v2: CASUNAT2 writer folgt (casu_core provides a "
                    "CASUNAT2 reader only; the segmented writer is a later port step)");
}

int cmd_repair_v2(const Args& args) {
    (void)args;
    throw CasuError("repair-v2: CASUNAT2 writer folgt (finalizing a CASUNAT2 "
                    "prefix requires the segmented writer, which is not ported yet)");
}

}  // namespace casu::cli
