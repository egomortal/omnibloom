#!/usr/bin/env python3
"""omni-native-s1 (sec-job2): sec1 rebuilt on the s1 in-tree engine (see manifest). Previously:
omni-native-sec1 (sec-job1): s1b + OMNI_SEC_LOCALHOST_V1 shell switch/notice (engine overlay changes/sec1-shell)
+ the security library updates (OpenSSL 3.5.9, curl 8.23.0, libpng 1.6.59, libxml2 2.13.9, FFmpeg 7.1.5) from the
private stage OMNI_SECLIBS (default /home/builder/omni-seclibs/stage/user/homebrew/lib), never the SDK's copies.
omni-native-s1b: s0c + OMNI_FILES_BROKER_V1 (USB drives through the omni-files broker).
omni-native-s0c: Omni's UI process as the native title PPSA99732 (runs in WSL, via
outputs/build-omni-native-s0c.sh). LOCAL BUILD ONLY: never touches the console.

Inputs (all read-only): candidate 56c's engine link (DL1 link receipt + 56c's replaced objects),
Ex-Box's native toolchain (nxe-ps5/bigapp/private/av2: native-sdk prospero-clang/lld, app_crt.o,
ps5-native-tool, libc-a.prx, static RADV) and the Oct-20 native-title fixes (omni-browser/tools/native-title).
Steps: compile the native sources -> link pass 1 -> import check + local map from pass 1 ->
link pass 2 -> exports/undefined checks -> ps5-native-tool link -> layout guard (refuses to package
on failure) -> FSELF sign -> package out/PPSA99732.
"""
import hashlib, json, os, re, shlex, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTS = HERE.parent
ROOT = OUTS.parent
AV2 = ROOT / 'nxe-ps5/bigapp/private/av2'
SDK = AV2 / 'toolchain/native-sdk'
UP = AV2 / 'upstream/PS5_Vulkan'
NATIVE = UP / 'tooling/native'
SMOKE = AV2 / 'title-smoke'
RADV = HERE / 'radv/libvulkan_radeon-hdr-wsi.a'   # s3.5-hdr: Ex-Box PPSA99736's archive (shared 1f53ac68 + the HDR VideoOut WSI member)
if hashlib.sha256(RADV.read_bytes()).hexdigest() != '2bb567dab75d52ae30f0ba157d701f60b368a2f1d451bdd358dc837b5e8a704e': raise SystemExit('BLOCKED: the private HDR RADV archive is not 2bb567da')
VKH = AV2 / 'upstream/PS5_Mesa/include'
TOOL = SMOKE / 'host/ps5-native-tool'
LIBC_PRX = SMOKE / 'runtime/libc-a.prx'
APP_CRT = SMOKE / 'obj/app_crt.o'
AGC_STUBS = [SMOKE / 'stubs/libSceAgc.so', SMOKE / 'stubs/libSceAgcDriver.so']
ENG = Path('/home/builder/s1/engine')   # s1: DL1 engine + dl2-candidate-57 + sec1-shell + sec-job2 engine-patches (in-tree build)
S1LC = HERE / 'link-command.json'   # s2: the s2 tree's link with the GPU objects   # make_link_command.py: the in-tree OmniEngine link
DL1 = ROOT / 'baseline/DL1/build'
HB = Path('/opt/ps5-payload-sdk/target/user/homebrew')
B = HERE / 'build'
PKG = HERE / 'out/PPSA99732'
LLVM = Path('/usr/lib/llvm-21/bin')
CXX = str(SDK / 'bin/prospero-clang++'); CC = str(SDK / 'bin/prospero-clang'); LLD = str(SDK / 'bin/prospero-lld')
NM = str(LLVM / 'llvm-nm'); READELF = str(LLVM / 'llvm-readelf'); OBJCOPY = str(LLVM / 'llvm-objcopy')
OLD, NEW = '/path/to/downloads/', '/path/to/downloads/'
log = []
def say(*a):
    line = ' '.join(str(x) for x in a); print(line, flush=True); log.append(line)
