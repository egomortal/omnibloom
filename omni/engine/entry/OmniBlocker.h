#pragma once
#include <WebKit/WKUserContentControllerRef.h>
#include <string>
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
