"""OMNI_C56_VIDEOFIX2: python3 tools/patch_c56_videofix2.py <dl2-candidate-56b entry/OmniBrowser.cpp> <output>
Exact-match replacements (each must match once), CRLF kept."""
import sys
src = open(sys.argv[1], 'rb').read().decode('utf-8')
assert '\r\n' in src
reps = [
# 1. kill switch + state, next to VIDEOFIX1's
("""static bool omniVideoFixOn()
{
    static const bool on = access("/data/omni/c56-videofix-disabled.flag", F_OK) != 0;
    return on;
}
""",
"""static bool omniVideoFixOn()
{
    static const bool on = access("/data/omni/c56-videofix-disabled.flag", F_OK) != 0;
    return on;
}
// OMNI_C56_VIDEOFIX2: WebKit's fullscreen media-control bar stays shown while it keeps getting mouse moves, or while the mouse
// rests on it. During a fullscreen video (a video on the plane) the shell (a) sends no mouse move whose position equals the last
// one it sent (a stick held past its dead zone with the pointer clamped at a screen edge sent one every tick), and (b) after 3 s
// without a sent mouse event tells the page once that the mouse is at the middle of the screen (the drawn pointer stays where it
// is; the next real pointer move goes to the page as usual), so the bar can fade as in 54. Kill switch:
// /data/omni/c56-videofix2-disabled.flag (= 56b).
static bool omniVideoFix2On()
{
    static const bool on = access("/data/omni/c56-videofix2-disabled.flag", F_OK) != 0;
    return on;
}
static struct { float x = -1e9f, y = -1e9f; uint32_t lastSent = 0; bool parked = false; unsigned sent = 0, dropped = 0, parks = 0; } omniFix2;
"""),
# 2. mouse(): drop same-position moves during a fullscreen video; note what was sent
("""    if (!active() || settingsOpen || active()->crashed || pointerY < offset || pointerY >= omniPageBottom()) return;
    WKPageHandleMouseEvent(active()->page, WKMouseEventMake(type, kWKEventMouseButtonLeftButton,
""",
"""    if (!active() || settingsOpen || active()->crashed || pointerY < offset || pointerY >= omniPageBottom()) return;
    if (omniVideoFix2On() && pageFullscreen && OmniMedia::Hw::holePunchActive()) { // OMNI_C56_VIDEOFIX2
        if (type == kWKEventMouseMove && pointerX == omniFix2.x && pointerY == omniFix2.y) { ++omniFix2.dropped; return; }
        ++omniFix2.sent; omniFix2.parked = false; omniFix2.lastSent = SDL_GetTicks();
    }
    omniFix2.x = pointerX; omniFix2.y = pointerY;
    WKPageHandleMouseEvent(active()->page, WKMouseEventMake(type, kWKEventMouseButtonLeftButton,
"""),
# 3. tick(): park the page's mouse after 3 s idle; a 5 s counter line
("""    const uint32_t omniSafetyMs = omniS1 && !omniVideoFix ? 10000 : 500;
""",
"""    const uint32_t omniSafetyMs = omniS1 && !omniVideoFix ? 10000 : 500;
    if (omniVideoFix2On() && pageFullscreen && OmniMedia::Hw::holePunchActive() && active() && !active()->crashed && !omniOverlayOpen() && !settingsOpen) { // OMNI_C56_VIDEOFIX2
        if (!omniFix2.lastSent) omniFix2.lastSent = omniNow;
        if (!omniFix2.parked && omniNow - omniFix2.lastSent >= 3000) {
            omniFix2.parked = true; ++omniFix2.parks;
            WKPageHandleMouseEvent(active()->page, WKMouseEventMake(kWKEventMouseMove, kWKEventMouseButtonLeftButton,
                WKPointMake(width / 2.0 * displayScale * omniPageScale, (height / 2.0 - omniPageTop()) * displayScale * omniPageScale), 0, 0));
        }
        static uint32_t since = 0; static unsigned lines = 0;
        if (!since) since = omniNow;
        if (omniNow - since >= 5000) {
            since = omniNow;
            if (lines < 200) {
                ++lines;
                char line[200];
                snprintf(line, sizeof line, "video fix 2 (5 s): mouse sent %u, same-position dropped %u, parked %u, pointer %.0f,%.0f%s",
                    omniFix2.sent, omniFix2.dropped, omniFix2.parks, pointerX, pointerY, omniFix2.parked ? " (page mouse parked)" : "");
                log(line);
            }
            omniFix2.sent = omniFix2.dropped = omniFix2.parks = 0;
        }
    } else omniFix2.lastSent = 0;
"""),
]
for old, new in reps:
    o = old.replace('\n', '\r\n'); n = new.replace('\n', '\r\n')
    c = src.count(o)
    assert c == 1, (c, old[:80])
    src = src.replace(o, n)
open(sys.argv[2], 'wb').write(src.encode('utf-8'))
print('patched', len(reps), 'replacements')