def run(cmd, out=None, check=True, **kw):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)
    if out: Path(out).write_text(r.stdout + r.stderr)
    if check and r.returncode:
        print((r.stdout + r.stderr)[-12000:]); raise SystemExit(f'FAILED ({r.returncode}): {" ".join(str(c) for c in cmd)[:300]}')
    return r
def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()

t0 = time.time()
B.mkdir(parents=True, exist_ok=True)
for f in [CXX, LLD, TOOL, LIBC_PRX, APP_CRT, RADV, *AGC_STUBS, S1LC]:
    if not Path(f).exists(): raise SystemExit(f'BLOCKED: missing {f}')

# 1. engine link inputs = DL1 link receipt with 56c's replaced objects
ln = json.loads(S1LC.read_text()); cwd = Path(ln['cwd'])
replaced = {}   # s1: the in-tree link already names every rebuilt object
fix = lambda s: s.replace(OLD, NEW)
objects, libs, wraps, dropped = [], [], [], []
cmd = ln['command']; i = 1
# libz.a: the whole RADV archive already carries zlib 1.3.1 (Mesa subproject); two copies are duplicates.
DROP = ('libc.a', 'libkernel.so', 'libGLESv2.so', 'libEGL.so', 'libz.a')
while i < len(cmd):
    a = fix(cmd[i]); i += 1
    if a in ('-o', '-include', '-mllvm', '-isystem', '-iquote', '-MF', '-MT', '-x', '-target', '-Xclang', '-Xlinker'): i += 1; continue
    if a.startswith('-Wl,'):
        for part in a[4:].split(','):
            if part.startswith('--wrap='): wraps.append(part)
        continue
    if a.startswith('-l'): libs.append(a); continue
    if a.startswith('-'): continue
    if not a.endswith(('.o', '.a', '.so')): raise SystemExit(f'BLOCKED: unexpected link argument {a!r}')
    p = a if a.startswith('/') else str(cwd / a)
    p = replaced.get(p, p)
    if Path(p).name in DROP: dropped.append(p); continue
    (objects if p.endswith('.o') else libs).append(p)
say(f'engine inputs: {len(objects)} objects, {len(libs)} libraries, wraps {wraps}; dropped {dropped}')
# resolve -lX to files (the payload driver's search path)
search = [HB / 'lib', Path('/opt/omni-build/sysroot/lib'), Path('/opt/ps5-payload-sdk/target/lib')]
# sec1: the updated security libraries come from the private stage, by name; everything else as before.
SECLIBS = Path(os.environ.get('OMNI_SECLIBS', '/home/builder/omni-seclibs/stage/user/homebrew/lib'))
SECNAMES = ['libssl.a', 'libcrypto.a', 'libcurl.a', 'libpng16.a', 'libpng.a', 'libxml2.a',
            'libavformat.a', 'libavcodec.a', 'libavutil.a', 'libswscale.a', 'libswresample.a']
for n in SECNAMES:
    if not (SECLIBS / n).exists(): raise SystemExit(f'BLOCKED: updated library missing: {SECLIBS / n}')
def secmap(path):
    p = Path(path)
    return str(SECLIBS / p.name) if p.parent == HB / 'lib' and p.name in SECNAMES else path
libs = [secmap(l) if not l.startswith('-l') else l for l in libs]
search = [SECLIBS] + search   # -lssl/-lcrypto/-lav*/-lsw* resolve to the stage first (it holds only the updated ones)
archives = []
for l in libs:
    if not l.startswith('-l'): archives.append(l); continue
    name = l[2:]
    hit = next((str(d / f'lib{name}.a') for d in search if (d / f'lib{name}.a').exists()), None)
    if not hit and (SDK / f'target/lib/lib{name}.so').exists(): continue  # a system module: the SDK stubs below
    if not hit: raise SystemExit(f'BLOCKED: cannot resolve {l} in {search}')
    archives.append(hit)
