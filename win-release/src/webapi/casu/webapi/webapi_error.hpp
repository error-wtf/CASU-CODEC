// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#pragma once
#include <stdexcept>
#include <string>

namespace casu::webapi {

class WebApiError : public std::runtime_error {
public:
    explicit WebApiError(const std::string& msg) : std::runtime_error(msg) {}
};

}  // namespace casu::webapi