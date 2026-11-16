// OMNI_PAUSE_INFO_V1: the pure part of the pause info strip (no SDL, no WebKit). When a full-screen video has been paused
// for kDelayMs, a TV-player info strip shows: the video's title, the local time, position / duration with a bar, the time
// left and "Ends at 22:41". The strip IS the video keys OSD (OMNI_VIDEO_KEYS_V1's OmniVideoKeys::Osd, drawn by its
// omniVkOsdDraw): this header only fills its fields. The page script is the video keys' own read-only script (kInfo:
// the full-screen video, same-origin frames walked) plus the Media Session title. Shell side: OmniPauseInfoShell.h
// (written by tools/apply_pause_info.py, which also has the reasons). Tested with g++ (tools/test_pause_info.cpp) and
// node (tools/test_pause_info.cjs runs the script against a fake DOM).
#pragma once
#include "OmniVideoKeys.h"
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <string>

namespace OmniPauseInfo {

namespace OVK = OmniVideoKeys;

constexpr uint32_t kDelayMs = 1500;                      // paused this long (and idle) before the strip shows
constexpr uint32_t kFadeMs = 200;                        // fade in (Reduce motion: none, it is there at once)
constexpr uint32_t kHoldMs = 12u * 3600u * 1000u;        // the OSD's "until" while shown (renewed every minute)
constexpr size_t kTitleMax = 300;                        // bytes of title kept (the pill cuts it to its width)
constexpr int kDay = 24 * 60;                            // minutes
constexpr double kEndSlack = 0.5;                        // within this of the end: the video ended, no strip

// Fade-in opacity 0..1, sinceMs after the strip appeared.
inline uint32_t fadeMs(bool reduce) { return reduce ? 0u : kFadeMs; }
inline float fadeT(bool reduce, uint32_t sinceMs)
{
    const uint32_t d = fadeMs(reduce);
    return d == 0 || sinceMs >= d ? 1.f : float(sinceMs) / float(d);
}

// Minute of the day -> "22:41" (24-hour, wraps: -1 -> "23:59", 1440 -> "00:00").
inline std::string hhmm(long long minuteOfDay)
{
    long long m = minuteOfDay % kDay;
    if (m < 0) m += kDay;
    char b[8];
    std::snprintf(b, sizeof b, "%02d:%02d", int(m / 60), int(m % 60));
    return b;
}

// Seconds of media left; -1 when unknown (no duration, a live stream, no position).
inline double remaining(const OVK::Info& i)
{
    if (!i.ok || i.state == OVK::sNone || !(i.duration > 0) || !std::isfinite(i.duration)) return -1;
    const double pos = i.position >= 0 ? i.position : 0;
    const double r = i.duration - pos;
    return r > 0 ? r : 0;
}

// The minute of the day the video ends when play resumes now: now (local minute + second) plus the time left at the
// current speed (rate <= 0 or unknown: 1x), rounded to the nearest minute. -1: unknown, or more than a day away.
inline int endsAtMinute(int nowMinute, int nowSecond, double remainingSeconds, double rate)
{
    if (!(remainingSeconds >= 0) || !std::isfinite(remainingSeconds)) return -1;
    const double speed = rate > 0 && std::isfinite(rate) ? rate : 1.0;
    const double wall = remainingSeconds / speed;
    if (wall > 86400.0) return -1;
    const double end = double(nowMinute) * 60.0 + double(nowSecond) + wall;
    long long m = static_cast<long long>(std::floor((end + 30.0) / 60.0)) % kDay;
    if (m < 0) m += kDay;
    return int(m);
}

// "33:05 left   Ends at 22:41"; "Live" for streams; "" when nothing is known.
inline std::string leftLine(const OVK::Info& i, int nowMinute, int nowSecond)
{
    if (!i.ok || i.state == OVK::sNone) return std::string();
    if (i.duration == OVK::kLive) return "Live";
    const double left = remaining(i);
    if (left < 0) return std::string();
    std::string s = OVK::clock(left) + " left";
    const int end = endsAtMinute(nowMinute, nowSecond, left, i.rate);
    if (end >= 0) s += "   Ends at " + hhmm(end);
    return s;
}

// --- the page script --------------------------------------------------------------------------------------------
// The video keys' read-only press (R3's kInfo: acts on nothing) wrapped so its answer gets the Media Session title first:
// "omni-pzi1\n<title>\n<the omni-vk1 answer>". One evaluate when the pause has lasted kDelayMs.
constexpr const char* kHead = R"JS((function(){var r=)JS";
constexpr const char* kTail = R"JS(;var t='';try{var m=navigator.mediaSession&&navigator.mediaSession.metadata;if(m&&m.title)t=String(m.title);}catch(e){}
return 'omni-pzi1\n'+t.replace(/[\r\n\t]+/g,' ').slice(0,300)+'\n'+r;})())JS";
inline std::string script()
{
    return std::string(kHead) + OVK::script(OVK::plan(OVK::pR3, false)) + kTail;
}

