"use strict";
/* WEB CASU Player — pure web build.
 * Runs on any static host: no Python/yt-dlp backend required.
 * Optional server endpoints (config.js) add CORS-friendly stream/catalog
 * helpers; without them everything except cross-origin visualizer still works.
 */

// ---------------------------------------------------------------------------
// small helpers
// ---------------------------------------------------------------------------
const $ = (id) => document.getElementById(String(id).replace(/^#/, ""));
const media = $("media"), youtubeFrame = $("youtube"),
      nativeCanvas = $("native-canvas"), queueNode = $("queue");

const CFG = (window.PUREWEB || {}).endpoints || {};
const YT_ORIGIN = "https://www.youtube-nocookie.com";
const NETWORK_SCHEMES = new Set(["http:", "https:"]);
const MAX_PLAYLIST_BYTES = 8 * 1024 * 1024;
const MAX_PLAYLIST_ENTRIES = 4096;
const MAX_PLAYLIST_LINE = 8192;
const MAX_XMLTV_BYTES = 32 * 1024 * 1024;
const MAX_XMLTV_CHANNELS = 2048;
const MAX_XMLTV_PROGRAMMES = 200000;
const MAX_EPG_TEXT = 1024;

function formatTime(value) {
  value = Math.max(0, Math.floor(Number(value) || 0));
  const h = Math.floor(value / 3600), m = Math.floor((value % 3600) / 60), s = value % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return (h ? pad(h) + ":" : "") + pad(m) + ":" + pad(s);
}

function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("show"), 2600);
}

