// OMNI_TAB_MEMORY_VIEW_V1 tests: g++ -std=c++20 -Wall -Wextra -I<dir of OmniTabMemoryView.h> test_tab_memory_view.cpp -o t && ./t
#include "OmniTabMemoryView.h"
#include <cstdio>
#include <string>
#include <vector>

static int failures = 0;
#define CHECK(c) do { if (!(c)) { ++failures; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

using namespace OmniTabMemoryView;

static TabState T(uint32_t shownAt, bool pinned = false, bool collapsed = false, bool kept = false, Block b = kFree, bool loaded = true)
{
    TabState t; t.shownAt = shownAt; t.pinned = pinned; t.collapsed = collapsed; t.kept = kept; t.block = b; t.loaded = loaded;
    return t;
}
// The order before this patch (OmniTabGroups::unloadsBefore), for the "nothing kept" equivalence.
static bool oldBefore(bool aP, bool aC, uint32_t aS, bool bP, bool bC, uint32_t bS)
{
    if (aP != bP) return !aP;
    if (aC != bC) return aC;
    return aS < bS;
}
static int oldPick(const std::vector<TabState>& v)
{
    int best = -1;
    for (size_t i = 0; i < v.size(); ++i) {
        if (!v[i].loaded || v[i].block != kFree) continue;
        if (best < 0 || oldBefore(v[i].pinned, v[i].collapsed, v[i].shownAt, v[size_t(best)].pinned, v[size_t(best)].collapsed, v[size_t(best)].shownAt)) best = int(i);
    }
    return best;
}

