#!/usr/bin/env python3
"""OMNI_NO_MINI_MODE_V1 (candidate fix, child engine; .cpp-only so no header-wide rebuild).
JavaScriptCore treats "JIT off" as a low-memory device: VM::isInMiniMode() = !useJIT || forceMiniVMMode. Omni runs the
interpreter by default (no JIT flag), so every page process was in mini mode: every GC a FULL collection (no eden
collections), the mini heap-growth factor (more frequent GCs), synchronous sweeping, and libpas/bmalloc's footprint-first
mini mode for every allocation. The PS5 page process has GBs, and the JIT-on mode (non-mini) already passes the soaks.
Here mini mode follows only Options::forceMiniVMMode() at these sites; unlinked-code-block jettisoning (header-inline
VM::useUnlinkedCodeBlockJettisoning) is left as is."""
import difflib, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; N = HERE.parent
W = Path(sys.argv[1]) / 'webkit/Source'
D = N / 'patches-nomini'; D.mkdir(exist_ok=True)
MARK = 'OMNI_NO_MINI_MODE_V1'; done = []
def edit(rel, a, b):
    p = W / rel; raw = p.read_bytes().decode('utf-8'); crlf = '\r\n' in raw; t = raw.replace('\r\n', '\n')
    if MARK in t and b in t: print('already', rel); return
    n = t.count(a)
    if n != 1: sys.exit(f'{rel}: anchor matched {n} times: {a[:90]!r}')
    s = t.replace(a, b)
    with open(D / (p.name + '.diff'), 'a') as fh: fh.write(''.join(difflib.unified_diff(t.splitlines(True), s.splitlines(True), 'a/' + rel, 'b/' + rel)))
    p.write_bytes((s.replace('\n', '\r\n') if crlf else s).encode('utf-8')); done.append(rel); print('patched', rel)
edit('JavaScriptCore/heap/Collector.cpp', '    if (!Options::useGenerationalGC() || VM::isInMiniMode())\n        return CollectionScope::Full;\n',
     '    if (!Options::useGenerationalGC() || Options::forceMiniVMMode()) // OMNI_NO_MINI_MODE_V1 (was VM::isInMiniMode(): JIT off = mini)\n        return CollectionScope::Full;\n')
edit('JavaScriptCore/heap/Heap.cpp', '    if (VM::isInMiniMode())\n        return Options::miniVMHeapGrowthFactor() * heapSize;\n',
     '    if (Options::forceMiniVMMode()) // OMNI_NO_MINI_MODE_V1\n        return Options::miniVMHeapGrowthFactor() * heapSize;\n')
edit('JavaScriptCore/heap/Heap.cpp', '    return overCriticalMemoryThreshold() || Options::sweepSynchronously() || VM::isInMiniMode();\n',
     '    return overCriticalMemoryThreshold() || Options::sweepSynchronously() || Options::forceMiniVMMode(); // OMNI_NO_MINI_MODE_V1\n')
edit('JavaScriptCore/runtime/InitializeThreading.cpp', '        if (VM::isInMiniMode())\n            WTF::fastEnableMiniMode(Options::forceMiniVMMode());\n',
     '        if (Options::forceMiniVMMode()) // OMNI_NO_MINI_MODE_V1\n            WTF::fastEnableMiniMode(Options::forceMiniVMMode());\n')
edit('JavaScriptCore/heap/FastMallocAlignedMemoryAllocator.cpp', '&& !VM::isInMiniMode();\n', '&& !Options::forceMiniVMMode(); // OMNI_NO_MINI_MODE_V1\n')
print(f'{MARK}: {len(done)} edits')
