// OMNI_FEATURES_V3: forward declarations for the features-3 hooks in OmniBrowser.cpp and the
// features-1 headers (address-bar star, search suggestions, page source, screenshot, dark pages,
// tab limit / memory guard / compact tab strip). Included right after OmniFeaturesDecl.h, inside
// OmniBrowser.cpp's anonymous namespace; the definitions are in OmniFeatures3.h (included just
// after OmniFeatures.h). See outputs/changes/features-3/REPORT.md.
#pragma once
struct Tab;
struct OmniSuggestion;
struct OmniFxPanel;
struct OmniFxRow;
// tabs: limit setting, memory guard, unloaded (discarded) background tabs
static int omniF3TabLimit();                                   // Browser settings > Tab limit (default 4)
static bool omniF3TabsFull();                                  // no new tab possible (limit reached)
static bool omniF3TabAllowed();                                // newTab(): limit + memory guard, sets the status message
static std::string omniF3TabRefusal();                         // the last refusal, for notices
static bool omniF3TabFinished(Tab& tab);                       // finished(): true for an unloaded tab's blank page
static void omniF3TabActivated();                              // activate(): reload an unloaded tab
static bool omniF3DrawTabStrip();                              // omniDrawTopBar(): more than 4 tabs (false: the old strip)
static bool omniF3TabStripClick(int x);                        // click() in the tab row (more than 4 tabs)
// address bar
static bool omniF3StarShown();
static void omniF3StarDraw();
static bool omniF3StarClick(int x, int by);
static void omniF3SuggestMerge(std::vector<OmniSuggestion>& local);   // omniSuggestUpdate(): adds search-engine suggestions
static std::string omniF3SuggestDetail();                      // "Search Google" under a search suggestion
// panels of features-1 (quick menu, site settings, browser settings, context menu, tabs page)
static void omniF3QuickTiles(OmniFxPanel& p);                 // quick menu: Screenshot, Page source, Dark page
static bool omniF3QuickAction(int id);                         // true: handled (ids >= 300)
static void omniF3SiteRows(OmniFxPanel& p, const std::string& host);
static bool omniF3SiteInput(const OmniFxRow& r, int b);
static void omniF3SettingsRows(OmniFxPanel& p);
static bool omniF3SettingsInput(const OmniFxRow& r, int b);
static void omniF3ContextRows(OmniFxPanel& p);
static bool omniF3ContextAction(int id);
static void omniF3TabRowValue(const Tab& t, bool current, std::string& value);
// per pass
static void omniF3Tick();

// OMNI_FEATURES_V3_FIX1 (review of candidate 48): a tab about to be closed is activated without restoring it; session restore
// creates lazy tabs that hold no page, so the memory guard does not refuse them.
static bool omniTmSkipRestore = false, omniF3Restoring = false;
