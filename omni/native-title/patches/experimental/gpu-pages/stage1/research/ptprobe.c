/* OMNI_PTPROBE_V1 (2026-11-18): does mapping memory with 2 MiB alignment cost fewer kernel page tables on the PS5?
 *
 * The console's ShellCore logs "page table CPU <n>/8192" every ~2 s in the kernel log (captured by klog_capture.py).
 * This payload maps 1 GiB in 32 MiB blocks four ways, touches every 4 KiB page, holds each for 20 s, unmaps, and marks
 * every phase in the kernel log (stderr) and in /data/omni/ptprobe.txt:
 *   A  anonymous mmap (plain)                        - what libpas does (the web process)
 *   B  anonymous mmap, MAP_ALIGNED(21) (2 MiB)       - libpas' optional aligned path
 *   C  direct memory, 64 KiB alignment               - what the title's heap / thread stacks do
 *   D  direct memory, 2 MiB alignment                - what RADV does
 * Phases C/D are skipped (logged) if a payload cannot get direct memory. Run with Omni closed. */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

int sceKernelAllocateMainDirectMemory(size_t len, size_t align, int type, off_t *phys);
int sceKernelMapDirectMemory(void **addr, size_t len, int prot, int flags, off_t phys, size_t align);
int sceKernelReleaseDirectMemory(off_t start, size_t len);

#define BLOCK (32ull << 20)
#define NBLK 32
static FILE *out;

static void mark(const char *fmt, const char *a, long b)
{
    char line[200];
    time_t t = time(NULL);
    struct tm tm; gmtime_r(&t, &tm);
    char ts[32]; strftime(ts, sizeof ts, "%Y-%m-%dT%H:%M:%SZ", &tm);
    snprintf(line, sizeof line, "PTPROBE %s ", ts);
    size_t n = strlen(line);
    snprintf(line + n, sizeof line - n, fmt, a, b);
    fprintf(stderr, "%s\n", line);
    if (out) { fprintf(out, "%s\n", line); fflush(out); }
}

static void touch(void *p) { volatile uint8_t *b = p; for (size_t i = 0; i < BLOCK; i += 4096) b[i] = (uint8_t)i; }

static void anon(const char *name, int extra)
{
    void *blk[NBLK] = {0}; int ok = 0;
    mark("%s start", name, 0);
    for (int i = 0; i < NBLK; ++i) {
        void *p = mmap(NULL, BLOCK, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON | extra, -1, 0);
        if (p == MAP_FAILED) { mark("%s mmap failed errno=%ld", name, errno); break; }
        touch(p); blk[i] = p; ++ok;
    }
    mark("%s mapped+touched blocks=%ld (hold 20 s)", name, ok);
    sleep(20);
    for (int i = 0; i < NBLK; ++i) if (blk[i]) munmap(blk[i], BLOCK);
    mark("%s released", name, 0);
    sleep(10);
}

static void direct(const char *name, size_t align)
{
    void *addr[NBLK] = {0}; off_t phys[NBLK]; int ok = 0;
    mark("%s start", name, 0);
    for (int i = 0; i < NBLK; ++i) {
        int r = sceKernelAllocateMainDirectMemory(BLOCK, align, 0 /* WB_ONION */, &phys[i]);
        if (r) { mark("%s allocate failed 0x%lx", name, (long)(unsigned)r); break; }
        void *a = NULL;
        r = sceKernelMapDirectMemory(&a, BLOCK, PROT_READ | PROT_WRITE, 0, phys[i], align);
        if (r) { mark("%s map failed 0x%lx", name, (long)(unsigned)r); sceKernelReleaseDirectMemory(phys[i], BLOCK); break; }
        touch(a); addr[i] = a; ++ok;
    }
    mark("%s mapped+touched blocks=%ld (hold 20 s)", name, ok);
    sleep(20);
    for (int i = 0; i < NBLK; ++i) if (addr[i]) { munmap(addr[i], BLOCK); sceKernelReleaseDirectMemory(phys[i], BLOCK); }
    mark("%s released", name, 0);
    sleep(10);
}

int main(void)
{
    out = fopen("/data/omni/ptprobe.txt", "w");
    mark("%s baseline (hold 15 s)", "begin", 0);
    sleep(15);
    anon("A-anon-plain", 0);
#ifdef MAP_ALIGNED
    anon("B-anon-2M", MAP_ALIGNED(21));
#else
    mark("%s skipped: no MAP_ALIGNED", "B-anon-2M", 0);
#endif
    direct("C-direct-64K", 64 << 10);
    direct("D-direct-2M", 2 << 20);
    mark("%s done", "end", 0);
    if (out) fclose(out);
    return 0;
}
