// OMNI_FEATURES_V3: browser features, round 3 (address-bar star, search suggestions, page source,
// screenshot, dark pages, tab limit with a memory guard and a compact tab strip). Included once
// from OmniBrowser.cpp right after OmniFeatures.h (inside its anonymous namespace). The settings
// live in their own file, /data/omni/browser-more.txt, so features-1's browser-settings.txt keeps
// its format. See outputs/changes/features-3/REPORT.md.
#pragma once

struct OmniF3Settings {
    bool suggest = true;     // search-engine suggestions while typing an address
    bool dark = false;       // dark pages on every site (sites can override)
    // OMNI_PERF_D_TABS: defaults 8 / 6 (were 4 / 4). Measured with background media release: 16 tabs
    // still left ~500 MiB of shell memory free; the refuse/unload guards below are unchanged.
    // A saved browser-more.txt keeps the user's own values.
    int tabLimit = 8;        // most tabs open at once (4, 6, 8, 12, 16)
    int keepLoaded = 6;      // most tabs kept loaded; older background tabs are unloaded
    int refuseMiB = 160;     // shell flexible memory below which new tabs are refused
    int unloadMiB = 112;     // ... and below which background tabs are unloaded
};
static OmniF3Settings omniF3Set;
static bool omniF3Loaded = false;
static const int omniF3TabSteps[] = { 4, 6, 8, 12, 16 };
static const int omniF3KeepSteps[] = { 2, 3, 4, 6, 8, 12, 16 };
static void omniF3Load()
{
    if (omniF3Loaded) return;
    omniF3Loaded = true;
    if (FILE* f = fopen(omniData("browser-more.txt").c_str(), "r")) {
        char line[256];
        while (fgets(line, sizeof(line), f)) {
            std::string s(line);
            while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
            const size_t t = s.find('\t');
            if (t == std::string::npos) continue;
            const std::string k = s.substr(0, t);
            const int v = atoi(s.c_str() + t + 1);
            if (k == "suggest") omniF3Set.suggest = v != 0;
            else if (k == "dark") omniF3Set.dark = v != 0;
            else if (k == "tablimit") omniF3Set.tabLimit = std::clamp(v, 4, 16);
            else if (k == "keeploaded") omniF3Set.keepLoaded = std::clamp(v, 1, 16);
            else if (k == "refuse_mib") omniF3Set.refuseMiB = std::clamp(v, 0, 4096);
            else if (k == "unload_mib") omniF3Set.unloadMiB = std::clamp(v, 0, 4096);
        }
        fclose(f);
    }
}
static void omniF3Save()
{
    char b[256];
    snprintf(b, sizeof(b), "suggest\t%d\ndark\t%d\ntablimit\t%d\nkeeploaded\t%d\nrefuse_mib\t%d\nunload_mib\t%d\n", omniF3Set.suggest ? 1 : 0,
        omniF3Set.dark ? 1 : 0, omniF3Set.tabLimit, omniF3Set.keepLoaded, omniF3Set.refuseMiB, omniF3Set.unloadMiB);
    omniIoQueue(omniData("browser-more.txt"), b, false);
}
static int omniF3Step(const int* steps, int count, int value, int dir)
{
    int i = 0;
    for (int k = 0; k < count; ++k) if (std::abs(steps[k] - value) < std::abs(steps[i] - value)) i = k;
    return steps[std::clamp(i + dir, 0, count - 1)];
}

#include "OmniTabMemory.h"
#include "OmniSuggest.h"
#include "OmniAddressStar.h"
#include "OmniPageTools.h"
#include "OmniDarkPages.h"

// --- panels of features-1 ------------------------------------------------------------------------------
enum { omniF3Shot = 301, omniF3Source, omniF3Dark,                                   // quick menu / context menu
    omniF3SiteDark = 320,                                                              // site settings
    omniF3SetDark = 340, omniF3SetSuggest, omniF3SetTabs, omniF3SetKeep, omniF3SetMemory, omniF3SetConsole };   // + OMNI_SEC_LOCALHOST_V1   // browser settings
