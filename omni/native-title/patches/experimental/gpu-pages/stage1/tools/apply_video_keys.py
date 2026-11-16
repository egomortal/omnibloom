#!/usr/bin/env python3
"""OMNI_VIDEO_KEYS_V1 (2026-11-16): better controller control of full-screen video (the TV couch case).

What existed (grep of the patched tree, recipe order up to apply_tips.py)
  button()'s `if (pageFullscreen && active())` branch (OMNI_FULLSCREEN_KEYS_V1) sends YouTube's keyboard keys to the page
  with omniFullscreenKey: Square k, L1 j, R1 l, D-pad arrows (YouTube: 5 s / volume), Triangle c, L3 m; Cross clicks at
  the pointer; Circle / Options / Create leave full screen; touchpad = next playback speed (OMNI_PLAYBACK_SPEED_V1,
  omniSpShortcut). Those keys do something only where the page itself handles them (YouTube, some players): a plain
  <video> or most site players ignore k / j / l / c / m. draw()'s full-screen branch draws the page and the "Return to
  browser" hint only: no toast, so speed notices are invisible there. L2 in full screen leaves it for saved links
  (omniSavedL2); R2 does nothing there (OmniSavedLinksControls::axis returns None for the right trigger in full screen);
  R3 reaches the branch and matches nothing. No hold / repeat in full screen (omniKbTick repeats only while typing).
  YouTube TV mode (omniYtTvButton) takes D-pad / Cross / Circle before the branch. Now playing (OMNI_MEDIA_CONTROLS_V1)
  is an Options panel with one evaluate per press (omniNpRun). Immersive video (OMNI_VIDEO_IMMERSIVE_V1) is a site's
  page-filling player without pageFullscreen: browsing buttons, unchanged here. The "Resume from 12:05?" prompt is the
  bundled omni-resume-videos add-on's (its 'r:' entries; Continue watching shows its 'w:' entries): appended inside the
  full-screen element (or to <body> when that element is the <video> itself, then unseen), arrows move its focus, but
  Cross in full screen clicked at the pointer, not the prompt.

What the user sees now (full screen only; every press is one page script in the active tab's main frame, no polling)
  Square play / pause, L1 / R1 10 s, D-pad left / right 5 s, Triangle captions on / off, L3 mute: on YouTube (host or
    #movie_player) exactly the old keys; elsewhere the script acts on the full-screen video (the <video> itself, the
    playing / largest one in the full-screen element or its same-origin frame, else in the page); when it finds none (a
    cross-origin player frame) or has nothing to do (no <track> captions) the old key is sent, so nothing that worked
    before stops working. Captions: TextTrack subtitles / captions, the browser language first, the last one remembered.
  NEW (free buttons, below): R2 + L1 / R1 back / forward 1 minute (YouTube: its player's seekTo); R2 + D-pad left /
    right one frame back / forward (pauses; 1/30 s; YouTube: pauses and sends its own , / . keys); R2 + Triangle next
    caption track (off after the last; YouTube: its player's caption track list, else c); R2 + Square next audio track
    (video.audioTracks; YouTube: its player's audio track list); R3 the OSD alone.
  OSD: a small pill at the bottom for 2 s after each of these presses (and the touchpad speed press): what happened
    ("+1 min", "Paused", "Captions: English", "Audio: Deutsch", "Speed: 1.5x"), position / duration with a bar, speed
    and captions state. For YouTube's own keys the state is predicted from the answer read just before the key.
  The add-on's resume prompt: Cross in full screen now presses its focused button (Resume / Start over) instead of
    clicking at the pointer; the OSD shows "Resume from 12:05?" with the focused choice (useful when the full-screen
    element is the <video> and the prompt is unseen); D-pad left / right stay its arrows while it has the focus.
  Off switch: /data/omni/video-keys-off.flag (read once): button() behaves exactly as before.
Free in full screen (proof, patched tree): R2: OmniSavedLinksControls.h axis() `if (!c.enabled || (c.fullscreen &&
  trigger == Trigger::Right)) return Action::None;`, omniL2Track reads the left trigger only, PDF / image viewer triggers
  only with their pages (closed in full screen), the keyboard's L2 / R2 only while typing. R3: no case in the branch;
  omniQaShotChord (L2 + R3) requires !pageFullscreen; omniBmapBrowse runs after the branch. R2 is read as held from
  SDL_GameControllerGetAxis(controller, R2) >= 20000 when L1 / R1 / D-pad / Triangle / Square is pressed (L1 / R1 reach
  button() on the press in full screen: ShoulderChord PassDown). D-pad up / down, Circle, Options, Create, L2 unchanged.
  Not taken: YouTube TV mode (omniYtTvKeysActive): the whole feature steps aside, the old branch runs.
Omni's own players (OMNI_PLAYBACK_RATE_V1 / hole punch): only currentTime / pause / play / muted / TextTrack mode /
  AudioTrack enabled are touched (the same calls a site's own controls make; seeks are supported there).
Late answers: each press carries its own copy (heap, freed in the callback); answers come back in order, so rapid presses
  each send their key. An answer for another tab, or after full screen ended, is dropped (no key, no OSD).

Pure part: engine/entry/OmniVideoKeys.h (copied from tools/OmniVideoKeys.h): button plan, the page script, its answer,
  fallbacks, OSD texts. Tests: tools/test_video_keys.cpp (g++ -std=c++20 -Wall -Wextra -Werror -I. test_video_keys.cpp
  -o t && ./t --emit <dir>) and tools/test_video_keys.cjs (node test_video_keys.cjs <dir>: the scripts on a fake DOM).
Shell part: engine/entry/OmniVideoKeysShell.h (written here), alias OVKY, names omniVk*.

Anchors (each once; whole lines; new lines after them; CRLF / LF kept per file):
  OmniBrowser.cpp   the OmniBfList.h include (pure include after); the omniSpShortcut declaration (declarations after);
                    the omniShellSignature `flag(editing); ... fullscreenHintUntil);` line (OSD state mixed in after);
                    the full-screen hint's omniLabel(omniBlockerHostOf(...)) line + its closing brace (OSD draw after);
                    `if (pageFullscreen && active()) {` + its Cross line in button() (omniVkButton between them);
                    the OmniBfListShell.h include (shell include after)
  OmniFeatures3.h   the omniScTick line of omniF3Tick (omniVkTick after)
Apply AFTER apply_bf_list.py, apply_site_clear.py, apply_playback_speed.py, apply_media_controls.py (their lines are
  anchors / their functions are called). Controls guide (OmniControlsHelp.h) is not edited here; rows are in the report.
usage: apply_video_keys.py <engine tree>   (anchored, idempotent, keeps each file's line endings; re-run: "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_VIDEO_KEYS_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_video_keys.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
NAMES = ('OVKY', 'omniVk', 'OmniVideoKeys', 'OMNI_VIDEO_KEYS', 'video-keys-off')

SHELL = r'''// OMNI_VIDEO_KEYS_V1: full-screen video keys (shell side). Included from OmniBrowser.cpp after OmniBfListShell.h. The
// pure part is OmniVideoKeys.h; the reasons are in tools/apply_video_keys.py. Main thread only; nothing is written to
// disk; one page script per press (no polling), its answer decides whether the press's old key / click still goes out.
#pragma once

namespace OVKY = OmniVideoKeys;

struct OmniVkCall { OVKY::Press press; uintptr_t tab = 0; };   // one per press, freed by its answer
static OVKY::Osd omniVkOsd;
static uint32_t omniVkOsdUntil = 0;   // 0: hidden
static int omniVkState = -1;          // -1 not read yet, 0 off (/data/omni/video-keys-off.flag), 1 on

static bool omniVkOn()
{
    if (omniVkState < 0) omniVkState = access(omniData("video-keys-off.flag").c_str(), F_OK) != 0 ? 1 : 0;
    return omniVkState == 1;
}
static OVKY::Pad omniVkPad(int b)
{
    switch (b) {
    case SDL_CONTROLLER_BUTTON_A: return OVKY::pCross;
    case SDL_CONTROLLER_BUTTON_X: return OVKY::pSquare;
    case SDL_CONTROLLER_BUTTON_Y: return OVKY::pTriangle;
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: return OVKY::pL1;
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: return OVKY::pR1;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: return OVKY::pLeft;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: return OVKY::pRight;
    case SDL_CONTROLLER_BUTTON_LEFTSTICK: return OVKY::pL3;
    case SDL_CONTROLLER_BUTTON_RIGHTSTICK: return OVKY::pR3;
    case SDL_CONTROLLER_BUTTON_TOUCHPAD: return OVKY::pTouchpad;
    default: return OVKY::pOther;
    }
}
static bool omniVkOsdShown() { return omniVkOsdUntil && pageFullscreen && int32_t(SDL_GetTicks() - omniVkOsdUntil) < 0; }
static void omniVkShow(const OVKY::Osd& o)
{
    if (!OVKY::shown(o)) return;
    omniVkOsd = o;
    omniVkOsdUntil = SDL_GetTicks() + OVKY::kOsdMs;
    if (!omniVkOsdUntil) omniVkOsdUntil = 1;
    omniShellDirty = true;
}

// The page's answer: the old key / click when the script left the press to it, then the OSD.
static void omniVkAnswer(WKTypeRef result, WKErrorRef error, void* context)
{
    std::unique_ptr<OmniVkCall> call(static_cast<OmniVkCall*>(context));
    if (!running || !call) return;
    Tab* t = active();
    if (!t || t->crashed || t->omniMediaIdentity != call->tab || !pageFullscreen) return;   // the context changed: dropped
    const OVKY::Info info = OVKY::parse(omniFxResultString(result, error));
    const OVKY::Fallback fb = OVKY::fallbackFor(call->press, info);
    const OVKY::Press& p = call->press;
    if (fb == OVKY::fbKey) omniFullscreenKey(p.key.text, p.key.identifier, p.key.keysym);
    else if (fb == OVKY::fbClick) click();
    OVKY::Osd o = OVKY::osd(p, info, fb);
    if (p.speedFirst && o.title.empty()) o.title = OPS::notice(omniSpMemory.get(omniSpKey(*t)));   // a player out of reach
    omniVkShow(o);
}

// button()'s full-screen branch, first. false: not ours (the branch goes on as before).
static bool omniVkButton(int b)
{
    Tab* t = active();
    if (!pageFullscreen || !t || !t->page || t->crashed || t->omniPaintHold.active || !omniVkOn()) return false;
    if (omniYtTvKeysActive()) return false;   // YouTube TV mode keeps every key as it was
    const bool r2 = controller && SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_TRIGGERRIGHT) >= OVKY::kR2Held;
    const OVKY::Press p = OVKY::plan(omniVkPad(b), r2);
    if (p.act == OVKY::kNone) return false;
    if (p.speedFirst) {
        if (omniSpCaps().rateOff) return false;   // the branch's omniSpShortcut says "not available", as before
        omniSpShortcut();   // its evaluate is sent first: the one below reads the new speed
    }
    auto source = adoptWK(WKStringCreateWithUTF8CString(OVKY::script(p).c_str()));
    WKPageEvaluateJavaScriptInMainFrame(t->page, source.get(), new OmniVkCall { p, t->omniMediaIdentity }, omniVkAnswer);
    return true;
}

// omniF3Tick: hides the OSD on time (also when the shell refresh is slow in full screen).
static void omniVkTick(uint32_t now)
{
    if (omniVkOsdUntil && (int32_t(now - omniVkOsdUntil) >= 0 || !pageFullscreen)) { omniVkOsdUntil = 0; omniShellDirty = true; }
}
// omniShellSignature: what the OSD shows (0 hidden).
static uint64_t omniVkOsdSig()
{
    if (!omniVkOsdShown()) return 0;
    uint64_t h = 1469598103934665603ull;
    for (const std::string* s : { &omniVkOsd.title, &omniVkOsd.clock, &omniVkOsd.right, &omniVkOsd.resume })
        for (unsigned char c : *s + "\n") { h ^= c; h *= 1099511628211ull; }
    const int bar = int(omniVkOsd.fraction * 1000);
    h ^= uint64_t(uint32_t(bar)); h *= 1099511628211ull;
    return h | 1;
}
// draw()'s full-screen branch: a pill at the bottom centre (layout px, 1280 x 720).
static void omniVkOsdDraw()
{
    if (!omniVkOsdShown()) return;
    const OmniTheme& T = omniTheme();
    const OVKY::Osd& o = omniVkOsd;
    const int w = 680, h = o.resume.empty() ? 78 : 108, x = (width - w) / 2, y = height - h - 36;
    omniShadow(x, y, w, h, omniRadius, 10, 110, 3);
    fillRounded(x, y, w, h, omniRadius, T.raised);
    const int rw = o.right.empty() ? 0 : 220;
    omniLabel(o.title, x + 22, y + 24, omniSmallBold, T.ink, 0, w - 44 - rw);
    if (rw) omniLabel(o.right, x + w - 22, y + 24, omniSmall, T.inkDim, 2, rw - 12);
    const int cw = o.clock.empty() ? 0 : 170;
    if (o.fraction >= 0) {
        const int bx = x + 22, by = y + 50, bw = w - 44 - cw, bh = 8;
        fillRounded(bx, by, bw, bh, 4, T.line);
        const int fw = int(bw * o.fraction + 0.5);
        if (fw > 0) fillRounded(bx, by, std::max(fw, 8), bh, 4, T.accent);
    }
    if (cw) omniLabel(o.clock, x + w - 22, y + 54, omniSmall, T.ink, 2, cw - 10);
    if (!o.resume.empty()) omniLabel(o.resume, x + 22, y + 86, omniSmall, T.inkDim, 0, w - 44);
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniBfList.h" // OMNI_BF_LIST_V1: Back history list model and hold timing (pure)\n',
         '#include "OmniBfList.h" // OMNI_BF_LIST_V1: Back history list model and hold timing (pure)\n'
         '#include "OmniVideoKeys.h" // OMNI_VIDEO_KEYS_V1: full-screen video keys: plan, page script, OSD texts (pure)\n'),
        ('static void omniSpShortcut();                   // OMNI_PLAYBACK_SPEED_V1: touchpad in fullscreen: the next speed\n',
         'static void omniSpShortcut();                   // OMNI_PLAYBACK_SPEED_V1: touchpad in fullscreen: the next speed\n'
         'static bool omniVkButton(int b);                // OMNI_VIDEO_KEYS_V1 (OmniVideoKeysShell.h): full-screen video keys\n'
         'static void omniVkOsdDraw();                    // OMNI_VIDEO_KEYS_V1: the full-screen OSD (draw())\n'
         'static uint64_t omniVkOsdSig();                 // OMNI_VIDEO_KEYS_V1: the OSD in omniShellSignature\n'
         'static void omniVkTick(uint32_t now);           // OMNI_VIDEO_KEYS_V1: hides the OSD on time (omniF3Tick)\n'),
        ('    flag(editing); flag(pageEditing); flag(settingsOpen); flag(pageFullscreen); flag(SDL_GetTicks() < fullscreenHintUntil);\n',
         '    flag(editing); flag(pageEditing); flag(settingsOpen); flag(pageFullscreen); flag(SDL_GetTicks() < fullscreenHintUntil);\n'
         '    { const uint64_t vk = omniVkOsdSig(); mix(&vk, sizeof vk); } // OMNI_VIDEO_KEYS_V1: the full-screen OSD shows / changes / hides\n'),
        ('            omniLabel(omniBlockerHostOf(active()->url), 330 + lw + 24, 36, omniSmall, T.inkDim, 0, 1000 - 24 - (330 + lw + 24));\n'
         '        }\n',
         '            omniLabel(omniBlockerHostOf(active()->url), 330 + lw + 24, 36, omniSmall, T.inkDim, 0, 1000 - 24 - (330 + lw + 24));\n'
         '        }\n'
         '        omniVkOsdDraw(); // OMNI_VIDEO_KEYS_V1: position / speed / captions for 2 s after a video key\n'),
        ('    if (pageFullscreen && active()) {\n'
         '        if (button == SDL_CONTROLLER_BUTTON_A) click();\n',
         '    if (pageFullscreen && active()) {\n'
         '        if (omniVkButton(button)) return; // OMNI_VIDEO_KEYS_V1: page script first; the keys below are its fallbacks\n'
         '        if (button == SDL_CONTROLLER_BUTTON_A) click();\n'),
        ('#include "OmniBfListShell.h" /* OMNI_BF_LIST_V1: Back history (hold Circle, Options > Browse) */\n',
         '#include "OmniBfListShell.h" /* OMNI_BF_LIST_V1: Back history (hold Circle, Options > Browse) */\n'
         '#include "OmniVideoKeysShell.h" /* OMNI_VIDEO_KEYS_V1: full-screen video keys + OSD */\n'),
    ],
    'OmniFeatures3.h': [
        ('    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n',
         '    omniScTick(now);    // OMNI_SITE_CLEAR_V1_R2: native timeout of "Clear data for this site"\n'
         '    omniVkTick(now);    /* OMNI_VIDEO_KEYS_V1: hides the full-screen OSD on time */\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_BF_LIST_V1', 'OMNI_FULLSCREEN_KEYS_V1', 'OMNI_PLAYBACK_SPEED_V1', 'OMNI_YOUTUBE_TV_V1'),
         'OmniFeatures3.h': ('OMNI_SITE_CLEAR_V1_R2', 'OMNI_MEDIA_CONTROLS_V1')}


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


# The Controls guide's table names other patches' handlers by design: never a name clash there.
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
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
    """Before a first apply: no other patch's code or tree file uses this patch's names (it has no numeric ids)."""
    name = re.compile('|'.join(re.escape(n) for n in NAMES))
    mine = {'OmniVideoKeys.h', 'OmniVideoKeysShell.h'}
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name in (Path(__file__).name, 'apply_controls_help.py'):   # the guide only quotes names in row text
            continue
        src = f.read_text(encoding='utf-8', errors='replace')
        if 'OMNI_VIDEO_KEYS_V1' in src:   # a patch built on top of this one (pause info, seek) uses its names
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
    pure = (HERE / 'OmniVideoKeys.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniVideoKeys.h: %s missing' % MARK)
    msgs = [write_new('OmniVideoKeys.h', pure, 'OmniBfList.h'),
            write_new('OmniVideoKeysShell.h', SHELL, 'OmniBfListShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
