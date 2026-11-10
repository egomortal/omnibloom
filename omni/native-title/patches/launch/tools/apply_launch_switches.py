#!/usr/bin/env python3
"""omni-launch: kill switches that REACH the child, added on top of the component patches (anchored, exactly once,
idempotent, CRLF kept). The child engine only receives OMNI_RASTER_* keys from /data/omni/raster-env.txt
(engine/entry/OmniMain.cpp runChild), so environment switches named otherwise were dead as shipped. Flag files under
/data/omni are read with access() by the child's own processes, as jank.flag / ytprof.flag / malloc-mini-off.flag are.

  --ack   OMNI_ACK_SWITCH_V1   (after OMNI_ACK_V1, child)  /data/omni/ack-pace-off.flag = OMNI_ACK_PACE=0 (upstream gate);
          OMNI_RASTER_ACK_PACE / OMNI_RASTER_ACK_CREDITS / OMNI_RASTER_ACK_HZ accepted (and still the OMNI_ACK_* names).
          Also rewrites <ack patches dir>/ack-policy.inc (--ack-inc=DIR) so the host gates compile the shipped text.
  --net   OMNI_NET5_SWITCH_V1  (after omni-net apply_net)  /data/omni/net5-off.flag = every net-off-<name>.flag at once
          (cachemodel castore warm prefetch preconnect h2 br prio jscache dohwarm diskcap): the release network path.
  --s34g  OMNI_S34G_SWITCH_V1  (after s3.4g)               /data/omni/s34g-off.flag = stock JSC: the five
          OMNI_NO_MINI_MODE_V1 sites follow VM::isInMiniMode() again, OMNI_HEAP_CAP_V1 returns the stock target, and
          the two OMNI_MALLOC_MINI_V1 allocator gates take their stock branch (as malloc-mini-off.flag absent).
  --check-stock=<s3 root>   with --s34g: prove that the flag-present projection of every edited condition is the
          stock s3 condition, and the flag-absent projection is the s3.4g text (prints PASS/FAIL, exit 1 on FAIL).
usage: apply_launch_switches.py <tree> [--ack --ack-inc=DIR] [--net] [--s34g [--check-stock=S3]]"""
import re, sys
from pathlib import Path

T = Path(sys.argv[1]); W = T / 'webkit/Source'; A = sys.argv[2:]
arg = lambda k: next((a.split('=', 1)[1] for a in A if a.startswith(k + '=')), None)
done = []

def edit_text(t, ops, where):
    for a, b in ops:
        n = t.count(a)
        if n != 1: sys.exit(f'{where}: anchor found {n} times: {a[:100]!r}')
        t = t.replace(a, b)
    return t

def edit(path, marker, ops):
    p = Path(path); raw = p.read_bytes().decode('utf-8'); crlf = '\r\n' in raw; t = raw.replace('\r\n', '\n')
    if marker in t: print('already', p.name); return
    s = edit_text(t, ops, p.name)
    p.write_bytes((s.replace('\n', '\r\n') if crlf else s).encode('utf-8')); done.append(p.name); print('patched', p.name, marker)

# ------------------------------------------------------------------ ACK
ACK_HELPER = r'''// OMNI_ACK_SWITCH_V1 (omni-launch): the child copies only OMNI_RASTER_* keys out of /data/omni/raster-env.txt, so
// OMNI_ACK_PACE / _CREDITS / _HZ never reached it. Accept OMNI_RASTER_ACK_<X> first, then OMNI_ACK_<X>, and a flag file.
#ifndef OMNI_ACK_PACE_OFF_FLAG
#define OMNI_ACK_PACE_OFF_FLAG "/data/omni/ack-pace-off.flag"
#endif
static const char* omniAckEnv(const char* name)
{
    char raster[64];
    snprintf(raster, sizeof raster, "OMNI_RASTER_%s", name + 5); // OMNI_ACK_PACE -> OMNI_RASTER_ACK_PACE
    const char* value = getenv(raster);
    return (value && value[0]) ? value : getenv(name);
}

static unsigned omniAckEnvUnsigned(const char* name, unsigned fallback, unsigned low, unsigned high)
{
    const char* value = omniAckEnv(name);'''
