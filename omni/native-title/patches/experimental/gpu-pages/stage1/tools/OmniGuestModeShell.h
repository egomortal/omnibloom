// OMNI_GUEST_MODE_V1: guest mode (shell side). Included from OmniBrowser.cpp after OmniHistoryKeepShell.h (inside its
// anonymous namespace: every store it stashes is defined above). The pure part is OmniGuestMode.h (state machine, write
// allowlist, Stash, session text, texts); the reasons and the list of chokepoints are in tools/apply_guest_mode.py.
// Main thread only. apply_guest_mode.py puts the OMNI_GST_HAS_* lines (which optional patches this tree has) on top.
//
// Options (top level) > "Guest mode": asks (Cancel focused), then on the next tick: the owner's files are flushed and the
// owner's tabs captured as session text, the owner's lists are stashed (taken: the guest sees none) and the settings a
// guest may change copied (kept: dropped on leaving), every tab closes, the private (non-persistent) data store is
// replaced by a fresh one and one guest tab opens on a plain start page. Every tab opened while omniGuest() is a private
// tab on that store (newTab). "Leave guest mode": the guest tabs close, the guest store is cleared and released, the
// stash comes back, uBlock's switch / trusted sites are put back and the owner's tabs are made again from the captured
// text (not through omniEverydayStart: its startup choice and crash marker belong to a real start).
// OMNI_GUEST_MODE_V1_R2: parental controls, clipboard history, highlights, notice history, reader-auto, shortcuts,
// quick-bar / hint bar, uBlock switch + trusted sites (memory only, put back), add-ons and the Downloads app (blocked).
#pragma once

namespace OGST = OmniGuestMode;

static OGST::Stash omniGstStash;
static int omniGstPending = 0;          // 1 enter, 2 leave: the question's answer, done on the next omniGstTick
static std::string omniGstOwnerTabs;    // omniSessionText() when guest mode began
static bool omniGstUboEnabled = true;   // uBlock as the owner left it
static std::vector<std::string> omniGstUboTrusted;

// --- chokepoints ---------------------------------------------------------------------------------------------------------
// omniIoQueue(): a write under the data folder in guest mode (logged once per file).
static void omniGstRefused(const std::string& path)
{
    static std::unordered_set<std::string> told;
    if (told.size() < 64 && told.insert(path).second) { fprintf(stderr, "OMNI GUEST: write refused in guest mode: %s\n", path.c_str()); fflush(stderr); }
}
// Panels and actions that would show or change the owner's data.
static bool omniGstBlocked(const char* what)
{
    if (!omniGuest()) return false;
    notice(OGST::blockedNotice(what));
    return true;
}
// The private context + store, made when missing (as omniNewPrivateTab makes them).
static void omniGstPrivateEnsure()
{
    if (omniPrivateContext) return;
    omniPrivateStore = adoptWK(WKWebsiteDataStoreCreateNonPersistentDataStore());
    auto config = adoptWK(WKContextConfigurationCreate());
    WKContextConfigurationSetUserId(config.get(), -1);
    omniPrivateContext = adoptWK(WKContextCreateWithConfiguration(config.get()));
    WKContextSetPrimaryWebsiteDataStore(omniPrivateContext.get(), omniPrivateStore.get());
    WKContextSetUsesSingleWebProcess(omniPrivateContext.get(), true);
    omniAdNotePrivateContext(omniPrivateContext.get()); // OMNI_ADDONS_V1
}
// newTab(): a tab opened in guest mode uses the guest (private, non-persistent) context and store.
static bool omniGstConfig(WKPageConfigurationRef config)
{
    if (!omniGuest()) return false;
    omniGstPrivateEnsure();
    WKPageConfigurationSetContext(config, omniPrivateContext.get());
    WKPageConfigurationSetWebsiteDataStore(config, omniPrivateStore.get());
    return true;
}
// omniDownloadInstall(): no file reaches the shared download folder from a guest session.
static void omniGstDownloadRefused(WKDownloadRef download)
{
    static WKDownloadClientV0 client {};
    client.base.version = 0;
    client.decideDestinationWithResponse = [](WKDownloadRef, WKURLResponseRef, WKStringRef, const void*) -> WKStringRef { return nullptr; };   // no destination: cancelled
    WKDownloadSetClient(download, &client.base);
    WKDownloadCancel(download, nullptr, [](WKDataRef, const void*) {});
    fprintf(stderr, "OMNI GUEST: download cancelled (guest mode)\n"); fflush(stderr);
    notice(OGST::downloadNotice());
}
// omniScuRender(): the plain guest start page (search only; the page's own "private" look).
static std::string omniGstStartJson(const std::string& hint)
{
    OmniStartCustom::Config g = OmniStartCustom::defaults();
    for (int s = 0; s < OmniStartCustom::sCount; ++s) g.hidden[s] = s != OmniStartCustom::sSearch;
    return OmniStartCustom::pageJson(g, true, false, {}, {}, std::string(), hint);
}
// omniDrawTopBar(): "GUEST" over the identity while guest rules apply.
static void omniGstDrawBadge()
{
    if (!omniGuest()) return;
    fill(0, 0, 98, 52, omniTheme().bg);
    fillRounded(10, 15, 80, 28, 14, { 150, 110, 235, 255 });
    omniLabel(OGST::kBadge, 50, 29, omniSmallBold, { 255, 255, 255, 255 }, 1, 72);
}
// Parental controls' "Lock private tabs": guest tabs are private tabs, so guest mode is off while it is on.
static bool omniGstParentalLocked()
{
#if OMNI_GST_HAS_PARENTAL
    omniParLoad();
    return omniParStore.active() && omniParStore.lockPrivate;
#else
    return false;
#endif
}

