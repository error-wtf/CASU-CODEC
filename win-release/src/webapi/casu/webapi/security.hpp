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

struct ProxyPolicy {
    std::vector<std::string> allowed_hosts;  // exact or subdomain match, lowercase
    bool allow_any_http = false;
    bool allow_any_https = false;
};

bool is_allowed_proxy_target(const std::string& url, const ProxyPolicy& policy);
bool is_safe_path_segment(const std::string& seg);
bool is_within_root(const std::string& path, const std::string& root);
std::string sanitize_filename(const std::string& name);
std::string normalize_path(const std::string& p);

}  // namespace casu::webapi