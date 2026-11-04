#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Omnibloom: reproducible rebuild of java-worker.elf (the JDownloader 2 console engine).

Replays, from pinned inputs, the exact build chain the downloader chat used on
2026-10-26 (packages jd-002 -> jd-008), in a fresh private WSL tree. Every relink
stage re-checks the previous stage's ELF against its original sha256, so the first
divergence (if any) is pinpointed. If a stage diverges, the chain is re-run in
non-strict mode (only the literal original-hash check is dropped; the "relink is
deterministic" check stays) so a usable final ELF is still produced.

Runs inside WSL only. Never touches the console or the original trees.
Usage: replay.py <recipe_dir> <original_native_build_dir> <windows_status_dir>
"""
import hashlib, json, os, re, shutil, subprocess, sys, time
from pathlib import Path

RECIPE = Path(sys.argv[1]); ORIG = Path(sys.argv[2]); WINOUT = Path(sys.argv[3])
N = os.environ.get('OMNIBLOOM_JD_RUN', '001')
BUILD = Path(f'/var/tmp/omnibloom-jd-build-{N}')
W = Path(f'/var/tmp/omnibloom-jd-work-{N}')
SOURCE_DATE = '2026-10-26T06:26:45Z'   # "built on" string inside the original ELF
VERSION_OPT = 'adhoc.root.openjdk-b219cdec88ca2e165711f63b8158ab78303facc8'
ORIGINAL = {
 'jd-002': '4d7b3c4df1a5b50a36c540bd98a2f3bcc8af45cdf8741846fc5de29e02069cc0',
 'jd-003': '7e5d9cb2a8e201ddd0a8e464548919f231f36e5f51a06e5088aebade8bb4880e',
 'jd-004': '399afe234b5a8e2ebf272374afe263deb21576755f8a4e4143de847372923c50',
 'jd-005': 'ab87a9feb618b5b6c29c3e15c7a11889733706301360a9305f38b1f32dc9dacd',
 'jd-006': 'e7bc9a7efaaa1a82a05d09fb65e11df8f2ee7fed291ce4d8a3409852046002c0',
 'jd-007': '3f78951c09fb9ce686b6031d8552e57461a3853a9ae48f0a0acae769e0e40e49',
 'jd-008': 'd761c256a9c1153b7e04aa87d2cff75531bd1631b1fa3e66f5185798f7429c2e',
 'jd-002-zip': '81e50f97f24b256db9cd4b3a35d356796c4d24459afd3806e4b40495b9864463',
 'jd-002-manifest': 'f09545420a1c48ff3d3cfb3062d06bf2c62a567489781cad1e1c46d43eaeb5fd',
}
STATUS = {'run': N, 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'build_root': str(BUILD),
          'work': str(W), 'steps': [], 'state': 'RUNNING'}

def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        while b := f.read(1 << 20): h.update(b)
    return h.hexdigest()

def save():
    WINOUT.mkdir(parents=True, exist_ok=True)
    (WINOUT / f'replay-status-{N}.json').write_text(json.dumps(STATUS, indent=2) + '\n')

def step(name, argv, cwd=None, env=None, check=True, timeout=7200):
    t = time.time(); rec = {'name': name, 'argv': [str(a) for a in argv], 'started': time.strftime('%H:%M:%SZ', time.gmtime())}
    STATUS['steps'].append(rec); STATUS['current'] = name; save()
    log = W / 'driver-logs' / f'{name}.log'; log.parent.mkdir(exist_ok=True)
    with open(log, 'w') as f:
        p = subprocess.run([str(a) for a in argv], cwd=cwd or W, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=timeout)
    rec.update(exit=p.returncode, seconds=round(time.time() - t))
    if p.returncode != 0:
        rec['log_tail'] = log.read_text(errors='replace')[-3000:]
    save()
    if check and p.returncode != 0:
        raise RuntimeError(f'{name} failed ({p.returncode})')
    return p.returncode

def put(src, name=None):
    shutil.copyfile(src, W / (name or Path(src).name))

def stage_sources(pkg, names):
    for n in names:
        frozen = ORIG / 'packages' / pkg / 'source' / n
        put(frozen if frozen.exists() else ORIG / n, n)

def main():
    if BUILD.exists() or W.exists():
        raise SystemExit(f'{BUILD} or {W} already exists; set OMNIBLOOM_JD_RUN to a new number')
    W.mkdir(parents=True)
    # 0. Environment record
    env_info = {}
    for k, cmd in {'whoami': ['whoami'], 'clang21': ['/usr/lib/llvm-21/bin/clang', '--version'], 'nproc': ['nproc'],
                   'python': ['python3', '--version'], 'uname': ['uname', '-r']}.items():
        env_info[k] = subprocess.run(cmd, capture_output=True, text=True).stdout.strip().splitlines()[0]
    STATUS['environment'] = env_info; save()
    # 1. Scripts: top-level originals, then the jd-002 frozen ones over them
    for p in ORIG.glob('*'):
        if p.suffix in ('.py', '.cpp', '.hpp', '.h') and p.is_file(): put(p)
    stage_sources('jd-002', ['java_worker.cpp', 'package_payload.py', 'build_step.py', 'resident_spec.py'])
    (W / 'downloads').symlink_to(ORIG / 'downloads', target_is_directory=True)
    cons = W.parent / 'jd-consumer'
    if not cons.exists(): cons.mkdir()
    shutil.copyfile(ORIG / 'packages/jd-002/source/NativeProviderProbe.java', cons / 'NativeProviderProbe.java')
    # Recipe overrides: build root from env; extra configure arguments for exact version/date strings
    pl = (W / 'prepare_linux.py').read_text().replace("Path('/var/tmp/omni-jd-native-20261026-001')", f"Path('{BUILD}')")
    (W / 'prepare_linux.py').write_text(pl)
    bs = (W / 'build_step.py').read_text()
    bs = bs.replace("'--with-jvm-features=-dtrace']", "'--with-jvm-features=-dtrace','--with-source-date=" + SOURCE_DATE +
                    "','--with-build-user=root','--with-version-opt=" + VERSION_OPT + "']")
    assert '--with-source-date' in bs
    (W / 'build_step.py').write_text(bs)
    py = ['python3', '-I']
    # 2. Inputs, port patches, private adaptations
    step('prepare', [*py, W / 'prepare_linux.py'])
    step('adapt-linux', [*py, W / 'adapt_linux.py'])
    step('fix-private-sdk', [*py, W / 'fix_private_sdk.py'])
    step('fix-link-response', [*py, W / 'fix_link_response.py'])
    for fx in ('fix_awt_printing', 'fix_awt_fontpath', 'fix_awt_sound', 'fix_awt_x11', 'fix_awt_font_dependency'):
        step(fx, [*py, W / f'{fx}.py'])
    # 3. OpenJDK build (configure uses --with-jobs=4: at most half of this PC's cores)
    for s in ('autoconf-001', 'configure-004', 'hotspot-001', 'base-001', 'desktop-001', 'modules-001'):
        step(s, ['python3', W / 'build_step.py', s], timeout=10800)
    step('resident-spec', [*py, W / 'resident_spec.py'])
    # 4. jd-002: runtime image + first ELF
    step('package-jd-002', ['python3', W / 'build_step.py', 'package-jd-002'], timeout=10800)
    step('export-jd-002', [*py, W / 'export_image.py', 'jd-002'])
    j2 = W / 'packages/jd-002'
    cmp = STATUS.setdefault('compare', {})
    cmp['jd-002'] = {'elf': sha(j2 / 'java-worker.elf'), 'zip': sha(j2 / 'native-image.zip'), 'manifest': sha(j2 / 'image-manifest.json')}
    cmp['jd-002']['elf_match'] = cmp['jd-002']['elf'] == ORIGINAL['jd-002']
    cmp['jd-002']['zip_match'] = cmp['jd-002']['zip'] == ORIGINAL['jd-002-zip']
    cmp['jd-002']['manifest_match'] = cmp['jd-002']['manifest'] == ORIGINAL['jd-002-manifest']
    save()
    # 5. Relink chain jd-003 .. jd-008
    chain = [
        ('jd-003', 'relink_telemetry.py', ['java_worker.cpp']),
        ('jd-004', 'relink_deadlines.py', ['java_worker.cpp']),
        ('jd-005', 'relink_filesystem.py', ['filesystem_compat.cpp', 'test_filesystem_compat.cpp']),
        ('jd-006', 'relink_sampling.py', ['java_worker.cpp', 'test_metadata_sampler.cpp']),
        ('jd-007', 'relink_own_uid.py', ['java_worker.cpp', 'own_uid.hpp', 'test_own_uid.cpp']),
        ('jd-008', 'build_space_runtime.py', ['space_compat.cpp', 'test_space_compat.cpp', 'ps5MountSnapshot.h', 'test_mount_snapshot.cpp']),
    ]
    strict = True
    for pkg, script, srcs in chain:
        stage_sources(pkg, [script, *srcs])
        text = (W / script).read_text()
        if not strict:
            text = re.sub(r"==\s*'[0-9a-f]{64}'", '', text)
            (W / script).write_text(text)
        rc = step(f'relink-{pkg}' + ('' if strict else '-nonstrict'), [*py, W / script], check=False)
        if rc != 0 and strict:
            STATUS.setdefault('divergence', []).append({'at': pkg, 'reason': 'previous stage ELF differs from the original (strict hash check failed)'})
            failed = W / 'packages' / pkg
            if failed.exists(): failed.rename(W / 'packages' / f'{pkg}-strict-failed')
            strict = False
            text = re.sub(r"==\s*'[0-9a-f]{64}'", '', text); (W / script).write_text(text)
            step(f'relink-{pkg}-nonstrict', [*py, W / script])
        elif rc != 0:
            raise RuntimeError(f'{pkg} failed in non-strict mode')
        cmp[pkg] = {'elf': sha(W / 'packages' / pkg / 'java-worker.elf')}
        cmp[pkg]['match'] = cmp[pkg]['elf'] == ORIGINAL[pkg]
        save()
    # 6. Copy results to Windows
    final = W / 'packages/jd-008'
    dest = WINOUT.parent / 'build' / f'run-{N}'; dest.mkdir(parents=True, exist_ok=True)
    for p in (final / 'java-worker.elf', final / 'export-receipt.json', final / 'link-command.json',
              j2 / 'native-image.zip', j2 / 'image-manifest.json', j2 / 'build-receipt.json', W / 'linux-build-paths.json'):
        shutil.copyfile(p, dest / (p.parent.name + '--' + p.name if p.parent.name.startswith('jd-') else p.name))
    STATUS['final'] = {'elf': cmp['jd-008']['elf'], 'matches_installed_console_elf': cmp['jd-008']['match'],
                       'image_zip_matches': cmp['jd-002']['zip_match']}
    STATUS['state'] = 'DONE'; STATUS['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()); save()

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        STATUS['state'] = 'FAILED'; STATUS['error'] = repr(e); save(); raise
