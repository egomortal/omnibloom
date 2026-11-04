#!/usr/bin/env python3
"""Log failed allocator mappings without changing allocation or crash behavior."""
import pathlib
import sys

root = pathlib.Path(sys.argv[1]) / 'Source/bmalloc/libpas/src/libpas'
path = root / 'pas_page_malloc.c'
text = path.read_text()
marker = '/* omni allocation diagnostics */'
if marker not in text:
    anchor = '    if (mmap_result == MAP_FAILED) {\n'
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + '''#if PAS_PLATFORM(PLAYSTATION)
        /* omni allocation diagnostics */
        int saved_errno = errno;
        char message[160];
        int length = snprintf(message, sizeof(message), "allocator mmap failed: bytes=%zu errno=%d\\n", size, saved_errno);
        if (length > 0) write(2, message, (size_t)length < sizeof(message) ? (size_t)length : sizeof(message) - 1);
        errno = saved_errno;
#endif
''')
    path.write_text(text)
text = path.read_text()
if 'omni_mapping_backtrace' not in text:
    anchor = 'static void*\npas_page_malloc_try_map_pages(size_t size, pas_memory_flavor flavor)\n'
    assert text.count(anchor) == 1
    helper = '''#if PAS_PLATFORM(PLAYSTATION)
#include <unwind.h>
static _Unwind_Reason_Code omni_mapping_backtrace(struct _Unwind_Context* context, void* opaque)
{
    unsigned* count = opaque;
    char line[96];
    int length = snprintf(line, sizeof(line), "mapping stack[%u]=%p\\n", *count, (void*)_Unwind_GetIP(context));
    if (length > 0) write(2, line, (size_t)length < sizeof(line) ? (size_t)length : sizeof(line) - 1);
    return ++*count >= 20 ? _URC_END_OF_STACK : _URC_NO_REASON;
}
#endif
'''
    text = text.replace(anchor, helper + anchor)
    anchor = '        errno = saved_errno;\n'
    assert text.count(anchor) == 1
    text = text.replace(anchor, '        unsigned mapping_depth = 0;\n        _Unwind_Backtrace(omni_mapping_backtrace, &mapping_depth);\n' + anchor)
    path.write_text(text)
text = path.read_text()
if 'omni mapping budget' not in text:
    anchor = '        unsigned mapping_depth = 0;\n'
    assert text.count(anchor) == 1
    text = text.replace(anchor, '''        /* omni mapping budget: measure at failure, not earlier startup. */
        extern int sceKernelAvailableFlexibleMemorySize(size_t*);
        size_t available_flexible = 0;
        int query_result = sceKernelAvailableFlexibleMemorySize(&available_flexible);
        length = snprintf(message, sizeof(message), "allocator budget: query=%d flexible=%zu allocated=%zu\\n", query_result, available_flexible, pas_page_malloc_num_allocated_bytes);
        if (length > 0) write(2, message, (size_t)length < sizeof(message) ? (size_t)length : sizeof(message) - 1);
''' + anchor)
    path.write_text(text)
text = path.read_text()
if 'omni native mapping comparison' not in text:
    anchor = '        unsigned mapping_depth = 0;\n'
    assert text.count(anchor) == 1
    text = text.replace(anchor, '''        /* omni native mapping comparison: diagnostic only, never an allocator fallback. */
        if (size == 67108864) {
            extern int sceKernelMapFlexibleMemory(void**, size_t, int, int);
            extern int sceKernelReleaseFlexibleMemory(void*, size_t);
            void* native_mapping = NULL;
            int native_result = sceKernelMapFlexibleMemory(&native_mapping, size, 3, 0);
            int release_result = native_result ? 0 : sceKernelReleaseFlexibleMemory(native_mapping, size);
            length = snprintf(message, sizeof(message), "allocator native comparison: result=%#x address=%p release=%#x\\n", native_result, native_mapping, release_result);
            if (length > 0) write(2, message, (size_t)length < sizeof(message) ? (size_t)length : sizeof(message) - 1);
        }
''' + anchor)
    path.write_text(text)
path = root / 'pas_utils.c'
text = path.read_text()
if marker not in text:
    anchor = 'void pas_panic_on_out_of_memory_error(void)\n{\n'
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + '''#if PAS_PLATFORM(PLAYSTATION)
    /* omni allocation diagnostics */
    char message[160];
    int length = snprintf(message, sizeof(message), "allocator fatal: caller=%p\\n", __builtin_return_address(0));
    if (length > 0) write(2, message, (size_t)length < sizeof(message) ? (size_t)length : sizeof(message) - 1);
#endif
''')
    path.write_text(text)
text = path.read_text()
if 'omni_allocation_backtrace' not in text:
    anchor = 'void pas_panic_on_out_of_memory_error(void)\n'
    assert text.count(anchor) == 1
    helper = '''#if PAS_PLATFORM(PLAYSTATION)
#include <unwind.h>
static _Unwind_Reason_Code omni_allocation_backtrace(struct _Unwind_Context* context, void* opaque)
{
    unsigned* count = opaque;
    char line[96];
    int length = snprintf(line, sizeof(line), "allocator stack[%u]=%p\\n", *count, (void*)_Unwind_GetIP(context));
    if (length > 0) write(2, line, (size_t)length < sizeof(line) ? (size_t)length : sizeof(line) - 1);
    return ++*count >= 20 ? _URC_END_OF_STACK : _URC_NO_REASON;
}
#endif
'''
    text = text.replace(anchor, helper + anchor)
    trace_marker = '    /* omni allocation diagnostics */\n'
    assert text.count(trace_marker) == 1
    text = text.replace(trace_marker, trace_marker + '    unsigned depth = 0;\n    _Unwind_Backtrace(omni_allocation_backtrace, &depth);\n')
    path.write_text(text)
