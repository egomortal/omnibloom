// OMNI_FEATURES_V3: dark pages. A global switch (Browser settings) and a per-site choice (Site
// settings, quick menu): Default / Always dark / Never dark, stored in /data/omni/site-dark.txt.
// Two parts, both cheap for the shell (nothing is drawn by Omni itself):
//  1. The page's "dark appearance" (WKPageSetUseDarkAppearanceForTesting): prefers-color-scheme
//     matches dark, so sites with their own dark theme use it.
//  2. A user script (document start, main frame, isolated world "omni-dark") that, once <body>
//     exists and again at DOMContentLoaded / load / +1.5 s, measures the page's own background.
//     Already dark: nothing more. Light: html gets filter: invert(1) hue-rotate(180deg), and images,
//     video, picture, canvas, iframes, embeds and elements with a background image get the same
//     filter again, so they keep their real colours. Fullscreen turns the filter off.
// The per-site list is handed to the script by small "config" user scripts with a version number
// (the newest wins), because the shared user-content controller has no way to remove one script;
// open pages are switched at once through a data-omni-dark attribute on <html>.
#pragma once

static std::unordered_map<std::string, int> omniDkSites;   // host -> 1 always dark, 0 never
static bool omniDkLoaded = false, omniDkInstalled = false;
static int omniDkVersion = 0;
static std::unordered_map<const void*, int> omniDkApplied;  // tab -> dark appearance sent (0/1)
static void omniDkLoad()
{
    if (omniDkLoaded) return;
    omniDkLoaded = true;
    if (FILE* f = fopen(omniData("site-dark.txt").c_str(), "r")) {
        char line[600];
        while (fgets(line, sizeof(line), f) && omniDkSites.size() < 400) {
            std::string s(line);
            while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
            const size_t t = s.find('\t');
            if (t == std::string::npos || t == 0) continue;
            omniDkSites[s.substr(0, t)] = s.compare(t + 1, std::string::npos, "1") == 0 ? 1 : 0;
        }
        fclose(f);
    }
}
static void omniDkSave()
{
    std::string s;
    for (auto& [h, v] : omniDkSites) s += omniOneLine(h, 255) + "\t" + (v ? "1" : "0") + "\n";
    omniIoQueue(omniData("site-dark.txt"), std::move(s), false);
}
static std::string omniDkHost(const std::string& url)
{
    std::string h = omniLower(omniBlockerHostOf(url));
    if (h.rfind("www.", 0) == 0) h = h.substr(4);
    return h;
}
static int omniDkSite(const std::string& host) { omniDkLoad(); auto f = omniDkSites.find(host); return f == omniDkSites.end() ? -1 : f->second; }
static bool omniDkWant(const std::string& url)
{
    if (omniTestMode() || !omniWebURL(url)) return false;
    omniF3Load();
    const int s = omniDkSite(omniDkHost(url));
    return s < 0 ? omniF3Set.dark : s == 1;
}

static const char* const omniDkLogic = R"JS((function(){
if(window.__omniDarkApply)return;
var D=document,fs=false,timer=0;
var M='html[data-omnidark] ';
var CSS='html[data-omnidark]{filter:invert(1) hue-rotate(180deg)!important}'
+'html[data-omnidark][data-omnidark-bg]{background-color:var(--omni-dark-bg,#fff)!important}'
+M+'img,'+M+'video,'+M+'picture,'+M+'canvas,'+M+'iframe,'+M+'embed,'+M+'object,'+M+'svg image,'+M+'[style*="background-image"]{filter:invert(1) hue-rotate(180deg)!important}'
+M+'picture img,'+M+'picture video,'+M+'[style*="background-image"] img,'+M+'[style*="background-image"] video,'+M+'[style*="background-image"] [style*="background-image"]{filter:none!important}';
function want(){var e=D.documentElement;if(!e||!/^https?:$/.test(location.protocol))return false;
var a=e.getAttribute('data-omni-dark');if(a==='on')return true;if(a==='off')return false;
var c=window.__omniDarkCfg;if(!c)return false;var h=(location.hostname||'').toLowerCase().replace(/^www\./,'');
if(c.off.indexOf(h)>=0)return false;if(c.on.indexOf(h)>=0)return true;return !!c.g;}
function lum(s){var m=/rgba?\(([^)]*)\)/.exec(s||'');if(!m)return -1;var p=m[1].split(/[\s,\/]+/).map(parseFloat);
if(p.length>3&&!(p[3]>=0.5))return -1;return (0.2126*p[0]+0.7152*p[1]+0.0722*p[2])/255;}
function own(e){var had=e.hasAttribute('data-omnidark-bg');if(had)e.removeAttribute('data-omnidark-bg');var c=getComputedStyle(e).backgroundColor;if(had)e.setAttribute('data-omnidark-bg','');return c;}
function style(){if(D.getElementById('omni-dark-style'))return;var s=D.createElement('style');s.id='omni-dark-style';s.textContent=CSS;(D.head||D.documentElement).appendChild(s);}
function update(){try{var e=D.documentElement;if(!e)return;var on=want()&&!fs;
if(on&&!D.body)return;
if(on){var hc=own(e),hl=lum(hc),bb='',bl=-1;if(hl<0&&D.body){bb=getComputedStyle(D.body).backgroundColor;bl=lum(bb);}
var l=hl>=0?hl:bl;
if(l>=0&&l<0.4)on=false;
else if(l<0&&/dark/.test(getComputedStyle(e).colorScheme||'')&&matchMedia('(prefers-color-scheme: dark)').matches)on=false;
if(on){style();if(hl<0){e.style.setProperty('--omni-dark-bg',bl>=0?bb:'#fff');e.setAttribute('data-omnidark-bg','');}else e.removeAttribute('data-omnidark-bg');}}
if(on){if(!e.hasAttribute('data-omnidark'))e.setAttribute('data-omnidark','');}else if(e.hasAttribute('data-omnidark'))e.removeAttribute('data-omnidark');}catch(_){}}
function soon(){clearTimeout(timer);timer=setTimeout(update,30);}
window.__omniDarkApply=update;
var e=D.documentElement;
if(e){var mo=new MutationObserver(function(){if(D.body){mo.disconnect();update();}});mo.observe(e,{childList:true});
new MutationObserver(soon).observe(e,{attributes:true,attributeFilter:['data-omni-dark']});}
D.addEventListener('DOMContentLoaded',update);
addEventListener('load',function(){update();setTimeout(update,1500);});
function full(){fs=!!(D.webkitFullscreenElement||D.fullscreenElement);update();}
D.addEventListener('webkitfullscreenchange',full);D.addEventListener('fullscreenchange',full);
update();})();)JS";

