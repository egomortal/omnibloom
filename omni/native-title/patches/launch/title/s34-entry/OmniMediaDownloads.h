// Isolated media-worker startup. No WebKit/SDL or shared browser-launcher state.
// All network/file checks run only after an explicit request, on one bounded thread.
#pragma once
#include "OmniMediaSection.h"
#include "OmniNonBlocking.h"
#include <arpa/inet.h>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <mutex>
#include <new>
#include <netinet/in.h>
#include <poll.h>
#include <pthread.h>
#include <string>
#include <sys/socket.h>
#include <unistd.h>
#include <utility>

namespace OmniMediaDownloads {
constexpr uint16_t launcherPort = 8080;
constexpr const char* workerPath = "/data/omni-downloader/python-worker.elf";
constexpr const char* launchRoute = "/hbldr?path=%2Fdata%2Fomni-downloader%2Fpython-worker.elf&args=omni-media-worker&daemon=1&pipe=0";
constexpr const char* preferencePath = "/data/omni/media-downloads-enabled.flag";
inline uintptr_t nextTabIdentity() {
    static std::atomic<uintptr_t> next { 1 };
    return next.fetch_add(1, std::memory_order_relaxed);
}

enum class HttpState { Complete, Refused, Failed };
struct HttpResult { HttpState state = HttpState::Failed; int status = 0; std::string body; };
inline uint64_t nowMs() {
    return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
}
inline bool waitFd(int fd, short events, uint64_t deadline) {
    for (;;) {
        const uint64_t now = nowMs();
        if (now >= deadline) return false;
        pollfd p { fd, events, 0 };
        const int n = poll(&p, 1, static_cast<int>(deadline - now));
        if (n < 0 && errno == EINTR) continue;
        return n > 0 && (p.revents & (events | POLLHUP | POLLERR));
    }
}
inline bool decimal(const std::string& value, size_t maximum, size_t& number) {
    if (value.empty()) return false;
    number = 0;
    for (unsigned char c : value) {
        if (c < '0' || c > '9' || number > (maximum - (c - '0')) / 10) return false;
        number = number * 10 + c - '0';
    }
    return number <= maximum;
}
inline std::string trim(std::string value) {
    const auto first = value.find_first_not_of(" \t");
    return first == std::string::npos ? "" : value.substr(first, value.find_last_not_of(" \t") - first + 1);
}
inline HttpResult parseHttp(const std::string& raw) {
    const auto split = raw.find("\r\n\r\n"), first = raw.find("\r\n");
    if (split == std::string::npos || split > 4096 || first == std::string::npos) return {};
    const std::string status = raw.substr(0, first);
    if (status.size() < 12 || (status.compare(0, 9, "HTTP/1.0 ") && status.compare(0, 9, "HTTP/1.1 "))
        || (status.size() > 12 && status[12] != ' ')) return {};
    size_t code = 0;
    if (!decimal(status.substr(9, 3), 599, code) || code < 100) return {};
    bool hasLength = false;
    size_t length = 0;
    for (size_t at = first + 2; at < split;) {
        const auto end = raw.find("\r\n", at), colon = raw.find(':', at);
        if (end == std::string::npos || end > split || colon == std::string::npos || colon >= end) return {};
        std::string name = raw.substr(at, colon - at);
        if (name.empty()) return {};
        for (char& c : name) {
            const unsigned char u = static_cast<unsigned char>(c);
            if (!((u >= 'A' && u <= 'Z') || (u >= 'a' && u <= 'z') || (u >= '0' && u <= '9') || u == '-')) return {};
            if (c >= 'A' && c <= 'Z') c = static_cast<char>(c + ('a' - 'A'));
        }
        const std::string value = trim(raw.substr(colon + 1, end - colon - 1));
        if (name == "transfer-encoding") return {}; // Fixed-size endpoints only; no ambiguous framing.
        if (name == "content-length") {
            if (hasLength || !decimal(value, 4096, length)) return {};
            hasLength = true;
        }
        at = end + 2;
    }
    std::string body = raw.substr(split + 4);
    if (body.size() > 4096 || (hasLength && body.size() != length)) return {};
    return { HttpState::Complete, static_cast<int>(code), std::move(body) };
}
// IPv4 loopback only; no DNS, redirects, environment proxy or browser cookies.
inline HttpResult get(uint16_t port, const std::string& path, unsigned timeoutMs) {
    if (!port || path.empty() || path[0] != '/' || path.find_first_of("\r\n ") != std::string::npos) return {};
    const uint64_t deadline = nowMs() + timeoutMs;
    const int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return {};
    struct Close { int fd; ~Close() { close(fd); } } owner { fd };
    if (!omniSocketNonBlocking(fd)) return {};
#ifdef SO_NOSIGPIPE
    int noSignal = 1;
    if (setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &noSignal, sizeof(noSignal))) return {};
#endif
    sockaddr_in address {};
    address.sin_family = AF_INET;
    address.sin_port = htons(port);
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (connect(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address))) {
        if (errno == ECONNREFUSED) return { HttpState::Refused, 0, "" };
        if (errno != EINPROGRESS || !waitFd(fd, POLLOUT, deadline)) return {};
        int error = 0; socklen_t size = sizeof(error);
        if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &size)) return {};
        if (error == ECONNREFUSED) return { HttpState::Refused, 0, "" };
        if (error) return {};
    }
    const std::string request = "GET " + path + " HTTP/1.0\r\nHost: 127.0.0.1:" + std::to_string(port)
        + "\r\nConnection: close\r\nAccept: application/json\r\n\r\n";
    size_t sent = 0;
    while (sent < request.size()) {
        if (!waitFd(fd, POLLOUT, deadline)) return {};
#ifdef MSG_NOSIGNAL
        const ssize_t n = send(fd, request.data() + sent, request.size() - sent, MSG_NOSIGNAL);
#else
        const ssize_t n = send(fd, request.data() + sent, request.size() - sent, 0);
#endif
        if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        if (n <= 0) return {};
        sent += static_cast<size_t>(n);
    }
    std::string raw;
    raw.reserve(1024);
    char buffer[1024];
    for (;;) {
        if (!waitFd(fd, POLLIN, deadline)) return {};
        const ssize_t n = recv(fd, buffer, sizeof(buffer), 0);
        if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        if (n < 0) return {};
        if (!n) break;
        if (raw.size() + static_cast<size_t>(n) > 8192) return {};
        raw.append(buffer, static_cast<size_t>(n));
    }
    return parseHttp(raw);
}

