package org.casu.mpcasu;

import android.os.Handler;
import android.os.Looper;
import android.webkit.WebView;
import org.json.JSONObject;

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
        void onState(String title, boolean playing, double position, double duration);
    }

    private static final long POLL_MS = 1000;
    private static final String POLL_JS =
            "JSON.stringify(window.MPCASUControls ? MPCASUControls.state() : "
          + "{title:'',playing:false,position:0,duration:0})";

    private static volatile WebView webView;
    private static volatile String title = "";
    private static volatile boolean playing = false;
    private static volatile double position = 0;
    private static volatile double duration = 0;
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
        position = 0;
        duration = 0;
    }

    /**
     * Forward a widget action into the player. Returns false when no live
     * player exists (caller should launch MainActivity instead).
     */
    public static boolean dispatch(String widgetAction) {
        WebView view = webView;
        if (view == null) return false;
        if (McasuWidgetProvider.ACTION_PREV.equals(widgetAction)) {
            previous();
        } else if (McasuWidgetProvider.ACTION_NEXT.equals(widgetAction)) {
            next();
        } else if (McasuWidgetProvider.ACTION_PLAY.equals(widgetAction)) {
            toggle();
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
    public static double position() { return position; }
    public static double duration() { return duration; }

    /** Transport surface for MediaSession callbacks. */
    public static void play() { run("MPCASUControls.play()"); }
    public static void pause() { run("MPCASUControls.pause()"); }
    public static void toggle() { if (playing) pause(); else play(); }
    public static void stop() { run("MPCASUControls.stop()"); }
    public static void seekTo(double seconds) {
        if (Double.isFinite(seconds) && seconds >= 0)
            run("MPCASUControls.seek(" + seconds + ")");
    }
    public static void next() { run("MPCASUControls.next()"); }
    public static void previous() { run("MPCASUControls.previous()"); }

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
            try {
                JSONObject state = new JSONObject(body);
                String newTitle = state.optString("title", "");
                boolean newPlaying = state.optBoolean("playing", false);
                double newPosition = finiteOrZero(state.optDouble("position", 0));
                double newDuration = finiteOrZero(state.optDouble("duration", 0));
                boolean changed = !newTitle.equals(title) || newPlaying != playing
                        || Math.abs(newPosition - position) >= 0.5
                        || Math.abs(newDuration - duration) >= 0.5;
                title = newTitle;
                playing = newPlaying;
                position = newPosition;
                duration = newDuration;
                if (changed && listener != null)
                    listener.onState(newTitle, newPlaying, newPosition, newDuration);
            } catch (Exception ignored) {
                // Page navigation/provider mode may temporarily have no player API.
            }
        });
    }

    private static double finiteOrZero(double value) {
        return Double.isFinite(value) && value >= 0 ? value : 0;
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