dropped += [a for a in archives if Path(a).name in DROP]; archives = [a for a in archives if Path(a).name not in DROP]
# /opt/omni-build/wkreq-sdr-rc7final.16vtJE/ is root-only (mktemp 0700 by the RC7 build), unreadable to
# the build helper's user: rebuild libWebKitRequirements.a with RC7's own recipe (build-rc7final.sh
# lines 46-49) from the 56c source tree, and require the DL1 receipt's exact hash.
# s1: the in-tree link names the sysroot's libWebKitRequirements.a; Omni's launcher is the engine's own ports/webkit-requirements
# (RC7's recipe, as DL1's rc7final archive was built), so that archive is rebuilt from /home/builder/s1/engine and used instead.
wr = ENG / 'ports/webkit-requirements'; wt = B / 'wkreq'; shutil.rmtree(wt, ignore_errors=True); wt.mkdir()
for f in ('process-launcher', 'launcher-child', 'support'):
    run(['/opt/ps5-payload-sdk/bin/prospero-clang++', '-std=c++17', '-O2', f'-I{wr}/include', f'-I{wr}/src', '-c', wr / f'src/{f}.cpp', '-o', wt / f'{f}.cpp.o'])
run(['/opt/ps5-payload-sdk/bin/prospero-ar', 'rcs', wt / 'libWebKitRequirements.a', *sorted(wt.glob('*.o'))])
archives = [str(wt / 'libWebKitRequirements.a') if Path(a).name == 'libWebKitRequirements.a' else a for a in archives]
WKREQ_SHA = sha(wt / 'libWebKitRequirements.a')
say(f'libWebKitRequirements.a rebuilt from the s1 engine ports: {WKREQ_SHA[:16]}')
seen = set(); archives = [a for a in archives if not (a in seen or seen.add(a))]

# 2. OmniMain.o: Omni's own sceSystemServiceLoadExec (decoder/audio release, then the system call)
# becomes __wrap_sceSystemServiceLoadExec, so the system function can be imported under its name.
main_o = next(o for o in objects if Path(o).name in ('OmniMain.o', 'OmniMain.cpp.o'))
defs = run([NM, '--defined-only', main_o]).stdout
if not re.search(r' T sceSystemServiceLoadExec$', defs, re.M): raise SystemExit('BLOCKED: OmniMain.o does not define sceSystemServiceLoadExec')
native_main = B / 'OmniMain.native.o'
# s0b: renamed to omni_impl_*; __wrap_sceSystemServiceLoadExec is OmniNativeTitle.cpp's (children stop first)
run([OBJCOPY, '--redefine-sym', 'sceSystemServiceLoadExec=omni_impl_sceSystemServiceLoadExec', main_o, native_main])
objects[objects.index(main_o)] = str(native_main)
say(f'OmniMain.o {sha(main_o)[:16]} -> OmniMain.native.o (LoadExec hook renamed)')

# 3. native sources
flags = ['-std=c++20', '-O2', '-Wall', '-Wextra', '-Wno-unused-parameter', '-fno-exceptions', '-fno-rtti', '-ffunction-sections', '-fdata-sections',
         '-D__PROSPERO__', f'-I{ENG}/ports/webkit-requirements/src', f'-I{ENG}/ports/webkit-requirements/include', f'-I{VKH}', f'-I{HB}/include']
mine = []
for src in ['OmniNativeTitle.cpp', 'NativeLauncherState.cpp', 'NativeLibc.cpp', 'NativeFilesBroker.cpp', 'OmniGpuPresent.cpp', 'NativeEmutls.cpp']:   # s2: GPU part 2; s3.1: jit2 OMNI_EMUTLS_ROUNDS_V1
    o = B / (Path(src).stem + '.o')
    run([CXX, *flags, '-I', HERE / 'src', '-c', HERE / 'src' / src, '-o', o], out=B / (Path(src).stem + '.compile.log'))
    mine.append(str(o))
