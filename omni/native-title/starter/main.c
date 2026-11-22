/* Omni engine starter (OMNI_STARTER_V3). SPDX-License-Identifier: GPL-3.0-or-later
V1: chunked loading. V2: reaps finished engines, "quit" request, takes over from an older starter.
V3: exits instead of listening when it can't bind 127.0.0.1:9031, checks each ELF before loading it, answers
"version" and tells the client when a request is refused or fails, kills the new process on every error path.

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
#include <sys/wait.h>
#include <poll.h>
#include <elf.h>

#include "gpl/elfldr.h"

#define STARTER_PORT 9031
#define STARTER_VERSION "OMNI_STARTER_V4"
/* V4 (2026-11-20): "pt" request -> "pt <used> <total>
", the kernel CPU page-table pool (sceKernelGetPageTableStats,
   which a payload can call and the title cannot) for the title's page-table governor (OMNI_PT_BACKSTOP). */
int sceKernelGetPageTableStats(int* cpuTotal, int* cpuAvailable, int* gpuTotal, int* gpuAvailable);
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

// A short answer to the client. Only on connections that won't become a process's stdout (a send time-out there
// would make the engine lose log lines), and with a time-out so a client that doesn't read can't stall us.
static void reply(int c, const char* text)
{
    struct timeval tv = { 2, 0 };
    setsockopt(c, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
    (void)!write(c, text, strlen(text));
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

// V3 (2026-11-15): check the file before the loader reads it. The loader trusts every offset in the ELF; a cut-off
// or damaged file (a half-finished copy, a bad download) would make it read past the end of the mapping and crash
// the starter, or copy garbage into a process that then runs with full privileges. Omni's engines are all
// position-independent (ET_DYN) with their lowest address at 0, which is also all the chunked loader handles.
static int in_file(uint64_t off, uint64_t len, size_t size)
{
    return off <= size && len <= size - off;
}

static const char* elf_problem(const uint8_t* elf, size_t size)
{
    if (size < sizeof(Elf64_Ehdr)) return "too small";
    const Elf64_Ehdr* eh = (const Elf64_Ehdr*)elf;
    if (memcmp(eh->e_ident, ELFMAG, SELFMAG) || eh->e_ident[EI_CLASS] != ELFCLASS64 || eh->e_ident[EI_DATA] != ELFDATA2LSB)
        return "not a 64-bit little-endian ELF";
    if (eh->e_type != ET_DYN) return "not position-independent (ET_DYN)";
    if (eh->e_phentsize != sizeof(Elf64_Phdr) || !eh->e_phnum || !in_file(eh->e_phoff, (uint64_t)eh->e_phnum * sizeof(Elf64_Phdr), size))
        return "program headers outside the file";
    if (eh->e_shnum && (eh->e_shentsize != sizeof(Elf64_Shdr) || !in_file(eh->e_shoff, (uint64_t)eh->e_shnum * sizeof(Elf64_Shdr), size)))
        return "section headers outside the file";
    const Elf64_Phdr* ph = (const Elf64_Phdr*)(elf + eh->e_phoff);
    uint64_t lo = UINT64_MAX, hi = 0;
    for (int i = 0; i < eh->e_phnum; ++i) {
        if (ph[i].p_vaddr > (1ull << 32) || ph[i].p_memsz > (1ull << 32)) return "segment address out of range";
        if (ph[i].p_vaddr < lo) lo = ph[i].p_vaddr;
        if (ph[i].p_vaddr + ph[i].p_memsz > hi) hi = ph[i].p_vaddr + ph[i].p_memsz;
        if (ph[i].p_type == PT_LOAD && (ph[i].p_filesz > ph[i].p_memsz || !in_file(ph[i].p_offset, ph[i].p_filesz, size)))
            return "segment data outside the file";
    }
    if (lo != 0) return "lowest address is not 0";
    if (hi > (1ull << 30)) return "image larger than 1 GB";
    if (eh->e_entry >= hi) return "entry point outside the image";
    const Elf64_Shdr* sh = eh->e_shnum ? (const Elf64_Shdr*)(elf + eh->e_shoff) : 0;
    for (int i = 0; i < eh->e_shnum; ++i) {
        if (sh[i].sh_type != SHT_RELA) continue;
        if (!in_file(sh[i].sh_offset, sh[i].sh_size, size)) return "relocations outside the file";
        const Elf64_Rela* r = (const Elf64_Rela*)(elf + sh[i].sh_offset);
        for (uint64_t j = 0, n = sh[i].sh_size / sizeof(Elf64_Rela); j < n; ++j)
            if ((r[j].r_info & 0xffffffffu) == R_X86_64_RELATIVE && (r[j].r_offset > hi || hi - r[j].r_offset < 8))
                return "relocation outside the image";   // the loader would silently skip it
    }
    return 0;
}

static pid_t start_file(const char* path, int stdio)
{
    int fd = open(path, O_RDONLY);
    if (fd < 0) { say("open %s: errno %d", path, errno); return -1; }
    struct stat st;
    if (fstat(fd, &st) || st.st_size < 64 || (uint64_t)st.st_size > (1ull << 30)) { say("%s: bad size", path); close(fd); return -1; }
    uint8_t* elf = mmap(0, (size_t)st.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
    close(fd);
    if (elf == MAP_FAILED) { say("mmap %s: errno %d", path, errno); return -1; }
    const char* problem = elf_problem(elf, (size_t)st.st_size);
    if (problem) { say("%s: refused, %s", path, problem); munmap(elf, (size_t)st.st_size); return -1; }
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
    if (bind(server, (struct sockaddr*)&sa, sizeof sa)) {
        // An older starter holds the port: ask it to quit (V2+ understands "quit"), then try again.
        int q = socket(AF_INET, SOCK_STREAM, 0);
        static const char quit[] = { 'q', 'u', 'i', 't', 10 };
        if (q >= 0 && !connect(q, (struct sockaddr*)&sa, sizeof sa)) { (void)!write(q, quit, sizeof quit); }
        if (q >= 0) close(q);
        int bound = 0;
        for (int i = 0; i < 50 && !bound; ++i) {
            bound = !bind(server, (struct sockaddr*)&sa, sizeof sa);
            if (!bound) usleep(100000);
        }
        // V3: never listen() on a socket that isn't bound to 127.0.0.1. listen() on an unbound socket binds it to
        // a random port on EVERY interface, which would let anything on the network start programs with full
        // privileges. If the old starter won't let go of the port, give up; the title then uses elfldr.
        if (!bound) {
            say("bind 127.0.0.1:%d: errno %d (another starter still running); exiting", STARTER_PORT, errno);
            return 1;
        }
    }
    if (listen(server, 16)) {
        say("listen 127.0.0.1:%d: errno %d", STARTER_PORT, errno);
        return 1;
    }
    say("ready on 127.0.0.1:%d (%s, pid %d)", STARTER_PORT, STARTER_VERSION, (int)getpid());

    for (;;) {
        // V2 (2026-11-15): reap the engine processes we started once they end. V1 never did, so every finished
        // engine stayed behind as a zombie (listed at 0 MB), and the console never looked idle. Reaping happens
        // here, between requests, so it can't take the stop events elfldr_spawn() waits for.
        while (waitpid(-1, 0, WNOHANG) > 0) { }
        struct pollfd pf = { server, POLLIN, 0 };
        if (poll(&pf, 1, 1000) <= 0) continue;
        int c = accept(server, 0, 0);
        if (c < 0) { if (errno != EINTR) usleep(100000); continue; }
        // 2 s to send the request line (the title sends it at once): a client that connects and says nothing
        // can't hold the only request slot for long.
        struct timeval tv = { 2, 0 };
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
        if (got && line[got - 1] == '\r') line[--got] = 0;
        if (!strcmp(line, "quit")) { say("quit requested (a newer starter is taking over)"); close(c); return 0; }
        if (!strcmp(line, "pt")) {   // V4: the kernel page-table pool, for the title's governor
            int total = 0, avail = 0, gt = 0, ga = 0;
            char out[64];
            if (sceKernelGetPageTableStats(&total, &avail, &gt, &ga) == 0 && total > 0 && avail >= 0 && avail <= total)
                snprintf(out, sizeof out, "pt %d %d\n", total - avail, total);
            else
                snprintf(out, sizeof out, "pt -1 0\n");
            reply(c, out);
            close(c);
            continue;
        }
        if (!strcmp(line, "version")) {   // V3: lets the title tell an older starter apart and replace it
            reply(c, STARTER_VERSION "\n");
            close(c);
            continue;
        }
        if (strncmp(line, "file:", 5) || !allowed(line + 5)) {
            say("refused request \"%.80s\"", line);
            reply(c, "omni-starter: refused\n");
            close(c);
            continue;
        }
        struct timespec t0, t1;
        clock_gettime(CLOCK_MONOTONIC, &t0);
        pid_t pid = start_file(line + 5, c);
        clock_gettime(CLOCK_MONOTONIC, &t1);
        long ms = (t1.tv_sec - t0.tv_sec) * 1000 + (t1.tv_nsec - t0.tv_nsec) / 1000000;
        say("%s -> pid %d (%ld ms)", line + 5, (int)pid, ms);
        if (pid < 0) reply(c, "omni-starter: start failed (see starter.log)\n");
        close(c);   // the new process holds its own copy as stdout/stderr
    }
}
