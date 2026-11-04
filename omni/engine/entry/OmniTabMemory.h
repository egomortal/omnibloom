// OMNI_FEATURES_V3: more than four tabs, carefully. The tab limit is a setting (default 4, as
// before, until memory is measured on the console). Two guards keep the web process and the shell
// inside their memory:
//  - "Tabs kept loaded": beyond that many loaded tabs, the least recently shown background tab is
//    unloaded: its session history is copied (WKPageCopySessionState), the page is replaced by
//    about:blank and the history list is then cleared, so neither the document nor a back/forward
//    cache entry keeps its memory. When the tab is shown again the saved history is restored
//    (WKPageRestoreFromSessionState: Back/Forward work as before, and the current page reloads). Tabs playing audio or video, loading, crashed or
//    owned by the media section are never unloaded.
//  - Shell flexible memory (sceKernelAvailableFlexibleMemorySize, the same query the startup log
//    prints): below `refuse_mib` new tabs are refused with a message; below `unload_mib` one
//    background tab is unloaded every 4 s. The web process's own memory cannot be queried from the
//    shell on this port (WKContextGetStatistics is an empty stub), so the loaded-tab cap is the
//    guard for it.
// Every change is logged as "OMNI TABMEM: ..." for the console measurement.
#pragma once

struct OmniTmTab {
    bool unloaded = false, blankDone = false;
    std::string url, title;          // shown while unloaded
    WKRetainPtr<WKTypeRef> session;  // back/forward list at unload time
    uint32_t shownAt = 0;            // last time the tab was the active one
};
static std::unordered_map<const void*, OmniTmTab> omniTmTabs;
static std::string omniTmRefusal = "Tab limit reached: close a tab to open another.";
static long long omniTmFree = -1;    // MiB of shell flexible memory, -1 unknown
static uint32_t omniTmQueriedAt = 0, omniTmUnloadAt = 0;

static long long omniTmQueryMiB()
{
#ifdef __PROSPERO__
    size_t f = 0;
    if (sceKernelAvailableFlexibleMemorySize(&f)) return -1;
    return (long long)(f >> 20);
#else
    return -1;
#endif
}
static bool omniTmIsUnloaded(const Tab& t)
{
    if (!t.omniLazyURL.empty()) return true;   // restored from the session, not loaded yet
    auto f = omniTmTabs.find(&t);
    return f != omniTmTabs.end() && f->second.unloaded;
}
static int omniTmLoadedCount()
{
    int n = 0;
    for (auto& t : tabs) if (!omniTmIsUnloaded(*t)) ++n;
    return n;
}
static void omniTmLog(const char* why)
{
    size_t shm = 0; const int decoders = OmniMedia::Hw::openDecoderCount(&shm); // OMNI_TAB_MEDIA_RELEASE_V1
    fprintf(stderr, "OMNI TABMEM: %s tabs=%zu loaded=%d limit=%d keep=%d shell_free=%lld MiB (refuse<%d unload<%d) hw_decoders=%d hw_shm=%zu MiB\n", why, tabs.size(),
        omniTmLoadedCount(), omniF3Set.tabLimit, omniF3Set.keepLoaded, omniTmFree, omniF3Set.refuseMiB, omniF3Set.unloadMiB, decoders, shm >> 20);
    fflush(stderr);
}
static bool omniTmCanUnload(const Tab& t)
{
    if (&t == active() || omniTmIsUnloaded(t) || t.loading || t.crashed || omniMediaOwns(t) || !omniWebURL(t.url)) return false;
    const WKMediaState m = WKPageGetMediaState(t.page);
    if (m & (kWKMediaIsPlayingAudio | kWKMediaIsPlayingVideo)) return false;
    return true;
}
// Unloads the least recently shown background tab; false when none qualifies.
static bool omniTmUnloadOne(const char* why)
{
    Tab* best = nullptr;
    uint32_t oldest = UINT32_MAX;
    for (auto& t : tabs) {
        if (!omniTmCanUnload(*t)) continue;
        const uint32_t at = omniTmTabs[t.get()].shownAt;
        if (!best || at < oldest) { best = t.get(); oldest = at; }
    }
    if (!best) return false;
    OmniTmTab& s = omniTmTabs[best];
    s.unloaded = true; s.blankDone = false;
    s.url = best->url; s.title = best->title;
    s.session = adoptWK(WKPageCopySessionState(best->page, nullptr, nullptr));
    auto blank = adoptWK(WKURLCreateWithUTF8CString("about:blank"));
    WKPageLoadURL(best->page, blank.get());
    omniTmUnloadAt = SDL_GetTicks();
    omniShellDirty = true;
    omniTmLog((std::string("unloaded background tab (") + why + "): " + omniShownURL(s.url).substr(0, 80)).c_str());
    return true;
}

