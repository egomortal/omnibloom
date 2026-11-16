#!/usr/bin/env python3
"""OMNI_YT_AUTOCONTINUE_V1 (2026-11-16): YouTube "Video paused. Continue watching?" answered for the user (opt-in).

Backlog A01. YouTube (and YouTube Music) pause long lean-back sessions with "Video paused. Continue watching?" and wait
for "Yes". With this setting On, Omni presses YouTube's own "Yes" button when that dialog is showing.

What the user sees
  - Site settings (Options > Site settings), only while the shown tab is on youtube.com or one of its subdomains
    (www., m., music.), a row after "Reader view":
        "Answer 'Continue watching?'"   value: Off (default) / On / "On (held: sleep timer)"
        detail: "Presses YouTube's own Yes when it pauses to ask" (+ ", N times this session" once it has)
    Cross / Left / Right toggle it. Notices: "YouTube 'Continue watching?': answered for you" / "...: you answer it".
    In a private tab the change is for this session only (not saved; a private tab never stores anything):
    "... (private tab: until Omni restarts, not saved)". The setting itself works the same in private tabs.
  - When it answers: notice "YouTube: answered 'Continue watching?'" and one log line "OMNI YTAC: answered ...".
Where it does NOT act
  - YouTube TV mode (any /tv path: OMNI_YOUTUBE_TV_V1's TV app) - checked in the shell AND in the page script (SPA
    navigation). Embeds (youtube-nocookie / iframes on other sites): main frame only, YouTube hosts only.
  - Attestation experiments (page-script confounds, OMNI_YT_ATTEST_GUARD_V1 / OMNI_YT_ATTEST_LOG_V1 / yt-timeline):
    while /data/omni/ytguard-off.flag exists, /data/omni/yt-attest-log.flag exists (omniYtAttestLogOn), the
    yt-timeline runner is on (ytTimeline) or any self-test mode (omniTestMode) - NOTHING is evaluated in any page.
    The flags are read once (the first time the setting is On), like the guard's own kill switch.
  - Sleep timer (OMNI_SLEEP_TIMER_V1 / OMNI_SMALL_COMFORTS_V1): never past it. While the timer fades nothing is
    answered, and from the moment it stops playback (omniSleepPauseAll, both timers) nothing is answered until the
    user's next button / key / click (omniSleepWake's events). While a timer is counting it answers normally (the
    timer still stops playback at its end).
How (why no user script): Off = no page script at all (the default). On = every 3 s (OYAC::kPollMs), for each tab on a
YouTube host (not /tv, not crashed, not unloaded by tab memory / tab sleep) one small read-mostly script through
WKPageEvaluateJavaScriptInMainFrame (the same channel media controls and the sleep timer use). It defines nothing in
the page (no globals, no observer, no timers): it looks for a VISIBLE
    yt-confirm-dialog-renderer   (youtube.com: "Video paused. Continue watching?"; button #confirm-button)
        acted on only when the page's main video is paused AND (its text matches the known English wording OR the
        dialog has no visible Cancel button - the "are you there" dialog has only "Yes"; delete / remove
        confirmations always have Cancel, so they are never pressed)
    ytmusic-you-there-renderer   (music.youtube.com; its own button)
and clicks that button, answering "yt" / "music" ('' otherwise). After an answer nothing is pressed for 10 s
(kQuietMs, all tabs). A user script was not used: it would be in every YouTube page even with the setting Off (the
attestation work counts any page script as a confound), and toggling would need a reload.
Pure part: engine/entry/OmniYtAutoContinue.h (namespace OmniYtAutoContinue, alias OYAC): settings file parse /
serialize, the URL check, the page script, its answer, texts. Shell: engine/entry/OmniYtAutoContinueShell.h
(prefix omniYac), included from OmniFeatures3.h after OmniSleepTimerShell.h. Saved as <data>/yt-autocontinue.txt
("on" / "off"; not written in test modes).
Tests: tools/test_yt_autocontinue.cpp (g++ -std=c++17 -Wall -Wextra -I<tree>/engine/entry) and
tools/test_yt_autocontinue_js.mjs <tree>/engine/entry/OmniYtAutoContinue.h (node, fake DOM: dialog detection).

Anchors (whole lines, exactly once each; MARK makes each file idempotent; all insert-before / insert-after):
  OmniBrowser.cpp   the OmniSleepTimer.h include line (pure include after it); the OmniFeatures3Decl.h include line
                    (forward declarations after it); the
                    `omniSleepCheckAt = (now + 3000) | 1;` line of omniSleepPauseAll (hold after it); the
                    omniSleepWake(event.type) line of the event loop (wake after it).
  OmniQuickMenu.h   the omniRauSiteInput declaration (row id + declarations after it), the omniRauSiteRow call (row
                    after it), the omniRauSiteRowId input line (ours before it).
  OmniFeatures3.h   the OmniSleepTimerShell.h include line (shell include after it), the omniStTick(now) line of
                    omniF3Tick (omniYacTick after it).
Row id 787 (Site settings panel; checked unused before a first apply, with every name, as apply_bf_list.py does).
Apply AFTER apply_sleep_timer.py, apply_reader_auto.py, apply_yt_attest_log.py, apply_small_comforts.py.
usage: apply_yt_autocontinue.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_YT_AUTOCONTINUE_V1'
HERE = Path(__file__).resolve().parent
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ['787']
NAMES = [r'\bomniYac', r'\bOYAC\b', r'OmniYtAutoContinue', r'yt-autocontinue\.txt']

PURE = r'''// OMNI_YT_AUTOCONTINUE_V1: the pure part of "Answer 'Continue watching?'" (YouTube / YouTube Music; no SDL, no
// WebKit). The shell side is OmniYtAutoContinueShell.h; the reasons are in tools/apply_yt_autocontinue.py. Tested with
// g++ (test_yt_autocontinue.cpp) and node (test_yt_autocontinue_js.mjs: the page script against a fake DOM).
#pragma once
#include <cstdint>
#include <string>

namespace OmniYtAutoContinue {

constexpr int kSiteRowId = 787;                       // Site settings row
constexpr const char* kFileName = "yt-autocontinue.txt";
constexpr uint32_t kPollMs = 3000;                    // one check per YouTube tab this often (only while On)
constexpr uint32_t kQuietMs = 10000;                  // after an answer: nothing pressed for this long (all tabs)
constexpr uint32_t kAnswerTimeoutMs = 8000;           // a check without an answer by then no longer blocks the next

inline bool reached(uint32_t now, uint32_t at) { return int32_t(now - at) >= 0; }
inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }

// "on" (any case, surrounding spaces / line ends ignored) = On; anything else, or no file, = Off (the default).
inline bool parse(const std::string& text)
{
    size_t a = 0, b = text.size();
    while (a < b && (text[a] == ' ' || text[a] == '\t' || text[a] == '\r' || text[a] == '\n')) ++a;
    while (b > a && (text[b - 1] == ' ' || text[b - 1] == '\t' || text[b - 1] == '\r' || text[b - 1] == '\n')) --b;
    if (b - a != 2) return false;
    return lower(text[a]) == 'o' && lower(text[a + 1]) == 'n';
}
inline std::string serialize(bool on) { return on ? "on\n" : "off\n"; }

// youtube.com or a subdomain of it (www., m., music.); lower case expected or not.
inline bool youtubeHost(const std::string& host0)
{
    std::string h;
    for (char c : host0) h += lower(c);
    while (!h.empty() && h.back() == '.') h.pop_back();
    static const std::string base = "youtube.com";
    if (h == base) return true;
    return h.size() > base.size() + 1 && h.compare(h.size() - base.size() - 1, base.size() + 1, "." + base) == 0;
}
struct Where { bool youtube = false, tv = false; };
// http(s) URL on a YouTube host; tv: its path is /tv or /tv/... (YouTube TV mode: never acted on).
inline Where where(const std::string& url)
{
    Where w;
    size_t p;
    auto starts = [&](const char* pre) { size_t i = 0; for (; pre[i]; ++i) if (i >= url.size() || lower(url[i]) != pre[i]) return false; return true; };
    if (starts("https://")) p = 8; else if (starts("http://")) p = 7; else return w;
    size_t end = url.find_first_of("/?#", p);
    if (end == std::string::npos) end = url.size();
    std::string host = url.substr(p, end - p);
    const size_t at = host.rfind('@');
    if (at != std::string::npos) host = host.substr(at + 1);
    const size_t colon = host.find(':');
    if (colon != std::string::npos) host = host.substr(0, colon);
    if (!youtubeHost(host)) return w;
    w.youtube = true;
    if (end < url.size() && url[end] == '/' && url.compare(end, 3, "/tv") == 0)
        w.tv = end + 3 == url.size() || url[end + 3] == '/' || url[end + 3] == '?' || url[end + 3] == '#';
    return w;
}
inline bool eligible(const std::string& url) { const Where w = where(url); return w.youtube && !w.tv; }

// The check (WKPageEvaluateJavaScriptInMainFrame, main frame). Defines nothing in the page. Answers "yt" / "music"
// when it pressed YouTube's own button, '' otherwise.
constexpr const char* kScript = R"JS((function () {
  try {
    if (window.top !== window) return '';
    if (!/(^|\.)youtube\.com$/.test(location.hostname)) return '';
    if (/^\/tv(\/|$)/.test(location.pathname)) return '';
    var shown = function (e) {
      if (!e || e.isConnected === false || e.hidden) return false;
      if (e.getAttribute && e.getAttribute('aria-hidden') === 'true') return false;
      var r = e.getBoundingClientRect ? e.getBoundingClientRect() : null;
      if (!r || r.width < 1 || r.height < 1) return false;
      var s = window.getComputedStyle ? window.getComputedStyle(e) : null;
      return !s || (s.display !== 'none' && s.visibility !== 'hidden');
    };
    var text = function (e) { return String((e && e.textContent) || '').replace(/\s+/g, ' ').trim(); };
    var press = function (b) {
      var inner = b.querySelector ? b.querySelector('button') : null;
      var t = inner || b;
      if (typeof t.click !== 'function') return false;
      t.click();
      return true;
    };
    var m = document.querySelectorAll('ytmusic-you-there-renderer');
    for (var i = 0; i < m.length; i++) {
      if (!shown(m[i])) continue;
      var mb = m[i].querySelector('button') || m[i].querySelector('yt-button-renderer, tp-yt-paper-button, #button');
      if (mb && press(mb)) return 'music';
    }
    var d = document.querySelectorAll('yt-confirm-dialog-renderer');
    if (!d.length) return '';
    var v = document.querySelector('video.html5-main-video') || document.querySelector('video');
    if (!v || !v.paused || v.ended) return '';
    var words = /continue watching|still watching|are you still there|video paused/i;
    for (var j = 0; j < d.length; j++) {
      if (!shown(d[j])) continue;
      var ok = d[j].querySelector('#confirm-button');
      if (!ok || !shown(ok)) continue;
      var cancel = d[j].querySelector('#cancel-button');
      var noCancel = !cancel || !shown(cancel) || text(cancel) === '';
      if (!words.test(text(d[j])) && !noCancel) continue;
      if (press(ok)) return 'yt';
    }
    return '';
  } catch (e) { return ''; }
})())JS";

enum Answer { kNone = 0, kYouTube, kMusic };
inline Answer parseAnswer(const std::string& a) { return a == "yt" ? kYouTube : a == "music" ? kMusic : kNone; }

// --- texts -------------------------------------------------------------------------------------------------------
inline const char* rowLabel() { return "Answer 'Continue watching?'"; }
inline std::string rowValue(bool on, bool held) { return !on ? "Off" : held ? "On (held: sleep timer)" : "On"; }
inline std::string rowDetail(unsigned answered)
{
    std::string s = "Presses YouTube's own Yes when it pauses to ask";
    if (answered) s += ", " + std::to_string(answered) + (answered == 1 ? " time" : " times") + " this session";
    return s;
}
inline std::string toggleNotice(bool on, bool privateTab)
{
    std::string s = on ? "YouTube 'Continue watching?': answered for you" : "YouTube 'Continue watching?': you answer it";
    if (privateTab) s += " (private tab: until Omni restarts, not saved)";
    return s;
}
inline std::string answeredNotice() { return "YouTube: answered 'Continue watching?'"; }

} // namespace OmniYtAutoContinue
'''

SHELL = r'''// OMNI_YT_AUTOCONTINUE_V1: "Answer 'Continue watching?'" (shell side). Included from OmniFeatures3.h (inside
// OmniBrowser.cpp's anonymous namespace, after OmniSleepTimerShell.h: it reads the sleep timer's phase). The pure part
// is OmniYtAutoContinue.h; the reasons are in tools/apply_yt_autocontinue.py. Main thread only.
#pragma once

namespace OYAC = OmniYtAutoContinue;
static bool omniYacLoaded = false;
static bool omniYacSaved = false;          // the saved choice (<data>/yt-autocontinue.txt)
static bool omniYacOn = false;             // in effect (a private tab's change lives here only)
static bool omniYacHeld = false;           // the sleep timer stopped playback: nothing until the user's next input
static int omniYacBlocked = -1;            // attestation experiment / test mode (read once): -1 not read yet
static uint32_t omniYacNextAt = 0, omniYacQuietUntil = 0, omniYacAskedAt = 0;
static uintptr_t omniYacGen = 0;           // answers for an older generation (setting changed) are dropped
static int omniYacPending = 0;             // checks out
static unsigned omniYacAnswered = 0;       // this session

static void omniYacLoad()
{
    if (omniYacLoaded) return;
    omniYacLoaded = true;
    FILE* f = fopen(omniData(OYAC::kFileName).c_str(), "rb");
    if (!f) return;
    char buf[64];
    const size_t n = fread(buf, 1, sizeof buf - 1, f);
    fclose(f);
    buf[n] = 0;
    omniYacSaved = omniYacOn = OYAC::parse(std::string(buf, n));
}
static void omniYacWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OYAC::kFileName), OYAC::serialize(omniYacSaved), false);
}
// Page-script confounds of the YouTube attestation work: no page script at all while any of them is on.
static bool omniYacExperiment()
{
    if (omniYacBlocked < 0) {
        const char* why = !access("/data/omni/ytguard-off.flag", F_OK) ? "ytguard-off.flag"
            : omniYtAttestLogOn() ? "yt-attest-log.flag" : ytTimeline ? "yt-timeline" : omniTestMode() ? "test mode" : nullptr;
        omniYacBlocked = why ? 1 : 0;
        if (why) { fprintf(stderr, "OMNI YTAC: off while %s is active (no page script; OMNI_YT_AUTOCONTINUE_V1)\n", why); fflush(stderr); }
    }
    return omniYacBlocked == 1;
}
// omniSleepPauseAll (both sleep timers): playback was stopped on purpose.
static void omniYacSleepHold()
{
    if (omniYacHeld) return;
    omniYacHeld = true;
    ++omniYacGen;
    if (omniYacOn) { fprintf(stderr, "OMNI YTAC: held by the sleep timer until the next button press\n"); fflush(stderr); }
}
// Every SDL event (after omniSleepWake): the user is back.
static void omniYacWake(uint32_t type)
{
    if (!omniYacHeld || (type != SDL_CONTROLLERBUTTONDOWN && type != SDL_KEYDOWN && type != SDL_MOUSEBUTTONDOWN)) return;
    omniYacHeld = false;
    omniYacNextAt = SDL_GetTicks() + OYAC::kPollMs;
}
static bool omniYacSleepBusy() { return omniYacHeld || omniSt.phase() == OST::Phase::Fading; }

// --- per pass (omniF3Tick) -------------------------------------------------------------------------------------------
static void omniYacTick(uint32_t now)
{
    if (!OYAC::reached(now, omniYacNextAt)) return;
    omniYacNextAt = now + OYAC::kPollMs;
    omniYacLoad();
    if (!omniYacOn || omniYacSleepBusy() || !OYAC::reached(now, omniYacQuietUntil)) return;
    if (omniYacPending > 0 && !OYAC::reached(now, omniYacAskedAt + OYAC::kAnswerTimeoutMs)) return;
    if (omniYacExperiment()) return;
    static WKRetainPtr<WKStringRef> js = adoptWK(WKStringCreateWithUTF8CString(OYAC::kScript));
    omniYacPending = 0;
    for (auto& t : tabs) {
        if (!t->page || t->crashed || omniTmIsUnloaded(*t) || !OYAC::eligible(t->url)) continue;
        ++omniYacPending;
        omniYacAskedAt = now;
        WKPageEvaluateJavaScriptInMainFrame(t->page, js.get(), reinterpret_cast<void*>(omniYacGen), [](WKTypeRef result, WKErrorRef error, void* gen) {
            if (reinterpret_cast<uintptr_t>(gen) != omniYacGen) return;   // the setting / hold changed since
            if (omniYacPending > 0) --omniYacPending;
            const OYAC::Answer a = OYAC::parseAnswer(omniFxResultString(result, error));
            if (a == OYAC::kNone) return;
            ++omniYacAnswered;
            omniYacQuietUntil = SDL_GetTicks() + OYAC::kQuietMs;
            fprintf(stderr, "OMNI YTAC: answered 'Continue watching?' (%s, %u this session)\n", a == OYAC::kMusic ? "YouTube Music" : "YouTube", omniYacAnswered);
            fflush(stderr);
            notice(OYAC::answeredNotice());
        });
    }
}

// --- Site settings row (only on YouTube hosts) ---------------------------------------------------------------------
static void omniYacSiteRow(OmniFxPanel& p, const std::string&)
{
    Tab* t = active();
    if (!t || !OYAC::where(t->url).youtube) return;
    omniYacLoad();
    OmniFxRow r; r.id = omniYacSiteRowId; r.label = OYAC::rowLabel(); r.stepper = true;
    r.value = OYAC::rowValue(omniYacOn, omniYacOn && omniYacHeld);
    r.detail = OYAC::rowDetail(omniYacAnswered);
    p.rows.push_back(r);
}
static bool omniYacSiteInput(const OmniFxRow&, int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    Tab* t = active();
    if (!t) return true;
    omniYacLoad();
    omniYacOn = !omniYacOn;
    ++omniYacGen;
    omniYacPending = 0;
    omniYacNextAt = SDL_GetTicks();   // On: the first check on the next pass
    const bool priv = t->omniPrivate;
    if (!priv) { omniYacSaved = omniYacOn; omniYacWrite(); }
    notice(OYAC::toggleNotice(omniYacOn, priv));
    omniShellDirty = true;
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSleepTimer.h" // OMNI_SLEEP_TIMER_V1: Sleep timer chooser, fade, end of video (pure)\n',
         '#include "OmniSleepTimer.h" // OMNI_SLEEP_TIMER_V1: Sleep timer chooser, fade, end of video (pure)\n'
         '#include "OmniYtAutoContinue.h" // OMNI_YT_AUTOCONTINUE_V1: answer YouTube\'s "Continue watching?" (pure)\n'),
        ('#include "OmniFeatures3Decl.h" // OMNI_FEATURES_V3: star, suggestions, page tools, dark pages, tab memory\n',
         '#include "OmniFeatures3Decl.h" // OMNI_FEATURES_V3: star, suggestions, page tools, dark pages, tab memory\n'
         'static void omniYacSleepHold();              // OMNI_YT_AUTOCONTINUE_V1 (OmniYtAutoContinueShell.h): sleep timer stopped playback\n'
         'static void omniYacWake(uint32_t type);      // OMNI_YT_AUTOCONTINUE_V1: the user is back (every SDL event)\n'),
        ('    omniSleepCheckAt = (now + 3000) | 1;\n',
         '    omniSleepCheckAt = (now + 3000) | 1;\n'
         '    omniYacSleepHold(); // OMNI_YT_AUTOCONTINUE_V1: no "Continue watching?" answers past the sleep timer\n'),
        ('        omniSleepWake(event.type); // OMNI_SMALL_COMFORTS_V1: unmute tabs the sleep timer muted\n',
         '        omniSleepWake(event.type); // OMNI_SMALL_COMFORTS_V1: unmute tabs the sleep timer muted\n'
         '        omniYacWake(event.type); // OMNI_YT_AUTOCONTINUE_V1: a sleep-timer hold ends with the next press\n'),
    ],
    'OmniQuickMenu.h': [
        ('static bool omniRauSiteInput(const OmniFxRow& r, int b);\n',
         'static bool omniRauSiteInput(const OmniFxRow& r, int b);\n'
         'constexpr int omniYacSiteRowId = OmniYtAutoContinue::kSiteRowId; // OMNI_YT_AUTOCONTINUE_V1 (OmniYtAutoContinueShell.h)\n'
         'static void omniYacSiteRow(OmniFxPanel& p, const std::string& host);\n'
         'static bool omniYacSiteInput(const OmniFxRow& r, int b);\n'),
        ('    omniRauSiteRow(p, host); // OMNI_READER_AUTO_V1: Reader view: Ask / Always for this site\n',
         '    omniRauSiteRow(p, host); // OMNI_READER_AUTO_V1: Reader view: Ask / Always for this site\n'
         '    omniYacSiteRow(p, host); // OMNI_YT_AUTOCONTINUE_V1: Answer \'Continue watching?\' (YouTube hosts only)\n'),
        ('    if (r.id == omniRauSiteRowId) return omniRauSiteInput(r, b); // OMNI_READER_AUTO_V1 (handles its disabled state)\n',
         '    if (r.id == omniYacSiteRowId) return omniYacSiteInput(r, b); // OMNI_YT_AUTOCONTINUE_V1\n'
         '    if (r.id == omniRauSiteRowId) return omniRauSiteInput(r, b); // OMNI_READER_AUTO_V1 (handles its disabled state)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniSleepTimerShell.h" // OMNI_SLEEP_TIMER_V1\n',
         '#include "OmniSleepTimerShell.h" // OMNI_SLEEP_TIMER_V1\n'
         '#include "OmniYtAutoContinueShell.h" // OMNI_YT_AUTOCONTINUE_V1 (after the sleep timer: reads its phase)\n'),
        ('    omniStTick(now);    // OMNI_SLEEP_TIMER_V1: countdown, fade (1 script/s), end-of-video probe (every 5 s)\n',
         '    omniStTick(now);    // OMNI_SLEEP_TIMER_V1: countdown, fade (1 script/s), end-of-video probe (every 5 s)\n'
         '    omniYacTick(now);   // OMNI_YT_AUTOCONTINUE_V1: YouTube tabs every 3 s, only while On\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_SMALL_COMFORTS_V1', 'OMNI_YT_ATTEST_LOG_V1', 'OMNI_FEATURES_V3'),
         'OmniQuickMenu.h': ('OMNI_READER_AUTO_V1',),
         'OmniFeatures3.h': ('OMNI_SLEEP_TIMER_V1',)}


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
    data = text.replace('\r\n', '\n').replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


# Copied from apply_bf_list.py (build-safe id / name checks).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def code_only(src):
    """A sibling apply_*.py without its comments and module docstring (line numbers kept): names mentioned only in its
    notes are not a use. Numeric ids are never looked for in siblings (their notes list other patches' id ranges)."""
    import io
    import tokenize
    cut, first = [], True
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type == tokenize.COMMENT or (first and t.type == tokenize.STRING):
                cut.append((t.start, t.end))
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                              tokenize.ENCODING):
                first = False
    except (tokenize.TokenError, SyntaxError):
        return ''.join(r for r in src.splitlines(True) if not r.lstrip().startswith('#'))
    starts = [0] + [i + 1 for i, c in enumerate(src) if c == '\n']   # tokenize's rows end at '\n' only
    out = list(src)
    for (r0, c0), (r1, c1) in cut:
        for i in range(starts[r0 - 1] + c0, starts[r1 - 1] + c1):
            if out[i] not in '\r\n':
                out[i] = ' '
    return ''.join(out)


def ids_free():
    """Before a first apply: no other patch or tree file uses this patch's ids or names."""
    word = re.compile(r'\b(%s)\b' % '|'.join(IDS))
    name = re.compile('|'.join(NAMES))
    mine = {'OmniYtAutoContinue.h', 'OmniYtAutoContinueShell.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        t = code_only(f.read_text(encoding='utf-8', errors='replace'))
        m = name.search(t)   # numeric ids: engine tree only (a sibling's notes list other patches' ids)
        if m:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in mine or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        c = cpp_code(t)
        m = word.search(c) or (None if f.name in GUIDE else name.search(c))
        if m and MARK not in t:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))


def main():
    for fname, needs in NEEDS.items():
        s = (root / fname).read_bytes().decode('utf-8')
        for need in needs:
            if need not in s:
                sys.exit('%s: %s missing: apply its patch first' % (fname, need))
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        ids_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    msgs = [write_new('OmniYtAutoContinue.h', PURE, 'OmniSleepTimer.h'),
            write_new('OmniYtAutoContinueShell.h', SHELL, 'OmniSleepTimerShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
