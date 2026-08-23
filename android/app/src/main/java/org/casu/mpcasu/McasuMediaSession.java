package org.casu.mpcasu;

import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.media.MediaMetadata;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;

/**
 * Android MediaSession (platform API, no androidx) mirroring the pure-web
 * player. Transport callbacks forward into the WebView through the same
 * JS surface the widget uses; PlaybackState/Metadata are refreshed from
 * PlayerBridge's poll loop.
 */
final class McasuMediaSession {

    static final long ACTIONS =
            PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE
            | PlaybackState.ACTION_PLAY_PAUSE | PlaybackState.ACTION_SKIP_TO_NEXT
            | PlaybackState.ACTION_SKIP_TO_PREVIOUS | PlaybackState.ACTION_STOP;

    private final MediaSession session;

    McasuMediaSession(Context context) {
        session = new MediaSession(context, "MPCASU");
        Intent open = new Intent(context, MainActivity.class);
        session.setSessionActivity(PendingIntent.getActivity(
                context, 0, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
        session.setFlags(MediaSession.FLAG_HANDLES_MEDIA_BUTTONS
                | MediaSession.FLAG_HANDLES_TRANSPORT_CONTROLS);
        session.setCallback(new MediaSession.Callback() {
            @Override public void onPlay() {
                if (!PlayerBridge.playing()) PlayerBridge.play();
            }
            @Override public void onPause() {
                if (PlayerBridge.playing()) PlayerBridge.play();
            }
            @Override public void onSkipToNext() { PlayerBridge.next(); }
            @Override public void onSkipToPrevious() { PlayerBridge.previous(); }
            @Override public void onStop() {
                if (PlayerBridge.playing()) PlayerBridge.play();
            }
        });
        session.setActive(true);
        pushState("", false);
    }

    /** Mirror polled player state into PlaybackState + Metadata. */
    void pushState(String title, boolean playing) {
        int state = playing ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED;
        session.setPlaybackState(new PlaybackState.Builder()
                .setActions(ACTIONS)
                .setState(state, 0, 1.0f)
                .build());
        session.setMetadata(new MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE,
                        title == null || title.isEmpty()
                                ? "MPCASU" : title)
                .build());
    }

    void release() {
        try {
            session.release();
        } catch (Exception ignored) {
        }
    }
}
