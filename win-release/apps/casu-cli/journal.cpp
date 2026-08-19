// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "journal.hpp"

#include "casu/formats.hpp"
#include "casu/sha256.hpp"

#include <chrono>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <string>
#include <vector>

namespace casu::cli {

using casu::CasuError;
using casu::JsonArray;
using casu::JsonObject;
using casu::JsonValue;

namespace {

constexpr std::size_t MAX_JOURNAL_BYTES = 8 * 1024 * 1024;
constexpr std::size_t MAX_REPORT_RESULTS = 10'000;

JsonValue json_null() { return JsonValue(std::nullptr_t{}); }

JsonValue job_record(const JournalJob& job) {
    JsonObject record;
    record.items["source"] = JsonValue(job.source);
    record.items["output"] = JsonValue(job.output);
    record.items["profile"] = job.profile;
    return JsonValue(std::make_shared<JsonObject>(std::move(record)));
}

long long path_size(const std::string& path) {
    std::error_code ec;
    const std::uintmax_t size = std::filesystem::file_size(path, ec);
    return ec ? -1 : (long long)size;
}

void atomic_write_text(const std::string& path, const std::string& payload) {
    std::filesystem::path target = std::filesystem::absolute(path);
    std::error_code ec;
    std::filesystem::create_directories(target.parent_path(), ec);
    const std::filesystem::path temporary =
        target.parent_path() / ("." + target.filename().string() + ".tmp");
    {
        FILE* f = std::fopen(temporary.string().c_str(), "wb");
        if (!f) throw CasuError("could not create journal file: " + path);
        const bool wrote = std::fwrite(payload.data(), 1, payload.size(), f) == payload.size();
        std::fflush(f);
        std::fclose(f);
        if (!wrote) {
            std::filesystem::remove(temporary, ec);
            throw CasuError("could not write journal file: " + path);
        }
    }
    std::filesystem::remove(target, ec);
    std::filesystem::rename(temporary, target, ec);
    if (ec) {
        std::filesystem::remove(temporary, ec);
        throw CasuError("could not finalize journal file: " + path);
    }
}

}  // namespace

std::string conversion_journal_path(const std::string& directory,
                                    const std::vector<JournalJob>& jobs) {
    auto identity = std::make_shared<JsonArray>();
    for (const JournalJob& job : jobs) identity->items.push_back(job_record(job));
    const std::string encoded = casu::dump_json(JsonValue(std::move(identity)));
    const std::string digest = casu::Sha256::oneshot(encoded);
    std::filesystem::path dir = std::filesystem::absolute(directory);
    return (dir / (".casu-conversion-" + digest.substr(0, 16) + ".json")).string();
}

void write_journal(const std::string& path, const std::string& state,
                   const std::vector<JournalJob>& jobs, const JsonValue& results) {
    if (path.empty()) return;
    const long long updated_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                                     std::chrono::system_clock::now().time_since_epoch())
                                     .count();
    JsonObject payload;
    payload.items["version"] = JsonValue(int64_t(1));
    payload.items["state"] = JsonValue(state);
    payload.items["updated_ns"] = JsonValue(updated_ns);
    auto recorded_jobs = std::make_shared<JsonArray>();
    for (const JournalJob& job : jobs) recorded_jobs->items.push_back(job_record(job));
    payload.items["jobs"] = JsonValue(std::move(recorded_jobs));
    payload.items["results"] = results;
    const JsonValue value = JsonValue(std::make_shared<JsonObject>(std::move(payload)));
    const std::string text = casu::dump_json(value);
    if (text.size() > MAX_JOURNAL_BYTES)
        throw CasuError("conversion journal exceeds safety limit");
    atomic_write_text(path, text);
}

std::map<std::pair<std::string, std::string>, JsonValue> load_resume(
    const std::string& path, const std::vector<JournalJob>& jobs) {
    std::map<std::pair<std::string, std::string>, JsonValue> reusable;
    if (path.empty()) return reusable;

    std::error_code ec;
    if (!std::filesystem::is_regular_file(path, ec)) return reusable;

    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) throw CasuError("conversion journal is invalid");
    std::fseek(f, 0, SEEK_END);
    long size = std::ftell(f);
    std::fseek(f, 0, SEEK_SET);
    if (size < 0 || (unsigned long)size > MAX_JOURNAL_BYTES) {
        std::fclose(f);
        throw CasuError("conversion journal is invalid");
    }
    std::string text((std::size_t)size, '\0');
    if (size > 0 && std::fread(&text[0], 1, (std::size_t)size, f) != (std::size_t)size) {
        std::fclose(f);
        throw CasuError("conversion journal is invalid");
    }
    std::fclose(f);

    JsonValue payload;
    try {
        payload = casu::parse_json(text);
    } catch (const casu::JsonError&) {
        throw CasuError("conversion journal is invalid");
    }
    const JsonValue* version = payload.find("version");
    const JsonValue* recorded_jobs = payload.find("jobs");
    const JsonValue* recorded_results = payload.find("results");
    if (!version || !version->is_int() || version->as_int() != 1 || !recorded_jobs ||
        !recorded_jobs->is_array() || !recorded_results || !recorded_results->is_array())
        throw CasuError("conversion journal is invalid");

    // The journal must describe the exact same job set (source/output/profile).
    if (recorded_jobs->as_array().items.size() != jobs.size())
        throw CasuError("conversion journal does not match the requested jobs");
    for (std::size_t i = 0; i < jobs.size(); ++i) {
        const JsonValue& recorded = recorded_jobs->as_array().items[i];
        const std::string expected = casu::dump_json(job_record(jobs[i]));
        if (casu::dump_json(recorded) != expected)
            throw CasuError("conversion journal does not match the requested jobs");
    }

    for (const JsonValue& item : recorded_results->as_array().items) {
        if (!item.is_object()) continue;
        const JsonValue* status = item.find("status");
        const JsonValue* out = item.find("output");
        const JsonValue* src = item.find("source");
        const JsonValue* size_v = item.find("output_size");
        const JsonValue* digest_v = item.find("output_sha256");
        if (!status || !status->is_string() || status->as_string() != "converted") continue;
        if (!out || !out->is_string() || !src || !src->is_string()) continue;
        if (!size_v || !size_v->is_int() || !digest_v || !digest_v->is_string()) continue;
        const std::string expected_digest = digest_v->as_string();
        if (expected_digest.size() != 64) continue;
        const std::string output_path = out->as_string();
        const long long expected_size = size_v->as_int();
        if (path_size(output_path) != expected_size) continue;
        if (casu::sha256_file(output_path) != expected_digest) continue;
        JsonValue reused = item;
        if (reused.is_object()) {
            JsonObject copy = reused.as_object_mut();
            copy.items["resumed"] = JsonValue(true);
            reused = JsonValue(std::make_shared<JsonObject>(std::move(copy)));
        }
        reusable[{src->as_string(), output_path}] = std::move(reused);
    }
    return reusable;
}

}  // namespace casu::cli