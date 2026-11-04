// OMNI_GAMEPAD_V1: the web Gamepad API (navigator.getGamepads()) fed from the shell's own controller input.
// Every controller SDL has open (DualSense, Master Control's virtual pads) is a libwpe gamepad with the
// standard mapping. WebKit's UI-process provider (GamepadProviderLibWPE) reads them through the libwpe
// gamepad handler installed here; which page receives the input is the shell's choice
// (WKOmniSetGamepadInputPage, UIGamepadProviderLibWPE.cpp): the active tab, only while the browser
// window has focus, no Omni UI (keyboard, menus, panels, settings, dialogs) is open, the setting is on,
// and the page is not the Master Control page (it takes the pad through window.omniPadController and
// would otherwise see every press twice).
// Setting "Web pages can use the controller" (Browser settings), default on; off = /data/omni/gamepad-off.flag.
#pragma once
#include <wpe/wpe.h>

extern "C" void WKOmniSetGamepadInputPage(WKPageRef);

struct OmniGpPad { SDL_JoystickID sdl = -1; struct wpe_gamepad* wpe = nullptr; char id[96] = {}; };
static OmniGpPad omniGpPads[8];
static struct wpe_gamepad_provider* omniGpProvider = nullptr;
static bool omniGpStarted = false;
static int omniGpEnabled = -1;   // -1: not read yet
static WKPageRef omniGpTarget = nullptr;

static bool omniGamepadEnabled()
{
    if (omniGpEnabled < 0) omniGpEnabled = access("/data/omni/gamepad-off.flag", F_OK) ? 1 : 0;
    return omniGpEnabled == 1;
}
static OmniGpPad* omniGpFind(uintptr_t id)
{
    for (auto& p : omniGpPads) if (p.sdl >= 0 && uintptr_t(p.sdl) + 1 == id) return &p;
    return nullptr;
}
static OmniGpPad* omniGpFindSdl(SDL_JoystickID sdl)
{
    for (auto& p : omniGpPads) if (p.sdl == sdl) return &p;
    return nullptr;
}

static struct wpe_view_backend* omniGpViewBackend(void*, void*) { return nullptr; }
static const struct wpe_gamepad_provider_interface omniGpProviderInterface = {
    // create
    [](struct wpe_gamepad_provider* provider) -> void* { omniGpProvider = provider; return provider; },
    // destroy
    [](void*) { omniGpProvider = nullptr; omniGpStarted = false; },
    // start: WebKit listens now (a page asked for gamepads); report the controllers already open
    [](void*) {
        omniGpStarted = true;
        fprintf(stderr, "gamepad: page input monitoring started\n");
        for (auto& p : omniGpPads) if (p.sdl >= 0 && omniGpProvider) wpe_gamepad_provider_dispatch_gamepad_connected(omniGpProvider, uintptr_t(p.sdl) + 1);
    },
    // stop
    [](void*) { omniGpStarted = false; fprintf(stderr, "gamepad: page input monitoring stopped\n"); },
    // get_view_backend: unused on PlayStation (the shell names the page)
    omniGpViewBackend,
    nullptr, nullptr, nullptr,
};
static const struct wpe_gamepad_interface omniGpInterface = {
    // create: WebKit made its gamepad object for one of our ids
    [](struct wpe_gamepad* gamepad, struct wpe_gamepad_provider*, uintptr_t id) -> void* {
        OmniGpPad* p = omniGpFind(id);
        if (p) p->wpe = gamepad;
        return p;
    },
    // destroy
    [](void* data) { if (auto* p = static_cast<OmniGpPad*>(data)) p->wpe = nullptr; },
    // get_id
    [](void* data) -> const char* { auto* p = static_cast<OmniGpPad*>(data); return p && p->id[0] ? p->id : "Wireless Controller (STANDARD GAMEPAD)"; },
    nullptr, nullptr, nullptr,
};

// Before the WebKit context exists (GamepadProviderLibWPE asks libwpe for the provider on first use).
static void omniGamepadInstall()
{
    wpe_gamepad_set_handler(&omniGpProviderInterface, &omniGpInterface);
    fprintf(stderr, "gamepad: web Gamepad API provider installed (setting %s)\n", omniGamepadEnabled() ? "on" : "off");
}

