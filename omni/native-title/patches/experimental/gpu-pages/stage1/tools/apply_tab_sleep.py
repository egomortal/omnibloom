#!/usr/bin/env python3
"""OMNI_TAB_SLEEP_V1 (2026-11-16): Browser settings > "Sleep idle tabs": Off / After 10 / 30 / 60 min (default 30),
plus "Include pinned tabs" (default Off). A background tab not shown for that long is unloaded ("put to sleep") so
memory stays free; it reloads when shown, exactly as a tab the count guard unloaded (same omniTmUnloadOne: session
history copied, about:blank, back/forward kept). This is ON TOP of today's guards in OmniTabMemory.h ("Tabs kept
loaded" count, shell memory low, new tab refused), which are unchanged.

Never slept (OmniTabSleep.h decide(), in this order)
  - what omniTmCanUnload already refuses: the shown tab, an unloaded / lazy tab, loading, crashed, owned by the media
    section, not a web page, WKPageGetMediaState playing audio or video. Background audio (OMNI_BG_AUDIO_V1) keeps an
    audible hidden video PLAYING, so its tab reports kWKMediaIsPlayingAudio and is never slept; a paused / released
    one may sleep like any idle tab.
  - a tab with a sound badge (OMNI_TAB_AUDIO_V1 omniTaBadge: playing, muted or not), as a second net.
  - private tabs: unloading drops a private page's state for good (no history is kept for it).
  - "Keep loaded" tabs (OMNI_TAB_MEMORY_VIEW_V1 omniTmvKept); pinned tabs (OMNI_PINNED_TABS_V1) unless "Include
    pinned tabs" is on.
  - any tab while a WebKit download runs (omniDownloads not empty), the Downloads app's progress shows or a hand-over
    is in its 10 s window (OMNI_DL_PROGRESS_V1 omniDlp). Downloads are not tied to a tab in the shell, so the whole
    check waits: it never cuts a download's page.
  - a page with unsaved input: once per background stint (from one show to the next) the check runs a one-shot page
    script (WKPageEvaluateJavaScriptInMainFrame, main frame + same-origin frames 2 deep, <= 3000 controls): "d" when
    an input / textarea / select / checkbox / radio / chosen file differs from its default, the focused
    contenteditable holds text, or window.onbeforeunload is set; else "c". Only "c" lets the tab sleep; "d", an error
    or no string keeps it awake until it is shown again; no answer in 30 s: asked again at a later check. It reads no
    values out. The script runs only on a tab already idle long enough, not on every tab switch (cheaper; the answer
    is the state at sleep time).
Rate: one check a minute (the first a minute after start), at most 2 tabs per check (probed or slept), in the count
  guard's order: unpinned before pinned, a collapsed group's tabs first, then the longest idle. Idle time = now -
  shownAt (OmniTmTab; the tab opened in the background and never shown: from the first check that saw it). Wrap-safe.
  While Off: one branch per pass, no map, no script.
Shown as: the Tabs panel row value "Asleep" (omniF3TabRowValue; was "Unloaded") and the Memory panel value "Asleep"
  (same hollow disc / faint title as unloaded: the existing marker); once shown again it is a normal tab.
Storage: /data/omni/tab-sleep.txt ("minutes\t30\npinned\t0\n", omniIoQueue). Log: omniTmUnloadOne's "OMNI TABMEM:
  unloaded background tab (idle tab asleep): <url>"; "OMNI TABSLEEP: stays awake (unsaved input): <url>"; settings.
Ids: Browser settings rows 347 / 348 (inside omniF3SettingsInput's 300..899 range, its switch); alias OTSP, prefix
  omniTsp, namespace OmniTabSleep (grep of every apply_*.py under outputs/ and the patched r-T tree, 2026-11-16: free;
  checked again before the first apply: refuses if another file uses them).

What changes
  engine/entry/OmniTabSleep.h      (pure; copied from tools/): settings, eligibility, order, rate limit, texts, script.
  engine/entry/OmniTabSleepShell.h (copied from tools/): state, probe, tick, settings rows.
Anchors (exactly once each; MARK makes each file idempotent; whole lines only):
  OmniBrowser.cpp           the Background audio pure include line (OMNI_BG_AUDIO_V1; ours after it).
  OmniFeatures3Decl.h       the omniTmvTick declaration line (omniTspAsleep / omniTspForget declared after it).
  OmniFeatures3.h           the Background audio shell include line; the add(omniF3SetKeep ...) line of
                            omniF3SettingsRows; the "case omniF3SetConsole:" line (our case before it); the omniDlpTick
                            line of omniF3Tick.
  OmniTabMemory.h           omniF3TabRowValue's value = "Unloaded" line.
  OmniTabMemoryViewShell.h  the "r.value = OTMV::rowValue(st[i]);" line of omniTmvBuild.
  OmniTabsPage.h            the omniTmvForget line of omniFxTabClosing.
Apply AFTER apply_tab_memory_view.py, apply_dl_progress.py and apply_bg_audio.py (their lines are anchors).
Tested by tools/test_tab_sleep.cpp:  g++ -std=c++20 -Wall -Wextra -I<tools> test_tab_sleep.cpp -o t && ./t
usage: apply_tab_sleep.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_TAB_SLEEP_V1'
if len(sys.argv) != 2:
    sys.exit('usage: apply_tab_sleep.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
HERE = Path(__file__).resolve().parent
PURE = HERE / 'OmniTabSleep.h'
SHELL = HERE / 'OmniTabSleepShell.h'
OURS = ('OmniTabSleep.h', 'OmniTabSleepShell.h')
TAKEN = (r'(?<![\w.])347(?![\w.])', r'(?<![\w.])348(?![\w.])', r'\bOTSP\b', r'\bomniTsp[A-Z]', r'\bOmniTabSleep')

BGA = 'Omni' 'Bg' 'Audio'   # spelled in pieces: apply_bg_audio.py refuses to run while another apply_*.py names it

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "' + BGA + '.h" // OMNI_BG_AUDIO_V1: Background audio setting (pure)\n',
         '#include "' + BGA + '.h" // OMNI_BG_AUDIO_V1: Background audio setting (pure)\n'
         '#include "OmniTabSleep.h" // OMNI_TAB_SLEEP_V1: Sleep idle tabs: eligibility, order, rate limit, texts (pure)\n'),
    ],
    'OmniFeatures3Decl.h': [
        ('static void omniTmvTick(uint32_t now);                     // omniF3Tick: numbers every 2 s while the panel is on top\n',
         'static void omniTmvTick(uint32_t now);                     // omniF3Tick: numbers every 2 s while the panel is on top\n'
         '// OMNI_TAB_SLEEP_V1 (OmniTabSleepShell.h): Browser settings > Sleep idle tabs\n'
         'static bool omniTspAsleep(const Tab& t);                   // Tabs / Memory panel: "Asleep" instead of "Unloaded"\n'
         'static void omniTspForget(const void* tab);                // omniFxTabClosing\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "' + BGA + 'Shell.h" // OMNI_BG_AUDIO_V1\n',
         '#include "' + BGA + 'Shell.h" // OMNI_BG_AUDIO_V1\n'
         '#include "OmniTabSleepShell.h" // OMNI_TAB_SLEEP_V1 (after tab memory, pinned tabs, tab groups, downloads progress)\n'),
        ('    add(omniF3SetKeep, "Tabs kept loaded", omniF3Set.keepLoaded >= omniF3Set.tabLimit ? std::string("All") : std::to_string(omniF3Set.keepLoaded), true);\n',
         '    add(omniF3SetKeep, "Tabs kept loaded", omniF3Set.keepLoaded >= omniF3Set.tabLimit ? std::string("All") : std::to_string(omniF3Set.keepLoaded), true);\n'
         '    omniTspSettingsRows(p); // OMNI_TAB_SLEEP_V1: Sleep idle tabs (Off / 10 / 30 / 60 min), Include pinned tabs\n'),
        ('    case omniF3SetConsole: if (!dir) return false; omniSecBlockSet(!omniSecBlockOn()); return true;   // OMNI_SEC_LOCALHOST_V1\n',
         '    case OmniTabSleep::kRowMinutes: case OmniTabSleep::kRowPinned: return omniTspSettingsInput(r.id, b); // OMNI_TAB_SLEEP_V1\n'
         '    case omniF3SetConsole: if (!dir) return false; omniSecBlockSet(!omniSecBlockOn()); return true;   // OMNI_SEC_LOCALHOST_V1\n'),
        ('    omniDlpTick(now);   // OMNI_DL_PROGRESS_V1: Downloads progress (polls only while jobs run / after a hand-over)\n',
         '    omniDlpTick(now);   // OMNI_DL_PROGRESS_V1: Downloads progress (polls only while jobs run / after a hand-over)\n'
         '    omniTspTick(now);   // OMNI_TAB_SLEEP_V1: idle background tabs: one check a minute, at most 2 per check\n'),
    ],
    'OmniTabMemory.h': [
        ('    if (!current && omniTmIsUnloaded(t) && value.empty()) value = "Unloaded";\n',
         '    if (!current && omniTmIsUnloaded(t) && value.empty()) value = omniTspAsleep(t) ? OmniTabSleep::kAsleepValue : "Unloaded"; // OMNI_TAB_SLEEP_V1\n'),
    ],
    'OmniTabMemoryViewShell.h': [
        ('        r.value = OTMV::rowValue(st[i]);\n',
         '        r.value = OTMV::rowValue(st[i]);\n'
         '        if (!st[i].loaded && st[i].block != OTMV::kCurrent && omniTspAsleep(t)) r.value = OmniTabSleep::kAsleepValue; // OMNI_TAB_SLEEP_V1\n'),
    ],
    'OmniTabsPage.h': [
        ('    omniTmvForget(&tab); // OMNI_TAB_MEMORY_VIEW_V1: its "Keep loaded" mark\n',
         '    omniTmvForget(&tab); // OMNI_TAB_MEMORY_VIEW_V1: its "Keep loaded" mark\n'
         '    omniTspForget(&tab); // OMNI_TAB_SLEEP_V1: its idle / asleep state\n'),
    ],
}
NEEDS = (('OmniTabMemory.h', 'OMNI_TAB_MEMORY_VIEW_V1', 'apply_tab_memory_view.py'),
         ('OmniTabMemoryViewShell.h', 'OMNI_TAB_MEMORY_VIEW_V1', 'apply_tab_memory_view.py'),
         ('OmniFeatures3.h', 'OMNI_BG_AUDIO_V1', 'apply_bg_audio.py'),
         ('OmniFeatures3.h', 'OMNI_DL_PROGRESS_V1', 'apply_dl_progress.py'),
         ('OmniTabsPage.h', 'OMNI_TAB_MEMORY_VIEW_V1', 'apply_tab_memory_view.py'))


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


def ids_free():
    """Before the first apply: no engine file and no other apply_*.py may use our row ids / names."""
    if any(MARK in (root / n).read_bytes().decode('utf-8') for n in EDITS):
        return
    me = Path(__file__).resolve()
    places = [p for d in (root, root.parent / 'media') if d.is_dir() for p in d.iterdir()
              if p.suffix in ('.h', '.cpp', '.inc') and p.name not in OURS]
    places += [p for p in HERE.glob('apply_*.py') if p.resolve() != me and p.name != 'apply_controls_help.py'
        and MARK not in p.read_text(encoding='utf-8', errors='replace')]   # OMNI_SIBLING_SKIP: guide / dependent patches
    for p in places:
        s = p.read_bytes().decode('utf-8', 'replace')
        if p.suffix == '.py':   # sibling script: names in its code only; row ids count in the engine tree only
            s = code_only(s)
        else:
            s = cpp_code(s)
        for pat in (TAKEN[2:] if p.suffix == '.py' else TAKEN[:2] if p.name in GUIDE else TAKEN):
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
    msgs = [write_new('OmniTabSleep.h', PURE.read_bytes().decode('utf-8'), 'OmniTabMemoryView.h'),
            write_new('OmniTabSleepShell.h', SHELL.read_bytes().decode('utf-8'), 'OmniTabMemory.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
