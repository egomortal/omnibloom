#!/usr/bin/env python3
"""OMNI_POPUP_NOTICE_V1 (2026-11-16): a "Pop-up blocked" notice with choices, as desktop browsers have.

How pop-ups were handled before (popup() in OmniBrowser.cpp = WKPageUIClient createNewPage; there is no separate
decidePolicyForNewWindowAction / runOpenPanel path for new windows, target=_blank and window.open both arrive here):
  1. omniF2PopupPolicy (OmniPermissions.h): Site permissions > "Pop-ups and redirects" Allow -> opens (skips 2 and 3);
     Block -> refused when there is no unconsumed user gesture (notice "Pop-up blocked. To open it: Options > Site
     settings > Site permissions"; the last one per site can be opened from there).
  2. With uBlock on and the site not trusted: no unconsumed user gesture (WKNavigationActionHasUnconsumedUserGesture;
     controller presses are real mouse / key events, so they count) -> refused, same notice. Turned off by the
     /data/omni/popup-gesture-off.flag file.
  3. uBlock `$popup` filters (omniUBlockPopupBlocked, OmniUBlock.cpp; /data/omni/ublock-popup-rules.txt, opener
     domain=/to= and wildcard patterns) -> refused, notice "uBO blocked an ad popup" (nothing could be reopened).
  Otherwise newTab(config) (the tab limit / memory guard apply; a private opener gives a private tab).

What the user sees now
  - A refused pop-up of the active tab shows, for 8 s in the status line:
        "Pop-up blocked. Options: Open it / Always allow for this site"     (no press, rule 2)
        "Pop-up blocked by uBlock (ad). Options: Open anyway"               (rule 3: no Always allow)
        "Pop-up blocked (site set to Block). Options: Open it"              (rule 1 Block: change it in Site permissions)
    While it shows, Options opens "Blocked pop-ups" (instead of the quick menu; the notice ends). Afterwards the
    quick menu's top level has a "Blocked pop-ups (2)" row while the tab has any.
  - "Blocked pop-ups" (this tab, the last 5, newest first, repeats counted "x3"):
        one row per pop-up: its address, value "No press" / "Ad, uBlock" / "Site: Block"; Cross opens it in a new
        tab ("Open it" / "Open anyway" for ads) through omniFxOpenInNewTab: the tab limit, memory guard and private
        rules apply; the row goes away once opened (stays when no tab could be opened). A window the page fills
        itself (about:blank etc.) is listed but can't be reopened.
        "Always allow for example.com": Off / On (Cross toggles), only for the newest no-press block; never for
        uBlock ad pop-ups or a site set to Block in Site permissions (row disabled, says so).
        "Clear this list".
  - Allowed sites skip only rule 2 (the press rule): uBlock's ad filters and Site permissions > Block still apply.
    Background tabs' blocks are listed without a notice. Lists live for this run, per tab, dropped when it closes.

Storage: /data/omni/popup-allow.txt through omniIoQueue (full rewrite), read once on first use (<= 64 KB):
    omni-popup-allow\t1
    <host>            (one per line; lower case, "www." dropped; covers subdomains; at most 500)
  Private tabs: "Always allow" goes to a session list used by private tabs only (as autoplay's private split); a
  normal tab neither sees nor changes it; a private tab shows a saved entry as "On (normal tabs' list)" (disabled).
  Nothing is written in the self-test modes (the whole feature is off there).

Pure part: engine/entry/OmniPopupNotice.h (no SDL / WebKit): host keys and matching, allow-list parse / serialize,
private split, per-tab recent list caps, texts. namespace OmniPopupNotice (alias OPN in the shell).
Tested by tools/test_popup_notice.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_popup_notice.cpp -o t && ./t
Shell side: engine/entry/OmniPopupNoticeShell.h (included from OmniFeatures3.h after OmniMediaControlsShell.h).
Ids: panel kind 7390, quick-menu row 8470, panel rows 1-5 / 20 / 21.

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp   the OmniMediaControls.h include line (pure include); "Tab* newTab(...);" + "WKPageRef popup(" (forward
                    declarations between them); popup()'s "omniF2pp == -1" line, its no-gesture "if" line, its
                    omniF2PopupBlocked + "return nullptr;" pair, its notice("uBO blocked an ad popup") line; button()'s
                    Options -> omniFxQuickMenuShow line (Options while the notice is up goes before it).
  OmniQuickMenu.h   the omniNpQuickRow(p) call (row after it); the omniNpQuickInput line (handler before it).
  OmniTabsPage.h    the omniTgForget(&tab) line of omniFxTabClosing (omniPnForget after it).
  OmniFeatures3.h   the OmniMediaControlsShell.h include line (the last include of the tree this was made on).
Apply AFTER apply_media_controls.py and apply_tab_groups.py (their lines are anchors).
usage: apply_popup_notice.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_POPUP_NOTICE_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_POPUP_NOTICE_V1: the pure part of the "Pop-up blocked" notice (no SDL, no WebKit). The shell side is
// OmniPopupNoticeShell.h; the reasons are in tools/apply_popup_notice.py. Tested on the host with g++
// (test_popup_notice.cpp).
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <map>
#include <string>
#include <vector>

namespace OmniPopupNotice {

constexpr const char* kFileName = "popup-allow.txt";
constexpr const char* kHeader = "omni-popup-allow\t1";
constexpr size_t kMaxHosts = 500, kHostMax = 253, kMaxFileBytes = 64 * 1024;
constexpr size_t kPerTab = 5;          // the last 5 blocked pop-ups of a tab
constexpr size_t kMaxTabs = 32;        // tabs with a list (oldest list dropped first)
constexpr size_t kUrlMax = 4096;       // longer targets are listed but can't be reopened
constexpr uint32_t kNoticeMs = 8000;   // how long the notice (and the Options shortcut) stays

// Why a pop-up was blocked.
enum Kind { kGesture = 1,   // opened without a press (script-initiated): may be always-allowed
            kAd = 2,        // a uBlock `$popup` filter matched (ad / pop-under network): never always-allowed
            kSiteBlock = 3  // Site permissions > Pop-ups is "Blocked" for the opener: change it there
};

inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }
inline std::string lowerStr(std::string s) { for (auto& c : s) c = lower(c); return s; }
inline bool endsWith(const std::string& s, const std::string& tail)
{
    return s.size() >= tail.size() && s.compare(s.size() - tail.size(), tail.size(), tail) == 0;
}
inline bool isWeb(const std::string& url)
{
    const std::string l = lowerStr(url.substr(0, 8));
    return l.rfind("https://", 0) == 0 || l.rfind("http://", 0) == 0;
}

// --- hosts -------------------------------------------------------------------------------------------------------
// Host of an http(s) URL: lower case, no user info, no port, no trailing dot ("" for anything else).
inline std::string hostOf(const std::string& url)
{
    if (!isWeb(url)) return {};
    size_t a = url.find("://") + 3;
    size_t end = url.find_first_of("/?#", a);
    if (end == std::string::npos) end = url.size();
    std::string auth = url.substr(a, end - a);
    const size_t at = auth.rfind('@');
    if (at != std::string::npos) auth = auth.substr(at + 1);
    if (!auth.empty() && auth[0] == '[') {   // IPv6 literal: keep the brackets' content
        const size_t close = auth.find(']');
        return close == std::string::npos ? std::string() : lowerStr(auth.substr(1, close - 1));
    }
    const size_t colon = auth.find(':');
    if (colon != std::string::npos) auth = auth.substr(0, colon);
    while (!auth.empty() && auth.back() == '.') auth.pop_back();
    return lowerStr(auth);
}
inline bool validHost(const std::string& h)
{
    if (h.empty() || h.size() > kHostMax || h.front() == '.' || h.find("..") != std::string::npos) return false;
    for (char c : h)
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_' || c == ':')) return false;
    return true;
}
// The key a host is stored under: lower case, "www." dropped (www.example.com and example.com are one site).
inline std::string hostKey(const std::string& host)
{
    std::string h = lowerStr(host);
    while (!h.empty() && h.back() == '.') h.pop_back();
    if (h.rfind("www.", 0) == 0 && h.size() > 4) h = h.substr(4);
    return validHost(h) ? h : std::string();
}
// A stored key covers the host and its subdomains (example.com covers m.example.com, not badexample.com).
inline bool covers(const std::string& key, const std::string& host)
{
    const std::string h = hostKey(host);
    if (key.empty() || h.empty()) return false;
    return h == key || endsWith(h, "." + key);
}

// --- the allow list (/data/omni/popup-allow.txt) --------------------------------------------------------------------
struct AllowList { std::vector<std::string> hosts; };   // keys, in the order added

inline bool allowedBy(const AllowList& l, const std::string& host)
{
    for (auto& k : l.hosts) if (covers(k, host)) return true;
    return false;
}
inline bool contains(const AllowList& l, const std::string& key)
{
    for (auto& k : l.hosts) if (k == key) return true;
    return false;
}
// false: invalid host, already listed or the list is full.
inline bool add(AllowList& l, const std::string& host)
{
    const std::string k = hostKey(host);
    if (k.empty() || contains(l, k) || l.hosts.size() >= kMaxHosts) return false;
    l.hosts.push_back(k);
    return true;
}
// Removes the key of `host` and every listed parent that covers it (so the site is really no longer allowed).
inline bool remove(AllowList& l, const std::string& host)
{
    const size_t before = l.hosts.size();
    std::vector<std::string> keep;
    for (auto& k : l.hosts) if (!covers(k, host)) keep.push_back(k);
    l.hosts.swap(keep);
    return l.hosts.size() != before;
}
// One host per line after the header; '#' lines, blanks, invalid and duplicate hosts are skipped; at most kMaxHosts.
// A file without the header is read too (hand-written lists).
inline AllowList parse(const std::string& text)
{
    AllowList l;
    size_t i = 0;
    const size_t n = std::min(text.size(), kMaxFileBytes);
    while (i < n) {
        size_t e = text.find('\n', i);
        if (e == std::string::npos || e > n) e = n;
        std::string line = text.substr(i, e - i);
        i = e + 1;
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ' || line.back() == '\t')) line.pop_back();
        size_t s = 0;
        while (s < line.size() && (line[s] == ' ' || line[s] == '\t')) ++s;
        line = line.substr(s);
        if (line.empty() || line[0] == '#' || line == kHeader || line.rfind("omni-popup-allow", 0) == 0) continue;
        add(l, line);
    }
    return l;
}
inline std::string serialize(const AllowList& l)
{
    std::string out = std::string(kHeader) + "\n";
    for (auto& k : l.hosts) out += k + "\n";
    return out;
}
// Private split (as autoplay's): choices made in a private tab live in `session` for this run and count only for
// private tabs; a normal tab sees the saved list only.
inline bool isAllowed(const AllowList& saved, const AllowList& session, const std::string& host, bool privateTab)
{
    return allowedBy(saved, host) || (privateTab && allowedBy(session, host));
}

// --- the recent list (per tab, this run only) -------------------------------------------------------------------
struct Blocked { std::string url, host; Kind kind = kGesture; int count = 1; };   // host: the opener's
struct Recent {
    std::map<uintptr_t, std::deque<Blocked>> tabs;   // newest first
    std::deque<uintptr_t> order;                      // tabs by last use, newest last
};
inline bool reopenable(const Blocked& b) { return isWeb(b.url) && b.url.size() <= kUrlMax; }
inline void record(Recent& r, uintptr_t tab, const std::string& url, const std::string& openerHost, Kind kind)
{
    auto& items = r.tabs[tab];
    Blocked b { url, openerHost, kind, 1 };
    for (auto it = items.begin(); it != items.end(); ++it)
        if (it->url == url && it->kind == kind && it->host == openerHost) { b.count = it->count + 1; items.erase(it); break; }
    items.push_front(b);
    while (items.size() > kPerTab) items.pop_back();
    for (auto it = r.order.begin(); it != r.order.end(); ++it) if (*it == tab) { r.order.erase(it); break; }
    r.order.push_back(tab);
    while (r.order.size() > kMaxTabs) { r.tabs.erase(r.order.front()); r.order.pop_front(); }
}
inline void forget(Recent& r, uintptr_t tab)
{
    r.tabs.erase(tab);
    for (auto it = r.order.begin(); it != r.order.end(); ++it) if (*it == tab) { r.order.erase(it); break; }
}
inline const std::deque<Blocked>* list(const Recent& r, uintptr_t tab)
{
    auto it = r.tabs.find(tab);
    return it == r.tabs.end() || it->second.empty() ? nullptr : &it->second;
}
inline size_t count(const Recent& r, uintptr_t tab) { auto* l = list(r, tab); return l ? l->size() : 0; }
inline bool take(Recent& r, uintptr_t tab, size_t index, Blocked& out)
{
    auto it = r.tabs.find(tab);
    if (it == r.tabs.end() || index >= it->second.size()) return false;
    out = it->second[index];
    it->second.erase(it->second.begin() + long(index));
    if (it->second.empty()) forget(r, tab);
    return true;
}
// The host "Always allow" would add: the newest script-initiated block of the tab (ads and site blocks never offer it).
inline std::string allowCandidate(const Recent& r, uintptr_t tab)
{
    if (auto* l = list(r, tab))
        for (auto& b : *l) if (b.kind == kGesture && !hostKey(b.host).empty()) return hostKey(b.host);
    return {};
}

// --- texts -------------------------------------------------------------------------------------------------------
inline bool canAllow(Kind k) { return k == kGesture; }
inline const char* openLabel(Kind k) { return k == kAd ? "Open anyway" : "Open it"; }
inline std::string noticeText(Kind k)
{
    switch (k) {
    case kAd: return "Pop-up blocked by uBlock (ad). Options: Open anyway";
    case kSiteBlock: return "Pop-up blocked (site set to Block). Options: Open it";
    default: return "Pop-up blocked. Options: Open it / Always allow for this site";
    }
}
inline std::string quickLabel(size_t n) { return "Blocked pop-ups (" + std::to_string(n) + ")"; }
inline std::string rowValue(const Blocked& b)
{
    std::string v = b.kind == kAd ? "Ad, uBlock" : b.kind == kSiteBlock ? "Site: Block" : "No press";
    if (b.count > 1) v += " x" + std::to_string(b.count);
    return v;
}
inline std::string allowNotice(const std::string& key, bool privateTab)
{
    return "Pop-ups allowed on " + key + (privateTab ? " (this private session)" : "");
}
inline std::string disallowNotice(const std::string& key) { return "Pop-ups on " + key + " are blocked again"; }
// The notice is "up" (and Options opens the list) only while the status line still shows our text.
inline bool hintUp(const std::string& status, const std::string& ours, uint32_t statusUntil, uint32_t now)
{
    return !ours.empty() && status == ours && statusUntil != 0 && int32_t(statusUntil - now) > 0;
}

} // namespace OmniPopupNotice
'''

SHELL = r'''// OMNI_POPUP_NOTICE_V1: "Pop-up blocked" notice and the Blocked pop-ups list (shell side). Included from OmniFeatures3.h
// (inside OmniBrowser.cpp's anonymous namespace). The pure part is OmniPopupNotice.h; the reasons are in
// tools/apply_popup_notice.py. Everything runs on the main thread; the allow list is written by omniIoQueue.
#pragma once

namespace OPN = OmniPopupNotice;
enum { omniPnPanelKind = 7390, omniPnQuickRowId = 8470, omniPnRowAllow = 20, omniPnRowClear = 21 };
static OPN::AllowList omniPnSaved, omniPnSession;   // session: choices made in private tabs (private tabs only)
static bool omniPnLoaded = false;
static OPN::Recent omniPnRecent;
static std::string omniPnHint;                        // the notice text while it is ours
static uintptr_t omniPnHintTab = 0;                   // the tab it is about

static void omniPnLoad()
{
    if (omniPnLoaded) return;
    omniPnLoaded = true;
    FILE* f = fopen(omniData(OPN::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && text.size() < OPN::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    omniPnSaved = OPN::parse(text);
}
static void omniPnWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OPN::kFileName), OPN::serialize(omniPnSaved), false);
}
static uintptr_t omniPnKey(const Tab* t) { return reinterpret_cast<uintptr_t>(t); }

// popup(): true when the opener's site is on the allow list (the no-press rule is skipped; uBlock's `$popup` filters
// and Site permissions > Block still apply).
static bool omniPnAllowed(WKPageRef page, const std::string& opener)
{
    if (omniTestMode()) return false;
    omniPnLoad();
    Tab* t = omniTabForPage(page);
    return OPN::isAllowed(omniPnSaved, omniPnSession, OPN::hostOf(opener), t && t->omniPrivate);
}
// popup(): a pop-up was refused (kind: OPN::Kind). Records it for the opener's tab and shows the notice for 8 s.
static void omniPnBlocked(WKPageRef page, const std::string& opener, const std::string& target, int kind)
{
    if (omniTestMode()) return;
    Tab* t = omniTabForPage(page);
    if (!t) return;
    const OPN::Kind k = kind == OPN::kAd ? OPN::kAd : kind == OPN::kSiteBlock ? OPN::kSiteBlock : OPN::kGesture;
    OPN::record(omniPnRecent, omniPnKey(t), target, OPN::hostOf(opener), k);
    if (t != active()) return;   // a background tab: listed, no notice
    omniPnHint = OPN::noticeText(k);
    omniPnHintTab = omniPnKey(t);
    status = omniPnHint;
    statusUntil = SDL_GetTicks() + OPN::kNoticeMs;
    omniShellDirty = true;
}
// omniFxTabClosing: the tab's list goes with it.
static void omniPnForget(const void* tab)
{
    OPN::forget(omniPnRecent, reinterpret_cast<uintptr_t>(tab));
    if (omniPnHintTab == reinterpret_cast<uintptr_t>(tab)) { omniPnHint.clear(); omniPnHintTab = 0; }
}

// --- the Blocked pop-ups panel ---------------------------------------------------------------------------------------
static void omniPnBuild(OmniFxPanel& p)
{
    Tab* t = active();
    const uintptr_t key = omniPnKey(t);
    const auto* items = t ? OPN::list(omniPnRecent, key) : nullptr;
    p.subtitle = t ? omniOneLine(omniShownURL(t->url), 80) : std::string();
    auto add = [&](int id, std::string label, std::string value, bool on, std::string detail = {}) {
        OmniFxRow r; r.id = id; r.label = std::move(label); r.value = std::move(value); r.enabled = on; r.detail = std::move(detail);
        p.rows.push_back(r);
        return &p.rows.back();
    };
    if (!items) { add(0, "No pop-ups blocked in this tab", "", false); return; }
    int i = 0;
    for (auto& b : *items) {
        ++i;
        if (OPN::reopenable(b))
            add(i, omniOneLine(omniShownURL(b.url), 90), OPN::rowValue(b), true, std::string(OPN::openLabel(b.kind)) + " in a new tab");
        else
            add(i, b.url.empty() || !OPN::isWeb(b.url) ? std::string("A window the page fills itself") : omniOneLine(b.url, 90),
                OPN::rowValue(b), false, "Can't be reopened; Always allow lets the page open it next time");
    }
    // Always allow: only for the newest no-press block (never for uBlock's ad pop-ups or a site set to Block).
    const bool priv = t && t->omniPrivate;
    const std::string cand = OPN::allowCandidate(omniPnRecent, key);
    if (!cand.empty()) {
        omniPnLoad();
        const bool saved = OPN::allowedBy(omniPnSaved, cand), session = priv && OPN::allowedBy(omniPnSession, cand);
        if (omniPermGet(cand, "popups") == 2 || omniPermGet("www." + cand, "popups") == 2)
            add(omniPnRowAllow, "Always allow for " + cand, "Blocked in Site permissions", false);
        else if (saved && priv)
            add(omniPnRowAllow, "Always allow for " + cand, "On (normal tabs' list)", false);
        else
            add(omniPnRowAllow, "Always allow for " + cand, saved || session ? "On" : "Off", true,
                priv ? "Private tab: only for this private session" : "Saved; pop-ups from this site open without a press");
    }
    add(omniPnRowClear, "Clear this list", "", true);
}
static bool omniPnInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (!r.enabled) return true;
    Tab* t = active();
    if (!t) return true;
    const uintptr_t key = omniPnKey(t);
    if (r.id >= 1 && r.id <= int(OPN::kPerTab)) {
        OPN::Blocked item;
        auto* items = OPN::list(omniPnRecent, key);
        if (!items || size_t(r.id) > items->size() || !OPN::reopenable((*items)[size_t(r.id - 1)])) return true;
        const std::string url = (*items)[size_t(r.id - 1)].url;
        omniFxCloseAll();
        // the tab limit, memory guard and private rules apply (a private tab opens a private tab); the entry is kept
        // when no tab could be opened
        if (omniFxOpenInNewTab(url, false, false)) OPN::take(omniPnRecent, key, size_t(r.id - 1), item);
        return true;
    }
    if (r.id == omniPnRowAllow) {
        const std::string cand = OPN::allowCandidate(omniPnRecent, key);
        if (cand.empty()) return true;
        omniPnLoad();
        const bool priv = t->omniPrivate;
        OPN::AllowList& list = priv ? omniPnSession : omniPnSaved;
        if (OPN::allowedBy(list, cand)) {
            OPN::remove(list, cand);
            if (!priv) omniPnWrite();
            notice(OPN::disallowNotice(cand));
        } else if (OPN::add(list, cand)) {
            if (!priv) omniPnWrite();
            notice(OPN::allowNotice(cand, priv));
        } else notice("The pop-up allow list is full (500 sites)");
        omniFxRefresh();
        return true;
    }
    if (r.id == omniPnRowClear) { OPN::forget(omniPnRecent, key); omniFxRefresh(); return true; }
    return false;
}
static void omniPnShow()
{
    OmniFxPanel p;
    p.kind = omniPnPanelKind; p.w = 900;
    p.title = "Blocked pop-ups";
    p.build = omniPnBuild; p.input = omniPnInput;
    p.faces = { { 0, "Choose" }, { 1, "Back" } };
    p.extra = "uBlock's ad pop-ups can be opened, never always-allowed";
    omniFxPush(std::move(p));
}
// button(): Options while the notice is up opens the list instead of the quick menu (the notice says so).
static bool omniPnOptions()
{
    const uint32_t now = SDL_GetTicks();
    if (!OPN::hintUp(status, omniPnHint, statusUntil, now) || !active() || omniPnKey(active()) != omniPnHintTab) return false;
    omniPnHint.clear();
    statusUntil = now + 1;   // the notice ends now ("Ready" next pass)
    omniPnShow();
    return true;
}

// --- Options (top level): "Blocked pop-ups (2)" while the tab has any -------------------------------------------------
static void omniPnQuickRow(OmniFxPanel& p)
{
    const size_t n = active() ? OPN::count(omniPnRecent, omniPnKey(active())) : 0;
    if (!n) return;
    OmniFxRow r; r.id = omniPnQuickRowId; r.label = OPN::quickLabel(n);
    p.rows.push_back(r);
}
static bool omniPnQuickInput(const OmniFxRow& r, int b)
{
    if (r.id != omniPnQuickRowId || b != SDL_CONTROLLER_BUTTON_A) return false;
    omniPnShow();
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniMediaControls.h" // OMNI_MEDIA_CONTROLS_V1: Now playing (pure)\n',
         '#include "OmniMediaControls.h" // OMNI_MEDIA_CONTROLS_V1: Now playing (pure)\n'
         '#include "OmniPopupNotice.h" // OMNI_POPUP_NOTICE_V1: Pop-up blocked notice, popup-allow.txt (pure)\n'),
        ('Tab* newTab(WKPageConfigurationRef supplied = nullptr);\nWKPageRef popup(',
         'Tab* newTab(WKPageConfigurationRef supplied = nullptr);\n'
         '// OMNI_POPUP_NOTICE_V1 (OmniPopupNoticeShell.h): allow list, "Pop-up blocked" notice, Options while it shows\n'
         'static bool omniPnAllowed(WKPageRef page, const std::string& opener);\n'
         'static void omniPnBlocked(WKPageRef page, const std::string& opener, const std::string& target, int kind);\n'
         'static void omniPnForget(const void* tab);\n'
         'static bool omniPnOptions();\n'
         'static void omniPnQuickRow(OmniFxPanel& p);\n'
         'static bool omniPnQuickInput(const OmniFxRow& r, int b);\n'
         'WKPageRef popup('),
        ('    if (omniF2pp == -1) { omniF2PopupBlocked(page, opener, target); return nullptr; }\n',
         '    if (omniF2pp == -1) { omniF2PopupBlocked(page, opener, target); omniPnBlocked(page, opener, target, 3); return nullptr; } // OMNI_POPUP_NOTICE_V1: site set to Block\n'),
        ('        if (!WKNavigationActionHasUnconsumedUserGesture(action) && access("/data/omni/popup-gesture-off.flag", F_OK)) {\n',
         '        if (!WKNavigationActionHasUnconsumedUserGesture(action) && access("/data/omni/popup-gesture-off.flag", F_OK)\n'
         '            && !omniPnAllowed(page, opener)) { // OMNI_POPUP_NOTICE_V1: "Always allow" sites skip only this rule\n'),
        ('            omniF2PopupBlocked(page, opener, target); // OMNI_FEATURES_V2\n            return nullptr;\n',
         '            omniF2PopupBlocked(page, opener, target); // OMNI_FEATURES_V2\n'
         '            omniPnBlocked(page, opener, target, 1); // OMNI_POPUP_NOTICE_V1: "Pop-up blocked. Options: Open it / Always allow"\n'
         '            return nullptr;\n'),
        ('            notice("uBO blocked an ad popup");\n',
         '            omniPnBlocked(page, opener, target, 2); // OMNI_POPUP_NOTICE_V1: "Pop-up blocked by uBlock (ad). Options: Open anyway" (was notice("uBO blocked an ad popup"))\n'),
        ('    if (button == SDL_CONTROLLER_BUTTON_START) { omniFxQuickMenuShow(); return; }',
         '    if (button == SDL_CONTROLLER_BUTTON_START && omniPnOptions()) return; // OMNI_POPUP_NOTICE_V1: Blocked pop-ups while the notice shows\n'
         '    if (button == SDL_CONTROLLER_BUTTON_START) { omniFxQuickMenuShow(); return; }'),
    ],
    'OmniQuickMenu.h': [
        ('        omniNpQuickRow(p); // OMNI_MEDIA_CONTROLS_V1: Now playing, while a tab plays\n',
         '        omniNpQuickRow(p); // OMNI_MEDIA_CONTROLS_V1: Now playing, while a tab plays\n'
         '        omniPnQuickRow(p); // OMNI_POPUP_NOTICE_V1: Blocked pop-ups (n), while this tab has any\n'),
        ('    if (omniNpQuickInput(r, b)) return true; // OMNI_MEDIA_CONTROLS_V1 (before the >= 900 rows)\n',
         '    if (omniPnQuickInput(r, b)) return true; // OMNI_POPUP_NOTICE_V1 (before the >= 900 rows)\n'
         '    if (omniNpQuickInput(r, b)) return true; // OMNI_MEDIA_CONTROLS_V1 (before the >= 900 rows)\n'),
    ],
    'OmniTabsPage.h': [
        ('    omniTgForget(&tab); // OMNI_TAB_GROUPS_V1\n',
         '    omniTgForget(&tab); // OMNI_TAB_GROUPS_V1\n'
         '    omniPnForget(&tab); // OMNI_POPUP_NOTICE_V1: its Blocked pop-ups list\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniMediaControlsShell.h" // OMNI_MEDIA_CONTROLS_V1\n',
         '#include "OmniMediaControlsShell.h" // OMNI_MEDIA_CONTROLS_V1\n'
         '#include "OmniPopupNoticeShell.h" // OMNI_POPUP_NOTICE_V1\n'),
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
    if 'OMNI_MEDIA_CONTROLS_V1' not in (root / 'OmniFeatures3.h').read_bytes().decode('utf-8'):
        sys.exit('OmniFeatures3.h: OMNI_MEDIA_CONTROLS_V1 missing: apply_media_controls.py first')
    if 'OMNI_TAB_GROUPS_V1' not in (root / 'OmniTabsPage.h').read_bytes().decode('utf-8'):
        sys.exit('OmniTabsPage.h: OMNI_TAB_GROUPS_V1 missing: apply_tab_groups.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniPopupNotice.h', PURE, 'OmniMediaControls.h'),
            write_new('OmniPopupNoticeShell.h', SHELL, 'OmniMediaControlsShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
