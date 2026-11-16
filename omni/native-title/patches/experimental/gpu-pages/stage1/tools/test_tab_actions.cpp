// OMNI_TAB_ACTIONS_V1: host tests for engine/entry/OmniTabActions.h (the pure part of the Tabs panel's tab actions).
//   g++ -std=c++20 -Wall -Wextra -Werror -I<tree>/engine/entry test_tab_actions.cpp -o t && ./t
#include "OmniTabActions.h"
#include <cstdio>
#include <string>
#include <vector>

namespace A = OmniTabActions;
namespace G = OmniTabGroups;
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static A::Info P() { A::Info i; i.pinned = true; return i; }
static A::Info Gr(int g) { A::Info i; i.group = g; return i; }
static A::Info U(bool priv = false, bool unloaded = false) { A::Info i; i.priv = priv; i.unloaded = unloaded; return i; }
// What omniTgNormalize would do: OmniTabGroups::order over the same tabs.
static bool normalizeKeeps(const std::vector<A::Info>& t)
{
    std::vector<bool> pinned;
    std::vector<int> pos;
    for (auto& i : t) { pinned.push_back(i.pinned); pos.push_back(i.group); }
    return G::isIdentity(G::order(pinned, pos));
}
static bool contains(const std::string& s, const std::string& part) { return s.find(part) != std::string::npos; }

