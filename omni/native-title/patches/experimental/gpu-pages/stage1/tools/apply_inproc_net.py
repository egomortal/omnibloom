#!/usr/bin/env python3
"""OMNI_INPROC_NET_V1 (2026-11-22): single-process plan Phase 2 - run the NetworkProcess role on a thread INSIDE the
title instead of spawning a separate engine process. outputs/omni-ptresearch/SINGLE-PROCESS-PLAN.md.

Seam: WebKit::ProcessLauncher::launchProcess() makes a SOCK_SEQPACKET socketpair and calls
PlayStation::launchProcess(path, argv, {param.sock = client fd}); Omni's version (this file) normally writes a ticket and
a pre-spawned engine process claims it. The title binary already links WebKit::NetworkProcessMain (verified by nm), so
for the Network role we can call it on a std::thread with the client fd and skip the spawn. IPC over the socketpair is
unchanged (both ends now live in the title). The NetworkProcess has no JavaScript and the PlayStation AuxiliaryProcessMain
installs no signal handlers (checked), so it is the safe proving ground before the WebProcess (Phase 3).

DEFAULT OFF: only when /data/omni/inproc-net.flag exists (read per launch). Off -> the original ticket/spawn path, so the
daily build is unchanged and this cannot affect the child builds (the flag never exists there).
usage: apply_inproc_net.py <process-launcher.cpp path>"""
import sys
from pathlib import Path

MARK = 'OMNI_INPROC_NET_V1'
p = Path(sys.argv[1])
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)


def rep(old, new):
    global s
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(old), old[:70]))
    s = s.replace(old, new, 1)


