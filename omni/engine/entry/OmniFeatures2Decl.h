// OMNI_FEATURES_V2: forward declarations for the second round of browser features (saved logins
// entered by hand + fill-on-demand, form autofill, file upload picker, site permissions). Included
// inside OmniBrowser.cpp's anonymous namespace right after OmniFeaturesDecl.h; the definitions are
// in OmniFeatures2.h (included just after OmniFeatures.h, before tick()). Every hook in
// OmniBrowser.cpp is one line tagged OMNI_FEATURES_V2. See outputs/changes/features-2/REPORT.md.
#pragma once
struct OmniFxPanel;
struct OmniFxRow;
static void omniF2InstallUI(WKPageUIClientV19& ui);            // newTab(): file chooser + permission callbacks
static int omniF2PopupPolicy(WKPageRef page, const std::string& opener, const std::string& target, bool gesture);   // 1 allow, -1 block, 0 as before
static void omniF2PopupBlocked(WKPageRef page, const std::string& opener, const std::string& target);
static void omniF2Tick();                                       // storage prompt, picker cancel, reveal reset
static void omniF2SiteExtra(OmniFxPanel& p);                    // extra rows for the Site settings panel
static bool omniF2SiteInput(const OmniFxRow& r, int b);         // their input (true: handled)
static void omniF2SettingsExtra(OmniFxPanel& p);               // extra rows for the Browser settings panel
static bool omniF2SettingsInput(const OmniFxRow& r, int b);
static bool omniF2QuickExtra(OmniFxPanel& p);                   // extra rows for the quick menu (returns true if any added)
static bool omniF2QuickInput(const OmniFxRow& r, int b);
