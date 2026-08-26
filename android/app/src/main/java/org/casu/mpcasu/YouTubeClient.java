// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// SPDX-FileCopyrightText: 2026 Lino Casu
package org.casu.mpcasu;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/** YouTube over the public Innertube API with the ANDROID client — the
 *  same client family the Linux reference forces through yt-dlp
 *  (player_client=android) because it returns a byte-range-capable
 *  progressive MP4. Search + player resolve, no API key, clear errors. */
public final class YouTubeClient {

    public static final class Video {
        public String id;
        public String title;
        public String channel;
        public long durationSeconds;
        public String thumbnail;
    }

    public static final class YouTubeException extends Exception {
        public final String code; // taxonomy id for the UI
        public YouTubeException(String code, String message) {
            super(message);
            this.code = code;
        }
    }

    private static final String UA =
            "com.google.android.youtube/19.09.37 (Linux; U; Android 14) gzip";
    private static final String CONTEXT =
            "{\"context\":{\"client\":{\"clientName\":\"ANDROID\","
            + "\"clientVersion\":\"19.09.37\",\"androidSdkVersion\":34,"
            + "\"hl\":\"en\",\"gl\":\"US\"}}}";

    // ------------------------------------------------------------------ search

    public static List<Video> search(String query, int limit) throws YouTubeException {
        try {
            JSONObject body = new JSONObject();
            JSONObject context = new JSONObject(CONTEXT).getJSONObject("context");
            body.put("context", context);
            body.put("query", query);
            JSONObject response = post("https://www.youtube.com/youtubei/v1/search", body);
            List<Video> out = new ArrayList<>();
            walkSearchResults(response.optJSONObject("contents"), out);
            if (out.isEmpty()) {
                throw new YouTubeException("resolver-changed",
                        "YouTube-Antwort enthielt keine Ergebnisse (resolver-changed)");
            }
            while (out.size() > limit) out.remove(out.size() - 1);
            return out;
        } catch (YouTubeException e) {
            throw e;
        } catch (Exception e) {
            throw new YouTubeException("network-offline",
                    "Suche fehlgeschlagen: " + rootMessage(e));
        }
    }

    private static void walkSearchResults(JSONObject contents, List<Video> out) {
        if (contents == null) return;
        JSONArray array = contents.optJSONArray("contents");
        if (array == null) return;
        for (int i = 0; i < array.length() && out.size() < 40; i++) {
            JSONObject renderer = array.optJSONObject(i);
            if (renderer == null) continue;
            JSONObject videoRenderer = renderer.optJSONObject("videoRenderer");
            if (videoRenderer == null) {
                // nested sections (itemSectionRenderer)
                JSONObject section = renderer.optJSONObject("itemSectionRenderer");
                if (section != null) walkSearchResults(section, out);
                continue;
            }
            Video video = new Video();
            video.id = videoRenderer.optString("videoId", "");
            JSONObject title = videoRenderer.optJSONObject("title");
            video.title = title != null ? text(title.optJSONArray("runs")) : "";
            if (video.title.isEmpty()) video.title = video.id;
            JSONObject owner = videoRenderer.optJSONObject("ownerText");
            if (owner != null) video.channel = text(owner.optJSONArray("runs"));
            JSONObject length = videoRenderer.optJSONObject("lengthText");
            video.durationSeconds = parseDuration(length != null ? length.optString("simpleText", "") : "");
            JSONArray thumbnails = videoRenderer.optJSONObject("thumbnail") != null
                    ? videoRenderer.optJSONObject("thumbnail").optJSONArray("thumbnails") : null;
            if (thumbnails != null && thumbnails.length() > 0) {
                JSONObject last = thumbnails.optJSONObject(thumbnails.length() - 1);
                if (last != null) video.thumbnail = last.optString("url", "");
            }
            if (!video.id.isEmpty()) out.add(video);
        }
    }

