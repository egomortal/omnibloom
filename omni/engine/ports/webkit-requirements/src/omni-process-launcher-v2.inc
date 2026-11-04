// Omni Engine: process launcher, parent side (tickets + remote dup) -- OMNI_PERF_D_T1 version.
//
// This is process-launcher.cpp (same directory, unchanged) plus early spares. It is #included by
// entry/OmniMain.cpp: omni_build.py can only recompile .cpp files that map to exactly one link
// object, and process-launcher.cpp is a member of libWebKitRequirements.a. Because OmniMain.o is
// an object file and defines every global symbol of that member (PlayStation::launchProcess,
// PlayStation::terminateProcess, omni_launcher_set_spawner), the linker never extracts the member
// (a second definition would fail the link loudly, never silently).
//
// Probes on a 13.60 console: elfldr "file:" spawning works, Unix socket files
// are blocked for payloads, SCM_RIGHTS works in-process. So instead of a
// socket handshake:
//   1. write ticket <dir>/req-<pid>-<seq>.t : parent pid, fd number, argv
//   2. ask the spawner (elfldr) to start the multi-call ELF
//   3. the child claims the ticket (atomic rename), copies the fd out of us
//      (Sony syscall 0x25b), writes <dir>/ack-<pid>-<seq> with its pid
// We keep the fd open until the ack; WebKit then closes its copy.
//
// OMNI_PERF_D_T1: the first WebProcess and NetworkProcess used to be started only when WebKit asked
// for them, one after the other, and WebKit waits for each on the UI thread: 694-2490 ms each, the
// UI frozen 1.6-3.3 s at every app start. omni_launcher_prespawn() (called by OmniMain.cpp at the
// very start of the UI process, before audio, decoder service, SDL and fonts) starts two spare
// processes; both load while the shell starts, and WebKit's first two launches find a loaded spare
// (acknowledged in ~25 ms, as later launches already were). /data/omni/prespawn-disabled.flag: off.
// SPDX-License-Identifier: GPL-3.0-or-later
#include "launcher-common.h"

#include <mutex>
#include <signal.h>
#include <vector>
#include <pthread.h>

namespace {
std::mutex g_seqLock;
unsigned g_seq;
omni_spawn_fn g_spawner = nullptr;
// Spare processes (see launcher-child.cpp): started ahead of time so WebKit's
// launchProcess(), which runs on the UI thread, does not wait for the ELF loader
// (0.9 s normally, 5.7 s seen when YouTube opened a new WebProcess).
std::mutex g_spareLock;
int g_started = 0;   // processes started and not yet acknowledged a request
int g_waiting = 0;   // requests written and not yet acknowledged
// OMNI_PERF_D_T1: tickets of the early spares; a ticket disappears when its process has loaded
// (a loaded process consumes exactly one spare ticket of its parent).
std::mutex g_earlyLock;
std::vector<std::string> g_earlyTickets;
double g_earlyStart = 0;
int g_launches = 0;

int spawnOne(const char* target, std::string* ticketOut = nullptr)
{
    unsigned seq;
    {
        std::lock_guard<std::mutex> lk(g_seqLock);
        seq = ++g_seq;
    }
    char name[64];
    snprintf(name, sizeof(name), "spare-%d-%u.t", (int)getpid(), seq);
    std::string ticket = omni_launcher_dir() + "/" + name, tmp = ticket + ".tmp";
    if (FILE* f = fopen(tmp.c_str(), "w")) {
        fprintf(f, "%ld %d\n", (long)time(nullptr), (int)getpid());
        fclose(f);
        rename(tmp.c_str(), ticket.c_str());
    }
    int sp = (g_spawner ? g_spawner : omni_spawn_elf)(target);
    if (sp < 0)
        unlink(ticket.c_str());
    else if (ticketOut)
        *ticketOut = ticket;
    return sp;
}

// Start processes until every waiting request has one, plus `reserve` spare.
void topUp(const char* target, int reserve)
{
    std::lock_guard<std::mutex> lk(g_spareLock);
    while (g_started < g_waiting + reserve) {
        int sp = spawnOne(target);
        omni_launcher_trace("launch: started %s process (result=%d)\n", g_started < g_waiting ? "a" : "a spare", sp);
        if (sp < 0)
            break;
        g_started++;
    }
}

// OMNI_PERF_D_T1: early spares loaded so far (their tickets are gone).
int earlyLoaded(int* total)
{
    std::lock_guard<std::mutex> lk(g_earlyLock);
    int loaded = 0;
    struct stat st;
    for (auto& t : g_earlyTickets)
        if (stat(t.c_str(), &st))
            loaded++;
    if (total)
        *total = (int)g_earlyTickets.size();
    return loaded;
}

// OMNI_PERF_D_T1: one log line when each early spare has loaded (measures the loader's
// parallelism on the console). Polls a few stat() calls every 10 ms, for at most 20 s.
void* earlyWatch(void*)
{
    int reported = 0;
    for (int i = 0; i < 2000; i++) {
        int total = 0;
        int loaded = earlyLoaded(&total);
        while (reported < loaded)
            omni_launcher_trace("launch: early spare %d of %d loaded %.0f ms after start (OMNI_PERF_D_T1)\n", ++reported, total, omni_now_ms() - g_earlyStart);
        if (reported >= total)
            break;
        usleep(10000);
    }
    return nullptr;
}
}

