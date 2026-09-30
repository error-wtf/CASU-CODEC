// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Loopback web API security helpers (WP-WEBAPI-005): DNS-rebinding host
// validation, stream-proxy SSRF allow-list, path-traversal guards and
// filename sanitization. Pure C++, no Qt.
#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace casu::webapi {

bool is_trusted_loopback_host(const std::string& host_header, uint16_t port);
bool is_loopback_or_private_host(const std::string& host);

// Classifies a literal IP (v4 dotted quad or v6 literal, optionally
// bracketed) against private/loopback/link-local/reserved/documentation
// ranges, mirroring the PHP catalog.php guard (FILTER_FLAG_NO_PRIV_RANGE |
// FILTER_FLAG_NO_RES_RANGE) plus IPv6 ULA/link-local/IPv4-mapped coverage.
// Unparseable input is rejected (returns true).
bool is_private_or_reserved_ip(const std::string& ip);

// Resolves host via the platform resolver (QHostInfo) and returns true when
// every resolved address is acceptable, i.e. none is private/reserved.
// Unresolvable hosts return false (fail closed). This is the DNS-rebinding
// guard shared by catalog-url and stream-proxy targets.
bool resolves_to_public_addresses_only(const std::string& host);

struct ProxyPolicy {
    std::vector<std::string> allowed_hosts;  // exact or subdomain match, lowercase
    bool allow_any_http = false;
    bool allow_any_https = false;
};

bool is_allowed_proxy_target(const std::string& url, const ProxyPolicy& policy);

// SSRF guard for /api/catalog-url: http(s) only, no userinfo, and the host
// must resolve to public addresses only (private/loopback/link-local/
// reserved rejected, IPv4 and IPv6). See pure-web-release/php/catalog.php.
bool is_allowed_catalog_target(const std::string& url);
bool is_safe_path_segment(const std::string& seg);
bool is_within_root(const std::string& path, const std::string& root);
std::string sanitize_filename(const std::string& name);
std::string normalize_path(const std::string& p);

}  // namespace casu::webapi