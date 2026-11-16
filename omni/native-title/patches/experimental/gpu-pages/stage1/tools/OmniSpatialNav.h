// OMNI_SPATIAL_NAV_V1: the pure part of D-pad spatial navigation (a focus ring the D-pad moves between links,
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