extern "C" void omni_launcher_set_spawner(omni_spawn_fn fn) { g_spawner = fn; }

// OMNI_PERF_D_T1: start `count` spare processes now (UI process, before anything else). Returns
// how many were started. The steady state is unchanged: after the first two launches one spare is
// kept, as before.
extern "C" int omni_launcher_prespawn(const char* target, int count)
{
    if (!target || count <= 0)
        return 0;
    omni_launcher_dir_ensure();
    g_earlyStart = omni_now_ms();
    int started = 0;
    {
        std::lock_guard<std::mutex> lk(g_spareLock);
        while (started < count) {
            std::string ticket;
            int sp = spawnOne(target, &ticket);
            omni_launcher_trace("launch: started an early spare process (result=%d, OMNI_PERF_D_T1)\n", sp);
            if (sp < 0)
                break;
            g_started++;
            started++;
            std::lock_guard<std::mutex> ek(g_earlyLock);
            g_earlyTickets.push_back(ticket);
        }
    }
    if (started) {
        pthread_attr_t attr;
        pthread_t thread;
        if (!pthread_attr_init(&attr)) {
            pthread_attr_setstacksize(&attr, 128 * 1024);
            pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
            pthread_create(&thread, &attr, earlyWatch, nullptr);
            pthread_attr_destroy(&attr);
        }
    }
    return started;
}

// OMNI_PERF_D_T1: early spares started but not loaded yet (0 when none were started). The shell
// can use it to delay its first page creation while it keeps drawing (not used by WS-D).
extern "C" int omni_launcher_spares_pending(void)
{
    int total = 0;
    int loaded = earlyLoaded(&total);
    return total - loaded;
}

namespace PlayStation {

int32_t launchProcess(const char* path, char* argv[], LaunchParam param)
{
    omni_launcher_trace("launch: path=%s socket=%d\n", path ? path : "(null)", param.sock);
    omni_launcher_dir_ensure();
    unsigned seq;
    {
        std::lock_guard<std::mutex> lk(g_seqLock);
        seq = ++g_seq;
    }
    char name[64];
    snprintf(name, sizeof(name), "%d-%u", (int)getpid(), seq);
    std::string base = omni_launcher_dir() + "/";
    std::string ticket = base + "req-" + name + ".t";
    std::string ack = base + "ack-" + name;
    unlink(ack.c_str());

    // write to a temp name, then rename: children never see half a ticket
    std::string tmp = ticket + ".tmp";
    FILE* f = fopen(tmp.c_str(), "w");
    if (!f)
        return -1;
    fprintf(f, "%ld %d %d\n%s\n", (long)time(nullptr), (int)getpid(), param.sock, path ? path : "");
    for (int i = 0; argv && argv[i] && i < 15; i++)
        fprintf(f, "%s\n", argv[i]);
    fclose(f);
    if (rename(tmp.c_str(), ticket.c_str()))
        return -1;

    const char* self = getenv("OMNI_SELF_PATH");
    const char* target = self ? self : path;
    {
        std::lock_guard<std::mutex> lk(g_spareLock);
        g_waiting++;
    }
    topUp(target, 0); // a spare may already be waiting; start one only if needed
    {
        std::lock_guard<std::mutex> lk(g_spareLock);
        if (g_started < g_waiting) { // could not start a process for this request
            g_waiting--;
            unlink(ticket.c_str());
            omni_launcher_trace("launch: spawn failed\n");
            return -2;
        }
    }
    int earlyTotal = 0;
    const int earlyReady = earlyLoaded(&earlyTotal);
    const int launchNumber = ++g_launches;
    double t0 = omni_now_ms();
    bool extraStarted = false;
    while (omni_now_ms() - t0 < 120000) {
        FILE* a = fopen(ack.c_str(), "r");
        if (a) {
            int pid = -4;
            if (fscanf(a, "%d", &pid) != 1)
                pid = -4;
            fclose(a);
            unlink(ack.c_str());
            omni_launcher_trace("launch: acknowledged pid=%d after %.0f ms\n", pid, omni_now_ms() - t0);
            if (earlyTotal)
                omni_launcher_trace("launch: launch %d: %d of %d early spares were loaded when it was asked, %.0f ms after start (OMNI_PERF_D_T1)\n",
                    launchNumber, earlyReady, earlyTotal, t0 - g_earlyStart);
            {
                std::lock_guard<std::mutex> lk(g_spareLock);
                g_waiting--;
                if (g_started > 0)
                    g_started--;
            }
            topUp(target, 1); // keep one spare ready for the next launch
            return pid; // child pid, or negative error reported by the child
        }
        if (!extraStarted && omni_now_ms() - t0 > 5000) {
            // The process meant for this request may have died while loading.
            extraStarted = true;
            std::lock_guard<std::mutex> lk(g_spareLock);
            if (spawnOne(target) >= 0)
                g_started++;
            omni_launcher_trace("launch: no answer after 5 s, started another process\n");
        }
        usleep(5000);
    }
    unlink(ticket.c_str()); // nobody claimed it
    {
        std::lock_guard<std::mutex> lk(g_spareLock);
        g_waiting--;
    }
    omni_launcher_trace("launch: acknowledgment timed out\n");
    return -3;
}

int terminateProcess(int32_t pid)
{
    return pid > 0 ? kill(pid, SIGKILL) : -1;
}

} // namespace PlayStation
