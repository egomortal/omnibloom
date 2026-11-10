#!/usr/bin/env python3
"""OMNI_JANK_V1 (shell/title only): frame-time histograms for the shell's present loop, with per-long-frame
attribution to the phases the shell already measures. Every hook is a no-op unless /data/omni/jank.flag
exists when the shell first asks (one raw open(), kept in OmniJank.h). Nothing else changes: no timer, no
thread, no allocation, and the startup/bootstrap code is untouched.

Anchored edits on engine/entry/OmniBrowser.cpp in the tree given as argv[1]; each anchor must match exactly
once or the patch refuses. Writes a unified diff to ../patches/OmniBrowser.cpp.jank.diff.
usage: apply_jank.py <tree root>"""
import difflib, hashlib, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
N = HERE.parent
# the jank sources and the diff folder may live outside the build dir (OMNI_JANK_SRC / OMNI_JANK_PATCHES)
SRC = Path(os.environ.get('OMNI_JANK_SRC') or (N / 'src'))
PATCHES = Path(os.environ.get('OMNI_JANK_PATCHES') or (N / 'patches'))
MARK = 'OMNI_JANK_V1'
tree = Path(sys.argv[1])
entry = tree / 'engine/entry'
target = entry / 'OmniBrowser.cpp'

raw = target.read_bytes().decode('utf-8')
crlf = '\r\n' in raw
text = raw.replace('\r\n', '\n')
if MARK in text:
    print('already patched'); sys.exit(0)
before = text

EDITS = [
    # 1. the header
    ('after', '#include "config.h"\n',
     '#include "OmniJank.h" // OMNI_JANK_V1: shell frame-time histograms (off unless /data/omni/jank.flag)\n'),
    # 2. the log sink: OmniJank writes through the engine's log writer thread, as the rest of the shell does
    ('after', 'void log(const char* message) { OmniLocalScope traceScope(20); OmniMedia::Hw::shellLog(message); }\n',
     'static void omniJankLog(const char* line) { log(line); } // OMNI_JANK_V1\n'),
    # 3. every tick is one frame; any return path records it
    ('after', '    const auto frameStarted = SDL_GetPerformanceCounter();\n',
     '    OmniJank::begin(frameStarted); // OMNI_JANK_V1\n'
     '    struct OmniJankEnd { Uint64 started; ~OmniJankEnd() { OmniJank::end(started, SDL_GetPerformanceCounter(), SDL_GetTicks()); } } omniJankEnd { frameStarted }; // OMNI_JANK_V1\n'),
    # 4. page paint (WKPagePaint), full and partial: the same timed helper covers both
    ('after', '    if (ms > 400) ++c.over400;\n',
     '    OmniJank::addPhase(OmniJank::PhPagePaint, ms); // OMNI_JANK_V1\n'
     '    if (ms >= 100) OmniJank::pageBlocked(); // OMNI_JANK_V1: the web process had no backing store\n'),
    # 5. the 4K draw/compose
    ('after', '    profileDraw += drawFinished - drawStarted;\n',
     '    OmniJank::addPhase(OmniJank::PhDraw, omniGap.draw); // OMNI_JANK_V1\n'),
    # 6. the present hand-off (including the bounded wait for the presenter's vblank)
    ('after', 'static void omniPresentFrame()\n{\n',
     '    struct OmniJankPresent { Uint64 t0; ~OmniJankPresent() { OmniJank::addPhase(OmniJank::PhPresent,\n'
     '        1000.0 * double(SDL_GetPerformanceCounter() - t0) / double(SDL_GetPerformanceFrequency())); } }\n'
     '        omniJankPresent { SDL_GetPerformanceCounter() }; // OMNI_JANK_V1\n'),
    # 7. input: the gamepad tick and the SDL event loop, between the stall-trace input markers
    ('replace', '    OmniMedia::Hw::holePunchShellPhase(3); // OMNI_HOLEPUNCH_V7_STALLTRACE: input\n',
     '    OmniMedia::Hw::holePunchShellPhase(3); // OMNI_HOLEPUNCH_V7_STALLTRACE: input\n'
     '    const Uint64 omniJankInputStart = SDL_GetPerformanceCounter(); // OMNI_JANK_V1\n'),
    ('replace', '    OmniMedia::Hw::holePunchShellPhase(1); // OMNI_HOLEPUNCH_V7_STALLTRACE: input done\n',
     '    OmniJank::addPhase(OmniJank::PhInput, 1000.0 * double(SDL_GetPerformanceCounter() - omniJankInputStart) / double(SDL_GetPerformanceFrequency())); // OMNI_JANK_V1\n'
     '    OmniMedia::Hw::holePunchShellPhase(1); // OMNI_HOLEPUNCH_V7_STALLTRACE: input done\n'),
    # 8. the uBlock poll (every 500 ms, on this thread)
    ('replace',
     '    if (SDL_GetTicks() - lastBlockerPoll > 500) { OmniMedia::Hw::holePunchShellPhase(2); omniBlockerPoll(); OmniMedia::Hw::holePunchShellPhase(1); lastBlockerPoll = SDL_GetTicks(); } // OMNI_HOLEPUNCH_V7_STALLTRACE: uBlock\n',
     '    if (SDL_GetTicks() - lastBlockerPoll > 500) { OmniMedia::Hw::holePunchShellPhase(2); const Uint64 omniJankBlocker = SDL_GetPerformanceCounter(); omniBlockerPoll();\n'
     '        OmniJank::addPhase(OmniJank::PhBlocker, 1000.0 * double(SDL_GetPerformanceCounter() - omniJankBlocker) / double(SDL_GetPerformanceFrequency())); // OMNI_JANK_V1\n'
     '        OmniMedia::Hw::holePunchShellPhase(1); lastBlockerPoll = SDL_GetTicks(); } // OMNI_HOLEPUNCH_V7_STALLTRACE: uBlock\n'),
    # 9. the hole-punch video poll
    ('replace',
     '    if (OmniMedia::Hw::holePunchPoll()) omniShellDirty = true; // OMNI_HOLEPUNCH_V1: new video picture or rect\n',
     '    { const Uint64 omniJankVideo = SDL_GetPerformanceCounter(); // OMNI_JANK_V1\n'
     '      if (OmniMedia::Hw::holePunchPoll()) omniShellDirty = true; // OMNI_HOLEPUNCH_V1: new video picture or rect\n'
     '      OmniJank::addPhase(OmniJank::PhVideo, 1000.0 * double(SDL_GetPerformanceCounter() - omniJankVideo) / double(SDL_GetPerformanceFrequency())); } // OMNI_JANK_V1\n'),
    # 10. what the frame did
    ('after', '    ++omniCensus.draws; ++(omniPlan == 1 ? omniCensus.regional : omniCensus.full);\n',
     '    OmniJank::state(true, omniPageCopied, true, omniPlan == 0, omniPlan == 1); // OMNI_JANK_V1\n'),
    # 11. the harness label: a runner writes a word into /data/omni/jank-mark.txt and the window is cut there.
    #     Polled once a second beside the capture flag, never per frame.
    ('after',
     '    if (SDL_GetTicks() >= omniCaptureCheckAt) { omniCaptureCheckAt = SDL_GetTicks() + 1000; omniCaptureWanted = !access("/data/omni/capture-preview.flag", F_OK); }\n',
     '    omniJankMarkPoll(); // OMNI_JANK_V1: the harness section label, once a second\n'),
    # 12. install the sink before the main loop, and write the totals when it returns
    ('after', '    log("display ready; browser running");\n',
     '    if (OmniJank::on()) { OmniJank::setSink(omniJankLog, double(SDL_GetPerformanceFrequency())); log("OMNI_JANK_V1 on (/data/omni/jank.flag): shell frame histograms"); } // OMNI_JANK_V1\n'),
    ('after', '    log("main loop returned");\n',
     '    OmniJank::dumpTotal(); // OMNI_JANK_V1\n'),
]

