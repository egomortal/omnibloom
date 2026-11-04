// OMNI_FEATURES_V3: page tools.
//  - Screenshot: the visible page (page area only, no browser bars) saved as PNG into the downloads
//    folder. The page buffer is copied on the main thread (one memcpy: ~8 MB at 4K, where the page
//    is kept at half resolution, 1920 px wide) and encoded on a short-lived thread, so the PNG
//    encode never blocks drawing; a notice gives the path when it is written. Video drawn by the
//    hardware path (under the page) is not in the page buffer: those areas come out white.
//  - Page source: WebKit on this build has no view-source mode, so the main frame's source text
//    (WKPageGetSourceForFrame: the document as the server sent it) is escaped into a generated page
//    (line numbers, light syntax colouring) and opened in a new tab. If WebKit returns nothing (for
//    example a page made by script) the live DOM (documentElement.outerHTML) is shown instead.
#pragma once

// --- screenshot ------------------------------------------------------------------------------------
static std::atomic<int> omniPtShotState { 0 };   // 0 idle, 1 writing, 2 written, 3 failed
static std::string omniPtShotPath;
static void omniPtScreenshot()
{
    Tab* t = active();
    if (!t) return;
    if (omniPtShotState.load() == 1) { notice("Still saving the last screenshot..."); return; }
    int w = renderWidth, h = renderPageHeight;
    const uint8_t* src = pixels.data();
    if (omniPageScale < 1) {
        const int sw = (renderWidth + 1) / 2, sh = (renderPageHeight + 1) / 2;
        if (omniPageSmall.size() == size_t(sw) * sh) { w = sw; h = sh; src = reinterpret_cast<const uint8_t*>(omniPageSmall.data()); }
    }
    if (!src || w <= 0 || h <= 0 || pixels.size() < size_t(renderWidth) * renderPageHeight * 4) { notice("Nothing to capture yet"); return; }
    const long long freeMiB = omniTmQueryMiB();
    if (freeMiB >= 0 && freeMiB < 64 + (long long)(size_t(w) * h * 4 >> 20)) { notice("Not enough memory for a screenshot right now"); return; }
    const std::string dir = omniData("downloads");
    mkdir(dir.c_str(), 0777);
    char stamp[32];
    const time_t now = time(nullptr);
    struct tm tmv {};
    localtime_r(&now, &tmv);
    strftime(stamp, sizeof(stamp), "%Y%m%d-%H%M%S", &tmv);
    std::string path = dir + "/screenshot-" + stamp + ".png";
    for (int n = 2; !access(path.c_str(), F_OK) && n < 100; ++n) path = dir + "/screenshot-" + stamp + "-" + std::to_string(n) + ".png";
    std::vector<uint8_t> copy(src, src + size_t(w) * h * 4);
    omniPtShotPath = path;
    omniPtShotState = 1;
    std::thread([copy = std::move(copy), w, h, path]() {
        const bool ok = omniWritePng(path.c_str(), copy.data(), w, h, w * 4);
        omniPtShotState = ok ? 2 : 3;
    }).detach();
    fprintf(stderr, "OMNI SCREENSHOT: %dx%d -> %s\n", w, h, path.c_str());
    notice("Saving screenshot...");
}
static void omniPtTick()
{
    const int s = omniPtShotState.load();
    if (s == 2) { omniPtShotState = 0; notice("Screenshot saved: " + omniPtShotPath); omniShellDirty = true; }
    else if (s == 3) { omniPtShotState = 0; notice("Couldn't save the screenshot (" + omniPtShotPath + ")"); omniShellDirty = true; }
}

