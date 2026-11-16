// OMNI_PAGE_INFO_V1: the pure part of "Page info" (no SDL, no WebKit): connection classification (padlock state),
// the one page script (language, words, cookies / storage the page can read, navigation timing) and its answer,
// reading time, number / time / size formatting and every row text. The shell side is OmniPageInfoShell.h; the
// reasons (what is real, what this build can't tell) are in tools/apply_page_info.py. Tested on the host with g++
// (tools/test_page_info.cpp; it also writes the script to argv[1] so node can check and run it:
// tools/test_page_info_js.cjs).
#pragma once
#include <cstddef>
#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace OmniPageInfo {

constexpr const char* kAnswerTag = "omni-page-info";
constexpr size_t kTextMax = 3000000;   // characters of page text the script counts (bigger pages: the first 3 M)
constexpr int kWordsPerMinute = 230;   // reading speed for space-separated scripts
constexpr int kCjkPerMinute = 500;     // characters per minute for Chinese / Japanese / Korean text

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

// --- connection ----------------------------------------------------------------------------------------------------
enum Kind { kNone = 0, kSecure, kNotSecure, kLocal, kInternal, kFile, kOther };
struct Connection {
    Kind kind = kNone;
    std::string scheme;   // lower case, without ":"
    std::string host;     // lower case, IPv6 without brackets, no trailing dot ("" when the address has none)
};

// The host of an http(s) / ws(s) / ftp style URL: lower case, user info / port / brackets gone, no trailing dots.
inline std::string hostOf(const std::string& url)
{
    const size_t s = url.find("://");
    if (s == std::string::npos) return std::string();
    size_t p = s + 3;
    size_t end = url.find_first_of("/?#", p);
    if (end == std::string::npos) end = url.size();
    const size_t at = url.rfind('@', end ? end - 1 : 0);
    if (at != std::string::npos && at >= p && at < end) p = at + 1;
    std::string h;
    if (p < end && url[p] == '[') {
        const size_t close = url.find(']', p);
        if (close == std::string::npos || close >= end) return std::string();
        h = url.substr(p + 1, close - p - 1);
    } else {
        const size_t colon = url.find(':', p);
        h = url.substr(p, (colon != std::string::npos && colon < end ? colon : end) - p);
    }
    for (auto& c : h) c = lower(c);
    while (!h.empty() && h.back() == '.') h.pop_back();
    return h;
}

inline bool ipv4(const std::string& h, int out[4])
{
    int parts = 0, digits = 0, value = 0;
    for (size_t i = 0; i <= h.size(); ++i) {
        if (i == h.size() || h[i] == '.') {
            if (!digits || value > 255 || parts >= 4) return false;
            out[parts++] = value; digits = 0; value = 0;
            continue;
        }
        if (h[i] < '0' || h[i] > '9' || ++digits > 3) return false;
        value = value * 10 + (h[i] - '0');
    }
    return parts == 4;
}
// Hosts that never leave the home network or the console: loopback, private / link-local IPv4 ranges, IPv6
// loopback / unique-local / link-local, "localhost" (and *.localhost), mDNS names (*.local), one-label names.
inline bool localHost(const std::string& h)
{
    if (h.empty()) return false;
    int a[4];
    if (ipv4(h, a)) {
        return a[0] == 127 || a[0] == 10 || a[0] == 0 || (a[0] == 192 && a[1] == 168) || (a[0] == 172 && a[1] >= 16 && a[1] <= 31)
            || (a[0] == 169 && a[1] == 254);
    }
    if (h.find(':') != std::string::npos) {   // IPv6
        if (h == "::1" || h == "::") return true;
        const std::string first = h.substr(0, h.find(':'));
        if (first.size() == 4 && (first.compare(0, 2, "fc") == 0 || first.compare(0, 2, "fd") == 0)) return true;   // fc00::/7
        if (first.size() == 4 && first.compare(0, 3, "fe8") == 0) return true;                                        // fe80::/10 (fe80-fe8f)
        if (first.size() == 4 && (first.compare(0, 3, "fe9") == 0 || first.compare(0, 3, "fea") == 0 || first.compare(0, 3, "feb") == 0)) return true;
        if (h.compare(0, 7, "::ffff:") == 0 && ipv4(h.substr(7), a)) return localHost(h.substr(7));
        return false;
    }
    if (h == "localhost" || endsWith(h, ".localhost") || endsWith(h, ".local") || endsWith(h, ".home.arpa")) return true;
    return h.find('.') == std::string::npos;   // an intranet name ("router", "nas")
}

