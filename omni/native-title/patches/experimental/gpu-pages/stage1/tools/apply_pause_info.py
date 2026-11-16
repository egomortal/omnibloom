#!/usr/bin/env python3
"""OMNI_PAUSE_INFO_V1 (2026-11-16): backlog E12 "Pause info overlay": a TV-player info strip over a paused full-screen video.

What existed (grep of the patched tree, chain_final + apply_video_keys.py)
  OMNI_VIDEO_KEYS_V1 (OmniVideoKeysShell.h) draws an OSD pill in draw()'s full-screen branch (omniVkOsdDraw, 680 px wide,
  bottom centre): a title row (title left, `right` text right), a bar with "12:05 / 45:10", and an optional second line
  (`resume`); it shows while omniVkOsdUntil is ahead (omniVkTick hides it on time or when full screen ends) and is in the
  shell signature (omniVkOsdSig). Its page script (OmniVideoKeys::script; R3's kInfo press acts on nothing) finds the
  full-screen video (the <video> itself, the playing / largest one in the full-screen element or its same-origin frame)
  and answers state / position / duration / rate. Nothing shows anything when a full-screen video is paused.
  Play state without a script: ui.isPlayingAudioDidChange (WebPageProxy's isPlayingMediaDidChange: the playing audio OR
  video bits changed) calls omniNpMediaChanged (OMNI_MEDIA_CONTROLS_V1); WKPageGetMediaState is the UI process's cached
  state (no IPC). Fades: omniFadeBegin / omniFadeEnd (OMNI_POLISH_V1) blend whatever is drawn between them over the saved
  pixels. Local time: OMNI_SMALL_COMFORTS_V1 has no wall clock (sleep timer / battery / downloads only); the tree's local
  clock is night light's omniNlMinute() (localtime_r's offset, else the downloader's tz-offset.json, else UTC: PS5 libc
  usually has no TZ). Used when OmniNightLightShell.h is in the tree; else localtime_r.

What the user sees now (full screen only)
  The video is paused (any way: Square, the site's own button, Cross at the pointer, YouTube's k) and stays paused for
  1.5 s with no button pressed: the video keys' pill shows, held (not 2 s), as an info strip:
      <video title>                                                  21:12      (Media Session title, else the tab's)
      [========------------------------------]                12:05 / 45:10     (the video keys' own bar and clock)
      33:05 left   Ends at 22:41                                                (live: "Live"; no duration: no line)
  "Ends at": the local time now + the time left at the current speed (1.5x ends sooner), nearest minute, 24-hour.
  The local time (and "Ends at") is renewed when the minute changes: a redraw only, no script.
  It fades in over 200 ms; with Reduce motion on (OMNI_REDUCE_MOTION_V1, when in the tree) it is there at once.
  It goes away (at once) when the video plays (the media-state callback), on any button except the pause toggle
  (Square without R2: it plays the video, which hides it), when full screen ends, the tab changes or crashes, or when a
  video key shows its own 2 s OSD in its place. After a button hid it, it comes back only with the next pause.
  Not shown: a video at its end, the resume add-on's prompt up (the video keys OSD has that), no video found, YouTube TV
  mode's own UI (no pageFullscreen), a cross-origin player frame (the script sees no video: nothing shows).
Cost: no polling. One page script per pause that lasted 1.5 s (also one when full screen starts with the video paused);
  while shown, one redraw per minute; the fade is ~200 ms of redraws.
Off switch: /data/omni/pause-info-off.flag (read once).

Pure part: engine/entry/OmniPauseInfo.h (copied from tools/OmniPauseInfo.h; includes OmniVideoKeys.h): times, "Ends at",
  the strip's fields, the script wrapper and its answer. Tests: tools/test_pause_info.cpp
  (g++ -std=c++20 -Wall -Wextra -Werror -I. test_pause_info.cpp -o t && ./t --emit <dir>) and tools/test_pause_info.cjs
  (node test_pause_info.cjs <dir>: the script on a fake DOM; node --check <dir>/pzi.js).
Shell part: engine/entry/OmniPauseInfoShell.h (written here), alias OPZI, names omniPzi*. No settings row, no row id.

Anchors (each once; whole lines; new lines after / around them; CRLF / LF kept per file):
  OmniBrowser.cpp          the OmniVideoKeys.h include (pure include after); the omniVkTick declaration (declarations
                           after); `void button(int button)` + `{` + its ++omniMqInputGeneration line (omniPziInput after);
                           the omniVkOsdDraw(); line of draw() (fade begin before, fade end after); the
                           OmniVideoKeysShell.h include (shell include after)
  OmniFeatures3.h          the omniVkTick(now); line of omniF3Tick (omniPziTick after)
  OmniMediaControlsShell.h `static void omniNpMediaChanged(WKPageRef page)` + `{` (omniPziMediaChanged first)
Apply AFTER apply_video_keys.py (and so after apply_media_controls.py, apply_night_light.py, apply_reduce_motion.py).
usage: apply_pause_info.py <engine tree>   (anchored, idempotent, keeps each file's line endings; re-run: "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_PAUSE_INFO_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_pause_info.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
NAMES = ('OPZI', 'omniPzi', 'OmniPauseInfo', 'OMNI_PAUSE_INFO', 'pause-info-off')

SHELL_HEAD = r'''// OMNI_PAUSE_INFO_V1: the pause info strip (shell side). Included from OmniBrowser.cpp after OmniVideoKeysShell.h. The
// pure part is OmniPauseInfo.h; the reasons are in tools/apply_pause_info.py. Main thread only; nothing is written to
// disk; no polling: the media-state callback arms a 1.5 s wait, then one page script; the strip is the video keys' OSD.
#pragma once

namespace OPZI = OmniPauseInfo;

static int omniPziState = -1;          // -1 not read yet, 0 off (/data/omni/pause-info-off.flag), 1 on
static uintptr_t omniPziTab = 0;       // Tab::omniMediaIdentity the wait / strip belongs to
static uint32_t omniPziAt = 0;         // 0: no wait; else when the script goes out (SDL_GetTicks)
static uintptr_t omniPziGen = 0;       // answers to an older wait are dropped
static bool omniPziShown = false;
static uint32_t omniPziShownAt = 0;
static uint32_t omniPziMinuteAt = 0;   // when the local minute changes next
static OPZI::Answer omniPziAnswer;     // the page's answer the strip shows
static OVKY::Osd omniPziOsd;           // what was handed to the video keys OSD (still ours while equal)
static bool omniPziWasFull = false;
static bool omniPziFading = false;     // an omniFadeBegin is open in draw()

static bool omniPziOn()
{
    if (omniPziState < 0) omniPziState = access(omniData("pause-info-off.flag").c_str(), F_OK) != 0 ? 1 : 0;
    return omniPziState == 1;
}
static bool omniPziPlaying(const Tab& t)
{
    // UI-process cached state (WebPageProxy::m_mediaState), no IPC.
    return t.page && !t.crashed && (unsigned(WKPageGetMediaState(t.page)) & (kWKMediaIsPlayingAudio | kWKMediaIsPlayingVideo));
}
static bool omniPziOwnsOsd() { return omniPziShown && omniVkOsdShown() && omniVkOsd == omniPziOsd; }
'''

CLOCK_NL = r'''// Local time: night light's minute of the day (libc's offset, else tz-offset.json, else UTC); offsets are whole minutes.
static void omniPziLocal(int& minute, int& second)
{
    minute = omniNlMinute();
    second = int((long long)time(nullptr) % 60);
    if (second < 0) second += 60;
}
'''
CLOCK_LIBC = r'''// Local time: libc's (no night light in this tree).
static void omniPziLocal(int& minute, int& second)
{
    const time_t now = time(nullptr);
    struct tm tmv {};
    localtime_r(&now, &tmv);
    minute = tmv.tm_hour * 60 + tmv.tm_min;
    second = tmv.tm_sec > 59 ? 59 : tmv.tm_sec;
}
'''
REDUCE_RM = 'static bool omniPziReduce() { return omniRmOn(); }   // OMNI_REDUCE_MOTION_V1: no fade\n'
REDUCE_NONE = 'static bool omniPziReduce() { return false; }        // no Reduce motion in this tree\n'

SHELL_TAIL = r'''
static void omniPziHide()
{
    omniPziAt = 0;
    if (!omniPziShown) return;
    if (omniPziOwnsOsd()) omniVkOsdUntil = 0;
    omniPziShown = false;
    omniShellDirty = true;
}
// Start (or restart) the 1.5 s wait for the active tab.
static void omniPziArm(const Tab& t)
{
    omniPziTab = t.omniMediaIdentity;
    omniPziAt = SDL_GetTicks() + OPZI::kDelayMs;
    if (!omniPziAt) omniPziAt = 1;
    ++omniPziGen;
}
// Builds the strip from the stored answer at the current local minute and hands it to the video keys OSD.
static void omniPziPut(const Tab& t, uint32_t now)
{
    int minute = 0, second = 0;
    omniPziLocal(minute, second);
    omniPziOsd = OPZI::strip(omniPziAnswer, t.title, minute, second);
    omniVkOsd = omniPziOsd;
    omniVkOsdUntil = now + OPZI::kHoldMs;
    if (!omniVkOsdUntil) omniVkOsdUntil = 1;
    omniPziMinuteAt = now + OPZI::msToNextMinute(second);
    omniShellDirty = true;
}

// ui.isPlayingAudioDidChange (via omniNpMediaChanged): the active full-screen tab stopped playing: wait; it plays: hide.
static void omniPziMediaChanged(WKPageRef page)
{
    if (!omniPziOn() || !pageFullscreen) return;
    Tab* t = omniTabForPage(page);
    if (!t || t != active()) return;
    if (omniPziPlaying(*t)) { omniPziHide(); return; }
    if (!omniPziShown) omniPziArm(*t);
}

// button(), first: any button hides the strip and restarts a pending wait; the pause toggle (Square, no R2) does
// neither: it plays the video, and the media-state callback hides the strip.
static void omniPziInput(int b)
{
    if (!omniPziShown && !omniPziAt) return;
    const bool r2 = controller && SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_TRIGGERRIGHT) >= OVKY::kR2Held;
    if (OVKY::plan(omniVkPad(b), r2).act == OVKY::kToggle) return;
    if (omniPziShown) { omniPziHide(); return; }
    Tab* t = active();
    if (t && t->omniMediaIdentity == omniPziTab) omniPziArm(*t);
    else omniPziAt = 0;
}

static void omniPziAnswerCb(WKTypeRef result, WKErrorRef error, void* context)
{
    if (!running || reinterpret_cast<uintptr_t>(context) != omniPziGen || omniPziAt) return;   // a newer wait / press
    Tab* t = active();
    if (!pageFullscreen || !t || t->crashed || t->omniMediaIdentity != omniPziTab || omniPziPlaying(*t)) return;
    const OPZI::Answer a = OPZI::parse(omniFxResultString(result, error));
    if (!OPZI::shows(a)) return;
    if (omniVkOsdShown() && !omniPziOwnsOsd()) return;   // a video key's OSD came up meanwhile: it wins
    omniPziAnswer = a;
    omniPziShown = true;
    omniPziShownAt = SDL_GetTicks();
    omniPziPut(*t, omniPziShownAt);
}

// omniF3Tick: full screen start / end, the wait running out, the minute changing, the fade's frames.
static void omniPziTick(uint32_t now)
{
    if (!pageFullscreen) {
        if (omniPziWasFull) { omniPziHide(); omniPziWasFull = false; omniPziTab = 0; }
        return;
    }
    Tab* t = active();
    if (!omniPziWasFull) {   // full screen began: a video already paused gets the same wait
        omniPziWasFull = true;
        if (t && t->page && !t->crashed && omniPziOn() && !omniPziPlaying(*t)) omniPziArm(*t);
    }
    if (!t || t->crashed || t->omniMediaIdentity != omniPziTab) { omniPziHide(); return; }
    if (omniPziShown) {
        if (!omniPziOwnsOsd()) { omniPziShown = false; return; }   // replaced by a video key's OSD, or hidden
        if (now - omniPziShownAt < OPZI::fadeMs(omniPziReduce())) omniShellDirty = true;
        if (int32_t(now - omniPziMinuteAt) >= 0) omniPziPut(*t, now);
        return;
    }
    if (!omniPziAt || int32_t(now - omniPziAt) < 0) return;
    if (omniVkOsdShown()) { omniPziAt = omniVkOsdUntil ? omniVkOsdUntil : 1; return; }   // after a video key's 2 s OSD
    omniPziAt = 0;
    if (!t->page || omniPziPlaying(*t) || t->omniPaintHold.active) return;
    auto source = adoptWK(WKStringCreateWithUTF8CString(OPZI::script().c_str()));
    WKPageEvaluateJavaScriptInMainFrame(t->page, source.get(), reinterpret_cast<void*>(omniPziGen), omniPziAnswerCb);
}

// draw()'s full-screen branch, around omniVkOsdDraw: the strip's fade in (none with Reduce motion).
static void omniPziDrawBegin()
{
    omniPziFading = false;
    if (!omniPziOwnsOsd()) return;
    const float a = OPZI::fadeT(omniPziReduce(), SDL_GetTicks() - omniPziShownAt);
    if (a >= 1) return;
    omniFadeBegin((width - 740) / 2, height - 108 - 36 - 30, 740, 108 + 36 + 30, a);
    omniPziFading = true;
}
static void omniPziDrawEnd()
{
    if (omniPziFading) omniFadeEnd();
    omniPziFading = false;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniVideoKeys.h" // OMNI_VIDEO_KEYS_V1: full-screen video keys: plan, page script, OSD texts (pure)\n',
         '#include "OmniVideoKeys.h" // OMNI_VIDEO_KEYS_V1: full-screen video keys: plan, page script, OSD texts (pure)\n'
         '#include "OmniPauseInfo.h" // OMNI_PAUSE_INFO_V1: the paused full-screen video info strip: times, ends at (pure)\n'),
        ('static void omniVkTick(uint32_t now);           // OMNI_VIDEO_KEYS_V1: hides the OSD on time (omniF3Tick)\n',
         'static void omniVkTick(uint32_t now);           // OMNI_VIDEO_KEYS_V1: hides the OSD on time (omniF3Tick)\n'
         'static void omniPziTick(uint32_t now);          // OMNI_PAUSE_INFO_V1 (OmniPauseInfoShell.h): wait, minute, fade (omniF3Tick)\n'
         'static void omniPziMediaChanged(WKPageRef page); // OMNI_PAUSE_INFO_V1: play / pause of the full-screen tab\n'
         'static void omniPziInput(int b);                // OMNI_PAUSE_INFO_V1: buttons hide the strip (button())\n'
         'static void omniPziDrawBegin();                 // OMNI_PAUSE_INFO_V1: the strip fades in (draw())\n'
         'static void omniPziDrawEnd();                   // OMNI_PAUSE_INFO_V1\n'),
        ('void button(int button)\n'
         '{\n'
         '    ++omniMqInputGeneration; // OMNI_MQ_NATIVE_V1\n',
         'void button(int button)\n'
         '{\n'
         '    ++omniMqInputGeneration; // OMNI_MQ_NATIVE_V1\n'
         '    omniPziInput(button); /* OMNI_PAUSE_INFO_V1: any button but the pause toggle hides the pause info strip */\n'),
        ('        omniVkOsdDraw(); // OMNI_VIDEO_KEYS_V1: position / speed / captions for 2 s after a video key\n',
         '        omniPziDrawBegin(); /* OMNI_PAUSE_INFO_V1: the pause info strip (the OSD below) fades in */\n'
         '        omniVkOsdDraw(); // OMNI_VIDEO_KEYS_V1: position / speed / captions for 2 s after a video key\n'
         '        omniPziDrawEnd(); /* OMNI_PAUSE_INFO_V1 */\n'),
        ('#include "OmniVideoKeysShell.h" /* OMNI_VIDEO_KEYS_V1: full-screen video keys + OSD */\n',
         '#include "OmniVideoKeysShell.h" /* OMNI_VIDEO_KEYS_V1: full-screen video keys + OSD */\n'
         '#include "OmniPauseInfoShell.h" /* OMNI_PAUSE_INFO_V1: info strip over a paused full-screen video */\n'),
    ],
    'OmniFeatures3.h': [
        ('    omniVkTick(now);    /* OMNI_VIDEO_KEYS_V1: hides the full-screen OSD on time */\n',
         '    omniVkTick(now);    /* OMNI_VIDEO_KEYS_V1: hides the full-screen OSD on time */\n'
         '    omniPziTick(now);   /* OMNI_PAUSE_INFO_V1: pause info strip: wait, minute, fade */\n'),
    ],
    'OmniMediaControlsShell.h': [
        ('static void omniNpMediaChanged(WKPageRef page)\n'
         '{\n',
         'static void omniNpMediaChanged(WKPageRef page)\n'
         '{\n'
         '    omniPziMediaChanged(page); /* OMNI_PAUSE_INFO_V1: the full-screen video paused / plays */\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_VIDEO_KEYS_V1', 'OMNI_MQ_NATIVE_V1', 'OMNI_POLISH_V1'),
         'OmniFeatures3.h': ('OMNI_VIDEO_KEYS_V1', 'OMNI_MEDIA_CONTROLS_V1'),
         'OmniMediaControlsShell.h': ('OMNI_MEDIA_CONTROLS_V1',),
         'OmniVideoKeysShell.h': ('OMNI_VIDEO_KEYS_V1', 'static void omniVkOsdDraw()', 'static OVKY::Pad omniVkPad(int b)')}


def shell_text():
    """The shell, with the tree's local clock (night light when present) and Reduce motion (when present)."""
    def has(name, needle):
        p = root / name
        return p.exists() and needle in p.read_bytes().decode('utf-8', errors='replace')
    clock = CLOCK_NL if has('OmniNightLightShell.h', 'static int omniNlMinute()') else CLOCK_LIBC
    reduce = REDUCE_RM if has('OmniReduceMotionShell.h', 'static bool omniRmOn()') else REDUCE_NONE
    return SHELL_HEAD + clock + reduce + SHELL_TAIL


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


