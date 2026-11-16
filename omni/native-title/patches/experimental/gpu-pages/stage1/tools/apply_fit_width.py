#!/usr/bin/env python3
"""OMNI_FIT_WIDTH_V1 (2026-11-16): "Fit page to screen width" (backlog E10): one press sets this site's zoom so the
page fills the TV without scrolling sideways.

What the user sees
  - The page menu (hold Cross on a page, no link / picture under the pointer): a row "Fit page to screen width" after
    "Show QR code" (disabled on omni:// / about: / new-tab pages and on a crashed tab).
  - Options: a row "Fit to screen width" right after the zoom row ("Zoom (this site)  < 110% >"; in the older 3-column
    grid after Zoom out / Zoom in / Reset zoom). With the OMNI_MQ_NATIVE_V1 groups it sits in Quick toggles next to the
    zoom row. Detail: "Largest zoom without sideways scrolling".
  Cross: one short script in the page measures the content (below); the site zoom (OMNI_SITE_ZOOM_V1) becomes the
  largest of its steps (50 67 75 80 90 100 110 125 150 175 200 %) at which that content fits the view width, and a
  notice says so:
      "Zoom 125% (fits the screen)"
      "Zoom 200% (the largest; the page is still narrower than the screen)"
      "Zoom 50% (the smallest; the page is still wider than the screen)"
      "This page already fills the screen width (zoom 100%)"     (a fluid page: nothing changes)
      "Couldn't measure this page" (no answer, a crashed tab)
  Remembered for this site: the zoom goes through site zoom's own store (omniSiteZoom, /data/omni/site-zoom.txt via
  omniPrefsSave, the default zoom = no entry), exactly as a D-pad step does, and every open tab of the host follows.
  Private tabs behave as site zoom does for them (OmniBrowser's omniZoomStep stores the host there too).
  The menu row of the Options list stays open (as the zoom row); the page menu closes.

How it measures (one WKPageEvaluateJavaScriptInMainFrame; main frame only; at most 900 elements looked at):
  v = documentElement.clientWidth (CSS px at the current zoom), s = max(documentElement / body scrollWidth),
  c = the horizontal extent of the content: from <body>, an element as wide as the view (98 %) is a wrapper and its
  children are looked at instead (8 levels deep at most; deeper, or with its own text, it counts as full width); a
  narrower one counts with its box (clipped to the scrollable width; display:none, position:fixed, visibility:hidden
  and boxes outside the page are skipped). A page that already scrolls sideways (s > v) uses max(s, c).
  At zoom s the view is v * z / s CSS px wide (z = the live page zoom / (displayScale * omniPageScale)), so the largest
  step s with c * s <= v * z (0.5 % slack for rounding) fits; none: 50 %; above 200 % only 200 % is offered.
  c >= 97 % of v with no sideways scroll: the page is fluid (it reflows to any width): nothing to fit.
The answer is used only when the same tab is still alive and on the same address; the zoom is set for the host the
press was made on.

Pure part: engine/entry/OmniFitWidth.h (no SDL / WebKit; includes OmniSiteZoom.h for the steps): the page script, its
answer, the step choice, the notice texts, the row ids. Tested by tools/test_fit_width.cpp:
    g++ -std=c++20 -Wall -Wextra -Werror -I<tree>/engine/entry test_fit_width.cpp -o t && ./t
  (./t --emit <file> writes the page script for node --check <file>).
Shell side: engine/entry/OmniFitWidthShell.h (included from OmniFeatures3.h after OmniQrShareShell.h), alias OFW,
names omniFw*. Ids: page menu row 9785, Options row 9786 (unused in the tree and in every sibling's code, checked
again before the first apply; the Options hook sits before the `r.id >= 900` line).

Anchors (whole lines, exactly once each; new lines inserted after them, before for the Options row; CRLF / LF kept):
  OmniBrowser.cpp     the OmniSiteZoom.h include line (pure include after it).
  OmniContextMenu.h   the omniQrContextAction declaration (ours after it); the omniQrContextRow(p) call (row after);
                      the omniQrContextAction input line (input after).
  OmniQuickMenu.h     the omniBflQuickAction declaration (ours after); the Reader view add() line of the quick menu
                      (our row before it, i.e. right after the zoom row / tiles); the OMNI_SITE_ZOOM_V1 omniMqGroup case
                      (Quick toggles case after); the omniCfQuickAction input line (input after).
  OmniFeatures3.h     the OmniQrShareShell.h include line (shell include after).
Apply AFTER apply_site_zoom.py, apply_qr_share.py, apply_bf_list.py and apply_colour_filter.py (their lines are anchors;
checked). usage: apply_fit_width.py <engine tree>   (idempotent: re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_FIT_WIDTH_V1'
HERE = Path(__file__).resolve().parent
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('9785', '9786')
NAMES = (r'\bOFW\b', r'\bomniFw[A-Z]', 'OmniFitWidth', 'OMNI_FIT_WIDTH')

PURE = r'''// OMNI_FIT_WIDTH_V1: "Fit page to screen width", the pure part (no SDL, no WebKit). The shell side is
// OmniFitWidthShell.h; the reasons are in tools/apply_fit_width.py. Tested on the host with g++ (test_fit_width.cpp).
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <string>
#include "OmniSiteZoom.h"

namespace OmniFitWidth {

constexpr int kContextId = 9785;   // page menu (hold Cross) row
constexpr int kQuickId = 9786;     // Options row (after the zoom row)
constexpr double kSlack = 1.005;   // rounding: a step that fits within 0.5 % counts
constexpr double kFluid = 0.97;    // content this close to the view width (no sideways scroll): a fluid page

// The page script (WKPageEvaluateJavaScriptInMainFrame): JSON {"v":view,"c":content,"s":scrollWidth}, CSS px at the
// current zoom; "" when there is no document. Used whole (an expression, nothing appended or cut).
inline const char* script()
{
    return R"JS((function(){try{var w=window,d=document,de=d.documentElement,b=d.body;if(!de||!b)return'';
var v=de.clientWidth||w.innerWidth||0,s=Math.max(de.scrollWidth||0,b.scrollWidth||0),lim=Math.max(v,s),full=v*0.98,n=0,lo=1e9,hi=-1e9,sx=w.scrollX||w.pageXOffset||0;
function add(L,R){if(L<lo)lo=L;if(R>hi)hi=R;}
function own(e){for(var t=e.firstChild;t;t=t.nextSibling)if(t.nodeType===3&&/\S/.test(t.data))return true;return false;}
function walk(e,dp){if(++n>900)return;var st=w.getComputedStyle(e);if(!st||st.display==='none'||st.position==='fixed')return;
var r=e.getBoundingClientRect(),L=Math.max(r.left+sx,0),R=Math.min(r.right+sx,lim);if(R-L<2)return;
if(R-L>=full){if(dp>=8||own(e)){if(st.visibility!=='hidden')add(L,R);return;}for(var c=e.firstElementChild;c;c=c.nextElementSibling)walk(c,dp+1);return;}
if(st.visibility==='hidden')return;add(L,R);}
walk(b,0);
return JSON.stringify({v:Math.round(v),c:Math.round(hi>lo?hi-lo:0),s:Math.round(s)});}catch(err){return'';}})())JS";
}

struct Measure {
    bool ok = false;
    double view = 0, content = 0, scroll = 0;   // CSS px at the zoom the page had
};
inline bool number(const std::string& j, const char* key, double& out)
{
    const std::string k = std::string("\"") + key + "\":";
    const size_t i = j.find(k);
    if (i == std::string::npos) return false;
    const char* s = j.c_str() + i + k.size();
    char* end = nullptr;
    out = std::strtod(s, &end);
    return end != s && std::isfinite(out);
}
inline Measure parse(const std::string& json)
{
    Measure m;
    if (!number(json, "v", m.view) || !number(json, "c", m.content) || !number(json, "s", m.scroll)) return m;
    m.ok = m.view >= 1 && m.content >= 0 && m.scroll >= 0 && m.view < 1e6 && m.content < 1e7 && m.scroll < 1e7;
    return m;
}

enum class Kind { Fits, Largest, StillWide, Fills, Unknown };
struct Fit {
    Kind kind = Kind::Unknown;
    int percent = 0;   // the step to set (Fills / Unknown: nothing to set)
};

// currentPercent: the zoom the page was measured at (the live page zoom / the base scale, x 100).
inline Fit choose(const Measure& m, double currentPercent)
{
    Fit f;
    if (!m.ok || !(currentPercent > 0) || !std::isfinite(currentPercent)) return f;
    const bool scrolls = m.scroll > m.view + 1;
    const double c = scrolls ? std::max(m.scroll, m.content) : m.content;
    if (!scrolls && (c < 1 || c >= m.view * kFluid)) {   // fluid (or empty): it reflows to any width
        f.kind = Kind::Fills;
        f.percent = int(std::lround(currentPercent));
        return f;
    }
    const double limit = currentPercent * m.view / c * kSlack;   // the largest zoom at which c still fits
    int best = 0;
    for (int s : OmniSiteZoom::kSteps) if (s <= limit) best = s;
    if (!best) { f.kind = Kind::StillWide; f.percent = OmniSiteZoom::kMin; return f; }
    f.percent = best;
    f.kind = best == OmniSiteZoom::kMax && limit > OmniSiteZoom::kMax * 1.05 ? Kind::Largest : Kind::Fits;
    return f;
}

inline std::string notice(const Fit& f)
{
    const std::string p = std::to_string(f.percent) + "%";
    switch (f.kind) {
    case Kind::Fits: return "Zoom " + p + " (fits the screen)";
    case Kind::Largest: return "Zoom " + p + " (the largest; the page is still narrower than the screen)";
    case Kind::StillWide: return "Zoom " + p + " (the smallest; the page is still wider than the screen)";
    case Kind::Fills: return "This page already fills the screen width (zoom " + p + ")";
    default: return "Couldn't measure this page";
    }
}

} // namespace OmniFitWidth
'''

SHELL = r'''// OMNI_FIT_WIDTH_V1: "Fit page to screen width" (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's
// anonymous namespace, after OmniQrShareShell.h). The pure part is OmniFitWidth.h; the reasons are in
// tools/apply_fit_width.py. The zoom goes through site zoom (OMNI_SITE_ZOOM_V1): omniSiteZoom, omniPrefsSave,
// omniApplySiteZoom. Main thread only.
#pragma once

namespace OFW = OmniFitWidth;

struct OmniFwAsk {
    const void* tab;
    std::string url, host;
    double percent;   // the zoom the page was measured at
};

static void omniFwApply(const OmniFwAsk& q, const std::string& answer)
{
    const OFW::Fit f = OFW::choose(OFW::parse(answer), q.percent);
    if (f.kind == OFW::Kind::Unknown || f.kind == OFW::Kind::Fills) { notice(OFW::notice(f)); return; }
    const int def = OmniSiteZoom::toPercent(omniFxDefaultZoom());   // as omniZoomStep: the default zoom is no entry
    if (f.percent == def) omniSiteZoom.erase(q.host); else omniSiteZoom.set(q.host, f.percent);
    omniPrefsSave();
    for (auto& t : tabs) if (omniBlockerHostOf(t->url) == q.host) omniApplySiteZoom(t.get());
    omniPageDirty = true;
    omniShellDirty = true;
    notice(OFW::notice(f));
}

static void omniFwStart()
{
    Tab* t = active();
    const std::string host = omniMenuHost();
    if (!t || host.empty() || t->crashed) { notice("Fit to width works on web pages"); return; }
    const double base = displayScale * omniPageScale, z = WKPageGetPageZoomFactor(t->page);
    const double percent = base > 0 && z > 0 ? z / base * 100 : omniZoomFor(host) * 100;
    auto src = adoptWK(WKStringCreateWithUTF8CString(OFW::script()));
    auto* q = new OmniFwAsk { t, t->url, host, percent };
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), q, [](WKTypeRef result, WKErrorRef error, void* ctx) {
        std::unique_ptr<OmniFwAsk> a(static_cast<OmniFwAsk*>(ctx));
        if (!omniTabAlive(a->tab)) return;
        const Tab* tab = static_cast<const Tab*>(a->tab);
        if (tab->url != a->url) return;   // navigated meanwhile: the measure is of another page
        omniFwApply(*a, omniFxResultString(result, error));
    });
}

// --- hold-Cross page menu ------------------------------------------------------------------------------------------
static void omniFwContextRow(OmniFxPanel& p)
{
    Tab* t = active();
    OmniFxRow r; r.id = OFW::kContextId; r.label = "Fit page to screen width";
    r.enabled = t && !t->crashed && !omniMenuHost().empty();
    p.rows.push_back(r);
}
static bool omniFwContextAction(int id)
{
    if (id != OFW::kContextId) return false;
    omniFxCloseAll();
    omniFwStart();
    return true;
}

// --- Options: after the zoom row (stays open, as the zoom row does) ------------------------------------------------
static void omniFwQuickRow(OmniFxPanel& p)
{
    Tab* t = active();
    OmniFxRow r; r.id = OFW::kQuickId; r.label = "Fit to screen width";
    r.enabled = t && !t->crashed && !omniMenuHost().empty();
    if (r.enabled) r.detail = "Largest zoom without sideways scrolling";
    p.rows.push_back(r);
}
static bool omniFwQuickAction(const OmniFxRow& r, int b)
{
    if (r.id != OFW::kQuickId) return false;
    if (b == SDL_CONTROLLER_BUTTON_A && r.enabled) omniFwStart();
    return b == SDL_CONTROLLER_BUTTON_A;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSiteZoom.h" // OMNI_SITE_ZOOM_V1: zoom steps, host keys, site-zoom.txt (pure)\n',
         '#include "OmniSiteZoom.h" // OMNI_SITE_ZOOM_V1: zoom steps, host keys, site-zoom.txt (pure)\n'
         '#include "OmniFitWidth.h" // OMNI_FIT_WIDTH_V1: Fit page to screen width (pure: script, step choice)\n'),
    ],
    'OmniContextMenu.h': [
        ('static bool omniQrContextAction(int id);\n',
         'static bool omniQrContextAction(int id);\n'
         'static void omniFwContextRow(OmniFxPanel& p); // OMNI_FIT_WIDTH_V1 (OmniFitWidthShell.h)\n'
         'static bool omniFwContextAction(int id); // OMNI_FIT_WIDTH_V1\n'),
        ('        omniQrContextRow(p); // OMNI_QR_SHARE_V1: Show QR code\n',
         '        omniQrContextRow(p); // OMNI_QR_SHARE_V1: Show QR code\n'
         '        omniFwContextRow(p); // OMNI_FIT_WIDTH_V1: Fit page to screen width\n'),
        ('    if (omniQrContextAction(r.id)) return true; // OMNI_QR_SHARE_V1\n',
         '    if (omniQrContextAction(r.id)) return true; // OMNI_QR_SHARE_V1\n'
         '    if (omniFwContextAction(r.id)) return true; // OMNI_FIT_WIDTH_V1\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniBflQuickAction(int id); // OMNI_BF_LIST_V1\n',
         'static bool omniBflQuickAction(int id); // OMNI_BF_LIST_V1\n'
         'static void omniFwQuickRow(OmniFxPanel& p); // OMNI_FIT_WIDTH_V1 (OmniFitWidthShell.h): Fit to screen width\n'
         'static bool omniFwQuickAction(const OmniFxRow& r, int b); // OMNI_FIT_WIDTH_V1\n'),
        ('    add(omniQmReader, "Reader view", page);\n',
         '    omniFwQuickRow(p); // OMNI_FIT_WIDTH_V1: Fit to screen width (after the zoom row / tiles)\n'
         '    add(omniQmReader, "Reader view", page);\n'),
        ('    case omniMqBlock: case 303: case omniQmZoomReset: return 2; // existing omniF3Dark; OMNI_SITE_ZOOM_V1: zoom row\n',
         '    case omniMqBlock: case 303: case omniQmZoomReset: return 2; // existing omniF3Dark; OMNI_SITE_ZOOM_V1: zoom row\n'
         '    case OmniFitWidth::kQuickId: return 2; // OMNI_FIT_WIDTH_V1: Quick toggles, next to the zoom row\n'),
        ('    if (omniCfQuickAction(r.id)) return true; // OMNI_COLOUR_FILTER_V1 (before the >= 900 rows)\n',
         '    if (omniCfQuickAction(r.id)) return true; // OMNI_COLOUR_FILTER_V1 (before the >= 900 rows)\n'
         '    if (omniFwQuickAction(r, b)) return true; // OMNI_FIT_WIDTH_V1 (before the >= 900 rows)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniQrShareShell.h" // OMNI_QR_SHARE_V1\n',
         '#include "OmniQrShareShell.h" // OMNI_QR_SHARE_V1\n'
         '#include "OmniFitWidthShell.h" // OMNI_FIT_WIDTH_V1 (uses site zoom and the page menu)\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_SITE_ZOOM_V1',),
         'OmniContextMenu.h': ('OMNI_QR_SHARE_V1',),
         'OmniQuickMenu.h': ('OMNI_SITE_ZOOM_V1', 'OMNI_BF_LIST_V1', 'OMNI_COLOUR_FILTER_V1'),
         'OmniFeatures3.h': ('OMNI_QR_SHARE_V1',)}


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


def ids_free():
    """Before a first apply: no other patch or tree file uses this patch's ids or names."""
    word = re.compile(r'\b(%s)\b' % '|'.join(IDS))
    name = re.compile('|'.join(NAMES))
    mine = {'OmniFitWidth.h', 'OmniFitWidthShell.h'}
    # A sibling not applied to this tree yet still owns its ids: its code (generated headers / edits included,
    # comments and docstring stripped) assigning one of ours to a row id ("kRowId = 9785", "kContextId = 9785",
    # "r.id = 9785", "constexpr int x = 9785") is a clash.
    assign = re.compile(r'(?:\b\w*(?:[Rr]ow|[Ii]d)\w*|\bconstexpr\s+int\s+\w+)\s*=\s*(%s)(?![\w.])' % '|'.join(IDS))
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        t = code_only(f.read_text(encoding='utf-8', errors='replace'))
        m = name.search(t) or assign.search(t)   # bare numbers: not looked for (siblings' notes list others' ids)
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
    msgs = [write_new('OmniFitWidth.h', PURE, 'OmniSiteZoom.h'),
            write_new('OmniFitWidthShell.h', SHELL, 'OmniQrShareShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
