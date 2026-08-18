<?php
/**
 * Optional same-origin stream relay for the pure-web player.
 *
 * Media elements play cross-origin without CORS, but the WebAudio visualizer
 * needs it. This relay lets the player analyse remote radio/audio streams and
 * reach hosts that block hotlinking. It is an SSRF surface, so only the hosts
 * listed below are allowed — extend the list for your own stations, or leave
 * it empty to disable the relay entirely (the player still plays everything
 * directly).
 */
$allow = [
    'securestreams5.autopo.st:1860',
    'listen.undergroundbass.com:8804',
    'ice.bassdrive.net',
    'st01.sslstream.dlf.de',
    'icecast.ndr.de',
    'dispatcher.rndfnk.com',
    'streaming.radio-r.net',
    'streaming.fueralle.org',
    'stream.radiox.de:8443',
    'mp3.querfunk.de',
    'stream.laut.fm',
    'www.rdl.de:8000',
    'www.radioeins.de',
    'bytefm.cast.addradio.de',
    'liveradio.swr.de',
    'streams.deltaradio.de',
    'wdr-1live-live.icecast.wdr.de',
    'ice1.somafm.com',
    'radio.streemlion.com:1960',
    'dreamsiteradiocp.com:8006',
];

header('Access-Control-Allow-Origin: *');
header('Content-Type: audio/mpeg');
header('Cache-Control: no-cache');
$url = isset($_GET['url']) ? trim($_GET['url']) : '';
if (!preg_match('#^https?://#', $url)) { http_response_code(400); exit('bad url'); }
$host = parse_url($url, PHP_URL_HOST);
$port = parse_url($url, PHP_URL_PORT);
$authority = ($host ?: '') . ($port ? ':' . $port : '');
if ($authority && in_array($authority, $allow, true)) {
    // allowed host:port combo
} elseif ($host && in_array($host, $allow, true)) {
    // allowed host (any port)
} else {
    http_response_code(403);
    exit('forbidden');
}

$ctx = stream_context_create(['http' => ['timeout' => 30, 'ignore_errors' => true]]);
$fp = @fopen($url, 'rb', false, $ctx);
if (!$fp) { http_response_code(502); exit('relay failed'); }
while (!feof($fp)) { echo fread($fp, 65536); flush(); }
fclose($fp);
