// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// SPDX-FileCopyrightText: 2026 Lino Casu
package org.casu.mpcasu;

import android.media.MediaCodec;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.media.MediaMuxer;
import android.os.Build;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.ByteBuffer;
import java.util.HashMap;
import java.util.Map;

/** Records a network stream to a playable file — the Android twin of the
 *  Linux/Windows ffmpeg recorder.
 *
 *  Two engines:
 *  - MUXER: MediaExtractor pulls the stream (supports direct MP4/AAC and HLS)
 *    and MediaMuxer writes a REAL container (MP4 / TS / ADTS-AAC / OGG) with
 *    the selected tracks. Audio-only options drop the video track.
 *  - COPY: byte-exact stream copy for progressive radio/TS streams.
 *
 *  Because MediaMuxer only writes to file paths, muxer recordings land in a
 *  temp file first and are moved to the destination (SAF folder or app dir)
 *  when finished. */
public final class StreamRecorder {

    public interface Listener {
        void onStarted(String info);
        void onProgress(long seconds, long bytes);
        void onFinished(String fileName, long bytes, String error);
    }

    public static final String FMT_MP4 = "mp4";   // video + audio
    public static final String FMT_M4A = "m4a";   // audio only (MP4 container)
    public static final String FMT_OGG = "ogg";   // audio only
    public static final String FMT_MP3 = "mp3";   // audio only (byte copy)
    public static final String FMT_COPY = "copy"; // raw stream copy

    /** Output extensions per format. */
    public static String extensionFor(String format, String sourceUrl) {
        switch (format) {
            case FMT_MP4: return "mp4";
            case FMT_M4A: return "m4a";
            case FMT_OGG: return "ogg";
            case FMT_MP3: return "mp3";
            default: {
                // COPY keeps the source container: guess from URL/content.
                String u = sourceUrl == null ? "" : sourceUrl.toLowerCase();
                if (u.contains(".mp3")) return "mp3";
                if (u.contains(".aac")) return "aac";
                if (u.contains(".ogg")) return "ogg";
                if (u.contains(".mp4")) return "mp4";
                if (u.contains(".m4a")) return "m4a";
                if (u.contains(".flac")) return "flac";
                return "ts";
            }
        }
    }

    /** Whether the running Android version supports the muxer format. */
    public static boolean formatSupported(String format) {
        switch (format) {
            case FMT_MP4:
            case FMT_M4A:
            case FMT_MP3:
            case FMT_COPY:
                return true;
            case FMT_OGG:
                return Build.VERSION.SDK_INT >= 29;
            default:
                return false;
        }
    }

    private final android.content.Context context;
    private final String sourceUrl;
    private final File destination;       // final file path (app dir)
    private final androidx.documentfile.provider.DocumentFile destinationDir; // or SAF dir
    private final String format;
    private final Listener listener;
    private volatile boolean stopped = false;
    private Thread thread;
    private long totalBytes;

    public StreamRecorder(android.content.Context context, String sourceUrl,
                          File destination,
                          androidx.documentfile.provider.DocumentFile destinationDir,
                          String format, Listener listener) {
        this.context = context.getApplicationContext();
        this.sourceUrl = sourceUrl;
        this.destination = destination;
        this.destinationDir = destinationDir;
        this.format = format;
        this.listener = listener;
    }

    public void start() {
        thread = new Thread(this::run, "StreamRecorder");
        thread.start();
    }

    public void stop() {
        stopped = true;
    }

    public boolean isStopped() {
        return stopped;
    }

    private void run() {
        String error = null;
        String finalName = destination != null ? destination.getName()
                : "recording";
        try {
            if (FMT_MP3.equals(format) || FMT_COPY.equals(format)) {
                if (destination != null && destination.exists()
                        && !sourceUrl.startsWith("http")) {
                    finalName = runLocalCopy();
                } else {
                    finalName = runCopy(FMT_MP3.equals(format) ? "mp3"
                            : extensionFor(FMT_COPY, sourceUrl));
                }
            } else {
                finalName = runMuxer();
            }
        } catch (Exception e) {
            error = e.getMessage() == null ? e.getClass().getSimpleName()
                    : e.getMessage();
            android.util.Log.e("StreamRecorder", "recording failed", e);
        }
        final String name = finalName;
        final String err = error;
        final long bytes = totalBytes;
        notifyFinished(name, bytes, err);
    }

