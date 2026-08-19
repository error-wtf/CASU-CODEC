// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// casu-cli — subcommand handler declarations.
#pragma once

#include "cli_util.hpp"

namespace casu::cli {

int cmd_kind(const Args& args);
int cmd_sha256(const Args& args);
int cmd_validate_verify_info(const Args& args, const std::string& command);
int cmd_native_info(const Args& args);
int cmd_mp5_info(const Args& args);
int cmd_pack(const Args& args);
int cmd_pack_mp5(const Args& args);
int cmd_pack_v2(const Args& args);
int cmd_repair_v2(const Args& args);
int cmd_analyze(const Args& args);
int cmd_convert(const Args& args);
int cmd_benchmark(const Args& args);
int cmd_play(const Args& args);
int cmd_transcode(const Args& args);
int cmd_export(const Args& args);

// Prints a command's usage line and returns the help text.
const char* command_usage(const std::string& command);

}  // namespace casu::cli
