#!/usr/bin/env python3
"""OMNI_MEMTRACE_V1 (2026-11-18, test only): log every direct-memory allocation / mapping of the TITLE with its caller.

Why: OMNI_MEMMAP_V2 showed ~300 MB of GPU-visible direct memory at idle that exists only with the GPU present on, and
the present / GPU video logs account for ~45 MB of it. stage1/src-title/omni_memtrace.c wraps the three direct-memory
imports (sceKernelAllocateMainDirectMemory, sceKernelAllocateDirectMemory, sceKernelMapDirectMemory) at link time, so
the static SDL, the pinned RADV archive and the title's own code all log "OMNI MEMTRACE: ..." lines (size, protection,
caller offset) while /data/omni/memmap.flag exists. The import table does not change (__real_X = the same import X).

Mode:
  build <build.py> <stage1/src-title>   the TITLE link, run AFTER apply_one_submitter.py build (anchors on its lines):
                                        compiles omni_memtrace.c, adds the 3 wraps, and a gate after pass 2 refusing a
                                        title without the 3 __wrap_ definitions.
Idempotent ("already"), every anchor must be found exactly once, CRLF kept.
usage: apply_memtrace.py build <build.py> <stage1/src-title>"""
import sys
from pathlib import Path

MARK = 'OMNI_MEMTRACE_V1'
WRAPS = ['sceKernelAllocateMainDirectMemory', 'sceKernelAllocateDirectMemory', 'sceKernelMapDirectMemory']


def main():
    if len(sys.argv) != 4 or sys.argv[1] != 'build':
        sys.exit(__doc__)
    p, srcdir = Path(sys.argv[2]), Path(sys.argv[3])
    src = srcdir / 'omni_memtrace.c'
    if not src.is_file():
        sys.exit('omni_memtrace.c not found in %s' % srcdir)
    raw = p.read_bytes().decode('utf-8')
    crlf = '\r\n' in raw
    t = raw.replace('\r\n', '\n')
    if MARK in t:
        print('already', p.name)
        return
    edits = [
        ("mine.append(str(o))\n",
         None),   # placeholder: resolved below (the one-submitter compile line is the anchor)
        ("MY_WRAPS += OGS_WRAPS   # OMNI_GPU_ONE_SUBMITTER_V1\n",
         "MY_WRAPS += OGS_WRAPS   # OMNI_GPU_ONE_SUBMITTER_V1\n"
         "MY_WRAPS += OMT_WRAPS   # " + MARK + "\n"),
        ("say('OMNI_GPU_ONE_SUBMITTER_V1 gate: __wrap_ defined for ' + ', '.join(OGS_WRAPS))\n",
         "say('OMNI_GPU_ONE_SUBMITTER_V1 gate: __wrap_ defined for ' + ', '.join(OGS_WRAPS))\n"
         "omt_missing = [n for n in OMT_WRAPS if not re.search(rf' [tT] __wrap_{n}$', ogs_defs, re.M)]   # " + MARK + "\n"
         "if omt_missing: raise SystemExit(f'REFUSED: " + MARK + " wraps missing from the title: {omt_missing}')\n"
         "say('" + MARK + " gate: __wrap_ defined for ' + ', '.join(OMT_WRAPS))\n"),
    ]
    # The compile block goes right after the one-submitter's "OMNI_GPU_ONE_SUBMITTER_V1: AGC driver calls" say() line.
    anchor0 = "say('OMNI_GPU_ONE_SUBMITTER_V1: AGC driver calls go through one lock: ' + ', '.join(OGS_WRAPS))\n"
    edits[0] = (anchor0, anchor0 +
                "# " + MARK + " (test only): log the title's direct-memory calls with their callers (memmap.flag).\n"
                f"OMT_SRC = Path({str(src)!r})\n"
                "o = B / 's1-omni_memtrace.o'\n"
                "run([CC, '-std=gnu11', '-O2', '-Wall', '-Wextra', '-ffunction-sections', '-fdata-sections', '-D__PROSPERO__', "
                "'-c', OMT_SRC, '-o', o], out=B / 's1-omni_memtrace.log')\n"
                "mine.append(str(o))\n"
                f"OMT_WRAPS = {WRAPS!r}\n"
                "say('" + MARK + ": direct-memory calls logged with memmap.flag: ' + ', '.join(OMT_WRAPS))\n")
    for old, _ in edits:
        if t.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r (run apply_one_submitter.py build first)' % (p.name, t.count(old), old[:70]))
    for old, new in edits:
        t = t.replace(old, new, 1)
    p.write_bytes((t.replace('\n', '\r\n') if crlf else t).encode('utf-8'))
    print('patched', p.name, '(%d edits)' % len(edits))


if __name__ == '__main__':
    main()
