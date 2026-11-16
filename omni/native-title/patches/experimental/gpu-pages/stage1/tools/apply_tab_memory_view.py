#!/usr/bin/env python3
"""OMNI_TAB_MEMORY_VIEW_V1 (2026-11-16): Tabs > "Memory..." panel: which tabs are loaded / unloaded, the shell's
memory, and "Unload this tab" / "Unload all background tabs" / "Keep this tab loaded".
What can be measured (audit of the r-T tree with every patch up to apply_text_cache_cap.py)
  - Every tab shares ONE web process (OmniEngineSetup.cpp / OmniBrowser.cpp WKContextSetUsesSingleWebProcess, the
    private context too). Its memory cannot be read from the shell: WKContextGetStatistics is an empty stub on this
    port (OmniTabMemory.h says so) and there is no per-page memory API. So there is NO per-tab number; a row says
    loaded / unloaded only, and an info row says why ("Memory per tab: Not readable").
  - The shell's own flexible memory: sceKernelConfiguredFlexibleMemorySize - sceKernelAvailableFlexibleMemorySize.
    Both are in the launch title's imports (titlefix-rc6/merge/imports-launch.txt) and already declared at file
    scope in OmniBrowser.cpp (the startup "memory budget" log). sceKernelGetDirectMemorySize is the size of the
    direct-memory pool, not a usage, so it is not shown. No new import.
  - The hardware decoders' shared memory (OmniMedia::Hw::openDecoderCount, as the OMNI TABMEM line) and the rendered-
    text cache (omniTcCache, OMNI_TEXT_CACHE_CAP_V1).
  The summary says "Shell 312 MB . 3 of 9 tabs loaded" (not "Omni": the web process is not in it); the hint line
  "780 MB free . video 48 MB . text 12 MB".
Panel (Tabs > Memory..., kind 7440): one row per tab "<filled / hollow disc> title", value Current / Loaded /
  Loaded, pinned / Kept loaded / Unloaded / Playing / Loading / Stopped / Media, detail the address; then
  "Unload all background tabs" (value "<n> tabs") and the info row. Cross: switch to the tab. Square: unload it
  (the shown tab, a tab playing / loading / crashed / owned by the media section / not a web page cannot be: a notice
  says why; unloading a kept tab ends its "Keep loaded"). Triangle: "Keep loaded" on / off, at most 2, session only
  (never saved). Numbers are read when the panel opens and every 2 s while it is on top (omniF3Tick); nothing
  while it is closed or under another panel.
How "Keep loaded" relates to pinned tabs: pinned tabs (OMNI_PINNED_TABS_V1) were already unloaded last, collapsed
  groups' tabs first (OMNI_TAB_GROUPS_V1); that order stays. A kept tab goes after all of them, and is skipped
  entirely by the "more tabs loaded than kept" rule and by "Unload all"; only "shell memory low" / "new tab refused"
  may take it, as the last resort. "Unload all" includes pinned tabs (the pin is a strip position; Keep loaded is the
  memory pin).
What changes
  - engine/entry/OmniTabMemoryView.h (pure; copied from tools/): order, plans, keep set, texts.
  - engine/entry/OmniTabMemoryViewShell.h (copied from tools/): state, omniTmvPick, the panel, the Tabs row, tick.
  - omniTmUnloadOne: its pick loop becomes omniTmvPick(why) (same order when nothing is kept, plus the forced tab of
    the panel); the unload itself is unchanged.
  Names: omniTmv*, namespace OmniTabMemoryView (alias OTMV); ids: Tabs row 120, panel kind 7440, rows 200 / 201.
Anchors (exactly once each; MARK makes each file idempotent; whole lines only):
  OmniBrowser.cpp      the OmniTextCacheCap.h include line (file scope).
  OmniFeatures3Decl.h  the omniTgCollapsedTab declaration line.
  OmniTabMemory.h      the "// Unloads the least recently shown" comment line; the pick block of omniTmUnloadOne
                       ("Tab* best = nullptr;" .. "if (!best) return false;").
  OmniTabsPage.h       the omniPnForget line; the omniTsTabsRows line; the omniTsTabsInput line.
  OmniFeatures3.h      the omniOrTick line of omniF3Tick.
Tested by tools/test_tab_memory_view.cpp:
  g++ -std=c++20 -Wall -Wextra -I<tools> test_tab_memory_view.cpp -o t && ./t
usage: apply_tab_memory_view.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_TAB_MEMORY_VIEW_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'
HERE = Path(__file__).parent
PURE = HERE / 'OmniTabMemoryView.h'
SHELL = HERE / 'OmniTabMemoryViewShell.h'

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniTextCacheCap.h" // OMNI_TEXT_CACHE_CAP_V1: byte budget + LRU for rendered UI text (pure)\n',
         '#include "OmniTextCacheCap.h" // OMNI_TEXT_CACHE_CAP_V1: byte budget + LRU for rendered UI text (pure)\n'
         '#include "OmniTabMemoryView.h" // OMNI_TAB_MEMORY_VIEW_V1: Tabs > Memory: unload order, keep-loaded set, texts (pure)\n'),
    ],
    'OmniFeatures3Decl.h': [
        ("static bool omniTgCollapsedTab(const Tab& t);              // omniTmUnloadOne: a collapsed group's tabs go first\n",
         "static bool omniTgCollapsedTab(const Tab& t);              // omniTmUnloadOne: a collapsed group's tabs go first\n"
         '// OMNI_TAB_MEMORY_VIEW_V1 (OmniTabMemoryViewShell.h): Tabs > Memory\n'
         'static void omniTmvForget(const void* tab);                // omniFxTabClosing: drops "Keep loaded"\n'
         'static void omniTmvTabsRow(OmniFxPanel& p);                // Tabs panel: "Memory..." row\n'
         'static bool omniTmvTabsInput(const OmniFxRow& r, int b);\n'
         'static void omniTmvTick(uint32_t now);                     // omniF3Tick: numbers every 2 s while the panel is on top\n'),
    ],
    'OmniTabMemory.h': [
        ('// Unloads the least recently shown background tab; false when none qualifies.\n',
         '#include "OmniTabMemoryViewShell.h" // OMNI_TAB_MEMORY_VIEW_V1: Tabs > Memory panel, "Keep loaded", omniTmvPick\n'
         '// Unloads the least recently shown background tab; false when none qualifies.\n'),
        ('    Tab* best = nullptr;\n'
         '    uint32_t oldest = UINT32_MAX;\n'
         '    for (auto& t : tabs) {\n'
         '        if (!omniTmCanUnload(*t)) continue;\n'
         '        const uint32_t at = omniTmTabs[t.get()].shownAt;\n'
         "        if (!best || OmniTabGroups::unloadsBefore(omniPtPinned(*t), omniTgCollapsedTab(*t), at, omniPtPinned(*best), omniTgCollapsedTab(*best), oldest)) { best = t.get(); oldest = at; } // OMNI_PINNED_TABS_V1: pinned tabs last; OMNI_TAB_GROUPS_V1: then collapsed groups' tabs first\n"
         '    }\n'
         '    if (!best) return false;\n',
         '    // OMNI_TAB_MEMORY_VIEW_V1: OTMV::pickUnload: pinned tabs last (OMNI_PINNED_TABS_V1), collapsed groups\' tabs first\n'
         '    // (OMNI_TAB_GROUPS_V1), then least recently shown; "Keep loaded" tabs only when memory is low; or the panel\'s tab.\n'
         '    Tab* best = omniTmvPick(why);\n'
         '    if (!best) return false;\n'),
    ],
    'OmniTabsPage.h': [
        ('    omniPnForget(&tab); // OMNI_POPUP_NOTICE_V1: its Blocked pop-ups list\n',
         '    omniPnForget(&tab); // OMNI_POPUP_NOTICE_V1: its Blocked pop-ups list\n'
         '    omniTmvForget(&tab); // OMNI_TAB_MEMORY_VIEW_V1: its "Keep loaded" mark\n'),
        ('    omniTsTabsRows(p); // OMNI_TAB_SESSIONS_V1: Save these tabs as a session..., Sessions...\n',
         '    omniTsTabsRows(p); // OMNI_TAB_SESSIONS_V1: Save these tabs as a session..., Sessions...\n'
         '    omniTmvTabsRow(p); // OMNI_TAB_MEMORY_VIEW_V1: Memory... (loaded / unloaded tabs, unload, keep loaded)\n'),
        ('    if (omniTsTabsInput(r, b)) return true; // OMNI_TAB_SESSIONS_V1\n',
         '    if (omniTmvTabsInput(r, b)) return true; // OMNI_TAB_MEMORY_VIEW_V1\n'
         '    if (omniTsTabsInput(r, b)) return true; // OMNI_TAB_SESSIONS_V1\n'),
    ],
    'OmniFeatures3.h': [
        ('    omniOrTick(now);    // OMNI_OFFLINE_RETRY_V1: network watch while a tab is offline, staggered reloads\n',
         '    omniOrTick(now);    // OMNI_OFFLINE_RETRY_V1: network watch while a tab is offline, staggered reloads\n'
         '    omniTmvTick(now);   // OMNI_TAB_MEMORY_VIEW_V1: Memory panel numbers every 2 s while it is on top\n'),
    ],
}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits, mark=MARK):
    s = (root / name).read_bytes().decode('utf-8')
    if mark in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits, mark=MARK):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if mark in s:
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
    data = text.replace('\r\n', '\n').replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


def main():
    for f in (PURE, SHELL):
        if not f.exists():
            sys.exit('%s missing (it ships next to this script)' % f)
    for name in ('OmniTabMemoryView.h', 'OmniTabMemoryViewShell.h'):   # never overwrite someone else's file
        h = root / name
        if h.exists() and MARK not in h.read_bytes().decode('utf-8', 'replace'):
            sys.exit('%s exists without %s' % (name, MARK))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniTabMemoryView.h', PURE.read_bytes().decode('utf-8'), 'OmniTabSessions.h'),
            write_new('OmniTabMemoryViewShell.h', SHELL.read_bytes().decode('utf-8'), 'OmniTabMemory.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
