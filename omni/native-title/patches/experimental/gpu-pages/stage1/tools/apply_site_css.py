#!/usr/bin/env python3
"""OMNI_SITE_TWEAKS_V1 (2026-11-16): Site settings > "Page tweaks": TV-friendly per-site page tweaks, no CSS typing.

What the user sees
  - Site settings (Options > Site settings) has a new row after "Clear data for this site":
        "Page tweaks"     value: "Off" / "1 on" / "3 on" (what this tab uses), "-" on omni:// / about: / file: pages
    Cross opens a small panel (title "Page tweaks", subtitle the site, "(private tab: this session only)" there):
        Bigger text                    Off / +15% / +30%   (Cross / D-pad right: next, D-pad left: previous)
        Hide sticky headers/footers    On / Off
        Wider text column              On / Off
        Larger focus outline           On / Off
        Reset tweaks for this site     (only when something is on)
        Cookie banners   Hidden by uBlock   (greyed: information only, see below)
    Every change applies to the open page at once (no reload) and to every later page of that site; a notice says
    "Bigger text +15% on example.com" (+ " (private tabs, this session)" in a private tab).
  - Sites: the page's host without "www." (www.example.com and example.com share one entry; sub.example.com has its
    own). Only http / https pages; IPv6-literal hosts are left out (WebKit's URL patterns can't name them).
  - Private tabs (the autoplay r2 rule, OmniAutoplayShell.h): a choice made in a private tab lasts for this run, applies
    to private tabs only and is never written; a normal tab shows and changes the saved choice only, never the
    private one. Private tabs use the saved choice until one is made there.

"Hide cookie banners" is NOT a toggle: the bundled uBlock Origin Lite rulesets (engine/resources/ubo-content/
manifest.json) already include "annoyances-cookies" (EasyList/uBO - Cookie Notices: 13,380 generic + 20,613
site-specific cosmetic rules, plus its scriptlets), injected for every site where uBlock is on. A second, cruder
selector list here would only add cost. When uBlock is off for a site, its banners show (as with every other filter).

How (the mechanism)
  The per-site sheets are WebKit user style sheets (API::UserStyleSheet, UserStyleLevel::User so their !important
  beats the page's own !important; top frame only; allow list = "*://<host>/*" + "*://www.<host>/*", which WebKit's
  UserContentURLPattern matches on http and https, any port). That is the add-on style sheet path
  (omniAddonsAddStyleSheet in OmniBlocker.cpp); dark pages' per-site switch could not be reused as is, because it
  pushes versioned config *scripts* that can never be removed. A new OmniBlocker.cpp function,
      bool omniSiteCssSet(key, css, allow, privateTabs)
  keeps one sheet per site and per controller (normal tabs: the shared controller; private tabs: privateController
  only, so normal tabs never get a private choice) and replaces it in place (remove + add; empty css = remove).
  WebUserContentController::addUserStyleSheets / removeUserStyleSheet call
  invalidateInjectedStyleSheetCacheInAllFramesInAllPages(), so open pages restyle without a reload.
  omniStTick (from omniF3Tick) installs the saved sites once, as soon as omniBlockerController() exists.

The CSS (OmniSiteTweaks::css, one rule per toggle so an unknown selector can only drop its own rule):
  Bigger text   html{font-size:115%|130%!important}. Root font size, not WebKit page zoom (site zoom stays separate):
                rem / em / % text grows and the layout width stays. Limits: text a page sizes in px does not change
                (no CSS can scale it without zoom); a page whose root is 62.5% grows more than 15%.
  Sticky bars   position:static!important on header, footer, [role=banner|contentinfo], sticky / fixed-top / fixed-
                bottom / navbar-fixed / is-fixed / is-stuck / is-pinned / headroom class names, [id*=sticky], and
                inline position:fixed|sticky; never html, body, dialog, video, iframe, [role=dialog|alertdialog],
                [aria-modal=true], nor anything that :has() a video / iframe / dialog (players and modals stay).
                A user style sheet can't read computed styles, so this is by selector: a relatively positioned
                header loses its positioning context (its absolutely placed menus may move).
  Wider column  max-width:none!important on main, article, [role=main] and their direct children except
                img / video / picture / svg / canvas / iframe / embed / object / audio / figure / table / pre.
  Focus ring    :focus-visible{outline:4px solid #ffd400; outline-offset:3px; box-shadow 0 0 0 7px rgba(0,0,0,.85)}
                (all !important): yellow on a dark halo, visible on light and dark pages.

File: /data/omni/site-tweaks.txt (omniIoQueue, whole file): "# Omni page tweaks v1", then "<host>\\t<tokens>" with
tokens text=15 | text=30, sticky, wide, focus. Unknown tokens are skipped; at most 500 sites (a new site is
refused with a notice when full); 256 KB read cap. Nothing is written in test mode.

Pure part: engine/entry/OmniSiteTweaks.h (no SDL / WebKit): URL -> host key, allow patterns, file parse / serialize,
normal / private choice split, text stepper, CSS per toggle set, texts.
Tested by tools/test_site_tweaks.cpp:  g++ -std=c++20 -Wall -Wextra -Wshadow -I<tree>/engine/entry test_site_tweaks.cpp
Shell side: engine/entry/OmniSiteTweaksShell.h (included from OmniFeatures3.h after OmniSiteClearShell.h).

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp   the OmniSiteClear.h include line (apply_site_clear.py's): the pure include.
  OmniQuickMenu.h   the omniScSiteInput declaration, the omniScSiteRow call, the omniScSiteRowId input line
                    (all apply_site_clear.py's). Row id 740 (site rows: 710 autoplay, 720 https-only, 730 clear;
                    the panel sends ids >= 300 to features-3 and >= 900 to features-2, so 740 is dispatched first).
  OmniFeatures3.h   the OmniSiteClearShell.h include line; the omniScTick line of omniF3Tick (omniStTick after it).
  OmniBlocker.h     the omniAddonsRemove declaration (omniSiteCssSet after it).
  OmniBlocker.cpp   the omniAddonsRemove definition's first two lines (omniSiteCssSet goes before them).
Apply AFTER apply_site_clear.py (its lines are anchors).
usage: apply_site_css.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_SITE_TWEAKS_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_SITE_TWEAKS_V1: the pure part of Site settings > "Page tweaks" (no SDL, no WebKit): per-site reading tweaks
// for a TV (bigger text, no sticky bars, no text column limit, a strong focus ring) as one user style sheet per site.
// The shell side is OmniSiteTweaksShell.h; the reasons are in tools/apply_site_css.py. Tested on the host with g++
// (tools/test_site_tweaks.cpp).
#pragma once
#include <cstddef>
#include <map>
#include <string>
#include <vector>

namespace OmniSiteTweaks {

constexpr const char* kFileName = "site-tweaks.txt";
constexpr const char* kHeader = "# Omni page tweaks v1";
constexpr size_t kHostMax = 253;
constexpr size_t kMaxSites = 500;
constexpr long kMaxFileBytes = 256 * 1024;

struct Tweaks {
    int text = 0;          // 0, 15 or 30: html font-size +15% / +30%
    bool sticky = false;   // hide (unstick) sticky / fixed headers and footers
    bool wide = false;     // no max-width on main / article (and their non-media children)
    bool focus = false;    // strong :focus-visible ring
    bool any() const { return text || sticky || wide || focus; }
    bool operator==(const Tweaks& o) const { return text == o.text && sticky == o.sticky && wide == o.wide && focus == o.focus; }
    bool operator!=(const Tweaks& o) const { return !(*this == o); }
};
struct Store {
    std::map<std::string, Tweaks> sites;   // only entries with any() (siteKey hosts)
};
using Session = std::map<std::string, Tweaks>;   // private-tab choices: this run, private tabs only

inline int validText(int v) { return v == 15 || v == 30 ? v : 0; }

// --- hosts -------------------------------------------------------------------------------------------------------
inline bool isIPv4(const std::string& h)
{
    int parts = 0, digits = 0, value = 0;
    for (size_t i = 0; i <= h.size(); ++i) {
        if (i == h.size() || h[i] == '.') {
            if (!digits || value > 255) return false;
            ++parts; digits = 0; value = 0;
            continue;
        }
        if (h[i] < '0' || h[i] > '9' || ++digits > 3) return false;
        value = value * 10 + (h[i] - '0');
    }
    return parts == 4;
}
// A stored host: lower case, no trailing dot, no "www." (www.example.com and example.com share one entry), only
// [a-z0-9.-_]. IPv6 literals are refused (WebKit's user-content URL patterns can't name them: ':' reads as a port).
inline bool validKey(const std::string& h)
{
    if (h.empty() || h.size() > kHostMax || h.front() == '.' || h.back() == '.' || h.compare(0, 4, "www.") == 0) return false;
    for (char c : h)
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_')) return false;
    return h.find("..") == std::string::npos;
}
// http(s) URL -> stored host ("" for anything else: omni://, about:, file:, data:, IPv6 literals).
inline std::string siteKey(const std::string& url)
{
    auto starts = [&](const char* p, size_t n) {
        if (url.size() < n) return false;
        for (size_t i = 0; i < n; ++i) {
            char c = url[i];
            if (c >= 'A' && c <= 'Z') c = char(c + ('a' - 'A'));
            if (c != p[i]) return false;
        }
        return true;
    };
    size_t start;
    if (starts("https://", 8)) start = 8;
    else if (starts("http://", 7)) start = 7;
    else return std::string();
    size_t end = url.find_first_of("/?#", start);
    if (end == std::string::npos) end = url.size();
    std::string auth = url.substr(start, end - start);
    const size_t at = auth.rfind('@');
    if (at != std::string::npos) auth = auth.substr(at + 1);
    if (!auth.empty() && auth[0] == '[') return std::string();
    std::string host = auth.substr(0, auth.find(':'));
    for (auto& c : host) if (c >= 'A' && c <= 'Z') c = char(c + ('a' - 'A'));
    while (!host.empty() && host.back() == '.') host.pop_back();
    if (host.compare(0, 4, "www.") == 0 && host.size() > 4) host = host.substr(4);
    return validKey(host) ? host : std::string();
}
// WebKit UserContentURLPattern allow list for a stored host: the host itself and its www. twin, http and https
// ("*" scheme), any port (patterns carry none), any path. Subdomains other than www. are not included.
inline std::vector<std::string> allowPatterns(const std::string& key)
{
    std::vector<std::string> out;
    if (!validKey(key)) return out;
    out.push_back("*://" + key + "/*");
    if (!isIPv4(key)) out.push_back("*://www." + key + "/*");
    return out;
}
// What those patterns match (UserContentURLPattern::matchesHost without subdomains, case-insensitive): used by the
// tests to pin the rule, and by the shell nowhere else.
inline bool patternMatchesHost(const std::string& key, const std::string& host0)
{
    std::string host;
    for (char c : host0) host += (c >= 'A' && c <= 'Z') ? char(c + ('a' - 'A')) : c;
    for (const auto& p : allowPatterns(key)) {
        const std::string h = p.substr(4, p.size() - 6);   // "*://" ... "/*"
        if (h == host) return true;
    }
    return false;
}

// --- file ---------------------------------------------------------------------------------------------------------
// "# Omni page tweaks v1" then one line per site: "<host>\t<tokens>", tokens space separated:
// text=15 | text=30, sticky, wide, focus. Unknown tokens are skipped (a newer Omni's file still loads).
inline Tweaks parseTokens(const std::string& s)
{
    Tweaks t;
    size_t i = 0;
    while (i < s.size()) {
        while (i < s.size() && (s[i] == ' ' || s[i] == ',')) ++i;
        size_t j = i;
        while (j < s.size() && s[j] != ' ' && s[j] != ',') ++j;
        const std::string tok = s.substr(i, j - i);
        if (tok == "text=15") t.text = 15;
        else if (tok == "text=30") t.text = 30;
        else if (tok == "sticky") t.sticky = true;
        else if (tok == "wide") t.wide = true;
        else if (tok == "focus") t.focus = true;
        i = j;
    }
    return t;
}
inline std::string tokens(const Tweaks& t)
{
    std::string s;
    auto add = [&](const std::string& x) { if (!s.empty()) s += ' '; s += x; };
    if (t.text) add("text=" + std::to_string(validText(t.text)));
    if (t.sticky) add("sticky");
    if (t.wide) add("wide");
    if (t.focus) add("focus");
    return s;
}
inline Store parse(const std::string& text)
{
    Store st;
    size_t pos = 0;
    while (pos < text.size() && st.sites.size() < kMaxSites) {
        size_t nl = text.find('\n', pos);
        if (nl == std::string::npos) nl = text.size();
        std::string line = text.substr(pos, nl - pos);
        pos = nl + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty() || line[0] == '#') continue;
        const size_t tab = line.find('\t');
        if (tab == std::string::npos) continue;
        const std::string host = line.substr(0, tab);
        if (!validKey(host)) continue;
        const Tweaks t = parseTokens(line.substr(tab + 1));
        if (t.any()) st.sites[host] = t;
    }
    return st;
}
inline std::string serialize(const Store& st)
{
    std::string s = std::string(kHeader) + "\n";
    for (const auto& [h, t] : st.sites)
        if (t.any() && validKey(h)) s += h + "\t" + tokens(t) + "\n";
    return s;
}

// --- choices --------------------------------------------------------------------------------------------------------
inline Tweaks saved(const Store& st, const std::string& key)
{
    auto it = st.sites.find(key);
    return it == st.sites.end() ? Tweaks() : it->second;
}
// What a tab of this kind uses: a private tab its session choice when there is one, else the saved one; a normal
// tab only ever the saved one (it never sees a private choice).
inline Tweaks effective(const Store& st, const Session& session, const std::string& key, bool privateTab)
{
    if (privateTab) {
        auto it = session.find(key);
        if (it != session.end()) return it->second;
    }
    return saved(st, key);
}
struct Change { bool ok = true, savedChanged = false; };
// Make `next` what this kind of tab uses for key. Private: the session holds a row only while it differs from the
// saved choice (all-off included); the saved file is untouched. Normal: the saved choice (refused when the file is
// full and key is new); a private row equal to the new saved choice is dropped.
inline Change change(Store& st, Session& session, const std::string& key, const Tweaks& next0, bool privateTab)
{
    Change c;
    if (!validKey(key)) { c.ok = false; return c; }
    Tweaks next = next0;
    next.text = validText(next.text);
    if (privateTab) {
        if (next == saved(st, key)) session.erase(key);
        else if (session.count(key) || session.size() < kMaxSites) session[key] = next;
        else c.ok = false;
        return c;
    }
    const Tweaks before = saved(st, key);
    if (next == before) return c;
    if (!next.any()) st.sites.erase(key);
    else if (st.sites.count(key) || st.sites.size() < kMaxSites) st.sites[key] = next;
    else { c.ok = false; return c; }
    c.savedChanged = true;
    auto it = session.find(key);
    if (it != session.end() && it->second == next) session.erase(it);
    return c;
}
inline int cycleText(int cur, int dir)
{
    static const int steps[] = { 0, 15, 30 };
    int i = cur == 30 ? 2 : cur == 15 ? 1 : 0;
    i = (i + (dir < 0 ? 2 : 1)) % 3;
    return steps[i];
}

// --- the style sheet ----------------------------------------------------------------------------------------------
// One user-level sheet (UserStyleLevel::User: its !important beats the page's own !important), top frame only.
// Each part is written so that a selector WebKit does not know can only drop that one rule.
inline std::string css(const Tweaks& t)
{
    std::string s;
    if (validText(t.text))
        // CSS font-size on the root, not page zoom: rem / em / % text grows, the layout width stays. Text a page
        // sizes in px does not change (no CSS can scale it without zoom); a root the page set to 62.5% grows too.
        s += "html{font-size:" + std::to_string(100 + validText(t.text)) + "%!important}\n";
    if (t.sticky)
        // Only elements that look like page bars: landmark header/footer, sticky/fixed class names, inline
        // position:fixed/sticky. Never dialogs, the root, or anything holding a video / iframe / dialog.
        s += ":is(header,footer,[role=\"banner\"],[role=\"contentinfo\"],[class*=\"sticky\" i],[id*=\"sticky\" i],"
             "[class*=\"fixed-top\"],[class*=\"fixed-bottom\"],[class*=\"navbar-fixed\"],[class*=\"is-fixed\"],"
             "[class*=\"is-stuck\"],[class*=\"is-pinned\"],[class*=\"headroom\"],"
             "[style*=\"position:fixed\" i],[style*=\"position: fixed\" i],"
             "[style*=\"position:sticky\" i],[style*=\"position: sticky\" i])"
             ":not(html,body,dialog,video,iframe,[role=\"dialog\"],[role=\"alertdialog\"],[aria-modal=\"true\"])"
             ":not(:has(video,iframe,dialog,[role=\"dialog\"],[role=\"alertdialog\"],[aria-modal=\"true\"]))"
             "{position:static!important}\n";
    if (t.wide)
        s += ":is(main,article,[role=\"main\"]),"
             ":is(main,article,[role=\"main\"])>:not(img,video,picture,svg,canvas,iframe,embed,object,audio,figure,table,pre)"
             "{max-width:none!important}\n";
    if (t.focus)
        s += ":focus-visible{outline:4px solid #ffd400!important;outline-offset:3px!important;"
             "box-shadow:0 0 0 7px rgba(0,0,0,.85)!important}\n";
    return s;
}

// --- texts ------------------------------------------------------------------------------------------------------------
inline std::string textName(int v) { v = validText(v); return v ? "+" + std::to_string(v) + "%" : std::string("Off"); }
inline const char* onOff(bool b) { return b ? "On" : "Off"; }
inline int count(const Tweaks& t) { return (t.text ? 1 : 0) + t.sticky + t.wide + t.focus; }
inline std::string rowValue(const Tweaks& t, bool hasSite)
{
    if (!hasSite) return "-";
    const int n = count(t);
    return n == 0 ? std::string("Off") : n == 1 ? std::string("1 on") : std::to_string(n) + " on";
}
inline std::string subtitle(const std::string& key, bool privateTab)
{
    return privateTab ? key + "  (private tab: this session only)" : key;
}
inline std::string notice(const std::string& key, const std::string& what, bool privateTab, bool failed)
{
    if (failed) return "Couldn't change page tweaks for " + key + " (too many sites)";
    return what + " on " + key + (privateTab ? " (private tabs, this session)" : "");
}

}  // namespace OmniSiteTweaks
'''

SHELL = r'''// OMNI_SITE_TWEAKS_V1: Site settings > "Page tweaks" (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's
// anonymous namespace, after OmniSiteClearShell.h). The pure part is OmniSiteTweaks.h; the reasons are in
// tools/apply_site_css.py. Main thread only; the file is written by omniIoQueue.
#pragma once

namespace OSTW = OmniSiteTweaks;
static OSTW::Store omniStStore;
static OSTW::Session omniStSession;   // choices made in private tabs: this run, private tabs only
static bool omniStLoaded = false, omniStInstalled = false;

static void omniStLoad()
{
    if (omniStLoaded) return;
    omniStLoaded = true;
    FILE* f = fopen(omniData(OSTW::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) < OSTW::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    omniStStore = OSTW::parse(text);
}
static void omniStWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OSTW::kFileName), OSTW::serialize(omniStStore), false);
}
// Both controllers' sheets for one site: normal tabs get the saved choice, private tabs the session choice (or the
// saved one). WebKit restyles open pages when a sheet is added or removed, so no reload.
static void omniStApply(const std::string& key)
{
    const auto allow = OSTW::allowPatterns(key);
    if (allow.empty()) return;
    omniSiteCssSet(key, OSTW::css(OSTW::saved(omniStStore, key)), allow, false);
    omniSiteCssSet(key, OSTW::css(OSTW::effective(omniStStore, omniStSession, key, true)), allow, true);
}
// From omniF3Tick: once the user-content controllers exist, the saved sites get their sheets.
static void omniStTick()
{
    if (omniStInstalled || !omniBlockerController()) return;
    omniStInstalled = true;
    omniStLoad();
    for (const auto& [key, t] : omniStStore.sites) omniStApply(key);
    fprintf(stderr, "OMNI SITE TWEAKS: %d site(s) installed\n", int(omniStStore.sites.size()));
}

// --- the "Page tweaks" panel ---------------------------------------------------------------------------------------
enum { omniStText = 1, omniStSticky, omniStWide, omniStFocus, omniStReset, omniStCookies };
static void omniStPanelBuild(OmniFxPanel& p)
{
    omniStLoad();
    const std::string& key = p.page;
    const bool priv = p.mode == 1;
    const OSTW::Tweaks t = OSTW::effective(omniStStore, omniStSession, key, priv);
    p.subtitle = OSTW::subtitle(key, priv);
    auto add = [&](int id, const char* label, std::string value, bool stepper, const char* detail) {
        OmniFxRow r; r.id = id; r.label = label; r.value = std::move(value); r.stepper = stepper; r.detail = detail; p.rows.push_back(r);
    };
    add(omniStText, "Bigger text", OSTW::textName(t.text), true, "Text size on this site, separate from its zoom");
    add(omniStSticky, "Hide sticky headers/footers", OSTW::onOff(t.sticky), false, "Bars that stay on screen scroll away with the page");
    add(omniStWide, "Wider text column", OSTW::onOff(t.wide), false, "Article text uses the full width of the TV");
    add(omniStFocus, "Larger focus outline", OSTW::onOff(t.focus), false, "A thick ring around the selected link or field");
    add(omniStReset, "Reset tweaks for this site", "", false, "");
    p.rows.back().enabled = t.any();
    add(omniStCookies, "Cookie banners", "Hidden by uBlock", false, "uBlock's Cookie Notices list already hides them");
    p.rows.back().enabled = false;
}
static bool omniStPanelInput(OmniFxPanel& p, const OmniFxRow& r, int b)
{
    const bool a = b == SDL_CONTROLLER_BUTTON_A, left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT;
    const bool side = left || b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT;
    if (!a && !side) return false;
    if (!r.enabled) return true;
    if (r.id == omniStReset && !a) return true;
    omniStLoad();
    const std::string key = p.page;
    const bool priv = p.mode == 1;
    OSTW::Tweaks next = OSTW::effective(omniStStore, omniStSession, key, priv);
    std::string what;
    switch (r.id) {
    case omniStText: next.text = OSTW::cycleText(next.text, left ? -1 : 1); what = "Bigger text " + OSTW::textName(next.text); break;
    case omniStSticky: next.sticky = !next.sticky; what = std::string("Hide sticky bars ") + OSTW::onOff(next.sticky); break;
    case omniStWide: next.wide = !next.wide; what = std::string("Wider text column ") + OSTW::onOff(next.wide); break;
    case omniStFocus: next.focus = !next.focus; what = std::string("Larger focus outline ") + OSTW::onOff(next.focus); break;
    case omniStReset: next = OSTW::Tweaks(); what = "Page tweaks reset"; break;
    default: return true;
    }
    const OSTW::Change c = OSTW::change(omniStStore, omniStSession, key, next, priv);
    if (c.savedChanged) omniStWrite();
    if (c.ok) omniStApply(key);
    notice(OSTW::notice(key, what, priv, !c.ok));
    return true;
}

// --- Site settings > Page tweaks -------------------------------------------------------------------------------------
static std::string omniStSiteKey() { return active() ? OSTW::siteKey(active()->url) : std::string(); }
static void omniStSiteRow(OmniFxPanel& p, const std::string&)
{
    omniStLoad();
    const std::string key = omniStSiteKey();
    const bool priv = active() && active()->omniPrivate;
    OmniFxRow r; r.id = omniStSiteRowId; r.label = "Page tweaks"; r.enabled = !key.empty();
    r.value = OSTW::rowValue(OSTW::effective(omniStStore, omniStSession, key, priv), !key.empty());
    p.rows.push_back(r);
}
static bool omniStSiteInput(const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    const std::string key = omniStSiteKey();
    if (!r.enabled || key.empty() || !active()) return true;
    OmniFxPanel p;
    p.title = "Page tweaks"; p.w = 760;
    p.page = key; p.mode = active()->omniPrivate ? 1 : 0;   // fixed while the panel is open
    p.build = omniStPanelBuild; p.input = omniStPanelInput;
    p.faces = { { 0, "Change" }, { 1, "Back" } };
    p.extra = "Applies at once, no reload";
    omniFxPush(std::move(p));
    return true;
}
'''

BLOCKER_FN = r'''// OMNI_SITE_TWEAKS_V1: Site settings > Page tweaks (OmniSiteTweaksShell.h decides what). One user style sheet per site
// and per controller (normal tabs: controller; private tabs: privateController only), replaced in place; css "" removes
// it. WebKit restyles open pages when a sheet is added or removed (no reload).
namespace {
struct SiteCssEntry {
    RefPtr<API::UserStyleSheet> sheet;
    std::string css;
};
std::unordered_map<std::string, SiteCssEntry> siteCssSheets[2];
}
bool omniSiteCssSet(const std::string& key, const std::string& css, const std::vector<std::string>& allow, bool privateTabs)
{
    WKUserContentControllerRef target = privateTabs ? privateController.get() : controller.get();
    if (!target) return false;
    auto& sheets = siteCssSheets[privateTabs ? 1 : 0];
    auto* proxy = WebKit::toImpl(target);
    auto it = sheets.find(key);
    if (it != sheets.end()) {
        if (it->second.css == css) return true;
        proxy->removeUserStyleSheet(*it->second.sheet);
        sheets.erase(it);
    }
    if (css.empty()) return true;
    if (allow.empty()) return false;   // never a sheet for every site
    WebCore::UserStyleSheet sheet { addonString(css), WTF::URL { }, addonList(allow), { },
        WebCore::UserContentInjectedFrames::InjectInTopFrameOnly,
        WebCore::UserContentMatchParentFrame::ForOpaqueOrigins, WebCore::UserStyleLevel::User };
    auto world = API::ContentWorld::sharedWorldWithName(addonString("omni-site-tweaks"));
    Ref<API::UserStyleSheet> userSheet = API::UserStyleSheet::create(WTF::move(sheet), world.get());
    proxy->addUserStyleSheet(userSheet.get());
    sheets[key] = SiteCssEntry { userSheet.ptr(), css };
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSiteClear.h" // OMNI_SITE_CLEAR_V1: Clear data for this site (pure)\n',
         '#include "OmniSiteClear.h" // OMNI_SITE_CLEAR_V1: Clear data for this site (pure)\n'
         '#include "OmniSiteTweaks.h" // OMNI_SITE_TWEAKS_V1: Page tweaks per site, site-tweaks.txt (pure)\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniScSiteInput(const OmniFxRow& r, int b);\n',
         'static bool omniScSiteInput(const OmniFxRow& r, int b);\n'
         'constexpr int omniStSiteRowId = 740; // OMNI_SITE_TWEAKS_V1 (OmniSiteTweaksShell.h)\n'
         'static void omniStSiteRow(OmniFxPanel& p, const std::string& host);\n'
         'static bool omniStSiteInput(const OmniFxRow& r, int b);\n'),
        ('    omniScSiteRow(p, host); // OMNI_SITE_CLEAR_V1: Clear data for this site\n',
         '    omniScSiteRow(p, host); // OMNI_SITE_CLEAR_V1: Clear data for this site\n'
         '    omniStSiteRow(p, host); // OMNI_SITE_TWEAKS_V1: Page tweaks\n'),
        ('    if (r.id == omniScSiteRowId) return omniScSiteInput(r, b); // OMNI_SITE_CLEAR_V1 (handles its disabled state)\n',
         '    if (r.id == omniStSiteRowId) return omniStSiteInput(r, b); // OMNI_SITE_TWEAKS_V1 (handles its disabled state)\n'
         '    if (r.id == omniScSiteRowId) return omniScSiteInput(r, b); // OMNI_SITE_CLEAR_V1 (handles its disabled state)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n',
         '#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n'
         '#include "OmniSiteTweaksShell.h" // OMNI_SITE_TWEAKS_V1\n'),
        ('    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n',
         '    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n'
         '    omniStTick();       // OMNI_SITE_TWEAKS_V1: saved page tweaks, once the controllers exist\n'),
    ],
    'OmniBlocker.h': [
        ('void omniAddonsRemove(const std::string& id);\n',
         'void omniAddonsRemove(const std::string& id);\n'
         '// OMNI_SITE_TWEAKS_V1: the per-site user style sheet of Page tweaks (key = site; privateTabs: the private\n'
         '// controller only, else the normal one only); css "" removes it. false: controllers not ready / no allow list.\n'
         'bool omniSiteCssSet(const std::string& key, const std::string& css, const std::vector<std::string>& allow, bool privateTabs);\n'),
    ],
    'OmniBlocker.cpp': [
        ('void omniAddonsRemove(const std::string& id)\n{\n',
         BLOCKER_FN + 'void omniAddonsRemove(const std::string& id)\n{\n'),
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
    if 'OMNI_SITE_CLEAR_V1' not in (root / 'OmniFeatures3.h').read_bytes().decode('utf-8'):
        sys.exit('OmniFeatures3.h: OMNI_SITE_CLEAR_V1 missing: apply_site_clear.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniSiteTweaks.h', PURE, 'OmniSiteClear.h'),
            write_new('OmniSiteTweaksShell.h', SHELL, 'OmniSiteClearShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
