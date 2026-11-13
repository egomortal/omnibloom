#!/usr/bin/env python3
"""OMNI_JIT_DEFAULT_ON_V1: JavaScriptCore's JIT is on by default (it was opt-in, "faster, less safe").

Why now: OMNI_JSC_JIT_V4 gives the JIT pool W^X without runtime permission changes (an RX view + an RW alias of one
shared-memory object), and on the console it matched V3's speed on six sites and passed the old JIT's soaks
(20-min YouTube 0 stalls, 9-min JS soak 0 errors), 2026-11-11. The child must carry V4 (rc6) for this to be shipped.

Switch: on unless /data/omni/jsc-jit-off.flag exists. The old opt-in /data/omni/jsc-jit.flag is no longer needed
(and never turns it off). Settings > "JavaScript JIT" writes / removes jsc-jit-off.flag.

  apply_jit_default_on.py --child <engine tree>   engine/entry/OmniMain.cpp      (the page process's JSC_* setup)
  apply_jit_default_on.py --title <engine tree>   engine/entry/OmniBrowserSettings.h (the Settings row)
Anchored, once each; idempotent.
"""
import sys
from pathlib import Path
MARK = 'OMNI_JIT_DEFAULT_ON_V1'
mode, root = sys.argv[1], Path(sys.argv[2])

def patch(rel, edits):
    p = root / rel
    s = p.read_text(encoding='utf-8')
    if MARK in s:
        print('already applied'); return
    for old, new in edits:
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (rel, s.count(old), old[:80]))
        s = s.replace(old, new, 1)
    p.write_text(s, encoding='utf-8')
    print('applied')

if mode == '--child':
    patch('engine/entry/OmniMain.cpp', [
        ('    if (!access("/data/omni/jsc-jit.flag", F_OK)) {\n',
         '    // OMNI_JIT_DEFAULT_ON_V1: on by default since the W^X pool (OMNI_JSC_JIT_V4); off with /data/omni/jsc-jit-off.flag.\n'
         '    if (access("/data/omni/jsc-jit-off.flag", F_OK)) {\n'),
        ('        fprintf(stderr, "jit: on (baseline + regexp, 64 MB pool, pages flip RX<->RWX while writing code)\\n");\n',
         '        fprintf(stderr, "jit: on (baseline + regexp, 64 MB pool; default, off with /data/omni/jsc-jit-off.flag) (OMNI_JIT_DEFAULT_ON_V1)\\n");\n'),
        ('        fprintf(stderr, "jit: off (interpreter)\\n");\n',
         '        fprintf(stderr, "jit: off (interpreter): /data/omni/jsc-jit-off.flag (OMNI_JIT_DEFAULT_ON_V1)\\n");\n'),
    ])
elif mode == '--title':
    patch('engine/entry/OmniBrowserSettings.h', [
        ('static bool omniFxJitOn() { return !access("/data/omni/jsc-jit.flag", F_OK); }\n',
         '// OMNI_JIT_DEFAULT_ON_V1: on unless /data/omni/jsc-jit-off.flag (the W^X pool, OMNI_JSC_JIT_V4, made it the default).\n'
         'static bool omniFxJitOn() { return access("/data/omni/jsc-jit-off.flag", F_OK) != 0; }\n'),
        ('    add(omniFxSetJit, "JavaScript JIT (experimental: faster, less safe)", omniFxJitOn() ? "On" : "Off", true); // OMNI_JSC_JIT_V1\n',
         '    add(omniFxSetJit, "JavaScript JIT (faster pages)", omniFxJitOn() ? "On" : "Off", true); // OMNI_JSC_JIT_V1 / OMNI_JIT_DEFAULT_ON_V1\n'),
        ('        if (omniFxJitOn()) unlink("/data/omni/jsc-jit.flag");\n'
         '        else if (FILE* f = fopen("/data/omni/jsc-jit.flag", "w")) { fputs("1\\n", f); fclose(f); }\n',
         '        if (!omniFxJitOn()) unlink("/data/omni/jsc-jit-off.flag");   // OMNI_JIT_DEFAULT_ON_V1: off -> on\n'
         '        else if (FILE* f = fopen("/data/omni/jsc-jit-off.flag", "w")) { fputs("1\\n", f); fclose(f); }   // on -> off\n'),
    ])
else:
    sys.exit('usage: apply_jit_default_on.py --child|--title <engine tree>')