ACK_OPS = [
    ('#include <stdlib.h>\n#endif\n\nstruct OmniAckPolicy {', '#include <stdlib.h>\n#include <unistd.h> // OMNI_ACK_SWITCH_V1: access()\n#endif\n\nstruct OmniAckPolicy {'),
    ('static unsigned omniAckEnvUnsigned(const char* name, unsigned fallback, unsigned low, unsigned high)\n{\n    const char* value = getenv(name);', ACK_HELPER),
    ('        const char* pace = getenv("OMNI_ACK_PACE");\n        const bool off = pace && pace[0] == \'0\' && !pace[1];',
     '        const char* pace = omniAckEnv("OMNI_ACK_PACE");\n'
     '        const bool offFlag = access(OMNI_ACK_PACE_OFF_FLAG, F_OK) == 0; // OMNI_ACK_SWITCH_V1\n'
     '        const bool off = offFlag || (pace && pace[0] == \'0\' && !pace[1]);'),
    (r'            fprintf(stderr, "OMNI ACK: OMNI_ACK_V1 off (OMNI_ACK_PACE=0): the upstream one-update-in-flight gate\n");',
     r'            fprintf(stderr, "OMNI ACK: OMNI_ACK_V1 off (%s): the upstream one-update-in-flight gate\n", offFlag ? OMNI_ACK_PACE_OFF_FLAG : "OMNI_ACK_PACE=0");'),
]
if '--ack' in A:
    edit(W / 'WebKit/WebProcess/WebPage/CoordinatedGraphics/DrawingAreaCoordinatedGraphics.cpp', 'OMNI_ACK_SWITCH_V1', ACK_OPS)
    inc = arg('--ack-inc')
    if inc:
        p = Path(inc) / 'ack-policy.inc'; t = p.read_text()
        if 'OMNI_ACK_SWITCH_V1' not in t: p.write_text(edit_text(t, ACK_OPS, 'ack-policy.inc')); print('patched ack-policy.inc (shipped text for the gates)')

# ------------------------------------------------------------------ NET
NET_OPS = [('        x = !::access(path, F_OK); v[id] = x;\n',
            '        x = !::access(path, F_OK) || !::access("/data/omni/net5-off.flag", F_OK); v[id] = x; // OMNI_NET5_SWITCH_V1: one flag = every net5 fix off\n')]
