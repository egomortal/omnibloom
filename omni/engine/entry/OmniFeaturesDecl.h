// OMNI_FEATURES_V1: forward declarations for the browser-feature hooks in OmniBrowser.cpp.
// Included inside OmniBrowser.cpp's anonymous namespace, after `struct Tab`; the definitions are in
// OmniFeatures.h (included just before tick()). Every hook in OmniBrowser.cpp is a one-line call
// tagged OMNI_FEATURES_V1 so the visual-polish work merges cleanly around it.
#pragma once
struct Tab;
static std::string omniFxSearchPrefix();                       // destination(): search URL prefix
static std::string omniFxSearchAction();                       // new-tab page form action
static std::string omniFxSearchName();                         // "Google", "DuckDuckGo", ...
static bool omniFxQuietFailure(Tab& tab, const std::string& domain, int code, const std::string& description);
static void omniFxRecordFailure(Tab& tab, WKErrorRef error);   // failed(): remember the failing URL
static bool omniFxErrorPanelShown();                           // the toast leaves page errors to the panel
static void omniFxTabClosing(Tab& tab);                        // closeTab(): reopen-closed-tab list
static double omniFxDefaultZoom();                             // omniZoomFor(): sites without their own zoom
static void omniFxApplyTextZoom(Tab* tab);                     // omniApplySiteZoom(): text size setting
static void omniFxDownloadStarted(WKDownloadRef download, const std::string& path);
static void omniFxDownloadProgress(WKDownloadRef download, long long total, long long expected);
static void omniFxDownloadEnded(WKDownloadRef download, bool ok);
static bool omniFxPolicyDownload(WKPageRef page, WKNavigationActionRef action, WKFramePolicyListenerRef listener);
static void omniFxQuickMenuShow();                             // Options (and Esc) while browsing
static void omniFxBack();                                      // B / D-pad left, with feedback
static void omniFxForward();
static bool omniFxDpadSide(int button);                        // D-pad left/right while browsing
static bool omniFxButtonEvent(const SDL_ControllerButtonEvent& event);   // hold Cross for the context menu
static void omniFxStickTick();                                 // pointer acceleration, snapping, right stick
// OMNI_STICK_DEADZONE_V1: stick dead zone (definitions in OmniPointerFeel.h)
static float omniStickDeadZone(bool right);                    // radius (fraction of full deflection) for the chosen size
static float omniStickGate(bool right, float medium);          // a stick threshold set for Medium, kept above the chosen dead zone
static float omniStickScale(SDL_GameController* c, bool right); // right-stick factor: 0 inside the dead zone, rescaled past it
static bool omniStickAxisLive(const SDL_ControllerAxisEvent& e); // axis event outside the dead zone (bars, active pad)
static bool omniStickQuietEvent(const SDL_Event& e);           // stick event inside the dead zone: no redraw
static void omniFxTick();                                      // hold timer, snap animation, downloads redraw
// OMNI_POINTER_STYLE_V1: pointer style, size, colour, outline, opacity (definitions in OmniPointerStyle.h)
static uint64_t omniPtrSignature(double scale);                // changes when the pointer sprite must be rebuilt
static SDL_Surface* omniPtrBuildSprite(double scale, int* hotX, int* hotY); // the sprite and its hotspot (never null unless out of memory)
static uint8_t omniPtrAlpha();                                 // opacity setting, 0-255
