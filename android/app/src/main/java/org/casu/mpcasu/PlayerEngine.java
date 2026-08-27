// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// SPDX-FileCopyrightText: 2026 Lino Casu
package org.casu.mpcasu;

import android.content.Context;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.media.PlaybackParams;
import android.media.audiofx.Visualizer;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.SurfaceHolder;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/** Single playback engine: MediaPlayer lifecycle + queue + modes + A-B +
 *  rate + audio focus + persistence. One instance, owned by PlayerService.
 *  All public methods are main-thread; MediaPlayer events arrive on our
 *  looper. Every open is prepareAsync — the UI never blocks. */
public final class PlayerEngine implements MediaPlayer.OnPreparedListener,
        MediaPlayer.OnCompletionListener, MediaPlayer.OnErrorListener,
        MediaPlayer.OnInfoListener, MediaPlayer.OnSeekCompleteListener,
        AudioManager.OnAudioFocusChangeListener {

    public interface Listener {
        void onStateChanged(boolean playing);
        void onItemChanged(MediaItem item, int index);
        void onPosition(long positionMs, long durationMs);
        void onEnded(int finishedIndex);          // EOF before auto-advance
        void onError(String userMessage);
        void onQueueChanged();
        void onTracksReady(MediaPlayer player);   // for track menus/subtitles
        void onVideoSizeChanged(int width, int height);  // for aspect-ratio
    }

    private static final String TAG = "MPCASU-Engine";
    private static final float[] RATES = {0.5f, 0.75f, 1.0f, 1.25f, 1.5f, 2.0f};

    private final Context context;
    private final QueueStore store;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final Random random = new Random();
    private final List<Listener> listeners = new ArrayList<>();

    private MediaPlayer player;
    private android.view.Surface surface;   // kept across player recreation
    private final List<MediaItem> items = new ArrayList<>();
    private int index = -1;
    private boolean prepared;
    private boolean playing;
    private boolean pausedByUser;
    private float rate = 1.0f;
    private String repeat = "off";   // off|all|one
    private boolean shuffle;
    private long pendingSeekMs = -1;
    private float pendingRate = 1.0f;
    private long abStartMs = -1;
    private long abEndMs = -1;
    private String lastError;
    private AudioManager audio;
    private AudioFocusRequest focusRequest;
    private Visualizer visualizer;
    private boolean hasFocus;
    private long openSeq = 0;

    private final Runnable abTicker = new Runnable() {
        @Override public void run() {
            if (abEndMs > 0 && playing && player != null) {
                try {
                    long pos = player.getCurrentPosition();
                    if (pos >= abEndMs) {
                        player.seekTo((int) (abStartMs < 0 ? 0L : abStartMs));
                    }
                } catch (Exception ignored) {}
            }
            main.postDelayed(this, 250);
        }
    };

    public PlayerEngine(Context context) {
        this.context = context.getApplicationContext();
        this.store = new QueueStore(this.context);
        audio = (AudioManager) this.context.getSystemService(Context.AUDIO_SERVICE);
        restore();
        main.postDelayed(abTicker, 250);
    }

    // ------------------------------------------------------------------ listeners

    public void addListener(Listener l) {
        if (l != null && !listeners.contains(l)) listeners.add(l);
    }

    public void removeListener(Listener l) {
        listeners.remove(l);
    }

    private void fireStateChanged() {
        for (Listener l : new ArrayList<>(listeners)) l.onStateChanged(playing);
    }

    private void fireItemChanged() {
        MediaItem item = current();
        for (Listener l : new ArrayList<>(listeners)) l.onItemChanged(item, index);
    }

    private void fireQueueChanged() {
        for (Listener l : new ArrayList<>(listeners)) l.onQueueChanged();
    }

    private void fireError(String message) {
        lastError = message;
        for (Listener l : new ArrayList<>(listeners)) l.onError(message);
    }

    private void fireVideoSizeChanged(int width, int height) {
        for (Listener l : new ArrayList<>(listeners)) l.onVideoSizeChanged(width, height);
    }

    // ------------------------------------------------------------------ state

    public MediaItem current() {
        if (index >= 0 && index < items.size()) return items.get(index);
        return null;
    }

    public List<MediaItem> items() { return items; }
    public int index() { return index; }
    public boolean isPlaying() { return playing; }
    public boolean isPausedByUser() { return pausedByUser; }
    public String repeat() { return repeat; }
    public boolean shuffle() { return shuffle; }
    public float rate() { return rate; }
    public String lastError() { return lastError; }

    public long position() {
        try {
            return player != null ? Math.max(0, player.getCurrentPosition()) : 0;
        } catch (Exception e) { return 0; }
    }

    public long duration() {
        try {
            return player != null && prepared ? Math.max(0, player.getDuration()) : 0;
        } catch (Exception e) { return 0; }
    }

    /** Poll tick (200 ms) from the service: pushes position to listeners. */
    public void pollPosition() {
        if (player == null || !prepared) return;
        long pos = position();
        long dur = duration();
        for (Listener l : new ArrayList<>(listeners)) l.onPosition(pos, dur);
    }

    public Visualizer attachVisualizer(int rateHz, Visualizer.OnDataCaptureListener l) {
        try {
            releaseVisualizer();
            int sessionId = player != null ? player.getAudioSessionId() : 0;
            if (sessionId == 0) return null;
            visualizer = new Visualizer(sessionId);
            visualizer.setDataCaptureListener(l, rateHz, true, false);
            visualizer.setEnabled(true);
            return visualizer;
        } catch (Exception e) {
            Log.i(TAG, "visualizer unavailable: " + e.getMessage());
            return null;
        }
    }

    public void releaseVisualizer() {
        if (visualizer != null) {
            try { visualizer.setEnabled(false); visualizer.release(); } catch (Exception ignored) {}
            visualizer = null;
        }
    }

    // ------------------------------------------------------------------ queue ops

    public int add(MediaItem item) {
        if (item == null || item.url == null) return -1;
        items.add(item);
        persist();
        fireQueueChanged();
        return items.size() - 1;
    }

    public void addAll(List<MediaItem> list) {
        if (list == null) return;
        for (MediaItem item : list) {
            if (item != null && item.url != null) items.add(item);
        }
        persist();
        fireQueueChanged();
    }

    public void removeAt(int position) {
        if (position < 0 || position >= items.size()) return;
        items.remove(position);
        if (position < index) {
            index--;
        } else if (position == index) {
            // removing the playing item: stop playback, keep position marker
            stopInternal(false);
            if (index >= items.size()) index = items.size() - 1;
        }
        persist();
        fireQueueChanged();
        fireItemChanged();
    }

    public void removeAll(List<Integer> positions) {
        if (positions == null || positions.isEmpty()) return;
        List<Integer> sorted = new ArrayList<>(positions);
        java.util.Collections.sort(sorted, java.util.Collections.reverseOrder());
        for (int p : sorted) removeAt(p);
    }

    public void move(int from, int to) {
        if (from < 0 || from >= items.size() || to < 0 || to >= items.size() || from == to) return;
        MediaItem item = items.remove(from);
        items.add(to, item);
        if (index == from) index = to;
        else if (from < index && to >= index) index--;
        else if (from > index && to <= index) index++;
        persist();
        fireQueueChanged();
    }

    public void clear() {
        stopInternal(false);
        items.clear();
        index = -1;
        persist();
        fireQueueChanged();
        fireItemChanged();
    }

    public void rename(int position, String title) {
        if (position < 0 || position >= items.size() || title == null || title.trim().isEmpty()) return;
        items.get(position).title = title.trim();
        persist();
        fireQueueChanged();
        if (position == index) fireItemChanged();
    }

    public void setShuffle(boolean on) {
        shuffle = on;
        persist();
        fireQueueChanged();
    }

    public void cycleRepeat() {
        repeat = "off".equals(repeat) ? "all" : ("all".equals(repeat) ? "one" : "off");
        persist();
        fireQueueChanged();
    }

    // ------------------------------------------------------------------ transport

    /** Play a queue index; resolves CASU containers transparently. */
    public void playIndex(int position) {
        playIndex(position, 0);
    }

    public void playIndex(int position, long startMs) {
        if (position < 0 || position >= items.size()) return;
        index = position;
        pausedByUser = false;
        openCurrent(startMs);
    }

    public void openExternal(MediaItem item, boolean enqueue, long startMs) {
        if (item == null) return;
        int existing = indexOfUrl(item.url);
        if (existing >= 0) {
            playIndex(existing, startMs);
            return;
        }
        if (enqueue) {
            items.add(item);
            index = items.size() - 1;
            persist();
            fireQueueChanged();
        }
        pausedByUser = false;
        openCurrent(startMs);
    }

    public void playPause() {
        if (player == null || !prepared) {
            if (index < 0 && !items.isEmpty()) playIndex(0);
            else if (current() != null) openCurrent(0);
            return;
        }
        try {
            if (playing) {
                player.pause();
                setPlaying(false, true);
            } else {
                requestFocus();
                player.start();
                applyRate();
                setPlaying(true, false);
            }
            persist();
        } catch (Exception e) {
            fireError(userError(e));
        }
    }

    public void pause() {
        if (player != null && playing) {
            try {
                player.pause();
                setPlaying(false, true);
                persist();
            } catch (Exception ignored) {}
        }
    }

    public void stop() {
        stopInternal(true);
    }

    private void stopInternal(boolean persist) {
        releaseVisualizer();
        if (player != null) {
            try { player.stop(); } catch (Exception ignored) {}
            try { player.release(); } catch (Exception ignored) {}
            player = null;
        }
        prepared = false;
        if (playing) {
            playing = false;
            fireStateChanged();
        }
        if (persist) persist();
    }

    public void next() {
        nextInternal(false);
    }

    public void previous() {
        int count = items.size();
        if (count == 0) return;
        int target = index - 1;
        if (target < 0) {
            if ("all".equals(repeat)) target = count - 1;
            else return;
        }
        playIndex(target);
    }

    public void seekTo(long ms) {
        if (player != null && prepared) {
            try {
                player.seekTo((int) Math.max(0, ms));
                if (!playing && !pausedByUser) {
                    requestFocus();
                    player.start();
                    applyRate();
                    setPlaying(true, false);
                }
            } catch (Exception e) {
                fireError(userError(e));
            }
        } else {
            pendingSeekMs = ms;
        }
    }

    public void seekBy(long deltaMs) {
        seekTo(position() + deltaMs);
    }

    public void cycleRate() {
        int at = 0;
        for (int i = 0; i < RATES.length; i++) if (RATES[i] == rate) at = i;
        rate = RATES[(at + 1) % RATES.length];
        applyRate();
        persist();
    }

    private void applyRate() {
        if (player == null) return;
        try {
            PlaybackParams params = new PlaybackParams();
            params.setSpeed(rate);
            player.setPlaybackParams(params);
        } catch (Exception e) {
            Log.i(TAG, "rate " + rate + " unavailable: " + e.getMessage());
        }
    }

    // ------------------------------------------------------------------ A-B loop

    /** Returns a short status text for the UI. */
    public String cycleAbLoop() {
        long pos = position();
        if (abStartMs < 0) {
            abStartMs = pos;
            abEndMs = -1;
            return "A gesetzt · " + fmt(pos);
        }
        if (abEndMs < 0) {
            if (pos <= abStartMs) return "B muss nach A liegen";
            abEndMs = pos;
            return "A–B aktiv · " + fmt(abStartMs) + " – " + fmt(abEndMs);
        }
        abStartMs = abEndMs = -1;
        return "A–B aus";
    }

    public boolean abActive() { return abStartMs >= 0; }

    private static String fmt(long ms) {
        long s = ms / 1000;
        return String.format("%d:%02d", s / 60, s % 60);
    }

    // ------------------------------------------------------------------ internals

    private int indexOfUrl(String url) {
        if (url == null) return -1;
        for (int i = 0; i < items.size(); i++) {
            if (url.equals(items.get(i).url)) return i;
        }
        return -1;
    }

    /** Resolve the playable URL (CASU containers → cache file) and open. */
    private void openCurrent(long startMs) {
        MediaItem item = current();
        if (item == null) return;
        releaseVisualizer();
        prepared = false;
        pendingSeekMs = startMs > 0 ? startMs : -1;
        pendingRate = rate;
        String source = item.url;
        String kind = item.kind == null ? "" : item.kind;
        if ("casu".equals(kind) || "mp5".equals(kind)
                || source.toLowerCase().endsWith(".casu")
                || source.toLowerCase().endsWith(".mp5")) {
            final String resolved = CasuBridge.extractToCache(source,
                    context.getCacheDir().getAbsolutePath());
            if (resolved == null || resolved.startsWith("ERROR")) {
                fireError("CASU-Container konnte nicht geöffnet werden"
                        + (resolved != null ? ": " + resolved.substring(5) : ""));
                return;
            }
            source = resolved;
        }
        openSource(source);
    }

    private void openSource(String source) {
        final long seq = ++openSeq;
        if (source.startsWith("http://") || source.startsWith("https://")) {
            // Radio / playlist streams: resolve async so Android's MediaPlayer
            // gets a direct playable URL (handles .pls/.m3u chains + UA header).
            StreamResolver.resolve(source, result -> main.post(() -> {
                if (seq != openSeq) return; // superseded by a newer open
                openResolved(result.url, result.headers);
            }));
            return;
        }
        openResolved(source, null);
    }

    private void openResolved(String source, java.util.Map<String, String> headers) {
        if (player != null) {
            try { player.reset(); } catch (Exception ignored) {}
        } else {
            player = createPlayer();
        }
        try {
            requestFocus();
            if (source.startsWith("content://")) {
                player.setDataSource(context, android.net.Uri.parse(source));
            } else if (source.startsWith("/")) {
                player.setDataSource(source);
            } else if (headers != null && !headers.isEmpty()) {
                player.setDataSource(context, android.net.Uri.parse(source), headers);
            } else {
                player.setDataSource(source);
            }
            player.setAudioAttributes(new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                    .build());
            player.prepareAsync();
            // UI gets the item immediately; prepared event follows async.
            fireItemChanged();
            setPlaying(false, false);
        } catch (Exception e) {
            Log.w(TAG, "open failed", e);
            fireError(userError(e));
        }
    }

    private MediaPlayer createPlayer() {
        MediaPlayer mp = new MediaPlayer();
        mp.setOnPreparedListener(this);
        mp.setOnCompletionListener(this);
        mp.setOnErrorListener(this);
        mp.setOnInfoListener(this);
        mp.setOnSeekCompleteListener(this);
        mp.setAudioAttributes(new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                .build());
        if (surface != null) {
            try { mp.setSurface(surface); } catch (Exception ignored) {}
        }
        return mp;
    }

    /** Attach a video surface. Kept referenced so EVERY future MediaPlayer
     *  instance (after stop/open cycles) is bound again — otherwise video
     *  plays blind (audio only) after the first teardown. */
    public void setSurface(android.view.Surface surface) {
        this.surface = surface;
        if (player != null) {
            try { player.setSurface(surface); } catch (Exception ignored) {}
        }
    }

    public int videoWidth() {
        try { return player != null && prepared ? player.getVideoWidth() : 0; }
        catch (Exception e) { return 0; }
    }

    public int videoHeight() {
        try { return player != null && prepared ? player.getVideoHeight() : 0; }
        catch (Exception e) { return 0; }
    }

    public MediaPlayer player() { return player; }

    // ------------------------------------------------------------------ events

    @Override public void onPrepared(MediaPlayer mp) {
        prepared = true;
        // BUG 5 FIX: Re-apply surface after prepare — if the TextureView
        // wasn't laid out when createPlayer() ran, the surface was null then.
        // This is the most common cause of "video plays but no picture".
        if (surface != null) {
            try { mp.setSurface(surface); } catch (Exception ignored) {}
        }
        if (pendingRate > 0 && pendingRate != 1.0f) applyRate();
        long dur = duration();
        if (pendingSeekMs > 0 && pendingSeekMs < Math.max(dur - 500, pendingSeekMs + 500)) {
            try { mp.seekTo((int) pendingSeekMs); } catch (Exception ignored) {}
        }
        pendingSeekMs = -1;
        requestFocus();
        try {
            mp.start();
            applyRate();
            setPlaying(true, false);
        } catch (Exception e) {
            fireError(userError(e));
        }
        for (Listener l : new ArrayList<>(listeners)) l.onTracksReady(mp);
        // Fire video size if the player already knows it (some codecs
        // report size on prepare, others on first frame — onInfo handles
        // the latter case).
        int vw = videoWidth(), vh = videoHeight();
        if (vw > 0 && vh > 0) fireVideoSizeChanged(vw, vh);
    }

    @Override public void onCompletion(MediaPlayer mp) {
        if ("one".equals(repeat) && current() != null) {
            try { mp.seekTo(0); mp.start(); setPlaying(true, false); } catch (Exception ignored) {}
            return;
        }
        for (Listener l : new ArrayList<>(listeners)) l.onEnded(index);
        nextInternal(true);
    }

    @Override public boolean onError(MediaPlayer mp, int what, int extra) {
        Log.w(TAG, "player error what=" + what + " extra=" + extra);
        setPlaying(false, false);
        String message;
        if (what == MediaPlayer.MEDIA_ERROR_UNSUPPORTED || extra == -1010) {
            message = "Format wird von diesem Gerät nicht unterstützt (codec-unsupported)";
        } else if (what == MediaPlayer.MEDIA_ERROR_TIMED_OUT) {
            message = "Zeitüberschreitung der Quelle (timeout)";
        } else if (what == MediaPlayer.MEDIA_ERROR_SERVER_DIED) {
            message = "Medien-Dienst wurde beendet (playback-failed)";
        } else {
            message = "Wiedergabefehler der Quelle (http-error/unsupported)";
        }
        fireError(message);
        return true; // handled: no system dialogs
    }

    @Override public boolean onInfo(MediaPlayer mp, int what, int extra) {
        // MEDIA_INFO_VIDEO_RENDERING_START = 3 — first frame rendered.
        // This is the authoritative signal that video is actually playing.
        if (what == 3) {
            // Ensure the surface is still attached (some devices detach
            // during prepare → start transition).
            if (surface != null) {
                try { mp.setSurface(surface); } catch (Exception ignored) {}
            }
            int vw = videoWidth(), vh = videoHeight();
            if (vw > 0 && vh > 0) fireVideoSizeChanged(vw, vh);
        }
        // MEDIA_INFO_VIDEO_SIZE_CHANGED = ?
        // Different devices use different codes; always check dimensions.
        int vw = videoWidth(), vh = videoHeight();
        if (vw > 0 && vh > 0) fireVideoSizeChanged(vw, vh);
        return false;
    }

    @Override public void onSeekComplete(MediaPlayer mp) {
        // no-op: position polling drives the UI
    }

    private void nextInternal(boolean automatic) {
        int count = items.size();
        if (count == 0) return;
        int target;
        if (shuffle && count > 1) {
            target = random.nextInt(count - 1);
            if (target >= index) target++;
        } else {
            target = index + 1;
        }
        if (target >= count) {
            if ("all".equals(repeat)) target = 0;
            else {
                setPlaying(false, false);
                persist();
                return;
            }
        }
        playIndex(target);
    }

    private void setPlaying(boolean now, boolean byUser) {
        playing = now;
        if (now) pausedByUser = false;
        else if (byUser) pausedByUser = true;
        fireStateChanged();
    }

    // ------------------------------------------------------------------ focus

    private void requestFocus() {
        if (hasFocus || audio == null) return;
        try {
            if (focusRequest == null) {
                focusRequest = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
                        .setAudioAttributes(new AudioAttributes.Builder()
                                .setUsage(AudioAttributes.USAGE_MEDIA)
                                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                                .build())
                        .setOnAudioFocusChangeListener(this)
                        .build();
            }
            hasFocus = audio.requestAudioFocus(focusRequest) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED;
        } catch (Exception ignored) {}
    }

    private void abandonFocus() {
        if (focusRequest != null && audio != null) {
            try { audio.abandonAudioFocusRequest(focusRequest); } catch (Exception ignored) {}
        }
        hasFocus = false;
    }

    @Override public void onAudioFocusChange(int change) {
        if (change == AudioManager.AUDIOFOCUS_LOSS) {
            pause();
        } else if (change == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT) {
            if (playing) pause();
        }
    }

    // ------------------------------------------------------------------ errors

    private static String userError(Exception e) {
        String msg = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
        if (msg.contains("Unable to resolve") || msg.contains("No address")) return "Netzwerk nicht erreichbar (network-offline)";
        if (msg.contains("timeout") || msg.contains("Timed out")) return "Zeitüberschreitung (timeout)";
        if (msg.contains("Permission") || msg.contains("denied")) return "Zugriff verweigert (permission-denied)";
        if (msg.contains("FileNotFound") || msg.contains("open failed")) return "Datei nicht gefunden (file-missing)";
        return "Quelle nicht abspielbar: " + msg;
    }

    // ------------------------------------------------------------------ persistence

    public void persist() {
        store.save(items, index, position(), playing, shuffle, repeat);
    }

    private void restore() {
        // Product decision (user): the QUEUE STARTS EMPTY on a fresh app
        // start. queue.json still persists during a session (crash safety,
        // position resume while the service lives) but the queue is never
        // silently repopulated from old sessions — library content belongs
        // in the LIBRARY tab, not preloaded into the queue.
    }

    public QueueStore.Saved savedState() {
        return store.load();
    }

    public void shutdown() {
        main.removeCallbacks(abTicker);
        releaseVisualizer();
        abandonFocus();
        persist();
        stopInternal(false);
    }
}
