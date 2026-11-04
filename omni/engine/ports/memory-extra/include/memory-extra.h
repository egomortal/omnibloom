/* Omni Engine: C API of the "memory-extra" VSS shim (used by libpas and
 * WTF/wtf/playstation/OSAllocatorPlayStation.cpp). See memory-extra/vss.h for
 * the C++ API. SPDX-License-Identifier: BSD-2-Clause
 *
 * PS5 (console-measured 2026-10-19, tools/vdec-probe/diag/vsstest.c): an
 * anonymous mmap(PROT_NONE) "reservation" is charged in full against the
 * process's flexible memory budget (448 MiB for Omni's UI process) although it
 * holds no memory, and sceKernelAvailableFlexibleMemorySize() does not show it.
 * WebKit's reservations (~164 MiB) used the budget up: thread stacks then failed
 * (pthread_create EAGAIN, Omni's crashes since v29) and the hardware decoder's
 * codec module could not load (rtld load_prx ENOMEM -> videodec2 0x811d0200).
 * sceKernelReserveVirtualRange() reserves address space at no cost; committing
 * inside it with a fixed mapping costs only what is committed; re-reserving over
 * a committed range gives the memory back (pages read as zero afterwards). */
#ifndef OMNI_MEMORY_EXTRA_H
#define OMNI_MEMORY_EXTRA_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <sys/mman.h>

#ifndef MAP_ANON
#define MAP_ANON MAP_ANONYMOUS
#endif

#ifdef __PROSPERO__
#ifdef __cplusplus
extern "C" {
#endif
int sceKernelReserveVirtualRange(void** addr, size_t len, int flags, size_t alignment);
int sceKernelVirtualQuery(const void* addr, int flags, void* info, size_t infoSize);
#ifdef __cplusplus
}
#endif
#define OMNI_VSS_FIXED 0x10
#define OMNI_VSS_PAGE ((size_t)0x4000)

/* SceKernelVirtualQueryInfo (72 bytes on the console). */
typedef struct {
    void* start;
    void* end;
    int64_t offset;
    int32_t protection;
    int32_t memoryType;
    uint8_t flags; /* bit0 flexible, bit1 direct, bit2 stack, bit3 pooled, bit4 committed */
    char name[32];
} omni_vss_query_info;

/* Calls fn(start, length, mapped) for each piece of [addr, addr+bytes): mapped
 * is true where memory is already mapped (flexible/direct, e.g. committed pages
 * or a fallback mmap reservation) and false where only a cost-free reservation
 * exists. Returns false if fn fails or the range cannot be inspected. */
static inline bool omni_vss_each(void* addr, size_t bytes, bool (*fn)(uintptr_t, size_t, bool, int), int arg)
{
    uintptr_t at = (uintptr_t)addr, end = at + bytes;
    while (at < end) {
        omni_vss_query_info q;
        memset(&q, 0, sizeof q);
        if (sceKernelVirtualQuery((const void*)at, 0, &q, sizeof q))
            return false;
        uintptr_t pieceEnd = (uintptr_t)q.end;
        if (pieceEnd <= at)
            return false;
        if (pieceEnd > end)
            pieceEnd = end;
        if (!fn(at, pieceEnd - at, (q.flags & 0x03) != 0, arg))
            return false;
        at = pieceEnd;
    }
    return true;
}

static inline bool omni_vss_apply_prot(uintptr_t at, size_t n, bool mapped, int prot)
{
    if (mapped)
        return !mprotect((void*)at, n, prot);
    if (prot == PROT_NONE)
        return true; /* already an inaccessible reservation */
    /* Commit: fixed anonymous mapping inside the reservation (zero-filled). */
    return mmap((void*)at, n, prot, MAP_FIXED | MAP_PRIVATE | MAP_ANON, -1, 0) == (void*)at;
}
#endif /* __PROSPERO__ */

static inline void* memory_extra_vss_reserve(size_t bytes, size_t alignment)
{
#ifdef __PROSPERO__
    {
        size_t align = OMNI_VSS_PAGE;
        while (align < alignment)
            align <<= 1;
        void* p = NULL;
        size_t len = (bytes + OMNI_VSS_PAGE - 1) & ~(OMNI_VSS_PAGE - 1);
        if (!sceKernelReserveVirtualRange(&p, len, 0, align) && p && !((uintptr_t)p & (alignment ? alignment - 1 : 0)))
            return p;
        if (p)
            munmap(p, len);
        /* Fall through to the original (budget-costly) path. */
    }
#endif
    if (!alignment) {
        void* p = mmap(NULL, bytes, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
        return p == MAP_FAILED ? NULL : p;
    }
    size_t total = bytes + alignment;
    void* raw = mmap(NULL, total, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
    if (raw == MAP_FAILED)
        return NULL;
    uintptr_t start = (uintptr_t)raw;
    uintptr_t aligned = (start + alignment - 1) & ~(uintptr_t)(alignment - 1);
    size_t head = aligned - start, tail = total - head - bytes;
    if (head)
        munmap(raw, head);
    if (tail)
        munmap((void*)(aligned + bytes), tail);
    return (void*)aligned;
}

static inline bool memory_extra_vss_commit(void* addr, size_t bytes, bool writable, int usage)
{
    (void)usage;
    int prot = PROT_READ | (writable ? PROT_WRITE : 0);
#ifdef __PROSPERO__
    /* Already-committed pieces keep their contents (mprotect), reserved pieces get
     * fresh zeroed memory - the same result the original mprotect-only path gave. */
    return omni_vss_each(addr, bytes, omni_vss_apply_prot, prot);
#else
    return !mprotect(addr, bytes, prot);
#endif
}

static inline bool memory_extra_vss_decommit(void* addr, size_t bytes)
{
#ifdef __PROSPERO__
    {
        void* p = addr;
        if (!sceKernelReserveVirtualRange(&p, bytes, OMNI_VSS_FIXED, 0) && p == addr)
            return true; /* memory returned to the budget, range stays reserved */
    }
#endif
    return mmap(addr, bytes, PROT_NONE, MAP_FIXED | MAP_PRIVATE | MAP_ANON, -1, 0) != MAP_FAILED;
}

static inline bool memory_extra_vss_release(void* addr, size_t bytes)
{
    return !munmap(addr, bytes);
}

static inline bool memory_extra_vss_protect(void* addr, size_t bytes, bool readable, bool writable, int usage)
{
    (void)usage;
    int prot = (readable ? PROT_READ : 0) | (writable ? PROT_WRITE : 0);
#ifdef __PROSPERO__
    return omni_vss_each(addr, bytes, omni_vss_apply_prot, prot ? prot : PROT_NONE);
#else
    return !mprotect(addr, bytes, prot ? prot : PROT_NONE);
#endif
}
#endif
