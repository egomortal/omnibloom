// OMNI_TAB_GROUPS_V1: host tests for engine/entry/OmniTabGroups.h (the pure part of tab groups) and the "group" lines
// added to OmniTabSessions.h (sessions.txt).
//   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_tab_groups.cpp -o t && ./t
#include "OmniTabGroups.h"
#include "OmniTabSessions.h"
#include "OmniPinnedTabs.h"   // OMNI_TAB_GROUPS_V1_R2: restoreFlags (the start-up restore order)
#include <algorithm>
#include <cstdio>
#include <string>
#include <vector>

namespace G = OmniTabGroups;
namespace TS = OmniTabSessions;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static int tabsStore[32];
static const void* T(int i) { return &tabsStore[i]; }

int main()
{
    // --- checks / caps
    CHECK(G::canJoin(false, false) == G::kOk);
    CHECK(G::canJoin(true, false) == G::kPrivate);
    CHECK(G::canJoin(true, true) == G::kPrivate);   // private wins
    CHECK(G::canJoin(false, true) == G::kPinned);
    CHECK(G::canCreate(false, false, 7) == G::kOk);
    CHECK(G::canCreate(false, false, 8) == G::kFull);
    CHECK(G::canCreate(true, false, 8) == G::kPrivate);
    CHECK(G::refusal(G::kPrivate) == "Private tabs can't join groups");
    CHECK(G::refusal(G::kFull).find("8 groups") == 0);
    CHECK(G::refusal(G::kOk).empty());

    // --- names / colours
    {
        G::Model m;
        CHECK(G::defaultName(m) == "Group 1");
        const int a = G::create(m, G::defaultName(m), G::nextColour(m));
        CHECK(a && m.groups[0].name == "Group 1" && m.groups[0].colour == 0);
        G::add(m, T(0), a);
        CHECK(G::defaultName(m) == "Group 2");
        CHECK(G::nextColour(m) == 1);
        const int b = G::create(m, "group 1", 3);   // same name, other case: made unique
        G::add(m, T(1), b);
        CHECK(m.groups[1].name == "group 1 (2)");
        CHECK(G::nextColour(m) == 1);
        CHECK(G::rename(m, b, "  Work\tstuff \n"));
        CHECK(m.groups[1].name == "Work stuff");
        CHECK(!G::rename(m, b, "   "));
        CHECK(m.groups[1].name == "Work stuff");
        CHECK(G::rename(m, b, "GROUP 1") && m.groups[1].name == "GROUP 1 (2)");
        CHECK(G::rename(m, a, std::string(100, 'x')) && m.groups[0].name.size() == G::kNameMax);
        CHECK(G::stepColour(m, a, -1) == 5 && G::stepColour(m, a, 1) == 0 && G::stepColour(m, a, 7) == 1);
        CHECK(std::string(G::colourName(5)) == "Purple" && std::string(G::colourName(-1)) == "Purple");
        CHECK(G::cleanName("", "Group 3") == "Group 3");
        // UTF-8 never split
        const std::string u = G::cleanName(std::string(39, 'a') + "\xc3\xa9", "x");
        CHECK(u == std::string(39, 'a'));
    }

    // --- membership, caps, empty groups go
    {
        G::Model m;
        int ids[9] = {};
        for (int i = 0; i < 8; ++i) { ids[i] = G::create(m, "", G::nextColour(m)); G::add(m, T(i), ids[i]); }
        CHECK(int(m.groups.size()) == 8);
        CHECK(G::create(m, "Nine", 0) == 0);   // max 8
        CHECK(m.groups[6].colour == 0 && m.groups[7].colour == 1);   // six colours, then round again
        CHECK(G::groupOf(m, T(3)) == ids[3]);
        CHECK(G::add(m, T(3), ids[0]));             // moves: group 4 is empty and goes
        CHECK(int(m.groups.size()) == 7 && G::count(m, ids[0]) == 2 && G::indexOf(m, ids[3]) < 0);
        CHECK(!G::add(m, T(20), 12345));            // no such group
        CHECK(G::remove(m, T(0)) == ids[0] && G::count(m, ids[0]) == 1);
        CHECK(G::remove(m, T(0)) == 0);
        CHECK(G::remove(m, T(3)) == ids[0] && G::indexOf(m, ids[0]) < 0);   // its last tab left
        CHECK(int(m.groups.size()) == 6);
        CHECK(G::ungroup(m, ids[1]) == 1 && G::groupOf(m, T(1)) == 0 && int(m.groups.size()) == 5);
        CHECK(!G::toggleCollapsed(m, 999));
        CHECK(G::toggleCollapsed(m, ids[2]) && G::collapsedTab(m, T(2)) && !G::collapsedTab(m, T(4)));
        CHECK(!G::toggleCollapsed(m, ids[2]) && !G::collapsedTab(m, T(2)));
        // prune: tab 2 closed / became pinned, tab 5 private
        G::prune(m, { T(4), T(6), T(7) });
        CHECK(G::groupOf(m, T(2)) == 0 && G::groupOf(m, T(5)) == 0 && int(m.groups.size()) == 3);
        // the next "Group N" fills the lowest free number
        CHECK(G::defaultName(m) == "Group 1");
    }

    // --- order: pinned, groups (display order), ungrouped; stable
    {
        //            0      1      2     3      4     5      6
        std::vector<bool> pin { false, true, false, false, true, false, false };
        std::vector<int> gp   { 1,    -1,    -1,    0,   -1,    1,    0 };
        auto o = G::order(pin, gp);
        CHECK((o == std::vector<size_t> { 1, 4, 3, 6, 0, 5, 2 }));
        CHECK(!G::isIdentity(o));
        std::vector<bool> pin2 { true, false, false, false };
        CHECK(G::isIdentity(G::order(pin2, { -1, 0, 0, -1 })));
        CHECK(G::isIdentity(G::order(pin2, {})));   // no groups: nothing moves
        // pinned with a stale group: pinned wins
        CHECK((G::order({ false, true }, { -1, 0 }) == std::vector<size_t> { 1, 0 }));
    }

    // --- panel rows
    {
        // tabs: pinned(0), group0 (1,2), group1 (3), ungrouped (4)
        std::vector<int> gp { -1, 0, 0, 1, -1 };
        auto r = G::panelRows(gp, { false, false });
        CHECK((r == std::vector<int> { 0, -1, 1, 2, -2, 3, 4 }));
        r = G::panelRows(gp, { true, false });
        CHECK((r == std::vector<int> { 0, -1, -2, 3, 4 }));
        r = G::panelRows(gp, { true, true });
        CHECK((r == std::vector<int> { 0, -1, -2, 4 }));
        CHECK((G::panelRows({ -1, -1 }, {}) == std::vector<int> { 0, 1 }));
    }

    // --- unload order: pinned rule first, then collapsed, then oldest
    CHECK(G::unloadsBefore(false, false, 50, true, true, 1));    // unpinned before pinned (even collapsed)
    CHECK(!G::unloadsBefore(true, true, 1, false, false, 50));
    CHECK(G::unloadsBefore(false, true, 90, false, false, 10));  // collapsed first
    CHECK(!G::unloadsBefore(false, false, 10, false, true, 90));
    CHECK(G::unloadsBefore(false, false, 10, false, false, 90)); // then least recently shown
    CHECK(G::unloadsBefore(true, true, 10, true, false, 90));    // among pinned: collapsed flag still orders

    // --- session lines
    {
        const std::string p = G::payload(2, 4, true, "Work\tstuff");
        CHECK(p == "2\t4\t1\tWork stuff");
        const std::string l = G::line(5, p);
        CHECK(l == "group\t5\t2\t4\t1\tWork stuff\n");
        G::Mark k;
        CHECK(G::parseLine(l, k) && k.index == 5 && k.group == 2 && k.colour == 4 && k.collapsed && k.name == "Work stuff");
        CHECK(G::parseLine("group\t5\t2\t4\t1\tWork stuff\r\n", k) && k.name == "Work stuff");
        CHECK(G::parseLine("group\t0\t0\t9\t0\t", k) && k.colour == 3 && k.name == "Group 1");   // colour wraps, empty name
        CHECK(!G::parseLine("group\tx\t0\t0\t0\tA", k));
        CHECK(!G::parseLine("group\t1\t0\t0\t2\tA", k));
        CHECK(!G::parseLine("group\t1\t0\t0", k));
        CHECK(!G::parseLine("group\t12345\t0\t0\t0\tA", k));
        CHECK(!G::parseLine("pinned\t1", k));
        CHECK(!G::parseLine("tab\thttps://a/\tA", k));
        CHECK(G::parsePayload("1\t0\t0\tNews", k) && k.group == 1 && k.name == "News");
        CHECK(!G::parsePayload("garbage", k));
    }

    // --- restore (session.txt at start-up; a session opened)
    {
        G::Model m;
        std::vector<const void*> tabs { T(0), T(1), T(2), T(3), T(4), T(5) };
        std::vector<bool> ok { true, true, true, false, true, true };   // 3 private
        std::vector<G::Mark> marks;
        auto mk = [](int index, int g, int c, bool col, const char* n) { G::Mark k; k.index = index; k.group = g; k.colour = c; k.collapsed = col; k.name = n; return k; };
        marks.push_back(mk(1, 0, 2, false, "Work"));
        marks.push_back(mk(2, 0, 2, false, "Work"));
        marks.push_back(mk(3, 1, 1, true, "Fun"));     // private: skipped
        marks.push_back(mk(4, 1, 1, true, "Fun"));
        marks.push_back(mk(4, 0, 2, false, "Work"));   // listed twice: first wins
        marks.push_back(mk(9, 0, 2, false, "Work"));   // no such tab
        CHECK(G::restore(m, marks, tabs, ok) == 3);
        CHECK(int(m.groups.size()) == 2 && m.groups[0].name == "Work" && m.groups[1].name == "Fun" && m.groups[1].collapsed);
        CHECK(G::groupOf(m, T(4)) == m.groups[1].id && G::groupOf(m, T(3)) == 0);
        // a session opened later: same name joins, a new one is made
        std::vector<const void*> more { T(10), T(11) };
        CHECK(G::restore(m, { mk(0, 0, 5, false, "work"), mk(1, 3, 0, false, "Recipes") }, more, { true, true }) == 2);
        CHECK(int(m.groups.size()) == 3 && G::count(m, m.groups[0].id) == 3 && m.groups[2].name == "Recipes");
        // past 8 groups the tabs stay ungrouped
        G::Model f;
        std::vector<const void*> many;
        std::vector<bool> all;
        std::vector<G::Mark> ms;
        for (int i = 0; i < 10; ++i) { many.push_back(T(i)); all.push_back(true); ms.push_back(mk(i, i, i, false, ("G" + std::to_string(i)).c_str())); }
        CHECK(G::restore(f, ms, many, all) == 8 && int(f.groups.size()) == 8 && G::groupOf(f, T(9)) == 0);
    }

    // --- start-up restore order (OMNI_TAB_GROUPS_V1_R2). session.txt: tab 0 "pinned\t0", tab 1 "group\t1\t0\t3\t0\tG",
    // tab 2 plain; both kinds of line index the tabs in FILE order. This replays omniEverydayStart's three steps with
    // the pure parts the shell uses (omniTgRestoreApply = restore; omniPtRestoreApply = restoreFlags on the current
    // order + pinned first; omniTgNormalize = prune pinned / closed, then order). r1 normalized right after restore,
    // i.e. before the pins were applied.
    {
        auto mk = [](int index, int g, int c, bool col, const char* n) { G::Mark k; k.index = index; k.group = g; k.colour = c; k.collapsed = col; k.name = n; return k; };
        const std::vector<G::Mark> marks { mk(1, 0, 3, false, "G") };
        const std::vector<int> pinIdx { 0 };
        struct Out { std::vector<const void*> tabs, pinned; G::Model m; int sel = 0; };
        auto run = [&](bool r1, int sel0) {
            Out o;
            o.tabs = { T(0), T(1), T(2) };
            o.sel = sel0;
            auto isPinned = [&o](const void* p) { return std::find(o.pinned.begin(), o.pinned.end(), p) != o.pinned.end(); };
            auto normalize = [&]() {   // omniTgNormalize
                std::vector<const void*> keep;
                for (const void* p : o.tabs) if (!isPinned(p)) keep.push_back(p);
                G::prune(o.m, keep);
                if (o.m.groups.empty()) return;
                std::vector<bool> pin;
                std::vector<int> pos;
                for (const void* p : o.tabs) { pin.push_back(isPinned(p)); pos.push_back(G::indexOf(o.m, G::groupOf(o.m, p))); }
                std::vector<const void*> next;
                for (size_t i : G::order(pin, pos)) next.push_back(o.tabs[i]);
                o.tabs = next;
            };
            auto follow = [&o](const void* shown) { for (size_t i = 0; i < o.tabs.size(); ++i) if (o.tabs[i] == shown) o.sel = int(i); };
            // 1. omniTgRestoreApply
            G::restore(o.m, marks, o.tabs, std::vector<bool>(o.tabs.size(), true));
            if (r1) { const void* shown = o.tabs[size_t(o.sel)]; normalize(); follow(shown); }
            // 2. omniPtRestoreApply
            const std::vector<bool> flags = OmniPinnedTabs::restoreFlags(pinIdx, std::vector<bool>(o.tabs.size(), true));
            for (size_t i = 0; i < o.tabs.size(); ++i) if (flags[i]) o.pinned.push_back(o.tabs[i]);
            { const void* shown = o.tabs[size_t(o.sel)]; std::stable_partition(o.tabs.begin(), o.tabs.end(), isPinned); follow(shown); }
            // 3. r2: the order once, `sel` follows its tab
            if (!r1) { const void* shown = o.tabs[size_t(o.sel)]; normalize(); follow(shown); }
            return o;
        };
        const Out r2 = run(false, 1);   // "selected\t1": the grouped tab was shown
        CHECK(r2.pinned.size() == 1 && r2.pinned[0] == T(0));                                  // tab 0 still pinned
        CHECK(r2.m.groups.size() == 1 && r2.m.groups[0].name == "G" && r2.m.groups[0].colour == 3);
        CHECK(G::groupOf(r2.m, T(1)) == r2.m.groups[0].id && G::count(r2.m, r2.m.groups[0].id) == 1);   // tab 1 still in G
        CHECK(G::groupOf(r2.m, T(0)) == 0 && G::groupOf(r2.m, T(2)) == 0);
        CHECK((r2.tabs == std::vector<const void*> { T(0), T(1), T(2) }));                   // pinned, G, ungrouped
        CHECK(r2.sel == 1 && r2.tabs[size_t(r2.sel)] == T(1));
        // what r1 did (kept as the regression): the grouped tab moved to the front first, so "pinned\t0" pinned it and
        // the pin then took it out of its group at the next omniTgNormalize (pinned tabs are not eligible; the group
        // went, and that layout was saved next).
        const Out r1 = run(true, 1);
        CHECK(r1.pinned.size() == 1 && r1.pinned[0] == T(1));
        {
            G::Model next = r1.m;
            G::prune(next, { T(0), T(2) });   // the eligible (unpinned) tabs
            CHECK(next.groups.empty() && G::groupOf(next, T(1)) == 0);
        }
        // the pinned tab was shown: same layout, `sel` stays on it
        const Out again = run(false, 0);
        CHECK(again.tabs == r2.tabs && again.pinned == r2.pinned && again.sel == 0);
    }

    // --- texts
    CHECK(G::headerValue(1, false, false) == "1 tab");
    CHECK(G::headerValue(3, true, false) == "3 tabs \xc2\xb7 collapsed");
    CHECK(G::headerValue(3, true, true).find("current tab inside") != std::string::npos);
    CHECK(G::ungroupNotice("Work", 1) == "Ungrouped \"Work\": its tab stays open");
    CHECK(G::ungroupNotice("Work", 3) == "Ungrouped \"Work\": its 3 tabs stay open");
    CHECK(G::newNotice("Group 1", 1) == "New group \"Group 1\" (1 of 8)");

    // --- sessions.txt: the "group" line rides with its tab and survives a round trip; old files / old readers
    {
        std::vector<TS::Candidate> c {
            { "https://a.com/", "A", false, false, G::payload(0, 2, false, "Work") },
            { "https://p.com/", "P", true, false, G::payload(0, 2, false, "Work") },   // private: never saved
            { "https://b.com/", "B", false, false, "" },
            { "https://a.com/", "A2", false, false, G::payload(1, 1, false, "Dup") },   // duplicate URL: dropped
            { "https://c.com/", "C", false, false, G::payload(1, 1, true, "Fun") },
        };
        auto tabs = TS::collect(c, 8);
        CHECK(tabs.size() == 3 && tabs[0].group == "0\t2\t0\tWork" && tabs[1].group.empty() && tabs[2].group == "1\t1\t1\tFun");
        std::vector<TS::Session> list;
        CHECK(TS::save(list, "S", tabs, 100) == TS::kAdded);
        const std::string text = TS::serialize(list);
        CHECK(text.find("tab\thttps://a.com/\tA\ngroup\t0\t0\t2\t0\tWork\ntab\thttps://b.com/\tB\ntab\thttps://c.com/\tC\ngroup\t2\t1\t1\t1\tFun\n") != std::string::npos);
        auto back = TS::parse(text);
        CHECK(back.size() == 1 && back[0].tabs.size() == 3 && back[0].tabs[0].group == "0\t2\t0\tWork" && back[0].tabs[1].group.empty() && back[0].tabs[2].group == "1\t1\t1\tFun");
        CHECK(TS::serialize(back) == text);
        // a "group" line naming another tab (its tab line was bad) is ignored
        auto odd = TS::parse("omni-sessions\t1\nsession\t1\tX\ntab\thttps://a.com/\tA\ntab\tftp://bad\tB\ngroup\t1\t0\t0\t0\tW\ngroup\tx\t0\t0\t0\tW\ngroup\t0\t0\t0\t0\tOK\n");
        CHECK(odd.size() == 1 && odd[0].tabs.size() == 1 && odd[0].tabs[0].group == "0\t0\t0\tOK");
        // a file from before groups parses as before
        auto old = TS::parse("omni-sessions\t1\nsession\t5\tOld\ntab\thttps://a.com/\tA\n");
        CHECK(old.size() == 1 && old[0].tabs[0].group.empty());
        // what an old reader does: it knows only "session" / "tab" lines, so it gets the same tabs
        size_t tabLines = 0, pos = 0;
        while ((pos = text.find("\ntab\t", pos)) != std::string::npos) { ++tabLines; ++pos; }
        CHECK(tabLines == 3);
    }

    printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
