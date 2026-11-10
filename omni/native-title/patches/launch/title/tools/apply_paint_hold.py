#!/usr/bin/env python3
"""OMNI_PAINT_HOLD_V1 = Astra's reviewed C-003-R2 (codex-ui/20261103-js-main-c003-review-fix), rebased onto
s3.4d's engine/entry/OmniBrowser.cpp by anchor instead of by line offset. The published cumulative
proposal.diff is against a 7100-line s3 shell and will not apply to s3.4d's 7482-line one; it also carries a
mojibake context line ("Video found â€” L2 to review"), so applying it would corrupt that string. This
applier inserts the same bodies at the same places and never rewrites a context line.

The experiment is OFF unless /data/omni/paint-hold-experimental.flag exists (unchanged from C-003-R2), and
it never holds in a test mode, a private tab or on a host that is not an https YouTube host.
The inserted function block and OmniPaintHold.h are byte-verbatim from the reviewed package.
usage: apply_paint_hold.py <tree root>"""
import difflib, hashlib, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
N = HERE.parent
# the jank sources and the diff folder may live outside the build dir (OMNI_JANK_SRC / OMNI_JANK_PATCHES)
SRC = Path(os.environ.get('OMNI_JANK_SRC') or (N / 'src'))
PATCHES = Path(os.environ.get('OMNI_JANK_PATCHES') or (N / 'patches'))
MARK = 'OMNI_PAINT_HOLD_V1'
tree = Path(sys.argv[1])
entry = tree / 'engine/entry'
target = entry / 'OmniBrowser.cpp'

BLOCK_SHA = '0f1a1cb2a0'   # recomputed below; the check is on the header, which the review pinned
HEADER_SHA = 'f1babdde36697385dad6f3493ab570e862c772f823118935b469d30855975e67'

header = (SRC / 'OmniPaintHold.h').read_bytes()
if hashlib.sha256(header).hexdigest() != HEADER_SHA:
    sys.exit('OmniPaintHold.h is not the reviewed C-003-R2 header')
block = (SRC / 'painthold-block.inc').read_text(encoding='utf-8')

raw = target.read_bytes().decode('utf-8')
crlf = '\r\n' in raw
text = raw.replace('\r\n', '\n')
if MARK in text or 'omniPaintHoldBegin' in text:
    print('already patched'); sys.exit(0)
before = text

