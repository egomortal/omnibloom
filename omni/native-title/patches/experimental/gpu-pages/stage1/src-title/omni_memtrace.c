/* OMNI_MEMTRACE_V1 (2026-11-18, test only): who maps the title's direct memory.
 *
 * The title's memory map (OMNI_MEMMAP_V1/V2) showed ~300 MB of GPU-visible direct memory at idle that appears only with
 * the GPU present on, and the present and GPU video logs account for only ~45 MB of it. This file wraps the three
 * direct-memory calls the title imports (MapNamedDirectMemory is not imported: wrapping it would add an import) at link time (lld --wrap; __real_X is the unchanged system import X), so the static SDL, the pinned
 * RADV archive and the title's own code all pass through here. With /data/omni/memmap.flag each call logs one line:
 *   OMNI MEMTRACE: <call> len <KB> KB align <a> type/prot <t> -> <result> phys <p> va <v> caller <ra> (+<offset>)
 * <offset> is the return address minus the title image base: symbolise it offline against the build's llvm-pie.elf.
 * Without the flag: one access() on the first call, then a single branch per call. No allocation here. */
#define _GNU_SOURCE 1   /* dladdr / Dl_info on glibc host checks; the PS5 SDK has them anyway */
#include <dlfcn.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/types.h>
#include <unistd.h>

int __real_sceKernelAllocateMainDirectMemory(size_t len, size_t align, int type, off_t *phys);
int __real_sceKernelAllocateDirectMemory(off_t start, off_t end, size_t len, size_t align, int type, off_t *phys);
int __real_sceKernelMapDirectMemory(void **addr, size_t len, int prot, int flags, off_t phys, size_t align);

static int omni_memtrace_state; /* 0 unknown, 1 on, -1 off */
static uintptr_t omni_memtrace_base;

static int omni_memtrace_on(void)
{
    if (omni_memtrace_state == 0) {
        omni_memtrace_state = access("/data/omni/memmap.flag", F_OK) == 0 ? 1 : -1;
        Dl_info info;
        if (dladdr((void *)&omni_memtrace_on, &info) && info.dli_fbase) omni_memtrace_base = (uintptr_t)info.dli_fbase;
    }
    return omni_memtrace_state > 0;
}

static void omni_memtrace_log(const char *call, size_t len, size_t align, int typeOrProt, int ret, long long phys,
                              void *va, void *ra)
{
    uintptr_t r = (uintptr_t)ra;
    fprintf(stderr, "OMNI MEMTRACE: %s len %zu KB align %#zx type/prot %#x -> %#x phys %#llx va %p caller %p (+%#lx)\n",
            call, len >> 10, align, (unsigned)typeOrProt, (unsigned)ret, phys, va, ra,
            (unsigned long)(omni_memtrace_base && r > omni_memtrace_base ? r - omni_memtrace_base : 0));
}

int __wrap_sceKernelAllocateMainDirectMemory(size_t len, size_t align, int type, off_t *phys)
{
    int ret = __real_sceKernelAllocateMainDirectMemory(len, align, type, phys);
    if (omni_memtrace_on()) omni_memtrace_log("allocMain", len, align, type, ret, phys ? (long long)*phys : -1, NULL, __builtin_return_address(0));
    return ret;
}

int __wrap_sceKernelAllocateDirectMemory(off_t start, off_t end, size_t len, size_t align, int type, off_t *phys)
{
    int ret = __real_sceKernelAllocateDirectMemory(start, end, len, align, type, phys);
    if (omni_memtrace_on()) omni_memtrace_log("alloc", len, align, type, ret, phys ? (long long)*phys : -1, NULL, __builtin_return_address(0));
    return ret;
}

int __wrap_sceKernelMapDirectMemory(void **addr, size_t len, int prot, int flags, off_t phys, size_t align)
{
    int ret = __real_sceKernelMapDirectMemory(addr, len, prot, flags, phys, align);
    if (omni_memtrace_on()) omni_memtrace_log("map", len, align, prot, ret, (long long)phys, addr ? *addr : NULL, __builtin_return_address(0));
    return ret;
}
