// OMNI_FEATURES_V1: browser settings (search engine, home page, default zoom, text size, pointer speed,
// link snapping, D-pad left/right) stored in /data/omni/browser-settings.txt, plus the
// "Browser settings" panel and the About line.
#pragma once
#ifndef OMNI_FEATURES_LABEL
#define OMNI_FEATURES_LABEL "features-3" // OMNI_FEATURES_V3
#endif

struct OmniFxEngine { const char* name; const char* action; const char* prefix; };
static const OmniFxEngine omniFxEngines[] = {
    { "Google", "https://www.google.com/search", "https://www.google.com/search?q=" },
    { "DuckDuckGo", "https://duckduckgo.com/", "https://duckduckgo.com/?q=" },
    { "Bing", "https://www.bing.com/search", "https://www.bing.com/search?q=" },
    { "Startpage", "https://www.startpage.com/do/search", "https://www.startpage.com/do/search?q=" },
};
constexpr int omniFxEngineCount = int(sizeof(omniFxEngines) / sizeof(omniFxEngines[0]));
static const double omniFxTextSteps[] = { 0.85, 1.0, 1.15, 1.3, 1.5, 1.75 };
constexpr int omniFxTextCount = int(sizeof(omniFxTextSteps) / sizeof(omniFxTextSteps[0]));
static const char* const omniFxPointerNames[] = { "Slow", "Normal", "Fast", "Very fast" };
static const float omniFxPointerSpeed[] = { 650.f, 1050.f, 1500.f, 2000.f };   // layout px per second at full tilt
static const char* const omniFxDeadZoneNames[] = { "Small", "Medium", "Large", "Extra large" }; // OMNI_STICK_DEADZONE_V1 (radii in OmniPointerFeel.h)

struct OmniFxSettings {
    int search = 0;          // omniFxEngines index
    std::string home;        // empty: the new-tab page
    double zoom = 1.0;       // page zoom for sites without their own
    double text = 1.0;       // text size
    int pointer = 1;         // omniFxPointerNames index
    bool snap = true;        // pointer snaps to the nearest link when the stick is released
    int dpad = 0;            // D-pad left/right while browsing: 0 back / forward, 1 previous / next tab
    int deadzone = 1;        // OMNI_STICK_DEADZONE_V1: omniFxDeadZoneNames index (1 Medium = the dead zones used before)
    std::string pstyle = "omni"; // OMNI_POINTER_STYLE_V1: "omni", "art:<name>" or "file:<picture>" (OmniPointerStyle.h)
    int psize = 2;           // OMNI_POINTER_STYLE_V1: omniPtrSizes index (2 = 100%)
    int pcolour = 0;         // OMNI_POINTER_STYLE_V1: omniPtrColours index (0 = white)
    bool poutline = true;    // OMNI_POINTER_STYLE_V1: contrasting outline
    int popacity = 0;        // OMNI_POINTER_STYLE_V1: omniPtrOpacities index (0 = 100%)
};
static OmniFxSettings omniFxSet;
static bool omniFxSetLoaded = false;
static void omniFxLoad()
{
    if (omniFxSetLoaded) return;
    omniFxSetLoaded = true;
    if (FILE* f = fopen(omniData("browser-settings.txt").c_str(), "r")) {
        char line[2400];
        while (fgets(line, sizeof(line), f)) {
            std::string s(line);
            while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
            const size_t t = s.find('\t');
            if (t == std::string::npos) continue;
            const std::string k = s.substr(0, t), v = s.substr(t + 1);
            if (k == "search") omniFxSet.search = std::clamp(atoi(v.c_str()), 0, omniFxEngineCount - 1);
            else if (k == "home") omniFxSet.home = omniWebURL(v) ? v : std::string();
            else if (k == "zoom") { const double z = atof(v.c_str()); if (z >= 0.5 && z <= 2.5) omniFxSet.zoom = z; }
            else if (k == "text") { const double z = atof(v.c_str()); if (z >= 0.85 && z <= 1.75) omniFxSet.text = z; }
            else if (k == "pointer") omniFxSet.pointer = std::clamp(atoi(v.c_str()), 0, 3);
            else if (k == "snap") omniFxSet.snap = v != "0";
            else if (k == "dpad") omniFxSet.dpad = std::clamp(atoi(v.c_str()), 0, 1);
            else if (k == "deadzone") omniFxSet.deadzone = std::clamp(atoi(v.c_str()), 0, 3); // OMNI_STICK_DEADZONE_V1
            else if (k == "ptrstyle") { if (v.size() <= 160 && (v == "omni" || v.rfind("art:", 0) == 0 || v.rfind("file:", 0) == 0)) omniFxSet.pstyle = v; } // OMNI_POINTER_STYLE_V1
            else if (k == "ptrsize") omniFxSet.psize = std::clamp(atoi(v.c_str()), 0, 8);
            else if (k == "ptrcolour") omniFxSet.pcolour = std::clamp(atoi(v.c_str()), 0, 11);
            else if (k == "ptroutline") omniFxSet.poutline = v != "0";
            else if (k == "ptropacity") omniFxSet.popacity = std::clamp(atoi(v.c_str()), 0, 6);
        }
        fclose(f);
    }
}
static void omniFxSave()
{
    char b[512];
    snprintf(b, sizeof(b), "search\t%d\nzoom\t%.3f\ntext\t%.3f\npointer\t%d\nsnap\t%d\ndpad\t%d\ndeadzone\t%d\nptrsize\t%d\nptrcolour\t%d\nptroutline\t%d\nptropacity\t%d\n",
        omniFxSet.search, omniFxSet.zoom, omniFxSet.text, omniFxSet.pointer, omniFxSet.snap ? 1 : 0, omniFxSet.dpad, omniFxSet.deadzone, // OMNI_STICK_DEADZONE_V1
        omniFxSet.psize, omniFxSet.pcolour, omniFxSet.poutline ? 1 : 0, omniFxSet.popacity); // OMNI_POINTER_STYLE_V1
    omniIoQueue(omniData("browser-settings.txt"), std::string(b) + "home\t" + omniOneLine(omniFxSet.home, 2048) + "\nptrstyle\t" + omniOneLine(omniFxSet.pstyle, 160) + "\n", false);
}

