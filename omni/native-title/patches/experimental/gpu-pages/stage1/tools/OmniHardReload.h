// OMNI_HARD_RELOAD_V1: the pure part of "Reload without cache" (hold-Cross page menu, Options > Browse). No SDL, no
// WebKit. The shell side is OmniHardReloadShell.h (written by tools/apply_hard_reload.py); tested on the host with g++
// (tools/test_hard_reload.cpp).
#pragma once
#include <string>

namespace OmniHardReload {

constexpr int kContextRowId = 7741;   // hold-Cross page menu row
constexpr int kQuickRowId = 8741;     // Options > Browse row (>= 900: its hook sits before the `r.id >= 900` line)
constexpr const char* kLabel = "Reload without cache";
constexpr const char* kNotice = "Reloaded without cache";

inline bool startsWithNoCase(const std::string& s, const char* p)
{
    size_t i = 0;
    for (; p[i]; ++i) {
        if (i >= s.size()) return false;
        char c = s[i];
        if (c >= 'A' && c <= 'Z') c = char(c + ('a' - 'A'));
        if (c != p[i]) return false;
    }
    return true;
}

// Only ordinary web pages (http / https with a host): never omni:// built-in pages, the new-tab page, about:, data:,
// file:, blob: or a crashed tab (its own Reload restarts the web process).
inline bool offered(const std::string& url, bool omniPagesTab, bool newTabPage, bool crashed)
{
    if (omniPagesTab || newTabPage || crashed) return false;
    size_t p;
    if (startsWithNoCase(url, "https://")) p = 8;
    else if (startsWithNoCase(url, "http://")) p = 7;
    else return false;
    return p < url.size() && url[p] != '/' && url[p] != '?' && url[p] != '#';
}

} // namespace OmniHardReload
