#!/usr/bin/env python3
"""OMNI_GPU_ONE_SUBMITTER_V1 (2026-11-16): ONE submitter at the AGC driver level in the TITLE process (layers mode).
With layers on, the console was seen to hard-hang 15-45 s after launch. The title had two GPU submitters that never
synchronised: the gpu-broker owner (engine-child work: broker_submit -> sceAgcDriverSubmitDcb, kick() ->
sceAgcSuspendPoint, the shared TF-ring / HS-offchip state) and the title's own RADV (OmniGpuPresent, Zink): the pinned
archive libvulkan_radeon-hdr-wsi.a, whose winsys_ps5_radv_ps5_platform.c.o is the ONLY member importing AGC
(sceAgcDriverSubmitDcb, sceAgcSuspendPoint from its kick thread, sceAgcDriverSetTFRing, sceAgcDriverSetHsOffchipParam,
sceAgcInit). The PS5 winsys orders work only inside one Mesa instance ("no concurrent queues").

The lock lives in stage1/src-title/omni_gpu_one_submitter.c (host-tested: tools/test_one_submitter.cpp). The title's
RADV is a sha-pinned PREBUILT archive (build.py refuses any other), so Mesa's side is not patched in source: the title
link wraps the five AGC functions (lld --wrap), which routes the archive's calls AND the broker's through the lock with
no Mesa rebuild and no change to the import table. The engine child links its own Mesa with the broker CLIENT
(cp2/client.a, no AGC import) and is not touched.

Modes (each idempotent, every anchor must be found exactly once, CRLF kept):
  broker <server.cpp>      the broker owner (a COPY of omni-gpupages-ls1b/broker-mem, see 'recipe'): the cache flush
                           moves before the lock; "set shared state, then SubmitDcb" runs inside one bracket
                           (enter/leave), deciding the state from the process-wide value (not only the broker's own
                           memory of it); kick()'s suspend point and the warm-up submission are bracketed as the broker's.
  build  <build.py> <stage1/src-title>   the TITLE link (after patch_title_build.py): compiles omni_gpu_one_submitter.c
                           into the title, adds --wrap for the 5 AGC names, and a gate after pass 2 that refuses a title
                           without all 5 __wrap_sceAgc* definitions.
  recipe <build-omni-gpupages-rc6-title.sh>   the recipe: copies broker-mem to $F/broker-onesub, patches it ('broker'),
                           points OGP_BRK at the copy, and runs 'build' right after patch_title_build.py.
usage: apply_one_submitter.py MODE PATH [SRC-TITLE]"""
import sys
from pathlib import Path

MARK = 'OMNI_GPU_ONE_SUBMITTER_V1'


def patch(path, edits, need=None, suffix='.before-onesubmitter'):
    p = Path(path)
    raw = p.read_bytes().decode('utf-8')
    crlf = '\r\n' in raw
    t = raw.replace('\r\n', '\n')
    if MARK in t:
        print('already', p.name)
        return
    if need and need not in t:
        sys.exit('%s: %r missing: wrong file or an earlier patch is not applied' % (p.name, need))
    for old, new in edits:
        n = t.count(old)
        if n != 1:
            sys.exit('%s: anchor found %d times: %r' % (p.name, n, old[:100]))
        t = t.replace(old, new, 1)
    backup = p.with_name(p.name + suffix)
    if not backup.exists():
        backup.write_bytes(raw.encode('utf-8'))
    p.write_bytes((t.replace('\n', '\r\n') if crlf else t).encode('utf-8'))
    print('patched %s (%d edits)' % (p.name, len(edits)))


