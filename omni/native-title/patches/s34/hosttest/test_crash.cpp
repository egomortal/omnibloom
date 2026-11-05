// Host tests for OmniCrash.h OMNI_CRASH_V2 (Linux x86-64; the console layout is fed as a synthetic context).
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <sys/wait.h>
#include <sys/mman.h>
#define OMNI_CRASH_LOG_PATH "/tmp/omni-crash-hosttest.log"
#define OMNI_CRASH_LOG2_PATH "/tmp/omni-crash-hosttest-crash.log"
#include "../engine-patches/entry/OmniCrash.h"

static int failures = 0;
#define CHECK(c, what) do { if (c) printf("ok   %s\n", what); else { printf("FAIL %s\n", what); ++failures; } } while (0)

extern "C" void* __real_malloc(size_t); extern "C" void __real_free(void*);
extern "C" void* __real_calloc(size_t, size_t); extern "C" void* __real_realloc(void*, size_t);
static int counting = 0, allocations = 0;
extern "C" void* __wrap_malloc(size_t n) { if (counting) ++allocations; return __real_malloc(n); }
extern "C" void __wrap_free(void* p) { if (counting) ++allocations; __real_free(p); }
extern "C" void* __wrap_calloc(size_t a, size_t b) { if (counting) ++allocations; return __real_calloc(a, b); }
extern "C" void* __wrap_realloc(void* p, size_t n) { if (counting) ++allocations; return __real_realloc(p, n); }

static std::string readLog()
{
    std::string s; FILE* f = fopen(OMNI_CRASH_LOG_PATH, "r"); if (!f) return s;
    char b[4096]; size_t n; while ((n = fread(b, 1, sizeof b, f)) > 0) s.append(b, n); fclose(f); return s;
}
static uintptr_t lo, hi;   // the test's "readable" memory
static bool testReadable(uintptr_t a, size_t n) { return a >= lo && a + n <= hi; }
__attribute__((noinline)) static void anchorFunction() { asm volatile(""); }

static void unitTests()
{
    // 1. layout: the console's (word 8) proved by mc_addr == si_addr; a shifted one found; none -> -1
    uintptr_t w[64] {}; bool proved = false;
    w[8 + OmniCrash::R_ADDR] = 0x400025f560; w[8 + OmniCrash::R_RSP] = 0x7000001000;
    CHECK(OmniCrash::findMcontext(w, 64, 0x400025f560, true, &proved) == 8 && proved, "console layout proved at word 8");
    uintptr_t s[64] {}; s[12 + OmniCrash::R_ADDR] = 0x1234560; s[12 + OmniCrash::R_RSP] = 0x7000002000;
    CHECK(OmniCrash::findMcontext(s, 64, 0x1234560, true, &proved) == 12 && proved, "shifted layout found by the landmark");
    uintptr_t z[64] {};
    CHECK(OmniCrash::findMcontext(z, 64, 0x99, true, &proved) == -1, "no landmark: layout not claimed");
    CHECK(OmniCrash::findMcontext(z, 64, 0, false, &proved) == 8 && !proved, "non-fault signal: console layout assumed");
    // 2. frame walk over a made-up stack: 3 frames, then a frame pointer leaving the stack stops it
    alignas(16) static uintptr_t stack[64] {};
    lo = uintptr_t(stack); hi = uintptr_t(stack + 64); OmniCrash::readableOverride = testReadable;
    stack[10] = uintptr_t(&stack[20]); stack[11] = 0x1111;
    stack[20] = uintptr_t(&stack[30]); stack[21] = 0x2222;
    stack[30] = 0x10;                  stack[31] = 0x3333;   // next frame pointer is bogus: walk ends after this one
    uintptr_t frames[32];
    int n = OmniCrash::walkFrames(0xabc, uintptr_t(&stack[10]), uintptr_t(&stack[0]), frames, 32);
    CHECK(n == 4 && frames[0] == 0xabc && frames[1] == 0x1111 && frames[2] == 0x2222 && frames[3] == 0x3333, "frame-pointer walk: rip + 3 return addresses");
    n = OmniCrash::walkFrames(0xabc, 0x8, uintptr_t(&stack[0]), frames, 32);
    CHECK(n == 1, "bad rbp: only rip");
    n = OmniCrash::walkFrames(0xabc, uintptr_t(&stack[10]), uintptr_t(&stack[0]), frames, 2);
    CHECK(n == 2, "frame limit honoured");
}

