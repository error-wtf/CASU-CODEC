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
