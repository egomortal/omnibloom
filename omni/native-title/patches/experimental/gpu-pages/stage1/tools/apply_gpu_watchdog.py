#!/usr/bin/env python3
"""OMNI_GPU_WATCHDOG_V1 (2026-11-16): a GPU STALL WATCHDOG for layers mode (stage 1). With layers on, the console was
seen to hard-hang ~15-45 s after launch and a video to stop with data buffered; the driver's own stall line (RADV
winsys, 10 s) never reached the log. PS5_Vulkan issue #3 reports the class (a submission that never completes).
This turns a GPU wait pending longer than /data/omni/gpu-watchdog-ms.txt (default 1500; 0/off disables) into
"layers off for this session" BEFORE the driver's 10 s: see stage1/src/ogp-s1-watchdog.h (pure logic, host-tested by
tools/test_gpu_watchdog.cpp) for the files it writes and the second-stall-same-day rule.

Modes (each idempotent, every anchor must be found exactly once, CRLF kept):
  child   <stage1/src>          ENGINE CHILD. ogp-s1-surface.inc: brackets every GPU wait of the compositor threads
                                (sync readback, tile-diff readback, async fence/map) and each whole frame (willRender..
                                didRender); a watchdog thread (never the main thread) trips once, records the trip
                                (fsync'd), logs one line and _exit()s the page process, whose compositor thread is stuck
                                inside Mesa and cannot be freed in place. ogp-s1-child.c: the constructor keeps stage 1
                                off while gpu-pages-stage1-session-off.flag exists, so the reloaded page draws on the CPU.
  relink  <build-omni-gpupages-child-relink.sh>  copies the new header into tree A; symbol-gate words
                                'OmniGpuWatchdog', 'ogp_s1_ctor'.
  copylist <tools/apply_gpupages_child.py>       copies the header with the other stage-1 files (fresh trees: the
                                TITLE also compiles ogp-s1-surface.inc for its in-process engine; nothing runs there).
  title   <stage1/src-title>    TITLE. OmniGpuPagesService.cpp: clears the session flag at title start; refuses binds
                                while it exists; omni_gpu_watchdog_title_stall(): a present stall with stage 1 serving
                                records a trip and SIGKILLs the bound page processes (no more child submissions).
  present <dir holding OmniGpuPresent.cpp>       TITLE. Its existing 1 s fence/acquire/present watchdogs and the 5 s
                                reaper call omni_gpu_watchdog_title_stall() (weak: absent, nothing changes).
  shell   <OmniBrowser.cpp of the TITLE tree>    TITLE. The page-process crash handler shows the watchdog's notice
                                (the existing notice() bar + tab message + log) and reloads the page once.
usage: apply_gpu_watchdog.py MODE PATH"""
import sys
from pathlib import Path

MARK = 'OMNI_GPU_WATCHDOG_V1'


def patch(path, edits, need=None):
    p = Path(path)
    raw = p.read_bytes().decode('utf-8')
    crlf = '\r\n' in raw
    t = raw.replace('\r\n', '\n')
    if MARK in t:
        print('already', p.name)
        return
    if need and need not in t:
        sys.exit('%s: %r missing: wrong file or an earlier patch is not applied' % (p.name, need))
    for old, new in edits:
        n = t.count(old)
        if n != 1:
            sys.exit('%s: anchor found %d times: %r' % (p.name, n, old[:100]))
        t = t.replace(old, new, 1)
    backup = p.with_name(p.name + '.before-gpuwatchdog')
    if not backup.exists():
        backup.write_bytes(raw.encode('utf-8'))
    p.write_bytes((t.replace('\n', '\r\n') if crlf else t).encode('utf-8'))
    print('patched %s (%d edits)' % (p.name, len(edits)))


