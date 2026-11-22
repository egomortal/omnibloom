#!/usr/bin/env python3
"""OMNI_PT_BACKSTOP_V1 (2026-11-19, owner: "go all the way" - part 2 of the page-table governor, title side).

The console hangs when the kernel's CPU page-table pool (8,192 pages) runs out: measured hangs at ~6,700-6,950 used.
libkernel's sceKernelGetPageTableStats(int* cpuTotal, int* cpuAvailable, int* gpuTotal, int* gpuAvailable) returns
the same numbers ShellCore logs (console probe omni-ptprobe/ptstats.c 2026-11-19: 8192 / 3072 free = 5120 used, the
kernel log said 5101-5183; +256 MiB touched -> exactly 128 fewer free; reported in steps of 128).

The video service's pace queue maps one direct-memory picture buffer per queued picture (up to ~1 GiB = ~512 page
tables). This makes that mapping hook refuse while the system is at or above 6,400 used (/data/omni/pt-line.txt can set
5,000..7,600; /data/omni/pt-backstop-off.flag turns it off). A refusal is the existing, handled path ("direct memory
refused a queued picture; queue capped at N frames"): the queue simply stops growing. Logged at most every 10 s:
"OMNI PT BACKSTOP: <used>/<total> page tables >= line <n>: picture buffer refused". The call is looked up at runtime
(dlsym), so the title's import list is unchanged.
Patches engine/media/OmniHwService.cpp; must run BEFORE prep_launch.py (like apply_memmap.py).
usage: apply_pt_backstop.py <$NE (holding engine/media)>   prints "applied" / "already"."""
import sys
from pathlib import Path

MARK = 'OMNI_PT_BACKSTOP_V1'
p = Path(sys.argv[1]) / 'engine/media/OmniHwService.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')

OLD = 'void* abrMapHook(size_t size, int64_t& start, int* rc, const char** stage) { return backendDirectAlloc(size, start, rc, stage); }\n'
NEW = ('// ' + MARK + ': the kernel page-table pool (see tools/apply_pt_backstop.py); -1 when unknown\n'
       'int omniPtUsed(int* totalOut)\n'
       '{\n'
       '    using Fn = int (*)(int*, int*, int*, int*);\n'
       '    static const Fn fn = reinterpret_cast<Fn>(dlsym(RTLD_DEFAULT, "sceKernelGetPageTableStats"));\n'
       '    int total = 0, avail = 0, gpuTotal = 0, gpuAvail = 0;\n'
       '    if (!fn || fn(&total, &avail, &gpuTotal, &gpuAvail) != 0 || total <= 0 || avail < 0 || avail > total) return -1;\n'
       '    if (totalOut) *totalOut = total;\n'
       '    return total - avail;\n'
       '}\n'
       'static int omniPtLine()\n'
       '{\n'
       '    static const int line = [] {\n'
       '        if (!access("/data/omni/pt-backstop-off.flag", F_OK)) return 0;\n'
       '        int v = 6400;\n'
       '        if (FILE* f = fopen("/data/omni/pt-line.txt", "r")) { int x = 0; if (fscanf(f, "%d", &x) == 1 && x >= 5000 && x <= 7600) v = x; fclose(f); }\n'
       '        return v;\n'
       '    }();\n'
       '    return line;\n'
       '}\n'
       'void* abrMapHook(size_t size, int64_t& start, int* rc, const char** stage)\n'
       '{\n'
       '    if (const int line = omniPtLine()) {   // ' + MARK + '\n'
       '        int total = 0;\n'
       '        const int used = omniPtUsed(&total);\n'
       '        if (used >= line) {\n'
       '            static double lastLog = 0;\n'
       '            if (nowMs() - lastLog > 10000) {\n'
       '                lastLog = nowMs();\n'
       '                fprintf(stderr, "OMNI PT BACKSTOP: %d/%d page tables >= line %d: picture buffer refused (%zu bytes)\\n", used, total, line, size);\n'
       '                fflush(stderr);\n'
       '            }\n'
       '            if (rc) *rc = -1;\n'
       '            if (stage) *stage = "page-table line";\n'
       '            return nullptr;\n'
       '        }\n'
       '    }\n'
       '    return backendDirectAlloc(size, start, rc, stage);\n'
       '}\n')
