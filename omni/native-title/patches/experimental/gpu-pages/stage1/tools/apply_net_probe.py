#!/usr/bin/env python3
"""OMNI_NET_PROBE_V1 (2026-11-23, TEST builds): which non-blocking socket methods the TITLE may use.

Single-process plan, step "network engine in the app": WebKit's NetworkProcess ran on the title main thread (Phase 2,
2026-11-22) but curl failed - it needs non-blocking sockets, and in the title fcntl(O_NONBLOCK) fails with errno 13
(memory: ps5-title-no-nonblocking-sockets). Before choosing between a non-blocking shim and a blocking-thread design,
this measures, once, on a detached thread at startup, only with /data/omni/netprobe.flag:
  fcntl F_SETFL O_NONBLOCK | setsockopt SOL_SOCKET SO_NBIO (Sony 0x1200) | ioctl FIONBIO
  then a connect to 1.1.1.1:80 (timed: did it return at once with EINPROGRESS?), poll POLLOUT 3 s + SO_ERROR,
  recv(MSG_DONTWAIT) on the connected socket (EAGAIN expected), send(MSG_DONTWAIT), and getaddrinfo("example.com").
One "OMNI NETPROBE ..." line per result via omni_launcher_trace. No flag: nothing runs.
usage: apply_net_probe.py <engine/entry/OmniMain.cpp>"""
import sys
from pathlib import Path

MARK = 'OMNI_NET_PROBE_V1'
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


