// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_MQ_NATIVE_V1: shared pointer/controller actions in a reserved chrome row.
#pragma once
static bool omniDkWant(const std::string&);
static int omniMqFocus = -1;
static float omniMqReturnX = 0, omniMqReturnY = 0;
static const void* omniMqOwner = nullptr;
static bool omniMqAvailable()
{
    return active() && !editing && !settingsOpen && !pageFullscreen && !omniOverlayOpen()
        && !omniFindBarOpen() && !(omniMediaDownloadsEnabled && omniSavedOwnedView() != OmniSavedView::None);
}
static int omniMqHit(int x, int y)
{
    if (y < 116 || y >= 160 || x < 640) return -1;
    const int column = (x - 640) / 158;
    return column < 4 && (x - 640) % 158 < 150 ? column : -1;
}
static bool omniMqEnabled(int item)
{
    return item != 1 || (active() && omniWebURL(active()->url));
}
static void omniMqActivate(int item)
{
    if (!omniMqEnabled(item)) return;
    if (item == 0) { if (omniBlockerSetEnabled(!omniBlockerEnabled()) && active()) WKPageReload(active()->page); }
    else if (item == 1) omniF3QuickAction(303); // existing Dark page action
    else if (item == 2) { omniMqFocus = -1; omniHubAppsShow(); }
    else if (item == 3) { omniMqFocus = -1; omniAdQuickAction(381); }
    omniShellDirty = true;
}
static bool omniMqClick(int x, int y)
{
    omniMqFocus = -1; // Any pointer activation owns focus, including a click back in the page.
    if (!omniMqAvailable()) return false;
    const int pageTop = omniPageTop();
    if (y >= pageTop) return false;
    const int barY = y + top - pageTop;
    if (barY < 112 || barY >= top) return false;
    const int hit = omniMqHit(x, barY);
    omniMqFocus = -1;
    if (hit >= 0) omniMqActivate(hit);
    return true; // padding belongs to the row, never to address/settings controls
}
static void omniMqPointerTakeover() { ++omniMqInputGeneration; omniMqFocus = -1; }
static void omniMqEnter()
{
    if (!omniMqAvailable()) return;
    omniMqReturnX = pointerX;
    omniMqReturnY = std::max(0.f, pointerY - omniPageTop()); // content-relative, including hidden chrome
    omniMqOwner = active(); omniMqFocus = 0;
    // Reveal atomically before positioning the chrome-owned pointer. The style tick
    // must not carry it down with the page as it would during a slide animation.
    omniChromeWanted = true; omniChromeT = omniChromeShown = 1.f;
    omniPageDirty = omniShellDirty = true; omniChromeWake();
    pointerX = 715; pointerY = 138;
}
static bool omniMqButton(int b)
{
    if (!omniMqAvailable()) { omniMqFocus = -1; return false; }
    if (omniMqFocus < 0 || omniMqOwner != active()) { omniMqFocus = -1; return false; }
    if (b == SDL_CONTROLLER_BUTTON_B || b == SDL_CONTROLLER_BUTTON_DPAD_DOWN) {
        pointerX = omniMqReturnX; pointerY = std::clamp(omniPageTop() + omniMqReturnY, float(omniPageTop()), float(height-bottom-1)); omniMqFocus = -1; return true;
    } else if (b == SDL_CONTROLLER_BUTTON_DPAD_LEFT) omniMqFocus = (omniMqFocus + 3) % 4;
    else if (b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT) omniMqFocus = (omniMqFocus + 1) % 4;
    else if (b == SDL_CONTROLLER_BUTTON_A) { omniMqActivate(omniMqFocus); return true; }
    else if (b != SDL_CONTROLLER_BUTTON_DPAD_UP) { omniMqFocus = -1; return false; }
    omniChromeWake();
    pointerX = 715 + 158 * omniMqFocus; pointerY = 138;
    return true;
}
static void omniMqDraw()
{
    const OmniTheme& t = omniTheme();
    fill(0, 112, width, top - 112, t.bar);
    omniLabel("Quick access", 24, 138, omniSmall, t.inkDim);
    const bool web = active() && omniWebURL(active()->url);
    const std::string labels[] = {
        std::string("uBlock ") + (omniBlockerFailed() ? "Error" : omniBlockerEnabled() ? "On" : "Off"),
        std::string("Dark mode ") + (!web ? "—" : omniDkWant(active()->url) ? "On" : "Off"), "Apps", "Add-ons"
    };
    for (int i = 0; i < 4; ++i) {
        const int x = 640 + i * 158;
        const bool selected = omniMqFocus == i || omniHover(x, 116, 150, 44), enabled = omniMqEnabled(i);
        if (selected) omniRingRect(x, 116, 150, 44, omniRadius, t.accent, t.hover);
        else omniEdgeRect(x, 116, 150, 44, omniRadius, t.edge, t.tab);
        omniLabel(labels[i], x + 75, 138, omniSmall, enabled ? t.ink : t.inkFaint, 1, 138);
    }
}
