// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Unit tests for casu_core (kind detection, CASUNAT2 header/chunk parsing,
// validation, JSON parser, manifest validation). Builds minimal in-memory
// CASUNAT2 files and checks both the happy path and the fail-closed rejections.
#include "casu/formats.hpp"
#include "casu/sha256.hpp"
#include "casu/json.hpp"
#include "casu/manifest.hpp"
#include "casu/native.hpp"
#include "casu/native_v2.hpp"
#include "casu/mp5.hpp"
#include "casu/sidecar.hpp"
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <string>
#include <tuple>
#include <vector>
#ifdef CASU_HAVE_ZSTD
#include <zstd.h>
#endif

using namespace casu;

namespace {
int failures = 0;
void check(bool ok, const char* label) {
    if (!ok) { ++failures; std::printf("FAIL %s\n", label); }
    else std::printf("ok   %s\n", label);
}

void be16(uint8_t* p, uint16_t v) { p[0] = uint8_t(v >> 8); p[1] = uint8_t(v); }
void be64(uint8_t* p, uint64_t v) { for (int i = 7; i >= 0; --i) { p[i] = uint8_t(v); v >>= 8; } }
void be64s(uint8_t* p, int64_t v) { be64(p, static_cast<uint64_t>(v)); }

void le16(uint8_t* p, uint16_t v) { p[0] = uint8_t(v); p[1] = uint8_t(v >> 8); }
void le32(uint8_t* p, uint32_t v) { p[0] = uint8_t(v); p[1] = uint8_t(v >> 8); p[2] = uint8_t(v >> 16); p[3] = uint8_t(v >> 24); }

// Build a minimal MP5 file (header + manifest + chunk table + footer) with a
// single AUDIO_BLOCK chunk whose compressed payload is given verbatim.
std::vector<uint8_t> make_mp5_with_payload(const std::string& manifest,
                                           const std::vector<uint8_t>& comp_payload) {
    std::vector<uint8_t> f;
    f.insert(f.end(), {'C','A','S','U','M','P','5',0});
    uint8_t hdr[12];
    le16(hdr, 1); le16(hdr + 2, 0);
    le32(hdr + 4, (uint32_t)manifest.size()); le32(hdr + 8, 0);
    f.insert(f.end(), hdr, hdr + 12);
    f.insert(f.end(), manifest.begin(), manifest.end());
    uint8_t ch[11];
    ch[0] = casu::mp5::AUDIO_BLOCK;
    le16(ch + 1, 0); le32(ch + 3, 0); le32(ch + 7, (uint32_t)comp_payload.size());
    f.insert(f.end(), ch, ch + 11);
    f.insert(f.end(), comp_payload.begin(), comp_payload.end());
    uint8_t end[11];
    std::memset(end, 0, sizeof(end));
    end[0] = casu::mp5::END;
    f.insert(f.end(), end, end + 11);
    // Footer: count(4) + manifest_sha256(32).
    uint8_t footer[36];
    le32(footer, 1);
    Sha256 ctx;
    ctx.update(manifest);
    std::vector<uint8_t> md = ctx.digest();
    std::memcpy(footer + 4, md.data(), 32);
    f.insert(f.end(), footer, footer + 36);
    return f;
}

// Build a minimal but structurally valid CASUNAT2 file: header + manifest "{}"
// + one AUDIO_BLOCK chunk + END marker.
std::vector<uint8_t> make_minimal_nat2() {
    std::vector<uint8_t> f;
    f.insert(f.end(), {'C','A','S','U','N','A','T','2'});
    uint8_t tmp[12];
    be16(tmp, casunat2::VERSION); be16(tmp + 2, 0); be64(tmp + 4, 2);  // manifest_length = 2 ("{}")
    f.insert(f.end(), tmp, tmp + 12);
    f.insert(f.end(), {'{', '}'});
    // AUDIO_BLOCK chunk header (28 B) + 4-byte payload
    uint8_t ch[28];
    ch[0] = casunat2::AUDIO_BLOCK; ch[1] = 0; be16(ch + 2, 0);
    be64s(ch + 4, 0); be64(ch + 12, 4); be64(ch + 20, 4);
    f.insert(f.end(), ch, ch + casunat2::CHUNK_HEADER_SIZE);
    f.insert(f.end(), {0x01, 0x02, 0x03, 0x04});
    // END marker (no payload)
    std::memset(ch, 0, sizeof(ch));
    ch[0] = casunat2::END;
    f.insert(f.end(), ch, ch + casunat2::CHUNK_HEADER_SIZE);
    return f;
}
}  // namespace

