#!/usr/bin/env python3
"""OMNI_HEAP_CAP_V1 (s3.4f, child engine, Heap.cpp only; applied on top of OMNI_NO_MINI_MODE_V1).
With mini mode gone the collector uses the normal heap-growth rule. On this console WTF::memoryFootprint() reads 0 and
percentAvailableMemoryInUse() is therefore 0, so proportionalHeapSize() always picks smallHeapGrowthFactor (2x the live
heap after a full GC) and the critical-memory path never trips: the JS heap's next-GC target is unbounded.
The guard: once the 2x target passes OMNI_HEAP_CAP (256 MB) the target becomes max(256 MB, 1.2x live heap) -- the
mini-mode growth factor -- so the heap above 256 MB grows the way it did in mini mode (more frequent full GCs), while
smaller heaps keep the fast generational behaviour. Eden/full scope, sweeping and malloc behaviour are unchanged."""
import difflib, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; N = HERE.parent
W = Path(sys.argv[1]) / 'webkit/Source'
D = N / 'patches-heapcap'; D.mkdir(exist_ok=True)
MARK = 'OMNI_HEAP_CAP_V1'
def edit(rel, a, b):
    p = W / rel; raw = p.read_bytes().decode('utf-8'); crlf = '\r\n' in raw; t = raw.replace('\r\n', '\n')
    if MARK in t and b in t: print('already', rel); return
    n = t.count(a)
    if n != 1: sys.exit(f'{rel}: anchor matched {n} times: {a[:90]!r}')
    s = t.replace(a, b)
    with open(D / (p.name + '.diff'), 'a') as fh: fh.write(''.join(difflib.unified_diff(t.splitlines(True), s.splitlines(True), 'a/' + rel, 'b/' + rel)))
    p.write_bytes((s.replace('\n', '\r\n') if crlf else s).encode('utf-8')); print('patched', rel)
edit('JavaScriptCore/heap/Heap.cpp',
     'void Heap::updateAllocationLimits()\n{\n',
     '// OMNI_HEAP_CAP_V1: memoryFootprint() reads 0 on this console, so the growth rule never leaves 2x; above 256 MB the\n'
     '// next-GC target grows like mini mode (1.2x the live heap) instead.\n'
     'static size_t omniCappedHeapTarget(size_t heapSize, size_t proposed)\n{\n'
     '    constexpr size_t omniHeapCap = 256 * MB;\n'
     '    if (proposed <= omniHeapCap || Options::forceMiniVMMode())\n        return proposed;\n'
     '    return std::max(omniHeapCap, static_cast<size_t>(Options::miniVMHeapGrowthFactor() * heapSize));\n}\n\n'
     'void Heap::updateAllocationLimits()\n{\n')
edit('JavaScriptCore/heap/Heap.cpp',
     '        m_maxHeapSize = std::max(m_minBytesPerCycle, proportionalHeapSize(currentHeapSize, m_growthMode, m_ramSize));\n',
     '        m_maxHeapSize = std::max(m_minBytesPerCycle, omniCappedHeapTarget(currentHeapSize, proportionalHeapSize(currentHeapSize, m_growthMode, m_ramSize))); // OMNI_HEAP_CAP_V1\n')
print('OMNI_HEAP_CAP_V1: 2 edits')