int main()
{
    // pinned 0,1 | group 0: 2,3,4 | group 1: 5 | ungrouped 6 (private), 7, 8 (unloaded)
    const std::vector<A::Info> tabs = { P(), P(), Gr(0), Gr(0), Gr(0), Gr(1), U(true), U(), U(false, true) };
    CHECK(A::ordered(tabs) && normalizeKeeps(tabs));
    {   // ordered() agrees with OmniTabGroups::order
        const std::vector<A::Info> bad = { Gr(0), P(), U() };
        CHECK(!A::ordered(bad) && !normalizeKeeps(bad));
        const std::vector<A::Info> bad2 = { Gr(1), Gr(0) };
        CHECK(!A::ordered(bad2) && !normalizeKeeps(bad2));
    }

    // --- blocks / move targets
    CHECK(A::block(tabs, 0).first == 0 && A::block(tabs, 0).last == 1);
    CHECK(A::block(tabs, 3).first == 2 && A::block(tabs, 3).last == 4);
    CHECK(A::block(tabs, 5).first == 5 && A::block(tabs, 5).last == 5);
    CHECK(A::block(tabs, 7).first == 6 && A::block(tabs, 7).last == 8);
    CHECK(A::moveTarget(tabs, 0, A::kLeft) == -1 && A::moveTarget(tabs, 0, A::kRight) == 1);
    CHECK(A::moveTarget(tabs, 1, A::kRight) == -1);           // a pinned tab never leaves the pinned tabs
    CHECK(A::moveTarget(tabs, 2, A::kLeft) == -1);            // the group's first tab can't move into the pinned tabs
    CHECK(A::moveTarget(tabs, 4, A::kRight) == -1);           // nor its last into the next group
    CHECK(A::moveTarget(tabs, 4, A::kStart) == 2 && A::moveTarget(tabs, 2, A::kEnd) == 4);
    CHECK(A::moveTarget(tabs, 5, A::kLeft) == -1 && A::moveTarget(tabs, 5, A::kEnd) == -1);   // alone in its group
    CHECK(A::moveTarget(tabs, 6, A::kLeft) == -1 && A::moveTarget(tabs, 6, A::kEnd) == 8);
    CHECK(A::moveTarget(tabs, 99, A::kLeft) == -1);
    CHECK(std::string(A::cantMove(tabs, 1, A::kRight)) == "Last pinned tab");
    CHECK(std::string(A::cantMove(tabs, 2, A::kLeft)) == "First in its group");
    CHECK(std::string(A::cantMove(tabs, 6, A::kStart)) == "Already first");
    CHECK(A::positionText(tabs, 1) == "2 of 2 pinned");
    CHECK(A::positionText(tabs, 3) == "2 of 3 in the group");
    CHECK(A::positionText(tabs, 7) == "2 of 3");
    // every possible move keeps the order omniTgNormalize wants (so it never undoes one)
    for (size_t i = 0; i < tabs.size(); ++i)
        for (A::Move m : { A::kLeft, A::kRight, A::kStart, A::kEnd }) {
            const int to = A::moveTarget(tabs, i, m);
            if (to < 0) continue;
            std::vector<A::Info> t = tabs;
            const A::Info moved = t[i];
            A::moveItem(t, i, size_t(to));
            CHECK(A::ordered(t) && normalizeKeeps(t));
            CHECK(t[size_t(to)].pinned == moved.pinned && t[size_t(to)].group == moved.group && t[size_t(to)].priv == moved.priv);
        }
    {   // moveItem keeps the others' order
        std::vector<int> v = { 0, 1, 2, 3, 4 };
        A::moveItem(v, 1, 3); CHECK((v == std::vector<int> { 0, 2, 3, 1, 4 }));
        A::moveItem(v, 3, 0); CHECK((v == std::vector<int> { 1, 0, 2, 3, 4 }));
        A::moveItem(v, 0, 9); CHECK((v == std::vector<int> { 1, 0, 2, 3, 4 }));   // out of range: nothing
    }

    // --- close other tabs / tabs to the right: never the kept tab, never a pinned tab
    {
        const auto others = A::closeSet(tabs, 3, A::kCloseOthers);
        CHECK((others == std::vector<size_t> { 2, 4, 5, 6, 7, 8 }));
        CHECK(A::pinnedSpared(tabs, 3, A::kCloseOthers) == 2);
        CHECK(A::privateIn(tabs, others) == 1);
        const auto right = A::closeSet(tabs, 3, A::kCloseRight);
        CHECK((right == std::vector<size_t> { 4, 5, 6, 7, 8 }));
        CHECK(A::pinnedSpared(tabs, 3, A::kCloseRight) == 0);
        CHECK((A::closeSet(tabs, 0, A::kCloseRight) == std::vector<size_t> { 2, 3, 4, 5, 6, 7, 8 }));   // from a pinned tab
        CHECK(A::pinnedSpared(tabs, 0, A::kCloseRight) == 1 && A::pinnedSpared(tabs, 0, A::kCloseOthers) == 1);
        CHECK(A::closeSet(tabs, 8, A::kCloseRight).empty());
        const std::vector<A::Info> onlyPinned = { P(), P(), U() };
        CHECK(A::closeSet(onlyPinned, 2, A::kCloseOthers).empty() && A::pinnedSpared(onlyPinned, 2, A::kCloseOthers) == 2);
        CHECK(A::closeValue(0, 2, A::kCloseOthers) == "Only pinned tabs");
        CHECK(A::closeValue(0, 0, A::kCloseRight) == "None to the right");
        CHECK(A::closeValue(6, 2, A::kCloseOthers) == "6 tabs (2 pinned stay)");
        CHECK(A::closeValue(1, 0, A::kCloseOthers) == "1 tab");
        CHECK(A::askTitle(6, A::kCloseOthers) == "Close 6 tabs?");
        CHECK(A::askTitle(1, A::kCloseRight) == "Close 1 tab to the right?");
        CHECK(contains(A::askMessage(2, 1), "Pinned tabs are never closed this way (2 stay open)."));
        CHECK(contains(A::askMessage(1, 0), "(1 stays open)."));
        CHECK(contains(A::askMessage(0, 0), "Pinned tabs are never closed this way."));   // said even with none pinned
        CHECK(contains(A::askMessage(0, 0), "Reopen closed tab") && !contains(A::askMessage(0, 0), "private"));
        CHECK(contains(A::askMessage(0, 3), "not private ones"));
        CHECK(A::askOk(6) == "Close 6 tabs");
        CHECK(A::closedNotice(3, 2) == "Closed 3 tabs; 2 pinned tabs stay");
        CHECK(A::closedNotice(1, 0) == "Closed 1 tab");
    }

    // --- duplicate: right after the original, inside its block; private stays private; the tab limit
    {
        CHECK(A::canDuplicate(3, 4) && !A::canDuplicate(4, 4) && !A::canDuplicate(5, 4));
        CHECK(A::limitText(4, 4) == "Tab limit reached (4 of 4)");
        CHECK(A::duplicateInfo(U(true)).priv && A::duplicateInfo(U(true)).group == -1);
        CHECK(!A::duplicateInfo(U()).priv);
        CHECK(A::duplicateInfo(Gr(1)).group == 1 && !A::duplicateInfo(P()).pinned && A::duplicateInfo(P()).group == -1);
        CHECK(A::duplicateIndex(tabs, 3) == 4);   // grouped: next to it, in the group
        CHECK(A::duplicateIndex(tabs, 6) == 7);   // private: next to it
        CHECK(A::duplicateIndex(tabs, 0) == 6);   // pinned: first among the ungrouped tabs (after the groups)
        CHECK(A::duplicateIndex({ P(), U() }, 0) == 1);
        CHECK(A::duplicateIndex({ P(), P() }, 1) == 2);
        CHECK(A::duplicateIndex(tabs, 99) == tabs.size());
        for (size_t s = 0; s < tabs.size(); ++s) {   // the copy never needs omniTgNormalize to move it
            std::vector<A::Info> t = tabs;
            const size_t at = A::duplicateIndex(tabs, s);
            t.insert(t.begin() + std::ptrdiff_t(at), A::duplicateInfo(tabs[s]));
            CHECK(A::ordered(t) && normalizeKeeps(t));
            CHECK(t[at].priv == tabs[s].priv && !t[at].pinned);
        }
        CHECK(A::duplicateNotice(true) == "Duplicated as a private tab");
    }

    // --- reload all: the loaded tabs
    CHECK((A::reloadSet(tabs) == std::vector<size_t> { 0, 1, 2, 3, 4, 5, 6, 7 }));
    CHECK(A::reloadNotice(8, 1) == "Reloading 8 tabs (1 unloaded: it loads when shown)");
    CHECK(A::reloadNotice(1, 0) == "Reloading 1 tab");

    // --- bookmark all: private, non-web, already bookmarked, repeats skipped; the cap
    {
        auto C = [](const char* url, bool priv, bool web, bool bm) { A::Candidate c; c.url = url; c.priv = priv; c.web = web; c.bookmarked = bm; return c; };
        const std::vector<A::Candidate> c = { C("https://a/", false, true, false), C("https://p/", true, true, false),
                                             C("omni://pages/newtab", false, false, false), C("https://b/", false, true, true),
                                             C("https://a/", false, true, false), C("https://c/", false, true, false) };
        const A::BookmarkPlan p = A::bookmarkPlan(c, 500);
        CHECK((p.add == std::vector<size_t> { 0, 5 }));
        CHECK(p.priv == 1 && p.notWeb == 1 && p.already == 1 && p.repeated == 1 && p.overCap == 0);
        CHECK(A::bookmarkValue(p) == "2 tabs");
        CHECK(A::bookmarkNotice(p, "Tabs 16 Nov 2026") == "Bookmarked 2 tabs in \"Tabs 16 Nov 2026\"; skipped 1 private, 1 already bookmarked");
        const A::BookmarkPlan q = A::bookmarkPlan(c, 1);
        CHECK((q.add == std::vector<size_t> { 0 }) && q.overCap == 1);
        const A::BookmarkPlan none = A::bookmarkPlan(c, 0);
        CHECK(none.add.empty() && A::bookmarkValue(none) == "Bookmarks are full (500)");
        CHECK(A::bookmarkNotice(none, "").find("full") != std::string::npos);
        const A::BookmarkPlan priv = A::bookmarkPlan({ C("https://p/", true, true, false) }, 500);
        CHECK(priv.add.empty() && A::bookmarkNotice(priv, "") == "Private tabs are not bookmarked" && A::bookmarkValue(priv) == "No tabs to bookmark");
        const A::BookmarkPlan dup = A::bookmarkPlan({ C("https://b/", false, true, true) }, 500);
        CHECK(A::bookmarkValue(dup) == "Already bookmarked");
    }
    {   // the folder: new, named after the date, unique, within the bookmarks manager's 40 bytes
        CHECK(A::folderName("Tabs 16 Nov 2026", {}) == "Tabs 16 Nov 2026");
        CHECK(A::folderName("Tabs 16 Nov 2026", { "Tabs 16 Nov 2026" }) == "Tabs 16 Nov 2026 (2)");
        CHECK(A::folderName("Tabs 16 Nov 2026", { "Tabs 16 Nov 2026", "Tabs 16 Nov 2026 (2)" }) == "Tabs 16 Nov 2026 (3)");
        const std::string longBase(60, 'x');
        const std::string f1 = A::folderName(longBase, {});
        CHECK(f1.size() == OmniBookmarksModel::kFolderMax);
        const std::string f2 = A::folderName(longBase, { f1 });
        CHECK(f2.size() <= OmniBookmarksModel::kFolderMax && f2 != f1 && f2.find(" (2)") != std::string::npos);
        CHECK(A::folderName("  \t ", {}) == "Tabs");
        // as stored: the name survives the bookmarks file round trip
        OmniBookmarksModel::Entry e { "https://a/", "A", A::folderName("Tabs 16 Nov 2026", {}) };
        const auto back = OmniBookmarksModel::parse(OmniBookmarksModel::serializeLine(e));
        CHECK(back.size() == 1 && back[0].folder == "Tabs 16 Nov 2026");
    }

    // --- menu rows: their own ids, clear of the group menu's 1..3 / 10..17
    CHECK(A::isRow(A::kRowDuplicate) && A::isRow(A::kRowBookmarkAll) && !A::isRow(1) && !A::isRow(17) && !A::isRow(A::kRowBookmarkAll + 1));
    CHECK(A::kRowBookmarkAll - A::kRowDuplicate == 8);

    printf("%s: %d checks, %d failed\n", fails ? "FAIL" : "ok", checks, fails);
    return fails ? 1 : 0;
}
