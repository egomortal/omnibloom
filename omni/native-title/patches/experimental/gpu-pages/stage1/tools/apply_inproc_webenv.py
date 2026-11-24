#!/usr/bin/env python3
"""OMNI_INPROC_WEBENV_V1 (2026-11-23): single-process plan Phase 3 - give the in-process WebProcess the JavaScript JIT.

The title's main() forces JSC_useJIT=false / JSC_useRegExpJIT=false at startup ("no process uses the JIT unless
runChild() turns it on for a web process"); JavaScriptCore reads its options ONCE per process, when WebKit first
initialises it in the UI. A WebProcess started inside the title (OMNI_INPROC_NET_V1 + inproc-web.flag) therefore ran
the interpreter only, and YouTube rejected every playback token (BotGuard) -> OMNI_YTGUARD reloaded the page every
~20 s (console 2026-11-23, 25955623, Lytiw: "reloadn rejected" x5, playback in ~12 s bursts). The child gets its JIT
from runChild().

The title binary is built with the baseline + regexp JIT (no DFG/FTL - those are child-build only for now), so when
/data/omni/inproc-web.flag exists this turns on exactly those tiers at the same point main() used to turn them off
(baseline + regexp, 64 MB pool), like the child's OMNI_JSC_JIT_V1 path. No flag -> the original code.
fopen, not access(): in this unit access() is ps5_access, which does not see /data/omni flags.
usage: apply_inproc_webenv.py <engine/entry/OmniMain.cpp>"""
import sys
from pathlib import Path

MARK = 'OMNI_INPROC_WEBENV_V1'
p = Path(sys.argv[1])
# --ftl (2026-11-23, the title built with ENABLE_DFG_JIT/ENABLE_FTL_JIT): the child's tiers too, with its settings
# (OMNI_JSC_DFGFTL_V1 + _DEFAULT_ON_V1): DFG + FTL on, polling traps (the signal trap path reads the ucontext), 1+1 compiler threads.
FTL = len(sys.argv) > 2 and sys.argv[2] == '--ftl'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)

old = ('    // OMNI_JSC_JIT_V1: no process uses the JIT unless runChild() turns it on for a web process.\n'
       '    setenv("JSC_useJIT", "false", 1);\n'
       '    setenv("JSC_useRegExpJIT", "false", 1);\n')
new = ('    // OMNI_JSC_JIT_V1: no process uses the JIT unless runChild() turns it on for a web process.\n'
       '    // ' + MARK + ': ...or the WebProcess runs inside this process (inproc-web.flag): JSC reads its options once,\n'
       '    // so the in-process page engine gets the tiers this binary has (baseline + regexp) from here.\n'
       '    if (FILE* omniWebFlag = fopen("/data/omni/inproc-web.flag", "r")) {\n'
       '        fclose(omniWebFlag);\n'
       '        setenv("JSC_useJIT", "true", 1);\n'
       '        setenv("JSC_useBaselineJIT", "true", 1);\n'
       '        setenv("JSC_useRegExpJIT", "true", 1);\n'
       + ('        setenv("JSC_useDFGJIT", "true", 1);\n'
          '        setenv("JSC_useFTLJIT", "true", 1);\n'
          '        setenv("JSC_usePollingTraps", "true", 1);\n'
          '        setenv("JSC_numberOfDFGCompilerThreads", "1", 1);\n'
          '        setenv("JSC_numberOfFTLCompilerThreads", "1", 1);\n' if FTL else
          '        setenv("JSC_useDFGJIT", "false", 1);\n'
          '        setenv("JSC_useFTLJIT", "false", 1);\n') +
       '        setenv("JSC_useBBQJIT", "false", 1);\n'
       '        setenv("JSC_useOMGJIT", "false", 1);\n'
       '        setenv("JSC_jitMemoryReservationSize", "67108864", 1);\n'
       '        omni_launcher_trace("jit: on for the in-process page engine (' + ('baseline + DFG + FTL + regexp, polling traps' if FTL else 'baseline + regexp') + ', 64 MB pool) (' + MARK + ')\\n");\n'
       '    } else {\n'
       '        setenv("JSC_useJIT", "false", 1);\n'
       '        setenv("JSC_useRegExpJIT", "false", 1);\n'
       '    }\n')
if s.count(old) != 1:
    sys.exit('%s: anchor found %d times' % (p.name, s.count(old)))
s = s.replace(old, new, 1)
# one early spare (for the NetworkProcess) instead of two in in-process page engine mode; omniInprocWebMode() comes
# from OMNI_INPROC_NET_V1 in omni-process-launcher-v2.inc, which OmniMain.cpp #includes near its top
sp = '                omni_launcher_prespawn(kSelf[i], 2);\n'
if s.count(sp) != 1:
    sys.exit('%s: prespawn anchor found %d times' % (p.name, s.count(sp)))
s = s.replace(sp, '                omni_launcher_prespawn(kSelf[i], omniInprocWebMode() ? 1 : 2);   // ' + MARK + '\n', 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