static void reportTest()
{
    unlink("/tmp/omni-crash-hosttest-crash.log");
    // 3. report() on a synthetic console context: registers, frames, memory dumps, no allocation
    unlink(OMNI_CRASH_LOG_PATH);
    OmniCrash::bootLog = -1; OmniCrash::crashLog = -1; OmniCrash::install(reinterpret_cast<const void*>(&anchorFunction), "hosttest");
    static uintptr_t mem[256]; lo = uintptr_t(mem); hi = uintptr_t(mem + 256);   // stack and block live inside mem
    uintptr_t* st = mem + 100; uintptr_t* bl = mem + 20;
    for (int i = 0; i < 16; ++i) bl[i] = 0xb10c000000 + i;
    st[0] = uintptr_t(&st[8]); st[1] = uintptr_t(&anchorFunction) + 3;
    st[8] = 0; st[9] = uintptr_t(&anchorFunction) + 7;
    OmniCrash::readableOverride = testReadable;
    uintptr_t ctx[80] {};
    uintptr_t* r = ctx + 8;
    r[OmniCrash::R_ADDR] = 0x400025f560; r[OmniCrash::R_RIP] = uintptr_t(&anchorFunction) + 1;
    r[OmniCrash::R_RSP] = uintptr_t(st) - 64; r[OmniCrash::R_RBP] = uintptr_t(st); r[OmniCrash::R_RSI] = uintptr_t(bl + 4);
    r[OmniCrash::R_RAX] = 0x24db3e0; r[OmniCrash::R_R14] = uintptr_t(bl + 8);
    siginfo_t info {}; info.si_signo = SIGSEGV; info.si_code = 1; info.si_addr = reinterpret_cast<void*>(0x400025f560);
    allocations = 0; counting = 1;
    OmniCrash::report(SIGSEGV, &info, ctx);
    counting = 0;
    std::string log = readLog();
    CHECK(allocations == 0, "report() allocates nothing");
    CHECK(log.find("OMNI_CRASH_V2 hosttest") != std::string::npos, "install line in the log file");
    CHECK(log.find("FATAL signal/address/address-minus-image-base: 0x000000000000000b 0x000000400025f560") != std::string::npos, "first FATAL line with signal and si_addr");
    CHECK(log.find("layout=proved") != std::string::npos, "layout proved");
    CHECK(log.find("rax=0x00000000024db3e0") != std::string::npos, "register values");
    CHECK(log.find("FATAL frame 2") != std::string::npos && log.find("FATAL frame 3") == std::string::npos, "rip + 2 frames");
    CHECK(log.find("FATAL memory rsi") != std::string::npos && log.find("0x000000b10c000000") != std::string::npos, "memory around rsi");
    CHECK(log.find("FATAL memory r14") != std::string::npos, "memory around r14");
    CHECK(log.find("FATAL end of report") != std::string::npos, "report completes");
    { std::string c; FILE* f = fopen("/tmp/omni-crash-hosttest-crash.log", "r"); if (f) { char b[8192]; size_t n; while ((n = fread(b, 1, sizeof b, f)) > 0) c.append(b, n); fclose(f); }
      CHECK(c.find("FATAL end of report") != std::string::npos, "report also in crash.log"); }
    OmniCrash::readableOverride = nullptr;
}