# ------------------------------------------------------------------------------------------------------ engine child
SURFACE_HELPERS = r'''
// OMNI_GPU_WATCHDOG_V1 (ogp-s1-watchdog.h): every place a compositor thread can wait on the GPU is bracketed (GpuScope),
// and so is each whole frame (willRender..didRender, the looser frame limit). A thread of its own looks every
// pollMs(); the first wait pending past the limit records the trip (session flag; on a second stall the same day the
// kill switch), logs one line and ends this page process: its compositor thread is stuck inside Mesa's wait and cannot
// be freed in place (tearing the compositor down joins that thread, which would block the main thread). The UI then
// reloads the page in a new process, which starts with stage 1 off (ogp-s1-child.c). The main thread never waits here.
static OmniGpuWatchdog::Watch s_gpuWatch;
static std::atomic<int> s_gpuLimitMs { -1 };   // -1: not started, 0: off, else ms per GPU wait
static bool gpuWatchOn() { return s_gpuLimitMs.load(std::memory_order_relaxed) > 0; }
struct GpuScope {
    int slot;
    GpuScope(OmniGpuWatchdog::Kind kind, uint32_t what) : slot(gpuWatchOn() ? s_gpuWatch.begin(kind, what, nowMs()) : -1) { }
    ~GpuScope() { s_gpuWatch.end(slot); }
    GpuScope(const GpuScope&) = delete;
    GpuScope& operator=(const GpuScope&) = delete;
};
static void* gpuWatchdogMain(void*)
{
    const int limit = s_gpuLimitMs.load();
    for (;;) {
        usleep(static_cast<useconds_t>(OmniGpuWatchdog::pollMs(limit)) * 1000);
        uint32_t what = 0;
        double pending = 0;
        if (!s_gpuWatch.check(nowMs(), limit, &what, &pending)) continue;
        const long long now = static_cast<long long>(time(nullptr));
        char line[700];
        OmniGpuWatchdog::recordTrip("/data/omni", OmniGpuWatchdog::dayOf(now), now, "engine", getpid(), what, pending, limit,
            "this page process exits now and the page reloads drawing on the CPU", line, sizeof line);
        fprintf(stderr, "%s\n", line);
        fflush(stderr);
        _exit(OmniGpuWatchdog::kExitCode);
    }
    return nullptr;
}
static void gpuWatchdogStart()   // main thread (created()), once per process, only with stage 1 ready
{
    const int limit = OmniGpuWatchdog::readLimitMs("/data/omni");
    int expect = -1;
    if (!s_gpuLimitMs.compare_exchange_strong(expect, limit)) return;
    if (!limit) {
        fprintf(stderr, "OMNI GPU WATCHDOG pid=%d: off (/data/omni/gpu-watchdog-ms.txt)\n", getpid());
        return;
    }
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setstacksize(&attr, 256u << 10);
    pthread_t thread;
    const int rc = pthread_create(&thread, &attr, gpuWatchdogMain, nullptr);
    pthread_attr_destroy(&attr);
    if (rc) {
        s_gpuLimitMs = 0;
        fprintf(stderr, "OMNI GPU WATCHDOG pid=%d: thread FAILED (%d): no watchdog in this process\n", getpid(), rc);
        return;
    }
    pthread_detach(thread);
    fprintf(stderr, "OMNI GPU WATCHDOG pid=%d: on: %d ms per GPU wait, %d ms per frame\n", getpid(), limit, OmniGpuWatchdog::frameLimitMs(limit));
}
'''

NOWMS = ('static double nowMs()\n{\n    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);\n'
         '    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;\n}\n')

SYNC_READ = ('    glReadPixels(bounds.x(), bounds.y(), bounds.width(), bounds.height(), state->bgra ? GL_BGRA_EXT : GL_RGBA, '
             'GL_UNSIGNED_BYTE, pixels);\n')
DIFF_READ = '    glReadPixels(0, 0, cellsX, cellsY, GL_RGBA, GL_UNSIGNED_BYTE, s.maskBuf.data());\n'
PACE = ('    bool ours = didRenderImpl(surface);\n    if (!ours) return false;\n    ++s_didCount;\n'
        '    static const bool pace = access("/data/omni/gpu-pages-nopace.flag", F_OK) != 0;\n    State* state = find(surface);\n')

