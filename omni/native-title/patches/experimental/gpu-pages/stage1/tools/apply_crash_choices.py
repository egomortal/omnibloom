#!/usr/bin/env python3
"""OMNI_CRASH_CHOICES_V1 (2026-11-16): backlog E24, a crashed tab that tells you what to try.

What existed (grep of the patched tree, chain_final order)
  OmniBrowser.cpp newTab(): nav.webProcessDidCrash sets Tab::crashed, cancels the paint hold, sets tab.message
  ("Page process stopped. Try Reload."), drops the tab's dialogs, leaves page fullscreen / editing on the active tab
  and logs "web process crashed". OmniErrorPage.h (OMNI_FEATURES_V1) then draws its error panel for the crashed tab:
  "This page stopped working", Cross = Reload (WKPageReload), Circle = Back (or hide the panel: crashDismissed).
  There was NO automatic reload anywhere (offline retry explicitly never reloads crashed tabs; tab sleep never unloads
  them; the RELOAD TEST self-test reloads by itself, and self-test modes never show the panel).

What the user sees now
  The crashed tab's panel (same place, size grows with its contents) lists choices, D-pad up / down picks, Cross runs it,
  the pointer can click a row; Circle keeps its old meaning (Back, or hide the panel):
    Reload                        as before (the old Cross).
    Open in Reader view           reload, then the engine Reader view (omniReaderStart, the menus' one) once that load
                                  finishes in the shown tab (60 s at most; a crash meanwhile cancels it). Web pages only.
    Reload with Data saver        turns Data saver on (OMNI_DATA_SAVER_V1: data-saver.txt, its prefetch / font parts)
                                  and reloads; "Reload (Data saver is on)" when it already is. Web pages only.
    Unload other tabs and reload  unloads every other tab omniTmCanUnload allows (OMNI_TAB_MEMORY_VIEW_V1's forced
                                  unload: session history kept, reloads when shown), except "Keep loaded" tabs and
                                  private tabs (unloading a private tab drops it for good), then reloads. Shown while
                                  there is another tab.
    Close tab                     closeTab().
  Crashes are counted per host in this session (memory only; never written). From the 2nd crash on the same host the
  panel adds, in amber: "This site crashed twice. Try Lite mode or Data saver." (Lite mode is backlog E23.)
  Automatic reload (new, small): a tab whose page crashed while it was in the BACKGROUND reloads once when it is shown
  (Chrome does the same), instead of showing the panel. Loop guard: never when the last two crashes on that host were
  within 5 minutes; then the panel shows. A tab that crashes while shown always gets the panel. Never in self-tests.
Private tabs: their crashes go to a ledger of their own (memory only, gone when Omni closes); nothing is written; logs
  never carry a host for any tab ("OMNI CRASH: page process ended (crash 2 on this site this session, private tab)").

Names: namespace OmniCrashChoices, alias OCRC, prefix omniCrc (grep of the tree and every sibling apply_*.py's code:
  free; checked again before the first apply). No settings rows, no ids.
Pure part: tools/OmniCrashChoices.h -> engine/entry (host key, ledger, loop guard, choices, focus, layout, texts).
  Tested by tools/test_crash_choices.cpp:  g++ -std=c++20 -Wall -Wextra -I<tools> test_crash_choices.cpp -o t && ./t
Shell side: engine/entry/OmniCrashChoicesShell.h (included from OmniFeatures3.h after OmniDataSaverShell.h).

Anchors (whole lines, exactly once each; MARK makes each file idempotent; inserted lines use /* */ comments):
  OmniBrowser.cpp   the omniReaderStart declaration (apply_reader_auto.py's): + omniCrcCrashed declaration
                    log("web process crashed"); in webProcessDidCrash: + omniCrcCrashed(tab)
  OmniErrorPage.h   the omniHoErrorShown declaration: our declarations before it
                    the omniHoErrorDraw / omniHoErrorButton / omniHoErrorClick handovers: ours after each (the crashed
                    tab's panel; parental and HTTPS-only panels keep drawing first)
  OmniFeatures3.h   the OmniDataSaverShell.h include line: + OmniCrashChoicesShell.h
                    the omniOrTick(now) line of omniF3Tick: + omniCrcTick(now)
Apply AFTER apply_https_only.py, apply_offline_retry.py, apply_data_saver.py, apply_tab_memory_view.py and
apply_reader_auto.py (their lines / functions are used).
usage: apply_crash_choices.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_CRASH_CHOICES_V1'
if len(sys.argv) != 2:
    sys.exit('usage: apply_crash_choices.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
HERE = Path(__file__).resolve().parent
NAMES = (r'\bomniCrc[A-Z]', r'\bOCRC\b', r'\bOmniCrashChoices')

SHELL = r'''// OMNI_CRASH_CHOICES_V1: the crashed tab's panel with choices, shell side. Included from OmniFeatures3.h (inside
// OmniBrowser.cpp's anonymous namespace, after OmniDataSaverShell.h). The pure part is OmniCrashChoices.h; the reasons
// are in tools/apply_crash_choices.py. Main thread only. Nothing here is written to disk.
#pragma once
#include "OmniCrashChoices.h"

namespace OCRC = OmniCrashChoices;
struct OmniCrcTab {
    std::string host;          // the crashed page's host key (never logged)
    int count = 0;             // crashes on that host this session (its ledger)
    bool autoPending = false;  // crashed in the background: reload once when shown (loop guard said yes)
    bool readerPending = false;
    uint32_t readerAt = 0;
};
static OCRC::Ledger omniCrcLedger, omniCrcPrivLedger;   // memory only; private tabs never share the normal one
static std::unordered_map<const Tab*, OmniCrcTab> omniCrcTabs;
static int omniCrcFocus = 0;
static const Tab* omniCrcFocusTab = nullptr;

// webProcessDidCrash (OmniBrowser.cpp), after the old handler did its part.
static void omniCrcCrashed(Tab& tab)
{
    if (omniTestMode()) return;
    const uint32_t now = SDL_GetTicks();
    OCRC::Ledger& ledger = tab.omniPrivate ? omniCrcPrivLedger : omniCrcLedger;
    OmniCrcTab& s = omniCrcTabs[&tab];
    s.host = OCRC::hostKey(tab.url);
    s.count = ledger.note(s.host, now);
    s.readerPending = false;
    s.autoPending = &tab != active() && ledger.autoReloadOk(s.host);
    omniFxState(&tab).crashDismissed = false;
    if (&tab == active()) { omniCrcFocus = 0; omniCrcFocusTab = &tab; }
    fprintf(stderr, "%s\n", OCRC::logLine(s.count, tab.omniPrivate, s.autoPending).c_str()); fflush(stderr);
}

static bool omniCrcShown()
{
    Tab* t = active();
    return t && t->crashed && !omniTestMode() && omniFxErrorShown();
}
static bool omniCrcSaverOn() { omniDsvLoad(); return omniDsv.on; }
static std::vector<OCRC::Choice> omniCrcChoices(const Tab& t) { return OCRC::choices(omniWebURL(t.url), tabs.size() > 1); }

struct OmniCrcGeom { int x = 0, y = 0; double zoom = 1.0; OCRC::Layout L; std::vector<std::string> body; bool advice = false; };
static OmniCrcGeom omniCrcGeom(const Tab& t, int rows)
{
    OmniCrcGeom g;
    g.body = omniWrap(OCRC::kBody, omniSmall, OCRC::kW - 128, 2);
    auto f = omniCrcTabs.find(&t);
    g.advice = f != omniCrcTabs.end() && OCRC::showAdvice(f->second.host, f->second.count);
    g.L = OCRC::layout(int(g.body.size()), g.advice, rows);
    if (omniUisLevel() != OUIS::Normal) { /* OMNI_UI_SCALE_V1_R2: zoomed layout space, centred on the page */
        const OUIS::BoxFit b = OUIS::fitBox(omniUisLevel(), OCRC::kW, g.L.h, 0, 0, omniPageTop(), omniPageBottom());
        g.zoom = b.zoom; g.x = b.x; g.y = b.y;
        return g;
    }
    const int py0 = omniPageTop(), py1 = omniPageBottom();
    g.x = (width - OCRC::kW) / 2;
    g.y = py0 + std::max(10, (py1 - py0 - g.L.h) / 2);
    return g;
}

static void omniCrcReloadNow(Tab& t, const char* text)
{
    omniFxState(&t).crashDismissed = false;
    WKPageReload(t.page);
    notice(text);
}
static int omniCrcUnloadOthers()
{
    int n = 0;
    std::vector<Tab*> others;
    for (auto& x : tabs) if (x.get() != active()) others.push_back(x.get());
    for (Tab* o : others) {
        if (o->omniPrivate || omniTmvKept(*o) || !omniTmCanUnload(*o)) continue;
        if (omniTmvUnload(*o)) ++n;
    }
    return n;
}
static void omniCrcRun(OCRC::Choice c)
{
    Tab* t = active();
    if (!t) return;
    fprintf(stderr, "OMNI CRASH: choice %d\n", int(c)); fflush(stderr);
    switch (c) {
    case OCRC::Reload: omniFxErrorRetry(); break;
    case OCRC::Reader: {
        OmniCrcTab& s = omniCrcTabs[t];
        s.readerPending = true;
        s.readerAt = SDL_GetTicks();
        omniCrcReloadNow(*t, OCRC::kReaderNotice);
        break;
    }
    case OCRC::DataSaver: {
        omniDsvLoad();
        const bool was = omniDsv.on;
        if (!was) { omniDsv.on = true; omniDsvWrite(); omniDsvApply(); omniShellDirty = true; }
        omniCrcReloadNow(*t, OCRC::saverNotice(was).c_str());
        break;
    }
    case OCRC::UnloadOthers: {
        const int n = omniCrcUnloadOthers();
        omniCrcReloadNow(*t, OCRC::unloadNotice(n).c_str());
        break;
    }
    case OCRC::CloseTab:
        omniCrcTabs.erase(t);
        closeTab();
        break;
    }
    omniShellDirty = true;
}

static bool omniCrcDraw()
{
    if (!omniCrcShown()) return false;
    Tab* t = active();
    if (omniCrcFocusTab != t) { omniCrcFocusTab = t; omniCrcFocus = 0; }
    const std::vector<OCRC::Choice> ch = omniCrcChoices(*t);
    omniCrcFocus = OCRC::moveFocus(omniCrcFocus, 0, int(ch.size()));
    const OmniCrcGeom g = omniCrcGeom(*t, int(ch.size()));
    const OmniTheme& T = omniTheme();
    const int py0 = physical(omniPageTop()), py1 = physical(omniPageBottom());
    omniRectPx({ 0, py0, canvas->w, std::max(0, py1 - py0) }, T.bg, 200);
    OmniUisZoomScope uisZoom(g.zoom, true); /* OMNI_UI_SCALE_V1_R2: row hover uses the zoomed pointer */
    const int x = g.x, y = g.y, w = OCRC::kW;
    omniShadow(x, y, w, g.L.h, omniRadius + 2, 22, 160, 6);
    fillRounded(x, y, w, g.L.h, omniRadius + 2, T.panel);
    omniDisc(x + 50, y + 50, 20, omniBad);
    omniIcon(omniIconAlert, x + 50, y + 50, T.bg);
    omniLabel(OCRC::kTitle, x + 88, y + 42, omniBodyBold, T.ink, 0, w - 120);
    omniLabel(omniShownURL(t->url), x + 88, y + 70, omniSmall, T.inkDim, 0, w - 120);
    for (size_t i = 0; i < g.body.size(); ++i) omniLabel(g.body[i], x + 88, y + 108 + int(i) * OCRC::kLineH, omniSmall, T.ink);
    if (g.advice) {
        omniDisc(x + 94, y + g.L.adviceY + 12, 5, omniWarn);
        omniLabel(OCRC::kAdvice, x + 108, y + g.L.adviceY + 12, omniSmallBold, T.ink, 0, w - 140);
    }
    const bool saver = omniCrcSaverOn();
    const int hover = OCRC::rowAt(g.L, int(ch.size()), pointerX - x, pointerY - y);
    for (int i = 0; i < int(ch.size()); ++i) {
        const int ry = y + OCRC::rowY(g.L, i);
        const bool focus = i == omniCrcFocus;
        fillRounded(x + OCRC::kRowX, ry, OCRC::kRowW, OCRC::kRowH, omniRadius, focus ? T.accent : i == hover ? T.hover : T.key);
        if (focus) faceIcon(x + OCRC::kRowX + 24, ry + OCRC::kRowH / 2, 0, playStationIcons);
        omniLabel(OCRC::label(ch[size_t(i)], saver), x + OCRC::kRowX + 46, ry + OCRC::kRowH / 2, omniSmallBold,
                  focus ? T.accentInk : T.ink, 0, OCRC::kRowW - 56);
    }
    const bool canBack = WKPageCanGoBack(t->page);
    faceIcon(x + OCRC::kRowX + 14, y + g.L.hintY, 1, playStationIcons);
    omniLabel(canBack ? "Back" : "Hide", x + OCRC::kRowX + 34, y + g.L.hintY, omniSmall, T.inkDim, 0, 200);
    return true;
}
static bool omniCrcButton(int b)
{
    Tab* t = active();
    if (!t) return false;
    const std::vector<OCRC::Choice> ch = omniCrcChoices(*t);
    switch (b) {
    case SDL_CONTROLLER_BUTTON_A:
        omniCrcFocus = OCRC::moveFocus(omniCrcFocus, 0, int(ch.size()));
        omniCrcRun(ch[size_t(omniCrcFocus)]);
        return true;
    case SDL_CONTROLLER_BUTTON_B: omniFxErrorBack(); return true;
    case SDL_CONTROLLER_BUTTON_DPAD_UP: omniCrcFocus = OCRC::moveFocus(omniCrcFocus, -1, int(ch.size())); omniShellDirty = true; return true;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: omniCrcFocus = OCRC::moveFocus(omniCrcFocus, 1, int(ch.size())); omniShellDirty = true; return true;
    default: return false;   /* Y address, L1 / R1 tabs, Options menu keep working */
    }
}
static bool omniCrcClick(int x, int y)
{
    Tab* t = active();
    if (!t) return false;
    const std::vector<OCRC::Choice> ch = omniCrcChoices(*t);
    const OmniCrcGeom g = omniCrcGeom(*t, int(ch.size()));
    int zx = x, zy = y;
    if (g.zoom != 1.0) omniUisMap(g.zoom, zx, zy);
    const int i = OCRC::rowAt(g.L, int(ch.size()), zx - g.x, zy - g.y);
    if (i >= 0) { omniCrcFocus = i; omniCrcRun(ch[size_t(i)]); return true; }
    return y >= omniPageTop() && y < omniPageBottom();   /* the dimmed page: nothing; the bars still work */
}

// --- per pass (omniF3Tick): the automatic reload of a background crash, Reader view after its reload -------------------
static void omniCrcTick(uint32_t now)
{
    if (omniCrcTabs.empty() || omniTestMode()) return;
    for (auto it = omniCrcTabs.begin(); it != omniCrcTabs.end();) it = omniTabAlive(it->first) ? std::next(it) : omniCrcTabs.erase(it);
    Tab* t = active();
    if (!t) return;
    auto f = omniCrcTabs.find(t);
    if (f == omniCrcTabs.end()) return;
    OmniCrcTab& s = f->second;
    if (s.autoPending && t->crashed) {
        s.autoPending = false;
        fprintf(stderr, "OMNI CRASH: background crash, reloading on show\n"); fflush(stderr);
        omniCrcReloadNow(*t, OCRC::kAutoNotice);
        return;
    }
    if (!t->crashed) s.autoPending = false;
    if (!s.readerPending) return;
    /* a crash during that reload cancels it in omniCrcCrashed; a redirect to another host or 60 s cancel it here */
    if (OCRC::after(now, s.readerAt + OCRC::kReaderWaitMs) || OCRC::hostKey(t->url) != s.host) { s.readerPending = false; return; }
    if (!t->loading && !t->crashed && t->message.empty() && t->loadedAt && OCRC::after(t->loadedAt, s.readerAt)) {
        s.readerPending = false;
        omniReaderStart();
    }
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('static void omniReaderStart(); // OMNI_READER_AUTO_V1: the engine Reader view (defined below)\n',
         'static void omniReaderStart(); // OMNI_READER_AUTO_V1: the engine Reader view (defined below)\n'
         'static void omniCrcCrashed(Tab& tab); /* OMNI_CRASH_CHOICES_V1 (OmniCrashChoicesShell.h): count, choices panel */\n'),
        ('        log("web process crashed");\n',
         '        log("web process crashed");\n'
         '        omniCrcCrashed(tab); /* OMNI_CRASH_CHOICES_V1: per-host count, background reload on show (loop-guarded) */\n'),
    ],
    'OmniErrorPage.h': [
        ('static bool omniHoErrorShown(); // OMNI_HTTPS_ONLY_V1 (OmniHttpsOnlyShell.h): the "no secure connection" panel\n',
         'static bool omniCrcShown(); /* OMNI_CRASH_CHOICES_V1 (OmniCrashChoicesShell.h): the crashed tab\'s choices */\n'
         'static bool omniCrcDraw();\n'
         'static bool omniCrcButton(int b);\n'
         'static bool omniCrcClick(int x, int y);\n'
         'static bool omniHoErrorShown(); // OMNI_HTTPS_ONLY_V1 (OmniHttpsOnlyShell.h): the "no secure connection" panel\n'),
        ('    if (omniHoErrorDraw()) return; // OMNI_HTTPS_ONLY_V1\n',
         '    if (omniHoErrorDraw()) return; // OMNI_HTTPS_ONLY_V1\n'
         '    if (omniCrcDraw()) return; /* OMNI_CRASH_CHOICES_V1: Reload / Reader view / Data saver / Unload others / Close */\n'),
        ('    if (omniHoErrorShown()) return omniHoErrorButton(b); // OMNI_HTTPS_ONLY_V1: Continue / Go back\n',
         '    if (omniHoErrorShown()) return omniHoErrorButton(b); // OMNI_HTTPS_ONLY_V1: Continue / Go back\n'
         '    if (omniCrcShown()) return omniCrcButton(b); /* OMNI_CRASH_CHOICES_V1 */\n'),
        ('    if (omniHoErrorShown()) return omniHoErrorClick(x, y); // OMNI_HTTPS_ONLY_V1\n',
         '    if (omniHoErrorShown()) return omniHoErrorClick(x, y); // OMNI_HTTPS_ONLY_V1\n'
         '    if (omniCrcShown()) return omniCrcClick(x, y); /* OMNI_CRASH_CHOICES_V1 */\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniDataSaverShell.h" // OMNI_DATA_SAVER_V1 (after Downloads progress: its badge sits right of that one)\n',
         '#include "OmniDataSaverShell.h" // OMNI_DATA_SAVER_V1 (after Downloads progress: its badge sits right of that one)\n'
         '#include "OmniCrashChoicesShell.h" /* OMNI_CRASH_CHOICES_V1 (after data saver and tab memory: it uses both) */\n'),
        ('    omniOrTick(now);    // OMNI_OFFLINE_RETRY_V1: network watch while a tab is offline, staggered reloads\n',
         '    omniOrTick(now);    // OMNI_OFFLINE_RETRY_V1: network watch while a tab is offline, staggered reloads\n'
         '    omniCrcTick(now);   /* OMNI_CRASH_CHOICES_V1: background crash reload on show, Reader view after its reload */\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_READER_AUTO_V1',),
         'OmniErrorPage.h': ('OMNI_HTTPS_ONLY_V1', 'OMNI_OFFLINE_RETRY_V1'),
         'OmniFeatures3.h': ('OMNI_DATA_SAVER_V1', 'OMNI_OFFLINE_RETRY_V1', 'OMNI_TAB_MEMORY_VIEW_V1')}


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


# The Controls guide's table names other patches' handlers by design: never a name clash.
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): a name in another patch's notes is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def code_only(src):
    """A sibling apply_*.py without its comments and module docstring (line numbers kept): names mentioned only in its
    notes are not a use."""
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


def names_free():
    """Before a first apply: no other patch (its code) or tree file (its code) uses this patch's names. No ids here."""
    name = re.compile('|'.join(NAMES))
    mine = {'OmniCrashChoices.h', 'OmniCrashChoicesShell.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        m = name.search(code_only(f.read_text(encoding='utf-8', errors='replace')))
        if m:
            sys.exit('%s already uses %r: pick other names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in mine or f.name in GUIDE or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        m = name.search(cpp_code(t))
        if m and MARK not in t:
            sys.exit('%s already uses %r: pick other names' % (f.name, m.group(0)))


def main():
    for fname, needs in NEEDS.items():
        s = (root / fname).read_bytes().decode('utf-8')
        for need in needs:
            if need not in s:
                sys.exit('%s: %s missing: apply its patch first' % (fname, need))
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        names_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    pure = (HERE / 'OmniCrashChoices.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniCrashChoices.h: %s missing' % MARK)
    msgs = [write_new('OmniCrashChoices.h', pure, 'OmniDataSaver.h'),
            write_new('OmniCrashChoicesShell.h', SHELL, 'OmniDataSaverShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
