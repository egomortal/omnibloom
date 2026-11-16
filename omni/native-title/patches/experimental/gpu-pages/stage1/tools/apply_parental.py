#!/usr/bin/env python3
r"""OMNI_PARENTAL_V1 (2026-11-16): Browser settings > "Parental controls..." for a shared family console.

What the user sees
  - Browser settings > "Parental controls..." (row id 893, after "Keep history"); value Off / Off (PIN set) /
    On: Block these sites / On: Allowed sites only. Opening it needs the PIN once one is set (always, whatever
    "Lock settings" says). The panel:
        Parental controls     On / Off      (the first On asks for a new PIN: 4-6 digits, typed twice)
        Sites                 Block these sites / Allowed sites only
        Blocked sites...      the block list (Add a site..., Add this page's site, Cross on a site removes it)
        Allowed sites...      the allow list (in block-list mode: exceptions)
        Force safe search     Off / On      Google safe=active, Bing adlt=strict, DuckDuckGo kp=1
        Lock private tabs     Off / On      a new private tab needs the PIN
        Lock settings         Off / On      Browser settings and Site settings need the PIN
        Change PIN / Set a PIN
        Forgot the PIN?       explains the reset: delete /data/omni/parental.txt with the PC Setup app
  - PIN entry: Omni's own number pad (an OmniFxPanel 3 x 4 grid: 1-9, Delete, 0, OK; Square deletes, Triangle = OK,
    Circle cancels). Digits are never drawn: the subtitle shows one dot per digit. 5 wrong PINs -> "Too many wrong
    PINs. Try again in 4:59" for 5 minutes; the count and the end time are in parental.txt, so restarting Omni
    doesn't reset them (console clock: a cooldown longer than 5 minutes from now is cut back to 5 minutes).
  - A blocked page: Omni's own panel over the page (the OMNI_FEATURES_V1 error panel, failDomain "OmniParental"):
        "This site is blocked"   address, then "<host> is blocked on this console by parental controls..."
        Cross / Circle  "Go back"             highlighted; nothing was loaded, the previous page stays
        Square          "Allow once (PIN)"    the host (and its subdomains) for an hour, this run of Omni only
        Triangle        "Always allow (PIN)"  adds the host to Allowed sites
    A blocked subframe (iframe) is simply not loaded. A saved web app (OMNI_WEB_APPS_V1 tile) whose site is
    blocked doesn't open ("<host> is blocked by parental controls").

Crypto (reused, nothing new linked): OmniVault.h (OMNI_VAULT_V2, the password vault) already declares and the title
already links OpenSSL 3.5.9 libcrypto: OmniVault::deriveKey = PKCS5_PBKDF2_HMAC(SHA-256), OmniVault::randomBytes =
RAND_bytes, OmniVault::wipe = OPENSSL_cleanse. The PIN is stored as
    pin\tpbkdf2-sha256\t100000\t<16-byte random salt, hex>\t<32-byte derived key, hex>
and compared in constant time; the PIN itself is never written. 100,000 rounds (the vault uses 600,000 to wrap a
key): one check blocks the main thread briefly (logged "OMNI PARENTAL: PIN ok in N ms"). HONEST LIMIT: a 4-6 digit
PIN has at most 10^6 values, so anyone who can read parental.txt can brute-force it offline; such a person can also
just delete the file. These controls are for a family console, not protection against someone with file access.

Enforcement points
  1. omniEverydayNavigation's action callback (OMNI_EVERYDAY_V1): omniParPolicy is its FIRST line (before Save link,
     HTTPS-only, YouTube TV, the UA switch and the final omniApUse(action, listener), none of which is changed).
     WebKit calls it for main-frame and subframe navigations: typed / link / bookmark / session restore / popup
     first loads / Back-Forward / Reload (server redirects too in upstream WebKit: unverified on the console).
     Blocked: WKFramePolicyListenerIgnore (+ the panel for a main frame). Safe search: Ignore + tab->omniPendingLoad
     = rewritten URL (the re-issue path HTTPS-only's upgrade uses), main-frame GET only; the rewrite is idempotent
     (no reload loop). Not installed in the self-test modes (omniEverydayNavigation returns early there).
  2. omniNewPrivateTab (OmniBrowser.cpp), omniFxSettingsShow (OmniBrowserSettings.h), omniFxSiteSettingsShow
     (OmniQuickMenu.h): omniParGate asks for the PIN first when "Lock private tabs" / "Lock settings" is on. Every
     entry point (Quick menu, Circle, Back button, Quick access, context menu, Tabs page) goes through these.
     A correct PIN unlocks until every panel is closed again (omniParTick).
  3. omniWapLaunch (OmniWebAppsShell.h): app tiles to blocked hosts are refused.
Host rules (pure, OmniParental.h): hosts are compared as keys: lower case, trailing dots dropped, userinfo ignored,
percent escapes decoded, backslashes / missing slashes after http: read like WHATWG, tabs / newlines stripped,
IPv4 in any WHATWG form (2130706433, 0x7f.1, 0177.0.0.1) as dotted decimal, IPv6 canonical, IDN labels as punycode
(ASCII lower-casing only), ideographic full stops as dots. An entry covers its subdomains ("www." is dropped from
entries); IP entries match exactly. A web URL whose host can't be read is blocked (fail closed). blob: is judged
by its creator's origin; about:, data:, javascript:, omni:, file: and host-less schemes are not checked (data: is
Omni's new-tab page; data: / javascript: content runs in place and its own navigations are checked separately).
127.0.0.0/8, ::1, localhost are always allowed (Omni's own Downloads / Bloom Core apps); LAN addresses are not.
In block-list mode an entry on Allowed sites is an exception (blocked: google.com, allowed: classroom.google.com).

Safe search: what can and can't be forced
  - Google (google.<tld>, www., images.; /search, and / or /webhp with q=): safe=active (any other safe= value and
    duplicates replaced). Bing (*.bing.com /search, /images/search, /videos/search, /news/search, /shop):
    adlt=strict. DuckDuckGo (duckduckgo.com, html., lite.; /, /html, /lite with q=): kp=1. Top-level navigations
    only: results a page fetches with XHR / pushState (no navigation) are not rewritten.
  - YouTube Restricted Mode: NOT forced. The documented ways are the "YouTube-Restrict: Strict" request header or
    DNS (restrict.youtube.com). This WebKit's C API has no request-header hook for the shell:
    WKWebsitePoliciesSetCustomHeaderFields exists but is an empty stub (UIProcess/API/C/WKWebsitePolicies.cpp), the
    navigation listener can't change the request, and the C API has no cookie setter (WKHTTPCookieStoreRef only
    deletes / sets the accept policy). The PREF=f2=8000000 cookie trick is undocumented, so it is not used. What
    works: add youtube.com to Blocked sites (or use "Allowed sites only").

Storage: /data/omni/parental.txt through omniIoQueue (full rewrite), read once on first use (<= 64 KB):
    omni-parental\t1 / enabled / mode block|allow / safe / lockprivate / locksettings / pin ... / fails / lockuntil /
    block\t<host> / allow\t<host>    (<= 500 each). Another header (or a damaged file) reads as "not set up" (off).
Forgot PIN: the PC Setup app deletes /data/omni/parental.txt; at the next start everything is off. That is the
honest reset for a home console (no account, no recovery code).

Known bypasses / limits (by design or not reachable from the shell)
  - Subresources are not navigations: images, video, fetch/XHR and WebSocket from an allowed page to a blocked host
    still load (a proxy or translate / cache site on an allowed host shows blocked content). Block-list mode is
    weaker than "Allowed sites only" here.
  - Block-list mode: a site reached by its raw IP address or another hostname (mirror, CDN name) is not blocked
    unless listed (no DNS lookups). Most HTTPS sites fail on a raw IP anyway (certificate).
  - Anyone with file access (FTP, PC Setup) can delete parental.txt or brute-force the 4-6 digit PIN offline.
  - The cooldown uses the console clock (time()); setting the clock back can't extend it beyond 5 minutes, setting
    it forward ends it early.
  - Self-test modes have no navigation policy (unchanged from before).

Pure part: engine/entry/OmniParental.h. Tested by tools/test_parental.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_parental.cpp -o t && ./t
    g++ -std=c++20 -Wall -Wextra -DOPAR_TEST_OPENSSL -I<tree>/engine/entry test_parental.cpp -lcrypto -o t && ./t
      (the second also runs the real OmniVault::deriveKey: the PBKDF2-HMAC-SHA256 known vector + a PIN round trip)
Shell side: engine/entry/OmniParentalShell.h (included from OmniFeatures3.h after OmniWebAppsShell.h).

Anchors (exactly once each; MARK makes each file idempotent; each file keeps its own line endings):
  OmniBrowser.cpp        the OmniWebApps.h include line (pure include after it); the omniHoCommitted declaration
                         (apply_https_only.py's; our declarations after it); the omniFxPolicyDownload line, first
                         in omniEverydayNavigation's action callback (our hook before it); the head of
                         omniNewPrivateTab (gate after its brace).
  OmniErrorPage.h        HTTPS-only's three hand-over lines in omniFxErrorDraw / omniFxErrorButton / omniFxErrorClick
                         (ours before each).
  OmniBrowserSettings.h  the omniHkSettingsRow call and the omniHkRowId input line (apply_history_keep.py's; ours
                         after each); the head of omniFxSettingsShow (gate after its brace).
  OmniQuickMenu.h        the head of omniFxSiteSettingsShow (gate after its brace).
  OmniFeatures3.h        the OmniWebAppsShell.h include line; the omniScTick line of omniF3Tick (apply_site_clear.py r2).
  OmniWebAppsShell.h     "const OWAP::App app = list[size_t(i)];" in omniWapLaunch (refusal after it).
Inserted lines use /* */ comments (nothing is appended after a line-prefix anchor). Apply AFTER apply_https_only.py,
apply_site_clear.py, apply_history_keep.py and apply_web_apps.py (their lines are anchors). Refuses when row id 893
is already used in the tree.
usage: apply_parental.py <engine tree>   (re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_PARENTAL_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_PARENTAL_V1: the pure part of Browser settings > "Parental controls..." (no SDL, no WebKit, no OpenSSL).
// The shell side is OmniParentalShell.h; the reasons are in tools/apply_parental.py. Tested on the host with g++
// (test_parental.cpp): URL / host normalisation (userinfo, case, trailing dots, IPv4 / IPv6 literals, IDN -> punycode,
// percent escapes, backslashes), host rules with subdomains, the per-navigation decision, safe-search URL rewrites,
// the wrong-PIN limiter, PIN syntax, the PIN hash record and parental.txt parse / serialize.
// The PIN is never stored: the shell derives PBKDF2-HMAC-SHA256 (OmniVault::deriveKey, OpenSSL) with a random 16-byte
// salt and keeps only salt + hash (Pin below).
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace OmniParental {

constexpr const char* kFileName = "parental.txt";
constexpr const char* kHeader = "omni-parental\t1";
constexpr const char* kErrorDomain = "OmniParental";   // OmniFxTabState::failDomain while the blocked panel is shown
constexpr size_t kMaxSites = 500, kHostMax = 253;
constexpr long kMaxFileBytes = 64L << 10;
constexpr int kPinMin = 4, kPinMax = 6;
constexpr int kMaxFails = 5;                  // wrong PINs in a row before the cooldown
constexpr int64_t kCooldownSec = 300;         // 5 minutes
constexpr uint32_t kOnceMs = 60u * 60u * 1000u; // "Allow once": this host for an hour (or until Omni closes)
constexpr int kDefaultIterations = 100000;    // PBKDF2 rounds for a new PIN (the file keeps its own count)
constexpr int kMinIterations = 10000, kMaxIterations = 5000000;

enum Mode { kBlockList = 0, kAllowList = 1 };

// --- small helpers -------------------------------------------------------------------------------------------------
inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }
inline std::string lowerAscii(std::string s) { for (auto& c : s) c = lower(c); return s; }
inline bool endsWith(const std::string& s, const std::string& t) { return s.size() >= t.size() && s.compare(s.size() - t.size(), t.size(), t) == 0; }
inline int hexVal(char c) { return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1; }

// --- IP literals -----------------------------------------------------------------------------------------------------
// WHATWG IPv4: 1-4 parts, each decimal, 0x hex or 0-leading octal; the last part fills the remaining bytes.
// Returns 1: an IPv4 address (dotted in *out), 0: not an IPv4 form, -1: looks numeric but is invalid (fail closed).
inline int parseIPv4(const std::string& h, std::string* out)
{
    if (h.empty()) return 0;
    std::vector<std::string> parts;
    size_t from = 0;
    for (;;) { const size_t d = h.find('.', from); parts.push_back(h.substr(from, d == std::string::npos ? std::string::npos : d - from)); if (d == std::string::npos) break; from = d + 1; }
    if (parts.size() > 1 && parts.back().empty()) parts.pop_back();   // one trailing dot is allowed
    // Only a host whose LAST label is numeric is an IPv4 address (WHATWG "ends in a number").
    auto numeric = [](const std::string& p) {
        if (p.empty()) return false;
        if (p.size() > 1 && p[0] == '0' && (p[1] == 'x' || p[1] == 'X')) { for (size_t i = 2; i < p.size(); ++i) if (hexVal(p[i]) < 0) return false; return true; }
        for (char c : p) if (c < '0' || c > '9') return false;
        return true;
    };
    if (!numeric(parts.back())) return 0;
    if (parts.size() > 4) return -1;
    uint64_t v[4] = { 0, 0, 0, 0 };
    for (size_t i = 0; i < parts.size(); ++i) {
        const std::string& p = parts[i];
        if (!numeric(p)) return -1;
        int base = 10; size_t k = 0;
        if (p.size() > 1 && p[0] == '0' && (p[1] == 'x' || p[1] == 'X')) { base = 16; k = 2; }
        else if (p.size() > 1 && p[0] == '0') { base = 8; k = 1; }
        uint64_t x = 0;
        for (; k < p.size(); ++k) {
            const int d = hexVal(p[k]);
            if (d < 0 || d >= base) return -1;
            x = x * uint64_t(base) + uint64_t(d);
            if (x > 0xffffffffull) return -1;
        }
        v[i] = x;
    }
    const size_t n = parts.size();
    for (size_t i = 0; i + 1 < n; ++i) if (v[i] > 255) return -1;
    const uint64_t lastMax = n == 1 ? 0xffffffffull : n == 2 ? 0xffffffull : n == 3 ? 0xffffull : 0xffull;
    if (v[n - 1] > lastMax) return -1;
    uint32_t a = uint32_t(v[n - 1]);
    for (size_t i = 0; i + 1 < n; ++i) a |= uint32_t(v[i]) << (8 * (3 - i));
    if (out) *out = std::to_string(a >> 24) + "." + std::to_string((a >> 16) & 255) + "." + std::to_string((a >> 8) & 255) + "." + std::to_string(a & 255);
    return 1;
}
// IPv6 (no brackets) -> canonical RFC 5952 text, lower case. False: not valid.
inline bool canonIPv6(const std::string& s0, std::string* out)
{
    std::string s = lowerAscii(s0);
    const size_t pct = s.find('%');            // a zone id is not allowed in URLs
    if (pct != std::string::npos || s.empty()) return false;
    uint16_t w[8] = { 0 };
    int n = 0, gap = -1;
    size_t i = 0;
    if (s.compare(0, 2, "::") == 0) { gap = 0; i = 2; if (i == s.size()) { if (out) *out = "::"; return true; } }
    else if (s[0] == ':') return false;
    while (i < s.size()) {
        if (n >= 8) return false;
        // dotted IPv4 tail
        const size_t end = s.find(':', i);
        const std::string piece = s.substr(i, end == std::string::npos ? std::string::npos : end - i);
        if (piece.find('.') != std::string::npos) {
            if (end != std::string::npos || n > 6) return false;
            int dots = 0; for (char c : piece) { if (c == '.') ++dots; else if (c < '0' || c > '9') return false; }
            if (dots != 3) return false;
            std::string d;
            if (parseIPv4(piece, &d) != 1) return false;
            unsigned a, b, c, e; if (sscanf(d.c_str(), "%u.%u.%u.%u", &a, &b, &c, &e) != 4) return false;
            w[n++] = uint16_t(a << 8 | b); w[n++] = uint16_t(c << 8 | e);
            i = s.size();
            break;
        }
        if (piece.empty() || piece.size() > 4) return false;
        unsigned v = 0; for (char c : piece) { const int h = hexVal(c); if (h < 0) return false; v = v * 16 + unsigned(h); }
        w[n++] = uint16_t(v);
        if (end == std::string::npos) { i = s.size(); break; }
        i = end + 1;
        if (i < s.size() && s[i] == ':') { if (gap >= 0) return false; gap = n; ++i; if (i == s.size()) break; }
        else if (i == s.size()) return false;   // trailing single ':'
    }
    if (gap < 0 && n != 8) return false;
    if (gap >= 0 && n > 7) return false;
    uint16_t full[8] = { 0 };
    if (gap < 0) for (int k = 0; k < 8; ++k) full[k] = w[k];
    else {
        for (int k = 0; k < gap; ++k) full[k] = w[k];
        const int tail = n - gap;
        for (int k = 0; k < tail; ++k) full[8 - tail + k] = w[gap + k];
    }
    // longest run of zeros (>= 2) becomes "::"
    int bestAt = -1, bestLen = 0;
    for (int k = 0; k < 8;) {
        if (full[k]) { ++k; continue; }
        int m = k; while (m < 8 && !full[m]) ++m;
        if (m - k > bestLen && m - k >= 2) { bestAt = k; bestLen = m - k; }
        k = m;
    }
    std::string o;
    char b[8];
    for (int k = 0; k < 8; ++k) {
        if (k == bestAt) { o += "::"; k += bestLen - 1; continue; }
        if (!o.empty() && o.back() != ':') o += ':';
        snprintf(b, sizeof b, "%x", full[k]); o += b;
    }
    if (out) *out = o;
    return true;
}

// --- IDN: RFC 3492 punycode for one label (ASCII lower-casing only; no Unicode case folding / NFC) -------------------
inline bool utf8Decode(const std::string& s, std::vector<uint32_t>& cps)
{
    cps.clear();
    for (size_t i = 0; i < s.size();) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        uint32_t cp; int extra;
        if (c < 0x80) { cp = c; extra = 0; }
        else if ((c & 0xe0) == 0xc0) { cp = c & 0x1f; extra = 1; }
        else if ((c & 0xf0) == 0xe0) { cp = c & 0x0f; extra = 2; }
        else if ((c & 0xf8) == 0xf0) { cp = c & 0x07; extra = 3; }
        else return false;
        for (int k = 1; k <= extra; ++k) {
            if (i + size_t(k) >= s.size()) return false;
            const unsigned char d = static_cast<unsigned char>(s[i + size_t(k)]);
            if ((d & 0xc0) != 0x80) return false;
            cp = cp << 6 | (d & 0x3f);
        }
        if ((extra == 1 && cp < 0x80) || (extra == 2 && cp < 0x800) || (extra == 3 && cp < 0x10000) || cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff)) return false;
        cps.push_back(extra == 0 ? uint32_t(lower(char(cp))) : cp);
        i += size_t(extra) + 1;
    }
    return true;
}
inline bool punycodeLabel(const std::string& label, std::string* out)
{
    std::vector<uint32_t> in;
    if (!utf8Decode(label, in)) return false;
    bool ascii = true; for (uint32_t c : in) if (c >= 0x80) ascii = false;
    if (ascii) { std::string o; for (uint32_t c : in) o += char(c); *out = o; return true; }
    const uint32_t base = 36, tmin = 1, tmax = 26, skew = 38, damp = 700;
    auto digit = [](uint32_t d) { return char(d < 26 ? 'a' + d : '0' + (d - 26)); };
    auto adapt = [&](uint32_t delta, uint32_t numpoints, bool first) {
        delta = first ? delta / damp : delta / 2;
        delta += delta / numpoints;
        uint32_t k = 0;
        while (delta > ((base - tmin) * tmax) / 2) { delta /= base - tmin; k += base; }
        return k + (base - tmin + 1) * delta / (delta + skew);
    };
    std::string o;
    for (uint32_t c : in) if (c < 0x80) o += char(c);
    const uint32_t b = uint32_t(o.size());
    uint32_t h = b;
    if (b) o += '-';
    uint32_t n = 128, delta = 0, bias = 72;
    while (h < in.size()) {
        uint32_t m = 0xffffffffu;
        for (uint32_t c : in) if (c >= n && c < m) m = c;
        if (uint64_t(m - n) * (h + 1) + delta > 0xffffffffull) return false;
        delta += (m - n) * (h + 1);
        n = m;
        for (uint32_t c : in) {
            if (c < n && ++delta == 0) return false;
            if (c == n) {
                uint32_t q = delta;
                for (uint32_t k = base;; k += base) {
                    const uint32_t t = k <= bias ? tmin : k >= bias + tmax ? tmax : k - bias;
                    if (q < t) break;
                    o += digit(t + (q - t) % (base - t));
                    q = (q - t) / (base - t);
                }
                o += digit(q);
                bias = adapt(delta, h + 1, h == b);
                delta = 0;
                ++h;
            }
        }
        ++delta; ++n;
    }
    *out = "xn--" + o;
    return true;
}

// --- hosts -----------------------------------------------------------------------------------------------------------
// A host as written in a URL or typed into a list -> the key that is compared: lower case, no trailing dots,
// percent escapes decoded, non-ASCII labels as punycode, IPv4 in dotted decimal, IPv6 canonical without brackets.
// "" when it can't be read (the caller fails closed: a web URL with an unreadable host is blocked).
inline std::string normHost(const std::string& raw)
{
    std::string h;
    for (size_t i = 0; i < raw.size(); ++i) {   // percent escapes (WebKit already decodes; defence in depth)
        if (raw[i] == '%' && i + 2 < raw.size() && hexVal(raw[i + 1]) >= 0 && hexVal(raw[i + 2]) >= 0) { h += char(hexVal(raw[i + 1]) * 16 + hexVal(raw[i + 2])); i += 2; }
        else if (raw[i] == '%') return std::string();
        else h += raw[i];
    }
    if (h.size() >= 2 && h.front() == '[' && h.back() == ']') {
        std::string v6;
        return canonIPv6(h.substr(1, h.size() - 2), &v6) ? v6 : std::string();
    }
    if (h.find(':') != std::string::npos) return std::string();
    // full-width / ideographic dots (U+3002, U+FF0E, U+FF61) are label separators too
    for (const char* dot : { "\xe3\x80\x82", "\xef\xbc\x8e", "\xef\xbd\xa1" }) for (size_t p; (p = h.find(dot)) != std::string::npos;) h.replace(p, 3, ".");
    while (!h.empty() && h.back() == '.') h.pop_back();
    if (h.empty() || h.size() > 4 * kHostMax) return std::string();
    std::string out;
    size_t from = 0;
    for (;;) {
        const size_t d = h.find('.', from);
        const std::string label = h.substr(from, d == std::string::npos ? std::string::npos : d - from);
        if (label.empty()) return std::string();   // "a..b"
        std::string enc;
        if (!punycodeLabel(label, &enc) || enc.empty() || enc.size() > 63) return std::string();
        for (char c : enc) {
            const bool ok = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-' || c == '_';
            if (!ok) return std::string();
        }
        out += (out.empty() ? "" : ".") + enc;
        if (d == std::string::npos) break;
        from = d + 1;
    }
    if (out.size() > kHostMax) return std::string();
    std::string v4;
    const int ip = parseIPv4(out, &v4);
    if (ip < 0) return std::string();
    return ip == 1 ? v4 : out;
}
inline bool isIP(const std::string& key) { return key.find(':') != std::string::npos || parseIPv4(key, nullptr) == 1; }
inline bool isLoopback(const std::string& key)
{
    if (key == "localhost" || endsWith(key, ".localhost") || key == "::1") return true;
    if (key.compare(0, 4, "127.") == 0 && parseIPv4(key, nullptr) == 1) return true;
    // IPv4-mapped 127/8 in canonical form: "::ffff:7fXX:XXXX"
    return key.size() > 12 && key.compare(0, 9, "::ffff:7f") == 0 && key[11] == ':';
}

// A list entry as typed ("https://www.YouTube.com/watch", "*.example.org", "Bücher.de") -> its key ("" if unusable).
// "www." is dropped (blocking www.example.com blocks example.com and all its subdomains, as people expect).
inline std::string entryKey(std::string s)
{
    while (!s.empty() && (s.front() == ' ' || s.front() == '\t')) s.erase(0, 1);
    while (!s.empty() && (s.back() == ' ' || s.back() == '\t' || s.back() == '\r' || s.back() == '\n')) s.pop_back();
    const size_t scheme = s.find("://");
    if (scheme != std::string::npos) s = s.substr(scheme + 3);
    const size_t end = s.find_first_of("/?#\\");
    if (end != std::string::npos) s = s.substr(0, end);
    const size_t at = s.rfind('@');
    if (at != std::string::npos) s = s.substr(at + 1);
    if (!s.empty() && s[0] != '[') { const size_t colon = s.rfind(':'); if (colon != std::string::npos && s.find(':') == colon) s = s.substr(0, colon); }
    else if (!s.empty()) { const size_t close = s.find(']'); if (close != std::string::npos) s = s.substr(0, close + 1); }
    if (s.compare(0, 2, "*.") == 0) s = s.substr(2);
    while (!s.empty() && s[0] == '.') s.erase(0, 1);
    std::string k = normHost(s);
    if (k.compare(0, 4, "www.") == 0 && k.size() > 4 && k.find('.', 4) != std::string::npos) k = k.substr(4);
    return k;
}
// host (a normHost key) is the entry or a subdomain of it. IP literals: exact only.
inline bool hostMatches(const std::string& host, const std::string& entry)
{
    if (host.empty() || entry.empty()) return false;
    if (host == entry) return true;
    if (isIP(entry) || isIP(host)) return false;
    return host.size() > entry.size() && endsWith(host, "." + entry);
}
inline bool listMatches(const std::set<std::string>& list, const std::string& host)
{
    if (list.count(host)) return true;
    for (size_t p = host.find('.'); p != std::string::npos; p = host.find('.', p + 1))   // each parent domain
        if (list.count(host.substr(p + 1)) && hostMatches(host, host.substr(p + 1))) return true;
    return false;
}

// --- URLs ------------------------------------------------------------------------------------------------------------
enum Kind {
    kInternal,     // about:, omni:, data:, javascript:, file:, schemes without an authority: nothing to check
    kWeb,          // has a host: host is its key
    kUnreadable,   // has an authority whose host can't be read: blocked (fail closed)
};
struct Target { Kind kind = kInternal; std::string scheme, host; };
inline bool specialScheme(const std::string& s) { return s == "http" || s == "https" || s == "ws" || s == "wss" || s == "ftp"; }
inline Target classify(const std::string& url0, int depth = 0)
{
    Target t;
    std::string url;
    for (char c : url0) if (c != '\t' && c != '\n' && c != '\r') url += c;   // WHATWG strips these anywhere
    size_t a = 0, b = url.size();
    while (a < b && static_cast<unsigned char>(url[a]) <= 0x20) ++a;
    while (b > a && static_cast<unsigned char>(url[b - 1]) <= 0x20) --b;
    url = url.substr(a, b - a);
    const size_t colon = url.find(':');
    if (colon == std::string::npos || colon == 0) { t.kind = kUnreadable; return t; }   // relative: not from WebKit
    for (size_t i = 0; i < colon; ++i) {
        const char c = url[i];
        const bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (i && ((c >= '0' && c <= '9') || c == '+' || c == '-' || c == '.'));
        if (!ok) { t.kind = kUnreadable; return t; }
    }
    t.scheme = lowerAscii(url.substr(0, colon));
    std::string rest = url.substr(colon + 1);
    if (t.scheme == "blob") {   // blob:https://host/uuid: the creator's origin decides; blob:null/... is opaque
        if (depth == 0 && rest.find("://") != std::string::npos) { Target in = classify(rest, 1); in.scheme = "blob:" + in.scheme; return in; }
        t.kind = kInternal; return t;
    }
    if (t.scheme == "about" || t.scheme == "data" || t.scheme == "javascript" || t.scheme == "omni" || t.scheme == "file") { t.kind = kInternal; return t; }
    const bool special = specialScheme(t.scheme);
    size_t p = 0;
    if (special) { while (p < rest.size() && (rest[p] == '/' || rest[p] == '\\')) ++p; }   // "http:\\host", "http:host"
    else if (rest.compare(0, 2, "//") == 0) p = 2;
    else { t.kind = kInternal; return t; }   // mailto:, tel:, ... (no host)
    const size_t end = rest.find_first_of(special ? "/?#\\" : "/?#", p);
    std::string auth = rest.substr(p, end == std::string::npos ? std::string::npos : end - p);
    const size_t at = auth.rfind('@');
    if (at != std::string::npos) auth = auth.substr(at + 1);   // userinfo is never the host
    std::string host = auth;
    if (!auth.empty() && auth[0] == '[') {
        const size_t close = auth.find(']');
        if (close == std::string::npos) { t.kind = kUnreadable; return t; }
        host = auth.substr(0, close + 1);
        const std::string after = auth.substr(close + 1);
        if (!after.empty() && after[0] != ':') { t.kind = kUnreadable; return t; }
    } else {
        const size_t c2 = auth.find(':');
        if (c2 != std::string::npos) host = auth.substr(0, c2);
    }
    if (host.empty()) { t.kind = special && t.scheme != "file" ? kUnreadable : kInternal; return t; }
    t.host = normHost(host);
    t.kind = t.host.empty() ? kUnreadable : kWeb;
    return t;
}

// --- PIN ---------------------------------------------------------------------------------------------------------------
inline bool validPin(const std::string& pin)
{
    if (int(pin.size()) < kPinMin || int(pin.size()) > kPinMax) return false;
    for (char c : pin) if (c < '0' || c > '9') return false;
    return true;
}
struct Pin {                      // "pin\tpbkdf2-sha256\t<iterations>\t<salt hex 32>\t<hash hex 64>"
    int iterations = 0;
    std::string saltHex, hashHex;
    bool ok() const { return iterations >= kMinIterations && iterations <= kMaxIterations && saltHex.size() == 32 && hashHex.size() == 64; }
};
inline bool allHex(const std::string& s) { for (char c : s) if (hexVal(c) < 0 || (c >= 'A' && c <= 'F')) return false; return true; }

inline std::string toHex(const uint8_t* b, size_t n)
{
    static const char* h = "0123456789abcdef";
    std::string o; for (size_t i = 0; i < n; ++i) { o += h[b[i] >> 4]; o += h[b[i] & 15]; }
    return o;
}
inline bool fromHex(const std::string& h, std::string& out)
{
    out.clear();
    if (h.size() % 2) return false;
    for (size_t i = 0; i < h.size(); i += 2) { const int a = hexVal(h[i]), b = hexVal(h[i + 1]); if (a < 0 || b < 0) return false; out += char(a * 16 + b); }
    return true;
}
// kdf: bool(const std::string& pin, const std::string& salt, int iterations, uint8_t out[32]) - the shell passes
// OmniVault::deriveKey (PBKDF2-HMAC-SHA256, OpenSSL). salt: 16 random bytes (OmniVault::randomBytes).
template <class Kdf> inline bool makePin(const std::string& pin, const std::string& salt, int iterations, Kdf kdf, Pin* out)
{
    if (!validPin(pin) || salt.size() != 16 || iterations < kMinIterations || iterations > kMaxIterations) return false;
    uint8_t key[32];
    if (!kdf(pin, salt, iterations, key)) return false;
    Pin p; p.iterations = iterations;
    p.saltHex = toHex(reinterpret_cast<const uint8_t*>(salt.data()), salt.size());
    p.hashHex = toHex(key, 32);
    for (auto& k : key) k = 0;
    *out = p;
    return true;
}
template <class Kdf> inline bool verifyPin(const Pin& p, const std::string& pin, Kdf kdf)
{
    if (!p.ok() || !validPin(pin)) return false;
    std::string salt, want;
    if (!fromHex(p.saltHex, salt) || !fromHex(p.hashHex, want) || want.size() != 32) return false;
    uint8_t key[32];
    if (!kdf(pin, salt, p.iterations, key)) return false;
    unsigned diff = 0;
    for (size_t i = 0; i < 32; ++i) diff |= unsigned(key[i] ^ static_cast<uint8_t>(want[i]));   // constant time
    for (auto& k : key) k = 0;
    return diff == 0;
}

// Wrong-PIN limiter: kMaxFails wrong PINs -> kCooldownSec. Seconds are the console's clock (time()); a cooldown that
// reaches further than kCooldownSec into the future (the clock was set back) is cut to kCooldownSec.
struct Limiter {
    int fails = 0;
    int64_t lockUntil = 0;
    int64_t remaining(int64_t now)
    {
        if (lockUntil > now + kCooldownSec) lockUntil = now + kCooldownSec;
        return lockUntil > now ? lockUntil - now : 0;
    }
    bool locked(int64_t now) { return remaining(now) > 0; }
    // A wrong PIN. True: that started the cooldown.
    bool failed(int64_t now)
    {
        if (locked(now)) return true;
        if (++fails >= kMaxFails) { fails = 0; lockUntil = now + kCooldownSec; return true; }
        return false;
    }
    void succeeded() { fails = 0; lockUntil = 0; }
    int triesLeft() const { return kMaxFails - fails; }
};

// --- the settings file -----------------------------------------------------------------------------------------------
struct Store {
    bool enabled = false;
    int mode = kBlockList;
    bool safeSearch = false, lockPrivate = false, lockSettings = false;
    Pin pin;
    Limiter limiter;
    std::set<std::string> block, allow;   // keys (entryKey); in block-list mode `allow` holds the exceptions
    bool active() const { return enabled && pin.ok(); }
};
inline std::vector<std::string> splitTabs(const std::string& s)
{
    std::vector<std::string> v; size_t from = 0;
    for (;;) { const size_t t = s.find('\t', from); v.push_back(s.substr(from, t == std::string::npos ? std::string::npos : t - from)); if (t == std::string::npos) break; from = t + 1; }
    return v;
}
inline bool parseInt64(const std::string& s, int64_t* out)
{
    if (s.empty() || s.size() > 18) return false;
    int64_t v = 0; for (char c : s) { if (c < '0' || c > '9') return false; v = v * 10 + (c - '0'); }
    *out = v; return true;
}
// ok: false when the text isn't a parental.txt (missing / other header): the caller treats that as "not set up".
inline Store parse(const std::string& text, bool* ok = nullptr)
{
    Store s;
    if (ok) *ok = false;
    size_t from = 0;
    bool first = true;
    while (from < text.size()) {
        size_t nl = text.find('\n', from);
        if (nl == std::string::npos) nl = text.size();
        std::string line = text.substr(from, nl - from);
        from = nl + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (first) { first = false; if (line != kHeader) return Store(); if (ok) *ok = true; continue; }
        const auto f = splitTabs(line);
        if (f.size() < 2) continue;
        const std::string& k = f[0];
        int64_t v = 0;
        if (k == "enabled") s.enabled = f[1] == "1";
        else if (k == "mode") s.mode = f[1] == "allow" ? kAllowList : kBlockList;
        else if (k == "safe") s.safeSearch = f[1] == "1";
        else if (k == "lockprivate") s.lockPrivate = f[1] == "1";
        else if (k == "locksettings") s.lockSettings = f[1] == "1";
        else if (k == "pin" && f.size() == 5 && f[1] == "pbkdf2-sha256" && parseInt64(f[2], &v) && allHex(f[3]) && allHex(f[4])) {
            Pin p; p.iterations = int(v > kMaxIterations ? 0 : v); p.saltHex = f[3]; p.hashHex = f[4];
            if (p.ok()) s.pin = p;
        }
        else if (k == "fails" && parseInt64(f[1], &v)) s.limiter.fails = int(v >= kMaxFails ? kMaxFails - 1 : v);
        else if (k == "lockuntil" && parseInt64(f[1], &v)) s.limiter.lockUntil = v;
        else if ((k == "block" || k == "allow")) {
            const std::string key = entryKey(f[1]);
            auto& list = k == "block" ? s.block : s.allow;
            if (!key.empty() && list.size() < kMaxSites) list.insert(key);
        }
    }
    if (first) return Store();
    return s;
}
inline std::string serialize(const Store& s)
{
    std::string o = std::string(kHeader) + "\n";
    o += std::string("enabled\t") + (s.enabled ? "1" : "0") + "\n";
    o += std::string("mode\t") + (s.mode == kAllowList ? "allow" : "block") + "\n";
    o += std::string("safe\t") + (s.safeSearch ? "1" : "0") + "\n";
    o += std::string("lockprivate\t") + (s.lockPrivate ? "1" : "0") + "\n";
    o += std::string("locksettings\t") + (s.lockSettings ? "1" : "0") + "\n";
    if (s.pin.ok()) o += "pin\tpbkdf2-sha256\t" + std::to_string(s.pin.iterations) + "\t" + s.pin.saltHex + "\t" + s.pin.hashHex + "\n";
    if (s.limiter.fails) o += "fails\t" + std::to_string(s.limiter.fails) + "\n";
    if (s.limiter.lockUntil) o += "lockuntil\t" + std::to_string(s.limiter.lockUntil) + "\n";
    for (const auto& h : s.block) o += "block\t" + h + "\n";
    for (const auto& h : s.allow) o += "allow\t" + h + "\n";
    return o;
}
enum AddResult { kAdded, kAlready, kFull, kBad };
inline AddResult addSite(std::set<std::string>& list, const std::string& typed, std::string* key = nullptr)
{
    const std::string k = entryKey(typed);
    if (key) *key = k;
    if (k.empty()) return kBad;
    if (list.count(k)) return kAlready;
    if (list.size() >= kMaxSites) return kFull;
    list.insert(k);
    return kAdded;
}

// --- the decision ----------------------------------------------------------------------------------------------------
struct Session {                              // this run only (never written)
    std::map<std::string, uint32_t> once;     // "Allow once": host -> SDL ticks when allowed
    bool allowedOnce(const std::string& host, uint32_t nowMs) const
    {
        for (const auto& [h, at] : once) if (hostMatches(host, h) && uint32_t(nowMs - at) < kOnceMs) return true;
        return false;
    }
    void allow(const std::string& host, uint32_t nowMs) { if (once.size() > 200) once.clear(); once[host] = nowMs; }
};
enum Verdict { kAllow, kBlock };
struct Decision { Verdict verdict = kAllow; std::string host; const char* why = ""; };
inline Decision decide(const Store& s, const Session& session, const std::string& url, uint32_t nowMs)
{
    Decision d;
    if (!s.active()) return d;
    const Target t = classify(url);
    d.host = t.host;
    if (t.kind == kInternal) { d.why = "internal"; return d; }
    if (t.kind == kUnreadable) { d.verdict = kBlock; d.why = "unreadable host"; return d; }
    if (isLoopback(t.host)) { d.why = "this console"; return d; }   // Omni's own apps (Downloads, Bloom Core) on 127.0.0.1
    if (listMatches(s.allow, t.host) || session.allowedOnce(t.host, nowMs)) { d.why = "allowed"; return d; }
    if (s.mode == kAllowList) { d.verdict = kBlock; d.why = "not on the allowed list"; return d; }
    if (listMatches(s.block, t.host)) { d.verdict = kBlock; d.why = "on the blocked list"; return d; }
    d.why = "not listed";
    return d;
}

// --- safe search -----------------------------------------------------------------------------------------------------
// Google (safe=active), Bing (adlt=strict), DuckDuckGo (kp=1): their documented URL parameters, on top-level search
// result pages only. "" when the URL is not a search page of these or already carries the right value.
// YouTube Restricted Mode can't be forced from here (see apply_parental.py: no request-header hook in this WebKit).
inline bool googleHost(const std::string& h)
{
    std::string r = h;
    if (r.compare(0, 4, "www.") == 0) r = r.substr(4);
    else if (r.compare(0, 7, "images.") == 0) r = r.substr(7);
    if (r.compare(0, 7, "google.") != 0) return false;
    const std::string tld = r.substr(7);   // com, de, co.uk, com.au
    if (tld.empty() || tld.size() > 6) return false;
    int dots = 0; for (char c : tld) { if (c == '.') ++dots; else if (c < 'a' || c > 'z') return false; }
    return dots <= 1 && tld.front() != '.' && tld.back() != '.';
}
inline std::string withParam(const std::string& url, size_t qStart, size_t qEnd, const std::string& key, const std::string& value)
{
    // qStart: index after '?' (or npos: no query); qEnd: '#' or end.
    std::string query = qStart == std::string::npos ? std::string() : url.substr(qStart, qEnd - qStart);
    std::vector<std::string> parts;
    size_t from = 0;
    while (from <= query.size() && !query.empty()) {
        size_t amp = query.find('&', from);
        if (amp == std::string::npos) amp = query.size();
        parts.push_back(query.substr(from, amp - from));
        from = amp + 1;
        if (amp == query.size()) break;
    }
    bool found = false, changed = false;
    std::vector<std::string> out;
    for (const auto& p : parts) {
        const size_t eq = p.find('=');
        const std::string k = lowerAscii(p.substr(0, eq));
        if (k == key) {
            const std::string v = eq == std::string::npos ? std::string() : p.substr(eq + 1);
            if (found) { changed = true; continue; }   // duplicates (a later "safe=off" must not win)
            found = true;
            if (v != value || p.substr(0, eq) != key) changed = true;
            out.push_back(key + "=" + value);
        } else out.push_back(p);
    }
    if (!found) { out.push_back(key + "=" + value); changed = true; }
    if (!changed) return std::string();
    std::string q;
    for (size_t i = 0; i < out.size(); ++i) q += (i ? "&" : "") + out[i];
    const size_t pathEnd = qStart == std::string::npos ? qEnd : qStart - 1;
    return url.substr(0, pathEnd) + "?" + q + url.substr(qEnd);
}
inline bool hasParam(const std::string& query, const char* key)
{
    size_t from = 0;
    const std::string k = key;
    while (from <= query.size()) {
        size_t amp = query.find('&', from);
        if (amp == std::string::npos) amp = query.size();
        const std::string p = query.substr(from, amp - from);
        if (lowerAscii(p.substr(0, p.find('='))) == k) return true;
        from = amp + 1;
    }
    return false;
}
inline std::string safeSearchUrl(const std::string& url)
{
    const Target t = classify(url);
    if (t.kind != kWeb || (t.scheme != "https" && t.scheme != "http")) return std::string();
    const size_t schemeEnd = url.find("//");
    if (schemeEnd == std::string::npos) return std::string();
    const size_t pathAt = url.find_first_of("/?#", schemeEnd + 2);
    const size_t hash = url.find('#');
    const size_t qEnd = hash == std::string::npos ? url.size() : hash;
    size_t q = url.find('?', schemeEnd + 2);
    if (q != std::string::npos && q > qEnd) q = std::string::npos;
    const std::string path = pathAt == std::string::npos || url[pathAt] != '/' ? std::string("/")
        : url.substr(pathAt, (q != std::string::npos ? q : qEnd) - pathAt);
    const std::string query = q == std::string::npos ? std::string() : url.substr(q + 1, qEnd - q - 1);
    const size_t qStart = q == std::string::npos ? std::string::npos : q + 1;
    const std::string& h = t.host;
    if (googleHost(h)) {
        if (path == "/search" || ((path == "/" || path == "/webhp") && hasParam(query, "q"))) return withParam(url, qStart, qEnd, "safe", "active");
        return std::string();
    }
    if (h == "bing.com" || endsWith(h, ".bing.com")) {
        if (path == "/search" || path == "/images/search" || path == "/videos/search" || path == "/news/search" || path == "/shop")
            return withParam(url, qStart, qEnd, "adlt", "strict");
        return std::string();
    }
    if (h == "duckduckgo.com" || h == "html.duckduckgo.com" || h == "lite.duckduckgo.com" || h == "www.duckduckgo.com") {
        if ((path == "/" || path == "/html" || path == "/html/" || path == "/lite" || path == "/lite/") && hasParam(query, "q"))
            return withParam(url, qStart, qEnd, "kp", "1");
        return std::string();
    }
    return std::string();
}

// --- texts -----------------------------------------------------------------------------------------------------------
inline std::string blockedTitle() { return "This site is blocked"; }
inline std::string blockedBody(const std::string& host, int mode)
{
    const std::string who = host.empty() ? std::string("This address") : host;
    return mode == kAllowList ? who + " isn't on this console's allowed sites. A parent can enter the PIN to allow it."
                              : who + " is blocked on this console by parental controls. A parent can enter the PIN to allow it.";
}
inline std::string modeName(int mode) { return mode == kAllowList ? "Allowed sites only" : "Block these sites"; }
inline std::string summary(const Store& s)
{
    if (!s.pin.ok()) return "Off";
    if (!s.enabled) return "Off (PIN set)";
    return "On: " + modeName(s.mode);
}
inline std::string cooldownText(int64_t remainingSec)
{
    const int64_t m = remainingSec / 60, sec = remainingSec % 60;
    char b[96];
    snprintf(b, sizeof b, "Too many wrong PINs. Try again in %lld:%02lld", (long long)m, (long long)sec);
    return b;
}
inline std::string dots(size_t n)   // what the PIN pad shows: one dot per digit, never the digits
{
    std::string o;
    for (size_t i = 0; i < size_t(kPinMax); ++i) o += (i ? " " : "") + std::string(i < n ? "\xe2\x97\x8f" : "\xe2\x97\x8b");
    return o;
}
inline std::string forgotBody()
{
    return "The PIN can't be shown or recovered (only a salted hash of it is stored). To reset parental controls, use the "
           "PC Setup app to delete /data/omni/parental.txt on this console, then restart Omni: every parental setting "
           "is cleared. Anyone who can reach the console's files can do this, so these controls are meant for a family "
           "console, not as protection against someone with that access.";
}
inline std::string safeSearchDetail()
{
    return "Google, Bing, DuckDuckGo. YouTube Restricted Mode can't be forced here";
}

} // namespace OmniParental
'''

SHELL = r'''// OMNI_PARENTAL_V1: Browser settings > "Parental controls..." (shell side). Included from OmniFeatures3.h (inside
// OmniBrowser.cpp's anonymous namespace, after OmniWebAppsShell.h). The pure part is OmniParental.h; the reasons are in
// tools/apply_parental.py. Main thread only; /data/omni/parental.txt is written through omniIoQueue.
//   - Enforcement: omniParPolicy runs first in omniEverydayNavigation's action callback, for main-frame AND subframe
//     navigations (a blocked subframe is ignored; a blocked main frame shows "This site is blocked" over the page).
//     Safe search re-issues a main-frame GET with the provider's parameter (the https-only / UA re-issue path).
//   - PIN: typed on Omni's own number pad (an OmniFxPanel grid; digits never drawn), checked with PBKDF2-HMAC-SHA256
//     from OmniVault.h (OmniVault::deriveKey, OpenSSL's PKCS5_PBKDF2_HMAC; salt from OmniVault::randomBytes =
//     RAND_bytes). 5 wrong PINs -> 5 minutes (the count is kept in the file, so restarting Omni doesn't reset it).
//   - omniParUnlocked: a correct PIN opens the gate until every panel is closed again (omniParTick).
#pragma once
#include <ctime>

namespace OPAR = OmniParental;
static OPAR::Store omniParStore;
static bool omniParLoaded = false;
static OPAR::Session omniParSession;   // "Allow once" hosts (this run only)
static bool omniParUnlocked = false;

static void omniParLoad()
{
    if (omniParLoaded) return;
    omniParLoaded = true;
    FILE* f = fopen(omniData(OPAR::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) < OPAR::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    bool ok = false;
    omniParStore = OPAR::parse(text, &ok);
    fprintf(stderr, "OMNI PARENTAL: %s (%s)\n", ok ? "loaded" : "unreadable parental.txt: off", OPAR::summary(omniParStore).c_str()); fflush(stderr);
}
static void omniParWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OPAR::kFileName), OPAR::serialize(omniParStore), false);
}
static int64_t omniParNow() { return int64_t(time(nullptr)); }

// --- the PIN pad ---------------------------------------------------------------------------------------------------
enum { omniParPadVerify = 0, omniParPadNew, omniParPadAgain };
enum { omniParKey0 = 200, omniParKeyDelete = 210, omniParKeyOk = 211 };
static int omniParPadMode = omniParPadVerify;
static std::string omniParDigits, omniParFirst, omniParPadTitle, omniParPadNote;
static std::function<void(bool)> omniParPadDone;

static void omniParWipeDigits() { OmniVault::wipe(omniParDigits); OmniVault::wipe(omniParFirst); }
static void omniParPadBuild(OmniFxPanel& p)
{
    p.title = omniParPadTitle;
    p.subtitle = OPAR::dots(omniParDigits.size()) + (omniParPadNote.empty() ? std::string() : "    " + omniParPadNote);
    auto key = [&](int id, const char* label) { OmniFxRow r; r.id = id; r.label = label; p.rows.push_back(r); };
    static const char* const digits[] = { "0", "1", "2", "3", "4", "5", "6", "7", "8", "9" };
    for (int d = 1; d <= 9; ++d) key(omniParKey0 + d, digits[d]);
    key(omniParKeyDelete, "Delete");
    key(omniParKey0, "0");
    key(omniParKeyOk, "OK");
}
static void omniParPadFinish(bool ok)
{
    omniParWipeDigits();
    omniParPadNote.clear();
    std::function<void(bool)> done = std::move(omniParPadDone);
    omniParPadDone = nullptr;
    if (ok) omniParUnlocked = true;
    omniFxPop();   // the pad
    if (done) done(ok);
}
static void omniParPadSubmit()
{
    if (!OPAR::validPin(omniParDigits)) { omniParPadNote = "Enter 4 to 6 digits"; return; }
    const int64_t now = omniParNow();
    if (omniParPadMode == omniParPadVerify) {
        if (omniParStore.limiter.locked(now)) { omniParWipeDigits(); omniParPadNote = OPAR::cooldownText(omniParStore.limiter.remaining(now)); return; }
        const auto t0 = SDL_GetTicks();
        const bool good = OPAR::verifyPin(omniParStore.pin, omniParDigits, OmniVault::deriveKey);
        fprintf(stderr, "OMNI PARENTAL: PIN %s in %u ms\n", good ? "ok" : "wrong", SDL_GetTicks() - t0); fflush(stderr);
        if (good) {
            if (omniParStore.limiter.fails || omniParStore.limiter.lockUntil) { omniParStore.limiter.succeeded(); omniParWrite(); }
            omniParPadFinish(true);
            return;
        }
        omniParWipeDigits();
        const bool cooling = omniParStore.limiter.failed(now);
        omniParWrite();   // the count survives a restart
        if (cooling) { notice(OPAR::cooldownText(omniParStore.limiter.remaining(now))); omniParPadFinish(false); return; }
        const int left = omniParStore.limiter.triesLeft();
        omniParPadNote = "Wrong PIN: " + std::to_string(left) + (left == 1 ? " try left" : " tries left");
        return;
    }
    if (omniParPadMode == omniParPadNew) {
        omniParFirst = omniParDigits;
        OmniVault::wipe(omniParDigits);
        omniParPadMode = omniParPadAgain;
        omniParPadTitle = "Enter the new PIN again";
        omniParPadNote.clear();
        return;
    }
    // omniParPadAgain
    if (omniParDigits != omniParFirst) {
        omniParWipeDigits();
        omniParPadMode = omniParPadNew;
        omniParPadTitle = "Choose a 4 to 6 digit PIN";
        omniParPadNote = "The PINs didn't match";
        return;
    }
    std::string salt(16, '\0');
    OPAR::Pin pin;
    const bool made = OmniVault::randomBytes(&salt[0], salt.size())
        && OPAR::makePin(omniParDigits, salt, OPAR::kDefaultIterations, OmniVault::deriveKey, &pin);
    OmniVault::wipe(salt);
    if (!made) { omniParWipeDigits(); notice("Couldn't set the PIN (no random numbers available)"); omniParPadFinish(false); return; }
    omniParStore.pin = pin;
    omniParStore.limiter.succeeded();
    omniParWrite();
    omniParPadFinish(true);
}
static bool omniParPadInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b == SDL_CONTROLLER_BUTTON_X) { if (!omniParDigits.empty()) omniParDigits.pop_back(); return true; }   // Square: delete
    if (b == SDL_CONTROLLER_BUTTON_Y) { omniParPadSubmit(); return true; }                                    // Triangle: OK
    if (b != SDL_CONTROLLER_BUTTON_A) return true;   // nothing else reaches the page while the pad is up
    if (r.id >= omniParKey0 && r.id <= omniParKey0 + 9) {
        if (int(omniParDigits.size()) < OPAR::kPinMax) omniParDigits += char('0' + (r.id - omniParKey0));
        omniParPadNote.clear();
    } else if (r.id == omniParKeyDelete) { if (!omniParDigits.empty()) omniParDigits.pop_back(); }
    else if (r.id == omniParKeyOk) omniParPadSubmit();
    return true;
}
static void omniParPadPush(int mode, const std::string& title, std::function<void(bool)> done)
{
    omniParWipeDigits();
    omniParPadMode = mode;
    omniParPadTitle = title;
    omniParPadNote.clear();
    omniParPadDone = std::move(done);
    OmniFxPanel p;
    p.title = title; p.w = 560; p.cols = 3; p.rowH = 74; p.maxVisible = 4;
    p.build = omniParPadBuild; p.input = omniParPadInput;
    p.faces = { { 0, "Press" }, { 2, "Delete" }, { 3, "OK" }, { 1, "Cancel" } };
    p.extra = "Digits are never shown";
    omniFxPush(std::move(p));
}
// Asks for the parental PIN (done(true) only after a correct one). The cooldown refuses before the pad opens.
static void omniParAskPin(const std::string& title, std::function<void(bool)> done)
{
    omniParLoad();
    const int64_t now = omniParNow();
    if (omniParStore.limiter.locked(now)) { notice(OPAR::cooldownText(omniParStore.limiter.remaining(now))); return; }
    omniParPadPush(omniParPadVerify, title, std::move(done));
}
static void omniParNewPin(std::function<void(bool)> done) { omniParPadPush(omniParPadNew, "Choose a 4 to 6 digit PIN", std::move(done)); }

// --- gates: Browser settings, Site settings, private tabs -------------------------------------------------------------
// True: the PIN pad was opened (or the cooldown refused); `again` runs after a correct PIN.
static bool omniParGate(int what, void (*again)())
{
    if (omniTestMode()) return false;
    omniParLoad();
    if (!omniParStore.active() || omniParUnlocked) return false;
    const bool need = what == omniParGatePrivate ? omniParStore.lockPrivate : omniParStore.lockSettings;
    if (!need) return false;
    const char* title = what == omniParGatePrivate ? "Enter the PIN to open a private tab"
        : what == omniParGateSite ? "Enter the PIN to open Site settings" : "Enter the PIN to open Browser settings";
    omniParAskPin(title, [again](bool ok) { if (ok && again) again(); });
    return true;
}
// OMNI_WEB_APPS_V1 app tiles: a saved app whose site is blocked doesn't open.
static bool omniParAppBlocked(const std::string& url)
{
    omniParLoad();
    const OPAR::Decision d = OPAR::decide(omniParStore, omniParSession, url, SDL_GetTicks());
    if (d.verdict != OPAR::kBlock) return false;
    notice((d.host.empty() ? std::string("This app's site") : d.host) + " is blocked by parental controls");
    fprintf(stderr, "OMNI PARENTAL: app tile refused: %s (%s)\n", url.c_str(), d.why); fflush(stderr);
    return true;
}

// --- the navigation policy -----------------------------------------------------------------------------------------
static void omniParShow(Tab& tab, const std::string& url, const std::string& host)
{
    OmniFxTabState& s = omniFxState(&tab);
    s.failURL = url;
    s.failDomain = OPAR::kErrorDomain;
    s.failCode = 0;
    s.crashDismissed = false;
    tab.loading = false;
    tab.url = url;
    tab.title = "Blocked";
    tab.message = OPAR::blockedBody(host, omniParStore.mode);
    omniShellDirty = true;
}
// First in omniEverydayNavigation's action callback (every frame). True: answered.
static bool omniParPolicy(WKPageRef page, WKNavigationActionRef action, WKFramePolicyListenerRef listener)
{
    omniParLoad();
    if (!omniParStore.active()) return false;
    auto request = adoptWK(WKNavigationActionCopyRequest(action));
    auto url = request ? adoptWK(WKURLRequestCopyURL(request.get())) : WKRetainPtr<WKURLRef>();
    if (!url) return false;
    const std::string target = OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get());
    auto frame = adoptWK(WKNavigationActionCopyTargetFrameInfo(action));
    const bool mainFrame = !frame || WKFrameInfoGetIsMainFrame(frame.get());
    Tab* tab = omniTabForPage(page);
    const OPAR::Decision d = OPAR::decide(omniParStore, omniParSession, target, SDL_GetTicks());
    if (d.verdict == OPAR::kBlock) {
        WKFramePolicyListenerIgnore(listener);
        fprintf(stderr, "OMNI PARENTAL: blocked %s %s (%s)\n", mainFrame ? "page" : "frame", target.substr(0, 200).c_str(), d.why); fflush(stderr);
        if (mainFrame && tab) omniParShow(*tab, target, d.host);
        return true;
    }
    if (!mainFrame || !tab || !omniParStore.safeSearch) return false;
    const std::string method = OmniTest::toStd(adoptWK(WKURLRequestCopyHTTPMethod(request.get())).get());
    if (!method.empty() && method != "GET") return false;
    const std::string safe = OPAR::safeSearchUrl(target);
    if (safe.empty()) return false;
    WKFramePolicyListenerIgnore(listener);
    tab->url = safe;
    tab->loading = true;
    tab->omniPendingLoad = safe;   // loaded by omniEverydayTick (as the https-only upgrade does)
    fprintf(stderr, "OMNI PARENTAL: safe search -> %s\n", safe.substr(0, 200).c_str()); fflush(stderr);
    return true;
}

// --- "This site is blocked" (inside the OMNI_FEATURES_V1 error panel) ----------------------------------------------
static bool omniParErrorShown()
{
    Tab* t = active();
    return t && !t->crashed && omniFxErrorShown() && omniFxState(t).failDomain == OPAR::kErrorDomain;
}
// Chip 0: Cross "Go back" (highlighted). Chip 1: Square "Allow once (PIN)". Chip 2: Triangle "Always allow (PIN)".
static OmniFxErrorLayout omniParErrorGeom()
{
    OmniFxErrorLayout L = omniFxErrorGeom();
    L.chips = 3;
    L.chipX[0] = L.x + 32; L.chipW[0] = 160;
    L.chipX[1] = L.chipX[0] + L.chipW[0] + 12; L.chipW[1] = 236;
    L.chipX[2] = L.chipX[1] + L.chipW[1] + 12; L.chipW[2] = 236;
    return L;
}
static bool omniParErrorDraw()
{
    if (!omniParErrorShown()) return false;
    Tab* t = active();
    const OmniTheme& T = omniTheme();
    const OmniFxTabState& s = omniFxState(t);
    const int py0 = physical(omniPageTop()), py1 = physical(omniPageBottom());
    omniRectPx({ 0, py0, canvas->w, std::max(0, py1 - py0) }, T.bg, 235);   // the blocked page isn't there: dim harder
    const OmniFxErrorLayout L = omniParErrorGeom();
    omniShadow(L.x, L.y, L.w, L.h, omniRadius + 2, 22, 160, 6);
    fillRounded(L.x, L.y, L.w, L.h, omniRadius + 2, T.panel);
    omniDisc(L.x + 50, L.y + 50, 20, omniBad);
    omniIcon(omniIconAlert, L.x + 50, L.y + 50, T.bg);
    omniLabel(OPAR::blockedTitle(), L.x + 88, L.y + 42, omniBodyBold, T.ink, 0, L.w - 120);
    omniLabel(omniShownURL(s.failURL), L.x + 88, L.y + 70, omniSmall, T.inkDim, 0, L.w - 120);
    const auto lines = omniWrap(t->message, omniSmall, L.w - 128, 3);
    for (size_t i = 0; i < lines.size(); ++i) omniLabel(lines[i], L.x + 88, L.y + 108 + int(i) * 26, omniSmall, T.ink);
    const char* labels[3] = { "Go back", "Allow once (PIN)", "Always allow (PIN)" };
    const int faces[3] = { SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_X, SDL_CONTROLLER_BUTTON_Y };   // Cross, Square, Triangle
    for (int i = 0; i < 3; ++i) {
        const bool primary = i == 0;
        const bool hover = pointerX >= L.chipX[i] && pointerX < L.chipX[i] + L.chipW[i] && pointerY >= L.chipY && pointerY < L.chipY + 44;
        fillRounded(L.chipX[i], L.chipY, L.chipW[i], 44, omniRadius, primary ? T.accent : hover ? T.hover : T.key);
        faceIcon(L.chipX[i] + 26, L.chipY + 22, faces[i], playStationIcons);
        omniLabel(labels[i], L.chipX[i] + 48, L.chipY + 22, omniSmallBold, primary ? T.accentInk : T.ink, 0, L.chipW[i] - 56);
    }
    return true;
}
static void omniParGoBack()
{
    Tab* t = active();
    if (!t) return;
    omniFxState(t).failDomain.clear();
    omniFxErrorDismiss();   // nothing was loaded: the previous page is still there
}
static void omniParAllow(bool always)
{
    Tab* t = active();
    if (!t) return;
    const std::string url = omniFxState(t).failURL;
    const OPAR::Target tg = OPAR::classify(url);
    if (tg.kind != OPAR::kWeb) { notice("This address can't be allowed"); return; }
    const std::string host = tg.host;
    WKRetainPtr<WKPageRef> page = t->page;
    const std::string title = always ? "PIN: always allow " + host : "PIN: allow " + host + " for an hour";
    omniParAskPin(title, [page, url, host, always](bool ok) {
        if (!ok) return;
        if (always) {
            std::string key;
            const OPAR::AddResult r = OPAR::addSite(omniParStore.allow, host, &key);
            if (r == OPAR::kFull) { notice("The allowed list is full (500 sites)"); return; }
            omniParWrite();
            notice(key + " is always allowed now (Parental controls > Allowed sites)");
        } else {
            omniParSession.allow(host, SDL_GetTicks());
            notice(host + " is allowed for an hour (until Omni closes at the latest)");
        }
        Tab* tab = omniTabForPage(page.get());
        if (!tab) return;
        omniFxState(tab).failDomain.clear();
        tab->message.clear();
        tab->loading = true;
        auto u = adoptWK(WKURLCreateWithUTF8CString(url.c_str()));
        WKPageLoadURL(tab->page, u.get());
    });
}
static bool omniParErrorButton(int b)
{
    switch (b) {
    case SDL_CONTROLLER_BUTTON_A: case SDL_CONTROLLER_BUTTON_B: omniParGoBack(); return true;
    case SDL_CONTROLLER_BUTTON_X: omniParAllow(false); return true;
    case SDL_CONTROLLER_BUTTON_Y: omniParAllow(true); return true;
    default: return false;   // L1/R1 tabs, Options menu keep working
    }
}
static bool omniParErrorClick(int x, int y)
{
    const OmniFxErrorLayout L = omniParErrorGeom();
    if (y >= L.chipY && y < L.chipY + 44) {
        if (x >= L.chipX[0] && x < L.chipX[0] + L.chipW[0]) { omniParGoBack(); return true; }
        if (x >= L.chipX[1] && x < L.chipX[1] + L.chipW[1]) { omniParAllow(false); return true; }
        if (x >= L.chipX[2] && x < L.chipX[2] + L.chipW[2]) { omniParAllow(true); return true; }
    }
    return y >= omniPageTop() && y < omniPageBottom();
}

// --- the site lists ----------------------------------------------------------------------------------------------------
enum { omniParListAdd = 1, omniParListAddPage, omniParListFirst = 100 };
static std::string omniParEdit;
static int omniParEditList = 0;   // 0 blocked, 1 allowed
static std::set<std::string>& omniParList(int which) { return which ? omniParStore.allow : omniParStore.block; }
static std::string omniParPageHost()
{
    Tab* t = active();
    if (!t || !omniWebURL(t->url)) return std::string();
    const OPAR::Target tg = OPAR::classify(t->url);
    return tg.kind == OPAR::kWeb && !OPAR::isLoopback(tg.host) ? OPAR::entryKey(tg.host) : std::string();
}
static void omniParListBuild(OmniFxPanel& p)
{
    const auto& list = omniParList(p.mode);
    p.title = p.mode ? "Allowed sites" : "Blocked sites";
    p.subtitle = p.mode ? (omniParStore.mode == OPAR::kAllowList ? "Only these sites (and their subdomains) open" : "Always open, even if a blocked site covers them")
                        : (omniParStore.mode == OPAR::kBlockList ? "These sites and their subdomains don't open" : "Not used while \"Allowed sites only\" is on");
    p.corner = std::to_string(list.size()) + " / " + std::to_string(OPAR::kMaxSites);
    OmniFxRow add; add.id = omniParListAdd; add.label = "Add a site..."; p.rows.push_back(add);
    const std::string host = omniParPageHost();
    OmniFxRow page; page.id = omniParListAddPage; page.label = "Add this page's site"; page.value = host.empty() ? std::string("-") : host;
    page.enabled = !host.empty() && !list.count(host); p.rows.push_back(page);
    int i = 0;
    for (const auto& h : list) { OmniFxRow r; r.id = omniParListFirst + i++; r.label = h; r.value = "Remove"; p.rows.push_back(r); }
}
static void omniParListAddKey(int which, const std::string& typed)
{
    std::string key;
    switch (OPAR::addSite(omniParList(which), typed, &key)) {
    case OPAR::kAdded: omniParWrite(); notice("Added " + key); break;
    case OPAR::kAlready: notice(key + " is already on the list"); break;
    case OPAR::kFull: notice("The list is full (500 sites)"); break;
    default: notice("That isn't a site address"); break;
    }
    omniFxRefresh();
}
static bool omniParListInput(OmniFxPanel& p, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (!r.enabled) return true;
    const int which = p.mode;
    if (r.id == omniParListAdd) {
        omniParEdit.clear();
        omniParEditList = which;
        omniKbEdit(&omniParEdit, which ? "Site to allow (example.com)" : "Site to block (example.com)", [](bool ok) {
            if (ok && omniParEdit.find_first_not_of(" \t") != std::string::npos) omniParListAddKey(omniParEditList, omniParEdit);
        });
        return true;
    }
    if (r.id == omniParListAddPage) { omniParListAddKey(which, omniParPageHost()); return true; }
    if (r.id >= omniParListFirst) {
        auto& list = omniParList(which);
        const std::string host = r.label;
        if (list.erase(host)) { omniParWrite(); notice("Removed " + host); }
        return true;
    }
    return true;
}
static void omniParListShow(int which)
{
    OmniFxPanel p;
    p.mode = which; p.w = 760; p.maxVisible = 9;
    p.build = omniParListBuild; p.input = omniParListInput;
    p.faces = { { 0, "Select" }, { 1, "Back" } };
    p.extra = "Subdomains are included: example.com covers www.example.com and m.example.com";
    omniFxPush(std::move(p));
}

// --- the Parental controls panel ---------------------------------------------------------------------------------------
enum { omniParRowOn = 1, omniParRowMode, omniParRowBlocked, omniParRowAllowed, omniParRowSafe, omniParRowPrivate, omniParRowSettings,
       omniParRowPin, omniParRowForgot };
static void omniParPanelBuild(OmniFxPanel& p)
{
    const OPAR::Store& s = omniParStore;
    p.subtitle = s.pin.ok() ? "Changes here always need the PIN" : "Set a PIN first: it protects these settings";
    auto add = [&](int id, const char* label, std::string value, bool stepper, std::string detail = std::string()) {
        OmniFxRow r; r.id = id; r.label = label; r.value = std::move(value); r.stepper = stepper; r.detail = std::move(detail); p.rows.push_back(r);
    };
    auto onOff = [](bool v) { return std::string(v ? "On" : "Off"); };
    add(omniParRowOn, "Parental controls", onOff(s.active()), true);
    add(omniParRowMode, "Sites", OPAR::modeName(s.mode), true);
    add(omniParRowBlocked, "Blocked sites...", std::to_string(s.block.size()), false);
    add(omniParRowAllowed, "Allowed sites...", std::to_string(s.allow.size()), false, s.mode == OPAR::kBlockList ? "exceptions" : "");
    add(omniParRowSafe, "Force safe search", onOff(s.safeSearch), true, OPAR::safeSearchDetail());
    add(omniParRowPrivate, "Lock private tabs", onOff(s.lockPrivate), true, "PIN to open one");
    add(omniParRowSettings, "Lock settings", onOff(s.lockSettings), true, "PIN for Browser and Site settings");
    add(omniParRowPin, s.pin.ok() ? "Change PIN" : "Set a PIN", "", false);
    add(omniParRowForgot, "Forgot the PIN?", "", false);
}
static bool omniParPanelInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    const bool a = b == SDL_CONTROLLER_BUTTON_A, side = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT || b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT;
    OPAR::Store& s = omniParStore;
    auto toggle = [&](bool& v) { if (!a && !side) return false; v = !v; omniParWrite(); return true; };
    switch (r.id) {
    case omniParRowOn:
        if (!a && !side) return false;
        if (!s.pin.ok()) {   // first time: a PIN, then on
            omniParNewPin([](bool ok) { if (!ok) return; omniParStore.enabled = true; omniParWrite(); notice("Parental controls are on"); omniFxRefresh(); });
            return true;
        }
        s.enabled = !s.enabled; omniParWrite();
        notice(s.enabled ? "Parental controls are on" : "Parental controls are off (the PIN is kept)");
        return true;
    case omniParRowMode: if (!a && !side) return false; s.mode = s.mode == OPAR::kAllowList ? OPAR::kBlockList : OPAR::kAllowList; omniParWrite(); return true;
    case omniParRowBlocked: if (!a) return false; omniParListShow(0); return true;
    case omniParRowAllowed: if (!a) return false; omniParListShow(1); return true;
    case omniParRowSafe: return toggle(s.safeSearch);
    case omniParRowPrivate: return toggle(s.lockPrivate);
    case omniParRowSettings: return toggle(s.lockSettings);
    case omniParRowPin:
        if (!a) return false;
        omniParNewPin([](bool ok) { if (ok) notice("PIN saved"); omniFxRefresh(); });
        return true;
    case omniParRowForgot:
        if (!a) return false;
        omniAsk("Forgot the PIN?", OPAR::forgotBody(), "OK", [](bool) {});
        return true;
    }
    return false;
}
static void omniParPanelPush()
{
    OmniFxPanel p;
    p.title = "Parental controls"; p.w = 820; p.maxVisible = 9;
    p.build = omniParPanelBuild; p.input = omniParPanelInput;
    p.faces = { { 0, "Change" }, { 1, "Back" } };
    p.extra = "D-pad \xe2\x97\x80 \xe2\x96\xb6 change";
    omniFxPush(std::move(p));
}
// Browser settings row. Opening the panel always needs the PIN once one is set.
static void omniParOpen()
{
    omniParLoad();
    if (omniParStore.pin.ok() && !omniParUnlocked) {
        omniParAskPin("Enter the PIN for parental controls", [](bool ok) { if (ok) omniParPanelPush(); });
        return;
    }
    omniParPanelPush();
}
static void omniParSettingsRow(OmniFxPanel& p)
{
    omniParLoad();
    OmniFxRow r; r.id = omniParRowId; r.label = "Parental controls..."; r.value = OPAR::summary(omniParStore);
    p.rows.push_back(r);
}
static bool omniParSettingsInput(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    omniParOpen();
    return true;
}

// From omniF3Tick: the PIN gate closes again once every panel is gone; digits never outlive the pad.
static void omniParTick(uint32_t)
{
    if (omniParUnlocked && omniFxStack.empty() && !editing) omniParUnlocked = false;
    if (omniParDigits.empty() && omniParFirst.empty()) return;
    for (const auto& p : omniFxStack) if (p.build == omniParPadBuild) return;
    omniParWipeDigits();
}
'''

DECLS = (
    'static bool omniParPolicy(WKPageRef page, WKNavigationActionRef action, WKFramePolicyListenerRef listener); /* OMNI_PARENTAL_V1 (OmniParentalShell.h): blocked sites (every frame), safe search */\n'
    'enum { omniParGateSettings = 1, omniParGateSite, omniParGatePrivate }; /* OMNI_PARENTAL_V1: PIN gates */\n'
    'static bool omniParGate(int what, void (*again)()); /* OMNI_PARENTAL_V1 */\n'
    'static bool omniParAppBlocked(const std::string& url); /* OMNI_PARENTAL_V1: web app tiles */\n'
    'static bool omniParErrorShown(); /* OMNI_PARENTAL_V1: "This site is blocked" */\n'
    'static bool omniParErrorDraw();\n'
    'static bool omniParErrorButton(int b);\n'
    'static bool omniParErrorClick(int x, int y);\n'
    'constexpr int omniParRowId = 893; /* OMNI_PARENTAL_V1: Browser settings > Parental controls... */\n'
    'static void omniParSettingsRow(OmniFxPanel& p);\n'
    'static bool omniParSettingsInput(int b);\n'
)

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniWebApps.h" // OMNI_WEB_APPS_V1: Open as app, Apps on the start page, apps.json (pure)\n',
         '#include "OmniWebApps.h" // OMNI_WEB_APPS_V1: Open as app, Apps on the start page, apps.json (pure)\n'
         '#include "OmniParental.h" /* OMNI_PARENTAL_V1: Parental controls: host rules, safe search, PIN limiter, parental.txt (pure) */\n'),
        ('static void omniHoCommitted(Tab& tab); // OMNI_HTTPS_ONLY_V1\n',
         'static void omniHoCommitted(Tab& tab); // OMNI_HTTPS_ONLY_V1\n' + DECLS),
        ('        if (omniFxPolicyDownload(page, action, listener)) return; // OMNI_FEATURES_V1: Save link / image\n',
         '        if (omniParPolicy(page, action, listener)) return; /* OMNI_PARENTAL_V1: blocked site (main frame + subframes), safe search */\n'
         '        if (omniFxPolicyDownload(page, action, listener)) return; // OMNI_FEATURES_V1: Save link / image\n'),
        ('static void omniNewPrivateTab()\n{\n',
         'static void omniNewPrivateTab()\n{\n'
         '    if (omniParGate(omniParGatePrivate, omniNewPrivateTab)) return; /* OMNI_PARENTAL_V1: Lock private tabs */\n'),
    ],
    'OmniErrorPage.h': [
        ('    if (omniHoErrorDraw()) return; // OMNI_HTTPS_ONLY_V1\n',
         '    if (omniParErrorDraw()) return; /* OMNI_PARENTAL_V1: This site is blocked */\n'
         '    if (omniHoErrorDraw()) return; // OMNI_HTTPS_ONLY_V1\n'),
        ('    if (omniHoErrorShown()) return omniHoErrorButton(b); // OMNI_HTTPS_ONLY_V1: Continue / Go back\n',
         '    if (omniParErrorShown()) return omniParErrorButton(b); /* OMNI_PARENTAL_V1: Go back / Allow once / Always allow */\n'
         '    if (omniHoErrorShown()) return omniHoErrorButton(b); // OMNI_HTTPS_ONLY_V1: Continue / Go back\n'),
        ('    if (omniHoErrorShown()) return omniHoErrorClick(x, y); // OMNI_HTTPS_ONLY_V1\n',
         '    if (omniParErrorShown()) return omniParErrorClick(x, y); /* OMNI_PARENTAL_V1 */\n'
         '    if (omniHoErrorShown()) return omniHoErrorClick(x, y); // OMNI_HTTPS_ONLY_V1\n'),
    ],
    'OmniBrowserSettings.h': [
        ('    omniHkSettingsRow(p); /* OMNI_HISTORY_KEEP_V1: Keep history */\n',
         '    omniHkSettingsRow(p); /* OMNI_HISTORY_KEEP_V1: Keep history */\n'
         '    omniParSettingsRow(p); /* OMNI_PARENTAL_V1: Parental controls... */\n'),
        ('    if (r.id == omniHkRowId) return omniHkSettingsInput(b); /* OMNI_HISTORY_KEEP_V1 (before the >= 300 rows) */\n',
         '    if (r.id == omniHkRowId) return omniHkSettingsInput(b); /* OMNI_HISTORY_KEEP_V1 (before the >= 300 rows) */\n'
         '    if (r.id == omniParRowId) return omniParSettingsInput(b); /* OMNI_PARENTAL_V1 (before the >= 300 rows) */\n'),
        ('static void omniFxSettingsShow()\n{\n',
         'static void omniFxSettingsShow()\n{\n'
         '    if (omniParGate(omniParGateSettings, omniFxSettingsShow)) return; /* OMNI_PARENTAL_V1: Lock settings */\n'),
    ],
    'OmniQuickMenu.h': [
        ('static void omniFxSiteSettingsShow()\n{\n',
         'static void omniFxSiteSettingsShow()\n{\n'
         '    if (omniParGate(omniParGateSite, omniFxSiteSettingsShow)) return; /* OMNI_PARENTAL_V1: Lock settings */\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniWebAppsShell.h" // OMNI_WEB_APPS_V1 (uses the pinned tabs\' close rule)\n',
         '#include "OmniWebAppsShell.h" // OMNI_WEB_APPS_V1 (uses the pinned tabs\' close rule)\n'
         '#include "OmniParentalShell.h" /* OMNI_PARENTAL_V1 */\n'),
        ('    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n',
         '    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n'
         '    omniParTick(now);   /* OMNI_PARENTAL_V1: the PIN gate closes with the last panel */\n'),
    ],
    'OmniWebAppsShell.h': [
        ('    const OWAP::App app = list[size_t(i)];\n',
         '    const OWAP::App app = list[size_t(i)];\n'
         '    if (omniParAppBlocked(app.url)) return; /* OMNI_PARENTAL_V1: the app\'s site is blocked */\n'),
    ],
}
PREREQ = {
    'OmniBrowser.cpp': 'OMNI_HTTPS_ONLY_V1', 'OmniErrorPage.h': 'OMNI_HTTPS_ONLY_V1', 'OmniBrowserSettings.h': 'OMNI_HISTORY_KEEP_V1',
    'OmniFeatures3.h': 'OMNI_SITE_CLEAR_V1_R2', 'OmniWebAppsShell.h': 'OMNI_WEB_APPS_V1',
}
ROW_ID = 893   # Browser settings row id: unused by every apply_*.py and the tree (checked 2026-11-16)


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def read(name):
    return (root / name).read_bytes().decode('utf-8')


def check(name, edits):
    s = read(name)
    if MARK in s:
        return
    need = PREREQ.get(name)
    if need and need not in s:
        sys.exit('%s: %s missing: apply its script first' % (name, need))
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits):
    p = root / name
    s = read(name)
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


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def main():
    import re
    if MARK not in read('OmniBrowser.cpp'):   # the row id must still be free (another feature may have taken it)
        for name in ('OmniBrowserSettings.h', 'OmniBrowser.cpp', 'OmniFeatures2.h', 'OmniFeatures3.h'):
            if re.search(r'(?<![0-9])%d(?![0-9])' % ROW_ID, cpp_code(read(name))):
                sys.exit('%s: row id %d is already used: refusing' % (name, ROW_ID))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniParental.h', PURE, 'OmniHttpsOnly.h'),
            write_new('OmniParentalShell.h', SHELL, 'OmniHttpsOnlyShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
