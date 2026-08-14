/* ==========================================================================
   MPCASU Web Media Player — Complete Rewrite
   ========================================================================== */

/* -- Polyfills / helpers -------------------------------------------------- */
const _window = window;
const { Uint8Array: _U8, Uint16Array: _U16, Int32Array: _I32,
        Float64Array: _F64, DataView, TextDecoder, TextEncoder,
        atob, btoa, fetch: _fetch, console: _console,
        Math: _Math, Date: _Date, performance: _perf,
        setTimeout: _st, clearTimeout: _ct, setInterval: _si, clearInterval: _ci,
        requestAnimationFrame: _raf, cancelAnimationFrame: _caf } = _window;

/* ==========================================================================
   CASU Binary Format Reader (unchanged from original)
   ========================================================================== */
const CASU = (() => {
  const MAGIC = 0x43415355;
  const VERSION = 2;
  const ChunkType = {
    STREAM_CONFIG: 1, VIDEO_KEY_STATE: 16, VIDEO_TILE_UPDATE: 17,
    AUDIO_BLOCK: 32, SUBTITLE_PACKET: 48, CHAPTER_TABLE: 64, END: 255
  };
  class Reader {
    constructor(buffer) {
      this.view = new DataView(buffer);
      this.offset = 0;
      this.streams = [];
      this.chunks = [];
    }
    readU32() { const v = this.view.getUint32(this.offset, false); this.offset += 4; return v; }
    readU16() { const v = this.view.getUint16(this.offset, false); this.offset += 2; return v; }
    readU8() { const v = this.view.getUint8(this.offset); this.offset += 1; return v; }
    readBytes(n) { const b = new Uint8Array(this.view.buffer, this.offset, n); this.offset += n; return b; }
    readString() {
      const len = this.readU32();
      const bytes = new Uint8Array(this.view.buffer, this.offset, len);
      this.offset += len;
      return new TextDecoder().decode(bytes);
    }
    open() {
      const magic = this.readU32();
      if (magic !== MAGIC) throw new Error("Not a CASU file");
      const version = this.readU32();
      if (version > VERSION) throw new Error("Unsupported CASU version: " + version);
      this.readU32(); // flags
      const manifestLen = this.readU32();
      this.manifest = JSON.parse(new TextDecoder().decode(this.readBytes(manifestLen)));
      while (this.offset < this.view.byteLength - 4) {
        const chunkType = this.readU8();
        if (chunkType === 255) break;
        const streamId = this.readU8();
        const pts = this.readU32();
        const payloadLen = this.readU32();
        this.chunks.push({ type: chunkType, streamId, pts, payload: this.readBytes(payloadLen) });
      }
      return this.manifest;
    }
  }
  return { Reader, ChunkType };
})();

/* ==========================================================================
   Utility functions
   ========================================================================== */
function fmtTime(s) {
  if (!s || !isFinite(s)) return '0:00';
  const m = _Math.floor(s / 60);
  const sec = _Math.floor(s % 60);
  return m + ':' + (sec < 10 ? '0' : '') + sec;
}

function extname(path) {
  const i = path.lastIndexOf('.');
  return i !== -1 ? path.slice(i).toLowerCase() : '';
}

function basename(path) {
  const i = path.lastIndexOf('/');
  return i !== -1 ? path.slice(i + 1) : path;
}

/* ==========================================================================
   Playlist parsers (M3U, PLS, JSON)
   ========================================================================== */
const PlaylistParsers = {
  parseM3U(text, baseUrl) {
    const lines = text.split('\n');
    const tracks = [];
    let meta = null;
    for (let line of lines) {
      line = line.trim();
      if (!line) continue;
      if (line.startsWith('#EXTINF:')) {
        const ci = line.indexOf(',');
        if (ci !== -1) {
          const info = line.slice(ci + 1).trim();
          const di = info.indexOf(' - ');
          if (di !== -1) meta = { artist: info.slice(0, di).trim(), title: info.slice(di + 3).trim() };
          else meta = { artist: 'Radio', title: info };
        }
      } else if (!line.startsWith('#')) {
        tracks.push({
          metaData: meta || { artist: 'Stream', title: basename(line) },
          url: line
        });
        meta = null;
      }
    }
    return tracks;
  },

  parsePLS(text) {
    const lines = text.split('\n');
    const tracks = [];
    let entry = {};
    for (let line of lines) {
      line = line.trim();
      if (!line || line.startsWith('[')) continue;
      const [key, ...rest] = line.split('=');
      const val = rest.join('=').trim();
      const lk = key.trim().toLowerCase();
      if (lk === 'file1') entry.url = val;
      else if (lk === 'title1') entry.title = val;
      else if (lk === 'length1') entry.duration = parseInt(val, 10);
      if (entry.url && entry.title) {
        tracks.push({ metaData: { artist: 'Stream', title: entry.title }, url: entry.url });
        entry = {};
      }
    }
    if (entry.url) tracks.push({ metaData: { artist: 'Stream', title: entry.title || basename(entry.url) }, url: entry.url });
    return tracks;
  },

  parseJSON(text) {
    const data = JSON.parse(text);
    const arr = Array.isArray(data) ? data : (data.tracks || data.playlist || []);
    return arr.map(t => ({
      metaData: { artist: t.artist || t.metaData?.artist || '', title: t.title || t.metaData?.title || basename(t.url || '') },
      url: t.url || t.file || ''
    })).filter(t => t.url);
  }
};

/* ==========================================================================
   Stream relay config (from webamp-embed)
   ========================================================================== */
const STREAM_RELAY = {
  "https://securestreams5.autopo.st:1860/error": "error",
  "https://securestreams5.autopo.st:1860/TELEFON": "telefon",
  "https://listen.undergroundbass.com:8804/stream": "underground",
  "https://ice.bassdrive.net/stream": "bassdrive",
  "https://st01.sslstream.dlf.de/dlf/01/128/mp3/stream.mp3": "dlf",
  "https://icecast.ndr.de/ndr/ndr1niedersachsen/lueneburg/mp3/128/stream.mp3": "ndr",
  "https://dispatcher.rndfnk.com/hr/hrinfo/live/mp3/high": "hrinfo",
  "https://streaming.radio-r.net/radio-r": "radior",
  "https://streaming.fueralle.org/fsk.mp3": "fsk",
  "https://stream.radiox.de:8443/live": "radiox",
  "https://mp3.querfunk.de/qfhi": "querfunk",
  "https://stream.laut.fm/local_heroes": "localheroes",
  "http://www.rdl.de:8000/rdl": "rdl",
  "https://www.radioeins.de/livemp3": "radioeins",
  "https://bytefm.cast.addradio.de/bytefm/main/mid/stream": "bytefm",
  "https://dispatcher.rndfnk.com/hr/hr3/live/mp3/high": "hr3",
  "https://liveradio.swr.de/sw282p3/swr3/play.mp3": "swr3",
  "https://streams.deltaradio.de/delta-live/mp3-192/mediaplayer": "delta",
  "https://wdr-1live-live.icecast.wdr.de/wdr/1live/live/mp3/128/stream.mp3": "onelive",
  "https://dispatcher.rndfnk.com/rbb/fritz/live/mp3/mid": "fritz",
  "https://ice5.somafm.com/groovesalad-256-mp3": "soma",
  "https://stream.laut.fm/inklusion": "bhr",
  "http://65.108.124.70:7200/stream": "jesus",
  "https://radio.streemlion.com:1965/stream": "chill",
  "http://radio.streemlion.com:1960/stream": "chill"
};

