// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// casu-cli — inspection subcommands: kind, sha256, info, validate, verify,
// native-info, mp5-info. Outputs and exit codes mirror casu/cli.py.
#include "cli_util.hpp"

#include "casu/formats.hpp"
#include "casu/json.hpp"
#include "casu/manifest.hpp"
#include "casu/mp5.hpp"
#include "casu/native.hpp"
#include "casu/native_v2.hpp"
#include "casu/sha256.hpp"
#include "casu/sidecar.hpp"

#include <cstdio>
#include <string>
#include <vector>

namespace casu::cli {

using casu::CasuError;
using casu::JsonValue;

namespace {

std::string manifest_text(const std::string& path) {
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) throw CasuError("could not read manifest " + path);
    std::fseek(f, 0, SEEK_END);
    long size = std::ftell(f);
    std::fseek(f, 0, SEEK_SET);
    if (size < 0 || (unsigned long)size > 64ULL * 1024 * 1024) {
        std::fclose(f);
        throw CasuError("could not read manifest " + path);
    }
    std::string text((std::size_t)size, '\0');
    if (size > 0 && std::fread(&text[0], 1, (std::size_t)size, f) != (std::size_t)size) {
        std::fclose(f);
        throw CasuError("could not read manifest " + path);
    }
    std::fclose(f);
    return text;
}

void print_invalid_message(const std::string& message) {
    std::printf("INVALID: %s\n", message.c_str());
}

}  // namespace

int cmd_kind(const Args& args) {
    const std::string file = args.positional.at(0);
    try {
        std::printf("%s\n", kind_name(casu::detect_casu_kind(file)).c_str());
        return 0;
    } catch (const casu::CasuError& exc) {
        std::fprintf(stderr, "casu: %s\n", exc.what());
        return 1;
    }
}

int cmd_sha256(const Args& args) {
    const std::string file = args.positional.at(0);
    const std::string digest = casu::sha256_file(file);
    if (digest.empty()) {
        std::fprintf(stderr, "casu: could not read file\n");
        return 1;
    }
    std::printf("%s  %s\n", digest.c_str(), file.c_str());
    return 0;
}

