package org.casu.mpcasu;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * YouTube search without API keys or yt-dlp: fetches the public search
 * results page and extracts the videoRenderer entries from ytInitialData.
 *
 * YouTube rotates the serving format per request (raw JSON object literal
 * vs. hex-escaped JS string, JS-only escapes like \' inside). Both forms
 * are handled with a full JS-string unescape; when YouTube rotates again
 * the endpoint answers with a JSON error and the UI toasts it — the same
 * degradation a desktop web-casu shows without yt-dlp installed.
 */
final class YouTubeSearch {

    private static final Pattern RAW_FORM = Pattern.compile(
            "ytInitialData\\s*=\\s*(\\{.+?\\});</script>", Pattern.DOTALL);
    private static final Pattern STRING_FORM = Pattern.compile(
            "ytInitialData\\s*=\\s*'(.+?)';</script>", Pattern.DOTALL);

    private YouTubeSearch() {}

    static String json(String encodedQuery) {
        String query;
        try {
            query = URLDecoder.decode(encodedQuery, "UTF-8");
        } catch (Exception e) {
            query = encodedQuery;
        }
        List<String[]> results = new ArrayList<>();
        String error = null;
        try {
            String page = fetch("https://www.youtube.com/results?search_query="
                    + java.net.URLEncoder.encode(query, "UTF-8"));
            JSONObject data = null;
            Matcher raw = RAW_FORM.matcher(page);
            if (raw.find()) {
                try {
                    data = new JSONObject(jsUnescape(
                            raw.group(1).getBytes(StandardCharsets.US_ASCII)));
                } catch (Exception ignored) {
                    data = null;
                }
            }
            if (data == null) {
                Matcher str = STRING_FORM.matcher(page);
                if (!str.find()) throw new IOException("ytInitialData not found");
                data = new JSONObject(jsUnescape(
                        str.group(1).getBytes(StandardCharsets.US_ASCII)));
            }
            results = extract(data);
            if (results.isEmpty()) error = "no results parsed";
        } catch (Exception e) {
            error = e.getMessage() == null ? e.toString() : e.getMessage();
        }
        StringBuilder out = new StringBuilder("{\"results\":[");
        for (int i = 0; i < results.size(); i++) {
            String[] r = results.get(i);
            if (i > 0) out.append(',');
            out.append("{\"title\":\"").append(esc(r[0]))
               .append("\",\"uploader\":\"").append(esc(r[1]))
               .append("\",\"duration\":\"").append(esc(r[2]))
               .append("\",\"url\":\"https://www.youtube.com/watch?v=")
               .append(esc(r[3])).append("\"}");
        }
        out.append("],\"error\":");
        out.append(error == null ? "null" : "\"" + esc(error) + "\"");
        out.append('}');
        return out.toString();
    }

    private static String fetch(String target) throws IOException {
        HttpURLConnection conn = (HttpURLConnection) new URL(target).openConnection();
        conn.setConnectTimeout(10_000);
        conn.setReadTimeout(15_000);
        conn.setRequestProperty("User-Agent",
                "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
                + "(KHTML, like Gecko) Chrome/120 Mobile Safari/537.36");
        conn.setRequestProperty("Accept-Language", "en-US,en;q=0.9");
        conn.setRequestProperty("Cookie", "SOCS=CAI; CONSENT=YES+cb");
        int status = conn.getResponseCode();
        if (status != 200) throw new IOException("HTTP " + status);
        StringBuilder page = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                conn.getInputStream(), StandardCharsets.UTF_8))) {
            char[] buf = new char[16 * 1024];
            int n;
            while ((n = reader.read(buf)) > 0) page.append(buf, 0, n);
        } finally {
            conn.disconnect();
        }
        return page.toString();
    }

    /**
     * JS string unescape at byte level: \\xHH → byte (UTF-8 safe), then the
     * standard JS escapes (quote, apostrophe, backslash, n, t, r, b, f, slash, u-hex).
     */
    private static String jsUnescape(byte[] raw) throws java.io.IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream(raw.length);
        int i = 0, n = raw.length;
        while (i < n) {
            int b = raw[i] & 0xFF;
            if (b == 0x5C && i + 1 < n) {  // backslash
                int c = raw[i + 1] & 0xFF;
                if (c == 0x78 && i + 3 < n) {  // x-escape to byte
                    try {
                        out.write(Integer.parseInt(new String(raw, i + 2, 2,
                                StandardCharsets.US_ASCII), 16));
                        i += 4;
                        continue;
                    } catch (NumberFormatException ignored) {
                        // fall through: literal
                    }
                }
                if (c == 0x75 && i + 5 < n) {  // u-escape to UTF-8 char
                    try {
                        String hex = new String(raw, i + 2, 4,
                                StandardCharsets.US_ASCII);
                        out.write(new String(new int[]{Integer.parseInt(hex, 16)},
                                0, 1).getBytes(StandardCharsets.UTF_8));
                        i += 6;
                        continue;
                    } catch (NumberFormatException ignored) {
                        // fall through: literal
                    }
                }
                int mapped = switch (c) {
                    case '"' -> '"';
                    case '\'' -> '\'';
                    case '\\' -> '\\';
                    case 'n' -> '\n';
                    case 't' -> '\t';
                    case 'r' -> '\r';
                    case 'b' -> '\b';
                    case 'f' -> '\f';
                    case '/' -> '/';
                    default -> -1;
                };
                if (mapped >= 0) {
                    out.write(mapped);
                    i += 2;
                    continue;
                }
            }
            out.write(raw[i]);
            i += 1;
        }
        return out.toString("UTF-8");
    }

    /** Walk the ytInitialData tree collecting videoRenderer entries. */
    private static List<String[]> extract(Object node) {
        List<String[]> out = new ArrayList<>();
        collect(node, out, 0);
        return out;
    }

    private static void collect(Object node, List<String[]> out, int depth) {
        if (depth > 24 || out.size() >= 20) return;
        if (node instanceof JSONObject) {
            JSONObject obj = (JSONObject) node;
            JSONObject video = obj.optJSONObject("videoRenderer");
            if (video != null) {
                String title = text(video.optJSONObject("title"));
                String author = text(video.optJSONObject("ownerText"));
                if (author.isEmpty())
                    author = text(video.optJSONObject("longBylineText"));
                String length = text(video.optJSONObject("lengthText"));
                String id = video.optString("videoId", "");
                if (!id.isEmpty() && !title.isEmpty())
                    out.add(new String[]{title, author, length, id});
                return;
            }
            java.util.Iterator<String> keys = obj.keys();
            while (keys.hasNext()) {
                String key = keys.next();
                if (key.equals("trackingParams") || key.equals("serviceEndpoint"))
                    continue;
                collect(obj.opt(key), out, depth + 1);
            }
        } else if (node instanceof JSONArray) {
            JSONArray arr = (JSONArray) node;
            for (int i = 0; i < arr.length(); i++) collect(arr.opt(i), out, depth + 1);
        }
    }

    private static String text(JSONObject wrapper) {
        if (wrapper == null) return "";
        JSONArray runs = wrapper.optJSONArray("runs");
        if (runs != null) {
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < runs.length(); i++)
                sb.append(runs.optJSONObject(i) == null ? ""
                        : runs.optJSONObject(i).optString("text", ""));
            return sb.toString();
        }
        JSONObject simple = wrapper.optJSONObject("simpleText");
        return simple != null ? simple.optString("text", "") : "";
    }

    private static String esc(String s) {
        return s == null ? "" : s.replace("\\", "\\\\")
                .replace("\"", "\\\"").replace("\n", " ").replace("\r", " ");
    }
}
