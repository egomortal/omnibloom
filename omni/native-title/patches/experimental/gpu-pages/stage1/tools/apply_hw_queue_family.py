#!/usr/bin/env python3
"""OMNI_HW_QUEUE_FAMILY_V1 (2026-11-26, after OMNI_HW_CODEC_SWITCH_V1): VP9 and H.264/HEVC on separate compute queues.

Console (gbp11, OMNI_HW_CODEC_SWITCH_V1 logs): in Omni's process H.264 and HEVC decoders open one after another on the one
compute queue, but once an H.264 decoder has been created (even closed again), VP9's CreateDecoder answers 0x811d0100, and
the other way round; every configuration variant, fresh memory, plenty of address space and flexible memory. Until now Omni
had one compute queue per process (pipe 0 queue 0, never released: release-then-allocate hung in the 2026-10-19 probe).

Now the first family to open keeps pipe 0 queue 0, and the first open of the other family allocates a second queue (nothing
is released): slots tried in order 0/1, 1/0, 0/2, 2/0, 1/1, each logged; none accepted -> the old single queue. App exit
releases the second queue before the first (decoders are closed before either). Families: 0 = H.264 + HEVC, 1 = VP9.
Kill switch: /data/omni/hw-queue-family-off.flag (one queue for everything, as before).
usage: apply_hw_queue_family.py <tree root holding engine/media>"""
import sys
from pathlib import Path

MARK = 'OMNI_HW_QUEUE_FAMILY_V1'
p = Path(sys.argv[1]) / 'engine' / 'media' / 'OmniHwBackend.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('OmniHwBackend.cpp: already', MARK)
    sys.exit(0)
if 'OMNI_HW_CODEC_SWITCH_V1' not in s:
    sys.exit('apply OMNI_HW_CODEC_SWITCH_V1 first')


def sub(old, new):
    global s
    if s.count(old) != 1:
        sys.exit('anchor found %d times: %r' % (s.count(old), old[:100]))
    s = s.replace(old, new, 1)


sub('bool queueReleased = false; // released for app exit; never allocate again\n',
    'bool queueReleased = false; // released for app exit; never allocate again\n'
    '// ' + MARK + ': the second compute queue (the codec family the first queue does not serve)\n'
    'void* queue2 = nullptr; void* queue2Mem = nullptr; size_t queue2MemSize = 0; int64_t queue2MemStart = -1;\n'
    'int queueFamily = -1;      // family the first queue serves (0 H.264/HEVC, 1 VP9); -1 none opened yet\n'
    'bool queue2Tried = false;  // one attempt per process\n')

# the family queue picker goes right after ensureQueue()
sub('    fprintf(stderr, "OMNI HW BACKEND: compute queue pipe 0 queue 0 -> 0x%08x (%p)\\n", unsigned(rc), queue);\n    return rc;\n}\n',
    '    fprintf(stderr, "OMNI HW BACKEND: compute queue pipe 0 queue 0 -> 0x%08x (%p)\\n", unsigned(rc), queue);\n    return rc;\n}\n\n'
    '// ' + MARK + ': the queue for this codec family (after ensureQueue). Never releases anything.\n'
    'void* familyQueue(int family)\n'
    '{\n'
    '    std::lock_guard<std::mutex> lock(queueLock);\n'
    '    if (queueFamily < 0) queueFamily = family;\n'
    '    if (family == queueFamily || queueReleased || access("/data/omni/hw-queue-family-off.flag", F_OK) == 0) return queue;\n'
    '    if (queue2 || queue2Tried) return queue2 ? queue2 : queue;\n'
    '    queue2Tried = true;\n'
    '    static const uint16_t slots[][2] = { { 0, 1 }, { 1, 0 }, { 0, 2 }, { 2, 0 }, { 1, 1 } };\n'
    '    void* const m0 = queueMem; const size_t s0 = queueMemSize; const int64_t st0 = queueMemStart;   // allocQueue writes these\n'
    '    for (const auto& sl : slots) {\n'
    '        void* q = nullptr;\n'
    '        const int rc = allocQueue(sl[0], sl[1], &q);\n'
    '        fprintf(stderr, "OMNI HW BACKEND: ' + MARK + ' second compute queue for %s: pipe %u queue %u -> 0x%08x (%p)\\n",\n'
    '            family == 1 ? "VP9" : "H.264/HEVC", unsigned(sl[0]), unsigned(sl[1]), unsigned(rc), q);\n'
    '        if (!rc && q) { queue2 = q; queue2Mem = queueMem; queue2MemSize = queueMemSize; queue2MemStart = queueMemStart; }\n'
    '        queueMem = m0; queueMemSize = s0; queueMemStart = st0;\n'
    '        if (queue2) break;\n'
    '    }\n'
    '    if (!queue2) fprintf(stderr, "OMNI HW BACKEND: ' + MARK + ' no second compute queue: one queue for both families (as before)\\n");\n'
    '    fflush(stderr);\n'
    '    return queue2 ? queue2 : queue;\n'
    '}\n')

# app exit: the second queue first
sub('    queueReleased = true;\n    if (!queue) return 0;\n',
    '    queueReleased = true;\n'
    '    if (queue2) {   // ' + MARK + '\n'
    '        const int r2 = api.ReleaseComputeQueue ? api.ReleaseComputeQueue(queue2) : -1;\n'
    '        if (!r2 && queue2Mem) { sceKernelMunmap(queue2Mem, queue2MemSize); sceKernelReleaseDirectMemory(queue2MemStart, queue2MemSize); }\n'
    '        queue2 = nullptr; queue2Mem = nullptr; queue2MemSize = 0; queue2MemStart = -1;\n'
    '    }\n'
    '    if (!queue) return 0;\n')

# open(): pick the family's queue
sub('    c.compute_queue = reinterpret_cast<uint64_t>(queue);\n',
    '    void* const useQueue = familyQueue(codec == Codec::VP9 ? 1 : 0);   // ' + MARK + '\n'
    '    c.compute_queue = reinterpret_cast<uint64_t>(useQueue);\n')
sub('            w, h, depth, int(codec), queue, flexibleKiB(), threadCount());\n',
    '            w, h, depth, int(codec), useQueue, flexibleKiB(), threadCount());   // ' + MARK + ': the queue used\n')

p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('OmniHwBackend.cpp: applied', MARK)
