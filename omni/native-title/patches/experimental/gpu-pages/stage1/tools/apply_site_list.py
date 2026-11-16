#!/usr/bin/env python3
"""OMNI_SITE_LIST_V1 (2026-11-16): "Sites with custom settings", one list of every site that has any saved per-site choice.

What the user sees
  - Browser settings has a new row "Sites with custom settings" (after "Site permissions"; Search settings finds it like
    any other row: "sites", "custom", "site settings"). Site settings has a new last row "All sites..." (same list).
  - The list (title "Sites with custom settings", subtitle "5 sites with settings of their own"):
        "Search sites..."            Cross: the on-screen keyboard; the text is cleaned (scheme, path, port, "www." go:
                                     "https://www.example.com/x" looks for "example.com"); Square clears it.
        example.com    Zoom 125% . Autoplay blocked . Pop-ups allowed       (one row per host, A-Z)
    Cross opens the site; Square "Reset this site" asks once (the shell's modal, Cancel focused):
        "Reset settings for example.com?"
        "Back to the defaults: Zoom 125%, Autoplay blocked, Pop-ups allowed. Cookies and site data are kept."
        (+ "uBlock is turned back on for example.com too (it covers this site)." when the uBlock / pop-up allow list's own
         removal also drops a listed parent domain: their remove() functions do that on purpose.)
  - One site (title = the host, subtitle = its summary): Zoom (stepper, Cross resets), Site version, Dark page, Autoplay,
    HTTPS-only, Pop-ups and redirects, Always allow pop-ups, uBlock on this site, Page tweaks (opens the existing Page
    tweaks panel for that host), Site permissions (opens the existing Site permissions page for that host), one row per
    add-on that can run there, "Reset this site". Square resets from here too (the panel closes after a reset).
    Site settings itself is not reused: its rows read the active tab (omniMenuHost, omniApSiteHost, omniHoSiteHost,
    omniStSiteKey, active()->url), so it cannot take another host. This panel calls the same store functions instead.
  - Private-tab session choices are never listed or shown (only the saved stores are read); every change made here is a
    normal (saved) choice.

The stores (all read from their in-memory state after their own loader; none of their files is touched here)
  kind         file (owner)                                      key (owner's rule, unchanged)            reset / change
  zoom         site-zoom.txt (OMNI_SITE_ZOOM_V1, OmniBrowser.cpp) OmniSiteZoom::hostKey: www. dropped      omniSiteZoom.erase/set + omniPrefsSave
  mobile UA    site-ua.txt (OmniBrowser.cpp omniMobileHosts)      omniBlockerHostOf: www. dropped          erase/insert + omniPrefsSave
  dark         site-dark.txt (OMNI_FEATURES_V3, OmniDarkPages.h)   omniDkHost: www. dropped                 omniDkSetSite(key, -1 / 0 / 1)
  autoplay     autoplay.txt (OMNI_AUTOPLAY_V1)                    OAP::siteKey: www. dropped, [v6]         OAP::setSite(.., kDefault) + omniApWrite
  https-only   https-only.txt allow lines (OMNI_HTTPS_ONLY_V1)    OHO::hostKey: www. dropped, v6 bare      OHO::setSite(.., false, normal) + omniHoWrite
  permissions  site-permissions.txt saved map (OMNI_FEATURES_V2)  omniBlockerHostOf (popups); storage:<x>  omniPermClearHost (the owner's "Reset
                                                                  rows under WebKit's host string         permissions for this site"; it drops that
                                                                                                          host's session row too) / omniPermSet(.., true)
  popup allow  popup-allow.txt (OMNI_POPUP_NOTICE_V1)             OPN::hostKey: www. dropped              OPN::remove / OPN::add + omniPnWrite
  page tweaks  site-tweaks.txt (OMNI_SITE_TWEAKS_V1)              OSTW::siteKey: www. dropped, no v6      OSTW::change(.., Tweaks(), normal)
                                                                                                          + omniStWrite + omniStApply
  uBlock off   ublock-allowlist.txt (OmniBlocker.cpp)             omniBlockerHostOf                        omniBlockerSetSiteTrusted(key, false)
  add-ons      addons/state.json "sites" (OMNI_ADDONS_V1)         omniAdHostOf: www. dropped              sites.erase + omniAdApply (or omniAdSaveState
                                                                                                          when the add-on is no longer installed)
  reader view  reader-sites.txt always lines (OMNI_READER_AUTO_V1)  ORAU::siteKey: www. dropped              ORAU::setSite(.., false) + omniRauWrite
               r2, optional: compiled in only when OmniReaderAutoShell.h is in the tree (__has_include in OmniSiteListShell.h;
               apply_reader_auto.py runs later and includes that shell from OmniFeatures3.h, before ours). No registration needed.
  game mode    OMNI_GAME_MODE_V1 store (omniGmStore.sites)          OGMM::hostKey: www. dropped, v6 bare     OGMM::setSite(.., false, normal) + omniGmWrite
               r3, optional the same way (__has_include("OmniGameModeShell.h"); apply_game_mode.py includes it from
               OmniFeatures3.h, before ours). No registration needed.
  r4, each optional the same way (__has_include of its shell, which its patch includes from OmniFeatures3.h, before ours):
  always mute  site-mute.txt (OMNI_SITE_MUTE_V1)                   OSMU::hostKey: www. dropped, v6 bare     omniSmuSetSaved(key, false) (writes, unmutes
                                                                                                          its tabs); list omniSmuSavedSites, row
                                                                                                          omniSmuSavedValue (Site settings row 776)
  site volume  site-volume.txt (OMNI_SITE_VOLUME_V1, tab volume's) OmniMediaControls::site: www. dropped,   omniSvoResetSaved(key) (tabs back at 100 %);
                                                                  v6 KEPT in brackets (siteHost() strips   list omniSvoSavedSites + omniSvoSavedValue
                                                                  them: same row as the other stores)      ("30%"; percentOf()); row 778's value
  video full   site-autofs.txt (OMNI_AUTO_FULLSCREEN_V1)           OAFS::hostKey: www. dropped, v6 bare     OAFS::setSite(.., false) + omniAfsWrite
  screen                                                                                                  (row 793's store; omniAfsSession not read)
  Private tabs: their sources return the saved lists only (omniSmuStore / omniTvSaved / omniAfsStore); private choices
  live in omniSmuSession / omniTvPrivate / omniAfsSession, which are never read here, so nothing of a private tab shows,
  during or after its session.
  Chain order: site_list's position does not matter for these (the __has_include checks run when OmniBrowser.cpp is
  compiled, after the whole chain). apply_auto_fullscreen.py needs apply_reader_auto.py and apply_site_volume.py needs
  apply_tab_volume.py, which both run after this patch, so the three are appended after the chain; a tree patched
  with r2 / r3 gets the r4 headers by running this script again (only the two new headers change).
  Not listed: playback speed (OMNI_PLAYBACK_SPEED_V1: per site, this session only), passwords / autofill (logins, not
  settings), "Continue" on the HTTPS-only page and every private-tab session map.
  The uBlock list had no reader outside OmniBlocker.cpp: omniBlockerTrustedSites() (a copy of the saved list) is added.

Merging: OmniSiteList::siteHost (lower case, no brackets, no trailing dot, "www." dropped when a dot remains) groups the
items for display; each item keeps its store's key and is reset with exactly that key, so a store holding both
www.example.com and example.com (an older site-dark.txt) gets both reset. New choices made in the site panel use each
store's own key function on "https://<host>/".

Pure part: engine/entry/OmniSiteList.h (merge by host, summary line, filter, reset texts), tested by
tools/test_site_list.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_site_list.cpp -o t && ./t
(with OmniSettingsSearch.h in the tree it also checks that Search settings finds the new row).
Shell side: engine/entry/OmniSiteListShell.h, included from OmniBrowser.cpp right after OmniAddons.h (every store above it).

Anchors (exactly once each; MARK makes each file idempotent; whole lines only):
  OmniBrowser.cpp        the OmniSiteClear.h include line (apply_site_clear.py's): + OmniSiteList.h
                         the OmniAddons.h include line: + OmniSiteListShell.h
  OmniBlocker.h          the omniBlockerSetSiteTrusted declaration: + omniBlockerTrustedSites()
  OmniBlocker.cpp        the omniBlockerSiteTrusted definition's first line: its definition goes before it
  OmniBrowserSettings.h  the omniChSettingsRow declaration (apply_controls_help.py's): row id 855 + declarations
                         the omniF2SettingsExtra(p) call: + omniSliSettingsRow(p)
                         the omniSlRowId dispatch (apply_send_link.py's): our dispatch first
  OmniQuickMenu.h        the omniStSiteInput declaration (apply_site_css.py's): row id 750 + declarations
                         the omniF2SiteExtra(p) call: + omniSliSiteRow(p)
                         the omniStSiteRowId dispatch: our dispatch first
Ids: Browser settings row 855, Site settings row 750, panel kinds 7395 / 7396 (all unused before). Namespace alias OSLI.
Apply AFTER apply_site_clear.py, apply_site_css.py, apply_controls_help.py and apply_settings_search.py.
usage: apply_site_list.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_SITE_LIST_V1'
REV = 'OMNI_SITE_LIST_V1_R4'   # r2: optional reader-sites.txt (OMNI_READER_AUTO_V1); r3: optional game mode (OMNI_GAME_MODE_V1); r4: optional site mute, site volume, auto fullscreen; only the two new headers change
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_SITE_LIST_V1: the pure part of "Sites with custom settings" (no SDL, no WebKit): every saved per-site choice of
// every store, merged by host, one summary line per site, the host filter and the reset texts. The shell side is
// OmniSiteListShell.h (it reads each store and resets through each store's own functions); the reasons are in
// tools/apply_site_list.py. Tested on the host with g++ (tools/test_site_list.cpp).
// OMNI_SITE_LIST_V1_R2: kReader (reader-sites.txt, OMNI_READER_AUTO_V1; listed only when that patch is in the tree).
// OMNI_SITE_LIST_V1_R3: kGame (game mode sites, OMNI_GAME_MODE_V1; listed only when that patch is in the tree).
// OMNI_SITE_LIST_V1_R4: kMute (OMNI_SITE_MUTE_V1), kVolume (OMNI_SITE_VOLUME_V1), kAutoFs (OMNI_AUTO_FULLSCREEN_V1);
// each listed only when its patch is in the tree.
#pragma once
#include <algorithm>
#include <cstddef>
#include <map>
#include <string>
#include <vector>

namespace OmniSiteList {

// One kind per store (and per kind of choice inside Site permissions). The order is the summary's order.
enum Kind {
    kZoom = 0,    // site-zoom.txt (OMNI_SITE_ZOOM_V1)                value: percent
    kMobile,      // site-ua.txt                                      value: 1
    kDark,        // site-dark.txt (OMNI_FEATURES_V3)                 value: 1 always dark, 0 never dark
    kAutoplay,    // autoplay.txt (OMNI_AUTOPLAY_V1)                  value: OmniAutoplay::Mode (1 allow, 2 no sound, 3 block)
    kMute,        // site-mute.txt (OMNI_SITE_MUTE_V1)                value: 1
    kVolume,      // site-volume.txt (OMNI_SITE_VOLUME_V1)            value: percent
    kAutoFs,      // site-autofs.txt (OMNI_AUTO_FULLSCREEN_V1)        value: 1
    kHttp,        // https-only.txt allow lines (OMNI_HTTPS_ONLY_V1)  value: 1
    kPopups,      // site-permissions.txt "popups" (OMNI_FEATURES_V2) value: 1 allow, 2 block
    kStorage,     // site-permissions.txt "storage:<site>" rows       value: how many
    kPopupAllow,  // popup-allow.txt (OMNI_POPUP_NOTICE_V1)           value: 1
    kTweaks,      // site-tweaks.txt (OMNI_SITE_TWEAKS_V1)            value: how many tweaks are on
    kReader,      // reader-sites.txt "always" (OMNI_READER_AUTO_V1)  value: 1
    kGame,        // game mode sites (OMNI_GAME_MODE_V1)              value: 1
    kUblock,      // ublock-allowlist.txt (uBlock off on the site)    value: 1
    kAddon,       // addons/state.json per-site switch (OMNI_ADDONS_V1) value: 1 on, 0 off; name: the add-on's name
    kKindCount
};

// One saved choice, under the key its store holds it by (reset and change use `key` exactly as it is).
struct Item {
    Kind kind = kZoom;
    std::string key;
    int value = 1;
    std::string name;    // kAddon: the add-on's name
    std::string owner;   // kAddon: the add-on's id
};
struct Site {
    std::string host;           // siteHost() of every item's key
    std::vector<Item> items;    // in Kind order
};

inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }
inline bool endsWith(const std::string& s, const std::string& tail)
{
    return s.size() >= tail.size() && s.compare(s.size() - tail.size(), tail.size(), tail) == 0;
}

// The host a saved key is listed under: lower case, no surrounding blanks, IPv6 without brackets, no trailing dots, and
// "www." dropped when a dot remains after it (www.example.com and example.com are one row). Only for grouping and
// showing: no store's own matching rule changes (each item keeps its key).
inline std::string siteHost(const std::string& key)
{
    size_t a = 0, b = key.size();
    while (a < b && (key[a] == ' ' || key[a] == '\t')) ++a;
    while (b > a && (key[b - 1] == ' ' || key[b - 1] == '\t' || key[b - 1] == '\r' || key[b - 1] == '\n')) --b;
    std::string h;
    h.reserve(b - a);
    for (size_t i = a; i < b; ++i) h += lower(key[i]);
    if (h.size() > 2 && h.front() == '[' && h.back() == ']') h = h.substr(1, h.size() - 2);
    while (!h.empty() && h.back() == '.') h.pop_back();
    if (h.compare(0, 4, "www.") == 0 && h.find('.', 4) != std::string::npos) h.erase(0, 4);
    return h;
}

// Items -> one Site per host, hosts in alphabetical order, items in Kind order (then key, then add-on name).
// Items with an empty host are dropped.
inline std::vector<Site> merge(const std::vector<Item>& items)
{
    std::map<std::string, Site> by;
    for (const auto& it : items) {
        const std::string h = siteHost(it.key);
        if (h.empty() || it.kind < 0 || it.kind >= kKindCount) continue;
        Site& s = by[h];
        s.host = h;
        s.items.push_back(it);
    }
    std::vector<Site> out;
    out.reserve(by.size());
    for (auto& [h, s] : by) {
        std::stable_sort(s.items.begin(), s.items.end(), [](const Item& x, const Item& y) {
            if (x.kind != y.kind) return x.kind < y.kind;
            if (x.key != y.key) return x.key < y.key;
            return x.name < y.name;
        });
        out.push_back(std::move(s));
    }
    return out;
}
inline const Site* find(const std::vector<Site>& sites, const std::string& host)
{
    for (const auto& s : sites) if (s.host == host) return &s;
    return nullptr;
}

// --- texts -------------------------------------------------------------------------------------------------------
inline const char* dot() { return " \xc2\xb7 "; }   // " · "
inline std::string autoplayText(int mode)
{
    return mode == 3 ? "Autoplay blocked" : mode == 2 ? "Autoplay without sound" : "Autoplay allowed";
}
inline std::string itemText(const Item& it)
{
    switch (it.kind) {
    case kZoom: return "Zoom " + std::to_string(it.value) + "%";
    case kMobile: return "Mobile site";
    case kDark: return it.value ? "Always dark" : "Never dark";
    case kAutoplay: return autoplayText(it.value);
    case kMute: return "Always muted";
    case kVolume: return "Volume " + std::to_string(it.value) + "%";
    case kAutoFs: return "Video fullscreen";
    case kHttp: return "HTTP allowed";
    case kPopups: return it.value == 2 ? "Pop-ups blocked" : "Pop-ups allowed";
    case kStorage: return "Cookie access (" + std::to_string(it.value) + ")";
    case kPopupAllow: return "Pop-ups allowed";
    case kTweaks: return it.value == 1 ? std::string("1 page tweak") : std::to_string(it.value) + " page tweaks";
    case kReader: return "Reader view always";
    case kGame: return "Game mode";
    case kUblock: return "uBlock off";
    case kAddon: return (it.name.empty() ? it.owner : it.name) + (it.value ? " on" : " off");
    default: return std::string();
    }
}
// The parts of the summary line, in order, each once. Pop-ups set to Block in Site permissions win over the pop-up
// allow list (the popup() hook checks Block first), so "Pop-ups allowed" is not shown next to "Pop-ups blocked".
inline std::vector<std::string> parts(const Site& s)
{
    bool popupsBlocked = false;
    for (const auto& it : s.items) if (it.kind == kPopups && it.value == 2) popupsBlocked = true;
    std::vector<std::string> out;
    for (const auto& it : s.items) {
        if (it.kind == kPopupAllow && popupsBlocked) continue;
        const std::string t = itemText(it);
        if (t.empty() || std::find(out.begin(), out.end(), t) != out.end()) continue;
        out.push_back(t);
    }
    return out;
}
// "Zoom 125% · Autoplay blocked · Pop-ups allowed"
inline std::string summary(const Site& s)
{
    std::string out;
    for (const auto& p : parts(s)) { if (!out.empty()) out += dot(); out += p; }
    return out;
}
// "30%" -> 30 (a store's shown value, e.g. tab volume's label); -1 when it is not a percent ("-", "", "abc%", "30").
inline int percentOf(const std::string& label)
{
    if (label.size() < 2 || label.size() > 5 || label.back() != '%') return -1;
    int v = 0;
    for (size_t i = 0; i + 1 < label.size(); ++i) {
        if (label[i] < '0' || label[i] > '9') return -1;
        v = v * 10 + (label[i] - '0');
    }
    return v;
}
inline std::string countText(size_t n) { return n == 1 ? std::string("1 setting") : std::to_string(n) + " settings"; }

// --- the filter --------------------------------------------------------------------------------------------------
constexpr size_t kMaxQuery = 120;
// What was typed -> what is looked for: lower case, trimmed, no scheme, no path / query / fragment, no user info, no port,
// no trailing dots, no leading "www." ("https://WWW.Example.com/x" -> "example.com"). Brackets of an IPv6 literal go too.
inline std::string cleanQuery(const std::string& typed)
{
    std::string q;
    for (char c : typed.substr(0, kMaxQuery * 4)) if (c != '\r' && c != '\n') q += lower(c);
    size_t a = q.find_first_not_of(" \t"), b = q.find_last_not_of(" \t");
    q = a == std::string::npos ? std::string() : q.substr(a, b - a + 1);
    const size_t scheme = q.find("://");
    if (scheme != std::string::npos && scheme <= 8) q = q.substr(scheme + 3);
    const size_t end = q.find_first_of("/?#");
    if (end != std::string::npos) q = q.substr(0, end);
    const size_t at = q.rfind('@');
    if (at != std::string::npos) q = q.substr(at + 1);
    if (!q.empty() && q[0] == '[') {
        const size_t close = q.find(']');
        q = close == std::string::npos ? q.substr(1) : q.substr(1, close - 1);
    } else {
        const size_t colon = q.find(':');
        if (colon != std::string::npos && q.find(':', colon + 1) == std::string::npos) q = q.substr(0, colon);   // a port
    }
    while (!q.empty() && (q.back() == '.' || q.back() == ' ')) q.pop_back();
    if (q.compare(0, 4, "www.") == 0 && q.size() > 4) q.erase(0, 4);
    if (q.size() > kMaxQuery) q.resize(kMaxQuery);
    return q;
}
// Sites whose host contains the (cleaned) query, in list order. An empty query keeps every site.
inline std::vector<size_t> filter(const std::vector<Site>& sites, const std::string& query)
{
    const std::string q = cleanQuery(query);
    std::vector<size_t> out;
    for (size_t i = 0; i < sites.size(); ++i)
        if (q.empty() || sites[i].host.find(q) != std::string::npos) out.push_back(i);
    return out;
}

// --- the panel's texts ---------------------------------------------------------------------------------------------
inline std::string sitesText(size_t n) { return n == 1 ? std::string("1 site") : std::to_string(n) + " sites"; }
inline std::string listSubtitle(size_t total, size_t shown, const std::string& query)
{
    if (query.empty()) return total == 0 ? std::string("No site has settings of its own") : sitesText(total) + " with settings of their own";
    return std::to_string(shown) + " of " + sitesText(total) + " match \"" + query + "\"";
}
inline std::string searchValue(const std::string& query) { return query.empty() ? std::string("Type part of an address") : "\"" + query + "\""; }
inline std::string emptyLabel(bool hasQuery) { return hasQuery ? "No sites match" : "No site has settings of its own yet"; }
inline std::string detailSubtitle(const Site* s)
{
    if (!s || s->items.empty()) return "Nothing saved: this site uses the defaults";
    return summary(*s);
}

// --- reset ---------------------------------------------------------------------------------------------------------
// Saved keys of `list` that cover `key` as a parent domain (example.com covers m.example.com). The uBlock allow list and
// the pop-up allow list remove those too when one of their keys is removed (so the site is really no longer allowed):
// the question names them.
inline std::vector<std::string> coveringParents(const std::vector<std::string>& list, const std::string& key)
{
    std::vector<std::string> out;
    if (key.empty()) return out;
    for (const auto& e : list)
        if (!e.empty() && e != key && endsWith(key, "." + e) && std::find(out.begin(), out.end(), e) == out.end()) out.push_back(e);
    return out;
}
inline std::string joinList(const std::vector<std::string>& v)
{
    std::string out;
    for (size_t i = 0; i < v.size(); ++i) out += (i == 0 ? "" : i + 1 == v.size() ? " and " : ", ") + v[i];
    return out;
}
inline std::string askTitle(const std::string& host) { return "Reset settings for " + host + "?"; }
// ublockParents / popupParents: coveringParents() of the site's uBlock / pop-up allow keys.
inline std::string askBody(const Site& s, const std::vector<std::string>& ublockParents, const std::vector<std::string>& popupParents)
{
    std::string out = "Back to the defaults: ";
    const auto p = parts(s);
    for (size_t i = 0; i < p.size(); ++i) out += (i ? ", " : "") + p[i];
    out += ". Cookies and site data are kept.";
    if (!ublockParents.empty()) out += " uBlock is turned back on for " + joinList(ublockParents) + " too (it covers this site).";
    if (!popupParents.empty()) out += " Pop-ups from " + joinList(popupParents) + " are no longer always allowed either (it covers this site).";
    return out;
}
inline std::string resetNotice(const std::string& host, bool failed)
{
    return failed ? "Settings reset for " + host + ", except uBlock (its list couldn't be saved)" : "Settings reset for " + host;
}

} // namespace OmniSiteList
'''

SHELL = r'''// OMNI_SITE_LIST_V1: "Sites with custom settings" (shell side). Included from OmniBrowser.cpp right after OmniAddons.h
// (inside its anonymous namespace), so every store it reads is defined above it. The pure part is OmniSiteList.h; the
// reasons are in tools/apply_site_list.py. Main thread only.
//
// It owns no file and no state of its own (only the filter text). Each build reads the stores' in-memory state (after
// their own loaders), and every change or reset goes through the store's own function and the store's own writer, so
// memory and files stay consistent and no file is ever edited here. Private-tab session choices (autoplay, HTTPS-only,
// page tweaks, pop-up allow, site permissions) are never read: only what is saved.
// OMNI_SITE_LIST_V1_R2: reader-sites.txt (OMNI_READER_AUTO_V1) is an optional store. apply_reader_auto.py runs later in
// the recipe, writes OmniReaderAutoShell.h and includes it from OmniFeatures3.h (before this file), so the file's
// presence (__has_include) switches the Reader view parts on; without it they are compiled out.
#pragma once
#if __has_include("OmniReaderAutoShell.h")
#define OMNI_SLI_READER 1
#endif
// OMNI_SITE_LIST_V1_R3: game mode (OMNI_GAME_MODE_V1) the same way: apply_game_mode.py runs later, writes
// OmniGameModeShell.h and includes it from OmniFeatures3.h (before this file).
#if __has_include("OmniGameModeShell.h")
#define OMNI_SLI_GAME 1
#endif
// OMNI_SITE_LIST_V1_R4: three more optional stores, the same way (each shell is included from OmniFeatures3.h, before
// this file; their saved-list helpers never return a private tab's session choice):
//   OMNI_SITE_MUTE_V1        OmniSiteMuteShell.h        omniSmuSavedSites / omniSmuSavedValue / omniSmuSetSaved, key OSMU::hostKey
//   OMNI_SITE_VOLUME_V1      OmniSiteVolumeShell.h      omniSvoSavedSites / omniSvoSavedValue / omniSvoResetSaved, key
//                            OmniMediaControls::site (IPv6 kept in brackets: siteHost() groups it with the other stores)
//   OMNI_AUTO_FULLSCREEN_V1  OmniAutoFullscreenShell.h  omniAfsStore (saved only; omniAfsSession is never read), OAFS::hostKey
#if __has_include("OmniSiteMuteShell.h")
#define OMNI_SLI_MUTE 1
#endif
#if __has_include("OmniSiteVolumeShell.h")
#define OMNI_SLI_VOLUME 1
#endif
#if __has_include("OmniAutoFullscreenShell.h")
#define OMNI_SLI_AUTOFS 1
#endif

namespace OSLI = OmniSiteList;
static_assert(int(OmniAutoplay::kAllow) == 1 && int(OmniAutoplay::kNoSound) == 2 && int(OmniAutoplay::kBlock) == 3,
              "OSLI::autoplayText expects these values");
enum { omniSliKindList = 7395, omniSliKindSite = 7396 };
enum { omniSliRowSearch = 1, omniSliRowNone = 2, omniSliRowSite = 100 };
enum { omniSliDZoom = 1, omniSliDMobile, omniSliDDark, omniSliDAutoplay, omniSliDHttp, omniSliDPopups, omniSliDPopupAllow,
       omniSliDUblock, omniSliDTweaks, omniSliDPerms, omniSliDReset, omniSliDReader, omniSliDGame,
       omniSliDMute, omniSliDVolume, omniSliDAutoFs, omniSliDAddon = 100 };
static std::string omniSliQuery;   // the list's filter ("" = every site)
static std::string omniSliEdit;    // the keyboard's buffer

// --- reading the stores ------------------------------------------------------------------------------------------
static std::vector<OSLI::Item> omniSliCollect()
{
    std::vector<OSLI::Item> out;
    auto add = [&](OSLI::Kind k, const std::string& key, int v, const std::string& name = std::string(), const std::string& owner = std::string()) {
        OSLI::Item it; it.kind = k; it.key = key; it.value = v; it.name = name; it.owner = owner;
        out.push_back(std::move(it));
    };
    omniPrefsLoad();                                                                  // site-zoom.txt, site-ua.txt
    for (const auto& e : omniSiteZoom.entries()) add(OSLI::kZoom, e.first, e.second);
    for (const auto& h : omniMobileHosts) add(OSLI::kMobile, h, 1);
    omniDkLoad();                                                                     // site-dark.txt
    for (const auto& [h, v] : omniDkSites) add(OSLI::kDark, h, v);
    omniApLoad();                                                                     // autoplay.txt (saved rules only)
    for (const auto& [h, m] : omniApStore.sites) if (m != OAP::kDefault) add(OSLI::kAutoplay, h, int(m));
    omniHoLoad();                                                                     // https-only.txt allow lines
    for (const auto& h : omniHoStore.allow) add(OSLI::kHttp, h, 1);
    omniPermLoad();                                                                   // site-permissions.txt (saved only)
    for (const auto& [h, perms] : omniPerm.saved) {
        int storage = 0;
        for (const auto& [k, v] : perms) {
            if (k == "popups") add(OSLI::kPopups, h, v);
            else if (k.rfind("storage:", 0) == 0) ++storage;
        }
        if (storage) add(OSLI::kStorage, h, storage);
    }
    omniPnLoad();                                                                     // popup-allow.txt (saved list only)
    for (const auto& h : omniPnSaved.hosts) add(OSLI::kPopupAllow, h, 1);
    omniStLoad();                                                                     // site-tweaks.txt (saved only)
    for (const auto& [h, t] : omniStStore.sites) if (t.any()) add(OSLI::kTweaks, h, OSTW::count(t));
#ifdef OMNI_SLI_READER
    omniRauLoad();                                                                    // reader-sites.txt (saved only)
    for (const auto& h : omniRauStore.always) add(OSLI::kReader, h, 1);
#endif
#ifdef OMNI_SLI_GAME
    omniGmLoad();                                                                     // game mode sites (saved only)
    for (const auto& h : omniGmStore.sites) add(OSLI::kGame, h, 1);
#endif
#ifdef OMNI_SLI_MUTE
    for (const auto& h : omniSmuSavedSites()) add(OSLI::kMute, h, 1);                 // site-mute.txt (saved only)
#endif
#ifdef OMNI_SLI_VOLUME
    for (const auto& h : omniSvoSavedSites()) {                                       // site-volume.txt (saved only)
        const int pct = OSLI::percentOf(omniSvoSavedValue(h));
        if (pct >= 0) add(OSLI::kVolume, h, pct);
    }
#endif
#ifdef OMNI_SLI_AUTOFS
    omniAfsLoad();                                                                    // site-autofs.txt (saved only)
    for (const auto& h : omniAfsStore.sites) add(OSLI::kAutoFs, h, 1);
#endif
    for (const auto& h : omniBlockerTrustedSites()) add(OSLI::kUblock, h, 1);         // ublock-allowlist.txt
    for (const auto& [id, st] : omniAdState.addons) {                                 // addons/state.json site switches
        const OmniAd* a = omniAdFind(id);
        for (const auto& [h, v] : st.sites) add(OSLI::kAddon, h, v, a ? a->m.name : id, id);
    }
    return out;
}
static std::vector<OSLI::Site> omniSliSites() { return OSLI::merge(omniSliCollect()); }
static OSLI::Site omniSliSite(const std::string& host)
{
    const auto all = omniSliSites();
    const OSLI::Site* s = OSLI::find(all, host);
    if (s) return *s;
    OSLI::Site none; none.host = host;
    return none;
}
// A URL for the stores' own key functions (most take a URL): IPv6 hosts get their brackets back.
static std::string omniSliUrl(const std::string& host)
{
    return "https://" + (host.find(':') != std::string::npos ? "[" + host + "]" : host) + "/";
}

// --- reset: each store's own reset, then each store's own writer -------------------------------------------------------
static void omniSliReset(const OSLI::Site& s)
{
    bool prefs = false, ap = false, ho = false, pn = false, rau = false, gm = false, afs = false, failed = false;
    for (const auto& it : s.items) {
        switch (it.kind) {
        case OSLI::kZoom: omniSiteZoom.erase(it.key); prefs = true; break;
        case OSLI::kMobile: omniMobileHosts.erase(it.key); prefs = true; break;
        case OSLI::kDark: omniDkSetSite(it.key, -1); break;                                       // saves + updates open pages
        case OSLI::kAutoplay: OAP::setSite(omniApStore.sites, it.key, OAP::kDefault); ap = true; break;
        case OSLI::kHttp: OHO::setSite(omniHoStore, omniHoSession, it.key, false, false); ho = true; break;
        case OSLI::kPopups: case OSLI::kStorage: omniPermClearHost(it.key); break;               // saves
        case OSLI::kPopupAllow: OPN::remove(omniPnSaved, it.key); pn = true; break;
        case OSLI::kTweaks: {
            const OSTW::Change c = OSTW::change(omniStStore, omniStSession, it.key, OSTW::Tweaks(), false);
            if (c.savedChanged) omniStWrite();
            omniStApply(it.key);
            break;
        }
#ifdef OMNI_SLI_READER
        case OSLI::kReader: ORAU::setSite(omniRauStore, it.key, false); rau = true; break;
#endif
#ifdef OMNI_SLI_GAME
        case OSLI::kGame: if (OGMM::setSite(omniGmStore, omniGmSession, it.key, false, false)) gm = true; break;
#endif
#ifdef OMNI_SLI_MUTE
        case OSLI::kMute: omniSmuSetSaved(it.key, false); break;                                  // saves + unmutes its tabs
#endif
#ifdef OMNI_SLI_VOLUME
        case OSLI::kVolume: omniSvoResetSaved(it.key); break;                                     // saves + its tabs at 100 %
#endif
#ifdef OMNI_SLI_AUTOFS
        case OSLI::kAutoFs: if (OAFS::setSite(omniAfsStore, it.key, false)) afs = true; break;
#endif
        case OSLI::kUblock: if (!omniBlockerSetSiteTrusted(it.key, false)) failed = true; break;  // saves + reinstalls
        case OSLI::kAddon: {
            omniAdSt(it.owner).sites.erase(it.key);
            if (OmniAd* a = omniAdFind(it.owner)) omniAdApply(*a); else omniAdSaveState();        // add-on gone: just save
            break;
        }
        default: break;
        }
    }
    if (prefs) {   // as omniZoomStep / omniMobileToggle: save, then open tabs follow (the user agent from the next load)
        omniPrefsSave();
        for (auto& t : tabs) { omniApplySiteZoom(t.get()); omniApplyUserAgent(t.get(), t->url); }
        omniPageDirty = true;
    }
    if (ap) omniApWrite();
    if (ho) omniHoWrite();
    if (pn) omniPnWrite();
#ifdef OMNI_SLI_READER
    if (rau) omniRauWrite();
#else
    (void)rau;
#endif
#ifdef OMNI_SLI_GAME
    if (gm) omniGmWrite();
#else
    (void)gm;
#endif
#ifdef OMNI_SLI_AUTOFS
    if (afs) omniAfsWrite();
#else
    (void)afs;
#endif
    notice(OSLI::resetNotice(s.host, failed));
    fprintf(stderr, "OMNI SITE LIST: reset %d choice(s)%s\n", int(s.items.size()), failed ? ", uBlock list not saved" : ""); fflush(stderr);
}
static void omniSliDetailBuild(OmniFxPanel& p);
static void omniSliAskReset(const std::string& host)
{
    const OSLI::Site s = omniSliSite(host);
    if (s.items.empty()) { notice("Nothing is saved for " + host); return; }
    std::vector<std::string> ub, pn;
    const auto trusted = omniBlockerTrustedSites();
    for (const auto& it : s.items) {
        if (it.kind == OSLI::kUblock) for (const auto& x : OSLI::coveringParents(trusted, it.key)) ub.push_back(x);
        if (it.kind == OSLI::kPopupAllow) for (const auto& x : OSLI::coveringParents(omniPnSaved.hosts, it.key)) pn.push_back(x);
    }
    omniAsk(OSLI::askTitle(host), OSLI::askBody(s, ub, pn), "Reset", [host](bool ok) {
        if (!ok) return;
        omniSliReset(omniSliSite(host));   // read again: what is saved now is what gets reset
        if (!omniFxStack.empty() && omniFxStack.back().build == omniSliDetailBuild && omniFxStack.back().page == host) omniFxPop();
        omniFxRefresh();
    });
}

// --- one site: its settings, changed through each store's own setter -----------------------------------------------
static int omniSliPopupsSaved(const std::string& host)   // Site permissions > Pop-ups as saved (never a private choice)
{
    omniPermLoad();
    auto h = omniPerm.saved.find(host);
    if (h == omniPerm.saved.end()) return 0;
    auto v = h->second.find("popups");
    return v == h->second.end() ? 0 : v->second;
}
static void omniSliDetailBuild(OmniFxPanel& p)
{
    const std::string& host = p.page;
    const std::string url = omniSliUrl(host);
    const OSLI::Site site = omniSliSite(host);
    p.subtitle = OSLI::detailSubtitle(&site);
    auto add = [&](int id, std::string label, std::string value, bool on, bool stepper, std::string detail = std::string()) {
        OmniFxRow r; r.id = id; r.label = std::move(label); r.value = std::move(value); r.enabled = on; r.stepper = stepper; r.detail = std::move(detail);
        p.rows.push_back(std::move(r));
    };
    const std::string bh = omniBlockerHostOf(url);   // zoom, site version, uBlock, Site permissions use this key
    omniPrefsLoad();
    const bool ownZoom = !bh.empty() && omniSiteZoom.get(bh) != 0;
    add(omniSliDZoom, "Zoom", omniFxPercent(omniZoomFor(bh)), !bh.empty(), true, ownZoom ? "Cross resets" : "Default");
    add(omniSliDMobile, "Site version", omniMobileHosts.count(bh) ? "Mobile (iPhone)" : "Desktop", !bh.empty(), true);
    const std::string dk = omniDkHost(url);
    const int dark = omniDkSite(dk);
    add(omniSliDDark, "Dark page", dark == 1 ? "Always dark" : dark == 0 ? "Never dark" : omniDarkStyle() == 2 ? "Default (forced)"
        : omniDarkStyle() == 1 ? "Default (natural)" : "Default (off)", !dk.empty(), true);
    omniApLoad();
    const std::string ak = OAP::siteKey(url);
    add(omniSliDAutoplay, "Autoplay", ak.empty() ? std::string("-") : OAP::siteValue(omniApStore, omniApSession, ak, false), !ak.empty(), true);
#ifdef OMNI_SLI_MUTE
    const std::string mk = OSMU::hostKey(url);
    add(omniSliDMute, "Sound", omniSmuSavedValue(mk), !mk.empty(), true);
#endif
#ifdef OMNI_SLI_VOLUME
    const std::string vk = OmniMediaControls::site(url);
    const std::string vv = omniSvoSavedValue(vk);   // "30%" saved, "-" nothing saved
    const bool vOwn = OSLI::percentOf(vv) >= 0;
    add(omniSliDVolume, "Volume", vOwn ? vv : std::string("Default (100%)"), vOwn, false,
        vOwn ? "Cross: reset to 100%" : "Change it in Now playing");
#endif
#ifdef OMNI_SLI_AUTOFS
    omniAfsLoad();
    const std::string fk = OAFS::hostKey(url);
    add(omniSliDAutoFs, "Video", fk.empty() ? std::string("-") : OAFS::rowValue(OAFS::saved(omniAfsStore, fk)), !fk.empty(), true);
#endif
    omniHoLoad();
    const std::string hk = OHO::urlHostKey(url);
    const std::string hv = hk.empty() ? std::string("-") : OHO::siteValue(omniHoStore, omniHoSession, hk, false);
    add(omniSliDHttp, "HTTPS-only", hv, !hk.empty() && hv.rfind("Not needed", 0) != 0, true);
    const int pop = omniSliPopupsSaved(bh);
    add(omniSliDPopups, "Pop-ups and redirects", omniPermValueName(pop), !bh.empty(), true);
    omniPnLoad();
    const std::string pk = OPN::hostKey(host);
    const bool pnOwn = OPN::contains(omniPnSaved, pk), pnAny = OPN::allowedBy(omniPnSaved, pk);
    add(omniSliDPopupAllow, "Always allow pop-ups", pop == 2 ? std::string("Blocked in Site permissions") : pnOwn ? "On" : pnAny ? "On (parent site)" : "Off",
        !pk.empty() && pop != 2, true, "Pop-ups opened without a press");
    const bool ubOn = omniBlockerEnabled();
    add(omniSliDUblock, "uBlock on this site", !ubOn ? std::string("Off everywhere") : omniBlockerSiteTrusted(bh) ? "Off (allowed)" : "On", ubOn && !bh.empty(), true);
    omniStLoad();
    const std::string tk = OSTW::siteKey(url);
    add(omniSliDTweaks, "Page tweaks", OSTW::rowValue(OSTW::saved(omniStStore, tk), !tk.empty()), !tk.empty(), false);
#ifdef OMNI_SLI_READER
    omniRauLoad();
    const std::string rk = ORAU::siteKey(url);
    add(omniSliDReader, "Reader view", rk.empty() ? std::string("-") : ORAU::rowValue(ORAU::saved(omniRauStore, rk)), !rk.empty(), true);
#endif
#ifdef OMNI_SLI_GAME
    omniGmLoad();
    const std::string gk = OGMM::hostKey(url);
    add(omniSliDGame, "Game mode", gk.empty() ? std::string("-") : OGMM::siteValue(omniGmStore.sites.count(gk) != 0, false), !gk.empty(), true);
#endif
    int perms = 0;
    if (auto h = omniPerm.saved.find(bh); h != omniPerm.saved.end()) perms = int(h->second.size());
    add(omniSliDPerms, "Site permissions", perms ? std::to_string(perms) + " saved" : std::string("Default"), !bh.empty(), false);
    const std::string adh = omniAdHostOf(url);
    int i = 0;
    for (const auto& a : omniAds) {
        const int id = omniSliDAddon + i++;
        if (!a.error.empty() || adh.empty()) continue;
        auto f = omniAdState.addons.find(a.m.id);
        const OmniAddonsCore::AddonState none;
        const OmniAddonsCore::AddonState& st = f == omniAdState.addons.end() ? none : f->second;
        const int cur = OmniAddonsCore::siteState(a.m, st, adh);
        if (cur == -2) continue;   // the add-on never runs here
        add(id, a.m.name, cur == 1 ? std::string("Always on") : cur == 0 ? std::string("Always off")
            : std::string("Default (") + (OmniAddonsCore::globalOn(a.m, st) ? "on" : "off") + ")", true, true, "Add-on");
    }
    add(omniSliDReset, "Reset this site", "", !site.items.empty(), false);
    p.rows.back().danger = !site.items.empty();
}
static bool omniSliDetailInput(OmniFxPanel& p, const OmniFxRow& r, int b)
{
    const std::string host = p.page;
    if (b == SDL_CONTROLLER_BUTTON_X) { omniSliAskReset(host); return true; }
    const bool a = b == SDL_CONTROLLER_BUTTON_A, left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT;
    const bool side = left || right;
    if (!a && !side) return false;
    if (!r.enabled) return true;
    const std::string url = omniSliUrl(host);
    const std::string bh = omniBlockerHostOf(url);
    switch (r.id) {
    case omniSliDZoom: {   // as omniZoomStep, for this host: the default zoom is no entry
        const int def = OmniSiteZoom::toPercent(omniFxDefaultZoom()), before = OmniSiteZoom::toPercent(omniZoomFor(bh));
        const int z = a ? def : OmniSiteZoom::step(before, right ? 1 : -1);
        if (z == def) omniSiteZoom.erase(bh); else omniSiteZoom.set(bh, z);
        omniPrefsSave();
        for (auto& t : tabs) if (omniBlockerHostOf(t->url) == bh) omniApplySiteZoom(t.get());
        omniPageDirty = true;
        return true;
    }
    case omniSliDMobile:   // as omniMobileToggle, for this host (open tabs of it get the user agent; it shows on their next load)
        if (!omniMobileHosts.erase(bh)) omniMobileHosts.insert(bh);
        omniPrefsSave();
        for (auto& t : tabs) if (omniBlockerHostOf(t->url) == bh) omniApplyUserAgent(t.get(), t->url);
        notice(std::string(omniMobileHosts.count(bh) ? "Mobile site" : "Desktop site") + " for " + bh + " (from its next load)");
        return true;
    case omniSliDDark: {   // as omniF3SiteInput
        static const int order[] = { -1, 1, 0 };   // Default, Always dark, Never dark
        const std::string dk = omniDkHost(url);
        const int cur = omniDkSite(dk);
        int i = cur == 1 ? 1 : cur == 0 ? 2 : 0;
        i = (i + (left ? 2 : 1)) % 3;
        omniDkSetSite(dk, order[i]);
        return true;
    }
    case omniSliDAutoplay: {   // the saved rule (a normal tab's choice)
        const std::string ak = OAP::siteKey(url);
        omniApLoad();
        const OAP::Mode next = OAP::cycleSite(OAP::siteRule(omniApStore.sites, ak), left ? -1 : 1);
        if (!OAP::setSite(omniApStore.sites, ak, next)) { notice(OAP::siteNotice(ak, next, false, true)); return true; }
        omniApWrite();
        notice("Autoplay on " + ak + ": " + (next == OAP::kDefault ? std::string("default") : std::string(OAP::name(next))) + ". Applies to pages opened from now on");
        return true;
    }
    case omniSliDHttp: {   // the saved choice (a normal tab's), as omniHoSiteInput
        const std::string hk = OHO::urlHostKey(url);
        omniHoLoad();
        const bool allow = omniHoStore.allow.count(hk) == 0;
        const bool ok = OHO::setSite(omniHoStore, omniHoSession, hk, allow, false);
        if (ok) omniHoWrite();
        notice(OHO::siteNotice(hk, allow, false, !ok, omniHoStore.httpsOnly));
        return true;
    }
    case omniSliDPopups: {   // as omniPermSiteInput, always saved (this panel is not a private tab's)
        const int v = omniSliPopupsSaved(bh);
        omniPermSet(bh, "popups", (v + (left ? 2 : 1)) % 3, true);
        return true;
    }
    case omniSliDPopupAllow: {   // as omniPnInput's "Always allow", on the saved list
        const std::string pk = OPN::hostKey(host);
        omniPnLoad();
        if (OPN::allowedBy(omniPnSaved, pk)) { OPN::remove(omniPnSaved, pk); omniPnWrite(); notice(OPN::disallowNotice(pk)); }
        else if (OPN::add(omniPnSaved, pk)) { omniPnWrite(); notice(OPN::allowNotice(pk, false)); }
        else notice("The pop-up allow list is full (500 sites)");
        return true;
    }
    case omniSliDUblock:   // as Site settings > uBlock on this site
    {
        const bool trust = !omniBlockerSiteTrusted(bh);
        if (!omniBlockerSetSiteTrusted(bh, trust)) notice("Couldn't save the uBlock list");
        else notice(std::string(trust ? "uBlock off for " : "uBlock on for ") + bh + " (from its next load)");
        return true;
    }
    case omniSliDTweaks: {   // the Page tweaks panel itself, for this host and the saved choice (mode 0)
        if (!a) return true;
        const std::string tk = OSTW::siteKey(url);
        OmniFxPanel q;
        q.title = "Page tweaks"; q.w = 760;
        q.page = tk; q.mode = 0;
        q.build = omniStPanelBuild; q.input = omniStPanelInput;
        q.faces = { { 0, "Change" }, { 1, "Back" } };
        q.extra = "Applies at once, no reload";
        omniFxPush(std::move(q));
        return true;
    }
#ifdef OMNI_SLI_READER
    case omniSliDReader: {   // the saved choice (a normal tab's), as omniRauSiteInput
        const std::string rk = ORAU::siteKey(url);
        omniRauLoad();
        const bool on = !ORAU::saved(omniRauStore, rk);
        const bool ok = ORAU::setSite(omniRauStore, rk, on);
        if (ok) omniRauWrite();
        notice(ORAU::siteNotice(rk, on, false, !ok));
        return true;
    }
#endif
#ifdef OMNI_SLI_GAME
    case omniSliDGame: {   // the saved choice (a normal tab's)
        const std::string gk = OGMM::hostKey(url);
        omniGmLoad();
        const bool on = omniGmStore.sites.count(gk) == 0;
        bool full = false;
        if (OGMM::setSite(omniGmStore, omniGmSession, gk, on, false, &full)) omniGmWrite();
        notice(OGMM::siteNotice(gk, on, false, full));
        return true;
    }
#endif
#ifdef OMNI_SLI_MUTE
    case omniSliDMute: {   // the saved choice (a normal tab's); omniSmuSetSaved writes, updates open tabs, notices
        const std::string mk = OSMU::hostKey(url);
        omniSmuSetSaved(mk, omniSmuSavedValue(mk) != OSMU::siteValue(true, false));
        return true;
    }
#endif
#ifdef OMNI_SLI_VOLUME
    case omniSliDVolume:   // Cross forgets the remembered volume (open tabs of the site back at 100 %)
        if (a) omniSvoResetSaved(OmniMediaControls::site(url));
        return true;
#endif
#ifdef OMNI_SLI_AUTOFS
    case omniSliDAutoFs: {   // the saved choice (a normal tab's)
        const std::string fk = OAFS::hostKey(url);
        omniAfsLoad();
        const bool on = !OAFS::saved(omniAfsStore, fk);
        const bool ok = OAFS::setSite(omniAfsStore, fk, on);
        if (ok) omniAfsWrite();
        notice(OAFS::siteNotice(fk, on, false, !ok));
        return true;
    }
#endif
    case omniSliDPerms: if (a) omniPermSiteShow(bh); return true;   // Site permissions for this host
    case omniSliDReset: if (a) omniSliAskReset(host); return true;
    default: break;
    }
    if (r.id >= omniSliDAddon && size_t(r.id - omniSliDAddon) < omniAds.size()) {   // as omniAdDetailInput's site row
        OmniAd& ad = omniAds[size_t(r.id - omniSliDAddon)];
        const std::string adh = omniAdHostOf(url);
        auto& st = omniAdSt(ad.m.id);
        const int cur = OmniAddonsCore::siteState(ad.m, st, adh);
        if (cur == -2) return true;
        static const int order[] = { -1, 1, 0 };   // Default, Always on, Always off
        int i = cur == 1 ? 1 : cur == 0 ? 2 : 0;
        i = (i + (left ? 2 : 1)) % 3;
        if (order[i] < 0) st.sites.erase(adh);
        else if (st.sites.size() < OmniAddonsCore::maxSites || st.sites.count(adh)) st.sites[adh] = order[i];
        omniAdApply(ad);
        return true;
    }
    return true;
}
static void omniSliDetailShow(const std::string& host)
{
    if (host.empty()) return;
    OmniFxPanel p;
    p.kind = omniSliKindSite; p.w = 900; p.maxVisible = 9;
    p.title = host; p.page = host;
    p.build = omniSliDetailBuild; p.input = omniSliDetailInput;
    p.faces = { { 0, "Change" }, { 2, "Reset this site" }, { 1, "Back" } };
    p.extra = "D-pad \xe2\x97\x80 \xe2\x96\xb6 change   zoom: Cross resets";
    omniFxPush(std::move(p));
}

// --- the list ----------------------------------------------------------------------------------------------------
static void omniSliListBuild(OmniFxPanel& p)
{
    const auto sites = omniSliSites();
    const auto pick = OSLI::filter(sites, omniSliQuery);
    p.subtitle = OSLI::listSubtitle(sites.size(), pick.size(), omniSliQuery);
    OmniFxRow search; search.id = omniSliRowSearch; search.label = "Search sites\xe2\x80\xa6"; search.value = OSLI::searchValue(omniSliQuery);
    if (!omniSliQuery.empty()) search.detail = "Square clears";
    p.rows.push_back(std::move(search));
    for (size_t i : pick) {
        const OSLI::Site& s = sites[i];
        OmniFxRow r; r.id = omniSliRowSite + int(i);
        r.label = s.host;
        r.detail = OSLI::summary(s);
        p.rows.push_back(std::move(r));
    }
    if (pick.empty()) {
        OmniFxRow none; none.id = omniSliRowNone; none.label = OSLI::emptyLabel(!omniSliQuery.empty()); none.enabled = false;
        p.rows.push_back(std::move(none));
    }
}
static void omniSliOpenKeyboard()
{
    omniSliEdit = omniSliQuery;
    omniKbEdit(&omniSliEdit, "Search sites", [](bool ok) {
        if (!ok || omniFxStack.empty() || omniFxStack.back().build != omniSliListBuild) { omniFxRefresh(); return; }
        OmniFxPanel& p = omniFxStack.back();
        omniSliQuery = OSLI::cleanQuery(omniSliEdit);
        omniFxRebuild(p);
        p.sel = p.rows.size() > 1 && p.rows[1].enabled ? 1 : 0;   // the first match
        p.scroll = 0;
        omniShellDirty = true;
    });
}
static bool omniSliListInput(OmniFxPanel& p, const OmniFxRow& r, int b)
{
    const bool a = b == SDL_CONTROLLER_BUTTON_A, square = b == SDL_CONTROLLER_BUTTON_X;
    if (r.id == omniSliRowSearch || r.id == omniSliRowNone) {
        if (a) { omniSliOpenKeyboard(); return true; }
        if (square && !omniSliQuery.empty()) { omniSliQuery.clear(); omniFxRebuild(p); p.sel = 0; p.scroll = 0; return true; }
        return a || square;
    }
    if (r.id < omniSliRowSite) return a;
    if (a) { omniSliDetailShow(r.label); return true; }
    if (square) { omniSliAskReset(r.label); return true; }
    return false;
}
static void omniSliShow()
{
    omniSliQuery.clear();
    OmniFxPanel p;
    p.kind = omniSliKindList; p.w = 1000; p.maxVisible = 9;
    p.title = "Sites with custom settings";
    p.build = omniSliListBuild; p.input = omniSliListInput;
    p.faces = { { 0, "Open" }, { 2, "Reset this site" }, { 1, "Back" } };
    p.extra = "Choices made in private tabs are not listed";
    omniFxPush(std::move(p));
    OmniFxPanel& q = omniFxStack.back();
    if (q.rows.size() > 1 && q.rows[1].enabled) q.sel = 1;   // the first site, not the search row
}

// --- the two ways in -----------------------------------------------------------------------------------------------
// Browser settings > "Sites with custom settings" (no count: the row is rebuilt on every redraw, the list only when open).
static void omniSliSettingsRow(OmniFxPanel& p)
{
    OmniFxRow r; r.id = omniSliRowId; r.label = "Sites with custom settings";
    p.rows.push_back(std::move(r));
}
static bool omniSliSettingsInput(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    omniSliShow();
    return true;
}
// Site settings > "All sites..."
static void omniSliSiteRow(OmniFxPanel& p)
{
    OmniFxRow r; r.id = omniSliSiteRowId; r.label = "All sites\xe2\x80\xa6"; r.detail = "Every site with settings of its own";
    p.rows.push_back(std::move(r));
}
static bool omniSliSiteInput(const OmniFxRow&, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    omniSliShow();
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSiteClear.h" // OMNI_SITE_CLEAR_V1: Clear data for this site (pure)\n',
         '#include "OmniSiteClear.h" // OMNI_SITE_CLEAR_V1: Clear data for this site (pure)\n'
         '#include "OmniSiteList.h" // OMNI_SITE_LIST_V1: Sites with custom settings (pure)\n'),
        ('#include "OmniAddons.h" // OMNI_ADDONS_V1\n',
         '#include "OmniAddons.h" // OMNI_ADDONS_V1\n'
         '#include "OmniSiteListShell.h" // OMNI_SITE_LIST_V1: Sites with custom settings (after every store it reads)\n'),
    ],
    'OmniBlocker.h': [
        ('bool omniBlockerSetSiteTrusted(const std::string& host, bool trusted);\n',
         'bool omniBlockerSetSiteTrusted(const std::string& host, bool trusted);\n'
         '// OMNI_SITE_LIST_V1: the saved list of trusted (uBlock off) hostnames, as stored (a copy).\n'
         'std::vector<std::string> omniBlockerTrustedSites();\n'),
    ],
    'OmniBlocker.cpp': [
        ('bool omniBlockerSiteTrusted(const std::string& host)\n',
         'std::vector<std::string> omniBlockerTrustedSites() { return trustedSites; } // OMNI_SITE_LIST_V1\n'
         'bool omniBlockerSiteTrusted(const std::string& host)\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static void omniChSettingsRow(OmniFxPanel& p); // OMNI_CONTROLS_HELP_V1 (OmniControlsHelpShell.h)\n',
         'static void omniChSettingsRow(OmniFxPanel& p); // OMNI_CONTROLS_HELP_V1 (OmniControlsHelpShell.h)\n'
         'constexpr int omniSliRowId = 855; // OMNI_SITE_LIST_V1: "Sites with custom settings" (OmniSiteListShell.h)\n'
         'static void omniSliSettingsRow(OmniFxPanel& p);\n'
         'static bool omniSliSettingsInput(int b);\n'),
        ('    omniF2SettingsExtra(p); // OMNI_FEATURES_V2: Passwords, Autofill, Site permissions\n',
         '    omniF2SettingsExtra(p); // OMNI_FEATURES_V2: Passwords, Autofill, Site permissions\n'
         '    omniSliSettingsRow(p); // OMNI_SITE_LIST_V1: Sites with custom settings\n'),
        ('    if (r.id == omniSlRowId) return omniSlSettingsInput(b); // OMNI_SEND_LINK_V1\n',
         '    if (r.id == omniSliRowId) return omniSliSettingsInput(b); // OMNI_SITE_LIST_V1 (before the >= 300 rows)\n'
         '    if (r.id == omniSlRowId) return omniSlSettingsInput(b); // OMNI_SEND_LINK_V1\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniStSiteInput(const OmniFxRow& r, int b);\n',
         'static bool omniStSiteInput(const OmniFxRow& r, int b);\n'
         'constexpr int omniSliSiteRowId = 750; // OMNI_SITE_LIST_V1: "All sites..." (OmniSiteListShell.h)\n'
         'static void omniSliSiteRow(OmniFxPanel& p);\n'
         'static bool omniSliSiteInput(const OmniFxRow& r, int b);\n'),
        ('    omniF2SiteExtra(p); // OMNI_FEATURES_V2: Site permissions, Fill saved login\n',
         '    omniF2SiteExtra(p); // OMNI_FEATURES_V2: Site permissions, Fill saved login\n'
         '    omniSliSiteRow(p); // OMNI_SITE_LIST_V1: All sites...\n'),
        ('    if (r.id == omniStSiteRowId) return omniStSiteInput(r, b); // OMNI_SITE_TWEAKS_V1 (handles its disabled state)\n',
         '    if (r.id == omniSliSiteRowId) return omniSliSiteInput(r, b); // OMNI_SITE_LIST_V1\n'
         '    if (r.id == omniStSiteRowId) return omniStSiteInput(r, b); // OMNI_SITE_TWEAKS_V1 (handles its disabled state)\n'),
    ],
}
# Names this patch adds: none may exist before it (checked on a tree without MARK).
NEW_NAMES = ('omniSli', 'OSLI', 'OmniSiteList', 'omniBlockerTrustedSites')


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
    for n in NEW_NAMES:
        if n in s:
            sys.exit('%s: %r already used (before %s)' % (name, n, MARK))
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
    for name, mark in (('OmniBrowser.cpp', 'OMNI_SITE_CLEAR_V1'), ('OmniQuickMenu.h', 'OMNI_SITE_TWEAKS_V1'),
                       ('OmniBrowserSettings.h', 'OMNI_CONTROLS_HELP_V1'), ('OmniBrowserSettings.h', 'OMNI_SETTINGS_SEARCH_V1')):
        if mark not in (root / name).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: apply its patch first' % (name, mark))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniSiteList.h', PURE, 'OmniSiteClear.h'),
            write_new('OmniSiteListShell.h', SHELL, 'OmniSiteClearShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK + ' (r4)')


main()
