#!/usr/bin/env python3
"""OMNI_GPU_DEFAULT_ON_V1 (2026-11-17): the GPU present (OmniGpuPresent) and the GPU video conversion (OmniGpuVideo) are
ON by default, with an off switch each, instead of off unless a flag file exists.

Why
  Every console soak and gate since s3.2 ran with gpu-present.flag + gpu-video.flag (run_rc2's GPU2), but nothing ever
  wrote them for users: the owner's own PS5 (Bloom 0.5.4-bloom.1, 2026-11-17) runs SDL's software display and converts
  and scales every video frame to 4K on the CPU (movy.sx: "convert split 8-bit 2.81 ms (layer 3840x2160)"; the GPU
  conversion of the same layer takes 0.43 ms). So users ran the slower path that no soak covered.
  It is also the base the GPU blend (OMNI_GPU_MIX_V1) builds on.

What changes (console builds only; the host tests keep "flag present = on")
  OmniGpuPresent.cpp  __wrap_SDL_Init brings the GPU present up unless /data/omni/gpu-present-off.flag exists or a
                      self-test runs (any *-selftest.flag: some test modes have no real display window, and SDL's
                      software surface there is not ABGR8888). gpu-present.flag still turns it on and its option words
                      are still read. All of the set-up checks and the fallback to SDL's own present are unchanged.
  OmniGpuVideo.cpp    the GPU conversion starts unless /data/omni/gpu-video-off.flag exists (gpu-video.flag still read
                      for its words). Its verify-then-switch logic is unchanged (the CPU path until the GPU result
                      matched).
  The per-second video-fps.log line stays off unless one of the old flags exists (no new log by default).

Patches the persistent eboot workspace ("$NE", like apply_video_enhance_media.py). A patched tree prints "already".
Backups: <file>.before-gpu-default-on (first apply only).
usage: apply_gpu_default_on.py <eboot workspace root>"""
import shutil
import sys
from pathlib import Path

MARK = 'OMNI_GPU_DEFAULT_ON_V1'
HEADLESS_C = r"""// OMNI_GPU_DEFAULT_ON_V1_R2: the shell's own headless rule (OmniBrowser.cpp `const bool headless`): those test runs open
// no real display window (SDL's dummy surface is not ABGR8888), so the default stays off there. Visible test runs (the
// YouTube / site gates with youtube-visible-test.flag) get the GPU by default, as users do.
static bool %(fn)s()
{
    auto has = [](const char* n) { char p[96]; snprintf(p, sizeof p, "/data/omni/%%s", n); return access(p, F_OK) == 0; };
    return has("browser-selftest.flag") || has("blocker-selftest.flag") || has("input-selftest.flag") || has("google-selftest.flag")
        || (has("youtube-selftest.flag") && !has("youtube-visible-test.flag")) || has("widget-selftest.flag")
        || (has("feature-selftest.flag") && !has("media-visible-test.flag")) || has("ui-selftest.flag");
}
"""
root = Path(sys.argv[1])
present = root / 'src' / 'OmniGpuPresent.cpp'
video = root / 'engine' / 'media' / 'OmniGpuVideo.cpp'


def load(p):
    raw = p.read_bytes().decode('utf-8')
    nl = '\r\n' if raw.count('\r\n') * 2 > raw.count('\n') else '\n'
    return raw.replace('\r\n', '\n'), nl


def save(p, text, nl):
    bak = p.with_name(p.name + '.before-gpu-default-on')
    if not bak.exists():
        shutil.copy2(p, bak)
    p.write_bytes(text.replace('\n', nl).encode('utf-8'))


def edit(text, old, new, name, count=1):
    if text.count(old) != count:
        sys.exit('%s: anchor found %d times (want %d): %r' % (name, text.count(old), count, old[:90]))
    return text.replace(old, new)


done = []
for p in (present, video):
    if not p.exists():
        sys.exit('missing %s' % p)

