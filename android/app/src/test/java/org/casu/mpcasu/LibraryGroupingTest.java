package org.casu.mpcasu;

import static org.junit.Assert.assertEquals;

import java.util.Arrays;
import java.util.List;
import org.junit.Test;

public class LibraryGroupingTest {
    private static Library.Track track(long id, String title, String artist, String album, String genre) {
        return new Library.Track(id, "content://audio/" + id, title, artist, album, genre, 1000, false);
    }

    @Test public void groupsAreDistinctSortedAndSelectable() {
        List<Library.Track> tracks = Arrays.asList(
                track(1, "Zulu", "Beta", "Second", "Rock"),
                track(2, "Alpha", "alpha", "First", "Jazz"),
                track(3, "Bravo", "Beta", "Second", "Rock"));
        assertEquals(Arrays.asList("alpha", "Beta"), Library.groups(tracks, "artists", ""));
        assertEquals(Arrays.asList("Bravo", "Zulu"), Arrays.asList(
                Library.tracksInGroup(tracks, "artists", "Beta").get(0).title,
                Library.tracksInGroup(tracks, "artists", "Beta").get(1).title));
        assertEquals(Arrays.asList("Jazz", "Rock"), Library.groups(tracks, "genres", ""));
    }

    @Test public void blankMetadataUsesUnknownGroup() {
        List<Library.Track> tracks = Arrays.asList(track(1, "Untitled", null, "", null));
        assertEquals(Arrays.asList("Unknown Album"), Library.groups(tracks, "albums", ""));
        assertEquals(1, Library.tracksInGroup(tracks, "genres", "Unknown Genre").size());
    }
}