PROBE = r'''// OMNI_NET_PROBE_V1 (test): which non-blocking socket methods the title may use (see tools/apply_net_probe.py)
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <poll.h>
#include <time.h>
#include <thread>
static double omniNetProbeMs()
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1000.0 + t.tv_nsec / 1e6;
}
static void omniNetProbe()
{
    std::thread([] {
        int one = 1;
        int s = socket(AF_INET, SOCK_STREAM, 0);
        omni_launcher_trace("OMNI NETPROBE socket=%d errno=%d\n", s, s < 0 ? errno : 0);
        if (s < 0)
            return;
        errno = 0;
        int fl = fcntl(s, F_GETFL);
        int r1 = fcntl(s, F_SETFL, (fl < 0 ? 0 : fl) | O_NONBLOCK);
        int e1 = errno;
        int after1 = fcntl(s, F_GETFL);
        omni_launcher_trace("OMNI NETPROBE fcntl O_NONBLOCK rc=%d errno=%d flags now=%#x\n", r1, r1 ? e1 : 0, after1);
        errno = 0;
        int r2 = setsockopt(s, SOL_SOCKET, 0x1200 /* SO_NBIO */, &one, sizeof one);
        omni_launcher_trace("OMNI NETPROBE setsockopt SO_NBIO rc=%d errno=%d\n", r2, r2 ? errno : 0);
        errno = 0;
        int r3 = ioctl(s, FIONBIO, &one);
        omni_launcher_trace("OMNI NETPROBE ioctl FIONBIO rc=%d errno=%d\n", r3, r3 ? errno : 0);
        struct sockaddr_in a;
        memset(&a, 0, sizeof a);
        a.sin_family = AF_INET;
        a.sin_port = htons(80);
        inet_pton(AF_INET, "1.1.1.1", &a.sin_addr);
        double t0 = omniNetProbeMs();
        errno = 0;
        int rc = connect(s, reinterpret_cast<struct sockaddr*>(&a), sizeof a);
        int ec = errno;
        double t1 = omniNetProbeMs();
        omni_launcher_trace("OMNI NETPROBE connect rc=%d errno=%d took %.1f ms (non-blocking if EINPROGRESS and fast)\n", rc, rc ? ec : 0, t1 - t0);
        struct pollfd pf = { s, POLLOUT, 0 };
        int pr = poll(&pf, 1, 3000);
        int soerr = -1;
        socklen_t sl = sizeof soerr;
        getsockopt(s, SOL_SOCKET, SO_ERROR, &soerr, &sl);
        omni_launcher_trace("OMNI NETPROBE poll POLLOUT rc=%d revents=%#x so_error=%d after %.1f ms\n", pr, (unsigned)pf.revents, soerr, omniNetProbeMs() - t1);
        char b = 0;
        errno = 0;
        double t2 = omniNetProbeMs();
        ssize_t rr = recv(s, &b, 1, MSG_DONTWAIT);
        omni_launcher_trace("OMNI NETPROBE recv MSG_DONTWAIT rc=%zd errno=%d took %.1f ms (EAGAIN=%d)\n", rr, rr < 0 ? errno : 0, omniNetProbeMs() - t2, EAGAIN);
        errno = 0;
        ssize_t sr = send(s, "HEAD / HTTP/1.0\r\n\r\n", 19, MSG_DONTWAIT);
        omni_launcher_trace("OMNI NETPROBE send MSG_DONTWAIT rc=%zd errno=%d\n", sr, sr < 0 ? errno : 0);
        close(s);
        struct addrinfo* ai = nullptr;
        double t3 = omniNetProbeMs();
        int g = getaddrinfo("example.com", "80", nullptr, &ai);
        omni_launcher_trace("OMNI NETPROBE getaddrinfo rc=%d first=%d took %.1f ms (OMNI_NET_PROBE_V1)\n", g, ai ? ai->ai_family : -1, omniNetProbeMs() - t3);
        if (ai)
            freeaddrinfo(ai);
        // R2: the title's getaddrinfo is the SDK stub (EAI_FAIL); the child's uses Sony's resolver (libSceNet). Is that
        // module already loaded here? dlsym (OmniNativeTitle.cpp) searches the loaded modules' exports.
        using PoolCreateFn = int (*)(const char*, int, int);
        using ResCreateFn = int (*)(const char*, int, int);
        using NtoaFn = int (*)(int, const char*, struct in_addr*, int, int, int);
        using DestroyFn = int (*)(int);
        // R3 (gin27: libSceNet is NOT loaded in the title, all five came back null): load it by path through libkernel's
        // sceKernelLoadStartModule (found with the same dlsym; libkernel is always loaded), then look again.
        if (!dlsym(nullptr, "sceNetResolverCreate")) {
            using LoadStartFn = int (*)(const char*, size_t, const void*, uint32_t, void*, int*);
            void* lsm = dlsym(nullptr, "sceKernelLoadStartModule");
            omni_launcher_trace("OMNI NETPROBE sceKernelLoadStartModule=%p\n", lsm);
            if (lsm) {
                static const char* const paths[] = { "/system/common/lib/libSceNet.sprx", "/system/priv/lib/libSceNet.sprx", "libSceNet.sprx" };
                for (const char* path : paths) {
                    int res = 0;
                    int h = reinterpret_cast<LoadStartFn>(lsm)(path, 0, nullptr, 0, nullptr, &res);
                    omni_launcher_trace("OMNI NETPROBE load %s -> handle %#x res %d\n", path, (unsigned)h, res);
                    if (h >= 0)
                        break;
                }
            }
        }
        void* pc = dlsym(nullptr, "sceNetPoolCreate");
        void* pd = dlsym(nullptr, "sceNetPoolDestroy");
        void* rcr = dlsym(nullptr, "sceNetResolverCreate");
        void* rn = dlsym(nullptr, "sceNetResolverStartNtoa");
        void* rd = dlsym(nullptr, "sceNetResolverDestroy");
        omni_launcher_trace("OMNI NETPROBE resolver symbols pool=%p pooldestroy=%p create=%p ntoa=%p destroy=%p\n", pc, pd, rcr, rn, rd);
        if (pc && pd && rcr && rn && rd) {
            double t4 = omniNetProbeMs();
            int pool = reinterpret_cast<PoolCreateFn>(pc)("omni-dns", 0x4000, 0);
            int rid = pool >= 0 ? reinterpret_cast<ResCreateFn>(rcr)("omni-dns", pool, 0) : -1;
            struct in_addr ad;
            memset(&ad, 0, sizeof ad);
            int nr = rid >= 0 ? reinterpret_cast<NtoaFn>(rn)(rid, "example.com", &ad, 0, 0, 0) : -1;
            char txt[32] = "?";
            inet_ntop(AF_INET, &ad, txt, sizeof txt);
            omni_launcher_trace("OMNI NETPROBE sce resolver pool=%#x rid=%#x ntoa=%#x addr=%s took %.1f ms\n", (unsigned)pool, (unsigned)rid, (unsigned)nr, txt, omniNetProbeMs() - t4);
            if (rid >= 0)
                reinterpret_cast<DestroyFn>(rd)(rid);
            if (pool >= 0)
                reinterpret_cast<DestroyFn>(pd)(pool);
        }
    }).detach();
}

int main(int, char**)
'''
rep('\nint main(int, char**)\n', '\n' + PROBE)

rep('    // OMNI_JSC_JIT_V1: no process uses the JIT unless runChild() turns it on for a web process.\n',
    '    if (FILE* omniSp = fopen("/data/omni/netprobe.flag", "r")) { fclose(omniSp); omniNetProbe(); }   // ' + MARK + '\n'
    '    // TEST ONLY (2026-11-24): /data/omni/crashtest.flag -> a deliberate memory fault 75 s after start, to exercise\n'
    '    // OMNI_INPROC_CRASH_SAFETY_V1 (report, decoder release, relaunch, restored tabs). The flag is removed first, so\n'
    '    // the relaunched Omni does not crash again.\n'
    '    if (FILE* omniCt = fopen("/data/omni/crashtest.flag", "r")) {\n'
    '        fclose(omniCt);\n'
    '        unlink("/data/omni/crashtest.flag");\n'
    '        std::thread([] { sleep(75); if (FILE* m = fopen("/data/omni/run/crashtest-relaunch", "w")) fclose(m);\n'
    '            omni_launcher_trace("OMNI CRASHTEST: deliberate fault now\\n"); *reinterpret_cast<volatile int*>(16) = 1; }).detach();\n'
    '    }\n'
    '    // OMNI_JSC_JIT_V1: no process uses the JIT unless runChild() turns it on for a web process.\n')

p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
