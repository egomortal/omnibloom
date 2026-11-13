/* omni-gpu-pages stage 1 (OMNI_GPU_PAGES_STAGE1_V1), WebProcess side: become a gpu-broker client of the title.
 * SPDX-License-Identifier: GPL-3.0-or-later  (links LGPL-2.1-or-later gpu-broker client code)
 *
 * A separate object linked into the stage-1 child. It changes no WebKit source and none of Omni's own
 * bootstrap code (launcher-child, sec connect, OmniMain); it only adds one constructor and two functions.
 *
 * OFF unless /data/omni/gpu-pages-stage1.flag exists, and /data/omni/gpu-pages-stage1-off.flag (the kill
 * switch) does not. Off, the constructor makes two access() calls and nothing else happens in this process.
 *
 * On:
 *   1. constructor(101), before anything else maps memory: reserve the broker's two host windows exactly where
 *      protocol.h puts them (stage 2's CP-2 client does the same; without both, bind is told so and refuses);
 *   2. omni_gpu_pages_s1_bind(), called by the DrawingArea the first time a page in this process needs GL,
 *      on the main thread: write req-<pid> for the title's OmniGpuPagesService, wait (bounded, 1.5 s) for its
 *      ep-<pid> answer, pull the endpoint out of the title with syscall 0x25b (__sys_rdup), bind, ping.
 * Every failure is a logged return value. The caller then leaves accelerated compositing off for the whole
 * process, which is exactly today's behaviour: no failure here can reach WebKit's RELEASE_ASSERT. */
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include "protocol.h"
#include "client.h"

#define OGP_S1_FLAG "/data/omni/gpu-pages-stage1.flag"
#define OGP_S1_OFF  "/data/omni/gpu-pages-stage1-off.flag"
#define OGP_S1_DIR  "/data/omni/gpu-pages/s1"
#define OGP_S1_WAIT_MS 1500

extern int sceKernelReserveVirtualRange(void** address, size_t bytes, int flags, size_t alignment);
extern int sceKernelMunmap(void* address, size_t bytes);
extern int __sys_rdup(int pid, int fd);

static int g_enabled;     /* 1 when the flag is on and the kill switch is off */
static int g_reserved;    /* both host windows reserved */
static int g_bound;       /* 1 bound, -1 tried and failed */
static int g_noraise, g_nodladdr;   /* OMNI_GPUPAGES_HOOKSPLIT_V1 (diagnostic): stack raising / dladdr rewrite off */

__attribute__((constructor(101))) static void ogp_s1_ctor(void)
{
    if (access(OGP_S1_FLAG, F_OK) || !access(OGP_S1_OFF, F_OK)) return;
    if (!access("/data/omni/gpu-pages-child-off.flag", F_OK)) return;   /* OMNI_GPUPAGES_CHILDOFF_V1 (diagnostic): title side only */
    g_enabled = 1;
    g_noraise = !access("/data/omni/gpu-pages-noraise.flag", F_OK);
    g_nodladdr = !access("/data/omni/gpu-pages-nodladdr.flag", F_OK);
    /* OMNI_GPUPAGES_NORESERVE_V1 (diagnostic): /data/omni/gpu-pages-noreserve.flag skips the host-window reservation
     * (bind then refuses and the process stays on the CPU path), to test whether the reservation slows the process. */
    if (access("/data/omni/gpu-pages-noreserve.flag", F_OK))
        g_reserved = pw_gpu_reserve_host_ranges(sceKernelReserveVirtualRange, sceKernelMunmap);
}

int omni_gpu_pages_s1_enabled(void) { return g_enabled; }
static double ogp_s1_ms(void);
static void ogp_s1_note(const char* fmt, ...);
static void ogp_s1_sampler_start(void);   /* OMNI_GPUPAGES_SAMPLER_V1 */
__attribute__((constructor(102))) static void ogp_s1_ctor_note(void)
{
    if (g_enabled) ogp_s1_note("process start (constructor), host windows %s", g_reserved ? "reserved" : "NOT reserved");
    if (g_enabled) ogp_s1_sampler_start();
}

