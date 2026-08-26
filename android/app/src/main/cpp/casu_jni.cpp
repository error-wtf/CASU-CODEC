// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// JNI bridge exposing the byte-parity casu_core to the Android app:
// detectKind / verifyCasunat2 (full integrity walk) / extractPayload for
// MP5 + CASUNAT1 sidecars.
#include <jni.h>
#include <filesystem>
#include <fstream>
#include <string>

#include "casu/formats.hpp"
#include "casu/native.hpp"
#include "casu/native_v2.hpp"
#include "casu/native_v2_payloads.hpp"
#include "casu/mp5.hpp"
#include "casu/sidecar.hpp"

namespace {

std::string to_std(JNIEnv* env, jstring s) {
    if (!s) return {};
    const char* utf = env->GetStringUTFChars(s, nullptr);
    std::string out = utf ? utf : "";
    if (utf) env->ReleaseStringUTFChars(s, utf);
    return out;
}

jstring to_jni(JNIEnv* env, const std::string& s) {
    return env->NewStringUTF(s.c_str());
}

}  // namespace

extern "C" JNIEXPORT jstring JNICALL
Java_org_casu_mpcasu_CasuCore_detectKind(JNIEnv* env, jclass,
                                        jstring path) {
    // A C++ exception must never escape across JNI: it would terminate the
    // whole app (uncaught casu::CasuError -> std::terminate -> SIGABRT).
    try {
        const casu::CasuKind kind = casu::detect_casu_kind(to_std(env, path));
        switch (kind) {
            case casu::CasuKind::Casunat1: return to_jni(env, "CASUNAT1");
            case casu::CasuKind::Casunat2: return to_jni(env, "CASUNAT2");
            case casu::CasuKind::Mp5: return to_jni(env, "MP5");
            case casu::CasuKind::Sidecar: return to_jni(env, "SIDECAR");
            default: return to_jni(env, "NONE");
        }
    } catch (const std::exception& e) {
        return to_jni(env, std::string("ERROR: ") + e.what());
    }
}

// Full integrity verification (header+manifest digest, chunk hashes,
// seek-index cross-checks). Returns the manifest JSON on success or throws
// into Java via an error string prefixed "ERROR: ".
extern "C" JNIEXPORT jstring JNICALL
Java_org_casu_mpcasu_CasuCore_verifyCasunat2(JNIEnv* env, jclass,
                                             jstring path) {
    try {
        const auto container = casu::casunat2::read_native_v2(to_std(env, path));
        return to_jni(env, casu::dump_json(container.manifest));
    } catch (const std::exception& e) {
        return to_jni(env, std::string("ERROR: ") + e.what());
    }
}

// Extract the playable payload of an MP5/CASUNAT1 container to cacheDir.
extern "C" JNIEXPORT jstring JNICALL
Java_org_casu_mpcasu_CasuCore_extractToCache(JNIEnv* env, jclass,
                                             jstring path,
                                             jstring cacheDir) {
    const std::string src = to_std(env, path);
    const std::string dir = to_std(env, cacheDir);
    try {
        std::error_code ec;
        const casu::CasuKind kind = casu::detect_casu_kind(src);
        if (kind == casu::CasuKind::Mp5) {
            auto [filename, payload] = casu::mp5::extract_attachment(src);
            std::string suffix = ".bin";
            const std::size_t dot = filename.rfind('.');
            if (dot != std::string::npos && filename.size() - dot <= 8)
                suffix = filename.substr(dot);
            const std::string out =
                dir + "/mp5-extract-" + std::to_string(payload.size()) + suffix;
            std::ofstream f(out, std::ios::binary | std::ios::trunc);
            f.write(reinterpret_cast<const char*>(payload.data()),
                    static_cast<std::streamsize>(payload.size()));
            return to_jni(env, out);
        }
        if (kind == casu::CasuKind::Casunat1 ||
            kind == casu::CasuKind::Sidecar) {
            const std::string resolved = casu::resolve_casu_source(src);
            return to_jni(env, resolved);
        }
        return to_jni(env, "ERROR: unsupported container kind");
    } catch (const std::exception& e) {
        return to_jni(env, std::string("ERROR: ") + e.what());
    }
}

