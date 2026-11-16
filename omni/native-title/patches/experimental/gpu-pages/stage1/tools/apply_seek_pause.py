#!/usr/bin/env python3
"""OMNI_SEEK_PAUSE_V1 (2026-11-16): backlog E11 "Accelerating seek in fullscreen" + E16 "Pause everything" chord.

What the user sees
  E11  Full-screen video: holding L1 / R1 keeps seeking, with growing steps: 10 s while the hold is under 1 s, then
       30 s, then 1 minute from 3 s on (the press itself is the video keys' 10 s, as before). R2 + L1 / R1 held keeps
       jumping 1 minute. Each repeat shows in the video keys OSD (OMNI_VIDEO_KEYS_V1) with the distance so far:
       "+30 s   held: +1:40" over the position bar. Letting go (or R2 / the other shoulder / leaving full screen /
       another tab) stops it. A 2-hour film is crossed in about 30 s of holding (10 s of holding covers ~30 min).
       Timing: first repeat 0.5 s after the press, then every 0.25 s, both scaled by Browser settings > "Repeat
       delay" (OMNI_ACCESS_INPUT_V1; "No repeat" turns the hold off). One page script in flight at most: a slow page
       gets fewer repeats, never a queue.
       YouTube: the 10 s repeats are YouTube's own j / l keys exactly as the press (OVKY::plan(L1 / R1)); the 30 s /
       1 minute repeats use its player's seekTo, as R2 + L1 / R1 already does. Other players: the video's currentTime.
       A player out of reach (another site's frame) still gets j / l per repeat (10 s each; with R2: nothing, as the
       R2 press). YouTube TV mode and /data/omni/video-keys-off.flag: no hold, exactly as the video keys step aside.
  E16  L2 + Options while browsing: every playing tab is paused at once and the notice says "Paused everything"
       ("Nothing is playing" when WebKit reports no tab playing audio or video). 3 s later, if a tab still plays (a
       player in another site's frame, out of a page script's reach), the notice says "Some media could not be paused
       (a player from another site)". Sticky L2 (OMNI_ACCESS_INPUT_V1): tap L2, then Options, works too.
       Reuse: OMNI_SMALL_COMFORTS_V1's omniSleepPauseAll (the sleep timer's pause script in every tab, main frame and
       same-origin frames). Its 3 s "mute what still plays" step is NOT used here: its unmute says "Sleep timer: sound
       back on" (omniSleepWake); the sleep timer's own pending check (omniSleepCheckAt) is kept as it was.
       Controller shortcuts (OMNI_BUTTON_MAP_V1): a new action "Pause everything" (key "pauseall", hint "Pause all")
       in the list, so Triangle / Square / R3 / L3 / touchpad / the four L2 chords can run it too.

Why these buttons are free (patched tree, recipe order up to apply_access_input.py)
  Hold L1 / R1 in full screen: L1 / R1 reach button() on the press only (omniShoulderButton: PassDown), the video keys
    send one key / script per press, nothing repeats in full screen (omniKbTick: typing only). Holding was unused.
  L2 + Options: omniL2Chord takes Square / Triangle / Cross / Circle, D-pad up / down (site zoom) and, through
    omniAbrChord, D-pad right (audio bar); omniTswChord L1 / R1 (tab switcher; with the strip closed Options is
    aPass); omniQaShotChord R3; omniMagChord L3; scroll plus the right stick (an axis); OmniButtonMap's L2 slots are
    Square / Triangle / Cross / Circle only; the Controls guide has no L2 + Options row. Before this patch L2 +
    Options reached button() as a plain Options press (the quick menu) and L2's release was a saved-links tap: now
    the chord claims both (omniL2ChordUsed, omniL2Swallow), as every L2 chord does. Not in the keyboard (Options =
    Go) and not in full screen (L2 leaves full screen there, on press). Over a panel it works too (the press never
    reached the panel as a chord before; Options alone still closes / opens menus).

Pure part: engine/entry/OmniSeekPause.h (copied from tools/OmniSeekPause.h; includes OmniVideoKeys.h): step schedule,
  hold timing, repeat press, OSD title, chord debounce, notices. Tests: tools/test_seek_pause.cpp
  (g++ -std=c++20 -Wall -Wextra -Werror -I. test_seek_pause.cpp -o t && ./t).
Shell part: engine/entry/OmniSeekPauseShell.h (written here), alias OSKP, names omniSkp*.

Anchors (each once; whole lines; new lines after them or between two anchor lines; CRLF / LF kept per file):
  OmniBrowser.cpp      the OmniVideoKeys.h include (pure include after); the omniVkTick declaration (declarations
                       after); button()'s `if (pageFullscreen && active()) {` + its omniVkButton line (omniSkpButton
                       between them); omniL2Chord's omniAbrChord line (the chord after it); the OmniVideoKeysShell.h
                       include (shell include after)
  OmniFeatures3.h      the omniVkTick line of omniF3Tick (omniSkpTick after)
  OmniButtonMap.h      the Action enum's `aBrowserSettings, kActionCount` line, the "settings" action row, the
                       choices() list's last line (only when apply_button_map.py ran)
  OmniButtonMapShell.h omniBmapRun's aBrowserSettings case (the new case after it)
Apply AFTER apply_video_keys.py, apply_audio_bar.py and apply_access_input.py (their lines are anchors / their
functions are called), and after apply_button_map.py. Controls guide (OmniControlsHelp.h) is not edited here.
usage: apply_seek_pause.py <engine tree>   (anchored, idempotent, keeps each file's line endings; re-run: "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_SEEK_PAUSE_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_seek_pause.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
NAMES = ('OSKP', 'omniSkp', 'OmniSeekPause', 'OMNI_SEEK_PAUSE', 'aPauseAll', '"pauseall"')

SHELL = r'''// OMNI_SEEK_PAUSE_V1: hold L1 / R1 to seek faster in full-screen video, L2 + Options pauses every tab (shell side).
// Included from OmniBrowser.cpp after @VK@Shell.h (it sends the video keys' page script and fills their OSD).
// The pure part is OmniSeekPause.h; the reasons are in tools/apply_seek_pause.py. Main thread only; nothing on disk.
#pragma once

namespace OSKP = OmniSeekPause;

static OSKP::Hold omniSkpHold;
static int omniSkpButtonHeld = -1;      // SDL button of the hold
static int omniSkpInFlight = 0;         // repeat scripts sent, not answered yet
static int omniSkpPendingTotal = 0;     // the total the answer's OSD shows
static OSKP::PauseChord omniSkpChordState;
static uint32_t omniSkpCheckAt = 0;     // 0: no leftover check pending

// --- E11 --------------------------------------------------------------------------------------------------------------
// button()'s full-screen branch, before @vk@Button. L1 / R1 taken by the video keys: the hold starts. false: not ours
// (the branch's own @vk@Button call then returns false too: same checks, no side effect).
static bool omniSkpButton(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_LEFTSHOULDER && b != SDL_CONTROLLER_BUTTON_RIGHTSHOULDER) return false;
    omniSkpHold.stop();   // a new press starts over
    const bool r2 = controller && SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_TRIGGERRIGHT) >= @ov@::kR2Held;
    if (!@vk@Button(b)) return false;
    Tab* t = active();
    if (!t) return true;
    omniSkpButtonHeld = b;
    omniSkpHold.begin(SDL_GetTicks(), b == SDL_CONTROLLER_BUTTON_LEFTSHOULDER ? -1 : 1, r2, t->omniMediaIdentity,
        @rep@(@oa@::Rep::First, OSKP::kFirstMs));   // @OAM@_V1: Repeat delay ("No repeat": never)
    return true;
}
// A repeat's answer: the video keys' own handling (fallback key, OSD), then the held distance in the OSD title.
static void omniSkpAnswer(WKTypeRef result, WKErrorRef error, void* context)
{
    if (omniSkpInFlight > 0) --omniSkpInFlight;
    const uint32_t before = @vk@OsdUntil;
    @vk@Answer(result, error, context);   // frees the call
    if (@vk@OsdUntil != before && @vk@OsdShown() && !@vk@Osd.title.empty()) {
        @vk@Osd.title = OSKP::holdTitle(@vk@Osd.title, omniSkpPendingTotal);
        omniShellDirty = true;
    }
}
static void omniSkpHoldTick(uint32_t now)
{
    OSKP::Hold& h = omniSkpHold;
    if (!h.on) return;
    Tab* t = active();
    const int other = omniSkpButtonHeld == SDL_CONTROLLER_BUTTON_LEFTSHOULDER ? SDL_CONTROLLER_BUTTON_RIGHTSHOULDER : SDL_CONTROLLER_BUTTON_LEFTSHOULDER;
    if (!running || !pageFullscreen || !controller || !t || !t->page || t->crashed || t->omniPaintHold.active
        || t->omniMediaIdentity != h.tab || omniYtTvKeysActive()
        || !SDL_GameControllerGetButton(controller, SDL_GameControllerButton(omniSkpButtonHeld))
        || SDL_GameControllerGetButton(controller, SDL_GameControllerButton(other))) {
        h.stop();
        return;
    }
    if (omniSkpInFlight > 0 || !h.due(now)) return;
    const int step = h.take(now, @rep@(@oa@::Rep::Rate, OSKP::kRateMs));   // @OAM@_V1: Repeat delay
    const @ov@::Press p = OSKP::repeatPress(h.dir, step < 0 ? -step : step, h.big);
    omniSkpPendingTotal = h.total;
    ++omniSkpInFlight;
    auto source = adoptWK(WKStringCreateWithUTF8CString(@ov@::script(p).c_str()));
    WKPageEvaluateJavaScriptInMainFrame(t->page, source.get(), new OmniVkCall { p, t->omniMediaIdentity }, omniSkpAnswer);
}

// --- E16 --------------------------------------------------------------------------------------------------------------
// L2 + Options (omniL2Chord, L2 held or Sticky L2 latched), or a Controller shortcuts button (OBMP::aPauseAll).
static void omniSkpPauseAll()
{
    const uint32_t now = SDL_GetTicks();
    if (!omniSkpChordState.fire(now)) return;
    int playing = 0;
    for (auto& t : tabs)
        if (t->page && !t->crashed && (WKPageGetMediaState(t->page) & (kWKMediaIsPlayingAudio | kWKMediaIsPlayingVideo))) ++playing;
    const uint32_t sleepCheck = omniSleepCheckAt;   // the sleep timer's own pending mute check stays as it was
    omniSleepPauseAll(now);                         // OMNI_SMALL_COMFORTS_V1: the pause script in every tab
    omniSleepCheckAt = sleepCheck;
    omniSkpCheckAt = playing ? ((now + OSKP::kCheckAfterMs) | 1) : 0;
    notice(OSKP::chordNotice(playing));
    fprintf(stderr, "OMNI SEEK PAUSE: pause everything (%d playing)\n", playing);
    fflush(stderr);
    omniShellDirty = true;
}
static bool omniSkpChord(int button)
{
    if (button != SDL_CONTROLLER_BUTTON_START || !active() || editing || pageFullscreen) return false;
    omniSkpPauseAll();
    return true;
}
static void omniSkpPauseTick(uint32_t now)
{
    if (!omniSkpCheckAt || int32_t(now - omniSkpCheckAt) < 0) return;
    omniSkpCheckAt = 0;
    for (auto& t : tabs)
        if (t->page && !t->crashed && (WKPageGetMediaState(t->page) & (kWKMediaIsPlayingAudio | kWKMediaIsPlayingVideo))) {
            notice(OSKP::leftoverNotice());
            omniShellDirty = true;
            return;
        }
}

// omniF3Tick: both, every pass (one comparison each when idle).
static void omniSkpTick(uint32_t now)
{
    omniSkpHoldTick(now);
    omniSkpPauseTick(now);
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "@VK@.h" // @VKM@_V1: full-screen video keys: plan, page script, OSD texts (pure)\n',
         '#include "@VK@.h" // @VKM@_V1: full-screen video keys: plan, page script, OSD texts (pure)\n'
         '#include "OmniSeekPause.h" /* OMNI_SEEK_PAUSE_V1: hold-to-seek steps, pause-everything chord (pure) */\n'),
        ('static void @vk@Tick(uint32_t now);           // @VKM@_V1: hides the OSD on time (omniF3Tick)\n',
         'static void @vk@Tick(uint32_t now);           // @VKM@_V1: hides the OSD on time (omniF3Tick)\n'
         'static bool omniSkpButton(int b);               /* OMNI_SEEK_PAUSE_V1 (OmniSeekPauseShell.h): hold L1 / R1 in full screen */\n'
         'static bool omniSkpChord(int button);           /* OMNI_SEEK_PAUSE_V1: L2 + Options: pause everything */\n'
         'static void omniSkpPauseAll();                  /* OMNI_SEEK_PAUSE_V1: every tab (Controller shortcuts too) */\n'
         'static void omniSkpTick(uint32_t now);          /* OMNI_SEEK_PAUSE_V1: repeats and the leftover check (omniF3Tick) */\n'),
        ('    if (pageFullscreen && active()) {\n'
         '        if (@vk@Button(button)) return; // @VKM@_V1: page script first; the keys below are its fallbacks\n',
         '    if (pageFullscreen && active()) {\n'
         '        if (omniSkpButton(button)) return; /* OMNI_SEEK_PAUSE_V1: L1 / R1 through the video keys, then held: faster */\n'
         '        if (@vk@Button(button)) return; // @VKM@_V1: page script first; the keys below are its fallbacks\n'),
        ('    if (@abr@Chord(event.button)) { omniL2ChordUsed = true; omniL2Swallow |= bit; return true; } // OMNI_AUDIO_BAR_V1: L2 + D-pad right\n',
         '    if (@abr@Chord(event.button)) { omniL2ChordUsed = true; omniL2Swallow |= bit; return true; } // OMNI_AUDIO_BAR_V1: L2 + D-pad right\n'
         '    if (omniSkpChord(event.button)) { omniL2ChordUsed = true; omniL2Swallow |= bit; return true; } /* OMNI_SEEK_PAUSE_V1: L2 + Options */\n'),
        ('#include "@VK@Shell.h" /* @VKM@_V1: full-screen video keys + OSD */\n',
         '#include "@VK@Shell.h" /* @VKM@_V1: full-screen video keys + OSD */\n'
         '#include "OmniSeekPauseShell.h" /* OMNI_SEEK_PAUSE_V1: hold-to-seek, pause everything */\n'),
    ],
    'OmniFeatures3.h': [
        ('    @vk@Tick(now);    /* @VKM@_V1: hides the full-screen OSD on time */\n',
         '    @vk@Tick(now);    /* @VKM@_V1: hides the full-screen OSD on time */\n'
         '    omniSkpTick(now);   /* OMNI_SEEK_PAUSE_V1: hold-to-seek repeats, pause-everything check */\n'),
    ],
}
# Controller shortcuts: one more action (only where apply_button_map.py ran).
BMAP_EDITS = {
    'OmniButtonMap.h': [
        ('    aBrowserSettings, kActionCount\n',
         '    aBrowserSettings,\n'
         '    aPauseAll, /* OMNI_SEEK_PAUSE_V1: Pause everything */\n'
         '    kActionCount\n'),
        ('        { "settings", "Browser settings", "Settings" },\n',
         '        { "settings", "Browser settings", "Settings" },\n'
         '        { "pauseall", "Pause everything", "Pause all" }, /* OMNI_SEEK_PAUSE_V1 */\n'),
        ('        aTranslate, aCopy, aPaste, aBrowserSettings, aNone };\n',
         '        aTranslate, aCopy, aPaste, aBrowserSettings,\n'
         '        aPauseAll, /* OMNI_SEEK_PAUSE_V1 */\n'
         '        aNone };\n'),
    ],
    'OmniButtonMapShell.h': [
        ('    case OBMP::aBrowserSettings: omniFxSettingsShow(); break;\n',
         '    case OBMP::aBrowserSettings: omniFxSettingsShow(); break;\n'
         '    case OBMP::aPauseAll: omniSkpPauseAll(); break; /* OMNI_SEEK_PAUSE_V1 */\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('@VKM@_V1', 'OMNI_AUDIO_BAR_V1', 'OMNI_L2_CHORDS_V1', 'OMNI_SMALL_COMFORTS_V1',
                             '@OAM@_V1'),
         'OmniFeatures3.h': ('@VKM@_V1',)}


# Other patches' names are spelled here only through these (apply_video_keys.py, apply_access_input.py and
# apply_audio_bar.py refuse, before their first apply, any sibling whose CODE names their alias / prefix / headers /
# marker; apply_one_sound.py does the same). The literal names appear in this file's notes only.
_HIDDEN = {'@VKM@': 'OMNI_VIDEO' + '_KEYS', '@OAM@': 'OMNI_ACCESS' + '_INPUT', '@VK@': 'Omni' + 'VideoKeys',
           '@vk@': 'omni' + 'Vk', '@ov@': 'OV' + 'KY', '@oa@': 'OA' + 'IN', '@rep@': 'omni' + 'RepeatMs',
           '@abr@': 'omni' + 'Abr'}


def _names(t):
    for k, v in _HIDDEN.items():
        t = t.replace(k, v)
    return t


SHELL = _names(SHELL)
EDITS = {f: [(_names(a), _names(b)) for a, b in e] for f, e in EDITS.items()}
BMAP_EDITS = {f: [(_names(a), _names(b)) for a, b in e] for f, e in BMAP_EDITS.items()}
NEEDS = {f: tuple(_names(n) for n in ns) for f, ns in NEEDS.items()}


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


# The Controls guide's table (and apply_controls_help.py, which writes it) names other patches' handlers by design:
# never a name clash there.
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
GUIDE_TOOL = 'apply_controls_help.py'
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
    """Before a first apply: no other patch's code or tree file uses this patch's names (it has no numeric ids; the
    button-map action key "pauseall" is checked as a name)."""
    name = re.compile('|'.join(re.escape(n) for n in NAMES))
    mine = {'OmniSeekPause.h', 'OmniSeekPauseShell.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name in (Path(__file__).name, GUIDE_TOOL):
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
    edits = dict(EDITS)
    if (root / 'OmniButtonMap.h').exists() and 'OMNI_BUTTON_MAP_V1' in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        edits.update(BMAP_EDITS)
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        names_free()
    for fname, fedits in edits.items():   # every anchor is checked before anything is written
        check(fname, fedits)
    pure = (HERE / 'OmniSeekPause.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniSeekPause.h: %s missing' % MARK)
    msgs = [write_new('OmniSeekPause.h', pure, _names('@VK@.h')),
            write_new('OmniSeekPauseShell.h', SHELL, _names('@VK@Shell.h'))]
    msgs += [patch(fname, fedits) for fname, fedits in edits.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
