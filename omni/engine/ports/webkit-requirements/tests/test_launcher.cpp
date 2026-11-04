// Host test for the Omni launcher: the same binary acts as UI and as children.
// SPDX-License-Identifier: BSD-2-Clause
#include <omni-launcher.h>
#include <process-launcher.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <initializer_list>
#include <thread>
#include <unistd.h>

static int child_main(int argc, char** argv)
{
    int fd = PlayStation::getConnectionIdentifier();
    char msg[256];
    int n = snprintf(msg, sizeof(msg), "child pid=%d role=%s arg=%s argc=%d", getpid(),
        argv[0], argc > 1 ? argv[1] : "-", argc);
    if (write(fd, msg, n) != n)
        return 1;
    char buf[64] = { };
    ssize_t r = read(fd, buf, sizeof(buf) - 1); // wait for UI's reply
    return (r > 0 && !strcmp(buf, "bye")) ? 0 : 2;
}

int main(int, char** argv0)
{
    char* args[16];
    int argc = 0;
    int role = omni_child_bootstrap(args, 16, &argc);
    if (role == OMNI_ROLE_CHILD) {
        int rc = child_main(argc, args);
        for (int i = 0; i < argc; i++)
            free(args[i]); // process-lifetime in real use; freed here for LSan
        return rc;
    }
    if (role == OMNI_ROLE_ERROR) {
        fprintf(stderr, "bootstrap error\n");
        return 1;
    }

    // UI process
    setenv("OMNI_SELF_PATH", argv0[0], 1);
    int fails = 0;
    auto launch = [&](const char* path, const char* id, int* serverOut, int32_t* pidOut) {
        int sp[2];
        socketpair(AF_UNIX, SOCK_SEQPACKET, 0, sp);
        char idbuf[32];
        snprintf(idbuf, sizeof(idbuf), "%s", id);
        char* av[] = { idbuf, nullptr };
        *pidOut = PlayStation::launchProcess(path, av, { sp[1], 0 });
        close(sp[1]);
        *serverOut = sp[0];
    };

    int s1, s2;
    int32_t p1 = 0, p2 = 0;
    std::thread t1([&] { launch("/app0/WebProcess.self", "1001", &s1, &p1); });
    std::thread t2([&] { launch("/app0/NetworkProcess.self", "1002", &s2, &p2); });
    t1.join();
    t2.join();
    printf("launched pids %d %d\n", p1, p2);
    if (p1 <= 0 || p2 <= 0 || p1 == p2)
        fails++;

    for (int s : { s1, s2 }) {
        char buf[256] = { };
        ssize_t r = read(s, buf, sizeof(buf) - 1);
        printf("UI got: %s\n", r > 0 ? buf : "(nothing)");
        if (r <= 0 || !strstr(buf, "role=/app0/"))
            fails++;
        if (write(s, "bye", 3) != 3)
            fails++;
    }
    for (int i = 0; i < 2; i++) {
        int st = 0;
        pid_t w = wait(&st);
        printf("child %d exited %d\n", (int)w, WIFEXITED(st) ? WEXITSTATUS(st) : -1);
        if (!WIFEXITED(st) || WEXITSTATUS(st))
            fails++;
    }
    printf(fails ? "FAILED (%d)\n" : "launcher test passed\n", fails);
    return fails ? 1 : 0;
}