// The current /healthz schema has exactly two fields. Reject duplicates and impostors.
class HealthReader {
    const std::string& text;
    size_t at = 0;
    void ws() { while (at < text.size() && (text[at] == ' ' || text[at] == '\t' || text[at] == '\r' || text[at] == '\n')) ++at; }
    bool take(char c) { ws(); if (at >= text.size() || text[at] != c) return false; ++at; return true; }
    bool string(std::string& value) {
        if (!take('"')) return false;
        value.clear();
        while (at < text.size()) {
            unsigned char c = static_cast<unsigned char>(text[at++]);
            if (c == '"') return true;
            if (c < 32) return false;
            if (c == '\\') {
                if (at >= text.size()) return false;
                c = static_cast<unsigned char>(text[at++]);
                if (c == 'u') {
                    unsigned code = 0;
                    for (unsigned i = 0; i < 4; ++i) {
                        if (at >= text.size()) return false;
                        const unsigned char h = static_cast<unsigned char>(text[at++]);
                        const unsigned digit = h >= '0' && h <= '9' ? h - '0' : h >= 'a' && h <= 'f' ? h - 'a' + 10 : h >= 'A' && h <= 'F' ? h - 'A' + 10 : 16;
                        if (digit > 15) return false;
                        code = code * 16 + digit;
                    }
                    if (code > 127) return false;
                    c = static_cast<unsigned char>(code);
                } else if (c != '"' && c != '\\' && c != '/') return false;
            }
            value += static_cast<char>(c);
        }
        return false;
    }
public:
    explicit HealthReader(const std::string& value) : text(value) { }
    bool valid() {
        bool service = false, version = false;
        if (!take('{')) return false;
        for (unsigned count = 0; count < 2; ++count) {
            std::string key, value;
            if (!string(key) || !take(':')) return false;
            if (key == "service" && !service) {
                if (!string(value) || value != "omni-media-worker") return false;
                service = true;
            } else if (key == "api_version" && !version) {
                if (!take('1')) return false;
                version = true;
            } else return false;
            if (count == 0 && !take(',')) return false;
        }
        if (!take('}')) return false;
        ws();
        return service && version && at == text.size();
    }
};
inline bool healthy(const HttpResult& r) { return r.state == HttpState::Complete && r.status == 200 && HealthReader(r.body).valid(); }

