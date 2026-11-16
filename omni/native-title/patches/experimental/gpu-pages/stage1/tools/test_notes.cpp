// OMNI_NOTES_V1: host tests of the pure part (OmniNotes.h).
//   g++ -std=c++20 -Wall -Wextra -Werror -I. test_notes.cpp -o t && ./t
#include "OmniNotes.h"
#include <cstdio>
#include <string>
#include <vector>

namespace N = OmniNotes;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static void testClean()
{
    CHECK(N::clean("abc") == "abc");
    CHECK(N::clean("a\r\nb\rc") == "a\nb\nc");
    CHECK(N::clean("a\tb") == "a\tb");
    CHECK(N::clean(std::string("a\x01" "b\x7f" "c", 5)) == "abc");
    CHECK(N::clean(std::string("a\0b", 3)) == "ab");
    CHECK(N::clean("x\xff" "y") == "x\xef\xbf\xbdy");                         // invalid byte -> U+FFFD
    CHECK(N::clean("x\xe2\x80\xa8y") == "x\ny");                              // U+2028 -> LF
    CHECK(N::clean("  lead\n\n  \t\n") == "  lead");                           // trailing blanks go, leading spaces stay
    CHECK(N::clean("\n\n \t ").empty());
    bool cut = true;
    CHECK(N::clean("short", &cut) == "short" && !cut);
    std::string big(5000, 'a');
    const std::string c = N::clean(big, &cut);
    CHECK(cut && c.size() == N::kMaxBytes);
    std::string uni;
    while (uni.size() < 5000) uni += "\xe2\x82\xac";                          // 3-byte euro signs
    const std::string cu = N::clean(uni, &cut);
    CHECK(cut && cu.size() <= N::kMaxBytes && cu.size() % 3 == 0 && cu.size() > N::kMaxBytes - 3);
}

static void testEscape()
{
    const std::string s = "a\\b\nc\td\\n";
    CHECK(N::escape(s) == "a\\\\b\\nc\\td\\\\n");
    CHECK(N::unescape(N::escape(s)) == s);
    CHECK(N::escape(s).find('\n') == std::string::npos && N::escape(s).find('\t') == std::string::npos);
    CHECK(N::unescape("x\\qy\\") == "xqy");                                   // unknown escape, lone backslash
    CHECK(N::unescape("\\r") == "\r");
}

static void testRoundTrip()
{
    std::vector<N::Note> v;
    long long id = 0;
    CHECK(N::add(v, "Wi-Fi code\n1234-5678\ttab", 1000, &id) == N::Add::Ok && id == 1);
    CHECK(N::add(v, "back\\slash \\n literal", 1001, &id) == N::Add::Ok && id == 2);
    CHECK(N::add(v, "  \n ", 1002) == N::Add::Empty && v.size() == 2);
    const std::string file = N::serialize(v);
    CHECK(file.rfind("omni-notes 1\n", 0) == 0);
    size_t lines = 0;
    for (char ch : file) lines += ch == '\n';
    CHECK(lines == 3);                                                         // header + one line per note
    const std::vector<N::Note> back = N::parse(file);
    CHECK(back.size() == 2);
    CHECK(back.size() == 2 && back[0].text == v[0].text && back[1].text == v[1].text);
    CHECK(back.size() == 2 && back[0].id == 1 && back[0].created == 1000 && back[0].modified == 1000);
    CHECK(N::serialize(back) == file);                                        // stable
}

static void testParseTolerant()
{
    // no header, CRLF lines, extra future fields, junk lines, duplicate and bad ids, an empty text
    const std::string f = "1\t10\t20\thello\\nworld\textra\tfields\r\n"
                          "garbage line\n"
                          "\n"
                          "1\t11\t21\tdup id\n"
                          "x\t1\t1\tbad id\n"
                          "0\t1\t1\tzero id\n"
                          "3\tq\t\tno dates\n"
                          "4\t5\t6\t\\n \\t\n";
    const std::vector<N::Note> v = N::parse(f);
    CHECK(v.size() == 2);
    CHECK(v.size() == 2 && v[0].id == 1 && v[0].text == "hello\nworld" && v[0].modified == 20);
    CHECK(v.size() == 2 && v[1].id == 3 && v[1].created == 0 && v[1].modified == 0 && v[1].text == "no dates");
    // a later version's header is read the same way
    CHECK(N::parse("omni-notes 2\n7\t1\t2\tnew\tmore\n").size() == 1);
    // over the cap: the newest 200 are kept
    std::string big = "omni-notes 1\n";
    for (int i = 1; i <= 250; ++i) big += std::to_string(i) + "\t" + std::to_string(i) + "\t" + std::to_string(i) + "\tn" + std::to_string(i) + "\n";
    const std::vector<N::Note> kept = N::parse(big);
    CHECK(kept.size() == N::kMaxNotes);
    bool oldest = false;
    for (const N::Note& n : kept) if (n.id <= 50) oldest = true;
    CHECK(!oldest);
    // a stored text over 4 KB is cut on reading
    CHECK(N::parse("9\t1\t1\t" + std::string(6000, 'z') + "\n")[0].text.size() == N::kMaxBytes);
    // over the file cap: nothing
    CHECK(N::parse(std::string(size_t(N::kMaxFileBytes) + 1, 'a')).empty());
}

