#!/usr/bin/env python3
"""(s3.1b copy: tick() anchor moved for s3's OmniAddons.h/OmniPages.h includes.) omni-youtube yt1: OMNI_YT_TIMELINE_V1 (measurement only, opt-in by /data/omni/yt-timeline.flag).
Applies to <tree>/engine/entry/OmniBrowser.cpp. Idempotent; every anchor must match exactly once.

The mode is production-like (NOT a self-test mode: uBlock, user agent per site and the user's settings stay as in
everyday use) but it never restores or saves the session. It loads the URL list from /data/omni/yt-timeline.txt one
after another (each one: navigate, then a downscaled copy of the presented canvas every `interval` ms for `seconds`,
shell events, page-paint stats, and a JSON summary from a measuring user script), writes the frames to
/data/omni/yttl/ and ends the title itself."""
import sys
from pathlib import Path
tree = Path(sys.argv[1] if len(sys.argv) > 1 else '/home/builder/yt')
p = tree / 'engine/entry/OmniBrowser.cpp'
s = p.read_text()
if 'OMNI_YT_TIMELINE_V1' in s:
    print('already applied'); sys.exit(0)

def sub(old, new, count=1):
    global s
    n = s.count(old)
    if n != count:
        sys.exit(f'anchor matched {n} times (want {count}): {old[:90]!r}')
    s = s.replace(old, new)

DECL = r'''bool youtubeTest = false;
// OMNI_YT_TIMELINE_V1 (measurement only): see omniYtTick()
bool ytTimeline = false;
struct OmniYtFrame { uint32_t ms; std::vector<uint32_t> px; unsigned paints, blocked, dirty, deferred, slow; double paintMs; bool loading, video; };
static struct OmniYtState {
    int stage = 0; uint32_t t0 = 0, last = 0, started = 0;
    std::vector<std::string> urls; size_t index = 0;
    unsigned seconds = 6, interval = 200;
    std::vector<OmniYtFrame> frames; std::vector<std::string> events;
    unsigned paints = 0, blocked = 0, dirty = 0, deferred = 0, slow = 0; double paintMs = 0;
    bool firstDirty = false, wasLoading = false, sawVideo = false, jsPending = false;
    int fw = 0, fh = 0;
} omniYt;
static void omniYtEvent(const char* what)
{
    if (!ytTimeline || !omniYt.t0 || omniYt.stage != 2 || omniYt.events.size() > 400) return;
    char b[200]; snprintf(b, sizeof b, "%u %s", SDL_GetTicks() - omniYt.t0, what); omniYt.events.emplace_back(b);
}'''
sub('bool youtubeTest = false;', DECL)

# page paint timing (every WKPagePaint)
sub('''    if (ms > 400) ++c.over400;
''', '''    if (ms > 400) ++c.over400;
    if (ytTimeline && omniYt.stage == 2) { // OMNI_YT_TIMELINE_V1
        ++omniYt.paints; omniYt.paintMs += ms;
        if (ms >= 100) { ++omniYt.blocked; char b[80]; snprintf(b, sizeof b, "page paint blocked %.0f ms", ms); omniYtEvent(b); }
    }
''')

# WebKit's pixel reports
sub('''        ++omniSplit.dirtyCalls; omniSplit.dirtyArea += r.size.width * r.size.height;
''', '''        ++omniSplit.dirtyCalls; omniSplit.dirtyArea += r.size.width * r.size.height;
        if (ytTimeline && omniYt.stage == 2) { ++omniYt.dirty; if (!omniYt.firstDirty) { omniYt.firstDirty = true; omniYtEvent("first pixels reported"); } } // OMNI_YT_TIMELINE_V1
''')

sub('''        if (featureTest) log("FEATURE DIAG: provisional navigation started");
''', '''        if (featureTest) log("FEATURE DIAG: provisional navigation started");
        if (ytTimeline) omniYtEvent("provisional navigation"); // OMNI_YT_TIMELINE_V1
''')

sub('''            if (wait) { ++omniCensus.deferred; omniPaintNow = false; }
''', '''            if (wait) { ++omniCensus.deferred; omniPaintNow = false; if (ytTimeline && omniYt.stage == 2) ++omniYt.deferred; } // OMNI_YT_TIMELINE_V1
''')
sub('''    const bool omniSlow = omniS1 && omniTab && !firstFrame && int32_t(omniNow - omniTab->omniSlowUntil) < 0;
''', '''    const bool omniSlow = omniS1 && omniTab && !firstFrame && int32_t(omniNow - omniTab->omniSlowUntil) < 0;
    if (ytTimeline && omniYt.stage == 2 && omniSlow) ++omniYt.slow; // OMNI_YT_TIMELINE_V1
''')

