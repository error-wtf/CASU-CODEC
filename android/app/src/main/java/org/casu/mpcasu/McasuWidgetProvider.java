package org.casu.mpcasu;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

/**
 * MPCASU home-screen widget (4×1): current title + play/pause state and
 * ⏮ ▶/⏸ ⏭ transport buttons. Buttons arrive here as broadcasts; they are
 * forwarded into the live WebView (same JS surface as the desktop web
 * player: next(±1) / #play click). If no player is alive the tap simply
 * launches MainActivity. Playback state flows back through PlayerBridge's
 * poll loop → {@link #pushState}.
 */
public class McasuWidgetProvider extends AppWidgetProvider {

    public static final String ACTION_PREV = "org.casu.mpcasu.WIDGET_PREV";
    public static final String ACTION_PLAY = "org.casu.mpcasu.WIDGET_PLAY";
    public static final String ACTION_NEXT = "org.casu.mpcasu.WIDGET_NEXT";

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] appWidgetIds) {
        RemoteViews views = buildViews(context, PlayerBridge.title(), PlayerBridge.playing());
        for (int id : appWidgetIds) manager.updateAppWidget(id, views);
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        if (ACTION_PREV.equals(action) || ACTION_PLAY.equals(action) || ACTION_NEXT.equals(action)) {
            if (!PlayerBridge.dispatch(action)) {
                // No live player: open the app so the user lands in control.
                Intent open = new Intent(context, MainActivity.class)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(open);
            }
            return;
        }
        super.onReceive(context, intent);
    }

    /** Push title/playing state into every placed widget instance. */
    public static void pushState(Context context, String title, boolean playing) {
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        if (manager == null) return;
        ComponentName who = new ComponentName(context, McasuWidgetProvider.class);
        int[] ids = manager.getAppWidgetIds(who);
        if (ids == null || ids.length == 0) return;
        RemoteViews views = buildViews(context, title, playing);
        manager.updateAppWidget(who, views);
    }

    private static RemoteViews buildViews(Context context, String title, boolean playing) {
        RemoteViews views = new RemoteViews(context.getPackageName(),
                R.layout.widget_mpcasu);
        boolean idle = title == null || title.isEmpty();
        views.setTextViewText(R.id.widget_title,
                idle ? context.getString(R.string.widget_idle_title) : title);
        views.setTextViewText(R.id.widget_state, context.getString(
                playing ? R.string.widget_state_playing : R.string.widget_state_paused));
        views.setTextViewText(R.id.widget_play, playing ? "⏸" : "▶");
        views.setOnClickPendingIntent(R.id.widget_prev,
                pending(context, ACTION_PREV));
        views.setOnClickPendingIntent(R.id.widget_play,
                pending(context, ACTION_PLAY));
        views.setOnClickPendingIntent(R.id.widget_next,
                pending(context, ACTION_NEXT));
        return views;
    }

    private static PendingIntent pending(Context context, String action) {
        Intent intent = new Intent(context, McasuWidgetProvider.class).setAction(action);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE;
        return PendingIntent.getBroadcast(context, action.hashCode(), intent, flags);
    }
}