EDITS = [
    ('after', '#include "config.h"\n', '#include "OmniPaintHold.h" // OMNI_PAINT_HOLD_V1 (C-003-R2)\n'),
    ('after', 'struct Tab {\n', '    OmniPaintHold::Gate omniPaintHold; // OMNI_PAINT_HOLD_V1\n'),
    ('after', 'WKRetainPtr<WKWebsiteDataStoreRef> websiteDataStore;\n',
     'static void omniPaintHoldBegin(Tab&, WKPageRef); // OMNI_PAINT_HOLD_V1\n'
     'static OmniPaintHold::RevealInput omniPaintRevealInput; // OMNI_PAINT_HOLD_V1\n'),
    # navigation failed / web process crashed: let go of the hold
    ('replace',
     '    auto& tab = *static_cast<Tab*>(const_cast<void*>(info));\n'
     '    if (&tab == active()) omniShoulderCancel(); // OMNI_SHOULDER_DOWNLOADS_V1\n'
     '    auto domain',
     '    auto& tab = *static_cast<Tab*>(const_cast<void*>(info));\n'
     '    tab.omniPaintHold.cancel(); // OMNI_PAINT_HOLD_V1\n'
     '    omniShellDirty = true;\n'
     '    if (&tab == active()) omniShoulderCancel(); // OMNI_SHOULDER_DOWNLOADS_V1\n'
     '    auto domain'),
    ('replace', '    nav.didStartProvisionalNavigation = [](WKPageRef, WKNavigationRef, WKTypeRef, const void* info) {\n',
     '    nav.didStartProvisionalNavigation = [](WKPageRef page, WKNavigationRef, WKTypeRef, const void* info) {\n'),
    ('after', '        omniSavedDocumentChanged(tab);\n', '        omniPaintHoldBegin(tab, page); // OMNI_PAINT_HOLD_V1\n'),
    ('after', '        tab.loading = false;\n        tab.crashed = true;\n',
     '        tab.omniPaintHold.cancel(); // OMNI_PAINT_HOLD_V1\n        omniShellDirty = true;\n'),
    # no pointer, wheel, click, key or gamepad event reaches a held page
    ('after', '    if (!active() || settingsOpen || active()->crashed || pointerY < offset || pointerY >= omniPageBottom()) return;\n',
     '    if (active()->omniPaintHold.active) return; // OMNI_PAINT_HOLD_V1\n'),
    ('after', 'void omniPageWheel(double amount)\n{\n',
     '    if (active() && active()->omniPaintHold.active) { active()->omniPaintHold.cancel(); omniShellDirty = true; return; } // OMNI_PAINT_HOLD_V1\n'),
    ('replace', '    if (pageFullscreen) { mouse(kWKEventMouseDown); mouse(kWKEventMouseUp); return; }\n',
     '    if (pageFullscreen) { if (active()->omniPaintHold.active) { active()->omniPaintHold.cancel(); omniShellDirty = true; return; } mouse(kWKEventMouseDown); mouse(kWKEventMouseUp); return; } // OMNI_PAINT_HOLD_V1\n'),
    ('replace', '    } else { mouse(kWKEventMouseDown); mouse(kWKEventMouseUp); fieldClickDeadline = SDL_GetTicks() + 2000; }\n',
     '    } else { if (active()->omniPaintHold.active) { active()->omniPaintHold.cancel(); omniShellDirty = true; return; } mouse(kWKEventMouseDown); mouse(kWKEventMouseUp); fieldClickDeadline = SDL_GetTicks() + 2000; } // OMNI_PAINT_HOLD_V1\n'),
    # the page layer is masked while held; chrome, progress, dialogs and navigation stay visible
    ('after', '    const int ra = std::max(a, y0), rb = std::min(b, y1);\n    if (rb <= ra) return;\n',
     '    if (active() && active()->omniPaintHold.holding(SDL_GetTicks())) { // OMNI_PAINT_HOLD_V1\n'
     '        SDL_Rect held { 0, ra, canvas->w, rb - ra };\n'
     '        SDL_FillRect(canvas, &held, bgPixel);\n'
     '        return; // Chrome, progress, dialogs and navigation remain visible.\n'
     '    }\n'),
    ('after', 'static void omniFullscreenKey(const char* text, const char* identifier, int keysym)\n{\n    if (!active()) return;\n',
     '    if (active()->omniPaintHold.active) { active()->omniPaintHold.cancel(); omniShellDirty = true; return; } // OMNI_PAINT_HOLD_V1\n'),
    ('after', 'void tick(void*)\n{\n', '    omniPaintHoldTick(); // OMNI_PAINT_HOLD_V1\n'),
    ('replace', '    omniGamepadTick(active(), settingsOpen || editing || omniOverlayOpen(), omniShoulderFocused); // OMNI_GAMEPAD_V1\n',
     '    omniGamepadTick(active(), settingsOpen || editing || omniOverlayOpen() || (active() && active()->omniPaintHold.active), omniShoulderFocused); // OMNI_GAMEPAD_V1 OMNI_PAINT_HOLD_V1\n'),
    # the reveal gesture owns its repeats and its text input (review finding P2)
    ('after', '        if (event.type != SDL_CONTROLLERDEVICEADDED) omniGamepadEvent(event); // OMNI_GAMEPAD_V1 (added: after the pad is open)\n',
     '        if (event.type == SDL_KEYUP) omniPaintRevealInput.keyUp(static_cast<int32_t>(event.key.keysym.scancode)); // OMNI_PAINT_HOLD_V1\n'
     '        if (event.type == SDL_KEYDOWN && omniPaintRevealInput.keyDown(static_cast<int32_t>(event.key.keysym.scancode), event.key.repeat != 0)) continue;\n'
     '        if (event.type == SDL_TEXTINPUT && omniPaintRevealInput.textInput()) continue;\n'),
    ('after', '            omniShoulderFocused = false; omniShoulderReset();\n', '            omniPaintRevealInput.reset(); // OMNI_PAINT_HOLD_V1\n'),
    ('after', '            omniShoulderFocused = true; omniShoulderReset();\n', '            omniPaintRevealInput.reset(); // OMNI_PAINT_HOLD_V1\n'),
    ('after', '            omniShoulderFocused = event.window.event == SDL_WINDOWEVENT_FOCUS_GAINED; omniShoulderReset();\n',
     '            omniPaintRevealInput.reset(); // OMNI_PAINT_HOLD_V1\n'),
    ('after', '            if (editing) append(event.text.text);\n',
     '            else if (active()->omniPaintHold.active) { active()->omniPaintHold.cancel(); omniShellDirty = true; } // OMNI_PAINT_HOLD_V1\n'),
    ('after', '            else if (key == SDLK_F6 || (key == SDLK_l && (event.key.keysym.mod & KMOD_CTRL))) editAddress();\n            else {\n',
     '                if (active()->omniPaintHold.active) { omniPaintRevealInput.consumeGesture(static_cast<int32_t>(event.key.keysym.scancode)); active()->omniPaintHold.cancel(); omniShellDirty = true; continue; } // OMNI_PAINT_HOLD_V1\n'),
]

for kind, anchor, body in EDITS:
    n = text.count(anchor)
    if n != 1:
        sys.exit('anchor matched %d times: %r' % (n, anchor[:110]))
    text = text.replace(anchor, anchor + body if kind == 'after' else body)

# the function block, verbatim from the reviewed package, immediately before the row painter it guards
tail = 'static void omniPageToCanvasRows(const SDL_Rect& dst, SDL_Color bg, int a, int b)\n'
if text.count(tail) != 1:
    sys.exit('omniPageToCanvasRows anchor matched %d times' % text.count(tail))
text = text.replace(tail, block + tail)

PATCHES.mkdir(parents=True, exist_ok=True)
(PATCHES / 'OmniBrowser.cpp.painthold.diff').write_text(
    ''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
                                 'a/engine/entry/OmniBrowser.cpp', 'b/engine/entry/OmniBrowser.cpp')))
target.write_bytes((text.replace('\n', '\r\n') if crlf else text).encode('utf-8'))
(entry / 'OmniPaintHold.h').write_bytes(header)
print('patched %s %s (%d edits + the C-003-R2 block, %d lines)'
      % (target.name, hashlib.sha256(text.encode()).hexdigest()[:12], len(EDITS), block.count('\n')))
print('copied OmniPaintHold.h %s (reviewed)' % HEADER_SHA[:12])
