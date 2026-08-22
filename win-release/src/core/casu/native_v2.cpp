// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// Full port of casu/native_v2/{reader,writer}.py. Error messages mirror the
// reference so parity tests can compare failures verbatim.
#include "casu/native_v2.hpp"
#include "casu/sha256.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <map>
#include <set>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#include <process.h>
#else
#include <unistd.h>
#endif

namespace casu {
namespace casunat2 {

using casu::CasuError;
namespace nat = casu::natv2;

namespace {

constexpr std::size_t kHeaderSize = 20;         // ">8sHHQ"
constexpr std::size_t kChunkHeaderSize = 28;    // ">BBHqQQ"

uint16_t be16(const uint8_t* p) {
    return uint16_t(uint16_t(p[0]) << 8 | uint16_t(p[1]));
}
uint64_t be64(const uint8_t* p) {
    uint64_t v = 0;
    for (int i = 0; i < 8; ++i) v = (v << 8) | p[i];
    return v;
}
int64_t be64s(const uint8_t* p) { return static_cast<int64_t>(be64(p)); }
void put_be64(std::string& out, uint64_t v) {
    for (int i = 7; i >= 0; --i) out.push_back(char((v >> (8 * i)) & 0xFF));
}

bool is_hex64(const std::string& s) {
    if (s.size() != 64) return false;
    static const std::string hexdigits = "0123456789abcdefABCDEF";
    return s.find_first_not_of(hexdigits) == std::string::npos;
}

[[noreturn]] void fail(const std::string& msg) { throw NativeV2Error(msg); }

std::optional<int64_t> coerce_int_opt(const JsonValue* v) {
    if (!v || v->is_null() || v->is_bool() || v->is_array() ||
        v->is_object())
        return std::nullopt;
    if (v->is_int()) return v->as_int();
    if (v->is_double()) {
        const double d = v->as_double();
        if (!std::isfinite(d)) return std::nullopt;
        if (d > 9.2233720368547758e18 || d < -9.2233720368547758e18)
            return std::nullopt;
        return static_cast<int64_t>(d);
    }
    const std::string& s = v->as_string();
    try {
        std::size_t idx = 0;
        const long long parsed = std::stoll(s, &idx, 10);
        while (idx < s.size() && std::isspace(static_cast<unsigned char>(s[idx])))
            ++idx;
        if (idx != s.size()) return std::nullopt;
        return static_cast<int64_t>(parsed);
    } catch (const std::exception&) {
        return std::nullopt;
    }
}

// Port of writer._pack_chunk.
std::string pack_chunk(const Chunk& chunk) {
    const std::string& payload = chunk.payload;
    if (chunk.stream_id > 255) fail("stream_id must fit in uint8");
    if (chunk.flags > 65535) fail("flags must fit in uint16");
    const uint64_t uncompressed = chunk.uncompressed_length.value_or(
        static_cast<uint64_t>(payload.size()));
    if (uncompressed < payload.size())
        fail("uncompressed_length cannot be below payload length");
    std::string header;
    header.reserve(kChunkHeaderSize);
    header.push_back(char(chunk.chunk_type));
    header.push_back(char(chunk.stream_id));
    header.push_back(char((chunk.flags >> 8) & 0xFF));
    header.push_back(char(chunk.flags & 0xFF));
    put_be64(header, static_cast<uint64_t>(chunk.pts));  // signed bit pattern
    put_be64(header, payload.size());
    put_be64(header, uncompressed);
    return header + payload;
}

// Port of writer._index_payload: {"version":1,"entries":[...]} sorted keys,
// compact separators, ensure_ascii=True.
std::string index_payload(const std::vector<SeekEntry>& entries) {
    auto root = std::make_shared<JsonObject>();
    auto array = std::make_shared<JsonArray>();
    for (const SeekEntry& e : entries) {
        auto entry = std::make_shared<JsonObject>();
        entry->items["stream_id"] = JsonValue(e.stream_id);
        entry->items["target_pts"] = JsonValue(e.target_pts);
        entry->items["key_state_pts"] = JsonValue(e.key_state_pts);
        entry->items["key_state_offset"] = JsonValue(e.key_state_offset);
        entry->items["first_update_offset"] =
            JsonValue(e.first_update_offset);
        array->items.push_back(JsonValue(std::move(entry)));
    }
    root->items["version"] = JsonValue(int64_t(1));
    root->items["entries"] = JsonValue(std::move(array));
    return dump_json(JsonValue(std::move(root)), true, true);
}

JsonValue deep_copy(const JsonValue& v);

JsonValue deep_copy_array(const JsonArray& a) {
    auto out = std::make_shared<JsonArray>();
    out->items.reserve(a.items.size());
    for (const JsonValue& item : a.items) out->items.push_back(deep_copy(item));
    return JsonValue(std::move(out));
}

JsonValue deep_copy_object(const JsonObject& o) {
    auto out = std::make_shared<JsonObject>();
    for (const auto& [k, item] : o.items)
        out->items.emplace(k, deep_copy(item));
    return JsonValue(std::move(out));
}

JsonValue deep_copy(const JsonValue& v) {
    switch (v.kind()) {
        case JsonValue::Kind::Null:
        case JsonValue::Kind::Bool:
        case JsonValue::Kind::Int:
        case JsonValue::Kind::Double:
        case JsonValue::Kind::String:
            return v;
        case JsonValue::Kind::Array:
            return deep_copy_array(v.as_array());
        case JsonValue::Kind::Object:
            return deep_copy_object(v.as_object());
    }
    return v;
}

void fsync_file(std::FILE* handle) {
#ifdef _WIN32
    ::_commit(::_fileno(handle));
#else
    ::fsync(::fileno(handle));
#endif
}

}  // namespace

// ---------------------------------------------------------------------------
// Recovery point decoding (reader._decode_recovery_point)
// ---------------------------------------------------------------------------
namespace {

JsonValue decode_recovery_point(const std::string& payload, uint64_t offset,
                                const std::string& prefix_sha256,
                                const std::map<uint64_t, Chunk>& prior_chunks,
                                bool allow_legacy_verified) {
    try {
        JsonValue value = parse_strict_json(payload);
        if (!value.is_object()) throw CasuError("not an object");
        // Pop checkpoint_sha256 before hashing the checkpoint serialization.
        JsonValue declared_checkpoint_value;
        bool has_checkpoint = false;
        if (const JsonValue* ck = value.find("checkpoint_sha256")) {
            declared_checkpoint_value = *ck;
            has_checkpoint = true;
            value.as_object_mut().items.erase("checkpoint_sha256");
        }
        const JsonValue* version = value.find("version");
        const auto boundary = coerce_int_opt(value.find("last_complete_chunk_offset"));
        if (!boundary || !version || !version->is_int() ||
            version->as_int() != 1 || !prior_chunks.count(
                                          static_cast<uint64_t>(*boundary)) ||
            *boundary >= static_cast<int64_t>(offset))
            throw CasuError("invalid boundary");
        const JsonValue* declared_prefix_field =
            value.find("sha256_before_recovery");
        const bool have_both =
            has_checkpoint && declared_prefix_field != nullptr &&
            !declared_prefix_field->is_null();
        if (!have_both && !allow_legacy_verified)
            throw CasuError("missing checkpoint fields");
        std::string checkpoint_hash;
        if (have_both) {
            if (!declared_checkpoint_value.is_string() &&
                !declared_checkpoint_value.is_int())
                throw CasuError("bad checkpoint type");
            const std::string declared_checkpoint =
                declared_checkpoint_value.is_string()
                    ? declared_checkpoint_value.as_string()
                    : std::to_string(declared_checkpoint_value.as_int());
            const std::string declared_prefix =
                declared_prefix_field->is_string()
                    ? declared_prefix_field->as_string()
                    : std::to_string(declared_prefix_field->as_int());
            if (declared_prefix != prefix_sha256 ||
                declared_checkpoint.size() != 64)
                throw CasuError("checkpoint mismatch");
            checkpoint_hash = Sha256::oneshot(dump_json(value, true, true));
            if (checkpoint_hash != declared_checkpoint)
                throw CasuError("checkpoint mismatch");
        }
        using FieldCheck = std::pair<const char*, uint8_t>;
        const std::vector<FieldCheck> field_checks = {
            {"key_state_offsets", VIDEO_KEY_STATE},
            {"audio_block_offsets", AUDIO_BLOCK},
        };
        for (const FieldCheck& check : field_checks) {
            const JsonValue* entries = value.find(check.first);
            if (!entries || !entries->is_object())
                throw CasuError("missing offsets table");
            for (const auto& [raw_stream_key, raw_offset] :
                 entries->as_object().items) {
                int64_t raw_stream_id = 0;
                try {
                    std::size_t consumed = 0;
                    raw_stream_id = std::stoll(raw_stream_key, &consumed, 10);
                    if (consumed != raw_stream_key.size())
                        throw std::invalid_argument("");
                } catch (const std::exception&) {
                    throw CasuError("bad stream key");
                }
                const auto raw_off = coerce_int_opt(&raw_offset);
                if (!raw_off) throw CasuError("bad offset value");
                const auto referenced = prior_chunks.find(
                    static_cast<uint64_t>(*raw_off));
                if (referenced == prior_chunks.end() ||
                    referenced->second.chunk_type != check.second ||
                    referenced->second.stream_id !=
                        static_cast<uint8_t>(raw_stream_id) ||
                    *raw_off > *boundary)
                    throw CasuError("bad reference");
            }
        }
        if (has_checkpoint)
            value.as_object_mut().items["checkpoint_sha256"] =
                declared_checkpoint_value;
        return value;
    } catch (const JsonError&) {
        fail("invalid CASUNAT2 recovery point");
    } catch (const CasuError&) {
        fail("invalid CASUNAT2 recovery point");
    }
}

struct WalkedChunk {
    Chunk chunk;
    uint64_t offset = 0;
};

}  // namespace

// ---------------------------------------------------------------------------
// Reader
// ---------------------------------------------------------------------------
Container read_native_v2(const std::string& path, bool load_payloads) {
    return read_native_v2(path, CasuLimits(), load_payloads);
}

Container read_native_v2(const std::string& path, const CasuLimits& limits,
                         bool load_payloads) {
    limits.validate();
    std::FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) fail("could not read CASUNAT2 file: " + path);
    if (std::fseek(f, 0, SEEK_END) != 0) {
        std::fclose(f);
        fail("could not stat CASUNAT2 file");
    }
#ifdef _WIN32
    const int64_t fsize_signed = ::_ftelli64(f);
#else
    const int64_t fsize_signed = std::ftell(f);
#endif
    if (fsize_signed < 0) {
        std::fclose(f);
        fail("could not stat CASUNAT2 file");
    }
    const uint64_t size = static_cast<uint64_t>(fsize_signed);
    std::rewind(f);
    if (size > limits.max_file_bytes) {
        std::fclose(f);
        fail("CASUNAT2 file exceeds configured size limit");
    }

