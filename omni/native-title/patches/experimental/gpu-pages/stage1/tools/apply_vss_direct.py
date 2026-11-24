#!/usr/bin/env python3
"""OMNI_VSS_DIRECT_V1 (2026-11-22): single-process plan Phase 1 - back the title's heap commits with DIRECT memory
(0 kernel page tables) instead of flexible mmap. outputs/omni-ptresearch/SINGLE-PROCESS-PLAN.md.

memory-extra.h is the VSS shim libpas and WTF/OSAllocatorPlayStation use: reserve (free address range) -> commit
(make it usable) -> decommit/release. Today commit of a reserved piece does mmap(MAP_FIXED|ANON) = FLEXIBLE memory =
1 page table / 2 MiB. The title has ~12 GiB of direct memory that costs 0 tables (console probe 2026-11-20/22); the
engine children have none, so this is title-relevant and, for safety, DEFAULT OFF + full fallback (so the child and any
error path behave exactly as before).

With /data/omni/vss-direct.flag present:
  commit  : each reserved 16 KiB-aligned piece is sceKernelAllocateDirectMemory (type 0 WB_ONION) + mapped FIXED at its
            address; on ANY failure it falls back to today's flexible mmap. Already-mapped pieces: mprotect (as today).
  decommit: free the direct pieces (munmap + sceKernelReleaseDirectMemory) then re-reserve the range (cost-free), so the
            address space stays reserved and the physical direct memory goes back.
  release : free the direct pieces, then munmap the whole range.
The physical offset needed to release is read back with sceKernelVirtualQuery (q.offset = direct offset at the queried
region's start; probes D2/D3 2026-11-22 confirmed the offset math and that partial release works). No global state:
every function is still a static inline that only reads the flag and queries the kernel.

This edits the shim header in place; the title recipe binds a fixed copy over /opt (OMNI_VSS_BIND_V1), so it reaches the
title build; the child recipe picks it up too but the flag is never set there (and direct alloc would fail -> fallback).
usage: apply_vss_direct.py <memory-extra.h path>"""
import sys
from pathlib import Path

MARK = 'OMNI_VSS_DIRECT_V1'
p = Path(sys.argv[1])
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)


def rep(old, new):
    global s
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(old), old[:70]))
    s = s.replace(old, new, 1)


