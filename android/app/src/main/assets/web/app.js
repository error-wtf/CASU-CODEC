"use strict";

/*
 * Compatibility reference for the retired Android WebView player.
 *
 * Android 5.0 uses the native Java/libVLC surface.  Keeping these two small
 * helpers documents and regression-tests the live-stream semantics shared by
 * the web players without shipping a second, inactive player implementation.
 */
function formatTime(seconds) {
  if(!Number.isFinite(seconds)) return "LIVE";
  seconds = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  const pad = (value) => String(value).padStart(2, "0");
  return hours ? `${hours}:${pad(minutes)}:${pad(remainder)}`
               : `${minutes}:${pad(remainder)}`;
}

function seekPosition(media) {
  return Number.isFinite(media.duration)?media.currentTime:0;
}
