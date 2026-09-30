// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// SPDX-FileCopyrightText: 2026 Lino Casu
package org.casu.mpcasu;

import android.util.Log;

/** Bridge to the byte-parity casucore (JNI). All functions return error
 *  strings prefixed "ERROR: " instead of throwing across the boundary.
 *  The static block loads libcasucore.so once per process BEFORE the first
 *  native call — previously no loadLibrary existed anywhere, so every
 *  .casu/.mp5 open died with an UnsatisfiedLinkError. */
public final class CasuBridge {

    private static final String TAG = "CasuBridge";
    private static boolean libraryLoaded;

    static {
        try {
            // CMake target "casucore" -> libcasucore.so
            System.loadLibrary("casucore");
            libraryLoaded = true;
        } catch (Throwable t) {
            // Never crash the app at class-init: callers fall back to the
            // safe wrappers below and surface an error string instead.
            libraryLoaded = false;
            Log.e(TAG, "libcasucore.so missing: " + t);
        }
    }

    /** True when the native core is bound (diagnostics / media info). */
    public static boolean isNativeAvailable() {
        return libraryLoaded;
    }

    public static native String detectKind(String path);
    public static native String verifyCasunat2(String path);
    public static native String extractToCache(String path, String cacheDir);
    /** Decode all CASUNAT2 audio blocks into a 16-bit WAV in cacheDir.
     *  Returns the WAV path, or "ERROR: ...". */
    public static native String extractCasunat2AudioWav(String path, String cacheDir);

    /** Warm-up probe: must never throw across JNI. */
    public static void warmUp() {
        try {
            detectKind("/nonexistent");
        } catch (Throwable ignored) {
            // A missing/wrong native core must not take the app down.
        }
    }

    /** Returns the playable file for a CASU/MP5 container, or null. */
    public static String extractToCacheSafe(String path, String cacheDir) {
        try {
            String result = extractToCache(path, cacheDir);
            if (result != null && !result.startsWith("ERROR")) return result;
        } catch (Throwable ignored) {}
        return null;
    }

    /** CASUNAT2 → WAV in cache (audio playback path), or null on failure. */
    public static String extractAudioWavSafe(String path, String cacheDir) {
        try {
            String result = extractCasunat2AudioWav(path, cacheDir);
            if (result != null && !result.startsWith("ERROR")) return result;
        } catch (Throwable ignored) {}
        return null;
    }
}
