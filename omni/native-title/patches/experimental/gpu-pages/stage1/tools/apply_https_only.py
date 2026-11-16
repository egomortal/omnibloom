#!/usr/bin/env python3
"""OMNI_HTTPS_ONLY_V1 (2026-11-16): HTTPS-only mode (roadmap R3-033) and a Global Privacy Control switch.

What the user sees
  - Browser settings > "HTTPS-only mode": Off (default for now) / On. Cross or D-pad left / right toggles; applies to
    pages opened from then on.
      On: an http:// address opened in a tab (typed, a link, a bookmark, a redirect) is opened as https:// instead.
      If the secure attempt fails (certificate / TLS error, connection refused or reset, timeout, or the site sends
      Omni straight back to http), Omni shows its own panel over the page:
          "This site doesn't support a secure connection"   http://host/...
          Cross / Circle  "Go back"                    the previous page stays (nothing was loaded); the
                                                       highlighted, safe default
          Square          "Continue to the http site"  allowed for that host until Omni closes
      "Always" for a host: Site settings > "HTTPS-only on this site": Upgrade to https / Allow http.
      In a private tab that choice, and "Continue" pressed there, last for this session only and apply to private
      tabs only: normal tabs keep upgrading the host and never show the private choice (r2). "Continue" from a
      normal tab applies to every tab until Omni closes.
      Never upgraded: 127.0.0.1 / localhost / ::1 (and *.localhost), private LAN addresses (10/8, 172.16/12,
      192.168/16, 169.254/16, fc00::/7, fe80::/10, IPv4-mapped forms of those), *.local (so the Downloads app on
      127.0.0.1 / the console's LAN address is never touched), omni:// / about: / data: pages (not http at all),
      hosts the user allowed. A port alone exempts nothing (r2: port 8765 on a public host used to). Subresources
      (images, scripts, frames) are not touched. Back / Forward and Reload of an http page that is already in the
      history, and non-GET submissions (a form POST to http), load as before: re-issuing
      them as a new https load would break the history entry / drop the form body.
  - Browser settings > "Ask sites not to sell or share my data": Off (default) / On. On: WebKit's Global Privacy
    Control (WKWebsitePoliciesSetGlobalPrivacyControlEnabled, present in this WebKit's C API): the page's settings
    get globalPrivacyControlEnabled, so navigator.globalPrivacyControl is true and the network process adds
    "Sec-GPC: 1" to requests to potentially trustworthy (https / local) origins (NetworkResourceLoader). It is applied
    through the per-navigation website policies that apply_autoplay.py already answers in omniApUse (one policies
    object for both; with GPC off and autoplay "Allow" the navigation is answered with plain Use exactly as before).

How
  - omniEverydayNavigation's action callback (OMNI_EVERYDAY_V1, OmniBrowser.cpp): for a MAIN-frame navigation,
    right after the target URL is read (before YouTube-TV / user-agent handling, which then see the https URL),
    omniHoPolicy() asks the pure decide(): Upgrade -> WKFramePolicyListenerIgnore + tab->omniPendingLoad = https URL
    (the same re-issue path the UA switch uses; loaded on the next tick) and the attempt is remembered per tab
    (OmniFxTabState: http URL, https URL, host, time). Interstitial -> Ignore + the panel (an http navigation to
    the host whose https attempt is still in flight = the site redirected https back to http; upgrading again would
    loop). The final omniApUse(action, listener) line written by apply_autoplay.py is not touched.
  - failed() (the provisional-load-failure callback, also didFailNavigation): omniHoLoadFailed() runs first; when
    the failing URL is the in-flight https attempt's host and the error is a connection / TLS failure
    (CurlErrorDomain: 7, 16, 28, 35, 51-56, 58-60, 77, 80, 83, 90-92) the panel is shown instead of the generic
    error. DNS failures (6) and everything else fall through to the normal error panel (http would fail too).
    Any failure (cancel included) ends the in-flight attempt; a commit ends it too (didCommitNavigation).
  - The panel is the OMNI_FEATURES_V1 error panel (OmniErrorPage.h) with its own title / text / two chips (Cross
    "Go back" first and highlighted, Square "Continue to the http site": Square is free there, the normal error
    panel only uses it for uBlock's "Allow this site"):
    omniFxErrorDraw / omniFxErrorButton / omniFxErrorClick hand over to omniHoError* when failDomain is
    "OmniHttpsOnly". Retry elsewhere (failURL is the http URL) goes through the upgrade again.

Storage: /data/omni/https-only.txt through omniIoQueue (full rewrite), read once on first use (<= 64 KB):
    omni-https-only\t1
    https_only\t<0|1>
    gpc\t<0|1>
    allow\t<host>            hosts lower case, without "www." and port; exact host (no subdomains); <= 500 rows
  Nothing is written in the self-test modes (and the everyday navigation client is not installed there at all).

Pure part: engine/entry/OmniHttpsOnly.h (no SDL/WebKit): URL / host parsing, IPv4 / IPv6 range checks, exemptions,
upgrade URL, decide(), fallback errors, allow-list parse / serialize / set, texts.
Tested by tools/test_https_only.cpp:   g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_https_only.cpp -o t && ./t
Shell side: engine/entry/OmniHttpsOnlyShell.h (included from OmniFeatures3.h after OmniAutoplayShell.h).

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp        the OmniAutoplay.h include line (written by apply_autoplay.py); the head of failed()
                         (declaration before it) + its "int code = WKErrorGetErrorCode(error);" line together with
                         the OmniUBlockRedirect line after it (hook between them); the omniApUse forward declaration
                         (apply_autoplay.py's; ours go after it); the targetURL line of omniEverydayNavigation's
                         action callback together with the OMNI_YOUTUBE_TV_V1 comment after it (hook between);
                         "omniApplySiteZoom(tab);\n    };\n}" closing its didCommitNavigation (hook before it).
  OmniErrorPage.h        the saveURL member of OmniFxTabState (state after it); the heads of omniFxErrorDraw,
                         omniFxErrorButton, omniFxErrorClick (declarations before the first, hand-over lines).
  OmniAutoplayShell.h    the comment above omniApUse and its needsPolicy block (both written by apply_autoplay.py):
                         one policies object carries autoplay and / or GPC.
  OmniBrowserSettings.h  the omniApSettingsInput declaration, the omniApSettingsRow call, the omniApRowId input line
                         (all apply_autoplay.py's).
  OmniQuickMenu.h        the omniApSiteInput declaration, the omniApSiteRow call, the omniApSiteRowId input line
                         (all apply_autoplay.py's).
  OmniFeatures3.h        the OmniAutoplayShell.h include line.
Apply AFTER apply_autoplay.py (its lines are anchors).
Upgrading (r2: no port exemption, private-only session allowances, Cross = Go back): only the two headers
changed; they are rewritten whenever they differ, so an r1 tree gets them and the result is byte-identical to a
fresh apply (the EDITS, and so the anchors apply_media_controls.py / apply_pinned_tabs.py use, are unchanged).
usage: apply_https_only.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_HTTPS_ONLY_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_HTTPS_ONLY_V1: the pure part of HTTPS-only mode and the Global Privacy Control switch (no SDL, no WebKit).
// The shell side is OmniHttpsOnlyShell.h; the reasons are in tools/apply_https_only.py. Tested on the host with g++
// (test_https_only.cpp).
// OMNI_HTTPS_ONLY_V1_R2: no port exemption; Session keeps private-tab allowances apart (Nav::privateTab).
#pragma once
#include <cstddef>
#include <cstdint>
#include <map>
#include <set>
#include <string>

namespace OmniHttpsOnly {

constexpr size_t kMaxAllow = 500, kHostMax = 253;
constexpr long kMaxFileBytes = 64L << 10;
constexpr const char* kFileName = "https-only.txt";
constexpr const char* kHeader = "omni-https-only\t1";
constexpr const char* kErrorDomain = "OmniHttpsOnly";   // OmniFxTabState::failDomain while the panel is shown
constexpr uint32_t kInFlightMs = 60000;                 // an https attempt older than this is forgotten
constexpr int kRedirectedBack = -1;                     // failCode: the site sent Omni back to http

struct Store { bool httpsOnly = false; bool gpc = false; std::set<std::string> allow; };
struct Session {                                        // this run only (never written)
    std::set<std::string> cont;                         // "Continue" pressed in a normal tab: http in every tab
    std::map<std::string, bool> priv;                   // private tabs only: their site choices and "Continue"
    void clear() { cont.clear(); priv.clear(); }
};

inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }
inline bool startsWithNoCase(const std::string& s, const char* p)
{
    size_t i = 0;
    for (; p[i]; ++i) if (i >= s.size() || lower(s[i]) != p[i]) return false;
    return true;
}

// --- URLs --------------------------------------------------------------------------------------------------------
inline bool parseIPv6(const std::string& s, uint8_t out[16]);
struct Url {
    bool ok = false, http = false;   // http: "http://" (else "https://")
    std::string host;                // lower case, no brackets for IPv6, no trailing dot
    int port = -1;                   // -1: none written
    size_t schemeEnd = 0, hostEnd = 0, authEnd = 0;   // offsets into the original string
};
inline Url parseUrl(const std::string& url)
{
    Url u;
    if (startsWithNoCase(url, "http://")) { u.http = true; u.schemeEnd = 7; }
    else if (startsWithNoCase(url, "https://")) u.schemeEnd = 8;
    else return u;
    size_t end = url.find_first_of("/?#", u.schemeEnd);
    if (end == std::string::npos) end = url.size();
    u.authEnd = end;
    size_t start = u.schemeEnd;
    const size_t at = url.rfind('@', end == 0 ? 0 : end - 1);
    if (at != std::string::npos && at >= start && at < end) start = at + 1;
    std::string host;
    size_t after;
    if (start < end && url[start] == '[') {
        const size_t close = url.find(']', start);
        if (close == std::string::npos || close >= end) return u;
        host = url.substr(start + 1, close - start - 1);
        uint8_t v6[16];
        if (!parseIPv6(host, v6)) return u;
        after = close + 1;
    } else {
        after = url.find(':', start);
        if (after == std::string::npos || after > end) after = end;
        host = url.substr(start, after - start);
    }
    u.hostEnd = after;
    if (after < end) {
        if (url[after] != ':') return u;
        const std::string p = url.substr(after + 1, end - after - 1);
        if (!p.empty()) {
            if (p.size() > 5) return u;
            int v = 0;
            for (char c : p) { if (c < '0' || c > '9') return u; v = v * 10 + (c - '0'); }
            if (v > 65535) return u;
            u.port = v;
        }
    }
    for (auto& c : host) c = lower(c);
    while (!host.empty() && host.back() == '.') host.pop_back();
    if (host.empty() || host.size() > kHostMax) return u;
    for (char c : host)
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-' || c == '_' || c == ':'))
            return u;
    u.host = host;
    u.ok = true;
    return u;
}
// Allow-list key: lower case, "www." dropped (www.example.com and example.com share a choice), IPv6 unbracketed.
inline std::string hostKey(const std::string& host)
{
    std::string h;
    for (char c : host) h += lower(c);
    if (h.size() > 2 && h.front() == '[' && h.back() == ']') h = h.substr(1, h.size() - 2);
    while (!h.empty() && h.back() == '.') h.pop_back();
    if (h.compare(0, 4, "www.") == 0 && h.size() > 4) h = h.substr(4);
    return h;
}
inline std::string urlHostKey(const std::string& url)
{
    const Url u = parseUrl(url);
    return u.ok ? hostKey(u.host) : std::string();
}

// --- addresses ---------------------------------------------------------------------------------------------------
// Strict dotted quad ("10.0.0.1"); WebKit has already canonicalised other spellings before the policy callback.
inline bool parseIPv4(const std::string& s, uint32_t& out)
{
    uint32_t v = 0;
    int parts = 0;
    size_t i = 0;
    while (true) {
        if (i >= s.size() || s[i] < '0' || s[i] > '9') return false;
        uint32_t part = 0;
        size_t digits = 0;
        while (i < s.size() && s[i] >= '0' && s[i] <= '9') {
            part = part * 10 + uint32_t(s[i] - '0');
            if (++digits > 3 || part > 255) return false;
            ++i;
        }
        v = (v << 8) | part;
        if (++parts == 4) break;
        if (i >= s.size() || s[i] != '.') return false;
        ++i;
    }
    if (i != s.size()) return false;
    out = v;
    return true;
}
// RFC 4291 text form, "::" compression and a dotted-quad tail; no zone ids.
inline bool parseIPv6(const std::string& s, uint8_t out[16])
{
    uint16_t words[8] = {};
    int n = 0, gap = -1;
    size_t i = 0;
    if (s.size() < 2) return false;
    if (s[0] == ':') { if (s[1] != ':') return false; gap = 0; i = 2; if (i == s.size()) goto done; }
    while (i < s.size()) {
        if (n >= 8) return false;
        size_t j = i;
        uint32_t w = 0;
        while (j < s.size() && j - i < 5) {
            const char c = lower(s[j]);
            int d = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
            if (d < 0) break;
            w = w * 16 + uint32_t(d);
            ++j;
        }
        if (j < s.size() && s[j] == '.') {           // IPv4 tail
            uint32_t v4;
            if (n > 6 || !parseIPv4(s.substr(i), v4)) return false;
            words[n++] = uint16_t(v4 >> 16);
            words[n++] = uint16_t(v4 & 0xffff);
            i = s.size();
            break;
        }
        if (j == i || j - i > 4) return false;
        words[n++] = uint16_t(w);
        i = j;
        if (i == s.size()) break;
        if (s[i] != ':') return false;
        ++i;
        if (i < s.size() && s[i] == ':') {
            if (gap >= 0) return false;
            gap = n;
            ++i;
            if (i == s.size()) break;
        } else if (i == s.size()) return false;   // trailing single ':'
    }
done:
    if (gap < 0 && n != 8) return false;
    if (gap >= 0 && n > 7) return false;
    uint16_t full[8] = {};
    if (gap < 0) for (int k = 0; k < 8; ++k) full[k] = words[k];
    else {
        for (int k = 0; k < gap; ++k) full[k] = words[k];
        const int tail = n - gap;
        for (int k = 0; k < tail; ++k) full[8 - tail + k] = words[gap + k];
    }
    for (int k = 0; k < 8; ++k) { out[2 * k] = uint8_t(full[k] >> 8); out[2 * k + 1] = uint8_t(full[k] & 0xff); }
    return true;
}
inline bool privateIPv4(uint32_t a)
{
    return (a >> 24) == 127 || (a >> 24) == 10 || (a >> 20) == ((172u << 4) | 1u) || (a >> 16) == ((192u << 8) | 168u)
        || (a >> 16) == ((169u << 8) | 254u) || a == 0;
}
inline bool endsWith(const std::string& s, const char* suffix)
{
    const std::string x(suffix);
    return s.size() >= x.size() && s.compare(s.size() - x.size(), x.size(), x) == 0;
}
// Loopback, private LAN, link-local, *.localhost, *.local (mDNS).
inline bool privateHost(const std::string& hostIn)
{
    std::string host = hostIn;
    if (host.size() > 2 && host.front() == '[' && host.back() == ']') host = host.substr(1, host.size() - 2);
    if (host == "localhost" || endsWith(host, ".localhost") || endsWith(host, ".local")) return true;
    uint32_t v4;
    if (parseIPv4(host, v4)) return privateIPv4(v4);
    uint8_t b[16];
    if (host.find(':') != std::string::npos && parseIPv6(host, b)) {
        bool zeroTo10 = true;
        for (int k = 0; k < 10; ++k) if (b[k]) zeroTo10 = false;
        if (zeroTo10 && b[10] == 0xff && b[11] == 0xff)                    // ::ffff:a.b.c.d
            return privateIPv4(uint32_t(b[12]) << 24 | uint32_t(b[13]) << 16 | uint32_t(b[14]) << 8 | b[15]);
        bool zeroTo15 = zeroTo10 && !b[10] && !b[11] && !b[12] && !b[13] && !b[14];
        if (zeroTo15 && (b[15] == 1 || b[15] == 0)) return true;           // ::1, ::
        if ((b[0] & 0xfe) == 0xfc) return true;                            // fc00::/7
        if (b[0] == 0xfe && (b[1] & 0xc0) == 0x80) return true;            // fe80::/10
    }
    return false;
}
// True: never upgraded (not http at all, or a local / private-network host: Omni's own apps live there).
inline bool exempt(const Url& u)
{
    if (!u.ok || !u.http) return true;
    return privateHost(u.host);
}
// "http://h:80/p?q#f" -> "https://h/p?q#f"; any other port is kept.
inline std::string upgradeUrl(const std::string& url)
{
    const Url u = parseUrl(url);
    if (!u.ok || !u.http) return std::string();
    std::string out = "https://" + url.substr(u.schemeEnd, u.hostEnd - u.schemeEnd);
    if (u.port != 80) out += url.substr(u.hostEnd, u.authEnd - u.hostEnd);
    return out + url.substr(u.authEnd);
}

// --- allow list --------------------------------------------------------------------------------------------------
// http allowed for `host` in a tab of this kind. A normal tab never reads session.priv (no private visit leaks).
inline bool allowed(const Store& s, const Session& session, const std::string& host, bool privateTab)
{
    const std::string key = hostKey(host);
    if (key.empty()) return false;
    if (privateTab) {
        auto it = session.priv.find(key);
        if (it != session.priv.end()) return it->second;
    }
    return session.cont.count(key) != 0 || s.allow.count(key) != 0;
}
// Site settings choice. privateTab: only session.priv changes (a row exists only while it differs from what applies
// without it). Normal tab: the saved choice (a "Continue" for the host is dropped). False: a new saved host when 500
// exist.
inline bool setSite(Store& s, Session& session, const std::string& host, bool allow, bool privateTab)
{
    const std::string key = hostKey(host);
    if (key.empty()) return false;
    if (privateTab) {
        if (allow == (session.cont.count(key) != 0 || s.allow.count(key) != 0)) session.priv.erase(key);
        else session.priv[key] = allow;
        return true;
    }
    if (allow && !s.allow.count(key) && s.allow.size() >= kMaxAllow) return false;
    session.cont.erase(key);
    if (allow) s.allow.insert(key); else s.allow.erase(key);
    return true;
}
// "Continue to the http site": this run only. From a normal tab: every tab. From a private tab: private tabs only.
inline void allowForSession(Session& session, const std::string& host, bool privateTab)
{
    const std::string key = hostKey(host);
    if (key.empty()) return;
    if (privateTab) session.priv[key] = true;
    else session.cont.insert(key);
}

// --- the decision ------------------------------------------------------------------------------------------------
enum Action { kLoad = 0, kUpgrade, kInterstitial };
struct Nav {
    std::string url;
    bool get = true;                 // GET (or unknown); a POST to http keeps its body by loading as before
    bool historyOrReload = false;    // Back / Forward / Reload of an entry already in the history
    std::string inFlightHost;        // host key of this tab's https attempt still in flight ("" none)
    bool privateTab = false;         // the navigating tab is private (session.priv applies)
};
inline Action decide(const Store& s, const Session& session, const Nav& n, std::string* httpsOut = nullptr)
{
    if (!s.httpsOnly) return kLoad;
    const Url u = parseUrl(n.url);
    if (exempt(u)) return kLoad;
    if (allowed(s, session, u.host, n.privateTab)) return kLoad;
    if (!n.inFlightHost.empty() && hostKey(u.host) == n.inFlightHost) return kInterstitial;   // https -> http loop
    if (!n.get || n.historyOrReload) return kLoad;
    if (httpsOut) *httpsOut = upgradeUrl(n.url);
    return kUpgrade;
}
// The https attempt failed in a way http might not: show the panel (else: the normal error panel).
inline bool fallbackError(const std::string& domain, int code)
{
    if (domain != "CurlErrorDomain") return false;
    switch (code) {
    case 7:   // couldn't connect (refused)
    case 16:  // HTTP/2 framing
    case 28:  // timed out
    case 35:  // TLS connect error
    case 51: case 53: case 54: case 58: case 59: case 60: case 77: case 80: case 83: case 90: case 91:   // TLS / certificates
    case 52: case 55: case 56:   // empty reply / send / receive failure (closed on the TLS hello)
    case 92:  // HTTP/2 stream
        return true;
    default:
        return false;
    }
}

// --- file --------------------------------------------------------------------------------------------------------
inline std::string serialize(const Store& s)
{
    std::string out = std::string(kHeader) + "\n";
    out += std::string("https_only\t") + (s.httpsOnly ? "1" : "0") + "\n";
    out += std::string("gpc\t") + (s.gpc ? "1" : "0") + "\n";
    size_t n = 0;
    for (const auto& h : s.allow) {
        if (h.empty() || n >= kMaxAllow) continue;
        out += "allow\t" + h + "\n";
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
        const size_t t = line.find('\t');
        if (t == std::string::npos) continue;
        const std::string kind = line.substr(0, t), value = line.substr(t + 1);
        if (kind == "https_only") s.httpsOnly = value == "1";
        else if (kind == "gpc") s.gpc = value == "1";
        else if (kind == "allow") {
            const bool v6 = value.find(':') != std::string::npos;
            const Url u = parseUrl("http://" + (v6 ? "[" + value + "]" : value) + "/");
            if (!u.ok || u.port != -1) continue;
            const std::string key = hostKey(u.host);
            if (key.empty() || (!s.allow.count(key) && s.allow.size() >= kMaxAllow)) continue;
            s.allow.insert(key);
        }
    }
    return s;
}

// --- texts -------------------------------------------------------------------------------------------------------
inline const char* onOff(bool on) { return on ? "On" : "Off"; }
inline std::string httpsOnlyDetail(bool on)
{
    return on ? "Sites open over https; Omni asks before using an insecure http site"
              : "http sites open as they are (not encrypted)";
}
inline std::string gpcDetail(bool on)
{
    return on ? "Sends the Global Privacy Control signal (Sec-GPC) to secure sites"
              : "Sites are not sent the Global Privacy Control signal";
}
inline std::string httpsOnlyNotice(bool on)
{
    return std::string("HTTPS-only mode: ") + onOff(on) + ". Applies to pages you open from now on";
}
inline std::string gpcNotice(bool on)
{
    return std::string("Ask sites not to sell or share my data: ") + onOff(on) + ". Applies to pages you open from now on";
}
inline const char* interstitialTitle() { return "This site doesn't support a secure connection"; }
inline std::string reason(int code)
{
    switch (code) {
    case kRedirectedBack: return "it sent Omni back to the insecure address";
    case 7: return "it refused the secure connection";
    case 28: return "the secure connection timed out";
    case 60: case 51: case 77: case 83: case 90: case 91: return "its security certificate isn't valid";
    default: return "the secure connection failed";
    }
}
inline std::string interstitialBody(const std::string& host, int code)
{
    return "HTTPS-only mode is on. Omni tried https://" + host + " but " + reason(code)
        + ". On the http site, others on the network can see and change what you view and send.";
}
// The site row: what applies to `host` now.
inline std::string siteValue(const Store& s, const Session& session, const std::string& host, bool privateTab)
{
    const Url u = parseUrl("http://" + (host.find(':') != std::string::npos ? "[" + host + "]" : host) + "/");
    if (u.ok && privateHost(u.host)) return "Not needed (local)";
    const std::string key = hostKey(host);
    const bool savedAllow = s.allow.count(key) != 0, cont = session.cont.count(key) != 0;
    if (privateTab) {
        auto it = session.priv.find(key);
        if (it != session.priv.end() && it->second != (savedAllow || cont))
            return it->second ? "Allow http (this session)" : "Upgrade to https (this session)";
    }
    if (cont && !savedAllow) return "Allow http (this session)";
    return savedAllow ? "Allow http" : "Upgrade to https";
}
inline std::string siteNotice(const std::string& host, bool allow, bool privateTab, bool full, bool httpsOnlyOn)
{
    if (full) return "Too many sites allowed to use http (500). Remove one first";
    std::string out = "HTTPS-only on " + host + ": " + (allow ? "Allow http" : "Upgrade to https");
    if (privateTab) out += " (this session only)";
    if (!httpsOnlyOn) out += ". HTTPS-only mode is off in Browser settings";
    return out;
}
inline std::string continueNotice(const std::string& host, bool privateTab)
{
    if (privateTab) return "Using http for " + host + " in private tabs until Omni closes";
    return "Using http for " + host + " until Omni closes. Site settings can allow it always";
}
// The panel's chips, in order: the safe choice first (Cross, highlighted), then the insecure one (Square).
inline const char* goBackLabel() { return "Go back"; }
inline const char* continueLabel() { return "Continue to the http site"; }

} // namespace OmniHttpsOnly
'''

SHELL = r'''// OMNI_HTTPS_ONLY_V1: HTTPS-only mode + Global Privacy Control (shell side). Included from OmniFeatures3.h (inside
// OmniBrowser.cpp's anonymous namespace, after OmniAutoplayShell.h). The pure part is OmniHttpsOnly.h; the reasons
// are in tools/apply_https_only.py. Everything runs on the main thread; the file is written by omniIoQueue.
#pragma once

namespace OHO = OmniHttpsOnly;
static OHO::Store omniHoStore;
static bool omniHoLoaded = false;
static OHO::Session omniHoSession;   // this run only: normal-tab "Continue" (cont), private-tab choices (priv)

static void omniHoLoad()
{
    if (omniHoLoaded) return;
    omniHoLoaded = true;
    FILE* f = fopen(omniData(OHO::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) < OHO::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    omniHoStore = OHO::parse(text);
}
static void omniHoWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OHO::kFileName), OHO::serialize(omniHoStore), false);
}
static bool omniHoGpcOn() { omniHoLoad(); return omniHoStore.gpc; }   // read by omniApUse (OmniAutoplayShell.h)

static void omniHoForget(OmniFxTabState& s) { s.hoHttpURL.clear(); s.hoHttpsURL.clear(); s.hoHost.clear(); s.hoAt = 0; }
static void omniHoShow(Tab& tab, const std::string& httpURL, int code)
{
    OmniFxTabState& s = omniFxState(&tab);
    omniHoForget(s);
    s.failURL = httpURL;
    s.failDomain = OHO::kErrorDomain;
    s.failCode = code;
    s.crashDismissed = false;
    tab.loading = false;
    tab.url = httpURL;
    tab.title = "Not secure";
    tab.message = OHO::interstitialBody(OHO::urlHostKey(httpURL), code);
    omniShellDirty = true;
    fprintf(stderr, "OMNI HTTPS: no secure connection for %s (code %d)\n", httpURL.c_str(), code); fflush(stderr);
}

// omniEverydayNavigation's action callback, main frame, right after the target URL is read. True: answered.
static bool omniHoPolicy(Tab* tab, WKNavigationActionRef action, WKURLRequestRef request, const std::string& url, WKFramePolicyListenerRef listener)
{
    if (!tab || url.rfind("http://", 0) != 0) return false;   // WebKit hands canonical (lower-case) schemes
    omniHoLoad();
    if (!omniHoStore.httpsOnly) return false;
    OmniFxTabState& s = omniFxState(tab);
    OHO::Nav n;
    n.url = url;
    const std::string method = request ? OmniTest::toStd(adoptWK(WKURLRequestCopyHTTPMethod(request)).get()) : std::string();
    n.get = method.empty() || method == "GET";
    const WKFrameNavigationType type = WKNavigationActionGetNavigationType(action);
    n.historyOrReload = type == kWKFrameNavigationTypeBackForward || type == kWKFrameNavigationTypeReload;
    if (s.hoAt && SDL_GetTicks() - s.hoAt < OHO::kInFlightMs) n.inFlightHost = s.hoHost;
    n.privateTab = tab->omniPrivate;   // OMNI_HTTPS_ONLY_V1_R2: private allowances stay in private tabs
    std::string https;
    switch (OHO::decide(omniHoStore, omniHoSession, n, &https)) {
    case OHO::kUpgrade:
        if (https.empty()) return false;
        WKFramePolicyListenerIgnore(listener);
        s.hoHttpURL = url;
        s.hoHttpsURL = https;
        s.hoHost = OHO::urlHostKey(url);
        s.hoAt = SDL_GetTicks();
        if (!s.hoAt) s.hoAt = 1;
        tab->url = https;
        tab->loading = true;
        tab->omniPendingLoad = https;   // loaded by omniEverydayTick (as the user-agent switch does)
        fprintf(stderr, "OMNI HTTPS: upgrade %s -> %s\n", url.c_str(), https.c_str()); fflush(stderr);
        return true;
    case OHO::kInterstitial:
        WKFramePolicyListenerIgnore(listener);
        omniHoShow(*tab, url, OHO::kRedirectedBack);
        return true;
    default:
        return false;
    }
}
// failed() (provisional load failure and failure after commit), before anything else. True: the panel is shown.
static bool omniHoLoadFailed(Tab& tab, WKErrorRef error, const std::string& domain, int code)
{
    OmniFxTabState& s = omniFxState(&tab);
    if (!s.hoAt || s.hoHttpsURL.empty()) return false;
    std::string failing;
    if (auto url = adoptWK(WKErrorCopyFailingURL(error))) failing = OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get());
    const OHO::Url f = OHO::parseUrl(failing);
    const bool ours = failing.empty() || (f.ok && !f.http && OHO::hostKey(f.host) == s.hoHost);
    const std::string http = s.hoHttpURL;
    omniHoForget(s);   // any failure (a cancel too) ends the attempt
    if (!ours || !OHO::fallbackError(domain, code)) return false;
    omniSavedDocumentChanged(tab);
    omniHoShow(tab, http, code);
    return true;
}
// didCommitNavigation: the attempt (if any) worked.
static void omniHoCommitted(Tab& tab) { omniHoForget(omniFxState(&tab)); }

// --- the panel (inside the OMNI_FEATURES_V1 error panel) ---------------------------------------------------------
static bool omniHoErrorShown()
{
    Tab* t = active();
    return t && !t->crashed && omniFxErrorShown() && omniFxState(t).failDomain == OHO::kErrorDomain;
}
// Chip 0: Cross "Go back" (the safe default, highlighted). Chip 1: Square "Continue to the http site".
static OmniFxErrorLayout omniHoErrorGeom()
{
    OmniFxErrorLayout L = omniFxErrorGeom();
    L.chips = 2;
    L.chipX[0] = L.x + 40; L.chipW[0] = 180;
    L.chipX[1] = L.chipX[0] + L.chipW[0] + 14; L.chipW[1] = 330;
    return L;
}
static bool omniHoErrorDraw()
{
    if (!omniHoErrorShown()) return false;
    Tab* t = active();
    const OmniTheme& T = omniTheme();
    const OmniFxTabState& s = omniFxState(t);
    const int py0 = physical(omniPageTop()), py1 = physical(omniPageBottom());
    omniRectPx({ 0, py0, canvas->w, std::max(0, py1 - py0) }, T.bg, 200);
    const OmniFxErrorLayout L = omniHoErrorGeom();
    omniShadow(L.x, L.y, L.w, L.h, omniRadius + 2, 22, 160, 6);
    fillRounded(L.x, L.y, L.w, L.h, omniRadius + 2, T.panel);
    omniDisc(L.x + 50, L.y + 50, 20, omniWarn);
    omniIcon(omniIconAlert, L.x + 50, L.y + 50, T.bg);
    omniLabel(OHO::interstitialTitle(), L.x + 88, L.y + 42, omniBodyBold, T.ink, 0, L.w - 120);
    omniLabel(omniShownURL(s.failURL), L.x + 88, L.y + 70, omniSmall, T.inkDim, 0, L.w - 120);
    const auto lines = omniWrap(t->message, omniSmall, L.w - 128, 3);
    for (size_t i = 0; i < lines.size(); ++i) omniLabel(lines[i], L.x + 88, L.y + 108 + int(i) * 26, omniSmall, T.ink);
    const char* labels[2] = { OHO::goBackLabel(), OHO::continueLabel() };
    const int faces[2] = { SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_X };   // Cross, Square
    for (int i = 0; i < 2; ++i) {
        const bool primary = i == 0;   // Cross: the safe choice, highlighted as the default
        const bool hover = pointerX >= L.chipX[i] && pointerX < L.chipX[i] + L.chipW[i] && pointerY >= L.chipY && pointerY < L.chipY + 44;
        fillRounded(L.chipX[i], L.chipY, L.chipW[i], 44, omniRadius, primary ? T.accent : hover ? T.hover : T.key);
        faceIcon(L.chipX[i] + 26, L.chipY + 22, faces[i], playStationIcons);
        omniLabel(labels[i], L.chipX[i] + 48, L.chipY + 22, omniSmallBold, primary ? T.accentInk : T.ink, 0, L.chipW[i] - 56);
    }
    return true;
}
static void omniHoContinue()
{
    Tab* t = active();
    if (!t) return;
    OmniFxTabState& s = omniFxState(t);
    const std::string url = s.failURL;
    const std::string host = OHO::urlHostKey(url);
    s.failDomain.clear();
    t->message.clear();
    if (host.empty()) { omniFxErrorDismiss(); return; }
    omniHoLoad();
    OHO::allowForSession(omniHoSession, host, t->omniPrivate);   // private tab: private tabs only (r2)
    notice(OHO::continueNotice(host, t->omniPrivate));
    navigate(url);
}
static void omniHoGoBack()
{
    Tab* t = active();
    if (!t) return;
    omniFxState(t).failDomain.clear();
    omniFxErrorDismiss();   // nothing was loaded: the previous page is still there
}
static bool omniHoErrorButton(int b)
{
    switch (b) {
    case SDL_CONTROLLER_BUTTON_A: omniHoGoBack(); return true;     // Cross: the safe default
    case SDL_CONTROLLER_BUTTON_B: omniHoGoBack(); return true;
    case SDL_CONTROLLER_BUTTON_X: omniHoContinue(); return true;   // Square: the insecure http site, deliberately
    default: return false;   // Y address, L1/R1 tabs, Options menu keep working
    }
}
static bool omniHoErrorClick(int x, int y)
{
    const OmniFxErrorLayout L = omniHoErrorGeom();
    if (y >= L.chipY && y < L.chipY + 44) {
        if (x >= L.chipX[0] && x < L.chipX[0] + L.chipW[0]) { omniHoGoBack(); return true; }
        if (x >= L.chipX[1] && x < L.chipX[1] + L.chipW[1]) { omniHoContinue(); return true; }
    }
    return y >= omniPageTop() && y < omniPageBottom();
}

// --- Browser settings ----------------------------------------------------------------------------------------------
static void omniHoSettingsRows(OmniFxPanel& p)
{
    omniHoLoad();
    OmniFxRow r; r.id = omniHoRowId; r.label = "HTTPS-only mode"; r.value = OHO::onOff(omniHoStore.httpsOnly); r.stepper = true;
    r.detail = OHO::httpsOnlyDetail(omniHoStore.httpsOnly);
    p.rows.push_back(r);
    OmniFxRow g; g.id = omniHoGpcRowId; g.label = "Ask sites not to sell or share my data"; g.value = OHO::onOff(omniHoStore.gpc); g.stepper = true;
    g.detail = OHO::gpcDetail(omniHoStore.gpc);
    p.rows.push_back(g);
}
static bool omniHoSettingsInput(int id, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    omniHoLoad();
    if (id == omniHoGpcRowId) {
        omniHoStore.gpc = !omniHoStore.gpc;
        notice(OHO::gpcNotice(omniHoStore.gpc));
    } else {
        omniHoStore.httpsOnly = !omniHoStore.httpsOnly;
        notice(OHO::httpsOnlyNotice(omniHoStore.httpsOnly));
    }
    omniHoWrite();
    return true;
}

// --- Site settings > HTTPS-only on this site -----------------------------------------------------------------------
static std::string omniHoSiteHost()
{
    Tab* t = active();
    if (!t) return std::string();
    const std::string url = omniHoErrorShown() ? omniFxState(t).failURL : t->url;
    return OHO::urlHostKey(url);
}
static void omniHoSiteRow(OmniFxPanel& p, const std::string&)
{
    omniHoLoad();
    const std::string host = omniHoSiteHost();
    OmniFxRow r; r.id = omniHoSiteRowId; r.label = "HTTPS-only on this site"; r.stepper = true; r.enabled = !host.empty();
    r.value = host.empty() ? std::string("-") : OHO::siteValue(omniHoStore, omniHoSession, host, active() && active()->omniPrivate);
    if (!host.empty() && r.value.rfind("Not needed", 0) == 0) r.enabled = false;
    p.rows.push_back(r);
}
static bool omniHoSiteInput(const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    const std::string host = omniHoSiteHost();
    Tab* t = active();
    if (!r.enabled || host.empty() || !t) return true;
    omniHoLoad();
    const bool priv = t->omniPrivate;
    const bool allow = !OHO::allowed(omniHoStore, omniHoSession, host, priv);
    const bool ok = OHO::setSite(omniHoStore, omniHoSession, host, allow, priv);
    if (ok && !priv) omniHoWrite();
    notice(OHO::siteNotice(host, allow, priv, !ok, omniHoStore.httpsOnly));
    if (!ok) return true;
    if (allow && omniHoErrorShown()) {   // on the panel: open the http site now
        const std::string url = omniFxState(t).failURL;
        omniFxState(t).failDomain.clear();
        t->message.clear();
        navigate(url);
    } else if (!allow && omniHoStore.httpsOnly && t->url.rfind("http://", 0) == 0) {
        navigate(t->url);   // a new load (not Reload) so it is upgraded
    }
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniAutoplay.h" // OMNI_AUTOPLAY_V1: autoplay choice per site, autoplay.txt (pure)\n',
         '#include "OmniAutoplay.h" // OMNI_AUTOPLAY_V1: autoplay choice per site, autoplay.txt (pure)\n'
         '#include "OmniHttpsOnly.h" // OMNI_HTTPS_ONLY_V1: HTTPS-only mode + GPC, https-only.txt (pure)\n'),
        ('void failed(WKPageRef, WKNavigationRef, WKErrorRef error, WKTypeRef, const void* info)\n{\n',
         'static bool omniHoLoadFailed(Tab& tab, WKErrorRef error, const std::string& domain, int code); // OMNI_HTTPS_ONLY_V1 (OmniHttpsOnlyShell.h)\n'
         'void failed(WKPageRef, WKNavigationRef, WKErrorRef error, WKTypeRef, const void* info)\n{\n'),
        ('    int code = WKErrorGetErrorCode(error);\n'
         '    if (domain == "OmniUBlockRedirect" && ',
         '    int code = WKErrorGetErrorCode(error);\n'
         '    if (omniHoLoadFailed(tab, error, domain, code)) return; // OMNI_HTTPS_ONLY_V1: the https attempt failed: "doesn\'t support a secure connection"\n'
         '    if (domain == "OmniUBlockRedirect" && '),
        ('static void omniApUse(WKNavigationActionRef action, WKFramePolicyListenerRef listener); // OMNI_AUTOPLAY_V1 (OmniAutoplayShell.h)\n',
         'static void omniApUse(WKNavigationActionRef action, WKFramePolicyListenerRef listener); // OMNI_AUTOPLAY_V1 (OmniAutoplayShell.h)\n'
         'static bool omniHoPolicy(Tab* tab, WKNavigationActionRef action, WKURLRequestRef request, const std::string& url, WKFramePolicyListenerRef listener); // OMNI_HTTPS_ONLY_V1 (OmniHttpsOnlyShell.h)\n'
         'static void omniHoCommitted(Tab& tab); // OMNI_HTTPS_ONLY_V1\n'),
        ('            const std::string targetURL = url ? OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get()) : std::string();\n'
         '            // OMNI_YOUTUBE_TV_V1: TV mode opens',
         '            const std::string targetURL = url ? OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get()) : std::string();\n'
         '            if (omniHoPolicy(tab, action, request.get(), targetURL, listener)) return; // OMNI_HTTPS_ONLY_V1: http -> https, or the panel\n'
         '            // OMNI_YOUTUBE_TV_V1: TV mode opens'),
        ('        omniApplySiteZoom(tab);\n    };\n}\n',
         '        omniHoCommitted(*tab); // OMNI_HTTPS_ONLY_V1: the https attempt (if any) worked\n'
         '        omniApplySiteZoom(tab);\n    };\n}\n'),
    ],
    'OmniErrorPage.h': [
        ('    std::string saveURL;   // the next main-frame load of this URL becomes a download (Save link / image)\n',
         '    std::string saveURL;   // the next main-frame load of this URL becomes a download (Save link / image)\n'
         '    std::string hoHttpURL, hoHttpsURL, hoHost;   // OMNI_HTTPS_ONLY_V1: the https attempt in flight\n'
         '    uint32_t hoAt = 0;                           // OMNI_HTTPS_ONLY_V1: when it started (0: none)\n'),
        ('static void omniFxErrorDraw()\n{\n',
         'static bool omniHoErrorShown(); // OMNI_HTTPS_ONLY_V1 (OmniHttpsOnlyShell.h): the "no secure connection" panel\n'
         'static bool omniHoErrorDraw();\n'
         'static bool omniHoErrorButton(int b);\n'
         'static bool omniHoErrorClick(int x, int y);\n'
         'static void omniFxErrorDraw()\n{\n'
         '    if (omniHoErrorDraw()) return; // OMNI_HTTPS_ONLY_V1\n'),
        ('static bool omniFxErrorButton(int b)\n{\n',
         'static bool omniFxErrorButton(int b)\n{\n'
         '    if (omniHoErrorShown()) return omniHoErrorButton(b); // OMNI_HTTPS_ONLY_V1: Continue / Go back\n'),
        ('static bool omniFxErrorClick(int x, int y)\n{\n',
         'static bool omniFxErrorClick(int x, int y)\n{\n'
         '    if (omniHoErrorShown()) return omniHoErrorClick(x, y); // OMNI_HTTPS_ONLY_V1\n'),
    ],
    'OmniAutoplayShell.h': [
        ("// The last step of omniEverydayNavigation's action callback (was a plain WKFramePolicyListenerUse).\n",
         'static bool omniHoGpcOn(); // OMNI_HTTPS_ONLY_V1 (OmniHttpsOnlyShell.h): Global Privacy Control setting\n'
         "// The last step of omniEverydayNavigation's action callback (was a plain WKFramePolicyListenerUse).\n"),
        ('        if (OAP::needsPolicy(d)) {\n'
         '            auto policies = adoptWK(WKWebsitePoliciesCreate());\n'
         '            WKWebsitePoliciesSetAutoplayPolicy(policies.get(), omniApWk(d.mode));\n',
         '        const bool gpc = omniHoGpcOn(); // OMNI_HTTPS_ONLY_V1: the same policies object carries GPC\n'
         '        if (OAP::needsPolicy(d) || gpc) {\n'
         '            auto policies = adoptWK(WKWebsitePoliciesCreate());\n'
         '            if (OAP::needsPolicy(d)) WKWebsitePoliciesSetAutoplayPolicy(policies.get(), omniApWk(d.mode));\n'
         '            if (gpc) WKWebsitePoliciesSetGlobalPrivacyControlEnabled(policies.get(), true); // OMNI_HTTPS_ONLY_V1: Sec-GPC + navigator.globalPrivacyControl\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static bool omniApSettingsInput(int b);\n',
         'static bool omniApSettingsInput(int b);\n'
         'constexpr int omniHoRowId = 890, omniHoGpcRowId = 891; // OMNI_HTTPS_ONLY_V1 (OmniHttpsOnlyShell.h)\n'
         'static void omniHoSettingsRows(OmniFxPanel& p);\n'
         'static bool omniHoSettingsInput(int id, int b);\n'),
        ('    omniApSettingsRow(p); // OMNI_AUTOPLAY_V1: Allow / Block sound / Block all\n',
         '    omniApSettingsRow(p); // OMNI_AUTOPLAY_V1: Allow / Block sound / Block all\n'
         '    omniHoSettingsRows(p); // OMNI_HTTPS_ONLY_V1: HTTPS-only mode, Ask sites not to sell or share my data\n'),
        ('    if (r.id == omniApRowId) return omniApSettingsInput(b); // OMNI_AUTOPLAY_V1 (before the >= 300 rows)\n',
         '    if (r.id == omniHoRowId || r.id == omniHoGpcRowId) return omniHoSettingsInput(r.id, b); // OMNI_HTTPS_ONLY_V1 (before the >= 300 rows)\n'
         '    if (r.id == omniApRowId) return omniApSettingsInput(b); // OMNI_AUTOPLAY_V1 (before the >= 300 rows)\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniApSiteInput(const OmniFxRow& r, int b);\n',
         'static bool omniApSiteInput(const OmniFxRow& r, int b);\n'
         'constexpr int omniHoSiteRowId = 720; // OMNI_HTTPS_ONLY_V1 (OmniHttpsOnlyShell.h)\n'
         'static void omniHoSiteRow(OmniFxPanel& p, const std::string& host);\n'
         'static bool omniHoSiteInput(const OmniFxRow& r, int b);\n'),
        ('    omniApSiteRow(p, host); // OMNI_AUTOPLAY_V1: Autoplay on this site\n',
         '    omniApSiteRow(p, host); // OMNI_AUTOPLAY_V1: Autoplay on this site\n'
         '    omniHoSiteRow(p, host); // OMNI_HTTPS_ONLY_V1: HTTPS-only on this site\n'),
        ('    if (r.id == omniApSiteRowId) return omniApSiteInput(r, b); // OMNI_AUTOPLAY_V1 (handles its disabled state)\n',
         '    if (r.id == omniHoSiteRowId) return omniHoSiteInput(r, b); // OMNI_HTTPS_ONLY_V1 (handles its disabled state)\n'
         '    if (r.id == omniApSiteRowId) return omniApSiteInput(r, b); // OMNI_AUTOPLAY_V1 (handles its disabled state)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniAutoplayShell.h" // OMNI_AUTOPLAY_V1\n',
         '#include "OmniAutoplayShell.h" // OMNI_AUTOPLAY_V1\n'
         '#include "OmniHttpsOnlyShell.h" // OMNI_HTTPS_ONLY_V1\n'),
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
    if 'OMNI_AUTOPLAY_V1' not in (root / 'OmniFeatures3.h').read_bytes().decode('utf-8'):
        sys.exit('OmniFeatures3.h: OMNI_AUTOPLAY_V1 missing: apply_autoplay.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniHttpsOnly.h', PURE, 'OmniAutoplay.h'),
            write_new('OmniHttpsOnlyShell.h', SHELL, 'OmniAutoplayShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
