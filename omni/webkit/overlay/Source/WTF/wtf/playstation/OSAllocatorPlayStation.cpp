/*
 * Copyright (C) 2010-2022 Apple Inc. All rights reserved.
 * Copyright (C) 2024 SONY Interactive Entertainment Inc. All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY APPLE INC. AND ITS CONTRIBUTORS ``AS IS''
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
 * THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 * PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL APPLE INC. OR ITS CONTRIBUTORS
 * BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF
 * THE POSSIBILITY OF SUCH DAMAGE.
 */

#include "config.h"
#include <wtf/OSAllocator.h>

#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <memory-extra/vss.h>
#include <wtf/Assertions.h>
#include <wtf/DataLog.h>
#include <wtf/MathExtras.h>
#include <wtf/PageBlock.h>
#include <wtf/SafeStrerror.h>
#include <wtf/text/CString.h>

namespace WTF {

// OMNI_JSC_JIT_V1: executable memory for JavaScriptCore's JIT pool.
// Sony's allocator refuses executable memory (memory-extra commits RW only). Omni's WebProcess runs as a
// jailbroken payload, where anonymous mappings may be made executable (console probe omni-native-jit0,
// 2026-11-02: RW->RX and RX<->RWX flips work in the WebProcess type). The JIT is only reached when the
// WebProcess starts with JSC_useJIT=true (Omni's /data/omni/jsc-jit.flag, default off). The pool is
// mapped with plain mmap at its reserved size (JSC_jitMemoryReservationSize keeps it small) and is
// never handed to memory-extra; ENABLE(MPROTECT_RX_TO_RWX) keeps it read+execute except while JSC
// writes code. Only one executable region exists (JSC's fixed pool); it is tracked here so the
// decommit/release/protect calls that libpas or JSC make on it use mmap/mprotect, not memory-extra.
static uintptr_t s_omniExecBegin;
static uintptr_t s_omniExecEnd;
static constexpr size_t s_omniExecMaxBytes = 256 * 1024 * 1024;

static bool omniInExecRegion(const void* address, size_t bytes)
{
    uintptr_t begin = reinterpret_cast<uintptr_t>(address);
    return s_omniExecEnd && begin >= s_omniExecBegin && begin + bytes <= s_omniExecEnd;
}

static void* omniMapExecutable(size_t bytes, bool writable)
{
    if (bytes > s_omniExecMaxBytes || s_omniExecEnd) {
        fprintf(stderr, "jit: executable reservation refused bytes=%zu existing=%d\n", bytes, s_omniExecEnd ? 1 : 0);
        return nullptr;
    }
    // Map read/write, then flip to the requested protection: the probe showed RWX at map time is
    // silently dropped in the title type, while mprotect after mapping works in both process types.
    void* result = mmap(nullptr, bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    if (result == MAP_FAILED) {
        fprintf(stderr, "jit: executable mmap failed bytes=%zu errno=%d\n", bytes, errno);
        return nullptr;
    }
    int protection = PROT_READ | PROT_EXEC | (writable ? PROT_WRITE : 0);
    if (mprotect(result, bytes, protection)) {
        fprintf(stderr, "jit: executable mprotect failed bytes=%zu errno=%d\n", bytes, errno);
        munmap(result, bytes);
        return nullptr;
    }
    s_omniExecBegin = reinterpret_cast<uintptr_t>(result);
    s_omniExecEnd = s_omniExecBegin + bytes;
    fprintf(stderr, "jit: executable pool %p bytes=%zu %s\n", result, bytes, writable ? "rwx" : "rx (written through rx<->rwx flips)");
    return result;
}

void* OSAllocator::tryReserveAndCommit(size_t bytes, Usage usage, void* address, bool writable, bool executable, bool jitCageEnabled, unsigned numGuardPagesToAddOnEachEnd)
{
    UNUSED_PARAM(numGuardPagesToAddOnEachEnd); // Guard pages not supported, and will be ignored.
    ASSERT_UNUSED(jitCageEnabled, !jitCageEnabled);
    ASSERT_UNUSED(address, !address);
    if (executable)
        return omniMapExecutable(bytes, writable);

    void* result = memory_extra::vss::reserve(bytes);
    if (!result)
        return nullptr;

    bool success = memory_extra::vss::commit(result, bytes, writable, usage);
    if (!success) {
        memory_extra::vss::release(result, bytes);
        return nullptr;
    }

    return result;
}

void* OSAllocator::tryReserveUncommitted(size_t bytes, Usage usage, void* address, bool writable, bool executable, bool jitCageEnabled, unsigned numGuardPagesToAddOnEachEnd)
{
    UNUSED_PARAM(usage);
    UNUSED_PARAM(numGuardPagesToAddOnEachEnd); // Guard pages not supported, and will be ignored.
    ASSERT_UNUSED(jitCageEnabled, !jitCageEnabled);
    ASSERT_UNUSED(address, !address);
    // libpas' JIT heap never commits its pages on PlayStation (client-owned permissions), so the
    // executable pool is mapped, accessible, at reservation time.
    if (executable)
        return omniMapExecutable(bytes, writable);

    void* result = memory_extra::vss::reserve(bytes);
    if (!result)
        return nullptr;

    return result;
}

void* OSAllocator::reserveUncommitted(size_t bytes, Usage usage, void* address, bool writable, bool executable, bool jitCageEnabled, unsigned numGuardPagesToAddOnEachEnd)
{
    void* result = tryReserveUncommitted(bytes, usage, address, writable, executable, jitCageEnabled, numGuardPagesToAddOnEachEnd);
    RELEASE_ASSERT(result);
    return result;
}

void* OSAllocator::tryReserveUncommittedAligned(size_t bytes, size_t alignment, Usage usage, void* address, bool writable, bool executable, bool jitCageEnabled, unsigned numGuardPagesToAddOnEachEnd)
{
    ASSERT_UNUSED(numGuardPagesToAddOnEachEnd, !numGuardPagesToAddOnEachEnd);
    ASSERT_UNUSED(jitCageEnabled, !jitCageEnabled);
    ASSERT_UNUSED(executable, !executable);
    ASSERT_UNUSED(address, !address);
    UNUSED_PARAM(usage);
    UNUSED_PARAM(writable);
    ASSERT(hasOneBitSet(alignment) && alignment >= pageSize());

    void* result = memory_extra::vss::reserve(bytes, alignment);
    if (!result)
        return nullptr;

    return result;
}

void* OSAllocator::reserveAndCommit(size_t bytes, Usage usage, void* address, bool writable, bool executable, bool jitCageEnabled, unsigned numGuardPagesToAddOnEachEnd)
{
    void* result = tryReserveAndCommit(bytes, usage, address, writable, executable, jitCageEnabled, numGuardPagesToAddOnEachEnd);
    RELEASE_ASSERT(result);
    return result;
}

void OSAllocator::commit(void* address, size_t bytes, bool writable, bool executable)
{
    if (executable || omniInExecRegion(address, bytes)) {
        // Already mapped at reservation; (re)apply the protection.
        bool success = !mprotect(address, bytes, PROT_READ | PROT_EXEC | (writable ? PROT_WRITE : 0));
        RELEASE_ASSERT(success);
        return;
    }
    bool success = memory_extra::vss::commit(address, bytes, writable, -1);
    RELEASE_ASSERT(success);
}

void OSAllocator::decommit(void* address, size_t bytes)
{
    if (omniInExecRegion(address, bytes)) {
        madvise(address, bytes, MADV_DONTNEED);
        return;
    }
    bool success = memory_extra::vss::decommit(address, bytes);
    RELEASE_ASSERT(success);
}

void OSAllocator::hintMemoryNotNeededSoon(void* address, size_t bytes)
{
    UNUSED_PARAM(address);
    UNUSED_PARAM(bytes);
}

void OSAllocator::releaseDecommitted(void* address, size_t bytes, unsigned numGuardPagesToAddOnEachEnd)
{
    UNUSED_PARAM(numGuardPagesToAddOnEachEnd); // Guard pages not supported, and will be ignored.
    if (omniInExecRegion(address, bytes)) {
        RELEASE_ASSERT(!munmap(address, bytes));
        if (reinterpret_cast<uintptr_t>(address) == s_omniExecBegin && reinterpret_cast<uintptr_t>(address) + bytes == s_omniExecEnd)
            s_omniExecBegin = s_omniExecEnd = 0;
        return;
    }
    bool success = memory_extra::vss::release(address, bytes);
    RELEASE_ASSERT(success);
}

bool OSAllocator::tryProtect(void* address, size_t bytes, bool readable, bool writable)
{
    if (omniInExecRegion(address, bytes))
        return !mprotect(address, bytes, (readable ? PROT_READ : 0) | (writable ? PROT_WRITE : 0) | PROT_EXEC);
    return memory_extra::vss::protect(address, bytes, readable, writable, -1);
}

void OSAllocator::protect(void* address, size_t bytes, bool readable, bool writable)
{
    if (bool result = tryProtect(address, bytes, readable, writable); !result) [[unlikely]] {
        dataLogLn("mprotect failed: ", safeStrerror(errno));
        RELEASE_ASSERT_NOT_REACHED();
    }
}

void OSAllocator::zeroFill(void* base, size_t size)
{
    memset(base, 0, size);
}

} // namespace WTF
