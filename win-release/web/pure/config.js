/* Pure-web player configuration.
 *
 * Default: zero backend — the player works fully static (local files,
 * direct streams, HLS, radio, YouTube via the IFrame Player API, CASU
 * native playback). Optional server endpoints are detected at startup and
 * enable extra features when present:
 *
 *   ping      — a tiny endpoint that answers {"ok":true} (e.g. php/ping.php)
 *   stream    — same-origin relay for cross-origin audio/video (CORS helper)
 *   catalog   — same-origin proxy to fetch remote M3U/XMLTV URLs
 *   search    — a resolver endpoint for YouTube search/resolve (needs yt-dlp
 *               on the server; not available on plain static hosts)
 *
 * Relative URLs are resolved against the page location. Set any of them to
 * null to force-disable that feature even if the endpoint exists.
 */
window.PUREWEB = window.PUREWEB || {
  /* Preload this same-origin M3U playlist on startup (fetched once, items are
   * appended to the queue). Set to null to disable. */
  playlist: "RADIO.m3u",
  /* Compact embed layout (no sidebar/queue, fits any iframe) — also enabled
   * by appending ?embed=1 to the player URL. */
  embed: false,
  endpoints: {
    ping: "php/ping.php",
    stream: "php/stream.php",
    catalog: "php/catalog.php",
    search: null,
  },
  youtube: {
    /* Keep using the YouTube IFrame Player API. If you have a resolver that
     * returns direct googlevideo URLs (yt-dlp), set search to that endpoint
     * and set resolveFirst to true to prefer direct playback. */
    resolveFirst: false,
  },
  hls: {
    liveSyncDuration: 6,
  },
};
