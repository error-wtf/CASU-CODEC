// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/json.hpp"
#include <charconv>
#include <cmath>
#include <cstdio>
#include <cstring>

namespace casu {

namespace {

struct Parser {
    const char* p;
    std::size_t n;
    std::size_t pos = 0;
    JsonLimits limits;
    uint64_t nodes = 0;
    uint64_t string_bytes = 0;
    uint32_t depth = 0;

    [[noreturn]] void fail(const char* msg) const {
        throw JsonError(std::string("JSON parse error at byte ") + std::to_string(pos) + ": " + msg);
    }

    void skip_ws() {
        while (pos < n) {
            char c = p[pos];
            if (c == ' ' || c == '\t' || c == '\r' || c == '\n') ++pos;
            else break;
        }
    }

    void bump() { if (pos < n) ++pos; }

    bool at_end() { skip_ws(); return pos >= n; }

    char peek() {
        skip_ws();
        if (pos >= n) fail("unexpected end of input");
        return p[pos];
    }

    void expect(char c) {
        skip_ws();
        if (pos >= n || p[pos] != c) {
            fail((std::string("expected '") + c + "'").c_str());
        }
        ++pos;
    }

    JsonValue parse() {
        skip_ws();
        if (pos >= n) fail("empty document");
        return parse_value();
    }

    JsonValue parse_value() {
        if (++nodes > limits.max_nodes) fail("document exceeds node limit");
        if (depth >= limits.max_depth) fail("document exceeds depth limit");
        ++depth;
        JsonValue v;
        skip_ws();
        if (pos >= n) fail("unexpected end of input");
        char c = p[pos];
        switch (c) {
            case '{': v = parse_object(); break;
            case '[': v = parse_array(); break;
            case '"': v = JsonValue(parse_string()); break;
            case 't':
                expect_word("true");
                v = JsonValue(true);
                break;
            case 'f':
                expect_word("false");
                v = JsonValue(false);
                break;
            case 'n':
                expect_word("null");
                v = JsonValue(std::nullptr_t{});
                break;
            default:
                v = parse_number();
                break;
        }
        --depth;
        return v;
    }

    void expect_word(const char* word) {
        std::size_t len = std::strlen(word);
        if (pos + len > n || std::memcmp(p + pos, word, len) != 0) fail("invalid literal");
        pos += len;
    }

    JsonValue parse_object() {
        expect('{');
        auto holder = std::make_shared<JsonObject>();
        if (peek() == '}') { ++pos; return JsonValue(std::move(holder)); }
        for (;;) {
            skip_ws();
            if (pos >= n || p[pos] != '"') fail("object key must be a string");
            std::string key = parse_string();
            expect(':');
            auto v = parse_value();
            holder->items.insert_or_assign(std::move(key), std::move(v));
            skip_ws();
            if (pos >= n) fail("unterminated object");
            if (p[pos] == ',') { ++pos; continue; }
            if (p[pos] == '}') { ++pos; break; }
            fail("expected ',' or '}' in object");
        }
        return JsonValue(std::move(holder));
    }

    JsonValue parse_array() {
        expect('[');
        auto holder = std::make_shared<JsonArray>();
        if (peek() == ']') { ++pos; return JsonValue(std::move(holder)); }
        for (;;) {
            auto v = parse_value();
            holder->items.push_back(std::move(v));
            skip_ws();
            if (pos >= n) fail("unterminated array");
            if (p[pos] == ',') { ++pos; continue; }
            if (p[pos] == ']') { ++pos; break; }
            fail("expected ',' or ']' in array");
        }
        return JsonValue(std::move(holder));
    }

    std::string parse_string() {
        if (pos >= n || p[pos] != '"') fail("expected string");
        ++pos;
        std::string out;
        for (;;) {
            if (pos >= n) fail("unterminated string");
            unsigned char c = static_cast<unsigned char>(p[pos]);
            if (c == '"') { ++pos; break; }
            if (c == '\\') {
                ++pos;
                if (pos >= n) fail("unterminated escape");
                char e = p[pos++];
                switch (e) {
                    case '"': out.push_back('"'); break;
                    case '\\': out.push_back('\\'); break;
                    case '/': out.push_back('/'); break;
                    case 'b': out.push_back('\b'); break;
                    case 'f': out.push_back('\f'); break;
                    case 'n': out.push_back('\n'); break;
                    case 'r': out.push_back('\r'); break;
                    case 't': out.push_back('\t'); break;
                    case 'u': {
                        if (pos + 4 > n) fail("short \\u escape");
                        uint32_t cp = 0;
                        for (int i = 0; i < 4; ++i) {
                            char h = p[pos++];
                            cp <<= 4;
                            if (h >= '0' && h <= '9') cp |= uint32_t(h - '0');
                            else if (h >= 'a' && h <= 'f') cp |= uint32_t(h - 'a' + 10);
                            else if (h >= 'A' && h <= 'F') cp |= uint32_t(h - 'A' + 10);
                            else fail("invalid \\u escape");
                        }
                        // Encode as UTF-8 (surrogate pairs handled as 3-byte each).
                        if (cp < 0x80) out.push_back(char(cp));
                        else if (cp < 0x800) {
                            out.push_back(char(0xC0 | (cp >> 6)));
                            out.push_back(char(0x80 | (cp & 0x3F)));
                        } else if (cp < 0x10000) {
                            out.push_back(char(0xE0 | (cp >> 12)));
                            out.push_back(char(0x80 | ((cp >> 6) & 0x3F)));
                            out.push_back(char(0x80 | (cp & 0x3F)));
                        } else {
                            out.push_back(char(0xF0 | (cp >> 18)));
                            out.push_back(char(0x80 | ((cp >> 12) & 0x3F)));
                            out.push_back(char(0x80 | ((cp >> 6) & 0x3F)));
                            out.push_back(char(0x80 | (cp & 0x3F)));
                        }
                        break;
                    }
                    default: fail("invalid escape sequence");
                }
            } else if (c < 0x20) {
                fail("unescaped control character in string");
            } else {
                out.push_back(char(c));
                ++pos;
            }
            if (out.size() > limits.max_string_bytes) fail("string exceeds size limit");
        }
        string_bytes += out.size();
        return out;
    }