// validate / verify / info share the manifest dispatch of cli.py.
int cmd_validate_verify_info(const Args& args, const std::string& command) {
    const std::string manifest = args.positional.at(0);
    std::string magic;
    if (!read_magic(manifest, magic))
        throw CasuError("could not read manifest " + manifest);

    if (magic == "CASUNAT2") {
        try {
            const casu::casunat2::Container container = casu::casunat2::read_native_v2(manifest);
            if (command == "info") {
                JsonObject out;
                out.items["valid"] = JsonValue(true);
                out.items["native"] = JsonValue(true);
                out.items["native_version"] = JsonValue(int64_t(2));
                const JsonValue* streams = container.manifest.find("streams");
                out.items["streams"] =
                    streams ? *streams : JsonValue(std::make_shared<casu::JsonArray>());
                out.items["chunks"] = JsonValue((int64_t)container.chunks.size());
                out.items["seek_entries"] = JsonValue((int64_t)container.seek_entries.size());
                out.items["integrity_verified"] = JsonValue(container.integrity_verified);
                std::printf("%s\n", pretty_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(out)))).c_str());
            } else {
                std::printf("VALID: CASUNAT2 structure, seek index, and integrity verified\n");
            }
            return 0;
        } catch (const casu::CasuError& exc) {
            if (command == "info") {
                JsonObject out;
                out.items["valid"] = JsonValue(false);
                out.items["native"] = JsonValue(true);
                out.items["native_version"] = JsonValue(int64_t(2));
                auto errors = std::make_shared<casu::JsonArray>();
                errors->items.push_back(JsonValue(std::string(exc.what())));
                out.items["errors"] = JsonValue(std::move(errors));
                std::printf("%s\n", pretty_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(out)))).c_str());
            } else {
                print_invalid_message(exc.what());
            }
            return 1;
        }
    }

    if (magic == "CASUNAT1") {
        try {
            const casu::casunat1::Container container =
                casu::casunat1::read_native(manifest, true);
            if (command == "info") {
                JsonObject out;
                out.items["valid"] = JsonValue(true);
                out.items["native"] = JsonValue(true);
                out.items["payload_bytes"] = JsonValue((int64_t)container.payload_length);
                out.items["manifest"] = container.manifest;
                std::printf("%s\n", pretty_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(out)))).c_str());
            } else {
                std::printf("VALID: native CASU container and payload integrity verified\n");
            }
            return 0;
        } catch (const casu::CasuError& exc) {
            if (command == "info") {
                JsonObject out;
                out.items["valid"] = JsonValue(false);
                out.items["native"] = JsonValue(true);
                auto errors = std::make_shared<casu::JsonArray>();
                errors->items.push_back(JsonValue(std::string(exc.what())));
                out.items["errors"] = JsonValue(std::move(errors));
                std::printf("%s\n", pretty_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(out)))).c_str());
            } else {
                print_invalid_message(exc.what());
            }
            return 1;
        }
    }

    // JSON sidecar path.
    JsonValue parsed;
    try {
        parsed = casu::parse_json(manifest_text(manifest));
    } catch (const casu::JsonError& exc) {
        throw CasuError("could not read manifest " + manifest + ": " + exc.what());
    }
    const std::vector<std::string> errors = casu::validate_manifest(parsed);
    if (!errors.empty()) {
        if (command == "info") {
            JsonObject out;
            out.items["valid"] = JsonValue(false);
            auto error_list = std::make_shared<casu::JsonArray>();
            for (const std::string& error : errors)
                error_list->items.push_back(JsonValue(error));
            out.items["errors"] = JsonValue(std::move(error_list));
            std::printf("%s\n", pretty_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(out)))).c_str());
        } else {
            for (const std::string& error : errors) print_invalid_message(error);
        }
        return 1;
    }

    const bool verify_source = command == "verify" || args.flag("--verify-source");
    if (verify_source) {
        std::string source;
        try {
            source = casu::resolve_casu_source(manifest);
        } catch (const casu::CasuError& exc) {
            if (command == "info") {
                JsonObject out;
                out.items["valid"] = JsonValue(false);
                auto error_list = std::make_shared<casu::JsonArray>();
                error_list->items.push_back(JsonValue(std::string(exc.what())));
                out.items["errors"] = JsonValue(std::move(error_list));
                std::printf("%s\n", pretty_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(out)))).c_str());
            } else {
                print_invalid_message(exc.what());
            }
            return 1;
        }
        if (command == "info") {
            JsonObject out;
            out.items["source_verified"] = JsonValue(source);
            std::printf("%s\n", pretty_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(out)))).c_str());
            return 0;
        }
        std::printf("VERIFIED source: %s\n", source.c_str());
    }

    if (command == "info") {
        JsonObject out;
        out.items["valid"] = JsonValue(true);
        out.items["manifest"] = JsonValue(abs_path(manifest));
        const JsonValue* value = nullptr;
        value = parsed.find("format");
        out.items["format"] = value ? *value : JsonValue(std::make_shared<casu::JsonObject>());
        value = parsed.find("source");
        out.items["source"] = value ? *value : JsonValue(std::make_shared<casu::JsonObject>());
        value = parsed.find("streams");
        out.items["streams"] = value ? *value : JsonValue(std::make_shared<casu::JsonArray>());
        int video_segments = 0, audio_segments = 0, seek_entries = 0;
        if (const JsonValue* video = parsed.find("video"))
            if (const JsonValue* segments = video->find("segments"))
                video_segments = (int)segments->as_array().items.size();
        if (const JsonValue* audio = parsed.find("audio"))
            if (const JsonValue* segments = audio->find("segments"))
                audio_segments = (int)segments->as_array().items.size();
        if (const JsonValue* seek = parsed.find("seek_index"))
            if (const JsonValue* entries = seek->find("entries"))
                seek_entries = (int)entries->as_array().items.size();
        out.items["video_segments"] = JsonValue((int64_t)video_segments);
        out.items["audio_segments"] = JsonValue((int64_t)audio_segments);
        out.items["seek_index_entries"] = JsonValue((int64_t)seek_entries);
        const JsonValue* native_payload = parsed.find("seek_index");
        bool native_states = false;
        if (native_payload)
            if (const JsonValue* nks = native_payload->find("native_key_states"))
                if (nks->is_bool()) native_states = nks->as_bool();
        out.items["native_payload"] = JsonValue(native_states);
        value = parsed.find("integrity");
        out.items["integrity"] = value ? *value : JsonValue(std::make_shared<casu::JsonObject>());
        std::printf("%s\n", pretty_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(out)))).c_str());
        return 0;
    }

    std::printf("VALID CASU manifest: %s\n", manifest.c_str());
    return 0;
}