run([CC, '-std=c11', '-O2', '-fPIC', '-c', HERE / 'stubs/libSceVideodec2_stub.c', '-o', B / 'libSceVideodec2_stub.o'])
vstub = B / 'libSceVideodec2.so'
run([LLD, '--shared', '-soname', 'libSceVideodec2.prx', '-o', vstub, B / 'libSceVideodec2_stub.o'])
# OMNI_S0_NO_VDEC_STUB=1: fallback build without the Videodec2 import (if the console refuses to load a
# title whose import table names libSceVideodec2 before sceSysmodule loads it); dlsym() then finds
# the decoder's functions in the loaded modules (sceKernelGetModuleList + sceKernelDlsym).
NO_VDEC = os.environ.get('OMNI_S0_NO_VDEC_STUB') == '1'
stubs = [*AGC_STUBS] if NO_VDEC else [*AGC_STUBS, vstub]
if NO_VDEC:
    flags.append('-DOMNI_S0_NO_VDEC_STUB=1')
    for src in ['OmniNativeTitle.cpp']:
        run([CXX, *flags, '-I', HERE / 'src', '-c', HERE / 'src' / src, '-o', B / (Path(src).stem + '.o')], out=B / (Path(src).stem + '.compile.log'))
say('Videodec2: ' + ('no import (dlsym from loaded modules only)' if NO_VDEC else 'linked imports via stubs/libSceVideodec2_stub.c (lazy: excluded from the start-up check)'))

# 4. RADV link recipe (our copy of radv-link.sh; its local map goes to build/)
env = dict(os.environ, OMNI_RADV_MAP=str(B / 'radv-platform-local.map'), PS5_CLANG='clang-21')
r = run(['bash', '-c', 'source "$1"; radv_link_recipe "$2" "$3" "$4" || exit 2; printf "%s\\0" "${radv_linker_script[@]}"; printf "\\1"; printf "%s\\0" "${radv_link_inputs[@]}"; printf "\\1"; printf "%s\\0" "${radv_link_flags[@]}"',
         '_', HERE / 'tools/radv-link.sh', UP, SDK, RADV], env=env)
script, rinputs, rflags = [[x for x in part.split('\0') if x] for part in r.stdout.split('\1')]
bound = {f.split('=', 1)[1].split('=')[0] for f in rflags if f.startswith('--defsym=')}
enosys = [f'--defsym={n}=omni_enosys_{n}' for n in ('readlink', 'link', 'symlink', 'fchown') if n not in bound]
say(f'radv recipe: {len(rflags)} flags; ENOSYS bindings: {enosys}')

MY_WRAPS = ['SDL_Init', 'SDL_Quit', 'SDL_UpdateWindowSurface', 'SDL_UpdateWindowSurfaceRects', 'SDL_FreeSurface', 'main', 'exit', '_exit', '_Exit', 'sceSystemServiceLoadExec', 'sigaction', 'dup', 'close', 'shm_open', 'connect', '__cxa_throw',
            'sceKeyboardInit', 'sceKeyboardOpen', 'sceKeyboardReadState', 'sceImeDialogInit', 'sceImeDialogGetResult', 'sceImeDialogTerm', 'sceImeDialogGetStatus',
            'isatty', 'mkstemp', 'fstatfs', 'fnmatch', 'gai_strerror', 'getnameinfo']
sdk_so = sorted(str(p) for p in (SDK / 'target/lib').glob('*.so'))
local_map = B / 'native-local.map'
def write_local(names):
    local_map.write_text('{\n    local:\n' + ''.join(f'        {n};\n' for n in sorted(names)) + '};\n')