    Container c;
    c.path = path;
    c.limits = limits;

    std::vector<uint8_t> header(kHeaderSize);
    if (std::fread(header.data(), 1, kHeaderSize, f) != kHeaderSize) {
        std::fclose(f);
        fail("truncated CASUNAT2 header");
    }
    if (std::memcmp(header.data(), "CASUNAT2", 8) != 0 ||
        be16(header.data() + 8) != VERSION || be16(header.data() + 10) != 0) {
        std::fclose(f);
        fail("unsupported CASUNAT2 header/version");
    }
    const uint64_t manifest_length = be64(header.data() + 12);
    if (manifest_length > limits.max_manifest_bytes ||
        manifest_length > size - kHeaderSize) {
        std::fclose(f);
        fail("invalid CASUNAT2 manifest length");
    }
    std::string manifest_bytes(manifest_length, '\0');
    if (manifest_length > 0 &&
        std::fread(&manifest_bytes[0], 1, manifest_length, f) !=
            manifest_length) {
        std::fclose(f);
        fail("truncated CASUNAT2 manifest");
    }
    try {
        c.manifest = parse_strict_json(manifest_bytes);
    } catch (const JsonError&) {
        std::fclose(f);
        fail("invalid CASUNAT2 manifest");
    }

    nat::NativeV2PayloadValidator* topology = nullptr;
    nat::NativeV2PayloadValidator topology_validator(c.manifest, limits, false);
    topology = &topology_validator;

    Sha256 digest;
    digest.update(header.data(), kHeaderSize);
    digest.update(manifest_bytes);

    bool seen_integrity = false;
    std::optional<std::string> integrity_expected;
    std::optional<uint64_t> integrity_offset;
    std::vector<std::pair<uint64_t, std::string>> observed_chunk_hashes;
    std::map<uint64_t, Chunk> parsed_by_offset;