    private static String text(JSONArray runs) {
        if (runs == null) return "";
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < runs.length(); i++) {
            JSONObject run = runs.optJSONObject(i);
            if (run != null) sb.append(run.optString("text", ""));
        }
        return sb.toString();
    }

    // ------------------------------------------------------------------ resolve

    /** Returns a direct playable media URL for a video id/URL. */
    public static String resolveMediaUrl(String videoIdOrUrl) throws YouTubeException {
        String id = extractVideoId(videoIdOrUrl);
        if (id == null || id.isEmpty()) {
            throw new YouTubeException("invalid-url", "Keine YouTube-Video-ID erkannt (invalid-url)");
        }
        try {
            JSONObject body = new JSONObject();
            JSONObject context = new JSONObject(CONTEXT).getJSONObject("context");
            body.put("context", context);
            body.put("videoId", id);
            body.put("contentCheckOk", true);
            body.put("racyCheckOk", true);
            JSONObject response = post("https://www.youtube.com/youtubei/v1/player", body);
            String status = response.optJSONObject("playabilityStatus") != null
                    ? response.optJSONObject("playabilityStatus").optString("status", "") : "";
            if (!"OK".equals(status)) {
                String reason = response.optJSONObject("playabilityStatus") != null
                        ? response.optJSONObject("playabilityStatus").optString("reason", status)
                        : status;
                String code = "resolver-changed";
                if (reason != null && reason.toLowerCase().contains("sign in")) code = "auth-required";
                else if (reason != null && reason.toLowerCase().contains("age")) code = "auth-required";
                else if (reason != null && reason.toLowerCase().contains("not available")) code = "geo-blocked";
                throw new YouTubeException(code, "YouTube: " + reason + " (" + code + ")");
            }
            JSONObject streamingData = response.optJSONObject("streamingData");
            if (streamingData == null) {
                throw new YouTubeException("resolver-changed", "YouTube: keine streamingData (resolver-changed)");
            }
            // Progressive formats (video+audio in one stream) — exactly what
            // the Linux reference selects with player_client=android.
            JSONArray formats = streamingData.optJSONArray("formats");
            String best = null;
            long bestPixels = -1;
            if (formats != null) {
                for (int i = 0; i < formats.length(); i++) {
                    JSONObject format = formats.optJSONObject(i);
                    if (format == null) continue;
                    String url = format.optString("url", "");
                    if (url.isEmpty()) continue;
                    String mime = format.optString("mimeType", "");
                    if (!mime.startsWith("video/mp4") && !mime.startsWith("video/webm")) continue;
                    long width = format.optLong("width", 0);
                    long height = format.optLong("height", 0);
                    long pixels = width * height;
                    if (pixels > bestPixels) {
                        bestPixels = pixels;
                        best = url;
                    }
                }
            }
            if (best == null) {
                // Fallback: adaptive audio-only so radio-style playback works.
                JSONArray adaptive = streamingData.optJSONArray("adaptiveFormats");
                if (adaptive != null) {
                    long bestBitrate = -1;
                    for (int i = 0; i < adaptive.length(); i++) {
                        JSONObject format = adaptive.optJSONObject(i);
                        if (format == null) continue;
                        String mime = format.optString("mimeType", "");
                        if (!mime.startsWith("audio/")) continue;
                        String url = format.optString("url", "");
                        long bitrate = format.optLong("bitrate", 0);
                        if (!url.isEmpty() && bitrate > bestBitrate) {
                            bestBitrate = bitrate;
                            best = url;
                        }
                    }
                }
            }
            if (best == null) {
                throw new YouTubeException("resolver-changed",
                        "YouTube: keine abspielbaren Formate (resolver-changed)");
            }
            return best;
        } catch (YouTubeException e) {
            throw e;
        } catch (Exception e) {
            throw new YouTubeException("network-offline",
                    "Resolve fehlgeschlagen: " + rootMessage(e));
        }
    }

    public static String extractVideoId(String input) {
        if (input == null) return null;
        String value = input.trim();
        if (value.matches("[\\w-]{11}")) return value;
        java.util.regex.Matcher m = java.util.regex.Pattern
                .compile("(?:v=|youtu\\.be/|/shorts/|/embed/)([\\w-]{11})")
                .matcher(value);
        return m.find() ? m.group(1) : null;
    }

    // ------------------------------------------------------------------ http

    private static JSONObject post(String url, JSONObject body) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
        conn.setRequestMethod("POST");
        conn.setConnectTimeout(10000);
        conn.setReadTimeout(20000);
        conn.setDoOutput(true);
        conn.setRequestProperty("Content-Type", "application/json");
        conn.setRequestProperty("User-Agent", UA);
        byte[] payload = body.toString().getBytes(StandardCharsets.UTF_8);
        try (java.io.OutputStream out = conn.getOutputStream()) {
            out.write(payload);
        }
        int code = conn.getResponseCode();
        if (code < 200 || code >= 300) {
            throw new Exception("HTTP " + code + " (http-error)");
        }
        try (InputStream in = conn.getInputStream()) {
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            byte[] chunk = new byte[16 * 1024];
            int n;
            while ((n = in.read(chunk)) > 0) buf.write(chunk, 0, n);
            return new JSONObject(new String(buf.toByteArray(), StandardCharsets.UTF_8));
        } finally {
            conn.disconnect();
        }
    }

    private static long parseDuration(String text) {
        if (text == null || text.isEmpty()) return 0;
        long total = 0;
        java.util.regex.Matcher m = java.util.regex.Pattern
                .compile("(?:(\\d+):)?(\\d+):(\\d+)").matcher(text);
        if (m.matches()) {
            if (m.group(1) != null) total += Long.parseLong(m.group(1)) * 3600;
            total += Long.parseLong(m.group(2)) * 60;
            total += Long.parseLong(m.group(3));
        }
        return total;
    }

    private static String rootMessage(Throwable t) {
        String msg = t.getMessage() == null ? t.getClass().getSimpleName() : t.getMessage();
        if (msg.contains("Unable to resolve") || msg.contains("UnknownHost")) return "Netzwerk nicht erreichbar (network-offline)";
        if (msg.toLowerCase().contains("timeout")) return "Zeitüberschreitung (timeout)";
        return msg;
    }
}
