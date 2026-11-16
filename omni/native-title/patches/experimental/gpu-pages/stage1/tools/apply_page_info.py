#!/usr/bin/env python3
"""OMNI_PAGE_INFO_V1 (2026-11-16): "Page info", one panel of facts about the page in the shown tab.

What the user sees
  Ways in: Options > Settings > "Page info" (next to Site settings), the hold-Cross page menu "Page info" (after Site
  settings), and a click on the padlock / "http://" at the left end of the address field (x 184-221, the lock icon
  is drawn at 205; http(s) pages only; elsewhere the field still opens the address editor).
  Panel (title "Page info", subtitle the host; Cross on a row opens where that thing is changed):
    Address               Cross copies            detail: the full address        Cross: copy (as "Copy address")
    Connection            Secure (https) / Not secure (http) / Local network (http) / Omni page / File on the console /
                          No connection (data:)  (lock icon exactly when the address bar draws it: https)
                          https detail: "Encrypted to <host>. Certificate details aren't available in this build"
    uBlock                On / Off for this site / Off everywhere / Error
                          detail: "How many requests it blocked isn't available in this build"        Cross: Site settings
    Pop-ups blocked in this tab   n (only when there are any)                                         Cross: the list
    Cookies and site data "3 cookies . 12 stored items" (what the page can read; HttpOnly not counted) Cross: Site settings
                          (where "Clear data for this site" is)
    Permissions           None granted / Pop-ups allowed . Cookie access for 2 sites                   Cross: Site permissions
    Saved settings for this site  "3 settings" + the site list's summary line             Cross: that site's page in
                                                                                          "Sites with custom settings"
    Zoom / Autoplay / HTTPS-only / Page tweaks / Reader view / Game mode   the value in effect     Cross: Site settings
    Page language         "Japanese (ja)" / "Not stated by the page"       Cross (not English): translate (as Translate)
    Reading time          "About 6 min", detail "1,234 words. An estimate: menus and footers may count"
    Page load time        "2.4 s", detail "First byte 120 ms . Content ready 1.1 s . 48 KB . Reloaded"   Cross: measure again
    Private tab           (private tabs only) "Private tab: Page info stores nothing, and choices made here last until
                          Omni closes"
  Private tabs show the same facts; the values in effect include that private session's choices (autoplay,
  HTTPS-only, page tweaks, permissions); nothing is written anywhere by this panel.

What is real and what this build can't tell (checked in the engine tree and the engine's WebKit tree (s1/webkit))
  real   address, connection kind (from the URL, the same rule the address bar's lock uses), uBlock state for the site
         (omniBlockerEnabled / Failed / SiteTrusted), the tab's blocked pop-ups (OmniPopupNotice's per-tab record),
         Site permissions (omniPermFor: site-permissions.txt + this session), saved per-site settings (the site list's
         read model: omniSliSite + OSLI::parts / summary, OMNI_SITE_LIST_V1), the values in effect (each store's own
         value function, as the site list's detail page), and from ONE read-only page script (OmniPageInfo::script(),
         WKPageEvaluateJavaScriptInMainFrame, run when the panel opens, when the tab's address changes while it is
         open, and on Cross on the load / reading rows): the root element's lang attribute (the translate offer reads
         the same), words and CJK characters (reading time), document.cookie / localStorage / sessionStorage counts,
         navigation timing (performance.getEntriesByType('navigation')[0], performance.timing as a fallback).
  not available
         - certificate details: WKFrameGetCertificateInfo returns nullptr in this build (the panel says so).
         - uBlock's blocked-request count: the network engine (OmniUBlock.cpp, omniUBlockShouldBlock) runs in the
           network process and keeps no counter; the shell process has nothing per page (the panel says so).
         - the site's whole cookie jar: WKCookieManagerGetHostnamesWithCookies is an empty stub here and no C API
           returns cookies; the WKWebsiteDataStoreStatistics* calls only delete / flag. So the count is what the page
           itself can read (HttpOnly sign-in cookies are hidden from it: the row says so).
Cost: the script runs once per opening (text capped at 3 M characters); nothing runs while the panel is closed.

Pure part: OmniPageInfo.h (kept in tools/, copied into the tree): connection classification, the script and its
answer, number / time / size formatting, reading time, every text. Tests (tools/):
  g++ -std=c++20 -Wall -Wextra -Werror -I. test_page_info.cpp -o t && ./t script.js
  node --check script.js && node test_page_info_js.cjs script.js      (fake pages: article, CJK, old timing API, cap)
Shell side: engine/entry/OmniPageInfoShell.h, included from OmniBrowser.cpp right after OmniSiteListShell.h (it uses
the site list's omniSliSite / omniSliDetailShow and the OMNI_SLI_READER / OMNI_SLI_GAME switches).

Anchors (exactly once each; MARK makes each file idempotent; whole lines only, our lines go before or after them):
  OmniBrowser.cpp     the OmniSiteList.h include line (apply_site_list.py's): + OmniPageInfo.h
                      the OmniSiteListShell.h include line (apply_site_list.py's): + OmniPageInfoShell.h
                      the omniMqPointerTakeover declaration: + omniPgiLockClick declaration (click() is above the shell)
                      the omniF3StarClick line of click(): our padlock click goes before it
  OmniContextMenu.h   the omniImvContextAction declaration (apply_image_viewer.py's): + declarations, row id 9770
                      the "Site settings" add() line: + omniPgiContextRow(p)
                      the omniCxSite dispatch line: our dispatch first
  OmniQuickMenu.h     the omniBflQuickAction declaration (apply_bf_list.py's): + declarations, row id 8597
                      the omniQmSite add() line of omniFxQuickAllBuild: + omniPgiQuickRow(p)
                      the omniMqGroup Settings case line: our case first (group 4, Settings)
                      the omniBflQuickAction dispatch line: our dispatch first (before the >= 900 rows)
Ids: page menu row 9770, Options row 8597, panel kind 7397 (unused before; checked on a tree without MARK).
Namespace alias OPGI, names omniPgi*.
Apply AFTER apply_site_list.py (and apply_bf_list.py, apply_image_viewer.py, whose lines are anchors).
usage: apply_page_info.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_PAGE_INFO_V1'
HERE = Path(__file__).resolve().parent
root = Path(sys.argv[1]) / 'engine' / 'entry'

SHELL = r'''// OMNI_PAGE_INFO_V1: "Page info" (shell side). Included from OmniBrowser.cpp right after OmniSiteListShell.h (inside its
// anonymous namespace), so every store, the site list's read model and the panel helpers are defined above it. The pure
// part is OmniPageInfo.h; the reasons (what is real, what this build can't tell) are in tools/apply_page_info.py.
// Main thread only. It owns no file: it reads the stores' in-memory state and asks the page one read-only script.
#pragma once

namespace OPGI = OmniPageInfo;
enum { omniPgiKind = 7397 };
enum { omniPgiRAddress = 1, omniPgiRConn, omniPgiRUblock, omniPgiRPopups, omniPgiRStorage, omniPgiRPerms, omniPgiRSaved,
       omniPgiRZoom, omniPgiRAutoplay, omniPgiRHttps, omniPgiRTweaks, omniPgiRReader, omniPgiRGame, omniPgiRLang,
       omniPgiRReading, omniPgiRLoad, omniPgiRPrivate, omniPgiRGone };
struct OmniPgiState {
    const void* tab = nullptr;   // the tab the panel is about (looked up in `tabs`, never dereferenced unchecked)
    std::string url;             // its address when the script was asked
    uint32_t gen = 0;            // the newest question; older answers are dropped
    bool waiting = false;        // the script has not answered yet
    OPGI::Report report;
};
static OmniPgiState omniPgi;
struct OmniPgiAsk { uint32_t gen; };

static Tab* omniPgiTab()
{
    for (auto& t : tabs) if (t.get() == omniPgi.tab) return t.get();
    return nullptr;
}
// Ask the page (again): language, text, cookies / storage counts, navigation timing.
static void omniPgiAsk(Tab* t)
{
    omniPgi.tab = t;
    omniPgi.url = t ? t->url : std::string();
    omniPgi.report = OPGI::Report();
    omniPgi.waiting = false;
    const uint32_t gen = ++omniPgi.gen;
    if (!t || !t->page || t->crashed) return;
    omniPgi.waiting = true;
    static const std::string js = OPGI::script();
    auto src = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), new OmniPgiAsk { gen }, [](WKTypeRef result, WKErrorRef error, void* ctx) {
        std::unique_ptr<OmniPgiAsk> a(static_cast<OmniPgiAsk*>(ctx));
        if (a->gen != omniPgi.gen) return;   // asked again since (or about another page)
        omniPgi.waiting = false;
        omniPgi.report = OPGI::parse(omniFxResultString(result, error));
        if (!omniFxStack.empty() && omniFxStack.back().kind == omniPgiKind) omniFxRefresh();
        else omniShellDirty = true;
    });
}

static void omniPgiBuild(OmniFxPanel& p)
{
    auto add = [&](int id, std::string label, std::string value, bool on, std::string detail = std::string(), int icon = -1) {
        OmniFxRow r; r.id = id; r.label = std::move(label); r.value = std::move(value); r.enabled = on; r.detail = std::move(detail); r.icon = icon;
        p.rows.push_back(std::move(r));
    };
    Tab* t = omniPgiTab();
    if (!t) { p.subtitle = "The tab was closed"; add(omniPgiRGone, "This tab is no longer open", "", false); return; }
    if (t->url != omniPgi.url) omniPgiAsk(t);   // the tab moved on: facts about what it shows now
    const std::string url = t->url;
    const bool priv = t->omniPrivate;
    const OPGI::Report& rep = omniPgi.report;
    auto fromPage = [&](const std::string& v) { return omniPgi.waiting ? std::string(OPGI::kReading) : rep.ok ? v : std::string("Not available"); };
    const OPGI::Connection c = OPGI::classify(url);
    p.subtitle = OPGI::subtitle(c, t->title);

    add(omniPgiRAddress, "Address", url.empty() ? std::string("-") : std::string("Cross copies"), !url.empty(), url);
    add(omniPgiRConn, "Connection", OPGI::connectionValue(c), true, OPGI::connectionDetail(c), OPGI::padlock(c) ? int(omniIconLock) : -1);
    const std::string bh = omniBlockerHostOf(url);
    add(omniPgiRUblock, "uBlock", OPGI::ublockValue(omniBlockerEnabled(), omniBlockerFailed(), !bh.empty() && omniBlockerSiteTrusted(bh), !bh.empty()),
        true, OPGI::kUblockDetail);
    const size_t blockedPopups = OPN::count(omniPnRecent, omniPnKey(t));
    if (blockedPopups) add(omniPgiRPopups, "Pop-ups blocked in this tab", OPGI::popupsBlockedValue(blockedPopups), t == active(), "Cross lists them");
    add(omniPgiRStorage, "Cookies and site data", fromPage(OPGI::storageValue(rep)), true, OPGI::kStorageDetail);
    const std::map<std::string, int> perms = bh.empty() ? std::map<std::string, int>() : omniPermFor(bh);
    add(omniPgiRPerms, "Permissions", bh.empty() ? std::string("-") : OPGI::permissionsValue(perms), !bh.empty(),
        priv ? std::string("This private session's choices count too") : std::string());

    // Settings: the site list's read model (saved choices) and each store's value in effect (as its detail page).
    const std::string sh = OSLI::siteHost(bh);
    const OSLI::Site site = sh.empty() ? OSLI::Site() : omniSliSite(sh);
    add(omniPgiRSaved, "Saved settings for this site", sh.empty() ? std::string("-") : OPGI::savedValue(OSLI::parts(site).size()), !sh.empty(),
        site.items.empty() ? std::string() : OSLI::summary(site));
    omniPrefsLoad();
    add(omniPgiRZoom, "Zoom", bh.empty() ? std::string("-") : omniFxPercent(omniZoomFor(bh)), !bh.empty());
    omniApLoad();
    const std::string ak = OAP::siteKey(url);
    add(omniPgiRAutoplay, "Autoplay", ak.empty() ? std::string("-") : OAP::siteValue(omniApStore, omniApSession, ak, priv), !ak.empty());
    omniHoLoad();
    const std::string hk = OHO::urlHostKey(url);
    add(omniPgiRHttps, "HTTPS-only", hk.empty() ? std::string("-") : OHO::siteValue(omniHoStore, omniHoSession, hk, priv), !hk.empty());
    omniStLoad();
    const std::string tk = OSTW::siteKey(url);
    add(omniPgiRTweaks, "Page tweaks", OSTW::rowValue(OSTW::effective(omniStStore, omniStSession, tk, priv), !tk.empty()), !tk.empty());
#ifdef OMNI_SLI_READER
    omniRauLoad();
    const std::string rk = ORAU::siteKey(url);
    add(omniPgiRReader, "Reader view", rk.empty() ? std::string("-") : ORAU::rowValue(ORAU::saved(omniRauStore, rk)), !rk.empty());
#endif
#ifdef OMNI_SLI_GAME
    omniGmLoad();
    const std::string gk = OGMM::hostKey(url);
    add(omniPgiRGame, "Game mode", gk.empty() ? std::string("-") : OGMM::siteValue(omniGmStore.sites.count(gk) != 0, false), !gk.empty());
#endif

    // From the page itself (one script).
    add(omniPgiRLang, "Page language", fromPage(OPGI::languageValue(rep)), true,
        !omniPgi.waiting && OPGI::translatable(rep) && omniWebURL(url) && !omniIsTranslated(url) ? std::string("Cross translates it") : std::string());
    add(omniPgiRReading, "Reading time", fromPage(OPGI::readingValue(rep)), true, omniPgi.waiting ? std::string() : OPGI::wordsText(rep));
    add(omniPgiRLoad, "Page load time", fromPage(OPGI::loadValue(rep, t->loading)), true,
        omniPgi.waiting ? std::string() : rep.ok ? OPGI::loadDetail(rep) + ". Cross measures again" : std::string("Cross measures again"));
    if (priv) add(omniPgiRPrivate, "Private tab", "", true, OPGI::kPrivateDetail);
}
static bool omniPgiInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    Tab* t = omniPgiTab();
    if (!t || !r.enabled) return true;
    const bool shown = t == active();   // Site settings and Translate work on the shown tab
    switch (r.id) {
    case omniPgiRAddress: omniFxCopy(t->url, "Page address"); return true;
    case omniPgiRPopups: if (shown) omniPnShow(); return true;
    case omniPgiRPerms: omniPermSiteShow(omniBlockerHostOf(t->url)); return true;
    case omniPgiRSaved: {
        const std::string h = OSLI::siteHost(omniBlockerHostOf(t->url));
        if (!h.empty()) omniSliDetailShow(h);
        return true;
    }
    case omniPgiRLang:
        if (shown && !omniPgi.waiting && OPGI::translatable(omniPgi.report) && omniWebURL(t->url) && !omniIsTranslated(t->url)) {
            omniFxCloseAll();
            omniTranslateToggle();
        }
        return true;
    case omniPgiRReading: case omniPgiRLoad: omniPgiAsk(t); omniFxRefresh(); return true;   // measure again
    case omniPgiRUblock: case omniPgiRStorage: case omniPgiRZoom: case omniPgiRAutoplay: case omniPgiRHttps: case omniPgiRTweaks:
    case omniPgiRReader: case omniPgiRGame:
        if (shown) omniFxSiteSettingsShow(); else notice("Site settings follow the tab that is shown");
        return true;
    default: return true;
    }
}
static void omniPgiShow()
{
    Tab* t = active();
    if (!t) return;
    omniPgiAsk(t);
    OmniFxPanel p;
    p.kind = omniPgiKind; p.w = 1000; p.maxVisible = 9;
    p.title = "Page info";
    p.build = omniPgiBuild; p.input = omniPgiInput;
    p.faces = { { 0, "Open" }, { 1, "Back" } };
    p.extra = t->omniPrivate ? OPGI::kPrivateDetail : "Cross on a setting opens where it is changed";
    omniFxPush(std::move(p));
    fprintf(stderr, "OMNI PAGE INFO: opened (%s)\n", OPGI::connectionValue(OPGI::classify(t->url)).c_str()); fflush(stderr);   // never the address
}

// --- the ways in -------------------------------------------------------------------------------------------------
// The padlock / "http://" at the left end of the address field (only on http(s) pages; elsewhere the field edits).
static bool omniPgiLockClick(int x, int by)
{
    if (x < 184 || x >= 222 || by < 60 || by >= 106 || editing) return false;
    Tab* t = active();
    if (!t || !omniWebURL(t->url)) return false;
    omniPgiShow();
    return true;
}
// Options > Settings > "Page info"
static void omniPgiQuickRow(OmniFxPanel& p)
{
    OmniFxRow r; r.id = omniPgiQuickId; r.label = "Page info"; r.enabled = active() != nullptr;
    p.rows.push_back(std::move(r));
}
static bool omniPgiQuickAction(int id)
{
    if (id != omniPgiQuickId) return false;
    omniPgiShow();   // on top of Options: Circle comes back
    return true;
}
// hold Cross > "Page info"
static void omniPgiContextRow(OmniFxPanel& p)
{
    OmniFxRow r; r.id = omniPgiContextId; r.label = "Page info"; r.enabled = active() != nullptr;
    p.rows.push_back(std::move(r));
}
static bool omniPgiContextAction(int id)
{
    if (id != omniPgiContextId) return false;
    omniPgiShow();   // on top of the page menu, as Site settings
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSiteList.h" // OMNI_SITE_LIST_V1: Sites with custom settings (pure)\n',
         '#include "OmniSiteList.h" // OMNI_SITE_LIST_V1: Sites with custom settings (pure)\n'
         '#include "OmniPageInfo.h" // OMNI_PAGE_INFO_V1: Page info (pure)\n'),
        ('#include "OmniSiteListShell.h" // OMNI_SITE_LIST_V1: Sites with custom settings (after every store it reads)\n',
         '#include "OmniSiteListShell.h" // OMNI_SITE_LIST_V1: Sites with custom settings (after every store it reads)\n'
         '#include "OmniPageInfoShell.h" // OMNI_PAGE_INFO_V1: Page info (after the site list it reuses)\n'),
        ('static void omniMqPointerTakeover();\n',
         'static void omniMqPointerTakeover();\n'
         'static bool omniPgiLockClick(int x, int by); // OMNI_PAGE_INFO_V1: the padlock opens Page info (OmniPageInfoShell.h)\n'),
        ('        else if (omniF3StarClick(x, by)) { } // OMNI_FEATURES_V3: bookmark star\n',
         '        else if (omniPgiLockClick(x, by)) { } // OMNI_PAGE_INFO_V1: the padlock / "http://" opens Page info\n'
         '        else if (omniF3StarClick(x, by)) { } // OMNI_FEATURES_V3: bookmark star\n'),
    ],
    'OmniContextMenu.h': [
        ('static bool omniImvContextAction(OmniFxPanel& p, int id); /* OMNI_IMAGE_VIEWER_V1 */\n',
         'static bool omniImvContextAction(OmniFxPanel& p, int id); /* OMNI_IMAGE_VIEWER_V1 */\n'
         'constexpr int omniPgiContextId = 9770; // OMNI_PAGE_INFO_V1: hold-Cross page menu row "Page info" (OmniPageInfoShell.h)\n'
         'static void omniPgiContextRow(OmniFxPanel& p);\n'
         'static bool omniPgiContextAction(int id);\n'),
        ('        add(omniCxSite, "Site settings", web, omniIconShield);\n',
         '        add(omniCxSite, "Site settings", web, omniIconShield);\n'
         '        omniPgiContextRow(p); // OMNI_PAGE_INFO_V1: Page info\n'),
        ('    if (r.id == omniCxSite) { omniFxSiteSettingsShow(); return true; }\n',
         '    if (omniPgiContextAction(r.id)) return true; // OMNI_PAGE_INFO_V1 (stays open: the panel goes on top)\n'
         '    if (r.id == omniCxSite) { omniFxSiteSettingsShow(); return true; }\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniBflQuickAction(int id); // OMNI_BF_LIST_V1\n',
         'static bool omniBflQuickAction(int id); // OMNI_BF_LIST_V1\n'
         'constexpr int omniPgiQuickId = 8597; // OMNI_PAGE_INFO_V1: Options > Settings row "Page info" (OmniPageInfoShell.h)\n'
         'static void omniPgiQuickRow(OmniFxPanel& p);\n'
         'static bool omniPgiQuickAction(int id);\n'),
        ('    add(omniQmSite, "Site settings", true, omniIconShield);\n',
         '    add(omniQmSite, "Site settings", true, omniIconShield);\n'
         '    omniPgiQuickRow(p); // OMNI_PAGE_INFO_V1: Page info\n'),
        ('    case omniQmSettings: case omniQmBrowserSettings: case omniQmSite: case omniQmControls: return 4;\n',
         '    case omniPgiQuickId: return 4; // OMNI_PAGE_INFO_V1: Settings, next to Site settings\n'
         '    case omniQmSettings: case omniQmBrowserSettings: case omniQmSite: case omniQmControls: return 4;\n'),
        ('    if (omniBflQuickAction(r.id)) return true; // OMNI_BF_LIST_V1: Back history (before the >= 900 rows)\n',
         '    if (omniPgiQuickAction(r.id)) return true; // OMNI_PAGE_INFO_V1: Page info (before the >= 900 rows)\n'
         '    if (omniBflQuickAction(r.id)) return true; // OMNI_BF_LIST_V1: Back history (before the >= 900 rows)\n'),
    ],
}
NEEDS = {
    'OmniBrowser.cpp': ('OMNI_SITE_LIST_V1', 'OMNI_FEATURES_V3'),
    'OmniContextMenu.h': ('OMNI_IMAGE_VIEWER_V1',),
    'OmniQuickMenu.h': ('OMNI_BF_LIST_V1', 'OMNI_SITE_LIST_V1'),
}
IDS = ('7397', '8597', '9770')
NAMES = ('omniPgi', 'OPGI', 'OmniPageInfo')


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
    mine = {'OmniPageInfo.h', 'OmniPageInfoShell.h'}
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
    pure = (HERE / 'OmniPageInfo.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniPageInfo.h: %s missing' % MARK)
    msgs = [write_new('OmniPageInfo.h', pure, 'OmniSiteList.h'),
            write_new('OmniPageInfoShell.h', SHELL, 'OmniSiteListShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
