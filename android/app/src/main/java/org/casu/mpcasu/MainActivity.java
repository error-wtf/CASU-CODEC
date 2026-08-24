package org.casu.mpcasu;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
import android.content.res.AssetManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
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
 *
 * The activity also owns the Android surface layer: a MediaSession and the
 * home-screen widget are kept in sync with the web player through
 * {@link PlayerBridge} (JS forwarding out, polled state back).
 */
public class MainActivity extends Activity {
    private static final int FILE_REQUEST = 7;
    private LoopbackServer server;
    private McasuMediaSession mediaSession;
    private ValueCallback<Uri[]> fileCallback;
    private WebView webView;

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

        webView = new WebView(this);
        setContentView(webView);
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(true);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        webView.setWebViewClient(new WebViewClient());
        // Provider web players (Spotify/Tidal/…) need cookies + login
        // sessions; BACK walks the WebView history back to MPCASU first.
        android.webkit.CookieManager cookies = android.webkit.CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(webView, true);
        // Without a WebChromeClient the web UI's "Choose files" input is a
        // dead end on Android: onShowFileChooser is what opens the system
        // document picker (Linux desktops open it natively).
        webView.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(
                    WebView view, ValueCallback<Uri[]> callback,
                    FileChooserParams params) {
                fileCallback = callback;
                try {
                    startActivityForResult(params.createIntent(), FILE_REQUEST);
                } catch (android.content.ActivityNotFoundException e) {
                    fileCallback = null;
                    return false;
                }
                return true;
            }
        });
        webView.loadUrl("http://127.0.0.1:" + server.port() + "/web/index.html");

        // Warm up the native core so the .so + verification are ready.
        // The probe path is intentionally unreadable; detectKind reports
        // that as an "ERROR: …" string (never throws across JNI).
        try {
            CasuCore.detectKind("/nonexistent");
        } catch (Throwable ignored) {
            // A missing/wrong native core must not take the app down:
            // the web player degrades gracefully without casu_core.
        }

        // Surface layer: MediaSession for system transport controls
        // (lock screen, headsets, assistant) plus state polling that also
        // refreshes the home-screen widget.
        mediaSession = new McasuMediaSession(this);
        requestNotificationPermission();
        PlayerBridge.attach(webView, (title, playing) -> {
            if (mediaSession != null) mediaSession.pushState(title, playing);
            McasuWidgetProvider.pushState(getApplicationContext(), title, playing);
            // VLC-style notification-panel controls: the foreground service
            // appears with the first playback and mirrors title/glyph.
            if (playing) {
                PlaybackNotificationService.start(getApplicationContext());
            }
            PlaybackNotificationService.updateState(getApplicationContext(), title, playing);
        });
    }

    /** Android 13+ requires runtime grants for notifications + media. */
    private void requestNotificationPermission() {
        java.util.List<String> needed = new java.util.ArrayList<>();
        if (Build.VERSION.SDK_INT >= 33) {
            addIfDenied(needed, "android.permission.POST_NOTIFICATIONS");
            addIfDenied(needed, "android.permission.READ_MEDIA_AUDIO");
            addIfDenied(needed, "android.permission.READ_MEDIA_VIDEO");
        } else if (Build.VERSION.SDK_INT >= 23) {
            addIfDenied(needed, "android.permission.READ_EXTERNAL_STORAGE");
        }
        if (!needed.isEmpty()) {
            requestPermissions(needed.toArray(new String[0]), 1);
        }
    }

    private void addIfDenied(java.util.List<String> list, String permission) {
        if (checkSelfPermission(permission)
                != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            list.add(permission);
        }
    }

    @Override public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();  // provider browsing: BACK returns to MPCASU
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == FILE_REQUEST) {
            if (fileCallback != null) {
                fileCallback.onReceiveValue(
                        WebChromeClient.FileChooserParams.parseResult(resultCode, data));
                fileCallback = null;
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override protected void onDestroy() {
        PlaybackNotificationService.stop(getApplicationContext());
        PlayerBridge.detach();
        if (mediaSession != null) {
            mediaSession.release();
            mediaSession = null;
        }
        if (server != null) server.stop();
        super.onDestroy();
    }
}
