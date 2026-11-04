// Omni Engine: C++ API of the "memory-extra" VSS shim used by WebKit's
// PlayStation port (WTF/wtf/playstation/OSAllocatorPlayStation.cpp).
// SPDX-License-Identifier: BSD-2-Clause
#pragma once
#include <memory-extra.h>

namespace memory_extra {
namespace vss {
inline void* reserve(size_t bytes, size_t alignment = 0) { return memory_extra_vss_reserve(bytes, alignment); }
inline bool commit(void* a, size_t n, bool writable, int usage) { return memory_extra_vss_commit(a, n, writable, usage); }
inline bool decommit(void* a, size_t n) { return memory_extra_vss_decommit(a, n); }
inline bool release(void* a, size_t n) { return memory_extra_vss_release(a, n); }
inline bool protect(void* a, size_t n, bool r, bool w, int usage) { return memory_extra_vss_protect(a, n, r, w, usage); }
} // namespace vss
} // namespace memory_extra
