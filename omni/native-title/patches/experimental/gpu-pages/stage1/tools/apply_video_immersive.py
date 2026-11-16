#!/usr/bin/env python3
"""OMNI_VIDEO_IMMERSIVE_V1 (2026-11-16, owner: on some sites the top bar keeps coming back while a video plays
"fullscreen"). Those sites don't use the browser's fullscreen: they stretch the player over their own page, so Omni
sees an ordinary page and its Auto-hide brings the bars back on every pointer move or stick touch.

Omni's own video plane already knows where the playing video is (the hole-punch rect, view pixels). When that video
covers most of the page view (at least 3/4 of it, and edge to edge across or down: a full-page player, not a
theater-mode one), Omni treats the page like fullscreen for its bars:
  - pointer moves, the sticks, the D-pad and Cross/Circle/Square no longer bring the bars back;
  - the bars slide away 3 s after the last input wherever the pointer is;
  - Triangle (address), Options, R3, L1/R1 (tabs) and touchpad/Back still show them, as before.
Only with Auto-hide on (the default): with it off the bars are part of the layout and stay. Real fullscreen is
unchanged. No page script, no polling of the page: one rect read per tick from the video plane (a mutex).
usage: apply_video_immersive.py <engine tree>   (edits engine/media/OmniHwService.{h,cpp}, engine/entry/OmniBrowser.cpp)"""
import sys
from pathlib import Path

MARK = 'OMNI_VIDEO_IMMERSIVE_V1'
root = Path(sys.argv[1]) / 'engine'


def patch(rel, edits):
    p = root / rel
    raw = p.read_bytes()
    nl = '\r\n' if b'\r\n' in raw else '\n'
    s = raw.decode('utf-8')
    if MARK in s:
        return rel + ': already'
    for old, new in edits:
        old, new = old.replace('\n', nl), new.replace('\n', nl)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (rel, s.count(old), old[:90]))
        s = s.replace(old, new, 1)
    p.write_bytes(s.encode('utf-8'))
    return rel + ': applied'


HEADER = [(
    'bool holePunchActive();\n',
    'bool holePunchActive();\n'
    '// OMNI_VIDEO_IMMERSIVE_V1: the playing video\'s rect in view pixels; false when no video uses the plane.\n'
    'bool holePunchRect(int& x, int& y, int& w, int& h);\n')]

SERVICE = [(
    '''bool holePunchActive()
{
    std::lock_guard<std::mutex> l(plane.lock);
    return plane.attached && plane.owner >= 0;
}
''', '''bool holePunchActive()
{
    std::lock_guard<std::mutex> l(plane.lock);
    return plane.attached && plane.owner >= 0;
}
bool holePunchRect(int& x, int& y, int& w, int& h)   // OMNI_VIDEO_IMMERSIVE_V1
{
    std::lock_guard<std::mutex> l(plane.lock);
    if (!plane.attached || plane.owner < 0) return false;
    x = plane.rect.x; y = plane.rect.y; w = plane.rect.w; h = plane.rect.h;
    return w > 0 && h > 0;
}
''')]

BROWSER = [
    # the test, before the bar wake functions
    ('''// OMNI_STYLE_V1: auto-hiding bars, progress and toast animation state ----------------------------
static void omniChromeWake(bool pointerMotion)
{
    omniLastInput = SDL_GetTicks();
''', '''// OMNI_VIDEO_IMMERSIVE_V1: a playing video covers most of the page view (a site's own "fullscreen" player).
// Updated once per tick in omniStyleTick from the video plane's rect.
static bool omniVideoImmersive = false;
static bool omniVideoFillsView()
{
    int x = 0, y = 0, w = 0, h = 0;
    if (!active() || pageFullscreen || !OmniMedia::Hw::holePunchRect(x, y, w, h)) return false;
    const double vw = renderWidth * omniPageScale, vh = renderPageHeight * omniPageScale;   // view pixels
    if (vw < 2 || vh < 2) return false;
    const double fw = w / vw, fh = h / vh;
    return fw * fh >= 0.75 && (fw >= 0.97 || fh >= 0.97);
}
// OMNI_STYLE_V1: auto-hiding bars, progress and toast animation state ----------------------------
static void omniChromeWake(bool pointerMotion)
{
    omniLastInput = SDL_GetTicks();
    if (omniVideoImmersive && !editing && !settingsOpen) return;   // OMNI_VIDEO_IMMERSIVE_V1: input stays with the video
'''),
    # explicit bar buttons still show the bars
    ('''static void omniChromeButton(int b)
{
''', '''static void omniChromeButton(int b)
{
    if (omniVideoImmersive && (b == SDL_CONTROLLER_BUTTON_Y || b == SDL_CONTROLLER_BUTTON_START || b == SDL_CONTROLLER_BUTTON_BACK
        || b == SDL_CONTROLLER_BUTTON_RIGHTSTICK || b == SDL_CONTROLLER_BUTTON_LEFTSHOULDER || b == SDL_CONTROLLER_BUTTON_RIGHTSHOULDER
        || b == SDL_CONTROLLER_BUTTON_TOUCHPAD)) { omniLastInput = SDL_GetTicks(); omniChromeWanted = true; return; }   // OMNI_VIDEO_IMMERSIVE_V1
'''),
    # tick: refresh the state; hide regardless of where the pointer is
    ('''    if (!omniAutoHideActive() || pageFullscreen) { omniChromeWanted = true; omniChromeT = omniChromeShown = 1; }
    else {
        if (editing || settingsOpen || !tab) omniChromeWanted = true;
        else if (omniChromeWanted && !tab->loading && !tab->crashed && tab->message.empty()
            && now - std::max(omniLastInput, tab->loadedAt) >= 3000 && pointerY >= top && pointerY < height - bottom)
''', '''    omniVideoImmersive = omniAutoHideActive() && omniVideoFillsView();   // OMNI_VIDEO_IMMERSIVE_V1
    if (!omniAutoHideActive() || pageFullscreen) { omniChromeWanted = true; omniChromeT = omniChromeShown = 1; }
    else {
        if (editing || settingsOpen || !tab) omniChromeWanted = true;
        else if (omniChromeWanted && !tab->loading && !tab->crashed && tab->message.empty()
            && now - std::max(omniLastInput, tab->loadedAt) >= 3000 && (omniVideoImmersive || (pointerY >= top && pointerY < height - bottom)))
'''),
]

print(patch('media/OmniHwService.h', HEADER))
print(patch('media/OmniHwService.cpp', SERVICE))
print(patch('entry/OmniBrowser.cpp', BROWSER))
