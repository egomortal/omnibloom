// omni-gpu-pages stage 1 (OMNI_GPU_PAGES_STAGE1_V1), title side: the gpu-broker owner for Omni's WebProcesses.
// SPDX-License-Identifier: GPL-3.0-or-later  (links LGPL-2.1-or-later gpu-broker owner code)
//
// A new title source; no existing title file changes. OFF unless /data/omni/gpu-pages-stage1.flag exists and
// /data/omni/gpu-pages-stage1-off.flag (the kill switch) does not, checked once at start. Off, this file starts
// nothing at all.
//
// On, one detached thread answers WebProcesses. A child that wants GPU compositing writes
// /data/omni/gpu-pages/s1/req-<pid> (ogp-s1-child.c). On the first request the broker owner starts on the RADV this
// title already owns (CP-2, 2026-11-10: a second platform init in a title that already runs RADV is fine); each
// request then gets its own endpoint from ps5_gpu_broker_open(), answered as ep-<pid> = "pid=<title> fd=<fd>
// cookie=<n>" (written to .tmp and renamed). The child pulls the fd across with syscall 0x25b, exactly as CP-2's
// client did. Every refusal is an "error=..." answer, and the child then leaves compositing off: a page never
// waits on this thread for more than its own 1.5 s bound.
// Known limit, fine for the A/B and not for shipping by default: slots are not reclaimed when a WebProcess ends
// (30 per title session); past that, new WebProcesses are refused and simply draw the way they do today.
#include "server.h"
#include <cerrno>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <pthread.h>
#include <sys/stat.h>
#include <unistd.h>

extern "C" void omni_native_log(const char*, ...);   // OmniNativeTitle.cpp: /data/omni/native/boot.log
extern "C" {
int ogp_s1_kill(pid_t, int) __asm__("kill") __attribute__((weak));   // resolves at run time in a title (CP-2: ESRCH seen)
}

namespace {
constexpr const char* kFlag = "/data/omni/gpu-pages-stage1.flag";
constexpr const char* kOff = "/data/omni/gpu-pages-stage1-off.flag";
constexpr const char* kDir = "/data/omni/gpu-pages/s1";
constexpr int kSlots = 30;

bool childAbsent(int pid)
{
    if (pid <= 0) return true;
    if (!ogp_s1_kill) return false;   // never claim absence without the kernel's word
    errno = 0;
    if (ogp_s1_kill(pid, 0) == 0 || errno == EPERM) return false;
    return errno == ESRCH;
}

void answer(int pid, const char* text)
{
    char path[96], tmp[112];
    snprintf(path, sizeof path, "%s/ep-%d", kDir, pid);
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    int fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (fd < 0) { omni_native_log("gpu-pages: cannot answer pid %d (errno %d)", pid, errno); return; }
    (void)!write(fd, text, strlen(text)); fsync(fd); close(fd);
    rename(tmp, path);
}

void* serve(void*)
{
    bool started = false, failed = false;
    int slots = 0;
    omni_native_log("gpu-pages: stage 1 is ON (%s); serving WebProcess requests in %s", kFlag, kDir);
    // OMNI_GPUPAGES_EAGER_V1: the 2026-11-12 run showed a lazy start answered after the child's 1.5 s bound, so the
    // owner now starts 3 s after title start (after the title's own RADV/video init) or on the first request,
    // whichever comes first; each answer is then only ps5_gpu_broker_open().
    for (int waited = 0; waited < 150; ++waited) {
        bool pending = false;
        if (DIR* d = opendir(kDir)) {
            while (struct dirent* e = readdir(d))
                if (!strncmp(e->d_name, "req-", 4) && !strstr(e->d_name, ".tmp")) { pending = true; break; }
            closedir(d);
        }
        if (pending) break;
        usleep(20000);
    }
    // OMNI_GPUPAGES_HOSTMEM_V1: the 2026-11-12 eager run's WebProcess exhausted the default 128 MiB host-visible budget
    // (zink "couldn't allocate memory" heap 4/5, no broker refusal logged) and crashed; one 4K readback is 33 MB.
    // 384 MiB by default (the memory is the title's shm; ~745 MB flexible was free at bind), tunable with
    // /data/omni/gpu-pages-host-mib.txt (64..1024, MiB).
    unsigned long long hostMiB = 384;
    if (FILE* f = fopen("/data/omni/gpu-pages-host-mib.txt", "r")) {
        unsigned long long v = 0;
        if (fscanf(f, "%llu", &v) == 1 && v >= 64 && v <= 1024) hostMiB = v;
        fclose(f);
    }
    bool hostSet = ps5_gpu_broker_set_host_limit(hostMiB << 20);
    started = ps5_gpu_broker_start(kDir, false, true, childAbsent);
    failed = !started;
    omni_native_log("gpu-pages: broker owner %s on this title's RADV device (eager start; host-visible budget %llu MiB %s)",
        started ? "started" : "FAILED to start: every WebProcess keeps drawing as today", hostMiB, hostSet ? "set" : "NOT set");
    for (;;) {
        if (DIR* d = opendir(kDir)) {
            while (struct dirent* e = readdir(d)) {
                int pid = 0;
                if (strncmp(e->d_name, "req-", 4) || strstr(e->d_name, ".tmp") || (pid = atoi(e->d_name + 4)) <= 0) continue;
                char text[128];
                if (!started && !failed) {
                    started = ps5_gpu_broker_start(kDir, false, true, childAbsent);
                    failed = !started;
                    omni_native_log("gpu-pages: broker owner %s on this title's RADV device (first request, pid %d)",
                        started ? "started" : "FAILED to start: every WebProcess keeps drawing as today", pid);
                }
                if (failed)
                    snprintf(text, sizeof text, "error=broker-start-failed\n");
                else if (slots >= kSlots)
                    snprintf(text, sizeof text, "error=no-slot (%d used this session)\n", slots);
                else {
                    int cookie = 0;
                    int fd = ps5_gpu_broker_open(&cookie);
                    if (fd < 0)
                        snprintf(text, sizeof text, "error=open errno=%d\n", errno);
                    else {
                        snprintf(text, sizeof text, "pid=%d fd=%d cookie=%d\n", static_cast<int>(getpid()), fd, cookie);
                        ++slots;
                    }
                }
                answer(pid, text);
                char req[96]; snprintf(req, sizeof req, "%s/%s", kDir, e->d_name);
                unlink(req);
                omni_native_log("gpu-pages: pid %d -> %s", pid, text);
            }
            closedir(d);
        }
        usleep(20000);
    }
    return nullptr;
}

__attribute__((constructor)) void omniGpuPagesServiceStart()
{
    if (access(kFlag, F_OK) || !access(kOff, F_OK)) return;   // the default: nothing starts
    mkdir("/data/omni", 0777); mkdir("/data/omni/gpu-pages", 0777); mkdir(kDir, 0777);
    if (DIR* d = opendir(kDir)) {   // requests and answers from an earlier session are meaningless now
        while (struct dirent* e = readdir(d)) {
            if (strncmp(e->d_name, "req-", 4) && strncmp(e->d_name, "ep-", 3)) continue;
            char path[300]; snprintf(path, sizeof path, "%s/%s", kDir, e->d_name); unlink(path);
        }
        closedir(d);
    }
    pthread_attr_t attr; pthread_t thread;
    pthread_attr_init(&attr); pthread_attr_setstacksize(&attr, 256 * 1024); pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
    pthread_create(&thread, &attr, serve, nullptr);
    pthread_attr_destroy(&attr);
}
} // namespace