static int childDies(void (*body)(), int* status)
{
    pid_t p = fork();
    if (p == 0) { body(); _exit(0); }
    waitpid(p, status, 0); return p;
}
static void realSegv()
{
    unlink(OMNI_CRASH_LOG_PATH);
    OmniCrash::bootLog = -1; OmniCrash::crashLog = -1; OmniCrash::install(reinterpret_cast<const void*>(&anchorFunction), "segv");
    volatile uintptr_t* bad = reinterpret_cast<volatile uintptr_t*>(0x400025f560);
    (void)*bad;
}
static void webkitLike(int sig, siginfo_t* info, void* ctx);
static struct sigaction previous;
static void webkitLike(int sig, siginfo_t* info, void* ctx) { if (previous.sa_flags & SA_SIGINFO) previous.sa_sigaction(sig, info, ctx); }
static void chained()
{
    unlink(OMNI_CRASH_LOG_PATH);
    OmniCrash::bootLog = -1; OmniCrash::crashLog = -1; OmniCrash::install(reinterpret_cast<const void*>(&anchorFunction), "chained");
    struct sigaction a {}; a.sa_sigaction = webkitLike; a.sa_flags = SA_SIGINFO; sigemptyset(&a.sa_mask);
    sigaction(SIGSEGV, &a, &previous);   // like WTF's handler installed after Omni's: it keeps ours as the old action
    alarm(5);
    volatile int* bad = reinterpret_cast<volatile int*>(0x10);
    (void)*bad;
}
static void ownedFirst()
{
    unlink(OMNI_CRASH_LOG_PATH);
    struct sigaction a {}; a.sa_handler = [](int) { _exit(42); }; sigemptyset(&a.sa_mask);
    sigaction(SIGSEGV, &a, nullptr);
    OmniCrash::bootLog = -1; OmniCrash::crashLog = -1; OmniCrash::install(reinterpret_cast<const void*>(&anchorFunction), "owned");
    volatile int* bad = reinterpret_cast<volatile int*>(0x10);
    (void)*bad;
}
static void aborts()
{
    unlink(OMNI_CRASH_LOG_PATH);
    OmniCrash::bootLog = -1; OmniCrash::crashLog = -1; OmniCrash::install(reinterpret_cast<const void*>(&anchorFunction), "abort");
    abort();
}

int main()
{
    unitTests();
    reportTest();
    int st = 0;
    childDies(realSegv, &st); std::string log = readLog();
    CHECK(WIFSIGNALED(st) && WTERMSIG(st) == SIGSEGV, "real SIGSEGV: reported, then dies of SIGSEGV as before");
    CHECK(log.find("FATAL signal/address/address-minus-image-base: 0x000000000000000b 0x000000400025f560") != std::string::npos, "real SIGSEGV: FATAL line in boot.log");
    CHECK(log.find("FATAL end of report") != std::string::npos, "real SIGSEGV: report completes");
    childDies(chained, &st); log = readLog();
    CHECK(WIFSIGNALED(st) && WTERMSIG(st) == SIGSEGV, "chained through a later handler: dies of SIGSEGV, no loop");
    CHECK(log.find("FATAL signal") != std::string::npos, "chained: reported");
    childDies(ownedFirst, &st); log = readLog();
    CHECK(WIFEXITED(st) && WEXITSTATUS(st) == 42, "an existing SIGSEGV handler is left alone");
    CHECK(log.find("left to their owners: 11") != std::string::npos, "left-alone handler noted");
    childDies(aborts, &st); log = readLog();
    CHECK(WIFEXITED(st) && WEXITSTATUS(st) == 128 + SIGABRT, "SIGABRT keeps the V1 behaviour (_exit 134)");
    CHECK(log.find("FATAL signal/address/address-minus-image-base: 0x0000000000000006") != std::string::npos, "SIGABRT reported");
    printf("%s: %d failure(s)\n", failures ? "CRASH HOSTTEST FAIL" : "CRASH HOSTTEST PASS", failures);
    return failures ? 1 : 0;
}
