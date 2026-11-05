#pragma once
#include <WebKit/WKUserContentControllerRef.h>
#include <WebKit/WKPageConfigurationRef.h>
#include <string>
#include <vector>
void omniBlockerInitialize(bool testing, void (*ready)(bool));
WKUserContentControllerRef omniBlockerController();
bool omniBlockerEnabled();
bool omniBlockerSetEnabled(bool enabled);
bool omniBlockerUsesUBlock();
bool omniBlockerFailed();
void omniBlockerPoll();
// uBlock content filtering (scriptlets + cosmetic filters, injected user scripts).
bool omniBlockerContentActive();
// Extra user scripts owned by the shell (kept across uBlock script rebuilds).
void omniBlockerAddShellScript(WKUserScriptRef);
// Per-site "trusted" switch: disables network, cosmetic and scriptlet filtering
// for pages whose top-level hostname is (a subdomain of) a listed hostname.
std::string omniBlockerHostOf(const std::string& url);
bool omniBlockerSiteTrusted(const std::string& host);
bool omniBlockerSetSiteTrusted(const std::string& host, bool trusted);
// OMNI_UBO_SITE_V1: per-site uBlock content (default since OMNI_PERF_D_W1; off with /data/omni/ubo-site-rules-disabled.flag). Call before a navigation
// to url is allowed; topURL = the page's main-frame URL when the navigation is in a subframe.
// OMNI_C52_FIX1: Wanted = flag present and the site data not known to be unusable (install the hooks);
// Active = per-site scripts are in use right now (check before copying any URL). privateTab: never logged.
bool omniBlockerSiteRulesWanted();
bool omniBlockerSiteActive();
void omniBlockerPrepareSite(const std::string& url, const std::string& topURL, bool subframe, bool privateTab);
// OMNI_ADDONS_V1 (OmniAddons.h decides, these only register): each add-on's user script / style sheet lives in
// the world "omni-addon-<id>", with WebKit URL allow + block lists. Private tabs use their own controller,
// which mirrors everything above; add-ons go there only with privateToo.
WKUserContentControllerRef omniBlockerPrivateController();
using OmniAddonMessageFn = std::string (*)(const std::string& addonId, WKPageRef page, const std::string& body);
void omniAddonsSetMessageHandler(OmniAddonMessageFn);
bool omniAddonsAddScript(const std::string& id, const std::string& source, const std::vector<std::string>& allow, const std::vector<std::string>& block,
    bool documentStart, bool allFrames, bool privateToo, bool injectNow);
bool omniAddonsAddStyleSheet(const std::string& id, const std::string& css, const std::vector<std::string>& allow, const std::vector<std::string>& block,
    bool allFrames, bool authorLevel, bool privateToo);
void omniAddonsRemove(const std::string& id);
bool omniAddonsAddMessageHandler(const std::string& id);   // webkit.messageHandlers.omniAddon in that world only
// s3 OMNI_PAGES_V1: Omni's built-in pages (omni://pages/...). allow() decides every load (url, main frame?, the requesting
// frame's origin "scheme://host"); message() answers window.omnibloomHost (trusted documents only; JSON in, JSON out).
using OmniPagesAllowFn = bool (*)(WKPageRef page, const std::string& url, bool mainFrame, const std::string& frameOrigin);
using OmniPagesMessageFn = std::string (*)(WKPageRef page, const std::string& body);
void omniPagesSetup(const std::string& root, OmniPagesAllowFn allow, OmniPagesMessageFn message);
bool omniPagesInstall(WKPageConfigurationRef config);    // each page configuration; true = omni:// is served for it
bool omniPagesSetBridge(const std::string& source);      // page-world document-start script, omni://pages/* top frames only
