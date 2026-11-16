// OMNI_KB_LAYOUTS_V1 host tests: g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_kb_layouts.cpp -o t && ./t
// (the tree must have apply_kb_words.py and apply_kb_layouts.py applied: OmniKbWords.h is checked against accents too).
#include "OmniKbLayouts.h"
#include "OmniKbWords.h"
#include <cstdio>
#include <set>

namespace L = OmniKbLayouts;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); } } while (0)

static std::string join(const std::vector<std::string>& v)
{
    std::string o;
    for (auto& s : v) { if (!o.empty()) o += ' '; o += s; }
    return o;
}

int main()
{
    // QWERTY is exactly the rows OMNI_KEYBOARD_V2 had.
    {
        auto t = L::compose(0, L::kTailText), u = L::compose(0, L::kTailUrl), e = L::compose(0, L::kTailEmail);
        CHECK(t.rows[0] == "q w e r t y u i o p");
        CHECK(t.rows[1] == "a s d f g h j k l '");
        CHECK(t.rows[2] == "z x c v b n m , . ?");
        CHECK(u.rows[1] == "a s d f g h j k l -");
        CHECK(u.rows[2] == "z x c v b n m . / ?");
        CHECK(e.rows[1] == "a s d f g h j k l -");
        CHECK(e.rows[2] == "z x c v b n m . _ @");
    }
    // AZERTY: m on row 2, the tail key moves to row 3 (10 keys each).
    {
        auto t = L::compose(1, L::kTailText), e = L::compose(1, L::kTailEmail);
        CHECK(t.rows[0] == "a z e r t y u i o p");
        CHECK(t.rows[1] == "q s d f g h j k l m");
        CHECK(t.rows[2] == "w x c v b n ' , . ?");
        CHECK(e.rows[2] == "w x c v b n - . _ @");
    }
    // QWERTZ: z/y swapped, umlauts, 11-key rows.
    {
        auto t = L::compose(2, L::kTailText);
        CHECK(t.rows[0] == "q w e r t z u i o p \xc3\xbc");
        CHECK(t.rows[1] == "a s d f g h j k l \xc3\xb6 \xc3\xa4");
        CHECK(t.rows[2] == "y x c v b n m ' , . ?");
    }
    // Every layout: 10 or 11 keys per row, all 26 ASCII letters once, one code point per key, valid UTF-8, unique ids.
    std::set<std::string> ids;
    for (int i = 0; i < L::kCount; ++i) {
        CHECK(ids.insert(L::kLayouts[i].id).second);
        CHECK(L::parseId(L::kLayouts[i].id) == i);
        CHECK(L::parseId(L::serialize(i)) == i);
        for (int tail = 0; tail < 3; ++tail) {
            auto r = L::compose(i, tail);
            std::string ascii;
            for (int k = 0; k < 3; ++k) {
                const auto keys = L::tokens(r.rows[k]);
                CHECK(keys.size() >= 10 && keys.size() <= 11);
                for (auto& key : keys) {
                    uint32_t cp;
                    CHECK(L::validUtf8(key));
                    CHECK(L::singleCodePoint(key, cp));
                    if (cp >= 'a' && cp <= 'z') ascii += char(cp);
                }
            }
            std::set<char> letters(ascii.begin(), ascii.end());
            CHECK(letters.size() == 26 && ascii.size() == 26);
        }
    }
    CHECK(L::parseId("") == 0);
    CHECK(L::parseId("dvorak") == 0);
    CHECK(L::parseId("  azerty\r\n") == 1);
    CHECK(L::parseId("AZERTY") == 0);   // ids are lower case
    CHECK(L::stepLayout(0, -1) == L::kCount - 1);
    CHECK(L::stepLayout(L::kCount - 1, 1) == 0);
    CHECK(L::stepLayout(99, 1) == 1);

    // UTF-8 encode / decode.
    for (uint32_t cp : { 0x41u, 0x7Fu, 0x80u, 0xE9u, 0x7FFu, 0x800u, 0x20ACu, 0xFFFFu, 0x10000u, 0x1F600u, 0x10FFFFu }) {
        const std::string s = L::utf8(cp);
        uint32_t back = 0;
        CHECK(L::singleCodePoint(s, back) && back == cp);
    }
    CHECK(L::utf8(0xE9) == "\xc3\xa9");
    CHECK(L::utf8(0x20AC) == "\xe2\x82\xac");
    CHECK(L::utf8(0xD800) == "\xef\xbf\xbd");
    CHECK(!L::validUtf8("\xc3"));
    CHECK(!L::validUtf8("\xc0\xaf"));       // overlong
    CHECK(!L::validUtf8("\xed\xa0\x80"));   // surrogate
    CHECK(!L::validUtf8("\xe9"));           // Latin-1 byte, not UTF-8
    CHECK(L::validUtf8("caf\xc3\xa9"));

    // Case.
    CHECK(L::upperToken("a") == "A");
    CHECK(L::upperToken("\xc3\xa4") == "\xc3\x84");   // ä -> Ä
    CHECK(L::upperToken("\xc3\xb8") == "\xc3\x98");   // ø -> Ø
    CHECK(L::upperToken("\xc3\xb1") == "\xc3\x91");   // ñ -> Ñ
    CHECK(L::upperToken("\xc3\x9f") == "\xc3\x9f");   // ß stays
    CHECK(L::upperToken(".com") == ".com");
    CHECK(L::upperToken("1") == "1");
    CHECK(L::upperToken("\xe2\x82\xac") == "\xe2\x82\xac");   // € unchanged
    CHECK(L::upperToken("\xc3\xb7") == "\xc3\xb7");   // ÷ is not a letter
    CHECK(L::isUpperLetter("A") && L::isUpperLetter("\xc3\x89") && L::isUpperLetter("\xc5\x81"));   // A É Ł
    CHECK(!L::isUpperLetter("a") && !L::isUpperLetter("\xc3\xa9") && !L::isUpperLetter("AB") && !L::isUpperLetter("1")
          && !L::isUpperLetter("\xc3\x9f") && !L::isUpperLetter(""));
    for (uint32_t cp = 0x20; cp < 0x180; ++cp) {   // lower(upper(x)) == x for every lower-case letter it maps
        const uint32_t u = L::upperCp(cp);
        if (u != cp && cp != 0x131) CHECK(L::lowerCp(u) == cp);
    }

    // Accent variants.
    CHECK(join(L::variants("e")) == "\xc3\xa9 \xc3\xa8 \xc3\xaa \xc3\xab \xc4\x93 \xc4\x99 \xc4\x9b");
    CHECK(join(L::variants("E")) == "\xc3\x89 \xc3\x88 \xc3\x8a \xc3\x8b \xc4\x92 \xc4\x98 \xc4\x9a");
    CHECK(L::variants("a").size() == 9 && L::variants("a")[0] == "\xc3\xa0");
    CHECK(L::variants("A")[4] == "\xc3\x86");   // Æ
    CHECK(L::variants("o")[4] == "\xc3\xb8" && L::variants("O")[4] == "\xc3\x98" && L::variants("O")[6] == "\xc5\x92");   // ø Ø Œ
    CHECK(L::variants("c")[0] == "\xc3\xa7" && L::variants("C")[0] == "\xc3\x87");
    CHECK(L::variants("n")[0] == "\xc3\xb1" && L::variants("N")[0] == "\xc3\x91");
    CHECK(L::variants("s")[0] == "\xc3\x9f" && L::variants("S")[0] == "\xc3\x9f");   // ß in both cases
    CHECK(L::variants("u")[3] == "\xc3\xbc" && L::variants("i")[3] == "\xc3\xaf");
    CHECK(L::variants("y")[1] == "\xc3\xbf" && L::variants("Y")[1] == "\xc5\xb8");   // ÿ Ÿ
    CHECK(L::variants("q").empty() && L::variants("1").empty() && L::variants(".com").empty() && L::variants("\xc3\xa4").empty()
          && L::variants("").empty() && L::variants("ee").empty());
    for (const auto& a : L::kAccents) {
        const auto lo = L::variants(a.base), up = L::variants(L::upperToken(a.base));
        CHECK(!lo.empty() && lo.size() == up.size() && lo.size() <= 9);
        for (size_t i = 0; i < lo.size(); ++i) {
            uint32_t c;
            CHECK(L::singleCodePoint(lo[i], c) && L::singleCodePoint(up[i], c));
            CHECK(L::upperToken(lo[i]) == up[i]);
        }
    }
    CHECK(L::step(0, 5, -1) == 4 && L::step(4, 5, 1) == 0 && L::step(2, 5, 1) == 3 && L::step(0, 0, 1) == 0);
    CHECK(!L::holdOpens(1000, 1449) && L::holdOpens(1000, 1450));
    CHECK(L::holdOpens(0xFFFFFF00u, 0xFFFFFF00u + 500) && L::holdOpens(0xFFFFFF00u, 0x200u) && !L::holdOpens(0xFFFFFF00u, 0x10u));
    CHECK(L::popupLeft(500, 4, 56, 184, 1096) == 388);
    CHECK(L::popupLeft(200, 9, 56, 184, 1096) == 184);
    CHECK(L::popupLeft(1090, 9, 56, 184, 1096) == 1096 - 504);

    // Word suggestions with accented text (OmniKbWords: ASCII letters only): words with accents are skipped whole,
    // never cut at the accent or learned without it.
    namespace W = OmniKbWords;
    std::string out;
    CHECK(!W::clean("caf\xc3\xa9", out));   // rejected (callers ignore `out` on false)
    CHECK(W::fragment("caf\xc3\xa9", "").empty());                 // caret right after é: no chips
    CHECK(W::fragment("na\xc3\xafve", "").empty());                // "ve" after ï is not a word start
    CHECK(W::fragment("caf", "\xc3\xa9").empty());                 // é right of the caret
    CHECK(W::finishedWord("caf\xc3\xa9 ").empty());                // Space after café teaches nothing
    CHECK(W::finishedWord("\xc3\xa9t\xc3\xa9 ").empty());
    CHECK(W::fragment("\xc3\xa9t\xc3\xa9 wor", "") == "wor");      // the next ASCII word still gets chips
    CHECK(W::finishedWord("\xc3\xa0 hello ") == "hello");
    W::Learned l;
    CHECK(!l.add("caf\xc3\xa9") && !l.add("\xc3\xbc" "ber") && l.words.empty());
    l.parse("omni-kb-words\t1\ncaf\xc3\xa9\t3\t1\nhello\t2\t2\n\xc3\xbc" "ber\t1\t3\n");
    CHECK(l.words.size() == 1 && l.words[0].word == "hello");      // bad lines in the file are dropped, not mangled
    CHECK(L::validUtf8(l.serialize()));

    std::printf("%s: %d checks, %d failed\n", fails ? "FAILED" : "ok", checks, fails);
    return fails ? 1 : 0;
}
