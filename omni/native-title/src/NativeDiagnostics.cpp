// Native-title diagnostics (OMNI_NATIVE_DIAG_V1), included by NativeLauncherState.cpp.
// Logs, without changing behaviour:
//   * every dup() through __wrap_dup: what the descriptor is (fstat type, F_GETFD/F_GETFL)
//     and the caller's stack, as image offsets for addr2line on llvm-pie.elf;
//   * a failing C++ allocation (std::new_handler, which runs inside operator new, so the
//     stack shows the allocating caller) with configured/available flexible memory.
// Offsets are relative to __ehdr_start (the ELF header of this PIE), matching llvm-pie.elf.
// SPDX-License-Identifier: GPL-3.0-or-later
#include <atomic>
#include <cstddef>
#include <errno.h>
#include <fcntl.h>
#include <new>
#include <stdint.h>
#include <stdio.h>
#include <sys/stat.h>
#include <unwind.h>

extern "C" char __ehdr_start __attribute__((weak));
extern "C" int32_t sceKernelAvailableFlexibleMemorySize(size_t*);
extern "C" int32_t sceKernelConfiguredFlexibleMemorySize(size_t*);

namespace {
struct OmniStack { uintptr_t pcs[24]; int count; };

_Unwind_Reason_Code omniStackStep(struct _Unwind_Context* context, void* argument)
{
    auto* stack = static_cast<OmniStack*>(argument);
    if (stack->count >= 24) return _URC_END_OF_STACK;
    uintptr_t pc = _Unwind_GetIP(context);
    if (!pc) return _URC_END_OF_STACK;
    stack->pcs[stack->count++] = pc;
    return _URC_NO_REASON;
}

void omniLogStack(const char* label)
{
    OmniStack stack {};
    _Unwind_Backtrace(omniStackStep, &stack);
    const uintptr_t base = reinterpret_cast<uintptr_t>(&__ehdr_start);
    char line[24 * 19 + 96];
    int used = snprintf(line, sizeof(line), "native diag: %s stack (offsets from %p):", label, reinterpret_cast<void*>(base));
    for (int i = 0; i < stack.count && used > 0 && used < static_cast<int>(sizeof(line)) - 20; ++i)
        used += snprintf(line + used, sizeof(line) - used, " %lx", static_cast<unsigned long>(base && stack.pcs[i] > base ? stack.pcs[i] - base : stack.pcs[i]));
    fprintf(stderr, "%s\n", line);
    fflush(stderr);
}

void omniLogFlexible(const char* label)
{
    size_t configured = 0, available = 0;
    int a = sceKernelConfiguredFlexibleMemorySize(&configured);
    int b = sceKernelAvailableFlexibleMemorySize(&available);
    fprintf(stderr, "native diag: %s flexible configured=%zu MiB (rc 0x%x) available=%zu MiB (rc 0x%x)\n",
        label, configured >> 20, a, available >> 20, b);
    fflush(stderr);
}

void omniNewHandler()
{
    static int reports = 0;
    if (reports++ < 3) {
        fprintf(stderr, "native diag: operator new failed (report %d)\n", reports);
        omniLogFlexible("at failed allocation");
        omniLogStack("failed allocation");
    }
    std::set_new_handler(nullptr); // operator new now throws std::bad_alloc as before
}
}

// Called by __wrap_dup before the duplication attempt.
static void omniNativeDiagDup(int fd)
{
    static int reports = 0;
    if (reports++ >= 6) return;
    struct stat info {};
    int saved = errno;
    int statResult = fstat(fd, &info);
    int fdFlags = fcntl(fd, F_GETFD);
    int flFlags = fcntl(fd, F_GETFL);
    const char* type = statResult ? "fstat-failed" : S_ISSOCK(info.st_mode) ? "socket" : S_ISREG(info.st_mode) ? "file"
        : S_ISFIFO(info.st_mode) ? "fifo" : S_ISCHR(info.st_mode) ? "chardev" : S_ISDIR(info.st_mode) ? "dir" : "other";
    fprintf(stderr, "native diag: dup(%d) type=%s mode=0%o F_GETFD=%d F_GETFL=0x%x (fstat errno %d)\n",
        fd, type, statResult ? 0 : static_cast<unsigned>(info.st_mode), fdFlags, flFlags, statResult ? errno : 0);
    omniLogStack("dup");
    errno = saved;
}