// --- tabs and the guest store ----------------------------------------------------------------------------------------------
// Every tab closes as closeTab() closes one, without its "last tab: open a new one" step and without loading the
// lazily restored tabs it passes on the way.
static void omniGstDropAllTabs()
{
    if (pageFullscreen && active()) { WKViewRequestExitFullScreen(active()->view.get()); setPageFullscreen(false); }
    while (!tabs.empty()) {
        Tab* t = tabs.back().get();
        t->omniLazyURL.clear();
        omniModalsDropTab(t);
        omniFxTabClosing(*t);
        WKPageClose(t->page);
        tabs.pop_back();
    }
    selected = 0;
}
// The private store is cleared (cookies, caches, storage, databases, service workers) and released with its context;
// the next private / guest tab makes new ones. Its web process ends with its last page.
static void omniGstWipePrivate()
{
    if (omniPrivateStore) {
        WKWebsiteDataStoreRef store = omniPrivateStore.get();
        auto done = [](void*) {};
        WKHTTPCookieStoreDeleteAllCookies(WKWebsiteDataStoreGetHTTPCookieStore(store), nullptr, done);
        WKWebsiteDataStoreRemoveNetworkCache(store, nullptr, done);
        WKWebsiteDataStoreRemoveLocalStorage(store, nullptr, done);
        WKWebsiteDataStoreRemoveAllIndexedDatabases(store, nullptr, done);
        WKWebsiteDataStoreRemoveAllServiceWorkerRegistrations(store, nullptr, done);
        WKWebsiteDataStoreRemoveAllFetchCaches(store, nullptr, done);
    }
    omniAdNotePrivateContext(nullptr);   // OMNI_ADDONS_V1 compares page contexts with it
    omniPrivateContext.clear();
    omniPrivateStore.clear();
}
// The owner's tabs again, from the text captured on entering (omniEverydayStart's making of tabs, pins and groups).
static bool omniGstRestoreTabs()
{
    OGST::SavedTabs s = OGST::parseSession(omniGstOwnerTabs, size_t(std::max(1, omniF3TabLimit())));
    omniGstOwnerTabs.clear();
    for (const std::string& line : s.extra) if (!omniPtRestoreLine(line)) omniTgRestoreLine(line);
    if (s.tabs.empty()) s.tabs.emplace_back("newtab", "New tab");
    omniF3Restoring = true;
    for (auto& [url, title] : s.tabs) {
        Tab* tab = newTab();
        if (!tab) break;
        tab->omniLazyURL = url;
        if (url != "newtab") { tab->url = url; tab->title = title.empty() ? omniBlockerHostOf(url) : title; }
    }
    omniF3Restoring = false;
    int sel = s.selected;
    omniTgRestoreApply(sel);
    omniPtRestoreApply(sel);
    if (tabs.empty()) return false;
    const void* shown = tabs[size_t(std::clamp(sel, 0, int(tabs.size()) - 1))].get();
    omniTgNormalize();
    for (size_t i = 0; i < tabs.size(); ++i) if (tabs[i].get() == shown) sel = int(i);
    activate(size_t(std::clamp(sel, 0, int(tabs.size()) - 1)));
    omniSessionSaved = omniSessionText();
    return true;
}
// uBlock (OmniBlocker.cpp writes its own files; in guest mode it keeps changes in memory): the owner's switch and
// trusted sites back, through its setters (which write the owner's values again).
static void omniGstUboRestore()
{
    if (omniBlockerEnabled() != omniGstUboEnabled) omniBlockerSetEnabled(omniGstUboEnabled);
    const std::vector<std::string> now = omniBlockerTrustedSites();
    for (const std::string& h : now)
        if (std::find(omniGstUboTrusted.begin(), omniGstUboTrusted.end(), h) == omniGstUboTrusted.end()) omniBlockerSetSiteTrusted(h, false);
    for (const std::string& h : omniGstUboTrusted)
        if (std::find(now.begin(), now.end(), h) == now.end()) omniBlockerSetSiteTrusted(h, true);
    omniGstUboTrusted.clear();
}

