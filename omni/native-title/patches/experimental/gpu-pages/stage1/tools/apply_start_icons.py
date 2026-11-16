#!/usr/bin/env python3
"""OMNI_START_ICONS_V1 (2026-11-16): real site icons on the omni://pages start page.

What the user sees
  The start page (omni://pages/start/, pages bundle start/) shows the site's own icon - the one OMNI_FAVICONS_V1
  captured into /data/omni/icons - instead of / beside the coloured letter on: Pinned sites and Recent sites tiles,
  Continue watching tiles, Web apps tiles, and the Reading list / Recently closed tiles (OMNI_START_CUSTOM_V1). No icon
  cached for a site (or anything failing) = exactly what was there before (the letter / the plain tile): the page
  swaps the letter for the icon only once the image has loaded.

Why this way (studied first)
  - The start page's CSP (index.html's <meta> and OmniBlocker.cpp's pagesCSP) allows images from 'self' and data:
    only; remote icons are out, and the page never reads files. It already gets two things from Omni's memory through
    the omni://pages scheme handler: _user/start-bg.png (OMNI_START_CUSTOM_V1) and _user/pdf/<token>.pdf
    (OMNI_PDF_VIEWER_V1). This adds a third route next to them:
        omni://pages/_user/icon/<16 lowercase hex>.png
    'self' already covers it: NO CSP change (index.html: img-src 'self' data:; pagesCSP: img-src 'self' data: blob:).
  - The route (OmniBlocker.cpp, before the _user/pdf/ branch) serves ONLY:
      * a name matching ^[0-9a-f]{16}\\.png$ exactly (OmniFavicons::isIconFileName; pagesRelPath has already refused
        "..", "\\\\", NUL, empty / hidden segments and decoded %xx, so "_user/icon/../x" never gets here); nothing else
        under _user/icon/ (no sub folders, no query: pagesRelPath drops ?# before the check);
      * to the main frame of a document whose origin is omni://pages and whose address starts with
        omni://pages/start/ (the start page; web content can't load omni://pages at all: omniPagesAllow);
      * through the shell's callback (omniPagesSetIconFile, OmniStartIconsShell.h): the tab must be a built-in-pages
        tab, the name must be in OMNI_FAVICONS_V1's DISK index (omniFavIndex), and the file read (<= 16 KB) must be a
        32 x 32 PNG by OmniFavicons::isPng32. So private-tab icons (omniFavPriv, memory only) and "Don't save history"
        icons (omniFavMem only, never written) are never served; icons removed by Clear history / Delete site are gone
        from the index at once (their unlink is queued) and are refused from then on. (This tree has no guest mode.)
      * as image/png with pagesCSP, nosniff, Cache-Control no-cache. Anything else: a quiet 404 (no log line: a site
        with no cached icon is the normal case).
  - The icon key is OMNI_FAVICONS_V1's own: fnv1a64(hostKey(url)) as 16 hex digits (OmniFavicons::fileName without
    ".png"), computed by the new pure header OmniStartIcons.h from OmniFavicons.h itself (one implementation).
    Engine -> page hand-off: an "icon" field (only when the address has a host key) in the three fixed data scripts:
      OmniCw::pageJson (Continue watching items, from the page address), OmniStartCustom::pageJson (reading entries
      from their site, closed tabs from their address) and OmniWebApps::pageJson (apps, from their start address: the
      page still gets no address, only the key).
    Pinned / Recent sites live in the page's own localStorage (pins.js / app.js), which Omni never sees: the bundle's
    start/start-icons.js computes the same key in JavaScript (a byte-for-byte port of hostKey + FNV-1a 64; tested
    against the C++ vectors by tools/test_start_icons_js.cjs).
  - Continue watching's tiles are drawn by Omni's own script (OmniContinueWatchingShell.h's omniCwScript): its letter
    line now hands the letter element to window.omniStartIcons.attach (start-icons.js) when that exists; on the old
    data: new-tab page (pages off) nothing changes.

Files
  new  OmniStartIcons.h        pure: key / siteKey / field / validKey / fileFromRel / startPage / isPng (tests:
                               tools/test_start_icons.cpp)
  new  OmniStartIconsShell.h   omniSicIconFile: the route's callback (disk index + file read + PNG check)
  OmniBlocker.h     after omniPagesSetPdfFile's declaration: OmniPagesIconFileFn + omniPagesSetIconFile
  OmniBlocker.cpp   after the OmniUBlockFrames.h include: the pure include; after pagesPdfFile's variable: pagesIconFile;
                    before the _user/pdf/ branch: the _user/icon/ branch; after omniPagesSetPdfFile's definition: ours
  OmniPages.h       omniPagesInit's omniPagesRefreshBridge() line: the callback registered after it (before any start
                    page can load, so the first start page's images find the route)
  OmniFeatures3.h   after the OmniFaviconsShell.h include: the shell
  OmniContinueWatching.h  before "namespace OmniCw {": the pure include; the item's "left" line: + the icon field
  OmniStartCustom.h       before "namespace OmniStartCustom {": the include; the reading / closed item lines: + icon
  OmniWebApps.h           before "namespace OmniWebApps {": the include; the app item line: + icon
  OmniContinueWatchingShell.h  before omniCwScript: a note; its letter line: + the icon (start-icons.js attach)
  Pages bundle (repo, not this script): omnibloom/omni/pages/bundle-clean4/start/{start-icons.js (new), index.html
  (its <script> only; CSP untouched), start-custom.js/.css, start-webapps.js/.css, pins.js, app.js (a data-osic-url
  attribute on the Pinned / Recent buttons)}. Tests: tools/test_start_icons.cpp (g++), tools/test_start_icons_js.cjs
  (node).
Alias OSIC, names omniSic* / omniPagesSetIconFile / pagesIconFile (refused when the tree already uses them). No ids.
Each anchor exactly once, CRLF / LF kept per file, idempotent (MARK per file), /* */ comments only on anchored lines.
Apply after apply_favicons.py, apply_start_custom.py, apply_pdf_viewer.py, apply_web_apps.py and
apply_continue_watching.py.
usage: apply_start_icons.py <engine tree>   (re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_START_ICONS_V1'
HERE = Path(__file__).resolve().parent
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_START_ICONS_V1: site icons on the omni://pages start page, the pure part (no SDL, no WebKit).
// The key of a site's icon is OMNI_FAVICONS_V1's file name without ".png": fnv1a64(hostKey(url)) in 16 lowercase hex
// digits. The start page gets it per tile ("icon" in the data scripts; start-icons.js computes the same for Pinned /
// Recent sites) and loads omni://pages/_user/icon/<key>.png, which OmniBlocker.cpp's pages handler serves from the
// favicon DISK cache only (OmniStartIconsShell.h). Reasons: tools/apply_start_icons.py. Tests: tools/test_start_icons.cpp.
#pragma once
#include <string>
#include <vector>
#include "OmniFavicons.h"

namespace OmniStartIcons {

constexpr const char* kRoute = "_user/icon/";                 // under omni://pages/ (the handler's relative path)
constexpr const char* kStartPrefix = "omni://pages/start/";   // the only document the route answers

inline bool validKey(const std::string& k)
{
    if (k.size() != 16) return false;
    for (char c : k) if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
    return true;
}
// A page address -> its icon key ("" for anything without a host key: not http(s), odd hosts).
inline std::string key(const std::string& url)
{
    const std::string n = OmniFavicons::fileName(OmniFavicons::hostKey(url));
    return n.size() == 20 ? n.substr(0, 16) : std::string();
}
// A bare site ("example.com", as the reading list shows it) -> its icon key.
inline std::string siteKey(const std::string& site)
{
    if (site.empty() || site.size() > 253 || site.find_first_of("/?#@\\ ") != std::string::npos) return std::string();
    return key("https://" + site + "/");
}
// ,"icon":"<key>"  for a JSON object ("" when there is no key; the key is hex: nothing to escape).
inline std::string field(const std::string& k) { return validKey(k) ? ",\"icon\":\"" + k + "\"" : std::string(); }
// The handler's relative path (already decoded and checked by pagesRelPath) -> the icon file name; "" refused.
// Exactly "_user/icon/" + 16 lowercase hex + ".png": no sub folders, no other names.
inline std::string fileFromRel(const std::string& rel)
{
    const std::string pre = kRoute;
    if (rel.size() != pre.size() + 20 || rel.compare(0, pre.size(), pre) != 0) return std::string();
    const std::string name = rel.substr(pre.size());
    return OmniFavicons::isIconFileName(name) ? name : std::string();
}
// The requesting document is the start page (omni://pages/start/...).
inline bool startPage(const std::string& docURL) { return docURL.compare(0, std::string(kStartPrefix).size(), kStartPrefix) == 0; }
// What may go out: a 32 x 32 PNG as OMNI_FAVICONS_V1 stores them.
inline bool isPng(const std::vector<uint8_t>& b) { return OmniFavicons::isPng32(std::string(b.begin(), b.end())); }

} // namespace OmniStartIcons
'''

SHELL = r'''// OMNI_START_ICONS_V1: site icons on the start page (shell side). Included from OmniFeatures3.h after
// OmniFaviconsShell.h (inside OmniBrowser.cpp's anonymous namespace). The pure part is OmniStartIcons.h; the reasons are
// in tools/apply_start_icons.py. OmniBlocker.cpp's pages handler (main thread) asks omniSicIconFile for
// omni://pages/_user/icon/<key>.png after checking the name and that the requesting document is the start page.
#pragma once

namespace OSIC = OmniStartIcons;

// Only icons in the favicon DISK cache: private-tab icons (omniFavPriv) and "Don't save history" ones (omniFavMem
// without a file) are never in omniFavIndex, so they are never served. One <= 16 KB file read per tile.
static bool omniSicIconFile(WKPageRef page, const std::string& name, std::vector<uint8_t>& data)
{
    if (!OFAV::isIconFileName(name)) return false;
    Tab* t = omniTabForPage(page);
    if (!t || !t->omniPagesTab || t->crashed) return false;
    omniFavScan();
    if (!omniFavIndex.has(name)) return false;
    std::string png;
    if (FILE* f = fopen((omniFavDir() + name).c_str(), "rb")) {
        char buf[4096];
        size_t n;
        while (png.size() <= OFAV::kMaxPngBytes && (n = fread(buf, 1, sizeof buf, f)) > 0) png.append(buf, n);
        fclose(f);
    }
    if (!OFAV::isPng32(png)) return false;   // not written yet (the writer thread) / damaged: the letter stays
    data.assign(png.begin(), png.end());
    omniFavIndex.touch(name, (long long)time(nullptr));   // used: kept longer (LRU), as when drawn
    return true;
}
'''

C = '/* ' + MARK + ' */'
EDITS = {
    'OmniBlocker.h': [
        ('void omniPagesSetPdfFile(OmniPagesUserFileFn fn); /* OMNI_PDF_VIEWER_V1: omni://pages/_user/pdf/<token>.pdf */\n',
         'void omniPagesSetPdfFile(OmniPagesUserFileFn fn); /* OMNI_PDF_VIEWER_V1: omni://pages/_user/pdf/<token>.pdf */\n'
         '/* ' + MARK + ': omni://pages/_user/icon/<16 hex>.png for the start page: the bytes of a cached site icon (false: none) */\n'
         'using OmniPagesIconFileFn = bool (*)(WKPageRef page, const std::string& name, std::vector<uint8_t>& data);\n'
         'void omniPagesSetIconFile(OmniPagesIconFileFn fn); ' + C + '\n'),
    ],
    'OmniBlocker.cpp': [
        ('#include "OmniUBlockFrames.h" // OMNI_UBLOCK_FRAMES_V1\n',
         '#include "OmniUBlockFrames.h" // OMNI_UBLOCK_FRAMES_V1\n'
         '#include "OmniStartIcons.h" /* ' + MARK + ': the _user/icon/ route\'s name and PNG checks (pure) */\n'),
        ('OmniPagesUserFileFn pagesPdfFile = nullptr; /* OMNI_PDF_VIEWER_V1: _user/pdf/<token>.pdf from the shell\'s memory */\n',
         'OmniPagesUserFileFn pagesPdfFile = nullptr; /* OMNI_PDF_VIEWER_V1: _user/pdf/<token>.pdf from the shell\'s memory */\n'
         'OmniPagesIconFileFn pagesIconFile = nullptr; /* ' + MARK + ': _user/icon/<key>.png from the favicon disk cache */\n'),
        ('        if (rel.rfind("_user/pdf/", 0) == 0) { /* OMNI_PDF_VIEWER_V1: a PDF the shell holds (the reader fetches it same-origin) */\n',
         '        if (rel.rfind("_user/icon/", 0) == 0) { /* ' + MARK + ': a cached site icon, for the start page only */\n'
         '            std::vector<uint8_t> bytes;\n'
         '            const std::string name = OmniStartIcons::fileFromRel(rel);\n'
         '            if (name.empty() || !pagesIconFile || !frame.isMainFrame() || frameOrigin != "omni://pages"\n'
         '                || !OmniStartIcons::startPage(pagesStd(frame.request().url().string()))\n'
         '                || !pagesIconFile(WebKit::toAPI(&page), name, bytes) || !OmniStartIcons::isPng(bytes)) {\n'
         '                task.didComplete(WebCore::ResourceError(WTF::String::fromLatin1("OmniPages"), 404, wurl, WTF::String::fromLatin1("no icon"))); /* quiet: no icon cached is normal */\n'
         '                return;\n'
         '            }\n'
         '            WebCore::ResourceResponse response { WTF::URL { wurl }, WTF::String::fromLatin1("image/png"), static_cast<long long>(bytes.size()), WTF::String() };\n'
         '            response.setHTTPStatusCode(200);\n'
         '            response.setHTTPHeaderField(WebCore::HTTPHeaderName::ContentSecurityPolicy, WTF::String::fromLatin1(pagesCSP));\n'
         '            response.setHTTPHeaderField(WTF::String::fromLatin1("X-Content-Type-Options"), WTF::String::fromLatin1("nosniff"));\n'
         '            response.setHTTPHeaderField(WTF::String::fromLatin1("Cache-Control"), WTF::String::fromLatin1("no-cache"));\n'
         '            task.didReceiveResponse(WTF::move(response));\n'
         '            task.didReceiveData(WebCore::SharedBuffer::create(std::span<const uint8_t>(bytes.data(), bytes.size())));\n'
         '            task.didComplete(WebCore::ResourceError());\n'
         '            return;\n'
         '        }\n'
         '        if (rel.rfind("_user/pdf/", 0) == 0) { /* OMNI_PDF_VIEWER_V1: a PDF the shell holds (the reader fetches it same-origin) */\n'),
        ('void omniPagesSetPdfFile(OmniPagesUserFileFn fn) { pagesPdfFile = fn; } /* OMNI_PDF_VIEWER_V1 */\n',
         'void omniPagesSetPdfFile(OmniPagesUserFileFn fn) { pagesPdfFile = fn; } /* OMNI_PDF_VIEWER_V1 */\n'
         'void omniPagesSetIconFile(OmniPagesIconFileFn fn) { pagesIconFile = fn; } ' + C + '\n'),
    ],
    'OmniPages.h': [
        ('    omniPagesRefreshBridge();\n',
         '    omniPagesRefreshBridge();\n'
         '    omniPagesSetIconFile(omniSicIconFile); /* ' + MARK + ': omni://pages/_user/icon/<key>.png (start page; favicon disk cache) */\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniFaviconsShell.h" // OMNI_FAVICONS_V1: site icons (capture, cache, drawing; after the strips and panels it draws in)\n',
         '#include "OmniFaviconsShell.h" // OMNI_FAVICONS_V1: site icons (capture, cache, drawing; after the strips and panels it draws in)\n'
         '#include "OmniStartIconsShell.h" /* ' + MARK + ': the start page\'s icon route callback (after OmniFaviconsShell.h) */\n'),
    ],
    'OmniContinueWatching.h': [
        ('namespace OmniCw {\n',
         '#include "OmniStartIcons.h" /* ' + MARK + ': each item\'s "icon" key */\n'
         'namespace OmniCw {\n'),
        ('            + ",\\"left\\":" + jsonQuote(leftText(e.position, e.duration)) + "}";\n',
         '            + ",\\"left\\":" + jsonQuote(leftText(e.position, e.duration)) + OmniStartIcons::field(OmniStartIcons::key(e.url)) + "}"; ' + C + '\n'),
    ],
    'OmniStartCustom.h': [
        ('namespace OmniStartCustom {\n',
         '#include "OmniStartIcons.h" /* ' + MARK + ': reading / closed items\' "icon" key */\n'
         'namespace OmniStartCustom {\n'),
        ('            + ",\\"s\\":" + quote(reading[i].site) + ",\\"d\\":" + quote(reading[i].when) + "}";\n',
         '            + ",\\"s\\":" + quote(reading[i].site) + ",\\"d\\":" + quote(reading[i].when) + OmniStartIcons::field(OmniStartIcons::siteKey(reading[i].site)) + "}"; ' + C + '\n'),
        ('                + ",\\"s\\":" + quote(closed[i].site) + "}";\n',
         '                + ",\\"s\\":" + quote(closed[i].site) + OmniStartIcons::field(OmniStartIcons::key(closed[i].url)) + "}"; ' + C + '\n'),
    ],
    'OmniWebApps.h': [
        ('namespace OmniWebApps {\n',
         '#include "OmniStartIcons.h" /* ' + MARK + ': each app\'s "icon" key (the key only: still no address) */\n'
         'namespace OmniWebApps {\n'),
        ('            + ",\\"c\\":" + quote(c) + ",\\"k\\":" + quote(inkFor(c)) + ",\\"l\\":" + quote(letter(a.name)) + "}";\n',
         '            + ",\\"c\\":" + quote(c) + ",\\"k\\":" + quote(inkFor(c)) + ",\\"l\\":" + quote(letter(a.name)) + OmniStartIcons::field(OmniStartIcons::key(a.url)) + "}"; ' + C + '\n'),
    ],
    'OmniContinueWatchingShell.h': [
        ('static const char* const omniCwScript = R"JS((function(D){\'use strict\';\n',
         '/* ' + MARK + ': the letter element goes to window.omniStartIcons.attach (pages bundle start-icons.js), which swaps in\n'
         '   omni://pages/_user/icon/<it.icon>.png once it has loaded; without it (old bundle, pages off) the letter stays. */\n'
         'static const char* const omniCwScript = R"JS((function(D){\'use strict\';\n'),
        ("top.appendChild(el('i',{flex:'none',width:'42px',height:'42px',borderRadius:'21px',background:'var(--accent,#107c10)',color:'var(--accentInk,#fff)',font:'700 20px sans-serif',display:'flex',alignItems:'center',justifyContent:'center',fontStyle:'normal'},it.l));\n",
         "var ic=el('i',{flex:'none',width:'42px',height:'42px',borderRadius:'21px',background:'var(--accent,#107c10)',color:'var(--accentInk,#fff)',font:'700 20px sans-serif',display:'flex',alignItems:'center',justifyContent:'center',fontStyle:'normal'},it.l);top.appendChild(ic);\n"
         "var SI=window.omniStartIcons;if(pages&&SI&&typeof SI.attach==='function')try{SI.attach(ic,SI.pick(it.icon,it.u))}catch(x){}\n"),
    ],
}
NEEDS = [('OmniFeatures3.h', 'OMNI_FAVICONS_V1', 'apply_favicons.py'),
         ('OmniBlocker.cpp', 'OMNI_START_CUSTOM_V1', 'apply_start_custom.py'),
         ('OmniBlocker.cpp', 'OMNI_PDF_VIEWER_V1', 'apply_pdf_viewer.py'),
         ('OmniPages.h', 'OMNI_WEB_APPS_V1', 'apply_web_apps.py'),
         ('OmniContinueWatchingShell.h', 'OMNI_CONTINUE_WATCHING_V1', 'apply_continue_watching.py')]
NAMES = ('OSIC', 'omniSic', 'OmniStartIcons', 'OMNI_START_ICONS', 'omniPagesSetIconFile', 'pagesIconFile', 'OmniPagesIconFileFn')
MINE = ('OmniStartIcons.h', 'OmniStartIconsShell.h')


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


# Copied from apply_bf_list.py: comments / notes are not uses.
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
    """Before a first apply: no other patch or tree file uses this patch's names (this patch has no numeric ids)."""
    name = re.compile(r'\b(?:%s)' % '|'.join(NAMES))
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        m = name.search(code_only(f.read_text(encoding='utf-8', errors='replace')))
        if m:
            sys.exit('%s already uses %r: pick other names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in MINE or f.name in GUIDE or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        m = name.search(cpp_code(t))
        if m and MARK not in t:
            sys.exit('%s already uses %r: pick other names' % (f.name, m.group(0)))


def main():
    for name, mark, tool in NEEDS:
        if mark not in (root / name).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (name, mark, tool))
    if MARK not in (root / 'OmniBlocker.cpp').read_bytes().decode('utf-8'):
        ids_free()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniStartIcons.h', PURE, 'OmniFavicons.h'),
            write_new('OmniStartIconsShell.h', SHELL, 'OmniFaviconsShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
