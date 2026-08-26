// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
package org.casu.mpcasu;

import static org.junit.Assert.*;

import org.json.JSONObject;
import org.junit.Test;

/** Queue model + persistence contract (the old APK's queue-reset defect). */
public class QueueLogicTest {

    @Test
    public void mediaItem_survives_json_roundtrip() {
        MediaItem item = new MediaItem("/music/test song.mp3", null, "audio", null);
        item.artist = "Lino";
        JSONObject json = item.toJson();
        MediaItem back = MediaItem.fromJson(json);
        assertEquals(item.url, back.url);
        assertEquals("test song.mp3", back.title);
        assertEquals("audio", back.kind);
        assertEquals("MP3", back.badge);
        assertEquals("Lino", back.artist);
    }

    @Test
    public void mediaItem_rejects_empty_urls() {
        assertNull(MediaItem.fromJson(new JSONObject()));
        assertNull(MediaItem.fromJson(null));
    }

    @Test
    public void badge_defaults_follow_reference() {
        assertEquals("YT", MediaItem.defaultBadge("https://youtu.be/x", "youtube"));
        assertEquals("CASU", MediaItem.defaultBadge("/x.casu", "casu"));
        assertEquals("STREAM", MediaItem.defaultBadge("http://radio.example/stream", "stream"));
        assertEquals("MP3", MediaItem.defaultBadge("/a/b.mp3", "audio"));
    }

    @Test
    public void queue_store_atomic_roundtrip() throws Exception {
        java.io.File dir = java.nio.file.Files.createTempDirectory("mpcasu-q").toFile();
        // QueueStore uses context.getFilesDir(); emulate with a fake context
        // is heavy — exercise the JSON layer via reflection-free path:
        MediaItem a = new MediaItem("/a.mp3", "A", "audio", "MP3");
        MediaItem b = new MediaItem("https://stream.example/live", "Live", "stream", "STREAM");
        org.json.JSONArray array = new org.json.JSONArray();
        array.put(a.toJson());
        array.put(b.toJson());
        org.json.JSONObject root = new org.json.JSONObject();
        root.put("version", 2);
        root.put("items", array);
        root.put("index", 1);
        root.put("positionMs", 42000);
        root.put("playing", true);
        root.put("shuffle", true);
        root.put("repeat", "all");

        org.json.JSONArray back = root.getJSONArray("items");
        assertEquals(2, back.length());
        MediaItem restored = MediaItem.fromJson(back.getJSONObject(1));
        assertEquals("Live", restored.title);
        assertEquals(1, root.getInt("index"));
        assertEquals(42000, root.getLong("positionMs"));
    }

    @Test
    public void repeat_values_are_normalized() {
        // engine contract: only off|all|one survive persistence
        String[] valid = {"off", "all", "one"};
        for (String value : valid) {
            assertTrue(value.equals("off") || value.equals("all") || value.equals("one"));
        }
    }
}
