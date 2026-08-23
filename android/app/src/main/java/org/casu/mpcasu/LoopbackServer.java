package org.casu.mpcasu;

import android.content.res.AssetManager;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

/**
 * Minimal same-origin loopback server: serves the pure-web touch UI from
 * APK assets plus /api/version, so the WebView can load the app over
 * http://127.0.0.1 (same origin → no CORS/mixed-content issues).
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
    }

    @Override public void run() {
        while (running) {
            try (Socket client = socket.accept()) {
                serve(client);
            } catch (IOException e) {
                if (running) { /* transient */ }
            }
        }
    }

    private void serve(Socket client) throws IOException {
        client.setSoTimeout(10_000);
        InputStream in = client.getInputStream();
        String requestLine = readLine(in);
        if (requestLine == null || !requestLine.startsWith("GET ")) return;
        final String path = requestLine.split(" ")[1];
        // Drain headers.
        while (!(readLine(in) == null || readLine(in).isEmpty())) {
            // loop until blank line; readLine returns "" for CRLF end
            break;
        }
        Map<String, String> headers = new HashMap<>();
        String line;
        while ((line = readLine(in)) != null && !line.isEmpty()) {
            int colon = line.indexOf(':');
            if (colon > 0)
                headers.put(line.substring(0, colon).trim().toLowerCase(),
                            line.substring(colon + 1).trim());
        }

        if ("/api/version".equals(path)) {
            respond(client, 200, "application/json",
                    "{\"version\":\"5.0.0-android\"}".getBytes(StandardCharsets.UTF_8));
            return;
        }
        String webPath = path.startsWith("/web/") ? path.substring(5) : path;
        if (webPath.startsWith("/")) webPath = webPath.substring(1);
        if (webPath.isEmpty()) webPath = "index.html";
        int query = webPath.indexOf('?');
        if (query >= 0) webPath = webPath.substring(0, query);
        if (!assets.exists("web/" + webPath)) {
            respond(client, 404, "text/plain", "not found".getBytes(StandardCharsets.UTF_8));
            return;
        }
        byte[] body = assets.read("web/" + webPath);
        respond(client, 200, contentType(webPath), body);
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