    JsonValue parse_number() {
        std::size_t start = pos;
        skip_ws();
        if (pos >= n) fail("expected number");
        if (p[pos] == '-' ) ++pos;
        if (pos >= n) fail("expected number");
        if (p[pos] == '0') {
            ++pos;
        } else if (p[pos] >= '1' && p[pos] <= '9') {
            while (pos < n && p[pos] >= '0' && p[pos] <= '9') ++pos;
        } else {
            fail("invalid number");
        }
        bool is_double = false;
        if (pos < n && p[pos] == '.') {
            is_double = true;
            ++pos;
            if (pos >= n || p[pos] < '0' || p[pos] > '9') fail("invalid fraction");
            while (pos < n && p[pos] >= '0' && p[pos] <= '9') ++pos;
        }
        if (pos < n && (p[pos] == 'e' || p[pos] == 'E')) {
            is_double = true;
            ++pos;
            if (pos < n && (p[pos] == '+' || p[pos] == '-')) ++pos;
            if (pos >= n || p[pos] < '0' || p[pos] > '9') fail("invalid exponent");
            while (pos < n && p[pos] >= '0' && p[pos] <= '9') ++pos;
        }
        std::string tok(p + start, pos - start);
        if (is_double) {
            double d = std::strtod(tok.c_str(), nullptr);
            if (!std::isfinite(d)) fail("number must be finite");
            return JsonValue(d);
        }
        int64_t i = std::strtoll(tok.c_str(), nullptr, 10);
        return JsonValue(i);
    }
};

std::string escape_string(const std::string& s) {
    std::string out;
    out.reserve(s.size() + 2);
    out.push_back('"');
    for (unsigned char c : s) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (c < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof(buf), "\\u%04x", c);
                    out += buf;
                } else {
                    out.push_back(char(c));
                }
        }
    }
    out.push_back('"');
    return out;
}

void dump(const JsonValue& v, bool sort_keys, std::string& out) {
    switch (v.kind()) {
        case JsonValue::Kind::Null: out += "null"; break;
        case JsonValue::Kind::Bool: out += v.as_bool() ? "true" : "false"; break;
        case JsonValue::Kind::Int: out += std::to_string(v.as_int()); break;
        case JsonValue::Kind::Double: {
            double d = v.as_double();
            if (!std::isfinite(d)) { out += "null"; break; }
            // Shortest round-trip representation (matches Python repr / json).
            char buf[40];
            auto res = std::to_chars(buf, buf + sizeof(buf), d);
            std::string s(buf, res.ptr);
            // Python's json.dumps prints integer-valued floats with a ".0"
            // (e.g. json.dumps(0.0) == "0.0").
            if (s.find('.') == std::string::npos && s.find('e') == std::string::npos &&
                s.find('E') == std::string::npos)
                s += ".0";
            out += s;
            break;
        }
        case JsonValue::Kind::String: out += escape_string(v.as_string()); break;
        case JsonValue::Kind::Array: {
            out.push_back('[');
            const auto& items = v.as_array().items;
            for (std::size_t i = 0; i < items.size(); ++i) {
                if (i) out.push_back(',');
                dump(items[i], sort_keys, out);
            }
            out.push_back(']');
            break;
        }
        case JsonValue::Kind::Object: {
            out.push_back('{');
            const auto& items = v.as_object().items;
            bool first = true;
            for (const auto& [k, val] : items) {
                if (!first) out.push_back(',');
                first = false;
                out += escape_string(k);
                out.push_back(':');
                dump(val, sort_keys, out);
            }
            out.push_back('}');
            break;
        }
    }
}

}  // namespace

JsonValue parse_json(const char* data, std::size_t n, const JsonLimits& limits) {
    Parser parser{data, n, 0, limits, 0, 0};
    JsonValue v = parser.parse();
    if (!parser.at_end()) parser.fail("trailing garbage after document");
    return v;
}

JsonValue parse_json(const std::string& text, const JsonLimits& limits) {
    return parse_json(text.data(), text.size(), limits);
}

std::string dump_json(const JsonValue& v, bool sort_keys) {
    std::string out;
    dump(v, sort_keys, out);
    return out;
}

}  // namespace casu
