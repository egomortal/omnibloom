// s3 OMNI_PAGES_V1: Omni's built-in pages (outputs/omni-pages, ENGINE-CONTRACT.md), shell side.
// - Files: /app0/pages (packaged with the title); /data/omni/pages-dev replaces it only while /data/omni/pages-dev.flag
//   exists. /data/omni/pages-off.flag turns the whole feature off (the old built-in new-tab page comes back).
// - Origin: omni://pages, served by OmniBlocker.cpp's scheme handler with ENGINE-CONTRACT §1's CSP. A built-in page may
//   load its own files and other built-in pages; any other main-frame load needs an address Omni itself opened in
//   that tab (so Back/Forward work, while web content can't frame or fetch these pages).
// - Which page opens when: new tab / Home -> start/; the first new tab of a session -> welcome/?firstRun=1 (which goes
//   straight on to start/ once the user finished it); a main-frame offline / certificate / console-block failure ->
//   info/?state=... in that tab (the native error panel is not shown on top). Never in self-test modes.
// - window.omnibloomHost: a page-world document-start script, omni://pages/* top frames only; the native side answers
//   only the main frame of an omni://pages document. Implemented: getLanguage, getGlyphs (sync), getApps, openApp,
//   retryNavigation, getContext, search, addons.list/call, vault.list/status, request() with navigation.current /
//   navigation.open; every other request() method answers UNSUPPORTED (the pages show their "unavailable" state).
//   The Bloom Core token never reaches a page: the engine calls Bloom Core itself.
// - Controller: on built-in pages the D-pad, Cross, Circle, L1 and R1 go first to window.omniMediaController(action)
//   (actions up down left right cross circle l1 r1); false = Omni's own action.
#pragma once

static const char* const omniPagesBase = "omni://pages/";
static int omniPagesState = -1;                 // -1 not decided yet, 0 off, 1 on
static std::string omniPagesRoot;
static bool omniPagesFirstNewTab = true;
static std::unordered_map<const Tab*, std::vector<std::string>> omniPagesAllowed;   // addresses Omni opened per tab
struct OmniPagesAction { int kind = 0; WKPageRef page = nullptr; std::string text; };   // done on the next tick
static std::vector<OmniPagesAction> omniPagesQueue;
enum { omniPagesActOpenApp = 1, omniPagesActLoad = 2 };

static bool omniPagesIsPagesURL(const std::string& url) { return url.rfind(omniPagesBase, 0) == 0; }
static bool omniPagesIsNewTab(const std::string& url)
{
    return url.rfind("omni://pages/start/", 0) == 0 || url.rfind("omni://pages/welcome/", 0) == 0;
}
static std::string omniPagesNoFragment(const std::string& url) { return url.substr(0, url.find('#')); }

static bool omniPagesEnabled()
{
    if (omniTestMode()) return false;
    if (omniPagesState < 0) {
        omniPagesRoot = !access("/data/omni/pages-dev.flag", F_OK) && !access("/data/omni/pages-dev/start/index.html", R_OK)
            ? std::string("/data/omni/pages-dev") : std::string("/app0/pages");
        omniPagesState = access("/data/omni/pages-off.flag", F_OK) && !access((omniPagesRoot + "/start/index.html").c_str(), R_OK) ? 1 : 0;
        fprintf(stderr, "pages: OMNI_PAGES_V1 %s (root %s)\n", omniPagesState ? "on" : "off", omniPagesRoot.c_str());
    }
    return omniPagesState == 1;
}
static bool omniPagesOpen(Tab* tab, const std::string& path)
{
    if (!tab || !omniPagesEnabled() || !tab->omniPagesCapable) return false;   // tabs made before omniPagesInit() keep the old pages
    const std::string url = std::string(omniPagesBase) + path;
    auto& allowed = omniPagesAllowed[tab];
    const std::string key = omniPagesNoFragment(url);
    if (std::find(allowed.begin(), allowed.end(), key) == allowed.end()) {
        allowed.push_back(key);
        if (allowed.size() > 64) allowed.erase(allowed.begin());
    }
    auto u = adoptWK(WKURLCreateWithUTF8CString(url.c_str()));
    WKPageLoadURL(tab->page, u.get());
    return true;
}
// New tab / Home. false: the feature is off (the caller shows the old new-tab page).
static bool omniPagesNewTab(Tab* tab)
{
    if (!tab || !omniPagesEnabled() || !tab->omniPagesCapable) return false;
    const bool first = std::exchange(omniPagesFirstNewTab, false);
    tab->url.clear(); tab->title = "New tab"; tab->omniNewTabPage = true; tab->loading = true;
    return omniPagesOpen(tab, first ? "welcome/index.html?firstRun=1" : "start/index.html");
}