inline Connection classify(const std::string& url)
{
    Connection c;
    const size_t colon = url.find(':');
    if (url.empty() || colon == std::string::npos || colon == 0 || colon > 16) return c;
    for (size_t i = 0; i < colon; ++i) {
        const char ch = lower(url[i]);
        if (!((ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') || ch == '+' || ch == '-' || ch == '.')) return c;
        c.scheme += ch;
    }
    c.host = hostOf(url);
    if (c.scheme == "https") c.kind = kSecure;
    else if (c.scheme == "http") c.kind = localHost(c.host) ? kLocal : kNotSecure;
    else if (c.scheme == "omni" || c.scheme == "about" || c.scheme == "omnibloom") c.kind = kInternal;
    else if (c.scheme == "file") c.kind = kFile;
    else c.kind = kOther;   // data:, blob:, javascript:, view-source:, ...
    if (c.kind == kSecure && c.host.empty()) c.kind = kOther;
    if ((c.kind == kNotSecure || c.kind == kLocal) && c.host.empty()) c.kind = kOther;
    return c;
}
inline bool padlock(const Connection& c) { return c.kind == kSecure; }   // the address bar draws the lock exactly then
inline std::string connectionValue(const Connection& c)
{
    switch (c.kind) {
    case kSecure: return "Secure (https)";
    case kNotSecure: return "Not secure (http)";
    case kLocal: return "Local network (http)";
    case kInternal: return "Omni page";
    case kFile: return "File on the console";
    case kOther: return c.scheme.empty() ? std::string("No connection") : "No connection (" + c.scheme + ":)";
    default: return "No page";
    }
}
constexpr const char* kCertificateText = "Certificate details aren't available in this build";
inline std::string connectionDetail(const Connection& c)
{
    switch (c.kind) {
    case kSecure: return std::string("Encrypted to ") + c.host + ". " + kCertificateText;
    case kNotSecure: return "Not encrypted: what you send to " + c.host + " can be read on the way";
    case kLocal: return c.host + " is on your home network or this console. Not encrypted, but it stays local";
    case kInternal: return "Built into Omni: nothing is loaded from the internet";
    case kFile: return "Read from the console's storage";
    case kOther: return "This address isn't loaded from a server";
    default: return std::string();
    }
}

// --- the page script -------------------------------------------------------------------------------------------------
// One synchronous, read-only script (WKPageEvaluateJavaScriptInMainFrame). It answers
//   "omni-page-info;lang=..;w=..;c=..;ck=..;ls=..;ss=..;ld=..;dcl=..;fb=..;nt=..;tb=.."
// lang: the root element's lang attribute ([A-Za-z0-9_-] only, 24 at most); w: words; c: CJK characters; ck: cookies
// the page can read (document.cookie; HttpOnly ones are hidden from pages); ls / ss: localStorage / sessionStorage
// items; ld: load event end, dcl: DOMContentLoaded end, fb: first byte (responseStart), all ms since the navigation
// started; nt: 0 navigate, 1 reload, 2 back / forward, 3 prerender; tb: bytes transferred for the document
// (0: from the cache). -1: not available. Text: the longest article / main element when it holds at least a quarter
// of the body's text, else the body (headers, menus and footers then count too: an estimate).
inline std::string script()
{
    std::string s = "(function(){var o={lang:'',w:0,c:0,ck:-1,ls:-1,ss:-1,ld:-1,dcl:-1,fb:-1,nt:-1,tb:-1},d=document,max=";
    s += std::to_string(kTextMax);
    s += R"JS(;
try{o.lang=String((d.documentElement&&d.documentElement.getAttribute('lang'))||'').replace(/[^A-Za-z0-9_-]/g,'').slice(0,24);}catch(e){}
try{var body=d.body,bt=body?String(body.innerText||body.textContent||''):'',t=bt,best='';
var list=d.querySelectorAll?d.querySelectorAll('article,main,[role=main]'):[];
for(var i=0;i<list.length&&i<50;i++){var x=String(list[i].innerText||list[i].textContent||'');if(x.length>best.length)best=x;}
if(best.length>=bt.length/4&&best.length>0)t=best;
if(t.length>max)t=t.slice(0,max);
var cj=/[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]/g,n=0;while(cj.exec(t))n++;o.c=n;
var re=/[^\s\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]+/g,m,w=0;while((m=re.exec(t))){if(/[A-Za-z0-9\u00c0-\u024f\u0370-\u03ff\u0400-\u04ff\u0590-\u06ff\u0900-\u097f\u0e00-\u0e7f]/.test(m[0]))w++;}o.w=w;}catch(e){}
try{var cs=String(d.cookie||'');o.ck=0;var parts=cs.split(';');for(var k=0;k<parts.length;k++)if(parts[k].replace(/^\s+|\s+$/g,'').length>0)o.ck++;}catch(e){o.ck=-1;}
try{o.ls=window.localStorage.length;}catch(e){o.ls=-1;}
try{o.ss=window.sessionStorage.length;}catch(e){o.ss=-1;}
try{var p=window.performance,r=function(v){return typeof v==='number'&&isFinite(v)&&v>0?Math.round(v):-1;};
var nv=p&&typeof p.getEntriesByType==='function'?p.getEntriesByType('navigation'):null,e0=nv&&nv.length?nv[0]:null;
if(e0){o.ld=r(e0.loadEventEnd);o.dcl=r(e0.domContentLoadedEventEnd);o.fb=r(e0.responseStart);
var ty={navigate:0,reload:1,back_forward:2,prerender:3}[e0.type];o.nt=typeof ty==='number'?ty:-1;
o.tb=typeof e0.transferSize==='number'&&isFinite(e0.transferSize)&&e0.transferSize>=0?Math.round(e0.transferSize):-1;}
else if(p&&p.timing&&p.timing.navigationStart>0){var tm=p.timing,st=tm.navigationStart;
o.ld=tm.loadEventEnd>0?tm.loadEventEnd-st:-1;o.dcl=tm.domContentLoadedEventEnd>0?tm.domContentLoadedEventEnd-st:-1;o.fb=tm.responseStart>0?tm.responseStart-st:-1;
if(p.navigation&&typeof p.navigation.type==='number'&&p.navigation.type<3)o.nt=p.navigation.type;}}catch(e){}
var a=[];for(var key in o)a.push(key+'='+o[key]);return 'omni-page-info;'+a.join(';');})()
)JS";
    return s;
}

