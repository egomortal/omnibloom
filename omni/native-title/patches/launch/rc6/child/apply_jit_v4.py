#!/usr/bin/env python3
"""OMNI_JSC_JIT_V4: W^X JIT pool for JavaScriptCore on the PS5 (dual mapping, no runtime permission changes).

V3 (in the launch child) maps the JIT pool read/write/execute once, so it can't race on concurrent exec-permission
mprotects (EPERM / stalls on FW 13.60), but it gives up W^X for the WebProcess's whole life, which is why the JIT is
opt-in ("faster, less safe").

V4 keeps V3's rule (permissions are set once, single-threaded, at reservation, and never changed) and restores W^X:
the pool is an anonymous shared-memory object mapped twice, read+execute at the address JSC runs code from, and
read+write at a second, unrelated address that only JSC's JIT-copy routine writes through. Console proof:
omni-jit-fix/probe/jitprobe4 (2026-11-11, single-threaded): shm 64 MB, RW view + RX view, 5000 random
write-through-RW / run-through-RX checks, 5000 ok, 0 bad. (Direct memory at 64 MB is refused: 0x80020023.)

Every JIT write on x86-64 goes through performJITMemcpy (LinkBuffer::linkCode, X86Assembler set*/relink/replace/
revert/fillNops via machineCodeCopy<jitMemcpyRepatch>); V4 makes it copy to alias + (dst - pool) before the
MPROTECT_RX_TO_RWX branch (whose write window V3 already made a no-op). A write that bypasses it now faults on the
RX view instead of silently landing in RWX memory.

Fallback: if shm_open/ftruncate/mmap fail, or the alias self-check fails, the pool is made exactly as V3 does.
Kill switch: /data/omni/jsc-jit-v3.flag -> V3 (RWX). The JIT itself still only runs with /data/omni/jsc-jit.flag.

Usage: apply_jit_v4.py <webkit source root>   (anchored, once each; idempotent)
"""
import sys
from pathlib import Path
root = Path(sys.argv[1]) / 'Source'
MARK = 'OMNI_JSC_JIT_V4'

def patch(rel, edits):
    p = root / rel
    s = p.read_text(encoding='utf-8')
    if MARK in s:
        return 'already'
    for old, new in edits:
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (rel, s.count(old), old[:80]))
        s = s.replace(old, new, 1)
    p.write_text(s, encoding='utf-8')
    return 'applied'

# 1. WTF: the pool as RX + RW alias of one shm object.
osa = patch('WTF/wtf/playstation/OSAllocatorPlayStation.cpp', [
    ('static uintptr_t s_omniExecBegin;\n',
     'static uintptr_t s_omniExecBegin;\n'
     'static uintptr_t s_omniExecWritable; // OMNI_JSC_JIT_V4: the RW alias of the pool (0 = V3, no alias)\n'),
    ('static void* omniMapExecutable(size_t bytes, bool writable)\n{\n'
     '    if (bytes > s_omniExecMaxBytes || s_omniExecEnd) {\n'
     '        fprintf(stderr, "jit: executable reservation refused bytes=%zu existing=%d\\n", bytes, s_omniExecEnd ? 1 : 0);\n'
     '        return nullptr;\n'
     '    }\n',
     'static void* omniMapExecutable(size_t bytes, bool writable)\n{\n'
     '    if (bytes > s_omniExecMaxBytes || s_omniExecEnd) {\n'
     '        fprintf(stderr, "jit: executable reservation refused bytes=%zu existing=%d\\n", bytes, s_omniExecEnd ? 1 : 0);\n'
     '        return nullptr;\n'
     '    }\n'
     '    // OMNI_JSC_JIT_V4: W^X without runtime permission changes. One anonymous shared-memory object, mapped\n'
     '    // read+execute (where JSC runs code) and read+write at a second address (where performJITMemcpy writes).\n'
     '    // Both protections are fixed at map time, here, on JSC\'s initialising thread (probe 4, 2026-11-11).\n'
     '    if (access("/data/omni/jsc-jit-v3.flag", F_OK)) {\n'
     '        int fd = shm_open(SHM_ANON, O_RDWR, 0600);\n'
     '        void* rx = MAP_FAILED;\n'
     '        void* rw = MAP_FAILED;\n'
     '        int err = 0;\n'
     '        if (fd < 0 || ftruncate(fd, bytes))\n'
     '            err = errno;\n'
     '        else {\n'
     '            rx = mmap(nullptr, bytes, PROT_READ | PROT_EXEC, MAP_SHARED, fd, 0);\n'
     '            err = rx == MAP_FAILED ? errno : 0;\n'
     '            if (rx != MAP_FAILED) {\n'
     '                rw = mmap(nullptr, bytes, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);\n'
     '                err = rw == MAP_FAILED ? errno : 0;\n'
     '            }\n'
     '        }\n'
     '        if (fd >= 0)\n'
     '            close(fd);\n'
     '        bool aliasOk = false;\n'
     '        if (rx != MAP_FAILED && rw != MAP_FAILED) {\n'
     '            // Self-check without executing anything: bytes written through the RW view read back through RX.\n'
     '            volatile uint8_t* w = static_cast<volatile uint8_t*>(rw) + bytes - 16;\n'
     '            const volatile uint8_t* r = static_cast<const volatile uint8_t*>(rx) + bytes - 16;\n'
     '            static const uint8_t probe[8] = { 0xB8, 0x2A, 0x00, 0x00, 0x00, 0xC3, 0xCC, 0xCC };\n'
     '            for (unsigned i = 0; i < 8; ++i)\n'
     '                w[i] = probe[i];\n'
     '            aliasOk = true;\n'
     '            for (unsigned i = 0; i < 8; ++i)\n'
     '                aliasOk = aliasOk && r[i] == probe[i];\n'
     '            for (unsigned i = 0; i < 8; ++i)\n'
     '                w[i] = 0xCC;\n'
     '        }\n'
     '        if (aliasOk) {\n'
     '            s_omniExecBegin = reinterpret_cast<uintptr_t>(rx);\n'
     '            s_omniExecEnd = s_omniExecBegin + bytes;\n'
     '            s_omniExecWritable = reinterpret_cast<uintptr_t>(rw);\n'
     '            fprintf(stderr, "jit: executable pool %p bytes=%zu read+execute, write alias elsewhere: W^X, no runtime permission changes (OMNI_JSC_JIT_V4)\\n", rx, bytes);\n'
     '            return rx;\n'
     '        }\n'
     '        if (rx != MAP_FAILED)\n'
     '            munmap(rx, bytes);\n'
     '        if (rw != MAP_FAILED)\n'
     '            munmap(rw, bytes);\n'
     '        fprintf(stderr, "jit: V4 dual mapping unavailable (errno %d, alias check %d); using V3\\n", err, aliasOk ? 1 : 0);\n'
     '    } else\n'
     '        fprintf(stderr, "jit: /data/omni/jsc-jit-v3.flag: V3 pool requested\\n");\n'),
    ('void* OSAllocator::tryReserveAndCommit(',
     '} // namespace WTF\n'
     '// OMNI_JSC_JIT_V4: JavaScriptCore asks for the RW alias of an address in the pool (0 when the pool has no alias).\n'
     'extern "C" uintptr_t omniJitWritableAlias(uintptr_t executableAddress)\n{\n'
     '    if (!WTF::s_omniExecWritable || executableAddress < WTF::s_omniExecBegin || executableAddress >= WTF::s_omniExecEnd)\n'
     '        return 0;\n'
     '    return WTF::s_omniExecWritable + (executableAddress - WTF::s_omniExecBegin);\n'
     '}\n'
     'namespace WTF {\n\n'
     'void* OSAllocator::tryReserveAndCommit('),
])
src = (root / 'WTF/wtf/playstation/OSAllocatorPlayStation.cpp').read_text(encoding='utf-8')
if '#include <fcntl.h>' not in src:
    src = src.replace('#include <errno.h>\n', '#include <errno.h>\n#include <fcntl.h>\n', 1)
    (root / 'WTF/wtf/playstation/OSAllocatorPlayStation.cpp').write_text(src, encoding='utf-8')