static void testCaps()
{
    std::vector<N::Note> v;
    for (size_t i = 0; i < N::kMaxNotes; ++i) CHECK(N::add(v, "n" + std::to_string(i), static_cast<long long>(i)) == N::Add::Ok);
    CHECK(N::add(v, "one more", 999) == N::Add::Full && v.size() == N::kMaxNotes);
    CHECK(N::remove(v, 5) && !N::remove(v, 5) && v.size() == N::kMaxNotes - 1);
    long long id = 0;
    CHECK(N::add(v, "again", 1000, &id) == N::Add::Ok && id == static_cast<long long>(N::kMaxNotes) + 1);
    bool cut = false;
    std::vector<N::Note> w;
    CHECK(N::add(w, std::string(5000, 'b'), 1, nullptr, &cut) == N::Add::Ok && cut && w[0].text.size() == N::kMaxBytes);
}

static void testLines()
{
    std::string t = "one\ntwo\nthree";
    CHECK(N::lines(t).size() == 3 && N::join(N::lines(t)) == t);
    CHECK(N::lines("").empty());
    CHECK(N::setLine(t, 1, "TWO") && t == "one\nTWO\nthree");
    CHECK(N::setLine(t, 3, "four") && t == "one\nTWO\nthree\nfour");          // append
    CHECK(!N::setLine(t, 9, "x"));
    CHECK(N::setLine(t, 0, "a\nb") && N::lines(t).size() == 5);               // a pasted text becomes lines
    CHECK(N::removeLine(t, 0) && t == "b\nTWO\nthree\nfour");
    CHECK(!N::removeLine(t, 4));
    CHECK(N::setLine(t, 3, "") && t == "b\nTWO\nthree");                      // an emptied last line goes
    CHECK(N::setLine(t, 1, "") && t == "b\n\nthree");                         // an empty middle line stays
    std::string e;
    CHECK(N::setLine(e, 0, "first") && e == "first");
    std::string full(4090, 'x');
    bool cut = false;
    CHECK(N::setLine(full, 1, "123456789", &cut) && cut && full.size() == N::kMaxBytes);
    std::string one = "only";
    CHECK(N::removeLine(one, 0) && one.empty());
}

static void testTexts()
{
    CHECK(N::title("\n  \n  Shopping   list\nmilk") == "Shopping list");
    CHECK(N::title("") == "(empty note)");
    CHECK(N::title(std::string(200, 'q')).size() == N::kTitleBytes);
    CHECK(N::title(std::string(200, 'q')).substr(N::kTitleBytes - 3) == "...");
    CHECK(N::pageNote("  Example\tPage ", "https://example.com/a") == "Example Page\nhttps://example.com/a");
    CHECK(N::pageNote("", "https://example.com/") == "https://example.com/");
    CHECK(N::pageNote("https://x.y/", "https://x.y/") == "https://x.y/");
    CHECK(N::lineDetail("a") == "1 line" && N::lineDetail("a\nb") == "2 lines");
    CHECK(N::addedNotice(true, false).find("first 4 KB") != std::string::npos);
    CHECK(N::addedNotice(false, true).find("not saved") != std::string::npos);
    CHECK(N::fullNotice().find("200") != std::string::npos);
    CHECK(N::editorSubtitle("ab\ncd") == "2 lines \xc2\xb7 5 / 4096 bytes");
    const long long now = 1794787200;   // 2026-11-16 (any value works: relative)
    CHECK(N::dateText(now, now) == "Today");
    CHECK(N::dateText(now - 86400, now) == "Yesterday");
    CHECK(N::dateText(now - 40 * 86400, now).find("20") != std::string::npos);
    CHECK(N::preview("a\tb\n\nc", 50) == "a b c");
}

static void testGate()
{
    N::PrivateGate g;
    CHECK(!g.needAsk(false, false));
    CHECK(g.needAsk(true, false));
    CHECK(!g.needAsk(true, true));                                            // guest: memory only, no ask
    g.accept();
    CHECK(!g.needAsk(true, false));
    g.tick(true);
    CHECK(!g.needAsk(true, false));                                           // same private session
    g.tick(false);                                                            // the last private tab closed
    CHECK(g.needAsk(true, false));
}

static void testOrder()
{
    std::vector<N::Note> v;
    N::add(v, "a", 5); N::add(v, "b", 9); N::add(v, "c", 9);
    const std::vector<size_t> o = N::order(v);
    CHECK(o.size() == 3 && o[0] == 2 && o[1] == 1 && o[2] == 0);              // newest first, ties: higher id
    CHECK(N::find(v, 2) && N::find(v, 2)->text == "b" && !N::find(v, 7));
}

int main()
{
    testClean();
    testEscape();
    testRoundTrip();
    testParseTolerant();
    testCaps();
    testLines();
    testTexts();
    testGate();
    testOrder();
    std::printf("%s: %d checks, %d failed\n", fails ? "FAILED" : "ok", checks, fails);
    return fails ? 1 : 0;
}
