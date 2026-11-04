// OMNI_FEATURES_V1: hold Cross (A) for half a second over a page: a context menu for the link, image
// or page under the pointer. The shell asks the page with one small read-only script
// (document.elementsFromPoint at the pointer, same-origin frames followed); WebKit's own hit test
// result is only available in the web process. Save uses the existing download path: the next load
// of that URL in this tab is turned into a download by the navigation policy (omniFxPolicyDownload).
#pragma once

// Minimal JSON reader for the flat objects the scripts return: "key":"string" or "key":number.
static bool omniFxJsonString(const std::string& j, const char* key, std::string& out)
{
    const std::string k = std::string("\"") + key + "\":";
    size_t i = j.find(k);
    if (i == std::string::npos) return false;
    i += k.size();
    if (i >= j.size() || j[i] != '"') return false;
    out.clear();
    for (++i; i < j.size() && j[i] != '"'; ++i) {
        char c = j[i];
        if (c != '\\' || i + 1 >= j.size()) { out += c; continue; }
        c = j[++i];
        if (c == 'n') out += '\n'; else if (c == 't') out += '\t'; else if (c == 'r') out += '\r'; else if (c == 'b' || c == 'f') out += ' ';
        else if (c == 'u' && i + 4 < j.size()) {
            unsigned cp = unsigned(strtoul(j.substr(i + 1, 4).c_str(), nullptr, 16)); i += 4;
            if (cp >= 0xD800 && cp < 0xDC00 && i + 6 < j.size() && j[i + 1] == '\\' && j[i + 2] == 'u') {
                const unsigned lo = unsigned(strtoul(j.substr(i + 3, 4).c_str(), nullptr, 16));
                if (lo >= 0xDC00 && lo < 0xE000) { cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00); i += 6; }
            }
            if (cp < 0x80) out += char(cp);
            else if (cp < 0x800) { out += char(0xC0 | (cp >> 6)); out += char(0x80 | (cp & 63)); }
            else if (cp < 0x10000) { out += char(0xE0 | (cp >> 12)); out += char(0x80 | ((cp >> 6) & 63)); out += char(0x80 | (cp & 63)); }
            else { out += char(0xF0 | (cp >> 18)); out += char(0x80 | ((cp >> 12) & 63)); out += char(0x80 | ((cp >> 6) & 63)); out += char(0x80 | (cp & 63)); }
        } else out += c;
    }
    return true;
}
static bool omniFxJsonNumber(const std::string& j, const char* key, double& out)
{
    const std::string k = std::string("\"") + key + "\":";
    const size_t i = j.find(k);
    if (i == std::string::npos) return false;
    char* end = nullptr;
    out = strtod(j.c_str() + i + k.size(), &end);
    return end != j.c_str() + i + k.size();
}
static std::string omniFxResultString(WKTypeRef result, WKErrorRef error)
{
    return !error && result && WKGetTypeID(result) == WKStringGetTypeID() ? OmniTest::toStd(static_cast<WKStringRef>(result)) : std::string();
}
// Page CSS pixels per layout (1280x720) pixel for the active tab's current zoom.
static double omniFxCssPerLayout(Tab* t)
{
    const double z = t ? WKPageGetPageZoomFactor(t->page) : 0;
    return z > 0 ? displayScale * omniPageScale / z : 1.0;
}

// --- save link / image: the next main-frame load of the URL becomes a download --------------------
static bool omniFxPolicyDownload(WKPageRef page, WKNavigationActionRef action, WKFramePolicyListenerRef listener)
{
    Tab* tab = omniTabForPage(page);
    if (!tab) return false;
    auto found = omniFxTabStates.find(tab);
    if (found == omniFxTabStates.end() || found->second.saveURL.empty()) return false;
    auto target = adoptWK(WKNavigationActionCopyTargetFrameInfo(action));
    if (target && !WKFrameInfoGetIsMainFrame(target.get())) return false;
    auto request = adoptWK(WKNavigationActionCopyRequest(action));
    auto url = request ? adoptWK(WKURLRequestCopyURL(request.get())) : WKRetainPtr<WKURLRef>();
    const std::string u = url ? OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get()) : std::string();
    if (u != found->second.saveURL) return false;
    found->second.saveURL.clear();
    WKFramePolicyListenerDownload(listener);
    return true;
}
static void omniFxSaveURL(const std::string& url)
{
    Tab* t = active();
    if (!t || url.empty()) return;
    if (url.rfind("blob:", 0) == 0) { notice("This file only exists inside the page and can't be saved"); return; }
    if (!omniWebURL(url) && url.rfind("data:", 0) != 0) { notice("This link can't be saved"); return; }
    omniFxState(t).saveURL = url;
    auto u = adoptWK(WKURLCreateWithUTF8CString(url.c_str()));
    WKPageLoadURL(t->page, u.get());
    notice("Saving to " + omniData("downloads/") + "...");
}
static void omniFxCopy(const std::string& text, const char* what)
{
    omniKbClipboard = text;
    notice(std::string(what) + " copied: paste it with the keyboard's Paste key");
}