// --- hooks used by OmniBrowser.cpp -----------------------------------------------------------------
static std::string omniFxSearchPrefix() { if (omniTestMode()) return omniFxEngines[0].prefix; omniFxLoad(); return omniFxEngines[omniFxSet.search].prefix; }
static std::string omniFxSearchAction() { omniFxLoad(); return omniFxEngines[omniFxSet.search].action; }
static std::string omniFxSearchName() { omniFxLoad(); return omniFxEngines[omniFxSet.search].name; }
static double omniFxDefaultZoom() { if (omniTestMode()) return 1.0; omniFxLoad(); return omniFxSet.zoom; }
static void omniFxApplyTextZoom(Tab* tab)
{
    if (!tab || omniTestMode()) return;
    omniFxLoad();
    if (std::fabs(WKPageGetTextZoomFactor(tab->page) - omniFxSet.text) > 1e-3) WKPageSetTextZoomFactor(tab->page, omniFxSet.text);
}
static void omniFxApplyZoomEverywhere()
{
    for (auto& t : tabs) { omniApplySiteZoom(t.get()); omniFxApplyTextZoom(t.get()); }
    omniPageDirty = true;
}
static std::string omniFxPercent(double z) { char b[16]; snprintf(b, sizeof(b), "%d%%", int(z * 100 + 0.5)); return b; }
static int omniFxNearest(const double* steps, int count, double v)
{
    int i = 0;
    for (int k = 1; k < count; ++k) if (std::fabs(steps[k] - v) < std::fabs(steps[i] - v)) i = k;
    return i;
}

// --- Home ------------------------------------------------------------------------------------------
static void omniFxHome()
{
    if (!active()) return;
    omniFxLoad();
    if (omniFxSet.home.empty()) omniOpenNewTabPage(active()); else navigate(omniFxSet.home);
}

// --- Browser settings panel ------------------------------------------------------------------------
enum { omniFxSetSearch = 1, omniFxSetHome, omniFxSetZoom, omniFxSetText, omniFxSetPointer, omniFxSetSnap, omniFxSetDpad, omniFxSetDisplay, omniFxSetAbout, omniFxSetDeadZone /* OMNI_STICK_DEADZONE_V1 */,
    omniFxSetPtrStyle, omniFxSetPtrSize, omniFxSetPtrColour, omniFxSetPtrOutline, omniFxSetPtrOpacity /* OMNI_POINTER_STYLE_V1 */,
    omniFxSetJit /* OMNI_JSC_JIT_V1 */, omniFxSetGamepad /* OMNI_GAMEPAD_V1 */ };