struct Report {
    bool ok = false;   // the page answered
    std::string lang;
    long long words = 0, cjk = 0;
    int cookies = -1, local = -1, session = -1;
    long long loadMs = -1, readyMs = -1, firstByteMs = -1, bytes = -1;
    int navType = -1;
};
inline Report parse(const std::string& text)
{
    Report r;
    const std::string tag = std::string(kAnswerTag) + ";";
    if (text.compare(0, tag.size(), tag) != 0) return r;
    r.ok = true;
    size_t p = tag.size();
    while (p < text.size()) {
        size_t semi = text.find(';', p);
        if (semi == std::string::npos) semi = text.size();
        const std::string item = text.substr(p, semi - p);
        p = semi + 1;
        const size_t eq = item.find('=');
        if (eq == std::string::npos) continue;
        const std::string key = item.substr(0, eq), val = item.substr(eq + 1);
        if (key == "lang") {
            std::string l;
            for (char c : val) if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_') l += c;
            r.lang = l.substr(0, 24);
            continue;
        }
        if (val.empty()) continue;
        bool neg = false;
        size_t i = 0;
        if (val[0] == '-') { neg = true; i = 1; }
        if (i >= val.size() || val.size() - i > 12) continue;
        long long v = 0;
        bool good = true;
        for (; i < val.size(); ++i) { if (val[i] < '0' || val[i] > '9') { good = false; break; } v = v * 10 + (val[i] - '0'); }
        if (!good) continue;
        if (neg) v = -1;
        const int iv = v > 1000000000 ? 1000000000 : int(v);
        if (key == "w") r.words = v < 0 ? 0 : v;
        else if (key == "c") r.cjk = v < 0 ? 0 : v;
        else if (key == "ck") r.cookies = iv;
        else if (key == "ls") r.local = iv;
        else if (key == "ss") r.session = iv;
        else if (key == "ld") r.loadMs = v;
        else if (key == "dcl") r.readyMs = v;
        else if (key == "fb") r.firstByteMs = v;
        else if (key == "nt") r.navType = v >= 0 && v <= 3 ? int(v) : -1;
        else if (key == "tb") r.bytes = v;
    }
    return r;
}

