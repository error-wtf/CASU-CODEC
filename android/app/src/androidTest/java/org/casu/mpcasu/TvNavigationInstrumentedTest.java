package org.casu.mpcasu;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.view.View;
import android.view.ViewGroup;
import android.view.KeyEvent;
import android.widget.ListView;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.json.JSONArray;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class TvNavigationInstrumentedTest {
    private static View find(View v, String description) {
        if(description.equals(String.valueOf(v.getContentDescription())))return v;
        if(v instanceof ViewGroup){ViewGroup g=(ViewGroup)v;for(int i=0;i<g.getChildCount();i++){View found=find(g.getChildAt(i),description);if(found!=null)return found;}}
        return null;
    }
    private static ListView list(View v) {
        if(v instanceof ListView)return (ListView)v;
        if(v instanceof ViewGroup){ViewGroup g=(ViewGroup)v;for(int i=0;i<g.getChildCount();i++){ListView found=list(g.getChildAt(i));if(found!=null)return found;}}
        return null;
    }
    @Test public void remoteCanEnterIptvSelectChannelsAndReturn() throws Exception {
        Instrumentation instrumentation=InstrumentationRegistry.getInstrumentation();
        android.content.Context context=instrumentation.getTargetContext();
        JSONArray rows=new JSONArray();
        for(int i=0;i<3;i++){MediaItem item=new MediaItem("https://example.org/"+i,"Channel "+i,"stream","IPTV");item.playlist="News";rows.put(item.toJson());}
        context.getSharedPreferences("iptv",0).edit().putString("channels",rows.toString()).commit();
        Activity main=instrumentation.startActivitySync(new Intent(context,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        try {
            instrumentation.waitForIdleSync();
            View tab=find(main.getWindow().getDecorView(),"IPTV");assertNotNull(tab);
            instrumentation.runOnMainSync(()->assertTrue(tab.requestFocus()));
            instrumentation.sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_CENTER);
            instrumentation.waitForIdleSync();
            java.lang.reflect.Field f=MainActivity.class.getDeclaredField("iptvView");f.setAccessible(true);
            IptvView iptv=(IptvView)f.get(main);assertTrue(iptv.isShown());
            ListView channels=list(iptv);assertNotNull(channels);assertEquals(3,channels.getCount());
            instrumentation.runOnMainSync(()->{channels.requestFocus();channels.setSelection(0);});
            instrumentation.waitForIdleSync();
            instrumentation.sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_DOWN);
            instrumentation.waitForIdleSync();assertEquals(1,channels.getSelectedItemPosition());
            java.lang.reflect.Field ringField=MainActivity.class.getDeclaredField("remoteFocus");ringField.setAccessible(true);
            View ring=(View)ringField.get(main);assertTrue(ring.isShown());
            java.lang.reflect.Field bounds=RemoteFocus.class.getDeclaredField("bounds");bounds.setAccessible(true);
            assertFalse(((android.graphics.Rect)bounds.get(ring)).isEmpty());
            instrumentation.sendKeyDownUpSync(KeyEvent.KEYCODE_BACK);
            instrumentation.waitForIdleSync();assertFalse(iptv.isShown());assertFalse(main.isFinishing());
        } finally {instrumentation.runOnMainSync(main::finish);}
    }
    @Test public void m3uGroupNamesSurviveResolution() throws Exception {
        PlaylistIO.Playlist p=PlaylistIO.load("https://example.org/list.m3u", source->"#EXTM3U\n#EXTINF:-1 group-title=\"News\",World\nhttps://example.org/live.m3u8\n");
        assertEquals("News",p.items.get(0).group);assertEquals("World",p.items.get(0).title);
    }
}
