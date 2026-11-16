// OMNI_NOTES_V1: the pure part of Notes (no SDL, no WebKit): the store (/data/omni/notes.txt) parse / serialize with
// escaping and caps, note text clean-up, the line editing model (a note is edited line by line: the on-screen keyboard's
// dialog field is single-line), titles, dates, the private-session ask gate and the texts. Shell side: OmniNotesShell.h
// (written by tools/apply_notes.py; reasons there). Tested on the host with g++ (tools/test_notes.cpp).
#pragma once
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <string>
#include <utility>
#include <vector>

namespace OmniNotes {

static const char* const kFileName = "notes.txt";   // in /data/omni (omniData)
static const char* const kHeader = "omni-notes";    // first line: "omni-notes <version>"
constexpr int kVersion = 1;
constexpr size_t kMaxNotes = 200;          // a new note is refused when full; a larger file keeps the newest 200
constexpr size_t kMaxBytes = 4096;         // one note's text (UTF-8 bytes, cut at a character boundary)
constexpr long kMaxFileBytes = 4L << 20;   // read cap of the file (200 x 4 KB escaped is at most ~1.7 MB)
constexpr size_t kTitleBytes = 80;
constexpr int kTileList = 427;             // Options > Browse "Notes" (reading list 420 / 421, highlights 425)
constexpr int kActionId = 21;              // "Selected text" panel row (text select 1..4, highlights 20)
constexpr int kContextId = 8621;           // page menu row "Add page to notes"

struct Note {
    long long id = 0, created = 0, modified = 0;   // seconds since 1970
    std::string text;                              // lines joined by '\n'; tabs kept
};

// --- UTF-8 ------------------------------------------------------------------------------------------------------------
// The length of the valid UTF-8 sequence at s[i] (0: invalid: bad lead, truncated, overlong, surrogate, > U+10FFFF).
inline size_t decode(const std::string& s, size_t i, uint32_t& cp)
{
    const unsigned char c = static_cast<unsigned char>(s[i]);
    if (c < 0x80) { cp = c; return 1; }
    size_t n;
    uint32_t min;
    if ((c & 0xE0) == 0xC0) { n = 2; cp = c & 0x1F; min = 0x80; }
    else if ((c & 0xF0) == 0xE0) { n = 3; cp = c & 0x0F; min = 0x800; }
    else if ((c & 0xF8) == 0xF0) { n = 4; cp = c & 0x07; min = 0x10000; }
    else return 0;
    if (i + n > s.size()) return 0;
    for (size_t k = 1; k < n; ++k) {
        const unsigned char d = static_cast<unsigned char>(s[i + k]);
        if ((d & 0xC0) != 0x80) return 0;
        cp = (cp << 6) | (d & 0x3F);
    }
    if (cp < min || cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF)) return 0;
    return n;
}
// The longest prefix of at most max bytes that does not split a sequence.
inline std::string utf8Cut(const std::string& s, size_t max)
{
    if (s.size() <= max) return s;
    size_t n = max;
    while (n > 0 && (static_cast<unsigned char>(s[n]) & 0xC0) == 0x80) --n;
    return s.substr(0, n);
}

// Note text as stored: valid UTF-8 (an invalid byte becomes U+FFFD), CR LF / CR -> LF, U+2028 / U+2029 -> LF, other
// control characters (C0 except tab and LF, DEL) dropped, trailing spaces / tabs / empty lines removed, at most
// kMaxBytes (cut: set when something was cut for size). An empty result is not a note.
inline std::string clean(const std::string& in, bool* cut = nullptr)
{
    std::string o;
    o.reserve(in.size());
    for (size_t i = 0; i < in.size();) {
        uint32_t cp;
        const size_t n = decode(in, i, cp);
        if (!n) { o += "\xef\xbf\xbd"; ++i; continue; }
        if (cp == '\r') { o += '\n'; i += (i + 1 < in.size() && in[i + 1] == '\n') ? 2 : 1; continue; }
        if (cp == 0x2028 || cp == 0x2029) { o += '\n'; i += n; continue; }
        if ((cp < 0x20 && cp != '\n' && cp != '\t') || cp == 0x7F) { i += n; continue; }
        o.append(in, i, n);
        i += n;
    }
    size_t e = o.size();
    while (e > 0 && (o[e - 1] == ' ' || o[e - 1] == '\t' || o[e - 1] == '\n')) --e;
    o.resize(e);
    const bool over = o.size() > kMaxBytes;
    if (over) {
        o = utf8Cut(o, kMaxBytes);
        size_t f = o.size();
        while (f > 0 && (o[f - 1] == ' ' || o[f - 1] == '\t' || o[f - 1] == '\n')) --f;
        o.resize(f);
    }
    if (cut) *cut = over;
    return o;
}

