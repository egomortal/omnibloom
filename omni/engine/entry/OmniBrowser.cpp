#include "../media/OmniDiagnosticMode.h"
extern "C" int omniHDROutputPQ(); // OMNI_HDR_PORT_V1
// OMNI_PERF_A_HOOK (for the video service, WS-B): set by the service when it can show a new video picture without a new canvas
// (the presenter owns the fullscreen video pixels). The shell main thread calls it only when the one reason to draw is the
// video plane (holePunchPoll() true, nothing else changed); nonzero skips that draw. nullptr (default): draw as before.
extern "C" int (*omniShellVideoOnlyDrawSkip)(void);
// OMNI_PERF_A_COUNTER: the reason mask (omniDr* bits, OmniBrowser.cpp) of the shell's latest draw decision (diagnostics).
extern "C" unsigned omniShellLastDrawReasons;
// Native tabbed browser shell. All SDL and WebKit calls run on the main loop.
#include "config.h"
#include <wpe/wpe.h> // OMNI_GAMEPAD_V1: at file scope (OmniGamepad.h is included inside the anonymous namespace)
#include "OmniEngineState.h"
#include "OmniPlaybackHud.h"
#include "OmniPng.h"
#include "OmniBlocker.h"
#include "OmniMediaDownloads.h" // OMNI_MEDIA_DOWNLOADS_V1: isolated optional worker
#include "OmniShoulderChord.h" // OMNI_SHOULDER_DOWNLOADS_V1
#include "OmniSavedLinksControls.h" // OMNI_SAVED_LINKS_V1
#include "OmniLinkReviewGate.h"
#include "OmniNamedWorldEval.h"
#include "OmniLinkReviewWire.h"
#include "OmniLinkSnapshot.h"
#include "OmniNetGrabber.h" // OMNI_NET_GRABBER_V1
#include <WebKit/WKContextConfigurationRef.h>
#include <WebKit/WKContextConfigurationPlayStation.h>
#include <WebKit/WKContextPrivate.h>
#include <WebKit/WKWebsiteDataStoreConfigurationRef.h>
#include <WebKit/WKWebsiteDataStoreRef.h>
#include <WebKit/WKPageConfigurationRef.h>
#include <WebKit/WKPageNavigationClient.h>
#include <WebKit/WKPageUIClient.h>
#include <WebKit/WKPageStateClient.h>
#include <WebKit/WKViewClient.h>
#include <WebKit/WKPagePrivatePlayStation.h>
#include <WebKit/WKPagePrivate.h>
#include <WebKit/WKUserScriptRef.h>
#include <WebKit/WKURLResponse.h>
#include <WebKit/WKPreferencesRef.h>
#include <WebKit/WKPreferencesRefPrivate.h>
#include <WebKit/WKRunLoop.h>
#include <WebKit/WKPageFindClient.h> // OMNI_EVERYDAY_V1
#include <WebKit/WKFindOptions.h>
#include <WebKit/WKDownloadRef.h>
#include <WebKit/WKDownloadClient.h>
#include <WebKit/WKNavigationResponseRef.h>
#include <WebKit/WKFramePolicyListener.h>
#include <WebKit/WKFrameInfoRef.h>
#include <WebKit/WKHTTPCookieStoreRef.h>
#include <WebKit/WKPageLoadTypes.h>
#include <ctime>
#include <immintrin.h> // OMNI_SMOOTH_DRAW_V1
#include <unordered_set>
#include <WebKit/WKAuthenticationChallenge.h> // OMNI_DIALOGS_V1
#include <WebKit/WKAuthenticationDecisionListener.h>
#include <WebKit/WKCredential.h>
#include <WebKit/WKProtectionSpace.h>
#include <WebKit/WKSecurityOriginRef.h>
#include <functional>
#include <deque> // OMNI_SHELL_DRAW_V1
#include <utility> // OMNI_SHORTCUTS_V1
#include <unordered_map>
#include <chrono> // OMNI_SHELL_PRESENT_V1
#include <condition_variable>
#include <cstring>
#include <mutex>
#include <thread>
#include "../media/OmniHwService.h" // OMNI_HOLEPUNCH_V1: video plane under the page
#include <pthread.h>
#include <sys/resource.h>
extern "C" void omniPipelineScope(int event, long long kind, long long detail, long long object)
{
    const auto thread = (long long)pthread_self();
    OmniMedia::Hw::diagnosticTrace(event, kind, detail, object, thread);
    if (((kind >= 6 && kind <= 17) || (kind >= 60 && kind <= 63)) || (kind == 5 && detail == 33)) {
        rusage usage {}; const int rc = getrusage(RUSAGE_THREAD, &usage);
        const long long cpu = rc ? -1 : (static_cast<long long>(usage.ru_utime.tv_sec) + usage.ru_stime.tv_sec) * 1000000 + usage.ru_utime.tv_usec + usage.ru_stime.tv_usec;
        OmniMedia::Hw::diagnosticTrace(event == 40 ? 44 : 45, kind, cpu, rc ? -1 : usage.ru_nvcsw, thread);
        OmniMedia::Hw::diagnosticTrace(event == 40 ? 46 : 47, kind, rc ? -1 : usage.ru_nivcsw, rc ? -1 : usage.ru_minflt, thread);
    }
}
struct OmniLocalScope { long long kind; explicit OmniLocalScope(long long k):kind(k) { omniPipelineScope(40,kind,0,0); } ~OmniLocalScope() { omniPipelineScope(41,kind,0,0); } };

#include "../media/OmniAudioRelay.h" // OMNI_AUDIO_RELAY_V1: the relay's device closes before SDL_Quit
#include <WebKit/WKURL.h>
#include <WebKit/WKErrorRef.h>
#include <WebKit/WKNavigationActionRef.h>
#include <WebKit/WKURLRequest.h>
#include <wtf/RunLoop.h>
#define SDL_MAIN_HANDLED
#include <SDL2/SDL.h>
#include <SDL2/SDL_ttf.h>
#include <png.h>
#include <zlib.h> // OMNI_POINTER_STYLE_V1: built-in pointer art
#include "OmniPointerArt.h" // OMNI_POINTER_STYLE_V1: Kenney CC0 cursors and crosshairs
#include "OmniPointerRaster.h" // OMNI_POINTER_STYLE_V1
#include <algorithm>
#include <memory>
#include <sys/stat.h>
#include <unistd.h>
#include <signal.h>
#include <cmath>
#include <dirent.h> // OMNI_FEATURES_V1: downloads page
#include "OmniFeatures2Includes.h" // OMNI_FEATURES_V2
#include <atomic> // OMNI_FEATURES_V3: screenshot writer state
#include <WebKit/WKBackForwardListRef.h> // OMNI_FEATURES_V3: unloaded tabs

#ifdef __PROSPERO__
extern "C" int sceKernelAvailableFlexibleMemorySize(size_t*);
extern "C" int sceKernelConfiguredFlexibleMemorySize(size_t*);
extern "C" int64_t sceKernelGetDirectMemorySize(void);
extern "C" int sceSystemServiceLoadExec(const char*, const char**);
#endif
// uBlock (OmniUBlock.cpp): `$popup` filters for windows a page opens.
extern "C" bool omniUBlockPopupBlocked(const char* url, const char* opener);
extern "C" WKUserScriptRef WKUserScriptCreateWithSourceInWorldOmni(WKStringRef source, _WKUserScriptInjectionTime, bool forMainFrameOnly, WKStringRef worldName); // OMNI_FEATURES_V3: dark pages (as OmniBlocker.cpp)

namespace {
constexpr int width = 1280, height = 720, top = 112, bottom = 32;
constexpr int pageHeight = height - top - bottom;
// OMNI_KEYBOARD_V2: rows of 10 units (88 px) 40 px apart, the action row last; the preview field
// and the panel's top edge sit above keyboardY (the toast and compact dialogs end at y 360).
constexpr int keyboardX = 200, keyboardY = 420, keyWidth = 88, keyHeight = 40;
constexpr int keyboardWidth = 10 * keyWidth, actionY = keyboardY + 5 * keyHeight;
int renderWidth = width, renderHeight = height, renderPageHeight = pageHeight;
double displayScale = 1;
int physical(int value) { return static_cast<int>(value * displayScale + 0.5); }
// OMNI_FAST_PAGE_V1: page view pixels per canvas pixel. 0.5 at 4K: WebKit paints the page at half
// resolution (a quarter of the pixels) and the shell doubles it; video still draws at full 4K.
double omniPageScale = 1;
static WKSize omniViewSize() { return WKSizeMake(std::lround(renderWidth * omniPageScale), std::lround(renderPageHeight * omniPageScale)); }
struct Tab {
    WKRetainPtr<WKViewRef> view;
    WKPageRef page = nullptr;
    std::string title = "New tab", url;
    std::string message;
    bool loading = false;
    bool crashed = false;
    uint32_t loadedAt = 0;
    // uBlock link skipping / URL cleaning: the network process ends a top-level
    // load with "OmniUBlockRedirect"; the shell then opens the rewritten URL.
    std::string pendingURL;
    uint32_t rewriteWindowStart = 0;
    int rewriteCount = 0;
    // OMNI_DIALOGS_V1: JavaScript dialog rate limit per tab ("Block dialogs" silences one host).
    std::deque<uint32_t> omniDialogTimes;
    std::string omniDialogBlockHost;
    // OMNI_EVERYDAY_V1
    bool omniPrivate = false, omniMobileUA = false, omniReader = false, omniNewTabPage = false;
    bool omniMediaSection = false; // OMNI_MEDIA_DOWNLOADS_V1: explicit section ownership
    uintptr_t omniMediaIdentity = OmniMediaDownloads::nextTabIdentity();
    uint64_t omniSavedDocument = 1;
    OmniSavedLinks::VideoObservation omniSavedVideo;
    OmniNetGrabber::Ring omniNetRing; // OMNI_NET_GRABBER_V1: media this tab fetched (never filled for private tabs)
    bool omniNetClient = false;       // OMNI_C52_FIX1: the grabber's resource-load client is installed on this page
    std::string omniLazyURL;      // session tab not loaded yet (loads when first shown)
    std::string omniPendingLoad;  // re-issued with another user agent (next tick)
    uint32_t omniSlowUntil = 0, omniSlowBackoff = 0; // OMNI_PERF_A_S1: a WKPagePaint blocked (>= 100 ms): no page paint before omniSlowUntil
    // OMNI_PERF_A_S1 (ws-a-1b): WebKit reported pixels since this tab was shown (its backing store exists); when a wait for that
    // began; how many watchdog paints were tried without a report (each waits longer: 2, 4, 8 s).
    bool omniShownReported = false, omniEverReported = false;
    uint32_t omniWaitSince = 0, omniNoReportTries = 0;
};
WKRetainPtr<WKContextRef> context;
WKRetainPtr<WKPreferencesRef> preferences;
WKRetainPtr<WKWebsiteDataStoreRef> websiteDataStore;
std::vector<std::unique_ptr<Tab>> tabs;
size_t selected = 0;
// OMNI_SHELL_DRAW_V1: what changed since the last presented frame.
// OMNI_PERF_A_COUNTER: why the shell draws. `omniShellDirty = true` records the phase of tick() it happens in (WebKit:
// outside tick, i.e. callbacks and other timers); tick() adds the page, video, refresh and busy reasons itself. Aggregated
// and logged once per 5 s ("draw reasons (5 s): ..."), never per frame.
enum : unsigned {
    omniDrFirst = 1u << 0, omniDrPageFull = 1u << 1, omniDrPagePartial = 1u << 2, omniDrSafety = 1u << 3,
    omniDrVideo = 1u << 4, omniDrRefresh = 1u << 5, omniDrBusy = 1u << 6, omniDrSpinner = 1u << 7,
    omniDrStyle = 1u << 8, omniDrInput = 1u << 9, omniDrAxis = 1u << 10, omniDrStick = 1u << 11,
    omniDrWebKit = 1u << 12, omniDrFeature = 1u << 13, omniDrSignature = 1u << 14 };
constexpr int omniDrCount = 15;
static unsigned omniDirtyPhase = omniDrWebKit;   // the reason `omniShellDirty = true` records now
static unsigned omniDrawReasons = 0;             // since the last draw decision
struct OmniDirtyFlag {
    bool on = false;
    OmniDirtyFlag& operator=(bool v) { on = v; if (v) omniDrawReasons |= omniDirtyPhase; return *this; }
    OmniDirtyFlag& operator=(const OmniDirtyFlag& o) { return *this = o.on; }
    operator bool() const { return on; }
};
static bool omniPageDirty = true;
static OmniDirtyFlag omniShellDirty { true };
static void omniMarkDirty(unsigned reason) { omniDrawReasons |= reason; omniShellDirty.on = true; }
// OMNI_PERF_A_*: kill switches, read once: /data/omni/perf-a-disabled.flag (all) or perf-a-<item>-disabled.flag.
enum { omniPerfS1, omniPerfS3, omniPerfS4, omniPerfS5, omniPerfS6, omniPerfS7, omniPerfS2, omniPerfS8, omniPerfCount };
static bool omniPerfOn(int item)
{
    static int state[omniPerfCount] = {};   // 0 not read yet, 1 on, 2 off
    if (!state[item]) {
        static const char* const names[omniPerfCount] = { "s1", "s3", "s4", "s5", "s6", "s7", "s2", "s8" };
        char flag[96];
        snprintf(flag, sizeof flag, "/data/omni/perf-a-%s-disabled.flag", names[item]);
        state[item] = access("/data/omni/perf-a-disabled.flag", F_OK) == 0 || access(flag, F_OK) == 0 ? 2 : 1;
    }
    return state[item] == 1;
}
// OMNI_FAST_PAGE_V1 half-resolution page (declared here for OMNI_PERF_A_S5).
static std::vector<uint32_t> omniPageSmall;
// OMNI_PERF_A_S5: the 4K page buffer (`pixels`) lags the half-resolution one; the canvas is filled straight from omniPageSmall,
// and omniEnsurePixels() brings `pixels` up to date for the few readers that need it (video compose, preview capture).
static bool omniPixelsStale = false;
static void omniEnsurePixels();
static bool omniSmoothDrawOn(); // OMNI_SMOOTH_DRAW_V1 (defined with the page copy)
// OMNI_PERF_A_HOOK, merge point for WS-B (ws-b-1: media/OmniHwService.h declares OmniMedia::Hw::holePunchPresenterOwnsVideo()):
// true while the presenter shows the fullscreen video by itself. Set OMNI_PERF_A_WS_B to 1 when merging with ws-b-1;
// at 0 it is always false. dl2-candidate-55 (= 54 with ws-b-1): 1.
#ifndef OMNI_PERF_A_WS_B
#define OMNI_PERF_A_WS_B 1
#endif
static bool omniPresenterOwnsVideo()
{
#if OMNI_PERF_A_WS_B
    return OmniMedia::Hw::holePunchPresenterOwnsVideo();
#else
    return false;
#endif
}
// OMNI_C56_VIDEOFIX1: while a video uses the plane, the shell keeps 54's page-paint and refresh cadence (see tick()).
// Kill switch: /data/omni/c56-videofix-disabled.flag (55/56 behaviour).
static bool omniVideoFixOn()
{
    static const bool on = access("/data/omni/c56-videofix-disabled.flag", F_OK) != 0;
    return on;
}
// OMNI_C56_VIDEOFIX2: WebKit's fullscreen media-control bar stays shown while it keeps getting mouse moves, or while the mouse
// rests on it. During a fullscreen video (a video on the plane) the shell (a) sends no mouse move whose position equals the last
// one it sent (a stick held past its dead zone with the pointer clamped at a screen edge sent one every tick), and (b) after 3 s
// without a sent mouse event tells the page once that the mouse is at the middle of the screen (the drawn pointer stays where it
// is; the next real pointer move goes to the page as usual), so the bar can fade as in 54. Kill switch:
// /data/omni/c56-videofix2-disabled.flag (= 56b).
static bool omniVideoFix2On()
{
    static const bool on = access("/data/omni/c56-videofix2-disabled.flag", F_OK) != 0;
    return on;
}
static struct { float x = -1e9f, y = -1e9f; uint32_t lastSent = 0; bool parked = false; unsigned sent = 0, dropped = 0, parks = 0; } omniFix2;
// OMNI_PERF_A_S4: page rows (in page-buffer rows) WebKit's pixels changed in since the last drawn frame.
struct OmniRows { int y0 = 0, y1 = 0; bool any() const { return y1 > y0; } void add(int a, int b) { if (b <= a) return; if (!any()) { y0 = a; y1 = b; } else { y0 = std::min(y0, a); y1 = std::max(y1, b); } } };
static OmniRows omniPageDamage;
// OMNI_PERF_A_COUNTER: aggregated over 5 s.
struct OmniDrawCensus {
    uint32_t since = 0;
    unsigned ticks = 0, draws = 0, full = 0, regional = 0, regionalRows = 0, nothing = 0, reused = 0, idle = 0, videoSkips = 0, busyKept = 0;
    unsigned reason[omniDrCount] = {};
    unsigned paints = 0, over20 = 0, over100 = 0, over400 = 0, deferred = 0, slowArmed = 0, safety = 0, safetyChanged = 0, realigns = 0, watchdog = 0, forced = 0;
    double paintMs = 0, paintMax = 0;
    unsigned whole[8] = {};   // dl2-candidate-55: S4 refused: cause, mode, sliding, overlay, layout, hover, age, allRows
};
static OmniDrawCensus omniCensus;
struct OmniDrawSplit /* OMNI_SMOOTH_DRAW_V1 */ { double fill = 0, page = 0, blit = 0, compose = 0, chrome = 0, present = 0, paint = 0; unsigned frames = 0, paints = 0, reports = 0;
    unsigned dirtyCalls = 0; double dirtyArea = 0; unsigned partial = 0, unchanged = 0; };
// OMNI_DIRTY_PAINT_V1: the union of the rects WebKit reported since the last page paint (view coordinates).
struct OmniViewDirty { bool any = false; double x0 = 0, y0 = 0, x1 = 0, y1 = 0; };
static OmniViewDirty omniViewDirty;
static OmniDrawSplit omniSplit;
static uint32_t omniLastDraw = 0, omniLastPageCopy = 0;
static const void* omniLastActive = nullptr;
SDL_Window* window = nullptr;
SDL_Surface* screen = nullptr;
SDL_Surface* canvas = nullptr;
// OMNI_SHELL_PRESENT_V1: SDL's PS5 present blocks until vblank; it runs on this thread instead
// of the UI main thread. Guarded by omniPresentLock. The thread object is never destroyed (the
// process ends with _exit), so it can't terminate the process from a static destructor.
static std::mutex omniPresentLock;
static std::condition_variable omniPresentWake, omniPresentIdle;
// Trace the existing mutex, including release/reacquire around condition waits.
// Roles: 1 UI handoff, 2 presenter, 3 shutdown. Events 100..105 are diagnostic only.
struct OmniPresentGuard {
    std::unique_lock<std::mutex> native;
    int role, operation = 0;
    explicit OmniPresentGuard(int r) : native(omniPresentLock, std::defer_lock), role(r) { lock(); }
    ~OmniPresentGuard() { if (native.owns_lock()) unlock(); }
    void event(int e) { omniPipelineScope(e, role, operation, reinterpret_cast<long long>(&omniPresentLock)); }
    void lock() { event(100); native.lock(); event(101); }
    void unlock() { event(102); native.unlock(); }
    void stage(int op) { operation = op; event(105); }
    template<typename Predicate> void wait(std::condition_variable& cv, Predicate ready) {
        while (!ready()) {
            omniPipelineScope(103, role, -1, -1);
            event(102); cv.wait(native); event(101);
        }
    }
    template<typename Predicate> bool waitFor(std::condition_variable& cv, int ms, Predicate ready) {
        const auto until = std::chrono::steady_clock::now() + std::chrono::milliseconds(ms);
        while (!ready()) {
            const auto deadline = std::chrono::duration_cast<std::chrono::microseconds>(until.time_since_epoch()).count();
            omniPipelineScope(103, role, ms, deadline);
            event(102); const auto status = cv.wait_until(native, until); event(101);
            if (status == std::cv_status::timeout) return ready();
        }
        return true;
    }
};

static std::thread* omniPresenter = nullptr;
static bool omniPresentBusy = false, omniPresentStop = false, omniPresentFailed = false;
static SDL_Rect omniPresentDamage {};          // OMNI_PERF_A_S2: rows the handed-off canvas changed (guarded by omniPresentLock)
static bool omniPresentDamaged = false;        // false: tile the whole frame
static std::atomic<uint64_t> omniVblankAt { 0 }; // OMNI_PERF_A_S8: performance counter when the presenter's last flip returned
static uint64_t omniPresents = 0, omniPresentSkips = 0;
static double omniPresentTotalMs = 0, omniPresentMaxMs = 0, omniPresentCopyMs = 0;
static unsigned omniPresentReports = 0;
SDL_Surface* pageSurface = nullptr;
SDL_GameController* controller = nullptr;
static OmniInput::ShoulderChord omniShoulderChord;
static bool omniShoulderFocused = true;
static OmniSavedLinks::TriggerGate omniSavedTriggers;
static OmniSavedLinks::DeferredExit omniSavedExit;
static uintptr_t omniSavedExitIdentity = 0;
static uint64_t omniSavedExitDocument = 0;
static int64_t omniSavedExitPad = -1;
static bool omniSavedExitPrivate = false, omniSavedKeepExitTransition = false;
static std::string omniSavedExitURL;
static bool omniLinkReviewBegin(int destination = 0); // OMNI_NET_GRABBER_V1: 0 saved view (L2), 1 share (R2 / Send current link), 2 section (L1+R1 / menu)
static bool omniGrabBegin(int destination); // OMNI_NET_GRABBER_V1
static void omniLinkReviewCancel();
static void omniLinkReviewTick();
static void omniSavedCancel() {
    omniLinkReviewCancel();
    omniSavedTriggers.cancel();
    if (!omniSavedKeepExitTransition) { omniSavedExit.cancel(); omniSavedExitURL.clear(); }
}
static void omniShoulderCancel() { omniShoulderChord.cancel(); omniSavedCancel(); }
static void omniSavedDocumentChanged(Tab&);
static void omniSavedMediaChanged(WKPageRef);
static void omniSavedLinksTick();
static bool omniSavedButton(int);
static bool omniSavedScroll(double); // OMNI_DOWNLOADS_NAV_V1
static bool omniMcButton(int); // OMNI_PAD_CONTROLLER_V1
// OMNI_MULTI_CONTROLLER_V1: every connected controller is open; `controller` is the active one
// (the last to press a button or move a stick), whose sticks drive the pointer and scrolling.
static SDL_GameController* omniPads[8] = {};
static void omniOpenPad(int deviceIndex)
{
    if (!SDL_IsGameController(deviceIndex)) return;
    SDL_JoystickID id = SDL_JoystickGetDeviceInstanceID(deviceIndex);
    for (auto* p : omniPads) if (p && SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(p)) == id) return;
    for (auto*& p : omniPads) if (!p) { p = SDL_GameControllerOpen(deviceIndex); if (p && !controller) controller = p; return; }
}
static void omniClosePad(SDL_JoystickID id)
{
    for (auto*& p : omniPads) if (p && SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(p)) == id) {
        if (controller == p) controller = nullptr;
        SDL_GameControllerClose(p); p = nullptr;
    }
    if (!controller) for (auto* p : omniPads) if (p) { controller = p; break; }
}
static void omniActivatePad(SDL_JoystickID id)
{
    if (SDL_GameController* p = SDL_GameControllerFromInstanceID(id)) controller = p;
}
#include "OmniGamepad.h" // OMNI_GAMEPAD_V1: web Gamepad API from the shell's controllers; OMNI_PAD_CONTROLLER_V1 origins
TTF_Font* font = nullptr;
TTF_Font* smallFont = nullptr;
std::vector<unsigned char> pixels(width * pageHeight * 4, 255);
bool running = true;
bool editing = false, shift = false;
bool pageEditing = false;
bool playStationIcons = false, settingsOpen = false, uiTest = false;
bool displayTest = false;
// OMNI_DISPLAY_MODE_V1: startup-only SDR resolution; a failed high-mode startup
// leaves a marker so the next launch uses 1080p until the user chooses again.
static int omniDisplayChoice = 0;
static bool omniDisplayStartupPending = false;
void log(const char* message); // defined below
static bool omniDisplayRecovered = false; // OMNI_DISPLAY_RECOVERY_CLEAR_V1: started at 1080p after an incomplete high-resolution start
static const char* const omniDisplayModes[] = { "1080", "1440", "2160" };
static const char* const omniDisplayLabels[] = { "1080p", "1440p", "4K SDR" };
static void omniDisplayPresented()
{
    if (omniDisplayStartupPending) {
        unlink("/data/omni/display-startup.pending");
        omniDisplayStartupPending = false;
    }
    // OMNI_DISPLAY_RECOVERY_CLEAR_V1: the 1080p recovery start worked, so clear the marker and let
    // the next launch retry the chosen resolution. Before this, one failed 4K start kept every
    // later launch at 1080p until the resolution was re-saved in Settings.
    if (omniDisplayRecovered) {
        unlink("/data/omni/display-startup.pending");
        omniDisplayRecovered = false;
        log("1080p recovery start succeeded; next launch retries the chosen resolution");
    }
}
bool pageFullscreen = false;
uint32_t fullscreenHintUntil = 0;
void saveControllerStyle() {
    if (FILE* file = fopen("/data/omni/controller-style.txt", "w")) {
        fputs(playStationIcons ? "playstation\n" : "xbox\n", file); fclose(file);
    }
}
// OMNI_STYLE_V1 --------------------------------------------------------------------------------
// Style refresh (REQ-9): one theme for every shell surface, rounded drawing, auto-hiding bars.
// Settings are saved like saveControllerStyle(): /data/omni/ui-theme.txt, /data/omni/ui-autohide.txt.
static int omniThemeIndex = 0;
static bool omniAutoHide = true;            // setting (on by default)
static bool omniAutoHideAllowed = false;    // off in every self-test mode: tests keep the fixed layout
static int omniSettingsRow = 0;             // 0 controller buttons, 1 theme, 2 auto-hide
static bool omniChromeWanted = true;        // the bars should be shown
static float omniChromeT = 1, omniChromeShown = 1;   // animation time and eased amount shown, 0..1
static uint32_t omniLastInput = 0;
// Scrolling (right stick, d-pad up/down) doesn't bring hidden bars back: that would push the page
// being read down by the bar height on every scroll. Set true for "any input brings them back".
constexpr bool omniScrollRevealsChrome = false;
static bool omniAutoHideActive() { return omniAutoHide && omniAutoHideAllowed; }
// While auto-hide is active the page view has the full display height and the bars are drawn over
// it, so hiding or showing them never resizes the view (no reflow, no flicker).
static int omniNormalPageHeight() { return omniAutoHideActive() ? renderHeight : physical(pageHeight); }
static float omniPageTopF() { return pageFullscreen ? 0.f : omniAutoHideActive() ? top * omniChromeShown : float(top); }
static int omniPageTop() { return int(omniPageTopF() + 0.5f); }
static int omniPageBottom() { return pageFullscreen ? height : omniAutoHideActive() ? height - int(bottom * omniChromeShown + 0.5f) : height - bottom; }
static void omniChromeWake(bool pointerMotion = false);
static void omniApplyPageHeight();
static void omniSettingsClick(int x, int y);
static void omniSettingsChange(bool right);
static OmniPlaybackHud::Panel omniStatsPanel;
static SDL_Surface* omniStatsSurface=nullptr;
static void omniStatsSet(bool enabled) {
    // One lifetime surface, backed by fixed storage. No preference or flag file.
    if (enabled && !omniStatsSurface && canvas) {
        omniStatsPanel.scale=canvas->w>=2560?3:2;
        omniStatsPanel.background=SDL_MapRGB(canvas->format,17,27,36);
        omniStatsPanel.ink=SDL_MapRGB(canvas->format,232,238,244);
        omniStatsPanel.accent=SDL_MapRGB(canvas->format,115,227,176);
        omniStatsSurface=SDL_CreateRGBSurfaceWithFormatFrom(omniStatsPanel.pixels,
            omniStatsPanel.width(),omniStatsPanel.height(),32,omniStatsPanel.width()*4,canvas->format->format);
        if(omniStatsSurface) SDL_SetSurfaceBlendMode(omniStatsSurface,SDL_BLENDMODE_NONE);
    }
    omniStatsPanel.enabled=enabled && omniStatsSurface;
    omniStatsPanel.reset();
    OmniMedia::Hw::playbackStatsEnable(omniStatsPanel.enabled);
    OmniMedia::Audio::relayHudEnable(omniStatsPanel.enabled);
    omniShellDirty=true;
}
static void omniStatsTick(uint32_t now) {
    if(!omniStatsPanel.due(now)) return;
    const auto st=OmniMedia::Hw::playbackStats();
    OmniPlaybackHud::Sample sample;
    sample.decoderErrors=st.decoderErrors;sample.completed=st.completed;sample.repeats=st.repeats;sample.drops=st.drops;
    sample.completionUs=st.completionUs;sample.width=st.width;sample.height=st.height;
    sample.codec=st.codec;sample.active=st.active;sample.decoderFailed=st.decoderFailed;
    sample.audio=OmniMedia::Audio::relayHudUnderruns();
    sample.hdr=omniHDROutputPQ(); // OMNI_HDR_PORT_V1: confirmed VideoOut range, not source bit depth.
    if(omniStatsPanel.update(now,sample))omniShellDirty=true;
}

static void saveUiTheme();
static void saveAutoHide();
uint32_t fieldClickDeadline = 0;
std::string address, status = "Ready";
uint32_t statusUntil = 0; // non-zero: transient notice, reset to "Ready" afterwards
void notice(const std::string& text) { status = text; statusUntil = SDL_GetTicks() + 3500; }
static void omniOfferTranslation(WKPageRef page); // OMNI_TRANSLATE_V1
// OMNI_DIALOGS_V1: modals and overlays (declared here, implemented after the drawing helpers) -----
// While omniKbTarget is set the on-screen keyboard (opened with pageEditing = true, so it has no
// shortcuts page) edits that string instead of the page or the address.
static std::string* omniKbTarget = nullptr;
static const char* omniKbLabel = "";
static std::function<void(bool)> omniKbDone;   // runs when the keyboard closes (Go = true, Cancel = false)
static void omniEraseLast(std::string& s)
{
    if (s.empty()) return;
    size_t i = s.size() - 1;
    while (i && (static_cast<unsigned char>(s[i]) & 0xc0) == 0x80) --i;
    s.resize(i);
}
static bool omniTestMode();
static bool omniOverlayOpen();
static bool omniOverlayButton(int button);
static bool omniOverlayClick(int x, int y);
static bool omniOverlayScroll(double amount);
static void omniOverlayDraw();
static void omniKbTargetDone(bool submitted);
static void omniModalsDropTab(const void* tab);
static void omniDialogsInstall(WKPageUIClientV19& ui);
static void omniAuthChallenge(WKPageRef page, WKAuthenticationChallengeRef challenge, const void* clientInfo);
static void omniSelectInstall();
// OMNI_EVERYDAY_V1 (declarations; implementation after the REQ-10 modals)
static Tab* omniTabForPage(WKPageRef page);
static void omniNetObserve(WKPageRef, WKURLRef, WKURLResponseRef); // OMNI_NET_GRABBER_V1
static void omniNetGrabberApply(Tab&); // OMNI_C52_FIX1: (un)install the grabber's resource-load client for one tab
static void omniNetGrabberSyncAll();   // OMNI_C52_FIX1: ... for every tab (Media downloads preference changed)
static void omniEverydayFinished(Tab& tab);
static void omniOpenNewTabPage(Tab* tab);
static void omniApplyUserAgent(Tab* tab, const std::string& url);
static void omniEverydayTabCreated(Tab* tab);
static void omniEverydayNavigation(WKPageNavigationClientV3& nav);
static void omniEverydayActivated();
static bool omniEverydayStart();
static void omniEverydayTick();
static void omniEverydayShutdown();
static void omniKbPageReset(); // OMNI_SHORTCUTS_V1
#include "OmniFeaturesDecl.h" // OMNI_FEATURES_V1: browser features (definitions in OmniFeatures.h)
#include "OmniFeatures2Decl.h" // OMNI_FEATURES_V2: passwords, file picker, permissions
#include "OmniFeatures3Decl.h" // OMNI_FEATURES_V3: star, suggestions, page tools, dark pages, tab memory
float pointerX = 640, pointerY = 360;
int keySelection = 0;
uint32_t startTime = 0;
bool savedPreview = false;
bool selfTest = false;
bool inputTest = false, inputProbePending = false;
bool googleTest = false, googleProbePending = false;
bool youtubeTest = false;
bool nativeForeground = false;
bool ipcPressureTest = false;
unsigned ipcReplies = 0, ipcErrors = 0;
bool widgetTest = false;
bool featureTest = false;
bool gamepadTest = false, padCtlTest = false; // OMNI_GAMEPAD_TEST_V1 / OMNI_PAD_CONTROLLER_TEST_V1
bool longMediaTest = false;
// Validation-only controls: keep production timing and the v139 comparison unchanged.
bool mediaMatrixTest = false;
bool mediaEnduranceTest = false;
bool mediaThirtyMinuteTest = false;
unsigned mediaMatrixCycles = 0;
bool pipelineTraceTest = false;
bool stagedMediaTest = false, stagedMediaStarted = false;
bool featureSnapshotPending = false;
unsigned featureSnapshotCount = 0;
uint32_t featureSnapshotStarted = 0;
bool mediaControlsTest = false;
bool recoveryTest = false;
int recoveryCycles = 0;
bool blockerTest = false, blockerProbePending = false;
bool grabberTest = false; // OMNI_NET_GRABBER_TEST_V1: /data/omni/grabber-selftest.flag
std::string grabberTestURL = "http://127.0.0.1:8080/fs/data/omni/grabber-test/index.html"; // OMNI_NET_GRABBER_TEST_V1
const char* blockerTestURL = "http://127.0.0.1:8080/fs/data/omni/blocker-test/index.html";
int testStage = 0;
uint32_t stageTime = 0;
const std::string keys = "1234567890qwertyuiopasdfghjkl-zxcvbnm./:@_?=&%+#!";

Tab* active() { return tabs.empty() ? nullptr : tabs[selected].get(); }
void log(const char* message) { OmniLocalScope traceScope(20); OmniMedia::Hw::shellLog(message); }

void setPageFullscreen(bool enabled)
{
    if (pageFullscreen == enabled || !active()) return;
    OmniMedia::Hw::diagnosticTrace(30,enabled,renderWidth,renderPageHeight);
    omniSavedKeepExitTransition = !enabled && omniSavedExit.active();
    omniShoulderCancel(); // OMNI_SHOULDER_DOWNLOADS_V1
    omniSavedKeepExitTransition = false;
    pageFullscreen = enabled;
    editing = pageEditing = settingsOpen = false;
    fieldClickDeadline = 0;
    renderPageHeight = enabled ? renderHeight : omniNormalPageHeight(); // OMNI_STYLE_V1
    SDL_FreeSurface(pageSurface);
    pixels.assign(size_t(renderWidth) * renderPageHeight * 4, 0);
    omniPixelsStale = false; // OMNI_PERF_A_S5
    pageSurface = SDL_CreateRGBSurfaceWithFormatFrom(pixels.data(), renderWidth, renderPageHeight, 32, renderWidth * 4, SDL_PIXELFORMAT_ARGB8888);
    if (!pageSurface) { log("fullscreen surface allocation failed"); running = false; return; }
    WKViewSetSize(active()->view.get(), omniViewSize());
    fullscreenHintUntil = SDL_GetTicks() + 3000;
    log(enabled ? "fullscreen entered" : "fullscreen exited");
    OmniMedia::Hw::diagnosticTrace(31,enabled,renderWidth,renderPageHeight);
}

void activate(size_t index)
{
    if (index >= tabs.size()) return;
    if (omniKbTarget) { omniKbTarget = nullptr; omniKbDone = nullptr; } // OMNI_DIALOGS_V1
    if (pageFullscreen && active()) { WKViewRequestExitFullScreen(active()->view.get()); setPageFullscreen(false); }
    if (active()) { WKViewSetFocus(active()->view.get(), false); WKViewSetVisible(active()->view.get(), false); }
    omniShoulderCancel(); // OMNI_SHOULDER_DOWNLOADS_V1
    selected = index;
    // A popup can be created while the old tab is fullscreen. Activation exits
    // fullscreen above, so resize the newly selected view to the restored area.
    WKViewSetSize(active()->view.get(), omniViewSize());
    editing = pageEditing = false;
    fieldClickDeadline = 0;
    status = "Ready";
    WKViewSetVisible(active()->view.get(), true);
    WKViewSetFocus(active()->view.get(), true);
    WKViewSetActive(active()->view.get(), true);
    std::fill(pixels.begin(), pixels.end(), 255);
    omniPixelsStale = false; // OMNI_PERF_A_S5: the white page is what shows until the tab's first paint
    active()->omniShownReported = false; active()->omniWaitSince = 0; active()->omniNoReportTries = 0; // OMNI_PERF_A_S1: wait for its report
    omniEverydayActivated(); // OMNI_EVERYDAY_V1: restored tabs load when first shown
    omniF3TabActivated(); // OMNI_FEATURES_V3: an unloaded tab reloads when shown
    omniSavedMediaChanged(active()->page); // Existing cached media state only.
}

std::string destination(std::string value)
{
    size_t first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return "https://example.com/";
    value = value.substr(first, value.find_last_not_of(" \t\r\n") - first + 1);
    if (value.rfind("https://", 0) == 0 || value.rfind("http://", 0) == 0) return value;
    if (value.find(' ') == std::string::npos && value.find('.') != std::string::npos && value.find("://") == std::string::npos)
        return "https://" + value;
    std::string encoded;
    for (unsigned char c : value) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_') encoded += c;
        else { char hex[4]; snprintf(hex, sizeof(hex), "%%%02X", c); encoded += hex; }
    }
    return omniFxSearchPrefix() + encoded; // OMNI_GOOGLE_SEARCH_V1 (was DuckDuckGo) OMNI_FEATURES_V1: engine setting (Google default)
}

void navigate(const std::string& input)
{
    if (!active()) return;
    omniShoulderCancel(); // OMNI_SHOULDER_DOWNLOADS_V1
    omniSavedDocumentChanged(*active());
    active()->url = destination(input);
    active()->loading = true;
    active()->message.clear();
    status = "Ready";
    omniApplyUserAgent(active(), active()->url); // OMNI_EVERYDAY_V1: desktop / mobile site
    auto url = adoptWK(WKURLCreateWithUTF8CString(active()->url.c_str()));
    WKPageLoadURL(active()->page, url.get());
    editing = false;
}

void finished(WKPageRef page, WKNavigationRef, WKTypeRef, const void* info)
{
    auto& tab = *static_cast<Tab*>(const_cast<void*>(info));
    if (omniF3TabFinished(tab)) return; // OMNI_FEATURES_V3: the blank page of an unloaded tab
    if (&tab == active()) omniShoulderCancel(); // OMNI_SHOULDER_DOWNLOADS_V1
    tab.loading = false;
    tab.loadedAt = SDL_GetTicks();
    tab.message.clear();
    tab.title = OmniTest::toStd(adoptWK(WKPageCopyTitle(page)).get());
    auto url = adoptWK(WKPageCopyActiveURL(page));
    if (url) tab.url = OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get());
    omniSavedMediaChanged(page);
    log("page loaded");
    if (&tab == active()) omniOfferTranslation(page); // OMNI_TRANSLATE_V1
    omniEverydayFinished(tab); // OMNI_EVERYDAY_V1: history, new-tab page, find bar
}
void failed(WKPageRef, WKNavigationRef, WKErrorRef error, WKTypeRef, const void* info)
{
    auto& tab = *static_cast<Tab*>(const_cast<void*>(info));
    if (&tab == active()) omniShoulderCancel(); // OMNI_SHOULDER_DOWNLOADS_V1
    auto domain = OmniTest::toStd(adoptWK(WKErrorCopyDomain(error)).get());
    auto description = OmniTest::toStd(adoptWK(WKErrorCopyLocalizedDescription(error)).get());
    int code = WKErrorGetErrorCode(error);
    if (domain == "OmniUBlockRedirect" && (description.rfind("https://", 0) == 0 || description.rfind("http://", 0) == 0)) {
        // uBlock rewrote a top-level navigation (skipped redirector / cleaned URL).
        // Guard against loops: at most 6 rewrites within 5 seconds per tab.
        uint32_t now = SDL_GetTicks();
        if (now - tab.rewriteWindowStart > 5000) { tab.rewriteWindowStart = now; tab.rewriteCount = 0; }
        if (++tab.rewriteCount <= 6) {
            tab.pendingURL = description;
            tab.url = description;
            tab.message.clear();
            fprintf(stderr, "browser: uBlock rewrote navigation -> %s\n", description.c_str());
            return;
        }
        fprintf(stderr, "browser: uBlock rewrite loop stopped at %s\n", description.c_str());
    }
    if (omniFxQuietFailure(tab, domain, code, description)) { tab.loading = false; return; } // OMNI_FEATURES_V1: Stop, link became a download
    omniSavedDocumentChanged(tab);
    tab.loading = false;
    tab.title = "Load failed";
    tab.message = domain == "OmniUBlock" && !access("/data/omni/ublock-error.flag", F_OK)
        ? "Filtering failed. Requests blocked; restart Omni to retry."
        : domain == "OmniUBlock"
        ? "uBlock blocked this page (it is on a filter list). Press Site: OFF to allow this site."
        : domain == "OmniUBlockRedirect"
        ? "Link redirected too many times. Try Reload."
        : domain == "CurlErrorDomain" && code == 60
        ? "HTTPS certificate verification failed. Connection blocked."
        : "Page failed to load. Check the address or try Reload.";
    omniFxRecordFailure(tab, error); // OMNI_FEATURES_V1: error panel (Retry / Back)
    fprintf(stderr, "browser: page failed: domain=%s code=%d description=%s\n", domain.c_str(), code, description.c_str());
    fflush(stderr);
}

Tab* newTab(WKPageConfigurationRef supplied = nullptr);
WKPageRef popup(WKPageRef page, WKPageConfigurationRef config, WKNavigationActionRef action, WKWindowFeaturesRef, const void*)
{
    std::string target, opener;
    if (auto request = adoptWK(WKNavigationActionCopyRequest(action)))
        if (auto url = adoptWK(WKURLRequestCopyURL(request.get())))
            target = OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get());
    if (auto url = adoptWK(WKPageCopyActiveURL(page)))
        opener = OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get());
    const int omniF2pp = omniF2PopupPolicy(page, opener, target, WKNavigationActionHasUnconsumedUserGesture(action)); // OMNI_FEATURES_V2: per-site Allow/Block
    if (omniF2pp == -1) { omniF2PopupBlocked(page, opener, target); return nullptr; }
    if (omniF2pp != 1 && omniBlockerEnabled() && !omniBlockerSiteTrusted(omniBlockerHostOf(opener))) {
        // New windows need a real press/click (one window per press).
        if (!WKNavigationActionHasUnconsumedUserGesture(action) && access("/data/omni/popup-gesture-off.flag", F_OK)) {
            fprintf(stderr, "browser: blocked popup without user gesture: %s\n", target.c_str());
            omniF2PopupBlocked(page, opener, target); // OMNI_FEATURES_V2
            return nullptr;
        }
        // uBlock `$popup` filters (ad / pop-under networks).
        if (target.rfind("http", 0) == 0 && omniUBlockPopupBlocked(target.c_str(), opener.c_str())) {
            fprintf(stderr, "browser: blocked ad popup: %s\n", target.c_str());
            notice("uBO blocked an ad popup");
            return nullptr;
        }
    }
    Tab* tab = newTab(config);
    if (Tab* opener = omniTabForPage(page); tab && opener) tab->omniPrivate = opener->omniPrivate; // OMNI_EVERYDAY_V1
    if (tab) omniNetGrabberApply(*tab); // OMNI_C52_FIX1: a private opener's popup loses the client before it loads
    return tab ? static_cast<WKPageRef>(WKRetain(tab->page)) : nullptr;
}

// OMNI_UBO_SITE_V1: per-site uBlock content. Before WebKit is told to go ahead with a navigation (main
// frame or subframe, and again on the response, which covers redirects), the blocker registers the
// user scripts for that host; the policy reply follows them on the same IPC connection, so they are
// in the web process before the frame's document starts. Wraps whatever the client already does
// (everyday navigation, or nothing in self-test modes). Not installed without the flag.
static void (*omniSiteNextAction)(WKPageRef, WKNavigationActionRef, WKFramePolicyListenerRef, WKTypeRef, const void*) = nullptr;
static void (*omniSiteNextResponse)(WKPageRef, WKNavigationResponseRef, WKFramePolicyListenerRef, WKTypeRef, const void*) = nullptr;
static std::string omniSiteCommittedURL(WKPageRef page)
{
    auto url = adoptWK(WKPageCopyCommittedURL(page));
    return url ? OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get()) : std::string();
}
static void omniSiteNavigation(WKPageNavigationClientV3& nav)
{
    // OMNI_C52_FIX1: not in self-test modes (their logs and the blocker self-test measure the bundle path; no
    // test wants per-site rules today), and not when the site data already failed to load (L4).
    if (omniTestMode() || !omniBlockerSiteRulesWanted()) return;
    omniSiteNextAction = nav.decidePolicyForNavigationAction;
    omniSiteNextResponse = nav.decidePolicyForNavigationResponse;
    nav.decidePolicyForNavigationAction = [](WKPageRef page, WKNavigationActionRef action, WKFramePolicyListenerRef listener, WKTypeRef userData, const void* info) {
        if (omniBlockerSiteActive()) { // OMNI_C52_FIX1: nothing is copied while the full bundle (or nothing) is in use
            auto target = adoptWK(WKNavigationActionCopyTargetFrameInfo(action));
            auto request = adoptWK(WKNavigationActionCopyRequest(action));
            auto url = request ? adoptWK(WKURLRequestCopyURL(request.get())) : WKRetainPtr<WKURLRef>();
            if (url) {
                const bool subframe = target && !WKFrameInfoGetIsMainFrame(target.get());
                Tab* tab = omniTabForPage(page);
                omniBlockerPrepareSite(OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get()), subframe ? omniSiteCommittedURL(page) : std::string(), subframe,
                    !tab || tab->omniPrivate);
            }
        }
        if (omniSiteNextAction) omniSiteNextAction(page, action, listener, userData, info);
        else WKFramePolicyListenerUse(listener);
    };
    nav.decidePolicyForNavigationResponse = [](WKPageRef page, WKNavigationResponseRef navigationResponse, WKFramePolicyListenerRef listener, WKTypeRef userData, const void* info) {
        if (omniBlockerSiteActive()) { // OMNI_C52_FIX1
            auto response = adoptWK(WKNavigationResponseCopyResponse(navigationResponse));
            auto frame = adoptWK(WKNavigationResponseCopyFrameInfo(navigationResponse));
            auto url = response ? adoptWK(WKURLResponseCopyURL(response.get())) : WKRetainPtr<WKURLRef>();
            if (url) {
                const bool subframe = frame && !WKFrameInfoGetIsMainFrame(frame.get());
                Tab* tab = omniTabForPage(page);
                omniBlockerPrepareSite(OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get()), subframe ? omniSiteCommittedURL(page) : std::string(), subframe,
                    !tab || tab->omniPrivate);
            }
        }
        if (omniSiteNextResponse) omniSiteNextResponse(page, navigationResponse, listener, userData, info);
        else WKFramePolicyListenerUse(listener);
    };
}

Tab* newTab(WKPageConfigurationRef supplied)
{
    if (!omniF3TabAllowed()) return nullptr; // OMNI_FEATURES_V3: tab limit setting (default 4) + memory guard (was a fixed four-tab limit)
    auto config = supplied ? WKRetainPtr<WKPageConfigurationRef>(supplied) : adoptWK(WKPageConfigurationCreate());
    if (!supplied) {
        WKPageConfigurationSetContext(config.get(), context.get());
        WKPageConfigurationSetPreferences(config.get(), preferences.get());
        WKPageConfigurationSetWebsiteDataStore(config.get(), websiteDataStore.get());
    }
    WKPageConfigurationSetUserContentController(config.get(), omniBlockerController());
    auto tab = std::make_unique<Tab>();
    tab->view = adoptWK(WKViewCreate(config.get()));
    tab->page = WKViewGetPage(tab->view.get());
    WKViewClientV0 viewClient {};
    viewClient.base.version = 0; viewClient.base.clientInfo = tab.get();
    viewClient.enterFullScreen = [](WKViewRef, const void* info) { if (info == active()) setPageFullscreen(true); };
    viewClient.beganEnterFullScreen = [](WKViewRef, WKRect, WKRect, const void*) { };
    viewClient.exitFullScreen = [](WKViewRef, const void* info) { if (info == active()) setPageFullscreen(false); };
    viewClient.closeFullScreen = viewClient.exitFullScreen;
    viewClient.beganExitFullScreen = [](WKViewRef, WKRect, WKRect, const void* info) { if (info == active()) setPageFullscreen(false); };
    viewClient.setViewNeedsDisplay = [](WKViewRef, WKRect r, const void* info) {   // OMNI_SHELL_DRAW_V1 OMNI_SMOOTH_DRAW_V1
        if (info != active()) return;
        { Tab* t = active(); t->omniShownReported = t->omniEverReported = true; t->omniNoReportTries = 0; } // OMNI_PERF_A_S1
        ++omniSplit.dirtyCalls; omniSplit.dirtyArea += r.size.width * r.size.height;
        // OMNI_DIRTY_PAINT_V1: remember where; the next tick repaints only that (other causes still set omniPageDirty)
        auto& d = omniViewDirty; const double x0 = r.origin.x, y0 = r.origin.y, x1 = x0 + r.size.width, y1 = y0 + r.size.height;
        if (!d.any) d = { true, x0, y0, x1, y1 };
        else { d.x0 = std::min(d.x0, x0); d.y0 = std::min(d.y0, y0); d.x1 = std::max(d.x1, x1); d.y1 = std::max(d.y1, y1); }
    };
    WKViewSetViewClient(tab->view.get(), &viewClient.base);
    WKViewSetSize(tab->view.get(), omniViewSize());
    WKPageSetPageZoomFactor(tab->page, displayScale * omniPageScale); // OMNI_FAST_PAGE_V1
    auto userAgent = adoptWK(WKStringCreateWithUTF8CString("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"));
    WKPageSetCustomUserAgent(tab->page, userAgent.get());
    WKPageNavigationClientV3 nav {}; // OMNI_EVERYDAY_V1: V3 adds navigationResponseDidBecomeDownload
    nav.base.version = 3; nav.base.clientInfo = tab.get();
    nav.didFinishNavigation = finished;
    nav.didSameDocumentNavigation = [](WKPageRef page, WKNavigationRef, WKSameDocumentNavigationType, WKTypeRef, const void*) {
        if (auto* tab = omniTabForPage(page)) {
            omniSavedDocumentChanged(*tab);
            tab->omniNetRing.newEpoch(); // OMNI_NET_GRABBER_V1: SPA video change ranks newer manifests first
            if (!tab->omniPrivate) if (auto url = adoptWK(WKPageCopyActiveURL(page)))
                tab->url = OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get());
        }
    };
    nav.didStartProvisionalNavigation = [](WKPageRef, WKNavigationRef, WKTypeRef, const void* info) {
        auto& tab = *static_cast<Tab*>(const_cast<void*>(info));
        if (&tab == active()) omniShoulderCancel(); // OMNI_SHOULDER_DOWNLOADS_V1
        omniSavedDocumentChanged(tab);
        tab.loading = true;
        tab.crashed = false;
        tab.message.clear();
        if (featureTest) log("FEATURE DIAG: provisional navigation started");
    };
    if (featureTest) nav.didCommitNavigation = [](WKPageRef, WKNavigationRef, WKTypeRef, const void*) {
        log("FEATURE DIAG: navigation committed");
    };
    nav.didFailNavigation = failed; nav.didFailProvisionalNavigation = failed;
    nav.didReceiveAuthenticationChallenge = omniAuthChallenge; // OMNI_DIALOGS_V1: HTTP sign-in; server trust rejected as before
    nav.webProcessDidCrash = [](WKPageRef, const void* info) {
        auto& tab = *static_cast<Tab*>(const_cast<void*>(info));
        tab.loading = false;
        tab.crashed = true;
        tab.message = "Page process stopped. Try Reload.";
        omniModalsDropTab(&tab); // OMNI_DIALOGS_V1
        if (&tab == active()) {
            // The dead renderer cannot complete a fullscreen-exit handshake.
            // Restore chrome locally so Reload and the other tabs remain usable.
            setPageFullscreen(false);
            editing = pageEditing = false; fieldClickDeadline = 0;
        }
        log("web process crashed");
    };
    omniEverydayNavigation(nav); // OMNI_EVERYDAY_V1: UA per site, downloads, site zoom (not in self-test modes)
    omniSiteNavigation(nav); // OMNI_UBO_SITE_V1 (only with /data/omni/ubo-site-rules.flag)
    WKPageSetPageNavigationClient(tab->page, &nav.base);
    WKPageStateClientV0 state {};
    state.base.version = 0; state.base.clientInfo = tab.get();
    state.didChangeTitle = [](const void* info) {
        auto& tab = *static_cast<Tab*>(const_cast<void*>(info));
        if (tab.message.empty()) tab.title = OmniTest::toStd(adoptWK(WKPageCopyTitle(tab.page)).get());
    };
    WKPageSetPageStateClient(tab->page, &state.base);
    omniEverydayTabCreated(tab.get()); // OMNI_EVERYDAY_V1: find client
    WKPageUIClientV19 ui {}; ui.base.version = 19; ui.createNewPage = popup;
    omniDialogsInstall(ui); // OMNI_DIALOGS_V1: alert/confirm/prompt/beforeunload, <select> menus
    ui.addMessageToConsole = [](WKPageRef, WKStringRef message, const void*) {
        auto text = OmniTest::toStd(message);
        if (widgetTest || featureTest) log(("widget console: " + text).c_str());
        else if (text.rfind("OMNI_", 0) == 0) log(("page: " + text.substr(0, 400)).c_str());
    };
    // Local WebKit forwards audio OR video state changes through this V19 slot.
    ui.isPlayingAudioDidChange = [](WKPageRef page, const void*) { omniSavedMediaChanged(page); };
    omniF2InstallUI(ui); // OMNI_FEATURES_V2: file chooser + site permissions
    WKPageSetPageUIClient(tab->page, &ui.base);
    if (widgetTest || featureTest) {
        WKPageResourceLoadClientV0 resources {};
        resources.didCompleteWithError = [](const void*, WKPageRef, WKURLRef original, WKURLResponseRef, WKErrorRef error) {
            auto url = OmniTest::toStd(adoptWK(WKURLCopyString(original)).get());
            if (featureTest) {
                auto path = url.find("/fs/data/omni/");
                if (path == std::string::npos) return;
                auto name = url.substr(path + 14);
                if (name != "feature-test.html" && name != "media-test.mp4" && name != "media-test.webm") return;
                fprintf(stderr, "FEATURE DIAG: resource complete name=%s error=%d\n", name.c_str(), error ? WKErrorGetErrorCode(error) : 0);
                fflush(stderr);
                return;
            }
            if (!error) return;
            auto domain = OmniTest::toStd(adoptWK(WKErrorCopyDomain(error)).get());
            auto description = OmniTest::toStd(adoptWK(WKErrorCopyLocalizedDescription(error)).get());
            fprintf(stderr, "widget resource failed: %s domain=%s code=%d description=%s\n", url.c_str(), domain.c_str(), WKErrorGetErrorCode(error), description.c_str()); fflush(stderr);
        };
        WKPageSetResourceLoadClient(tab->page, &resources.base);
    } else omniNetGrabberApply(*tab); // OMNI_C52_FIX1: only with Media downloads on (or the grabber self-test); private tabs drop it below
    tabs.push_back(std::move(tab));
    activate(tabs.size() - 1);
    log("tab created");
    return active();
}

void closeTab()
{
    if (!active()) return;
    if (pageFullscreen) { WKViewRequestExitFullScreen(active()->view.get()); setPageFullscreen(false); }
    omniModalsDropTab(active()); // OMNI_DIALOGS_V1: answer its dialogs / sign-in first
    omniFxTabClosing(*active()); // OMNI_FEATURES_V1: reopen closed tab
    WKPageClose(active()->page);
    tabs.erase(tabs.begin() + selected);
    if (tabs.empty()) { selected = 0; newTab(); if (omniTestMode()) navigate("https://example.com/"); else omniOpenNewTabPage(active()); } // OMNI_EVERYDAY_V1
    else { selected = std::min(selected, tabs.size() - 1); activate(selected); }
    log("tab closed");
}
// OMNI_KEYBOARD_V2 ------------------------------------------------------------------------------
// Controller-first keyboard: a real caret (L1/R1 by character, L2/R2 by word, right stick), text
// selection, an internal clipboard, undo, three layers (letters, symbols, number pad), quick keys per
// field type, hold-to-repeat, and a preview of the text being edited. The address and dialog fields
// are edited here (std::string + caret); webpage fields are edited with WebKit editing commands and
// mirrored into the preview by a small read-only script after each change.
enum { omniKbInsert = 0, omniKbShiftKey, omniKbLayerKey, omniKbToolsKey, omniKbSpaceKey, omniKbBackKey, omniKbGoKey,
    omniKbCloseKey, omniKbSitesKey, omniKbSelectKey, omniKbAllKey, omniKbCutKey, omniKbCopyKey, omniKbPasteKey,
    omniKbUndoKey, omniKbHomeKey, omniKbEndKey, omniKbDelWordKey, omniKbClearKey, omniKbNewlineKey };
enum { omniKbLetters = 0, omniKbSymbols = 1, omniKbNumpad = 2 };
enum { omniKbFieldText = 0, omniKbFieldUrl, omniKbFieldEmail, omniKbFieldNumber, omniKbFieldSearch, omniKbFieldPassword, omniKbFieldMulti };
struct OmniKbKey { std::string label, insert; int action; float units; };
struct OmniKbUndo { std::string text; size_t caret, anchor; };
struct OmniKbState {
    int session = 0;              // bumped whenever the keyboard opens or its target changes
    int kind = -1;                // -1 closed, 0 address, 1 webpage field, 2 dialog field (omniKbTarget)
    const void* target = nullptr;
    int field = omniKbFieldText, layer = omniKbLetters;
    int caps = 0;                 // 0 off, 1 next letter only, 2 caps lock
    bool tools = false, select = false;
    int row = 1, col = 0;         // focused key
    size_t caret = 0, anchor = 0; // byte offsets (address / dialog field); anchor != caret: selection
    std::vector<OmniKbUndo> undo;
    // Webpage field mirror (read back by omniKbProbe()).
    bool mirrorValid = false, mirrorNoSel = false, fieldKnown = false, contentEditable = false, backward = false;
    std::string before, selected, after, enterHint;
    int estFromEnd = 0;           // fields without a selection API (email, number): caret estimate, code points from the end
    bool probing = false, probeAgain = false, probeFirst = false;
};
static OmniKbState omniKb;
static std::string omniKbClipboard;
void editAddress() { address = active() ? active()->url : ""; pageEditing = false; editing = true; keySelection = 0; fieldClickDeadline = 0; omniKbPageReset(); omniKb.kind = -1; } // OMNI_SHORTCUTS_V1 OMNI_KEYBOARD_V2
void editPage() { editing = pageEditing = true; keySelection = 0; fieldClickDeadline = 0; omniKb.kind = -1; } // OMNI_KEYBOARD_V2
void dismissKeyboard() {
    if (omniKbTarget) { omniKbTargetDone(false); return; } // OMNI_DIALOGS_V1
    // Keep the webpage field and its suggestions intact; never send Enter.
    editing = pageEditing = false;
    fieldClickDeadline = 0;
}

// OMNI_SHORTCUTS_V1 ----------------------------------------------------------------------------
// Saved sites on the keyboard's second page. Tile 0 is "+ Add this site"; tiles 1..19 are sites.
static std::vector<std::pair<std::string, std::string>> omniShortcuts; // url, title
static bool omniShortcutsLoaded = false;
static int omniKbPage = 0;          // 0 = letters, 1 = shortcuts (address keyboard only)
static int omniShortcutSel = 0;     // 0..19 tiles, 20..25 = the action row
constexpr int omniShortcutMax = 19, omniTileCols = 4;
static void omniShortcutsLoad()
{
    if (omniShortcutsLoaded) return;
    omniShortcutsLoaded = true;
    if (FILE* f = fopen("/data/omni/shortcuts.txt", "r")) {
        char line[2400];
        while (fgets(line, sizeof(line), f) && omniShortcuts.size() < size_t(omniShortcutMax)) {
            std::string s(line);
            while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
            auto tab = s.find('\t');
            std::string url = tab == std::string::npos ? s : s.substr(0, tab);
            std::string title = tab == std::string::npos ? url : s.substr(tab + 1);
            if (!url.empty()) omniShortcuts.emplace_back(url, title.empty() ? url : title);
        }
        fclose(f);
    }
}
static void omniShortcutsSave()
{
    FILE* f = fopen("/data/omni/shortcuts.tmp", "w");
    if (!f) { notice("Couldn't save shortcuts"); return; }
    for (auto& [url, title] : omniShortcuts) {
        std::string t = title; for (auto& c : t) if (c == '\t' || c == '\n' || c == '\r') c = ' ';
        fprintf(f, "%s\t%s\n", url.c_str(), t.c_str());
    }
    fclose(f);
    rename("/data/omni/shortcuts.tmp", "/data/omni/shortcuts.txt");
}
static void omniShortcutAddCurrent()
{
    omniShortcutsLoad();
    if (!active() || active()->url.empty() || active()->url.rfind("about:", 0) == 0) { notice("No site to save"); return; }
    const std::string url = active()->url;
    std::string title = active()->title.empty() ? url : active()->title;
    for (auto& s : omniShortcuts) if (s.first == url) { notice("Already in shortcuts: " + title); return; }
    if (omniShortcuts.size() >= size_t(omniShortcutMax)) { notice("Shortcuts are full: remove one first (Square)"); return; }
    omniShortcuts.emplace_back(url, title);
    omniShortcutsSave();
    notice("Saved to shortcuts: " + title);
}
static void omniShortcutActivate(int tile)
{
    omniShortcutsLoad();
    if (tile == 0) { omniShortcutAddCurrent(); return; }
    if (tile < 1 || tile > int(omniShortcuts.size())) return;
    std::string url = omniShortcuts[tile - 1].first;
    editing = pageEditing = false; omniKbPage = 0;
    navigate(url);
}
static void omniShortcutRemove(int tile)
{
    omniShortcutsLoad();
    if (tile < 1 || tile > int(omniShortcuts.size())) return;
    std::string title = omniShortcuts[tile - 1].second;
    omniShortcuts.erase(omniShortcuts.begin() + (tile - 1));
    omniShortcutsSave();
    notice("Removed from shortcuts: " + title);
}
void pageCommand(const char* command, const std::string& value = {}) {
    if (!active()) return;
    auto name = adoptWK(WKStringCreateWithUTF8CString(command));
    auto text = adoptWK(WKStringCreateWithUTF8CString(value.c_str()));
    WKPageExecuteCommandForTesting(active()->page, name.get(), text.get());
}
// OMNI_KEYBOARD_V2: text model, webpage mirror ----------------------------------------------------
static size_t omniCpPrev(const std::string& s, size_t i)
{
    if (!i) return 0;
    if (i > s.size()) return s.size();
    --i;
    while (i && (static_cast<unsigned char>(s[i]) & 0xc0) == 0x80) --i;
    return i;
}
static size_t omniCpNext(const std::string& s, size_t i)
{
    if (i >= s.size()) return s.size();
    ++i;
    while (i < s.size() && (static_cast<unsigned char>(s[i]) & 0xc0) == 0x80) ++i;
    return i;
}
static size_t omniCpCount(const std::string& s)
{
    size_t n = 0;
    for (unsigned char c : s) n += (c & 0xc0) != 0x80;
    return n;
}
static size_t omniCpOffset(const std::string& s, size_t codePoints)   // byte offset of the n-th code point
{
    size_t i = 0;
    while (codePoints-- && i < s.size()) i = omniCpNext(s, i);
    return i;
}
// 0 space, 1 word (letters, digits, any non-ASCII), 2 punctuation: word jumps stop between classes.
static int omniKbClass(const std::string& s, size_t i)
{
    const unsigned char c = s[i];
    if (c == ' ' || c == '\t' || c == '\n' || c == '\r') return 0;
    if (c >= 0x80 || (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')) return 1;
    return 2;
}
static size_t omniKbWordLeft(const std::string& s, size_t i)
{
    while (i && omniKbClass(s, omniCpPrev(s, i)) == 0) i = omniCpPrev(s, i);
    if (!i) return 0;
    const int k = omniKbClass(s, omniCpPrev(s, i));
    while (i && omniKbClass(s, omniCpPrev(s, i)) == k) i = omniCpPrev(s, i);
    return i;
}
static size_t omniKbWordRight(const std::string& s, size_t i)
{
    while (i < s.size() && omniKbClass(s, i) == 0) i = omniCpNext(s, i);
    if (i >= s.size()) return s.size();
    const int k = omniKbClass(s, i);
    while (i < s.size() && omniKbClass(s, i) == k) i = omniCpNext(s, i);
    return i;
}
static std::string* omniKbText() { return omniKb.kind == 2 ? omniKbTarget : omniKb.kind == 0 ? &address : nullptr; }
static size_t omniKbLimit() { return omniKb.kind == 2 ? 1024 : 2048; }
static void omniKbClamp()
{
    const std::string* t = omniKbText();
    if (!t) { omniKb.caret = omniKb.anchor = 0; return; }
    for (size_t* p : { &omniKb.caret, &omniKb.anchor }) {
        if (*p > t->size()) *p = t->size();
        while (*p && *p < t->size() && (static_cast<unsigned char>((*t)[*p]) & 0xc0) == 0x80) --*p;
    }
}
static void omniKbProbe(bool first = false);
static void omniKbBegin(int kind, const void* target)
{
    omniKb.session++;
    omniKb.kind = kind; omniKb.target = target;
    omniKb.layer = omniKbLetters; omniKb.caps = 0; shift = false;
    omniKb.tools = omniKb.select = false;
    omniKb.row = 1; omniKb.col = 0;
    omniKb.undo.clear();
    omniKb.mirrorValid = omniKb.mirrorNoSel = omniKb.fieldKnown = omniKb.contentEditable = omniKb.backward = false;
    omniKb.before.clear(); omniKb.selected.clear(); omniKb.after.clear(); omniKb.enterHint.clear();
    omniKb.estFromEnd = 0;
    omniKb.field = kind == 0 ? omniKbFieldUrl : omniKbFieldText;
    if (kind == 2 && strstr(omniKbLabel, "assword")) omniKb.field = omniKbFieldPassword;
    if (kind == 0) { omniKb.caret = address.size(); omniKb.anchor = 0; }   // the whole address selected: typing replaces it
    else if (kind == 2) { omniKb.caret = omniKb.anchor = omniKbTarget ? omniKbTarget->size() : 0; }
    else { omniKb.caret = omniKb.anchor = 0; omniKbProbe(true); }
}
static int omniKbKindNow() { return omniKbTarget ? 2 : pageEditing ? 1 : 0; }
// Called by every keyboard entry point: (re)starts the session when the keyboard opened or its target changed.
static void omniKbEnsure()
{
    if (!editing) { omniKb.kind = -1; omniKb.select = false; return; }
    const int kind = omniKbKindNow();
    const void* target = kind == 2 ? static_cast<const void*>(omniKbTarget) : kind == 1 ? static_cast<const void*>(active()) : static_cast<const void*>(&address);
    if (kind != omniKb.kind || target != omniKb.target) omniKbBegin(kind, target);
    else if (kind != 1) omniKbClamp();
}
static bool omniKbAtTopRow() { return editing && omniKbPage == 0 && omniKb.row == 0; }
static int omniSuggestSelected();   // defined with the address suggestions
// Local fields ----------------------------------------------------------------------------------
static void omniKbPushUndo()
{
    const std::string* t = omniKbText();
    if (!t) return;
    if (omniKb.undo.size() >= 64) omniKb.undo.erase(omniKb.undo.begin());
    omniKb.undo.push_back({ *t, omniKb.caret, omniKb.anchor });
}
static void omniKbEraseSelection(std::string& t)
{
    const size_t a = std::min(omniKb.caret, omniKb.anchor), b = std::max(omniKb.caret, omniKb.anchor);
    t.erase(a, b - a);
    omniKb.caret = omniKb.anchor = a;
}
static void omniKbLocalInsert(const std::string& value)
{
    std::string* t = omniKbText();
    if (!t) return;
    omniKbClamp();
    const size_t sel = std::max(omniKb.caret, omniKb.anchor) - std::min(omniKb.caret, omniKb.anchor);
    if (t->size() - sel + value.size() > omniKbLimit()) { notice("The field is full"); return; }
    omniKbPushUndo();
    omniKbEraseSelection(*t);
    t->insert(omniKb.caret, value);
    omniKb.caret += value.size();
    omniKb.anchor = omniKb.caret;
}
static void omniKbLocalErase(int how)   // 0 character before, 1 word before, 2 character after
{
    std::string* t = omniKbText();
    if (!t) return;
    omniKbClamp();
    if (omniKb.caret != omniKb.anchor) { omniKbPushUndo(); omniKbEraseSelection(*t); return; }
    const size_t c = omniKb.caret;
    const size_t from = how == 2 ? c : how == 1 ? omniKbWordLeft(*t, c) : omniCpPrev(*t, c);
    const size_t to = how == 2 ? omniCpNext(*t, c) : c;
    if (from == to) return;
    omniKbPushUndo();
    t->erase(from, to - from);
    omniKb.caret = omniKb.anchor = from;
}
// Webpage fields ---------------------------------------------------------------------------------
// The probe reads the focused field (also inside same-origin frames) and returns, joined by U+001F:
// kind (input, textarea, ce, none), type, inputmode, enterkeyhint, direction ("nosel": no selection
// API), text before the selection, the selection, text after it (each at most 400 characters).
// The first probe of a session also scrolls the field above the keyboard (F = visible fraction).
static const char* const omniKbProbeScript = R"JS((function(){try{
var F=__F__,S=String.fromCharCode(31),d=document,e=d.activeElement,n=0;
while(e&&e.tagName==='IFRAME'&&n<4){try{var cd=e.contentDocument;if(!cd)break;d=cd;e=d.activeElement;n++;}catch(x){break;}}
if(!e)return 'none';
var g=function(a){return String((e.getAttribute&&e.getAttribute(a))||'').toLowerCase();};
var c=function(s){return String(s).split(S).join(' ');};
var k='none',t='',b='',m='',a='',dir='',tn=e.tagName;
if(tn==='INPUT'||tn==='TEXTAREA'){
 k=tn==='INPUT'?'input':'textarea';t=tn==='INPUT'?String(e.type||'text').toLowerCase():'textarea';
 var v=String(e.value==null?'':e.value),s=null,f=null;
 try{s=e.selectionStart;f=e.selectionEnd;dir=e.selectionDirection||'';}catch(x){s=null;}
 if(s==null||f==null){dir='nosel';b=v.slice(-800);}
 else{b=v.slice(Math.max(0,s-400),s);m=v.slice(s,f).slice(0,400);a=v.slice(f,f+400);}
}else if(e.isContentEditable){
 k='ce';t='contenteditable';
 var sel=d.getSelection?d.getSelection():null;
 if(sel&&sel.rangeCount){var r=sel.getRangeAt(0),r1=d.createRange(),r2=d.createRange();
  r1.selectNodeContents(e);r1.setEnd(r.startContainer,r.startOffset);
  r2.selectNodeContents(e);r2.setStart(r.endContainer,r.endOffset);
  b=r1.toString().slice(-400);m=r.toString().slice(0,400);a=r2.toString().slice(0,400);
  if(!r.collapsed&&sel.anchorNode===r.endContainer&&sel.anchorOffset===r.endOffset)dir='backward';}
 else b=String(e.innerText||'').slice(-400);
}
if(F>=0&&n===0&&k!=='none'&&e.getBoundingClientRect){var q=e.getBoundingClientRect(),lim=innerHeight*F;if(q.bottom>lim||q.top<0)window.scrollBy(0,q.top-lim*0.3);}
return [k,t,c(g('inputmode')),c(g('enterkeyhint')),dir,c(b),c(m),c(a)].join(S);
}catch(x){return 'none';}})())JS";
static void omniKbProbeDone(WKTypeRef result, WKErrorRef error, void* context)
{
    omniKb.probing = false;
    const bool current = editing && omniKb.kind == 1 && intptr_t(context) == omniKb.session;
    if (current) {
        std::string value = !error && result && WKGetTypeID(result) == WKStringGetTypeID() ? OmniTest::toStd(static_cast<WKStringRef>(result)) : "none";
        std::vector<std::string> part;
        size_t from = 0;
        while (part.size() < 7) {
            const size_t at = value.find('\x1f', from);
            if (at == std::string::npos) break;
            part.push_back(value.substr(from, at - from));
            from = at + 1;
        }
        part.push_back(value.substr(from));
        if (part.size() != 8 || part[0] == "none") omniKb.mirrorValid = false;
        else {
            const std::string& k = part[0], &type = part[1], &mode = part[2];
            omniKb.mirrorValid = true;
            omniKb.contentEditable = k == "ce";
            omniKb.mirrorNoSel = part[4] == "nosel";
            omniKb.backward = part[4] == "backward";
            omniKb.enterHint = part[3];
            omniKb.before = part[5]; omniKb.selected = part[6]; omniKb.after = part[7];
            if (omniKb.mirrorNoSel) {
                omniKb.estFromEnd = std::min<int>(omniKb.estFromEnd, int(omniCpCount(omniKb.before)));
                omniKb.select = false;
            }
            if (!omniKb.fieldKnown) {
                omniKb.fieldKnown = true;
                int f = omniKbFieldText;
                if (k == "textarea" || k == "ce") f = omniKbFieldMulti;
                else if (type == "email") f = omniKbFieldEmail;
                else if (type == "url") f = omniKbFieldUrl;
                else if (type == "number" || type == "tel") f = omniKbFieldNumber;
                else if (type == "search") f = omniKbFieldSearch;
                else if (type == "password") f = omniKbFieldPassword;
                if (f != omniKbFieldMulti && f != omniKbFieldPassword) {
                    if (mode == "numeric" || mode == "decimal" || mode == "tel") f = omniKbFieldNumber;
                    else if (mode == "email") f = omniKbFieldEmail;
                    else if (mode == "url") f = omniKbFieldUrl;
                    else if (mode == "search") f = omniKbFieldSearch;
                }
                omniKb.field = f;
                if (f == omniKbFieldNumber && omniKb.layer == omniKbLetters) { omniKb.layer = omniKbNumpad; omniKb.row = 0; omniKb.col = 0; }
                // No selection API (email, number): the caret position is estimated, starting at the end.
                if (omniKb.mirrorNoSel) { pageCommand("MoveToEndOfLine"); omniKb.estFromEnd = 0; }
            }
        }
        omniShellDirty = true;
    }
    if (omniKb.probeAgain) {
        omniKb.probeAgain = false;
        const bool first = omniKb.probeFirst;
        omniKb.probeFirst = false;
        omniKbProbe(first);
    }
}
static void omniKbProbe(bool first)
{
    if (!editing || omniKb.kind != 1 || !active()) return;
    if (omniKb.probing) { omniKb.probeAgain = true; omniKb.probeFirst |= first; return; }
    omniKb.probing = true;
    float fraction = -1;
    if (first && !omniTestMode()) {
        const float view = renderPageHeight / float(displayScale);
        fraction = std::clamp((keyboardY - 64 - omniPageTop()) / std::max(1.f, view), 0.1f, 1.f);
    }
    std::string js = omniKbProbeScript;
    char number[24];
    snprintf(number, sizeof(number), "%.3f", fraction);
    js.replace(js.find("__F__"), 5, number);
    auto script = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), reinterpret_cast<void*>(intptr_t(omniKb.session)), omniKbProbeDone);
}
static void omniKbPageCmd(const char* command, const std::string& value = {}) { pageCommand(command, value); omniKbProbe(); }
// Copy (and cut) for webpage fields: the selected text, or the whole value when nothing is selected.
static const char* const omniKbCopyScript = R"JS((function(){try{var d=document,e=d.activeElement,n=0;
while(e&&e.tagName==='IFRAME'&&n<4){try{var cd=e.contentDocument;if(!cd)break;d=cd;e=d.activeElement;n++;}catch(x){break;}}
if(!e)return '';
if(e.tagName==='INPUT'||e.tagName==='TEXTAREA'){if(String(e.type).toLowerCase()==='password')return '';var v=String(e.value||''),s=null,f=null;try{s=e.selectionStart;f=e.selectionEnd;}catch(x){}return (s!=null&&f>s)?v.slice(s,f):v;}
var t=d.getSelection?String(d.getSelection()):'';return t||String(e.innerText||'');}catch(x){return '';}})())JS";
static void omniKbCopy(bool cut)
{
    if (omniKb.kind == 1) {
        if (!active()) return;
        auto script = adoptWK(WKStringCreateWithUTF8CString(omniKbCopyScript));
        WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), reinterpret_cast<void*>(intptr_t(cut)), [](WKTypeRef result, WKErrorRef error, void* context) {
            std::string text = !error && result && WKGetTypeID(result) == WKStringGetTypeID() ? OmniTest::toStd(static_cast<WKStringRef>(result)) : "";
            if (text.empty()) { notice("Nothing to copy"); return; }
            omniKbClipboard = text.substr(0, 8192);
            notice(context ? "Cut" : "Copied");
        });
        // Messages reach the page in order: the script reads the selection before it is deleted.
        if (cut && omniKb.mirrorValid && !omniKb.selected.empty()) omniKbPageCmd("DeleteBackward");
        return;
    }
    std::string* t = omniKbText();
    if (!t) return;
    omniKbClamp();
    if (omniKb.field == omniKbFieldPassword) { notice("Passwords can't be copied"); return; }
    const bool sel = omniKb.caret != omniKb.anchor;
    const size_t a = sel ? std::min(omniKb.caret, omniKb.anchor) : 0, b = sel ? std::max(omniKb.caret, omniKb.anchor) : t->size();
    if (a == b) { notice("Nothing to copy"); return; }
    omniKbClipboard = t->substr(a, b - a);
    if (cut) {
        omniKbPushUndo();
        t->erase(a, b - a);
        omniKb.caret = omniKb.anchor = a;
    }
    notice(cut ? "Cut" : "Copied");
}
void submitKeyboard() {
    if (omniKbTarget) { omniKbTargetDone(true); return; } // OMNI_DIALOGS_V1
    if (!pageEditing) { navigate(address); return; }
    omniKbEnsure(); // OMNI_KEYBOARD_V2: a text area's Enter is the New line key; Go closes the keyboard
    if (omniKb.kind == 1 && omniKb.field == omniKbFieldMulti && !omniKb.contentEditable) { dismissKeyboard(); return; }
    const bool keepOpen = omniKb.kind == 1 && omniKb.contentEditable;   // editors and chat boxes: Enter, keep typing
    if (!keepOpen) editing = pageEditing = false;
    // The WPE backend expects an XKB keysym, not a Windows virtual key.
    for (auto type : { kWKEventKeyDown, kWKEventKeyUp })
        WKPageHandleKeyboardEvent(active()->page, WKKeyboardEventMake(type, kWKInputTypeNormal, "\r", 1, "Enter", 0xff0d, 0, 0, 0));
    if (keepOpen) omniKbProbe();
}
void append(const std::string& value) {
    omniKbEnsure(); // OMNI_KEYBOARD_V2: inserts at the caret (replacing a selection)
    if (omniKb.kind == 1) { omniKbPageCmd("InsertText", value); return; }
    if (omniKb.kind == 0 || omniKb.kind == 2) { omniKbLocalInsert(value); return; }
    if (omniKbTarget) { if (omniKbTarget->size() + value.size() <= 1024) *omniKbTarget += value; return; } // OMNI_DIALOGS_V1
    if (pageEditing) { pageCommand("InsertText", value); return; }
    if (address.size() + value.size() <= 2048) address += value;
}
void eraseCharacter() {
    omniKbEnsure(); // OMNI_KEYBOARD_V2: deletes before the caret (or the selection)
    if (omniKb.kind == 1) { omniKbPageCmd("DeleteBackward"); return; }
    if (omniKb.kind == 0 || omniKb.kind == 2) { omniKbLocalErase(0); return; }
    if (omniKbTarget) { omniEraseLast(*omniKbTarget); return; } // OMNI_DIALOGS_V1
    if (pageEditing) { pageCommand("DeleteBackward"); return; }
    if (address.empty()) return;
    size_t i = address.size() - 1;
    while (i && (static_cast<unsigned char>(address[i]) & 0xc0) == 0x80) --i;
    address.resize(i);
}
// OMNI_TRANSLATE_V1 ---------------------------------------------------------------------------
static const char* omniLanguageName(const std::string& code)
{
    static const std::pair<const char*, const char*> names[] = {
        {"ja","Japanese"},{"zh","Chinese"},{"ko","Korean"},{"es","Spanish"},{"fr","French"},{"de","German"},
        {"pt","Portuguese"},{"it","Italian"},{"ru","Russian"},{"ar","Arabic"},{"hi","Hindi"},{"th","Thai"},
        {"vi","Vietnamese"},{"id","Indonesian"},{"tr","Turkish"},{"pl","Polish"},{"nl","Dutch"},{"uk","Ukrainian"}};
    for (auto& [c, n] : names) if (code == c) return n;
    return nullptr;
}
static bool omniIsTranslated(const std::string& url)
{
    auto host = omniBlockerHostOf(url);
    return host.size() > 15 && host.compare(host.size() - 15, 15, ".translate.goog") == 0;
}
static void omniTranslateToggle()
{
    if (!active() || active()->url.empty()) return;
    const std::string url = active()->url;
    if (omniIsTranslated(url)) { if (WKPageCanGoBack(active()->page)) WKPageGoBack(active()->page); return; }
    if (url.rfind("http://", 0) != 0 && url.rfind("https://", 0) != 0) { notice("This page can't be translated"); return; }
    std::string encoded;
    for (unsigned char c : url) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' || c == '~') encoded += char(c);
        else { char hex[4]; snprintf(hex, sizeof(hex), "%%%02X", c); encoded += hex; }
    }
    notice("Translating with Google Translate...");
    navigate("https://translate.google.com/translate?sl=auto&tl=en&u=" + encoded);
}
static void omniOfferTranslation(WKPageRef page)
{
    auto script = adoptWK(WKStringCreateWithUTF8CString("(document.documentElement.lang||'').toLowerCase()"));
    WKPageEvaluateJavaScriptInMainFrame(page, script.get(), nullptr, [](WKTypeRef result, WKErrorRef error, void*) {
        std::string lang;
        if (!error && result && WKGetTypeID(result) == WKStringGetTypeID()) lang = OmniTest::toStd(static_cast<WKStringRef>(result));
        lang = lang.substr(0, lang.find_first_of("-_"));
        if (lang.empty() || lang == "en" || !active() || omniIsTranslated(active()->url)) return;
        const char* name = omniLanguageName(lang);
        notice(std::string("Page is in ") + (name ? name : lang.c_str()) + ": touchpad (or R3 on the shortcuts page) translates it");
    });
}
static void omniKbPageReset() { omniKbPage = 0; omniShortcutSel = 0; } // OMNI_SHORTCUTS_V1
// OMNI_KEYBOARD_V2: layout, actions, controller and USB keyboard input -----------------------------
static std::string omniKbGoLabel()
{
    if (omniKb.kind == 0) return "Go";
    if (omniKb.kind == 2) return "OK";
    if (omniKb.contentEditable) return "Enter";
    if (omniKb.field == omniKbFieldMulti) return "Done";
    const std::string& h = omniKb.enterHint;
    if (h == "search" || (h.empty() && omniKb.field == omniKbFieldSearch)) return "Search";
    if (h == "send") return "Send";
    if (h == "next") return "Next";
    if (h == "done") return "Done";
    return "Go";
}
static const char* omniKbLayerLabel()
{
    if (omniKb.layer != omniKbLetters) return "ABC";
    return omniKb.field == omniKbFieldNumber ? "123" : "#+=";
}
// Rows 0-3 characters, row 4 quick keys (or the edit tools), row 5 actions; each row is 10 units wide.
static const std::vector<std::vector<OmniKbKey>>& omniKbRows()
{
    static std::vector<std::vector<OmniKbKey>> rows;
    static std::string builtFor;
    const bool url = omniKb.kind == 0 || omniKb.field == omniKbFieldUrl, email = omniKb.field == omniKbFieldEmail;
    const std::string go = omniKbGoLabel();
    const std::string key = std::to_string(omniKb.layer) + "|" + std::to_string(omniKb.field) + "|" + std::to_string(omniKb.caps != 0)
        + "|" + std::to_string(omniKb.tools) + "|" + std::to_string(omniKb.kind == 0) + "|" + go;
    if (key == builtFor && !rows.empty()) return rows;
    builtFor = key;
    rows.assign(6, {});
    const bool upper = omniKb.caps != 0;
    auto chars = [&](std::vector<OmniKbKey>& row, const char* list, float units) {
        std::string token;
        for (const char* p = list;; ++p) {
            if (*p == ' ' || !*p) {
                if (!token.empty()) {
                    if (upper && token.size() == 1 && token[0] >= 'a' && token[0] <= 'z') token[0] = char(token[0] - 'a' + 'A');
                    row.push_back({ token, token, omniKbInsert, units });
                    token.clear();
                }
                if (!*p) break;
            } else token += *p;
        }
    };
    auto act = [](std::vector<OmniKbKey>& row, const std::string& label, int action, float units) { row.push_back({ label, "", action, units }); };
    auto text = [](std::vector<OmniKbKey>& row, const std::string& value, float units) { row.push_back({ value, value, omniKbInsert, units }); };
    if (omniKb.layer == omniKbSymbols) {
        chars(rows[0], "! @ # $ % ^ & * ( )", 1);
        chars(rows[1], "- _ = + [ ] { } \\ |", 1);
        chars(rows[2], "; : ' \" , . < > / ?", 1);
        chars(rows[3], "` ~ \xe2\x82\xac \xc2\xa3 \xc2\xa5 \xc2\xb0 \xe2\x80\xa2 \xc2\xab \xc2\xbb \xc2\xa7", 1);
    } else if (omniKb.layer == omniKbNumpad) {
        chars(rows[0], "1 2 3 + *", 2);
        chars(rows[1], "4 5 6 - /", 2);
        chars(rows[2], "7 8 9 . ,", 2);
        chars(rows[3], "( 0 ) # =", 2);
    } else {
        chars(rows[0], "1 2 3 4 5 6 7 8 9 0", 1);
        chars(rows[1], "q w e r t y u i o p", 1);
        chars(rows[2], url || email ? "a s d f g h j k l -" : "a s d f g h j k l '", 1);
        chars(rows[3], url ? "z x c v b n m . / ?" : email ? "z x c v b n m . _ @" : "z x c v b n m , . ?", 1);
    }
    auto& quick = rows[4];
    if (omniKb.tools) {
        act(quick, "Select", omniKbSelectKey, 1); act(quick, "All", omniKbAllKey, 1); act(quick, "Cut", omniKbCutKey, 1);
        act(quick, "Copy", omniKbCopyKey, 1); act(quick, "Paste", omniKbPasteKey, 1); act(quick, "Undo", omniKbUndoKey, 1);
        act(quick, "Home", omniKbHomeKey, 1); act(quick, "End", omniKbEndKey, 1); act(quick, "Del word", omniKbDelWordKey, 1);
        act(quick, "Clear", omniKbClearKey, 1);
    } else if (url) {
        if (omniKb.kind == 0) act(quick, "Sites", omniKbSitesKey, 1); else text(quick, ":", 1);
        text(quick, "https://", 2); text(quick, "www.", 1.5f); text(quick, ".com", 1.5f);
        text(quick, ".org", 1); text(quick, ".net", 1); text(quick, "=", 1); text(quick, "&", 1);
    } else if (email) {
        text(quick, "@", 1); text(quick, ".com", 1.5f); text(quick, ".net", 1.5f);
        text(quick, "@gmail.com", 3); text(quick, "@outlook.com", 3);
    } else if (omniKb.field == omniKbFieldMulti) {
        chars(quick, ", . ? ! ' \" -", 1);
        act(quick, "New line", omniKbNewlineKey, 3);
    } else chars(quick, ", . ? ! ' \" - ( ) :", 1);
    auto& action = rows[5];
    act(action, "Shift", omniKbShiftKey, 1.25f); act(action, omniKbLayerLabel(), omniKbLayerKey, 1.25f);
    act(action, "Edit", omniKbToolsKey, 1); act(action, "Space", omniKbSpaceKey, 2.5f);
    act(action, "Delete", omniKbBackKey, 1.25f); act(action, go, omniKbGoKey, 1.5f); act(action, "Close", omniKbCloseKey, 1.25f);
    return rows;
}
static void omniKbFocusClamp()
{
    const auto& rows = omniKbRows();
    omniKb.row = std::clamp(omniKb.row, 0, int(rows.size()) - 1);
    omniKb.col = std::clamp(omniKb.col, 0, int(rows[omniKb.row].size()) - 1);
}
static float omniKbKeyCentre(const std::vector<OmniKbKey>& row, int col)
{
    float u = 0;
    for (int c = 0; c < col && c < int(row.size()); ++c) u += row[c].units;
    return u + (col < int(row.size()) ? row[col].units / 2 : 0);
}
// D-pad / left stick: left and right wrap within a row; up and down wrap between the top and bottom
// rows and land on the key nearest below/above (rows have keys of different widths).
static void omniKbFocus(int dx, int dy)
{
    omniKbFocusClamp();
    const auto& rows = omniKbRows();
    if (dx) {
        const int n = int(rows[omniKb.row].size());
        omniKb.col = (omniKb.col + dx + n) % n;
    }
    if (dy) {
        const float centre = omniKbKeyCentre(rows[omniKb.row], omniKb.col);
        omniKb.row = (omniKb.row + dy + int(rows.size())) % int(rows.size());
        const auto& row = rows[omniKb.row];
        int best = 0;
        for (int c = 1; c < int(row.size()); ++c)
            if (std::fabs(omniKbKeyCentre(row, c) - centre) < std::fabs(omniKbKeyCentre(row, best) - centre)) best = c;
        omniKb.col = best;
    }
}
static void omniKbMove(int how, int dir)   // how: 0 character, 1 word, 2 line start/end
{
    omniKbEnsure();
    if (!editing || (omniKb.kind == 0 && omniKbPage == 1)) return;
    const bool extend = omniKb.select;
    if (omniKb.kind == 1) {
        if (omniKb.mirrorValid && omniKb.mirrorNoSel) {
            // No selection API: move with single steps so the estimated caret stays exact.
            const std::string& v = omniKb.before;
            const int count = int(omniCpCount(v));
            const int pos = std::clamp(count - omniKb.estFromEnd, 0, count);
            int to = pos;
            if (how == 0) to = std::clamp(pos + dir, 0, count);
            else if (how == 1) {
                const size_t at = omniCpOffset(v, size_t(pos));
                to = int(omniCpCount(v.substr(0, dir < 0 ? omniKbWordLeft(v, at) : omniKbWordRight(v, at))));
            }
            if (how == 2) { pageCommand(dir < 0 ? "MoveToBeginningOfLine" : "MoveToEndOfLine"); to = dir < 0 ? 0 : count; }
            else for (int k = 0; k < std::min(std::abs(to - pos), 400); ++k) pageCommand(to < pos ? "MoveLeft" : "MoveRight");
            omniKb.estFromEnd = count - to;
            omniKbProbe();
            return;
        }
        static const char* const names[3][2] = { { "MoveLeft", "MoveRight" }, { "MoveWordLeft", "MoveWordRight" }, { "MoveToBeginningOfLine", "MoveToEndOfLine" } };
        std::string command = names[how][dir > 0];
        if (extend) command += "AndModifySelection";
        omniKbPageCmd(command.c_str());
        return;
    }
    std::string* t = omniKbText();
    if (!t) return;
    omniKbClamp();
    if (!extend && how == 0 && omniKb.caret != omniKb.anchor) {   // collapse the selection on that side
        omniKb.caret = omniKb.anchor = dir < 0 ? std::min(omniKb.caret, omniKb.anchor) : std::max(omniKb.caret, omniKb.anchor);
        return;
    }
    const size_t c = omniKb.caret;
    omniKb.caret = how == 0 ? (dir < 0 ? omniCpPrev(*t, c) : omniCpNext(*t, c))
        : how == 1 ? (dir < 0 ? omniKbWordLeft(*t, c) : omniKbWordRight(*t, c)) : (dir < 0 ? 0 : t->size());
    if (!extend) omniKb.anchor = omniKb.caret;
}
static void omniKbDeleteWord()
{
    omniKbEnsure();
    if (omniKb.kind == 1) omniKbPageCmd("DeleteWordBackward");
    else omniKbLocalErase(1);
}
static void omniKbDeleteForward()
{
    omniKbEnsure();
    if (omniKb.kind == 1) {
        if (omniKb.mirrorNoSel && omniKb.estFromEnd > 0) --omniKb.estFromEnd;
        omniKbPageCmd("DeleteForward");
    } else omniKbLocalErase(2);
}
static void omniKbAction(int a)
{
    omniKbEnsure();
    if (!editing) return;
    std::string* t = omniKbText();
    const bool page = omniKb.kind == 1;
    switch (a) {
    case omniKbShiftKey: omniKb.caps = (omniKb.caps + 1) % 3; shift = omniKb.caps != 0; return;
    case omniKbLayerKey:
        omniKb.layer = omniKb.layer != omniKbLetters ? omniKbLetters : omniKb.field == omniKbFieldNumber ? omniKbNumpad : omniKbSymbols;
        omniKbFocusClamp();
        return;
    case omniKbToolsKey: omniKb.tools = !omniKb.tools; omniKbFocusClamp(); return;
    case omniKbSitesKey: if (omniKb.kind == 0) { omniKbPage = 1; omniShortcutSel = 0; } return;
    case omniKbSpaceKey: append(" "); return;
    case omniKbBackKey: eraseCharacter(); return;
    case omniKbGoKey: omniKb.select = false; submitKeyboard(); return;
    case omniKbCloseKey: dismissKeyboard(); return;
    case omniKbSelectKey:
        if (page && omniKb.mirrorNoSel) { notice("This field doesn't support selecting: use Del word or Clear"); return; }
        omniKb.select = !omniKb.select;
        if (omniKb.select) notice("Select: move the cursor with L1/R1 (or L2/R2) to select");
        return;
    case omniKbAllKey:
        omniKb.select = false;
        if (page) omniKbPageCmd("SelectAll");
        else if (t) { omniKb.anchor = 0; omniKb.caret = t->size(); }
        return;
    case omniKbCopyKey: case omniKbCutKey: omniKb.select = false; omniKbCopy(a == omniKbCutKey); return;
    case omniKbPasteKey: {
        if (omniKbClipboard.empty()) { notice("Nothing copied yet"); return; }
        omniKb.select = false;
        std::string value = omniKbClipboard;
        if (!page) for (auto& ch : value) if (ch == '\n' || ch == '\r' || ch == '\t') ch = ' ';
        append(value);
        return;
    }
    case omniKbUndoKey:
        omniKb.select = false;
        if (page) omniKbPageCmd("Undo");
        else if (t && !omniKb.undo.empty()) {
            *t = omniKb.undo.back().text; omniKb.caret = omniKb.undo.back().caret; omniKb.anchor = omniKb.undo.back().anchor;
            omniKb.undo.pop_back();
            omniKbClamp();
        } else notice("Nothing to undo");
        return;
    case omniKbHomeKey: omniKbMove(2, -1); return;
    case omniKbEndKey: omniKbMove(2, 1); return;
    case omniKbDelWordKey: omniKbDeleteWord(); return;
    case omniKbClearKey:
        omniKb.select = false;
        if (page) { pageCommand("SelectAll"); omniKb.estFromEnd = 0; omniKbPageCmd("DeleteBackward"); }
        else if (t && !t->empty()) { omniKbPushUndo(); t->clear(); omniKb.caret = omniKb.anchor = 0; }
        return;
    case omniKbNewlineKey: if (page) omniKbPageCmd(omniKb.contentEditable ? "InsertLineBreak" : "InsertNewline"); return;
    default: return;
    }
}
static void omniKbType(const std::string& value)
{
    append(value);
    if (omniKb.caps == 1 && value.size() == 1 && value[0] >= 'A' && value[0] <= 'Z') { omniKb.caps = 0; shift = false; }   // one-shot shift
}
static void omniKbPress(int row, int col)
{
    const auto& rows = omniKbRows();
    if (row < 0 || row >= int(rows.size()) || col < 0 || col >= int(rows[row].size())) return;
    const OmniKbKey key = rows[row][col];   // a copy: the action may rebuild the rows
    if (key.action == omniKbInsert) omniKbType(key.insert);
    else omniKbAction(key.action);
}
// Legacy key indices (0-49 the old character grid, 50-55 its action row), kept for old callers.
[[maybe_unused]] void keyboardKey(int index)
{
    if (index < 50) {
        if (index < static_cast<int>(keys.size())) {
            char c = keys[index]; if (shift && c >= 'a' && c <= 'z') c -= 'a' - 'A'; omniKbType(std::string(1, c));
        }
    } else if (index == 50) omniKbAction(omniKbShiftKey);
    else if (index == 51) omniKbAction(omniKbSpaceKey);
    else if (index == 52) omniKbAction(omniKbBackKey);
    else if (index == 53) omniKbAction(omniKbClearKey);
    else if (index == 54) omniKbAction(omniKbGoKey);
    else dismissKeyboard();
}
// Hold-to-repeat: the button pressed last repeats while it is held (driven by omniKbTick()).
static int omniKbRepeatButton = -1, omniKbRepeatCount = 0;
static uint32_t omniKbRepeatNext = 0;
static bool omniKbRepeating = false;
static bool omniKbRepeatable(int b)
{
    switch (b) {
    case SDL_CONTROLLER_BUTTON_DPAD_UP: case SDL_CONTROLLER_BUTTON_DPAD_DOWN: case SDL_CONTROLLER_BUTTON_DPAD_LEFT:
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: case SDL_CONTROLLER_BUTTON_X: case SDL_CONTROLLER_BUTTON_Y:
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: return true;
    case SDL_CONTROLLER_BUTTON_A: {   // Cross repeats on Delete, Space and Del word (not on letters)
        if (omniKb.kind == 0 && omniKbPage == 1) return false;
        omniKbFocusClamp();
        const int action = omniKbRows()[omniKb.row][omniKb.col].action;
        return action == omniKbBackKey || action == omniKbSpaceKey || action == omniKbDelWordKey;
    }
    default: return false;
    }
}
// Shortcuts page (address keyboard): tiles 0-19, then the action row 20 Letters, 21 Go, 22 Close.
static void omniKbShortcutAction(int i)
{
    if (i == 0) omniKbPageReset();
    else if (i == 1) submitKeyboard();
    else dismissKeyboard();
}
static void omniKbShortcutButton(int b)
{
    int& sel = omniShortcutSel;
    auto toAction = [](int tile) { const int col = tile % omniTileCols; return 20 + (col == 0 ? 0 : col == 3 ? 2 : 1); };
    auto toTile = [](int action, int row) { return row * omniTileCols + (action == 20 ? 0 : action == 21 ? 1 : 3); };
    switch (b) {
    case SDL_CONTROLLER_BUTTON_A: if (sel < 20) omniShortcutActivate(sel); else omniKbShortcutAction(sel - 20); break;
    case SDL_CONTROLLER_BUTTON_X: omniShortcutRemove(sel); break;
    case SDL_CONTROLLER_BUTTON_RIGHTSTICK: editing = pageEditing = false; omniKbPageReset(); omniTranslateToggle(); break; // OMNI_TRANSLATE_V1
    case SDL_CONTROLLER_BUTTON_START: submitKeyboard(); break;
    case SDL_CONTROLLER_BUTTON_Y: case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER:
    case SDL_CONTROLLER_BUTTON_TOUCHPAD: omniKbPageReset(); break;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: sel = sel < 20 ? (sel + 1) % 20 : 20 + (sel - 19) % 3; break;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: sel = sel < 20 ? (sel + 19) % 20 : 20 + (sel - 18) % 3; break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: sel = sel < 16 ? sel + omniTileCols : sel < 20 ? toAction(sel) : toTile(sel, 0); break;
    case SDL_CONTROLLER_BUTTON_DPAD_UP: sel = sel >= 20 ? toTile(sel, 4) : sel < omniTileCols ? toAction(sel) : sel - omniTileCols; break;
    default: break;
    }
}
// Every controller button while the keyboard is open (Circle and Create close it before this).
static void omniKbButton(int b)
{
    omniKbEnsure();
    if (!omniKbRepeating) {
        omniKbRepeatButton = omniKbRepeatable(b) ? b : -1;
        omniKbRepeatNext = SDL_GetTicks() + 380;
        omniKbRepeatCount = 0;
    }
    if (omniKb.kind == 0 && omniKbPage == 1) { omniKbShortcutButton(b); return; }
    switch (b) {
    case SDL_CONTROLLER_BUTTON_START: omniKbAction(omniKbGoKey); break;
    case SDL_CONTROLLER_BUTTON_A:
        omniKbFocusClamp();
        if (omniKbRepeating && omniKbRepeatCount > 12 && omniKbRows()[omniKb.row][omniKb.col].action == omniKbBackKey) omniKbDeleteWord();
        else omniKbPress(omniKb.row, omniKb.col);
        break;
    case SDL_CONTROLLER_BUTTON_X:   // Square: delete; held long, whole words
        if (omniKbRepeating && omniKbRepeatCount > 12) omniKbDeleteWord(); else eraseCharacter();
        break;
    case SDL_CONTROLLER_BUTTON_Y: append(" "); break;
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: omniKbMove(0, -1); break;
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: omniKbMove(0, 1); break;
    case SDL_CONTROLLER_BUTTON_LEFTSTICK: omniKbAction(omniKbShiftKey); break;
    case SDL_CONTROLLER_BUTTON_RIGHTSTICK: omniKbAction(omniKbLayerKey); break;
    case SDL_CONTROLLER_BUTTON_TOUCHPAD: omniKbAction(omniKb.kind == 0 ? omniKbSitesKey : omniKbToolsKey); break;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: omniKbFocus(-1, 0); break;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: omniKbFocus(1, 0); break;
    case SDL_CONTROLLER_BUTTON_DPAD_UP: omniKbFocus(0, -1); break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: omniKbFocus(0, 1); break;
    default: break;
    }
}
// Pointer clicks on the keyboard (layout coordinates).
static void omniKbClick(int x, int y)
{
    omniKbEnsure();
    if (x < keyboardX || x >= keyboardX + keyboardWidth) return;
    int r = -1;
    for (int i = 0; i < 6; ++i) { const int top = i < 5 ? keyboardY + i * keyHeight : actionY; if (y >= top && y < top + keyHeight - 4) r = i; }
    if (r < 0) return;
    if (omniKb.kind == 0 && omniKbPage == 1) { // OMNI_SHORTCUTS_V1 tiles
        if (r < 5) omniShortcutActivate(r * omniTileCols + (x - keyboardX) / (keyboardWidth / omniTileCols));
        else omniKbShortcutAction(std::min(2, (x - keyboardX) * 3 / keyboardWidth));
        return;
    }
    const auto& rows = omniKbRows();
    const float at = float(x - keyboardX) / keyWidth;
    float u = 0;
    for (int c = 0; c < int(rows[r].size()); ++c) {
        u += rows[r][c].units;
        if (at < u) { omniKb.row = r; omniKb.col = c; omniKbPress(r, c); return; }
    }
}
// A USB keyboard while the on-screen keyboard is open: arrows (Ctrl: words, Shift: select),
// Home/End, Delete, Ctrl+A/C/X/V/Z. Enter, Backspace and Escape are handled as before.
static void omniKbKey(SDL_Keycode key, Uint16 mod)
{
    omniKbEnsure();
    const bool ctrl = mod & KMOD_CTRL, shiftHeld = mod & KMOD_SHIFT;
    const bool was = omniKb.select;
    if (key == SDLK_LEFT || key == SDLK_RIGHT || key == SDLK_HOME || key == SDLK_END) {
        omniKb.select = shiftHeld && !(omniKb.kind == 1 && omniKb.mirrorNoSel);
        if (key == SDLK_LEFT || key == SDLK_RIGHT) omniKbMove(ctrl ? 1 : 0, key == SDLK_LEFT ? -1 : 1);
        else omniKbMove(2, key == SDLK_HOME ? -1 : 1);
        omniKb.select = was;
    } else if (key == SDLK_DELETE) omniKbDeleteForward();
    else if (ctrl && key == SDLK_a) omniKbAction(omniKbAllKey);
    else if (ctrl && key == SDLK_c) omniKbAction(omniKbCopyKey);
    else if (ctrl && key == SDLK_x) omniKbAction(omniKbCutKey);
    else if (ctrl && key == SDLK_v) omniKbAction(omniKbPasteKey);
    else if (ctrl && key == SDLK_z) omniKbAction(omniKbUndoKey);
}
void mouse(WKEventType type)
{
    if (omniOverlayOpen()) return; // OMNI_DIALOGS_V1: the page gets no pointer events under a modal
    int offset = omniPageTop(); // OMNI_STYLE_V1: the bars may be hidden or sliding
    if (!active() || settingsOpen || active()->crashed || pointerY < offset || pointerY >= omniPageBottom()) return;
    if (omniVideoFix2On() && pageFullscreen && OmniMedia::Hw::holePunchActive()) { // OMNI_C56_VIDEOFIX2
        if (type == kWKEventMouseMove && pointerX == omniFix2.x && pointerY == omniFix2.y) { ++omniFix2.dropped; return; }
        ++omniFix2.sent; omniFix2.parked = false; omniFix2.lastSent = SDL_GetTicks();
    }
    omniFix2.x = pointerX; omniFix2.y = pointerY;
    WKPageHandleMouseEvent(active()->page, WKMouseEventMake(type, kWKEventMouseButtonLeftButton,
        WKPointMake(pointerX * displayScale * omniPageScale, (pointerY - offset) * displayScale * omniPageScale), type == kWKEventMouseMove ? 0 : 1, 0)); // OMNI_FAST_PAGE_V1
}
void omniPageWheel(double amount)
{
    if (active()) WKPageHandleWheelEvent(active()->page, WKWheelEventMake(kWKEventWheel,
        WKPointMake(pointerX * displayScale * omniPageScale, std::clamp<double>(pointerY - omniPageTop(), 0, omniPageBottom() - omniPageTop() - 1) * displayScale * omniPageScale), // OMNI_STYLE_V1 OMNI_FAST_PAGE_V1
        WKSizeMake(0, amount * displayScale * omniPageScale), WKSizeMake(0, amount / 40), 0));
}
void scroll(double amount)
{
    if (omniOverlayScroll(amount)) return; // OMNI_DIALOGS_V1
    if (settingsOpen || pageFullscreen) return;
    if (omniSavedScroll(amount)) return; // OMNI_DOWNLOADS_NAV_V1: an open Media downloads dialog scrolls first
    omniPageWheel(amount);
}
void click()
{
    if (omniOverlayClick(int(pointerX), int(pointerY))) return; // OMNI_DIALOGS_V1
    if (!active()) return;
    if (pageFullscreen) { mouse(kWKEventMouseDown); mouse(kWKEventMouseUp); return; }
    int x = pointerX, y = pointerY;
    if (settingsOpen) { omniSettingsClick(x, y); return; } // OMNI_STYLE_V1: new panel layout
    // OMNI_STYLE_V1: `by` is y inside the top bar, which may be sliding (equals y when it is shown);
    // `top` when the pointer isn't on it.
    const int omniTop = omniPageTop(), by = y < omniTop ? y + (top - omniTop) : top;
    if (by >= 52 && by < top && x >= 1210) { settingsOpen = true; omniSettingsRow = 0; return; }
    if (editing) { omniKbClick(x, y); return; } // OMNI_KEYBOARD_V2
    if (by < 52) { // OMNI_STYLE_V1
        if (x >= 1150) {
            if (omniBlockerSetEnabled(!omniBlockerEnabled())) WKPageReload(active()->page);
            return;
        }
        if (omniF3TabStripClick(x)) return; // OMNI_FEATURES_V3: more than 4 tabs
        if (x < 100) return;
        int index = (x - 100) / 240;
        if (index < static_cast<int>(tabs.size())) { if ((x - 100) % 240 >= 208) { omniTmSkipRestore = true; activate(index); omniTmSkipRestore = false; closeTab(); } else activate(index); } // OMNI_FEATURES_V3_FIX1
        else if (x >= 1070 && x < 1180) { if (newTab()) { if (!omniTestMode()) omniOpenNewTabPage(active()); address.clear(); editing = true; omniKbPageReset(); } } // OMNI_SHORTCUTS_V1
    } else if (by < top) { // OMNI_STYLE_V1
        if (x < 64) WKPageGoBack(active()->page);
        else if (x < 120) WKPageGoForward(active()->page);
        else if (x < 176) WKPageReload(active()->page);
        else if (x >= 1104 && x < 1204) {
            // Per-site uBlock switch ("trusted site"), like uBO's power button.
            auto host = omniBlockerHostOf(active()->url);
            if (!host.empty() && omniBlockerEnabled() && omniBlockerSetSiteTrusted(host, !omniBlockerSiteTrusted(host)))
                WKPageReload(active()->page);
        }
        else if (omniF3StarClick(x, by)) { } // OMNI_FEATURES_V3: bookmark star
        else editAddress();
    } else { mouse(kWKEventMouseDown); mouse(kWKEventMouseUp); fieldClickDeadline = SDL_GetTicks() + 2000; }
}

// OMNI_STYLE_V1: theme ---------------------------------------------------------------------------
struct OmniTheme {
    const char* id; const char* name;
    SDL_Color bg, bar, line, tab, hover, field, panel, raised, key, ink, inkDim, inkFaint, accent, accentInk;
};
static const OmniTheme omniThemes[] = {
    { "dark", "Dark", {14,19,28,255}, {24,31,43,255}, {39,48,63,255}, {31,39,53,255}, {45,55,72,255}, {35,44,59,255},
      {24,31,43,255}, {38,47,63,255}, {41,51,68,255}, {233,238,246,255}, {157,169,187,255}, {98,110,128,255}, {58,212,176,255}, {6,36,30,255} },
    { "midnight", "Midnight", {3,4,7,255}, {10,12,17,255}, {26,30,38,255}, {18,21,28,255}, {32,37,47,255}, {20,24,32,255},
      {12,15,21,255}, {27,32,42,255}, {28,33,43,255}, {226,230,238,255}, {138,147,163,255}, {84,92,107,255}, {58,212,176,255}, {6,36,30,255} },
    { "playstation", "PlayStation", {6,17,40,255}, {12,29,61,255}, {30,52,92,255}, {19,39,76,255}, {31,57,104,255}, {22,44,85,255},
      {12,29,61,255}, {28,53,97,255}, {29,54,99,255}, {238,243,255,255}, {164,182,216,255}, {100,121,160,255}, {38,135,255,255}, {255,255,255,255} },
    { "purple", "Purple", {16,13,24,255}, {26,22,37,255}, {45,39,60,255}, {35,30,49,255}, {51,44,70,255}, {38,33,54,255},
      {26,22,37,255}, {45,39,63,255}, {48,41,66,255}, {239,235,247,255}, {170,161,191,255}, {108,100,128,255}, {170,132,255,255}, {26,14,52,255} },
};
constexpr int omniThemeCount = int(sizeof(omniThemes) / sizeof(omniThemes[0]));
constexpr int omniRadius = 6;   // layout px: 9 px at 1080p
static const SDL_Color omniGood {64,200,128,255}, omniBad {236,98,98,255}, omniWarn {242,181,68,255};
static const OmniTheme& omniTheme() { return omniThemes[omniThemeIndex]; }
static SDL_Color omniInk() { return omniTheme().ink; }
static SDL_Color omniMix(SDL_Color a, SDL_Color b, float t)
{
    auto m = [t](int x, int y) { return Uint8(std::clamp(x + (y - x) * t + 0.5f, 0.f, 255.f)); };
    return { m(a.r, b.r), m(a.g, b.g), m(a.b, b.b), 255 };
}

// OMNI_STYLE_V1: blending in the canvas's own pixel layout (ABGR8888 on the console). ---------------
struct OmniPix { int rs, gs, bs; uint32_t amask; bool ok; };
static OmniPix omniPix()
{
    const SDL_PixelFormat* f = canvas->format;
    return { f->Rshift, f->Gshift, f->Bshift, f->Amask, f->BytesPerPixel == 4 && !f->Rloss && !f->Gloss && !f->Bloss };
}
static inline uint32_t omniDiv255(uint32_t v) { v += 128; return (v + (v >> 8)) >> 8; }
static inline void omniBlendPx(uint32_t& px, const OmniPix& f, SDL_Color c, uint32_t a)
{
    if (!a) return;
    if (a >= 255) { px = (uint32_t(c.r) << f.rs) | (uint32_t(c.g) << f.gs) | (uint32_t(c.b) << f.bs) | f.amask; return; }
    const uint32_t r = (px >> f.rs) & 255, g = (px >> f.gs) & 255, b = (px >> f.bs) & 255, k = 255 - a;
    px = (omniDiv255(c.r * a + r * k) << f.rs) | (omniDiv255(c.g * a + g * k) << f.gs) | (omniDiv255(c.b * a + b * k) << f.bs) | f.amask;
}
// Blend towards black: every colour channel scaled by (256 - a) / 256, two multiplies per pixel
// whatever the channel order (used by shadows and the bars' soft edges).
static inline void omniDarkenPx(uint32_t& px, uint32_t amask, uint32_t a)
{
    const uint32_t k = 256 - a;
    px = ((((px & 0x00ff00ffu) * k) >> 8) & 0x00ff00ffu) | ((((px >> 8) & 0x00ff00ffu) * k) & 0xff00ff00u) | amask;
}
static inline uint32_t* omniRow(int y) { return reinterpret_cast<uint32_t*>(static_cast<uint8_t*>(canvas->pixels) + size_t(y) * canvas->pitch); }
// Physical rectangle, optionally translucent.
static void omniRectPx(SDL_Rect r, SDL_Color c, uint8_t alpha = 255)
{
    if (r.w <= 0 || r.h <= 0 || !alpha) return;
    const OmniPix f = omniPix();
    if (alpha == 255 || !f.ok) { SDL_FillRect(canvas, &r, SDL_MapRGBA(canvas->format, c.r, c.g, c.b, 255)); return; }
    const int x0 = std::max(r.x, 0), x1 = std::min(r.x + r.w, canvas->w), y0 = std::max(r.y, 0), y1 = std::min(r.y + r.h, canvas->h);
    for (int y = y0; y < y1; ++y) { uint32_t* row = omniRow(y); for (int x = x0; x < x1; ++x) omniBlendPx(row[x], f, c, alpha); }
}
// Coverage of a quarter disc (r x r pixels, 4x4 samples each), cached per radius.
static const std::vector<uint8_t>& omniCornerMask(int r)
{
    static std::unordered_map<int, std::vector<uint8_t>> cache;
    auto& mask = cache[r];
    if (mask.empty()) {
        mask.resize(size_t(r) * r);
        for (int y = 0; y < r; ++y) for (int x = 0; x < r; ++x) {
            int inside = 0;
            for (int sy = 0; sy < 4; ++sy) for (int sx = 0; sx < 4; ++sx) {
                const float dx = r - (x + (sx + 0.5f) / 4), dy = r - (y + (sy + 0.5f) / 4);
                inside += dx * dx + dy * dy <= float(r) * r;
            }
            mask[size_t(y) * r + x] = uint8_t(inside * 255 / 16);
        }
    }
    return mask;
}
enum { omniCornerTL = 1, omniCornerTR = 2, omniCornerBL = 4, omniCornerBR = 8, omniCornersTop = 3, omniCornersAll = 15 };
static void omniRoundedPx(SDL_Rect R, int r, SDL_Color c, uint8_t alpha = 255, int corners = omniCornersAll)
{
    r = std::min({ r, R.w / 2, R.h / 2 });
    const OmniPix f = omniPix();
    if (r <= 0 || !f.ok) { omniRectPx(R, c, alpha); return; }
    const int tl = corners & omniCornerTL ? r : 0, tr = corners & omniCornerTR ? r : 0;
    const int bl = corners & omniCornerBL ? r : 0, br = corners & omniCornerBR ? r : 0;
    omniRectPx({ R.x, R.y + r, R.w, R.h - 2 * r }, c, alpha);
    omniRectPx({ R.x + tl, R.y, R.w - tl - tr, r }, c, alpha);
    omniRectPx({ R.x + bl, R.y + R.h - r, R.w - bl - br, r }, c, alpha);
    const auto& mask = omniCornerMask(r);
    const uint32_t solid = (uint32_t(c.r) << f.rs) | (uint32_t(c.g) << f.gs) | (uint32_t(c.b) << f.bs) | f.amask;
    auto corner = [&](int cx, int cy, bool flipX, bool flipY) {
        for (int j = 0; j < r; ++j) {
            const int y = flipY ? cy + r - 1 - j : cy + j;
            if (y < 0 || y >= canvas->h) continue;
            uint32_t* row = omniRow(y);
            const uint8_t* m = mask.data() + size_t(j) * r;
            for (int i = 0; i < r; ++i) {
                const int x = flipX ? cx + r - 1 - i : cx + i;
                if (!m[i] || x < 0 || x >= canvas->w) continue;
                if (m[i] == 255 && alpha == 255) row[x] = solid;
                else omniBlendPx(row[x], f, c, m[i] * alpha / 255);
            }
        }
    };
    if (tl) corner(R.x, R.y, false, false);
    if (tr) corner(R.x + R.w - r, R.y, true, false);
    if (bl) corner(R.x, R.y + R.h - r, false, true);
    if (br) corner(R.x + R.w - r, R.y + R.h - r, true, true);
}
// Rounded rectangle in layout coordinates, scaled like fill(); radius in layout px.
void fillRounded(int x, int y, int w, int h, int radius, SDL_Color color, uint8_t alpha = 255, int corners = omniCornersAll)
{
    omniRoundedPx({ physical(x), physical(y), physical(w), physical(h) }, physical(radius), color, alpha, corners);
}
// Soft drop shadow of a rounded rectangle (layout coordinates), offset down by dy. Coverage and
// the runs of pixels to darken are computed once per size (4 cached); only pixels outside the
// rectangle (and in its rounded corners) are touched: the panel drawn next covers the rest.
static void omniShadow(int x, int y, int w, int h, int radius, int blur, uint8_t strength, int dy = 0)
{
    const OmniPix f = omniPix();
    if (!f.ok || !strength) return;
    struct Run { int row, from, to; };   // mask row, [from, to) columns
    struct Mask { int key[5] = {}; int ox = 0, oy = 0, w = 0; std::vector<uint8_t> a; std::vector<Run> runs; };   // ox/oy: from the rectangle
    static Mask masks[4];
    static int nextMask = 0;
    const int key[5] = { w, h, radius, blur, dy };
    const SDL_Rect R { physical(x), physical(y), physical(w), physical(h) };
    Mask* m = nullptr;
    for (auto& candidate : masks) if (!candidate.a.empty() && !memcmp(candidate.key, key, sizeof(key))) m = &candidate;
    if (!m) {
        m = &masks[nextMask];
        nextMask = (nextMask + 1) % 4;
        memcpy(m->key, key, sizeof(key));
        const float s = float(displayScale), bl = std::max(1.f, blur * s), r = radius * s;
        const int rr = std::min({ physical(radius), R.w / 2, R.h / 2 });
        const float cx = R.w / 2.f, cy = R.h / 2.f + dy * s, hw = R.w / 2.f, hh = R.h / 2.f;   // relative to the rectangle
        m->ox = int(std::floor(cx - hw - bl)); m->oy = int(std::floor(cy - hh - bl));
        m->w = int(cx + hw + bl + 1) - m->ox;
        const int rows = int(cy + hh + bl + 1) - m->oy;
        m->a.assign(size_t(m->w) * rows, 0);
        m->runs.clear();
        for (int j = 0; j < rows; ++j) {
            const int ry = m->oy + j;
            const bool covered = ry >= 0 && ry < R.h, beside = ry >= rr && ry < R.h - rr;
            int from = -1;
            for (int i = 0; i <= m->w; ++i) {
                bool use = false;
                if (i < m->w) {
                    const int rx = m->ox + i;
                    const float qx = std::max(std::fabs(rx + 0.5f - cx) - (hw - r), 0.f), qy = std::max(std::fabs(ry + 0.5f - cy) - (hh - r), 0.f);
                    const float d = std::sqrt(qx * qx + qy * qy) - r;   // distance outside the shadow's rounded rectangle
                    const float t = d <= 0 ? 1.f : std::max(0.f, 1.f - d / bl);
                    m->a[size_t(j) * m->w + i] = uint8_t(255 * t * t);
                    const bool hidden = covered && rx >= (beside ? 0 : rr) && rx < (beside ? R.w : R.w - rr);
                    use = m->a[size_t(j) * m->w + i] && !hidden;
                }
                if (use && from < 0) from = i;
                if (!use && from >= 0) { m->runs.push_back({ j, from, i }); from = -1; }
            }
        }
    }
    const int x0 = R.x + m->ox, y0 = R.y + m->oy;
    for (const Run& run : m->runs) {
        const int py = y0 + run.row;
        if (py < 0 || py >= canvas->h) continue;
        uint32_t* row = omniRow(py);
        const uint8_t* a = m->a.data() + size_t(run.row) * m->w;
        const int from = std::max(run.from, -x0), to = std::min(run.to, canvas->w - x0);
        for (int i = from; i < to; ++i) omniDarkenPx(row[x0 + i], f.amask, a[i] * strength >> 8);
    }
}
// Black gradient over whole physical rows (soft edge of the bars over the page).
static void omniFadeRows(int y, int rows, int from, int to)
{
    const OmniPix f = omniPix();
    if (!f.ok) return;
    for (int i = 0; i < rows; ++i) {
        if (y + i < 0 || y + i >= canvas->h) continue;
        const uint32_t a = uint32_t(from + (to - from) * (i + 0.5f) / rows);
        uint32_t* row = omniRow(y + i);
        if (a) for (int x = 0; x < canvas->w; ++x) omniDarkenPx(row[x], f.amask, a);
    }
}

// OMNI_STYLE_V1: UI fonts. Noto Sans JP when installed (Japanese and most CJK), else DejaVu.
// Strings with glyphs it lacks (Hangul, simplified-only Hanzi) use Noto Sans KR / SC instead.
#ifdef SDL_TTF_VERSION_ATLEAST
#if SDL_TTF_VERSION_ATLEAST(2, 0, 18)
#define OMNI_TTF_GLYPH32 1
#endif
#endif
struct OmniFace { TTF_Font* f = nullptr; int px = 0, capMid = 0, legacyShift = 0; bool bold = false, noto = false; };
enum { omniBody = 0, omniSmall = 1, omniBodyBold = 2, omniSmallBold = 3,
    omniTitle = 4, omniCaption = 5, omniCaptionBold = 6, omniFaceCount = 7 };   // OMNI_POLISH_V1: title 28, caption 14 (layout px)
static OmniFace omniFaces[omniFaceCount];
static TTF_Font* omniFallbackFaces[omniFaceCount][2] = {};
static bool omniFallbackTried[omniFaceCount][2] = {};
static bool omniGlyph(TTF_Font* f, uint32_t cp)
{
#ifdef OMNI_TTF_GLYPH32
    return TTF_GlyphIsProvided32(f, cp);
#else
    return cp <= 0xffff && TTF_GlyphIsProvided(f, Uint16(cp));
#endif
}
static void omniOpenFonts()
{
    const char* jp = "/data/omni/fonts/extra/NotoSansJP_400Regular.ttf";
    const char* jpBold = "/data/omni/fonts/extra/NotoSansJP_700Bold.ttf";
    const char* dv = "/data/omni/fonts/DejaVuSans.ttf";
    const char* dvBold = "/data/omni/fonts/DejaVuSans-Bold.ttf";
    for (int i = 0; i < omniFaceCount; ++i) { // OMNI_POLISH_V1: seven faces (was four)
        OmniFace& face = omniFaces[i];
        face.bold = i == omniBodyBold || i == omniSmallBold || i == omniTitle || i == omniCaptionBold;
        face.px = physical(i == omniBody || i == omniBodyBold ? 22 : i == omniTitle ? 28 : i >= omniCaption ? 14 : 17);   // 22/17: the sizes DejaVu had
        const char* order[] = { face.bold ? jpBold : jp, jp, face.bold ? dvBold : dv, dv };
        for (const char* path : order) {
            if (access(path, R_OK) || !(face.f = TTF_OpenFont(path, face.px))) continue;
            face.noto = path == jp || path == jpBold;
            break;
        }
        if (!face.f) continue;
        if (face.noto) TTF_SetFontHinting(face.f, TTF_HINTING_LIGHT);
        // Text is placed by the middle of its capitals, so layouts made for DejaVu keep their look.
        face.capMid = TTF_FontAscent(face.f) - int((face.noto ? 0.733f : 0.729f) * face.px / 2 + 0.5f);
        face.legacyShift = int(0.5635f * face.px + 0.5f) - face.capMid;
    }
    font = omniFaces[omniBody].f;
    smallFont = omniFaces[omniSmall].f;
    fprintf(stderr, "browser: UI font %s\n", omniFaces[omniBody].noto ? "Noto Sans JP" : "DejaVu Sans"); fflush(stderr);
}
static TTF_Font* omniFallbackFace(int id, int which)
{
    if (!omniFallbackTried[id][which]) {
        omniFallbackTried[id][which] = true;
        static const char* paths[2][2] = {
            { "/data/omni/fonts/extra/NotoSansKR_400Regular.ttf", "/data/omni/fonts/extra/NotoSansKR_700Bold.ttf" },
            { "/data/omni/fonts/extra/NotoSansSC_400Regular.ttf", "/data/omni/fonts/extra/NotoSansSC_700Bold.ttf" } };
        const char* path = paths[which][omniFaces[id].bold ? 1 : 0];
        if (!access(path, R_OK) && (omniFallbackFaces[id][which] = TTF_OpenFont(path, omniFaces[id].px)))
            TTF_SetFontHinting(omniFallbackFaces[id][which], TTF_HINTING_LIGHT);
    }
    return omniFallbackFaces[id][which];
}
// Only called when a string is rendered or measured for the first time (results are cached).
static TTF_Font* omniPickFace(int id, const std::string& value)
{
    TTF_Font* base = omniFaces[id].f;
    std::vector<uint32_t> wide;
    for (size_t i = 0; i < value.size();) {
        const unsigned char c = value[i];
        const int n = c < 0x80 ? 1 : (c >> 5) == 6 ? 2 : (c >> 4) == 14 ? 3 : (c >> 3) == 30 ? 4 : 1;
        if (n > 1 && i + n <= value.size()) {
            uint32_t cp = c & (0x7f >> n);
            for (int k = 1; k < n; ++k) cp = (cp << 6) | (static_cast<unsigned char>(value[i + k]) & 0x3f);
            wide.push_back(cp);
        }
        i += n;
    }
    if (wide.empty() || !base) return base;
    auto covers = [&](TTF_Font* f) { for (uint32_t cp : wide) if (!omniGlyph(f, cp)) return false; return true; };
    if (covers(base)) return base;
    for (int which = 0; which < 2; ++which)
        if (TTF_Font* f = omniFallbackFace(id, which); f && covers(f)) return f;
    return base;
}
static SDL_Surface* omniTextSurface(int id, const std::string& value, SDL_Color color)
{
    // OMNI_SHELL_DRAW_V1: rendering text with SDL_ttf every frame was a large part of the
    // shell's per-frame cost; keep the most recent 256 rendered strings.
    static std::unordered_map<std::string, SDL_Surface*> cache;
    static std::deque<std::string> order;
    char prefix[32];
    snprintf(prefix, sizeof(prefix), "%d|%02x%02x%02x|", id, color.r, color.g, color.b);
    std::string key = prefix + value;
    if (auto found = cache.find(key); found != cache.end()) return found->second;
    TTF_Font* face = omniPickFace(id, value);
    if (!face) return nullptr;
    color.a = 255;   // translucency is applied at blit time
    SDL_Surface* surface = TTF_RenderUTF8_Blended(face, value.c_str(), color);
    if (!surface) return nullptr;
    cache.emplace(key, surface);
    order.push_back(key);
    if (order.size() > 256) {
        auto oldest = cache.find(order.front());
        if (oldest != cache.end()) { SDL_FreeSurface(oldest->second); cache.erase(oldest); }
        order.pop_front();
    }
    return surface;
}
static int omniTextWidthPx(int id, const std::string& value)
{
    static std::unordered_map<std::string, int> widths;
    std::string key = std::to_string(id) + "|" + value;
    if (auto found = widths.find(key); found != widths.end()) return found->second;
    int w = 0, h = 0;
    if (TTF_Font* face = omniPickFace(id, value)) TTF_SizeUTF8(face, value.c_str(), &w, &h);
    if (widths.size() > 1024) widths.clear();
    widths.emplace(key, w);
    return w;
}
// The longest prefix that fits in maxPx with an ellipsis (cached).
static std::string omniFit(int id, const std::string& value, int maxPx)
{
    if (maxPx <= 0 || omniTextWidthPx(id, value) <= maxPx) return value;
    static std::unordered_map<std::string, std::string> fitted;
    std::string key = std::to_string(id) + "|" + std::to_string(maxPx) + "|" + value;
    if (auto found = fitted.find(key); found != fitted.end()) return found->second;
    TTF_Font* face = omniPickFace(id, value);
    std::vector<size_t> cuts;   // byte offsets where code points start
    for (size_t i = 0; i < value.size(); ++i) if ((static_cast<unsigned char>(value[i]) & 0xc0) != 0x80) cuts.push_back(i);
    size_t lo = 0, hi = cuts.size();
    std::string best = "...";   // ASCII: the CJK fonts draw U+2026 centred
    while (lo < hi) {
        const size_t mid = (lo + hi + 1) / 2;
        std::string candidate = value.substr(0, mid < cuts.size() ? cuts[mid] : value.size());
        while (!candidate.empty() && (candidate.back() == ' ' || candidate.back() == '-' || candidate.back() == ',' || candidate.back() == ':')) candidate.pop_back();
        candidate += "...";
        int w = 0, h = 0;
        if (face) TTF_SizeUTF8(face, candidate.c_str(), &w, &h);
        if (w <= maxPx) { lo = mid; best = candidate; } else hi = mid - 1;
    }
    if (fitted.size() > 512) fitted.clear();
    fitted.emplace(key, best);
    return best;
}
// OMNI_POLISH_V1: straight-alpha 32-bit surface (SDL_ttf Blended text, the pointer sprite) blended
// into the canvas with omniBlendPx. SDL's blend blit between ARGB8888 and the console's ABGR8888
// canvas left saturated red/yellow/green pixels on every glyph edge ("colour fringing" on the TV).
static bool omniBlendSurface(SDL_Surface* s, int x, int y, int clipW, uint8_t alpha)
{
    const OmniPix f = omniPix();
    const SDL_PixelFormat* sf = s->format;
    if (!f.ok || sf->BytesPerPixel != 4 || !sf->Amask || SDL_MUSTLOCK(s)) return false;
    const int as = sf->Ashift, rs = sf->Rshift, gs = sf->Gshift, bs = sf->Bshift;
    const int w = clipW > 0 ? std::min(clipW, s->w) : s->w;
    const int i0 = std::max(0, -x), i1 = std::min(w, canvas->w - x), j0 = std::max(0, -y), j1 = std::min(s->h, canvas->h - y);
    for (int j = j0; j < j1; ++j) {
        const uint32_t* sp = reinterpret_cast<const uint32_t*>(static_cast<const uint8_t*>(s->pixels) + size_t(j) * s->pitch);
        uint32_t* row = omniRow(y + j) + x;
        for (int i = i0; i < i1; ++i) {
            const uint32_t v = sp[i];
            uint32_t a = (v >> as) & 255;
            if (!a) continue;
            if (alpha != 255) a = omniDiv255(a * alpha);
            omniBlendPx(row[i], f, SDL_Color { Uint8((v >> rs) & 255), Uint8((v >> gs) & 255), Uint8((v >> bs) & 255), 255 }, a);
        }
    }
    return true;
}
static void omniBlitText(SDL_Surface* s, int x, int y, int clipW, uint8_t alpha)
{
    if (omniBlendSurface(s, x, y, clipW, alpha)) return; // OMNI_POLISH_V1
    SDL_Rect src { 0, 0, clipW > 0 ? std::min(clipW, s->w) : s->w, s->h };
    SDL_Rect dst { x, y, src.w, src.h };
    if (alpha != 255) SDL_SetSurfaceAlphaMod(s, alpha);
    SDL_BlitSurface(s, &src, canvas, &dst);
    if (alpha != 255) SDL_SetSurfaceAlphaMod(s, 255);
}
// A label whose capitals are centred on layout y `cy`; align 0 = starts at x, 1 = centred, 2 = ends.
// maxW (layout px, 0 = none) shortens it with an ellipsis. Returns its width in layout px.
static int omniLabel(const std::string& value, float x, float cy, int id, SDL_Color color, int align = 0, int maxW = 0, uint8_t alpha = 255)
{
    if (value.empty() || !omniFaces[id].f || !alpha) return 0;
    SDL_Surface* s = omniTextSurface(id, maxW > 0 ? omniFit(id, value, physical(maxW)) : value, color);
    if (!s) return 0;
    int px = int(x * displayScale + 0.5);
    if (align == 1) px -= s->w / 2; else if (align == 2) px -= s->w;
    omniBlitText(s, px, int(cy * displayScale + 0.5) - omniFaces[id].capMid, 0, alpha);
    return int(s->w / displayScale + 0.5);
}

// OMNI_STYLE_V1: auto-hiding bars, progress and toast animation state ----------------------------
static void omniChromeWake(bool pointerMotion)
{
    omniLastInput = SDL_GetTicks();
    if (omniChromeWanted || !omniAutoHideActive()) { omniChromeWanted = true; return; }
    // Showing the bars pushes the page down by the top bar's height. Pointer movement leaves them
    // hidden while that would push what's under the pointer off the screen (bottom of the view).
    if (pointerMotion && pointerY >= omniPageTopF() && pointerY - omniPageTopF() + top >= height - bottom) return;
    omniChromeWanted = true;
}
static void omniChromeScroll() { if (omniScrollRevealsChrome) omniChromeWake(); else omniLastInput = SDL_GetTicks(); }
static void omniChromeButton(int b)
{
    const bool scrollKey = (b == SDL_CONTROLLER_BUTTON_DPAD_UP || b == SDL_CONTROLLER_BUTTON_DPAD_DOWN) && !editing && !settingsOpen && !pageFullscreen;
    if (scrollKey) omniChromeScroll(); else omniChromeWake();
}
static void omniChromeEvent(const SDL_Event& e)
{
    if (e.type == SDL_CONTROLLERAXISMOTION) {
        if (!omniStickAxisLive(e.caxis)) return; // OMNI_STICK_DEADZONE_V1: was |value| <= 7000 (= Medium); drift keeps no bars shown
        if (e.caxis.axis == SDL_CONTROLLER_AXIS_RIGHTY) omniChromeScroll();
        else omniChromeWake(e.caxis.axis == SDL_CONTROLLER_AXIS_LEFTX || e.caxis.axis == SDL_CONTROLLER_AXIS_LEFTY);
    } else if (e.type == SDL_MOUSEMOTION) omniChromeWake(true);
    else if (e.type == SDL_MOUSEWHEEL) omniChromeScroll();
    else if (e.type == SDL_MOUSEBUTTONDOWN || e.type == SDL_KEYDOWN || e.type == SDL_TEXTINPUT) omniChromeWake();
}
static float omniProgress = 0, omniProgressAlpha = 0;
static uint32_t omniProgressDoneAt = 0;
static const void* omniProgressTab = nullptr;
static std::string omniToastText;
static uint32_t omniToastSince = 0;
static bool omniToastError = false;           // OMNI_POLISH_V1: page errors fade out after omniToastErrorMs
constexpr uint32_t omniToastErrorMs = 10000;
static void omniPolishTick(uint32_t now);     // OMNI_POLISH_V1: panel open fades, theme -> new-tab page
// Once per tick, before the page is painted: bar slide, progress bar, redraws for animations.
static void omniStyleTick()
{
    const uint32_t now = SDL_GetTicks();
    static uint32_t last = now;
    const float dt = float(std::min<uint32_t>(now - last, 100));
    last = now;
    Tab* tab = active();
    const float before = omniChromeShown;
    if (!omniAutoHideActive() || pageFullscreen) { omniChromeWanted = true; omniChromeT = omniChromeShown = 1; }
    else {
        if (editing || settingsOpen || !tab) omniChromeWanted = true;
        else if (omniChromeWanted && !tab->loading && !tab->crashed && tab->message.empty()
            && now - std::max(omniLastInput, tab->loadedAt) >= 3000 && pointerY >= top && pointerY < height - bottom)
            omniChromeWanted = false;   // 3 s without input after the page loaded, pointer not on a bar
        const float step = dt / 220.f;
        omniChromeT = omniChromeWanted ? std::min(1.f, omniChromeT + step) : std::max(0.f, omniChromeT - step);
        omniChromeShown = omniChromeT * omniChromeT * (3 - 2 * omniChromeT);
        if (omniChromeShown != before) {
            // The pointer rides with the page, so it stays on what it points at.
            if (pointerY >= top * before && !editing && !settingsOpen)
                pointerY = std::clamp(pointerY + top * (omniChromeShown - before), 0.f, float(height - 1));
            if (before >= 1) omniPageDirty = true;   // starts hiding: paint the rows the bars covered
        }
    }
    if (omniChromeShown != before) omniShellDirty = true;
    if (tab != omniProgressTab) { omniProgressTab = tab; omniProgress = omniProgressAlpha = 0; omniProgressDoneAt = 0; }
    if (tab && tab->loading && !tab->crashed) {
        const float target = std::clamp(float(WKPageGetEstimatedProgress(tab->page)), 0.1f, 1.f);
        if (omniProgressDoneAt) { omniProgress = 0; omniProgressDoneAt = 0; }   // a new load
        omniProgress = std::max(omniProgress, omniProgress + (target - omniProgress) * std::min(1.f, dt / 160.f));
        omniProgressAlpha = 1;
    } else if (omniProgressAlpha > 0) {
        omniProgress += (1 - omniProgress) * std::min(1.f, dt / 80.f);
        if (!omniProgressDoneAt) omniProgressDoneAt = now;
        if (now - omniProgressDoneAt > 200) omniProgressAlpha = std::max(0.f, omniProgressAlpha - dt / 260.f);
    }
    bool anyLoading = false;
    for (auto& t : tabs) anyLoading |= t->loading;
    // OMNI_PERF_A_HOOK (WS-B OMNI_PERF_B_V2): a fullscreen video the presenter shows by itself hides the bars, the spinner and
    // the toast (draw()'s fullscreen branch draws none of them): their animations need no 4K draw there.
    const bool omniVideoOwnsScreen = pageFullscreen && omniPresenterOwnsVideo();
    if ((anyLoading || omniProgressAlpha > 0) && now - omniLastDraw >= 33 && !omniVideoOwnsScreen) omniMarkDirty(omniDrSpinner);   // ~30 Hz spinner (OMNI_PERF_A_COUNTER: own reason)
    if (!omniToastText.empty() && !omniVideoOwnsScreen && (now - omniToastSince < 240 || (statusUntil && omniToastText == status && int32_t(statusUntil - now) < 420)))
        omniShellDirty = true;   // toast fading in or out
    if (omniToastError && !omniToastText.empty() && !omniVideoOwnsScreen && now - omniToastSince >= omniToastErrorMs - 420 && now - omniToastSince < omniToastErrorMs + 100)
        omniShellDirty = true;   // OMNI_POLISH_V1: error toast fading out
    omniPolishTick(now); // OMNI_POLISH_V1
}
// Page rows WKPagePaint has to fill: with the bars shown, the rows below the screen are skipped.
static int omniPaintRows()
{
    if (!omniAutoHideActive() || pageFullscreen || omniChromeShown < 1) return renderPageHeight;
    return std::clamp(renderHeight - physical(top), 1, renderPageHeight);
}
static void saveUiTheme()
{
    if (FILE* file = fopen("/data/omni/ui-theme.txt", "w")) { fputs(omniThemes[omniThemeIndex].id, file); fputs("\n", file); fclose(file); }
}
static void saveAutoHide()
{
    if (FILE* file = fopen("/data/omni/ui-autohide.txt", "w")) { fputs(omniAutoHide ? "on\n" : "off\n", file); fclose(file); }
}
static void omniLoadStyleSettings()
{
    if (FILE* file = fopen("/data/omni/ui-theme.txt", "r")) {
        char value[32] {};
        if (fgets(value, sizeof(value), file))
            for (int i = 0; i < omniThemeCount; ++i)
                if (!strncmp(value, omniThemes[i].id, strlen(omniThemes[i].id))) omniThemeIndex = i;
        fclose(file);
    }
    if (FILE* file = fopen("/data/omni/ui-autohide.txt", "r")) {
        char value[16] {};
        if (fgets(value, sizeof(value), file)) omniAutoHide = strncmp(value, "off", 3) != 0;
        fclose(file);
    }
    omniAutoHideAllowed = !(uiTest || displayTest || selfTest || inputTest || googleTest || youtubeTest || ipcPressureTest
        || widgetTest || featureTest || mediaControlsTest || recoveryTest || blockerTest);
    omniLastInput = SDL_GetTicks();
}
// Auto-hide switched in Settings: the page view gets the full height (or the old one) once.
static void omniApplyPageHeight()
{
    if (pageFullscreen) return;   // setPageFullscreen(false) restores omniNormalPageHeight()
    const int wanted = omniNormalPageHeight();
    if (wanted == renderPageHeight) return;
    renderPageHeight = wanted;
    SDL_FreeSurface(pageSurface);
    pixels.assign(size_t(renderWidth) * renderPageHeight * 4, 255);
    omniPixelsStale = false; // OMNI_PERF_A_S5
    pageSurface = SDL_CreateRGBSurfaceWithFormatFrom(pixels.data(), renderWidth, renderPageHeight, 32, renderWidth * 4, SDL_PIXELFORMAT_ARGB8888);
    if (!pageSurface) { log("page surface allocation failed"); running = false; return; }
    if (active()) WKViewSetSize(active()->view.get(), omniViewSize());
    omniChromeWanted = true;
    omniPageDirty = true;
}
static void omniSettingsChange(bool right)
{
    if (omniSettingsRow == 4) { omniStatsSet(right); return; }
    if (omniSettingsRow == 0) { playStationIcons = right; saveControllerStyle(); }
    else if (omniSettingsRow == 1) { omniThemeIndex = (omniThemeIndex + (right ? 1 : omniThemeCount - 1)) % omniThemeCount; saveUiTheme(); }
    else if (omniSettingsRow == 3) {
        const int next = (omniDisplayChoice + (right ? 1 : 2)) % 3;
        FILE* f = fopen("/data/omni/display-mode.txt.tmp", "w");
        if (!f) { status = "Could not save resolution"; return; }
        const bool written = fprintf(f, "%s\n", omniDisplayModes[next]) > 0;
        const bool closed = fclose(f) == 0;
        if (!written || !closed || rename("/data/omni/display-mode.txt.tmp", "/data/omni/display-mode.txt")) {
            status = "Could not save resolution"; return;
        }
        omniDisplayChoice = next;
        unlink("/data/omni/display-startup.pending");
        status = "Resolution saved. Restart Omni to apply.";
    }
    else if (omniAutoHide != right) { omniAutoHide = right; saveAutoHide(); omniApplyPageHeight(); }
}

void fill(int x, int y, int w, int h, SDL_Color color)
{
    SDL_Rect rect { physical(x), physical(y), physical(w), physical(h) };
    SDL_FillRect(canvas, &rect, SDL_MapRGBA(canvas->format, color.r, color.g, color.b, color.a));
}
void text(const std::string& value, int x, int y, int maxWidth, bool small = false, SDL_Color color = omniInk())
{
    // OMNI_STYLE_V1: same placement as before for any UI font; cached in omniTextSurface().
    const int id = small ? omniSmall : omniBody;
    if (value.empty() || !omniFaces[id].f) return;
    SDL_Surface* surface = omniTextSurface(id, value, color);
    if (!surface) return;
    omniBlitText(surface, physical(x), physical(y) + omniFaces[id].legacyShift, physical(maxWidth), color.a);
}

#include "OmniControllerIcons.h"

// OMNI_STYLE_V1: icons ---------------------------------------------------------------------------
// Signed-distance shapes in layout px, rendered once per display scale into coverage masks and
// blended in the canvas's own format (the old vector helpers wrote ARGB, swapping red and blue on
// the console's ABGR canvas).
[[maybe_unused]] static void (*const omniLegacySettingsPanel)() = settingsPanel;   // replaced by omniSettingsPanel
[[maybe_unused]] static void (*const omniLegacyIconCircle)(int, int, int, SDL_Color) = iconCircle;
static float omniSdSeg(float px, float py, float ax, float ay, float bx, float by, float r)
{
    const float pax = px - ax, pay = py - ay, bax = bx - ax, bay = by - ay;
    const float h = std::clamp((pax * bax + pay * bay) / (bax * bax + bay * bay + 1e-6f), 0.f, 1.f);
    return std::hypot(pax - bax * h, pay - bay * h) - r;
}
static float omniSdBox(float px, float py, float cx, float cy, float hw, float hh, float r)
{
    const float qx = std::fabs(px - cx) - (hw - r), qy = std::fabs(py - cy) - (hh - r);
    return std::hypot(std::max(qx, 0.f), std::max(qy, 0.f)) + std::min(std::max(qx, qy), 0.f) - r;
}
static float omniSdPoly(const SDL_FPoint* v, int n, float px, float py)
{
    float d = (px - v[0].x) * (px - v[0].x) + (py - v[0].y) * (py - v[0].y), sign = 1;
    for (int i = 0, j = n - 1; i < n; j = i++) {
        const float ex = v[j].x - v[i].x, ey = v[j].y - v[i].y, wx = px - v[i].x, wy = py - v[i].y;
        const float h = std::clamp((wx * ex + wy * ey) / (ex * ex + ey * ey + 1e-6f), 0.f, 1.f);
        const float bx = wx - ex * h, by = wy - ey * h;
        d = std::min(d, bx * bx + by * by);
        const bool c1 = py >= v[i].y, c2 = py < v[j].y, c3 = ex * wy > ey * wx;
        if ((c1 && c2 && c3) || (!c1 && !c2 && !c3)) sign = -sign;
    }
    return sign * std::sqrt(d);
}
static float omniSdShield(float x, float y)
{
    static SDL_FPoint v[32];
    static int n = 0;
    if (!n) {
        auto add = [](float px, float py) { v[n++] = { px, py }; };
        add(11, 1.2f); add(20.2f, 4.4f); add(20.2f, 11);
        for (int i = 1; i <= 8; ++i) { const float t = i / 8.f, u = 1 - t; add(u * u * 20.2f + 2 * u * t * 19.6f + t * t * 11, u * u * 11 + 2 * u * t * 20.4f + t * t * 25); }
        for (int i = 1; i <= 7; ++i) { const float t = i / 8.f, u = 1 - t; add(u * u * 11 + 2 * u * t * 2.4f + t * t * 1.8f, u * u * 25 + 2 * u * t * 20.4f + t * t * 11); }
        add(1.8f, 11); add(1.8f, 4.4f);
    }
    return omniSdPoly(v, n, x, y);
}
static float omniSdReload(float x, float y)
{
    const float cx = 12, cy = 12.5f, R = 6.8f, r = 1.25f, a1 = -1.15f, a0 = a1 - 4.9f;   // arc a0..a1, gap at the top right
    float ang = std::atan2(y - cy, x - cx);
    while (ang >= a0 + 6.2831853f) ang -= 6.2831853f;
    while (ang < a0) ang += 6.2831853f;
    float d = ang <= a1 ? std::fabs(std::hypot(x - cx, y - cy) - R) - r
        : std::min(std::hypot(x - cx - R * std::cos(a0), y - cy - R * std::sin(a0)), std::hypot(x - cx - R * std::cos(a1), y - cy - R * std::sin(a1))) - r;
    // Arrow head at the a1 end, pointing on clockwise.
    const float px = cx + R * std::cos(a1), py = cy + R * std::sin(a1), tx = -std::sin(a1), ty = std::cos(a1), nx = std::cos(a1), ny = std::sin(a1);
    const SDL_FPoint head[3] = { { px + tx * 3.6f, py + ty * 3.6f }, { px - tx * 1.2f + nx * 3.7f, py - ty * 1.2f + ny * 3.7f }, { px - tx * 1.2f - nx * 3.7f, py - ty * 1.2f - ny * 3.7f } };
    return std::min(d, omniSdPoly(head, 3, x, y) - 0.3f);
}
static float omniSdGear(float x, float y)
{
    const float dx = x - 13, dy = y - 13, dist = std::hypot(dx, dy);
    const float k = std::round(std::atan2(dy, dx) / 0.7853982f) * 0.7853982f;
    const float lx = dx * std::cos(k) + dy * std::sin(k), ly = -dx * std::sin(k) + dy * std::cos(k);
    const float body = std::min(dist - 7.8f, omniSdBox(lx, ly, 9.4f, 0, 2.5f, 2.2f, 0.8f));
    return std::max(body, -(dist - 3.4f));
}
enum { omniIconBack, omniIconForward, omniIconReload, omniIconGear, omniIconPlus, omniIconClose, omniIconLock, omniIconShield,
    omniIconShieldHole, omniIconCheck, omniIconBang, omniIconAlert, omniIconDpad, omniIconDpadV, omniIconCount };
struct OmniIconShape { float w, h; float (*sd)(float, float); };
static const OmniIconShape omniIconShapes[omniIconCount] = {
    { 24, 24, [](float x, float y) { return std::min(omniSdSeg(x, y, 14.5f, 5.5f, 8, 12, 1.3f), omniSdSeg(x, y, 8, 12, 14.5f, 18.5f, 1.3f)); } },
    { 24, 24, [](float x, float y) { return std::min(omniSdSeg(x, y, 9.5f, 5.5f, 16, 12, 1.3f), omniSdSeg(x, y, 16, 12, 9.5f, 18.5f, 1.3f)); } },
    { 24, 24, omniSdReload },
    { 26, 26, omniSdGear },
    { 20, 20, [](float x, float y) { return std::min(omniSdSeg(x, y, 10, 3.5f, 10, 16.5f, 1.3f), omniSdSeg(x, y, 3.5f, 10, 16.5f, 10, 1.3f)); } },
    { 14, 14, [](float x, float y) { return std::min(omniSdSeg(x, y, 3.5f, 3.5f, 10.5f, 10.5f, 1.15f), omniSdSeg(x, y, 10.5f, 3.5f, 3.5f, 10.5f, 1.15f)); } },
    { 14, 16, [](float x, float y) {
        const float shackle = y <= 6.5f ? std::fabs(std::hypot(x - 7, y - 6.5f) - 3.3f) - 0.85f
            : std::min(omniSdSeg(x, y, 3.7f, 6.5f, 3.7f, 8.5f, 0.85f), omniSdSeg(x, y, 10.3f, 6.5f, 10.3f, 8.5f, 0.85f));
        return std::min(shackle, omniSdBox(x, y, 7, 11.3f, 5.6f, 4.4f, 1.4f)); } },
    { 22, 26, omniSdShield },
    { 22, 26, [](float x, float y) { return omniSdShield(x, y) + 2.3f; } },
    { 22, 26, [](float x, float y) { return std::min(omniSdSeg(x, y, 6.8f, 12.8f, 9.9f, 16.2f, 1.4f), omniSdSeg(x, y, 9.9f, 16.2f, 15.4f, 9.4f, 1.4f)); } },
    { 22, 26, [](float x, float y) { return std::min(omniSdSeg(x, y, 11, 7.5f, 11, 13.6f, 1.4f), std::hypot(x - 11, y - 17.8f) - 1.6f); } },
    { 18, 18, [](float x, float y) { return std::min(omniSdSeg(x, y, 9, 4.6f, 9, 10.2f, 1.25f), std::hypot(x - 9, y - 13.4f) - 1.4f); } },
    { 24, 24, [](float x, float y) { return std::min(omniSdBox(x, y, 12, 12, 3.6f, 10.5f, 1.6f), omniSdBox(x, y, 12, 12, 10.5f, 3.6f, 1.6f)); } },
    { 24, 24, [](float x, float y) { return omniSdBox(x, y, 12, 12, 3.6f, 10.5f, 1.6f); } },
};
struct OmniIconMask { int w = 0, h = 0; std::vector<uint8_t> a; };
static const OmniIconMask& omniIconMask(int id)
{
    static OmniIconMask masks[omniIconCount];
    OmniIconMask& mask = masks[id];
    if (mask.a.empty()) {
        const OmniIconShape& shape = omniIconShapes[id];
        const float s = float(displayScale);
        mask.w = int(std::ceil(shape.w * s)); mask.h = int(std::ceil(shape.h * s));
        mask.a.resize(size_t(mask.w) * mask.h);
        for (int y = 0; y < mask.h; ++y) for (int x = 0; x < mask.w; ++x) {
            float a = 0;   // 2x2 samples of the analytic edge coverage
            for (int k = 0; k < 4; ++k)
                a += std::clamp(0.5f - 2 * s * shape.sd((x + 0.25f + 0.5f * (k & 1)) / s, (y + 0.25f + 0.5f * (k >> 1)) / s), 0.f, 1.f);
            mask.a[size_t(y) * mask.w + x] = uint8_t(a / 4 * 255 + 0.5f);
        }
    }
    return mask;
}
// Icon centred on a layout point, tinted (blended straight into the canvas).
static void omniIcon(int id, float cx, float cy, SDL_Color color, uint8_t alpha = 255)
{
    const OmniPix f = omniPix();
    if (!f.ok || !alpha) return;
    const OmniIconMask& mask = omniIconMask(id);
    const int x0 = int(cx * displayScale + 0.5) - mask.w / 2, y0 = int(cy * displayScale + 0.5) - mask.h / 2;
    for (int j = std::max(0, -y0); j < mask.h && y0 + j < canvas->h; ++j) {
        uint32_t* row = omniRow(y0 + j);
        const uint8_t* a = mask.a.data() + size_t(j) * mask.w;
        for (int i = std::max(0, -x0); i < mask.w && x0 + i < canvas->w; ++i)
            if (a[i]) omniBlendPx(row[x0 + i], f, color, alpha == 255 ? a[i] : a[i] * alpha / 255);
    }
}
static void omniDisc(float cx, float cy, float r, SDL_Color c, uint8_t alpha = 255)
{
    const OmniPix f = omniPix();
    if (!f.ok || !alpha) return;
    const float s = float(displayScale), X = cx * s, Y = cy * s, R = r * s;
    const int x0 = std::max(0, int(X - R - 1)), x1 = std::min(canvas->w, int(X + R + 2));
    const int y0 = std::max(0, int(Y - R - 1)), y1 = std::min(canvas->h, int(Y + R + 2));
    for (int y = y0; y < y1; ++y) {
        uint32_t* row = omniRow(y);
        for (int x = x0; x < x1; ++x) {
            const float cov = std::clamp(R + 0.5f - std::hypot(x + 0.5f - X, y + 0.5f - Y), 0.f, 1.f);
            if (cov > 0) omniBlendPx(row[x], f, c, uint32_t(cov * alpha));
        }
    }
}
// Loading spinner: an arc on a faint track, one turn a second.
static void omniSpinner(float cx, float cy, float r, SDL_Color c)
{
    const OmniPix f = omniPix();
    if (!f.ok) return;
    const float s = float(displayScale), X = cx * s, Y = cy * s, R = r * s, t = 1.15f * s;
    const float start = SDL_GetTicks() % 1000 / 1000.f * 6.2831853f, sweep = 4.0f;
    const float ex0 = X + R * std::cos(start), ey0 = Y + R * std::sin(start), ex1 = X + R * std::cos(start + sweep), ey1 = Y + R * std::sin(start + sweep);
    const int x0 = std::max(0, int(X - R - t - 1)), x1 = std::min(canvas->w, int(X + R + t + 2));
    const int y0 = std::max(0, int(Y - R - t - 1)), y1 = std::min(canvas->h, int(Y + R + t + 2));
    for (int y = y0; y < y1; ++y) {
        uint32_t* row = omniRow(y);
        for (int x = x0; x < x1; ++x) {
            const float dx = x + 0.5f - X, dy = y + 0.5f - Y, ring = std::fabs(std::hypot(dx, dy) - R) - t;
            float ang = std::atan2(dy, dx) - start;
            while (ang < 0) ang += 6.2831853f;
            const float arc = ang <= sweep ? ring : std::min(std::hypot(x + 0.5f - ex0, y + 0.5f - ey0), std::hypot(x + 0.5f - ex1, y + 0.5f - ey1)) - t;
            omniBlendPx(row[x], f, c, uint32_t(std::clamp(0.5f - ring, 0.f, 1.f) * 55));
            omniBlendPx(row[x], f, c, uint32_t(std::clamp(0.5f - arc, 0.f, 1.f) * 255));
        }
    }
}
// Arrow pointer with a dark rim and a soft shadow, rendered once.
// OMNI_POINTER_STYLE_V1: the sprite follows Browser settings (style, size, colour, outline; OmniPointerStyle.h) and is
// rebuilt only when one of them or the display scale changes. The default settings give 56c's arrow pixel for pixel.
// The hotspot (arrow tip, finger tip, crosshair centre) sits on pointerX/pointerY, so clicks land on it at any size.
static int omniPointerHotX = 0, omniPointerHotY = 0;
static SDL_Surface* omniPointerSprite()
{
    static SDL_Surface* sprite = nullptr;
    static uint64_t builtFor = 0;
    const uint64_t want = omniPtrSignature(displayScale);
    if (builtFor == want) return sprite;
    builtFor = want;
    if (sprite) { SDL_FreeSurface(sprite); sprite = nullptr; }
    sprite = omniPtrBuildSprite(displayScale, &omniPointerHotX, &omniPointerHotY);
    return sprite;
}
static void omniDrawPointer()
{
    if (SDL_Surface* sprite = omniPointerSprite()) {
        const uint8_t alpha = omniPtrAlpha(); // OMNI_POINTER_STYLE_V1: opacity setting
        SDL_Rect dst { int(pointerX * displayScale + 0.5) - omniPointerHotX, int(pointerY * displayScale + 0.5) - omniPointerHotY, sprite->w, sprite->h };
        if (!omniBlendSurface(sprite, dst.x, dst.y, 0, alpha)) { SDL_SetSurfaceAlphaMod(sprite, alpha); SDL_BlitSurface(sprite, nullptr, canvas, &dst); } // OMNI_POLISH_V1
        return;
    }
    fill(pointerX, pointerY, 4, 19, {12,18,24,255}); fill(pointerX, pointerY, 16, 4, {12,18,24,255});
    fill(pointerX + 1, pointerY + 1, 2, 15, {255,255,255,255}); fill(pointerX + 1, pointerY + 1, 12, 2, {255,255,255,255});
}

// OMNI_KEYBOARD_V2: text with a caret, selection and horizontal scrolling --------------------------
// Layout only changes when the text, caret or selection change (cached per field); the visible part
// is rendered once into the field's own surface (not the shared text cache: it changes per key).
struct OmniKbView { size_t start = 0; std::string key; SDL_Surface* surface = nullptr; int caretX = 0, selX0 = 0, selX1 = 0; bool left = false, right = false; };
static OmniKbView omniKbPreviewView, omniKbAddressView;
static int omniKbMeasure(int font, const std::string& s)
{
    if (s.empty()) return 0;
    int w = 0, h = 0;
    if (TTF_Font* f = omniPickFace(font, s)) TTF_SizeUTF8(f, s.c_str(), &w, &h);
    return w;
}
// The edited text as shown (dots for passwords, line breaks as a pilcrow) with the caret and the
// selection as byte offsets into it. False while a webpage field hasn't been read yet.
static bool omniKbShown(std::string& shown, size_t& caret, size_t& s0, size_t& s1)
{
    std::string before, sel, after;
    bool caretAtStart = false;
    if (omniKb.kind == 1) {
        if (!omniKb.mirrorValid) return false;
        if (omniKb.mirrorNoSel) {
            const size_t count = omniCpCount(omniKb.before);
            const size_t at = omniCpOffset(omniKb.before, count - std::min<size_t>(count, size_t(std::max(0, omniKb.estFromEnd))));
            before = omniKb.before.substr(0, at); after = omniKb.before.substr(at);
        } else { before = omniKb.before; sel = omniKb.selected; after = omniKb.after; caretAtStart = omniKb.backward; }
    } else {
        const std::string* t = omniKbText();
        if (!t) return false;
        omniKbClamp();
        const size_t a = std::min(omniKb.caret, omniKb.anchor), b = std::max(omniKb.caret, omniKb.anchor);
        before = t->substr(0, a); sel = t->substr(a, b - a); after = t->substr(b);
        caretAtStart = omniKb.caret < omniKb.anchor;
    }
    auto shape = [](const std::string& s) {
        std::string out;
        if (omniKb.field == omniKbFieldPassword) {
            for (unsigned char c : s) if ((c & 0xc0) != 0x80) out += "\xe2\x80\xa2";
            return out;
        }
        for (char c : s) { if (c == '\n') out += "\xc2\xb6"; else if (c == '\r' || c == '\t') out += ' '; else out += c; }
        return out;
    };
    before = shape(before); sel = shape(sel); after = shape(after);
    s0 = before.size(); s1 = s0 + sel.size(); caret = caretAtStart ? s0 : s1;
    shown = before + sel + after;
    return true;
}
static void omniKbDrawText(OmniKbView& v, const std::string& shown, size_t caret, size_t s0, size_t s1, int x, float cy, int w, int font, SDL_Color ink, SDL_Color accent)
{
    if (!omniFaces[font].f || w <= 0) return;
    const int room = physical(w), margin = physical(20);
    char head[96];
    snprintf(head, sizeof(head), "%d|%d|%zu|%zu|%zu|%02x%02x%02x|", font, room, caret, s0, s1, ink.r, ink.g, ink.b);
    const std::string key = head + shown;
    auto aligned = [&](size_t i) { while (i && i < shown.size() && (static_cast<unsigned char>(shown[i]) & 0xc0) == 0x80) --i; return std::min(i, shown.size()); };
    auto starts = [&](size_t from, size_t to) {   // code point starts in [from, to], ascending
        std::vector<size_t> c;
        for (size_t i = from; i < to; i = omniCpNext(shown, i)) c.push_back(i);
        c.push_back(to);
        return c;
    };
    if (key != v.key) {
        v.key = key;
        caret = std::min(caret, shown.size());
        v.start = aligned(std::min(v.start, shown.size()));
        // Keep the caret in view: some context to its left, a margin to its right.
        if (caret < v.start) { v.start = caret; for (int k = 0; k < 8 && v.start; ++k) v.start = omniCpPrev(shown, v.start); }
        if (omniKbMeasure(font, shown.substr(v.start, caret - v.start)) > room - margin) {
            const size_t lo = std::max(v.start, caret > 600 ? aligned(caret - 600) : size_t(0));
            const auto c = starts(lo, caret);   // widths shrink along c; the last one (the caret) fits
            size_t a = 0, b = c.size() - 1;
            while (a < b) { const size_t m = (a + b) / 2; if (omniKbMeasure(font, shown.substr(c[m], caret - c[m])) <= room - margin) b = m; else a = m + 1; }
            v.start = c[a];
        } else if (v.start && omniKbMeasure(font, shown.substr(v.start)) < room - margin) {
            // The rest fits: move the view back so the field stays filled (after deleting at the end).
            const size_t lo = v.start > 600 ? aligned(v.start - 600) : 0;
            const auto c = starts(lo, v.start);
            size_t a = 0, b = c.size() - 1;
            while (a < b) { const size_t m = (a + b) / 2; if (omniKbMeasure(font, shown.substr(c[m])) <= room - margin) b = m; else a = m + 1; }
            v.start = c[a];
        }
        size_t end = shown.size();
        if (omniKbMeasure(font, shown.substr(v.start)) > room) {
            size_t hi = std::min(shown.size(), v.start + 1200);
            while (hi < shown.size() && (static_cast<unsigned char>(shown[hi]) & 0xc0) == 0x80) ++hi;
            const auto c = starts(v.start, hi);
            size_t a = 0, b = c.size() - 1;
            while (a < b) { const size_t m = (a + b + 1) / 2; if (omniKbMeasure(font, shown.substr(v.start, c[m] - v.start)) <= room) a = m; else b = m - 1; }
            end = c[a];
        }
        if (v.surface) { SDL_FreeSurface(v.surface); v.surface = nullptr; }
        const std::string part = shown.substr(v.start, end - v.start);
        if (!part.empty()) if (TTF_Font* f = omniPickFace(font, part)) v.surface = TTF_RenderUTF8_Blended(f, part.c_str(), SDL_Color { ink.r, ink.g, ink.b, 255 });
        auto xAt = [&](size_t i) { i = std::clamp(i, v.start, end); return omniKbMeasure(font, shown.substr(v.start, i - v.start)); };
        v.caretX = xAt(caret); v.selX0 = xAt(s0); v.selX1 = xAt(s1);
        v.left = v.start > 0; v.right = end < shown.size();
    }
    const int px = physical(x), half = font == omniBody ? 13 : 11;
    const int top = int(cy * displayScale + 0.5) - omniFaces[font].capMid, y0 = physical(int(cy) - half), h = physical(2 * half);
    if (s1 > s0 && v.selX1 > v.selX0) omniRectPx({ px + v.selX0, y0, v.selX1 - v.selX0, h }, accent, 90);
    if (v.surface) omniBlitText(v.surface, px, top, room, 255);
    const int bar = std::max(2, physical(2));
    omniRectPx({ px + std::min(v.caretX, room - bar) - bar / 2, y0, bar, h }, accent);
    // Text continues beyond the field: a faint edge on that side.
    if (v.left) omniRectPx({ px - physical(6), y0, std::max(1, physical(1)), h }, accent, 110);
    if (v.right) omniRectPx({ px + room + physical(5), y0, std::max(1, physical(1)), h }, accent, 110);
}
static std::string omniKbFieldName()
{
    if (omniKb.kind == 0) return "Address";
    if (omniKb.kind == 2) return omniKbLabel;
    switch (omniKb.field) {
    case omniKbFieldUrl: return "Web address";
    case omniKbFieldEmail: return "Email";
    case omniKbFieldNumber: return "Number";
    case omniKbFieldSearch: return "Search";
    case omniKbFieldPassword: return "Password";
    case omniKbFieldMulti: return omniKb.contentEditable ? "Editor" : "Text area";
    default: return "Webpage field";
    }
}
// Bottom bar while the keyboard is open.
static void omniKbHints()
{
    omniKbEnsure();
    const OmniTheme& T = omniTheme();
    const int y = height - 16;
    const bool ps = playStationIcons;
    int x = 18;
    auto label = [&](const std::string& s) { x += omniLabel(s, float(x), float(y), omniSmall, T.ink) + 16; };
    auto face = [&](int b, const std::string& s) { faceIcon(x + 10, y, b, ps); x += 30; label(s); };
    auto pill = [&](const char* p) {
        const int w = int(omniTextWidthPx(omniSmallBold, p) / displayScale + 0.5) + 12;
        fillRounded(x, y - 11, w, 22, 5, T.key);
        omniLabel(p, x + w / 2.f, float(y), omniSmallBold, T.ink, 1);
        x += w + 5;
    };
    auto shoulders = [&](const std::string& s) {
        controllerAsset(x + 14, y, ps ? OmniControllerAssets::ps_lb : OmniControllerAssets::xbox_lb);
        controllerAsset(x + 48, y, ps ? OmniControllerAssets::ps_rb : OmniControllerAssets::xbox_rb);
        x += 68; label(s);
    };
    auto options = [&](const std::string& s) { menuIcon(x + 10, y); x += 30; label(s); };
    if (omniKb.kind == 0 && omniKbPage == 1) {
        face(0, "Open"); face(2, "Remove"); face(1, "Close"); options("Go"); shoulders("Letters");
        pill(ps ? "R3" : "RS"); label("Translate page");
        return;
    }
    face(0, "Type"); face(2, "Delete"); face(3, "Space"); face(1, "Close"); options(omniKbGoLabel());
    shoulders("Cursor");
    pill(ps ? "L2" : "LT"); pill(ps ? "R2" : "RT"); label("Word");
    pill(ps ? "L3" : "LS"); label(omniKb.caps == 2 ? "Caps off" : omniKb.caps ? "Caps lock" : "Shift");
    pill(ps ? "R3" : "RS"); label(omniKb.layer != omniKbLetters ? "Letters" : omniKb.field == omniKbFieldNumber ? "Numbers" : "Symbols");
    if (ps) { pill("Touchpad"); label(omniKb.kind == 0 ? "Sites" : "Edit"); }
}

// OMNI_POLISH_V1: shared look ---------------------------------------------------------------------
// Focus rings (the pointer is the controller's focus in the bars), panel open fades, one hint-bar
// layout for every mode. Only drawing code: what each control does is unchanged.
static void omniRingRect(int x, int y, int w, int h, int r, SDL_Color ring, SDL_Color inside)
{
    fillRounded(x - 2, y - 2, w + 4, h + 4, r + 2, ring);
    fillRounded(x, y, w, h, r, inside);
}
static void omniRingDisc(float cx, float cy, float r, SDL_Color ring, SDL_Color inside)
{
    omniDisc(cx, cy, r + 2, ring);
    omniDisc(cx, cy, r, inside);
}
// Panels (settings, keyboard, tools menu, history, dialogs) fade in over omniPanelFadeMs when they
// open. The rectangle under the panel is saved before it is drawn and blended back with weight 1 - t:
// one pass over the panel's own pixels on the few frames of the fade, nothing once it is open.
enum { omniPanelSettings, omniPanelKeyboard, omniPanelMenu, omniPanelHistory, omniPanelModal, omniPanelCount };
constexpr uint32_t omniPanelFadeMs = 150;
static uint32_t omniPanelSince[omniPanelCount] = {};   // 0: not open, 1: shown without a fade
static float omniPanelT(int which)
{
    uint32_t& since = omniPanelSince[which];
    if (!omniAutoHideAllowed || since <= 1) { if (!since) since = 1; return 1; }   // self-tests: no motion
    const uint32_t dt = SDL_GetTicks() - since;
    if (dt >= omniPanelFadeMs) return 1;
    const float u = 1 - dt / float(omniPanelFadeMs);
    return 1 - u * u * u;
}
static std::vector<uint32_t> omniFadeSaved;
static SDL_Rect omniFadeRect {};
static uint32_t omniFadeK = 256;
static void omniFadeBegin(int x, int y, int w, int h, float t)
{
    omniFadeK = 256;
    if (t >= 1 || !omniPix().ok) return;
    const int x0 = std::max(0, physical(x)), y0 = std::max(0, physical(y));
    const int x1 = std::min(canvas->w, physical(x + w)), y1 = std::min(canvas->h, physical(y + h));
    if (x1 <= x0 || y1 <= y0) return;
    omniFadeRect = { x0, y0, x1 - x0, y1 - y0 };
    omniFadeSaved.resize(size_t(omniFadeRect.w) * omniFadeRect.h);
    for (int j = 0; j < omniFadeRect.h; ++j) memcpy(omniFadeSaved.data() + size_t(j) * omniFadeRect.w, omniRow(y0 + j) + x0, size_t(omniFadeRect.w) * 4);
    omniFadeK = uint32_t(std::clamp(t, 0.f, 1.f) * 256);
}
static void omniFadeEnd()
{
    if (omniFadeK >= 256) return;
    const uint32_t k = omniFadeK, q = 256 - k;
    for (int j = 0; j < omniFadeRect.h; ++j) {
        uint32_t* d = omniRow(omniFadeRect.y + j) + omniFadeRect.x;
        const uint32_t* s = omniFadeSaved.data() + size_t(j) * omniFadeRect.w;
        for (int i = 0; i < omniFadeRect.w; ++i) {   // two channels per multiply, any channel order
            const uint32_t a = d[i], b = s[i];
            d[i] = ((((a & 0x00ff00ffu) * k + (b & 0x00ff00ffu) * q) >> 8) & 0x00ff00ffu) | ((((a >> 8) & 0x00ff00ffu) * k + ((b >> 8) & 0x00ff00ffu) * q) & 0xff00ff00u);
        }
    }
    omniFadeK = 256;
}
// Hint bar: glyph + label items, flowing from the left; a second group is right-aligned.
enum { omniHintView = 10, omniHintMenu, omniHintShoulders, omniHintRStick, omniHintLStick, omniHintDpadV, omniHintDpadH };
struct OmniHint { int glyph; std::string label; };
static int omniHintGlyphW(int g) { return g == omniHintShoulders ? 62 : 28; }
static int omniHintItemW(const OmniHint& h) { return omniHintGlyphW(h.glyph) + 6 + int(omniTextWidthPx(omniSmall, h.label) / displayScale + 0.5); }
constexpr int omniHintGap = 30;
static void omniHintDraw(const OmniHint& h, int x)
{
    using namespace OmniControllerAssets;
    const OmniTheme& T = omniTheme();
    const int cy = height - bottom / 2;
    const bool ps = playStationIcons;
    switch (h.glyph) {
    case omniHintView: menuIcon(x + 14, cy, true); break;
    case omniHintMenu: menuIcon(x + 14, cy); break;
    case omniHintShoulders: controllerAsset(x + 14, cy, ps ? ps_lb : xbox_lb); controllerAsset(x + 48, cy, ps ? ps_rb : xbox_rb); break;
    case omniHintRStick: stickIcon(x + 14, cy, true); break;
    case omniHintLStick: stickIcon(x + 14, cy); break;
    case omniHintDpadV: omniIcon(omniIconDpad, x + 14, cy, T.inkFaint); omniIcon(omniIconDpadV, x + 14, cy, T.ink); break;
    case omniHintDpadH: controllerAsset(x + 14, cy, ps ? ps_dpad_horizontal : xbox_dpad_horizontal); break;
    default: faceIcon(x + 14, cy, h.glyph, ps); break;
    }
    omniLabel(h.label, float(x + omniHintGlyphW(h.glyph) + 6), float(cy), omniSmall, T.ink);
}
// The bar's background is drawn by the caller; `note` (dim) fills the space between the groups.
static void omniHints(const std::vector<OmniHint>& left, const std::vector<OmniHint>& right = {}, const std::string& note = "")
{
    const OmniTheme& T = omniTheme();
    int x = 20;
    for (const auto& h : left) { omniHintDraw(h, x); x += omniHintItemW(h) + omniHintGap; }
    int rw = 0;
    for (const auto& h : right) rw += omniHintItemW(h) + omniHintGap;
    int rx = width - 20 - (rw ? rw - omniHintGap : 0);
    for (const auto& h : right) { omniHintDraw(h, rx); rx += omniHintItemW(h) + omniHintGap; }
    const int room = width - 20 - (rw ? rw : 0) - x;
    if (!note.empty() && room > 60) omniLabel(note, float(x), float(height - bottom / 2), omniSmall, T.inkDim, 0, room);
}
// Browsing: what each button does today (button()). Edit here when a button's action changes.
static void omniBrowseHints()
{
    omniHints({ { 0, "Click" }, { 3, "Address" }, { 2, "New tab" }, { omniHintShoulders, "Tabs" }, { omniHintRStick, "Close tab" }, { 1, "Back" } },
        { { omniHintView, "Settings" }, { omniHintMenu, "Menu" } });
}

// OMNI_STYLE_V1: bars ----------------------------------------------------------------------------
static bool omniHover(int x, int y, int w, int h)
{
    return omniChromeShown >= 1 && !editing && !settingsOpen && !pageFullscreen
        && pointerX >= x && pointerX < x + w && pointerY >= y && pointerY < y + h;
}
static void omniDrawAddress()
{
    const OmniTheme& T = omniTheme();
    const bool focused = editing && !pageEditing;
    if (focused) fillRounded(182, 60, 918, 44, omniRadius + 1, T.accent);
    else if (omniHover(176, 52, 928, 60)) fillRounded(182, 60, 918, 44, omniRadius + 1, omniMix(T.field, T.accent, 0.55f)); // OMNI_POLISH_V1: pointer focus
    fillRounded(184, 62, 914, 40, omniRadius, T.field);
    if (focused) { // OMNI_KEYBOARD_V2: caret, selection and scrolling
        omniKbEnsure();
        std::string shown;
        size_t caret = 0, s0 = 0, s1 = 0;
        if (omniKb.kind == 0 && omniKbShown(shown, caret, s0, s1)) {
            omniKbDrawText(omniKbAddressView, shown, caret, s0, s1, 198, 82, 886, omniSmall, T.ink, T.accent);
            if (shown.empty()) omniLabel("Search or enter address", 206, 82, omniSmall, T.inkFaint);
        } else text(address + "|", 198, 71, 886, true);
        return;
    }
    const std::string url = active() ? active()->url : "";
    const float right = omniF3StarShown() ? 1052 : 1086; // OMNI_FEATURES_V3: room for the star
    float x = 198;
    if (url.empty()) { omniLabel("Search or enter address", x, 82, omniSmall, T.inkFaint); return; }
    omniF3StarDraw(); // OMNI_FEATURES_V3: bookmark star
    const size_t scheme = url.find("://");
    const bool secure = url.rfind("https://", 0) == 0;
    if (!secure && url.rfind("http://", 0) != 0) { omniLabel(url, x, 82, omniSmall, T.inkDim, 0, int(right - x)); return; }
    const size_t hostStart = scheme + 3, hostEnd = std::min(url.find_first_of("/?#", hostStart), url.size());
    if (secure) { omniIcon(omniIconLock, 205, 81, T.inkDim); x = 219; }
    else x += omniLabel(url.substr(0, hostStart), x, 82, omniSmall, T.inkFaint, 0, int(right - x));   // "http://": not secure
    x += omniLabel(url.substr(hostStart, hostEnd - hostStart), x, 82, omniSmall, T.ink, 0, int(right - x));
    if (hostEnd < url.size() && right - x > 24) omniLabel(url.substr(hostEnd), x, 82, omniSmall, T.inkDim, 0, int(right - x));
}
static void omniDrawTopBar()
{
    const OmniTheme& T = omniTheme();
    fill(0, 0, width, 52, T.bg);
    fill(0, 52, width, top - 52, T.bar);
    omniRectPx({ 0, physical(top) - 1, renderWidth, 1 }, T.line);
    const int o = omniLabel("O", 20, 27, omniBodyBold, T.accent);
    omniLabel("MNI", 20 + o, 27, omniBodyBold, T.ink);
    // Tabs: fixed width, ellipsised titles (titles stay while loading); the selected tab joins the toolbar.
    if (!omniF3DrawTabStrip()) // OMNI_FEATURES_V3: more than 4 tabs: compact / scrolling strip (4 or fewer: unchanged)
    for (size_t i = 0; i < tabs.size(); ++i) {
        const int x = 100 + int(i) * 240;
        const Tab& tab = *tabs[i];
        const bool sel = i == selected, hover = omniHover(x, 8, 232, 44);
        if (sel) fillRounded(x, 8, 232, 44, omniRadius, T.bar, 255, omniCornersTop);
        else if (hover) omniRingRect(x, 12, 232, 34, omniRadius, T.accent, T.hover); // OMNI_POLISH_V1: focus ring
        else fillRounded(x, 12, 232, 34, omniRadius, T.tab);
        if (sel) fillRounded(x + 14, 8, 204, 3, 1, T.accent, 255, omniCornersAll); // OMNI_POLISH_V1: selected-tab marker
        float tx = x + 16;
        if (tab.loading) { omniSpinner(x + 22, 30, 6.5f, T.accent); tx = x + 38; }
        else if (tab.crashed || !tab.message.empty()) { omniDisc(x + 21, 30, 4, tab.crashed ? omniBad : omniWarn); tx = x + 34; }
        const std::string title = !tab.title.empty() ? tab.title : !tab.url.empty() ? omniBlockerHostOf(tab.url) : std::string("New tab");
        omniLabel(title, tx, 30, omniSmall, sel ? T.ink : T.inkDim, 0, int(x + (tab.omniPrivate ? 136 : 202) - tx)); // OMNI_POLISH_V1: room for the private badge
        const bool closeHover = omniHover(x + 208, 8, 24, 44);
        if (closeHover) omniRingDisc(x + 218, 30, 11, T.accent, omniMix(sel ? T.bar : T.tab, T.ink, 0.16f));
        omniIcon(omniIconClose, x + 218, 30, closeHover || sel ? T.ink : T.inkDim);
    }
    const bool full = omniF3TabsFull(); // OMNI_FEATURES_V3: tab limit setting
    if (omniHover(1070, 0, 80, 52) && !full) omniRingRect(1080, 12, 46, 34, omniRadius, T.accent, T.hover); // OMNI_POLISH_V1
    else fillRounded(1080, 12, 46, 34, omniRadius, T.tab);
    omniIcon(omniIconPlus, 1103, 29, full ? T.inkFaint : T.ink);
    // uBlock status: shield, green when on (outlined: network rules only), grey off, red on error.
    {
        const bool failed = omniBlockerFailed(), enabled = omniBlockerEnabled(), uBlock = omniBlockerUsesUBlock();
        const bool content = !uBlock || omniBlockerContentActive(), hover = omniHover(1150, 0, 130, 52);
        if (hover) omniRingRect(1154, 10, 118, 38, omniRadius, T.accent, T.hover); // OMNI_POLISH_V1
        const SDL_Color under = hover ? T.hover : T.bg;
        omniIcon(omniIconShield, 1176, 29, failed ? omniBad : enabled ? omniGood : T.inkFaint);
        if (failed) omniIcon(omniIconBang, 1176, 29, under);
        else if (enabled && !content) { omniIcon(omniIconShieldHole, 1176, 29, under); omniIcon(omniIconCheck, 1176, 29, omniGood); }
        else if (enabled) omniIcon(omniIconCheck, 1176, 29, under);
        // OMNI_POLISH_V1: "Ad block" (was "uBO" / "Block"); the shield shows on, off, network-only or error.
        omniLabel(failed ? "Error" : "Ad block", 1196, 29, omniSmall, enabled && !failed ? T.ink : T.inkDim, 0, 72);
    }
    // Toolbar
    const bool canBack = active() && WKPageCanGoBack(active()->page), canForward = active() && WKPageCanGoForward(active()->page);
    auto navButton = [&](float cx, int icon, bool enabled, int x0, int x1) {
        if (enabled && omniHover(x0, 52, x1 - x0, 60)) omniRingDisc(cx, 82, 19, T.accent, T.hover); // OMNI_POLISH_V1
        omniIcon(icon, cx, 82, enabled ? T.ink : T.inkFaint);
    };
    navButton(32, omniIconBack, canBack, 0, 64);
    navButton(90, omniIconForward, canForward, 64, 120);
    navButton(148, omniIconReload, active() != nullptr, 120, 176);
    omniDrawAddress();
    if (omniProgressAlpha > 0 && omniProgress > 0) { // OMNI_POLISH_V1: 4 px on a faint track (was 2 px)
        const uint8_t a = uint8_t(255 * omniProgressAlpha);
        fillRounded(184, 104, 914, 4, 2, omniMix(T.bar, T.accent, 0.22f), a);
        fillRounded(184, 104, std::max(8, int(914 * std::min(omniProgress, 1.f))), 4, 2, T.accent, a);
    }
    {
        // Per-site uBlock switch.
        auto host = active() ? omniBlockerHostOf(active()->url) : std::string { };
        const bool trusted = omniBlockerSiteTrusted(host), usable = !host.empty() && omniBlockerEnabled();
        const bool hover = usable && omniHover(1104, 52, 100, 60);
        // OMNI_POLISH_V1: two lines, "This site" over a status dot and "Blocking" / "Allowed" (was "Site: ON/OFF").
        const SDL_Color state = trusted ? omniWarn : omniGood;
        const SDL_Color inside = !usable ? T.tab : omniMix(T.field, state, hover ? 0.24f : 0.12f);
        if (hover) omniRingRect(1104, 62, 98, 40, omniRadius, T.accent, inside);
        else fillRounded(1104, 62, 98, 40, omniRadius, inside);
        omniLabel("This site", 1153, 73, omniCaption, usable ? T.inkDim : T.inkFaint, 1);
        if (!usable) omniLabel("-", 1153, 91, omniCaptionBold, T.inkFaint, 1);
        else {
            const char* word = trusted ? "Allowed" : "Blocking";
            const int ww = int(omniTextWidthPx(omniCaptionBold, word) / displayScale + 0.5), x0 = 1153 - (ww + 12) / 2;
            omniDisc(x0 + 3.5f, 91, 3.5f, state);
            omniLabel(word, x0 + 12, 91, omniCaptionBold, T.ink);
        }
    }
    if (omniHover(1210, 52, 70, 60)) omniRingDisc(1238, 82, 19, T.accent, T.hover); // OMNI_POLISH_V1
    omniIcon(omniIconGear, 1238, 82, T.ink);
}
static void omniSettingsHints()
{
    // OMNI_POLISH_V1: shared hint layout (was fixed x positions with clipped text()); Y opens Browser tools.
    omniHints({ { omniHintDpadV, "Choose setting" }, { omniHintDpadH, "Change" }, { 0, "Done" }, { 1, "Back" } }, { { 3, "Browser tools" } });
}
static void omniDrawHintBar()
{
    const OmniTheme& T = omniTheme();
    fill(0, height - bottom, width, bottom, T.bar);
    omniRectPx({ 0, physical(height - bottom), renderWidth, 1 }, T.line);
    if (settingsOpen) omniSettingsHints(); else if (editing) omniKbHints(); else omniBrowseHints(); // OMNI_KEYBOARD_V2, OMNI_POLISH_V1 (was controllerHints())
}
// Both bars over the page. While they slide, each is drawn in place and its rows are moved: the
// same drawing code (including controllerHints()) serves every position. Copies only while moving.
static std::vector<uint8_t> omniRowScratch;
static void omniDrawBars()
{
    const float shown = omniAutoHideActive() ? omniChromeShown : 1.f;
    if (shown <= 0) return;
    uint8_t* px = static_cast<uint8_t*>(canvas->pixels);
    const size_t pitch = canvas->pitch;
    const int topRows = std::min(physical(top), canvas->h), pageY = int(top * shown * displayScale + 0.5);
    const int hidden = topRows - pageY;
    if (hidden <= 0) omniDrawTopBar();
    else if (pageY > 0) {
        omniRowScratch.resize(pitch * topRows);
        memcpy(omniRowScratch.data(), px, pitch * topRows);
        omniDrawTopBar();
        memmove(px, px + pitch * hidden, pitch * pageY);
        memcpy(px + pitch * pageY, omniRowScratch.data() + pitch * pageY, pitch * hidden);
    }
    omniFadeRows(pageY, physical(5), 70, 0);
    const int y0 = std::min(physical(height - bottom), canvas->h), rows = canvas->h - y0;
    const int visible = std::min(rows, int(bottom * shown * displayScale + 0.5)), down = rows - visible;
    if (down <= 0) omniDrawHintBar();
    else if (visible > 0) {
        omniRowScratch.resize(pitch * rows);
        memcpy(omniRowScratch.data(), px + pitch * y0, pitch * rows);
        omniDrawHintBar();
        memmove(px + pitch * (y0 + down), px + pitch * y0, pitch * visible);
        memcpy(px + pitch * y0, omniRowScratch.data(), pitch * down);
    }
    omniFadeRows(canvas->h - visible - physical(4), physical(4), 0, 45);
}

// OMNI_STYLE_V1: toast (status and page messages) ------------------------------------------------
static void omniDrawToast()
{
    const OmniTheme& T = omniTheme();
    const bool error = active() && !active()->message.empty() && !omniFxErrorPanelShown(); // OMNI_FEATURES_V1: the error panel shows page errors
    const std::string& message = error ? active()->message : status;
    if (message == "Ready") { omniToastText.clear(); return; }
    const uint32_t now = SDL_GetTicks();
    if (message != omniToastText) { omniToastText = message; omniToastSince = now; }
    omniToastError = error;
    // OMNI_POLISH_V1: a status set without notice() (four-tab limit, resolution saved) times out like a
    // notice; progress messages ("...") stay until they are replaced.
    if (!error && !statusUntil && omniAutoHideAllowed && !(message.size() >= 3 && !message.compare(message.size() - 3, 3, "...")))
        statusUntil = now + 6000;
    float a = std::min(1.f, (now - omniToastSince) / 180.f);
    if (!error && statusUntil) a = std::min(a, std::max(0.f, int32_t(statusUntil - now) / 320.f));   // fades out as notice() ends
    if (error) a = std::min(a, std::max(0.f, int32_t(omniToastSince + omniToastErrorMs - now) / 320.f));   // OMNI_POLISH_V1: the tab keeps its dot
    a = a * a * (3 - 2 * a);
    if (a <= 0) return;
    const std::string shown = omniFit(omniSmall, message, physical(940));
    const int icon = error ? 28 : 0, w = int(omniTextWidthPx(omniSmall, shown) / displayScale + 0.5) + 48 + icon, h = 44; // OMNI_POLISH_V1: pill
    const int x = (width - w) / 2;
    const int base = editing ? keyboardY - 46 - 14 : std::min(omniPageBottom(), height - bottom) - 18;
    const int y = base - h + int((1 - a) * 12);
    const uint8_t A = uint8_t(255 * a);
    omniShadow(x, y, w, h, h / 2, 12, uint8_t(110 * a), 3);
    fillRounded(x, y, w, h, h / 2, omniMix(T.raised, T.line, 0.6f), A); // OMNI_POLISH_V1: pill with a hairline edge
    fillRounded(x + 1, y + 1, w - 2, h - 2, h / 2 - 1, T.raised, A);
    if (error) { omniDisc(x + 32, y + h / 2.f, 9, omniBad, A); omniIcon(omniIconAlert, x + 32, y + h / 2.f, T.bg, A); }
    omniLabel(shown, x + 24 + icon, y + h / 2.f, omniSmall, T.ink, 0, 0, A);
}

// OMNI_STYLE_V1 / OMNI_KEYBOARD_V2: on-screen keyboard ----------------------------------------------
static void omniDrawKeyboard()
{
    omniKbEnsure();
    const OmniTheme& T = omniTheme();
    const int px = keyboardX - 16, py = keyboardY - 58, pw = keyboardWidth + 32, ph = actionY + keyHeight + 6 - py;
    struct FadeScope { ~FadeScope() { omniFadeEnd(); } } fadeScope; // OMNI_POLISH_V1: fades in when it opens
    omniFadeBegin(px - 24, py - 24, pw + 48, ph + 48, omniPanelT(omniPanelKeyboard));
    omniShadow(px, py, pw, ph, omniRadius, 16, 130, 4);
    fillRounded(px, py, pw, ph, omniRadius, T.panel);
    // Preview: the text being edited with its caret and selection, and the field's name.
    const int fy = keyboardY - 50, fh = 40;
    const float fcy = fy + fh / 2.f;
    fillRounded(keyboardX - 2, fy - 2, keyboardWidth + 4, fh + 4, omniRadius + 1, omniKb.select ? omniWarn : T.accent);
    fillRounded(keyboardX, fy, keyboardWidth, fh, omniRadius, T.field);
    std::string name = omniKbFieldName();
    if (omniKb.caps == 2) name += "   CAPS";
    else if (omniKb.caps == 1) name += "   Shift";
    if (omniKb.select) name += "   Selecting";
    const int nameW = omniLabel(name, float(keyboardX + keyboardWidth - 14), fcy, omniSmall, T.inkDim, 2, 300);
    const int room = keyboardWidth - 28 - nameW - 20;
    std::string shown;
    size_t caret = 0, s0 = 0, s1 = 0;
    if (omniKbShown(shown, caret, s0, s1)) {
        omniKbDrawText(omniKbPreviewView, shown, caret, s0, s1, keyboardX + 14, fcy, room, omniBody, T.ink, T.accent);
        if (shown.empty() && omniKb.kind == 0) omniLabel("Search or enter address", float(keyboardX + 22), fcy, omniSmall, T.inkFaint, 0, room - 10);
    } else omniLabel("Typing into the webpage field", float(keyboardX + 14), fcy, omniSmall, T.inkFaint, 0, room);
    const SDL_Color emptyKey = omniMix(T.panel, T.key, 0.4f);
    const int keyH = keyHeight - 4;
    if (omniKb.kind == 0 && omniKbPage == 1) { // OMNI_SHORTCUTS_V1: tile page
        omniShortcutsLoad();
        const int tileW = keyboardWidth / omniTileCols;
        for (int i = 0; i < 20; ++i) {
            const int x = keyboardX + i % omniTileCols * tileW, y = keyboardY + i / omniTileCols * keyHeight;
            const bool used = i == 0 || i <= int(omniShortcuts.size()), sel = omniShortcutSel == i;
            fillRounded(x, y, tileW - 4, keyH, omniRadius, sel ? T.accent : used ? T.key : emptyKey);
            const SDL_Color ink = sel ? T.accentInk : T.ink;
            if (i == 0) { omniIcon(omniIconPlus, x + 19, y + keyH / 2.f, sel ? T.accentInk : T.accent); omniLabel("Add this site", x + 34, y + keyH / 2.f, omniSmall, ink, 0, tileW - 46); }
            else if (used) omniLabel(omniShortcuts[i - 1].second, x + 12, y + keyH / 2.f, omniSmall, ink, 0, tileW - 28);
        }
        const char* actions[] = { "Letters", "Go", "Close" };
        for (int i = 0; i < 3; ++i) {
            const int x0 = keyboardX + i * keyboardWidth / 3, x1 = keyboardX + (i + 1) * keyboardWidth / 3;
            const bool sel = omniShortcutSel == 20 + i;
            fillRounded(x0, actionY, x1 - x0 - 4, keyH, omniRadius, sel ? T.accent : omniMix(T.key, T.panel, 0.35f));
            omniLabel(actions[i], (x0 + x1 - 4) / 2.f, actionY + keyH / 2.f, omniSmall, sel ? T.accentInk : i == 1 ? T.accent : T.ink, 1);
        }
        return;
    }
    const auto& rows = omniKbRows();
    omniKbFocusClamp();
    const bool keysFocused = omniSuggestSelected() < 0;   // the address suggestions may have the focus
    for (int r = 0; r < int(rows.size()); ++r) {
        const int y = r < 5 ? keyboardY + r * keyHeight : actionY;
        float u = 0;
        for (int c = 0; c < int(rows[r].size()); ++c) {
            const OmniKbKey& k = rows[r][c];
            const int x0 = keyboardX + int(u * keyWidth + 0.5f);
            u += k.units;
            const int w = keyboardX + int(u * keyWidth + 0.5f) - x0 - 4;
            const bool focus = r == omniKb.row && c == omniKb.col, sel = focus && keysFocused;
            const bool on = (k.action == omniKbShiftKey && omniKb.caps) || (k.action == omniKbToolsKey && omniKb.tools)
                || (k.action == omniKbSelectKey && omniKb.select);
            const SDL_Color fillC = sel ? T.accent
                : on ? omniMix(T.key, T.accent, k.action == omniKbShiftKey && omniKb.caps == 2 ? 0.6f : 0.35f)
                : k.action != omniKbInsert ? omniMix(T.key, T.panel, 0.35f) : T.key;
            if (focus && !keysFocused) fillRounded(x0 - 2, y - 2, w + 4, keyH + 4, omniRadius + 1, omniMix(T.panel, T.accent, 0.5f));
            fillRounded(x0, y, w, keyH, omniRadius, fillC);
            const std::string& label = k.action == omniKbShiftKey && omniKb.caps == 2 ? std::string("Caps lock") : k.label;
            const SDL_Color ink = sel ? T.accentInk : k.action == omniKbGoKey ? T.accent : T.ink;
            const bool big = k.action == omniKbInsert && omniCpCount(k.label) <= 2;
            omniLabel(label, x0 + w / 2.f, y + keyH / 2.f, big ? omniBody : omniSmall, ink, 1, w - 8);
        }
    }
}

// OMNI_STYLE_V1: settings panel (rows: controller buttons, theme, auto-hide) ---------------------
// OMNI_POLISH_V1: the panel now ends above the hint bar (y 124..648, was 136..706 over the bar), a
// title-size heading, the selected row tinted as well as marked, centred resolution labels, the
// theme names unclipped. Every hit area in omniSettingsClick moved with its row.
static void omniSettingsPanel()
{
    const OmniTheme& T = omniTheme();
    struct FadeScope { ~FadeScope() { omniFadeEnd(); } } fadeScope;
    omniFadeBegin(270, 100, 740, 580, omniPanelT(omniPanelSettings));
    omniShadow(300, 124, 680, 524, omniRadius + 2, 20, 150, 6);
    fillRounded(300, 124, 680, 524, omniRadius + 2, T.panel);
    omniLabel("Settings", 332, 162, omniTitle, T.ink);
    const bool closeHover = pointerX >= 918 && pointerX < 970 && pointerY >= 136 && pointerY < 188;
    if (closeHover) omniRingDisc(944, 162, 18, T.accent, T.hover);
    omniIcon(omniIconClose, 944, 162, closeHover ? T.ink : T.inkDim);
    omniRectPx({ physical(320), physical(194), physical(640), std::max(1, physical(1) / 2) }, T.line);
    const int rowTop[] = { 202, 330, 426, 502, 588 }, rowBottom[] = { 324, 420, 496, 582, 632 };
    fillRounded(316, rowTop[omniSettingsRow], 648, rowBottom[omniSettingsRow] - rowTop[omniSettingsRow], omniRadius, omniMix(T.panel, T.accent, 0.08f));
    fillRounded(310, rowTop[omniSettingsRow] + 6, 4, rowBottom[omniSettingsRow] - rowTop[omniSettingsRow] - 12, 2, T.accent);
    auto heading = [&](int row, const char* label, int cy) { omniLabel(label, 332, cy, omniSettingsRow == row ? omniSmallBold : omniSmall, omniSettingsRow == row ? T.ink : T.inkDim); };
    heading(0, "Controller buttons", 216);
    for (int i = 0; i < 2; ++i) {
        const int x = i ? 644 : 332;
        const bool on = playStationIcons == bool(i);
        if (on) fillRounded(x - 2, 230, 308, 88, omniRadius + 1, T.accent);
        fillRounded(x, 232, 304, 84, omniRadius, on ? T.raised : T.tab);
        omniLabel(i ? "PlayStation" : "Xbox", x + 20, 256, omniBody, on ? T.ink : T.inkDim);
        for (int b = 0; b < 4; ++b) faceIcon(x + 36 + b * 52, 292, b, i);
        if (on) { omniDisc(x + 280, 256, 11, T.accent); omniIcon(omniIconCheck, x + 280, 256, T.accentInk); }
    }
    heading(1, "Theme", 346);
    for (int i = 0; i < omniThemeCount; ++i) {
        const int x = 332 + i * 156;
        const bool on = omniThemeIndex == i;
        const OmniTheme& t = omniThemes[i];
        if (on) fillRounded(x - 2, 358, 152, 56, omniRadius + 1, T.accent);
        fillRounded(x, 360, 148, 52, omniRadius, on ? T.raised : T.tab);
        omniDisc(x + 24, 386, 13, t.line);
        omniDisc(x + 24, 386, 12, t.bar);
        omniDisc(x + 24, 386, 5.5f, t.accent);
        omniLabel(t.name, x + 44, 386, omniSmall, on ? T.ink : T.inkDim, 0, 100);
    }
    heading(2, "Hide bars while reading", 444);
    omniLabel("After 3 s without input. Any button brings them back.", 332, 470, omniCaption, T.inkDim, 0, 548);
    fillRounded(892, 442, 56, 28, 14, omniAutoHide ? T.accent : T.key);
    omniDisc(omniAutoHide ? 934 : 906, 456, 10, omniAutoHide ? T.ink : T.inkDim);
    heading(3, "Resolution (restart to apply)", 518);
    for (int i = 0; i < 3; ++i) {
        const int x = 332 + i * 208;
        const bool on = omniDisplayChoice == i;
        fillRounded(x, 534, 200, 40, omniRadius, on ? T.accent : T.key);
        omniLabel(omniDisplayLabels[i], x + 100, 554, omniSmallBold, on ? T.accentInk : T.ink, 1);
    }
    heading(4, "Playback stats (this session)", 610);
    fillRounded(892, 596, 56, 28, 14, omniStatsPanel.enabled ? T.accent : T.key);
    omniDisc(omniStatsPanel.enabled ? 934 : 906, 610, 10, omniStatsPanel.enabled ? T.ink : T.inkDim);
}
static void omniSettingsClick(int x, int y)
{
    // OMNI_POLISH_V1: same hit areas as before, moved with the new row positions.
    if(y>=588 && y<632 && x>=332 && x<948) { omniSettingsRow=4; omniStatsSet(!omniStatsPanel.enabled); return; }
    if (x >= 918 && x < 970 && y >= 136 && y < 188) { settingsOpen = false; return; }
    if (y >= 232 && y < 316 && x >= 332 && x < 948 && (x < 636 || x >= 644)) {
        omniSettingsRow = 0; playStationIcons = x >= 644; saveControllerStyle(); return;
    }
    if (y >= 360 && y < 412 && x >= 332 && x < 948 && (x - 332) % 156 < 148) {
        omniSettingsRow = 1; omniThemeIndex = (x - 332) / 156; saveUiTheme(); return;
    }
    if (y >= 426 && y < 496 && x >= 332 && x < 948) { omniSettingsRow = 2; omniSettingsChange(!omniAutoHide); }
    if (y >= 534 && y < 574 && x >= 332 && x < 948 && (x - 332) % 208 < 200) {
        omniSettingsRow = 3;
        const int chosen = (x - 332) / 208;
        const int previous = omniDisplayChoice;
        omniDisplayChoice = (chosen + 2) % 3;
        omniSettingsChange(true);
        if (status == "Could not save resolution") omniDisplayChoice = previous;
    }
}

// OMNI_DIALOGS_V1 -------------------------------------------------------------------------------
// Modals (JavaScript dialogs, <select> menus, HTTP sign-in, shell confirmations) and a small overlay
// layer API used by later shell features (REQ-11). Everything runs on the main loop; WebKit listeners
// are retained while a modal is open and called exactly once when it closes.
static bool omniTestMode()
{
    return selfTest || blockerTest || inputTest || grabberTest /* OMNI_NET_GRABBER_TEST_V1 */ || googleTest || youtubeTest || ipcPressureTest || widgetTest
        || featureTest || mediaControlsTest || recoveryTest || uiTest || displayTest;
}
// Overlay layers registered by other features: drawn under the modal, asked for input after it.
struct OmniOverlayLayer {
    bool (*open)();                 // shown now?
    bool (*button)(int);            // controller button; true = consumed
    bool (*click)(int, int);        // pointer click in layout coordinates; true = consumed
    bool (*scroll)(double);         // right stick / wheel; true = consumed
    void (*draw)();
    bool blocksPage;                // no pointer events reach the page while open
};
static std::vector<OmniOverlayLayer>& omniOverlayLayers() { static std::vector<OmniOverlayLayer> layers; return layers; }

enum { omniModalAlert, omniModalConfirm, omniModalPrompt, omniModalBeforeUnload, omniModalAuth, omniModalSelect, omniModalAsk };
struct OmniSelectRow { std::string label; int option; bool enabled, grouped = false, current = false; };   // option -1: group heading
struct OmniModal {
    int kind = omniModalAlert;
    const void* tab = nullptr;                 // Tab* that asked (nullptr: the shell)
    std::string title, message, okLabel = "OK", cancelLabel = "Cancel", host;
    std::vector<std::string> lines;            // wrapped message (computed once)
    std::string field[2];                      // prompt text | username, password
    int fields = 0;
    bool offerBlock = false, insecure = false, failed = false;
    std::vector<WKTypeRef> listeners;          // retained listener (dialogs) or challenges (auth)
    std::function<void(bool)> ask;             // omniModalAsk
    std::vector<OmniSelectRow> rows;           // omniModalSelect
    int focus = 0;                             // fields first, then buttons (left to right); list: row
    int scroll = 0;                            // first message line / first list row shown
    float scrollAcc = 0;
};
static std::deque<std::unique_ptr<OmniModal>> omniModals;
static OmniModal* omniEditingModal = nullptr;  // modal whose field the keyboard edits
static uint32_t omniDialogNoticeAt = 0;

static Tab* omniTabForPage(WKPageRef page)
{
    for (auto& t : tabs) if (t->page == page) return t.get();
    return nullptr;
}
static bool omniTabAlive(const void* tab)
{
    for (auto& t : tabs) if (t.get() == tab) return true;
    return false;
}
// The keyboard edits `target`; `done(submitted)` runs when Go or Cancel closes it.
static void omniKbEdit(std::string* target, const char* label, std::function<void(bool)> done)
{
    settingsOpen = false;
    omniKbTarget = target; omniKbLabel = label; omniKbDone = std::move(done);
    editing = pageEditing = true; keySelection = 0; fieldClickDeadline = 0; shift = false;
    omniKb.kind = -1; // OMNI_KEYBOARD_V2
}
static void omniKbTargetDone(bool submitted)
{
    omniKbTarget = nullptr;
    editing = pageEditing = false; fieldClickDeadline = 0;
    auto done = std::move(omniKbDone); omniKbDone = nullptr;
    if (done) done(submitted);
}
static int omniModalButtons(const OmniModal& m)
{
    if (m.kind == omniModalSelect) return 0;
    return (m.kind == omniModalAlert ? 1 : 2) + (m.offerBlock ? 1 : 0);
}
// Button index (0 = leftmost) -> meaning: 0 primary (OK, Leave, Sign in), 1 cancel, 2 block dialogs.
static int omniModalButtonRole(const OmniModal& m, int i)
{
    const int n = omniModalButtons(m);
    if (m.offerBlock && i == 0) return 2;
    return i == n - 1 ? 0 : 1;   // the primary button is on the right
}
static std::string omniModalButtonLabel(const OmniModal& m, int role)
{
    return role == 0 ? m.okLabel : role == 1 ? m.cancelLabel : std::string("Block dialogs");
}
static OmniModal* omniModalCurrent();
static void omniModalPump();

// Answers a modal (accept = primary action) and releases what it retained. `block` = Block dialogs.
static void omniModalAnswer(OmniModal* m, bool accept, bool block = false)
{
    if (!m) return;
    if (omniEditingModal == m) { omniEditingModal = nullptr; if (omniKbTarget) { omniKbTarget = nullptr; omniKbDone = nullptr; editing = pageEditing = false; } }
    std::unique_ptr<OmniModal> owned;
    for (auto it = omniModals.begin(); it != omniModals.end(); ++it)
        if (it->get() == m) { owned = std::move(*it); omniModals.erase(it); break; }
    omniShoulderCancel(); // OMNI_SHOULDER_DOWNLOADS_V1
    if (!owned) return;
    if (block && omniTabAlive(m->tab)) {
        Tab* tab = const_cast<Tab*>(static_cast<const Tab*>(m->tab));
        tab->omniDialogBlockHost = m->host;
        notice("Dialogs from " + (m->host.empty() ? std::string("this page") : m->host) + " are blocked in this tab");
    }
    for (WKTypeRef l : m->listeners) {
        switch (m->kind) {
        case omniModalAlert: WKPageRunJavaScriptAlertResultListenerCall(static_cast<WKPageRunJavaScriptAlertResultListenerRef>(l)); break;
        case omniModalConfirm: WKPageRunJavaScriptConfirmResultListenerCall(static_cast<WKPageRunJavaScriptConfirmResultListenerRef>(l), accept); break;
        case omniModalBeforeUnload: WKPageRunBeforeUnloadConfirmPanelResultListenerCall(static_cast<WKPageRunBeforeUnloadConfirmPanelResultListenerRef>(l), accept); break;
        case omniModalPrompt: {
            auto value = adoptWK(WKStringCreateWithUTF8CString(m->field[0].c_str()));
            WKPageRunJavaScriptPromptResultListenerCall(static_cast<WKPageRunJavaScriptPromptResultListenerRef>(l), accept ? value.get() : nullptr);
            break;
        }
        case omniModalSelect: {
            int option = -1;
            if (accept && m->focus >= 0 && m->focus < int(m->rows.size()) && m->rows[m->focus].enabled) option = m->rows[m->focus].option;
            auto value = adoptWK(WKStringCreateWithUTF8CString(std::to_string(option).c_str()));
            WKPageRunJavaScriptPromptResultListenerCall(static_cast<WKPageRunJavaScriptPromptResultListenerRef>(l), option >= 0 ? value.get() : nullptr);
            break;
        }
        case omniModalAuth: {
            auto listener = WKAuthenticationChallengeGetDecisionListener(static_cast<WKAuthenticationChallengeRef>(l));
            if (accept && !m->field[0].empty()) {
                auto user = adoptWK(WKStringCreateWithUTF8CString(m->field[0].c_str()));
                auto password = adoptWK(WKStringCreateWithUTF8CString(m->field[1].c_str()));
                // ForSession: kept in the network process's memory for this session; never on disk.
                auto credential = adoptWK(WKCredentialCreate(user.get(), password.get(), kWKCredentialPersistenceForSession));
                WKAuthenticationDecisionListenerUseCredential(listener, credential.get());
            } else if (accept || !omniTabAlive(m->tab)) WKAuthenticationDecisionListenerCancel(listener);
            else WKAuthenticationDecisionListenerRejectProtectionSpaceAndContinue(listener);   // show the server's 401 page
            break;
        }
        default: break;
        }
        WKRelease(l);
    }
    for (auto& f : owned->field) std::fill(f.begin(), f.end(), '\0');   // don't leave the password in freed memory
    if (owned->ask) owned->ask(accept);
    omniPageDirty = omniShellDirty = true;
    omniModalPump();   // the next modal (its tab is brought to the front if needed)
}
// Answers every modal of a tab that is closing or whose web process stopped.
static void omniModalsDropTab(const void* tab)
{
    for (;;) {
        OmniModal* found = nullptr;
        for (auto& m : omniModals) if (m->tab == tab) { found = m.get(); break; }
        if (!found) break;
        found->tab = nullptr;   // closing: auth is cancelled, dialogs get their default answer
        const bool leave = found->kind == omniModalBeforeUnload;
        omniModalAnswer(found, leave);
    }
}
// The modal shown now: the first one for the active tab (or for the shell).
static OmniModal* omniModalCurrent()
{
    for (auto& m : omniModals) if (!m->tab || m->tab == active()) return m.get();
    return nullptr;
}
static bool omniModalVisible() { return omniModalCurrent() != nullptr; }
static void omniModalShown()
{
    // A modal appears: leave page fullscreen, settings and any keyboard; no pending field click.
    if (pageFullscreen && active()) { WKViewRequestExitFullScreen(active()->view.get()); setPageFullscreen(false); }
    settingsOpen = false;
    if (editing && !omniEditingModal) { if (omniKbTarget) omniKbTargetDone(false); else dismissKeyboard(); }
    fieldClickDeadline = 0;
    omniShellDirty = true;
}
// After a modal was added or answered: show the next one. A JavaScript dialog from a background tab
// blocks the shared web process (single-process mode), so its tab is brought to the front.
static void omniModalPump()
{
    if (!omniModalCurrent())
        for (auto& m : omniModals) {
            if (m->kind == omniModalAuth) continue;   // sign-in waits until its tab is shown
            for (size_t i = 0; i < tabs.size(); ++i)
                if (tabs[i].get() == m->tab) { activate(i); notice("Switched to the tab that is showing a dialog"); break; }
            break;
        }
    if (omniModalCurrent()) omniModalShown();
}
static void omniModalPush(std::unique_ptr<OmniModal> m)
{
    omniShoulderCancel(); // OMNI_SHOULDER_DOWNLOADS_V1
    const bool backgroundAuth = m->kind == omniModalAuth && m->tab != active();
    const bool wasShowing = omniModalCurrent() != nullptr;
    omniModals.push_back(std::move(m));
    if (!wasShowing) omniModalPump();
    if (backgroundAuth) notice("A background tab is asking you to sign in");
}
// Shell confirmation ("Clear history?") with the same modal.
[[maybe_unused]] static void omniAsk(const std::string& title, const std::string& message, const std::string& okLabel, std::function<void(bool)> done)
{
    auto m = std::make_unique<OmniModal>();
    m->kind = omniModalAsk; m->title = title; m->message = message; m->okLabel = okLabel; m->ask = std::move(done);
    m->focus = 0;   // Cancel (left) is focused first; the primary button is on the right
    omniModalPush(std::move(m));
}

// --- WebKit callbacks ----------------------------------------------------------------------------
static std::string omniOriginHost(WKSecurityOriginRef origin)
{
    if (!origin) return { };
    return OmniTest::toStd(adoptWK(WKSecurityOriginCopyHost(origin)).get());
}
static void omniDialogDefault(int kind, WKTypeRef listener)
{
    // The answers WebKit gave before the shell handled dialogs (no UI client callbacks).
    if (kind == omniModalAlert) WKPageRunJavaScriptAlertResultListenerCall(static_cast<WKPageRunJavaScriptAlertResultListenerRef>(listener));
    else if (kind == omniModalConfirm) WKPageRunJavaScriptConfirmResultListenerCall(static_cast<WKPageRunJavaScriptConfirmResultListenerRef>(listener), false);
    else if (kind == omniModalBeforeUnload) WKPageRunBeforeUnloadConfirmPanelResultListenerCall(static_cast<WKPageRunBeforeUnloadConfirmPanelResultListenerRef>(listener), true);
    else WKPageRunJavaScriptPromptResultListenerCall(static_cast<WKPageRunJavaScriptPromptResultListenerRef>(listener), nullptr);
}
static void omniSelectParse(OmniModal& m, const std::string& payload)
{
    // Line 0: selected index; then one line per option: flags TAB group TAB label (built by the user script).
    size_t start = 0; int line = 0, selected = -1, option = 0;
    std::string group = "\x01";
    while (start <= payload.size()) {
        size_t end = payload.find('\n', start);
        std::string row = payload.substr(start, end == std::string::npos ? std::string::npos : end - start);
        if (line++ == 0) selected = atoi(row.c_str());
        else {
            size_t t1 = row.find('\t'), t2 = t1 == std::string::npos ? std::string::npos : row.find('\t', t1 + 1);
            if (t2 != std::string::npos && m.rows.size() < 2400) {
                const std::string g = row.substr(t1 + 1, t2 - t1 - 1), label = row.substr(t2 + 1);
                if (!g.empty() && g != group) m.rows.push_back({ g, -1, false });
                group = g;
                if (option == selected) m.focus = int(m.rows.size());
                m.rows.push_back({ label.empty() ? std::string(" ") : label, option, row[0] != 'd', !g.empty(), option == selected });
            }
            ++option;
        }
        if (end == std::string::npos) break;
        start = end + 1;
    }
    if (m.focus >= int(m.rows.size()) || m.rows.empty() || m.rows[m.focus].option < 0)
        for (int i = 0; i < int(m.rows.size()); ++i) if (m.rows[i].enabled) { m.focus = i; break; }
}
static void omniDialogRequest(int kind, WKPageRef page, const std::string& message, const std::string& defaultValue,
    WKSecurityOriginRef origin, WKTypeRef listener)
{
    Tab* tab = omniTabForPage(page);
    const bool select = kind == omniModalPrompt && message == "\x01OMNI_SELECT_V1";
    if (omniTestMode() || !tab) {
        static bool logged = false;
        if (omniTestMode() && !select && !logged) { logged = true; log("dialogs are answered at once in self-test modes (old behaviour)"); }
        omniDialogDefault(kind, listener);
        return;
    }
    auto m = std::make_unique<OmniModal>();
    m->kind = select ? int(omniModalSelect) : kind;
    m->tab = tab;
    m->host = omniBlockerHostOf(tab->url);
    if (m->host.empty()) m->host = omniOriginHost(origin);
    if (!select) {
        // Rate limit: a host the user blocked in this tab gets the default answer, silently.
        if (!tab->omniDialogBlockHost.empty() && tab->omniDialogBlockHost != m->host) tab->omniDialogBlockHost.clear();
        if (!tab->omniDialogBlockHost.empty()) {
            if (SDL_GetTicks() - omniDialogNoticeAt > 5000) { omniDialogNoticeAt = SDL_GetTicks(); notice("Blocked a dialog from " + m->host); }
            omniDialogDefault(kind, listener);
            return;
        }
        const uint32_t now = SDL_GetTicks();
        while (!tab->omniDialogTimes.empty() && now - tab->omniDialogTimes.front() > 10000) tab->omniDialogTimes.pop_front();
        tab->omniDialogTimes.push_back(now);
        m->offerBlock = tab->omniDialogTimes.size() >= 3;
    }
    const std::string originHost = omniOriginHost(origin);
    m->title = select ? std::string("Choose an option") : kind == omniModalBeforeUnload ? std::string("Leave this page?")
        : (originHost.empty() ? std::string("This page") : originHost) + " says";
    m->message = kind == omniModalBeforeUnload ? std::string("Changes you made may not be saved.") : select ? std::string() : message.substr(0, 6000);
    if (kind == omniModalBeforeUnload) { m->okLabel = "Leave"; m->cancelLabel = "Stay"; }
    if (kind == omniModalPrompt && !select) { m->fields = 1; m->field[0] = defaultValue.substr(0, 1024); }
    if (select) omniSelectParse(*m, defaultValue);
    else m->focus = m->fields + omniModalButtons(*m) - 1;   // the primary button
    m->listeners.push_back(WKRetain(listener));
    omniModalPush(std::move(m));
}
static void omniDialogsInstall(WKPageUIClientV19& ui)
{
    ui.runJavaScriptAlert = [](WKPageRef page, WKStringRef text, WKFrameRef, WKSecurityOriginRef origin, WKPageRunJavaScriptAlertResultListenerRef listener, const void*) {
        omniDialogRequest(omniModalAlert, page, OmniTest::toStd(text), { }, origin, listener);
    };
    ui.runJavaScriptConfirm = [](WKPageRef page, WKStringRef text, WKFrameRef, WKSecurityOriginRef origin, WKPageRunJavaScriptConfirmResultListenerRef listener, const void*) {
        omniDialogRequest(omniModalConfirm, page, OmniTest::toStd(text), { }, origin, listener);
    };
    ui.runJavaScriptPrompt = [](WKPageRef page, WKStringRef text, WKStringRef value, WKFrameRef, WKSecurityOriginRef origin, WKPageRunJavaScriptPromptResultListenerRef listener, const void*) {
        omniDialogRequest(omniModalPrompt, page, OmniTest::toStd(text), OmniTest::toStd(value), origin, listener);
    };
    ui.runBeforeUnloadConfirmPanel = [](WKPageRef page, WKStringRef text, WKFrameRef, WKPageRunBeforeUnloadConfirmPanelResultListenerRef listener, const void*) {
        omniDialogRequest(omniModalBeforeUnload, page, OmniTest::toStd(text), { }, nullptr, listener);
    };
}
static void omniAuthChallenge(WKPageRef page, WKAuthenticationChallengeRef challenge, const void*)
{
    WKAuthenticationDecisionListenerRef listener = WKAuthenticationChallengeGetDecisionListener(challenge);
    WKProtectionSpaceRef space = WKAuthenticationChallengeGetProtectionSpace(challenge);
    const WKProtectionSpaceAuthenticationScheme scheme = WKProtectionSpaceGetAuthenticationScheme(space);
    const bool askable = scheme == kWKProtectionSpaceAuthenticationSchemeDefault || scheme == kWKProtectionSpaceAuthenticationSchemeHTTPBasic
        || scheme == kWKProtectionSpaceAuthenticationSchemeHTTPDigest || scheme == kWKProtectionSpaceAuthenticationSchemeNTLM
        || scheme == kWKProtectionSpaceAuthenticationSchemeNegotiate;
    Tab* tab = omniTabForPage(page);
    const int failures = WKAuthenticationChallengeGetPreviousFailureCount(challenge);
    // Server trust (certificate errors), client certificates, other schemes and self-test modes: the
    // challenge is rejected, which ends exactly like the default handling before (curl fails the load
    // with the certificate error; a 401 page is shown as it is). Never UseCredential here.
    if (!askable || !tab || omniTestMode() || failures >= 5) {
        WKAuthenticationDecisionListenerRejectProtectionSpaceAndContinue(listener);
        return;
    }
    const std::string host = OmniTest::toStd(adoptWK(WKProtectionSpaceCopyHost(space)).get());
    const std::string realm = OmniTest::toStd(adoptWK(WKProtectionSpaceCopyRealm(space)).get());
    const int port = WKProtectionSpaceGetPort(space);
    const bool proxy = WKProtectionSpaceGetIsProxy(space);
    // One sign-in per host + realm: further challenges (subresources) wait for the same answer.
    const std::string key = host + ":" + std::to_string(port) + "\n" + realm;
    for (auto& m : omniModals)
        if (m->kind == omniModalAuth && m->tab == tab && m->host == key) { m->listeners.push_back(WKRetain(challenge)); return; }
    auto m = std::make_unique<OmniModal>();
    m->kind = omniModalAuth; m->tab = tab; m->host = key; m->fields = 2;
    m->title = proxy ? "Proxy sign-in" : "Sign in";
    m->message = host + (port && port != 80 && port != 443 ? ":" + std::to_string(port) : std::string()) + " asks for a username and password."
        + (realm.empty() ? std::string() : "\nSite says: \"" + realm.substr(0, 200) + "\"");
    m->insecure = !WKProtectionSpaceGetReceivesCredentialSecurely(space);
    m->failed = failures > 0;
    m->okLabel = "Sign in";
    if (WKCredentialRef proposed = WKAuthenticationChallengeGetProposedCredential(challenge))
        m->field[0] = OmniTest::toStd(adoptWK(WKCredentialCopyUser(proposed)).get());
    m->focus = 0;
    m->listeners.push_back(WKRetain(challenge));
    omniModalPush(std::move(m));
}
// <select> menus: see the header of patch-shell-dialogs.py. Not installed in self-test modes.
// OMNI_FAST_PAGE_V1: with the page painted at half resolution, WebKit's devicePixelRatio is half the
// display's. Sites (YouTube) pick video quality from it, so report the display's ratio instead.
static void omniFastPageInstall()
{
    if (omniPageScale >= 1) return;
    const char* source = R"JS((function(){try{var d=Object.getOwnPropertyDescriptor(window,'devicePixelRatio')||Object.getOwnPropertyDescriptor(Window.prototype,'devicePixelRatio');if(!d||!d.get)return;var g=d.get;Object.defineProperty(window,'devicePixelRatio',{configurable:true,enumerable:true,get:function(){return g.call(window)*2;}});}catch(e){}})();)JS";
    auto text = adoptWK(WKStringCreateWithUTF8CString(source));
    auto script = adoptWK(WKUserScriptCreateWithSource(text.get(), kWKInjectAtDocumentStart, false));   // all frames
    omniBlockerAddShellScript(script.get());
}
static void omniSelectInstall()
{
    if (omniTestMode()) return;
    static const char* source = R"JS((function(){if(window.__omniSelectV1)return;window.__omniSelectV1=1;var P=window.prompt;
function clean(s){return String(s==null?'':s).replace(/[\t\r\n]+/g,' ').trim().slice(0,200);}
addEventListener('mousedown',function(e){
if(e.button!==0||!e.isTrusted)return;
var t=e.composedPath?e.composedPath()[0]:e.target;if(!t||t.nodeType!==1||!t.closest)return;
var s=t.closest('select');if(!s||s.multiple||s.size>1||s.disabled)return;
var o=s.options;if(!o.length)return;
e.preventDefault();try{s.focus();}catch(x){}
var lines=[String(s.selectedIndex)];
for(var i=0;i<o.length&&i<2000;i++){var p=o[i].parentNode,g=p&&p.tagName==='OPTGROUP';lines.push((o[i].disabled||(g&&p.disabled)?'d':'-')+'\t'+(g?clean(p.label)||' ':'')+'\t'+clean(o[i].label||o[i].text));}
var t0=Date.now(),r=P.call(window,'\u0001OMNI_SELECT_V1',lines.join('\n')),n=r===null?-1:parseInt(r,10);
if(r===null&&Date.now()-t0<40){n=s.selectedIndex;for(var k=0;k<o.length;k++){n=(n+1)%o.length;if(!o[n].disabled)break;}}
if(!(n>=0&&n<o.length)||n===s.selectedIndex)return;
s.selectedIndex=n;s.dispatchEvent(new Event('input',{bubbles:true}));s.dispatchEvent(new Event('change',{bubbles:true}));
},true);})();)JS";
    auto text = adoptWK(WKStringCreateWithUTF8CString(source));
    auto script = adoptWK(WKUserScriptCreateWithSource(text.get(), kWKInjectAtDocumentStart, false));   // all frames
    omniBlockerAddShellScript(script.get());
}

// --- layout and drawing --------------------------------------------------------------------------
static int omniCodepointWidth(int id, const std::string& cp) { return omniTextWidthPx(id, cp); }
// Greedy word wrap to maxW layout px (long words break between code points).
static std::vector<std::string> omniWrap(const std::string& input, int id, int maxW, size_t maxLines)
{
    std::vector<std::string> out;
    const int limit = physical(maxW);
    std::string textIn = input;
    for (auto& c : textIn) if (c == '\t' || c == '\r') c = ' ';
    size_t start = 0;
    while (out.size() < maxLines) {
        const size_t nl = textIn.find('\n', start);
        const std::string para = textIn.substr(start, nl == std::string::npos ? std::string::npos : nl - start);
        std::string line;
        size_t i = 0;
        while (i < para.size() && out.size() < maxLines) {
            const size_t sp = para.find(' ', i);
            const std::string word = para.substr(i, sp == std::string::npos ? std::string::npos : sp - i);
            const std::string candidate = line.empty() ? word : line + " " + word;
            if (omniTextWidthPx(id, candidate) <= limit) line = candidate;
            else if (!line.empty()) { out.push_back(line); line.clear(); continue; }   // the word starts the next line
            else {
                std::string part; int w = 0;
                for (size_t k = 0; k < word.size();) {
                    const unsigned char c = word[k];
                    const size_t n = c < 0x80 ? 1 : (c >> 5) == 6 ? 2 : (c >> 4) == 14 ? 3 : (c >> 3) == 30 ? 4 : 1;
                    const std::string cp = word.substr(k, n);
                    const int cw = omniCodepointWidth(id, cp);
                    if (w + cw > limit && !part.empty()) { out.push_back(part); part.clear(); w = 0; }
                    part += cp; w += cw; k += n;
                }
                line = part;
            }
            i = sp == std::string::npos ? para.size() : sp + 1;
        }
        out.push_back(line);
        if (nl == std::string::npos) break;
        start = nl + 1;
    }
    while (out.size() > 1 && out.back().empty()) out.pop_back();
    return out;
}
struct OmniRect { int x = 0, y = 0, w = 0, h = 0; bool hit(int px, int py) const { return w > 0 && px >= x && px < x + w && py >= y && py < y + h; } };
struct OmniModalLayout {
    OmniRect panel, message, list;
    OmniRect field[2], fieldLabel[2];
    OmniRect button[3];
    int lineHeight = 30, visibleLines = 0, rowHeight = 40, visibleRows = 0;
    bool compact = false;
};
constexpr int omniModalW = 760, omniModalPad = 28;
static OmniModalLayout omniModalLayout(OmniModal& m)
{
    OmniModalLayout L;
    L.compact = omniEditingModal == &m && editing;   // the keyboard is open below: title and fields only
    const int w = m.kind == omniModalSelect ? 640 : omniModalW;
    const int x = (width - w) / 2, inner = w - 2 * omniModalPad;
    if (m.lines.empty() && !m.message.empty()) m.lines = omniWrap(m.message, omniBody, inner, 400);
    int h = omniModalPad + 34;   // title
    if (m.kind == omniModalSelect) {
        L.visibleRows = std::min<int>(int(m.rows.size()), 11);
        L.list = { x + 12, 0, w - 24, L.visibleRows * L.rowHeight };
        h += 10 + L.list.h + 22;
    } else {
        const int maxLines = L.compact ? (m.fields > 1 ? 0 : 1) : m.fields ? 5 : 9;
        L.visibleLines = std::min<int>(int(m.lines.size()), maxLines);
        if (L.visibleLines) h += 8 + L.visibleLines * L.lineHeight;
        if (m.failed || m.insecure) h += L.compact ? 0 : 30;
        h += m.fields * (m.kind == omniModalAuth ? 84 : 60);
        if (!L.compact) h += 20 + 46;   // buttons
        h += L.compact ? omniModalPad - 14 : omniModalPad - 4;
    }
    const int y = L.compact ? 116 : std::max(70, (height - h) / 2);   // compact: ends above the keyboard (y 374)
    L.panel = { x, y, w, h };
    int cy = y + omniModalPad + 34;
    if (m.kind == omniModalSelect) { L.list.y = cy + 10; return L; }
    if (L.visibleLines) { L.message = { x + omniModalPad, cy + 8, inner, L.visibleLines * L.lineHeight }; cy += 8 + L.message.h; }
    if ((m.failed || m.insecure) && !L.compact) cy += 30;
    for (int i = 0; i < m.fields; ++i) {
        if (m.kind == omniModalAuth) { L.fieldLabel[i] = { x + omniModalPad, cy + 8, inner, 20 }; cy += 36; }
        else cy += 12;
        L.field[i] = { x + omniModalPad, cy, inner, 44 }; cy += 48;
    }
    if (!L.compact) {
        const int n = omniModalButtons(m);
        int bx = x + w - omniModalPad;
        const int by = y + h - omniModalPad + 4 - 46;
        for (int i = n - 1; i >= 0; --i) {
            const int role = omniModalButtonRole(m, i);
            const int bw = std::max(132, int(omniTextWidthPx(omniSmallBold, omniModalButtonLabel(m, role)) / displayScale + 0.5) + 48);
            if (role == 2) L.button[i] = { x + omniModalPad, by, bw, 46 };   // Block dialogs: on the left
            else { bx -= bw; L.button[i] = { bx, by, bw, 46 }; bx -= 12; }
        }
    }
    return L;
}
static void omniModalClampList(OmniModal& m, const OmniModalLayout& L)
{
    const int rows = int(m.rows.size());
    if (m.focus < m.scroll) m.scroll = m.focus;
    if (m.focus >= m.scroll + L.visibleRows) m.scroll = m.focus - L.visibleRows + 1;
    m.scroll = std::clamp(m.scroll, 0, std::max(0, rows - L.visibleRows));
}
static void omniDrawModal(OmniModal& m)
{
    const OmniTheme& T = omniTheme();
    OmniModalLayout L = omniModalLayout(m);
    const float fadeT = omniPanelT(omniPanelModal); // OMNI_POLISH_V1: backdrop and panel fade in
    if (!L.compact) omniRectPx({ 0, 0, canvas->w, canvas->h }, { 0, 0, 0, 255 }, uint8_t(120 * fadeT));   // dim what is behind (not the keyboard)
    struct FadeScope { ~FadeScope() { omniFadeEnd(); } } fadeScope;
    omniFadeBegin(L.panel.x - 30, L.panel.y - 30, L.panel.w + 60, L.panel.h + 60, fadeT);
    omniShadow(L.panel.x, L.panel.y, L.panel.w, L.panel.h, omniRadius + 2, 22, 160, 6);
    fillRounded(L.panel.x, L.panel.y, L.panel.w, L.panel.h, omniRadius + 2, T.panel);
    fillRounded(L.panel.x, L.panel.y, L.panel.w, 4, 2, T.accent, 255, omniCornersTop);
    const int titleY = L.panel.y + omniModalPad + 12;
    int tx = L.panel.x + omniModalPad;
    if (m.kind == omniModalAuth) { omniIcon(omniIconLock, tx + 7, titleY, m.insecure ? omniWarn : T.accent); tx += 24; }
    omniLabel(m.title, tx, titleY, omniBodyBold, T.ink, 0, L.panel.x + L.panel.w - omniModalPad - tx);
    if (m.kind == omniModalSelect) {
        omniModalClampList(m, L);
        const int rows = int(m.rows.size());
        for (int r = 0; r < L.visibleRows && m.scroll + r < rows; ++r) {
            const OmniSelectRow& row = m.rows[m.scroll + r];
            const int ry = L.list.y + r * L.rowHeight;
            const bool sel = m.focus == m.scroll + r;
            if (row.option < 0) { omniLabel(row.label, L.list.x + 14, ry + L.rowHeight / 2.f, omniSmallBold, T.inkDim, 0, L.list.w - 28); continue; }
            if (sel) fillRounded(L.list.x, ry + 2, L.list.w, L.rowHeight - 4, omniRadius, T.accent);
            else if (pointerX >= L.list.x && pointerX < L.list.x + L.list.w && pointerY >= ry && pointerY < ry + L.rowHeight && row.enabled)
                fillRounded(L.list.x, ry + 2, L.list.w, L.rowHeight - 4, omniRadius, T.hover);
            omniLabel(row.label, L.list.x + (row.grouped ? 38 : 18), ry + L.rowHeight / 2.f, omniBody,
                sel ? T.accentInk : row.enabled ? T.ink : T.inkFaint, 0, L.list.w - 80);
            if (row.current) omniIcon(omniIconCheck, L.list.x + L.list.w - 26, ry + L.rowHeight / 2.f, sel ? T.accentInk : T.accent);   // the value now
        }
        if (m.scroll > 0) omniLabel("\xe2\x96\xb2", L.panel.x + L.panel.w - 30, L.list.y - 12, omniSmall, T.inkDim, 1);
        if (m.scroll + L.visibleRows < rows) omniLabel("\xe2\x96\xbc", L.panel.x + L.panel.w - 30, L.list.y + L.list.h + 10, omniSmall, T.inkDim, 1);
        char count[48]; snprintf(count, sizeof(count), "%d options", int(std::count_if(m.rows.begin(), m.rows.end(), [](const OmniSelectRow& r) { return r.option >= 0; })));
        omniLabel(count, L.panel.x + L.panel.w - omniModalPad, titleY, omniSmall, T.inkFaint, 2);
        return;
    }
    // Message (scrolls a line at a time; arrows show there is more).
    const int maxScroll = std::max(0, int(m.lines.size()) - L.visibleLines);
    m.scroll = std::clamp(m.scroll, 0, maxScroll);
    for (int i = 0; i < L.visibleLines; ++i)
        omniLabel(m.lines[m.scroll + i], L.message.x, L.message.y + i * L.lineHeight + L.lineHeight / 2.f, omniBody, T.ink);
    if (maxScroll) {
        const int ax = L.panel.x + L.panel.w - 18;
        if (m.scroll > 0) omniLabel("\xe2\x96\xb2", ax, L.message.y + 10, omniSmall, T.accent, 1);
        if (m.scroll < maxScroll) omniLabel("\xe2\x96\xbc", ax, L.message.y + L.message.h - 10, omniSmall, T.accent, 1);
    }
    if ((m.failed || m.insecure) && !L.compact) {
        const int wy = L.message.w ? L.message.y + L.message.h + 16 : titleY + 40;
        omniLabel(m.failed ? "That username or password was not accepted. Try again." : "This connection is not secure: the password is sent unencrypted.",
            L.panel.x + omniModalPad, wy, omniSmall, m.failed ? omniBad : omniWarn, 0, L.panel.w - 2 * omniModalPad);
    }
    const int fieldCount = m.fields;
    for (int i = 0; i < fieldCount; ++i) {
        const OmniRect& f = L.field[i];
        const bool focused = m.focus == i, typing = omniKbTarget == &m.field[i];
        if (L.fieldLabel[i].w) omniLabel(i == 0 ? "Username" : "Password", L.fieldLabel[i].x, L.fieldLabel[i].y + 10, omniSmall, T.inkDim);
        if (focused || typing) fillRounded(f.x - 2, f.y - 2, f.w + 4, f.h + 4, omniRadius + 1, T.accent);
        fillRounded(f.x, f.y, f.w, f.h, omniRadius, T.field);
        std::string shown = m.field[i];
        if (m.kind == omniModalAuth && i == 1) {
            std::string dots;
            for (size_t k = 0; k < shown.size(); ++k) if ((static_cast<unsigned char>(shown[k]) & 0xc0) != 0x80) dots += "\xe2\x80\xa2";
            shown = dots;
        }
        if (typing) { // OMNI_KEYBOARD_V2: the bar at the caret, not always at the end
            omniKbEnsure();
            const size_t before = omniCpCount(m.field[i].substr(0, std::min(omniKb.caret, m.field[i].size())));
            shown.insert(omniCpOffset(shown, before), "|");
        }
        // Show the end of a long value (where typing happens).
        const int room = physical(f.w - 28);
        while (!shown.empty() && omniTextWidthPx(omniBody, shown) > room) {
            size_t cut = 1;
            while (cut < shown.size() && (static_cast<unsigned char>(shown[cut]) & 0xc0) == 0x80) ++cut;
            shown.erase(0, cut);
        }
        if (shown.empty() && !typing) { // OMNI_POLISH_V1: the A glyph of the chosen controller (was the letter "A" in text)
            faceIcon(f.x + 26, f.y + f.h / 2, 0, playStationIcons);
            omniLabel("to type", f.x + 46, f.y + f.h / 2.f, omniSmall, T.inkDim);
        }
        else omniLabel(shown, f.x + 14, f.y + f.h / 2.f, omniBody, T.ink);
    }
    if (L.compact) return;
    const int n = omniModalButtons(m);
    for (int i = 0; i < n; ++i) {
        const OmniRect& b = L.button[i];
        const int role = omniModalButtonRole(m, i);
        const bool focused = m.focus == fieldCount + i, hover = b.hit(int(pointerX), int(pointerY));
        if (focused) fillRounded(b.x - 2, b.y - 2, b.w + 4, b.h + 4, omniRadius + 1, T.ink);
        fillRounded(b.x, b.y, b.w, b.h, omniRadius, role == 0 ? T.accent : hover ? T.hover : T.key);
        omniLabel(omniModalButtonLabel(m, role), b.x + b.w / 2.f, b.y + b.h / 2.f, omniSmallBold, role == 0 ? T.accentInk : role == 2 ? omniWarn : T.ink, 1);
    }
}
// Hints in the bottom bar area while a modal is shown (drawn over the bar).
static void omniModalHints(const OmniModal& m)
{
    const OmniTheme& T = omniTheme();
    if (editing) return;   // the keyboard's own hints
    fill(0, height - bottom, width, bottom, T.bar);
    omniRectPx({ 0, physical(height - bottom), renderWidth, 1 }, T.line);
    // OMNI_POLISH_V1: shared hint layout (same items and words as before).
    if (m.kind == omniModalSelect) { omniHints({ { 0, "Choose" }, { 1, "Cancel" } }, {}, "D-pad: move   L1/R1: page"); return; }
    std::vector<OmniHint> items { { 0, "Press" } };
    if (m.fields) items.push_back({ 3, "Type" });
    items.push_back({ 1, m.kind == omniModalAlert ? "OK" : m.kind == omniModalBeforeUnload ? "Stay" : "Cancel" });
    omniHints(items, {}, "D-pad: choose   Right stick: scroll");
}

// --- input ---------------------------------------------------------------------------------------
static void omniModalEditField(OmniModal& m, int i)
{
    if (i < 0 || i >= m.fields) return;
    m.focus = i;
    omniEditingModal = &m;
    const char* label = m.kind == omniModalAuth ? (i == 0 ? "Username" : "Password (hidden)") : "Type your answer";
    omniKbEdit(&m.field[i], label, [mp = &m, i](bool submitted) {
        // The modal may be gone (answered elsewhere) by now: look it up before touching it.
        for (auto& owned : omniModals) if (owned.get() == mp) {
            omniEditingModal = nullptr;
            if (!submitted) return;
            if (mp->kind == omniModalAuth && i == 0) { omniModalEditField(*mp, 1); return; }   // then the password
            mp->focus = mp->fields + omniModalButtons(*mp) - 1;    // Go: the primary button is next
            if (mp->kind == omniModalPrompt || (mp->kind == omniModalAuth && i == 1)) omniModalAnswer(mp, true);
            return;
        }
        omniEditingModal = nullptr;
    });
}
static void omniModalPress(OmniModal& m, int focus)
{
    if (m.kind == omniModalSelect) { m.focus = focus; if (focus >= 0 && focus < int(m.rows.size()) && m.rows[focus].enabled) omniModalAnswer(&m, true); return; }
    if (focus < m.fields) { omniModalEditField(m, focus); return; }
    const int role = omniModalButtonRole(m, focus - m.fields);
    omniModalAnswer(&m, role == 0, role == 2);
}
static int omniModalHit(OmniModal& m, int x, int y)
{
    OmniModalLayout L = omniModalLayout(m);
    if (m.kind == omniModalSelect) {
        if (!L.list.hit(x, y)) return -1;
        const int row = m.scroll + (y - L.list.y) / L.rowHeight;
        return row < int(m.rows.size()) && m.rows[row].option >= 0 ? row : -1;
    }
    for (int i = 0; i < m.fields; ++i) if (L.field[i].hit(x, y)) return i;
    for (int i = 0; i < omniModalButtons(m); ++i) if (L.button[i].hit(x, y)) return m.fields + i;
    return -1;
}
static void omniModalScrollBy(OmniModal& m, int lines)
{
    if (m.kind == omniModalSelect) {
        int f = m.focus;
        for (int k = 0; k < std::abs(lines); ++k) {
            int g = f;
            do g += lines > 0 ? 1 : -1; while (g >= 0 && g < int(m.rows.size()) && !m.rows[g].enabled);
            if (g < 0 || g >= int(m.rows.size())) break;
            f = g;
        }
        m.focus = f;
        return;
    }
    m.scroll += lines;   // clamped when drawn
}
static bool omniModalButtonInput(OmniModal& m, int b)
{
    if (b == SDL_CONTROLLER_BUTTON_START) return false;        // Start still exits Omni
    if (editing && omniKbTarget) return false;                 // the keyboard is editing this modal's field
    const int count = m.kind == omniModalSelect ? int(m.rows.size()) : m.fields + omniModalButtons(m);
    const int hover = omniModalHit(m, int(pointerX), int(pointerY));
    switch (b) {
    case SDL_CONTROLLER_BUTTON_A: omniModalPress(m, hover >= 0 ? hover : m.focus); break;
    case SDL_CONTROLLER_BUTTON_B:
        omniModalAnswer(&m, m.kind == omniModalAlert);         // alert: OK; everything else: Cancel / Stay
        break;
    case SDL_CONTROLLER_BUTTON_Y: if (m.fields) omniModalEditField(m, m.focus < m.fields ? m.focus : 0); break;
    case SDL_CONTROLLER_BUTTON_DPAD_UP:
        if (m.kind == omniModalSelect) omniModalScrollBy(m, -1);
        else if (m.focus >= m.fields && m.fields) m.focus = m.fields - 1;
        else if (m.focus > 0 && m.focus < m.fields) --m.focus;
        else --m.scroll;
        break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN:
        if (m.kind == omniModalSelect) omniModalScrollBy(m, 1);
        else if (m.focus < m.fields - 1) ++m.focus;
        else if (m.focus < m.fields) m.focus = count - 1;
        else ++m.scroll;
        break;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: if (m.kind != omniModalSelect && m.focus > m.fields) --m.focus; break;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: if (m.kind != omniModalSelect && m.focus >= m.fields && m.focus < count - 1) ++m.focus; break;
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: omniModalScrollBy(m, m.kind == omniModalSelect ? -10 : -5); break;
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: omniModalScrollBy(m, m.kind == omniModalSelect ? 10 : 5); break;
    default: break;
    }
    return true;
}

// --- overlay entry points (called from button(), click(), mouse(), scroll(), draw()) --------------
static bool omniOverlayOpen()
{
    if (omniModalVisible()) return true;
    for (auto& layer : omniOverlayLayers()) if (layer.blocksPage && layer.open()) return true;
    return false;
}
static bool omniOverlayButton(int button)
{
    if (OmniModal* m = omniModalCurrent()) return omniModalButtonInput(*m, button);
    for (auto& layer : omniOverlayLayers()) if (layer.open() && layer.button && layer.button(button)) return true;
    return false;
}
static bool omniOverlayClick(int x, int y)
{
    if (OmniModal* m = omniModalCurrent()) {
        if (editing && omniKbTarget) return false;   // keyboard keys are clicked as usual
        const int hit = omniModalHit(*m, x, y);
        if (hit >= 0) omniModalPress(*m, hit);
        omniShellDirty = true;
        return true;
    }
    for (auto& layer : omniOverlayLayers()) if (layer.open() && layer.click && layer.click(x, y)) { omniShellDirty = true; return true; }
    return false;
}
static bool omniOverlayScroll(double amount)
{
    if (OmniModal* m = omniModalCurrent()) {
        m->scrollAcc -= float(amount);
        const int step = m->kind == omniModalSelect ? 40 : 30;
        while (m->scrollAcc >= step) { m->scrollAcc -= step; omniModalScrollBy(*m, 1); }
        while (m->scrollAcc <= -step) { m->scrollAcc += step; omniModalScrollBy(*m, -1); }
        omniShellDirty = true;
        return true;
    }
    for (auto& layer : omniOverlayLayers()) if (layer.open() && layer.scroll && layer.scroll(amount)) { omniShellDirty = true; return true; }
    return false;
}
static void omniOverlayDraw()
{
    for (auto& layer : omniOverlayLayers()) if (layer.open() && layer.draw) layer.draw();
    if (OmniModal* m = omniModalCurrent()) { omniDrawModal(*m); omniModalHints(*m); }
}

// OMNI_EVERYDAY_V1 ------------------------------------------------------------------------------
// History, address suggestions, session restore, new-tab page, find, per-site zoom and user agent,
// private tabs, clear data, downloads, reader view, and the Browser tools menu that reaches them.
#ifndef OMNI_DATA_DIR
#define OMNI_DATA_DIR "/data/omni/"
#endif
static std::string omniData(const char* name) { return std::string(OMNI_DATA_DIR) + name; }
static const char* const omniDesktopUA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15";   // the UA newTab() sets (default)
static const char* const omniMobileUAString = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";

// --- background writer: every file write leaves the main thread ----------------------------------
struct OmniIoJob { std::string path, data; bool append; };
// Never destroyed (heap): a static destructor must not wait on a condition variable the writer sleeps on.
static std::mutex& omniIoLock = *new std::mutex;
static std::condition_variable& omniIoWake = *new std::condition_variable;
static std::condition_variable& omniIoIdle = *new std::condition_variable;
static std::deque<OmniIoJob>& omniIoJobs = *new std::deque<OmniIoJob>;
static bool omniIoBusy = false;
static std::thread* omniIoThread = nullptr;   // never destroyed (the process ends with _exit)
static void omniIoMain()
{
    std::unique_lock<std::mutex> lock(omniIoLock);
    for (;;) {
        omniIoWake.wait(lock, [] { return !omniIoJobs.empty(); });
        OmniIoJob job = std::move(omniIoJobs.front());
        omniIoJobs.pop_front();
        omniIoBusy = true;
        lock.unlock();
        if (job.append) {
            if (FILE* f = fopen(job.path.c_str(), "a")) { fwrite(job.data.data(), 1, job.data.size(), f); fclose(f); }
        } else {
            const std::string tmp = job.path + ".tmp";
            if (FILE* f = fopen(tmp.c_str(), "w")) {
                const bool ok = fwrite(job.data.data(), 1, job.data.size(), f) == job.data.size();
                if (!fclose(f) && ok) rename(tmp.c_str(), job.path.c_str());
            }
        }
        lock.lock();
        omniIoBusy = false;
        omniIoIdle.notify_all();
    }
}
static void omniIoQueue(const std::string& path, std::string data, bool append)
{
    {
        std::lock_guard<std::mutex> lock(omniIoLock);
        // A full rewrite carries the whole state: earlier queued writes of that file are dropped.
        if (!append) omniIoJobs.erase(std::remove_if(omniIoJobs.begin(), omniIoJobs.end(), [&](const OmniIoJob& j) { return j.path == path; }), omniIoJobs.end());
        omniIoJobs.push_back({ path, std::move(data), append });
        if (!omniIoThread) omniIoThread = new std::thread(omniIoMain);
    }
    omniIoWake.notify_one();
}
static void omniIoFlush()
{
    std::unique_lock<std::mutex> lock(omniIoLock);
    omniIoIdle.wait_for(lock, std::chrono::milliseconds(800), [] { return omniIoJobs.empty() && !omniIoBusy; });
}
static std::string omniOneLine(std::string s, size_t max)
{
    for (auto& c : s) if (c == '\t' || c == '\n' || c == '\r') c = ' ';
    if (s.size() > max) { size_t cut = max; while (cut && (static_cast<unsigned char>(s[cut]) & 0xc0) == 0x80) --cut; s.resize(cut); }
    return s;
}
static std::string omniLower(std::string s) { for (auto& c : s) if (c >= 'A' && c <= 'Z') c += 'a' - 'A'; return s; }
static bool omniWebURL(const std::string& url) { return url.rfind("https://", 0) == 0 || url.rfind("http://", 0) == 0; }
static std::string omniHtmlEscape(const std::string& s)
{
    std::string out;
    for (char c : s) {
        if (c == '&') out += "&amp;"; else if (c == '<') out += "&lt;"; else if (c == '>') out += "&gt;";
        else if (c == '"') out += "&quot;"; else if (c == '\'') out += "&#39;"; else out += c;
    }
    return out;
}
static std::string omniCss(SDL_Color c) { char b[16]; snprintf(b, sizeof(b), "#%02x%02x%02x", c.r, c.g, c.b); return b; }

// --- history -------------------------------------------------------------------------------------
struct OmniVisit { long long time; std::string url, title; };
static std::vector<OmniVisit> omniHistory;   // oldest first
static bool omniHistoryLoaded = false;
constexpr size_t omniHistoryMax = 2000;
static void omniHistoryLoad()
{
    if (omniHistoryLoaded) return;
    omniHistoryLoaded = true;
    FILE* f = fopen(omniData("history.txt").c_str(), "r");
    if (!f) return;
    char line[4096];
    while (fgets(line, sizeof(line), f)) {
        std::string s(line);
        while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
        const size_t a = s.find('\t'), b = a == std::string::npos ? a : s.find('\t', a + 1);
        if (b == std::string::npos) continue;
        OmniVisit v { atoll(s.substr(0, a).c_str()), s.substr(a + 1, b - a - 1), s.substr(b + 1) };
        if (omniWebURL(v.url)) omniHistory.push_back(std::move(v));
    }
    fclose(f);
    if (omniHistory.size() > omniHistoryMax) omniHistory.erase(omniHistory.begin(), omniHistory.end() - omniHistoryMax);
}
static void omniHistoryRewrite()
{
    std::string data;
    for (auto& v : omniHistory) data += std::to_string(v.time) + "\t" + v.url + "\t" + v.title + "\n";
    omniIoQueue(omniData("history.txt"), std::move(data), false);
}
static void omniHistoryAdd(const std::string& url, const std::string& rawTitle)
{
    omniHistoryLoad();
    const std::string u = omniOneLine(url, 2048), title = omniOneLine(rawTitle, 300);
    const long long now = time(nullptr);
    if (!omniHistory.empty() && omniHistory.back().url == u) { omniHistory.back().time = now; omniHistory.back().title = title; return; }   // reload
    omniHistory.push_back({ now, u, title });
    omniIoQueue(omniData("history.txt"), std::to_string(now) + "\t" + u + "\t" + title + "\n", true);
    if (omniHistory.size() > omniHistoryMax + 200) {   // keep about 2000: trim the oldest now and then
        omniHistory.erase(omniHistory.begin(), omniHistory.end() - omniHistoryMax);
        omniHistoryRewrite();
    }
}

// --- per-site settings: zoom, mobile user agent ---------------------------------------------------
static std::unordered_map<std::string, double> omniSiteZoom;
static std::unordered_set<std::string> omniMobileHosts;
static bool omniPrefsLoaded = false;
static void omniPrefsLoad()
{
    if (omniPrefsLoaded) return;
    omniPrefsLoaded = true;
    char line[600];
    if (FILE* f = fopen(omniData("site-zoom.txt").c_str(), "r")) {
        while (fgets(line, sizeof(line), f)) {
            std::string s(line);
            const size_t t = s.find('\t');
            const double z = t == std::string::npos ? 0 : atof(s.c_str() + t + 1);
            if (z >= 0.3 && z <= 3.0) omniSiteZoom[s.substr(0, t)] = z;
        }
        fclose(f);
    }
    if (FILE* f = fopen(omniData("site-ua.txt").c_str(), "r")) {
        while (fgets(line, sizeof(line), f)) {
            std::string s(line);
            const size_t t = s.find_first_of("\t\r\n");
            if (s.compare(t == std::string::npos ? s.size() : t, 7, "\tmobile") == 0) omniMobileHosts.insert(s.substr(0, t));
        }
        fclose(f);
    }
}
static void omniPrefsSave()
{
    std::string zoom, ua;
    char z[32];
    for (auto& [host, factor] : omniSiteZoom) { snprintf(z, sizeof(z), "%.3f", factor); zoom += host + "\t" + z + "\n"; }
    for (auto& host : omniMobileHosts) ua += host + "\tmobile\n";
    omniIoQueue(omniData("site-zoom.txt"), zoom, false);
    omniIoQueue(omniData("site-ua.txt"), ua, false);
}
static double omniZoomFor(const std::string& host)
{
    auto found = omniSiteZoom.find(host);
    return found == omniSiteZoom.end() ? omniFxDefaultZoom() : found->second; // OMNI_FEATURES_V1: default zoom setting
}
// Page zoom = displayScale (devicePixelRatio, relied on for video quality) times the site's zoom.
static void omniApplySiteZoom(Tab* tab)
{
    if (!tab || omniTestMode()) return;
    const double wanted = displayScale * omniPageScale * omniZoomFor(omniBlockerHostOf(tab->url)); // OMNI_FAST_PAGE_V1
    if (std::fabs(WKPageGetPageZoomFactor(tab->page) - wanted) > 1e-6) WKPageSetPageZoomFactor(tab->page, wanted);
    omniFxApplyTextZoom(tab); // OMNI_FEATURES_V1: text size setting
}
static void omniApplyUserAgent(Tab* tab, const std::string& url)
{
    if (!tab || omniTestMode()) return;
    const bool mobile = omniMobileHosts.count(omniBlockerHostOf(url)) > 0;
    if (mobile == tab->omniMobileUA) return;
    tab->omniMobileUA = mobile;
    auto ua = adoptWK(WKStringCreateWithUTF8CString(mobile ? omniMobileUAString : omniDesktopUA));
    WKPageSetCustomUserAgent(tab->page, ua.get());
}

// --- new-tab page --------------------------------------------------------------------------------
static const char* const omniNewTabPrefix = "data:text/html;charset=utf-8,%3C%21--omni-newtab--%3E";
static std::string omniPercentEncode(const std::string& s)
{
    std::string out;
    for (unsigned char c : s) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' || c == '~') out += char(c);
        else { char hex[4]; snprintf(hex, sizeof(hex), "%%%02X", c); out += hex; }
    }
    return out;
}
// OMNI_POLISH_V1: the new-tab page takes its colours from CSS variables, so a theme change can
// restyle an open page (omniPolishTick) instead of leaving the old theme until it is reopened.
static std::string omniNewTabVars(const OmniTheme& T)
{
    std::string v;
    const std::pair<const char*, SDL_Color> vars[] = { { "accent", T.accent }, { "accentInk", T.accentInk }, { "bg", T.bg }, { "field", T.field }, { "hover", T.hover }, { "ink", T.ink }, { "inkDim", T.inkDim }, { "inkFaint", T.inkFaint }, { "line", T.line }, { "tab", T.tab } };
    for (auto& [name, c] : vars) v += std::string("--") + name + ":" + omniCss(c) + ";";
    return v;
}
static std::string omniNewTabHtml()
{
    omniShortcutsLoad();
    omniHistoryLoad();
    const OmniTheme& T = omniTheme();
    std::string h = "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>New tab</title><style>:root{" + omniNewTabVars(T) + "}"
        "body{margin:0;background:var(--bg);color:var(--ink);font-family:'Noto Sans JP','DejaVu Sans',sans-serif}"
        ".w{max-width:1120px;margin:0 auto;padding:44px 48px 60px}"
        "h1{font-size:34px;font-weight:700;letter-spacing:.04em;margin:0 0 22px}h1 b{color:var(--accent)}"
        "form{display:flex;gap:12px;margin:0 0 30px}"
        "input{flex:1;font-size:24px;padding:14px 20px;border-radius:12px;border:2px solid var(--line);background:var(--field);color:var(--ink);outline:none}"
        "input:focus{border-color:var(--accent)}"
        "button{font-size:22px;padding:0 26px;border-radius:12px;border:0;background:var(--accent);color:var(--accentInk);font-weight:700}"
        "h2{font-size:17px;color:var(--inkDim);font-weight:600;margin:28px 0 12px;text-transform:uppercase;letter-spacing:.08em}"
        ".g{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}"
        "a{display:flex;align-items:center;gap:14px;padding:16px;border-radius:14px;background:var(--tab);color:var(--ink);text-decoration:none;min-width:0}"
        "a:hover,a:focus{background:var(--hover);outline:2px solid var(--accent)}"
        "a i{flex:none;width:42px;height:42px;border-radius:21px;background:var(--accent);color:var(--accentInk);font:700 20px sans-serif;display:flex;align-items:center;justify-content:center;font-style:normal}"
        "a span{min-width:0}a b,a small{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}"
        "a b{font-size:19px;font-weight:600}a small{font-size:14px;color:var(--inkDim);margin-top:3px}"
        "p{color:var(--inkFaint);font-size:16px}"
        "</style></head><body><div class=\"w\"><h1><b>O</b>MNI</h1>"
        "<form action=\"" + omniFxSearchAction() + "\" method=\"get\" onsubmit=\"var v=this.q.value.trim();"
        "if(/^https?:\\/\\//i.test(v)){location.href=v;return false}if(v&&v.indexOf(' ')<0&&/^[^\\s\\/]+\\.[a-z]{2,}(\\/.*)?$/i.test(v)){location.href='https://'+v;return false}\">"
        "<input name=\"q\" placeholder=\"Search " + omniFxSearchName() + " or type an address\" autocomplete=\"off\"><button>Search</button></form>"; // OMNI_FEATURES_V1: search engine setting
    auto tile = [&](const std::string& url, const std::string& title) {
        const std::string host = omniBlockerHostOf(url);
        std::string shown = host.rfind("www.", 0) == 0 ? host.substr(4) : host;
        std::string letter = shown.empty() ? std::string("?") : std::string(1, char(toupper(static_cast<unsigned char>(shown[0]))));
        h += "<a href=\"" + omniHtmlEscape(url) + "\"><i>" + omniHtmlEscape(letter) + "</i><span><b>" + omniHtmlEscape(title.empty() ? shown : title)
            + "</b><small>" + omniHtmlEscape(shown) + "</small></span></a>";
    };
    h += "<h2>Shortcuts</h2>";
    if (omniShortcuts.empty()) h += "<p>No shortcuts yet: press L3 on a page to save it, or use Bookmark page in the Options menu.</p>";
    else { h += "<div class=\"g\">"; for (auto& [url, title] : omniShortcuts) tile(url, title); h += "</div>"; }
    // Recently visited: the last 8 different sites.
    std::vector<std::string> seen;
    for (auto it = omniHistory.rbegin(); it != omniHistory.rend() && seen.size() < 8; ++it) {
        const std::string host = omniBlockerHostOf(it->url);
        if (host.empty() || std::find(seen.begin(), seen.end(), host) != seen.end()) continue;
        if (seen.empty()) h += "<h2>Recently visited</h2><div class=\"g\">";
        seen.push_back(host);
        tile(it->url, it->title);
    }
    if (!seen.empty()) h += "</div>";
    h += "</div></body></html>";
    return h;
}
static void omniOpenNewTabPage(Tab* tab)
{
    if (!tab) return;
    std::string html = omniNewTabHtml();
    const std::string url = omniNewTabPrefix + omniPercentEncode(html);
    tab->url.clear(); tab->title = "New tab"; tab->omniNewTabPage = true; tab->loading = true;
    auto u = adoptWK(WKURLCreateWithUTF8CString(url.c_str()));
    WKPageLoadURL(tab->page, u.get());
}

// --- address suggestions -------------------------------------------------------------------------
struct OmniSuggestion { std::string url, title; bool search = false; }; // OMNI_FEATURES_V3: search: a search-engine suggestion
static std::vector<OmniSuggestion> omniSuggestions;
static std::string omniSuggestFor = "\x01";
static int omniSuggestSel = -1;
static int omniSuggestSelected() { return omniSuggestSel; } // OMNI_KEYBOARD_V2
static bool omniSuggestActive() { return editing && !pageEditing && !omniKbTarget && omniKbPage == 0 && !settingsOpen && !omniTestMode(); }
// The address without scheme, "www." and trailing slashes (as shown); omniBareURL() is it lowercased (matching).
static std::string omniShownURL(const std::string& url)
{
    std::string u = url;
    for (const char* p : { "https://", "http://" }) if (omniLower(u.substr(0, strlen(p))) == p) { u = u.substr(strlen(p)); break; }
    if (omniLower(u.substr(0, 4)) == "www.") u = u.substr(4);
    while (!u.empty() && u.back() == '/') u.pop_back();
    return u;
}
static std::string omniBareURL(const std::string& url) { return omniLower(omniShownURL(url)); }
static void omniSuggestUpdate()
{
    if (address == omniSuggestFor) return;
    omniSuggestFor = address;
    omniSuggestions.clear();
    omniSuggestSel = -1;
    std::string q = omniLower(address);
    q.erase(0, q.find_first_not_of(' '));
    while (!q.empty() && q.back() == ' ') q.pop_back();
    if (q.empty() || (active() && address == active()->url)) return;
    for (const char* p : { "https://", "http://" }) if (q.rfind(p, 0) == 0) { q = q.substr(strlen(p)); break; }
    if (q.rfind("www.", 0) == 0) q = q.substr(4);
    if (q.empty()) return;
    omniShortcutsLoad();
    omniHistoryLoad();
    struct Scored { int score; size_t order; OmniSuggestion s; };
    std::vector<Scored> found;
    std::vector<std::string> seen;
    auto consider = [&](const std::string& url, const std::string& title, int bonus) {
        const std::string bare = omniBareURL(url);
        if (std::find(seen.begin(), seen.end(), bare) != seen.end()) return;
        int score;
        if (bare.rfind(q, 0) == 0) score = 0;                               // host starts with it
        else if (bare.find(q) != std::string::npos) score = 2;
        else if (omniLower(title).find(q) != std::string::npos) score = 3;
        else return;
        seen.push_back(bare);
        found.push_back({ score - bonus, found.size(), { url, title } });
    };
    for (auto& [url, title] : omniShortcuts) consider(url, title, 1);
    for (auto it = omniHistory.rbegin(); it != omniHistory.rend() && seen.size() < 400; ++it) consider(it->url, it->title, 0);
    std::stable_sort(found.begin(), found.end(), [](const Scored& a, const Scored& b) { return a.score < b.score; });
    std::vector<OmniSuggestion> local; // OMNI_FEATURES_V3: merged with the search engine's suggestions
    for (size_t i = 0; i < found.size() && i < 5; ++i) local.push_back(found[i].s);
    omniF3SuggestMerge(local);
}
static bool omniSuggestOpen()
{
    if (!omniSuggestActive()) { omniSuggestSel = -1; return false; }
    omniSuggestUpdate();
    return !omniSuggestions.empty();
}
constexpr int omniSuggestX = 184, omniSuggestY = 108, omniSuggestW = 914, omniSuggestRow = 46;
static void omniSuggestGo(int i)
{
    if (i < 0 || i >= int(omniSuggestions.size())) return;
    const std::string url = omniSuggestions[i].url;
    omniSuggestSel = -1;
    omniKbPageReset();
    navigate(url);
}
static bool omniSuggestButton(int b)
{
    const int n = int(omniSuggestions.size());
    if (omniSuggestSel < 0) {
        if (b == SDL_CONTROLLER_BUTTON_DPAD_UP && omniKbAtTopRow()) { omniSuggestSel = n - 1; return true; } // OMNI_KEYBOARD_V2
        return false;
    }
    omniSuggestSel = std::min(omniSuggestSel, n - 1);
    switch (b) {
    case SDL_CONTROLLER_BUTTON_DPAD_UP: if (omniSuggestSel > 0) --omniSuggestSel; return true;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: omniSuggestSel = omniSuggestSel + 1 < n ? omniSuggestSel + 1 : -1; return true;
    case SDL_CONTROLLER_BUTTON_A: case SDL_CONTROLLER_BUTTON_Y: omniSuggestGo(omniSuggestSel); return true;
    case SDL_CONTROLLER_BUTTON_B: omniSuggestSel = -1; return true;
    case SDL_CONTROLLER_BUTTON_START: case SDL_CONTROLLER_BUTTON_BACK:
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: omniSuggestSel = -1; return false;
    default: return true;
    }
}
static bool omniSuggestClick(int x, int y)
{
    if (x < omniSuggestX || x >= omniSuggestX + omniSuggestW || y < omniSuggestY) return false;
    const int i = (y - omniSuggestY - 4) / omniSuggestRow;
    if (i < 0 || i >= int(omniSuggestions.size())) return false;
    omniSuggestGo(i);
    return true;
}
static void omniSuggestDraw()
{
    const OmniTheme& T = omniTheme();
    const int n = int(omniSuggestions.size()), h = n * omniSuggestRow + 8;
    omniShadow(omniSuggestX, omniSuggestY, omniSuggestW, h, omniRadius, 14, 130, 4);
    fillRounded(omniSuggestX, omniSuggestY, omniSuggestW, h, omniRadius, T.raised);
    for (int i = 0; i < n; ++i) {
        const int y = omniSuggestY + 4 + i * omniSuggestRow;
        const bool sel = omniSuggestSel == i;
        if (sel) fillRounded(omniSuggestX + 4, y, omniSuggestW - 8, omniSuggestRow, omniRadius, T.accent);
        const auto& s = omniSuggestions[i];
        const std::string bare = s.search ? omniF3SuggestDetail() : omniShownURL(s.url); // OMNI_FEATURES_V3
        const int w = omniLabel(s.title.empty() ? bare : s.title, omniSuggestX + 18, y + omniSuggestRow / 2.f, omniSmall, sel ? T.accentInk : T.ink, 0, 520);
        omniLabel(bare, omniSuggestX + 30 + w, y + omniSuggestRow / 2.f, omniSmall, sel ? T.accentInk : T.inkDim, 0, omniSuggestW - 60 - w);
    }
    if (omniSuggestSel < 0) { // OMNI_POLISH_V1: on a pill (was faint text over the page)
        const char* tip = "\xe2\x96\xb2 Up from the top row of keys: suggestions";
        const int tw = int(omniTextWidthPx(omniCaption, tip) / displayScale + 0.5);
        fillRounded(omniSuggestX + omniSuggestW - tw - 24, omniSuggestY + h + 4, tw + 24, 24, 12, T.raised, 235);
        omniLabel(tip, omniSuggestX + omniSuggestW - 12, omniSuggestY + h + 16, omniCaption, T.inkDim, 2);
    }
}

// --- find on page --------------------------------------------------------------------------------
static bool omniFindOpenFlag = false;
static std::string omniFindQuery;
static int omniFindCount = -1, omniFindIndex = 0, omniFindStep = 0;
static const void* omniFindTab = nullptr;
constexpr unsigned omniFindMax = 1000;
static void omniFindRun(int step)
{
    if (!active() || omniFindQuery.empty()) return;
    omniFindStep = step;
    auto q = adoptWK(WKStringCreateWithUTF8CString(omniFindQuery.c_str()));
    WKFindOptions options = kWKFindOptionsCaseInsensitive | kWKFindOptionsWrapAround | kWKFindOptionsShowHighlight | kWKFindOptionsShowFindIndicator;
    if (step < 0) options |= kWKFindOptionsBackwards;
    WKPageFindString(active()->page, q.get(), options, omniFindMax);
}
static void omniFindClose()
{
    if (omniFindOpenFlag && omniTabAlive(omniFindTab)) WKPageHideFindUI(static_cast<const Tab*>(omniFindTab)->page);
    omniFindOpenFlag = false;
}
static void omniFindStart()
{
    if (!active()) return;
    omniKbEdit(&omniFindQuery, "Find on page", [](bool submitted) {
        if (!submitted || omniFindQuery.empty() || !active()) return;
        omniFindOpenFlag = true; omniFindTab = active(); omniFindIndex = 0; omniFindCount = -1;
        omniFindRun(0);
    });
}
static bool omniFindBarOpen() { return omniFindOpenFlag && active() == omniFindTab && !pageFullscreen && !editing; }
static bool omniFindButton(int b)
{
    switch (b) {
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: omniFindRun(1); return true;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: omniFindRun(-1); return true;
    case SDL_CONTROLLER_BUTTON_Y: omniFindStart(); return true;
    case SDL_CONTROLLER_BUTTON_B: omniFindClose(); return true;
    default: return false;
    }
}
constexpr int omniFindX = 676, omniFindW = 584, omniFindH = 50;
static int omniFindY() { return std::max(8, omniPageTop() + 10); }
static bool omniFindClick(int x, int y)
{
    if (x < omniFindX || x >= omniFindX + omniFindW || y < omniFindY() || y >= omniFindY() + omniFindH) return false;
    if (x >= omniFindX + omniFindW - 50) omniFindClose();
    else if (x >= omniFindX + omniFindW - 150) omniFindRun(x >= omniFindX + omniFindW - 100 ? 1 : -1);
    else omniFindStart();
    return true;
}
static void omniFindDraw()
{
    const OmniTheme& T = omniTheme();
    const int x = omniFindX, y = omniFindY();
    omniShadow(x, y, omniFindW, omniFindH, omniRadius, 14, 140, 4);
    fillRounded(x, y, omniFindW, omniFindH, omniRadius, T.raised);
    const float cy = y + omniFindH / 2.f;
    const int lw = omniLabel("Find", x + 16, cy, omniSmallBold, T.accent);
    omniLabel(omniFindQuery, x + 28 + lw, cy, omniBody, T.ink, 0, 250);
    char count[48];
    if (omniFindCount < 0) snprintf(count, sizeof(count), "...");
    else if (!omniFindCount) snprintf(count, sizeof(count), "No matches");
    else snprintf(count, sizeof(count), "%d of %d%s", std::max(1, omniFindIndex), omniFindCount, unsigned(omniFindCount) >= omniFindMax ? "+" : "");
    omniLabel(count, x + omniFindW - 160, cy, omniSmall, omniFindCount == 0 ? omniBad : T.inkDim, 2);
    omniIcon(omniIconBack, x + omniFindW - 125, cy, T.ink);
    omniIcon(omniIconForward, x + omniFindW - 75, cy, T.ink);
    omniIcon(omniIconClose, x + omniFindW - 25, cy, T.inkDim);
    { // OMNI_POLISH_V1: on a pill (was faint text over the page)
        const char* tip = "D-pad \xe2\x97\x80 \xe2\x96\xb6 previous / next   Y edit   B close";
        const int tw = int(omniTextWidthPx(omniCaption, tip) / displayScale + 0.5);
        fillRounded(x + omniFindW - tw - 24, y + omniFindH + 6, tw + 24, 24, 12, T.raised, 235);
        omniLabel(tip, x + omniFindW - 12, y + omniFindH + 18, omniCaption, T.inkDim, 2);
    }
}
static void omniEverydayTabCreated(Tab* tab)
{
    static WKPageFindClientV0 find {};
    find.base.version = 0;
    find.didFindString = [](WKPageRef page, WKStringRef, unsigned matchCount, const void*) {
        if (!omniFindOpenFlag || !omniTabAlive(omniFindTab) || static_cast<const Tab*>(omniFindTab)->page != page) return;
        const int count = int(matchCount);
        omniFindIndex = omniFindStep == 0 || omniFindCount != count || !omniFindIndex ? 1 : (omniFindIndex - 1 + omniFindStep + count) % count + 1;
        omniFindCount = count;
        omniShellDirty = omniPageDirty = true;
    };
    find.didFailToFindString = [](WKPageRef page, WKStringRef, const void*) {
        if (!omniFindOpenFlag || !omniTabAlive(omniFindTab) || static_cast<const Tab*>(omniFindTab)->page != page) return;
        omniFindCount = 0; omniFindIndex = 0; omniShellDirty = true;
    };
    WKPageSetPageFindClient(tab->page, &find.base);
}

// --- downloads -----------------------------------------------------------------------------------
struct OmniDownload { std::string name; long long bytes = 0; uint32_t noticeAt = 0; };
static std::unordered_map<const void*, OmniDownload> omniDownloads;
static std::string omniSafeFileName(std::string name)
{
    for (auto& c : name) if (c == '/' || c == '\\' || c == ':' || c == '*' || c == '?' || c == '"' || c == '<' || c == '>' || c == '|' || static_cast<unsigned char>(c) < 32) c = '_';
    while (!name.empty() && (name[0] == '.' || name[0] == ' ')) name.erase(0, 1);
    if (name.size() > 120) name = name.substr(name.size() - 120);
    return name.empty() ? std::string("download") : name;
}
static WKStringRef omniDownloadDestination(WKDownloadRef download, WKURLResponseRef, WKStringRef suggested, const void*)
{
    const std::string dir = omniData("downloads");
    mkdir(dir.c_str(), 0777);
    std::string name = omniSafeFileName(OmniTest::toStd(suggested));
    const size_t dot = name.rfind('.');
    const std::string stem = dot == std::string::npos || dot == 0 ? name : name.substr(0, dot), ext = dot == std::string::npos || dot == 0 ? "" : name.substr(dot);
    std::string path = dir + "/" + name;
    for (int i = 2; !access(path.c_str(), F_OK) && i < 1000; ++i) path = dir + "/" + stem + " (" + std::to_string(i) + ")" + ext;
    omniDownloads[download].name = path.substr(dir.size() + 1);
    omniFxDownloadStarted(download, path); // OMNI_FEATURES_V1: downloads page
    notice("Downloading " + omniDownloads[download].name + " to " + dir + "/");
    return WKStringCreateWithUTF8CString(path.c_str());   // +1: WebKit adopts it
}
static void omniDownloadInstall(WKDownloadRef download)
{
    static WKDownloadClientV0 client {};
    client.base.version = 0;
    client.decideDestinationWithResponse = omniDownloadDestination;
    client.didWriteData = [](WKDownloadRef download, long long, long long total, long long expected, const void*) {
        OmniDownload& d = omniDownloads[download];
        d.bytes = total;
        omniFxDownloadProgress(download, total, expected); // OMNI_FEATURES_V1
        if (SDL_GetTicks() - d.noticeAt < 1000) return;
        d.noticeAt = SDL_GetTicks();
        char text[200];
        if (expected > 0) snprintf(text, sizeof(text), "Downloading %s: %d%% of %.1f MB", d.name.c_str(), int(100.0 * total / expected), expected / 1048576.0);
        else snprintf(text, sizeof(text), "Downloading %s: %.1f MB", d.name.c_str(), total / 1048576.0);
        notice(text);
    };
    client.didFinish = [](WKDownloadRef download, const void*) {
        notice("Downloaded " + omniDownloads[download].name + " to " + omniData("downloads/"));
        omniFxDownloadEnded(download, true); // OMNI_FEATURES_V1
        omniDownloads.erase(download);
    };
    client.didFailWithError = [](WKDownloadRef download, WKErrorRef, WKDataRef, const void*) {
        notice("Download failed: " + omniDownloads[download].name);
        omniFxDownloadEnded(download, false); // OMNI_FEATURES_V1 (a cancel replaces the notice)
        omniDownloads.erase(download);
    };
    WKDownloadSetClient(download, &client.base);
}

// --- navigation client: user agent per site, downloads, site zoom on commit ----------------------
static void omniEverydayNavigation(WKPageNavigationClientV3& nav)
{
    if (omniTestMode()) return;   // self-test modes keep the old navigation client
    nav.decidePolicyForNavigationAction = [](WKPageRef page, WKNavigationActionRef action, WKFramePolicyListenerRef listener, WKTypeRef, const void*) {
        if (omniFxPolicyDownload(page, action, listener)) return; // OMNI_FEATURES_V1: Save link / image
        Tab* tab = omniTabForPage(page);
        auto target = adoptWK(WKNavigationActionCopyTargetFrameInfo(action));
        if (tab && target && WKFrameInfoGetIsMainFrame(target.get())) {
            auto request = adoptWK(WKNavigationActionCopyRequest(action));
            auto url = request ? adoptWK(WKURLRequestCopyURL(request.get())) : WKRetainPtr<WKURLRef>();
            const std::string targetURL = url ? OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get()) : std::string();
            const bool mobile = omniMobileHosts.count(omniBlockerHostOf(targetURL)) > 0;
            if (omniWebURL(targetURL) && mobile != tab->omniMobileUA) {
                omniApplyUserAgent(tab, targetURL);
                const std::string method = OmniTest::toStd(adoptWK(WKURLRequestCopyHTTPMethod(request.get())).get());
                const WKFrameNavigationType type = WKNavigationActionGetNavigationType(action);
                if ((method.empty() || method == "GET") && type != kWKFrameNavigationTypeBackForward && type != kWKFrameNavigationTypeReload) {
                    // The request already carries the old UA: load it again once with the new one.
                    WKFramePolicyListenerIgnore(listener);
                    tab->omniPendingLoad = targetURL;
                    return;
                }
            }
        }
        WKFramePolicyListenerUse(listener);
    };
    nav.decidePolicyForNavigationResponse = [](WKPageRef, WKNavigationResponseRef navigationResponse, WKFramePolicyListenerRef listener, WKTypeRef, const void*) {
        auto response = adoptWK(WKNavigationResponseCopyResponse(navigationResponse));
        auto frame = adoptWK(WKNavigationResponseCopyFrameInfo(navigationResponse));
        const bool mainFrame = !frame || WKFrameInfoGetIsMainFrame(frame.get());
        const int status = response ? WKURLResponseHTTPStatusCode(response.get()) : 0;
        const bool attachment = response && WKURLResponseIsAttachment(response.get());
        if (status < 400 && (attachment || (mainFrame && !WKNavigationResponseCanShowMIMEType(navigationResponse)))) WKFramePolicyListenerDownload(listener);
        else WKFramePolicyListenerUse(listener);
    };
    nav.navigationResponseDidBecomeDownload = [](WKPageRef, WKNavigationResponseRef, WKDownloadRef download, const void*) { omniDownloadInstall(download); };
    nav.navigationActionDidBecomeDownload = [](WKPageRef, WKNavigationActionRef, WKDownloadRef download, const void*) { omniDownloadInstall(download); }; // OMNI_FEATURES_V1
    nav.didCommitNavigation = [](WKPageRef page, WKNavigationRef, WKTypeRef, const void*) {
        Tab* tab = omniTabForPage(page);
        if (!tab) return;
        tab->omniNetRing.clear(); // OMNI_NET_GRABBER_V1: a new page starts with no observed media
        if (auto url = adoptWK(WKPageCopyActiveURL(page))) tab->url = OmniTest::toStd(adoptWK(WKURLCopyString(url.get())).get());
        if (tab->url.rfind(omniNewTabPrefix, 0) == 0) tab->url.clear();
        omniApplySiteZoom(tab);
    };
}

// --- private tabs, clear data, reader view -------------------------------------------------------
static WKRetainPtr<WKContextRef> omniPrivateContext;
static WKRetainPtr<WKWebsiteDataStoreRef> omniPrivateStore;
static void omniNewPrivateTab()
{
    if (!omniPrivateContext) {
        // A web process works for one session only (WebPage::sessionID() is the process's), so a
        // private data store needs its own process pool: one more single web process.
        omniPrivateStore = adoptWK(WKWebsiteDataStoreCreateNonPersistentDataStore());
        auto config = adoptWK(WKContextConfigurationCreate());
        WKContextConfigurationSetUserId(config.get(), -1);
        omniPrivateContext = adoptWK(WKContextCreateWithConfiguration(config.get()));
        WKContextSetPrimaryWebsiteDataStore(omniPrivateContext.get(), omniPrivateStore.get());
        WKContextSetUsesSingleWebProcess(omniPrivateContext.get(), true);
    }
    auto config = adoptWK(WKPageConfigurationCreate());
    WKPageConfigurationSetContext(config.get(), omniPrivateContext.get());
    WKPageConfigurationSetPreferences(config.get(), preferences.get());
    WKPageConfigurationSetWebsiteDataStore(config.get(), omniPrivateStore.get());
    if (Tab* tab = newTab(config.get())) {
        tab->omniPrivate = true;
        omniNetGrabberApply(*tab); // OMNI_C52_FIX1: removed before the private tab loads anything
        omniOpenNewTabPage(tab);
        notice("Private tab: no history; cookies and site data are forgotten when Omni closes");
    }
}
static int omniClearPending = 0;
static void omniClearStep(void*) { if (--omniClearPending == 0) { notice("Browsing data cleared"); if (active()) WKPageReload(active()->page); } }
static void omniClearBrowsingData()
{
    omniHistory.clear(); omniHistoryLoaded = true;
    omniIoQueue(omniData("history.txt"), "", false);
    omniSuggestFor = "\x01";
    notice("Clearing browsing data...");
    WKWebsiteDataStoreRef store = websiteDataStore.get();
    omniClearPending = 7;
    WKHTTPCookieStoreDeleteAllCookies(WKWebsiteDataStoreGetHTTPCookieStore(store), nullptr, omniClearStep);
    WKWebsiteDataStoreRemoveNetworkCache(store, nullptr, omniClearStep);
    WKWebsiteDataStoreRemoveLocalStorage(store, nullptr, omniClearStep);
    WKWebsiteDataStoreRemoveAllIndexedDatabases(store, nullptr, omniClearStep);
    WKWebsiteDataStoreRemoveAllServiceWorkerRegistrations(store, nullptr, omniClearStep);
    WKWebsiteDataStoreRemoveAllFetchCaches(store, nullptr, omniClearStep);
    WKWebsiteDataStoreRemoveMemoryCaches(store, nullptr, omniClearStep);
}
static void omniReaderStart()
{
    Tab* tab = active();
    if (!tab || !omniWebURL(tab->url)) { notice("Reader view works on web pages"); return; }
    static const char* extract = R"JS((function(){
function esc(s){return String(s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
var best=null,bestScore=0,scores=new Map(),ps=document.querySelectorAll('p');
for(var i=0;i<ps.length;i++){var t=(ps[i].innerText||'').trim();if(t.length<60)continue;var par=ps[i].parentElement;if(!par)continue;
var s=(scores.get(par)||0)+t.length;scores.set(par,s);if(s>bestScore){bestScore=s;best=par;}}
var art=document.querySelector('article'),root=art&&best&&art.contains(best)?art:best;
if(!root||bestScore<500)return '';
var h1=document.querySelector('h1'),title=(h1&&h1.innerText.trim())||document.title,out=['<h1>'+esc(title)+'</h1>'];
var nodes=root.querySelectorAll('h2,h3,h4,p,li,blockquote,pre,img,figcaption');
for(var j=0;j<nodes.length&&out.length<2000;j++){var n=nodes[j],tag=n.tagName.toLowerCase();
if(tag==='img'){var src=n.currentSrc||n.src;if(src&&/^https?:/.test(src)&&(n.naturalWidth||n.width)>=200)out.push('<img src="'+esc(src)+'">');continue;}
if(tag!=='li'&&n.closest('li,blockquote')&&n.closest('li,blockquote')!==n)continue;
var t2=(n.innerText||'').trim();if(t2)out.push('<'+tag+'>'+esc(t2)+'</'+tag+'>');}
return out.join('\n');})())JS";
    auto script = adoptWK(WKStringCreateWithUTF8CString(extract));
    notice("Reader view...");
    WKPageEvaluateJavaScriptInMainFrame(tab->page, script.get(), tab, [](WKTypeRef result, WKErrorRef error, void* context) {
        Tab* tab = static_cast<Tab*>(context);
        if (!omniTabAlive(tab)) return;
        std::string body;
        if (!error && result && WKGetTypeID(result) == WKStringGetTypeID()) body = OmniTest::toStd(static_cast<WKStringRef>(result));
        if (body.size() < 300) { notice("Reader view: no article found on this page"); return; }
        const OmniTheme& T = omniTheme();
        const std::string html = "<!doctype html><html><head><meta charset=\"utf-8\"><title>" + omniHtmlEscape(tab->title) + "</title><style>"
            "body{margin:0;background:" + omniCss(T.bg) + ";color:" + omniCss(T.ink) + "}"
            "main{max-width:860px;margin:0 auto;padding:36px 48px 80px;font:26px/1.65 'Noto Serif','DejaVu Serif',Georgia,serif}"
            "h1{font:700 40px/1.25 'Noto Sans JP','DejaVu Sans',sans-serif;margin:8px 0 28px}h2,h3,h4{font-family:'Noto Sans JP','DejaVu Sans',sans-serif;line-height:1.3}"
            "img{max-width:100%;height:auto;border-radius:10px;margin:12px 0}blockquote{border-left:4px solid " + omniCss(T.accent) + ";margin:0;padding-left:22px;color:" + omniCss(T.inkDim) + "}"
            "pre{white-space:pre-wrap;font-size:20px}a{color:" + omniCss(T.accent) + "}.src{font:18px sans-serif;color:" + omniCss(T.inkFaint) + "}"
            "</style></head><body><main><p class=\"src\">Reader view \xc2\xb7 " + omniHtmlEscape(omniBlockerHostOf(tab->url)) + " \xc2\xb7 Back returns to the page</p>" + body + "</main></body></html>";
        tab->omniReader = true;
        auto text = adoptWK(WKStringCreateWithUTF8CString(html.c_str()));
        auto base = adoptWK(WKURLCreateWithUTF8CString(tab->url.c_str()));
        WKPageLoadHTMLString(tab->page, text.get(), base.get());
    });
}

// --- history overlay -----------------------------------------------------------------------------
static bool omniHistoryOpenFlag = false;
static int omniHistorySel = 0, omniHistoryScroll = 0;
constexpr int omniHistoryRows = 9, omniHistoryRowH = 50, omniHistoryX = 150, omniHistoryW = 980;
constexpr int omniHistoryTop = (height - bottom - (70 + omniHistoryRows * omniHistoryRowH + 20)) / 2;
static int omniHistoryCount() { return int(omniHistory.size()) + 1; }   // row 0: Clear history
static const OmniVisit* omniHistoryItem(int row) { return row >= 1 && row <= int(omniHistory.size()) ? &omniHistory[omniHistory.size() - row] : nullptr; }
static void omniHistoryShow() { omniHistoryLoad(); omniHistoryOpenFlag = true; omniHistorySel = omniHistory.empty() ? 0 : 1; omniHistoryScroll = 0; }
static void omniHistoryActivate(int row)
{
    if (row == 0) {
        if (omniHistory.empty()) { notice("History is empty"); return; }
        omniAsk("Clear history?", "All " + std::to_string(omniHistory.size()) + " visits will be removed from this console.", "Clear history", [](bool ok) {
            if (!ok) return;
            omniHistory.clear();
            omniIoQueue(omniData("history.txt"), "", false);
            omniHistorySel = 0; omniSuggestFor = "\x01";
            notice("History cleared");
        });
        return;
    }
    if (const OmniVisit* v = omniHistoryItem(row)) { const std::string url = v->url; omniHistoryOpenFlag = false; navigate(url); }
}
static void omniHistoryDelete(int row)
{
    if (!omniHistoryItem(row)) return;
    omniHistory.erase(omniHistory.begin() + (omniHistory.size() - row));
    omniHistoryRewrite();
    omniSuggestFor = "\x01";
    omniHistorySel = std::min(omniHistorySel, omniHistoryCount() - 1);
}
static bool omniHistoryButton(int b)
{
    const int n = omniHistoryCount();
    switch (b) {
    case SDL_CONTROLLER_BUTTON_DPAD_UP: omniHistorySel = std::max(0, omniHistorySel - 1); break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: omniHistorySel = std::min(n - 1, omniHistorySel + 1); break;
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: omniHistorySel = std::max(0, omniHistorySel - omniHistoryRows); break;
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: omniHistorySel = std::min(n - 1, omniHistorySel + omniHistoryRows); break;
    case SDL_CONTROLLER_BUTTON_A: omniHistoryActivate(omniHistorySel); break;
    case SDL_CONTROLLER_BUTTON_X: omniHistoryDelete(omniHistorySel); break;
    case SDL_CONTROLLER_BUTTON_B: case SDL_CONTROLLER_BUTTON_BACK: omniHistoryOpenFlag = false; break;
    case SDL_CONTROLLER_BUTTON_START: return false;
    default: break;
    }
    return true;
}
static int omniHistoryRowAt(int x, int y)
{
    const int listY = omniHistoryTop + 70;
    if (x < omniHistoryX || x >= omniHistoryX + omniHistoryW || y < listY || y >= listY + omniHistoryRows * omniHistoryRowH) return -1;
    const int row = omniHistoryScroll + (y - listY) / omniHistoryRowH;
    return row < omniHistoryCount() ? row : -1;
}
static bool omniHistoryClick(int x, int y)
{
    const int row = omniHistoryRowAt(x, y);
    if (row >= 0) { omniHistorySel = row; omniHistoryActivate(row); }
    return true;
}
static bool omniHistoryScrollBy(double amount)
{
    static float acc = 0;
    acc -= float(amount);
    while (acc >= 50) { acc -= 50; omniHistorySel = std::min(omniHistoryCount() - 1, omniHistorySel + 1); }
    while (acc <= -50) { acc += 50; omniHistorySel = std::max(0, omniHistorySel - 1); }
    return true;
}
static std::string omniAgo(long long when)
{
    const long long d = std::max(0LL, (long long)time(nullptr) - when);
    char b[32];
    if (d < 60) return "just now";
    if (d < 3600) snprintf(b, sizeof(b), "%lld min ago", d / 60);
    else if (d < 86400) snprintf(b, sizeof(b), "%lld h ago", d / 3600);
    else if (d < 86400 * 30) snprintf(b, sizeof(b), "%lld days ago", d / 86400);
    else { time_t t = time_t(when); struct tm tmv {}; localtime_r(&t, &tmv); strftime(b, sizeof(b), "%Y-%m-%d", &tmv); }
    return b;
}
static void omniPanelHints(const std::vector<std::pair<int, const char*>>& faces, const char* extra)
{
    const OmniTheme& T = omniTheme();
    fill(0, height - bottom, width, bottom, T.bar);
    omniRectPx({ 0, physical(height - bottom), renderWidth, 1 }, T.line);
    std::vector<OmniHint> items; // OMNI_POLISH_V1: shared hint layout (was text() at fixed steps)
    for (auto& [b, label] : faces) items.push_back({ b, label });
    omniHints(items, {}, extra ? extra : "");
}
static void omniHistoryDraw()
{
    const OmniTheme& T = omniTheme();
    const float fadeT = omniPanelT(omniPanelHistory); // OMNI_POLISH_V1: backdrop and panel fade in
    omniRectPx({ 0, 0, canvas->w, canvas->h }, { 0, 0, 0, 255 }, uint8_t(110 * fadeT));
    const int h = 70 + omniHistoryRows * omniHistoryRowH + 20;
    struct FadeScope { ~FadeScope() { omniFadeEnd(); } } fadeScope;
    omniFadeBegin(omniHistoryX - 30, omniHistoryTop - 30, omniHistoryW + 60, h + 60, fadeT);
    omniShadow(omniHistoryX, omniHistoryTop, omniHistoryW, h, omniRadius + 2, 22, 160, 6);
    fillRounded(omniHistoryX, omniHistoryTop, omniHistoryW, h, omniRadius + 2, T.panel);
    omniLabel("History", omniHistoryX + 28, omniHistoryTop + 36, omniTitle, T.ink); // OMNI_POLISH_V1: title size
    omniLabel(std::to_string(omniHistory.size()) + " visits", omniHistoryX + omniHistoryW - 28, omniHistoryTop + 36, omniSmall, T.inkFaint, 2);
    const int n = omniHistoryCount();
    if (omniHistorySel < omniHistoryScroll) omniHistoryScroll = omniHistorySel;
    if (omniHistorySel >= omniHistoryScroll + omniHistoryRows) omniHistoryScroll = omniHistorySel - omniHistoryRows + 1;
    omniHistoryScroll = std::clamp(omniHistoryScroll, 0, std::max(0, n - omniHistoryRows));
    const int listY = omniHistoryTop + 70;
    for (int r = 0; r < omniHistoryRows && omniHistoryScroll + r < n; ++r) {
        const int row = omniHistoryScroll + r, y = listY + r * omniHistoryRowH;
        const bool sel = row == omniHistorySel;
        if (sel) fillRounded(omniHistoryX + 12, y + 2, omniHistoryW - 24, omniHistoryRowH - 4, omniRadius, T.accent);
        const SDL_Color ink = sel ? T.accentInk : T.ink, dim = sel ? T.accentInk : T.inkDim;
        const float cy = y + omniHistoryRowH / 2.f;
        if (row == 0) { omniIcon(omniIconClose, omniHistoryX + 40, cy, sel ? T.accentInk : omniBad); omniLabel("Clear history", omniHistoryX + 64, cy, omniBody, sel ? T.accentInk : omniBad); continue; }
        const OmniVisit& v = *omniHistoryItem(row);
        const std::string bare = omniShownURL(v.url);
        const int w = omniLabel(v.title.empty() ? bare : v.title, omniHistoryX + 32, cy, omniBody, ink, 0, 560);
        omniLabel(bare, omniHistoryX + 48 + w, cy, omniSmall, dim, 0, std::max(0, omniHistoryW - 230 - w));
        omniLabel(omniAgo(v.time), omniHistoryX + omniHistoryW - 30, cy, omniSmall, dim, 2);
    }
    if (n == 1) omniLabel("Pages you visit appear here (not from private tabs).", omniHistoryX + 32, listY + omniHistoryRowH * 1.5f, omniBody, T.inkFaint);
    omniFadeEnd(); // OMNI_POLISH_V1: the hint bar is outside the fade
    omniPanelHints({ { 0, "Open" }, { 2, "Delete" }, { 1, "Close" } }, "D-pad: move   L1/R1: page");
}

#include "OmniMediaDownloadsHooks.inc" // OMNI_MEDIA_DOWNLOADS_V1
// OMNI_C52_FIX1 (review M2): the grabber's resource-load client makes WebKit send will-send/response/
// completion messages for every subresource of every frame. Install it only where omniNetObserve could
// record anything: Media downloads enabled (or the grabber self-test), a normal (non-private) tab that is
// not the Media downloads tab. The widget/feature self-tests keep their own diagnostic client.
static void omniNetGrabberApply(Tab& tab)
{
    if (widgetTest || featureTest || !tab.page) return;
    const bool want = (grabberTest || (omniMediaDownloadsEnabled && !omniTestMode())) && !tab.omniPrivate && !tab.omniMediaSection;
    if (want == tab.omniNetClient) return;
    if (want) {
        // OMNI_NET_GRABBER_V1: watch responses of every frame (incl. cross-origin player iframes) for
        // HLS/DASH manifests and whole media files. One cheap string check per response, no logging.
        WKPageResourceLoadClientV0 grabber {};
        grabber.base.version = 0; grabber.base.clientInfo = nullptr; // the tab is looked up by page (closed tabs never match)
        grabber.didReceiveResponse = [](const void*, WKPageRef page, WKURLRef original, WKURLResponseRef response) { omniNetObserve(page, original, response); };
        WKPageSetResourceLoadClient(tab.page, &grabber.base);
    } else {
        WKPageSetResourceLoadClient(tab.page, nullptr);
        tab.omniNetRing.clear(); // nothing observed earlier is kept once the tab stops being watched
    }
    tab.omniNetClient = want;
}
static void omniNetGrabberSyncAll()
{
    for (auto& tab : tabs) omniNetGrabberApply(*tab);
}
// OMNI_NET_GRABBER_V1: called on the UI main loop for each response a normal tab receives. Privacy and
// feature checks come before any URL is read; static assets are rejected before the MIME copy; nothing logs.
static void omniNetObserve(WKPageRef page, WKURLRef original, WKURLResponseRef response)
{
    if (!response || !(omniMediaDownloadsEnabled || grabberTest) || !running) return; // OMNI_NET_GRABBER_TEST_V1
    Tab* tab = omniTabForPage(page);
    if (!tab || tab->omniPrivate || tab->omniMediaSection || tab->crashed) return;
    WKRetainPtr<WKURLRef> responseURL;
    if (!original) { responseURL = adoptWK(WKURLResponseCopyURL(response)); original = responseURL.get(); }
    if (!original) return;
    auto text = adoptWK(WKURLCopyString(original));
    if (!text || WKStringGetLength(text.get()) < 8 || WKStringGetLength(text.get()) > OmniNetGrabber::maxUrlChars) return;
    const auto url = OmniTest::toStd(text.get());
    if (OmniNetGrabber::staticAsset(url)) return;
    const auto mime = OmniTest::toStd(adoptWK(WKURLResponseCopyMIMEType(response)).get());
    tab->omniNetRing.record(OmniNetGrabber::classify(url, mime, WKURLResponseHTTPStatusCode(response),
        WKURLResponseGetExpectedContentLength(response)), url);
}

// --- Browser tools menu --------------------------------------------------------------------------
static bool omniMenuOpenFlag = false;
static int omniMenuSel = 0;
enum { omniMenuHistory, omniMenuFind, omniMenuZoom, omniMenuMobile, omniMenuPrivate, omniMenuReader, omniMenuClear, omniMenuMediaDownloads, omniMenuSendMediaLink, omniMenuCount };
static const double omniZoomSteps[] = { 0.5, 0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5 };
static std::string omniMenuHost() { return active() ? omniBlockerHostOf(active()->url) : std::string(); }
static bool omniMenuEnabled(int item)
{
    const bool page = !omniMenuHost().empty();
    if (item == omniMenuMediaDownloads) return omniMediaDownloadsEnabled;
    if (item == omniMenuSendMediaLink) return omniMediaDownloadsEnabled && active() && !active()->url.empty();
    if (item == omniMenuZoom || item == omniMenuMobile || item == omniMenuReader || item == omniMenuFind) return page;
    if (item == omniMenuPrivate) return !omniF3TabsFull(); // OMNI_FEATURES_V3
    return true;
}
static void omniZoomStep(int dir)
{
    const std::string host = omniMenuHost();
    if (host.empty()) return;
    const double now = omniZoomFor(host);
    const int last = int(sizeof(omniZoomSteps) / sizeof(omniZoomSteps[0])) - 1;
    int i = 0;   // nearest step
    for (int k = 1; k <= last; ++k) if (std::fabs(omniZoomSteps[k] - now) < std::fabs(omniZoomSteps[i] - now)) i = k;
    const double z = dir == 0 ? omniFxDefaultZoom() : omniZoomSteps[std::clamp(i + dir, 0, last)]; // OMNI_FEATURES_V1: reset = default zoom
    if (std::fabs(z - omniFxDefaultZoom()) < 1e-3) omniSiteZoom.erase(host); else omniSiteZoom[host] = z;
    omniPrefsSave();
    for (auto& t : tabs) if (omniBlockerHostOf(t->url) == host) omniApplySiteZoom(t.get());
    omniPageDirty = true;
}
static void omniMobileToggle()
{
    const std::string host = omniMenuHost();
    if (host.empty() || !active()) return;
    if (!omniMobileHosts.erase(host)) omniMobileHosts.insert(host);
    omniPrefsSave();
    omniApplyUserAgent(active(), active()->url);
    WKPageReload(active()->page);
    notice(std::string(omniMobileHosts.count(host) ? "Mobile site" : "Desktop site") + " for " + host);
}
static void omniMenuActivate(int item)
{
    if (!omniMenuEnabled(item)) return;
    switch (item) {
    case omniMenuHistory: omniMenuOpenFlag = false; omniHistoryShow(); break;
    case omniMenuFind: omniMenuOpenFlag = false; omniFindStart(); break;
    case omniMenuZoom: omniZoomStep(0); break;
    case omniMenuMobile: omniMobileToggle(); break;
    case omniMenuPrivate: omniMenuOpenFlag = false; omniNewPrivateTab(); break;
    case omniMenuReader: omniMenuOpenFlag = false; omniReaderStart(); break;
    case omniMenuMediaDownloads: omniMenuOpenFlag = false; if (!omniGrabBegin(2)) omniMediaDownloadsOpen(false); break; // OMNI_NET_GRABBER_V1
    case omniMenuSendMediaLink: omniMenuOpenFlag = false; if (!omniGrabBegin(1)) omniMediaDownloadsOpen(true); break; // OMNI_NET_GRABBER_V1
    case omniMenuClear:
        omniMenuOpenFlag = false;
        omniAsk("Clear browsing data?", "History, cookies, site storage and caches will be deleted (you will be signed out of sites). Shortcuts, settings and private tabs are not affected.",
            "Clear data", [](bool ok) { if (ok) omniClearBrowsingData(); });
        break;
    }
}
constexpr int omniMenuW = 600, omniMenuRowH = 54;
static int omniMenuX() { return (width - omniMenuW) / 2; }
static int omniMenuY() { return (height - (96 + omniMenuCount * omniMenuRowH + 18)) / 2; }
static void omniMenuShow() { settingsOpen = false; omniMenuOpenFlag = true; omniMenuSel = 0; }
static bool omniMenuButton(int b)
{
    switch (b) {
    case SDL_CONTROLLER_BUTTON_DPAD_UP: omniMenuSel = (omniMenuSel + omniMenuCount - 1) % omniMenuCount; break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: omniMenuSel = (omniMenuSel + 1) % omniMenuCount; break;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: case SDL_CONTROLLER_BUTTON_DPAD_RIGHT:
        if (omniMenuSel == omniMenuZoom) omniZoomStep(b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT ? 1 : -1);
        else if (omniMenuSel == omniMenuMobile) omniMobileToggle();
        break;
    case SDL_CONTROLLER_BUTTON_A: omniMenuActivate(omniMenuSel); break;
    case SDL_CONTROLLER_BUTTON_B: case SDL_CONTROLLER_BUTTON_BACK: omniMenuOpenFlag = false; break;
    case SDL_CONTROLLER_BUTTON_START: return false;
    default: break;
    }
    return true;
}
static bool omniMenuClick(int x, int y)
{
    const int listY = omniMenuY() + 96;
    if (x >= omniMenuX() && x < omniMenuX() + omniMenuW && y >= listY && y < listY + omniMenuCount * omniMenuRowH) {
        const int item = (y - listY) / omniMenuRowH;
        omniMenuSel = item;
        if (item == omniMenuZoom && x >= omniMenuX() + omniMenuW - 210) omniZoomStep(x >= omniMenuX() + omniMenuW - 70 ? 1 : x < omniMenuX() + omniMenuW - 160 ? -1 : 0);
        else omniMenuActivate(item);
    } else if (x < omniMenuX() || x >= omniMenuX() + omniMenuW || y < omniMenuY() || y >= listY + omniMenuCount * omniMenuRowH + 18) omniMenuOpenFlag = false;
    return true;
}
static void omniMenuDraw()
{
    const OmniTheme& T = omniTheme();
    const float fadeT = omniPanelT(omniPanelMenu); // OMNI_POLISH_V1: backdrop and panel fade in
    omniRectPx({ 0, 0, canvas->w, canvas->h }, { 0, 0, 0, 255 }, uint8_t(110 * fadeT));
    const int x = omniMenuX(), y = omniMenuY(), h = 96 + omniMenuCount * omniMenuRowH + 18;
    struct FadeScope { ~FadeScope() { omniFadeEnd(); } } fadeScope;
    omniFadeBegin(x - 30, y - 30, omniMenuW + 60, h + 60, fadeT);
    omniShadow(x, y, omniMenuW, h, omniRadius + 2, 22, 160, 6);
    fillRounded(x, y, omniMenuW, h, omniRadius + 2, T.panel);
    omniLabel("Browser tools", x + 28, y + 36, omniTitle, T.ink); // OMNI_POLISH_V1: title size
    const std::string host = omniMenuHost();
    omniLabel(host.empty() ? std::string("No site open") : host, x + 28, y + 70, omniSmall, T.inkDim, 0, omniMenuW - 56);
    char zoom[16]; snprintf(zoom, sizeof(zoom), "%d%%", int(omniZoomFor(host) * 100 + 0.5));
    const char* labels[omniMenuCount] = { "History", "Find on page", "Zoom for this site", "Mobile site", "New private tab", "Reader view", "Clear browsing data", "Media downloads", "Send current link" };
    for (int i = 0; i < omniMenuCount; ++i) {
        const int ry = y + 96 + i * omniMenuRowH;
        const bool sel = omniMenuSel == i, on = omniMenuEnabled(i);
        if (sel) fillRounded(x + 12, ry + 2, omniMenuW - 24, omniMenuRowH - 4, omniRadius, on ? T.accent : T.key);
        const SDL_Color ink = sel && on ? T.accentInk : on ? (i == omniMenuClear ? omniBad : T.ink) : T.inkFaint;
        const float cy = ry + omniMenuRowH / 2.f;
        omniLabel(labels[i], x + 32, cy, omniBody, ink);
        const SDL_Color side = sel && on ? T.accentInk : T.inkDim;
        if (i == omniMenuZoom && on) {
            omniIcon(omniIconBack, x + omniMenuW - 180, cy, side);
            omniLabel(zoom, x + omniMenuW - 110, cy, omniBodyBold, sel ? T.accentInk : T.ink, 1);
            omniIcon(omniIconForward, x + omniMenuW - 42, cy, side);
        } else if (i == omniMenuMobile && on) omniLabel(omniMobileHosts.count(host) ? "On (iPhone)" : "Off (desktop)", x + omniMenuW - 32, cy, omniSmall, side, 2);
        else if (i == omniMenuHistory) omniLabel(std::to_string(omniHistory.size()), x + omniMenuW - 32, cy, omniSmall, side, 2);
        else if (i == omniMenuPrivate && !on) omniLabel("Tab limit reached", x + omniMenuW - 32, cy, omniSmall, side, 2);
    }
    omniFadeEnd(); // OMNI_POLISH_V1: the hint bar is outside the fade
    omniPanelHints({ { 0, "Choose" }, { 1, "Close" } }, "D-pad up/down: move   left/right: zoom, mobile site");
}

// --- small things drawn on the shell -------------------------------------------------------------
static bool omniSettingsToolsOpen() { return settingsOpen && !omniMenuOpenFlag; }
constexpr int omniToolsX = 680, omniToolsY = 140, omniToolsW = 220, omniToolsH = 44; // OMNI_POLISH_V1: in the new header row
static bool omniSettingsToolsButton(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_Y) return false;
    omniMenuShow();
    return true;
}
static bool omniSettingsToolsClick(int x, int y)
{
    if (x < omniToolsX || x >= omniToolsX + omniToolsW || y < omniToolsY || y >= omniToolsY + omniToolsH) return false;
    omniMenuShow();
    return true;
}
static void omniSettingsToolsDraw()
{
    const OmniTheme& T = omniTheme();
    const bool hover = pointerX >= omniToolsX && pointerX < omniToolsX + omniToolsW && pointerY >= omniToolsY && pointerY < omniToolsY + omniToolsH;
    struct FadeScope { ~FadeScope() { omniFadeEnd(); } } fadeScope; // OMNI_POLISH_V1: fades in with the panel
    omniFadeBegin(omniToolsX - 4, omniToolsY - 4, omniToolsW + 8, omniToolsH + 8, omniPanelT(omniPanelSettings));
    if (hover) omniRingRect(omniToolsX, omniToolsY, omniToolsW, omniToolsH, omniToolsH / 2, T.accent, T.hover);
    else fillRounded(omniToolsX, omniToolsY, omniToolsW, omniToolsH, omniToolsH / 2, T.key);
    faceIcon(omniToolsX + 26, omniToolsY + omniToolsH / 2, 3, playStationIcons);
    omniLabel("Browser tools", omniToolsX + 50, omniToolsY + omniToolsH / 2.f, omniSmallBold, T.ink, 0, omniToolsW - 64);
}
static bool omniDecorOpen() { return !pageFullscreen; }
static void omniDecorDraw()
{
    // Private tabs: a badge on the tab (only while the bars are fully shown).
    if (omniAutoHideActive() && omniChromeShown < 1) return;
    if (tabs.size() > 4) return; // OMNI_FEATURES_V3: the compact strip marks private tabs itself
    for (size_t i = 0; i < tabs.size(); ++i) {
        if (!tabs[i]->omniPrivate) continue;
        const int x = 100 + int(i) * 240;
        // OMNI_POLISH_V1: smaller caption pill after the (shortened) title, tinted with the tab colour.
        const OmniTheme& T = omniTheme();
        const SDL_Color under = i == selected ? T.bar : T.tab;
        fillRounded(x + 142, 20, 60, 20, 10, omniMix(under, { 150, 110, 235, 255 }, 0.7f));
        omniLabel("Private", x + 172, 30, omniCaptionBold, { 255, 255, 255, 255 }, 1, 54);
    }
}
// OMNI_POLISH_V1: per-tick bookkeeping for the look: which panels just opened (fade), theme changes
// reaching open new-tab pages. Runs from omniStyleTick; only marks the shell dirty while a fade runs.
static void omniPolishTick(uint32_t now)
{
    now = std::max<uint32_t>(now, 2);   // 0 and 1 mean "closed" and "shown without a fade"
    const void* modal = omniModalCurrent();
    const bool open[omniPanelCount] = { settingsOpen, editing, omniMenuOpenFlag, omniHistoryOpenFlag, modal != nullptr };
    static bool was[omniPanelCount] = {};
    static const void* lastModal = nullptr;
    for (int i = 0; i < omniPanelCount; ++i) {
        const bool opened = open[i] && (!was[i] || (i == omniPanelModal && modal != lastModal));
        if (!open[i]) omniPanelSince[i] = 0;
        else if (opened && (omniPanelSince[i] == 0 || i == omniPanelModal)) omniPanelSince[i] = now;
        was[i] = open[i];
        if (omniPanelSince[i] > 1 && now - omniPanelSince[i] < omniPanelFadeMs + 40) omniShellDirty = true;
    }
    lastModal = modal;
    static int theme = -1;
    if (theme != omniThemeIndex) {
        if (theme >= 0) {
            const std::string js = "document.documentElement.setAttribute('style','" + omniNewTabVars(omniTheme()) + "')";
            auto script = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
            for (auto& t : tabs) if (t->omniNewTabPage && !t->loading)
                WKPageEvaluateJavaScriptInMainFrame(t->page, script.get(), nullptr, [](WKTypeRef, WKErrorRef, void*) { });
        }
        theme = omniThemeIndex;
    }
}
[[maybe_unused]] static const bool omniEverydayLayers = [] {
    auto& layers = omniOverlayLayers();
    layers.push_back({ [] { return omniHistoryOpenFlag; }, omniHistoryButton, omniHistoryClick, omniHistoryScrollBy, omniHistoryDraw, true });
    layers.push_back({ [] { return omniMenuOpenFlag; }, omniMenuButton, omniMenuClick, [](double) { return true; }, omniMenuDraw, true });
    layers.push_back({ omniSuggestOpen, omniSuggestButton, omniSuggestClick, nullptr, omniSuggestDraw, false });
    layers.push_back({ omniFindBarOpen, omniFindButton, omniFindClick, nullptr, omniFindDraw, false });
    layers.push_back({ omniSettingsToolsOpen, omniSettingsToolsButton, omniSettingsToolsClick, nullptr, omniSettingsToolsDraw, false });
    layers.push_back({ omniDecorOpen, nullptr, nullptr, nullptr, omniDecorDraw, false });
    return true;
}();

// --- hooks ---------------------------------------------------------------------------------------
static void omniEverydayFinished(Tab& tab)
{
    if (tab.url.rfind(omniNewTabPrefix, 0) == 0) { tab.url.clear(); tab.title = "New tab"; tab.omniNewTabPage = true; }
    else tab.omniNewTabPage = false;
    if (omniFindTab == &tab) omniFindOpenFlag = false;
    const bool reader = std::exchange(tab.omniReader, false);
    if (omniTestMode() || tab.omniPrivate || omniMediaOwns(tab) || reader || !omniWebURL(tab.url)) return;
    omniHistoryAdd(tab.url, tab.title);
}
static void omniEverydayActivated()
{
    Tab* tab = active();
    if (!tab || tab->omniLazyURL.empty()) return;
    const std::string url = std::move(tab->omniLazyURL);
    tab->omniLazyURL.clear();
    if (url == "newtab") omniOpenNewTabPage(tab); else navigate(url);
}
static bool omniSessionReady = false;
static std::string omniSessionSaved;
static std::string omniSessionText()
{
    std::string s = "omni-session\t1\n";
    int n = 0, sel = 0;
    for (size_t i = 0; i < tabs.size(); ++i) {
        const Tab& t = *tabs[i];
        if (t.omniPrivate || omniMediaOwns(t)) continue; // Media section only opens explicitly; no session auto-start.
        if (i == selected) sel = n;
        const std::string url = !t.omniLazyURL.empty() ? t.omniLazyURL : omniWebURL(t.url) ? t.url : std::string("newtab");
        s += "tab\t" + omniOneLine(url, 2048) + "\t" + omniOneLine(t.title, 200) + "\n";
        ++n;
    }
    return s + "selected\t" + std::to_string(sel) + "\n";
}
static void omniSessionSave()
{
    if (!omniSessionReady || omniTestMode()) return;
    std::string s = omniSessionText();
    if (s == omniSessionSaved) return;
    omniSessionSaved = s;
    omniIoQueue(omniData("session.txt"), std::move(s), false);
}
static bool omniEverydayStart()
{
    if (omniTestMode()) return false;   // every self-test mode opens its own start page as before
    omniPrefsLoad();
    omniHistoryLoad();
    std::vector<std::pair<std::string, std::string>> saved;
    int sel = 0;
    if (FILE* f = fopen(omniData("session.txt").c_str(), "r")) {
        char line[2400];
        while (fgets(line, sizeof(line), f)) {
            std::string s(line);
            while (!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
            if (s.rfind("tab\t", 0) == 0 && saved.size() < size_t(omniF3TabLimit())) { // OMNI_FEATURES_V3: tab limit setting
                const size_t t = s.find('\t', 4);
                std::string url = s.substr(4, t == std::string::npos ? std::string::npos : t - 4);
                if (url == "newtab" || omniWebURL(url)) saved.emplace_back(url, t == std::string::npos ? std::string() : s.substr(t + 1));
            } else if (s.rfind("selected\t", 0) == 0) sel = atoi(s.c_str() + 9);
        }
        fclose(f);
    }
    if (saved.empty()) saved.emplace_back("newtab", "New tab");
    omniF3Restoring = true;   // OMNI_FEATURES_V3_FIX1
    for (auto& [url, title] : saved) {
        Tab* tab = newTab();
        if (!tab) break;
        tab->omniLazyURL = url;
        if (url != "newtab") { tab->url = url; tab->title = title.empty() ? omniBlockerHostOf(url) : title; }
    }
    omniF3Restoring = false;
    if (tabs.empty()) return false;
    activate(size_t(std::clamp(sel, 0, int(tabs.size()) - 1)));   // loads that tab; the others load when shown
    omniSessionReady = true;
    omniSessionSaved = omniSessionText();
    if (saved.size() > 1 || saved[0].first != "newtab") notice("Restored " + std::to_string(tabs.size()) + (tabs.size() == 1 ? " tab" : " tabs") + " from last time"); // OMNI_FEATURES_V3_FIX1: what actually opened
    return true;
}
static void omniEverydayTick()
{
    for (auto& tab : tabs) {
        if (tab->omniPendingLoad.empty()) continue;
        auto url = adoptWK(WKURLCreateWithUTF8CString(tab->omniPendingLoad.c_str()));
        tab->omniPendingLoad.clear();
        tab->loading = true;
        WKPageLoadURL(tab->page, url.get());
    }
    static uint32_t lastSave = 0;
    if (SDL_GetTicks() - lastSave >= 1000) { lastSave = SDL_GetTicks(); omniSessionSave(); }
}
static void omniEverydayShutdown()
{
    omniSessionSave();
    omniIoFlush();
}

// OMNI_PERF_A_S4 / S2 ----------------------------------------------------------------------
// Which rows each drawn frame changed. Canvas and screen buffers are exchanged at every 4K hand-off, so the canvas a draw
// starts from holds an older frame: a regional draw redraws the rows changed since that frame (buffer age), and the SDL
// tiler is given the rows changed since the frame on screen (its own per-buffer pending rect covers its other buffer).
struct OmniFrameRows { uint32_t frame = 0; bool full = true; uint64_t key = 0; std::vector<uint8_t> rows; };
static OmniFrameRows omniFrames[4];
static uint32_t omniFrameNo = 0;                       // frames drawn so far
static uint32_t omniCanvasHolds = 0, omniScreenHolds = 0; // frame in canvas->pixels / screen->pixels (0: unknown)
static bool omniCanvasPending = false;                 // OMNI_PERF_A_S7: the canvas holds a drawn frame the presenter was too busy to take
static int omniHoleFrames = 0;                         // full draws still owed after a hole-punched video was shown
static SDL_Rect omniPointerLast { 0, 0, 0, 0 };        // where the last drawn frame has the pointer
// rows: what the next draw redraws (regional). changed: what the next frame changes against the last drawn one, when every cause is
// known (changedKnown); a whole draw for any other reason records "everything changed".
struct OmniRegion { bool active = false, topBar = false, bottomBar = false, fadeTop = false, fadeBottom = false, pointer = false, changedKnown = false; std::vector<uint8_t> rows, changed; };
static OmniRegion omniRegion;                          // set by tick() for the next draw() only
// Bars, their soft edges over the page and the page rows between them, as omniDrawBars() draws them (bars shown or hidden).
struct OmniZones { bool bars = false; int topEnd = 0, fadeTop0 = 0, fadeTopRows = 0, bottom0 = 0, fadeBot0 = 0, fadeBotRows = 0; };
static OmniZones omniZones()
{
    OmniZones z;
    const float shown = omniAutoHideActive() ? omniChromeShown : 1.f;
    if (shown < 1) return z;
    z.bars = true;
    z.topEnd = std::min(physical(top), canvas->h);
    z.fadeTop0 = int(top * shown * displayScale + 0.5); z.fadeTopRows = physical(5);
    const int y0 = std::min(physical(height - bottom), canvas->h), rows = canvas->h - y0;
    const int visible = std::min(rows, int(bottom * shown * displayScale + 0.5));
    z.bottom0 = canvas->h - visible;
    z.fadeBot0 = canvas->h - visible - physical(4); z.fadeBotRows = physical(4);
    return z;
}
static SDL_Rect omniPointerRect()
{
    SDL_Surface* sprite = omniPointerSprite();
    if (!sprite) return { 0, 0, 0, 0 };
    return { int(pointerX * displayScale + 0.5) - omniPointerHotX, int(pointerY * displayScale + 0.5) - omniPointerHotY, sprite->w, sprite->h }; // OMNI_POINTER_STYLE_V1
}
// Layout the frame was drawn with: a regional draw needs the same.
static uint64_t omniFrameKey()
{
    const OmniZones z = omniZones();
    return uint64_t(uint32_t(int(omniPageTopF() * displayScale + 0.5))) | (uint64_t(z.bars) << 20) | (uint64_t(omniAutoHideActive()) << 21)
        | (uint64_t(pageFullscreen) << 22) | (uint64_t(uint32_t(omniThemeIndex) & 255) << 24) | (uint64_t(uint32_t(renderPageHeight)) << 32)
        | (uint64_t(uint32_t(canvas ? canvas->h : 0) & 0xffff) << 48);
}
// After each draw(): which rows this frame changed against the previous one (everything unless tick() planned it with every
// cause known). A whole draw planned that way (e.g. because the canvas was too old) still records only the rows that changed.
static void omniFrameRecord(bool regional)
{
    (void)regional;
    OmniFrameRows& f = omniFrames[++omniFrameNo % 4];
    f.frame = omniFrameNo;
    f.key = omniFrameKey();
    f.full = !omniRegion.changedKnown || int(omniRegion.changed.size()) != (canvas ? canvas->h : 0);
    if (OmniMedia::Hw::holePunchActive()) { omniHoleFrames = 3; f.full = true; }
    else if (omniHoleFrames > 0) { --omniHoleFrames; f.full = true; }
    if (!f.full) f.rows = omniRegion.changed;
    omniRegion.changedKnown = false;
    omniCanvasHolds = omniFrameNo;
    omniPointerLast = omniPointerRect();
    omniPageDamage = OmniRows();
}
// Under omniPresentLock, after the canvas became the screen (exchange) or was copied there: the tiler's damage rows.
static void omniHandOffRecord(bool exchanged)
{
    const uint32_t f = omniCanvasHolds;
    bool full = !omniPerfOn(omniPerfS2) || !f || !omniScreenHolds || f <= omniScreenHolds || f - omniScreenHolds > 3 || OmniMedia::Hw::holePunchActive();
    int y0 = canvas->h, y1 = 0;
    for (uint32_t g = omniScreenHolds + 1; !full && g <= f; ++g) {
        const OmniFrameRows& r = omniFrames[g % 4];
        if (r.frame != g || r.full || int(r.rows.size()) != canvas->h) { full = true; break; }
        for (int y = 0; y < canvas->h; ++y) if (r.rows[y]) { y0 = std::min(y0, y); y1 = std::max(y1, y + 1); }
    }
    omniPresentDamaged = !full;
    if (!full) { if (y1 <= y0) { y0 = 0; y1 = 1; } omniPresentDamage = { 0, y0, canvas->w, y1 - y0 }; }
    // While a video uses the plane the presenter rewrites that buffer (re-flips): its frame is unknown afterwards.
    const uint32_t shown = OmniMedia::Hw::holePunchActive() ? 0 : f;
    if (exchanged) omniCanvasHolds = omniScreenHolds;
    omniScreenHolds = shown;
    omniCanvasPending = false;
}
// Decides how tick() draws: 0 the whole frame (as before), 1 only omniRegion's rows (OMNI_PERF_A_S4), 2 nothing (no visible change).
static int omniPlanDraw(unsigned reasons)
{
    omniRegion.active = omniRegion.topBar = omniRegion.bottomBar = omniRegion.fadeTop = omniRegion.fadeBottom = omniRegion.pointer = false;
    omniRegion.changedKnown = false;
    if (!omniPerfOn(omniPerfS4) || !canvas || canvas == screen) return 0;
    // Only causes whose effect is known: page pixels, the pointer, the loading spinner (top bar), the 1 s refresh (bars).
    // (The refresh is known only with S3: without the shell signature it is the only thing that shows a status change.)
    const unsigned known = omniDrPagePartial | omniDrPageFull | omniDrSafety | omniDrSpinner | omniDrAxis | omniDrStick
        | (omniPerfOn(omniPerfS3) ? omniDrRefresh : 0u);
    if (reasons & ~known) { ++omniCensus.whole[0]; return 0; }
    if (!omniSmoothDrawOn() || canvas->format->format != SDL_PIXELFORMAT_ABGR8888 || renderWidth != canvas->w || pageFullscreen
        || OmniMedia::Hw::holePunchActive() || omniHoleFrames > 0 || editing || settingsOpen || omniStatsPanel.enabled || status != "Ready"
        || !active() || !active()->message.empty() || omniModalCurrent() || !omniPointerSprite())
        { ++omniCensus.whole[1]; return 0; }
    if (omniAutoHideActive() && omniChromeShown != 0.f && omniChromeShown != 1.f) { ++omniCensus.whole[2]; return 0; }   // bars sliding
    for (auto& layer : omniOverlayLayers()) if (layer.open != omniDecorOpen && layer.open()) { ++omniCensus.whole[3]; return 0; }   // dl2-candidate-55: decor is always "open" (see draw())
    const int h = canvas->h;
    const uint64_t key = omniFrameKey();
    if (!omniFrameNo || omniFrames[omniFrameNo % 4].frame != omniFrameNo || omniFrames[omniFrameNo % 4].key != key) { ++omniCensus.whole[4]; return 0; }   // layout changed
    const OmniZones z = omniZones();
    std::vector<uint8_t>& R = omniRegion.changed;
    R.assign(size_t(h), 0);
    auto mark = [h](int a, int b) { a = std::max(a, 0); b = std::min(b, h); if (b > a) memset(R.data() + a, 1, size_t(b - a)); };
    // What changed since the last drawn frame.
    bool changed = false;
    const int pageY = int(omniPageTopF() * displayScale + 0.5);
    if (omniPageDamage.any()) {
        int a = pageY + omniPageDamage.y0, b = pageY + omniPageDamage.y1;
        if (z.bars) { a = std::max(a, z.topEnd); b = std::min(b, z.bottom0); }   // rows under opaque bars never show the page
        if (b > a) { mark(a, b); changed = true; }
    }
    if ((reasons & omniDrSpinner) && z.bars) { mark(0, z.topEnd); changed = true; }
    if ((reasons & omniDrRefresh) && z.bars) { mark(0, z.topEnd); mark(z.bottom0, h); changed = true; }
    const SDL_Rect p = omniPointerRect();
    const bool moved = p.x != omniPointerLast.x || p.y != omniPointerLast.y || p.w != omniPointerLast.w || p.h != omniPointerLast.h;
    if (moved) {
        // Over a bar the pointer changes hover rings: the whole frame then.
        auto overBars = [&z](const SDL_Rect& r) { return z.bars && r.h > 0 && (r.y < z.topEnd || r.y + r.h > z.bottom0); };
        if (overBars(p) || overBars(omniPointerLast)) { ++omniCensus.whole[5]; return 0; }
        mark(p.y, p.y + p.h); mark(omniPointerLast.y, omniPointerLast.y + omniPointerLast.h);
        changed = true;
    }
    if (!changed) return 2;
    omniRegion.changedKnown = true;   // from here on a whole draw still records only these rows
    // Rows to redraw: these, and those changed since the frame the canvas holds (buffer age).
    omniRegion.rows = R;
    std::vector<uint8_t>& D = omniRegion.rows;
    if (!omniCanvasHolds || omniCanvasHolds > omniFrameNo || omniFrameNo - omniCanvasHolds > 3) { ++omniCensus.whole[6]; return 0; }
    for (uint32_t g = omniCanvasHolds + 1; g <= omniFrameNo; ++g) {
        const OmniFrameRows& r = omniFrames[g % 4];
        if (r.frame != g || r.full || r.key != key || int(r.rows.size()) != h) { ++omniCensus.whole[6]; return 0; }
        for (int y = 0; y < h; ++y) D[y] |= r.rows[y];
    }
    auto markD = [h](int a, int b) { a = std::max(a, 0); b = std::min(b, h); if (b > a) memset(D.data() + a, 1, size_t(b - a)); };
    auto touches = [h](int a, int b) { a = std::max(a, 0); b = std::min(b, h); for (int y = a; y < b; ++y) if (D[y]) return true; return false; };
    // Close over what overlaps: a bar is redrawn whole, a soft edge (blended over the page) is re-applied whole, the pointer
    // (blended over everything) is redrawn on rows that are all redrawn.
    for (bool grew = true; grew;) {
        grew = false;
        auto close = [&](int a, int b, bool& flag) { if (b > a && !flag && touches(a, b)) { markD(a, b); flag = true; grew = true; } };
        if (z.bars) {
            close(0, z.topEnd, omniRegion.topBar);
            close(z.fadeTop0, z.fadeTop0 + z.fadeTopRows, omniRegion.fadeTop);
            close(z.bottom0, h, omniRegion.bottomBar);
            close(z.fadeBot0, z.fadeBot0 + z.fadeBotRows, omniRegion.fadeBottom);
        }
        close(p.y, p.y + p.h, omniRegion.pointer);
    }
    unsigned count = 0;
    for (int y = 0; y < h; ++y) count += D[y];
    if (count >= unsigned(h)) { ++omniCensus.whole[7]; return 0; }   // every row: the whole draw is the same work
    omniCensus.regionalRows += count;
    omniRegion.active = true;
    return 1;
}
// OMNI_PERF_A_S3: what the bars, toast and panels show, hashed once per tick (a few microseconds). A change draws at once;
// the refresh that used to run every 100 ms for state changes that set no flag runs once a second.
static uint64_t omniShellSignature()
{
    uint64_t h = 1469598103934665603ull;
    auto mix = [&h](const void* p, size_t n) { const uint8_t* b = static_cast<const uint8_t*>(p); for (size_t i = 0; i < n; ++i) { h ^= b[i]; h *= 1099511628211ull; } };
    auto text = [&mix](const std::string& s) { const size_t n = s.size(); mix(&n, sizeof n); mix(s.data(), n); };
    auto flag = [&mix](bool v) { const uint8_t b = v; mix(&b, 1); };
    text(status); flag(statusUntil != 0); text(address);
    const size_t count = tabs.size(); mix(&count, sizeof count); mix(&selected, sizeof selected);
    for (auto& t : tabs) { text(t->title); text(t->url); text(t->message); flag(t->loading); flag(t->crashed); flag(t->omniPrivate); }
    flag(editing); flag(pageEditing); flag(settingsOpen); flag(pageFullscreen); flag(SDL_GetTicks() < fullscreenHintUntil);
    mix(&omniThemeIndex, sizeof omniThemeIndex); flag(playStationIcons); flag(omniStatsPanel.enabled); flag(omniAutoHide);
    flag(omniBlockerEnabled()); flag(omniBlockerFailed());
    if (Tab* t = active()) { flag(WKPageCanGoBack(t->page)); flag(WKPageCanGoForward(t->page)); }
    for (auto& layer : omniOverlayLayers()) flag(layer.open());
    flag(omniModalCurrent() != nullptr);
    return h;
}
// OMNI_PERF_A_S8: the free 1/60 s timer beats against the 59.94 Hz display (two ticks share one vblank every ~17 s). The timer
// runs at the display's period and, when its phase has drifted more than 2 ms from 1 ms after the presenter's last flip,
// one tick is moved there (at most every 250 ms, only while the presenter flips).
static WTF::RunLoop::Timer* omniRefreshTimer = nullptr;
static constexpr double omniVblankMs = 1001.0 / 60;
static void omniVblankAlign()
{
    static bool realigning = false;
    static Uint64 lastAlign = 0;
    // ws-a-1b: restarting the refresh timer is opt-in (/data/omni/perf-a-s8-align.flag): a timer that is not re-armed would stop
    // the shell silently. Without the flag the timer only runs at the display's period.
    static const bool alignWanted = access("/data/omni/perf-a-s8-align.flag", F_OK) == 0;
    if (!omniRefreshTimer || !omniPerfOn(omniPerfS8) || !alignWanted) return;
    if (realigning) { realigning = false; omniRefreshTimer->startRepeating(WTF::Seconds(omniVblankMs / 1000)); return; }
    const Uint64 now = SDL_GetPerformanceCounter(), v = omniVblankAt.load(std::memory_order_relaxed);
    const double f = double(SDL_GetPerformanceFrequency());
    if (!v || now < v) return;
    const double since = 1000.0 * double(now - v) / f;
    if (since > 100 || (lastAlign && 1000.0 * double(now - lastAlign) / f < 250)) return;
    const double phase = std::fmod(since, omniVblankMs), target = 1.0;
    double err = phase - target;
    if (err > omniVblankMs / 2) err -= omniVblankMs; else if (err <= -omniVblankMs / 2) err += omniVblankMs;
    if (std::fabs(err) <= 2.0) return;
    double delay = omniVblankMs - phase + target;
    if (delay < 4) delay += omniVblankMs;
    lastAlign = now; realigning = true; ++omniCensus.realigns;
    omniRefreshTimer->startOneShot(WTF::Seconds(delay / 1000));
}
// OMNI_PERF_A_COUNTER: once per 5 s, through the engine's log writer thread.
static void omniCensusTick()
{
    static unsigned lines = 0;
    const uint32_t now = SDL_GetTicks();
    ++omniCensus.ticks;
    if (!omniCensus.since) { omniCensus.since = now; return; }
    if (now - omniCensus.since < 5000) return;
    OmniDrawCensus& c = omniCensus;
    if (omniReleaseDiagnostics() && lines < 1500 && (c.draws || c.paints || c.deferred || c.reused)) {
        ++lines;
        const unsigned* r = c.reason;
        char line[640];
        snprintf(line, sizeof line, "draw reasons (5 s): ticks %u draws %u (full %u, regional %u avg %u rows) nothing %u reused %u idle %u videoSkip %u busyKept %u"
            " | first %u page %u partial %u safety %u video %u refresh %u busy %u spinner %u style %u input %u axis %u stick %u webkit %u feature %u signature %u"
            " | WKPagePaint %u avg %.2f max %.1f ms (>20 %u, >100 %u, >400 %u) deferred %u slow %u watchdog %u | safety %u changed %u | forced %u realign %u",
            c.ticks, c.draws, c.full, c.regional, c.regional ? c.regionalRows / c.regional : 0, c.nothing, c.reused, c.idle, c.videoSkips, c.busyKept,
            r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12], r[13], r[14],
            c.paints, c.paints ? c.paintMs / c.paints : 0.0, c.paintMax, c.over20, c.over100, c.over400, c.deferred, c.slowArmed, c.watchdog, c.safety, c.safetyChanged, c.forced, c.realigns);
        log(line);
        const unsigned* g = c.whole;   // dl2-candidate-55
        if (g[0] || g[1] || g[2] || g[3] || g[4] || g[5] || g[6] || g[7]) {
            char why[200];
            snprintf(why, sizeof why, "regional refused (5 s): cause %u mode %u sliding %u overlay %u layout %u hover %u age %u allRows %u", g[0], g[1], g[2], g[3], g[4], g[5], g[6], g[7]);
            log(why);
        }
    }
    // ws-a-1b: a heartbeat in every mode (once a minute, at most 60 lines), so an idle shell can be told from a stopped one.
    static uint32_t beatAt = 0; static unsigned beats = 0, beatTicks = 0, beatDraws = 0, beatPaints = 0, beatBlocked = 0;
    beatTicks += c.ticks; beatDraws += c.draws; beatPaints += c.paints; beatBlocked += c.over100;
    if (!beatAt) beatAt = now;
    if (now - beatAt >= 60000) {
        if (beats++ < 60) { char line[200]; snprintf(line, sizeof line, "shell alive (60 s): ticks %u draws %u page paints %u (blocked %u)", beatTicks, beatDraws, beatPaints, beatBlocked); log(line); }
        beatAt = now; beatTicks = beatDraws = beatPaints = beatBlocked = 0;
    }
    omniCensus = OmniDrawCensus();
    omniCensus.since = now;
}

// OMNI_SHELL_PRESENT_V1 -------------------------------------------------------------------
static void omniPresenterMain()
{
    OmniPresentGuard lock(2);
    for (;;) {
        // OMNI_HOLEPUNCH_V7_REFLIP: while a paced video plays, wake just before each vblank; when no
        // canvas came and the main thread is stalled, the newest due video picture goes into the
        // last presented frame and is flipped from here. -1: wait for a canvas, as before.
        lock.stage(1); // scheduling/state
        const int reflipWaitMs = OmniMedia::Hw::holePunchReflipWaitMs();
        OmniMedia::Hw::diagnosticTrace(20,reflipWaitMs);
        if (reflipWaitMs < 0) lock.wait(omniPresentWake, [] { return omniPresentBusy || omniPresentStop; });
        else if (!lock.waitFor(omniPresentWake, reflipWaitMs, [] { return omniPresentBusy || omniPresentStop; })) {
            OmniMedia::Hw::diagnosticTrace(21,1);
            omniPresentBusy = true;   // the screen surface is this thread's meanwhile
            lock.unlock();
            int reflipResult = 0;
            if (OmniMedia::Hw::holePunchReflip(static_cast<uint8_t*>(screen->pixels), screen->pitch, screen->w, screen->h)) {
                OmniMedia::Hw::diagnosticTrace(22,1);
                reflipResult = SDL_UpdateWindowSurface(window);   // tile + flip + wait for vblank, as for a canvas
                OmniMedia::Hw::holePunchVblank(!reflipResult);
                if (!reflipResult) omniVblankAt.store(SDL_GetPerformanceCounter(), std::memory_order_relaxed); // OMNI_PERF_A_S8
                OmniMedia::Hw::diagnosticTrace(23,reflipResult,1);
            }
            lock.lock();
            if (reflipResult) { omniPresentFailed = true; fprintf(stderr, "browser: present failed: %s\n", SDL_GetError()); fflush(stderr); }
            omniPresentBusy = false;
            omniPresentIdle.notify_all();
            continue;
        }
        OmniMedia::Hw::diagnosticTrace(21,0);
        if (omniPresentStop) return;
        const SDL_Rect damage = omniPresentDamage; const bool damaged = omniPresentDamaged; // OMNI_PERF_A_S2: this canvas's changed rows
        lock.unlock();
        // OMNI_HOLEPUNCH_V8_CADENCE: the video picture due at the vblank this flip reaches, as of now
        OmniMedia::Hw::holePunchBeforeFlip(static_cast<uint8_t*>(screen->pixels), screen->pitch, screen->w, screen->h);
        const auto started = SDL_GetPerformanceCounter();
        OmniMedia::Hw::diagnosticTrace(22,0);
        const int result = damaged ? SDL_UpdateWindowSurfaceRects(window, &damage, 1) : SDL_UpdateWindowSurface(window);   // tile (changed rows) + flip + wait for vblank
        OmniMedia::Hw::holePunchVblank(!result);
        if (!result) omniVblankAt.store(SDL_GetPerformanceCounter(), std::memory_order_relaxed); // OMNI_PERF_A_S8
        OmniMedia::Hw::diagnosticTrace(23,result,0); // OMNI_HOLEPUNCH_V4: the flip time paces hole-punched video
        const double ms = 1000.0 * (SDL_GetPerformanceCounter() - started) / SDL_GetPerformanceFrequency();
        lock.lock();
        if (result) { omniPresentFailed = true; fprintf(stderr, "browser: present failed: %s\n", SDL_GetError()); fflush(stderr); }
        if (!result) omniDisplayPresented();
        ++omniPresents; omniPresentTotalMs += ms; omniPresentMaxMs = std::max(omniPresentMaxMs, ms);
        if (omniReleaseDiagnostics() && !(omniPresents % 300) && omniPresentReports < 12) {
            ++omniPresentReports;
            // OMNI_HOLEPUNCH_V7_REV2: this line was written with omniPresentLock held: on the console's
            // stderr (up to 200 ms a line) the presenter and the next omniPresentFrame waited for it.
            // V7 on: the engine's log writer thread writes it; off: fputs + fflush here, as before.
            char presentLine[256];
            snprintf(presentLine, sizeof presentLine, "browser: OMNI PRESENT: presents=%llu flipWaitAvgMs=%.3f flipWaitMaxMs=%.3f copyAvgMs=%.3f busySkips=%llu\n",
                static_cast<unsigned long long>(omniPresents), omniPresentTotalMs / omniPresents, omniPresentMaxMs,
                omniPresentCopyMs / omniPresents, static_cast<unsigned long long>(omniPresentSkips));
            OmniMedia::Hw::holePunchLogLine(presentLine);
        }
        omniPresentBusy = false;
        omniPresentIdle.notify_all();
    }
}

// Hands the finished canvas to the presenter. Never waits for vblank.
static void omniPresentFrame()
{
    if (canvas == screen) {   // no off-screen canvas: present in place, as before
        if (SDL_UpdateWindowSurface(window)) { log(SDL_GetError()); running = false; }
        else omniDisplayPresented();
        return;
    }
    // Prepare the mask before omniPresentLock: a full-screen scan under that lock
    // previously excluded presenter deadlines. Publication still rechecks pin/epoch.
    OmniMedia::Hw::holePunchPrepareHandOff(static_cast<const uint8_t*>(canvas->pixels), canvas->pitch, canvas->w, canvas->h);
    omniPipelineScope(40,94,0,0);
    OmniPresentGuard lock(1);
    omniPipelineScope(41,94,0,0);
    if (omniPresentFailed) { running = false; return; }
    // A tick can land just before the previous flip's vblank: wait for it briefly (bounded).
    if (omniPresentBusy)
        lock.waitFor(omniPresentIdle, 4, [] { return !omniPresentBusy; });
    if (omniPresentBusy) {
        ++omniPresentSkips;
        // OMNI_PERF_A_S7: still flipping the previous frame. The finished canvas is handed off on the next tick unless something
        // changes meanwhile (was: drawn again from scratch, 30 % of 52 ms draws with a translucent control bar).
        if (omniPerfOn(omniPerfS7)) { omniCanvasPending = true; ++omniCensus.busyKept; return; }
        omniMarkDirty(omniDrBusy);   // as before: draw and present again on the next tick
        return;
    }
    // OMNI_HOLEPUNCH_V7_REV2: which video pixels this canvas holds (a re-flip writes only those)
    lock.stage(2); // validate handoff and prepare live mask
    OmniMedia::Hw::diagnosticTrace(24);
    OmniMedia::Hw::holePunchHandOff(static_cast<const uint8_t*>(canvas->pixels), canvas->pitch, canvas->w, canvas->h);
    const auto started = SDL_GetPerformanceCounter();
    lock.stage(3); // screen copy
    omniPipelineScope(40,93,0,0);
    // Both buffers are SDL-owned and identically laid out. The presenter is idle
    // and omniPresentLock excludes it until the new live mask and pixels are published.
    // SDL's PS5 backend reads window->surface->pixels on every update; SDL blitters
    // likewise refresh their pixel pointers per call. Never exchange external/RLE buffers.
    const bool exchange = int64_t(canvas->w) * canvas->h > int64_t(2560) * 1440 &&
        canvas->w == screen->w && canvas->h == screen->h && canvas->pitch == screen->pitch &&
        canvas->format->format == screen->format->format && canvas->pixels != screen->pixels &&
        !(canvas->flags & SDL_PREALLOC) && !(screen->flags & SDL_PREALLOC) &&
        ((canvas->flags ^ screen->flags) & SDL_SIMD_ALIGNED) == 0 &&
        !SDL_MUSTLOCK(canvas) && !SDL_MUSTLOCK(screen) && !canvas->locked && !screen->locked;
    OmniMedia::Hw::diagnosticTrace(106,exchange,canvas->w,canvas->h);
    if (exchange)
        std::swap(canvas->pixels, screen->pixels);
    else if (canvas->pitch == screen->pitch)
        memcpy(screen->pixels, canvas->pixels, size_t(canvas->pitch) * canvas->h);
    else
        for (int row = 0; row < canvas->h; ++row)
            memcpy(static_cast<uint8_t*>(screen->pixels) + size_t(row) * screen->pitch,
                static_cast<const uint8_t*>(canvas->pixels) + size_t(row) * canvas->pitch, size_t(canvas->w) * 4);
    omniHandOffRecord(exchange); // OMNI_PERF_A_S2/S4: rows the tiler must take; which frame each buffer now holds
    omniPipelineScope(41,93,0,0);
    OmniMedia::Hw::diagnosticTrace(25);
    lock.stage(4); // publish/notify
    omniPresentCopyMs += 1000.0 * (SDL_GetPerformanceCounter() - started) / SDL_GetPerformanceFrequency();
    if (!omniPresenter) omniPresenter = new std::thread(omniPresenterMain);
    omniPresentBusy = true;
    omniPresentWake.notify_one();
}

// Stops the presenter after its current flip. Call before SDL_Quit.
static void omniStopPresenter()
{
    {
        OmniPresentGuard lock(3);
        omniPresentStop = true;
    }
    omniPresentWake.notify_one();
    if (omniPresenter && omniPresenter->joinable()) omniPresenter->join();
}

// OMNI_HOLEPUNCH_V1: call right after the page was blitted at `page`. Redraws the part of
// the page area a hardware video covers: the video below, the page (with its transparent
// hole) blended over it. No-op while no video uses the plane.
// OMNI_FAST_PAGE_V1: paint the page into the full-size buffer. At omniPageScale 0.5, WebKit paints a
// half-size image (cleared the same way the caller clears the full buffer) and each pixel is doubled.
// (omniPageSmall is declared near the top: OMNI_PERF_A_S5)
// OMNI_SMOOTH_DRAW_V1: main-thread draw costs at 4K (stage averages logged as "draw split"), and the full-frame
// passes made cheaper: the page doubled 8 pixels at a time, the page copied into the canvas with a channel swap
// (SDL blended all 8.3M pixels and converted ARGB->ABGR every frame), the background filled only around the page.
// Kill switch: /data/omni/smooth-draw-disabled.flag (SDL paths as before).
extern "C" int omniHDRCpuReady(); // AVX2 + OS support (OmniMain10Bridge.cpp)
static bool omniSmoothDrawOn() { static const bool on = access("/data/omni/smooth-draw-disabled.flag", F_OK) != 0 && omniHDRCpuReady(); return on; }
static inline double omniMsSince(Uint64 t) { return 1000.0 * double(SDL_GetPerformanceCounter() - t) / double(SDL_GetPerformanceFrequency()); }
__attribute__((target("avx2"))) static void omniDoubleRow(uint32_t* d, const uint32_t* s, int width)
{
    const __m256i idx = _mm256_setr_epi32(0, 0, 1, 1, 2, 2, 3, 3);
    int x = 0;
    for (; x + 8 <= width; x += 8) {
        const __m128i v = _mm_loadu_si128(reinterpret_cast<const __m128i*>(s + x / 2));
        _mm256_storeu_si256(reinterpret_cast<__m256i*>(d + x), _mm256_permutevar8x32_epi32(_mm256_castsi128_si256(v), idx));
    }
    for (; x + 1 < width; x += 2) d[x] = d[x + 1] = s[x / 2];
    if (width & 1) d[width - 1] = s[(width - 1) / 2];
}
// ARGB8888 (memory B,G,R,A) -> ABGR8888 (R,G,B,A). False if any pixel is not opaque (the caller blends that row).
__attribute__((target("avx2"))) static bool omniCopyRowOpaque(uint32_t* d, const uint32_t* s, int n)
{
    const __m256i swap = _mm256_setr_epi8(2,1,0,3, 6,5,4,7, 10,9,8,11, 14,13,12,15, 2,1,0,3, 6,5,4,7, 10,9,8,11, 14,13,12,15);
    const __m256i alpha = _mm256_set1_epi32(int(0xff000000u));
    int x = 0;
    for (; x + 8 <= n; x += 8) {
        const __m256i v = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(s + x));
        if (_mm256_movemask_epi8(_mm256_cmpeq_epi32(_mm256_and_si256(v, alpha), alpha)) != -1) return false;
        _mm256_storeu_si256(reinterpret_cast<__m256i*>(d + x), _mm256_shuffle_epi8(v, swap));
    }
    for (; x < n; ++x) { const uint32_t v = s[x]; if ((v >> 24) != 255) return false; d[x] = (v & 0xff00ff00u) | ((v >> 16) & 255) | ((v & 255) << 16); }
    return true;
}
// OMNI_PERF_A_S5/S6 row kernel (host test, bit-exact against SDL 2.30: changes/ws-a-1/tests/test_rowover.cc + rowover.hh)
// One row of the page (ARGB8888 as WKPagePaint writes it: memory B,G,R,A) into the canvas (ABGR8888: R,G,B,A),
// blended over the opaque background exactly as SDL 2.30's BlitNtoNPixelAlpha (ALPHA_BLEND_RGBA) does after the
// background fill: c = s*a + d*(255-a) + 1; c += c >> 8; c >>= 8 (alpha: s = 255). a == 0 keeps the background,
// a == 255 is the plain channel swap. Doubled: s holds n/2 pixels, each shown twice (the half-resolution page).
template <bool Doubled>
__attribute__((target("avx2"))) static void omniRowOver(uint32_t* d, const uint32_t* s, int n, uint32_t bg)
{
    const __m256i swap = _mm256_setr_epi8(2,1,0,3, 6,5,4,7, 10,9,8,11, 14,13,12,15, 2,1,0,3, 6,5,4,7, 10,9,8,11, 14,13,12,15);
    const __m256i abc = _mm256_setr_epi8(3,3,3,3, 7,7,7,7, 11,11,11,11, 15,15,15,15, 3,3,3,3, 7,7,7,7, 11,11,11,11, 15,15,15,15);
    const __m256i amask = _mm256_set1_epi32(int(0xff000000u)), idx = _mm256_setr_epi32(0, 0, 1, 1, 2, 2, 3, 3);
    const __m256i bgv = _mm256_set1_epi32(int(bg)), zero = _mm256_setzero_si256();
    const __m256i c255 = _mm256_set1_epi16(255), one = _mm256_set1_epi16(1);
    const __m256i dlo = _mm256_unpacklo_epi8(bgv, zero), dhi = _mm256_unpackhi_epi8(bgv, zero);
    int x = 0;
    for (; x + 8 <= n; x += 8) {
        const __m256i v = Doubled ? _mm256_permutevar8x32_epi32(_mm256_castsi128_si256(_mm_loadu_si128(reinterpret_cast<const __m128i*>(s + x / 2))), idx)
                                  : _mm256_loadu_si256(reinterpret_cast<const __m256i*>(s + x));
        const __m256i av = _mm256_and_si256(v, amask);
        if (_mm256_movemask_epi8(_mm256_cmpeq_epi32(av, amask)) == -1) { _mm256_storeu_si256(reinterpret_cast<__m256i*>(d + x), _mm256_shuffle_epi8(v, swap)); continue; }
        if (_mm256_testz_si256(av, av)) { _mm256_storeu_si256(reinterpret_cast<__m256i*>(d + x), bgv); continue; }
        const __m256i sv = _mm256_or_si256(_mm256_shuffle_epi8(v, swap), amask), a = _mm256_shuffle_epi8(v, abc);
        __m256i slo = _mm256_unpacklo_epi8(sv, zero), shi = _mm256_unpackhi_epi8(sv, zero);
        const __m256i alo = _mm256_unpacklo_epi8(a, zero), ahi = _mm256_unpackhi_epi8(a, zero);
        slo = _mm256_add_epi16(_mm256_add_epi16(_mm256_mullo_epi16(slo, alo), _mm256_mullo_epi16(dlo, _mm256_sub_epi16(c255, alo))), one);
        shi = _mm256_add_epi16(_mm256_add_epi16(_mm256_mullo_epi16(shi, ahi), _mm256_mullo_epi16(dhi, _mm256_sub_epi16(c255, ahi))), one);
        slo = _mm256_srli_epi16(_mm256_add_epi16(slo, _mm256_srli_epi16(slo, 8)), 8);
        shi = _mm256_srli_epi16(_mm256_add_epi16(shi, _mm256_srli_epi16(shi, 8)), 8);
        _mm256_storeu_si256(reinterpret_cast<__m256i*>(d + x), _mm256_packus_epi16(slo, shi));
    }
    for (; x < n; ++x) {
        const uint32_t v = s[Doubled ? x / 2 : x], a = v >> 24;
        if (a == 255) { d[x] = (v & 0xff00ff00u) | ((v >> 16) & 255) | ((v & 255) << 16); continue; }
        if (!a) { d[x] = bg; continue; }
        const uint32_t sc[4] = { (v >> 16) & 255, (v >> 8) & 255, v & 255, 255 };   // R, G, B, A (canvas byte order)
        uint32_t out = 0;
        for (int c = 0; c < 4; ++c) {
            uint32_t t = sc[c] * a + ((bg >> (8 * c)) & 255) * (255 - a) + 1;
            t += t >> 8;
            out |= ((t >> 8) & 255) << (8 * c);
        }
        d[x] = out;
    }
}
// Canvas rows [a, b) from the page buffer (the whole frame: 0, canvas->h). OMNI_PERF_A_S5: from the half-resolution page when the
// 4K buffer lags it (doubled, swapped and copied in one pass; odd rows copy the row above). OMNI_PERF_A_S6: rows with transparency
// (a hole-punched video under the page) are blended 8 pixels at a time with SDL's arithmetic instead of SDL fill + blit per row.
static void omniPageToCanvasRows(const SDL_Rect& dst, SDL_Color bg, int a, int b)
{
    const Uint32 bgPixel = SDL_MapRGBA(canvas->format, bg.r, bg.g, bg.b, bg.a);
    a = std::max(a, 0); b = std::min(b, canvas->h);
    if (b <= a) return;
    const int y0 = std::max(0, dst.y), y1 = std::min(canvas->h, dst.y + renderPageHeight);
    // around the page: background (bars and dialogs draw over it next)
    if (y0 > a) { SDL_Rect r { 0, a, canvas->w, std::min(y0, b) - a }; if (r.h > 0) SDL_FillRect(canvas, &r, bgPixel); }
    if (y1 < b) { const int s = std::max(y1, a); SDL_Rect r { 0, s, canvas->w, b - s }; if (r.h > 0) SDL_FillRect(canvas, &r, bgPixel); }
    const int ra = std::max(a, y0), rb = std::min(b, y1);
    if (rb <= ra) return;
    const bool fast = omniSmoothDrawOn() && dst.x == 0 && canvas->format->format == SDL_PIXELFORMAT_ABGR8888 && renderWidth <= canvas->w;
    if (!fast) {   // as before (the whole page; a regional draw is never planned without the fast path)
        omniEnsurePixels();
        SDL_Rect r { 0, y0, canvas->w, y1 - y0 }; SDL_FillRect(canvas, &r, bgPixel);
        SDL_Rect d = dst; SDL_BlitSurface(pageSurface, nullptr, canvas, &d);
        return;
    }
    if (renderWidth < canvas->w) { SDL_Rect r { renderWidth, ra, canvas->w - renderWidth, rb - ra }; SDL_FillRect(canvas, &r, bgPixel); }
    auto row = [](int y) { return reinterpret_cast<uint32_t*>(static_cast<uint8_t*>(canvas->pixels) + size_t(y) * canvas->pitch); };
    const int sw = (renderWidth + 1) / 2;
    if (omniPixelsStale && omniPageSmall.size() >= size_t(sw) * ((renderPageHeight + 1) / 2)) {   // OMNI_PERF_A_S5
        int previous = -1;
        for (int y = ra; y < rb; ++y) {
            const int source = (y - dst.y) / 2;
            uint32_t* d = row(y);
            if (source == previous) { memcpy(d, row(y - 1), size_t(renderWidth) * 4); continue; }
            previous = source;
            omniRowOver<true>(d, omniPageSmall.data() + size_t(source) * sw, renderWidth, bgPixel);
        }
        return;
    }
    omniEnsurePixels();
    const bool blend = omniPerfOn(omniPerfS6);
    const uint32_t* src = reinterpret_cast<const uint32_t*>(pixels.data());
    for (int y = ra; y < rb; ++y) {
        uint32_t* d = row(y);
        if (blend) { omniRowOver<false>(d, src + size_t(y - dst.y) * renderWidth, renderWidth, bgPixel); continue; }   // OMNI_PERF_A_S6
        if (omniCopyRowOpaque(d, src + size_t(y - dst.y) * renderWidth, renderWidth)) continue;
        SDL_Rect fr { 0, y, renderWidth, 1 }; SDL_FillRect(canvas, &fr, bgPixel);   // a row with transparency: as before
        SDL_Rect sr { 0, y - dst.y, renderWidth, 1 }, dr { 0, y, 0, 0 }; SDL_BlitSurface(pageSurface, &sr, canvas, &dr);
    }
}
static void omniPageToCanvas(const SDL_Rect& dst, SDL_Color bg) { omniPageToCanvasRows(dst, bg, 0, canvas->h); }
// OMNI_PERF_A_S5: the 4K page buffer for its readers (video compose, preview capture): every row doubled from the half-size page.
static void omniEnsurePixels()
{
    if (!omniPixelsStale) return;
    omniPixelsStale = false;
    const int sw = (renderWidth + 1) / 2;
    if (omniPageSmall.size() < size_t(sw) * ((renderPageHeight + 1) / 2) || pixels.size() < size_t(renderWidth) * renderPageHeight * 4) return;
    uint32_t* dst = reinterpret_cast<uint32_t*>(pixels.data());
    for (int y = 0; y < renderPageHeight; ++y) {
        uint32_t* d = dst + size_t(y) * renderWidth;
        if (y & 1) { memcpy(d, d - renderWidth, size_t(renderWidth) * 4); continue; }
        omniDoubleRow(d, omniPageSmall.data() + size_t(y / 2) * sw, renderWidth);
    }
}
// OMNI_PERF_A_COUNTER / S1: every WKPagePaint timed. One that blocks (>= 100 ms: the web process has not answered for its backing
// store) stops page paints on that tab for 500 ms, doubling up to 2 s while it keeps blocking; a fast one resets that.
static void omniPagePaintTimed(unsigned char* buffer, WKSize size, WKRect rect)
{
    Tab* tab = active();
    const Uint64 t0 = SDL_GetPerformanceCounter();
    WKPagePaint(tab->page, buffer, size, rect);
    const double ms = omniMsSince(t0);
    OmniDrawCensus& c = omniCensus;
    ++c.paints; c.paintMs += ms; c.paintMax = std::max(c.paintMax, ms);
    if (ms > 20) ++c.over20;
    if (ms > 100) ++c.over100;
    if (ms > 400) ++c.over400;
    if (!omniPerfOn(omniPerfS1)) return;
    if (ms >= 100) {
        static unsigned notes = 0;
        tab->omniSlowBackoff = tab->omniSlowBackoff ? std::min<uint32_t>(tab->omniSlowBackoff * 2, 2000) : 500;
        tab->omniSlowUntil = SDL_GetTicks() + tab->omniSlowBackoff;
        ++c.slowArmed;
        if (notes++ < 30) { char line[160]; snprintf(line, sizeof line, "page paint blocked %.0f ms: no page paint on this tab for %u ms", ms, tab->omniSlowBackoff); log(line); }
    } else if (ms < 20) tab->omniSlowBackoff = 0;
}
// OMNI_DIRTY_PAINT_V1: repaint only the reported rect of the page buffer. -1: not possible (paint all), 0: the rect came
// out identical (nothing to draw: e.g. a hidden player control updating under a fullscreen video), 1: changed.
static int omniPaintPagePartial(int rows, const OmniViewDirty& r)
{
    if (!omniSmoothDrawOn()) return -1;
    if (omniPixelsStale && OmniMedia::Hw::holePunchActive()) return -1;   // OMNI_PERF_A_S5: the compose needs the whole 4K buffer
    rows = std::clamp(rows, 0, renderPageHeight);
    const bool half = omniPageScale < 1;
    const int bw = half ? (renderWidth + 1) / 2 : renderWidth, bh = half ? (renderPageHeight + 1) / 2 : renderPageHeight;
    const int brows = half ? (rows + 1) / 2 : rows;
    uint32_t* buf = half ? omniPageSmall.data() : reinterpret_cast<uint32_t*>(pixels.data());
    if (half && omniPageSmall.size() != size_t(bw) * bh) return -1;
    const int x0 = std::clamp(int(std::floor(r.x0)), 0, bw), x1 = std::clamp(int(std::ceil(r.x1)), 0, bw);
    const int y0 = std::clamp(int(std::floor(r.y0)), 0, brows), y1 = std::clamp(int(std::ceil(r.y1)), 0, brows);
    if (x1 <= x0 || y1 <= y0) return 0;
    if (int64_t(x1 - x0) * (y1 - y0) * 2 > int64_t(bw) * brows) return -1;   // most of the page: the full path is as cheap
    const int w = x1 - x0; static std::vector<uint32_t> saved; saved.resize(size_t(w) * (y1 - y0));
    const uint32_t clear = OmniMedia::Hw::holePunchActive() ? 0u : 0xffffffffu;
    for (int y = y0; y < y1; ++y) {
        uint32_t* row = buf + size_t(y) * bw + x0;
        memcpy(saved.data() + size_t(y - y0) * w, row, size_t(w) * 4);
        std::fill(row, row + w, clear);
    }
    omniPagePaintTimed(reinterpret_cast<unsigned char*>(buf), WKSizeMake(bw, bh), WKRectMake(x0, y0, w, y1 - y0)); // OMNI_PERF_A_COUNTER
    bool same = true;
    for (int y = y0; y < y1 && same; ++y) same = !memcmp(saved.data() + size_t(y - y0) * w, buf + size_t(y) * bw + x0, size_t(w) * 4);
    if (same) return 0;
    if (half) omniPageDamage.add(2 * y0, std::min(rows, 2 * y1)); else omniPageDamage.add(y0, y1); // OMNI_PERF_A_S4
    if (half && !omniPixelsStale) {   // the doubled rows of that rect, as omniPaintPage does for all of them (OMNI_PERF_A_S5: not while the canvas reads the half-size page)
        uint32_t* dst = reinterpret_cast<uint32_t*>(pixels.data());
        const int dx0 = 2 * x0, dx1 = std::min(renderWidth, 2 * x1);
        for (int y = 2 * y0; y < std::min(rows, 2 * y1); ++y) {
            uint32_t* d = dst + size_t(y) * renderWidth + dx0;
            if (y & 1) { memcpy(d, d - renderWidth, size_t(dx1 - dx0) * 4); continue; }
            omniDoubleRow(d, buf + size_t(y / 2) * bw + x0, dx1 - dx0);
        }
    }
    return 1;
}
static void omniPaintPage(int rows)
{
    rows = std::clamp(rows, 0, renderPageHeight);
    omniPageDamage.add(0, renderPageHeight); // OMNI_PERF_A_S4
    if (omniPageScale >= 1) {
        omniPixelsStale = false;
        omniPagePaintTimed(pixels.data(), WKSizeMake(renderWidth, renderPageHeight), WKRectMake(0, 0, renderWidth, rows)); // OMNI_PERF_A_COUNTER
        return;
    }
    const int sw = (renderWidth + 1) / 2, sh = (renderPageHeight + 1) / 2, sr = (rows + 1) / 2;
    omniPageSmall.resize(size_t(sw) * sh);
    std::fill(omniPageSmall.begin(), omniPageSmall.begin() + size_t(sw) * sr, OmniMedia::Hw::holePunchActive() ? 0u : 0xffffffffu);
    omniPagePaintTimed(reinterpret_cast<unsigned char*>(omniPageSmall.data()), WKSizeMake(sw, sh), WKRectMake(0, 0, sw, sr)); // OMNI_PERF_A_COUNTER
    // OMNI_PERF_A_S5: no 4K copy (33 MB written per paint); the canvas reads the half-size page. Video under the page needs it.
    if (omniPerfOn(omniPerfS5) && omniSmoothDrawOn() && !OmniMedia::Hw::holePunchActive()) { omniPixelsStale = true; return; }
    if (omniPixelsStale) { omniEnsurePixels(); return; }   // every row, from the page just painted
    uint32_t* dst = reinterpret_cast<uint32_t*>(pixels.data());
    for (int y = 0; y < rows; ++y) {
        uint32_t* d = dst + size_t(y) * renderWidth;
        if (y & 1) { memcpy(d, d - renderWidth, size_t(renderWidth) * 4); continue; }
        const uint32_t* s = omniPageSmall.data() + size_t(y / 2) * sw;
        if (omniSmoothDrawOn()) { omniDoubleRow(d, s, renderWidth); continue; }   // OMNI_SMOOTH_DRAW_V1
        for (int x = 0; x + 1 < renderWidth; x += 2) d[x] = d[x + 1] = s[x / 2];
        if (renderWidth & 1) d[renderWidth - 1] = s[sw - 1];
    }
}
static void omniHolePunchCompose(const SDL_Rect& page)
{
    OmniMedia::Hw::diagnosticTrace(26);
    OmniMedia::Hw::holePunchCompose(static_cast<uint8_t*>(canvas->pixels), canvas->pitch, canvas->w, canvas->h,
        page.x, page.y, pixels.data(), renderWidth * 4, renderWidth, renderPageHeight);
    OmniMedia::Hw::diagnosticTrace(27);
}

// OMNI_STALL_FIX1: the automatic preview capture (OMNI_CAPTURE_V1, feature tests at 12 s, or capture-preview.flag)
// PNG-encoded the 4K page buffer and the 4K canvas on the main thread: one ~540 ms draw() every feature-test run,
// which the scroll bench saw as one ~550 ms frame whenever its 6 s window covered the 12 s mark. Now both buffers
// are copied (one malloc + memcpy, ~66 MB at 4K) and encoded on a worker thread, as the page screenshot does
// (OmniPageTools.h). Same files, same moment; if the copy cannot be allocated the old synchronous path runs.
static std::atomic<int> omniCaptureState { 0 };   // 0 idle, 1 writing, 2 written, 3 failed
static bool omniCaptureAsync()
{
    if (omniCaptureState.load() == 1) return false;
    const int w = renderWidth, ph = renderPageHeight, h = renderHeight;
    if (!canvas || w <= 0 || ph <= 0 || h <= 0 || pixels.size() < size_t(w) * ph * 4) return false;
    const size_t row = size_t(w) * 4, pageBytes = row * ph, shellBytes = row * h;
    unsigned char* copy = static_cast<unsigned char*>(malloc(pageBytes + shellBytes));
    if (!copy) return false;
    memcpy(copy, pixels.data(), pageBytes);
    const unsigned char* shell = static_cast<const unsigned char*>(canvas->pixels);
    for (int y = 0; y < h; ++y) memcpy(copy + pageBytes + row * y, shell + size_t(canvas->pitch) * y, row);
    omniCaptureState = 1;
    std::thread([copy, w, ph, h, pageBytes]() {
        omniWritePng("/data/omni/browser-page-preview.png", copy, w, ph, w * 4);
        const bool ok = omniWritePng("/data/omni/browser-preview.png", copy + pageBytes, w, h, w * 4);
        free(copy);
        omniCaptureState = ok ? 2 : 3;
    }).detach();
    return true;
}
static void omniCaptureFinish() { for (int i = 0; i < 300 && omniCaptureState.load() == 1; ++i) usleep(10000); } // shutdown: a write in progress gets up to 3 s

void draw()
{
    const OmniTheme& T = omniTheme(); // OMNI_STYLE_V1
    Uint64 omniT = SDL_GetPerformanceCounter(); // OMNI_SMOOTH_DRAW_V1: stage timing
    auto omniLap = [&omniT](double& acc) { const Uint64 now = SDL_GetPerformanceCounter(); acc += 1000.0 * double(now - omniT) / double(SDL_GetPerformanceFrequency()); omniT = now; };
    if (OmniMedia::Hw::holePunchActive()) omniEnsurePixels(); // OMNI_PERF_A_S5: the compose reads the 4K page buffer
    // OMNI_PERF_A_S4: tick() planned which rows changed (page rows, the pointer, the spinner's top bar): only those are drawn, in
    // the same order and with the same code as the whole frame (page, bars, their soft edges, toast, pointer).
    const bool omniRegional = omniRegion.active && !pageFullscreen;
    omniRegion.active = false;
    if (omniRegional) {
        const SDL_Rect destinationRect {0, int(omniPageTopF() * displayScale + 0.5), renderWidth, renderPageHeight};
        const std::vector<uint8_t>& rows = omniRegion.rows;
        for (int y = 0; y < canvas->h;) {
            if (!rows[y]) { ++y; continue; }
            int end = y;
            while (end < canvas->h && rows[end]) ++end;
            omniPageToCanvasRows(destinationRect, T.bg, y, end);
            y = end;
        }
        omniLap(omniSplit.blit);
        omniLap(omniSplit.compose);
        const OmniZones z = omniZones();
        if (omniRegion.topBar) omniDrawTopBar();
        if (omniRegion.fadeTop) omniFadeRows(z.fadeTop0, z.fadeTopRows, 70, 0);
        if (omniRegion.bottomBar) omniDrawHintBar();
        if (omniRegion.fadeBottom) omniFadeRows(z.fadeBot0, z.fadeBotRows, 0, 45);
        omniDrawToast();   // shows nothing (planned only while the status is "Ready"); keeps its state as in every draw
        if (omniRegion.topBar && omniDecorOpen()) omniDecorDraw();   // dl2-candidate-55: private-tab badges over the redrawn top bar
        if (omniRegion.pointer) omniDrawPointer();
    } else if (!pageFullscreen) {
    // OMNI_STYLE_V1: the page first, then the bars over it (they may be sliding away), then the
    // toast, keyboard and settings. Without auto-hide the page sits below the top bar as before.
    SDL_Rect destinationRect {0, int(omniPageTopF() * displayScale + 0.5), renderWidth, renderPageHeight};
    omniPageToCanvas(destinationRect, T.bg); // OMNI_SMOOTH_DRAW_V1 (was: fill all + SDL blend blit)
    omniLap(omniSplit.blit);
    omniHolePunchCompose(destinationRect); // OMNI_HOLEPUNCH_V1
    omniLap(omniSplit.compose);
    omniDrawBars();
    omniDrawToast();
    if (editing) omniDrawKeyboard();
    if (settingsOpen) omniSettingsPanel();
    } else {
        SDL_Rect destinationRect {0, 0, renderWidth, renderPageHeight};
        omniPageToCanvas(destinationRect, T.bg); // OMNI_SMOOTH_DRAW_V1
        omniLap(omniSplit.blit);
        omniHolePunchCompose(destinationRect); // OMNI_HOLEPUNCH_V1
        omniLap(omniSplit.compose);
        if (SDL_GetTicks() < fullscreenHintUntil) {
            omniShadow(280, 16, 720, 40, omniRadius, 10, 110, 3);
            fillRounded(280, 16, 720, 40, omniRadius, T.raised);
            faceIcon(306, 36, 1, playStationIcons); // OMNI_POLISH_V1: labels with ellipsis, the site instead of the raw URL
            const int lw = omniLabel("Return to browser", 330, 36, omniSmallBold, T.ink);
            omniLabel(omniBlockerHostOf(active()->url), 330 + lw + 24, 36, omniSmall, T.inkDim, 0, 1000 - 24 - (330 + lw + 24));
        }
    }
    if (!omniRegional) { // OMNI_PERF_A_S4: a regional draw is planned only with no panel, overlay or modal open (the pointer is drawn above)
    if(omniStatsPanel.enabled && omniStatsSurface) {
        SDL_Rect where {physical(12),physical(12),0,0};
        SDL_BlitSurface(omniStatsSurface,nullptr,canvas,&where);
    }
    omniOverlayDraw(); // OMNI_DIALOGS_V1: modals, menus and overlays above the shell
    omniDrawPointer(); // OMNI_STYLE_V1: bigger pointer with a soft shadow
    }
    static Uint32 omniCaptureCheckAt = 0; // OMNI_CAPTURE_V1: flag polled once per second, not every frame
    bool omniCaptureWanted = false;
    if (SDL_GetTicks() >= omniCaptureCheckAt) { omniCaptureCheckAt = SDL_GetTicks() + 1000; omniCaptureWanted = !access("/data/omni/capture-preview.flag", F_OK); }
    if (omniCaptureState.load() == 3) { omniCaptureState = 0; savedPreview = false; fprintf(stderr, "browser: preview capture failed (background write); retrying\n"); } // OMNI_STALL_FIX1: retry as before
    else if (omniCaptureState.load() == 2) { omniCaptureState = 0; fprintf(stderr, "browser: preview capture written (background)\n"); }
    if (active() && omniCaptureState.load() != 1 && ((featureTest && !savedPreview && (!pipelineTraceTest || testStage >= 5) && SDL_GetTicks() - startTime > 12000) || omniCaptureWanted)) { // OMNI_CAPTURE_V1: automatic capture only in feature tests
        OmniLocalScope traceScope(21);
        omniEnsurePixels(); // OMNI_PERF_A_S5: the page preview is the 4K page buffer
        unlink("/data/omni/capture-preview.flag");
        if (omniCaptureAsync()) savedPreview = true; // OMNI_STALL_FIX1: encoded off the main thread (state 3 above clears it again)
        else {
        omniWritePng("/data/omni/browser-page-preview.png", pixels.data(), renderWidth, renderPageHeight, renderWidth * 4);
        savedPreview = omniWritePng("/data/omni/browser-preview.png", static_cast<unsigned char*>(canvas->pixels), renderWidth, renderHeight, canvas->pitch);
        }
        auto script = adoptWK(WKStringCreateWithUTF8CString("JSON.stringify({ready:document.readyState,fonts:document.fonts.status,textLength:document.body.innerText.length,font:getComputedStyle(document.body).fontFamily})"));
        WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), nullptr, [](WKTypeRef result, WKErrorRef error, void*) {
            if (!error && result && WKGetTypeID(result) == WKStringGetTypeID()) log(OmniTest::toStd(static_cast<WKStringRef>(result)).c_str());
            else log("page inspection failed");
        });
    }
    omniLap(omniSplit.chrome);
    omniFrameRecord(omniRegional); // OMNI_PERF_A_S4/S2: the rows this frame changed
    omniPresentFrame(); // OMNI_SHELL_PRESENT_V1
    omniLap(omniSplit.present);
    if (++omniSplit.frames == 300) {   // OMNI_SMOOTH_DRAW_V1
        if (omniSplit.reports++ < 20 && omniReleaseDiagnostics()) {
            char line[320];
            snprintf(line, sizeof line, "draw split (300 draws, avg ms): page+bg %.2f compose %.2f chrome %.2f present %.2f | page paints %u avg %.2f ms (partial %u, unchanged %u) | needsDisplay %u avg %.0f px%s",
                omniSplit.blit / 300, omniSplit.compose / 300, omniSplit.chrome / 300, omniSplit.present / 300, omniSplit.paints,
                omniSplit.paints ? omniSplit.paint / omniSplit.paints : 0.0, omniSplit.partial, omniSplit.unchanged, omniSplit.dirtyCalls, omniSplit.dirtyCalls ? omniSplit.dirtyArea / omniSplit.dirtyCalls : 0.0,
                omniSmoothDrawOn() ? "" : " (smooth draw off)");
            log(line);
        }
        const unsigned reports = omniSplit.reports; omniSplit = OmniDrawSplit(); omniSplit.reports = reports;
    }
}

// OMNI_FULLSCREEN_KEYS_V1: one key press (down + up) as a page keyboard shortcut.
static void omniFullscreenKey(const char* text, const char* identifier, int keysym)
{
    if (!active()) return;
    const size_t length = text ? strlen(text) : 0;
    for (auto type : { kWKEventKeyDown, kWKEventKeyUp })
        WKPageHandleKeyboardEvent(active()->page, WKKeyboardEventMake(type, kWKInputTypeNormal, text ? text : "", length, identifier, keysym, 0, 0, 0));
}

void button(int button)
{
    if (omniSavedButton(button)) { omniShellDirty = true; return; }
    if (omniMcButton(button)) { omniShellDirty = true; return; } // OMNI_PAD_CONTROLLER_V1: Master Control page first
    if (omniOverlayButton(button)) { omniShellDirty = true; return; } // OMNI_DIALOGS_V1: modals and menus first
    omniShellDirty = true; // OMNI_SHELL_DRAW_V1
    omniChromeButton(button); // OMNI_STYLE_V1: buttons bring hidden bars back
    if (editing && (button == SDL_CONTROLLER_BUTTON_B || button == SDL_CONTROLLER_BUTTON_BACK)) {
        dismissKeyboard();
        return;
    }
    if (pageFullscreen && active()) {
        if (button == SDL_CONTROLLER_BUTTON_A) click();
        else if (button == SDL_CONTROLLER_BUTTON_B || button == SDL_CONTROLLER_BUTTON_START || button == SDL_CONTROLLER_BUTTON_BACK) WKViewRequestExitFullScreen(active()->view.get());
        // OMNI_FULLSCREEN_KEYS_V1: video player shortcuts (YouTube's keyboard keys).
        else if (button == SDL_CONTROLLER_BUTTON_X) omniFullscreenKey("k", "U+004B", 0x6b);
        else if (button == SDL_CONTROLLER_BUTTON_LEFTSHOULDER) omniFullscreenKey("j", "U+004A", 0x6a);
        else if (button == SDL_CONTROLLER_BUTTON_RIGHTSHOULDER) omniFullscreenKey("l", "U+004C", 0x6c);
        else if (button == SDL_CONTROLLER_BUTTON_DPAD_LEFT) omniFullscreenKey(nullptr, "Left", 0xff51);
        else if (button == SDL_CONTROLLER_BUTTON_DPAD_RIGHT) omniFullscreenKey(nullptr, "Right", 0xff53);
        else if (button == SDL_CONTROLLER_BUTTON_DPAD_UP) omniFullscreenKey(nullptr, "Up", 0xff52);
        else if (button == SDL_CONTROLLER_BUTTON_DPAD_DOWN) omniFullscreenKey(nullptr, "Down", 0xff54);
        else if (button == SDL_CONTROLLER_BUTTON_Y) omniFullscreenKey("c", "U+0043", 0x63);
        else if (button == SDL_CONTROLLER_BUTTON_LEFTSTICK) omniFullscreenKey("m", "U+004D", 0x6d);
        return;
    }
    if (button == SDL_CONTROLLER_BUTTON_BACK) { settingsOpen = !settingsOpen; fieldClickDeadline = 0; omniSettingsRow = 0; return; } // OMNI_STYLE_V1: row reset
    if (settingsOpen) {
        if (button == SDL_CONTROLLER_BUTTON_A || button == SDL_CONTROLLER_BUTTON_B) settingsOpen = false;
        else if (button == SDL_CONTROLLER_BUTTON_DPAD_UP) omniSettingsRow = std::max(0, omniSettingsRow - 1); // OMNI_STYLE_V1
        else if (button == SDL_CONTROLLER_BUTTON_DPAD_DOWN) omniSettingsRow = std::min(4, omniSettingsRow + 1);
        else if (button == SDL_CONTROLLER_BUTTON_DPAD_LEFT || button == SDL_CONTROLLER_BUTTON_DPAD_RIGHT)
            omniSettingsChange(button == SDL_CONTROLLER_BUTTON_DPAD_RIGHT); // row 0: controller style, as before
        return;
    }
    if (editing) { omniKbButton(button); return; } // OMNI_KEYBOARD_V2: Options = Go (it quit Omni), all keyboard keys
    if (button == SDL_CONTROLLER_BUTTON_START) { omniFxQuickMenuShow(); return; } // OMNI_FEATURES_V1: quick menu (Exit Omni is in it, with a confirm)
    if (!active()) return;
    if (button == SDL_CONTROLLER_BUTTON_A) click();
    else if (button == SDL_CONTROLLER_BUTTON_B) omniFxBack(); // OMNI_FEATURES_V1: a notice when there is no earlier page
    else if (button == SDL_CONTROLLER_BUTTON_Y) { if (WKPageIsContentEditable(active()->page)) editPage(); else editAddress(); }
    else if (button == SDL_CONTROLLER_BUTTON_X) { if (newTab()) { if (!omniTestMode()) omniOpenNewTabPage(active()); address.clear(); editing = true; omniKbPageReset(); } } // OMNI_SHORTCUTS_V1: letters page first
    else if (button == SDL_CONTROLLER_BUTTON_RIGHTSHOULDER) activate((selected + 1) % tabs.size());
    else if (button == SDL_CONTROLLER_BUTTON_LEFTSHOULDER) activate((selected + tabs.size() - 1) % tabs.size());
    else if (button == SDL_CONTROLLER_BUTTON_LEFTSTICK) omniShortcutAddCurrent(); // OMNI_SHORTCUTS_V1
    else if (button == SDL_CONTROLLER_BUTTON_TOUCHPAD) omniTranslateToggle(); // OMNI_TRANSLATE_V1
    else if (button == SDL_CONTROLLER_BUTTON_RIGHTSTICK) closeTab();
    else if (omniFxDpadSide(button)) { } // OMNI_FEATURES_V1: D-pad left/right = back/forward (setting: switch tabs)
    else if (button == SDL_CONTROLLER_BUTTON_DPAD_DOWN) scroll(-140);
    else if (button == SDL_CONTROLLER_BUTTON_DPAD_UP) scroll(140);
}

// OMNI_KEYBOARD_V2: held buttons repeat; L2/R2 move the caret by word and the right stick by
// character (its vertical axis scrolls the page as when browsing). Called once per main-loop pass;
// it only asks for a redraw when something moved.
static void omniKbTick()
{
    static int stickDir = 0;
    static uint32_t stickNext = 0;
    static bool trigger[2] = {};
    static uint32_t triggerNext[2] = {};
    if (!editing || !controller) { omniKbRepeatButton = -1; stickDir = 0; trigger[0] = trigger[1] = false; return; }
    const uint32_t now = SDL_GetTicks();
    if (omniKbRepeatButton >= 0) {
        if (!SDL_GameControllerGetButton(controller, SDL_GameControllerButton(omniKbRepeatButton))) omniKbRepeatButton = -1;
        else if (int32_t(now - omniKbRepeatNext) >= 0) {
            const int b = omniKbRepeatButton;
            ++omniKbRepeatCount;
            omniKbRepeating = true; button(b); omniKbRepeating = false;
            const bool pad = b >= SDL_CONTROLLER_BUTTON_DPAD_UP && b <= SDL_CONTROLLER_BUTTON_DPAD_RIGHT;
            const bool words = omniKbRepeatCount > 12 && (b == SDL_CONTROLLER_BUTTON_X || b == SDL_CONTROLLER_BUTTON_A);
            omniKbRepeatNext = now + (words ? 150 : pad ? 90 : 60);
        }
    }
    if (!editing) return;
    const bool caretKeys = !(omniKb.kind == 0 && omniKbPage == 1);
    for (int i = 0; i < 2; ++i) {
        const int v = SDL_GameControllerGetAxis(controller, i ? SDL_CONTROLLER_AXIS_TRIGGERRIGHT : SDL_CONTROLLER_AXIS_TRIGGERLEFT);
        const bool held = caretKeys && v > (trigger[i] ? 9000 : 16000);
        if (held && (!trigger[i] || int32_t(now - triggerNext[i]) >= 0)) {
            triggerNext[i] = now + (trigger[i] ? 110 : 400);
            omniKbMove(1, i ? 1 : -1);
            omniChromeWake();
            omniShellDirty = true;
        }
        trigger[i] = held;
    }
    const int rx = SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_RIGHTX);
    const int ry = SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_RIGHTY);
    const float caretGate = omniStickGate(true, 20000.f / 32768) * 32768; // OMNI_STICK_DEADZONE_V1: 20000 at Medium
    const int dir = !caretKeys || std::abs(rx) < std::abs(ry) ? 0 : rx > caretGate ? 1 : rx < -caretGate ? -1 : 0;
    if (dir && (dir != stickDir || int32_t(now - stickNext) >= 0)) {
        stickNext = now + (dir != stickDir ? 380 : 70);
        omniKbMove(0, dir);
        omniShellDirty = true;
    }
    stickDir = dir;
    const float rk = omniStickScale(controller, true), rDead = omniStickDeadZone(true) * 32768.f; // OMNI_STICK_DEADZONE_V1: 1 and 7000 at Medium
    if (rk > 0 && std::abs(ry) > rDead && std::abs(ry) > std::abs(rx)) { omniChromeScroll(); scroll(-ry / 32768.f * rk * 55); omniShellDirty = true; }
}

// OMNI_SHOULDER_DOWNLOADS_V1: included after button(), before tick().
static OmniInput::ShoulderContext omniShoulderContext()
{
    const bool attached = controller && SDL_GameControllerGetAttached(controller);
    const bool focused = omniShoulderFocused && running && attached && active();
    const auto id = attached ? SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controller)) : -1;
    const bool eligible = omniMediaDownloadsEnabled && focused && !omniTestMode() && !pageFullscreen
        && !editing && !pageEditing && !omniKbTarget && !settingsOpen
        && !omniOverlayOpen() && !omniFindBarOpen() && !active()->crashed;
    return { id, active() ? active()->omniMediaIdentity : 0, eligible, focused };
}
static uint8_t omniShoulderPhysical()
{
    if (!controller || !SDL_GameControllerGetAttached(controller)) return 0;
    return (SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_LEFTSHOULDER) ? OmniInput::ShoulderChord::left : 0)
        | (SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER) ? OmniInput::ShoulderChord::right : 0);
}
static void omniShoulderReset()
{
    // SDL snapshots can include FUTURE queued edges. A mid-queue handoff must
    // conservatively wait for neutral, never sample a future release and rearm.
    omniShoulderChord.reset(omniShoulderContext(), OmniInput::ShoulderChord::both);
    omniSavedCancel();
}
static void omniShoulderButton(const SDL_ControllerButtonEvent& event)
{
    const bool down = event.type == SDL_CONTROLLERBUTTONDOWN;
    if (down) {
        auto* previous = controller;
        omniActivatePad(event.which);
        if (previous != controller) omniShoulderReset();
    }
    const auto before = omniShoulderContext();
    // Releasing a different pad must neither activate it nor release this pad.
    if (before.controller != event.which) return;
    const bool left = event.button == SDL_CONTROLLER_BUTTON_LEFTSHOULDER;
    const bool right = event.button == SDL_CONTROLLER_BUTTON_RIGHTSHOULDER;
    if (!left && !right) {
        if (down) button(event.button); // L3/R3 and every other button untouched.
    } else if (!omniMediaDownloadsEnabled) {
        // Track held state for a possible later enabling, but never let a tab
        // activation/cancel suppress ANY baseline shoulder DOWN while disabled.
        (void)omniShoulderChord.edge(before,
            left ? OmniInput::Shoulder::Left : OmniInput::Shoulder::Right, down);
        if (down) button(event.button);
    } else {
        using OmniInput::ShoulderAction;
        const auto action = omniShoulderChord.edge(before,
            left ? OmniInput::Shoulder::Left : OmniInput::Shoulder::Right, down);
        switch (action) {
        case ShoulderAction::None: break;
        case ShoulderAction::PassDown: button(event.button); break;
        case ShoulderAction::LeftSingle: button(SDL_CONTROLLER_BUTTON_LEFTSHOULDER); break;
        case ShoulderAction::RightSingle: button(SDL_CONTROLLER_BUTTON_RIGHTSHOULDER); break;
        case ShoulderAction::OpenSection:
            // Existing hook enforces feature/capacity/startup policy. False
            // opens only the section; it never shares the current/private URL.
            // OMNI_NET_GRABBER_V1: a public page's grabbed rows ride along (same gated snapshot as L2).
            if (!omniGrabBegin(2)) omniMediaDownloadsOpen(false);
            break;
        }
    }
    omniShoulderChord.contextChanged(omniShoulderContext());
}

// OMNI_SAVED_LINKS_V1: fixed local-page commands, never page-provided script.
static OmniSavedLinks::Context omniSavedContext()
{
    const bool attached = controller && SDL_GameControllerGetAttached(controller);
    const auto pad = attached ? SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controller)) : -1;
    const bool allowed = omniMediaDownloadsEnabled && omniShoulderFocused && running && attached && active()
        && !omniTestMode() && !editing && !pageEditing && !omniKbTarget && !settingsOpen
        && !omniOverlayOpen() && !omniFindBarOpen() && !active()->crashed;
    return { pad, active() ? active()->omniMediaIdentity : 0, active() ? active()->omniSavedDocument : 0, allowed, pageFullscreen };
}
static void omniSavedReconcile()
{
    if (!omniMediaDownloadsEnabled) { omniSavedTriggers.cancel(); return; }
    const auto c = omniSavedContext();
    const int left = controller ? SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_TRIGGERLEFT) : 0;
    const int right = controller ? SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_TRIGGERRIGHT) : 0;
    omniSavedTriggers.reconcile(c, left, right);
}
static std::string omniSavedCurrentURL()
{
    if (!active() || active()->omniPrivate) return ""; // Privacy BEFORE any URL copy.
    auto url = adoptWK(WKPageCopyActiveURL(active()->page));
    if (!url) return "";
    auto value = adoptWK(WKURLCopyString(url.get()));
    if (!value || WKStringGetLength(value.get()) > 4096) return "";
    return OmniTest::toStd(value.get());
}
enum class OmniSavedView { None, Form, Saved };
static OmniSavedView omniSavedOwnedView()
{
    if (!active() || !active()->omniMediaSection || active()->omniPrivate) return OmniSavedView::None;
    const auto url = omniSavedCurrentURL();
    if (url == OmniMediaSection::base()) return OmniSavedView::Form;
    if (url == OmniMediaSection::base() + "#view=saved") return OmniSavedView::Saved;
    return OmniSavedView::None;
}
static bool omniSavedCommand(const char* action, bool requireSaved)
{
    if (!omniSavedContext().enabled || pageFullscreen) return false;
    const auto view = omniSavedOwnedView();
    if (view == OmniSavedView::None || (requireSaved && view != OmniSavedView::Saved)) return false;
    // Every caller supplies one compile-time fixed script. No URL/JS from a page.
    auto script = adoptWK(WKStringCreateWithUTF8CString(action));
    WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), nullptr, nullptr);
    return true;
}
static void omniSavedOpenNow()
{
    if (omniSavedOwnedView() != OmniSavedView::None) {
        omniSavedCommand("window.omniMediaController?.('saved.open')", false);
        return;
    }
    if (!active()) return;
    const bool privateSource = active()->omniPrivate;
    const auto source = omniSavedCurrentURL();
    if (active()->omniMediaSection && (active()->loading || OmniMediaSection::belongs(source, OmniMediaSection::base()))) {
        notice("Wait for Media downloads to finish opening"); return;
    }
    const bool valid = !privateSource && OmniMediaSection::validLink(source);
    if (valid && omniLinkReviewBegin()) return;
    omniMediaDownloadsOpenSaved(valid ? source : "", valid && active()->omniSavedVideo.seen);
    if (privateSource) notice("Opening saved links; the private page was not shared");
}
static void omniSavedL2()
{
    if (!pageFullscreen) { omniSavedOpenNow(); return; }
    if (!active() || omniSavedExit.active()) return;
    omniSavedExitIdentity = active()->omniMediaIdentity;
    omniSavedExitDocument = active()->omniSavedDocument;
    omniSavedExitPad = omniSavedContext().pad;
    omniSavedExitPrivate = active()->omniPrivate;
    omniSavedExitURL = omniSavedCurrentURL();
    omniSavedExit.arm(SDL_GetTicks());
    // Explicit L2 alone may request fullscreen exit; detection never does.
    WKViewRequestExitFullScreen(active()->view.get());
}
static void omniSavedAxis(const SDL_ControllerAxisEvent& event)
{
    const auto c = omniSavedContext();
    if (c.pad != event.which) return;
    const auto trigger = event.axis == SDL_CONTROLLER_AXIS_TRIGGERLEFT ? OmniSavedLinks::Trigger::Left : OmniSavedLinks::Trigger::Right;
    switch (omniSavedTriggers.axis(c, trigger, event.value)) {
    case OmniSavedLinks::Action::None: break;
    case OmniSavedLinks::Action::Saved: omniSavedL2(); break;
    case OmniSavedLinks::Action::Prefill:
        if (active() && active()->omniMediaSection && (active()->loading
                || OmniMediaSection::belongs(omniSavedCurrentURL(), OmniMediaSection::base())))
            omniSavedCommand("window.omniMediaController?.('form.prefillCandidate')", false);
        else if (!omniGrabBegin(1)) omniMediaDownloadsOpen(true); // OMNI_NET_GRABBER_V1: prefill the top grabbed candidate
        break;
    }
}
// OMNI_DOWNLOADS_NAV_V1: the Media downloads page (fixed local URL, both its views) gets Circle,
// Triangle, D-pad up/down and Cross first. Its fixed script answers whether it used the press;
// when it did not (no dialog, focus in a text field, nothing to move to), the press runs the
// normal browser action instead of being swallowed. Circle also closes the topmost open dialog
// when the page's controller declines (it ignores presses while a text field has focus).
static bool omniSavedSkip = false;
static void omniSavedFallback(WKTypeRef result, WKErrorRef error, void* context)
{
    const bool handled = !error && result && WKGetTypeID(result) == WKStringGetTypeID() && OmniTest::toStd(static_cast<WKStringRef>(result)) == "1";
    if (handled || !running) return;
    // Circle with nothing left to close or step back through on the downloads page (it rewrites
    // its own history): return to the page Media downloads was opened from, else the previous tab.
    const int pressed = static_cast<int>(reinterpret_cast<intptr_t>(context));
    if (pressed == SDL_CONTROLLER_BUTTON_B && active() && omniSavedOwnedView() != OmniSavedView::None && !WKPageCanGoBack(active()->page)) {
        for (size_t i = 0; i < tabs.size(); ++i)
            if (tabs[i].get() != active() && tabs[i]->omniMediaIdentity == omniMediaOriginIdentity) { activate(i); omniShellDirty = true; return; }
        for (size_t i = tabs.size(); i-- > 0;)
            if (tabs[i].get() != active() && !tabs[i]->omniMediaSection) { activate(i); omniShellDirty = true; return; }
        return;
    }
    if (pressed == SDL_CONTROLLER_BUTTON_DPAD_LEFT || pressed == SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return;   // OMNI_FEATURES_V3_FIX1: as in 42, no browser Back/Forward from the downloads page
    omniSavedSkip = true;
    button(static_cast<int>(reinterpret_cast<intptr_t>(context)));
    omniSavedSkip = false;
}
static bool omniSavedButton(int b)
{
    if (!omniMediaDownloadsEnabled || omniSavedSkip) return false;
    if (omniSavedOwnedView() == OmniSavedView::None || !omniSavedContext().enabled || pageFullscreen) return false;
    const char* script = nullptr;
    switch (b) {
    case SDL_CONTROLLER_BUTTON_Y: script = "window.omniMediaController?.('saved.saveCandidate')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_DPAD_UP: script = "window.omniMediaController?.('saved.previous')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: script = "window.omniMediaController?.('saved.next')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: script = "window.omniMediaController?.('saved.left')===true?'1':'0'"; break;   // OMNI_DOWNLOADS_NAV_V2: grids (themes)
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: script = "window.omniMediaController?.('saved.right')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_A: script = "window.omniMediaController?.('saved.choose')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_B: script = "(window.omniMediaController?.('saved.dismiss')===true||(()=>{const d=[...document.querySelectorAll('dialog[open]')].pop();if(!d)return false;d.close();return true})())?'1':'0'"; break;
    default: return false;
    }
    auto source = adoptWK(WKStringCreateWithUTF8CString(script));
    WKPageEvaluateJavaScriptInMainFrame(active()->page, source.get(), reinterpret_cast<void*>(static_cast<intptr_t>(b)), omniSavedFallback);
    return true;
}
// OMNI_PAD_CONTROLLER_V1: the Master Control page (http://127.0.0.1:8095 or http://192.0.2.10:8095, exact
// origin) gets the D-pad, Cross, Circle, Square, Triangle, L1 and R1 first through its window.omniPadController.
// One compile-time fixed script per button; no URL or script from a page. Not handled: the normal action.
static bool omniMcSkip = false;
static void omniMcFallback(WKTypeRef result, WKErrorRef error, void* context)
{
    const bool handled = !error && result && WKGetTypeID(result) == WKStringGetTypeID() && OmniTest::toStd(static_cast<WKStringRef>(result)) == "1";
    if (handled || !running) return;
    omniMcSkip = true;
    button(static_cast<int>(reinterpret_cast<intptr_t>(context)));
    omniMcSkip = false;
}
static bool omniMcButton(int b)
{
    if (omniMcSkip || !active() || pageFullscreen || settingsOpen || editing || omniOverlayOpen() || active()->crashed || !omniMcOrigin(active()->url)) return false;
    const char* script = nullptr;
    switch (b) {
    case SDL_CONTROLLER_BUTTON_DPAD_UP: script = "window.omniPadController?.('up')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: script = "window.omniPadController?.('down')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: script = "window.omniPadController?.('left')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: script = "window.omniPadController?.('right')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_A: script = "window.omniPadController?.('cross')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_B: script = "window.omniPadController?.('circle')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_X: script = "window.omniPadController?.('square')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_Y: script = "window.omniPadController?.('triangle')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: script = "window.omniPadController?.('l1')===true?'1':'0'"; break;
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: script = "window.omniPadController?.('r1')===true?'1':'0'"; break;
    default: return false;
    }
    auto source = adoptWK(WKStringCreateWithUTF8CString(script));
    WKPageEvaluateJavaScriptInMainFrame(active()->page, source.get(), reinterpret_cast<void*>(static_cast<intptr_t>(b)), omniMcFallback);
    return true;
}
static void omniSavedScrollFallback(WKTypeRef result, WKErrorRef error, void* context)
{
    const bool handled = !error && result && WKGetTypeID(result) == WKStringGetTypeID() && OmniTest::toStd(static_cast<WKStringRef>(result)) == "1";
    if (!handled && running) omniPageWheel(static_cast<double>(reinterpret_cast<intptr_t>(context)) / 16);
}
// The right stick scrolls the topmost open dialog's scroll box wherever the pointer is (the
// backdrop is inert, so a wheel over it moved nothing). No dialog: the normal wheel.
static bool omniSavedScroll(double amount)
{
    if (!omniMediaDownloadsEnabled || !active() || omniSavedOwnedView() == OmniSavedView::None || !omniSavedContext().enabled) return false;
    char script[512];
    snprintf(script, sizeof script, "(()=>{const d=[...document.querySelectorAll('dialog[open]')].pop();if(!d)return false;const s=[d,...d.querySelectorAll('*')].find(e=>e.scrollHeight>e.clientHeight+1&&/(auto|scroll)/.test(getComputedStyle(e).overflowY));if(s)s.scrollBy(0,%d);return true})()?'1':'0'", static_cast<int>(-amount));
    auto source = adoptWK(WKStringCreateWithUTF8CString(script));
    WKPageEvaluateJavaScriptInMainFrame(active()->page, source.get(), reinterpret_cast<void*>(static_cast<intptr_t>(amount * 16)), omniSavedScrollFallback);
    return true;
}
static void omniSavedDocumentChanged(Tab& tab)
{
    ++tab.omniSavedDocument;
    tab.omniSavedVideo.reset();
    if (&tab == active()) omniSavedCancel();
}
static void omniSavedMediaChanged(WKPageRef page)
{
    Tab* tab = omniTabForPage(page);
    if (!tab) return;
    const bool allowed = omniMediaDownloadsEnabled && !omniTestMode() && !tab->omniPrivate
        && !(tab->omniMediaSection && OmniMediaSection::belongs(tab->url, OmniMediaSection::base()))
        && !tab->loading && !tab->crashed && tab->message.empty()
        && OmniMediaSection::validLink(tab->url);
    // This getter reads UI-process cached state, not media bytes or a DOM scan.
    tab->omniSavedVideo.observe(allowed && (WKPageGetMediaState(page) & kWKMediaIsPlayingVideo), allowed);
}
static void omniSavedLinksTick()
{
    omniLinkReviewTick();
    if (!omniMediaDownloadsEnabled) {
        omniSavedCancel();
        for (auto& tab : tabs) tab->omniSavedVideo.reset();
        return;
    }
    if (omniSavedExit.active()) {
        const auto c = omniSavedContext();
        const bool same = c.enabled && c.pad == omniSavedExitPad && active()
            && active()->omniMediaIdentity == omniSavedExitIdentity && active()->omniSavedDocument == omniSavedExitDocument
            && active()->omniPrivate == omniSavedExitPrivate && (omniSavedExitPrivate || omniSavedCurrentURL() == omniSavedExitURL);
        const auto result = omniSavedExit.poll(SDL_GetTicks(), same, pageFullscreen);
        if (result == OmniSavedLinks::ExitResult::Open) { omniSavedExitURL.clear(); omniSavedOpenNow(); }
        else if (result == OmniSavedLinks::ExitResult::Cancelled) { omniSavedExitURL.clear(); notice("Saved links opening cancelled; press L2 to try again"); }
    }
    if (active() && (active()->omniPrivate || (active()->omniMediaSection
            && OmniMediaSection::belongs(active()->url, OmniMediaSection::base())))) active()->omniSavedVideo.reset();
    if (active() && active()->omniSavedVideo.takeNotice(omniSavedContext().enabled && !pageFullscreen
            && !active()->loading && OmniMediaSection::validLink(active()->url)))
        notice("Video found — L2 to review");
}

#include "OmniNativeLinkReview.inc" // OMNI_LINK_REVIEW_V1: native-gated isolated manual pull
// OMNI_NET_GRABBER_V1: R2 / Send current link / L1+R1 / menu run the same gated snapshot + network merge as L2.
// False (private tab, Media downloads tab, invalid page URL, gate busy or not eligible) = the button's old path.
static bool omniGrabBegin(int destination)
{
    omniLinkSupersedeOwed(); // OMNI_C52_FIX1: this press's own path runs now; an older cancelled press is not replayed
    if (!active() || active()->omniPrivate || active()->omniMediaSection) return false; // privacy before any URL copy
    if (!OmniMediaSection::validLink(omniSavedCurrentURL())) return false;
    return omniLinkReviewBegin(destination);
}

#include "OmniFeatures.h" // OMNI_FEATURES_V1
#include "OmniFeatures2.h" // OMNI_FEATURES_V2
#include "OmniFeatures3.h" // OMNI_FEATURES_V3
void tick(void*)
{
    // OMNI_HOLEPUNCH_V7_STALLTRACE: the main thread's phases for the stall log; after tick() returns
    // (any return) it is in the run loop again
    struct OmniPhaseOutside { ~OmniPhaseOutside() { OmniMedia::Hw::holePunchShellPhase(0); } } omniPhaseOutside;
    OmniMedia::Hw::holePunchShellPhase(1);
    const auto frameStarted = SDL_GetPerformanceCounter();
    struct OmniDirtyPhaseReset { ~OmniDirtyPhaseReset() { omniDirtyPhase = omniDrWebKit; } } omniDirtyPhaseReset; // OMNI_PERF_A_COUNTER: outside tick: WebKit
    omniDirtyPhase = omniDrFeature;
    omniVblankAlign(); // OMNI_PERF_A_S8
    omniCensusTick(); // OMNI_PERF_A_COUNTER
    // OMNI_TICK_GAP_V1 (diagnostic): a gap > 60 ms between ticks, with how long the previous tick itself ran. A long gap after a
    // short tick means the run loop was busy elsewhere (WebKit IPC, timers); after a long tick, in the tick.
    struct OmniTickGap { Uint64 lastStart = 0, lastEnd = 0; unsigned notes = 0; double paint = 0, draw = 0, prevPaint = 0, prevDraw = 0; };
    static OmniTickGap omniGap;
    struct OmniTickEnd { ~OmniTickEnd() { omniGap.lastEnd = SDL_GetPerformanceCounter(); } } omniTickEnd;
    omniGap.prevPaint = omniGap.paint; omniGap.prevDraw = omniGap.draw; omniGap.paint = omniGap.draw = 0;
    if (omniGap.lastStart && omniGap.notes < 10) {
        const double f = double(SDL_GetPerformanceFrequency());
        const double gap = 1000.0 * double(frameStarted - omniGap.lastStart) / f, ran = 1000.0 * double(omniGap.lastEnd - omniGap.lastStart) / f;
        if (gap > 120) { ++omniGap.notes; fprintf(stderr, "browser: main loop gap %.0f ms (previous tick ran %.1f ms: page paint %.1f, draw %.1f, other %.1f; then %.0f ms outside tick) at %u ms\n", gap, ran, omniGap.prevPaint, omniGap.prevDraw, ran - omniGap.prevPaint - omniGap.prevDraw, gap - ran, SDL_GetTicks()); }
    }
    omniGap.lastStart = frameStarted;
    static uint64_t profileFrames = 0, profilePaint = 0, profileDraw = 0;
    static uint64_t profileStarted = frameStarted;
    static unsigned profileReports = 0;
    static bool firstFrame = true;
    static uint32_t lastBlockerPoll = 0;
    if (SDL_GetTicks() - lastBlockerPoll > 500) { OmniMedia::Hw::holePunchShellPhase(2); omniBlockerPoll(); OmniMedia::Hw::holePunchShellPhase(1); lastBlockerPoll = SDL_GetTicks(); } // OMNI_HOLEPUNCH_V7_STALLTRACE: uBlock
    for (auto& tab : tabs) {
        if (tab->pendingURL.empty()) continue;
        auto url = adoptWK(WKURLCreateWithUTF8CString(tab->pendingURL.c_str()));
        tab->pendingURL.clear();
        tab->loading = true;
        WKPageLoadURL(tab->page, url.get());
        if (tab.get() == active()) notice("uBO skipped a redirect / cleaned the link");
    }
    omniEverydayTick(); // OMNI_EVERYDAY_V1: re-issued loads, session save (background write)
    omniMediaDownloadsTick(); // OMNI_MEDIA_DOWNLOADS_V1: nonblocking completion only
    omniSavedLinksTick(); // OMNI_SAVED_LINKS_V1: no I/O or DOM scan.
    omniFxTick(); // OMNI_FEATURES_V1: hold timer, settings load
    omniF2Tick(); // OMNI_FEATURES_V2: permission prompts, picker cancel
    omniF3Tick(); // OMNI_FEATURES_V3: suggestions, screenshot, dark pages, tab memory
    if (statusUntil && SDL_GetTicks() > statusUntil) { statusUntil = 0; status = "Ready"; }
    static bool popupEngineWarm = false;
    if (!popupEngineWarm && active() && active()->loadedAt && SDL_GetTicks() - active()->loadedAt > 4000) {
        // Load the small `$popup` rule set while idle, not during the first popup.
        popupEngineWarm = true;
        omniUBlockPopupBlocked("https://omni.invalid/warm-up", "https://omni.invalid/");
    }
    if (firstFrame) log("first frame: polling input");
    if (!editing && active() && fieldClickDeadline) {
        if (SDL_GetTicks() > fieldClickDeadline) fieldClickDeadline = 0;
        else if (WKPageIsContentEditable(active()->page)) editPage();
    }
    if (uiTest && active() && !active()->loading && SDL_GetTicks() - active()->loadedAt > 1500) {
        omniPaintPage(renderPageHeight); // OMNI_FAST_PAGE_V1
        for (bool ps : {false,true}) {
            playStationIcons=ps; editing=false; settingsOpen=false; draw();
            omniWritePng(ps ? "/data/omni/ui-playstation.png" : "/data/omni/ui-xbox.png",static_cast<unsigned char*>(canvas->pixels),renderWidth,renderHeight,canvas->pitch);
            editing=true; pageEditing=true; draw();
            omniWritePng(ps ? "/data/omni/keyboard-playstation.png" : "/data/omni/keyboard-xbox.png",static_cast<unsigned char*>(canvas->pixels),renderWidth,renderHeight,canvas->pitch);
        }
        editing=false; settingsOpen=true; draw();
        omniWritePng("/data/omni/controller-settings.png",static_cast<unsigned char*>(canvas->pixels),renderWidth,renderHeight,canvas->pitch);
        log("UI TEST: captured Xbox, PlayStation and settings views"); running=false;
    } else if (displayTest && active()) {
        if (SDL_GetTicks() - startTime > 45000) { log("DISPLAY TEST FAIL: timeout"); running = false; }
        else if (!active()->loading && active()->title == "Example Domain" && SDL_GetTicks() - active()->loadedAt > 3000) {
            omniPaintPage(renderPageHeight); // OMNI_FAST_PAGE_V1
            draw();
            bool saved = omniWritePng("/data/omni/display-browser.png",static_cast<unsigned char*>(canvas->pixels),renderWidth,renderHeight,canvas->pitch);
            fprintf(stderr,"browser: DISPLAY TEST %s: page and shell rendered at %dx%d\n",saved ? "PASS" : "FAIL",renderWidth,renderHeight);
            running = false;
        }
    } else if (recoveryTest && active()) {
        if (SDL_GetTicks() - stageTime > 30000) { log("RELOAD TEST FAIL: timeout"); running = false; }
        else if (SDL_GetTicks() - stageTime > 1000) {
            if (testStage == 0 && !active()->loading && active()->title == "Example Domain") {
                log("RELOAD TEST: killing owned renderer to test unexpected shared-process failure");
                auto pid = WKPageGetProcessIdentifier(active()->page);
                if (pid <= 0 || pid == getpid() || kill(pid, SIGKILL)) { log("RELOAD TEST FAIL: could not terminate owned renderer"); running = false; return; }
                testStage = 1; stageTime = SDL_GetTicks();
            } else if (testStage == 1 && !active()->message.empty()) {
                WKPageReload(active()->page); testStage = 2; stageTime = SDL_GetTicks();
            } else if (testStage == 2 && !active()->loading && active()->loadedAt >= stageTime && active()->message.empty() && active()->title == "Example Domain") {
                ++recoveryCycles;
                fprintf(stderr, "browser: RELOAD TEST recovered=%d\n", recoveryCycles); fflush(stderr);
                if (recoveryCycles == 3) { log("RELOAD TEST PASS: three unexpected renderer crashes with two tabs without closing browser"); running = false; }
                else { testStage = 0; stageTime = SDL_GetTicks(); }
            }
        }
    } else if (featureTest && active()) {
        if (stagedMediaTest && !stagedMediaStarted && !active()->loading) {
            stagedMediaStarted = true;
            stageTime = SDL_GetTicks();
            auto script = adoptWK(WKStringCreateWithUTF8CString(
                "document.readyState==='complete'&&typeof window.omniStartMediaTest==='function'?(window.omniStartMediaTest(), 'staged media started'):'staged media unavailable'"));
            WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), nullptr, [](WKTypeRef result, WKErrorRef error, void*) {
                log(!error && result && WKGetTypeID(result) == WKStringGetTypeID()
                    ? OmniTest::toStd(static_cast<WKStringRef>(result)).c_str() : "FEATURE DIAG: staged start failed");
            });
        }
        // Inspect before document completion: a media load can delay window.load.
        // One outstanding callback, at most three snapshots, within the existing
        // test deadline. Never log page URLs, cookies, or arbitrary body contents.
        if (featureSnapshotPending && SDL_GetTicks() - featureSnapshotStarted > 5000) {
            log("FEATURE DIAG: DOM callback deadline exceeded");
            featureSnapshotPending = false;
            featureSnapshotCount = 3;
        }
        if (!featureSnapshotPending && featureSnapshotCount < 3
            && SDL_GetTicks() - startTime > 5000 + featureSnapshotCount * 10000) {
            featureSnapshotPending = true;
            featureSnapshotStarted = SDL_GetTicks();
            ++featureSnapshotCount;
            log(active()->loading ? "FEATURE DIAG: requesting DOM while loading" : "FEATURE DIAG: requesting DOM after load");
            auto script = adoptWK(WKStringCreateWithUTF8CString(
                "JSON.stringify({ready:document.readyState,body:!!document.body,results:Array.isArray(window.omniFeatureResults)?window.omniFeatureResults.length:null,video:Array.from(document.querySelectorAll('video')).slice(0,2).map(v=>({network:v.networkState,ready:v.readyState,time:v.currentTime,error:v.error?v.error.code:null})),staged:typeof window.omniStartMediaTest,isolation:window.omniMediaIsolation?window.omniMediaIsolation.snapshot():null})"));
            WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), nullptr, [](WKTypeRef result, WKErrorRef error, void*) {
                featureSnapshotPending = false;
                log(!error && result && WKGetTypeID(result) == WKStringGetTypeID()
                    ? ("FEATURE DIAG: " + OmniTest::toStd(static_cast<WKStringRef>(result))).c_str()
                    : "FEATURE DIAG: DOM inspection failed");
            });
        }
        if (mediaControlsTest && !active()->loading && SDL_GetTicks() - active()->loadedAt > 1500) {
            if (testStage == 0) {
                pointerX = 84.0f * width / renderWidth; pointerY = top + 498.0f * width / renderWidth; mouse(kWKEventMouseMove); click(); testStage = 1; stageTime = SDL_GetTicks();
            } else if (testStage == 1 && SDL_GetTicks() - stageTime > 700) {
                click(); testStage = 2; stageTime = SDL_GetTicks();
            } else if (testStage == 2 && SDL_GetTicks() - stageTime > 500) {
                pointerX = 100.0f * width / renderWidth; pointerY = top + 30.0f * width / renderWidth; mouse(kWKEventMouseMove); click(); testStage = 3; stageTime = SDL_GetTicks();
            } else if (testStage == 3 && SDL_GetTicks() - stageTime > (mediaEnduranceTest ? (mediaThirtyMinuteTest ? 1830000u : 600000u) : mediaMatrixTest ? 12000u : (longMediaTest ? (pipelineTraceTest ? 68000u : 22000u) : 1800u))) {
                log(pageFullscreen && renderPageHeight == renderHeight ? "MEDIA FULLSCREEN PASS: shell hidden; page occupies full display" : "MEDIA FULLSCREEN FAIL: shell did not enter fullscreen");
                omniPaintPage(renderPageHeight); // OMNI_FAST_PAGE_V1
                draw();
                omniWritePng("/data/omni/video-fullscreen.png", static_cast<unsigned char*>(canvas->pixels), renderWidth, renderHeight, canvas->pitch);
                button(SDL_CONTROLLER_BUTTON_B); testStage = 4; stageTime = SDL_GetTicks();
            } else if (testStage == 4 && SDL_GetTicks() - stageTime > 600) {
                log(!pageFullscreen && renderPageHeight == physical(pageHeight) ? "MEDIA FULLSCREEN EXIT PASS: controller restores browser" : "MEDIA FULLSCREEN EXIT FAIL");
                if (mediaMatrixTest && ++mediaMatrixCycles < 4) {
                    fprintf(stderr, "browser: MEDIA MATRIX completed cycle=%u\n", mediaMatrixCycles);
                    testStage = 2; stageTime = SDL_GetTicks();
                } else {
                    if (mediaMatrixTest) fprintf(stderr, "browser: MEDIA MATRIX completed cycle=%u\n", mediaMatrixCycles);
                    testStage = 5;
                }
            }
        }
        if (SDL_GetTicks() - stageTime > (mediaEnduranceTest ? (mediaThirtyMinuteTest ? 1890000u : 650000u) : (longMediaTest ? (pipelineTraceTest ? 110000u : 65000u) : 45000u))) { log("FEATURE TEST FAIL: timeout"); running = false; }
        else if ((!pipelineTraceTest || testStage >= 5) && !active()->loading && SDL_GetTicks() - (stagedMediaTest ? stageTime : active()->loadedAt) > (stagedMediaTest ? (longMediaTest ? (pipelineTraceTest ? 2000u : 55000u) : 30000u) : 12000u) && !googleProbePending) {
            googleProbePending = true;
            auto script = adoptWK(WKStringCreateWithUTF8CString(stagedMediaTest
                ? "JSON.stringify({results:window.omniFeatureResults||[],isolation:window.omniMediaIsolation?window.omniMediaIsolation.snapshot():null})"
                : "JSON.stringify(window.omniFeatureResults || {error:'No test results'})"));
            WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), nullptr, [](WKTypeRef result, WKErrorRef error, void*) {
                log(!error && result && WKGetTypeID(result) == WKStringGetTypeID() ? OmniTest::toStd(static_cast<WKStringRef>(result)).c_str() : "FEATURE TEST FAIL: inspection failed");
                running = false;
            });
        }
    } else if (grabberTest && active()) { // OMNI_NET_GRABBER_TEST_V1
        if (SDL_GetTicks() - stageTime > 60000) { log("GRABBER TEST FAIL: timeout"); log("GRABBER TEST DONE"); running = false; }
        else if (!active()->loading && active()->loadedAt && SDL_GetTicks() - active()->loadedAt > 15000) omniGrabberTestRun();
    } else if (widgetTest && active()) {
        if (SDL_GetTicks() - stageTime > 45000) { log("WIDGET TEST: timeout"); running = false; }
        else if (!active()->loading && !googleProbePending && SDL_GetTicks() - active()->loadedAt > 15000) {
            googleProbePending = true;
            auto script = adoptWK(WKStringCreateWithUTF8CString("JSON.stringify({ready:document.readyState,api:typeof grecaptcha,errors:window.omniWidgetErrors,frames:Array.from(document.querySelectorAll('iframe')).map(f=>({src:f.src.split('?')[0],width:f.offsetWidth,height:f.offsetHeight})),scripts:Array.from(document.scripts).map(s=>s.src.split('?')[0]).filter(Boolean),text:document.body.innerText.slice(0,300),cookieEnabled:navigator.cookieEnabled})"));
            WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), nullptr, [](WKTypeRef result, WKErrorRef error, void*) {
                log(!error && result && WKGetTypeID(result) == WKStringGetTypeID() ? OmniTest::toStd(static_cast<WKStringRef>(result)).c_str() : "widget inspection failed");
                omniWritePng("/data/omni/widget-test.png", static_cast<unsigned char*>(canvas->pixels), renderWidth, renderHeight, canvas->pitch);
                running = false;
            });
        }
    } else if (ipcPressureTest && active()) {
        if (SDL_GetTicks() - stageTime > 45000) { log("IPC PRESSURE FAIL: timeout"); running = false; }
        else if (!active()->loading && active()->message.empty()) {
            if (!testStage || ipcReplies == 128) {
                if (testStage && ipcErrors) { log("IPC PRESSURE FAIL: reply mismatch"); running = false; }
                else if (testStage == 3) { log("IPC PRESSURE PASS: 384 large round trips preserved all replies"); running = false; }
                else {
                    ++testStage; ipcReplies = 0;
                    for (unsigned i = 0; i < 128; ++i) {
                        auto expected = std::make_unique<std::string>(std::to_string(testStage) + ":" + std::to_string(i) + ":" + std::string(8192, 'a' + i % 26));
                        auto script = adoptWK(WKStringCreateWithUTF8CString(("'" + *expected + "'").c_str()));
                        WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), expected.release(), [](WKTypeRef result, WKErrorRef error, void* opaque) {
                            std::unique_ptr<std::string> expected(static_cast<std::string*>(opaque));
                            if (error || !result || WKGetTypeID(result) != WKStringGetTypeID()
                                || OmniTest::toStd(static_cast<WKStringRef>(result)) != *expected) ++ipcErrors;
                            ++ipcReplies;
                        });
                    }
                }
            }
        }
    } else if (youtubeTest && active()) {
        if (!testStage && !active()->loading && SDL_GetTicks() - stageTime > 3000) {
            log("YOUTUBE PAGE TEST: navigating from loaded start page");
            navigate("https://www.youtube.com/"); testStage = 1; stageTime = SDL_GetTicks();
        }
        if (SDL_GetTicks() - stageTime > 45000) { log("YOUTUBE PAGE TEST: timeout"); running = false; }
        else if (testStage && !active()->loading && !googleProbePending && SDL_GetTicks() - stageTime > 20000) {
            googleProbePending = true;
            auto script = adoptWK(WKStringCreateWithUTF8CString("JSON.stringify({host:location.hostname,ready:document.readyState,title:document.title.slice(0,100),youtube:!!document.querySelector('ytd-app,ytm-app'),mediaSource:typeof MediaSource,text:document.body?document.body.innerText.slice(0,250):''})"));
            WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), nullptr, [](WKTypeRef result, WKErrorRef error, void*) {
                log(!error && result && WKGetTypeID(result) == WKStringGetTypeID() ? OmniTest::toStd(static_cast<WKStringRef>(result)).c_str() : "YOUTUBE PAGE TEST: inspection failed");
                omniWritePng("/data/omni/youtube-page-test.png", static_cast<unsigned char*>(canvas->pixels), renderWidth, renderHeight, canvas->pitch);
                running = false;
            });
        }
    } else if (googleTest && active()) {
        if (SDL_GetTicks() - stageTime > 45000) { log("GOOGLE TEST FAIL: timeout"); running = false; }
        else if (!active()->loading && !googleProbePending && SDL_GetTicks() - active()->loadedAt > 15000) {
            googleProbePending = true;
            auto script = adoptWK(WKStringCreateWithUTF8CString("JSON.stringify({unsupported:/browser isn.t supported|Update your browser/i.test(document.body.innerText),results:!!document.querySelector('#search')||Array.from(document.links).some(a=>/^https?:\\/\\/(www\\.)?webkit\\.org/.test(a.href)),title:document.title.slice(0,100),text:document.body.innerText.slice(0,350)})"));
            WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), nullptr, [](WKTypeRef result, WKErrorRef error, void*) {
                auto value = !error && result && WKGetTypeID(result) == WKStringGetTypeID() ? OmniTest::toStd(static_cast<WKStringRef>(result)) : "error";
                log(value.c_str());
                log(value.find("\"unsupported\":false,\"results\":true") != std::string::npos ? "GOOGLE TEST PASS: search results rendered" : "GOOGLE TEST FAIL: search results not verified");
                running = false;
            });
        }
    } else if (gamepadTest && active()) { // OMNI_GAMEPAD_TEST_V1: a virtual pad through the libwpe provider -> navigator.getGamepads()
        if (SDL_GetTicks() - stageTime > 40000) { log("GAMEPAD TEST FAIL: timeout"); omniGpTestPad(false); running = false; }
        else if (!active()->loading && !inputProbePending && active()->loadedAt && SDL_GetTicks() - active()->loadedAt > 2500) {
            if (testStage == 0) { omniGpTestPad(true); testStage = 1; stageTime = SDL_GetTicks(); }
            else if (testStage == 1 && SDL_GetTicks() - stageTime > 1200) { omniGpTestPress(true); testStage = 2; stageTime = SDL_GetTicks(); }
            else if (testStage == 2 && SDL_GetTicks() - stageTime > 400) { omniGpTestPress(false); testStage = 3; stageTime = SDL_GetTicks(); }
            else if (testStage == 3 && SDL_GetTicks() - stageTime > 1500) {
                inputProbePending = true;
                auto script = adoptWK(WKStringCreateWithUTF8CString("JSON.stringify(window.omniGamepadResults||{error:'no results'})"));
                WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), nullptr, [](WKTypeRef result, WKErrorRef error, void*) {
                    const auto value = !error && result && WKGetTypeID(result) == WKStringGetTypeID() ? OmniTest::toStd(static_cast<WKStringRef>(result)) : std::string("error");
                    log(value.c_str());
                    log(value.find("\"pass\":true") != std::string::npos ? "GAMEPAD TEST PASS: navigator.getGamepads() sees the pad, a button press and a stick" : "GAMEPAD TEST FAIL");
                    omniGpTestPad(false); running = false;
                });
            }
        }
    } else if (padCtlTest && active()) { // OMNI_PAD_CONTROLLER_TEST_V1: the Master Control page through window.omniPadController
        if (SDL_GetTicks() - stageTime > 40000) { log("PADCTL TEST FAIL: timeout"); running = false; }
        else if (!active()->loading && !inputProbePending && active()->loadedAt && SDL_GetTicks() - active()->loadedAt > 3000) {
            static const char* probe = "JSON.stringify({url:location.href,api:typeof window.omniPadController,kbd:document.body.classList.contains('kbd'),focus:(document.activeElement&&(document.activeElement.id||document.activeElement.className||document.activeElement.tagName))||null,fin:(document.querySelector('.fin.on,.fin.active,.fin[aria-current],.fin[aria-selected=true]')||{}).textContent||null})";
            if (testStage == 0 || testStage == 2 || testStage == 4) {
                inputProbePending = true;
                auto script = adoptWK(WKStringCreateWithUTF8CString(probe));
                WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), nullptr, [](WKTypeRef result, WKErrorRef error, void*) {
                    const auto value = !error && result && WKGetTypeID(result) == WKStringGetTypeID() ? OmniTest::toStd(static_cast<WKStringRef>(result)) : std::string("error");
                    fprintf(stderr, "browser: PADCTL stage %d %s\n", testStage, value.c_str());
                    if (testStage == 4) {
                        log(value.find("\"api\":\"function\"") != std::string::npos && value.find("\"kbd\":true") != std::string::npos ? "PADCTL TEST PASS: Master Control page takes D-pad/R1/Cross through omniPadController" : "PADCTL TEST FAIL");
                        running = false;
                    }
                    inputProbePending = false; ++testStage; stageTime = SDL_GetTicks();
                });
            } else if (testStage == 1 && SDL_GetTicks() - stageTime > 300) {
                fprintf(stderr, "browser: PADCTL R1 routed=%d\n", omniMcButton(SDL_CONTROLLER_BUTTON_RIGHTSHOULDER) ? 1 : 0);
                testStage = 2; stageTime = SDL_GetTicks();
            } else if (testStage == 3 && SDL_GetTicks() - stageTime > 300) {
                button(SDL_CONTROLLER_BUTTON_DPAD_DOWN);
                fprintf(stderr, "browser: PADCTL D-pad down sent through button()\n");
                testStage = 4; stageTime = SDL_GetTicks();
            } else if (testStage == 4) { /* probe above */ }
        }
    } else if (inputTest && active()) {
        if (SDL_GetTicks() - stageTime > 30000) { log("INPUT TEST FAIL: timeout"); running = false; }
        else if (!active()->loading && !inputProbePending && SDL_GetTicks() - stageTime > 1200) {
            if (testStage == 0) {
                pointerX = 300; pointerY = top + 50; click();
                testStage = 1; stageTime = SDL_GetTicks();
            } else if (testStage == 1 && editing && pageEditing) {
                draw();
                omniWritePng("/data/omni/keyboard-preview.png", static_cast<unsigned char*>(canvas->pixels), renderWidth, renderHeight, canvas->pitch);
                append("omni testx"); eraseCharacter(); append(" query");
                testStage = 2; stageTime = SDL_GetTicks();
            } else if (testStage == 2) {
                submitKeyboard(); testStage = 3; stageTime = SDL_GetTicks();
            } else if (testStage == 3) {
                inputProbePending = true;
                auto script = adoptWK(WKStringCreateWithUTF8CString("JSON.stringify({value:document.querySelector('#q').value,submitted:window.submitted,events:window.inputEvents>0})"));
                WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), nullptr, [](WKTypeRef result, WKErrorRef error, void*) {
                    auto value = !error && result && WKGetTypeID(result) == WKStringGetTypeID() ? OmniTest::toStd(static_cast<WKStringRef>(result)) : "error";
                    log(value.c_str());
                    log(value == "{\"value\":\"omni test query\",\"submitted\":\"omni test query\",\"events\":true}" ? "INPUT TEST PASS: click opens keyboard; insertion, deletion, input events and form submit work" : "INPUT TEST FAIL: unexpected field or submission");
                    running = false;
                });
            }
        }
    } else if (blockerTest && active()) {
        if (SDL_GetTicks() - stageTime > 45000) { log("BLOCK TEST FAIL: stage timeout"); running = false; }
        else if (!active()->loading && !blockerProbePending && SDL_GetTicks() - active()->loadedAt > 1200) {
            blockerProbePending = true;
            auto script = adoptWK(WKStringCreateWithUTF8CString("[window.omniAllowed===true,window.omniBlocked===true,window.omniBlockedError===true].join(',')"));
            WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), nullptr, [](WKTypeRef result, WKErrorRef error, void*) {
                std::string value = !error && result && WKGetTypeID(result) == WKStringGetTypeID() ? OmniTest::toStd(static_cast<WKStringRef>(result)) : "error";
                const char* expected = testStage == 0 || testStage == 3 ? "true,true,false" : "true,false,true";
                fprintf(stderr, "browser: BLOCK TEST stage=%d actual=%s expected=%s\n", testStage, value.c_str(), expected);
                fflush(stderr);
                if (value != expected) { log("BLOCK TEST FAIL: unexpected script execution"); running = false; }
                else if (testStage == 0) {
                    omniBlockerSetEnabled(true); testStage = 1; navigate(blockerTestURL);
                } else if (testStage == 1) {
                    newTab(); testStage = 2; navigate(blockerTestURL);
                } else if (testStage == 2) {
                    omniBlockerSetEnabled(false); testStage = 3; navigate(blockerTestURL);
                } else { log("BLOCK TEST PASS: baseline loads both scripts; enabled blocks matching script only; new tab inherits blocking; disabling restores requests"); running = false; }
                stageTime = SDL_GetTicks(); blockerProbePending = false;
            });
        }
    } else if (selfTest && active()) {
        if (SDL_GetTicks() - stageTime > 45000) { log("TAB TEST FAIL: stage timeout"); running = false; }
        else if (!active()->loading && SDL_GetTicks() - active()->loadedAt >= 1800) {
            if (testStage == 0 && active()->title == "Example Domain") {
                log("TAB TEST: first page loaded"); newTab(); navigate("https://en.wikipedia.org/wiki/PlayStation_5");
                testStage = 1; stageTime = SDL_GetTicks();
            } else if (testStage == 1 && active()->title.find("PlayStation 5") != std::string::npos) {
                log("TAB TEST: two independent pages loaded");
                omniPaintPage(renderPageHeight); // OMNI_FAST_PAGE_V1
                draw();
                omniWritePng("/data/omni/tabs-preview.png", static_cast<unsigned char*>(canvas->pixels), width, height, canvas->pitch);
                activate(0);
                if (active()->title != "Example Domain") { log("TAB TEST FAIL: switch lost page"); running = false; }
                else { navigate("https://news.ycombinator.com/"); testStage = 2; stageTime = SDL_GetTicks(); }
            } else if (testStage == 2 && active()->title == "Hacker News") {
                if (!WKPageCanGoBack(active()->page)) { log("TAB TEST FAIL: history missing"); running = false; }
                else { active()->loading = true; WKPageGoBack(active()->page); testStage = 3; stageTime = SDL_GetTicks(); }
            } else if (testStage == 3 && active()->title == "Example Domain") {
                if (tabs.size() != 2 || tabs[1]->title.find("PlayStation 5") == std::string::npos) { log("TAB TEST FAIL: history crossed tabs"); running = false; }
                else { activate(1); closeTab(); testStage = 4; stageTime = SDL_GetTicks(); }
            } else if (testStage == 4) {
                if (tabs.size() == 1 && active()->title == "Example Domain") {
                    log("TAB TEST PASS: create, switch, independent history, back, close");
                    newTab(); navigate("https://expired.badssl.com/");
                    testStage = 5; stageTime = SDL_GetTicks();
                } else { log("TAB TEST FAIL: closing tab changed survivor"); running = false; }
            } else if (testStage == 5) {
                if (active()->message != "HTTPS certificate verification failed. Connection blocked.") {
                    log("ERROR RECOVERY TEST FAIL: certificate error not shown"); running = false;
                } else {
                    draw();
                    omniWritePng("/data/omni/error-preview.png", static_cast<unsigned char*>(canvas->pixels), width, height, canvas->pitch);
                    activate(0);
                    if (!active()->message.empty()) { log("ERROR RECOVERY TEST FAIL: error crossed tabs"); running = false; }
                    else {
                        activate(1); navigate("https://example.com/");
                        testStage = 6; stageTime = SDL_GetTicks();
                    }
                }
            } else if (testStage == 6) {
                if (active()->title == "Example Domain" && active()->message.empty())
                    log("ERROR RECOVERY TEST PASS: invalid certificate blocked, error isolated to tab, valid navigation clears error");
                else {
                    fprintf(stderr, "browser: ERROR RECOVERY TEST FAIL: title=%s message=%s\n", active()->title.c_str(), active()->message.c_str());
                    fflush(stderr);
                }
                running = false;
            }
        }
    }
    OmniMedia::Hw::holePunchShellPhase(3); // OMNI_HOLEPUNCH_V7_STALLTRACE: input
    omniGamepadTick(active(), settingsOpen || editing || omniOverlayOpen(), omniShoulderFocused); // OMNI_GAMEPAD_V1
    SDL_Event event;
    while (SDL_PollEvent(&event)) {
        // OMNI_PERF_A_COUNTER: stick motion by itself changes nothing drawn (the stick tick moves the pointer, WebKit reports scrolling)
        // dl2-candidate-55: so do the raw joystick events SDL posts next to every game-controller event (SDL_JOYAXISMOTION with
        // every stick change: they were `input`, which S4 does not know, so no draw was ever regional), sensor updates and
        // touchpad motion (handled nowhere in the shell).
        const bool omniInvisibleEvent = (event.type == SDL_CONTROLLERAXISMOTION && event.caxis.axis != SDL_CONTROLLER_AXIS_TRIGGERLEFT
            && event.caxis.axis != SDL_CONTROLLER_AXIS_TRIGGERRIGHT) || event.type == SDL_JOYAXISMOTION || event.type == SDL_JOYBALLMOTION
            || event.type == SDL_JOYHATMOTION || event.type == SDL_JOYBUTTONDOWN || event.type == SDL_JOYBUTTONUP
            || event.type == SDL_JOYBATTERYUPDATED || event.type == SDL_CONTROLLERSENSORUPDATE || event.type == SDL_SENSORUPDATE
            || event.type == SDL_CONTROLLERTOUCHPADMOTION;
        omniDirtyPhase = omniInvisibleEvent ? omniDrAxis : omniDrInput;
        if (!omniStickQuietEvent(event)) omniShellDirty = true; // OMNI_SHELL_DRAW_V1; OMNI_STICK_DEADZONE_V1: a stick inside its dead zone asks for nothing
        omniChromeEvent(event); // OMNI_STYLE_V1
        if (event.type != SDL_CONTROLLERDEVICEADDED) omniGamepadEvent(event); // OMNI_GAMEPAD_V1 (added: after the pad is open)
        if (event.type == SDL_QUIT) running = false;
        else if (event.type == SDL_APP_WILLENTERBACKGROUND || event.type == SDL_APP_DIDENTERBACKGROUND) {
            omniShoulderFocused = false; omniShoulderReset();
        } else if (event.type == SDL_APP_DIDENTERFOREGROUND) {
            omniShoulderFocused = true; omniShoulderReset();
        } else if (event.type == SDL_WINDOWEVENT && (event.window.event == SDL_WINDOWEVENT_FOCUS_LOST || event.window.event == SDL_WINDOWEVENT_FOCUS_GAINED)) {
            omniShoulderFocused = event.window.event == SDL_WINDOWEVENT_FOCUS_GAINED; omniShoulderReset();
        } else if (event.type == SDL_CONTROLLERDEVICEADDED) { omniOpenPad(event.cdevice.which); omniShoulderReset(); omniGamepadEvent(event); }
        else if (event.type == SDL_CONTROLLERDEVICEREMOVED) { omniClosePad(event.cdevice.which); omniShoulderReset(); }
        else if (event.type == SDL_CONTROLLERAXISMOTION) {
            if (omniStickAxisLive(event.caxis)) { // OMNI_STICK_DEADZONE_V1: was |value| > 7000 (= Medium): a drifting pad no longer takes over
                auto* previous = controller; omniActivatePad(event.caxis.which);
                if (previous != controller) omniShoulderReset();
            }
            if (event.caxis.axis == SDL_CONTROLLER_AXIS_TRIGGERLEFT || event.caxis.axis == SDL_CONTROLLER_AXIS_TRIGGERRIGHT)
                omniSavedAxis(event.caxis);
        } else if (event.type == SDL_CONTROLLERBUTTONDOWN || event.type == SDL_CONTROLLERBUTTONUP) { if (!omniFxButtonEvent(event.cbutton)) omniShoulderButton(event.cbutton); } // OMNI_FEATURES_V1: hold Cross
        else if (event.type == SDL_MOUSEMOTION) { pointerX = event.motion.x * float(width) / screen->w; pointerY = event.motion.y * float(height) / screen->h; mouse(kWKEventMouseMove); }
        else if (event.type == SDL_MOUSEBUTTONDOWN && event.button.button == SDL_BUTTON_LEFT) click();
        else if (event.type == SDL_MOUSEWHEEL) scroll(event.wheel.y * 80);
        else if (event.type == SDL_TEXTINPUT && active()) {
            if (editing) append(event.text.text);
            else WKPageHandleKeyboardEvent(active()->page, WKKeyboardEventMake(kWKEventKeyDown, kWKInputTypeNormal,
                event.text.text, strlen(event.text.text), "", 0, 0, 0, 0));
        } else if (event.type == SDL_KEYDOWN && active()) {
            auto key = event.key.keysym.sym;
            if (key == SDLK_F8) { omniStatsSet(!omniStatsPanel.enabled); continue; }
            if (editing) {
                if (key == SDLK_RETURN) submitKeyboard();
                else if (key == SDLK_BACKSPACE) eraseCharacter();
                else if (key == SDLK_ESCAPE) dismissKeyboard();
                else omniKbKey(key, event.key.keysym.mod); // OMNI_KEYBOARD_V2
            } else if (key == SDLK_ESCAPE) { if (pageFullscreen) WKViewRequestExitFullScreen(active()->view.get()); else omniFxQuickMenuShow(); } // OMNI_FEATURES_V1: Esc no longer quits
            else if (key == SDLK_F6 || (key == SDLK_l && (event.key.keysym.mod & KMOD_CTRL))) editAddress();
            else {
                const char* id = key == SDLK_RETURN ? "Enter" : key == SDLK_BACKSPACE ? "U+0008" : key == SDLK_TAB ? "U+0009" : "";
                int vk = key == SDLK_RETURN ? 0xff0d : key == SDLK_BACKSPACE ? 0xff08 : key == SDLK_TAB ? 0xff09 : 0;
                if (vk) WKPageHandleKeyboardEvent(active()->page, WKKeyboardEventMake(kWKEventKeyDown, kWKInputTypeNormal, "", 0, id, vk, 0, 0, 0));
            }
        }
        omniShoulderChord.contextChanged(omniShoulderContext());
        omniSavedTriggers.contextChanged(omniSavedContext());
    }
    omniDirtyPhase = omniDrInput; // OMNI_PERF_A_COUNTER
    // SDL's sampled state may include later queued edges: reconcile only after drain.
    omniShoulderChord.reconcile(omniShoulderContext(), omniShoulderPhysical());
    omniSavedReconcile();
    if (!running) {
        for (auto& tab : tabs) WKPageClose(tab->page);
        omniLinkReviewCancel(); // Ignore any late result while running=false.
        OmniMedia::Audio::relayStop(); // OMNI_AUDIO_RELAY_V1: audio device closed before SDL_Quit
        omniEverydayShutdown(); // OMNI_EVERYDAY_V1: last session save, flush queued writes
        omniStopPresenter(); // OMNI_SHELL_PRESENT_V1: never quit SDL during a flip
        OmniMedia::Hw::diagnosticTraceDump();
        if(omniStatsSurface) { SDL_FreeSurface(omniStatsSurface); omniStatsSurface=nullptr; }
        omniCaptureFinish(); // OMNI_STALL_FIX1: a background preview write finishes before exit
        log("shutdown: closing SDL");
        SDL_Quit();
        log("shutdown: SDL closed");
#ifdef __PROSPERO__
        // Off-screen selects SDL's dummy video driver, not a different process
        // lifecycle. RC5 proved SDL and service cleanup return, then _exit hangs.
        // Match SDL's PS5 main wrapper for BOTH video drivers. OmniMain's wrapper
        // releases the service/queue before this existing platform exit call.
        log("shutdown: requesting platform app exit");
        const int exitResult = sceSystemServiceLoadExec("exit", nullptr);
        fprintf(stderr, "shutdown: platform app exit returned=%#x\n", exitResult); fflush(stderr);
#endif
        log("shutdown: fallback _exit");
        _exit(0);
    }
    // Discrete keyboard movement with a dead zone and delayed repeat.
    static int heldDirection = -1;
    static uint32_t nextKeyMove = 0;
    if (controller && editing) {
        int x = SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_LEFTX);
        int y = SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_LEFTY);
        int direction = -1;
        if (std::max(abs(x), abs(y)) > omniStickGate(false, 14000.f / 32768) * 32768) // OMNI_STICK_DEADZONE_V1: 14000 at Medium
            direction = abs(x) > abs(y)
                ? (x > 0 ? SDL_CONTROLLER_BUTTON_DPAD_RIGHT : SDL_CONTROLLER_BUTTON_DPAD_LEFT)
                : (y > 0 ? SDL_CONTROLLER_BUTTON_DPAD_DOWN : SDL_CONTROLLER_BUTTON_DPAD_UP);
        uint32_t now = SDL_GetTicks();
        if (direction != -1 && (direction != heldDirection || static_cast<int32_t>(now - nextKeyMove) >= 0)) {
            button(direction);
            nextKeyMove = now + (direction != heldDirection ? 350 : 130);
        }
        heldDirection = direction;
    } else heldDirection = -1;
    omniKbTick(); // OMNI_KEYBOARD_V2: repeat, triggers, right stick
    if (controller && !editing) {
        omniDirtyPhase = omniDrStick; // OMNI_PERF_A_COUNTER: pointer motion (OMNI_PERF_A_S4 redraws its rows), right-stick scrolling
        const float omniPx = pointerX, omniPy = pointerY;
        const bool omniDirtyBefore = omniShellDirty.on;
        const unsigned omniReasonsBefore = omniDrawReasons;
        omniFxStickTick(); // OMNI_FEATURES_V1: acceleration, link snapping, right stick both axes (was 16 px per pass)
        // dl2-candidate-55: the stick tick's own redraw is for the pointer; a pointer that did not move (stick held against a
        // screen edge) needs none. A scrolled menu or dialog (its own redraw) keeps it.
        if (omniPerfOn(omniPerfS3) && pointerX == omniPx && pointerY == omniPy && !omniOverlayOpen() && !omniModalCurrent()) {
            const unsigned added = omniDrawReasons & ~omniReasonsBefore & ~unsigned(omniDrStick);
            omniDrawReasons = omniReasonsBefore | added;
            omniShellDirty.on = omniDirtyBefore || added;
        }
        omniDirtyPhase = omniDrInput;
    }
    OmniMedia::Hw::holePunchShellPhase(1); // OMNI_HOLEPUNCH_V7_STALLTRACE: input done
    omniDirtyPhase = omniDrStyle; // OMNI_PERF_A_COUNTER
    omniStyleTick(); // OMNI_STYLE_V1: bar slide, progress bar, toast fades
    omniDirtyPhase = omniDrFeature;
    const auto paintStarted = SDL_GetPerformanceCounter();
    // The refresh timer already limits this to 30 Hz. A second 33 ms gate
    // measured after synchronous painting skips the next timer tick whenever
    // painting takes time, cutting video presentation toward 15 Hz.
    // OMNI_SHELL_DRAW_V1: copy the page only when WebKit reported new pixels, another tab
    // is shown, or every 500 ms (safety net); present only when something changed, or
    // every 100 ms so status text and loading states stay current.
    const uint32_t omniNow = SDL_GetTicks();
    omniStatsTick(omniNow); // reuse existing loop time, at most once/second
    bool omniPageCopied = false;
    // OMNI_PERF_A_S1: WKPagePaint waits up to 500 ms for a backing store the web process has not produced yet (a busy, loading
    // page; a tab shown again after its store was discarded), and the 500 ms safety net called it again and again. Now: a page
    // that is loading is painted when it reports new pixels (a tab switch or a shell cause waits for that, at most 2 s); no
    // safety-net paint while it loads; after a paint that blocked, none on that tab for 0.5-2 s; the safety net (every 2 s,
    // idle pages only) draws only when the page really changed.
    Tab* const omniTab = active();
    const bool omniS1 = omniPerfOn(omniPerfS1);
    const bool omniSlow = omniS1 && omniTab && !firstFrame && int32_t(omniNow - omniTab->omniSlowUntil) < 0;
    // ws-a-1b: a safety-net paint on a page that has just loaded blocked 179/754 ms (its backing store was being replaced): the net
    // runs every 10 s (reports cover every update; `safety N changed N` in the counter says whether it is needed at all).
    // OMNI_C56_VIDEOFIX1: while a video uses the plane WebKit reports little or nothing (fullscreen HDR: no report in 10 minutes),
    // and 54's 500 ms full paint was what brought the page's changes in (the fullscreen media-control bar fading out). With the
    // 10 s net the faded bar stayed in the canvas for the whole run (c55-hdrauto-1: `PQ refused for a translucent area` ~298 per
    // window, 8-bit copies made, re-flips 7.5 ms instead of 2.2 ms: 429 dropped). 500 ms again while the plane is in use; while
    // the presenter owns a fullscreen video the paint draws only if the page really changed (half-size page compared), so the
    // fullscreen draw rate stays low.
    const bool omniVideoFix = omniVideoFixOn() && OmniMedia::Hw::holePunchActive();
    const bool omniVideoOwned = omniVideoFix && pageFullscreen && omniPresenterOwnsVideo();
    if (omniVideoFix) { static bool noted = false; if (!noted) { noted = true; log("video fix (OMNI_C56_VIDEOFIX1): page paint every 500 ms and the shell refresh while a video uses the plane"); } }
    const uint32_t omniSafetyMs = omniS1 && !omniVideoFix ? 10000 : 500;
    if (omniVideoFix2On() && pageFullscreen && OmniMedia::Hw::holePunchActive() && active() && !active()->crashed && !omniOverlayOpen() && !settingsOpen) { // OMNI_C56_VIDEOFIX2
        if (!omniFix2.lastSent) omniFix2.lastSent = omniNow;
        if (!omniFix2.parked && omniNow - omniFix2.lastSent >= 3000) {
            omniFix2.parked = true; ++omniFix2.parks;
            WKPageHandleMouseEvent(active()->page, WKMouseEventMake(kWKEventMouseMove, kWKEventMouseButtonLeftButton,
                WKPointMake(width / 2.0 * displayScale * omniPageScale, (height / 2.0 - omniPageTop()) * displayScale * omniPageScale), 0, 0));
        }
        static uint32_t since = 0; static unsigned lines = 0;
        if (!since) since = omniNow;
        if (omniNow - since >= 5000) {
            since = omniNow;
            if (lines < 200) {
                ++lines;
                char line[200];
                snprintf(line, sizeof line, "video fix 2 (5 s): mouse sent %u, same-position dropped %u, parked %u, pointer %.0f,%.0f%s",
                    omniFix2.sent, omniFix2.dropped, omniFix2.parks, pointerX, pointerY, omniFix2.parked ? " (page mouse parked)" : "");
                log(line);
            }
            omniFix2.sent = omniFix2.dropped = omniFix2.parks = 0;
        }
    } else omniFix2.lastSent = 0;
    const bool omniReported = omniViewDirty.any;
    // OMNI_DIRTY_PAINT_V1: only WebKit's reported rect changed (same tab, safety-net time not due): repaint just that.
    if (active() && !active()->crashed && omniViewDirty.any && !omniPageDirty && active() == omniLastActive
        && omniNow - omniLastPageCopy < omniSafetyMs && !firstFrame && !omniSlow) {
        const Uint64 t0 = SDL_GetPerformanceCounter();
        OmniMedia::Hw::holePunchShellPhase(4);
        const int partial = omniPaintPagePartial(omniPaintRows(), omniViewDirty);
        OmniMedia::Hw::holePunchShellPhase(1);
        if (partial < 0) omniPageDirty = true;   // the full path below
        else {
            omniViewDirty = OmniViewDirty();
            omniSplit.paint += omniMsSince(t0); ++omniSplit.paints; ++omniSplit.partial;
            if (partial == 0) ++omniSplit.unchanged; else { omniPageCopied = true; omniDrawReasons |= omniDrPagePartial; }
        }
    }
    if (omniViewDirty.any && !omniPageCopied) omniPageDirty = omniPageDirty || omniViewDirty.any;
    const bool omniMustPaint = omniPageDirty || active() != omniLastActive || firstFrame;
    const bool omniSafetyOnly = !omniMustPaint && omniNow - omniLastPageCopy >= omniSafetyMs;
    bool omniPaintNow = active() && !active()->crashed && (omniMustPaint || omniSafetyOnly);
    if (omniPaintNow && omniS1 && !firstFrame) { // OMNI_PERF_A_S1
        Tab& t = *omniTab;
        // a loading page, or one without a report since it was shown, gets no safety-net paint (it reports its own changes)
        if (omniSafetyOnly) omniPaintNow = !omniSlow && !t.loading && t.omniShownReported;
        else {
            // Paint when WebKit has reported pixels since the tab was shown (its backing store exists then) and, while it loads,
            // with a report this tick. Watchdog: a page that never reports is painted anyway: after 300 ms for a tab that had a
            // backing store before, 2 s for a new one, then 4 s and 8 s between tries (a try that blocks also arms the backoff).
            bool wait = omniSlow || !t.omniShownReported || (!omniReported && t.loading);
            if (wait && !omniSlow) {
                if (!t.omniWaitSince) t.omniWaitSince = omniNow;
                const uint32_t limit = t.omniNoReportTries ? std::min<uint32_t>(2000u << std::min<uint32_t>(t.omniNoReportTries, 2u), 8000u)
                                                           : (t.omniEverReported ? 300u : 2000u);
                if (omniNow - t.omniWaitSince >= limit) { wait = false; if (!t.omniShownReported) ++t.omniNoReportTries; ++omniCensus.watchdog; }
            }
            if (wait) { ++omniCensus.deferred; omniPaintNow = false; }
            else t.omniWaitSince = 0;
        }
    }
    // the safety net on an idle page: draw only when the page really changed (OMNI_PERF_A_S1)
    const bool omniCompare = omniPaintNow && omniS1 && omniSafetyOnly && omniPageScale < 1 && (!OmniMedia::Hw::holePunchActive() || omniVideoOwned) // OMNI_C56_VIDEOFIX1
        && omniPageSmall.size() == size_t((renderWidth + 1) / 2) * ((renderPageHeight + 1) / 2);
    static std::vector<uint32_t> omniSafetyBefore;
    if (omniCompare) omniSafetyBefore.assign(omniPageSmall.begin(), omniPageSmall.end());
    if (omniPaintNow) {
        omniViewDirty = OmniViewDirty();
        omniPageDirty = false;
        omniLastActive = active();
        omniLastPageCopy = omniNow;
        omniPageCopied = true;
        if (firstFrame) log("first frame: painting page");
        // OMNI_HOLEPUNCH_V1: WKPagePaint draws the page over the buffer (SrcOver). While a video
        // is shown under the page, start from transparent so the page's hole stays a hole.
        if (OmniMedia::Hw::holePunchActive()) std::fill(pixels.begin(), pixels.end(), 0);
        OmniMedia::Hw::holePunchShellPhase(4); // OMNI_HOLEPUNCH_V7_STALLTRACE: page paint
        { const Uint64 t0 = SDL_GetPerformanceCounter(); omniPaintPage(omniPaintRows()); omniSplit.paint += omniMsSince(t0); ++omniSplit.paints; } // OMNI_STYLE_V1 OMNI_FAST_PAGE_V1 OMNI_SMOOTH_DRAW_V1
        OmniMedia::Hw::holePunchShellPhase(1);
        if (omniCompare) {
            ++omniCensus.safety;
            if (memcmp(omniSafetyBefore.data(), omniPageSmall.data(), omniSafetyBefore.size() * 4)) { ++omniCensus.safetyChanged; omniDrawReasons |= omniDrSafety; }
            else { omniPageCopied = false; omniPageDamage = OmniRows(); }   // nothing new: nothing to draw
        } else omniDrawReasons |= omniDrPageFull;
    }
    { const double f = double(SDL_GetPerformanceFrequency()); omniGap.paint = 1000.0 * double(SDL_GetPerformanceCounter() - paintStarted) / f; } // ws-a-1b: page paint time in the gap line also when nothing is drawn
    omniDirtyPhase = omniDrVideo; // OMNI_PERF_A_COUNTER
    if (OmniMedia::Hw::holePunchPoll()) omniShellDirty = true; // OMNI_HOLEPUNCH_V1: new video picture or rect
    omniDirtyPhase = omniDrFeature;
    // OMNI_PERF_A_S3: what the bars, toast and panels show changed: draw now (no flag needed); the rest waits for the refresh.
    if (omniPerfOn(omniPerfS3)) {
        static uint64_t shown = 0;
        const uint64_t now = omniShellSignature();
        if (now != shown) { if (shown) omniMarkDirty(omniDrSignature); shown = now; }
    }
    // OMNI_SMOOTH_DRAW_V2: the 100 ms refresh keeps status text and spinners current; a fullscreen video shows neither, and each
    // of those draws composed the whole 4K frame (12-60 ms of main-thread work): once a second there.
    // OMNI_PERF_A_S3: once a second everywhere (state changes draw at once through the signature; the spinner has its own 30 Hz).
    // OMNI_C56_VIDEOFIX1: omniLastDraw is also moved by ticks that draw nothing (stick noise: raw joystick events arrive several
    // times a second), so the 1 s refresh never came due and the only draws left with a video on the plane were the 2 s
    // watchdog. The video start-up hand-shake and OMNI_SKIP_COMPOSE ("a wrong skip costs at most the shell's own timer") rely on
    // that timer: c55-seq-1 "no picture presented for 1001 ms ... presents=2 shown=0", pacing off, 418 shown. While a video uses
    // the plane and the presenter does not own it (windowed, or fullscreen before the presenter takes it): 54's period (100 ms
    // windowed, 1 s fullscreen), timed from the last real draw.
    static uint32_t omniVideoFixLastDraw = 0;
    const bool omniVideoTimer = omniVideoFix && !omniVideoOwned;
    const uint32_t omniRefreshMs = omniVideoTimer ? (pageFullscreen ? 1000u : 100u)
        : ((pageFullscreen && OmniMedia::Hw::holePunchActive()) || omniPerfOn(omniPerfS3) ? 1000u : 100u);
    const bool omniRefreshDue = (omniVideoTimer ? omniNow - omniVideoFixLastDraw : omniNow - omniLastDraw) >= omniRefreshMs;
    if (!firstFrame && !omniPageCopied && !omniShellDirty && !omniRefreshDue) {
        if (omniCanvasPending) { omniPresentFrame(); ++omniCensus.reused; }   // OMNI_PERF_A_S7: the kept canvas, not a new draw
        else ++omniCensus.idle;
        return;
    }
    unsigned omniReasons = omniDrawReasons | (firstFrame ? omniDrFirst : 0u);
    if (!omniPageCopied && !firstFrame && (!omniShellDirty || (omniRefreshDue && omniPerfOn(omniPerfS3)))) omniReasons |= omniDrRefresh;   // dl2-candidate-55: also beside stick noise
    // dl2-candidate-55: only causes that change nothing drawn (stick noise, raw joystick events): no draw in any mode.
    const bool omniInvisibleOnly = omniPerfOn(omniPerfS3) && !firstFrame && omniReasons && !(omniReasons & ~unsigned(omniDrAxis));
    omniDrawReasons = 0;
    omniShellDirty = false;
    omniLastDraw = omniNow;
    omniShellLastDrawReasons = omniReasons;
    // OMNI_PERF_A_HOOK: only the video plane changed and the video service shows that picture by itself.
    // dl2-candidate-55: left unwired (nullptr). With ws-b-1's V2 the poll asks for a draw while the presenter owns the video only
    // for a new rect / owner / poster or a stale live mask, and each of those needs a new canvas; picture-only draws are already
    // gone at the source (`video` 0-1 per 5 s in the counter). The fullscreen draws were stick noise (fixed above).
    if (omniReasons == omniDrVideo && omniShellVideoOnlyDrawSkip && omniShellVideoOnlyDrawSkip()) {
        ++omniCensus.videoSkips;
        if (omniCanvasPending) { omniPresentFrame(); ++omniCensus.reused; }
        return;
    }
    int omniPlan = firstFrame ? 0 : omniInvisibleOnly ? 2 : omniPlanDraw(omniReasons); // OMNI_PERF_A_S4
    if (omniInvisibleOnly) { omniRegion.active = false; omniRegion.changedKnown = false; }
    // ws-a-1b watchdog: whatever the plan says, the whole frame is drawn at least every 2 s while anything asks for a draw
    // (no stale pixel can outlive 2 s, whatever a regional plan or a "nothing changed" decision missed).
    static uint32_t omniLastFullDraw = 0;
    if (omniPlan != 0 && omniNow - omniLastFullDraw >= 2000) { omniPlan = 0; omniRegion.active = false; ++omniCensus.forced; }
    if (omniPlan == 0) omniLastFullDraw = omniNow;
    if (omniPlan == 2) {   // nothing visible changed (stick noise, a refresh with the bars hidden, a page rect under the bars)
        ++omniCensus.nothing;
        if (!omniInvisibleOnly) omniPageDamage = OmniRows();   // dl2-candidate-55: not planned: keep any page rows for the next draw
        if (omniCanvasPending) { omniPresentFrame(); ++omniCensus.reused; }
        return;
    }
    ++omniCensus.draws; ++(omniPlan == 1 ? omniCensus.regional : omniCensus.full);
    omniVideoFixLastDraw = omniNow; // OMNI_C56_VIDEOFIX1
    for (int i = 0; i < omniDrCount; ++i) if (omniReasons & (1u << i)) ++omniCensus.reason[i];
    if (firstFrame) log("first frame: drawing shell");
    const auto drawStarted = SDL_GetPerformanceCounter();
    OmniMedia::Hw::holePunchShellPhase(5); // OMNI_HOLEPUNCH_V7_STALLTRACE: draw
    draw();
    OmniMedia::Hw::holePunchShellPhase(1);
    const auto drawFinished = SDL_GetPerformanceCounter();
    profilePaint += drawStarted - paintStarted;
    { const double f = double(SDL_GetPerformanceFrequency()); omniGap.paint = 1000.0 * double(drawStarted - paintStarted) / f; omniGap.draw = 1000.0 * double(drawFinished - drawStarted) / f; } // OMNI_TICK_GAP_V1
    profileDraw += drawFinished - drawStarted;
    if (++profileFrames % 60 == 0 && profileReports < 6 && omniReleaseDiagnostics()) {
        ++profileReports;
        const double frequency = SDL_GetPerformanceFrequency();
        char timings[256];
        snprintf(timings, sizeof(timings), "render timing: frames=%llu elapsed=%.3f paintMs=%.3f drawMs=%.3f",
            static_cast<unsigned long long>(profileFrames), (drawFinished - profileStarted) / frequency,
            1000.0 * profilePaint / frequency / profileFrames, 1000.0 * profileDraw / frequency / profileFrames);
        log(timings);
    }
    if (firstFrame) log("first frame: presented");
    firstFrame = false;
}
}
// OMNI_PERF_A_HOOK / OMNI_PERF_A_COUNTER (declared at the top of this file)
extern "C" { int (*omniShellVideoOnlyDrawSkip)(void) = nullptr; unsigned omniShellLastDrawReasons = 0; }

int omniBrowserMain()
{
    if (FILE* file=fopen("/data/omni/controller-style.txt","r")) {
        char value[32] {}; if (fgets(value,sizeof(value),file)) playStationIcons = !strncmp(value,"playstation",11); fclose(file);
    }
    uiTest = !access("/data/omni/ui-selftest.flag",F_OK);
    displayTest = !access("/data/omni/display-selftest.flag",F_OK);
    if (displayTest) {
        if (FILE* file = fopen("/data/omni/display-test-mode.txt", "r")) {
            char value[16] {};
            if (fscanf(file, "%15s", value) == 1 && (!strcmp(value,"1440") || !strcmp(value,"2160"))) SDL_setenv("OMNI_SDL_HEIGHT",value,1);
            fclose(file);
        }
    }
    blockerTest = !access("/data/omni/blocker-selftest.flag", F_OK);
    inputTest = !access("/data/omni/input-selftest.flag", F_OK);
    grabberTest = !access("/data/omni/grabber-selftest.flag", F_OK); // OMNI_NET_GRABBER_TEST_V1: flag text "mp4" = progressive case
    if (grabberTest) if (FILE* file = fopen("/data/omni/grabber-selftest.flag", "r")) {
        char value[8] {};
        if (fscanf(file, "%7s", value) == 1 && !strcmp(value, "mp4")) grabberTestURL += "?case=mp4";
        fclose(file);
    }
    googleTest = !access("/data/omni/google-selftest.flag", F_OK);
    youtubeTest = !access("/data/omni/youtube-selftest.flag", F_OK);
    ipcPressureTest = !access("/data/omni/ipc-pressure-selftest.flag", F_OK);
    widgetTest = !access("/data/omni/widget-selftest.flag", F_OK);
    featureTest = !access("/data/omni/feature-selftest.flag", F_OK);
    gamepadTest = !access("/data/omni/gamepad-selftest.flag", F_OK); // OMNI_GAMEPAD_TEST_V1
    padCtlTest = !access("/data/omni/padctl-selftest.flag", F_OK); // OMNI_PAD_CONTROLLER_TEST_V1
    stagedMediaTest = featureTest && !access("/data/omni/staged-media-selftest.flag", F_OK);
    pipelineTraceTest = !access("/data/omni/pipeline-trace.flag", F_OK);
    OmniMedia::Hw::diagnosticTraceStart();
    longMediaTest = stagedMediaTest && !access("/data/omni/long-media-selftest.flag", F_OK);
    mediaControlsTest = !access("/data/omni/media-controls-selftest.flag", F_OK);
    mediaMatrixTest = !access("/data/omni/media-matrix-selftest.flag", F_OK);
    mediaEnduranceTest = !access("/data/omni/media-endurance-selftest.flag", F_OK);
    mediaThirtyMinuteTest = mediaEnduranceTest && !access("/data/omni/media-thirty-minute-selftest.flag", F_OK);
    recoveryTest = !access("/data/omni/recovery-selftest.flag", F_OK);
    selfTest = !access("/data/omni/browser-selftest.flag", F_OK);
    const bool headless = selfTest || blockerTest || inputTest || googleTest || (youtubeTest && access("/data/omni/youtube-visible-test.flag", F_OK)) || widgetTest || (featureTest && access("/data/omni/media-visible-test.flag", F_OK)) || uiTest;
    nativeForeground = !headless;
    if (headless) SDL_SetHint(SDL_HINT_VIDEODRIVER, "dummy");
    if (FILE* f = fopen("/data/omni/display-mode.txt", "r")) {
        char value[16] {}, extra = 0;
        if (fscanf(f, "%15s %c", value, &extra) == 1)
            for (int i = 0; i < 3; ++i) if (!strcmp(value, omniDisplayModes[i])) omniDisplayChoice = i;
        fclose(f);
    }
    if (!headless && !displayTest) {
        if (omniDisplayChoice && !access("/data/omni/display-startup.pending", F_OK)) {
            omniDisplayChoice = 0;
            log("previous high-resolution startup incomplete; using 1080p recovery");
            omniDisplayRecovered = true;
        }
        if (omniDisplayChoice) {
            FILE* f = fopen("/data/omni/display-startup.pending", "w");
            if (f) { omniDisplayStartupPending = fclose(f) == 0; }
            if (!omniDisplayStartupPending) omniDisplayChoice = 0;
        }
        SDL_setenv("OMNI_SDL_HEIGHT", omniDisplayModes[omniDisplayChoice], 1);
    }
    log("initializing SDL software display");
    SDL_SetMainReady();
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_GAMECONTROLLER) || TTF_Init()) { log(SDL_GetError()); return 1; }
    SDL_DisplayMode mode {};
    int displayWidth = width, displayHeight = height;
    if (inputTest || uiTest) { displayWidth = 1920; displayHeight = 1080; }
    if (!headless && !SDL_GetDesktopDisplayMode(0, &mode) && mode.w > 0 && mode.h > 0) {
        displayWidth = mode.w; displayHeight = mode.h;
    }
    window = SDL_CreateWindow("Omni Browser", SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED,
        displayWidth, displayHeight, SDL_WINDOW_SHOWN | (headless ? 0 : SDL_WINDOW_FULLSCREEN_DESKTOP));
    if (!window) { log(SDL_GetError()); return 1; }
    screen = SDL_GetWindowSurface(window);
    if (!screen) { log(SDL_GetError()); SDL_Quit(); return 1; }
    fprintf(stderr, "browser: display=%dx%d surface=%dx%d layout=%dx%d fullscreen=%d\n", displayWidth, displayHeight, screen->w, screen->h, width, height, !headless); fflush(stderr);
    renderWidth = screen->w; renderHeight = screen->h;
    displayScale = double(renderWidth) / width;
    omniPageScale = (renderWidth >= 3840 && access("/data/omni/page-native-4k.flag", F_OK)) ? 0.5 : 1; // OMNI_FAST_PAGE_V1
    if (omniPageScale < 1) log("fast pages: page painted at half resolution and doubled (page-native-4k.flag turns this off)");
    OmniMedia::Hw::holePunchSetViewScale(1.0 / omniPageScale);
    omniLoadStyleSettings(); // OMNI_STYLE_V1: theme + auto-hide (full-height page view while it is on)
    omniMediaDownloadsLoadPreference(); // OMNI_MEDIA_DOWNLOADS_V1: no worker probe/start here
    renderPageHeight = omniAutoHideActive() ? renderHeight : renderHeight - physical(top) - physical(bottom);
    // Reserve the fullscreen extent before media starts; entering fullscreen must not grow this vector.
    pixels.reserve(size_t(renderWidth) * renderHeight * 4);
    pixels.assign(renderWidth * renderPageHeight * 4, 255);
    log("page pixel buffer ready");
    // OMNI_SHELL_PRESENT_V1: draw off-screen in the window's pixel format; the presenter thread
    // copies finished frames into the window surface (falls back to drawing in place).
    canvas = SDL_CreateRGBSurfaceWithFormat(0, screen->w, screen->h, 32, screen->format->format);
    if (!canvas) { log("off-screen canvas allocation failed; drawing in place"); canvas = screen; }
    // OMNI_HOLEPUNCH_V1: hardware video may be drawn under the page (refuses unknown layouts).
    OmniMedia::Hw::holePunchAttach(canvas->format->BytesPerPixel, canvas->format->Rshift, canvas->format->Gshift, canvas->format->Bshift);
    pageSurface = SDL_CreateRGBSurfaceWithFormatFrom(pixels.data(), renderWidth, renderPageHeight, 32, renderWidth * 4, SDL_PIXELFORMAT_ARGB8888);
    log("software canvas ready");
    omniOpenFonts(); // OMNI_STYLE_V1: Noto Sans JP when installed (CJK), else DejaVu as before
    log("UI fonts opened");
#ifdef __PROSPERO__
    size_t availableFlexible = 0;
    int memoryQuery = sceKernelAvailableFlexibleMemorySize(&availableFlexible);
    fprintf(stderr, "browser: flexible memory query=%d available=%zu\n", memoryQuery, availableFlexible);
    size_t configuredFlexible = 0;
    int configuredQuery = sceKernelConfiguredFlexibleMemorySize(&configuredFlexible);
    fprintf(stderr, "browser: memory budget configured-query=%d flexible=%zu direct=%lld\n",
        configuredQuery, configuredFlexible, static_cast<long long>(sceKernelGetDirectMemorySize()));
#endif
    if (!canvas || !pageSurface || !font || !smallFont) { log("surface/font initialization failed"); SDL_Quit(); return 1; }
    for (int i = 0; i < SDL_NumJoysticks(); ++i) omniOpenPad(i); // OMNI_MULTI_CONTROLLER_V1
    omniShoulderChord.reset(omniShoulderContext(), omniShoulderPhysical()); // OMNI_SHOULDER_DOWNLOADS_V1
    omniSavedReconcile(); // OMNI_SAVED_LINKS_V1: open them all
    WKRunLoopInitializeMain();
    omniGamepadInstall(); // OMNI_GAMEPAD_V1: before the context (WebKit's provider asks libwpe on first use)
    auto config = adoptWK(WKContextConfigurationCreate());
    WKContextConfigurationSetUserId(config.get(), -1);
    auto storeConfig = adoptWK(WKWebsiteDataStoreConfigurationCreate());
    std::string profile = "/data/omni/browser-profile";
    mkdir(profile.c_str(), 0777);
    auto pathString = [&](const char* name) { return adoptWK(WKStringCreateWithUTF8CString((profile + name).c_str())); };
    // Curl installs a durable cookie database only for an explicit nonempty
    // path. Unlike Cocoa, the PlayStation configuration supplies no default.
    // Keep normal expiry/session semantics; do not clear site state on launch.
    WKWebsiteDataStoreConfigurationSetCookieStorageFile(storeConfig.get(), pathString("/Cookies.db").get());
    WKWebsiteDataStoreConfigurationSetNetworkCacheDirectory(storeConfig.get(), pathString("/NetworkCache").get());
    WKWebsiteDataStoreConfigurationSetLocalStorageDirectory(storeConfig.get(), pathString("/LocalStorage").get());
    WKWebsiteDataStoreConfigurationSetIndexedDBDatabaseDirectory(storeConfig.get(), pathString("/IndexedDB").get());
    websiteDataStore = adoptWK(WKWebsiteDataStoreCreateWithConfiguration(storeConfig.get()));
    context = adoptWK(WKContextCreateWithConfiguration(config.get()));
    WKContextSetPrimaryWebsiteDataStore(context.get(), websiteDataStore.get());
    WKContextSetUsesSingleWebProcess(context.get(), true);
    preferences = adoptWK(WKPreferencesCreate());
    WKPreferencesSetAcceleratedCompositingEnabled(preferences.get(), false);
    WKPreferencesSetFullScreenEnabled(preferences.get(), true);
    WKPreferencesSetNeedsSiteSpecificQuirks(preferences.get(), true);
    status = "Preparing content blocker...";
    omniBlockerInitialize(blockerTest, [](bool ready) {
        if (widgetTest) {
            auto source = adoptWK(WKStringCreateWithUTF8CString("window.omniWidgetErrors=[];addEventListener('error',e=>omniWidgetErrors.push(e.message||('resource '+(e.target.src||e.target.href||e.target.tagName))),true);addEventListener('unhandledrejection',e=>omniWidgetErrors.push(String(e.reason)));"));
            auto script = adoptWK(WKUserScriptCreateWithSource(source.get(), kWKInjectAtDocumentStart, true));
            omniBlockerAddShellScript(script.get());
        }
        status = ready ? "Ready" : "Ad blocking unavailable: rules could not be loaded.";
        if (blockerTest && !ready) { log("BLOCK TEST FAIL: blocker unavailable"); running = false; return; }
        if (blockerTest) omniBlockerSetEnabled(false);
        omniFastPageInstall(); // OMNI_FAST_PAGE_V1: with 2160p advertised smooth (OMNI_SMOOTH_4K60_V1), sites see the
        // display's full ratio and pick 2160p, which needs no scaling at all.
        omniSelectInstall(); // OMNI_DIALOGS_V1: <select> menus (not in self-test modes)
        if (!omniEverydayStart()) { // OMNI_EVERYDAY_V1: session restore / new-tab page; self-test modes unchanged
        newTab(); navigate(featureTest ? "http://127.0.0.1:8080/fs/data/omni/feature-test.html" : widgetTest ? "https://www.google.com/recaptcha/api2/demo" : googleTest ? "https://www.google.com/search?q=webkit" : inputTest ? "http://127.0.0.1:8080/fs/data/omni/input-test/index.html" : grabberTest ? grabberTestURL.c_str() /* OMNI_NET_GRABBER_TEST_V1 */ : blockerTest ? blockerTestURL : gamepadTest ? "http://127.0.0.1:8080/fs/data/omni/gamepad-test.html" : padCtlTest ? "http://127.0.0.1:8095/" : "https://example.com/");
        }
        if (featureTest && !access("/data/omni/ublock-test.flag", F_OK)) navigate("http://127.0.0.1:8080/fs/data/omni/feature-test.html?ublock");
        if (recoveryTest) { newTab(); navigate("https://example.com/"); }
        if (!ready) status = "Ad blocking unavailable: rules could not be loaded.";
        stageTime = SDL_GetTicks();
    });
    startTime = SDL_GetTicks();
    stageTime = startTime;
    log("display ready; browser running");
    WTF::RunLoop::Timer refresh(WTF::Ref { WTF::RunLoop::mainSingleton() }, "OmniBrowser refresh"_s, [] { tick(nullptr); });
    refresh.startRepeating(WTF::Seconds(omniPerfOn(omniPerfS8) ? omniVblankMs / 1000 : 1.0 / 60)); // OMNI_SHELL_DRAW_V1 (was 30 Hz); OMNI_PERF_A_S8: 59.94 Hz
    omniRefreshTimer = &refresh; // OMNI_PERF_A_S8: vblank phase (omniVblankAlign)
    log("refresh timer ready; entering main loop");
    WKRunLoopRunMain();
    log("main loop returned");
    return 0;
}