# 1. includes + the in-process entry declaration, after <signal.h>
rep('#include "launcher-common.h"\n',   # only this line: the build's variant has other includes after it
    '#include "launcher-common.h"\n'
    '// ' + MARK + ': run the NetworkProcess role in the title (Phase 2). See tools/apply_inproc_net.py.\n'
    '#include <thread>\n#include <cstring>\n#include <cstdlib>\n#include <cstdio>\n#include <unistd.h>\n'
    'namespace WebKit { int NetworkProcessMain(int, char**); int WebProcessMain(int, char**); }   // both defined in the title\n'
    'extern "C" void WKRunLoopCallOnMainThread(void (*)(void*), void*);   // WebKit C API (UIProcess/API/C/playstation/WKRunLoop.h)\n'
    '#ifdef ENABLE   // only where WebKit config.h is in (OmniMain.cpp); process-launcher.cpp has no ENABLE()\n'
    '#if ENABLE(MEDIA_SOURCE)\n'
    'namespace WebCore { void omniInstallMediaCapabilities(); }   // OMNI_MEDIACAPS_V1 (declared again further down OmniMain.cpp)\n'
    '#endif\n'
    '#endif\n'
    '// V2 (2026-11-22): the NetworkProcess must own a MAIN thread (WebCore::NetworkStateNotifier::singleton() RELEASE_ASSERTs\n'
    '// isMainThread(); V1 on a std::thread crashed the title at once). It starts on the title main thread from a queued task;\n'
    '// its RunLoop::run() nests inside the title WKRunLoopRunMain(), whose shell refresh timer keeps firing in the nested loop.\n'
    '// V3 (Phase 3 proof): the same for the WebProcess (/data/omni/inproc-web.flag, first launch only).\n'
    'struct OmniInprocNetArgs { int fd; char* coreId; bool web; };\n'
    '// 2026-11-23: in-process page engine mode (inproc-web.flag, read once): the WebProcess spares are not needed -\n'
    '// one spare for the NetworkProcess at start, none kept in reserve (each idle spare is a whole loaded engine).\n'
    'static bool omniInprocWebMode()\n'
    '{\n'
    '    static int on = -1;\n'
    '    if (on < 0) { FILE* f = fopen("/data/omni/inproc-web.flag", "r"); on = f ? 1 : 0; if (f) fclose(f); }\n'
    '    return on == 1;\n'
    '}\n'
    '// 2026-11-24: the NetworkProcess in the title too (inproc-net.flag): then no early spare at all.\n'
    'static bool omniInprocNetMode()\n'
    '{\n'
    '    static int on = -1;\n'
    '    if (on < 0) { FILE* f = fopen("/data/omni/inproc-net.flag", "r"); on = f ? 1 : 0; if (f) fclose(f); }\n'
    '    return on == 1;\n'
    '}\n'
    '// V4 hang probe: a main-thread heartbeat (queued every 2 s); if it stops for 15 s while an in-process role runs, the\n'
    '// main thread gets SIGTRAP so Omni\'s crash reporter prints the exact stack it is blocked in (the app is hung anyway).\n'
    '#include <atomic>\n#include <pthread.h>\n#include <signal.h>\n'
    'static std::atomic<unsigned> g_omniBeat { 0 };\n'
    'static void omniInprocBeat(void*) { g_omniBeat.fetch_add(1); }\n'
    'static void omniInprocStartHangProbe()\n'
    '{\n'
    '    pthread_t mainThread = pthread_self();\n'
    '    std::thread([mainThread] {\n'
    '        unsigned last = g_omniBeat.load();\n'
    '        int still = 0;\n'
    '        for (int i = 0; i < 300; ++i) {   // watch for 10 minutes\n'
    '            WKRunLoopCallOnMainThread(omniInprocBeat, nullptr);\n'
    '            sleep(2);\n'
    '            unsigned now = g_omniBeat.load();\n'
    '            still = now == last ? still + 2 : 0;\n'
    '            last = now;\n'
    '            if (still >= 15) {\n'
    '                omni_launcher_trace("launch: HANG PROBE: main thread silent %d s -> SIGTRAP for its stack\\n", still);\n'
    '                pthread_kill(mainThread, SIGTRAP);\n'
    '                return;\n'
    '            }\n'
    '        }\n'
    '    }).detach();\n'
    '}\n'
    'extern "C" volatile int omni_inproc_main_spin;   // OMNI_INPROC_SPIN_V1 (IPC/Connection.cpp): serve the UI while waiting\n'
    'static void omniInprocNetMain(void* p)\n'
    '{\n'
    '    OmniInprocNetArgs* a = static_cast<OmniInprocNetArgs*>(p);\n'
    '    omni_inproc_main_spin = 1;\n'
    '    // 2026-11-24 (release): the hang probe SIGTRAPs the app after 15 s of main-thread silence - a debugging aid only,\n'
    '    // now opt-in with /data/omni/inproc-hangprobe.flag (heavy JavaScript can legitimately hold the thread that long).\n'
    '    if (FILE* omniHp = fopen("/data/omni/inproc-hangprobe.flag", "r")) { fclose(omniHp); omniInprocStartHangProbe(); }\n'
    '    char program[] = "omni";\n'
    '    char fdstr[16];\n'
    '    snprintf(fdstr, sizeof fdstr, "%d", a->fd);\n'
    '    char* nargv[] = { program, a->coreId, fdstr, nullptr };\n'
    '    const char* role = a->web ? "WebProcess" : "NetworkProcess";\n'
    '#ifdef ENABLE\n'
    '#if ENABLE(MEDIA_SOURCE)\n'
    '    if (a->web)   // as runChild() does before WebProcessMain (2026-11-23: the in-process start skipped it)\n'
    '        WebCore::omniInstallMediaCapabilities();\n'
    '#endif\n'
    '#endif\n'
    '    omni_launcher_trace("launch: %s starting on the main thread fd=%d (V3)\\n", role, a->fd);\n'
    '    int rc = a->web ? WebKit::WebProcessMain(3, nargv) : WebKit::NetworkProcessMain(3, nargv);\n'
    '    omni_launcher_trace("launch: in-process %s main returned %d\\n", role, rc);\n'
    '    free(a->coreId);\n'
    '    delete a;\n'
    '}\n'
    '#define OMNI_INPROC_PID 0x7ffffffe   // synthetic pid for an in-process role; never kill(2) it\n'
    '#include <sys/socket.h>\n#include <sys/uio.h>\n'
    '// The title refuses dup() of a socket (EPERM, console 2026-11-22); passing it to ourselves with SCM_RIGHTS works.\n'
    'static int omniInprocScmDup(int fd)\n'
    '{\n'
    '    int sv[2];\n'
    '    if (socketpair(AF_UNIX, SOCK_STREAM, 0, sv))\n'
    '        return -1;\n'
    '    int out = -1;\n'
    '    char b = 0;\n'
    '    struct iovec io = { &b, 1 };\n'
    '    char cbuf[CMSG_SPACE(sizeof(int))];\n'
    '    std::memset(cbuf, 0, sizeof cbuf);\n'
    '    struct msghdr m;\n'
    '    std::memset(&m, 0, sizeof m);\n'
    '    m.msg_iov = &io; m.msg_iovlen = 1; m.msg_control = cbuf; m.msg_controllen = sizeof cbuf;\n'
    '    struct cmsghdr* c = CMSG_FIRSTHDR(&m);\n'
    '    c->cmsg_level = SOL_SOCKET; c->cmsg_type = SCM_RIGHTS; c->cmsg_len = CMSG_LEN(sizeof(int));\n'
    '    std::memcpy(CMSG_DATA(c), &fd, sizeof fd);\n'
    '    if (sendmsg(sv[0], &m, 0) == 1) {\n'
    '        char rb = 0;\n'
    '        struct iovec ri = { &rb, 1 };\n'
    '        char rcbuf[CMSG_SPACE(sizeof(int))];\n'
    '        std::memset(rcbuf, 0, sizeof rcbuf);\n'
    '        struct msghdr r;\n'
    '        std::memset(&r, 0, sizeof r);\n'
    '        r.msg_iov = &ri; r.msg_iovlen = 1; r.msg_control = rcbuf; r.msg_controllen = sizeof rcbuf;\n'
    '        if (recvmsg(sv[1], &r, 0) == 1) {\n'
    '            struct cmsghdr* rc = CMSG_FIRSTHDR(&r);\n'
    '            if (rc && rc->cmsg_level == SOL_SOCKET && rc->cmsg_type == SCM_RIGHTS)\n'
    '                std::memcpy(&out, CMSG_DATA(rc), sizeof out);\n'
    '        }\n'
    '    }\n'
    '    close(sv[0]);\n'
    '    close(sv[1]);\n'
    '    return out;\n'
    '}\n')

