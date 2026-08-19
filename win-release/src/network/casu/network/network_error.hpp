// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#pragma once
#include <stdexcept>
#include <string>

namespace casu::network {

class NetworkError : public std::runtime_error {
public:
    explicit NetworkError(const std::string& msg) : std::runtime_error(msg) {}
};

}  // namespace casu::network