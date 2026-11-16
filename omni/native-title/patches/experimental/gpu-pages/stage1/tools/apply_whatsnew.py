#!/usr/bin/env python3
"""OMNI_WHATSNEW_V1 (2026-11-16): a one-time "What's new" page after Omni updates, and Options > Settings > What's new.

What the user sees
  - After an update (below), once, 4 s after start on a quiet screen (no panel, menu, modal, keyboard, settings, full
    screen or overlay): a new tab opens omni://pages/whatsnew/index.html?after=1, "What's new in Omni": cards grouped
    Tabs, Video, Reading, Privacy, Accessibility, Controller, Keyboard, Browsing, each with its button (PlayStation or
    Xbox names, as set; the wording of the Controls guide) or where to find it, and a "Try it" button where Omni has a
    native action for it (Controls guide, Options menu, Browser settings, Site settings, Tabs, History, Downloads,
    Reading list, Bookmarks, Screenshots). D-pad moves between cards (up / down by row, left / right within a row),
    Cross runs the card's Try it, L1 / R1 jump between groups, Circle is Omni's Back (closes nothing else).
    No quiet moment within 2 minutes: the notice "Omni was updated: Options > Settings > What's new" instead.
    Tab limit reached: the same notice.
  - Options > Settings (the group that holds Controls) has a row "What's new" (value "Omni 0.5.3"); Cross opens the
    page in a new tab (or, at the tab limit, in the current tab: Back returns). Disabled when the built-in pages are off.
  - The page's language: whatsnew.info answers the OMNI_UI_LANG_V1 language in use (omniUlCode); the page translates
    its own headings for es / fr / de / pt. The feature texts come from CHANGELOG.md and stay English.

"Updated": the key = OMNI_UA_VERSION (OmniYoutubeTv.h, "0.5.3"; -DOMNI_UA_VERSION overrides; "dev" without it) + "+" +
  the "id" of /app0/pages/whatsnew/whatsnew.json (a content hash written by the repo's tools/gen_whatsnew.py from the
  CHANGELOG's "Unreleased" section), compared with /data/omni/whatsnew-seen.txt. So a release bump and a dev build with
  new changelog entries both count. A fresh install (no saved key and none of session.txt, history.txt, bookmarks.txt,
  browser-settings.txt, controls-hint-shown.flag) only records the key: new users get the welcome page, not this.
  The key is written (omniIoQueue) when the page opens or the notice shows. Never in self-test modes.
Never phones home: the page reads its own bundled whatsnew.json; the bridge answers whatsnew.info (version, previous
  version, language, the action names) and whatsnew.try (one name from the fixed list; anything else INVALID_VALUE),
  only for a whatsnew/ page of omni://pages. The action runs on the next tick (menus closed first).

Files
  new  OmniWhatsNew.h         pure (from tools/OmniWhatsNew.h): key, decision, data id, actions, info JSON
                              (tests: tools/test_whatsnew.cpp)
  new  OmniWhatsNewShell.h    the version check (tick), the bridge, the Options row, the actions
  OmniBrowser.cpp   after the OmniStartCustom.h include line: the pure include; before the OmniPages.h include line: the
                    bridge declaration; after the OmniBfListShell.h include line: the shell include (after OmniPages.h)
  OmniPages.h       after the "start." request line: the "whatsnew." line
  OmniFeatures3.h   after the omniTipTick declaration: the tick declaration; after the omniTipTick call: the tick
  OmniQuickMenu.h   after the omniBflQuickAction declaration: declarations; after the Controls add() line: the row;
                    after the Settings group case: its case; after the omniChQuickInput line: the input
Ids / names: Options row 8611 (Settings group; checked unused in the tree), alias OWHN, names omniWhn*, OmniWhatsNew.
Each anchor once (whole lines), CRLF / LF kept per file, idempotent (MARK per file). Apply after apply_tips.py,
apply_controls_help.py, apply_bf_list.py, apply_start_custom.py, apply_reading_list.py, apply_screenshot_gallery.py.
usage: apply_whatsnew.py <engine tree>
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_WHATSNEW_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_whatsnew.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('8611',)
NAMES = ('OWHN', 'omniWhn', 'OmniWhatsNew', 'OMNI_WHATSNEW', 'OMNI_WHN_')

SHELL = r'''// OMNI_WHATSNEW_V1: the "What's new" page (shell side): the one-time check after an update, the page bridge
// (whatsnew.info / whatsnew.try), Options > Settings > What's new. Included from OmniBrowser.cpp after OmniPages.h. The
// pure part is OmniWhatsNew.h; the reasons are in tools/apply_whatsnew.py. Nothing here touches the network.
#pragma once

namespace OWHN = OmniWhatsNew;

#ifdef OMNI_UA_VERSION
#define OMNI_WHN_VERSION OMNI_UA_VERSION
#else
#define OMNI_WHN_VERSION "dev"
#endif

static bool omniWhnDecided = false, omniWhnPending = false;
static uint32_t omniWhnStart = 0;
static std::string omniWhnKey, omniWhnPrev;   // this build's key; the key saved by the run before (read once)
static int omniWhnQueued = OWHN::aNone;       // a page's "Try it", run on the next tick

static std::string omniWhnRead(const std::string& path, size_t cap)
{
    std::string s;
    if (FILE* f = fopen(path.c_str(), "rb")) {
        char buf[1024];
        size_t n;
        while (s.size() < cap && (n = fread(buf, 1, std::min(sizeof buf, cap - s.size()), f)) > 0) s.append(buf, n);
        fclose(f);
    }
    return s;
}
static const std::string& omniWhnCurrentKey()
{
    if (omniWhnKey.empty()) {
        const std::string id = omniPagesEnabled() ? OWHN::dataId(omniWhnRead(omniPagesRoot + OWHN::kDataRel, OWHN::kHeadMax)) : std::string();
        omniWhnKey = OWHN::key(OMNI_WHN_VERSION, id);
    }
    return omniWhnKey;
}
static void omniWhnRecord() { omniIoQueue(omniData(OWHN::kSeenName), omniWhnCurrentKey() + "\n", false); }
static std::string omniWhnLang()
{
#if __has_include("OmniUiLangShell.h")
    if (!omniUlLoaded) omniUlLoad();
    return omniUlCode;
#else
    return "en";
#endif
}
static bool omniWhnHadData()
{
    const char* names[] = { "session.txt", "history.txt", "bookmarks.txt", "browser-settings.txt" };
    for (const char* n : names) if (!access(omniData(n).c_str(), F_OK)) return true;
    return !access("/data/omni/controls-hint-shown.flag", F_OK);
}
static bool omniWhnQuiet()
{
    return omniFxStack.empty() && !omniModalVisible() && !pageFullscreen && !settingsOpen && !editing && !omniOverlayOpen()
        && !omniHistoryOpenFlag && !omniMenuOpenFlag;
}
// manual: from the Options row (at the tab limit the current tab is used: Back returns).
static bool omniWhnOpenPage(bool afterUpdate, bool manual)
{
    if (!omniPagesEnabled()) return false;
    Tab* t = newTab();
    if (!t && manual) t = active();
    return t && omniPagesOpen(t, afterUpdate ? OWHN::kPageAfterUpdate : OWHN::kPagePath);
}
static void omniWhnRun(int a)
{
    omniFxCloseAll();
    switch (a) {
    case OWHN::aControls: omniChOpen(); break;
    case OWHN::aOptions: omniFxQuickMenuShow(); break;
    case OWHN::aSettings: omniFxSettingsShow(); break;
    case OWHN::aSiteSettings: omniFxSiteSettingsShow(); break;
    case OWHN::aTabs: omniFxTabsShow(); break;
    case OWHN::aHistory: omniHistoryShow(); break;
    case OWHN::aDownloads: omniFxDownloadsShow(); break;
    case OWHN::aReadingList: omniRlQuickAction(OmniReadingList::kTileList); break;
    case OWHN::aBookmarks: omniFxBookmarksShow(0); break;
    case OWHN::aScreenshots: omniSsQuickAction(OmniShotGallery::kTile); break;
    default: break;
    }
}

static void omniWhnTick(uint32_t now)
{
    if (omniWhnQueued != OWHN::aNone) { const int a = std::exchange(omniWhnQueued, int(OWHN::aNone)); omniWhnRun(a); }
    if (omniWhnDecided && !omniWhnPending) return;
    if (!omniWhnDecided) {
        omniWhnDecided = true;
        omniWhnStart = now;
        if (omniTestMode()) return;
        omniWhnPrev = OWHN::seenFrom(omniWhnRead(omniData(OWHN::kSeenName), 512));
        const OWHN::Decision d = OWHN::decide(omniWhnPrev, omniWhnCurrentKey(), omniWhnHadData());
        if (d == OWHN::kRecord) omniWhnRecord();
        omniWhnPending = d == OWHN::kShow;
        fprintf(stderr, "OMNI_WHATSNEW_V1: key %s, seen %s: %s\n", omniWhnCurrentKey().c_str(), omniWhnPrev.empty() ? "-" : omniWhnPrev.c_str(),
            d == OWHN::kShow ? "show" : d == OWHN::kRecord ? "fresh install, recorded" : "nothing new");
        return;
    }
    if (uint32_t(now - omniWhnStart) < OWHN::kDelayMs) return;
    // OMNI_WHATSNEW_V1_R2: a harness run switches to test mode after the first tick (built-in pages are off there, so the
    // tab failed with "Unsupported protocol" and added a tab to the gate). Nothing opens and nothing is recorded: a real
    // launch still shows the page.
    if (omniTestMode()) { omniWhnPending = false; return; }
    if (!omniWhnQuiet() && uint32_t(now - omniWhnStart) < OWHN::kGiveUpMs) return;
    omniWhnPending = false;
    omniWhnRecord();
    if (!omniWhnQuiet() || !omniWhnOpenPage(true, false)) notice("Omni was updated: Options > Settings > What's new");
}

// The page bridge (OmniPages.h, request() methods "whatsnew.*"); only for omni://pages/whatsnew/ itself.
static std::string omniWhnBridge(WKPageRef, Tab& tab, const std::string& method, const std::string& arg)
{
    if (!tab.omniPagesTab || tab.url.rfind("omni://pages/whatsnew/", 0) != 0) return omniPagesErr("UNSUPPORTED");
    if (method == "whatsnew.info")
        return omniPagesOk(OWHN::infoJson(OMNI_WHN_VERSION, omniWhnPrev, omniWhnLang(), tab.url.find("after=1") != std::string::npos));
    if (method == "whatsnew.try") {
        const OWHN::Action a = OWHN::action(arg);
        if (a == OWHN::aNone) return omniPagesErr("INVALID_VALUE");
        omniWhnQueued = a;
        return omniPagesOk("null");
    }
    return omniPagesErr("UNSUPPORTED");
}

static void omniWhnQuickRow(OmniFxPanel& p)   // Options > Settings
{
    OmniFxRow r; r.id = OWHN::kQuickRowId; r.label = "What's new"; r.value = OWHN::rowValue(OMNI_WHN_VERSION);
    r.enabled = omniPagesEnabled();
    p.rows.push_back(r);
}
static bool omniWhnQuickInput(const OmniFxRow& r, int b)
{
    if (r.id != OWHN::kQuickRowId) return false;
    if (b != SDL_CONTROLLER_BUTTON_A || !r.enabled) return true;
    omniFxCloseAll();
    if (!omniWhnOpenPage(false, true)) notice("Couldn't open What's new");
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniStartCustom.h" // OMNI_START_CUSTOM_V1: Customise start page: order, sections, background (pure)\n',
         '#include "OmniStartCustom.h" // OMNI_START_CUSTOM_V1: Customise start page: order, sections, background (pure)\n'
         '#include "OmniWhatsNew.h" // OMNI_WHATSNEW_V1: What\'s new page: update check, actions (pure)\n'),
        ('#include "OmniPages.h" // s3 OMNI_PAGES_V1: omni://pages built-in pages\n',
         'static std::string omniWhnBridge(WKPageRef page, Tab& tab, const std::string& method, const std::string& arg); // OMNI_WHATSNEW_V1 (OmniWhatsNewShell.h)\n'
         '#include "OmniPages.h" // s3 OMNI_PAGES_V1: omni://pages built-in pages\n'),
        ('#include "OmniBfListShell.h" /* OMNI_BF_LIST_V1: Back history (hold Circle, Options > Browse) */\n',
         '#include "OmniBfListShell.h" /* OMNI_BF_LIST_V1: Back history (hold Circle, Options > Browse) */\n'
         '#include "OmniWhatsNewShell.h" /* OMNI_WHATSNEW_V1: What\'s new page (after OmniPages.h) */\n'),
    ],
    'OmniPages.h': [
        ('        if (method.rfind("start.", 0) == 0) return omniScuBridge(page, *tab, method, omniPagesField(a, "url")); // OMNI_START_CUSTOM_V1 (OmniStartCustomShell.h)\n',
         '        if (method.rfind("start.", 0) == 0) return omniScuBridge(page, *tab, method, omniPagesField(a, "url")); // OMNI_START_CUSTOM_V1 (OmniStartCustomShell.h)\n'
         '        if (method.rfind("whatsnew.", 0) == 0) return omniWhnBridge(page, *tab, method, omniPagesField(a, "url")); // OMNI_WHATSNEW_V1 (OmniWhatsNewShell.h)\n'),
    ],
    'OmniFeatures3.h': [
        ('static void omniTipTick(uint32_t now); // OMNI_TIPS_V1 (OmniTipsShell.h, included from OmniBrowser.cpp after the controller shortcuts)\n',
         'static void omniTipTick(uint32_t now); // OMNI_TIPS_V1 (OmniTipsShell.h, included from OmniBrowser.cpp after the controller shortcuts)\n'
         'static void omniWhnTick(uint32_t now); // OMNI_WHATSNEW_V1 (OmniWhatsNewShell.h, included from OmniBrowser.cpp after OmniPages.h)\n'),
        ('    omniTipTick(now);   /* OMNI_TIPS_V1: contexts for the one-time tips (every 250 ms at most), the card\'s 8 s */\n',
         '    omniTipTick(now);   /* OMNI_TIPS_V1: contexts for the one-time tips (every 250 ms at most), the card\'s 8 s */\n'
         '    omniWhnTick(now);   /* OMNI_WHATSNEW_V1: the one-time What\'s new page after an update; Try it actions */\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniBflQuickAction(int id); // OMNI_BF_LIST_V1\n',
         'static bool omniBflQuickAction(int id); // OMNI_BF_LIST_V1\n'
         'static void omniWhnQuickRow(OmniFxPanel& p); // OMNI_WHATSNEW_V1 (OmniWhatsNewShell.h): What\'s new\n'
         'static bool omniWhnQuickInput(const OmniFxRow& r, int b); // OMNI_WHATSNEW_V1\n'),
        ('    add(omniQmControls, "Controls", true);   // s2: R3 close tab, View settings\n',
         '    add(omniQmControls, "Controls", true);   // s2: R3 close tab, View settings\n'
         '    omniWhnQuickRow(p); // OMNI_WHATSNEW_V1: What\'s new (Settings group)\n'),
        ('    case omniQmSettings: case omniQmBrowserSettings: case omniQmSite: case omniQmControls: return 4;\n',
         '    case omniQmSettings: case omniQmBrowserSettings: case omniQmSite: case omniQmControls: return 4;\n'
         '    case OmniWhatsNew::kQuickRowId: return 4; // OMNI_WHATSNEW_V1: What\'s new (Settings)\n'),
        ('    if (omniChQuickInput(r, b)) return true; // OMNI_CONTROLS_HELP_V1 (before the >= 900 rows)\n',
         '    if (omniChQuickInput(r, b)) return true; // OMNI_CONTROLS_HELP_V1 (before the >= 900 rows)\n'
         '    if (omniWhnQuickInput(r, b)) return true; // OMNI_WHATSNEW_V1 (before the >= 900 rows)\n'),
    ],
}

NEEDS = {'OmniBrowser.cpp': ('OMNI_BF_LIST_V1', 'OMNI_START_CUSTOM_V1', 'OMNI_PAGES_V1'),
         'OmniFeatures3.h': ('OMNI_TIPS_V1',),
         'OmniPages.h': ('OMNI_START_CUSTOM_V1',),
         'OmniQuickMenu.h': ('OMNI_CONTROLS_HELP_V1', 'OMNI_READING_LIST_V1', 'OMNI_SCREENSHOT_GALLERY_V1', 'OMNI_BF_LIST_V1')}


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
    """Before a first apply: no other patch or tree file uses this patch's ids or names."""
    word = re.compile(r'\b(%s)\b' % '|'.join(IDS))
    name = re.compile('|'.join(NAMES))
    mine = {'OmniWhatsNew.h', 'OmniWhatsNewShell.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        t = code_only(f.read_text(encoding='utf-8', errors='replace'))
        m = name.search(t)   # numeric ids: engine tree only (a sibling's notes list other patches' ids)
        if m:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in mine or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        c = cpp_code(t)
        m = word.search(c) or (None if f.name in GUIDE else name.search(c))
        if m and MARK not in t:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))


def main():
    for fname, needs in NEEDS.items():
        s = (root / fname).read_bytes().decode('utf-8')
        for need in needs:
            if need not in s:
                sys.exit('%s: %s missing: apply its patch first' % (fname, need))
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        ids_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    pure = (HERE / 'OmniWhatsNew.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniWhatsNew.h: %s missing' % MARK)
    msgs = [write_new('OmniWhatsNew.h', pure, 'OmniQuickMenu.h'),
            write_new('OmniWhatsNewShell.h', SHELL, 'OmniFeatures3.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
