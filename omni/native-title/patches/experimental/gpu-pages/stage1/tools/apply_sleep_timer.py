#!/usr/bin/env python3
"""OMNI_SLEEP_TIMER_V1 (2026-11-16): Sleep timer chooser - stop playback in 15 / 30 / 45 / 60 / 90 min, at the end of
this video, or Off.

What was there: OMNI_SMALL_COMFORTS_V1 (OmniBrowser.cpp) has an Options tile "Sleep timer" that CYCLES
Off -> 15 -> 30 -> 60 -> 90 on each press, warns a minute before and then pauses every tab (omniSleepPauseAll: a pause
script per tab, and 3 s later every tab still playing (cross-origin players) is muted until the next button press).
This patch keeps that pause path and the tile, and replaces the cycling with a chooser.

What the user sees
  - Options > "Sleep timer" (the existing tile, always shown) and "Now playing" > "Sleep timer" (new last row) open the
    panel "Sleep timer":
        15 minutes / 30 minutes / 45 minutes / 60 minutes / 90 minutes
        At end of this video      value: the playing tab's title (disabled, "Nothing is playing", when no tab plays)
        Off                       (disabled while off)
    The active choice shows its time left ("23 min left" / "Active"). Cross picks and goes back to the panel below.
  - Notices: "Sleep timer: playback stops in 45 min", "... at the end of this video", "Sleep timer off",
    "Sleep timer: playback stops in 1 minute" (a minute before), "Sleep timer: playback stopped".
  - Top bar, right of the controller battery: "zZ 23 min" / "zZ end of video" / "zZ ..." (fading) while active.
  - Time up: the sound fades over 10 s (one small page script per second, only in tabs WebKit reports as playing
    audio: each media element's volume = its own volume x ((10-s-1)/10)^2), then every tab is paused through
    omniSleepPauseAll (+ its mute of still-playing tabs until a button press), the volumes are put back on the paused
    elements, and the notice shows. Cross-origin iframes (YouTube embeds) can't be faded; they are paused / muted by
    omniSleepPauseAll as before.
  - "At end of this video": the tab (Now playing's tab, otherwise media controls' omniNpTarget) is probed from the
    native tick with media controls' read-only script (MC::kProbe) once every 5 s (sooner, once, when < 5 s remain).
    Stop when: position within 1 s of the duration, another src / duration (the next video began, autoplay), no media
    twice, or 3 probes without an answer (8 s timeout each). No fade then (the video has ended). A live stream has no
    end: the timer turns into 60 min with a notice. The tab closed: the timer turns off with a notice.
  - Survives tab switches (global state); not saved (an Omni restart starts with it off).
Screen saver: checked - nothing in Omni blocks the PS5 screen saver (no sceSystemServicePowerTick in the shell,
OmniMain.cpp, libSDL2-hdr-v5.a or the outputs tree; SDL's own SDL_DisableScreenSaver has no PS5 driver hook, it
only sets a flag). So there is nothing to release and no "screen saver" setting was added.

Pure part: engine/entry/OmniSleepTimer.h (no SDL / WebKit): Timer phases (Off, Counting, Watching, Fading), warn,
fade curve and steps, the end-of-video watcher, the fade / restore page script, every text.
Tested by tools/test_sleep_timer.cpp: g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_sleep_timer.cpp -o t && ./t
Shell side: engine/entry/OmniSleepTimerShell.h (included from OmniFeatures3.h after OmniSiteClearShell.h).

Anchors (exactly once each; MARK makes each file idempotent; insert-before / insert-after except the two
small-comforts bodies):
  OmniBrowser.cpp     the OmniSmallComforts.h include line (pure include after it); the OmniFeatures3Decl.h include
                      line (forward declarations after it); the "OMNI_MQ_NATIVE_V1: global uBlock lives in the shared
                      quick-access row." comment in omniDrawTopBar (the top-bar label before it); the body of
                      omniSleepValue (omniSleep.value + return text) and of omniSleepCycle (omniSleep.cycle + its
                      notice) - the old SleepTimer object stays but is never started.
  OmniFeatures3.h     the OmniSiteClearShell.h include line; the omniScTick line of omniF3Tick (omniStTick after it).
  OmniMediaControlsShell.h  the kRowGo row of omniNpBuild (row after it); the kRowPlay case of omniNpInput (case
                      before it). apply_media_controls.py rewrites that header when it differs, so run this AFTER it.
Apply AFTER apply_media_controls.py and apply_site_clear.py.
usage: apply_sleep_timer.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_SLEEP_TIMER_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_SLEEP_TIMER_V1: the pure part of the Sleep timer chooser (no SDL, no WebKit). The shell side is
// OmniSleepTimerShell.h; the reasons are in tools/apply_sleep_timer.py. Times are SDL_GetTicks() milliseconds
// (uint32_t, compared wrap-safe). Tested with g++ (test_sleep_timer.cpp).
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <string>

namespace OmniSleepTimer {

inline bool reached(uint32_t now, uint32_t at) { return int32_t(now - at) >= 0; }

constexpr int kChoices[] = { 15, 30, 45, 60, 90 };   // minutes
constexpr int kChoiceCount = int(sizeof(kChoices) / sizeof(kChoices[0]));
constexpr int kEndOfVideo = -1;                     // a choice: stop when the watched video ends
constexpr int kLiveFallbackMinutes = 60;            // "end of video" on a live stream
constexpr uint32_t kWarnMs = 60000, kFadeStepMs = 1000, kProbeMs = 5000, kProbeTimeoutMs = 8000, kProbeMinMs = 500;
constexpr int kFadeSteps = 10;                      // 10 steps of 1 s
constexpr int kMaxFails = 3, kMaxEmpty = 2;
constexpr double kLive = -2;                        // Probe::dur of a stream without an end (as OmniMediaControls)
constexpr double kEndSlack = 1.0;                   // seconds: "at the end"

inline bool validMinutes(int m) { for (int c : kChoices) if (c == m) return true; return false; }

// The volume multiplier after fade step s (0 .. kFadeSteps-1): ((kFadeSteps - s - 1) / kFadeSteps)^2, so 0.81 ... 0.
inline double fadeFactor(int step)
{
    if (step < 0) return 1.0;
    if (step >= kFadeSteps - 1) return 0.0;
    const double x = double(kFadeSteps - step - 1) / kFadeSteps;
    return x * x;
}

// --- end of video ------------------------------------------------------------------------------------------------
// One answer of the media-controls probe. state: 0 none, 1 playing, 2 paused; pos / dur seconds (-1 unknown, dur
// kLive for a live stream).
struct Probe { bool ok = false; int state = 0; double pos = -1, dur = -1; std::string src; };
enum class Verdict { Keep, Ended, Live };
class EndWatch {
public:
    void reset() { *this = EndWatch(); }
    // nextMs: when to probe again (5 s, or just after the remaining time when less than 5 s remain).
    Verdict feed(const Probe& p, uint32_t& nextMs)
    {
        nextMs = kProbeMs;
        if (!p.ok) return ++fails_ >= kMaxFails ? Verdict::Ended : Verdict::Keep;
        fails_ = 0;
        if (p.state == 0) return ++empty_ >= kMaxEmpty ? Verdict::Ended : Verdict::Keep;
        empty_ = 0;
        if (p.dur == kLive) return Verdict::Live;
        if (primed_) {
            if (!src_.empty() && !p.src.empty() && p.src != src_) return Verdict::Ended;   // the next item began
            if (dur_ > 0 && p.dur > 0 && (p.dur - dur_ > 1.0 || dur_ - p.dur > 1.0)) return Verdict::Ended;   // same src (MSE), new item
        } else {
            primed_ = true;
            src_ = p.src;
        }
        if (p.dur > 0) dur_ = p.dur;
        if (p.dur > 0 && p.pos >= 0 && p.pos >= p.dur - kEndSlack) return Verdict::Ended;
        if (p.state == 1 && p.dur > 0 && p.pos >= 0) {
            const double left = p.dur - p.pos;
            if (left * 1000.0 < kProbeMs) {
                const uint32_t ms = uint32_t(left * 1000.0) + 500u;
                nextMs = ms < kProbeMinMs ? kProbeMinMs : ms;
            }
        }
        return Verdict::Keep;
    }
    const std::string& src() const { return src_; }

private:
    bool primed_ = false;
    int fails_ = 0, empty_ = 0;
    double dur_ = -1;
    std::string src_;
};

// --- the timer ---------------------------------------------------------------------------------------------------
enum class Phase { Off, Counting, Watching, Fading };
enum class Event { None, Warn, Fade, Fire, Probe };
struct Step { Event event = Event::None; double factor = 1.0; bool redraw = false; };

class Timer {
public:
    Phase phase() const { return phase_; }
    bool on() const { return phase_ != Phase::Off; }
    int minutes() const { return minutes_; }        // the chosen minutes (Counting / Fading after Counting), else 0
    uintptr_t tab() const { return tab_; }          // the watched tab (Watching)
    bool probeOut() const { return probeOut_; }

    bool startMinutes(int m, uint32_t now)
    {
        if (!validMinutes(m)) { off(); return false; }
        phase_ = Phase::Counting; minutes_ = m; tab_ = 0; probeOut_ = false;
        deadline_ = now + uint32_t(m) * 60000u;
        warned_ = uint32_t(m) * 60000u <= kWarnMs;
        shown_ = -2;
        return true;
    }
    void startEndOfVideo(uintptr_t tab, uint32_t now)
    {
        phase_ = Phase::Watching; minutes_ = 0; tab_ = tab; probeOut_ = false; probeAt_ = now; warned_ = true;
        watch_.reset();
        shown_ = -2;
    }
    void off() { phase_ = Phase::Off; minutes_ = 0; tab_ = 0; probeOut_ = false; warned_ = false; shown_ = -2; }

    // Once per native tick (cheap when nothing is due).
    Step tick(uint32_t now)
    {
        Step s;
        switch (phase_) {
        case Phase::Off: return s;
        case Phase::Counting:
            if (reached(now, deadline_)) { phase_ = Phase::Fading; fadeStart_ = now; lastStep_ = -1; break; }
            if (!warned_ && reached(now + kWarnMs, deadline_)) { warned_ = true; s.event = Event::Warn; }
            s.redraw = remember(minutesLeft(now));
            return s;
        case Phase::Watching:
            if (probeOut_) {
                if (!reached(now, probeSent_ + kProbeTimeoutMs)) return s;
                probeOut_ = false;   // no answer in time: one failure
                uint32_t next = kProbeMs;
                if (watch_.feed(Probe(), next) == Verdict::Ended) { off(); s.event = Event::Fire; s.redraw = true; return s; }
                probeAt_ = now + next;
                return s;
            }
            if (reached(now, probeAt_)) { probeOut_ = true; probeSent_ = now; s.event = Event::Probe; }
            s.redraw = remember(-1);
            return s;
        case Phase::Fading: break;
        }
        // Fading: one step a second, then Fire.
        const int step = int((now - fadeStart_) / kFadeStepMs);
        if (step >= kFadeSteps) { off(); s.event = Event::Fire; s.redraw = true; return s; }
        if (step > lastStep_) { lastStep_ = step; s.event = Event::Fade; s.factor = fadeFactor(step); }
        s.redraw = remember(-3);
        return s;
    }
    // The probe's answer (Watching, a probe out). Ended: the timer is off and the shell stops playback now; Live: the
    // timer now counts kLiveFallbackMinutes.
    Verdict answer(const Probe& p, uint32_t now)
    {
        if (phase_ != Phase::Watching || !probeOut_) return Verdict::Keep;
        probeOut_ = false;
        uint32_t next = kProbeMs;
        const Verdict v = watch_.feed(p, next);
        if (v == Verdict::Ended) off();
        else if (v == Verdict::Live) startMinutes(kLiveFallbackMinutes, now);
        else probeAt_ = now + next;
        return v;
    }
    const std::string& watchedSrc() const { return watch_.src(); }

    // Whole minutes left, rounded up (Counting), 0 otherwise.
    int minutesLeft(uint32_t now) const
    {
        if (phase_ != Phase::Counting) return 0;
        const int32_t left = int32_t(deadline_ - now);
        return left <= 0 ? 0 : int((uint32_t(left) + 59999u) / 60000u);
    }
    // Options / Now playing row value.
    std::string value(uint32_t now) const
    {
        switch (phase_) {
        case Phase::Counting: { const int m = minutesLeft(now); return std::to_string(m < 1 ? 1 : m) + " min left"; }
        case Phase::Watching: return "End of video";
        case Phase::Fading: return "Stopping...";
        default: return "Off";
        }
    }
    // The top bar's label ("" when off).
    std::string badge(uint32_t now) const
    {
        switch (phase_) {
        case Phase::Counting: { const int m = minutesLeft(now); return "zZ " + std::to_string(m < 1 ? 1 : m) + " min"; }
        case Phase::Watching: return "zZ end of video";
        case Phase::Fading: return "zZ ...";
        default: return std::string();
        }
    }

private:
    bool remember(int shown) { if (shown == shown_) return false; shown_ = shown; return true; }
    Phase phase_ = Phase::Off;
    int minutes_ = 0;
    uintptr_t tab_ = 0;
    uint32_t deadline_ = 0, fadeStart_ = 0, probeAt_ = 0, probeSent_ = 0;
    int lastStep_ = -1, shown_ = -2;
    bool warned_ = false, probeOut_ = false;
    EndWatch watch_;
};

// --- texts -------------------------------------------------------------------------------------------------------
inline std::string choiceLabel(int m)
{
    if (m == kEndOfVideo) return "At end of this video";
    if (m <= 0) return "Off";
    return std::to_string(m) + " minutes";
}
inline std::string startNotice(int m)
{
    if (m == kEndOfVideo) return "Sleep timer: playback stops at the end of this video";
    if (m <= 0) return "Sleep timer off";
    return "Sleep timer: playback stops in " + std::to_string(m) + " min";
}
inline std::string warnNotice() { return "Sleep timer: playback stops in 1 minute"; }
inline std::string firedNotice() { return "Sleep timer: playback stopped"; }
inline std::string liveNotice() { return "Sleep timer: a live stream has no end, stopping in " + std::to_string(kLiveFallbackMinutes) + " min"; }
inline std::string goneNotice() { return "Sleep timer off: the video's tab was closed"; }
inline std::string nothingNotice() { return "Nothing is playing"; }
inline std::string subtitle(const Timer& t, uint32_t now)
{
    if (!t.on()) return "Off. Stops playback in every tab; not kept after Omni restarts";
    if (t.phase() == Phase::Watching) return "Active: stops at the end of the video";
    if (t.phase() == Phase::Fading) return "Stopping playback...";
    return "Active: " + t.value(now);
}

// --- the page script ---------------------------------------------------------------------------------------------
// f in [0, 1]: every playing media element (main frame, same-origin frames to depth 3) gets volume = its own volume
// (kept the first time in el._omniStV) x f. f < 0: put the kept volumes back (elements touched before). Returns the
// number of elements touched.
inline std::string fadeScript(double f)
{
    char num[32];
    if (f < 0) std::snprintf(num, sizeof num, "-1");
    else std::snprintf(num, sizeof num, "%.3f", f > 1 ? 1.0 : f);
    return std::string("(function(f){var n=0;function w(d,k){if(!d||k>3)return;try{var m=d.querySelectorAll('video,audio');"
        "for(var i=0;i<m.length;i++){var e=m[i];try{if(f<0){if(e._omniStV!==undefined){e.volume=e._omniStV;delete e._omniStV;n++;}}"
        "else if(!e.paused||e._omniStV!==undefined){if(e._omniStV===undefined)e._omniStV=e.volume;"
        "e.volume=Math.max(0,Math.min(1,e._omniStV*f));n++;}}catch(x){}}"
        "var r=d.querySelectorAll('iframe,frame');for(var j=0;j<r.length;j++){var c=null;try{c=r[j].contentDocument;}catch(x){}w(c,k+1);}}"
        "catch(x){}}w(document,0);return n;})(") + num + ")";
}
inline std::string restoreScript() { return fadeScript(-1); }

} // namespace OmniSleepTimer
'''

SHELL = r'''// OMNI_SLEEP_TIMER_V1: the Sleep timer chooser (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's
// anonymous namespace, after OmniSiteClearShell.h, before OmniMediaControlsShell.h). The pure part is OmniSleepTimer.h;
// the reasons are in tools/apply_sleep_timer.py. Main thread only; nothing is written to disk.
// Pausing reuses OMNI_SMALL_COMFORTS_V1's omniSleepPauseAll (a pause script per tab + a mute of still-playing tabs
// until the next button press); "end of video" reuses media controls' read-only probe (OmniMediaControls::script).
#pragma once

namespace OST = OmniSleepTimer;
constexpr int omniStKind = 7330;           // the chooser's OmniFxPanel::kind
constexpr int omniStRowEnd = 1000, omniStRowOff = 1001;   // chooser rows (the minute rows use their minutes)
static OST::Timer omniSt;
static uintptr_t omniStGen = 0;            // probe answers for an older choice are dropped
static uintptr_t omniStOpenKey = 0;        // the tab "At end of this video" means (Now playing's tab; 0: media controls' pick)
static Tab* omniNpTarget();                // OmniMediaControlsShell.h

static Tab* omniStTab(uintptr_t key)
{
    if (key) for (auto& t : tabs) if (t->omniMediaIdentity == key) return t.get();
    return nullptr;
}
static Tab* omniStEndTab() { return omniStOpenKey ? omniStTab(omniStOpenKey) : omniNpTarget(); }
static void omniStScript(const std::string& source, bool onlyPlaying)
{
    auto js = adoptWK(WKStringCreateWithUTF8CString(source.c_str()));
    for (auto& t : tabs) {
        if (!t->page || t->crashed) continue;
        if (onlyPlaying && !(WKPageGetMediaState(t->page) & kWKMediaIsPlayingAudio)) continue;   // UI-process cached, no IPC
        WKPageEvaluateJavaScriptInMainFrame(t->page, js.get(), nullptr, [](WKTypeRef, WKErrorRef, void*) { });
    }
}
static void omniStFire(uint32_t now)
{
    omniSleepPauseAll(now);                        // OMNI_SMALL_COMFORTS_V1: pause every tab, mute leftovers after 3 s
    omniStScript(OST::restoreScript(), false);     // after the pause (same page, same order): volumes back
    notice(OST::firedNotice());
    fprintf(stderr, "OMNI SLEEP TIMER: playback stopped\n"); fflush(stderr);
    omniShellDirty = true;
}
static void omniStSet(int choice, uintptr_t key)
{
    const uint32_t now = SDL_GetTicks();
    if (omniSt.phase() == OST::Phase::Fading) omniStScript(OST::restoreScript(), false);   // a fade in progress: undo it
    ++omniStGen;
    if (choice == OST::kEndOfVideo) {
        Tab* t = key ? omniStTab(key) : omniNpTarget();
        if (!t) { notice(OST::nothingNotice()); return; }
        omniSt.startEndOfVideo(t->omniMediaIdentity, now);
    } else if (!omniSt.startMinutes(choice, now)) {
        omniSt.off();
        choice = 0;
    }
    notice(OST::startNotice(choice));
    omniShellDirty = true;
}
static void omniStProbe()
{
    Tab* t = omniStTab(omniSt.tab());
    if (!t || !t->page || t->crashed) {
        omniSt.off(); ++omniStGen;
        notice(OST::goneNotice());
        omniShellDirty = true;
        return;
    }
    auto js = adoptWK(WKStringCreateWithUTF8CString(OmniMediaControls::script(OmniMediaControls::kProbe, omniSt.watchedSrc()).c_str()));
    WKPageEvaluateJavaScriptInMainFrame(t->page, js.get(), reinterpret_cast<void*>(omniStGen), [](WKTypeRef result, WKErrorRef error, void* ctx) {
        if (reinterpret_cast<uintptr_t>(ctx) != omniStGen) return;   // another choice was made since
        const OmniMediaControls::Info i = OmniMediaControls::parse(omniFxResultString(result, error));
        OST::Probe p;
        p.ok = i.ok; p.pos = i.position; p.dur = i.duration; p.src = i.src;
        p.state = i.state == OmniMediaControls::kPlaying ? 1 : i.state == OmniMediaControls::kPaused ? 2 : 0;
        const uint32_t now = SDL_GetTicks();
        switch (omniSt.answer(p, now)) {
        case OST::Verdict::Ended: ++omniStGen; omniStFire(now); break;
        case OST::Verdict::Live: notice(OST::liveNotice()); omniShellDirty = true; break;
        default: break;
        }
    });
}

// --- per pass (omniF3Tick) -------------------------------------------------------------------------------------------
static void omniStTick(uint32_t now)
{
    if (!omniSt.on()) return;
    const OST::Step s = omniSt.tick(now);
    if (s.redraw) omniShellDirty = true;
    switch (s.event) {
    case OST::Event::Warn: notice(OST::warnNotice()); break;
    case OST::Event::Fade: omniStScript(OST::fadeScript(s.factor), true); break;   // at most one script per second
    case OST::Event::Fire: ++omniStGen; omniStFire(now); break;
    case OST::Event::Probe: omniStProbe(); break;
    default: break;
    }
}

// --- top bar (omniDrawTopBar, right of the controller battery) --------------------------------------------------------
static void omniStDrawTopBar(float x)
{
    if (!omniSt.on()) return;
    const OmniTheme& T = omniTheme();
    omniLabel(omniSt.badge(SDL_GetTicks()), x, 30, omniCaption, omniSt.phase() == OST::Phase::Fading ? T.accent : T.inkDim, 0, int(1276 - x));
}

// --- the chooser -----------------------------------------------------------------------------------------------------
static void omniStBuild(OmniFxPanel& p)
{
    const uint32_t now = SDL_GetTicks();
    p.subtitle = OST::subtitle(omniSt, now);
    auto add = [&](int id, const std::string& label, bool on, std::string value) {
        OmniFxRow r; r.id = id; r.label = label; r.enabled = on; r.value = std::move(value); p.rows.push_back(r);
    };
    const bool counting = omniSt.phase() == OST::Phase::Counting;
    for (int m : OST::kChoices) add(m, OST::choiceLabel(m), true, counting && omniSt.minutes() == m ? omniSt.value(now) : std::string());
    Tab* t = omniStEndTab();
    const bool watching = omniSt.phase() == OST::Phase::Watching;
    add(omniStRowEnd, OST::choiceLabel(OST::kEndOfVideo), t != nullptr,
        watching ? std::string("Active") : t ? OmniMediaControls::rowValue(t->title, t->url) : OST::nothingNotice());
    add(omniStRowOff, OST::choiceLabel(0), omniSt.on(), std::string());
}
static bool omniStInput(OmniFxPanel&, const OmniFxRow& r, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (!r.enabled) return true;
    const int choice = r.id == omniStRowEnd ? OST::kEndOfVideo : r.id == omniStRowOff ? 0 : r.id;
    omniStSet(choice, omniStOpenKey);
    omniFxPop();   // back to Options / Now playing (its row shows the new value)
    return true;
}
static void omniStOpen(uintptr_t key)
{
    omniStOpenKey = key;
    OmniFxPanel p;
    p.kind = omniStKind; p.title = "Sleep timer"; p.w = 640;
    p.build = omniStBuild; p.input = omniStInput;
    p.faces = { { 0, "Choose" }, { 1, "Back" } };
    p.extra = "The sound fades over 10 seconds, then every tab pauses";
    omniFxPush(std::move(p));
}
static std::string omniStValue() { return omniSt.value(SDL_GetTicks()); }
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSmallComforts.h" // OMNI_SMALL_COMFORTS_V1: sleep timer, battery bars, downloads-done file (pure)\n',
         '#include "OmniSmallComforts.h" // OMNI_SMALL_COMFORTS_V1: sleep timer, battery bars, downloads-done file (pure)\n'
         '#include "OmniSleepTimer.h" // OMNI_SLEEP_TIMER_V1: Sleep timer chooser, fade, end of video (pure)\n'),
        ('#include "OmniFeatures3Decl.h" // OMNI_FEATURES_V3: star, suggestions, page tools, dark pages, tab memory\n',
         '#include "OmniFeatures3Decl.h" // OMNI_FEATURES_V3: star, suggestions, page tools, dark pages, tab memory\n'
         'static std::string omniStValue();             // OMNI_SLEEP_TIMER_V1 (OmniSleepTimerShell.h): "Off" / "23 min left" / ...\n'
         'static void omniStOpen(uintptr_t key = 0);    // OMNI_SLEEP_TIMER_V1: the chooser (key: the tab "end of this video" means)\n'
         'static void omniStDrawTopBar(float x);        // OMNI_SLEEP_TIMER_V1: "zZ 23 min" in the top bar\n'),
        ('    // OMNI_MQ_NATIVE_V1: global uBlock lives in the shared quick-access row.\n',
         '    omniStDrawTopBar(OmniSmallComforts::battery().bars() >= 0 ? 1155.f : 1130.f); // OMNI_SLEEP_TIMER_V1: "zZ 23 min" while active\n'
         '    // OMNI_MQ_NATIVE_V1: global uBlock lives in the shared quick-access row.\n'),
        ('    omniSleep.value(SDL_GetTicks(), text, sizeof(text));\n    return text;\n',
         '    (void)text;\n    return omniStValue(); // OMNI_SLEEP_TIMER_V1: the chooser\'s state (was omniSleep.value)\n'),
        ('    const int minutes = omniSleep.cycle(SDL_GetTicks());\n'
         '    notice(minutes ? "Sleep timer: playback pauses in " + std::to_string(minutes) + " min" : std::string("Sleep timer off"));\n',
         '    omniStOpen(); // OMNI_SLEEP_TIMER_V1: the chooser (was: cycle Off / 15 / 30 / 60 / 90 on each press)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n',
         '#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n'
         '#include "OmniSleepTimerShell.h" // OMNI_SLEEP_TIMER_V1\n'),
        ('    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n',
         '    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n'
         '    omniStTick(now);    // OMNI_SLEEP_TIMER_V1: countdown, fade (1 script/s), end-of-video probe (every 5 s)\n'),
    ],
    'OmniMediaControlsShell.h': [
        ('    add(MC::kRowGo, v.goLabel, true);\n',
         '    add(MC::kRowGo, v.goLabel, true);\n'
         '    add(omniStNpRow, "Sleep timer", true, omniStValue()); // OMNI_SLEEP_TIMER_V1\n'),
        ('    case MC::kRowPlay: omniNpRun(MC::kToggle); break;\n',
         '    case omniStNpRow: omniStOpen(omniNpKey); return true; // OMNI_SLEEP_TIMER_V1: "end of this video" = this tab\n'
         '    case MC::kRowPlay: omniNpRun(MC::kToggle); break;\n'),
    ],
}
# the Now playing row id (MC rows are 1..8)
SHELL = SHELL.replace("constexpr int omniStRowEnd", "constexpr int omniStNpRow = 40;    // Now playing's \"Sleep timer\" row\nconstexpr int omniStRowEnd", 1)


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits, mark=MARK):
    s = (root / name).read_bytes().decode('utf-8')
    if mark in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits, mark=MARK):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if mark in s:
        return name + ': already'
    for old0, new0 in edits:
        old, e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))
        s = s.replace(old, new0.replace('\n', e), 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied'


def write_new(name, text, like):
    raw = (root / like).read_bytes()
    nl = '\r\n' if raw.count(b'\r\n') * 2 > raw.count(b'\n') else '\n'
    data = text.replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


def main():
    f3 = (root / 'OmniFeatures3.h').read_bytes().decode('utf-8')
    if 'OMNI_SITE_CLEAR_V1' not in f3 or 'OMNI_MEDIA_CONTROLS_V1' not in f3:
        sys.exit('OmniFeatures3.h: OMNI_SITE_CLEAR_V1 / OMNI_MEDIA_CONTROLS_V1 missing: apply_site_clear.py and apply_media_controls.py first')
    if 'OMNI_SMALL_COMFORTS_V1' not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        sys.exit('OmniBrowser.cpp: OMNI_SMALL_COMFORTS_V1 missing')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniSleepTimer.h', PURE, 'OmniSmallComforts.h'),
            write_new('OmniSleepTimerShell.h', SHELL, 'OmniSiteClearShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
