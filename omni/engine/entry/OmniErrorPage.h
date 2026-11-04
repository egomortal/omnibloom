// OMNI_FEATURES_V1: error panel over the page when a load fails or the page's web process stops:
// what happened, the address, and Retry / Back / (Allow site) on the controller. Replaces the
// page-error toast (the toast still shows ordinary notices). Cancelled loads (Stop, a link that
// became a download) are no longer reported as "Load failed".
#pragma once

struct OmniFxTabState {
    std::string failURL, failDomain;
    int failCode = 0;
    bool crashDismissed = false;
    uint32_t stopAt = 0;
    std::string saveURL;   // the next main-frame load of this URL becomes a download (Save link / image)
};
static std::unordered_map<const void*, OmniFxTabState> omniFxTabStates;
static OmniFxTabState& omniFxState(const Tab* t) { return omniFxTabStates[t]; }
static void omniFxForgetTab(const Tab* t) { omniFxTabStates.erase(t); }

static bool omniFxQuietFailure(Tab& tab, const std::string& domain, int code, const std::string& description)
{
    if (omniTestMode()) return false;
    OmniFxTabState& s = omniFxState(&tab);
    const bool stopped = s.stopAt && SDL_GetTicks() - s.stopAt < 4000;
    const bool policy = domain == "WebKitErrorDomain" && (code == 102 || code == 204);   // interrupted by policy change / plug-in will handle
    const bool cancelled = code == -999 || domain == "WebKitInternal" || omniLower(description).find("cancel") != std::string::npos;
    if (!(stopped || policy || cancelled)) return false;
    s.stopAt = 0;
    if (auto url = adoptWK(WKPageCopyActiveURL(tab.page))) {
        const std::string now = OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get());
        if (now.rfind(omniNewTabPrefix, 0) != 0) tab.url = now;
    }
    if (stopped && &tab == active()) notice("Stopped");
    fprintf(stderr, "browser: quiet load end: domain=%s code=%d\n", domain.c_str(), code); fflush(stderr);
    return true;
}
static void omniFxRecordFailure(Tab& tab, WKErrorRef error)
{
    OmniFxTabState& s = omniFxState(&tab);
    s.failURL.clear();
    if (auto url = adoptWK(WKErrorCopyFailingURL(error))) s.failURL = OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get());
    if (s.failURL.empty()) s.failURL = tab.url;
    s.failDomain = OmniTest::toStd(adoptWK(WKErrorCopyDomain(error)).get());
    s.failCode = WKErrorGetErrorCode(error);
    omniShellDirty = true;
}
static void omniFxStop()
{
    if (!active()) return;
    omniFxState(active()).stopAt = SDL_GetTicks();
    WKPageStopLoading(active()->page);
    active()->loading = false;
}

static bool omniFxErrorShown()
{
    Tab* t = active();
    if (!t || omniTestMode() || pageFullscreen || editing || settingsOpen) return false;
    if (!omniFxStack.empty() || omniHistoryOpenFlag || omniMenuOpenFlag) return false;
    if (t->crashed) return !omniFxState(t).crashDismissed;
    return !t->loading && !t->message.empty();
}
static bool omniFxErrorPanelShown() { return omniFxErrorShown(); }
static bool omniFxErrorBlocked()   // uBlock refused the page: X allows the site
{
    Tab* t = active();
    return t && !t->crashed && omniFxState(t).failDomain == "OmniUBlock" && access("/data/omni/ublock-error.flag", F_OK);
}
static void omniFxErrorDismiss()
{
    Tab* t = active();
    if (!t) return;
    if (t->crashed) { omniFxState(t).crashDismissed = true; return; }
    t->message.clear();
    // The previous page is still shown: show its address and title again.
    if (auto url = adoptWK(WKPageCopyActiveURL(t->page))) {
        const std::string now = OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get());
        t->url = now.rfind(omniNewTabPrefix, 0) == 0 ? std::string() : now;
    }
    t->title = OmniTest::toStd(adoptWK(WKPageCopyTitle(t->page)).get());
    if (t->title.empty()) t->title = t->url.empty() ? "New tab" : omniShownURL(t->url);
}
static void omniFxErrorRetry()
{
    Tab* t = active();
    if (!t) return;
    if (t->crashed) { omniFxState(t).crashDismissed = false; WKPageReload(t->page); notice("Reloading..."); return; }
    const std::string url = omniFxState(t).failURL;
    t->message.clear();
    if (omniWebURL(url)) navigate(url); else WKPageReload(t->page);
}
static void omniFxErrorBack()
{
    Tab* t = active();
    if (!t) return;
    if (t->crashed && WKPageCanGoBack(t->page)) { omniFxState(t).crashDismissed = false; WKPageGoBack(t->page); return; }
    omniFxErrorDismiss();
}
static void omniFxErrorAllow()
{
    Tab* t = active();
    if (!t) return;
    const std::string host = omniBlockerHostOf(omniFxState(t).failURL.empty() ? t->url : omniFxState(t).failURL);
    if (host.empty() || !omniBlockerSetSiteTrusted(host, true)) { notice("Couldn't change uBlock for this site"); return; }
    notice("uBlock is off for " + host);
    omniFxErrorRetry();
}