WEAKDEFS = []
LOCAL = {'dlopen', 'dlsym', 'dlclose', 'dlerror', 'syscall', 'timegm', '___mb_cur_max', '_setjmp', '_longjmp', 'if_nametoindex', 'mkostemp', 'pipe2', 'catchReturnFromMain', 'omni_impl_sceSystemServiceLoadExec', 'omni_enosys_readlink', 'omni_enosys_link', 'omni_enosys_symlink', 'omni_enosys_fchown'}

def link(pass_name, extra_objects):
    write_local(LOCAL)
    # -T must be on the command line itself: the SDK's prospero-lld wrapper adds its own payload
    # script (ldscripts/elf_x86_64.x) unless it sees -T among its arguments (not inside an @file).
    args = ['--eh-frame-hdr', '--error-limit=0', '--gc-sections', '--strip-debug',
            *wraps, *[f'--wrap={w}' for w in MY_WRAPS], *rflags, *enosys, *WEAKDEFS,
            '--version-script', NATIVE / 'app-symbols.map', '--version-script', local_map,
            '--exclude-libs=ALL', '-e', '_start', '-o', B / 'llvm-pie.elf',
            APP_CRT, *mine, *extra_objects, *objects,
            '--start-group', *archives, '--end-group',
            *stubs, *rinputs, '--as-needed', *sdk_so]
    (B / f'link-{pass_name}.rsp').write_text('\n'.join(shlex.quote(str(a)) for a in args))
    r = run([LLD, '--threads=8', *script, f'@{B}/link-{pass_name}.rsp'], out=B / f'link-{pass_name}.log', check=False)
    if r.returncode:
        text = r.stdout + r.stderr
        und = sorted(set(re.findall(r'undefined symbol: (.+)', text))); dup = sorted(set(re.findall(r'duplicate symbol: (.+)', text)))
        (B / f'link-{pass_name}-summary.json').write_text(json.dumps({'undefined': und, 'duplicate': dup}, indent=1))
        print(text[-8000:]); raise SystemExit(f'LINK {pass_name} FAILED: {len(und)} undefined, {len(dup)} duplicate (build/link-{pass_name}.log)')
    say(f'link {pass_name}: ok ({(B / "llvm-pie.elf").stat().st_size} bytes)')

def dynsyms(path):
    out = run([READELF, '--dyn-syms', '-W', path]).stdout
    rows = []
    for line in out.splitlines():
        f = line.split()
        if len(f) >= 8 and f[0].endswith(':') and f[0][:-1].isdigit():
            rows.append(dict(type=f[3], bind=f[4], ndx=f[6], name=f[7].split('@')[0]))
    return rows

# 5. pass 1 (empty import check), then the generated check + local map
(B / 'import_check.cpp').write_text('extern "C" unsigned omni_native_check_imports(void (*)(const char*, ...)) { return 0; }\n')
run([CXX, *flags, '-c', B / 'import_check.cpp', '-o', B / 'import_check.o'])
link('pass1', [str(B / 'import_check.o')])
rows = dynsyms(B / 'llvm-pie.elf')
exported = sorted({r['name'] for r in rows if r['ndx'] != 'UND' and r['name'] and r['name'] != '_start'})
if exported:
    say(f'pass 1 exported {len(exported)} names; making them local: {exported[:20]}')
    LOCAL |= set(exported)
stub_types = {}
for so in [*sdk_so, *map(str, stubs)]:
    for r_ in dynsyms(so):
        if r_['ndx'] != 'UND': stub_types.setdefault(r_['name'], r_['type'])
lazy = {r_['name'] for r_ in dynsyms(vstub) if r_['ndx'] != 'UND'}  # never start-up checked
manifest_extra = {'videodec2': 'dlsym only' if NO_VDEC else 'linked imports'}
imports = sorted({(r_['name'], 'OBJECT' if stub_types.get(r_['name']) == 'OBJECT' else 'FUNC') for r_ in rows
                  if r_['ndx'] == 'UND' and r_['name'] and r_['bind'] != 'WEAK' and r_['name'] not in lazy})
