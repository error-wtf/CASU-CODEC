// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/json.hpp"
#include <charconv>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <cerrno>

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
    bool strict = false;  // duplicate keys + unpaired surrogates are errors

    [[noreturn]] void fail(const std::string& msg) const {
        throw JsonError("JSON parse error at byte " + std::to_string(pos) + ": " + msg);
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
            fail(std::string("expected '") + c + "'");
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
            if (strict && holder->items.find(key) != holder->items.end())
                fail("duplicate JSON key: " + key);
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
                        auto read_hex4 = [&](uint32_t& cp) -> bool {
                            if (pos + 4 > n) return false;
                            cp = 0;
                            for (int i = 0; i < 4; ++i) {
                                char h = p[pos++];
                                cp <<= 4;
                                if (h >= '0' && h <= '9') cp |= uint32_t(h - '0');
                                else if (h >= 'a' && h <= 'f') cp |= uint32_t(h - 'a' + 10);
                                else if (h >= 'A' && h <= 'F') cp |= uint32_t(h - 'A' + 10);
                                else return false;
                            }
                            return true;
                        };
                        uint32_t cp = 0;
                        if (!read_hex4(cp)) fail("invalid \\u escape");
                        auto append_utf8 = [&](uint32_t value) {
                            if (value < 0x80) out.push_back(char(value));
                            else if (value < 0x800) {
                                out.push_back(char(0xC0 | (value >> 6)));
                                out.push_back(char(0x80 | (value & 0x3F)));
                            } else {
                                out.push_back(char(0xE0 | (value >> 12)));
                                out.push_back(char(0x80 | ((value >> 6) & 0x3F)));
                                out.push_back(char(0x80 | (value & 0x3F)));
                            }
                        };
                        if (cp >= 0xD800 && cp <= 0xDBFF) {
                            // High surrogate: must be followed by \uDC00-\uDFFF.
                            if (pos + 1 < n && p[pos] == '\\' && p[pos + 1] == 'u') {
                                pos += 2;
                                uint32_t low = 0;
                                if (!read_hex4(low)) fail("invalid \\u escape");
                                if (low < 0xDC00 || low > 0xDFFF)
                                    fail("unpaired surrogate in \\u escape");
                                const uint32_t combined =
                                    0x10000 + ((cp - 0xD800) << 10) + (low - 0xDC00);
                                out.push_back(char(0xF0 | (combined >> 18)));
                                out.push_back(char(0x80 | ((combined >> 12) & 0x3F)));
                                out.push_back(char(0x80 | ((combined >> 6) & 0x3F)));
                                out.push_back(char(0x80 | (combined & 0x3F)));
                            } else {
                                fail("unpaired surrogate in \\u escape");
                            }
                        } else if (cp >= 0xDC00 && cp <= 0xDFFF) {
                            // Lone low surrogate is invalid Unicode.
                            fail("unpaired surrogate in \\u escape");
                        } else {
                            append_utf8(cp);
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
        // Fail-closed integer range: Python json parses arbitrary precision
        // and the validator rejects values outside int64; a clamped strtoll
        // would silently accept hostile magnitudes, so overflow is an error.
        errno = 0;
        char* endp = nullptr;
        const long long value = std::strtoll(tok.c_str(), &endp, 10);
        if (errno == ERANGE || endp != tok.c_str() + tok.size())
            fail("JSON integer exceeds int64");
        return JsonValue(static_cast<int64_t>(value));
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

// Python json.dumps(..., ensure_ascii=True) escapes every code point >= 0x7F
// as \uXXXX (surrogate pairs for astral planes). Input must be valid UTF-8.
void append_ascii_escape(std::string& out, uint32_t cp) {
    char buf[16];
    if (cp >= 0x10000) {
        const uint32_t v = cp - 0x10000;
        const uint32_t hi = 0xD800 + (v >> 10);
        const uint32_t lo = 0xDC00 + (v & 0x3FF);
        std::snprintf(buf, sizeof(buf), "\\u%04x\\u%04x", hi, lo);
        out += buf;
    } else {
        std::snprintf(buf, sizeof(buf), "\\u%04x", cp);
        out += buf;
    }
}

std::string escape_string_ascii(const std::string& s) {
    std::string out;
    out.reserve(s.size() + 2);
    out.push_back('"');
    for (std::size_t i = 0; i < s.size();) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        if (c < 0x20 || c == '"' || c == '\\') {
            switch (c) {
                case '"': out += "\\\""; break;
                case '\\': out += "\\\\"; break;
                case '\b': out += "\\b"; break;
                case '\f': out += "\\f"; break;
                case '\n': out += "\\n"; break;
                case '\r': out += "\\r"; break;
                case '\t': out += "\\t"; break;
                default: {
                    char buf[8];
                    std::snprintf(buf, sizeof(buf), "\\u%04x", c);
                    out += buf;
                    break;
                }
            }
            ++i;
            continue;
        }
        if (c < 0x80) { out.push_back(char(c)); ++i; continue; }
        // Decode one UTF-8 sequence.
        std::size_t len = 0;
        uint32_t cp = 0;
        if ((c & 0xE0) == 0xC0) { len = 2; cp = c & 0x1Fu; }
        else if ((c & 0xF0) == 0xE0) { len = 3; cp = c & 0x0Fu; }
        else if ((c & 0xF8) == 0xF0) { len = 4; cp = c & 0x07u; }
        else { cp = c; len = 1; }  // invalid byte — pass through raw
        bool ok = len > 1 && i + len <= s.size();
        for (std::size_t k = 1; ok && k < len; ++k) {
            const unsigned char cc = static_cast<unsigned char>(s[i + k]);
            if ((cc & 0xC0) != 0x80) { ok = false; break; }
            cp = (cp << 6) | (cc & 0x3Fu);
        }
        if (!ok) { out.push_back(char(c)); ++i; continue; }
        append_ascii_escape(out, cp);
        i += len;
    }
    out.push_back('"');
    return out;
}

void dump(const JsonValue& v, bool sort_keys, bool ensure_ascii, std::string& out) {
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
        case JsonValue::Kind::String:
            out += ensure_ascii ? escape_string_ascii(v.as_string())
                                : escape_string(v.as_string());
            break;
        case JsonValue::Kind::Array: {
            out.push_back('[');
            const auto& items = v.as_array().items;
            for (std::size_t i = 0; i < items.size(); ++i) {
                if (i) out.push_back(',');
                dump(items[i], sort_keys, ensure_ascii, out);
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
                out += ensure_ascii ? escape_string_ascii(k) : escape_string(k);
                out.push_back(':');
                dump(val, sort_keys, ensure_ascii, out);
            }
            out.push_back('}');
            break;
        }
    }
}

}  // namespace

JsonValue parse_json(const char* data, std::size_t n, const JsonLimits& limits) {
    Parser parser{data, n, 0, limits, 0, 0, 0, false};
    JsonValue v = parser.parse();
    if (!parser.at_end()) parser.fail("trailing garbage after document");
    return v;
}

JsonValue parse_json(const std::string& text, const JsonLimits& limits) {
    return parse_json(text.data(), text.size(), limits);
}

JsonValue parse_strict_json(const char* data, std::size_t n, const JsonLimits& limits) {
    Parser parser{data, n, 0, limits, 0, 0, 0, true};
    JsonValue v = parser.parse();
    if (!parser.at_end()) parser.fail("trailing garbage after document");
    return v;
}

JsonValue parse_strict_json(const std::string& text, const JsonLimits& limits) {
    return parse_strict_json(text.data(), text.size(), limits);
}

std::string dump_json(const JsonValue& v, bool sort_keys, bool ensure_ascii) {
    std::string out;
    dump(v, sort_keys, ensure_ascii, out);
    return out;
}

}  // namespace casu
