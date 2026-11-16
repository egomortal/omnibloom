// OMNI_CLIP_HISTORY_V1: host tests of the pure clipboard history (OmniClipHistory.h).
//   g++ -std=c++20 -Wall -Wextra -Werror -I. test_clip_history.cpp -o t && ./t      (run in tools/, or -I<tree>/engine/entry)
#include "OmniClipHistory.h"
#include <cstdio>
#include <string>

namespace C = OmniClipHistory;
static int fails = 0, checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); } } while (0)

static bool validUtf8(const std::string& s)
{
    for (size_t i = 0; i < s.size();) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        size_t n = c < 0x80 ? 1 : (c >> 5) == 6 ? 2 : (c >> 4) == 14 ? 3 : (c >> 3) == 30 ? 4 : 0;
        if (!n || i + n > s.size()) return false;
        for (size_t k = 1; k < n; ++k) if ((static_cast<unsigned char>(s[i + k]) & 0xC0) != 0x80) return false;
        i += n;
    }
    return true;
}
static size_t cps(const std::string& s) { size_t n = 0; for (unsigned char c : s) if ((c & 0xC0) != 0x80) ++n; return n; }

int main()
{
    // --- ring buffer, order, cap of 10 ---
    {
        C::History h;
        CHECK(h.empty());
        for (int i = 0; i < 12; ++i) h.add("item " + std::to_string(i), false);
        CHECK(h.size() == 10);
        CHECK(h.at(0).text == "item 11");
        CHECK(h.at(9).text == "item 2");      // 0 and 1 dropped
        for (size_t i = 0; i + 1 < h.size(); ++i) CHECK(h.at(i).id > h.at(i + 1).id);
        h.add("", false);                      // ignored
        CHECK(h.size() == 10 && h.at(0).text == "item 11");
        // 30 more: the ring wraps several times, still newest first
        for (int i = 12; i < 42; ++i) h.add("item " + std::to_string(i), false);
        CHECK(h.size() == 10 && h.at(0).text == "item 41" && h.at(9).text == "item 32");
    }
    // --- dedupe: the same text moves to the front, no duplicate ---
    {
        C::History h;
        h.add("a", false); h.add("b", false); h.add("c", false);
        h.add("a", false);
        CHECK(h.size() == 3);
        CHECK(h.at(0).text == "a" && h.at(1).text == "c" && h.at(2).text == "b");
        // a full ring: re-adding the oldest does not drop anything
        C::History f;
        for (int i = 0; i < 10; ++i) f.add(std::to_string(i), false);
        f.add("0", false);
        CHECK(f.size() == 10 && f.at(0).text == "0" && f.at(9).text == "1");
    }
    // --- 4 KB cap at a UTF-8 boundary; dedupe compares the capped text ---
    {
        std::string big(4095, 'x');
        big += "\xc3\xa9\xc3\xa9";               // e-acute twice: byte 4095 starts a 2-byte sequence
        CHECK(C::clip(big).size() == 4095);
        C::History h;
        h.add(big, false);
        CHECK(h.at(0).text.size() == 4095 && validUtf8(h.at(0).text));
        h.add(big + "more", false);              // same first 4 KB: same item
        CHECK(h.size() == 1);
        CHECK(C::isCurrent(big, h.at(0)));
        CHECK(!C::isCurrent("", h.at(0)));
        CHECK(C::clip(std::string(4096, 'y')).size() == 4096);
        std::string emoji;
        for (int i = 0; i < 1100; ++i) emoji += "\xf0\x9f\x98\x80";   // 4 bytes each
        CHECK(C::clip(emoji).size() == 4096 && validUtf8(C::clip(emoji)));
        std::string three(4094, 'z'); three += "\xe2\x82\xac";       // euro sign across the cap
        CHECK(C::clip(three).size() == 4094);
    }
    // --- touch / remove by id ---
    {
        C::History h;
        h.add("one", false); h.add("two", true); h.add("three", false);
        const uint32_t idTwo = h.at(1).id;
        std::string t;
        CHECK(h.touch(idTwo, &t) && t == "two");
        CHECK(h.at(0).text == "two" && h.at(0).priv);     // keeps its own flag
        CHECK(h.currentPrivate());
        CHECK(h.at(0).id == idTwo);
        CHECK(!h.touch(9999));
        CHECK(h.remove(idTwo, &t) && t == "two");
        CHECK(h.size() == 2 && h.at(0).text == "three" && h.at(1).text == "one");
        CHECK(!h.remove(idTwo));
    }
    // --- private rule ---
    {
        C::History h;
        h.add("normal 1", false);
        h.add("secret", true);
        h.add("normal 2", false);
        CHECK(h.count(false) == 2 && h.count(true) == 3);
        auto v = h.visible(false);
        CHECK(v.size() == 2 && v[0].text == "normal 2" && v[1].text == "normal 1");
        v = h.visible(true);
        CHECK(v.size() == 3 && v[1].text == "secret");
        CHECK(h.hasPrivate());
        CHECK(!h.currentPrivate());
        CHECK(!h.purgePrivate());                           // the clipboard holds "normal 2": kept
        CHECK(h.size() == 2 && !h.hasPrivate());
        CHECK(h.at(0).text == "normal 2" && h.at(1).text == "normal 1");
        // the current clipboard came from a private tab: the purge says to clear it
        h.add("secret 2", true);
        CHECK(h.currentPrivate() && h.hasPrivate());
        CHECK(h.purgePrivate());
        CHECK(!h.currentPrivate() && !h.hasPrivate() && h.size() == 2);
        // private copy of a text already listed as normal: stays normal (no loss in normal tabs)
        h.add("normal 1", true);
        CHECK(h.size() == 2 && h.at(0).text == "normal 1" && !h.at(0).priv && h.currentPrivate());
        CHECK(h.count(false) == 2);
        // normal copy of a private item: becomes normal (it was copied in a normal tab)
        h.add("p", true);
        CHECK(h.at(0).priv);
        h.add("p", false);
        CHECK(!h.at(0).priv && h.count(false) == 3);
        // a private item pushed out of the ring leaves nothing private once a normal copy is current
        C::History r;
        r.add("x", true);
        for (int i = 0; i < 10; ++i) r.add("n" + std::to_string(i), false);
        CHECK(!r.hasPrivate() && !r.currentPrivate());
        r.add("y", true);
        for (int i = 0; i < 10; ++i) r.add("m" + std::to_string(i), false);
        CHECK(!r.hasPrivate());   // the clipboard holds m9 now
        r.add("z", true);
        CHECK(r.hasPrivate());
        // purge on a ring that wrapped
        C::History w;
        for (int i = 0; i < 25; ++i) w.add("t" + std::to_string(i), i % 3 == 0);
        const size_t normal = w.count(false);
        w.purgePrivate();
        CHECK(w.size() == normal);
        for (size_t i = 0; i < w.size(); ++i) CHECK(!w.at(i).priv);
        for (size_t i = 0; i + 1 < w.size(); ++i) CHECK(w.at(i).id > w.at(i + 1).id);
    }
    // --- clear ---
    {
        C::History h;
        h.add("a", true); h.add("b", false);
        h.clear();
        CHECK(h.empty() && !h.hasPrivate() && h.count(true) == 0);
        h.add("c", false);
        CHECK(h.size() == 1 && h.at(0).text == "c");
    }
    // --- labels: one line, 40 code points, UTF-8 safe ---
    {
        CHECK(C::label("hello") == "hello");
        CHECK(C::label("  a\r\n\tb  ") == "a b");
        CHECK(C::label("a\xc2\xa0\xc2\xa0" "b\xe2\x80\xa8" "c\xc2\x85" "d") == "a b c d");
        CHECK(C::label("") == "");
        CHECK(C::label(" \n ") == "");
        const std::string forty(40, 'k');
        CHECK(C::label(forty) == forty);
        const std::string l = C::label(forty + "k");
        CHECK(cps(l) == 40 && l.size() == 40 && l.substr(37) == "...");
        std::string words;
        for (int i = 0; i < 20; ++i) words += "ab ";
        const std::string lw = C::label(words);
        CHECK(cps(lw) <= 40 && lw.substr(lw.size() - 3) == "..." && lw[lw.size() - 4] != ' ');
        std::string cyr;
        for (int i = 0; i < 50; ++i) cyr += "\xd0\x96";          // 2-byte letters
        const std::string lc = C::label(cyr);
        CHECK(validUtf8(lc) && cps(lc) == 40);
        std::string cjk;
        for (int i = 0; i < 40; ++i) cjk += "\xe6\xbc\xa2";      // exactly 40: no cut
        CHECK(C::label(cjk) == cjk);
        std::string emo;
        for (int i = 0; i < 41; ++i) emo += "\xf0\x9f\x98\x80";
        const std::string le = C::label(emo);
        CHECK(validUtf8(le) && cps(le) == 40 && le.size() == 37 * 4 + 3);
        CHECK(C::label("abcdef", 3) == "...");
        CHECK(C::label("abc", 3) == "abc");
        CHECK(C::label("multi\nline\ncopied text") == "multi line copied text");
        // a cut 4 KB item still labels cleanly
        std::string big(4095, 'x'); big += "\xc3\xa9";
        CHECK(validUtf8(C::label(C::clip(big))));
    }
    // --- texts, ids ---
    {
        CHECK(C::quickLabel(3) == "Clipboard (3)");
        CHECK(C::rowValue(true, false) == "In clipboard");
        CHECK(C::rowValue(false, true) == "Private");
        CHECK(C::rowValue(false, false).empty());
        CHECK(C::kKbKey != C::kPanelKind && C::kQuickRowId >= 900 && C::kClearRowId < 1);
    }
    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "ok", checks, fails);
    return fails ? 1 : 0;
}
