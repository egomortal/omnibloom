// OMNI_TAB_GROUP_SITE_V1: host tests for engine/entry/OmniTabGroupSite.h ("Group tabs by site": plan, order, limit, undo).
//   g++ -std=c++20 -Wall -Wextra -Werror -I<tree>/engine/entry test_tab_group_site.cpp -o t && ./t
#include "OmniTabGroupSite.h"
#include <cstdio>
#include <string>
#include <vector>

namespace S = OmniTabGroupSite;
namespace G = OmniTabGroups;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static S::In T(const char* url, bool priv = false, bool pinned = false, bool grouped = false)
{
    S::In i; i.url = url; i.priv = priv; i.pinned = pinned; i.grouped = grouped; return i;
}
static std::vector<size_t> V(std::initializer_list<size_t> l) { return std::vector<size_t>(l); }
// What omniTgNormalize does after apply: OmniTabGroups::order over the tabs (none pinned here).
static std::vector<size_t> normalized(const G::Model& m, const std::vector<const void*>& tabs, const std::vector<bool>& pinned)
{
    std::vector<int> pos;
    for (auto* t : tabs) pos.push_back(G::indexOf(m, G::groupOf(m, t)));
    return G::order(pinned, pos);
}

int main()
{
    // --- sites ---
    CHECK(S::siteOf("https://www.youtube.com/watch?v=1") == "youtube.com");
    CHECK(S::siteOf("https://m.youtube.com/") == "youtube.com");
    CHECK(S::siteOf("http://YouTube.com:8080/x") == "youtube.com");
    CHECK(S::siteOf("https://news.bbc.co.uk/a") == "bbc.co.uk");
    CHECK(S::siteOf("https://shop.example.com.au/") == "example.com.au");
    CHECK(S::siteOf("https://alice.github.io/p") == "alice.github.io");
    CHECK(S::siteOf("http://192.168.0.5/") == "192.168.0.5");
    CHECK(S::siteOf("http://localhost:3000/") == "localhost");
    CHECK(S::siteOf("https://example.com./") == "example.com");
    CHECK(S::siteOf("omni://tabs").empty() && S::siteOf("about:blank").empty() && S::siteOf("newtab").empty());
    CHECK(S::siteOf("file:///x").empty() && S::siteOf("").empty() && S::siteOf("https:///nohost").empty());
    CHECK(S::siteName("xn--bcher-kva.de") == "b\xc3\xbc" "cher.de");

    // --- plan: 2+ ungrouped tabs per site, first-appearance order, skips ---
    const std::vector<S::In> tabs = {
        T("https://www.youtube.com/a", false, true),   // 0 pinned: never
        T("https://news.bbc.co.uk/1"),                 // 1 bbc
        T("https://www.youtube.com/b"),                // 2 yt
        T("https://example.org/"),                     // 3 alone
        T("https://bbc.co.uk/2"),                      // 4 bbc
        T("https://youtube.com/c", true),              // 5 private: never
        T("https://m.youtube.com/d"),                  // 6 yt
        T("https://www.youtube.com/e", false, false, true),   // 7 manual group: never
        T("omni://start"),                             // 8 not web
        T("https://reddit.com/r/a", true),             // 9 private
        T("https://reddit.com/r/b", true),             // 10 private: two private tabs still don't group
    };
    S::Plan p = S::plan(tabs, 0);
    CHECK(p.sites.size() == 2 && p.left == 0 && p.room == G::kMaxGroups);
    CHECK(p.sites[0].site == "bbc.co.uk" && p.sites[0].tabs == V({ 1, 4 }));
    CHECK(p.sites[1].site == "youtube.com" && p.sites[1].tabs == V({ 2, 6 }));
    CHECK(p.tabCount() == 4);
    CHECK(S::rowValue(p) == "2 sites, 4 tabs");

    // nothing to do
    S::Plan none = S::plan({ T("https://a.com/"), T("https://b.com/"), T("https://a.com/x", true) }, 0);
    CHECK(none.sites.empty() && none.left == 0);
    CHECK(S::rowValue(none) == "No site has 2 ungrouped tabs" && S::emptyNotice(none) == "No site has 2 ungrouped tabs");

    // --- limit ---
    S::Plan lim = S::plan(tabs, G::kMaxGroups - 1);
    CHECK(lim.sites.size() == 1 && lim.left == 1 && lim.sites[0].site == "bbc.co.uk");
    CHECK(S::doneNotice(1, lim.left > 0) == "Grouped 1 site; group limit reached");
    S::Plan full = S::plan(tabs, G::kMaxGroups);
    CHECK(full.sites.empty() && full.left == 2 && full.room == 0);
    CHECK(S::rowValue(full) == "Group limit reached (8 of 8)");
    CHECK(S::emptyNotice(full) == "Grouped 0 sites; group limit reached");
    CHECK(S::plan(tabs, 99).room == 0);
    CHECK(S::doneNotice(4, false) == "Grouped 4 sites");

    // --- apply on a model: names, colours round-robin, relative order kept ---
    int objs[16] = {};
    std::vector<const void*> ptr;
    for (size_t i = 0; i < tabs.size(); ++i) ptr.push_back(&objs[i]);
    G::Model m;
    const int manual = G::create(m, "youtube.com", 0);   // a manual group with the site's name; tab 7 is in it
    G::add(m, ptr[7], manual);
    std::vector<int> ids = S::apply(m, p, ptr);
    CHECK(ids.size() == 2 && m.groups.size() == 3);
    CHECK(m.groups[1].name == "bbc.co.uk" && m.groups[2].name == "youtube.com (2)");
    CHECK(m.groups[1].colour == 1 && m.groups[2].colour == 2);   // next free colours (0 is the manual group's)
    CHECK(G::groupOf(m, ptr[1]) == ids[0] && G::groupOf(m, ptr[4]) == ids[0]);
    CHECK(G::groupOf(m, ptr[2]) == ids[1] && G::groupOf(m, ptr[6]) == ids[1]);
    CHECK(G::groupOf(m, ptr[7]) == manual && G::groupOf(m, ptr[0]) == 0 && G::groupOf(m, ptr[5]) == 0 && G::groupOf(m, ptr[9]) == 0);
    std::vector<bool> pinned(tabs.size(), false);
    pinned[0] = true;
    const std::vector<size_t> ord = normalized(m, ptr, pinned);
    // pinned 0 | manual: 7 | bbc: 1, 4 | youtube: 2, 6 | ungrouped 3, 5, 8, 9, 10 (each part keeps its order)
    CHECK(ord == V({ 0, 7, 1, 4, 2, 6, 3, 5, 8, 9, 10 }));

    // round-robin once every colour is used: 6 sites, then more
    {
        std::vector<S::In> many;
        const char* hosts[] = { "a.com", "b.com", "c.com", "d.com", "e.com", "f.com", "g.com", "h.com", "i.com" };
        for (const char* h : hosts) for (int k = 0; k < 2; ++k) many.push_back(T((std::string("https://") + h + "/" + std::to_string(k)).c_str()));
        S::Plan mp = S::plan(many, 0);
        CHECK(mp.sites.size() == size_t(G::kMaxGroups) && mp.left == 1);
        std::vector<int> o(many.size());
        std::vector<const void*> mptr;
        for (auto& x : o) mptr.push_back(&x);
        G::Model mm;
        const std::vector<int> mids = S::apply(mm, mp, mptr);
        CHECK(mids.size() == size_t(G::kMaxGroups) && int(mm.groups.size()) == G::kMaxGroups);
        for (int k = 0; k < G::kMaxGroups; ++k) CHECK(mm.groups[size_t(k)].colour == k % G::kColours);
        CHECK(mm.groups[0].name == "a.com" && mm.groups[7].name == "h.com");
        CHECK(S::plan(many, int(mm.groups.size())).sites.empty());
    }
    // a tab already grouped by the time apply runs is skipped; a group left empty is not kept
    {
        G::Model mm;
        int a = 0, b = 0;
        std::vector<const void*> two = { &a, &b };
        S::Plan tp = S::plan({ T("https://x.com/1"), T("https://x.com/2") }, 0);
        const int other = G::create(mm, "Other", 0);
        G::add(mm, &a, other); G::add(mm, &b, other);
        CHECK(S::apply(mm, tp, two).empty() && mm.groups.size() == 1);
    }

    // --- undo ---
    S::Undo u;
    u.ids = ids; u.order = ptr; u.at = 1000; u.sites = int(ids.size()); u.armed = true;
    CHECK(S::undoable(u, m, 1000) && S::undoable(u, m, 1000 + S::kUndoMs - 1) && !S::undoable(u, m, 1000 + S::kUndoMs));
    CHECK(S::secondsLeft(u, 1000) == 30 && S::secondsLeft(u, 1000 + 7500) == 23 && S::secondsLeft(u, 1000 + 40000) == 0);
    CHECK(S::undoValue(2, 23) == "Grouped 2 sites, 23 s left");
    {   // tick wrap: still measured as elapsed time
        S::Undo w = u; w.at = 0xFFFFF000u;
        CHECK(S::undoable(w, m, 0x00000100u));
    }
    {   // the groups were removed by hand: nothing left to undo
        G::Model mm = m;
        for (int id : ids) G::ungroup(mm, id);
        CHECK(!S::undoable(u, mm, 2000));
    }
    const int removed = S::undo(m, u);
    CHECK(removed == 2 && !u.armed && !S::undoable(u, m, 1001));
    CHECK(m.groups.size() == 1 && m.groups[0].id == manual && G::groupOf(m, ptr[7]) == manual);
    for (size_t i : { 1, 2, 4, 6 }) CHECK(G::groupOf(m, ptr[i]) == 0);

    // order restore: the earlier order, tabs opened since after them, closed ones gone
    {
        int x = 0, y = 0, z = 0, n1 = 0;
        const std::vector<const void*> before = { &x, &y, &z };
        const std::vector<const void*> now = { &z, &n1, &x };   // y closed, n1 new
        CHECK(S::restoreOrder(now, before) == V({ 2, 0, 1 }));
        CHECK(S::restoreOrder({}, before).empty());
        CHECK(S::restoreOrder(now, {}) == V({ 0, 1, 2 }));
    }
    CHECK(std::string(S::label()) == "Group tabs by site" && std::string(S::undoLabel()) == "Undo grouping");
    CHECK(S::kRowId < 7530 || S::kRowId > 7538);

    printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "ok", checks, fails);
    return fails ? 1 : 0;
}