# ----------------------------------------------------------------------------------------------------- broker owner
BROKER = [
    ('int sceKernelUsleep(unsigned);\n}\n',
     'int sceKernelUsleep(unsigned);\n'
     '// OMNI_GPU_ONE_SUBMITTER_V1 (omni_gpu_one_submitter.c, linked into the title): one process-wide lock around\n'
     '// every AGC driver call of the title. Inside enter/leave the wrapped calls count as the broker\'s.\n'
     'void omni_gpu_one_submitter_enter(int who);\n'
     'void omni_gpu_one_submitter_leave(void);\n'
     'int omni_gpu_one_submitter_tf_is(uint64_t address,uint32_t size);\n'
     'int omni_gpu_one_submitter_offchip_is(uint32_t granularity,uint32_t buffering);\n'
     '}\n'
     'static constexpr int kOgsBroker=1;   // OMNI_GPU_SUBMITTER_BROKER\n'),
    # the flush moves to the caller, before the lock
    ('int broker_submit(void *words,uint32_t count)\n{\n    radv_ps5_cpu_flush(words,size_t(count)*4);\n',
     'int broker_submit(void *words,uint32_t count)\n{\n'
     '    // OMNI_GPU_ONE_SUBMITTER_V1: the caller flushed the words before taking the one-submitter lock.\n'),
    ('    sceAgcSuspendPoint();\n    fences.kick_ns',
     '    omni_gpu_one_submitter_enter(kOgsBroker);sceAgcSuspendPoint();omni_gpu_one_submitter_leave();   // OMNI_GPU_ONE_SUBMITTER_V1\n'
     '    fences.kick_ns'),
    ('    int status=0;\n'
     '    if(tess_changes && !(status=radv_ps5_set_tess_factor_ring(c.tess,c.tess_bytes))) { fences.tess=c.tess;fences.tess_bytes=c.tess_bytes; }\n'
     '    if(!status && offchip_changes && !(status=radv_ps5_set_hs_offchip_param(c.granularity,c.buffering))) {\n'
     '        fences.offchip=true;fences.granularity=c.granularity;fences.buffering=c.buffering;\n'
     '    }\n'
     '    if(!status) {\n'
     '        const bool refused=test_fail_submit && ++test_submissions>test_fail_submit;\n'
     '        status=refused ? EIO : broker_submit(staging.cpu,(uint32_t)(m.bytes/4)+8);\n'
     '        // An error cannot prove that nothing reached the hardware: the staging stays, and nothing else is freed.\n'
     '        if(status) { give_up(out,refused ? "test_submit_failure" : "vulkan_submit_error");return EIO; }\n'
     '    }\n',
     '    int status=0;\n'
     '    // OMNI_GPU_ONE_SUBMITTER_V1: flush first (outside any lock), then the state this client needs and its submission\n'
     '    // in ONE bracket of the process-wide lock, so the title\'s RADV cannot change the shared GPU state between them.\n'
     '    // The state is set when the process-wide value differs (the title may have changed it), not only when the\n'
     '    // broker\'s own memory of it does.\n'
     '    radv_ps5_cpu_flush(staging.cpu,size_t(m.bytes/4+8)*4);\n'
     '    bool tried=false,refused=false;\n'
     '    omni_gpu_one_submitter_enter(kOgsBroker);\n'
     '    const bool tess_needed=c.tess && (tess_changes || !omni_gpu_one_submitter_tf_is(c.tess,c.tess_bytes));\n'
     '    const bool offchip_needed=c.offchip && (offchip_changes || !omni_gpu_one_submitter_offchip_is(c.granularity,c.buffering));\n'
     '    if(tess_needed && !(status=radv_ps5_set_tess_factor_ring(c.tess,c.tess_bytes))) { fences.tess=c.tess;fences.tess_bytes=c.tess_bytes; }\n'
     '    if(!status && offchip_needed && !(status=radv_ps5_set_hs_offchip_param(c.granularity,c.buffering))) {\n'
     '        fences.offchip=true;fences.granularity=c.granularity;fences.buffering=c.buffering;\n'
     '    }\n'
     '    if(!status) {\n'
     '        tried=true;refused=test_fail_submit && ++test_submissions>test_fail_submit;\n'
     '        status=refused ? EIO : broker_submit(staging.cpu,(uint32_t)(m.bytes/4)+8);\n'
     '    }\n'
     '    omni_gpu_one_submitter_leave();\n'
     '    // An error cannot prove that nothing reached the hardware: the staging stays, and nothing else is freed.\n'
     '    if(tried && status) { give_up(out,refused ? "test_submit_failure" : "vulkan_submit_error");return EIO; }\n'),
    ('    int result=radv_ps5_submit(reinterpret_cast<uint32_t *>(memory.cpu),8,marker,77);\n',
     '    omni_gpu_one_submitter_enter(kOgsBroker);   // OMNI_GPU_ONE_SUBMITTER_V1\n'
     '    int result=radv_ps5_submit(reinterpret_cast<uint32_t *>(memory.cpu),8,marker,77);\n'
     '    omni_gpu_one_submitter_leave();\n'),
]

# ---------------------------------------------------------------------------------------------------- title build.py
WRAPS = ['sceAgcDriverSubmitDcb', 'sceAgcSuspendPoint', 'sceAgcDriverSetTFRing', 'sceAgcDriverSetHsOffchipParam',
         'sceAgcInit']


