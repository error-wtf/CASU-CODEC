// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/webapi/media_serve.hpp"

#include "casu/network/range.hpp"

#include <string>

namespace casu::webapi {

MediaPlan plan_media_response(const std::string& range_header, int64_t file_size,
                              const std::string& content_type) {
    MediaPlan plan;
    if (file_size < 0) {
        plan.status = 404;
        return plan;
    }
    plan.file_size = file_size;
    plan.headers.emplace_back("Content-Type", content_type);
    plan.headers.emplace_back("Accept-Ranges", "bytes");

    if (range_header.empty()) {
        plan.status = 200;
        plan.start = 0;
        plan.length = file_size;
        return plan;
    }

    casu::network::range::ParsedRange parsed =
        casu::network::range::parse_bytes_range(range_header, file_size);
    if (!parsed.ok || parsed.unsatisfiable) {
        plan.status = 416;
        plan.headers.emplace_back("Content-Range",
                                  casu::network::range::unsatisfied_range_header(file_size));
        return plan;
    }

    plan.status = 206;
    plan.partial = true;
    plan.start = parsed.start;
    plan.length = parsed.end - parsed.start + 1;
    plan.headers.emplace_back(
        "Content-Range", casu::network::range::content_range_header(
                             parsed.start, parsed.end, file_size));
    return plan;
}

}  // namespace casu::webapi