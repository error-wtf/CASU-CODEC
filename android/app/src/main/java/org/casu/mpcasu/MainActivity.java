// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// SPDX-FileCopyrightText: 2026 Lino Casu
package org.casu.mpcasu;

import android.Manifest;
import org.json.JSONObject;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.media.MediaMetadataRetriever;
import android.media.MediaPlayer;
import android.media.audiofx.Visualizer;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.text.Editable;
import android.text.TextWatcher;
import android.util.Log;
import android.view.Gravity;
import android.view.Surface;
import android.view.TextureView;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/** MPCASU Android — native rewrite of the full Linux Qt player.
 *  Symbol-driven UI, 5 bottom tabs, everything touch-first. */
public class MainActivity extends Activity implements PlayerEngine.Listener {

    // palette (MPCASU red/black)
    private static final int BG = Color.parseColor("#0b0d10");
    private static final int SURFACE = Color.parseColor("#12151a");
    private static final int ACCENT = Color.parseColor("#ff1e2d");
    private static final int TEXT = Color.parseColor("#f2f4f7");
    private static final int MUTED = Color.parseColor("#9aa3ad");
    private static final int BORDER = Color.parseColor("#262b31");

    private static final int TAB_PLAY = 0, TAB_QUEUE = 1, TAB_LIBRARY = 2,
            TAB_WEB = 3, TAB_SETTINGS = 4;

    private static final String[] PROVIDER_NAMES = {"SPOTIFY", "HEARTHIS", "TIDAL", "NETFLIX", "BROWSE"};
    private static final String[] PROVIDER_URLS = {
            "https://open.spotify.com/", "https://hearthis.at/", "https://tidal.com/",
            "https://www.netflix.com/", "https://www.google.com/"};
    private static final int[] PROVIDER_COLORS = {
            Color.parseColor("#1DB954"),  // Spotify green
            Color.parseColor("#FF6B35"),  // HearThis orange
            Color.parseColor("#00FFFF"),  // Tidal cyan
            Color.parseColor("#E50914"),  // Netflix red
            Color.parseColor("#4285F4")}; // Browse blue

    private FrameLayout root;
    private FrameLayout content;
    private LinearLayout bottomNav;
    private final TextView[] navTabs = new TextView[5];
    private int activeTab = TAB_PLAY;

    // now playing
    private FrameLayout stage;
    private TextureView videoView;
    private WaveView waveView;
    private ImageView coverView;
    private TextView titleView;
    private TextView artistView;
    private TextView timeNow;
    private TextView timeTotal;
    private SeekBar seekBar;
    private Button playBtn;
    private Button shuffleBtn;
    private Button repeatBtn;
    private Button abBtn;
    private Button rateBtn;
    private Button recordBtn;
    private SeekBar volumeBar;
    private boolean draggingSeek;
    private boolean videoActive;

    // queue
    private ListView queueList;
    private QueueAdapter queueAdapter;
    private TextView queueSummary;
    private EditText queueSearch;

    // library
    private ListView libraryList;
    private LibraryAdapter libraryAdapter;
    private EditText librarySearch;
    private String libraryMode = "all";
    private List<Library.Track> libraryTracks = new ArrayList<>();

    // web
    private LinearLayout providerGrid;

    // settings
    private SeekBar settingsVolume;
    private android.widget.CheckBox resumeBox;
    private android.widget.CheckBox consentBox;
    private TextView aboutBox;

    // engine + helpers
    private PlayerEngine engine;
    private Library library;
    private SubtitleLoader subtitles;
    private android.os.Handler ui;
    private Settings settings;
    private boolean recording;
    private Thread recordThread;
    private File recordTarget;
    private Visualizer visualizer;

    // persisted settings (JSON)
    public static final class Settings {
        public int volume = 100;
        public float rate = 1.0f;
        public boolean visualizer = true;
        public boolean resume = true;
        public boolean consent = false;
        public String subtitlePath = null;

        public static Settings load(android.content.Context context) {
            Settings out = new Settings();
            try (java.io.FileInputStream in = new java.io.FileInputStream(
                    new java.io.File(context.getFilesDir(), "settings.json"))) {
                byte[] buf = new byte[in.available()];
                int read = in.read(buf);
                JSONObject o = new JSONObject(new String(buf, 0, Math.max(0, read)));
                out.volume = o.optInt("volume", 100);
                out.rate = (float) o.optDouble("rate", 1.0);
                out.visualizer = o.optBoolean("visualizer", true);
                out.resume = o.optBoolean("resume", true);
                out.consent = o.optBoolean("consent", false);
                out.subtitlePath = o.optString("subtitlePath", null);
                if (out.subtitlePath != null && out.subtitlePath.isEmpty()) out.subtitlePath = null;
            } catch (Exception ignored) {
            }
            return out;
        }

        public void save(android.content.Context context) {
            try {
                JSONObject o = new JSONObject();
                o.put("volume", volume);
                o.put("rate", rate);
                o.put("visualizer", visualizer);
                o.put("resume", resume);
                o.put("consent", consent);
                o.put("subtitlePath", subtitlePath == null ? "" : subtitlePath);
                try (java.io.FileOutputStream out = new java.io.FileOutputStream(
                        new java.io.File(context.getFilesDir(), "settings.json"))) {
                    out.write(o.toString().getBytes());
                }
            } catch (Exception ignored) {
            }
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        ui = new android.os.Handler(getMainLooper());
        settings = Settings.load(this);

        // BUG 4+7 FIX: On cold start, delete stale queue.json so the queue
        // starts EMPTY. Library content belongs in the LIBRARY tab, not
        // preloaded into the queue from a previous session.
        clearStaleQueue();

        library = new Library(this);

        ensureEngine();
        CasuBridge.warmUp();
        requestPermissions();

        buildUi();
        setContentView(root);

        handleIntent(getIntent());
    }

    private void clearStaleQueue() {
        try {
            java.io.File qf = new java.io.File(getFilesDir(), "queue.json");
            if (qf.exists()) qf.delete();
        } catch (Exception ignored) {}
    }

    private void ensureEngine() {
        // Cold start: boot the service; its onCreate creates THE engine.
        // The engine appears asynchronously on the main thread — intents and
        // resume logic wait for it (withEngine) instead of using a transient
        // player that the service would never see (the old split-engine bug).
        if (engine == null) engine = PlaybackService.engine();
        if (engine == null) {
            Intent start = new Intent(this, PlaybackService.class);
            if (Build.VERSION.SDK_INT >= 26) startForegroundService(start);
            else startService(start);
            ui.postDelayed(() -> ensureEngine(), 50);
            return;
        }
        engine.addListener(this);
        onEngineReady();
    }

    private Runnable pendingOpen;
    private boolean engineReady;

    /** Runs the action once the service-owned engine exists. */
    private void withEngine(Runnable action) {
        if (engine != null && engineReady) {
            action.run();
            return;
        }
        pendingOpen = action;
    }

    private void onEngineReady() {
        engineReady = true;
        if (pendingOpen != null) {
            Runnable action = pendingOpen;
            pendingOpen = null;
            action.run();
            return;
        }
        maybeResume();
    }

    /** Resume setting: continue the last item at its saved position. */
    private void maybeResume() {
        if (engine == null || !settings.resume || engine.isPlaying()
                || engine.isPausedByUser() || engine.index() < 0
                || engine.position() > 0) {
            return;
        }
        QueueStore.Saved saved = engine.savedState();
        if (saved != null && saved.positionMs > 0) {
            engine.playIndex(engine.index(), saved.positionMs);
        }
    }

