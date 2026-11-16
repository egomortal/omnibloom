// OMNI_WHATSNEW_V1: the pure part of the "What's new" page (no SDL, no WebKit, no file I/O). The shell side is
// OmniWhatsNewShell.h (written by tools/apply_whatsnew.py, which copies this file into engine/entry); the page is
// omni://pages/whatsnew/ and its data whatsnew/whatsnew.json is generated from CHANGELOG.md by the repo's
// tools/gen_whatsnew.py. Tested on the host with g++ (tools/test_whatsnew.cpp).
//
// "Updated" means: the key (Omni's release version + the data file's content id) differs from the key saved in
// /data/omni/whatsnew-seen.txt. A fresh install (no saved key and no earlier Omni data) only records the key: the
// first-run welcome page is what a new user sees. Nothing here ever goes to the network.
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

namespace OmniWhatsNew {

constexpr const char* kSeenName = "whatsnew-seen.txt";        // under /data/omni (omniData)
constexpr const char* kPagePath = "whatsnew/index.html";      // under omni://pages/
constexpr const char* kPageAfterUpdate = "whatsnew/index.html?after=1";
constexpr const char* kDataRel = "/whatsnew/whatsnew.json";   // under the pages root (/app0/pages)
constexpr int kQuickRowId = 8611;          // Options > Settings row (Controls is there too)
constexpr uint32_t kDelayMs = 4000;        // the page waits this long after start, and for a quiet screen
constexpr uint32_t kGiveUpMs = 120000;     // never quiet by then: a notice instead of a tab
constexpr size_t kSeenMax = 200;           // bytes of the saved key taken
constexpr size_t kHeadMax = 4096;          // bytes of the data file read for its id

// The content id of the data file: the value of its first "id" key (the generator writes it second, after "schema";
// groups and items have no "id" key). Lower-case hex, 8-64 characters; anything else: "".
inline std::string dataId(const std::string& head)
{
    const std::string k = "\"id\"";
    size_t i = head.find(k);
    if (i == std::string::npos) return std::string();
    i += k.size();
    while (i < head.size() && (head[i] == ' ' || head[i] == '\t' || head[i] == '\r' || head[i] == '\n')) ++i;
    if (i >= head.size() || head[i] != ':') return std::string();
    ++i;
    while (i < head.size() && (head[i] == ' ' || head[i] == '\t' || head[i] == '\r' || head[i] == '\n')) ++i;
    if (i >= head.size() || head[i] != '"') return std::string();
    std::string v;
    for (++i; i < head.size() && head[i] != '"'; ++i) {
        const char c = head[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')) || v.size() >= 64) return std::string();
        v += c;
    }
    if (i >= head.size() || v.size() < 8) return std::string();
    return v;
}

// The saved key from the file's text: its first line, spaces trimmed, at most kSeenMax bytes, printable ASCII only.
inline std::string seenFrom(const std::string& file)
{
    std::string line = file.substr(0, file.find('\n'));
    if (line.size() > kSeenMax) line.resize(kSeenMax);
    size_t a = 0, b = line.size();
    while (a < b && (line[a] == ' ' || line[a] == '\t' || line[a] == '\r')) ++a;
    while (b > a && (line[b - 1] == ' ' || line[b - 1] == '\t' || line[b - 1] == '\r')) --b;
    line = line.substr(a, b - a);
    for (unsigned char c : line)
        if (c < 0x20 || c > 0x7e) return std::string();
    return line;
}

// "0.5.3" + "1a2b3c4d..." -> "0.5.3+1a2b3c4d..."; no id (no data file): the version alone. No version: "".
inline std::string key(const std::string& version, const std::string& id)
{
    if (version.empty()) return std::string();
    return id.empty() ? version : version + "+" + id;
}

// The version part of a key ("0.5.3+abc" -> "0.5.3").
inline std::string versionOf(const std::string& k) { return k.substr(0, k.find('+')); }

enum Decision : int { kNone, kShow, kRecord };
// seen: the saved key ("" none); now: this build's key; hadData: Omni data from an earlier run exists.
inline Decision decide(const std::string& seen, const std::string& now, bool hadData)
{
    if (now.empty() || seen == now) return kNone;
    if (seen.empty() && !hadData) return kRecord;   // fresh install: the welcome page, not What's new
    return kShow;
}

// "Try it" actions a page may ask for (whatsnew.try): a fixed list, nothing else is run.
enum Action : int { aNone, aControls, aOptions, aSettings, aSiteSettings, aTabs, aHistory, aDownloads, aReadingList,
    aBookmarks, aScreenshots, aActionCount };
inline const char* actionName(int a)
{
    static const char* const t[aActionCount] = { "", "controls", "options", "settings", "site-settings", "tabs", "history",
        "downloads", "reading-list", "bookmarks", "screenshots" };
    return a > aNone && a < aActionCount ? t[a] : "";
}
inline Action action(const std::string& name)
{
    if (name.empty() || name.size() > 32) return aNone;
    for (int a = aNone + 1; a < aActionCount; ++a)
        if (name == actionName(a)) return Action(a);
    return aNone;
}

// The page's whatsnew.info answer (JSON object; strings are plain ASCII keys / codes, escaped anyway).
inline std::string jsonQuote(const std::string& s)
{
    std::string o = "\"";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { o += '\\'; o += char(c); }
        else if (c < 0x20 || c == 0x7f) { static const char* hex = "0123456789abcdef"; o += "\\u00"; o += hex[c >> 4]; o += hex[c & 15]; }
        else o += char(c);
    }
    return o + "\"";
}
inline std::string infoJson(const std::string& version, const std::string& previousKey, const std::string& lang, bool afterUpdate)
{
    std::string actions = "[";
    for (int a = aNone + 1; a < aActionCount; ++a) actions += std::string(a > 1 ? "," : "") + "\"" + actionName(a) + "\"";
    return "{\"version\":" + jsonQuote(version) + ",\"previous\":" + jsonQuote(versionOf(previousKey)) + ",\"lang\":"
        + jsonQuote(lang.empty() ? std::string("en") : lang) + ",\"afterUpdate\":" + (afterUpdate ? "true" : "false")
        + ",\"actions\":" + actions + "]}";
}

// Options row value: "Omni 0.5.3".
inline std::string rowValue(const std::string& version) { return version.empty() ? std::string() : "Omni " + version; }

} // namespace OmniWhatsNew
