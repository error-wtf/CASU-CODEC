# RELEASE NOTES v6.0.0 — „One Field, Whole Playlists"

**Freigabe:** 2026-08-28 · **Vorgänger:** v5.0.0

v6.0.0 macht aus jedem YouTube-Feld einen Alle-Könner: Man kann **komplette
YouTube-Playlists** und/oder **mehrere einzelne YouTube-Video-URLs auf einmal**
(in ein Feld, durch Komma/Zeilenumbruch/Semikolon getrennt) in die Queue
werfen. Jedes Video wird ein **eigener Queue-Eintrag** — Shuffle, Repeat und
Next/Previous wirken damit pro Video, nicht pro Playlist.

Diese Parität gilt in **allen** Playern: Linux (Qt + Tk), Windows (Qt/C++),
Android (APK) sowie den Web-Frontends (web-casu + Pure Web).

## Für alle Player (Linux Qt/Tk, Windows, Android, Web)

1. **Mehrere Videos in ein Feld:** Komma-, Semikolon- oder zeilengetrennt
   `https://youtu.be/A, https://www.youtube.com/watch?v=B` ⇒ alle als einzelne
   Queue-Items, das erste wird abgespielt.
2. **Komplette Playlists direkt in die Queue:** Ein Playlist-Link
   (`.../playlist?list=PL…`) expandiert sofort in seine Videos (nicht mehr nur
   als eine Suchliste oder ein IFrame-Item). Shuffle/Repeat wirken pro Video.
3. **Gemischt:** Playlists UND einzelne Videos in beliebiger Reihenfolge in
   einer Eingabe — alles wird zu einer flachen Queue expandiert (Dedupe, max.
   100/200 Videos).
4. **Einzelne Video-URL bleibt unverändert:** Der bestehende 1-Klick-Weg
   (Video direkt spielen) bleibt identisch und wird nicht gestört.

## Implementierung (Referenz-Parser)

Gemeinsame Kernfunktion `casu/search.expand_youtube_input()` (Linux) bzw.
äquivalente Logik je Plattform:

- `split_youtube_input()` — Feld in Einzel-URLs zerlegen.
- `youtube_playlist_id()` — Playlist-`list=`-Wert extrahieren.
- Playlists expandieren über `yt-dlp --flat-playlist` / Innertube
  (`fetchPlaylist`, `playlistVideoRenderer`); einzelne URLs bleiben 1:1.

## Änderungen je Player

- **Qt (Referenz):** `SourcesView._open_typed` expandiert per Thread direkt in
  die Queue (`queueItemsRequested` → `_on_queue_items_requested`), spielt das
  erste Video, alle weiteren stehen in der Queue (Next/Shuffle/Repeat greifen).
- **Tk:** `_open_search_dialog.open_typed` + `_expand_youtube_input` — gleiche
  Queue-Semantik wie Qt.
- **web-casu:** Neuer Endpoint `POST /api/youtube-items` (`_youtube_items`)
  liefert flache Video-Liste; der URL-Dialog nutzt ihn bei Playlist/mehreren.
- **Pure Web:** Mehrere einzelne Video-URLs werden ohne Backend in getrennte
  Queue-Items zerlegt; Playlist-Link bleibt ein einzelnes embedbares Item.
- **Android:** `YouTubeClient.fetchPlaylist()` (Innertube browse) +
  `extractPlaylistId()`; der „Netzwerk-Stream hinzufügen"-Dialog ruft
  `expandYouTubeAdd()` → alle Videos in die Queue, erstes spielt.
- **Windows (C++):** `on_youtube_play` zerlegt das Feld in Einzel-URLs, expandiert
  Playlist-Links per `YtDlp().expand_playlist` und übergibt alles an `add_files`.

## Version

- Produktversion für alle Plattformen: **6.0.0**.
- Container-Format (`CASU_FORMAT_VERSION`) bleibt **3.0.0** — vollständig
  abwärtskompatibel; ältere Player akzeptieren neu geschriebene Dateien weiter.
- Linux: 4 DEBs (casu-codec, casu-converter, mpcasu, web-casu) + Pure-Web-ZIP.
- Windows: `MPCASU-Setup-6.0.0.exe` + `MPCASU-Windows-x86_64.zip`.
- Android: `mpcasu-6.0.0.apk` (versionCode 6).

## Geplant (Folge-Releases)

- **macOS**: `.dmg`-Build (siehe `ALL_RELEASE_V5/Mac-OS/`).
