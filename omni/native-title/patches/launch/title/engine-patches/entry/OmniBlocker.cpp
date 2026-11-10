#include "config.h"
#include "OmniBlocker.h"
#include <WebKit/WKUserContentExtensionStoreRef.h>
#include <WebKit/WKUserScriptRef.h>
#include <WebKit/WKRetainPtr.h>
#include <WebKit/WKString.h>
#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#include <sys/stat.h>
#include <unistd.h>
#include <cerrno>
#include <chrono>
#include <unordered_map>
#include <pthread.h> // OMNI_PERF_D_IDX
// OMNI_UBO_SITE_V1: per-site uBlock content. Per-site user scripts carry a URL allowlist and match
// about:/blob:/data: frames by their parent document; the C API offers neither, so these come from
// WebKit's own C++ API (as OmniNamedWorldEval.h does for named-world evaluation).
#include "OmniUBlockSite.h"
#include "APIContentWorld.h"
#include "APIUserScript.h"
#include "WKAPICast.h"
#include "WebUserContentControllerProxy.h"
#include <JavaScriptCore/JavaScript.h>
// OMNI_ADDONS_V1: add-on user style sheets, per-world message handlers and immediate injection (WebKit's C++ API, as above).
#include "APIString.h"
#include "APIUserStyleSheet.h"
#include "FrameInfoData.h"
#include "JavaScriptEvaluationResult.h"
#include "WebPageProxy.h"
#include "WebScriptMessageHandler.h"
#if __has_include("InjectUserScriptImmediately.h")
#include "InjectUserScriptImmediately.h"
#define OMNI_ADDONS_INJECT_NOW 1
#endif
#include <expected>
#include <memory>
// s3 OMNI_PAGES_V1: Omni's built-in pages (omni://pages/...) served from the title package by a URL scheme handler,
// plus the trusted page bridge (window.omnibloomHost) for those documents only.
#include "APIFrameInfo.h"
#include "APIPageConfiguration.h"
#include "WebFrameProxy.h"
#include "WebURLSchemeHandler.h"
#include "WebURLSchemeTask.h"
#include <WebCore/HTTPHeaderNames.h>
#include <WebCore/ResourceError.h>
#include <WebCore/ResourceResponse.h>
#include <WebCore/SharedBuffer.h>
#include <fstream>

// Defined by engine/scripts/patch-user-script-world.py (named isolated world).
extern "C" WKUserScriptRef WKUserScriptCreateWithSourceInWorldOmni(WKStringRef source, _WKUserScriptInjectionTime, bool forMainFrameOnly, WKStringRef worldName);