CHILD_SURFACE = [
    ('#include <sys/mman.h>\n',
     '#include <sys/mman.h>\n#include <pthread.h>\n'
     '#include "ogp-s1-watchdog.h"   // OMNI_GPU_WATCHDOG_V1: timer + trip files (no GPU types: host-tested)\n'),
    ('    double tWill { 0 };   // OMNI_GPUPAGES_TIMING_V2\n',
     '    double tWill { 0 };   // OMNI_GPUPAGES_TIMING_V2\n'
     '    int wdFrame { -1 };   // OMNI_GPU_WATCHDOG_V1: the watch slot of the frame in progress (compositor thread)\n'),
    (NOWMS, NOWMS + SURFACE_HELPERS),
    ('    if (!omniGpuPagesProcessReady()) return;   // the default: nothing is recorded, upstream runs unchanged\n',
     '    if (!omniGpuPagesProcessReady()) return;   // the default: nothing is recorded, upstream runs unchanged\n'
     '    gpuWatchdogStart();   // OMNI_GPU_WATCHDOG_V1\n'),
    ('    state->tWill = nowMs();\n    ++s_willCount;\n',
     '    state->tWill = nowMs();\n    ++s_willCount;\n'
     '    s_gpuWatch.end(state->wdFrame);   // OMNI_GPU_WATCHDOG_V1: the whole frame, willRender..didRender\n'
     '    state->wdFrame = gpuWatchOn() ? s_gpuWatch.begin(OmniGpuWatchdog::kFrame, OmniGpuWatchdog::kWhatFrame, state->tWill) : -1;\n'),
    (DIFF_READ,
     '    {\n        GpuScope wd(OmniGpuWatchdog::kWait, OmniGpuWatchdog::kWhatTileDiff);   // OMNI_GPU_WATCHDOG_V1: submit + wait\n'
     '    ' + DIFF_READ + '    }\n'),
    ('    if (!s.ringPending) return false;\n    State::Slot& slot = s.ring[s.ringHead];\n',
     '    if (!s.ringPending) return false;\n'
     '    GpuScope wd(OmniGpuWatchdog::kWait, OmniGpuWatchdog::kWhatAsyncFence);   // OMNI_GPU_WATCHDOG_V1: fence wait + map\n'
     '    State::Slot& slot = s.ring[s.ringHead];\n'),
    (SYNC_READ,
     '    {\n        GpuScope wd(OmniGpuWatchdog::kWait, OmniGpuWatchdog::kWhatReadback);   // OMNI_GPU_WATCHDOG_V1: submit + wait\n'
     '    ' + SYNC_READ + '    }\n'),
    (PACE,
     PACE + '    if (state) { s_gpuWatch.end(state->wdFrame); state->wdFrame = -1; }   // OMNI_GPU_WATCHDOG_V1: frame done (pacing is not GPU)\n'),
    ('    if (state->context != eglGetCurrentContext()) return;   // not ours to delete in another context\n',
     '    s_gpuWatch.end(state->wdFrame);   // OMNI_GPU_WATCHDOG_V1\n'
     '    if (state->context != eglGetCurrentContext()) return;   // not ours to delete in another context\n'),
]

CHILD_C = [
    ('#define OGP_S1_OFF  "/data/omni/gpu-pages-stage1-off.flag"\n',
     '#define OGP_S1_OFF  "/data/omni/gpu-pages-stage1-off.flag"\n'
     '/* OMNI_GPU_WATCHDOG_V1: written by the GPU stall watchdog (ogp-s1-watchdog.h), removed when the title starts */\n'
     '#define OGP_S1_SESSION_OFF "/data/omni/gpu-pages-stage1-session-off.flag"\n'),
    ('    if (access(OGP_S1_FLAG, F_OK) || !access(OGP_S1_OFF, F_OK)) return;\n',
     '    if (access(OGP_S1_FLAG, F_OK) || !access(OGP_S1_OFF, F_OK)) return;\n'
     '    if (!access(OGP_S1_SESSION_OFF, F_OK)) return;   /* OMNI_GPU_WATCHDOG_V1: a stall turned layers off this session */\n'),
]

# ------------------------------------------------------------------------------------------------------ build scripts
RELINK = [
    ('CHANGED=""\nfor f in ogp-s1-surface.inc ogp-s1-drawingarea.inc ogp-s1-policy.h ogp-s1-tcprobe.inc ogp-s1b-async.inc; do\n',
     'CHANGED=""\n'
     '# OMNI_GPU_WATCHDOG_V1: ogp-s1-watchdog.h is new (the surface includes it): copied in even though tree A has none yet\n'
     '[ -f "$T/$CG/ogp-s1-watchdog.h" ] && cmp -s "$S1/src/ogp-s1-watchdog.h" "$T/$CG/ogp-s1-watchdog.h" || '
     '{ cp "$S1/src/ogp-s1-watchdog.h" "$T/$CG/ogp-s1-watchdog.h" && chown builder:builder "$T/$CG/ogp-s1-watchdog.h" && CHANGED="$CHANGED ogp-s1-watchdog.h"; }\n'
     'for f in ogp-s1-surface.inc ogp-s1-drawingarea.inc ogp-s1-policy.h ogp-s1-tcprobe.inc ogp-s1b-async.inc; do\n'),
    ("           'omniUBlockPopupBlocked', '(anonymous namespace)::filterFailure()')\n",
     "           'omniUBlockPopupBlocked', '(anonymous namespace)::filterFailure()',\n"
     "           # OMNI_GPU_WATCHDOG_V1: the header's inline functions (surface TU) and the session check in ogp-s1-child.c's constructor\n"
     "           'OmniGpuWatchdog', 'ogp_s1_ctor')\n"),
]
COPYLIST = [
    ("for f in ('ogp-s1-policy.h', 'ogp-s1-drawingarea.inc', 'ogp-s1-surface.inc', 'ogp-s1-tcprobe.inc'):\n",
     "for f in ('ogp-s1-policy.h', 'ogp-s1-drawingarea.inc', 'ogp-s1-surface.inc', 'ogp-s1-tcprobe.inc',\n"
     "          'ogp-s1-watchdog.h'):   # OMNI_GPU_WATCHDOG_V1: included by the surface\n"),
]

