// OMNI_CLIP_HISTORY_V1: the pure part of the clipboard history (no SDL, no WebKit): the last 10 things copied to
// Omni's own clipboard (omniKbClipboard), newest first, in memory only (never written anywhere, gone when Omni exits).
// Ring buffer of 10, the same text copied again moves to the front, items at most 4 KB (cut at a UTF-8 boundary),
// one-line labels of at most 40 characters. Private rule: an item copied in a private tab is listed only while the
// active tab is private, and every such item is dropped when the last private tab closes (purgePrivate); then the
// current clipboard is cleared too if it came from a private tab. Shell side: OmniClipHistoryShell.h; reasons in
// tools/apply_clip_history.py. Tested on the host with g++ (tools/test_clip_history.cpp).
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace OmniClipHistory {

constexpr size_t kMaxItems = 10;     // items kept
constexpr size_t kItemMax = 4096;    // bytes per item (the cap Select text's Copy uses)
constexpr size_t kLabelChars = 40;   // characters (code points) of a row's label
constexpr int kPanelKind = 7560;     // OmniFxPanel::kind of the quick menu's Clipboard panel
constexpr int kKbKey = 7561;         // the keyboard's "Clips" key (OmniKbKey::action)
constexpr int kQuickRowId = 8495;    // the quick menu's "Clipboard (n)" row
constexpr int kClearRowId = -2;      // the panel's "Clear clipboard history" row (item rows: Item::id >= 1)

// The longest prefix of s of at most max bytes that does not split a UTF-8 sequence.
inline std::string utf8Cut(const std::string& s, size_t max)
{
    if (s.size() <= max) return s;
    size_t n = max;
    while (n > 0 && (static_cast<unsigned char>(s[n]) & 0xC0) == 0x80) --n;
    return s.substr(0, n);
}
// What an item holds: the text, at most kItemMax bytes.
inline std::string clip(const std::string& s) { return utf8Cut(s, kItemMax); }

// A row's label: one line (controls, spaces, U+0085 / U+00A0 / U+2028 / U+2029 runs become one space, trimmed), at most
// `chars` code points; longer text ends in "..." (within the limit). Never splits a UTF-8 sequence.
inline std::string label(const std::string& s, size_t chars = kLabelChars)
{
    std::string line;
    bool space = false;
    for (size_t i = 0; i < s.size(); ++i) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        const unsigned char c1 = i + 1 < s.size() ? static_cast<unsigned char>(s[i + 1]) : 0;
        const unsigned char c2 = i + 2 < s.size() ? static_cast<unsigned char>(s[i + 2]) : 0;
        size_t skip = 0;
        if (c <= 0x20 || c == 0x7F) skip = 1;
        else if (c == 0xC2 && (c1 == 0x85 || c1 == 0xA0)) skip = 2;
        else if (c == 0xE2 && c1 == 0x80 && (c2 == 0xA8 || c2 == 0xA9)) skip = 3;
        if (skip) { space = !line.empty(); i += skip - 1; continue; }
        if (space) { line += ' '; space = false; }
        line += char(c);
    }
    // code points: count lead bytes; find the byte offset after `chars` of them
    auto offsetAfter = [&](size_t n) {
        size_t cps = 0, i = 0;
        for (; i < line.size(); ++i) {
            if ((static_cast<unsigned char>(line[i]) & 0xC0) != 0x80) {
                if (cps == n) return i;
                ++cps;
            }
        }
        return line.size();
    };
    const size_t all = offsetAfter(chars);
    if (all >= line.size()) return line;
    const size_t keep = chars > 3 ? chars - 3 : 0;
    std::string out = line.substr(0, offsetAfter(keep));
    while (!out.empty() && out.back() == ' ') out.pop_back();
    return out + "...";
}

struct Item {
    std::string text;      // at most kItemMax bytes
    bool priv = false;     // copied in a private tab (listed only in private tabs; dropped with the last one)
    uint32_t id = 0;       // stable while it is kept (>= 1)
};

// Newest first. A fixed ring of kMaxItems slots: adding to a full ring drops the oldest.
class History {
public:
    size_t size() const { return n_; }
    bool empty() const { return n_ == 0; }
    const Item& at(size_t i) const { return slots_[(head_ + i) % kMaxItems]; }   // 0: newest
    bool currentPrivate() const { return currentPriv_; }