__attribute__((constructor)) static void omniInstallNativeDiagnostics()
{
    std::set_new_handler(omniNewHandler);
    omniLogFlexible("startup");
}

// OMNI_NATIVE_DIAG_V1: every C++ throw is logged with the exception type and the thrower's
// stack (first 8), then thrown unchanged. Linked with --wrap=__cxa_throw (build-native.py).
extern "C" [[noreturn]] void __real___cxa_throw(void*, void*, void (*)(void*));
extern "C" [[noreturn]] void __wrap___cxa_throw(void* exception, void* type, void (*destructor)(void*))
{
    static int reports = 0;
    if (reports++ < 8) {
        // std::type_info layout: vtable pointer, then the mangled name.
        const char* name = type ? *reinterpret_cast<const char* const*>(static_cast<char*>(type) + sizeof(void*)) : "?";
        fprintf(stderr, "native diag: C++ throw of %s (report %d)\n", name ? name : "?", reports);
        omniLogFlexible("at throw");
        omniLogStack("throw");
    }
    __real___cxa_throw(exception, type, destructor);
}

// OMNI_NATIVE_DIAG_V1: the title's C++ allocations otherwise bind to the system C++ runtime
// (libSceLibcInternal), whose failures ("bad allocation") our hooks above can't see. These
// definitions keep the same allocator (malloc/free) and only add logging: every allocation of
// 64 MiB or more (first 16), and any failure with its size, free flexible memory and the
// caller's stack. A failure then aborts, as the uncaught std::bad_alloc did.
#include <stdlib.h>
namespace {
std::atomic<int> omniBigAllocations { 0 };
void* omniNewImpl(size_t size, size_t alignment, bool nothrow)
{
    if (!size) size = 1;
    void* p = nullptr;
    if (alignment > alignof(std::max_align_t)) { if (posix_memalign(&p, alignment, size)) p = nullptr; }
    else p = malloc(size);
    if (size >= (64u << 20) && omniBigAllocations++ < 16) {
        fprintf(stderr, "native diag: large C++ allocation %zu bytes (%zu MiB) -> %p\n", size, size >> 20, p);
        omniLogStack("large allocation");
    }
    if (p || nothrow) return p;
    fprintf(stderr, "native diag: operator new(%zu bytes = %zu MiB, align %zu) failed, errno %d\n", size, size >> 20, alignment, errno);
    omniLogFlexible("at failed operator new");
    omniLogStack("failed operator new");
    abort();
}
}
void* operator new(size_t size) { return omniNewImpl(size, 0, false); }
void* operator new[](size_t size) { return omniNewImpl(size, 0, false); }
void* operator new(size_t size, const std::nothrow_t&) noexcept { return omniNewImpl(size, 0, true); }
void* operator new[](size_t size, const std::nothrow_t&) noexcept { return omniNewImpl(size, 0, true); }
void* operator new(size_t size, std::align_val_t a) { return omniNewImpl(size, static_cast<size_t>(a), false); }
void* operator new[](size_t size, std::align_val_t a) { return omniNewImpl(size, static_cast<size_t>(a), false); }
void* operator new(size_t size, std::align_val_t a, const std::nothrow_t&) noexcept { return omniNewImpl(size, static_cast<size_t>(a), true); }
void* operator new[](size_t size, std::align_val_t a, const std::nothrow_t&) noexcept { return omniNewImpl(size, static_cast<size_t>(a), true); }
void operator delete(void* p) noexcept { free(p); }
void operator delete[](void* p) noexcept { free(p); }
void operator delete(void* p, size_t) noexcept { free(p); }
void operator delete[](void* p, size_t) noexcept { free(p); }
void operator delete(void* p, std::align_val_t) noexcept { free(p); }
void operator delete[](void* p, std::align_val_t) noexcept { free(p); }
void operator delete(void* p, size_t, std::align_val_t) noexcept { free(p); }
void operator delete[](void* p, size_t, std::align_val_t) noexcept { free(p); }
void operator delete(void* p, const std::nothrow_t&) noexcept { free(p); }
void operator delete[](void* p, const std::nothrow_t&) noexcept { free(p); }
