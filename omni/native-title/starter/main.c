/* Omni engine starter (OMNI_STARTER_V1). SPDX-License-Identifier: GPL-3.0-or-later

Starts Omni's engine processes (the .elf files in /data/omni/native) for the Omni title, in place of the payload loader (elfldr,
port 9021). Same request as elfldr's: one line "file:<path>\n" per connection; the new process's stdout and stderr
are that connection (the title drains it, as it does with elfldr).

Why: elfldr reads the whole ELF (~196 MB for Omni's engine) into memory and builds a second full-size copy to
relocate it; its allocator keeps that memory afterwards, so it sat at ~240 MB (up to ~420 MB while starting two
engines) exactly while Omni loads a page, when the console's memory runs out (kernel "LOW FMEM", restarts). This
starter maps the ELF file read-only and relocates it in 16 MB pieces (gpl/elfldr.c, OMNI_STARTER_V1): ~16 MB at
the peak, a few MB the rest of the time.

Only 127.0.0.1 (elfldr listens on every interface), only ELF files directly in /data/omni/native/, one request at a
time. The title starts this through elfldr once (it is small), then talks to it on 127.0.0.1:9031; if it isn't
there, the title falls back to elfldr as before. Log: /data/omni/native/starter.log. */
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>

#include "gpl/elfldr.h"

#define STARTER_PORT 9031
#define NATIVE_DIR "/data/omni/native/"
#define LOG_PATH NATIVE_DIR "starter.log"

static void say(const char* fmt, ...)
{
    char stamp[32];
    time_t now = time(0);
    struct tm tmv;
    gmtime_r(&now, &tmv);
    strftime(stamp, sizeof stamp, "%Y-%m-%dT%H:%M:%SZ", &tmv);
    fprintf(stderr, "%s omni-starter: ", stamp);
    va_list ap;
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
    fputc('\n', stderr);
}

// Only plain file names directly in NATIVE_DIR ending in ".elf": no "..", no further "/".
static int allowed(const char* path)
{
    size_t n = strlen(NATIVE_DIR), len = strlen(path);
    if (len <= n + 4 || len > 200 || strncmp(path, NATIVE_DIR, n))
        return 0;
    const char* name = path + n;
    if (strchr(name, '/') || strstr(name, "..") || strcmp(path + len - 4, ".elf"))
        return 0;
    for (const char* c = name; *c; ++c)
        if (!((*c >= 'a' && *c <= 'z') || (*c >= 'A' && *c <= 'Z') || (*c >= '0' && *c <= '9') || *c == '-' || *c == '_' || *c == '.'))
            return 0;
    return 1;
}

static pid_t start_file(const char* path, int stdio)
{
    int fd = open(path, O_RDONLY);
    if (fd < 0) { say("open %s: errno %d", path, errno); return -1; }
    struct stat st;
    if (fstat(fd, &st) || st.st_size < 64) { say("%s: bad size", path); close(fd); return -1; }
    uint8_t* elf = mmap(0, (size_t)st.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
    close(fd);
    if (elf == MAP_FAILED) { say("mmap %s: errno %d", path, errno); return -1; }
    const char* name = strrchr(path, '/') + 1;
    char procname[32];
    snprintf(procname, sizeof procname, "%s", name);
    char* argv[] = { procname, 0 };
    char* envp[] = { 0 };
    pid_t pid = elfldr_spawn("/", stdio, elf, argv, envp);
    munmap(elf, (size_t)st.st_size);
    return pid;
}

int main(void)
{
    // Our own log instead of elfldr's request connection (so that connection ends for whoever started us).
    int lf = open(LOG_PATH, O_WRONLY | O_CREAT | O_APPEND, 0666);
    if (lf >= 0) { dup2(lf, STDOUT_FILENO); dup2(lf, STDERR_FILENO); close(lf); }
    setvbuf(stdout, 0, _IONBF, 0);
    signal(SIGPIPE, SIG_IGN);

    int server = socket(AF_INET, SOCK_STREAM, 0);
    if (server < 0) { say("socket: errno %d", errno); return 1; }
    int one = 1;
    setsockopt(server, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    struct sockaddr_in sa;
    memset(&sa, 0, sizeof sa);
    sa.sin_family = AF_INET;
    sa.sin_port = htons(STARTER_PORT);
    sa.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (bind(server, (struct sockaddr*)&sa, sizeof sa) || listen(server, 16)) {
        say("bind/listen 127.0.0.1:%d: errno %d (already running?)", STARTER_PORT, errno);
        return 1;
    }
    say("ready on 127.0.0.1:%d (OMNI_STARTER_V1, pid %d)", STARTER_PORT, (int)getpid());

    for (;;) {
        int c = accept(server, 0, 0);
        if (c < 0) { if (errno != EINTR) usleep(100000); continue; }
        struct timeval tv = { 5, 0 };
        setsockopt(c, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
        char line[256];
        size_t got = 0;
        while (got < sizeof line - 1) {
            ssize_t r = read(c, line + got, 1);
            if (r <= 0 || line[got] == '\n') break;
            ++got;
        }
        line[got] = 0;
        if (!got) { close(c); continue; }   // a probe (the title checks that we answer)
        if (strncmp(line, "file:", 5) || !allowed(line + 5)) {
            say("refused request \"%.80s\"", line);
            close(c);
            continue;
        }
        struct timespec t0, t1;
        clock_gettime(CLOCK_MONOTONIC, &t0);
        pid_t pid = start_file(line + 5, c);
        clock_gettime(CLOCK_MONOTONIC, &t1);
        long ms = (t1.tv_sec - t0.tv_sec) * 1000 + (t1.tv_nsec - t0.tv_nsec) / 1000000;
        say("%s -> pid %d (%ld ms)", line + 5, (int)pid, ms);
        close(c);   // the new process holds its own copy as stdout/stderr
    }
}
