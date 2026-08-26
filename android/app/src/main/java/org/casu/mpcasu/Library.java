// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// SPDX-FileCopyrightText: 2026 Lino Casu
package org.casu.mpcasu;

import android.content.ContentUris;
import android.content.Context;
import android.net.Uri;
import android.provider.MediaStore;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Media library backed by MediaStore (audio + video) with search,
 *  grouping fields and JSON-persisted favorites — the Android equivalent
 *  of the Linux reference's MediaLibrary. */
public final class Library {

    public static final class Track {
        public final long id;
        public final String uri;      // content:// URI (directly playable)
        public final String title;
        public final String artist;
        public final String album;
        public final String genre;
        public final long durationMs;
        public final boolean video;

        Track(long id, String uri, String title, String artist, String album,
              String genre, long durationMs, boolean video) {
            this.id = id;
            this.uri = uri;
            this.title = title;
            this.artist = artist;
            this.album = album;
            this.genre = genre;
            this.durationMs = durationMs;
            this.video = video;
        }

        public MediaItem toItem() {
            MediaItem item = new MediaItem(uri, title, video ? "video" : "audio",
                    video ? "VIDEO" : "AUDIO");
            item.artist = artist != null && !artist.isEmpty() ? artist : null;
            return item;
        }
    }

    private final Context context;
    private Set<String> favorites = new HashSet<>();
    private final File favoritesFile;

    public Library(Context context) {
        this.context = context.getApplicationContext();
        favoritesFile = new File(this.context.getFilesDir(), "favorites.json");
        loadFavorites();
    }

    public List<Track> query(String search, boolean videoOnly, boolean audioOnly) {
        List<Track> out = new ArrayList<>();
        out.addAll(queryStore(false, search, videoOnly));
        if (!audioOnly) out.addAll(queryStore(true, search, false));
        return out;
    }

    private List<Track> queryStore(boolean video, String search, boolean skip) {
        List<Track> out = new ArrayList<>();
        if (skip) return out;
        try {
            Uri collection = video
                    ? MediaStore.Video.Media.EXTERNAL_CONTENT_URI
                    : MediaStore.Audio.Media.EXTERNAL_CONTENT_URI;
            String[] projection = video
                    ? new String[]{MediaStore.Video.Media._ID,
                       MediaStore.Video.Media.TITLE, MediaStore.Video.Media.DURATION,
                       MediaStore.Video.Media.BUCKET_DISPLAY_NAME}
                    : new String[]{MediaStore.Audio.Media._ID,
                       MediaStore.Audio.Media.TITLE, MediaStore.Audio.Media.ARTIST,
                       MediaStore.Audio.Media.ALBUM, MediaStore.Audio.Media.DURATION};
            String selection = null;
            String[] args = null;
            if (search != null && !search.isEmpty()) {
                selection = video
                        ? MediaStore.Video.Media.TITLE + " LIKE ?"
                        : MediaStore.Audio.Media.TITLE + " LIKE ? OR "
                          + MediaStore.Audio.Media.ARTIST + " LIKE ? OR "
                          + MediaStore.Audio.Media.ALBUM + " LIKE ?";
                String like = "%" + search + "%";
                args = video ? new String[]{like}
                        : new String[]{like, like, like};
            }
            try (android.database.Cursor cursor = context.getContentResolver().query(
                    collection, projection, selection, args,
                    MediaStore.MediaColumns.DATE_ADDED + " DESC")) {
                if (cursor == null) return out;
                while (cursor.moveToNext()) {
                    long id = cursor.getLong(0);
                    String title = cursor.getString(1);
                    String artist = !video ? cursor.getString(2) : null;
                    String album = !video ? cursor.getString(3) : null;
                    long duration = cursor.getLong(video ? 2 : 4);
                    if (duration <= 0 && video) duration = cursor.getLong(2);
                    String uri = ContentUris.withAppendedId(collection, id).toString();
                    out.add(new Track(id, uri, title == null || title.isEmpty()
                            ? MediaItem.fallbackTitle(uri) : title,
                            artist, album, null, duration, video));
                }
            }
        } catch (Exception ignored) {
            // MediaStore unavailable (weird profiles): library stays empty.
        }
        return out;
    }

    // ------------------------------------------------------------------ favorites

    public boolean isFavorite(String uri) {
        return favorites.contains(uri);
    }

    public void toggleFavorite(String uri) {
        if (favorites.contains(uri)) favorites.remove(uri);
        else favorites.add(uri);
        saveFavorites();
    }

    public List<Track> filterFavorites(List<Track> tracks) {
        List<Track> out = new ArrayList<>();
        for (Track track : tracks) {
            if (favorites.contains(track.uri)) out.add(track);
        }
        return out;
    }

    private void loadFavorites() {
        try (FileInputStream in = new FileInputStream(favoritesFile)) {
            byte[] buf = new byte[(int) favoritesFile.length()];
            int read = in.read(buf);
            JSONObject root = new JSONObject(new String(buf, 0, Math.max(0, read)));
            JSONArray array = root.optJSONArray("favorites");
            if (array != null) {
                for (int i = 0; i < array.length(); i++) {
                    String value = array.optString(i, "");
                    if (!value.isEmpty()) favorites.add(value);
                }
            }
        } catch (Exception ignored) {
        }
    }

    private void saveFavorites() {
        try {
            JSONObject root = new JSONObject();
            JSONArray array = new JSONArray();
            for (String value : favorites) array.put(value);
            root.put("favorites", array);
            File tmp = new File(favoritesFile.getParentFile(), favoritesFile.getName() + ".tmp");
            try (FileOutputStream out = new FileOutputStream(tmp)) {
                out.write(root.toString().getBytes());
            }
            if (!tmp.renameTo(favoritesFile)) {
                try (FileOutputStream out = new FileOutputStream(favoritesFile)) {
                    out.write(root.toString().getBytes());
                }
                tmp.delete();
            }
        } catch (Exception ignored) {
        }
    }
}
