// OMNI_REDUCE_MOTION_V1: the pure part of Browser settings > "Reduce motion" (no SDL, no WebKit).
// The shell side is OmniReduceMotionShell.h; the reasons are in tools/apply_reduce_motion.py. Tested on the host with g++
// (tools/test_reduce_motion.cpp).
//
// The rule: with Reduce motion on, nothing of Omni's own moves. Anything that slides, eases or sweeps (the auto-hiding
// bars, the pointer's snap onto a link, the progress bar's fill, night light's colour change, smooth scrolling) happens
// at once (Kind::Move -> 0 ms); a pure opacity change (panels, toasts, the progress bar and the scroll position bar
// going away) stays as a cross-fade of at most kMaxFadeMs (Kind::Fade). Off: every duration is exactly what it was.
#pragma once
#include <algorithm>
#include <cstdint>
#include <string>

namespace OmniReduceMotion {

constexpr int kRowId = 849;                                  // Browser settings row (apply_reduce_motion.py refuses a tree
                                                             // or a tools folder that already uses 849)
constexpr const char* kFileName = "reduce-motion.txt";      // in the data folder: "on" / "off"
constexpr const char* kRowLabel = "Reduce motion";
constexpr const char* kRowDetail = "Bars, panels, toasts and the pointer snap without animating; no smooth scrolling;"
                                   " pages get no CSS animations";
constexpr uint32_t kMaxFadeMs = 80;

enum class Kind { Move, Fade };

// Omni's own animations: the durations at their call sites (ms). test_reduce_motion.cpp checks them against the tree.
constexpr uint32_t kBarSlideMs = 220;        // OMNI_STYLE_V1: the auto-hiding bars (omniStyleTick, dt / 220.f)
constexpr uint32_t kPointerSnapMs = 110;     // OmniPointerFeel.h: the pointer easing onto the nearest link
constexpr uint32_t kProgressFillMs = 160;    // the progress bar catching up with the load
constexpr uint32_t kProgressFinishMs = 80;   // ... running to its end when the load is done
constexpr uint32_t kProgressFadeMs = 260;    // ... then going away
constexpr uint32_t kToastInMs = 180, kToastOutMs = 320;   // the toast pill (it also rises kToastRisePx while it fades in)
constexpr float kToastRisePx = 12;
constexpr uint32_t kPanelFadeMs = 150;       // omniPanelFadeMs: settings, keyboard, menus, history, dialogs
constexpr uint32_t kNightLightMs = 2000;     // OmniNightLight::kFadeMs (a colour sweep: Move)
constexpr uint32_t kScrollbarFadeMs = 300;   // OMNI_SCROLL_PLUS_V1: OmniScrollPlus::kFadeMs (its 700 ms hold is not motion)

// The duration to use.
constexpr uint32_t ms(bool reduce, Kind kind, uint32_t normal)
{
    return !reduce ? normal : kind == Kind::Fade ? std::min(normal, kMaxFadeMs) : 0;
}
constexpr bool instant(bool reduce, Kind kind, uint32_t normal) { return ms(reduce, kind, normal) == 0; }

// 0..1 done `elapsed` ms into a `duration` ms animation; a zero duration is done at once.
inline float progress(uint32_t elapsed, uint32_t duration)
{
    return duration == 0 ? 1.f : std::min(1.f, float(elapsed) / float(duration));
}
// One tick's share of a 0..1 animation (dtMs since the last tick); a zero duration takes the whole way at once.
inline float tickStep(float dtMs, uint32_t duration)
{
    return duration == 0 ? 1.f : std::min(1.f, dtMs / float(duration));
}

// Panels: 1 - (1 - t)^3 over the panel fade (omniPanelT), normalMs = omniPanelFadeMs.
inline float panelFade(bool reduce, uint32_t dt, uint32_t normalMs)
{
    const uint32_t d = ms(reduce, Kind::Fade, normalMs);
    if (dt >= d) return 1;
    const float u = 1 - float(dt) / float(d);
    return 1 - u * u * u;
}

// Toast: opacity coming in (sinceMs after it appeared) and going (remainingMs before it ends, may be <= 0).
inline float toastIn(bool reduce, uint32_t sinceMs) { return progress(sinceMs, ms(reduce, Kind::Fade, kToastInMs)); }
inline float toastOut(bool reduce, int32_t remainingMs)
{
    if (remainingMs <= 0) return 0;
    const uint32_t d = ms(reduce, Kind::Fade, kToastOutMs);
    return d == 0 ? 1.f : std::min(1.f, float(remainingMs) / float(d));
}
inline float toastRise(bool reduce) { return reduce ? 0.f : kToastRisePx; }

// A "shown, then fading" clock (OMNI_SCROLL_PLUS_V1's position bar: hold 700 ms, fade 300 ms): the time handed to its own
// alpha() so that, reduced, the fade part takes ms(Fade, fade) instead. Off: the time unchanged.
inline uint32_t fadeClock(uint32_t elapsed, uint32_t hold, uint32_t fade, bool reduce)
{
    if (!reduce || elapsed <= hold || fade == 0) return elapsed;
    const uint32_t d = ms(reduce, Kind::Fade, fade);
    if (d == 0) return hold + fade;
    const uint64_t scaled = uint64_t(elapsed - hold) * fade / d;
    return scaled >= fade ? hold + fade : hold + uint32_t(scaled);
}

// Pages. WebKit has a reduced-motion switch only inside WebCore (Settings::forcedPrefersReducedMotionAccessibilityValue,
// not a WebPreferences key, so no WKPreferences / C API reaches it) and this port's Theme answers "no preference", so
// `prefers-reduced-motion: reduce` never matches. Instead one global user style sheet (user level: its !important wins
// over the page's, inline styles included): animations and transitions finish at once (0.01 ms, so animationend /
// transitionend still fire and pages waiting for them go on), one iteration, no smooth scroll-behavior.
constexpr const char* kPageCss =
    "*,*::before,*::after{animation-duration:0.01ms!important;animation-iteration-count:1!important;"
    "transition-duration:0.01ms!important;scroll-behavior:auto!important}";

// reduce-motion.txt
inline bool parse(const std::string& text)
{
    size_t i = 0;
    while (i < text.size() && (text[i] == ' ' || text[i] == '\t' || text[i] == '\r' || text[i] == '\n')) ++i;
    return text.compare(i, 2, "on") == 0 && (i + 2 == text.size() || text[i + 2] == '\n' || text[i + 2] == '\r'
        || text[i + 2] == ' ' || text[i + 2] == '\t');
}
inline std::string serialize(bool on) { return on ? "on\n" : "off\n"; }
inline const char* rowValue(bool on) { return on ? "On" : "Off"; }
inline const char* noticeText(bool on) { return on ? "Reduce motion on" : "Reduce motion off"; }

} // namespace OmniReduceMotion