// --- the file format --------------------------------------------------------------------------------------------------
// "omni-notes 1\n", then one note per line: id TAB created TAB modified TAB text, the text escaped so it has no tab or
// line break: '\' -> "\\", LF -> "\n", TAB -> "\t", CR -> "\r". Readers ignore fields after the fourth (a later version
// may add some) and unknown lines; a file without the header line is read the same way.
inline std::string escape(const std::string& s)
{
    std::string o;
    o.reserve(s.size() + 16);
    for (char c : s) {
        switch (c) {
        case '\\': o += "\\\\"; break;
        case '\n': o += "\\n"; break;
        case '\t': o += "\\t"; break;
        case '\r': o += "\\r"; break;
        default: o += c;
        }
    }
    return o;
}
// Unknown escapes keep the character after the backslash; a backslash at the end is dropped.
inline std::string unescape(const std::string& s)
{
    std::string o;
    o.reserve(s.size());
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] != '\\') { o += s[i]; continue; }
        if (++i >= s.size()) break;
        switch (s[i]) {
        case 'n': o += '\n'; break;
        case 't': o += '\t'; break;
        case 'r': o += '\r'; break;
        default: o += s[i];
        }
    }
    return o;
}
// A whole decimal number 0 .. 9e15 (no sign, no spaces); false otherwise.
inline bool number(const std::string& s, long long& v)
{
    if (s.empty() || s.size() > 16) return false;
    v = 0;
    for (char c : s) {
        if (c < '0' || c > '9') return false;
        v = v * 10 + (c - '0');
    }
    return v <= 9000000000000000LL;
}
inline bool newer(const Note& a, const Note& b) { return a.modified != b.modified ? a.modified > b.modified : a.id > b.id; }
inline std::vector<Note> parse(const std::string& text)
{
    std::vector<Note> out;
    if (text.size() > size_t(kMaxFileBytes)) return out;
    for (size_t p = 0; p < text.size();) {
        size_t e = text.find('\n', p);
        if (e == std::string::npos) e = text.size();
        std::string line = text.substr(p, e - p);
        p = e + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        std::vector<std::string> f;
        for (size_t q = 0;;) {
            const size_t t = line.find('\t', q);
            f.push_back(line.substr(q, t == std::string::npos ? std::string::npos : t - q));
            if (t == std::string::npos) break;
            q = t + 1;
        }
        if (f.size() < 4) continue;                 // the header, blank or unknown lines
        Note n;
        if (!number(f[0], n.id) || n.id < 1) continue;
        if (!number(f[1], n.created)) n.created = 0;
        if (!number(f[2], n.modified)) n.modified = n.created;
        n.text = clean(unescape(f[3]));
        if (n.text.empty()) continue;
        bool dup = false;
        for (const Note& o : out) if (o.id == n.id) { dup = true; break; }
        if (!dup) out.push_back(std::move(n));
    }
    if (out.size() > kMaxNotes) {
        std::stable_sort(out.begin(), out.end(), newer);
        out.resize(kMaxNotes);
    }
    return out;
}
inline std::string serialize(const std::vector<Note>& notes)
{
    std::string o = std::string(kHeader) + " " + std::to_string(kVersion) + "\n";
    for (const Note& n : notes)
        o += std::to_string(n.id) + "\t" + std::to_string(n.created) + "\t" + std::to_string(n.modified) + "\t"
            + escape(n.text) + "\n";
    return o;
}

// --- the list ---------------------------------------------------------------------------------------------------------
inline long long nextId(const std::vector<Note>& notes)
{
    long long m = 0;
    for (const Note& n : notes) m = std::max(m, n.id);
    return m + 1;
}
inline Note* find(std::vector<Note>& notes, long long id)
{
    for (Note& n : notes) if (n.id == id) return &n;
    return nullptr;
}
enum class Add { Ok, Full, Empty };
// A new note (id: nextId). cut: the text was longer than kMaxBytes.
inline Add add(std::vector<Note>& notes, const std::string& text, long long now, long long* id = nullptr, bool* cut = nullptr)
{
    if (notes.size() >= kMaxNotes) return Add::Full;
    Note n;
    n.text = clean(text, cut);
    if (n.text.empty()) return Add::Empty;
    n.id = nextId(notes);
    n.created = n.modified = now < 0 ? 0 : now;
    if (id) *id = n.id;
    notes.push_back(std::move(n));
    return Add::Ok;
}
inline bool remove(std::vector<Note>& notes, long long id)
{
    const size_t before = notes.size();
    notes.erase(std::remove_if(notes.begin(), notes.end(), [&](const Note& n) { return n.id == id; }), notes.end());
    return notes.size() != before;
}
// Indexes newest (last changed) first.
inline std::vector<size_t> order(const std::vector<Note>& notes)
{
    std::vector<size_t> v(notes.size());
    for (size_t i = 0; i < v.size(); ++i) v[i] = i;
    std::stable_sort(v.begin(), v.end(), [&](size_t a, size_t b) { return newer(notes[a], notes[b]); });
    return v;
}

