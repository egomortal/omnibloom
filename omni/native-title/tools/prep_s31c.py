#!/usr/bin/env python3
"""omni-native-s3.1c prep = tools/prep_s31.py (s3.1b) with the s3.1c objects folder, marker and label (OMNI_POINTER_CROSS_V1).
omni-native-s3.1 prep (= tools/prep_s3.py with the s3.1 objects folder, marker, label and jit2's NativeEmutls.cpp).
omni-native-s2 prep (after ninja + make_link_command.py, inside the private namespace where /home/builder/s1 is the s2
tree). The GPU job's recipe (omni-native-s2-gpu/prep.py) on the s2 tree: compiles the GPU OmniHwService.cpp (parts 1+2)
and OmniGpuVideo.cpp with the tree's own compile command into /home/builder/s2aobjs (title link only; the child keeps the
tree's unchanged OmniHwService), renames SDL's VideoOut references to OmniGpuPresent.cpp's stand-ins in a private copy
of the SDL archive, and writes this folder's link-command.json and build.py (s1c's build.py + label + OmniGpuPresent.cpp
+ the 4 SDL wraps). Never writes outside this folder and /home/builder/s2aobjs."""
import json, shlex, shutil, subprocess, sys
from pathlib import Path
N = Path(__file__).resolve().parent.parent
S1C, GPU = N.parent / 'omni-native-s1c', N.parent / 'omni-native-s2-gpu'
W = Path('/home/builder/s31cobjs'); (W / 'media').mkdir(parents=True, exist_ok=True)   # s3.1: its own objects folder (s3's is never written)
VKH = N.parent.parent / 'nxe-ps5/bigapp/private/av2/upstream/PS5_Mesa/include'
ENGMEDIA = '/home/builder/s1/engine/media'
def say(*a): print(*a, flush=True)
if not Path('/home/builder/s1/.s31c-marker').exists(): sys.exit('BLOCKED: /home/builder/s1 is not the s3.1c overlay (no .s31c-marker)')
line = (GPU / 'fetch/hwservice-compile.txt').read_text().splitlines()[0]
cwd, cmd = '/home/builder/s1/build', None
for part in (p.strip() for p in line.split(' && ')):
    if part.startswith('cd '): cwd = shlex.split(part)[1]
    elif 'OmniHwService.cpp' in part: cmd = shlex.split(part)
if not cmd: sys.exit('BLOCKED: no compile command in the GPU fetch')
base, i = [], 0
while i < len(cmd):
    a = cmd[i]
    if a in ('-MD', '-MMD'): i += 1; continue
    if a in ('-MT', '-MF', '-o', '-c'): i += 2; continue
    base.append(a); i += 1
for f in ('OmniHwService.cpp', 'OmniGpuVideo.h', 'OmniGpuVideo.cpp', 'OmniGpuVideoShader.h'):
    shutil.copyfile(GPU / 'engine/media' / f, W / 'media' / f)
objs = {}
for src, extra in (('OmniHwService.cpp', []), ('OmniGpuVideo.cpp', ['-isystem', str(VKH)])):
    obj = W / (src + '.o')
    args = [base[0], '-iquote', ENGMEDIA, *base[1:], *extra, '-o', str(obj), '-c', str(W / 'media' / src)]
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    (N / f'compile-{src}.log').write_text(' '.join(shlex.quote(a) for a in args) + '\n\n' + r.stdout + r.stderr)
    if r.returncode: sys.exit(f'BLOCKED: compiling {src} failed: ' + (r.stderr.strip().splitlines() or ['?'])[-1][:300])
    objs[src] = str(obj); say('compiled', src, obj.stat().st_size, 'bytes')
lc = json.loads(Path('/home/builder/s1/link-command.json').read_text())
c = lc['command']
hits = [k for k, a in enumerate(c) if a.endswith('/media/OmniHwService.cpp.o')]
if len(hits) != 1: sys.exit(f'BLOCKED: OmniHwService.cpp.o appears {len(hits)} times in the link')
k = hits[0]; c[k:k + 1] = [objs['OmniHwService.cpp'], objs['OmniGpuVideo.cpp']]
VO = ['sceVideoOutOpen', 'sceVideoOutClose', 'sceVideoOutAddFlipEvent', 'sceVideoOutSetFlipRate', 'sceVideoOutSubmitFlip',
      'sceVideoOutDeleteFlipEvent', 'sceVideoOutSetBufferAttribute2', 'sceVideoOutRegisterBuffers2', 'sceVideoOutGetOutputStatus']
