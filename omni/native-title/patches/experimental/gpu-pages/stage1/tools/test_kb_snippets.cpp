// OMNI_KB_SNIPPETS_V1: host tests of the pure keyboard snippets (OmniKbSnippets.h).
//   g++ -std=c++20 -Wall -Wextra -Werror -I. test_kb_snippets.cpp -o t && ./t      (run in tools/, or -I<tree>/engine/entry)
#include "OmniKbSnippets.h"
#include <cstdio>
#include <string>

namespace S = OmniKbSnippets;
static int fails = 0, checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); } } while (0)

static bool validUtf8(const std::string& s)
{
    for (size_t i = 0; i < s.size();) {
        const size_t n = S::seqLen(s, i);
        if (!n) return false;
        i += n;
    }
    return true;
}
static std::string rep(const std::string& u, size_t n) { std::string s; for (size_t i = 0; i < n; ++i) s += u; return s; }

int main()
{
    // --- clean: one line, trimmed, controls -> space, invalid bytes dropped ---
    {
        CHECK(S::clean("  hello   world  ") == "hello world");
        CHECK(S::clean("a\r\nb\nc\rd\te") == "a b c d e");
        CHECK(S::clean("\n\n") == "");
        CHECK(S::clean("x\x01y\x7fz") == "x y z");
        CHECK(S::clean("a\xe2\x80\xa8" "b") == "a b");                 // U+2028
        CHECK(S::clean("a\xc2\x85" "b") == "a b");                     // U+0085 (C1)
        CHECK(S::clean("caf\xc3\xa9") == "caf\xc3\xa9");               // é kept
        CHECK(S::clean("ok\xff\xfe" "go") == "okgo");                  // invalid bytes dropped
        CHECK(S::clean("\xc3") == "");                                 // a cut sequence
        CHECK(S::clean("\xc0\xaf") == "");                             // overlong '/'
        CHECK(S::clean("\xed\xa0\x80") == "");                         // a surrogate
        CHECK(S::clean("\xf0\x9f\x98\x80 smile") == "\xf0\x9f\x98\x80 smile");   // emoji kept
    }
    // --- 200-character cap, UTF-8 safe ---
    {
        bool cut = false;
        const std::string a200 = rep("a", 200);
        CHECK(S::clean(a200, &cut) == a200 && !cut);
        CHECK(S::clean(a200 + "b", &cut) == a200 && cut);
        const std::string e = "\xc3\xa9";                              // 2 bytes
        const std::string r = S::clean(rep(e, 250), &cut);
        CHECK(cut && S::cpCount(r) == 200 && r.size() == 400 && validUtf8(r));
        const std::string g = "\xf0\x9f\x98\x80";                      // 4 bytes
        const std::string r2 = S::clean("x" + rep(g, 300), &cut);
        CHECK(cut && S::cpCount(r2) == 200 && validUtf8(r2) && r2.size() == 1 + 199 * 4);
        // a cut that lands after a space: trailing space trimmed
        const std::string r3 = S::clean(rep("a", 199) + " bbbb", &cut);
        CHECK(cut && r3 == rep("a", 199));
        // cutChars never splits a sequence
        for (size_t n = 0; n < 8; ++n) CHECK(validUtf8(S::cutChars("a\xc3\xa9\xe2\x82\xac\xf0\x9f\x98\x80z", n)));
        CHECK(S::cutChars("a\xc3\xa9\xe2\x82\xac", 2) == "a\xc3\xa9");
    }
    // --- labels ---
    {
        CHECK(S::label("short") == "short");
        const std::string l = S::label(rep("w", 60));
        CHECK(l == rep("w", 37) + "..." && S::cpCount(l) == 40);
        const std::string l2 = S::label(rep("\xc3\xa9", 60));
        CHECK(validUtf8(l2) && S::cpCount(l2) == 40);
        CHECK(S::label(rep("a", 36) + " bcdefgh") == rep("a", 36) + "...");   // no space before the dots
    }
    // --- list: add, caps, duplicates, remove ---
    {
        S::List l;
        CHECK(l.empty() && !l.full());
        CHECK(l.add("me@example.com") == S::kAdded);
        CHECK(l.add("  me@example.com ") == S::kDuplicate);
        CHECK(l.add(" \n\t ") == S::kEmpty);
        for (int i = 1; i < 10; ++i) CHECK(l.add("phrase " + std::to_string(i)) == S::kAdded);
        CHECK(l.size() == 10 && l.full());
        CHECK(l.add("one more") == S::kFull);
        CHECK(l.add("phrase 3") == S::kDuplicate);                     // duplicate wins over full
        CHECK(l.at(0) == "me@example.com" && l.at(9) == "phrase 9");   // saved in order, newest last
        CHECK(l.remove(0) && l.size() == 9 && l.at(0) == "phrase 1");
        CHECK(!l.remove(9) && l.size() == 9);
        CHECK(l.add("one more") == S::kAdded && l.at(9) == "one more");
        bool cut = false;
        S::List m;
        CHECK(m.add(rep("x", 500), &cut) == S::kAdded && cut && m.at(0).size() == 200);
    }
    // --- file: serialize / parse round trip, header, CRLF, junk, caps ---
    {
        S::List l;
        l.add("Hello, I'm on my way");
        l.add("caf\xc3\xa9 \xf0\x9f\x98\x80");
        l.add("back\\slash and \"quotes\"");
        const std::string f = l.serialize();
        CHECK(f == "omni-kb-snippets\t1\nHello, I'm on my way\ncaf\xc3\xa9 \xf0\x9f\x98\x80\nback\\slash and \"quotes\"\n");
        const S::List p = S::List::parse(f);
        CHECK(p.size() == 3 && p.items() == l.items());
        // CRLF, a different header version, blank lines, duplicates, invalid bytes, a long line
        const std::string g = "omni-kb-snippets\t2\r\none\r\n\r\n  one  \r\ntw\xffo\r\n" + rep("z", 300) + "\r\n";
        const S::List q = S::List::parse(g);
        CHECK(q.size() == 3 && q.at(0) == "one" && q.at(1) == "two" && q.at(2) == rep("z", 200));
        // no header: every line is a phrase; a header-looking line later is a phrase too
        const S::List r = S::List::parse("first\nomni-kb-snippets\t1\n");
        CHECK(r.size() == 2 && r.at(0) == "first" && r.at(1) == "omni-kb-snippets 1");
        // no final newline
        CHECK(S::List::parse("omni-kb-snippets\t1\nlast").size() == 1);
        // at most 10 kept (the first 10)
        std::string many = "omni-kb-snippets\t1\n";
        for (int i = 0; i < 25; ++i) many += "s" + std::to_string(i) + "\n";
        const S::List m = S::List::parse(many);
        CHECK(m.size() == 10 && m.at(0) == "s0" && m.at(9) == "s9");
        CHECK(S::List::parse("").empty() && S::List::parse("omni-kb-snippets\t1\n").empty());
        // an empty list still writes the header (the file is rewritten, not left stale)
        CHECK(S::List().serialize() == "omni-kb-snippets\t1\n");
        // the read cap: a huge file is read up to 64 KB only
        const std::string huge = "omni-kb-snippets\t1\n" + rep("y", 200 * 1024);
        const S::List h = S::List::parse(huge);
        CHECK(h.size() == 1 && h.at(0).size() == 200);
    }
    // --- picker ---
    {
        S::Picker p;
        // empty list: only the save row
        CHECK(p.press(S::bDown, 0) == S::aMove && p.sel == 0);
        CHECK(p.press(S::bCross, 0) == S::aAskSave);
        p.askSave();
        CHECK(p.confirm == S::cSave);
        CHECK(p.press(S::bCircle, 0) == S::aCancel && p.confirm == S::cNone);
        CHECK(p.press(S::bCross, 0) == S::aAskSave);
        p.askSave();
        CHECK(p.press(S::bCross, 0) == S::aSave && p.confirm == S::cNone);
        // 3 phrases: rows 0..2, save row 3; wrap both ways
        CHECK(p.press(S::bUp, 3) == S::aMove && p.sel == 3);
        CHECK(p.press(S::bDown, 3) == S::aMove && p.sel == 0);
        CHECK(p.press(S::bCross, 3) == S::aInsert);
        CHECK(p.press(S::bSquare, 3) == S::aAskDelete && p.confirm == S::cDelete);
        CHECK(p.press(S::bCircle, 3) == S::aCancel && p.confirm == S::cNone);
        CHECK(p.press(S::bSquare, 3) == S::aAskDelete);
        CHECK(p.press(S::bDown, 3) == S::aMove && p.confirm == S::cNone && p.sel == 1);   // moving cancels
        CHECK(p.press(S::bSquare, 3) == S::aAskDelete);
        CHECK(p.press(S::bSquare, 3) == S::aDelete && p.confirm == S::cNone);
        p.sel = 3;
        CHECK(p.press(S::bSquare, 3) == S::aNone && p.confirm == S::cNone);                // the save row can't be deleted
        p.afterDelete(2);
        CHECK(p.sel == 2);
        CHECK(p.press(S::bOther, 2) == S::aNone);
        CHECK(p.press(S::bCircle, 2) == S::aClose);
        // full list: the save row only explains
        p.sel = 10;
        CHECK(p.press(S::bCross, 10) == S::aFullNotice && p.confirm == S::cNone);
        // a stale selection is clamped
        p.sel = 42;
        CHECK(p.press(S::bCross, 2) == S::aInsert && p.sel == 0);
        // clicks
        CHECK(p.click(1, 3) == S::aInsert && p.sel == 1);
        CHECK(p.click(3, 3) == S::aAskSave);
        CHECK(p.click(10, 10) == S::aFullNotice);
        CHECK(p.click(-1, 3) == S::aClose && p.click(4, 3) == S::aClose);
    }
    // --- texts: never the phrase, private wording only when private ---
    {
        CHECK(std::string(S::subtitle(S::cSave, true)).find("Private tab") == 0);
        CHECK(std::string(S::subtitle(S::cSave, false)).find("Private") == std::string::npos);
        CHECK(std::string(S::subtitle(S::cNone, false)).find("plain text") != std::string::npos);
        CHECK(std::string(S::addedNotice(S::kAdded, true)).find("200") != std::string::npos);
        CHECK(std::string(S::saveRowLabel(10)).find("delete one") != std::string::npos);
        CHECK(std::string(S::saveRowLabel(3)) == "+ Save current text as snippet");
    }
    std::printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
