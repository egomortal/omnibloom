#!/usr/bin/env python3
"""OMNI_NOTICE_HISTORY_V1 (2026-11-16): "Recent notices" - the last 30 notices of this run, for a TV where a 3.5 s
toast is easy to miss.

What the user sees
  - Options (top level) has a row "Notices (n)" while at least one notice is kept, after "Downloads (n active)".
    Its value is "<dot> 2 new" while some arrived since the list was last opened (nothing when all are read).
  - Cross opens "Recent notices" (newest first): each row is the notice's text, its value "2 min ago" ("just now",
    "40 s ago", "1 h 5 min ago"; "x3  2 min ago" when the same text came 3 times within 5 s of each other), and, where
    Omni has a cheap hook for it, a dim detail saying what Cross does:
        "Sent to Downloads: <name>", "Downloaded: <title>"   -> Open Downloads        (omniMediaDownloadsOpen(false),
                                                                the Downloads app; there is no hook that opens its
                                                                Library section directly, so the app opens as L1+R1)
        "Downloaded <file> to ...", "Download failed: <file>"   -> Open file downloads   (omniFxDownloadsShow)
        "Pop-up blocked..." (all three texts + OmniPermissions')-> Open Blocked pop-ups  (omniPnShow: the SHOWN tab's
                                                                list, which may be empty if the pop-up was elsewhere)
        "Screenshot saved (...)"                              -> Open Screenshots      (omniSsOpen)
    Every other notice is text only (Cross does nothing). Square clears the list, Circle goes back.
  - The list is memory only (static data in the shell): it is gone when Omni closes. Nothing is written anywhere.

How notice() is hooked (once, no call site edited)
  OmniBrowser.cpp's one-line notice() gets "omniNhNote(text);" at its end (forward declaration on the line before).
  Every notice(...) call (about 330 lines in the T tree) goes through it. The toast's other source - statuses set WITHOUT
  notice() ("status = ...; statusUntil = ..." in OmniPopupNoticeShell.h's "Pop-up blocked" hint, OmniTabMemory.h's
  refusals, "Resolution saved", the content blocker's "Ad blocking unavailable") - is caught by omniNhTick (from
  omniF3Tick, every pass): ONHI::StatusWatch compares (status, statusUntil) with the last pass; a new text, or the
  same text with a later deadline, is a new notice. notice() syncs the watch so its own texts are not counted twice.
  Two direct statuses replaced within one pass are seen as the last one only (the first was never drawn either).
  Page error messages (Tab::message, shown by the toast in red) are NOT kept: they have their own error panel.

What is not kept (ONHI::noisy, on the English text)
  - "Ready", empty, and progress texts ending in "..." or an ellipsis ("Saving screenshot...", "Reloading...") - a
    result notice always follows.
  - per-key-press steps and progress, by prefix: "Zoom " (zoom steps, at-the-limit, reset), "Volume: " (tab volume),
    "Speed: " (playback speed), "Magnifier " (magnifier steps), "Downloading " (file download progress every second),
    "Copying from the USB drive: " / "Copying to the USB drive: " (percent), "Press " (the first-launch controls
    hint, which also extends its own deadline). A side effect: "Zoom works on web pages" and "Magnifier needs Omni's
    GPU display output..." are not kept either.
  - Identical texts within 5 s of the entry's last raise: one entry, counted ("x2"), moved to the top.

Private tabs (the safer of the two rules): NOTHING is recorded while any private tab exists (not just while one is
shown): a background private tab's download / pop-up / dialog notice can name a private file or site even while a
normal tab is shown. Notices kept before the first private tab opened stay and are shown everywhere (they never came
from a private tab). Test modes record nothing (omniTestMode), so the quick menu's rows stay as the tests expect.

Translation: the English text is stored. The list is an OmniFx panel, so when OMNI_UI_LANG_V1 is applied its panel
draw (omniTr on title, subtitle, row label / value / detail) translates whatever its tables know (prefix entries
such as "Sent to Downloads: *" included); nothing here depends on OmniUiLang.h. "2 min ago" / "Notices (3)" /
"<dot> 2 new" have no table entries and stay English.

Files
  OmniNoticeHistory.h       (new, pure; also kept in tools/ for the host test) ring buffer (30), dedupe (5 s), noise
                            prefixes, actions by prefix, "2 min ago", StatusWatch. tools/test_notice_history.cpp.
  OmniNoticeHistoryShell.h  (new) the store, omniNhNote / omniNhTick, the quick row, the panel.
Anchors (each once; every file keeps its own line endings; re-run prints "already")
  OmniBrowser.cpp   the OmniSiteList.h include line (apply_site_list.py's): + OmniNoticeHistory.h include
                    the one-line notice() definition: + forward declaration before it, + omniNhNote(text) in it.
                    (apply_gpu_watchdog.py, not in the rc6 recipe, anchors that exact line: run it BEFORE this one.)
  OmniQuickMenu.h   the omniDlpQuickRow declaration / call / input line (apply_dl_progress.py's): + ours after each
  OmniFeatures3.h   the OmniWebAppsShell.h include line (apply_web_apps.py's): + OmniNoticeHistoryShell.h
                    the omniScTick line of omniF3Tick (apply_site_clear.py's r2): + omniNhTick(now)
Ids: quick row 8476, panel kind 7476; names ONHI / omniNh / OmniNoticeHistory (checked unused before a first apply).
Apply AFTER apply_site_list.py, apply_dl_progress.py, apply_popup_notice.py, apply_screenshot_gallery.py,
apply_web_apps.py, apply_site_clear.py.
usage: apply_notice_history.py <engine tree>
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_NOTICE_HISTORY_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_notice_history.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('7476', '8476')
NAMES = ('ONHI', 'omniNh', 'OmniNoticeHistory', 'OMNI_NOTICE_HISTORY')

SHELL = r'''// OMNI_NOTICE_HISTORY_V1: "Recent notices" (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's
// anonymous namespace, after OmniWebAppsShell.h). The pure part is OmniNoticeHistory.h; the reasons are in
// tools/apply_notice_history.py. Main thread only. Memory only: nothing is written anywhere.
#pragma once

namespace ONHI = OmniNoticeHistory;
static ONHI::History omniNhList;
static ONHI::StatusWatch omniNhWatch;
static std::vector<uint64_t> omniNhRows;       // the shown rows' entries (ONHI::Entry::seq), same order
static uint32_t omniNhRefreshAt = 0;

static bool omniNhPrivateOpen()
{
    for (const auto& t : tabs) if (t && t->omniPrivate) return true;
    return false;
}
static void omniNhBuild(OmniFxPanel& p);
static bool omniNhShown() { return !omniFxStack.empty() && omniFxStack.back().build == omniNhBuild; }
static void omniNhRecord(const std::string& text)
{
    if (omniTestMode() || omniNhPrivateOpen()) return;   // never recorded while any private tab exists
    if (!omniNhList.add(text, SDL_GetTicks())) return;
    if (omniFxStack.empty()) return;
    if (omniNhShown() || omniFxStack.back().build == omniFxQuickBuild) omniFxRefresh();   // the list / the row's count
}
// notice() (OmniBrowser.cpp) calls this after setting status / statusUntil.
static void omniNhNote(const std::string& text)
{
    omniNhWatch.sync(status, statusUntil);
    omniNhRecord(text);
}
// omniF3Tick: statuses set without notice(); the open list's "2 min ago" texts.
static void omniNhTick(uint32_t now)
{
    if (omniNhWatch.changed(status, statusUntil)) omniNhRecord(status);
    if (omniNhShown() && !ONHI::within(now, omniNhRefreshAt, ONHI::kRefreshMs)) omniFxRefresh();
}

// --- Options (top level): "Notices (n)  <dot> 2 new" ------------------------------------------------------------------
static void omniNhQuickRow(OmniFxPanel& p)
{
    if (omniNhList.empty()) return;
    OmniFxRow r; r.id = ONHI::kQuickRowId; r.label = ONHI::quickLabel(omniNhList.size()); r.value = ONHI::quickValue(omniNhList.unread());
    p.rows.push_back(r);
}

// --- the list ---------------------------------------------------------------------------------------------------------
static void omniNhBuild(OmniFxPanel& p)
{
    const uint32_t now = SDL_GetTicks();
    omniNhRefreshAt = now;
    omniNhList.markRead();
    omniNhRows.clear();
    int id = 1;
    for (const auto& e : omniNhList.entries()) {
        OmniFxRow r; r.id = id++; r.label = e.text; r.value = ONHI::rowValue(e, now); r.detail = ONHI::actionHint(e.action);
        p.rows.push_back(r);
        omniNhRows.push_back(e.seq);
    }
    if (p.rows.empty()) { OmniFxRow r; r.id = 0; r.label = ONHI::emptyLabel(); p.rows.push_back(r); }
}
static bool omniNhInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b == SDL_CONTROLLER_BUTTON_X) {   // Square: clear the list
        omniNhList.clear();
        omniFxRefresh();
        return true;
    }
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (r.id < 1 || size_t(r.id) > omniNhRows.size()) return true;
    const ONHI::Entry* e = omniNhList.find(omniNhRows[size_t(r.id - 1)]);
    if (!e || e->action == ONHI::kNone) return true;   // text only
    const ONHI::Action a = e->action;
    omniFxCloseAll();
    switch (a) {
    case ONHI::kMediaDownloads: omniMediaDownloadsOpen(false); break;   // the Downloads app (as L1 + R1)
    case ONHI::kFileDownloads: omniFxDownloadsShow(); break;
    case ONHI::kBlockedPopups: omniPnShow(); break;                     // the shown tab's blocked pop-ups
    case ONHI::kScreenshots: omniSsOpen(); break;
    default: break;
    }
    return true;
}
static void omniNhShow()
{
    OmniFxPanel p;
    p.kind = ONHI::kPanelKind; p.w = 1100; p.maxVisible = 9;
    p.title = ONHI::panelTitle(); p.subtitle = ONHI::panelSubtitle();
    p.build = omniNhBuild; p.input = omniNhInput;
    p.faces = { { 0, "Open" }, { 2, "Clear all" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}
static bool omniNhQuickInput(const OmniFxRow& r, int b)
{
    if (r.id != ONHI::kQuickRowId || b != SDL_CONTROLLER_BUTTON_A) return false;
    omniNhShow();
    return true;
}
'''

NOTICE = 'void notice(const std::string& text) { status = text; statusUntil = SDL_GetTicks() + 3500; }\n'

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSiteList.h" // OMNI_SITE_LIST_V1: Sites with custom settings (pure)\n',
         '#include "OmniSiteList.h" // OMNI_SITE_LIST_V1: Sites with custom settings (pure)\n'
         '#include "OmniNoticeHistory.h" // OMNI_NOTICE_HISTORY_V1: Recent notices (pure)\n'),
        (NOTICE,
         'static void omniNhNote(const std::string& text); // OMNI_NOTICE_HISTORY_V1 (OmniNoticeHistoryShell.h): Recent notices\n'
         'void notice(const std::string& text) { status = text; statusUntil = SDL_GetTicks() + 3500; omniNhNote(text); } // OMNI_NOTICE_HISTORY_V1\n'),
    ],
    'OmniQuickMenu.h': [
        ('static void omniDlpQuickRow(OmniFxPanel& p); // OMNI_DL_PROGRESS_V1 (OmniDlProgressShell.h)\n',
         'static void omniDlpQuickRow(OmniFxPanel& p); // OMNI_DL_PROGRESS_V1 (OmniDlProgressShell.h)\n'
         'static void omniNhQuickRow(OmniFxPanel& p); // OMNI_NOTICE_HISTORY_V1 (OmniNoticeHistoryShell.h)\n'
         'static bool omniNhQuickInput(const OmniFxRow& r, int b);\n'),
        ('        omniDlpQuickRow(p); // OMNI_DL_PROGRESS_V1: Downloads (n active), while the Downloads app has jobs\n',
         '        omniDlpQuickRow(p); // OMNI_DL_PROGRESS_V1: Downloads (n active), while the Downloads app has jobs\n'
         '        omniNhQuickRow(p); // OMNI_NOTICE_HISTORY_V1: Notices (n), while any are kept\n'),
        ('    if (omniDlpQuickInput(r, b)) return true; // OMNI_DL_PROGRESS_V1 (before the >= 900 rows)\n',
         '    if (omniDlpQuickInput(r, b)) return true; // OMNI_DL_PROGRESS_V1 (before the >= 900 rows)\n'
         '    if (omniNhQuickInput(r, b)) return true; // OMNI_NOTICE_HISTORY_V1 (before the >= 900 rows)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniWebAppsShell.h" // OMNI_WEB_APPS_V1 (uses the pinned tabs\' close rule)\n',
         '#include "OmniWebAppsShell.h" // OMNI_WEB_APPS_V1 (uses the pinned tabs\' close rule)\n'
         '#include "OmniNoticeHistoryShell.h" // OMNI_NOTICE_HISTORY_V1 (after the shells whose panels it opens)\n'),
        ('    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n',
         '    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n'
         '    omniNhTick(now);    // OMNI_NOTICE_HISTORY_V1: statuses set without notice(), the open list\'s times\n'),
    ],
}

NEEDS = {
    'OmniBrowser.cpp': ('OMNI_SITE_LIST_V1',),
    'OmniQuickMenu.h': ('OMNI_DL_PROGRESS_V1',),
    'OmniFeatures3.h': ('OMNI_WEB_APPS_V1', 'OMNI_SITE_CLEAR_V1_R2', 'OMNI_POPUP_NOTICE_V1', 'OMNI_SCREENSHOT_GALLERY_V1'),
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
    """A sibling apply_*.py without its comments and module docstring: names mentioned only in its notes are not a
    use. Numeric ids are looked for in the engine tree only (siblings' notes list other patches' ids)."""
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
    starts = [0] + [i + 1 for i, c in enumerate(src) if c == '\n']
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
    mine = {'OmniNoticeHistory.h', 'OmniNoticeHistoryShell.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        m = name.search(code_only(f.read_text(encoding='utf-8', errors='replace')))
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
    pure = (HERE / 'OmniNoticeHistory.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniNoticeHistory.h: %s missing' % MARK)
    msgs = [write_new('OmniNoticeHistory.h', pure, 'OmniQuickMenu.h'),
            write_new('OmniNoticeHistoryShell.h', SHELL, 'OmniFeatures3.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
