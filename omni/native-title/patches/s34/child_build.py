#!/usr/bin/env python3
"""omni-native-s1 child engine (sec-job2): sec1's child recipe on the s1 in-tree engine link (make_link_command.py).
The page processes run this engine: JavaScriptCore JIT compiled in, used only with /data/omni/jsc-jit.flag. Previously:
omni-native-sec1 child engine (sec-job1): s0c's child + OMNI_SEC_LOCALHOST_V1 (child-src/omni-sec-connect.cpp,
linked with -Wl,--wrap=connect: page connections to loopback / the console's own addresses are refused except
Omni's own UI ports) + the updated security libraries from OMNI_SECLIBS, on the sec1-shell engine overlay.
omni-native-s0c child engine (OMNI_NATIVE_CHILD_V1): candidate 56c's omni-engine.elf relinked with a
libWebKitRequirements.a whose launcher-child.cpp is built with -DOMNI_NATIVE_CHILD (child-src/).
Only the native title starts this copy (/data/omni/native/omni-engine-child.elf); the big-app keeps
/data/omni/omni-engine.elf (56c). Same link as omni_build.py steps 2-4 (DL1 link command + 56c's
replaced inputs + this archive). LOCAL BUILD ONLY."""
import hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; OUTS = HERE.parent; ROOT = OUTS.parent
DL1 = ROOT / 'baseline/DL1'; ENG = Path('/home/builder/s1/engine'); S1LC = Path('/home/builder/s1/link-command.json')
OUT = HERE / 'child'; OLD, NEW = '/home/builder/Downloads/jailbreak stuff/', '/home/builder/Downloads/ps5 stuff/'
fix = lambda s: s.replace(OLD, NEW) if isinstance(s, str) else s
def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()
def run(cmd, out=None, **kw):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)
    if out: Path(out).write_text(r.stdout + r.stderr)
    if r.returncode: print((r.stdout + r.stderr)[-6000:]); sys.exit(f'FAILED: {" ".join(map(str, cmd))[:300]}')
    return r
t0 = time.time(); shutil.rmtree(OUT, ignore_errors=True); OUT.mkdir()
WKREQ_OLD = '/opt/omni-build/wkreq-sdr-rc7final.16vtJE/libWebKitRequirements.a'
# 1. archive: RC7's recipe (as build.py), launcher-child from child-src/ with the define
wr = ENG / 'ports/webkit-requirements'; wt = OUT / 'wkreq'; wt.mkdir()
for f in ('process-launcher', 'launcher-child', 'support'):
    src = HERE / 'child-src/launcher-child.cpp' if f == 'launcher-child' else wr / f'src/{f}.cpp'
    extra = ['-DOMNI_NATIVE_CHILD=1'] if f == 'launcher-child' else []
    run(['/opt/ps5-payload-sdk/bin/prospero-clang++', '-std=c++17', '-O2', *extra, f'-I{wr}/include', f'-I{wr}/src', '-c', src, '-o', wt / f'{f}.cpp.o'], out=wt / f'{f}.compile.log')
run(['/opt/ps5-payload-sdk/bin/prospero-ar', 'rcs', wt / 'libWebKitRequirements.a', *sorted(wt.glob('*.o'))])
# sec1: the console-port block (a separate object, only in the child engine's link)
secobj = OUT / 'omni-sec-connect.o'
run(['/opt/ps5-payload-sdk/bin/prospero-clang++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-c', HERE / 'child-src/omni-sec-connect.cpp', '-o', secobj], out=OUT / 'omni-sec-connect.compile.log')
SECLIBS = Path(os.environ.get('OMNI_SECLIBS', '/home/builder/omni-seclibs/stage/user/homebrew/lib'))
HBL = '/opt/ps5-payload-sdk/target/user/homebrew/lib/'
SECNAMES = ['libssl.a', 'libcrypto.a', 'libcurl.a', 'libpng16.a', 'libpng.a', 'libxml2.a', 'libavformat.a', 'libavcodec.a', 'libavutil.a', 'libswscale.a', 'libswresample.a']
for n in SECNAMES:
    if not (SECLIBS / n).exists(): sys.exit(f'BLOCKED: updated library missing: {SECLIBS / n}')