// --- lines (the editor) -----------------------------------------------------------------------------------------------
inline std::vector<std::string> lines(const std::string& text)
{
    std::vector<std::string> v;
    if (text.empty()) return v;
    for (size_t p = 0;;) {
        const size_t e = text.find('\n', p);
        v.push_back(text.substr(p, e == std::string::npos ? std::string::npos : e - p));
        if (e == std::string::npos) break;
        p = e + 1;
    }
    return v;
}
inline std::string join(const std::vector<std::string>& v)
{
    std::string o;
    for (size_t i = 0; i < v.size(); ++i) { if (i) o += '\n'; o += v[i]; }
    return o;
}
// Line `index` replaced by `line` (which may hold line breaks: a pasted text becomes several lines); index == the line
// count appends. The result is cleaned (cut at kMaxBytes). False: index out of range.
inline bool setLine(std::string& text, size_t index, const std::string& line, bool* cut = nullptr)
{
    std::vector<std::string> v = lines(text);
    if (index > v.size()) return false;
    if (index == v.size()) v.push_back(line); else v[index] = line;
    text = clean(join(v), cut);
    return true;
}
inline bool removeLine(std::string& text, size_t index)
{
    std::vector<std::string> v = lines(text);
    if (index >= v.size()) return false;
    v.erase(v.begin() + long(index));
    text = clean(join(v));
    return true;
}
// One line for a panel row: tabs as spaces, at most max bytes ("..." when cut).
inline std::string preview(const std::string& s, size_t max)
{
    std::string c;
    bool space = false;
    for (char ch : s) {
        if (ch == ' ' || ch == '\t' || ch == '\n') { space = !c.empty(); continue; }
        if (space) { c += ' '; space = false; }
        c += ch;
    }
    if (c.size() <= max) return c;
    return utf8Cut(c, max > 3 ? max - 3 : 0) + "...";
}
// The first line with something on it.
inline std::string title(const std::string& text)
{
    for (const std::string& l : lines(text)) {
        const std::string t = preview(l, kTitleBytes);
        if (!t.empty()) return t;
    }
    return "(empty note)";
}
inline std::string lineDetail(const std::string& text)
{
    const size_t n = lines(text).size();
    return n == 1 ? std::string("1 line") : std::to_string(n) + " lines";
}
// "Add page to notes": the page title on the first line, the address on the second (no title: the address only).
inline std::string pageNote(const std::string& pageTitle, const std::string& url)
{
    const std::string t = preview(pageTitle, 300);
    const std::string u = preview(url, 2048);
    if (t.empty() || t == u) return u;
    return t + "\n" + u;
}

// "Today", "Yesterday", else "12 Nov 2026" (local time).
inline std::string dateText(long long at, long long now)
{
    const time_t a = time_t(at), n = time_t(now), y = time_t(now - 86400);
    struct tm ta {}, tn {}, ty {};
    localtime_r(&a, &ta);
    localtime_r(&n, &tn);
    localtime_r(&y, &ty);
    if (ta.tm_year == tn.tm_year && ta.tm_yday == tn.tm_yday) return "Today";
    if (ta.tm_year == ty.tm_year && ta.tm_yday == ty.tm_yday) return "Yesterday";
    static const char* const mon[] = { "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec" };
    char b[40];
    snprintf(b, sizeof b, "%d %s %d", ta.tm_mday, mon[(ta.tm_mon % 12 + 12) % 12], ta.tm_year + 1900);
    return b;
}

// --- private tabs -----------------------------------------------------------------------------------------------------
// Adding from a private tab asks once per private session (it ends when the last private tab closes). Guest mode
// never asks: its notes are memory only.
struct PrivateGate {
    bool asked = false;                       // "Save" was chosen in this private session
    bool needAsk(bool privateTab, bool guest) const { return privateTab && !guest && !asked; }
    void accept() { asked = true; }
    void tick(bool anyPrivateTab) { if (!anyPrivateTab) asked = false; }
};

// --- texts ------------------------------------------------------------------------------------------------------------
inline std::string addedNotice(bool cut, bool guest)
{
    if (guest) return std::string("Added to notes") + (cut ? " (the first 4 KB)" : "") + ": guest notes are not saved";
    return std::string("Added to notes") + (cut ? " (the first 4 KB)" : "") + ": Options > Browse > Notes";
}
inline std::string fullNotice()
{
    return "Notes are full (" + std::to_string(kMaxNotes) + "): delete some in Options > Browse > Notes";
}
inline std::string cutNotice() { return "A note keeps at most 4 KB: the end was cut"; }
inline std::string emptyNotice() { return "Nothing to add to notes"; }
inline std::string privateAskTitle() { return "Save to notes?"; }
inline std::string privateAskBody() { return "Notes are kept after private browsing"; }
inline std::string deleteTitle() { return "Delete this note?"; }
inline std::string panelSubtitle(size_t n, bool guest)
{
    if (guest) return "Guest mode: notes are kept only until guest mode ends";
    if (!n) return "Jot a code, a list or a link. Select text > Add to notes also works";
    return std::to_string(n) + (n == 1 ? " note" : " notes") + " \xc2\xb7 Triangle copies one";
}
inline std::string editorSubtitle(const std::string& text)
{
    return lineDetail(text) + " \xc2\xb7 " + std::to_string(text.size()) + " / " + std::to_string(kMaxBytes) + " bytes";
}

} // namespace OmniNotes
