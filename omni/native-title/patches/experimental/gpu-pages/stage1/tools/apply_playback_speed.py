#!/usr/bin/env python3
"""OMNI_PLAYBACK_SPEED_V1 (2026-11-16): playback speed for the playing video / audio: 0.5x 0.75x 1x 1.25x 1.5x 1.75x 2x.

What the user sees
  - "Now playing" (OMNI_MEDIA_CONTROLS_V1) gets a stepper row "Speed  < 1x >" after "Forward 10 seconds".
    D-pad left / right: one step slower / faster (stops at 0.5x / 2x); Cross: the next speed (2x wraps to 0.5x).
    Notice: "Speed: 1.5x" (the multiplication sign is U+00D7, DejaVu has it).
  - Fullscreen video: the TOUCHPAD press is the next speed (same wrap) for the active tab. Checked free: the fullscreen
    branch of button() maps Cross, Circle, Options, Create, Square, Triangle, L1, R1, L3 and the D-pad (OMNI_FULLSCREEN_KEYS_V1);
    L2 alone is the saved-links tap, L2 chords and OMNI_QUICK_ACTIONS_V1's L2 + R3 are off in fullscreen, YouTube TV's keys
    are D-pad / Cross / Circle; R3 is also free there but closes the tab outside fullscreen, so the touchpad (translate
    outside fullscreen, harmless) was taken. Its notice is not drawn while the presenter owns a hole-punched fullscreen
    video (omniVideoOwnsScreen hides toasts): the speed change itself is the feedback there.
  - The speed is remembered per site (per tab for pages without an http(s) host; private tabs separately) for the
    session only - memory, never written. When a tab of that site starts playing again (WebKit's isPlayingAudioDidChange,
    rising edge of audio / video playing - no page loop, no timer), the speed is applied again with one script: YouTube
    puts playbackRate back to its own value on every new video.

How
  One WKPageEvaluateJavaScriptInMainFrame per press in the tab (ForceUserGesture, as media controls). The script sets
  preservesPitch (+ webkitPreservesPitch) true, defaultPlaybackRate and playbackRate on every <video>/<audio> with a
  source (main frame + same-origin frames to depth 3, media controls' walk), and calls YouTube's player API
  document.getElementById('movie_player').setPlaybackRate(r) when present (first, so YouTube's own state agrees).
  It answers "omni-sp1\n<set>\n<skipped>\n<youtube>\n<found>". Only numbers go into the script (clamped to a step,
  printed with %.2f), no page or user text, so no string escaping is needed; MC::jsString stays the escaper if a string
  is ever added. Cross-origin frames (embedded players) are not reachable, as for media controls.

Omni's own players (HW path) - checked in the tree:
  OMNI_PLAYBACK_RATE_V1 (media/OmniPlaybackRate.h) already gives the MSE (hole-punch / HW decode), native HLS and plain
  file players playbackRate 0.25 .. 2.0 with a pitch-keeping WSOLA time-stretch; the playhead and the shell's clock run
  at the rate. Two cases where it does not:
    * /data/omni/playback-rate-disabled.flag (env OMNI_PLAYBACK_RATE=0): every player stays at 1 -> the row shows "Not
      available" and a press shows "Speed not available for this video"; no script runs.
    * /data/omni/holepunch-v5-disabled.flag (env OMNI_HOLEPUNCH_V5=0): an MSE player that ends on V4's SDL queue (no audio
      ring: relay unavailable) drops its audio at a rate other than 1 (OmniMSEPlayer.cpp "plays rate 1 only: muted
      otherwise"). The shell cannot see which output a player got, so with that flag MSE elements (blob: / srcObject)
      are left at their speed (and YouTube's API is not called); if nothing else could be set the notice is
      "Speed not available for this video". Going back to 1x is always applied.
  The flags are read with access() at most once per 10 s (the players read them when they are created).

Pure part: engine/entry/OmniPlaybackSpeed.h (no SDL / WebKit): steps, labels, notices, the capability rule, the
per-site memory, the playing edge, the script and its answer. Tested by tools/test_playback_speed.cpp:
  g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_playback_speed.cpp -o t && ./t <dir>
  (writes the scripts to <dir>) + node --check / node tools/test_playback_speed.cjs <dir> (runs them on a fake DOM).
Shell side: engine/entry/OmniPlaybackSpeedShell.h (included from OmniFeatures3.h just before OmniMediaControlsShell.h).

Anchors (exactly once each; MARK makes each file idempotent; all insert-before / insert-after, except the
isPlayingAudioDidChange line, which gets one more call):
  OmniBrowser.cpp           the OmniMediaControls.h include line (pure include after it); the omniNpMediaChanged
                            forward declaration (ours after it); the ui.isPlayingAudioDidChange line as media controls
                            left it (+ omniSpMediaChanged(page)); the L3 line of button()'s fullscreen branch (touchpad
                            after it).
  OmniFeatures3.h           the OmniMediaControlsShell.h include line (our shell before it).
  OmniMediaControlsShell.h  the "OmniFxRow m; m.id = MC::kRowMute" line of omniNpBuild (Speed row before it); the head of
                            omniNpInput (our row first, before its Cross-only check).
Order: apply_media_controls.py rewrites OmniMediaControlsShell.h whenever it differs, so run this AFTER it (as
apply_sleep_timer.py). Independent of apply_sleep_timer.py (different lines of that header); the chain runs it after.
usage: apply_playback_speed.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_PLAYBACK_SPEED_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_PLAYBACK_SPEED_V1: the pure part of playback speed (no SDL, no WebKit). The shell side is
// OmniPlaybackSpeedShell.h; the reasons are in tools/apply_playback_speed.py. Tested with g++ (test_playback_speed.cpp).
#pragma once
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <string>
#include <vector>

namespace OmniPlaybackSpeed {

constexpr double kSteps[] = { 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0 };
constexpr int kStepCount = int(sizeof(kSteps) / sizeof(kSteps[0]));
constexpr int kNormal = 2;                 // kSteps[kNormal] == 1
constexpr const char* kTimes = "\xC3\x97"; // U+00D7 MULTIPLICATION SIGN (UTF-8)

// The step nearest to r (1 for anything not finite or <= 0).
inline int indexOf(double r)
{
    if (!std::isfinite(r) || r <= 0) return kNormal;
    int best = kNormal;
    for (int i = 0; i < kStepCount; ++i) if (std::fabs(kSteps[i] - r) < std::fabs(kSteps[best] - r)) best = i;
    return best;
}
inline double normalize(double r) { return kSteps[indexOf(r)]; }
// D-pad: one step (dir -1 / +1), stopping at the ends.
inline double step(double r, int dir)
{
    int i = indexOf(r) + (dir > 0 ? 1 : dir < 0 ? -1 : 0);
    if (i < 0) i = 0;
    if (i >= kStepCount) i = kStepCount - 1;
    return kSteps[i];
}
// Cross / the fullscreen shortcut: the next speed, 2x wraps to 0.5x.
inline double cycle(double r) { return kSteps[(indexOf(r) + 1) % kStepCount]; }
inline bool isNormal(double r) { return indexOf(r) == kNormal; }

// "1x", "0.5x", "0.75x", "1.25x", "2x" (x = U+00D7).
inline std::string label(double r)
{
    const double v = normalize(r);
    char buf[16];
    std::snprintf(buf, sizeof buf, "%.2f", v);
    std::string s = buf;
    while (!s.empty() && s.back() == '0') s.pop_back();
    if (!s.empty() && s.back() == '.') s.pop_back();
    return s + kTimes;
}
inline std::string notice(double r) { return "Speed: " + label(r); }
inline std::string unavailableNotice() { return "Speed not available for this video"; }
inline std::string unavailableValue() { return "Not available"; }

// --- what Omni's players can do (OMNI_PLAYBACK_RATE_V1) ------------------------------------------------------------
struct Caps { bool rateOff = false; bool mseOff = false; };
// Mirrors OmniMedia::Rate::enabled() and OmniMedia::Hw::holeV5FlagEnabled(): an env value decides when set (first
// char '0': off), else the flag file's presence.
inline bool killed(const char* env, bool flagPresent) { return env ? env[0] == '0' : flagPresent; }
inline Caps caps(const char* rateEnv, bool rateFlag, const char* v5Env, bool v5Flag)
{
    Caps c;
    c.rateOff = killed(rateEnv, rateFlag);
    c.mseOff = !c.rateOff && killed(v5Env, v5Flag);
    return c;
}

// --- session memory (never stored) ----------------------------------------------------------------------------------
// The key: "s:<site>" / "p:<site>" (private tabs) / "t:<tab>" for a page without an http(s) host.
inline std::string siteKey(const std::string& site, bool privateTab, uintptr_t tab)
{
    if (site.empty()) return "t:" + std::to_string(tab);
    return (privateTab ? "p:" : "s:") + site;
}
class Memory {
public:
    double get(const std::string& key) const { auto it = m_.find(key); return it == m_.end() ? 1.0 : it->second; }
    void set(const std::string& key, double r)
    {
        if (key.empty()) return;
        if (isNormal(r)) { m_.erase(key); return; }
        if (m_.size() >= kMax && !m_.count(key)) m_.erase(m_.begin());
        m_[key] = normalize(r);
    }
    bool empty() const { return m_.empty(); }
    size_t size() const { return m_.size(); }
    static constexpr size_t kMax = 256;
private:
    std::map<std::string, double> m_;
};

// Rising edge of "playing" per tab (from isPlayingAudioDidChange, which fires on any media-state change).
class Edges {
public:
    bool started(uintptr_t tab, bool playing)
    {
        if (m_.size() >= 64 && !m_.count(tab)) m_.clear();
        bool& was = m_[tab];
        const bool edge = playing && !was;
        was = playing;
        return edge;
    }
    void set(uintptr_t tab, bool playing) { m_[tab] = playing; }
private:
    std::map<uintptr_t, bool> m_;
};

// --- the script --------------------------------------------------------------------------------------------------
// R: the speed; M: 1 = leave MSE elements (blob: / srcObject) alone at a speed other than 1 (and skip YouTube's API).
constexpr const char* kScriptBody = R"JS((function(R,M){
var o=[],i,e,n=0,s=0,y=0,skipMse=false;
function walk(d,k){if(!d||k>3)return;try{var m=d.querySelectorAll('video,audio');for(var a=0;a<m.length;a++)o.push(m[a]);
var f=d.querySelectorAll('iframe,frame');for(var j=0;j<f.length;j++){var c=null;try{c=f[j].contentDocument;}catch(x){}walk(c,k+1);}}catch(x){}}
walk(document,0);
function has(v){try{return !!(v.currentSrc||v.srcObject);}catch(x){return false;}}
function mse(v){try{return !!v.srcObject||/^blob:/i.test(v.currentSrc||'');}catch(x){return false;}}
if(M&&R!==1)for(i=0;i<o.length;i++)if(has(o[i])&&mse(o[i]))skipMse=true;
if(!skipMse){try{var p=document.getElementById('movie_player');if(p&&typeof p.setPlaybackRate==='function'){p.setPlaybackRate(R);y=1;}}catch(x){}}
for(i=0;i<o.length;i++){e=o[i];if(!has(e))continue;if(skipMse&&mse(e)){s++;continue;}
try{try{e.preservesPitch=true;}catch(x){}try{e.webkitPreservesPitch=true;}catch(x){}
e.defaultPlaybackRate=R;e.playbackRate=R;n++;}catch(x){}}
return ['omni-sp1',n,s,y,o.length].join('\n');
}))JS";
inline std::string script(double r, bool mseOff)
{
    char num[32];
    std::snprintf(num, sizeof num, "%.2f", normalize(r));
    return std::string(kScriptBody) + "(" + num + "," + (mseOff ? "1" : "0") + ")";
}

struct Answer { bool ok = false; int set = 0, skipped = 0, found = 0; bool youtube = false; };
inline Answer parse(const std::string& text)
{
    std::vector<std::string> f;
    size_t pos = 0;
    while (f.size() < 6) {
        const size_t nl = text.find('\n', pos);
        f.push_back(text.substr(pos, nl == std::string::npos ? std::string::npos : nl - pos));
        if (nl == std::string::npos) break;
        pos = nl + 1;
    }
    Answer a;
    if (f.size() != 5 || f[0] != "omni-sp1") return a;
    auto num = [](const std::string& s, int& out) {
        if (s.empty() || s.size() > 6) return false;
        for (char c : s) if (c < '0' || c > '9') return false;
        out = std::atoi(s.c_str());
        return true;
    };
    int yt = 0;
    if (!num(f[1], a.set) || !num(f[2], a.skipped) || !num(f[3], yt) || !num(f[4], a.found) || yt > 1) return a;
    a.youtube = yt == 1;
    a.ok = true;
    return a;
}
// Did the speed take? (something was set)
inline bool applied(const Answer& a) { return a.ok && (a.set > 0 || a.youtube); }
// The notice after a press.
inline std::string resultNotice(const Answer& a, double r)
{
    if (!a.ok) return "The page didn't answer";
    if (applied(a)) return notice(r);
    if (a.skipped > 0) return unavailableNotice();
    return "No video or audio found on this page";
}

} // namespace OmniPlaybackSpeed
'''

SHELL = r'''// OMNI_PLAYBACK_SPEED_V1: playback speed (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous
// namespace, just before OmniMediaControlsShell.h, whose omniNpBuild / omniNpInput call omniSpNpRow / omniSpInput). The
// pure part is OmniPlaybackSpeed.h; the reasons are in tools/apply_playback_speed.py. Main thread only; nothing is
// written to disk, nothing is injected into pages (one evaluate per press / per playback start of a remembered site).
#pragma once

namespace OPS = OmniPlaybackSpeed;
constexpr int omniSpNpRowId = 41;          // Now playing's "Speed" row (MC rows 1..8, sleep timer 40)
static OPS::Memory omniSpMemory;           // speed per site, this session only
static OPS::Edges omniSpEdges;             // playing edges per tab (re-apply on start)
static uintptr_t omniSpGen = 0;            // answers to older presses are dropped
static std::string omniSpPendingKey;       // the memory key of the press in flight
static double omniSpPendingPrev = 1;       // its speed before the press (put back when nothing took it)

static Tab* omniSpTab(uintptr_t key)
{
    if (key) for (auto& t : tabs) if (t->omniMediaIdentity == key) return t.get();
    return nullptr;
}
static std::string omniSpKey(const Tab& t) { return OPS::siteKey(OmniMediaControls::site(t.url), t.omniPrivate, t.omniMediaIdentity); }
static OPS::Caps omniSpCaps()
{
    static OPS::Caps c;
    static uint32_t at = 0;
    static bool have = false;
    const uint32_t now = SDL_GetTicks();
    if (!have || now - at > 10000u) {   // the players read these flags when they are created
        have = true; at = now;
        c = OPS::caps(getenv("OMNI_PLAYBACK_RATE"), access("/data/omni/playback-rate-disabled.flag", F_OK) == 0,
            getenv("OMNI_HOLEPUNCH_V5"), access("/data/omni/holepunch-v5-disabled.flag", F_OK) == 0);
    }
    return c;
}
// One evaluate: set the speed in the tab. user: a press (notice, memory put back when nothing took it).
static void omniSpApply(Tab& t, double rate, bool user)
{
    if (!t.page || t.crashed) { if (user) notice("That tab is closed"); return; }
    const OPS::Caps c = omniSpCaps();
    if (c.rateOff) { if (user) notice(OPS::unavailableNotice()); return; }
    auto js = adoptWK(WKStringCreateWithUTF8CString(OPS::script(rate, c.mseOff).c_str()));
    const uintptr_t gen = user ? ++omniSpGen : 0;
    WKPageEvaluateJavaScriptInMainFrame(t.page, js.get(), reinterpret_cast<void*>(gen), [](WKTypeRef result, WKErrorRef error, void* ctx) {
        const uintptr_t g = reinterpret_cast<uintptr_t>(ctx);
        if (!g || g != omniSpGen) return;   // a re-apply on playback start, or a newer press is on its way
        const OPS::Answer a = OPS::parse(omniFxResultString(result, error));
        const double now = omniSpMemory.get(omniSpPendingKey);
        if (a.ok && !OPS::applied(a)) omniSpMemory.set(omniSpPendingKey, omniSpPendingPrev);   // nothing took it
        notice(OPS::resultNotice(a, now));
        if (!omniFxStack.empty()) omniFxRefresh(); else omniShellDirty = true;
    });
}
static void omniSpSet(Tab& t, double rate)
{
    const std::string key = omniSpKey(t);
    omniSpPendingKey = key;
    omniSpPendingPrev = omniSpMemory.get(key);
    omniSpMemory.set(key, rate);
    omniSpEdges.set(t.omniMediaIdentity, t.page && !t.crashed && (WKPageGetMediaState(t.page) & (kWKMediaIsPlayingAudio | kWKMediaIsPlayingVideo)));
    omniSpApply(t, rate, true);
    fprintf(stderr, "OMNI PLAYBACK SPEED: %.2f\n", OPS::normalize(rate)); fflush(stderr);
}

// ui.isPlayingAudioDidChange: a tab of a remembered site started playing -> its speed again (YouTube resets it).
static void omniSpMediaChanged(WKPageRef page)
{
    if (omniSpMemory.empty()) return;   // nothing remembered: nothing to do
    Tab* t = omniTabForPage(page);
    if (!t || !t->page || t->crashed) return;
    const bool playing = WKPageGetMediaState(page) & (kWKMediaIsPlayingAudio | kWKMediaIsPlayingVideo);   // UI-process cached, no IPC
    if (!omniSpEdges.started(t->omniMediaIdentity, playing)) return;
    const double r = omniSpMemory.get(omniSpKey(*t));
    if (!OPS::isNormal(r)) omniSpApply(*t, r, false);
}

// --- Now playing (OMNI_MEDIA_CONTROLS_V1) ---------------------------------------------------------------------------
static void omniSpNpRow(OmniFxPanel& p, const Tab& t)
{
    OmniFxRow r; r.id = omniSpNpRowId; r.label = "Speed";
    if (omniSpCaps().rateOff) { r.value = OPS::unavailableValue(); r.detail = OPS::unavailableNotice(); }
    else { r.value = OPS::label(omniSpMemory.get(omniSpKey(t))); r.stepper = true; }
    p.rows.push_back(r);
}
// Cross: the next speed (wraps); D-pad left / right: one step. false: not ours (the panel's L1 / R1 paging).
static bool omniSpInput(uintptr_t key, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    Tab* t = omniSpTab(key);
    if (!t) return true;
    if (omniSpCaps().rateOff) { notice(OPS::unavailableNotice()); return true; }
    const double cur = omniSpMemory.get(omniSpKey(*t));
    const double next = b == SDL_CONTROLLER_BUTTON_A ? OPS::cycle(cur) : OPS::step(cur, b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT ? 1 : -1);
    if (OPS::indexOf(next) == OPS::indexOf(cur)) { notice(OPS::notice(cur)); return true; }   // at 0.5x / 2x already
    omniSpSet(*t, next);
    return true;
}
// Fullscreen: the touchpad press is the next speed for the active tab.
static void omniSpShortcut()
{
    Tab* t = active();
    if (!t) return;
    if (omniSpCaps().rateOff) { notice(OPS::unavailableNotice()); return; }
    omniSpSet(*t, OPS::cycle(omniSpMemory.get(omniSpKey(*t))));
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniMediaControls.h" // OMNI_MEDIA_CONTROLS_V1: Now playing (pure)\n',
         '#include "OmniMediaControls.h" // OMNI_MEDIA_CONTROLS_V1: Now playing (pure)\n'
         '#include "OmniPlaybackSpeed.h" // OMNI_PLAYBACK_SPEED_V1: playback speed steps, memory, script (pure)\n'),
        ('static void omniNpMediaChanged(WKPageRef page); // OMNI_MEDIA_CONTROLS_V1 (OmniMediaControlsShell.h)\n',
         'static void omniNpMediaChanged(WKPageRef page); // OMNI_MEDIA_CONTROLS_V1 (OmniMediaControlsShell.h)\n'
         'static void omniSpMediaChanged(WKPageRef page); // OMNI_PLAYBACK_SPEED_V1 (OmniPlaybackSpeedShell.h): re-apply on playback start\n'
         'static void omniSpShortcut();                   // OMNI_PLAYBACK_SPEED_V1: touchpad in fullscreen: the next speed\n'),
        ('    ui.isPlayingAudioDidChange = [](WKPageRef page, const void*) { omniSavedMediaChanged(page); omniNpMediaChanged(page); }; // OMNI_MEDIA_CONTROLS_V1\n',
         '    ui.isPlayingAudioDidChange = [](WKPageRef page, const void*) { omniSavedMediaChanged(page); omniNpMediaChanged(page); omniSpMediaChanged(page); }; // OMNI_MEDIA_CONTROLS_V1; OMNI_PLAYBACK_SPEED_V1\n'),
        ('        else if (button == SDL_CONTROLLER_BUTTON_LEFTSTICK) omniFullscreenKey("m", "U+004D", 0x6d);\n',
         '        else if (button == SDL_CONTROLLER_BUTTON_LEFTSTICK) omniFullscreenKey("m", "U+004D", 0x6d);\n'
         '        else if (button == SDL_CONTROLLER_BUTTON_TOUCHPAD) omniSpShortcut(); // OMNI_PLAYBACK_SPEED_V1: next speed (was unused in fullscreen)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniMediaControlsShell.h" // OMNI_MEDIA_CONTROLS_V1\n',
         '#include "OmniPlaybackSpeedShell.h" // OMNI_PLAYBACK_SPEED_V1 (before media controls: its panel calls ours)\n'
         '#include "OmniMediaControlsShell.h" // OMNI_MEDIA_CONTROLS_V1\n'),
    ],
    'OmniMediaControlsShell.h': [
        ('    OmniFxRow m; m.id = MC::kRowMute;',
         '    omniSpNpRow(p, *t); // OMNI_PLAYBACK_SPEED_V1: "Speed  < 1x >"\n'
         '    OmniFxRow m; m.id = MC::kRowMute;'),
        ('static bool omniNpInput(OmniFxPanel&, const OmniFxRow& r, int b)\n{\n',
         'static bool omniNpInput(OmniFxPanel&, const OmniFxRow& r, int b)\n{\n'
         '    if (r.id == omniSpNpRowId) return omniSpInput(omniNpKey, b); // OMNI_PLAYBACK_SPEED_V1: Cross / D-pad left-right\n'),
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
    f3 = (root / 'OmniFeatures3.h').read_bytes().decode('utf-8')
    if 'OMNI_MEDIA_CONTROLS_V1' not in f3:
        sys.exit('OmniFeatures3.h: OMNI_MEDIA_CONTROLS_V1 missing: apply_media_controls.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniPlaybackSpeed.h', PURE, 'OmniMediaControls.h'),
            write_new('OmniPlaybackSpeedShell.h', SHELL, 'OmniMediaControlsShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
