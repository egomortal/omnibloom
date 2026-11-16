#!/usr/bin/env python3
"""OMNI_TAB_ACTIONS_V1 (2026-11-16): classic tab actions on a Tabs panel tab row.

What the user sees
  - Tabs panel (OmniTabsPage.h): hold Cross on a tab row opens the tab menu (OMNI_TAB_GROUPS_V1's "Tab group" menu,
    now titled "Tab"): the group rows as before, then
        Duplicate tab          the same page in a new tab right after it (a private tab's copy is private; a grouped
                               tab's copy joins the group; a pinned tab's copy is not pinned and goes first among the
                               ungrouped tabs). Off at the tab limit: "Tab limit reached (4 of 4)"; the memory guard
                               (newTab / omniF3TabAllowed) can still refuse, and says why.
        Move left / right      one place; the menu stays open (press again); the value shows "2 of 5" / "2 of 3 in
                               the group" / "2 of 3 pinned".
        Move to the start / end
                               A move stays inside the tab's block: pinned tabs first, then each group, then the
                               ungrouped tabs (OmniTabGroups' order). Rows that can't move are off ("Already first",
                               "First in its group", "Last pinned tab" ...).
        Close other tabs       every tab but this one and the pinned tabs
        Close tabs to the right  the unpinned tabs after this one
                               Both ask once (omniAsk): "Close 3 tabs?" / "Close 2 tabs to the right?", saying pinned
                               tabs are never closed this way (and how many stay) and that closed tabs go to Reopen
                               closed tab (the last 10, not private ones: omniFxTabClosing as for any close).
        Reload all tabs        the loaded tabs (an unloaded one loads when it is shown)
        Bookmark all tabs      into a new bookmarks folder "Tabs 16 Nov 2026" ("... (2)" when that folder exists;
                               OMNI_BOOKMARKS_MANAGER_V1's third column); private tabs, non-web pages, pages already
                               bookmarked (the address is a bookmark's key) and repeats are skipped; at most up to the
                               500 cap. The notice names the folder and what was skipped.
    The hint on tab rows is now "Hold Cross: tab menu" (private tabs too: their menu has the actions, the group rows
    say "Private tabs can't join groups").
  - No new button: Cross switch, Triangle mute, Square close, D-pad left / right pin, hold Cross the menu (as before).

Pure part: engine/entry/OmniTabActions.h (no SDL/WebKit): blocks, move targets, close / reload sets, duplicate
position, bookmark plan, folder name, texts. Uses OmniTabGroups.h (kMaxGroups: the same keys as OmniTabGroups::order,
so omniTgNormalize leaves a moved / duplicated tab where it was put) and OmniBookmarksModel.h (folder names).
Tested by tools/test_tab_actions.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_tab_actions.cpp -o t && ./t
Shell side: engine/entry/OmniTabActionsShell.h (included from OmniFeatures3.h after OmniTabGroupsShell.h; the two
hooks the group menu calls are declared in OmniFeatures3Decl.h). Menu row ids 7530..7538 (unused; the group menu has
1..3 and 10..17). Alias OTAC.

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp       the OmniTabGroups.h include line (ours after it).
  OmniFeatures3Decl.h   tab groups' omniTgRowMark declaration (ours after it).
  OmniFeatures3.h       the OmniTabGroupsShell.h include line (ours after it).
  OmniTabGroupsShell.h  omniTgMenuBuild's refusal line and its p.corner line (our rows after the group rows);
                        omniTgMenuInput's head (ours first); omniTgMenuShow's title line; omniTgTabFaces' hint line.
                        apply_tab_groups.py rewrites this file when its bytes differ, so a re-run of it drops our
                        edits; this script then sees no MARK there and applies them again (run it after).
Apply AFTER apply_tab_groups.py (r2) and apply_bookmarks_manager.py.
r2 (OMNI_TAB_ACTIONS_V1_R2, REV): Duplicate of a private tab while parental controls lock private tabs. Before, it
called omniNewPrivateTab, which only opened the PIN pad: the menu then said "No room for another tab", popped the
pad, and after a PIN an empty private tab opened. Now the gate is asked first (omniParGate, compiled in when
OmniParental.h exists): the PIN pad shows and nothing else; a correct PIN runs the duplicate again for the same tab
(found by Tab::omniMediaIdentity) and closes the tab menu. Whenever a new tab didn't appear because a panel opened
instead, no refusal is shown. Only OmniTabActionsShell.h changes (rewritten whole: an r1 tree upgrades).
usage: apply_tab_actions.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_TAB_ACTIONS_V1'
REV = 'OMNI_TAB_ACTIONS_V1_R2'   # r2: Duplicate of a private tab behind the parental PIN (shell only)
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_TAB_ACTIONS_V1: the pure part of the Tabs panel's tab actions (no SDL, no WebKit): which tabs Duplicate, Move,
// Close other tabs, Close tabs to the right, Reload all tabs and Bookmark all tabs touch, given pinned tabs
// (OMNI_PINNED_TABS_V1), tab groups (OMNI_TAB_GROUPS_V1), private tabs and the tab limit; plus their texts. The shell
// side is OmniTabActionsShell.h; the reasons are in tools/apply_tab_actions.py. Tested with g++ (test_tab_actions.cpp).
#pragma once
#include "OmniTabGroups.h"
#include "OmniBookmarksModel.h"
#include <algorithm>
#include <cstddef>
#include <string>
#include <vector>

namespace OmniTabActions {

// Rows of the hold-Cross tab menu (OmniTabGroupsShell.h's "Tab group" menu uses 1..3 and 10..17).
enum Row : int { kRowDuplicate = 7530, kRowMoveLeft, kRowMoveRight, kRowMoveStart, kRowMoveEnd, kRowCloseOthers,
                 kRowCloseRight, kRowReloadAll, kRowBookmarkAll };
inline bool isRow(int id) { return id >= kRowDuplicate && id <= kRowBookmarkAll; }

// One tab, in tab order. group: the display position of its group (OmniTabGroups::indexOf), -1 none.
struct Info { bool pinned = false, priv = false, unloaded = false; int group = -1; };

// The tab order is pinned, then each group (display order), then ungrouped: the keys OmniTabGroups::order sorts by.
inline int key(const Info& t) { return t.pinned ? 0 : t.group >= 0 ? 1 + t.group : 1 + OmniTabGroups::kMaxGroups; }
inline bool ordered(const std::vector<Info>& tabs)   // omniTgNormalize would leave this order as it is
{
    for (size_t i = 1; i < tabs.size(); ++i) if (key(tabs[i - 1]) > key(tabs[i])) return false;
    return true;
}
// The run of tabs around `i` with its key: its pinned tabs, its group, or the ungrouped tabs. A move stays inside it.
struct Block { size_t first = 0, last = 0; };
inline Block block(const std::vector<Info>& tabs, size_t i)
{
    Block b { i, i };
    if (i >= tabs.size()) return b;
    const int k = key(tabs[i]);
    while (b.first > 0 && key(tabs[b.first - 1]) == k) --b.first;
    while (b.last + 1 < tabs.size() && key(tabs[b.last + 1]) == k) ++b.last;
    return b;
}

// --- move ----------------------------------------------------------------------------------------------------------
enum Move { kLeft, kRight, kStart, kEnd };
// Where tab `i` goes; -1: it can't (already first / last of its block, or no such tab).
inline int moveTarget(const std::vector<Info>& tabs, size_t i, Move m)
{
    if (i >= tabs.size()) return -1;
    const Block b = block(tabs, i);
    switch (m) {
    case kLeft: return i > b.first ? int(i - 1) : -1;
    case kRight: return i < b.last ? int(i + 1) : -1;
    case kStart: return i > b.first ? int(b.first) : -1;
    case kEnd: return i < b.last ? int(b.last) : -1;
    }
    return -1;
}
// Moves v[from] to index `to`; the others keep their order.
template <class T> inline void moveItem(std::vector<T>& v, size_t from, size_t to)
{
    if (from >= v.size() || to >= v.size() || from == to) return;
    if (from < to) std::rotate(v.begin() + std::ptrdiff_t(from), v.begin() + std::ptrdiff_t(from) + 1, v.begin() + std::ptrdiff_t(to) + 1);
    else std::rotate(v.begin() + std::ptrdiff_t(to), v.begin() + std::ptrdiff_t(from), v.begin() + std::ptrdiff_t(from) + 1);
}
// "2 of 3 pinned", "2 of 4 in the group", "2 of 5"
inline std::string positionText(const std::vector<Info>& tabs, size_t i)
{
    if (i >= tabs.size()) return std::string();
    const Block b = block(tabs, i);
    const std::string n = std::to_string(i - b.first + 1) + " of " + std::to_string(b.last - b.first + 1);
    if (tabs[i].pinned) return n + " pinned";
    if (tabs[i].group >= 0) return n + " in the group";
    return n;
}
inline const char* cantMove(const std::vector<Info>& tabs, size_t i, Move m)   // the disabled row's value
{
    const bool first = m == kLeft || m == kStart;
    if (i < tabs.size() && tabs[i].pinned) return first ? "First pinned tab" : "Last pinned tab";
    if (i < tabs.size() && tabs[i].group >= 0) return first ? "First in its group" : "Last in its group";
    return first ? "Already first" : "Already last";
}

// --- duplicate -----------------------------------------------------------------------------------------------------
inline bool canDuplicate(int open, int limit) { return open < limit; }
// The copy: private stays private; it joins the original's group; a copy of a pinned tab is not pinned.
inline Info duplicateInfo(const Info& src)
{
    Info d;
    d.priv = src.priv;
    d.group = src.pinned || src.priv ? -1 : src.group;
    return d;
}
// Where the copy goes (its index once inserted): right after the original; a pinned tab's copy goes first among the
// ungrouped tabs (after the pinned tabs and the groups).
inline size_t duplicateIndex(const std::vector<Info>& before, size_t src)
{
    if (src >= before.size()) return before.size();
    if (!before[src].pinned) return src + 1;
    const int k = key(duplicateInfo(before[src]));
    for (size_t i = 0; i < before.size(); ++i) if (key(before[i]) >= k) return i;
    return before.size();
}
inline std::string limitText(int open, int limit) { return "Tab limit reached (" + std::to_string(open) + " of " + std::to_string(limit) + ")"; }
inline std::string duplicateNotice(bool priv) { return priv ? "Duplicated as a private tab" : "Tab duplicated"; }

// --- close other tabs / tabs to the right --------------------------------------------------------------------------
enum Close { kCloseOthers, kCloseRight };
// The tabs to close (indexes, in order): never `keep`, never a pinned tab.
inline std::vector<size_t> closeSet(const std::vector<Info>& tabs, size_t keep, Close c)
{
    std::vector<size_t> out;
    for (size_t i = 0; i < tabs.size(); ++i) {
        if (i == keep || tabs[i].pinned) continue;
        if (c == kCloseRight && i < keep) continue;
        out.push_back(i);
    }
    return out;
}
// Pinned tabs the action leaves open although they are "other" / "to the right".
inline int pinnedSpared(const std::vector<Info>& tabs, size_t keep, Close c)
{
    int n = 0;
    for (size_t i = 0; i < tabs.size(); ++i) if (i != keep && tabs[i].pinned && (c == kCloseOthers || i > keep)) ++n;
    return n;
}
inline int privateIn(const std::vector<Info>& tabs, const std::vector<size_t>& set)
{
    int n = 0;
    for (size_t i : set) if (i < tabs.size() && tabs[i].priv) ++n;
    return n;
}
inline std::string tabsText(int n) { return std::to_string(n) + (n == 1 ? " tab" : " tabs"); }
inline const char* closeLabel(Close c) { return c == kCloseOthers ? "Close other tabs" : "Close tabs to the right"; }
inline std::string closeValue(int n, int spared, Close c)
{
    if (n <= 0) return spared ? std::string("Only pinned tabs") : std::string(c == kCloseOthers ? "No other tabs" : "None to the right");
    return tabsText(n) + (spared ? " (" + std::to_string(spared) + " pinned stay)" : std::string());
}
inline std::string askTitle(int n, Close c) { return "Close " + tabsText(n) + (c == kCloseOthers ? "?" : " to the right?"); }
inline std::string askMessage(int spared, int priv)
{
    std::string m = "Pinned tabs are never closed this way";
    m += spared ? " (" + std::to_string(spared) + (spared == 1 ? " stays open)." : " stay open).") : std::string(".");
    m += " Closed tabs go to Reopen closed tab (the last 10";
    m += priv ? ", not private ones)." : ").";
    return m;
}
inline std::string askOk(int n) { return "Close " + tabsText(n); }
inline std::string closedNotice(int n, int spared)
{
    std::string s = "Closed " + tabsText(n);
    if (spared) s += "; " + std::to_string(spared) + " pinned " + (spared == 1 ? "tab stays" : "tabs stay");
    return s;
}

// --- reload all ----------------------------------------------------------------------------------------------------
// Loaded tabs only: an unloaded tab (tab memory, or restored and not shown yet) loads when it is shown.
inline std::vector<size_t> reloadSet(const std::vector<Info>& tabs)
{
    std::vector<size_t> out;
    for (size_t i = 0; i < tabs.size(); ++i) if (!tabs[i].unloaded) out.push_back(i);
    return out;
}
inline std::string reloadNotice(int n, int unloaded)
{
    std::string s = "Reloading " + tabsText(n);
    if (unloaded) s += " (" + std::to_string(unloaded) + " unloaded: " + (unloaded == 1 ? "it loads" : "they load") + " when shown)";
    return s;
}

// --- bookmark all --------------------------------------------------------------------------------------------------
struct Candidate { std::string url; bool priv = false, web = false, bookmarked = false; };
struct BookmarkPlan { std::vector<size_t> add; int priv = 0, notWeb = 0, already = 0, repeated = 0, overCap = 0; };
// Which tabs become bookmarks: not private, web pages, not bookmarked yet (a bookmark's address is its key), each
// address once, at most `room` (the bookmarks cap is 500).
inline BookmarkPlan bookmarkPlan(const std::vector<Candidate>& tabs, size_t room)
{
    BookmarkPlan p;
    std::vector<std::string> seen;
    for (size_t i = 0; i < tabs.size(); ++i) {
        const Candidate& c = tabs[i];
        if (c.priv) { ++p.priv; continue; }
        if (!c.web) { ++p.notWeb; continue; }
        if (c.bookmarked) { ++p.already; continue; }
        if (std::find(seen.begin(), seen.end(), c.url) != seen.end()) { ++p.repeated; continue; }
        seen.push_back(c.url);
        if (p.add.size() >= room) { ++p.overCap; continue; }
        p.add.push_back(i);
    }
    return p;
}
// A new folder: "<base>", or "<base> (2)" ... when a folder has that name (names as OmniBookmarksModel stores them).
inline std::string folderName(const std::string& base0, const std::vector<std::string>& existing)
{
    const std::string base = OmniBookmarksModel::cleanFolder(base0).empty() ? std::string("Tabs") : OmniBookmarksModel::cleanFolder(base0);
    auto taken = [&](const std::string& n) { return std::find(existing.begin(), existing.end(), n) != existing.end(); };
    if (!taken(base)) return base;
    for (int k = 2; k < 1000; ++k) {
        const std::string suffix = " (" + std::to_string(k) + ")";
        const std::string n = OmniBookmarksModel::cleanFolder(OmniBookmarksModel::oneLine(base, OmniBookmarksModel::kFolderMax - suffix.size()) + suffix);
        if (!taken(n)) return n;
    }
    return base;
}
inline std::string bookmarkValue(const BookmarkPlan& p)
{
    if (!p.add.empty()) return tabsText(int(p.add.size()));
    if (p.overCap) return "Bookmarks are full (500)";
    if (p.already) return "Already bookmarked";
    return "No tabs to bookmark";
}
inline std::string bookmarkNotice(const BookmarkPlan& p, const std::string& folder)
{
    if (p.add.empty()) {
        if (p.overCap) return "Bookmarks are full (500): delete some first";
        if (p.already) return "These tabs are already bookmarked";
        return p.priv ? "Private tabs are not bookmarked" : "No web pages to bookmark";
    }
    std::string s = "Bookmarked " + tabsText(int(p.add.size())) + " in \"" + folder + "\"";
    std::vector<std::string> skipped;
    if (p.priv) skipped.push_back(std::to_string(p.priv) + " private");
    if (p.already) skipped.push_back(std::to_string(p.already) + " already bookmarked");
    if (p.overCap) skipped.push_back(std::to_string(p.overCap) + " over the 500 cap");
    for (size_t i = 0; i < skipped.size(); ++i) s += (i ? ", " : "; skipped ") + skipped[i];
    return s;
}

} // namespace OmniTabActions
'''

SHELL = r'''// OMNI_TAB_ACTIONS_V1: tab actions in the Tabs panel's hold-Cross tab menu (shell side). Included from OmniFeatures3.h
// after OmniTabGroupsShell.h (inside OmniBrowser.cpp's anonymous namespace); declared in OmniFeatures3Decl.h for the
// group menu's hooks. The pure part is OmniTabActions.h; the reasons are in tools/apply_tab_actions.py. Main thread.
// OMNI_TAB_ACTIONS_V1_R2: Duplicate of a private tab asks the parental PIN first (when OmniParental.h is there) and
// runs again after a correct PIN; never "No room for another tab" when a panel opened instead of the tab.
#pragma once

namespace OTAC = OmniTabActions;

static std::vector<OTAC::Info> omniTacInfos()
{
    const std::vector<int> pos = omniTgPositions();
    std::vector<OTAC::Info> out;
    out.reserve(tabs.size());
    for (size_t i = 0; i < tabs.size(); ++i) {
        const Tab& t = *tabs[i];
        OTAC::Info f;
        f.pinned = omniPtPinned(t); f.priv = t.omniPrivate; f.unloaded = omniTmIsUnloaded(t);
        f.group = f.pinned || f.priv || i >= pos.size() ? -1 : pos[i];
        out.push_back(f);
    }
    return out;
}
static void omniTacKeepShown(const void* shown) { const size_t s = omniPtIndex(shown); if (s < tabs.size()) selected = s; }
static std::vector<OTAC::Candidate> omniTacCandidates()
{
    std::vector<OTAC::Candidate> out;
    for (auto& t : tabs) {
        OTAC::Candidate c; c.url = omniTsTabURL(*t); c.priv = t->omniPrivate; c.web = omniWebURL(c.url);
        c.bookmarked = c.web && !c.priv && omniFxBookmarkIndex(c.url) >= 0;
        out.push_back(c);
    }
    return out;
}
static size_t omniTacRoom() { omniFxBookmarksLoad(); return omniFxBookmarks.size() >= omniFxBookmarkMax ? 0 : omniFxBookmarkMax - omniFxBookmarks.size(); }

// --- the rows (after the group rows of omniTgMenuBuild) ----------------------------------------------------------------
static void omniTacMenuRows(OmniFxPanel& p, const Tab* t)
{
    if (!t) return;
    omniTgNormalize();   // pinned, groups, ungrouped: each block is one run
    const size_t i = omniPtIndex(t);
    if (i >= tabs.size()) return;
    const std::vector<OTAC::Info> infos = omniTacInfos();
    auto add = [&p](int id, const std::string& label, int icon, bool enabled, const std::string& value) {
        OmniFxRow r; r.id = id; r.label = label; r.icon = icon; r.enabled = enabled; r.value = value;
        p.rows.push_back(r);
    };
    const bool full = omniF3TabsFull();
    add(OTAC::kRowDuplicate, "Duplicate tab", omniIconPlus, !full,
        full ? OTAC::limitText(int(tabs.size()), omniF3TabLimit()) : t->omniPrivate ? std::string("Private") : std::string());
    const struct { int id; const char* label; OTAC::Move m; } moves[] = {
        { OTAC::kRowMoveLeft, "Move left", OTAC::kLeft }, { OTAC::kRowMoveRight, "Move right", OTAC::kRight },
        { OTAC::kRowMoveStart, "Move to the start", OTAC::kStart }, { OTAC::kRowMoveEnd, "Move to the end", OTAC::kEnd } };
    for (const auto& m : moves) {
        const bool can = OTAC::moveTarget(infos, i, m.m) >= 0;
        add(m.id, m.label, -1, can, !can ? std::string(OTAC::cantMove(infos, i, m.m)) : m.m == OTAC::kLeft || m.m == OTAC::kRight ? OTAC::positionText(infos, i) : std::string());
    }
    for (OTAC::Close c : { OTAC::kCloseOthers, OTAC::kCloseRight }) {
        const int n = int(OTAC::closeSet(infos, i, c).size());
        add(c == OTAC::kCloseOthers ? OTAC::kRowCloseOthers : OTAC::kRowCloseRight, OTAC::closeLabel(c), omniIconClose, n > 0, OTAC::closeValue(n, OTAC::pinnedSpared(infos, i, c), c));
    }
    const int reload = int(OTAC::reloadSet(infos).size());
    add(OTAC::kRowReloadAll, "Reload all tabs", omniIconReload, reload > 0, OTAC::tabsText(reload));
    const OTAC::BookmarkPlan plan = OTAC::bookmarkPlan(omniTacCandidates(), omniTacRoom());
    add(OTAC::kRowBookmarkAll, "Bookmark all tabs", -1, !plan.add.empty(), OTAC::bookmarkValue(plan));
}

// --- the actions -----------------------------------------------------------------------------------------------------
static void omniTacMove(Tab& t, OTAC::Move m)
{
    omniTgNormalize();
    const size_t from = omniPtIndex(&t);
    const std::vector<OTAC::Info> infos = omniTacInfos();
    const int to = OTAC::moveTarget(infos, from, m);
    if (to < 0) { notice(OTAC::cantMove(infos, from, m)); return; }
    const void* shown = active();
    OTAC::moveItem(tabs, from, size_t(to));
    omniTacKeepShown(shown);
    omniTgNormalize();   // a no-op: the move stayed inside its block
    omniTgFocus = &t;    // the Tabs panel's highlight follows the tab
    omniShellDirty = true;
    notice("Moved: " + OTAC::positionText(omniTacInfos(), omniPtIndex(&t)));
    fprintf(stderr, "OMNI TAB ACTIONS: moved tab %zu -> %d\n", from, to);
}
#if __has_include("OmniParental.h")
static uintptr_t omniTacDupPending = 0;   // OMNI_TAB_ACTIONS_V1_R2: the tab to duplicate after a correct parental PIN
static bool omniTacDuplicate(Tab& src);
static void omniTacDuplicateAgain()        // omniParGate's `again` (the PIN pad is gone, the gate is open)
{
    const uintptr_t id = omniTacDupPending;
    omniTacDupPending = 0;
    Tab* src = nullptr;
    for (auto& t : tabs) if (id && t->omniMediaIdentity == id) { src = t.get(); break; }
    if (!src) { notice("That tab was closed"); return; }
    omniTacDuplicate(*src);
    if (!omniFxStack.empty() && omniFxStack.back().build == omniTgMenuBuild) omniFxPop();   // the tab menu
}
#endif
// False: a PIN pad (or another panel) opened instead and the tab menu stays under it.
static bool omniTacDuplicate(Tab& src)
{
    omniTgNormalize();
    const std::vector<OTAC::Info> before = omniTacInfos();
    const size_t from = omniPtIndex(&src);
    if (from >= tabs.size()) return true;
    const bool priv = src.omniPrivate;
#if __has_include("OmniParental.h")
    if (priv) {   // OMNI_TAB_ACTIONS_V1_R2: the PIN first; the duplicate runs after a correct one (cooldown: its notice)
        omniTacDupPending = src.omniMediaIdentity;
        if (omniParGate(omniParGatePrivate, omniTacDuplicateAgain)) return false;
        omniTacDupPending = 0;
    }
#endif
    const std::string url = omniTsTabURL(src);
    const int group = before[from].group >= 0 ? OTG::groupOf(omniTgModel, &src) : 0;
    const size_t count = tabs.size(), panels = omniFxStack.size();
    if (priv) omniNewPrivateTab(); else newTab();   // both check the tab limit and memory (omniF3TabAllowed)
    Tab* made = active();
    if (tabs.size() != count + 1 || !made || made == &src || tabs.back().get() != made) {
        if (tabs.size() == count && omniFxStack.size() > panels) return false;   // a panel (PIN pad) opened instead: no refusal
        const std::string why = omniF3TabRefusal();
        notice(why.empty() ? std::string("No room for another tab") : why);
        return true;
    }
    if (omniWebURL(url)) navigate(url);
    else if (!priv) omniOpenNewTabPage(made);   // omniNewPrivateTab opened the new-tab page already
    if (group) OTG::add(omniTgModel, made, group);
    const void* shown = active();
    OTAC::moveItem(tabs, tabs.size() - 1, OTAC::duplicateIndex(before, from));
    omniTacKeepShown(shown);
    omniTgNormalize();
    omniTgFocus = made;
    omniShellDirty = true;
    notice(OTAC::duplicateNotice(priv));
    fprintf(stderr, "OMNI TAB ACTIONS: duplicated tab %zu%s, %zu tabs\n", from, priv ? " (private)" : "", tabs.size());
    return true;
}
// After the question: closes the tabs it named (pinned tabs never); each goes to "Reopen closed tab" as usual
// (omniFxTabClosing: not private ones, the last 10).
static void omniTacClose(const void* keepTab, OTAC::Close c)
{
    Tab* keep = omniTgTab(keepTab);
    if (!keep) { notice("This tab was closed"); return; }
    omniTgNormalize();
    const std::vector<OTAC::Info> infos = omniTacInfos();
    const size_t k = omniPtIndex(keep);
    const std::vector<size_t> set = OTAC::closeSet(infos, k, c);
    const int spared = OTAC::pinnedSpared(infos, k, c);
    std::vector<const void*> doomed;
    for (size_t i : set) { doomed.push_back(tabs[i].get()); tabs[i]->omniLazyURL.clear(); }   // closing must not load them first
    const void* shown = active();
    int n = 0;
    omniTmSkipRestore = true;   // nor reload an unloaded one
    for (const void* d : doomed) {
        const size_t i = omniPtIndex(d);
        if (i >= tabs.size() || tabs.size() <= 1 || tabs[i].get() == keep || omniPtPinned(*tabs[i])) continue;
        activate(i);
        closeTab();
        ++n;
    }
    omniTmSkipRestore = false;
    const size_t s = omniPtIndex(omniTgTab(shown) ? shown : static_cast<const void*>(keep));
    if (s < tabs.size()) activate(s);
    omniTgFocus = keep;
    omniShellDirty = true;
    notice(OTAC::closedNotice(n, spared));
    fprintf(stderr, "OMNI TAB ACTIONS: %s closed %d tab(s), %d pinned kept, %zu open\n", c == OTAC::kCloseOthers ? "others" : "right", n, spared, tabs.size());
    omniFxRefresh();
}
static void omniTacAskClose(const Tab& t, OTAC::Close c)
{
    omniTgNormalize();
    const std::vector<OTAC::Info> infos = omniTacInfos();
    const size_t k = omniPtIndex(&t);
    const std::vector<size_t> set = OTAC::closeSet(infos, k, c);
    if (set.empty()) { notice(OTAC::closeValue(0, OTAC::pinnedSpared(infos, k, c), c)); return; }
    const int n = int(set.size());
    const void* keep = &t;
    omniFxPop();   // back to the Tabs panel; the question goes over it
    omniAsk(OTAC::askTitle(n, c), OTAC::askMessage(OTAC::pinnedSpared(infos, k, c), OTAC::privateIn(infos, set)), OTAC::askOk(n),
        [keep, c](bool ok) { if (ok) omniTacClose(keep, c); });
}
static void omniTacReloadAll()
{
    const std::vector<OTAC::Info> infos = omniTacInfos();
    const std::vector<size_t> set = OTAC::reloadSet(infos);
    for (size_t i : set) WKPageReload(tabs[i]->page);
    notice(OTAC::reloadNotice(int(set.size()), int(infos.size() - set.size())));
    fprintf(stderr, "OMNI TAB ACTIONS: reload all, %zu of %zu tab(s)\n", set.size(), infos.size());
}
static void omniTacBookmarkAll()
{
    const OTAC::BookmarkPlan plan = OTAC::bookmarkPlan(omniTacCandidates(), omniTacRoom());
    if (plan.add.empty()) { notice(OTAC::bookmarkNotice(plan, std::string())); return; }
    auto list = omniBmEntries();
    const std::string folder = OTAC::folderName("Tabs " + OmniTabSessions::shortDate(time(nullptr)), OBMK::folders(list));
    for (size_t i : plan.add) {
        const Tab& t = *tabs[i];
        const std::string url = omniTsTabURL(t);
        list.push_back({ url, t.title.empty() ? omniShownURL(url) : t.title, folder });
    }
    OBMK::normalize(list);   // the new folder after the others, before the bookmarks without a folder
    omniBmStore(list);
    omniBmSetOpen(folder, true);
    notice(OTAC::bookmarkNotice(plan, folder));
    fprintf(stderr, "OMNI TAB ACTIONS: bookmarked %zu tab(s) in a new folder\n", plan.add.size());
}

// --- input (omniTgMenuInput hands every button here first) --------------------------------------------------------------
static bool omniTacMenuInput(const OmniFxRow& r, int b)
{
    if (!OTAC::isRow(r.id) || b != SDL_CONTROLLER_BUTTON_A) return false;
    if (!r.enabled) return true;
    Tab* t = omniTgTab(omniTgMenuTab);
    if (!t) { omniFxPop(); return true; }
    switch (r.id) {
    case OTAC::kRowDuplicate: if (omniTacDuplicate(*t)) omniFxPop(); return true;   // R2: not over a PIN pad
    case OTAC::kRowMoveLeft: omniTacMove(*t, OTAC::kLeft); omniFxRefresh(); return true;    // the menu stays: press again
    case OTAC::kRowMoveRight: omniTacMove(*t, OTAC::kRight); omniFxRefresh(); return true;
    case OTAC::kRowMoveStart: omniTacMove(*t, OTAC::kStart); omniFxPop(); return true;
    case OTAC::kRowMoveEnd: omniTacMove(*t, OTAC::kEnd); omniFxPop(); return true;
    case OTAC::kRowCloseOthers: omniTacAskClose(*t, OTAC::kCloseOthers); return true;
    case OTAC::kRowCloseRight: omniTacAskClose(*t, OTAC::kCloseRight); return true;
    case OTAC::kRowReloadAll: omniTacReloadAll(); omniFxPop(); return true;
    case OTAC::kRowBookmarkAll: omniTacBookmarkAll(); omniFxPop(); return true;
    default: return false;
    }
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniTabGroups.h" // OMNI_TAB_GROUPS_V1: tab groups: order, panel rows, unload order, session line (pure)\n',
         '#include "OmniTabGroups.h" // OMNI_TAB_GROUPS_V1: tab groups: order, panel rows, unload order, session line (pure)\n'
         '#include "OmniTabActions.h" // OMNI_TAB_ACTIONS_V1: tab menu actions: duplicate, move, close others / right, reload / bookmark all (pure)\n'),
    ],
    'OmniFeatures3Decl.h': [
        ('static bool omniTgRowMark(const OmniFxPanel& p, const OmniFxRow& r, int x, int y, int h);   // omniFxDrawPanel: colours\n',
         'static bool omniTgRowMark(const OmniFxPanel& p, const OmniFxRow& r, int x, int y, int h);   // omniFxDrawPanel: colours\n'
         '// OMNI_TAB_ACTIONS_V1 (OmniTabActionsShell.h): the tab menu\'s actions (hold Cross on a Tabs panel tab row)\n'
         'static void omniTacMenuRows(OmniFxPanel& p, const Tab* t);   // omniTgMenuBuild: after the group rows\n'
         'static bool omniTacMenuInput(const OmniFxRow& r, int b);     // omniTgMenuInput: first\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniTabGroupsShell.h" // OMNI_TAB_GROUPS_V1\n',
         '#include "OmniTabGroupsShell.h" // OMNI_TAB_GROUPS_V1\n'
         '#include "OmniTabActionsShell.h" // OMNI_TAB_ACTIONS_V1 (after tab groups: it extends their tab menu)\n'),
    ],
    'OmniTabGroupsShell.h': [
        ('    if (c != OTG::kOk) { refusal(OTG::refusal(c)); return; }\n',
         '    if (c != OTG::kOk) { refusal(OTG::refusal(c)); omniTacMenuRows(p, t); return; } // OMNI_TAB_ACTIONS_V1: the actions still apply\n'),
        ('    p.corner = std::to_string(omniTgModel.groups.size()) + " of " + std::to_string(OTG::kMaxGroups) + " groups";\n',
         '    p.corner = std::to_string(omniTgModel.groups.size()) + " of " + std::to_string(OTG::kMaxGroups) + " groups";\n'
         '    omniTacMenuRows(p, t); // OMNI_TAB_ACTIONS_V1: Duplicate, Move, Close other / to the right, Reload all, Bookmark all\n'),
        ('static bool omniTgMenuInput(OmniFxPanel&, const OmniFxRow& r, int b)\n{\n',
         'static bool omniTgMenuInput(OmniFxPanel&, const OmniFxRow& r, int b)\n{\n'
         '    if (omniTacMenuInput(r, b)) return true; // OMNI_TAB_ACTIONS_V1: its rows (7530..7538)\n'),
        ('    p.title = "Tab group"; p.w = 820; p.maxVisible = 8;\n',
         '    p.title = "Tab"; p.w = 820; p.maxVisible = 9; // OMNI_TAB_ACTIONS_V1: the group rows, then the tab actions\n'),
        ('    if (r.id >= 0 && r.id < int(tabs.size()) && !tabs[size_t(r.id)]->omniPrivate) p.extra = "Hold Cross: group";\n',
         '    if (r.id >= 0 && r.id < int(tabs.size())) p.extra = "Hold Cross: tab menu"; // OMNI_TAB_ACTIONS_V1: group, duplicate, move, close others (private tabs too)\n'),
    ],
}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits):
    s = (root / name).read_bytes().decode('utf-8')
    if MARK in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if MARK in s:
        return name + ': already'
    for old0, new0 in edits:
        old, e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))
        s = s.replace(old, new0.replace('\n', e), 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied'


def write_new(name, text, like):
    raw = (root / like).read_bytes()
    nl = '\r\n' if raw.count(b'\r\n') * 2 > raw.count(b'\n') else '\n'
    data = text.replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


def main():
    for need, f, tool in (('OMNI_TAB_GROUPS_V1_R2', 'OmniBrowser.cpp', 'apply_tab_groups.py'),
                          ('OMNI_TAB_GROUPS_V1', 'OmniTabGroupsShell.h', 'apply_tab_groups.py'),
                          ('OMNI_BOOKMARKS_MANAGER_V1', 'OmniBookmarks.h', 'apply_bookmarks_manager.py'),
                          ('OMNI_BOOKMARKS_MANAGER_V1', 'OmniBookmarksShell.h', 'apply_bookmarks_manager.py'),
                          ('OMNI_PINNED_TABS_V1', 'OmniPinnedTabsShell.h', 'apply_pinned_tabs.py')):
        p = root / f
        if not p.exists() or need not in p.read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (f, need, tool))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniTabActions.h', PURE, 'OmniTabGroups.h'),
            write_new('OmniTabActionsShell.h', SHELL, 'OmniTabGroupsShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK + ' (r2)')


main()
