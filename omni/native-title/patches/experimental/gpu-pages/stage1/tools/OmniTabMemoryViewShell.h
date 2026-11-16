// OMNI_TAB_MEMORY_VIEW_V1: Tabs > Memory (shell side). Included from OmniTabMemory.h just before omniTmUnloadOne
// (inside OmniBrowser.cpp's anonymous namespace, after the panel framework). The pure part is OmniTabMemoryView.h;
// the reasons are in tools/apply_tab_memory_view.py. Everything runs on the main thread.
// Numbers: the shell's flexible memory (configured minus available: both imports the launch title already has),
// the hardware decoders' shared memory and the rendered-text cache. No per-tab number: every tab shares one web
// process and its memory cannot be read here. Queried when the panel opens and every 2 s while it is on top; nothing
// while it is closed.
#pragma once

namespace OTMV = OmniTabMemoryView;
static std::vector<const void*> omniTmvKeep;   // "Keep loaded" tabs (at most 2; this session only)
static Tab* omniTmvForce = nullptr;            // set around omniTmUnloadOne: unload exactly this tab
static uint32_t omniTmvShownAt = 0;            // last numbers refresh of the panel
enum { omniTmvTabsRowId = 120 };               // Tabs panel row (tabs 0..15, 100..102, 110, 111, groups 470..477)
enum { omniTmvKind = 7440, omniTmvRowAll = 200, omniTmvRowInfo = 201 };   // the Memory panel (tab rows: tab index)
static bool omniTmUnloadOne(const char* why);  // OmniTabMemory.h, right below

static void omniTmvForget(const void* tab) { OTMV::forget(omniTmvKeep, tab); }
static bool omniTmvKept(const Tab& t) { return OTMV::kept(omniTmvKeep, &t); }
static std::string omniTmvURL(const Tab& t) { return !t.omniLazyURL.empty() && t.omniLazyURL != "newtab" ? t.omniLazyURL : t.url; }
// Why the guard may not unload `t` (as omniTmCanUnload, which stays the decision).
static OTMV::Block omniTmvBlock(const Tab& t)
{
    if (&t == active()) return OTMV::kCurrent;
    if (omniTmIsUnloaded(t)) return OTMV::kAlready;
    if (t.loading) return OTMV::kLoading;
    if (t.crashed) return OTMV::kStopped;
    if (omniMediaOwns(t)) return OTMV::kMediaOwned;
    if (!omniWebURL(t.url)) return OTMV::kNotWeb;
    if (WKPageGetMediaState(t.page) & (kWKMediaIsPlayingAudio | kWKMediaIsPlayingVideo)) return OTMV::kPlaying;
    return OTMV::kFree;
}
static OTMV::TabState omniTmvState(const Tab& t)
{
    OTMV::TabState s;
    s.loaded = !omniTmIsUnloaded(t);
    if (omniTmCanUnload(t)) s.block = OTMV::kFree;
    else if ((s.block = omniTmvBlock(t)) == OTMV::kFree) s.block = OTMV::kNotWeb;   // never looser than the guard
    s.pinned = omniPtPinned(t);
    s.collapsed = omniTgCollapsedTab(t);
    s.kept = omniTmvKept(t);
    auto f = omniTmTabs.find(&t);
    s.shownAt = f != omniTmTabs.end() ? f->second.shownAt : 0;
    return s;
}
// omniTmUnloadOne's choice: the forced tab (Memory panel), else OTMV::pickUnload (kept tabs only when memory is low).
static Tab* omniTmvPick(const char* why)
{
    if (omniTmvForce) return omniTabAlive(omniTmvForce) && omniTmCanUnload(*omniTmvForce) ? omniTmvForce : nullptr;
    std::vector<OTMV::TabState> st;
    st.reserve(tabs.size());
    for (auto& t : tabs) st.push_back(omniTmvState(*t));
    const int i = OTMV::pickUnload(st, OTMV::allowKeptFor(why ? why : ""));
    return i < 0 ? nullptr : tabs[size_t(i)].get();
}
static bool omniTmvUnload(Tab& t)
{
    omniTmvForce = &t;
    const bool done = omniTmUnloadOne("Memory panel");
    omniTmvForce = nullptr;
    return done;
}
static int omniTmvLoaded() { int n = 0; for (auto& t : tabs) if (!omniTmIsUnloaded(*t)) ++n; return n; }