# 2. JSC: record the alias of the pool's start.
ea = patch('JavaScriptCore/jit/ExecutableAllocator.cpp', [
    ('        g_jscConfig.startExecutableMemory = reservation.base;\n',
     '        g_jscConfig.startExecutableMemory = reservation.base;\n'
     '#if PLATFORM(PLAYSTATION)\n'
     '        // OMNI_JSC_JIT_V4: writes into the pool go through its RW alias (0 = V3 pool, written in place).\n'
     '        g_jscConfig.startOfFixedWritableMemoryPool = omniJitWritableAlias(reinterpret_cast<uintptr_t>(reservation.base));\n'
     '#endif\n'),
    ('namespace JSC {\n\nusing namespace WTF;\n',
     '#if PLATFORM(PLAYSTATION)\n'
     'extern "C" uintptr_t omniJitWritableAlias(uintptr_t executableAddress); // OMNI_JSC_JIT_V4 (WTF OSAllocatorPlayStation)\n'
     '#endif\n\n'
     'namespace JSC {\n\nusing namespace WTF;\n'),
])

# 3. JSC: performJITMemcpy writes through the alias.
eh = patch('JavaScriptCore/jit/ExecutableAllocator.h', [
    ('    jitMemcpyChecks(dst, src, n);\n'
     '    if (isJITPC(dst)) {\n'
     '#if ENABLE(MPROTECT_RX_TO_RWX)\n'
     '        auto ret = performJITMemcpyWithMProtect(dst, src, n);\n',
     '    jitMemcpyChecks(dst, src, n);\n'
     '    if (isJITPC(dst)) {\n'
     '#if PLATFORM(PLAYSTATION)\n'
     '        if (g_jscConfig.startOfFixedWritableMemoryPool) {\n'
     '            // OMNI_JSC_JIT_V4: the pool is read+execute here; its write alias is the same memory elsewhere.\n'
     '            void* alias = reinterpret_cast<void*>(g_jscConfig.startOfFixedWritableMemoryPool\n'
     '                + (reinterpret_cast<uintptr_t>(dst) - reinterpret_cast<uintptr_t>(g_jscConfig.startExecutableMemory)));\n'
     '            if constexpr ((*repatch).contains(RepatchingFlag::Atomic))\n'
     '                memcpyAtomic(alias, src, n);\n'
     '            else\n'
     '                memcpyAtomicIfPossible(alias, src, n);\n'
     '            jitMemcpyCheckForZeros(dst, src, n);\n'
     '            return dst;\n'
     '        }\n'
     '#endif\n'
     '#if ENABLE(MPROTECT_RX_TO_RWX)\n'
     '        auto ret = performJITMemcpyWithMProtect(dst, src, n);\n'),
])
print('OSAllocatorPlayStation.cpp %s; ExecutableAllocator.cpp %s; ExecutableAllocator.h %s' % (osa, ea, eh))
print('applied' if 'applied' in (osa, ea, eh) else 'already applied')
