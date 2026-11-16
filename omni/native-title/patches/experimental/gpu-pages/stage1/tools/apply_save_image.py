#!/usr/bin/env python3
"""OMNI_SAVE_IMAGE_V1 (2026-11-16): the hold-Cross page menu's "Save image" and "Save link target" go to the Downloads
app, the way a page's regular file download does (OMNI_FILE_DOWNLOADS_V1).

What existed (OMNI_FEATURES_V1, OmniContextMenu.h): the page menu already had "Save link" (over a link) and
"Save image" (over an <img> / <picture>), both through omniFxSaveURL: the tab loads the address and the navigation
ACTION policy (omniFxPolicyDownload) turns that load into WebKit's own download (omniData("downloads/")). That path
never reaches the navigation RESPONSE policy, so OMNI_FILE_DOWNLOADS_V1 did not apply to it. The hit test is a small
read-only page script (omniFxContextScript, document.elementsFromPoint at the pointer); it found <img>/<picture> only.

What the user sees now
  - Over a link: "Save link target" (was "Save link"). Over an image: "Save image". Both are left out for blob:
    addresses (they exist only inside the page; before, the row showed and then said it can't be saved).
  - Cross on either: the address goes to the Downloads app (Downloads tab opens / comes forward with #url=<address>,
    omniMediaDownloadsRequest(false, false, true, link), as file downloads do); notice "Sent to Downloads: <name>"
    (name: the address's last path part, percent-decoded, made file-safe; the host when there is none; long names
    shortened to 28 + "..." + 28). The Downloads app fetches the file; Omni itself fetches nothing new.
  - Kept on WebKit's own save (omniFxSaveURL, unchanged behaviour), the same cases as OMNI_FILE_DOWNLOADS_V1:
    private tabs (private links are never shared with Downloads), "Media downloads" off, non-HTTP(S) or
    credential-bearing addresses (data: images keep WebKit's own save into downloads/, as before), the Downloads tab
    itself, self-test modes.
  - The same address again within 3 s is not sent twice: the notice repeats, no second request. Unlike the page-driven
    file download (which records before asking), only an accepted hand-over is remembered, so a "Media downloads is
    opening" / "could not start" answer can be retried at once.
  - Background images: when no <img>/<picture>/<video> is under the pointer, the page script also takes the first
    http(s) url(...) of an element's computed background-image (not <html>/<body>/<iframe>/<video>, not an element
    covering more than 60% of the viewport, so a page-wide backdrop doesn't replace the page menu). Its title is the
    element's aria-label / title, else "Image".
  - Hit-test fix: omniFxContextQuery cut the last 2 characters of omniFxContextScript to add the call, but the raw
    string ends "})(" (the ")JS\"" delimiter takes the last ')'), so the IIFE's ')' was lost and every probe was a
    SyntaxError -> "{}" -> only the page rows (no link / image / video rows at all). Now only the trailing "(" / "()"
    is cut (checked with node --check on the assembled script).
  - Controls guide row: "Save link target / Save image", note "Page menu; to Downloads when Media downloads is on".

Pure part: engine/entry/OmniSaveImage.h (route, offered, fileName, shown, Recent); tests: tools/test_save_image.cpp.
Shell part: omniSviSave in OmniContextMenu.h (before omniFxCopy; OmniContextMenu.h is included from OmniFeatures.h,
after OmniMediaDownloadsHooks.inc and omniFileDownloadsTake, so omniMediaDownloadsRequest / omniMediaDownloadsEnabled
are declared). Namespace alias OSVI (function scope).
Anchors (each once; whole lines kept, inserted lines before/after them):
  OmniBrowser.cpp     the OmniMediaDownloads.h include line (pure include after it)
  OmniContextMenu.h   'static void omniFxCopy(' line (definition before it); the "Save link" / "Save image" add() lines
                      and their two switch cases (whole lines replaced); the script's VIDEO line (background line after);
                      the 'js.replace(js.size() - 2, 2, ...' line of omniFxContextQuery (replaced: hit-test fix)
Tests: test_save_image.cpp (g++, pure part + OmniMediaSection::validLink); test_save_image_js.cjs <OmniContextMenu.h>
(node: assembles the probe as omniFxContextQuery does, runs it on mock DOMs).
  OmniControlsHelp.h  the "Save link / Save image" row (whole line replaced)
Needs OMNI_FILE_DOWNLOADS_V1 in OmniBrowser.cpp (same rules, same Downloads hand-over).
usage: apply_save_image.py <engine tree>   (anchored, idempotent, keeps CRLF)
"""
import sys
from pathlib import Path