    // ------------------------------------------------------------- raw copy

    private String runCopy() throws Exception {
        return runCopy(extensionFor(FMT_COPY, sourceUrl));
    }

    private String runLocalCopy() throws Exception {
        try (DestinationTarget target = openDestination(extensionFor(format, sourceUrl))) {
            long start = System.currentTimeMillis();
            try (InputStream in = new FileInputStream(destination)) {
                byte[] chunk = new byte[64 * 1024];
                int n;
                while (!stopped && (n = in.read(chunk)) > 0) {
                    target.out.write(chunk, 0, n);
                    totalBytes += n;
                }
            }
            if (totalBytes == 0) {
                throw new IllegalStateException("Keine Daten empfangen");
            }
        }
        return currentName;
    }

    private String runCopy(String ext) throws Exception {
        try (DestinationTarget target = openDestination(ext)) {
            HttpURLConnection conn = (HttpURLConnection) new URL(sourceUrl).openConnection();
            conn.setConnectTimeout(15000);
            conn.setReadTimeout(15000);
            conn.setRequestProperty("User-Agent",
                    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36");
            conn.setInstanceFollowRedirects(true);
            int code = conn.getResponseCode();
            if (code < 200 || code >= 300) {
                throw new IllegalStateException("HTTP " + code);
            }
            long start = System.currentTimeMillis();
            try (InputStream in = conn.getInputStream()) {
                byte[] chunk = new byte[64 * 1024];
                long lastReport = 0;
                int n;
                while (!stopped && (n = in.read(chunk)) > 0) {
                    target.out.write(chunk, 0, n);
                    totalBytes += n;
                    if (System.currentTimeMillis() - lastReport > 1000) {
                        lastReport = System.currentTimeMillis();
                        // live streams have no timeline — report wall time
                        notifyProgress((System.currentTimeMillis() - start) / 1000L,
                                totalBytes);
                    }
                }
            } finally {
                conn.disconnect();
            }
        }
        return currentName;
    }

    // --------------------------------------------------------------- muxer

    private String runMuxer() throws Exception {
        MediaExtractor extractor = new MediaExtractor();
        MediaMuxer muxer = null;
        File tmp = null;
        try {
            // Own HTTP datasource: MediaExtractor's built-in network source has
            // no timeouts and can hang forever on live streams.
            HttpStreamDataSource source = new HttpStreamDataSource(sourceUrl, 15000);
            try {
                extractor.setDataSource(source);
            } catch (Exception e) {
                source.close();
                // Live fMP4/DASH streams (YouTube live) can't be sniffed —
                // fall back to a byte copy, which stays a playable MP4/M4A.
                return runCopy(extensionFor(format, sourceUrl));
            }

            // MediaMuxer writes to a real path only → temp file, then move.
            tmp = File.createTempFile("rec-tmp-",
                    "." + extensionFor(format, sourceUrl),
                    destination != null ? destination.getParentFile()
                            : context.getExternalCacheDir());
            int muxerFormat;
            switch (format) {
                case FMT_OGG: muxerFormat = MediaMuxer.OutputFormat.MUXER_OUTPUT_OGG; break;
                default: muxerFormat = MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4; break;
            }

            boolean audioOnly = FMT_M4A.equals(format) || FMT_OGG.equals(format);

            muxer = new MediaMuxer(tmp.getAbsolutePath(), muxerFormat);
            Map<Integer, Integer> trackMap = new HashMap<>();
            boolean haveVideo = false;
            for (int i = 0; i < extractor.getTrackCount(); i++) {
                MediaFormat fmt = extractor.getTrackFormat(i);
                String mime = fmt.getString(MediaFormat.KEY_MIME);
                if (mime == null) continue;
                boolean isVideo = mime.startsWith("video/");
                boolean isAudio = mime.startsWith("audio/");
                if (isVideo && audioOnly) continue;  // drop video if audio-only
                if (!isVideo && !isAudio) continue;
                if (haveVideo && isVideo) continue;   // first video track wins
                try {
                    extractor.selectTrack(i);
                    trackMap.put(i, muxer.addTrack(fmt));
                    if (isVideo) haveVideo = true;
                } catch (Exception ignored) {
                    // unsupported track → skip it, keep the rest
                }
            }
            if (trackMap.isEmpty()) {
                throw new IllegalStateException(
                        "Stream enthält keine verwertbaren Spuren");
            }

            muxer.start();
            ByteBuffer buffer = ByteBuffer.allocateDirect(1 << 20);
            MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
            long lastReport = 0;
            long maxTimeUs = 0;
            while (!stopped) {
                int track = extractor.getSampleTrackIndex();
                if (track < 0) break;  // end of stream
                int size = extractor.readSampleData(buffer, 0);
                if (size < 0) break;
                Integer mapped = trackMap.get(track);
                if (mapped != null) {
                    info.offset = 0;
                    info.size = size;
                    info.presentationTimeUs = extractor.getSampleTime();
                    info.flags = extractor.getSampleFlags()
                            & MediaCodec.BUFFER_FLAG_KEY_FRAME;
                    muxer.writeSampleData(mapped, buffer, info);
                    totalBytes += size;
                    maxTimeUs = Math.max(maxTimeUs, info.presentationTimeUs);
                }
                extractor.advance();
                if (System.currentTimeMillis() - lastReport > 1000) {
                    lastReport = System.currentTimeMillis();
                    notifyProgress(maxTimeUs / 1000L, totalBytes);
                }
            }
            try {
                muxer.stop();
            } catch (Exception ignored) {
                // partial live recording: stop() may complain about missing
                // trailing data — the file is still playable
            }
            notifyProgress(maxTimeUs / 1000L, totalBytes);
        } catch (Exception e) {
            if (tmp != null) tmp.delete();  // no junk left behind
            throw e;
        } finally {
            try { extractor.release(); } catch (Exception ignored) {}
            if (muxer != null) {
                try { muxer.release(); } catch (Exception ignored) {}
            }
        }
        if (totalBytes == 0) {
            // no data: don't leave junk behind
            tmp.delete();
            throw new IllegalStateException("Keine Daten empfangen");
        }

        // Move the finished recording to its destination.
        if (destination != null) {
            moveFile(tmp, destination);
            return destination.getName();
        } else {
            String name = moveToSaf(tmp, extensionFor(format, sourceUrl));
            if (name == null) {
                // SAF failed — keep it in the app dir so nothing is lost.
                File fallback = defaultFallback();
                moveFile(tmp, fallback);
                return fallback.getName();
            }
            return name;
        }
    }

    // ----------------------------------------------------------- destination

    /** Opens the final output stream: SAF folder or plain file. */
    private DestinationTarget openDestination(String ext) throws Exception {
        String stamp = new java.text.SimpleDateFormat("yyyyMMdd-HHmmss",
                java.util.Locale.US).format(new java.util.Date());
        if (destinationDir != null) {
            String mime = mimeFor(ext);
            androidx.documentfile.provider.DocumentFile file =
                    destinationDir.createFile(mime, "rec-" + stamp);
            if (file == null) {
                throw new IllegalStateException(
                        "Zielordner nicht beschreibbar (SAF)");
            }
            currentName = file.getName();
            OutputStream out = context.getContentResolver()
                    .openOutputStream(file.getUri(), "w");
            return new DestinationTarget(out, null);
        }
        File target = destination != null ? destination
                : new File(defaultDir(), "rec-" + stamp + "." + ext);
        currentName = target.getName();
        return new DestinationTarget(new FileOutputStream(target), target);
    }

    private String currentName = "recording";

    private static final class DestinationTarget implements AutoCloseable {
        final OutputStream out;
        final File file;
        DestinationTarget(OutputStream out, File file) {
            this.out = out;
            this.file = file;
        }
        @Override public void close() {
            try { out.flush(); } catch (Exception ignored) {}
            try { out.close(); } catch (Exception ignored) {}
        }
    }

    private File defaultDir() {
        // App-specific dir: no storage permission needed (the SAF picker
        // covers user-chosen locations like Download/ or SD cards).
        File dir = new File(context.getExternalFilesDir(
                android.os.Environment.DIRECTORY_MUSIC), "MPCASU");
        dir.mkdirs();
        return dir;
    }

    private File defaultFallback() {
        File dir = defaultDir();
        dir.mkdirs();
        return new File(dir, "rec-" + System.currentTimeMillis() + "."
                + extensionFor(format, sourceUrl));
    }

    private String moveToSaf(File tmp, String ext) {
        try {
            String stamp = new java.text.SimpleDateFormat("yyyyMMdd-HHmmss",
                    java.util.Locale.US).format(new java.util.Date());
            androidx.documentfile.provider.DocumentFile file =
                    destinationDir.createFile(mimeFor(ext), "rec-" + stamp);
            if (file == null) return null;
            try (InputStream in = new FileInputStream(tmp);
                 OutputStream out = context.getContentResolver()
                         .openOutputStream(file.getUri(), "w")) {
                byte[] chunk = new byte[64 * 1024];
                int n;
                while ((n = in.read(chunk)) > 0) out.write(chunk, 0, n);
            }
            tmp.delete();
            return file.getName();
        } catch (Exception e) {
            return null;
        }
    }

    private static void moveFile(File from, File to) throws Exception {
        if (to.getParentFile() != null) to.getParentFile().mkdirs();
        try (InputStream in = new FileInputStream(from);
             OutputStream out = new FileOutputStream(to)) {
            byte[] chunk = new byte[64 * 1024];
            int n;
            while ((n = in.read(chunk)) > 0) out.write(chunk, 0, n);
        }
        from.delete();
    }

    private static String mimeFor(String ext) {
        switch (ext) {
            case "mp4": return "video/mp4";
            case "m4a": return "audio/mp4";
            case "ts": return "video/mp2ts";
            case "aac": return "audio/aac";
            case "ogg": return "audio/ogg";
            case "mp3": return "audio/mpeg";
            case "flac": return "audio/flac";
            default: return "application/octet-stream";
        }
    }

    // -------------------------------------------------------------- notify

    private void notifyProgress(long seconds, long bytes) {
        if (listener == null) return;
        listener.onProgress(seconds, bytes);
    }

    private void notifyFinished(String name, long bytes, String error) {
        if (listener == null) return;
        listener.onFinished(name, bytes, error);
    }

    // ------------------------------------------------------- http datasource

    /** MediaDataSource over HttpURLConnection with REAL timeouts and Range
     *  support — MediaExtractor's built-in network source hangs forever on
     *  some live streams. The extractor reads mostly sequentially; seeks
     *  reconnect with a Range header. */
    static final class HttpStreamDataSource extends android.media.MediaDataSource {
        private static final String UA =
                "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36";
        private final String url;
        private final int timeoutMs;
        private HttpURLConnection conn;
        private InputStream in;
        private long streamPos = 0;      // next byte position served by `in`
        private final byte[] skip = new byte[8192];

        HttpStreamDataSource(String url, int timeoutMs) {
            this.url = url;
            this.timeoutMs = timeoutMs;
        }

        private void closeStream() {
            try { if (in != null) in.close(); } catch (Exception ignored) {}
            in = null;
            try { if (conn != null) conn.disconnect(); } catch (Exception ignored) {}
            conn = null;
        }

        private void openAt(long position) throws java.io.IOException {
            closeStream();
            HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
            c.setConnectTimeout(timeoutMs);
            c.setReadTimeout(timeoutMs);
            c.setInstanceFollowRedirects(true);
            c.setRequestProperty("User-Agent", UA);
            if (position > 0) {
                c.setRequestProperty("Range", "bytes=" + position + "-");
            }
            int code = c.getResponseCode();
            if (code < 200 || code >= 300) {
                c.disconnect();
                throw new java.io.IOException("HTTP " + code);
            }
            conn = c;
            in = c.getInputStream();
            if (position > 0 && code == 200) {
                // server ignored Range — skip forward manually
                long toSkip = position;
                while (toSkip > 0) {
                    int n = in.read(skip, 0, (int) Math.min(toSkip, skip.length));
                    if (n < 0) throw new java.io.EOFException("stream ended while seeking");
                    toSkip -= n;
                }
            }
            streamPos = position;
        }

        @Override
        public synchronized int readAt(long position, byte[] buffer, int offset,
                                       int size) throws java.io.IOException {
            if (size == 0) return 0;
            if (in == null || position != streamPos) {
                openAt(position);
            }
            int n = in.read(buffer, offset, size);
            if (n > 0) streamPos += n;
            return n;
        }

        @Override
        public synchronized long getSize() {
            return -1;  // unknown (live / streaming)
        }

        @Override
        public synchronized void close() {
            closeStream();
        }
    }
}