int main()
{
    // --- pick order: least recently shown
    CHECK(pickUnload({ T(50), T(10), T(30) }, false) == 1);
    CHECK(pickUnload({}, false) == -1);
    // ties: the first one (strict <, as before)
    CHECK(pickUnload({ T(10), T(10) }, false) == 0);
    // pinned last
    CHECK(pickUnload({ T(1, true), T(99) }, false) == 1);
    CHECK(pickUnload({ T(1, true), T(5, true) }, false) == 0);
    // collapsed group's tabs first
    CHECK(pickUnload({ T(1), T(99, false, true) }, false) == 1);
    // pinned beats collapsed (pinned is never in a group, but the order says pinned last first)
    CHECK(pickUnload({ T(1, true, true), T(99) }, false) == 1);
    // blocked / unloaded / current never picked
    CHECK(pickUnload({ T(1, false, false, false, kCurrent), T(2, false, false, false, kPlaying), T(3, false, false, false, kLoading),
                       T(4, false, false, false, kFree, false), T(5) }, false) == 4);
    CHECK(pickUnload({ T(1, false, false, false, kCurrent) }, true) == -1);
    // kept: skipped unless memory is low; then last
    CHECK(pickUnload({ T(1, false, false, true), T(50) }, false) == 1);
    CHECK(pickUnload({ T(1, false, false, true) }, false) == -1);
    CHECK(pickUnload({ T(1, false, false, true) }, true) == 0);
    CHECK(pickUnload({ T(1, false, false, true), T(50, true) }, true) == 1);    // a pinned tab goes before a kept one
    CHECK(pickUnload({ T(9, false, false, true), T(3, false, false, true) }, true) == 1);
    CHECK(pickUnload({ T(9, false, false, true, kPlaying) }, true) == -1);
    // nothing kept: exactly the old order (exhaustive over small cases)
    {
        int mismatches = 0;
        for (int mask = 0; mask < (1 << 12); ++mask) {
            std::vector<TabState> v;
            for (int k = 0; k < 3; ++k) {
                const int bits = (mask >> (k * 4)) & 15;
                v.push_back(T(uint32_t((bits & 3) * 10 + k % 2), bits & 4, bits & 8, false, (bits & 3) == 3 ? kPlaying : kFree));
            }
            if (pickUnload(v, false) != oldPick(v) || pickUnload(v, true) != oldPick(v)) ++mismatches;
        }
        CHECK(mismatches == 0);
    }
    CHECK(allowKeptFor("shell memory low"));
    CHECK(allowKeptFor("new tab refused"));
    CHECK(!allowKeptFor("more tabs loaded than kept"));
    CHECK(!allowKeptFor("Memory panel"));
    CHECK(!allowKeptFor(""));

    // --- unload all
    {
        const std::vector<TabState> v = { T(1, false, false, false, kCurrent), T(2), T(3, true), T(4, false, false, true),
                                          T(5, false, false, false, kPlaying), T(6, false, false, false, kFree, false), T(7, false, true) };
        const std::vector<int> plan = unloadAllPlan(v);
        CHECK((plan == std::vector<int> { 1, 2, 6 }));
        CHECK(unloadAllPlan({}).empty());
        CHECK(unloadAllValue(0) == "Nothing to unload");
        CHECK(unloadAllValue(1) == "1 tab");
        CHECK(unloadAllValue(3) == "3 tabs");
        CHECK(unloadAllNotice(0) == "No background tab can be unloaded");
        CHECK(unloadAllNotice(1) == "Unloaded 1 background tab");
        CHECK(unloadAllNotice(2) == "Unloaded 2 background tabs");
    }

    // --- keep set: max 2, toggle, refuse, forget
    {
        int a = 0, b = 0, c = 0;
        std::vector<const void*> s;
        CHECK(toggleKeep(s, &a, true) == kKeepAdded);
        CHECK(kept(s, &a) && !kept(s, &b));
        CHECK(toggleKeep(s, &b, false) == kKeepRefused);
        CHECK(toggleKeep(s, &b, true) == kKeepAdded);
        CHECK(toggleKeep(s, &c, true) == kKeepFull);
        CHECK(s.size() == 2 && !kept(s, &c));
        CHECK(toggleKeep(s, &a, true) == kKeepRemoved);
        CHECK(toggleKeep(s, &c, true) == kKeepAdded);
        CHECK(toggleKeep(s, &c, false) == kKeepRemoved);   // releasing always works
        forget(s, &b);
        CHECK(s.empty());
        forget(s, &b);
        CHECK(s.empty());
        CHECK(std::string(keepNotice(kKeepFull)).find("Two tabs") == 0);
        CHECK(std::string(keepNotice(kKeepAdded)).size() > 0 && std::string(keepNotice(kKeepRefused)).size() > 0);
        CHECK(std::string(keepFace(true)) == "Don't keep loaded" && std::string(keepFace(false)) == "Keep loaded");
    }

    // --- texts
    CHECK(summary(812, 3, 9) == "Shell 812 MB \xc2\xb7 3 of 9 tabs loaded");
    CHECK(summary(-1, 1, 1) == "Shell memory unknown \xc2\xb7 1 of 1 tab loaded");
    CHECK(summary(0, 0, 4) == "Shell 0 MB \xc2\xb7 0 of 4 tabs loaded");
    CHECK(mbText(-3) == "0 MB");
    CHECK(detailLine(780, 48, 2, 12 * 1024) == "780 MB free \xc2\xb7 video 48 MB \xc2\xb7 text 12 MB");
    CHECK(detailLine(780, 48, 0, 100) == "780 MB free \xc2\xb7 text 0 MB");
    CHECK(detailLine(-1, 0, 0, 1536) == "text 2 MB");
    CHECK(rowLabel(true, "YouTube") == "\xe2\x97\x8f YouTube");
    CHECK(rowLabel(false, "News") == "\xe2\x97\x8b News");
    CHECK(rowValue(T(0, false, false, false, kCurrent)) == "Current");
    CHECK(rowValue(T(0, false, false, true, kCurrent)) == "Current, kept loaded");
    CHECK(rowValue(T(0, false, false, false, kFree, false)) == "Unloaded");
    CHECK(rowValue(T(0, false, false, true, kFree, false)) == "Unloaded");
    CHECK(rowValue(T(0, false, false, true)) == "Kept loaded");
    CHECK(rowValue(T(0)) == "Loaded");
    CHECK(rowValue(T(0, true)) == "Loaded, pinned");
    CHECK(rowValue(T(0, false, false, false, kPlaying)) == "Playing");
    CHECK(rowValue(T(0, false, false, false, kLoading)) == "Loading");
    CHECK(rowValue(T(0, false, false, false, kStopped)) == "Stopped");
    CHECK(rowValue(T(0, false, false, false, kMediaOwned)) == "Media");
    CHECK(rowValue(T(0, false, false, false, kNotWeb)) == "Loaded");
    CHECK(std::string(unloadRefusal(T(0))).empty());
    CHECK(std::string(unloadRefusal(T(0, false, false, false, kCurrent))) == "The tab you are viewing can't be unloaded");
    CHECK(std::string(unloadRefusal(T(0, false, false, false, kFree, false))) == "This tab is already unloaded");
    for (Block b : { kCurrent, kLoading, kStopped, kPlaying, kMediaOwned, kNotWeb }) CHECK(*unloadRefusal(T(0, false, false, false, b)) != 0);
    CHECK(std::string(kPerTabValue) == "Not readable");

    // --- refresh cadence (wrap-safe)
    CHECK(!refreshDue(1999, 0));
    CHECK(refreshDue(2000, 0));
    CHECK(refreshDue(5, 0xFFFFFFFFu - 2000));
    CHECK(!refreshDue(5, 0xFFFFFFFFu - 10));
    CHECK(kMaxKeep == 2 && kRefreshMs == 2000);

    if (failures) { std::printf("%d failure(s)\n", failures); return 1; }
    std::printf("all tab memory view tests passed\n");
    return 0;
}