# 1. helpers: add after omni_vss_apply_prot's closing, before the first memory_extra_vss_ function.
HELP = r'''
#ifdef __PROSPERO__
// OMNI_VSS_DIRECT_V1: back commits with direct memory (0 page tables) in the title. See tools/apply_vss_direct.py.
#include <unistd.h>  // access
#ifdef __cplusplus
extern "C" {
#endif
int sceKernelAllocateDirectMemory(int64_t searchStart, int64_t searchEnd, size_t len, size_t align, int type, int64_t* phys);
int sceKernelMapDirectMemory(void** addr, size_t len, int prot, int flags, int64_t directStart, size_t align);
int sceKernelReleaseDirectMemory(int64_t start, size_t len);
int64_t sceKernelGetDirectMemorySize(void);
#ifdef __cplusplus
}
#endif
static inline bool omni_vss_direct_on(void)
{
    static int on = -1;
    if (on < 0)
        on = access("/data/omni/vss-direct.flag", F_OK) == 0 ? 1 : 0; // default OFF
    return on == 1;
}
// Commit one reserved 16 KiB-aligned piece with direct memory; false -> the caller uses the flexible path.
static inline bool omni_vss_direct_commit_one(uintptr_t at, size_t n, int prot)
{
    int64_t phys = -1;
    if (sceKernelAllocateDirectMemory(0, sceKernelGetDirectMemorySize(), n, OMNI_VSS_PAGE, 0 /* WB_ONION */, &phys))
        return false;
    void* got = (void*)at;
    if (sceKernelMapDirectMemory(&got, n, prot, OMNI_VSS_FIXED, phys, OMNI_VSS_PAGE) || got != (void*)at) {
        sceKernelReleaseDirectMemory(phys, n);
        return false;
    }
    return true;
}
static inline bool omni_vss_commit_cb(uintptr_t at, size_t n, bool mapped, int prot)
{
    if (mapped)
        return !mprotect((void*)at, n, prot);
    if (omni_vss_direct_on() && omni_vss_direct_commit_one(at, n, prot))
        return true;
    return omni_vss_apply_prot(at, n, false, prot); // flexible fallback (or child, where direct alloc fails)
}
// Free any direct memory mapped in [at, at+bytes); leaves the address space to the caller. 16 KiB granularity.
static inline void omni_vss_direct_free(uintptr_t at, size_t bytes)
{
    uintptr_t end = at + bytes;
    while (at < end) {
        omni_vss_query_info q;
        memset(&q, 0, sizeof q);
        if (sceKernelVirtualQuery((const void*)at, 0, &q, sizeof q))
            break;
        uintptr_t qs = (uintptr_t)q.start, qe = (uintptr_t)q.end;
        if (qe <= at)
            break;
        uintptr_t pieceEnd = qe < end ? qe : end;
        if (q.flags & 0x02) { // direct memory: phys = region offset + distance from the region start
            int64_t phys = q.offset + (int64_t)(at - qs);
            // R2 (2026-11-23): replace the piece with a FIXED reservation in ONE step - never munmap first. A munmap
            // left the range free until the caller re-reserved it; another thread's mmap(NULL) (IPC out-of-line
            // bodies, thousands a minute with the WebProcess in the title) could land there and was then wiped by
            // the FIXED re-reserve -> SIGSEGV "page not present" in memcpy (console 8b2cce2b, YouTube 4K in-process).
            void* r = (void*)at;
            if (sceKernelReserveVirtualRange(&r, pieceEnd - at, OMNI_VSS_FIXED, 0) || r != (void*)at)
                munmap((void*)at, pieceEnd - at);   // could not replace in place: the old behaviour
            sceKernelReleaseDirectMemory(phys, pieceEnd - at);
        }
        at = pieceEnd;
    }
}
#endif /* __PROSPERO__ */
'''
rep('static inline void* memory_extra_vss_reserve(size_t bytes, size_t alignment)\n',
    HELP + '\nstatic inline void* memory_extra_vss_reserve(size_t bytes, size_t alignment)\n')

# 2. commit: route through omni_vss_commit_cb when the flag is on.
rep('    /* Already-committed pieces keep their contents (mprotect), reserved pieces get\n'
    '     * fresh zeroed memory - the same result the original mprotect-only path gave. */\n'
    '    return omni_vss_each(addr, bytes, omni_vss_apply_prot, prot);\n',
    '    /* Already-committed pieces keep their contents (mprotect), reserved pieces get fresh memory - direct\n'
    '     * (0 page tables) when ' + MARK + ' is on, else flexible, the original result. */\n'
    '    return omni_vss_each(addr, bytes, omni_vss_direct_on() ? omni_vss_commit_cb : omni_vss_apply_prot, prot);\n')

# 3. decommit: free direct memory first, then the existing re-reserve returns the address space cost-free.
rep('    {\n'
    '        void* p = addr;\n'
    '        if (!sceKernelReserveVirtualRange(&p, bytes, OMNI_VSS_FIXED, 0) && p == addr)\n'
    '            return true; /* memory returned to the budget, range stays reserved */\n'
    '    }\n',
    '    {\n'
    '        if (omni_vss_direct_on())\n'
    '            omni_vss_direct_free((uintptr_t)addr, bytes); // ' + MARK + ': give the physical direct memory back\n'
    '        void* p = addr;\n'
    '        if (!sceKernelReserveVirtualRange(&p, bytes, OMNI_VSS_FIXED, 0) && p == addr)\n'
    '            return true; /* memory returned to the budget, range stays reserved */\n'
    '    }\n')

# 4. release: free direct memory, then munmap the address space as before.
rep('static inline bool memory_extra_vss_release(void* addr, size_t bytes)\n{\n    return !munmap(addr, bytes);\n}\n',
    'static inline bool memory_extra_vss_release(void* addr, size_t bytes)\n{\n'
    '#ifdef __PROSPERO__\n'
    '    if (omni_vss_direct_on())\n'
    '        omni_vss_direct_free((uintptr_t)addr, bytes); // ' + MARK + '\n'
    '#endif\n'
    '    return !munmap(addr, bytes);\n}\n')

p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
