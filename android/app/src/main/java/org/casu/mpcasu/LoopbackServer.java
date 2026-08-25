package org.casu.mpcasu;

import android.content.res.AssetManager;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URL;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Minimal same-origin loopback server: serves the pure-web touch UI from
 * APK assets plus a small /api surface, so the WebView can load the app
 * over http://127.0.0.1 (same origin → no CORS/mixed-content issues).
 *
 * /api/stream-proxy relays http(s) audio streams same-origin. Without it
 * the WebAudio analyser sees silence for cross-origin sources (CORS
 * tainting) and the visualizer stays flat; the proxy also enables Range
 * seeking on streams. Every connection is handled on its own thread — a
 * long-lived stream must never block asset/API requests.
 */
final class LoopbackServer implements Runnable {
    interface AssetSource {
        byte[] read(String path) throws IOException;
        boolean exists(String path);
    }

    private final AssetSource assets;
    private final int port;
    private volatile boolean running = true;
    private ServerSocket socket;
    private final ExecutorService pool = Executors.newCachedThreadPool();

    LoopbackServer(AssetSource assets, int port) {
        this.assets = assets;
        this.port = port;
    }

    int port() { return socket != null ? socket.getLocalPort() : port; }

    void start() throws IOException {
        socket = new ServerSocket(port, 64, java.net.InetAddress.getByName("127.0.0.1"));
        Thread t = new Thread(this, "casu-loopback");
        t.setDaemon(true);
        t.start();
    }

    void stop() {
        running = false;
        try { if (socket != null) socket.close(); } catch (IOException ignored) {}
        pool.shutdownNow();
    }

    @Override public void run() {
        while (running) {
            try {
                Socket client = socket.accept();
                pool.execute(() -> {
                    try {
                        serve(client);
                    } catch (IOException ignored) {
                    } finally {
                        try { client.close(); } catch (IOException ignored) {}
                    }
                });
            } catch (IOException e) {
                if (running) { /* transient */ }
            }
        }
    }

    private void serve(Socket client) throws IOException {
        client.setSoTimeout(10_000);
        InputStream in = client.getInputStream();
        String requestLine = readLine(in);
        if (requestLine == null) return;
        final boolean isPost = requestLine.startsWith("POST ");
        if (!requestLine.startsWith("GET ") && !isPost) return;
        final String path = requestLine.split(" ")[1];
        Map<String, String> headers = new HashMap<>();
        String line;
        while ((line = readLine(in)) != null && !line.isEmpty()) {
            int colon = line.indexOf(':');
            if (colon > 0)
                headers.put(line.substring(0, colon).trim().toLowerCase(),
                            line.substring(colon + 1).trim());
        }

        if ("/api/library.m3u".equals(path)) {
            byte[] m3u = LibraryIndex.libraryM3u(assets).getBytes(StandardCharsets.UTF_8);
            respond(client, 200, "audio/x-mpegurl", m3u);
            return;
        }
        if (path.startsWith("/api/yt-search?q=")) {
            String query = path.substring("/api/yt-search?q=".length());
            respond(client, 200, "application/json",
                    YouTubeSearch.json(query).getBytes(StandardCharsets.UTF_8));
            return;
        }
        if ("/api/ping".equals(path)) {
            respond(client, 200, "application/json",
                    "{\"ok\":true}".getBytes(StandardCharsets.UTF_8));
            return;
        }
        if (isPost) {
            servePost(client, path, headers, in);
            return;
        }
        if ("/api/library".equals(path)) {
            respond(client, 200, "application/json",
                    LibraryIndex.json().getBytes(StandardCharsets.UTF_8));
            return;
        }
        if (path.startsWith("/media?path=")) {
            LibraryIndex.serveMedia(client, path.substring("/media?path=".length()),
                                    headers.get("range"), this::respond);
            return;
        }
        if ("/api/version".equals(path)) {
            respond(client, 200, "application/json",
                    "{\"version\":\"5.0.0-android\"}".getBytes(StandardCharsets.UTF_8));
            return;
        }
        if (path.startsWith("/api/stream-proxy?url=")) {
            proxy(client, path.substring("/api/stream-proxy?url=".length()),
                  headers.get("range"));
            return;
        }
        String webPath = path.startsWith("/web/") ? path.substring(5) : path;
        if (webPath.startsWith("/")) webPath = webPath.substring(1);
        if (webPath.isEmpty()) webPath = "index.html";
        int query = webPath.indexOf('?');
        if (query >= 0) webPath = webPath.substring(0, query);
        // Candidate asset keys: the web/ subtree first, then the APK asset
        // root — index.html references ../assets/*.png, which resolves to
        // /web/assets/… and must map onto the root-level images (this is
        // why the brand logo never rendered on Android before).
        String[] candidates = {"web/" + webPath,
                               webPath.replaceFirst("^assets/", "")};
        for (String key : candidates) {
            if (assets.exists(key)) {
                byte[] body = assets.read(key);
                respond(client, 200, contentType(webPath), body);
                return;
            }
        }
        respond(client, 404, "text/plain", "not found".getBytes(StandardCharsets.UTF_8));
    }

