// OMNI_FIND_PLUS_V1: host tests for OmniFindPlus.h (copied to engine/entry by apply_find_plus.py).
//   g++ -std=c++20 -Wall -Wextra -I<tools or tree/engine/entry> test_find_plus.cpp -o t && ./t
#include "OmniFindPlus.h"
#include <cstdio>

static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniFindPlus;

static State opened(const char* q)
{
    State s;
    s.setQuery(q);
    s.open = true;
    return s;
}

int main()
{
    // option flags (the WKFindOptions values, Shared/API/c/WKFindOptions.h)
    CHECK(kCaseInsensitive == 1 && kBackwards == 8 && kWrapAround == 16 && kShowOverlay == 32 && kShowFindIndicator == 64 && kShowHighlight == 128);
    CHECK(options(false, 0) == (kCaseInsensitive | kWrapAround | kShowHighlight | kShowFindIndicator));
    CHECK(options(true, 1) == (kWrapAround | kShowHighlight | kShowFindIndicator));
    CHECK(options(false, -1) == (kCaseInsensitive | kWrapAround | kShowHighlight | kShowFindIndicator | kBackwards));
    CHECK(options(true, -1) & kBackwards);
    CHECK(!(options(false, 1) & kBackwards));
    CHECK(!(options(false, 0) & kShowOverlay));
    CHECK(options(true, 0) & kShowHighlight);   // every search highlights all matches

    // a new search: searching, then "1 of 17"
    State s = opened("cat");
    s.begin(0);
    CHECK(countLabel(s) == "Searching\xe2\x80\xa6");
    CHECK(s.found("cat", 17) == Wrap::None);
    CHECK(countLabel(s) == "1 of 17");
    // next / previous, wrap both ways
    s.begin(1); CHECK(s.found("cat", 17) == Wrap::None); CHECK(countLabel(s) == "2 of 17");
    s.begin(-1); s.found("cat", 17); CHECK(countLabel(s) == "1 of 17");
    s.begin(-1); CHECK(s.found("cat", 17) == Wrap::ToBottom); CHECK(countLabel(s) == "17 of 17");
    s.begin(1); CHECK(s.found("cat", 17) == Wrap::ToTop); CHECK(countLabel(s) == "1 of 17");
    CHECK(std::string(wrapNotice(Wrap::ToTop)).find("first match") != std::string::npos);
    CHECK(std::string(wrapNotice(Wrap::ToBottom)).find("last match") != std::string::npos);
    CHECK(std::string(wrapNotice(Wrap::None)).empty());

    // answers still in flight keep their own steps: R1 R1 L1 pressed fast, answers arrive afterwards
    s.begin(1); s.begin(1); s.begin(-1);
    s.found("cat", 17); s.found("cat", 17); s.found("cat", 17);
    CHECK(countLabel(s) == "2 of 17");
    CHECK(s.steps.empty());

    // an answer for an older query is ignored
    s.setQuery("dog"); s.begin(0);
    CHECK(s.found("cat", 17) == Wrap::None);
    CHECK(s.count == -1);
    s.found("dog", 3);
    CHECK(countLabel(s) == "1 of 3");
    // the page changed between presses: the count differs -> back to 1
    s.begin(1); s.found("dog", 3); CHECK(s.index == 2);
    s.begin(1); s.found("dog", 5); CHECK(countLabel(s) == "1 of 5");

    // a single match never claims to wrap
    State one = opened("x"); one.begin(0); one.found("x", 1);
    one.begin(1); CHECK(one.found("x", 1) == Wrap::None); CHECK(countLabel(one) == "1 of 1");
    one.begin(-1); CHECK(one.found("x", 1) == Wrap::None);

    // more than the maximum (kWKMoreThanMaximumMatchCount, was "..." forever)
    State many = opened("e"); many.begin(0);
    CHECK(many.found("e", kMoreThanMax) == Wrap::None);
    CHECK(countLabel(many) == "1000+ matches");
    CHECK(many.more && many.count == 1000);
    many.begin(1); many.found("e", 1001); CHECK(countLabel(many) == "1000+ matches");
    many.begin(0); many.found("e", 1000); CHECK(countLabel(many) == "1 of 1000");

    // no matches
    State none = opened("zzz"); none.begin(0);
    none.failed("zzz");
    CHECK(none.noMatches());
    CHECK(countLabel(none) == "No matches");
    none.begin(1); none.begin(1); none.found("zzz", 0); CHECK(countLabel(none) == "No matches");
    CHECK(none.steps.size() == 1);   // a zero count takes exactly one step
    none.found("zzz", 0); CHECK(none.steps.empty());
    none.begin(1); none.failed("other"); CHECK(none.steps.size() == 1);   // not ours: the step stays queued
    none.failed("zzz"); CHECK(none.steps.empty() && none.count == 0);
    // ignored when closed
    State closed; closed.setQuery("a"); closed.begin(0);
    CHECK(closed.found("a", 4) == Wrap::None && closed.count == -1);
    closed.failed("a"); CHECK(closed.count == -1);
    CHECK(!closed.noMatches());

    // close keeps the query and the case setting, drops the rest
    State c = opened("Mixed"); c.caseSensitive = true; c.begin(0); c.found("Mixed", 4); c.begin(1);
    c.close();
    CHECK(!c.open && c.query == "Mixed" && c.caseSensitive && c.count == -1 && c.index == 0 && c.steps.empty());
    CHECK(std::string(caseNotice(true)) == "Match case: on" && std::string(caseNotice(false)) == "Match case: off");

    // query length cap, UTF-8 safe
    State l;
    l.setQuery(std::string(300, 'a'));
    CHECK(l.query.size() == kQueryMax);
    std::string u(kQueryMax - 1, 'a');
    u += "\xc3\xa9tail";   // 2-byte sequence across the cut
    l.setQuery(u);
    CHECK(l.query.size() == kQueryMax - 1);
    std::string u3(kQueryMax - 2, 'a');
    u3 += "\xe2\x80\xa6zz";   // 3-byte sequence across the cut
    l.setQuery(u3);
    CHECK(l.query.size() == kQueryMax - 2);
    std::string u4(kQueryMax - 3, 'a');
    u4 += "\xe2\x80\xa6zz";   // ends exactly at the cut: kept
    l.setQuery(u4);
    CHECK(l.query.size() == kQueryMax);
    l.setQuery("short");
    CHECK(l.query == "short");

    // buttons
    CHECK(actionFor(bR1) == Action::Next && actionFor(bDpadRight) == Action::Next);
    CHECK(actionFor(bL1) == Action::Previous && actionFor(bDpadLeft) == Action::Previous);
    CHECK(actionFor(bTriangle) == Action::Edit);
    CHECK(actionFor(bSquare) == Action::ToggleCase);
    CHECK(actionFor(bCircle) == Action::Close);
    CHECK(actionFor(bOther) == Action::None);
    CHECK(std::string(tipText()).find("{L1}") != std::string::npos && std::string(tipText()).find("{Square}") != std::string::npos);

    // per-tab store: private and normal tabs never share
    Store st;
    int tabA = 0, tabB = 0, tabC = 0;
    st.at(key(&tabA)).setQuery("secret");
    st.at(key(&tabA)).open = true;
    CHECK(st.find(key(&tabB)) == nullptr);
    st.at(key(&tabB)).setQuery("public");
    CHECK(st.find(key(&tabA))->query == "secret" && st.find(key(&tabB))->query == "public");
    st.at(key(&tabC));
    CHECK(st.size() == 3);
    st.retain({ key(&tabB) });   // A and C closed
    CHECK(st.size() == 1 && st.find(key(&tabA)) == nullptr && st.find(key(&tabB))->query == "public");
    st.erase(key(&tabB));
    CHECK(st.size() == 0);

    // bar hits (offsets from the bar's left / top)
    CHECK(hit(-1, 10) == Hit::None && hit(kBarW, 10) == Hit::None && hit(10, kBarH) == Hit::None && hit(10, -1) == Hit::None);
    CHECK(hit(kBarW - 10, 25) == Hit::Close);
    CHECK(hit(kBarW - 75, 25) == Hit::Next);
    CHECK(hit(kBarW - 125, 25) == Hit::Previous);
    CHECK(hit(kChipX + 5, 25) == Hit::ToggleCase);
    CHECK(hit(20, 25) == Hit::Edit && hit(kCountRight - 20, 25) == Hit::Edit);
    CHECK(kChipX + kChipW < kCountRight - 120);   // the count ("1000+ matches") has room right of the chip
    CHECK(kCountRight < kBarW - 150);
    CHECK(28 + 40 + kQueryMaxW < kChipX);        // "Find" + the query stop before the chip
    CHECK(kBarX + kBarW <= 1280);

    std::printf("%s: %d checks, %d failures\n", fails ? "FAILED" : "ok", checks, fails);
    return fails ? 1 : 0;
}
