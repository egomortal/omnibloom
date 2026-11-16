#!/usr/bin/env python3
"""OMNI_SMALL_COMFORTS_V1 (2026-11-16): three small comforts for the TV.

1. Sleep timer. Options menu tile "Sleep timer" (value "Off" or "N min left"); Cross steps Off -> 15 -> 30 -> 60 ->
   90 min -> Off (each choice starts now; the menu stays open). A notice a minute before ("Sleep timer: pausing
   playback in 1 minute"); then every tab's main frame runs a tiny script that pauses each playing <video>/<audio>
   (also in same-origin frames), the notice "Sleep timer: paused playback" shows and the timer turns off. WebKit's C
   API has no pause-all call (WKPagePrivate.h: only WKPageSetMuted / WKPageGetMediaState), so 3 s later a tab that
   still reports playing audio or video (a cross-origin embedded player the script cannot reach) is muted with
   WKPageSetMuted; the next button / key / click unmutes those tabs ("Sleep timer: sound back on"). Not saved:
   a restart starts with the timer off.
2. Controller battery. A small battery (outline + 0-3 bars) in the top bar between the "+" tab button and "Ad block",
   for the active controller: SDL2 SDL_JoystickCurrentPowerLevel(SDL_GameControllerGetJoystick(controller)). Hidden
   when SDL says unknown or wired (and with no controller). Empty is red, low amber. Asked at most every 30 s (and
   at most every 2 s when another controller becomes the active one); a change marks the shell dirty. No allocation.
3. "Downloaded: <title>". The Downloads worker (downloads/worker/worker.py, OMNI_SMALL_COMFORTS_V1) writes
   /data/omni/downloads-done.txt ("job id<TAB>title", newest last, at most 8, atomic replace) when a real job
   completes. With Media downloads on, Omni stat()s it every 5 s on the main loop (no thread, no socket) and reads it
   (<= 4 KiB) only when its stamp changes; each new job id gives one notice, unless the Downloads tab is the one in
   front (then it is only recorded). What the file held when Omni started is never announced.
   Why not polling /api/status: that route needs the per-run X-Omni-Token, which the worker only puts into the
   Downloads page HTML; Omni would have to scrape it from a page (and the status JSON outgrows the shell's 4 KiB
   loopback reader). The file needs no token, no socket and no thread.
The pure logic (timer, battery bars and throttle, done-file parse and once-per-id tracker) is
engine/entry/OmniSmallComforts.h (no SDL, no WebKit), tested by test_small_comforts.cpp.

Anchors (none shared with apply_site_zoom / apply_file_downloads / apply_grabber_suspects; OmniQuickMenu.h: not
the zoom tiles nor the start of omniFxQuickInput that apply_site_zoom edits):
  OmniBrowser.cpp  '#include "OmniEngineState.h"', the top bar's "// uBlock status: shield" comment,
                   '#include "OmniFeatures.h" // OMNI_FEATURES_V1', the omniSavedLinksTick() call in tick(),
                   'omniChromeEvent(event); // OMNI_STYLE_V1' in the event loop
  OmniQuickMenu.h  the "Browser tools" tile, the "case omniQmDownloads:" line of the stay-open switch
usage: apply_small_comforts.py <engine tree>   (writes engine/entry/OmniSmallComforts.h; edits OmniBrowser.cpp and
OmniQuickMenu.h; each anchor exactly once; idempotent; keeps CRLF)
"""
import sys
from pathlib import Path

MARK = 'OMNI_SMALL_COMFORTS_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