enum class Outcome { Ready, Unavailable, PackageMissing, LauncherRejected, TimedOut, CoolingDown };
struct Completion { Outcome outcome = Outcome::Unavailable; std::string link; uint16_t port = 0; };
enum class RequestResult { Started, Disabled, PrivateLink, InvalidLink, Busy, ThreadError };
struct Hooks {
    HttpResult (*fetch)(uint16_t, const std::string&, unsigned) = get;
    uint64_t (*clock)() = nowMs;
    void (*sleep)(unsigned) = [](unsigned ms) { poll(nullptr, 0, static_cast<int>(ms)); };
    bool (*packageReady)() = [] { return access(workerPath, R_OK) == 0; };
    unsigned (*port)() = OmniMediaSection::assignedPort;
};
inline Outcome ensureReady(const Hooks& hooks, uint64_t& nextLaunchAt, uint16_t* readyPort = nullptr) {
    const unsigned selected = hooks.port();
    if (selected < 8761 || selected > 8899) return Outcome::Unavailable;
    const uint16_t workerPort = static_cast<uint16_t>(selected);
    HttpResult health = hooks.fetch(workerPort, "/healthz", 800);
    if (healthy(health)) { if (readyPort) *readyPort = workerPort; return Outcome::Ready; }
    // Only connection refusal establishes an unused listener. Any other owner/failure is left alone.
    if (health.state != HttpState::Refused) return Outcome::Unavailable;
    if (!hooks.packageReady()) return Outcome::PackageMissing;
    if (hooks.clock() < nextLaunchAt) return Outcome::CoolingDown;
    nextLaunchAt = hooks.clock() + 60000; // Also suppress retries after an ambiguous submission.
    const HttpResult launch = hooks.fetch(launcherPort, launchRoute, 3000);
    if (launch.state == HttpState::Refused || (launch.state == HttpState::Complete && launch.status != 200)) return Outcome::LauncherRejected;
    const uint64_t deadline = hooks.clock() + 30000;
    do {
        health = hooks.fetch(workerPort, "/healthz", 800);
        if (healthy(health)) { if (readyPort) *readyPort = workerPort; return Outcome::Ready; }
        if (health.state == HttpState::Complete) return Outcome::Unavailable;
        if (hooks.clock() >= deadline) break;
        hooks.sleep(250);
    } while (hooks.clock() < deadline);
    return Outcome::TimedOut;
}

class Starter {
    struct Task { Starter* owner; std::string link; };
    Hooks hooks;
    std::atomic<bool> busy { false }, complete { false };
    std::mutex lock;
    Completion result;
    uint64_t nextLaunchAt = 0; // Only the sole startup thread reads/writes this.
    static void* run(void* opaque) {
        auto* task = static_cast<Task*>(opaque);
        auto* owner = task->owner;
        Completion value;
        value.link = std::move(task->link);
        delete task;
#if defined(__cpp_exceptions)
        try { value.outcome = ensureReady(owner->hooks, owner->nextLaunchAt, &value.port); }
        catch (...) { value.outcome = Outcome::Unavailable; }
#else
        value.outcome = ensureReady(owner->hooks, owner->nextLaunchAt, &value.port);
#endif
        { std::lock_guard<std::mutex> guard(owner->lock); owner->result = std::move(value); }
        owner->complete.store(true, std::memory_order_release);
        return nullptr;
    }
public:
    explicit Starter(Hooks value = {}) : hooks(value) { }
    Starter(const Starter&) = delete;
    Starter& operator=(const Starter&) = delete;
    RequestResult request(bool enabled, const std::string& link, bool privateSource) {
        if (!enabled) return RequestResult::Disabled;
        if (!link.empty() && privateSource) return RequestResult::PrivateLink;
        if (!link.empty() && !OmniMediaSection::validLink(link)) return RequestResult::InvalidLink;
        bool wasBusy = false;
        if (!busy.compare_exchange_strong(wasBusy, true, std::memory_order_acq_rel)) return RequestResult::Busy;
        Task* task = nullptr;
#if defined(__cpp_exceptions)
        try { task = new (std::nothrow) Task { this, link }; }
        catch (...) { busy.store(false, std::memory_order_release); return RequestResult::ThreadError; }
#else
        task = new (std::nothrow) Task { this, link };
#endif
        if (!task) { busy.store(false, std::memory_order_release); return RequestResult::ThreadError; }
        pthread_attr_t attr;
        int error = pthread_attr_init(&attr);
        if (!error) {
            error = pthread_attr_setstacksize(&attr, 256 * 1024);
            if (!error) error = pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
            pthread_t thread;
            if (!error) error = pthread_create(&thread, &attr, run, task);
            pthread_attr_destroy(&attr);
        }
        if (error) { delete task; busy.store(false, std::memory_order_release); return RequestResult::ThreadError; }
        return RequestResult::Started;
    }
    // Called on UI loop. Never waits for startup, networking or its mutex.
    bool take(Completion& value) {
        if (!complete.load(std::memory_order_acquire)) return false;
        std::unique_lock<std::mutex> guard(lock, std::try_to_lock);
        if (!guard.owns_lock()) return false;
        value = std::move(result);
        complete.store(false, std::memory_order_release);
        busy.store(false, std::memory_order_release);
        return true;
    }
};
inline Starter& starter() { static Starter* const value = new Starter; return *value; } // Browser exits with _exit.
inline const char* message(Outcome result) {
    switch (result) {
    case Outcome::Ready: return "Media downloads ready";
    case Outcome::PackageMissing: return "Media downloads package is unavailable";
    case Outcome::LauncherRejected: return "Media downloads could not start";
    case Outcome::TimedOut: return "Media downloads is still unavailable; browsing can continue";
    case Outcome::CoolingDown: return "Media downloads is starting; try again shortly";
    default: return "Media downloads unavailable; browsing can continue";
    }
}
} // namespace OmniMediaDownloads