(B / 'imports.json').write_text(json.dumps(imports, indent=0))
weak_free = sorted({r_['name'] for r_ in rows if r_['ndx'] == 'UND' and r_['bind'] == 'WEAK' and r_['name'] and r_['name'] not in stub_types})
WEAKDEFS.extend(f'--defsym={n}=' + ('ADDR(.text)+SIZEOF(.text)' if n == 'etext' else '0') for n in weak_free)
LOCAL |= set(weak_free)
say(f'weak undefined names with no system provider, bound as ELF leaves them (0; etext = end of .text): {weak_free}')
providers = {}
for so in [*sdk_so, *map(str, stubs)]:
    for r_ in dynsyms(so):
        if r_['ndx'] != 'UND': providers.setdefault(r_['name'], Path(so).name)
by = {}
for n, _ in imports: by.setdefault(providers.get(n, '?'), []).append(n)
(B / 'imports-by-stub.json').write_text(json.dumps(by, indent=1))
say('startup-checked imports by stub: ' + ', '.join(f'{k}={len(v)}' for k, v in sorted(by.items())))
risky = {k: v for k, v in by.items() if k in ('libScePosixForWebKit.so', 'libkernel_sys.so', 'libc_stub_weak.so', 'libkernel_stub_weak.so', '?')}
if risky: say(f'NOTE imports from stubs known to leave null imports in titles: {risky}')
run(['python3', HERE / 'tools/gen_import_check.py', B / 'imports.json', B / 'import_check.cpp'])
run([CXX, *flags, '-c', B / 'import_check.cpp', '-o', B / 'import_check.o'])
link('pass2', [str(B / 'import_check.o')])
rows = dynsyms(B / 'llvm-pie.elf')
exported = sorted({r['name'] for r in rows if r['ndx'] != 'UND' and r['name'] and r['name'] != '_start'})
if exported: raise SystemExit(f'REFUSED: the title still exports {exported[:20]}')
und = {r['name'] for r in rows if r['ndx'] == 'UND'}
bad = sorted(und & {'exit', '_exit', '_Exit', 'sceKeyboardInit', 'sceKeyboardOpen', 'sceKeyboardReadState', 'sceImeDialogInit', 'sceImeDialogGetResult', 'sceImeDialogTerm', 'sceImeDialogGetStatus'})
if bad: raise SystemExit(f'REFUSED: the title still imports {bad} directly (must go through the wraps)')
say(f'pass 2: {len(und)} imports ({len(imports)} checked at start, {len(lazy & und)} lazy Videodec2); no direct exit/_exit/keyboard/IME imports (dup only behind __wrap_dup)')
# the title must have no undefined references to unresolvable names other than imports
phdrs = run([READELF, '-l', '-W', B / 'llvm-pie.elf']).stdout
(B / 'llvm-pie-phdrs.txt').write_text(phdrs)
say('pass 2 program headers: ' + ', '.join(l.split()[0] for l in phdrs.splitlines() if l.strip().startswith(('LOAD', 'TLS', 'DYNAMIC', 'GNU_'))))

# 6. layout guard on the intermediate PIE (executable sections), then convert, then guard the eboot
lay = run(['python3', HERE / 'tools/check_native_layout.py', B / 'llvm-pie.elf', '--policy', 'none', '--sections', '--report', B / 'layout-pie.json'], check=False, out=B / 'layout-pie.log')
if lay.returncode: raise SystemExit('REFUSED TO PACKAGE: llvm-pie.elf layout: ' + (B / 'layout-pie.log').read_text().strip())
pie = json.loads((B / 'layout-pie.json').read_text())
say(f"layout (llvm-pie.elf): no overlapping LOADs; {len(pie['executable_sections'])} executable sections, all inside the text LOAD: {pie['executable_sections']}")
run([TOOL, 'link', '--in', B / 'llvm-pie.elf', '--out', B / 'eboot.elf', '--stub-dir', SDK / 'target/lib', *sum([['--stub', s] for s in stubs], []),
     '--module-sdk', '0x02000009', '--companion-sdk', '0x08050001', '--file-name', 'eboot.elf'], out=B / 'convert.log')