// OMNI_JSC_JIT_V1: /data/omni/jsc-jit.flag turns on JavaScriptCore's baseline and regular-expression JIT in page
// processes started after the change (OmniMain.cpp reads it when a web process starts). Off by default.
static bool omniFxJitOn() { return !access("/data/omni/jsc-jit.flag", F_OK); }
static void omniPtrSettingsRows(OmniFxPanel& p);   // OMNI_POINTER_STYLE_V1 (OmniPointerStyle.h)
static bool omniPtrSettingsInput(int id, int b);
static std::string omniFxHomeEdit;
static void omniFxSettingsBuild(OmniFxPanel& p)
{
    omniFxLoad();
    auto add = [&](int id, const char* label, std::string value, bool stepper) { OmniFxRow r; r.id = id; r.label = label; r.value = std::move(value); r.stepper = stepper; p.rows.push_back(r); };
    add(omniFxSetSearch, "Search engine", omniFxEngines[omniFxSet.search].name, true);
    add(omniFxSetHome, "Home page", omniFxSet.home.empty() ? std::string("New-tab page") : omniShownURL(omniFxSet.home), false);
    add(omniFxSetZoom, "Default page zoom", omniFxPercent(omniFxSet.zoom), true);
    add(omniFxSetText, "Text size", omniFxPercent(omniFxSet.text), true);
    add(omniFxSetPointer, "Pointer speed", omniFxPointerNames[omniFxSet.pointer], true);
    add(omniFxSetSnap, "Pointer snaps to links", omniFxSet.snap ? "On" : "Off", true);
    omniPtrSettingsRows(p); // OMNI_POINTER_STYLE_V1: style, size, colour, outline, opacity
    add(omniFxSetDeadZone, "Stick dead zone", omniFxDeadZoneNames[std::clamp(omniFxSet.deadzone, 0, 3)], true); // OMNI_STICK_DEADZONE_V1
    add(omniFxSetDpad, "D-pad left / right", omniFxSet.dpad ? "Switch tabs" : "Back / forward", true);
    omniF3SettingsRows(p); // OMNI_FEATURES_V3: dark pages, suggestions, tab limit, tabs kept loaded, tab memory
    add(omniFxSetGamepad, "Web pages can use the controller", omniGamepadEnabled() ? "On" : "Off", true); // OMNI_GAMEPAD_V1
    add(omniFxSetJit, "JavaScript JIT (experimental: faster, less safe)", omniFxJitOn() ? "On" : "Off", true); // OMNI_JSC_JIT_V1
    add(omniFxSetDisplay, "Controller, theme and display...", "", false);
    omniF2SettingsExtra(p); // OMNI_FEATURES_V2: Passwords, Autofill, Site permissions
    add(omniFxSetAbout, "About Omni", std::string(OMNI_FEATURES_LABEL) + " \xc2\xb7 " + __DATE__, false);
    p.rows.back().enabled = true;
}
static bool omniFxSettingsInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (r.id >= 900) return omniF2SettingsInput(r, b); // OMNI_FEATURES_V2
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT, right = b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT, a = b == SDL_CONTROLLER_BUTTON_A;
    const int dir = left ? -1 : (right || a) ? 1 : 0;
    if (r.id >= 300) return omniF3SettingsInput(r, b); // OMNI_FEATURES_V3
    switch (r.id) {
    case omniFxSetSearch:
        if (!dir) return false;
        omniFxSet.search = (omniFxSet.search + dir + omniFxEngineCount) % omniFxEngineCount; omniFxSave();
        return true;
    case omniFxSetHome:
        if (a) {
            omniFxHomeEdit = omniFxSet.home;
            omniKbEdit(&omniFxHomeEdit, "Home page address (empty: new-tab page)", [](bool ok) {
                if (!ok) return;
                const std::string v = omniFxHomeEdit.find_first_not_of(" \t") == std::string::npos ? std::string() : destination(omniFxHomeEdit);
                omniFxSet.home = omniWebURL(v) ? v : std::string(); omniFxSave(); omniFxRefresh();
                notice(omniFxSet.home.empty() ? "Home: the new-tab page" : "Home page set to " + omniShownURL(omniFxSet.home));
            });
            return true;
        }
        if (b == SDL_CONTROLLER_BUTTON_X) {   // use the current page
            if (active() && omniWebURL(active()->url)) { omniFxSet.home = active()->url; omniFxSave(); notice("Home page set to " + omniShownURL(omniFxSet.home)); }
            else notice("Open a website first");
            return true;
        }
        if (b == SDL_CONTROLLER_BUTTON_Y) { omniFxSet.home.clear(); omniFxSave(); notice("Home: the new-tab page"); return true; }
        return false;
    case omniFxSetZoom: {
        if (!dir) return false;
        const int last = int(sizeof(omniZoomSteps) / sizeof(omniZoomSteps[0])) - 1;
        const int i = omniFxNearest(omniZoomSteps, last + 1, omniFxSet.zoom);
        omniFxSet.zoom = a ? 1.0 : omniZoomSteps[std::clamp(i + dir, 0, last)];
        omniFxSave(); omniFxApplyZoomEverywhere();
        return true;
    }
    case omniFxSetText: {
        if (!dir) return false;
        const int i = omniFxNearest(omniFxTextSteps, omniFxTextCount, omniFxSet.text);
        omniFxSet.text = a ? 1.0 : omniFxTextSteps[std::clamp(i + dir, 0, omniFxTextCount - 1)];
        omniFxSave(); omniFxApplyZoomEverywhere();
        return true;
    }
    case omniFxSetPointer:
        if (!dir) return false;
        omniFxSet.pointer = std::clamp(omniFxSet.pointer + (a ? (omniFxSet.pointer == 3 ? -3 : 1) : dir), 0, 3); omniFxSave();
        return true;
    case omniFxSetSnap: if (!dir) return false; omniFxSet.snap = !omniFxSet.snap; omniFxSave(); return true;
    case omniFxSetDpad: if (!dir) return false; omniFxSet.dpad = !omniFxSet.dpad; omniFxSave(); return true;
    case omniFxSetPtrStyle: case omniFxSetPtrSize: case omniFxSetPtrColour: case omniFxSetPtrOutline: case omniFxSetPtrOpacity: return omniPtrSettingsInput(r.id, b); // OMNI_POINTER_STYLE_V1
    case omniFxSetDeadZone: if (!dir) return false; omniFxSet.deadzone = (std::clamp(omniFxSet.deadzone, 0, 3) + dir + 4) % 4; omniFxSave(); return true; // OMNI_STICK_DEADZONE_V1: D-pad / Cross cycle
    case omniFxSetGamepad: if (!dir) return false; omniGamepadSetEnabled(!omniGamepadEnabled()); return true; // OMNI_GAMEPAD_V1
    case omniFxSetJit: // OMNI_JSC_JIT_V1
        if (!dir) return false;
        if (omniFxJitOn()) unlink("/data/omni/jsc-jit.flag");
        else if (FILE* f = fopen("/data/omni/jsc-jit.flag", "w")) { fputs("1\n", f); fclose(f); }
        fprintf(stderr, "jit: setting %s (applies to page processes started from now on)\n", omniFxJitOn() ? "on" : "off");
        notice(omniFxJitOn() ? "JavaScript JIT on for pages opened from now on (restart Omni to apply everywhere)" : "JavaScript JIT off for pages opened from now on (restart Omni to apply everywhere)");
        return true;
    case omniFxSetDisplay: if (!a) return false; omniFxCloseAll(); settingsOpen = true; omniSettingsRow = 0; return true;
    case omniFxSetAbout:
        if (!a) return false;
        notice(std::string("Omni ") + OMNI_FEATURES_LABEL + " (" + __DATE__ + "), WebKit engine, " + std::to_string(renderWidth) + "x" + std::to_string(renderHeight));
        return true;
    }
    return false;
}
static void omniFxSettingsShow()
{
    OmniFxPanel p;
    p.title = "Browser settings"; p.subtitle = "Saved on this console"; p.w = 800; p.maxVisible = 9;
    p.build = omniFxSettingsBuild; p.input = omniFxSettingsInput;
    p.faces = { { 0, "Change" }, { 1, "Back" } };
    p.extra = "D-pad \xe2\x97\x80 \xe2\x96\xb6 change   Y reset   Home page: X current page"; // OMNI_POINTER_STYLE_V1: Y resets pointer rows too
    omniFxPush(std::move(p));
}
