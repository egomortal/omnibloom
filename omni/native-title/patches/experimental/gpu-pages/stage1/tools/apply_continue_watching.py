#!/usr/bin/env python3
"""OMNI_CONTINUE_WATCHING_V1 (2026-11-16): a "Continue watching" row on Omni's start page.

What it does
  - The bundled add-on omni-resume-videos (1.1.0, omnibloom/addons/bundled/omni-resume-videos) keeps, next to its
    address-free 'r:<hash>' resume entries, one 'w:<same hash>' entry per video left part-way:
        {"u":"<page address, tracking/start-time params removed>","t":"<title>","i":"<og:image>","p":<s>,"d":<s>,"a":<unix s>}
    Only after 2 minutes watched, removed past 95 % or at the end, at most 30 (oldest dropped). Add-on storage writes
    from private tabs are refused by the host (OmniAddonsCore::handleMessage) and the add-on never runs there
    (private_safe false), so private tabs are never recorded.
  - The shell reads those entries from the add-on host's in-memory storage (omniAdFind(...)->storage, the copy that
    /data/omni/addons/storage/omni-resume-videos.txt is written from), never from the file: no disk read, and a removal
    here cannot be overwritten by the host's next save. Read only when a start page finishes loading or a start-page tab
    is shown again (re-rendered only when the list changed); nothing per frame.
  - Start page = omni://pages/start/ (the built-in pages) or the old data: new-tab page (pages off). After it loads, one
    fixed script (the list as a JSON literal; no page text is ever evaluated) puts a "Continue watching" section after
    the search area: up to 6 tiles, newest first: site letter (the start page's CSP allows no remote images, so no
    og:image thumbnails), title, "site . 12 min left", a progress bar. Cross (the page's own D-pad focus, or the
    pointer) opens the page; the add-on then offers to resume. Square on a focused / pointed tile removes that entry
    (the 'w:' key only: the resume offer on that page stays) and the row redraws with focus on the next tile; Square
    anywhere else keeps its usual action (new tab). Not shown in private tabs, nor while the add-on is switched off.
  - Browser settings: "Continue watching on start page" (On / Off) right after "Home page". Off =
    /data/omni/continue-watching-off.flag; open start pages update at once.

Files
  - OmniContinueWatching.h (new, pure: flat JSON parse, ranking, "12 min left", the page JSON). Tests:
      g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_continue_watching.cpp -o t && ./t
  - OmniContinueWatchingShell.h (new: storage read, page script, Square, settings row), included after OmniPages.h.
  - OmniBrowser.cpp: include (pure), forward declarations, hooks in omniEverydayFinished / omniEverydayActivated /
    button(), include (shell).   OmniBrowserSettings.h: the settings row and its input.

usage: apply_continue_watching.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_CONTINUE_WATCHING_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_CONTINUE_WATCHING_V1: "Continue watching" on the start page, pure part (no SDL / WebKit types).
// Entries come from the omni-resume-videos add-on's storage: key "w:<hash>", value written by its JSON.stringify:
//   {"u":"https://...","t":"title","i":"https://og-image","p":1421,"d":3600,"a":1700000000}
// OmniContinueWatchingShell.h does the rest; tests: tools/test_continue_watching.cpp (g++ on the host).
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <string>
#include <vector>

namespace OmniCw {

constexpr const char* kPrefix = "w:";
constexpr size_t kShown = 6;            // tiles on the start page
constexpr double kMinWatched = 120;     // seconds (the add-on does not store earlier; checked again here)
constexpr double kDone = 0.95;          // past this the video counts as finished
constexpr double kMinDuration = 180;    // the add-on's "long video" rule
constexpr size_t kUrlMax = 4096, kTitleMax = 300;

struct Entry {
    std::string key, url, title, image;
    double position = 0, duration = 0;
    long long at = 0;
};

inline void putUtf8(std::string& o, unsigned cp)
{
    if (cp < 0x80) o += char(cp);
    else if (cp < 0x800) { o += char(0xc0 | (cp >> 6)); o += char(0x80 | (cp & 0x3f)); }
    else if (cp < 0x10000) { o += char(0xe0 | (cp >> 12)); o += char(0x80 | ((cp >> 6) & 0x3f)); o += char(0x80 | (cp & 0x3f)); }
    else { o += char(0xf0 | (cp >> 18)); o += char(0x80 | ((cp >> 12) & 0x3f)); o += char(0x80 | ((cp >> 6) & 0x3f)); o += char(0x80 | (cp & 0x3f)); }
}
inline bool hex4(const std::string& s, size_t i, unsigned& v)
{
    if (i + 4 > s.size()) return false;
    v = 0;
    for (size_t k = i; k < i + 4; ++k) {
        const char c = s[k];
        v <<= 4;
        if (c >= '0' && c <= '9') v |= unsigned(c - '0');
        else if (c >= 'a' && c <= 'f') v |= unsigned(c - 'a' + 10);
        else if (c >= 'A' && c <= 'F') v |= unsigned(c - 'A' + 10);
        else return false;
    }
    return true;
}
// A JSON string starting at s[i] == '"'; i ends after the closing quote.
inline bool readString(const std::string& s, size_t& i, std::string& out)
{
    out.clear();
    if (i >= s.size() || s[i] != '"') return false;
    for (++i; i < s.size(); ++i) {
        const char c = s[i];
        if (c == '"') { ++i; return true; }
        if ((unsigned char)c < 0x20) return false;
        if (c != '\\') { out += c; continue; }
        if (++i >= s.size()) return false;
        switch (s[i]) {
        case '"': out += '"'; break; case '\\': out += '\\'; break; case '/': out += '/'; break;
        case 'b': out += '\b'; break; case 'f': out += '\f'; break; case 'n': out += '\n'; break;
        case 'r': out += '\r'; break; case 't': out += '\t'; break;
        case 'u': {
            unsigned cp;
            if (!hex4(s, i + 1, cp)) return false;
            i += 4;
            if (cp >= 0xd800 && cp < 0xdc00) {   // a surrogate pair, or U+FFFD
                unsigned lo;
                if (i + 2 < s.size() && s[i + 1] == '\\' && s[i + 2] == 'u' && hex4(s, i + 3, lo) && lo >= 0xdc00 && lo < 0xe000) {
                    cp = 0x10000 + ((cp - 0xd800) << 10) + (lo - 0xdc00);
                    i += 6;
                } else cp = 0xfffd;
            } else if (cp >= 0xdc00 && cp < 0xe000) cp = 0xfffd;
            putUtf8(out, cp);
            break;
        }
        default: return false;
        }
    }
    return false;
}
// A flat JSON object (string / number / true / false / null values). Nested values: false.
inline bool parseFlat(const std::string& s, std::map<std::string, std::string>& strs, std::map<std::string, double>& nums)
{
    size_t i = 0;
    auto ws = [&] { while (i < s.size() && (s[i] == ' ' || s[i] == '\t' || s[i] == '\n' || s[i] == '\r')) ++i; };
    ws();
    if (i >= s.size() || s[i] != '{') return false;
    ++i; ws();
    if (i < s.size() && s[i] == '}') { ++i; ws(); return i == s.size(); }
    for (;;) {
        std::string k, v;
        ws();
        if (!readString(s, i, k)) return false;
        ws();
        if (i >= s.size() || s[i] != ':') return false;
        ++i; ws();
        if (i >= s.size()) return false;
        if (s[i] == '"') { if (!readString(s, i, v)) return false; strs[k] = v; }
        else if (s.compare(i, 4, "true") == 0 || s.compare(i, 4, "null") == 0) i += 4;
        else if (s.compare(i, 5, "false") == 0) i += 5;
        else if (s[i] == '-' || (s[i] >= '0' && s[i] <= '9')) {
            const char* b = s.c_str() + i;
            char* e = nullptr;
            const double d = strtod(b, &e);
            if (e == b || !std::isfinite(d)) return false;
            i += size_t(e - b);
            nums[k] = d;
        } else return false;
        ws();
        if (i < s.size() && s[i] == ',') { ++i; continue; }
        if (i < s.size() && s[i] == '}') { ++i; ws(); return i == s.size(); }
        return false;
    }
}

inline bool webUrl(const std::string& u)
{
    if (u.rfind("https://", 0) != 0 && u.rfind("http://", 0) != 0) return false;
    if (u.size() > kUrlMax) return false;
    for (unsigned char c : u) if (c <= 0x20 || c == 0x7f || c == '"' || c == '<' || c == '>' || c == '\\') return false;
    return true;
}
inline bool validKey(const std::string& k)
{
    if (k.rfind(kPrefix, 0) != 0 || k.size() <= 2 || k.size() > 128) return false;
    for (unsigned char c : k) if (c < 0x21 || c == 0x7f || c == '"' || c == '\\') return false;
    return true;
}
// One storage value -> Entry; false for anything that is not a usable continue-watching entry.
inline bool parseEntry(const std::string& key, const std::string& json, Entry& e)
{
    if (!validKey(key)) return false;
    std::map<std::string, std::string> s;
    std::map<std::string, double> n;
    if (!parseFlat(json, s, n) || !s.count("u") || !n.count("p") || !n.count("d")) return false;
    e = Entry();
    e.key = key; e.url = s["u"]; e.title = s.count("t") ? s["t"] : std::string(); e.image = s.count("i") ? s["i"] : std::string();
    e.position = n["p"]; e.duration = n["d"]; e.at = n.count("a") ? (long long)n["a"] : 0;
    return webUrl(e.url);
}
// Worth a tile: a long video, watched at least 2 minutes, not finished.
inline bool showable(const Entry& e)
{
    return webUrl(e.url) && e.duration > kMinDuration && e.position >= kMinWatched && e.position < e.duration * kDone;
}
// The tiles: showable entries, newest first, one per page address, at most `max`.
inline std::vector<Entry> rank(const std::map<std::string, std::string>& storage, size_t max = kShown)
{
    std::vector<Entry> all;
    for (auto it = storage.lower_bound(kPrefix); it != storage.end() && it->first.rfind(kPrefix, 0) == 0; ++it) {
        Entry e;
        if (parseEntry(it->first, it->second, e) && showable(e)) all.push_back(std::move(e));
    }
    std::stable_sort(all.begin(), all.end(), [](const Entry& a, const Entry& b) { return a.at != b.at ? a.at > b.at : a.key < b.key; });
    std::vector<Entry> out;
    for (auto& e : all) {
        if (out.size() >= max) break;
        bool dup = false;
        for (auto& o : out) if (o.url == e.url) dup = true;
        if (!dup) out.push_back(std::move(e));
    }
    return out;
}

// "12 min left", "1 h 5 min left", "2 h left", "Under 1 min left".
inline std::string leftText(double position, double duration)
{
    const double rem = duration - position;
    if (!(rem >= 60)) return "Under 1 min left";
    const long long mins = (long long)std::ceil(rem / 60.0 - 1e-9);
    char b[48];
    if (mins < 60) snprintf(b, sizeof b, "%lld min left", mins);
    else if (mins % 60) snprintf(b, sizeof b, "%lld h %lld min left", mins / 60, mins % 60);
    else snprintf(b, sizeof b, "%lld h left", mins / 60);
    return b;
}
// Progress bar width, 1..99 %.
inline int percent(double position, double duration)
{
    if (!(duration > 0)) return 1;
    return std::clamp(int(position * 100.0 / duration), 1, 99);
}
// "example.com" from "https://user@www.Example.com:8443/x?y" (lowercase, no "www.", no port).
inline std::string site(const std::string& url)
{
    size_t b = url.find("://");
    if (b == std::string::npos) return std::string();
    b += 3;
    size_t e = url.find_first_of("/?#", b);
    std::string h = url.substr(b, e == std::string::npos ? std::string::npos : e - b);
    const size_t at = h.rfind('@');
    if (at != std::string::npos) h = h.substr(at + 1);
    if (!h.empty() && h[0] == '[') { const size_t r = h.find(']'); h = h.substr(0, r == std::string::npos ? h.size() : r + 1); }
    else { const size_t c = h.find(':'); if (c != std::string::npos) h = h.substr(0, c); }
    for (auto& c : h) if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
    if (h.rfind("www.", 0) == 0) h = h.substr(4);
    return h;
}
inline std::string letter(const std::string& siteName)
{
    if (siteName.empty()) return "?";
    const char c = siteName[0];
    if (c >= 'a' && c <= 'z') return std::string(1, char(c - 'a' + 'A'));
    if ((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')) return std::string(1, c);
    return "?";
}
// At most `max` bytes, never cutting a UTF-8 sequence; control characters become spaces.
inline std::string cleanText(const std::string& s, size_t max)
{
    std::string o;
    for (unsigned char c : s) o += (c < 0x20 || c == 0x7f) ? ' ' : char(c);
    if (o.size() <= max) return o;
    size_t n = max;
    while (n && (static_cast<unsigned char>(o[n]) & 0xc0) == 0x80) --n;
    return o.substr(0, n) + "\xE2\x80\xA6";
}
// A JSON string literal that is also safe as JavaScript source (U+2028 / U+2029 escaped).
inline std::string jsonQuote(const std::string& s)
{
    std::string o = "\"";
    for (size_t i = 0; i < s.size(); ++i) {
        const unsigned char c = (unsigned char)s[i];
        if (c == '"' || c == '\\') { o += '\\'; o += char(c); }
        else if (c < 0x20 || c == 0x7f) { char b[8]; snprintf(b, sizeof b, "\\u%04x", c); o += b; }
        else if (c == 0xe2 && i + 2 < s.size() && (unsigned char)s[i + 1] == 0x80 && ((unsigned char)s[i + 2] == 0xa8 || (unsigned char)s[i + 2] == 0xa9)) {
            o += (unsigned char)s[i + 2] == 0xa8 ? "\\u2028" : "\\u2029";
            i += 2;
        } else if (c == '<') o += "\\u003c";
        else o += char(c);
    }
    return o + "\"";
}
// The data the page script draws: {"items":[{k,u,t,s,l,p,left}],"focus":n,"hint":"..."}.
inline std::string pageJson(const std::vector<Entry>& list, int focus, const std::string& hint)
{
    std::string o = "{\"items\":[";
    for (size_t i = 0; i < list.size(); ++i) {
        const Entry& e = list[i];
        const std::string s = site(e.url);
        std::string t = cleanText(e.title, kTitleMax);
        if (t.find_first_not_of(' ') == std::string::npos) t = s;
        o += (i ? "," : "") + std::string("{\"k\":") + jsonQuote(e.key) + ",\"u\":" + jsonQuote(e.url) + ",\"t\":" + jsonQuote(t)
            + ",\"s\":" + jsonQuote(s) + ",\"l\":" + jsonQuote(letter(s)) + ",\"p\":" + std::to_string(percent(e.position, e.duration))
            + ",\"left\":" + jsonQuote(leftText(e.position, e.duration)) + "}";
    }
    return o + "],\"focus\":" + std::to_string(focus) + ",\"hint\":" + jsonQuote(hint) + "}";
}
// What the Square probe returned: "<index>\t<key>"; false when nothing was focused or it is not one of ours.
inline bool parseProbe(const std::string& r, int& index, std::string& key)
{
    const size_t t = r.find('\t');
    if (t == std::string::npos || t == 0 || t > 3) return false;
    index = 0;
    for (size_t i = 0; i < t; ++i) { if (r[i] < '0' || r[i] > '9') return false; index = index * 10 + (r[i] - '0'); }
    key = r.substr(t + 1);
    return validKey(key);
}

} // namespace OmniCw
'''

SHELL = r'''// OMNI_CONTINUE_WATCHING_V1: "Continue watching" on the start page, shell part (after OmniPages.h / OmniAddons.h).
// Data: the omni-resume-videos add-on's "w:" storage entries, read from the add-on host's in-memory copy (the one
// /data/omni/addons/storage/omni-resume-videos.txt is saved from). The reasons are in tools/apply_continue_watching.py.
#pragma once

static const char* const omniCwAddon = "omni-resume-videos";
static int omniCwState = -1;    // -1 not read yet, 0 off, 1 on (/data/omni/continue-watching-off.flag)
static bool omniCwSkip = false;
static std::map<WKPageRef, std::string> omniCwDrawn;   // what each start page shows now (redraw only on change)

static bool omniCwOn()
{
    if (omniCwState < 0) omniCwState = access(omniData("continue-watching-off.flag").c_str(), F_OK) != 0 ? 1 : 0;
    return omniCwState == 1;
}
static bool omniCwStartURL(const std::string& url)
{
    return url.rfind("omni://pages/start/", 0) == 0 || url.rfind(omniNewTabPrefix, 0) == 0;
}
static OmniAd* omniCwAd()
{
    OmniAd* a = omniAdFind(omniCwAddon);
    if (!a || !a->error.empty() || a->js.empty() || !OmniAddonsCore::globalOn(a->m, omniAdSt(a->m.id))) return nullptr;
    return a;
}
// One fixed script; %DATA% is OmniCw::pageJson (a JSON literal). Built-in pages: CSSOM styles only (CSP), D-pad focus
// comes from the page's own controller (a[href] are focusable), Cross clicks; the link opens through the host bridge.
static const char* const omniCwScript = R"JS((function(D){'use strict';
var old=document.getElementById('omni-cw');if(old)old.remove();if(!D.items.length)return '0';
var pages=location.protocol==='omni:';
function el(t,css,txt){var e=document.createElement(t);if(css)Object.assign(e.style,css);if(txt!=null)e.textContent=txt;return e}
var sec=el('section',{margin:'0 0 24px'});sec.id='omni-cw';if(pages)sec.className='section card';sec.setAttribute('aria-label','Continue watching');
sec.appendChild(el('h2',null,'Continue watching'));
var g=el('div',{display:'grid',gridTemplateColumns:'repeat(3,minmax(0,1fr))',gap:'14px'});
D.items.forEach(function(it){
var a=el('a',{display:'flex',flexDirection:'column',gap:'10px',padding:'16px',borderRadius:'14px',background:'var(--tab,rgba(127,127,127,.14))',color:'inherit',textDecoration:'none',minWidth:'0'});
a.href=it.u;a.title=it.t;a.setAttribute('data-omni-cw',it.k);
var top=el('div',{display:'flex',alignItems:'center',gap:'14px',minWidth:'0'});
top.appendChild(el('i',{flex:'none',width:'42px',height:'42px',borderRadius:'21px',background:'var(--accent,#107c10)',color:'var(--accentInk,#fff)',font:'700 20px sans-serif',display:'flex',alignItems:'center',justifyContent:'center',fontStyle:'normal'},it.l));
var sp=el('span',{display:'block',minWidth:'0'});
sp.appendChild(el('b',{display:'block',fontSize:'19px',fontWeight:'600',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'},it.t));
sp.appendChild(el('small',{display:'block',fontSize:'14px',opacity:'.75',marginTop:'3px',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'},it.s+' · '+it.left));
top.appendChild(sp);a.appendChild(top);
var bar=el('div',{height:'6px',borderRadius:'3px',background:'rgba(127,127,127,.35)',overflow:'hidden'});
bar.appendChild(el('div',{height:'100%',width:it.p+'%',background:'var(--accent,#107c10)'}));a.appendChild(bar);
a.addEventListener('click',function(e){var H=window.omnibloomHost;if(pages&&H&&H.request&&it.u.indexOf('@')<0){e.preventDefault();H.request({method:'navigation.open',params:{url:it.u}})}});
g.appendChild(a)});
sec.appendChild(g);sec.appendChild(el('p',{fontSize:'14px',opacity:'.7',margin:'10px 0 0'},D.hint));
var at=pages?document.querySelector('main section.hero'):document.querySelector('.w form');
if(at&&at.parentNode)at.parentNode.insertBefore(sec,at.nextSibling);else{var m=document.querySelector('main')||document.body;if(!m)return '0';m.insertBefore(sec,m.firstChild)}
if(D.focus>=0){var all=g.querySelectorAll('a'),f=all[Math.min(D.focus,all.length-1)];if(f){document.querySelectorAll('.pad-focus').forEach(function(x){x.classList.remove('pad-focus')});f.classList.add('pad-focus');try{f.focus({preventScroll:true})}catch(x){f.focus()}}}
return String(D.items.length)})(%DATA%))JS";
// Square: which tile has the D-pad focus (or the pointer): "<index>\t<key>", or "".
static const char* const omniCwProbe = "(function(){var e=document.activeElement,t=e&&e.closest?e.closest('[data-omni-cw]'):null;"
    "if(!t)try{t=document.querySelector('[data-omni-cw]:hover')}catch(x){}if(!t)return '';"
    "return [].indexOf.call(document.querySelectorAll('[data-omni-cw]'),t)+'\\t'+t.getAttribute('data-omni-cw')})()";

static void omniCwEval(Tab* tab, const std::string& js)
{
    auto source = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    WKPageEvaluateJavaScriptInMainFrame(tab->page, source.get(), nullptr, [](WKTypeRef, WKErrorRef, void*) { });
}
// Draws (or updates) the row on a start page. focus >= 0: focus that tile afterwards (after a removal).
static void omniCwRender(Tab* tab, int focus, bool force)
{
    if (!tab || tab->loading || tab->crashed || omniTestMode()) return;
    std::vector<OmniCw::Entry> list;
    if (!tab->omniPrivate && omniCwOn())
        if (OmniAd* a = omniCwAd()) list = OmniCw::rank(a->storage.kv, OmniCw::kShown);
    const std::string hint = playStationIcons ? "\xC3\x97 Resume   \xE2\x96\xA1 Remove from this row" : "A Resume   X Remove from this row";
    const std::string data = OmniCw::pageJson(list, focus, hint);
    const auto it = omniCwDrawn.find(tab->page);
    const bool seen = it != omniCwDrawn.end();
    if (!force && seen && it->second == data) return;   // nothing new to draw
    if (omniCwDrawn.size() > 64) omniCwDrawn.clear();
    omniCwDrawn[tab->page] = data;   // remembered even when empty: showing the tab again can still draw the row
    if (!force && !seen && list.empty()) return;   // a fresh start page without entries: nothing to put there
    std::string js = omniCwScript;
    const size_t at = js.find("%DATA%");
    js.replace(at, 6, data);
    omniCwEval(tab, js);
}
// omniEverydayFinished(): a start page finished loading (before its URL is cleared to "New tab").
static void omniCwFinished(Tab& tab)
{
    if (!omniCwStartURL(tab.url)) { omniCwDrawn.erase(tab.page); return; }
    omniCwDrawn.erase(tab.page);   // a fresh document has no row yet
    omniCwRender(&tab, -1, false);
}
// omniEverydayActivated(): a start page shown again (the list may have changed in another tab).
static void omniCwActivated(Tab* tab)
{
    if (tab && tab->omniNewTabPage && omniCwDrawn.count(tab->page)) omniCwRender(tab, -1, false);
}
static void omniCwProbeDone(WKTypeRef result, WKErrorRef error, void* context)
{
    if (!running) return;
    const std::string r = !error && result && WKGetTypeID(result) == WKStringGetTypeID() ? OmniTest::toStd(static_cast<WKStringRef>(result)) : std::string();
    Tab* tab = active();
    int index = 0;
    std::string key;
    if (!OmniCw::parseProbe(r, index, key)) {   // no tile focused: Square's usual action
        if (tab && static_cast<const void*>(tab->page) == context) { omniCwSkip = true; button(SDL_CONTROLLER_BUTTON_X); omniCwSkip = false; }
        return;
    }
    if (!tab || static_cast<const void*>(tab->page) != context) return;
    OmniAd* a = omniAdFind(omniCwAddon);
    if (a && OmniAddonsCore::storageRemove(a->storage, key)) {   // the "w:" entry only: the page's resume offer stays
        omniAdSaveStorage(*a);
        a->dirty = true; a->dirtyAt = SDL_GetTicks();   // new documents get the new storage
        fprintf(stderr, "continue-watching: removed one entry\n");
        notice("Removed from Continue watching");
    }
    omniCwRender(tab, index, true);
}
// button(): Square on a start page whose row has the focus removes that entry.
static bool omniCwButton(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_X || omniCwSkip) return false;
    Tab* t = active();
    if (!t || !t->omniNewTabPage || t->loading || t->crashed || t->omniPrivate || editing || settingsOpen || pageFullscreen || omniOverlayOpen()) return false;
    auto it = omniCwDrawn.find(t->page);
    if (it == omniCwDrawn.end() || it->second.rfind("{\"items\":[]", 0) == 0) return false;   // no row on this page
    auto source = adoptWK(WKStringCreateWithUTF8CString(omniCwProbe));
    WKPageEvaluateJavaScriptInMainFrame(t->page, source.get(), const_cast<void*>(static_cast<const void*>(t->page)), omniCwProbeDone);
    return true;
}
// Browser settings: "Continue watching on start page" On / Off.
static bool omniCwSettingsInput(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    const std::string flag = omniData("continue-watching-off.flag");
    if (omniCwOn()) { if (FILE* f = fopen(flag.c_str(), "w")) { fputs("1\n", f); fclose(f); } }
    else unlink(flag.c_str());
    omniCwState = -1;
    notice(omniCwOn() ? "Continue watching shown on the start page" : "Continue watching hidden");
    for (auto& t : tabs) if (t->omniNewTabPage && omniCwDrawn.count(t->page)) omniCwRender(t.get(), -1, true);
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniTabAudio.h" // OMNI_TAB_AUDIO_V1: tab sound badges, per-tab mute (pure)\n',
         '#include "OmniTabAudio.h" // OMNI_TAB_AUDIO_V1: tab sound badges, per-tab mute (pure)\n'
         '#include "OmniContinueWatching.h" // OMNI_CONTINUE_WATCHING_V1: start-page row from the resume add-on (pure)\n'),
        ('static void omniOpenNewTabPage(Tab* tab);\n',
         'static void omniOpenNewTabPage(Tab* tab);\n'
         'static void omniCwFinished(Tab& tab);     // OMNI_CONTINUE_WATCHING_V1 (OmniContinueWatchingShell.h)\n'
         'static void omniCwActivated(Tab* tab);\n'
         'static bool omniCwButton(int b);\n'),
        ('    if (tab.url.rfind(omniNewTabPrefix, 0) == 0 || omniPagesIsNewTab(tab.url)) { tab.url.clear(); tab.title = "New tab"; tab.omniNewTabPage = true; } // s3 OMNI_PAGES_V1: + start/welcome\n',
         '    omniCwFinished(tab); // OMNI_CONTINUE_WATCHING_V1: the start page gets its row (reads tab.url before it is cleared)\n'
         '    if (tab.url.rfind(omniNewTabPrefix, 0) == 0 || omniPagesIsNewTab(tab.url)) { tab.url.clear(); tab.title = "New tab"; tab.omniNewTabPage = true; } // s3 OMNI_PAGES_V1: + start/welcome\n'),
        ('    omniApplySiteZoom(tab); // OMNI_SITE_ZOOM_V1: on tab switch too (compares first; null-safe)\n',
         '    omniApplySiteZoom(tab); // OMNI_SITE_ZOOM_V1: on tab switch too (compares first; null-safe)\n'
         '    omniCwActivated(tab); // OMNI_CONTINUE_WATCHING_V1: a start page shown again redraws its row if the list changed\n'),
        ('    if (omniPagesButton(button)) { omniShellDirty = true; return; } // s3 OMNI_PAGES_V1: built-in pages first\n',
         '    if (omniPagesButton(button)) { omniShellDirty = true; return; } // s3 OMNI_PAGES_V1: built-in pages first\n'
         '    if (omniCwButton(button)) { omniShellDirty = true; return; } // OMNI_CONTINUE_WATCHING_V1: Square on a Continue watching tile\n'),
        ('#include "OmniPages.h" // s3 OMNI_PAGES_V1: omni://pages built-in pages\n',
         '#include "OmniPages.h" // s3 OMNI_PAGES_V1: omni://pages built-in pages\n'
         '#include "OmniContinueWatchingShell.h" // OMNI_CONTINUE_WATCHING_V1\n'),
    ],
    'OmniBrowserSettings.h': [
        ('constexpr int omniYtTvRowId = 860, omniUaOmniRowId = 861;\n',
         'constexpr int omniYtTvRowId = 860, omniUaOmniRowId = 861;\n'
         'constexpr int omniCwRowId = 870; // OMNI_CONTINUE_WATCHING_V1 (OmniContinueWatchingShell.h)\n'
         'static bool omniCwOn();\n'
         'static bool omniCwSettingsInput(int b);\n'),
        ('    add(omniFxSetHome, "Home page", omniFxSet.home.empty() ? std::string("New-tab page") : omniShownURL(omniFxSet.home), false);\n',
         '    add(omniFxSetHome, "Home page", omniFxSet.home.empty() ? std::string("New-tab page") : omniShownURL(omniFxSet.home), false);\n'
         '    add(omniCwRowId, "Continue watching on start page", omniCwOn() ? "On" : "Off", true); // OMNI_CONTINUE_WATCHING_V1\n'),
        ('    if (r.id == omniYtTvRowId || r.id == omniUaOmniRowId) return omniYtTvSettingsInput(r.id, b); // OMNI_YOUTUBE_TV_V1\n',
         '    if (r.id == omniCwRowId) return omniCwSettingsInput(b); // OMNI_CONTINUE_WATCHING_V1 (before the >= 300 rows)\n'
         '    if (r.id == omniYtTvRowId || r.id == omniUaOmniRowId) return omniYtTvSettingsInput(r.id, b); // OMNI_YOUTUBE_TV_V1\n'),
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
    for need, mark in (('OmniPages.h', 'OMNI_PAGES_V1'), ('OmniAddons.h', 'OMNI_ADDONS_V1'), ('OmniBrowser.cpp', 'OMNI_TAB_AUDIO_V1'),
                       ('OmniBrowserSettings.h', 'OMNI_YOUTUBE_TV_V1')):
        if mark not in (root / need).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: apply that patch first' % (need, mark))
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniContinueWatching.h', PURE, 'OmniTabSessions.h'),
            write_new('OmniContinueWatchingShell.h', SHELL, 'OmniPages.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