static void omniGpAdd(SDL_JoystickID sdl)
{
    if (omniGpFindSdl(sdl)) return;
    SDL_GameController* c = SDL_GameControllerFromInstanceID(sdl);
    if (!c) return;
    for (auto& p : omniGpPads) if (p.sdl < 0) {
        p.sdl = sdl; p.wpe = nullptr;
        const char* name = SDL_GameControllerName(c);
        snprintf(p.id, sizeof p.id, "%s (STANDARD GAMEPAD)", name && *name ? name : "Wireless Controller");
        if (omniGpStarted && omniGpProvider) wpe_gamepad_provider_dispatch_gamepad_connected(omniGpProvider, uintptr_t(sdl) + 1);
        return;
    }
}
static void omniGpRemove(SDL_JoystickID sdl)
{
    OmniGpPad* p = omniGpFindSdl(sdl);
    if (!p) return;
    if (omniGpStarted && omniGpProvider) wpe_gamepad_provider_dispatch_gamepad_disconnected(omniGpProvider, uintptr_t(sdl) + 1);
    *p = OmniGpPad();
}
static int omniGpButton(int sdlButton)
{
    switch (sdlButton) {
    case SDL_CONTROLLER_BUTTON_A: return WPE_GAMEPAD_BUTTON_BOTTOM;
    case SDL_CONTROLLER_BUTTON_B: return WPE_GAMEPAD_BUTTON_RIGHT;
    case SDL_CONTROLLER_BUTTON_X: return WPE_GAMEPAD_BUTTON_LEFT;
    case SDL_CONTROLLER_BUTTON_Y: return WPE_GAMEPAD_BUTTON_TOP;
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: return WPE_GAMEPAD_BUTTON_LEFT_SHOULDER;
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: return WPE_GAMEPAD_BUTTON_RIGHT_SHOULDER;
    case SDL_CONTROLLER_BUTTON_BACK: return WPE_GAMEPAD_BUTTON_SELECT;
    case SDL_CONTROLLER_BUTTON_START: return WPE_GAMEPAD_BUTTON_START;
    case SDL_CONTROLLER_BUTTON_LEFTSTICK: return WPE_GAMEPAD_BUTTON_LEFT_STICK;
    case SDL_CONTROLLER_BUTTON_RIGHTSTICK: return WPE_GAMEPAD_BUTTON_RIGHT_STICK;
    case SDL_CONTROLLER_BUTTON_DPAD_UP: return WPE_GAMEPAD_BUTTON_D_PAD_TOP;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: return WPE_GAMEPAD_BUTTON_D_PAD_BOTTOM;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: return WPE_GAMEPAD_BUTTON_D_PAD_LEFT;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: return WPE_GAMEPAD_BUTTON_D_PAD_RIGHT;
    case SDL_CONTROLLER_BUTTON_GUIDE: return WPE_GAMEPAD_BUTTON_CENTER;
    default: return -1;
    }
}
// Every SDL controller event (state is kept current whatever the target; only the target page sees it).
static void omniGamepadEvent(const SDL_Event& e)
{
    if (e.type == SDL_CONTROLLERDEVICEADDED) { if (SDL_IsGameController(e.cdevice.which)) omniGpAdd(SDL_JoystickGetDeviceInstanceID(e.cdevice.which)); return; }
    if (e.type == SDL_CONTROLLERDEVICEREMOVED) { omniGpRemove(e.cdevice.which); return; }
    if (e.type == SDL_CONTROLLERBUTTONDOWN || e.type == SDL_CONTROLLERBUTTONUP) {
        OmniGpPad* p = omniGpFindSdl(e.cbutton.which);
        const int b = omniGpButton(e.cbutton.button);
        if (p && p->wpe && b >= 0) wpe_gamepad_dispatch_button_changed(p->wpe, static_cast<enum wpe_gamepad_button>(b), e.type == SDL_CONTROLLERBUTTONDOWN);
        return;
    }
    if (e.type == SDL_CONTROLLERAXISMOTION) {
        OmniGpPad* p = omniGpFindSdl(e.caxis.which);
        if (!p || !p->wpe) return;
        const double v = e.caxis.value < 0 ? e.caxis.value / 32768.0 : e.caxis.value / 32767.0;
        switch (e.caxis.axis) {
        case SDL_CONTROLLER_AXIS_LEFTX: wpe_gamepad_dispatch_axis_changed(p->wpe, WPE_GAMEPAD_AXIS_LEFT_STICK_X, v); break;
        case SDL_CONTROLLER_AXIS_LEFTY: wpe_gamepad_dispatch_axis_changed(p->wpe, WPE_GAMEPAD_AXIS_LEFT_STICK_Y, v); break;
        case SDL_CONTROLLER_AXIS_RIGHTX: wpe_gamepad_dispatch_axis_changed(p->wpe, WPE_GAMEPAD_AXIS_RIGHT_STICK_X, v); break;
        case SDL_CONTROLLER_AXIS_RIGHTY: wpe_gamepad_dispatch_axis_changed(p->wpe, WPE_GAMEPAD_AXIS_RIGHT_STICK_Y, v); break;
        case SDL_CONTROLLER_AXIS_TRIGGERLEFT: case SDL_CONTROLLER_AXIS_TRIGGERRIGHT: {
            const auto button = e.caxis.axis == SDL_CONTROLLER_AXIS_TRIGGERLEFT ? WPE_GAMEPAD_BUTTON_LEFT_TRIGGER : WPE_GAMEPAD_BUTTON_RIGHT_TRIGGER;
#if WPE_CHECK_VERSION(1, 16, 2)
            wpe_gamepad_dispatch_analog_button_changed(p->wpe, button, v < 0 ? 0 : v);
#else
            wpe_gamepad_dispatch_button_changed(p->wpe, button, v > 0.5);
#endif
            break;
        }
        default: break;
        }
    }
}
// OMNI_GAMEPAD_TEST_V1 (gamepad self-test only): a virtual pad with no SDL device behind it.
static void omniGpTestPad(bool on)
{
    const SDL_JoystickID sdl = 4000;
    if (on) {
        for (auto& p : omniGpPads) if (p.sdl < 0) {
            p.sdl = sdl; p.wpe = nullptr; snprintf(p.id, sizeof p.id, "Omni self-test pad (STANDARD GAMEPAD)");
            fprintf(stderr, "gamepad: test pad added (monitoring %s)\n", omniGpStarted ? "on" : "off");
            if (omniGpStarted && omniGpProvider) wpe_gamepad_provider_dispatch_gamepad_connected(omniGpProvider, uintptr_t(sdl) + 1);
            return;
        }
    } else omniGpRemove(sdl);
}
static void omniGpTestPress(bool down)
{
    OmniGpPad* p = omniGpFindSdl(4000);
    fprintf(stderr, "gamepad: test press %d (pad %s, target %s)\n", down ? 1 : 0, p && p->wpe ? "created by WebKit" : "not created", omniGpTarget ? "set" : "none");
    if (!p || !p->wpe) return;
    wpe_gamepad_dispatch_button_changed(p->wpe, WPE_GAMEPAD_BUTTON_BOTTOM, down);
    wpe_gamepad_dispatch_axis_changed(p->wpe, WPE_GAMEPAD_AXIS_LEFT_STICK_X, down ? 0.5 : 0.0);
}
static bool omniMcOrigin(const std::string& url); // OMNI_PAD_CONTROLLER_V1 (below)
// Once per shell tick: the page that should get gamepad input now (nullptr = none).
static void omniGamepadTick(Tab* tab, bool omniUiOpen, bool focused)
{
    WKPageRef want = nullptr;
    if (omniGamepadEnabled() && tab && focused && !omniUiOpen && !tab->crashed && !omniMcOrigin(tab->url))
        want = tab->page;
    if (want == omniGpTarget) return;
    omniGpTarget = want;
    WKOmniSetGamepadInputPage(want);
}
static void omniGamepadSetEnabled(bool on)
{
    if (on) unlink("/data/omni/gamepad-off.flag");
    else if (FILE* f = fopen("/data/omni/gamepad-off.flag", "w")) fclose(f);
    omniGpEnabled = on ? 1 : 0;
    if (!on && omniGpTarget) { omniGpTarget = nullptr; WKOmniSetGamepadInputPage(nullptr); }
    fprintf(stderr, "gamepad: web pages can use the controller: %s\n", on ? "on" : "off");
}

// OMNI_PAD_CONTROLLER_V1: the Master Control page (fixed origins, exact match) gets the D-pad, Cross,
// Circle, Square, Triangle, L1 and R1 first through window.omniPadController(action), like the Media
// downloads page's omniMediaController. Its answer says whether it used the press; when it did not
// (Circle on the dial, nothing to move to) the press runs the normal browser action.
static bool omniMcOrigin(const std::string& url)
{
    for (const char* origin : { "http://127.0.0.1:8095", "http://192.0.2.10:8095" }) {
        const size_t n = strlen(origin);
        if (url.size() >= n && !url.compare(0, n, origin) && (url.size() == n || url[n] == '/' || url[n] == '?' || url[n] == '#')) return true;
    }
    return false;
}
