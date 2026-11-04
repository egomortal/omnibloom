// OMNI_FEATURES_V1: the Options button opens this quick menu instead of quitting Omni. A 3 x 8 grid
// on the D-pad: navigation, page tools, lists, settings and Exit (with a confirmation). Zoom keeps
// the menu open so it can be pressed repeatedly; lists open on top of it (B comes back here).
#pragma once

// --- back / forward with feedback; D-pad left/right while browsing ------------------------------
static void omniFxBack()
{
    if (!active()) return;
    if (WKPageCanGoBack(active()->page)) WKPageGoBack(active()->page); else notice("No earlier page in this tab");
}
static void omniFxForward()
{
    if (!active()) return;
    if (WKPageCanGoForward(active()->page)) WKPageGoForward(active()->page); else notice("No later page in this tab");
}
static bool omniFxDpadSide(int button)
{
    if (button != SDL_CONTROLLER_BUTTON_DPAD_LEFT && button != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    omniFxLoad();
    const bool left = button == SDL_CONTROLLER_BUTTON_DPAD_LEFT;
    if (omniFxSet.dpad == 1 && tabs.size() > 1) activate(left ? (selected + tabs.size() - 1) % tabs.size() : (selected + 1) % tabs.size());
    else if (left) omniFxBack(); else omniFxForward();
    return true;
}

// --- site settings ---------------------------------------------------------------------------------
enum { omniFxSiteBlock = 1, omniFxSiteBlockAll, omniFxSiteMobile, omniFxSiteZoom, omniFxSiteReload };
static void omniFxSiteBuild(OmniFxPanel& p)
{
    const std::string host = omniMenuHost();
    const bool page = !host.empty();
    p.subtitle = page ? host : std::string("No site open");
    auto add = [&](int id, const char* label, std::string value, bool on, bool stepper) { OmniFxRow r; r.id = id; r.label = label; r.value = std::move(value); r.enabled = on; r.stepper = stepper; p.rows.push_back(r); };
    const bool enabled = omniBlockerEnabled();
    add(omniFxSiteBlock, "uBlock on this site", !enabled ? "Off everywhere" : omniBlockerSiteTrusted(host) ? "Off (allowed)" : "On", page && enabled, false);
    add(omniFxSiteBlockAll, "uBlock on all sites", omniBlockerFailed() ? "Error" : enabled ? "On" : "Off", true, false);
    add(omniFxSiteMobile, "Site version", omniMobileHosts.count(host) ? "Mobile (iPhone)" : "Desktop", page, true);
    add(omniFxSiteZoom, "Zoom for this site", omniFxPercent(omniZoomFor(host)), page, true);
    omniF3SiteRows(p, host); // OMNI_FEATURES_V3: dark page on this site
    add(omniFxSiteReload, "Reload page", "", active() != nullptr, false);
    p.rows.back().icon = omniIconReload;
    omniF2SiteExtra(p); // OMNI_FEATURES_V2: Site permissions, Fill saved login
}
static bool omniFxSiteInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (r.id >= 900) return omniF2SiteInput(r, b); // OMNI_FEATURES_V2
    if (!r.enabled) return b == SDL_CONTROLLER_BUTTON_A;
    if (r.id >= 300) return omniF3SiteInput(r, b); // OMNI_FEATURES_V3
    const bool a = b == SDL_CONTROLLER_BUTTON_A, side = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT || b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT;
    const std::string host = omniMenuHost();
    switch (r.id) {
    case omniFxSiteBlock:
        if (!a && !side) return false;
        if (omniBlockerSetSiteTrusted(host, !omniBlockerSiteTrusted(host)) && active()) WKPageReload(active()->page);
        return true;
    case omniFxSiteBlockAll:
        if (!a && !side) return false;
        if (omniBlockerSetEnabled(!omniBlockerEnabled()) && active()) WKPageReload(active()->page);
        return true;
    case omniFxSiteMobile: if (!a && !side) return false; omniMobileToggle(); return true;
    case omniFxSiteZoom:
        if (a) omniZoomStep(0); else if (side) omniZoomStep(b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT ? 1 : -1); else return false;
        return true;
    case omniFxSiteReload: if (!a) return false; omniFxCloseAll(); if (active()) WKPageReload(active()->page); return true;
    }
    return false;
}
static void omniFxSiteSettingsShow()
{
    OmniFxPanel p;
    p.title = "Site settings"; p.w = 760;
    p.build = omniFxSiteBuild; p.input = omniFxSiteInput;
    p.faces = { { 0, "Change" }, { 1, "Back" } };
    p.extra = "D-pad \xe2\x97\x80 \xe2\x96\xb6 change   zoom: Cross resets";
    omniFxPush(std::move(p));
}

// --- the quick menu --------------------------------------------------------------------------------
enum { omniQmBack = 1, omniQmForward, omniQmReload, omniQmHome, omniQmNewTab, omniQmTabs, omniQmFind, omniQmZoomOut, omniQmZoomIn,
    omniQmZoomReset, omniQmReader, omniQmTranslate, omniQmBookmark, omniQmCopy, omniQmSite, omniQmBookmarks, omniQmHistory, omniQmDownloads,
    omniQmReopen, omniQmPrivate, omniQmTools, omniQmSettings, omniQmBrowserSettings, omniQmExit };