# the mark poller needs a definition before its only call site (inside draw-time code), so it goes next to the sink
MARK_POLL = '''static void omniJankMarkPoll() // OMNI_JANK_V1: /data/omni/jank-mark.txt names the current section ("scroll", "load", "video")
{
    if (!OmniJank::on()) return;
    static char last[32] = "";
    char now[32] = "";
    const int fd = ::open("/data/omni/jank-mark.txt", O_RDONLY);
    if (fd >= 0) {
        const ssize_t got = ::read(fd, now, sizeof now - 1);
        ::close(fd);
        if (got > 0) {
            now[got] = 0;
            for (char* p = now; *p; ++p) if (*p == '\\n' || *p == '\\r') { *p = 0; break; }
        } else now[0] = 0;
    }
    if (strcmp(now, last)) { memcpy(last, now, sizeof last); if (now[0]) OmniJank::mark(now); }
}
'''


def apply_edits(s, edits):
    for kind, anchor, body in edits:
        n = s.count(anchor)
        if n != 1:
            sys.exit('anchor matched %d times: %r' % (n, anchor[:110]))
        s = s.replace(anchor, anchor + body if kind == 'after' else body)
    return s


text = apply_edits(text, EDITS)
# the poller definition right after the sink helper (so it precedes every call)
hook = 'static void omniJankLog(const char* line) { log(line); } // OMNI_JANK_V1\n'
assert text.count(hook) == 1
text = text.replace(hook, hook + MARK_POLL)

PATCHES.mkdir(parents=True, exist_ok=True)
(PATCHES / 'OmniBrowser.cpp.jank.diff').write_text(
    ''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
                                 'a/engine/entry/OmniBrowser.cpp', 'b/engine/entry/OmniBrowser.cpp')))
target.write_bytes((text.replace('\n', '\r\n') if crlf else text).encode('utf-8'))

header = (SRC / 'OmniJank.h').read_bytes()
(entry / 'OmniJank.h').write_bytes(header)
print('patched %s %s (%d edits + the poller)' % (target.name, hashlib.sha256(text.encode()).hexdigest()[:12], len(EDITS)))
print('copied OmniJank.h %s' % hashlib.sha256(header).hexdigest()[:12])
