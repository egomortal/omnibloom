#!/usr/bin/env python3
"""OMNI_SPATIAL_NAV_V1 (2026-11-16): D-pad spatial navigation: a focus ring that the D-pad moves between links,
buttons and fields (like TV browsers), as an alternative to the stick pointer.

What existed (audited in the patched tree after the whole recipe chain, 2026-11-16)
  - button() while browsing: D-pad up / down scroll(+-omniScpDpadStep()) (140 px at Normal, OMNI_SCROLL_PLUS_V1);
    D-pad left / right omniFxDpadSide (OmniQuickMenu.h): Back / Forward, or switch tabs ("D-pad left / right").
    Earlier in button(): the pointer-cross route (the D-pad hands the lead back from the pointer), quick-access row,
    Media downloads, built-in pages, Continue watching, Master Control, overlays / panels, the keyboard, YouTube TV mode
    (omniYtTvButton: arrows / Enter / Back as key events), full-screen video keys, Browser settings, Options, the
    button map (OMNI_BUTTON_MAP_V1: Triangle / Square / R3 / L3 / touchpad only; never the D-pad or Cross).
  - Cross: click() at the pointer (mouse down + up; a text box opens the keyboard through fieldClickDeadline and
    WKPageIsContentEditable in the main loop). Held Cross: the link / page menu at the pointer (omniFxButtonEvent; a
    short press reaches button(A) on release).
  - Key events to pages: omniFullscreenKey -> WKPageHandleKeyboardEvent (YouTube TV mode, full-screen video keys).

WebKit's own spatial navigation (checked in the engine's WebKit tree (s1/webkit), the tree the title links)
  - Always compiled (no ENABLE() flag; page/SpatialNavigation.cpp is in WebCore/Sources.txt). Runtime preference
    SpatialNavigationEnabled (default false), exported in the C API: WKPreferencesSetSpatialNavigationEnabled
    (WKPreferencesRef.h). With it on, EventHandler::defaultArrowEventHandler sends arrow keys that the page did not
    handle to FocusController::advanceFocus(direction).
  - Not used here, because on this port it cannot do the job alone:
      * it moves only to isKeyboardFocusable() elements; links need TabsToLinks, which defaults to false on
        PORT=PlayStation (UnifiedWebPreferences.yaml: true only for GTK / WPE), and <div onclick> / role=button
        controls without tabindex (most modern sites) are skipped;
      * with nothing in that direction it scrolls one line (40 px), and the UI process never learns whether focus
        moved or the page scrolled (key events have no result), so "scroll instead" cannot follow the D-pad speed;
      * it is one global preference: arrow keys would change meaning on every page (full-screen players, YouTube's
        own keys, <select>, radio groups, caret moves at a field's edge in FrameSelection::modify);
      * the page's own CSS draws its focus ring (often `outline: none`), so a strong, accent-coloured ring and Cross
        activation need a page script anyway.
    So this patch uses one small page script per press (the "fallback" of the design), scored like the W3C CSS
    Spatial Navigation draft (css-nav-1 / WICG polyfill): distance = A + B + C*w - D, A the euclidean distance
    between the facing edges, B the distance along the direction, C the orthogonal offset (w = 2 up / down, 30 left /
    right), D the square root of the overlap area. WebKit's preference stays untouched.

What the user sees
  - Browser settings, before "D-pad left / right": "D-pad navigation"  Scroll / Move between links  (default Scroll;
    D-pad left / right change it, Cross steps, Triangle resets). Saved in /data/omni/spatial-nav.txt ("mode<TAB>0|1").
  - In "Move between links" mode, while browsing a page (no panel, keyboard, settings or full-screen video):
      * D-pad up / down / left / right: the ring goes to the nearest link, button, field, tab, checkbox... in that
        direction (visible, not covered, not disabled; at most 3/4 of a screen beyond the edge), scrolled into view
        with a small margin. Links / buttons also get the page's focus (preventScroll), so keyboard-friendly menus
        open; text boxes and selects are not focused until Cross (no page suggestion pop-ups).
        The first press after the pointer was used starts from the element under the pointer (or the pointer's
        point); with no ring and no pointer, from the viewport edge.
      * Nothing that way: D-pad up / down scroll the page by the "Scroll speed" step (as in Scroll mode); left /
        right scroll sideways by the same step (Back / Forward stay on Circle and Options).
      * The ring: a fixed overlay outside the page's own CSS (never clipped, never `outline: none`): the theme's accent
        colour (the "Accent colour" setting; High contrast: its yellow, thicker), with a 2 px black or white halo
        inside and out chosen by the accent's luminance, so it reads on any background. It follows page and box
        scrolling (one requestAnimationFrame per scroll burst, listeners only while shown).
      * Cross: activates the ring's element by a real click at its centre (same path as the pointer: a text box opens
        the on-screen keyboard as today, a <select> opens Omni's list, links open, held Cross gives the link menu
        there because the hidden pointer follows the ring). When the centre is covered, the script focuses / clicks
        the element itself (a text box then opens the keyboard through fieldClickDeadline).
      * The pointer is hidden while the ring leads; moving the stick (or a mouse) shows it and removes the ring
        (the pointer-cross lead, OMNI_POINTER_CROSS_V1). Switching tabs, another address, or Scroll mode remove it too.
      * YouTube TV mode keeps its own D-pad (omniYtTvButton runs earlier in button()); full-screen video, the keyboard,
        built-in pages, Media downloads, panels and dialogs keep theirs (they run earlier as well). The button map
        does not remap the D-pad (fine).
  - One script per press, one in flight; a press during the flight waits for the answer (latest press wins); an
    answer that never comes stops blocking after 1.5 s. Nothing is polled; nothing runs in Scroll mode.

Pure part: engine/entry/OmniSpatialNav.h (no SDL / WebKit): the mode setting, ring colours / width, the page script
(move / act / hide) and its arguments, answer parsing, CSS -> layout px, the one-in-flight queue, the ring's drop
rules. Tested by tools/test_spatial_nav.cpp:
    g++ -std=c++20 -Wall -Wextra -Werror -I<tools or tree>/engine/entry test_spatial_nav.cpp -o t && ./t core.js samples.js
and the script on fake DOM layouts by tools/test_spatial_nav_js.cjs (node test_spatial_nav_js.cjs core.js samples.js).
Shell side: engine/entry/OmniSpatialNavShell.h (included from OmniFeatures3.h after OmniScrollPlusShell.h).

Settings row id 857: checked unused in every engine/entry file (this script refuses to run if it appears there).

Anchors (exactly once each; MARK makes each file idempotent; each file keeps its line endings):
  OmniBrowser.cpp       the OmniScrollPlus.h include line (pure include after it);
                        `static bool omniYtTvPointerHidden();` (forward declarations after it);
                        omniDrawPointer's and omniPointerRect's omniYtTvPointerHidden lines (ours after each);
                        button()'s omniBmapBrowse line (Cross on the ring after it);
                        button()'s omniFxDpadSide line (the D-pad in link mode before it).
  OmniFeatures3.h       the OmniScrollPlusShell.h include line; omniF3Tick's omniScpTick line (ours after each).
  OmniBrowserSettings.h the omniScpRowSpeed declaration line (ours before it); the "D-pad left / right" row (ours
                        before it); omniFxSettingsInput's omniScpRowSpeed dispatch line (ours before it).
Apply AFTER apply_scroll_plus.py, apply_youtube_tv.py, apply_button_map.py, apply_high_contrast.py and
apply_ui_accent.py (their lines / names are used).
usage: apply_spatial_nav.py <engine tree>   (re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_SPATIAL_NAV_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'
ROW_IDS = (857,)

PURE = r'''// OMNI_SPATIAL_NAV_V1: the pure part of D-pad spatial navigation (a focus ring the D-pad moves between links,
// buttons and fields): the "D-pad navigation" setting, the ring's colours and width, the one page script (move /
// act / hide) with its arguments, its answers, CSS -> layout px, the one-in-flight queue and the ring's drop rules.
// No SDL, no WebKit. Shell side: OmniSpatialNavShell.h; the reasons (and why not WebKit's own spatial navigation)
// are in tools/apply_spatial_nav.py. Tested on the host with g++ (test_spatial_nav.cpp) and node
// (test_spatial_nav_js.cjs, the script on fake DOM layouts).
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>

namespace OmniSpatialNav {

constexpr int kRowId = 857;                       // Browser settings row "D-pad navigation"
constexpr const char* kFile = "spatial-nav.txt";  // /data/omni/spatial-nav.txt: "mode\t0|1\n"
constexpr uint32_t kStaleMs = 1500;               // an answer that never came stops blocking after this

// --- setting -----------------------------------------------------------------------------------------------------
enum Mode : int { kScroll, kLinks, kModeCount };
inline const char* modeName(int m)
{
    static const char* const n[kModeCount] = { "Scroll", "Move between links" };
    return n[std::clamp(m, 0, int(kModeCount) - 1)];
}
inline int parseMode(const std::string& text)
{
    size_t i = 0;
    while (i < text.size()) {
        size_t e = text.find('\n', i);
        if (e == std::string::npos) e = text.size();
        std::string line = text.substr(i, e - i);
        i = e + 1;
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.pop_back();
        if (line == "mode\t1") return kLinks;
        if (line == "mode\t0") return kScroll;
    }
    return kScroll;
}
inline std::string serialize(int mode) { return std::string("mode\t") + (mode == kLinks ? "1" : "0") + "\n"; }
// D-pad left / right (no wrap); Cross (dir 0): the other one.
inline int stepMode(int m, int dir)
{
    m = std::clamp(m, 0, int(kModeCount) - 1);
    if (dir == 0) return (m + 1) % kModeCount;
    return std::clamp(m + (dir < 0 ? -1 : 1), 0, int(kModeCount) - 1);
}

// --- directions (the script's D argument) ------------------------------------------------------------------------
enum Dir : int { kUp, kDown, kLeft, kRight };

// --- ring look ---------------------------------------------------------------------------------------------------
struct Rgb { uint8_t r = 0, g = 0, b = 0; };
inline double channel(uint8_t c)
{
    const double s = c / 255.0;
    return s <= 0.04045 ? s / 12.92 : std::pow((s + 0.055) / 1.055, 2.4);
}
inline double luminance(Rgb c) { return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b); }
inline double contrast(Rgb a, Rgb b)
{
    const double x = luminance(a), y = luminance(b);
    return (std::max(x, y) + 0.05) / (std::min(x, y) + 0.05);
}
// The 2 px halo inside and outside the accent ring: black or white, whichever contrasts more with the accent.
inline Rgb halo(Rgb accent)
{
    const Rgb black { 0, 0, 0 }, white { 255, 255, 255 };
    return contrast(accent, black) >= contrast(accent, white) ? black : white;
}
inline std::string hex(Rgb c)
{
    char s[8];
    snprintf(s, sizeof s, "#%02x%02x%02x", unsigned(c.r), unsigned(c.g), unsigned(c.b));
    return s;
}
// CSS px of the accent border (the page's zoom scales it with the page).
inline int ringWidth(bool highContrast) { return highContrast ? 6 : 4; }

// --- the page script ---------------------------------------------------------------------------------------------
// One function, called with (M, D, PX, PY, FP, C, H, W):
//   M  'm' move one step in direction D (0 up, 1 down, 2 left, 3 right)    -> "moved,<x>,<y>" | "none"
//      'a' act on the ring's element                                       -> "pt,<x>,<y>" | "field" | "clicked" | "none"
//      'h' hide the ring                                                   -> "hidden"
//   PX, PY  the pointer in viewport CSS px (-1: off the page); FP 1: start from the pointer, not the ring
//   C, H, W ring colour, halo colour ('#rrggbb'), ring width (CSS px). Any exception answers "err".
// x, y: the centre of the element's visible part in viewport CSS px (where Cross clicks; the hidden pointer goes
// there). State lives in the page under Symbol.for('omni.spatialnav.v1') (gone with the document).
// Candidates: links, buttons, form fields, summary, label[for], ARIA widget roles, [onclick], contenteditable,
// tabindex >= 0; at least 2x2 px, at most half the viewport, not disabled, not inside another candidate, not
// visibility:hidden, and when on screen the hit test at their centre must reach them (covered ones are skipped).
// Reach: on screen, or up to 3/4 of the viewport beyond the edge in the direction moved.
inline const char* core()
{
    return R"JS((function(M,D,PX,PY,FP,C,H,W){try{
var d=document,w=window,de=d.documentElement;if(!de)return'none';
var K=Symbol.for('omni.spatialnav.v1'),st=w[K];
if(!st){st={el:null,fe:null,ring:null,on:false,raf:0,lis:null};try{Object.defineProperty(w,K,{value:st,configurable:true});}catch(x){w[K]=st;}}
var S='a[href],area[href],button,input:not([type=hidden]),select,textarea,summary,label[for],[role=button],[role=link],[role=tab],[role=menuitem],[role=menuitemcheckbox],[role=menuitemradio],[role=checkbox],[role=radio],[role=switch],[role=option],[role=treeitem],[onclick],[contenteditable=""],[contenteditable=true],[tabindex]:not([tabindex="-1"])';
var VW=w.innerWidth||de.clientWidth,VH=w.innerHeight||de.clientHeight;
function R4(b){return{l:b.left,t:b.top,r:b.right,b:b.bottom};}
function onScreen(b){return b.bottom>0&&b.top<VH&&b.right>0&&b.left<VW;}
function unhook(){if(st.lis){w.removeEventListener('scroll',st.lis,true);w.removeEventListener('resize',st.lis,false);st.lis=null;}if(st.raf&&w.cancelAnimationFrame)w.cancelAnimationFrame(st.raf);st.raf=0;}
function hide(){unhook();if(st.ring&&st.ring.parentNode)st.ring.parentNode.removeChild(st.ring);st.on=false;}
function place(){st.raf=0;var e=st.el,g=st.ring;if(!g||!e||!e.isConnected){hide();return;}var b=e.getBoundingClientRect(),p=W+2,s=g.style;s.left=(b.left-p)+'px';s.top=(b.top-p)+'px';s.width=(b.width+2*p)+'px';s.height=(b.height+2*p)+'px';}
function show(e){st.el=e;if(!st.ring)st.ring=d.createElement('div');var g=st.ring;g.setAttribute('aria-hidden','true');
g.style.cssText='position:fixed;pointer-events:none;z-index:2147483647;box-sizing:border-box;margin:0;padding:0;background:transparent;border-radius:6px;border:'+W+'px solid '+C+';box-shadow:0 0 0 2px '+H+',inset 0 0 0 2px '+H+';';
if(g.parentNode!==de)de.appendChild(g);if(!st.lis){st.lis=function(){if(!st.raf)st.raf=w.requestAnimationFrame(place);};w.addEventListener('scroll',st.lis,true);w.addEventListener('resize',st.lis,false);}place();st.on=true;}
function tag(e){return(e.tagName||'').toLowerCase();}
function texty(e){var t=tag(e);if(t==='textarea'||t==='select'||e.isContentEditable)return true;if(t!=='input')return false;var y=(e.getAttribute('type')||'text').toLowerCase();return' checkbox radio button submit reset file image range color hidden '.indexOf(' '+y+' ')<0;}
function mid(e){var rs=e.getClientRects(),q=null;for(var i=0;i<rs.length;i++){if(rs[i].width>0&&rs[i].height>0&&onScreen(rs[i])){q=rs[i];break;}}if(!q)q=e.getBoundingClientRect();
var x0=Math.max(q.left,0),x1=Math.min(q.right,VW),y0=Math.max(q.top,0),y1=Math.min(q.bottom,VH);if(x1<x0)x1=x0;if(y1<y0)y1=y0;return[(x0+x1)/2,(y0+y1)/2];}
function hits(e){var m=mid(e),h=d.elementFromPoint(m[0],m[1]);return!!h&&(h===e||e.contains(h));}
function out(k,m){return k+','+m[0].toFixed(1)+','+m[1].toFixed(1);}
if(M==='h'){hide();return'hidden';}
if(M==='a'){var e=st.el;if(!st.on||!e||!e.isConnected){hide();return'none';}
if(!onScreen(e.getBoundingClientRect())){e.scrollIntoView({block:'nearest',inline:'nearest',behavior:'instant'});place();}
if(hits(e))return out('pt',mid(e));
if(texty(e)&&tag(e)!=='select'){e.focus();return'field';}
try{e.focus({preventScroll:true});}catch(x){}if(e.click)e.click();return'clicked';}
var list=d.querySelectorAll(S),all=[],set=new Set(),i;
for(i=0;i<list.length;i++){var el=list[i];if(el.disabled)continue;var bb=el.getBoundingClientRect();if(bb.width<2||bb.height<2||bb.width*bb.height>VW*VH*0.5)continue;all.push({e:el,c:R4(bb)});set.add(el);}
var cs=[];for(i=0;i<all.length;i++){var p=all[i].e.parentElement,inner=false;for(;p;p=p.parentElement)if(set.has(p)){inner=true;break;}if(!inner)cs.push(all[i]);}
var cur=null,R=null;
if(!FP&&st.el&&st.el.isConnected){var cb=st.el.getBoundingClientRect();if(onScreen(cb)){cur=st.el;R=R4(cb);}}
if(!R&&FP&&PX>=0&&PY>=0){var hp=d.elementFromPoint(PX,PY),hc=hp&&hp.closest?hp.closest(S):null;if(hc&&set.has(hc)){cur=hc;R=R4(hc.getBoundingClientRect());}else R={l:PX,t:PY,r:PX,b:PY};}
if(!R)R=D===1?{l:0,t:0,r:VW,b:0}:D===0?{l:0,t:VH,r:VW,b:VH}:D===3?{l:0,t:0,r:0,b:VH}:{l:VW,t:0,r:VW,b:VH};
var V=D<2,my=VH*0.75,mx=VW*0.75,best=[];
for(i=0;i<cs.length;i++){var c=cs[i].c;if(cs[i].e===cur)continue;
var ok=D===1?(c.t>=R.b-1||(c.t>R.t+1&&c.b>R.b+1)):D===0?(c.b<=R.t+1||(c.b<R.b-1&&c.t<R.t-1)):D===3?(c.l>=R.r-1||(c.l>R.l+1&&c.r>R.r+1)):(c.r<=R.l+1||(c.r<R.r-1&&c.l<R.l-1));
if(!ok)continue;
if(!(c.b>(D===0?-my:0)&&c.t<VH+(D===1?my:0)&&c.r>(D===2?-mx:0)&&c.l<VW+(D===3?mx:0)))continue;
var a1,a2,o1,o2,lo,hi;
if(V){a1=D===1?R.b:R.t;a2=D===1?c.t:c.b;lo=Math.max(R.l,c.l);hi=Math.min(R.r,c.r);if(lo<=hi){o1=o2=0;}else if(c.r<R.l){o1=R.l;o2=c.r;}else{o1=R.r;o2=c.l;}}
else{a1=D===3?R.r:R.l;a2=D===3?c.l:c.r;lo=Math.max(R.t,c.t);hi=Math.min(R.b,c.b);if(lo<=hi){o1=o2=0;}else if(c.b<R.t){o1=R.t;o2=c.b;}else{o1=R.b;o2=c.t;}}
var along=Math.max(0,(D===1||D===3)?a2-a1:a1-a2),orth=Math.abs(o2-o1);
var ix=Math.max(0,Math.min(R.r,c.r)-Math.max(R.l,c.l)),iy=Math.max(0,Math.min(R.b,c.b)-Math.max(R.t,c.t));
best.push({e:cs[i].e,s:Math.sqrt(along*along+orth*orth)+along+orth*(V?2:30)-Math.sqrt(ix*iy),n:best.length});}
best.sort(function(a,b){return a.s-b.s||a.n-b.n;});
var pick=null;
for(i=0;i<best.length&&i<16;i++){var e2=best[i].e,cs2=w.getComputedStyle?w.getComputedStyle(e2):null;if(cs2&&(cs2.visibility==='hidden'||cs2.visibility==='collapse'))continue;if(onScreen(e2.getBoundingClientRect())&&!hits(e2))continue;pick=e2;break;}
if(!pick)return'none';
var pb=pick.getBoundingClientRect();
if(!(pb.top>=0&&pb.bottom<=VH&&pb.left>=0&&pb.right<=VW)){pick.scrollIntoView({block:'nearest',inline:'nearest',behavior:'instant'});pb=pick.getBoundingClientRect();
var mg=Math.min(48,VH*0.08);if(pb.height<VH-2*mg){if(pb.top<mg)w.scrollBy({top:pb.top-mg,left:0,behavior:'instant'});else if(pb.bottom>VH-mg)w.scrollBy({top:pb.bottom-(VH-mg),left:0,behavior:'instant'});}}
if(st.fe&&st.fe!==pick&&d.activeElement===st.fe&&st.fe.blur)st.fe.blur();st.fe=null;
if(!texty(pick)){try{pick.focus({preventScroll:true});if(d.activeElement===pick)st.fe=pick;}catch(x){}}
show(pick);return out('moved',mid(pick));
}catch(err){return'err';}}))JS";
}
inline std::string num(double v)
{
    char s[32];
    snprintf(s, sizeof s, "%.1f", std::isfinite(v) ? std::clamp(v, -1.0e6, 1.0e6) : -1.0);
    return s;
}
// The whole script: core() + "(" arguments ")". Built here only; never trimmed (core() ends with its own ")").
inline std::string script(char mode, int dir, double px, double py, bool fromPointer, Rgb ring, Rgb haloColour, int width)
{
    const char m = mode == 'a' || mode == 'h' ? mode : 'm';
    std::string js = core();
    js += "('";
    js += m;
    js += "',";
    js += std::to_string(std::clamp(dir, 0, 3));
    js += ',' + num(px) + ',' + num(py) + ',' + (fromPointer ? "1" : "0");
    js += ",'" + hex(ring) + "','" + hex(haloColour) + "'," + std::to_string(std::clamp(width, 1, 12)) + ")";
    return js;
}

// --- answers -----------------------------------------------------------------------------------------------------
enum Kind : int { aBad, aMoved, aNone, aHidden, aPoint, aField, aClicked };
struct Answer { Kind kind = aBad; double x = 0, y = 0; };
inline bool number(const std::string& s, double& v)
{
    if (s.empty() || s.size() > 16 || s.find_first_not_of("-0123456789.") != std::string::npos) return false;
    char* end = nullptr;
    v = strtod(s.c_str(), &end);
    return end && *end == 0 && std::isfinite(v);
}
inline Answer parse(const std::string& s)
{
    Answer a;
    if (s == "none") { a.kind = aNone; return a; }
    if (s == "hidden") { a.kind = aHidden; return a; }
    if (s == "field") { a.kind = aField; return a; }
    if (s == "clicked") { a.kind = aClicked; return a; }
    const size_t c1 = s.find(','), c2 = c1 == std::string::npos ? c1 : s.find(',', c1 + 1);
    if (c2 == std::string::npos || s.size() > 48) return a;
    const std::string k = s.substr(0, c1);
    double x = 0, y = 0;
    if (!number(s.substr(c1 + 1, c2 - c1 - 1), x) || !number(s.substr(c2 + 1), y)) return a;
    if (k == "moved") a.kind = aMoved;
    else if (k == "pt") a.kind = aPoint;
    else return a;
    a.x = x; a.y = y;
    return a;
}

// --- coordinates: viewport CSS px -> the shell's layout px (k: CSS px per layout px, omniFxCssPerLayout) ----------
struct Pt { float x = 0, y = 0; };
inline Pt toLayout(double cssX, double cssY, double k, int pageTop, int pageBottom, int width)
{
    if (!(k > 0) || !std::isfinite(k)) k = 1;
    Pt p;
    p.x = float(std::clamp(cssX / k, 0.0, double(std::max(0, width - 1))));
    p.y = float(std::clamp(cssY / k + pageTop, double(pageTop), double(std::max(pageTop, pageBottom - 1))));
    return p;
}

// --- one move script in flight; a press meanwhile waits (the latest wins) -----------------------------------------
struct Flight {
    bool busy = false;
    int pending = -1;      // the direction pressed while busy, -1 none
    uint32_t since = 0;
    // true: send this press now. false: remembered (sent by done()).
    bool send(int dir, uint32_t now)
    {
        if (busy && uint32_t(now - since) < kStaleMs) { pending = dir; return false; }
        busy = true; since = now; pending = -1;
        return true;
    }
    // The answer came: the press to send next (-1 none).
    int done() { busy = false; const int p = pending; pending = -1; return p; }
    void reset() { busy = false; pending = -1; }
};

// --- the ring's life (shell state: shown, which tab, which address) -----------------------------------------------
enum Drop : int { kKeep, kDropTab, kDropPointer, kDropUrl, kDropMode };
inline Drop check(bool shown, const void* ringTab, const void* activeTab, bool pointerLeads, bool sameUrl, bool linkMode)
{
    if (!shown) return kKeep;
    if (!linkMode) return kDropMode;
    if (ringTab != activeTab) return kDropTab;
    if (pointerLeads) return kDropPointer;
    if (!sameUrl) return kDropUrl;
    return kKeep;
}
// The pointer is hidden while the ring leads on the tab that shows it.
inline bool pointerHidden(bool shown, bool pointerLeads, bool sameTab) { return shown && !pointerLeads && sameTab; }
// Cross goes to the ring's element (not the pointer) only then.
inline bool crossTakes(bool shown, bool sameTab, bool pointerLeads) { return shown && sameTab && !pointerLeads; }
// The next move starts from the pointer (not the ring) when no ring is shown on this tab.
inline bool fromPointer(bool shown, bool sameTab) { return !(shown && sameTab); }

} // namespace OmniSpatialNav
'''

SHELL = r'''// OMNI_SPATIAL_NAV_V1: D-pad spatial navigation (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's
// anonymous namespace, after OmniScrollPlusShell.h). The pure part is OmniSpatialNav.h; the reasons are in
// tools/apply_spatial_nav.py. Main thread only (WebKit's script callbacks come on the main run loop).
//   - Browser settings > "D-pad navigation": Scroll (as before) / Move between links.
//   - Link mode: D-pad = one page script that moves the focus ring (or answers "none": the page scrolls instead);
//     Cross = one script that answers where the ring's element is, then the usual click() there.
//   - The ring goes when the stick / a mouse moves the pointer, on another tab or address, or back in Scroll mode.
#pragma once

namespace OSPN = OmniSpatialNav;

static int omniOspnMode = OSPN::kScroll;
static bool omniOspnLoaded = false;
struct OmniOspnRing { bool shown = false; Tab* tab = nullptr; std::string url; };
static OmniOspnRing omniOspnRing;
static OSPN::Flight omniOspnFlight;
static Tab* omniOspnFlightTab = nullptr;          // the tab the move in flight was sent to
static bool omniOspnActing = false;               // a Cross script is out
static uint32_t omniOspnActAt = 0;
static uint32_t omniOspnGen = 1;                  // bumped when the ring is dropped: late answers are ignored

static void omniOspnLoad()
{
    if (omniOspnLoaded) return;
    omniOspnLoaded = true;
    std::string text;
    if (FILE* f = fopen(omniData(OSPN::kFile).c_str(), "r")) {
        char buf[128];
        const size_t n = fread(buf, 1, sizeof buf, f);
        fclose(f);
        text.assign(buf, n);
    }
    omniOspnMode = OSPN::parseMode(text);
}
static void omniOspnSave() { omniIoQueue(omniData(OSPN::kFile), OSPN::serialize(omniOspnMode), false); }
static bool omniOspnOn() { if (omniTestMode()) return false; omniOspnLoad(); return omniOspnMode == OSPN::kLinks; }
static bool omniOspnBrowsing()
{
    return active() && !active()->crashed && !editing && !pageEditing && !settingsOpen && !pageFullscreen && !omniOverlayOpen();
}
static OSPN::Rgb omniOspnRgb(SDL_Color c) { OSPN::Rgb r; r.r = c.r; r.g = c.g; r.b = c.b; return r; }
static std::string omniOspnScript(Tab* t, char mode, int dir)
{
    const double k = omniFxCssPerLayout(t);
    const bool fromPointer = OSPN::fromPointer(omniOspnRing.shown, omniOspnRing.tab == t);
    const bool onPage = pointerY >= omniPageTop() && pointerY < omniPageBottom();
    const double px = fromPointer && onPage ? pointerX * k : -1, py = fromPointer && onPage ? (pointerY - omniPageTop()) * k : -1;
    const OSPN::Rgb accent = omniOspnRgb(omniTheme().accent);
    return OSPN::script(mode, dir, px, py, fromPointer, accent, OSPN::halo(accent), OSPN::ringWidth(omniThemeIndex == omniHcThemeIndex()));
}
static void omniOspnRun(Tab* t, const std::string& js, uintptr_t context, void (*done)(WKTypeRef, WKErrorRef, void*))
{
    auto src = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), reinterpret_cast<void*>(context), done);
}
// Removes the ring from the active tab's page. Scripts only ever go to the active tab (WKPageEvaluateJavaScript*
// crashes on a suspended page, CRASH_IF_SUSPENDED): a ring left in a tab that went to the background is removed when
// that tab is active again (omniOspnStale).
static Tab* omniOspnStale = nullptr;
static void omniOspnHideIn(Tab* t)
{
    if (!t || !omniTabAlive(t) || t->crashed) return;
    if (t != active()) { omniOspnStale = t; return; }
    omniOspnRun(t, omniOspnScript(t, 'h', 0), 0, [](WKTypeRef, WKErrorRef, void*) { });
}
static void omniOspnDrop()
{
    omniOspnRing = OmniOspnRing();
    ++omniOspnGen;
    omniOspnFlight.reset();
    omniOspnFlightTab = nullptr;
    omniOspnActing = false;
    omniShellDirty = true;
}

// --- D-pad: move the ring ------------------------------------------------------------------------------------------
static void omniOspnSend(int dir);
static void omniOspnMoved(WKTypeRef result, WKErrorRef error, void* context)
{
    const uintptr_t c = reinterpret_cast<uintptr_t>(context);
    if (uint32_t(c >> 2) != omniOspnGen) return;   // the ring was dropped since (tab, address, pointer, mode)
    const int dir = int(c & 3);
    Tab* sentTo = omniOspnFlightTab;
    const int next = omniOspnFlight.done();
    Tab* t = active();
    if (!t || t != sentTo || !omniOspnOn() || !omniOspnBrowsing()) return;
    const OSPN::Answer a = OSPN::parse(omniFxResultString(result, error));
    if (a.kind == OSPN::aMoved) {
        if (omniPtrCross.active) { omniOspnHideIn(t); return; }   // the stick took over meanwhile
        omniOspnRing.shown = true; omniOspnRing.tab = t; omniOspnRing.url = t->url;
        // The hidden pointer follows the ring: held Cross (link menu), L2 chords and link preview act on its element.
        const OSPN::Pt p = OSPN::toLayout(a.x, a.y, omniFxCssPerLayout(t), omniPageTop(), omniPageBottom(), width);
        pointerX = p.x; pointerY = p.y; omniFxPtr.anim = false;
        omniShellDirty = true;
    } else if (a.kind == OSPN::aNone) {   // nothing that way: scroll as in Scroll mode (the step of "Scroll speed")
        const int step = omniScpDpadStep();
        if (dir == OSPN::kUp) scroll(step);
        else if (dir == OSPN::kDown) scroll(-step);
        else omniFxHorizontalScroll(dir == OSPN::kLeft ? step : -step);
    }
    if (next >= 0) omniOspnSend(next);
}
static void omniOspnSend(int dir)
{
    Tab* t = active();
    if (!t) return;
    if (!omniOspnFlight.send(dir, SDL_GetTicks())) return;   // one in flight: this press goes when it answers
    omniOspnFlightTab = t;
    omniOspnRun(t, omniOspnScript(t, 'm', dir), (uintptr_t(omniOspnGen) << 2) | uintptr_t(dir & 3), omniOspnMoved);
}
// button(), before omniFxDpadSide: true when link mode takes the D-pad (a page with no panel, keyboard or full screen;
// YouTube TV mode, built-in pages and overlays ran earlier in button()).
static bool omniOspnDpad(int b)
{
    int dir;
    switch (b) {
    case SDL_CONTROLLER_BUTTON_DPAD_UP: dir = OSPN::kUp; break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: dir = OSPN::kDown; break;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: dir = OSPN::kLeft; break;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: dir = OSPN::kRight; break;
    default: return false;
    }
    if (!omniOspnOn() || !omniOspnBrowsing()) return false;
    Tab* t = active();
    if (t->omniPaintHold.active) { t->omniPaintHold.cancel(); omniShellDirty = true; return true; }   // as omniPageWheel
    omniOspnSend(dir);
    return true;
}

// --- Cross: the ring's element ---------------------------------------------------------------------------------------
static void omniOspnActed(WKTypeRef result, WKErrorRef error, void* context)
{
    if (uint32_t(reinterpret_cast<uintptr_t>(context)) != omniOspnGen) return;
    omniOspnActing = false;
    Tab* t = active();
    if (!t || t != omniOspnRing.tab || !omniOspnBrowsing()) return;
    const OSPN::Answer a = OSPN::parse(omniFxResultString(result, error));
    switch (a.kind) {
    case OSPN::aPoint: {   // a real click there: links, buttons, <select> (Omni's list), text boxes (the keyboard)
        if (omniPtrCross.active) return;
        const OSPN::Pt p = OSPN::toLayout(a.x, a.y, omniFxCssPerLayout(t), omniPageTop(), omniPageBottom(), width);
        pointerX = p.x; pointerY = p.y; omniFxPtr.anim = false;
        click();
        omniShellDirty = true;
        break;
    }
    case OSPN::aField: fieldClickDeadline = SDL_GetTicks() + 2000; break;   // focused by the script: the keyboard opens
    case OSPN::aClicked: break;                                          // covered: the script clicked it itself
    default: omniOspnDrop(); break;                                      // gone (another page): the pointer shows again
    }
}
// button(), after the button map: Cross while the ring leads on this tab.
static bool omniOspnCross(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A || !omniOspnOn()) return false;
    Tab* t = active();
    if (!t || !OSPN::crossTakes(omniOspnRing.shown, omniOspnRing.tab == t, omniPtrCross.active) || !omniOspnBrowsing()) return false;
    const uint32_t now = SDL_GetTicks();
    if (omniOspnActing && uint32_t(now - omniOspnActAt) < OSPN::kStaleMs) return true;   // one at a time
    omniOspnActing = true; omniOspnActAt = now;
    omniOspnRun(t, omniOspnScript(t, 'a', 0), uintptr_t(omniOspnGen), omniOspnActed);
    return true;
}

// --- pointer, tick ---------------------------------------------------------------------------------------------------
// omniDrawPointer / omniPointerRect: hidden while the ring leads (panels, the keyboard, settings and full screen show it).
static bool omniOspnPointerHidden()
{
    return OSPN::pointerHidden(omniOspnRing.shown, omniPtrCross.active, omniOspnRing.tab == active())
        && !pageFullscreen && !editing && !settingsOpen && !omniOverlayOpen();
}
// omniF3Tick, every pass (returns at once without a ring).
static void omniOspnTick(uint32_t)
{
    if (omniOspnStale && (!omniTabAlive(omniOspnStale) || omniOspnStale == active())) {   // a ring left in a tab
        Tab* t = omniTabAlive(omniOspnStale) ? omniOspnStale : nullptr;
        omniOspnStale = nullptr;
        if (t && !(omniOspnRing.shown && omniOspnRing.tab == t)) omniOspnHideIn(t);
    }
    if (!omniOspnRing.shown) return;
    Tab* t = active();
    const bool sameUrl = t && t == omniOspnRing.tab && t->url == omniOspnRing.url;
    if (OSPN::check(true, omniOspnRing.tab, t, omniPtrCross.active, sameUrl, omniOspnOn()) == OSPN::kKeep) return;
    omniOspnHideIn(omniOspnRing.tab);   // also after a same-document address change (the page keeps the overlay)
    omniOspnDrop();
}

// --- Browser settings row (OSPN::kRowId, OmniBrowserSettings.h) ------------------------------------------------------
static void omniOspnSettingsRow(OmniFxPanel& p)
{
    omniOspnLoad();
    OmniFxRow r; r.id = OSPN::kRowId; r.label = "D-pad navigation"; r.value = OSPN::modeName(omniOspnMode); r.stepper = true;
    p.rows.push_back(r);
}
// D-pad left / right change, Cross steps, Triangle resets (Scroll).
static bool omniOspnSettingsInput(int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT;
    const bool cross = b == SDL_CONTROLLER_BUTTON_A, reset = b == SDL_CONTROLLER_BUTTON_Y;
    if (!left && !right && !cross && !reset) return false;
    omniOspnLoad();
    const int was = omniOspnMode;
    omniOspnMode = reset ? int(OSPN::kScroll) : OSPN::stepMode(omniOspnMode, cross ? 0 : left ? -1 : 1);
    if (omniOspnMode != was) {
        omniOspnSave();
        notice(omniOspnMode == OSPN::kLinks ? "D-pad moves a ring between links; the stick pointer still works" : "D-pad scrolls the page");
    }
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniScrollPlus.h" // OMNI_SCROLL_PLUS_V1: scroll speed, L2 + right stick page / end, position bar (pure)\n',
         '#include "OmniScrollPlus.h" // OMNI_SCROLL_PLUS_V1: scroll speed, L2 + right stick page / end, position bar (pure)\n'
         '#include "OmniSpatialNav.h" // OMNI_SPATIAL_NAV_V1: D-pad focus ring between links (pure)\n'),
        ('static bool omniYtTvPointerHidden();\n',
         'static bool omniYtTvPointerHidden();\n'
         '// OMNI_SPATIAL_NAV_V1 (definitions in OmniSpatialNavShell.h): the D-pad / Cross in "Move between links" mode.\n'
         'static bool omniOspnPointerHidden();\n'
         'static bool omniOspnDpad(int b);\n'
         'static bool omniOspnCross(int b);\n'),
        ('    if (omniYtTvPointerHidden()) return; // OMNI_YOUTUBE_TV_V1: the TV app is driven by the D-pad\n',
         '    if (omniYtTvPointerHidden()) return; // OMNI_YOUTUBE_TV_V1: the TV app is driven by the D-pad\n'
         '    if (omniOspnPointerHidden()) return; // OMNI_SPATIAL_NAV_V1: the focus ring leads (the stick shows the pointer)\n'),
        ('    if (omniYtTvPointerHidden()) return { 0, 0, 0, 0 }; // OMNI_YOUTUBE_TV_V1: hidden (its old rows are redrawn)\n',
         '    if (omniYtTvPointerHidden()) return { 0, 0, 0, 0 }; // OMNI_YOUTUBE_TV_V1: hidden (its old rows are redrawn)\n'
         '    if (omniOspnPointerHidden()) return { 0, 0, 0, 0 }; // OMNI_SPATIAL_NAV_V1: hidden while the focus ring leads\n'),
        ('    if (omniBmapBrowse(button)) return; // OMNI_BUTTON_MAP_V1: a remapped button (on its default: false, the lines below run)\n',
         '    if (omniBmapBrowse(button)) return; // OMNI_BUTTON_MAP_V1: a remapped button (on its default: false, the lines below run)\n'
         '    if (omniOspnCross(button)) return; // OMNI_SPATIAL_NAV_V1: Cross on the focus ring\'s element (link mode)\n'),
        ('    else if (omniFxDpadSide(button)) { } // OMNI_FEATURES_V1: D-pad left/right = back/forward (setting: switch tabs)\n',
         '    else if (omniOspnDpad(button)) { } // OMNI_SPATIAL_NAV_V1: "Move between links": the D-pad moves the focus ring\n'
         '    else if (omniFxDpadSide(button)) { } // OMNI_FEATURES_V1: D-pad left/right = back/forward (setting: switch tabs)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniScrollPlusShell.h" // OMNI_SCROLL_PLUS_V1\n',
         '#include "OmniScrollPlusShell.h" // OMNI_SCROLL_PLUS_V1\n'
         '#include "OmniSpatialNavShell.h" // OMNI_SPATIAL_NAV_V1 (after scroll plus: its D-pad step)\n'),
        ('    omniScpTick(now);   // OMNI_SCROLL_PLUS_V1: position bar fade, a remembered metrics query (only after a scroll)\n',
         '    omniScpTick(now);   // OMNI_SCROLL_PLUS_V1: position bar fade, a remembered metrics query (only after a scroll)\n'
         '    omniOspnTick(now);  // OMNI_SPATIAL_NAV_V1: drops the focus ring (pointer moved, other tab / address, Scroll mode)\n'),
    ],
    'OmniBrowserSettings.h': [
        ('constexpr int omniScpRowSpeed = 840, omniScpRowSmooth = 841; // OMNI_SCROLL_PLUS_V1 (OmniScrollPlusShell.h)\n',
         'static void omniOspnSettingsRow(OmniFxPanel& p); // OMNI_SPATIAL_NAV_V1: "D-pad navigation" (OmniSpatialNavShell.h, row id OSPN::kRowId = 857)\n'
         'static bool omniOspnSettingsInput(int b);\n'
         'constexpr int omniScpRowSpeed = 840, omniScpRowSmooth = 841; // OMNI_SCROLL_PLUS_V1 (OmniScrollPlusShell.h)\n'),
        ('    add(omniFxSetDpad, "D-pad left / right", omniFxSet.dpad ? "Switch tabs" : "Back / forward", true);\n',
         '    omniOspnSettingsRow(p); // OMNI_SPATIAL_NAV_V1: D-pad navigation (Scroll / Move between links)\n'
         '    add(omniFxSetDpad, "D-pad left / right", omniFxSet.dpad ? "Switch tabs" : "Back / forward", true);\n'),
        ('    if (r.id == omniScpRowSpeed || r.id == omniScpRowSmooth) return omniScpSettingsInput(r.id, b); // OMNI_SCROLL_PLUS_V1 (before the >= 300 rows)\n',
         '    if (r.id == OmniSpatialNav::kRowId) return omniOspnSettingsInput(b); // OMNI_SPATIAL_NAV_V1 (before the >= 300 rows)\n'
         '    if (r.id == omniScpRowSpeed || r.id == omniScpRowSmooth) return omniScpSettingsInput(r.id, b); // OMNI_SCROLL_PLUS_V1 (before the >= 300 rows)\n'),
    ],
}
NEW_FILES = ('OmniSpatialNav.h', 'OmniSpatialNavShell.h')


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


_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its comments (literals kept, newlines kept): an id in another patch's notes is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def ids_free():
    """Refuse when the settings row id is used in any entry file (sibling apply_*.py notes are not scanned)."""
    pat = re.compile(r'(?<![\w.])(%s)(?![\w.])' % '|'.join(str(i) for i in ROW_IDS))
    hits = []
    for p in sorted(root.iterdir()):
        if p.suffix not in ('.h', '.cpp', '.inc') or p.name in NEW_FILES:
            continue
        s = p.read_text('utf-8', 'replace')
        if MARK in s:
            s = '\n'.join(l for l in s.splitlines() if MARK not in l)
        for n, line in enumerate(cpp_code(s).split('\n'), 1):
            if pat.search(line):
                hits.append('%s:%d' % (p.name, n))
    if hits:
        sys.exit('settings row id %s is taken: %s' % (ROW_IDS, ', '.join(hits[:12])))


def main():
    need = (('OmniBrowser.cpp', 'OMNI_SCROLL_PLUS_V1', 'apply_scroll_plus.py'),
            ('OmniBrowser.cpp', 'OMNI_YOUTUBE_TV_V1', 'apply_youtube_tv.py'),
            ('OmniBrowser.cpp', 'OMNI_BUTTON_MAP_V1', 'apply_button_map.py'),
            ('OmniBrowser.cpp', 'OMNI_POINTER_CROSS_V1', 'the base tree (pointer cross)'),
            ('OmniBrowser.cpp', 'OMNI_HIGH_CONTRAST_V1', 'apply_high_contrast.py'),
            ('OmniBrowser.cpp', 'OMNI_UI_ACCENT_V1', 'apply_ui_accent.py'),
            ('OmniFeatures3.h', 'OMNI_SCROLL_PLUS_V1', 'apply_scroll_plus.py'),
            ('OmniBrowserSettings.h', 'OMNI_SCROLL_PLUS_V1', 'apply_scroll_plus.py'))
    for name, mark, tool in need:
        if mark not in (root / name).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (name, mark, tool))
    ob = (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8')
    for name in ('static int omniHcThemeIndex()', 'uint32_t fieldClickDeadline', 'static bool omniTabAlive(const void* tab)'):
        if name not in ob:
            sys.exit('OmniBrowser.cpp: %r missing' % name)
    ids_free()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniSpatialNav.h', PURE, 'OmniScrollPlus.h'),
            write_new('OmniSpatialNavShell.h', SHELL, 'OmniScrollPlusShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


if __name__ == '__main__':
    main()