static void omniFxQuickBuild(OmniFxPanel& p)
{
    Tab* t = active();
    const std::string host = omniMenuHost();
    const bool page = !host.empty(), web = t && omniWebURL(t->url), four = omniF3TabsFull(); // OMNI_FEATURES_V3
    auto add = [&](int id, const char* label, bool on, int icon = -1, std::string value = {}) { OmniFxRow r; r.id = id; r.label = label; r.enabled = on; r.icon = icon; r.value = std::move(value); p.rows.push_back(r); };
    add(omniQmBack, "Back", t && WKPageCanGoBack(t->page), omniIconBack);
    add(omniQmForward, "Forward", t && WKPageCanGoForward(t->page), omniIconForward);
    if (t && t->loading) add(omniQmReload, "Stop", true, omniIconClose); else add(omniQmReload, "Reload", t != nullptr, omniIconReload);
    add(omniQmHome, "Home", t != nullptr);
    add(omniQmNewTab, "New tab", !four, omniIconPlus, four ? std::to_string(tabs.size()) + " open" : std::string()); // OMNI_FEATURES_V3
    add(omniQmTabs, "Tabs", true, -1, std::to_string(tabs.size()) + " open");
    add(omniQmFind, "Find on page", page);
    add(omniQmZoomOut, "Zoom out", page, -1, "\xe2\x88\x92");
    add(omniQmZoomIn, "Zoom in", page, -1, "+");
    add(omniQmZoomReset, "Reset zoom", page, -1, omniFxPercent(omniZoomFor(host)));
    add(omniQmReader, "Reader view", page);
    add(omniQmTranslate, web && omniIsTranslated(t->url) ? "Show original" : "Translate", web);
    add(omniQmBookmark, web && omniFxBookmarkIndex(t->url) >= 0 ? "Remove bookmark" : "Bookmark page", web);
    add(omniQmCopy, "Copy address", web);
    omniF3QuickTiles(p); // OMNI_FEATURES_V3: Screenshot, Page source, Dark page
    add(omniQmSite, "Site settings", true, omniIconShield);
    omniF2QuickExtra(p); // OMNI_FEATURES_V2: Fill saved login when there is one
    omniFxBookmarksLoad();
    add(omniQmBookmarks, "Bookmarks", true, -1, std::to_string(omniFxBookmarks.size()));
    add(omniQmHistory, "History", true);
    const int running = omniFxDownloadsRunning();
    add(omniQmDownloads, "Downloads", true, -1, running ? std::to_string(running) + " running" : "");
    add(omniQmReopen, "Reopen closed tab", !omniFxClosed.empty() && !four);
    add(omniQmPrivate, "New private tab", !four);
    add(omniQmTools, "Browser tools", true);
    add(omniQmSettings, "Settings", true, omniIconGear);
    add(omniQmBrowserSettings, "Browser settings", true, omniIconGear);
    add(omniQmExit, "Exit Omni", true, omniIconClose);
    p.rows.back().danger = true;
    p.subtitle = page ? host : t && t->omniNewTabPage ? std::string("New tab") : std::string();
}
static bool omniFxQuickInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (!r.enabled) return true;
    if (r.id >= 900) return omniF2QuickInput(r, b); // OMNI_FEATURES_V2
    if (omniF3QuickAction(r.id)) return true; // OMNI_FEATURES_V3
    Tab* t = active();
    switch (r.id) {   // stay open
    case omniQmZoomOut: omniZoomStep(-1); return true;
    case omniQmZoomIn: omniZoomStep(1); return true;
    case omniQmZoomReset: omniZoomStep(0); return true;
    case omniQmSite: omniFxSiteSettingsShow(); return true;
    case omniQmTabs: omniFxTabsShow(); return true;
    case omniQmBookmarks: omniFxBookmarksShow(0); return true;
    case omniQmDownloads: omniFxDownloadsShow(); return true;
    case omniQmBrowserSettings: omniFxSettingsShow(); return true;
    default: break;
    }
    omniFxCloseAll();
    switch (r.id) {
    case omniQmBack: omniFxBack(); break;
    case omniQmForward: omniFxForward(); break;
    case omniQmReload: if (t) { if (t->loading) omniFxStop(); else WKPageReload(t->page); } break;
    case omniQmHome: omniFxHome(); break;
    case omniQmNewTab: if (newTab()) { if (!omniTestMode()) omniOpenNewTabPage(active()); address.clear(); editing = true; omniKbPageReset(); } break;
    case omniQmFind: omniFindStart(); break;
    case omniQmReader: omniReaderStart(); break;
    case omniQmTranslate: omniTranslateToggle(); break;
    case omniQmBookmark: omniFxBookmarkToggleCurrent(); break;
    case omniQmCopy: if (t) omniFxCopy(t->url, "Page address"); break;
    case omniQmHistory: omniHistoryShow(); break;
    case omniQmReopen: omniFxReopenClosed(); break;
    case omniQmPrivate: omniNewPrivateTab(); break;
    case omniQmTools: omniMenuShow(); break;
    case omniQmSettings: settingsOpen = true; omniSettingsRow = 0; fieldClickDeadline = 0; break;
    case omniQmExit:
        omniAsk("Exit Omni?", "Your tabs are saved and open again next time.", "Exit", [](bool ok) { if (ok) running = false; });
        break;
    }
    return true;
}
static void omniFxQuickMenuShow()
{
    if (omniModalVisible() || pageFullscreen) return;
    if (!omniFxStack.empty()) { omniFxCloseAll(); return; }   // Esc on a USB keyboard toggles it
    if (editing) dismissKeyboard();
    settingsOpen = false; omniHistoryOpenFlag = false; omniMenuOpenFlag = false;
    omniFxCloseAll();
    OmniFxPanel p;
    p.title = "Omni"; p.cols = 3; p.w = 960; p.rowH = 58;
    p.build = omniFxQuickBuild; p.input = omniFxQuickInput;
    p.faces = { { 0, "Choose" }, { 1, "Close" } };
    p.extra = "D-pad: move   Options: close";
    omniFxPush(std::move(p));
    omniFxStack.back().sel = 2;   // Reload / Stop
}