sub('''    youtubeTest = !access("/data/omni/youtube-selftest.flag", F_OK);
''', '''    youtubeTest = !access("/data/omni/youtube-selftest.flag", F_OK);
    ytTimeline = !access("/data/omni/yt-timeline.flag", F_OK); // OMNI_YT_TIMELINE_V1
''')

# everyday start: settings yes, session no (never restored, never saved: omniSessionReady stays false)
sub('''    if (omniTestMode()) return false;   // every self-test mode opens its own start page as before
''', '''    if (omniTestMode()) return false;   // every self-test mode opens its own start page as before
    if (ytTimeline) { omniPrefsLoad(); newTab(); log("yt timeline: everyday settings, one blank tab, no session"); return true; } // OMNI_YT_TIMELINE_V1
''')

# the measuring user script (main frame, document start)
JS = r'''(function(){if(window.top!==window||window.__omniYt)return;var T=function(){return Math.round(performance.now())};
var R=window.__omniYt={t:[],paint:[],lcp:[],fonts:[],raf:{n:0,gaps:[]},items:[]};function ev(n){R.t.push([T(),n]);}
document.addEventListener('DOMContentLoaded',function(){ev('dcl')});addEventListener('load',function(){ev('load')});
try{new PerformanceObserver(function(l){l.getEntries().forEach(function(e){R.paint.push([e.name,Math.round(e.startTime)])})}).observe({type:'paint',buffered:true})}catch(e){ev('no paint observer')}
try{new PerformanceObserver(function(l){l.getEntries().forEach(function(e){R.lcp.push([Math.round(e.startTime),e.size,(e.element&&e.element.tagName)||''])})}).observe({type:'largest-contentful-paint',buffered:true})}catch(e){ev('no lcp observer')}
try{document.fonts.addEventListener('loadingdone',function(e){R.fonts.push([T(),e.fontfaces.length])})}catch(e){}
var last=0;function f(ts){R.raf.n++;if(last&&ts-last>50)R.raf.gaps.push([Math.round(last),Math.round(ts-last)]);last=ts;if(performance.now()<20000)requestAnimationFrame(f);}requestAnimationFrame(f);
var iv=setInterval(function(){var t=T();var q=function(s){return document.querySelectorAll(s).length};var vis=0,ok=0;
document.querySelectorAll('img').forEach(function(i){var r=i.getBoundingClientRect();if(r.bottom>0&&r.top<innerHeight&&r.width>40){vis++;if(i.complete&&i.naturalWidth>0)ok++;}});
var v=document.querySelector('video');R.items.push([t,q('ytd-app'),q('ytd-masthead,#masthead'),q('ytd-rich-item-renderer,ytd-video-renderer,ytd-reel-video-renderer,ytd-compact-video-renderer,ytd-rich-grid-media'),vis,ok,v?v.readyState:-1,v?Math.round(v.currentTime*1000):-1,document.readyState.charAt(0)]);
if(t>20000)clearInterval(iv);},250);
window.__omniYtDump=function(){var res=performance.getEntriesByType('resource'),by={},dns=0,tcp=0,tls=0,firstImg=null,lastEnd=0;
res.forEach(function(e){var k=e.initiatorType||'other';var b=by[k]||(by[k]={n:0,kb:0,cached:0,maxEnd:0});b.n++;b.kb+=Math.round((e.transferSize||0)/1024);if(!e.transferSize)b.cached++;b.maxEnd=Math.max(b.maxEnd,Math.round(e.responseEnd));
if(e.domainLookupEnd>e.domainLookupStart)dns+=e.domainLookupEnd-e.domainLookupStart;if(e.connectEnd>e.connectStart)tcp+=e.connectEnd-e.connectStart;if(e.secureConnectionStart>0)tls+=e.connectEnd-e.secureConnectionStart;
if(k=='img'&&(firstImg===null||e.startTime<firstImg))firstImg=e.startTime;lastEnd=Math.max(lastEnd,e.responseEnd);});
var n=performance.getEntriesByType('navigation')[0];var txt=document.body?document.body.innerText:'';
return {path:location.pathname,ua:navigator.userAgent.slice(0,150),ev:R.t,paint:R.paint,lcp:R.lcp.slice(-2),fonts:R.fonts,
raf:{n:R.raf.n,busy:R.raf.gaps.reduce(function(a,g){return a+g[1]},0),gaps:R.raf.gaps.slice(0,40)},items:R.items,
res:{n:res.length,by:by,dns:Math.round(dns),tcp:Math.round(tcp),tls:Math.round(tls),firstImg:firstImg===null?null:Math.round(firstImg),lastEnd:Math.round(lastEnd)},
nav:n?{dns:Math.round(n.domainLookupEnd-n.domainLookupStart),tcp:Math.round(n.connectEnd-n.connectStart),ttfb:Math.round(n.responseStart),resp:Math.round(n.responseEnd),dcl:Math.round(n.domContentLoadedEventEnd),load:Math.round(n.loadEventEnd),kb:Math.round((n.transferSize||0)/1024)}:null,
unsupported:/browser isn.t supported|update your browser/i.test(txt),consent:/consent\.|before you continue/i.test(location.href+' '+document.title),
vp9:(function(){try{return MediaSource.isTypeSupported('video/webm; codecs="vp9"')}catch(e){return null}})(),
q:(function(){try{var p=document.querySelector('#movie_player');return p&&p.getPlaybackQuality?p.getPlaybackQuality():null}catch(e){return null}})()};};})();'''
sub('''        status = ready ? "Ready" : "Ad blocking unavailable: rules could not be loaded.";
''', '''        if (ytTimeline) { // OMNI_YT_TIMELINE_V1: the measuring script (main frame, document start)
            static const char* ytJs = R"OMNIYTJS(''' + JS + ''')OMNIYTJS";
            auto source = adoptWK(WKStringCreateWithUTF8CString(ytJs));
            auto script = adoptWK(WKUserScriptCreateWithSource(source.get(), kWKInjectAtDocumentStart, true));
            omniBlockerAddShellScript(script.get());
        }
        status = ready ? "Ready" : "Ad blocking unavailable: rules could not be loaded.";
''')

