package org.casu.mpcasu;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.*;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class MediaMetadataInstrumentedTest {
    @Test public void readsUnicodeTagsAndBoundedCoverAndPreservesRename() throws Exception {
        android.content.Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File file = new File(context.getCacheDir(), "metadata-test.mp3");
        try (InputStream input = InstrumentationRegistry.getInstrumentation().getContext().getAssets().open("tagged-cover.mp3");
             OutputStream output = new FileOutputStream(file)) {
            byte[] bytes = new byte[8192]; int n;
            while ((n = input.read(bytes)) != -1) output.write(bytes, 0, n);
        }
        MediaMetadata metadata = MediaMetadata.read(context, file.getAbsolutePath());
        assertEquals("Überall – Test", metadata.title);
        assertEquals("Casu Artist", metadata.artist);
        assertEquals("Cover Album", metadata.album);
        assertNotNull(metadata.artwork);
        assertTrue(metadata.artwork.getWidth() <= 640);
        MediaItem item = new MediaItem(file.getAbsolutePath(), "filename", "audio", "MP3");
        metadata.apply(item);
        assertEquals(metadata.title, item.title);
        item.title = "Custom title";
        metadata.apply(item);
        assertEquals("Custom title", item.title);
        assertEquals(metadata.album, MediaItem.fromJson(item.toJson()).album);
    }
    @Test public void importsDesktopJsonAndCueRelativeToPlaylist() throws Exception {
        assertEquals("/music/überall.mp3", PlaylistIO.load("/music/mix.json", p -> "{\"version\":1,\"items\":[\"überall.mp3\"]}").items.get(0).url);
        assertEquals("/music/two words.mp3", PlaylistIO.load("/music/mix.cue", p -> "FILE \"two words.mp3\" MP3\n TRACK 01 AUDIO").items.get(0).url);
    }
}
