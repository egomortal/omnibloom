#!/usr/bin/env python3
# features-3 (OMNI_FEATURES_V3): applies the hooks to a clean dl2-candidate-44 entry/ directory.
# Every replacement must match exactly once (it stops on any drift). Files keep CRLF.
import sys, os
T = '// OMNI_FEATURES_V3'
E = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'entry')
H = {
'OmniBrowser.cpp': [
 ('#include <dirent.h> // OMNI_FEATURES_V1: downloads page\n',
  '#include <dirent.h> // OMNI_FEATURES_V1: downloads page\n#include <atomic> ' + T + ': screenshot writer state\n#include <WebKit/WKBackForwardListRef.h> ' + T + ': unloaded tabs\n'),
 ('extern "C" bool omniUBlockPopupBlocked(const char* url, const char* opener);\n',
  'extern "C" bool omniUBlockPopupBlocked(const char* url, const char* opener);\n'
  'extern "C" WKUserScriptRef WKUserScriptCreateWithSourceInWorldOmni(WKStringRef source, _WKUserScriptInjectionTime, bool forMainFrameOnly, WKStringRef worldName); ' + T + ': dark pages (as OmniBlocker.cpp)\n'),
 ('#include "OmniFeaturesDecl.h" // OMNI_FEATURES_V1: browser features (definitions in OmniFeatures.h)\n',
  '#include "OmniFeaturesDecl.h" // OMNI_FEATURES_V1: browser features (definitions in OmniFeatures.h)\n#include "OmniFeatures3Decl.h" ' + T + ': star, suggestions, page tools, dark pages, tab memory\n'),
 ('    omniEverydayActivated(); // OMNI_EVERYDAY_V1: restored tabs load when first shown\n',
  '    omniEverydayActivated(); // OMNI_EVERYDAY_V1: restored tabs load when first shown\n    omniF3TabActivated(); ' + T + ': an unloaded tab reloads when shown\n'),
 ('void finished(WKPageRef page, WKNavigationRef, WKTypeRef, const void* info)\n{\n    auto& tab = *static_cast<Tab*>(const_cast<void*>(info));\n',
  'void finished(WKPageRef page, WKNavigationRef, WKTypeRef, const void* info)\n{\n    auto& tab = *static_cast<Tab*>(const_cast<void*>(info));\n    if (omniF3TabFinished(tab)) return; ' + T + ': the blank page of an unloaded tab\n'),
 ('    if (tabs.size() >= 4) { status = "Four-tab limit for this first build. Close a tab to open another."; return nullptr; }\n',
  '    if (!omniF3TabAllowed()) return nullptr; ' + T + ': tab limit setting (default 4) + memory guard (was a fixed four-tab limit)\n'),
 ('        if (x < 100) return;\n',
  '        if (omniF3TabStripClick(x)) return; ' + T + ': more than 4 tabs\n        if (x < 100) return;\n'),
 ('        else editAddress();\n    } else {',
  '        else if (omniF3StarClick(x, by)) { } ' + T + ': bookmark star\n        else editAddress();\n    } else {'),
 ('    const float right = 1086;\n', '    const float right = omniF3StarShown() ? 1052 : 1086; ' + T + ': room for the star\n'),
 ('    if (url.empty()) { omniLabel("Search or enter address", x, 82, omniSmall, T.inkFaint); return; }\n',
  '    if (url.empty()) { omniLabel("Search or enter address", x, 82, omniSmall, T.inkFaint); return; }\n    omniF3StarDraw(); ' + T + ': bookmark star\n'),
 ('    for (size_t i = 0; i < tabs.size(); ++i) {\n        const int x = 100 + int(i) * 240;\n        const Tab& tab = *tabs[i];\n',
  '    if (!omniF3DrawTabStrip()) ' + T + ': more than 4 tabs: compact / scrolling strip (4 or fewer: unchanged)\n    for (size_t i = 0; i < tabs.size(); ++i) {\n        const int x = 100 + int(i) * 240;\n        const Tab& tab = *tabs[i];\n'),
 ('    const bool full = tabs.size() >= 4;\n', '    const bool full = omniF3TabsFull(); ' + T + ': tab limit setting\n'),
 ('    if (omniAutoHideActive() && omniChromeShown < 1) return;\n',
  '    if (omniAutoHideActive() && omniChromeShown < 1) return;\n    if (tabs.size() > 4) return; ' + T + ': the compact strip marks private tabs itself\n'),
 ('struct OmniSuggestion { std::string url, title; };\n', 'struct OmniSuggestion { std::string url, title; bool search = false; }; ' + T + ': search: a search-engine suggestion\n'),
 ('    for (size_t i = 0; i < found.size() && i < 5; ++i) omniSuggestions.push_back(found[i].s);\n',
  '    std::vector<OmniSuggestion> local; ' + T + ': merged with the search engine\'s suggestions\n    for (size_t i = 0; i < found.size() && i < 5; ++i) local.push_back(found[i].s);\n    omniF3SuggestMerge(local);\n'),
 ('        const std::string bare = omniShownURL(s.url);\n', '        const std::string bare = s.search ? omniF3SuggestDetail() : omniShownURL(s.url); ' + T + '\n'),
 ('    if (item == omniMenuPrivate) return tabs.size() < 4;\n', '    if (item == omniMenuPrivate) return !omniF3TabsFull(); ' + T + '\n'),
 ('omniLabel("4 tabs open", x + omniMenuW - 32', 'omniLabel("Tab limit reached", x + omniMenuW - 32'),
 ('            if (s.rfind("tab\\t", 0) == 0 && saved.size() < 4) {\n',
  '            if (s.rfind("tab\\t", 0) == 0 && saved.size() < size_t(omniF3TabLimit())) { ' + T + ': tab limit setting\n'),
 ('#include "OmniFeatures.h" // OMNI_FEATURES_V1\n', '#include "OmniFeatures.h" // OMNI_FEATURES_V1\n#include "OmniFeatures3.h" ' + T + '\n'),
 ('    omniFxTick(); // OMNI_FEATURES_V1: hold timer, settings load\n',
  '    omniFxTick(); // OMNI_FEATURES_V1: hold timer, settings load\n    omniF3Tick(); ' + T + ': suggestions, screenshot, dark pages, tab memory\n'),
],
'OmniQuickMenu.h': [
 ('four = tabs.size() >= 4;\n', 'four = omniF3TabsFull(); ' + T + '\n'),
 ('four ? "4 open" : "");\n', 'four ? std::to_string(tabs.size()) + " open" : std::string()); ' + T + '\n'),
 ('    add(omniQmCopy, "Copy address", web);\n', '    add(omniQmCopy, "Copy address", web);\n    omniF3QuickTiles(p); ' + T + ': Screenshot, Page source, Dark page\n'),
 ('    if (b != SDL_CONTROLLER_BUTTON_A) return false;\n    if (!r.enabled) return true;\n    Tab* t = active();\n    switch (r.id) {   // stay open\n',
  '    if (b != SDL_CONTROLLER_BUTTON_A) return false;\n    if (!r.enabled) return true;\n    if (omniF3QuickAction(r.id)) return true; ' + T + '\n    Tab* t = active();\n    switch (r.id) {   // stay open\n'),
 ('    add(omniFxSiteReload, "Reload page", "", active() != nullptr, false);\n',
  '    omniF3SiteRows(p, host); ' + T + ': dark page on this site\n    add(omniFxSiteReload, "Reload page", "", active() != nullptr, false);\n'),
 ('    if (!r.enabled) return b == SDL_CONTROLLER_BUTTON_A;\n', '    if (!r.enabled) return b == SDL_CONTROLLER_BUTTON_A;\n    if (r.id >= 300) return omniF3SiteInput(r, b); ' + T + '\n'),
],
'OmniBrowserSettings.h': [
 ('#define OMNI_FEATURES_LABEL "features-1"\n', '#define OMNI_FEATURES_LABEL "features-3" ' + T + '\n'),
 ('    add(omniFxSetDisplay, "Controller, theme and display...", "", false);\n',
  '    omniF3SettingsRows(p); ' + T + ': dark pages, suggestions, tab limit, tabs kept loaded, tab memory\n    add(omniFxSetDisplay, "Controller, theme and display...", "", false);\n'),
 ('    const int dir = left ? -1 : (right || a) ? 1 : 0;\n    switch (r.id) {\n    case omniFxSetSearch:\n',
  '    const int dir = left ? -1 : (right || a) ? 1 : 0;\n    if (r.id >= 300) return omniF3SettingsInput(r, b); ' + T + '\n    switch (r.id) {\n    case omniFxSetSearch:\n'),
],
'OmniContextMenu.h': [
 ('    const bool four = tabs.size() >= 4;\n', '    const bool four = omniF3TabsFull(); ' + T + '\n'),
 ('        add(omniCxReader, "Reader view", web);\n', '        add(omniCxReader, "Reader view", web);\n        omniF3ContextRows(p); ' + T + ': page source, screenshot, dark page\n'),
 ('    if (!r.enabled) return true;\n    const std::string link = p.link,', '    if (!r.enabled) return true;\n    if (omniF3ContextAction(r.id)) return true; ' + T + '\n    const std::string link = p.link,'),
],
'OmniTabsPage.h': [
 ('    if (!newTab()) { notice("Four tabs open: close one first"); return; }\n', '    if (!newTab()) return; ' + T + ': newTab() says why (limit or memory)\n'),
 ('    if (tabs.size() >= 4) { notice("Four tabs open: close one first"); return false; }\n    if (priv) omniNewPrivateTab(); else if (!newTab()) { notice("Four tabs open: close one first"); return false; }\n',
  '    if (!omniF3TabAllowed()) return false; ' + T + ': limit setting + memory guard (it says why)\n    if (priv) omniNewPrivateTab(); else if (!newTab()) return false;\n'),
 ('        if (t.omniPrivate && i == selected) r.value = "Current, private";\n',
  '        if (t.omniPrivate && i == selected) r.value = "Current, private";\n        omniF3TabRowValue(t, i == selected, r.value); ' + T + ': "Unloaded"\n'),
 ('n.enabled = tabs.size() < 4; if (!n.enabled) n.value = "4 tabs open";', 'n.enabled = !omniF3TabsFull(); if (!n.enabled) n.value = "Tab limit reached"; ' + T),
 ('v.enabled = tabs.size() < 4;\n', 'v.enabled = !omniF3TabsFull(); ' + T + '\n'),
 ('c.enabled = !omniFxClosed.empty() && tabs.size() < 4;\n', 'c.enabled = !omniFxClosed.empty() && !omniF3TabsFull(); ' + T + '\n'),
 ('    p.corner = std::to_string(tabs.size()) + " of 4";\n', '    p.corner = std::to_string(tabs.size()) + " of " + std::to_string(omniF3TabLimit()); ' + T + '\n'),
],
'OmniBookmarks.h': [
 ('if (newTab()) navigate(url); else notice("Four tabs open: close one first");', 'if (newTab()) navigate(url); ' + T + ': newTab() says why'),
],
'OmniDownloadsPage.h': [
 ('notice("Four tabs open: opening here");', 'notice("No new tab possible: opening here"); /* OMNI_FEATURES_V3 */'),
],
}
for name, reps in H.items():
    p = os.path.join(E, name)
    s = open(p, newline='').read()
    assert '\r\n' in s, name
    s = s.replace('\r\n', '\n')
    for a, b in reps:
        n = s.count(a)
        if n != 1: sys.exit('%s: %d matches for %r' % (name, n, a[:70]))
        s = s.replace(a, b)
    open(p, 'w', newline='').write(s.replace('\n', '\r\n'))
    print(name, len(reps), 'hooks')
