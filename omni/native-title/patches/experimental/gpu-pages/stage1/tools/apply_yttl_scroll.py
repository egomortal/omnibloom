import sys
p = sys.argv[1]
b = open(p, 'rb').read(); nl = b'\r\n' if b'\r\n' in b else b'\n'
s = b.decode('utf-8')
NL = nl.decode()
def rep(a, c):
    global s
    a = a.replace('\n', NL); c = c.replace('\n', NL)
    if s.count(a) != 1: sys.exit('anchor count %d: %r' % (s.count(a), a[:70]))
    s = s.replace(a, c, 1)

# 1. config line: `scroll N` = N px per frame tick, alternating down/up every 3 s after the page finished loading
rep('''                else if (l.rfind("fullscreen ", 0) == 0) y.fullscreenRequested = omniYtFullscreenOption(l);
''', '''                else if (l.rfind("fullscreen ", 0) == 0) y.fullscreenRequested = omniYtFullscreenOption(l);
                else if (l.rfind("scroll ", 0) == 0) omniYtScrollPx = std::clamp(atoi(l.c_str() + 7), 0, 200); // OMNI_YTTL_SCROLL_V1
''')
# 2. per frame in stage 2: scroll through the shell's own scroll() (the right stick / wheel path), once loading is done
rep('''        if (!y.sawVideo && OmniMedia::Hw::holePunchActive()) { y.sawVideo = true; omniYtEvent("video plane active"); }
''', '''        if (!y.sawVideo && OmniMedia::Hw::holePunchActive()) { y.sawVideo = true; omniYtEvent("video plane active"); }
        // OMNI_YTTL_SCROLL_V1 (test only, inert without `scroll N` in yt-timeline.txt): after the page finished loading and
        // 2 s more, scroll down for 3 s then up for 3 s, repeatedly, through scroll() (the right stick / wheel path).
        if (omniYtScrollPx > 0 && !loading && ms >= 4000) {
            if (!omniYtScrollStartMs) { omniYtScrollStartMs = ms; omniYtEvent("scroll test started"); }
            const uint32_t phase = (ms - omniYtScrollStartMs) / 3000;
            scroll((phase % 2) ? double(omniYtScrollPx) : -double(omniYtScrollPx));
        }
''')
# 3. reset per run, and the globals (before the YTTL runner)
rep('''        y.firstDirty = y.sawVideo = false; y.wasLoading = false; y.t0 = now; y.stage = 2;
''', '''        y.firstDirty = y.sawVideo = false; y.wasLoading = false; y.t0 = now; y.stage = 2;
        omniYtScrollStartMs = 0; // OMNI_YTTL_SCROLL_V1
''')
rep('''// One URL after another from /data/omni/yt-timeline.txt''', '''static int omniYtScrollPx = 0; static uint32_t omniYtScrollStartMs = 0; // OMNI_YTTL_SCROLL_V1: `scroll N` in yt-timeline.txt
// One URL after another from /data/omni/yt-timeline.txt''')
open(p, 'wb').write(s.encode('utf-8'))
print('applied OMNI_YTTL_SCROLL_V1 (4 anchors)')
