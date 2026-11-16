#!/usr/bin/env python3
"""OMNI_ZAPPER_V1 (2026-11-16): element zapper: hide a page element for good, saved as a uBlock cosmetic user rule.

What existed (grep of the patched tree, chain_final order)
  Omni's uBlock cosmetic filtering is the pre-compiled uBO content bundle: per-site scripts built natively from
  /data/omni/ubo-site/site-index.txt (OmniUBlockSite.h, OmniBlocker.cpp) or the full bundle in /data/omni/ubo-content/.
  Both are generated offline (outputs/ubo-site/make-ubo-site.py); nothing reads a user rule list at run time: no
  "My filters" / user-filters file exists (grep of the tree and every apply_*.py). OmniBlocker.cpp keeps only the
  per-site trusted list (/data/omni/ublock-allowlist.txt). It does offer omniSiteCssSet(key, css, allow, privateTabs)
  (OMNI_SITE_TWEAKS_V1): one user style sheet per key and controller (UserStyleLevel::User, top frame, URL allow list),
  replaced in place; WebKit restyles open pages on add / remove (no reload).

So this adds the user rules file, loaded alongside the bundled lists
  /data/omni/ublock-user-filters.txt (omniData(OmniZapper::kFileName)): a uBlock Origin "My filters" list, one filter
  per line. Lines of the form "host##selector" / "h1,h2##selector" (plain CSS) become cosmetic rules exactly as uBO
  reads them: on the host and all its subdomains (the sheet's allow pattern "*://*.host/*"; IPv4: "*://ip/*"), rule
  "selector{display:none!important}" at user level (beats the page's own !important), one rule per selector.
  Everything else (comments, network filters, generic "##x", "#@#" exceptions, "~host", entities, scriptlets "##+js",
  HTML filters "##^", procedural operators like :has-text / :style / :upward, selectors with { } ; < \\ or comments)
  is kept in the file untouched and not applied here (a later "My filters" editor, backlog S10, can grow on this).
  The sheets are registered with key "zap:<host>" in both controllers (saved rules apply in private tabs too, as uBO's
  do) once the controllers exist (omniZapTick from omniF3Tick), again when the private controller appears, and
  re-made (each second, on a change) when uBlock is switched off everywhere or for a rule's host ("uBlock on this
  site: Off" also turns these rules off, as in uBO). Caps: 256 KB / 3000 lines read, 100 zapper rules per host, 280
  characters per selector. Writes: omniIoQueue (whole file), never in private tabs or test modes.

What the user sees
  - Hold Cross on a web page: the page menu ends with "Hide this element..." (every kind of hit: link, image, page).
    Cross: the menus close, the element under the pointer gets a red outline box (a fixed, pointer-events:none div in
    the page), and a bar shows "Hide this element: div.banner  (640 x 120)" / "Matches 3 elements on this page".
    Moving the pointer re-picks (at most every 100 ms; the box is re-placed every 400 ms while still, so a scroll
    keeps it on the element). D-pad up: the parent (bigger), down: back toward the innermost element ("This is the
    biggest / smallest element here" at the ends; html / body are never picked). Circle / Options / Create: cancel.
    Cross: hidden now (inline display:none !important on every match, max 500) and saved as "host##selector"
    (host = the page host without "www."), notice "Hidden on example.com. Undo: hold Cross > Undo hide element".
    A selector matching more than 10 elements asks first ("Hide 37 elements?", "Hide all" / Cancel).
  - Private tab: the same picker, but hidden on this page only; nothing is written (notice says so).
  - Undo: the page menu shows "Undo hide element" for the last hide (same host; private: the same tab): the rule is
    removed (if this hide added it), the sheet re-made, the page's inline hide restored.
  - Site settings: a row "Hidden elements" (after Page tweaks), value = count of rules that apply on this host (its
    own and its parent domains'), "None" (disabled) or "-". Cross: a list of those selectors (the rule host on the
    right when it is a parent domain); Cross on one shows it again (rule removed); the last row "Show all again"
    asks first. Private tab: the list is read-only ("change these in a normal tab").

The selector generator (page script, OmniZapper::kCore; node fake-DOM tests: test_zapper_js.cjs)
  "#id" when the id is stable and unique; else up to 2 stable classes ".a.b" (or the tag); not unique: add the tag and
  ":nth-of-type(k)"; then the same for the parent, joined by " > ", at most 4 levels, stopping at the first unique
  selector. Generated-looking ids / classes are skipped (4+ digits in a row; css- sc- jsx- svelte- emotion- tw-
  prefixes; a 5+ token mixing letters and digits; 3+ inner capitals). The selector must match the picked element
  (Element.matches). Before saving, the shell checks the shape again (OmniZapper::generatedShape: only the
  generator's characters, cssSafe) so a page that tampered with the script can't plant arbitrary CSS.

Pure part: engine/entry/OmniZapper.h (from tools/OmniZapper.h). Tests:
  g++ -std=c++20 -Wall -Wextra -Werror -I. test_zapper.cpp -o t && ./t core.js && node test_zapper_js.cjs core.js
Shell part: engine/entry/OmniZapperShell.h (written here), alias OZAP, names omniZap*.
Ids: Site settings row 7925, page menu rows 9925 / 9926 (unused in the tree and in every sibling's code).

Anchors (each once; whole lines; new lines after them, the Site settings input line before its anchor):
  OmniBrowser.cpp    the OmniSiteTweaks.h include line (pure include after)
  OmniContextMenu.h  the omniTslContextAction declaration (declarations after); the context panel's
                     "p.build = omniFxContextBuild; p.input = omniFxContextInput;" line (omniZapWrapContext after: the
                     rows go last in every kind of page menu); the omniTslContextAction call (our action after)
  OmniQuickMenu.h    the omniStSiteInput declaration (declarations after); the omniStSiteRow call (row after); the
                     omniStSiteRowId input line (our input before it)
  OmniFeatures3.h    the OmniSiteTweaksShell.h include line (shell include after); the omniScTick line (tick after)
Apply AFTER apply_text_select.py, apply_site_css.py, apply_site_clear.py (their lines are anchors).
usage: apply_zapper.py <engine tree>   (anchored, idempotent, keeps each file's line endings; re-run: "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_ZAPPER_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_zapper.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('7925', '9925', '9926')
NAMES = ('OZAP', 'omniZap', 'OmniZapper', 'OMNI_ZAPPER')

SHELL = r'''// OMNI_ZAPPER_V1: the element zapper (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous
// namespace, after OmniSiteTweaksShell.h). The pure part (rules file, sheets, selector checks, page script, texts) is
// OmniZapper.h; the reasons are in tools/apply_zapper.py. Main thread only; the file is written by omniIoQueue.
#pragma once

namespace OZAP = OmniZapper;

// --- the user rules file and its sheets ------------------------------------------------------------------------------
static OZAP::Store omniZapStore;
static bool omniZapLoaded = false, omniZapInstalled = false, omniZapHadPrivate = false;
static std::vector<std::string> omniZapSheetHosts;   // rule hosts with a registered sheet
static std::string omniZapSig;                       // uBlock on / off + trusted sites when the sheets were made
static uint32_t omniZapSigAt = 0;

static void omniZapLoad()
{
    if (omniZapLoaded) return;
    omniZapLoaded = true;
    FILE* f = fopen(omniData(OZAP::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && text.size() <= OZAP::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    omniZapStore = OZAP::parse(text);
}
static void omniZapWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OZAP::kFileName), OZAP::serialize(omniZapStore), false);
}
static std::string omniZapSignature()
{
    std::string s = omniBlockerEnabled() ? "1" : "0";
    for (const auto& h : omniBlockerTrustedSites()) s += "|" + h;
    return s;
}
// Every rule host's sheet in both controllers (css "" removes it: uBlock off everywhere or for that host).
static void omniZapSync()
{
    omniZapLoad();
    const bool on = omniBlockerEnabled();
    std::vector<std::string> hosts;
    for (const auto& [host, css] : OZAP::sheets(omniZapStore)) {
        const std::string key = "zap:" + host;
        const auto allow = OZAP::allowPatterns(host);
        const std::string sheet = on && !omniBlockerSiteTrusted(host) ? css : std::string();
        omniSiteCssSet(key, sheet, allow, false);
        omniSiteCssSet(key, sheet, allow, true);
        hosts.push_back(host);
    }
    for (const auto& old : omniZapSheetHosts) {
        if (std::find(hosts.begin(), hosts.end(), old) != hosts.end()) continue;
        omniSiteCssSet("zap:" + old, std::string(), {}, false);
        omniSiteCssSet("zap:" + old, std::string(), {}, true);
    }
    omniZapSheetHosts.swap(hosts);
    omniZapHadPrivate = omniBlockerPrivateController() != nullptr;
    omniZapSig = omniZapSignature();
}

// --- the picker -------------------------------------------------------------------------------------------------------
struct OmniZapState {
    bool on = false;                 // picking: the layer is open
    const void* tab = nullptr;       // the tab whose page shows the box
    uint32_t gen = 0;                // results of an older pick are dropped
    bool priv = false;
    std::string host;                // the page's host (no "www."): the rule host
    std::string sel, label;          // the picked element's selector / short name
    int n = 0, w = 0, h = 0;
    int pending = 0;                 // page queries not answered yet
    uint32_t lastAt = 0;             // the last query sent
    float lastX = -1, lastY = -1;    // the pointer when the last pick was asked
};
static OmniZapState omniZap;
static uint32_t omniZapGen = 0;
struct OmniZapLast {                 // the last hide, for Undo
    bool on = false, priv = false, saved = false;
    const void* tab = nullptr;
    std::string host, sel;
};
static OmniZapLast omniZapLast;
struct OmniZapQuery { const void* tab; uint32_t gen; int op; };

static void omniZapResult(OZAP::Op op, const std::string& json);
static void omniZapEnd(bool clearPage);
// track: a picker query (its answer updates the bar); otherwise fire and forget (hide / unhide / clear).
static void omniZapEval(Tab* t, OZAP::Op op, double layoutX, double layoutY, const std::string& sel, bool track)
{
    if (!t || t->crashed) return;
    const double k = omniFxCssPerLayout(t);
    const std::string js = OZAP::script(op, layoutX * k, (layoutY - omniPageTop()) * k, sel);
    auto src = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    auto* q = new OmniZapQuery { t, track ? omniZap.gen : 0u, int(op) };
    if (track) { ++omniZap.pending; omniZap.lastAt = SDL_GetTicks(); }
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), q, [](WKTypeRef result, WKErrorRef error, void* context) {
        std::unique_ptr<OmniZapQuery> q(static_cast<OmniZapQuery*>(context));
        if (!q->gen || q->gen != omniZap.gen) return;
        if (omniZap.pending > 0) --omniZap.pending;
        if (!omniTabAlive(q->tab) || active() != q->tab) { omniZapEnd(false); return; }
        omniZapResult(OZAP::Op(q->op), omniFxResultString(result, error));
    });
}
static Tab* omniZapTab(const void* tab) { return tab && omniTabAlive(tab) ? static_cast<Tab*>(const_cast<void*>(tab)) : nullptr; }
static void omniZapEnd(bool clearPage)
{
    if (clearPage) if (Tab* t = omniZapTab(omniZap.tab)) omniZapEval(t, OZAP::Op::Clear, 0, 0, std::string(), false);
    const uint32_t gen = ++omniZapGen;
    omniZap = OmniZapState();
    omniZap.gen = gen;
    omniShellDirty = true;
}
// px, py: the layout point the page menu was opened at.
static void omniZapStart(int px, int py)
{
    Tab* t = active();
    if (!t || t->crashed) return;
    const std::string host = omniWebURL(t->url) ? omniBlockerHostOf(t->url) : std::string();
    if (host.empty()) { notice("Elements can only be hidden on web pages"); return; }
    omniZapEnd(omniZap.tab != nullptr);   // a fresh generation (never 0: 0 marks fire-and-forget queries)
    omniZap.tab = t;
    omniZap.priv = t->omniPrivate;
    omniZap.host = host;
    omniZap.lastX = float(px);
    omniZap.lastY = float(py);
    omniZapEval(t, OZAP::Op::Start, px, py, std::string(), true);
}
static void omniZapResult(OZAP::Op op, const std::string& json)
{
    double ok = 0, n = 0, w = 0, h = 0, edge = 0;
    omniFxJsonNumber(json, "ok", ok);
    if (op == OZAP::Op::Sync) {
        if (ok <= 0) { omniZapEnd(false); notice("The element is gone (the page changed)"); }
        return;
    }
    if (ok <= 0) {
        const bool start = op == OZAP::Op::Start;
        omniZapEnd(!start);
        notice(start ? "Nothing to hide here: hold Cross over the part of the page to hide" : "The element is gone (the page changed)");
        return;
    }
    if (op == OZAP::Op::Start) {
        if (editing || settingsOpen || pageFullscreen || omniOverlayOpen()) { omniZapEnd(true); return; }   // something opened meanwhile
        omniZap.on = true;
    }
    omniFxJsonString(json, "sel", omniZap.sel);
    omniFxJsonString(json, "label", omniZap.label);
    omniFxJsonNumber(json, "n", n);
    omniFxJsonNumber(json, "w", w);
    omniFxJsonNumber(json, "h", h);
    omniZap.n = int(n); omniZap.w = int(w); omniZap.h = int(h);
    if (omniFxJsonNumber(json, "edge", edge) && edge > 0)
        notice(op == OZAP::Op::Up ? "This is the biggest element here" : "This is the smallest element here");
    omniShellDirty = true;
}
static void omniZapHideNow(const std::string& sel)
{
    Tab* t = active();
    if (!t || t != omniZap.tab) { omniZapEnd(false); return; }
    const bool priv = omniZap.priv;
    const std::string host = omniZap.host;
    omniZapEval(t, OZAP::Op::Hide, 0, 0, sel, false);   // also removes the box
    OZAP::Added a = OZAP::Added::Invalid;
    if (!priv) {
        omniZapLoad();
        a = OZAP::add(omniZapStore, host, sel);
        if (a == OZAP::Added::Ok) { omniZapWrite(); omniZapSync(); }
        fprintf(stderr, "OMNI ZAPPER: %s##%s (%d)\n", host.c_str(), sel.c_str(), int(a)); fflush(stderr);
    }
    omniZapLast = OmniZapLast();
    omniZapLast.on = true; omniZapLast.priv = priv; omniZapLast.saved = a == OZAP::Added::Ok;
    omniZapLast.tab = t; omniZapLast.host = host; omniZapLast.sel = sel;
    omniZapEnd(false);
    notice(OZAP::hiddenNotice(host, priv, a));
}
static void omniZapConfirm()
{
    if (omniZap.pending > 0) return;                    // the bar is about to change: the next press uses it
    const std::string sel = omniZap.sel;
    if (sel.empty() || !OZAP::generatedShape(sel)) { notice("No rule for this element: D-pad up picks a bigger one"); return; }
    if (omniZap.n > OZAP::kConfirmOver) {
        const void* tab = omniZap.tab;
        const uint32_t gen = omniZap.gen;
        omniAsk(OZAP::askManyTitle(omniZap.n), OZAP::askManyBody(sel, omniZap.n, omniZap.host, omniZap.priv), "Hide all", [sel, tab, gen](bool ok) {
            if (!ok || gen != omniZap.gen || !omniZap.on || active() != tab) return;
            omniZapHideNow(sel);
        });
        return;
    }
    omniZapHideNow(sel);
}
// From omniF3Tick: the sheets once the controllers exist (and when uBlock's switches change); the picker follows
// the pointer and keeps the box on its element.
static bool omniZapOpen();
static void omniZapTick(uint32_t now)
{
    if (!omniZapInstalled) {
        if (omniBlockerController()) {
            omniZapInstalled = true;
            omniZapSync();
            fprintf(stderr, "OMNI ZAPPER: %d host(s) with hidden elements\n", int(omniZapSheetHosts.size())); fflush(stderr);
        }
    } else if (uint32_t(now - omniZapSigAt) >= 1000) {
        omniZapSigAt = now;
        if ((!omniZapHadPrivate && omniBlockerPrivateController()) || omniZapSignature() != omniZapSig) omniZapSync();
    }
    if (!omniZapOpen() || omniModalVisible() || omniFxPanelOpen() || editing) return;
    if (omniZap.pending > 0) {
        if (uint32_t(now - omniZap.lastAt) < OZAP::kBusyMs) return;
        omniZap.pending = 0;                           // a page that never answers
    }
    const uint32_t since = uint32_t(now - omniZap.lastAt);
    const bool moved = std::fabs(pointerX - omniZap.lastX) + std::fabs(pointerY - omniZap.lastY) >= 4.0f;
    if (moved && since >= OZAP::kFollowMs && pointerY >= omniPageTop()) {
        omniZap.lastX = pointerX; omniZap.lastY = pointerY;
        omniZapEval(active(), OZAP::Op::Move, pointerX, pointerY, std::string(), true);
    } else if (since >= OZAP::kSyncMs) omniZapEval(active(), OZAP::Op::Sync, 0, 0, std::string(), true);
}

// --- the picking layer: a bar over the page, every button taken -----------------------------------------------------
static bool omniZapOpen()
{
    if (!omniZap.on) return false;
    if (!omniTabAlive(omniZap.tab) || active() != omniZap.tab || active()->crashed || pageFullscreen) { omniZapEnd(true); return false; }
    return true;
}
static bool omniZapButton(int b)
{
    switch (b) {
    case SDL_CONTROLLER_BUTTON_DPAD_UP: omniZapEval(active(), OZAP::Op::Up, 0, 0, std::string(), true); break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: omniZapEval(active(), OZAP::Op::Down, 0, 0, std::string(), true); break;
    case SDL_CONTROLLER_BUTTON_A: omniZapConfirm(); break;
    case SDL_CONTROLLER_BUTTON_B: case SDL_CONTROLLER_BUTTON_BACK: case SDL_CONTROLLER_BUTTON_START: omniZapEnd(true); break;
    default: break;                                   // the other buttons do nothing while picking
    }
    omniShellDirty = true;
    return true;
}
static bool omniZapClick(int, int)
{
    if (omniPtrCross.inCross) omniZapConfirm();       // Cross while the pointer leads: hide, as Cross
    else omniZapEnd(true);                            // a mouse click: cancel
    return true;
}
static void omniZapDraw()
{
    const OmniTheme& T = omniTheme();
    const int w = std::min(820, width - 40), h = 66, x = (width - w) / 2;
    const bool low = pointerY < omniPageTop() + (height - omniPageTop()) / 3;   // pointer high up: the bar goes low
    const int y = low ? height - h - 96 : omniPageTop() + 14;
    omniShadow(x, y, w, h, omniRadius + 2, 14, 140, 4);
    fillRounded(x, y, w, h, omniRadius + 2, T.panel);
    omniLabel(omniZap.label.empty() ? std::string("Hide this element") : OZAP::barTitle(omniZap.label, omniZap.w, omniZap.h),
        x + 24, y + 22, omniBodyBold, T.ink, 0, w - 48);
    omniLabel(omniZap.sel.empty() ? OZAP::barDetail(0, omniZap.priv) : OZAP::barDetail(omniZap.n, omniZap.priv), x + 24, y + 47, omniSmall, T.inkDim, 0, w - 48);
    if (!omniFxPanelOpen() && !editing) omniPanelHints({ { 0, "Hide" }, { 1, "Cancel" } }, "D-pad up / down: bigger / smaller");
}
[[maybe_unused]] static const bool omniZapLayers = [] {
    omniOverlayLayers().push_back({ omniZapOpen, omniZapButton, omniZapClick, nullptr, omniZapDraw, true });
    return true;
}();

// --- Undo -----------------------------------------------------------------------------------------------------------
static bool omniZapUndoable(Tab* t)
{
    if (!t || !omniZapLast.on) return false;
    if (omniZapLast.priv) return omniZapLast.tab == t;
    return omniWebURL(t->url) && omniBlockerHostOf(t->url) == omniZapLast.host;
}
static void omniZapUndo()
{
    const OmniZapLast last = omniZapLast;
    omniZapLast = OmniZapLast();
    if (!last.on) return;
    if (last.saved) {
        omniZapLoad();
        OZAP::remove(omniZapStore, last.host, last.sel);
        omniZapWrite();
        omniZapSync();
    }
    if (Tab* t = omniZapTab(last.tab)) omniZapEval(t, OZAP::Op::Unhide, 0, 0, last.sel, false);
    if (active() && active() != last.tab) omniZapEval(active(), OZAP::Op::Unhide, 0, 0, last.sel, false);
    notice("Shown again: " + OZAP::shortSel(last.sel));
}

// --- hold-Cross page menu: our rows go last, whatever the menu shows -------------------------------------------------
static OmniFxBuild omniZapInnerBuild = nullptr;
static void omniZapContextBuild(OmniFxPanel& p)
{
    if (omniZapInnerBuild) omniZapInnerBuild(p);
    Tab* t = active();
    if (!t || t->crashed || !omniWebURL(t->url) || omniBlockerHostOf(t->url).empty()) return;
    OmniFxRow r; r.id = OZAP::kContextId; r.label = "Hide this element...";
    p.rows.push_back(r);
    if (omniZapUndoable(t)) {
        OmniFxRow u; u.id = OZAP::kUndoId; u.label = "Undo hide element"; u.value = OZAP::shortSel(omniZapLast.sel, 28);
        p.rows.push_back(u);
    }
}
static void omniZapWrapContext(OmniFxPanel& p)
{
    if (p.build == omniZapContextBuild) return;
    omniZapInnerBuild = p.build;
    p.build = omniZapContextBuild;
}
static bool omniZapContextAction(OmniFxPanel& p, int id)
{
    if (id == OZAP::kContextId) {
        const int px = p.anchorX, py = p.anchorY;   // p is gone after omniFxCloseAll
        omniFxCloseAll();
        omniZapStart(px, py);
        return true;
    }
    if (id == OZAP::kUndoId) { omniFxCloseAll(); omniZapUndo(); return true; }
    return false;
}

// --- Site settings > Hidden elements ----------------------------------------------------------------------------------
enum { omniZapRowAll = 1, omniZapRowFirst = 100 };
static std::string omniZapPageHost()
{
    Tab* t = active();
    return t && omniWebURL(t->url) ? omniBlockerHostOf(t->url) : std::string();
}
static void omniZapSiteRow(OmniFxPanel& p, const std::string&)
{
    omniZapLoad();
    const std::string host = omniZapPageHost();
    const size_t n = host.empty() ? 0 : OZAP::rulesFor(omniZapStore, host).size();
    OmniFxRow r; r.id = OZAP::kSiteRowId; r.label = "Hidden elements";
    r.value = host.empty() ? std::string("-") : OZAP::rowValue(n);
    r.enabled = n > 0;
    p.rows.push_back(r);
}
static void omniZapPanelBuild(OmniFxPanel& p)
{
    omniZapLoad();
    const auto list = OZAP::rulesFor(omniZapStore, p.page);
    const bool priv = p.mode == 1;
    p.subtitle = p.page + ": " + OZAP::plural(int(list.size()), "rule", "rules") + (priv ? ". Private tab: change these in a normal tab" : "");
    for (size_t i = 0; i < list.size() && i < 400; ++i) {
        OmniFxRow r; r.id = omniZapRowFirst + int(i); r.label = OZAP::shortSel(list[i].selector, 70);
        r.value = list[i].host == p.page ? std::string() : list[i].host;
        r.enabled = !priv;
        p.rows.push_back(r);
    }
    OmniFxRow r;
    if (list.empty()) { r.id = 0; r.label = "Nothing hidden on this site"; r.enabled = false; }
    else { r.id = omniZapRowAll; r.label = "Show all again"; r.enabled = !priv; r.danger = !priv; }
    p.rows.push_back(r);
}
static void omniZapShowAgain(const OZAP::Rule& x)
{
    OZAP::remove(omniZapStore, x.host, x.selector);
    if (omniZapLast.on && omniZapLast.host == x.host && omniZapLast.sel == x.selector) omniZapLast = OmniZapLast();
    if (active()) omniZapEval(active(), OZAP::Op::Unhide, 0, 0, x.selector, false);   // a hide made on this page
}
static bool omniZapPanelInput(OmniFxPanel& p, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (!r.enabled || p.mode == 1) return true;
    omniZapLoad();
    const std::string host = p.page;
    const auto list = OZAP::rulesFor(omniZapStore, host);
    if (r.id == omniZapRowAll) {
        omniAsk("Show all hidden elements on " + host + "?", "Your " + OZAP::plural(int(list.size()), "rule", "rules")
            + " for this site are removed from ublock-user-filters.txt.", "Show all", [host](bool ok) {
            if (!ok) return;
            for (const auto& x : OZAP::rulesFor(omniZapStore, host)) omniZapShowAgain(x);
            omniZapWrite();
            omniZapSync();
            omniFxRefresh();
            notice("Hidden elements shown again on " + host);
        });
        return true;
    }
    if (r.id < omniZapRowFirst || size_t(r.id - omniZapRowFirst) >= list.size()) return true;
    const OZAP::Rule x = list[size_t(r.id - omniZapRowFirst)];
    omniZapShowAgain(x);
    omniZapWrite();
    omniZapSync();
    notice("Shown again: " + OZAP::shortSel(x.selector));
    omniFxRefresh();
    return true;
}
static bool omniZapSiteInput(const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    const std::string host = omniZapPageHost();
    if (!r.enabled || host.empty() || !active()) return true;
    OmniFxPanel p;
    p.title = "Hidden elements"; p.w = 760;
    p.page = host; p.mode = active()->omniPrivate ? 1 : 0;   // fixed while the panel is open
    p.build = omniZapPanelBuild; p.input = omniZapPanelInput;
    p.faces = { { 0, "Show again" }, { 1, "Back" } };
    p.extra = "Saved in ublock-user-filters.txt (uBlock syntax)";
    omniFxPush(std::move(p));
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSiteTweaks.h" // OMNI_SITE_TWEAKS_V1: Page tweaks per site, site-tweaks.txt (pure)\n',
         '#include "OmniSiteTweaks.h" // OMNI_SITE_TWEAKS_V1: Page tweaks per site, site-tweaks.txt (pure)\n'
         '#include "OmniZapper.h" // OMNI_ZAPPER_V1: element zapper, ublock-user-filters.txt (pure)\n'),
    ],
    'OmniContextMenu.h': [
        ('static bool omniTslContextAction(OmniFxPanel& p, int id);\n',
         'static bool omniTslContextAction(OmniFxPanel& p, int id);\n'
         'static void omniZapWrapContext(OmniFxPanel& p); /* OMNI_ZAPPER_V1 (OmniZapperShell.h): rows last in every page menu */\n'
         'static bool omniZapContextAction(OmniFxPanel& p, int id); /* OMNI_ZAPPER_V1 */\n'),
        ('    p.build = omniFxContextBuild; p.input = omniFxContextInput;\n',
         '    p.build = omniFxContextBuild; p.input = omniFxContextInput;\n'
         '    omniZapWrapContext(p); /* OMNI_ZAPPER_V1: Hide this element... / Undo hide element */\n'),
        ('    if (omniTslContextAction(p, r.id)) return true; // OMNI_TEXT_SELECT_V1\n',
         '    if (omniTslContextAction(p, r.id)) return true; // OMNI_TEXT_SELECT_V1\n'
         '    if (omniZapContextAction(p, r.id)) return true; /* OMNI_ZAPPER_V1 */\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniStSiteInput(const OmniFxRow& r, int b);\n',
         'static bool omniStSiteInput(const OmniFxRow& r, int b);\n'
         'static void omniZapSiteRow(OmniFxPanel& p, const std::string& host); /* OMNI_ZAPPER_V1 (OmniZapperShell.h) */\n'
         'static bool omniZapSiteInput(const OmniFxRow& r, int b); /* OMNI_ZAPPER_V1 */\n'),
        ('    omniStSiteRow(p, host); // OMNI_SITE_TWEAKS_V1: Page tweaks\n',
         '    omniStSiteRow(p, host); // OMNI_SITE_TWEAKS_V1: Page tweaks\n'
         '    omniZapSiteRow(p, host); /* OMNI_ZAPPER_V1: Hidden elements */\n'),
        ('    if (r.id == omniStSiteRowId) return omniStSiteInput(r, b); // OMNI_SITE_TWEAKS_V1 (handles its disabled state)\n',
         '    if (r.id == OmniZapper::kSiteRowId) return omniZapSiteInput(r, b); /* OMNI_ZAPPER_V1 (handles its disabled state) */\n'
         '    if (r.id == omniStSiteRowId) return omniStSiteInput(r, b); // OMNI_SITE_TWEAKS_V1 (handles its disabled state)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniSiteTweaksShell.h" // OMNI_SITE_TWEAKS_V1\n',
         '#include "OmniSiteTweaksShell.h" // OMNI_SITE_TWEAKS_V1\n'
         '#include "OmniZapperShell.h" /* OMNI_ZAPPER_V1: element zapper (page menu, picking layer, Hidden elements) */\n'),
        ('    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n',
         '    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n'
         '    omniZapTick(now);   /* OMNI_ZAPPER_V1: user rule sheets; the picker follows the pointer */\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_SITE_TWEAKS_V1',),
         'OmniContextMenu.h': ('OMNI_TEXT_SELECT_V1',),
         'OmniQuickMenu.h': ('OMNI_SITE_TWEAKS_V1',),
         'OmniFeatures3.h': ('OMNI_SITE_TWEAKS_V1', 'OMNI_SITE_CLEAR_V1_R2')}


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
    mine = {'OmniZapper.h', 'OmniZapperShell.h'}
    # A sibling not applied to this tree yet still owns its ids: its code (generated headers / edits included,
    # comments and docstring stripped) assigning one of ours to a row id ("kRowId = 9925", "kContextId = 9925",
    # "r.id = 9925", "constexpr int x = 9925") is a clash.
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
    pure = (HERE / 'OmniZapper.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniZapper.h: %s missing' % MARK)
    msgs = [write_new('OmniZapper.h', pure, 'OmniSiteTweaks.h'),
            write_new('OmniZapperShell.h', SHELL, 'OmniSiteTweaksShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