// --- hooks ------------------------------------------------------------------------------------------
static int omniF3TabLimit() { omniF3Load(); return omniTestMode() ? 4 : omniF3Set.tabLimit; }
static bool omniF3TabsFull() { return int(tabs.size()) >= omniF3TabLimit(); }
static std::string omniF3TabRefusal() { return omniTmRefusal; }
static bool omniF3TabAllowed()
{
    const int limit = omniF3TabLimit();
    if (int(tabs.size()) >= limit) {
        omniTmRefusal = limit == 4 ? "Four tabs open: close one first (Browser settings > Tab limit raises it)."
                                   : std::to_string(limit) + " tabs open (the limit in Browser settings). Close a tab first.";
        status = omniTmRefusal; statusUntil = SDL_GetTicks() + 5000;
        return false;
    }
    if (omniTestMode() || tabs.empty() || omniF3Restoring) return true;   // OMNI_FEATURES_V3_FIX1: restored tabs are lazy
    omniTmFree = omniTmQueryMiB();
    omniTmQueriedAt = SDL_GetTicks();
    if (omniTmFree >= 0 && omniTmFree < omniF3Set.refuseMiB) {
        const bool freed = omniTmUnloadOne("new tab refused");
        omniTmRefusal = "Memory is low (" + std::to_string(omniTmFree) + " MiB free): close a tab first"
            + (freed ? std::string(". A background tab was unloaded.") : std::string("."));
        status = omniTmRefusal; statusUntil = SDL_GetTicks() + 6000;
        omniTmLog("new tab refused (memory)");
        return false;
    }
    return true;
}
static bool omniF3TabFinished(Tab& tab)
{
    auto f = omniTmTabs.find(&tab);
    if (f == omniTmTabs.end() || !f->second.unloaded) return false;
    f->second.blankDone = true;
    tab.loading = false;
    WKBackForwardListClear(WKPageGetBackForwardList(tab.page));   // drops the page's back/forward cache entry too
    tab.url = f->second.url; tab.title = f->second.title;   // the strip, Tabs page and session keep the real page
    return true;
}
static void omniF3TabActivated()
{
    Tab* t = active();
    if (!t) return;
    OmniTmTab& s = omniTmTabs[t];
    s.shownAt = SDL_GetTicks();
    if (!s.unloaded) return;
    if (omniTmSkipRestore) return;   // OMNI_FEATURES_V3_FIX1: about to be closed: leave it unloaded
    s.unloaded = false;
    t->url = s.url; t->title = s.title;
    if (!s.blankDone) { WKPageStopLoading(t->page); s.session = WKRetainPtr<WKTypeRef>(); omniTmLog("unload cancelled (tab shown before the blank page loaded)"); return; }
    if (s.session) { omniApplyUserAgent(t, s.url); WKPageRestoreFromSessionState(t->page, s.session.get()); }
    else navigate(s.url);
    s.session = WKRetainPtr<WKTypeRef>();
    t->loading = true;
    notice("Reloading this tab (it was unloaded to save memory)");
    omniTmLog("reloading unloaded tab");
}
static void omniTmTick(uint32_t now)
{
    if (omniTestMode()) return;
    if (Tab* t = active()) omniTmTabs[t].shownAt = now;
    for (auto& t : tabs) {   // an unloaded tab keeps its title (the blank page may report an empty one)
        auto f = omniTmTabs.find(t.get());
        if (f != omniTmTabs.end() && f->second.unloaded && (t->title != f->second.title || t->url != f->second.url)) {
            t->title = f->second.title; t->url = f->second.url;
        }
    }
    if (now - omniTmQueriedAt >= 2000) {
        omniTmQueriedAt = now;
        const long long before = omniTmFree;
        omniTmFree = omniTmQueryMiB();
        static size_t lastTabs = 0;
        if (tabs.size() != lastTabs || (before >= 0) != (omniTmFree >= 0) || std::llabs(omniTmFree - before) >= 16) {
            lastTabs = tabs.size();
            omniTmLog("sample");
        }
        static uint32_t prune = 0;
        if (now - prune > 10000) {
            prune = now;
            for (auto it = omniTmTabs.begin(); it != omniTmTabs.end();) it = omniTabAlive(it->first) ? std::next(it) : omniTmTabs.erase(it);
        }
    }
    if (now - omniTmUnloadAt < 4000) return;
    if (omniTmFree >= 0 && omniTmFree < omniF3Set.unloadMiB) { if (omniTmUnloadOne("shell memory low")) return; }
    if (omniF3Set.keepLoaded < omniF3Set.tabLimit && omniTmLoadedCount() > omniF3Set.keepLoaded) omniTmUnloadOne("more tabs loaded than kept");
}
static void omniF3TabRowValue(const Tab& t, bool current, std::string& value)
{
    if (!current && omniTmIsUnloaded(t) && value.empty()) value = "Unloaded";
}