# OMNI_NET_SWITCH_LOG_V1: omni_net_off(id) reads (and logs) a flag only when that id's code path runs. cachemodel is read
# only when the requested model is DocumentBrowser, preconnect only when the page issues a preconnect -- so with the flag
# present neither ever logged on the console. Read every flag once at curl start-up (network process) and at
# WebProcess::setCacheModel (web process), log the requested -> applied cache model, and log the first preconnect.
ANNOUNCE = r'''// OMNI_NET_SWITCH_LOG_V1 (omni-launch): read every net-off flag once per process at start-up, so each switch that is on
// logs "OMNI NET kill switch on: <name>" even when its code path never runs in that session (cachemodel, preconnect).
void omni_net_announce()
{
    static std::atomic<bool> done { false };
    if (done.exchange(true))
        return;
    for (int i = 0; i < (int)(sizeof(omniNetOffNames) / sizeof(omniNetOffNames[0])); ++i)
        omni_net_off(i);
    if (!::access("/data/omni/net5-off.flag", F_OK))
        fprintf(stderr, "OMNI NET kill switch on: net5 (every net-off switch)\n");
}
void omni_net_note(const char* line) { fprintf(stderr, "%s\n", line); }
'''
NETLOG = {
 'WebCore/platform/network/curl/CurlContext.cpp': [
   ('extern "C" bool omni_net_off(int);\n', 'extern "C" bool omni_net_off(int);\nextern "C" void omni_net_announce(); // OMNI_NET_SWITCH_LOG_V1\n'),
   ('    if (maxConnects < 0 && !omni_net_off(2))', '    omni_net_announce(); // OMNI_NET_SWITCH_LOG_V1: every net-off flag read and logged at curl start-up\n    if (maxConnects < 0 && !omni_net_off(2))'),
   ('// OMNI_NET_H2_SWITCH_V1: HTTP/2 is OPT-IN.', ANNOUNCE + '// OMNI_NET_H2_SWITCH_V1: HTTP/2 is OPT-IN.')],
 'WebKit/NetworkProcess/NetworkProcess.cpp': [
   ('extern "C" bool omni_net_off(int);\n', 'extern "C" bool omni_net_off(int);\nextern "C" void omni_net_announce(); // OMNI_NET_SWITCH_LOG_V1\n'),
   ('    if (cacheModel == CacheModel::DocumentBrowser && !omni_net_off(0)) // OMNI_NET_CACHEMODEL_V1: Omni is the primary browser\n',
    '    const int omniRequestedModel = static_cast<int>(cacheModel); // OMNI_NET_SWITCH_LOG_V1\n    omni_net_announce();\n'
    '    if (cacheModel == CacheModel::DocumentBrowser && !omni_net_off(0)) // OMNI_NET_CACHEMODEL_V1: Omni is the primary browser\n'),
   ('    fprintf(stderr, "OMNI NET cache model (network process): %d\\n", static_cast<int>(cacheModel));',
    '    fprintf(stderr, "OMNI NET cache model (network process): requested %d -> %d (0 viewer, 1 document browser, 2 primary)\\n", omniRequestedModel, static_cast<int>(cacheModel));')],
 'WebKit/WebProcess/WebProcess.cpp': [
   ('extern "C" bool omni_net_off(int);\n', 'extern "C" bool omni_net_off(int);\nextern "C" void omni_net_announce(); // OMNI_NET_SWITCH_LOG_V1\n'),
   ('    if (cacheModel == CacheModel::DocumentBrowser && !omni_net_off(0)) // OMNI_NET_CACHEMODEL_V1\n',
    '    omni_net_announce(); // OMNI_NET_SWITCH_LOG_V1: web process reads (and logs) every net-off flag once\n'
    '    if (cacheModel == CacheModel::DocumentBrowser && !omni_net_off(0)) // OMNI_NET_CACHEMODEL_V1\n')],
 'WebCore/platform/network/curl/DNSResolveQueueCurl.cpp': [
   ('extern "C" bool omni_net_off(int);\n', 'extern "C" bool omni_net_off(int);\nextern "C" void omni_net_note(const char*); // OMNI_NET_SWITCH_LOG_V1\n'),
   ('    if (omni_net_off(4) || !utf8URL)\n        return;\n',
    '    if (omni_net_off(4) || !utf8URL)\n        return;\n'
    '    static bool omniPreconnectSeen = false; // OMNI_NET_SWITCH_LOG_V1: say once that the preconnect path is live\n'
    '    if (!omniPreconnectSeen) {\n        omniPreconnectSeen = true;\n        omni_net_note("OMNI NET preconnect: first request (OMNI_NET_PRECONNECT_V1 path is live)");\n    }\n')],
}
# OMNI_NET_JSCACHE_OPTIN_V1 (rc3): the console bisect convicted OMNI_JSC_BYTECODE_CACHE_V1 (main-thread rewrites of
# YouTube's ~30 MB bundle, 2.1 GB / 1164 s of writes in 300 s, 0 hits), so it is OFF unless /data/omni/net-on-jscache.flag
# exists; net-off-jscache.flag and net5-off.flag still force it off. Every other net5 fix keeps its default (on).
JSC_OPS = [('        x = !::access(path, F_OK) || !::access("/data/omni/net5-off.flag", F_OK); v[id] = x; // OMNI_NET5_SWITCH_V1: one flag = every net5 fix off\n',
            '        x = !::access(path, F_OK) || !::access("/data/omni/net5-off.flag", F_OK); // OMNI_NET5_SWITCH_V1: one flag = every net5 fix off\n'
            '        if (!x && !strcmp(omniNetOffNames[id], "jscache") && ::access("/data/omni/net-on-jscache.flag", F_OK)) { // OMNI_NET_JSCACHE_OPTIN_V1\n'
            '            v[id] = 1; // the JS bytecode cache is opt-in: OFF unless net-on-jscache.flag (net-off-jscache / net5-off still win)\n'
            '            fprintf(stderr, "OMNI NET jscache: off by default (opt in with /data/omni/net-on-jscache.flag)\\n");\n'
            '            return true;\n'
            '        }\n'
            '        v[id] = x;\n')]
