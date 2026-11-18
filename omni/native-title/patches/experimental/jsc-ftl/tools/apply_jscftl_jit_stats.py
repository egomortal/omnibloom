#!/usr/bin/env python3
"""OMNI_JSC_JIT_STATS_V1 (P4): one stderr line every 10 s with the JIT pool and tier counters (test diagnostics).

  jit stats: pool A/L/R KB (allocated / tier-up limit / reserved); compiled baseline N dfg N ftl N failed N;
             osr-exit thunks dfg N ftl N; jettisons N (speculation N) (OMNI_JSC_JIT_STATS_V1)

JavaScriptCore side (counters are relaxed atomics, a few increments per compile; no cost on the hot path):
  jit/ExecutableAllocator.cpp      the counters, omniJitStatsCount(), omniJitStatsLine() (pool bytes from the
                                   fixed VM pool: racy byte-count reads, diagnostics only; zeros before JSC starts)
  jit/JITPlan.cpp                  every finished plan by path: baseline / DFG / FTL / failed (cancelled not counted)
  dfg/DFGOSRExit.cpp               each DFG OSR-exit thunk compiled (first time an exit site is taken)
  ftl/FTLOSRExitCompiler.cpp       each FTL OSR-exit thunk compiled
  bytecode/CodeBlock.cpp           every CodeBlock::jettison, and those for speculation failures (OSR-exit loops show
                                   up as jettisons (speculation) that keep rising on a warm page)
Child side (engine/entry/OmniMain.cpp): a detached 128 KB thread prints the line every 10 s. Web processes only, and
only with /data/omni/jsc-dfg.flag or /data/omni/jsc-jit-stats.flag; otherwise nothing runs.

usage: apply_jscftl_jit_stats.py <tree root containing webkit/ and engine/>   every anchor of every file checked
before any write; per-file idempotent ("already" for files carrying the marker).
Backups: $OMNI_PATCH_BACKUP_DIR/<relpath>.before-<MARK> if set, else <file>.before-<MARK>.
"""
import os, sys
from pathlib import Path

MARK = 'OMNI_JSC_JIT_STATS_V1'

def patch_files(root, plan):
    todo, results = [], []
    for rel, edits in plan:
        p = root / rel
        if not p.is_file():
            sys.exit('%s: file missing' % p)
        s = p.read_text(encoding='utf-8')
        if MARK in s:
            results.append(('already', rel)); continue
        t = s
        for old, new in edits:
            n = t.count(old)
            if n != 1:
                sys.exit('%s: anchor found %d times: %r' % (rel, n, old[:100]))
            t = t.replace(old, new, 1)
        if MARK not in t:
            sys.exit('%s: patched text lacks the marker %s' % (rel, MARK))
        todo.append((rel, p, s, t))
    for rel, p, s, t in todo:
        bdir = os.environ.get('OMNI_PATCH_BACKUP_DIR')
        b = (Path(bdir) / (rel + '.before-' + MARK)) if bdir else p.with_name(p.name + '.before-' + MARK)
        b.parent.mkdir(parents=True, exist_ok=True)
        if not b.exists():
            b.write_text(s, encoding='utf-8')
        p.write_text(t, encoding='utf-8')
        results.append(('applied', rel))
    for state, rel in results:
        print('%s %s %s' % (state, MARK, rel))
    print('applied' if any(r[0] == 'applied' for r in results) else 'already')

if len(sys.argv) != 2:
    sys.exit(__doc__)
root = Path(sys.argv[1])
J = 'webkit/Source/JavaScriptCore/'
DECL = ('#include "config.h"\n',
        '#include "config.h"\n'
        'extern "C" void omniJitStatsCount(unsigned which); // OMNI_JSC_JIT_STATS_V1 (jit/ExecutableAllocator.cpp)\n')

