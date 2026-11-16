#!/usr/bin/env python3
"""OMNI_BOOKMARKLETS_V1 (2026-11-16): bookmarklets: a javascript: bookmark runs on the page in the current tab.

How javascript: bookmarks behaved before (grep of the patched tree, recipe order up to apply_notice_history.py)
  - They could not be made on the console: omniFxBookmarkAdd (star, Options, Add current page, context menu) refuses
    anything but http(s) ("Only web pages can be bookmarked"); the Setup's PC import keeps only http(s) (clean_url).
  - One written into bookmarks.txt by hand was listed, and Cross ran navigate(url) -> destination(): not http(s), so
    "javascript:alert(1)" (no '.') went to the search engine as a query, and "javascript:document.title" (a '.', no
    space) became "https://javascript:document.title" (a failed load). Never run, never a javascript: navigation, so
    the policy layers never saw one (OMNI_PARENTAL_V1's kInternal class for javascript:, https-only, uBlock).
  - bookmarks.txt lines are read like fgets(2400) and addresses are cut at 2048 bytes on save (OmniBookmarksModel),
    which would break a longer bookmarklet's code.

What the user sees now
  - Bookmarks list: a bookmarklet row shows the badge "JS" (the row's value) and "Bookmarklet . 1.2 KB" instead of its
    address (the code is never shown: not in the row, the delete question or the Edit subtitle).
  - Cross (or D-pad right, which would open a blank new tab otherwise) on a bookmarklet: the menus close and it runs in
    the CURRENT tab's main frame (WKPageEvaluateJavaScriptInMainFrame, the page's own world, as the media controls,
    reader and autofill scripts run). Not a navigation. Notice "Bookmarklet ran: <name>" / "<name> stopped with an
    error" (the error text goes to the log, not for private tabs).
  - First run of each bookmarklet asks (an Omni panel, "Don't run" focused):
        "Run this bookmarklet on <host>?"   "It can read and change this page."
        Run / Always run this bookmarklet / Don't run
    "Always" remembers the SHA-256 of the decoded code in /data/omni/bookmarklets.txt (one hex key per line, newest
    last, 1000 kept; nothing else is stored), so the same code is trusted however it is percent-encoded, and changed
    code asks again. Edit bookmark (Triangle) on a bookmarklet has "Run without asking: On" - Cross forgets it.
    The answer applies only if the tab and its address are unchanged ("The page changed: open the bookmarklet again").
  - Never runs (a notice says why): parental controls on (any mode; OmniParental Store::active()), omni:// built-in
    and new-tab pages, Reader view (omniReader / omniRauInReader), a reading-list saved copy (omniRpId; about:blank
    anyway), any page not http(s), a crashed or unloaded tab, empty code, more than 64 KB (address or decoded code).
  - Private tabs: asked every time (no "Always" row; nothing is read into or written to the store from them).
  - "Add bookmarklet" row (after "Add current page"): the on-screen keyboard takes the code (paste works where the
    keyboard has it), then a name (default "Bookmarklet"). Input starting with "javascript:" is an address (cleaned as
    browsers clean URLs); anything else is code, stored as "javascript:" + the code with %, controls and spaces
    percent-encoded (byte-exact round trip: line breaks survive, "//" comments can't swallow the rest). Disabled while
    parental controls are on. The same rows also come from the PC once Setup keeps javascript: bookmarks (see report).

Decoding (OmniBookmarklets::sourceOf; checked against Node's WHATWG URL + TextDecoder): URL Standard input clean-up
  (leading / trailing C0 and spaces, every tab / LF / CR), "javascript:" in any case, then HTML's javascript: URL
  special case: everything after the scheme (query and fragment included) percent-decoded (%XX only; '+' stays), UTF-8
  decoded with U+FFFD per maximal bad subpart and a leading BOM dropped. Deliberate difference: the script's completion
  value is ignored (a marker string is appended as the last statement), so a bookmarklet that evaluates to a string
  does not replace the page as Chrome / Firefox would; nearly all use void(...) / an IIFE anyway. NUL bytes are kept
  (WKStringCreateWithUTF8CStringWithLength). Page CSP still applies to what the code does (eval, injected <script>).

bookmarks.txt (OmniBookmarkletsFile.h): a line starting with "javascript:" (any case) is read whole up to 64 KB of
  address (+ title / folder) and saved with up to 64 KB of address; every other line is read / cut / written by
  OmniBookmarksModel exactly as before (a file without bookmarklets loads and saves byte-identically; host-tested).
  An older Omni reads such a long line as several 2399-byte entries (and would cut it on its next save).

Pure parts (host-tested, tools/test_bookmarklets.cpp):
  engine/entry/OmniBookmarklets.h      (from tools/): decoding, typed-code encoding, SHA-256, consent store, decide(),
                                        texts.  g++ -std=c++20 -Wall -Wextra -Werror -I. test_bookmarklets.cpp
  engine/entry/OmniBookmarkletsFile.h  (from tools/): bookmarks.txt lines. Add -DOBKL_MODEL -I<tree>/engine/entry.
Shell part: engine/entry/OmniBookmarkletsShell.h (written here), alias OBKL, names omniBmk*.
Ids: panel kind 7614, Edit row 8614, bookmarks-list row -7 (checked unused in every apply_*.py and the tree).

Anchors (each once; whole lines; CRLF / LF kept; MARK per file makes a re-run print "already"):
  OmniBrowser.cpp       the OmniBookmarksModel.h include line (pure includes after)
  OmniBookmarks.h       the OmniBookmarksModel::parse line of omniFxBookmarksLoad, the serialize line of
                        omniFxBookmarksSave (replaced by OmniBookmarkletsFile's)
  OmniBookmarksShell.h  the OBMK alias (declarations after), `p.rows.push_back(add);` (Add bookmarklet row after),
                        the bookmark row's r.detail line (badge after), the omniBmAskDelete omniAsk line and the Edit
                        subtitle line (no code shown), the Folder row line of omniBmEditBuild (consent row after),
                        omniBmEditInput's head (consent input after), `const bool lr = ...` in omniBmInput (Add
                        bookmarklet input before), `const OBMK::Entry e = ...` + `switch (b) {` (run before the switch)
  OmniFeatures3.h       the OmniParentalShell.h include line (shell include after)
Apply AFTER apply_bookmarks_manager.py and apply_parental.py (their lines are anchors).
usage: apply_bookmarklets.py <engine tree>   (anchored, idempotent, keeps each file's line endings; re-run: "already")
"""
import re
import sys
from pathlib import Path

