// Host test for spare processes: after the first launches, a later launch is
// answered by an already-running spare (fast), and spares exit with the parent.
// SPDX-License-Identifier: BSD-2-Clause
#include <omni-launcher.h>
#include <process-launcher.h>
#include <dirent.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include <vector>

static double now() { timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec * 1e3 + t.tv_nsec / 1e6; }
// Simulated ELF-loader start-up cost.
static int slowSpawn(const char* path)
{
    pid_t p = fork();
    if (p < 0) return -1;
    if (!p) { usleep(400000); execl(path, path, (char*)nullptr); _exit(127); }
    return 0;
}

int main(int, char** argv0)
{
    char* args[16]; int argc = 0;
    int role = omni_child_bootstrap(args, 16, &argc);
    if (role == OMNI_ROLE_CHILD) {
        int fd = PlayStation::getConnectionIdentifier();
        char msg[64]; int n = snprintf(msg, sizeof msg, "hello %s", argc > 1 ? args[1] : "-");
        if (write(fd, msg, n) != n) return 1;
        char b[8]; ssize_t r = read(fd, b, sizeof b); // until UI closes
        (void)r; for (int k = 0; k < argc; k++) free(args[k]); return 0;
    }
    if (role == OMNI_ROLE_ERROR) return 1;
    setvbuf(stdout, nullptr, _IONBF, 0);
    setenv("OMNI_SELF_PATH", argv0[0], 1);
    omni_launcher_set_spawner(slowSpawn);
    int fails = 0; std::vector<int> socks;
    for (int i = 0; i < 4; i++) {
        int sp[2]; socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, sp);
        char id[16]; snprintf(id, sizeof id, "%d", 2000 + i); char* av[] = { id, nullptr };
        double t0 = now();
        int32_t pid = PlayStation::launchProcess("/app0/WebProcess.self", av, { sp[1], 0 });
        double ms = now() - t0;
        close(sp[1]);
        char buf[64] = {}; ssize_t r = read(sp[0], buf, sizeof buf - 1);
        printf("launch %d: pid %d in %.0f ms, child says \"%s\"\n", i, pid, ms, r > 0 ? buf : "");
        if (pid <= 0 || r <= 0 || !strstr(buf, id)) fails++;
        if (i >= 1 && ms > 200) { printf("  expected a spare to answer quickly\n"); fails++; }
        socks.push_back(sp[0]);
        usleep(600000); // let the replacement spare finish loading
    }
    for (int s : socks) close(s);   // children exit
    // Count processes still running (children + spares); spares must exit once we are gone.
    pid_t watcher = fork();
    if (!watcher) {
        usleep(300000);                      // parent exits meanwhile
        sleep(2);
        int alive = 0;
        DIR* d = opendir("/proc");
        while (struct dirent* e = readdir(d)) {
            char p[300], comm[64] = {}; snprintf(p, sizeof p, "/proc/%s/cmdline", e->d_name);
            FILE* f = fopen(p, "r"); if (!f) continue;
            size_t n = fread(comm, 1, sizeof comm - 1, f); fclose(f); comm[n] = 0;
            if (!strncmp(comm, "/tmp/omni-spare-test", 20) && atoi(e->d_name) != getpid()) alive++;
        }
        closedir(d);
        printf("processes left 2.3 s after the parent exited: %d\n", alive);
        FILE* r = fopen("/tmp/omni-spare-result", "w"); fprintf(r, "%d\n", alive); fclose(r);
        _exit(0);
    }
    printf(fails ? "FAILED (%d)\n" : "spare launches passed\n", fails);
    _exit(fails ? 1 : 0);
}