if MARK not in s:
    if s.count(OLD) != 1:
        sys.exit('%s: anchor found %d times' % (p.name, s.count(OLD)))
    s = s.replace(OLD, NEW, 1)

# V2 (2026-11-19 23:55Z): on g9h the backstop never logged - the 4K queue fills to its cap at stream start while the
# count is still under the line, and the climb comes later. So (a) the first reading is logged once (proves the
# runtime lookup works), and (b) while the count is at or above the line, the service thread's periodic refresh
# drops the pool's mapped-but-unused picture buffers (up to 320 MiB kept for reuse = ~160 page tables; nothing on
# screen uses them) at most every 2 s.
MARK2 = 'OMNI_PT_BACKSTOP_V2'
OLD2 = 'void abrRefreshAvailable() { abrAvailableBytes.store(backendDirectAvailable(), std::memory_order_relaxed); }\n'
NEW2 = ('void abrRefreshAvailable()\n'
        '{\n'
        '    abrAvailableBytes.store(backendDirectAvailable(), std::memory_order_relaxed);\n'
        '    if (const int line = omniPtLine()) {   // ' + MARK2 + '\n'
        '        static double lastCheck = 0, lastLog = 0; static bool firstLogged = false;\n'
        '        const double now = nowMs();\n'
        '        if (now - lastCheck < 2000) return;\n'
        '        lastCheck = now;\n'
        '        int total = 0;\n'
        '        const int used = omniPtUsed(&total);\n'
        '        if (!firstLogged) { firstLogged = true; fprintf(stderr, "OMNI PT BACKSTOP: first reading %d/%d page tables, line %d\\n", used, total, line); fflush(stderr); }\n'
        '        if (used >= line && abrPool().poolBytes()) {\n'
        '            const size_t pooled = abrPool().poolBytes();\n'
        '            abrPool().drain();\n'
        '            if (now - lastLog > 10000) { lastLog = now; fprintf(stderr, "OMNI PT BACKSTOP: %d/%d page tables >= line %d: dropped %.0f MiB of pooled picture buffers\\n", used, total, line, double(pooled) / 1048576); fflush(stderr); }\n'
        '        }\n'
        '    }\n'
        '}\n')
if MARK2 not in s:
    if s.count(OLD2) != 1:
        sys.exit('%s: V2 anchor found %d times' % (p.name, s.count(OLD2)))
    s = s.replace(OLD2, NEW2, 1)

# V3 (2026-11-20 01:10Z): on g9i the first reading was "-1/0": dlsym(RTLD_DEFAULT, "sceKernelGetPageTableStats") finds
# nothing in the title (a payload links it from libkernel). Look it up in the system modules the title can open, the
# way OmniMain.cpp finds sceSystemServiceLoadExec (dlopen("<module>.sprx") + dlsym), and say which one answered.
MARK3 = 'OMNI_PT_BACKSTOP_V3'
OLD3 = '    static const Fn fn = reinterpret_cast<Fn>(dlsym(RTLD_DEFAULT, "sceKernelGetPageTableStats"));\n'
NEW3 = ('    static const char* from = "none";   // ' + MARK3 + '\n'
        '    static const Fn fn = [] {\n'
        '        if (void* f = dlsym(RTLD_DEFAULT, "sceKernelGetPageTableStats")) { from = "default"; return reinterpret_cast<Fn>(f); }\n'
        '        for (const char* m : { "libkernel_sys.sprx", "libkernel.sprx", "libkernel_web.sprx" })\n'
        '            if (void* h = dlopen(m, RTLD_LAZY))\n'
        '                if (void* f = dlsym(h, "sceKernelGetPageTableStats")) { from = m; return reinterpret_cast<Fn>(f); }\n'
        '        return Fn(nullptr);\n'
        '    }();\n'
        '    static bool said = false;\n'
        '    if (!said) { said = true; fprintf(stderr, "OMNI PT BACKSTOP: sceKernelGetPageTableStats from %s\\n", from); fflush(stderr); }\n')
