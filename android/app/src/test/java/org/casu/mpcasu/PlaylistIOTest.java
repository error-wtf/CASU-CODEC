// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
package org.casu.mpcasu;

import static org.junit.Assert.*;

import org.junit.Test;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.List;

/** Playlist format fixtures — every format the Linux reference supports. */
public class PlaylistIOTest {

    @Test
    public void m3u_with_extinf_titles() throws Exception {
        String m3u = "#EXTM3U\n"
                + "#EXTINF:213,Artist — Song One\n"
                + "/music/one.mp3\n"
                + "#EXTINF:-1,Radio Live\n"
                + "https://radio.example/live\n";
        PlaylistIO.Playlist playlist = PlaylistIO.load("test.m3u", loc -> m3u);
        assertEquals(2, playlist.items.size());
        assertEquals("/music/one.mp3", playlist.items.get(0).url);
        assertEquals("Artist — Song One", playlist.items.get(0).title);
        assertEquals("https://radio.example/live", playlist.items.get(1).url);
    }

    @Test
    public void pls_ordered_by_number() throws Exception {
        String pls = "[playlist]\n"
                + "File2=https://b.example/2\n"
                + "Title2=Second\n"
                + "File1=/first.flac\n"
                + "Title1=First\n"
                + "NumberOfEntries=2\n"
                + "Version=2\n";
        PlaylistIO.Playlist playlist = PlaylistIO.load("mix.pls", loc -> pls);
        assertEquals(2, playlist.items.size());
        assertEquals("/first.flac", playlist.items.get(0).url);
        assertEquals("Second", playlist.items.get(1).title);
    }

    @Test
    public void xspf_tracks_with_titles() throws Exception {
        String xspf = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                + "<playlist version=\"1\" xmlns=\"http://xspf.org/ns/0/\">\n"
                + "  <trackList>\n"
                + "    <track><location>song%201.mp3</location><title>Song 1</title></track>\n"
                + "    <track><location>http://stream/x</location><title>S2</title></track>\n"
                + "  </trackList>\n</playlist>\n";
        PlaylistIO.Playlist playlist = PlaylistIO.load("list.xspf", loc -> xspf);
        assertEquals(2, playlist.items.size());
        assertEquals("Song 1", playlist.items.get(0).title);
    }

    @Test
    public void jspf_json_tracks() throws Exception {
        String jspf = "{\"playlist\":{"
                + "\"title\":\"My JSPF\","
                + "\"track\":[{\"location\":\"/a.mp3\",\"title\":\"A\"}]}}";
        PlaylistIO.Playlist playlist = PlaylistIO.load("list.jspf", loc -> jspf);
        assertEquals("My JSPF", playlist.name);
        assertEquals("/a.mp3", playlist.items.get(0).url);
    }

    @Test
    public void asx_refs() throws Exception {
        String asx = "<asx version=\"3.0\"><entry>"
                + "<ref href=\"http://stream.example/live\"/></entry></asx>";
        PlaylistIO.Playlist playlist = PlaylistIO.load("list.asx", loc -> asx);
        assertEquals(1, playlist.items.size());
        assertEquals("http://stream.example/live", playlist.items.get(0).url);
    }

    @Test
    public void wpl_smil_media() throws Exception {
        String wpl = "<smil><body><seq>"
                + "<media src=\"a.mp3\"/><media src=\"b.mp3\"/>"
                + "</seq></body></smil>";
        PlaylistIO.Playlist playlist = PlaylistIO.load("list.wpl", loc -> wpl);
        assertEquals(2, playlist.items.size());
    }

    @Test
    public void ram_lines() throws Exception {
        String ram = "# comment\nhttp://stream.example/one\nrtsp://cam.example/feed\n";
        PlaylistIO.Playlist playlist = PlaylistIO.load("list.ram", loc -> ram);
        assertEquals(2, playlist.items.size());
    }

    @Test
    public void casu_json_items() throws Exception {
        String json = "{\"type\":\"mpcasu-playlist\",\"items\":["
                + "{\"url\":\"/x.mp3\",\"title\":\"X\"},"
                + "{\"url\":\"https://y\",\"title\":\"Y\"}]}";
        PlaylistIO.Playlist playlist = PlaylistIO.load("list.json", loc -> json);
        assertEquals(2, playlist.items.size());
        assertEquals("X", playlist.items.get(0).title);
    }

    @Test
    public void relative_paths_resolve_against_playlist_base() throws Exception {
        String m3u = "#EXTM3U\n/music/local.mp3\n";
        PlaylistIO.Playlist playlist = PlaylistIO.load(
                "/home/user/lists/fav.m3u", loc -> m3u);
        // absolute entries stay absolute
        assertEquals("/music/local.mp3", playlist.items.get(0).url);

        String relative = "#EXTM3U\nsong.mp3\n";
        PlaylistIO.Playlist rel = PlaylistIO.load(
                "/home/user/lists/fav.m3u", loc -> relative);
        assertEquals("/home/user/lists/song.mp3", rel.items.get(0).url);
    }

    @Test
    public void file_uri_from_android_picker_is_read_and_resolved() throws Exception {
        java.io.File dir = Files.createTempDirectory("mpcasu-playlist").toFile();
        java.io.File playlistFile = new java.io.File(dir, "radio list.m3u");
        Files.write(playlistFile.toPath(),
                ("#EXTM3U\n#EXTINF:-1,Test Radio\nhttps://radio.example/live\n")
                        .getBytes(StandardCharsets.UTF_8));

        String location = "file://" + playlistFile.getAbsolutePath().replace(" ", "%20");
        PlaylistIO.Playlist playlist = PlaylistIO.load(location, PlaylistIO::fetchText);

        assertEquals(1, playlist.items.size());
        assertEquals("Test Radio", playlist.items.get(0).title);
        assertEquals("https://radio.example/live", playlist.items.get(0).url);
    }

    @Test
    public void remote_m3u8_is_a_stream_not_a_playlist_group() {
        assertFalse(PlaylistIO.isPlaylistPath("https://tv.example/live/index.m3u8"));
        assertTrue(PlaylistIO.isPlaylistPath("/music/favorites.m3u"));
        assertFalse(PlaylistIO.isPlaylistPath("https://radio.example/stream"));
    }

    @Test
    public void writers_roundtrip_through_parsers() throws Exception {
        MediaItem a = new MediaItem("/a.mp3", "A", "audio", "MP3");
        MediaItem b = new MediaItem("https://stream/x", "B", "stream", "STREAM");
        java.util.List<MediaItem> items = new java.util.ArrayList<>();
        items.add(a);
        items.add(b);

        PlaylistIO.Playlist m3u = PlaylistIO.load("x.m3u",
                loc -> PlaylistIO.writeM3u("x", items));
        assertEquals(2, m3u.items.size());

        PlaylistIO.Playlist pls = PlaylistIO.load("x.pls",
                loc -> PlaylistIO.writePls(items));
        assertEquals(2, pls.items.size());

        PlaylistIO.Playlist xspf = PlaylistIO.load("x.xspf",
                loc -> PlaylistIO.writeXspf("x", items));
        assertEquals(2, xspf.items.size());

        PlaylistIO.Playlist jspf = PlaylistIO.load("x.jspf",
                loc -> PlaylistIO.writeJspf("x", items));
        assertEquals(2, jspf.items.size());

        PlaylistIO.Playlist json = PlaylistIO.load("x.json",
                loc -> PlaylistIO.writeCasuJson("x", items));
        assertEquals(2, json.items.size());
    }
}