// --- the menu --------------------------------------------------------------------------------------
enum { omniCxNewTab = 1, omniCxBackground, omniCxPrivate, omniCxCopyLink, omniCxSaveLink, omniCxShortcut, omniCxBookmarkLink,
    omniCxOpenImage, omniCxCopyImage, omniCxSaveImage, omniCxVideoTab,
    omniCxBack, omniCxForward, omniCxReload, omniCxBookmarkPage, omniCxCopyPage, omniCxTranslate, omniCxReader, omniCxSite };
static void omniFxSiteSettingsShow();
static void omniFxContextBuild(OmniFxPanel& p)
{
    auto add = [&](int id, const char* label, bool on = true, int icon = -1) { OmniFxRow r; r.id = id; r.label = label; r.enabled = on; r.icon = icon; p.rows.push_back(r); };
    const bool four = omniF3TabsFull(); // OMNI_FEATURES_V3
    if (!p.link.empty()) {
        add(omniCxNewTab, "Open link in new tab", !four, omniIconPlus);
        add(omniCxBackground, "Open in background tab", !four);
        add(omniCxPrivate, "Open in private tab", !four);
        add(omniCxCopyLink, "Copy link address");
        add(omniCxSaveLink, "Save link");
        add(omniCxShortcut, "Add link to shortcuts");
        add(omniCxBookmarkLink, "Bookmark link");
    }
    if (!p.image.empty()) {
        add(omniCxOpenImage, "Open image in new tab", !four);
        add(omniCxCopyImage, "Copy image address");
        add(omniCxSaveImage, "Save image");
    }
    if (p.link.empty() && p.image.empty()) {
        Tab* t = active();
        const bool web = t && omniWebURL(t->url);
        if (!p.text.empty()) add(omniCxVideoTab, "Open video in new tab", !four);
        add(omniCxBack, "Back", t && WKPageCanGoBack(t->page), omniIconBack);
        add(omniCxForward, "Forward", t && WKPageCanGoForward(t->page), omniIconForward);
        add(omniCxReload, "Reload", t != nullptr, omniIconReload);
        add(omniCxBookmarkPage, web && omniFxBookmarkIndex(t->url) >= 0 ? "Remove bookmark" : "Bookmark page", web);
        add(omniCxCopyPage, "Copy page address", web);
        add(omniCxTranslate, web && omniIsTranslated(t->url) ? "Show original" : "Translate page", web);
        add(omniCxReader, "Reader view", web);
        omniF3ContextRows(p); // OMNI_FEATURES_V3: page source, screenshot, dark page
        add(omniCxSite, "Site settings", web, omniIconShield);
    }
}
static bool omniFxContextInput(OmniFxPanel& p, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (!r.enabled) return true;
    if (omniF3ContextAction(r.id)) return true; // OMNI_FEATURES_V3
    const std::string link = p.link, image = p.image, video = p.text, label = p.page;
    if (r.id == omniCxSite) { omniFxSiteSettingsShow(); return true; }
    omniFxCloseAll();
    Tab* t = active();
    switch (r.id) {
    case omniCxNewTab: omniFxOpenInNewTab(link, false, false); break;
    case omniCxBackground: omniFxOpenInNewTab(link, true, false); break;
    case omniCxPrivate: omniFxOpenInNewTab(link, false, true); break;
    case omniCxCopyLink: omniFxCopy(link, "Link"); break;
    case omniCxSaveLink: omniFxSaveURL(link); break;
    case omniCxShortcut: omniFxShortcutAdd(link, label); break;
    case omniCxBookmarkLink: omniFxBookmarkAdd(link, label); break;
    case omniCxOpenImage: omniFxOpenInNewTab(image, false, false); break;
    case omniCxCopyImage: omniFxCopy(image, "Image address"); break;
    case omniCxSaveImage: omniFxSaveURL(image); break;
    case omniCxVideoTab: omniFxOpenInNewTab(video, false, false); break;
    case omniCxBack: omniFxBack(); break;
    case omniCxForward: omniFxForward(); break;
    case omniCxReload: if (t) WKPageReload(t->page); break;
    case omniCxBookmarkPage: omniFxBookmarkToggleCurrent(); break;
    case omniCxCopyPage: if (t) omniFxCopy(t->url, "Page address"); break;
    case omniCxTranslate: omniTranslateToggle(); break;
    case omniCxReader: omniReaderStart(); break;
    }
    return true;
}
static void omniFxContextOpen(const std::string& json, int px, int py)
{
    if (!active() || editing || settingsOpen || pageFullscreen || omniOverlayOpen()) return;
    OmniFxPanel p;
    omniFxJsonString(json, "link", p.link);
    omniFxJsonString(json, "img", p.image);
    omniFxJsonString(json, "video", p.text);
    std::string linkText, alt;
    omniFxJsonString(json, "text", linkText);
    omniFxJsonString(json, "alt", alt);
    if (!omniWebURL(p.text)) p.text.clear();
    p.page = !linkText.empty() ? linkText : alt;
    if (!p.link.empty()) { p.title = linkText.empty() ? "Link" : linkText; p.subtitle = omniShownURL(p.link); }
    else if (!p.image.empty()) { p.title = alt.empty() ? "Image" : alt; p.subtitle = p.image.rfind("data:", 0) == 0 ? std::string("Embedded image") : omniShownURL(p.image); }
    else { p.title = active()->title.empty() ? "This page" : active()->title; p.subtitle = omniShownURL(active()->url); }
    p.w = 520; p.rowH = 46; p.maxVisible = 11; p.anchorX = px; p.anchorY = py;
    p.build = omniFxContextBuild; p.input = omniFxContextInput;
    p.faces = { { 0, "Choose" }, { 1, "Close" } };
    omniFxPush(std::move(p));
}
static const char* const omniFxContextScript = R"JS((function(x,y){try{var d=document,r={};
var es=d.elementsFromPoint?d.elementsFromPoint(x,y):[d.elementFromPoint(x,y)],e=es[0];
for(var k=0;k<3&&e&&e.tagName==='IFRAME';k++){try{var fd=e.contentDocument;if(!fd)break;var b=e.getBoundingClientRect();x-=b.left;y-=b.top;es=fd.elementsFromPoint(x,y);e=es[0];}catch(_){break;}}
if(!e)return'{}';
var a=e.closest?e.closest('a[href]'):null;
if(a&&a.href&&!/^javascript:/i.test(a.href)){r.link=a.href;r.text=(a.innerText||a.getAttribute('aria-label')||a.title||'').replace(/\s+/g,' ').trim().slice(0,140);}
for(var i=0;i<es.length&&i<8;i++){var n=es[i],im=n.tagName==='IMG'?n:(n.tagName==='PICTURE'?n.querySelector('img'):null);
if(im&&(im.currentSrc||im.src)){r.img=im.currentSrc||im.src;r.alt=(im.alt||'').replace(/\s+/g,' ').trim().slice(0,140);break;}
if(n.tagName==='VIDEO'){var s=n.currentSrc||n.src;if(s&&!/^blob:/.test(s))r.video=s;break;}}
return JSON.stringify(r);}catch(err){return'{}';}})()JS";
struct OmniFxQuery { const void* tab; int px, py; };
static void omniFxContextQuery()
{
    Tab* t = active();
    if (!t || t->crashed) return;
    const double k = omniFxCssPerLayout(t);
    char head[96];
    snprintf(head, sizeof(head), "(function(){var X=%.1f,Y=%.1f;return ", pointerX * k, (pointerY - omniPageTop()) * k);
    std::string js = omniFxContextScript;
    js.replace(js.size() - 2, 2, "(X,Y);})()");   // the template ends with "()": call it with X, Y
    js = std::string(head) + js;
    auto src = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    auto* q = new OmniFxQuery { t, int(pointerX), int(pointerY) };
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), q, [](WKTypeRef result, WKErrorRef error, void* context) {
        std::unique_ptr<OmniFxQuery> q(static_cast<OmniFxQuery*>(context));
        if (!omniTabAlive(q->tab) || active() != q->tab) return;
        std::string json = omniFxResultString(result, error);
        omniFxContextOpen(json.empty() ? std::string("{}") : json, q->px, q->py);
    });
}
