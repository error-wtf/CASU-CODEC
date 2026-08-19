// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// CASU-Converter — red/black design tokens (mirror of casu/design.py) and the
// Qt stylesheet built from them.
#pragma once

#include <string>

namespace casu::conv {

struct DesignTokens {
    std::string bg = "#07090b";
    std::string panel = "#101317";
    std::string panel2 = "#15191e";
    std::string line = "#252a30";
    std::string red = "#ff1e2d";
    std::string red_dark = "#3a1015";
    std::string muted = "#858b93";
    std::string text = "#f4f5f7";
    std::string secondary = "#b9bec5";
    std::string sidebar = "#0c0f12";
    std::string button = "#161a1f";
    std::string button_text = "#d7d9dc";
    std::string input_bg = "#080a0c";
    std::string input_border = "#333942";
    std::string toast_bg = "#171b20";
    std::string toast_border = "#444444";
    std::string scrollbar = "#1b2026";
};

const DesignTokens& design_tokens();

std::string application_stylesheet();

}  // namespace casu::conv