// Minimal fatal-signal diagnostics: no allocation or symbol lookup in handler.
#pragma once
#include <signal.h>
#include <unistd.h>
#include <stdint.h>
#include <dlfcn.h>
#include <stdio.h>
// OMNI_CRASH_STACK_V1: end of the code, defined by the linker (weak: 0 if absent).
extern "C" __attribute__((weak)) char etext;

namespace OmniCrash {
static unsigned char alternateStack[64 * 1024];
static int output = -1;
static uintptr_t imageBase;
static uintptr_t codeStart, codeEnd; // OMNI_CRASH_STACK_V1: executable segment of Omni
// sceKernelVirtualQuery, looked up at install (no declaration that could clash with SDK headers).
static int (*virtualQuery)(const void*, int, void*, size_t) = nullptr;
// Optional last-chance cleanup before the process dies (UI process: release the
// hardware video decoder so a dead Omni cannot take the console down). Runs once.
static void (*volatile beforeExit)() = nullptr;
static char* hexadecimal(char* p, uintptr_t value)
{
    *p++ = '0'; *p++ = 'x';
    for (int shift = sizeof(value) * 8 - 4; shift >= 0; shift -= 4)
        *p++ = "0123456789abcdef"[(value >> shift) & 15];
    *p++ = ' '; return p;
}
// OMNI_CRASH_STACK_V1: heuristic backtrace (see patch-crash-stack.py).
static void stackScan(const void* context)
{
#ifndef OMNI_CRASH_STACK_LOW
#define OMNI_CRASH_STACK_LOW 0x700000000
#define OMNI_CRASH_STACK_HIGH 0x7f0000000
#endif
    const uintptr_t stackLow = OMNI_CRASH_STACK_LOW, stackHigh = OMNI_CRASH_STACK_HIGH;
    if (!context || !imageBase || !codeStart) return;
    // Lowest stack-window value in the saved registers ~ the faulting thread's stack pointer.
    uintptr_t sp = 0;
    const uintptr_t* words = static_cast<const uintptr_t*>(context);
    for (int i = 0; i < 160; ++i) {
        uintptr_t v = words[i];
        if (v >= stackLow && v < stackHigh && (!sp || v < sp)) sp = v;
    }
    if (!sp) return;
    uintptr_t end = sp + 16 * 1024;
    if (virtualQuery) {
        struct { uintptr_t start, end, offset; int prot, type; unsigned char flags; char name[32]; } region {};
        if (!virtualQuery(reinterpret_cast<const void*>(sp), 0, &region, sizeof(region)) && region.end > sp && region.end < end)
            end = region.end;
    }
    char line[512];
    char* p = line;
    const char scanLabel[] = "FATAL stack scan from/to: ";
    for (char c : scanLabel) if (c) *p++ = c;
    p = hexadecimal(p, sp);
    p = hexadecimal(p, end);
    *p++ = '\n';
    if (output >= 0) write(output, line, p - line);
    p = line;
    const char label[] = "FATAL stack (image offsets): ";
    for (char c : label) if (c) *p++ = c;
    int found = 0;
    for (uintptr_t at = sp & ~uintptr_t(7); at + 8 <= end && found < 48; at += 8) {
        uintptr_t v = *reinterpret_cast<const uintptr_t*>(at);
        if (v <= codeStart || v >= codeEnd) continue;
        p = hexadecimal(p, v - imageBase);
        if (++found % 8 == 0) {
            *p++ = '\n';
            if (output >= 0) write(output, line, p - line);
            p = line;
            for (char c : label) if (c) *p++ = c;
        }
    }
    if (found % 8) { *p++ = '\n'; if (output >= 0) write(output, line, p - line); }
}
static void fatal(int signal, siginfo_t* info, void* context)
{
    char line[256];
    char* p = line;
    const char label[] = "FATAL signal/address/address-minus-image-base: ";
    for (char c : label) if (c) *p++ = c;
    // The SDK ucontext layout does not match this firmware. Do not read it.
    uintptr_t address = reinterpret_cast<uintptr_t>(info->si_addr);
    p = hexadecimal(p, signal);
    p = hexadecimal(p, address);
    p = hexadecimal(p, imageBase && address >= imageBase ? address - imageBase : 0);
    *p++ = '\n';
    if (output >= 0) write(output, line, p - line);
    stackScan(context); // OMNI_CRASH_STACK_V1
    if (void (*cleanup)() = beforeExit) { beforeExit = nullptr; cleanup(); }
    _exit(128 + signal);
}
static void install(const void* symbol)
{
    output = fileno(stderr);
    Dl_info image {};
    if (dladdr(symbol, &image)) imageBase = reinterpret_cast<uintptr_t>(image.dli_fbase);
    // OMNI_CRASH_STACK_V1: code range = image base .. linker's etext (includes rodata on lld;
    // the extra words are harmless noise). Falls back to 256 MiB if etext is absent.
    if (uintptr_t textEnd = reinterpret_cast<uintptr_t>(&etext); imageBase && textEnd > imageBase) {
        codeStart = imageBase; codeEnd = textEnd;
    }
    if (!codeStart && imageBase) { codeStart = imageBase; codeEnd = imageBase + (256u << 20); }
    virtualQuery = reinterpret_cast<int (*)(const void*, int, void*, size_t)>(dlsym(RTLD_DEFAULT, "sceKernelVirtualQuery"));
    fprintf(stderr, "crash diagnostics: code range %p-%p\n", reinterpret_cast<void*>(codeStart), reinterpret_cast<void*>(codeEnd));
    fprintf(stderr, "crash diagnostics: image base=%p\n", reinterpret_cast<void*>(imageBase));
    fflush(stderr); fsync(output);
    stack_t stack {};
    stack.ss_sp = alternateStack; stack.ss_size = sizeof(alternateStack);
    sigaltstack(&stack, nullptr);
    struct sigaction action {};
    sigemptyset(&action.sa_mask);
    action.sa_sigaction = fatal;
    action.sa_flags = SA_SIGINFO | SA_ONSTACK | SA_RESETHAND;
    // Leave WebKit's memory-fault machinery and normal termination untouched.
    for (int signal : { SIGILL, SIGABRT, SIGTRAP }) sigaction(signal, &action, nullptr);
}
}