// --- formatting ------------------------------------------------------------------------------------------------------
// 1234567 -> "1,234,567"
inline std::string grouped(long long n)
{
    const bool neg = n < 0;
    std::string d = std::to_string(neg ? -n : n), out;
    for (size_t i = 0; i < d.size(); ++i) {
        if (i && (d.size() - i) % 3 == 0) out += ',';
        out += d[i];
    }
    return neg ? "-" + out : out;
}
inline std::string plural(long long n, const char* one, const char* many) { return grouped(n) + " " + (n == 1 ? one : many); }
// 850 -> "850 ms", 2430 -> "2.4 s", 12000 -> "12 s", 65000 -> "1 min 5 s"
inline std::string msText(long long ms)
{
    if (ms < 0) return "-";
    if (ms < 1000) return std::to_string(ms) + " ms";
    if (ms < 10000) {
        const long long tenths = (ms + 50) / 100;
        if (tenths % 10 == 0) return std::to_string(tenths / 10) + " s";
        return std::to_string(tenths / 10) + "." + std::to_string(tenths % 10) + " s";
    }
    const long long s = (ms + 500) / 1000;
    if (s < 60) return std::to_string(s) + " s";
    return std::to_string(s / 60) + " min" + (s % 60 ? " " + std::to_string(s % 60) + " s" : std::string());
}
// 0 -> "0 bytes", 900 -> "900 bytes", 1536 -> "1.5 KB", 2500000 -> "2.4 MB" (1024 based)
inline std::string bytesText(long long b)
{
    if (b < 0) return "-";
    if (b < 1024) return plural(b, "byte", "bytes");
    const char* units[] = { "KB", "MB", "GB" };
    double v = double(b) / 1024.0;
    int u = 0;
    while (v >= 1024.0 && u < 2) { v /= 1024.0; ++u; }
    long long tenths = (long long)(v * 10 + 0.5);
    if (tenths >= 100 && (tenths + 5) / 10 >= 1024 && u < 2) { v /= 1024.0; ++u; tenths = (long long)(v * 10 + 0.5); }   // 1023.6 KB -> 1 MB
    std::string n = tenths >= 100 ? std::to_string((tenths + 5) / 10) : std::to_string(tenths / 10) + (tenths % 10 ? "." + std::to_string(tenths % 10) : std::string());
    return n + " " + units[u];
}