HEADER = r'''// OMNI_SMALL_COMFORTS_V1: the pure part (no SDL, no WebKit) of three small comforts:
//   - SleepTimer: Off / 15 / 30 / 60 / 90 min from the Options menu; a warning 1 minute before, then it fires once
//     (the shell pauses all media) and turns itself off. Not saved: a restart starts with it off.
//   - BatteryGauge: the active controller's battery as 0-3 bars for the top bar; -1 hides it (unknown, wired, or
//     SDL's MAX). Asked at most every 30 s (and at most every 2 s when the active controller changes).
//   - DoneTracker: /data/omni/downloads-done.txt, written by the Downloads worker (one "job id<TAB>title" line per
//     finished download, newest last, at most 8). The shell checks the file's stamp every 5 s and shows
//     "Downloaded: <title>" once per job id. What the file held when Omni started is never announced.
// Times are SDL_GetTicks() milliseconds (uint32_t), compared wrap-safe. Tested with g++ (test_small_comforts.cpp).
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

namespace OmniSmallComforts {

inline bool reached(uint32_t now, uint32_t at) { return int32_t(now - at) >= 0; }

// --- sleep timer ---------------------------------------------------------------------------------
constexpr int kSleepSteps[] = { 0, 15, 30, 60, 90 };
constexpr int kSleepStepCount = int(sizeof(kSleepSteps) / sizeof(kSleepSteps[0]));
constexpr uint32_t kSleepWarnMs = 60u * 1000u;

class SleepTimer {
public:
    enum class Event { None, Warn, Fire };
    bool on() const { return step_ != 0; }
    int minutes() const { return kSleepSteps[step_]; }
    // The next choice (Off -> 15 -> 30 -> 60 -> 90 -> Off), started now. Returns its minutes (0: off).
    int cycle(uint32_t now) { step_ = (step_ + 1) % kSleepStepCount; start(now); return minutes(); }
    // Set a choice by minutes (one of the steps; anything else turns it off).
    void set(int minutes, uint32_t now)
    {
        step_ = 0;
        for (int i = 1; i < kSleepStepCount; ++i) if (kSleepSteps[i] == minutes) step_ = i;
        start(now);
    }
    void off() { step_ = 0; warned_ = false; }
    // Once per tick. Fire: the time is up (the timer is off afterwards). Warn: once, a minute before (not for a timer
    // that is already within its last minute when it starts).
    Event tick(uint32_t now)
    {
        if (!on()) return Event::None;
        if (reached(now, deadline_)) { off(); return Event::Fire; }
        if (!warned_ && reached(now + kSleepWarnMs, deadline_)) { warned_ = true; return Event::Warn; }
        return Event::None;
    }
    // Whole minutes left, rounded up (0 when off).
    int minutesLeft(uint32_t now) const
    {
        if (!on()) return 0;
        const int32_t left = int32_t(deadline_ - now);
        return left <= 0 ? 0 : int((uint32_t(left) + 59999u) / 60000u);
    }
    // The Options menu value: "Off", "1 min left" ... "90 min left".
    void value(uint32_t now, char* out, size_t size) const
    {
        if (!size) return;
        if (!on()) std::snprintf(out, size, "Off");
        else std::snprintf(out, size, "%d min left", minutesLeft(now) < 1 ? 1 : minutesLeft(now));
    }

private:
    void start(uint32_t now)
    {
        warned_ = false;
        deadline_ = now + uint32_t(minutes()) * 60000u;
        if (on() && minutes() * 60000u <= kSleepWarnMs) warned_ = true;
    }
    int step_ = 0;
    bool warned_ = false;
    uint32_t deadline_ = 0;
};

// --- controller battery --------------------------------------------------------------------------
// SDL2's SDL_JoystickPowerLevel: -1 unknown, 0 empty (<= 5 %), 1 low (<= 20 %), 2 medium (<= 70 %), 3 full, 4 wired,
// 5 max (not a level). Bars: 0 empty .. 3 full; -1: not shown.
constexpr int kPowerUnknown = -1, kPowerEmpty = 0, kPowerLow = 1, kPowerMedium = 2, kPowerFull = 3, kPowerWired = 4, kPowerMax = 5;
inline int batteryBars(int level) { return level >= kPowerEmpty && level <= kPowerFull ? level : -1; }

class BatteryGauge {
public:
    static constexpr uint32_t kEveryMs = 30000, kSwitchMs = 2000;
    // Whether the shell should ask SDL now: never asked, 30 s since the last ask, or another active controller (and
    // 2 s since the last ask, so a pad tug-of-war cannot ask every frame).
    bool due(uint32_t now, const void* pad) const
    {
        if (!asked_) return true;
        const uint32_t since = now - askedAt_;
        return since >= kEveryMs || (pad != pad_ && since >= kSwitchMs);
    }
    // The answer (an SDL power level; kPowerUnknown when no controller). True when the drawn bars change.
    bool update(uint32_t now, const void* pad, int level)
    {
        asked_ = true; askedAt_ = now; pad_ = pad;
        const int bars = pad ? batteryBars(level) : -1;
        if (bars == bars_) return false;
        bars_ = bars;
        return true;
    }
    int bars() const { return bars_; }   // -1: hidden

private:
    bool asked_ = false;
    uint32_t askedAt_ = 0;
    const void* pad_ = nullptr;
    int bars_ = -1;
};
inline BatteryGauge& battery() { static BatteryGauge gauge; return gauge; }

// --- "Downloaded: <title>" -----------------------------------------------------------------------
constexpr size_t kDoneMaxFile = 4096, kDoneMaxEntries = 8, kDoneMaxId = 64, kDoneMaxTitle = 80, kDoneSeen = 32;
struct DoneEntry { std::string id, title; };

// Cut to at most `max` bytes without splitting a UTF-8 sequence; "..." when cut.
inline std::string clipUtf8(const std::string& s, size_t max)
{
    if (s.size() <= max) return s;
    size_t end = max >= 3 ? max - 3 : 0;
    while (end > 0 && (static_cast<unsigned char>(s[end]) & 0xC0) == 0x80) --end;
    return s.substr(0, end) + "...";
}
inline bool doneIdValid(const std::string& id)
{
    if (id.empty() || id.size() > kDoneMaxId) return false;
    for (unsigned char c : id)
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_')) return false;
    return true;
}
// "id<TAB>title" lines (any line ending); bad lines skipped; the newest kDoneMaxEntries kept, oldest first.
inline std::vector<DoneEntry> parseDone(const std::string& text)
{
    std::vector<DoneEntry> out;
    const size_t n = text.size() < kDoneMaxFile ? text.size() : kDoneMaxFile;
    size_t at = 0;
    while (at < n) {
        size_t nl = text.find('\n', at);
        if (nl == std::string::npos || nl > n) nl = n;
        std::string line = text.substr(at, nl - at);
        at = nl + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        const size_t tab = line.find('\t');
        if (tab == std::string::npos) continue;
        DoneEntry e;
        e.id = line.substr(0, tab);
        if (!doneIdValid(e.id)) continue;
        for (size_t i = tab + 1; i < line.size(); ++i) {
            const unsigned char c = static_cast<unsigned char>(line[i]);
            e.title += c < 0x20 || c == 0x7F ? ' ' : char(c);
        }
        const size_t a = e.title.find_first_not_of(' '), b = e.title.find_last_not_of(' ');
        e.title = a == std::string::npos ? std::string() : e.title.substr(a, b - a + 1);
        if (e.title.empty()) e.title = "a download";
        e.title = clipUtf8(e.title, kDoneMaxTitle);
        for (auto it = out.begin(); it != out.end(); ++it) if (it->id == e.id) { out.erase(it); break; }
        out.push_back(std::move(e));
        if (out.size() > kDoneMaxEntries) out.erase(out.begin());
    }
    return out;
}

// What stat() says about the file; a change of any field means "read it again".
struct FileStamp {
    bool exists = false;
    int64_t mtime = 0, size = 0;
    uint64_t inode = 0;
    bool operator==(const FileStamp& o) const { return exists == o.exists && mtime == o.mtime && size == o.size && inode == o.inode; }
};

class DoneTracker {
public:
    // True when the file should be read (the first check, or the stamp changed).
    bool restamp(const FileStamp& stamp)
    {
        if (checked_ && stamp == stamp_) return false;
        checked_ = true; stamp_ = stamp;
        return true;
    }
    // The file's entries after a change. The first call only records them (Omni just started). Otherwise: the notice
    // for entries not seen before ("" for none), or "" with them recorded when `announce` is false (the user is on the
    // Downloads tab and sees it there).
    std::string take(const std::vector<DoneEntry>& entries, bool announce)
    {
        std::vector<const DoneEntry*> fresh;
        for (const auto& e : entries) if (!seen(e.id)) { fresh.push_back(&e); remember(e.id); }
        if (!primed_) { primed_ = true; return {}; }
        if (fresh.empty() || !announce) return {};
        std::string text = "Downloaded: " + fresh.back()->title;
        if (fresh.size() > 1) text += " (and " + std::to_string(fresh.size() - 1) + " more)";
        return text;
    }

private:
    bool seen(const std::string& id) const { for (const auto& s : seen_) if (s == id) return true; return false; }
    void remember(const std::string& id)
    {
        if (seen_.size() >= kDoneSeen) seen_.erase(seen_.begin());
        seen_.push_back(id);
    }
    bool checked_ = false, primed_ = false;
    FileStamp stamp_;
    std::vector<std::string> seen_;
};

} // namespace OmniSmallComforts
'''