    uint64_t pos = kHeaderSize + manifest_length;
    if (std::fseek(f, static_cast<long>(pos), SEEK_SET) != 0) {
        std::fclose(f);
        fail("CASUNAT2 seek failed");
    }
    while (pos < size) {
        if (c.chunks.size() >= limits.max_chunks) {
            std::fclose(f);
            fail("excessive CASUNAT2 chunks");
        }
        const uint64_t offset = pos;
        std::vector<uint8_t> chdr(kChunkHeaderSize);
        if (std::fread(chdr.data(), 1, kChunkHeaderSize, f) !=
            kChunkHeaderSize) {
            std::fclose(f);
            fail("truncated CASUNAT2 chunk header");
        }
        const uint8_t kind = chdr[0];
        const uint8_t stream_id = chdr[1];
        const uint16_t flags = be16(chdr.data() + 2);
        const int64_t pts = be64s(chdr.data() + 4);
        const uint64_t payload_length = be64(chdr.data() + 12);
        const uint64_t uncompressed = be64(chdr.data() + 20);
        switch (kind) {
            case STREAM_CONFIG:
            case VIDEO_KEY_STATE:
            case VIDEO_TILE_UPDATE:
            case VIDEO_FORMAT_CHANGE:
            case AUDIO_BLOCK:
            case SUBTITLE_PACKET:
            case SUBTITLE_BITMAP:
            case CHAPTER_TABLE:
            case ATTACHMENT:
            case RECOVERY_POINT:
            case SEEK_INDEX:
            case INTEGRITY_TABLE:
            case END:
                break;
            default: {
                std::fclose(f);
                fail("unknown CASUNAT2 chunk type " + std::to_string(kind));
            }
        }
        if (payload_length > limits.max_chunk_bytes ||
            payload_length > size - pos - kChunkHeaderSize ||
            uncompressed < payload_length ||
            uncompressed > limits.max_chunk_bytes) {
            std::fclose(f);
            fail("invalid CASUNAT2 chunk length");
        }
        std::string payload(payload_length, '\0');
        if (payload_length > 0 &&
            std::fread(&payload[0], 1, payload_length, f) != payload_length) {
            std::fclose(f);
            fail("truncated CASUNAT2 chunk payload");
        }
        if (seen_integrity && kind != END) {
            std::fclose(f);
            fail("CASUNAT2 contains data after integrity table");
        }
        const std::string digest_before_chunk = digest.hexdigest();
        if (kind == INTEGRITY_TABLE) {
            if (seen_integrity) {
                std::fclose(f);
                fail("duplicate CASUNAT2 integrity table");
            }
            seen_integrity = true;
            integrity_offset = offset;
        } else if (!seen_integrity) {
            digest.update(chdr.data(), kChunkHeaderSize);
            digest.update(payload.data(), payload.size());
            std::string combined;
            combined.reserve(kChunkHeaderSize + payload.size());
            combined.append(reinterpret_cast<const char*>(chdr.data()),
                            kChunkHeaderSize);
            combined.append(payload);
            observed_chunk_hashes.emplace_back(offset,
                                               Sha256::oneshot(combined));
        }
        try {
            topology->feed(kind, stream_id, flags, pts, payload,
                           uncompressed, true);
        } catch (const nat::NativeV2ValidationError& exc) {
            std::fclose(f);
            fail(exc.what());
        }

        Chunk chunk;
        chunk.chunk_type = kind;
        chunk.stream_id = stream_id;
        chunk.flags = flags;
        chunk.pts = pts;
        chunk.payload_length = payload_length;
        chunk.uncompressed_length = uncompressed;
        chunk.offset = offset;
        const bool keep_payload =
            load_payloads || kind == SEEK_INDEX || kind == INTEGRITY_TABLE ||
            kind == RECOVERY_POINT || kind == END;
        if (keep_payload) chunk.payload = std::move(payload);
        c.chunks.push_back(std::move(chunk));
        c.offsets.push_back(offset);

        // Seek index.
        if (kind == SEEK_INDEX) {
            try {
                const JsonValue values_root =
                    parse_strict_json(c.chunks.back().payload);
                const JsonValue* entries = values_root.find("entries");
                if (!values_root.is_object() || !entries ||
                    !entries->is_array() ||
                    entries->as_array().items.size() > limits.max_chunks)
                    throw CasuError("invalid seek entries");
                for (const JsonValue& item : entries->as_array().items) {
                    if (!item.is_object() ||
                        item.as_object().items.size() != 5)
                        throw CasuError("invalid seek entry");
                    static const std::set<std::string> required = {
                        "stream_id", "target_pts", "key_state_pts",
                        "key_state_offset", "first_update_offset"};
                    SeekEntry e;
                    for (const auto& [key, value] : item.as_object().items) {
                        if (!required.count(key) || value.is_bool() ||
                            !value.is_int())
                            throw CasuError("invalid seek entry values");
                        if (key == "stream_id") e.stream_id = value.as_int();
                        else if (key == "target_pts")
                            e.target_pts = value.as_int();
                        else if (key == "key_state_pts")
                            e.key_state_pts = value.as_int();
                        else if (key == "key_state_offset")
                            e.key_state_offset = value.as_int();
                        else if (key == "first_update_offset")
                            e.first_update_offset = value.as_int();
                    }
                    c.seek_entries.push_back(e);
                }
            } catch (const JsonError&) {
                std::fclose(f);
                fail("invalid CASUNAT2 seek index");
            } catch (const CasuError&) {
                std::fclose(f);
                fail("invalid CASUNAT2 seek index");
            }
        } else if (kind == INTEGRITY_TABLE) {
            try {
                const JsonValue values =
                    parse_strict_json(c.chunks.back().payload);
                if (!values.is_object()) throw CasuError("table not object");
                const JsonValue* sha = values.find("sha256_before_integrity");
                if (!sha || !sha->is_string())
                    throw CasuError("missing digest");
                integrity_expected = sha->as_string();
                std::vector<std::pair<uint64_t, std::string>> normalized;
                if (const JsonValue* hashes = values.find("chunk_sha256")) {
                    if (!hashes->is_array() ||
                        hashes->as_array().items.size() > limits.max_chunks)
                        throw CasuError("invalid chunk hash table");
                    for (const JsonValue& item : hashes->as_array().items) {
                        if (!item.is_object() ||
                            item.as_object().items.size() != 2 ||
                            !item.find("offset") || !item.find("sha256"))
                            throw CasuError("invalid chunk hash entry");
                        const JsonValue* off = item.find("offset");
                        const JsonValue* hash = item.find("sha256");
                        if (off->is_bool() || !off->is_int() ||
                            !hash->is_string())
                            throw CasuError("invalid chunk hash entry");
                        normalized.emplace_back(
                            static_cast<uint64_t>(off->as_int()),
                            hash->as_string());
                    }
                }
                c.chunk_hashes = std::move(normalized);
                bool valid = integrity_expected->size() == 64 &&
                             is_hex64(*integrity_expected);
                for (const auto& [entry_offset, hash] : c.chunk_hashes) {
                    if (entry_offset < kHeaderSize || hash.size() != 64 ||
                        !is_hex64(hash))
                        valid = false;
                }
                if (!valid) throw CasuError("invalid chunk hash");
            } catch (const JsonError&) {
                std::fclose(f);
                fail("invalid CASUNAT2 integrity table");
            } catch (const CasuError&) {
                std::fclose(f);
                fail("invalid CASUNAT2 integrity table");
            }
        } else if (kind == RECOVERY_POINT) {
            try {
                JsonValue value =
                    decode_recovery_point(c.chunks.back().payload, offset,
                                          digest_before_chunk,
                                          parsed_by_offset, true);
                c.recovery_points.push_back(
                    RecoveryPoint{offset, std::move(value)});
            } catch (const NativeV2Error&) {
                std::fclose(f);
                throw;
            }
        }
        parsed_by_offset[offset] = c.chunks.back();

        pos += kChunkHeaderSize + payload_length;
        if (kind == END) {
            if (pos != size) {
                std::fclose(f);
                fail("trailing bytes after CASUNAT2 END");
            }
            break;
        }
        if (std::fseek(f, static_cast<long>(pos), SEEK_SET) != 0) {
            std::fclose(f);
            fail("CASUNAT2 seek failed");
        }
    }
    std::fclose(f);