    /** Relay a remote http(s) stream same-origin (Range-aware, chunked). */
    private void proxy(Socket client, String encodedUrl, String range)
            throws IOException {
        String target;
        try {
            target = URLDecoder.decode(encodedUrl, "UTF-8");
        } catch (IllegalArgumentException e) {
            target = encodedUrl;
        }
        if (!target.startsWith("http://") && !target.startsWith("https://")) {
            respond(client, 400, "text/plain", "unsupported scheme".getBytes(StandardCharsets.UTF_8));
            return;
        }
        HttpURLConnection conn;
        try {
            HttpURLConnection.setFollowRedirects(true);
            conn = (HttpURLConnection) new URL(target).openConnection();
            conn.setConnectTimeout(10_000);
            conn.setReadTimeout(15_000);
            conn.setRequestMethod("GET");
            if (range != null && !range.isEmpty())
                conn.setRequestProperty("Range", range);
            conn.setRequestProperty("User-Agent", "MPCASU/5.0.0 (Android)");
            conn.connect();
        } catch (IOException e) {
            respond(client, 502, "text/plain", "upstream unreachable".getBytes(StandardCharsets.UTF_8));
            return;
        }
        int status = conn.getResponseCode();
        OutputStream out = client.getOutputStream();
        StringBuilder head = new StringBuilder("HTTP/1.1 " + status + " \r\n");
        String type = conn.getContentType();
        if (type != null) head.append("Content-Type: ").append(type).append("\r\n");
        String len = conn.getHeaderField("Content-Length");
        if (len != null) head.append("Content-Length: ").append(len).append("\r\n");
        String cr = conn.getHeaderField("Content-Range");
        if (cr != null) head.append("Content-Range: ").append(cr).append("\r\n");
        String ar = conn.getHeaderField("Accept-Ranges");
        if (ar != null) head.append("Accept-Ranges: ").append(ar).append("\r\n");
        head.append("Access-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n");
        out.write(head.toString().getBytes(StandardCharsets.UTF_8));
        out.flush();
        try (InputStream upstream = conn.getInputStream()) {
            byte[] buf = new byte[64 * 1024];
            int n;
            while ((n = upstream.read(buf)) > 0) {
                out.write(buf, 0, n);
                out.flush();
            }
        } catch (IOException ignored) {
            // client walked away or upstream hiccupped: connection closes
        } finally {
            conn.disconnect();
        }
    }

