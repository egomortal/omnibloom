// Minimal fatal-signal diagnostics: no allocation or symbol lookup in handler.
// OMNI_CRASH_V2 (omni-jit2, 2026-11-04): also SIGSEGV/SIGBUS/SIGFPE (only when nobody owns them yet, so WebKit's
// own handlers, installed later, chain to this one), every line also appended to /data/omni/native/boot.log with
// write()+fsync() (no stdio, no malloc in the handler), the full register set decoded from the console's machine
// context (uc_mcontext at byte 64, FreeBSD amd64 order; checked against mc_addr == si_addr), up to 32 frames by the
// frame-pointer chain, 64 bytes around every register that points at readable memory, the raw context words, and
// the load base (dladdr, else the code region from sceKernelVirtualQuery) plus the absolute address of one anchor
// function, so a crash can be symbolised offline even when dladdr fails (the title: "image base=0").
#pragma once
#include <signal.h>
#include <unistd.h>
#include <stdint.h>
#include <dlfcn.h>
#include <stdio.h>
#include <fcntl.h>
#include <pthread.h>
// OMNI_CRASH_STACK_V1: end of the code, defined by the linker (weak: 0 if absent).
extern "C" __attribute__((weak)) char etext;

#ifndef OMNI_CRASH_LOG_PATH
#define OMNI_CRASH_LOG_PATH "/data/omni/native/boot.log"
#endif
#ifndef OMNI_CRASH_LOG2_PATH
#define OMNI_CRASH_LOG2_PATH "/data/omni/native/crash.log"   // only crash reports: never truncated or rotated by anyone
#endif
#ifndef OMNI_CRASH_MCONTEXT_WORD
#define OMNI_CRASH_MCONTEXT_WORD 8   // the console's ucontext_t: uc_mcontext at byte 64 (ps5platform/context.h, PROBE.md)
#endif