    if (c.chunks.empty() || c.chunks.back().chunk_type != END)
        fail("CASUNAT2 is missing END chunk");
    if (!integrity_expected.has_value() || !integrity_offset.has_value())
        fail("CASUNAT2 is missing integrity table");
    const bool verified = digest.hexdigest() == *integrity_expected;
    if (!verified) fail("CASUNAT2 integrity verification failed");
    c.integrity_verified = verified;
    try {
        topology->finalize(true);
    } catch (const nat::NativeV2ValidationError& exc) {
        fail(exc.what());
    }

    // R21/R23 cross-checks against the seek index.
    {
        std::map<uint64_t, const Chunk*> offset_map;
        for (std::size_t i = 0; i < c.chunks.size(); ++i)
            offset_map[c.offsets[i]] = &c.chunks[i];
        std::map<int64_t, std::pair<int64_t, int64_t>> previous_by_stream;
        for (const SeekEntry& entry : c.seek_entries) {
            const auto key_it = offset_map.find(
                static_cast<uint64_t>(entry.key_state_offset));
            const auto first_it = offset_map.find(
                static_cast<uint64_t>(entry.first_update_offset));
            const Chunk* key =
                key_it == offset_map.end() ? nullptr : key_it->second;
            const Chunk* first_update =
                first_it == offset_map.end() ? nullptr : first_it->second;
            if (entry.target_pts != entry.key_state_pts || key == nullptr ||
                key->chunk_type != VIDEO_KEY_STATE ||
                key->stream_id != entry.stream_id ||
                key->pts != entry.key_state_pts)
                fail("CASUNAT2 seek index key-state offset is invalid");
            if (first_update == nullptr ||
                first_update->stream_id != entry.stream_id ||
                (first_update->chunk_type != VIDEO_KEY_STATE &&
                 first_update->chunk_type != VIDEO_TILE_UPDATE))
                fail("CASUNAT2 seek index dependency offset is invalid");
            auto prior = previous_by_stream.find(entry.stream_id);
            const std::pair<int64_t, int64_t> marker{entry.key_state_pts,
                                                     entry.key_state_offset};
            if (prior != previous_by_stream.end() && !(prior->second < marker))
                fail("CASUNAT2 seek index is not strictly ordered");
            previous_by_stream[entry.stream_id] = marker;
        }

        std::set<uint64_t> expected_offsets;
        for (std::size_t i = 0; i < c.chunks.size(); ++i)
            if (c.chunks[i].chunk_type != INTEGRITY_TABLE &&
                c.chunks[i].chunk_type != END)
                expected_offsets.insert(c.offsets[i]);
        std::map<uint64_t, std::string> table_map;
        for (const auto& [o, h] : c.chunk_hashes) table_map[o] = h;
        if (table_map.size() != expected_offsets.size() ||
            c.chunk_hashes.size() != table_map.size())
            fail("CASUNAT2 chunk hash table does not cover the verified prefix");
        for (const auto& o : expected_offsets)
            if (!table_map.count(o))
                fail("CASUNAT2 chunk hash table does not cover the verified prefix");
        std::map<uint64_t, std::string> observed_map;
        for (const auto& [o, h] : observed_chunk_hashes) observed_map[o] = h;
        if (observed_map != table_map)
            fail("CASUNAT2 chunk hash table does not cover the verified prefix");

        std::set<std::pair<int64_t, int64_t>> indexed_keys;
        for (const SeekEntry& entry : c.seek_entries)
            indexed_keys.insert({entry.stream_id, entry.key_state_offset});
        std::set<std::pair<int64_t, int64_t>> actual_keys;
        for (const Chunk& chunk : c.chunks)
            if (chunk.chunk_type == VIDEO_KEY_STATE)
                actual_keys.insert({chunk.stream_id,
                                    static_cast<int64_t>(chunk.offset)});
        if (indexed_keys != actual_keys)
            fail("CASUNAT2 seek index does not cover every video key state");
    }

    if (load_payloads) {
        try {
            nat::NativeV2PayloadValidator semantic(c.manifest, limits, true);
            for (const Chunk& chunk : c.chunks)
                semantic.feed(chunk.chunk_type, chunk.stream_id, chunk.flags,
                              chunk.pts, chunk.payload,
                              chunk.uncompressed_length, true);
            semantic.finalize(true);
        } catch (const nat::NativeV2ValidationError& exc) {
            fail(exc.what());
        }
    }
    return c;
}

// ---------------------------------------------------------------------------
// Indexed reads / reconstruction
// ---------------------------------------------------------------------------

namespace {

uint64_t query_file_size(const std::string& path) {
    std::FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) throw CasuError("could not read CASUNAT2 file: " + path);
    if (std::fseek(f, 0, SEEK_END) != 0) {
        std::fclose(f);
        throw CasuError("could not stat CASUNAT2 file");
    }
#ifdef _WIN32
    const int64_t size = ::_ftelli64(f);
#else
    const int64_t size = std::ftell(f);
#endif
    std::fclose(f);
    if (size < 0) throw CasuError("could not stat CASUNAT2 file");
    return static_cast<uint64_t>(size);
}

}  // namespace

