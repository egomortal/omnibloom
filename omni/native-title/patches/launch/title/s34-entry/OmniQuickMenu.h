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

// --- s2 OMNI_HUB_CARDS_V1: Apps (what Bloom Core lists) -----------------------------------------------------------
static std::vector<OmniHub::LiveApp> omniHubApps;
static bool omniHubAppsOk = false;
static void omniHubAppsBuild(OmniFxPanel& p)
{
    p.subtitle = omniHubAppsOk ? std::string("Bloom Core: running") : std::string("Bloom Core: unavailable"); // OMNI_MQ_NATIVE_V1: existing status.json reader
    int i = 0;
    for (const auto& a : omniHubApps) {
        OmniFxRow r; r.id = 100 + i++;
        r.label = a.name.empty() ? a.id : a.name;
        r.value = !a.verified ? std::string("Not verified") : a.kind == "title" ? std::string(a.id == "omni" ? "This app" : "PS5 app")
            : a.up ? (a.version.empty() ? std::string("Running") : a.version) : std::string("Not running");
        r.enabled = a.verified && a.up && a.port && !a.mainPage.empty() && a.kind != "title";
        p.rows.push_back(r);
    }
    if (p.rows.empty()) {
        OmniFxRow r; r.id = 1; r.enabled = false;
        r.label = omniHubAppsOk ? "No apps installed yet" : "Install Bloom Core with Omnibloom Setup";
        p.rows.push_back(r);
    }
}
static bool omniHubAppsInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (!r.enabled || r.id < 100 || size_t(r.id - 100) >= omniHubApps.size()) return true;
    const auto& a = omniHubApps[size_t(r.id - 100)];
    const std::string url = "http://127.0.0.1:" + std::to_string(a.port) + a.mainPage;
    omniFxCloseAll();
    if (newTab()) navigate(url);
    return true;
}
static void omniHubAppsShow()
{
    omniHubAppsOk = OmniHub::liveApps(omniHubApps);
    fprintf(stderr, "hub: Apps menu: Bloom Core %s, %d app(s)\n", omniHubAppsOk ? "answered" : "not running", int(omniHubApps.size()));
    OmniFxPanel p;
    p.title = "Apps"; p.w = 1040; p.cols = 2; p.rowH = 96; p.maxVisible = 4; // OMNI_MQ_NATIVE_V1
    p.build = omniHubAppsBuild; p.input = omniHubAppsInput;
    p.faces = { { 0, "Open" }, { 1, "Back" } };
    omniFxPush(std::move(p));
}
// --- s2 (Astra's HUD answer 2): Controls: the buttons the hint bar no longer shows stay findable here ----------------
static void omniControlsBuild(OmniFxPanel& p)
{
    const bool ps = playStationIcons;
    int id = 1;
    auto row = [&](const char* action, const char* button) { OmniFxRow r; r.id = id++; r.label = action; r.value = button; p.rows.push_back(r); };
    row("Click", ps ? "Cross" : "A");
    row("Address", ps ? "Triangle" : "Y");
    row("New tab", ps ? "Square" : "X");
    row("Switch tabs", ps ? "L1 / R1" : "LB / RB");
    row("Back", ps ? "Circle" : "B");
    row("Close tab", ps ? "R3 (press the right stick)" : "RS (press the right stick)");
    row("Settings", ps ? "Create" : "View");
    row("This menu", ps ? "Options" : "Menu");
    row("Send current link to Downloads", ps ? "R2" : "RT");
    row("Saved links", ps ? "L2" : "LT");
    omniAdControlsRows(p, id); // OMNI_ADDONS_V1
    p.subtitle = ps ? "PlayStation buttons" : "Xbox buttons";
}
static bool omniControlsInput(OmniFxPanel&, const OmniFxRow&, int b) { return b == SDL_CONTROLLER_BUTTON_A; }
static void omniControlsShow()
{
    OmniFxPanel p;
    p.title = "Controls"; p.w = 760;
    p.build = omniControlsBuild; p.input = omniControlsInput;
    p.faces = { { 1, "Back" } };
    p.extra = "Button labels: Settings > Controller buttons";
    omniFxPush(std::move(p));
}

// --- the quick menu --------------------------------------------------------------------------------
enum { omniQmBack = 1, omniQmForward, omniQmReload, omniQmHome, omniQmNewTab, omniQmTabs, omniQmFind, omniQmZoomOut, omniQmZoomIn,
    omniQmZoomReset, omniQmReader, omniQmTranslate, omniQmBookmark, omniQmCopy, omniQmSite, omniQmBookmarks, omniQmHistory, omniQmDownloads,
    omniQmReopen, omniQmPrivate, omniQmTools, omniQmSettings, omniQmBrowserSettings, omniQmExit, omniQmApps, omniQmControls };