namespace OmniCrash {
static unsigned char alternateStack[64 * 1024];
static int output = -1;
static int bootLog = -1;   // OMNI_CRASH_V2
static int crashLog = -1;  // OMNI_CRASH_V2
static uintptr_t imageBase;
static uintptr_t codeStart, codeEnd; // OMNI_CRASH_STACK_V1: executable segment of Omni
static uintptr_t anchorAddress;      // OMNI_CRASH_V2: runtime address of the symbol given to install()
static const char* role = "process";
static volatile sig_atomic_t reporting = 0;
// sceKernelVirtualQuery, looked up at install (no declaration that could clash with SDK headers).
static int (*virtualQuery)(const void*, int, void*, size_t) = nullptr;
// Host tests only: decides readability when sceKernelVirtualQuery is absent.
static bool (*readableOverride)(uintptr_t, size_t) = nullptr;
// Optional last-chance cleanup before the process dies (UI process: release the
// hardware video decoder so a dead Omni cannot take the console down). Runs once.
// OMNI_CRASH_V2: not for SIGSEGV/SIGBUS/SIGFPE (a corrupted heap could deadlock it; before V2 those signals had no
// handler at all, so their behaviour is unchanged apart from the report).
static void (*volatile beforeExit)() = nullptr;

struct Region { uintptr_t start, end, offset; int prot, type; unsigned char flags; char name[32]; };
enum { R_ONSTACK, R_RDI, R_RSI, R_RDX, R_RCX, R_R8, R_R9, R_RAX, R_RBX, R_RBP, R_R10, R_R11, R_R12, R_R13, R_R14,
       R_R15, R_TRAPNO, R_ADDR, R_FLAGS, R_ERR, R_RIP, R_CS, R_RFLAGS, R_RSP, R_SS, R_COUNT };
static const char* const registerNames[R_COUNT] = { "onstack", "rdi", "rsi", "rdx", "rcx", "r8", "r9", "rax", "rbx",
    "rbp", "r10", "r11", "r12", "r13", "r14", "r15", "trapno", "addr", "flags", "err", "rip", "cs", "rflags", "rsp", "ss" };

// ---- async-signal-safe output -----------------------------------------------------------------------------------
struct Line {
    char text[720]; size_t used = 0;
    void put(char c) { if (used < sizeof(text) - 1) text[used++] = c; }
    void str(const char* s) { while (s && *s) put(*s++); }
    void hex(uintptr_t v) { str("0x"); for (int shift = sizeof(v) * 8 - 4; shift >= 0; shift -= 4) put("0123456789abcdef"[(v >> shift) & 15]); put(' '); }
    void dec(long v) { char d[24]; int n = 0; unsigned long u = v < 0 ? (put('-'), (unsigned long)(-v)) : (unsigned long)v;
        do { d[n++] = char('0' + u % 10); u /= 10; } while (u && n < 23); while (n) put(d[--n]); put(' '); }
};
static void emit(Line& line)
{
    line.put('\n');
    if (output >= 0) (void)!write(output, line.text, line.used);
    if (bootLog >= 0) (void)!write(bootLog, line.text, line.used);
    if (crashLog >= 0) (void)!write(crashLog, line.text, line.used);
    line.used = 0;
}
static void syncLogs()
{
    if (bootLog >= 0) fsync(bootLog);
    if (crashLog >= 0) fsync(crashLog);
}
static bool readable(uintptr_t address, size_t bytes)
{
    if (address < 0x10000 || address + bytes < address) return false;
    if (readableOverride) return readableOverride(address, bytes);
    if (!virtualQuery) return false;
    Region region {};
    if (virtualQuery(reinterpret_cast<const void*>(address), 0, &region, sizeof(region))) return false;
    return region.start <= address && address + bytes <= region.end && (region.prot & 1);
}
static uintptr_t offsetOf(uintptr_t v) { return imageBase && v >= codeStart && v < codeEnd ? v - imageBase : 0; }

// ---- machine context ------------------------------------------------------------------------------------------
// Returns the word index of mc_onstack in the context, or -1. The console's layout first (FreeBSD amd64 mcontext 48
// bytes later than FreeBSD's), proved by mc_addr == si_addr for faults; else the first index where it holds.
static int findMcontext(const uintptr_t* words, int count, uintptr_t faultAddress, bool fault, bool* proved)
{
    *proved = false;
    const int preferred = OMNI_CRASH_MCONTEXT_WORD;
    if (!fault || !faultAddress) return preferred + R_COUNT <= count ? preferred : -1;
    if (preferred + R_COUNT <= count && words[preferred + R_ADDR] == faultAddress) { *proved = true; return preferred; }
    for (int i = 0; i + R_COUNT <= count; ++i)
        if (words[i + R_ADDR] == faultAddress && (words[i + R_RSP] & 7) == 0 && words[i + R_RSP]) { *proved = true; return i; }
    return -1;
}
static int walkFrames(uintptr_t rip, uintptr_t rbp, uintptr_t rsp, uintptr_t* frames, int max)
{
    int n = 0;
    if (rip && n < max) frames[n++] = rip;
    uintptr_t fp = rbp;
    while (n < max) {
        if (!fp || (fp & 7) || fp < rsp || fp - rsp > (uintptr_t(1) << 22) || !readable(fp, 16)) break;
        const uintptr_t next = reinterpret_cast<const uintptr_t*>(fp)[0];
        const uintptr_t ret = reinterpret_cast<const uintptr_t*>(fp)[1];
        if (!ret) break;
        frames[n++] = ret;
        if (next <= fp) break;
        fp = next;
    }
    return n;
}
// OMNI_CRASH_STACK_V1: heuristic backtrace (see patch-crash-stack.py); V2 starts at the decoded rsp when known.
static void stackScan(const void* context, uintptr_t knownSp)
{
#ifndef OMNI_CRASH_STACK_LOW
#define OMNI_CRASH_STACK_LOW 0x700000000
#define OMNI_CRASH_STACK_HIGH 0x7f0000000
#endif
    const uintptr_t stackLow = OMNI_CRASH_STACK_LOW, stackHigh = OMNI_CRASH_STACK_HIGH;
    if (!context || !codeStart) return;
    uintptr_t sp = knownSp;
    if (!sp) {
        const uintptr_t* words = static_cast<const uintptr_t*>(context);
        for (int i = 0; i < 160; ++i) {
            uintptr_t v = words[i];
            if (v >= stackLow && v < stackHigh && (!sp || v < sp)) sp = v;
        }
    }
    if (!sp) return;
    uintptr_t end = sp + 16 * 1024;
    while (end > sp && !readable(sp & ~uintptr_t(7), end - (sp & ~uintptr_t(7)))) end -= 4096;   // stay inside the stack
    Line line;
    line.str("FATAL stack scan from/to: "); line.hex(sp); line.hex(end); emit(line);
    int found = 0;
    line.str("FATAL stack (image offsets): ");
    for (uintptr_t at = sp & ~uintptr_t(7); at + 8 <= end && found < 48; at += 8) {
        uintptr_t v = *reinterpret_cast<const uintptr_t*>(at);
        if (v <= codeStart || v >= codeEnd) continue;
        line.hex(v - imageBase);
        if (++found % 8 == 0) { emit(line); line.str("FATAL stack (image offsets): "); }
    }
    if (found % 8) emit(line);
}
// Everything but the exit: separate so host tests can feed it a made-up context.
static void report(int signal, siginfo_t* info, void* context)
{
    Line line;
    const uintptr_t address = info ? reinterpret_cast<uintptr_t>(info->si_addr) : 0;
    line.str("FATAL signal/address/address-minus-image-base: ");
    line.hex(uintptr_t(signal)); line.hex(address); line.hex(imageBase && address >= imageBase ? address - imageBase : 0);
    line.str("pid="); line.dec(long(getpid())); line.str("code="); line.dec(info ? long(info->si_code) : 0);
    line.str("thread="); line.hex(uintptr_t(pthread_self())); line.str(role); emit(line);
    line.str("FATAL load base="); line.hex(imageBase); line.str("code="); line.hex(codeStart); line.hex(codeEnd);
    line.str("anchor="); line.hex(anchorAddress); emit(line);
    syncLogs();
    const uintptr_t* words = static_cast<const uintptr_t*>(context);
    const bool fault = signal == SIGSEGV || signal == SIGBUS;
    bool proved = false;
    const int m = context ? findMcontext(words, 64, address, fault, &proved) : -1;
    uintptr_t rsp = 0;
    if (m >= 0) {
        const uintptr_t* r = words + m;
        rsp = r[R_RSP];
        line.str("FATAL rip="); line.hex(r[R_RIP]); line.str("rip-image-base="); line.hex(offsetOf(r[R_RIP]));
        line.str("err="); line.hex(r[R_ERR]); line.str("trapno="); line.hex(r[R_TRAPNO] & 0xffffffff);
        line.str(!proved ? "layout=assumed" : m == OMNI_CRASH_MCONTEXT_WORD ? "layout=proved" : "layout=landmark-only"); line.str(" word="); line.dec(m); emit(line);
        static const int order[] = { R_RAX, R_RBX, R_RCX, R_RDX, R_RSI, R_RDI, R_RBP, R_RSP, R_R8, R_R9, R_R10, R_R11, R_R12, R_R13, R_R14, R_R15, R_RFLAGS, R_ADDR };
        const int count = int(sizeof(order) / sizeof(order[0]));
        for (int k = 0; k < count; ++k) {
            if (k % 6 == 0) line.str("FATAL registers: ");
            line.str(registerNames[order[k]]); line.put('='); line.hex(r[order[k]]);
            if (k % 6 == 5 || k == count - 1) emit(line);
        }
        uintptr_t frames[32];
        const int n = walkFrames(r[R_RIP], r[R_RBP], rsp, frames, 32);
        line.str("FATAL frames (absolute, image offset):"); emit(line);
        for (int i = 0; i < n; ++i) {
            line.str("FATAL frame "); line.dec(i); line.hex(frames[i]); line.hex(offsetOf(frames[i])); emit(line);
        }
        syncLogs();
        // 64 bytes around every register that points at readable memory (the object, the freed block, the list node)
        static const int around[] = { R_RDI, R_RSI, R_RDX, R_RCX, R_R8, R_R9, R_RAX, R_RBX, R_R12, R_R13, R_R14, R_R15 };
        for (int reg : around) {
            const uintptr_t v = r[reg] & ~uintptr_t(7);
            if (v < 0x10000 || !readable(v - 32, 64)) continue;
            line.str("FATAL memory "); line.str(registerNames[reg]); line.put(' '); line.hex(r[reg]); line.str("from-32:");
            for (int w = 0; w < 8; ++w) line.hex(reinterpret_cast<const uintptr_t*>(v - 32)[w]);
            emit(line);
        }
    } else if (context) {
        line.str("FATAL registers: layout not found (no mc_addr == si_addr); raw context below"); emit(line);
    }
    if (context) {
        for (int row = 0; row < 5; ++row) {
            line.str("FATAL context words "); line.dec(row * 8); line.put(':');
            for (int w = 0; w < 8; ++w) line.hex(words[row * 8 + w]);
            emit(line);
        }
    }
    syncLogs();
    stackScan(context, rsp); // OMNI_CRASH_STACK_V1
    line.str("FATAL end of report"); emit(line);
    syncLogs();
}
static void fatal(int signal, siginfo_t* info, void* context)
{
    if (reporting) return;   // a fault inside the report: SA_RESETHAND already made the next one fatal
    reporting = 1;
    report(signal, info, context);
    if (signal == SIGSEGV || signal == SIGBUS || signal == SIGFPE) {
        // OMNI_CRASH_V2: default action again, then let it happen as it would have without this handler (a fault
        // re-executes and the system records it as before; a sent signal is raised again).
        struct sigaction action {};
        action.sa_handler = SIG_DFL; sigemptyset(&action.sa_mask);
        sigaction(signal, &action, nullptr);
        const long code = info ? long(info->si_code) : 0;
        if (code <= 0 || code >= 0x10000) raise(signal);
        return;
    }
    if (void (*cleanup)() = beforeExit) { beforeExit = nullptr; cleanup(); }
    _exit(128 + signal);
}
static void install(const void* symbol, const char* who = nullptr)
{
    if (who) role = who;
    output = fileno(stderr);   // the title's stderr is not fd 2 (V1's FATAL lines reached the process log this way)
    if (bootLog < 0) bootLog = open(OMNI_CRASH_LOG_PATH, O_WRONLY | O_APPEND | O_CREAT | O_CLOEXEC, 0666);   // OMNI_CRASH_V2: raw open, never fopen
    if (crashLog < 0) crashLog = open(OMNI_CRASH_LOG2_PATH, O_WRONLY | O_APPEND | O_CREAT | O_CLOEXEC, 0666);
    anchorAddress = reinterpret_cast<uintptr_t>(symbol);
    Dl_info image {};
    if (dladdr(symbol, &image)) imageBase = reinterpret_cast<uintptr_t>(image.dli_fbase);
    // OMNI_CRASH_STACK_V1: code range = image base .. linker's etext (includes rodata on lld;
    // the extra words are harmless noise). Falls back to 256 MiB if etext is absent.
    if (uintptr_t textEnd = reinterpret_cast<uintptr_t>(&etext); imageBase && textEnd > imageBase) {
        codeStart = imageBase; codeEnd = textEnd;
    }
    if (!codeStart && imageBase) { codeStart = imageBase; codeEnd = imageBase + (256u << 20); }
    virtualQuery = reinterpret_cast<int (*)(const void*, int, void*, size_t)>(dlsym(RTLD_DEFAULT, "sceKernelVirtualQuery"));
    const char* how = imageBase ? "dladdr" : "none";
    if (!imageBase && virtualQuery) {   // OMNI_CRASH_V2: the title (dladdr finds nothing): the code region holding the anchor
        Region region {};
        if (!virtualQuery(symbol, 0, &region, sizeof(region)) && region.start <= anchorAddress && anchorAddress < region.end) {
            imageBase = codeStart = region.start; codeEnd = region.end; how = "code region";
        }
    }
    char text[320];
    int n = snprintf(text, sizeof(text), "crash diagnostics: code range %p-%p\n", reinterpret_cast<void*>(codeStart), reinterpret_cast<void*>(codeEnd));
    if (n > 0) (void)!write(output, text, size_t(n) < sizeof(text) ? size_t(n) : sizeof(text) - 1);
    n = snprintf(text, sizeof(text), "crash diagnostics: image base=%p\n", reinterpret_cast<void*>(imageBase));
    if (n > 0) (void)!write(output, text, size_t(n) < sizeof(text) ? size_t(n) : sizeof(text) - 1);
    stack_t stack {};
    stack.ss_sp = alternateStack; stack.ss_size = sizeof(alternateStack);
    sigaltstack(&stack, nullptr);
    struct sigaction action {};
    sigemptyset(&action.sa_mask);
    action.sa_sigaction = fatal;
    action.sa_flags = SA_SIGINFO | SA_ONSTACK | SA_RESETHAND;
    for (int signal : { SIGILL, SIGABRT, SIGTRAP }) sigaction(signal, &action, nullptr);
    // OMNI_CRASH_V2: memory faults too, but only where nobody has a handler yet (WebKit's, installed later, keep
    // this one as their previous action and call it for faults they do not handle).
    char owned[64] = ""; size_t o = 0;
    for (int signal : { SIGSEGV, SIGBUS, SIGFPE }) {
        struct sigaction old {};
        if (sigaction(signal, nullptr, &old) == 0 && !(old.sa_flags & SA_SIGINFO) && (old.sa_handler == SIG_DFL))
            sigaction(signal, &action, nullptr);
        else if (o + 4 < sizeof(owned)) o += size_t(snprintf(owned + o, sizeof(owned) - o, " %d", signal));
    }
    n = snprintf(text, sizeof(text), "crash diagnostics: OMNI_CRASH_V2 %s pid=%d base=%p (%s) anchor=%p etext=%p log=%s fd=%d%s%s\n",
        role, int(getpid()), reinterpret_cast<void*>(imageBase), how, reinterpret_cast<void*>(anchorAddress),
        reinterpret_cast<void*>(&etext), OMNI_CRASH_LOG_PATH, bootLog, o ? "; left to their owners:" : "", owned);
    if (n > 0) {
        const size_t len = size_t(n) < sizeof(text) ? size_t(n) : sizeof(text) - 1;
        (void)!write(output, text, len);
        if (bootLog >= 0) { (void)!write(bootLog, text, len); fsync(bootLog); }
        if (crashLog >= 0) { (void)!write(crashLog, text, len); fsync(crashLog); }
    }
}
}
