// Omni Engine launcher: platform primitives (PS5 vs Linux host).
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
#include <unistd.h>

#ifdef __PROSPERO__
#include <arpa/inet.h>
#include <netinet/in.h>
#include <ps5/kernel.h>
#include <sys/socket.h>
#include <pthread.h>

static inline void* omni_drain_loader_output(void* context)
{
    int fd = static_cast<int>(reinterpret_cast<intptr_t>(context));
    char output[1024];
    for (;;) {
        ssize_t count = read(fd, output, sizeof(output));
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) break;
        fwrite(output, 1, static_cast<size_t>(count), stderr);
        fflush(stderr);
    }
    close(fd);
    return nullptr;
}

// Escape the jail, uid 0, all capabilities (as elfldr does). 0 on success.
static inline int omni_raise_privileges(void)
{
    static const uint8_t caps[16] = { 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
                                      0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff };
    pid_t me = getpid();
    intptr_t root = kernel_get_root_vnode();
    if (!root || kernel_set_proc_rootdir(me, root) || kernel_set_proc_jaildir(me, 0)
        || kernel_set_ucred_uid(me, 0) || kernel_set_ucred_caps(me, caps))
        return -1;
    return 0;
}

// Sony syscall 0x25b: duplicate descriptor `fd` of process `pid` into us.
static inline int omni_remote_dup(pid_t pid, int fd)
{
    return syscall(0x25b, pid, fd);
}

// Ask elfldr (127.0.0.1:9021) to start a saved ELF. 0 or -errno.
static inline int omni_spawn_elf(const char* path)
{
    int s = socket(AF_INET, SOCK_STREAM, 0);
    if (s < 0)
        return -errno;
    struct sockaddr_in sa;
    memset(&sa, 0, sizeof(sa));
    sa.sin_family = AF_INET;
    sa.sin_port = htons(9021);
    sa.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (connect(s, (struct sockaddr*)&sa, sizeof(sa))) {
        int e = errno;
        close(s);
        return -e;
    }
    // Prepare the output reader before asking the loader to spawn. Foreground
    // default thread stacks can be 2 MiB; this simple reader needs only 128 KiB.
    // Use a separate descriptor so the caller and reader each own one handle.
    int reader = dup(s);
    if (reader < 0) { int e = errno; close(s); return -e; }
    pthread_attr_t attr;
    int error = pthread_attr_init(&attr);
    if (error) { close(reader); close(s); return -error; }
    error = pthread_attr_setstacksize(&attr, 128 * 1024);
    if (!error) error = pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
    pthread_t thread;
    if (!error) error = pthread_create(&thread, &attr, omni_drain_loader_output, reinterpret_cast<void*>(static_cast<intptr_t>(reader)));
    pthread_attr_destroy(&attr);
    if (error) {
        fprintf(stderr, "launch: output reader creation failed: %d\n", error);
        close(reader); close(s); return -error;
    }
    char line[512];
    int n = snprintf(line, sizeof(line), "file:%s\n", path);
    int ok = write(s, line, (size_t)n) == n;
    if (!ok) {
        shutdown(s, SHUT_RDWR);
        close(s);
        return -EIO;
    }
    // The loader may attach the child's output to this connection. Preserve
    // and drain it until EOF, including output from library constructors.
    shutdown(s, SHUT_WR);
    close(s); // The detached reader owns its duplicate until loader EOF.
    return 0;
}

#else // Linux host (tests)
#include <sys/syscall.h>

static inline int omni_raise_privileges(void) { return 0; }

static inline int omni_remote_dup(pid_t pid, int fd)
{
    int pfd = (int)syscall(SYS_pidfd_open, pid, 0);
    if (pfd < 0)
        return -1;
    int r = (int)syscall(SYS_pidfd_getfd, pfd, fd, 0);
    close(pfd);
    return r;
}

static inline int omni_spawn_elf(const char* path)
{
    pid_t p = fork();
    if (p < 0)
        return -errno;
    if (!p) {
        execl(path, path, (char*)nullptr);
        _exit(127);
    }
    return 0;
}
#endif
