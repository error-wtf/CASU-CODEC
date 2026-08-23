package org.casu.mpcasu;

import android.os.Handler;
import android.os.Looper;
import android.webkit.WebView;

/**
 * Bridge between the Android surface layer (home-screen widget,
 * MediaSession) and the pure-web player running inside the WebView.
 *
 * The web player is the single source of truth: transport commands are
 * forwarded as the same JS calls the touch UI uses (next(±1), #play
 * click), and state flows back by polling #title / #play textContent.
 */
public final class PlayerBridge {

    public interface StateListener {
        /** Called on the UI thread whenever polled player state changes. */
        void onState(String title, boolean playing);
    }

    private static final long POLL_MS = 1000;
    // #play shows "▶" while idle/paused and "❚❚" while playing.
    private static final String POLL_JS =
            "JSON.stringify({t:(document.querySelector('#title')||{textContent:''}).textContent||'',"
          + "p:((document.querySelector('#play')||{textContent:'\\u25B6'}).textContent||'')"
          + ".indexOf('\\u25B6')<0})";

    private static volatile WebView webView;
    private static volatile String title = "";
    private static volatile boolean playing = false;
    private static StateListener listener;
    private static final Handler handler = new Handler(Looper.getMainLooper());
    private static final Runnable pollLoop = new Runnable() {
        @Override public void run() {
            pollOnce();
            if (webView != null) handler.postDelayed(this, POLL_MS);
        }
    };

    private PlayerBridge() {}

    /** Attach the live player WebView and start polling its state. */
    public static void attach(WebView view, StateListener stateListener) {
        webView = view;
        listener = stateListener;
        handler.removeCallbacks(pollLoop);
        handler.post(pollLoop);
    }

    /** Detach on destroy: widget falls back to launching the app. */
    public static void detach() {
        webView = null;
        listener = null;
        handler.removeCallbacks(pollLoop);
        title = "";
        playing = false;
    }

    /**
     * Forward a widget action into the player. Returns false when no live
     * player exists (caller should launch MainActivity instead).
     */
    public static boolean dispatch(String widgetAction) {
        WebView view = webView;
        if (view == null) return false;
        if (McasuWidgetProvider.ACTION_PREV.equals(widgetAction)) {
            run("next(-1)");
        } else if (McasuWidgetProvider.ACTION_NEXT.equals(widgetAction)) {
            run("next(1)");
        } else if (McasuWidgetProvider.ACTION_PLAY.equals(widgetAction)) {
            run("document.querySelector('#play').click()");
        } else {
            return false;
        }
        // Feedback comes back through the next poll tick; nudge immediately
        // so the button glyph flips without visible lag.
        handler.post(PlayerBridge::pollOnce);
        return true;
    }

    public static String title() { return title; }
    public static boolean playing() { return playing; }

    /** Transport surface for MediaSession callbacks. */
    public static void play() { run("document.querySelector('#play').click()"); }
    public static void next() { run("next(1)"); }
    public static void previous() { run("next(-1)"); }

    private static void run(String js) {
        WebView view = webView;
        if (view != null) view.evaluateJavascript(js, null);
    }

    private static void pollOnce() {
        final WebView view = webView;
        if (view == null) return;
        view.evaluateJavascript(POLL_JS, value -> {
            if (value == null || value.length() < 4) return;
            // value is a JSON string literal like "{\"t\":\"...\",\"p\":false}"
            String body = value;
            if (body.startsWith("\"") && body.endsWith("\"")) {
                body = body.substring(1, body.length() - 1)
                        .replace("\\\"", "\"").replace("\\\\", "\\");
            }
            String newTitle = extractString(body, "t");
            boolean newPlaying = body.contains("\"p\":true");
            boolean changed = !newTitle.equals(title) || newPlaying != playing;
            title = newTitle;
            playing = newPlaying;
            if (changed && listener != null) {
                listener.onState(newTitle, newPlaying);
            }
        });
    }

    private static String extractString(String json, String key) {
        int k = json.indexOf("\"" + key + "\":");
        if (k < 0) return "";
        int start = json.indexOf('"', k + key.length() + 2);
        if (start < 0) return "";
        StringBuilder out = new StringBuilder();
        for (int i = start + 1; i < json.length(); i++) {
            char c = json.charAt(i);
            if (c == '\\') {
                i++;
                if (i < json.length()) out.append(json.charAt(i));
            } else if (c == '"') {
                break;
            } else {
                out.append(c);
            }
        }
        return out.toString();
    }
}