PAUSE_JS = ("(function(){var n=0;function p(d,k){if(!d||k>3)return;try{var m=d.querySelectorAll('video,audio');"
            "for(var i=0;i<m.length;i++){if(!m[i].paused){try{m[i].pause();n++;}catch(e){}}}"
            "var f=d.querySelectorAll('iframe,frame');for(var j=0;j<f.length;j++){var c=null;try{c=f[j].contentDocument;}catch(e){}p(c,k+1);}"
            "}catch(e){}}p(document,0);return n;})()")

GLUE = r'''// OMNI_SMALL_COMFORTS_V1: sleep timer, controller battery, "Downloaded: <title>" (pure parts: OmniSmallComforts.h).
constexpr int omniQmSleep = 700; // Options menu tile id (the menu's own ids end below 30; OMNI_FEATURES_V3 301+, V2 900+)
static OmniSmallComforts::SleepTimer omniSleep;
static std::vector<WKPageRef> omniSleepMuted;   // tabs muted because the pause script could not stop them
static uint32_t omniSleepCheckAt = 0;
static std::string omniSleepValue()
{
    char text[24];
    omniSleep.value(SDL_GetTicks(), text, sizeof(text));
    return text;
}
static void omniSleepCycle()
{
    const int minutes = omniSleep.cycle(SDL_GetTicks());
    notice(minutes ? "Sleep timer: playback pauses in " + std::to_string(minutes) + " min" : std::string("Sleep timer off"));
    omniShellDirty = true;
}
static void omniSleepPauseAll(uint32_t now)
{
    // WebKit's C API has no "pause all media": a script per tab (main frame; same-origin frames from there).
    static const char* source = "@PAUSE_JS@";
    auto script = adoptWK(WKStringCreateWithUTF8CString(source));
    for (auto& t : tabs)
        if (t->page && !t->crashed) WKPageEvaluateJavaScriptInMainFrame(t->page, script.get(), nullptr, [](WKTypeRef, WKErrorRef, void*) { });
    omniSleepCheckAt = (now + 3000) | 1;
}
static void omniSleepTick(uint32_t now)
{
    switch (omniSleep.tick(now)) {
    case OmniSmallComforts::SleepTimer::Event::Warn: notice("Sleep timer: pausing playback in 1 minute"); break;
    case OmniSmallComforts::SleepTimer::Event::Fire: omniSleepPauseAll(now); notice("Sleep timer: paused playback"); omniShellDirty = true; break;
    default: break;
    }
    if (!omniSleepCheckAt || !OmniSmallComforts::reached(now, omniSleepCheckAt)) return;
    omniSleepCheckAt = 0;
    for (auto& t : tabs)   // still playing (a cross-origin player): silence it until the user is back
        if (t->page && !t->crashed && (WKPageGetMediaState(t->page) & (kWKMediaIsPlayingAudio | kWKMediaIsPlayingVideo))) {
            WKPageSetMuted(t->page, kWKMediaAudioMuted);
            omniSleepMuted.push_back(t->page);
        }
}
static void omniSleepWake(uint32_t type)   // every SDL event; returns at once unless a tab was muted
{
    if (omniSleepMuted.empty() || (type != SDL_CONTROLLERBUTTONDOWN && type != SDL_KEYDOWN && type != SDL_MOUSEBUTTONDOWN)) return;
    for (auto& t : tabs)
        for (WKPageRef page : omniSleepMuted) if (t->page == page) WKPageSetMuted(page, kWKMediaNoneMuted);   // only tabs still open
    omniSleepMuted.clear();
    notice("Sleep timer: sound back on");
}
static_assert(SDL_JOYSTICK_POWER_UNKNOWN == OmniSmallComforts::kPowerUnknown && SDL_JOYSTICK_POWER_EMPTY == OmniSmallComforts::kPowerEmpty
    && SDL_JOYSTICK_POWER_FULL == OmniSmallComforts::kPowerFull && SDL_JOYSTICK_POWER_WIRED == OmniSmallComforts::kPowerWired, "SDL2 power levels");
static void omniBatteryTick(uint32_t now)
{
    auto& gauge = OmniSmallComforts::battery();
    if (!gauge.due(now, controller)) return;
    int level = SDL_JOYSTICK_POWER_UNKNOWN;
    if (controller) if (SDL_Joystick* joystick = SDL_GameControllerGetJoystick(controller)) level = int(SDL_JoystickCurrentPowerLevel(joystick));
    if (gauge.update(now, controller, level)) omniShellDirty = true;
}
static void omniDownloadsDoneTick(uint32_t now)
{
    static constexpr const char* path = "/data/omni/downloads-done.txt";
    static OmniSmallComforts::DoneTracker tracker;
    static uint32_t checkedAt = 0;
    static bool checked = false;
    if (!omniMediaDownloadsEnabled || (checked && now - checkedAt < 5000)) return;
    checked = true; checkedAt = now;
    struct stat st {};
    OmniSmallComforts::FileStamp stamp;
    if (!stat(path, &st) && S_ISREG(st.st_mode)) stamp = { true, int64_t(st.st_mtime), int64_t(st.st_size), uint64_t(st.st_ino) };
    if (!tracker.restamp(stamp)) return;
    std::string text;
    if (stamp.exists) {
        if (FILE* f = fopen(path, "rb")) {
            char buffer[OmniSmallComforts::kDoneMaxFile];
            text.assign(buffer, fread(buffer, 1, sizeof(buffer), f));
            fclose(f);
        }
    }
    const bool onDownloads = active() && omniMediaOwns(*active());
    const std::string message = tracker.take(OmniSmallComforts::parseDone(text), !onDownloads);
    if (!message.empty()) notice(message);
}
static void omniSmallComfortsTick()
{
    if (omniTestMode()) return;
    const uint32_t now = SDL_GetTicks();
    omniSleepTick(now);
    omniBatteryTick(now);
    omniDownloadsDoneTick(now);
}
'''