patch_files(root, [
    (J + 'jit/ExecutableAllocator.cpp', [
        ('bool ExecutableAllocator::underMemoryPressure()\n',
         '// OMNI_JSC_JIT_STATS_V1: tier counters (JITPlan, DFG/FTL OSR-exit thunks, CodeBlock::jettison) and the pool use,\n'
         '// printed every 10 s by the child\'s stats thread (engine/entry/OmniMain.cpp). Diagnostics only.\n'
         'static std::atomic<unsigned long long> s_omniJitStats[8];\n'
         'extern "C" void omniJitStatsCount(unsigned which)\n'
         '{\n'
         '    if (which < 8)\n'
         '        s_omniJitStats[which].fetch_add(1, std::memory_order_relaxed);\n'
         '}\n'
         '\n'
         'extern "C" int omniJitStatsLine(char* buffer, size_t size)\n'
         '{\n'
         '    unsigned long long n[8];\n'
         '    for (unsigned i = 0; i < 8; ++i)\n'
         '        n[i] = s_omniJitStats[i].load(std::memory_order_relaxed);\n'
         '    size_t allocated = 0;\n'
         '    size_t available = 0;\n'
         '    size_t reserved = 0;\n'
         '    if (FixedVMPoolExecutableAllocator* allocator = g_jscConfig.fixedVMPoolExecutableAllocator) {\n'
         '        allocated = allocator->bytesAllocated(); // unlocked read of byte counts: diagnostics only\n'
         '        available = allocator->bytesAvailable();\n'
         '        reserved = allocator->bytesReserved();\n'
         '    }\n'
         '    return snprintf(buffer, size, "jit stats: pool %zu/%zu/%zu KB (allocated/tier-up limit/reserved); compiled baseline %llu dfg %llu ftl %llu failed %llu; "\n'
         '        "osr-exit thunks dfg %llu ftl %llu; jettisons %llu (speculation %llu) (OMNI_JSC_JIT_STATS_V1)",\n'
         '        allocated >> 10, available >> 10, reserved >> 10, n[0], n[1], n[2], n[3], n[4], n[5], n[6], n[7]);\n'
         '}\n'
         '\n'
         'bool ExecutableAllocator::underMemoryPressure()\n'),
    ]),
    (J + 'jit/JITPlan.cpp', [
        DECL,
        ('    RELEASE_ASSERT((path == CancelPath) == (m_stage == JITPlanStage::Canceled));\n',
         '    RELEASE_ASSERT((path == CancelPath) == (m_stage == JITPlanStage::Canceled));\n'
         '    // OMNI_JSC_JIT_STATS_V1: 0 baseline, 1 DFG, 2 FTL, 3 failed (cancelled plans are not counted).\n'
         '    omniJitStatsCount(path == BaselinePath ? 0 : path == DFGPath ? 1 : path == FTLPath ? 2 : path == FailPath ? 3 : 8);\n'),
    ]),
    (J + 'dfg/DFGOSRExit.cpp', [
        DECL,
        ('        LinkBuffer patchBuffer(jit, codeBlock, LinkBuffer::Profile::DFGOSRExit);\n',
         '        omniJitStatsCount(4); // OMNI_JSC_JIT_STATS_V1: a DFG OSR-exit thunk\n'
         '        LinkBuffer patchBuffer(jit, codeBlock, LinkBuffer::Profile::DFGOSRExit);\n'),
    ]),
    (J + 'ftl/FTLOSRExitCompiler.cpp', [
        DECL,
        ('    LinkBuffer patchBuffer(jit, codeBlock, LinkBuffer::Profile::FTLOSRExit);\n',
         '    omniJitStatsCount(5); // OMNI_JSC_JIT_STATS_V1: an FTL OSR-exit thunk\n'
         '    LinkBuffer patchBuffer(jit, codeBlock, LinkBuffer::Profile::FTLOSRExit);\n'),
    ]),
    (J + 'bytecode/CodeBlock.cpp', [
        DECL,
        ('void CodeBlock::jettison(Profiler::JettisonReason reason, ReoptimizationMode mode, const FireDetail* detail)\n'
         '{\n',
         'void CodeBlock::jettison(Profiler::JettisonReason reason, ReoptimizationMode mode, const FireDetail* detail)\n'
         '{\n'
         '#if ENABLE(JIT)\n'
         '    // OMNI_JSC_JIT_STATS_V1: 6 every jettison, 7 those for speculation failures (OSR-exit driven).\n'
         '    omniJitStatsCount(6);\n'
         '    if (Profiler::isSpeculationFailure(reason))\n'
         '        omniJitStatsCount(7);\n'
         '#endif\n'),
    ]),
    ('engine/entry/OmniMain.cpp', [
        ('static int runChild(int argc, char** args)\n',
         '// OMNI_JSC_JIT_STATS_V1: the JIT stats line every 10 s (JavaScriptCore jit/ExecutableAllocator.cpp builds it).\n'
         'extern "C" int omniJitStatsLine(char* buffer, size_t size);\n'
         'static void* omniJitStatsThread(void*)\n'
         '{\n'
         '    for (;;) {\n'
         '        sleep(10);\n'
         '        char line[384];\n'
         '        if (omniJitStatsLine(line, sizeof(line)) > 0)\n'
         '            fprintf(stderr, "%s\\n", line);\n'
         '    }\n'
         '    return nullptr;\n'
         '}\n'
         '\n'
         'static int runChild(int argc, char** args)\n'),
        ('#if ENABLE(MEDIA_SOURCE)\n'
         '    // OMNI_MEDIACAPS_V1: decodingInfo factory, installed before any page can ask.\n',
         '    // OMNI_JSC_JIT_STATS_V1: only with the DFG flag or /data/omni/jsc-jit-stats.flag (test diagnostics).\n'
         '    if (!access("/data/omni/jsc-dfg.flag", F_OK) || !access("/data/omni/jsc-jit-stats.flag", F_OK)) {\n'
         '        pthread_attr_t omniStatsAttr;\n'
         '        pthread_attr_init(&omniStatsAttr);\n'
         '        pthread_attr_setstacksize(&omniStatsAttr, 128 * 1024);\n'
         '        pthread_attr_setdetachstate(&omniStatsAttr, PTHREAD_CREATE_DETACHED);\n'
         '        pthread_t omniStatsThread;\n'
         '        int omniStatsError = pthread_create(&omniStatsThread, &omniStatsAttr, omniJitStatsThread, nullptr);\n'
         '        pthread_attr_destroy(&omniStatsAttr);\n'
         '        fprintf(stderr, "jit stats: %s (OMNI_JSC_JIT_STATS_V1)\\n", omniStatsError ? "thread failed" : "every 10 s");\n'
         '    }\n'
         '#if ENABLE(MEDIA_SOURCE)\n'
         '    // OMNI_MEDIACAPS_V1: decodingInfo factory, installed before any page can ask.\n'),
    ]),
])