# Depends on OMNI_READING_PROGRESS_V1: reads omniRpId (apply_reading_progress.py runs first); that script's name scan skips this file.
MARK = 'OMNI_BOOKMARKLETS_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_bookmarklets.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('7614', '8614')
NAMES = ('OBKL', 'omniBmk', 'OmniBookmarklets', 'OMNI_BOOKMARKLETS')

SHELL = r'''// OMNI_BOOKMARKLETS_V1: bookmarklets (shell side): a javascript: bookmark runs on the page in the current tab.
// Included from OmniFeatures3.h after OmniParentalShell.h (inside OmniBrowser.cpp's anonymous namespace); the bookmarks
// manager (OmniBookmarksShell.h) calls in through the declarations at its top. Pure parts: OmniBookmarklets.h
// (decoding, SHA-256 key, consent, rules, texts) and OmniBookmarkletsFile.h (bookmarks.txt). The reasons are in
// tools/apply_bookmarklets.py. Main thread only. /data/omni/bookmarklets.txt ("Always" answers: SHA-256 keys only) is
// written through omniIoQueue; never from a private tab, never in test modes.
#pragma once

namespace OBKL = OmniBookmarklets;
static OBKL::Consent omniBmkConsent;
static bool omniBmkConsentLoaded = false;
struct OmniBmkPending {
    const void* tab = nullptr;   // checked with omniTabAlive before use
    std::string pageUrl, source, key, title;
    bool privateTab = false;
};
static OmniBmkPending omniBmkAsk;                          // the question on screen
static std::string omniBmkCode, omniBmkName, omniBmkNewURL; // "Add bookmarklet": the keyboard's buffers

static void omniBmkLoad()
{
    if (omniBmkConsentLoaded) return;
    omniBmkConsentLoaded = true;
    std::string text;
    if (FILE* f = fopen(omniData(OBKL::kConsentFile).c_str(), "rb")) {
        char buf[4096];
        size_t n;
        while ((n = fread(buf, 1, sizeof buf, f)) > 0 && text.size() < (size_t(1) << 20)) text.append(buf, n);
        fclose(f);
    }
    omniBmkConsent = OBKL::parseConsent(text);
}
static void omniBmkSaveConsent()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OBKL::kConsentFile), OBKL::serializeConsent(omniBmkConsent), false);
}
static bool omniBmkParental() { omniParLoad(); return omniParStore.active(); }
static OBKL::Context omniBmkContext(const Tab* t)
{
    OBKL::Context c;
    c.parental = omniBmkParental();
    if (!t) return c;
    c.hasTab = true;
    c.crashed = t->crashed;
    c.unloaded = !t->omniLazyURL.empty() || omniTmIsUnloaded(*t);
    c.omniPage = t->omniPagesTab || t->omniNewTabPage;
    c.reader = t->omniReader || t->omniRauInReader;
    c.savedCopy = !t->omniRpId.empty();
    c.privateTab = t->omniPrivate;
    c.pageUrl = t->url;
    return c;
}

// --- running -------------------------------------------------------------------------------------------------------
struct OmniBmkRun { const void* tab; std::string title; bool privateTab; };
static void omniBmkRun(Tab* t, const std::string& source, const std::string& key, const std::string& title)
{
    const std::string js = OBKL::runScript(source);
    auto script = adoptWK(WKStringCreateWithUTF8CStringWithLength(js.data(), js.size()));
    fprintf(stderr, "OMNI BOOKMARKLET: run %.12s (%zu bytes)%s\n", key.c_str(), source.size(), t->omniPrivate ? " private tab" : ""); fflush(stderr);
    WKPageEvaluateJavaScriptInMainFrame(t->page, script.get(), new OmniBmkRun { t, title, t->omniPrivate }, [](WKTypeRef result, WKErrorRef error, void* context) {
        std::unique_ptr<OmniBmkRun> r(static_cast<OmniBmkRun*>(context));
        const bool ran = !error && result && WKGetTypeID(result) == WKStringGetTypeID()
            && OmniTest::toStd(static_cast<WKStringRef>(result)) == OBKL::kRunMarker;
        if (!ran) {
            const std::string why = error ? OmniTest::toStd(adoptWK(WKErrorCopyLocalizedDescription(error)).get()) : std::string("no answer");
            fprintf(stderr, "OMNI BOOKMARKLET: stopped: %s\n", r->privateTab ? "(private tab)" : why.substr(0, 200).c_str()); fflush(stderr);
        }
        if (omniTabAlive(r->tab)) notice(ran ? "Bookmarklet ran: " + r->title : r->title + " stopped with an error");
        omniShellDirty = true;
    });
}

// --- "Run this bookmarklet on <host>?" -----------------------------------------------------------------------------
static void omniBmkAskBuild(OmniFxPanel& p)
{
    OmniFxRow run; run.id = OBKL::kAskRun; run.label = "Run";
    p.rows.push_back(run);
    if (!omniBmkAsk.privateTab) {
        OmniFxRow always; always.id = OBKL::kAskAlways; always.label = "Always run this bookmarklet";
        always.detail = "On any site, without asking (Edit bookmark turns it off)";
        p.rows.push_back(always);
    }
    OmniFxRow no; no.id = OBKL::kAskNo; no.label = "Don't run";
    p.rows.push_back(no);
}
static bool omniBmkAskInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    const OmniBmkPending q = std::move(omniBmkAsk);
    omniBmkAsk = OmniBmkPending();
    omniFxCloseAll();
    if (r.id != OBKL::kAskRun && r.id != OBKL::kAskAlways) return true;
    Tab* t = active();
    if (!t || t != q.tab || !omniTabAlive(q.tab) || t->url != q.pageUrl) { notice("The page changed: open the bookmarklet again"); return true; }
    const OBKL::Verdict v = OBKL::pageVerdict(omniBmkContext(t));   // the page rules again (nothing changes them while asking, but cheap)
    if (v != OBKL::Verdict::Run) { notice(OBKL::refusal(v)); return true; }
    if (r.id == OBKL::kAskAlways && !q.privateTab && !t->omniPrivate) {
        omniBmkConsent.allow(q.key);
        omniBmkSaveConsent();
    }
    omniBmkRun(t, q.source, q.key, q.title);
    return true;
}
static void omniBmkAskShow(Tab* t, const std::string& source, const std::string& key, const std::string& title, bool privateTab)
{
    omniBmkAsk = OmniBmkPending { t, t->url, source, key, title, privateTab };
    OmniFxPanel p;
    p.kind = OBKL::kPanelKind;
    p.title = OBKL::askTitle(t->url);
    p.subtitle = OBKL::askSubtitle(privateTab);
    p.w = 860; p.maxVisible = 3;
    p.build = omniBmkAskBuild; p.input = omniBmkAskInput;
    p.faces = { { 0, "Choose" }, { 1, "Back" } };
    p.sel = privateTab ? 1 : 2;   // "Don't run" is focused first
    omniFxPush(std::move(p));
}

// From the bookmarks list (Cross / D-pad right on a bookmark). False: not a bookmarklet (it opens as before).
static bool omniBmkOpen(const std::string& url, const std::string& title)
{
    if (!OBKL::isBookmarklet(url)) return false;
    omniFxCloseAll();
    Tab* t = active();
    omniBmkLoad();
    std::string source, key;
    const OBKL::Verdict v = OBKL::decide(omniBmkContext(t), url, omniBmkConsent, &source, &key);
    if (v == OBKL::Verdict::Run) omniBmkRun(t, source, key, title);
    else if (v == OBKL::Verdict::Ask || v == OBKL::Verdict::AskPrivate) omniBmkAskShow(t, source, key, title, v == OBKL::Verdict::AskPrivate);
    else {
        notice(OBKL::refusal(v));
        fprintf(stderr, "OMNI BOOKMARKLET: refused (%d)\n", int(v)); fflush(stderr);
    }
    omniShellDirty = true;
    return true;
}

// --- the bookmarks manager -----------------------------------------------------------------------------------------
static std::string omniBmkShown(const std::string& url) { return OBKL::isBookmarklet(url) ? OBKL::shown(url) : omniShownURL(url); }
static void omniBmkDecorate(OmniFxRow& r, const std::string& url, const std::string& folder, bool searching)
{
    if (!OBKL::isBookmarklet(url)) return;
    r.value = OBKL::badge();
    r.detail = (searching && !folder.empty() ? folder + " \xc2\xb7 " : std::string()) + OBKL::rowDetail(url);
}
static void omniBmkAddRow(OmniFxPanel& p)
{
    OmniFxRow r;
    r.id = OBKL::kAddRowId;
    r.label = "Add bookmarklet";
    r.enabled = !omniBmkParental();
    r.detail = r.enabled ? "Paste or type javascript: code" : "Off while parental controls are on";
    p.rows.push_back(r);
}
static void omniBmkAdd(const std::string& url, const std::string& typedName)
{
    omniFxBookmarksLoad();
    if (omniFxBookmarkIndex(url) >= 0) { notice("Already bookmarked"); omniBmFocusURL = url; return; }
    if (omniFxBookmarks.size() >= omniFxBookmarkMax) { notice("Bookmarks are full (500): delete some first"); return; }
    std::string name = OBMK::trim(OBMK::oneLine(typedName, OBMK::kTitleMax));
    if (name.empty()) name = "Bookmarklet";
    omniFxBookmarks.emplace_back(url, name);
    omniFxBookmarksSave();
    omniBmFocusURL = url;
    notice("Added bookmarklet: " + name);
}
static bool omniBmkAddInput(const OmniFxRow& r, int b)
{
    if (r.id != OBKL::kAddRowId) return false;
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (!r.enabled || omniBmkParental()) { notice(OBKL::refusal(OBKL::Verdict::Parental)); return true; }
    omniBmkCode.clear();
    omniKbEdit(&omniBmkCode, "Bookmarklet: paste or type its javascript: code", [](bool ok) {
        if (!ok) { omniBmkCode.clear(); return; }
        const std::string url = OBKL::fromTyped(omniBmkCode);
        omniBmkCode.clear();
        if (url.empty()) { notice("No code: nothing added"); omniFxRefresh(); return; }
        if (url.size() > OBKL::kMaxBytes) { notice(OBKL::refusal(OBKL::Verdict::TooBig)); omniFxRefresh(); return; }
        omniBmkNewURL = url;
        omniBmkName = "Bookmarklet";
        omniKbEdit(&omniBmkName, "Bookmarklet name", [](bool named) {
            if (named) omniBmkAdd(omniBmkNewURL, omniBmkName);
            else notice("Bookmarklet not added");
            omniBmkNewURL.clear();
            omniFxRefresh();
        });
    });
    return true;
}
// Edit bookmark: "Run without asking" (only when "Always" was chosen; Cross forgets it).
static void omniBmkEditRow(OmniFxPanel& p, const std::string& url)
{
    if (!OBKL::isBookmarklet(url)) return;
    omniBmkLoad();
    const bool on = omniBmkConsent.has(OBKL::keyOf(OBKL::sourceOf(url)));
    OmniFxRow r;
    r.id = OBKL::kEditRowId;
    r.label = "Run without asking";
    r.value = on ? "On" : "Off";
    r.enabled = on;
    r.detail = on ? "Cross: ask again before it runs" : "Asks first (choose Always to skip)";
    p.rows.push_back(r);
}
static bool omniBmkEditInput(const OmniFxRow& r)
{
    if (r.id != OBKL::kEditRowId) return false;
    omniBmkLoad();
    omniBmkConsent.forget(OBKL::keyOf(OBKL::sourceOf(omniBmEditURL)));
    omniBmkSaveConsent();
    notice("This bookmarklet will ask before it runs");
    omniFxRefresh();
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniBookmarksModel.h" // OMNI_BOOKMARKS_MANAGER_V1: bookmarks.txt with folders, reorder, search (pure)\n',
         '#include "OmniBookmarksModel.h" // OMNI_BOOKMARKS_MANAGER_V1: bookmarks.txt with folders, reorder, search (pure)\n'
         '#include "OmniBookmarklets.h" // OMNI_BOOKMARKLETS_V1: javascript: bookmarks: decoding, SHA-256 consent key, rules (pure)\n'
         '#include "OmniBookmarkletsFile.h" // OMNI_BOOKMARKLETS_V1: bookmarks.txt lines with 64 KB javascript: addresses (pure)\n'),
    ],
    'OmniBookmarks.h': [
        ('    auto list = OmniBookmarksModel::parse(data, omniFxBookmarkMax);\n',
         '    auto list = OmniBookmarkletsFile::parse(data, omniFxBookmarkMax); // OMNI_BOOKMARKLETS_V1: javascript: lines whole (64 KB), others as the model reads them\n'),
        ('    omniIoQueue(omniData("bookmarks.txt"), OmniBookmarksModel::serialize(list), false);\n',
         '    omniIoQueue(omniData("bookmarks.txt"), OmniBookmarkletsFile::serialize(list), false); // OMNI_BOOKMARKLETS_V1: javascript: addresses up to 64 KB\n'),
    ],
    'OmniBookmarksShell.h': [
        ('namespace OBMK = OmniBookmarksModel;\n',
         'namespace OBMK = OmniBookmarksModel;\n'
         '// OMNI_BOOKMARKLETS_V1 (OmniBookmarkletsShell.h, included later from OmniFeatures3.h): javascript: bookmarks\n'
         'static bool omniBmkOpen(const std::string& url, const std::string& title);\n'
         'static void omniBmkDecorate(OmniFxRow& r, const std::string& url, const std::string& folder, bool searching);\n'
         'static std::string omniBmkShown(const std::string& url);\n'
         'static void omniBmkAddRow(OmniFxPanel& p);\n'
         'static bool omniBmkAddInput(const OmniFxRow& r, int b);\n'
         'static void omniBmkEditRow(OmniFxPanel& p, const std::string& url);\n'
         'static bool omniBmkEditInput(const OmniFxRow& r);\n'),
        ('    p.rows.push_back(add);\n',
         '    p.rows.push_back(add);\n'
         '    omniBmkAddRow(p); // OMNI_BOOKMARKLETS_V1: "Add bookmarklet"\n'),
        (r'''            r.detail = (omniBmQuery.empty() || e.folder.empty() ? std::string() : e.folder + " \xc2\xb7 ") + omniShownURL(e.url);''' '\n',
         r'''            r.detail = (omniBmQuery.empty() || e.folder.empty() ? std::string() : e.folder + " \xc2\xb7 ") + omniShownURL(e.url);''' '\n'
         '            omniBmkDecorate(r, e.url, e.folder, !omniBmQuery.empty()); // OMNI_BOOKMARKLETS_V1: "JS" badge, size instead of the code\n'),
        ('    omniAsk(mode ? "Remove this shortcut?" : "Delete this bookmark?", title + " (" + omniShownURL(url) + ") will be removed from this console.", mode ? "Remove" : "Delete", [url, mode](bool ok) {\n',
         '    omniAsk(mode ? "Remove this shortcut?" : "Delete this bookmark?", title + " (" + omniBmkShown(url) + ") will be removed from this console.", mode ? "Remove" : "Delete", [url, mode](bool ok) { // OMNI_BOOKMARKLETS_V1: omniBmkShown\n'),
        ('    p.subtitle = omniShownURL(e->url);\n',
         '    p.subtitle = omniBmkShown(e->url); // OMNI_BOOKMARKLETS_V1: never the code\n'),
        ('    OmniFxRow f; f.id = omniBmEditFolder; f.label = "Folder"; f.value = e->folder.empty() ? "None" : e->folder; p.rows.push_back(f);\n',
         '    OmniFxRow f; f.id = omniBmEditFolder; f.label = "Folder"; f.value = e->folder.empty() ? "None" : e->folder; p.rows.push_back(f);\n'
         '    omniBmkEditRow(p, e->url); // OMNI_BOOKMARKLETS_V1: "Run without asking" (bookmarklets)\n'),
        ('static bool omniBmEditInput(OmniFxPanel&, const OmniFxRow& r, int b)\n{\n    if (b != SDL_CONTROLLER_BUTTON_A) return false;\n',
         'static bool omniBmEditInput(OmniFxPanel&, const OmniFxRow& r, int b)\n{\n    if (b != SDL_CONTROLLER_BUTTON_A) return false;\n'
         '    if (omniBmkEditInput(r)) return true; // OMNI_BOOKMARKLETS_V1: forget "Always"\n'),
        ('    const bool lr = b == SDL_CONTROLLER_BUTTON_LEFTSHOULDER || b == SDL_CONTROLLER_BUTTON_RIGHTSHOULDER;\n',
         '    if (omniBmkAddInput(r, b)) return true; // OMNI_BOOKMARKLETS_V1: "Add bookmarklet"\n'
         '    const bool lr = b == SDL_CONTROLLER_BUTTON_LEFTSHOULDER || b == SDL_CONTROLLER_BUTTON_RIGHTSHOULDER;\n'),
        ('    const OBMK::Entry e = list[size_t(r.id)];\n    switch (b) {\n',
         '    const OBMK::Entry e = list[size_t(r.id)];\n'
         '    if ((b == SDL_CONTROLLER_BUTTON_A || b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT) && omniBmkOpen(e.url, e.title)) return true; // OMNI_BOOKMARKLETS_V1: runs on this tab\'s page\n'
         '    switch (b) {\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniParentalShell.h" /* OMNI_PARENTAL_V1 */\n',
         '#include "OmniParentalShell.h" /* OMNI_PARENTAL_V1 */\n'
         '#include "OmniBookmarkletsShell.h" /* OMNI_BOOKMARKLETS_V1: javascript: bookmarks run on the current page */\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_BOOKMARKS_MANAGER_V1', 'OMNI_PARENTAL_V1'),
         'OmniBookmarks.h': ('OMNI_BOOKMARKS_MANAGER_V1',),
         'OmniBookmarksShell.h': ('OMNI_BOOKMARKS_MANAGER_V1',),
         'OmniFeatures3.h': ('OMNI_PARENTAL_V1', 'OMNI_READING_LIST_V1')}


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
    mine = {'OmniBookmarklets.h', 'OmniBookmarkletsFile.h', 'OmniBookmarkletsShell.h'}
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
    # the bookmarks list's own row ids: -7 must still be free there
    shell = cpp_code((root / 'OmniBookmarksShell.h').read_bytes().decode('utf-8'))
    if MARK not in shell and re.search(r'=\s*-7\b', shell):
        sys.exit('OmniBookmarksShell.h already uses row id -7: pick another kAddRowId')


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
    pure = {}
    for name in ('OmniBookmarklets.h', 'OmniBookmarkletsFile.h'):
        pure[name] = (HERE / name).read_text(encoding='utf-8')
        if MARK not in pure[name]:
            sys.exit('%s: %s missing' % (name, MARK))
    msgs = [write_new('OmniBookmarklets.h', pure['OmniBookmarklets.h'], 'OmniBookmarksModel.h'),
            write_new('OmniBookmarkletsFile.h', pure['OmniBookmarkletsFile.h'], 'OmniBookmarksModel.h'),
            write_new('OmniBookmarkletsShell.h', SHELL, 'OmniBookmarksShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
