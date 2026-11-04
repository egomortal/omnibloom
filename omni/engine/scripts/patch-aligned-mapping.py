#!/usr/bin/env python3
"""Avoid temporary double-sized mappings when the PS5 honors MAP_ALIGNED.

Retains original libpas region sizes, header masking, zeroing and accounting.
The original allocation path remains the fallback if kernel alignment fails.
"""
import pathlib
import sys
path = pathlib.Path(sys.argv[1]) / 'Source/bmalloc/libpas/src/libpas/pas_page_malloc.c'
text = path.read_text()
marker = '/* omni aligned mapping: avoid alignment padding peak. */'
if marker not in text:
    anchor = '    mmap_result = pas_page_malloc_try_map_pages(mapped_size, flavor);\n'
    assert text.count(anchor) == 1
    text = text.replace(anchor, '''    mmap_result = NULL;
#if PAS_PLATFORM(PLAYSTATION)
    /* omni aligned mapping: avoid alignment padding peak. */
    if (!alignment.alignment_begin && page_allocation_alignment > pas_page_malloc_alignment()) {
        void* candidate = mmap(NULL, aligned_size, PROT_READ | PROT_WRITE,
            MAP_PRIVATE | MAP_ANON | MAP_ALIGNED(pas_log2(page_allocation_alignment)), PAS_VM_TAG, 0);
        if (candidate != MAP_FAILED) {
            if (!((uintptr_t)candidate & (page_allocation_alignment - 1))) {
                mmap_result = candidate;
                mapped_size = aligned_size;
            } else {
                // Some kernels may ignore optional alignment flags.
                int released = munmap(candidate, aligned_size);
                PAS_ASSERT(!released);
            }
        }
    }
#endif
    if (!mmap_result)
        mmap_result = pas_page_malloc_try_map_pages(mapped_size, flavor);
''')
    path.write_text(text)