BATTERY_DRAW = r'''    {   // OMNI_SMALL_COMFORTS_V1: the active controller's battery (hidden when unknown or wired)
        const int bars = OmniSmallComforts::battery().bars();
        if (bars >= 0) {
            const SDL_Color c = bars == 0 ? omniBad : bars == 1 ? omniWarn : T.inkDim;
            fillRounded(1130, 23, 17, 12, 2, c);
            fillRounded(1131, 24, 15, 10, 1, T.bg);
            fill(1147, 26, 2, 6, c);
            for (int i = 0; i < bars; ++i) fill(1132 + i * 5, 25, 4, 8, c);
        }
    }
'''

BROWSER = [
    ('#include "OmniEngineState.h"\n',
     '#include "OmniEngineState.h"\n'
     '#include "OmniSmallComforts.h" // ' + MARK + ': sleep timer, battery bars, downloads-done file (pure)\n'),
    # review 2026-11-16: the launch title's top bar has no shield (OMNI_MQ_NATIVE_V1 moved uBlock to the quick-access
    # row); the battery goes in the free top-right space, before that comment.
    ('    // OMNI_MQ_NATIVE_V1: global uBlock lives in the shared quick-access row.\n',
     BATTERY_DRAW + '    // OMNI_MQ_NATIVE_V1: global uBlock lives in the shared quick-access row.\n'),
    ('#include "OmniFeatures.h" // OMNI_FEATURES_V1\n',
     GLUE.replace('@PAUSE_JS@', PAUSE_JS) + '#include "OmniFeatures.h" // OMNI_FEATURES_V1\n'),
    ('    omniSavedLinksTick(); // OMNI_SAVED_LINKS_V1: no I/O or DOM scan.\n',
     '    omniSavedLinksTick(); // OMNI_SAVED_LINKS_V1: no I/O or DOM scan.\n'
     '    omniSmallComfortsTick(); // ' + MARK + ': sleep timer, controller battery (<= every 30 s), downloads-done stamp (every 5 s)\n'),
    ('        omniChromeEvent(event); // OMNI_STYLE_V1\n',
     '        omniChromeEvent(event); // OMNI_STYLE_V1\n'
     '        omniSleepWake(event.type); // ' + MARK + ': unmute tabs the sleep timer muted\n'),
]
QUICK = [
    ('    add(omniQmTools, "Browser tools", true);\n',
     '    add(omniQmSleep, "Sleep timer", true, -1, omniSleepValue()); // ' + MARK + '\n'
     '    add(omniQmTools, "Browser tools", true);\n'),
    ('    case omniQmDownloads: omniFxDownloadsShow(); return true;\n',
     '    case omniQmDownloads: omniFxDownloadsShow(); return true;\n'
     '    case omniQmSleep: omniSleepCycle(); return true; // ' + MARK + ': Off / 15 / 30 / 60 / 90 min\n'),
]