# ------------------------------------------------------------------------------------------------------ title
TITLE_TAIL = r'''
// OMNI_GPU_WATCHDOG_V1, title side. OmniGpuPresent's own watchdogs (1 s fence / acquire / present waits, the 5 s reaper)
// call this when a present stalls. With stage 1 serving, a page process's GPU work shares the one GPU ring, so the stall
// is treated like an engine-side trip: layers off for this session (a second stall the same day: the kill switch), no
// new bind, and every bound page process is stopped so it submits nothing more; the shell reloads its pages, which then
// draw on the CPU. File writes and kill() only: never a GPU wait. Stage 1 not serving: nothing.
extern "C" void omni_gpu_watchdog_title_stall(const char* what, double waitedMs)
{
    if (!s_wdRunning.load() || s_wdStalled.exchange(true)) return;
    const long long now = static_cast<long long>(time(nullptr));
    char line[700];
    OmniGpuWatchdog::recordTrip("/data/omni", OmniGpuWatchdog::dayOf(now), now, "title", static_cast<int>(getpid()),
        OmniGpuWatchdog::kWhatPresent, waitedMs, 1000, "the page processes bound to the broker are stopped; pages reload drawing on the CPU",
        line, sizeof line);
    omni_native_log("%s [%s]", line, what ? what : "present");
    int stopped = 0;
    for (auto& slot : s_wdPids) {
        const int pid = slot.exchange(0);
        if (pid > 0 && ogp_s1_kill && !childAbsent(pid) && !ogp_s1_kill(pid, SIGKILL)) ++stopped;
    }
    omni_native_log("OMNI GPU WATCHDOG: title stopped %d page process(es)", stopped);
}
'''
TITLE = [
    ('#include "server.h"\n',
     '#include "server.h"\n#include "../src/ogp-s1-watchdog.h"   // OMNI_GPU_WATCHDOG_V1 (sibling of src-title)\n#include <atomic>\n#include <ctime>\n'),
    ('constexpr int kSlots = 30;\n',
     'constexpr int kSlots = 30;\n'
     '// OMNI_GPU_WATCHDOG_V1: serving (stage 1 on), a title-side stall seen, and the page processes given an endpoint\n'
     'std::atomic<bool> s_wdRunning { false }, s_wdStalled { false };\n'
     'std::atomic<int> s_wdPids[kSlots] {};\n'),
    ('    bool started = false, failed = false;\n    int slots = 0;\n',
     '    bool started = false, failed = false;\n    int slots = 0;\n    s_wdRunning = true;   // OMNI_GPU_WATCHDOG_V1\n'),
    ('                if (failed)\n                    snprintf(text, sizeof text, "error=broker-start-failed\\n");\n',
     '                if (s_wdStalled.load() || OmniGpuWatchdog::sessionOff("/data/omni"))   // OMNI_GPU_WATCHDOG_V1\n'
     '                    snprintf(text, sizeof text, "error=gpu-watchdog (a GPU stall turned layers off for this session)\\n");\n'
     '                else if (failed)\n                    snprintf(text, sizeof text, "error=broker-start-failed\\n");\n'),
    ('                        ++slots;\n',
     '                        ++slots;\n'
     '                        if (slots <= kSlots) s_wdPids[slots - 1] = pid;   // OMNI_GPU_WATCHDOG_V1: stopped on a title-side stall\n'),
    ('    if (access(kFlag, F_OK) || !access(kOff, F_OK)) return;   // the default: nothing starts\n',
     '    OmniGpuWatchdog::sessionStart("/data/omni");   // OMNI_GPU_WATCHDOG_V1: a stall\'s "layers off" lasts one title session\n'
     '    if (access(kFlag, F_OK) || !access(kOff, F_OK)) return;   // the default: nothing starts\n'),
    ('} // namespace\n', '} // namespace\n' + TITLE_TAIL),
]