int main() {
    // --- kind detection ---
    {
        FILE* f = std::fopen("/tmp/casu_nat2_test.casu", "wb");
        auto blob = make_minimal_nat2();
        std::fwrite(blob.data(), 1, blob.size(), f);
        std::fclose(f);
    }
    check(detect_casu_kind("/tmp/casu_nat2_test.casu") == CasuKind::Casunat2, "kind=CASUNAT2");

    {
        FILE* f = std::fopen("/tmp/casu_mp5_test.casu", "wb");
        const char* m = "CASUMP5\0";
        std::fwrite(m, 1, 8, f);
        std::fclose(f);
    }
    check(detect_casu_kind("/tmp/casu_mp5_test.casu") == CasuKind::Mp5, "kind=MP5");
    {
        FILE* f = std::fopen("/tmp/casu_plain.txt", "wb");
        std::fwrite("hello world not a casu", 1, 22, f);
        std::fclose(f);
    }
    check(detect_casu_kind("/tmp/casu_plain.txt") == CasuKind::None, "kind=none");

    // --- CASUNAT2 validation ---
    {
        uint64_t chunks = casunat2::validate_file("/tmp/casu_nat2_test.casu");
        check(chunks == 1, "validate minimal NAT2 -> 1 chunk");
    }
    // Missing END marker must fail.
    {
        FILE* f = std::fopen("/tmp/casu_noend.casu", "wb");
        auto blob = make_minimal_nat2();
        blob.resize(blob.size() - 27);  // drop END chunk
        std::fwrite(blob.data(), 1, blob.size(), f);
        std::fclose(f);
        bool threw = false;
        try { casunat2::validate_file("/tmp/casu_noend.casu"); }
        catch (const CasuError&) { threw = true; }
        check(threw, "missing END marker rejected");
    }
    // Bad magic must fail.
    {
        FILE* f = std::fopen("/tmp/casu_badmagic.casu", "wb");
        auto blob = make_minimal_nat2();
        blob[0] = 'X';
        std::fwrite(blob.data(), 1, blob.size(), f);
        std::fclose(f);
        bool threw = false;
        try { casunat2::validate_file("/tmp/casu_badmagic.casu"); }
        catch (const CasuError&) { threw = true; }
        check(threw, "bad magic rejected");
    }

    // --- sha256 known-answer test ---
    {
        Sha256 ctx;
        ctx.update(std::string("abc"));
        std::string digest = ctx.hexdigest();
        check(digest == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
              "sha256('abc') known answer");
    }
    // sha256_file known answer.
    {
        FILE* f = std::fopen("/tmp/casu_sha.txt", "wb");
        std::fwrite("abc", 1, 3, f);
        std::fclose(f);
        check(sha256_file("/tmp/casu_sha.txt") ==
              "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
              "sha256_file known answer");
    }
    // sha256 padding regression: input length == 64k+55 (buffer_len_ 56 after
    // the 0x80 pad) previously produced a wrong digest.
    {
        std::string s(30 * 64 + 55, 'x');  // 1975 bytes
        check(Sha256::oneshot(s) ==
              "2140e1d4ecabef57e23bf0a2fa5b39f5d615e1ab59a83d924e23f6ec2e14acc8",
              "sha256 padding 64k+55 regression");
    }

    // --- bounded JSON parser ---
    {
        JsonValue v = parse_json(R"({"a":1,"b":[true,null,"x"],"c":{"d":-2.5}})");
        check(v.is_object(), "json parses object");
        check(v.find("a") && v.find("a")->is_int() && v.find("a")->as_int() == 1, "json int");
        const JsonValue* b = v.find("b");
        check(b && b->is_array() && b->as_array().items.size() == 3, "json array");
        check(b && b->as_array().items[1].is_null(), "json null");
        check(v.find("c") && v.find("c")->find("d") &&
              v.find("c")->find("d")->is_number(), "json nested");
        check(dump_json(v) == R"({"a":1,"b":[true,null,"x"],"c":{"d":-2.5}})",
              "json dump round-trip");
    }
    // Trailing garbage must be rejected.
    {
        bool threw = false;
        try { parse_json(std::string("{\"a\":1}") + "extra"); }
        catch (const JsonError&) { threw = true; }
        check(threw, "json trailing garbage rejected");
    }
    // Depth limit must be enforced.
    {
        bool threw = false;
        JsonLimits shallow;
        shallow.max_depth = 2;
        try { parse_json(R"({"a":{"b":{"c":1}}})", shallow); }
        catch (const JsonError&) { threw = true; }
        check(threw, "json depth limit enforced");
    }
    // Node limit must be enforced.
    {
        bool threw = false;
        JsonLimits tiny;
        tiny.max_nodes = 2;  // root object + one value already = 2; a 2nd value exceeds
        try { parse_json(R"({"a":1,"b":2})", tiny); }
        catch (const JsonError&) { threw = true; }
        check(threw, "json node limit enforced");
    }
    // NaN/Infinity are not valid JSON.
    {
        bool threw = false;
        try { parse_json("NaN"); }
        catch (const JsonError&) { threw = true; }
        check(threw, "json NaN rejected");
    }

    // --- manifest validation (WP-CORE-002) ---
    {
        std::string valid = R"({
            "casu": {"name":"CASU","container_extension":".casu","version":"2.0.0","analysis_mode":"strict"},
            "format": {"magic":"MPCASU\\0","schema":"0.2"},
            "source": {"filename":"demo.mp4","duration_s":12.5,"size_bytes":12345,"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
            "streams": [{"codec_type":"video","codec_name":"h264"}],
            "metadata": {"title":"demo"},
            "video": {"segments":[{"start_s":0,"end_s":12.5,"state":"active","segment_id":"s1","lifecycle":"UPDATE","priority":1}]},
            "seek_index": {"native_key_states":true,"entries":[{"timestamp_s":0,"stream":"video","segment_id":"s1"}]},
            "integrity": {"timestamps_are_source_of_truth":true}
        })";
        auto errs = parse_and_validate_manifest(valid);
        check(errs.empty(), "manifest valid -> no errors");
    }
    // Structural errors must be surfaced.
    {
        std::string bad = R"({
            "casu": {"name":"MPCASU","version":"9.9.9"},
            "format": {"schema":"9.9"},
            "source": {"filename":"../evil/../../etc/passwd"},
            "video": {"segments":[{"start_s":0,"end_s":5},{"start_s":2,"end_s":6,"state":"","priority":true}]},
            "integrity": {"timestamps_are_source_of_truth":false}
        })";
        auto errs = parse_and_validate_manifest(bad);
        check(!errs.empty(), "manifest invalid -> errors reported");
        bool found_traversal = false;
        for (const auto& e : errs) if (e.find("path traversal") != std::string::npos) found_traversal = true;
        check(found_traversal, "manifest path traversal rejected");
    }

    // --- CASUNAT1 write/read/extract (WP-CORE-003) ---
    {
        const char* payload = "THE ORIGINAL MEDIA PAYLOAD 0123456789";
        {
            FILE* s = std::fopen("/tmp/casu_nat1_src.bin", "wb");
            std::fwrite(payload, 1, std::strlen(payload), s);
            std::fclose(s);
        }
        std::string manifest_json = R"({
            "casu":{"name":"CASU","container_extension":".casu","version":"2.0.0"},
            "source":{"filename":"casu_nat1_src.bin","duration_s":1.0,"size_bytes":)" +
            std::to_string(std::strlen(payload)) + R"(},
            "streams":[],
            "integrity":{"timestamps_are_source_of_truth":true}
        })";
        JsonValue m = parse_json(manifest_json);
        casunat1::write_native("/tmp/casu_nat1_out.casu", "/tmp/casu_nat1_src.bin", m);
        check(detect_casu_kind("/tmp/casu_nat1_out.casu") == CasuKind::Casunat1,
              "CASUNAT1 kind detected");
        // Read + verify.
        casunat1::Container c = casunat1::read_native("/tmp/casu_nat1_out.casu", true);
        check(c.payload_length == std::strlen(payload), "CASUNAT1 payload length");
        check(c.payload_sha256 == Sha256::oneshot(payload, std::strlen(payload)),
              "CASUNAT1 payload sha256");
        // Extract and compare bytes.
        casunat1::read_native("/tmp/casu_nat1_out.casu").extract_payload("/tmp/casu_nat1_extracted.bin");
        {
            FILE* e = std::fopen("/tmp/casu_nat1_extracted.bin", "rb");
            std::string got;
            char buf[64];
            std::size_t n;
            while ((n = std::fread(buf, 1, sizeof(buf), e)) > 0) got.append(buf, n);
            std::fclose(e);
            check(got == payload, "CASUNAT1 payload extraction round-trip");
        }
        // Corrupt payload byte -> integrity mismatch on read.
        {
            FILE* f = std::fopen("/tmp/casu_nat1_out.casu", "r+b");
            std::fseek(f, 0, SEEK_END);
            long sz = std::ftell(f);
            std::fseek(f, sz - 5, SEEK_SET);
            unsigned char b;
            std::fread(&b, 1, 1, f);
            std::fseek(f, sz - 5, SEEK_SET);
            b ^= 0xFF;
            std::fwrite(&b, 1, 1, f);
            std::fclose(f);
            bool threw = false;
            try { casunat1::read_native("/tmp/casu_nat1_out.casu", true); }
            catch (const CasuError&) { threw = true; }
            check(threw, "CASUNAT1 payload corruption detected");
        }
    }

    // --- CASUNAT2 reader (WP-CORE-004): minimal NAT2 without integrity
    // table must be rejected (fail-closed) ---
    {
        FILE* f = std::fopen("/tmp/casu_nat2_nointegrity.casu", "wb");
        auto blob = make_minimal_nat2();
        std::fwrite(blob.data(), 1, blob.size(), f);
        std::fclose(f);
        bool threw = false;
        try { casunat2::read_native_v2("/tmp/casu_nat2_nointegrity.casu", true); }
        catch (const CasuError&) { threw = true; }
        check(threw, "CASUNAT2 missing integrity table rejected");
    }
    // Bad magic rejected.
    {
        FILE* f = std::fopen("/tmp/casu_nat2_badmagic.casu", "wb");
        auto blob = make_minimal_nat2();
        blob[0] = 'X';
        std::fwrite(blob.data(), 1, blob.size(), f);
        std::fclose(f);
        bool threw = false;
        try { casunat2::read_native_v2("/tmp/casu_nat2_badmagic.casu", true); }
        catch (const CasuError&) { threw = true; }
        check(threw, "CASUNAT2 bad magic rejected (reader)");
    }

    // --- MP5 write/read/verify (WP-CORE-005) ---
    {
        std::string manifest = R"({"casu":{"name":"CASU","version":"2.0.0"},"source":{"filename":"media.bin","duration_s":1.0},"streams":[]})";
        JsonValue m = parse_json(manifest);
        std::vector<uint8_t> payload = {'h','e','l','l','o',' ','w','o','r','l','d'};
        std::vector<std::tuple<casu::mp5::ChunkType, uint8_t, uint32_t, std::vector<uint8_t>>> chunks;
        chunks.emplace_back(casu::mp5::STREAM_CONFIG, 0, 0, std::vector<uint8_t>{'c','f','g'});
        chunks.emplace_back(casu::mp5::AUDIO_BLOCK, 0, 0, payload);
        chunks.emplace_back(casu::mp5::END, 0, 0, std::vector<uint8_t>{});
        casu::mp5::write_mp5("/tmp/casu_mp5_out.mp5", m, chunks);
        check(detect_casu_kind("/tmp/casu_mp5_out.mp5") == CasuKind::Mp5, "MP5 kind detected");
        auto issues = casu::mp5::verify_mp5("/tmp/casu_mp5_out.mp5");
        // No attachment is expected for this minimal file; integrity must pass.
        bool no_digest_issue = true;
        for (const auto& i : issues) {
            if (i.find("digest") != std::string::npos || i.find("count") != std::string::npos)
                no_digest_issue = false;
        }
        check(no_digest_issue, "MP5 round-trip integrity (digest/count) OK");
        auto c2 = casu::mp5::read_mp5("/tmp/casu_mp5_out.mp5");
        check(c2.chunks.size() == 2, "MP5 chunk count (2 non-END chunks)");
        // Audio block payload round-trips via decompression.
        bool found_audio = false;
        for (const auto& cs : c2.chunks) {
            if (cs.chunk_type == casu::mp5::AUDIO_BLOCK) {
                auto pl = c2.read_chunk_payload(cs);
                check(pl == payload, "MP5 payload decompress round-trip");
                found_audio = true;
            }
        }
        check(found_audio, "MP5 audio chunk found");
    }

    // --- MP5 zstd-read path (WP-CORE-007) ---
    {
        std::string manifest = R"({"casu":{"name":"CASU","version":"2.0.0"},"source":{"filename":"media.bin","duration_s":1.0},"streams":[]})";
        std::vector<uint8_t> payload;
        for (int i = 0; i < 4096; ++i) payload.push_back(uint8_t(i * 7));
#ifdef CASU_HAVE_ZSTD
        // A zstd-compressed chunk (as produced by the reference writer when the
        // Python zstd package is installed) must be readable by the C++ reader.
        std::vector<uint8_t> comp(ZSTD_compressBound(payload.size()));
        std::size_t clen = ZSTD_compress(comp.data(), comp.size(), payload.data(), payload.size(), 3);
        check(!ZSTD_isError(clen), "zstd payload compresses");
        comp.resize(clen);
        auto blob = make_mp5_with_payload(manifest, comp);
        FILE* f = std::fopen("/tmp/casu_mp5_zstd.mp5", "wb");
        std::fwrite(blob.data(), 1, blob.size(), f);
        std::fclose(f);
        auto c = casu::mp5::read_mp5("/tmp/casu_mp5_zstd.mp5");
        check(c.chunks.size() == 1, "MP5 zstd file chunk count");
        bool ok = false;
        for (const auto& cs : c.chunks) {
            if (cs.chunk_type == casu::mp5::AUDIO_BLOCK) {
                auto pl = c.read_chunk_payload(cs);
                ok = (pl == payload);
            }
        }
        check(ok, "MP5 zstd payload decompress round-trip");
        // Corrupt payload must fail closed (no crash, typed error).
        {
            std::vector<uint8_t> junk = {'n','o','t','a','p','a','y','l','o','a','d'};
            auto bad = make_mp5_with_payload(manifest, junk);
            FILE* g = std::fopen("/tmp/casu_mp5_bad.mp5", "wb");
            std::fwrite(bad.data(), 1, bad.size(), g);
            std::fclose(g);
            auto bc = casu::mp5::read_mp5("/tmp/casu_mp5_bad.mp5");
            bool threw = false;
            try {
                for (const auto& cs : bc.chunks)
                    (void)bc.read_chunk_payload(cs);
            } catch (const CasuError&) { threw = true; }
            check(threw, "MP5 corrupt payload rejected");
        }
    }
