#!/usr/bin/env python3
"""OMNI_READING_PROGRESS_V1 (2026-11-16): reading progress for the Reading list (OMNI_READING_LIST_V1).

What it does
  - A saved page opened from the Reading list (Cross: the saved copy in a new tab, an about:blank document loaded with
    WKPageLoadHTMLString, CSP without scripts, the "Saved copy" banner #omni-saved-banner) is remembered by its entry id.
  - How far it is read = the scroll fraction scrollY / (scrollHeight - innerHeight), read by ONE fixed read-only script
    (WKPageEvaluateJavaScriptInMainFrame; the shell's own call, not subject to the page's CSP) at these moments only:
      * the tab is left: another tab is shown (activate()),
      * the tab navigates away (didStartProvisionalNavigation: the old document still answers; e.g. "Open live page"),
      * a panel opens over it (Options / Tabs / any OmniFx panel: also the way to "Exit Omni"),
      * the page was scrolled with the stick (omniPageWheel) and then left alone for 1.5 s (one read per scroll pause:
        this keeps the value current for closing the tab or Omni, when no script can answer any more).
    No polling loop: nothing runs while the page is just shown. The script answers -1 (ignored) when the document is
    not the saved copy (no banner) or does not scroll.
  - Reopen: after the saved copy finished loading, one script scrolls to the stored fraction (again 0.5 s later if the
    user has not scrolled since, for late layout). Finished pages reopen at the top.
  - "Finished" at >= 95 % (sticky: going back up does not undo it; the time it was first reached is kept).
    Reading list rows: value "40% read . 1.2 MB" / "Finished . 1.2 MB" (under 1 %: the size only).
  - Panel toggle (second row): "Remove finished items after 7 days", Off by default; On =
    /data/omni/reading-list-prune-finished.flag. Pruned (file + index line) when the list is loaded, hourly, and at once
    when switched on; one notice says how many.
  - Private: a saved page opened while a private tab is active (or in a private tab) is restored but never updates
    progress.

Storage (backward compatible). index.tsv keeps its header "omni-reading-list\\t1" and its 6-field page lines; progress is
extra lines in the same file:   p \\t <id> \\t <permille 0..1000> \\t <updated unix s> \\t <finished unix s or 0>
An EXTRA COLUMN ON THE PAGE LINES WAS NOT USED: OMNI_READING_LIST_V1's parser skips any line without exactly 6 fields,
so an older Omni would drop every page and then delete their files as "not in the index". It skips the 5-field
"p" lines (and "p" is no valid id), keeps every page, and simply drops the progress the next time it rewrites the index.
Setup's backup.py copies index.tsv as an opaque file (allow-list entry, sha-checked; restore writes pages before the
index), so progress is backed up and restored with it; the prune flag is a *.flag (never backed up, like other flags).

Files
  - OmniReadingProgress.h (new, pure: progress lines parse/serialize, finished rule, labels, restore target, prune plan,
    the two page scripts). Tests: g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_reading_progress.cpp -o t && ./t <dir>
    (writes the page scripts to <dir> for node --check).
  - OmniReadingProgressShell.h (new: reads, restore, panel row/toggle, prune), included after OmniReadingListShell.h.
Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp           the OmniReadingList.h include line; the Tab member 'uint8_t omniTaBadge' line; the
                            'Tab* active() {...}' definition (declarations after it); activate()'s
                            'omniShoulderCancel(); selected = index;' lines; 'omniPaintHoldBegin(tab, page);' in
                            didStartProvisionalNavigation; the 'void omniPageWheel(double amount) {' lines
  OmniReadingListShell.h    'namespace RL = OmniReadingList;', the index parse / serialize lines, 'notice("Opening saved
                            page...")', the LoadHTMLString + 'loading = true' lines, the Save row push, the row value
                            line, the 'r.id < omniRlRowFirst' input line
  OmniFeatures3.h           the OmniReadingListShell.h include, the omniRlTick(now) call
Row id 423 (Reading list panel) is checked against every source in the tree and every tools/apply_*.py first.
usage: apply_reading_progress.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_READING_PROGRESS_V1'
ROW_ID = 423
root = Path(sys.argv[1]) / 'engine' / 'entry'
tools = Path(__file__).resolve().parent

PURE = r'''// OMNI_READING_PROGRESS_V1: reading progress for the reading list, pure part (no SDL, no WebKit). Progress lives in
// /data/omni/reading-list/index.tsv as extra 5-field lines "p\t<id>\t<permille>\t<updated>\t<finished>" that
// OMNI_READING_LIST_V1's parser (6 fields per page line) skips, so an older Omni still reads the file.
// Tested on the host with g++ (tools/test_reading_progress.cpp). Shell side: OmniReadingProgressShell.h.
#pragma once
#include "OmniReadingList.h"
#include <map>
#include <string>
#include <vector>

namespace OmniReadingProgress {

constexpr int kFinished = 950;                         // permille: "Finished" at >= 95 %
constexpr int kStep = 10;                              // a change under 1 % is not stored
constexpr long long kPruneAge = 7LL * 86400;           // "Remove finished items after 7 days"
constexpr int kRowPrune = 423;                         // Reading list panel row (save 1, info 2, pages 1000+)
static const char* const kTag = "p";                   // the progress line's first field (never a valid page id)
static const char* const kPruneFlag = "/data/omni/reading-list-prune-finished.flag";

struct Progress {
    int permille = -1;          // -1 unknown
    long long at = 0;           // last stored (unix s)
    long long finishedAt = 0;   // first time >= kFinished (unix s), 0 not finished
};
using Map = std::map<std::string, Progress>;

inline bool finished(const Progress& p) { return p.finishedAt > 0; }

// The progress lines of an index file. Wrong header: nothing. Page lines, bad lines and unknown lines are skipped;
// a later line for the same id wins.
inline Map parseLines(const std::string& text)
{
    Map out;
    size_t at = 0;
    bool first = true;
    while (at < text.size()) {
        size_t nl = text.find('\n', at);
        if (nl == std::string::npos) nl = text.size();
        std::string line = text.substr(at, nl - at);
        at = nl + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (first) { if (line != OmniReadingList::kHeader) return {}; first = false; continue; }
        if (line.size() < 2 || line[0] != kTag[0] || line[1] != '\t') continue;
        const auto f = OmniReadingList::splitTabs(line);
        if (f.size() != 5 || f[0] != kTag || !OmniReadingList::validId(f[1])) continue;
        long long pm = 0, up = 0, fin = 0;
        if (!OmniReadingList::parseNumber(f[2], pm) || !OmniReadingList::parseNumber(f[3], up)
            || !OmniReadingList::parseNumber(f[4], fin) || pm > 1000 || up <= 0) continue;
        Progress p;
        p.permille = int(pm); p.at = up; p.finishedAt = fin;
        if (p.permille >= kFinished && !p.finishedAt) p.finishedAt = up;
        out[f[1]] = p;
    }
    return out;
}
// The lines appended after the page lines: pages of `list` (in its order) with a known value only, so entries that
// left the list lose their progress with them.
inline std::string lines(const std::vector<OmniReadingList::Entry>& list, const Map& m)
{
    std::string o;
    for (const auto& e : list) {
        const auto it = m.find(e.id);
        if (it == m.end() || it->second.permille < 0 || it->second.permille > 1000) continue;
        o += std::string(kTag) + "\t" + e.id + "\t" + std::to_string(it->second.permille) + "\t" + std::to_string(it->second.at)
            + "\t" + std::to_string(it->second.finishedAt) + "\n";
    }
    return o;
}

// A new reading (permille 0..1000). True when the stored value changed (worth writing the index).
inline bool update(Progress& p, int permille, long long now)
{
    if (permille < 0 || permille > 1000) return false;
    bool changed = p.permille < 0 || permille - p.permille >= kStep || p.permille - permille >= kStep;
    if (permille >= kFinished && !p.finishedAt) { p.finishedAt = now; changed = true; }
    if (changed) { p.permille = permille; p.at = now; }
    return changed;
}

// "Finished", "40% read", or "" (unknown, or under 1 %).
inline std::string label(const Progress* p)
{
    if (!p) return std::string();
    if (finished(*p)) return "Finished";
    if (p->permille < kStep) return std::string();
    return std::to_string(p->permille / 10) + "% read";
}
// The row's value: the label before the size ("40% read \xc2\xb7 1.2 MB").
inline std::string rowValue(const Progress* p, const std::string& size)
{
    const std::string l = label(p);
    return l.empty() ? size : l + " \xc2\xb7 " + size;
}
// Where a reopened page scrolls to (permille); 0 = stay at the top (unknown, under 1 %, finished).
inline int restoreTo(const Progress* p)
{
    if (!p || finished(*p) || p->permille < kStep) return 0;
    return p->permille > 1000 ? 1000 : p->permille;
}

// The pages "Remove finished items after 7 days" removes now (ids, in list order).
inline std::vector<std::string> prunePlan(const std::vector<OmniReadingList::Entry>& list, const Map& m, long long now, bool enabled)
{
    std::vector<std::string> out;
    if (!enabled) return out;
    for (const auto& e : list) {
        const auto it = m.find(e.id);
        if (it != m.end() && finished(it->second) && now - it->second.finishedAt >= kPruneAge) out.push_back(e.id);
    }
    return out;
}

// The read script's answer "ORP1:<0..1000>"; -1 for anything else ("ORP1:-1": not the saved copy / no scrolling).
inline int parseResult(const std::string& r)
{
    if (r.size() < 6 || r.size() > 9 || r.compare(0, 5, "ORP1:") != 0) return -1;
    long long v = 0;
    if (!OmniReadingList::parseNumber(r.substr(5), v) || v > 1000) return -1;
    return int(v);
}

// Read-only: the scroll fraction of the saved copy (the banner proves the document is still the saved page).
inline const char* readScript()
{
    return R"JS((function(){try{var d=document;if(!d.getElementById('omni-saved-banner'))return 'ORP1:-1';
var s=d.scrollingElement||d.documentElement,b=d.body,h=Math.max(s?s.scrollHeight:0,b?b.scrollHeight:0),m=h-(window.innerHeight||0);
if(!(m>8))return 'ORP1:-1';var y=window.scrollY||window.pageYOffset||(s?s.scrollTop:0)||0;
return 'ORP1:'+Math.round(Math.min(1,Math.max(0,y/m))*1000);}catch(e){return 'ORP1:-1';}})())JS";
}
// Scrolls the saved copy to `permille`, and once more 0.5 s later when nobody scrolled in between (late layout).
inline std::string restoreScript(int permille)
{
    if (permille < 0) permille = 0;
    if (permille > 1000) permille = 1000;
    static const char* const head = R"JS((function(){var P=)JS";
    static const char* const tail = R"JS(/1000;try{var d=document;if(!d.getElementById('omni-saved-banner'))return 'ORP1:-1';
function go(){var s=d.scrollingElement||d.documentElement,b=d.body,h=Math.max(s?s.scrollHeight:0,b?b.scrollHeight:0),m=h-(window.innerHeight||0);
if(m>0)window.scrollTo(0,Math.round(m*P));return window.scrollY||window.pageYOffset||0;}
var y=go();setTimeout(function(){if((window.scrollY||window.pageYOffset||0)===y)go();},500);return 'ORP1:ok';}catch(e){return 'ORP1:-1';}})())JS";
    return std::string(head) + std::to_string(permille) + tail;
}

} // namespace OmniReadingProgress
'''

SHELL = r'''// OMNI_READING_PROGRESS_V1: reading progress for saved pages (shell side). Included from OmniFeatures3.h after
// OmniReadingListShell.h (inside OmniBrowser.cpp's anonymous namespace). Pure part: OmniReadingProgress.h; the design
// (when the one read script runs, the index lines, older Omni) is in tools/apply_reading_progress.py.
// Locks: omniRpMap is guarded by omniRlLock (the reading list's); the index is written under omniRlFileLock by
// omniRlWriteIndexLocked(), which appends the progress lines (omniRpAppendLocked).
#pragma once

namespace ORPG = OmniReadingProgress;
static ORPG::Map omniRpMap;                       // omniRlLock
static std::atomic<bool> omniRpWriteQueued { false };
static std::string omniRpOpeningId;               // the entry being opened (one open at a time: omniRlOpening)
static bool omniRpOpeningPrivate = false;         // opened while a private tab was active
static uint32_t omniRpLastWheel = 0;              // a wheel on the active tracked tab (read after 1.5 s quiet)
static bool omniRpPanelWas = false;
static bool omniRpPruneOn = false, omniRpPruneRead = false, omniRpPrunedOnce = false;
static uint32_t omniRpPruneAt = 0;

// --- index (worker threads) ------------------------------------------------------------------------------------------
static void omniRpLoadFrom(const std::string& text)   // omniRlLoadLocked(): omniRlFileLock held
{
    ORPG::Map m = ORPG::parseLines(text);
    std::lock_guard<std::mutex> g(omniRlLock);
    omniRpMap = std::move(m);
}
static void omniRpAppendLocked(std::string& text)     // omniRlWriteIndexLocked(): omniRlLock held
{
    text += ORPG::lines(omniRlList, omniRpMap);
}
static void omniRpQueueWrite()
{
    if (omniRpWriteQueued.exchange(true)) return;
    std::thread([] {
        std::lock_guard<std::mutex> fl(omniRlFileLock);
        omniRpWriteQueued = false;
        omniRlLoadLocked();
        omniRlWriteIndexLocked();
    }).detach();
}

// --- reads / restore (main thread) -------------------------------------------------------------------------------------
static void omniRpRead(Tab& t)
{
    if (t.omniRpState != 2 || t.omniRpId.empty() || t.crashed || !t.page) return;
    auto* id = new std::string(t.omniRpId);
    auto js = adoptWK(WKStringCreateWithUTF8CString(ORPG::readScript()));
    WKPageEvaluateJavaScriptInMainFrame(t.page, js.get(), id, [](WKTypeRef result, WKErrorRef error, void* ctx) {
        std::unique_ptr<std::string> id(static_cast<std::string*>(ctx));
        const int pm = ORPG::parseResult(omniFxResultString(result, error));
        if (pm < 0) return;
        bool changed = false;
        { std::lock_guard<std::mutex> g(omniRlLock); changed = ORPG::update(omniRpMap[*id], pm, (long long)time(nullptr)); }
        if (!changed) return;
        omniRpQueueWrite();
        if (omniRlPanelShown()) omniFxRefresh();
    });
}
static void omniRpLeaving(Tab& t) { if (t.omniRpState == 2) omniRpRead(t); }   // activate(): another tab is shown
static void omniRpNavigating(Tab& t)                                            // didStartProvisionalNavigation
{
    if (t.omniRpState != 2) return;          // 1: the saved copy's own load
    omniRpRead(t);                           // the old document still answers
    t.omniRpState = 0;
    t.omniRpId.clear();
}
static void omniRpWheel()                                                       // omniPageWheel()
{
    Tab* t = active();
    if (t && t->omniRpState == 2) omniRpLastWheel = SDL_GetTicks() | 1u;
}
static void omniRpWillOpen(const RL::Entry& e)                                  // omniRlOpenSaved()
{
    omniRpOpeningId = e.id;
    omniRpOpeningPrivate = active() && active()->omniPrivate;
}
static void omniRpOpened(Tab& t)                                                // the saved copy is loading in t
{
    if (omniRpOpeningId.empty()) return;
    int to = 0;
    { std::lock_guard<std::mutex> g(omniRlLock); const auto it = omniRpMap.find(omniRpOpeningId); to = ORPG::restoreTo(it == omniRpMap.end() ? nullptr : &it->second); }
    t.omniRpId = omniRpOpeningId;
    t.omniRpTrack = !omniRpOpeningPrivate && !t.omniPrivate;
    t.omniRpRestore = to;
    t.omniRpState = 1;
    omniRpOpeningId.clear();
}

// --- "Remove finished items after 7 days" ------------------------------------------------------------------------------
static void omniRpPruneLoad()
{
    if (omniRpPruneRead) return;
    omniRpPruneRead = true;
    omniRpPruneOn = access(ORPG::kPruneFlag, F_OK) == 0;
}
static bool omniRpPrune()   // false: the list is not loaded yet
{
    omniRpPruneLoad();
    std::vector<std::string> ids;
    {
        std::lock_guard<std::mutex> g(omniRlLock);
        if (!omniRlLoaded) return false;
        ids = ORPG::prunePlan(omniRlList, omniRpMap, (long long)time(nullptr), omniRpPruneOn);
        if (ids.empty()) return true;
        omniRlList.erase(std::remove_if(omniRlList.begin(), omniRlList.end(), [&](const RL::Entry& x) {
            return std::find(ids.begin(), ids.end(), x.id) != ids.end(); }), omniRlList.end());
        for (const auto& id : ids) omniRpMap.erase(id);
    }
    std::thread([ids] {
        std::lock_guard<std::mutex> fl(omniRlFileLock);
        for (const auto& id : ids) if (RL::validId(id)) unlink(omniRlPath(id).c_str());
        omniRlWriteIndexLocked();
    }).detach();
    fprintf(stderr, "OMNI READING PROGRESS: removed %zu finished page(s)\n", ids.size());
    notice(ids.size() == 1 ? std::string("Removed 1 finished page from the reading list")
                           : "Removed " + std::to_string(ids.size()) + " finished pages from the reading list");
    if (omniRlPanelShown()) omniFxRefresh();
    return true;
}

// --- Reading list panel ------------------------------------------------------------------------------------------------
static void omniRpPanelRows(OmniFxPanel& p)
{
    omniRpPruneLoad();
    OmniFxRow r; r.id = ORPG::kRowPrune; r.label = "Remove finished items after 7 days";
    r.value = omniRpPruneOn ? "On" : "Off";
    r.detail = "Finished = read to 95 %";
    p.rows.push_back(r);
}
static bool omniRpPanelInput(const OmniFxRow& r, int b)
{
    if (r.id != ORPG::kRowPrune) return false;
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    omniRpPruneLoad();
    if (omniRpPruneOn) {
        if (unlink(ORPG::kPruneFlag) && errno != ENOENT) { notice("Couldn't change the setting"); return true; }
        omniRpPruneOn = false;
        notice("Finished pages stay in the reading list");
    } else {
        FILE* f = fopen(ORPG::kPruneFlag, "wb");
        if (!f) { notice("Couldn't change the setting"); return true; }
        fclose(f);
        omniRpPruneOn = true;
        notice("Finished pages are removed 7 days after you finish them");
        omniRpPrune();
    }
    omniFxRefresh();
    return true;
}
static std::string omniRpRowValue(const std::string& id, const std::string& size)
{
    std::lock_guard<std::mutex> g(omniRlLock);
    const auto it = omniRpMap.find(id);
    return ORPG::rowValue(it == omniRpMap.end() ? nullptr : &it->second, size);
}

// --- per pass (omniF3Tick) ----------------------------------------------------------------------------------------------
static void omniRpTick(uint32_t now)
{
    for (auto& up : tabs) {
        Tab& t = *up;
        if (t.omniRpState != 1 || t.loading) continue;
        if (t.crashed || (!t.url.empty() && t.url.rfind("about:", 0) != 0)) { t.omniRpState = 0; t.omniRpId.clear(); continue; }
        if (t.omniRpRestore > 0) {
            auto js = adoptWK(WKStringCreateWithUTF8CString(ORPG::restoreScript(t.omniRpRestore).c_str()));
            WKPageEvaluateJavaScriptInMainFrame(t.page, js.get(), nullptr, [](WKTypeRef, WKErrorRef, void*) { });
        }
        t.omniRpState = t.omniRpTrack ? 2 : 0;
        if (!t.omniRpTrack) t.omniRpId.clear();
    }
    Tab* a = active();
    if (omniRpLastWheel && now - omniRpLastWheel > 1500) {
        omniRpLastWheel = 0;
        if (a) omniRpRead(*a);
    }
    const bool panel = !omniFxStack.empty();
    if (panel && !omniRpPanelWas && a) omniRpRead(*a);   // Options / Tabs / any panel over the page (also Exit Omni)
    omniRpPanelWas = panel;
    if (now - omniRpPruneAt > (omniRpPrunedOnce ? 3600000u : 10000u)) {
        omniRpPruneAt = now;
        omniRpPruneLoad();
        if (omniRpPruneOn && omniRpPrune()) omniRpPrunedOnce = true;
    }
}
'''

TAB_FIELD = ('    uint8_t omniTaBadge = 0;   // OMNI_TAB_AUDIO_V1: OmniTabAudio::Badge last drawn\n',
             '    uint8_t omniTaBadge = 0;   // OMNI_TAB_AUDIO_V1: OmniTabAudio::Badge last drawn\n'
             '    // OMNI_READING_PROGRESS_V1: a reading-list saved copy shown in this tab (entry id), its restore target (permille),\n'
             '    // 0 none / 1 loading (restore pending) / 2 tracked, and whether it may update progress (not from private tabs)\n'
             '    std::string omniRpId;\n'
             '    int omniRpRestore = 0;\n'
             '    uint8_t omniRpState = 0;\n'
             '    bool omniRpTrack = false;\n')

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniReadingList.h" // OMNI_READING_LIST_V1: reading list index, caps, saved-page wrapper (pure)\n',
         '#include "OmniReadingList.h" // OMNI_READING_LIST_V1: reading list index, caps, saved-page wrapper (pure)\n'
         '#include "OmniReadingProgress.h" // OMNI_READING_PROGRESS_V1: progress lines, finished rule, prune plan (pure)\n'),
        TAB_FIELD,
        ('Tab* active() { return tabs.empty() ? nullptr : tabs[selected].get(); }\n',
         'Tab* active() { return tabs.empty() ? nullptr : tabs[selected].get(); }\n'
         '// OMNI_READING_PROGRESS_V1 (OmniReadingProgressShell.h): one scroll read when a saved copy is left / navigated away\n'
         'static void omniRpLeaving(Tab& t);\n'
         'static void omniRpNavigating(Tab& t);\n'
         'static void omniRpWheel();\n'),
        ('    omniShoulderCancel(); // OMNI_SHOULDER_DOWNLOADS_V1\n    selected = index;\n',
         '    if (active() && selected != index) omniRpLeaving(*active()); // OMNI_READING_PROGRESS_V1: the tab being left\n'
         '    omniShoulderCancel(); // OMNI_SHOULDER_DOWNLOADS_V1\n    selected = index;\n'),
        ('        omniPaintHoldBegin(tab, page); // OMNI_PAINT_HOLD_V1\n',
         '        omniRpNavigating(tab); // OMNI_READING_PROGRESS_V1: last read of a saved copy (old document still there)\n'
         '        omniPaintHoldBegin(tab, page); // OMNI_PAINT_HOLD_V1\n'),
        ('void omniPageWheel(double amount)\n{\n',
         'void omniPageWheel(double amount)\n{\n'
         '    omniRpWheel(); // OMNI_READING_PROGRESS_V1: read once after the scrolling stops\n'),
    ],
    'OmniReadingListShell.h': [
        ('namespace RL = OmniReadingList;\n',
         'namespace RL = OmniReadingList;\n'
         '// OMNI_READING_PROGRESS_V1 (OmniReadingProgressShell.h, included after this file)\n'
         'static void omniRpLoadFrom(const std::string& text);\n'
         'static void omniRpAppendLocked(std::string& text);\n'
         'static void omniRpWillOpen(const RL::Entry& e);\n'
         'static void omniRpOpened(Tab& t);\n'
         'static void omniRpPanelRows(OmniFxPanel& p);\n'
         'static bool omniRpPanelInput(const OmniFxRow& r, int b);\n'
         'static std::string omniRpRowValue(const std::string& id, const std::string& size);\n'),
        ('    { std::lock_guard<std::mutex> g(omniRlLock); text = RL::serialize(omniRlList); }\n',
         '    { std::lock_guard<std::mutex> g(omniRlLock); text = RL::serialize(omniRlList); omniRpAppendLocked(text); } // OMNI_READING_PROGRESS_V1: + progress lines\n'),
        ('    if (omniRlReadFile(omniRlPath(RL::kIndexName), text, 8 << 20)) list = RL::parse(text);\n',
         '    if (omniRlReadFile(omniRlPath(RL::kIndexName), text, 8 << 20)) list = RL::parse(text);\n'
         '    omniRpLoadFrom(text); // OMNI_READING_PROGRESS_V1: the progress lines of the same file\n'),
        ('    notice("Opening saved page...");\n',
         '    notice("Opening saved page...");\n'
         '    omniRpWillOpen(e); // OMNI_READING_PROGRESS_V1\n'),
        ('            WKPageLoadHTMLString(t->page, s.get(), nullptr);\n            t->loading = true;\n',
         '            WKPageLoadHTMLString(t->page, s.get(), nullptr);\n            t->loading = true;\n'
         '            omniRpOpened(*t); // OMNI_READING_PROGRESS_V1: restore after the load, then track\n'),
        ('    s.value = omniRlPhase.load() ? std::string("Saving...") : t && t->omniPrivate ? std::string("Not in private tabs") : std::string();\n'
         '    p.rows.push_back(s);\n    if (!loaded || omniRlShown.empty()) {\n',
         '    s.value = omniRlPhase.load() ? std::string("Saving...") : t && t->omniPrivate ? std::string("Not in private tabs") : std::string();\n'
         '    p.rows.push_back(s);\n'
         '    omniRpPanelRows(p); // OMNI_READING_PROGRESS_V1: Remove finished items after 7 days\n'
         '    if (!loaded || omniRlShown.empty()) {\n'),
        ('        r.value = RL::sizeText(e.bytes);\n',
         '        r.value = omniRpRowValue(e.id, RL::sizeText(e.bytes)); // OMNI_READING_PROGRESS_V1: "40% read" / "Finished"\n'),
        ('    if (r.id < omniRlRowFirst) return b == SDL_CONTROLLER_BUTTON_A;\n',
         '    if (omniRpPanelInput(r, b)) return true; // OMNI_READING_PROGRESS_V1\n'
         '    if (r.id < omniRlRowFirst) return b == SDL_CONTROLLER_BUTTON_A;\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniReadingListShell.h" // OMNI_READING_LIST_V1\n',
         '#include "OmniReadingListShell.h" // OMNI_READING_LIST_V1\n'
         '#include "OmniReadingProgressShell.h" // OMNI_READING_PROGRESS_V1\n'),
        ('    omniRlTick(now);    // OMNI_READING_LIST_V1\n',
         '    omniRlTick(now);    // OMNI_READING_LIST_V1\n'
         '    omniRpTick(now);    // OMNI_READING_PROGRESS_V1: restore after load, read after a scroll pause, prune\n'),
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


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def code_only(src):
    """A sibling apply_*.py without its comments and module docstring (line numbers kept): names mentioned only in its
    notes are not a use. Numeric ids are never looked for in siblings (their notes list other patches' id ranges)."""
    import io
    import tokenize
    cut, first = [], True
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type == tokenize.COMMENT or (first and t.type == tokenize.STRING):
                cut.append((t.start, t.end))
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                              tokenize.ENCODING):
                first = False
    except (tokenize.TokenError, SyntaxError):
        return ''.join(r for r in src.splitlines(True) if not r.lstrip().startswith('#'))
    starts = [0] + [i + 1 for i, c in enumerate(src) if c == '\n']   # tokenize's rows end at '\n' only
    out = list(src)
    for (r0, c0), (r1, c1) in cut:
        for i in range(starts[r0 - 1] + c0, starts[r1 - 1] + c1):
            if out[i] not in '\r\n':
                out[i] = ' '
    return ''.join(out)