    /** POST /api surface. The relay endpoints work fully offline; the
     * yt-dlp/ffmpeg-backed ones answer with a clean JSON error so the web
     * UI degrades the same way as a desktop web-casu without those tools
     * (YouTube falls back to the IFrame embed, search/transcode toast). */
    private void servePost(Socket client, String path, Map<String, String> headers,
                           InputStream in) throws IOException {
        int length = 0;
        try {
            length = Integer.parseInt(headers.getOrDefault("content-length", "0"));
        } catch (NumberFormatException ignored) {}
        String body = "";
        if (length > 0) {
            byte[] raw = new byte[length];
            in.readNBytes(raw, 0, length);
            body = new String(raw, StandardCharsets.UTF_8);
        }
        switch (path) {
            case "/api/catalog-url" -> {
                String url = jsonField(body, "url");
                if (url == null || !(url.startsWith("http://") || url.startsWith("https://"))) {
                    respond(client, 400, "application/json",
                            "{\"error\":\"HTTP or HTTPS URL required\"}".getBytes(StandardCharsets.UTF_8));
                    return;
                }
                proxyBuffered(client, url, null);
            }
            case "/api/search" -> {
                String query = jsonField(body, "query");
                if (query == null || query.isBlank()) {
                    respond(client, 400, "application/json",
                            "{\"results\":[],\"error\":\"query required\"}"
                                    .getBytes(StandardCharsets.UTF_8));
                    return;
                }
                String payload = YouTubeSearch.json(java.net.URLEncoder
                        .encode(query, StandardCharsets.UTF_8));
                respond(client, 200, "application/json",
                        payload.getBytes(StandardCharsets.UTF_8));
            }
            case "/api/resolve", "/api/spotify-metadata",
                 "/api/youtube-title", "/api/transcode-file", "/api/transcode-url" ->
                respond(client, 503, "application/json",
                        ("{\"error\":\"resolver/ffmpeg backend not available on Android - "
                                + "use direct URLs, playlists or CASU files\"}")
                                .getBytes(StandardCharsets.UTF_8));
            default ->
                respond(client, 404, "application/json",
                        "{\"error\":\"unknown endpoint\"}".getBytes(StandardCharsets.UTF_8));
        }
    }

    /** Fully buffered relay for catalog/EPG payloads (UI enforces 32 MiB). */
    private void proxyBuffered(Socket client, String target, String range)
            throws IOException {
        HttpURLConnection conn;
        try {
            conn = (HttpURLConnection) new URL(target).openConnection();
            conn.setConnectTimeout(10_000);
            conn.setReadTimeout(20_000);
            conn.setRequestProperty("User-Agent", "MPCASU/5.0.0 (Android)");
            conn.connect();
        } catch (IOException e) {
            respond(client, 502, "application/json",
                    "{\"error\":\"upstream unreachable\"}".getBytes(StandardCharsets.UTF_8));
            return;
        }
        int status = conn.getResponseCode();
        String type = conn.getContentType();
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        try (InputStream upstream = conn.getInputStream()) {
            byte[] chunk = new byte[64 * 1024];
            int n;
            while ((n = upstream.read(chunk)) > 0) buf.write(chunk, 0, n);
        } finally {
            conn.disconnect();
        }
        OutputStream out = client.getOutputStream();
        byte[] body = buf.toByteArray();
        out.write(("HTTP/1.1 " + status + " \r\n"
                   + "Content-Type: " + (type != null ? type : "application/octet-stream") + "\r\n"
                   + "Content-Length: " + body.length + "\r\n"
                   + "Access-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n")
                          .getBytes(StandardCharsets.UTF_8));
        out.write(body);
        out.flush();
    }

    private static String jsonField(String json, String key) {
        if (json == null) return null;
        int k = json.indexOf("\"" + key + "\":");
        if (k < 0) return null;
        int start = json.indexOf('"', k + key.length() + 2);
        if (start < 0) return null;
        int end = json.indexOf('"', start + 1);
        return end < 0 ? null : json.substring(start + 1, end);
    }

    private static String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        int prev = -1, c;
        while ((c = in.read()) != -1) {
            if (prev == '\r' && c == '\n') break;
            if (prev != -1) buf.write(prev);
            prev = c;
        }
        return prev == -1 && buf.size() == 0 ? null : buf.toString("UTF-8");
    }

    private void respond(Socket client, int status, String type, byte[] body)
            throws IOException {
        OutputStream out = client.getOutputStream();
        out.write(("HTTP/1.1 " + status + " OK\r\n"
                   + "Content-Type: " + type + "\r\n"
                   + "Content-Length: " + body.length + "\r\n"
                   + "Access-Control-Allow-Origin: *\r\n"
                   + "Connection: close\r\n\r\n").getBytes(StandardCharsets.UTF_8));
        out.write(body);
        out.flush();
    }

    private static String contentType(String path) {
        if (path.endsWith(".html")) return "text/html; charset=utf-8";
        if (path.endsWith(".js")) return "application/javascript";
        if (path.endsWith(".css")) return "text/css";
        if (path.endsWith(".m3u")) return "audio/x-mpegurl";
        if (path.endsWith(".png")) return "image/png";
        if (path.endsWith(".svg")) return "image/svg+xml";
        return "application/octet-stream";
    }
}
