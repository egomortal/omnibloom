#!/usr/bin/env python3
"""omni-native-s3.5-hdr prep = tools/prep_s34.py (s3.4d) with the s3.5 objects folder, marker and label, OmniHdrPolicy.h
in src/, the private HDR RADV archive (radv/, Ex-Box PPSA99736's VideoOut WSI member: A2B10G10R10 + HDR10_ST2084) in
build.py, and a param.json check that the title's own attribute declares HDR (bit 0x20000000; no other profile is touched).
omni-native-s3.4 prep = tools/prep_s33.py with the s3.4 objects folder, marker, label, the CLEAN4 media headers
(OmniHwService.h, OmniVideoStats.h, OmniHdrPreference.h) and Astra's final pages (codex-ui/20261104-ui-clean4-final-pages/proposed/pages).
omni-native-s3.3 prep = tools/prep_s32.py (s3.2-video) with the s3.3 objects folder, marker and label (OMNI_POINTER_CROSS_V1).
omni-native-s3.2-video prep (= tools/prep_s31.py with this folder's GPU sources, objects folder, marker, label, the
PQ shader header and the SDL_FreeSurface wrap). Runs after ninja + make_link_command.py, inside the private namespace
where /home/builder/s1 is the s3.2 overlay of s3. Compiles THIS folder's OmniHwService.cpp (s2-gpu's GPU hooks + the
V2 forget/counters hooks) and OmniGpuVideo.cpp (V2) with the tree's own compile command into /home/builder/s32objs
(title link only; the child keeps the tree's OmniHwService), renames SDL's VideoOut references to OmniGpuPresent.cpp's
stand-ins in a private copy of the SDL archive, and writes this folder's link-command.json and build.py (s1c's build.py +
label + OmniGpuPresent.cpp + 5 SDL wraps). Never writes outside this folder and /home/builder/s32objs."""
import json, shlex, shutil, subprocess, sys
from pathlib import Path
N = Path(__file__).resolve().parent.parent
S1C, GPU = N.parent / 'omni-native-s1c', N.parent / 'omni-native-s2-gpu'
W = Path('/home/builder/launchobjs'); (W / 'media').mkdir(parents=True, exist_ok=True)   # s3.2: its own objects folder
VKH = N.parent.parent / 'nxe-ps5/bigapp/private/av2/upstream/PS5_Mesa/include'
ENGMEDIA = '/home/builder/s1/engine/media'
def say(*a): print(*a, flush=True)
if not Path('/home/builder/s1/.launche-marker').exists(): sys.exit('BLOCKED: /home/builder/s1 is not the s3.5 overlay (no .launche-marker)')
line = (GPU / 'fetch/hwservice-compile.txt').read_text().splitlines()[0]   # the tree's own compile line (s2-gpu fetched it)
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
for f in ('OmniHwService.cpp', 'OmniAbrSwitch.h', 'OmniHwService.h', 'OmniVideoStats.h', 'OmniHdrPreference.h', 'OmniGpuVideo.h', 'OmniGpuVideo.cpp', 'OmniGpuVideoShader.h', 'OmniGpuVideoShaderV10.h', 'OmniSwsEmu10.h'):   # s3.2: this folder's sources
    shutil.copyfile(N / 'engine/media' / f, W / 'media' / f)
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
        ("'label': 'omni-native-s1c'", "'label': 'omni-launch-rc1', 'launch': 'combined launch candidate: s3.5-hdr + OMNI_GPU_VERIFY10_V1 + OMNI_ABR_SWITCH_V1 + OMNI_JANK_V1/OMNI_PAINT_HOLD_V1 + OMNI_ACK_V1 title', 's35': 'HDR10 output: OMNI_GPU_PRESENT_V4 (HDR10 swapchain via the private VideoOut WSI member, Off/Auto/On, SDR fallback, FPS_V3) + OMNI_GPU_VIDEO_V4 (PQ layer: HDR10 kept, HLG -> PQ) + OMNI_GPU_HDR_V1 (hole-punch staging) + OMNI_HDR_CAPS_V1 (what pages are told)', 's34d': 'OMNI_DARK_APPEARANCE_EMU_V1 (matchMedia prefers-color-scheme follows Dark mode)', 's34c': 'omni-video-4k60 01-03+05: OMNI_GPU_VIDEO_V3 + OMNI_GPU_PRESENT_V3 (shared device, in place, FPS_V2) + hole-eligibility probe', 's34b': 'OMNI_DARK_STANDARD_V1 (own dark theme first, invert filter last, Dark Reader add-on hook)', 's34': 'CLEAN4 integration (native quick bar/Options/Apps, media stats + HDR preference bridge, downloads readiness C-1, card ports C-2) + OMNI_DARK_VIDEO_PLANE_V1 (YouTube start stall) + OMNI_GPU_SURFACE_PAIR_V1 + OMNI_GPU_REGION_REUSE_V1 + YTTL fps probe; title only, the child is built before every patch', 'pointer': 'OMNI_POINTER_CROSS_V1 (Cross at the pointer while the pointer leads; title only, the child is built before the patch)', 's32': 'OMNI_GPU_VIDEO_V2 + OMNI_GPU_PRESENT_V2 + OMNI_VIDEO_FPS_V1 (4K60 video path; HDR phase 2 behind the hdr flag word), off unless their flags', 's31b': 'jit2 build 6: OMNI_NO_VIEW_TRANSITION_V1 + OMNI_SOAK_READ_V1 + OMNI_YT_TIMELINE_V1 (flag-only)', 's3': 'OMNI_NO_ACCEL_CANVAS_V1 + OMNI_ADDONS_V1 + OMNI_VAULT_V2 + OMNI_PAGES_V1 + OMNI_JSC_JIT_V3 (JIT default off)', 's31': 'audit OS-001 OMNI_SEC_PNA_CONNECT_V1 + OS-002 vault read errors + jit2 build 4 (OMNI_EMUTLS_ROUNDS_V1, OMNI_CRASH_V2)', 'gpu': 'OMNI_GPU_VIDEO_V2 + OMNI_GPU_PRESENT_V2, off unless their flags', 'hub': 'OMNI_HUB_CARDS_V1', 'hud': 'OMNI_HUD_ASTRA_V1'"),
        ("shutil.copyfile(icon, PKG / 'sce_sys/icon0.png')",
         "shutil.copyfile(icon, PKG / 'sce_sys/icon0.png')\n"
         "# s3 OMNI_PAGES_V1: the built-in pages at /app0/pages (ENGINE-CONTRACT 1: never dev/, tests, build scripts) + the add-ons page\n"
         "_skip = lambda n: n in ('dev', 'test-evidence', 'node_modules') or n.startswith(('test_bundle', 'build_bundle')) or n.endswith('.cjs')\n"
         "shutil.copytree(OUTS / 'codex-ui/20261104-ui-clean4-final-pages/proposed/pages', PKG / 'pages', ignore=lambda d, names: [n for n in names if _skip(n)])   # s3.4: Astra's final pages (add-ons page included)\n"
         "print('pages packaged:', sum(1 for _ in (PKG / 'pages').rglob('*') if _.is_file()), 'files', flush=True)"),
        ("run([LLD, *script, f'@{B}/link-{pass_name}.rsp']", "run([LLD, '--threads=8', *script, f'@{B}/link-{pass_name}.rsp']"),
        ("for src in ['OmniNativeTitle.cpp', 'NativeLauncherState.cpp', 'NativeLibc.cpp', 'NativeFilesBroker.cpp']:",
         "for src in ['OmniNativeTitle.cpp', 'NativeLauncherState.cpp', 'NativeLibc.cpp', 'NativeFilesBroker.cpp', 'OmniGpuPresent.cpp', 'NativeEmutls.cpp']:   # s2: GPU part 2; s3.1: jit2 OMNI_EMUTLS_ROUNDS_V1"),
        # s3.2: SDL_FreeSurface joins the wraps (the window surface's GPU import goes before SDL frees it)
        ("MY_WRAPS = ['main', ", "MY_WRAPS = ['SDL_Init', 'SDL_Quit', 'SDL_UpdateWindowSurface', 'SDL_UpdateWindowSurfaceRects', 'SDL_FreeSurface', 'main', "),
        # s3.5-hdr: the private HDR RADV archive (one member differs from the shared one: the VideoOut WSI, hash-pinned)
        ("RADV = AV2 / 'toolchain/build-radv/src/amd/vulkan/libvulkan_radeon.a'",
         "RADV = HERE / 'radv/libvulkan_radeon-hdr-wsi.a'   # s3.5-hdr: Ex-Box PPSA99736's archive (shared 1f53ac68 + the HDR VideoOut WSI member)\n"
         "if hashlib.sha256(RADV.read_bytes()).hexdigest() != '2bb567dab75d52ae30f0ba157d701f60b368a2f1d451bdd358dc837b5e8a704e': raise SystemExit('BLOCKED: the private HDR RADV archive is not 2bb567da')"),
        # s3.5-hdr: the title's OWN param.json must declare HDR (attribute bit 0x20000000, psdevwiki ATTRIBUTE flag 30; the
        # October test's 1 -> 536870913 on the shared loader profile). Omni's file already has it (0x62000000): checked, not changed.
        ("(PKG / 'sce_sys/param.json').write_text(json.dumps(param, indent=2) + '\\n')",
         "assert param['attribute'] & 0x20000000, 'param.json attribute lacks the HDR bit 0x20000000'\n"
         "print('param.json attribute 0x%08x: HDR bit 0x20000000 set (the title\\'s own file)' % param['attribute'], flush=True)\n"
         "(PKG / 'sce_sys/param.json').write_text(json.dumps(param, indent=2) + '\\n')")]
for a, z in subs:
    if b.count(a) != 1: sys.exit(f'BLOCKED: build.py anchor not found once: {a[:70]}')
    b = b.replace(a, z)
(N / 'build.py').write_text(b.replace('f.read(1 << 22)', 'f.read(1 << 20)'))   # 9P reads: smaller chunks
for d in ('stubs', 'src'):
    if (N / d).exists(): shutil.rmtree(N / d)
    shutil.copytree(S1C / d, N / d)
shutil.copytree(S1C / 'tools', N / 'tools', dirs_exist_ok=True)
for f in ('OmniNativeTitle.cpp', 'OmniGpuPresent.cpp', 'OmniPqOutShader.h', 'NativeEmutls.cpp', 'OmniHdrPolicy.h'):   # s3.2: + the PQ shader header; s3.5: + OmniHdrPolicy.h
    shutil.copyfile(N / 'src-title' / f, N / 'src' / f)
say('build.py written; tools/ stubs/ src/ from s1c; src/OmniNativeTitle.cpp + OmniGpuPresent.cpp + OmniPqOutShader.h + NativeEmutls.cpp from src-title')
