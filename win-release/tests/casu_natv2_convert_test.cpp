// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Byte-parity test for the native-v2 converter port: converts the committed
// lossless fixture through casu::natconv::convert_media_to_native_v2 and
// requires byte-identical output to the Python reference conversion
// (tests/fixtures/natv2/ref_convert.casu).
#include "casu/codec/native_convert.hpp"
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

    if (failures == 0) std::printf("ALL PASS\n");
    return failures == 0 ? 0 : 1;
}
