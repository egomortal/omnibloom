#!/usr/bin/env python3
"""OMNI_NOTICE_ACTIONS_V1 (2026-11-16): Toast actions - a notice can carry one action, run from the toast itself or,
for 10 minutes, from Recent notices.

What the user sees
  - Three notices get an action button beside the toast pill (right of it; above its right end when the pill is too
    wide), drawn like a hint-bar item: the Cross glyph (A on the Xbox controller style) and the action's label.
        "Downloaded: <title>" (a Downloads app job finished)       -> Open        omniMediaDownloadsOpen(false), the
                                                                                   Downloads app, exactly as L1 + R1
        "Downloaded <file> to ..." (a WebKit file download)          -> Open        omniFxDownloadsShow, the file
                                                                                   downloads list (as Recent notices)
        "Pop-up blocked. Options: ..." / "(site set to Block)"       -> Allow once  the newest blocked pop-up of that
                                                                                   tab opens in a new tab, through
                                                                                   omniFxOpenInNewTab (tab limit,
                                                                                   memory guard, private rule) and is
                                                                                   taken off the tab's Blocked pop-ups
                                                                                   list, as that list's own Cross does
    uBlock's ad pop-ups ("Pop-up blocked by uBlock (ad)") get no button: Options still opens the list for them. The
    pop-up notice's own "Options: Open it / Always allow" shortcut is unchanged.
  - An actionable toast shows at least 8 s (notice() gives 3.5 s; the pop-up notice already has 8 s), and while the
    pointer is on the pill or the button it is kept 1.5 s ahead (at most 30 s after it appeared). Hovering lights the
    button in the accent colour.
  - Recent notices (OMNI_NOTICE_HISTORY_V1): for 10 minutes after the notice, its row's detail reads
    "Open Downloads (9 min left)" / "Open file downloads (...)" / "Allow this pop-up once (...)", and Cross runs that
    action (menus close first). After 10 minutes the row falls back to Recent notices' own action (open Downloads /
    file downloads / the Blocked pop-ups list), which has no time limit and carries no address.

How Cross is kept from stealing a page click (the safest of the options weighed)
  Cross runs the action ONLY as a click ON the toast: the pointer must be on the pill or its button, visible
  (omniPtrAlpha() > 0), and the toast at least 0.6 s old (OTNA::kArmMs: a press as the toast appears under a resting
  pointer was aimed at the page). The hook is in click() right after omniOverlayClick, so it is reached only when Cross
  (or a real mouse click) is a pointer click at all: modals, menus, Options / fx panels, the keyboard, Browser settings,
  fullscreen video, built-in pages and the Master Control page that own Cross with their highlight run first and
  keep it; omniTnaUsable refuses again while editing / settings / fullscreen (and so video owning the screen) / any panel or
  overlay is open. Everywhere else on the page Cross clicks the page exactly as before, at any time.
  Rejected: "any Cross in the first 4 s" (downloads finish and pop-ups are blocked while the user is clicking:
  a click meant for the page would open the Downloads app or, worse, the very pop-up the page tried to force);
  "only when the pointer isn't over a link / field" (the only hover hit-test, OMNI_LINK_PREVIEW_V1's
  mouseDidMoveOverElement, knows links only, is off when link preview is off, and nothing knows script buttons);
  a free chord (L2 + face buttons are all taken by OMNI_L2_CHORDS_V1, Options is the pop-up notice's own shortcut, the
  others have browse actions). Before this patch a click on the toast went to the page element hidden under it; now
  the toast, which is drawn on top, takes it - the usual overlay rule.
  The UI-scale zoomed toast (OMNI_UI_SCALE_V1_R2, omniUisToast) has no button and no hit area (its geometry is
  internal to that path): there the action is in Recent notices only.

Private tabs
  An action from a tab (Allow once, file downloads) remembers the tab and whether it was private. When a private tab
  closes, its toast loses its button and its records go (checked every pass in omniTnaTick). Private records are never
  offered in Recent notices (which keeps nothing while any private tab exists anyway). "Downloaded: <title>" comes from
  the Downloads app and is never private. Everything is memory only; nothing is written anywhere. Test modes
  (omniTestMode) get no actions.

How it watches the toast
  omniTnaTick (omniF3Tick, right after omniNhTick) compares (status, statusUntil) with its own watch, as Recent notices
  does: a new text, or the same text with a later deadline, is a new toast. When it moves statusUntil itself (8 s
  minimum, hover hold, the toast ending after its action ran) it syncs both its watch and Recent notices' omniNhWatch,
  so a held toast is never recorded twice. A Recent notices row and a record are the same notice when the text is the
  same and their raise times are within 3 s (OTNA::kMatchMs).

Files
  OmniNoticeActions.h       (new, pure; also kept in tools/ for the host test) actions by text, arming, show / hold
                            deadlines, the button's place, the 10-minute store, texts. tools/test_notice_actions.cpp:
                            g++ -std=c++20 -Wall -Wextra -Werror -I. test_notice_actions.cpp -o t && ./t
  OmniNoticeActionsShell.h  (new) the watch, the button, the click, the runs, the Recent notices hooks.
Anchors (each exactly once; whole lines kept, new lines before / after them, /* */ comments only; every file keeps its
own line endings; re-run prints "already")
  OmniBrowser.cpp            the OmniNoticeHistory.h include (pure include after); the omniNhNote declaration (ours
                             after); click()'s omniOverlayClick line (omniTnaClick after); omniDrawToast's UI-scale
                             line (omniTnaNoPill before); omniDrawToast's omniLabel(shown, ...) line (omniTnaDraw after)
  OmniFeatures3.h            the OmniNoticeHistoryShell.h include (ours after); omniNhTick(now) (omniTnaTick after)
  OmniNoticeHistoryShell.h   the omniNhBuild declaration (ours after); the row line of omniNhBuild (detail after);
                             omniNhInput's "text only" line (omniTnaHistoryRun before). apply_notice_history.py
                             rewrites this file when re-run on a patched tree: run the chain in order on a fresh tree.
No ids. Names OTNA / omniTna / OmniNoticeActions (checked unused before a first apply).
Controls guide row (OmniControlsHelp.h table, kBrowsing):
  { kBrowsing, { gCross }, 0, false, "Run a notice's action (Open / Allow once)", "Pointer on the notice or its button",
    "omniTnaClick" },
Apply AFTER apply_notice_history.py (and so after apply_popup_notice.py, apply_dl_progress.py, apply_ui_scale.py).
usage: apply_notice_actions.py <engine tree>
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_NOTICE_ACTIONS_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_notice_actions.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ()
NAMES = ('OTNA', 'omniTna', 'OmniNoticeActions', 'OMNI_NOTICE_ACTIONS')

SHELL = r'''// OMNI_NOTICE_ACTIONS_V1: Toast actions (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous
// namespace, after OmniNoticeHistoryShell.h and OmniPopupNoticeShell.h). The pure part is OmniNoticeActions.h; the
// reasons are in tools/apply_notice_actions.py. Main thread only. Memory only: nothing is written anywhere.
#pragma once

namespace OTNA = OmniNoticeActions;
static OTNA::Watch omniTnaWatch;
static OTNA::Record omniTnaToast;             // the toast now showing and its action (kNone: no button); .at: it appeared
static OTNA::Store omniTnaStore;              // actionable notices of the last 10 min (Recent notices acts from here)
static OTNA::Rect omniTnaPill, omniTnaChip;   // where the toast and its button were last drawn (layout units)
static std::string omniTnaDrawnText;          // the text they were drawn for ("": no button drawn)
static bool omniTnaHover = false;

static uintptr_t omniTnaKey(const Tab* t) { return reinterpret_cast<uintptr_t>(t); }
static bool omniTnaAlive(uintptr_t key)
{
    for (const auto& t : tabs) if (t && omniTnaKey(t.get()) == key) return true;
    return false;
}
// The button may show / be pressed: the toast shows this text and nothing above the page owns Cross.
static bool omniTnaUsable(const std::string& message)
{
    if (omniTestMode() || omniTnaToast.action == OTNA::kNone || message != omniTnaToast.text || status != message) return false;
    if (editing || settingsOpen || pageFullscreen || !omniFxStack.empty() || omniOverlayOpen() || !active()) return false;   // fullscreen covers video owning the screen
    return statusUntil != 0 && int32_t(statusUntil - SDL_GetTicks()) > 0;
}
static bool omniTnaOn(float x, float y) { return OTNA::inside(omniTnaPill, x, y) || OTNA::inside(omniTnaChip, x, y); }
static bool omniTnaPointerOn()
{
    return omniPtrAlpha() > 0 && !omniTnaDrawnText.empty() && omniTnaDrawnText == status && omniTnaOn(float(pointerX), float(pointerY));
}
// statusUntil moved here: both watches learn it, so the toast is not taken for a new raise (Recent notices x2).
static void omniTnaSetUntil(uint32_t until)
{
    if (until == statusUntil) return;
    statusUntil = until;
    omniTnaWatch.sync(status, statusUntil);
    omniNhWatch.sync(status, statusUntil);
    omniShellDirty = true;
}
static void omniTnaArrive(uint32_t now)
{
    omniTnaToast = OTNA::Record {};
    omniTnaDrawnText.clear();
    omniShellDirty = true;
    Tab* t = active();
    const bool popup = !omniPnHint.empty() && status == omniPnHint && t && omniPnKey(t) == omniPnHintTab;
    OTNA::Record r;
    r.text = status; r.at = now; r.action = OTNA::actionFor(status, popup);
    if (r.action == OTNA::kAllowPopup) {
        const auto* items = OPN::list(omniPnRecent, omniPnHintTab);
        if (!items || !OPN::reopenable(items->front()) || items->front().kind == OPN::kAd || items->front().url.size() > OTNA::kUrlMax) return;
        r.url = items->front().url;
    }
    if (r.action == OTNA::kNone) return;
    if (OTNA::fromTab(r.action) && t) { r.tab = omniTnaKey(t); r.priv = t->omniPrivate; }
    omniTnaToast = r;
    omniTnaStore.add(r);
    omniTnaSetUntil(OTNA::showUntil(statusUntil, now));
}
// omniF3Tick, every pass (after omniNhTick).
static void omniTnaTick(uint32_t now)
{
    if (omniTestMode()) return;
    omniTnaStore.prune(now);
    omniTnaStore.dropClosedPrivate(omniTnaAlive);   // a private tab closed: its actions go
    if (omniTnaToast.priv && !omniTnaAlive(omniTnaToast.tab)) { omniTnaToast = OTNA::Record {}; omniTnaDrawnText.clear(); omniShellDirty = true; }
    if (omniTnaWatch.changed(status, statusUntil)) omniTnaArrive(now);
    const bool on = omniTnaUsable(status) && omniTnaPointerOn();
    if (on != omniTnaHover) { omniTnaHover = on; omniShellDirty = true; }
    if (on) omniTnaSetUntil(OTNA::holdUntil(statusUntil, now, omniTnaToast.at));
}

// --- running an action ------------------------------------------------------------------------------------------------
static bool omniTnaRun(const OTNA::Record& r)
{
    fprintf(stderr, "OMNI_NOTICE_ACTIONS_V1: %s\n", OTNA::label(r.action));
    switch (r.action) {
    case OTNA::kOpenDownloads: omniMediaDownloadsOpen(false); return true;   // the Downloads app (as L1 + R1)
    case OTNA::kOpenFileDownloads: omniFxDownloadsShow(); return true;
    case OTNA::kAllowPopup: {
        if (!omniFxOpenInNewTab(r.url, false, false)) return false;   // the tab limit / memory guard said why
        if (const auto* items = OPN::list(omniPnRecent, r.tab)) {
            for (size_t i = 0; i < items->size(); ++i) {
                if ((*items)[i].url != r.url) continue;
                OPN::Blocked taken;
                OPN::take(omniPnRecent, r.tab, i, taken);   // opened: off the Blocked pop-ups list, as that list does
                break;
            }
        }
        return true;
    }
    default: return false;
    }
}
// "Allow once" is used up once it opened; Open stays.
static void omniTnaUsed(const OTNA::Record& r)
{
    if (r.action != OTNA::kAllowPopup) return;
    for (const auto& s : omniTnaStore.records())
        if (s.action == r.action && s.url == r.url && s.tab == r.tab) { omniTnaStore.remove(&s); return; }
}

// --- the toast's button (omniDrawToast) and the click on it (click()) -------------------------------------------------
static void omniTnaNoPill()
{
    omniTnaDrawnText.clear();
    omniTnaPill = omniTnaChip = OTNA::Rect {};
}
static void omniTnaDraw(const std::string& message, bool error, int x, int y, int w, int h, uint8_t alpha)
{
    omniTnaNoPill();
    if (error || alpha < 160 || !omniTnaUsable(message)) return;   // fading in / out: no button yet
    const OmniTheme& T = omniTheme();
    const char* label = OTNA::label(omniTnaToast.action);
    const int textW = int(omniTextWidthPx(omniSmall, label) / displayScale + 0.5);
    omniTnaPill = OTNA::Rect { x, y, w, h };
    omniTnaChip = OTNA::chipRect(omniTnaPill, 14 + 28 + 6 + textW + 18, width);
    const OTNA::Rect c = omniTnaChip;
    const bool hover = omniPtrAlpha() > 0 && omniTnaOn(float(pointerX), float(pointerY));
    omniShadow(c.x, c.y, c.w, c.h, c.h / 2, 12, uint8_t(110 * alpha / 255), 3);
    fillRounded(c.x, c.y, c.w, c.h, c.h / 2, hover ? T.accent : omniMix(T.raised, T.line, 0.6f), alpha);
    if (!hover) fillRounded(c.x + 1, c.y + 1, c.w - 2, c.h - 2, c.h / 2 - 1, T.raised, alpha);
    faceIcon(c.x + 28, c.y + c.h / 2, 0, playStationIcons);   /* Cross (A on the Xbox style), as the hint bar draws it */
    omniLabel(label, float(c.x + 14 + 28 + 6), c.y + c.h / 2.f, omniSmall, hover ? T.accentInk : T.ink, 0, 0, alpha);
    omniTnaDrawnText = message;
}
// click(), after omniOverlayClick: Cross (or a mouse click) ON the toast runs its action. Anywhere else: false, the
// click goes on exactly as before.
static bool omniTnaClick(int x, int y)
{
    if (!omniTnaUsable(status) || omniTnaDrawnText != status || omniToastError || omniToastText != status || omniPtrAlpha() == 0) return false;
    const uint32_t now = SDL_GetTicks();
    if (!OTNA::armed(now, omniTnaToast.at) || !omniTnaOn(float(x), float(y))) return false;
    const OTNA::Record r = omniTnaToast;
    omniTnaToast = OTNA::Record {};
    omniTnaNoPill();
    omniTnaSetUntil(now + 1);   // the toast ends ("Ready" next pass)
    if (omniTnaRun(r)) omniTnaUsed(r);
    return true;
}

// --- Recent notices (OmniNoticeHistoryShell.h) -------------------------------------------------------------------------
static void omniTnaHistoryDetail(const std::string& text, uint32_t at, uint32_t now, std::string& detail)
{
    if (omniTestMode()) return;
    if (const OTNA::Record* r = omniTnaStore.match(text, at, now)) detail = OTNA::historyDetail(r->action, r->at, now);
}
static bool omniTnaHistoryRun(const std::string& text, uint32_t at)
{
    const OTNA::Record* p = omniTestMode() ? nullptr : omniTnaStore.match(text, at, SDL_GetTicks());
    if (!p) return false;   // none, or older than 10 min: Recent notices' own action
    const OTNA::Record r = *p;
    omniFxCloseAll();
    if (omniTnaRun(r)) omniTnaUsed(r);
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniNoticeHistory.h" // OMNI_NOTICE_HISTORY_V1: Recent notices (pure)\n',
         '#include "OmniNoticeHistory.h" // OMNI_NOTICE_HISTORY_V1: Recent notices (pure)\n'
         '#include "OmniNoticeActions.h" /* OMNI_NOTICE_ACTIONS_V1: Toast actions (pure) */\n'),
        ('static void omniNhNote(const std::string& text); // OMNI_NOTICE_HISTORY_V1 (OmniNoticeHistoryShell.h): Recent notices\n',
         'static void omniNhNote(const std::string& text); // OMNI_NOTICE_HISTORY_V1 (OmniNoticeHistoryShell.h): Recent notices\n'
         'static void omniTnaNoPill(); /* OMNI_NOTICE_ACTIONS_V1 (OmniNoticeActionsShell.h): the toast\'s action button */\n'
         'static void omniTnaDraw(const std::string& message, bool error, int x, int y, int w, int h, uint8_t alpha); /* OMNI_NOTICE_ACTIONS_V1 */\n'
         'static bool omniTnaClick(int x, int y); /* OMNI_NOTICE_ACTIONS_V1 */\n'),
        ('    if (omniOverlayClick(int(pointerX), int(pointerY))) return; // OMNI_DIALOGS_V1\n',
         '    if (omniOverlayClick(int(pointerX), int(pointerY))) return; // OMNI_DIALOGS_V1\n'
         '    if (omniTnaClick(int(pointerX), int(pointerY))) return; /* OMNI_NOTICE_ACTIONS_V1: a click ON the toast runs its action */\n'),
        ('    if (omniUisLevel() != OUIS::Normal) { omniUisToast(message, error, a); return; } // OMNI_UI_SCALE_V1_R2: the pill zoomed\n',
         '    omniTnaNoPill(); /* OMNI_NOTICE_ACTIONS_V1: no button unless drawn below (the zoomed pill has none) */\n'
         '    if (omniUisLevel() != OUIS::Normal) { omniUisToast(message, error, a); return; } // OMNI_UI_SCALE_V1_R2: the pill zoomed\n'),
        ('    omniLabel(shown, x + 24 + icon, y + h / 2.f, omniSmall, T.ink, 0, 0, A);\n',
         '    omniLabel(shown, x + 24 + icon, y + h / 2.f, omniSmall, T.ink, 0, 0, A);\n'
         '    omniTnaDraw(message, error, x, y, w, h, A); /* OMNI_NOTICE_ACTIONS_V1: the action button beside the pill */\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniNoticeHistoryShell.h" // OMNI_NOTICE_HISTORY_V1 (after the shells whose panels it opens)\n',
         '#include "OmniNoticeHistoryShell.h" // OMNI_NOTICE_HISTORY_V1 (after the shells whose panels it opens)\n'
         '#include "OmniNoticeActionsShell.h" /* OMNI_NOTICE_ACTIONS_V1 (after Recent notices and the pop-up notice) */\n'),
        ('    omniNhTick(now);    // OMNI_NOTICE_HISTORY_V1: statuses set without notice(), the open list\'s times\n',
         '    omniNhTick(now);    // OMNI_NOTICE_HISTORY_V1: statuses set without notice(), the open list\'s times\n'
         '    omniTnaTick(now);   /* OMNI_NOTICE_ACTIONS_V1: the toast\'s action, its hold, the 10-minute records */\n'),
    ],
    'OmniNoticeHistoryShell.h': [
        ('static void omniNhBuild(OmniFxPanel& p);\n',
         'static void omniNhBuild(OmniFxPanel& p);\n'
         'static void omniTnaHistoryDetail(const std::string& text, uint32_t at, uint32_t now, std::string& detail); /* OMNI_NOTICE_ACTIONS_V1 */\n'
         'static bool omniTnaHistoryRun(const std::string& text, uint32_t at); /* OMNI_NOTICE_ACTIONS_V1 */\n'),
        ('        OmniFxRow r; r.id = id++; r.label = e.text; r.value = ONHI::rowValue(e, now); r.detail = ONHI::actionHint(e.action);\n',
         '        OmniFxRow r; r.id = id++; r.label = e.text; r.value = ONHI::rowValue(e, now); r.detail = ONHI::actionHint(e.action);\n'
         '        omniTnaHistoryDetail(e.text, e.at, now, r.detail); /* OMNI_NOTICE_ACTIONS_V1: "Allow this pop-up once (9 min left)" */\n'),
        ('    if (!e || e->action == ONHI::kNone) return true;   // text only\n',
         '    if (e && omniTnaHistoryRun(e->text, e->at)) return true; /* OMNI_NOTICE_ACTIONS_V1: within 10 min of the notice */\n'
         '    if (!e || e->action == ONHI::kNone) return true;   // text only\n'),
    ],
}

NEEDS = {
    'OmniBrowser.cpp': ('OMNI_NOTICE_HISTORY_V1', 'OMNI_UI_SCALE_V1_R2'),
    'OmniFeatures3.h': ('OMNI_NOTICE_HISTORY_V1', 'OMNI_POPUP_NOTICE_V1'),
    'OmniNoticeHistoryShell.h': ('OMNI_NOTICE_HISTORY_V1',),
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
SKIP_SIBLINGS = ('apply_controls_help.py',)
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
    word = re.compile(r'\b(%s)\b' % '|'.join(IDS)) if IDS else None
    name = re.compile('|'.join(NAMES))
    mine = {'OmniNoticeActions.h', 'OmniNoticeActionsShell.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name or f.name in SKIP_SIBLINGS:
            continue
        raw = f.read_text(encoding='utf-8', errors='replace')
        if MARK in raw:   # a later patch that builds on this one
            continue
        m = name.search(code_only(raw))   # numeric ids: engine tree only
        if m:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in mine or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        if MARK in t:
            continue
        c = cpp_code(t)
        m = (word.search(c) if word else None) or (None if f.name in GUIDE else name.search(c))
        if m:
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
    pure = (HERE / 'OmniNoticeActions.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniNoticeActions.h: %s missing' % MARK)
    msgs = [write_new('OmniNoticeActions.h', pure, 'OmniNoticeHistory.h'),
            write_new('OmniNoticeActionsShell.h', SHELL, 'OmniNoticeHistoryShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