MARK = 'OMNI_SAVE_IMAGE_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_SAVE_IMAGE_V1: the pure part of the page menu's "Save image" / "Save link target" hand-over to the Downloads
// app (no SDL, no WebKit). Shell side: omniSviSave in OmniContextMenu.h; reasons in tools/apply_save_image.py.
// Tested on the host with g++ (tools/test_save_image.cpp).
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>

namespace OmniSaveImage {

constexpr uint32_t kRepeatMs = 3000;   // the same address again within 3 s is not sent twice (as file downloads)
constexpr size_t kShownMax = 60;       // longer notice names keep kShownEnd bytes at each end around "..."
constexpr size_t kShownEnd = 28;

enum class Route { Downloads, WebKit };

// Where the save is asked from. validLink: OmniMediaSection::validLink(url) (http(s), no user@host, no spaces,
// <= 4096 bytes), computed by the shell so the rule is exactly the file-downloads one.
struct Where {
    bool privateTab = false, downloadsTab = false, testMode = false, downloadsOn = false, validLink = false;
};

// OMNI_FILE_DOWNLOADS_V1's rule (omniFileDownloadsTake): Downloads only for a plain http(s) address from a normal tab
// with "Media downloads" on; WebKit's own save everywhere else (private tab, the Downloads tab, self-tests, data:...).
inline Route route(const std::string& url, const Where& w)
{
    if (url.empty() || w.testMode || w.privateTab || w.downloadsTab || !w.validLink || !w.downloadsOn) return Route::WebKit;
    return Route::Downloads;
}

inline bool startsNoCase(const std::string& s, const char* prefix)
{
    size_t i = 0;
    for (; prefix[i]; ++i) {
        if (i >= s.size()) return false;
        char c = s[i];
        if (c >= 'A' && c <= 'Z') c = char(c - 'A' + 'a');
        if (c != prefix[i]) return false;
    }
    return true;
}

// The Save rows are left out for blob: addresses (they exist only inside the page) and empty ones.
inline bool offered(const std::string& url) { return !url.empty() && !startsNoCase(url, "blob:"); }

inline int hexValue(char c)
{
    return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
}
inline std::string percentDecode(const std::string& s)
{
    std::string out;
    out.reserve(s.size());
    for (size_t i = 0; i < s.size(); ++i) {
        const int hi = s[i] == '%' && i + 2 < s.size() ? hexValue(s[i + 1]) : -1, lo = hi >= 0 ? hexValue(s[i + 2]) : -1;
        if (lo >= 0) { out += char(hi * 16 + lo); i += 2; } else out += s[i];
    }
    return out;
}
// As omniSafeFileName: path / reserved characters and controls become '_', no leading dots or spaces, <= 120 bytes.
inline std::string safeName(std::string name)
{
    for (auto& c : name)
        if (c == '/' || c == '\\' || c == ':' || c == '*' || c == '?' || c == '"' || c == '<' || c == '>' || c == '|'
            || static_cast<unsigned char>(c) < 32 || c == 127) c = '_';
    while (!name.empty() && (name[0] == '.' || name[0] == ' ')) name.erase(0, 1);
    while (!name.empty() && name.back() == ' ') name.pop_back();
    if (name.size() > 120) {
        size_t cut = name.size() - 120;
        while (cut < name.size() && (static_cast<unsigned char>(name[cut]) & 0xC0) == 0x80) ++cut;
        name = name.substr(cut);
    }
    return name;
}
// The name the notice shows: the address's last path part (no query / fragment), percent-decoded and file-safe; the
// host when the path has none ("https://example.com/" -> "example.com"); fallback when neither gives a name.
inline std::string fileName(const std::string& url, const char* fallback)
{
    const size_t scheme = url.find("://"), start = scheme == std::string::npos ? 0 : scheme + 3;
    size_t end = url.find_first_of("?#", start);
    if (end == std::string::npos) end = url.size();
    const size_t path = url.find('/', start);
    std::string host, last;
    if (path == std::string::npos || path >= end) host = url.substr(start, end - start);
    else {
        host = url.substr(start, path - start);
        const size_t slash = url.rfind('/', end - 1);
        last = url.substr(slash + 1, end - slash - 1);
    }
    std::string name = safeName(percentDecode(last));
    if (name.empty()) name = safeName(host);
    return name.empty() ? std::string(fallback) : name;
}
// Longer than kShownMax bytes: the first and last kShownEnd bytes around "...", never splitting a UTF-8 character.
inline std::string shown(const std::string& name)
{
    if (name.size() <= kShownMax) return name;
    size_t head = kShownEnd, tail = name.size() - kShownEnd;
    while (head > 0 && (static_cast<unsigned char>(name[head]) & 0xC0) == 0x80) --head;
    while (tail < name.size() && (static_cast<unsigned char>(name[tail]) & 0xC0) == 0x80) ++tail;
    return name.substr(0, head) + "..." + name.substr(tail);
}

// The last address handed over (only accepted hand-overs are noted). now: SDL_GetTicks() (wraps; unsigned difference).
struct Recent {
    std::string link;
    uint32_t at = 0;
    bool any = false;
    bool repeat(const std::string& l, uint32_t now) const { return any && l == link && uint32_t(now - at) < kRepeatMs; }
    void note(const std::string& l, uint32_t now) { link = l; at = now; any = true; }
};

} // namespace OmniSaveImage
'''

SHELL_FN = '''// ''' + MARK + ''': "Save image" / "Save link target" hand an http(s) address to the Downloads app (the Downloads tab
// opens or comes forward with #url=<address>), by the rules of OMNI_FILE_DOWNLOADS_V1 (omniFileDownloadsTake):
// private tabs, "Media downloads" off, non-HTTP(S) addresses (data: images), the Downloads tab itself and self-tests
// keep WebKit's own save (omniFxSaveURL). The Downloads app fetches the file; nothing is fetched here.
static OmniSaveImage::Recent omniSviRecent;
static void omniSviSave(const std::string& url, bool image)
{
    namespace OSVI = OmniSaveImage;
    Tab* t = active();
    if (!t || url.empty()) return;
    OSVI::Where where;
    where.privateTab = t->omniPrivate;
    where.downloadsTab = t->omniMediaSection;
    where.testMode = omniTestMode();
    where.downloadsOn = omniMediaDownloadsEnabled;
    where.validLink = OmniMediaSection::validLink(url);
    if (OSVI::route(url, where) != OSVI::Route::Downloads) { omniFxSaveURL(url); return; }   // WebKit's own save, as before
    const std::string name = OSVI::shown(OSVI::fileName(url, image ? "image" : "file"));
    const uint32_t now = SDL_GetTicks();
    if (omniSviRecent.repeat(url, now)) { notice("Sent to Downloads: " + name); return; }   // already handed over
    omniMediaDownloadsRequest(false, false, true, url);
    if (status != "Opening Media downloads...") return;   // not accepted: its own notice stays, a retry is allowed
    omniSviRecent.note(url, now);
    notice("Sent to Downloads: " + name);
}
'''

# The background-image line of the hit-test script (inside the R"JS(...)JS" raw string: no C++ comment possible).
BG_JS = (r'''if(!r.img&&!r.video)for(var j=0;j<es.length&&j<8;j++){var g=es[j];if(!g||!g.tagName||/^(HTML|BODY|IFRAME|VIDEO)$/.test(g.tagName))continue;'''
         r'''var w=(g.ownerDocument&&g.ownerDocument.defaultView)||window,bi='';try{bi=w.getComputedStyle(g).backgroundImage||'';}catch(_){}'''
         r'''var mm=/url\(\s*(['"]?)(https?:[^'")]+)\1\s*\)/i.exec(bi);if(!mm)continue;var gb=g.getBoundingClientRect();'''
         r'''if(gb.width*gb.height>0.6*w.innerWidth*w.innerHeight)continue;'''
         r'''r.img=mm[2];r.alt=(g.getAttribute('aria-label')||g.title||'').replace(/\s+/g,' ').trim().slice(0,140);break;}''' + '\n')

VIDEO_JS = r'''if(n.tagName==='VIDEO'){var s=n.currentSrc||n.src;if(s&&!/^blob:/.test(s))r.video=s;break;}}''' + '\n'

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniMediaDownloads.h" // OMNI_MEDIA_DOWNLOADS_V1: isolated optional worker\n',
         '#include "OmniMediaDownloads.h" // OMNI_MEDIA_DOWNLOADS_V1: isolated optional worker\n'
         '#include "OmniSaveImage.h" // ' + MARK + ': page menu Save image / Save link target -> Downloads (pure)\n'),
    ],
    'OmniContextMenu.h': [
        ('static void omniFxCopy(const std::string& text, const char* what)\n',
         SHELL_FN + 'static void omniFxCopy(const std::string& text, const char* what)\n'),
        ('        add(omniCxSaveLink, "Save link");\n',
         '        if (OmniSaveImage::offered(p.link)) add(omniCxSaveLink, "Save link target"); /* ' + MARK + ': to Downloads; not for blob: */\n'),
        ('        add(omniCxSaveImage, "Save image");\n',
         '        if (OmniSaveImage::offered(p.image)) add(omniCxSaveImage, "Save image"); /* ' + MARK + ': to Downloads; not for blob: */\n'),
        ('    case omniCxSaveLink: omniFxSaveURL(link); break;\n',
         '    case omniCxSaveLink: omniSviSave(link, false); break; /* ' + MARK + ' */\n'),
        ('    case omniCxSaveImage: omniFxSaveURL(image); break;\n',
         '    case omniCxSaveImage: omniSviSave(image, true); break; /* ' + MARK + ' */\n'),
        (VIDEO_JS, VIDEO_JS + BG_JS),
        # The raw string ends "})(" (its delimiter ")JS\"" takes the last ')'), so cutting 2 characters dropped the
        # IIFE's closing ')' and every probe was a SyntaxError -> "{}" -> page rows only. Cut only the trailing call.
        ('    js.replace(js.size() - 2, 2, "(X,Y);})()");   // the template ends with "()": call it with X, Y\n',
         '    if (js.size() >= 2 && js.compare(js.size() - 2, 2, "()") == 0) js.resize(js.size() - 2); /* ' + MARK + ': the template ends "})(" */\n'
         '    else if (!js.empty() && js.back() == \'(\') js.pop_back();\n'
         '    js += "(X,Y);})()";   /* call it with X, Y */\n'),
    ],
    'OmniControlsHelp.h': [
        ('    { kDownloads, { gCross }, 0, true, "Save link / Save image", "Page menu over a link or an image", "omniFxContextInput omniCxSaveLink / omniCxSaveImage" },\n',
         '    { kDownloads, { gCross }, 0, true, "Save link target / Save image", "Page menu; to Downloads when Media downloads is on", "omniFxContextInput omniCxSaveLink / omniCxSaveImage omniSviSave" }, /* ' + MARK + ' */\n'),
    ],
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
    data = text.replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


def main():
    if 'OMNI_FILE_DOWNLOADS_V1' not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        sys.exit('OmniBrowser.cpp: OMNI_FILE_DOWNLOADS_V1 missing: apply_file_downloads.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniSaveImage.h', PURE, 'OmniMediaSection.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
