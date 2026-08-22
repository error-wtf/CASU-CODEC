// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Byte-parity test for the native-v2 converter port: converts the committed
// lossless fixture through casu::natconv::convert_media_to_native_v2 and
// requires byte-identical output to the Python reference conversion
// (tests/fixtures/natv2/ref_convert.casu).
#include "casu/codec/native_convert.hpp"
#include "casu/codec/ffprobe.hpp"
#include "casu/codec/analyze.hpp"
#include "casu/native_v2.hpp"
#include "casu/sha256.hpp"

#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>

using namespace casu;

namespace {

std::string read_file(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::printf("usage: casu_natv2_convert_test <fixture_dir>\n");
        return 2;
    }
    const std::string dir = argv[1];
    const std::string source = dir + "/convert_source.mkv";
    const std::string reference = dir + "/ref_convert.casu";
    const std::string mine = dir + "/cpp_convert.casu";

    int failures = 0;
    auto check = [&](bool ok, const char* label) {
        if (!ok) {
            ++failures;
            std::printf("FAIL %s\n", label);
        } else {
            std::printf("ok   %s\n", label);
        }
    };

    bool converted = true;
    std::string error_text;
    try {
        natconv::convert_media_to_native_v2(source, mine);
    } catch (const CasuError& exc) {
        converted = false;
        error_text = exc.what();
    }
    check(converted, "c++ converter runs");
    if (!converted) {
        std::printf("  error: %s\n", error_text.c_str());
        return 1;
    }

    const std::string mine_bytes = read_file(mine);
    const std::string ref_bytes = read_file(reference);
    if (mine_bytes != ref_bytes) {
        for (std::size_t i = 0;
             i < std::min(mine_bytes.size(), ref_bytes.size()); ++i) {
            if (mine_bytes[i] != ref_bytes[i]) {
                std::printf("  first diff at byte %zu: cpp=%02x py=%02x\n", i,
                            uint8_t(mine_bytes[i]), uint8_t(ref_bytes[i]));
                break;
            }
        }
    }
    check(mine_bytes.size() == ref_bytes.size(), "converted size parity");
    check(mine_bytes == ref_bytes,
          "converted file BYTE-IDENTICAL to python reference");

    // The output must round-trip through the strict reader.
    bool valid = false;
    try {
        const casunat2::Container c = casunat2::read_native_v2(mine);
        valid = c.integrity_verified && !c.chunks.empty();
    } catch (const CasuError& exc) {
        std::printf("  verify error: %s\n", exc.what());
    }
    check(valid, "converted file passes strict verification");

    // --- Strict analysis state-map parity (iter_state_map) ------------------
    bool strict_ok = false;
    try {
        const JsonValue probe = casu::codec::probe_json(source);
        const JsonValue analysis =
            casu::analyze::strict_activity_analysis(source, probe, 16, 16);
        const JsonValue* spatial = analysis.find("spatial_analysis");
        const JsonValue* state_map = spatial && spatial->is_object()
                                         ? spatial->find("state_map")
                                         : nullptr;
        const std::string ref_text = read_file(dir + "/ref_strict_state_map.json");
        const JsonValue ref_map = parse_json(ref_text);
        if (state_map && state_map->is_array() && ref_map.is_array()) {
            // Compare as canonical sorted dumps (record order is deterministic).
            const std::string mine_dump = dump_json(*state_map, true, false);
            const std::string ref_dump = dump_json(ref_map, true, false);
            strict_ok = mine_dump == ref_dump;
            if (!strict_ok) {
                std::printf("  strict records: mine=%zu ref=%zu\n",
                            state_map->as_array().items.size(),
                            ref_map.as_array().items.size());
                for (std::size_t i = 0; i < std::min(
                         mine_dump.size(), ref_dump.size());
                     ++i) {
                    if (mine_dump[i] != ref_dump[i]) {
                        std::printf("  first diff at char %zu: cpp=%c py=%c\n",
                                    i, mine_dump[i], ref_dump[i]);
                        break;
                    }
                }
            }
        }
        const JsonValue* hint = analysis.find("state_is_hint_only");
        strict_ok = strict_ok && hint && hint->is_bool() &&
                    !hint->as_bool();
    } catch (const CasuError& exc) {
        std::printf("  strict error: %s\n", exc.what());
    }
    check(strict_ok, "strict state map IDENTICAL to python iter_state_map");

    if (failures == 0) std::printf("ALL PASS\n");
    return failures == 0 ? 0 : 1;
}