# OMNI_NET_HDRBUF_OPTIN_V1 (rc4): on the console, hdrbuf with the h2-capable libcurl kept YouTube's player from ever
# starting (net-off-hdrbuf.flag: 14.2 s), so it is OFF unless /data/omni/net-on-hdrbuf.flag; net-off-hdrbuf still wins.
HDRBUF_OPS = [('        x = !::access("/data/omni/net-off-hdrbuf.flag", F_OK);\n        v = x;\n        if (x)\n            fprintf(stderr, "OMNI NET kill switch on: hdrbuf\\n");\n',
               '        const bool omniOptedIn = !::access("/data/omni/net-on-hdrbuf.flag", F_OK); // OMNI_NET_HDRBUF_OPTIN_V1\n'
               '        x = !::access("/data/omni/net-off-hdrbuf.flag", F_OK) || !omniOptedIn;\n        v = x;\n'
               '        if (x && omniOptedIn)\n            fprintf(stderr, "OMNI NET kill switch on: hdrbuf\\n");\n'
               '        else if (x)\n            fprintf(stderr, "OMNI NET hdrbuf: off by default (opt in with /data/omni/net-on-hdrbuf.flag)\\n");\n')]
if '--hdrbuf-optin' in A:
    edit(W / 'WebCore/platform/network/curl/CurlRequest.cpp', 'OMNI_NET_HDRBUF_OPTIN_V1', HDRBUF_OPS)
if '--net' in A:
    edit(W / 'WebCore/platform/network/curl/CurlContext.cpp', 'OMNI_NET5_SWITCH_V1', NET_OPS)
    if '--no-jscache-optin' not in A:
        edit(W / 'WebCore/platform/network/curl/CurlContext.cpp', 'OMNI_NET_JSCACHE_OPTIN_V1', JSC_OPS)
    for rel, ops in NETLOG.items(): edit(W / rel, 'OMNI_NET_SWITCH_LOG_V1', ops)

# ------------------------------------------------------------------ S3.4G
HELPER = ('#include "config.h"\n\n// OMNI_S34G_SWITCH_V1 (omni-launch): /data/omni/s34g-off.flag = stock JavaScriptCore for every s3.4g site in this\n'
          '// file (read once per process). OMNI_STOCK_MINI is the stock condition those sites replaced.\n'
          '#include <unistd.h>\n#ifndef OMNI_STOCK_MINI\n#define OMNI_STOCK_MINI (JSC::VM::isInMiniMode())\n'
          'static inline bool omniS34gOff() { static const bool off = access("/data/omni/s34g-off.flag", F_OK) == 0; return off; }\n#endif\n')
