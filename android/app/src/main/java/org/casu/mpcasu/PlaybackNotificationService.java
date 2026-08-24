package org.casu.mpcasu;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.media.session.MediaSession;
import android.os.Build;
import android.os.IBinder;
import android.widget.RemoteViews;

/**
 * VLC-style media notification: keeps transport controls (⏮ ▶/⏸ ⏭) in the
 * notification panel while the player runs, wired to the same PlayerBridge
 * JS surface as the widget and the MediaSession. Uses the platform
 * DecoratedMediaCustomViewStyle + MediaSession token so Android renders the
 * system media chrome around our custom row — no androidx required.
 */
public class PlaybackNotificationService extends Service {

    public static final String CHANNEL_ID = "playback";
    public static final int NOTIFICATION_ID = 42;

    public static final String ACTION_PREV = "org.casu.mpcasu.NOTIF_PREV";
    public static final String ACTION_PLAY = "org.casu.mpcasu.NOTIF_PLAY";
    public static final String ACTION_NEXT = "org.casu.mpcasu.NOTIF_NEXT";
    public static final String ACTION_STOP = "org.casu.mpcasu.NOTIF_STOP";

    private static boolean running = false;
    private static String lastTitle = "";
    private static boolean lastPlaying = false;

    public PlaybackNotificationService() {}

    @Override public IBinder onBind(Intent intent) { return null; }

    @Override public void onCreate() {
        super.onCreate();
        running = true;
        createChannel(this);
        startForeground(NOTIFICATION_ID, build(this, lastTitle, lastPlaying));
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        final String action = intent != null ? intent.getAction() : null;
        if (ACTION_STOP.equals(action)) {
            stopSelf();
            return START_NOT_STICKY;
        }
        if (ACTION_PREV.equals(action)) {
            PlayerBridge.previous();
        } else if (ACTION_NEXT.equals(action)) {
            PlayerBridge.next();
        } else if (ACTION_PLAY.equals(action)) {
            PlayerBridge.play();
        }
        // Feedback (glyph/title) arrives via updateState() from the poll.
        return START_NOT_STICKY;
    }

    @Override public void onDestroy() {
        running = false;
        super.onDestroy();
    }

    /** Mirror polled player state; starts the service on first playback. */
    public static void updateState(Context context, String title, boolean playing) {
        lastTitle = title == null ? "" : title;
        lastPlaying = playing;
        if (running) {
            NotificationManager nm =
                    (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
            nm.notify(NOTIFICATION_ID, build(context, lastTitle, lastPlaying));
        }
    }

    public static void start(Context context) {
        createChannel(context);
        Intent intent = new Intent(context, PlaybackNotificationService.class);
        if (Build.VERSION.SDK_INT >= 26) {
            context.startForegroundService(intent);
        } else {
            context.startService(intent);
        }
    }

    public static void stop(Context context) {
        context.stopService(new Intent(context, PlaybackNotificationService.class));
        running = false;
    }

    private static void createChannel(Context context) {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID, "MPCASU playback",
                    NotificationManager.IMPORTANCE_LOW);
            channel.setShowBadge(false);
            NotificationManager nm =
                    (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
            nm.createNotificationChannel(channel);
        }
    }

    private static Notification build(Context context, String title, boolean playing) {
        RemoteViews views = new RemoteViews(context.getPackageName(),
                R.layout.notification_mpcasu);
        views.setTextViewText(R.id.notif_title,
                title == null || title.isEmpty() ? "MPCASU" : title);
        views.setTextViewText(R.id.notif_state, context.getString(
                playing ? R.string.widget_state_playing : R.string.widget_state_paused));
        views.setTextViewText(R.id.notif_play, playing ? "⏸" : "▶");
        views.setOnClickPendingIntent(R.id.notif_prev,
                action(context, ACTION_PREV));
        views.setOnClickPendingIntent(R.id.notif_play,
                action(context, ACTION_PLAY));
        views.setOnClickPendingIntent(R.id.notif_next,
                action(context, ACTION_NEXT));

        Intent open = new Intent(context, MainActivity.class);
        PendingIntent contentIntent = PendingIntent.getActivity(
                context, 0, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        Notification.Builder builder =
                Build.VERSION.SDK_INT >= 26
                        ? new Notification.Builder(context, CHANNEL_ID)
                        : new Notification.Builder(context);
        builder.setSmallIcon(android.R.drawable.ic_media_play)
               .setContentIntent(contentIntent)
               .setOngoing(true)
               .setOnlyAlertOnce(true)
               .setContent(views)
               .setCustomContentView(views)
               .setCustomBigContentView(views);
        if (Build.VERSION.SDK_INT >= 24) {
            MediaSession.Token token = McasuMediaSession.token();
            if (token != null) {
                builder.setStyle(new Notification.DecoratedMediaCustomViewStyle()
                        .setMediaSession(token));
            }
        }
        return builder.build();
    }

    private static PendingIntent action(Context context, String action) {
        Intent intent = new Intent(context, PlaybackNotificationService.class)
                .setAction(action);
        return PendingIntent.getService(context, action.hashCode(), intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }
}