// --- enter / leave -------------------------------------------------------------------------------------------------------------
static void omniGstEnterNow()
{
    OGST::Machine& m = OGST::state();
    if (!m.canEnter() || omniTestMode() || ytTimeline) { notice(OGST::unavailableNotice()); return; }
    if (omniGstParentalLocked()) { notice(OGST::parentalLockedNotice()); return; }
    // 1. the owner's files are current before writes stop; the owner's tabs as session text
    if (omniKw.dirty) { omniIoQueue(omniData("kb-words.txt"), omniKw.learned.serialize(), false); omniKw.dirty = false; }
    omniSessionSave();
    omniIoFlush();
    omniGstOwnerTabs = omniSessionText();
    // stores loaded first: a copy of an unloaded store would come back "loaded" but empty, and the owner's next change
    // would then write that empty list over the file
    omniPrefsLoad(); omniDkLoad(); omniPermLoad(); omniApLoad(); omniHoLoad(); omniPnLoad(); omniStLoad(); omniTvLoad();
    omniBarsLoad();
#if OMNI_GST_HAS_READER_AUTO
    omniRauLoad();
#endif
    omniGstUboEnabled = omniBlockerEnabled();
    omniGstUboTrusted = omniBlockerTrustedSites();
    if (!m.beginEnter()) return;
    omniFxCloseAll();
    editing = false; settingsOpen = false;
    // 2. the owner's lists: taken (the guest starts with empty ones; the guarded loaders don't read the files)
    omniGstStash.take(omniHistory);
    omniGstStash.take(omniFxBookmarks);
    omniGstStash.take(omniBmFolderOf);
    omniGstStash.take(omniTsList);
    omniGstStash.take(omniWapList);
    omniGstStash.take(omniKw.learned);
    omniGstStash.take(omniKbClipboard);
    omniGstStash.take(omniFxClosed);
    omniGstStash.take(omniShortcuts);                 // r2: the start tiles / shortcuts (edits: memory only)
#if OMNI_GST_HAS_CLIP
    omniGstStash.take(omniClh);                       // r2: clipboard history (the guest's copies are dropped on leaving)
#endif
#if OMNI_GST_HAS_HIGHLIGHTS
    omniGstStash.take(omniHltItems);                  // r2: never re-applied in guest tabs, not listed
    omniHltFocus = OmniHltFocus();
#endif
#if OMNI_GST_HAS_NOTICES
    omniGstStash.take(omniNhList);                    // r2: "Recent notices" (nothing is recorded in guest mode)
#endif
    // private-tab "this run" choices (the guest's tabs are private tabs): taken, so neither side sees the other's
    omniGstStash.take(omniApSession);
    omniGstStash.take(omniHoSession);
    omniGstStash.take(omniPnSession);
    omniGstStash.take(omniStSession);
    omniGstStash.take(omniTvPrivate);
#if OMNI_GST_HAS_READER_AUTO
    omniGstStash.take(omniRauSession);
#endif
    // settings a guest can change: kept (the guest's changes stay in memory and are dropped on leaving)
    omniGstStash.keep(omniSiteZoom);
    omniGstStash.keep(omniMobileHosts);
    omniGstStash.keep(omniDkSites);
    omniGstStash.keep(omniPerm);
    omniGstStash.keep(omniApStore);
    omniGstStash.keep(omniHoStore);
    omniGstStash.keep(omniPnSaved);
    omniGstStash.keep(omniStStore);
    omniGstStash.keep(omniTvSaved);
    omniGstStash.keep(omniQaHidden);                  // r2: quick bar / hint bar (ui-bars.txt: memory only)
    omniGstStash.keep(omniHintsHidden);
    omniGstStash.keep(omniAdState);                   // r2: add-on state an add-on itself changes (panels blocked)
#if OMNI_GST_HAS_READER_AUTO
    omniGstStash.keep(omniRauStore);
#endif
    omniPerm.session.clear();
    omniSuggestFor = "\x01";
    // 3. tabs: the owner's close (captured above), a fresh guest store, one guest tab
    omniGstDropAllTabs();
    omniFxClosed.clear();   // the owner's tabs just closed went into the (guest's) list
    omniGstWipePrivate();
    m.finishEnter();
    if (newTab()) omniOpenNewTabPage(active());
    fprintf(stderr, "OMNI GUEST: guest session %u started (%zu stores stashed)\n", m.sessions(), omniGstStash.size()); fflush(stderr);
    notice(OGST::enteredNotice());
    omniShellDirty = true;
}
static void omniGstLeaveNow()
{
    OGST::Machine& m = OGST::state();
    if (!m.beginLeave()) return;
    omniFxCloseAll();
    editing = false; settingsOpen = false;
    omniGstDropAllTabs();
    omniGstWipePrivate();
    omniGstStash.restore();
    omniSuggestFor = "\x01";
    ++omniDkVersion;   // dark pages: the owner's site list again
    m.finishLeave();
    omniGstUboRestore();   // owner rules again: the setters write the owner's values
    const bool restored = omniGstRestoreTabs();
    if (tabs.empty() && newTab()) omniOpenNewTabPage(active());
    fprintf(stderr, "OMNI GUEST: guest session ended, %s (%zu tabs)\n", restored ? "owner tabs restored" : "restore FAILED", tabs.size()); fflush(stderr);
    notice(OGST::leftNotice());
    omniShellDirty = true;
}
// From omniF3Tick, every pass.
static void omniGstTick(uint32_t)
{
    if (omniGstPending) {
        const int p = std::exchange(omniGstPending, 0);
        if (p == 1) omniGstEnterNow(); else omniGstLeaveNow();
    }
    // the shell's Settings (theme, display, bars: written straight to their files) stay locked for a guest
    if (settingsOpen && omniGuest()) { settingsOpen = false; notice(OGST::blockedNotice("Settings")); omniShellDirty = true; }
}