struct OmniFxErrorLayout { int x, y, w, h, chipY; int chipX[3], chipW[3]; int chips; };
static OmniFxErrorLayout omniFxErrorGeom()
{
    OmniFxErrorLayout L {};
    const int py0 = omniPageTop(), py1 = omniPageBottom();
    L.w = 700; L.h = 264;
    L.x = (width - L.w) / 2;
    L.y = py0 + std::max(10, (py1 - py0 - L.h) / 2);
    L.chipY = L.y + L.h - 68;
    L.chips = 3;
    int cx = L.x + 40;
    const int widths[3] = { 170, 170, 220 };
    for (int i = 0; i < 3; ++i) { L.chipX[i] = cx; L.chipW[i] = widths[i]; cx += widths[i] + 14; }
    return L;
}
static void omniFxErrorDraw()
{
    Tab* t = active();
    if (!t) return;
    const OmniTheme& T = omniTheme();
    const OmniFxTabState& s = omniFxState(t);
    const int py0 = physical(omniPageTop()), py1 = physical(omniPageBottom());
    omniRectPx({ 0, py0, canvas->w, std::max(0, py1 - py0) }, T.bg, 200);
    const OmniFxErrorLayout L = omniFxErrorGeom();
    omniShadow(L.x, L.y, L.w, L.h, omniRadius + 2, 22, 160, 6);
    fillRounded(L.x, L.y, L.w, L.h, omniRadius + 2, T.panel);
    const bool crashed = t->crashed, blocked = omniFxErrorBlocked();
    const bool cert = s.failDomain == "CurlErrorDomain" && s.failCode == 60;
    const char* title = crashed ? "This page stopped working" : blocked ? "uBlock blocked this page" : cert ? "This connection isn't secure"
        : t->message.find("redirected") != std::string::npos ? "Too many redirects" : "This page couldn't load";
    omniDisc(L.x + 50, L.y + 50, 20, crashed || cert ? omniBad : omniWarn);
    omniIcon(omniIconAlert, L.x + 50, L.y + 50, T.bg);
    omniLabel(title, L.x + 88, L.y + 42, omniBodyBold, T.ink, 0, L.w - 120);
    const std::string where = omniShownURL(s.failURL.empty() || crashed ? t->url : s.failURL);
    omniLabel(where, L.x + 88, L.y + 70, omniSmall, T.inkDim, 0, L.w - 120);
    std::string body = crashed ? "The page's process ended (often memory on a heavy page). Your other tabs are fine." : t->message;
    if (!crashed && !cert && !blocked && s.failCode) body += " (error " + std::to_string(s.failCode) + ")";
    const auto lines = omniWrap(body, omniSmall, L.w - 128, 3);
    for (size_t i = 0; i < lines.size(); ++i) omniLabel(lines[i], L.x + 88, L.y + 108 + int(i) * 26, omniSmall, T.ink);
    const bool canBack = crashed && WKPageCanGoBack(t->page);
    const char* labels[3] = { crashed ? "Reload" : "Retry", canBack ? "Back" : "Close", blocked ? "Allow this site" : nullptr };
    const int faces[3] = { 0, 1, 2 };
    for (int i = 0; i < 3; ++i) {
        if (!labels[i]) continue;
        const bool primary = i == 0;
        const bool hover = pointerX >= L.chipX[i] && pointerX < L.chipX[i] + L.chipW[i] && pointerY >= L.chipY && pointerY < L.chipY + 44;
        fillRounded(L.chipX[i], L.chipY, L.chipW[i], 44, omniRadius, primary ? T.accent : hover ? T.hover : T.key);
        faceIcon(L.chipX[i] + 26, L.chipY + 22, faces[i], playStationIcons);
        omniLabel(labels[i], L.chipX[i] + 48, L.chipY + 22, omniSmallBold, primary ? T.accentInk : T.ink, 0, L.chipW[i] - 56);
    }
}
static bool omniFxErrorButton(int b)
{
    switch (b) {
    case SDL_CONTROLLER_BUTTON_A: omniFxErrorRetry(); return true;
    case SDL_CONTROLLER_BUTTON_B: omniFxErrorBack(); return true;
    case SDL_CONTROLLER_BUTTON_X: if (omniFxErrorBlocked()) { omniFxErrorAllow(); return true; } return false;
    default: return false;   // Y address, L1/R1 tabs, Options menu, D-pad scroll keep working
    }
}
static bool omniFxErrorClick(int x, int y)
{
    const OmniFxErrorLayout L = omniFxErrorGeom();
    if (y >= L.chipY && y < L.chipY + 44) {
        if (x >= L.chipX[0] && x < L.chipX[0] + L.chipW[0]) { omniFxErrorRetry(); return true; }
        if (x >= L.chipX[1] && x < L.chipX[1] + L.chipW[1]) { omniFxErrorBack(); return true; }
        if (omniFxErrorBlocked() && x >= L.chipX[2] && x < L.chipX[2] + L.chipW[2]) { omniFxErrorAllow(); return true; }
    }
    // Clicks on the bars still work (tabs, address); clicks on the dimmed page do nothing.
    return y >= omniPageTop() && y < omniPageBottom();
}