#endif  // CASU_HAVE_ZSTD

    // --- Sidecar resolve (WP-CORE-006) ---
    {
        // Create a media file + a sidecar manifest next to it.
        const char* media = "sidecar source bytes 12345";
        std::string media_sha = Sha256::oneshot(media, std::strlen(media));
        {
            FILE* s = std::fopen("/tmp/casu_sc_media.bin", "wb");
            std::fwrite(media, 1, std::strlen(media), s);
            std::fclose(s);
        }
        {
            std::string manifest = std::string(R"({
                "casu":{"name":"CASU","container_extension":".casu","version":"2.0.0"},
                "source":{"path":"casu_sc_media.bin","filename":"casu_sc_media.bin",
                          "duration_s":1.0,"size_bytes":)") + std::to_string(std::strlen(media)) +
                R"(,"sha256":")" + media_sha + R"("},
                "streams":[],"integrity":{"timestamps_are_source_of_truth":true}
            })";
            FILE* m = std::fopen("/tmp/casu_sc_media.bin.casu", "wb");
            std::fwrite(manifest.data(), 1, manifest.size(), m);
            std::fclose(m);
        }
        std::string resolved = casu::resolve_casu_source("/tmp/casu_sc_media.bin.casu");
        check(!resolved.empty() && resolved.find("casu_sc_media.bin") != std::string::npos,
              "sidecar resolve finds source");
        // Path traversal must be rejected (filename escaping the dir).
        {
            std::string evil = R"({
                "casu":{"name":"CASU","container_extension":".casu","version":"2.0.0"},
                "source":{"path":"../etc/passwd","filename":"passwd","duration_s":1.0},
                "streams":[],"integrity":{"timestamps_are_source_of_truth":true}
            })";
            FILE* m = std::fopen("/tmp/casu_sc_evil.casu", "wb");
            std::fwrite(evil.data(), 1, evil.size(), m);
            std::fclose(m);
            bool threw = false;
            try { casu::resolve_casu_source("/tmp/casu_sc_evil.casu"); }
            catch (const CasuError&) { threw = true; }
            check(threw, "sidecar path traversal rejected");
        }
    }

    std::printf(failures == 0 ? "ALL PASS\n" : "%d FAILURES\n", failures);
    return failures == 0 ? 0 : 1;
}
