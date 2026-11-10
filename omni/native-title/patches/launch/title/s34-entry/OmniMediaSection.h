// Standalone integration policy. No WebKit, SDL, networking or process globals.
#pragma once
#include <cstdint>
#include <atomic>
#include <string>
#include <vector>

namespace OmniMediaSection {
constexpr unsigned apiVersion = 1;
constexpr unsigned defaultPort = 0;
using PortResolver = unsigned (*)();
inline std::atomic<PortResolver>& portResolver() { static std::atomic<PortResolver> value { nullptr }; return value; }
inline void setPortResolver(PortResolver value) { portResolver().store(value); }
inline unsigned assignedPort() {
    const auto resolver = portResolver().load();
    const unsigned value = resolver ? resolver() : 0;
    return value >= 8761 && value <= 8899 ? value : 0;
}
enum class Action { Disabled, Unavailable, InvalidLink, PrivateLink, Full, Create, Activate };
struct Tab { uintptr_t key; bool owned; std::string url; };
struct Plan { Action action; uintptr_t key = 0; std::string url; };

inline std::string base(unsigned port = defaultPort) {
    if (!port) port = assignedPort();
    return port >= 8761 && port <= 8899 ? "http://127.0.0.1:" + std::to_string(port) + "/downloads" : "";
}
inline bool belongs(const std::string& url, const std::string& origin) {
    return !origin.empty() && (url == origin || url.compare(0, origin.size()+1, origin + "#") == 0);
}
inline bool validLink(const std::string& url) {
    auto start = url.compare(0, 8, "https://") == 0 ? 8u : url.compare(0, 7, "http://") == 0 ? 7u : 0u;
    if (!start || url.size() > 4096) return false;
    auto end = url.find_first_of("/?#", start);
    auto authority = url.substr(start, end == std::string::npos ? end : end-start);
    if (authority.empty() || authority.find('@') != std::string::npos) return false;
    for (unsigned char c : url) if (c <= 32 || c == 127 || c == '\\') return false;
    return true;
}
inline std::string encode(const std::string& value) {
    static const char hex[] = "0123456789ABCDEF";
    std::string out;
    for (unsigned char c : value) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' || c == '~') out += char(c);
        else { out += '%'; out += hex[c >> 4]; out += hex[c & 15]; }
    }
    return out;
}
// Worker readiness comes from the host's asynchronous health check, never UI-thread IO.
// No probing/launching occurs while disabled. A link only prefills; it cannot start a job.
inline Plan plan(bool enabled, bool ready, const std::vector<Tab>& tabs,
                 const std::string& link = "", bool privateSource = false,
                 unsigned port = defaultPort, unsigned limit = 4) {
    if (!enabled) return {Action::Disabled, 0, ""};
    if (!ready || base(port).empty()) return {Action::Unavailable, 0, ""};
    if (!link.empty() && privateSource) return {Action::PrivateLink, 0, ""};
    if (!link.empty() && !validLink(link)) return {Action::InvalidLink, 0, ""};
    const auto root = base(port);
    for (const auto& tab : tabs) {
        if (tab.owned && belongs(tab.url, root))
            return {Action::Activate, tab.key, link.empty() ? "" : root + "#url=" + encode(link)};
    }
    if (tabs.size() >= limit) return {Action::Full, 0, ""};
    return {Action::Create, 0, root + (link.empty() ? "" : "#url=" + encode(link))};
}
} // namespace OmniMediaSection
