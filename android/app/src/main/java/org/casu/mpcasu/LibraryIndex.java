package org.casu.mpcasu;

import android.content.Context;
import android.os.Environment;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.Socket;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Android media library: scans the public media directories (Music,
 * Movies, Downloads, Podcasts) for audio/video files — the Android
 * equivalent of the Linux watched-folders library. First start indexes
 * everything; every later start extends with NEW files only, and
 * Options → "Refresh library" re-scans on demand (bootstrap JS).
 *
 * Files are served same-origin via /media?path=… with HTTP Range support
 * so seeking works inside the WebView player.
 */
final class LibraryIndex {

    private static final Set<String> AUDIO = new HashSet<>(Arrays.asList(
            "mp3", "flac", "wav", "ogg", "oga", "m4a", "aac", "opus", "wma", "alac", "mp2"));
    private static final Set<String> VIDEO = new HashSet<>(Arrays.asList(
            "mp4", "mkv", "m4v", "mov", "webm", "avi", "ts"));
    private static final Set<String> PLAYLISTS = new HashSet<>(Arrays.asList(
            "m3u", "m3u8", "pls"));

    private LibraryIndex() {}

    static File[] roots(Context context) {
        List<File> roots = new ArrayList<>();
        roots.add(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MUSIC));
        roots.add(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MOVIES));
        roots.add(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS));
        roots.add(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PODCASTS));
        File appMedia = new File(context.getExternalFilesDir(null), "media");
        if (!appMedia.exists()) appMedia.mkdirs();
        roots.add(appMedia);
        return roots.toArray(new File[0]);
    }

    /** M3U for the MPCASU config preload: detected library media followed
     * by the bundled RADIO.m3u stations. The player appends these on every
     * start, so new library files extend the queue automatically. */
    static String libraryM3u(LoopbackServer.AssetSource assets) throws java.io.IOException {
        StringBuilder sb = new StringBuilder("#EXTM3U\n");
        byte[] radioBytes = assets.read("web/RADIO.m3u");
        try (InputStream radio = new java.io.ByteArrayInputStream(radioBytes)) {
            String text = new String(radioBytes, StandardCharsets.UTF_8);
            String pending = null;
            for (String line : text.split("\\r?\\n")) {
                String t = line.trim();
                if (t.startsWith("#EXTINF:")) {
                    int comma = t.indexOf(',');
                    pending = comma >= 0 ? t.substring(comma + 1).trim() : "Radio";
                } else if (!t.isEmpty() && !t.startsWith("#")) {
                    sb.append("#EXTINF:-1,").append(pending != null ? pending : t)
                      .append('\n').append(t).append('\n');
                    pending = null;
                }
            }
        } catch (IOException ignored) {
            // bundled radio list missing — library-only preload
        }
        for (File root : roots(MpcasuApp.context())) {
            for (File f : listMedia(root, 0)) {
                if (PLAYLISTS.contains(ext(f.getName()))) continue;
                sb.append("#EXTINF:-1,").append(titleOf(f))
                  .append("\n/media?path=")
                  .append(java.net.URLEncoder.encode(
                      f.getAbsolutePath(), StandardCharsets.UTF_8))
                  .append('\n');
            }
        }
        return sb.toString();
    }

    /** JSON queue feed: every playable file under the public media roots. */
    static String json() {
        StringBuilder sb = new StringBuilder("{\"items\":[");
        boolean first = true;
        for (File root : LibraryIndex.roots(MpcasuApp.context())) {
            for (File f : listMedia(root, 0)) {
                if (!first) sb.append(',');
                first = false;
                String path = f.getAbsolutePath().replace("\"", "\\\"");
                sb.append("{\"path\":\"").append(path).append('"')
                  .append(",\"url\":\"/media?path=")
                  .append(java.net.URLEncoder.encode(path, StandardCharsets.UTF_8))
                  .append('"')
                  .append(",\"title\":\"").append(titleOf(f).replace("\"", "\\\"")).append('"')
                  .append(",\"kind\":\"").append(kindOf(f)).append('"')
                  .append(",\"modified\":").append(f.lastModified()).append('}');
            }
        }
        sb.append("]}");
        return sb.toString();
    }

    /** Stream a whitelisted library file same-origin (Range → 206 seek). */
    static void serveMedia(Socket client, String encoded, String rangeHeader,
                           LoopbackResponder responder) {
        String path;
        try {
            path = URLDecoder.decode(encoded, "UTF-8");
        } catch (java.io.UnsupportedEncodingException | IllegalArgumentException e) {
            path = encoded;
        }
        File file = new File(path).getAbsoluteFile();
        if (!isUnderRoot(file) || !file.isFile()) {
            try {
                responder.respond(client, 403, "text/plain",
                        "forbidden".getBytes(StandardCharsets.UTF_8));
            } catch (IOException ignored) {}
            return;
        }
        long length = file.length();
        long start = 0, end = length - 1;
        boolean partial = false;
        if (rangeHeader != null && rangeHeader.startsWith("bytes=")) {
            // "bytes=start-" or "bytes=start-end" (end inclusive, optional)
            try {
                String spec = rangeHeader.substring("bytes=".length());
                int dash = spec.indexOf('-');
                start = Long.parseLong(spec.substring(0, dash).trim());
                if (dash + 1 < spec.length())
                    end = Long.parseLong(spec.substring(dash + 1).trim());
                partial = true;
            } catch (RuntimeException ignored) {
                start = 0;
                end = length - 1;
                partial = false;
            }
        }
        try {
            OutputStream out = client.getOutputStream();
            out.write(("HTTP/1.1 " + (partial ? 206 : 200) + " OK\r\n"
                       + "Content-Type: " + contentTypeOf(file) + "\r\n"
                       + "Content-Length: " + (end - start + 1) + "\r\n"
                       + "Accept-Ranges: bytes\r\n"
                       + (partial ? "Content-Range: bytes " + start + "-" + end + "/" + length + "\r\n" : "")
                       + "Access-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n")
                              .getBytes(StandardCharsets.UTF_8));
            out.flush();
            try (InputStream in = new java.io.FileInputStream(file)) {
                in.skipNBytes(start);
                byte[] buf = new byte[64 * 1024];
                long remaining = end - start + 1;
                int n;
                while (remaining > 0 && (n = in.read(buf, 0,
                        (int) Math.min(buf.length, remaining))) > 0) {
                    out.write(buf, 0, n);
                    out.flush();
                    remaining -= n;
                }
            }
        } catch (IOException ignored) {
        }
    }

    interface LoopbackResponder {
        void respond(Socket client, int status, String type, byte[] body) throws IOException;
    }

    private static List<File> listMedia(File dir, int depth) {
        List<File> out = new ArrayList<>();
        if (dir == null || !dir.isDirectory() || depth > 6) return out;
        File[] children = dir.listFiles();
        if (children == null) return out;
        Arrays.sort(children, (a, b) -> a.getName().compareToIgnoreCase(b.getName()));
        for (File f : children) {
            if (f.isDirectory()) {
                out.addAll(listMedia(f, depth + 1));
            } else if (isMedia(f.getName())) {
                out.add(f);
            }
        }
        return out;
    }

    static boolean isMedia(String name) {
        String ext = ext(name);
        return AUDIO.contains(ext) || VIDEO.contains(ext) || PLAYLISTS.contains(ext);
    }

    private static boolean isUnderRoot(File file) {
        for (File root : roots(MpcasuApp.context())) {
            if (file.getPath().startsWith(root.getPath())) return true;
        }
        return false;
    }

    private static String ext(String name) {
        int dot = name.lastIndexOf('.');
        return dot < 0 ? "" : name.substring(dot + 1).toLowerCase(Locale.ROOT);
    }

    private static String kindOf(File f) {
        String ext = ext(f.getName());
        return PLAYLISTS.contains(ext) ? "playlist"
                : AUDIO.contains(ext) ? "audio" : "video";
    }

    private static String titleOf(File f) {
        String name = f.getName();
        int dot = name.lastIndexOf('.');
        return dot < 0 ? name : name.substring(0, dot);
    }

    private static String contentTypeOf(File f) {
        String ext = ext(f.getName());
        switch (ext) {
            case "mp3": return "audio/mpeg";
            case "flac": return "audio/flac";
            case "wav": return "audio/wav";
            case "ogg": case "oga": case "opus": return "audio/ogg";
            case "m4a": case "aac": return "audio/mp4";
            case "mp4": case "m4v": return "video/mp4";
            case "mkv": return "video/x-matroska";
            case "webm": return "video/webm";
            case "mov": return "video/quicktime";
            case "m3u": case "m3u8": return "audio/x-mpegurl";
            case "pls": return "audio/x-scpls";
            default: return "application/octet-stream";
        }
    }
}