// --- the Memory panel ------------------------------------------------------------------------------------------------
static void omniTmvBuild(OmniFxPanel& p)
{
    long long used = -1, freeMiB = -1;
#ifdef __PROSPERO__
    size_t configured = 0, available = 0;
    if (!sceKernelConfiguredFlexibleMemorySize(&configured) && !sceKernelAvailableFlexibleMemorySize(&available) && configured >= available) {
        used = (long long)((configured - available) >> 20);
        freeMiB = (long long)(available >> 20);
    }
#endif
    size_t shm = 0;
    const int decoders = OmniMedia::Hw::openDecoderCount(&shm);
    omniTmvShownAt = SDL_GetTicks();
    const int loaded = omniTmvLoaded();
    p.subtitle = OTMV::summary(used, loaded, int(tabs.size()));
    p.extra = OTMV::detailLine(freeMiB, shm >> 20, decoders, omniTcCache.stats().bytes >> 10);
    p.corner = "Kept " + std::to_string(omniTmvKeep.size()) + " of " + std::to_string(OTMV::kMaxKeep);
    std::vector<OTMV::TabState> st;
    for (auto& t : tabs) st.push_back(omniTmvState(*t));
    for (size_t i = 0; i < tabs.size(); ++i) {
        const Tab& t = *tabs[i];
        const std::string title = !t.title.empty() ? t.title : !omniTmvURL(t).empty() ? omniShownURL(omniTmvURL(t)) : std::string("New tab");
        OmniFxRow r; r.id = int(i);
        r.label = OTMV::rowLabel(st[i].loaded, title);
        r.value = OTMV::rowValue(st[i]);
        r.detail = omniTmvURL(t).empty() ? std::string() : omniShownURL(omniTmvURL(t));
        p.rows.push_back(r);
    }
    const size_t n = OTMV::unloadAllPlan(st).size();
    OmniFxRow a; a.id = omniTmvRowAll; a.label = "Unload all background tabs"; a.icon = omniIconClose;
    a.value = OTMV::unloadAllValue(n); a.enabled = n > 0;
    a.detail = "Kept-loaded tabs and tabs playing or loading stay";
    p.rows.push_back(a);
    OmniFxRow info; info.id = omniTmvRowInfo; info.label = OTMV::kPerTabLabel; info.value = OTMV::kPerTabValue;
    info.detail = OTMV::kPerTabDetail; info.enabled = false;
    p.rows.push_back(info);
}
static bool omniTmvInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (r.id == omniTmvRowAll) {
        if (b != SDL_CONTROLLER_BUTTON_A) return false;
        std::vector<OTMV::TabState> st;
        for (auto& t : tabs) st.push_back(omniTmvState(*t));
        std::vector<Tab*> go;
        for (int i : OTMV::unloadAllPlan(st)) go.push_back(tabs[size_t(i)].get());
        size_t done = 0;
        for (Tab* t : go) if (omniTmvUnload(*t)) ++done;
        notice(OTMV::unloadAllNotice(done));
        return true;
    }
    if (r.id < 0 || r.id >= int(tabs.size())) return r.id == omniTmvRowInfo;
    Tab& t = *tabs[size_t(r.id)];
    switch (b) {
    case SDL_CONTROLLER_BUTTON_A: omniFxCloseAll(); activate(size_t(r.id)); return true;
    case SDL_CONTROLLER_BUTTON_X: {   // Square: unload this tab
        const OTMV::TabState s = omniTmvState(t);
        if (s.loaded && s.block == OTMV::kFree) {
            omniTmvForget(&t);   // an explicit unload ends "Keep loaded"
            if (omniTmvUnload(t)) { notice("Tab unloaded: it reloads when you show it"); return true; }
        }
        const char* why = OTMV::unloadRefusal(s);
        notice(*why ? why : "This tab can't be unloaded now");
        return true;
    }
    case SDL_CONTROLLER_BUTTON_Y: {   // Triangle: keep loaded / release
        const OTMV::KeepResult k = OTMV::toggleKeep(omniTmvKeep, &t, omniWebURL(omniTmvURL(t)) && !omniMediaOwns(t));
        notice(OTMV::keepNotice(k));
        fprintf(stderr, "OMNI TABMEM: keep loaded %s (%zu of %d)\n", k == OTMV::kKeepAdded ? "on" : k == OTMV::kKeepRemoved ? "off" : "refused",
            omniTmvKeep.size(), OTMV::kMaxKeep);
        return true;
    }
    default: return false;
    }
}
static void omniTmvShow()
{
    OmniFxPanel p;
    p.kind = omniTmvKind; p.title = "Tab memory"; p.w = 900; p.maxVisible = 8;
    p.build = omniTmvBuild; p.input = omniTmvInput;
    p.faces = { { 0, "Switch" }, { 2, "Unload" }, { 3, "Keep loaded" }, { 1, "Back" } };
    omniFxPush(std::move(p));
    if (!omniFxStack.empty() && selected < tabs.size()) omniFxStack.back().sel = int(selected);
    omniTmLog("memory panel opened");
}
// omniF3Tick: the numbers every 2 s while the panel is on top (and not hidden by the keyboard); nothing otherwise.
static void omniTmvTick(uint32_t now)
{
    if (!omniFxPanelOpen() || omniFxStack.back().kind != omniTmvKind) return;
    if (!OTMV::refreshDue(now, omniTmvShownAt)) return;
    omniFxRefresh();   // rebuild (queries again) + redraw
}

// --- Tabs panel row (declared in OmniFeatures3Decl.h, called from OmniTabsPage.h) ------------------------------------
static void omniTmvTabsRow(OmniFxPanel& p)
{
    OmniFxRow r; r.id = omniTmvTabsRowId; r.label = "Memory\xe2\x80\xa6"; r.icon = omniIconForward;
    r.value = std::to_string(omniTmvLoaded()) + " of " + std::to_string(tabs.size()) + " loaded";
    p.rows.push_back(r);
}
static bool omniTmvTabsInput(const OmniFxRow& r, int b)
{
    if (r.id != omniTmvTabsRowId) return false;
    if (b == SDL_CONTROLLER_BUTTON_A) omniTmvShow();
    return true;   // the panel takes the button
}
