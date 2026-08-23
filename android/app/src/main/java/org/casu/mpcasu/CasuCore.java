package org.casu.mpcasu;

/** JNI bridge to the byte-parity casu_core (same sources as Windows/Linux). */
public final class CasuCore {
    static {
        System.loadLibrary("casucore");
    }

    /** Container kind: CASUNAT1 | CASUNAT2 | MP5 | SIDECAR | NONE. */
    public static native String detectKind(String path);

    /** Full CASUNAT2 integrity verification. Returns manifest JSON or "ERROR: …". */
    public static native String verifyCasunat2(String path);

    /** Extract playable payload for MP5 / resolve sidecar source. Returns path or "ERROR: …". */
    public static native String extractToCache(String path, String cacheDir);

    private CasuCore() {}
}