def patch(name, edits):
    p = root / name
    raw = p.read_bytes()
    nl = '\r\n' if b'\r\n' in raw else '\n'
    s = raw.decode('utf-8')
    if MARK in s:
        return name + ': already', nl
    for old0, new0 in edits:
        # files with mixed endings (lines added by earlier patches): the anchor's own line ending decides
        for e in (nl, '\n' if nl == '\r\n' else '\r\n'):
            old, new = old0.replace('\n', e), new0.replace('\n', e)
            if s.count(old):
                break
        n = s.count(old)
        if n != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, n, old0[:90]))
        s = s.replace(old, new, 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied', nl


def main():
    for name in ('OmniBrowser.cpp', 'OmniQuickMenu.h'):   # check every anchor before writing anything
        s = (root / name).read_text(encoding='utf-8')
        if MARK in s:
            continue
        for old, _ in (BROWSER if name == 'OmniBrowser.cpp' else QUICK):
            if s.replace('\r\n', '\n').count(old) != 1:
                sys.exit('%s: anchor not found exactly once: %r' % (name, old[:90]))
    msg, nl = patch('OmniBrowser.cpp', BROWSER)
    print(msg)
    print(patch('OmniQuickMenu.h', QUICK)[0])
    h = root / 'OmniSmallComforts.h'
    data = HEADER.replace('\n', nl).encode('utf-8')
    if not h.exists() or h.read_bytes() != data:
        h.write_bytes(data)
        print('OmniSmallComforts.h: written')
    else:
        print('OmniSmallComforts.h: already')
    print('applied ' + MARK)


main()