if MARK3 not in s:
    if s.count(OLD3) != 1:
        sys.exit('%s: V3 anchor found %d times' % (p.name, s.count(OLD3)))
    s = s.replace(OLD3, NEW3, 1)

# V4 (2026-11-20): dropping the spare pool may not be enough (4K + layers peaked ~6,790 with the queue already full).
# While the count stays >= line, the pace queue's ceilings step down to (live bytes - the overshoot in 2 MiB pages),
# never below 512 MiB, pool reserve 0; freed pictures are then not replaced and the queue shortens. Back to the
# configured values once the count is 256 below the line. Logged on each change.
MARK4 = 'OMNI_PT_BACKSTOP_V4'
OLD4 = ('            abrPool().drain();\n'
        '            if (now - lastLog > 10000) { lastLog = now; fprintf(stderr, "OMNI PT BACKSTOP: %d/%d page tables >= line %d: dropped %.0f MiB of pooled picture buffers\\n", used, total, line, double(pooled) / 1048576); fflush(stderr); }\n'
        '        }\n')
NEW4 = (OLD4 +
        '        {   // ' + MARK4 + ': step the queue ceiling down while over the line, restore below it\n'
        '            static bool lowered = false; static Abr::Config saved;\n'
        '            if (used >= line) {\n'
        '                Abr::Config c = abrPool().config();\n'
        '                if (!lowered) { saved = c; lowered = true; }\n'
        '                const size_t live = abrPool().liveBytes(), over = size_t(used - line + 128) << 21;\n'
        '                const size_t want = std::max<size_t>(size_t(512) << 20, live > over ? live - over : 0);\n'
        '                if (want < c.steadyCeiling) {\n'
        '                    c.steadyCeiling = want; c.switchCeiling = std::max(want, std::min(c.switchCeiling, want)); c.poolReserve = 0;\n'
        '                    abrPool().setConfig(c);\n'
        '                    fprintf(stderr, "OMNI PT BACKSTOP: %d/%d >= line %d: queue ceiling %.0f MiB (live %.0f MiB)\\n", used, total, line, double(want) / 1048576, double(live) / 1048576); fflush(stderr);\n'
        '                }\n'
        '            } else if (lowered && used < line - 256) {\n'
        '                abrPool().setConfig(saved); lowered = false;\n'
        '                fprintf(stderr, "OMNI PT BACKSTOP: %d/%d below line %d: queue ceiling restored\\n", used, total, line); fflush(stderr);\n'
        '            }\n'
        '        }\n')
if MARK4 not in s:
    if s.count(OLD4) != 1:
        sys.exit('%s: V4 anchor found %d times' % (p.name, s.count(OLD4)))
    s = s.replace(OLD4, NEW4, 1)

# V5 (2026-11-20 02:40Z): g9j logged "from none" - the call is not reachable from the title at all. Omni's engine
# starter (outputs/omni-starter, OMNI_STARTER_V4, a payload) answers "pt" on 127.0.0.1:9031 with "pt <used> <total>".
# Without the direct call, the 2 s refresh asks the starter (blocking socket, 300 ms time-outs: the title cannot use
# non-blocking sockets) and caches the answer; omniPtUsed() returns that cached reading (so the per-picture check in
# abrMapHook never touches a socket). An older starter answers "omni-starter: refused" -> -1 (blind, as before).
MARK5 = 'OMNI_PT_BACKSTOP_V5'
OLD5a = '    if (!fn || fn(&total, &avail, &gpuTotal, &gpuAvail) != 0 || total <= 0 || avail < 0 || avail > total) return -1;\n'
NEW5a = ('    if (!fn) {   // ' + MARK5 + ': the starter\'s reading, refreshed every 2 s by abrRefreshAvailable\n'
         '        const int u = omniPtCacheUsed.load(std::memory_order_relaxed);\n'
         '        if (u >= 0 && totalOut) *totalOut = omniPtCacheTotal.load(std::memory_order_relaxed);\n'
         '        return u;\n'
         '    }\n'
         '    if (fn(&total, &avail, &gpuTotal, &gpuAvail) != 0 || total <= 0 || avail < 0 || avail > total) return -1;\n')