SW = '(omniS34gOff() ? OMNI_STOCK_MINI : Options::forceMiniVMMode())'
S34G = {
 'JavaScriptCore/heap/Collector.cpp': [
   ('#include "config.h"\n', HELPER),
   ('    if (!Options::useGenerationalGC() || Options::forceMiniVMMode()) // OMNI_NO_MINI_MODE_V1',
    '    if (!Options::useGenerationalGC() || ' + SW + ') // OMNI_NO_MINI_MODE_V1 + OMNI_S34G_SWITCH_V1')],
 'JavaScriptCore/heap/Heap.cpp': [
   ('#include "config.h"\n', HELPER),
   ('    if (Options::forceMiniVMMode()) // OMNI_NO_MINI_MODE_V1\n        return Options::miniVMHeapGrowthFactor() * heapSize;\n',
    '    if (' + SW + ') // OMNI_NO_MINI_MODE_V1 + OMNI_S34G_SWITCH_V1\n        return Options::miniVMHeapGrowthFactor() * heapSize;\n'),
   ('|| Options::sweepSynchronously() || Options::forceMiniVMMode(); // OMNI_NO_MINI_MODE_V1',
    '|| Options::sweepSynchronously() || ' + SW + '; // OMNI_NO_MINI_MODE_V1 + OMNI_S34G_SWITCH_V1'),
   ('    if (proposed <= omniHeapCap || Options::forceMiniVMMode())\n        return proposed;\n',
    '    if (proposed <= omniHeapCap || Options::forceMiniVMMode() || omniS34gOff()) // OMNI_S34G_SWITCH_V1: flag = the stock target\n        return proposed;\n')],
 'JavaScriptCore/runtime/InitializeThreading.cpp': [
   ('#include "config.h"\n', HELPER),
   ('        if (omniKeepMallocMiniMode ? VM::isInMiniMode() : Options::forceMiniVMMode())\n',
    '        if ((omniKeepMallocMiniMode || omniS34gOff()) ? VM::isInMiniMode() : Options::forceMiniVMMode()) // OMNI_S34G_SWITCH_V1\n')],
 'JavaScriptCore/heap/FastMallocAlignedMemoryAllocator.cpp': [
   ('#include "config.h"\n', HELPER),
   ('        && (omniKeepMallocMiniMode ? !VM::isInMiniMode() : !Options::forceMiniVMMode()); // OMNI_MALLOC_MINI_V1\n',
    '        && ((omniKeepMallocMiniMode || omniS34gOff()) ? !VM::isInMiniMode() : !Options::forceMiniVMMode()); // OMNI_MALLOC_MINI_V1 + OMNI_S34G_SWITCH_V1\n')],
}
# flag present -> these exact stock lines (s3, before any Omni change) must reappear; flag absent -> s3.4g's lines
STOCK = {   # (text the flag-present projection must contain, the stock s3 text it stands for)
 'JavaScriptCore/heap/Collector.cpp': [('    if (!Options::useGenerationalGC() || VM::isInMiniMode())',) * 2],
 'JavaScriptCore/heap/Heap.cpp': [('    if (VM::isInMiniMode())\n        return Options::miniVMHeapGrowthFactor() * heapSize;',) * 2,
                                  ('|| Options::sweepSynchronously() || VM::isInMiniMode();',) * 2],
 'JavaScriptCore/runtime/InitializeThreading.cpp': [('        if (VM::isInMiniMode())\n            WTF::fastEnableMiniMode(Options::forceMiniVMMode());',) * 2],
 'JavaScriptCore/heap/FastMallocAlignedMemoryAllocator.cpp': [('&& (!VM::isInMiniMode());', '&& !VM::isInMiniMode();')],
}
if '--s34g' in A:
    for rel, ops in S34G.items(): edit(W / rel, 'OMNI_S34G_SWITCH_V1', ops)
    s3 = arg('--check-stock')
    if s3:
        bad = 0
        def proj(t, on):
            t = t.replace(SW, 'VM::isInMiniMode()' if on else 'Options::forceMiniVMMode()')
            t = t.replace('(omniKeepMallocMiniMode || omniS34gOff()) ? VM::isInMiniMode() : Options::forceMiniVMMode()', 'VM::isInMiniMode()' if on else 'omniKeepMallocMiniMode ? VM::isInMiniMode() : Options::forceMiniVMMode()')
            t = t.replace('(omniKeepMallocMiniMode || omniS34gOff()) ? !VM::isInMiniMode() : !Options::forceMiniVMMode()', '!VM::isInMiniMode()' if on else 'omniKeepMallocMiniMode ? !VM::isInMiniMode() : !Options::forceMiniVMMode()')
            return re.sub(r' *// OMNI_[^\n]*', '', t)
        for rel, lines in STOCK.items():
            cur = (W / rel).read_text().replace('\r\n', '\n'); stock = (Path(s3) / 'webkit/Source' / rel).read_text().replace('\r\n', '\n')
            on = proj(cur, True)
            for pl, sl in lines:
                ok = pl in on and sl in stock; bad += not ok
                print(('PASS ' if ok else 'FAIL ') + f'{rel}: s34g-off.flag present -> stock condition {sl.strip()[:70]!r}')
        heap = (W / 'JavaScriptCore/heap/Heap.cpp').read_text()
        ok = 'Options::forceMiniVMMode() || omniS34gOff())' in heap and 'return proposed;' in heap; bad += not ok
        print(('PASS ' if ok else 'FAIL ') + 'Heap.cpp: s34g-off.flag present -> omniCappedHeapTarget returns the stock proposed target')
        print('S34G SWITCH CHECK', 'PASS' if not bad else f'FAIL ({bad})'); sys.exit(1 if bad else 0)
print(f'omni-launch switches: {len(done)} files patched ({", ".join(done) or "none"})')
