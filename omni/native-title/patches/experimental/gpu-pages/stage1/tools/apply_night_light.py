#!/usr/bin/env python3
"""OMNI_NIGHT_LIGHT_V1 (2026-11-16): "Night light", a warm tint over everything Omni shows, for the evening.

What the user sees
  - Browser settings, after "Bottom button bar":
        "Night light"          Off / On / Scheduled (on now) / Scheduled (off now)    D-pad left/right or Cross
        "Night light warmth"   1 of 5 .. 5 of 5 (default 3)                            shown unless Off
        "Night light from"     21:00 (hour steps)                                      shown when Scheduled
        "Night light until"    07:00                                                   shown when Scheduled
    The Night light row's detail says what the schedule does now ("On now, until 07:00 (console time 22:14)"), or,
    when the title's GPU present is not running, that the tint needs it (the choice is still saved).
  - Options > Quick toggles: a "Night light" tile (value On / Off / "Scheduled, on now" ...). Cross turns it Off, or
    back to the last mode that was not Off (On by default): a one-press toggle that keeps the schedule.
  - Changes and schedule edges fade over 2 s (smoothstep); at start the current state is applied at once.
  - Saved in /data/omni/night-light.txt (omniIoQueue): mode, last, warmth, start, end.

Where the tint is applied (the cheapest correct place)
  The title's GPU present (OmniGpuPresent.cpp, OMNI_GPU_PRESENT_V1..V4 + OMNI_GPUPAGES_ZEROCOPY_V1) composes every
  frame into one canvas image: the SDL frame (page + panels), the hole-punch's video runs (copied on the GPU) and the
  zero-copy page. tools/apply_night_light_present.py adds one compute pass over that canvas (omni_night_light.comp,
  out = M * rgb). The shell only hands it a 3x3 matrix (omni_gpu_present_night, weak: an engine without it, or a
  title without the pass, does nothing). Off = nullptr: the present records nothing extra (no pass at all).
  Not tinted: HDR10-output video runs (PQ samples written after the pass), and everything when the GPU present is not
  running (SDL's CPU present: no cheap hook; tinting the SDL surface on the CPU would cost a full-frame pass per frame).
  The video plane is NOT a separate system plane here: the hole-punch composites video into Omni's own canvas, so SDR
  video is tinted with the page.

Local time: localtime_r()'s tm_gmtoff when not 0, else /data/omni-downloader/state/tz-offset.json
{"utcOffsetMinutes": n} (written by Omni's downloads page from the page's JS clock, read at most every 10 min), else
UTC. The rows show the console time used, so a wrong clock is visible.

Pure part: engine/entry/OmniNightLight.h (no SDL / WebKit / Vulkan): settings file, schedule (wraps past midnight;
start == end = never), local minute, tz-offset.json, warmth matrices, fade, CPU reference of the shader, texts.
Tested by tools/test_night_light.cpp:  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_night_light.cpp
The present pass: tools/test_night_light_present.cpp (lavapipe).
Shell side: engine/entry/OmniNightLightShell.h (included from OmniFeatures3.h after OmniSiteClearShell.h);
omniNlTick from omniF3Tick (after omniScTick): once a second it re-reads the schedule; during a fade it sends the
matrix each pass and marks the shell dirty so frames are presented.

Row ids: Browser settings 940-943 (omniNlRowMode/Warmth/Start/End; dispatched before the ">= 900" features-2 line),
quick tile 945 (omniNlQuickId; before the ">= 900" features-2 line of omniFxQuickInput; Quick toggles group).
Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp        the OmniSiteClear.h include line (pure include + the two weak title functions, file scope).
  OmniBrowserSettings.h  the omniHoRowId constexpr line (declarations); the "Bottom button bar" row (rows after it);
                         the "r.id >= 900" line of omniFxSettingsInput (handler before it).
  OmniQuickMenu.h        the omniRlQuickAction declaration (declarations); the omniTaQuickTiles call (tile after it);
                         the OmniTabAudio::kTile group case (case after it); the "r.id >= 900" line of
                         omniFxQuickInput (action before it).
  OmniFeatures3.h        the OmniSiteClearShell.h include line; the omniScTick line of omniF3Tick (omniNlTick after it).
Apply AFTER apply_site_clear.py, apply_tab_audio.py and apply_reading_list.py (their lines are anchors).
usage: apply_night_light.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_NIGHT_LIGHT_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_NIGHT_LIGHT_V1: the pure part of "Night light" (no SDL, no WebKit, no Vulkan): the settings file, the schedule
// (local minutes, wrapping past midnight), the warmth matrices, the 2 s fade, and the texts. The shell side is
// OmniNightLightShell.h; the tint itself is the title's GPU present pass (tools/apply_night_light_present.py).
// Tested on the host with g++ (tools/test_night_light.cpp).
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>

namespace OmniNightLight {

constexpr const char* kFileName = "night-light.txt";
constexpr const char* kTzOffsetPath = "/data/omni-downloader/state/tz-offset.json";
constexpr long kMaxFileBytes = 4096;
constexpr int kLevels = 5, kDefaultLevel = 3;
constexpr int kDefaultStart = 21 * 60, kDefaultEnd = 7 * 60, kDay = 24 * 60;
constexpr uint32_t kFadeMs = 2000;
constexpr int kMaxOffsetMinutes = 14 * 60;

enum Mode { kOff = 0, kOn = 1, kScheduled = 2 };

struct Settings {
    Mode mode = kOff;
    Mode last = kOn;                          // what the quick toggle turns back on (never kOff)
    int level = kDefaultLevel;                // warmth 1..5
    int start = kDefaultStart, end = kDefaultEnd;   // minutes of the local day
};

inline int clampLevel(int l) { return std::clamp(l, 1, kLevels); }
inline int wrapMinute(long long m) { m %= kDay; return int(m < 0 ? m + kDay : m); }

inline const char* modeName(Mode m) { return m == kOn ? "On" : m == kScheduled ? "Scheduled" : "Off"; }
inline const char* modeKey(Mode m) { return m == kOn ? "on" : m == kScheduled ? "scheduled" : "off"; }
inline bool modeFromKey(const std::string& s, Mode& m)
{
    if (s == "off") m = kOff; else if (s == "on") m = kOn; else if (s == "scheduled") m = kScheduled; else return false;
    return true;
}
inline std::string hhmm(int minute)
{
    char b[16];
    const int m = wrapMinute(minute);
    snprintf(b, sizeof b, "%02d:%02d", m / 60, m % 60);
    return b;
}
// "21:00", "7:30", "21" (whole hours). false: anything else (the default stays).
inline bool parseHhmm(const std::string& s, int& out)
{
    int h = 0, m = 0; size_t i = 0;
    if (s.empty() || s.size() > 5) return false;
    for (; i < s.size() && s[i] >= '0' && s[i] <= '9'; ++i) h = h * 10 + (s[i] - '0');
    if (i == 0 || i > 2) return false;
    if (i < s.size()) {
        if (s[i] != ':' || s.size() - i != 3) return false;
        for (size_t k = i + 1; k < s.size(); ++k) { if (s[k] < '0' || s[k] > '9') return false; m = m * 10 + (s[k] - '0'); }
    }
    if (h > 23 || m > 59) return false;
    out = h * 60 + m;
    return true;
}

inline std::string serialize(const Settings& s)
{
    return std::string("# Omni night light (OMNI_NIGHT_LIGHT_V1)\nmode\t") + modeKey(s.mode) + "\nlast\t" + modeKey(s.last == kOff ? kOn : s.last)
        + "\nwarmth\t" + std::to_string(clampLevel(s.level)) + "\nstart\t" + hhmm(s.start) + "\nend\t" + hhmm(s.end) + "\n";
}
// Unknown keys, bad values and comments are ignored (each bad value keeps its default).
inline Settings parse(const std::string& text)
{
    Settings s;
    size_t pos = 0;
    while (pos < text.size()) {
        size_t e = text.find('\n', pos);
        if (e == std::string::npos) e = text.size();
        std::string line = text.substr(pos, e - pos);
        pos = e + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty() || line[0] == '#') continue;
        const size_t tab = line.find('\t');
        if (tab == std::string::npos) continue;
        const std::string k = line.substr(0, tab), v = line.substr(tab + 1);
        Mode m;
        int n = 0;
        if (k == "mode" && modeFromKey(v, m)) s.mode = m;
        else if (k == "last" && modeFromKey(v, m) && m != kOff) s.last = m;
        else if (k == "warmth" && v.size() == 1 && v[0] >= '1' && v[0] <= '0' + kLevels) s.level = v[0] - '0';
        else if (k == "start" && parseHhmm(v, n)) s.start = n;
        else if (k == "end" && parseHhmm(v, n)) s.end = n;
    }
    return s;
}

// --- schedule ---------------------------------------------------------------------------------------------------
// [start, end) in local minutes; start > end wraps past midnight (21:00-07:00); start == end is an empty window.
inline bool inWindow(int minute, int start, int end)
{
    minute = wrapMinute(minute); start = wrapMinute(start); end = wrapMinute(end);
    if (start == end) return false;
    return start < end ? (minute >= start && minute < end) : (minute >= start || minute < end);
}
inline bool wantTint(const Settings& s, int minute)
{
    return s.mode == kOn || (s.mode == kScheduled && inWindow(minute, s.start, s.end));
}
// Local minute of the day: UTC seconds + offset seconds east of UTC (floor division: times before 1970 stay right).
inline int localMinute(long long utcSeconds, long long offsetSeconds)
{
    long long t = utcSeconds + offsetSeconds;
    long long days = t / 86400; if (t % 86400 < 0) --days;
    return int((t - days * 86400) / 60);
}
// tz-offset.json: {"utcOffsetMinutes": int} (Omni's downloads page writes it; ENGINE-CONTRACT 11.11). false: unusable.
inline bool parseTzOffsetJson(const std::string& text, int& minutes)
{
    const std::string key = "\"utcOffsetMinutes\"";
    size_t i = text.find(key);
    if (i == std::string::npos) return false;
    i += key.size();
    while (i < text.size() && (text[i] == ' ' || text[i] == '\t' || text[i] == '\r' || text[i] == '\n')) ++i;
    if (i >= text.size() || text[i] != ':') return false;
    ++i;
    while (i < text.size() && (text[i] == ' ' || text[i] == '\t' || text[i] == '\r' || text[i] == '\n')) ++i;
    bool neg = false;
    if (i < text.size() && (text[i] == '-' || text[i] == '+')) { neg = text[i] == '-'; ++i; }
    const size_t d0 = i;
    long v = 0;
    while (i < text.size() && text[i] >= '0' && text[i] <= '9' && i - d0 < 5) v = v * 10 + (text[i++] - '0');
    if (i == d0 || (i < text.size() && ((text[i] >= '0' && text[i] <= '9') || text[i] == '.'))) return false;
    if (neg) v = -v;
    if (v < -kMaxOffsetMinutes || v > kMaxOffsetMinutes) return false;
    minutes = int(v);
    return true;
}
// libc's offset when it knows one (not 0), else the file's, else UTC.
inline long long chooseOffsetSeconds(long long gmtoff, bool fileOk, int fileMinutes)
{
    if (gmtoff != 0) return gmtoff;
    return fileOk ? (long long)fileMinutes * 60 : 0;
}
// The next schedule edge after `minute` (start or end), for the texts.
inline int nextEdge(const Settings& s, int minute) { return inWindow(minute, s.start, s.end) ? s.end : s.start; }

// --- matrices ---------------------------------------------------------------------------------------------------
// Row-major 3x3 over the canvas's stored (gamma-encoded) RGB, as omni_night_light.comp computes out = M * rgb.
struct Mat { float m[9]; };
inline Mat identity() { return Mat { { 1, 0, 0, 0, 1, 0, 0, 0, 1 } }; }
// Warmth 1..5: red kept, green a little lower, blue strongly lower (roughly 5500 K .. 2700 K on a D65 screen).
constexpr float kGains[kLevels][3] = {
    { 1.00f, 0.95f, 0.85f }, { 1.00f, 0.90f, 0.72f }, { 1.00f, 0.85f, 0.60f }, { 1.00f, 0.80f, 0.48f }, { 1.00f, 0.74f, 0.36f } };
inline Mat warmthMatrix(int level)
{
    const float* g = kGains[clampLevel(level) - 1];
    return Mat { { g[0], 0, 0, 0, g[1], 0, 0, 0, g[2] } };
}
inline Mat target(const Settings& s, int minute) { return wantTint(s, minute) ? warmthMatrix(s.level) : identity(); }
inline bool near(const Mat& a, const Mat& b, float eps)
{
    for (int i = 0; i < 9; ++i) if (std::fabs(a.m[i] - b.m[i]) > eps) return false;
    return true;
}
constexpr float kSendEps = 1.0f / 2048;   // smaller steps are not sent again (below one 8-bit level)
inline bool isIdentity(const Mat& m) { return near(m, identity(), 1e-6f); }
inline Mat lerp(const Mat& a, const Mat& b, float t)
{
    Mat o;
    for (int i = 0; i < 9; ++i) o.m[i] = a.m[i] + (b.m[i] - a.m[i]) * t;
    return o;
}
inline float ease(float t) { t = std::clamp(t, 0.0f, 1.0f); return t * t * (3 - 2 * t); }

// The 2 s fade. Times are SDL_GetTicks() milliseconds (wrap-safe differences).
class Fade {
public:
    void snap(const Mat& m) { from_ = to_ = m; active_ = false; }
    // A new target fades from wherever the fade is now; the same target changes nothing.
    void retarget(const Mat& t, uint32_t now)
    {
        if (near(t, to_, 1e-6f)) return;
        from_ = value(now); to_ = t; at_ = now; active_ = true;
    }
    Mat value(uint32_t now) const
    {
        if (!active_) return to_;
        const uint32_t e = now - at_;
        if (e >= kFadeMs) return to_;
        return lerp(from_, to_, ease(float(e) / float(kFadeMs)));
    }
    bool running(uint32_t now) const { return active_ && now - at_ < kFadeMs; }
    const Mat& target() const { return to_; }
private:
    Mat from_ = identity(), to_ = identity();
    uint32_t at_ = 0;
    bool active_ = false;
};

// CPU reference of omni_night_light.comp for one 8-bit pixel (the host test of the present pass uses the same math).
inline void applyPixel(const Mat& m, uint8_t& r, uint8_t& g, uint8_t& b)
{
    const float c[3] = { r / 255.0f, g / 255.0f, b / 255.0f };
    uint8_t o[3];
    for (int i = 0; i < 3; ++i) {
        const float v = m.m[i * 3] * c[0] + m.m[i * 3 + 1] * c[1] + m.m[i * 3 + 2] * c[2];
        o[i] = uint8_t(std::lround(std::clamp(v, 0.0f, 1.0f) * 255.0f));
    }
    r = o[0]; g = o[1]; b = o[2];
}

// --- controls -------------------------------------------------------------------------------------------------
inline Mode cycleMode(Mode m, int dir) { return Mode(((int(m) + (dir < 0 ? 2 : 1)) % 3)); }
inline int stepHour(int minute, int dir) { return wrapMinute((wrapMinute(minute) / 60 + (dir < 0 ? -1 : 1)) * 60); }
inline Settings setMode(Settings s, Mode m) { s.mode = m; if (m != kOff) s.last = m; return s; }
// The quick tile: Off <-> the last mode that was not Off (the schedule is kept).
inline Settings quickToggle(Settings s) { return setMode(s, s.mode == kOff ? (s.last == kOff ? kOn : s.last) : kOff); }

// --- texts ------------------------------------------------------------------------------------------------------
inline std::string modeValue(const Settings& s, int minute)
{
    if (s.mode != kScheduled) return modeName(s.mode);
    return wantTint(s, minute) ? "Scheduled (on now)" : "Scheduled (off now)";
}
inline std::string levelValue(int level) { return std::to_string(clampLevel(level)) + " of " + std::to_string(kLevels); }
inline std::string clockNote(int minute) { return "console time " + hhmm(minute); }
inline std::string modeDetail(const Settings& s, int minute, bool available)
{
    if (!available) return "Needs Omni's GPU display output, which is not running. Saved; it applies when that output is on";
    switch (s.mode) {
    case kOn: return "Warm tint on (" + clockNote(minute) + ")";
    case kScheduled:
        if (wrapMinute(s.start) == wrapMinute(s.end)) return "From and until are the same time: never on";
        return (wantTint(s, minute) ? "On now, until " : "Off now, starts at ") + hhmm(nextEdge(s, minute)) + " (" + clockNote(minute) + ")";
    default: return "Warms the screen in the evening: less blue light";
    }
}
inline std::string tileValue(const Settings& s, int minute)
{
    if (s.mode == kScheduled) return wantTint(s, minute) ? "Scheduled, on" : "Scheduled, off";
    return modeName(s.mode);
}
inline std::string toggleNotice(const Settings& s, int minute, bool available)
{
    std::string t;
    if (s.mode == kOff) t = "Night light off";
    else if (s.mode == kOn) t = "Night light on";
    else t = wantTint(s, minute) ? "Night light on until " + hhmm(s.end) : "Night light scheduled from " + hhmm(s.start);
    if (s.mode != kOff && !available) t += " (needs Omni's GPU display output)";
    return t;
}

} // namespace OmniNightLight
'''

SHELL = r'''// OMNI_NIGHT_LIGHT_V1: "Night light" (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous
// namespace, after OmniSiteClearShell.h). The pure part is OmniNightLight.h; the tint is the title's GPU present pass
// (omni_gpu_present_night, declared weak at file scope in OmniBrowser.cpp); the reasons are in tools/apply_night_light.py.
// Main thread only; the file is written by omniIoQueue.
#pragma once

namespace ONL = OmniNightLight;
static ONL::Settings omniNl;
static bool omniNlLoaded = false;
static ONL::Fade omniNlFade;
static bool omniNlStarted = false, omniNlSent = false;
static ONL::Mat omniNlLastSent = ONL::identity();
static uint32_t omniNlNextCheck = 0;
static bool omniNlTzOk = false;
static int omniNlTzMinutes = 0;
static long long omniNlTzReadAt = LLONG_MIN;

static void omniNlLoad()
{
    if (omniNlLoaded) return;
    omniNlLoaded = true;
    FILE* f = fopen(omniData(ONL::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[1024];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) < ONL::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    omniNl = ONL::parse(text);
}
static void omniNlWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(ONL::kFileName), ONL::serialize(omniNl), false);
}
static bool omniNlAvailable() { return omni_gpu_present_night_ready && omni_gpu_present_night && omni_gpu_present_night_ready() == 1; }
// The local minute of the day (see OmniNightLight.h: libc's offset, else tz-offset.json, else UTC).
static int omniNlMinute()
{
    const time_t now = time(nullptr);
    struct tm tmv {};
    localtime_r(&now, &tmv);
    if ((long long)now - omniNlTzReadAt >= 600 || (long long)now < omniNlTzReadAt) {   // the file at most every 10 min
        omniNlTzReadAt = (long long)now;
        omniNlTzOk = false;
        if (FILE* f = fopen(ONL::kTzOffsetPath, "rb")) {
            char b[256];
            const size_t n = fread(b, 1, sizeof b - 1, f);
            fclose(f);
            omniNlTzOk = ONL::parseTzOffsetJson(std::string(b, n), omniNlTzMinutes);
        }
    }
    return ONL::localMinute((long long)now, ONL::chooseOffsetSeconds((long long)tmv.tm_gmtoff, omniNlTzOk, omniNlTzMinutes));
}
static void omniNlChanged() { omniNlWrite(); omniNlNextCheck = SDL_GetTicks(); }   // the tick fades to it now

// From omniF3Tick (every pass). Off and settled: one comparison. A fade marks the shell dirty so frames are presented.
static void omniNlTick(uint32_t now)
{
    if (!omni_gpu_present_night) return;   // a title without the pass
    omniNlLoad();
    if (!omniNlStarted || int32_t(now - omniNlNextCheck) >= 0) {
        const ONL::Mat t = ONL::target(omniNl, omniNlMinute());
        if (!omniNlStarted) { omniNlFade.snap(t); omniNlStarted = true; }   // at start: the current state at once
        else omniNlFade.retarget(t, now);
        omniNlNextCheck = now + 1000;
    }
    const ONL::Mat m = omniNlFade.value(now);
    if (ONL::isIdentity(m)) {
        if (omniNlSent) { omni_gpu_present_night(nullptr); omniNlSent = false; omniShellDirty = true; }   // no pass from now on
        return;
    }
    if (omniNlSent && ONL::near(m, omniNlLastSent, ONL::kSendEps)) return;
    omni_gpu_present_night(m.m);
    omniNlSent = true; omniNlLastSent = m;
    omniShellDirty = true;   // present a frame with the new tint
}

// --- Browser settings rows ----------------------------------------------------------------------------------------
static void omniNlSettingsRows(OmniFxPanel& p)
{
    omniNlLoad();
    const int minute = omniNlMinute();
    OmniFxRow r; r.id = omniNlRowMode; r.label = "Night light"; r.value = ONL::modeValue(omniNl, minute); r.stepper = true;
    r.detail = ONL::modeDetail(omniNl, minute, omniNlAvailable());
    p.rows.push_back(r);
    if (omniNl.mode == ONL::kOff) return;
    OmniFxRow w; w.id = omniNlRowWarmth; w.label = "Night light warmth"; w.value = ONL::levelValue(omniNl.level); w.stepper = true;
    p.rows.push_back(w);
    if (omniNl.mode != ONL::kScheduled) return;
    OmniFxRow s; s.id = omniNlRowStart; s.label = "Night light from"; s.value = ONL::hhmm(omniNl.start); s.stepper = true;
    p.rows.push_back(s);
    OmniFxRow e; e.id = omniNlRowEnd; e.label = "Night light until"; e.value = ONL::hhmm(omniNl.end); e.stepper = true;
    p.rows.push_back(e);
}
static bool omniNlSettingsInput(int id, int b)
{
    const bool left = b == SDL_CONTROLLER_BUTTON_DPAD_LEFT;
    if (b != SDL_CONTROLLER_BUTTON_A && !left && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    const int dir = left ? -1 : 1;
    omniNlLoad();
    if (id == omniNlRowMode) {
        omniNl = ONL::setMode(omniNl, ONL::cycleMode(omniNl.mode, dir));
        if (omniNl.mode != ONL::kOff && !omniNlAvailable()) notice(ONL::toggleNotice(omniNl, omniNlMinute(), false));
    } else if (id == omniNlRowWarmth) {
        omniNl.level = b == SDL_CONTROLLER_BUTTON_A ? omniNl.level % ONL::kLevels + 1 : ONL::clampLevel(omniNl.level + dir);   // Cross wraps 5 -> 1
    } else if (id == omniNlRowStart) {
        omniNl.start = ONL::stepHour(omniNl.start, dir);
    } else if (id == omniNlRowEnd) {
        omniNl.end = ONL::stepHour(omniNl.end, dir);
    } else {
        return false;
    }
    omniNlChanged();
    return true;
}

// --- Options > Quick toggles tile ---------------------------------------------------------------------------------
static void omniNlQuickTiles(OmniFxPanel& p)
{
    omniNlLoad();
    OmniFxRow r; r.id = omniNlQuickId; r.label = "Night light"; r.value = ONL::tileValue(omniNl, omniNlMinute());
    p.rows.push_back(r);
}
static bool omniNlQuickAction(int id)
{
    if (id != omniNlQuickId) return false;
    omniNlLoad();
    omniNl = ONL::quickToggle(omniNl);
    omniNlChanged();
    notice(ONL::toggleNotice(omniNl, omniNlMinute(), omniNlAvailable()));
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSiteClear.h" // OMNI_SITE_CLEAR_V1: Clear data for this site (pure)\n',
         '#include "OmniSiteClear.h" // OMNI_SITE_CLEAR_V1: Clear data for this site (pure)\n'
         '#include "OmniNightLight.h" // OMNI_NIGHT_LIGHT_V1: Night light schedule, warmth, fade, night-light.txt (pure)\n'
         '// OMNI_NIGHT_LIGHT_V1: the title\'s GPU present pass (tools/apply_night_light_present.py); absent in other titles.\n'
         'extern "C" int omni_gpu_present_night(const float* m) __attribute__((weak));\n'
         'extern "C" int omni_gpu_present_night_ready(void) __attribute__((weak));\n'),
    ],
    'OmniBrowserSettings.h': [
        ('constexpr int omniHoRowId = 890, omniHoGpcRowId = 891; // OMNI_HTTPS_ONLY_V1 (OmniHttpsOnlyShell.h)\n',
         'constexpr int omniHoRowId = 890, omniHoGpcRowId = 891; // OMNI_HTTPS_ONLY_V1 (OmniHttpsOnlyShell.h)\n'
         'constexpr int omniNlRowMode = 940, omniNlRowWarmth = 941, omniNlRowStart = 942, omniNlRowEnd = 943; // OMNI_NIGHT_LIGHT_V1 (OmniNightLightShell.h)\n'
         'static void omniNlSettingsRows(OmniFxPanel& p);\n'
         'static bool omniNlSettingsInput(int id, int b);\n'),
        ('    add(omniFxSetHintBar, "Bottom button bar", omniBarsHidden(false) ? "Hidden" : "Shown", true);\n',
         '    add(omniFxSetHintBar, "Bottom button bar", omniBarsHidden(false) ? "Hidden" : "Shown", true);\n'
         '    omniNlSettingsRows(p); // OMNI_NIGHT_LIGHT_V1: Night light, warmth, from, until\n'),
        ('    if (r.id >= 900) return omniF2SettingsInput(r, b); // OMNI_FEATURES_V2\n',
         '    if (r.id >= omniNlRowMode && r.id <= omniNlRowEnd) return omniNlSettingsInput(r.id, b); // OMNI_NIGHT_LIGHT_V1 (before the >= 900 rows)\n'
         '    if (r.id >= 900) return omniF2SettingsInput(r, b); // OMNI_FEATURES_V2\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniRlQuickAction(int id); // OMNI_READING_LIST_V1\n',
         'static bool omniRlQuickAction(int id); // OMNI_READING_LIST_V1\n'
         'constexpr int omniNlQuickId = 945; // OMNI_NIGHT_LIGHT_V1 (OmniNightLightShell.h): Quick toggles tile\n'
         'static void omniNlQuickTiles(OmniFxPanel& p);\n'
         'static bool omniNlQuickAction(int id);\n'),
        ('    omniTaQuickTiles(p); // OMNI_TAB_AUDIO_V1: Mute this tab / Unmute this tab\n',
         '    omniTaQuickTiles(p); // OMNI_TAB_AUDIO_V1: Mute this tab / Unmute this tab\n'
         '    omniNlQuickTiles(p); // OMNI_NIGHT_LIGHT_V1: Night light\n'),
        ('    case OmniTabAudio::kTile: return 2; // OMNI_TAB_AUDIO_V1: Quick toggles\n',
         '    case OmniTabAudio::kTile: return 2; // OMNI_TAB_AUDIO_V1: Quick toggles\n'
         '    case omniNlQuickId: return 2; // OMNI_NIGHT_LIGHT_V1: Quick toggles\n'),
        ('    if (r.id >= 900) return omniF2QuickInput(r, b); // OMNI_FEATURES_V2\n',
         '    if (omniNlQuickAction(r.id)) return true; // OMNI_NIGHT_LIGHT_V1 (before the >= 900 rows)\n'
         '    if (r.id >= 900) return omniF2QuickInput(r, b); // OMNI_FEATURES_V2\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n',
         '#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n'
         '#include "OmniNightLightShell.h" // OMNI_NIGHT_LIGHT_V1\n'),
        ('    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n',
         '    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n'
         '    omniNlTick(now);    // OMNI_NIGHT_LIGHT_V1: schedule check every second, the 2 s fade\n'),
    ],
}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits):
    s = (root / name).read_bytes().decode('utf-8')
    if MARK in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if MARK in s:
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
    if 'OMNI_SITE_CLEAR_V1' not in (root / 'OmniFeatures3.h').read_bytes().decode('utf-8'):
        sys.exit('OmniFeatures3.h: OMNI_SITE_CLEAR_V1 missing: apply_site_clear.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniNightLight.h', PURE, 'OmniSiteClear.h'),
            write_new('OmniNightLightShell.h', SHELL, 'OmniSiteClearShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