// --- page source -----------------------------------------------------------------------------------
static bool omniPtAlpha(char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'); }
static char omniPtLowerC(char c) { return c >= 'A' && c <= 'Z' ? char(c + 32) : c; }
static bool omniPtStartsNoCase(const std::string& s, size_t at, const std::string& what)
{
    if (s.size() - at < what.size()) return false;
    for (size_t k = 0; k < what.size(); ++k) if (omniPtLowerC(s[at + k]) != what[k]) return false;
    return true;
}
static void omniPtEscape(std::string& out, char c)
{
    switch (c) {
    case '&': out += "&amp;"; break;
    case '<': out += "&lt;"; break;
    case '>': out += "&gt;"; break;
    case '"': out += "&quot;"; break;
    default: out += c; break;
    }
}
// Escaped source with one <span class=l> per line (CSS counters number them) and colour classes:
// t tag name, a attribute name, v attribute value, c comment / doctype. Classes are closed and
// reopened at each line break so every line span is well formed.
static std::string omniPtSourceBody(const std::string& src, bool colour, bool numbers)
{
    std::string out;
    out.reserve(src.size() * 5 / 4 + 4096);
    const char* open = nullptr;   // colour class currently open
    auto setClass = [&](const char* c) {
        if (open == c) return;
        if (open) out += "</span>";
        open = c;
        if (open) { out += "<span class="; out += open; out += ">"; }
    };
    if (numbers) out += "<span class=l>";
    enum { Text, Tag, TagName, AttrName, AttrValue, Comment, Raw } st = Text;
    char quote = 0;
    std::string rawEnd;   // "</script" or "</style" while inside one
    const size_t n = src.size();
    for (size_t i = 0; i < n; ++i) {
        const char c = src[i];
        if (c == '\n') {
            const char* keep = open;
            if (open) out += "</span>";
            out += numbers ? "</span>\n<span class=l>" : "\n";
            if (keep) { out += "<span class="; out += keep; out += ">"; }
            continue;
        }
        if (c == '\r') continue;
        if (!colour) { omniPtEscape(out, c); continue; }
        switch (st) {
        case Raw:
            if (c == '<' && omniPtStartsNoCase(src, i, rawEnd)) { st = Text; --i; continue; }
            omniPtEscape(out, c);
            break;
        case Comment:
            omniPtEscape(out, c);
            if (c == '>' && (i < 2 || src.compare(i - 2, 2, "--") == 0 || quote == '!')) { setClass(nullptr); st = Text; }
            break;
        case Text:
            if (c == '<' && i + 1 < n && (omniPtAlpha(src[i + 1]) || src[i + 1] == '/' || src[i + 1] == '!')) {
                if (src.compare(i, 4, "<!--") == 0) { setClass("c"); quote = '-'; st = Comment; omniPtEscape(out, c); break; }
                if (src[i + 1] == '!') { setClass("c"); quote = '!'; st = Comment; omniPtEscape(out, c); break; }
                setClass("t"); omniPtEscape(out, c); st = TagName;
                size_t e = i + 1;
                if (e < n && src[e] == '/') ++e;
                std::string name;
                while (e < n && (omniPtAlpha(src[e]) || (src[e] >= '0' && src[e] <= '9') || src[e] == '-')) name += omniPtLowerC(src[e++]);
                rawEnd = src[i + 1] != '/' && (name == "script" || name == "style") ? "</" + name : std::string();
                break;
            }
            omniPtEscape(out, c);
            break;
        case TagName:
        case Tag:
        case AttrName:
            if (c == '>') { setClass("t"); omniPtEscape(out, c); setClass(nullptr); st = rawEnd.empty() ? Text : Raw; break; }
            if (c == '/' && i + 1 < n && src[i + 1] == '>') { setClass("t"); out += c; break; }
            if (c == ' ' || c == '\t') { setClass(nullptr); out += c; st = Tag; break; }
            if (c == '=') { setClass(nullptr); out += c; if (i + 1 < n && (src[i + 1] == '"' || src[i + 1] == '\'')) { quote = src[++i]; setClass("v"); omniPtEscape(out, quote); st = AttrValue; } break; }
            if (st == Tag) st = AttrName;
            setClass(st == TagName ? "t" : "a");
            omniPtEscape(out, c);
            break;
        case AttrValue:
            omniPtEscape(out, c);
            if (c == quote) { setClass(nullptr); st = Tag; }
            break;
        }
    }
    setClass(nullptr);
    if (numbers) out += "</span>";
    return out;
}
static void omniPtOpenSource(const std::string& url, const std::string& title, const std::string& src, bool live)
{
    if (src.empty()) { notice("This page has no source to show"); return; }
    size_t lines = 1;
    for (char c : src) lines += c == '\n';
    const bool colour = src.size() <= 1500000, numbers = lines <= 40000;
    const OmniTheme& T = omniTheme();
    auto hex = [](SDL_Color c) { char b[8]; snprintf(b, sizeof(b), "#%02x%02x%02x", c.r, c.g, c.b); return std::string(b); };
    std::string esc;
    for (char c : (title.empty() ? omniShownURL(url) : title)) omniPtEscape(esc, c);
    std::string escUrl;
    for (char c : url) omniPtEscape(escUrl, c);
    char info[160];
    snprintf(info, sizeof(info), "%zu lines \xc2\xb7 %.1f KB%s%s", lines, src.size() / 1024.0, live ? " \xc2\xb7 live page (the server's original was not available)" : "",
        colour ? "" : " \xc2\xb7 too large to colour");
    std::string html = "<!doctype html><html><head><meta charset=utf-8><title>Source: " + esc + "</title><style>"
        "html,body{margin:0;background:" + hex(T.bg) + ";color:" + hex(T.ink) + "}"
        "header{position:sticky;top:0;background:" + hex(T.bar) + ";padding:10px 16px;font:15px sans-serif;border-bottom:1px solid " + hex(T.line) + "}"
        "header b{color:" + hex(T.accent) + "}header span{color:" + hex(T.inkDim) + ";margin-left:12px}"
        "pre{margin:0;padding:10px 16px 40px 0;font:14px/1.5 'DejaVu Sans Mono',monospace;white-space:pre-wrap;word-break:break-all;counter-reset:l}"
        ".l{display:block;padding-left:72px;position:relative;min-height:1.5em}"
        ".l::before{counter-increment:l;content:counter(l);position:absolute;left:0;width:58px;text-align:right;color:" + hex(T.inkFaint) + "}"
        + std::string(numbers ? "" : "pre{padding-left:16px}") +
        ".t{color:#e9737b}.a{color:#e0a86c}.v{color:#9fcf7d}.c{color:#8a909b;font-style:italic}"
        "</style></head><body><header><b>Source</b> " + escUrl + "<span>" + info + "</span></header><pre>"
        + omniPtSourceBody(src, colour, numbers) + "</pre></body></html>";
    if (!newTab()) { notice(omniF3TabRefusal()); return; }
    Tab* t = active();
    t->title = "Source: " + (title.empty() ? omniShownURL(url) : title);
    auto s = adoptWK(WKStringCreateWithUTF8CString(html.c_str()));
    WKPageLoadHTMLString(t->page, s.get(), nullptr);
    t->loading = true;
    fprintf(stderr, "OMNI SOURCE: %s %zu bytes, %zu lines%s\n", url.c_str(), src.size(), lines, live ? " (live DOM)" : "");
}
struct OmniPtSourceQuery { const void* tab; std::string url, title; };
static void omniPtViewSource()
{
    Tab* t = active();
    if (!t || !omniWebURL(t->url) || t->crashed || omniTmIsUnloaded(*t)) { notice("Open a web page first"); return; }
    if (omniF3TabsFull()) { notice("Close a tab first: the source opens in a new tab"); return; }
    WKFrameRef frame = WKPageGetMainFrame(t->page);   // OMNI_FEATURES_V3_FIX1: null before the main frame exists
    if (!frame) { notice("The page isn't ready yet"); return; }
    notice("Getting the page source...");
    auto* q = new OmniPtSourceQuery { t, t->url, t->title };
    WKPageGetSourceForFrame(t->page, frame, q, [](WKStringRef source, WKErrorRef error, void* ctx) {
        std::unique_ptr<OmniPtSourceQuery> q(static_cast<OmniPtSourceQuery*>(ctx));
        std::string text = !error && source ? OmniTest::toStd(source) : std::string();
        if (!text.empty() || !omniTabAlive(q->tab)) { omniPtOpenSource(q->url, q->title, text, false); return; }
        auto* again = new OmniPtSourceQuery(*q);
        const Tab* tab = static_cast<const Tab*>(q->tab);
        auto js = adoptWK(WKStringCreateWithUTF8CString("document.documentElement?document.documentElement.outerHTML:''"));
        WKPageEvaluateJavaScriptInMainFrame(tab->page, js.get(), again, [](WKTypeRef result, WKErrorRef error, void* ctx2) {
            std::unique_ptr<OmniPtSourceQuery> q2(static_cast<OmniPtSourceQuery*>(ctx2));
            omniPtOpenSource(q2->url, q2->title, omniFxResultString(result, error), true);
        });
    });
}
