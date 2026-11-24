#!/usr/bin/env python3
"""OMNI_VSS_LIBPAS_V1 (2026-11-23): Phase 1 extension - libpas's MAIN page allocator on direct memory in the title.

Phase 1 (OMNI_VSS_DIRECT_V1) put memory_extra::vss on direct memory, but in libpas only the compact heap reservation
goes through memory_extra_vss_*; pas_page_malloc (all other libpas pages: the WebKit/JS heaps' pages) still maps with
plain mmap = FLEXIBLE memory. Console 2026-11-23 (d6068772, Lytiwm, OMNI_MEMMAP_V1): with the WebProcess in the title,
"F:anon:<pas_enumerable_page_malloc_try_allocate_without_deallocating_padding>" was 504 MB in 1382 regions (56 MB
without it), the title's flexible total 996 MB of its ~1 GB budget -> hardware decoder ENOMEM, then JSC
handleResourceExhaustion (crash at 78 s).

With /data/omni/vss-direct.flag (omni_vss_direct_on(), patched header), on PlayStation:
  map      : memory_extra_vss_reserve + memory_extra_vss_commit (direct pieces, 0 page tables); on failure the original
             mmap. Both the plain path (pas_page_malloc_try_map_pages) and the "omni aligned mapping" path.
  decommit : UNCHANGED (madvise). In production libpas does not mprotect decommitted pages and some users
             (thread-local caches, expendable memory) may read them after decommit, so the pages must stay mapped.
             Decommitted direct pages stay resident until freed (direct memory, no flexible, no page tables).
  free     : memory_extra_vss_release (frees direct pieces in place - R2, no address gap - then munmap).
Pages whose flavour owns its permissions (pas_memory_flavor_client_owns_permissions) keep the original path.
usage: apply_vss_libpas.py <bmalloc/libpas/src/libpas/pas_page_malloc.c>"""
import sys
from pathlib import Path

MARK = 'OMNI_VSS_LIBPAS_V1'
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


rep('#include "pas_zero_memory.h"\n',
    '#include "pas_zero_memory.h"\n'
    '#if PAS_PLATFORM(PLAYSTATION)\n'
    '#include <memory-extra.h>   /* ' + MARK + ': title pages on direct memory (vss-direct.flag) */\n'
    '#endif\n')

# 1. the plain mapping path
rep('    mmap_result = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON | PAS_NORESERVE, PAS_VM_TAG, 0);\n'
    '    if (mmap_result == MAP_FAILED) {\n',
    '#if PAS_PLATFORM(PLAYSTATION)\n'
    '    if (omni_vss_direct_on() && !pas_memory_flavor_client_owns_permissions(flavor)) {   /* ' + MARK + ' */\n'
    '        void* omni_pages = memory_extra_vss_reserve(size, 0);\n'
    '        if (omni_pages && memory_extra_vss_commit(omni_pages, size, true, -1)) {\n'
    '            PAS_RECORD_STAT(page_alloc_counts, size, false);\n'
    '            return omni_pages;\n'
    '        }\n'
    '        if (omni_pages)\n'
    '            memory_extra_vss_release(omni_pages, size);\n'
    '    }\n'
    '#endif\n'
    '    mmap_result = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON | PAS_NORESERVE, PAS_VM_TAG, 0);\n'
    '    if (mmap_result == MAP_FAILED) {\n')

# 2. the aligned mapping path
rep('    if (!alignment.alignment_begin && page_allocation_alignment > pas_page_malloc_alignment()) {\n'
    '        void* candidate = mmap(NULL, aligned_size, PROT_READ | PROT_WRITE,\n',
    '    if (omni_vss_direct_on() && !pas_memory_flavor_client_owns_permissions(flavor)\n'
    '        && !alignment.alignment_begin && page_allocation_alignment > pas_page_malloc_alignment()) {   /* ' + MARK + ' */\n'
    '        void* omni_pages = memory_extra_vss_reserve(aligned_size, page_allocation_alignment);\n'
    '        if (omni_pages && !((uintptr_t)omni_pages & (page_allocation_alignment - 1))\n'
    '            && memory_extra_vss_commit(omni_pages, aligned_size, true, -1)) {\n'
    '            mmap_result = omni_pages;\n'
    '            mapped_size = aligned_size;\n'
    '        } else if (omni_pages)\n'
    '            memory_extra_vss_release(omni_pages, aligned_size);\n'
    '    }\n'
    '    if (!mmap_result && !alignment.alignment_begin && page_allocation_alignment > pas_page_malloc_alignment()) {\n'
    '        void* candidate = mmap(NULL, aligned_size, PROT_READ | PROT_WRITE,\n')

# 3. free
rep('#else\n    munmap(ptr, size);\n',
    '#else\n'
    '#if PAS_PLATFORM(PLAYSTATION)\n'
    '    if (omni_vss_direct_on()) {   /* ' + MARK + ': frees direct pieces in place, then unmaps (also plain mappings) */\n'
    '        memory_extra_vss_release(ptr, size);\n'
    '        return;\n'
    '    }\n'
    '#endif\n'
    '    munmap(ptr, size);\n')

p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