t, nl = load(present)
if MARK in t:
    done.append('OmniGpuPresent.cpp: already')
else:
    old_init = 'extern "C" int __wrap_SDL_Init(uint32_t flags)\n{\n'
    helper = ('// ' + MARK + ': on by default (every console soak ran with it); /data/omni/gpu-present-off.flag turns it off.\n'
              '// gpu-present.flag still turns it on and still carries the option words (readOptions).\n'
              '// Self-test runs (any /data/omni/*-selftest.flag) keep the old rule (on only with gpu-present.flag): some test modes\n'
              '// open no real display window (their SDL surface is not ABGR8888), which the GPU present cannot take.\n'
              'static bool gpSelfTestRun()\n'
              '{\n'
              '    DIR* d = opendir("/data/omni");\n'
              '    if (!d) return false;\n'
              '    bool found = false;\n'
              '    const size_t k = strlen("-selftest.flag");\n'
              '    while (struct dirent* e = readdir(d)) {\n'
              '        const size_t n = strlen(e->d_name);\n'
              '        if (n > k && !strcmp(e->d_name + n - k, "-selftest.flag")) { found = true; break; }\n'
              '    }\n'
              '    closedir(d);\n'
              '    return found;\n'
              '}\n'
              'static bool gpWanted()\n'
              '{\n'
              '    if (access(kFlagPath, F_OK) == 0) return true;\n'
              '    return access("/data/omni/gpu-present-off.flag", F_OK) != 0 && !gpSelfTestRun();\n'
              '}\n')
    if '#include <dirent.h>' not in t:
        t = edit(t, '#include <cstring>\n', '#include <cstring>\n#include <dirent.h>   // ' + MARK + ': gpSelfTestRun\n', 'OmniGpuPresent.cpp')
    t = edit(t, old_init, helper + old_init, 'OmniGpuPresent.cpp')
    t = edit(t, 'if (g.state.load() == kOff && access(kFlagPath, F_OK) == 0) plog(true, "headless run',
             'if (g.state.load() == kOff && gpWanted()) plog(true, "headless run', 'OmniGpuPresent.cpp')
    t = edit(t, '} else if ((flags & kSDLInitVideo) && g.state.load() == kOff && access(kFlagPath, F_OK) == 0) {',
             '} else if ((flags & kSDLInitVideo) && g.state.load() == kOff && gpWanted()) {   // ' + MARK,
             'OmniGpuPresent.cpp')
    save(present, t, nl)
    done.append('OmniGpuPresent.cpp: applied')

t, nl = load(video)
if MARK in t:
    done.append('OmniGpuVideo.cpp: already')
