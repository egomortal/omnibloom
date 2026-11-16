#!/usr/bin/env python3
"""OMNI_LITE_MODE_V1 (2026-11-16): Browser settings > "Lite mode": On / Off (default Off). Backlog E23, title side only
(the video cap part needs the engine CHILD and is left out of v1).

What the user sees
  - Browser settings (Options > Browser settings) has a new row before "Block pages from reaching the console":
        "Lite mode"   value: On / Off (D-pad left / right or Cross toggles)
        detail On:  "3 tabs stay loaded, no tab pictures, smaller text cache, no spare engine"
    One notice on each change: "Lite mode on: 3 tabs stay loaded (others reload when shown)" /
    "Lite mode off: tabs and caches back to your settings".
  - On:
      * At most 3 tabs stay loaded (the shown one included). Once a second (at most 2 per check) the extra ones are
        unloaded through tab sleep's path (OMNI_TAB_SLEEP_V1 omniTspSleep: omniTmvForce + omniTmUnloadOne: session history
        kept, about:blank, reloads when shown), least recently shown first (OmniTmTab::shownAt; a tab never shown counts
        as oldest). Never: the shown tab, pinned tabs (omniPtPinned), audible tabs (sound badge or playing audio:
        omniTaBadge / omniTaPlaying), and, as tab sleep, private tabs (unloading drops them for good), "Keep loaded" tabs
        (omniTmvKept) and whatever omniTmCanUnload refuses (loading, crashed, media section, not a web page, playing
        video). Nothing is unloaded while a download runs (omniTspDownloadsBusy: downloads are not tied to a tab).
        Fewer than 3 is never forced: when the rest may not be unloaded, more stay loaded.
      * Tab thumbnails (OMNI_TAB_THUMBS_V1, only when that patch is in the tree): every stored picture is dropped at once
        and none is taken while On (the rows / switcher show the site letter, as for a tab never left).
      * Rendered-text cache (OMNI_TEXT_CACHE_CAP_V1): its byte budget is half of the normal one (OTCC::budgetFor), at
        least 8 MiB, never above normal: 4K 24 MiB (was 48), 1080p / 720p 8 MiB (was 16). Applied at once
        (omniTcCache.setBudget evicts) and on every miss (omniTextSurface re-derives the budget).
      * Reserve spare engine: the launcher (omni-process-launcher-v2.inc, OMNI_SPARE_DEFER_V1 / OMNI_SPARE_LAZY_V1, not
        changed) refills a spare engine after a launch only while /data/omni/spare-reserve.flag or spare-defer-off.flag
        exists (each launch checks again). Lite mode renames a present flag to "<flag>.lite"; Off renames it back. A flag
        made again while On is set aside again; at Off a live flag wins over its stash (the stash is deleted). The two
        early spares at app start (omni_launcher_prespawn) are not spare reserve: they are used by the first launches,
        and prespawn-disabled.flag is left alone.
  - Off: each part is back to its previous value: the tab cap is gone (unloaded tabs reload when shown, as always),
    thumbnails are taken again, the text budget is normal again (at once), the stashed flags are back.
  - Restart: lite-mode.txt keeps the switch; the first pass sweeps the spare flags for the saved state (a stash left by
    an interrupted run is put back when Off).
API for other patches (declared in OmniFeatures3Decl.h, so callable from OmniBrowser.cpp after it and from every
  shell; e.g. the crash panel's "Try Lite mode", apply_crash_choices.py):  bool omniLiteOn();  void omniLiteSetOn(bool on);
  omniLiteSetOn does exactly what the row does (save, notice, apply); same value: nothing.
Storage: /data/omni/lite-mode.txt ("on\t1\n", omniIoQueue); the "<flag>.lite" renames above.
Log: "OMNI LITE: on/off (spare flags set aside N / put back N)"; "OMNI LITE: unloaded N tab(s), M loaded"; the tab memory
  line "OMNI TABMEM: unloaded background tab (lite mode)" from omniTmUnloadOne.
Cost: Off, one branch per pass. On, one loop over the tabs a second.

Pure part: engine/entry/OmniLiteMode.h (copied from tools/OmniLiteMode.h): settings, pick, text budget, flag steps, texts.
  Tests: tools/test_lite_mode.cpp (g++ -std=c++20 -Wall -Wextra -Werror -I. test_lite_mode.cpp -o t && ./t).
Shell part: engine/entry/OmniLiteModeShell.h (written by this script), alias OLITE, names omniLite*.
Ids: Browser settings row 364 (omniF3SettingsInput's switch, ids 300..899). Checked free in the tree (code, not comments)
  and in every sibling apply_*.py (code only: names, and row-id assignments such as "= 364" / "case 364"; siblings that
  contain OMNI_LITE_MODE_V1 call this patch and are skipped, as is apply_controls_help.py).

Anchors (exactly once each; whole lines; MARK makes each file idempotent; CRLF / LF kept; inserted lines use /* */):
  OmniBrowser.cpp       the OmniTextCacheCap.h include line (pure include after); omniTextSurface's
                        "if (const size_t budget = OTCC::budgetFor(...)" line (budget passed through omniLiteTextBudget).
  OmniFeatures3Decl.h   the omniTspAsleep declaration line (our declarations after).
  OmniFeatures3.h       the OmniControlsHelpShell.h include line (ours before); omniF3SettingsRows' add(omniF3SetConsole
                        ...) line (our row before); omniF3SettingsInput's "case omniF3SetMemory:" line (our case before);
                        omniF3Tick's omniDsvTick line (our tick after).
  OmniTabThumbsShell.h  only when present: omniTthCapture's "if (!t || index >= tabs.size() ..." line (Lite return
                        before); the omniTthForget line (OMNI_LITE_THUMBS + omniTthLiteDrop after).
Apply AFTER apply_tab_sleep.py, apply_text_cache_cap.py, apply_pinned_tabs.py, apply_tab_audio.py,
apply_tab_memory_view.py, apply_data_saver.py, apply_controls_help.py and (when the chain has it) apply_tab_thumbs.py; a
re-run after apply_tab_thumbs.py patches the thumbnails file alone.
usage: apply_lite_mode.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_LITE_MODE_V1'
if len(sys.argv) != 2:
    sys.exit('usage: apply_lite_mode.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
HERE = Path(__file__).resolve().parent
PURE = HERE / 'OmniLiteMode.h'
OURS = ('OmniLiteMode.h', 'OmniLiteModeShell.h')
ROW_ID = '364'
NAMES = (r'\bOLITE\b', r'\bomniLite[A-Z]', r'\bOmniLiteMode\b', r'\bOMNI_LITE_THUMBS\b')
SKIP_SIBLINGS = ('apply_controls_help.py',)

SHELL = r'''// OMNI_LITE_MODE_V1: Browser settings > "Lite mode" (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's
// anonymous namespace) before OmniControlsHelpShell.h, so after the tab memory, tab memory view, pinned tabs, tab audio,
// tab sleep and (when present) tab thumbnails shells. The pure part is OmniLiteMode.h; the reasons are in
// tools/apply_lite_mode.py. Main thread only. Cost: Off, one branch per pass; On, one loop over the tabs a second.
#pragma once

namespace OLITE = OmniLiteMode;

static OLITE::Settings omniLiteSet;
static bool omniLiteLoaded = false, omniLiteSwept = false;
static uint32_t omniLiteCheckAt = 0;

static void omniLiteLoad()
{
    if (omniLiteLoaded) return;
    omniLiteLoaded = true;
    std::string text;
    if (FILE* f = fopen(omniData(OLITE::kFileName).c_str(), "r")) {
        char b[128];
        size_t n = 0;
        while ((n = fread(b, 1, sizeof(b), f)) > 0 && text.size() < 1024) text.append(b, n);
        fclose(f);
    }
    omniLiteSet = OLITE::parse(text);   // no file: Off
}
// Declared in OmniFeatures3Decl.h: other patches may ask / set it.
static bool omniLiteOn()
{
    omniLiteLoad();
    return omniLiteSet.on;
}
// omniTextSurface (declared in OmniFeatures3Decl.h): the rendered-text cache's byte budget, lowered while On.
static size_t omniLiteTextBudget(size_t normal) { return OLITE::textBudget(normal, omniLiteOn()); }

static bool omniLiteExists(const std::string& path)
{
    if (FILE* f = fopen(path.c_str(), "r")) { fclose(f); return true; }
    return false;
}
// The launcher's reserve-spare flags: set aside while On, put back at Off (OLITE::flagStep). Returns how many moved.
static int omniLiteSpareFlags(bool on)
{
    int moved = 0;
    for (int i = 0; i < OLITE::kSpareFlagCount; ++i) {
        const std::string live = omniData(OLITE::spareFlags()[i]);
        const std::string stash = live + OLITE::kStashSuffix;
        const OLITE::FlagStep step = OLITE::flagStep(on, omniLiteExists(live), omniLiteExists(stash));
        bool ok = true;
        if (step == OLITE::kStash) ok = rename(live.c_str(), stash.c_str()) == 0;
        else if (step == OLITE::kRestore) ok = rename(stash.c_str(), live.c_str()) == 0;
        else if (step == OLITE::kDropStash) ok = remove(stash.c_str()) == 0;
        else continue;
        if (ok) ++moved;
        else { fprintf(stderr, "OMNI LITE: could not move %s (errno %d)\n", OLITE::spareFlags()[i], errno); fflush(stderr); }
    }
    return moved;
}
static void omniLiteSetOn(bool on)
{
    omniLiteLoad();
    if (omniLiteSet.on == on) return;
    omniLiteSet.on = on;
    omniIoQueue(omniData(OLITE::kFileName), OLITE::serialize(omniLiteSet), false);
    const int moved = omniLiteSpareFlags(on);
    omniLiteSwept = true;
    omniTcCache.setBudget(omniLiteTextBudget(OTCC::budgetFor(renderWidth, renderHeight)), omniTcDrop);   // at once
#ifdef OMNI_LITE_THUMBS
    if (on) omniTthLiteDrop();   // OMNI_TAB_THUMBS_V1 is in the tree: its pictures go now; none are taken while On
#endif
    omniLiteCheckAt = 0;         // the first check on the next pass
    notice(OLITE::notice(on));
    fprintf(stderr, "OMNI LITE: %s (spare flags %s %d)\n", on ? "on" : "off", on ? "set aside" : "put back", moved);
    fflush(stderr);
    omniTmLog(on ? "lite mode on" : "lite mode off");
    omniFxRefresh();
}

// omniF3Tick, every pass: the spare flags once per run for the saved state; while On, one check a second.
static void omniLiteTick(uint32_t now)
{
    if (omniTestMode()) return;
    omniLiteLoad();
    if (!omniLiteSwept) {
        omniLiteSwept = true;
        if (const int moved = omniLiteSpareFlags(omniLiteSet.on)) {
            fprintf(stderr, "OMNI LITE: start, %s: spare flags %s %d\n", omniLiteSet.on ? "on" : "off", omniLiteSet.on ? "set aside" : "put back", moved);
            fflush(stderr);
        }
    }
    if (!omniLiteSet.on || !OLITE::checkDue(now, omniLiteCheckAt)) return;
    omniLiteCheckAt = now ? now : 1;
    if (omniTspDownloadsBusy()) return;
    const Tab* shown = active();
    std::vector<OLITE::Cand> cs;
    cs.reserve(tabs.size());
    for (auto& t : tabs) {
        OLITE::Cand c;
        c.loaded = !omniTmIsUnloaded(*t);
        c.current = t.get() == shown;
        c.pinned = omniPtPinned(*t);
        c.audible = t->omniTaBadge != 0 || omniTaPlaying(*t);
        c.keep = t->omniPrivate || omniTmvKept(*t);
        c.free = c.loaded && !c.current && omniTmCanUnload(*t);
        auto f = omniTmTabs.find(t.get());
        c.shownAt = f != omniTmTabs.end() ? f->second.shownAt : 0;
        cs.push_back(c);
    }
    std::vector<Tab*> doomed;
    for (int i : OLITE::pick(cs, now)) doomed.push_back(tabs[size_t(i)].get());
    int n = 0;
    for (Tab* t : doomed) {   // tab sleep's path: exactly this tab, if omniTmCanUnload still allows it
        omniTmvForce = t;
        if (omniTmUnloadOne(OLITE::kUnloadWhy)) ++n;
        omniTmvForce = nullptr;
    }
    if (!n) return;
    omniShellDirty = true;
    fprintf(stderr, "OMNI LITE: unloaded %d tab(s), %d loaded\n", n, omniTmLoadedCount());
    fflush(stderr);
}

// --- Browser settings row (omniF3SettingsRows, before "Block pages from reaching the console") ----------------------
static void omniLiteSettingsRows(OmniFxPanel& p)
{
    const bool on = omniLiteOn();
    OmniFxRow r; r.id = OLITE::kRow; r.label = OLITE::label(); r.value = OLITE::value(on); r.stepper = true; r.detail = OLITE::detail(on);
    p.rows.push_back(r);
}
static bool omniLiteSettingsInput(int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT, a = b == SDL_CONTROLLER_BUTTON_A;
    if (!left && !right && !a) return false;
    omniLiteSetOn(!omniLiteOn());
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniTextCacheCap.h" // OMNI_TEXT_CACHE_CAP_V1: byte budget + LRU for rendered UI text (pure)\n',
         '#include "OmniTextCacheCap.h" // OMNI_TEXT_CACHE_CAP_V1: byte budget + LRU for rendered UI text (pure)\n'
         '#include "OmniLiteMode.h" /* OMNI_LITE_MODE_V1: Lite mode: tab pick, text budget, spare flags, texts (pure) */\n'),
        ('    if (const size_t budget = OTCC::budgetFor(renderWidth, renderHeight); budget != omniTcCache.budget())\n',
         '    /* OMNI_LITE_MODE_V1: Lite mode lowers the budget (omniLiteTextBudget: half, at least 8 MiB; normal when Off) */\n'
         '    if (const size_t budget = omniLiteTextBudget(OTCC::budgetFor(renderWidth, renderHeight)); budget != omniTcCache.budget())\n'),
    ],
    'OmniFeatures3Decl.h': [
        ('static bool omniTspAsleep(const Tab& t);                   // Tabs / Memory panel: "Asleep" instead of "Unloaded"\n',
         'static bool omniTspAsleep(const Tab& t);                   // Tabs / Memory panel: "Asleep" instead of "Unloaded"\n'
         '/* OMNI_LITE_MODE_V1 (OmniLiteModeShell.h): Browser settings > Lite mode. Other patches may call the first two. */\n'
         'static bool omniLiteOn();\n'
         'static void omniLiteSetOn(bool on);                        /* saves, shows one notice, applies (same value: nothing) */\n'
         'static size_t omniLiteTextBudget(size_t normal);           /* omniTextSurface: the text cache budget */\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniControlsHelpShell.h" // OMNI_CONTROLS_HELP_V1 (after the other shells: it recognises their panels)\n',
         '#include "OmniLiteModeShell.h" /* OMNI_LITE_MODE_V1 (after tab sleep, tab audio, pinned tabs, tab thumbnails) */\n'
         '#include "OmniControlsHelpShell.h" // OMNI_CONTROLS_HELP_V1 (after the other shells: it recognises their panels)\n'),
        ('    add(omniF3SetConsole, "Block pages from reaching the console", omniSecBlockOn() ? "On (recommended)" : "Off", true);   // OMNI_SEC_LOCALHOST_V1\n',
         '    omniLiteSettingsRows(p); /* OMNI_LITE_MODE_V1: Lite mode (Off / On) */\n'
         '    add(omniF3SetConsole, "Block pages from reaching the console", omniSecBlockOn() ? "On (recommended)" : "Off", true);   // OMNI_SEC_LOCALHOST_V1\n'),
        ('    case omniF3SetMemory:\n',
         '    case OmniLiteMode::kRow: return omniLiteSettingsInput(b); /* OMNI_LITE_MODE_V1 */\n'
         '    case omniF3SetMemory:\n'),
        ('    omniDsvTick();      // OMNI_DATA_SAVER_V1: applies the saved setting once the content controllers exist\n',
         '    omniDsvTick();      // OMNI_DATA_SAVER_V1: applies the saved setting once the content controllers exist\n'
         '    omniLiteTick(now);  /* OMNI_LITE_MODE_V1: spare flags once; while On, at most 3 loaded tabs (one check a second) */\n'),
    ],
}
THUMBS = ('OmniTabThumbsShell.h', [
    ('    if (!t || index >= tabs.size() || tabs[index].get() == t || painted != t) return;\n',
     '    if (omniLiteOn()) return; /* OMNI_LITE_MODE_V1: no tab thumbnails while Lite mode is on */\n'
     '    if (!t || index >= tabs.size() || tabs[index].get() == t || painted != t) return;\n'),
    ('static void omniTthForget(const void* tab) { omniTth.forget(tab); }\n',
     'static void omniTthForget(const void* tab) { omniTth.forget(tab); }\n'
     '/* OMNI_LITE_MODE_V1: Lite mode on drops every thumbnail (OmniLiteModeShell.h, included later, calls it) */\n'
     '#define OMNI_LITE_THUMBS 1\n'
     'static void omniTthLiteDrop() { omniTth.prune([](const void*) { return false; }); }\n'),
])
if (root / THUMBS[0]).exists():   # tab thumbnails are optional: patched only when apply_tab_thumbs.py ran
    EDITS[THUMBS[0]] = THUMBS[1]
NEEDS = (('OmniFeatures3.h', 'OMNI_TAB_SLEEP_V1', 'apply_tab_sleep.py'),
         ('OmniBrowser.cpp', 'OMNI_TEXT_CACHE_CAP_V1', 'apply_text_cache_cap.py'),
         ('OmniFeatures3.h', 'OMNI_PINNED_TABS_V1', 'apply_pinned_tabs.py'),
         ('OmniFeatures3.h', 'OMNI_TAB_AUDIO_V1', 'apply_tab_audio.py'),
         ('OmniFeatures3.h', 'OMNI_DATA_SAVER_V1', 'apply_data_saver.py'),
         ('OmniFeatures3.h', 'OMNI_CONTROLS_HELP_V1', 'apply_controls_help.py'),
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


# A sibling script's code (strings included: they carry the C++ it writes) that assigns our row id to something:
# "kRowX = 364", "RowId = 364", "case 364", "id = 364" (not a bare number in a list of other patches' ranges).
ROW_ASSIGN = re.compile(r'(?:=\s*|\bcase\s+)%s(?![\w.])' % ROW_ID)


def ids_free():
    """Before the first apply: no engine file and no other apply_*.py may use our row id / names. Siblings that contain
    our MARK use this patch's API on purpose (they apply after it) and are skipped, as is the Controls guide's script."""
    if any(MARK in (root / n).read_bytes().decode('utf-8') for n in EDITS if n != THUMBS[0]):
        return
    me = Path(__file__).resolve()
    word = re.compile(r'(?<![\w.])%s(?![\w.])' % ROW_ID)
    names = re.compile('|'.join(NAMES))
    for f in sorted(HERE.glob('apply_*.py')):
        if f.resolve() == me or f.name in SKIP_SIBLINGS:
            continue
        raw = f.read_text(encoding='utf-8', errors='replace')
        if MARK in raw:
            continue
        t = code_only(raw)
        m = names.search(t) or ROW_ASSIGN.search(t)
        if m:
            sys.exit('%s already uses %r (line %d): pick other ids / names' % (f.name, m.group(0), t.count('\n', 0, m.start()) + 1))
    for d in (root, root.parent / 'media'):
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.name in OURS or f.suffix not in ('.h', '.cpp', '.inc'):
                continue
            raw = f.read_bytes().decode('utf-8', errors='replace')
            if MARK in raw:   # a later patch's file that calls our API
                continue
            c = cpp_code(raw)
            m = word.search(c) or (None if f.name in GUIDE else names.search(c))
            if m:
                sys.exit('%s already uses %r (line %d): pick other ids / names' % (f.name, m.group(0), c.count('\n', 0, m.start()) + 1))


def main():
    if not PURE.exists():
        sys.exit('%s missing (it ships next to this script)' % PURE)
    pure = PURE.read_bytes().decode('utf-8')
    if MARK not in pure:
        sys.exit('OmniLiteMode.h: %s missing' % MARK)
    for f, need, tool in NEEDS:
        if need not in (root / f).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (f, need, tool))
    if THUMBS[0] in EDITS and 'OMNI_TAB_THUMBS_V1' not in (root / 'OmniFeatures3.h').read_bytes().decode('utf-8'):
        sys.exit('OmniFeatures3.h: OMNI_TAB_THUMBS_V1 missing although %s exists' % THUMBS[0])
    for name in OURS:   # never overwrite someone else's file
        h = root / name
        if h.exists() and MARK not in h.read_bytes().decode('utf-8', 'replace'):
            sys.exit('%s exists without %s' % (name, MARK))
    ids_free()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniLiteMode.h', pure, 'OmniTabSleep.h'),
            write_new('OmniLiteModeShell.h', SHELL, 'OmniTabSleepShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
