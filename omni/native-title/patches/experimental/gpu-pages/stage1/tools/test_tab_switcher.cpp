// OMNI_TAB_SWITCHER_V1: host test of the pure part (engine/entry/OmniTabSwitcher.h).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_tab_switcher.cpp -o t && ./t
#include "OmniTabSwitcher.h"
#include <cstdio>
#include <string>
#include <vector>

namespace S = OmniTabSwitcher;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); } } while (0)

static S::Item it(uint32_t at, bool seen, bool priv = false, bool cur = false)
{
    S::Item i;
    i.shownAt = at; i.seen = seen; i.priv = priv; i.current = cur;
    return i;
}

int main()
{
    // --- MRU order: current first, then newest shown, never-shown last in tab order ---
    {
        std::vector<S::Item> v = { it(100, true), it(0, false), it(500, true, false, true), it(300, true), it(0, false), it(200, true) };
        CHECK((S::order(v) == std::vector<int> { 2, 3, 5, 0, 1, 4 }));
    }
    {   // equal shownAt keeps tab order (stable)
        std::vector<S::Item> v = { it(5, true, false, true), it(7, true), it(7, true) };
        CHECK((S::order(v) == std::vector<int> { 0, 1, 2 }));
    }
    {   // tick wrap: 0xFFFFFF00 is older than 0x10 shown after the wrap
        std::vector<S::Item> v = { it(1, true, false, true), it(0xFFFFFF00u, true), it(0x10, true) };
        CHECK((S::order(v) == std::vector<int> { 0, 2, 1 }));
    }
    {   // private rule: from a normal tab no private tabs; from a private tab both
        std::vector<S::Item> v = { it(9, true, false, true), it(8, true, true), it(7, true, false) };
        CHECK((S::order(v) == std::vector<int> { 0, 2 }));
        v[0].priv = true;
        CHECK((S::order(v) == std::vector<int> { 0, 1, 2 }));
        CHECK(S::visible(false, false) && S::visible(false, true) && !S::visible(true, false) && S::visible(true, true));
    }
    {   // no current tab (none active): everything visible is listed; empty in, empty out
        std::vector<S::Item> v = { it(1, true), it(2, true, true) };
        CHECK((S::order(v) == std::vector<int> { 0 }));
        CHECK(S::order({}).empty());
    }
    // --- selection ---
    CHECK(S::step(0, 5, 1) == 1 && S::step(4, 5, 1) == 0 && S::step(0, 5, -1) == 4 && S::step(2, 5, -7) == 0);
    CHECK(S::step(3, 0, 1) == 0 && S::step(0, 1, 1) == 0);
    CHECK(S::firstSel(5, true) == 1 && S::firstSel(5, false) == 4 && S::firstSel(2, false) == 1 && S::firstSel(1, true) == 0);
    CHECK(S::window(0, 3, 5) == 0);
    CHECK(S::window(0, 7, 10) == 1 && S::window(0, 9, 10) == 3 && S::window(3, 2, 10) == 2 && S::window(3, 5, 10) == 3);
    CHECK(S::window(9, 0, 10) == 0 && S::window(8, 9, 10) == 3);
    {   // walking the whole ring keeps the selection on screen
        int sel = 0, first = 0;
        for (int k = 0; k < 40; ++k) {
            sel = S::step(sel, 12, k % 3 == 0 ? -1 : 1);
            first = S::window(first, sel, 12);
            CHECK(sel >= first && sel < first + S::kVisible && first >= 0 && first <= 12 - S::kVisible);
        }
    }
    CHECK(S::counter(1, 6) == "2 of 6");
    // --- input ---
    CHECK(S::classify(S::bR1, false, true, true) == S::aOpenNext);
    CHECK(S::classify(S::bL1, false, true, true) == S::aOpenPrev);
    CHECK(S::classify(S::bR1, false, false, true) == S::aPass);    // no L2: plain next tab
    CHECK(S::classify(S::bR1, false, true, false) == S::aPass);    // not browsing (keyboard, panel, full screen)
    CHECK(S::classify(S::bRight, false, true, true) == S::aPass);  // L2 + D-pad is not the opening chord
    CHECK(S::classify(S::bUp, false, true, true) == S::aPass);     // L2 + D-pad up stays site zoom
    CHECK(S::classify(S::bCross, false, true, true) == S::aPass);  // L2 + Cross stays the Options menu
    CHECK(S::classify(S::bR1, true, true, false) == S::aNext && S::classify(S::bRight, true, false, false) == S::aNext);
    CHECK(S::classify(S::bL1, true, true, true) == S::aPrev && S::classify(S::bLeft, true, true, true) == S::aPrev);
    CHECK(S::classify(S::bCross, true, true, true) == S::aCommit && S::classify(S::bCircle, true, true, true) == S::aCancel);
    CHECK(S::classify(S::bUp, true, true, true) == S::aSwallow && S::classify(S::bOther, true, true, true) == S::aSwallow);
    {
        S::Swallow w;
        CHECK(!w.release(9));
        w.take(9); w.take(10);
        CHECK(w.release(9) && !w.release(9) && w.release(10) && w.bits == 0);
        w.take(-1); w.take(40);
        CHECK(w.bits == 0);
    }
    // --- tiles ---
    CHECK(S::hostOf("https://www.GitHub.com/omni/issues") == "github.com");
    CHECK(S::hostOf("http://user:pw@example.org:8080/x?y") == "example.org");
    CHECK(S::hostOf("https://[::1]:8443/") == "[::1]");
    CHECK(S::hostOf("omni://pages/start") == "" && S::hostOf("") == "" && S::hostOf("about:blank") == "");
    CHECK(S::siteName("en.wikipedia.org") == "wikipedia" && S::siteName("bbc.co.uk") == "bbc" && S::siteName("m.youtube.com") == "youtube");
    CHECK(S::siteName("localhost") == "localhost" && S::siteName("192.168.0.2") == "192.168.0.2" && S::siteName("github.com") == "github");
    CHECK(S::letter("https://en.wikipedia.org/wiki/Tea", "Tea") == "W");
    CHECK(S::letter("https://www.youtube.com/", "x") == "Y");
    CHECK(S::letter("http://192.168.0.2/", "Router") == "1");
    CHECK(S::letter("", "  reader view") == "R");
    CHECK(S::letter("", "\xC3\xA9t\xC3\xA9") == "T");                 // first ASCII letter of the title
    CHECK(S::letter("", "\xE6\x97\xA5\xE6\x9C\xAC") == "\xE6\x97\xA5");  // no ASCII: the first character, whole
    CHECK(S::letter("", "") == "?" && S::letter("", "   ") == "?");
    CHECK(S::letter("", "\xE6") == "\xE6");                            // a cut sequence does not read past the end
    CHECK(S::colourIndex("https://github.com/a", "A") == S::colourIndex("http://www.github.com/b", "B"));
    CHECK(S::colourIndex("https://en.wikipedia.org/", "") == S::colourIndex("https://de.wikipedia.org/", ""));
    for (int i = -3; i < 20; ++i) { const S::Rgb c = S::colour(i); CHECK(c.r || c.g || c.b); }
    CHECK(S::colourIndex("", "x") >= 0 && S::colourIndex("", "x") < S::kColours);
    CHECK(S::shownTitle("GitHub", "https://github.com") == "GitHub");
    CHECK(S::shownTitle("  ", "https://www.github.com/x") == "github.com" && S::shownTitle("", "") == "New tab");
    CHECK(S::caption("https://github.com/x", false, false) == "github.com");
    CHECK(S::caption("https://github.com/x", false, true) == "This tab \xC2\xB7 github.com");
    CHECK(S::caption("https://github.com/x", true, false) == "Private \xC2\xB7 github.com");
    CHECK(S::caption("", true, true) == "This tab \xC2\xB7 Private" && S::caption("", false, false).empty());
    CHECK(std::string(S::releaseHint(true)) == "Release L2 to switch" && std::string(S::releaseHint(false)) == "Release LT to switch");

    std::printf("%s: %d checks, %d failed\n", fails ? "FAILED" : "ok", checks, fails);
    return fails ? 1 : 0;
}