// --- loads: the scheme handler asks for every omni://pages request ----------------------------------------------------
static bool omniPagesAllow(WKPageRef page, const std::string& url, bool mainFrame, const std::string& frameOrigin)
{
    if (!omniPagesEnabled()) return false;
    if (frameOrigin == "omni://pages") return true;          // a built-in page: its own files, and other built-in pages
    if (!mainFrame) return false;                             // web content never frames or fetches these pages
    Tab* tab = omniTabForPage(page);
    if (!tab) return false;
    const auto& allowed = omniPagesAllowed[tab];
    return std::find(allowed.begin(), allowed.end(), omniPagesNoFragment(url)) != allowed.end();
}

// --- errors -> info page --------------------------------------------------------------------------------------------
// Main-frame failures only (the navigation client reports main-frame navigations). The original address stays in the
// tab's error state (omniFxState(tab).failURL), never in the info page's address; retryNavigation() reuses it.
static bool omniPagesFailed(Tab& tab, const std::string& domain, int code)
{
    if (!omniPagesEnabled() || tab.omniPrivate || !tab.omniPagesCapable) return false;
    const std::string failed = omniFxState(&tab).failURL;
    if (!omniWebURL(failed)) return false;
    const char* state = nullptr;
    if (domain == "CurlErrorDomain") {
        switch (code) {
        case 6: case 7: case 28: case 52: case 55: case 56: state = "offline"; break;   // resolve, connect, timeout, empty reply, send, recv
        case 35: case 51: case 58: case 59: case 60: case 77: case 83: case 90: case 91: state = "certificate"; break;
        default: break;
        }
    }
    const std::string lower = omniLower(domain);
    if (!state && (lower.find("omnisec") != std::string::npos || lower.find("localhost") != std::string::npos || lower.find("pna") != std::string::npos))
        state = "blocked";
    if (!state) return false;
    fprintf(stderr, "pages: main-frame failure (%s %d) -> info/?state=%s\n", domain.c_str(), code, state);
    tab.message.clear();                                       // the info page replaces the native error panel
    tab.title = state == std::string("offline") ? "No connection" : state == std::string("certificate") ? "Connection not private" : "Blocked";
    return omniPagesOpen(&tab, std::string("info/index.html?state=") + state);
}

// --- controller ------------------------------------------------------------------------------------------------------
static bool omniPagesSkip = false;
static void omniPagesPadFallback(WKTypeRef result, WKErrorRef error, void* context)
{
    const bool handled = !error && result && WKGetTypeID(result) == WKStringGetTypeID() && OmniTest::toStd(static_cast<WKStringRef>(result)) == "1";
    if (handled || !running) return;
    omniPagesSkip = true;
    button(static_cast<int>(reinterpret_cast<intptr_t>(context)));
    omniPagesSkip = false;
}
static bool omniPagesButton(int b)
{
    if (omniPagesSkip || !active() || !active()->omniPagesTab || pageFullscreen || settingsOpen || editing || omniOverlayOpen() || active()->crashed) return false;
    const char* script = nullptr;   // one fixed script per button: no URL or text from a page
    switch (b) {
    case SDL_CONTROLLER_BUTTON_DPAD_UP: script = "window.omniMediaController?.('up')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: script = "window.omniMediaController?.('down')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: script = "window.omniMediaController?.('left')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: script = "window.omniMediaController?.('right')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_A: script = "window.omniMediaController?.('cross')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_B: script = "window.omniMediaController?.('circle')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: script = "window.omniMediaController?.('l1')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: script = "window.omniMediaController?.('r1')===true?'1':'0'"; break;
    default: return false;
    }
    auto source = adoptWK(WKStringCreateWithUTF8CString(script));
    WKPageEvaluateJavaScriptInMainFrame(active()->page, source.get(), reinterpret_cast<void*>(static_cast<intptr_t>(b)), omniPagesPadFallback);
    return true;
}

