// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// casu-cli — Windows-native CASU command line tool (Phase C1).
// Implements the reference casu/cli.py subcommand set with compatible exit
// codes, stdout and JSON output (REQ-PORT-004).
#include "casu/formats.hpp"
#include "commands.hpp"

#include <cstdio>
#include <exception>
#include <stdexcept>
#include <string>
#include <vector>

namespace casu::cli {

namespace {

const char* kVersion = "CASU Codec for All Segmented Units 3.0.0";

struct CommandEntry {
    const char* name;
    int (*handler)(const Args&);
};

const CommandEntry kCommands[] = {
    {"analyze", cmd_analyze},
    {"convert", cmd_convert},
    {"pack", cmd_pack},
    {"pack-v2", cmd_pack_v2},
    {"pack-mp5", cmd_pack_mp5},
    {"mp5-info", cmd_mp5_info},
    {"native-info", cmd_native_info},
    {"repair-v2", cmd_repair_v2},
    {"export", cmd_export},
    {"transcode", cmd_transcode},
    {"play", cmd_play},
    {"validate", [](const Args& a) { return cmd_validate_verify_info(a, "validate"); }},
    {"verify", [](const Args& a) { return cmd_validate_verify_info(a, "verify"); }},
    {"info", [](const Args& a) { return cmd_validate_verify_info(a, "info"); }},
    {"benchmark", cmd_benchmark},
    {"kind", cmd_kind},
    {"sha256", cmd_sha256},
};

}  // namespace

const char* command_usage(const std::string& command) {
    if (command == "analyze") return "casu analyze <input> [-o <output>] [--analysis-fps <fps>] [--mode strict|visually_lossless|adaptive]";
    if (command == "convert") return "casu convert <input>... [-o <output>] [--report <path>] [--container sidecar|native|native-v2] [--force] [--resume] [--retry <n>] [--analysis-fps <fps>] [--mode <mode>]";
    if (command == "pack") return "casu pack <input> -o <output> [--analysis-fps <fps>] [--mode <mode>]";
    if (command == "pack-v2") return "casu pack-v2 <input> -o <output> [--tile-size <n>] [--key-interval <s>]";
    if (command == "pack-mp5") return "casu pack-mp5 <input> -o <output> [--mode <mode>]";
    if (command == "mp5-info") return "casu mp5-info <input> [--full]";
    if (command == "native-info") return "casu native-info <input>";
    if (command == "repair-v2") return "casu repair-v2 <input> -o <output>";
    if (command == "export") return "casu export <input>... -o <output> [--format <ext>] [--report <path>]";
    if (command == "transcode") return "casu transcode <input>... -o <output> [--format <ext>] [--preset <preset>] [--report <path>] [--first-tracks] [--strip-metadata] [--force] [--resume] [--retry <n>]";
    if (command == "play") return "casu play <input>";
    if (command == "validate") return "casu validate <manifest> [--verify-source]";
    if (command == "verify") return "casu verify <manifest>";
    if (command == "info") return "casu info <manifest>";
    if (command == "benchmark") return "casu benchmark <input> [-o <output>] [--analysis-fps <fps>] [--mode <mode>]";
    if (command == "kind") return "casu kind <file>";
    if (command == "sha256") return "casu sha256 <file>";
    return "casu <command> [args...]";
}

namespace {

void print_usage() {
    std::printf(
        "usage: casu <command> [options]\n"
        "CASU Codec for All Segmented Units — Windows CLI (Phase C1)\n"
        "commands:\n"
        "  analyze      write a CASU temporal-state sidecar\n"
        "  convert      convert legacy media to CASU (sidecar/native/native-v2)\n"
        "  pack         standalone CASUNAT1 (lossless source payload)\n"
        "  pack-v2      segmented CASUNAT2 (writer: see note below)\n"
        "  pack-mp5     CASU MP5 enhanced container\n"
        "  mp5-info     verify and inspect a CASU MP5 container\n"
        "  native-info  verify and inspect a native CASU container\n"
        "  repair-v2    finalize a declared CASUNAT2 prefix\n"
        "  export       convert verified CASU back to FFmpeg-supported media\n"
        "  transcode    convert media to another media format\n"
        "  play         validate a media path for MPCASU in-process playback\n"
        "  validate     validate a .casu manifest\n"
        "  verify       validate a manifest and verify its recorded source\n"
        "  info         machine-readable manifest information (JSON)\n"
        "  benchmark    deterministic analysis-cost JSON report\n"
        "  kind         content-based CASU kind (win extension)\n"
        "  sha256       SHA-256 of a file (win extension)\n"
        "  --version    print the version\n"
        "  --help       this help\n"
        "note: pack-v2/repair-v2/convert --container native-v2 fail with a clear\n"
        "      error until the CASUNAT2 writer is ported (reader is available).\n");
}

int dispatch(const std::string& command, const std::vector<std::string>& tokens) {
    for (const CommandEntry& entry : kCommands) {
        if (command == entry.name) {
            if (tokens.size() == 1 && (tokens[0] == "-h" || tokens[0] == "--help")) {
                std::printf("usage: %s\n", command_usage(command));
                return 0;
            }
            Args args = parse_args(tokens);
            if (args.flag("--help") || args.flag("-h")) {
                std::printf("usage: %s\n", command_usage(command));
                return 0;
            }
            return entry.handler(args);
        }
    }
    std::fprintf(stderr, "casu: error: invalid choice: '%s'\n", command.c_str());
    return 2;
}

}  // namespace

}  // namespace casu::cli

int main(int argc, char** argv) {
    if (argc < 2) {
        casu::cli::print_usage();
        return 2;
    }
    const std::string command = argv[1];
    if (command == "--version") {
        std::printf("%s\n", casu::cli::kVersion);
        return 0;
    }
    if (command == "--help" || command == "-h" || command == "help") {
        casu::cli::print_usage();
        return 0;
    }
    std::vector<std::string> tokens;
    for (int i = 2; i < argc; ++i) tokens.emplace_back(argv[i]);
    try {
        return casu::cli::dispatch(command, tokens);
    } catch (const casu::CasuError& exc) {
        std::fprintf(stderr, "casu: error: %s\n", exc.what());
        return 2;
    } catch (const casu::JsonError& exc) {
        std::fprintf(stderr, "casu: error: %s\n", exc.what());
        return 2;
    } catch (const std::out_of_range&) {
        std::fprintf(stderr, "casu: error: missing required file argument\n");
        return 2;
    } catch (const std::exception& exc) {
        std::fprintf(stderr, "casu: error: %s\n", exc.what());
        return 2;
    }
}
