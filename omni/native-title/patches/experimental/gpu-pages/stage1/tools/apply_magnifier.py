#!/usr/bin/env python3
"""OMNI_MAGNIFIER_V1 (2026-11-16): a magnifier lens that follows the pointer, for small text and tiny buttons on a TV.

What the user sees
  - Hold L2 and press L3 (LT + LS with Xbox labels) while browsing: a wide rounded lens (560 x 220 of the 1280 x 720
    view, a two-tone ring) centred on the pointer shows what is under it at 2x; the same chord again: 3x; again: off.
    Circle (B) also closes it while browsing. A small crosshair in the lens marks the pointer's spot (the arrow
    sprite is hidden while the lens is up, so the magnified arrow does not cover what it points at); clicks, scrolling
    and the stick work as before. Near an edge the lens stays on screen.
    Notices: "Magnifier 2x  (L2 + L3: 3x, Circle: close)", "Magnifier 3x  (...: off ...)", "Magnifier off".
  - The lens is hidden (not switched off) during full-screen video, where L3 is the mute key; it comes back after.
  - Controls guide (Options > Controls > Quick actions): "L2 + L3  Magnifier: 2x, 3x, off".
  - Not saved: every start begins with the lens off.

Why L2 + L3 (checked in the patched tree, 2026-11-16)
  L2 chords taken: Square / Triangle / Cross / Circle / D-pad up-down (omniL2Chord, OMNI_L2_CHORDS_V1 + SITE_ZOOM),
  R3 (omniQaShotChord, screenshot); L2 alone = saved links (omniL2Track, on release; the chord marks omniL2ChordUsed
  so the release is not a tap). L1 / R1 feed omniShoulderChord's L1 + R1 state machine (an L2 + R1 chord would break
  its held-state tracking). L3: button() -> omniShortcutAddCurrent / add-on quick switch (omniAdShortcut), keyboard
  Shift (omniKbButton, editing only: the chord is off while editing), full-screen mute (fullscreen: the chord is off).
  No handler reads the L2 axis together with L3 (grep SDL_CONTROLLER_AXIS_TRIGGERLEFT / BUTTON_LEFTSTICK), and the
  Controls guide table (OmniControlsHelp.h) has no L2 + L3 row. So L2 + L3 is free while browsing; the plain L3
  press keeps its meaning (the chord needs L2 held past 20000, as the screenshot chord).

Where the lens is drawn
  The title's GPU present (tools/apply_magnifier_present.py): two copies out of the composed canvas + one compute
  dispatch over the lens + one copy back, recorded after Night light's tint (the lens shows the tinted page) and after
  the hole-punch's video runs (SDR video under the lens is magnified). The shell only sends 8 floats
  (omni_gpu_present_lens, weak: an engine without it or a title without the pass does nothing). No CPU fallback:
  with SDL's CPU present (GPU present off) the chord shows "Magnifier needs Omni's GPU display output" and the lens
  stays off (a CPU lens would scale ~0.5 MPixel per frame in the shell; the GPU present is the normal path).
  Cost: nothing while off (no pass, no pipeline, no buffer); while on, two small copies + a ~250k-pixel dispatch per
  present, and the parameters are sent right before draw() (a mutex + 8 floats, only when they change).

Pointer mapping: pointer x / y as fractions of the view (1280 x 720) = fractions of the canvas (renderWidth x
renderHeight = view x displayScale), so the present multiplies by its canvas size; lens sizes are fractions of the
view height. The pointer's hotspot (pointerX * displayScale, as omniDrawPointer) is the lens's magnification centre.

Pure part: engine/entry/OmniMagnifier.h (no SDL / WebKit / Vulkan): zoom cycle, lens shape, parameters, texts.
Tested by tools/test_magnifier.cpp:  g++ -std=c++17 -Wall -Wextra -I<tree>/engine/entry test_magnifier.cpp
The present pass: tools/test_magnifier_present.cpp (lavapipe).
Shell side: engine/entry/OmniMagnifierShell.h (included from OmniFeatures3.h after OmniSiteClearShell.h).

Anchors (exactly once each; MARK makes each file idempotent; none is another helper's inserted line):
  OmniBrowser.cpp     the OmniSiteClear.h include line (pure include + the two weak title functions, file scope);
                      omniDrawPointer's head + its YouTube TV line (declaration before, the hide check after);
                      the "holePunchShellPhase(5) ... draw" line before tick()'s draw() (omniMagBeforeDraw before it).
  OmniFeatures.h      omniFxButtonEvent's head + its omniQaShotChord line (declaration before, the chord after).
  OmniFeatures3.h     the OmniSiteClearShell.h include line (the shell include after it).
  OmniControlsHelp.h  the L2 + D-pad up / down row (the L2 + L3 row after it).
Apply AFTER apply_controls_help.py (OmniControlsHelp.h), apply_quick_actions.py and apply_site_clear.py.
usage: apply_magnifier.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_MAGNIFIER_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_MAGNIFIER_V1: the pure part of the magnifier lens (no SDL, no WebKit, no Vulkan): the zoom cycle, the lens
// shape, the parameters sent to the title's GPU present (omni_gpu_present_lens) and the texts. The shell side is
// OmniMagnifierShell.h; the lens itself is the present's pass (tools/apply_magnifier_present.py, omni_magnifier.comp).
// Tested on the host with g++ (tools/test_magnifier.cpp).
#pragma once
#include <algorithm>
#include <cmath>
#include <string>

namespace OmniMagnifier {

constexpr int kOff = 0, kFirst = 2, kLast = 3;   // zoom levels: off, 2x, 3x
constexpr int kTriggerHeld = 20000;              // L2 axis (as the screenshot chord, OMNI_QUICK_ACTIONS_V1)
// The lens in view pixels (the shell's 1280 x 720 view): wide, for a line of text; a two-tone ring; a small crosshair.
struct Shape { float halfW, halfH, corner, ring, arm; };
constexpr Shape kWide { 280.0f, 110.0f, 26.0f, 4.0f, 9.0f };

// Off -> 2x -> 3x -> off (the chord); Circle: off.
inline int nextZoom(int z) { return z <= kOff ? kFirst : z < kLast ? z + 1 : kOff; }

// What omni_gpu_present_lens takes: pointer x, y as fractions of the view (= of the canvas), zoom, then half width,
// half height, corner radius, ring width and crosshair arm as fractions of the view height.
struct Params { float p[8] = {}; };
inline Params params(int zoom, float pointerX, float pointerY, float viewW, float viewH, const Shape& s = kWide)
{
    Params r;
    if (viewW <= 0 || viewH <= 0) return r;
    r.p[0] = std::clamp(pointerX / viewW, 0.0f, 1.0f);
    r.p[1] = std::clamp(pointerY / viewH, 0.0f, 1.0f);
    r.p[2] = float(std::clamp(zoom, kFirst, kLast));
    r.p[3] = s.halfW / viewH; r.p[4] = s.halfH / viewH; r.p[5] = s.corner / viewH; r.p[6] = s.ring / viewH; r.p[7] = s.arm / viewH;
    return r;
}
inline bool same(const Params& a, const Params& b)
{
    for (int i = 0; i < 8; ++i) if (std::fabs(a.p[i] - b.p[i]) > 1e-6f) return false;
    return true;
}
// Shown (the pass draws it) only when on, not in full-screen video, not in the test mode, and the present can draw it.
inline bool shown(int zoom, bool fullscreen, bool testMode, bool available) { return zoom > kOff && !fullscreen && !testMode && available; }

// --- texts (PlayStation or Xbox names) ----------------------------------------------------------------------------
inline std::string chordName(bool ps) { return ps ? "L2 + L3" : "LT + LS"; }
inline std::string zoomName(int zoom) { return std::to_string(zoom) + "×"; }   // U+00D7 (DejaVu has it)
inline std::string notice(int zoom, bool ps)
{
    if (zoom <= kOff) return "Magnifier off";
    const std::string next = zoom < kLast ? zoomName(zoom + 1) : std::string("off");
    return "Magnifier " + zoomName(zoom) + "  (" + chordName(ps) + ": " + next + ", " + (ps ? "Circle" : "B") + ": close)";
}
inline std::string unavailableNotice() { return "Magnifier needs Omni's GPU display output, which is not running"; }

} // namespace OmniMagnifier
'''

SHELL = r'''// OMNI_MAGNIFIER_V1: the magnifier lens (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous
// namespace, after OmniSiteClearShell.h). The pure part is OmniMagnifier.h; the lens is the title's GPU present pass
// (omni_gpu_present_lens, declared weak at file scope in OmniBrowser.cpp); the reasons are in tools/apply_magnifier.py.
// Main thread only. Not saved: every start begins with the lens off.
#pragma once

namespace OMAG = OmniMagnifier;
static int omniMagZoom = OMAG::kOff;
static bool omniMagSent = false;
static OMAG::Params omniMagLast;

static bool omniMagAvailable() { return omni_gpu_present_lens && omni_gpu_present_lens_ready && omni_gpu_present_lens_ready() == 1; }
// omniDrawPointer: while the present draws the lens, its crosshair marks the pointer (the arrow would be magnified
// over what it points at).
static bool omniMagHidesPointer() { return omniMagSent; }
// The chord's context: a page, nothing over it (as the screenshot chord, omniQaShotChord).
static bool omniMagBrowsing()
{
    return active() && !editing && !pageEditing && !settingsOpen && !pageFullscreen && !omniOverlayOpen() && !omniFindBarOpen() && !omniTestMode();
}
static bool omniMagL2(SDL_JoystickID which)
{
    SDL_GameController* pad = SDL_GameControllerFromInstanceID(which);
    return pad && SDL_GameControllerGetAxis(pad, SDL_CONTROLLER_AXIS_TRIGGERLEFT) >= OMAG::kTriggerHeld;
}
static void omniMagSet(int zoom)
{
    omniMagZoom = zoom;
    omniShellDirty = true;   // a whole frame: the pointer sprite goes (or comes back), the lens is drawn (or not)
    notice(OMAG::notice(zoom, playStationIcons));
}
// From omniFxButtonEvent (after omniL2Chord and the screenshot chord). L2 + L3: off -> 2x -> 3x -> off. Circle while the
// lens is on: off. Everything else (and these outside a plain page) goes on as before.
static bool omniMagChord(const SDL_ControllerButtonEvent& event)
{
    if (event.type != SDL_CONTROLLERBUTTONDOWN) return false;
    if (event.button == SDL_CONTROLLER_BUTTON_B) {
        if (omniMagZoom == OMAG::kOff || !omniMagBrowsing() || omniMagL2(event.which)) return false;   // L2 + Circle stays Browser settings
        omniMagSet(OMAG::kOff);
        return true;
    }
    if (event.button != SDL_CONTROLLER_BUTTON_LEFTSTICK || !omniMagL2(event.which) || !omniMagBrowsing()) return false;
    omniL2ChordUsed = true;   // the L2 release is not a saved-links tap (OMNI_L2_CHORDS_V1)
    if (!omniMagAvailable()) {
        omniMagZoom = OMAG::kOff;
        notice(OMAG::unavailableNotice());
        omniShellDirty = true;
        return true;
    }
    omniMagSet(OMAG::nextZoom(omniMagZoom));
    return true;
}
// Right before tick()'s draw(): the lens follows the pointer of THIS frame (the stick moved it after omniF3Tick).
// Off and settled: one comparison. Parameters go to the present only when they change.
static void omniMagBeforeDraw()
{
    if (!omni_gpu_present_lens) return;   // a title without the pass
    if (!OMAG::shown(omniMagZoom, pageFullscreen, omniTestMode(), omniMagZoom != OMAG::kOff && omniMagAvailable())) {
        if (omniMagSent) { omni_gpu_present_lens(nullptr); omniMagSent = false; }
        return;
    }
    const OMAG::Params p = OMAG::params(omniMagZoom, pointerX, pointerY, float(width), float(height));
    if (omniMagSent && OMAG::same(p, omniMagLast)) return;
    omni_gpu_present_lens(p.p);
    omniMagSent = true; omniMagLast = p;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSiteClear.h" // OMNI_SITE_CLEAR_V1: Clear data for this site (pure)\n',
         '#include "OmniSiteClear.h" // OMNI_SITE_CLEAR_V1: Clear data for this site (pure)\n'
         '#include "OmniMagnifier.h" // OMNI_MAGNIFIER_V1: the magnifier lens: zoom cycle, shape, parameters (pure)\n'
         '// OMNI_MAGNIFIER_V1: the title\'s GPU present pass (tools/apply_magnifier_present.py); absent in other titles.\n'
         'extern "C" int omni_gpu_present_lens(const float* p) __attribute__((weak));\n'
         'extern "C" int omni_gpu_present_lens_ready(void) __attribute__((weak));\n'),
        ('static void omniDrawPointer()\n{\n    if (omniYtTvPointerHidden()) return; // OMNI_YOUTUBE_TV_V1: the TV app is driven by the D-pad\n',
         'static bool omniMagHidesPointer(); // OMNI_MAGNIFIER_V1 (OmniMagnifierShell.h)\n'
         'static void omniDrawPointer()\n{\n    if (omniYtTvPointerHidden()) return; // OMNI_YOUTUBE_TV_V1: the TV app is driven by the D-pad\n'
         '    if (omniMagHidesPointer()) return; // OMNI_MAGNIFIER_V1: the lens is up; its crosshair marks the pointer\n'),
        ('    OmniMedia::Hw::holePunchShellPhase(5); // OMNI_HOLEPUNCH_V7_STALLTRACE: draw\n',
         '    omniMagBeforeDraw(); // OMNI_MAGNIFIER_V1: the lens follows this frame\'s pointer (before draw: the pointer sprite)\n'
         '    OmniMedia::Hw::holePunchShellPhase(5); // OMNI_HOLEPUNCH_V7_STALLTRACE: draw\n'),
    ],
    'OmniFeatures.h': [
        ('static bool omniFxButtonEvent(const SDL_ControllerButtonEvent& event)\n{\n    if (omniQaShotChord(event)) return true; // OMNI_QUICK_ACTIONS_V1\n',
         'static bool omniMagChord(const SDL_ControllerButtonEvent& event); // OMNI_MAGNIFIER_V1 (OmniMagnifierShell.h)\n'
         'static bool omniFxButtonEvent(const SDL_ControllerButtonEvent& event)\n{\n    if (omniQaShotChord(event)) return true; // OMNI_QUICK_ACTIONS_V1\n'
         '    if (omniMagChord(event)) return true; // OMNI_MAGNIFIER_V1: L2 + L3 (2x, 3x, off); Circle closes the lens\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n',
         '#include "OmniSiteClearShell.h" // OMNI_SITE_CLEAR_V1\n'
         '#include "OmniMagnifierShell.h" // OMNI_MAGNIFIER_V1\n'),
    ],
    'OmniControlsHelp.h': [
        ('    { kQuick, { gL2, gDpadV }, \'+\', false, "Zoom this site in / out", "Remembered for the site", "omniL2Chord (OMNI_SITE_ZOOM_V1)" },\n',
         '    { kQuick, { gL2, gDpadV }, \'+\', false, "Zoom this site in / out", "Remembered for the site", "omniL2Chord (OMNI_SITE_ZOOM_V1)" },\n'
         '    { kQuick, { gL2, gL3 }, \'+\', false, "Magnifier: 2x, 3x, off", "Follows the pointer; {Circle} closes it", "omniMagChord (OMNI_MAGNIFIER_V1)" },\n'),
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
    for name, mark, helper in (('OmniFeatures3.h', 'OMNI_SITE_CLEAR_V1', 'apply_site_clear.py'),
                               ('OmniFeatures.h', 'OMNI_QUICK_ACTIONS_V1', 'apply_quick_actions.py')):
        if mark not in (root / name).read_bytes().decode('utf-8'):
            sys.exit('%s: %s missing: %s first' % (name, mark, helper))
    if not (root / 'OmniControlsHelp.h').exists():
        sys.exit('OmniControlsHelp.h missing: apply_controls_help.py first')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniMagnifier.h', PURE, 'OmniSiteClear.h'),
            write_new('OmniMagnifierShell.h', SHELL, 'OmniSiteClearShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
