#!/usr/bin/env python3
"""OMNI_PAS_DECOMMIT_REMAP_V1 (2026-11-20, owner: "no i need it gone forever").

Console probes (outputs/omni-ptprobe/freeprobe*.c, START-HERE 2026-11-20):
  * the shared kernel CPU page-table pool is charged per MAPPED 2 MiB of flexible memory, touched or not, any protection
    (mmap PROT_NONE costs the same as RW); only munmap gives it back;
  * madvise(MADV_FREE) / MADV_DONTNEED / mprotect / MAP_FIXED remap give nothing back.
libpas (WebKit's malloc, PAS_OS(FREEBSD) on PS5) maps its pages RW, never unmaps them, and its scavenger "decommits"
with madvise(MADV_FREE): every page the web process ever used keeps costing the pool until the process exits (the
YouTube page process climbs to ~1,400 tables and never comes down).

Fix (PLAYSTATION only, libpas pas_page_malloc.c):
  * decommit_impl with do_mprotect (the symmetric contract: libpas commits again before touching; PAS_MPROTECT_DECOMMITTED
    test mode makes such pages PROT_NONE, so no caller reads them): memory_extra_vss_decommit() = re-reserve the range
    with sceKernelReserveVirtualRange(FIXED) -> pages and page tables go back, the address range stays ours (no hole).
    decommit_without_mprotect callers (expendable memory reads decommitted pages) keep madvise(MADV_FREE).
  * commit_impl with do_mprotect: memory_extra_vss_commit() = map RW only the pieces that are reserved (unmapped), plain
    mprotect for pieces still mapped, so live data is never replaced.
  * off switch /data/omni/decommit-remap-off.flag (read once): the original behaviour exactly. A failed re-reserve falls
    back to madvise, a failed commit map stops the process (explicit trap; PAS_ASSERT is compiled out on PS5).
usage: apply_pas_decommit_remap.py <tree root holding webkit/Source>"""
import sys
from pathlib import Path

MARK = 'OMNI_PAS_DECOMMIT_REMAP_V1'
p = Path(sys.argv[1]) / 'webkit/Source/bmalloc/libpas/src/libpas/pas_page_malloc.c'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)


def rep(old, new):
    global s
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(old), old[:90]))
    s = s.replace(old, new, 1)


HELPER = r'''#if PAS_PLATFORM(PLAYSTATION)
/* OMNI_PAS_DECOMMIT_REMAP_V1: on PS5 only unmapping returns kernel page tables; decommit re-reserves the range
 * (memory-extra VSS), commit maps the reserved pieces again. Off with /data/omni/decommit-remap-off.flag. */
#include <memory-extra.h>
#include <unistd.h>
static int omni_pas_remap_on(void)
{
    static int on = -1;
    if (on < 0)
        on = access("/data/omni/decommit-remap-off.flag", F_OK) != 0;
    return on;
}
#endif

static void commit_impl('''
rep('static void commit_impl(', HELPER)

# commit: the PLAYSTATION branch of commit_impl ("We don't need to call madvise to map page.")
rep('#elif PAS_PLATFORM(PLAYSTATION)\n    /* We don\'t need to call madvise to map page. */\n    PAS_ASSERT(!is_symmetric);\n',
    '#elif PAS_PLATFORM(PLAYSTATION)\n    /* We don\'t need to call madvise to map page. */\n    PAS_ASSERT(!is_symmetric);\n'
    '    if (do_mprotect && !pas_memory_flavor_client_owns_permissions(flavor) && omni_pas_remap_on())   /* ' + MARK + ' */\n'
    '        if (!memory_extra_vss_commit(ptr, size, true, -1)) {   /* never inside PAS_ASSERT: compiled out on PS5 */\n'
    '            static const char msg[] = "OMNI PAS REMAP: commit map failed\\n";\n'
    '            write(2, msg, sizeof msg - 1);\n'
    '            __builtin_trap();\n'
    '        }\n')

# decommit: the FREEBSD branch of decommit_impl
rep('#elif PAS_OS(FREEBSD)\n    PAS_ASSERT(!is_symmetric);\n    PAS_SYSCALL(madvise(ptr, size, MADV_FREE));\n',
    '#elif PAS_OS(FREEBSD)\n    PAS_ASSERT(!is_symmetric);\n'
    '#if PAS_PLATFORM(PLAYSTATION)\n'
    '    if (!(do_mprotect && !client_owns_permissions && omni_pas_remap_on() && memory_extra_vss_decommit(ptr, size)))   /* ' + MARK + ' */\n'
    '#endif\n'
    '    PAS_SYSCALL(madvise(ptr, size, MADV_FREE));\n')

p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