# 2. the hook at the very top of PlayStation::launchProcess
rep('int32_t launchProcess(const char* path, char* argv[], LaunchParam param)\n{\n'
    '    omni_launcher_trace("launch: path=%s socket=%d\\n", path ? path : "(null)", param.sock);\n',
    'int32_t launchProcess(const char* path, char* argv[], LaunchParam param)\n{\n'
    '    omni_launcher_trace("launch: path=%s socket=%d\\n", path ? path : "(null)", param.sock);\n'
    '    // ' + MARK + ': NetworkProcess role in the title, on a thread (default off).\n'
    '    // fopen, not access(): in this unit access() is ps5_access, which did not see /data/omni flags (2026-11-22 test).\n'
    '    const bool omniNet = path && std::strstr(path, "Network");\n'
    '    const bool omniWeb = path && std::strstr(path, "WebProcess");\n'
    '    static bool omniWebUsed = false;   // only the FIRST WebProcess goes in-process (one WebProcess singleton per process)\n'
    '    auto omniFlag = [](const char* n) { FILE* f = fopen(n, "r"); if (!f) return false; fclose(f); return true; };\n'
    '    const bool omniInproc = (omniNet && omniFlag("/data/omni/inproc-net.flag"))\n'
    '        || (omniWeb && !omniWebUsed && omniFlag("/data/omni/inproc-web.flag"));\n'
    '    if (omniNet || omniWeb)\n'
    '        omni_launcher_trace("launch: %s in-process flag=%d (' + MARK + ')\\n", omniWeb ? "WebProcess" : "NetworkProcess", omniInproc ? 1 : 0);\n'
    '    if (omniInproc) {\n'
    '        if (omniWeb)\n'
    '            omniWebUsed = true;\n'
    '        int connFd = dup(param.sock);   // our own copy: WebKit closes its socketpair.client after we return\n'
    '        if (connFd < 0)\n'
    '            connFd = omniInprocScmDup(param.sock);   // the title refuses dup() of sockets\n'
    '        char* coreId = strdup(argv && argv[0] ? argv[0] : "0");\n'
    '        if (connFd < 0 || !coreId) {\n'
    '            omni_launcher_trace("launch: in-proc net setup failed (fd=%d); falling back to spawn\\n", connFd);\n'
    '            if (connFd >= 0) close(connFd);\n'
    '            free(coreId);\n'
    '        } else {\n'
    '            omni_launcher_trace("launch: NetworkProcess IN-PROCESS (' + MARK + ') fd=%d\\n", connFd);\n'
    '            WKRunLoopCallOnMainThread(omniInprocNetMain, new OmniInprocNetArgs { connFd, coreId, omniWeb });   // main thread\n'
    '            return omniWeb ? OMNI_INPROC_PID : OMNI_INPROC_PID - 1;   // 2026-11-24: one synthetic pid PER role (gin32: both roles shared one)\n'
    '        }\n'
    '    }\n')

# 2b. no reserve spare in in-process page engine mode (only in the spares variant of the launcher, v2.inc)
_spare = '            topUp(target, 1); // keep one spare ready for the next launch\n'
if s.count(_spare) == 1:
    s = s.replace(_spare, '            topUp(target, omniInprocWebMode() ? 0 : 1); // keep one spare ready for the next launch (none in in-process page mode, ' + MARK + ')\n', 1)

# 3. never SIGKILL the title for the synthetic in-process pid
rep('int terminateProcess(int32_t pid)\n{\n    return pid > 0 ? kill(pid, SIGKILL) : -1;\n}\n',
    'int terminateProcess(int32_t pid)\n{\n'
    '    if (pid == OMNI_INPROC_PID || pid == OMNI_INPROC_PID - 1)\n'
    '        return 0;   // ' + MARK + ': the NetworkProcess runs in the title; do not kill(2) ourselves\n'
    '    return pid > 0 ? kill(pid, SIGKILL) : -1;\n}\n')

p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