PRESENT = [
    ('#include <vulkan/vulkan.h>\n',
     '#include <vulkan/vulkan.h>\n'
     '// OMNI_GPU_WATCHDOG_V1: OmniGpuPagesService.cpp (stage-1 title builds). Weak: absent, a stall only sets g.hung as before.\n'
     'extern "C" void omni_gpu_watchdog_title_stall(const char* what, double waitedMs) __attribute__((weak));\n'),
    ('g.hung = true; plog(true, "WATCHDOG: no swapchain image within 1 s (GPU or display stalled)");',
     'g.hung = true; if (omni_gpu_watchdog_title_stall) omni_gpu_watchdog_title_stall("acquire", 1000); '
     'plog(true, "WATCHDOG: no swapchain image within 1 s (GPU or display stalled)");'),
    ('g.hung = true; plog(true, "WATCHDOG: a frame did not finish on the GPU within 1 s");',
     'g.hung = true; if (omni_gpu_watchdog_title_stall) omni_gpu_watchdog_title_stall("frame fence", 1000); '
     'plog(true, "WATCHDOG: a frame did not finish on the GPU within 1 s");'),
    ('g.hung = true; plog(true, "WATCHDOG: present %llu not shown within 1 s"',
     'g.hung = true; if (omni_gpu_watchdog_title_stall) omni_gpu_watchdog_title_stall("present wait", 1000); '
     'plog(true, "WATCHDOG: present %llu not shown within 1 s"'),
    ('            watchdogFired = true; g.hung = true;\n',
     '            watchdogFired = true; g.hung = true;\n'
     '            if (omni_gpu_watchdog_title_stall) omni_gpu_watchdog_title_stall("present call not returning", 5000);   // OMNI_GPU_WATCHDOG_V1\n'),
]

SHELL_HELPER = r'''// OMNI_GPU_WATCHDOG_V1: a page process stopped by the GPU stall watchdog leaves the text to show
// (/data/omni/gpu-pages/watchdog-notice.txt, written by ogp-s1-watchdog.h). Taken once; every tab whose process went
// with it in the next 10 s gets the same text and reload.
static bool omniGpuWatchdogNotice(std::string& out)
{
    static std::string last;
    static uint32_t lastAt = 0;
    const char* path = "/data/omni/gpu-pages/watchdog-notice.txt";
    if (FILE* f = fopen(path, "r")) {
        char buf[320] = "";
        size_t n = fread(buf, 1, sizeof buf - 1, f);
        fclose(f);
        unlink(path);
        buf[n] = 0;
        while (n && (buf[n - 1] == '\n' || buf[n - 1] == '\r')) buf[--n] = 0;
        if (!n) return false;
        last = buf;
        lastAt = SDL_GetTicks() ? SDL_GetTicks() : 1;
    } else if (!lastAt || SDL_GetTicks() - lastAt > 10000)
        return false;
    out = last;
    return true;
}
'''
NOTICE = 'void notice(const std::string& text) { status = text; statusUntil = SDL_GetTicks() + 3500; }\n'
SHELL = [
    (NOTICE, NOTICE + SHELL_HELPER),
    ('        log("web process crashed");\n    };\n',
     '        log("web process crashed");\n'
     '        if (std::string text; omniGpuWatchdogNotice(text)) {   // OMNI_GPU_WATCHDOG_V1: layers went off; the new process draws on the CPU\n'
     '            tab.message = text;\n'
     '            notice(text);\n'
     '            log(text.c_str());\n'
     '            WKPageReload(tab.page);\n'
     '        }\n'
     '    };\n'),
]

if len(sys.argv) != 3:
    sys.exit(__doc__)
mode, arg = sys.argv[1], Path(sys.argv[2])
if mode == 'child':
    if not (arg / 'ogp-s1-watchdog.h').is_file():
        sys.exit('ogp-s1-watchdog.h missing next to ogp-s1-surface.inc')
    patch(arg / 'ogp-s1-surface.inc', CHILD_SURFACE, need='OMNI_GPUPAGES_ASYNCREAD_V1')
    patch(arg / 'ogp-s1-child.c', CHILD_C)
elif mode == 'relink':
    patch(arg, RELINK, need='SYMBOL GATE')
elif mode == 'copylist':
    patch(arg, COPYLIST, need='OMNI_GPU_PAGES_STAGE1_V1')
elif mode == 'title':
    if not (arg.parent / 'src' / 'ogp-s1-watchdog.h').is_file():
        sys.exit('../src/ogp-s1-watchdog.h missing next to src-title')
    patch(arg / 'OmniGpuPagesService.cpp', TITLE)
elif mode == 'present':
    patch(arg / 'OmniGpuPresent.cpp', PRESENT, need='OMNI_GPU_PRESENT_V1')
elif mode == 'shell':
    patch(arg, SHELL, need='nav.webProcessDidCrash')
else:
    sys.exit(__doc__)
print('applied ' + MARK + ' (' + mode + ')')