Chunk Container::read_chunk_at(uint64_t offset) const {
    const uint64_t size = query_file_size(path);
    if (size > limits.max_file_bytes || offset < kHeaderSize ||
        offset + kChunkHeaderSize > size)
        fail("chunk offset is outside CASUNAT2 file");
    std::FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) fail("could not read CASUNAT2 file: " + path);
    Chunk chunk;
    try {
        if (std::fseek(f, static_cast<long>(offset), SEEK_SET) != 0)
            fail("chunk offset is outside CASUNAT2 file");
        std::vector<uint8_t> header(kChunkHeaderSize);
        if (std::fread(header.data(), 1, kChunkHeaderSize, f) !=
            kChunkHeaderSize)
            fail("truncated chunk at indexed offset");
        const uint8_t kind = header[0];
        const uint8_t stream_id = header[1];
        const uint16_t flags = be16(header.data() + 2);
        const int64_t pts = be64s(header.data() + 4);
        const uint64_t payload_length = be64(header.data() + 12);
        const uint64_t uncompressed = be64(header.data() + 20);
        // tell() == offset + CHUNK_HEADER_SIZE here.
        if (payload_length > limits.max_chunk_bytes ||
            payload_length > size - offset - kChunkHeaderSize ||
            uncompressed < payload_length ||
            uncompressed > limits.max_chunk_bytes || flags != 0)
            fail("indexed chunk payload exceeds file");
        std::string payload(payload_length, '\0');
        if (payload_length > 0 &&
            std::fread(&payload[0], 1, payload_length, f) != payload_length)
            fail("truncated chunk at indexed offset");
        const std::string* expected_hash = nullptr;
        for (const auto& [entry_offset, hash] : chunk_hashes)
            if (entry_offset == offset) {
                expected_hash = &hash;
                break;
            }
        if (!expected_hash)
            fail("indexed chunk is absent from CASUNAT2 hash table");
        std::string combined;
        combined.reserve(kChunkHeaderSize + payload.size());
        combined.append(reinterpret_cast<const char*>(header.data()),
                        kChunkHeaderSize);
        combined.append(payload);
        if (Sha256::oneshot(combined) != *expected_hash)
            fail("on-disk CASUNAT2 chunk changed after verification");
        switch (kind) {
            case STREAM_CONFIG:
            case VIDEO_KEY_STATE:
            case VIDEO_TILE_UPDATE:
            case VIDEO_FORMAT_CHANGE:
            case AUDIO_BLOCK:
            case SUBTITLE_PACKET:
            case SUBTITLE_BITMAP:
            case CHAPTER_TABLE:
            case ATTACHMENT:
            case RECOVERY_POINT:
            case SEEK_INDEX:
            case INTEGRITY_TABLE:
            case END:
                break;
            default:
                fail("indexed chunk has unknown type");
        }
        chunk.chunk_type = kind;
        chunk.stream_id = stream_id;
        chunk.flags = flags;
        chunk.pts = pts;
        chunk.payload_length = payload_length;
        chunk.uncompressed_length = uncompressed;
        chunk.offset = offset;
        chunk.payload = std::move(payload);
    } catch (...) {
        std::fclose(f);
        throw;
    }
    std::fclose(f);
    return chunk;
}

JsonValue Container::read_audio_block_meta_at(uint64_t offset) const {
    const uint64_t size = query_file_size(path);
    if (size > limits.max_file_bytes || offset < kHeaderSize ||
        offset + kChunkHeaderSize > size)
        fail("chunk offset is outside CASUNAT2 file");
    std::FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) fail("could not read CASUNAT2 file: " + path);
    JsonValue meta;
    try {
        if (std::fseek(f, static_cast<long>(offset), SEEK_SET) != 0)
            fail("chunk offset is outside CASUNAT2 file");
        std::vector<uint8_t> header(kChunkHeaderSize);
        if (std::fread(header.data(), 1, kChunkHeaderSize, f) !=
            kChunkHeaderSize)
            fail("truncated chunk at indexed offset");
        const uint8_t kind = header[0];
        const uint16_t flags = be16(header.data() + 2);
        const uint64_t payload_length = be64(header.data() + 12);
        if (kind != AUDIO_BLOCK || flags != 0)
            fail("indexed chunk is not an audio block");
        if (payload_length > limits.max_chunk_bytes ||
            payload_length > size - offset - kChunkHeaderSize)
            fail("indexed chunk payload exceeds file");
        const std::size_t prefix_size = static_cast<std::size_t>(
            std::min<uint64_t>(payload_length,
                               4ULL + limits.max_audio_meta_bytes));
        std::vector<uint8_t> prefix(prefix_size);
        if (std::fread(prefix.data(), 1, prefix_size, f) != prefix_size)
            prefix.resize(std::ftell(f) < 0 ? 0 : prefix.size());
        if (prefix_size < 4)
            fail("audio block metadata prefix is truncated");
        const uint32_t meta_length =
            (uint32_t(uint8_t(prefix[0])) << 24) |
            (uint32_t(uint8_t(prefix[1])) << 16) |
            (uint32_t(uint8_t(prefix[2])) << 8) |
            uint32_t(uint8_t(prefix[3]));
        if (meta_length > limits.max_audio_meta_bytes ||
            4ULL + meta_length > prefix_size)
            fail("audio block metadata exceeds limit");
        meta = parse_strict_json(
            reinterpret_cast<const char*>(prefix.data()) + 4, meta_length);
    } catch (const JsonError&) {
        std::fclose(f);
        fail("invalid audio block metadata");
    } catch (...) {
        std::fclose(f);
        throw;
    }
    std::fclose(f);
    if (!meta.is_object())
        fail("audio block metadata must be an object");
    return meta;
}

ReconstructionPlan seek_video(const Container& container, int64_t stream_id,
                              int64_t target_pts) {
    bool found = false;
    ReconstructionPlan plan;
    plan.stream_id = stream_id;
    plan.target_pts = target_pts;
    for (const SeekEntry& entry : container.seek_entries) {
        if (entry.stream_id != stream_id ||
            entry.key_state_pts > target_pts)
            continue;
        // max by (key_state_pts, key_state_offset); first hit wins ties
        // (strictly ordered index makes ties impossible).
        if (!found || entry.key_state_pts > plan.key_state_pts ||
            (entry.key_state_pts == plan.key_state_pts &&
             entry.key_state_offset > plan.key_state_offset)) {
            found = true;
            plan.key_state_pts = entry.key_state_pts;
            plan.key_state_offset = entry.key_state_offset;
            plan.first_update_offset = entry.first_update_offset;
        }
    }
    if (!found) fail("no video key state at or before target PTS");
    return plan;
}