sdl = [i for i, a in enumerate(c) if a.endswith('libSDL2-hdr-v5.a')]
if len(sdl) != 1: sys.exit(f'BLOCKED: libSDL2-hdr-v5.a appears {len(sdl)} times in the link')
src_sdl = Path(c[sdl[0]] if c[sdl[0]].startswith('/') else Path(lc['cwd']) / c[sdl[0]])
gp_sdl = W / 'libSDL2-hdr-v5-gpupresent.a'
r = subprocess.run(['/usr/lib/llvm-21/bin/llvm-objcopy', *sum([['--redefine-sym', f'{n}=omni_gp_{n}'] for n in VO], []), str(src_sdl), str(gp_sdl)], capture_output=True, text=True)
if r.returncode: sys.exit('BLOCKED: llvm-objcopy on the SDL archive: ' + r.stderr[-300:])
nm = subprocess.run(['/usr/lib/llvm-21/bin/llvm-nm', '-A', str(gp_sdl)], capture_output=True, text=True).stdout
left = sorted({l.split()[-1] for l in nm.splitlines() if ' U sceVideoOut' in l})
moved = sorted({l.split()[-1] for l in nm.splitlines() if ' U omni_gp_sceVideoOut' in l})
if left or len(moved) != len(VO): sys.exit(f'BLOCKED: SDL VideoOut redirect incomplete: left {left}, moved {moved}')
c[sdl[0]] = str(gp_sdl)
(N / 'link-command.json').write_text(json.dumps(lc, indent=0))
say('link command: GPU objects swapped in, SDL copy with', len(moved), 'VideoOut stand-ins')
b = (S1C / 'build.py').read_text()
subs = [("S1LC = Path('/home/builder/s1/link-command.json')", "S1LC = HERE / 'link-command.json'   # s2: the s2 tree's link with the GPU objects"),
        ("'label': 'omni-native-s1c'", "'label': 'omni-native-s3.1c', 'pointer': 'OMNI_POINTER_CROSS_V1 (Cross at the pointer while the pointer leads; title only, the child is built before the patch)', 's31b': 'jit2 build 6: OMNI_NO_VIEW_TRANSITION_V1 + OMNI_SOAK_READ_V1 + OMNI_YT_TIMELINE_V1 (flag-only)', 's3': 'OMNI_NO_ACCEL_CANVAS_V1 + OMNI_ADDONS_V1 + OMNI_VAULT_V2 + OMNI_PAGES_V1 + OMNI_JSC_JIT_V3 (JIT default off)', 's31': 'audit OS-001 OMNI_SEC_PNA_CONNECT_V1 + OS-002 vault read errors + jit2 build 4 (OMNI_EMUTLS_ROUNDS_V1, OMNI_CRASH_V2)', 'gpu': 'OMNI_GPU_VIDEO_V1 + OMNI_GPU_PRESENT_V1, off unless their flags', 'hub': 'OMNI_HUB_CARDS_V1', 'hud': 'OMNI_HUD_ASTRA_V1'"),
        ("shutil.copyfile(icon, PKG / 'sce_sys/icon0.png')",
         "shutil.copyfile(icon, PKG / 'sce_sys/icon0.png')\n"
         "# s3 OMNI_PAGES_V1: the built-in pages at /app0/pages (ENGINE-CONTRACT 1: never dev/, tests, build scripts) + the add-ons page\n"
         "_skip = lambda n: n in ('dev', 'test-evidence', 'node_modules') or n.startswith(('test_bundle', 'build_bundle')) or n.endswith('.cjs')\n"
         "shutil.copytree(OUTS / 'omni-pages/bundle', PKG / 'pages', ignore=lambda d, names: [n for n in names if _skip(n)])\n"
         "shutil.copytree(OUTS / 'omni-addons/pages/addons', PKG / 'pages/addons', dirs_exist_ok=True)\n"
         "print('pages packaged:', sum(1 for _ in (PKG / 'pages').rglob('*') if _.is_file()), 'files', flush=True)"),
        ("run([LLD, *script, f'@{B}/link-{pass_name}.rsp']", "run([LLD, '--threads=8', *script, f'@{B}/link-{pass_name}.rsp']"),
        ("for src in ['OmniNativeTitle.cpp', 'NativeLauncherState.cpp', 'NativeLibc.cpp', 'NativeFilesBroker.cpp']:",
         "for src in ['OmniNativeTitle.cpp', 'NativeLauncherState.cpp', 'NativeLibc.cpp', 'NativeFilesBroker.cpp', 'OmniGpuPresent.cpp', 'NativeEmutls.cpp']:   # s2: GPU part 2; s3.1: jit2 OMNI_EMUTLS_ROUNDS_V1"),
        ("MY_WRAPS = ['main', ", "MY_WRAPS = ['SDL_Init', 'SDL_Quit', 'SDL_UpdateWindowSurface', 'SDL_UpdateWindowSurfaceRects', 'main', ")]
for a, z in subs:
    if b.count(a) != 1: sys.exit(f'BLOCKED: build.py anchor not found once: {a[:70]}')
    b = b.replace(a, z)
(N / 'build.py').write_text(b.replace('f.read(1 << 22)', 'f.read(1 << 20)'))   # 9P reads: smaller chunks
for d in ('stubs', 'src'):
    if (N / d).exists(): shutil.rmtree(N / d)
    shutil.copytree(S1C / d, N / d)
shutil.copytree(S1C / 'tools', N / 'tools', dirs_exist_ok=True)   # keeps tools/; s3 adds tools/prep_s3.py
shutil.copyfile(N / 'src-title/OmniNativeTitle.cpp', N / 'src/OmniNativeTitle.cpp')
shutil.copyfile(N / 'src-title/OmniGpuPresent.cpp', N / 'src/OmniGpuPresent.cpp')
shutil.copyfile(N / 'src-title/NativeEmutls.cpp', N / 'src/NativeEmutls.cpp')   # s3.1: jit2 OMNI_EMUTLS_ROUNDS_V1
say('build.py written; tools/ stubs/ src/ from s1c; src/OmniNativeTitle.cpp + OmniGpuPresent.cpp from src-title')