// --- the bridge ------------------------------------------------------------------------------------------------------
static std::string omniPagesJsonQuote(const std::string& s)
{
    std::string o = "\"";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { o += '\\'; o += char(c); }
        else if (c < 0x20 || c == 0x7f) { char b[8]; snprintf(b, sizeof b, "\\u%04x", c); o += b; }
        else o += char(c);
    }
    return o + "\"";
}
// The value of a string field in a flat JSON object written by JSON.stringify ({"k":"v",...}); "" when missing.
static std::string omniPagesField(const std::string& json, const char* key)
{
    const std::string k = std::string("\"") + key + "\":\"";
    size_t i = json.find(k);
    if (i == std::string::npos) return std::string();
    std::string v;
    for (i += k.size(); i < json.size() && json[i] != '"'; ++i) {
        if (json[i] != '\\' || i + 1 >= json.size()) { v += json[i]; continue; }
        const char e = json[++i];
        if (e == 'n') v += '\n'; else if (e == 't') v += '\t'; else if (e == 'r') v += '\r';
        else if (e == 'u' && i + 4 < json.size()) {
            const unsigned cp = unsigned(strtoul(json.substr(i + 1, 4).c_str(), nullptr, 16)); i += 4;
            if (cp < 0x80) v += char(cp);
            else if (cp < 0x800) { v += char(0xc0 | (cp >> 6)); v += char(0x80 | (cp & 0x3f)); }
            else { v += char(0xe0 | (cp >> 12)); v += char(0x80 | ((cp >> 6) & 0x3f)); v += char(0x80 | (cp & 0x3f)); }
        } else v += e;
        if (v.size() > 4096) break;
    }
    return v;
}
static std::string omniPagesOk(const std::string& resultJson) { return "{\"ok\":true,\"result\":" + resultJson + "}"; }
static std::string omniPagesErr(const char* code) { return std::string("{\"ok\":false,\"code\":\"") + code + "\"}"; }