namespace {

void put_u32le(std::vector<uint8_t>& v, uint32_t value) {
    v.push_back(static_cast<uint8_t>(value & 0xFF));
    v.push_back(static_cast<uint8_t>((value >> 8) & 0xFF));
    v.push_back(static_cast<uint8_t>((value >> 16) & 0xFF));
    v.push_back(static_cast<uint8_t>((value >> 24) & 0xFF));
}

void put_u16le(std::vector<uint8_t>& v, uint16_t value) {
    v.push_back(static_cast<uint8_t>(value & 0xFF));
    v.push_back(static_cast<uint8_t>((value >> 8) & 0xFF));
}

// Convert one decoded audio block to interleaved s16le samples appended to
// out. Supports the formats the writer emits (s16/s16le, flt/fltp via
// simple conversion); anything else reports false so the caller can fail
// with a clear message instead of writing garbage audio.
bool append_pcm_s16le(const casu::natv2::AudioBlock& block, std::vector<uint8_t>& out) {
    const int channels = static_cast<int>(block.channels > 0 ? block.channels : 1);
    const std::string fmt = block.sample_format;
    if (fmt == "s16" || fmt == "s16le" || fmt == "s16p" || fmt == "s16be") {
        // s16 native blocks are interleaved little-endian already.
        out.insert(out.end(), block.pcm.begin(), block.pcm.end());
        return true;
    }
    if (fmt == "flt" || fmt == "fltp" || fmt == "float" || fmt == "f32le") {
        const float* samples = reinterpret_cast<const float*>(block.pcm.data());
        const std::size_t count = block.pcm.size() / sizeof(float);
        out.reserve(out.size() + count * 2);
        for (std::size_t i = 0; i < count; i++) {
            float clamped = samples[i];
            if (clamped > 1.0f) clamped = 1.0f;
            if (clamped < -1.0f) clamped = -1.0f;
            const int16_t value = static_cast<int16_t>(clamped * 32767.0f);
            put_u16le(out, static_cast<uint16_t>(value));
        }
        return true;
    }
    return false;
}

}  // namespace

// Decode every CASUNAT2 audio block into one 16-bit WAV in cacheDir so the
// Android MediaPlayer can play CASU audio natively (the Linux reference
// plays these containers through its own PCM sink).
extern "C" JNIEXPORT jstring JNICALL
Java_org_casu_mpcasu_CasuCore_extractCasunat2AudioWav(JNIEnv* env, jclass,
                                                      jstring path,
                                                      jstring cacheDir) {
    const std::string src = to_std(env, path);
    const std::string dir = to_std(env, cacheDir);
    try {
        auto container = casu::casunat2::read_native_v2(src, /*load_payloads=*/false);
        // Audio stream id from the manifest.
        int audio_stream = -1;
        int64_t sample_rate = 0;
        int64_t channels = 0;
        if (container.manifest.is_object()) {
            if (const casu::JsonValue* streams = container.manifest.find("streams")) {
                if (streams->is_array()) {
                    for (const auto& stream : streams->as_array().items) {
                        if (!stream.is_object()) continue;
                        const casu::JsonValue* type = stream.find("type");
                        if (type && type->is_string() && type->as_string() == "audio") {
                            const casu::JsonValue* id = stream.find("stream_id");
                            if (id) audio_stream = static_cast<int>(id->as_int());
                            const casu::JsonValue* rate = stream.find("sample_rate");
                            if (rate) sample_rate = rate->as_int();
                            const casu::JsonValue* ch = stream.find("channels");
                            if (ch) channels = ch->as_int();
                            break;
                        }
                    }
                }
            }
        }
        std::vector<uint8_t> pcm;
        int64_t first_rate = sample_rate;
        int64_t first_channels = channels;
        for (std::size_t i = 0; i < container.chunks.size(); i++) {
            const auto& summary = container.chunks[i];
            if (summary.chunk_type != casu::casunat2::ChunkType::AUDIO_BLOCK) continue;
            if (audio_stream >= 0 && summary.stream_id != audio_stream) continue;
            const casu::casunat2::Chunk chunk = container.read_chunk_at(container.offsets[i]);
            const casu::natv2::AudioBlock block = casu::natv2::decode_audio_block(chunk.payload);
            if (first_rate == 0) { first_rate = block.sample_rate; first_channels = block.channels; }
            if (!append_pcm_s16le(block, pcm)) {
                return to_jni(env, "ERROR: unsupported sample format " + block.sample_format);
            }
        }
        if (pcm.empty()) return to_jni(env, "ERROR: container has no audio blocks");
        if (first_rate <= 0) first_rate = 44100;
        if (first_channels <= 0) first_channels = 1;
        // RIFF/WAVE header (s16le interleaved).
        const uint32_t data_size = static_cast<uint32_t>(pcm.size());
        const uint32_t byte_rate = static_cast<uint32_t>(first_rate * first_channels * 2);
        std::vector<uint8_t> wav;
        wav.reserve(data_size + 44);
        wav.insert(wav.end(), {'R','I','F','F'});
        put_u32le(wav, 36 + data_size);
        wav.insert(wav.end(), {'W','A','V','E','f','m','t',' '});
        put_u32le(wav, 16);
        put_u16le(wav, 1);  // PCM
        put_u16le(wav, static_cast<uint16_t>(first_channels));
        put_u32le(wav, static_cast<uint32_t>(first_rate));
        put_u32le(wav, byte_rate);
        put_u16le(wav, static_cast<uint16_t>(first_channels * 2));
        put_u16le(wav, 16);
        wav.insert(wav.end(), {'d','a','t','a'});
        put_u32le(wav, data_size);
        wav.insert(wav.end(), pcm.begin(), pcm.end());
        std::string out = dir + "/casu-audio-" + std::to_string(data_size) + ".wav";
        std::ofstream f(out, std::ios::binary | std::ios::trunc);
        f.write(reinterpret_cast<const char*>(wav.data()),
                static_cast<std::streamsize>(wav.size()));
        if (!f.good()) return to_jni(env, "ERROR: cannot write wav to cache");
        return to_jni(env, out);
    } catch (const std::exception& e) {
        return to_jni(env, std::string("ERROR: ") + e.what());
    }
}