    private void requestPermissions() {
        if (Build.VERSION.SDK_INT >= 33) {
            List<String> needed = new ArrayList<>();
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                    != PackageManager.PERMISSION_GRANTED) {
                needed.add(Manifest.permission.POST_NOTIFICATIONS);
            }
            if (checkSelfPermission(Manifest.permission.READ_MEDIA_AUDIO)
                    != PackageManager.PERMISSION_GRANTED) {
                needed.add(Manifest.permission.READ_MEDIA_AUDIO);
            }
            if (checkSelfPermission(Manifest.permission.READ_MEDIA_VIDEO)
                    != PackageManager.PERMISSION_GRANTED) {
                needed.add(Manifest.permission.READ_MEDIA_VIDEO);
            }
            if (!needed.isEmpty()) requestPermissions(needed.toArray(new String[0]), 1);
        } else if (Build.VERSION.SDK_INT >= 23) {
            if (checkSelfPermission(Manifest.permission.READ_EXTERNAL_STORAGE)
                    != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.READ_EXTERNAL_STORAGE}, 1);
            }
        }
    }

    // ================================================================== UI BUILD

    private void buildUi() {
        root = new FrameLayout(this);
        root.setBackgroundColor(BG);

        content = new FrameLayout(this);
        root.addView(content, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        content.addView(buildPlayView());
        content.addView(buildQueueView());
        content.addView(buildLibraryView());
        content.addView(buildWebView());
        content.addView(buildSettingsView());

        bottomNav = buildBottomNav();
        root.addView(bottomNav, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(64), Gravity.BOTTOM));

        showTab(TAB_PLAY);
    }

    private LinearLayout buildBottomNav() {
        LinearLayout nav = new LinearLayout(this);
        nav.setOrientation(LinearLayout.HORIZONTAL);
        nav.setBackgroundColor(Color.parseColor("#0e1014"));
        nav.setGravity(Gravity.CENTER);
        String[] symbols = {"▶", "☰", "▣", "∿", "⚙"};
        String[] labels = {"PLAY", "QUEUE", "LIBRARY", "WEB", "SETUP"};
        for (int i = 0; i < 5; i++) {
            LinearLayout tab = new LinearLayout(this);
            tab.setOrientation(LinearLayout.VERTICAL);
            tab.setGravity(Gravity.CENTER);
            TextView icon = new TextView(this);
            icon.setText(symbols[i]);
            icon.setTextSize(20);
            icon.setGravity(Gravity.CENTER);
            TextView label = new TextView(this);
            label.setText(labels[i]);
            label.setTextSize(9);
            label.setGravity(Gravity.CENTER);
            tab.addView(icon);
            tab.addView(label);
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                    0, ViewGroup.LayoutParams.MATCH_PARENT, 1f);
            tab.setLayoutParams(params);
            final int tabIndex = i;
            tab.setOnClickListener(v -> showTab(tabIndex));
            nav.addView(tab);
            navTabs[i] = icon;
        }
        return nav;
    }

    private void showTab(int tab) {
        activeTab = tab;
        for (int i = 0; i < content.getChildCount(); i++) {
            content.getChildAt(i).setVisibility(i == tab ? View.VISIBLE : View.GONE);
        }
        for (int i = 0; i < navTabs.length; i++) {
            navTabs[i].setTextColor(i == tab ? ACCENT : MUTED);
        }
        if (tab == TAB_QUEUE) refreshQueueUi();
        if (tab == TAB_LIBRARY) refreshLibrary();
    }

    // ---------------------------------------------------------------- PLAY view

    private View buildPlayView() {
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setPadding(dp(12), dp(12), dp(12), dp(76));

        stage = new FrameLayout(this);
        stage.setBackgroundColor(Color.parseColor("#080a0d"));
        LinearLayout.LayoutParams stageParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f);
        stageParams.bottomMargin = dp(10);
        page.addView(stage, stageParams);

        videoView = new TextureView(this);
        stage.addView(videoView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        videoView.setSurfaceTextureListener(new android.view.TextureView.SurfaceTextureListener() {
            @Override public void onSurfaceTextureAvailable(android.graphics.SurfaceTexture surface,
                                                            int width, int height) {
                if (engine != null) engine.setSurface(new Surface(surface));
            }
            @Override public void onSurfaceTextureSizeChanged(android.graphics.SurfaceTexture surface,
                                                              int width, int height) { }
            @Override public boolean onSurfaceTextureDestroyed(android.graphics.SurfaceTexture surface) {
                if (engine != null) engine.setSurface(null);
                return true;
            }
            @Override public void onSurfaceTextureUpdated(android.graphics.SurfaceTexture surface) { }
        });
        videoView.setVisibility(View.GONE);

        waveView = new WaveView(this);
        stage.addView(waveView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        coverView = new ImageView(this);
        coverView.setScaleType(ImageView.ScaleType.FIT_CENTER);
        coverView.setVisibility(View.GONE);
        stage.addView(coverView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        TextView badge = new TextView(this);
        badge.setText("MPCASU");
        badge.setTextColor(ACCENT);
        badge.setTextSize(11);
        badge.setTypeface(null, Typeface.BOLD);
        badge.setPadding(dp(10), dp(8), dp(10), dp(8));
        stage.addView(badge, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.TOP | Gravity.START));

        // title + artist
        LinearLayout meta = new LinearLayout(this);
        meta.setOrientation(LinearLayout.VERTICAL);
        titleView = new TextView(this);
        titleView.setTextColor(TEXT);
        titleView.setTextSize(17);
        titleView.setTypeface(null, Typeface.BOLD);
        titleView.setSingleLine(true);
        titleView.setEllipsize(android.text.TextUtils.TruncateAt.MARQUEE);
        titleView.setSelected(true);
        artistView = new TextView(this);
        artistView.setTextColor(MUTED);
        artistView.setTextSize(12);
        meta.addView(titleView);
        meta.addView(artistView);
        page.addView(meta);

        // seek row
        seekBar = new SeekBar(this);
        seekBar.getProgressDrawable().setColorFilter(ACCENT, android.graphics.PorterDuff.Mode.SRC_IN);
        seekBar.getThumb().setColorFilter(ACCENT, android.graphics.PorterDuff.Mode.SRC_IN);
        page.addView(seekBar, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(30)));
        seekBar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar bar, int value, boolean fromUser) {
                if (fromUser) updateTimeLabels(value, bar.getMax());
            }
            @Override public void onStartTrackingTouch(SeekBar bar) { draggingSeek = true; }
            @Override public void onStopTrackingTouch(SeekBar bar) {
                draggingSeek = false;
                if (engine != null && bar.getMax() > 0) {
                    engine.seekTo((long) ((double) value(bar) / bar.getMax() * engine.duration()));
                }
            }
            private int value(SeekBar bar) { return bar.getProgress(); }
        });

        LinearLayout times = new LinearLayout(this);
        times.setOrientation(LinearLayout.HORIZONTAL);
        timeNow = new TextView(this);
        timeNow.setTextColor(MUTED);
        timeNow.setTextSize(11);
        timeTotal = new TextView(this);
        timeTotal.setTextColor(MUTED);
        timeTotal.setTextSize(11);
        timeTotal.setGravity(Gravity.END);
        times.addView(timeNow, new LinearLayout.LayoutParams(0,
                ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        times.addView(timeTotal, new LinearLayout.LayoutParams(0,
                ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        page.addView(times);

        // transport row
        LinearLayout transport = new LinearLayout(this);
        transport.setOrientation(LinearLayout.HORIZONTAL);
        transport.setGravity(Gravity.CENTER);
        transport.setPadding(0, dp(6), 0, dp(2));
        Button prev = transportButton("⏮", 22, TEXT);
        prev.setOnClickListener(v -> { if (engine != null) engine.previous(); });
        playBtn = transportButton("▶", 30, ACCENT);
        playBtn.setBackground(circleBackground());
        playBtn.setOnClickListener(v -> { if (engine != null) engine.playPause(); });
        Button next = transportButton("⏭", 22, TEXT);
        next.setOnClickListener(v -> { if (engine != null) engine.next(); });
        LinearLayout.LayoutParams playParams = new LinearLayout.LayoutParams(dp(76), dp(76));
        playParams.setMargins(dp(18), 0, dp(18), 0);
        playBtn.setLayoutParams(playParams);
        transport.addView(prev);
        transport.addView(playBtn);
        transport.addView(next);
        page.addView(transport);

        // secondary row
        LinearLayout secondary = new LinearLayout(this);
        secondary.setOrientation(LinearLayout.HORIZONTAL);
        secondary.setGravity(Gravity.CENTER);
        shuffleBtn = smallButton("⤨");
        shuffleBtn.setOnClickListener(v -> {
            if (engine != null) {
                engine.setShuffle(!engine.shuffle());
                toast(engine.shuffle() ? "Shuffle an" : "Shuffle aus");
                refreshQueueUi();
            }
        });
        repeatBtn = smallButton("↻");
        repeatBtn.setOnClickListener(v -> {
            if (engine != null) {
                engine.cycleRepeat();
                toast("Repeat: " + engine.repeat());
                refreshQueueUi();
            }
        });
        abBtn = smallButton("A–B");
        abBtn.setOnClickListener(v -> {
            if (engine != null) toast(engine.cycleAbLoop());
        });
        Button snapshotBtn = smallButton("▧");
        snapshotBtn.setOnClickListener(v -> saveSnapshot());
        rateBtn = smallButton("1×");
        rateBtn.setOnClickListener(v -> {
            if (engine != null) {
                engine.cycleRate();
                rateBtn.setText(rateLabel(engine.rate()));
                toast("Rate " + rateLabel(engine.rate()));
            }
        });
        recordBtn = smallButton("●");
        recordBtn.setOnClickListener(v -> toggleRecording());
        secondary.addView(shuffleBtn);
        secondary.addView(repeatBtn);
        secondary.addView(abBtn);
        secondary.addView(snapshotBtn);
        secondary.addView(rateBtn);
        secondary.addView(recordBtn);
        page.addView(secondary);

        // volume row
        LinearLayout volumeRow = new LinearLayout(this);
        volumeRow.setOrientation(LinearLayout.HORIZONTAL);
        volumeRow.setGravity(Gravity.CENTER_VERTICAL);
        volumeRow.setPadding(dp(8), 0, dp(8), 0);
        TextView volIcon = new TextView(this);
        volIcon.setText("♪");
        volIcon.setTextColor(MUTED);
        volumeBar = new SeekBar(this);
        volumeBar.setMax(100);
        volumeBar.setProgress(settings.volume);
        volumeBar.getProgressDrawable().setColorFilter(ACCENT, android.graphics.PorterDuff.Mode.SRC_IN);
        volumeBar.getThumb().setColorFilter(ACCENT, android.graphics.PorterDuff.Mode.SRC_IN);
        volumeBar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar bar, int value, boolean fromUser) {
                if (fromUser) {
                    settings.volume = value;
                    applyVolume();
                }
            }
            @Override public void onStartTrackingTouch(SeekBar bar) { }
            @Override public void onStopTrackingTouch(SeekBar bar) { settings.save(MainActivity.this); }
        });
        volumeRow.addView(volIcon);
        volumeRow.addView(volumeBar, new LinearLayout.LayoutParams(0,
                ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        page.addView(volumeRow, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        // subtitle overlay lives on the stage
        TextView subtitleView = new TextView(this);
        subtitleView.setTextColor(TEXT);
        subtitleView.setTextSize(15);
        subtitleView.setGravity(Gravity.CENTER);
        subtitleView.setPadding(dp(16), 0, dp(16), dp(12));
        subtitleView.setId(View.generateViewId());
        subtitleView.setTag("subtitle");
        stage.addView(subtitleView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM));

        return page;
    }

    private android.graphics.drawable.GradientDrawable circleBackground() {
        android.graphics.drawable.GradientDrawable drawable =
                new android.graphics.drawable.GradientDrawable();
        drawable.setShape(android.graphics.drawable.GradientDrawable.OVAL);
        drawable.setColor(Color.parseColor("#1c0d10"));
        drawable.setStroke(dp(2), ACCENT);
        return drawable;
    }

    private Button transportButton(String symbol, int sizeSp, int color) {
        Button button = new Button(this);
        button.setText(symbol);
        button.setTextColor(color);
        button.setTextSize(sizeSp);
        button.setBackgroundColor(Color.TRANSPARENT);
        button.setPadding(0, 0, 0, 0);
        button.setMinWidth(dp(56));
        button.setMinHeight(dp(56));
        return button;
    }

    private Button smallButton(String symbol) {
        Button button = new Button(this);
        button.setText(symbol);
        button.setTextColor(TEXT);
        button.setTextSize(14);
        button.setBackgroundColor(Color.parseColor("#161a20"));
        button.setPadding(dp(10), 0, dp(10), 0);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, dp(40));
        params.setMargins(dp(4), 0, dp(4), 0);
        button.setLayoutParams(params);
        return button;
    }

    private static String rateLabel(float rate) {
        if (rate == (long) rate) return String.format(Locale.US, "%d×", (long) rate);
        return String.format(Locale.US, "%g×", rate);
    }

    // ---------------------------------------------------------------- QUEUE view

    private View buildQueueView() {
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setPadding(dp(10), dp(10), dp(10), dp(76));

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);
        Button add = smallButton("＋");
        add.setOnClickListener(v -> openFilePicker());
        Button addUrl = smallButton("∿");
        addUrl.setOnClickListener(v -> showAddUrlDialog());
        Button save = smallButton("⤓");
        save.setOnClickListener(v -> showSavePlaylistDialog());
        Button load = smallButton("⤒");
        load.setOnClickListener(v -> openPlaylistPicker());
        Button clear = smallButton("⌫");
        clear.setOnClickListener(v -> confirmClearQueue());
        header.addView(add);
        header.addView(addUrl);
        header.addView(load);
        header.addView(save);
        header.addView(clear);
        queueSummary = new TextView(this);
        queueSummary.setTextColor(MUTED);
        queueSummary.setTextSize(12);
        queueSummary.setGravity(Gravity.END);
        header.addView(queueSummary, new LinearLayout.LayoutParams(0,
                ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        page.addView(header);

        queueSearch = new EditText(this);
        queueSearch.setHint("Queue durchsuchen…");
        queueSearch.setTextColor(TEXT);
        queueSearch.setHintTextColor(MUTED);
        queueSearch.setTextSize(13);
        queueSearch.setBackground(boxBackground());
        queueSearch.setPadding(dp(12), dp(8), dp(12), dp(8));
        queueSearch.setSingleLine(true);
        queueSearch.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int a, int b, int c) { }
            @Override public void onTextChanged(CharSequence s, int a, int b, int c) { }
            @Override public void afterTextChanged(Editable s) { refreshQueueUi(); }
        });
        LinearLayout.LayoutParams searchParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        searchParams.topMargin = dp(8);
        searchParams.bottomMargin = dp(8);
        page.addView(queueSearch, searchParams);

        queueList = new ListView(this);
        queueList.setBackgroundColor(SURFACE);
        queueAdapter = new QueueAdapter();
        queueList.setAdapter(queueAdapter);
        queueList.setOnItemClickListener((parent, view, position, id) -> {
            List<Integer> visible = visibleQueueIndexes();
            if (position < visible.size()) engine.playIndex(visible.get(position));
        });
        page.addView(queueList, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));

        LinearLayout footer = new LinearLayout(this);
        footer.setOrientation(LinearLayout.HORIZONTAL);
        footer.setGravity(Gravity.CENTER);
        Button up = smallButton("↑");
        up.setOnClickListener(v -> moveSelected(-1));
        Button down = smallButton("↓");
        down.setOnClickListener(v -> moveSelected(1));
        Button rename = smallButton("✎");
        rename.setOnClickListener(v -> renameSelected());
        footer.addView(up);
        footer.addView(down);
        footer.addView(rename);
        page.addView(footer);
        return page;
    }

    private void moveSelected(int delta) {
        int position = queueAdapter.selected;
        List<Integer> visible = visibleQueueIndexes();
        int mapped = position >= 0 && position < visible.size() ? visible.get(position) : -1;
        if (mapped < 0) return;
        int target = mapped + delta;
        if (target < 0 || target >= engine.items().size()) return;
        engine.move(mapped, target);
        queueAdapter.selected = queueAdapter.selected + delta;
        refreshQueueUi();
    }

    private void renameSelected() {
        int mapped = selectedQueueIndex();
        if (mapped < 0) {
            toast("Kein Eintrag gewählt");
            return;
        }
        MediaItem item = engine.items().get(mapped);
        EditText input = new EditText(this);
        input.setText(item.title);
        input.setTextColor(TEXT);
        new AlertDialog.Builder(this)
                .setTitle("Umbenennen")
                .setView(input)
                .setPositiveButton("OK", (dialog, which) -> {
                    engine.rename(mapped, input.getText().toString());
                    refreshQueueUi();
                })
                .setNegativeButton("Abbrechen", null)
                .show();
    }

    private int selectedQueueIndex() {
        List<Integer> visible = visibleQueueIndexes();
        int position = queueAdapter.selected;
        return position >= 0 && position < visible.size() ? visible.get(position) : -1;
    }

    private List<Integer> visibleQueueIndexes() {
        List<Integer> out = new ArrayList<>();
        if (engine == null) return out;
        String query = queueSearch != null ? queueSearch.getText().toString().trim().toLowerCase(Locale.ROOT) : "";
        List<MediaItem> items = engine.items();
        for (int i = 0; i < items.size(); i++) {
            MediaItem item = items.get(i);
            String hay = (item.title + " " + item.url + " " + item.badge).toLowerCase(Locale.ROOT);
            if (query.isEmpty() || hay.contains(query)) out.add(i);
        }
        return out;
    }

    private void refreshQueueUi() {
        if (queueAdapter == null) return;
        queueAdapter.reload();
        List<MediaItem> items = engine.items();
        queueSummary.setText(engine.items().size() + " Einträge"
                + (engine.shuffle() ? " · ⤨" : "")
                + ("one".equals(engine.repeat()) ? " · ↻1" : "all".equals(engine.repeat()) ? " · ↻∞" : ""));
    }

    private final class QueueAdapter extends BaseAdapter {
        private final List<MediaItem> visible = new ArrayList<>();
        private final List<Integer> sourceIndexes = new ArrayList<>();
        int selected = -1;

        void reload() {
            visible.clear();
            sourceIndexes.clear();
            sourceIndexes.addAll(visibleQueueIndexes());
            for (int index : sourceIndexes) visible.add(engine.items().get(index));
            notifyDataSetChanged();
        }

        @Override public int getCount() { return visible.size(); }
        @Override public Object getItem(int position) { return visible.get(position); }
        @Override public long getItemId(int position) { return position; }

        @Override public View getView(int position, View convertView, ViewGroup parent) {
            LinearLayout row = convertView instanceof LinearLayout ? (LinearLayout) convertView : createQueueRow();
            MediaItem item = visible.get(position);
            int sourceIndex = sourceIndexes.get(position);
            TextView title = row.findViewWithTag("qtitle");
            TextView badge = row.findViewWithTag("qbadge");
            title.setText(item.title + (item.artist != null && !item.artist.isEmpty()
                    ? "\n" + item.artist : ""));
            badge.setText(item.badge);
            boolean active = sourceIndex == engine.index();
            row.setBackgroundColor(active ? Color.parseColor("#2a1114") : SURFACE);
            title.setTextColor(active ? ACCENT : TEXT);
            return row;
        }

        private LinearLayout createQueueRow() {
            LinearLayout row = new LinearLayout(MainActivity.this);
            row.setOrientation(LinearLayout.HORIZONTAL);
            row.setGravity(Gravity.CENTER_VERTICAL);
            row.setPadding(dp(12), dp(10), dp(12), dp(10));
            TextView badge = new TextView(MainActivity.this);
            badge.setTag("qbadge");
            badge.setTextColor(ACCENT);
            badge.setTextSize(10);
            badge.setTypeface(null, Typeface.BOLD);
            badge.setGravity(Gravity.CENTER);
            badge.setBackground(boxBackground());
            row.addView(badge, new LinearLayout.LayoutParams(dp(52), dp(24)));
            TextView title = new TextView(MainActivity.this);
            title.setTag("qtitle");
            title.setTextColor(TEXT);
            title.setTextSize(13);
            title.setPadding(dp(12), 0, dp(8), 0);
            row.addView(title, new LinearLayout.LayoutParams(0,
                    ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
            Button remove = new Button(MainActivity.this);
            remove.setText("×");
            remove.setTextColor(MUTED);
            remove.setTextSize(14);
            remove.setBackgroundColor(Color.TRANSPARENT);
            remove.setPadding(dp(8), 0, dp(8), 0);
            remove.setOnClickListener(v -> {
                Object tag = v.getTag();
                if (tag != null) engine.removeAt((int) tag);
            });
            remove.setTag(-1);
            row.addView(remove, new LinearLayout.LayoutParams(dp(40), dp(40)));
            row.setOnClickListener(v -> {
                int position = queueList.getPositionForView(v);
                selected = position;
                refreshQueueUi();
            });
            row.setOnLongClickListener(v -> {
                int position = queueList.getPositionForView(v);
                selected = position;
                engine.playIndex(sourceIndexes.get(position));
                return true;
            });
            return row;
        }
    }

    // ---------------------------------------------------------------- LIBRARY view

    private View buildLibraryView() {
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setPadding(dp(10), dp(10), dp(10), dp(76));

        librarySearch = new EditText(this);
        librarySearch.setHint("Bibliothek durchsuchen…");
        librarySearch.setTextColor(TEXT);
        librarySearch.setHintTextColor(MUTED);
        librarySearch.setTextSize(13);
        librarySearch.setBackground(boxBackground());
        librarySearch.setPadding(dp(12), dp(8), dp(12), dp(8));
        librarySearch.setSingleLine(true);
        librarySearch.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int a, int b, int c) { }
            @Override public void onTextChanged(CharSequence s, int a, int b, int c) { }
            @Override public void afterTextChanged(Editable s) { refreshLibrary(); }
        });
        LinearLayout searchRow = new LinearLayout(this);
        searchRow.setOrientation(LinearLayout.HORIZONTAL);
        searchRow.setGravity(Gravity.CENTER_VERTICAL);
        searchRow.addView(librarySearch, new LinearLayout.LayoutParams(0,
                ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        Button libRefresh = smallButton("⟳");
        libRefresh.setOnClickListener(v -> {
            if (library != null) library.rescan();
            refreshLibrary();
            toast("Bibliothek aktualisiert");
        });
        searchRow.addView(libRefresh);
        page.addView(searchRow, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        LinearLayout chips = new LinearLayout(this);
        chips.setOrientation(LinearLayout.HORIZONTAL);
        String[] modes = {"all", "artists", "albums", "genres", "favorites"};
        String[] labels = {"ALLE", "ARTISTS", "ALBUMS", "GENRES", "★"};
        for (int i = 0; i < modes.length; i++) {
            Button chip = new Button(this);
            chip.setText(labels[i]);
            chip.setTextSize(10);
            chip.setTextColor(TEXT);
            chip.setBackgroundColor(Color.parseColor("#161a20"));
            chip.setPadding(dp(10), 0, dp(10), 0);
            String mode = modes[i];
            chip.setOnClickListener(v -> {
                libraryMode = mode;
                refreshLibrary();
            });
            chips.addView(chip);
        }
        page.addView(chips, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        libraryList = new ListView(this);
        libraryList.setBackgroundColor(SURFACE);
        libraryAdapter = new LibraryAdapter();
        libraryList.setAdapter(libraryAdapter);
        libraryList.setOnItemClickListener((parent, view, position, id) -> {
            if (position < libraryTracks.size()) {
                Library.Track track = libraryTracks.get(position);
                MediaItem item = track.toItem();
                item.playlist = "LIBRARY";
                engine.openExternal(item, true, 0);
                toast("▶ " + item.title);
                showTab(TAB_PLAY);
            }
        });
        libraryList.setOnItemLongClickListener((parent, view, position, id) -> {
            if (position < libraryTracks.size()) {
                Library.Track track = libraryTracks.get(position);
                library.toggleFavorite(track.uri);
                toast(library.isFavorite(track.uri) ? "★ Favorit" : "Favorit entfernt");
                refreshLibrary();
                return true;
            }
            return false;
        });
        page.addView(libraryList, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        return page;
    }

    private void refreshLibrary() {
        ui.post(() -> {
            if (library == null) return;
            String query = librarySearch != null ? librarySearch.getText().toString().trim() : "";
            boolean includeAudio = !"video-only".equals(libraryMode);
            boolean includeVideo = !"artists".equals(libraryMode) && !"albums".equals(libraryMode);
            List<Library.Track> tracks = library.query(query, includeAudio, includeVideo);
            if ("favorites".equals(libraryMode)) {
                tracks = library.filterFavorites(tracks);
            }
            libraryTracks = tracks;
            if (libraryAdapter != null) libraryAdapter.notifyDataSetChanged();
        });
    }

    private final class LibraryAdapter extends BaseAdapter {
        @Override public int getCount() { return libraryTracks.size(); }
        @Override public Object getItem(int position) { return libraryTracks.get(position); }
        @Override public long getItemId(int position) { return position; }

        @Override public View getView(int position, View convertView, ViewGroup parent) {
            LinearLayout row = convertView instanceof LinearLayout ? (LinearLayout) convertView : null;
            if (row == null) {
                row = new LinearLayout(MainActivity.this);
                row.setOrientation(LinearLayout.VERTICAL);
                row.setPadding(dp(12), dp(8), dp(12), dp(8));
                TextView title = new TextView(MainActivity.this);
                title.setTag("ltitle");
                title.setTextColor(TEXT);
                title.setTextSize(13);
                TextView meta = new TextView(MainActivity.this);
                meta.setTag("lmeta");
                meta.setTextColor(MUTED);
                meta.setTextSize(11);
                row.addView(title);
                row.addView(meta);
            }
            Library.Track track = libraryTracks.get(position);
            TextView title = row.findViewWithTag("ltitle");
            TextView meta = row.findViewWithTag("lmeta");
            title.setText((library.isFavorite(track.uri) ? "★ " : "") + track.title);
            String details = join(" · ", track.artist, track.album, track.genre);
            meta.setText(details.isEmpty() ? (track.video ? "VIDEO" : "AUDIO") : details);
            return row;
        }
    }

    private static String join(String separator, String... parts) {
        StringBuilder sb = new StringBuilder();
        for (String part : parts) {
            if (part == null || part.isEmpty()) continue;
            if (sb.length() > 0) sb.append(separator);
            sb.append(part);
        }
        return sb.toString();
    }

    // ---------------------------------------------------------------- WEB view

    private View buildWebView() {
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setPadding(dp(10), dp(10), dp(10), dp(76));

        TextView heading = new TextView(this);
        heading.setText("WEB & STREAMS");
        heading.setTextColor(ACCENT);
        heading.setTextSize(13);
        heading.setTypeface(null, Typeface.BOLD);
        page.addView(heading);

        providerGrid = new LinearLayout(this);
        providerGrid.setOrientation(LinearLayout.VERTICAL);
        for (int i = 0; i < PROVIDER_NAMES.length; i += 3) {
            LinearLayout row = new LinearLayout(this);
            row.setOrientation(LinearLayout.HORIZONTAL);
            for (int j = i; j < Math.min(i + 3, PROVIDER_NAMES.length); j++) {
                LinearLayout card = new LinearLayout(this);
                card.setOrientation(LinearLayout.VERTICAL);
                card.setGravity(Gravity.CENTER);
                card.setBackground(boxBackground());
                card.setPadding(dp(8), dp(14), dp(8), dp(14));
                ImageView icon = new ImageView(this);
                Bitmap iconBmp = ProviderIcons.get(PROVIDER_NAMES[j]);
                if (iconBmp != null) {
                    icon.setImageBitmap(iconBmp);
                    icon.setScaleType(ImageView.ScaleType.CENTER_INSIDE);
                } else {
                    // fallback: colored circle with initial
                    icon.setImageBitmap(drawFallbackIcon(PROVIDER_NAMES[j],
                            PROVIDER_COLORS[j]));
                    icon.setScaleType(ImageView.ScaleType.CENTER_INSIDE);
                }
                icon.setLayoutParams(new LinearLayout.LayoutParams(dp(56), dp(56)));
                TextView label = new TextView(this);
                label.setText(PROVIDER_NAMES[j]);
                label.setTextColor(PROVIDER_COLORS[j]);
                label.setTextSize(10);
                label.setGravity(Gravity.CENTER);
                label.setTypeface(null, Typeface.BOLD);
                card.addView(icon);
                card.addView(label);
                final String name = PROVIDER_NAMES[j];
                final String url = PROVIDER_URLS[j];
                card.setOnClickListener(v -> openProvider(name, url));
                row.addView(card, new LinearLayout.LayoutParams(0,
                        ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
            }
            providerGrid.addView(row);
        }
        page.addView(providerGrid, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        TextView ytHeading = new TextView(this);
        ytHeading.setText("YOUTUBE");
        ytHeading.setTextColor(ACCENT);
        ytHeading.setTextSize(13);
        ytHeading.setTypeface(null, Typeface.BOLD);
        LinearLayout.LayoutParams ytParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        ytParams.topMargin = dp(14);
        page.addView(ytHeading, ytParams);

        LinearLayout searchRow = new LinearLayout(this);
        searchRow.setOrientation(LinearLayout.HORIZONTAL);
        EditText ytQuery = new EditText(this);
        ytQuery.setHint("Suchbegriff oder YouTube-URL…");
        ytQuery.setTextColor(TEXT);
        ytQuery.setHintTextColor(MUTED);
        ytQuery.setTextSize(13);
        ytQuery.setBackground(boxBackground());
        ytQuery.setPadding(dp(12), dp(10), dp(12), dp(10));
        ytQuery.setSingleLine(true);
        ytQuery.setId(View.generateViewId());
        searchRow.addView(ytQuery, new LinearLayout.LayoutParams(0,
                ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        Button go = smallButton("▶");
        go.setOnClickListener(v -> runYouTubeSearch(ytQuery.getText().toString()));
        searchRow.addView(go);
        page.addView(searchRow);

        LinearLayout results = new LinearLayout(this);
        results.setOrientation(LinearLayout.VERTICAL);
        results.setId(View.generateViewId());
        results.setTag("yt-results");
        page.addView(results, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        return page;
    }

    private void runYouTubeSearch(String query) {
        if (query == null || query.trim().isEmpty()) return;
        if (!settings.consent) {
            toast("Erst die yt-dlp-/YouTube-Hinweise in SETUP bestätigen");
            return;
        }
        LinearLayout results = content.findViewWithTag("yt-results");
        results.removeAllViews();
        TextView status = new TextView(this);
        status.setTextColor(MUTED);
        status.setText("Suche…");
        results.addView(status);
        final String term = query.trim();
        new Thread(() -> {
            String finalError = null;
            List<YouTubeClient.Video> found = null;
            try {
                String id = YouTubeClient.extractVideoId(term);
                if (id != null && (term.contains("youtu") || term.length() == 11)) {
                    // direct URL: resolve + queue + play
                    String mediaUrl = YouTubeClient.resolveMediaUrl(term);
                    MediaItem item = new MediaItem(mediaUrl, "YouTube " + id,
                            "youtube", "YT");
                    ui.post(() -> {
                        engine.openExternal(item, true, 0);
                        toast("▶ YouTube");
                        showTab(TAB_PLAY);
                    });
                    return;
                }
                found = YouTubeClient.search(term, 20);
            } catch (Exception e) {
                finalError = e.getMessage();
            }
            final List<YouTubeClient.Video> finalFound = found;
            final String error = finalError;
            ui.post(() -> {
                results.removeAllViews();
                if (error != null) {
                    TextView failed = new TextView(MainActivity.this);
                    failed.setTextColor(ACCENT);
                    failed.setText("Suche fehlgeschlagen: " + error);
                    results.addView(failed);
                    return;
                }
                if (finalFound == null || finalFound.isEmpty()) return;
                for (YouTubeClient.Video video : finalFound) {
                    results.addView(youTubeResultRow(video));
                }
            });
        }).start();
    }

    private View youTubeResultRow(YouTubeClient.Video video) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.VERTICAL);
        row.setPadding(dp(12), dp(10), dp(12), dp(10));
        row.setBackground(boxBackground());
        TextView title = new TextView(this);
        title.setTextColor(TEXT);
        title.setTextSize(13);
        title.setText(video.title);
        TextView meta = new TextView(this);
        meta.setTextColor(MUTED);
        meta.setTextSize(11);
        meta.setText((video.channel == null ? "YouTube" : video.channel)
                + (video.durationSeconds > 0 ? " · " + video.durationSeconds / 60 + ":"
                + String.format(Locale.US, "%02d", video.durationSeconds % 60) : ""));
        row.addView(title);
        row.addView(meta);
        row.setOnClickListener(v -> new Thread(() -> {
            try {
                String mediaUrl = YouTubeClient.resolveMediaUrl(video.id);
                MediaItem item = new MediaItem(mediaUrl,
                        video.title, video.durationSeconds > 0 ? "video" : "stream", "YT");
                ui.post(() -> {
                    engine.openExternal(item, true, 0);
                    toast("▶ " + video.title);
                    showTab(TAB_PLAY);
                });
            } catch (Exception e) {
                ui.post(() -> toast("YouTube: " + e.getMessage()));
            }
        }).start());
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.topMargin = dp(6);
        row.setLayoutParams(params);
        return row;
    }

    private void openProvider(String name, String url) {
        Intent intent = new Intent(this, ProviderActivity.class);
        intent.putExtra("name", name);
        intent.putExtra("url", url);
        startActivity(intent);
    }

    // ---------------------------------------------------------------- SETTINGS view

    private View buildSettingsView() {
        android.widget.ScrollView scroll = new android.widget.ScrollView(this);
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setPadding(dp(16), dp(16), dp(16), dp(90));
        scroll.addView(page);

        page.addView(sectionLabel("PLAYBACK"));
        settingsVolume = new SeekBar(this);
        settingsVolume.setMax(100);
        settingsVolume.setProgress(settings.volume);
        settingsVolume.getProgressDrawable().setColorFilter(ACCENT, android.graphics.PorterDuff.Mode.SRC_IN);
        settingsVolume.getThumb().setColorFilter(ACCENT, android.graphics.PorterDuff.Mode.SRC_IN);
        settingsVolume.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar bar, int value, boolean fromUser) {
                if (fromUser) {
                    settings.volume = value;
                    applyVolume();
                    if (volumeBar != null) volumeBar.setProgress(value);
                }
            }
            @Override public void onStartTrackingTouch(SeekBar bar) { }
            @Override public void onStopTrackingTouch(SeekBar bar) { settings.save(MainActivity.this); }
        });
        page.addView(settingsVolume);

        resumeBox = new android.widget.CheckBox(this);
        resumeBox.setText("Wiedergabe beim Start fortsetzen");
        resumeBox.setTextColor(TEXT);
        resumeBox.setChecked(settings.resume);
        resumeBox.setOnCheckedChangeListener((button, checked) -> {
            settings.resume = checked;
            settings.save(this);
        });
        page.addView(resumeBox);

        page.addView(sectionLabel("VISUALIZER"));
        android.widget.CheckBox vizBox = new android.widget.CheckBox(this);
        vizBox.setText("Wellenform-Visualizer (Oszilloskop)");
        vizBox.setTextColor(TEXT);
        vizBox.setChecked(settings.visualizer);
        vizBox.setOnCheckedChangeListener((button, checked) -> {
            settings.visualizer = checked;
            settings.save(this);
            waveView.setVisibility(checked ? View.VISIBLE : View.GONE);
            if (!checked) {
                if (visualizer != null) {
                    try { visualizer.setEnabled(false); visualizer.release(); } catch (Exception ignored) {}
                    visualizer = null;
                }
            } else {
                attachVisualizer();
            }
        });
        page.addView(vizBox);

        page.addView(sectionLabel("LEGAL"));
        consentBox = new android.widget.CheckBox(this);
        consentBox.setText("YouTube/yt-dlp nur für private Nutzung aktivieren");
        consentBox.setTextColor(TEXT);
        consentBox.setChecked(settings.consent);
        consentBox.setOnCheckedChangeListener((button, checked) -> {
            settings.consent = checked;
            settings.save(this);
        });
        page.addView(consentBox);

        page.addView(sectionLabel("LIBRARY"));
        Button refreshLib = new Button(this);
        refreshLib.setText("Bibliothek aktualisieren");
        refreshLib.setTextColor(TEXT);
        refreshLib.setBackgroundColor(Color.parseColor("#161a20"));
        refreshLib.setOnClickListener(v -> {
            if (library != null) library.rescan();
            refreshLibrary();
            toast("Bibliothek aktualisiert");
        });
        page.addView(refreshLib);

        Button scanDir = new Button(this);
        scanDir.setText("Ordner scannen…");
        scanDir.setTextColor(TEXT);
        scanDir.setBackgroundColor(Color.parseColor("#161a20"));
        scanDir.setOnClickListener(v -> openFilePicker());
        page.addView(scanDir);

        page.addView(sectionLabel("ACTIONS"));
        Button loadSubtitle = new Button(this);
        loadSubtitle.setText("Untertitel laden (SRT/VTT)");
        loadSubtitle.setTextColor(TEXT);
        loadSubtitle.setBackgroundColor(Color.parseColor("#161a20"));
        loadSubtitle.setOnClickListener(v -> openSubtitlePicker());
        page.addView(loadSubtitle);

        Button info = new Button(this);
        info.setText("Media-Info");
        info.setTextColor(TEXT);
        info.setBackgroundColor(Color.parseColor("#161a20"));
        info.setOnClickListener(v -> showMediaInfo());
        page.addView(info);

        page.addView(sectionLabel("ABOUT"));
        aboutBox = new TextView(this);
        aboutBox.setTextColor(MUTED);
        aboutBox.setTextSize(12);
        aboutBox.setText("MPCASU 6.0 — Native Android\nMedia Player für CASU & Legacy-Medien\n"
                + "In-Process Playback · Kein externer Player\n\n"
                + "Design inspiriert von VLC und Webamp — unabhängiger Original-Code.\n"
                + "Anti-Capitalist License 1.4 · Lino Casu");
        page.addView(aboutBox);
        return scroll;
    }

    private TextView sectionLabel(String text) {
        TextView label = new TextView(this);
        label.setText(text);
        label.setTextColor(ACCENT);
        label.setTextSize(11);
        label.setTypeface(null, Typeface.BOLD);
        label.setPadding(0, dp(16), 0, dp(6));
        return label;
    }

    private android.graphics.drawable.GradientDrawable boxBackground() {
        android.graphics.drawable.GradientDrawable drawable =
                new android.graphics.drawable.GradientDrawable();
        drawable.setColor(Color.parseColor("#12151a"));
        drawable.setCornerRadius(dp(8));
        drawable.setStroke(1, BORDER);
        return drawable;
    }

    // ================================================================== ENGINE EVENTS

    @Override public void onStateChanged(boolean playing) {
        ui.post(() -> {
            playBtn.setText(playing ? "❚❚" : "▶");
            if (recordBtn != null) recordBtn.setTextColor(recording ? ACCENT : TEXT);
        });
    }

    @Override public void onItemChanged(MediaItem item, int index) {
        ui.post(() -> {
            titleView.setText(item != null && item.title != null ? item.title : "MPCASU");
            artistView.setText(item != null && item.badge != null ? item.badge : "");
            updateStageFor(item);
            loadCover(item);
            loadSubtitleFor(item);
            refreshQueueUi();
        });
    }

    @Override public void onPosition(long positionMs, long durationMs) {
        ui.post(() -> {
            if (draggingSeek) return;
            if (durationMs > 0) {
                seekBar.setMax((int) durationMs);
                seekBar.setProgress((int) positionMs);
            }
            updateTimeLabels(positionMs, durationMs);
        });
    }

    @Override public void onEnded(int finishedIndex) { }

    @Override public void onError(String userMessage) {
        ui.post(() -> toast(userMessage));
    }

    @Override public void onQueueChanged() {
        ui.post(this::refreshQueueUi);
    }

    @Override public void onTracksReady(MediaPlayer player) {
        ui.post(() -> {
            boolean video = engine.videoWidth() > 0 && engine.videoHeight() > 0;
            videoActive = video;
            updateStageFor(engine.current());
            attachVisualizer();
        });
    }

    @Override public void onVideoSizeChanged(int width, int height) {
        ui.post(() -> {
            if (width > 0 && height > 0) {
                videoActive = true;
                updateStageFor(engine.current());
            }
        });
    }

    private void updateTimeLabels(long positionMs, long durationMs) {
        timeNow.setText(formatTime(positionMs));
        timeTotal.setText(formatTime(durationMs));
    }

    private static String formatTime(long ms) {
        long seconds = Math.max(0, ms) / 1000;
        return String.format(Locale.US, "%d:%02d", seconds / 60, seconds % 60);
    }

    // ================================================================== STAGE

    private void updateStageFor(MediaItem item) {
        boolean video = item != null && (item.isVideo() || (videoActive && engine.videoWidth() > 0));
        videoView.setVisibility(video ? View.VISIBLE : View.GONE);
        waveView.setVisibility(!video && settings.visualizer ? View.VISIBLE : View.GONE);
        coverView.setVisibility(!video && coverView.getVisibility() == View.VISIBLE
                && !settings.visualizer ? View.VISIBLE : View.GONE);
    }

    private void attachVisualizer() {
        if (engine == null || !settings.visualizer || videoActive) return;
        if (visualizer != null) {
            try { visualizer.release(); } catch (Exception ignored) {}
            visualizer = null;
        }
        visualizer = engine.attachVisualizer(7000, new Visualizer.OnDataCaptureListener() {
            @Override public void onWaveFormDataCapture(Visualizer vis, byte[] waveform, int samplingRate) {
                waveView.setWaveform(waveform);
            }
            @Override public void onFftDataCapture(Visualizer vis, byte[] fft, int samplingRate) { }
        });
    }

    private void loadCover(MediaItem item) {
        if (item == null || item.isVideo()) {
            coverView.setVisibility(View.GONE);
            return;
        }
        new Thread(() -> {
            Bitmap bitmap = null;
            try {
                MediaMetadataRetriever retriever = new MediaMetadataRetriever();
                try {
                    if (item.url.startsWith("content://")) {
                        retriever.setDataSource(this, Uri.parse(item.url));
                    } else if (item.url.startsWith("/")) {
                        retriever.setDataSource(item.url);
                    } else {
                        retriever.setDataSource(item.url, new java.util.HashMap<>());
                    }
                    byte[] art = retriever.getEmbeddedPicture();
                    if (art != null) {
                        bitmap = android.graphics.BitmapFactory.decodeByteArray(art, 0, art.length);
                    }
                } finally {
                    retriever.release();
                }
            } catch (Exception ignored) {
            }
            Bitmap finalBitmap = bitmap;
            ui.post(() -> {
                if (finalBitmap != null) {
                    coverView.setImageBitmap(finalBitmap);
                    if (!settings.visualizer) coverView.setVisibility(View.VISIBLE);
                } else {
                    coverView.setVisibility(View.GONE);
                }
            });
        }).start();
    }

    private void loadSubtitleFor(MediaItem item) {
        subtitles = null;
        TextView subtitleView = content.findViewWithTag("subtitle");
        if (subtitleView != null) subtitleView.setText("");
        if (item == null || item.subtitle == null || item.subtitle.isEmpty()) return;
        new Thread(() -> {
            try {
                SubtitleLoader loaded = SubtitleLoader.load(item.subtitle);
                subtitles = loaded;
                ui.post(() -> toast("Untertitel geladen · " + loaded.count() + " cues"));
            } catch (Exception e) {
                ui.post(() -> toast("Untertitel konnte nicht geladen werden"));
            }
        }).start();
    }

    // ================================================================== ACTIONS

    private void applyVolume() {
        // MediaPlayer has no gain > 1; map settings.volume (0..100) linearly.
        if (engine != null && engine.player() != null) {
            float gain = Math.max(0f, Math.min(1f, settings.volume / 100f));
            try { engine.player().setVolume(gain, gain); } catch (Exception ignored) {}
        }
    }

    private void saveSnapshot() {
        MediaItem item = engine != null ? engine.current() : null;
        if (item == null) {
            toast("Keine Wiedergabe aktiv");
            return;
        }
        new Thread(() -> {
            try {
                MediaMetadataRetriever retriever = new MediaMetadataRetriever();
                try {
                    if (item.url.startsWith("content://")) {
                        retriever.setDataSource(this, Uri.parse(item.url));
                    } else if (item.url.startsWith("/")) {
                        retriever.setDataSource(item.url);
                    } else {
                        retriever.setDataSource(item.url, new java.util.HashMap<>());
                    }
                    Bitmap frame = retriever.getFrameAtTime(engine.position() * 1000,
                            MediaMetadataRetriever.OPTION_CLOSEST);
                    if (frame == null) {
                        ui.post(() -> toast("Kein Video-Frame verfügbar"));
                        return;
                    }
                    File dir = new File(getExternalFilesDir(Environment.DIRECTORY_PICTURES),
                            "MPCASU");
                    if (!dir.exists()) dir.mkdirs();
                    File out = new File(dir, "snapshot-"
                            + new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US)
                            .format(new Date()) + ".png");
                    try (FileOutputStream stream = new FileOutputStream(out)) {
                        frame.compress(Bitmap.CompressFormat.PNG, 90, stream);
                    }
                    ui.post(() -> toast("Snapshot gespeichert · " + out.getName()));
                } finally {
                    retriever.release();
                }
            } catch (Exception e) {
                ui.post(() -> toast("Snapshot fehlgeschlagen: " + e.getMessage()));
            }
        }).start();
    }

    private void toggleRecording() {
        MediaItem item = engine != null ? engine.current() : null;
        if (item == null) {
            toast("Erst eine Quelle öffnen");
            return;
        }
        if (!item.url.startsWith("http")) {
            toast("Aufnahme für Streams (lokale Dateien speichern mit Export)");
            return;
        }
        if (recording) {
            recording = false;
            recordBtn.setTextColor(TEXT);
            toast("Aufnahme wird abgeschlossen…");
            if (recordThread != null) recordThread.interrupt();
            return;
        }
        File dir = new File(getExternalFilesDir(Environment.DIRECTORY_MUSIC), "MPCASU");
        if (!dir.exists()) dir.mkdirs();
        recordTarget = new File(dir, "record-"
                + new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(new Date())
                + ".ts");
        recording = true;
        recordBtn.setTextColor(ACCENT);
        toast("Aufnahme · " + recordTarget.getName());
        recordThread = new Thread(() -> {
            try (java.io.InputStream in = new java.net.URL(item.url).openStream();
                 java.io.OutputStream out = new java.io.FileOutputStream(recordTarget)) {
                byte[] chunk = new byte[64 * 1024];
                int n;
                while (recording && (n = in.read(chunk)) > 0) out.write(chunk, 0, n);
            } catch (Exception e) {
                ui.post(() -> toast("Aufnahme fehlgeschlagen: " + e.getMessage()));
            }
            recording = false;
            ui.post(() -> {
                recordBtn.setTextColor(TEXT);
                toast("Aufnahme gespeichert · " + recordTarget.getName());
            });
        });
        recordThread.start();
    }

    private void showMediaInfo() {
        MediaItem item = engine != null ? engine.current() : null;
        StringBuilder info = new StringBuilder();
        if (item == null) {
            info.append("Keine Wiedergabe aktiv");
        } else {
            info.append("Titel: ").append(item.title).append('\n');
            info.append("Badge: ").append(item.badge).append('\n');
            info.append("Quelle: ").append(item.url).append('\n');
            info.append("Position: ").append(formatTime(engine.position()))
                .append(" / ").append(formatTime(engine.duration())).append('\n');
            info.append("Video: ").append(engine.videoWidth()).append("×")
                .append(engine.videoHeight()).append('\n');
            if (item.url.toLowerCase().endsWith(".casu")) {
                String verify = CasuBridge.verifyCasunat2(item.url);
                info.append("CASU: ").append(verify.startsWith("ERROR")
                        ? verify : "Manifest verifiziert ✓");
            }
        }
        new AlertDialog.Builder(this)
                .setTitle("Media-Info")
                .setMessage(info.toString())
                .setPositiveButton("OK", null)
                .show();
    }

    private void confirmClearQueue() {
        new AlertDialog.Builder(this)
                .setTitle("Queue leeren?")
                .setPositiveButton("Leeren", (dialog, which) -> engine.clear())
                .setNegativeButton("Abbrechen", null)
                .show();
    }

    private void showAddUrlDialog() {
        EditText input = new EditText(this);
        input.setHint("http(s)://, rtsp:// …");
        input.setTextColor(TEXT);
        new AlertDialog.Builder(this)
                .setTitle("Netzwerk-Stream hinzufügen")
                .setView(input)
                .setPositiveButton("Hinzufügen", (dialog, which) -> {
                    String url = input.getText().toString().trim();
                    if (url.isEmpty()) return;
                    if (url.contains("youtu")) {
                        new Thread(() -> {
                            try {
                                String mediaUrl = YouTubeClient.resolveMediaUrl(url);
                                String id = YouTubeClient.extractVideoId(url);
                                ui.post(() -> {
                                    engine.openExternal(new MediaItem(mediaUrl,
                                            "YouTube " + id, "youtube", "YT"), true, 0);
                                    toast("▶ YouTube");
                                });
                            } catch (Exception e) {
                                ui.post(() -> toast("YouTube: " + e.getMessage()));
                            }
                        }).start();
                        return;
                    }
                    MediaItem item = new MediaItem(url, null, "stream", null);
                    engine.openExternal(item, true, 0);
                })
                .setNegativeButton("Abbrechen", null)
                .show();
    }

    private void showSavePlaylistDialog() {
        EditText name = new EditText(this);
        name.setHint("Playlist-Name");
        name.setTextColor(TEXT);
        String[] formats = {"m3u", "pls", "xspf", "jspf", "json"};
        new AlertDialog.Builder(this)
                .setTitle("Queue speichern als")
                .setView(name)
                .setItems(formats, (dialog, which) -> {
                    String base = name.getText().toString().trim();
                    if (base.isEmpty()) base = "playlist";
                    File dir = new File(getExternalFilesDir(Environment.DIRECTORY_MUSIC), "MPCASU");
                    if (!dir.exists()) dir.mkdirs();
                    File target = new File(dir, base + "." + formats[which]);
                    try {
                        String text;
                        if (which == 0) text = PlaylistIO.writeM3u(base, engine.items());
                        else if (which == 1) text = PlaylistIO.writePls(engine.items());
                        else if (which == 2) text = PlaylistIO.writeXspf(base, engine.items());
                        else if (which == 3) text = PlaylistIO.writeJspf(base, engine.items());
                        else text = PlaylistIO.writeCasuJson(base, engine.items());
                        PlaylistIO.writeText(target.getAbsolutePath(), text);
                        toast("Gespeichert · " + target.getName());
                    } catch (Exception e) {
                        toast("Speichern fehlgeschlagen: " + e.getMessage());
                    }
                })
                .setNegativeButton("Abbrechen", null)
                .show();
    }

    // ================================================================== FILE PICKING

    private static final int REQUEST_OPEN_MEDIA = 21;
    private static final int REQUEST_OPEN_PLAYLIST = 22;
    private static final int REQUEST_OPEN_SUBTITLE = 23;

    private void openFilePicker() {
        Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        try {
            startActivityForResult(Intent.createChooser(intent, "Medien öffnen"),
                    REQUEST_OPEN_MEDIA);
        } catch (Exception e) {
            toast("Kein Datei-Dialog verfügbar");
        }
    }

    private void openPlaylistPicker() {
        Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        try {
            startActivityForResult(Intent.createChooser(intent, "Playlist öffnen"),
                    REQUEST_OPEN_PLAYLIST);
        } catch (Exception e) {
            toast("Kein Datei-Dialog verfügbar");
        }
    }

    private void openSubtitlePicker() {
        MediaItem item = engine != null ? engine.current() : null;
        if (item == null) {
            toast("Erst Medien öffnen");
            return;
        }
        Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        try {
            startActivityForResult(Intent.createChooser(intent, "Untertitel öffnen"),
                    REQUEST_OPEN_SUBTITLE);
        } catch (Exception e) {
            toast("Kein Datei-Dialog verfügbar");
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (resultCode != RESULT_OK || data == null) return;
        List<Uri> uris = new ArrayList<>();
        if (data.getData() != null) uris.add(data.getData());
        if (data.getClipData() != null) {
            android.content.ClipDescription description = data.getClipData().getDescription();
            for (int i = 0; i < data.getClipData().getItemCount(); i++) {
                Uri uri = data.getClipData().getItemAt(i).getUri();
                if (uri != null) uris.add(uri);
            }
        }
        if (uris.isEmpty()) return;
        if (requestCode == REQUEST_OPEN_MEDIA) {
            List<MediaItem> items = new ArrayList<>();
            for (Uri uri : uris) {
                String kind = guessKind(uri);
                items.add(new MediaItem(uri.toString(), null, kind, null));
            }
            boolean wasEmpty = engine.items().isEmpty();
            engine.addAll(items);
            if (wasEmpty && !items.isEmpty()) {
                engine.playIndex(engine.items().size() - items.size());
            }
            toast(items.size() + " zur Queue hinzugefügt");
        } else if (requestCode == REQUEST_OPEN_PLAYLIST) {
            Uri uri = uris.get(0);
            loadPlaylist(uri);
        } else if (requestCode == REQUEST_OPEN_SUBTITLE) {
            MediaItem item = engine.current();
            if (item != null) {
                item.subtitle = uris.get(0).toString();
                loadSubtitleFor(item);
                engine.persist();
            }
        }
    }

    private static String guessKind(Uri uri) {
        String value = uri.toString().toLowerCase(Locale.ROOT);
        if (value.endsWith(".casu")) return "casu";
        if (value.endsWith(".mp5")) return "mp5";
        if (value.endsWith(".m3u") || value.endsWith(".m3u8") || value.endsWith(".pls")
                || value.endsWith(".xspf") || value.endsWith(".jspf") || value.endsWith(".asx")
                || value.endsWith(".wpl") || value.endsWith(".json")) return "playlist";
        if (value.contains("video") || value.endsWith(".mp4") || value.endsWith(".mkv")
                || value.endsWith(".webm") || value.endsWith(".mov") || value.endsWith(".m4v")) {
            return "video";
        }
        return "audio";
    }

    private void loadPlaylist(Uri uri) {
        new Thread(() -> {
            try {
                PlaylistIO.Playlist playlist = PlaylistIO.load(uri.toString(), PlaylistIO::fetchText);
                List<MediaItem> items = new ArrayList<>();
                for (PlaylistIO.Entry entry : playlist.items) {
                    if (entry.url == null || entry.url.isEmpty()) continue;
                    MediaItem item = new MediaItem(entry.url, entry.title, "stream", null);
                    item.playlist = playlist.name;
                    items.add(item);
                }
                ui.post(() -> {
                    engine.addAll(items);
                    toast(playlist.items.size() + " Einträge · " + playlist.name);
                    refreshQueueUi();
                });
            } catch (Exception e) {
                ui.post(() -> toast("Playlist fehlgeschlagen: " + e.getMessage()));
            }
        }).start();
    }

    // ================================================================== INTENTS

    private void handleIntent(Intent intent) {
        if (intent == null) return;
        String action = intent.getAction();
        if (Intent.ACTION_VIEW.equals(action) && intent.getData() != null) {
            Uri uri = intent.getData();
            String kind = guessKind(uri);
            withEngine(() -> {
                if ("playlist".equals(kind)) {
                    loadPlaylist(uri);
                } else {
                    MediaItem item = new MediaItem(uri.toString(), null, kind, null);
                    engine.openExternal(item, true, 0);
                }
            });
        } else if (Intent.ACTION_SEND.equals(action)) {
            Uri uri = intent.getParcelableExtra(Intent.EXTRA_STREAM);
            if (uri != null) {
                withEngine(() -> engine.openExternal(new MediaItem(uri.toString(), null,
                        guessKind(uri), null), true, 0));
            } else {
                String text = intent.getStringExtra(Intent.EXTRA_TEXT);
                if (text != null && text.contains("youtu")) {
                    showAddUrlDialog();
                }
            }
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIntent(intent);
    }

    // ================================================================== lifecycle

    @Override
    protected void onResume() {
        super.onResume();
        if (engine == null) {
            // Service engine not up yet: ensureEngine's retry loop will call
            // back through onEngineReady; nothing to render from a null queue.
            ensureEngine();
            return;
        }
        onStateChanged(engine.isPlaying());
        onItemChanged(engine.current(), engine.index());
        refreshQueueUi();
        // Resume playback on app start (setting).
        maybeResume();
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (engine != null) engine.persist();
    }

    private void toast(String text) {
        Toast.makeText(this, text, Toast.LENGTH_SHORT).show();
    }

    private Bitmap drawFallbackIcon(String name, int color) {
        int size = dp(56);
        Bitmap bmp = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        Canvas c = new Canvas(bmp);
        Paint bg = new Paint(Paint.ANTI_ALIAS_FLAG);
        bg.setColor(Color.parseColor("#12151a"));
        c.drawCircle(size/2f, size/2f, size/2f, bg);
        Paint fg = new Paint(Paint.ANTI_ALIAS_FLAG);
        fg.setColor(color);
        fg.setTextSize(size * 0.45f);
        fg.setTextAlign(Paint.Align.CENTER);
        fg.setTypeface(Typeface.DEFAULT_BOLD);
        String letter = name != null && !name.isEmpty() ? name.substring(0, 1) : "?";
        c.drawText(letter, size/2f, size * 0.62f, fg);
        return bmp;
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density);
    }
}