// --- reading -------------------------------------------------------------------------------------------------------
// Minutes to read: words / 230 + CJK characters / 500, rounded up; 0 when there is no text.
inline long long readingMinutes(long long words, long long cjk)
{
    if (words <= 0 && cjk <= 0) return 0;
    const long long w = words > 0 ? words : 0, c = cjk > 0 ? cjk : 0;
    const long long num = w * kCjkPerMinute + c * kWordsPerMinute, den = (long long)kWordsPerMinute * kCjkPerMinute;
    return (num + den - 1) / den;
}
inline std::string readingValue(const Report& r)
{
    if (!r.ok) return "-";
    const long long m = readingMinutes(r.words, r.cjk);
    if (m == 0) return "No text to read";
    if (r.words + r.cjk < 60) return "Under a minute";
    return "About " + std::to_string(m) + " min";
}
inline std::string wordsText(const Report& r)
{
    if (!r.ok) return std::string();
    if (r.words <= 0 && r.cjk <= 0) return "No readable text on this page";
    std::string s;
    if (r.words > 0) s = plural(r.words, "word", "words");
    if (r.cjk > 0) s += (s.empty() ? "" : " and ") + plural(r.cjk, "character", "characters") + " (Chinese / Japanese / Korean)";
    return s + ". An estimate: menus and footers may count";
}

// --- language ------------------------------------------------------------------------------------------------------
inline const char* languageName(const std::string& primary)
{
    static const char* const names[][2] = {
        {"en","English"},{"ja","Japanese"},{"zh","Chinese"},{"ko","Korean"},{"es","Spanish"},{"fr","French"},{"de","German"},
        {"pt","Portuguese"},{"it","Italian"},{"ru","Russian"},{"ar","Arabic"},{"hi","Hindi"},{"th","Thai"},{"vi","Vietnamese"},
        {"id","Indonesian"},{"tr","Turkish"},{"pl","Polish"},{"nl","Dutch"},{"uk","Ukrainian"},{"sv","Swedish"},{"da","Danish"},
        {"no","Norwegian"},{"nb","Norwegian"},{"fi","Finnish"},{"cs","Czech"},{"el","Greek"},{"he","Hebrew"},{"hu","Hungarian"},
        {"ro","Romanian"},{"ms","Malay"},{"fa","Persian"},{"bn","Bengali"},{"ca","Catalan"},{"sk","Slovak"},{"bg","Bulgarian"},
        {"hr","Croatian"},{"sr","Serbian"},{"lt","Lithuanian"},{"lv","Latvian"},{"et","Estonian"},{"sl","Slovenian"},{"tl","Tagalog"}};
    for (const auto& n : names) if (primary == n[0]) return n[1];
    return nullptr;
}
// "en-GB" -> "English (en-GB)"; "xx" -> "xx"; "" -> "Not stated by the page"
inline std::string languageValue(const Report& r)
{
    if (!r.ok) return "-";
    if (r.lang.empty()) return "Not stated by the page";
    std::string primary;
    for (char c : r.lang) { if (c == '-' || c == '_') break; primary += lower(c); }
    const char* n = languageName(primary);
    return n ? std::string(n) + " (" + r.lang + ")" : r.lang;
}
// The translate offer's rule (OMNI_TRANSLATE_V1): a stated language other than English can be translated.
inline bool translatable(const Report& r)
{
    if (!r.ok || r.lang.empty()) return false;
    std::string primary;
    for (char c : r.lang) { if (c == '-' || c == '_') break; primary += lower(c); }
    return !primary.empty() && primary != "en";
}

