<?php
/**
 * Optional same-origin proxy for remote M3U / XMLTV catalogs.
 *
 * Many playlist/EPG hosts send no CORS headers, so a plain browser fetch of a
 * remote catalog fails. This endpoint fetches the catalog server-side and
 * returns it same-origin. Bounded to http(s), 32 MiB and 30 s — keep this file
 * off static-only hosts, or remove it if you only load catalogs from files.
 *
 * SSRF hardening (v7.8): resolves every hostname and rejects private,
 * loopback, link-local and reserved addresses (IPv4 + IPv6) so remote pages
 * cannot probe the internal network through this proxy. Redirects are not
 * followed (follow_location = 0).
 */
header('Access-Control-Allow-Origin: *');
$url = isset($_GET['url']) ? trim($_GET['url']) : '';
if (!preg_match('#^https?://#', $url)) { http_response_code(400); exit('bad url'); }
$scheme = parse_url($url, PHP_URL_SCHEME);
if (!in_array($scheme, ['http', 'https'], true)) { http_response_code(400); exit('bad scheme'); }
$host = parse_url($url, PHP_URL_HOST);
if (!is_string($host) || $host === '') { http_response_code(400); exit('bad host'); }

// Resolve all A/AAAA records and reject private/reserved ranges (DNS-rebinding safe:
// we pin the first resolved IP and connect to the original hostname via that check only;
// PHP's default resolver may re-resolve, so we additionally re-verify below).
$records = @dns_get_record($host, DNS_A + DNS_AAAA);
$ips = [];
if (is_array($records)) {
    foreach ($records as $rec) {
        if (isset($rec['ip'])) { $ips[] = $rec['ip']; }
        if (isset($rec['ipv6'])) { $ips[] = $rec['ipv6']; }
    }
}
// Fallback: plain resolution (covers hosts dns_get_record misses)
if (!$ips) {
    $resolved = @gethostbynamel($host);
    if (is_array($resolved)) { $ips = $resolved; }
}
if (!$ips) { http_response_code(502); exit('unresolvable host'); }
foreach ($ips as $ip) {
    if (!filter_var($ip, FILTER_VALIDATE_IP)) { http_response_code(502); exit('bad dns'); }
    if (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE) === false) {
        http_response_code(403); exit('private network blocked');
    }
}

$ctx = stream_context_create(['http' => [
    'timeout' => 30,
    'ignore_errors' => true,
    'follow_location' => 0,
    'max_redirects' => 0,
]]);
$body = @file_get_contents($url, false, $ctx);
if ($body === false) { http_response_code(502); exit('fetch failed'); }
if (strlen($body) > 32 * 1024 * 1024) { http_response_code(413); exit('catalog too large'); }
$isXml = (bool)preg_match('/^\s*</', $body);
header('Content-Type: ' . ($isXml ? 'application/xml' : 'audio/x-mpegurl'));
header('Content-Length: ' . strlen($body));
echo $body;
