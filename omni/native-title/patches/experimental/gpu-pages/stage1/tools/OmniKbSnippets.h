// OMNI_KB_SNIPPETS_V1: the pure part of keyboard snippets (no SDL, no WebKit): up to 10 saved phrases the on-screen
// keyboard inserts at the cursor (Edit tools > Snippets). Each phrase is one line of at most 200 characters (code
// points; cut at a UTF-8 boundary, never mid-sequence), stored in /data/omni/kb-snippets.txt as plain text:
//   "omni-kb-snippets<TAB>1" then one phrase per line.
// Readers skip the first line only when it is that header, then clean every line (valid UTF-8, line breaks / tabs /
// controls -> one space, trimmed, 200-character cap), drop empty lines and duplicates, and keep the first 10. Also the
// picker's state (selection, save / delete confirm) and its fixed texts. Shell side: OmniKbSnippetsShell.h; reasons in
// tools/apply_kb_snippets.py. Tested on the host with g++ (tools/test_kb_snippets.cpp).
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace OmniKbSnippets {

constexpr size_t kMaxItems = 10;          // phrases kept
constexpr size_t kMaxChars = 200;         // code points per phrase
constexpr size_t kLabelChars = 40;        // code points of a picker row's label
constexpr size_t kReadCap = 64 * 1024;    // bytes read from the file at most
constexpr int kKbKey = 7581;              // the keyboard's "Snippets" key (OmniKbKey::action)
constexpr const char* kFile = "kb-snippets.txt";
constexpr const char* kHeader = "omni-kb-snippets\t1";

// Length of the valid UTF-8 sequence at s[i] (1..4), or 0 when it is not one (overlong, surrogate, > U+10FFFF, cut).
inline size_t seqLen(std::string_view s, size_t i)
{
    const unsigned char c = static_cast<unsigned char>(s[i]);
    if (c < 0x80) return 1;
    size_t n = 0;
    uint32_t cp = 0;
    if ((c & 0xE0) == 0xC0) { n = 2; cp = c & 0x1F; }
    else if ((c & 0xF0) == 0xE0) { n = 3; cp = c & 0x0F; }
    else if ((c & 0xF8) == 0xF0) { n = 4; cp = c & 0x07; }
    else return 0;
    if (i + n > s.size()) return 0;
    for (size_t k = 1; k < n; ++k) {
        const unsigned char d = static_cast<unsigned char>(s[i + k]);
        if ((d & 0xC0) != 0x80) return 0;
        cp = (cp << 6) | (d & 0x3F);
    }
    if ((n == 2 && cp < 0x80) || (n == 3 && cp < 0x800) || (n == 4 && cp < 0x10000)) return 0;   // overlong
    if ((cp >= 0xD800 && cp <= 0xDFFF) || cp > 0x10FFFF) return 0;
    return n;
}

// Code points in valid UTF-8 (lead bytes).
inline size_t cpCount(std::string_view s)
{
    size_t n = 0;
    for (unsigned char c : s) if ((c & 0xC0) != 0x80) ++n;
    return n;
}

// The first `chars` code points of valid UTF-8 (never splits a sequence).
inline std::string cutChars(std::string_view s, size_t chars)
{
    size_t cps = 0, i = 0;
    for (; i < s.size(); ++i) {
        if ((static_cast<unsigned char>(s[i]) & 0xC0) != 0x80) {
            if (cps == chars) break;
            ++cps;
        }
    }
    return std::string(s.substr(0, i));
}

// One storable phrase: invalid UTF-8 bytes dropped; line breaks, tabs, other controls (C0, DEL, C1) and U+2028 /
// U+2029 become a space, runs of spaces one space, trimmed, then at most kMaxChars code points (trimmed again).
// *cut: the text was longer than kMaxChars.
inline std::string clean(std::string_view s, bool* cut = nullptr)
{
    std::string line;
    bool space = false;
    for (size_t i = 0; i < s.size();) {
        const size_t n = seqLen(s, i);
        if (!n) { ++i; continue; }
        const unsigned char c = static_cast<unsigned char>(s[i]);
        const unsigned char c1 = n > 1 ? static_cast<unsigned char>(s[i + 1]) : 0;
        const unsigned char c2 = n > 2 ? static_cast<unsigned char>(s[i + 2]) : 0;
        const bool blank = c <= 0x20 || c == 0x7F || (n == 2 && c == 0xC2 && c1 < 0xA0)
            || (n == 3 && c == 0xE2 && c1 == 0x80 && (c2 == 0xA8 || c2 == 0xA9));
        if (blank) space = !line.empty();
        else {
            if (space) { line += ' '; space = false; }
            line.append(s.substr(i, n));
        }
        i += n;
    }
    const bool longer = cpCount(line) > kMaxChars;
    if (longer) {
        line = cutChars(line, kMaxChars);
        while (!line.empty() && line.back() == ' ') line.pop_back();
    }
    if (cut) *cut = longer;
    return line;
}

// A picker row's label: at most `chars` code points, "..." at the end when longer (within the limit).
inline std::string label(std::string_view s, size_t chars = kLabelChars)
{
    if (cpCount(s) <= chars) return std::string(s);
    std::string out = cutChars(s, chars > 3 ? chars - 3 : 0);
    while (!out.empty() && out.back() == ' ') out.pop_back();
    return out + "...";
}

enum Add { kAdded = 0, kEmpty, kDuplicate, kFull };

class List {
public:
    size_t size() const { return items_.size(); }
    bool empty() const { return items_.empty(); }
    bool full() const { return items_.size() >= kMaxItems; }
    const std::string& at(size_t i) const { return items_[i]; }
    const std::vector<std::string>& items() const { return items_; }

    // Saves a phrase at the end (cleaned first). *cut: it was longer than 200 characters.
    Add add(std::string_view raw, bool* cut = nullptr)
    {
        const std::string t = clean(raw, cut);
        if (t.empty()) return kEmpty;
        for (const auto& it : items_) if (it == t) return kDuplicate;
        if (full()) return kFull;
        items_.push_back(t);
        return kAdded;
    }
    bool remove(size_t i)
    {
        if (i >= items_.size()) return false;
        items_.erase(items_.begin() + std::ptrdiff_t(i));
        return true;
    }
    std::string serialize() const
    {
        std::string out = std::string(kHeader) + "\n";
        for (const auto& it : items_) out += it + "\n";
        return out;
    }
    static List parse(std::string_view file)
    {
        List l;
        if (file.size() > kReadCap) file = file.substr(0, kReadCap);
        size_t pos = 0;
        bool first = true;
        while (pos < file.size() && !l.full()) {
            size_t end = file.find('\n', pos);
            if (end == std::string_view::npos) end = file.size();
            std::string_view line = file.substr(pos, end - pos);
            pos = end + 1;
            if (!line.empty() && line.back() == '\r') line.remove_suffix(1);
            if (first) {
                first = false;
                if (line.substr(0, 16) == "omni-kb-snippets") continue;   // the header (any version)
            }
            l.add(line);   // empty / duplicate lines are skipped by add()
        }
        return l;
    }

private:
    std::vector<std::string> items_;
};

// --- the picker ---------------------------------------------------------------------------------------------------
// Rows: the n phrases, then one "save" row (index n). Buttons in the order the shell maps them.
enum Btn { bUp = 0, bDown, bCross, bSquare, bCircle, bOther };
enum Act { aNone = 0, aMove, aInsert, aAskSave, aSave, aFullNotice, aAskDelete, aDelete, aCancel, aClose };
enum Confirm { cNone = 0, cSave, cDelete };

struct Picker {
    int sel = 0;
    int confirm = cNone;

    // n: phrases listed (the save row is index n). The caller acts on the result; aAskSave asks the caller to check
    // the text and call askSave() when there is something to save.
    Act press(Btn b, size_t n)
    {
        const int rows = int(n) + 1;
        if (sel < 0 || sel >= rows) sel = 0;
        if (confirm == cSave) {
            if (b == bCross) { confirm = cNone; return aSave; }
            if (b == bCircle || b == bSquare) { confirm = cNone; return aCancel; }
            if (b == bUp || b == bDown) { confirm = cNone; return move(b, rows); }
            return aNone;
        }
        if (confirm == cDelete) {
            if (b == bSquare || b == bCross) { confirm = cNone; return size_t(sel) < n ? aDelete : aNone; }
            if (b == bCircle) { confirm = cNone; return aCancel; }
            if (b == bUp || b == bDown) { confirm = cNone; return move(b, rows); }
            return aNone;
        }
        switch (b) {
        case bUp: case bDown: return move(b, rows);
        case bCross:
            if (size_t(sel) < n) return aInsert;
            return n >= kMaxItems ? aFullNotice : aAskSave;
        case bSquare:
            if (size_t(sel) >= n) return aNone;
            confirm = cDelete;
            return aAskDelete;
        case bCircle: return aClose;
        default: return aNone;
        }
    }
    void askSave() { confirm = cSave; }
    // After a delete: the selection stays on the row that took its place (or the last row).
    void afterDelete(size_t n) { if (size_t(sel) > n) sel = int(n); }
    // A row clicked with the pointer.
    Act click(int row, size_t n)
    {
        confirm = cNone;
        if (row < 0 || row > int(n)) return aClose;
        sel = row;
        if (size_t(row) < n) return aInsert;
        return n >= kMaxItems ? aFullNotice : aAskSave;
    }

private:
    Act move(Btn b, int rows)
    {
        sel = b == bUp ? (sel + rows - 1) % rows : (sel + 1) % rows;
        return aMove;
    }
};

// --- fixed texts (never the phrase itself in a notice) --------------------------------------------------------------
inline const char* saveRowLabel(size_t n) { return n >= kMaxItems ? "10 snippets saved: delete one to save more" : "+ Save current text as snippet"; }
inline const char* subtitle(int confirm, bool priv)
{
    if (confirm == cSave)
        return priv ? "Private tab: the snippet stays on this console after the tab closes. Save it?" : "Save this text as a snippet?";
    if (confirm == cDelete) return "Delete this snippet? Square again deletes it";
    return "Saved on this console as plain text: never save passwords";
}
inline const char* addedNotice(Add r, bool cut)
{
    switch (r) {
    case kAdded: return cut ? "Snippet saved (the first 200 characters)" : "Snippet saved";
    case kEmpty: return "Nothing to save: type the text first";
    case kDuplicate: return "That snippet is already saved";
    default: return "10 snippets saved: delete one to save more";
    }
}
inline const char* emptyNotice() { return "Nothing to save: type the text first"; }

}   // namespace OmniKbSnippets
