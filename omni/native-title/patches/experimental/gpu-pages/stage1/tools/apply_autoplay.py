#!/usr/bin/env python3
"""OMNI_AUTOPLAY_V1 (2026-11-16): choose whether pages may start video and sound by themselves, for every site and
per site (what Chrome / Safari / Firefox call "Autoplay").

What the user sees
  - Browser settings > "Autoplay": Allow (default: today's behaviour) / Block sound / Block all. Cross or D-pad
    left / right steps it; applies to pages loaded from then on (notice says so).
      Allow        pages start media as before.
      Block sound  a page may start a video only muted; sound waits for a press on the page (Cross on the player).
                   Most players then start muted or show their play button.
      Block all    nothing starts until pressed, and media is not preloaded (less memory and data on the console).
  - Site settings (Options > Site settings, or hold Cross > Site settings) > "Autoplay on this site":
    Default (<global>) / Allow / Block sound / Block all. Changing it reloads the page so it takes effect.
    Choices made in a private tab last for this session only (as Site permissions do) and apply to private tabs
    only: a normal tab follows, shows and changes the saved choice, never the private one (r2).
  - With a blocking global choice, a few video sites are allowed by default so opening a video from the address bar,
    Continue watching or a link still plays: youtube.com, twitch.tv, vimeo.com, dailymotion.com (and Omni's own
    127.0.0.1 / localhost apps). A per-site choice overrides that. The site row shows "Allow (video site)" for them.

How
  WebKit's own per-navigation website policies (WKWebsitePolicies autoplay policy, the mechanism Safari uses for its
  per-site setting): the main navigation policy callback (omniEverydayNavigation in OmniBrowser.cpp) ends with
  WKFramePolicyListenerUse(listener); that call becomes omniApUse(action, listener), which for a MAIN-frame
  navigation whose decision is not "Allow by the global setting" answers WKFramePolicyListenerUseWithPolicies with
  kWKWebsiteAutoplayPolicy{Allow, AllowWithoutSound, Deny}. WebCore applies it to the new document
  (Document::requiresUserGestureForAudioPlayback / ...VideoPlayback / mediaDataLoadsAutomatically), its subframes
  follow the top document. With "Allow" everywhere and no site rows nothing changes (plain Use, as before).
  Controller presses reach pages as real mouse / key events, so they count as user gestures. Nothing is sent
  anywhere; no page script is added (YouTube's attestation is untouched).

Storage: /data/omni/autoplay.txt through omniIoQueue (full rewrite), read once on first use (<= 256 KB):
    omni-autoplay\t1
    global\t<allow|nosound|block>
    site\t<host>\t<allow|nosound|block>
  hosts lower case, without "www." and port; a rule covers subdomains (youtube.com covers m.youtube.com); at most
  500 site rows. Nothing is written in the self-test modes.

Pure part: engine/entry/OmniAutoplay.h (no SDL/WebKit): host keys, rule lookup, parse/serialize, cycling, texts.
Tested by tools/test_autoplay.cpp:   g++ -std=c++20 -I<tree>/engine/entry test_autoplay.cpp -o t && ./t
Shell side: engine/entry/OmniAutoplayShell.h (included from OmniFeatures3.h after OmniTabSessionsShell.h).

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp        the OmniContinueWatching.h include line; the WKBackForwardListRef.h include line (adds
                         WKWebsitePolicies.h); the omniFileDownloadsTake forward declaration (adds omniApUse's);
                         the last "WKFramePolicyListenerUse(listener);" of omniEverydayNavigation's action callback
                         (matched together with the OMNI_FILE_DOWNLOADS_V1 response-callback line after it).
  OmniBrowserSettings.h  the omniCwRowId constexpr line (declarations); the "Web pages can use the controller" row
                         (row goes after it); the omniCwRowId input line (handler goes before it).
  OmniQuickMenu.h        the site-settings enum line (declarations); the omniF3SiteRows call (row after it); the
                         "r.id >= 900" line of omniFxSiteInput (handler before it, so it runs before the
                         disabled-row and >= 300 checks).
  OmniFeatures3.h        the OmniTabSessionsShell.h include line.
Apply AFTER apply_tab_sessions.py and apply_continue_watching.py (their lines are anchors).
Upgrading (r2: private-tab choices no longer reach normal tabs): only the two headers changed; they are rewritten
whenever they differ, so an r1 tree gets them and the result is byte-identical to a fresh apply. Rewriting
OmniAutoplayShell.h drops apply_https_only.py's GPC edits in it: run apply_https_only.py after this (as always).
usage: apply_autoplay.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_AUTOPLAY_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_AUTOPLAY_V1: the pure part of the autoplay setting (no SDL, no WebKit). The shell side is OmniAutoplayShell.h;
// the reasons are in tools/apply_autoplay.py. Tested on the host with g++ (test_autoplay.cpp).
// OMNI_AUTOPLAY_V1_R2: decide() / siteValue() take the tab's private flag (private choices stay in private tabs).
#pragma once
#include <cstddef>
#include <map>
#include <string>

namespace OmniAutoplay {

enum Mode { kDefault = 0, kAllow, kNoSound, kBlock };   // kDefault: a site follows the global choice
enum Source { kGlobal = 0, kSite, kBuiltIn, kNotWeb };
struct Store { Mode global = kAllow; std::map<std::string, Mode> sites; };
struct Decision { Mode mode = kAllow; Source source = kNotWeb; std::string rule; };

constexpr size_t kMaxSites = 500, kHostMax = 253;
constexpr long kMaxFileBytes = 256L << 10;
constexpr const char* kFileName = "autoplay.txt";
constexpr const char* kHeader = "omni-autoplay\t1";
// Allowed by default when the global choice blocks, so videos opened from the address bar / Continue watching play.
constexpr const char* kVideoSites[] = { "youtube.com", "twitch.tv", "vimeo.com", "dailymotion.com" };
constexpr const char* kLocalHosts[] = { "127.0.0.1", "localhost" };

inline const char* key(Mode m) { return m == kAllow ? "allow" : m == kNoSound ? "nosound" : m == kBlock ? "block" : "default"; }
inline Mode parseMode(const std::string& s)
{
    return s == "allow" ? kAllow : s == "nosound" ? kNoSound : s == "block" ? kBlock : kDefault;
}
inline const char* name(Mode m) { return m == kAllow ? "Allow" : m == kNoSound ? "Block sound" : m == kBlock ? "Block all" : "Default"; }

// "https://User@WWW.Example.COM:8443/a?b" -> "example.com". "" for anything that is not http(s) or has no host.
inline std::string siteKey(const std::string& url)
{
    size_t start;
    if (url.compare(0, 8, "https://") == 0) start = 8;
    else if (url.compare(0, 7, "http://") == 0) start = 7;
    else return std::string();
    size_t end = url.find_first_of("/?#", start);
    if (end == std::string::npos) end = url.size();
    std::string auth = url.substr(start, end - start);
    const size_t at = auth.rfind('@');
    if (at != std::string::npos) auth = auth.substr(at + 1);
    std::string host;
    if (!auth.empty() && auth[0] == '[') {               // IPv6 literal: keep the brackets, drop the port
        const size_t close = auth.find(']');
        if (close == std::string::npos) return std::string();
        host = auth.substr(0, close + 1);
    } else host = auth.substr(0, auth.find(':'));
    for (auto& c : host) if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
    while (!host.empty() && host.back() == '.') host.pop_back();
    if (host.compare(0, 4, "www.") == 0 && host.size() > 4) host = host.substr(4);
    if (host.empty() || host.size() > kHostMax) return std::string();
    for (char c : host)
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_' || c == ':' || c == '[' || c == ']'))
            return std::string();
    return host;
}
// The host and each parent domain, most specific first ("a.b.example.com", "b.example.com", "example.com").
// IP literals and single labels have no parents.
inline bool isIp(const std::string& host)
{
    if (!host.empty() && host[0] == '[') return true;
    for (char c : host) if (!((c >= '0' && c <= '9') || c == '.')) return false;
    return true;
}
template <class F> inline bool eachDomain(const std::string& host, F f)
{
    if (host.empty()) return false;
    if (f(host)) return true;
    if (isIp(host)) return false;
    for (size_t dot = host.find('.'); dot != std::string::npos; dot = host.find('.', dot + 1)) {
        const std::string parent = host.substr(dot + 1);
        if (parent.find('.') == std::string::npos) break;    // never a bare TLD ("com")
        if (f(parent)) return true;
    }
    return false;
}
inline bool builtInAllowed(const std::string& host)
{
    for (const char* h : kLocalHosts) if (host == h) return true;
    return eachDomain(host, [](const std::string& d) { for (const char* v : kVideoSites) if (d == v) return true; return false; });
}

// session: rules made in private tabs (this run only). privateTab: the navigating tab is private; only then is the
// session consulted (it wins over the saved rules there, and a session kDefault row means "this site follows the
// global choice" even when a saved rule exists). A normal tab sees the saved rules only, so it never reveals or
// follows what was chosen in a private tab. (OMNI_AUTOPLAY_V1_R2)
inline Decision decide(const Store& store, const std::map<std::string, Mode>& session, const std::string& url, bool privateTab)
{
    Decision d;
    const std::string host = siteKey(url);
    if (host.empty()) return d;                          // kNotWeb: no policy, WebKit's defaults
    bool explicitDefault = false;
    auto find = [&](const std::map<std::string, Mode>& rules, bool stopOnDefault) {
        return eachDomain(host, [&](const std::string& h) {
            auto it = rules.find(h);
            if (it == rules.end()) return false;
            if (it->second == kDefault) { explicitDefault = stopOnDefault; return stopOnDefault; }
            d.mode = it->second; d.source = kSite; d.rule = h;
            return true;
        });
    };
    if (privateTab && find(session, true)) { if (!explicitDefault) return d; }
    else if (find(store.sites, false)) return d;
    if (store.global != kAllow && builtInAllowed(host)) { d.mode = kAllow; d.source = kBuiltIn; return d; }
    d.mode = store.global == kDefault ? kAllow : store.global; d.source = kGlobal;
    return d;
}
// False: answer the navigation exactly as before (plain Use, WebKit's defaults).
inline bool needsPolicy(const Decision& d) { return d.source == kSite || d.source == kBuiltIn || (d.source == kGlobal && d.mode != kAllow); }

// --- file --------------------------------------------------------------------------------------------------------
inline std::string serialize(const Store& s)
{
    std::string out = std::string(kHeader) + "\n";
    out += std::string("global\t") + key(s.global == kDefault ? kAllow : s.global) + "\n";
    size_t n = 0;
    for (const auto& [host, m] : s.sites) {
        if (m == kDefault || host.empty() || n >= kMaxSites) continue;
        out += "site\t" + host + "\t" + key(m) + "\n";
        ++n;
    }
    return out;
}
inline Store parse(const std::string& text)
{
    Store s;
    size_t pos = 0;
    while (pos < text.size()) {
        size_t nl = text.find('\n', pos);
        if (nl == std::string::npos) nl = text.size();
        std::string line = text.substr(pos, nl - pos);
        pos = nl + 1;
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.pop_back();
        const size_t t1 = line.find('\t');
        if (t1 == std::string::npos) continue;
        const std::string kind = line.substr(0, t1);
        if (kind == "global") {
            const Mode m = parseMode(line.substr(t1 + 1));
            if (m != kDefault) s.global = m;
        } else if (kind == "site") {
            const size_t t2 = line.find('\t', t1 + 1);
            if (t2 == std::string::npos) continue;
            const std::string host = siteKey("https://" + line.substr(t1 + 1, t2 - t1 - 1) + "/");
            const Mode m = parseMode(line.substr(t2 + 1));
            if (host.empty() || m == kDefault) continue;
            if (!s.sites.count(host) && s.sites.size() >= kMaxSites) continue;
            s.sites[host] = m;
        }
    }
    return s;
}

// --- changing ----------------------------------------------------------------------------------------------------
inline Mode cycleGlobal(Mode m, int dir)   // Allow -> Block sound -> Block all -> Allow
{
    const int i = (m == kNoSound ? 1 : m == kBlock ? 2 : 0) + (dir < 0 ? 2 : 1);
    return Mode(kAllow + i % 3);
}
inline Mode cycleSite(Mode m, int dir)     // Default -> Allow -> Block sound -> Block all -> Default
{
    return Mode(((int(m) + (dir < 0 ? 3 : 1)) % 4));
}
// The rule for exactly `host` (kDefault: none). Removing (kDefault) always works; a new host when 500 exist does not.
inline Mode siteRule(const std::map<std::string, Mode>& rules, const std::string& host)
{
    auto it = rules.find(host);
    return it == rules.end() ? kDefault : it->second;
}
inline bool setSite(std::map<std::string, Mode>& rules, const std::string& host, Mode m)
{
    if (host.empty()) return false;
    if (m == kDefault) { rules.erase(host); return true; }
    if (!rules.count(host) && rules.size() >= kMaxSites) return false;
    rules[host] = m;
    return true;
}

// --- texts -------------------------------------------------------------------------------------------------------
inline std::string globalDetail(Mode m)
{
    return m == kNoSound ? "Videos may start muted; sound waits for a press on the page"
        : m == kBlock ? "Nothing plays until you press play; media is not preloaded"
        : "Pages may start video and sound by themselves";
}
// The site row's value: the site's own rule, or what applies without one. privateTab: as in decide() (a normal tab
// never shows a private-tab choice).
inline std::string siteValue(const Store& store, const std::map<std::string, Mode>& session, const std::string& host, bool privateTab)
{
    const Mode own = privateTab && session.count(host) ? siteRule(session, host) : siteRule(store.sites, host);
    if (own != kDefault) return name(own);
    const Decision d = decide(store, session, "https://" + host + "/", privateTab);
    if (d.source == kSite) return std::string(name(d.mode)) + " (from " + d.rule + ")";
    if (d.source == kBuiltIn) return "Allow (video site)";
    return std::string("Default (") + name(store.global == kDefault ? kAllow : store.global) + ")";
}
inline std::string globalNotice(Mode m)
{
    return std::string("Autoplay: ") + name(m) + ". Applies to pages you open from now on";
}
inline std::string siteNotice(const std::string& host, Mode m, bool privateTab, bool full)
{
    if (full) return "Too many sites with their own autoplay choice (500). Reset one first";
    std::string s = "Autoplay on " + host + ": " + (m == kDefault ? std::string("default") : std::string(name(m)));
    if (privateTab) s += " (this session only)";
    return s + ". Reloading...";
}

} // namespace OmniAutoplay
'''

SHELL = r'''// OMNI_AUTOPLAY_V1: autoplay setting (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous
// namespace, after OmniTabSessionsShell.h). The pure part is OmniAutoplay.h; the reasons are in tools/apply_autoplay.py.
// Everything runs on the main thread; the file is written by omniIoQueue.
#pragma once

namespace OAP = OmniAutoplay;
static OAP::Store omniApStore;
static bool omniApLoaded = false;
static std::map<std::string, OAP::Mode> omniApSession;   // choices made in private tabs: this run, private tabs only

static void omniApLoad()
{
    if (omniApLoaded) return;
    omniApLoaded = true;
    FILE* f = fopen(omniData(OAP::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) < OAP::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    omniApStore = OAP::parse(text);
}
static void omniApWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OAP::kFileName), OAP::serialize(omniApStore), false);
}
static WKWebsiteAutoplayPolicy omniApWk(OAP::Mode m)
{
    switch (m) {
    case OAP::kAllow: return kWKWebsiteAutoplayPolicyAllow;
    case OAP::kNoSound: return kWKWebsiteAutoplayPolicyAllowWithoutSound;
    case OAP::kBlock: return kWKWebsiteAutoplayPolicyDeny;
    default: return kWKWebsiteAutoplayPolicyDefault;
    }
}
// The last step of omniEverydayNavigation's action callback (was a plain WKFramePolicyListenerUse).
static void omniApUse(WKNavigationActionRef action, WKFramePolicyListenerRef listener)
{
    auto target = adoptWK(WKNavigationActionCopyTargetFrameInfo(action));
    if (target && WKFrameInfoGetIsMainFrame(target.get())) {
        omniApLoad();
        auto request = adoptWK(WKNavigationActionCopyRequest(action));
        auto url = request ? adoptWK(WKURLRequestCopyURL(request.get())) : WKRetainPtr<WKURLRef>();
        const std::string u = url ? OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get()) : std::string();
        // OMNI_AUTOPLAY_V1_R2: private-tab choices only for private tabs (an unknown tab counts as normal)
        WKPageRef page = WKFrameInfoGetPage(target.get());
        Tab* tab = page ? omniTabForPage(page) : nullptr;
        const OAP::Decision d = OAP::decide(omniApStore, omniApSession, u, tab && tab->omniPrivate);
        if (OAP::needsPolicy(d)) {
            auto policies = adoptWK(WKWebsitePoliciesCreate());
            WKWebsitePoliciesSetAutoplayPolicy(policies.get(), omniApWk(d.mode));
            WKFramePolicyListenerUseWithPolicies(listener, policies.get());
            return;
        }
    }
    WKFramePolicyListenerUse(listener);
}

// --- Browser settings > Autoplay ---------------------------------------------------------------------------------
static void omniApSettingsRow(OmniFxPanel& p)
{
    omniApLoad();
    OmniFxRow r; r.id = omniApRowId; r.label = "Autoplay"; r.value = OAP::name(omniApStore.global); r.stepper = true;
    r.detail = OAP::globalDetail(omniApStore.global);
    p.rows.push_back(r);
}
static bool omniApSettingsInput(int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT;
    if (b != SDL_CONTROLLER_BUTTON_A && !left && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    omniApLoad();
    omniApStore.global = OAP::cycleGlobal(omniApStore.global, left ? -1 : 1);
    omniApWrite();
    notice(OAP::globalNotice(omniApStore.global));
    return true;
}

// --- Site settings > Autoplay on this site -----------------------------------------------------------------------
static std::string omniApSiteHost() { return active() ? OAP::siteKey(active()->url) : std::string(); }
static void omniApSiteRow(OmniFxPanel& p, const std::string&)
{
    omniApLoad();
    const std::string host = omniApSiteHost();
    OmniFxRow r; r.id = omniApSiteRowId; r.label = "Autoplay on this site"; r.stepper = true; r.enabled = !host.empty();
    r.value = host.empty() ? std::string("-") : OAP::siteValue(omniApStore, omniApSession, host, active() && active()->omniPrivate);
    p.rows.push_back(r);
}
static bool omniApSiteInput(const OmniFxRow& r, int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT;
    if (b != SDL_CONTROLLER_BUTTON_A && !left && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    const std::string host = omniApSiteHost();
    if (!r.enabled || host.empty() || !active()) return true;
    omniApLoad();
    const bool priv = active()->omniPrivate;
    const OAP::Mode saved = OAP::siteRule(omniApStore.sites, host);
    const OAP::Mode before = priv && omniApSession.count(host) ? omniApSession[host] : saved;
    const OAP::Mode next = OAP::cycleSite(before, left ? -1 : 1);
    bool ok = true;
    if (priv) {   // a session row (kDefault included) exists only while the private choice differs from the saved one
                  // (a normal tab reads and changes the saved rule only: it never sees this row)
        if (next == saved) omniApSession.erase(host);
        else omniApSession[host] = next;
    } else {
        ok = OAP::setSite(omniApStore.sites, host, next);
        if (ok) omniApWrite();
    }
    notice(OAP::siteNotice(host, next, priv, !ok));
    if (ok) WKPageReload(active()->page);
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniContinueWatching.h" // OMNI_CONTINUE_WATCHING_V1: start-page row from the resume add-on (pure)\n',
         '#include "OmniContinueWatching.h" // OMNI_CONTINUE_WATCHING_V1: start-page row from the resume add-on (pure)\n'
         '#include "OmniAutoplay.h" // OMNI_AUTOPLAY_V1: autoplay choice per site, autoplay.txt (pure)\n'),
        ('#include <WebKit/WKBackForwardListRef.h> // OMNI_FEATURES_V3: unloaded tabs\n',
         '#include <WebKit/WKBackForwardListRef.h> // OMNI_FEATURES_V3: unloaded tabs\n'
         '#include <WebKit/WKWebsitePolicies.h> // OMNI_AUTOPLAY_V1: per-navigation autoplay policy\n'),
        ('static bool omniFileDownloadsTake(WKPageRef page, WKURLResponseRef response); // OMNI_FILE_DOWNLOADS_V1\n',
         'static bool omniFileDownloadsTake(WKPageRef page, WKURLResponseRef response); // OMNI_FILE_DOWNLOADS_V1\n'
         'static void omniApUse(WKNavigationActionRef action, WKFramePolicyListenerRef listener); // OMNI_AUTOPLAY_V1 (OmniAutoplayShell.h)\n'),
        ('        WKFramePolicyListenerUse(listener);\n'
         '    };\n'
         '    nav.decidePolicyForNavigationResponse = [](WKPageRef page, WKNavigationResponseRef navigationResponse, WKFramePolicyListenerRef listener, WKTypeRef, const void*) { // OMNI_FILE_DOWNLOADS_V1: page named\n',
         '        omniApUse(action, listener); // OMNI_AUTOPLAY_V1: main-frame autoplay policy (was WKFramePolicyListenerUse)\n'
         '    };\n'
         '    nav.decidePolicyForNavigationResponse = [](WKPageRef page, WKNavigationResponseRef navigationResponse, WKFramePolicyListenerRef listener, WKTypeRef, const void*) { // OMNI_FILE_DOWNLOADS_V1: page named\n'),
    ],
    'OmniBrowserSettings.h': [
        ('constexpr int omniCwRowId = 870; // OMNI_CONTINUE_WATCHING_V1 (OmniContinueWatchingShell.h)\n',
         'constexpr int omniCwRowId = 870; // OMNI_CONTINUE_WATCHING_V1 (OmniContinueWatchingShell.h)\n'
         'constexpr int omniApRowId = 880; // OMNI_AUTOPLAY_V1 (OmniAutoplayShell.h)\n'
         'static void omniApSettingsRow(OmniFxPanel& p);\n'
         'static bool omniApSettingsInput(int b);\n'),
        ('    add(omniFxSetGamepad, "Web pages can use the controller", omniGamepadEnabled() ? "On" : "Off", true); // OMNI_GAMEPAD_V1\n',
         '    add(omniFxSetGamepad, "Web pages can use the controller", omniGamepadEnabled() ? "On" : "Off", true); // OMNI_GAMEPAD_V1\n'
         '    omniApSettingsRow(p); // OMNI_AUTOPLAY_V1: Allow / Block sound / Block all\n'),
        ('    if (r.id == omniCwRowId) return omniCwSettingsInput(b); // OMNI_CONTINUE_WATCHING_V1 (before the >= 300 rows)\n',
         '    if (r.id == omniApRowId) return omniApSettingsInput(b); // OMNI_AUTOPLAY_V1 (before the >= 300 rows)\n'
         '    if (r.id == omniCwRowId) return omniCwSettingsInput(b); // OMNI_CONTINUE_WATCHING_V1 (before the >= 300 rows)\n'),
    ],
    'OmniQuickMenu.h': [
        ('enum { omniFxSiteBlock = 1, omniFxSiteBlockAll, omniFxSiteMobile, omniFxSiteZoom, omniFxSiteReload };\n',
         'enum { omniFxSiteBlock = 1, omniFxSiteBlockAll, omniFxSiteMobile, omniFxSiteZoom, omniFxSiteReload };\n'
         'constexpr int omniApSiteRowId = 710; // OMNI_AUTOPLAY_V1 (OmniAutoplayShell.h)\n'
         'static void omniApSiteRow(OmniFxPanel& p, const std::string& host);\n'
         'static bool omniApSiteInput(const OmniFxRow& r, int b);\n'),
        ('    omniF3SiteRows(p, host); // OMNI_FEATURES_V3: dark page on this site\n',
         '    omniF3SiteRows(p, host); // OMNI_FEATURES_V3: dark page on this site\n'
         '    omniApSiteRow(p, host); // OMNI_AUTOPLAY_V1: Autoplay on this site\n'),
        ('    if (r.id >= 900) return omniF2SiteInput(r, b); // OMNI_FEATURES_V2\n',
         '    if (r.id == omniApSiteRowId) return omniApSiteInput(r, b); // OMNI_AUTOPLAY_V1 (handles its disabled state)\n'
         '    if (r.id >= 900) return omniF2SiteInput(r, b); // OMNI_FEATURES_V2\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniTabSessionsShell.h" // OMNI_TAB_SESSIONS_V1\n',
         '#include "OmniTabSessionsShell.h" // OMNI_TAB_SESSIONS_V1\n'
         '#include "OmniAutoplayShell.h" // OMNI_AUTOPLAY_V1\n'),
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
    if 'OMNI_TAB_SESSIONS_V1' not in (root / 'OmniFeatures3.h').read_bytes().decode('utf-8'):
        sys.exit('OmniFeatures3.h: OMNI_TAB_SESSIONS_V1 missing: apply_tab_sessions.py first')
    if 'OMNI_CONTINUE_WATCHING_V1' not in (root / 'OmniBrowserSettings.h').read_bytes().decode('utf-8'):
        sys.exit('OmniBrowserSettings.h: OMNI_CONTINUE_WATCHING_V1 missing: apply_continue_watching.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniAutoplay.h', PURE, 'OmniTabSessions.h'),
            write_new('OmniAutoplayShell.h', SHELL, 'OmniFeatures.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