# The Controls guide's table names other patches' handlers by design: never a name clash there (its apply script's
# table is string data too, so it is skipped as a sibling as well).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
GUIDE_PY = ('apply_controls_help.py',)
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): a name in another patch's notes is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def code_only(src):
    """A sibling apply_*.py without its comments and module docstring (line numbers kept): names mentioned only in its
    notes are not a use."""
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


def names_free():
    """Before a first apply: no other patch's code or tree file uses this patch's names (it has no numeric ids: no
    settings row)."""
    name = re.compile('|'.join(re.escape(n) for n in NAMES))
    mine = {'OmniPauseInfo.h', 'OmniPauseInfoShell.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name or f.name in GUIDE_PY:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        m = name.search(code_only(f.read_text(encoding='utf-8', errors='replace')))
        if m:
            sys.exit('%s already uses %r: pick other names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in mine or f.name in GUIDE or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        m = name.search(cpp_code(t))
        if m and MARK not in t:
            sys.exit('%s already uses %r: pick other names' % (f.name, m.group(0)))


def main():
    for fname, needs in NEEDS.items():
        s = (root / fname).read_bytes().decode('utf-8')
        for need in needs:
            if need not in s:
                sys.exit('%s: %s missing: apply its patch first' % (fname, need))
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        names_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    pure = (HERE / 'OmniPauseInfo.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniPauseInfo.h: %s missing' % MARK)
    msgs = [write_new('OmniPauseInfo.h', pure, 'OmniVideoKeys.h'),
            write_new('OmniPauseInfoShell.h', shell_text(), 'OmniVideoKeysShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