int cmd_native_info(const Args& args) {
    const std::string input = args.positional.at(0);
    std::string magic;
    if (!read_magic(input, magic)) throw CasuError("could not read native container: " + input);
    if (magic == "CASUNAT2") {
        const casu::casunat2::Container container = casu::casunat2::read_native_v2(input);
        JsonObject out;
        out.items["container"] = JsonValue(abs_path(container.path));
        out.items["native_version"] = JsonValue(int64_t(2));
        const JsonValue* streams = container.manifest.find("streams");
        out.items["streams"] = streams && streams->is_array()
                                   ? JsonValue((int64_t)streams->as_array().items.size())
                                   : JsonValue(int64_t(0));
        out.items["chunks"] = JsonValue((int64_t)container.chunks.size());
        out.items["seek_entries"] = JsonValue((int64_t)container.seek_entries.size());
        const JsonValue* recovery = container.manifest.find("recovery");
        out.items["recovery"] = recovery ? *recovery : JsonValue(std::nullptr_t{});
        out.items["integrity_verified"] = JsonValue(container.integrity_verified);
        std::printf("%s\n", pretty_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(out)))).c_str());
        return 0;
    }
    const casu::casunat1::Container container = casu::casunat1::read_native(input, true);
    JsonObject out;
    out.items["container"] = JsonValue(abs_path(container.path));
    out.items["native_version"] = JsonValue(int64_t(1));
    out.items["payload_bytes"] = JsonValue((int64_t)container.payload_length);
    out.items["payload_sha256"] = JsonValue(container.payload_sha256);
    out.items["manifest"] = container.manifest;
    std::printf("%s\n", pretty_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(out)))).c_str());
    return 0;
}

int cmd_mp5_info(const Args& args) {
    const std::string input = args.positional.at(0);
    const casu::mp5::Container container = casu::mp5::read_mp5(input);
    const std::vector<std::string> issues = casu::mp5::verify_mp5(input);
    const JsonValue* source_info = container.manifest.find("source");
    JsonObject summary;
    summary.items["container"] = JsonValue(abs_path(container.path));
    summary.items["mp5_version"] = JsonValue(int64_t(1));
    summary.items["chunks"] = JsonValue((int64_t)container.chunks.size());
    if (source_info && source_info->is_object()) {
        const JsonValue* value = source_info->find("filename");
        summary.items["source_filename"] = value ? *value : JsonValue(std::nullptr_t{});
        value = source_info->find("bytes");
        if (!value || value->is_null()) value = source_info->find("size_bytes");
        summary.items["payload_bytes"] = value ? *value : JsonValue(std::nullptr_t{});
        value = source_info->find("sha256");
        summary.items["source_sha256"] = value ? *value : JsonValue(std::nullptr_t{});
    } else {
        summary.items["source_filename"] = JsonValue(std::nullptr_t{});
        summary.items["payload_bytes"] = JsonValue(std::nullptr_t{});
        summary.items["source_sha256"] = JsonValue(std::nullptr_t{});
    }
    auto issue_list = std::make_shared<casu::JsonArray>();
    for (const std::string& issue : issues) issue_list->items.push_back(JsonValue(issue));
    summary.items["issues"] = JsonValue(std::move(issue_list));
    if (args.flag("--full")) {
        summary.items["manifest"] = container.manifest;
    } else {
        auto sections = std::make_shared<casu::JsonArray>();
        for (const auto& [key, value] : container.manifest.as_object().items)
            sections->items.push_back(JsonValue(key));
        summary.items["manifest_sections"] = JsonValue(std::move(sections));
    }
    std::printf("%s\n", pretty_json(JsonValue(std::make_shared<casu::JsonObject>(std::move(summary)))).c_str());
    return issues.empty() ? 0 : 1;
}

}  // namespace casu::cli
