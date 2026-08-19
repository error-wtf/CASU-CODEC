<?php
/**
 * Optional same-origin proxy for remote M3U / XMLTV catalogs.
 *
 * Many playlist/EPG hosts send no CORS headers, so a plain browser fetch of a
 * remote catalog fails. This endpoint fetches the catalog server-side and
 * returns it same-origin. Bounded to http(s), 32 MiB and 30 s — keep this file
 * off static-only hosts, or remove it if you only load catalogs from files.
 */
header('Access-Control-Allow-Origin: *');
$url = isset($_GET['url']) ? trim($_GET['url']) : '';
if (!preg_match('#^https?://#', $url)) { http_response_code(400); exit('bad url'); }
$scheme = parse_url($url, PHP_URL_SCHEME);
if (!in_array($scheme, ['http', 'https'], true)) { http_response_code(400); exit('bad scheme'); }

$ctx = stream_context_create(['http' => ['timeout' => 30, 'ignore_errors' => true]]);
$body = @file_get_contents($url, false, $ctx);
if ($body === false) { http_response_code(502); exit('fetch failed'); }
if (strlen($body) > 32 * 1024 * 1024) { http_response_code(413); exit('catalog too large'); }
$isXml = (bool)preg_match('/^\s*</', $body);
header('Content-Type: ' . ($isXml ? 'application/xml' : 'audio/x-mpegurl'));
header('Content-Length: ' . strlen($body));
echo $body;
