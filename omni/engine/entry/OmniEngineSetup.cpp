// Omni Engine test: WebKit context/view setup + navigation callbacks.
// SPDX-License-Identifier: GPL-3.0-or-later
#include "OmniEngineState.h"

#include <WebKit/WKContextConfigurationPlayStation.h>
#include <WebKit/WKContextConfigurationRef.h>
#include <WebKit/WKContextPrivate.h>
#include <WebKit/WKPageConfigurationRef.h>
#include <WebKit/WKPageNavigationClient.h>
#include <WebKit/WKPreferencesRef.h>
#include <WebKit/WKPreferencesRefPrivate.h>
#include <WebKit/WKRunLoop.h>
#include <WebKit/WKWebsiteDataStoreConfigurationRef.h>
#include <WebKit/WKWebsiteDataStoreRef.h>

#include <sys/stat.h>

namespace OmniTest {
void onFinished(int gen);
void onFailed(int gen, WKErrorRef error);
}

using namespace OmniTest;

static WKRetainPtr<WKStringRef> str(const std::string& s)
{
    return adoptWK(WKStringCreateWithUTF8CString(s.c_str()));
}

static void didFinish(WKPageRef, WKNavigationRef, WKTypeRef, const void*)
{
    onFinished(state().generation.load());
}

static void didFail(WKPageRef, WKNavigationRef, WKErrorRef error, WKTypeRef, const void*)
{
    onFailed(state().generation.load(), error);
}

static void webProcessCrashed(WKPageRef, const void*)
{
    logf("  WEB PROCESS CRASHED");
    advance(state().generation.load());
}

int omniEngineTestMain(const char* outDir)
{
    State& S = state();
    S.outDir = outDir;
    mkdir(outDir, 0777);
    S.log = fopen((S.outDir + (!access("/data/omni/tls-selftest.flag", F_OK) ? "/tls-test.txt" : "/engine-test.txt")).c_str(), "w");
    logf("Omni Engine test (WebKit PlayStation port, homebrew)");

    WKRunLoopInitializeMain();

    std::string profile = S.outDir + "/profile";
    mkdir(profile.c_str(), 0777);
    auto cfg = adoptWK(WKContextConfigurationCreate());
    WKContextConfigurationSetUserId(cfg.get(), -1);
    // markers: the launcher spawns the multi-call ELF and passes these as role
    WKContextConfigurationSetWebProcessPath(cfg.get(), str("/omni/WebProcess").get());
    WKContextConfigurationSetNetworkProcessPath(cfg.get(), str("/omni/NetworkProcess").get());

    auto ds = adoptWK(WKWebsiteDataStoreConfigurationCreate());
    WKWebsiteDataStoreConfigurationSetNetworkCacheDirectory(ds.get(), str(profile + "/NetworkCache").get());
    WKWebsiteDataStoreConfigurationSetLocalStorageDirectory(ds.get(), str(profile + "/LocalStorage").get());
    WKWebsiteDataStoreConfigurationSetIndexedDBDatabaseDirectory(ds.get(), str(profile + "/IndexedDB").get());
    auto store = adoptWK(WKWebsiteDataStoreCreateWithConfiguration(ds.get()));

    S.context = adoptWK(WKContextCreateWithConfiguration(cfg.get()));
    WKContextSetPrimaryWebsiteDataStore(S.context.get(), store.get());
    WKContextSetUsesSingleWebProcess(S.context.get(), true);

    auto prefs = adoptWK(WKPreferencesCreate());
    // CPU backing store so WKPagePaint can read the pixels back
    WKPreferencesSetAcceleratedCompositingEnabled(prefs.get(), false);
    WKPreferencesSetNeedsSiteSpecificQuirks(prefs.get(), true);

    auto pageCfg = adoptWK(WKPageConfigurationCreate());
    WKPageConfigurationSetContext(pageCfg.get(), S.context.get());
    WKPageConfigurationSetPreferences(pageCfg.get(), prefs.get());
    WKPageConfigurationSetWebsiteDataStore(pageCfg.get(), store.get());

    S.view = adoptWK(WKViewCreate(pageCfg.get()));
    WKViewSetSize(S.view.get(), WKSizeMake(kW, kH));
    WKViewSetVisible(S.view.get(), true);
    WKViewSetActive(S.view.get(), true);
    WKViewSetFocus(S.view.get(), true);
    S.page = WKViewGetPage(S.view.get());

    WKPageNavigationClientV0 nav { };
    nav.base.version = 0;
    nav.didFinishNavigation = didFinish;
    nav.didFailProvisionalNavigation = didFail;
    nav.didFailNavigation = didFail;
    nav.webProcessDidCrash = webProcessCrashed;
    WKPageSetPageNavigationClient(S.page, &nav.base);

    WKRunLoopCallOnMainThread([](void*) { loadNext(); }, nullptr);
    WKRunLoopRunMain();
    return 0;
}