// --- Options (top level): "Guest mode" / "Leave guest mode" -----------------------------------------------------------------
static void omniGstQuickRow(OmniFxPanel& p)
{
    if (omniTestMode() || ytTimeline) return;
    const bool guest = omniGuest();
    OmniFxRow r; r.id = omniGstQuickRowId; r.label = OGST::rowLabel(guest);
    r.value = !guest && omniGstParentalLocked() ? OGST::parentalLockedValue() : OGST::rowValue(guest);
    r.enabled = OGST::state().canEnter() || OGST::state().canLeave();
    p.rows.push_back(r);
}
static bool omniGstQuickInput(const OmniFxRow& r, int b)
{
    if (r.id != omniGstQuickRowId || b != SDL_CONTROLLER_BUTTON_A) return false;
    if (!r.enabled || omniGstPending) return true;
    const bool leave = OGST::state().canLeave();
    if (!leave && omniGstParentalLocked()) { notice(OGST::parentalLockedNotice()); return true; }   // no PIN is asked here
    omniAsk(leave ? OGST::leaveTitle() : OGST::enterTitle(), leave ? OGST::leaveBody() : OGST::enterBody(), leave ? "Leave" : "Start", [leave](bool ok) {
        if (!ok) return;
        omniFxCloseAll();
        omniGstPending = leave ? 2 : 1;
    });
    return true;
}
