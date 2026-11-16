#!/usr/bin/env python3
"""OMNI_YT_MEDIA_STOP_V1 (2026-11-16): YouTube PO-token experiment support (TEST ONLY): end each yt-timeline run on MEDIA
position instead of wall time, opt-in per run by a harness file. Without the file the title behaves exactly as before.

Why: yt_attest_arms.py needs each video to reach >= 70 media s (past YouTube's ~60 s rejected-token cut), but the window
is enforced in the title (OmniBrowser.cpp omniYtTick stage 2: `if (ms >= y.seconds * 1000)` dumps and ends the run) and
the startup (page + GenerateIT) eats 8-39 s of a wall window.

Page side (the title-embedded playback sampler OMNI_VIDEO_FPS_PROBE_V1, window.__omniPlaybackProbe, 1 sample/s; it is only
injected in yt-timeline mode):
  * every sample's `video` gains  ad      #movie_player has class ad-showing (YouTube's ad state; false when absent)
                                  bufEnd  end of the video element's last buffered range (s), null when none
    (yt_attest_summary.classify() already reads both: ad samples leave the media track, bufEnd = the stall's buffered end)
  * __omniPlaybackProbe.media(): "<time> <ad 0|1>" of the LATEST sample ('' before the first video sample). It reads the
    sampler's last sample only; no new page timer.
Title side (omniYtTick, only in yt-timeline mode = /data/omni/yt-timeline.flag, the yt test runner):
  * at each run start (stage 1) /data/omni/yt-media-stop.txt is read once: "M S C" (spaces or commas), e.g. "70 8 150":
        stop at media >= M s outside ads, or S s of wall time without media progress (once the main video has played
        >= 1 media s; progress = >= 0.5 media s, the summary's own threshold), or at C s of wall time.
    Limits: 1 <= M <= 300, 2 <= S <= 120, 10 <= C <= 360, M < C. Missing file = off; malformed / out of range = off
    with one log line "YTTL media stop run=N: ignored (...)". Off = `ms >= y.seconds * 1000` exactly as before.
  * while on, during stage 2 the shell asks the page once per second (one WKPageEvaluateJavaScriptInMainFrame call
    in flight at most, the same channel the final dump uses) for __omniPlaybackProbe.media(); answers from an earlier run
    are dropped (generation counter). On a stop: log "YTTL media stop run=N reason=media|stall|cap media=.. wall=.. ms",
    a YTTL event, then the existing dump + end of run (stage 3) unchanged.
Pure part: engine/entry/OmniYtMediaStop.h (namespace OmniYtMediaStop, alias OYMS): parse(), parseAnswer(), observe(),
decide(). Tested by tools/test_yt_media_stop.cpp (g++ -std=c++17 -Wall -Wextra -I<tree>/engine/entry); the sampler JS by
tools/test_yt_media_stop_js.mjs <patched OmniBrowser.cpp> (node, fake DOM).

Anchors in OmniBrowser.cpp (whole lines, exactly once each):
  sampler   `    function number(x) { ... }`  (helpers after it), the `total: ..., dropped: ...` line of the sample
            literal (ad / bufEnd appended), the `sourceHdr: ..., samples: samples.slice()}; },` dump line (media() after it)
  shell     the omniYtFullscreenOption line (include + state + poll after it), `omniYtScrollStartMs = 0;` in stage 1
            (run start after it), `if (ms >= y.seconds * 1000) {` in stage 2 (replaced by the opt-in condition)
Apply AFTER apply_yttl_scroll.py (its stage-1 line is an anchor). usage: apply_yt_media_stop.py <engine tree>
Keeps the file's line endings; re-run prints "already".
"""
import sys
from pathlib import Path

MARK = 'OMNI_YT_MEDIA_STOP_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_YT_MEDIA_STOP_V1: pure part of the opt-in media-position stop of yt-timeline runs (test only; no SDL, no WebKit).
// Shell side: omniYms* in OmniBrowser.cpp (omniYtTick). Reasons: tools/apply_yt_media_stop.py. Tests: test_yt_media_stop.cpp.
#pragma once
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <string>

