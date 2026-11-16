#!/usr/bin/env python3
"""OMNI_TAB_GROUPS_V1 (2026-11-16): tab groups (roadmap R3-004, the half after OMNI_PINNED_TABS_V1).

What the user sees
  - Tabs panel (OmniTabsPage.h): hold Cross (half a second, the page's hold-Cross timing) on a tab row opens the
    "Tab group" menu for that tab: "Add to "<group>"" for each other group (colour square, colour name, tab count),
    "New group..." (value: the default name, "Group 1", "Group 2" ...), "Remove from "<group>"" when it is in one.
    A short Cross still switches (on release, as a short Cross on a page still clicks). The hint line says
    "Hold Cross: group" on tab rows. Free buttons were checked: Cross switch, Triangle mute (OMNI_TAB_AUDIO_V1),
    Square close, D-pad left / right pin (OMNI_PINNED_TABS_V1), Circle back, L1/R1 page; so the menu is on hold Cross.
  - New group: made with the default name and the next unused of six colours (Blue, Red, Yellow, Green, Pink,
    Purple), the tab joins it, then Omni's on-screen keyboard opens on "Group name" (Go keeps what was typed, Cancel
    keeps the default). Names are one line, at most 40 bytes, unique ("Work (2)").
  - Each group shows as a header row before its tabs: a colour square, the name, the colour name, "3 tabs" (and
    "collapsed" / "collapsed, current tab inside"). On a header: Cross collapses / expands (a collapsed group's tab
    rows are hidden), Triangle renames (keyboard), D-pad left / right changes the colour, Square ungroups (the group
    goes, its tabs stay open). A grouped tab's row has a colour bar at its left.
  - Order: pinned tabs first (OMNI_PINNED_TABS_V1), then each group's tabs together (groups in creation order), then
    the ungrouped tabs; new tabs open at the end (ungrouped). The top strip shows that order (it is the tab order).
  - Private tabs can't join groups (the menu says "Private tabs can't join groups"); pinned tabs can't either
    ("unpin it first"); pinning a grouped tab takes it out of its group. At most 8 groups ("8 groups: ungroup one
    first"). A group whose last tab closes or leaves goes.
  - Tab memory (OmniTabMemory.h): when a background tab must be unloaded, the pinned rule comes first (unpinned
    before pinned), then a collapsed group's tabs go before the other tabs, then the least recently shown.
  - Restart: session.txt (OMNI_FEATURES_V3) gets "group\\t<index>\\t<group no>\\t<colour>\\t<collapsed>\\t<name>"
    after a grouped tab's "tab" line (and after pinned's "pinned\\t<n>"). Older builds skip unknown lines (tabs come
    back ungrouped); files without the lines restore as before.
  - Saved sessions (OMNI_TAB_SESSIONS_V1, sessions.txt): a grouped tab's "tab" line is followed by
    "group\\t<index in the session>\\t<group no>\\t<colour>\\t<collapsed>\\t<name>". Older builds skip it (and drop it
    when they rewrite the file); the "omni-sessions\\t1" header is unchanged. Opening a session (Replace or Add)
    regroups the opened tabs; a group with the same name already open is joined; past 8 groups they stay ungrouped.

Pure part: engine/entry/OmniTabGroups.h (no SDL/WebKit): model (groups, membership, caps, names, colours), order,
panel rows, unload order, session payload / line parse + serialize, restore, texts.
Tested by tools/test_tab_groups.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_tab_groups.cpp -o t && ./t
Shell side: engine/entry/OmniTabGroupsShell.h (included from OmniFeatures3.h after OmniSiteClearShell.h; declared in
OmniFeatures3Decl.h). Groups hold Tab pointers (forgotten in omniFxTabClosing), so the Tab struct is not touched.
Tabs panel rows are no longer tab indexes once a group exists: rows keep id = tab index, headers are ids 470..477,
and the hooks map between rows and tabs (show, faces, pin / close highlight).

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp      the OmniPinnedTabs.h include line; omniSessionText's pinned line; the restore loop's pinned
                       branch; the omniPtRestoreApply(sel) line (ours goes before it; r2: the order once after it).
  r2 (REV = OMNI_TAB_GROUPS_V1_R2): a tree patched by r1 gets the shell header rewritten and, in OmniBrowser.cpp, r1's
                       two restore lines (CALL_R1) replaced by CALL_R2; a fresh apply writes CALL_R2 directly.
  OmniFeatures3Decl.h  pinned's omniPtStripClick declaration (declarations after it).
  OmniFeatures3.h      the OmniSiteClearShell.h include line (OmniTabGroupsShell.h after it).
  OmniTabMemory.h      pinned's "unloadsBefore" line of omniTmUnloadOne.
  OmniTabsPage.h       omniPtForget(&tab) in omniFxTabClosing; the omniFxTabsBuild head + its for line; the "New tab"
                       row line; the omniTaTabFaces + omniPtTabFaces lines; the omniFxTabsInput head; the sel line of
                       omniFxTabsShow.
  OmniFeatures.h       the eligibility line of omniFxButtonEvent; the 500 ms line of omniFxTick (hold Cross).
  OmniFeaturesPanel.h  the r.icon line of omniFxDrawPanel's list rows (colour square / bar).
  OmniTabSessions.h    struct Tab, struct Candidate; serialize's "tab" line; parse's "tab" branch; collect's push_back.
  OmniTabSessionsShell.h  omniTsCandidates' Candidate line; omniTsOpen's notOpened line.
  Not touched: OmniContextMenu.h (the page's hold-Cross menu) and the Quick menu.
Apply AFTER apply_pinned_tabs.py, apply_tab_sessions.py, apply_tab_audio.py and apply_site_clear.py.
usage: apply_tab_groups.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_TAB_GROUPS_V1'
REV = 'OMNI_TAB_GROUPS_V1_R2'   # r2: restore = group, then pin (both by file index), then the order once
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_TAB_GROUPS_V1: the pure part of tab groups (no SDL, no WebKit). The shell side is OmniTabGroupsShell.h; the
// reasons are in tools/apply_tab_groups.py. Tested on the host with g++ (test_tab_groups.cpp).
#pragma once
#include <algorithm>
#include <cstdint>
#include <numeric>
#include <string>
#include <utility>
#include <vector>

namespace OmniTabGroups {

constexpr int kMaxGroups = 8;
constexpr int kColours = 6;
constexpr size_t kNameMax = 40;
constexpr size_t kPayloadMax = 120;
constexpr const char* kLinePrefix = "group\t";   // "group\t<tab index>\t<group no>\t<colour>\t<collapsed>\t<name>"

// --- colours -----------------------------------------------------------------------------------------------------
struct Rgb { uint8_t r, g, b; };
inline int clampColour(int c) { return ((c % kColours) + kColours) % kColours; }
inline Rgb colour(int c)
{
    static const Rgb k[kColours] = { { 66, 133, 244 }, { 234, 67, 53 }, { 249, 171, 0 }, { 52, 168, 83 }, { 233, 30, 140 }, { 147, 52, 230 } };
    return k[clampColour(c)];
}
inline const char* colourName(int c)
{
    static const char* const k[kColours] = { "Blue", "Red", "Yellow", "Green", "Pink", "Purple" };
    return k[clampColour(c)];
}

// --- text helpers --------------------------------------------------------------------------------------------------
inline std::string cut(std::string s, size_t max)   // never splits a UTF-8 sequence
{
    if (s.size() > max) { size_t c = max; while (c && (static_cast<unsigned char>(s[c]) & 0xc0) == 0x80) --c; s.resize(c); }
    return s;
}
inline std::string trim(const std::string& s)
{
    const size_t a = s.find_first_not_of(' ');
    if (a == std::string::npos) return std::string();
    return s.substr(a, s.find_last_not_of(' ') - a + 1);
}
inline std::string lower(std::string s) { for (auto& c : s) if (c >= 'A' && c <= 'Z') c += 'a' - 'A'; return s; }
inline bool sameName(const std::string& a, const std::string& b) { return lower(trim(a)) == lower(trim(b)); }
// What the keyboard returned (or a file held), made storable: one line, no tabs, at most kNameMax bytes; empty -> fallback.
inline std::string cleanName(const std::string& raw, const std::string& fallback)
{
    std::string n = raw.substr(0, 4096);
    for (auto& c : n) if (c == '\t' || c == '\n' || c == '\r') c = ' ';
    n = trim(cut(trim(n), kNameMax));
    return n.empty() ? fallback : n;
}

// --- the model -----------------------------------------------------------------------------------------------------
struct Group { int id = 0; std::string name; int colour = 0; bool collapsed = false; };
struct Model {
    std::vector<Group> groups;                          // display order (header rows, tab order)
    std::vector<std::pair<const void*, int>> member;    // tab -> group id (a tab is in one group at most)
    int nextId = 1;
};
inline int indexOf(const Model& m, int id)
{
    for (size_t i = 0; i < m.groups.size(); ++i) if (m.groups[i].id == id) return int(i);
    return -1;
}
inline int groupOf(const Model& m, const void* tab)
{
    for (auto& e : m.member) if (e.first == tab) return e.second;
    return 0;
}
inline const Group* groupFor(const Model& m, const void* tab)
{
    const int i = indexOf(m, groupOf(m, tab));
    return i < 0 ? nullptr : &m.groups[size_t(i)];
}
inline int count(const Model& m, int id) { return int(std::count_if(m.member.begin(), m.member.end(), [id](const std::pair<const void*, int>& e) { return e.second == id; })); }
inline bool collapsedTab(const Model& m, const void* tab) { const Group* g = groupFor(m, tab); return g && g->collapsed; }

// --- names / colours of new groups -----------------------------------------------------------------------------------
inline bool nameTaken(const Model& m, const std::string& n, int exceptId)
{
    for (auto& g : m.groups) if (g.id != exceptId && sameName(g.name, n)) return true;
    return false;
}
inline std::string defaultName(const Model& m)   // "Group 1", "Group 2" ... the first one no group has
{
    for (int k = 1; k < 1000; ++k) { const std::string n = "Group " + std::to_string(k); if (!nameTaken(m, n, 0)) return n; }
    return "Group";
}
// `base`, or "base (2)" ... so no other group (except `exceptId`) has it.
inline std::string uniqueName(const Model& m, const std::string& base, int exceptId = 0)
{
    if (!nameTaken(m, base, exceptId)) return base;
    for (int k = 2; k < 1000; ++k) {
        const std::string suffix = " (" + std::to_string(k) + ")";
        const std::string n = cut(base, kNameMax - suffix.size()) + suffix;
        if (!nameTaken(m, n, exceptId)) return n;
    }
    return base;
}
inline int nextColour(const Model& m)   // the first colour no group uses, else round the six
{
    for (int c = 0; c < kColours; ++c)
        if (std::none_of(m.groups.begin(), m.groups.end(), [c](const Group& g) { return g.colour == c; })) return c;
    return int(m.groups.size()) % kColours;
}

// --- checks --------------------------------------------------------------------------------------------------------
enum Check { kOk, kPrivate, kPinned, kFull };
inline Check canJoin(bool priv, bool pinned)
{
    if (priv) return kPrivate;
    if (pinned) return kPinned;
    return kOk;
}
inline Check canCreate(bool priv, bool pinned, int groups)
{
    const Check c = canJoin(priv, pinned);
    if (c != kOk) return c;
    return groups >= kMaxGroups ? kFull : kOk;
}
inline std::string refusal(Check c)
{
    switch (c) {
    case kPrivate: return "Private tabs can't join groups";
    case kPinned: return "Pinned tabs can't join groups: unpin it first";
    case kFull: return std::to_string(kMaxGroups) + " groups: ungroup one first";
    default: return std::string();
    }
}

// --- edits ---------------------------------------------------------------------------------------------------------
inline void dropEmpty(Model& m)
{
    m.groups.erase(std::remove_if(m.groups.begin(), m.groups.end(), [&m](const Group& g) { return count(m, g.id) == 0; }), m.groups.end());
}
// A new (empty) group at the end; 0 when kMaxGroups exist. The name is cleaned and made unique.
inline int create(Model& m, const std::string& name, int colourIndex, bool collapsed = false)
{
    if (int(m.groups.size()) >= kMaxGroups) return 0;
    Group g;
    g.id = m.nextId++;
    g.name = uniqueName(m, cleanName(name, defaultName(m)));
    g.colour = clampColour(colourIndex);
    g.collapsed = collapsed;
    m.groups.push_back(std::move(g));
    return m.groups.back().id;
}
// Moves `tab` into group `id` (out of any other; a group left empty goes). False: no such group.
inline bool add(Model& m, const void* tab, int id)
{
    if (!tab || indexOf(m, id) < 0) return false;
    for (auto& e : m.member) if (e.first == tab) { e.second = id; dropEmpty(m); return true; }
    m.member.emplace_back(tab, id);
    return true;
}
// Takes `tab` out of its group (an emptied group goes); returns the old group id, 0 when it had none.
inline int remove(Model& m, const void* tab)
{
    const int id = groupOf(m, tab);
    if (!id) return 0;
    m.member.erase(std::remove_if(m.member.begin(), m.member.end(), [tab](const std::pair<const void*, int>& e) { return e.first == tab; }), m.member.end());
    dropEmpty(m);
    return id;
}
// "Ungroup": the group goes, its tabs stay open (ungrouped). Returns how many tabs it had.
inline int ungroup(Model& m, int id)
{
    const int n = count(m, id);
    m.member.erase(std::remove_if(m.member.begin(), m.member.end(), [id](const std::pair<const void*, int>& e) { return e.second == id; }), m.member.end());
    m.groups.erase(std::remove_if(m.groups.begin(), m.groups.end(), [id](const Group& g) { return g.id == id; }), m.groups.end());
    return n;
}
inline bool rename(Model& m, int id, const std::string& raw)   // false: empty name or no such group (the old name stays)
{
    const int i = indexOf(m, id);
    const std::string n = cleanName(raw, std::string());
    if (i < 0 || n.empty()) return false;
    m.groups[size_t(i)].name = uniqueName(m, n, id);
    return true;
}
inline int stepColour(Model& m, int id, int delta)
{
    const int i = indexOf(m, id);
    if (i < 0) return -1;
    Group& g = m.groups[size_t(i)];
    g.colour = clampColour(g.colour + delta);
    return g.colour;
}
inline bool toggleCollapsed(Model& m, int id)
{
    const int i = indexOf(m, id);
    if (i < 0) return false;
    m.groups[size_t(i)].collapsed = !m.groups[size_t(i)].collapsed;
    return m.groups[size_t(i)].collapsed;
}
// Keeps only the members in `eligible` (open, not private, not pinned); groups left empty go.
inline void prune(Model& m, const std::vector<const void*>& eligible)
{
    m.member.erase(std::remove_if(m.member.begin(), m.member.end(), [&eligible](const std::pair<const void*, int>& e) {
        return std::find(eligible.begin(), eligible.end(), e.first) == eligible.end(); }), m.member.end());
    m.member.erase(std::remove_if(m.member.begin(), m.member.end(), [&m](const std::pair<const void*, int>& e) { return indexOf(m, e.second) < 0; }), m.member.end());
    dropEmpty(m);
}

// --- order / Tabs panel rows -----------------------------------------------------------------------------------------
// groupPos per tab: the display index of its group, -1 none. The order that puts pinned tabs first, then each group
// (in display order), then the ungrouped tabs; every part keeps its order.
inline std::vector<size_t> order(const std::vector<bool>& pinned, const std::vector<int>& groupPos)
{
    std::vector<size_t> idx(pinned.size());
    std::iota(idx.begin(), idx.end(), size_t(0));
    auto key = [&](size_t i) {
        if (pinned[i]) return 0;
        const int p = i < groupPos.size() ? groupPos[i] : -1;
        return p >= 0 ? 1 + p : 1 + kMaxGroups;
    };
    std::stable_sort(idx.begin(), idx.end(), [&](size_t a, size_t b) { return key(a) < key(b); });
    return idx;
}
inline bool isIdentity(const std::vector<size_t>& o)
{
    for (size_t i = 0; i < o.size(); ++i) if (o[i] != i) return false;
    return true;
}
// The Tabs panel's tab part: >= 0 a tab row (its index), < 0 the header of group -1 - value. A header comes before its
// group's first tab; a collapsed group's tabs have no rows.
inline std::vector<int> panelRows(const std::vector<int>& groupPos, const std::vector<bool>& collapsed)
{
    std::vector<int> out;
    int last = -1;
    for (size_t i = 0; i < groupPos.size(); ++i) {
        const int p = groupPos[i];
        if (p >= 0 && p != last) out.push_back(-1 - p);
        last = p;
        if (p >= 0 && size_t(p) < collapsed.size() && collapsed[size_t(p)]) continue;
        out.push_back(int(i));
    }
    return out;
}

// --- tab memory ----------------------------------------------------------------------------------------------------
// omniTmUnloadOne: is candidate a unloaded before b? Unpinned before pinned (OMNI_PINNED_TABS_V1), then a collapsed
// group's tabs before the others, then the least recently shown.
inline bool unloadsBefore(bool aPinned, bool aCollapsed, uint32_t aShownAt, bool bPinned, bool bCollapsed, uint32_t bShownAt)
{
    if (aPinned != bPinned) return !aPinned;
    if (aCollapsed != bCollapsed) return aCollapsed;
    return aShownAt < bShownAt;
}

// --- session lines (session.txt and sessions.txt) --------------------------------------------------------------------
// payload: "<group no>\t<colour>\t<collapsed 0|1>\t<name>"; line: "group\t<tab index>\t<payload>\n". Older builds skip
// the line (they restore the tabs ungrouped).
struct Mark { int index = -1, group = 0, colour = 0; bool collapsed = false; std::string name; };
inline std::string payload(int groupNo, int colourIndex, bool collapsed, const std::string& name)
{
    return std::to_string(std::clamp(groupNo, 0, 99)) + "\t" + std::to_string(clampColour(colourIndex)) + "\t" + (collapsed ? "1" : "0") + "\t"
        + cleanName(name, "Group " + std::to_string(std::clamp(groupNo, 0, 99) + 1));
}
inline std::string line(int index, const std::string& p) { return std::string(kLinePrefix) + std::to_string(index) + "\t" + p + "\n"; }
inline bool digits(const std::string& s, size_t maxLen, int& v)
{
    if (s.empty() || s.size() > maxLen) return false;
    v = 0;
    for (char c : s) { if (c < '0' || c > '9') return false; v = v * 10 + (c - '0'); }
    return true;
}
inline bool parsePayload(const std::string& p0, Mark& k)
{
    std::string p = p0;
    while (!p.empty() && (p.back() == '\r' || p.back() == '\n')) p.pop_back();
    if (p.size() > kPayloadMax + 200) return false;
    std::string f[3];
    size_t pos = 0;
    for (int i = 0; i < 3; ++i) {
        const size_t t = p.find('\t', pos);
        if (t == std::string::npos) return false;
        f[i] = p.substr(pos, t - pos);
        pos = t + 1;
    }
    Mark m;
    int c = 0;
    if (!digits(f[0], 2, m.group) || !digits(f[1], 2, c) || (f[2] != "0" && f[2] != "1")) return false;
    m.colour = clampColour(c);
    m.collapsed = f[2] == "1";
    m.name = cleanName(p.substr(pos), "Group " + std::to_string(m.group + 1));
    m.index = k.index;
    k = m;
    return true;
}
inline bool parseLine(const std::string& line0, Mark& k)
{
    std::string s = line0;
    while (!s.empty() && (s.back() == '\r' || s.back() == '\n')) s.pop_back();
    const std::string pre = kLinePrefix;
    if (s.compare(0, pre.size(), pre) != 0) return false;
    const size_t t = s.find('\t', pre.size());
    if (t == std::string::npos) return false;
    int index = 0;
    if (!digits(s.substr(pre.size(), t - pre.size()), 4, index)) return false;
    Mark m;
    if (!parsePayload(s.substr(t + 1), m)) return false;
    m.index = index;
    k = m;
    return true;
}
// Puts the listed tabs (marks' indexes into `tabs`) into groups: one group per group number (first appearance), or
// an existing group of the same name; at most kMaxGroups (the rest stay ungrouped); a tab listed twice, already in a
// group, or not eligible (private) is skipped. Returns how many tabs were grouped.
inline int restore(Model& m, const std::vector<Mark>& marks, const std::vector<const void*>& tabs, const std::vector<bool>& eligible)
{
    std::vector<std::pair<int, int>> made;   // group number -> model id
    int n = 0;
    for (const Mark& k : marks) {
        if (k.index < 0 || size_t(k.index) >= tabs.size() || size_t(k.index) >= eligible.size()) continue;
        const void* tab = tabs[size_t(k.index)];
        if (!tab || !eligible[size_t(k.index)] || groupOf(m, tab)) continue;
        int id = 0;
        for (auto& e : made) if (e.first == k.group) id = e.second;
        if (!id) {
            for (auto& g : m.groups) if (sameName(g.name, k.name)) { id = g.id; break; }
            if (!id) id = create(m, k.name, k.colour, k.collapsed);
            if (!id) continue;
            made.emplace_back(k.group, id);
        }
        if (add(m, tab, id)) ++n;
    }
    return n;
}

// --- texts ---------------------------------------------------------------------------------------------------------
inline std::string tabsText(int n) { return std::to_string(n) + (n == 1 ? " tab" : " tabs"); }
inline std::string headerValue(int n, bool collapsed, bool current)
{
    std::string v = tabsText(n);
    if (collapsed) v += current ? " \xc2\xb7 collapsed, current tab inside" : " \xc2\xb7 collapsed";
    return v;
}
inline std::string addedNotice(const std::string& name, int n) { return "Added to \"" + name + "\" (" + tabsText(n) + ")"; }
inline std::string newNotice(const std::string& name, int groups) { return "New group \"" + name + "\" (" + std::to_string(groups) + " of " + std::to_string(kMaxGroups) + ")"; }
inline std::string removedNotice(const std::string& name) { return "Removed from \"" + name + "\""; }
inline std::string ungroupNotice(const std::string& name, int n) { return "Ungrouped \"" + name + "\": " + (n == 1 ? std::string("its tab stays") : "its " + tabsText(n) + " stay") + " open"; }
inline const char* collapseFace(bool collapsed) { return collapsed ? "Expand" : "Collapse"; }

} // namespace OmniTabGroups
'''

SHELL = r'''// OMNI_TAB_GROUPS_V1: tab groups (shell side). Included from OmniFeatures3.h after OmniSiteClearShell.h (inside
// OmniBrowser.cpp's anonymous namespace); declared in OmniFeatures3Decl.h for the earlier hooks. The pure part is
// OmniTabGroups.h; the reasons are in tools/apply_tab_groups.py. Main thread only. Groups hold Tab pointers (forgotten
// in omniFxTabClosing), so the Tab struct is not touched; the tabs vector is kept as: pinned, groups, ungrouped.
#pragma once

namespace OTG = OmniTabGroups;
static OTG::Model omniTgModel;
static std::vector<OTG::Mark> omniTgRestoreMarks;   // session.txt "group" lines, until the tabs exist
static const void* omniTgFocus = nullptr;           // Tabs panel: put the highlight on this tab's row at the next build
static int omniTgFocusRow = -1;                     // ... or keep this row (a tab row's Square)
static const void* omniTgMenuTab = nullptr;         // the tab the Group menu is for
static const void* omniTgHoldTab = nullptr;         // hold Cross on a Tabs panel tab row
static bool omniTgHolding = false;
static std::string omniTgNameBuf;
static int omniTgNameId = 0;
enum { omniTgHeaderRow = 470 };                     // Tabs panel: group headers 470..477 (tabs 0..15, 100..102, 110, 111)
enum { omniTgMenuNone = 1, omniTgMenuNew = 2, omniTgMenuRemove = 3, omniTgMenuAdd = 10 };   // Group menu (10..17: groups)

static bool omniTgEligible(const Tab& t) { return !t.omniPrivate && !omniPtPinned(t); }
static Tab* omniTgTab(const void* p) { for (auto& t : tabs) if (t.get() == p) return t.get(); return nullptr; }
static std::vector<int> omniTgPositions()
{
    std::vector<int> pos;
    for (auto& t : tabs) pos.push_back(OTG::indexOf(omniTgModel, OTG::groupOf(omniTgModel, t.get())));
    return pos;
}
// Drops closed / private / pinned members and empty groups, then orders the tabs: pinned, groups, ungrouped
// (`selected` follows its tab). Nothing moves while no group exists.
static void omniTgNormalize()
{
    if (omniTgModel.groups.empty() && omniTgModel.member.empty()) return;
    std::vector<const void*> keep;
    for (auto& t : tabs) if (omniTgEligible(*t)) keep.push_back(t.get());
    OTG::prune(omniTgModel, keep);
    if (omniTgModel.groups.empty()) return;
    std::vector<bool> pinned;
    for (auto& t : tabs) pinned.push_back(omniPtPinned(*t));
    const std::vector<size_t> ord = OTG::order(pinned, omniTgPositions());
    if (OTG::isIdentity(ord)) return;
    const void* shown = active();
    std::vector<std::unique_ptr<Tab>> next;
    next.reserve(tabs.size());
    for (size_t i : ord) next.push_back(std::move(tabs[i]));
    tabs = std::move(next);
    for (size_t i = 0; i < tabs.size(); ++i) if (tabs[i].get() == shown) selected = i;
    omniShellDirty = true;
}
static void omniTgForget(const void* tab)
{
    OTG::remove(omniTgModel, tab);
    if (omniTgMenuTab == tab) omniTgMenuTab = nullptr;
    if (omniTgHoldTab == tab) { omniTgHoldTab = nullptr; omniTgHolding = false; }
    if (omniTgFocus == tab) omniTgFocus = nullptr;
}
static bool omniTgCollapsedTab(const Tab& t) { return OTG::collapsedTab(omniTgModel, &t); }

// --- session.txt (omniSessionText / omniEverydayStart) and sessions.txt (OmniTabSessionsShell.h) -----------------------
static std::string omniTgPayload(const Tab& t)
{
    if (!omniTgEligible(t)) return std::string();
    const int pos = OTG::indexOf(omniTgModel, OTG::groupOf(omniTgModel, &t));
    if (pos < 0) return std::string();
    const OTG::Group& g = omniTgModel.groups[size_t(pos)];
    return OTG::payload(pos, g.colour, g.collapsed, g.name);
}
static std::string omniTgSessionLine(const Tab& t, int savedIndex)
{
    const std::string p = omniTgPayload(t);
    return p.empty() ? std::string() : OTG::line(savedIndex, p);
}
static bool omniTgRestoreLine(const std::string& line)
{
    OTG::Mark k;
    if (!OTG::parseLine(line, k)) return false;
    if (omniTgRestoreMarks.size() < 64) omniTgRestoreMarks.push_back(k);
    return true;
}
// OMNI_TAB_GROUPS_V1_R2: membership only, nothing is reordered here. The "group" and "pinned" lines both index the
// tabs in file order, so omniEverydayStart calls this, then omniPtRestoreApply (which still sees file order), then
// omniTgNormalize once (pinned, groups, ungrouped) with `sel` following its tab. (r1 normalized here, before pinning:
// groups moved first, so "pinned\t0" could pin a grouped tab, which then left its group, and that layout was saved.)
static void omniTgRestoreApply(int& /*sel*/)
{
    if (omniTgRestoreMarks.empty() || tabs.empty()) { omniTgRestoreMarks.clear(); return; }
    std::vector<const void*> ptrs;
    std::vector<bool> ok;
    for (auto& t : tabs) { ptrs.push_back(t.get()); ok.push_back(!t->omniPrivate); }
    const int n = OTG::restore(omniTgModel, omniTgRestoreMarks, ptrs, ok);
    omniTgRestoreMarks.clear();
    if (n) fprintf(stderr, "OMNI TAB GROUPS: restored %d tab(s) in %zu group(s)\n", n, omniTgModel.groups.size());
}
// A saved session was opened: made[j] shows s.tabs[open[j]]; their "group" payloads regroup them (a group of the same
// name joins the open one; past 8 groups they stay ungrouped).
static void omniTgSessionOpened(const OmniTabSessions::Session& s, const std::vector<int>& open, const std::vector<Tab*>& made)
{
    std::vector<OTG::Mark> marks;
    std::vector<const void*> ptrs;
    std::vector<bool> ok;
    for (size_t j = 0; j < made.size() && j < open.size(); ++j) {
        ptrs.push_back(made[j]);
        ok.push_back(made[j] && !made[j]->omniPrivate);
        const size_t si = size_t(open[j]);
        if (si >= s.tabs.size() || s.tabs[si].group.empty()) continue;
        OTG::Mark k;
        if (!OTG::parsePayload(s.tabs[si].group, k)) continue;
        k.index = int(j);
        marks.push_back(k);
    }
    if (marks.empty()) return;
    const int n = OTG::restore(omniTgModel, marks, ptrs, ok);
    omniTgNormalize();
    fprintf(stderr, "OMNI TAB GROUPS: session \"%s\": %d tab(s) grouped\n", s.name.c_str(), n);
}

// --- Group menu (hold Cross on a Tabs panel tab row) ----------------------------------------------------------------
static void omniTgName(int id, const char* label)
{
    const int i = OTG::indexOf(omniTgModel, id);
    if (i < 0) return;
    omniTgNameId = id;
    omniTgNameBuf = omniTgModel.groups[size_t(i)].name;
    omniKbEdit(&omniTgNameBuf, label, [](bool ok) {
        if (ok && OTG::rename(omniTgModel, omniTgNameId, omniTgNameBuf)) {
            const int at = OTG::indexOf(omniTgModel, omniTgNameId);
            if (at >= 0) notice("Group named \"" + omniTgModel.groups[size_t(at)].name + "\"");
        }
        omniTgNameId = 0;
        omniFxRefresh();
    });
}
static void omniTgMenuBuild(OmniFxPanel& p)
{
    const Tab* t = omniTgTab(omniTgMenuTab);
    auto refusal = [&p](const std::string& text) { OmniFxRow r; r.id = omniTgMenuNone; r.label = text; r.enabled = false; p.rows.push_back(r); };
    if (!t) { refusal("This tab was closed"); return; }
    p.subtitle = !t->title.empty() ? t->title : !t->url.empty() ? omniShownURL(t->url) : std::string("New tab");
    const OTG::Check c = OTG::canJoin(t->omniPrivate, omniPtPinned(*t));
    if (c != OTG::kOk) { refusal(OTG::refusal(c)); return; }
    const int cur = OTG::groupOf(omniTgModel, t);
    for (size_t i = 0; i < omniTgModel.groups.size(); ++i) {
        const OTG::Group& g = omniTgModel.groups[i];
        if (g.id == cur) continue;
        OmniFxRow r; r.id = omniTgMenuAdd + int(i);
        r.label = "Add to \"" + g.name + "\""; r.detail = OTG::colourName(g.colour);
        r.value = OTG::tabsText(OTG::count(omniTgModel, g.id));
        p.rows.push_back(r);
    }
    OmniFxRow n; n.id = omniTgMenuNew; n.label = "New group\xe2\x80\xa6"; n.icon = omniIconPlus;
    n.enabled = int(omniTgModel.groups.size()) < OTG::kMaxGroups;
    n.value = n.enabled ? OTG::defaultName(omniTgModel) : OTG::refusal(OTG::kFull);
    p.rows.push_back(n);
    if (cur) {
        const int at = OTG::indexOf(omniTgModel, cur);
        OmniFxRow r; r.id = omniTgMenuRemove; r.icon = omniIconClose;
        r.label = "Remove from \"" + (at >= 0 ? omniTgModel.groups[size_t(at)].name : std::string()) + "\"";
        p.rows.push_back(r);
    }
    p.corner = std::to_string(omniTgModel.groups.size()) + " of " + std::to_string(OTG::kMaxGroups) + " groups";
}
static bool omniTgMenuInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (!r.enabled) return true;
    Tab* t = omniTgTab(omniTgMenuTab);
    if (!t) { omniFxPop(); return true; }
    const OTG::Check c = OTG::canJoin(t->omniPrivate, omniPtPinned(*t));
    if (c != OTG::kOk) { notice(OTG::refusal(c)); return true; }
    if (r.id == omniTgMenuNew) {
        const int id = OTG::create(omniTgModel, OTG::defaultName(omniTgModel), OTG::nextColour(omniTgModel));
        if (!id) { notice(OTG::refusal(OTG::kFull)); return true; }
        OTG::add(omniTgModel, t, id);
        omniTgNormalize();
        const int at = OTG::indexOf(omniTgModel, id);
        if (at >= 0) notice(OTG::newNotice(omniTgModel.groups[size_t(at)].name, int(omniTgModel.groups.size())));
        fprintf(stderr, "OMNI TAB GROUPS: new group, %zu group(s)\n", omniTgModel.groups.size());
        omniTgFocus = t;
        omniFxPop();
        omniTgName(id, "Group name");   // Go keeps the typed name, Cancel the default ("Group 1" ...)
        return true;
    }
    if (r.id == omniTgMenuRemove) {
        const OTG::Group* g = OTG::groupFor(omniTgModel, t);
        const std::string name = g ? g->name : std::string();
        OTG::remove(omniTgModel, t);
        omniTgNormalize();
        notice(OTG::removedNotice(name));
        omniTgFocus = t;
        omniFxPop();
        return true;
    }
    const int pos = r.id - omniTgMenuAdd;
    if (pos < 0 || pos >= int(omniTgModel.groups.size())) return true;
    OTG::Group& g = omniTgModel.groups[size_t(pos)];
    const int id = g.id;
    g.collapsed = false;   // the tab just added stays in sight
    OTG::add(omniTgModel, t, id);
    omniTgNormalize();
    const int at = OTG::indexOf(omniTgModel, id);
    if (at >= 0) notice(OTG::addedNotice(omniTgModel.groups[size_t(at)].name, OTG::count(omniTgModel, id)));
    omniTgFocus = t;
    omniFxPop();
    return true;
}
static void omniTgMenuShow(const void* tab)
{
    omniTgMenuTab = tab;
    OmniFxPanel p;
    p.title = "Tab group"; p.w = 820; p.maxVisible = 8;
    p.build = omniTgMenuBuild; p.input = omniTgMenuInput;
    p.faces = { { 0, "Choose" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}
// OmniFeatures.h omniFxButtonEvent / omniFxTick: hold Cross on a tab row of the Tabs panel opens the Group menu (a short
// press still switches, on release, as on a page).
static bool omniTgHoldEligible()
{
    omniTgHolding = false; omniTgHoldTab = nullptr;
    if (omniTestMode() || editing || omniFxStack.empty()) return false;
    const OmniFxPanel& p = omniFxStack.back();
    if (p.build != omniFxTabsBuild || p.sel < 0 || p.sel >= int(p.rows.size())) return false;
    const int id = p.rows[size_t(p.sel)].id;
    if (id < 0 || id >= int(tabs.size())) return false;
    omniTgHoldTab = tabs[size_t(id)].get();
    omniTgHolding = true;
    return true;
}
static bool omniTgHoldFire()
{
    if (!omniTgHolding) return false;
    omniTgHolding = false;
    if (!omniFxStack.empty() && omniFxStack.back().build == omniFxTabsBuild && omniTgTab(omniTgHoldTab)) omniTgMenuShow(omniTgHoldTab);
    omniTgHoldTab = nullptr;
    return true;
}

// --- Tabs panel (OmniTabsPage.h) ---------------------------------------------------------------------------------------
static int omniTgTabOfRow(const OmniFxPanel& p, int row)
{
    if (row < 0 || row >= int(p.rows.size())) return -1;
    const int id = p.rows[size_t(row)].id;
    return id >= 0 && id < int(tabs.size()) ? id : -1;
}
static int omniTgRowOfTab(const OmniFxPanel& p, size_t tab)
{
    for (size_t i = 0; i < p.rows.size(); ++i) if (p.rows[i].id == int(tab)) return int(i);
    if (tab < tabs.size()) {   // hidden in a collapsed group: its header
        const int pos = OTG::indexOf(omniTgModel, OTG::groupOf(omniTgModel, tabs[tab].get()));
        for (size_t i = 0; pos >= 0 && i < p.rows.size(); ++i) if (p.rows[i].id == omniTgHeaderRow + pos) return int(i);
    }
    return std::min(int(tab), std::max(0, int(p.rows.size()) - 1));
}
// Right after the tab rows were built (rows 0 .. tabs-1, id = tab index): group headers go in, a collapsed group's
// tab rows go out; the highlight follows a tab that moved (pin) or stays on its row (close).
static void omniTgTabRows(OmniFxPanel& p)
{
    const size_t n = std::min(tabs.size(), p.rows.size());
    if (!omniTgModel.groups.empty()) {
        std::vector<bool> collapsed;
        for (auto& g : omniTgModel.groups) collapsed.push_back(g.collapsed);
        const std::vector<int> layout = OTG::panelRows(omniTgPositions(), collapsed);
        std::vector<OmniFxRow> out;
        out.reserve(p.rows.size() + omniTgModel.groups.size());
        for (int e : layout) {
            if (e >= 0) { if (size_t(e) < n) out.push_back(p.rows[size_t(e)]); continue; }
            const int pos = -1 - e;
            const OTG::Group& g = omniTgModel.groups[size_t(pos)];
            const bool current = selected < tabs.size() && OTG::groupOf(omniTgModel, tabs[selected].get()) == g.id;
            OmniFxRow h; h.id = omniTgHeaderRow + pos;
            h.label = g.name; h.detail = OTG::colourName(g.colour);
            h.value = OTG::headerValue(OTG::count(omniTgModel, g.id), g.collapsed, current);
            out.push_back(h);
        }
        out.insert(out.end(), p.rows.begin() + long(n), p.rows.end());
        p.rows = std::move(out);
    }
    if (omniTgFocus) { for (size_t i = 0; i < tabs.size(); ++i) if (tabs[i].get() == omniTgFocus) p.sel = omniTgRowOfTab(p, i); }
    else if (omniTgFocusRow >= 0) p.sel = omniTgFocusRow;
    omniTgFocus = nullptr; omniTgFocusRow = -1;
}
static bool omniTgTabsInput(OmniFxPanel& p, const OmniFxRow& r, int b)
{
    if (r.id >= 0 && r.id < int(tabs.size())) {   // a tab row: the others act; the highlight is put right afterwards
        if (b == SDL_CONTROLLER_BUTTON_DPAD_LEFT || b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT) omniTgFocus = tabs[size_t(r.id)].get();
        else if (b == SDL_CONTROLLER_BUTTON_X) omniTgFocusRow = p.sel;
        return false;
    }
    const int pos = r.id - omniTgHeaderRow;
    if (pos < 0 || pos >= OTG::kMaxGroups) return false;
    if (pos >= int(omniTgModel.groups.size())) return true;
    OTG::Group& g = omniTgModel.groups[size_t(pos)];
    switch (b) {
    case SDL_CONTROLLER_BUTTON_A:
        OTG::toggleCollapsed(omniTgModel, g.id);
        omniShellDirty = true;
        return true;
    case SDL_CONTROLLER_BUTTON_Y: omniTgName(g.id, "Rename group"); return true;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT:
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT:
        OTG::stepColour(omniTgModel, g.id, b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT ? 1 : -1);
        omniShellDirty = true;
        return true;
    case SDL_CONTROLLER_BUTTON_X: {
        const std::string name = g.name;
        const int k = OTG::ungroup(omniTgModel, g.id);
        notice(OTG::ungroupNotice(name, k));
        omniShellDirty = true;
        return true;
    }
    default: return false;
    }
}
static void omniTgTabFaces(OmniFxPanel& p)
{
    p.extra.clear();
    if (p.sel < 0 || p.sel >= int(p.rows.size())) return;
    const OmniFxRow& r = p.rows[size_t(p.sel)];
    const int pos = r.id - omniTgHeaderRow;
    if (pos >= 0 && pos < int(omniTgModel.groups.size())) {
        p.faces = { { 0, OTG::collapseFace(omniTgModel.groups[size_t(pos)].collapsed) }, { 3, "Rename" }, { omniHintDpadH, "Colour" }, { 2, "Ungroup" }, { 1, "Back" } };
        return;
    }
    if (r.id >= 0 && r.id < int(tabs.size()) && !tabs[size_t(r.id)]->omniPrivate) p.extra = "Hold Cross: group";
}
// omniFxDrawPanel: a colour square on group header rows (Tabs panel, Group menu; true: the label moves right) and a
// colour bar beside a grouped tab's row.
static bool omniTgRowMark(const OmniFxPanel& p, const OmniFxRow& r, int x, int y, int h)
{
    if (omniTgModel.groups.empty()) return false;
    int pos = -1;
    bool square = false;
    if (p.build == omniFxTabsBuild) {
        if (r.id >= omniTgHeaderRow && r.id < omniTgHeaderRow + OTG::kMaxGroups) { pos = r.id - omniTgHeaderRow; square = true; }
        else if (r.id >= 0 && r.id < int(tabs.size())) pos = OTG::indexOf(omniTgModel, OTG::groupOf(omniTgModel, tabs[size_t(r.id)].get()));
    } else if (p.build == omniTgMenuBuild && r.id >= omniTgMenuAdd && r.id < omniTgMenuAdd + OTG::kMaxGroups) { pos = r.id - omniTgMenuAdd; square = true; }
    if (pos < 0 || pos >= int(omniTgModel.groups.size())) return false;
    const OTG::Rgb c = OTG::colour(omniTgModel.groups[size_t(pos)].colour);
    const SDL_Color col { c.r, c.g, c.b, 255 };
    const int cy = y + h / 2;
    if (square) {
        fillRounded(x + 31, cy - 11, 22, 22, 6, col);
        return true;
    }
    fillRounded(x + 18, y + 10, 5, h - 20, 2, col);
    return false;
}
'''

PT_CALL = '    omniPtRestoreApply(sel); // OMNI_PINNED_TABS_V1: pin the listed tabs (first), `sel` follows its tab\n'
# omniEverydayStart: group by file-order index, then pin by file-order index, then the order once (r2). r1 had only its
# first line before PT_CALL and reordered inside omniTgRestoreApply (see OMNI_TAB_GROUPS_V1_R2 in the shell).
CALL_R1 = ('    omniTgRestoreApply(sel); // OMNI_TAB_GROUPS_V1: group the listed tabs (before pinning moves them: indexes are file order)\n'
           + PT_CALL)
CALL_R2 = ('    omniTgRestoreApply(sel); // OMNI_TAB_GROUPS_V1: group the listed tabs (indexes are file order; nothing moves yet)\n'
           + PT_CALL
           + '    if (!tabs.empty()) { const void* omniTgShown = tabs[size_t(std::clamp(sel, 0, int(tabs.size()) - 1))].get(); omniTgNormalize();'
             ' for (size_t i = 0; i < tabs.size(); ++i) if (tabs[i].get() == omniTgShown) sel = int(i); }'
             ' // OMNI_TAB_GROUPS_V1_R2: then the order once (pinned, groups, ungrouped); `sel` follows its tab\n')

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniPinnedTabs.h" // OMNI_PINNED_TABS_V1: pinned tabs: order, unload order, strip, session line (pure)\n',
         '#include "OmniPinnedTabs.h" // OMNI_PINNED_TABS_V1: pinned tabs: order, unload order, strip, session line (pure)\n'
         '#include "OmniTabGroups.h" // OMNI_TAB_GROUPS_V1: tab groups: order, panel rows, unload order, session line (pure)\n'),
        ('        if (omniPtPinned(t)) s += OmniPinnedTabs::pinnedLine(n); // OMNI_PINNED_TABS_V1: "pinned\\t<n>" (older builds skip it)\n',
         '        if (omniPtPinned(t)) s += OmniPinnedTabs::pinnedLine(n); // OMNI_PINNED_TABS_V1: "pinned\\t<n>" (older builds skip it)\n'
         '        s += omniTgSessionLine(t, n); // OMNI_TAB_GROUPS_V1: "group\\t<n>\\t<group>\\t<colour>\\t<collapsed>\\t<name>" (older builds skip it)\n'),
        ('            } else if (omniPtRestoreLine(s)) { // OMNI_PINNED_TABS_V1: "pinned\\t<index>"\n',
         '            } else if (omniPtRestoreLine(s)) { // OMNI_PINNED_TABS_V1: "pinned\\t<index>"\n'
         '            } else if (omniTgRestoreLine(s)) { // OMNI_TAB_GROUPS_V1: "group\\t<index>\\t..."\n'),
        (PT_CALL, CALL_R2),
    ],
    'OmniFeatures3Decl.h': [
        ('static bool omniPtStripClick(int x);\n',
         'static bool omniPtStripClick(int x);\n'
         '// OMNI_TAB_GROUPS_V1 (OmniTabGroupsShell.h): tab groups\n'
         'static void omniTgForget(const void* tab);                 // omniFxTabClosing\n'
         'static bool omniTgCollapsedTab(const Tab& t);              // omniTmUnloadOne: a collapsed group\'s tabs go first\n'
         'static std::string omniTgSessionLine(const Tab& t, int savedIndex);   // omniSessionText\n'
         'static bool omniTgRestoreLine(const std::string& line);    // omniEverydayStart: a "group" line\n'
         'static void omniTgRestoreApply(int& sel);\n'
         'static std::string omniTgPayload(const Tab& t);            // sessions.txt: the tab\'s "group" payload\n'
         'static void omniTgSessionOpened(const OmniTabSessions::Session& s, const std::vector<int>& open, const std::vector<Tab*>& made);\n'
         'static void omniTgNormalize();                             // order: pinned, groups, ungrouped\n'
         'static void omniTgTabRows(OmniFxPanel& p);                 // Tabs panel\n'
         'static bool omniTgTabsInput(OmniFxPanel& p, const OmniFxRow& r, int b);\n'
         'static void omniTgTabFaces(OmniFxPanel& p);\n'
         'static int omniTgTabOfRow(const OmniFxPanel& p, int row);\n'
         'static int omniTgRowOfTab(const OmniFxPanel& p, size_t tab);\n'
         'static bool omniTgHoldEligible();                          // hold Cross on a Tabs panel tab row\n'
         'static bool omniTgHoldFire();\n'
         'static bool omniTgRowMark(const OmniFxPanel& p, const OmniFxRow& r, int x, int y, int h);   // omniFxDrawPanel: colours\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n',
         '#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n'
         '#include "OmniTabGroupsShell.h" // OMNI_TAB_GROUPS_V1\n'),
    ],
    'OmniTabMemory.h': [
        ('        if (!best || OmniPinnedTabs::unloadsBefore(omniPtPinned(*t), at, omniPtPinned(*best), oldest)) { best = t.get(); oldest = at; } // OMNI_PINNED_TABS_V1: pinned tabs last\n',
         '        if (!best || OmniTabGroups::unloadsBefore(omniPtPinned(*t), omniTgCollapsedTab(*t), at, omniPtPinned(*best), omniTgCollapsedTab(*best), oldest)) { best = t.get(); oldest = at; } // OMNI_PINNED_TABS_V1: pinned tabs last; OMNI_TAB_GROUPS_V1: then collapsed groups\' tabs first\n'),
    ],
    'OmniTabsPage.h': [
        ('    omniPtForget(&tab); // OMNI_PINNED_TABS_V1\n',
         '    omniPtForget(&tab); // OMNI_PINNED_TABS_V1\n'
         '    omniTgForget(&tab); // OMNI_TAB_GROUPS_V1\n'),
        ('static void omniFxTabsBuild(OmniFxPanel& p)\n{\n    for (size_t i = 0; i < tabs.size(); ++i) {\n',
         'static void omniFxTabsBuild(OmniFxPanel& p)\n{\n'
         '    omniTgNormalize(); // OMNI_TAB_GROUPS_V1: pinned, groups, ungrouped (before the rows read the order)\n'
         '    for (size_t i = 0; i < tabs.size(); ++i) {\n'),
        ('    OmniFxRow n; n.id = omniFxTabNew;',
         '    omniTgTabRows(p); // OMNI_TAB_GROUPS_V1: group header rows; a collapsed group\'s tabs have none\n'
         '    OmniFxRow n; n.id = omniFxTabNew;'),
        ('    omniTaTabFaces(p); // OMNI_TAB_AUDIO_V1: Triangle "Mute tab" / "Unmute tab" on tab rows\n'
         '    omniPtTabFaces(p); // OMNI_PINNED_TABS_V1: D-pad left / right "Pin" / "Unpin"\n',
         '    const int omniTgSel = p.sel; p.sel = omniTgTabOfRow(p, p.sel); // OMNI_TAB_GROUPS_V1: the two below read p.sel as a tab index\n'
         '    omniTaTabFaces(p); // OMNI_TAB_AUDIO_V1: Triangle "Mute tab" / "Unmute tab" on tab rows\n'
         '    omniPtTabFaces(p); // OMNI_PINNED_TABS_V1: D-pad left / right "Pin" / "Unpin"\n'
         '    p.sel = omniTgSel;\n'
         '    omniTgTabFaces(p); // OMNI_TAB_GROUPS_V1: header rows: Collapse / Rename / Colour / Ungroup; "Hold Cross: group"\n'),
        ('static bool omniFxTabsInput(OmniFxPanel& p, const OmniFxRow& r, int b)\n{\n',
         'static bool omniFxTabsInput(OmniFxPanel& p, const OmniFxRow& r, int b)\n{\n'
         '    if (omniTgTabsInput(p, r, b)) return true; // OMNI_TAB_GROUPS_V1: group headers; on tab rows it only notes the highlight\n'),
        ('    if (!omniFxStack.empty()) omniFxStack.back().sel = int(selected);\n',
         '    if (!omniFxStack.empty()) omniFxStack.back().sel = omniTgRowOfTab(omniFxStack.back(), selected); // OMNI_TAB_GROUPS_V1: rows are not tab indexes\n'),
    ],
    'OmniFeatures.h': [
        ('        if (h.active || !omniFxHoldEligible()) return false;\n',
         '        if (h.active || !(omniTgHoldEligible() || omniFxHoldEligible())) return false; // OMNI_TAB_GROUPS_V1: also a Tabs panel tab row\n'),
        ('        else if (SDL_GetTicks() - h.start >= 500) { h.fired = true; omniShellDirty = true; omniFxContextQuery(); }\n',
         '        else if (SDL_GetTicks() - h.start >= 500) { h.fired = true; omniShellDirty = true; if (!omniTgHoldFire()) omniFxContextQuery(); } // OMNI_TAB_GROUPS_V1: Tabs panel: the Group menu\n'),
    ],
    'OmniFeaturesPanel.h': [
        ('            if (r.icon >= 0) { omniIcon(r.icon, g.x + 42, cy, ink); lx = g.x + 66; }\n',
         '            if (r.icon >= 0) { omniIcon(r.icon, g.x + 42, cy, ink); lx = g.x + 66; }\n'
         '            if (omniTgRowMark(p, r, g.x, ry, p.rowH)) lx = g.x + 66; // OMNI_TAB_GROUPS_V1: group colour\n'),
    ],
    'OmniTabSessions.h': [
        ('struct Tab { std::string url, title; };\n',
         'struct Tab { std::string url, title; std::string group = std::string(); };   // OMNI_TAB_GROUPS_V1: group = its "group" line\'s payload (empty: none)\n'),
        ('struct Candidate { std::string url, title; bool priv = false, skip = false; };\n',
         'struct Candidate { std::string url, title; bool priv = false, skip = false; std::string group = std::string(); };   // OMNI_TAB_GROUPS_V1: group payload\n'),
        ('            s += "tab\\t" + oneLine(t.url, kUrlMax) + "\\t" + oneLine(t.title, kTitleMax) + "\\n";\n',
         '            s += "tab\\t" + oneLine(t.url, kUrlMax) + "\\t" + oneLine(t.title, kTitleMax) + "\\n";\n'
         '            if (!t.group.empty()) { // OMNI_TAB_GROUPS_V1: "group\\t<tab index>\\t<payload>" (older builds skip it)\n'
         '                std::string g = cut(t.group, 300);\n'
         '                for (auto& c : g) if (c == \'\\n\' || c == \'\\r\') c = \' \';\n'
         '                s += "group\\t" + std::to_string(k - 1) + "\\t" + g + "\\n";\n'
         '            }\n'),
        ('        } else if (open && line.rfind("tab\\t", 0) == 0) {\n',
         '        } else if (open && line.rfind("group\\t", 0) == 0) { // OMNI_TAB_GROUPS_V1: the tab it names must be the last one read\n'
         '            const size_t a = line.find(\'\\t\', 6);\n'
         '            if (a != std::string::npos && a > 6 && a < 11 && !out.back().tabs.empty() && line.find_first_not_of("0123456789", 6) == a\n'
         '                && atoi(line.substr(6, a - 6).c_str()) == int(out.back().tabs.size()) - 1)\n'
         '                out.back().tabs.back().group = cut(line.substr(a + 1), 300);\n'
         '        } else if (open && line.rfind("tab\\t", 0) == 0) {\n'),
        ('        if (!dup) out.push_back({ c.url, oneLine(c.title, kTitleMax) });\n',
         '        if (!dup) out.push_back({ c.url, oneLine(c.title, kTitleMax), c.group }); // OMNI_TAB_GROUPS_V1\n'),
    ],
    'OmniTabSessionsShell.h': [
        ('        TS::Candidate c; c.url = omniTsTabURL(t); c.title = t.title; c.priv = t.omniPrivate; c.skip = omniMediaOwns(t);\n',
         '        TS::Candidate c; c.url = omniTsTabURL(t); c.title = t.title; c.priv = t.omniPrivate; c.skip = omniMediaOwns(t);\n'
         '        c.group = omniTgPayload(t); // OMNI_TAB_GROUPS_V1: saved with the session\n'),
        ('    const int notOpened = int(plan.open.size() - made.size());\n',
         '    omniTgSessionOpened(s, plan.open, made); // OMNI_TAB_GROUPS_V1: the session\'s groups come back\n'
         '    const int notOpened = int(plan.open.size() - made.size());\n'),
    ],
}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


# r2 edits: only for files that already have MARK from r1 (a fresh apply writes the r2 text through EDITS); REV makes
# them idempotent.
EDITS_R2 = {
    'OmniBrowser.cpp': [(CALL_R1, CALL_R2)],
}


def skip(s, mark):
    return mark in s or (mark == REV and MARK not in s)


def check(name, edits, mark=MARK):
    s = (root / name).read_bytes().decode('utf-8')
    if skip(s, mark):
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits, mark=MARK):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if skip(s, mark):
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
    for need, f, tool in (('OMNI_PINNED_TABS_V1', 'OmniTabsPage.h', 'apply_pinned_tabs.py'),
                          ('OMNI_TAB_SESSIONS_V1', 'OmniFeatures3.h', 'apply_tab_sessions.py'),
                          ('OMNI_TAB_AUDIO_V1', 'OmniTabsPage.h', 'apply_tab_audio.py'),
                          ('OMNI_SITE_CLEAR_V1', 'OmniFeatures3.h', 'apply_site_clear.py')):
        if need not in (root / f).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (f, need, tool))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    for name, edits in EDITS_R2.items():
        check(name, edits, REV)
    msgs = [write_new('OmniTabGroups.h', PURE, 'OmniPinnedTabs.h'),
            write_new('OmniTabGroupsShell.h', SHELL, 'OmniPinnedTabsShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    msgs += [patch(name, edits, REV).replace(': ', ' (r2): ', 1) for name, edits in EDITS_R2.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK + ' (r2)')


main()
