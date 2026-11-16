#!/usr/bin/env python3
"""OMNI_AUTO_REFRESH_V1 (2026-11-16): hold Cross on a page > "Auto-refresh" (live scores, dashboards, status pages left
on a TV).

What the user sees
  - the page menu (hold Cross over a page, no link / image) has "Auto-refresh" after "Reload", value "Off" or
    "Every 5 min". Cross opens a chooser: Off / 30 s / 1 min / 5 min / 15 min / 30 min (the current one ticked) and
    "Always for this site" On / Off (remembers the tab's interval for the page's host, www. and port ignored; Off
    forgets it). Choosing an interval sets it for THIS tab; when the site is remembered the site follows the choice
    (Off forgets it). Private tabs: per tab only, the site row is disabled, nothing is stored.
  - a tab committing a page of a remembered site gets that interval (unless the user set its own); leaving the
    remembered site turns a remembered timer off again.
  - the shown tab's countdown in the top bar: the reload icon + "4:12", right of the downloads indicator (after the
    sleep timer / offline / downloads badges, placed exactly as they place themselves; layout px, so the interface
    size scales it). Icon only when space is short; nothing when there is no room. "0:00" while the page is asked.
Behaviour
  The tab is reloaded with WKPageReload (not ReloadFromOrigin) when its countdown ends. The countdown restarts at
  every commit (our reload, the user's navigation) and after every skip. A due reload is SKIPPED, and tried again one
  interval later, when (OmniAutoRefresh.h decide()):
    - the tab is asleep / unloaded / not loaded yet (OMNI_TAB_SLEEP_V1, tab memory guard, session restore): never woken
    - it is crashed or loading
    - the page is the result of a form POST (decidePolicyForNavigationAction, main frame: WKURLRequestCopyHTTPMethod;
      a redirect's own decision overwrites it, so POST -> 303 -> GET pages DO refresh; Back/Forward to a POST page
      counts as POST)
    - the console is offline (OMNI_OFFLINE_RETRY_V1's network watch says down) or the tab shows the offline error
      (that feature reloads it when the network is back)
    - media is playing (WKPageGetMediaState: audio or video)
    - shown tab only: the on-screen keyboard is open (`editing`: address bar or a page field), or there was controller /
      pointer input in the last 20 s (omniLastInput, which the shell's own input handling stamps)
    - the page holds unsaved input: tab sleep's one-shot page script (its pure header's probe constant, reused as is; main frame + same-origin frames 2 deep) runs once per due reload, after every check above passed;
      only "c" reloads (re-checked at that moment); "d", an error or no answer in 10 s skips.
  Never refreshed (no countdown chip, the timer silently waits): omni:// built-in pages and every non-http(s) page,
  the Downloads app's tab (omniMediaOwns), Reader view (its HTML commit is seen while tab.omniReader is set; Omni clears
  that flag again when the HTML finishes, so the commit hook keeps its own copy).
Scroll position
  WebKit restores a reload's scroll position itself: FrameLoader::checkLoadCompleteForThisFrame calls
  HistoryController::restoreScrollPositionAndViewState for isReload(loadType) from the current history item, unless
  the user scrolled meanwhile or the page set history.scrollRestoration = "manual" (checked in the engine's WebKit tree (s1/webkit)
  Source/WebCore/loader). Pages that build their content after the load event get clamped near the top, so the probe
  also returns scrollX / scrollY, and 1.5 s after our reload finished one script scrolls back ONLY if the page still
  sits at the top (scrollY < 8), same URL, within 30 s of the reload.
Cost: no tab with a timer: one branch per pass. Otherwise the timers are looked at 4 times a second, one page script
  per due reload, the top bar redrawn once a second while the shown tab's countdown is visible (bars shown).
Log: "OMNI AUTOREFRESH: tab set to N s", "reload #n (every N s): <url>" (1st and every 20th), "skipped (<reason>),
  next in N s: <url>" (when the reason changes), "every N s (remembered for <site>)", "site <site> remembered/forgotten".
Storage: /data/omni/refresh-sites.txt ("host\\tseconds\\n", at most 200 sites, omniIoQueue); never for private tabs.
Ids: page menu row 993 (free among the page menu's rows), chooser kind 7500 (its rows: the
  seconds, "Always for this site" 100), alias OARF, prefix omniArf, namespace OmniAutoRefresh (grep of every apply_*.py
  under outputs/ and the patched r-T tree, 2026-11-16: free; checked again before the first apply: refuses if taken).

What changes
  engine/entry/OmniAutoRefresh.h      (pure; copied from tools/): intervals, site store, timer, countdown text, skip
                                      rules, probe / restore scripts, chip layout.
  engine/entry/OmniAutoRefreshShell.h (copied from tools/): state, hooks, tick, chip, chooser, page menu row.
Anchors (exactly once each; MARK makes each file idempotent; whole lines only, new lines inserted before / after):
  OmniBrowser.cpp      tab sleep's pure include line (ours after it); the downloads progress call of omniDrawTopBar
                       (chip after it); the HTTPS-only policy line of decidePolicyForNavigationAction (POST note
                       before it); the HTTPS-only commit line of didCommitNavigation (commit hook after it).
  OmniFeatures3Decl.h  tab sleep's forget declaration line (our declarations after it).
  OmniFeatures3.h      tab sleep's shell include line; tab sleep's tick line of omniF3Tick.
  OmniTabsPage.h       tab sleep's forget line of omniFxTabClosing.
  OmniContextMenu.h    the add(omniCxReload, "Reload" ...) line; tab audio's context action line of omniFxContextInput.
(Other features' names are spelled in pieces below: their apply scripts refuse while another apply_*.py names them.)
Apply AFTER apply_tab_sleep.py (its lines are anchors; it in turn needs bg audio / dl progress / tab memory view),
apply_offline_retry.py, apply_https_only.py, apply_tab_audio.py.
Tested by tools/test_auto_refresh.cpp:  g++ -std=c++20 -Wall -Wextra -I<tools> test_auto_refresh.cpp -o t && ./t
usage: apply_auto_refresh.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_AUTO_REFRESH_V1'
if len(sys.argv) != 2:
    sys.exit('usage: apply_auto_refresh.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
HERE = Path(__file__).resolve().parent
PURE = HERE / 'OmniAutoRefresh.h'
SHELL = HERE / 'OmniAutoRefreshShell.h'
OURS = ('OmniAutoRefresh.h', 'OmniAutoRefreshShell.h')
TAKEN = (r'(?<![\w.])993(?![\w.])', r'(?<![\w.])7500(?![\w.])', r'\bOARF\b', r'\bomniArf[A-Z]', r'\bOmniAutoRefresh',
         r'refresh-sites\.txt')

TS = 'Omni' 'Tab' 'Sleep'   # spelled in pieces (see above)
TSP = 'omni' 'Tsp'
DLP = 'omni' 'Dlp'
HO = 'omni' 'Ho'
TA = 'omni' 'Ta'

DLP_DRAW = '    ' + DLP + 'DrawTopBar(OmniSmallComforts::battery().bars() >= 0 ? 1155.f : 1130.f); // OMNI_DL_PROGRESS_V1: Downloads progress while jobs run\n'
HO_POLICY = '            if (' + HO + 'Policy(tab, action, request.get(), targetURL, listener)) return; // OMNI_HTTPS_ONLY_V1: http -> https, or the panel\n'
HO_COMMIT = '        ' + HO + 'Committed(*tab); // OMNI_HTTPS_ONLY_V1: the https attempt (if any) worked\n'
TSP_INC = '#include "' + TS + '.h" // OMNI_TAB_SLEEP_V1: Sleep idle tabs: eligibility, order, rate limit, texts (pure)\n'
TSP_DECL = 'static void ' + TSP + 'Forget(const void* tab);                // omniFxTabClosing\n'
TSP_SHELL = '#include "' + TS + 'Shell.h" // OMNI_TAB_SLEEP_V1 (after tab memory, pinned tabs, tab groups, downloads progress)\n'
TSP_TICK = '    ' + TSP + 'Tick(now);   // OMNI_TAB_SLEEP_V1: idle background tabs: one check a minute, at most 2 per check\n'
TSP_CLOSE = '    ' + TSP + 'Forget(&tab); // OMNI_TAB_SLEEP_V1: its idle / asleep state\n'
CX_RELOAD = '        add(omniCxReload, "Reload", t != nullptr, omniIconReload);\n'
CX_TA = '    if (' + TA + 'ContextAction(r.id)) return true; // OMNI_TAB_AUDIO_V1\n'

EDITS = {
    'OmniBrowser.cpp': [
        (TSP_INC, TSP_INC +
         '#include "OmniAutoRefresh.h" // OMNI_AUTO_REFRESH_V1: page menu Auto-refresh: intervals, skip rules, countdown, sites (pure)\n'),
        (DLP_DRAW, DLP_DRAW +
         '    omniArfDrawTopBar(OmniSmallComforts::battery().bars() >= 0 ? 1155.f : 1130.f); // OMNI_AUTO_REFRESH_V1: the shown tab\'s countdown\n'),
        (HO_POLICY,
         '            omniArfPolicy(*tab, request.get()); // OMNI_AUTO_REFRESH_V1: a POST result is never auto-refreshed\n' + HO_POLICY),
        (HO_COMMIT, HO_COMMIT +
         '        omniArfCommitted(*tab); // OMNI_AUTO_REFRESH_V1: countdown restarts; POST / Reader view; remembered sites\n'),
    ],
    'OmniFeatures3Decl.h': [
        (TSP_DECL, TSP_DECL +
         '// OMNI_AUTO_REFRESH_V1 (OmniAutoRefreshShell.h): page menu > Auto-refresh\n'
         'static void omniArfDrawTopBar(float base);                 // omniDrawTopBar: the shown tab\'s countdown\n'
         'static void omniArfPolicy(Tab& t, WKURLRequestRef request); // decidePolicyForNavigationAction (main frame)\n'
         'static void omniArfCommitted(Tab& t);                      // didCommitNavigation\n'
         'static void omniArfForget(const void* tab);                // omniFxTabClosing\n'
         'static void omniArfContextRow(OmniFxPanel& p);             // hold-Cross page menu row\n'
         'static bool omniArfContextAction(int id);\n'),
    ],
    'OmniFeatures3.h': [
        (TSP_SHELL, TSP_SHELL +
         '#include "OmniAutoRefreshShell.h" // OMNI_AUTO_REFRESH_V1 (after tab sleep, offline retry, downloads progress, sleep timer)\n'),
        (TSP_TICK, TSP_TICK +
         '    omniArfTick(now);   // OMNI_AUTO_REFRESH_V1: due reloads (4 looks a second, only while a tab has a timer)\n'),
    ],
    'OmniTabsPage.h': [
        (TSP_CLOSE, TSP_CLOSE + '    omniArfForget(&tab); // OMNI_AUTO_REFRESH_V1: its timer\n'),
    ],
    'OmniContextMenu.h': [
        (CX_RELOAD, CX_RELOAD + '        omniArfContextRow(p); // OMNI_AUTO_REFRESH_V1: Auto-refresh (Off / 30 s .. 30 min)\n'),
        (CX_TA, CX_TA + '    if (omniArfContextAction(r.id)) return true; // OMNI_AUTO_REFRESH_V1\n'),
    ],
}
NEEDS = (('OmniBrowser.cpp', 'OMNI_TAB_SLEEP_V1', 'apply_tab_sleep.py'),
         ('OmniFeatures3.h', 'OMNI_TAB_SLEEP_V1', 'apply_tab_sleep.py'),
         ('OmniFeatures3.h', 'OMNI_OFFLINE_RETRY_V1', 'apply_offline_retry.py'),
         ('OmniFeatures3.h', 'OMNI_DL_PROGRESS_V1', 'apply_dl_progress.py'),
         ('OmniFeatures3.h', 'OMNI_SLEEP_TIMER_V1', 'apply_sleep_timer.py'),
         ('OmniBrowser.cpp', 'OMNI_HTTPS_ONLY_V1', 'apply_https_only.py'),
         ('OmniContextMenu.h', 'OMNI_TAB_AUDIO_V1', 'apply_tab_audio.py'),
         ('OmniTabsPage.h', 'OMNI_TAB_SLEEP_V1', 'apply_tab_sleep.py'),
         (TS + '.h', 'kProbeScript', 'apply_tab_sleep.py'))


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
    data = text.replace('\r\n', '\n').replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


def ids_free():
    """Before the first apply: no engine file and no other apply_*.py may use our ids / names."""
    if any(MARK in (root / n).read_bytes().decode('utf-8') for n in EDITS):
        return
    me = Path(__file__).resolve()
    places = [p for d in (root, root.parent / 'media') if d.is_dir() for p in d.iterdir()
              if p.suffix in ('.h', '.cpp', '.inc') and p.name not in OURS]
    places += [p for p in HERE.glob('apply_*.py') if p.resolve() != me and p.name != 'apply_controls_help.py'
        and MARK not in p.read_text(encoding='utf-8', errors='replace')]   # OMNI_SIBLING_SKIP: guide / dependent patches
    for p in places:
        s = p.read_bytes().decode('utf-8', 'replace')
        for pat in TAKEN:
            m = re.search(pat, s)
            if m:
                sys.exit('%s already uses %r (line %d): pick other ids' % (p.name, m.group(0), s.count('\n', 0, m.start()) + 1))


def main():
    for f in (PURE, SHELL):
        if not f.exists():
            sys.exit('%s missing (it ships next to this script)' % f)
    for f, need, tool in NEEDS:
        if need not in (root / f).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (f, need, tool))
    for name in OURS:   # never overwrite someone else's file
        h = root / name
        if h.exists() and MARK not in h.read_bytes().decode('utf-8', 'replace'):
            sys.exit('%s exists without %s' % (name, MARK))
    ids_free()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniAutoRefresh.h', PURE.read_bytes().decode('utf-8'), TS + '.h'),
            write_new('OmniAutoRefreshShell.h', SHELL.read_bytes().decode('utf-8'), TS + 'Shell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