namespace {
WKRetainPtr<WKUserContentControllerRef> controller;
// OMNI_ADDONS_V1: private tabs get their own controller. Everything below (uBlock content, shell scripts,
// content filters) goes to both, so private tabs behave as before; add-ons go there only if private_safe.
WKRetainPtr<WKUserContentControllerRef> privateController;
void ucAddScript(WKUserScriptRef script)
{
    WKUserContentControllerAddUserScript(controller.get(), script);
    if (privateController) WKUserContentControllerAddUserScript(privateController.get(), script);
}
void ucRemoveAllScripts()
{
    WKUserContentControllerRemoveAllUserScripts(controller.get());
    if (privateController) WKUserContentControllerRemoveAllUserScripts(privateController.get());
}
void ucRemoveAllFilters()
{
    WKUserContentControllerRemoveAllUserContentFilters(controller.get());
    if (privateController) WKUserContentControllerRemoveAllUserContentFilters(privateController.get());
}
void ucAddFilter(WKUserContentFilterRef f)
{
    WKUserContentControllerAddUserContentFilter(controller.get(), f);
    if (privateController) WKUserContentControllerAddUserContentFilter(privateController.get(), f);
}
void addonsReaddScripts();   // OMNI_ADDONS_V1: add-on scripts survive RemoveAllUserScripts (defined below)
void pagesReaddBridge();     // s3 OMNI_PAGES_V1: the built-in pages bridge survives it too (defined below)
WKRetainPtr<WKUserContentExtensionStoreRef> store;
WKRetainPtr<WKUserContentFilterRef> filter;
bool enabled = false;
bool nativeReady = false;
bool nativeFailed = false;
void (*completion)(bool) = nullptr;

// ---- uBlock content filtering -------------------------------------------
constexpr const char* allowlistPath = "/data/omni/ublock-allowlist.txt";
constexpr const char* contentDir = "/data/omni/ubo-content/";
std::vector<WKRetainPtr<WKUserScriptRef>> shellScripts;
bool contentActive = false;
std::vector<std::string> trustedSites;

bool validHost(const std::string& host)
{
    if (host.empty() || host.size() > 253) return false;
    return std::all_of(host.begin(), host.end(), [](char c) { return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-'; });
}
void loadTrustedSites()
{
    trustedSites.clear();
    FILE* file = fopen(allowlistPath, "r");
    if (!file) return;
    char line[300];
    while (fgets(line, sizeof(line), file)) {
        std::string host(line);
        if (host.empty() || (host.back() != '\n' && !feof(file))) {
            // Overlong line: skip the rest of it instead of reading the tail as a host.
            int ch; while ((ch = fgetc(file)) != EOF && ch != '\n') { }
            continue;
        }
        while (!host.empty() && (host.back() == '\n' || host.back() == '\r' || host.back() == ' ')) host.pop_back();
        if (validHost(host) && std::find(trustedSites.begin(), trustedSites.end(), host) == trustedSites.end()) trustedSites.push_back(host);
    }
    fclose(file);
}
bool saveTrustedSites()
{
    std::string temporary = std::string(allowlistPath) + ".new";
    FILE* file = fopen(temporary.c_str(), "w");
    if (!file) return false;
    for (auto& host : trustedSites) fprintf(file, "%s\n", host.c_str());
    bool ok = !ferror(file);
    ok = !fclose(file) && ok;
    return ok && !rename(temporary.c_str(), allowlistPath);
}
std::string readContent(const char* name)
{
    std::string result;
    FILE* file = fopen((std::string(contentDir) + name).c_str(), "rb");
    if (!file) return result;
    char chunk[16384]; size_t count;
    while ((count = fread(chunk, 1, sizeof(chunk), file)) && result.size() <= 6 * 1024 * 1024) result.append(chunk, count);
    bool valid = !ferror(file) && result.size() <= 6 * 1024 * 1024;
    fclose(file);
    if (!valid) result.clear();
    return result;
}
// ---- OMNI_UBO_SITE_V1: per-site rules -------------------------------------
// OMNI_PERF_D_W1: on by default (the 5.4 MB bundle is not registered); /data/omni/ubo-site-rules-disabled.flag
// turns it off. The old opt-in flag /data/omni/ubo-site-rules.flag is still accepted and changes nothing.
// If site-index.txt or always-*.js are missing or invalid, the full bundle is used. Instead of the bundle:
//   always-main.js     page world, document start, every frame: generic ("*") scriptlets (~20 KB)
//   always-generic.js  isolated world, document end, every frame: generic cosmetic filtering
//   per frame host     built from site-index.txt by OmniUBlockSite::Index when a navigation to that
//                      host is about to be allowed (decidePolicyForNavigationAction/Response), and
//                      registered with the allowlist *://host/*: WebKit itself picks, per frame, the
//                      scripts whose pattern matches (document start, before any page script).
// Network blocking is untouched. With the disabled flag nothing here runs.
constexpr const char* siteDir = "/data/omni/ubo-site/";
bool siteRulesOn() { return access("/data/omni/ubo-site-rules-disabled.flag", F_OK) != 0; } // OMNI_PERF_D_W1
bool siteActive = false;
bool siteTopOnly = false;
bool sitePageWorld = false;
bool siteIndexTried = false;
bool siteUnavailable = false; // OMNI_C52_FIX1: index or always-*.js unusable: index freed, hooks not installed
bool siteDebug = false;       // OMNI_C52_FIX1: /data/omni/ubo-site-debug.flag: one counter line per build (no host)
unsigned long long siteBuilds = 0;
OmniUBlockSite::Index siteIndex;
std::string siteAllow = "[]";
struct SiteEntry {
    std::vector<std::string> tops;
    WKRetainPtr<WKUserScriptRef> main, isolated;
    size_t mainHash = 0, isolatedHash = 0;
    unsigned long long used = 0;
};
std::unordered_map<std::string, SiteEntry> siteHosts;
unsigned long long siteClock = 0;
constexpr size_t siteMaxRegistered = 48; // hosts with scripts on the controller (each frame checks every pattern)
constexpr size_t siteMaxKnown = 512;     // remembered hosts, including hosts without rules
constexpr size_t siteMaxTops = 8;
struct SiteRegex { bool tried = false; JSGlobalContextRef context = nullptr; JSObjectRef tester = nullptr; std::vector<JSObjectRef> rules; } siteRegex;

std::string readFileLimited(const std::string& path, size_t limit)
{
    std::string result;
    FILE* file = fopen(path.c_str(), "rb");
    if (!file) return result;
    char chunk[16384]; size_t count;
    while ((count = fread(chunk, 1, sizeof(chunk), file)) && result.size() <= limit) result.append(chunk, count);
    bool valid = !ferror(file) && result.size() <= limit;
    fclose(file);
    if (!valid) result.clear();
    return result;
}
JSValueRef siteEvaluate(JSGlobalContextRef context, const char* source)
{
    auto script = JSStringCreateWithUTF8CString(source);
    JSValueRef exception = nullptr;
    auto result = JSEvaluateScript(context, script, nullptr, nullptr, 1, &exception);
    JSStringRelease(script);
    return exception ? nullptr : result;
}
// The few hostname rules written as regular expressions (10 upstream) use JavaScript's RegExp, as
// uBO does: one small JavaScriptCore context in this process, created the first time it is needed.
bool siteRegexTest(void*, size_t rule, const std::string& text)
{
    if (!siteRegex.tried) {
        siteRegex.tried = true;
        siteRegex.context = JSGlobalContextCreate(nullptr);
        if (!siteRegex.context) return false;
        auto compiler = siteEvaluate(siteRegex.context, "(function (s) { try { return new RegExp(s); } catch (e) { return null; } })");
        auto tester = siteEvaluate(siteRegex.context, "(function (r, t) { return r !== null && r.test(t); })");
        if (!compiler || !tester || !JSValueIsObject(siteRegex.context, compiler) || !JSValueIsObject(siteRegex.context, tester)) return false;
        siteRegex.tester = JSValueToObject(siteRegex.context, tester, nullptr);
        JSValueProtect(siteRegex.context, siteRegex.tester);
        auto compile = JSValueToObject(siteRegex.context, compiler, nullptr);
        for (size_t i = 0; i < siteIndex.regexCount(); ++i) {
            auto source = JSStringCreateWithUTF8CString(siteIndex.regexSource(i).c_str());
            JSValueRef args[] = { JSValueMakeString(siteRegex.context, source) };
            JSStringRelease(source);
            JSValueRef exception = nullptr;
            auto value = JSObjectCallAsFunction(siteRegex.context, compile, nullptr, 1, args, &exception);
            JSObjectRef object = !exception && value && JSValueIsObject(siteRegex.context, value) ? JSValueToObject(siteRegex.context, value, nullptr) : nullptr;
            if (object) JSValueProtect(siteRegex.context, object);
            siteRegex.rules.push_back(object);
        }
    }
    if (!siteRegex.tester || rule >= siteRegex.rules.size() || !siteRegex.rules[rule]) return false;
    auto string = JSStringCreateWithUTF8CString(text.c_str());
    JSValueRef args[] = { siteRegex.rules[rule], JSValueMakeString(siteRegex.context, string) };
    JSStringRelease(string);
    JSValueRef exception = nullptr;
    auto result = JSObjectCallAsFunction(siteRegex.context, siteRegex.tester, nullptr, 2, args, &exception);
    return !exception && result && JSValueToBoolean(siteRegex.context, result);
}
// host empty: every frame. Otherwise only frames whose URL (or, for about:/blob:/data: frames, the
// parent document's URL) is http(s)://host/...
WKRetainPtr<WKUserScriptRef> siteScript(const std::string& source, bool documentStart, bool isolated, bool topOnly, const std::string& host)
{
    auto text = adoptWK(WKStringCreateWithUTF8CString(source.c_str()));
    WTF::Vector<WTF::String> allow;
    if (!host.empty()) {
        auto pattern = adoptWK(WKStringCreateWithUTF8CString(("*://" + host + "/*").c_str()));
        allow.append(WebKit::toWTFString(pattern.get()));
    }
    WTF::Ref<API::ContentWorld> world = isolated && !sitePageWorld
        ? API::ContentWorld::sharedWorldWithName(WTF::String::fromLatin1("omni-ublock"))
        : WTF::Ref<API::ContentWorld>(API::ContentWorld::pageContentWorldSingleton());
    WebCore::UserScript script { WebKit::toWTFString(text.get()), { }, WTF::move(allow), { },
        documentStart ? WebCore::UserScriptInjectionTime::DocumentStart : WebCore::UserScriptInjectionTime::DocumentEnd,
        topOnly ? WebCore::UserContentInjectedFrames::InjectInTopFrameOnly : WebCore::UserContentInjectedFrames::InjectInAllFrames,
        WebCore::UserContentMatchParentFrame::ForOpaqueOrigins };
    return adoptWK(WebKit::toAPILeakingRef(API::UserScript::create(WTF::move(script), world.get())));
}
void siteUnregister(SiteEntry& entry)
{
    auto* proxy = WebKit::toImpl(controller.get());
    if (entry.main) proxy->removeUserScript(*WebKit::toImpl(entry.main.get()));
    if (entry.isolated) proxy->removeUserScript(*WebKit::toImpl(entry.isolated.get()));
    if (privateController) {   // OMNI_ADDONS_V1: mirrored
        auto* mirror = WebKit::toImpl(privateController.get());
        if (entry.main) mirror->removeUserScript(*WebKit::toImpl(entry.main.get()));
        if (entry.isolated) mirror->removeUserScript(*WebKit::toImpl(entry.isolated.get()));
    }
    entry.main = nullptr; entry.isolated = nullptr; entry.mainHash = entry.isolatedHash = 0;
}
std::string siteHostOf(const std::string& url)
{
    size_t begin;
    if (url.rfind("https://", 0) == 0) begin = 8;
    else if (url.rfind("http://", 0) == 0) begin = 7;
    else return { };
    auto end = url.find_first_of("/?#", begin);
    std::string authority = url.substr(begin, end == std::string::npos ? std::string::npos : end - begin);
    if (auto at = authority.rfind('@'); at != std::string::npos) authority = authority.substr(at + 1);
    if (authority.empty() || authority[0] == '[') return { };
    if (auto colon = authority.find(':'); colon != std::string::npos) authority.resize(colon);
    std::transform(authority.begin(), authority.end(), authority.begin(), [](unsigned char c) { return std::tolower(c); });
    while (!authority.empty() && authority.back() == '.') authority.pop_back();
    return validHost(authority) ? authority : std::string { };
}
// OMNI_PERF_D_IDX: the 3.7 MB index (45-48 ms on the console) and the two always-*.js files are read on a
// worker thread started by omniBlockerInitialize(), while the content rules compile; the UI thread only
// joins it when the rules are installed (usually already finished). Plain C++, no WebKit on the worker.
struct SitePreload {
    pthread_t thread { };
    bool started = false;
    bool ok = false;
    double ms = 0;
    OmniUBlockSite::Index index;
    std::string error, always, generic;
} sitePreload;
void* sitePreloadMain(void*)
{
    auto t0 = std::chrono::steady_clock::now();
    sitePreload.ok = sitePreload.index.load((std::string(siteDir) + "site-index.txt").c_str(), sitePreload.error);
    if (sitePreload.ok) {
        sitePreload.always = readFileLimited(std::string(siteDir) + "always-main.js", 2 * 1024 * 1024);
        sitePreload.generic = readFileLimited(std::string(siteDir) + "always-generic.js", 4 * 1024 * 1024);
    } else
        sitePreload.index = OmniUBlockSite::Index();
    sitePreload.ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    return nullptr;
}
void sitePreloadStart()
{
    if (sitePreload.started || siteIndexTried || !siteRulesOn() || access("/data/omni/ublock-native.flag", F_OK) || !access("/data/omni/ubo-content-disabled.flag", F_OK))
        return;
    pthread_attr_t attr;
    if (pthread_attr_init(&attr)) return;
    pthread_attr_setstacksize(&attr, 512 * 1024);
    sitePreload.started = !pthread_create(&sitePreload.thread, &attr, sitePreloadMain, nullptr);
    pthread_attr_destroy(&attr);
}
bool installSiteScripts(const std::string& allow, bool topOnly, bool pageWorld)
{
    sitePageWorld = pageWorld;
    siteTopOnly = topOnly;
    std::string always, generic;
    bool havePreloaded = false;
    if (!siteIndexTried) {
        siteIndexTried = true;
        auto t0 = std::chrono::steady_clock::now();
        std::string error;
        siteDebug = !access("/data/omni/ubo-site-debug.flag", F_OK);
        bool ok;
        double loadMs;
        const char* how = "";
        if (sitePreload.started) { // OMNI_PERF_D_IDX
            pthread_join(sitePreload.thread, nullptr);
            sitePreload.started = false;
            ok = sitePreload.ok;
            error = sitePreload.error;
            loadMs = sitePreload.ms;
            if (ok) {
                siteIndex = std::move(sitePreload.index);
                always = std::move(sitePreload.always);
                generic = std::move(sitePreload.generic);
                havePreloaded = true;
            }
            sitePreload.index = OmniUBlockSite::Index();
            how = " on a worker";
        } else {
            ok = siteIndex.load((std::string(siteDir) + "site-index.txt").c_str(), error);
            loadMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        }
        if (!ok) {
            fprintf(stderr, "browser: uBlock site rules unavailable (site-index.txt: %s); using the full bundle\n", error.c_str());
            siteIndex = OmniUBlockSite::Index(); // OMNI_C52_FIX1: a failed load can hold up to 32 MB
            siteUnavailable = true;
        } else
            fprintf(stderr, "browser: uBlock site rules index loaded: %zu keys, %zu bytes in %.1f ms%s (UI thread %.1f ms)\n", siteIndex.keyCount(), siteIndex.bytes(),
                loadMs, how, std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count());
    }
    if (!siteIndex.loaded()) return false;
    const std::string marker = "/*OMNI_ALLOWLIST*/[]";
    if (!havePreloaded) {
        always = readFileLimited(std::string(siteDir) + "always-main.js", 2 * 1024 * 1024);
        generic = readFileLimited(std::string(siteDir) + "always-generic.js", 4 * 1024 * 1024);
    }
    auto a = always.find(marker), g = generic.find(marker);
    if (a == std::string::npos || g == std::string::npos) {
        fprintf(stderr, "browser: uBlock site rules: always-main.js/always-generic.js missing or invalid; using the full bundle\n");
        siteIndex = OmniUBlockSite::Index(); // OMNI_C52_FIX1: release the unused index (~3.7 MB); not retried until restart
        siteUnavailable = true;
        return false;
    }
    always.replace(a, marker.size(), allow);
    generic.replace(g, marker.size(), allow);
    const bool genericTopOnly = topOnly || !access("/data/omni/ubo-site-generic-top-only.flag", F_OK);
    auto first = siteScript(always, true, false, topOnly, { });
    auto second = siteScript(generic, false, true, genericTopOnly, { });
    ucAddScript(first.get());
    ucAddScript(second.get());
    siteAllow = allow;
    siteActive = true;
    contentActive = true;
    fprintf(stderr, "browser: uBlock content filtering active: per-site rules (OMNI_UBO_SITE_V1; generic %zu + %zu bytes per frame%s; %zu trusted sites; %s world%s)\n",
        always.size(), generic.size(), genericTopOnly && !topOnly ? ", generic cosmetic top frame only" : "", trustedSites.size(), pageWorld ? "page" : "isolated", topOnly ? "; top frame only" : "");
    return true;
}

void installContentScripts()
{
    ucRemoveAllScripts();   // OMNI_ADDONS_V1: both controllers
    for (auto& script : shellScripts) ucAddScript(script.get());
    addonsReaddScripts();   // OMNI_ADDONS_V1
    pagesReaddBridge();     // s3 OMNI_PAGES_V1
    contentActive = false;
    siteActive = false;  // OMNI_UBO_SITE_V1: per-site scripts went with RemoveAllUserScripts
    siteHosts.clear();
    if (!enabled || access("/data/omni/ublock-native.flag", F_OK) || !access("/data/omni/ubo-content-disabled.flag", F_OK)) return;
    std::string allow = "[";
    for (size_t i = 0; i < trustedSites.size(); ++i) allow += (i ? ",\"" : "\"") + trustedSites[i] + "\"";
    allow += "]";
    struct Part { const char* file; _WKUserScriptInjectionTime time; bool isolated; };
    const Part parts[] = {
        { "main-start.js", kWKInjectAtDocumentStart, false },
        { "isolated-start.js", kWKInjectAtDocumentStart, true },
        { "isolated-end.js", kWKInjectAtDocumentEnd, true },
    };
    bool pageWorldOnly = !access("/data/omni/ubo-content-pageworld.flag", F_OK);
    // OMNI_UBO_MAINFRAME_V1: the content bundle (~5.4 MB of JavaScript, run by the interpreter: no JIT on the console) was
    // injected into every frame, ad and embed iframes included. With /data/omni/ubo-content-mainframe-only.flag only the
    // top document gets cosmetic filtering and scriptlets; network blocking still covers every frame.
    const bool mainFrameOnly = !access("/data/omni/ubo-content-mainframe-only.flag", F_OK);
    if (siteRulesOn() && installSiteScripts(allow, mainFrameOnly, pageWorldOnly)) return; // OMNI_UBO_SITE_V1, default since OMNI_PERF_D_W1
    auto world = adoptWK(WKStringCreateWithUTF8CString("omni-ublock"));
    std::vector<WKRetainPtr<WKUserScriptRef>> scripts;
    for (auto& part : parts) {
        std::string source = readContent(part.file);
        const std::string marker = "/*OMNI_ALLOWLIST*/[]";
        auto position = source.find(marker);
        if (source.empty() || position == std::string::npos) {
            fprintf(stderr, "browser: uBlock content bundle missing or invalid: %s\n", part.file);
            return;
        }
        source.replace(position, marker.size(), allow);
        auto text = adoptWK(WKStringCreateWithUTF8CString(source.c_str()));
        scripts.push_back(part.isolated && !pageWorldOnly
            ? adoptWK(WKUserScriptCreateWithSourceInWorldOmni(text.get(), part.time, mainFrameOnly, world.get()))
            : adoptWK(WKUserScriptCreateWithSource(text.get(), part.time, mainFrameOnly)));
    }
    for (auto& script : scripts) ucAddScript(script.get());
    contentActive = true;
    fprintf(stderr, "browser: uBlock content filtering active (scriptlets, cosmetic filters; %zu trusted sites; %s world%s)\n",
        trustedSites.size(), pageWorldOnly ? "page" : "isolated", mainFrameOnly ? "; top frame only" : "");
}
}

bool omniBlockerContentActive() { return contentActive; }
// OMNI_UBO_SITE_V1
bool omniBlockerSiteRulesWanted() { return !siteUnavailable && siteRulesOn(); } // OMNI_PERF_D_W1: default on
bool omniBlockerSiteActive() { return siteActive; } // OMNI_C52_FIX1
void omniBlockerPrepareSite(const std::string& url, const std::string& topURL, bool subframe, bool privateTab)
{
    if (!siteActive) return;
    const std::string host = siteHostOf(url);
    if (host.empty()) return;
    const std::string top = subframe ? siteHostOf(topURL) : std::string();
    auto found = siteHosts.find(host);
    const bool fresh = found == siteHosts.end();
    if (fresh && siteHosts.size() >= siteMaxKnown) {
        // Forget the least recently used host (its scripts, if any, leave the controller).
        auto oldest = siteHosts.end();
        for (auto it = siteHosts.begin(); it != siteHosts.end(); ++it) if (oldest == siteHosts.end() || it->second.used < oldest->second.used) oldest = it;
        if (oldest != siteHosts.end()) { siteUnregister(oldest->second); siteHosts.erase(oldest); }
    }
    SiteEntry& entry = siteHosts[host];
    entry.used = ++siteClock;
    const bool newTop = !top.empty() && std::find(entry.tops.begin(), entry.tops.end(), top) == entry.tops.end() && entry.tops.size() < siteMaxTops;
    if (!fresh && !newTop) return;
    if (newTop) entry.tops.push_back(top);
    auto t0 = std::chrono::steady_clock::now();
    auto built = siteIndex.build(host, entry.tops, siteAllow, siteRegexTest, nullptr);
    const size_t mainHash = built.main.empty() ? 0 : std::hash<std::string>()(built.main) | 1;
    const size_t isolatedHash = built.isolated.empty() ? 0 : std::hash<std::string>()(built.isolated) | 1;
    if (mainHash == entry.mainHash && isolatedHash == entry.isolatedHash) return; // nothing new (often: no rules)
    siteUnregister(entry);
    if (mainHash) { entry.main = siteScript(built.main, true, false, siteTopOnly, host); ucAddScript(entry.main.get()); }
    if (isolatedHash) { entry.isolated = siteScript(built.isolated, true, true, siteTopOnly, host); ucAddScript(entry.isolated.get()); }
    entry.mainHash = mainHash; entry.isolatedHash = isolatedHash;
    // OMNI_C52_FIX1: no host or URL is ever logged here (browsing history on /data). With the debug flag,
    // one counter line per build for non-private tabs; never for private tabs.
    ++siteBuilds;
    if (siteDebug && !privateTab)
        fprintf(stderr, "browser: uBlock site rules build %llu: page %zu B, isolated %zu B (%zu scriptlets, %zu css, %zu procedural%s%s) %.2f ms; %zu hosts known\n",
            siteBuilds, built.main.size(), built.isolated.size(), built.scriptletCalls, built.cssSelectors,
            built.proceduralSelectors, built.genericOff ? ", generic off" : "", built.genericExceptions ? ", generic exceptions" : "",
            std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count(), siteHosts.size());
    // Keep the number of patterns every frame checks small: drop the least recently used hosts' scripts.
    size_t registered = 0;
    for (auto& item : siteHosts) if (item.second.main || item.second.isolated) ++registered;
    while (registered > siteMaxRegistered) {
        auto oldest = siteHosts.end();
        for (auto it = siteHosts.begin(); it != siteHosts.end(); ++it)
            if ((it->second.main || it->second.isolated) && it->first != host && (oldest == siteHosts.end() || it->second.used < oldest->second.used)) oldest = it;
        if (oldest == siteHosts.end()) break;
        siteUnregister(oldest->second);
        siteHosts.erase(oldest); // rebuilt on its next navigation
        --registered;
    }
}
void omniBlockerAddShellScript(WKUserScriptRef script)
{
    shellScripts.emplace_back(script);
    ucAddScript(script);
}
std::string omniBlockerHostOf(const std::string& url)
{
    auto scheme = url.find("://");
    if (scheme == std::string::npos) return { };
    auto begin = scheme + 3;
    auto end = url.find_first_of("/?#", begin);
    std::string authority = url.substr(begin, end == std::string::npos ? std::string::npos : end - begin);
    if (auto at = authority.rfind('@'); at != std::string::npos) authority = authority.substr(at + 1);
    if (!authority.empty() && authority[0] == '[') return { };
    if (auto colon = authority.find(':'); colon != std::string::npos) authority.resize(colon);
    std::transform(authority.begin(), authority.end(), authority.begin(), [](unsigned char c) { return std::tolower(c); });
    while (!authority.empty() && authority.back() == '.') authority.pop_back();
    if (authority.rfind("www.", 0) == 0 && authority.find('.', 4) != std::string::npos) authority = authority.substr(4);
    return validHost(authority) ? authority : std::string { };
}
bool omniBlockerSiteTrusted(const std::string& host)
{
    if (host.empty()) return false;
    for (auto& entry : trustedSites)
        if (host == entry || (host.size() > entry.size() && host.compare(host.size() - entry.size(), entry.size(), entry) == 0 && host[host.size() - entry.size() - 1] == '.'))
            return true;
    return false;
}
bool omniBlockerSetSiteTrusted(const std::string& host, bool trusted)
{
    if (!validHost(host)) return false;
    auto previous = trustedSites;
    trustedSites.erase(std::remove_if(trustedSites.begin(), trustedSites.end(), [&](const std::string& entry) {
        return entry == host || (host.size() > entry.size() && host.compare(host.size() - entry.size(), entry.size(), entry) == 0 && host[host.size() - entry.size() - 1] == '.');
    }), trustedSites.end());
    if (trusted) trustedSites.push_back(host);
    if (!saveTrustedSites()) { trustedSites = previous; return false; }
    installContentScripts();
    return true;
}

// ---- OMNI_ADDONS_V1: add-on scripts, style sheets and message handlers (OmniAddons.h decides what) ----------
namespace {
struct AddonItem {
    std::string id;
    RefPtr<API::UserScript> script;
    RefPtr<API::UserStyleSheet> sheet;
    bool privateToo = false;
};
std::vector<AddonItem> addonItems;
std::vector<std::string> addonHandlerIds;
OmniAddonMessageFn addonMessageFn = nullptr;
WTF::String addonString(const std::string& s)
{
    auto text = adoptWK(WKStringCreateWithUTF8CString(s.c_str()));
    return WebKit::toWTFString(text.get());
}
WTF::Vector<WTF::String> addonList(const std::vector<std::string>& list)
{
    WTF::Vector<WTF::String> result;
    for (auto& item : list) result.append(addonString(item));
    return result;
}
WTF::Ref<API::ContentWorld> addonWorld(const std::string& id) { return API::ContentWorld::sharedWorldWithName(addonString("omni-addon-" + id)); }
void addonAddTo(WKUserContentControllerRef target, API::UserScript& script, bool now)
{
#ifdef OMNI_ADDONS_INJECT_NOW
    WebKit::toImpl(target)->addUserScript(script, now ? WebKit::InjectUserScriptImmediately::Yes : WebKit::InjectUserScriptImmediately::No);
#else
    (void)now;
    WKUserContentControllerAddUserScript(target, WebKit::toAPI(&script));
#endif
}
void addonsReaddScripts()
{
    for (auto& item : addonItems) {
        if (!item.script) continue;
        addonAddTo(controller.get(), *item.script, false);
        if (item.privateToo && privateController) addonAddTo(privateController.get(), *item.script, false);
    }
}
// webkit.messageHandlers.omniAddon, only in the add-on's own world: page scripts and other add-ons cannot post here.
class AddonMessageClient final : public WebKit::WebScriptMessageHandler::Client {
public:
    explicit AddonMessageClient(std::string id) : m_id(std::move(id)) { }
private:
    void didPostMessage(WebKit::WebPageProxy& page, WebKit::FrameInfoData&&, API::ContentWorld&, WebKit::JavaScriptEvaluationResult&& result,
        WTF::CompletionHandler<void(std::expected<WebKit::JavaScriptEvaluationResult, WTF::String>&&)>&& completion) override
    {
        std::string reply = "error: add-ons are not ready";
        if (addonMessageFn) {
            auto body = result.toString().utf8();
            reply = addonMessageFn(m_id, WebKit::toAPI(&page), std::string(reinterpret_cast<const char*>(body.data()), body.length()));   // CString::data(): const char8_t*
        }
        Ref<API::String> text = API::String::create(addonString(reply));
        if (auto value = WebKit::JavaScriptEvaluationResult::extract(text.ptr())) completion(WTF::move(*value));
        else completion(std::unexpected<WTF::String>(WTF::String()));
    }
    std::string m_id;
};
}
WKUserContentControllerRef omniBlockerPrivateController() { return privateController ? privateController.get() : controller.get(); }
void omniAddonsSetMessageHandler(OmniAddonMessageFn fn) { addonMessageFn = fn; }
bool omniAddonsAddScript(const std::string& id, const std::string& source, const std::vector<std::string>& allow, const std::vector<std::string>& block,
    bool documentStart, bool allFrames, bool privateToo, bool injectNow)
{
    if (!controller) return false;
    WebCore::UserScript script { addonString(source), { }, addonList(allow), addonList(block),
        documentStart ? WebCore::UserScriptInjectionTime::DocumentStart : WebCore::UserScriptInjectionTime::DocumentEnd,
        allFrames ? WebCore::UserContentInjectedFrames::InjectInAllFrames : WebCore::UserContentInjectedFrames::InjectInTopFrameOnly,
        WebCore::UserContentMatchParentFrame::ForOpaqueOrigins };
    auto world = addonWorld(id);
    Ref<API::UserScript> userScript = API::UserScript::create(WTF::move(script), world.get());
    addonAddTo(controller.get(), userScript.get(), injectNow);
    if (privateToo && privateController) addonAddTo(privateController.get(), userScript.get(), injectNow);
    addonItems.push_back({ id, userScript.ptr(), nullptr, privateToo });
    return true;
}
bool omniAddonsAddStyleSheet(const std::string& id, const std::string& css, const std::vector<std::string>& allow, const std::vector<std::string>& block,
    bool allFrames, bool authorLevel, bool privateToo)
{
    if (!controller) return false;
    WebCore::UserStyleSheet sheet { addonString(css), WTF::URL { }, addonList(allow), addonList(block),
        allFrames ? WebCore::UserContentInjectedFrames::InjectInAllFrames : WebCore::UserContentInjectedFrames::InjectInTopFrameOnly,
        WebCore::UserContentMatchParentFrame::ForOpaqueOrigins, authorLevel ? WebCore::UserStyleLevel::Author : WebCore::UserStyleLevel::User };
    auto world = addonWorld(id);
    Ref<API::UserStyleSheet> userSheet = API::UserStyleSheet::create(WTF::move(sheet), world.get());
    WebKit::toImpl(controller.get())->addUserStyleSheet(userSheet.get());
    if (privateToo && privateController) WebKit::toImpl(privateController.get())->addUserStyleSheet(userSheet.get());
    addonItems.push_back({ id, nullptr, userSheet.ptr(), privateToo });
    return true;
}
void omniAddonsRemove(const std::string& id)
{
    for (auto it = addonItems.begin(); it != addonItems.end();) {
        if (it->id != id) { ++it; continue; }
        auto* main = WebKit::toImpl(controller.get());
        if (it->script) main->removeUserScript(*it->script);
        if (it->sheet) main->removeUserStyleSheet(*it->sheet);
        if (it->privateToo && privateController) {
            auto* mirror = WebKit::toImpl(privateController.get());
            if (it->script) mirror->removeUserScript(*it->script);
            if (it->sheet) mirror->removeUserStyleSheet(*it->sheet);
        }
        it = addonItems.erase(it);
    }
}
bool omniAddonsAddMessageHandler(const std::string& id)
{
    if (!controller) return false;
    if (std::find(addonHandlerIds.begin(), addonHandlerIds.end(), id) != addonHandlerIds.end()) return true;
    auto world = addonWorld(id);
    for (WKUserContentControllerRef target : { controller.get(), privateController.get() }) {
        if (!target) continue;
        auto handler = WebKit::WebScriptMessageHandler::create(std::make_unique<AddonMessageClient>(id), WTF::String::fromLatin1("omniAddon"), world.get());
        WebKit::toImpl(target)->addUserScriptMessageHandler(handler.get());
    }
    addonHandlerIds.push_back(id);
    return true;
}

WKUserContentControllerRef omniBlockerController() { return controller.get(); }
bool omniBlockerEnabled() { return enabled; }
bool omniBlockerUsesUBlock() { return nativeReady; }
bool omniBlockerFailed() { return enabled && nativeFailed; }
void omniBlockerPoll() {
    nativeFailed = !access("/data/omni/ublock-error.flag", F_OK);
    if (nativeFailed) { nativeReady = false; return; }
    if (!nativeReady && !access("/data/omni/ublock-native.flag", F_OK) && !access("/data/omni/ublock-ready.flag", F_OK)) {
        nativeReady = true;
        ucRemoveAllFilters();   // OMNI_ADDONS_V1
        fprintf(stderr, "browser: upstream uBlock network engine active; legacy host filter removed\n");
    }
}
bool omniBlockerSetEnabled(bool value)
{
    if (!filter && !nativeReady) return false;
    if (!access("/data/omni/ublock-native.flag", F_OK)) {
        if (value) {
            if (unlink("/data/omni/ublock-disabled.flag") && errno != ENOENT) return false;
        }
        else {
            FILE* flag = fopen("/data/omni/ublock-disabled.flag", "w");
            if (!flag) return false;
            fclose(flag);
        }
    }
    ucRemoveAllFilters();   // OMNI_ADDONS_V1
    if (value && !nativeReady) ucAddFilter(filter.get());
    enabled = value;
    installContentScripts();
    return true;
}

void omniBlockerInitialize(bool testing, void (*ready)(bool))
{
    controller = adoptWK(WKUserContentControllerCreate());
    privateController = adoptWK(WKUserContentControllerCreate());   // OMNI_ADDONS_V1
    loadTrustedSites();
    sitePreloadStart(); // OMNI_PERF_D_IDX
    unlink("/data/omni/ublock-ready.flag");
    unlink("/data/omni/ublock-error.flag");
    unlink("/data/omni/ublock-disabled.flag");
    completion = ready;
    FILE* file = fopen("/data/omni/content-blocker.json", "rb");
    std::string source;
    if (file) {
        char chunk[4096];
        size_t count;
        while ((count = fread(chunk, 1, sizeof(chunk), file)) && source.size() <= 2 * 1024 * 1024)
            source.append(chunk, count);
        bool valid = !ferror(file) && source.size() <= 2 * 1024 * 1024;
        fclose(file);
        if (!valid) source.clear();
    }
    if (source.empty()) { ready(false); return; }
    if (testing) {
        size_t end = source.find_last_of(']');
        if (end == std::string::npos) { ready(false); return; }
        source.insert(end, R"(,{"trigger":{"url-filter":"/omni/blocker-test/blocked[.]js"},"action":{"type":"block"}})");
    }
    mkdir("/data/omni/content-rules", 0777);
    mkdir("/data/omni/content-rules/tmp", 0777);
    setenv("TMPDIR", "/data/omni/content-rules/tmp", 1);
    store = adoptWK(WKUserContentExtensionStoreCreate(adoptWK(WKStringCreateWithUTF8CString("/data/omni/content-rules")).get()));
    if (!store) { ready(false); return; }
    auto identifier = adoptWK(WKStringCreateWithUTF8CString(testing ? "omni-hosts-test-v1" : "omni-hosts-v1"));
    auto json = adoptWK(WKStringCreateWithUTF8CString(source.c_str()));
    WKUserContentExtensionStoreCompile(store.get(), identifier.get(), json.get(), nullptr,
        [](WKUserContentFilterRef result, WKUserContentExtensionStoreResult code, void*) {
            filter = adoptWK(result);
            bool ok = code == kWKUserContentExtensionStoreSuccess && filter;
            if (ok) omniBlockerSetEnabled(true);
            fprintf(stderr, "browser: content blocker compile result=%u enabled=%d\n", code, enabled);
            fflush(stderr);
            completion(ok);
        });
}

// ---- s3 OMNI_PAGES_V1: omni://pages/<path> ------------------------------------------------------------------------
// Files come from one read-only root (the title's /app0/pages, or the developer override the shell picks). The shell's
// allow function decides every load: a built-in page may load its own files and other built-in pages; a main-frame load
// from anything else is allowed only for an address Omni itself opened in that tab. Web content can't frame or fetch
// these pages. Every response carries ENGINE-CONTRACT §1's Content-Security-Policy.
namespace {
std::string pagesRoot;
OmniPagesAllowFn pagesAllow = nullptr;
OmniPagesMessageFn pagesMessage = nullptr;
RefPtr<API::UserScript> pagesBridge;
bool pagesHandlerAdded = false;
const char* const pagesCSP = "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; worker-src 'self'; "
    "connect-src 'self'; media-src 'self' blob:; frame-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'; object-src 'none'";
std::string pagesStd(const WTF::String& s)
{
    auto u = s.utf8();
    return std::string(reinterpret_cast<const char*>(u.data()), u.length());   // CString::data(): const char8_t*
}
const char* pagesMime(const std::string& path)
{
    const size_t dot = path.rfind('.');
    const std::string ext = dot == std::string::npos ? std::string() : path.substr(dot + 1);
    static const std::pair<const char*, const char*> table[] = {
        { "html", "text/html" }, { "htm", "text/html" }, { "js", "text/javascript" }, { "mjs", "text/javascript" }, { "css", "text/css" },
        { "json", "application/json" }, { "svg", "image/svg+xml" }, { "png", "image/png" }, { "jpg", "image/jpeg" }, { "jpeg", "image/jpeg" },
        { "webp", "image/webp" }, { "gif", "image/gif" }, { "ico", "image/x-icon" }, { "woff2", "font/woff2" }, { "woff", "font/woff" },
        { "ttf", "font/ttf" }, { "otf", "font/otf" }, { "txt", "text/plain" }, { "md", "text/plain" }, { "vtt", "text/vtt" }, { "srt", "text/plain" },
        { "ogg", "audio/ogg" }, { "mp3", "audio/mpeg" }, { "wav", "audio/wav" }, { "mp4", "video/mp4" }, { "webm", "video/webm" },
        { "pdf", "application/pdf" }, { "wasm", "application/wasm" }, { "map", "application/json" },
    };
    for (auto& e : table) if (ext == e.first) return e.second;
    return "application/octet-stream";
}
bool pagesTextMime(const char* mime)
{
    const std::string m = mime;
    return m.rfind("text/", 0) == 0 || m == "application/json" || m == "image/svg+xml";
}
// "omni://pages/a/b.html?x#y" -> "a/b.html" ("" = refused). No "..", no backslashes, no NUL, no hidden files; a
// directory (empty or trailing "/") means its index.html.
std::string pagesRelPath(const std::string& url)
{
    static const std::string base = "omni://pages/";
    if (url.compare(0, base.size(), base)) return std::string();
    std::string path = url.substr(base.size());
    path = path.substr(0, path.find_first_of("?#"));
    std::string decoded;
    for (size_t i = 0; i < path.size(); ++i) {
        if (path[i] == '%' && i + 2 < path.size() && isxdigit((unsigned char)path[i + 1]) && isxdigit((unsigned char)path[i + 2])) {
            decoded += char(strtol(path.substr(i + 1, 2).c_str(), nullptr, 16)); i += 2;
        } else decoded += path[i];
    }
    if (decoded.empty() || decoded.back() == '/') decoded += "index.html";
    if (decoded.size() > 512 || decoded.find('\\') != std::string::npos || decoded.find('\0') != std::string::npos || decoded[0] == '/') return std::string();
    size_t start = 0;
    while (start <= decoded.size()) {
        const size_t end = decoded.find('/', start);
        const std::string seg = decoded.substr(start, end == std::string::npos ? std::string::npos : end - start);
        if (seg.empty() || seg == "." || seg == ".." || seg[0] == '.') return std::string();
        if (end == std::string::npos) break;
        start = end + 1;
    }
    return decoded;
}
class PagesSchemeHandler final : public WebKit::WebURLSchemeHandler {
public:
    static Ref<PagesSchemeHandler> create() { return adoptRef(*new PagesSchemeHandler); }
private:
    PagesSchemeHandler() = default;
    void platformStartTask(WebKit::WebPageProxy& page, WebKit::WebURLSchemeTask& task) final
    {
        const WTF::URL wurl = task.request().url();
        const std::string url = pagesStd(wurl.string());
        auto& frame = task.frameInfo();
        const auto& origin = frame.securityOrigin();
        const std::string frameOrigin = pagesStd(origin.protocol()) + "://" + pagesStd(origin.host());
        auto fail = [&](int code, const char* why) {
            fprintf(stderr, "pages: refused %s (%s)\n", url.substr(0, 160).c_str(), why);
            task.didComplete(WebCore::ResourceError(WTF::String::fromLatin1("OmniPages"), code, wurl, WTF::String::fromLatin1(why)));
        };
        if (!pagesAllow || !pagesAllow(WebKit::toAPI(&page), url, frame.isMainFrame(), frameOrigin)) { fail(403, "not allowed"); return; }
        const std::string rel = pagesRelPath(url);
        if (rel.empty() || pagesRoot.empty()) { fail(400, "bad path"); return; }
        const std::string file = pagesRoot + "/" + rel;
        struct stat st {};
        if (stat(file.c_str(), &st) || !S_ISREG(st.st_mode) || st.st_size > (24 << 20)) { fail(404, "not found"); return; }
        std::ifstream in(file, std::ios::binary);
        std::vector<uint8_t> data((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
        if (!in.good() && !in.eof()) { fail(500, "read failed"); return; }
        const char* mime = pagesMime(rel);
        WebCore::ResourceResponse response { WTF::URL { wurl }, WTF::String::fromLatin1(mime), static_cast<long long>(data.size()),
            pagesTextMime(mime) ? WTF::String::fromLatin1("utf-8") : WTF::String() };
        response.setHTTPStatusCode(200);
        response.setHTTPHeaderField(WebCore::HTTPHeaderName::ContentSecurityPolicy, WTF::String::fromLatin1(pagesCSP));
        response.setHTTPHeaderField(WTF::String::fromLatin1("X-Content-Type-Options"), WTF::String::fromLatin1("nosniff"));
        response.setHTTPHeaderField(WTF::String::fromLatin1("Cache-Control"), WTF::String::fromLatin1("no-cache"));
        task.didReceiveResponse(WTF::move(response));
        task.didReceiveData(WebCore::SharedBuffer::create(std::span<const uint8_t>(data.data(), data.size())));
        task.didComplete(WebCore::ResourceError());
    }
    void platformStopTask(WebKit::WebPageProxy&, WebKit::WebURLSchemeTask&) final { }   // every task completes synchronously
};
// webkit.messageHandlers.omnibloomHost: it exists in the page world of every document, so each message is checked here:
// only the main frame of a document whose origin is omni://pages gets an answer.
class PagesMessageClient final : public WebKit::WebScriptMessageHandler::Client {
    void didPostMessage(WebKit::WebPageProxy& page, WebKit::FrameInfoData&& info, API::ContentWorld&, WebKit::JavaScriptEvaluationResult&& result,
        WTF::CompletionHandler<void(std::expected<WebKit::JavaScriptEvaluationResult, WTF::String>&&)>&& completion) override
    {
        std::string reply = "{\"ok\":false,\"code\":\"DENIED\"}";
        auto* main = page.mainFrame();
        const bool trusted = pagesStd(info.securityOrigin.protocol()) == "omni" && pagesStd(info.securityOrigin.host()) == "pages"
            && main && main->frameID() == info.frameID && pagesStd(info.request.url().string()).rfind("omni://pages/", 0) == 0;
        if (trusted && pagesMessage) {
            const std::string body = pagesStd(result.toString());
            reply = body.size() > (64u << 10) ? std::string("{\"ok\":false,\"code\":\"INVALID_VALUE\"}") : pagesMessage(WebKit::toAPI(&page), body);
        } else if (!trusted) fprintf(stderr, "pages: bridge message refused from %s\n", pagesStd(info.securityOrigin.toString()).substr(0, 80).c_str());
        Ref<API::String> text = API::String::create(addonString(reply));
        if (auto value = WebKit::JavaScriptEvaluationResult::extract(text.ptr())) completion(WTF::move(*value));
        else completion(std::unexpected<WTF::String>(WTF::String()));
    }
};
void pagesReaddBridge()
{
    if (!pagesBridge) return;
    addonAddTo(controller.get(), *pagesBridge, false);
    if (privateController) addonAddTo(privateController.get(), *pagesBridge, false);
}
}
void omniPagesSetup(const std::string& root, OmniPagesAllowFn allow, OmniPagesMessageFn message)
{
    pagesRoot = root; pagesAllow = allow; pagesMessage = message;
    if (!controller || pagesHandlerAdded) return;
    for (WKUserContentControllerRef target : { controller.get(), privateController.get() }) {
        if (!target) continue;
        auto handler = WebKit::WebScriptMessageHandler::create(std::make_unique<PagesMessageClient>(), WTF::String::fromLatin1("omnibloomHost"),
            API::ContentWorld::pageContentWorldSingleton());
        WebKit::toImpl(target)->addUserScriptMessageHandler(handler.get());
    }
    pagesHandlerAdded = true;
}
bool omniPagesInstall(WKPageConfigurationRef config)
{
    if (!config || pagesRoot.empty()) return false;
    auto* impl = WebKit::toImpl(config);
    const auto scheme = WTF::String::fromLatin1("omni");
    if (impl->urlSchemeHandlerForURLScheme(scheme)) return true;   // popups reuse the opener's configuration
    impl->setURLSchemeHandlerForURLScheme(PagesSchemeHandler::create(), scheme);
    return true;
}
bool omniPagesSetBridge(const std::string& source)
{
    if (!controller) return false;
    auto* main = WebKit::toImpl(controller.get());
    auto* mirror = privateController ? WebKit::toImpl(privateController.get()) : nullptr;
    if (pagesBridge) { main->removeUserScript(*pagesBridge); if (mirror) mirror->removeUserScript(*pagesBridge); }
    WebCore::UserScript script { addonString(source), { }, addonList({ "omni://pages/*" }), { },
        WebCore::UserScriptInjectionTime::DocumentStart, WebCore::UserContentInjectedFrames::InjectInTopFrameOnly,
        WebCore::UserContentMatchParentFrame::ForOpaqueOrigins };
    Ref<API::UserScript> userScript = API::UserScript::create(WTF::move(script), API::ContentWorld::pageContentWorldSingleton());
    pagesBridge = userScript.ptr();
    addonAddTo(controller.get(), userScript.get(), true);
    if (privateController) addonAddTo(privateController.get(), userScript.get(), true);
    return true;
}