// --- load time -----------------------------------------------------------------------------------------------------
inline const char* navTypeName(int t)
{
    return t == 0 ? "Opened" : t == 1 ? "Reloaded" : t == 2 ? "Back / forward" : t == 3 ? "Preloaded" : "";
}
inline std::string loadValue(const Report& r, bool stillLoading)
{
    if (!r.ok) return "-";
    if (r.loadMs >= 0) return msText(r.loadMs);
    if (stillLoading || r.readyMs >= 0) return "Still loading";
    return "Not available";
}
// "First byte 120 ms . Content ready 1.1 s . 48 KB . Reloaded" (only the parts known)
inline std::string loadDetail(const Report& r)
{
    if (!r.ok) return std::string();
    std::vector<std::string> v;
    if (r.firstByteMs >= 0) v.push_back("First byte " + msText(r.firstByteMs));
    if (r.readyMs >= 0) v.push_back("Content ready " + msText(r.readyMs));
    if (r.bytes == 0) v.push_back("From the cache");
    else if (r.bytes > 0) v.push_back(bytesText(r.bytes));
    if (navTypeName(r.navType)[0]) v.push_back(navTypeName(r.navType));
    std::string s;
    for (const auto& x : v) s += (s.empty() ? "" : " \xc2\xb7 ") + x;
    return s.empty() ? std::string("This page's own load, not later in-page changes") : s;
}

// --- cookies and site data -----------------------------------------------------------------------------------------
inline std::string storageValue(const Report& r)
{
    if (!r.ok) return "-";
    if (r.cookies < 0 && r.local < 0 && r.session < 0) return "Not readable on this page";
    std::vector<std::string> v;
    if (r.cookies >= 0) v.push_back(plural(r.cookies, "cookie", "cookies"));
    const long long items = (r.local > 0 ? r.local : 0) + (r.session > 0 ? r.session : 0);
    if (r.local >= 0 || r.session >= 0) v.push_back(plural(items, "stored item", "stored items"));
    std::string s;
    for (const auto& x : v) s += (s.empty() ? "" : " \xc2\xb7 ") + x;
    return s;
}
constexpr const char* kStorageDetail = "What this page can read. Sign-in (HttpOnly) cookies are hidden from pages, so they aren't counted";

// --- permissions ---------------------------------------------------------------------------------------------------
// The site's Site permissions entries (omniPermFor: saved + this session), e.g. {"popups":1, "storage:x.com":1}.
inline std::string permissionsValue(const std::map<std::string, int>& perms)
{
    int popups = 0, storageAllowed = 0, storageBlocked = 0;
    for (const auto& [k, v] : perms) {
        if (k == "popups") popups = v;
        else if (k.rfind("storage:", 0) == 0) { if (v == 1) ++storageAllowed; else if (v == 2) ++storageBlocked; }
    }
    std::vector<std::string> v;
    if (popups == 1) v.push_back("Pop-ups allowed");
    else if (popups == 2) v.push_back("Pop-ups blocked");
    if (storageAllowed) v.push_back("Cookie access for " + plural(storageAllowed, "site", "sites"));
    if (storageBlocked) v.push_back("Cookie access blocked for " + plural(storageBlocked, "site", "sites"));
    if (v.empty()) return "None granted";
    std::string s;
    for (const auto& x : v) s += (s.empty() ? "" : " \xc2\xb7 ") + x;
    return s;
}

// --- uBlock --------------------------------------------------------------------------------------------------------
inline std::string ublockValue(bool enabled, bool failed, bool siteTrusted, bool hasHost)
{
    if (failed) return "Error";
    if (!enabled) return "Off everywhere";
    if (!hasHost) return "On";
    return siteTrusted ? "Off for this site" : "On";
}
constexpr const char* kUblockDetail = "How many requests it blocked isn't available in this build";
inline std::string popupsBlockedValue(size_t n) { return std::to_string(n); }

// --- the panel -----------------------------------------------------------------------------------------------------
inline std::string subtitle(const Connection& c, const std::string& title)
{
    if (!c.host.empty()) return c.host;
    if (!title.empty()) return title;
    return c.kind == kNone ? std::string("No page") : connectionValue(c);
}
inline std::string savedValue(size_t n) { return n == 0 ? std::string("None (defaults)") : n == 1 ? std::string("1 setting") : std::to_string(n) + " settings"; }
constexpr const char* kPrivateDetail = "Private tab: Page info stores nothing, and choices made here last until Omni closes";
constexpr const char* kReading = "Reading\xe2\x80\xa6";   // "Reading..." while the page script runs

} // namespace OmniPageInfo
