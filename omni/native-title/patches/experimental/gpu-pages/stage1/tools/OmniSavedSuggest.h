// OMNI_SAVED_SUGGEST_V1: the pure part of the bookmark / reading-list rows in the address suggestions (no SDL, no
// WebKit, no I/O): the typed-text rule (2+ characters), word-prefix matching on title or address (ASCII
// case-insensitive), ranking (bookmarks before reading-list pages, at most 2 rows), the cache key and the row
// budget (5 rows; the "Search <host> for" row, the first history / shortcut row and the tab / answer rows are never
// pushed out). The shell side is OmniSavedSuggestShell.h; the reasons are in tools/apply_saved_suggest.py.
// Tested on the host with g++ (tools/test_saved_suggest.cpp).
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace OmniSavedSuggest {

enum Kind { kNone = 0, kBookmark = 1, kReading = 2 };
constexpr size_t kMaxSaved = 2, kMaxRows = 5, kMinChars = 2;
constexpr size_t kMaxWords = 6;   // query words looked at (the rest are ignored)

inline char low(char c) { return c >= 'A' && c <= 'Z' ? char(c - 'A' + 'a') : c; }
inline std::string lower(std::string s) { for (auto& c : s) c = low(c); return s; }
inline bool isWs(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }
// A word character: ASCII letter / digit, or any byte of a non-ASCII (UTF-8) character.
inline bool wordChar(char c)
{
    const unsigned char u = static_cast<unsigned char>(c);
    return (u >= 'a' && u <= 'z') || (u >= 'A' && u <= 'Z') || (u >= '0' && u <= '9') || u >= 0x80;
}
inline size_t codePoints(const std::string& s)
{
    size_t n = 0;
    for (char c : s) if ((static_cast<unsigned char>(c) & 0xc0) != 0x80) ++n;
    return n;
}
inline std::string stripScheme(std::string s)   // s is lowercase
{
    for (const char* p : { "https://", "http://" }) {
        const std::string pre(p);
        if (s.compare(0, pre.size(), pre) == 0) { s.erase(0, pre.size()); break; }
    }
    if (s.compare(0, 4, "www.") == 0) s.erase(0, 4);
    return s;
}
// The address as matched and compared: lowercase, no http(s)://, no "www.", no trailing slashes.
inline std::string bare(const std::string& url)
{
    std::string s = stripScheme(lower(url));
    while (!s.empty() && s.back() == '/') s.pop_back();
    return s;
}
// The typed text as matched: trimmed, lowercase, no scheme / "www."; "" when shorter than kMinChars characters.
inline std::string query(const std::string& typed)
{
    size_t a = 0, b = typed.size();
    while (a < b && isWs(typed[a])) ++a;
    while (b > a && isWs(typed[b - 1])) --b;
    std::string q = stripScheme(lower(typed.substr(a, b - a)));
    size_t c = q.find_first_not_of(' ');
    q.erase(0, c == std::string::npos ? q.size() : c);
    return codePoints(q) >= kMinChars ? q : std::string();
}
inline std::vector<std::string> words(const std::string& q)
{
    std::vector<std::string> out;
    size_t i = 0;
    while (i < q.size() && out.size() < kMaxWords) {
        while (i < q.size() && isWs(q[i])) ++i;
        size_t j = i;
        while (j < q.size() && !isWs(q[j])) ++j;
        if (j > i) out.push_back(q.substr(i, j - i));
        i = j;
    }
    return out;
}

// One saved page, prepared once per cache refresh (never per keystroke).
struct Entry {
    std::string url, title, id;   // id: the reading-list entry (its file name); "" for a bookmark
    int kind = kNone;
    std::string lowTitle, lowUrl; // lowercase title, bare() address
};
inline Entry prepare(int kind, const std::string& url, const std::string& title, const std::string& id = std::string())
{
    Entry e;
    e.url = url; e.title = title; e.id = id; e.kind = kind;
    e.lowTitle = lower(title);
    e.lowUrl = bare(url);
    return e;
}
// Never offered: empty addresses and script / data addresses (bookmarklets).
inline bool offerable(const Entry& e)
{
    if (e.url.empty()) return false;
    const std::string l = lower(e.url.substr(0, 11));
    return l.compare(0, 11, "javascript:") != 0 && l.compare(0, 5, "data:") != 0;
}

// Where `w` starts a word of `hay` (position 0 or after a non-word character): its position, npos when nowhere.
inline size_t wordPrefixAt(const std::string& hay, const std::string& w)
{
    if (w.empty()) return std::string::npos;
    for (size_t p = hay.find(w); p != std::string::npos; p = hay.find(w, p + 1))
        if (p == 0 || !wordChar(hay[p - 1])) return p;
    return std::string::npos;
}
// -1: no match. 0: the first word starts the title or the address; 1: every word starts a word somewhere.
inline int score(const Entry& e, const std::vector<std::string>& ws)
{
    if (ws.empty()) return -1;
    for (const auto& w : ws)
        if (wordPrefixAt(e.lowTitle, w) == std::string::npos && wordPrefixAt(e.lowUrl, w) == std::string::npos) return -1;
    return wordPrefixAt(e.lowTitle, ws[0]) == 0 || e.lowUrl.compare(0, ws[0].size(), ws[0]) == 0 ? 0 : 1;
}

struct Hit { int kind = kNone; size_t index = 0; };   // index into the list of that kind
// The rows to show: bookmarks before reading-list pages, then the better match, then list order; at most `max`;
// one row per address (a bookmark wins over the same page in the reading list); addresses in `skip` (open-tab rows)
// are left out. `reading` empty: no reading-list rows (private tabs).
inline std::vector<Hit> rank(const std::vector<Entry>& bookmarks, const std::vector<Entry>& reading,
                             const std::string& typed, const std::vector<std::string>& skip, size_t max = kMaxSaved)
{
    std::vector<Hit> out;
    const std::string q = query(typed);
    if (q.empty() || max == 0) return out;
    const std::vector<std::string> ws = words(q);
    struct Scored { int kind, score; size_t index; };
    std::vector<Scored> found;
    for (int kind : { int(kBookmark), int(kReading) }) {
        const auto& list = kind == kBookmark ? bookmarks : reading;
        for (size_t i = 0; i < list.size(); ++i) {
            if (!offerable(list[i])) continue;
            const int s = score(list[i], ws);
            if (s >= 0) found.push_back({ kind, s, i });
        }
    }
    std::stable_sort(found.begin(), found.end(), [](const Scored& a, const Scored& b) {
        return a.kind != b.kind ? a.kind < b.kind : a.score < b.score;
    });
    std::vector<std::string> seen = skip;
    for (const auto& f : found) {
        const Entry& e = (f.kind == kBookmark ? bookmarks : reading)[f.index];
        if (std::find(seen.begin(), seen.end(), e.lowUrl) != seen.end()) continue;
        seen.push_back(e.lowUrl);
        out.push_back({ f.kind, f.index });
        if (out.size() >= max) break;
    }
    return out;
}

// Cache key: FNV-1a over the parts that say "the list changed" (file stamp, list size, entry ids).
struct Key {
    uint64_t h = 1469598103934665603ull;
    Key& add(const void* p, size_t n)
    {
        const unsigned char* b = static_cast<const unsigned char*>(p);
        for (size_t i = 0; i < n; ++i) { h ^= b[i]; h *= 1099511628211ull; }
        return *this;
    }
    Key& add(long long v) { return add(&v, sizeof v); }
    Key& add(const std::string& s) { add((long long)s.size()); return add(s.data(), s.size()); }
};
// The prepared list and the key it was built for: rebuild() only runs when the key differs.
struct Cache {
    std::vector<Entry> items;
    uint64_t key = 0;
    bool built = false;
    template <class Build> bool refresh(uint64_t k, Build build)
    {
        if (built && k == key) return false;
        items.clear();
        build(items);
        key = k;
        built = true;
        return true;
    }
};

// The row budget. Existing rows by role, in list order; the merged order comes back as indexes: >= 0 an existing
// row, < 0 saved row -(j + 1). Saved rows go right after the leading tab / answer rows (above history and the
// engine's suggestions). Over kMaxRows: the last engine row goes first, then the last other history row, then the
// last saved row; the site row, the URL row (the first history / shortcut row) and leading rows always stay.
enum Role { kLead = 0, kUrl = 1, kLocal = 2, kSite = 3, kEngine = 4 };
inline std::vector<int> place(const std::vector<Role>& rows, size_t saved, size_t maxRows = kMaxRows)
{
    std::vector<int> out;
    size_t at = 0;
    while (at < rows.size() && rows[at] == kLead) ++at;
    for (size_t i = 0; i < at; ++i) out.push_back(int(i));
    for (size_t j = 0; j < saved; ++j) out.push_back(-int(j) - 1);
    for (size_t i = at; i < rows.size(); ++i) out.push_back(int(i));
    auto roleOf = [&](int v) { return v < 0 ? -1 : int(rows[size_t(v)]); };
    while (out.size() > maxRows) {
        bool dropped = false;
        for (int want : { int(kEngine), int(kLocal), -1 }) {
            for (size_t k = out.size(); k-- > 0;) {
                if (roleOf(out[k]) != want) continue;
                out.erase(out.begin() + std::ptrdiff_t(k));
                dropped = true;
                break;
            }
            if (dropped) break;
        }
        if (!dropped) break;   // only rows that always stay are left (the list was already over the budget)
    }
    return out;
}

} // namespace OmniSavedSuggest