static void omniF3QuickTiles(OmniFxPanel& p)
{
    Tab* t = active();
    const bool web = t && omniWebURL(t->url) && !omniTmIsUnloaded(*t);
    auto add = [&](int id, const char* label, bool on, std::string value = {}) { OmniFxRow r; r.id = id; r.label = label; r.enabled = on; r.value = std::move(value); p.rows.push_back(r); };
    add(omniF3Shot, "Screenshot", t != nullptr && !t->crashed);
    add(omniF3Source, "Page source", web && !omniF3TabsFull());
    add(omniF3Dark, "Dark page", web, web ? (omniDkWant(t->url) ? "On" : "Off") : std::string());
}
static bool omniF3QuickAction(int id)
{
    switch (id) {
    case omniF3Shot: omniFxCloseAll(); omniPtScreenshot(); return true;
    case omniF3Source: omniFxCloseAll(); omniPtViewSource(); return true;
    case omniF3Dark: omniDkToggleCurrent(); return true;   // the menu stays open (the tile shows the new state)
    }
    return false;
}
static void omniF3SiteRows(OmniFxPanel& p, const std::string& host)
{
    omniF3Load();
    OmniFxRow r; r.id = omniF3SiteDark; r.label = "Dark page on this site"; r.stepper = true; r.enabled = !host.empty();
    const int s = omniDkSite(omniDkHost(active() ? active()->url : std::string()));
    r.value = host.empty() ? std::string("-") : s == 1 ? "Always dark" : s == 0 ? "Never dark" : omniF3Set.dark ? "Default (dark)" : "Default (off)";
    p.rows.push_back(r);
}
static bool omniF3SiteInput(const OmniFxRow& r, int b)
{
    if (r.id != omniF3SiteDark) return false;
    const bool a = b == SDL_CONTROLLER_BUTTON_A, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT, left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT;
    if (!a && !right && !left) return false;
    if (!active() || !omniWebURL(active()->url)) return true;
    const std::string host = omniDkHost(active()->url);
    static const int order[] = { -1, 1, 0 };   // Default, Always dark, Never dark
    const int cur = omniDkSite(host);
    int i = cur == 1 ? 1 : cur == 0 ? 2 : 0;
    i = (i + (left ? 2 : 1)) % 3;
    omniDkSetSite(host, order[i]);
    return true;
}
// OMNI_SEC_LOCALHOST_V1 (sec-job1): the console-port block itself runs in the native title's child
// engine (a connect() wrap in the WebProcess/NetworkProcess payloads). The shell owns its switch, a
// flag file the children read, and the notice when a page was stopped (the children count blocks).
static bool omniSecBlockOn() { return access("/data/omni/sec-local-block.off", F_OK) != 0; }
static void omniSecBlockSet(bool on)
{
    if (on) { unlink("/data/omni/sec-local-block.off"); notice("Pages are blocked from reaching the console's own services"); return; }
    if (FILE* f = fopen("/data/omni/sec-local-block.off", "w")) { fputs("1\n", f); fclose(f); }
    notice("Warning: pages can now reach the console's own services (loader, FTP, Payload Manager)");
}
static void omniSecTick(uint32_t now)
{
    static uint32_t last = 0; static long long seen = -1;
    if (now - last < 1000) return;
    last = now;
    FILE* f = fopen("/data/omni/native/sec-blocked.txt", "r");
    if (!f) { if (seen < 0) seen = 0; return; }
    long long count = 0; char where[96] = {};
    if (fscanf(f, "%lld %95s", &count, where) < 1) count = 0;
    fclose(f);
    if (seen < 0) { seen = count; return; }   // blocks from before this session get no notice
    if (count > seen) { seen = count; notice(std::string("Blocked a page from reaching the console (") + where + ")"); }
}
static void omniF3SettingsRows(OmniFxPanel& p)
{
    omniF3Load();
    auto add = [&](int id, const char* label, std::string value, bool stepper) { OmniFxRow r; r.id = id; r.label = label; r.value = std::move(value); r.stepper = stepper; p.rows.push_back(r); };
    add(omniF3SetDark, "Dark pages (all sites)", omniF3Set.dark ? "On" : "Off", true);
    add(omniF3SetSuggest, "Search suggestions", omniF3Set.suggest ? "On" : "Off", true);
    add(omniF3SetTabs, "Tab limit", std::to_string(omniF3Set.tabLimit), true);
    add(omniF3SetKeep, "Tabs kept loaded", omniF3Set.keepLoaded >= omniF3Set.tabLimit ? std::string("All") : std::to_string(omniF3Set.keepLoaded), true);
    const long long freeMiB = omniTmQueryMiB();
    add(omniF3SetMemory, "Tab memory", std::to_string(omniTmLoadedCount()) + " of " + std::to_string(tabs.size()) + " loaded \xc2\xb7 "
        + (freeMiB >= 0 ? std::to_string(freeMiB) + " MiB free" : std::string("free memory unknown")), false);
    add(omniF3SetConsole, "Block pages from reaching the console", omniSecBlockOn() ? "On (recommended)" : "Off", true);   // OMNI_SEC_LOCALHOST_V1
}
static bool omniF3SettingsInput(const OmniFxRow& r, int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT, a = b == SDL_CONTROLLER_BUTTON_A;
    const int dir = left ? -1 : (right || a) ? 1 : 0;
    switch (r.id) {
    case omniF3SetDark: if (!dir) return false; omniF3Set.dark = !omniF3Set.dark; omniF3Save(); omniDkChanged(); return true;
    case omniF3SetSuggest: if (!dir) return false; omniF3Set.suggest = !omniF3Set.suggest; omniF3Save(); omniSuggestFor = "\x01"; return true;
    case omniF3SetTabs: {
        if (!dir) return false;
        const int n = int(sizeof(omniF3TabSteps) / sizeof(omniF3TabSteps[0]));
        const int was = omniF3Set.tabLimit;
        omniF3Set.tabLimit = a && omniF3Set.tabLimit == 16 ? 4 : omniF3Step(omniF3TabSteps, n, omniF3Set.tabLimit, dir);
        if (omniF3Set.keepLoaded >= was) omniF3Set.keepLoaded = std::min(6, omniF3Set.tabLimit);   // "All" stays at most 6 when the limit rises (OMNI_PERF_D_TABS)
        if (omniF3Set.tabLimit > omniF3Set.keepLoaded && was <= omniF3Set.keepLoaded) notice("Older background tabs unload beyond \"Tabs kept loaded\"");
        omniF3Save(); omniTmLog("tab limit changed");
        return true;
    }
    case omniF3SetKeep: {
        if (!dir) return false;
        const int n = int(sizeof(omniF3KeepSteps) / sizeof(omniF3KeepSteps[0]));
        omniF3Set.keepLoaded = std::min(omniF3Step(omniF3KeepSteps, n, std::min(omniF3Set.keepLoaded, omniF3Set.tabLimit), dir), omniF3Set.tabLimit);
        omniF3Save(); omniTmLog("tabs kept loaded changed");
        return true;
    }
    case omniF3SetConsole: if (!dir) return false; omniSecBlockSet(!omniSecBlockOn()); return true;   // OMNI_SEC_LOCALHOST_V1
    case omniF3SetMemory:
        if (!a) return false;
        omniTmFree = omniTmQueryMiB(); omniTmLog("checked from Browser settings");
        notice("Shell memory free: " + (omniTmFree >= 0 ? std::to_string(omniTmFree) + " MiB" : std::string("unknown")) + "; new tabs refused below "
            + std::to_string(omniF3Set.refuseMiB) + " MiB, background tabs unloaded below " + std::to_string(omniF3Set.unloadMiB) + " MiB");
        return true;
    }
    return false;
}
static void omniF3ContextRows(OmniFxPanel& p)
{
    Tab* t = active();
    const bool web = t && omniWebURL(t->url);
    auto add = [&](int id, const char* label, bool on) { OmniFxRow r; r.id = id; r.label = label; r.enabled = on; p.rows.push_back(r); };
    add(omniF3Source, "View page source", web && !omniF3TabsFull());
    add(omniF3Shot, "Screenshot", t != nullptr);
    add(omniF3Dark, web && omniDkWant(t->url) ? "Dark page: turn off" : "Dark page: turn on", web);
}
static bool omniF3ContextAction(int id)
{
    if (id != omniF3Source && id != omniF3Shot && id != omniF3Dark) return false;
    omniFxCloseAll();
    if (id == omniF3Source) omniPtViewSource(); else if (id == omniF3Shot) omniPtScreenshot(); else omniDkToggleCurrent();
    return true;
}

// --- per pass --------------------------------------------------------------------------------------
static void omniF3Tick()
{
    const uint32_t now = SDL_GetTicks();
    omniF3Load();
    omniTmTick(now);
    omniSgTick(now);
    omniPtTick();
    omniDkTick(now);
    omniSecTick(now);   // OMNI_SEC_LOCALHOST_V1
}
