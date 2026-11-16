#!/usr/bin/env python3
r"""OMNI_SITE_SEARCH_V1 (2026-11-16): site search shortcuts from OpenSearch ("Add Example search").

What existed (grep of the patched tree, chain_final order through apply_search_engine.py)
  - Search shortcuts (OMNI_SEARCH_TILES_V1, OmniSearchTiles.h): "yt cats" + Go -> YouTube; built-ins yt w r g d a m;
    the user's list is /data/omni/search-shortcuts.txt ("prefix<TAB>https://...%s[<TAB>Name]" per line, '#' comments,
    at most 30, built-ins only while the file is MISSING), read by omniStEngines (OmniSearchTiles::Store: re-read when
    the file's size or mtime changes) at omniStPath. omniStResolve (Go) and the first address suggestion use it.
    Nothing in Omni wrote that file and there was no manager for it (no list, rename or delete anywhere).
  - OMNI_SEARCH_ENGINE_V1 (OmniSearchEngine.h): the custom-template check OmniSearchEngine::check (https only, no
    credentials, plain host, exactly one %s, every other % is %XX, no spaces / quotes / <> / {}|^ ...). Reused here.
  - Private tabs: Tab::omniPrivate. Guest mode (apply_guest_mode.py, applied LAST when used) makes every tab private
    and refuses omniIoQueue writes under /data/omni, so both rules below also hold for guests.

What the user sees
  - After an https page finishes loading (normal tab, setting on, not a self-test mode), a one-shot page script looks
    for <link rel="search" type="application/opensearchdescription+xml" href>. When there is one, it fetches the
    description FROM THE PAGE'S OWN CONTEXT (fetch in the page: Omni's own networking is not used; same-origin is
    typical; a cross-origin description without CORS fails and is skipped), https only (the link and the final
    address after redirects), credentials omitted, 4 s, at most 16 KB (more is refused, not cut), and returns the
    XML text. Once per site per session (the fetch is not repeated for that site after an answer).
  - The shell parses it (OmniSiteSearch::offerFrom, pure): one OpenSearchDescription root; ShortName; the first Url
    with type text/html, GET, rel results (or none). {searchTerms} -> %s (exactly once, required); optional params
    ({x?}) dropped, required startIndex / startPage -> 1, count -> 20, language -> *, input/outputEncoding -> UTF-8,
    any other required one: refused. The result must pass OmniSearchEngine::check AND OmniSearchTiles::validTemplate.
    The parser is small and strict: no DOCTYPE / ENTITY (so no entity expansion), only the 5 predefined entities and
    numeric references to valid XML characters, bounded depth / elements / attributes / size, tags must nest.
  - Offer, when the site's template isn't already a shortcut (same host + path as one): a notice once per site per
    session "<Name> has a search: Options > Add <Name> search", and while that site is shown, the Options menu's top
    level has a row "Add <Name> search" (value: the template's host). Never in private tabs (so never for guests).
  - Cross on it: a panel "Add <Name> search": Keyword (default: the name's first word, lower case, else the host's first
    label; "2", "3"... while taken; Cross edits it with the on-screen keyboard: 1-16 of a-z 0-9 - _ !, not taken),
    "Searches go to" <host> (" (not this site)" when the template's host isn't the page's site), "Add search shortcut",
    "Not now" (no more offers for that site this session). Add appends "keyword<TAB>template<TAB>Name" to
    search-shortcuts.txt (a missing file is first written with the built-ins, so yt / w / ... stay); the notice says
    'Type "kw words" in the address bar to search <Name>'. At most 30 shortcuts (the file's own limit).
  - Browser settings, after "Search engine": "Offer site searches" On / Off (default On; /data/omni/site-search.txt,
    "offer<TAB>1|0"; Off: no page script runs at all) and "Search shortcuts..." (value "<n> keywords"), a list of the
    shortcuts in effect (keyword, name, host). Cross renames (keyboard), Square deletes (asks first), Circle back.
    Edits keep every line they do not touch (comments, invalid lines, the file's CRLF / LF), drop dead duplicate lines
    of the edited keyword (they would otherwise come alive), and write the built-ins first when the file is missing.
  Writes go through omniIoQueue (+ omniIoFlush), then omniStEngines is reset so the change applies at once (a
  same-size rewrite within one second would look unchanged to its mtime / size check); a write that didn't land
  (guest mode refusal, I/O error) says "Couldn't save".

Pure part: engine/entry/OmniSiteSearch.h (copied from tools/OmniSiteSearch.h; includes OmniSearchEngine.h and
OmniSearchTiles.h). Tests:
    g++ -std=c++20 -Wall -Wextra -Werror -I<tools> -I<tree>/engine/entry test_site_search.cpp -o t && ./t script.js
    node test_site_search_js.mjs script.js       (the page script against stub APIs)
Shell part: engine/entry/OmniSiteSearchShell.h (written by this script), alias OSSE, names omniSse*.
Ids: panel kinds 7620 / 7621 (OmniSiteSearch.h), Options row 8620, Browser settings rows 8627 / 8622 (checked unused in
every apply_*.py's code and the tree; the settings rows are dispatched before the >= 300 / >= 900 rows).

Anchors (exactly once each, whole lines; new lines go after them, or before for the settings input; line endings kept):
  OmniBrowser.cpp        the OmniSearchTiles.h include (pure include after); the omniHltFinished declaration (ours
                         after); the omniHltFinished(tab) call in finished() (ours after)
  OmniBrowserSettings.h  the omniOrSettingsInput declaration (declarations after); the omniSenRowValue() line after the
                         "Search engine" row (apply_search_engine.py's; rows after); the omniUisRowId input line (ours
                         before it)
  OmniQuickMenu.h        the omniClhQuickInput declaration; the omniClhQuickRow(p) line; the omniClhQuickInput(r, b)
                         line (apply_clip_history.py's; ours after each)
  OmniFeatures3.h        the OmniLinkPreviewShell.h include (shell include after)
Apply AFTER apply_search_engine.py (and apply_search_tiles.py, apply_clip_history.py, apply_highlights.py,
apply_link_preview.py, apply_offline_retry.py, apply_ui_scale.py: their lines are anchors); before apply_guest_mode.py.
usage: apply_site_search.py <engine tree>   (anchored, idempotent, keeps each file's line endings; re-run: "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_SITE_SEARCH_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_site_search.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('7620', '7621', '8620', '8627', '8622')
NAMES = ('OSSE', 'omniSse', 'OmniSiteSearch', 'OMNI_SITE_SEARCH(?!_SUGGEST)')   # OMNI_SITE_SEARCH_SUGGEST_V1 is another patch's MARK, not ours

SHELL = r'''// OMNI_SITE_SEARCH_V1: site search shortcuts from OpenSearch (shell side). Included from OmniFeatures3.h (inside
// OmniBrowser.cpp's anonymous namespace). The pure part is OmniSiteSearch.h; the reasons are in
// tools/apply_site_search.py. Main thread only.
#pragma once

namespace OSSE = OmniSiteSearch;

// --- "Offer site searches" (/data/omni/site-search.txt, On by default) ----------------------------------------------
static bool omniSseLoaded = false, omniSseOfferOn = true;
static bool omniSseOn()
{
    if (!omniSseLoaded) {
        omniSseLoaded = true;
        if (FILE* f = fopen(omniData("site-search.txt").c_str(), "rb")) {
            char b[256] = {};
            const size_t n = fread(b, 1, sizeof b - 1, f);
            fclose(f);
            omniSseOfferOn = OSSE::parseOffer(std::string(b, n));
        }
    }
    return omniSseOfferOn;
}
static void omniSseSetOn(bool on)
{
    omniSseOn();
    omniSseOfferOn = on;
    omniIoQueue(omniData("site-search.txt"), OSSE::offerText(on), false);
}

// --- search-shortcuts.txt -----------------------------------------------------------------------------------------
static const std::vector<OmniSearchTiles::Engine>& omniSseEngines() { return omniStEngines.get(omniStPath); }
static std::string omniSseReadFile(bool& exists)
{
    std::string text;
    exists = false;
    FILE* f = fopen(omniStPath, "rb");
    if (!f) return text;
    exists = true;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && text.size() < OmniSearchTiles::kMaxFile) text.append(buf, n);
    fclose(f);
    return text;
}
// The whole file through the I/O queue (refused in guest mode), waited for; the shortcuts are re-read at once
// (a same-size rewrite within a second would look unchanged to the Store's mtime / size check). false: not on disk.
static bool omniSseWrite(const std::string& text)
{
    omniIoQueue(omniStPath, text, false);
    omniIoFlush();
    omniStEngines = OmniSearchTiles::Store();
    bool exists = false;
    const bool ok = omniSseReadFile(exists) == text && exists;
    omniSuggestFor = "\x01";   // the address bar's rows are rebuilt (the shortcut row)
    fprintf(stderr, "OMNI SITE SEARCH: search-shortcuts.txt %s (%zu bytes)\n", ok ? "written" : "NOT written", text.size());
    return ok;
}

// --- offers (this session only) -----------------------------------------------------------------------------------
struct OmniSseSite { OSSE::Offer offer; bool hinted = false, dismissed = false; };
static std::map<std::string, OmniSseSite> omniSseSites;   // by page site (OSSE::pageSite)
static std::set<std::string> omniSseAsked;                // sites whose description was fetched (or the fetch failed)
struct OmniSseAsk { const void* tab = nullptr; std::string url, site; };
static std::map<uintptr_t, OmniSseAsk> omniSseOut;        // page scripts not answered yet, by generation
static uintptr_t omniSseGen = 0;

static bool omniSseEligible(const Tab& t)
{
    return omniSseOn() && !omniTestMode() && !t.omniPrivate && !t.crashed && !OSSE::pageSite(t.url).empty();
}
static OmniSseSite* omniSseOfferFor(const Tab* t)
{
    if (!t || !omniSseEligible(*t)) return nullptr;
    auto it = omniSseSites.find(OSSE::pageSite(t->url));
    if (it == omniSseSites.end() || !it->second.offer.ok || it->second.dismissed) return nullptr;
    if (OSSE::alreadySaved(it->second.offer, omniSseEngines())) return nullptr;
    return &it->second;
}
static void omniSseHint(const Tab& t)
{
    if (&t != active()) return;
    OmniSseSite* s = omniSseOfferFor(&t);
    if (!s || s->hinted) return;
    s->hinted = true;
    notice(OSSE::hintText(s->offer));
}
static void omniSseAnswer(uintptr_t gen, const std::string& answer)
{
    auto it = omniSseOut.find(gen);
    if (it == omniSseOut.end()) return;
    const OmniSseAsk ask = it->second;
    omniSseOut.erase(it);
    std::string xml;
    const OSSE::Answer a = OSSE::parseAnswer(answer, &xml);
    if (a == OSSE::Answer::Nothing || a == OSSE::Answer::NoLink) return;   // looked for again on the site's next load
    omniSseAsked.insert(ask.site);
    if (a != OSSE::Answer::Xml) { fprintf(stderr, "OMNI SITE SEARCH: %s: description not fetched\n", ask.site.c_str()); return; }
    const OSSE::Offer o = OSSE::offerFrom(xml);
    fprintf(stderr, "OMNI SITE SEARCH: %s: %s\n", ask.site.c_str(), o.ok ? o.tmpl.c_str() : ("refused: " + o.why).c_str());
    if (!o.ok) return;
    omniSseSites[ask.site].offer = o;
    if (!omniTabAlive(ask.tab)) return;
    const Tab* t = static_cast<const Tab*>(ask.tab);
    if (t->url == ask.url) omniSseHint(*t);
}
// From finished() (OmniBrowser.cpp), every tab: the page script once per site per session.
static void omniSseFinished(Tab& tab)
{
    if (!omniSseEligible(tab)) return;
    const std::string site = OSSE::pageSite(tab.url);
    if (omniSseAsked.count(site)) { omniSseHint(tab); return; }
    for (const auto& [g, ask] : omniSseOut) if (ask.site == site) return;   // already asking this site
    while (omniSseOut.size() >= 8) omniSseOut.erase(omniSseOut.begin());     // answers that never came
    const uintptr_t gen = ++omniSseGen;
    omniSseOut[gen] = OmniSseAsk{ &tab, tab.url, site };
    auto body = adoptWK(WKStringCreateWithUTF8CString(OSSE::pageScript().c_str()));
    auto args = adoptWK(WKDictionaryCreate(nullptr, nullptr, 0));   // an async function needs an argument list
    WKPageCallAsyncJavaScriptWithoutUserGesture(tab.page, body.get(), args.get(), nullptr, reinterpret_cast<void*>(gen), [](WKTypeRef result, WKErrorRef error, void* ctx) {
        omniSseAnswer(reinterpret_cast<uintptr_t>(ctx), omniFxResultString(result, error));
    });
}

// --- keyword entry (on-screen keyboard) -----------------------------------------------------------------------------
static std::string omniSseEditText, omniSseKwExcept;
static std::function<void(const std::string&)> omniSseKwDone;
static void omniSseEditKeyword(const std::string& current, const std::string& except, std::function<void(const std::string&)> done)
{
    omniSseEditText = current;
    omniSseKwExcept = except;
    omniSseKwDone = std::move(done);
    omniKbEdit(&omniSseEditText, "Search keyword (1-16 letters, digits, - _ !)", [](bool ok) {
        if (!ok) { omniFxRefresh(); return; }
        std::string kw;
        const OSSE::KwBad bad = OSSE::checkKeyword(omniSseEditText, omniSseEngines(), kw, omniSseKwExcept);
        if (bad != OSSE::KwBad::None) { notice(std::string("Keyword not changed: ") + OSSE::keywordWhy(bad)); omniFxRefresh(); return; }
        const auto done2 = omniSseKwDone;   // a copy: it may start another edit
        if (done2) done2(kw);
        omniFxRefresh();
    });
}

// --- "Add <Name> search" panel -------------------------------------------------------------------------------------
static OSSE::Offer omniSseDraft;
static std::string omniSseDraftKw, omniSseDraftSite;
static void omniSseConfirmBuild(OmniFxPanel& p)
{
    p.title = OSSE::quickLabel(omniSseDraft);
    p.subtitle = OSSE::usage(omniSseDraftKw, omniSseDraft.name);
    auto add = [&](int id, const std::string& label, const std::string& value, bool enabled) {
        OmniFxRow r; r.id = id; r.label = label; r.value = value; r.enabled = enabled; p.rows.push_back(r);
    };
    add(OSSE::kRowKeyword, "Keyword", omniSseDraftKw, true);
    p.rows.back().detail = "Cross: change";
    add(OSSE::kRowWhere, "Searches go to", OSSE::whereValue(omniSseDraft, omniSseDraftSite), false);
    add(OSSE::kRowAdd, "Add search shortcut", "", true);
    add(OSSE::kRowCancel, "Not now", "", true);
}
static void omniSseSave()
{
    std::string kw;
    const OSSE::KwBad bad = OSSE::checkKeyword(omniSseDraftKw, omniSseEngines(), kw);
    if (bad != OSSE::KwBad::None) { notice(std::string("Choose another keyword: ") + OSSE::keywordWhy(bad)); return; }
    if (omniSseEngines().size() >= OmniSearchTiles::kMaxEngines) {
        notice("Search shortcuts are full (30): delete one in Browser settings > Search shortcuts");
        return;
    }
    bool exists = false;
    const std::string text = omniSseReadFile(exists);
    if (!omniSseWrite(OSSE::addEntry(text, exists, kw, omniSseDraft.tmpl, omniSseDraft.name))) { notice("Couldn't save the search shortcut"); return; }
    omniFxCloseAll();
    notice("Added. " + OSSE::usage(kw, omniSseDraft.name));
}
static bool omniSseConfirmInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    switch (r.id) {
    case OSSE::kRowKeyword:
        omniSseEditKeyword(omniSseDraftKw, std::string(), [](const std::string& kw) { omniSseDraftKw = kw; });
        return true;
    case OSSE::kRowAdd: omniSseSave(); return true;
    case OSSE::kRowCancel:
        omniSseSites[omniSseDraftSite].dismissed = true;
        omniFxPop();
        return true;
    }
    return true;
}
static void omniSseConfirmShow()
{
    Tab* t = active();
    const OmniSseSite* s = omniSseOfferFor(t);
    if (!s) return;
    omniSseDraft = s->offer;
    omniSseDraftSite = OSSE::pageSite(t->url);
    omniSseDraftKw = OSSE::defaultKeyword(omniSseDraft.name, omniSseDraft.host, omniSseEngines());
    OmniFxPanel p;
    p.kind = OSSE::kPanelKind;
    p.w = 860; p.rowH = 54; p.maxVisible = 4;
    p.build = omniSseConfirmBuild; p.input = omniSseConfirmInput;
    p.faces = { { 0, "Choose" }, { 1, "Back" } };
    omniFxPush(std::move(p));
    omniFxStack.back().sel = 2;   // "Add search shortcut"
}

// --- Options (top level): "Add <Name> search" while a site with an offer is shown ----------------------------------
static void omniSseQuickRow(OmniFxPanel& p)
{
    const OmniSseSite* s = omniSseOfferFor(active());
    if (!s) return;
    OmniFxRow r; r.id = omniSseQuickRowId; r.label = OSSE::quickLabel(s->offer); r.value = s->offer.host;
    p.rows.push_back(r);
}
static bool omniSseQuickInput(const OmniFxRow& r, int b)
{
    if (r.id != omniSseQuickRowId || b != SDL_CONTROLLER_BUTTON_A) return false;
    omniFxCloseAll();
    omniSseConfirmShow();
    return true;
}

// --- Browser settings > "Search shortcuts...": rename (Cross) / delete (Square) ------------------------------------
static std::string omniSseRenameFrom;
static void omniSseManagerBuild(OmniFxPanel& p)
{
    const auto& list = omniSseEngines();
    p.subtitle = list.empty() ? std::string("None. Sites that offer a search can be added from Options")
                              : std::string("Type \"keyword words\" in the address bar");
    if (list.empty()) { OmniFxRow r; r.id = OSSE::kRowEmpty; r.label = "No search shortcuts"; r.enabled = false; p.rows.push_back(r); return; }
    for (size_t i = 0; i < list.size(); ++i) {
        OmniFxRow r; r.id = OSSE::kRowEntry + int(i); r.label = list[i].prefix; r.value = list[i].name;
        r.detail = OmniSearchTiles::hostOf(list[i].tmpl);
        p.rows.push_back(r);
    }
}
static bool omniSseManagerInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (r.id < OSSE::kRowEntry) return b == SDL_CONTROLLER_BUTTON_A;
    const auto& list = omniSseEngines();
    const size_t i = size_t(r.id - OSSE::kRowEntry);
    if (i >= list.size()) return b == SDL_CONTROLLER_BUTTON_A;
    const OmniSearchTiles::Engine e = list[i];
    if (b == SDL_CONTROLLER_BUTTON_A) {
        omniSseRenameFrom = e.prefix;
        omniSseEditKeyword(e.prefix, e.prefix, [](const std::string& kw) {
            if (kw == omniSseRenameFrom) return;
            bool exists = false, found = false;
            const std::string next = OSSE::renameEntry(omniSseReadFile(exists), exists, omniSseRenameFrom, kw, &found);
            if (!found) { notice("That search shortcut is gone"); return; }
            notice(omniSseWrite(next) ? "Keyword changed to " + kw : std::string("Couldn't save the search shortcuts"));
        });
        return true;
    }
    if (b == SDL_CONTROLLER_BUTTON_X) {
        const std::string prefix = e.prefix;
        omniAsk("Delete the \"" + prefix + "\" search?", "\"" + prefix + " words\" will no longer search " + e.name + ".", "Delete", [prefix](bool ok) {
            if (!ok) return;
            bool exists = false, found = false;
            const std::string next = OSSE::removeEntry(omniSseReadFile(exists), exists, prefix, &found);
            if (!found) { notice("That search shortcut is gone"); omniFxRefresh(); return; }
            notice(omniSseWrite(next) ? "Deleted the \"" + prefix + "\" search" : std::string("Couldn't save the search shortcuts"));
            omniFxRefresh();
        });
        return true;
    }
    return false;
}
static void omniSseManagerShow()
{
    OmniFxPanel p;
    p.kind = OSSE::kManagerKind;
    p.title = "Search shortcuts";
    p.w = 900; p.rowH = 50; p.maxVisible = 9;
    p.build = omniSseManagerBuild; p.input = omniSseManagerInput;
    p.faces = { { 0, "Rename" }, { 2, "Delete" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}
static void omniSseSettingsRows(OmniFxPanel& p)
{
    OmniFxRow r; r.id = omniSseRowOffer; r.label = "Offer site searches"; r.value = omniSseOn() ? "On" : "Off"; r.stepper = true;
    r.detail = "sites with a search: Options > Add <site> search; never in private tabs";
    p.rows.push_back(r);
    const size_t n = omniSseEngines().size();
    OmniFxRow m; m.id = omniSseRowList; m.label = "Search shortcuts..."; m.value = std::to_string(n) + (n == 1 ? " keyword" : " keywords");
    p.rows.push_back(m);
}
static bool omniSseSettingsInput(int id, int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT, a = b == SDL_CONTROLLER_BUTTON_A;
    if (id == omniSseRowOffer) {
        if (!left && !right && !a) return false;
        omniSseSetOn(!omniSseOn());
        return true;
    }
    if (id == omniSseRowList) {
        if (!a) return false;
        omniSseManagerShow();
        return true;
    }
    return false;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSearchTiles.h" // OMNI_SEARCH_TILES_V1: search shortcuts and most-visited tiles (pure)\n',
         '#include "OmniSearchTiles.h" // OMNI_SEARCH_TILES_V1: search shortcuts and most-visited tiles (pure)\n'
         '#include "OmniSiteSearch.h" // OMNI_SITE_SEARCH_V1: site search shortcuts from OpenSearch (pure)\n'),
        ('static void omniHltFinished(Tab& tab); // OMNI_HIGHLIGHTS_V1 (OmniHighlightsShell.h): re-apply saved highlights\n',
         'static void omniHltFinished(Tab& tab); // OMNI_HIGHLIGHTS_V1 (OmniHighlightsShell.h): re-apply saved highlights\n'
         'static void omniSseFinished(Tab& tab); // OMNI_SITE_SEARCH_V1 (OmniSiteSearchShell.h): a site\'s OpenSearch description, once per site\n'),
        ('    omniHltFinished(tab); // OMNI_HIGHLIGHTS_V1: this page\'s saved highlights\n',
         '    omniHltFinished(tab); // OMNI_HIGHLIGHTS_V1: this page\'s saved highlights\n'
         '    omniSseFinished(tab); // OMNI_SITE_SEARCH_V1: offer the site\'s search as a shortcut (never private tabs)\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static bool omniOrSettingsInput(int b);\n',
         'static bool omniOrSettingsInput(int b);\n'
         'constexpr int omniSseRowOffer = 8627, omniSseRowList = 8622; // OMNI_SITE_SEARCH_V1 (OmniSiteSearchShell.h)\n'
         'static void omniSseSettingsRows(OmniFxPanel& p);\n'
         'static bool omniSseSettingsInput(int id, int b);\n'),
        ('    p.rows.back().value = omniSenRowValue(); // OMNI_SEARCH_ENGINE_V1: "Custom: <site>" / "Custom... (not set)"\n',
         '    p.rows.back().value = omniSenRowValue(); // OMNI_SEARCH_ENGINE_V1: "Custom: <site>" / "Custom... (not set)"\n'
         '    omniSseSettingsRows(p); // OMNI_SITE_SEARCH_V1: Offer site searches, Search shortcuts...\n'),
        ('    if (r.id == omniUisRowId) return omniUisSettingsInput(b); // OMNI_UI_SCALE_V1 (before the >= 300 / >= 900 rows)\n',
         '    if (r.id == omniSseRowOffer || r.id == omniSseRowList) return omniSseSettingsInput(r.id, b); // OMNI_SITE_SEARCH_V1 (before the >= 300 / >= 900 rows)\n'
         '    if (r.id == omniUisRowId) return omniUisSettingsInput(b); // OMNI_UI_SCALE_V1 (before the >= 300 / >= 900 rows)\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniClhQuickInput(const OmniFxRow& r, int b);\n',
         'static bool omniClhQuickInput(const OmniFxRow& r, int b);\n'
         'constexpr int omniSseQuickRowId = 8620; // OMNI_SITE_SEARCH_V1 (OmniSiteSearchShell.h): Add <Name> search\n'
         'static void omniSseQuickRow(OmniFxPanel& p);\n'
         'static bool omniSseQuickInput(const OmniFxRow& r, int b);\n'),
        ('        omniClhQuickRow(p); // OMNI_CLIP_HISTORY_V1: Clipboard (n), while anything is listed\n',
         '        omniClhQuickRow(p); // OMNI_CLIP_HISTORY_V1: Clipboard (n), while anything is listed\n'
         '        omniSseQuickRow(p); // OMNI_SITE_SEARCH_V1: Add <Name> search, while the shown site offers one\n'),
        ('    if (omniClhQuickInput(r, b)) return true; // OMNI_CLIP_HISTORY_V1 (before the >= 900 rows)\n',
         '    if (omniClhQuickInput(r, b)) return true; // OMNI_CLIP_HISTORY_V1 (before the >= 900 rows)\n'
         '    if (omniSseQuickInput(r, b)) return true; // OMNI_SITE_SEARCH_V1 (before the >= 900 rows)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniLinkPreviewShell.h" // OMNI_LINK_PREVIEW_V1\n',
         '#include "OmniLinkPreviewShell.h" // OMNI_LINK_PREVIEW_V1\n'
         '#include "OmniSiteSearchShell.h" // OMNI_SITE_SEARCH_V1 (uses omniStEngines, omniKbEdit, omniAsk, omniIoQueue)\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_SEARCH_TILES_V1', 'OMNI_HIGHLIGHTS_V1', 'OMNI_SITE_CLEAR_V1'),
         'OmniBrowserSettings.h': ('OMNI_SEARCH_ENGINE_V1', 'OMNI_OFFLINE_RETRY_V1', 'OMNI_UI_SCALE_V1'),
         'OmniQuickMenu.h': ('OMNI_CLIP_HISTORY_V1',),
         'OmniFeatures3.h': ('OMNI_LINK_PREVIEW_V1',)}


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
    mine = {'OmniSiteSearch.h', 'OmniSiteSearchShell.h'}
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
    for need in ('OmniSearchEngine.h', 'OmniSearchTiles.h'):
        if not (root / need).exists():
            sys.exit('%s missing: apply_search_engine.py / apply_search_tiles.py first' % need)
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        ids_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    pure = (HERE / 'OmniSiteSearch.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniSiteSearch.h: %s missing' % MARK)
    msgs = [write_new('OmniSiteSearch.h', pure, 'OmniSearchTiles.h'),
            write_new('OmniSiteSearchShell.h', SHELL, 'OmniFeatures3.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