def build_edits(srcdir):
    src = str(Path(srcdir) / 'omni_gpu_one_submitter.c')
    return [
        ("say('stage 1: OmniGpuPagesService + gpu-broker owner compiled into the title (off unless /data/omni/gpu-pages-stage1.flag)')\n",
         "say('stage 1: OmniGpuPagesService + gpu-broker owner compiled into the title (off unless /data/omni/gpu-pages-stage1.flag)')\n"
         "# OMNI_GPU_ONE_SUBMITTER_V1: one process-wide lock around every AGC driver call of the title (the RADV archive's and\n"
         "# the broker's): the five AGC functions are wrapped at link time (__real_X = the system import X, unchanged).\n"
         f"OGS_SRC = Path({src!r})\n"
         "o = B / 's1-omni_gpu_one_submitter.o'\n"
         "run([CC, '-std=gnu11', '-O2', '-Wall', '-Wextra', '-ffunction-sections', '-fdata-sections', '-D__PROSPERO__', f'-I{OGS_SRC.parent}', '-c', OGS_SRC, '-o', o], out=B / 's1-omni_gpu_one_submitter.compile.log')\n"
         "mine.append(str(o))\n"
         f"OGS_WRAPS = {WRAPS!r}\n"
         "say('OMNI_GPU_ONE_SUBMITTER_V1: AGC driver calls go through one lock: ' + ', '.join(OGS_WRAPS))\n"),
        ("            'isatty', 'mkstemp', 'fstatfs', 'fnmatch', 'gai_strerror', 'getnameinfo']\n",
         "            'isatty', 'mkstemp', 'fstatfs', 'fnmatch', 'gai_strerror', 'getnameinfo']\n"
         "MY_WRAPS += OGS_WRAPS   # OMNI_GPU_ONE_SUBMITTER_V1\n"),
        ("say(f'pass 2: {len(und)} imports ({len(imports)} checked at start, {len(lazy & und)} lazy Videodec2); no direct exit/_exit/keyboard/IME imports (dup only behind __wrap_dup)')\n",
         "say(f'pass 2: {len(und)} imports ({len(imports)} checked at start, {len(lazy & und)} lazy Videodec2); no direct exit/_exit/keyboard/IME imports (dup only behind __wrap_dup)')\n"
         "# OMNI_GPU_ONE_SUBMITTER_V1 gate: every wrap is defined in the title (a reference that missed the wrap would have\n"
         "# linked straight to the import and bypassed the lock).\n"
         "ogs_defs = run([NM, '--defined-only', B / 'llvm-pie.elf']).stdout\n"
         "ogs_missing = [n for n in OGS_WRAPS if not re.search(rf' [tT] __wrap_{n}$', ogs_defs, re.M)]\n"
         "if ogs_missing: raise SystemExit(f'REFUSED: OMNI_GPU_ONE_SUBMITTER_V1 wraps missing from the title: {ogs_missing}')\n"
         "say('OMNI_GPU_ONE_SUBMITTER_V1 gate: __wrap_ defined for ' + ', '.join(OGS_WRAPS))\n"),
    ]


# ------------------------------------------------------------------------------------------------------------ recipe
RECIPE_OLD = ('OGP_BRK="$O/omni-gpupages-ls1b/broker-mem" python3 "$S1/tools/patch_title_build.py" "$NE/build.py" "$S1/src-title" '
              '> "$F/logs/patch-title-build.log" 2>&1 || { st "stage-1 title sources FAILED"; exit 1; }\n')
RECIPE_NEW = (
    '# OMNI_GPU_ONE_SUBMITTER_V1: a patched COPY of the broker owner (the shared broker-mem stays as it is), then the AGC\n'
    '# wraps + the lock in the title link (stage1/tools/apply_one_submitter.py)\n'
    'rm -rf "$F/broker-onesub" && cp -r "$O/omni-gpupages-ls1b/broker-mem" "$F/broker-onesub" \\\n'
    '  && python3 "$S1/tools/apply_one_submitter.py" broker "$F/broker-onesub/server.cpp" > "$F/logs/apply_one_submitter_broker.log" 2>&1 '
    '|| { st "one submitter (broker) FAILED: $(tail -1 "$F/logs/apply_one_submitter_broker.log")"; exit 1; }\n'
    'OGP_BRK="$F/broker-onesub" python3 "$S1/tools/patch_title_build.py" "$NE/build.py" "$S1/src-title" '
    '> "$F/logs/patch-title-build.log" 2>&1 || { st "stage-1 title sources FAILED"; exit 1; }\n'
    'python3 "$S1/tools/apply_one_submitter.py" build "$NE/build.py" "$S1/src-title" > "$F/logs/apply_one_submitter_build.log" 2>&1 '
    '|| { st "one submitter (title link) FAILED: $(tail -1 "$F/logs/apply_one_submitter_build.log")"; exit 1; }\n'
    'st "OMNI_GPU_ONE_SUBMITTER_V1: $(tail -1 "$F/logs/apply_one_submitter_broker.log"); $(tail -1 "$F/logs/apply_one_submitter_build.log")"\n')


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    mode, path = sys.argv[1], sys.argv[2]
    if mode == 'broker':
        patch(path, BROKER, need='int broker_submit(void *words,uint32_t count)')
    elif mode == 'build':
        if len(sys.argv) != 4:
            sys.exit('build needs <build.py> <stage1/src-title>')
        if not (Path(sys.argv[3]) / 'omni_gpu_one_submitter.c').is_file():
            sys.exit('omni_gpu_one_submitter.c not found in ' + sys.argv[3])
        patch(path, build_edits(sys.argv[3]), need='OMNI_GPU_PAGES_STAGE1_V1')
    elif mode == 'recipe':
        patch(path, [(RECIPE_OLD, RECIPE_NEW)])
    else:
        sys.exit('unknown mode ' + mode)


if __name__ == '__main__':
    main()