function youtubeId(value) {
  try {
    const u = new URL(value), host = u.hostname.toLowerCase().replace(/\.$/, "");
    let id = null;
    if (host === "youtu.be" || host.endsWith(".youtu.be")) id = u.pathname.slice(1).split("/")[0];
    if (host === "youtube.com" || host.endsWith(".youtube.com"))
      id = u.searchParams.get("v") || (u.pathname.match(/^\/(?:shorts|embed)\/([^/?#]+)/) || [])[1] || null;
    return /^[A-Za-z0-9_-]{11}$/.test(id || "") ? id : null;
  } catch (error) { return null; }
}

function youtubeList(value) {
  try { return new URL(value).searchParams.get("list") || ""; }
  catch (error) { return ""; }
}

function networkUrl(value) {
  const url = new URL(value);
  if (!NETWORK_SCHEMES.has(url.protocol) || !url.hostname)
    throw Error("Use an explicit supported network URL");
  return url.href;
}

function mimeFor(name) {
  const ext = (name || "").toLowerCase().split(".").pop();
  return ({ aac: "audio/aac", aiff: "audio/aiff", aif: "audio/aiff", alac: "audio/mp4",
    flac: "audio/flac", m4a: "audio/mp4", mp2: "audio/mpeg", mp3: "audio/mpeg",
    oga: "audio/ogg", ogg: "audio/ogg", opus: "audio/ogg", wav: "audio/wav",
    wma: "audio/x-ms-wma", avi: "video/x-msvideo", flv: "video/x-flv",
    m2ts: "video/mp2t", m4v: "video/mp4", mkv: "video/x-matroska",
    mov: "video/quicktime", mp4: "video/mp4", mpeg: "video/mpeg", mpg: "video/mpeg",
    mts: "video/mp2t", ogv: "video/ogg", ts: "video/mp2t", vob: "video/mpeg",
    webm: "video/webm", wmv: "video/x-ms-wmv" }[ext] || "application/octet-stream");
}

function itemLabel(item) {
  return item.title || item.file?.name || (item.url ? new URL(item.url).hostname : "item");
}

function isHlsUrl(url) {
  return /\.m3u8([?#].*)?$/i.test(String(url || "").split("?")[0]) ||
         /\.m3u8/i.test(String(url || ""));
}

// ---------------------------------------------------------------------------
// state + views
// ---------------------------------------------------------------------------
const state = {
  items: [], index: -1, shuffle: false, repeat: "off",
  objectUrls: new Set(), selected: -1, native: null, fallbacking: false,
  playbackToken: 0, youtubeState: -1, youtubeTime: 0, youtubeDuration: 0,
  epgNames: new Map(), programmes: [], abStart: null, abEnd: null, abToken: -1,
  rateIndex: 2, view: "now", expanded: new Set(),
  multi: new Set(),
  backend: { stream: false, catalog: false, search: false },
  viz: true, hls: null, vizCtx: null, vizAnalyser: null, vizRaf: 0,
  suppressAutoplay: false,
};

const VIEWS = {
  now: () => true,
  files: (item) => !!item.file,
  streams: (item) => !item.file && !!(item.url) && !item.kind?.startsWith("casu")
      && item.kind !== "youtube" && item.kind !== "spotify",
  playlists: (item) => !!(item.epgId || item.group || item.logo),
  iptv: (item) => !!item.epgId,
  youtube: (item) => item.kind === "youtube",
  spotify: (item) => item.kind === "spotify",
  casu: (item) => (item.kind || "").startsWith("casu"),
};

function markNav() {
  document.querySelectorAll(".nav[data-view]").forEach((node) =>
    node.classList.toggle("active", node.dataset.view === state.view));
}
function setView(name) {
  if (!VIEWS[name]) name = "now";
  state.view = name;
  markNav();
  $("view-title").textContent = {
    now: "NOW PLAYING", files: "LOCAL FILES", streams: "WEB & STREAMS",
    playlists: "PLAYLISTS", iptv: "IPTV", youtube: "YOUTUBE",
    spotify: "SPOTIFY", casu: "CASU FILES",
  }[name];
  document.querySelector(".app-shell").classList.remove("show-queue");
  renderQueue();
}

// ---------------------------------------------------------------------------
// queue rendering
// ---------------------------------------------------------------------------
function renderQueue() {
  const query = $("search").value.trim().toLowerCase();
  const viewFilter = VIEWS[state.view] || VIEWS.now;
  queueNode.replaceChildren();
  let shown = 0, lastPlaylist = null;
  state.items.forEach((item, index) => {
    if (!viewFilter(item)) return;
    if (query && !itemLabel(item).toLowerCase().includes(query)) return;
    shown++;
    if (item.playlist && !query) {
      if (lastPlaylist !== item.playlist) {
        lastPlaylist = item.playlist;
        const open = state.expanded.has(item.playlist);
        const count = state.items.filter((e) => e.playlist === item.playlist && viewFilter(e)).length;
        const header = document.createElement("li");
        header.className = "queue-group" + (open ? " open" : "");
        header.dataset.group = item.playlist;
        header.innerHTML = `<span class="thumb">☷</span><span class="track"><strong></strong><small></small></span>`;
        header.querySelector("strong").textContent = item.playlist;
        header.querySelector("small").textContent =
          `PLAYLIST · ${count} entries · click to ${open ? "collapse" : "expand"}`;
        header.onclick = () => {
          open ? state.expanded.delete(item.playlist) : state.expanded.add(item.playlist);
          renderQueue();
        };
        const tools = document.createElement("span");
        tools.className = "item-tools";
        const play = document.createElement("button");
        play.type = "button"; play.textContent = "▶"; play.title = "Play playlist from the start";
        play.onclick = (e) => { e.stopPropagation(); playPlaylistGroup(item.playlist); };
        const up = document.createElement("button");
        up.type = "button"; up.textContent = "↑"; up.title = "Move playlist up";
        up.onclick = (e) => { e.stopPropagation(); movePlaylistGroup(item.playlist, -1); };
        const down = document.createElement("button");
        down.type = "button"; down.textContent = "↓"; down.title = "Move playlist down";
        down.onclick = (e) => { e.stopPropagation(); movePlaylistGroup(item.playlist, 1); };
        const remove = document.createElement("button");
        remove.type = "button"; remove.textContent = "×"; remove.title = "Remove playlist (entries stay removed from the queue)";
        remove.onclick = (e) => { e.stopPropagation(); removePlaylistGroup(item.playlist); };
        tools.append(play, up, down, remove);
        header.append(tools);
        queueNode.append(header);
      }
      if (!state.expanded.has(item.playlist)) return;
    } else { lastPlaylist = null; }
    const li = document.createElement("li");
    li.dataset.index = index;
    const multi = state.multi.has(item);
    li.className = (index === state.index ? "active" : "") + (multi ? " multi" : "");
    li.setAttribute("aria-current", index === state.index ? "true" : "false");
    li.innerHTML =
      `<span class="thumb">${item.kind === "audio" ? "♫" : item.kind?.startsWith("casu") ? "◆" : "▶"}</span>` +
      `<span class="track"><strong></strong><small></small></span>`;
    li.querySelector("strong").textContent = itemLabel(item);
    li.querySelector("small").textContent = (item.kind || "media").toUpperCase() + (item.playlist ? " · " + item.playlist : "");
    const tools = document.createElement("span");
    tools.className = "item-tools";
    const rename = document.createElement("button");
    rename.type = "button"; rename.textContent = "✎"; rename.title = "Rename";
    rename.onclick = (e) => { e.stopPropagation(); renameIndex(index); };
    const remove = document.createElement("button");
    remove.type = "button"; remove.textContent = "×"; remove.title = "Remove";
    remove.onclick = (e) => { e.stopPropagation(); removeIndex(index); };
    tools.append(rename, remove);
    li.append(tools);
    li.onclick = (event) => {
      if (event.ctrlKey || event.shiftKey) {
        multi ? state.multi.delete(item) : state.multi.add(item);
        renderQueue();
        return;
      }
      playIndex(index);
    };
    li.onfocus = () => { state.selected = index; };
    li.onkeydown = (event) => { if (event.key === "Enter") { event.preventDefault(); playIndex(index); } };
    li.tabIndex = 0;
    queueNode.append(li);
    if (index === state.index) li.scrollIntoView({ block: "nearest" });
  });
  $("queue-summary").textContent =
    `${shown}/${state.items.length} item${state.items.length === 1 ? "" : "s"}` +
    (state.multi.size ? ` · ${state.multi.size} marked (Esc clears)` : "");
}

function addItem(item) {
  state.items.push(item);
  if (!(VIEWS[state.view] || VIEWS.now)(item)) { state.view = "now"; markNav(); }
  renderQueue();
  if (state.index < 0 && !state.suppressAutoplay) playIndex(0);
  return item;
}

function renameIndex(index) {
  const item = state.items[index];
  if (!item) return;
  const value = prompt("Rename", itemLabel(item));
  if (value !== null && value.trim()) { item.title = value.trim(); renderQueue(); persistQueue(); }
}

function removeIndex(index) {
  if (index < 0 || index >= state.items.length) return;
  const item = state.items[index];
  releaseItem(item);
  state.items.splice(index, 1);
  if (state.index === index) { state.index = -1; stopAll(); }
  if (state.index > index) state.index--;
  renderQueue();
  persistQueue();
}

function releaseItem(item) {
  item?.native2?.close();
  const urls = [item?.url, ...(item?.trackUrls || [])];
  for (const url of urls) if (state.objectUrls.has(url)) { URL.revokeObjectURL(url); state.objectUrls.delete(url); }
}

// ---------------------------------------------------------------------------
// queue groups & selection (non-destructive playlist groups)
//
// A playlist stays visible as ONE group row (header). Playback walks the flat
// items (logical sequence), so collapsed groups and loose files still play.
// Rows = group blocks or loose items; multi-selection (Ctrl/Shift) moves rows
// as a block; entries can be sorted INTO a playlist group and taken OUT.
// ---------------------------------------------------------------------------
function rowOf(index) {
  const item = state.items[index];
  if (!item) return null;
  if (item.playlist) {
    let start = index;
    while (start > 0 && state.items[start - 1]?.playlist === item.playlist) start--;
    let end = index;
    while (end + 1 < state.items.length && state.items[end + 1]?.playlist === item.playlist) end++;
    return { start, end, group: true, name: item.playlist };
  }
  return { start: index, end: index, group: false };
}

function selectedRows() {
  const rows = [];
  if (state.multi.size) {
    for (let i = 0; i < state.items.length; i++) {
      if (!state.multi.has(state.items[i])) continue;
      const row = rowOf(i);
      if (!rows.some((r) => i >= r.start && i <= r.end)) rows.push(row);
    }
    return rows;
  }
  const sel = state.selected >= 0 ? state.selected : state.index;
  return sel >= 0 ? [rowOf(sel)] : [];
}

function moveRowSegment(start, delta) {
  const row = rowOf(start);
  if (!row) return;
  if (delta > 0) {
    if (row.end + 1 >= state.items.length) return;
    const len = row.end - row.start + 1;
    const removed = state.items.splice(row.start, len);
    const below = rowOf(row.start);
    state.items.splice(below.end + 1, 0, ...removed);
  } else {
    if (row.start <= 0) return;
    const len = row.end - row.start + 1;
    const removed = state.items.splice(row.start, len);
    const above = rowOf(row.start - 1);
    state.items.splice(above.start, 0, ...removed);
  }
}

function moveRows(delta) {
  const rows = selectedRows();
  if (!rows.length) return;
  const playing = state.items[state.index];
  const starts = rows.map((r) => r.start).sort((a, b) => a - b);
  if (delta > 0) {
    for (let i = starts.length - 1; i >= 0; i--) moveRowSegment(starts[i], 1);
  } else {
    for (let i = 0; i < starts.length; i++) moveRowSegment(starts[i], -1);
  }
  state.index = playing ? state.items.indexOf(playing) : -1;
  if (state.selected >= 0) state.selected = playing ? state.items.indexOf(playing) : -1;
  renderQueue();
  persistQueue();
}

function removeRows() {
  const rows = selectedRows();
  if (!rows.length) return;
  const playing = state.items[state.index];
  const doomed = new Set();
  for (const row of rows) for (let i = row.start; i <= row.end; i++) doomed.add(state.items[i]);
  state.items = state.items.filter((item) => !doomed.has(item));
  state.multi = new Set(state.items.filter((item) => state.multi.has(item)));
  state.index = playing && doomed.has(playing) ? -1 : (playing ? state.items.indexOf(playing) : -1);
  if (state.index < 0) { stopAll(); }
  renderQueue();
  persistQueue();
}

function movePlaylistGroup(name, delta) {
  const item = state.items.find((e) => e.playlist === name);
  if (!item) return;
  const row = rowOf(state.items.indexOf(item));
  moveRowSegment(row.start, delta);
  const playing = state.items[state.index];
  state.index = playing ? state.items.indexOf(playing) : -1;
  renderQueue();
  persistQueue();
}

function removePlaylistGroup(name) {
  const playing = state.items[state.index];
  const members = state.items.filter((e) => e.playlist === name);
  if (!members.length) return;
  state.items = state.items.filter((e) => e.playlist !== name);
  members.forEach(releaseItem);
  state.multi = new Set(state.items.filter((item) => state.multi.has(item)));
  state.index = playing && playing.playlist === name ? -1 : (playing ? state.items.indexOf(playing) : -1);
  if (state.index < 0) { stopAll(); }
  renderQueue();
  persistQueue();
}

function playPlaylistGroup(name) {
  const index = state.items.findIndex((e) => e.playlist === name);
  if (index >= 0) playIndex(index);
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.multi.size) {
    state.multi.clear();
    renderQueue();
    persistQueue();
  }
});

// Sort the selected rows INTO a playlist ("rein"): a new name creates a new
// group; an existing group appends the selection (deduplicated) and moves the
// items out of any other group they belonged to.
function saveSelectionToPlaylist() {
  const rows = selectedRows();
  if (!rows.length) { toast("Select rows (Ctrl/Shift click) first, or right-click a row"); return; }
  const targets = [];
  for (const row of rows) for (let i = row.start; i <= row.end; i++) targets.push(state.items[i]);
  const existing = [...new Set(state.items.map((e) => e.playlist).filter(Boolean))];
  const hint = existing.length
    ? `Existing playlists: ${existing.join(", ")}. New name = new group, existing name = append into it.`
    : "New playlist name — the selected items become its visible group.";
  const name = prompt(hint, existing.length ? existing[0] : "New playlist");
  if (name === null || !name.trim()) return;
  const groupName = name.trim();
  const playing = state.items[state.index];
  const members = state.items.filter((e) => e.playlist === groupName);
  if (members.length) {
    const seen = new Set(members);
    const toInsert = targets.filter((t) => !seen.has(t));
    if (!toInsert.length) { toast("Selection is already inside that playlist"); return; }
    state.items = state.items.filter((e) => !toInsert.includes(e));
    const last = state.items.lastIndexOf(members[members.length - 1]);
    for (const it of toInsert) it.playlist = groupName;
    state.items.splice(last + 1, 0, ...toInsert);
    state.index = playing ? state.items.indexOf(playing) : -1;
    state.expanded.add(groupName);
    renderQueue();
    persistQueue();
    toast(`${toInsert.length} item(s) sorted into “${groupName}”`);
    return;
  }
  for (const it of targets) it.playlist = groupName;
  const removed = targets.filter((t) => state.items.includes(t));
  state.items = state.items.filter((t) => !targets.includes(t));
  state.items.push(...removed);
  state.index = playing ? state.items.indexOf(playing) : -1;
  state.expanded.add(groupName);
  renderQueue();
  persistQueue();
  toast(`Playlist “${groupName}” created with ${removed.length} item(s)`);
}

// Take entries OUT of their playlist ("raus"): they stay in the queue as
// loose items, grouped no more.
function removeFromPlaylist(items) {
  const playing = state.items[state.index];
  let count = 0;
  for (const it of items) if (it?.playlist) { it.playlist = ""; count++; }
  if (!count) { toast("No playlist entry selected"); return; }
  state.index = playing ? state.items.indexOf(playing) : -1;
  renderQueue();
  persistQueue();
  toast(`${count} item(s) removed from their playlist (stay in the queue)`);
}

function showQueueMenu(event, item, groupName) {
  event.preventDefault();
  const menu = document.createElement("div");
  menu.className = "queue-menu";
  const add = (label, action) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.onclick = () => { menu.remove(); action(); };
    menu.append(button);
    return button;
  };
  if (groupName) {
    add("▶ Play playlist", () => playPlaylistGroup(groupName));
    if (state.expanded.has(groupName)) add("Collapse playlist", () => { state.expanded.delete(groupName); renderQueue(); });
    else add("Expand playlist", () => { state.expanded.add(groupName); renderQueue(); });
    add("↑ Move playlist up", () => movePlaylistGroup(groupName, -1));
    add("↓ Move playlist down", () => movePlaylistGroup(groupName, 1));
    add("Remove playlist from queue", () => removePlaylistGroup(groupName));
    add("Remove ALL entries from playlist (keep in queue)", () =>
      removeFromPlaylist(state.items.filter((e) => e.playlist === groupName)));
  } else if (item) {
    const index = state.items.indexOf(item);
    add("▶ Play", () => playIndex(index));
    add("↑ Move up", () => moveRows(-1));
    add("↓ Move down", () => moveRows(1));
    add("Remove from queue", () => removeRows());
    add("Save selection to playlist…", saveSelectionToPlaylist);
    if (item.playlist) add("Remove from playlist", () => removeFromPlaylist([item]));
  }
  menu.style.left = event.clientX + "px";
  menu.style.top = event.clientY + "px";
  document.body.append(menu);
  const close = (e) => { if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener("click", close, true); } };
  setTimeout(() => document.addEventListener("click", close, true), 0);
}
queueNode.addEventListener("contextmenu", (event) => {
  const li = event.target.closest("li");
  if (!li) return;
  if (li.dataset.group) showQueueMenu(event, null, li.dataset.group);
  else if (li.dataset.index !== undefined) showQueueMenu(event, state.items[Number(li.dataset.index)]);
});

// ---------------------------------------------------------------------------
// local files
// ---------------------------------------------------------------------------
async function digestHex(buffer) {
  const hash = await crypto.subtle.digest("SHA-256", buffer);
  return [...new Uint8Array(hash)].map((v) => v.toString(16).padStart(2, "0")).join("");
}
function littleU64(view, offset) {
  const value = view.getBigUint64(offset, true);
  if (value > BigInt(Number.MAX_SAFE_INTEGER)) throw Error("CASU length exceeds browser integer range");
  return Number(value);
}

async function localFileRole(file) {
  const magic = new TextDecoder().decode(await file.slice(0, 8).arrayBuffer());
  const name = file.name.toLowerCase();
  if (/\.(xml|xmltv|tv)$/i.test(name)) return "epg";
  if (magic === "CASUNAT1" || magic === "CASUNAT2" || name.endsWith(".casu") || name.endsWith(".json")) return "casu";
  if (/\.(srt|vtt)$/i.test(name)) return "subtitle";
  if (/\.(m3u8?|pls|wpl|xspf|jspf|asx|wmx|wvx|rmp|ram)$/i.test(name)) return "playlist";
  return "media";
}

function decodeId3Text(body) {
  const u8 = new Uint8Array(body);
  if (!u8.length) return "";
  let enc = u8[0], bytes = u8.subarray(1), s = "";
  if (enc === 1) {
    const b = (bytes[0] === 0xff && bytes[1] === 0xfe) ? bytes.subarray(2) : bytes;
    s = new TextDecoder("utf-16le").decode(b);
  } else if (enc === 2 || enc === 3) {
    s = new TextDecoder("utf-8").decode(bytes);
  } else {
    s = new TextDecoder("latin1").decode(bytes);
  }
  return s.replace(/\0.*$/, "").trim();
}
function parseApic(body) {
  const u8 = new Uint8Array(body);
  if (u8.length < 12) return null;
  let enc = u8[0], p = 1, e = p;
  while (e < u8.length && u8[e] !== 0) e++;
  const mime = new TextDecoder("latin1").decode(u8.subarray(p, e));
  p = e + 1;
  if (p >= u8.length) return null;
  p++;
  if (enc === 1) { p++; while (p + 1 < u8.length && !(u8[p] === 0 && u8[p + 1] === 0)) p++; p += 2; }
  else { while (p < u8.length && u8[p] !== 0) p++; p++; }
  if (p >= u8.length) return null;
  return { mime: mime || "image/jpeg", data: u8.subarray(p) };
}
function textFrames(buffer) {
  const u8 = new Uint8Array(buffer), dec = new TextDecoder("utf-8");
  const isId = (s) => /^[A-Z0-9]{4}$/.test(s);
  if (u8.length < 10 || u8[0] !== 0x49 || u8[1] !== 0x44 || u8[2] !== 0x33) return {};
  const tagSize = ((u8[6] & 0x7f) << 21) | ((u8[7] & 0x7f) << 14) | ((u8[8] & 0x7f) << 7) | (u8[9] & 0x7f);
  const flags = u8[5];
  let off = 10;
  if (flags & 0x40) off += 4;
  const end = Math.min(10 + tagSize, u8.length), out = {};
  while (off + 10 <= end) {
    const id = dec.decode(u8.subarray(off, off + 4));
    if (!isId(id)) break;
    const sync = ((u8[off + 4] & 0x7f) << 21) | ((u8[off + 5] & 0x7f) << 14) |
                 ((u8[off + 6] & 0x7f) << 7) | (u8[off + 7] & 0x7f);
    const be = (u8[off + 4] << 24) | (u8[off + 5] << 16) | (u8[off + 6] << 8) | u8[off + 7];
    let size = sync;
    const probe = off + 10 + sync;
    if (probe + 4 <= end && !isId(dec.decode(u8.subarray(probe, probe + 4)))) size = be;
    const bodyOff = off + 10 + ((u8[off + 9] & 0x40) ? 4 : 0);
    const body = u8.subarray(bodyOff, Math.min(bodyOff + size, u8.length));
    if (id === "TIT2") out.title = decodeId3Text(body);
    else if (id === "TPE1") out.artist = decodeId3Text(body);
    else if (id === "TALB") out.album = decodeId3Text(body);
    else if (id === "TCON") out.genre = decodeId3Text(body);
    else if (id === "TRCK") out.track = decodeId3Text(body);
    else if (id === "APIC" && !out.art) out.art = parseApic(body);
    off += 10 + size;
  }
  return out;
}
async function audioTags(file) {
  try {
    const head = new Uint8Array(await file.slice(0, Math.min(file.size, 65536)).arrayBuffer());
    let read = 65536;
    if (head.length >= 10 && head[0] === 0x49 && head[1] === 0x44 && head[2] === 0x33)
      read = Math.min(file.size, 16 * 1024 * 1024);
    const tags = textFrames(await file.slice(0, read).arrayBuffer());
    if (!tags.title && file.size > 128) {
      const tail = new Uint8Array(await file.slice(Math.max(0, file.size - 128), file.size).arrayBuffer());
      if (tail[0] === 0x54 && tail[1] === 0x41 && tail[2] === 0x47) {
        const d = new TextDecoder("latin1");
        tags.title = (d.decode(tail.subarray(3, 33)) || "").replace(/\0.*$/, "").trim();
        tags.artist = (d.decode(tail.subarray(33, 63)) || "").replace(/\0.*$/, "").trim();
        tags.album = (d.decode(tail.subarray(63, 93)) || "").replace(/\0.*$/, "").trim();
      }
    }
    if (tags.art) tags.artUrl = URL.createObjectURL(new Blob([tags.art.data], { type: tags.art.mime || "image/jpeg" }));
    return tags;
  } catch (error) { return {}; }
}
function fileDisplayTitle(file, tags) {
  tags = tags || {};
  const name = file.name || "";
  if (tags.title) return tags.title.trim();
  const stem = name.replace(/\.[^.]*$/, "");
  const track = stem.match(/^(\d{1,3})\s*[-._)\s]+\s*(.+)$/);
  let base = track ? track[2] : stem;
  if (base.includes(" - ")) base = base.split(" - ").pop();
  return (base.trim() || name);
}
function addLocal(file, kind) {
  const url = URL.createObjectURL(file);
  state.objectUrls.add(url);
  const item = addItem({ title: file.name, url, kind, file });
  (async () => {
    try {
      const tags = await audioTags(file);
      const title = fileDisplayTitle(file, tags);
      if (title && title !== file.name) item.title = title;
      if (tags && (tags.artist || tags.album)) item.subtitle = [tags.artist, tags.album].filter(Boolean).join(" · ");
      if (tags && tags.artUrl) item.thumbnail = tags.artUrl;
      updateVizCover(item);
      renderQueue();
      if (state.items[state.index] === item) $("title").textContent = itemLabel(item);
    } catch (error) { /* tags are best-effort */ }
  })();
  return item;
}

// ---------------------------------------------------------------------------
// playlists (M3U/PLS) and EPG (XMLTV)
// ---------------------------------------------------------------------------
function boundedEpgText(value, label) {
  const text = String(value || "").trim();
  if (text.includes("\0") || new TextEncoder().encode(text).length > MAX_EPG_TEXT)
    throw Error(`${label} exceeds its safety limit`);
  return text;
}
function m3uAttributes(value) {
  const result = {};
  for (const match of value.matchAll(/([A-Za-z0-9_-]+)=(?:"([^"]*)"|'([^']*)'|([^\s]+))/g))
    result[match[1].toLowerCase()] = boundedEpgText(match[2] ?? match[3] ?? match[4], "playlist attribute");
  return result;
}
function decodeEntryPath(value) {
  let v = String(value || "").trim();
  if (v.startsWith("file://")) {
    try { v = decodeURIComponent(v.replace(/^file:\/\/(localhost)?/i, "")); } catch {}
  } else if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(v)) {
    try { v = decodeURIComponent(v); } catch {}
  }
  return v;
}
function localEntryMatch(entry, ordinary) {
  const normalized = decodeEntryPath(entry).replaceAll("\\", "/").replace(/^\.\//, "");
  const base = normalized.split("/").pop();
  if (ordinary.get(normalized)) return ordinary.get(normalized);
  if (ordinary.get(base)) return ordinary.get(base);
  for (const [key, file] of ordinary)
    if (key.endsWith("/" + normalized)) return file;
  return undefined;
}
function playlistXmlFormat(text, name) {
  const lower = name.toLowerCase();
  if (/\.(pls)$/i.test(lower)) return "pls";
  if (/\.(wpl)$/i.test(lower)) return "wpl";
  if (/\.(xspf)$/i.test(lower)) return "xspf";
  if (/\.(jspf|json)$/i.test(lower)) return "jspf";
  if (/\.(asx|wmx|wvx|axs)$/i.test(lower)) return "asx";
  if (/\.(rmp|ram)$/i.test(lower)) return "rmp";
  const trimmed = text.trimStart();
  if (trimmed.startsWith("[playlist]")) return "pls";
  if (trimmed.startsWith("{")) return "jspf";
  if (trimmed.startsWith("<") || trimmed.startsWith("<?xml")) {
    const head = trimmed.slice(0, 2048).toLowerCase();
    if (head.includes("<tracklist") || head.includes("xspf")) return "xspf";
    if (head.includes("<asx") || head.includes("<entry")) return "asx";
    if (head.includes("?wpl") || head.includes("<media")) return "wpl";
    if (head.includes("<track")) return "xspf";
    return "asx";
  }
  return "m3u";
}
function addPlaylistLocation(value, attributes, title, ordinary, consumed, playlistName) {
  const entry = String(value || "").trim();
  if (/^https?:\/\//i.test(entry)) {
    try {
      const url = networkUrl(entry);
      const yt = youtubeId(url);
      addItem({ title: boundedEpgText(title, "channel name"), url,
        kind: yt ? "youtube" : "stream",
        epgId: attributes["tvg-id"] || "", group: attributes["group-title"] || "",
        logo: attributes["tvg-logo"] || "", playlist: playlistName || "" });
      return true;
    } catch (error) { /* not a valid HTTP(S) URL — try local */ }
  }
  const local = localEntryMatch(entry, ordinary);
  if (local) {
    const item = addLocal(local, local.type.startsWith("audio/") ? "audio" : "video");
    if (title && String(title).trim() && String(title).trim() !== entry) item.title = String(title).trim();
    item.epgId = attributes["tvg-id"] || ""; item.group = attributes["group-title"] || "";
    item.playlist = playlistName || "";
    consumed.add(local.name);
    return true;
  }
  return false;
}
function xmlAttr(node, name) {
  if (!node || !node.attributes) return null;
  for (let i = 0; i < node.attributes.length; i++) {
    const attr = node.attributes.item(i);
    if (attr.name.toLowerCase() === String(name).toLowerCase()) return attr.value;
  }
  return null;
}
function findLocal(root, name) {
  const wanted = String(name).toLowerCase();
  const out = [];
  for (const node of root.getElementsByTagName("*")) {
    const local = (node.localName || node.tagName || "").toLowerCase();
    if (local === wanted) out.push(node);
  }
  return out;
}
function playlistXmlEntries(text, format) {
  const doc = new DOMParser().parseFromString(text, "text/xml");
  const entries = [];
  if (format === "wpl") {
    for (const media of findLocal(doc, "media")) {
      const src = xmlAttr(media, "src");
      if (src) entries.push([src, xmlAttr(media, "title") || ""]);
    }
  } else if (format === "xspf") {
    for (const track of findLocal(doc, "track")) {
      const titleNode = findLocal(track, "title")[0];
      const title = titleNode && titleNode.textContent ? titleNode.textContent.trim() : "";
      for (const location of findLocal(track, "location"))
        if (location.textContent) entries.push([location.textContent.trim(), title]);
    }
  } else if (format === "asx") {
    const all = findLocal(doc, "entry");
    if (!all.length) {
      for (const ref of findLocal(doc, "ref")) {
        const href = xmlAttr(ref, "href");
        if (href) entries.push([href, ""]);
      }
    } else {
      for (const entryNode of all) {
        const titleNode = findLocal(entryNode, "title")[0];
        const title = titleNode && titleNode.textContent ? titleNode.textContent.trim() : "";
        const refs = findLocal(entryNode, "ref");
        if (refs.length) {
          for (const ref of refs) {
            const href = xmlAttr(ref, "href");
            if (href) entries.push([href, title]);
          }
        } else {
          for (const param of findLocal(entryNode, "param"))
            if ((xmlAttr(param, "name") || "").toLowerCase() === "url" && xmlAttr(param, "value"))
              entries.push([xmlAttr(param, "value"), title]);
        }
      }
    }
  } else if (format === "rmp") {
    const smil = text.trimStart().startsWith("<");
    if (smil) {
      for (const node of [...findLocal(doc, "ref"), ...findLocal(doc, "audio"), ...findLocal(doc, "video"), ...findLocal(doc, "media")]) {
        const src = xmlAttr(node, "src") || xmlAttr(node, "href");
        if (src) entries.push([src, ""]);
      }
    } else {
      for (const line of text.split(/\r?\n/)) {
        const entry = line.trim();
        if (entry && !entry.startsWith("#")) entries.push([entry, ""]);
      }
    }
  }
  return entries;
}
async function addPlaylist(file, ordinary, consumed) {
  if (file.size > MAX_PLAYLIST_BYTES) throw Error("playlist exceeds the 8 MiB safety limit");
  const text = await file.text();
  if (new TextEncoder().encode(text).length > MAX_PLAYLIST_BYTES)
    throw Error("playlist exceeds the 8 MiB safety limit");
  const format = playlistXmlFormat(text, file.name);
  state.expanded.add(file.name);
  let missing = 0;
  const addEntry = (value, title) => {
    if (value == null || !String(value).trim()) return;
    if (!addPlaylistLocation(String(value), {}, String(title || "").trim(), ordinary, consumed, file.name)) missing++;
  };
  if (format === "pls") {
    const values = text.split(/\r?\n/).map((line) => /^File\d+=(.*)$/i.exec(line.trim())?.[1]?.trim()).filter(Boolean);
    if (values.length > MAX_PLAYLIST_ENTRIES) throw Error(`playlist exceeds ${MAX_PLAYLIST_ENTRIES} entries`);
    for (const value of values) addEntry(value, "");
  } else if (format === "jspf") {
    let payload;
    try { payload = JSON.parse(text); } catch { throw Error("JSPF playlist is not valid JSON"); }
    const pl = payload && payload.playlist && typeof payload.playlist === "object" ? payload.playlist : payload;
    const tracks = pl && (pl.track || pl.tracks);
    if (!Array.isArray(tracks) || tracks.length > MAX_PLAYLIST_ENTRIES) throw Error(`playlist exceeds ${MAX_PLAYLIST_ENTRIES} entries`);
    for (const track of tracks) {
      if (!track || typeof track !== "object") continue;
      const locations = Array.isArray(track.location) ? track.location : (track.location ? [track.location] : []);
      for (const location of locations) addEntry(location, track.title);
    }
  } else if (format === "wpl" || format === "xspf" || format === "asx" || format === "rmp") {
    let entries;
    try { entries = playlistXmlEntries(text, format); } catch { throw Error(`${format.toUpperCase()} playlist XML is malformed`); }
    if (entries.length > MAX_PLAYLIST_ENTRIES) throw Error(`playlist exceeds ${MAX_PLAYLIST_ENTRIES} entries`);
    for (const [value, title] of entries) addEntry(value, title);
  } else {
    const lines = text.split(/\r?\n/);
    if (lines.length > MAX_PLAYLIST_ENTRIES * 3 + 1) throw Error(`playlist exceeds ${MAX_PLAYLIST_ENTRIES} entries`);
    if (lines.some((line) => new TextEncoder().encode(line).length > MAX_PLAYLIST_LINE))
      throw Error(`playlist line exceeds ${MAX_PLAYLIST_LINE} bytes`);
    let pending = {}, pendingName = "", count = 0;
    for (const raw of lines) {
      const line = raw.trim();
      if (!line || line.startsWith("#EXTM3U")) continue;
      if (/^#EXTINF:/i.test(line)) {
        const comma = line.indexOf(",");
        pending = m3uAttributes(comma < 0 ? line : line.slice(0, comma));
        pendingName = boundedEpgText(comma < 0 ? "" : line.slice(comma + 1), "channel name");
        continue;
      }
      if (line.startsWith("#")) continue;
      if (++count > MAX_PLAYLIST_ENTRIES) throw Error(`playlist exceeds ${MAX_PLAYLIST_ENTRIES} entries`);
      addEntry(line, pendingName || line);
      pending = {}; pendingName = "";
    }
  }
  if (missing) toast(`${missing} entries reference local files — select the playlist together with its media files`);
}

function xmltvTime(value) {
  const match = /^(\d{14})(?:\s*([+-]\d{4}|Z))?$/.exec(String(value || "").trim());
  if (!match) throw Error("XMLTV timestamp is invalid");
  const stamp = match[1], year = +stamp.slice(0, 4), month = +stamp.slice(4, 6) - 1,
        day = +stamp.slice(6, 8), hour = +stamp.slice(8, 10), minute = +stamp.slice(10, 12),
        second = +stamp.slice(12, 14), offset = match[2] || "+0000",
        sign = offset[0] === "-" ? -1 : 1,
        minutes = offset === "Z" ? 0 : sign * (+offset.slice(1, 3) * 60 + +offset.slice(3, 5));
  const result = Date.UTC(year, month, day, hour, minute, second) - minutes * 60000;
  if (!Number.isFinite(result)) throw Error("XMLTV timestamp is invalid");
  return result;
}
async function addEpg(file) {
  if (file.size > MAX_XMLTV_BYTES) throw Error("XMLTV guide exceeds the 32 MiB safety limit");
  const text = await file.text();
  if (/<!DOCTYPE|<!ENTITY/i.test(text.slice(0, 4096))) throw Error("XMLTV DTD/entities are not accepted");
  const documentNode = new DOMParser().parseFromString(text, "application/xml");
  if (documentNode.querySelector("parsererror") || documentNode.documentElement.localName !== "tv")
    throw Error("XMLTV guide is malformed");
  const names = new Map(), programmes = [];
  for (const node of documentNode.documentElement.children) {
    if (node.localName === "channel") {
      const id = boundedEpgText(node.getAttribute("id"), "XMLTV channel id");
      const name = boundedEpgText(
        [...node.children].find((child) => child.localName === "display-name")?.textContent || id,
        "XMLTV channel name");
      if (id) names.set(id, name);
      if (names.size > MAX_XMLTV_CHANNELS) throw Error(`XMLTV exceeds ${MAX_XMLTV_CHANNELS} channels`);
    } else if (node.localName === "programme") {
      const channel = boundedEpgText(node.getAttribute("channel"), "XMLTV channel id");
      const child = (name) => boundedEpgText(
        [...node.children].find((item) => item.localName === name)?.textContent || "", `XMLTV ${name}`);
      const title = child("title");
      if (!channel || !title) continue;
      const start = xmltvTime(node.getAttribute("start")), stop = xmltvTime(node.getAttribute("stop"));
      if (stop <= start) continue;
      programmes.push({ channel, start, stop, title, description: child("desc"), category: child("category") });
      if (programmes.length > MAX_XMLTV_PROGRAMMES)
        throw Error(`XMLTV exceeds ${MAX_XMLTV_PROGRAMMES} programmes`);
    }
  }
  programmes.sort((a, b) => a.channel.localeCompare(b.channel) || a.start - b.start);
  state.epgNames = names; state.programmes = programmes;
  refreshEpg();
  toast(`${programmes.length} programmes loaded`);
}
function epgFor(item) {
  if (!item?.epgId) return { current: null, next: null, upcoming: [] };
  const now = Date.now();
  const upcoming = state.programmes
    .filter((entry) => entry.channel === item.epgId && entry.stop > now).slice(0, 20);
  const current = upcoming.find((entry) => entry.start <= now && now < entry.stop) || null;
  const next = upcoming.find((entry) => entry !== current && entry.start >= now) || null;
  return { current, next, upcoming };
}
function clockDate(value) {
  return new Intl.DateTimeFormat(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}
function refreshEpg() {
  const item = state.items[state.index], guide = epgFor(item);
  const nowNode = $("epg-now"), nextNode = $("epg-next");
  nowNode.textContent = guide.current ? guide.current.title : (state.programmes.length ? "NO CURRENT PROGRAMME" : "NO EPG LOADED");
  nextNode.textContent = guide.next ? `Next ${clockDate(guide.next.start)} · ${guide.next.title}` : "Extended M3U and XMLTV";
  if (guide.current && item) $("meta").textContent =
    `LIVE · ${item.group || "STREAM"} · ${clockDate(guide.current.start)}–${clockDate(guide.current.stop)}`;
}
function renderEpgDialog() {
  const root = $("epg-guide");
  root.replaceChildren();
  for (const item of state.items.filter((entry) => entry.epgId)) {
    const guide = epgFor(item);
    const card = document.createElement("article");
    card.className = "epg-channel";
    card.tabIndex = 0;
    card.onclick = () => playIndex(state.items.indexOf(item));
    card.onkeydown = (event) => { if (event.key === "Enter") card.click(); };
    const name = document.createElement("h3"), current = document.createElement("strong"),
          next = document.createElement("span");
    name.textContent = itemLabel(item);
    current.textContent = guide.current ? `NOW · ${guide.current.title}` : "No current programme";
    next.textContent = guide.next ? `NEXT · ${clockDate(guide.next.start)} · ${guide.next.title}` : "No following programme";
    card.append(name, current, next);
    root.append(card);
  }
  if (!root.children.length) {
    const empty = document.createElement("p");
    empty.textContent = "Load an Extended M3U playlist with tvg-id values together with an XMLTV file.";
    root.append(empty);
  }
}

// ---------------------------------------------------------------------------
// add files / URLs
// ---------------------------------------------------------------------------
async function parseCasu(file) {
  if (file.size > 1024 * 1024 * 1024) throw Error("CASU file exceeds the 1 GiB browser verification limit");
  const header = new Uint8Array(await file.slice(0, 100).arrayBuffer());
  const magic = new TextDecoder().decode(header.slice(0, 8));
  if (magic === "CASUNAT1") {
    if (header.length < 92) throw Error("CASUNAT1 header is truncated");
    const view = new DataView(header.buffer);
    const manifestLength = littleU64(view, 12), payloadLength = littleU64(view, 20);
    const offset = 92 + manifestLength;
    if (manifestLength > 64 * 1024 * 1024 || offset + payloadLength !== file.size)
      throw Error("CASUNAT1 size or manifest limit does not match its header");
    const manifest = JSON.parse(await file.slice(92, offset).text());
    if (!manifest || typeof manifest !== "object" || Array.isArray(manifest) ||
        !manifest.source || typeof manifest.source !== "object")
      throw Error("CASUNAT1 manifest is invalid");
    const name = manifest.source.filename || file.name.replace(/\.casu$/i, "");
    const payload = file.slice(offset, offset + payloadLength, mimeFor(name));
    const expected = [...header.slice(60, 92)].map((v) => v.toString(16).padStart(2, "0")).join("");
    const actual = await digestHex(await payload.arrayBuffer());
    if (actual !== expected) throw Error("CASUNAT1 payload integrity failed");
    return { kind: "native1", manifest, payload };
  }
  if (magic === "CASUNAT2") return { kind: "native2", player: await CasuNative.open(file) };
  if (file.size > 64 * 1024 * 1024) throw Error("CASU sidecar exceeds the 64 MiB browser limit");
  const manifest = JSON.parse(await file.text());
  const source = manifest?.source;
  if (!manifest || typeof manifest !== "object" || Array.isArray(manifest) || !source ||
      typeof source.filename !== "string" || !source.filename ||
      source.filename !== source.filename.replaceAll("\\", "/").split("/").pop() ||
      (source.sha256 !== undefined && !/^[0-9a-f]{64}$/i.test(source.sha256)))
    throw Error("CASU sidecar manifest is invalid");
  return { kind: "sidecar", manifest };
}

async function addFiles(files) {
  const all = [...files];
  const roles = await Promise.all(all.map(localFileRole));
  const withRole = (role) => all.filter((_file, index) => roles[index] === role);
  const playlists = withRole("playlist"), epgFiles = withRole("epg"), casuFiles = withRole("casu"),
        subtitleFiles = withRole("subtitle"), ordinaryFiles = withRole("media");
  const ordinary = new Map();
  for (const file of ordinaryFiles) {
    ordinary.set(file.name, file);
    if (file.webkitRelativePath) {
      const rel = file.webkitRelativePath.replaceAll("\\", "/");
      ordinary.set(rel, file);
    }
  }
  const consumed = new Set();
  const before = state.items.length;
  for (const file of epgFiles) { try { await addEpg(file); } catch (error) { toast(`${file.name}: ${error.message}`); } }
  for (const file of playlists) {
    if (state.items.some((e) => e.playlist === file.name)) { toast(`Playlist “${file.name}” is already in the queue`); continue; }
    try { await addPlaylist(file, ordinary, consumed); } catch (error) { toast(`${file.name}: ${error.message}`); }
  }
  for (const file of casuFiles) {
    try {
      const casu = await parseCasu(file);
      if (casu.kind === "native2") {
        addItem({ title: file.name, kind: "casu-native", native2: casu.player, file });
        $("verify-state").textContent = "VERIFIED";
        $("verify-detail").textContent = "CASUNAT2 structure, index and SHA-256 verified";
        continue;
      }
      if (casu.kind === "native1") {
        const name = casu.manifest?.source?.filename || file.name.replace(/\.casu$/i, "");
        const blob = new File([casu.payload], name, { type: mimeFor(name) });
        addLocal(blob, "casu");
        $("verify-state").textContent = "VERIFIED";
        $("verify-detail").textContent = "CASUNAT1 SHA-256 payload verified";
        continue;
      }
      const name = casu.manifest?.source?.filename;
      const source = ordinary.get(name);
      if (!source) { toast(`Select ${name || "the source media"} together with its sidecar`); continue; }
      const expected = casu.manifest?.source?.sha256;
      if (expected && await digestHex(await source.arrayBuffer()) !== expected)
        throw Error("CASU sidecar source SHA-256 mismatch");
      addLocal(source, "casu");
      consumed.add(name);
      $("verify-state").textContent = "VERIFIED";
      $("verify-detail").textContent = "Sidecar source SHA-256 verified";
    } catch (error) {
      const magic = new TextDecoder().decode(await file.slice(0, 8).arrayBuffer());
      if (magic === "CASUNAT1" || magic === "CASUNAT2") {
        addLocal(file, "casu-fallback");
        toast(`${file.name}: native browser path unavailable — trying verified server fallback`);
      } else {
        addLocal(file, file.type.startsWith("audio/") ? "audio" : "media-auto");
        toast(`${file.name}: not valid CASU — trying ordinary media playback`);
      }
    }
  }
  for (const file of ordinaryFiles) {
    if (consumed.has(file.name)) continue;
    // No double-loading: media already in the queue (same relative path) is
    // not added a second time.
    const key = file.webkitRelativePath ? file.webkitRelativePath.replaceAll("\\", "/") : file.name;
    if (state.items.some((e) => e.file && (e.file.name === key || e.file.webkitRelativePath === key))) continue;
    addLocal(file, file.type.startsWith("audio/") ? "audio" : "video");
  }
  const added = state.items.slice(before).filter((item) => item.file);
  for (const subtitle of subtitleFiles) {
    const item = added.find((candidate) => subtitleMatches(subtitle, candidate.file.name));
    if (item) (item.subtitleFiles ??= []).push(subtitle);
    else toast(`No matching media selected for subtitle: ${subtitle.name}`);
  }
  const current = state.items[state.index];
  if (current?.subtitleFiles?.length) await installMediaTracks(current);
  refreshEpg();
  persistQueue();
}

function mediaStem(name) { return name.replace(/\.[^.]+$/, "").toLowerCase(); }
function subtitleMatches(subtitle, name) {
  const mediaName = mediaStem(name), candidate = mediaStem(subtitle.name);
  return candidate === mediaName || candidate.startsWith(`${mediaName}.`) || candidate.startsWith(`${mediaName}_`);
}
function srtToVtt(text) {
  return `WEBVTT\n\n${text.replace(/^\s*WEBVTT[^\n]*\n?/i, "").replace(/(\d{2}:\d{2}:\d{2}),(\d{3})/g, "$1.$2")}`;
}
async function installMediaTracks(item) {
  media.querySelectorAll("track[data-mpcasu]").forEach((node) => node.remove());
  for (const url of item.trackUrls || []) { URL.revokeObjectURL(url); state.objectUrls.delete(url); }
  item.trackUrls = [];
  const select = $("subtitle-track");
  select.replaceChildren(new Option("Subtitles off", ""));
  for (const [index, file] of (item.subtitleFiles || []).entries()) {
    const content = /\.srt$/i.test(file.name) ? srtToVtt(await file.text()) : await file.text();
    const url = URL.createObjectURL(new Blob([content], { type: "text/vtt" }));
    const track = document.createElement("track");
    state.objectUrls.add(url);
    item.trackUrls.push(url);
    track.dataset.mpcasu = "1";
    track.kind = "subtitles";
    track.label = file.name;
    track.srclang = (/\.([a-z]{2,3})(?:[-_][a-z]{2})?\.(?:srt|vtt)$/i.exec(file.name)?.[1] || "und");
    track.src = url;
    media.append(track);
    select.add(new Option(file.name, String(index)));
  }
  select.hidden = !(item.subtitleFiles || []).length;
  select.value = "";
}

function openUrl(value) {
  if (!value) return;
  const yt = youtubeId(value);
  if (yt) {
    addItem({ title: value, url: networkUrl(value), kind: "youtube" });
    hydrateYouTubeTitle(state.items[state.items.length - 1], value);
    return;
  }
  const url = networkUrl(value);
  addItem({ title: url, url, kind: "stream" });
}

// ---------------------------------------------------------------------------
// backend (optional) detection + stream/catalog helpers
// ---------------------------------------------------------------------------
async function detectBackend() {
  const ping = CFG.ping && resolveEndpoint(CFG.ping);
  if (!ping) return;
  try {
    const response = await fetch(ping, { cache: "no-store" });
    if (!response.ok) return;
    const payload = await response.json();
    if (payload && payload.ok) {
      state.backend.stream = !!CFG.stream;
      state.backend.catalog = !!CFG.catalog;
      state.backend.search = !!CFG.search;
    }
  } catch (error) { /* backend is optional */ }
}
function resolveEndpoint(value) {
  try { return new URL(value, location.href).href; } catch (error) { return null; }
}
function relayUrl(url) {
  if (!state.backend.stream || !CFG.stream) return url;
  return `${resolveEndpoint(CFG.stream)}?url=${encodeURIComponent(url)}`;
}
async function loadRemoteCatalog(value) {
  if (!value) return;
  const url = networkUrl(value);
  let response;
  if (state.backend.catalog && CFG.catalog) {
    response = await fetch(`${resolveEndpoint(CFG.catalog)}?url=${encodeURIComponent(url)}`);
  } else {
    response = await fetch(url);
  }
  if (!response.ok) { let detail; try { detail = (await response.json()).error; } catch (error) {} throw Error(detail || `HTTP ${response.status}`); }
  const declared = Number(response.headers.get("Content-Length") || 0);
  if (declared > MAX_XMLTV_BYTES) throw Error("remote catalog exceeds the 32 MiB safety limit");
  const body = await response.arrayBuffer();
  if (body.byteLength > MAX_XMLTV_BYTES) throw Error("remote catalog exceeds the 32 MiB safety limit");
  const text = new TextDecoder().decode(body);
  const xml = /^\s*</.test(text);
  const file = new File([body], xml ? "remote.xml" : "remote.m3u");
  if (xml) await addEpg(file); else await addPlaylist(file, new Map(), new Set());
  renderEpgDialog();
  toast(`${xml ? "XMLTV guide" : "playlist"} loaded from URL`);
}

// ---------------------------------------------------------------------------
// playback: native / youtube / media
// ---------------------------------------------------------------------------
function resetNativeMetadata() {
  const subtitle = $("native-subtitle"), chapters = $("chapter-select");
  subtitle.textContent = ""; subtitle.hidden = true;
  chapters.replaceChildren(new Option("Chapters", "")); chapters.hidden = true;
  for (const [id, label] of [["#video-track", "Video"], ["#audio-track", "Audio"], ["#subtitle-track", "Subtitles off"]]) {
    const node = $(id);
    node.replaceChildren(new Option(label, "")); node.hidden = true;
  }
}
function populateNativeTracks(player) {
  for (const kind of ["video", "audio", "subtitle"]) {
    const node = $(`#${kind}-track`), tracks = player.trackOptions(kind);
    for (const track of tracks) node.add(new Option(track.label, String(track.id)));
    node.value = player.selected[kind] == null ? "" : String(player.selected[kind]);
    node.hidden = kind === "subtitle" ? !tracks.length : tracks.length < 2;
  }
}
function stopNative() {
  if (state.native) { state.native.pause(); state.native.onSubtitle = () => {}; state.native = null; }
  nativeCanvas.hidden = true;
  resetNativeMetadata();
  resetAbLoop();
}
function youtubeCommand(func, args = []) {
  if (youtubeFrame.hidden || !youtubeFrame.contentWindow) return;
  youtubeFrame.contentWindow.postMessage(
    JSON.stringify({ event: "command", func, args }), YT_ORIGIN);
}
function stopYoutube() {
  document.getElementById("drop-zone").classList.remove("video-mode");
  youtubeFrame.removeAttribute("src");
  youtubeFrame.hidden = true;
  state.youtubeState = -1; state.youtubeTime = 0; state.youtubeDuration = 0;
}
function resetAbLoop() {
  state.abStart = state.abEnd = null; state.abToken = -1;
  $("ab-loop").textContent = "A–B";
  $("ab-loop").classList.remove("on");
}
function updateVizCover(item) {
  const cover = $("viz-cover"), img = $("viz-cover-img");
  const thumb = item && (item.thumbnail || item.artUrl || "");
  if (thumb) { img.src = thumb; cover.hidden = false; }
  else { img.removeAttribute("src"); cover.hidden = true; }
}
async function hydrateYouTubeTitle(item, value) {
  const id = youtubeId(value);
  if (!id) return;
  try {
    const response = await fetch(`https://www.youtube.com/oembed?url=${encodeURIComponent(value)}&format=json`);
    const payload = await response.json();
    if (payload.title) {
      item.title = payload.title;
      if (payload.author_name) item.subtitle = payload.author_name;
      if (payload.thumbnail_url) item.thumbnail = payload.thumbnail_url;
      renderQueue();
      if (state.items[state.index] === item) $("title").textContent = itemLabel(item);
      updateVizCover(item);
    }
  } catch (error) { /* titles are best-effort without a backend */ }
}
function playYoutube(item, id) {
  document.getElementById("drop-zone").classList.add("video-mode");
  media.hidden = false;
  youtubeFrame.hidden = true;
  const list = youtubeList(item.url);
  const params = new URLSearchParams({
    enablejsapi: "1", autoplay: "1", playsinline: "1",
    origin: location.origin, rel: "0",
  });
  if (list) params.set("list", list);
  youtubeFrame.hidden = false;
  media.hidden = true;
  youtubeFrame.src = `${YT_ORIGIN}/embed/${encodeURIComponent(id)}?${params.toString()}`;
}
function setupHls(url, item) {
  if (state.hls) { try { state.hls.destroy(); } catch (error) {} state.hls = null; }
  if (!isHlsUrl(url) || !window.Hls) return false;
  if (media.canPlayType("application/vnd.apple.mpegurl") === "probably") return false; // native HLS
  if (!Hls.isSupported()) return false;
  state.hls = new Hls({ liveSyncDuration: (window.PUREWEB?.hls?.liveSyncDuration) || 6 });
  state.hls.loadSource(url);
  state.hls.attachMedia(media);
  state.hls.on(Hls.Events.ERROR, (_event, data) => {
    if (data.fatal) { state.hls?.destroy(); state.hls = null; toast("HLS stream error: " + (data.details || data.type)); }
  });
  return true;
}
async function playIndex(index) {
  if (index < 0 || index >= state.items.length) return;
  const token = ++state.playbackToken;
  state.index = index;
  state.selected = index;
  const item = state.items[index];
  updateVizCover(item);
  media.pause();
  stopYoutube();
  stopNative();
  media.querySelectorAll("track[data-mpcasu]").forEach((node) => node.remove());

  // Commit metadata immediately so the UI never waits on network playback.
  $("empty-state").hidden = true;
  $("title").textContent = itemLabel(item);
  $("meta").textContent = `${(item.kind || "STREAM").toUpperCase()}${item.subtitle ? ` · ${item.subtitle}` : ""} · SOURCE TIMING`;
  $("format-badge").textContent = (item.kind || "MEDIA").toUpperCase();
  $("segment-state").textContent = (item.originalKind || item.kind)?.startsWith("casu") ? "CASU SEGMENTED" : "STANDARD MEDIA";
  refreshEpg();
  renderQueue();
  persistQueue();

  if (item.native2) {
    media.hidden = true;
    nativeCanvas.hidden = false;
    state.native = item.native2;
    state.native.attach(nativeCanvas);
    state.native.onTime = (position, duration) => {
      if (token !== state.playbackToken) return;
      $("seek").max = Math.max(duration, 1);
      $("seek").value = position;
      $("clock").textContent = `${formatTime(position)} / ${formatTime(duration)}`;
    };
    state.native.onSubtitle = (text) => {
      if (token !== state.playbackToken) return;
      const node = $("native-subtitle");
      node.textContent = text; node.hidden = !text;
    };
    state.native.onEnded = () => { if (token === state.playbackToken) next(1); };
    populateNativeTracks(state.native);
    const chapters = $("chapter-select");
    for (const chapter of state.native.chapters) chapters.add(new Option(chapter.title, String(chapter.start)));
    chapters.hidden = !state.native.chapters.length;
    state.native.setVolume($("volume").value);
    state.native.play()
      .then(() => { if (token === state.playbackToken) $("play").textContent = "❚❚"; })
      .catch((error) => { if (token === state.playbackToken) toast(`CASUNAT2 native playback unavailable: ${error.message}`); });
    return;
  }

  const yt = youtubeId(item.url);
  if (yt) {
    playYoutube(item, yt);
    if (!item.title || item.title === item.url) hydrateYouTubeTitle(item, item.url);
    return;
  }

  document.getElementById("drop-zone").classList.remove("video-mode");
  media.hidden = false;
  if (item.subtitleFiles?.length) await installMediaTracks(item);
  if (token !== state.playbackToken) return;
  let playbackUrl = item.resolvedUrl || item.url;
  if (!item.proxyFailed && (item.kind === "stream" || item.resolvedUrl) && /^https?:/i.test(playbackUrl)) {
    playbackUrl = relayUrl(playbackUrl);
  }
  setupHls(playbackUrl, item);
  if (media.src !== new URL(playbackUrl, location.href).href) media.src = playbackUrl;
  if (canAnalyse(item)) startViz(item);
  media.play()
    .then(() => { if (token === state.playbackToken) $("play").textContent = "❚❚"; })
    .catch((error) => { if (token === state.playbackToken) toast(`Playback needs a click or failed: ${error.message}`); });
}

function next(delta = 1) {
  if (!state.items.length) return;
  if (state.repeat === "one") { playIndex(state.index); return; }
  if (!state.shuffle && state.repeat === "off" &&
      ((delta > 0 && state.index === state.items.length - 1) || (delta < 0 && state.index === 0))) {
    $("play").textContent = "▶";
    return;
  }
  let target = state.index + delta;
  if (state.shuffle && state.items.length > 1) {
    const others = [...Array(state.items.length).keys()].filter((i) => i !== state.index);
    target = others[Math.floor(Math.random() * others.length)];
  } else if (state.shuffle) {
    target = state.index;
  }
  if (target >= state.items.length) target = state.repeat === "all" ? 0 : state.items.length - 1;
  if (target < 0) target = state.repeat === "all" ? state.items.length - 1 : 0;
  playIndex(target);
}

function togglePlay() {
  if (state.native) {
    if (state.native.playing) { state.native.pause(); $("play").textContent = "▶"; }
    else state.native.play().then(() => { $("play").textContent = "❚❚"; }).catch((error) => toast(error.message));
    return;
  }
  if (!youtubeFrame.hidden) {
    youtubeCommand(state.youtubeState === 1 ? "pauseVideo" : "playVideo");
    return;
  }
  if (media.paused) media.play().catch((error) => toast(error.message));
  else media.pause();
}
function activeTime() {
  return state.native ? state.native.currentTime()
       : !youtubeFrame.hidden ? state.youtubeTime : (media.currentTime || 0);
}
function stopAll() {
  ++state.playbackToken;
  media.pause();
  media.removeAttribute("src");
  media.load();
  stopYoutube();
  stopNative();
  if (state.hls) { try { state.hls.destroy(); } catch (error) {} state.hls = null; }
  stopViz();
  $("empty-state").hidden = false;
  $("title").textContent = "No media selected";
  $("clock").textContent = "00:00 / 00:00";
}

// ---------------------------------------------------------------------------
// visualizer
// ---------------------------------------------------------------------------
function canAnalyse(item) {
  if (!item || item.native2 || youtubeId(item.url)) return false;
  if (item.file) return true;                         // object URL
  const url = new URL(item.resolvedUrl || item.url, location.href);
  return url.origin === location.origin || state.backend.stream;  // CORS-capable
}
async function startViz(item) {
  if (!state.viz || !canAnalyse(item)) return;
  try {
    if (!state.vizCtx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      const ctx = new AudioCtx();
      if (ctx.state === "suspended") {
        try { await ctx.resume(); } catch (error) { /* autoplay policy */ }
      }
      // Never route the media element through a non-running AudioContext:
      // a suspended graph would mute the player even though it "plays".
      if (ctx.state !== "running") return;
      state.vizCtx = ctx;
      state.vizAnalyser = ctx.createAnalyser();
      state.vizAnalyser.fftSize = 256;
      const source = ctx.createMediaElementSource(media);
      source.connect(state.vizAnalyser);
      state.vizAnalyser.connect(ctx.destination);
    }
    if (state.vizCtx.state === "suspended") {
      try { await state.vizCtx.resume(); } catch (error) { /* autoplay policy */ }
      if (state.vizCtx.state !== "running") return;
    }
    if (!$("viz-canvas").hidden) return; // already drawing
    $("viz-canvas").hidden = false;
    const canvas = $("viz-canvas"), ctx2 = canvas.getContext("2d");
    const bins = state.vizAnalyser.frequencyBinCount;
    const data = new Uint8Array(bins);
    const draw = () => {
      state.vizRaf = requestAnimationFrame(draw);
      if (canvas.hidden) return;
      ctx2.clearRect(0, 0, canvas.width, canvas.height);
      state.vizAnalyser.getByteFrequencyData(data);
      const bars = 96, step = Math.floor(bins / bars);
      for (let i = 0; i < bars; i++) {
        const value = data[i * step] / 255;
        const h = Math.max(2, value * canvas.height);
        ctx2.fillStyle = `hsl(${8 + i * 0.35}, 90%, ${50 + value * 30}%)`;
        ctx2.fillRect((canvas.width / bars) * i, canvas.height - h, canvas.width / bars - 2, h);
      }
    };
    draw();
  } catch (error) { /* visualizer is optional */ }
}
function stopViz() {
  cancelAnimationFrame(state.vizRaf);
  $("viz-canvas").hidden = true;
}

// ---------------------------------------------------------------------------
// transport wiring
// ---------------------------------------------------------------------------
function setAbLoop() {
  if (state.native || !youtubeFrame.hidden) { toast("A–B repeat is available for browser-decoded media"); return; }
  const value = activeTime(), button = $("ab-loop");
  if (state.abToken !== state.playbackToken) {
    state.abStart = state.abEnd = null; state.abToken = state.playbackToken;
    button.textContent = "A–B"; button.classList.remove("on");
  }
  if (state.abStart === null) {
    state.abStart = value; state.abEnd = null;
    button.textContent = "Set B"; button.classList.add("on");
    toast(`A set at ${formatTime(value)}`);
  } else if (state.abEnd === null) {
    if (value <= state.abStart + .05) { toast("B must be after A"); return; }
    state.abEnd = value;
    button.textContent = "A↔B";
    toast(`Loop ${formatTime(state.abStart)}–${formatTime(value)}`);
  } else {
    state.abStart = state.abEnd = null;
    button.textContent = "A–B"; button.classList.remove("on");
    toast("A–B repeat cleared");
  }
}
function saveSnapshot() {
  if (!state.native && !youtubeFrame.hidden && (!media.videoWidth || !media.videoHeight)) {
    toast("The active source has no video frame"); return;
  }
  if (!youtubeFrame.hidden) { toast("YouTube frames cannot be exported by the embedding page"); return; }
  const source = state.native ? nativeCanvas : media;
  const canvas = document.createElement("canvas");
  canvas.width = source.width || source.videoWidth;
  canvas.height = source.height || source.videoHeight;
  try {
    canvas.getContext("2d").drawImage(source, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (!blob) { toast("Snapshot encoding failed"); return; }
      const url = URL.createObjectURL(blob), link = document.createElement("a");
      link.href = url; link.download = `mpcasu-${Date.now()}.png`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }, "image/png");
  } catch (error) { toast(`Snapshot unavailable: ${error.message}`); }
}
function cycleSpeed() {
  if (state.native) { toast("Native CASU speed control is unavailable in this browser path"); return; }
  const rates = [.5, .75, 1, 1.25, 1.5, 2];
  state.rateIndex = (state.rateIndex + 1) % rates.length;
  const rate = rates[state.rateIndex];
  media.playbackRate = rate;
  if (!youtubeFrame.hidden) youtubeCommand("setPlaybackRate", [rate]);
  $("speed").textContent = `${rate}×`;
}
function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen().catch((error) => toast(error.message));
  else document.querySelector(".app-shell").requestFullscreen?.().catch((error) => toast(error.message));
}

media.addEventListener("play", () => { $("play").textContent = "❚❚"; startViz(state.items[state.index]); });
media.addEventListener("pause", () => $("play").textContent = "▶");
media.addEventListener("ended", () => {
  if (state.abToken === state.playbackToken && state.abEnd !== null) { media.currentTime = state.abStart; media.play(); return; }
  next(1);
});
media.addEventListener("error", () => {
  const item = state.items[state.index];
  if (!item) return;
  if (item.proxyUrl && !item.proxyFailed && media.currentSrc === new URL(item.proxyUrl, location.href).href) {
    item.proxyFailed = true;
    media.src = item.url;
    media.play().catch(() => {});
    return;
  }
  toast("This source could not be decoded by the browser");
});
media.addEventListener("loadedmetadata", () => {
  $("seek").max = Number.isFinite(media.duration) ? media.duration : 1;
  $("meta").textContent = `${(state.items[state.index]?.kind || "MEDIA").toUpperCase()} · ${media.videoWidth ? `${media.videoWidth}×${media.videoHeight}` : "AUDIO"}`;
});
media.addEventListener("timeupdate", () => {
  $("seek").value = media.currentTime;
  $("clock").textContent = `${formatTime(media.currentTime)} / ${formatTime(media.duration)}`;
  if (state.abToken === state.playbackToken && state.abEnd !== null && media.currentTime >= state.abEnd)
    media.currentTime = state.abStart;
});

window.addEventListener("message", (event) => {
  if (event.origin !== YT_ORIGIN && event.origin !== "https://www.youtube.com") return;
  if (event.source !== youtubeFrame.contentWindow) return;
  let message;
  try { message = typeof event.data === "string" ? JSON.parse(event.data) : event.data; } catch (error) { return; }
  const info = message?.info;
  if (!info || typeof info !== "object") return;
  if (Number.isFinite(info.currentTime)) state.youtubeTime = info.currentTime;
  if (Number.isFinite(info.duration)) state.youtubeDuration = info.duration;
  if (Number.isFinite(info.currentTime) || Number.isFinite(info.duration)) {
    $("seek").max = Math.max(state.youtubeDuration, 1);
    $("seek").value = state.youtubeTime;
    $("clock").textContent = `${formatTime(state.youtubeTime)} / ${formatTime(state.youtubeDuration)}`;
  }
  if (Number.isInteger(info.playerState)) {
    const previous = state.youtubeState;
    state.youtubeState = info.playerState;
    $("play").textContent = info.playerState === 1 ? "❚❚" : "▶";
    if (info.playerState === 0 && previous !== 0) next(1);
  }
});

$("play").onclick = togglePlay;
$("previous").onclick = () => next(-1);
$("next").onclick = () => next(1);
$("seek").oninput = (e) => {
  const raw = Number(e.target.value), max = Number(e.target.max || 1);
  const dur = state.native ? (state.native.duration ? state.native.duration() : 0)
            : (!youtubeFrame.hidden ? state.youtubeDuration : (media.duration || 0));
  const value = (dur > 0 && max > 0) ? (raw / max) * dur : raw;
  if (!Number.isFinite(value) || value < 0) return;
  if (state.native) state.native.seek(value);
  else if (!youtubeFrame.hidden) youtubeCommand("seekTo", [value, true]);
  else if (media.readyState > 0) media.currentTime = value;
};
$("volume").oninput = (e) => {
  const value = Number(e.target.value);
  media.volume = value;
  state.native?.setVolume(value);
  if (!youtubeFrame.hidden) youtubeCommand("setVolume", [Math.round(value * 100)]);
  try { localStorage.setItem("pureweb.volume", String(value)); } catch (error) {}
};
$("mute").onclick = () => {
  if (state.native) { state.native.setMute(!state.native.muted); $("mute").textContent = state.native.muted ? "🔇" : "🔊"; }
  else {
    media.muted = !media.muted;
    if (!youtubeFrame.hidden) youtubeCommand(media.muted ? "mute" : "unMute");
    $("mute").textContent = media.muted ? "🔇" : "🔊";
  }
};
$("shuffle").onclick = (e) => {
  state.shuffle = !state.shuffle;
  e.currentTarget.textContent = state.shuffle ? "Shuffle on" : "Shuffle";
  e.currentTarget.classList.toggle("on", state.shuffle);
  e.currentTarget.setAttribute("aria-pressed", String(state.shuffle));
};
function cycleRepeat() {
  $("repeat").textContent = state.repeat === "off" ? "Repeat off" : state.repeat === "all" ? "Repeat all" : "Repeat one";
  $("repeat").classList.toggle("on", state.repeat !== "off");
  $("repeat").setAttribute("aria-pressed", String(state.repeat !== "off"));
}
$("repeat").onclick = (e) => {
  state.repeat = state.repeat === "off" ? "all" : state.repeat === "all" ? "one" : "off";
  cycleRepeat();
};
cycleRepeat();
$("ab-loop").onclick = setAbLoop;
$("snapshot").onclick = saveSnapshot;
$("speed").onclick = cycleSpeed;
$("fullscreen").onclick = toggleFullscreen;
document.addEventListener("fullscreenchange", () => {
  $("fullscreen").classList.toggle("on", !!document.fullscreenElement);
  $("fullscreen").setAttribute("aria-pressed", String(!!document.fullscreenElement));
});
$("pip").onclick = () => {
  if (state.native || !youtubeFrame.hidden) toast("Picture-in-picture is unavailable for this playback mode");
  else media.requestPictureInPicture?.().catch((error) => toast(error.message));
};
for (const kind of ["video", "audio", "subtitle"]) {
  $(`#${kind}-track`).onchange = (e) => {
    if (state.native) {
      const value = e.target.value === "" ? null : Number(e.target.value);
      state.native.selectTrack(kind, value)
        .then(() => toast(`${kind[0].toUpperCase() + kind.slice(1)} track changed`))
        .catch((error) => toast(error.message));
      return;
    }
    if (kind === "subtitle") {
      [...media.textTracks].forEach((track, index) =>
        track.mode = e.target.value !== "" && index === Number(e.target.value) ? "showing" : "disabled");
    }
  };
}
$("viz-toggle").onclick = (e) => {
  state.viz = !state.viz;
  e.currentTarget.classList.toggle("on", state.viz);
  e.currentTarget.setAttribute("aria-pressed", String(state.viz));
  if (state.viz) startViz(state.items[state.index]);
  else stopViz();
};

// ---------------------------------------------------------------------------
// navigation + dialogs + persistence
// ---------------------------------------------------------------------------
const picker = () => $("file-input").click();
["#add-more", "#queue-open"].forEach((id) => $(id).onclick = picker);
$("queue-url").onclick = () => { $("url-value").value = ""; $("url-dialog").showModal(); };
$("open-casu").onclick = () => setView("casu");
$("back-button").onclick = () => setView("now");
document.querySelectorAll(".nav[data-view='now']").forEach((node) => node.onclick = () => setView("now"));
document.querySelectorAll(".nav[data-view]").forEach((node) =>
  node.onclick = () => setView(node.dataset.view));
$("open-epg").onclick = () => { renderEpgDialog(); $("epg-dialog").showModal(); };
$("open-search-youtube").onclick = () => {
  $("search-mode-note").textContent = state.backend.search
    ? "Search and resolve via the configured server endpoint"
    : "Paste a YouTube link to play — the IFrame Player API needs no backend";
  $("search-results").replaceChildren();
  $("search-dialog").showModal();
};
$("open-options").onclick = () => $("options-dialog").showModal();
$("file-input").onchange = async (e) => { await addFiles(e.target.files); e.target.value = ""; };
$("search").oninput = renderQueue;
$("url-confirm").onclick = () => { const v = $("url-value").value.trim(); if (v) { openUrl(v); $("url-dialog").close(); } };
$("search-run").onclick = () => { const v = $("search-query").value.trim(); if (v) { openUrl(v); $("search-dialog").close(); } };
$("search-query").addEventListener("keydown", (e) => { if (e.key === "Enter") $("search-run").click(); });
$("epg-load").onclick = () => { $("file-input").click(); };
$("epg-fetch").onclick = async () => {
  try { await loadRemoteCatalog($("epg-url").value.trim()); }
  catch (error) { toast(error.message); }
};
$("queue-toggle").onclick = () => {
  const shell = document.querySelector(".app-shell");
  if (shell.classList.contains("embed-mode")) shell.classList.toggle("queue-collapsed");
  else shell.classList.toggle("show-queue");
};
$("move-up").onclick = () => moveRows(-1);
$("move-down").onclick = () => moveRows(1);
$("remove").onclick = () => { if (selectedRows().length) removeRows(); else toast("Select rows first (Ctrl/Shift click)"); };
$("rename").onclick = () => { if (state.selected >= 0) renameIndex(state.selected); };
$("save-pl").onclick = savePlaylist;
$("clear-all").onclick = () => {
  state.items.forEach(releaseItem);
  state.objectUrls.forEach(URL.revokeObjectURL);
  state.objectUrls.clear();
  state.items = [];
  state.index = -1;
  state.selected = -1;
  stopAll();
  renderQueue();
  persistQueue();
};

function savePlaylist() {
  const urls = state.items.filter((item) => item.url && !item.file).map((item) => item.url);
  if (!urls.length) { toast("No network items to save"); return; }
  const content = "#EXTM3U\n" + urls.map((url) => `#EXTINF:-1,${itemLabel(state.items.find((i) => i.url === url))}\n${url}`).join("\n");
  const blob = new Blob([content], { type: "audio/x-mpegurl" });
  const url = URL.createObjectURL(blob), link = document.createElement("a");
  link.href = url; link.download = "mpcasu-playlist.m3u"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ---------------------------------------------------------------------------
// persistence (localStorage) — network/YouTube items only
// ---------------------------------------------------------------------------
const STORE_KEY = "pureweb.queue.v1";
function persistQueue() {
  try {
    const items = state.items.filter((item) => item.url && !item.file).map((item) => ({
      url: item.url, title: item.title, subtitle: item.subtitle, kind: item.kind,
      playlist: item.playlist || "",
    }));
    localStorage.setItem(STORE_KEY, JSON.stringify(items));
  } catch (error) { /* storage is best-effort */ }
}
function restoreQueue() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (!raw) return;
    const items = JSON.parse(raw);
    if (!Array.isArray(items)) return;
    state.suppressAutoplay = true;
    let restored = 0;
    try {
      for (const entry of items) {
        if (!entry || typeof entry.url !== "string") continue;
        const item = { url: entry.url, title: entry.title || entry.url, subtitle: entry.subtitle, kind: entry.kind || (youtubeId(entry.url) ? "youtube" : "stream") };
        if (entry.playlist) { item.playlist = entry.playlist; state.expanded.add(entry.playlist); }
        addItem(item);
        restored++;
      }
    } finally { state.suppressAutoplay = false; }
    if (restored) toast(`${restored} item(s) restored from the last session`);
  } catch (error) { /* storage is best-effort */ }
}

