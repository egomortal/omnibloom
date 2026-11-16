#!/usr/bin/env python3
"""OMNI_TRANSLATE_PLUS_V1 (2026-11-16): "Translate page" asks first, names the service and what is sent, follows
Omni's language, remembers Always / Never per site and finds the original page again.

What existed (OMNI_TRANSLATE_V1, OmniBrowser.cpp): touchpad / R3 on the shortcuts page / page menu / quick menu
"Translate" (all through omniTranslateToggle) navigated at once to
    https://translate.google.com/translate?sl=auto&tl=en&u=<page URL>
i.e. Google's public website proxy: the page ADDRESS (query string included) goes to Google, Google fetches the page
itself (without the console's cookies / sign-ins), translates its text and serves it from <host>.translate.goog;
links followed there keep going through Google. Target always English; no ask, no notice beyond "Translating with
Google Translate..." after the fact; private tabs the same. Nothing was sent without a press (the "Page is in X"
offer reads document.documentElement.lang in the page, locally). "Show original" was a plain Back.

What the user sees now
  - First translation (and EVERY translation in a private tab) asks, Cancel focused (the shell's own omniAsk modal):
        "Translate this page with Google Translate?"
        "The full address of this page (www.example.jp) is sent to Google Translate, which loads the page itself
         and translates its text into English. Google sees the address, the page and the links you follow on the
         translated copy until you choose Show original. Your sign-ins aren't sent, so pages behind a sign-in may
         not translate. Google's privacy policy applies. Omni asks this once; Site settings > Translate this site:
         Always / Never."      (private tab: "... Private tab: Omni asks every time and remembers nothing.")
    "Translate" goes ahead; the answer is bound to the tab and address that were shown (another tab or a page that
    changed meanwhile is NOT sent: "The page changed: nothing was sent"). Consent is stored as an id
    (kConsentId); changing what is sent means a new id, so everyone is asked again.
  - Never sent at all (notice instead): non-web pages ("This page can't be translated"), addresses with a user name /
    password in them, IP literals, one-label hosts (router, localhost) and local / reserved names (.local, .lan,
    .internal, .home.arpa, .localhost, .test, .onion ...): Google can't reach them and the address itself would leak.
  - Target language = Omni's UI language (OMNI_UI_LANG_V1's omniUlCode: Browser settings > Language, Automatic =
    the PS5 system language); "zh" -> zh-CN (fromSystem() does not keep Traditional vs Simplified), "nb"/"nn" -> no.
    Google's own toolbar follows it too (hl=). The "Page is in X" offer compares the page's lang with the target
    (es-MX page + Spanish target: no offer) instead of "not en".
  - Site settings > "Translate this site": Offer (default: the "Page is in X" notice) / Always (translated as soon as
    it loads; needs the one-time OK: stepping to Always asks it when it was never given) / Never (no offer; the
    touchpad still translates on request). A rule covers subdomains (example.com covers news.example.com). Choices
    made in a private tab last for this session and private tabs only; Always never auto-sends from a private tab
    (it only offers). Value detail: "Google Translate, into <language>".
  - Show original (touchpad again / menus): goes Back when the translated page is still the one opened from the
    original (tidy history, scroll kept), otherwise opens the original address decoded from the translate.goog URL
    (host: "--" -> "-", "-" -> "."; _x_tr_* parameters dropped, _x_tr_sch=http kept as http). After Show original,
    Always does not translate that site again in this tab until Omni restarts or the user translates again.

Storage: /data/omni/translate.txt through omniIoQueue (full rewrite), read once on first use (<= 64 KB):
    omni-translate\t1
    consent\t<kConsentId>        only after the OK in a normal tab
    site\t<host>\t<always|never>  hosts lower case, without "www." and port; <= 500 rows
  Nothing is written in the self-test modes or from private tabs.

Pure part: engine/entry/OmniTranslatePlus.h (no SDL / WebKit): URL parsing, eligibility, host keys, rules, parse /
serialize, target language, translate URL, translate.goog -> original, the decision, texts.
Tested by tools/test_translate_plus.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_translate_plus.cpp -o t && ./t
Shell side: engine/entry/OmniTranslatePlusShell.h (included from OmniFeatures3.h after OmniSiteClearShell.h).

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp   the OmniSiteClear.h include line (apply_site_clear.py's): pure include;
                    the whole OMNI_TRANSLATE_V1 omniTranslateToggle function: becomes a call of omniTpToggle (+ the
                    forward declarations of the shell's two entry points);
                    omniOfferTranslation's evaluate-callback (the call line to its closing "});"): the page is handed
                    to the callback and omniTpPageLang decides (omniLanguageName / omniIsTranslated stay: the menus
                    and the offer use them).
  OmniQuickMenu.h   the omniScSiteInput declaration, the omniScSiteRow call, the omniScSiteRowId input line (all
                    apply_site_clear.py's). Row id 771 (710-760 are taken).
  OmniFeatures3.h   the OmniSiteClearShell.h include line.
Apply AFTER apply_site_clear.py and apply_ui_lang.py (their lines / omniUlCode are used).
usage: apply_translate_plus.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_TRANSLATE_PLUS_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_TRANSLATE_PLUS_V1: the pure part of "Translate page" (no SDL, no WebKit). The shell side is
// OmniTranslatePlusShell.h; the reasons are in tools/apply_translate_plus.py. Tested on the host with g++
// (test_translate_plus.cpp).
#pragma once
#include <cstddef>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace OmniTranslatePlus {

constexpr const char* kFileName = "translate.txt";
constexpr long kMaxFileBytes = 64 * 1024;
constexpr size_t kMaxSites = 500;
constexpr size_t kHostMax = 253;
// What the user agreed to: Google's website proxy gets the page address. A new way of sending (another service,
// page text sent from the console) must use a new id so everyone is asked again.
constexpr const char* kConsentId = "google-proxy-v1";
constexpr const char* kService = "Google Translate";

enum Rule { kOffer = 0, kAlways = 1, kNever = 2 };

struct Store {
    std::string consent;                 // kConsentId once agreed in a normal tab
    std::map<std::string, Rule> sites;   // host key -> kAlways / kNever (kOffer is not stored)
};

inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }
inline bool startsWithNoCase(const std::string& s, const char* p)
{
    size_t i = 0;
    for (; p[i]; ++i) if (i >= s.size() || lower(s[i]) != p[i]) return false;
    return true;
}
inline bool endsWith(const std::string& s, const std::string& tail)
{
    return s.size() >= tail.size() && s.compare(s.size() - tail.size(), tail.size(), tail) == 0;
}

// --- addresses -----------------------------------------------------------------------------------------------------
struct Url {
    bool ok = false, https = false, userinfo = false;
    std::string host;   // lower case, no port, no brackets, no trailing dot
    std::string rest;   // from the first '/', '?' or '#' after the host ("" when none)
};
inline Url parseUrl(const std::string& url)
{
    Url u;
    size_t p;
    if (startsWithNoCase(url, "https://")) { u.https = true; p = 8; }
    else if (startsWithNoCase(url, "http://")) p = 7;
    else return u;
    size_t end = url.find_first_of("/?#", p);
    if (end == std::string::npos) end = url.size();
    std::string auth = url.substr(p, end - p);
    const size_t at = auth.rfind('@');
    if (at != std::string::npos) { u.userinfo = true; auth = auth.substr(at + 1); }
    std::string host;
    if (!auth.empty() && auth[0] == '[') {
        const size_t rb = auth.find(']');
        if (rb == std::string::npos) return u;
        host = auth.substr(1, rb - 1);
    } else host = auth.substr(0, auth.find(':'));
    for (char& c : host) c = lower(c);
    while (!host.empty() && host.back() == '.') host.pop_back();
    if (host.empty() || host.size() > kHostMax) return u;
    u.host = host;
    u.rest = url.substr(end);
    u.ok = true;
    return u;
}
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
inline bool isIPLiteral(const std::string& h) { return isIPv4(h) || h.find(':') != std::string::npos; }
// Hosts Google can't reach, or whose name says they are on this console's own network: never sent.
inline bool localHost(const std::string& h)
{
    if (h.empty() || isIPLiteral(h) || h.find('.') == std::string::npos) return true;   // 10.0.0.1, [::1], router
    static const char* const kTails[] = { ".localhost", ".local", ".localdomain", ".internal", ".lan", ".home",
        ".home.arpa", ".corp", ".intranet", ".private", ".test", ".invalid", ".example", ".onion" };
    for (const char* t : kTails) if (endsWith(h, t)) return true;
    return false;
}
inline bool isTranslatedHost(const std::string& h) { return h.size() > 15 && endsWith(h, ".translate.goog"); }
inline bool isTranslated(const std::string& url) { const Url u = parseUrl(url); return u.ok && isTranslatedHost(u.host); }

enum Why { kOk, kNotWeb, kCredentials, kLocal, kAlreadyTranslated };
inline Why eligibility(const std::string& url)
{
    const Url u = parseUrl(url);
    if (!u.ok) return kNotWeb;
    if (isTranslatedHost(u.host)) return kAlreadyTranslated;
    if (u.userinfo) return kCredentials;
    if (localHost(u.host)) return kLocal;
    if (u.host == "translate.google.com") return kAlreadyTranslated;
    return kOk;
}
// "www.example.com" -> "example.com" (only when something with a dot is left).
inline std::string hostKey(const std::string& host)
{
    if (host.compare(0, 4, "www.") == 0 && host.find('.', 4) != std::string::npos) return host.substr(4);
    return host;
}

// translate.goog -> the original address: host "my--site-example-com" -> "my-site.example.com"; _x_tr_* parameters
// dropped (_x_tr_sch=http: the original was http). "" when it is not a translated address or does not decode.
inline std::string originalOf(const std::string& url)
{
    const Url u = parseUrl(url);
    if (!u.ok || !isTranslatedHost(u.host)) return std::string();
    const std::string enc = u.host.substr(0, u.host.size() - 15);
    std::string host;
    for (size_t i = 0; i < enc.size(); ++i) {
        if (enc[i] != '-') { host += enc[i]; continue; }
        if (i + 1 < enc.size() && enc[i + 1] == '-') { host += '-'; ++i; }
        else host += '.';
    }
    if (host.empty() || host.front() == '.' || host.back() == '.' || host.find("..") != std::string::npos || host.find('.') == std::string::npos)
        return std::string();
    std::string path = u.rest, query, frag;
    const size_t h = path.find('#');
    if (h != std::string::npos) { frag = path.substr(h); path.resize(h); }
    const size_t q = path.find('?');
    if (q != std::string::npos) { query = path.substr(q + 1); path.resize(q); }
    bool http = false;
    std::string kept;
    size_t i = 0;
    while (i <= query.size() && !query.empty()) {
        size_t e = query.find('&', i);
        if (e == std::string::npos) e = query.size();
        const std::string part = query.substr(i, e - i);
        if (part.compare(0, 6, "_x_tr_") == 0) { if (part == "_x_tr_sch=http") http = true; }
        else if (!part.empty()) kept += (kept.empty() ? "" : "&") + part;
        i = e + 1;
    }
    return std::string(http ? "http://" : "https://") + host + (path.empty() ? "/" : path) + (kept.empty() ? "" : "?" + kept) + frag;
}
// The site key of a page: its host key, or the original's for a translated page; "" when it can't be translated.
inline std::string siteKey(const std::string& url)
{
    const std::string original = isTranslated(url) ? originalOf(url) : url;
    if (original.empty() || eligibility(original) != kOk) return std::string();
    return hostKey(parseUrl(original).host);
}
// Same document: scheme + host + path + query (no fragment; "" path = "/").
inline std::string documentKey(const std::string& url)
{
    const Url u = parseUrl(url);
    if (!u.ok) return url;
    std::string rest = u.rest.substr(0, u.rest.find('#'));
    if (rest.empty() || rest[0] != '/') rest = "/" + rest;
    return std::string(u.https ? "https://" : "http://") + u.host + rest;
}
inline bool sameDocument(const std::string& a, const std::string& b) { return !a.empty() && documentKey(a) == documentKey(b); }

// --- rules ---------------------------------------------------------------------------------------------------------
inline bool validKey(const std::string& k)
{
    if (k.empty() || k.size() > kHostMax || localHost(k)) return false;
    for (char c : k) if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-')) return false;
    return true;
}
// Exact host key first, then its parent domains (a rule for example.com covers news.example.com).
inline Rule siteRule(const std::map<std::string, Rule>& sites, const std::string& key)
{
    std::string h = key;
    while (h.find('.') != std::string::npos) {
        const auto it = sites.find(h);
        if (it != sites.end()) return it->second;
        h = h.substr(h.find('.') + 1);
    }
    return kOffer;
}
// false: the list is full (a new row would pass kMaxSites) or the key is not a site.
inline bool setSite(std::map<std::string, Rule>& sites, const std::string& key, Rule r)
{
    if (!validKey(key)) return false;
    if (r == kOffer) { sites.erase(key); return true; }
    if (!sites.count(key) && sites.size() >= kMaxSites) return false;
    sites[key] = r;
    return true;
}
inline Rule cycle(Rule r, int dir)
{
    const int n = 3;
    return Rule(((int(r) + (dir < 0 ? -1 : 1)) % n + n) % n);
}
inline const char* ruleWord(Rule r) { return r == kAlways ? "always" : r == kNever ? "never" : "offer"; }
inline const char* ruleName(Rule r) { return r == kAlways ? "Always" : r == kNever ? "Never" : "Offer"; }

inline Store parse(const std::string& text)
{
    Store s;
    size_t i = 0;
    while (i < text.size()) {
        size_t e = text.find('\n', i);
        if (e == std::string::npos) e = text.size();
        std::string line = text.substr(i, e - i);
        i = e + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        std::vector<std::string> f;
        size_t a = 0;
        while (true) {
            const size_t t = line.find('\t', a);
            f.push_back(line.substr(a, t == std::string::npos ? std::string::npos : t - a));
            if (t == std::string::npos) break;
            a = t + 1;
        }
        if (f.size() == 2 && f[0] == "consent") { if (f[1] == kConsentId) s.consent = f[1]; }   // an older id: ask again
        else if (f.size() == 3 && f[0] == "site") {
            const Rule r = f[2] == "always" ? kAlways : f[2] == "never" ? kNever : kOffer;
            if (r != kOffer) setSite(s.sites, f[1], r);
        }
    }
    return s;
}
inline std::string serialize(const Store& s)
{
    std::string out = "omni-translate\t1\n";
    if (!s.consent.empty()) out += "consent\t" + s.consent + "\n";
    for (const auto& [k, r] : s.sites) out += "site\t" + k + "\t" + ruleWord(r) + "\n";
    return out;
}

// --- languages -------------------------------------------------------------------------------------------------------
// "pt_BR" -> "pt", "ZH-Hant" -> "zh"; "" when it is not 2-3 letters.
inline std::string primary(const std::string& tag)
{
    std::string c;
    for (char ch : tag) {
        if (ch == '-' || ch == '_') break;
        ch = lower(ch);
        if (ch < 'a' || ch > 'z') return std::string();
        c += ch;
    }
    return c.size() == 2 || c.size() == 3 ? c : std::string();
}
inline std::string family(const std::string& p)   // languages Google treats as one
{
    if (p == "nb" || p == "nn") return "no";
    if (p == "iw") return "he";
    if (p == "in") return "id";
    return p;
}
// Omni's UI language code -> Google's tl= code. Anything unusable -> "en".
inline std::string targetLang(const std::string& uiCode)
{
    const std::string p = family(primary(uiCode));
    if (p.empty()) return "en";
    if (p == "zh") return "zh-CN";
    return p;
}
// The page's lang attribute differs from the target (an empty / unusable lang never offers).
inline bool foreign(const std::string& pageLang, const std::string& target)
{
    const std::string p = family(primary(pageLang));
    return !p.empty() && p != family(primary(target));
}
inline const char* languageName(const std::string& code)
{
    static const std::pair<const char*, const char*> kNames[] = {
        {"en","English"},{"es","Spanish"},{"fr","French"},{"de","German"},{"pt","Portuguese"},{"it","Italian"},
        {"nl","Dutch"},{"ja","Japanese"},{"ko","Korean"},{"zh","Chinese"},{"ru","Russian"},{"pl","Polish"},
        {"tr","Turkish"},{"ar","Arabic"},{"fi","Finnish"},{"sv","Swedish"},{"da","Danish"},{"no","Norwegian"},
        {"cs","Czech"},{"hu","Hungarian"},{"el","Greek"},{"ro","Romanian"},{"th","Thai"},{"vi","Vietnamese"},
        {"id","Indonesian"},{"uk","Ukrainian"},{"hi","Hindi"},{"he","Hebrew"}};
    const std::string p = family(primary(code));
    for (const auto& [c, n] : kNames) if (p == c) return n;
    return nullptr;
}
inline std::string targetName(const std::string& target)
{
    const char* n = languageName(target);
    return n ? std::string(n) : target;
}

// Percent-encodes everything but unreserved characters (RFC 3986), as the old code did.
inline std::string encode(const std::string& s)
{
    static const char* const hex = "0123456789ABCDEF";
    std::string out;
    for (unsigned char c : s) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' || c == '~') out += char(c);
        else { out += '%'; out += hex[c >> 4]; out += hex[c & 15]; }
    }
    return out;
}
inline std::string translateUrl(const std::string& url, const std::string& target)
{
    return "https://translate.google.com/translate?sl=auto&tl=" + target + "&hl=" + target + "&u=" + encode(url);
}

// --- the decision ----------------------------------------------------------------------------------------------------
enum Action { kNothing, kShowOriginal, kRefuse, kAskConsent, kTranslate, kOfferNotice };
struct Input {
    bool manual = false;       // a press (touchpad, R3, menus); false: a page finished loading
    bool translated = false;   // the tab shows a translate.goog page
    bool eligible = false;     // eligibility() == kOk
    bool privateTab = false;
    bool consent = false;      // Store::consent == kConsentId
    bool foreign = false;      // the page's lang differs from the target (loads only)
    bool suppressed = false;   // Show original was chosen for this site in this tab
    Rule rule = kOffer;
};
// Nothing is sent without a press or a saved Always + the saved OK; a private tab asks on every press and never
// sends by itself.
inline Action decide(const Input& in)
{
    if (in.translated) return in.manual ? kShowOriginal : kNothing;
    if (!in.eligible) return in.manual ? kRefuse : kNothing;
    if (in.manual) return in.privateTab || !in.consent ? kAskConsent : kTranslate;
    if (!in.foreign || in.rule == kNever || in.suppressed) return kNothing;
    if (in.rule == kAlways && in.consent && !in.privateTab) return kTranslate;
    return kOfferNotice;
}

// --- texts -----------------------------------------------------------------------------------------------------------
inline std::string refuseNotice(Why w)
{
    switch (w) {
    case kCredentials: return "This address has a sign-in in it: it isn't sent to Google Translate";
    case kLocal: return "Pages on your own network aren't sent to Google Translate";
    default: return "This page can't be translated";
    }
}
inline std::string askTitle() { return "Translate this page with Google Translate?"; }
inline std::string askBody(const std::string& host, const std::string& target, bool privateTab)
{
    std::string s = "The full address of this page (" + host + ") is sent to Google Translate, which loads the page itself and "
        "translates its text into " + targetName(target) + ". Google sees the address, the page and the links you follow on "
        "the translated copy until you choose Show original. Your sign-ins aren't sent, so pages behind a sign-in may "
        "not translate. Google's privacy policy applies.";
    s += privateTab ? " Private tab: Omni asks every time and remembers nothing."
                    : " Omni asks this once; Site settings > Translate this site: Always / Never.";
    return s;
}
inline const char* okLabel() { return "Translate"; }
inline std::string startNotice() { return "Translating with Google Translate..."; }
inline std::string staleNotice() { return "The page changed: nothing was sent to Google Translate"; }
inline std::string originalNotice() { return "Showing the original page"; }
inline std::string siteDetail(const std::string& target) { return std::string(kService) + ", into " + targetName(target); }
inline std::string siteNotice(const std::string& key, Rule r, bool privateTab, bool full)
{
    if (full) return "Too many sites saved: choice not saved";
    std::string s = key + ": ";
    s += r == kAlways ? "translated as soon as it loads" : r == kNever ? "no translate offers (a press still translates)"
                      : "translation offered when the page is in another language";
    if (privateTab) s += r == kAlways ? " (private tab: offered only, this session)" : " (this private session only)";
    return s;
}

} // namespace OmniTranslatePlus
'''

SHELL = r'''// OMNI_TRANSLATE_PLUS_V1: "Translate page" (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's
// anonymous namespace, after OmniSiteClearShell.h). The pure part is OmniTranslatePlus.h; the reasons are in
// tools/apply_translate_plus.py. Main thread only; the file is written by omniIoQueue.
#pragma once

namespace OTP = OmniTranslatePlus;
static OTP::Store omniTpStore;
static bool omniTpLoaded = false;
static std::map<std::string, OTP::Rule> omniTpSession;   // site choices made in private tabs: this run, private tabs only
static std::map<WKPageRef, std::string> omniTpFrom;      // page -> the address it last translated
static std::map<WKPageRef, std::string> omniTpOriginal;  // page -> site key shown original again (no Always there)

static void omniTpLoad()
{
    if (omniTpLoaded) return;
    omniTpLoaded = true;
    FILE* f = fopen(omniData(OTP::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) < OTP::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    omniTpStore = OTP::parse(text);
}
static void omniTpWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OTP::kFileName), OTP::serialize(omniTpStore), false);
}
// Omni's UI language (Browser settings > Language; Automatic = the PS5 system language) as Google's tl= code.
static std::string omniTpTarget()
{
    if (!omniUlLoaded) omniUlLoad();
    return OTP::targetLang(omniUlCode);
}
static bool omniTpConsented() { omniTpLoad(); return omniTpStore.consent == OTP::kConsentId; }
static OTP::Rule omniTpRule(const std::string& key, bool priv)
{
    if (key.empty()) return OTP::kOffer;
    omniTpLoad();
    if (priv) { const auto it = omniTpSession.find(key); if (it != omniTpSession.end()) return it->second; }
    return OTP::siteRule(omniTpStore.sites, key);
}
static void omniTpPrune()   // closed tabs' pages
{
    for (auto* m : { &omniTpFrom, &omniTpOriginal })
        for (auto it = m->begin(); it != m->end();) it = omniTabForPage(it->first) ? std::next(it) : m->erase(it);
}
// t is the active tab showing `url` (checked by the callers).
static void omniTpGo(Tab* t, const std::string& url)
{
    WKPageRef page = t->page;
    omniTpFrom[page] = url;
    omniTpOriginal.erase(page);
    notice(OTP::startNotice());
    navigate(OTP::translateUrl(url, omniTpTarget()));
}
static void omniTpShowOriginal(Tab* t)
{
    WKPageRef page = t->page;
    const std::string original = OTP::originalOf(t->url);
    const auto from = omniTpFrom.find(page);
    const bool direct = from != omniTpFrom.end() && OTP::sameDocument(from->second, original);
    const std::string key = OTP::siteKey(t->url);
    if (!key.empty()) omniTpOriginal[page] = key;
    notice(OTP::originalNotice());
    if ((direct || original.empty()) && WKPageCanGoBack(page)) { WKPageGoBack(page); return; }
    if (!original.empty()) navigate(original);
}
// The one-time OK (every time in a private tab). The answer only counts for the tab and address it was shown for.
static void omniTpAsk(Tab* t, const std::string& url, std::function<void()> then)
{
    const bool priv = t->omniPrivate;
    WKRetainPtr<WKPageRef> page = t->page;
    omniAsk(OTP::askTitle(), OTP::askBody(OTP::parseUrl(url).host, omniTpTarget(), priv), OTP::okLabel(), [page, url, priv, then](bool ok) {
        if (!ok) return;
        Tab* now = active();
        if (!now || omniTabForPage(page.get()) != now || now->url != url) { notice(OTP::staleNotice()); return; }
        if (!priv) { omniTpLoad(); omniTpStore.consent = OTP::kConsentId; omniTpWrite(); }
        then();
    });
}

// Touchpad / R3 on the shortcuts page / menus (omniTranslateToggle).
static void omniTpToggle()
{
    Tab* t = active();
    if (!t || t->url.empty()) return;
    const std::string url = t->url;
    const OTP::Why why = OTP::eligibility(url);
    OTP::Input in;
    in.manual = true;
    in.translated = OTP::isTranslated(url);
    in.eligible = why == OTP::kOk;
    in.privateTab = t->omniPrivate;
    in.consent = omniTpConsented();
    switch (OTP::decide(in)) {
    case OTP::kShowOriginal: omniTpShowOriginal(t); break;
    case OTP::kRefuse: notice(OTP::refuseNotice(why)); break;
    case OTP::kAskConsent: omniTpAsk(t, url, [url]() { if (Tab* a = active()) omniTpGo(a, url); }); break;
    case OTP::kTranslate: omniTpGo(t, url); break;
    default: break;
    }
}
// A page of the active tab finished loading; lang is its <html lang> (read in the page, nothing sent).
static void omniTpPageLang(WKPageRef page, const std::string& lang)
{
    Tab* t = active();
    if (!t || omniTabForPage(page) != t) return;
    omniTpPrune();
    const std::string url = t->url;
    const std::string target = omniTpTarget();
    const std::string key = OTP::siteKey(url);
    OTP::Input in;
    in.translated = OTP::isTranslated(url);
    in.eligible = OTP::eligibility(url) == OTP::kOk;
    in.privateTab = t->omniPrivate;
    in.consent = omniTpConsented();
    in.foreign = OTP::foreign(lang, target);
    in.rule = omniTpRule(key, t->omniPrivate);
    const auto o = omniTpOriginal.find(page);
    in.suppressed = o != omniTpOriginal.end() && o->second == key;
    switch (OTP::decide(in)) {
    case OTP::kTranslate: omniTpGo(t, url); break;
    case OTP::kOfferNotice: {
        const std::string p = OTP::primary(lang);
        const char* name = omniLanguageName(p);
        notice(std::string("Page is in ") + (name ? name : p.c_str()) + ": touchpad (or R3 on the shortcuts page) translates it");
        break;
    }
    default: break;
    }
}

// --- Site settings > Translate this site ---------------------------------------------------------------------------
static std::string omniTpSiteKey() { return active() ? OTP::siteKey(active()->url) : std::string(); }
static void omniTpSiteRow(OmniFxPanel& p, const std::string&)
{
    const std::string key = omniTpSiteKey();
    OmniFxRow r; r.id = omniTpSiteRowId; r.label = "Translate this site"; r.stepper = true; r.enabled = !key.empty();
    r.value = key.empty() ? std::string("-") : OTP::ruleName(omniTpRule(key, active() && active()->omniPrivate));
    if (!key.empty()) r.detail = OTP::siteDetail(omniTpTarget());
    p.rows.push_back(r);
}
static void omniTpSetSite(const std::string& key, OTP::Rule next, bool priv)
{
    omniTpLoad();
    bool ok = true;
    if (priv) {   // a session row exists only while the private choice differs from the saved one
        if (next == OTP::siteRule(omniTpStore.sites, key)) omniTpSession.erase(key);
        else omniTpSession[key] = next;
    } else {
        ok = OTP::setSite(omniTpStore.sites, key, next);
        if (ok) omniTpWrite();
    }
    notice(OTP::siteNotice(key, next, priv, !ok));
}
static bool omniTpSiteInput(const OmniFxRow& r, int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT;
    if (b != SDL_CONTROLLER_BUTTON_A && !left && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    Tab* t = active();
    const std::string key = omniTpSiteKey();
    if (!r.enabled || key.empty() || !t) return true;
    const bool priv = t->omniPrivate;
    const OTP::Rule next = OTP::cycle(omniTpRule(key, priv), left ? -1 : 1);
    // Always sends by itself from then on: the one-time OK comes first (a private tab only ever offers)
    if (next == OTP::kAlways && !priv && !omniTpConsented()) {
        omniTpAsk(t, t->url, [key, priv]() { omniTpSetSite(key, OTP::kAlways, priv); });
        return true;
    }
    omniTpSetSite(key, next, priv);
    return true;
}
'''

TOGGLE_OLD = (
    'static void omniTranslateToggle()\n'
    '{\n'
    '    if (!active() || active()->url.empty()) return;\n'
    '    const std::string url = active()->url;\n'
    '    if (omniIsTranslated(url)) { if (WKPageCanGoBack(active()->page)) WKPageGoBack(active()->page); return; }\n'
    '    if (url.rfind("http://", 0) != 0 && url.rfind("https://", 0) != 0) { notice("This page can\'t be translated"); return; }\n'
    '    std::string encoded;\n'
    '    for (unsigned char c : url) {\n'
    '        if ((c >= \'a\' && c <= \'z\') || (c >= \'A\' && c <= \'Z\') || (c >= \'0\' && c <= \'9\') || c == \'-\' || c == \'_\' || c == \'.\' || c == \'~\') encoded += char(c);\n'
    '        else { char hex[4]; snprintf(hex, sizeof(hex), "%%%02X", c); encoded += hex; }\n'
    '    }\n'
    '    notice("Translating with Google Translate...");\n'
    '    navigate("https://translate.google.com/translate?sl=auto&tl=en&u=" + encoded);\n'
    '}\n')
TOGGLE_NEW = (
    'static void omniTpToggle(); // OMNI_TRANSLATE_PLUS_V1 (OmniTranslatePlusShell.h): asks first, target language, Always / Never\n'
    'static void omniTpPageLang(WKPageRef page, const std::string& lang); // OMNI_TRANSLATE_PLUS_V1\n'
    'static void omniTranslateToggle() { omniTpToggle(); } // OMNI_TRANSLATE_PLUS_V1 (was: straight to Google Translate, English)\n')

OFFER_OLD = (
    '    WKPageEvaluateJavaScriptInMainFrame(page, script.get(), nullptr, [](WKTypeRef result, WKErrorRef error, void*) {\n'
    '        std::string lang;\n'
    '        if (!error && result && WKGetTypeID(result) == WKStringGetTypeID()) lang = OmniTest::toStd(static_cast<WKStringRef>(result));\n'
    '        lang = lang.substr(0, lang.find_first_of("-_"));\n'
    '        if (lang.empty() || lang == "en" || !active() || omniIsTranslated(active()->url)) return;\n'
    '        const char* name = omniLanguageName(lang);\n'
    '        notice(std::string("Page is in ") + (name ? name : lang.c_str()) + ": touchpad (or R3 on the shortcuts page) translates it");\n'
    '    });\n')
OFFER_NEW = (
    '    void* ctx = const_cast<void*>(static_cast<const void*>(page)); // OMNI_TRANSLATE_PLUS_V1: compared only, never used after a close\n'
    '    WKPageEvaluateJavaScriptInMainFrame(page, script.get(), ctx, [](WKTypeRef result, WKErrorRef error, void* pageCtx) {\n'
    '        std::string lang;\n'
    '        if (!error && result && WKGetTypeID(result) == WKStringGetTypeID()) lang = OmniTest::toStd(static_cast<WKStringRef>(result));\n'
    '        omniTpPageLang(static_cast<WKPageRef>(pageCtx), lang); // OMNI_TRANSLATE_PLUS_V1: offer / Always / Never against Omni\'s language\n'
    '    });\n')

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSiteClear.h" // OMNI_SITE_CLEAR_V1: Clear data for this site (pure)\n',
         '#include "OmniSiteClear.h" // OMNI_SITE_CLEAR_V1: Clear data for this site (pure)\n'
         '#include "OmniTranslatePlus.h" // OMNI_TRANSLATE_PLUS_V1: Translate page: consent, per-site choice, target language (pure)\n'),
        (TOGGLE_OLD, TOGGLE_NEW),
        (OFFER_OLD, OFFER_NEW),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniScSiteInput(const OmniFxRow& r, int b);\n',
         'static bool omniScSiteInput(const OmniFxRow& r, int b);\n'
         'constexpr int omniTpSiteRowId = 771; // OMNI_TRANSLATE_PLUS_V1 (OmniTranslatePlusShell.h)\n'
         'static void omniTpSiteRow(OmniFxPanel& p, const std::string& host);\n'
         'static bool omniTpSiteInput(const OmniFxRow& r, int b);\n'),
        ('    omniScSiteRow(p, host); // OMNI_SITE_CLEAR_V1: Clear data for this site\n',
         '    omniTpSiteRow(p, host); // OMNI_TRANSLATE_PLUS_V1: Translate this site: Offer / Always / Never\n'
         '    omniScSiteRow(p, host); // OMNI_SITE_CLEAR_V1: Clear data for this site\n'),
        ('    if (r.id == omniScSiteRowId) return omniScSiteInput(r, b); // OMNI_SITE_CLEAR_V1 (handles its disabled state)\n',
         '    if (r.id == omniTpSiteRowId) return omniTpSiteInput(r, b); // OMNI_TRANSLATE_PLUS_V1 (handles its disabled state)\n'
         '    if (r.id == omniScSiteRowId) return omniScSiteInput(r, b); // OMNI_SITE_CLEAR_V1 (handles its disabled state)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n',
         '#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n'
         '#include "OmniTranslatePlusShell.h" // OMNI_TRANSLATE_PLUS_V1\n'),
    ],
}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits, mark=MARK):
    s = (root / name).read_bytes().decode('utf-8')
    if mark in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits, mark=MARK):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if mark in s:
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
    if 'OMNI_UI_LANG_V1' not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        sys.exit('OmniBrowser.cpp: OMNI_UI_LANG_V1 missing: apply_ui_lang.py first (omniUlCode is the target language)')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniTranslatePlus.h', PURE, 'OmniSiteClear.h'),
            write_new('OmniTranslatePlusShell.h', SHELL, 'OmniSiteClearShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