/* ==========================================================================
   Waveform Visualizer (canvas)
   ========================================================================== */
class WaveformVisualizer {
  constructor(canvas, analyser) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.analyser = analyser;
    this.running = false;
    this.animId = null;
    this.barWidth = 3;
    this.gap = 1;
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.resize();
    this.draw();
  }

  stop() {
    this.running = false;
    if (this.animId) { _caf(this.animId); this.animId = null; }
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
  }

  resize() {
    const dpr = window.devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.ctx.scale(dpr, dpr);
  }

  draw() {
    if (!this.running) return;
    const { canvas, ctx, analyser } = this;
    const w = canvas.width / (window.devicePixelRatio || 1);
    const h = canvas.height / (window.devicePixelRatio || 1);
    ctx.clearRect(0, 0, w, h);

    if (analyser) {
      const bufferLength = analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      analyser.getByteFrequencyData(dataArray);

      const step = _Math.ceil(bufferLength / (w / (this.barWidth + this.gap)));
      let x = 0;
      for (let i = 0; i < bufferLength && x < w; i += step) {
        const value = dataArray[i] / 255;
        const barH = value * h * 0.9;
        ctx.fillStyle = value > 0.6 ? '#FF1E2D' : value > 0.3 ? '#FF6B77' : '#F2F2F2';
        ctx.fillRect(x, h - barH, this.barWidth, barH);
        x += this.barWidth + this.gap;
      }
    }

    this.animId = _raf(() => this.draw());
  }
}

/* ==========================================================================
   MPCASUPlayer — Main Player Class
   ========================================================================== */