static void omniDkAddScript(const std::string& source)
{
    auto text = adoptWK(WKStringCreateWithUTF8CString(source.c_str()));
    auto world = adoptWK(WKStringCreateWithUTF8CString("omni-dark"));
    auto script = adoptWK(WKUserScriptCreateWithSourceInWorldOmni(text.get(), kWKInjectAtDocumentStart, true, world.get()));
    if (script) omniBlockerAddShellScript(script.get());
}
static std::string omniDkJsonList(int value)
{
    std::string s = "[";
    bool first = true;
    for (auto& [h, v] : omniDkSites) {
        if (v != value) continue;
        std::string q;
        for (char c : h) if (c != '"' && c != '\\' && (unsigned char)c >= 0x20) q += c;
        s += (first ? "\"" : ",\"") + q + "\"";
        first = false;
    }
    return s + "]";
}
// A new config script (newest version wins in every new document).
static void omniDkPushConfig()
{
    omniDkLoad(); omniF3Load();
    if (!omniDkInstalled) { omniDkInstalled = true; omniDkAddScript(omniDkLogic); }
    char head[64];
    snprintf(head, sizeof(head), "(function(){var c={v:%d,g:%d,on:", ++omniDkVersion, omniF3Set.dark ? 1 : 0);
    omniDkAddScript(std::string(head) + omniDkJsonList(1) + ",off:" + omniDkJsonList(0)
        + "};var o=window.__omniDarkCfg;if(!o||o.v<c.v)window.__omniDarkCfg=c;if(window.__omniDarkApply)window.__omniDarkApply();})();");
}
// Open pages switch now (main world: only the <html> attribute the isolated script watches).
static void omniDkApplyOpenTabs()
{
    for (auto& t : tabs) {
        if (omniTmIsUnloaded(*t) || !omniWebURL(t->url)) continue;
        const bool on = omniDkWant(t->url);
        const std::string js = std::string("document.documentElement&&document.documentElement.setAttribute('data-omni-dark','") + (on ? "on" : "off") + "')";
        auto s = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
        WKPageEvaluateJavaScriptInMainFrame(t->page, s.get(), nullptr, [](WKTypeRef, WKErrorRef, void*) { });
    }
    // the dark appearance (prefers-color-scheme) follows within 300 ms (omniDkTick)
}
static void omniDkChanged()
{
    omniDkPushConfig();
    omniDkApplyOpenTabs();
    omniPageDirty = true;
}
static void omniDkSetSite(const std::string& host, int value)   // -1 default, 0 never, 1 always
{
    if (host.empty()) return;
    omniDkLoad();
    if (value < 0) omniDkSites.erase(host); else omniDkSites[host] = value;
    omniDkSave();
    omniDkChanged();
}
static void omniDkToggleCurrent()
{
    Tab* t = active();
    if (!t || !omniWebURL(t->url)) { notice("Open a web page first"); return; }
    const std::string host = omniDkHost(t->url);
    const bool now = !omniDkWant(t->url);
    omniF3Load();
    omniDkSetSite(host, now == omniF3Set.dark ? -1 : (now ? 1 : 0));   // back to the default when it matches
    notice(std::string(now ? "Dark page on for " : "Dark page off for ") + host);
}
static void omniDkTick(uint32_t now)
{
    if (omniTestMode()) return;
    // OMNI_FEATURES_V3_FIX1: the dark world is installed only once something is dark (it ran in every page before)
    if (!omniDkInstalled) { omniF3Load(); omniDkLoad(); bool any = omniF3Set.dark; for (auto& kv : omniDkSites) any = any || kv.second == 1; if (any) omniDkPushConfig(); }
    static uint32_t last = 0;
    if (now - last < 300) return;
    last = now;
    for (auto& t : tabs) {
        if (omniTmIsUnloaded(*t)) continue;
        std::string url = t->url;
        if (auto u = adoptWK(WKPageCopyActiveURL(t->page))) url = OmniTest::toStd(adoptWK(WKURLCopyString(u.get())).get());
        const int want = omniDkWant(url) ? 1 : 0;
        auto f = omniDkApplied.find(t.get());
        if ((f == omniDkApplied.end() ? 0 : f->second) == want && f != omniDkApplied.end()) continue;
        if (f == omniDkApplied.end() && !want) { omniDkApplied[t.get()] = 0; continue; }   // pages start light: nothing to send
        omniDkApplied[t.get()] = want;
        WKPageSetUseDarkAppearanceForTesting(t->page, want != 0);
    }
    static uint32_t prune = 0;
    if (now - prune > 10000) {
        prune = now;
        for (auto it = omniDkApplied.begin(); it != omniDkApplied.end();) it = omniTabAlive(it->first) ? std::next(it) : omniDkApplied.erase(it);
    }
}