// ---------------------------------------------------------------------------
// drag & drop + keyboard
// ---------------------------------------------------------------------------
document.querySelector("#drop-zone").addEventListener("dragover", (e) => e.preventDefault());
document.querySelector("#drop-zone").addEventListener("drop", async (e) => {
  e.preventDefault();
  if (e.dataTransfer?.files?.length) await addFiles(e.dataTransfer.files);
  const text = e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain");
  if (text && /^https?:\/\//i.test(text.trim())) openUrl(text.trim());
});
document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, textarea, select, dialog")) return;
  if (e.code === "Space") { e.preventDefault(); togglePlay(); }
  else if (e.key === "ArrowRight" && e.shiftKey) next(1);
  else if (e.key === "ArrowLeft" && e.shiftKey) next(-1);
  else if (e.key === "f" || e.key === "F") toggleFullscreen();
  else if (e.key === "m" || e.key === "M") $("mute").click();
});

// ---------------------------------------------------------------------------
// init
// ---------------------------------------------------------------------------
async function preloadPlaylist() {
  const path = (window.PUREWEB || {}).playlist;
  if (!path) return;
  try {
    const response = await fetch(new URL(path, location.href), { cache: "no-store" });
    if (!response.ok) return; // no startup playlist on this host
    const text = await response.text();
    if (!text.trim().startsWith("#EXTM3U")) return;
    const file = new File([text], path.split("/").pop() || "playlist.m3u", { type: "audio/x-mpegurl" });
    state.suppressAutoplay = true;
    try { await addPlaylist(file, new Map(), new Set()); } finally { state.suppressAutoplay = false; }
    if (state.items.length) toast(`${state.items.length} radio station(s) loaded from ${file.name}`);
  } catch (error) { /* startup playlist is optional */ }
}
(async function init() {
  const embed = (window.PUREWEB || {}).embed ||
    new URLSearchParams(location.search).get("embed") === "1" ||
    window.self !== window.top; // embedded in an iframe anywhere
  if (embed) document.querySelector(".app-shell").classList.add("embed-mode");
  await detectBackend();
  // Load the queue only ONCE: a startup playlist is the canonical content and
  // must not be duplicated by a previous session's persisted items.
  if (!(window.PUREWEB || {}).playlist) restoreQueue();
  try {
    // Never start muted: localStorage.getItem returns null on a fresh browser
    // and Number(null) is 0 — which would mute every first load.
    let volume = 1;
    const raw = localStorage.getItem("pureweb.volume");
    if (raw !== null) {
      const parsed = Number(raw);
      if (Number.isFinite(parsed) && parsed >= 0 && parsed <= 1) volume = parsed;
    }
    media.volume = volume;
    $("volume").value = volume;
  } catch (error) {}
  await preloadPlaylist();
  // Never autoplay on load (browser autoplay policy + audio-context muting).
  // Like Webamp: the user clicks a station, which is the user gesture that
  // lets the AudioContext start, so streams actually produce sound.
  if (state.items.length) { state.selected = 0; renderQueue(); }
})();
