// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
package org.casu.mpcasu;

import static org.junit.Assert.*;

import org.junit.Test;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;

public class SubtitleAndYouTubeTest {

    @Test
    public void srt_parsing_with_cues() throws Exception {
        String srt = "1\n"
                + "00:00:01,000 --> 00:00:03,500\n"
                + "Hallo Welt\n"
                + "\n"
                + "2\n"
                + "00:00:05,000 --> 00:00:07,000\n"
                + "Zweite <i>Zeile</i>\n";
        SubtitleLoader loader = SubtitleLoader.load(
                new ByteArrayInputStream(srt.getBytes(StandardCharsets.UTF_8)));
        assertEquals(2, loader.count());
        assertEquals("Hallo Welt", loader.cueAt(1500));
        assertNull(loader.cueAt(4000));
        assertEquals("Zweite Zeile", loader.cueAt(6000));
    }

    @Test
    public void vtt_parsing() throws Exception {
        String vtt = "WEBVTT\n\n"
                + "00:00:01.000 --> 00:00:03.000\n"
                + "Line one\n";
        SubtitleLoader loader = SubtitleLoader.load(
                new ByteArrayInputStream(vtt.getBytes(StandardCharsets.UTF_8)));
        assertEquals(1, loader.count());
        assertEquals("Line one", loader.cueAt(2000));
    }

    @Test
    public void subtitle_offset_shifts_lookup() throws Exception {
        String srt = "1\n00:00:10,000 --> 00:00:12,000\nSpäter\n";
        SubtitleLoader loader = SubtitleLoader.load(
                new ByteArrayInputStream(srt.getBytes(StandardCharsets.UTF_8)));
        // positive offset = subtitle appears LATER: at video position P we
        // look up P - offset, so the 10 s cue becomes visible at 12 s.
        loader.setOffsetMs(2000);
        assertNull(loader.cueAt(11000));
        assertEquals("Später", loader.cueAt(12500));
    }

    @Test
    public void video_id_extraction() {
        assertEquals("dQw4w9WgXcQ", YouTubeClient.extractVideoId(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ"));
        assertEquals("dQw4w9WgXcQ", YouTubeClient.extractVideoId(
                "https://youtu.be/dQw4w9WgXcQ"));
        assertEquals("dQw4w9WgXcQ", YouTubeClient.extractVideoId(
                "https://www.youtube.com/shorts/dQw4w9WgXcQ"));
        assertEquals("dQw4w9WgXcQ", YouTubeClient.extractVideoId("dQw4w9WgXcQ"));
        assertNull(YouTubeClient.extractVideoId("https://example.com/nothing"));
    }

    @Test
    public void m3u_channel_parsing_with_groups() {
        String m3u = "#EXTM3U\n"
                + "#EXTINF:-1 tvg-id=\"ard.de\" group-title=\"DACH\",Das Erste\n"
                + "https://ard.example/live\n"
                + "#EXTINF:-1 group-title=\"Music\",Radio X\n"
                + "https://radiox.example/stream\n";
        List<EpgLoader.Channel> channels = EpgLoader.parseM3u(m3u);
        assertEquals(2, channels.size());
        assertEquals("Das Erste", channels.get(0).name);
        assertEquals("ard.de", channels.get(0).tvgId);
        assertEquals("DACH", channels.get(0).group);
        assertEquals("https://ard.example/live", channels.get(0).url);
        assertEquals("Music", channels.get(1).group);
    }

    @Test
    public void xmltv_now_lookup() {
        String xmltv = "<?xml version=\"1.0\"?><tv>"
                + "<programme channel=\"ard.de\" start=\"20260826000000 +0000\" "
                + "stop=\"20260826235900 +0000\"><title>Tagesschau</title></programme>"
                + "</tv>";
        List<EpgLoader.Programme> guide = EpgLoader.parseXmltv(xmltv);
        assertEquals(1, guide.size());
        EpgLoader.Channel channel = new EpgLoader.Channel();
        channel.name = "Das Erste";
        channel.tvgId = "ard.de";
        assertEquals("Tagesschau", EpgLoader.nowFor(guide, channel));
    }
}