static double ogp_s1_ms(void)
{
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

static void ogp_s1_note(const char* fmt, ...)
{
    char line[400];
    va_list ap; va_start(ap, fmt);
    int n = vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
    if (n < 0) return;
    fprintf(stderr, "OMNI GPUPAGES child pid=%d t=%.3f: %s\n", (int)getpid(), ogp_s1_ms() / 1000.0, line);   /* lands in the title's process log */
    fflush(stderr);
}

/* RADV/Zink cache UUID (CP-2 try 4 finding): this Mesa build has no HAVE_BUILD_ID, so the UUID comes from dladdr() of a
 * driver function and stat() of dli_fname; a failure makes vkEnumeratePhysicalDevices fail ("cannot generate UUID").
 * Linked with -Wl,--wrap=dladdr. OFF (no flag / kill switch): exactly the real dladdr, so the child behaves as before.
 * ON: a real answer is kept when its file can be stat()ed; otherwise the first stat()-able path of a short list is
 * named (the UUID then follows that file's mtime; the shader disk cache stays disabled either way). */
#include <dlfcn.h>
int __real_dladdr(const void* addr, Dl_info* info);
static volatile int g_role_seen_early;   /* OMNI_GPUPAGES_SAMPLER_V2: set by the first dladdr (= role assigned) */
/* OMNI_GPUPAGES_DLADDR_V3: the rewrite is only active while the DrawingArea runs EGL init (Mesa's cache UUID is
 * computed there: radv_device_get_cache_uuid, zink's disk_cache_init). V2 still renamed every answer about this image
 * for the whole life of the process, and startup stayed slow / playback still stalled. Outside the window every
 * caller gets the real, untouched dladdr answer. */
static volatile int g_dladdr_window;
void omni_gpu_pages_s1_dladdr_window(int on) { __atomic_store_n(&g_dladdr_window, on, __ATOMIC_RELEASE); }
int __wrap_dladdr(const void* addr, Dl_info* info)
{
    int r = __real_dladdr(addr, info);
    if (g_enabled) g_role_seen_early = 1;
    if (!g_enabled || g_nodladdr || !info || !r || !__atomic_load_n(&g_dladdr_window, __ATOMIC_ACQUIRE)) return r;
    /* OMNI_GPUPAGES_DLADDR_V2: V1 stat()ed up to 4 paths on EVERY call and then wiped the whole answer (memset), so
     * every dladdr() in the process lost dli_fbase/dli_sname/dli_saddr (Omni's player watchdog logged "image base 0")
     * and paid the syscalls. With it, startup was ~5-9 s slower and YouTube playback stalled at ~60 s in 7 of 9 runs;
     * with it off (s1a7y) the run passed. Now: only an answer about THIS image is touched, the replacement name is
     * worked out once, and only dli_fname changes (base and symbol stay real). Mesa's UUID only needs a stat()-able
     * dli_fname for its own (= this image's) functions. */
    static const void* s_base;          /* this image's load base (first answer about our own code) */
    static const char* s_use;           /* name to give out instead of an unstat()able one; NULL: keep the real one */
    static int s_ready;                 /* 1 once s_base/s_use are worked out */
    if (!__atomic_load_n(&s_ready, __ATOMIC_ACQUIRE)) {
        Dl_info self;
        if (!__real_dladdr((const void*)&__wrap_dladdr, &self) || !self.dli_fbase) return r;
        struct stat st;
        const char* use = NULL;
        if (!(self.dli_fname && stat(self.dli_fname, &st) == 0 && st.st_mtime)) {
            static const char* const fallback[] = { "/data/omni/native/omni-engine-child.elf", "/data/omni/gpu-pages-stage1.flag", "/data/omni" };
            for (unsigned i = 0; i < sizeof fallback / sizeof *fallback && !use; i++)
                if (stat(fallback[i], &st) == 0 && st.st_mtime) use = fallback[i];
            ogp_s1_note("dladdr: this image (base %p) is named %s, not stat()able; its answers will name %s (worked out once)",
                self.dli_fbase, self.dli_fname ? self.dli_fname : "(none)", use ? use : "nothing (expect 'cannot generate UUID')");
        }
        s_base = self.dli_fbase; s_use = use;
        __atomic_store_n(&s_ready, 1, __ATOMIC_RELEASE);
    }
    if (s_use && info->dli_fbase == s_base) info->dli_fname = s_use;
    return r;
}

/* Thread stacks (CP-2 try 5): radv_shader_object_create has a ~99 KB frame and Mesa has no stack probes, so a thread
 * with a small default stack runs over its guard page while compiling a shader. Linked with -Wl,--wrap=pthread_create,
 * which reaches every thread this child creates from static code: WTF::Thread (the threaded compositor, which runs GL),
 * libc++ std::thread, and Mesa's own C11 thrd_create (util_queue, Zink's compile threads). OFF: exactly the real call.
 * ON: a thread asking for less than the minimum (default 8 MiB; OMNI_GPU_PAGES_STACK_KB, 256..65536) gets the minimum;
 * a caller-supplied stack (stackaddr set) is never touched. Stacks are only raised, never lowered. */
#include <pthread.h>
int __real_pthread_create(pthread_t* t, const pthread_attr_t* a, void* (*fn)(void*), void* arg);
int pthread_attr_get_np(pthread_t, pthread_attr_t*) __attribute__((weak));
static size_t ogp_s1_min_stack(void)
{
    static size_t v;
    if (!v) { const char* e = getenv("OMNI_GPU_PAGES_STACK_KB"); long kb = e ? atol(e) : 0; v = (kb >= 256 && kb <= 65536) ? (size_t)kb << 10 : (size_t)8 << 20; }
    return v;
}
int __wrap_pthread_create(pthread_t* t, const pthread_attr_t* a, void* (*fn)(void*), void* arg)
{
    if (!g_enabled || g_noraise) return __real_pthread_create(t, a, fn, arg);
    /* OMNI_GPUPAGES_SAMPLER_V2: role is now detected in __wrap_dladdr (called first at role assignment) */
    static int raised;
    size_t want = ogp_s1_min_stack(), have = 0;
    if (a) {
        void* addr = NULL;
        if (pthread_attr_getstackaddr(a, &addr) == 0 && addr) return __real_pthread_create(t, a, fn, arg);
        if (pthread_attr_getstacksize(a, &have) == 0 && have >= want) return __real_pthread_create(t, a, fn, arg);
        pthread_attr_setstacksize((pthread_attr_t*)a, want);   /* FreeBSD's pthread_attr_t is the caller's object: raise it in place */
        if (__atomic_add_fetch(&raised, 1, __ATOMIC_RELAXED) <= 6) ogp_s1_note("thread stack raised %zu -> %zu KiB", have >> 10, want >> 10);
        double t0 = ogp_s1_ms();
        int r = __real_pthread_create(t, a, fn, arg);
        double dt = ogp_s1_ms() - t0;
        static int slowA;
        if (dt > 20 && __atomic_add_fetch(&slowA, 1, __ATOMIC_RELAXED) <= 20) ogp_s1_note("pthread_create (raised attr) took %.1f ms", dt);
        return r;
    }
    pthread_attr_t mine; pthread_attr_init(&mine); pthread_attr_getstacksize(&mine, &have);
    if (have < want) pthread_attr_setstacksize(&mine, want);
    if (have < want && __atomic_add_fetch(&raised, 1, __ATOMIC_RELAXED) <= 6) ogp_s1_note("thread stack (default attr) raised %zu -> %zu KiB", have >> 10, want >> 10);
    double t0 = ogp_s1_ms();
    int r = __real_pthread_create(t, &mine, fn, arg);
    double dt = ogp_s1_ms() - t0;
    pthread_attr_destroy(&mine);
    static int slow, count; static double total;
    __atomic_add_fetch(&count, 1, __ATOMIC_RELAXED); total += dt;
    if ((dt > 20 && __atomic_add_fetch(&slow, 1, __ATOMIC_RELAXED) <= 20) || count == 10 || count == 40 || count == 100)
        ogp_s1_note("pthread_create #%d took %.1f ms (default attr; %.1f ms in all so far)", count, dt, total);
    return r;
}

/* OMNI_GPUPAGES_SAMPLER_V1 (diagnostic): with stage 1 on, a WebProcess took ~7.8 s from getting its role to creating
 * its drawing area (layers off: < 0.5 s). Once this process gets its role (its first pthread_create), a sampler thread
 * sends the main thread SIGXCPU every 700 ms, 16 times; the handler writes rip and code addresses found on the stack
 * as image offsets ("OMNI GPUPAGES SAMPLE"). /data/omni/gpu-pages-sampler-off.flag turns it off. */
#include <signal.h>
#include <stdint.h>
static pthread_t g_main_thread;
static uintptr_t g_stack_lo, g_stack_hi;
static const uintptr_t k_base = 0x200000000ull, k_code_end = 0x207000000ull;
static void ogp_s1_w(const char* b, size_t n) { ssize_t r = write(2, b, n); (void)r; }
static size_t ogp_s1_hex(char* o, uintptr_t v) { size_t n = 0; o[n++] = '0'; o[n++] = 'x'; int on = 0;
    for (int sh = 60; sh >= 0; sh -= 4) { int d = (int)((v >> sh) & 15); if (d || on || !sh) { on = 1; o[n++] = "0123456789abcdef"[d]; } } o[n++] = ' '; return n; }
static void ogp_s1_sample_handler(int sig, siginfo_t* info, void* context)
{
    (void)sig; (void)info;
    const uintptr_t* w = (const uintptr_t*)context + 8;   /* uc_mcontext at byte 64 (OmniCrash.h) */
    uintptr_t rip = w[20], rsp = w[23];
    char line[700]; size_t n = 0;
    const char* head = "OMNI GPUPAGES SAMPLE rip="; for (const char* c = head; *c; ++c) line[n++] = *c;
    n += ogp_s1_hex(line + n, rip >= k_base ? rip - k_base : rip);
    line[n++] = '|';
    int found = 0;
    uintptr_t end = rsp + 32 * 1024; if (end > g_stack_hi) end = g_stack_hi;
    for (uintptr_t a = rsp & ~(uintptr_t)7; a >= g_stack_lo && a + 8 <= end && found < 36 && n < sizeof line - 24; a += 8) {
        uintptr_t v = *(const uintptr_t*)a;
        if (v <= k_base || v >= k_code_end) continue;
        n += ogp_s1_hex(line + n, v - k_base); ++found;
    }
    line[n++] = '\n';
    ogp_s1_w(line, n);
}
static void* ogp_s1_sampler(void* arg)
{
    (void)arg;
    while (!g_role_seen_early) usleep(20 * 1000);
    for (int i = 0; i < 24; ++i) {
        usleep(500 * 1000);
        char t[96]; int k = snprintf(t, sizeof t, "OMNI GPUPAGES SAMPLE #%d t=%.3f pid=%d\n", i + 1, ogp_s1_ms() / 1000.0, (int)getpid());
        if (k > 0) ogp_s1_w(t, (size_t)k);
        pthread_kill(g_main_thread, SIGXCPU);
    }
    return NULL;
}
static void ogp_s1_sampler_start(void)
{
    if (access("/data/omni/gpu-pages-sampler.flag", F_OK) || !pthread_attr_get_np) return;   /* opt-in since DLADDR_V2 */
    g_main_thread = pthread_self();
    void* addr = NULL; size_t size = 0; pthread_attr_t a;
    if (pthread_attr_init(&a)) return;
    if (!pthread_attr_get_np(g_main_thread, &a)) pthread_attr_getstack(&a, &addr, &size);
    pthread_attr_destroy(&a);
    if (!addr || !size) return;
    g_stack_lo = (uintptr_t)addr; g_stack_hi = g_stack_lo + size;
    struct sigaction sa; memset(&sa, 0, sizeof sa); sa.sa_sigaction = ogp_s1_sample_handler; sa.sa_flags = SA_SIGINFO | SA_RESTART; sigemptyset(&sa.sa_mask);
    if (sigaction(SIGXCPU, &sa, NULL)) return;
    pthread_t th; pthread_attr_t ta; pthread_attr_init(&ta); pthread_attr_setstacksize(&ta, 256 << 10);
    if (!__real_pthread_create(&th, &ta, ogp_s1_sampler, NULL)) pthread_detach(th);
    pthread_attr_destroy(&ta);
}

static void ogp_s1_log_stack(const char* who)
{
    size_t size = 0; void* addr = NULL; pthread_attr_t a;
    if (pthread_attr_get_np && pthread_attr_init(&a) == 0) {
        if (pthread_attr_get_np(pthread_self(), &a) == 0) pthread_attr_getstack(&a, &addr, &size);
        pthread_attr_destroy(&a);
    }
    ogp_s1_note("%s thread stack: %zu KiB at %p (minimum for new threads while on: %zu KiB)", who, size >> 10, addr, ogp_s1_min_stack() >> 10);
}

static int ogp_s1_fail(char* why, unsigned long size, const char* fmt, ...)
{
    va_list ap; va_start(ap, fmt);
    if (why && size) vsnprintf(why, size, fmt, ap);
    va_end(ap);
    g_bound = -1;
    return -1;
}

/* 0: this process is a GPU client of the title now. -1: it is not, and why says so. Called once. */
int omni_gpu_pages_s1_bind(char* why, unsigned long size)
{
    if (g_bound) return g_bound > 0 ? 0 : ogp_s1_fail(why, size, "already tried and failed");
    if (!g_enabled) return ogp_s1_fail(why, size, "stage 1 is off (no flag, or the kill switch)");
    { static int once; if (!once++) ogp_s1_log_stack("binding (WebProcess main)"); }
    if (!g_reserved) return ogp_s1_fail(why, size, "the broker's host windows were not free at start-up");

    char req[96], ep[96], tmp[112], text[160];
    int pid = (int)getpid();
    snprintf(req, sizeof req, OGP_S1_DIR "/req-%d", pid);
    snprintf(ep, sizeof ep, OGP_S1_DIR "/ep-%d", pid);
    snprintf(tmp, sizeof tmp, "%s.tmp", req);
    mkdir("/data/omni/gpu-pages", 0777); mkdir(OGP_S1_DIR, 0777);
    unlink(ep);
    int fd = open(tmp, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (fd < 0) return ogp_s1_fail(why, size, "cannot write %s (errno %d)", tmp, errno);
    int n = snprintf(text, sizeof text, "%d\n", pid);
    (void)!write(fd, text, (size_t)n); fsync(fd); close(fd);
    if (rename(tmp, req)) return ogp_s1_fail(why, size, "cannot publish %s (errno %d)", req, errno);

    double t0 = ogp_s1_ms();
    int titlePid = -1, titleFd = -1, cookie = -1;
    for (;;) {
        int e = open(ep, O_RDONLY);
        if (e >= 0) {
            ssize_t got = read(e, text, sizeof text - 1);
            close(e);
            if (got > 0) {
                text[got] = 0;
                if (strstr(text, "error=")) { unlink(req); return ogp_s1_fail(why, size, "the title refused: %s", text); }
                if (sscanf(text, "pid=%d fd=%d cookie=%d", &titlePid, &titleFd, &cookie) == 3) break;
            }
        }
        if (ogp_s1_ms() - t0 > OGP_S1_WAIT_MS) {
            unlink(req);
            return ogp_s1_fail(why, size, "no answer from the title's OmniGpuPagesService in %d ms "
                               "(the title build has no stage-1 service, or its flag is off)", OGP_S1_WAIT_MS);
        }
        usleep(5000);
    }
    unlink(ep);
    int endpoint = __sys_rdup(titlePid, titleFd);
    if (endpoint < 0) return ogp_s1_fail(why, size, "__sys_rdup(%d, %d) failed (errno %d)", titlePid, titleFd, errno);
    /* bind is the round trip (PW_GPU_INIT, answered with the owner's offer); its return is the broker's status.
     * No ps5_gpu_client_ping(): it sends PW_GPU_IMAGE, which this owner does not serve (CP-2 try1, EINVAL). */
    int status = ps5_gpu_client_bind(endpoint, g_reserved != 0);
    if (status) return ogp_s1_fail(why, size, "the broker refused PW_GPU_INIT (status %d)", status);
    g_bound = 1;
    ogp_s1_note("bound to the title's gpu-broker in %.1f ms (cookie %d, endpoint fd %d)", ogp_s1_ms() - t0, cookie, endpoint);
    return 0;
}