nat::CanonicalFrame reconstruct_video(const Container& container,
                                      int64_t stream_id, int64_t target_pts) {
    const ReconstructionPlan plan = seek_video(container, stream_id, target_pts);
    nat::TileStateCache cache;
    uint64_t offset = static_cast<uint64_t>(plan.key_state_offset);
    const uint64_t size = query_file_size(container.path);
    bool first = true;
    int64_t dependencies = 0;
    while (offset < size) {
        const Chunk chunk = container.read_chunk_at(offset);
        const uint64_t following =
            offset + kChunkHeaderSize + chunk.payload_length;
        if (chunk.stream_id == stream_id) {
            if (first) {
                if (chunk.chunk_type != VIDEO_KEY_STATE ||
                    chunk.pts != plan.key_state_pts)
                    fail("seek index does not reference its video key state");
                cache.apply_key_state(chunk.payload, container.limits);
                first = false;
            } else if (chunk.chunk_type == VIDEO_KEY_STATE) {
                if (chunk.pts > target_pts) break;
                cache.apply_key_state(chunk.payload, container.limits);
            } else if (chunk.chunk_type == VIDEO_TILE_UPDATE) {
                if (chunk.pts > target_pts) break;
                ++dependencies;
                if (dependencies >
                    static_cast<int64_t>(container.limits.max_dependency_depth))
                    fail("CASUNAT2 video dependency depth exceeds limit");
                cache.apply_tile_update(chunk.payload, container.limits);
            }
        }
        if (chunk.chunk_type == SEEK_INDEX ||
            chunk.chunk_type == INTEGRITY_TABLE || chunk.chunk_type == END)
            break;
        offset = following;
    }
    const nat::CanonicalFrame* frame = cache.frame();
    if (!frame) fail("video reconstruction produced no frame");
    return *frame;
}

// ---------------------------------------------------------------------------
// Recovery / repair
// ---------------------------------------------------------------------------
NativeV2Recovery recover_native_v2(const std::string& path) {
    CasuLimits recovery_limits;
    recovery_limits.max_file_bytes = 512ULL * 1024 * 1024;
    std::FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) fail("damaged CASUNAT2 file is unavailable");
    std::string raw;
    try {
        raw.resize(recovery_limits.max_file_bytes + 1);
        const std::size_t got =
            std::fread(&raw[0], 1, raw.size(), f);
        raw.resize(got);
    } catch (const std::exception&) {
        std::fclose(f);
        fail("damaged CASUNAT2 file is unavailable");
    }
    std::fclose(f);
    if (raw.size() > recovery_limits.max_file_bytes)
        fail("damaged CASUNAT2 file exceeds recovery size limit");
    if (raw.size() < kHeaderSize) fail("truncated CASUNAT2 header");

    NativeV2Recovery result;
    result.path = path;
    const auto* bytes = reinterpret_cast<const uint8_t*>(raw.data());
    if (std::memcmp(bytes, "CASUNAT2", 8) != 0 ||
        be16(bytes + 8) != VERSION || be16(bytes + 10) != 0)
        fail("unsupported CASUNAT2 header/version");
    const uint64_t manifest_length = be64(bytes + 12);
    if (manifest_length > recovery_limits.max_manifest_bytes ||
        kHeaderSize + manifest_length > raw.size())
        fail("invalid CASUNAT2 manifest length");
    try {
        result.manifest = parse_strict_json(raw.data() + kHeaderSize,
                                            manifest_length);
        nat::validate_manifest(result.manifest, recovery_limits);
    } catch (const JsonError&) {
        fail("invalid CASUNAT2 manifest");
    } catch (const nat::NativeV2ValidationError& exc) {
        fail(exc.what());
    }

    uint64_t pos = kHeaderSize + manifest_length;
    std::vector<Chunk> chunks;
    std::optional<JsonValue> recovery_value;
    int64_t boundary = 0;
    Sha256 prefix_digest;
    prefix_digest.update(raw.data(), pos);
    std::map<uint64_t, Chunk> chunk_by_offset;
    while (pos + kChunkHeaderSize <= raw.size() &&
           chunks.size() < recovery_limits.max_chunks) {
        const uint64_t offset = pos;
        const auto* chdr = bytes + pos;
        const uint8_t kind = chdr[0];
        const uint8_t stream_id = chdr[1];
        const uint16_t flags = be16(chdr + 2);
        const int64_t pts = be64s(chdr + 4);
        const uint64_t payload_length = be64(chdr + 12);
        const uint64_t uncompressed = be64(chdr + 20);
        pos += kChunkHeaderSize;
        if (flags != 0 || payload_length > recovery_limits.max_chunk_bytes ||
            payload_length > raw.size() - pos ||
            uncompressed < payload_length ||
            uncompressed > recovery_limits.max_chunk_bytes)
            break;
        Chunk chunk;
        chunk.chunk_type = kind;
        chunk.stream_id = stream_id;
        chunk.flags = flags;
        chunk.pts = pts;
        chunk.uncompressed_length = uncompressed;
        chunk.offset = offset;
        chunk.payload.assign(raw.data() + pos, payload_length);
        pos += payload_length;
        switch (kind) {
            case STREAM_CONFIG:
            case VIDEO_KEY_STATE:
            case VIDEO_TILE_UPDATE:
            case VIDEO_FORMAT_CHANGE:
            case AUDIO_BLOCK:
            case SUBTITLE_PACKET:
            case SUBTITLE_BITMAP:
            case CHAPTER_TABLE:
            case ATTACHMENT:
            case RECOVERY_POINT:
            case SEEK_INDEX:
            case INTEGRITY_TABLE:
            case END:
                break;
            default:
                goto loop_end;  // unknown type stops the tolerant walk
        }
        chunks.push_back(chunk);
        if (kind == RECOVERY_POINT) {
            try {
                JsonValue value = decode_recovery_point(
                    chunk.payload, offset, prefix_digest.hexdigest(),
                    chunk_by_offset, false);
                boundary = coerce_int_opt(
                               value.find("last_complete_chunk_offset"))
                               .value_or(0);
                recovery_value = std::move(value);
            } catch (const NativeV2Error&) {
                break;
            }
        }
        chunk_by_offset[offset] = chunk;
        prefix_digest.update(raw.data() + offset, pos - offset);
    loop_end:;
    }
    if (!recovery_value.has_value())
        fail("CASUNAT2 contains no usable recovery point");
    result.recovery_point = std::move(*recovery_value);
    result.complete_chunk_offset = boundary;

    // Recompute per-chunk offsets to filter the usable prefix.
    uint64_t walk = kHeaderSize + manifest_length;
    for (const Chunk& chunk : chunks) {
        const uint64_t chunk_offset = walk;
        if (chunk_offset <= static_cast<uint64_t>(boundary) &&
            chunk.chunk_type != RECOVERY_POINT)
            result.chunks.push_back(chunk);
        walk += kChunkHeaderSize + chunk.payload_length;
    }
    return result;
}

