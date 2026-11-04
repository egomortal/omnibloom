// Omni Engine: process launcher, child side.
// SPDX-License-Identifier: GPL-3.0-or-later
#include "launcher-common.h"

#include <algorithm>
#include <dirent.h>
#include <errno.h>
#include <signal.h>
#include <string.h>
#include <vector>

namespace {
int g_childConnection = -1;
std::string g_dir;
}

std::string& omni_launcher_dir_ref() { return g_dir; }

extern "C" void omni_launcher_set_dir(const char* dir) { g_dir = dir ? dir : ""; }
extern "C" void omni_launcher_set_socket_path(const char*) { } // v1 API, unused now
extern "C" int omni_launcher_listen(void)
{
    omni_launcher_dir_ensure();
    return 0;
}

// Is process `pid` still running? (EPERM: exists but belongs to someone else.)
static bool processAlive(int pid)
{
    return pid > 0 && (!kill(pid, 0) || errno == EPERM);
}

// Parent pid encoded in a ticket name: "<kind>-<pid>-<seq>.t".
static int ticketParent(const char* name)
{
    const char* dash = strchr(name, '-');
    return dash ? atoi(dash + 1) : 0;
}

// Claim the oldest fresh ticket of a kind ("req-" or "spare-"), optionally only
// one from parent `onlyParent`. Tickets whose parent is gone or that are stale
// are deleted. Returns the claimed path (renamed to *.claimed-<pid>) or "".
static std::string claimTicket(const char* kind, int onlyParent = 0)
{
    const std::string& dir = omni_launcher_dir();
    DIR* d = opendir(dir.c_str());
    if (!d)
        return { };
    size_t kindLength = strlen(kind);
    std::vector<std::string> names;
    while (struct dirent* e = readdir(d)) {
        size_t n = strlen(e->d_name);
        if (!strncmp(e->d_name, kind, kindLength) && n > 2 && !strcmp(e->d_name + n - 2, ".t"))
            names.emplace_back(e->d_name);
    }
    closedir(d);
    std::vector<std::pair<long, std::string>> byAge;
    for (auto& n : names) {
        int parent = ticketParent(n.c_str());
        if (onlyParent && parent != onlyParent)
            continue;
        struct stat st;
        std::string p = dir + "/" + n;
        if (stat(p.c_str(), &st))
            continue;
        // Stale: older than the parent's 120 s startup deadline, or the parent is
        // gone (a spare ticket must also be recent, so a ticket left from before a
        // reboot can never turn a newly launched UI process into a spare).
        long age = (long)time(nullptr) - (long)st.st_mtime;
        if (age > 180 || (!strcmp(kind, "spare-") && age > 120) || parent == (int)getpid() || !processAlive(parent)) {
            unlink(p.c_str());
            continue;
        }
        byAge.emplace_back((long)st.st_mtime, p);
    }
    std::sort(byAge.begin(), byAge.end());
    char mine[32];
    snprintf(mine, sizeof(mine), ".claimed-%d", (int)getpid());
    for (auto& [mtime, p] : byAge) {
        std::string claimed = p + mine;
        if (!rename(p.c_str(), claimed.c_str()))
            return claimed; // atomic: only one child wins
    }
    return { };
}

extern "C" int omni_child_bootstrap(char** argvOut, int maxArgs, int* argcOut)
{
    *argcOut = 0;
    // Every process the launcher starts comes with one "spare" ticket. A process
    // that finds a request takes it and drops one spare ticket of the same parent
    // (its own); one that finds none becomes a spare: already loaded, it waits for
    // the parent's next request, so a launch no longer waits for the ELF loader.
    std::string t = claimTicket("req-");
    if (!t.empty()) {
        std::string own = claimTicket("spare-", ticketParent(t.substr(t.rfind('/') + 1).c_str()));
        if (!own.empty())
            unlink(own.c_str());
    } else {
        std::string spare = claimTicket("spare-");
        if (spare.empty())
            return OMNI_ROLE_FIRST; // nobody asked for a child: we are the UI process
        int parent = ticketParent(spare.substr(spare.rfind('/') + 1).c_str());
        unlink(spare.c_str());
        omni_launcher_trace("bootstrap: spare for parent %d waiting\n", parent);
        for (unsigned i = 0;; i++) {
            t = claimTicket("req-", parent);
            if (!t.empty())
                break;
            if (i % 25 == 0 && !processAlive(parent))
                _exit(0); // parent gone: nothing will ever ask
            usleep(20000);
        }
    }

    FILE* f = fopen(t.c_str(), "r");
    if (!f)
        return OMNI_ROLE_ERROR;
    long when = 0;
    int ppid = 0, pfd = -1;
    char line[4096];
    bool ok = fscanf(f, "%ld %d %d\n", &when, &ppid, &pfd) == 3;
    while (ok && *argcOut < maxArgs && fgets(line, sizeof(line), f)) {
        line[strcspn(line, "\n")] = 0;
        argvOut[(*argcOut)++] = strdup(line);
    }
    fclose(f);
    unlink(t.c_str());

    // ack file name = ticket name with "req-" -> "ack-" and no suffix
    std::string base = t.substr(t.rfind('/') + 1);
    std::string name = base.substr(4, base.find(".t") - 4);
    std::string ack = omni_launcher_dir() + "/ack-" + name;

    omni_launcher_trace("bootstrap: before descriptor handover parent=%d fd=%d ticket-valid=%d\n", ppid, pfd, ok);
    int fd = ok ? omni_remote_dup(ppid, pfd) : -1;
    omni_launcher_trace("bootstrap: parent=%d source-fd=%d copied-fd=%d errno=%d\n", ppid, pfd, fd, errno);
    if (fd < 0 && ok && !omni_raise_privileges())
        fd = omni_remote_dup(ppid, pfd);

    std::string tmp = ack + ".tmp";
    if (FILE* a = fopen(tmp.c_str(), "w")) {
        fprintf(a, "%d\n", fd >= 0 ? (int)getpid() : -5);
        fclose(a);
        rename(tmp.c_str(), ack.c_str());
    }
    if (fd < 0)
        return OMNI_ROLE_ERROR;
    g_childConnection = fd;
    return OMNI_ROLE_CHILD;
}

namespace PlayStation {
int getConnectionIdentifier() { return g_childConnection; }
}