// --- compact tab strip (more than 4 tabs) -------------------------------------------------------------
// Four tabs or fewer: the old strip (fixed 240 px tabs), byte for byte. More: tabs shrink to fit
// x 100..1060; below 120 px each the strip scrolls (arrows at both ends, the selected tab kept in
// view). The close cross shows on the selected tab and on tabs at least 150 px wide.
struct OmniTmStrip { int x0 = 100, step = 240, first = 0, count = 0; bool arrows = false; };
static int omniTmFirst = 0;
static OmniTmStrip omniTmStripLayout()
{
    OmniTmStrip L;
    const int n = int(tabs.size()), avail = 960;
    if (n * 120 <= avail) { L.step = std::min(240, avail / std::max(1, n)); L.count = n; return L; }
    L.arrows = true; L.x0 = 100 + 30;
    const int inner = avail - 60;
    L.count = std::max(1, inner / 120); L.step = inner / L.count;
    const int sel = int(selected);
    if (sel < omniTmFirst) omniTmFirst = sel;
    if (sel >= omniTmFirst + L.count) omniTmFirst = sel - L.count + 1;
    omniTmFirst = std::clamp(omniTmFirst, 0, n - L.count);
    L.first = omniTmFirst;
    return L;
}
static bool omniF3DrawTabStrip()
{
    if (tabs.size() <= 4) return false;
    const OmniTheme& T = omniTheme();
    const OmniTmStrip L = omniTmStripLayout();
    const int w = L.step - 8;
    for (int k = 0; k < L.count; ++k) {
        const size_t i = size_t(L.first + k);
        const int x = L.x0 + k * L.step;
        const Tab& tab = *tabs[i];
        const bool sel = i == selected, hover = omniHover(x, 8, w, 44), unloaded = omniTmIsUnloaded(tab);
        if (sel) fillRounded(x, 8, w, 44, omniRadius, T.bar, 255, omniCornersTop);
        else if (hover) omniRingRect(x, 12, w, 34, omniRadius, T.accent, T.hover);
        else fillRounded(x, 12, w, 34, omniRadius, T.tab);
        if (sel) fillRounded(x + 10, 8, w - 20, 3, 1, T.accent, 255, omniCornersAll);
        if (tab.omniPrivate) fillRounded(x + 10, 41, w - 20, 3, 1, { 150, 110, 235, 255 }, 255, omniCornersAll);   // private: a purple underline
        float tx = x + 12;
        if (tab.loading) { omniSpinner(x + 18, 30, 6.5f, T.accent); tx = x + 32; }
        else if (tab.crashed || !tab.message.empty()) { omniDisc(x + 17, 30, 4, tab.crashed ? omniBad : omniWarn); tx = x + 28; }
        const bool closable = sel || w >= 150;
        const std::string title = !tab.title.empty() ? tab.title : !tab.url.empty() ? omniBlockerHostOf(tab.url) : std::string("New tab");
        omniLabel(title, tx, 30, omniSmall, unloaded ? T.inkFaint : sel ? T.ink : T.inkDim, 0, int(x + w - (closable ? 30 : 10) - tx));
        if (closable) {
            const bool closeHover = omniHover(x + w - 24, 8, 24, 44);
            if (closeHover) omniRingDisc(x + w - 14, 30, 11, T.accent, omniMix(sel ? T.bar : T.tab, T.ink, 0.16f));
            omniIcon(omniIconClose, x + w - 14, 30, closeHover || sel ? T.ink : T.inkDim);
        }
    }
    if (L.arrows) {
        const bool left = L.first > 0, right = L.first + L.count < int(tabs.size());
        if (left && omniHover(100, 8, 28, 44)) omniRingDisc(114, 30, 13, T.accent, T.hover);
        omniIcon(omniIconBack, 114, 30, left ? T.ink : T.inkFaint);
        if (right && omniHover(1032, 8, 28, 44)) omniRingDisc(1046, 30, 13, T.accent, T.hover);
        omniIcon(omniIconForward, 1046, 30, right ? T.ink : T.inkFaint);
        if (left) omniLabel(std::to_string(L.first), 114, 47, omniCaption, T.inkDim, 1);
        if (right) omniLabel(std::to_string(int(tabs.size()) - L.first - L.count), 1046, 47, omniCaption, T.inkDim, 1);
    }
    return true;
}
static bool omniF3TabStripClick(int x)
{
    if (tabs.size() <= 4 || x >= 1150) return false;   // the shield (x >= 1150) is handled before
    if (x >= 1070) {   // "+"
        if (newTab()) { if (!omniTestMode()) omniOpenNewTabPage(active()); address.clear(); editing = true; omniKbPageReset(); }
        return true;
    }
    const OmniTmStrip L = omniTmStripLayout();
    if (L.arrows && x >= 100 && x < 128) { if (selected > 0) activate(selected - 1); return true; }
    if (L.arrows && x >= 1032 && x < 1062) { if (selected + 1 < tabs.size()) activate(selected + 1); return true; }
    if (x < L.x0) return true;
    const int k = (x - L.x0) / L.step, w = L.step - 8, in = (x - L.x0) % L.step;
    if (k >= L.count || in >= w) return true;
    const size_t i = size_t(L.first + k);
    if (i >= tabs.size()) return true;
    const bool closable = i == selected || w >= 150;
    if (closable && in >= w - 26) { omniTmSkipRestore = true; activate(i); omniTmSkipRestore = false; closeTab(); } else activate(i); // OMNI_FEATURES_V3_FIX1
    return true;
}
