// Omni Engine: process launcher, parent side (tickets + remote dup).
//
// Probes on a 13.60 console: elfldr "file:" spawning works, Unix socket files
// are blocked for payloads, SCM_RIGHTS works in-process. So instead of a
// socket handshake:
//   1. write ticket <dir>/req-<pid>-<seq>.t : parent pid, fd number, argv
//   2. ask the spawner (elfldr) to start the multi-call ELF
//   3. the child claims the ticket (atomic rename), copies the fd out of us
//      (Sony syscall 0x25b), writes <dir>/ack-<pid>-<seq> with its pid
// We keep the fd open until the ack; WebKit then closes its copy.
// SPDX-License-Identifier: GPL-3.0-or-later
#include "launcher-common.h"

#include <mutex>
#include <signal.h>

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

int spawnOne(const char* target)
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
}

extern "C" void omni_launcher_set_spawner(omni_spawn_fn fn) { g_spawner = fn; }

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
