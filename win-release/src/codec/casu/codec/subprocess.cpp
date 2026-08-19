// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
#include "casu/codec/subprocess.hpp"

#ifdef CASU_HAS_QT
#include <QByteArray>
#include <QProcess>
#include <QString>
#include <QStringList>

#include <array>
#else
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <future>
#include <random>
#include <thread>
#endif

namespace casu::codec {

Subprocess::Subprocess(std::string program, std::chrono::milliseconds timeout)
    : program_(std::move(program)), timeout_(timeout) {}

#ifdef CASU_HAS_QT

namespace {
void append_capped(std::string& sink, const char* data, std::size_t n, std::size_t cap) {
    const std::size_t room = n < cap - std::min(sink.size(), cap) ? n : cap - std::min(sink.size(), cap);
    if (room > 0) sink.append(data, room);
}
}  // namespace

ProcessResult Subprocess::run(const std::vector<std::string>& args,
                              std::size_t max_stdout, std::size_t max_stderr) const {
    ProcessResult out;
    QProcess proc;
    proc.setProcessChannelMode(QProcess::SeparateChannels);
    proc.setProgram(QString::fromUtf8(program_.c_str()));
    QStringList qargs;
    qargs.reserve(int(args.size()));
    for (const auto& arg : args) qargs << QString::fromUtf8(arg.c_str());
    proc.setArguments(qargs);
    proc.start();
    if (!proc.waitForStarted(10000)) {
        out.stderr_data = "could not start process: " + program_;
        return out;
    }
    out.started = true;
    const auto deadline = std::chrono::steady_clock::now() + timeout_;
    std::array<char, 65536> buf;
    while (proc.state() == QProcess::Running) {
        if (std::chrono::steady_clock::now() > deadline) {
            out.timed_out = true;
            out.stderr_data = "subprocess exceeded configured time limit";
            proc.kill();
            proc.waitForFinished(5000);
            return out;
        }
        proc.waitForReadyRead(100);
        while (proc.bytesAvailable() > 0) {
            const qint64 n = proc.read(buf.data(), qint64(buf.size()));
            if (n <= 0) break;
            if (out.stdout_data.size() >= max_stdout) {
                out.timed_out = true;
                out.stderr_data = "subprocess output exceeds configured limit";
                proc.kill();
                proc.waitForFinished(5000);
                return out;
            }
            append_capped(out.stdout_data, buf.data(), std::size_t(n), max_stdout);
        }
        const QByteArray err = proc.readAllStandardError();
        if (!err.isEmpty()) append_capped(out.stderr_data, err.constData(),
                                          std::size_t(err.size()), max_stderr);
    }
    proc.waitForFinished(5000);
    if (!out.timed_out) out.exit_code = proc.exitCode();
    const QByteArray so = proc.readAllStandardOutput();
    if (!so.isEmpty()) append_capped(out.stdout_data, so.constData(),
                                     std::size_t(so.size()), max_stdout);
    const QByteArray se = proc.readAllStandardError();
    if (!se.isEmpty()) append_capped(out.stderr_data, se.constData(),
                                     std::size_t(se.size()), max_stderr);
    return out;
}

#else  // CASU_HAS_QT not defined: _popen fallback with Windows argv quoting.

namespace {
std::string quote_win_arg(const std::string& arg) {
    std::string out;
    out.reserve(arg.size() + 2);
    out.push_back('"');
    for (char c : arg) {
        if (c == '"') out += "\\\"";
        else out.push_back(c);
    }
    out.push_back('"');
    return out;
}

std::string unique_stderr_file() {
    std::random_device rd;
    static std::mt19937_64 gen(rd());
    return (std::filesystem::temp_directory_path() /
            ("casu_proc_" + std::to_string(gen()) + ".err")).string();
}
}  // namespace

ProcessResult Subprocess::run(const std::vector<std::string>& args,
                              std::size_t max_stdout, std::size_t max_stderr) const {
    ProcessResult out;
    const std::string err_path = unique_stderr_file();
    std::string command = quote_win_arg(program_);
    for (const auto& arg : args) {
        command.push_back(' ');
        command += quote_win_arg(arg);
    }
    command += " 2> ";
    command += quote_win_arg(err_path);

    auto run_child = [&]() -> std::string {
        std::string collected;
        FILE* pipe = _popen(command.c_str(), "r");
        if (!pipe) return collected;
        char buf[65536];
        while (std::fgets(buf, int(sizeof(buf)), pipe)) {
            if (collected.size() >= max_stdout) break;
            collected.append(buf);
        }
        out.exit_code = _pclose(pipe);
        return collected;
    };
    std::future<std::string> future = std::async(std::launch::async, run_child);
    if (future.wait_for(timeout_) == std::future_status::timeout) {
        out.timed_out = true;
        out.stderr_data = "subprocess exceeded configured time limit";
        std::error_code ec;
        std::filesystem::remove(err_path, ec);
        return out;
    }
    out.started = true;
    out.stdout_data = future.get();
    std::ifstream err(err_path, std::ios::binary);
    if (err) {
        std::string detail((std::istreambuf_iterator<char>(err)),
                           std::istreambuf_iterator<char>());
        if (detail.size() > max_stderr) detail.resize(max_stderr);
        out.stderr_data = std::move(detail);
    }
    std::error_code ec;
    std::filesystem::remove(err_path, ec);
    return out;
}

#endif  // CASU_HAS_QT

}  // namespace casu::codec