TICK = r'''
// OMNI_YT_TIMELINE_V1 ---------------------------------------------------------------------------
// One URL after another from /data/omni/yt-timeline.txt (`url <u>` lines, optional `seconds N`, `interval N`; about:blank
// between runs keeps the web process and its memory cache, so "url X" twice = cold app then warm visit). Per run: a
// downscaled copy of the canvas every `interval` ms (what the presenter shows), shell events, page-paint counters and
// the measuring script's JSON. Frames go to /data/omni/yttl/r<N>-<idx>-<ms>.png at the end of each run. Ends the title.
static void omniYtCapture(uint32_t ms)
{
    auto& y = omniYt;
    if (!canvas || !canvas->pixels) return;
    const int f = std::max(1, canvas->w / 480);
    y.fw = canvas->w / f; y.fh = canvas->h / f;
    OmniYtFrame fr; fr.ms = ms; fr.px.resize(size_t(y.fw) * y.fh);
    const uint8_t* base = static_cast<const uint8_t*>(canvas->pixels);
    for (int r = 0; r < y.fh; ++r) {
        const uint32_t* src = reinterpret_cast<const uint32_t*>(base + size_t(r * f) * canvas->pitch);
        uint32_t* d = fr.px.data() + size_t(r) * y.fw;
        for (int c = 0; c < y.fw; ++c) d[c] = src[c * f];
    }
    fr.paints = y.paints; fr.blocked = y.blocked; fr.dirty = y.dirty; fr.deferred = y.deferred; fr.slow = y.slow; fr.paintMs = y.paintMs;
    fr.loading = active() && active()->loading; fr.video = OmniMedia::Hw::holePunchActive();
    y.frames.push_back(std::move(fr));
}
static void omniYtFinishRun()
{
    auto& y = omniYt;
    mkdir("/data/omni/yttl", 0777);
    char line[400];
    for (size_t i = 0; i < y.frames.size(); ++i) {
        const auto& fr = y.frames[i];
        char path[160]; snprintf(path, sizeof path, "/data/omni/yttl/r%zu-%02zu-%05u.png", y.index, i, fr.ms);
        omniWritePng(path, reinterpret_cast<const unsigned char*>(fr.px.data()), y.fw, y.fh, y.fw * 4);
        snprintf(line, sizeof line, "YTTL frame run=%zu i=%zu ms=%u paints=%u paintMs=%.0f blocked=%u reports=%u deferred=%u slowTicks=%u loading=%d video=%d",
            y.index, i, fr.ms, fr.paints, fr.paintMs, fr.blocked, fr.dirty, fr.deferred, fr.slow, fr.loading ? 1 : 0, fr.video ? 1 : 0);
        log(line);
    }
    for (const auto& e : y.events) { snprintf(line, sizeof line, "YTTL event run=%zu %s", y.index, e.c_str()); log(line); }
    y.frames.clear(); y.frames.shrink_to_fit(); y.events.clear();
}
static void omniYtTick()
{
    if (!ytTimeline || !active()) return;
    auto& y = omniYt;
    const uint32_t now = SDL_GetTicks();
    if (y.stage == 0) {
        if (now - stageTime < 2500) return;
        if (FILE* file = fopen("/data/omni/yt-timeline.txt", "r")) {
            char buf[1200];
            while (fgets(buf, sizeof buf, file)) {
                std::string l(buf); while (!l.empty() && (l.back() == '\n' || l.back() == '\r' || l.back() == ' ')) l.pop_back();
                if (l.rfind("url ", 0) == 0) y.urls.push_back(l.substr(4));
                else if (l.rfind("seconds ", 0) == 0) y.seconds = std::clamp(atoi(l.c_str() + 8), 2, 30);
                else if (l.rfind("interval ", 0) == 0) y.interval = std::clamp(atoi(l.c_str() + 9), 100, 2000);
            }
            fclose(file);
        }
        if (y.urls.empty()) { log("YTTL DONE: no urls"); running = false; y.stage = 9; return; }
        char line[120]; snprintf(line, sizeof line, "YTTL start: %zu runs, %u s each, a frame every %u ms", y.urls.size(), y.seconds, y.interval); log(line);
        y.stage = 1; y.last = now; return;
    }
    if (y.stage == 1) {
        if (now - y.last < 2000 || active()->loading) return;
        y.frames.clear(); y.events.clear(); y.paints = y.blocked = y.dirty = y.deferred = y.slow = 0; y.paintMs = 0;
        y.firstDirty = y.sawVideo = false; y.wasLoading = false; y.t0 = now; y.stage = 2;
        char line[1300]; snprintf(line, sizeof line, "YTTL run %zu: %s", y.index, y.urls[y.index].c_str()); log(line);
        omniYtEvent("navigate");
        navigate(y.urls[y.index]);
        return;
    }
    if (y.stage == 2) {
        const uint32_t ms = now - y.t0;
        const bool loading = active()->loading;
        if (loading != y.wasLoading) { omniYtEvent(loading ? "loading" : "load finished (shell)"); y.wasLoading = loading; }
        if (!y.sawVideo && OmniMedia::Hw::holePunchActive()) { y.sawVideo = true; omniYtEvent("video plane active"); }
        if (y.frames.empty() || ms - y.frames.back().ms >= y.interval) omniYtCapture(ms);
        if (ms >= y.seconds * 1000) {
            y.stage = 3; y.jsPending = true; y.last = now;
            auto script = adoptWK(WKStringCreateWithUTF8CString("JSON.stringify(window.__omniYtDump?window.__omniYtDump():{error:'no data',path:location.pathname})"));
            WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), nullptr, [](WKTypeRef result, WKErrorRef error, void*) {
                std::string v = !error && result && WKGetTypeID(result) == WKStringGetTypeID() ? OmniTest::toStd(static_cast<WKStringRef>(result)) : std::string("{\"error\":\"evaluate failed\"}");
                std::string line = "YTTL js run=" + std::to_string(omniYt.index) + " " + v;
                fprintf(stderr, "browser: %s\n", line.c_str()); fflush(stderr);
                omniYt.jsPending = false;
            });
        }
        return;
    }
    if (y.stage == 3) {
        if (y.jsPending && now - y.last < 8000) return;
        if (y.jsPending) log("YTTL js timeout");
        omniYtFinishRun();
        if (++y.index < y.urls.size()) {
            auto blank = adoptWK(WKURLCreateWithUTF8CString("about:blank")); WKPageLoadURL(active()->page, blank.get());
            y.stage = 1; y.last = now;
        } else { log("YTTL DONE"); y.stage = 9; running = false; }
    }
}
'''
# s3.1b: s3 has OmniAddons.h + OmniPages.h between the OMNI_FEATURES_V3 include and tick()
sub('''#include "OmniPages.h" // s3 OMNI_PAGES_V1: omni://pages built-in pages
void tick(void*)
''', '''#include "OmniPages.h" // s3 OMNI_PAGES_V1: omni://pages built-in pages
''' + TICK + '''void tick(void*)
''')
sub('''    omniEverydayTick(); // OMNI_EVERYDAY_V1: re-issued loads, session save (background write)
''', '''    omniEverydayTick(); // OMNI_EVERYDAY_V1: re-issued loads, session save (background write)
    omniYtTick(); // OMNI_YT_TIMELINE_V1 (opt-in measurement)
''')
# no test visits in the user's history (OMNI_YT_TIMELINE_V1)
sub('if (omniTestMode() || tab.omniPrivate || omniMediaOwns(tab)', 'if (omniTestMode() || ytTimeline || tab.omniPrivate || omniMediaOwns(tab)')
s = s.replace('    mkdir("/data/omni/yttl", 0777);', '    ::mkdir("/data/omni/yttl", 0777);')
p.write_text(s)
print('patched', p)
