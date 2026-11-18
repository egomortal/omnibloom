#!/usr/bin/env python3
"""OMNI_JSC_DFGFTL_V1 (P1): JavaScriptCore's optimizing tiers, switchable per flag file, in the web process.

The child is built with ENABLE_DFG_JIT=ON and ENABLE_FTL_JIT=ON (omni-jit-ftl/FEASIBILITY.md). Until now
engine/entry/OmniMain.cpp forced JSC_useDFGJIT/JSC_useFTLJIT=false (after jsc-env.txt, so nothing could turn them on).
With this patch, inside the existing JIT-on branch (OMNI_JIT_DEFAULT_ON_V1: on unless /data/omni/jsc-jit-off.flag):
  /data/omni/jsc-dfg.flag              -> JSC_useDFGJIT=true            (absent: false, i.e. exactly rc6's tiers)
  /data/omni/jsc-ftl.flag (+ dfg flag) -> JSC_useFTLJIT=true            (FTL needs the DFG; alone it does nothing)
  always: JSC_usePollingTraps=true (a DFG build no longer forces polling; the signal/hlt trap path reads the ucontext,
          whose layout differs on this firmware), JSC_numberOfDFGCompilerThreads=1, JSC_numberOfFTLCompilerThreads=1
  /data/omni/jsc-jit-pool-mb.txt (16..256, default 64) -> JSC_jitMemoryReservationSize (OSAllocatorPlayStation caps 256 MB)
The "jit: on (baseline" log prefix is kept (child_build.py's receipt looks for it) and now names the tiers.
jsc-env.txt (read earlier) can still set keys this block does not set (tier-up thresholds etc.).

usage: apply_jscftl_tiers.py <tree root containing engine/>     anchored, every anchor checked before writing, idempotent.
Backups: $OMNI_PATCH_BACKUP_DIR/<relpath>.before-<MARK> if set, else <file>.before-<MARK>.
Output lines: "applied OMNI_JSC_DFGFTL_V1 <relpath>" | "already OMNI_JSC_DFGFTL_V1 <relpath>", last line applied|already.
"""
import os, sys
from pathlib import Path

MARK = 'OMNI_JSC_DFGFTL_V1'

def patch_files(root, plan):
    """plan: [(relpath, [(old, new), ...])]. Checks every anchor of every file first, then writes."""
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

patch_files(root, [('engine/entry/OmniMain.cpp', [
    ('        setenv("JSC_useDFGJIT", "false", 1);\n'
     '        setenv("JSC_useFTLJIT", "false", 1);\n',
     '        // OMNI_JSC_DFGFTL_V1: the optimizing tiers are built in (ENABLE_DFG_JIT/ENABLE_FTL_JIT) and opt-in per flag file,\n'
     '        // read here at web-process start: /data/omni/jsc-dfg.flag -> DFG; with it, /data/omni/jsc-ftl.flag -> FTL as well.\n'
     '        const bool omniDfg = !access("/data/omni/jsc-dfg.flag", F_OK);\n'
     '        const bool omniFtl = omniDfg && !access("/data/omni/jsc-ftl.flag", F_OK);\n'
     '        setenv("JSC_useDFGJIT", omniDfg ? "true" : "false", 1);\n'
     '        setenv("JSC_useFTLJIT", omniFtl ? "true" : "false", 1);\n'
     '        // Polling VM traps: a DFG build no longer forces them, and the signal + hlt trap path reads the ucontext\n'
     '        // (OMNI_JSC_UCONTEXT_V1). One DFG and one FTL compiler thread (FTL defaults to up to 7).\n'
     '        setenv("JSC_usePollingTraps", "true", 1);\n'
     '        setenv("JSC_numberOfDFGCompilerThreads", "1", 1);\n'
     '        setenv("JSC_numberOfFTLCompilerThreads", "1", 1);\n'),
    ('        setenv("JSC_jitMemoryReservationSize", "67108864", 1);   // 64 MB executable pool (OSAllocatorPlayStation caps it at 256 MB)\n',
     '        // OMNI_JSC_DFGFTL_V1: executable pool size in MB from /data/omni/jsc-jit-pool-mb.txt (16..256; default 64;\n'
     '        // OSAllocatorPlayStation caps the pool at 256 MB). The V4 dual mapping was console-proven at 64 MB.\n'
     '        unsigned omniPoolMb = 64;\n'
     '        if (FILE* poolFile = fopen("/data/omni/jsc-jit-pool-mb.txt", "r")) {\n'
     '            unsigned value = 0;\n'
     '            if (fscanf(poolFile, "%u", &value) == 1 && value >= 16 && value <= 256)\n'
     '                omniPoolMb = value;\n'
     '            else\n'
     '                fprintf(stderr, "jit: /data/omni/jsc-jit-pool-mb.txt ignored (wants 16..256); pool stays 64 MB (OMNI_JSC_DFGFTL_V1)\\n");\n'
     '            fclose(poolFile);\n'
     '        }\n'
     '        char omniPoolBytes[24];\n'
     '        snprintf(omniPoolBytes, sizeof(omniPoolBytes), "%llu", static_cast<unsigned long long>(omniPoolMb) << 20);\n'
     '        setenv("JSC_jitMemoryReservationSize", omniPoolBytes, 1);\n'),
    ('        fprintf(stderr, "jit: on (baseline + regexp, 64 MB pool; default, off with /data/omni/jsc-jit-off.flag) (OMNI_JIT_DEFAULT_ON_V1)\\n");\n',
     '        fprintf(stderr, "jit: on (baseline%s%s + regexp, %u MB pool, polling traps; default, off with /data/omni/jsc-jit-off.flag) (OMNI_JIT_DEFAULT_ON_V1, OMNI_JSC_DFGFTL_V1)\\n",\n'
     '            omniDfg ? " + DFG" : "", omniFtl ? " + FTL" : "", omniPoolMb);\n'),
])])
