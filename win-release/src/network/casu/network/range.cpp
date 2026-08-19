// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/network/range.hpp"

#include <cctype>
#include <cstdlib>
#include <string>

namespace casu::network {
namespace range {

namespace {

bool is_all_digits(const std::string& s) {
    if (s.empty()) return false;
    for (char c : s) {
        if (!std::isdigit(static_cast<unsigned char>(c))) return false;
    }
    return true;
}

int64_t to_i64(const std::string& s, int64_t fallback) {
    char* end = nullptr;
    long long v = std::strtoll(s.c_str(), &end, 10);
    if (end == s.c_str() + s.size()) return static_cast<int64_t>(v);
    return fallback;
}

std::string trim(const std::string& s) {
    std::string r = s;
    while (!r.empty() && std::isspace(static_cast<unsigned char>(r.front()))) r.erase(r.begin());
    while (!r.empty() && std::isspace(static_cast<unsigned char>(r.back()))) r.pop_back();
    return r;
}

}  // namespace

ParsedRange parse_bytes_range(const std::string& header, int64_t size) {
    ParsedRange r;
    std::string h = trim(header);
    if (h.rfind("bytes=", 0) != 0 || h.find(',') != std::string::npos) return r;
    std::string spec = h.substr(6);
    size_t dash = spec.find('-');
    if (dash == std::string::npos) return r;
    std::string first = spec.substr(0, dash);
    std::string last = spec.substr(dash + 1);
    bool suffix_form = first.empty();

    if (!suffix_form && !is_all_digits(first)) return r;
    if (!last.empty() && !is_all_digits(last)) return r;
    if (suffix_form && last.empty()) return r;

    if (size < 0) {
        r.unsatisfiable = true;
        return r;
    }

    if (suffix_form) {
        int64_t k = to_i64(last, -1);
        if (k <= 0) {
            r.unsatisfiable = true;
            return r;
        }
        r.start = k >= size ? 0 : size - k;
        r.end = size - 1;
        r.ok = true;
        return r;
    }

    int64_t start = to_i64(first, -1);
    int64_t end = last.empty() ? size - 1 : to_i64(last, -1);
    if (start >= size || end < start) {
        r.unsatisfiable = true;
        return r;
    }
    if (end >= size) end = size - 1;
    r.start = start;
    r.end = end;
    r.ok = true;
    return r;
}

ContentRange parse_content_range(const std::string& header) {
    ContentRange r;
    std::string h = trim(header);
    if (h.rfind("bytes ", 0) != 0) return r;
    std::string spec = h.substr(6);
    size_t dash = spec.find('-');
    if (dash == std::string::npos) return r;
    std::string first = spec.substr(0, dash);
    std::string rest = spec.substr(dash + 1);
    size_t slash = rest.find('/');
    if (slash == std::string::npos || !is_all_digits(first)) return r;
    std::string last = rest.substr(0, slash);
    std::string total = rest.substr(slash + 1);
    if (!is_all_digits(last)) return r;
    r.start = to_i64(first, -1);
    r.end = to_i64(last, -1);
    if (is_all_digits(total)) {
        r.total = to_i64(total, -1);
    } else if (total == "*") {
        r.total = -1;
    } else {
        return r;
    }
    r.ok = true;
    return r;
}

int64_t parse_content_length(const std::string& header) {
    std::string h = trim(header);
    if (!is_all_digits(h)) return -1;
    return to_i64(h, -1);
}

bool accepts_ranges(const std::string& header) {
    std::string h = trim(header);
    if (h.empty()) return false;
    std::string lower = h;
    for (char& c : lower) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return lower != "none";
}

bool is_partial_content(int status) { return status == 206; }

std::string content_range_header(int64_t start, int64_t end, int64_t total) {
    return "bytes " + std::to_string(start) + "-" + std::to_string(end) + "/" +
           std::to_string(total);
}

std::string unsatisfied_range_header(int64_t total) {
    return "bytes */" + std::to_string(total);
}

}  // namespace range
}  // namespace casu::network