else:
    host = 'static const char* flagPath() { const char* p = getenv("OMNI_GPU_FLAG"); return p ? p : "gpu-video.flag"; }\n'
    cons = 'static const char* flagPath() { return "/data/omni/gpu-video.flag"; }\n'
    t = edit(t, host, host + 'static bool gvWanted() { return access(flagPath(), F_OK) == 0; }   // host tests: the flag file decides\n',
             'OmniGpuVideo.cpp')
    t = edit(t, cons, cons + '// ' + MARK + ': on by default; /data/omni/gpu-video-off.flag turns it off (gpu-video.flag still read for its\n'
             '// words). Self-test runs (any /data/omni/*-selftest.flag) keep the old rule: on only with gpu-video.flag.\n'
             'static bool gvSelfTestRun()\n'
             '{\n'
             '    DIR* d = opendir("/data/omni");\n'
             '    if (!d) return false;\n'
             '    bool found = false;\n'
             '    const size_t k = strlen("-selftest.flag");\n'
             '    while (struct dirent* e = readdir(d)) {\n'
             '        const size_t n = strlen(e->d_name);\n'
             '        if (n > k && !strcmp(e->d_name + n - k, "-selftest.flag")) { found = true; break; }\n'
             '    }\n'
             '    closedir(d);\n'
             '    return found;\n'
             '}\n'
             'static bool gvWanted()\n'
             '{\n'
             '    if (access(flagPath(), F_OK) == 0) return true;\n'
             '    return access("/data/omni/gpu-video-off.flag", F_OK) != 0 && !gvSelfTestRun();\n'
             '}\n',
             'OmniGpuVideo.cpp')
    if '#include <dirent.h>' not in t:
        first = t.index('#include ')
        t = t[:first] + '#include <dirent.h>   // ' + MARK + ': gvSelfTestRun\n' + t[first:]
    t = edit(t, 'if (access(flagPath(), F_OK) != 0) { g.state.store(kFailed, std::memory_order_release); return kCpu; }   // flag absent: never again',
             'if (!gvWanted()) { g.state.store(kFailed, std::memory_order_release); return kCpu; }   // switched off: never again (' + MARK + ')',
             'OmniGpuVideo.cpp')
    t = edit(t, '    if (access(flagPath(), F_OK) != 0) return false;\n    if (!g.state.compare_exchange_strong(expected, kStarting',
             '    if (!gvWanted()) return false;   // ' + MARK + '\n    if (!g.state.compare_exchange_strong(expected, kStarting',
             'OmniGpuVideo.cpp')
    save(video, t, nl)
    done.append('OmniGpuVideo.cpp: applied')


def upgrade_r1(path, old_fn, new_fn, label):
    """R1 used 'any *-selftest.flag' (that also caught the visible YouTube/site gates): replace with the headless rule."""
    t, nl = load(path)
    if 'OMNI_GPU_DEFAULT_ON_V1_R2' in t:
        return label + ': R2 already'
    a = t.find('static bool %s()\n{\n' % old_fn)
    if a < 0:
        return label + ': no R1 function'
    b = t.find('\n}\n', a) + 3
    start = t.rfind('// Self-test runs', 0, a)
    start = start if start >= 0 and a - start < 400 else a
    t = t[:start] + HEADLESS_C % {'fn': new_fn} + t[b:]
    t = t.replace('!%s()' % old_fn, '!%s()' % new_fn)
    save(path, t, nl)
    return label + ': upgraded to R2'


done.append(upgrade_r1(present, 'gpSelfTestRun', 'gpHeadlessRun', 'OmniGpuPresent.cpp'))
done.append(upgrade_r1(video, 'gvSelfTestRun', 'gvHeadlessRun', 'OmniGpuVideo.cpp'))


def add_reason_log(path):
    t, nl = load(path)
    if 'OMNI_GPU_DEFAULT_ON_V1_R2 reason' in t:
        return 'OmniGpuPresent.cpp: reason log already'
    old = ('static bool gpWanted()\n{\n    if (access(kFlagPath, F_OK) == 0) return true;\n'
           '    return access("/data/omni/gpu-present-off.flag", F_OK) != 0 && !gpHeadlessRun();\n}\n')
    if t.count(old) != 1:
        return 'OmniGpuPresent.cpp: reason log anchor missing'
    new = ('static bool gpWanted()\n{\n    if (access(kFlagPath, F_OK) == 0) return true;\n'
           '    const char* why = !access("/data/omni/gpu-present-off.flag", F_OK) ? "gpu-present-off.flag" : gpHeadlessRun() ? "headless test run" : nullptr;\n'
           '    if (why) { static bool said = false; if (!said) { said = true; plog(true, "default ON skipped: %s (SDL\'s own present)", why); } }   // OMNI_GPU_DEFAULT_ON_V1_R2 reason\n'
           '    return !why;\n}\n')
    save(path, t.replace(old, new), nl)
    return 'OmniGpuPresent.cpp: reason log added'


done.append(add_reason_log(present))

print('; '.join(done))
print(('already ' if all(('already' in d) for d in done) else 'applied ') + MARK + ' R2')
