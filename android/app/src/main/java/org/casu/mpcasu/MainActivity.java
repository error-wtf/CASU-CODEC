package org.casu.mpcasu;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.res.AssetManager;
import android.os.Bundle;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

/**
 * MPCASU Android: the pure-web touch UI (same app as the desktop web
 * player) served same-origin from APK assets over a loopback server, with
 * the byte-parity casu_core available via JNI for container verification.
 */
public class MainActivity extends Activity {
    private LoopbackServer server;

    @SuppressLint("SetJavaScriptEnabled")
    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        final AssetManager assets = getAssets();
        server = new LoopbackServer(new LoopbackServer.AssetSource() {
            @Override public boolean exists(String path) {
                try (InputStream is = assets.open(path)) {
                    return true;
                } catch (IOException e) {
                    return false;
                }
            }
            @Override public byte[] read(String path) throws IOException {
                InputStream is = assets.open(path);
                ByteArrayOutputStream buf = new ByteArrayOutputStream();
                byte[] chunk = new byte[64 * 1024];
                int n;
                while ((n = is.read(chunk)) > 0) buf.write(chunk, 0, n);
                is.close();
                return buf.toByteArray();
            }
        }, 0);
        try {
            server.start();
        } catch (IOException e) {
            throw new RuntimeException("loopback server failed", e);
        }

        WebView webView = new WebView(this);
        setContentView(webView);
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(true);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        webView.setWebViewClient(new WebViewClient());
        webView.loadUrl("http://127.0.0.1:" + server.port() + "/web/index.html");

        // Warm up the native core so the .so + verification are ready.
        CasuCore.detectKind("/nonexistent");
    }

    @Override protected void onDestroy() {
        if (server != null) server.stop();
        super.onDestroy();
    }
}