    // Something was copied (text: what omniKbClipboard now holds; privateTab: the tab it was copied in).
    // Empty text is ignored. The same text again moves to the front; it stays private only if both copies were.
    void add(const std::string& text, bool privateTab)
    {
        Item it;
        it.text = clip(text);
        if (it.text.empty()) return;
        it.priv = privateTab;
        const int old = find(it.text);
        if (old >= 0) { it.priv = at(size_t(old)).priv && privateTab; eraseAt(size_t(old)); }
        it.id = nextId_++;
        if (!nextId_) nextId_ = 1;
        pushFront(std::move(it));
        currentPriv_ = privateTab;
    }
    // A listed item was picked (it becomes the clipboard): it moves to the front keeping its own private flag.
    // Returns false when it is gone.
    bool touch(uint32_t id, std::string* text = nullptr)
    {
        const int i = indexOf(id);
        if (i < 0) return false;
        Item it = at(size_t(i));
        eraseAt(size_t(i));
        currentPriv_ = it.priv;
        if (text) *text = it.text;
        pushFront(std::move(it));
        return true;
    }
    // Square on a row. Returns false when it is gone; *text gets the removed text.
    bool remove(uint32_t id, std::string* text = nullptr)
    {
        const int i = indexOf(id);
        if (i < 0) return false;
        if (text) *text = at(size_t(i)).text;
        eraseAt(size_t(i));
        return true;
    }
    // The items a tab may list, newest first: private items only while the active tab is private.
    std::vector<Item> visible(bool privateTab) const
    {
        std::vector<Item> v;
        for (size_t i = 0; i < n_; ++i) if (!at(i).priv || privateTab) v.push_back(at(i));
        return v;
    }
    size_t count(bool privateTab) const
    {
        size_t c = 0;
        for (size_t i = 0; i < n_; ++i) if (!at(i).priv || privateTab) ++c;
        return c;
    }
    bool hasPrivate() const
    {
        for (size_t i = 0; i < n_; ++i) if (at(i).priv) return true;
        return currentPriv_;
    }
    // The last private tab closed: every private item goes. true: the current clipboard came from a private tab
    // (the shell clears it).
    bool purgePrivate()
    {
        for (size_t i = n_; i-- > 0;) if (at(i).priv) eraseAt(i);
        const bool clearCurrent = currentPriv_;
        currentPriv_ = false;
        return clearCurrent;
    }
    // "Clear clipboard history": everything (the shell clears the clipboard as well).
    void clear()
    {
        for (auto& s : slots_) s = Item();
        head_ = n_ = 0;
        currentPriv_ = false;
    }

private:
    int find(const std::string& text) const
    {
        for (size_t i = 0; i < n_; ++i) if (at(i).text == text) return int(i);
        return -1;
    }
    int indexOf(uint32_t id) const
    {
        for (size_t i = 0; i < n_; ++i) if (at(i).id == id) return int(i);
        return -1;
    }
    Item& slot(size_t i) { return slots_[(head_ + i) % kMaxItems]; }
    void pushFront(Item it)
    {
        if (n_ == kMaxItems) { slot(n_ - 1) = Item(); --n_; }   // the oldest goes
        head_ = (head_ + kMaxItems - 1) % kMaxItems;
        slot(0) = std::move(it);
        ++n_;
    }
    void eraseAt(size_t i)
    {
        for (size_t k = i; k + 1 < n_; ++k) slot(k) = std::move(slot(k + 1));
        slot(n_ - 1) = Item();   // no copy of the text stays in the free slot
        --n_;
    }
    std::array<Item, kMaxItems> slots_ {};
    size_t head_ = 0, n_ = 0;
    uint32_t nextId_ = 1;
    bool currentPriv_ = false;
};

// Is `clipboard` (omniKbClipboard, up to 8 KB) the text of this item (its first 4 KB)?
inline bool isCurrent(const std::string& clipboard, const Item& it) { return !clipboard.empty() && clip(clipboard) == it.text; }

inline std::string quickLabel(size_t n) { return "Clipboard (" + std::to_string(n) + ")"; }
inline std::string rowValue(bool current, bool priv)
{
    if (current && priv) return "In clipboard, private";
    if (current) return "In clipboard";
    return priv ? "Private" : "";
}

} // namespace OmniClipHistory