namespace OmniYtMediaStop {

constexpr const char* kPath = "/data/omni/yt-media-stop.txt";
constexpr double kProgressS = 0.5;   // media seconds that count as progress (yt_attest_summary STALL_PROGRESS_S)
constexpr double kStartS = 1.0;      // media seconds in one segment = the main video started (START_PROGRESS_S)
constexpr double kBackJumpS = 3.0;   // a jump back by more = a new segment (BACKJUMP_S)
constexpr uint32_t kPollMs = 1000, kAnswerTimeoutMs = 5000;
// asks the page sampler for its latest sample: "<time> <ad 0|1>" or ''
constexpr const char* kPollScript =
    "(function(){try{var p=window.__omniPlaybackProbe;return p&&p.media?String(p.media()):''}catch(e){return ''}})()";

struct Config { bool on = false; unsigned mediaS = 0, stallS = 0, capS = 0; };

// "70 8 150" / "70,8,150" (any spaces, tabs, commas, line ends between; nothing else). Off when malformed or out of range.
inline Config parse(const std::string& text)
{
    Config c; unsigned v[3]; int n = 0; size_t i = 0;
    auto sep = [](char ch) { return ch == ' ' || ch == '\t' || ch == ',' || ch == '\r' || ch == '\n'; };
    while (i < text.size()) {
        if (sep(text[i])) { ++i; continue; }
        if (text[i] < '0' || text[i] > '9' || n == 3) return Config();
        unsigned x = 0; int digits = 0;
        while (i < text.size() && text[i] >= '0' && text[i] <= '9') { if (++digits > 5) return Config(); x = x * 10 + unsigned(text[i] - '0'); ++i; }
        if (i < text.size() && !sep(text[i])) return Config();
        v[n++] = x;
    }
    if (n != 3) return Config();
    if (v[0] < 1 || v[0] > 300 || v[1] < 2 || v[1] > 120 || v[2] < 10 || v[2] > 360 || v[0] >= v[2]) return Config();
    c.on = true; c.mediaS = v[0]; c.stallS = v[1]; c.capS = v[2];
    return c;
}

// The page's answer "<time> <0|1>"; false for '' or anything else.
inline bool parseAnswer(const std::string& a, double& t, bool& ad)
{
    if (a.empty()) return false;
    char* end = nullptr;
    const double x = std::strtod(a.c_str(), &end);
    if (end == a.c_str() || !std::isfinite(x) || x < 0 || *end != ' ') return false;
    if ((end[1] != '0' && end[1] != '1') || end[2] != 0) return false;
    t = x; ad = end[1] == '1';
    return true;
}

struct State {
    bool haveAnchor = false, lastAd = false, started = false;
    double anchorT = 0, segStartT = 0, lastT = 0;
    uint32_t anchorMs = 0;   // run wall ms when the media position last moved (or main playback (re)appeared)
    unsigned answers = 0;
};

// One answer at run wall time ms. Ads restart the stall clock and never count as media.
inline void observe(State& s, uint32_t ms, double t, bool ad)
{
    ++s.answers;
    if (ad) { s.lastAd = true; s.haveAnchor = false; return; }
    if (!s.haveAnchor) { s.haveAnchor = true; s.anchorT = s.segStartT = s.lastT = t; s.anchorMs = ms; s.lastAd = false; return; }
    if (t < s.lastT - kBackJumpS) s.segStartT = t;   // reload / source reset: a new segment
    if (std::fabs(t - s.anchorT) >= kProgressS) { s.anchorT = t; s.anchorMs = ms; }
    if (t - s.segStartT >= kStartS) s.started = true;
    s.lastT = t; s.lastAd = false;
}

enum Reason { None = 0, Media, Stall, Cap };
inline const char* name(Reason r) { return r == Media ? "media" : r == Stall ? "stall" : r == Cap ? "cap" : "none"; }

// ms = run wall ms now. Off -> None (the caller keeps its wall window).
inline Reason decide(const Config& c, const State& s, uint32_t ms)
{
    if (!c.on) return None;
    if (ms >= c.capS * 1000u) return Cap;
    if (s.haveAnchor && !s.lastAd && s.lastT >= double(c.mediaS)) return Media;
    if (s.started && s.haveAnchor && !s.lastAd && ms >= s.anchorMs && ms - s.anchorMs >=c.stallS * 1000u) return Stall;
    return None;
}

// log-safe copy of the file text (printable ASCII, at most 40 chars)
inline std::string printable(const std::string& s)
{
    std::string o;
    for (char ch : s) { if (o.size() >= 40) break; o += (ch >= 32 && ch < 127) ? ch : ' '; }
    while (!o.empty() && o.back() == ' ') o.pop_back();
    return o;
}

} // namespace OmniYtMediaStop
'''

SHELL = r'''static bool omniYtFullscreenOption(const std::string& line) { return line == "fullscreen 1"; }
// OMNI_YT_MEDIA_STOP_V1 (test only, inert without /data/omni/yt-media-stop.txt): opt-in end of each run on media position.
#include "OmniYtMediaStop.h"
namespace OYMS = OmniYtMediaStop;
static OYMS::Config omniYmsCfg;
static OYMS::State omniYmsState;
static uintptr_t omniYmsGen = 0;
static bool omniYmsPending = false;
static uint32_t omniYmsAsked = 0;
static void omniYmsRunStart()
{
    omniYmsCfg = OYMS::Config(); omniYmsState = OYMS::State(); ++omniYmsGen; omniYmsPending = false; omniYmsAsked = 0;
    FILE* file = fopen(OYMS::kPath, "r");
    if (!file) return;
    char buf[128]; const size_t n = fread(buf, 1, sizeof buf - 1, file); fclose(file); buf[n] = 0;
    omniYmsCfg = OYMS::parse(buf);
    char line[300];
    if (omniYmsCfg.on) snprintf(line, sizeof line, "YTTL media stop run=%zu: media >= %u s outside ads, or %u s without media progress, or %u s wall",
        omniYt.index, omniYmsCfg.mediaS, omniYmsCfg.stallS, omniYmsCfg.capS);
    else snprintf(line, sizeof line, "YTTL media stop run=%zu: ignored (%s); wall window %u s as before", omniYt.index, OYMS::printable(buf).c_str(), omniYt.seconds);
    log(line);
}
static bool omniYmsShouldEnd(uint32_t now, uint32_t ms)
{
    if (omniYmsPending && now - omniYmsAsked >= OYMS::kAnswerTimeoutMs) omniYmsPending = false;
    if (!omniYmsPending && now - omniYmsAsked >= OYMS::kPollMs && active() && active()->page) {
        omniYmsPending = true; omniYmsAsked = now;
        auto script = adoptWK(WKStringCreateWithUTF8CString(OYMS::kPollScript));
        WKPageEvaluateJavaScriptInMainFrame(active()->page, script.get(), reinterpret_cast<void*>(omniYmsGen), [](WKTypeRef result, WKErrorRef error, void* gen) {
            if (reinterpret_cast<uintptr_t>(gen) != omniYmsGen) return;   // an earlier run's answer
            omniYmsPending = false;
            if (error || !result || WKGetTypeID(result) != WKStringGetTypeID() || omniYt.stage != 2) return;
            double t = 0; bool ad = false;
            if (OYMS::parseAnswer(OmniTest::toStd(static_cast<WKStringRef>(result)), t, ad))
                OYMS::observe(omniYmsState, SDL_GetTicks() - omniYt.t0, t, ad);
        });
    }
    const OYMS::Reason r = OYMS::decide(omniYmsCfg, omniYmsState, ms);
    if (r == OYMS::None) return false;
    char line[200]; snprintf(line, sizeof line, "YTTL media stop run=%zu reason=%s media=%.1f ad=%d wall=%u ms answers=%u", omniYt.index, OYMS::name(r),
        omniYmsState.haveAnchor ? omniYmsState.lastT : -1.0, omniYmsState.lastAd ? 1 : 0, ms, omniYmsState.answers);
    log(line);
    snprintf(line, sizeof line, "media stop %s", OYMS::name(r)); omniYtEvent(line);
    return true;
}
'''

EDITS = [
    # sampler JS (OMNI_VIDEO_FPS_PROBE_V1, inside the yt-timeline raw string): helpers, per-sample fields, media()
    ("    function number(x) { return typeof x === 'number' && isFinite(x) && x >= 0 ? x : null; }\n",
     "    function number(x) { return typeof x === 'number' && isFinite(x) && x >= 0 ? x : null; }\n"
     "    /* OMNI_YT_MEDIA_STOP_V1: YouTube's ad state and the end of the last buffered range, per sample */\n"
     "    function omniYmsAd() { try { var p = document.querySelector('#movie_player'); return !!(p && p.classList && p.classList.contains('ad-showing')); } catch (_) { return false; } }\n"
     "    function omniYmsBufEnd(v) { try { var b = v.buffered; return b && b.length ? number(b.end(b.length - 1)) : null; } catch (_) { return null; } }\n"),
    ("                total: q ? number(q.totalVideoFrames) : null, dropped: q ? number(q.droppedVideoFrames) : null\n",
     "                total: q ? number(q.totalVideoFrames) : null, dropped: q ? number(q.droppedVideoFrames) : null,\n"
     "                ad: omniYmsAd(), bufEnd: omniYmsBufEnd(v) /* OMNI_YT_MEDIA_STOP_V1 */\n"),
    ("            sourceHdr: 'unknown', displayHdr: 'unknown', samples: samples.slice()}; },\n",
     "            sourceHdr: 'unknown', displayHdr: 'unknown', samples: samples.slice()}; },\n"
     "        /* OMNI_YT_MEDIA_STOP_V1: the latest sample for the title's opt-in media stop: '<time> <ad 0|1>' */\n"
     "        media: function () { var d = previous && previous.video; return d && d.time !== null ? d.time.toFixed(3) + ' ' + (d.ad ? 1 : 0) : ''; },\n"),
    # shell
    ('static bool omniYtFullscreenOption(const std::string& line) { return line == "fullscreen 1"; }\n', SHELL),
    ('        omniYtScrollStartMs = 0; // OMNI_YTTL_SCROLL_V1\n',
     '        omniYtScrollStartMs = 0; // OMNI_YTTL_SCROLL_V1\n'
     '        omniYmsRunStart(); // OMNI_YT_MEDIA_STOP_V1: reads yt-media-stop.txt once per run (absent = off)\n'),
    ('        if (ms >= y.seconds * 1000) {\n',
     '        if (omniYmsCfg.on ? omniYmsShouldEnd(now, ms) : ms >= y.seconds * 1000) { // OMNI_YT_MEDIA_STOP_V1: off = the wall window as before\n'),
]


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


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
    p = root / 'OmniBrowser.cpp'
    s = p.read_bytes().decode('utf-8')
    done = MARK in s
    if not done:
        if 'OMNI_YTTL_SCROLL_V1' not in s or 'OMNI_VIDEO_FPS_PROBE_V1' not in s:
            sys.exit('OmniBrowser.cpp: OMNI_YTTL_SCROLL_V1 / OMNI_VIDEO_FPS_PROBE_V1 missing: apply_yttl_scroll.py first')
        for old0, _ in EDITS:   # every anchor is checked before anything is written
            old, _e = variants(old0, s)
            if s.count(old) != 1:
                sys.exit('OmniBrowser.cpp: anchor found %d times: %r' % (s.count(old), old0[:90]))
    msgs = [write_new('OmniYtMediaStop.h', PURE, 'OmniBrowser.cpp')]
    if done:
        msgs.append('OmniBrowser.cpp: already')
    else:
        for old0, new0 in EDITS:
            old, e = variants(old0, s)
            s = s.replace(old, new0.replace('\n', e), 1)
        p.write_bytes(s.encode('utf-8'))
        msgs.append('OmniBrowser.cpp: applied')
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
