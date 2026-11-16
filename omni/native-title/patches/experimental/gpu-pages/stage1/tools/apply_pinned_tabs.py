#!/usr/bin/env python3
"""OMNI_PINNED_TABS_V1 (2026-11-16): pinned tabs (roadmap R3-004; tab groups are not part of this).

What the user sees
  - Tabs panel (OmniTabsPage.h): on a tab row, D-pad left / right pins or unpins that tab (hint "Pin" / "Unpin" with
    the D-pad glyph, before "Close tab"). Cross (switch), Triangle (mute, OMNI_TAB_AUDIO_V1), Square (close) and the
    session rows (OMNI_TAB_SESSIONS_V1) keep their buttons; D-pad left / right did nothing on that panel before.
  - Hold-Cross page menu (OmniContextMenu.h): "Pin this tab" / "Unpin this tab" after "Reader view" (not shown in a
    private tab).
  - Pinned tabs always come first (pinning moves the tab to the end of the pinned group, unpinning to the first place
    after it). Tabs panel rows say "Pinned" / "Current, pinned". With any tab pinned the top strip draws pinned tabs
    as compact 52 px tiles (a pin mark + the site's initial, or the speaker when it makes sound; a spinner while
    loading) that never scroll away and have no close cross; the other tabs use the compact strip of OMNI_FEATURES_V3
    in the remaining width. Nothing pinned: both old strips are untouched.
  - Closing a pinned tab asks once (the gentler choice, not "unpin first"): the first Square (Tabs panel) or R3 says
    "Pinned tab: close again to close it" (the row turns red: "Square again: close"); the same close within 4 s
    closes it. Pinned tiles have no close cross.
  - Tab memory (OmniTabMemory.h): when a background tab has to be unloaded (more loaded than "Tabs kept loaded", or
    shell memory low), unpinned tabs go first (least recently shown first, as before); a pinned tab is unloaded only
    when no unpinned tab qualifies, so the limit of loaded tabs still holds.
  - Restart: the start-up session file (/data/omni/session.txt, OMNI_FEATURES_V3) gets a "pinned\\t<index>" line
    after each pinned tab's "tab" line. Older builds skip unknown lines (they restore the tabs, unpinned); files
    without the lines restore as before. Pinned tabs restore lazily like any other (only the shown tab loads).
  - Saved sessions (OMNI_TAB_SESSIONS_V1), "Replace the open tabs": pinned tabs stay open; only the unpinned tabs
    are closed; the room is the tab limit minus the pinned tabs and a session URL already open in a pinned tab counts
    as "already open". The Open panel's "Opens N, closes M" says the same. "Add" is unchanged.
  - Private tabs can never be pinned (the safer choice): Pin says "Private tabs can't be pinned" and the page menu
    has no row. Only web pages (http / https, not owned by the Media section) can be pinned. At most 6 pinned tabs.

Pure part: engine/entry/OmniPinnedTabs.h (no SDL/WebKit): checks, ordering, unload order, session-file line,
close arm, strip layout and hit test, texts, the Replace plan (uses OmniTabSessions.h, also pure).
Tested by tools/test_pinned_tabs.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_pinned_tabs.cpp -o t && ./t
Shell side: engine/entry/OmniPinnedTabsShell.h (included from OmniFeatures3.h right after OmniTabMemory.h, so the
session code after it sees omniPtSessionPlan / omniPtReplaceKeep). The pinned set is kept beside the tabs
(Tab pointers, forgotten in omniFxTabClosing), so the Tab struct is not touched.

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp      the OmniHttpsOnly.h include line; omniSessionText's "tab" line + "++n;"; the session restore
                       "selected" branch; "omniF3Restoring = false;" + "if (tabs.empty()) return false;" of
                       omniEverydayStart; the R3 closeTab() line of button().
  OmniFeatures3Decl.h  the omniTmSkipRestore / omniF3Restoring line (declarations after it).
  OmniFeatures3.h      the OmniTabMemory.h include line.
  OmniTabMemory.h      the "best / oldest" line of omniTmUnloadOne; the heads of omniF3DrawTabStrip and
                       omniF3TabStripClick (hand-over when a tab is pinned).
  OmniTabsPage.h       omniFxForgetTab(&tab) closing omniFxTabClosing; the omniFxTabsBuild head; the
                       "r.danger = t.crashed;" + push_back lines; the omniTaTabFaces line (apply_tab_audio.py's);
                       the Cross line of omniFxTabsInput's tab rows; its Square line + the "keep" line after it.
  OmniContextMenu.h    the omniFxContextBuild head; the "Reader view" add line; the "const std::string link = p.link"
                       line of omniFxContextInput. Chosen away from the Quick menu and from the omniTa / omniRl / omniF3
                       hook lines that apply_media_controls.py (Now playing) may use.
  OmniTabSessionsShell.h  in omniTsOpen: the plan line, "keep = active();", the omniLazyURL clear line, the
                       "== keep" skip line; in omniTsChoiceBuild: the pr / pa plan line.
Apply AFTER apply_tab_sessions.py, apply_tab_audio.py and apply_https_only.py (their lines are anchors).
usage: apply_pinned_tabs.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_PINNED_TABS_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_PINNED_TABS_V1: the pure part of pinned tabs (no SDL, no WebKit). The shell side is OmniPinnedTabsShell.h;
// the reasons are in tools/apply_pinned_tabs.py. Tested on the host with g++ (test_pinned_tabs.cpp).
#pragma once
#include <algorithm>
#include <cstdint>
#include <string>
#include <vector>
#include "OmniTabSessions.h"

namespace OmniPinnedTabs {

constexpr int kMaxPinned = 6;
constexpr uint32_t kCloseArmMs = 4000;          // "close again" window
constexpr const char* kLinePrefix = "pinned\t"; // session.txt: "pinned\t<index of the saved tab>"

inline bool webUrl(const std::string& u) { return u.rfind("https://", 0) == 0 || u.rfind("http://", 0) == 0; }

// --- pinning -----------------------------------------------------------------------------------------------------
enum Check { kOk, kPrivate, kNotWeb, kFull };
inline Check canPin(bool priv, bool web, int pinnedNow)
{
    if (priv) return kPrivate;
    if (!web) return kNotWeb;
    if (pinnedNow >= kMaxPinned) return kFull;
    return kOk;
}
inline std::string refusal(Check c)
{
    switch (c) {
    case kPrivate: return "Private tabs can't be pinned";
    case kNotWeb: return "Only web pages can be pinned: open a page in this tab first";
    case kFull: return std::to_string(kMaxPinned) + " tabs are pinned: unpin one first";
    default: return std::string();
    }
}
inline int countPinned(const std::vector<bool>& pinned) { return int(std::count(pinned.begin(), pinned.end(), true)); }
// Where tab `from` goes once its pin state changed (`pinned` already says the new state; pinned tabs are first):
// right after the other pinned tabs (pin: the end of the pinned group, unpin: the first place after it).
inline size_t targetIndex(const std::vector<bool>& pinned, size_t from)
{
    size_t k = 0;
    for (size_t i = 0; i < pinned.size(); ++i) if (i != from && pinned[i]) ++k;
    return k;
}
// Moves v[from] so it ends at index `to`; the others keep their order.
template <class T> void moveItem(std::vector<T>& v, size_t from, size_t to)
{
    if (from >= v.size() || to >= v.size() || from == to) return;
    if (from < to) std::rotate(v.begin() + from, v.begin() + from + 1, v.begin() + to + 1);
    else std::rotate(v.begin() + to, v.begin() + from, v.begin() + from + 1);
}
// The order that puts pinned tabs first, each group keeping its order.
inline std::vector<size_t> pinnedFirstOrder(const std::vector<bool>& pinned)
{
    std::vector<size_t> out;
    for (size_t i = 0; i < pinned.size(); ++i) if (pinned[i]) out.push_back(i);
    for (size_t i = 0; i < pinned.size(); ++i) if (!pinned[i]) out.push_back(i);
    return out;
}

// --- tab memory --------------------------------------------------------------------------------------------------
// omniTmUnloadOne: is candidate a unloaded before b? Unpinned before pinned, then the least recently shown.
inline bool unloadsBefore(bool aPinned, uint32_t aShownAt, bool bPinned, uint32_t bShownAt)
{
    if (aPinned != bPinned) return !aPinned;
    return aShownAt < bShownAt;
}
struct UnloadCandidate { bool can = true, pinned = false; uint32_t shownAt = 0; };
inline int pickUnload(const std::vector<UnloadCandidate>& c)   // the loop of omniTmUnloadOne; -1: none
{
    int best = -1;
    for (size_t i = 0; i < c.size(); ++i) {
        if (!c[i].can) continue;
        if (best < 0 || unloadsBefore(c[i].pinned, c[i].shownAt, c[size_t(best)].pinned, c[size_t(best)].shownAt)) best = int(i);
    }
    return best;
}

// --- session.txt -------------------------------------------------------------------------------------------------
inline std::string pinnedLine(int savedIndex) { return std::string(kLinePrefix) + std::to_string(savedIndex) + "\n"; }
inline bool parsePinnedLine(const std::string& line0, int& index)
{
    std::string line = line0;
    while (!line.empty() && (line.back() == '\r' || line.back() == '\n')) line.pop_back();
    const std::string p = kLinePrefix;
    if (line.compare(0, p.size(), p) != 0 || line.size() == p.size() || line.size() > p.size() + 3) return false;
    int v = 0;
    for (size_t i = p.size(); i < line.size(); ++i) {
        if (line[i] < '0' || line[i] > '9') return false;
        v = v * 10 + (line[i] - '0');
    }
    index = v;
    return true;
}
// The tabs to pin after a restore: listed, eligible (web page, not private), at most kMaxPinned, duplicates once.
inline std::vector<bool> restoreFlags(const std::vector<int>& indexes, const std::vector<bool>& eligible)
{
    std::vector<bool> out(eligible.size(), false);
    int n = 0;
    for (int i : indexes) {
        if (n >= kMaxPinned) break;
        if (i < 0 || size_t(i) >= eligible.size() || !eligible[size_t(i)] || out[size_t(i)]) continue;
        out[size_t(i)] = true;
        ++n;
    }
    return out;
}

// --- closing -----------------------------------------------------------------------------------------------------
struct CloseArm { const void* tab = nullptr; uint32_t at = 0; };
enum CloseStep { kCloseNow, kAskFirst };
// A pinned tab closes on the second close of the same tab within kCloseArmMs; the first one asks.
inline CloseStep closeStep(CloseArm& a, const void* tab, bool pinned, uint32_t now)
{
    if (!pinned) return kCloseNow;
    if (a.tab == tab && now - a.at < kCloseArmMs) { a = CloseArm(); return kCloseNow; }
    a.tab = tab; a.at = now;
    return kAskFirst;
}
inline bool armed(const CloseArm& a, const void* tab, uint32_t now) { return tab && a.tab == tab && now - a.at < kCloseArmMs; }

// --- top strip (when a tab is pinned) ----------------------------------------------------------------------------
// Pinned tiles from x 100 (52 px, every 60), then the other tabs as OMNI_FEATURES_V3's compact strip in what is left
// up to x 1060: 120..240 px each, scrolling with arrows (left arrow at the start of that area, right arrow at 1032)
// when they do not fit.
constexpr int kX0 = 100, kX1 = 1060, kPinStep = 60, kPinW = 52, kMinTab = 120, kMaxTab = 240, kArrow = 30, kRightArrowX = 1032;
struct Slot { int index = 0, x = 0, w = 0; bool compact = false; };
struct Strip { std::vector<Slot> slots; bool arrows = false; int restX0 = kX0, first = 0, count = 0, hiddenLeft = 0, hiddenRight = 0; };
// n tabs, the first `pinned` pinned; `first` (kept across frames) is the first unpinned tab shown when they scroll.
inline Strip stripLayout(int n, int pinned, int sel, int& first)
{
    Strip L;
    pinned = std::clamp(pinned, 0, std::max(0, n));
    for (int i = 0; i < pinned; ++i) { Slot s; s.index = i; s.x = kX0 + i * kPinStep; s.w = kPinW; s.compact = true; L.slots.push_back(s); }
    L.restX0 = kX0 + pinned * kPinStep;
    const int m = n - pinned, avail = kX1 - L.restX0;
    if (m <= 0) { first = 0; return L; }
    int x0 = L.restX0, step;
    if (m * kMinTab <= avail) { step = std::min(kMaxTab, avail / m); L.count = m; first = 0; }
    else {
        L.arrows = true; x0 = L.restX0 + kArrow;
        const int inner = avail - 2 * kArrow;
        L.count = std::max(1, inner / kMinTab); step = inner / L.count;
        const int s = sel - pinned;
        if (s >= 0) { if (s < first) first = s; if (s >= first + L.count) first = s - L.count + 1; }
        first = std::clamp(first, 0, m - L.count);
        L.hiddenLeft = first; L.hiddenRight = m - first - L.count;
    }
    L.first = first;
    for (int k = 0; k < L.count; ++k) { Slot s; s.index = pinned + first + k; s.x = x0 + k * step; s.w = step - 8; L.slots.push_back(s); }
    return L;
}
inline bool closable(const Slot& s, int sel) { return !s.compact && (s.index == sel || s.w >= 150); }
enum HitKind { kNone, kTab, kClose, kLeft, kRight };
struct Hit { HitKind kind = kNone; int index = -1; };
inline Hit hit(const Strip& L, int x, int sel)
{
    Hit h;
    if (L.arrows && x >= L.restX0 && x < L.restX0 + 28) { h.kind = kLeft; return h; }
    if (L.arrows && x >= kRightArrowX && x < kRightArrowX + 30) { h.kind = kRight; return h; }
    for (auto& s : L.slots) {
        if (x < s.x || x >= s.x + s.w) continue;
        h.index = s.index;
        h.kind = closable(s, sel) && x >= s.x + s.w - 26 ? kClose : kTab;
        return h;
    }
    return h;
}
// The letter on a pinned tile: the site's first letter (upper case), else the title's first character.
inline std::string initial(const std::string& url, const std::string& title)
{
    const std::string h = webUrl(url) ? OmniTabSessions::host(url) : std::string();
    for (char c : h) {
        if (c >= 'a' && c <= 'z') return std::string(1, char(c - 'a' + 'A'));
        if ((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')) return std::string(1, c);
    }
    const size_t a = title.find_first_not_of(' ');
    if (a == std::string::npos) return "?";
    size_t b = a + 1;
    while (b < title.size() && (static_cast<unsigned char>(title[b]) & 0xc0) == 0x80) ++b;
    std::string s = title.substr(a, b - a);
    if (s.size() == 1 && s[0] >= 'a' && s[0] <= 'z') s[0] = char(s[0] - 'a' + 'A');
    return s;
}

// --- saved sessions: Replace keeps the pinned tabs ---------------------------------------------------------------
// As OmniTabSessions::plan(..., replace = true), but the pinned tabs stay: the room is the limit minus them, a URL
// they show is "already open", and only the unpinned tabs are closed.
inline OmniTabSessions::Plan replacePlan(const OmniTabSessions::Session& s, const std::vector<std::string>& pinnedUrls, int unpinnedCount, int limit)
{
    OmniTabSessions::Plan p = OmniTabSessions::plan(s, pinnedUrls, int(pinnedUrls.size()), limit, false);
    p.closes = unpinnedCount;
    return p;
}

// --- texts -------------------------------------------------------------------------------------------------------
inline std::string rowValue(const std::string& v, bool pinned)
{
    if (!pinned) return v;
    if (v.empty()) return "Pinned";
    if (v == "Current") return "Current, pinned";
    return v + " \xc2\xb7 pinned";
}
inline const char* faceLabel(bool pinned) { return pinned ? "Unpin" : "Pin"; }
inline const char* contextLabel(bool pinned) { return pinned ? "Unpin this tab" : "Pin this tab"; }
inline std::string pinnedNotice(int count) { return "Tab pinned (" + std::to_string(count) + " of " + std::to_string(kMaxPinned) + "): it stays first and reopens next time"; }
inline std::string unpinnedNotice() { return "Tab unpinned"; }
inline std::string closeAskNotice() { return "Pinned tab: close it again to close it"; }
constexpr const char* kArmedValue = "Square again: close";

} // namespace OmniPinnedTabs
'''

SHELL = r'''// OMNI_PINNED_TABS_V1: pinned tabs (shell side). Included from OmniFeatures3.h right after OmniTabMemory.h (inside
// OmniBrowser.cpp's anonymous namespace). The pure part is OmniPinnedTabs.h; the reasons are in
// tools/apply_pinned_tabs.py. Everything runs on the main thread. Pinned tabs are always tabs[0 .. count-1].
#pragma once

namespace OPT = OmniPinnedTabs;
static std::vector<const void*> omniPtSet;   // the pinned tabs (at most 6); forgotten when a tab closes
static OPT::CloseArm omniPtArm;
static std::vector<int> omniPtRestoreIdx;    // session.txt "pinned" lines, until the tabs exist
static int omniPtFirst = 0;                  // strip scroll (unpinned tabs)
constexpr int omniPtContextId = 960;         // hold-Cross page menu row

static bool omniPtPinned(const Tab& t) { return std::find(omniPtSet.begin(), omniPtSet.end(), static_cast<const void*>(&t)) != omniPtSet.end(); }
static bool omniPtAny() { return !omniPtSet.empty(); }
static void omniPtForget(const void* tab)
{
    omniPtSet.erase(std::remove(omniPtSet.begin(), omniPtSet.end(), tab), omniPtSet.end());
    if (omniPtArm.tab == tab) omniPtArm = OPT::CloseArm();
}
static int omniPtCount() { int n = 0; for (auto& t : tabs) if (omniPtPinned(*t)) ++n; return n; }
static std::string omniPtURL(const Tab& t) { return !t.omniLazyURL.empty() && t.omniLazyURL != "newtab" ? t.omniLazyURL : t.url; }
static size_t omniPtIndex(const void* t) { for (size_t i = 0; i < tabs.size(); ++i) if (tabs[i].get() == t) return i; return tabs.size(); }
static std::vector<bool> omniPtFlags() { std::vector<bool> f; for (auto& t : tabs) f.push_back(omniPtPinned(*t)); return f; }
// Puts pinned tabs first (stable); `selected` keeps pointing at the same tab.
static void omniPtSortFirst()
{
    const void* shown = active();
    std::stable_partition(tabs.begin(), tabs.end(), [](const std::unique_ptr<Tab>& t) { return omniPtPinned(*t); });
    const size_t i = omniPtIndex(shown);
    if (i < tabs.size()) selected = i;
}

// Pins / unpins `t` and moves it; returns its index afterwards.
static size_t omniPtToggle(Tab& t)
{
    const bool pin = !omniPtPinned(t);
    if (pin) {
        const OPT::Check c = OPT::canPin(t.omniPrivate, omniWebURL(omniPtURL(t)) && !omniMediaOwns(t), omniPtCount());
        if (c != OPT::kOk) { notice(OPT::refusal(c)); return omniPtIndex(&t); }
        omniPtSet.push_back(&t);
    } else omniPtForget(&t);
    const size_t from = omniPtIndex(&t);
    if (from < tabs.size()) {
        const void* shown = active();
        OPT::moveItem(tabs, from, OPT::targetIndex(omniPtFlags(), from));
        const size_t s = omniPtIndex(shown);
        if (s < tabs.size()) selected = s;
    }
    notice(pin ? OPT::pinnedNotice(omniPtCount()) : OPT::unpinnedNotice());
    fprintf(stderr, "OMNI PINNED: %s, %d pinned of %zu tabs\n", pin ? "pinned" : "unpinned", omniPtCount(), tabs.size());
    omniShellDirty = true;
    return omniPtIndex(&t);
}
// Every user close of a tab (Tabs panel Square, R3): a pinned tab asks once.
static bool omniPtMayClose(Tab& t)
{
    if (OPT::closeStep(omniPtArm, &t, omniPtPinned(t), SDL_GetTicks()) == OPT::kCloseNow) return true;
    notice(OPT::closeAskNotice());
    omniShellDirty = true;
    return false;
}

// --- start-up restore (omniEverydayStart) ----------------------------------------------------------------------------
static bool omniPtRestoreLine(const std::string& line)
{
    int i = 0;
    if (!OPT::parsePinnedLine(line, i)) return false;
    if (omniPtRestoreIdx.size() < 64) omniPtRestoreIdx.push_back(i);
    return true;
}
static void omniPtRestoreApply(int& sel)
{
    if (omniPtRestoreIdx.empty() || tabs.empty()) { omniPtRestoreIdx.clear(); return; }
    std::vector<bool> ok;
    for (auto& t : tabs) ok.push_back(!t->omniPrivate && omniWebURL(omniPtURL(*t)));
    const std::vector<bool> flags = OPT::restoreFlags(omniPtRestoreIdx, ok);
    omniPtRestoreIdx.clear();
    const void* shown = tabs[size_t(std::clamp(sel, 0, int(tabs.size()) - 1))].get();
    for (size_t i = 0; i < tabs.size(); ++i) if (flags[i]) omniPtSet.push_back(tabs[i].get());
    omniPtSortFirst();   // written pinned-first already; this only repairs an edited file
    sel = int(omniPtIndex(shown));
    if (!omniPtSet.empty()) fprintf(stderr, "OMNI PINNED: restored %zu pinned tab(s)\n", omniPtSet.size());
}

// --- saved sessions (OmniTabSessionsShell.h, included after this file) -----------------------------------------------
static OmniTabSessions::Plan omniPtSessionPlan(const OmniTabSessions::Session& s, const std::vector<std::string>& urls, bool replace)
{
    if (!replace || !omniPtAny()) return OmniTabSessions::plan(s, urls, int(tabs.size()), omniF3TabLimit(), replace);
    std::vector<std::string> pinnedUrls;
    int unpinned = 0;
    for (auto& t : tabs) if (omniPtPinned(*t)) pinnedUrls.push_back(omniPtURL(*t)); else ++unpinned;
    return OPT::replacePlan(s, pinnedUrls, unpinned, omniF3TabLimit());
}
// Replace closes every unpinned tab but one, opens the session beside it, then closes that one: the shown tab if it is
// unpinned, else the last unpinned tab; none when every tab is pinned.
static Tab* omniPtReplaceKeep()
{
    Tab* a = active();
    if (a && !omniPtPinned(*a)) return a;
    for (size_t i = tabs.size(); i-- > 0;) if (!omniPtPinned(*tabs[i])) return tabs[i].get();
    return nullptr;
}

// --- Tabs panel (declared in OmniTabsPage.h) -------------------------------------------------------------------------
static void omniPtTabRow(const Tab& t, size_t, OmniFxRow& r)
{
    if (!omniPtPinned(t)) return;
    if (OPT::armed(omniPtArm, &t, SDL_GetTicks())) { r.value = OPT::kArmedValue; r.danger = true; return; }
    r.value = OPT::rowValue(r.value, true);
}
static bool omniPtTabsInput(OmniFxPanel& p, int row, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    if (row < 0 || row >= int(tabs.size())) return false;
    p.sel = int(omniPtToggle(*tabs[size_t(row)]));
    return true;
}
static void omniPtTabFaces(OmniFxPanel& p)
{
    if (p.sel < 0 || p.sel >= int(tabs.size())) return;
    const Tab& t = *tabs[size_t(p.sel)];
    if (t.omniPrivate) return;
    auto at = std::find_if(p.faces.begin(), p.faces.end(), [](const std::pair<int, const char*>& f) { return f.first == 2; });
    p.faces.insert(at, { omniHintDpadH, OPT::faceLabel(omniPtPinned(t)) });
}

// --- hold-Cross page menu (declared in OmniContextMenu.h) ------------------------------------------------------------
static void omniPtContextRows(OmniFxPanel& p)
{
    Tab* t = active();
    if (!t || t->omniPrivate) return;   // private tabs are never pinned
    const bool pinned = omniPtPinned(*t);
    OmniFxRow r; r.id = omniPtContextId; r.label = OPT::contextLabel(pinned);
    r.enabled = pinned || (omniWebURL(omniPtURL(*t)) && !omniMediaOwns(*t));
    p.rows.push_back(r);
}
static bool omniPtContextAction(int id)
{
    if (id != omniPtContextId) return false;
    omniFxCloseAll();
    if (Tab* t = active()) omniPtToggle(*t);
    return true;
}

// --- top strip while a tab is pinned (omniF3DrawTabStrip / omniF3TabStripClick hand over) -----------------------------
static OPT::Strip omniPtLayout() { return OPT::stripLayout(int(tabs.size()), omniPtCount(), int(selected), omniPtFirst); }
static void omniPtPinMark(float cx, float cy, SDL_Color c)
{
    omniDisc(cx, cy - 4, 4, c);
    fillRounded(int(cx) - 5, int(cy) - 1, 10, 2, 1, c);
    fillRounded(int(cx) - 1, int(cy) + 1, 2, 7, 1, c);
}
static bool omniPtDrawStrip()
{
    const OmniTheme& T = omniTheme();
    const OPT::Strip L = omniPtLayout();
    for (const OPT::Slot& s : L.slots) {
        const Tab& tab = *tabs[size_t(s.index)];
        const bool sel = size_t(s.index) == selected, hover = omniHover(s.x, 8, s.w, 44), unloaded = omniTmIsUnloaded(tab);
        omniHudTab(s.x, s.w, sel, hover);
        const SDL_Color ink = unloaded ? T.inkFaint : sel ? T.ink : T.inkDim;
        if (s.compact) {
            if (tab.loading) omniSpinner(s.x + 15, 30, 6.5f, T.accent);
            else if (tab.crashed || !tab.message.empty()) omniDisc(s.x + 15, 30, 4, tab.crashed ? omniBad : omniWarn);
            else omniPtPinMark(s.x + 15, 30, ink);
            if (tab.omniTaBadge) omniIcon(tab.omniTaBadge == OmniTabAudio::kMuted ? omniIconSpeakerMuted : omniIconSpeaker, s.x + 37, 30, ink);
            else omniLabel(OPT::initial(omniPtURL(tab), tab.title), s.x + 37, 30, omniSmall, ink, 1);
            continue;
        }
        if (tab.omniPrivate) fillRounded(s.x + 10, 41, s.w - 20, 3, 1, { 150, 110, 235, 255 }, 255, omniCornersAll);
        float tx = s.x + 12;
        if (tab.loading) { omniSpinner(s.x + 18, 30, 6.5f, T.accent); tx = s.x + 32; }
        else if (tab.crashed || !tab.message.empty()) { omniDisc(s.x + 17, 30, 4, tab.crashed ? omniBad : omniWarn); tx = s.x + 28; }
        const bool canClose = OPT::closable(s, int(selected));
        const std::string title = !tab.title.empty() ? tab.title : !tab.url.empty() ? omniBlockerHostOf(tab.url) : std::string("New tab");
        const OmniTabAudio::Slot ta = OmniTabAudio::compactSlot(s.x, s.w, canClose, tab.omniTaBadge != 0);
        omniLabel(title, tx, 30, omniSmall, ink, 0, int(ta.titleRight - tx));
        if (tab.omniTaBadge) omniIcon(tab.omniTaBadge == OmniTabAudio::kMuted ? omniIconSpeakerMuted : omniIconSpeaker, ta.iconX, 30, sel ? T.ink : T.inkDim);
        if (canClose) {
            const bool closeHover = omniHover(s.x + s.w - 24, 8, 24, 44);
            if (closeHover) omniRingDisc(s.x + s.w - 14, 30, 11, T.accent, omniMix(sel ? T.tabOn : T.tab, T.ink, 0.16f));
            omniIcon(omniIconClose, s.x + s.w - 14, 30, closeHover || sel ? T.ink : T.inkDim);
        }
    }
    if (L.arrows) {
        const int lx = L.restX0 + 14, rx = OPT::kRightArrowX + 14;
        const bool left = L.hiddenLeft > 0, right = L.hiddenRight > 0;
        if (left && omniHover(L.restX0, 8, 28, 44)) omniRingDisc(lx, 30, 13, T.accent, T.hover);
        omniIcon(omniIconBack, lx, 30, left ? T.ink : T.inkFaint);
        if (right && omniHover(OPT::kRightArrowX, 8, 28, 44)) omniRingDisc(rx, 30, 13, T.accent, T.hover);
        omniIcon(omniIconForward, rx, 30, right ? T.ink : T.inkFaint);
        if (left) omniLabel(std::to_string(L.hiddenLeft), lx, 47, omniCaption, T.inkDim, 1);
        if (right) omniLabel(std::to_string(L.hiddenRight), rx, 47, omniCaption, T.inkDim, 1);
    }
    return true;
}
static bool omniPtStripClick(int x)
{
    if (x >= 1070) {   // "+" (as omniF3TabStripClick)
        if (newTab()) { if (!omniTestMode()) omniOpenNewTabPage(active()); address.clear(); editing = true; omniKbPageReset(); }
        return true;
    }
    const OPT::Hit h = OPT::hit(omniPtLayout(), x, int(selected));
    switch (h.kind) {
    case OPT::kLeft: if (selected > 0) activate(selected - 1); break;
    case OPT::kRight: if (selected + 1 < tabs.size()) activate(selected + 1); break;
    case OPT::kTab: activate(size_t(h.index)); break;
    case OPT::kClose: omniTmSkipRestore = true; activate(size_t(h.index)); omniTmSkipRestore = false; closeTab(); break; // unpinned only
    default: break;
    }
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniHttpsOnly.h" // OMNI_HTTPS_ONLY_V1: HTTPS-only mode + GPC, https-only.txt (pure)\n',
         '#include "OmniHttpsOnly.h" // OMNI_HTTPS_ONLY_V1: HTTPS-only mode + GPC, https-only.txt (pure)\n'
         '#include "OmniPinnedTabs.h" // OMNI_PINNED_TABS_V1: pinned tabs: order, unload order, strip, session line (pure)\n'),
        ('        s += "tab\\t" + omniOneLine(url, 2048) + "\\t" + omniOneLine(t.title, 200) + "\\n";\n'
         '        ++n;\n',
         '        s += "tab\\t" + omniOneLine(url, 2048) + "\\t" + omniOneLine(t.title, 200) + "\\n";\n'
         '        if (omniPtPinned(t)) s += OmniPinnedTabs::pinnedLine(n); // OMNI_PINNED_TABS_V1: "pinned\\t<n>" (older builds skip it)\n'
         '        ++n;\n'),
        ('            } else if (s.rfind("selected\\t", 0) == 0) sel = atoi(s.c_str() + 9);\n',
         '            } else if (omniPtRestoreLine(s)) { // OMNI_PINNED_TABS_V1: "pinned\\t<index>"\n'
         '            } else if (s.rfind("selected\\t", 0) == 0) sel = atoi(s.c_str() + 9);\n'),
        ('    omniF3Restoring = false;\n'
         '    if (tabs.empty()) return false;\n',
         '    omniF3Restoring = false;\n'
         '    omniPtRestoreApply(sel); // OMNI_PINNED_TABS_V1: pin the listed tabs (first), `sel` follows its tab\n'
         '    if (tabs.empty()) return false;\n'),
        ('    else if (button == SDL_CONTROLLER_BUTTON_RIGHTSTICK) closeTab();\n',
         '    else if (button == SDL_CONTROLLER_BUTTON_RIGHTSTICK) { if (omniPtMayClose(*active())) closeTab(); } // OMNI_PINNED_TABS_V1: a pinned tab asks once\n'),
    ],
    'OmniFeatures3Decl.h': [
        ('static bool omniTmSkipRestore = false, omniF3Restoring = false;\n',
         'static bool omniTmSkipRestore = false, omniF3Restoring = false;\n'
         '// OMNI_PINNED_TABS_V1 (OmniPinnedTabsShell.h): pinned tabs\n'
         'static bool omniPtPinned(const Tab& t);\n'
         'static bool omniPtAny();\n'
         'static bool omniPtMayClose(Tab& t);                       // user closes: false = asked first (pinned)\n'
         'static void omniPtForget(const void* tab);                // omniFxTabClosing\n'
         'static bool omniPtRestoreLine(const std::string& line);   // omniEverydayStart: a "pinned" line\n'
         'static void omniPtRestoreApply(int& sel);\n'
         'static bool omniPtDrawStrip();                            // omniF3DrawTabStrip while a tab is pinned\n'
         'static bool omniPtStripClick(int x);\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniTabMemory.h"\n',
         '#include "OmniTabMemory.h"\n'
         '#include "OmniPinnedTabsShell.h" // OMNI_PINNED_TABS_V1 (before OmniTabSessionsShell.h, which uses it)\n'),
    ],
    'OmniTabMemory.h': [
        ('        if (!best || at < oldest) { best = t.get(); oldest = at; }\n',
         '        if (!best || OmniPinnedTabs::unloadsBefore(omniPtPinned(*t), at, omniPtPinned(*best), oldest)) { best = t.get(); oldest = at; } // OMNI_PINNED_TABS_V1: pinned tabs last\n'),
        ('static bool omniF3DrawTabStrip()\n{\n',
         'static bool omniF3DrawTabStrip()\n{\n'
         '    if (omniPtAny()) return omniPtDrawStrip(); // OMNI_PINNED_TABS_V1: compact pinned tiles first\n'),
        ('static bool omniF3TabStripClick(int x)\n{\n',
         'static bool omniF3TabStripClick(int x)\n{\n'
         '    if (omniPtAny() && x < 1150) return omniPtStripClick(x); // OMNI_PINNED_TABS_V1\n'),
    ],
    'OmniTabsPage.h': [
        ('    omniFxForgetTab(&tab);\n}\n',
         '    omniPtForget(&tab); // OMNI_PINNED_TABS_V1\n'
         '    omniFxForgetTab(&tab);\n}\n'),
        ('static void omniFxTabsBuild(OmniFxPanel& p)\n{\n',
         'static void omniPtTabRow(const Tab& t, size_t i, OmniFxRow& r); // OMNI_PINNED_TABS_V1 (OmniPinnedTabsShell.h)\n'
         'static bool omniPtTabsInput(OmniFxPanel& p, int row, int b);\n'
         'static void omniPtTabFaces(OmniFxPanel& p);\n'
         'static void omniFxTabsBuild(OmniFxPanel& p)\n{\n'),
        ('        r.danger = t.crashed;\n'
         '        p.rows.push_back(r);\n',
         '        r.danger = t.crashed;\n'
         '        omniPtTabRow(t, i, r); // OMNI_PINNED_TABS_V1: "Pinned", or "Square again: close"\n'
         '        p.rows.push_back(r);\n'),
        ('    omniTaTabFaces(p); // OMNI_TAB_AUDIO_V1: Triangle "Mute tab" / "Unmute tab" on tab rows\n',
         '    omniTaTabFaces(p); // OMNI_TAB_AUDIO_V1: Triangle "Mute tab" / "Unmute tab" on tab rows\n'
         '    omniPtTabFaces(p); // OMNI_PINNED_TABS_V1: D-pad left / right "Pin" / "Unpin"\n'),
        ('        if (b == SDL_CONTROLLER_BUTTON_A) { omniFxCloseAll(); activate(size_t(r.id)); return true; }\n',
         '        if (b == SDL_CONTROLLER_BUTTON_A) { omniFxCloseAll(); activate(size_t(r.id)); return true; }\n'
         '        if (omniPtTabsInput(p, r.id, b)) return true; // OMNI_PINNED_TABS_V1: D-pad left / right pins / unpins\n'),
        ('        if (b == SDL_CONTROLLER_BUTTON_X) {\n'
         '            const Tab* keep = ',
         '        if (b == SDL_CONTROLLER_BUTTON_X) {\n'
         '            if (!omniPtMayClose(*tabs[size_t(r.id)])) return true; // OMNI_PINNED_TABS_V1: a pinned tab asks once\n'
         '            const Tab* keep = '),
    ],
    'OmniContextMenu.h': [
        ('static void omniFxContextBuild(OmniFxPanel& p)\n{\n',
         'static void omniPtContextRows(OmniFxPanel& p); // OMNI_PINNED_TABS_V1 (OmniPinnedTabsShell.h)\n'
         'static bool omniPtContextAction(int id);\n'
         'static void omniFxContextBuild(OmniFxPanel& p)\n{\n'),
        ('        add(omniCxReader, "Reader view", web);\n',
         '        add(omniCxReader, "Reader view", web);\n'
         '        omniPtContextRows(p); // OMNI_PINNED_TABS_V1: Pin this tab / Unpin this tab\n'),
        ('    const std::string link = p.link, image = p.image, video = p.text, label = p.page;\n',
         '    if (omniPtContextAction(r.id)) return true; // OMNI_PINNED_TABS_V1\n'
         '    const std::string link = p.link, image = p.image, video = p.text, label = p.page;\n'),
    ],
    'OmniTabSessionsShell.h': [
        ('    const TS::Plan plan = TS::plan(s, urls, int(tabs.size()), omniF3TabLimit(), replace);\n',
         '    const TS::Plan plan = omniPtSessionPlan(s, urls, replace); // OMNI_PINNED_TABS_V1: Replace keeps the pinned tabs\n'),
        ('        keep = active();\n',
         '        keep = omniPtReplaceKeep(); // OMNI_PINNED_TABS_V1: an unpinned tab (none when all are pinned)\n'),
        ('        for (auto& t : tabs) if (t.get() != keep) t->omniLazyURL.clear();   // closing must not load them first\n',
         '        for (auto& t : tabs) if (t.get() != keep && !omniPtPinned(*t)) t->omniLazyURL.clear();   // closing must not load them first (OMNI_PINNED_TABS_V1: pinned stay)\n'),
        ('            while (i < tabs.size() && tabs[i].get() == keep) ++i;\n',
         '            while (i < tabs.size() && (tabs[i].get() == keep || omniPtPinned(*tabs[i]))) ++i; // OMNI_PINNED_TABS_V1\n'),
        ('    const TS::Plan pr = TS::plan(s, urls, int(tabs.size()), limit, true), pa = TS::plan(s, urls, int(tabs.size()), limit, false);\n',
         '    const TS::Plan pr = omniPtSessionPlan(s, urls, true), pa = TS::plan(s, urls, int(tabs.size()), limit, false); // OMNI_PINNED_TABS_V1\n'),
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
    for need, f, tool in (('OMNI_TAB_SESSIONS_V1', 'OmniFeatures3.h', 'apply_tab_sessions.py'),
                          ('OMNI_TAB_AUDIO_V1', 'OmniTabsPage.h', 'apply_tab_audio.py'),
                          ('OMNI_HTTPS_ONLY_V1', 'OmniBrowser.cpp', 'apply_https_only.py')):
        if need not in (root / f).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (f, need, tool))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniPinnedTabs.h', PURE, 'OmniTabSessions.h'),
            write_new('OmniPinnedTabsShell.h', SHELL, 'OmniTabSessionsShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