// --- the answer -------------------------------------------------------------------------------------------------
struct Answer {
    bool ok = false;
    std::string title;   // Media Session title ("" none)
    OVK::Info info;
};
inline Answer parse(const std::string& text)
{
    Answer a;
    const size_t n1 = text.find('\n');
    if (n1 == std::string::npos || text.compare(0, n1, "omni-pzi1") != 0) return a;
    const size_t n2 = text.find('\n', n1 + 1);
    if (n2 == std::string::npos) return a;
    a.title = text.substr(n1 + 1, n2 - n1 - 1);
    a.info = OVK::parse(text.substr(n2 + 1));
    a.ok = a.info.ok;
    return a;
}

// The strip shows only for a paused video that has not ended, with no resume prompt up (the video keys OSD has that).
inline bool shows(const Answer& a)
{
    const OVK::Info& i = a.info;
    if (!a.ok || i.state != OVK::sPaused || !i.resumeAt.empty()) return false;
    if (i.duration > 0 && i.position >= 0 && i.position >= i.duration - kEndSlack) return false;
    return true;
}

// Control characters as spaces, outer spaces trimmed, at most kTitleMax bytes (never cutting a UTF-8 sequence).
inline std::string cleanTitle(const std::string& s)
{
    std::string o;
    for (unsigned char c : s) o += (c < 0x20 || c == 0x7f) ? ' ' : char(c);
    size_t a = 0, b = o.size();
    while (a < b && o[a] == ' ') ++a;
    while (b > a && o[b - 1] == ' ') --b;
    o = o.substr(a, b - a);
    if (o.size() > kTitleMax) {
        size_t n = kTitleMax;
        while (n > 0 && (static_cast<unsigned char>(o[n]) & 0xC0) == 0x80) --n;
        o = o.substr(0, n);
    }
    return o;
}
// The Media Session title, else the tab's title, else "Paused".
inline std::string displayTitle(const std::string& metaTitle, const std::string& tabTitle)
{
    std::string t = cleanTitle(metaTitle);
    if (t.empty()) t = cleanTitle(tabTitle);
    return t.empty() ? std::string("Paused") : t;
}

// The strip, as the video keys OSD: title row (title left, local time right), the bar with "12:05 / 45:10" (the video
// keys' own clock and fraction, from its osd()), then "33:05 left   Ends at 22:41" on the pill's second line.
inline OVK::Osd strip(const Answer& a, const std::string& tabTitle, int nowMinute, int nowSecond)
{
    OVK::Osd o = OVK::osd(OVK::plan(OVK::pR3, false), a.info, OVK::fbNone);
    o.title = displayTitle(a.title, tabTitle);
    o.right = hhmm(nowMinute);
    o.resume = leftLine(a.info, nowMinute, nowSecond);
    return o;
}

// Milliseconds until the local minute changes (nowSecond 0..59), plus a little so the new minute has begun.
inline uint32_t msToNextMinute(int nowSecond)
{
    const int s = nowSecond < 0 ? 0 : nowSecond > 59 ? 59 : nowSecond;
    return uint32_t(60 - s) * 1000u + 50u;
}

} // namespace OmniPauseInfo
