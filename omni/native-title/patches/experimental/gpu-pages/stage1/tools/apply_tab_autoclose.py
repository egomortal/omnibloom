#!/usr/bin/env python3
"""OMNI_TAB_AUTOCLOSE_V1 (2026-11-16): Browser settings > "Close unused tabs": Off / 7 days / 14 days / 30 days
(default Off). Backlog E14.

What the user sees
  - Browser settings (Options > Browser settings) has a new row after "Sleep idle tabs" / "Include pinned tabs":
        "Close unused tabs"   value: Off / 7 days / 14 days / 30 days (D-pad left / right; Cross steps and wraps)
    The first time it is turned on, Omni asks once (the shell's modal, Cancel focused):
        "Close tabs unused for 7 days?"  (what is never closed; closed tabs can be reopened)  [Cancel] [Turn on]
    Cancel leaves it Off (asked again next time); "Turn on" is remembered (asked\t1) and never asked again.
  - 30 s after start (once the session is restored) and then once an hour, every background tab whose last-shown time
    is older than the setting is closed, oldest first. Each goes to "Reopen closed tab" (omniFxTabClosing: the existing
    recently-closed list, the last 10, never private tabs), so it can be reopened as usual. One notice:
        "Closed 3 unused tabs" / "Closed 1 unused tab"
  - Never closed: the shown tab, pinned tabs (OMNI_PINNED_TABS_V1 omniPtPinned), a tab with a sound badge or playing
    audio (OMNI_TAB_AUDIO_V1 omniTaBadge / omniTaPlaying), private tabs (they could not be reopened), Media-section
    tabs (omniMediaOwns), and never the last tab (the pure pick keeps one even with no shown tab).
  - A check is put off by a minute while a panel or a dialog is open (Tabs panel rows would move under the user) or a
    WebKit download runs (omniDownloads; downloads are not tied to a tab in the shell).
  - Background tabs are closed without being shown: the shown tab's view, keyboard and full screen are not touched
    (omniTxcCloseAt does what closeTab() does for the active tab: omniModalsDropTab, omniFxTabClosing, WKPageClose,
    erase; `selected` follows the shown tab). Unloaded / lazy (not yet loaded) tabs are closed as they are: their
    real address is in tab.url (OmniTabMemory / session restore keep it there), so Reopen gets the page.

Last-shown times (they must survive restarts)
  Tab sleep's last-shown time (OmniTabMemory.h OmniTmTab::shownAt) is SDL_GetTicks(): per run, lost on restart, so it is
  not used. This patch keeps its own wall-clock time per tab (time(), seconds): set when a tab stops or starts being the
  shown one (omniTxcTick compares active() with the last shown tab: one pointer compare per pass) and refreshed for the
  shown tab every 15 min. It is written into the existing session restore file, session.txt (omniSessionText; written
  through omniIoQueue only when the text changed, as before), one line per tab after its "tab" / "pinned" / "group"
  lines:  shown\t<n>\t<seconds>\t<FNV-1a of the tab's session URL, 8 hex>
  Older builds skip the line (they only read tab / pinned / group / selected). On start-up omniEverydayStart passes the
  lines to omniTxcRestoreLine and, right after the tabs are made (before groups / pinned reorder them), omniTxcRestoreApply
  gives each restored tab (file order) its time when the URL hash matches its omniLazyURL (Startup choice may open other
  tabs than last time's: no match, no time). A tab without a time (new, older session file) counts from the first check
  that sees it, so turning the feature on never closes anything at once.
  Clock safety (pure OmniTabAutoClose.h): nothing is decided while time() reads before 2024-01-01 (no stamps are taken
  then either); a stored time before 2024 or more than 5 min in the future (the clock went back) is not used: that tab
  counts as shown now (and its stored time is replaced). Rest mode with the clock running on is real unused time.
Storage: /data/omni/tab-autoclose.txt ("days\t7\nasked\t1\n", omniIoQueue); session.txt "shown" lines (above).
Log: "OMNI TAB AUTOCLOSE: closed N unused tab(s) (D days), M open"; "OMNI TAB AUTOCLOSE: setting D days".
Cost: Off or On, one pointer compare per pass (plus time() on a tab switch / every 15 min); a session.txt write at most
  every 15 min from the refresh. On: one loop over the tabs an hour.

Pure part: engine/entry/OmniTabAutoClose.h (copied from tools/OmniTabAutoClose.h): settings, clock rules, timer,
  selection, session line, texts. Tests: tools/test_tab_autoclose.cpp
  (g++ -std=c++20 -Wall -Wextra -Werror -I. test_tab_autoclose.cpp -o t && ./t).
Shell part: engine/entry/OmniTabAutoCloseShell.h (written by this script), alias OTXC, names omniTxc*.
Ids: Browser settings row 387 (omniF3SettingsInput's switch, ids >= 300). Checked free in the tree (code, not comments)
  and in every sibling apply_*.py (code only: names, and row-id assignments such as "= 387" / "case 387").

Anchors (exactly once each; whole lines; MARK makes each file idempotent; CRLF / LF kept):
  OmniBrowser.cpp      the OmniTabSleep.h include line (pure include after); omniSessionText's omniTgSessionLine line
                       (our line after); omniEverydayStart's omniTgRestoreLine branch (our branch after) and its
                       "omniF3Restoring = false;" line (restore apply after).
  OmniFeatures3Decl.h  the omniTspForget declaration line (our declarations after).
  OmniFeatures3.h      the OmniTabSleepShell.h include line; the omniTspSettingsRows line of omniF3SettingsRows; the
                       "case OmniTabSleep::kRowMinutes" line of omniF3SettingsInput (our case before); the omniTspTick
                       line of omniF3Tick.
  OmniTabsPage.h       the omniTspForget line of omniFxTabClosing.
Apply AFTER apply_tab_sleep.py, apply_pinned_tabs.py, apply_tab_groups.py, apply_tab_audio.py (their lines are anchors).
usage: apply_tab_autoclose.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_TAB_AUTOCLOSE_V1'
if len(sys.argv) != 2:
    sys.exit('usage: apply_tab_autoclose.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
HERE = Path(__file__).resolve().parent
PURE = HERE / 'OmniTabAutoClose.h'
OURS = ('OmniTabAutoClose.h', 'OmniTabAutoCloseShell.h')
ROW_ID = '387'
NAMES = (r'\bOTXC\b', r'\bomniTxc[A-Z]', r'\bOmniTabAutoClose\b')

SHELL = r'''// OMNI_TAB_AUTOCLOSE_V1: Browser settings > "Close unused tabs" (shell side). Included from OmniFeatures3.h (inside
// OmniBrowser.cpp's anonymous namespace) after OmniTabSleepShell.h, so after the pinned tabs, tab audio and tab groups
// shells. The pure part is OmniTabAutoClose.h; the reasons are in tools/apply_tab_autoclose.py. Main thread only.
// Cost: one pointer compare per pass (Off or On); On: one loop over the tabs an hour.
#pragma once

namespace OTXC = OmniTabAutoClose;

static OTXC::Settings omniTxcSet;
static bool omniTxcLoaded = false;
static OTXC::Timer omniTxcTimer;
static const void* omniTxcShown = nullptr;                    // the tab shown at the last pass
static uint32_t omniTxcRefreshAt = 0;                         // SDL ticks of the last stamp of the shown tab
static std::unordered_map<const void*, long long> omniTxcStamps;   // tab -> last shown (time(), seconds)
static std::vector<OTXC::Mark> omniTxcMarks;                  // session.txt "shown" lines, until the tabs exist

static void omniTxcLoad()
{
    if (omniTxcLoaded) return;
    omniTxcLoaded = true;
    std::string text;
    if (FILE* f = fopen(omniData(OTXC::kFileName).c_str(), "r")) {
        char b[256];
        size_t n = 0;
        while ((n = fread(b, 1, sizeof(b), f)) > 0 && text.size() < 4096) text.append(b, n);
        fclose(f);
    }
    omniTxcSet = OTXC::parse(text);   // no file: Off, not asked
}
static void omniTxcSave() { omniIoQueue(omniData(OTXC::kFileName), OTXC::serialize(omniTxcSet), false); }
static long long omniTxcNow() { return static_cast<long long>(time(nullptr)); }
static void omniTxcStamp(const void* tab, long long now)
{
    if (tab && OTXC::clockValid(now)) omniTxcStamps[tab] = now;   // a clock before 2024 stamps nothing
}
// Declared in OmniFeatures3Decl.h: omniFxTabClosing.
static void omniTxcForget(const void* tab)
{
    omniTxcStamps.erase(tab);
    if (omniTxcShown == tab) omniTxcShown = nullptr;
}

// --- session.txt (omniSessionText / omniEverydayStart; declared in OmniFeatures3Decl.h) ------------------------------
static std::string omniTxcSessionURL(const Tab& t)   // exactly what omniSessionText writes as the tab's URL
{
    const std::string url = !t.omniLazyURL.empty() ? t.omniLazyURL : omniWebURL(t.url) ? t.url : std::string("newtab");
    return omniOneLine(url, 2048);
}
static std::string omniTxcSessionLine(const Tab& t, int n)
{
    auto f = omniTxcStamps.find(&t);
    if (f == omniTxcStamps.end()) return std::string();
    return OTXC::sessionLine(n, f->second, OTXC::hashOf(omniTxcSessionURL(t)));
}
static bool omniTxcRestoreLine(const std::string& line)
{
    OTXC::Mark m;
    if (!OTXC::parseLine(line, m)) return false;
    if (m.index >= 0 && omniTxcMarks.size() < OTXC::kMaxMarks) omniTxcMarks.push_back(m);
    return true;
}
// Right after omniEverydayStart made the tabs (file order, nothing reordered yet): a line counts only for the tab whose
// session URL it was written for.
static void omniTxcRestoreApply()
{
    int n = 0;
    for (const OTXC::Mark& m : omniTxcMarks) {
        if (m.index < 0 || size_t(m.index) >= tabs.size()) continue;
        const Tab& t = *tabs[size_t(m.index)];
        if (t.omniLazyURL.empty() || OTXC::hashOf(t.omniLazyURL) != m.hash) continue;
        omniTxcStamps[&t] = m.seconds;   // checked against the clock when used (OTXC::normalize)
        ++n;
    }
    omniTxcMarks.clear();
    if (n) { fprintf(stderr, "OMNI TAB AUTOCLOSE: restored %d last-shown time(s)\n", n); fflush(stderr); }
}

// --- closing ------------------------------------------------------------------------------------------------------------
// closeTab() for a background tab: the shown tab stays shown (no activate(): its view, keyboard and full screen are
// not touched). The tab goes to "Reopen closed tab" through omniFxTabClosing as with any close.
static bool omniTxcCloseAt(size_t i)
{
    if (i >= tabs.size() || tabs.size() <= 1 || i == selected) return false;
    const void* shown = active();
    Tab& t = *tabs[i];
    omniModalsDropTab(&t);   // answer its dialogs / sign-in first
    omniFxTabClosing(t);     // recently-closed list, and every feature forgets it (ours too)
    WKPageClose(t.page);
    tabs.erase(tabs.begin() + long(i));
    const size_t s = omniPtIndex(shown);
    selected = s < tabs.size() ? s : std::min(selected, tabs.size() - 1);
    return true;
}
static void omniTxcCheck(uint32_t now)
{
    if (!omniFxStack.empty() || omniModalVisible() || !omniDownloads.empty()) { omniTxcTimer.postpone(now); return; }
    const long long wall = omniTxcNow();
    if (!OTXC::clockValid(wall)) { fprintf(stderr, "OMNI TAB AUTOCLOSE: clock not set, nothing closed\n"); fflush(stderr); return; }
    const Tab* shown = active();
    std::vector<OTXC::Cand> cs;
    cs.reserve(tabs.size());
    for (auto& t : tabs) {
        long long& st = omniTxcStamps[t.get()];
        st = OTXC::normalize(st, wall);   // unknown, before 2024 or in the future: counts from now
        OTXC::Cand c;
        c.current = t.get() == shown;
        c.pinned = omniPtPinned(*t);
        c.sound = t->omniTaBadge != 0 || omniTaPlaying(*t);
        c.keep = t->omniPrivate || omniMediaOwns(*t);
        c.shown = st;
        cs.push_back(c);
    }
    std::vector<const void*> doomed;
    for (int i : OTXC::pick(cs, wall, omniTxcSet.days)) doomed.push_back(tabs[size_t(i)].get());
    int closed = 0;
    for (const void* d : doomed) {
        const size_t i = omniPtIndex(d);
        if (i >= tabs.size() || tabs[i].get() == active() || omniPtPinned(*tabs[i])) continue;
        if (omniTxcCloseAt(i)) ++closed;
    }
    if (!closed) return;
    omniShellDirty = true;
    notice(OTXC::closedNotice(closed));
    fprintf(stderr, "OMNI TAB AUTOCLOSE: closed %d unused tab(s) (%d days), %zu open\n", closed, omniTxcSet.days, tabs.size());
    fflush(stderr);
}
// omniF3Tick, every pass: the shown tab's last-shown time (on a switch, every 15 min), and the start-up / hourly check.
static void omniTxcTick(uint32_t now)
{
    if (omniTestMode()) return;
    const Tab* a = active();
    if (a != omniTxcShown || uint32_t(now - omniTxcRefreshAt) >= OTXC::kRefreshMs) {
        const long long wall = omniTxcNow();
        if (omniTxcShown && omniTabAlive(omniTxcShown)) omniTxcStamp(omniTxcShown, wall);   // shown until now
        omniTxcStamp(a, wall);
        omniTxcShown = a;
        omniTxcRefreshAt = now;
    }
    if (!omniSessionReady) return;
    omniTxcLoad();
    if (omniTxcSet.days <= 0) return;
    if (omniTxcTimer.due(now)) omniTxcCheck(now);
}

// --- Browser settings row (omniF3SettingsRows, after "Sleep idle tabs"; input from omniF3SettingsInput) ----------------
static void omniTxcSettingsRows(OmniFxPanel& p)
{
    omniTxcLoad();
    OmniFxRow r; r.id = OTXC::kRowDays; r.label = OTXC::label(); r.value = OTXC::daysValue(omniTxcSet.days);
    r.stepper = true; r.detail = OTXC::daysDetail(omniTxcSet.days);
    p.rows.push_back(r);
}
static void omniTxcApply(int days)
{
    omniTxcSet.days = days;
    omniTxcSave();
    notice(OTXC::daysNotice(days));
    omniTxcTimer.restart(SDL_GetTicks());   // a first check 30 s from now
    fprintf(stderr, "OMNI TAB AUTOCLOSE: setting %d days\n", days); fflush(stderr);
    omniFxRefresh();
}
static bool omniTxcSettingsInput(int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT, a = b == SDL_CONTROLLER_BUTTON_A;
    const int dir = left ? -1 : (right || a) ? 1 : 0;
    if (!dir) return false;
    omniTxcLoad();
    const int next = OTXC::stepDays(omniTxcSet.days, dir, a);
    if (next == omniTxcSet.days) return true;
    if (omniTxcSet.days == 0 && next > 0 && !omniTxcSet.asked) {   // asks once, the first time it is turned on
        omniAsk(OTXC::askTitle(next), OTXC::askBody(), "Turn on", [next](bool ok) {
            if (!ok) return;
            omniTxcSet.asked = true;
            omniTxcApply(next);
        });
        return true;
    }
    omniTxcApply(next);
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniTabSleep.h" // OMNI_TAB_SLEEP_V1: Sleep idle tabs: eligibility, order, rate limit, texts (pure)\n',
         '#include "OmniTabSleep.h" // OMNI_TAB_SLEEP_V1: Sleep idle tabs: eligibility, order, rate limit, texts (pure)\n'
         '#include "OmniTabAutoClose.h" /* OMNI_TAB_AUTOCLOSE_V1: Close unused tabs: clock rules, selection, session line (pure) */\n'),
        (r'        s += omniTgSessionLine(t, n); // OMNI_TAB_GROUPS_V1: "group\t<n>\t<group>\t<colour>\t<collapsed>\t<name>" (older builds skip it)' '\n',
         r'        s += omniTgSessionLine(t, n); // OMNI_TAB_GROUPS_V1: "group\t<n>\t<group>\t<colour>\t<collapsed>\t<name>" (older builds skip it)' '\n'
         r'        s += omniTxcSessionLine(t, n); /* OMNI_TAB_AUTOCLOSE_V1: "shown\t<n>\t<seconds>\t<url hash>" (older builds skip it) */' '\n'),
        (r'            } else if (omniTgRestoreLine(s)) { // OMNI_TAB_GROUPS_V1: "group\t<index>\t..."' '\n',
         r'            } else if (omniTgRestoreLine(s)) { // OMNI_TAB_GROUPS_V1: "group\t<index>\t..."' '\n'
         r'            } else if (omniTxcRestoreLine(s)) { /* OMNI_TAB_AUTOCLOSE_V1: "shown\t<index>\t..." */' '\n'),
        ('    omniF3Restoring = false;\n',
         '    omniF3Restoring = false;\n'
         '    omniTxcRestoreApply(); /* OMNI_TAB_AUTOCLOSE_V1: last-shown times of the restored tabs (file order, URL checked) */\n'),
    ],
    'OmniFeatures3Decl.h': [
        ('static void omniTspForget(const void* tab);                // omniFxTabClosing\n',
         'static void omniTspForget(const void* tab);                // omniFxTabClosing\n'
         '/* OMNI_TAB_AUTOCLOSE_V1 (OmniTabAutoCloseShell.h): Browser settings > Close unused tabs */\n'
         'static void omniTxcForget(const void* tab);                /* omniFxTabClosing */\n'
         'static std::string omniTxcSessionLine(const Tab& t, int n); /* omniSessionText: "shown" line */\n'
         'static bool omniTxcRestoreLine(const std::string& line);   /* omniEverydayStart */\n'
         'static void omniTxcRestoreApply();                         /* omniEverydayStart, after the tabs are made */\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniTabSleepShell.h" // OMNI_TAB_SLEEP_V1 (after tab memory, pinned tabs, tab groups, downloads progress)\n',
         '#include "OmniTabSleepShell.h" // OMNI_TAB_SLEEP_V1 (after tab memory, pinned tabs, tab groups, downloads progress)\n'
         '#include "OmniTabAutoCloseShell.h" /* OMNI_TAB_AUTOCLOSE_V1 (after tab sleep, pinned tabs, tab audio) */\n'),
        ('    omniTspSettingsRows(p); // OMNI_TAB_SLEEP_V1: Sleep idle tabs (Off / 10 / 30 / 60 min), Include pinned tabs\n',
         '    omniTspSettingsRows(p); // OMNI_TAB_SLEEP_V1: Sleep idle tabs (Off / 10 / 30 / 60 min), Include pinned tabs\n'
         '    omniTxcSettingsRows(p); /* OMNI_TAB_AUTOCLOSE_V1: Close unused tabs (Off / 7 / 14 / 30 days) */\n'),
        ('    case OmniTabSleep::kRowMinutes: case OmniTabSleep::kRowPinned: return omniTspSettingsInput(r.id, b); // OMNI_TAB_SLEEP_V1\n',
         '    case OmniTabAutoClose::kRowDays: return omniTxcSettingsInput(b); /* OMNI_TAB_AUTOCLOSE_V1 */\n'
         '    case OmniTabSleep::kRowMinutes: case OmniTabSleep::kRowPinned: return omniTspSettingsInput(r.id, b); // OMNI_TAB_SLEEP_V1\n'),
        ('    omniTspTick(now);   // OMNI_TAB_SLEEP_V1: idle background tabs: one check a minute, at most 2 per check\n',
         '    omniTspTick(now);   // OMNI_TAB_SLEEP_V1: idle background tabs: one check a minute, at most 2 per check\n'
         '    omniTxcTick(now);   /* OMNI_TAB_AUTOCLOSE_V1: last-shown times; unused tabs closed at start and hourly */\n'),
    ],
    'OmniTabsPage.h': [
        ('    omniTspForget(&tab); // OMNI_TAB_SLEEP_V1: its idle / asleep state\n',
         '    omniTspForget(&tab); // OMNI_TAB_SLEEP_V1: its idle / asleep state\n'
         '    omniTxcForget(&tab); /* OMNI_TAB_AUTOCLOSE_V1: its last-shown time */\n'),
    ],
}
NEEDS = (('OmniFeatures3.h', 'OMNI_TAB_SLEEP_V1', 'apply_tab_sleep.py'),
         ('OmniFeatures3.h', 'OMNI_PINNED_TABS_V1', 'apply_pinned_tabs.py'),
         ('OmniBrowser.cpp', 'OMNI_TAB_GROUPS_V1', 'apply_tab_groups.py'),
         ('OmniFeatures3.h', 'OMNI_TAB_AUDIO_V1', 'apply_tab_audio.py'),
         ('OmniTabsPage.h', 'OMNI_TAB_SLEEP_V1', 'apply_tab_sleep.py'))


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
# "kRowX = 387", "RowId = 387", "case 387", "id = 387" (not a bare number in a list of other patches' ranges).
ROW_ASSIGN = re.compile(r'(?:=\s*|\bcase\s+)%s(?![\w.])' % ROW_ID)


def ids_free():
    """Before the first apply: no engine file and no other apply_*.py may use our row id / names."""
    if any(MARK in (root / n).read_bytes().decode('utf-8') for n in EDITS):
        return
    me = Path(__file__).resolve()
    word = re.compile(r'(?<![\w.])%s(?![\w.])' % ROW_ID)
    names = re.compile('|'.join(NAMES))
    for f in sorted(HERE.glob('apply_*.py')):
        if f.resolve() == me:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        t = code_only(f.read_text(encoding='utf-8', errors='replace'))
        m = names.search(t) or ROW_ASSIGN.search(t)
        if m:
            sys.exit('%s already uses %r (line %d): pick other ids / names' % (f.name, m.group(0), t.count('\n', 0, m.start()) + 1))
    for d in (root, root.parent / 'media'):
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.name in OURS or f.suffix not in ('.h', '.cpp', '.inc'):
                continue
            c = cpp_code(f.read_bytes().decode('utf-8', errors='replace'))
            m = word.search(c) or (None if f.name in GUIDE else names.search(c))
            if m:
                sys.exit('%s already uses %r (line %d): pick other ids / names' % (f.name, m.group(0), c.count('\n', 0, m.start()) + 1))


def main():
    if not PURE.exists():
        sys.exit('%s missing (it ships next to this script)' % PURE)
    pure = PURE.read_bytes().decode('utf-8')
    if MARK not in pure:
        sys.exit('OmniTabAutoClose.h: %s missing' % MARK)
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
    msgs = [write_new('OmniTabAutoClose.h', pure, 'OmniTabSleep.h'),
            write_new('OmniTabAutoCloseShell.h', SHELL, 'OmniTabSleepShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
