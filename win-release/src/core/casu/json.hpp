// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Bounded JSON document parser for casu_core. Mirrors the fail-closed limits
// of the reference: max_json_depth (32) and max_json_nodes (1_000_000) from
// casu/native_v2/format.py CasuLimits, and strict_json_loads semantics
// (casu/native_v2/jsonutil.py): no NaN/Infinity, no trailing garbage.
#pragma once
#include <cstdint>
#include <memory>
#include <map>
#include <string>
#include <variant>
#include <vector>
#include <stdexcept>

namespace casu {

class JsonError : public std::runtime_error {
public:
    explicit JsonError(const std::string& msg) : std::runtime_error(msg) {}
};

// Limits enforced while parsing (fail-closed; a hostile document cannot
// exhaust memory or recursion).
struct JsonLimits {
    uint32_t max_depth = 32;
    uint64_t max_nodes = 1'000'000;
    uint64_t max_string_bytes = 4 * 1024 * 1024;
};

class JsonValue;

// Opaque recursive holders so the variant stays well-formed while JsonValue
// is still incomplete.
struct JsonArray { std::vector<JsonValue> items; };
struct JsonObject { std::map<std::string, JsonValue> items; };

class JsonValue {
public:
    enum class Kind { Null, Bool, Int, Double, String, Array, Object };

    JsonValue() : kind_(Kind::Null), scalar_(std::nullptr_t{}) {}
    JsonValue(std::nullptr_t) : kind_(Kind::Null), scalar_(std::nullptr_t{}) {}
    // Explicit C-string overload so "literal" never decays to bool.
    JsonValue(const char* s) : kind_(Kind::String), scalar_(std::string(s)) {}
    JsonValue(bool b) : kind_(Kind::Bool), scalar_(b) {}
    JsonValue(int64_t i) : kind_(Kind::Int), scalar_(i) {}
    JsonValue(double d) : kind_(Kind::Double), scalar_(d) {}
    JsonValue(std::string s) : kind_(Kind::String), scalar_(std::move(s)) {}
    JsonValue(std::shared_ptr<JsonArray> a) : kind_(Kind::Array), scalar_(std::move(a)) {}
    JsonValue(std::shared_ptr<JsonObject> o) : kind_(Kind::Object), scalar_(std::move(o)) {}

    Kind kind() const { return kind_; }
    bool is_null() const { return kind_ == Kind::Null; }
    bool is_bool() const { return kind_ == Kind::Bool; }
    bool is_int() const { return kind_ == Kind::Int; }
    bool is_double() const { return kind_ == Kind::Double; }
    bool is_number() const { return kind_ == Kind::Int || kind_ == Kind::Double; }
    bool is_string() const { return kind_ == Kind::String; }
    bool is_array() const { return kind_ == Kind::Array; }
    bool is_object() const { return kind_ == Kind::Object; }

    bool as_bool() const { return std::get<bool>(scalar_); }
    int64_t as_int() const { return std::get<int64_t>(scalar_); }
    double as_double() const {
        if (kind_ == Kind::Double) return std::get<double>(scalar_);
        return static_cast<double>(std::get<int64_t>(scalar_));
    }
    const std::string& as_string() const { return std::get<std::string>(scalar_); }
    const JsonArray& as_array() const { return *std::get<std::shared_ptr<JsonArray>>(scalar_); }
    const JsonObject& as_object() const { return *std::get<std::shared_ptr<JsonObject>>(scalar_); }
    JsonArray& as_array_mut() { return *std::get<std::shared_ptr<JsonArray>>(scalar_); }
    JsonObject& as_object_mut() { return *std::get<std::shared_ptr<JsonObject>>(scalar_); }

    // Object access helper (safe).
    const JsonValue* find(const std::string& key) const {
        if (!is_object()) return nullptr;
        auto it = as_object().items.find(key);
        return it == as_object().items.end() ? nullptr : &it->second;
    }

private:
    using Scalar = std::variant<std::nullptr_t, bool, int64_t, double, std::string,
                                std::shared_ptr<JsonArray>, std::shared_ptr<JsonObject>>;
    Kind kind_;
    Scalar scalar_;
};

// Strict mode (strict_json_loads semantics): duplicate object keys are a
// hard error and unpaired \\uD800-\\uDFFF escapes are rejected, matching the
// reference jsonutil.py object_pairs_hook / strict Unicode decoding.
JsonValue parse_strict_json(const std::string& text, const JsonLimits& limits = JsonLimits());
JsonValue parse_strict_json(const char* data, std::size_t n, const JsonLimits& limits = JsonLimits());

// Parse a complete JSON document (no trailing garbage, bounded depth/nodes).
// Legacy permissive mode kept for non-security call sites.
JsonValue parse_json(const std::string& text, const JsonLimits& limits = JsonLimits());
JsonValue parse_json(const char* data, std::size_t n, const JsonLimits& limits = JsonLimits());

// Compact, deterministic serialization (sort_keys=True, separators=(",",":"),
// allow_nan=False) matching the reference writer. With ensure_ascii=true
// (Python json.dumps default) every non-ASCII character is emitted as
// \\uXXXX/\\uXXXX\\uXXXX escapes so output is byte-identical to the Python
// writer payloads; ensure_ascii=false matches _json_bytes() in text.py.
std::string dump_json(const JsonValue& v, bool sort_keys = true,
                      bool ensure_ascii = true);

}  // namespace casu