OLD5b = 'int omniPtUsed(int* totalOut)\n{\n'
NEW5b = ('// ' + MARK5 + ': the engine starter (OMNI_STARTER_V4) reads the pool for us; cached here\n'
         'static std::atomic<int> omniPtCacheUsed { -1 }, omniPtCacheTotal { 0 };\n'
         'static void omniPtAskStarter()\n'
         '{\n'
         '    int fd = socket(AF_INET, SOCK_STREAM, 0);\n'
         '    if (fd < 0) return;\n'
         '    timeval tv {}; tv.tv_usec = 300000;\n'
         '    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv); setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);\n'
         '    sockaddr_in a {}; a.sin_family = AF_INET; a.sin_port = htons(9031); a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);\n'
         '    int used = -1, total = 0;\n'
         '    if (!connect(fd, reinterpret_cast<sockaddr*>(&a), sizeof a) && write(fd, "pt\\n", 3) == 3) {\n'
         '        char buf[64] = { 0 }; size_t got = 0; ssize_t r;\n'
         '        while (got < sizeof buf - 1 && (r = read(fd, buf + got, sizeof buf - 1 - got)) > 0) { got += size_t(r); if (memchr(buf, 10, got)) break; }\n'
         '        if (sscanf(buf, "pt %d %d", &used, &total) != 2 || total <= 0) used = -1;\n'
         '    }\n'
         '    close(fd);\n'
         '    omniPtCacheTotal.store(total, std::memory_order_relaxed); omniPtCacheUsed.store(used, std::memory_order_relaxed);\n'
         '}\n'
         'static bool omniPtDirect();\n'
         'int omniPtUsed(int* totalOut)\n{\n')
OLD5c = '        int total = 0;\n        const int used = omniPtUsed(&total);\n        if (!firstLogged)'
NEW5c = '        if (!omniPtDirect()) omniPtAskStarter();   // ' + MARK5 + '\n        int total = 0;\n        const int used = omniPtUsed(&total);\n        if (!firstLogged)'
OLD5d = 'static int omniPtLine()\n{\n'
NEW5d = ('static bool omniPtDirect() { int t = 0; omniPtUsed(&t); return omniPtFnFound; }   // ' + MARK5 + '\n'
         'static int omniPtLine()\n{\n')
OLD5e = '    static bool said = false;\n'
NEW5e = '    omniPtFnFound = fn != nullptr;   // ' + MARK5 + '\n    static bool said = false;\n'
if MARK5 not in s:
    for o in (OLD5a, OLD5b, OLD5c, OLD5d, OLD5e):
        if s.count(o) != 1:
            sys.exit('%s: V5 anchor found %d times: %r' % (p.name, s.count(o), o.strip()[:70]))
    s = s.replace(OLD5a, NEW5a, 1).replace(OLD5e, NEW5e, 1).replace(OLD5b, 'static bool omniPtFnFound = false;   // ' + MARK5 + '\n' + NEW5b, 1)
    s = s.replace(OLD5c, NEW5c, 1).replace(OLD5d, NEW5d, 1)
    for inc in ('#include <sys/socket.h>', '#include <netinet/in.h>', '#include <arpa/inet.h>', '#include <sys/time.h>'):
        if inc not in s:
            first = s.index('#include ')
            s = s[:first] + inc + '  // ' + MARK5 + '\n' + s[first:]
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