def check_ids():
    """Row id ROW_ID and the omniRp / ORPG / OmniReadingProgress names must be ours alone: refuse when any source in the
    tree (or, names only, the code of any other tools/apply_*.py) already uses them. Skipped once this patch is in
    (re-runs). The row id is looked for in the engine tree only: sibling scripts' notes list other patches' ids."""
    if any(MARK in (root / n).read_bytes().decode('utf-8') for n in EDITS):
        return
    rx_id = re.compile(r'\b%d\b' % ROW_ID)
    rx_name = re.compile(r'\bomniRp[A-Z]\w*|\bORPG\b|\bOmniReadingProgress\b')
    for f in sorted(root.iterdir()):
        if f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        for i, line in enumerate(cpp_code(f.read_text(encoding='utf-8', errors='replace')).split('\n'), 1):
            if rx_id.search(line) or (f.name not in GUIDE and rx_name.search(line)):
                sys.exit('row id %d / name already used: %s:%d: %s' % (ROW_ID, f.name, i, line.strip()[:120]))
    me = Path(__file__).resolve()
    for f in sorted(tools.glob('apply_*.py')):
        if f.resolve() == me:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        for i, line in enumerate(code_only(f.read_text(encoding='utf-8', errors='replace')).splitlines(), 1):
            if rx_name.search(line):
                sys.exit('name already used by %s:%d: %s' % (f.name, i, line.strip()[:120]))


def main():
    needs = [('OmniReadingListShell.h', 'OMNI_READING_LIST_V1', 'apply_reading_list.py'),
             ('OmniBrowser.cpp', 'OMNI_TAB_AUDIO_V1', 'apply_tab_audio.py')]
    for name, mark, script in needs:
        if not (root / name).exists() or mark not in (root / name).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (name, mark, script))
    check_ids()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniReadingProgress.h', PURE, 'OmniReadingList.h'),
            write_new('OmniReadingProgressShell.h', SHELL, 'OmniReadingListShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