lay = run(['python3', HERE / 'tools/check_native_layout.py', B / 'eboot.elf', '--policy', 'omni', '--sections', '--report', B / 'layout-check.json'], check=False, out=B / 'layout-check.log')
if lay.returncode:
    raise SystemExit('REFUSED TO PACKAGE: layout check failed: ' + (B / 'layout-check.log').read_text().strip())
loads = json.loads((B / 'layout-check.json').read_text())['loads']
say('layout check (eboot.elf, policy omni): PASSED; LOAD sizes MiB: ' + ', '.join(f"{max(l['filesz'], l['memsz']) / 2**20:.1f}" for l in loads))

# 7. sign and package
if PKG.exists(): shutil.rmtree(PKG)
(PKG / 'sce_sys').mkdir(parents=True); (PKG / 'sce_module').mkdir()
run([TOOL, 'self', '--sign', '--in', B / 'eboot.elf', '--out', PKG / 'eboot.bin', '--magic', '0x1D3D154F'], out=B / 'sign.log')
run([TOOL, 'self', '--inspect', '--file', PKG / 'eboot.bin'], out=B / 'self-inspect.txt')
shutil.copyfile(LIBC_PRX, PKG / 'sce_module/libc.prx')
# s0b: the Oct-20 param.json (the one that launched on the console; s0's minimal file was never
# tried there), with the 1 GiB flexible memory budget set explicitly.
param = json.loads((OUTS / 'omni-native-title/PPSA99732/sce_sys/param.json').read_text())
param['kernel'] = dict(param.get('kernel', {}), flexibleMemorySize=1073741824)
assert param['titleId'] == 'PPSA99732'
assert param['attribute'] & 0x20000000, 'param.json attribute lacks the HDR bit 0x20000000'
print('param.json attribute 0x%08x: HDR bit 0x20000000 set (the title\'s own file)' % param['attribute'], flush=True)
(PKG / 'sce_sys/param.json').write_text(json.dumps(param, indent=2) + '\n')
# s0c: the app icon comes from branding/ (the user's chosen Omni icon, 512x512) from now on.
icon = ROOT / 'branding/icon0.png'
if not icon.exists(): raise SystemExit(f'BLOCKED: missing {icon}')
shutil.copyfile(icon, PKG / 'sce_sys/icon0.png')
# s3 OMNI_PAGES_V1: the built-in pages at /app0/pages (ENGINE-CONTRACT 1: never dev/, tests, build scripts) + the add-ons page
_skip = lambda n: n in ('dev', 'test-evidence', 'node_modules') or n.startswith(('test_bundle', 'build_bundle')) or n.endswith('.cjs')
shutil.copytree(OUTS / 'codex-ui/20261104-ui-clean4-final-pages/proposed/pages', PKG / 'pages', ignore=lambda d, names: [n for n in names if _skip(n)])   # s3.4: Astra's final pages (add-ons page included)
print('pages packaged:', sum(1 for _ in (PKG / 'pages').rglob('*') if _.is_file()), 'files', flush=True)
files = {str(p.relative_to(PKG)): sha(p) for p in sorted(PKG.rglob('*')) if p.is_file()}
manifest = {'label': 'omni-launch-rc1', 'launch': 'combined launch candidate: s3.5-hdr + OMNI_GPU_VERIFY10_V1 + OMNI_ABR_SWITCH_V1 + OMNI_JANK_V1/OMNI_PAINT_HOLD_V1 + OMNI_ACK_V1 title', 's35': 'HDR10 output: OMNI_GPU_PRESENT_V4 (HDR10 swapchain via the private VideoOut WSI member, Off/Auto/On, SDR fallback, FPS_V3) + OMNI_GPU_VIDEO_V4 (PQ layer: HDR10 kept, HLG -> PQ) + OMNI_GPU_HDR_V1 (hole-punch staging) + OMNI_HDR_CAPS_V1 (what pages are told)', 's34d': 'OMNI_DARK_APPEARANCE_EMU_V1 (matchMedia prefers-color-scheme follows Dark mode)', 's34c': 'omni-video-4k60 01-03+05: OMNI_GPU_VIDEO_V3 + OMNI_GPU_PRESENT_V3 (shared device, in place, FPS_V2) + hole-eligibility probe', 's34b': 'OMNI_DARK_STANDARD_V1 (own dark theme first, invert filter last, Dark Reader add-on hook)', 's34': 'CLEAN4 integration (native quick bar/Options/Apps, media stats + HDR preference bridge, downloads readiness C-1, card ports C-2) + OMNI_DARK_VIDEO_PLANE_V1 (YouTube start stall) + OMNI_GPU_SURFACE_PAIR_V1 + OMNI_GPU_REGION_REUSE_V1 + YTTL fps probe; title only, the child is built before every patch', 'pointer': 'OMNI_POINTER_CROSS_V1 (Cross at the pointer while the pointer leads; title only, the child is built before the patch)', 's32': 'OMNI_GPU_VIDEO_V2 + OMNI_GPU_PRESENT_V2 + OMNI_VIDEO_FPS_V1 (4K60 video path; HDR phase 2 behind the hdr flag word), off unless their flags', 's31b': 'jit2 build 6: OMNI_NO_VIEW_TRANSITION_V1 + OMNI_SOAK_READ_V1 + OMNI_YT_TIMELINE_V1 (flag-only)', 's3': 'OMNI_NO_ACCEL_CANVAS_V1 + OMNI_ADDONS_V1 + OMNI_VAULT_V2 + OMNI_PAGES_V1 + OMNI_JSC_JIT_V3 (JIT default off)', 's31': 'audit OS-001 OMNI_SEC_PNA_CONNECT_V1 + OS-002 vault read errors + jit2 build 4 (OMNI_EMUTLS_ROUNDS_V1, OMNI_CRASH_V2)', 'gpu': 'OMNI_GPU_VIDEO_V2 + OMNI_GPU_PRESENT_V2, off unless their flags', 'hub': 'OMNI_HUB_CARDS_V1', 'hud': 'OMNI_HUD_ASTRA_V1', 'jit': 'compiled in (baseline + regexp); off unless /data/omni/jsc-jit.flag', 'gamepad': 'OMNI_GAMEPAD_V1', 'wkreq_sha256': WKREQ_SHA, 'titleId': 'PPSA99732', 'status': 'packaged locally; NOT console validated',
            'childEngine': '/data/omni/native/omni-engine-child.elf (child/omni-engine-child.elf, OMNI_NATIVE_CHILD_V1) when installed, else /data/omni/omni-engine.elf', 'base': 'in-tree s1 engine (WebKit 539e0189f + Omni local + CVE fixes + JIT/gamepad; 57 + sec1-shell + sec-job2 shell) + s1b/sec1 native sources', 'seclibs': {n: sha(SECLIBS / n) for n in SECNAMES if (SECLIBS / n).exists() and not (SECLIBS / n).is_symlink()}, 'broker': '/data/omni/native/omni-files.elf (outputs/omni-files-broker/dist/omni-files.elf)', 'files': files,
            **manifest_extra, 'llvm_pie_sha256': sha(B / 'llvm-pie.elf'), 'eboot_elf_sha256': sha(B / 'eboot.elf'), 'seconds': round(time.time() - t0)}
(HERE / 'out/package-manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
say(f"eboot.bin {files['eboot.bin']}")
(B / 'build-summary.txt').write_text('\n'.join(log) + '\n')
print('Local native package built. No console installation, launch or runtime success claimed.')
