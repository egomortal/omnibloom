#!/usr/bin/env python3
"""OMNI_IMAGE_VIEWER_V1 (2026-11-16): an image viewer. A tab that shows an image by itself (WebKit's ImageDocument:
a .jpg / .png / .webp / .gif address opened directly) opens it in the viewer, and the hold-Cross page menu over a
picture has "View image" (first of the picture's rows; the hit test already gives the image address, fixed by
OMNI_SAVE_IMAGE_V1). The picture is fitted to the screen on black.

Approach: (b), a page-side viewer driven by the shell. Why not (a), an Omni overlay that decodes itself:
  - the title links libpng only (OmniPng.cpp writes, the screenshot gallery reads PNG with it on a worker); there is
    no libjpeg / libwebp / gif decoder reachable from the shell (WebKit's decoders live in the web process), so JPEG,
    WebP and GIF would need new decoders in the title;
  - the bytes: the UI process can't read WebKit's memory cache, and handing a blob to the shell through script means
    base64 through the evaluateJavaScript reply (20 MB of pixels = 27 MB of string, twice in memory) or Omni's own
    fetch (new networking, cookies / referrer rules, private tabs). Both cost more than they give.
  (b) costs one small script: the page's own image loader / decoder shows the picture (same cache, same cookies,
  animated GIF / WebP animate, nothing fetched or decoded by Omni), and input is reliable because the SHELL owns the
  controller while the viewer is up (an overlay layer, as the screenshot gallery's), sending the page plain numbers.
  WebKit's Gamepad API isn't used (the page gets no pad input while an Omni layer is open: omniGamepadTick's
  omniUiOpen), so no page can see or steal the controls.

What the user sees
  - Image address opened directly (address bar, "Open image in new tab", a link to a picture): when it finishes
    loading in the shown tab (or a background tab that loaded one is shown), the viewer opens by itself. Circle closes
    it to WebKit's own image page; that tab then stays closed until it loads something again (Dismissed).
  - Page menu over a picture: "View image" (not on Omni's own pages or the Downloads tab; http(s), file:, blob: and
    data:image/ addresses). The page's pictures at least 200 px both ways (natural or shown size; <img> only, the
    main frame, currentSrc || src, absolute, once each, at most 400) are collected once, in page order; the chosen one
    is the start (added first when it is not among them: a background image or a smaller one).
  - Top line (over the address bar, black): "3 / 12   photo.jpg" (name as Save image's notice; "Embedded image" for
    data:, "Image" for blob:). Hints: D-pad "Previous / next" (only with more than one), Cross "Fit / actual size",
    Square "Save", Circle "Close", note "R2 / L2: zoom   Left stick: move" (RT / LT with Xbox labels).
  - Controls while it is up (Omni owns them; the browsing meanings stand down because they all check
    omniOverlayOpen(): R2 / L2 media shortcuts, L2 chords, L1 + R1, tab switching):
      R2 / L2 (analogue)    zoom in / out about the screen centre, 4x per second fully pressed (dead zone 3000)
      D-pad up / down       zoom in / out one step (1.25x)
      right stick up / down zoom (gentle)
      left stick            move around the zoomed picture (1400 px/s fully over, the pointer stays hidden and goes
                            back where it was on close)
      D-pad left / right, L1 / R1   previous / next picture ("This is the first / last image" at the ends;
                            "No other pictures on this page" for one)
      Cross (or Cross at the pointer)   fit <-> actual size (2.5x when the picture is small)
      Square                save it: the page menu's Save image (omniSviSave: to Downloads, or WebKit's own save in
                            a private tab / with Media downloads off, exactly as that row; Downloads coming forward
                            closes the viewer, as switching tabs does)
      Circle                close; Options / Create close it and open their menus as usual
      Triangle, L3, R3, touchpad    nothing (and nothing reaches the page)
    Zoom range: fit (1) .. max(8x, 4x the picture's own pixels). The view is kept inside the picture; a picture
    smaller than the screen stays centred on that axis.
  - The viewer closes by itself when the tab is switched, navigates, reloads, crashes, goes full screen, Browser
    settings or the keyboard open, or the page removes its element (asked once a second while idle).
  - Private tabs: works the same; nothing is stored anywhere (no list, no history, no files; the dismissed page is
    remembered in memory for that tab only).

Page side (OmniImageViewer::kLibrary, the page's main world; nothing else in the page is changed): an
<omni-image-viewer> element on <html>, position fixed over everything (z-index 2147483647), black, the picture and a
"Couldn't load this image" message in a closed shadow root. Styles only through style.setProperty(..., 'important')
(CSSOM, allowed under a strict style-src CSP; page rules can't reach into the shadow root). window.__omniImv (v 1):
open / input / go / toggle / alive / close, each answering a short string. The library is sent once with open; then
each input is one fixed call with numbers. One input script is in flight at a time; stick / trigger movement adds up
until the page answers (OmniImageViewer::Pending), so a slow page never builds a queue. Image page check (kProbe):
document.contentType image/* with exactly one image -> its address (one tiny script per finished load of the shown
tab, for http(s) / file: / data:image / blob: addresses only).

Pure part: engine/entry/OmniImageViewer.h (addresses, trigger / stick maths, Pending, Dismissed, caption, scripts).
Shell part: engine/entry/OmniImageViewerShell.h (state, overlay layer, tick, openings, page menu row), included from
OmniFeatures3.h after OmniTextSelectShell.h. Namespace alias OIMV; names omniImv*; page menu row id 9760
(OmniImageViewer::kContextId; pinned tabs 960, QR 975; refused when the tree already uses 9760).
Anchors (each once; whole lines kept, the new lines go before / after them; inserted lines use /* */ comments):
  OmniBrowser.cpp     '#include "OmniSaveImage.h" ...' (pure include after);
                      'static void omniEverydayFinished(Tab& tab);' (omniImvFinished / omniImvActivated declared after);
                      '    omniFndFinished(tab); ...' in omniEverydayFinished (omniImvFinished(tab) after);
                      '    omniWapActivated(tab); ...' in omniEverydayActivated (omniImvActivated(tab) after);
                      'static bool omniMagHidesPointer(); ...' (declaration after) and its use in omniDrawPointer
                      (the viewer hides the pointer too: line after)
  OmniContextMenu.h   'static bool omniTslContextAction(OmniFxPanel& p, int id);' (declarations after);
                      '        add(omniCxOpenImage, "Open image in new tab", !four);' (the View image row before);
                      '    if (omniRlContextAction(r.id)) return true; ...' (the row's action before)
  OmniFeatures3.h     '#include "OmniTextSelectShell.h" ...' (shell include after); '    omniDlpTick(now); ...' in
                      omniF3Tick (omniImvTick(now) after)
Needs OMNI_SAVE_IMAGE_V1 (omniSviSave, OmniSaveImage.h), OMNI_TEXT_SELECT_V1 and OMNI_DL_PROGRESS_V1 first.
Tests: tools/test_image_viewer.cpp (g++ -std=c++20 -I<tree>/engine/entry; `--emit DIR` writes the assembled scripts
for node --check); tools/test_image_viewer_js.cjs <OmniImageViewer.h> (node: the page script on a mock DOM).
Controls guide rows (OmniControlsHelp.h, not edited here): see the report of this change.
usage: apply_image_viewer.py <engine tree>   (anchored, idempotent, keeps CRLF; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_IMAGE_VIEWER_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_IMAGE_VIEWER_V1: the pure part of the image viewer (no SDL, no WebKit): when a tab shows an image by itself
// (WebKit's ImageDocument) or the page menu's "View image" is chosen, the image is shown fit to the screen on black
// by a small overlay the shell puts INTO the page (closed shadow root, CSSOM styles only), driven by the controller
// through the shell: R2 / L2 (analogue) and D-pad up / down zoom, the left stick pans, D-pad left / right (L1 / R1)
// steps through the page's own <img> pictures (at least 200 px both ways, collected once), Cross toggles fit /
// actual size, Square saves (the page menu's Save image path), Circle closes. Omni fetches and decodes nothing
// itself: the page's own image loader shows the picture (no new networking, no new decoders).
// Shell side: OmniImageViewerShell.h; reasons in tools/apply_image_viewer.py. Tests: tools/test_image_viewer.cpp
// (g++) and tools/test_image_viewer_js.cjs (node: the page script below on a mock DOM).
#pragma once
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <string>
#include "OmniSaveImage.h"

namespace OmniImageViewer {

constexpr int kContextId = 9760;               // hold-Cross page menu row "View image" (pinned 960, QR 975)
constexpr int kTriggerDead = 3000;             // R2 / L2 below this (of 32767) do nothing
constexpr float kZoomPerSecond = 1.3862944f;   // ln 4: a fully pressed trigger zooms 4x per second
constexpr float kStepZoom = 0.22314355f;       // ln 1.25: one D-pad up / down press
constexpr float kWheelZoom = 0.0005f;          // per scroll() unit (right stick / wheel): about 5x per second at full stick
constexpr float kPanPerSecond = 1400.f;        // layout px per second, left stick fully over
constexpr float kPanCurve = 1.8f;              // gentle near the dead zone
constexpr float kMaxStepZoom = 3.f;            // one input script never zooms more than e^3
constexpr uint32_t kAliveMs = 1000;            // idle: ask the page once a second whether the overlay is still there
constexpr uint32_t kAnswerMs = 1500;           // an input script that never answers no longer holds the next one back
constexpr size_t kMaxUrl = 2u << 20;           // data: images up to 2 MB of text are passed to the page script

inline bool startsNoCase(const std::string& s, const char* prefix) { return OmniSaveImage::startsNoCase(s, prefix); }

// Addresses the viewer shows: http(s), file:, blob: (the page's own) and data:image/... Never javascript: / about:.
inline bool viewable(const std::string& url)
{
    if (url.empty() || url.size() > kMaxUrl) return false;
    return startsNoCase(url, "http://") || startsNoCase(url, "https://") || startsNoCase(url, "file:")
        || startsNoCase(url, "blob:") || startsNoCase(url, "data:image/");
}
// Pages worth asking "are you an image by itself?" when they finish loading (one tiny script, the active tab only).
inline bool probeWorthy(const std::string& url)
{
    return startsNoCase(url, "http://") || startsNoCase(url, "https://") || startsNoCase(url, "file:")
        || startsNoCase(url, "data:image/") || startsNoCase(url, "blob:");
}

// Where the viewer would open. busy: the keyboard, Browser settings, a page in full screen or another overlay is up.
struct Where {
    bool testMode = false, pagesTab = false, downloadsTab = false, crashed = false, busy = false;
};
inline bool canOpen(const Where& w) { return !w.testMode && !w.pagesTab && !w.downloadsTab && !w.crashed && !w.busy; }

// R2 / L2 (0..32767) -> change of log zoom for dt seconds (R2 in, L2 out; both pressed cancel).
inline float triggerAmount(int v)
{
    if (v <= kTriggerDead) return 0.f;
    const float a = float(v - kTriggerDead) / float(32767 - kTriggerDead);
    return a > 1.f ? 1.f : a;
}
inline float triggerZoom(int l2, int r2, float dt) { return (triggerAmount(r2) - triggerAmount(l2)) * kZoomPerSecond * dt; }

// Left stick (-32768..32767) -> how far the view moves (layout px) in dt seconds; radial dead zone `dead` (fraction).
inline void stickPan(int lx, int ly, float dead, float dt, float& dx, float& dy)
{
    dx = dy = 0;
    const float sx = lx / 32768.f, sy = ly / 32768.f, r = std::hypot(sx, sy);
    if (!(r > dead) || dead >= 1.f) return;
    float m = (r - dead) / (1.f - dead);
    if (m > 1.f) m = 1.f;
    const float speed = kPanPerSecond * std::pow(m, kPanCurve) * dt;
    dx = sx / r * speed;
    dy = sy / r * speed;
}

// Input gathered between page answers: one input script in flight at a time, the rest adds up meanwhile.
struct Pending {
    double dz = 0, dx = 0, dy = 0;
    bool inflight = false;
    uint32_t sentAt = 0;
    void add(double z, double x, double y) { dz += z; dx += x; dy += y; }
    bool any() const { return std::fabs(dz) > 1e-4 || std::fabs(dx) > 0.05 || std::fabs(dy) > 0.05; }
    bool ready(uint32_t now) const { return !inflight || uint32_t(now - sentAt) >= kAnswerMs; }
    bool take(uint32_t now, double& z, double& x, double& y)
    {
        if (!any() || !ready(now)) return false;
        z = dz > kMaxStepZoom ? kMaxStepZoom : dz < -kMaxStepZoom ? -kMaxStepZoom : dz;
        x = dx; y = dy;
        dz = dx = dy = 0;
        inflight = true; sentAt = now;
        return true;
    }
    void answered() { inflight = false; }
    void clear() { *this = Pending(); }
};

// An image page the user closed the viewer on: not opened again by itself until that tab loads something.
struct Dismissed {
    const void* tab = nullptr;
    std::string url;
    bool is(const void* t, const std::string& u) const { return tab && t == tab && u == url; }
    void note(const void* t, const std::string& u) { tab = t; url = u; }
    void clear() { tab = nullptr; url.clear(); }
};

// The top line: "3 / 12   photo.jpg" ("photo.jpg" alone for a single image).
inline std::string caption(int i, int n, const std::string& src)
{
    std::string name = startsNoCase(src, "data:") ? std::string("Embedded image")
        : startsNoCase(src, "blob:") ? std::string("Image") : OmniSaveImage::shown(OmniSaveImage::fileName(src, "image"));
    if (n <= 1) return name;
    return std::to_string(i + 1) + " / " + std::to_string(n) + "   " + name;
}
inline const char* zoomNote(bool playStation)
{
    return playStation ? "R2 / L2: zoom   Left stick: move" : "RT / LT: zoom   Left stick: move";
}
inline const char* endNotice(int i) { return i <= 0 ? "This is the first image" : "This is the last image"; }

// A JavaScript string literal for any UTF-8 text (quotes, backslashes, controls, '<', U+2028 / U+2029 escaped).
inline std::string jsQuote(const std::string& s)
{
    std::string o = "'";
    o.reserve(s.size() + 8);
    for (size_t i = 0; i < s.size(); ++i) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        if (c == '\\' || c == '\'' || c == '"') { o += '\\'; o += char(c); }
        else if (c == '\n') o += "\\n";
        else if (c == '\r') o += "\\r";
        else if (c < 0x20 || c == 0x7f || c == '<' || c == '>') { char b[8]; snprintf(b, sizeof(b), "\\x%02x", c); o += b; }
        else if (c == 0xE2 && i + 2 < s.size() && static_cast<unsigned char>(s[i + 1]) == 0x80
            && (static_cast<unsigned char>(s[i + 2]) == 0xA8 || static_cast<unsigned char>(s[i + 2]) == 0xA9)) {
            o += static_cast<unsigned char>(s[i + 2]) == 0xA8 ? "\\u2028" : "\\u2029";
            i += 2;
        } else o += char(c);
    }
    return o + "'";
}

// The page side (main frame, the page's world; read only except for its own element). window.__omniImv (v 1):
//   open(start, all) -> {"n","i","src"} ('{}': nothing to show); all: the page's <img> (currentSrc || src, absolute,
//                       once each, both natural or shown sides >= 200 px, at most 400) with start among them (added
//                       first when it is not, e.g. a background image or a small one)
//   input(dz, dx, dy) -> '1' / '0' (overlay gone): zoom by e^dz about the screen centre (1 = fit .. max(8, 4 / fit)),
//                       move the view by dx, dy CSS px (kept inside the picture)
//   go(step) -> {"n","i","src","e"} (e 1: no image that way); toggle() fit <-> actual size (2.5x for small ones);
//   alive() -> '1' / '0'; close() -> '1' (element removed, nothing left behind).
// The element is <omni-image-viewer> on <html>, position fixed over everything (z-index 2147483647), black, its
// picture and message inside a closed shadow root; every style is set with style.setProperty(..., 'important')
// (CSSOM: allowed under a strict style-src CSP, and page rules can't reach into the shadow root).
static const char* const kLibrary = R"JS((function(){var W=window;if(W.__omniImv&&W.__omniImv.v===1)return;
var D=document,S=null,MIN=200,MAX=400;
function css(e,o){for(var k in o)e.style.setProperty(k,o[k],'important');}
function abs(u){try{return new URL(u,D.baseURI).href;}catch(_){return String(u||'');}}
function vp(){var de=D.documentElement;return{w:W.innerWidth||(de&&de.clientWidth)||1,h:W.innerHeight||(de&&de.clientHeight)||1};}
function collect(start){var out=[],seen={},ims=D.images||[];
for(var i=0;i<ims.length&&out.length<MAX;i++){var m=ims[i],s=m.currentSrc||m.src;if(!s||/^(javascript|about):/i.test(s))continue;s=abs(s);if(seen[s])continue;
var r={width:0,height:0};try{r=m.getBoundingClientRect();}catch(_){}
var w=Math.max(m.naturalWidth||0,r.width||0),h=Math.max(m.naturalHeight||0,r.height||0);if(w>=MIN&&h>=MIN){seen[s]=1;out.push(s);}}
var k=start?out.indexOf(start):-1;if(start&&k<0){out.unshift(start);if(out.length>MAX)out.length=MAX;k=0;}
return{list:out,i:k<0?0:k};}
function build(){var host=D.createElement('omni-image-viewer');
css(host,{position:'fixed',left:'0',top:'0',right:'0',bottom:'0',width:'100%',height:'100%',margin:'0',padding:'0',border:'0',background:'#000',
'z-index':'2147483647',display:'block',overflow:'hidden',transform:'none',filter:'none',opacity:'1',visibility:'visible'});
var root=host;try{if(host.attachShadow)root=host.attachShadow({mode:'closed'});}catch(_){}
var img=D.createElement('img');img.alt='';try{img.draggable=false;img.decoding='async';}catch(_){}
css(img,{position:'absolute',left:'0',top:'0',margin:'0',padding:'0',border:'0','max-width':'none','max-height':'none','min-width':'0','min-height':'0',
'transform-origin':'0 0',visibility:'hidden',background:'transparent'});
var msg=D.createElement('div');css(msg,{position:'absolute',left:'0',right:'0',top:'45%','text-align':'center',color:'#bbb',font:'24px sans-serif',display:'none'});
root.appendChild(img);root.appendChild(msg);(D.documentElement||D.body).appendChild(host);
return{host:host,img:img,msg:msg};}
function fitS(){var v=vp();return S.nw>0&&S.nh>0?Math.min(v.w/S.nw,v.h/S.nh):1;}
function zmax(){return Math.max(8,4/fitS());}
function lay(){if(!S||S.state!==1)return;var v=vp(),s=fitS()*S.z,mx=Math.max(0,(S.nw*s-v.w)/2),my=Math.max(0,(S.nh*s-v.h)/2);
S.tx=Math.max(-mx,Math.min(mx,S.tx));S.ty=Math.max(-my,Math.min(my,S.ty));
var x=(v.w-S.nw*s)/2-S.tx,y=(v.h-S.nh*s)/2-S.ty;
S.el.img.style.setProperty('transform','translate('+x.toFixed(2)+'px,'+y.toFixed(2)+'px) scale('+s.toFixed(6)+')','important');}
function zoomTo(z){if(!(z>0))return;z=Math.max(1,Math.min(zmax(),z));S.tx*=z/S.z;S.ty*=z/S.z;S.z=z;}
function fail(){var e=S.el;css(e.img,{visibility:'hidden'});e.msg.textContent='Couldn\'t load this image';css(e.msg,{display:'block'});}
function show(){var e=S.el,img=e.img,tok=++S.tok;S.z=1;S.tx=0;S.ty=0;S.nw=0;S.nh=0;S.state=0;
css(img,{visibility:'hidden'});e.msg.textContent='';css(e.msg,{display:'none'});
img.onload=function(){if(!S||tok!==S.tok||S.state===1)return;S.nw=img.naturalWidth||0;S.nh=img.naturalHeight||0;
if(!(S.nw>0&&S.nh>0)){S.state=2;fail();return;}S.state=1;css(img,{width:S.nw+'px',height:S.nh+'px'});lay();css(img,{visibility:'visible'});};
img.onerror=function(){if(!S||tok!==S.tok)return;S.state=2;fail();};
img.src=S.list[S.i];if(img.complete&&img.naturalWidth)img.onload();}
function alive(){return!!(S&&S.el.host.parentNode&&S.el.host.isConnected!==false);}
function info(e){return JSON.stringify({n:S.list.length,i:S.i,src:S.list[S.i],e:e?1:0});}
try{W.addEventListener('resize',function(){if(S)lay();});}catch(_){}
W.__omniImv={v:1,
open:function(start,all){start=start?abs(start):'';var L=all?collect(start):{list:start?[start]:[],i:0};if(!L.list.length)return'{}';
if(!alive()){if(S&&S.el.host.parentNode)S.el.host.parentNode.removeChild(S.el.host);S={el:build(),tok:0};}
S.list=L.list;S.i=L.i;show();return info(0);},
input:function(dz,dx,dy){if(!alive())return'0';if(S.state===1){if(dz)zoomTo(S.z*Math.exp(dz));S.tx+=+dx||0;S.ty+=+dy||0;lay();}return'1';},
go:function(d){if(!alive())return'{}';var j=S.i+(d<0?-1:1);if(j<0||j>=S.list.length)return info(1);S.i=j;show();return info(0);},
toggle:function(){if(!alive())return'0';if(S.state!==1)return'1';if(S.z>1.05)zoomTo(1);else{var a=1/fitS();zoomTo(a>=1.5?a:2.5);}S.tx=0;S.ty=0;lay();return'1';},
alive:function(){return alive()?'1':'0';},
close:function(){if(S&&S.el.host.parentNode)S.el.host.parentNode.removeChild(S.el.host);S=null;return'1';}};
})()
)JS";

// "Is this tab an image by itself?" WebKit's ImageDocument: an image/* document whose only picture is the page.
// Answers that picture's address, '' otherwise. (Both raw strings end "})()" + newline: the ")JS" delimiter would
// otherwise take the call's last ')', the trap OMNI_SAVE_IMAGE_V1 fixed in the page menu's probe.)
static const char* const kProbe = R"JS((function(){try{var d=document,m=d.images;if(!/^image\//i.test(d.contentType||'')||!m||m.length!==1)return'';var s=m[0].currentSrc||m[0].src||'';return String(s);}catch(e){return'';}})()
)JS";

inline std::string call(const std::string& body)   // one fixed method of the page object, '0' when it isn't there
{
    return "(function(){var v=window.__omniImv;return v&&v.v===1?v." + body + ":'0';})()";
}
inline std::string openScript(const std::string& start, bool all)
{
    return std::string("(function(){") + kLibrary + ";var v=window.__omniImv;return v&&v.v===1?v.open(" + jsQuote(start)
        + (all ? ",1" : ",0") + "):'{}';})()";
}
inline std::string inputScript(double dz, double dx, double dy)
{
    char b[96];
    snprintf(b, sizeof(b), "input(%.5f,%.2f,%.2f)", dz, dx, dy);
    return call(b);
}
inline std::string goScript(int step) { return call("go(" + std::to_string(step < 0 ? -1 : 1) + ")"); }
inline std::string toggleScript() { return call("toggle()"); }
inline std::string aliveScript() { return call("alive()"); }
inline std::string closeScript() { return call("close()"); }
inline std::string probeScript() { return kProbe; }

} // namespace OmniImageViewer
'''

SHELL = r'''// OMNI_IMAGE_VIEWER_V1: the shell side of the image viewer (pure part: OmniImageViewer.h; reasons in
// tools/apply_image_viewer.py). The picture is drawn by the page (an overlay element the page script below puts in);
// the shell owns the controller while it is up: an overlay layer (blocksPage, so the page gets no pointer events and
// the browsing-only R2 / L2 / shoulder shortcuts stand down: they all check omniOverlayOpen()), a per-pass tick that
// reads R2 / L2 and the left stick, and the top caption + hints. Nothing is stored (private tabs included); Square uses
// the page menu's Save image (omniSviSave: Downloads, or WebKit's own save in a private tab).
// Included from OmniFeatures3.h after OmniTextSelectShell.h (OmniContextMenu.h's omniSviSave / omniFxJson* are above).
#pragma once
namespace OIMV = OmniImageViewer;

enum { omniImvOpenCall = 1, omniImvGoCall, omniImvInputCall, omniImvAliveCall, omniImvProbeCall, omniImvOtherCall };
struct OmniImvState {
    bool open = false, opening = false, autoOpened = false;
    const void* tab = nullptr;   // the tab it is shown in (Tab*), checked with omniTabAlive
    std::string url;             // that tab's address when it opened (a navigation closes the viewer)
    int n = 0, i = 0;            // images, current one
    std::string src;             // the current picture's address (caption, Square)
    uint32_t gen = 0, lastTick = 0, lastAlive = 0;
    float ptrX = 0, ptrY = 0;    // the pointer goes back here on close (the left stick pans meanwhile)
    OIMV::Pending pending;
};
static OmniImvState omniImv;
static OIMV::Dismissed omniImvDismissed;
struct OmniImvCall { uint32_t gen; const void* tab; int kind; std::string url; };

static bool omniImvShown() { return omniImv.open && omniFxStack.empty(); }
static bool omniImvHidesPointer() { return omniImvShown(); }
static Tab* omniImvTab() { return omniTabAlive(omniImv.tab) ? static_cast<Tab*>(const_cast<void*>(omniImv.tab)) : nullptr; }
static void omniImvAnswer(const OmniImvCall& c, const std::string& result);
static void omniImvEval(Tab* t, const std::string& js, int kind)
{
    if (!t || !t->page) return;
    auto src = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    auto* c = new OmniImvCall { omniImv.gen, t, kind, t->url };
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), c, [](WKTypeRef result, WKErrorRef error, void* context) {
        std::unique_ptr<OmniImvCall> c(static_cast<OmniImvCall*>(context));
        omniImvAnswer(*c, omniFxResultString(result, error));
    });
}
static OIMV::Where omniImvWhere(Tab* t)
{
    OIMV::Where w;
    w.testMode = omniTestMode();
    w.pagesTab = t->omniPagesTab;
    w.downloadsTab = t->omniMediaSection;
    w.crashed = t->crashed;
    w.busy = editing || settingsOpen || pageFullscreen || omniOverlayOpen();
    return w;
}
// byUser: Circle / Options / Create (an image page opened by itself then stays closed until the tab loads again).
static void omniImvClose(bool byUser)
{
    if (!omniImv.open && !omniImv.opening) return;
    Tab* t = omniImvTab();
    if (t && !t->crashed) {   // the element goes away even when the tab is no longer the shown one
        auto js = adoptWK(WKStringCreateWithUTF8CString(OIMV::closeScript().c_str()));
        WKPageEvaluateJavaScriptInMainFrame(t->page, js.get(), nullptr, [](WKTypeRef, WKErrorRef, void*) { });
    }
    if (byUser && omniImv.autoOpened) omniImvDismissed.note(omniImv.tab, omniImv.url);
    if (omniImv.open) { pointerX = omniImv.ptrX; pointerY = omniImv.ptrY; }
    ++omniImv.gen;
    omniImv.open = omniImv.opening = false;
    omniImv.pending.clear();
    omniShellDirty = true;
}
static void omniImvStart(Tab* t, const std::string& start, bool all, bool autoOpen)
{
    if (!t || omniImv.open || omniImv.opening) return;
    if (!OIMV::canOpen(omniImvWhere(t)) || !OIMV::viewable(start)) {
        if (!autoOpen) notice("This image can't be shown in the viewer");
        return;
    }
    ++omniImv.gen;
    omniImv.opening = true;
    omniImv.autoOpened = autoOpen;
    omniImv.tab = t;
    omniImv.url = t->url;
    omniImv.pending.clear();
    omniImvEval(t, OIMV::openScript(start, all), omniImvOpenCall);
}
static void omniImvTakeInfo(const std::string& r)
{
    double n = 0, i = 0;
    std::string src;
    if (omniFxJsonNumber(r, "n", n)) omniImv.n = int(n);
    if (omniFxJsonNumber(r, "i", i)) omniImv.i = int(i);
    if (omniFxJsonString(r, "src", src)) omniImv.src = src;
}
static void omniImvAnswer(const OmniImvCall& c, const std::string& r)
{
    if (c.kind == omniImvProbeCall) {   // an image page finished loading: open by itself (unless closed on it before)
        Tab* t = active();
        if (r.empty() || !t || t != c.tab || t->url != c.url || omniImv.open || omniImv.opening || omniImvDismissed.is(t, t->url)) return;
        omniImvStart(t, r, false, true);
        return;
    }
    if (c.gen != omniImv.gen || c.tab != omniImv.tab || !omniTabAlive(c.tab)) return;   // an older opening / closed since
    switch (c.kind) {
    case omniImvOpenCall: {
        omniImv.opening = false;
        double n = 0;
        Tab* t = omniImvTab();
        const bool ok = omniFxJsonNumber(r, "n", n) && n >= 1;
        if (!ok || !t || active() != t || t->url != omniImv.url || !OIMV::canOpen(omniImvWhere(t))) {
            omniImv.opening = true;   // so omniImvClose takes the element away again
            omniImvClose(false);
            if (!ok && !omniImv.autoOpened) notice("Couldn't open the image viewer on this page");
            return;
        }
        omniImvTakeInfo(r);
        omniImv.open = true;
        omniImv.ptrX = pointerX; omniImv.ptrY = pointerY;
        omniImv.lastTick = omniImv.lastAlive = SDL_GetTicks();
        omniShellDirty = true;
        break;
    }
    case omniImvGoCall: {
        double e = 0, n = 0;
        if (!omniFxJsonNumber(r, "n", n)) { omniImvClose(false); return; }   // the page dropped the overlay
        if (omniFxJsonNumber(r, "e", e) && e > 0) notice(OIMV::endNotice(omniImv.i));
        omniImvTakeInfo(r);
        omniShellDirty = true;
        break;
    }
    case omniImvInputCall:
        omniImv.pending.answered();
        if (r != "1") omniImvClose(false);
        break;
    case omniImvAliveCall:
        if (r != "1") omniImvClose(false);
        break;
    default:
        if (r == "0") omniImvClose(false);
        break;
    }
}

// --- the overlay layer ---------------------------------------------------------------------------------------------
static bool omniImvButton(int b)
{
    Tab* t = omniImvTab();
    if (!t) { omniImvClose(false); return false; }
    omniShellDirty = true;
    switch (b) {
    case SDL_CONTROLLER_BUTTON_B: omniImvClose(true); return true;
    case SDL_CONTROLLER_BUTTON_START: case SDL_CONTROLLER_BUTTON_BACK: omniImvClose(true); return false;   // their menus open as usual
    case SDL_CONTROLLER_BUTTON_A: omniImvEval(t, OIMV::toggleScript(), omniImvOtherCall); break;   // fit <-> actual size
    case SDL_CONTROLLER_BUTTON_X:   // Square: the page menu's Save image (Downloads; WebKit's own save in a private tab)
        if (!omniImv.src.empty()) { const std::string src = omniImv.src; omniSviSave(src, true); }
        break;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: case SDL_CONTROLLER_BUTTON_LEFTSHOULDER:
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: {
        const int step = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT || b == SDL_CONTROLLER_BUTTON_LEFTSHOULDER ? -1 : 1;
        if (omniImv.n <= 1) { notice("No other pictures on this page"); break; }
        omniImvEval(t, OIMV::goScript(step), omniImvGoCall);
        break;
    }
    case SDL_CONTROLLER_BUTTON_DPAD_UP: omniImv.pending.add(OIMV::kStepZoom, 0, 0); break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: omniImv.pending.add(-OIMV::kStepZoom, 0, 0); break;
    default: break;   // Triangle, L3, R3, touchpad: nothing (the page under the viewer gets nothing either)
    }
    return true;
}
static bool omniImvClick(int, int) { omniImvButton(SDL_CONTROLLER_BUTTON_A); return true; }   // Cross at the pointer
static bool omniImvScroll(double amount) { omniImv.pending.add(amount * OIMV::kWheelZoom, 0, 0); return true; }   // right stick: zoom
static void omniImvDraw()
{
    const int pageTop = omniPageTop(), band = std::max(pageTop, 40);
    if (pageTop > 0) omniRectPx({ 0, 0, canvas->w, physical(pageTop) }, { 0, 0, 0, 255 });   // the bars above the page: black
    if (pageTop < 40) omniRectPx({ 0, 0, canvas->w, physical(40) }, { 0, 0, 0, 255 }, 150);
    omniLabel(OIMV::caption(omniImv.i, omniImv.n, omniImv.src), 20, band / 2.f, omniSmall, { 255, 255, 255, 255 }, 0, width - 40);
    std::vector<std::pair<int, const char*>> faces;
    if (omniImv.n > 1) faces.push_back({ omniHintDpadH, "Previous / next" });
    faces.push_back({ 0, "Fit / actual size" });
    faces.push_back({ 2, "Save" });
    faces.push_back({ 1, "Close" });
    omniPanelHints(faces, OIMV::zoomNote(playStationIcons));
}
[[maybe_unused]] static const bool omniImvLayer = [] {
    omniOverlayLayers().push_back({ omniImvShown, omniImvButton, omniImvClick, omniImvScroll, omniImvDraw, true });
    return true;
}();

// omniF3Tick(): the tab must still be the shown one at the same address; R2 / L2 and the left stick become one input
// script at a time (the rest adds up until the page answers); idle, the page is asked once a second (it may have
// dropped the element).
static void omniImvTick(uint32_t now)
{
    if (!omniImv.open) return;
    Tab* t = omniImvTab();
    if (!t || t != active() || t->crashed || t->url != omniImv.url || editing || settingsOpen || pageFullscreen) { omniImvClose(false); return; }
    const float dt = std::clamp((now - omniImv.lastTick) / 1000.f, 0.f, 0.05f);
    omniImv.lastTick = now;
    if (omniFxStack.empty() && controller && SDL_GameControllerGetAttached(controller)) {
        const float dz = OIMV::triggerZoom(SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_TRIGGERLEFT),
            SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_TRIGGERRIGHT), dt);
        float dx = 0, dy = 0;
        OIMV::stickPan(SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_LEFTX), SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_LEFTY),
            omniStickDeadZone(false), dt, dx, dy);
        const double k = omniFxCssPerLayout(t);   // layout px -> the page's CSS px
        omniImv.pending.add(dz, dx * k, dy * k);
    }
    double z = 0, x = 0, y = 0;
    if (omniImv.pending.take(now, z, x, y)) { omniImvEval(t, OIMV::inputScript(z, x, y), omniImvInputCall); omniImv.lastAlive = now; }
    else if (!omniImv.pending.inflight && uint32_t(now - omniImv.lastAlive) >= OIMV::kAliveMs) {
        omniImv.lastAlive = now;
        omniImvEval(t, OIMV::aliveScript(), omniImvAliveCall);
    }
}

// --- openings --------------------------------------------------------------------------------------------------------
// finished(): a new document in that tab (the old element is gone with the old one); the active tab is asked whether it
// is an image by itself.
static void omniImvProbe(Tab* t)
{
    if (!t || t != active() || t->loading || omniImv.open || omniImv.opening || !OIMV::probeWorthy(t->url)) return;
    if (!OIMV::canOpen(omniImvWhere(t)) || omniImvDismissed.is(t, t->url)) return;
    omniImvEval(t, OIMV::probeScript(), omniImvProbeCall);
}
static void omniImvFinished(Tab& tab)
{
    if (omniImv.tab == &tab && (omniImv.open || omniImv.opening)) omniImvClose(false);
    if (omniImvDismissed.tab == &tab) omniImvDismissed.clear();
    omniImvProbe(&tab);
}
static void omniImvActivated(Tab* tab) { omniImvProbe(tab); }   // a background tab that loaded an image, shown now

// The page menu (hold Cross over a picture): "View image", the first of the picture's rows.
static void omniImvContextRow(OmniFxPanel& p)
{
    Tab* t = active();
    if (!t || p.image.empty() || !OIMV::viewable(p.image) || t->omniPagesTab || t->omniMediaSection) return;
    OmniFxRow r; r.id = OIMV::kContextId; r.label = "View image";
    p.rows.push_back(r);
}
static bool omniImvContextAction(OmniFxPanel& p, int id)
{
    if (id != OIMV::kContextId) return false;
    const std::string image = p.image;   // the panel goes away with omniFxCloseAll
    omniFxCloseAll();
    omniImvStart(active(), image, true, false);
    return true;
}
'''

C = '/* ' + MARK + ' */'
EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSaveImage.h" // OMNI_SAVE_IMAGE_V1: page menu Save image / Save link target -> Downloads (pure)\n',
         '#include "OmniSaveImage.h" // OMNI_SAVE_IMAGE_V1: page menu Save image / Save link target -> Downloads (pure)\n'
         '#include "OmniImageViewer.h" /* ' + MARK + ': image pages / View image, the page-side viewer (pure) */\n'),
        ('static void omniEverydayFinished(Tab& tab);\n',
         'static void omniEverydayFinished(Tab& tab);\n'
         'static void omniImvFinished(Tab& tab); /* ' + MARK + ' (OmniImageViewerShell.h) */\n'
         'static void omniImvActivated(Tab* tab); ' + C + '\n'),
        ("    omniFndFinished(tab); // OMNI_FIND_PLUS_V1: a navigation closes this tab's find bar (query kept)\n",
         "    omniFndFinished(tab); // OMNI_FIND_PLUS_V1: a navigation closes this tab's find bar (query kept)\n"
         '    omniImvFinished(tab); /* ' + MARK + ': an image page opens in the viewer; a new document closes it */\n'),
        ('    omniWapActivated(tab); // OMNI_WEB_APPS_V1: and its Web apps tiles, if they changed\n',
         '    omniWapActivated(tab); // OMNI_WEB_APPS_V1: and its Web apps tiles, if they changed\n'
         '    omniImvActivated(tab); /* ' + MARK + ': a background tab that loaded an image page */\n'),
        ('static bool omniMagHidesPointer(); // OMNI_MAGNIFIER_V1 (OmniMagnifierShell.h)\n',
         'static bool omniMagHidesPointer(); // OMNI_MAGNIFIER_V1 (OmniMagnifierShell.h)\n'
         'static bool omniImvHidesPointer(); /* ' + MARK + ' (OmniImageViewerShell.h) */\n'),
        ('    if (omniMagHidesPointer()) return; // OMNI_MAGNIFIER_V1: the lens is up; its crosshair marks the pointer\n',
         '    if (omniMagHidesPointer()) return; // OMNI_MAGNIFIER_V1: the lens is up; its crosshair marks the pointer\n'
         '    if (omniImvHidesPointer()) return; /* ' + MARK + ': the viewer is up; the left stick moves the picture */\n'),
    ],
    'OmniContextMenu.h': [
        ('static bool omniTslContextAction(OmniFxPanel& p, int id);\n',
         'static bool omniTslContextAction(OmniFxPanel& p, int id);\n'
         'static void omniImvContextRow(OmniFxPanel& p); /* ' + MARK + ' (OmniImageViewerShell.h) */\n'
         'static bool omniImvContextAction(OmniFxPanel& p, int id); ' + C + '\n'),
        ('        add(omniCxOpenImage, "Open image in new tab", !four);\n',
         '        omniImvContextRow(p); /* ' + MARK + ': View image (first of the picture rows) */\n'
         '        add(omniCxOpenImage, "Open image in new tab", !four);\n'),
        ('    if (omniRlContextAction(r.id)) return true; // OMNI_READING_LIST_V1\n',
         '    if (omniImvContextAction(p, r.id)) return true; ' + C + '\n'
         '    if (omniRlContextAction(r.id)) return true; // OMNI_READING_LIST_V1\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniTextSelectShell.h" // OMNI_TEXT_SELECT_V1: Select text (page menu row, selecting layer, actions)\n',
         '#include "OmniTextSelectShell.h" // OMNI_TEXT_SELECT_V1: Select text (page menu row, selecting layer, actions)\n'
         '#include "OmniImageViewerShell.h" /* ' + MARK + ': the image viewer (after the page menu and Save image) */\n'),
        ('    omniDlpTick(now);   // OMNI_DL_PROGRESS_V1: Downloads progress (polls only while jobs run / after a hand-over)\n',
         '    omniDlpTick(now);   // OMNI_DL_PROGRESS_V1: Downloads progress (polls only while jobs run / after a hand-over)\n'
         '    omniImvTick(now);   /* ' + MARK + ': viewer input (R2 / L2, left stick) and its checks */\n'),
    ],
}
NEEDS = [('OmniBrowser.cpp', 'OMNI_SAVE_IMAGE_V1', 'apply_save_image.py'),
         ('OmniFeatures3.h', 'OMNI_TEXT_SELECT_V1', 'apply_text_select.py'),
         ('OmniFeatures3.h', 'OMNI_DL_PROGRESS_V1', 'apply_dl_progress.py')]
TAKEN = [re.compile(r'\b9760\b'), re.compile(r'\bomniImv\w*'), re.compile(r'\bOIMV\b'), re.compile(r'__omniImv')]


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


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def ids_free():
    """Before the first apply: the row id and our names must not be used anywhere in the tree yet."""
    for f in sorted(root.iterdir()):
        if f.suffix not in ('.h', '.cpp', '.inc') or f.name in ('OmniImageViewer.h', 'OmniImageViewerShell.h'):
            continue
        s = cpp_code(f.read_bytes().decode('utf-8', 'replace'))
        for rx in (TAKEN[:1] if f.name in GUIDE else TAKEN):
            m = rx.search(s)
            if m:
                sys.exit('%s: %r already used (%s): choose another id / alias' % (f.name, m.group(0), MARK))


def main():
    for name, mark, tool in NEEDS:
        if mark not in (root / name).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (name, mark, tool))
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        ids_free()
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniImageViewer.h', PURE, 'OmniSaveImage.h'),
            write_new('OmniImageViewerShell.h', SHELL, 'OmniTextSelectShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
