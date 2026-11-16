// OMNI_BF_LIST_V1: host tests of the pure Back history model (OmniBfList.h).
//   g++ -std=c++20 -Wall -Wextra -Werror -I. test_bf_list.cpp -o t && ./t      (run in tools/, or -I<tree>/engine/entry)
#include "OmniBfList.h"
#include <cstdio>
#include <string>
#include <vector>

namespace B = OmniBfList;
static int fails = 0, checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); } } while (0)

static bool validUtf8(const std::string& s)
{
    for (size_t i = 0; i < s.size();) {
        const size_t n = B::utf8Len(s, i);
        if (!n) return false;
        i += n;
    }
    return true;
}

int main()
{
    // --- order: newest first, current marked, 15 each way ---
    {
        CHECK((B::offsets(0, 0) == std::vector<int> { 0 }));
        CHECK((B::offsets(2, 0) == std::vector<int> { 0, -1, -2 }));
        CHECK((B::offsets(0, 2) == std::vector<int> { 2, 1, 0 }));
        CHECK((B::offsets(3, 2) == std::vector<int> { 2, 1, 0, -1, -2, -3 }));
        const auto big = B::offsets(40, 22);
        CHECK(big.size() == 31);
        CHECK(big.front() == 15 && big.back() == -15);
        CHECK(big[15] == 0);
        CHECK(B::initialRow(B::offsets(3, 2)) == 3);   // the page before
        CHECK(B::initialRow(B::offsets(0, 2)) == 2);   // no earlier page: the current one
        CHECK(B::initialRow(B::offsets(0, 0)) == 0);
        CHECK(B::initialRow({}) == 0);
        CHECK(B::initialRow(big) == 16);
    }
    // --- UTF-8 shortening ---
    {
        CHECK(B::shorten("short", 72) == "short");
        CHECK(B::shorten("abcdefghij", 8) == "abcde...");
        CHECK(B::shorten("abcd efghij", 8) == "abcd...");          // no space before the dots
        CHECK(B::shorten("abc", 2) == "...");
        // 2-, 3- and 4-byte characters are never cut in half, whatever the limit
        const std::string mixed = "\xc3\xa9t\xc3\xa9 \xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e \xf0\x9f\x98\x80\xf0\x9f\x98\x80 caf\xc3\xa9";
        for (size_t m = 0; m < mixed.size() + 2; ++m) {
            const std::string s = B::shorten(mixed, m);
            CHECK(validUtf8(s));
            CHECK(s.size() <= std::max<size_t>(m, 3));
        }
        CHECK(B::shorten(mixed, 9) == "\xc3\xa9t\xc3\xa9...");
        CHECK(B::shorten(std::string(200, 'x'), B::kTitleMaxBytes).size() == B::kTitleMaxBytes);
    }
    // --- cleaning ---
    {
        CHECK(B::clean("  Hello\t\r\n  world  ") == "Hello world");
        CHECK(B::clean("a\x7f" "b") == "a b");
        CHECK(B::clean("bad \xff\xfe bytes \xc3") == "bad bytes");
        CHECK(B::clean("\xed\xa0\x80x") == "x");            // a surrogate is not UTF-8
        CHECK(B::clean("\xc0\xaf" "x") == "x");            // overlong
        CHECK(B::clean("\xe6\x97\xa5 ok") == "\xe6\x97\xa5 ok");
        CHECK(B::clean("") == "");
        CHECK(validUtf8(B::clean("\xf4\x90\x80\x80 \xf0\x9f\x98")));
    }
    // --- hosts ---
    {
        CHECK(B::hostOf("https://www.Example.com:8443/a?b#c") == "example.com");
        CHECK(B::hostOf("http://user:pw@news.site.org/x") == "news.site.org");
        CHECK(B::hostOf("http://[::1]:8080/") == "[::1]");
        CHECK(B::hostOf("https://www./") == "www.");
        CHECK(B::hostOf("https://host?q=1") == "host");
        CHECK(B::hostOf("file:///data/omni/x.html") == "file");
        CHECK(B::hostOf("about:blank") == "about");
        CHECK(B::hostOf("data:text/html,<b>hi</b>") == "data");
        CHECK(B::hostOf("blob:https://m.youtube.com/123") == "m.youtube.com");
        CHECK(B::hostOf("omni://pages/start") == "pages");
        CHECK(B::hostOf("") == "");
        CHECK(B::hostOf("no scheme here") == "");
        CHECK(B::hostOf(":x") == "");
    }
    // --- rows ---
    {
        const B::Row cur = B::makeRow(0, "Front page \xe2\x80\x93 News", "https://www.news.example/");
        CHECK(cur.label == "Front page \xe2\x80\x93 News" && cur.host == "news.example" && cur.value == "Current page");
        const B::Row back = B::makeRow(-2, "", "https://example.org/path");
        CHECK(back.label == "https://example.org/path" && back.host == "example.org" && back.value.empty());
        const B::Row data = B::makeRow(1, " \n ", "data:text/html,secret");
        CHECK(data.label == "data:" && data.host == "data");
        const B::Row none = B::makeRow(-1, "", "");
        CHECK(none.label == "Untitled page" && none.host.empty());
        const B::Row longOne = B::makeRow(-1, std::string(30, 'a') + std::string(30, ' ') + std::string(100, 'b'), "https://x.y/");
        CHECK(longOne.label.size() <= B::kTitleMaxBytes && longOne.label.find("  ") == std::string::npos);
        std::string hugeHost = "https://" + std::string(100, 'h') + ".com/";
        CHECK(B::makeRow(-1, "t", hugeHost).host.size() == B::kHostMaxBytes);
    }
    // --- texts ---
    {
        CHECK(B::subtitle(false, 1, 0) == "1 earlier page");
        CHECK(B::subtitle(false, 3, 1) == "3 earlier pages, 1 later page");
        CHECK(B::subtitle(true, 20, 2) == "20 earlier pages, 2 later pages (the nearest 15 shown). Private tab: never saved");
        CHECK(B::kPanelKind != B::kQuickRowId && B::kQuickRowId >= 900);   // >= 900: its quick-menu hook runs before the >= 900 rows
    }
    // --- hold Circle ---
    {
        B::Hold h;
        CHECK(h.tick(100, true) == B::Act::None);            // not active
        CHECK(h.release() == B::Act::None);
        CHECK(h.begin(3, 1000));
        CHECK(!h.begin(4, 1001));                            // one hold at a time
        CHECK(h.owns(3) && !h.owns(4));
        CHECK(h.tick(1499, true) == B::Act::None);
        CHECK(h.release() == B::Act::Back);                  // short press: an ordinary Back, on release
        CHECK(!h.active);
        CHECK(h.begin(3, 2000));
        CHECK(h.tick(2500, true) == B::Act::Open);           // 500 ms: the list, once
        CHECK(h.tick(2600, true) == B::Act::None);
        CHECK(h.tick(9000, true) == B::Act::None);
        CHECK(h.release() == B::Act::None);                  // the hold's release does not also go Back
        CHECK(!h.active);
        CHECK(h.begin(1, 3000));
        CHECK(h.tick(3200, false) == B::Act::Back);          // let go but the UP went elsewhere: still a Back
        CHECK(!h.active);
        CHECK(h.begin(1, 4000));
        CHECK(h.tick(4600, true) == B::Act::Open);
        CHECK(h.tick(4700, false) == B::Act::None);          // fired, then let go unseen: nothing more
        CHECK(!h.active);
        CHECK(h.begin(2, 0xFFFFFF00u));                      // SDL_GetTicks wrap
        CHECK(h.tick(0x000000F0u, true) == B::Act::None);    // 496 ms
        CHECK(h.tick(0x000000F4u, true) == B::Act::Open);    // 500 ms
        h.cancel();
        CHECK(!h.active && h.release() == B::Act::None);
    }
    std::printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "ok", checks, fails);
    return fails ? 1 : 0;
}