std::string repair_native_v2(const std::string& source,
                             const std::string& target) {
    const NativeV2Recovery recovery = recover_native_v2(source);
    const std::filesystem::path destination =
        std::filesystem::weakly_canonical(target);
    const std::filesystem::path original =
        std::filesystem::weakly_canonical(recovery.path);
    if (destination == original)
        fail("repair output must differ from the damaged source");
    JsonValue manifest = deep_copy(recovery.manifest);
    {
        auto recovery_info = std::make_shared<JsonObject>();
        recovery_info->items["status"] = JsonValue(std::string(
            "RECOVERED_PREFIX"));
        recovery_info->items["source_filename"] = JsonValue(
            original.filename().string());
        recovery_info->items["last_complete_chunk_offset"] = JsonValue(
            recovery.complete_chunk_offset);
        manifest.as_object_mut().items["recovery"] =
            JsonValue(std::move(recovery_info));
    }
    return write_native_v2(destination.string(), manifest, recovery.chunks, 0);
}

// ---------------------------------------------------------------------------
// Writer
// ---------------------------------------------------------------------------
std::string write_native_v2_streamed(
    const std::string& path, const JsonValue& manifest,
    const std::function<std::optional<Chunk>()>& next_chunk,
    uint64_t recovery_interval, const CasuLimits* limits_ptr) {
    std::vector<Chunk> chunks;
    CasuLimits limits;
    if (limits_ptr) limits = *limits_ptr;
    else limits.max_chunk_bytes = 512ULL * 1024 * 1024;
    limits.validate();
    const std::filesystem::path target(path);

    nat::NativeV2PayloadValidator validator(manifest, limits, true);
    const std::string manifest_bytes =
        dump_json(manifest, true, true);  // sort_keys, ensure_ascii=True
    if (manifest_bytes.size() > limits.max_manifest_bytes)
        fail("manifest exceeds CASUNAT2 limit");

    std::error_code ec;
    std::filesystem::create_directories(target.parent_path(), ec);

    // Atomic temp file in the target directory.
    std::filesystem::path temporary;
    std::FILE* out = nullptr;
    for (int attempt = 0; attempt < 64 && !out; ++attempt) {
        temporary = target.parent_path() /
                    ("." + target.filename().string() + ".tmp" +
                     std::to_string(::getpid()) + "-" +
                     std::to_string(attempt));
        out = std::fopen(temporary.string().c_str(), "wb");
    }
    if (!out) fail("could not create temporary CASUNAT2 file");

    try {
        std::string header;
        header.reserve(kHeaderSize);
        header += "CASUNAT2";
        header.push_back(char((VERSION >> 8) & 0xFF));
        header.push_back(char(VERSION & 0xFF));
        header.push_back('\0');
        header.push_back('\0');  // flags = 0
        put_be64(header, manifest_bytes.size());
        if (header.size() + manifest_bytes.size() > limits.max_file_bytes)
            fail("CASUNAT2 header/manifest exceeds file limit");

        Sha256 prefix_digest;
        auto write_all = [&](const void* data, std::size_t size,
                             bool update_digest) {
            if (std::fwrite(data, 1, size, out) != size)
                fail("CASUNAT2 write failed");
            if (update_digest) prefix_digest.update(data, size);
        };
        write_all(header.data(), header.size(), false);
        write_all(manifest_bytes.data(), manifest_bytes.size(), false);
        prefix_digest.update(header);
        prefix_digest.update(manifest_bytes);
        uint64_t position = header.size() + manifest_bytes.size();
        uint64_t written_chunk_count = 0;

        auto append_chunk = [&](const std::string& packed) {
            const uint64_t payload_size =
                packed.size() >= kChunkHeaderSize
                    ? packed.size() - kChunkHeaderSize
                    : 0;
            if (written_chunk_count >= limits.max_chunks ||
                packed.size() < kChunkHeaderSize ||
                payload_size > limits.max_chunk_bytes ||
                position + packed.size() > limits.max_file_bytes)
                fail("CASUNAT2 output exceeds configured limits");
            write_all(packed.data(), packed.size(), false);
            prefix_digest.update(packed);
            position += packed.size();
            ++written_chunk_count;
        };

        std::vector<std::pair<uint64_t, std::string>> chunk_hashes;
        std::map<int64_t, std::pair<int64_t, int64_t>> key_states;
        std::map<int64_t, std::size_t> seek_positions;
        std::vector<SeekEntry> seek;
        std::map<int64_t, uint64_t> key_offsets;
        std::map<int64_t, uint64_t> audio_offsets;

        // Canonical in-band stream configurations (never drift from the
        // manifest stream table).
        for (const auto& [stream_id, descriptor] : validator.descriptors()) {
            const std::string config_payload =
                dump_json(descriptor, true, true);
            Chunk config;
            config.chunk_type = STREAM_CONFIG;
            config.stream_id = static_cast<uint8_t>(stream_id);
            config.pts = 0;
            config.payload = config_payload;
            validator.feed(config.chunk_type, config.stream_id, 0, 0,
                           config.payload, std::nullopt, false);
            const uint64_t config_offset = position;
            const std::string packed = pack_chunk(config);
            append_chunk(packed);
            chunk_hashes.emplace_back(config_offset,
                                      Sha256::oneshot(packed));
        }

        for (uint64_t ordinal = 1;; ++ordinal) {
            if (ordinal > limits.max_chunks)
                fail("chunk count exceeds CASUNAT2 limit");
            auto maybe = next_chunk();
            if (!maybe.has_value()) break;
            Chunk chunk = std::move(*maybe);
            if (chunk.payload.size() > limits.max_chunk_bytes)
                fail("chunk exceeds CASUNAT2 limit");
            if (chunk.chunk_type == STREAM_CONFIG) {
                JsonValue configured;
                try {
                    configured = parse_strict_json(chunk.payload);
                } catch (const JsonError&) {
                    throw nat::NativeV2ValidationError(
                        "invalid supplied stream config");
                }
                auto descriptor = validator.descriptors().find(chunk.stream_id);
                if (descriptor == validator.descriptors().end() ||
                    !casu::natv2::json_equal(configured,
                                                 descriptor->second))
                    throw nat::NativeV2ValidationError(
                        "supplied stream config differs from manifest");
                continue;
            }
            validator.feed(chunk.chunk_type, chunk.stream_id, chunk.flags,
                           chunk.pts, chunk.payload,
                           chunk.uncompressed_length, false);
            const uint64_t offset = position;
            const std::string packed = pack_chunk(chunk);
            append_chunk(packed);
            chunk_hashes.emplace_back(offset, Sha256::oneshot(packed));
            if (chunk.chunk_type == VIDEO_KEY_STATE) {
                key_states[chunk.stream_id] = {chunk.pts,
                                               static_cast<int64_t>(offset)};
                key_offsets[chunk.stream_id] = offset;
                seek_positions[chunk.stream_id] = seek.size();
                seek.push_back(SeekEntry{chunk.stream_id, chunk.pts, chunk.pts,
                                         static_cast<int64_t>(offset),
                                         static_cast<int64_t>(offset)});
            } else if (chunk.chunk_type == VIDEO_TILE_UPDATE) {
                auto pos_it = seek_positions.find(chunk.stream_id);
                if (pos_it == seek_positions.end())
                    fail("video tile update precedes its key state");
                SeekEntry entry = seek[pos_it->second];
                if (entry.first_update_offset == entry.key_state_offset) {
                    entry.first_update_offset =
                        static_cast<int64_t>(offset);
                    seek[pos_it->second] = entry;
                }
            } else if (chunk.chunk_type == AUDIO_BLOCK) {
                audio_offsets[chunk.stream_id] = offset;
            }
            if (recovery_interval != 0 &&
                ordinal % recovery_interval == 0) {
                auto recovery = std::make_shared<JsonObject>();
                recovery->items["version"] = JsonValue(int64_t(1));
                recovery->items["last_complete_chunk_offset"] =
                    JsonValue(static_cast<int64_t>(offset));
                auto key_map = std::make_shared<JsonObject>();
                for (const auto& [sid, off] : key_offsets)
                    key_map->items[std::to_string(sid)] =
                        JsonValue(static_cast<int64_t>(off));
                auto audio_map = std::make_shared<JsonObject>();
                for (const auto& [sid, off] : audio_offsets)
                    audio_map->items[std::to_string(sid)] =
                        JsonValue(static_cast<int64_t>(off));
                recovery->items["key_state_offsets"] =
                    JsonValue(key_map);
                recovery->items["audio_block_offsets"] =
                    JsonValue(audio_map);
                recovery->items["sha256_before_recovery"] =
                    JsonValue(prefix_digest.hexdigest());
                // Checkpoint hash covers the serialization WITHOUT the
                // checkpoint field (double serialization like the reference).
                const std::string without_checkpoint =
                    dump_json(JsonValue(recovery), true, true);
                const std::string checkpoint_hash =
                    Sha256::oneshot(without_checkpoint);
                recovery->items["checkpoint_sha256"] =
                    JsonValue(checkpoint_hash);
                Chunk rp;
                rp.chunk_type = RECOVERY_POINT;
                rp.stream_id = 0;
                rp.pts = chunk.pts;
                rp.payload = dump_json(JsonValue(recovery), true, true);
                const uint64_t recovery_offset = position;
                const std::string rp_packed = pack_chunk(rp);
                append_chunk(rp_packed);
                chunk_hashes.emplace_back(recovery_offset,
                                          Sha256::oneshot(rp_packed));
            }
        }
        validator.finalize(false);
        std::stable_sort(seek.begin(), seek.end(),
                         [](const SeekEntry& a, const SeekEntry& b) {
                             if (a.stream_id != b.stream_id)
                                 return a.stream_id < b.stream_id;
                             if (a.key_state_pts != b.key_state_pts)
                                 return a.key_state_pts < b.key_state_pts;
                             return a.key_state_offset < b.key_state_offset;
                         });
        const uint64_t index_offset = position;
        Chunk index_chunk;
        index_chunk.chunk_type = SEEK_INDEX;
        index_chunk.stream_id = 0;
        index_chunk.pts = 0;
        index_chunk.payload = index_payload(seek);
        const std::string index_packed = pack_chunk(index_chunk);
        append_chunk(index_packed);
        chunk_hashes.emplace_back(index_offset, Sha256::oneshot(index_packed));

        const std::string digest_hex = prefix_digest.hexdigest();
        {
            auto table = std::make_shared<JsonArray>();
            for (const auto& [entry_offset, hash] : chunk_hashes) {
                auto entry = std::make_shared<JsonObject>();
                entry->items["offset"] =
                    JsonValue(static_cast<int64_t>(entry_offset));
                entry->items["sha256"] = JsonValue(hash);
                table->items.push_back(JsonValue(std::move(entry)));
            }
            auto integrity = std::make_shared<JsonObject>();
            integrity->items["sha256_before_integrity"] =
                JsonValue(digest_hex);
            integrity->items["chunk_sha256"] = JsonValue(std::move(table));
            Chunk integrity_chunk;
            integrity_chunk.chunk_type = INTEGRITY_TABLE;
            integrity_chunk.stream_id = 0;
            integrity_chunk.pts = static_cast<int64_t>(index_offset);
            integrity_chunk.payload =
                dump_json(JsonValue(std::move(integrity)), true, true);
            append_chunk(pack_chunk(integrity_chunk));
        }
        {
            Chunk end_chunk;
            end_chunk.chunk_type = END;
            end_chunk.stream_id = 0;
            end_chunk.pts = 0;
            end_chunk.payload.clear();
            append_chunk(pack_chunk(end_chunk));
        }
        std::fflush(out);
        fsync_file(out);
        std::fclose(out);
        out = nullptr;
    } catch (...) {
        if (out) std::fclose(out);
        std::filesystem::remove(temporary, ec);
        throw;
    }
    // Atomic publish.
    std::error_code replace_ec;
    std::filesystem::remove(target, replace_ec);
    std::filesystem::rename(temporary, target, replace_ec);
    if (replace_ec) {
        std::filesystem::remove(temporary, ec);
        fail("could not publish CASUNAT2 file");
    }
    return target.string();
}


std::string write_native_v2(const std::string& path, const JsonValue& manifest,
                            const std::vector<Chunk>& chunks,
                            uint64_t recovery_interval,
                            const CasuLimits* limits_ptr) {
    std::size_t index = 0;
    return write_native_v2_streamed(
        path, manifest,
        [&]() -> std::optional<Chunk> {
            if (index >= chunks.size()) return std::nullopt;
            return chunks[index++];
        },
        recovery_interval, limits_ptr);
}

}  // namespace casunat2
}  // namespace casu