nm = run(['/usr/lib/llvm-21/bin/llvm-nm', wt / 'launcher-child.cpp.o']).stdout
assert 'nativeChildWatch' in nm or 'nativeChildLeave' in nm, 'OMNI_NATIVE_CHILD code missing from launcher-child.o'
# 2. link inputs: the s1 in-tree OmniEngine link, with this archive and the updated libraries
ln = json.loads(S1LC.read_text())
replace = {}
for x in ln['command']:
    if x.endswith('/libWebKitRequirements.a'): replace[x] = str(wt / 'libWebKitRequirements.a')
assert replace, 'no libWebKitRequirements.a in the s1 link'
for n in SECNAMES: replace[HBL + n] = str(SECLIBS / n)   # explicit archive paths in the link command
lcmd = [replace.get(fix(x), fix(x)) for x in ln['command']]
# -lssl/-lcrypto/-lav*/-lsw*: the stage directory first in the driver's search path (it holds only updated libs)
# The DL1 driver (omni-clang++) puts the SDK's homebrew lib dir ahead of any -L given here, so -lssl/-lcrypto/-lav*/-lsw*
# would still pick the old archives (seen in the first sec1 link: OpenSSL 3.5.2 / Lavf61.1.100 strings). Resolve them to the
# stage archives by explicit path instead.
LMAP = {f'-l{n[3:-2]}': str(SECLIBS / n) for n in SECNAMES}
lcmd = [LMAP.get(x, x) for x in lcmd]
assert not [x for x in lcmd if x in LMAP], 'unmapped -l security library'
lcmd += [str(secobj), '-Wl,--wrap=connect']
unstr = OUT / 'omni-engine-child-unstripped.elf'; lcmd[lcmd.index('-o') + 1] = str(unstr); lcmd.append('-Wl,--build-id=sha1')
r = subprocess.run(lcmd, cwd=ln['cwd'], capture_output=True, text=True); (OUT / 'link.log').write_text(r.stdout + r.stderr)
if r.returncode: sys.exit('LINK FAILED (child/link.log)')
strip = json.loads((DL1 / 'build/strip-command.json').read_text()) if (DL1 / 'build/strip-command.json').exists() else ['/opt/ps5-payload-sdk/bin/llvm-strip']
final = OUT / 'omni-engine-child.elf'; run([*strip, unstr, '-o', final])
chk = subprocess.run(['/usr/lib/llvm-21/bin/llvm-nm', unstr], capture_output=True, text=True).stdout
if ' T __wrap_connect' not in chk: sys.exit('CHECK FAILED: __wrap_connect not linked')
used = {}
for n in SECNAMES:
    p = SECLIBS / n
    if not p.is_symlink(): used[n] = sha(p)
rc = {'label': 'omni-native-s3.1b-child', 's31b': 'OMNI_NO_VIEW_TRANSITION_V1 (jit2 build 6)', 's3': 'OMNI_JSC_JIT_V3 + OMNI_NO_ACCEL_CANVAS_V1 safety net', 's31': 'OMNI_SEC_PNA_CONNECT_V1 (audit OS-001) + OMNI_CRASH_V2 (jit2)', 'base': 's1 in-tree engine (JIT compiled in, gamepad, CVE fixes, PNA; 57 + sec1-shell + sec-job2 shell)', 'jit_strings': [k for k in ('jit: on (baseline', 'jit: off (interpreter)') if k.encode() in open(final, 'rb').read()], 'sec': 'OMNI_SEC_LOCALHOST_V1 connect wrap', 'seclibs': used, 'define': 'OMNI_NATIVE_CHILD=1 (launcher-child.cpp only)',
      'archive_sha256': sha(wt / 'libWebKitRequirements.a'), 'unstripped_sha256': sha(unstr), 'engine_sha256': sha(final),
      'engine_bytes': final.stat().st_size,
      'seconds': round(time.time() - t0)}
(OUT / 'receipt.json').write_text(json.dumps(rc, indent=1) + '\n')
print(json.dumps(rc, indent=1))