function MPCASUPlayer(containerId) {
  /* ---- State ---- */
  const self = this;
  const container = document.getElementById(containerId);
  if (!container) { _console.error('Container not found: ' + containerId); return; }

  let state = 'STOPPED';      // STOPPED | PLAYING | PAUSED | ENDED | ERROR
  let audioCtx = null;
  let sourceNode = null;
  let gainNode = null;
  let analyserNode = null;
  let currentFile = null;      // File or {url, metaData}
  let currentUrl = '';
  let duration = 0;
  let position = 0;
  let volume = 0.8;
  let prevVolume = volume;
  let isMuted = false;
  let playlist = [];
  let currentIndex = -1;
  let isRadioMode = false;
  let waveform = null;
  let continuousRelayAvail = false;
  let relayConnectedAt = 0;
  let relayReconnectTimer = null;

  /* ---- DOM refs ---- */
  let el = {};
  let sidebarBtns = {};

  /* =======================================================================
     BUILD UI
     ======================================================================= */
  function build() {
    container.innerHTML = '';
    container.style.cssText = 'background:#090B0D;color:#F2F2F2;font-family:"Segoe UI",system-ui,-apple-ui,sans-serif;display:flex;flex-direction:column;height:100vh;margin:0;overflow:hidden';

    // -- Top bar --
    const topBar = c('div', { style: 'display:flex;align-items:center;padding:12px 20px;background:#111418;border-bottom:2px solid #FF1E2D;flex-shrink:0' });
    const logo = c('span', { text: 'MPCASU', style: 'color:#FF1E2D;font-size:20px;font-weight:bold;letter-spacing:2px' });
    topBar.appendChild(logo);
    const subtitle = c('span', { text: 'MEDIA PLAYER', style: 'color:#686E75;font-size:11px;margin-left:10px;letter-spacing:3px' });
    topBar.appendChild(subtitle);
    // Radio indicator
    const radioInd = c('span', { id: 'mpcasu-radio-ind', text: '', style: 'color:#FF1E2D;font-size:10px;margin-left:auto;letter-spacing:1px;border:1px solid #FF1E2D;border-radius:4px;padding:2px 8px;display:none' });
    topBar.appendChild(radioInd);

    // -- Main area (sidebar + content) --
    const main = c('div', { style: 'display:flex;flex:1;overflow:hidden' });

    // -- Sidebar --
    const sidebar = c('div', { className: 'sidebar', style: 'width:220px;background:#111418;padding:10px 0;flex-shrink:0;overflow-y:auto;border-right:1px solid #1E2328' });

    const menuItems = [
      { key: 'library',  label: 'LIBRARY',    icon: '📂' },
      { key: 'playlist', label: 'PLAYLIST',   icon: '📋' },
      { key: 'streams',  label: 'STREAMS',    icon: '📻' },
      { key: 'youtube',  label: 'YOUTUBE',    icon: '▶️' },
      { key: 'settings', label: 'SETTINGS',   icon: '⚙️' }
    ];

    menuItems.forEach(item => {
      const btn = c('div', {
        style: 'padding:10px 20px;cursor:pointer;color:#A7ABB0;font-size:12px;letter-spacing:1px;border-left:3px solid transparent;display:flex;align-items:center;gap:10px',
        mouseover() { this.style.background = '#14181D'; this.style.color = '#F2F2F2'; },
        mouseout()  { this.style.background = 'transparent'; this.style.color = '#A7ABB0'; },
        click()     { showView(item.key); }
      });
      const iconSpan = c('span', { text: item.icon, style: 'font-size:14px' });
      const labelSpan = c('span', { text: item.label });
      btn.appendChild(iconSpan);
      btn.appendChild(labelSpan);
      sidebar.appendChild(btn);
      sidebarBtns[item.key] = btn;
    });

    // -- Content area --
    const content = c('div', { style: 'flex:1;display:flex;flex-direction:column;background:#090B0D;overflow:hidden;position:relative' });

    // -- View panels (hidden by default, shown via showView) --
    const viewPanels = document.createElement('div');
    viewPanels.id = 'mpcasu-view-panels';
    viewPanels.style.cssText = 'display:none;position:absolute;top:0;left:0;right:0;bottom:0;background:#0D0F13;z-index:100;overflow-y:auto;padding:20px';
    content.appendChild(viewPanels);

    // -- Video area --
    const videoArea = c('div', { id: 'mpcasu-video', style: 'flex:1;display:flex;align-items:center;justify-content:center;background:#000;position:relative;min-height:200px' });
    const videoEl = c('video', { id: 'mpcasu-video-el', style: 'max-width:100%;max-height:100%;display:none' });
    videoEl.controls = false;
    videoEl.preload = 'auto';
    videoArea.appendChild(videoEl);

    // -- Audio waveform area --
    const audioArea = c('div', { id: 'mpcasu-audio', style: 'flex:1;display:none;align-items:center;justify-content:center;flex-direction:column;position:relative;background:#06080A' });
    const waveformCanvas = c('canvas', { id: 'mpcasu-waveform', style: 'width:100%;height:100%;position:absolute;top:0;left:0' });
    audioArea.appendChild(waveformCanvas);
    const audioCenter = c('div', { style: 'position:relative;z-index:2;text-align:center;pointer-events:none' });
    const audioIcon = c('div', { text: '♪', style: 'font-size:64px;color:#FF1E2D;opacity:0.3' });
    audioCenter.appendChild(audioIcon);
    const audioTitle = c('div', { id: 'mpcasu-nowplaying', text: 'No media loaded', style: 'color:#A7ABB0;font-size:16px;margin-top:12px' });
    audioCenter.appendChild(audioTitle);
    const audioArtist = c('div', { id: 'mpcasu-artist', text: '', style: 'color:#686E75;font-size:13px;margin-top:4px' });
    audioCenter.appendChild(audioArtist);
    audioArea.appendChild(audioCenter);

    // -- Cover art --
    const coverArt = c('img', { id: 'mpcasu-cover', style: 'width:120px;height:120px;border-radius:8px;object-fit:cover;margin-top:12px;display:none;border:1px solid #1E2328;pointer-events:none' });
    audioCenter.appendChild(coverArt);

    content.appendChild(videoArea);
    content.appendChild(audioArea);

    // -- Now playing bar --
    const nowPlayingBar = c('div', { id: 'mpcasu-nowplaying-bar', text: 'Ready', style: 'padding:4px 16px;color:#686E75;font-size:11px;background:#111418;border-top:1px solid #1E2328;flex-shrink:0' });
    content.appendChild(nowPlayingBar);

    // -- Timeline --
    const timeline = c('div', { style: 'padding:6px 16px;background:#111418;flex-shrink:0' });
    const timeBar = c('div', { id: 'mpcasu-timebar', style: 'position:relative;height:4px;background:#24282D;border-radius:2px;cursor:pointer' });
    const timeProgress = c('div', { id: 'mpcasu-progress', style: 'height:100%;width:0%;background:#FF1E2D;border-radius:2px;transition:width 0.05s linear' });
    timeBar.appendChild(timeProgress);
    timeline.appendChild(timeBar);
    const timeLabels = c('div', { style: 'display:flex;justify-content:space-between;margin-top:3px;font-size:10px;color:#686E75' });
    timeLabels.innerHTML = '<span id="mpcasu-current">0:00</span><span id="mpcasu-duration">0:00</span>';
    timeline.appendChild(timeLabels);

    // -- Transport --
    const transport = c('div', { style: 'display:flex;align-items:center;justify-content:center;padding:8px 16px;background:#111418;gap:8px;flex-shrink:0;border-top:1px solid #1E2328;flex-wrap:wrap' });

    function mkBtn(text, action, extraStyle) {
      const b = c('button', {
        text,
        style: 'background:transparent;color:#F2F2F2;border:none;font-size:16px;cursor:pointer;padding:6px 12px;border-radius:4px;transition:all 0.2s' + (extraStyle ? ';' + extraStyle : ''),
        mouseover() { if (!extraStyle) this.style.background = '#3A1015'; },
        mouseout()  { if (!extraStyle) this.style.background = 'transparent'; },
        click: action
      });
      return b;
    }

    const btnPrev  = mkBtn('⏮', () => prev());
    const btnPlay  = mkBtn('▶', () => playPause(), 'font-size:24px;padding:6px 16px;background:#FF1E2D;border-radius:50%');
    btnPlay.id = 'mpcasu-playbtn';
    const btnNext  = mkBtn('⏭', () => next());
    const btnStop  = mkBtn('⏹', () => stop());

    transport.appendChild(btnPrev);
    transport.appendChild(btnPlay);
    transport.appendChild(btnNext);
    transport.appendChild(btnStop);

    // -- Volume --
    const volBtn = c('button', {
      id: 'mpcasu-volbtn',
      text: '🔊',
      style: 'background:transparent;color:#F2F2F2;border:none;font-size:14px;cursor:pointer;padding:6px',
      click() { toggleMute(); }
    });
    transport.appendChild(volBtn);

    const volSlider = c('input', {
      id: 'mpcasu-volslider',
      type: 'range', min: 0, max: 100, value: 80,
      style: 'width:80px;accent-color:#FF1E2D;background:#24282D;height:4px;border-radius:2px',
      input() { setVolume(this.value / 100); }
    });
    transport.appendChild(volSlider);

    // -- Info text --
    const info = c('span', {
      id: 'mpcasu-info',
      text: 'Drop files or click to open',
      style: 'color:#686E75;font-size:11px;margin-left:8px;cursor:pointer',
      click() { fileInput.click(); }
    });
    transport.appendChild(info);

    main.appendChild(sidebar);
    main.appendChild(content);
    container.appendChild(topBar);
    container.appendChild(main);
    container.appendChild(nowPlayingBar);
    container.appendChild(timeline);
    container.appendChild(transport);

    // -- Hidden file input --
    const fileInput = c('input', {
      type: 'file',
      accept: '.mp4,.mp3,.webm,.ogg,.wav,.flac,.aac,.m4a,.mkv,.casu,.m3u,.pls,.json',
      style: 'display:none',
      change(e) {
        if (e.target.files.length) handleFiles(e.target.files);
        e.target.value = '';
      }
    });
    container.appendChild(fileInput);

    // -- Drag & drop --
    container.ondragover = e => { e.preventDefault(); container.style.borderColor = '#FF1E2D'; };
    container.ondragleave = () => { container.style.borderColor = 'transparent'; };
    container.ondrop = e => {
      e.preventDefault();
      container.style.borderColor = 'transparent';
      if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
      const url = e.dataTransfer.getData('text/plain') || e.dataTransfer.getData('text/uri-list');
      if (url) addStreamUrl(url);
    };
    videoArea.onclick = () => fileInput.click();

    // -- Timeline seeking --
    timeBar.addEventListener('click', e => {
      const rect = timeBar.getBoundingClientRect();
      const pct = (e.clientX - rect.left) / rect.width;
      seek(pct * duration);
    });

    // -- Keyboard shortcuts --
    document.addEventListener('keydown', e => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      switch (e.code) {
        case 'Space': e.preventDefault(); playPause(); break;
        case 'ArrowLeft': seek((position || 0) - 5); break;
        case 'ArrowRight': seek((position || 0) + 5); break;
        case 'ArrowUp': setVolume(_Math.min(1, volume + 0.1)); volSlider.value = volume * 100; break;
        case 'ArrowDown': setVolume(_Math.max(0, volume - 0.1)); volSlider.value = volume * 100; break;
        case 'KeyM': toggleMute(); break;
        case 'KeyS': stop(); break;
      }
    });

    el = {
      topBar, sidebar, content, videoArea, audioArea, videoEl,
      waveformCanvas, audioIcon, audioTitle, audioArtist, coverArt,
      nowPlayingBar, timeBar, timeProgress, timeLabels,
      currentTime: document.getElementById('mpcasu-current'),
      durationTime: document.getElementById('mpcasu-duration'),
      playBtn: btnPlay, volBtn, volSlider, info, fileInput,
      radioInd, viewPanels, transport
    };
  }

  /* =======================================================================
     HELPERS: create element
     ======================================================================= */
  function c(tag, opts = {}) {
    const el = document.createElement(tag);
    if (opts.id) el.id = opts.id;
    if (opts.className) el.className = opts.className;
    if (opts.text) el.textContent = opts.text;
    if (opts.html) el.innerHTML = opts.html;
    if (opts.style) el.style.cssText = opts.style;
    for (const attr of ['type', 'min', 'max', 'value', 'accept']) {
      if (opts[attr] !== undefined) el.setAttribute(attr, opts[attr]);
    }
    if (opts.src) el.src = opts.src;
    if (opts.click) el.addEventListener('click', opts.click);
    if (opts.change) el.addEventListener('change', opts.change);
    if (opts.input) el.addEventListener('input', opts.input);
    if (opts.mouseover) el.addEventListener('mouseover', opts.mouseover);
    if (opts.mouseout) el.addEventListener('mouseout', opts.mouseout);
    return el;
  }

  /* =======================================================================
     VIEWS (sidebar panels)
     ======================================================================= */
  function showView(view) {
    const panel = el.viewPanels;
    panel.innerHTML = '';
    panel.style.display = 'block';

    // Highlight active sidebar
    Object.keys(sidebarBtns).forEach(k => {
      sidebarBtns[k].style.borderLeftColor = k === view ? '#FF1E2D' : 'transparent';
      sidebarBtns[k].style.color = k === view ? '#F2F2F2' : '#A7ABB0';
    });

    switch (view) {
      case 'library':  renderLibraryView(panel);  break;
      case 'playlist': renderPlaylistView(panel); break;
      case 'streams':  renderStreamsView(panel);  break;
      case 'youtube':  renderYoutubeView(panel);  break;
      case 'settings': renderSettingsView(panel); break;
    }
  }

  function closeView() {
    el.viewPanels.style.display = 'none';
    el.viewPanels.innerHTML = '';
    Object.keys(sidebarBtns).forEach(k => {
      sidebarBtns[k].style.borderLeftColor = 'transparent';
      sidebarBtns[k].style.color = '#A7ABB0';
    });
  }

  /* ---- LIBRARY: browse local files ---- */
  function renderLibraryView(panel) {
    panel.innerHTML = '';
    appendStyle(panel, 'h2', 'LIBRARY', 'color:#FF1E2D;font-size:16px;margin-bottom:16px;letter-spacing:2px');

    const desc = c('p', { text: 'Load media files from your device.', style: 'color:#A7ABB0;font-size:12px;margin-bottom:16px' });
    panel.appendChild(desc);

    const browseBtn = c('button', {
      text: '📂  Browse Files',
      style: 'background:#FF1E2D;color:#FFF;border:none;padding:10px 24px;font-size:13px;border-radius:6px;cursor:pointer;letter-spacing:1px',
      click() { el.fileInput.click(); }
    });
    panel.appendChild(browseBtn);

    const hint = c('p', { text: 'Or drag & drop files anywhere on the player.', style: 'color:#686E75;font-size:11px;margin-top:12px' });
    panel.appendChild(hint);

    // Quick format info
    const formats = c('div', { style: 'margin-top:20px;color:#686E75;font-size:11px;line-height:1.8' });
    formats.innerHTML = '<b style="color:#A7ABB0">Supported formats:</b><br>Video: MP4, WebM, OGG, MKV<br>Audio: MP3, WAV, FLAC, AAC, M4A<br>Playlists: M3U, PLS, JSON<br>Binary: CASU';
    panel.appendChild(formats);
  }

  /* ---- PLAYLIST: manage current playlist ---- */
  function renderPlaylistView(panel) {
    panel.innerHTML = '';
    appendStyle(panel, 'h2', 'PLAYLIST', 'color:#FF1E2D;font-size:16px;margin-bottom:16px;letter-spacing:2px');

    const controls = c('div', { style: 'display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap' });

    const loadM3uBtn = c('button', {
      text: '📂 Load M3U',
      style: 'background:#1E2328;color:#F2F2F2;border:1px solid #3A1015;padding:6px 14px;font-size:11px;border-radius:4px;cursor:pointer',
      click() {
        const input = c('input', { type: 'file', accept: '.m3u,.pls,.json', style: 'display:none',
          change(e) {
            if (e.target.files[0]) loadPlaylistFile(e.target.files[0]);
            e.target.value = '';
          }
        });
        panel.appendChild(input);
        input.click();
      }
    });
    controls.appendChild(loadM3uBtn);

    const clearBtn = c('button', {
      text: '🗑 Clear',
      style: 'background:#1E2328;color:#F2F2F2;border:1px solid #3A1015;padding:6px 14px;font-size:11px;border-radius:4px;cursor:pointer',
      click() { playlist = []; currentIndex = -1; renderPlaylistView(panel); updateUI(); }
    });
    controls.appendChild(clearBtn);

    panel.appendChild(controls);

    if (playlist.length === 0) {
      const empty = c('p', { text: 'Playlist is empty. Drop files or load a playlist file.', style: 'color:#686E75;font-size:12px' });
      panel.appendChild(empty);
      return;
    }

    const list = c('ul', {
      id: 'mpcasu-playlist-ui',
      style: 'list-style:none;padding:0;margin:0;max-height:400px;overflow-y:auto'
    });

    playlist.forEach((item, idx) => {
      const li = c('li', {
        style: 'display:flex;align-items:center;padding:6px 8px;margin:2px 0;background:' + (idx === currentIndex ? '#1E2328' : 'transparent') + ';border-radius:4px;cursor:grab;border-left:3px solid ' + (idx === currentIndex ? '#FF1E2D' : 'transparent'),
        draggable: true
      });

      const idxLabel = c('span', { text: (idx + 1) + '.', style: 'color:#686E75;font-size:10px;width:24px;flex-shrink:0' });
      li.appendChild(idxLabel);

      const nameSpan = c('span', {
        text: item.metaData?.title || item.name || basename(item.url || ''),
        style: 'flex:1;font-size:12px;color:#F2F2F2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap',
        click() { playIndex(idx); closeView(); }
      });
      li.appendChild(nameSpan);

      const delBtn = c('button', {
        text: '✕',
        style: 'background:transparent;color:#686E75;border:none;cursor:pointer;font-size:12px;padding:2px 6px',
        click(e) { e.stopPropagation(); playlist.splice(idx, 1); if (currentIndex >= playlist.length) currentIndex = playlist.length - 1; renderPlaylistView(panel); updateUI(); }
      });
      li.appendChild(delBtn);

      // Drag and drop reorder
      li.addEventListener('dragstart', e => {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', idx);
        li.style.opacity = '0.4';
      });
      li.addEventListener('dragend', () => { li.style.opacity = '1'; });
      li.addEventListener('dragover', e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; li.style.background = '#3A1015'; });
      li.addEventListener('dragleave', () => { li.style.background = idx === currentIndex ? '#1E2328' : 'transparent'; });
      li.addEventListener('drop', e => {
        e.preventDefault();
        const fromIdx = parseInt(e.dataTransfer.getData('text/plain'), 10);
        if (fromIdx !== idx && fromIdx >= 0 && fromIdx < playlist.length) {
          const [item] = playlist.splice(fromIdx, 1);
          const toIdx = fromIdx < idx ? idx - 1 : idx;
          playlist.splice(toIdx, 0, item);
          if (currentIndex === fromIdx) currentIndex = toIdx;
          else if (currentIndex > fromIdx && currentIndex <= toIdx) currentIndex--;
          else if (currentIndex < fromIdx && currentIndex >= toIdx) currentIndex++;
          renderPlaylistView(panel);
          updateUI();
        }
      });

      list.appendChild(li);
    });

    panel.appendChild(list);

    // -- Save playlist button --
    const saveBtn = c('button', {
      text: '💾 Save as M3U',
      style: 'background:#1E2328;color:#F2F2F2;border:1px solid #3A1015;padding:6px 14px;font-size:11px;border-radius:4px;cursor:pointer;margin-top:8px',
      click() { savePlaylistAsM3U(); }
    });
    panel.appendChild(saveBtn);
  }

  /* ---- STREAMS: URL input + radio presets ---- */
  function renderStreamsView(panel) {
    panel.innerHTML = '';
    appendStyle(panel, 'h2', 'STREAMS & RADIO', 'color:#FF1E2D;font-size:16px;margin-bottom:16px;letter-spacing:2px');

    // -- URL input --
    const urlRow = c('div', { style: 'display:flex;gap:8px;margin-bottom:16px' });
    const urlInput = c('input', {
      id: 'mpcasu-stream-url',
      type: 'text',
      placeholder: 'Enter stream URL (HTTP, HLS, RTSP)...',
      style: 'flex:1;background:#1E2328;color:#F2F2F2;border:1px solid #3A1015;padding:8px 12px;border-radius:4px;font-size:12px;outline:none'
    });
    urlRow.appendChild(urlInput);

    const addBtn = c('button', {
      text: '▶ Play',
      style: 'background:#FF1E2D;color:#FFF;border:none;padding:8px 16px;border-radius:4px;cursor:pointer;font-size:12px;letter-spacing:1px',
      click() {
        const url = urlInput.value.trim();
        if (url) addStreamUrl(url);
      }
    });
    urlRow.appendChild(addBtn);
    urlInput.addEventListener('keydown', e => { if (e.key === 'Enter') addBtn.click(); });

    panel.appendChild(urlRow);

    // -- Protocol hints --
    const hints = c('div', { style: 'color:#686E75;font-size:10px;margin-bottom:16px;line-height:1.6' });
    hints.innerHTML = 'Supported: <b>HTTP(S)</b> audio streams, <b>HLS</b> (.m3u8), <b>RTSP</b> streams. Some streams may require a relay backend.';
    panel.appendChild(hints);

    // -- Radio presets --
    appendStyle(panel, 'h3', '📻 RADIO PRESETS', 'color:#A7ABB0;font-size:13px;margin-bottom:8px;letter-spacing:1px');

    if (typeof RADIO_PRESETS !== 'undefined' && RADIO_PRESETS.length) {
      const grid = c('div', { style: 'display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:6px' });
      RADIO_PRESETS.forEach(p => {
        const card = c('div', {
          style: 'background:#1E2328;padding:10px 12px;border-radius:6px;cursor:pointer;border-left:3px solid #FF1E2D;transition:all 0.15s',
          mouseover() { this.style.background = '#2A3037'; },
          mouseout()  { this.style.background = '#1E2328'; },
          click() {
            addStreamUrl(p.url);
            // If radio mode is active, set the preset name
            el.radioInd.textContent = '🔴 LIVE: ' + p.name;
            el.radioInd.style.display = 'inline';
            closeView();
          }
        });
        const name = c('div', { text: p.name, style: 'color:#F2F2F2;font-size:12px;font-weight:bold;margin-bottom:2px' });
        card.appendChild(name);
        const urlShort = c('div', { text: p.url.length > 40 ? p.url.slice(0, 40) + '…' : p.url, style: 'color:#686E75;font-size:9px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap' });
        card.appendChild(urlShort);
        grid.appendChild(card);
      });
      panel.appendChild(grid);
    } else {
      const loadRadioBtn = c('button', {
        text: '📡 Load Radio Stations',
        style: 'background:#1E2328;color:#F2F2F2;border:1px solid #3A1015;padding:8px 16px;font-size:11px;border-radius:4px;cursor:pointer',
        click() { loadRadioPresets().then(() => renderStreamsView(panel)); }
      });
      panel.appendChild(loadRadioBtn);
    }
  }

  /* ---- YOUTUBE: YouTube URL input ---- */
  function renderYoutubeView(panel) {
    panel.innerHTML = '';
    appendStyle(panel, 'h2', 'YOUTUBE', 'color:#FF1E2D;font-size:16px;margin-bottom:16px;letter-spacing:2px');

    const desc = c('p', {
      text: 'Enter a YouTube URL to play audio. Uses yt-dlp API or invidious for direct streaming.',
      style: 'color:#A7ABB0;font-size:12px;margin-bottom:12px'
    });
    panel.appendChild(desc);

    const urlRow = c('div', { style: 'display:flex;gap:8px;margin-bottom:12px' });
    const ytInput = c('input', {
      id: 'mpcasu-yt-url',
      type: 'text',
      placeholder: 'https://youtube.com/watch?v=...',
      style: 'flex:1;background:#1E2328;color:#F2F2F2;border:1px solid #3A1015;padding:8px 12px;border-radius:4px;font-size:12px;outline:none'
    });
    urlRow.appendChild(ytInput);

    const fetchBtn = c('button', {
      text: '▶ Play',
      style: 'background:#FF1E2D;color:#FFF;border:none;padding:8px 16px;border-radius:4px;cursor:pointer;font-size:12px;letter-spacing:1px',
      click() {
        const url = ytInput.value.trim();
        if (url) loadYouTube(url);
      }
    });
    urlRow.appendChild(fetchBtn);
    ytInput.addEventListener('keydown', e => { if (e.key === 'Enter') fetchBtn.click(); });
    panel.appendChild(urlRow);

    // Status area
    const ytStatus = c('div', { id: 'mpcasu-yt-status', text: '', style: 'color:#686E75;font-size:11px;margin-top:8px' });
    panel.appendChild(ytStatus);

    // API config
    appendStyle(panel, 'h3', '⚙️ API CONFIGURATION', 'color:#A7ABB0;font-size:13px;margin:16px 0 8px;letter-spacing:1px');
    const apiLabel = c('label', { text: 'yt-dlp API endpoint:', style: 'color:#686E75;font-size:11px;display:block;margin-bottom:4px' });
    panel.appendChild(apiLabel);
    const apiInput = c('input', {
      id: 'mpcasu-yt-api',
      type: 'text',
      value: localStorage.getItem('mpcasu_yt_api') || '',
      placeholder: 'https://your-server.com/yt-dlp?url=',
      style: 'width:100%;background:#1E2328;color:#F2F2F2;border:1px solid #3A1015;padding:8px 12px;border-radius:4px;font-size:12px;outline:none;box-sizing:border-box',
      change() { localStorage.setItem('mpcasu_yt_api', this.value); }
    });
    panel.appendChild(apiInput);
    const apiHint = c('p', {
      text: 'The endpoint should accept ?url= and return JSON with {url, title, artist} or redirect to audio.',
      style: 'color:#686E75;font-size:10px;margin-top:6px'
    });
    panel.appendChild(apiHint);
  }

  /* ---- SETTINGS ---- */
  function renderSettingsView(panel) {
    panel.innerHTML = '';
    appendStyle(panel, 'h2', 'SETTINGS', 'color:#FF1E2D;font-size:16px;margin-bottom:16px;letter-spacing:2px');

    // Default volume
    appendStyle(panel, 'h3', '🔊 AUDIO', 'color:#A7ABB0;font-size:13px;margin-bottom:8px;letter-spacing:1px');
    const volRow = c('div', { style: 'display:flex;align-items:center;gap:12px;margin-bottom:12px' });
    const volLabel = c('span', { text: 'Default volume:', style: 'color:#686E75;font-size:12px' });
    volRow.appendChild(volLabel);
    const volSet = c('input', {
      type: 'range', min: 0, max: 100, value: volume * 100,
      style: 'flex:1;accent-color:#FF1E2D',
      input() {
        const v = this.value / 100;
        localStorage.setItem('mpcasu_volume', v);
        setVolume(v);
      }
    });
    volRow.appendChild(volSet);
    panel.appendChild(volRow);

    // Auto-play radio
    const autoRow = c('div', { style: 'display:flex;align-items:center;gap:8px;margin-bottom:12px' });
    const autoCheck = c('input', {
      type: 'checkbox',
      style: 'accent-color:#FF1E2D',
      change() { localStorage.setItem('mpcasu_autoradio', this.checked ? '1' : '0'); }
    });
    autoCheck.checked = localStorage.getItem('mpcasu_autoradio') === '1';
    autoRow.appendChild(autoCheck);
    const autoLabel = c('span', { text: 'Auto-start radio mode on load', style: 'color:#686E75;font-size:12px' });
    autoRow.appendChild(autoLabel);
    panel.appendChild(autoRow);

    // About
    appendStyle(panel, 'h3', 'ℹ️ ABOUT', 'color:#A7ABB0;font-size:13px;margin:16px 0 8px;letter-spacing:1px');
    const about = c('div', { style: 'color:#686E75;font-size:11px;line-height:1.8' });
    about.innerHTML = 'MPCASU Web Player v2.0<br>Dark theme player with CASU binary support<br>HTML5 video/audio streaming platform<br><br>© ' + new Date().getFullYear() + ' MPCASU Project';
    panel.appendChild(about);
  }

  function appendStyle(parent, tag, content, style) {
    const el = document.createElement(tag);
    el.textContent = content;
    el.style.cssText = style;
    parent.appendChild(el);
  }

  /* =======================================================================
     CORE PLAYBACK
     ======================================================================= */

  function handleFiles(files) {
    for (const file of files) {
      const ext = extname(file.name);
      if (ext === '.m3u' || ext === '.pls' || ext === '.json') {
        loadPlaylistFile(file);
      } else {
        addToPlaylist({ file, name: file.name, metaData: { title: file.name.replace(ext, ''), artist: '' } });
        if (playlist.length === 1 || currentIndex === -1) {
          loadFileItem(playlist[playlist.length - 1]);
        }
      }
    }
  }

  function addToPlaylist(item) {
    playlist.push(item);
    if (currentIndex === -1) currentIndex = 0;
    updateUI();
  }

  function loadPlaylistFile(file) {
    const reader = new FileReader();
    reader.onload = e => {
      const text = e.target.result;
      const ext = extname(file.name);
      let tracks = [];
      try {
        if (ext === '.m3u') tracks = PlaylistParsers.parseM3U(text);
        else if (ext === '.pls') tracks = PlaylistParsers.parsePLS(text);
        else if (ext === '.json') tracks = PlaylistParsers.parseJSON(text);
      } catch (err) {
        _console.error('Playlist parse error:', err);
        el.nowPlayingBar.textContent = 'Playlist parse error: ' + err.message;
        return;
      }
      tracks.forEach(t => addToPlaylist({ url: t.url, metaData: t.metaData, name: t.metaData?.title || basename(t.url) }));
      if (tracks.length && currentIndex >= 0) {
        loadFileItem(playlist[currentIndex]);
      }
      el.nowPlayingBar.textContent = 'Loaded ' + tracks.length + ' tracks from ' + file.name;
    };
    reader.readAsText(file);
  }

  function loadFileItem(item) {
    if (!item) return;
    currentFile = item;
    currentIndex = playlist.indexOf(item);
    isRadioMode = false;
    el.radioInd.style.display = 'none';

    const name = item.metaData?.title || item.name || basename(item.url || '');
    const artist = item.metaData?.artist || '';
    el.audioTitle.textContent = name;
    el.artist.textContent = artist;
    el.nowPlayingBar.textContent = 'Loading: ' + name;
    el.info.textContent = name;

    // Show cover art placeholder (use artist initial if no cover)
    const cover = el.coverArt;
    if (item.metaData?.cover) {
      cover.src = item.metaData.cover;
      cover.style.display = 'block';
    } else {
      cover.style.display = 'none';
    }

    const isAudio = item.file ? (item.file.type.startsWith('audio/') || /\.(mp3|wav|flac|ogg|m4a|aac)$/i.test(item.file.name)) : /\.(mp3|wav|flac|ogg|m4a|aac|m3u8)$/i.test(item.url || '');
    const isCasu = item.file ? /\.casu$/i.test(item.file.name) : /\.casu$/i.test(item.url || '');

    if (isCasu && item.file) {
      loadCasuFile(item.file);
      return;
    }

    const videoEl = el.videoEl;
    const url = item.url || (item.file ? URL.createObjectURL(item.file) : '');
    currentUrl = url;

    // Apply stream relay if applicable
    const finalUrl = applyStreamRelay(url);

    videoEl.src = finalUrl;
    videoEl.load();

    if (isAudio) {
      videoEl.style.display = 'none';
      el.audioArea.style.display = 'flex';
    } else {
      videoEl.style.display = 'block';
      el.audioArea.style.display = 'none';
    }

    setupAudioContext(videoEl);
    state = 'READY';
    updateUI();

    // Auto-play
    play();

    // Update playlist UI highlights
    if (document.getElementById('mpcasu-playlist-ui')) {
      renderPlaylistView(el.viewPanels);
    }
  }

  function applyStreamRelay(url) {
    if (!url) return url;
    const base = url.split('?')[0];
    if (STREAM_RELAY[base] || STREAM_RELAY[url]) {
      const id = STREAM_RELAY[base] || STREAM_RELAY[url];
      if (continuousRelayAvail) {
        return new URL('continuous-stream?id=' + id, window.location.href).href;
      } else {
        return new URL('stream.php?id=' + id, window.location.href).href;
      }
    }
    // HLS: if .m3u8, try proxying
    if (url.includes('.m3u8')) {
      // Use native HLS if available or CORS proxy
      if (typeof Hls !== 'undefined') {
        const hls = new Hls();
        hls.loadSource(url);
        hls.attachMedia(el.videoEl);
        return url;
      }
      // Fallback: check if native can handle it
      return url;
    }
    return url;
  }

  function loadCasuFile(file) {
    const reader = new FileReader();
    reader.onload = e => {
      try {
        const casu = new CASU.Reader(e.target.result);
        const manifest = casu.open();
        el.nowPlayingBar.textContent = 'CASU: ' + (manifest.source?.filename || file.name);
        el.audioArea.style.display = 'flex';
        el.videoEl.style.display = 'none';
        state = 'READY';
        updateUI();
        _console.log('CASU manifest:', manifest);
        _console.log('CASU chunks:', casu.chunks.length);
      } catch (err) {
        _console.error('CASU parse error:', err);
        el.nowPlayingBar.textContent = 'CASU error: ' + err.message;
      }
    };
    reader.readAsArrayBuffer(file);
  }

  function setupAudioContext(sourceEl) {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (sourceNode) { try { sourceNode.disconnect(); } catch(e) {} }
    try {
      sourceNode = audioCtx.createMediaElementSource(sourceEl);
    } catch(e) {
      // Already connected, try to reconnect
      sourceNode = null;
    }
    gainNode = audioCtx.createGain();
    analyserNode = audioCtx.createAnalyser();
    analyserNode.fftSize = 256;
    gainNode.gain.value = isMuted ? 0 : volume;

    if (sourceNode) {
      sourceNode.connect(gainNode);
      gainNode.connect(analyserNode);
      analyserNode.connect(audioCtx.destination);
    } else {
      // Fallback: connect directly
      try {
        const medNode = audioCtx.createMediaElementSource(sourceEl);
        sourceNode = medNode;
        sourceNode.connect(gainNode);
        gainNode.connect(analyserNode);
        analyserNode.connect(audioCtx.destination);
      } catch(e) {
        _console.warn('AudioContext setup fallback:', e);
      }
    }

    // Setup waveform
    if (!waveform) {
      waveform = new WaveformVisualizer(el.waveformCanvas, analyserNode);
    }

    sourceEl.addEventListener('loadedmetadata', () => {
      duration = sourceEl.duration;
      updateUI();
    });
    sourceEl.addEventListener('timeupdate', () => {
      position = sourceEl.currentTime;
      updateProgress();
    });
    sourceEl.addEventListener('ended', () => {
      state = 'ENDED';
      updateUI();
      autoNext();
    });
    sourceEl.addEventListener('error', () => {
      state = 'ERROR';
      el.nowPlayingBar.textContent = 'Playback error';
    });
    sourceEl.addEventListener('play', () => {
      state = 'PLAYING';
      if (waveform) waveform.start();
      updateUI();
    });
    sourceEl.addEventListener('pause', () => {
      state = sourceEl.currentTime > 0 ? 'PAUSED' : 'STOPPED';
      if (waveform && state !== 'PLAYING') waveform.stop();
      updateUI();
    });
  }

  /* =======================================================================
     TRANSPORT CONTROLS
     ======================================================================= */

  function playPause() {
    if (state === 'PLAYING') pause();
    else play();
  }

  function play() {
    const videoEl = el.videoEl;
    if (!videoEl.src && currentFile) {
      loadFileItem(currentFile);
      return;
    }
    if (!videoEl.src) return;

    videoEl.play().then(() => {
      if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume();
      state = 'PLAYING';
      if (waveform) waveform.start();
      updateUI();
    }).catch(e => _console.error('Play error:', e));
  }

  function pause() {
    el.videoEl.pause();
    state = 'PAUSED';
    if (waveform) waveform.stop();
    updateUI();
  }

  function stop() {
    const videoEl = el.videoEl;
    videoEl.pause();
    videoEl.currentTime = 0;
    state = 'STOPPED';
    position = 0;
    if (waveform) waveform.stop();
    updateUI();
    updateProgress();
  }

  function seek(time) {
    const videoEl = el.videoEl;
    if (videoEl.duration) {
      videoEl.currentTime = _Math.max(0, _Math.min(time, videoEl.duration));
    }
  }

  function prev() {
    if (playlist.length === 0) return;
    if (position > 3) { seek(0); return; }
    let idx = currentIndex - 1;
    if (idx < 0) idx = playlist.length - 1;
    playIndex(idx);
  }

  function next() {
    if (playlist.length === 0) return;
    let idx = currentIndex + 1;
    if (idx >= playlist.length) idx = 0;
    playIndex(idx);
  }

  function autoNext() {
    if (isRadioMode) {
      // In radio mode, reconnect
      _st(() => play(), 100);
      return;
    }
    if (currentIndex < playlist.length - 1) {
      next();
    } else if (playlist.length > 0) {
      // Loop back
      playIndex(0);
    }
  }

  function playIndex(idx) {
    if (idx < 0 || idx >= playlist.length) return;
    currentIndex = idx;
    loadFileItem(playlist[idx]);
  }

  function toggleMute() {
    isMuted = !isMuted;
    if (gainNode) gainNode.gain.value = isMuted ? 0 : volume;
    el.volBtn.textContent = isMuted ? '🔇' : '🔊';
    if (!isMuted) el.volSlider.value = volume * 100;
  }

  function setVolume(v) {
    volume = _Math.max(0, _Math.min(1, v));
    if (gainNode && !isMuted) gainNode.gain.value = volume;
    el.volSlider.value = volume * 100;
    el.volBtn.textContent = volume === 0 ? '🔇' : (volume < 0.5 ? '🔉' : '🔊');
    if (volume === 0) { isMuted = true; if (gainNode) gainNode.gain.value = 0; }
    else if (isMuted) { isMuted = false; if (gainNode) gainNode.gain.value = volume; }
  }

  /* =======================================================================
     STREAM / RADIO / YOUTUBE
     ======================================================================= */

  function addStreamUrl(url) {
    if (!url) return;
    // Detect protocol
    const isHls = url.includes('.m3u8');
    const name = basename(url).replace(/\.(m3u8|mp3|aac|ogg|flac|wav)$/i, '');

    const item = {
      url: url,
      metaData: { artist: 'Stream', title: name || 'Stream' },
      name: name || 'Stream'
    };

    // Apply relay if known
    const relayId = STREAM_RELAY[url];
    if (relayId) {
      item.url = continuousRelayAvail
        ? new URL('continuous-stream?id=' + relayId, window.location.href).href
        : new URL('stream.php?id=' + relayId, window.location.href).href;
    }

    // If HLS, try to use Hls.js
    if (isHls && typeof Hls !== 'undefined') {
      try {
        const hls = new Hls();
        hls.loadSource(url);
        hls.attachMedia(el.videoEl);
      } catch(e) {
        _console.warn('HLS.js init error, falling back to native', e);
      }
    }

    addToPlaylist(item);

    // If it's a radio stream, set radio mode
    if (url.includes('stream') || url.includes('listen') || url.includes('radio') || relayId) {
      isRadioMode = true;
      el.radioInd.textContent = '🔴 LIVE';
      el.radioInd.style.display = 'inline';
    }

    loadFileItem(item);
    closeView();
  }

  function loadYouTube(url) {
    const status = document.getElementById('mpcasu-yt-status');
    if (!status) return;
    status.textContent = 'Fetching YouTube audio...';

    // Extract video ID
    const match = url.match(/(?:youtube\.com\/(?:watch\?v=|embed\/|v\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
    const videoId = match ? match[1] : null;

    if (!videoId) {
      status.textContent = '❌ Invalid YouTube URL';
      return;
    }

    // Try yt-dlp API first
    const apiEndpoint = (document.getElementById('mpcasu-yt-api')?.value || localStorage.getItem('mpcasu_yt_api') || '').trim();

    if (apiEndpoint) {
      const fetchUrl = apiEndpoint + encodeURIComponent(url);
      _fetch(fetchUrl)
        .then(r => r.json())
        .then(data => {
          if (data.url) {
            const item = {
              url: data.url,
              metaData: { artist: data.artist || 'YouTube', title: data.title || videoId },
              name: data.title || videoId
            };
            addToPlaylist(item);
            loadFileItem(item);
            closeView();
            status.textContent = '✅ Playing: ' + (data.title || videoId);
          } else {
            status.textContent = '❌ API returned no audio URL';
          }
        })
        .catch(err => {
          status.textContent = '❌ API error: ' + err.message + '. Trying oEmbed fallback...';
          youTubeOEmbedFallback(videoId, status);
        });
    } else {
      youTubeOEmbedFallback(videoId, status);
    }
  }

  function youTubeOEmbedFallback(videoId, status) {
    // Use oEmbed to get the title, then try invidious/ytproxy
    _fetch('https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=' + videoId + '&format=json')
      .then(r => r.json())
      .then(data => {
        const title = data.title || videoId;
        const author = data.author_name || 'YouTube';

        // Try invidious audio proxy
        const invidiousUrls = [
          'https://invidious.snopyta.org/latest_version?id=' + videoId + '&itag=251',  // Opus
          'https://yewtu.be/latest_version?id=' + videoId + '&itag=251',
          'https://inv.riverside.rocks/latest_version?id=' + videoId + '&itag=251'
        ];

        status.textContent = '✅ Found: ' + title + '. Trying audio proxy...';

        // Try each invidious instance
        tryNextInvidious(invidiousUrls, 0, title, author, status);
      })
      .catch(err => {
        status.textContent = '❌ oEmbed failed: ' + err.message;

        // Last resort: embed as iframe (visual only)
        const item = {
          url: 'https://www.youtube.com/embed/' + videoId + '?autoplay=1',
          metaData: { artist: 'YouTube', title: videoId },
          name: videoId
        };
        addToPlaylist(item);
        el.videoEl.src = item.url;
        el.videoEl.style.display = 'block';
        el.audioArea.style.display = 'none';
      });
  }

  function tryNextInvidious(urls, idx, title, author, status) {
    if (idx >= urls.length) {
      status.textContent = '⚠️ No audio proxy available. Try setting a yt-dlp API endpoint in Settings.';
      return;
    }
    _fetch(urls[idx], { method: 'HEAD', mode: 'no-cors' })
      .then(() => {
        const item = {
          url: urls[idx],
          metaData: { artist: author, title: title },
          name: title
        };
        addToPlaylist(item);
        loadFileItem(item);
        closeView();
        status.textContent = '✅ Playing: ' + title;
      })
      .catch(() => tryNextInvidious(urls, idx + 1, title, author, status));
  }

  /* =======================================================================
     RADIO PRESETS LOADING
     ======================================================================= */
  function loadRadioPresets() {
    return _fetch('RADIO.m3u', { cache: 'no-store' })
      .then(r => {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.text();
      })
      .then(text => {
        const tracks = PlaylistParsers.parseM3U(text);
        window.RADIO_PRESETS = tracks.map(t => ({
          name: t.metaData?.title || t.metaData?.artist || basename(t.url),
          url: t.url
        }));
        localStorage.setItem('mpcasu_radio_presets', JSON.stringify(window.RADIO_PRESETS));
        return window.RADIO_PRESETS;
      })
      .catch(err => {
        _console.warn('Could not load RADIO.m3u, using cached or fallback presets:', err);
        // Try cached
        const cached = localStorage.getItem('mpcasu_radio_presets');
        if (cached) {
          try { window.RADIO_PRESETS = JSON.parse(cached); } catch(e) { window.RADIO_PRESETS = []; }
        }
        if (!window.RADIO_PRESETS || !window.RADIO_PRESETS.length) {
          window.RADIO_PRESETS = [
            { name: 'ERRORCOMPANY - LIVE', url: 'https://securestreams5.autopo.st:1860/error' },
            { name: 'ERRORCOMPANY - ZELLO', url: 'https://securestreams5.autopo.st:1860/TELEFON' },
            { name: 'DLF', url: 'https://st01.sslstream.dlf.de/dlf/01/128/mp3/stream.mp3' },
            { name: 'NDR INFO', url: 'https://icecast.ndr.de/ndr/ndr1niedersachsen/lueneburg/mp3/128/stream.mp3' },
            { name: 'HR INFO', url: 'https://dispatcher.rndfnk.com/hr/hrinfo/live/mp3/high' },
            { name: 'RADIO X', url: 'https://stream.radiox.de:8443/live' },
            { name: 'SOMA FM', url: 'https://ice5.somafm.com/groovesalad-256-mp3' },
            { name: 'BASSDRIVE', url: 'https://ice.bassdrive.net/stream' }
          ];
        }
      });
  }

  function savePlaylistAsM3U() {
    let m3u = '#EXTM3U\n';
    playlist.forEach(item => {
      const title = item.metaData?.title || item.name || basename(item.url || '');
      const artist = item.metaData?.artist || '';
      const label = artist ? artist + ' - ' + title : title;
      m3u += '#EXTINF:-1,' + label + '\n';
      m3u += (item.url || item.name) + '\n';
    });
    const blob = new Blob([m3u], { type: 'audio/x-mpegurl' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'playlist.m3u';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  /* =======================================================================
     UI UPDATES
     ======================================================================= */

  function updateUI() {
    el.playBtn.textContent = state === 'PLAYING' ? '⏸' : '▶';
    const name = currentFile?.metaData?.title || currentFile?.name || basename(currentUrl) || '';
    const extra = currentIndex >= 0 && playlist.length > 0 ? ' [' + (currentIndex + 1) + '/' + playlist.length + ']' : '';
    el.nowPlayingBar.textContent = state + (name ? ' · ' + name + extra : '');
  }

  function updateProgress() {
    const videoEl = el.videoEl;
    const progressEl = el.timeProgress;
    const currentEl = el.currentTime;
    const durationEl = el.durationTime;
    if (videoEl && videoEl.duration) {
      const pct = (videoEl.currentTime / videoEl.duration * 100) || 0;
      progressEl.style.width = pct + '%';
      currentEl.textContent = fmtTime(videoEl.currentTime);
      durationEl.textContent = fmtTime(videoEl.duration);
    }
  }

  /* =======================================================================
     RELAY WORKER REGISTRATION (from webamp-embed)
     ======================================================================= */
  async function initRelayWorker() {
    if ('serviceWorker' in navigator) {
      try {
        await navigator.serviceWorker.register('./relay-worker.js', {
          scope: './',
          updateViaCache: 'none'
        });
        await navigator.serviceWorker.ready;
        if (!navigator.serviceWorker.controller) {
          await new Promise(resolve => {
            const timeout = _st(resolve, 3000);
            navigator.serviceWorker.addEventListener('controllerchange', () => {
              _ct(timeout);
              resolve();
            }, { once: true });
          });
        }
        continuousRelayAvail = Boolean(navigator.serviceWorker.controller);
      } catch (error) {
        _console.warn('Continuous relay unavailable; using reconnect fallback.', error);
      }
    }
  }

  /* =======================================================================
     INIT
     ======================================================================= */
  function init() {
    // Load saved volume
    const savedVol = localStorage.getItem('mpcasu_volume');
    if (savedVol) { volume = parseFloat(savedVol); if (isNaN(volume)) volume = 0.8; }
    el.volSlider.value = volume * 100;

    // Restore radio presets from cache
    const cached = localStorage.getItem('mpcasu_radio_presets');
    if (cached) {
      try { window.RADIO_PRESETS = JSON.parse(cached); } catch(e) {}
    }

    // Init relay worker
    initRelayWorker().then(() => {
      // Auto-start radio mode if enabled
      if (localStorage.getItem('mpcasu_autoradio') === '1') {
        if (window.RADIO_PRESETS && window.RADIO_PRESETS.length) {
          const preset = window.RADIO_PRESETS[0];
          addStreamUrl(preset.url);
          el.radioInd.textContent = '🔴 AUTO: ' + preset.name;
          el.radioInd.style.display = 'inline';
        }
      }
    });

    // Handle URL params
    const params = new URLSearchParams(window.location.search);
    const audioUrl = params.get('audioUrl') || params.get('url');
    const filePath = params.get('file');

    if (audioUrl) {
      addStreamUrl(audioUrl);
    } else if (filePath) {
      _fetch(filePath)
        .then(r => r.blob())
        .then(b => {
          const f = new File([b], basename(filePath));
          handleFiles([f]);
        })
        .catch(e => _console.log('Auto-load failed:', e));
    }

    // Update waveform on resize
    window.addEventListener('resize', () => {
      if (waveform) waveform.resize();
    });
  }

  /* ---- Build UI and initialize ---- */
  build();
  init();

  /* ---- Expose public API ---- */
  self.loadFile = function(file) { handleFiles([file]); };
  self.playPause = playPause;
  self.play = play;
  self.pause = pause;
  self.stop = stop;
  self.seek = seek;
  self.prev = prev;
  self.next = next;
  self.addStreamUrl = addStreamUrl;
  self.setVolume = setVolume;
  self.toggleMute = toggleMute;
  self.loadPlaylist = function(files) { handleFiles(files); };
  self.getPlaylist = () => playlist;
  self.getCurrentIndex = () => currentIndex;
  self.getState = () => state;
  self.loadYouTube = loadYouTube;
}

/* ---- Export ---- */
window.MPCASUPlayer = MPCASUPlayer;
