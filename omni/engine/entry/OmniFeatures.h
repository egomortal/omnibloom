// OMNI_FEATURES_V1: browser features and controller UX, included once from OmniBrowser.cpp just
// before tick() (inside its anonymous namespace, so every shell helper is visible). Declarations used
// by the earlier hooks are in OmniFeaturesDecl.h. See outputs/changes/features-1/REPORT.md.
#pragma once
#include "OmniFeaturesPanel.h"
#include "OmniBrowserSettings.h"
#include "OmniErrorPage.h"
#include "OmniBookmarks.h"
#include "OmniFilesBroker.h" // OMNI_FILES_BROKER_V1
#include "OmniDownloadsPage.h"
#include "OmniTabsPage.h"
#include "OmniContextMenu.h"
#include "OmniPointerFeel.h"
#include "OmniPointerStyle.h" // OMNI_POINTER_STYLE_V1
#include "OmniQuickMenu.h"

// --- hold Cross for the context menu ---------------------------------------------------------------
struct OmniFxHold { bool active = false, fired = false; SDL_JoystickID pad = -1; uint32_t start = 0; };
static OmniFxHold omniFxHoldState;
static bool omniFxHoldEligible()
{
    if (omniTestMode() || !omniFxPointerOnPage() || omniFindBarOpen()) return false;
    if (omniMediaDownloadsEnabled && omniSavedOwnedView() != OmniSavedView::None) return false;   // its own A handling
    return true;
}
// SDL button events, before omniShoulderButton(): Cross over the page is held back until release
// (a press shorter than 0.5 s clicks as before, on release); a longer hold opens the context menu.
static bool omniFxButtonEvent(const SDL_ControllerButtonEvent& event)
{
    if (event.button != SDL_CONTROLLER_BUTTON_A) return false;
    OmniFxHold& h = omniFxHoldState;
    if (event.type == SDL_CONTROLLERBUTTONDOWN) {
        if (h.active || !omniFxHoldEligible()) return false;
        auto* previous = controller;
        omniActivatePad(event.which);
        if (previous != controller) omniShoulderReset();
        h = { true, false, event.which, SDL_GetTicks() };
        omniShellDirty = true;
        return true;
    }
    if (!h.active || event.which != h.pad) return false;
    const bool fired = h.fired;
    h = OmniFxHold();
    if (!fired) button(SDL_CONTROLLER_BUTTON_A);   // the ordinary click
    omniShellDirty = true;
    return true;
}
static void omniFxHoldDraw()
{
    const uint32_t held = SDL_GetTicks() - omniFxHoldState.start;
    if (held < 150) return;
    omniSpinner(pointerX + 24, pointerY + 30, 8, omniTheme().accent);
}

// --- per pass ----------------------------------------------------------------------------------------
static void omniFxTick()
{
    omniFxLoad();
    OmniFxHold& h = omniFxHoldState;
    if (h.active && !h.fired) {
        const SDL_GameController* pad = SDL_GameControllerFromInstanceID(h.pad);
        if (!pad) h = OmniFxHold();
        else if (SDL_GetTicks() - h.start >= 500) { h.fired = true; omniShellDirty = true; omniFxContextQuery(); }
        else omniShellDirty = true;   // the hold indicator animates
    }
    if (Tab* t = active()) {
        auto found = omniFxTabStates.find(t);
        if (found != omniFxTabStates.end() && !t->crashed) found->second.crashDismissed = false;
    }
    static uint32_t prune = 0;
    if (SDL_GetTicks() - prune > 5000) {
        prune = SDL_GetTicks();
        for (auto it = omniFxTabStates.begin(); it != omniFxTabStates.end();) it = omniTabAlive(it->first) ? std::next(it) : omniFxTabStates.erase(it);
    }
}

// --- overlay layers (after History / Browser tools: drawn above them; input is asked in order) ------
[[maybe_unused]] static const bool omniFeaturesLayers = [] {
    auto& layers = omniOverlayLayers();
    layers.push_back({ omniFxErrorShown, omniFxErrorButton, omniFxErrorClick, nullptr, omniFxErrorDraw, true });
    layers.push_back({ omniFxPanelOpen, omniFxButton, omniFxClick, omniFxScroll, omniFxDraw, true });
    layers.push_back({ [] { return omniFxHoldState.active && !omniFxHoldState.fired; }, nullptr, nullptr, nullptr, omniFxHoldDraw, false });
    return true;
}();
