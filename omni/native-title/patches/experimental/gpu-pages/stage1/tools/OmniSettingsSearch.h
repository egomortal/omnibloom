// OMNI_SETTINGS_SEARCH_V1: the pure part of the search box at the top of Browser settings (no SDL, no WebKit).
// Works on (id, section, label, value) tuples, so any row any patch adds to the panel is searchable: the shell
// (OmniSettingsSearchShell.h) turns the panel's built rows into Entry values after omniFxSettingsBuild has added
// them all, asks filter() which to keep and in what order, and keeps the original OmniFxRow objects (same ids, so
// the same input handler). Installed by tools/apply_settings_search.py; tested by tools/test_settings_search.cpp.
#pragma once
#include <algorithm>
#include <cstddef>
#include <string>
#include <vector>

namespace OmniSettingsSearch {

constexpr int kSearchRowId = -780;    // "Search settings..." (negative: below every Browser settings id range)
constexpr int kNoMatchRowId = -781;   // "No settings match" (disabled)
constexpr size_t kMaxQuery = 60;

struct Entry {
    int id = 0;
    std::string section, label, value;
};
enum Tier {
    LabelStart = 0,    // the label starts with the query ("dark" -> "Dark mode")
    LabelWord,         // the query starts a word of the label ("size" -> "Pointer size")
    AllWords,          // every query word starts a word of the label or value ("pointer opa", "youtube tv")
    LabelSub,          // inside a word of the label, or across spaces ("dpad" -> "D-pad left / right")
    ValueMatch,        // the value ("tv" -> YouTube: "TV mode")
    Synonym,           // the synonym table ("ads" -> uBlock, "privacy" -> HTTPS-only ...)
    SectionMatch,      // the section name ("media" -> every Media row)
    NoMatch
};

// Lower-case ASCII; anything that is not a letter or digit separates words; bytes >= 0x80 (UTF-8) stay word bytes.
inline std::string norm(const std::string& s)
{
    std::string o;
    o.reserve(s.size());
    bool space = true;
    for (unsigned char c : s) {
        const bool word = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c >= 0x80;
        if (c >= 'A' && c <= 'Z') { o += char(c - 'A' + 'a'); space = false; continue; }
        if (word) { o += char(c); space = false; continue; }
        if (!space) { o += ' '; space = true; }
    }
    while (!o.empty() && o.back() == ' ') o.pop_back();
    return o;
}
inline std::string squash(const std::string& n)
{
    std::string o;
    for (char c : n) if (c != ' ') o += c;
    return o;
}
inline std::vector<std::string> words(const std::string& n)   // n already normalized
{
    std::vector<std::string> w;
    size_t i = 0;
    while (i < n.size()) {
        const size_t j = n.find(' ', i);
        w.push_back(n.substr(i, j == std::string::npos ? std::string::npos : j - i));
        if (j == std::string::npos) break;
        i = j + 1;
    }
    return w;
}
inline bool startsWith(const std::string& s, const std::string& p) { return s.size() >= p.size() && s.compare(0, p.size(), p) == 0; }
// `phrase` (normalized) starts at a word boundary of `text` (normalized)
inline bool wordPrefix(const std::string& text, const std::string& phrase)
{
    if (phrase.empty()) return false;
    return startsWith(text, phrase) || (" " + text).find(" " + phrase) != std::string::npos;
}

// What the keyboard gave: one line, trimmed, inner runs of blanks collapsed, at most kMaxQuery bytes (whole UTF-8).
inline std::string cleanQuery(const std::string& raw)
{
    std::string o;
    bool space = false;
    for (unsigned char c : raw) {
        if (c == ' ' || c == '\t' || c == '\r' || c == '\n' || c < 0x20) { space = !o.empty(); continue; }
        if (space) { o += ' '; space = false; }
        o += char(c);
    }
    if (o.size() > kMaxQuery) {
        size_t n = kMaxQuery;
        while (n > 0 && (static_cast<unsigned char>(o[n]) & 0xC0) == 0x80) --n;
        o.resize(n);
        while (!o.empty() && o.back() == ' ') o.pop_back();
    }
    return o;
}

// --- sections ----------------------------------------------------------------------------------------
// Browser settings has no section headers of its own, so a row's section comes from its label (first rule
// that has a phrase starting a word of the label). New rows from other patches land in a sensible section
// without touching this table; anything unknown is "General".
struct SectionRule { const char* name; const char* phrases[16]; };
inline const SectionRule* sectionRules(size_t& count)
{
    static const SectionRule rules[] = {
        { "Keyboard", { "word suggestion", "learn words", "learned words", "keyboard", "layout", "typing", nullptr } },
        { "Privacy", { "https", "sell or share", "password", "autofill", "permission", "cookie", "site data",
                       "clear", "block pages", "tracking", "privacy", "history", nullptr } },
        { "Media", { "autoplay", "youtube", "video", "playback", "continue watching", "hdr", "quality", "sound",
                     "audio", "sleep timer", nullptr } },
        { "Display", { "zoom", "text size", "interface size", "dark", "theme", "night light", "warmth", "display",
                       "bottom button bar", "quick access", "font", nullptr } },
        { "Controls", { "pointer", "stick", "d pad", "controller", "controls", "quick bar", "gamepad", "button",
                        nullptr } },
        { "Tabs", { "tab", nullptr } },
        { "Network", { "online", "offline", "send links", "phone", "network", nullptr } },
        { "Browsing", { "search", "home page", "start page", "javascript", "tell sites", "suggestion", "ublock",
                        "content block", "ads", nullptr } },
    };
    count = sizeof(rules) / sizeof(rules[0]);
    return rules;
}
inline std::string sectionOf(const std::string& label)
{
    const std::string n = norm(label);
    size_t count = 0;
    const SectionRule* rules = sectionRules(count);
    for (size_t i = 0; i < count; ++i)
        for (size_t k = 0; rules[i].phrases[k]; ++k)
            if (wordPrefix(n, rules[i].phrases[k])) return rules[i].name;
    return "General";
}

// --- synonyms ----------------------------------------------------------------------------------------
// A query word (or the whole query) that equals a key, or starts it with 3+ letters ("priv" -> "privacy"), also
// matches rows whose label has one of the key's phrases at a word start.
struct SynonymRule { const char* key; const char* phrases[14]; };
inline const SynonymRule* synonyms(size_t& count)
{
    static const SynonymRule table[] = {
        { "dark", { "dark", "theme", "night light", nullptr } },
        { "theme", { "theme", "dark", nullptr } },
        { "night", { "night light", "dark", nullptr } },
        { "ads", { "ublock", "content block", "ad block", "blocker", "block ads", nullptr } },
        { "adblock", { "ublock", "content block", "ad block", "blocker", "block ads", nullptr } },
        { "blocker", { "ublock", "content block", "ad block", "blocker", nullptr } },
        { "privacy", { "https", "ask sites not to sell", "sell or share", "learn words", "clear", "cookie",
                       "site data", "password", "autofill", "site permissions", "tracking", nullptr } },
        { "security", { "https", "block pages from reaching", "password", "site permissions", nullptr } },
        { "gpc", { "ask sites not to sell", "sell or share", nullptr } },
        { "tracking", { "ask sites not to sell", "sell or share", "ublock", "content block", nullptr } },
        { "video", { "quality", "hdr", "autoplay", "playback speed", "speed", "youtube", "continue watching",
                     "video", "sleep timer", nullptr } },
        { "media", { "quality", "hdr", "autoplay", "playback", "youtube", "continue watching", "video", "sound",
                     nullptr } },
        { "sound", { "autoplay", "mute", "sound", "audio", nullptr } },
        { "audio", { "autoplay", "mute", "sound", "audio", nullptr } },
        { "keyboard", { "keyboard", "layout", "word suggestions", "learn words", "clear learned words", nullptr } },
        { "typing", { "keyboard", "layout", "word suggestions", "learn words", nullptr } },
        { "text size", { "interface size", "ui size", "site zoom", "page zoom", "text size", "zoom", nullptr } },
        { "font", { "text size", "interface size", "zoom", nullptr } },
        { "zoom", { "zoom", "text size", "interface size", nullptr } },
        { "ui", { "interface size", "bottom button bar", "quick access row", nullptr } },
        { "interface", { "interface size", "bottom button bar", "quick access row", nullptr } },
        { "controller", { "pointer", "stick", "d pad", "controller", "controls guide", "quick bar", nullptr } },
        { "gamepad", { "controller", "pointer", "stick", "d pad", nullptr } },
        { "dpad", { "d pad", nullptr } },
        { "cursor", { "pointer", nullptr } },
        { "mouse", { "pointer", nullptr } },
        { "shortcuts", { "controls guide", "quick access buttons", "quick bar", nullptr } },
        { "buttons", { "controls guide", "quick access buttons", "bottom button bar", nullptr } },
        { "home", { "home page", "start page", "new tab", nullptr } },
        { "offline", { "back online", "offline", nullptr } },
        { "internet", { "back online", "offline", nullptr } },
        { "network", { "back online", "offline", "send links", nullptr } },
        { "memory", { "tab memory", "tabs kept loaded", "tab limit", nullptr } },
        { "ram", { "tab memory", "tabs kept loaded", "tab limit", nullptr } },
        { "eye", { "night light", "dark", "warmth", nullptr } },
        { "blue light", { "night light", "warmth", nullptr } },
        { "warm", { "night light", "warmth", nullptr } },
        { "performance", { "javascript jit", "tabs kept loaded", "tab limit", nullptr } },
        { "speed", { "playback speed", "pointer speed", "javascript jit", nullptr } },
        { "phone", { "send links", "qr", nullptr } },
        { "data", { "clear", "site data", "cookie", "learned words", nullptr } },
        { "reset", { "clear", nullptr } },
    };
    count = sizeof(table) / sizeof(table[0]);
    return table;
}
// The phrases the query reaches through the synonym table (normalized query in, empty when none).
inline std::vector<std::string> synonymPhrases(const std::string& nq)
{
    std::vector<std::string> cand = words(nq);
    if (cand.size() != 1) cand.push_back(nq);
    std::vector<std::string> out;
    size_t count = 0;
    const SynonymRule* t = synonyms(count);
    for (size_t i = 0; i < count; ++i) {
        const std::string key = t[i].key;
        bool hit = false;
        for (const auto& c : cand)
            if (c == key || (c.size() >= 3 && startsWith(key, c))) { hit = true; break; }
        if (!hit) continue;
        for (size_t k = 0; t[i].phrases[k]; ++k)
            if (std::find(out.begin(), out.end(), t[i].phrases[k]) == out.end()) out.push_back(t[i].phrases[k]);
    }
    return out;
}

// --- matching ----------------------------------------------------------------------------------------
// nq: norm(query); syn: synonymPhrases(nq) (passed in so a list is matched with one table walk).
inline Tier tierOf(const Entry& e, const std::string& nq, const std::vector<std::string>& syn)
{
    if (nq.empty()) return NoMatch;
    const std::string l = norm(e.label), v = norm(e.value);
    if (startsWith(l, nq)) return LabelStart;
    if (wordPrefix(l, nq)) return LabelWord;
    const std::vector<std::string> qw = words(nq);
    if (qw.size() > 1) {
        const std::string lv = l + " " + v;
        bool all = true;
        for (const auto& w : qw) if (!wordPrefix(lv, w)) { all = false; break; }
        if (all) return AllWords;
    }
    const std::string sq = squash(nq);
    if (l.find(nq) != std::string::npos || (!sq.empty() && squash(l).find(sq) != std::string::npos)) return LabelSub;
    if (!v.empty() && (v.find(nq) != std::string::npos || (!sq.empty() && squash(v).find(sq) != std::string::npos))) return ValueMatch;
    for (const auto& p : syn) if (wordPrefix(l, p)) return Synonym;
    if (wordPrefix(norm(e.section), nq)) return SectionMatch;
    return NoMatch;
}

// Which entries to show, in order: best tier first, the panel's own order within a tier. An empty query keeps
// everything in order.
inline std::vector<size_t> filter(const std::vector<Entry>& list, const std::string& query)
{
    std::vector<size_t> out;
    const std::string nq = norm(query);
    if (nq.empty()) {
        for (size_t i = 0; i < list.size(); ++i) out.push_back(i);
        return out;
    }
    const std::vector<std::string> syn = synonymPhrases(nq);
    std::vector<std::pair<int, size_t>> hits;
    for (size_t i = 0; i < list.size(); ++i) {
        const Tier t = tierOf(list[i], nq, syn);
        if (t != NoMatch) hits.push_back({ int(t), i });
    }
    std::stable_sort(hits.begin(), hits.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
    for (const auto& h : hits) out.push_back(h.second);
    return out;
}

// The rows the panel shows for `query`, steady while the user works in them. The panel rebuilds its rows on every
// draw and after every button, and a row's value changes when it is used ("On" -> "Off"), which can change whether
// and where it matches. `shown` holds the ids shown so far for this query (the shell clears it when the query
// changes): those come first, in that order, whether they still match or not (the row under the highlight stays
// under it); rows that newly match are appended and remembered. Ids not in the list any more are skipped.
inline std::vector<size_t> view(const std::vector<Entry>& list, const std::string& query, std::vector<int>& shown)
{
    const std::vector<size_t> fresh = filter(list, query);
    if (norm(query).empty()) { shown.clear(); return fresh; }
    std::vector<size_t> out;
    std::vector<bool> used(list.size(), false);
    for (int id : shown)
        for (size_t i = 0; i < list.size(); ++i)
            if (!used[i] && list[i].id == id) { used[i] = true; out.push_back(i); break; }
    for (size_t i : fresh)
        if (!used[i]) { used[i] = true; out.push_back(i); shown.push_back(list[i].id); }
    return out;
}

inline std::string countText(size_t shown, size_t total, const std::string& query)
{
    if (shown == 0) return "No settings match \"" + query + "\"";
    return std::to_string(shown) + " of " + std::to_string(total) + (total == 1 ? " setting" : " settings")
        + " match \"" + query + "\"";
}

} // namespace OmniSettingsSearch