static void omniFxQuickAllBuild(OmniFxPanel& p)
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
    omniAdQuickTiles(p); // OMNI_ADDONS_V1: quick-switch add-on (press: this site, hold: all sites), Add-ons
    add(omniQmSite, "Site settings", true, omniIconShield);
    omniF2QuickExtra(p); // OMNI_FEATURES_V2: Fill saved login when there is one
    omniFxBookmarksLoad();
    add(omniQmBookmarks, "Bookmarks", true, -1, std::to_string(omniFxBookmarks.size()));
    add(omniQmHistory, "History", true);
    const int running = omniFxDownloadsRunning();
    add(omniQmDownloads, "Downloads", true, -1, running ? std::to_string(running) + " running" : "");
    add(omniQmApps, "Apps", true);   // s2 OMNI_HUB_CARDS_V1
    add(omniQmReopen, "Reopen closed tab", !omniFxClosed.empty() && !four);
    add(omniQmPrivate, "New private tab", !four);
    add(omniQmTools, "Browser tools", true);
    add(omniQmSettings, "Settings", true, omniIconGear);
    add(omniQmBrowserSettings, "Browser settings", true, omniIconGear);
    add(omniQmControls, "Controls", true);   // s2: R3 close tab, View settings
    add(omniQmExit, "Exit Omni", true, omniIconClose);
    p.rows.back().danger = true;
    p.subtitle = page ? host : t && t->omniNewTabPage ? std::string("New tab") : std::string();
}
// OMNI_MQ_NATIVE_V1: existing commands stay available; More holds the remainder.
enum { omniMqBrowse = 8000, omniMqToggles, omniMqApps, omniMqSettings, omniMqMore, omniMqBlock };
static bool omniFxQuickInput(OmniFxPanel&, const OmniFxRow&, int);
static int omniMqGroup(int id)
{
    switch (id) {
    case omniQmTabs: case omniQmBookmarks: case omniQmHistory: case omniQmBack: case omniQmForward: case omniQmReload: return 1;
    case omniMqBlock: case 303: return 2; // existing omniF3Dark
    case omniQmApps: case 381: return 3; // existing Add-ons list
    case omniQmSettings: case omniQmBrowserSettings: case omniQmSite: case omniQmControls: return 4;
    default: return 5;
    }
}
static void omniFxQuickBuild(OmniFxPanel& p)
{
    if (!p.mode) {
        p.subtitle = "Browse, adjust, open an app";
        const char* labels[] = { "Browse", "Quick toggles", "Apps", "Settings", "More" };
        for (int i = 0; i < 5; ++i) { OmniFxRow r; r.id = omniMqBrowse + i; r.label = labels[i]; p.rows.push_back(r); }
        return;
    }
    omniFxQuickAllBuild(p);
    OmniFxRow block; block.id = omniMqBlock; block.label = "uBlock"; block.value = omniBlockerFailed() ? "Error" : omniBlockerEnabled() ? "On" : "Off";
    p.rows.push_back(block);
    p.rows.erase(std::remove_if(p.rows.begin(), p.rows.end(), [&](const OmniFxRow& r) { return omniMqGroup(r.id) != p.mode; }), p.rows.end());
    for (auto& r : p.rows) if (r.id == 303) r.label = "Dark mode";
}
static bool omniFxQuickInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (!r.enabled) return true;
    if (r.id >= omniMqBrowse && r.id <= omniMqMore) {
        OmniFxPanel next; next.title = r.label; next.mode = r.id - omniMqBrowse + 1;
        next.w = 1000; next.rowH = 56; next.maxVisible = 8;
        next.build = omniFxQuickBuild; next.input = omniFxQuickInput;
        next.faces = { { 0, "Choose" }, { 1, "Back" } }; omniFxPush(std::move(next)); return true;
    }
    if (r.id == omniMqBlock) { if (omniBlockerSetEnabled(!omniBlockerEnabled()) && active()) WKPageReload(active()->page); return true; }
    if (r.id >= 900) return omniF2QuickInput(r, b); // OMNI_FEATURES_V2
    if (omniF3QuickAction(r.id)) return true; // OMNI_FEATURES_V3
    if (omniAdQuickAction(r.id)) return true; // OMNI_ADDONS_V1
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
    case omniQmApps: omniHubAppsShow(); return true;   // s2 OMNI_HUB_CARDS_V1
    case omniQmControls: omniControlsShow(); return true;   // s2
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
    p.title = "Options"; p.cols = 2; p.w = 1000; p.rowH = 92; p.maxVisible = 4; // OMNI_MQ_NATIVE_V1
    p.build = omniFxQuickBuild; p.input = omniFxQuickInput;
    p.faces = { { 0, "Choose" }, { 1, "Close" } };
    p.extra = "D-pad: move   Options: close";
    omniFxPush(std::move(p));
    omniFxStack.back().sel = 0;   // Browse
}

#include "OmniMqQuickAccess.h" // OMNI_MQ_NATIVE_V1