static std::string omniPagesMessage(WKPageRef page, const std::string& body)
{
    // body: "<method>\n<JSON.stringify(params)>"
    const size_t nl = body.find('\n');
    const std::string m = body.substr(0, nl), a = nl == std::string::npos ? std::string("{}") : body.substr(nl + 1);
    Tab* tab = omniTabForPage(page);
    if (!tab) return omniPagesErr("STALE_STATE");
    if (m == "getApps") {
        std::vector<OmniHub::LiveApp> apps;
        if (!OmniHub::liveApps(apps)) return omniPagesErr("UNAVAILABLE");
        std::string o = "{\"apps\":[";
        for (size_t i = 0; i < apps.size(); ++i) {
            const auto& x = apps[i];
            o += (i ? "," : "") + std::string("{\"id\":") + omniPagesJsonQuote(x.id) + ",\"name\":" + omniPagesJsonQuote(x.name.empty() ? x.id : x.name)
                + ",\"version\":" + omniPagesJsonQuote(x.version) + ",\"kind\":" + omniPagesJsonQuote(x.kind)
                + ",\"verified\":" + (x.verified ? "true" : "false") + ",\"up\":" + (x.up ? "true" : "false")
                + ",\"hasPage\":" + (x.port && !x.mainPage.empty() ? "true" : "false") + "}";
        }
        return omniPagesOk(o + "]}");
    }
    if (m == "openApp") {
        const std::string id = omniPagesField(a, "id");
        if (id.empty() || id.size() > 64) return omniPagesErr("INVALID_VALUE");
        omniPagesQueue.push_back({ omniPagesActOpenApp, page, id });
        return omniPagesOk("null");
    }
    if (m == "retryNavigation") {
        const std::string url = omniFxState(tab).failURL;
        if (!omniWebURL(url)) return omniPagesErr("NOT_FOUND");
        omniPagesQueue.push_back({ omniPagesActLoad, page, url });
        return omniPagesOk("null");
    }
    if (m == "search") {
        const std::string q = omniPagesField(a, "q");
        if (q.empty() || q.size() > 2048) return omniPagesErr("INVALID_VALUE");
        omniPagesQueue.push_back({ omniPagesActLoad, page, omniFxSearchPrefix() + omniPercentEncode(q) });
        return omniPagesOk("null");
    }
    if (m == "addons.list") return omniPagesOk(omniAdListJson(std::string()));
    if (m == "addons.call") {
        const std::string r = omniAdHostCall(omniPagesField(a, "op"), omniPagesField(a, "id"), omniPagesField(a, "a"), omniPagesField(a, "b"));
        return omniPagesOk(omniPagesJsonQuote(r));
    }
    if (m == "vault.status" || m == "vault.list") {
        omniPwLoad();
        const bool locked = omniPwLocked(), broken = omniPwBroken();
        std::string o = std::string("{\"locked\":") + (locked ? "true" : "false") + ",\"broken\":" + (broken ? "true" : "false")
            + ",\"pin\":" + (omniPw.vault && omniPw.vault->pinMode() ? "true" : "false");
        if (m == "vault.list") {
            o += ",\"items\":[";
            if (!locked) for (size_t i = 0; i < omniPw.list.size() && i < 2000; ++i) {
                const auto& e = omniPw.list[i];   // never the password
                o += (i ? "," : "") + std::string("{\"id\":") + omniPagesJsonQuote(e.id) + ",\"origin\":" + omniPagesJsonQuote(e.origin)
                    + ",\"username\":" + omniPagesJsonQuote(e.user) + ",\"updatedAt\":" + std::to_string(e.used ? e.used : e.created) + "}";
            }
            o += "]";
        } else o += ",\"count\":" + std::to_string(locked ? 0 : omniPw.list.size());
        return omniPagesOk(o + "}");
    }
    if (m == "request") {
        const std::string method = omniPagesField(a, "method");
        if (method == "navigation.current")
            return omniPagesOk(std::string("{\"navigationEpoch\":0,\"title\":") + omniPagesJsonQuote(tab->title) + ",\"url\":"
                + omniPagesJsonQuote(tab->omniPagesTab ? std::string() : tab->url) + ",\"private\":" + (tab->omniPrivate ? "true" : "false") + "}");
        if (method == "navigation.open") {
            const std::string url = omniPagesField(a, "url");
            if (!omniWebURL(url) || url.size() > 4096 || url.find('@') != std::string::npos) return omniPagesErr("INVALID_VALUE");
            omniPagesQueue.push_back({ omniPagesActLoad, page, url });
            return omniPagesOk("null");
        }
        return omniPagesErr("UNSUPPORTED");
    }
    return omniPagesErr("UNSUPPORTED");
}
static void omniPagesTick()
{
    if (omniPagesQueue.empty()) return;
    auto queue = std::move(omniPagesQueue); omniPagesQueue.clear();
    for (auto& act : queue) {
        Tab* tab = omniTabForPage(act.page);
        if (!tab) continue;
        if (act.kind == omniPagesActLoad) {
            if (!omniWebURL(act.text)) continue;
            auto u = adoptWK(WKURLCreateWithUTF8CString(act.text.c_str()));
            WKPageLoadURL(tab->page, u.get());
        } else if (act.kind == omniPagesActOpenApp) {
            std::vector<OmniHub::LiveApp> apps;
            if (!OmniHub::liveApps(apps)) { notice("Bloom Core is not running"); continue; }
            const OmniHub::LiveApp* found = nullptr;
            for (const auto& x : apps) if (x.id == act.text) found = &x;
            if (!found || !found->verified || !found->port || found->mainPage.empty()) { notice("That app can't be opened"); continue; }
            if (!found->up) notice(found->name.empty() ? std::string("That app isn't running") : found->name + " isn't running");
            const std::string url = "http://127.0.0.1:" + std::to_string(found->port) + found->mainPage;
            if (newTab()) navigate(url);
        }
    }
}
static void omniPagesRefreshBridge()
{
    if (omniPagesState != 1) return;
    std::string js = R"JS((function(){'use strict';
if(location.protocol!=='omni:'||location.host!=='pages'||window.top!==window)return;
var h=window.webkit&&window.webkit.messageHandlers&&window.webkit.messageHandlers.omnibloomHost;if(!h)return;
var LANG=%LANG%,GLYPHS=%GLYPHS%;
function raw(m,a){return h.postMessage(m+'\n'+JSON.stringify(a||{})).then(function(r){return JSON.parse(String(r));});}
function call(m,a){return raw(m,a).then(function(o){if(!o||o.ok!==true){var e=new Error((o&&o.code)||'UNSUPPORTED');e.code=(o&&o.code)||'UNSUPPORTED';throw e;}return o.result;});}
var STATES={offline:1,blocked:1,certificate:1,'protected':1,app:1};
var host={
 version:1,
 getLanguage:function(){return LANG;},
 getGlyphs:function(){return GLYPHS;},
 getApps:function(){return call('getApps');},
 openApp:function(id){return call('openApp',{id:String(id)});},
 retryNavigation:function(){return call('retryNavigation');},
 getContext:function(){var s=new URLSearchParams(location.search).get('state');return {state:STATES[s]?s:'offline'};},
 search:function(q){return call('search',{q:String(q)});},
 request:function(req){var r=req||{};return raw('request',{method:String(r.method||''),url:r.params&&r.params.url?String(r.params.url):''}).then(function(o){return o&&o.ok===true?{ok:true,result:o.result}:{ok:false,code:(o&&o.code)||'UNSUPPORTED'};},function(){return {ok:false,code:'UNSUPPORTED'};});},
 addons:Object.freeze({list:function(){return call('addons.list');},call:function(op,id,a,b){return call('addons.call',{op:String(op),id:String(id),a:a==null?'':String(a),b:b==null?'':String(b)});}}),
 vault:Object.freeze({status:function(){return call('vault.status');},list:function(){return call('vault.list').then(function(r){return r.items||[];});}})
};
Object.defineProperty(window,'omnibloomHost',{value:Object.freeze(host),writable:false,configurable:false});
try{localStorage.setItem('ob.glyphs',GLYPHS);}catch(e){}
})();)JS";
    auto put = [&](const char* key, const std::string& value) { const size_t at = js.find(key); if (at != std::string::npos) js.replace(at, strlen(key), value); };
    put("%LANG%", "\"en\"");
    put("%GLYPHS%", playStationIcons ? "\"playstation\"" : "\"xbox\"");
    if (!omniPagesSetBridge(js)) fprintf(stderr, "pages: bridge not installed (no content controller)\n");
}
// After the content controllers exist (omniAdInit's place in main()).
static void omniPagesInit()
{
    if (!omniPagesEnabled()) return;
    omniPagesSetup(omniPagesRoot, omniPagesAllow, omniPagesMessage);
    omniPagesRefreshBridge();
    fprintf(stderr, "pages: OMNI_PAGES_V1 ready: scheme omni://pages, bridge on, root %s\n", omniPagesRoot.c_str());
}
