#!/usr/bin/env python3
"""OMNI_JSC_COMPILER_STACK_V1 (P3): 2 MB stacks for JavaScriptCore's compiler threads on the PS5.

Omni caps every default-stack thread at 512 KB (WTF/wtf/posix/ThreadingPOSIX.cpp, [omni-default-stack]), and
WTF::stackSize() (WTF/wtf/Threading.cpp) only gives ThreadType::JavaScript its own size on PlayStation. Upstream Linux
compiler threads run on the 8 MB default; the DFG phases and B3/Air (FTL) on large functions (YouTube's player bundle)
are untested at 512 KB. ThreadType::Compiler threads (JITWorklistThread: baseline/DFG/FTL plans; Wasm worklist;
SequesteredAutomaticThread) now ask for 2 MB explicitly (StackAllocationSpecification::RequestSize, which the
512 KB cap does not touch). Baseline already uses these threads, so it gets the bigger stack too (about 3 threads).

usage: apply_jscftl_compiler_stack.py <tree root containing webkit/>   anchored, every anchor checked, idempotent.
Backups: $OMNI_PATCH_BACKUP_DIR/<relpath>.before-<MARK> if set, else <file>.before-<MARK>.
"""
import os, sys
from pathlib import Path

MARK = 'OMNI_JSC_COMPILER_STACK_V1'

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

patch_files(root, [('webkit/Source/WTF/wtf/Threading.cpp', [
    ('#if PLATFORM(PLAYSTATION)\n'
     '    if (threadType == ThreadType::JavaScript)\n'
     '        return 512 * KB;\n',
     '#if PLATFORM(PLAYSTATION)\n'
     '    if (threadType == ThreadType::JavaScript)\n'
     '        return 512 * KB;\n'
     '    // OMNI_JSC_COMPILER_STACK_V1: JIT compiler threads (DFG phases, B3/Air for the FTL) get 2 MB, not the 512 KB\n'
     '    // cap Omni puts on default-stack threads (posix/ThreadingPOSIX.cpp, [omni-default-stack]).\n'
     '    if (threadType == ThreadType::Compiler)\n'
     '        return 2 * MB;\n'),
])])
