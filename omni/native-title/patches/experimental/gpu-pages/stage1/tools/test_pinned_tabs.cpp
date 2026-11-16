// OMNI_PINNED_TABS_V1: host tests for engine/entry/OmniPinnedTabs.h (the pure part of pinned tabs).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_pinned_tabs.cpp -o t && ./t
#include "OmniPinnedTabs.h"
#include <cstdio>
#include <string>
#include <vector>

namespace P = OmniPinnedTabs;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

// Applies a toggle the way the shell does: flip, then move to targetIndex.
static void toggle(std::vector<char>& names, std::vector<bool>& pinned, size_t i)
{
    pinned[i] = !pinned[i];
    const size_t to = P::targetIndex(pinned, i);
    P::moveItem(names, i, to);
    // move the flag the same way
    std::vector<int> flags(pinned.begin(), pinned.end());
    P::moveItem(flags, i, to);
    for (size_t k = 0; k < flags.size(); ++k) pinned[k] = flags[k] != 0;
}
static bool pinnedFirst(const std::vector<bool>& p)
{
    bool seenUnpinned = false;
    for (bool b : p) { if (!b) seenUnpinned = true; else if (seenUnpinned) return false; }
    return true;
}

int main()
{
    // --- canPin / caps
    CHECK(P::canPin(false, true, 0) == P::kOk);
    CHECK(P::canPin(true, true, 0) == P::kPrivate);
    CHECK(P::canPin(false, false, 0) == P::kNotWeb);
    CHECK(P::canPin(false, true, 5) == P::kOk);
    CHECK(P::canPin(false, true, 6) == P::kFull);
    CHECK(P::canPin(true, false, 6) == P::kPrivate);   // private wins
    CHECK(P::refusal(P::kFull).find("6 tabs") == 0);
    CHECK(P::refusal(P::kOk).empty());

    // --- moveItem
    {
        std::vector<int> v = { 0, 1, 2, 3, 4 };
        P::moveItem(v, 3, 1); CHECK((v == std::vector<int>{ 0, 3, 1, 2, 4 }));
        P::moveItem(v, 1, 3); CHECK((v == std::vector<int>{ 0, 1, 2, 3, 4 }));
        P::moveItem(v, 0, 4); CHECK((v == std::vector<int>{ 1, 2, 3, 4, 0 }));
        P::moveItem(v, 4, 0); CHECK((v == std::vector<int>{ 0, 1, 2, 3, 4 }));
        P::moveItem(v, 2, 2); P::moveItem(v, 9, 0); P::moveItem(v, 0, 9);
        CHECK((v == std::vector<int>{ 0, 1, 2, 3, 4 }));
    }

    // --- ordering: pin / unpin keeps pinned tabs first and the others in order
    {
        std::vector<char> n = { 'a', 'b', 'c', 'd', 'e' };
        std::vector<bool> p(5, false);
        toggle(n, p, 3);   // pin d
        CHECK((n == std::vector<char>{ 'd', 'a', 'b', 'c', 'e' })); CHECK(p[0] && !p[1]);
        toggle(n, p, 4);   // pin e: after d
        CHECK((n == std::vector<char>{ 'd', 'e', 'a', 'b', 'c' })); CHECK(p[0] && p[1] && !p[2]);
        toggle(n, p, 0);   // unpin d: first place after the pinned group
        CHECK((n == std::vector<char>{ 'e', 'd', 'a', 'b', 'c' })); CHECK(p[0] && !p[1]);
        CHECK(pinnedFirst(p));
        toggle(n, p, 0);   // unpin e: stays at 0 (no other pinned)
        CHECK((n == std::vector<char>{ 'e', 'd', 'a', 'b', 'c' })); CHECK(P::countPinned(p) == 0);
        // random walk keeps the invariant
        unsigned seed = 7;
        for (int k = 0; k < 500; ++k) {
            seed = seed * 1103515245u + 12345u;
            toggle(n, p, (seed >> 8) % n.size());
            CHECK(pinnedFirst(p));
        }
    }
    {
        const auto o = P::pinnedFirstOrder({ false, true, false, true, true });
        CHECK((o == std::vector<size_t>{ 1, 3, 4, 0, 2 }));
        CHECK(P::pinnedFirstOrder({}).empty());
    }

    // --- unload order
    CHECK(P::unloadsBefore(false, 900, true, 100));    // unpinned before pinned, however recent
    CHECK(!P::unloadsBefore(true, 100, false, 900));
    CHECK(P::unloadsBefore(false, 100, false, 200));
    CHECK(!P::unloadsBefore(false, 200, false, 200));
    CHECK(P::unloadsBefore(true, 100, true, 200));
    {
        std::vector<P::UnloadCandidate> c(4);
        c[0] = { true, true, 10 };    // pinned, oldest
        c[1] = { true, false, 500 };
        c[2] = { true, false, 300 };  // unpinned oldest -> picked
        c[3] = { false, false, 1 };   // cannot unload (active / playing / loading)
        CHECK(P::pickUnload(c) == 2);
        c[1].can = c[2].can = false;  // only the pinned one qualifies: it goes (the loaded-tab limit still holds)
        CHECK(P::pickUnload(c) == 0);
        c[0].can = false;
        CHECK(P::pickUnload(c) == -1);
        CHECK(P::pickUnload({}) == -1);
    }

    // --- session.txt line
    CHECK(P::pinnedLine(0) == "pinned\t0\n");
    CHECK(P::pinnedLine(12) == "pinned\t12\n");
    {
        int i = -1;
        CHECK(P::parsePinnedLine("pinned\t3", i) && i == 3);
        CHECK(P::parsePinnedLine("pinned\t15\r\n", i) && i == 15);
        CHECK(P::parsePinnedLine(P::pinnedLine(7), i) && i == 7);
        i = -1;
        CHECK(!P::parsePinnedLine("pinned\t", i));
        CHECK(!P::parsePinnedLine("pinned\t-1", i));
        CHECK(!P::parsePinnedLine("pinned\t1x", i));
        CHECK(!P::parsePinnedLine("pinned\t1234", i));
        CHECK(!P::parsePinnedLine("pinned 1", i));
        CHECK(!P::parsePinnedLine("tab\thttps://a/\tA", i));
        CHECK(!P::parsePinnedLine("selected\t2", i));
        CHECK(i == -1);
    }
    {
        const std::vector<bool> ok = { true, true, false, true, true, true, true, true, true };
        auto f = P::restoreFlags({ 0, 2, 3, 3, 40, -1 }, ok);   // 2 is not a web page / private, 3 twice, 40 past the end
        CHECK(f.size() == ok.size());
        CHECK(f[0] && !f[1] && !f[2] && f[3] && !f[4]);
        f = P::restoreFlags({ 0, 1, 3, 4, 5, 6, 7, 8 }, ok);    // cap 6
        CHECK(P::countPinned(f) == 6); CHECK(!f[7] && !f[8]);
        CHECK(P::countPinned(P::restoreFlags({}, ok)) == 0);
    }
    // a written session (as omniSessionText) round-trips; an old file has no pinned lines
    {
        std::vector<bool> pinned = { true, true, false, false };
        std::string text = "omni-session\t1\n";
        for (int n = 0; n < 4; ++n) { text += "tab\thttps://s" + std::to_string(n) + "/\tT\n"; if (pinned[size_t(n)]) text += P::pinnedLine(n); }
        text += "selected\t2\n";
        std::vector<int> idx;
        size_t pos = 0;
        while (pos < text.size()) {
            size_t e = text.find('\n', pos);
            const std::string line = text.substr(pos, e - pos);
            pos = e + 1;
            int i;
            if (P::parsePinnedLine(line, i)) idx.push_back(i);
        }
        CHECK((P::restoreFlags(idx, std::vector<bool>(4, true)) == pinned));
    }

    // --- close arm
    {
        P::CloseArm a;
        int t1 = 0, t2 = 0;
        CHECK(P::closeStep(a, &t1, false, 1000) == P::kCloseNow);   // unpinned: closes
        CHECK(P::closeStep(a, &t1, true, 1000) == P::kAskFirst);
        CHECK(P::armed(a, &t1, 2000)); CHECK(!P::armed(a, &t2, 2000));
        CHECK(P::closeStep(a, &t1, true, 2000) == P::kCloseNow);    // again within 4 s
        CHECK(!P::armed(a, &t1, 2001));
        CHECK(P::closeStep(a, &t1, true, 10000) == P::kAskFirst);
        CHECK(P::closeStep(a, &t1, true, 14000) == P::kAskFirst);   // 4 s later: asks again
        CHECK(P::closeStep(a, &t2, true, 14100) == P::kAskFirst);   // another tab re-arms
        CHECK(P::closeStep(a, &t1, true, 14200) == P::kAskFirst);
        CHECK(P::closeStep(a, &t1, true, 14300) == P::kCloseNow);
        CHECK(!P::armed(a, nullptr, 0));
    }

    // --- strip layout
    {
        int first = 0;
        P::Strip L = P::stripLayout(3, 1, 0, first);   // 1 pinned + 2 tabs
        CHECK(L.slots.size() == 3 && !L.arrows);
        CHECK(L.slots[0].compact && L.slots[0].x == 100 && L.slots[0].w == 52);
        CHECK(L.restX0 == 160);
        CHECK(!L.slots[1].compact && L.slots[1].index == 1 && L.slots[1].x == 160 && L.slots[1].w == 232);   // 240 max
        CHECK(L.slots[2].x == 400);
        for (auto& s : L.slots) CHECK(s.x + s.w <= P::kX1);

        L = P::stripLayout(6, 6, 2, first);            // only pinned tabs
        CHECK(L.slots.size() == 6 && L.count == 0 && !L.arrows && first == 0);
        CHECK(L.slots[5].x == 400);

        L = P::stripLayout(16, 6, 15, first);          // 6 pinned + 10 others: scrolls, selected in view
        CHECK(L.arrows && L.restX0 == 460);
        CHECK(L.count == 4);                           // (600 - 60) / 120
        bool seen = false;
        for (auto& s : L.slots) { if (s.index == 15) seen = true; CHECK(s.x + s.w <= P::kRightArrowX); }
        CHECK(seen);
        CHECK(L.hiddenLeft == 6 && L.hiddenRight == 0 && first == 6);
        L = P::stripLayout(16, 6, 0, first);           // a pinned tab selected: the scroll stays
        CHECK(first == 6);
        L = P::stripLayout(16, 6, 7, first);           // tab 7 (unpinned #1) scrolls back
        CHECK(first == 1 && L.slots[6].index == 7);
        L = P::stripLayout(10, 15, 0, first);          // pinned > n is clamped
        CHECK(L.slots.size() == 10 && L.count == 0);
        L = P::stripLayout(0, 0, 0, first);
        CHECK(L.slots.empty());
        L = P::stripLayout(5, 0, 0, first);            // nothing pinned: as OMNI_FEATURES_V3's compact strip
        CHECK(L.slots.size() == 5 && L.slots[0].x == 100 && L.slots[0].w == 184 && L.slots[1].x == 292);
    }
    // --- hit test
    {
        int first = 0;
        P::Strip L = P::stripLayout(3, 1, 1, first);
        CHECK(P::hit(L, 120, 1).kind == P::kTab && P::hit(L, 120, 1).index == 0);   // pinned tile
        CHECK(P::hit(L, 151, 1).kind == P::kTab);                                    // tile edge (100 + 52 = 152)
        CHECK(P::hit(L, 155, 1).kind == P::kNone);                                   // gap
        CHECK(P::hit(L, 200, 1).kind == P::kTab && P::hit(L, 200, 1).index == 1);
        CHECK(P::hit(L, 160 + 232 - 10, 1).kind == P::kClose);                      // close cross of an unpinned tab
        CHECK(P::hit(L, 99, 1).kind == P::kNone);
        CHECK(P::hit(L, 1050, 1).kind == P::kNone);
        // a pinned tile never has a close cross, even selected
        CHECK(P::hit(L, 100 + 52 - 3, 0).kind == P::kTab);
        CHECK(!P::closable(L.slots[0], 0));
        L = P::stripLayout(16, 6, 15, first);
        CHECK(P::hit(L, 465, 15).kind == P::kLeft);
        CHECK(P::hit(L, 1040, 15).kind == P::kRight);
        CHECK(P::hit(L, 105, 15).kind == P::kTab && P::hit(L, 105, 15).index == 0);
    }

    // --- initial
    CHECK(P::initial("https://www.youtube.com/watch", "YouTube") == "Y");
    CHECK(P::initial("https://9gag.com/", "") == "9");
    CHECK(P::initial("http://user@example.org:8080/", "") == "E");
    CHECK(P::initial("newtab", "  hello") == "H");
    CHECK(P::initial("", "\xc3\xa9t\xc3\xa9") == "\xc3\xa9");   // a whole UTF-8 sequence
    CHECK(P::initial("", "") == "?");

    // --- Replace keeps pinned tabs
    {
        OmniTabSessions::Session s;
        s.name = "Movie night";
        for (const char* u : { "https://a/", "https://b/", "https://c/", "https://d/" }) s.tabs.push_back({ u, "" });
        // 2 pinned (one of them is b), 3 unpinned, limit 4: room 2 -> a, c; b already open; d over the limit
        auto p = P::replacePlan(s, { "https://b/", "https://x/" }, 3, 4);
        CHECK((p.open == std::vector<int>{ 0, 2 }));
        CHECK(p.alreadyOpen == 1 && p.overLimit == 1 && p.closes == 3);
        CHECK(OmniTabSessions::planValue(p, true) == "Opens 2, closes 3 (1 over the limit)");
        // nothing pinned: the same as OmniTabSessions::plan(replace)
        auto q = P::replacePlan(s, {}, 5, 4), r = OmniTabSessions::plan(s, { "https://a/" }, 5, 4, true);
        CHECK(q.open == r.open && q.closes == r.closes && q.overLimit == r.overLimit && q.alreadyOpen == r.alreadyOpen);
        // all pinned, limit full: nothing opens
        auto f = P::replacePlan(s, { "https://1/", "https://2/", "https://3/", "https://4/" }, 0, 4);
        CHECK(f.open.empty() && f.overLimit == 4 && f.closes == 0);
    }

    // --- texts
    CHECK(P::rowValue("", true) == "Pinned");
    CHECK(P::rowValue("Current", true) == "Current, pinned");
    CHECK(P::rowValue("Unloaded", true) == "Unloaded \xc2\xb7 pinned");
    CHECK(P::rowValue("Loading", false) == "Loading");
    CHECK(std::string(P::faceLabel(true)) == "Unpin" && std::string(P::faceLabel(false)) == "Pin");
    CHECK(P::pinnedNotice(2).find("(2 of 6)") != std::string::npos);

    printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "OK", checks, fails);
    return fails ? 1 : 0;
}
