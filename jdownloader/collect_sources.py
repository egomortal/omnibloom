# SPDX-License-Identifier: GPL-3.0-or-later
"""Copy (read-only) every source the java-worker.elf / Java image build used into ./source/.
Inputs come from the downloader chat's folder; nothing there is changed."""
import difflib, hashlib, json, os, shutil, sys, tarfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
ORIG = Path(sys.argv[1])            # .../downloader-workspace/outputs/omni-jdownloader-overnight-20261026
NB = ORIG / 'native-build'
SRC = HERE / 'source'
if SRC.exists(): raise SystemExit('source/ exists; move it aside first')
(SRC / 'build').mkdir(parents=True); (SRC / 'engine').mkdir(); (SRC / 'openjdk-patches').mkdir(); (SRC / 'java').mkdir()
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
inv = {}
def cp(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dst); inv[str(dst.relative_to(HERE))] = sha(dst)
# build recipe scripts (stage-frozen versions win)
frozen = {'build_step.py': 'jd-002', 'package_payload.py': 'jd-002', 'resident_spec.py': 'jd-002',
          'relink_telemetry.py': 'jd-003', 'relink_deadlines.py': 'jd-004', 'relink_filesystem.py': 'jd-005',
          'relink_sampling.py': 'jd-006', 'relink_own_uid.py': 'jd-007', 'build_space_runtime.py': 'jd-008'}
for n in ['prepare_linux.py', 'adapt_linux.py', 'fix_private_sdk.py', 'fix_link_response.py', 'fix_awt_printing.py',
          'fix_awt_fontpath.py', 'fix_awt_sound.py', 'fix_awt_x11.py', 'fix_awt_font_dependency.py', 'export_image.py',
          'private-sdk-response-wrapper.py', 'acquire.py', *frozen]:
    p = NB / 'packages' / frozen[n] / 'source' / n if n in frozen else NB / n
    cp(p if p.exists() else NB / n, SRC / 'build' / n)
for n in ['awt-font-dependency.patch', 'awt-fontpath.patch', 'awt-printing.patch', 'awt-sound.patch', 'awt-x11-fonts.patch',
          'private-adaptations.patch', 'private-sdk-lld.patch', 'linux-build-paths.json']:
    cp(NB / n, SRC / 'build' / n)
# native entry and helpers: every stage's java_worker.cpp, final = jd-007 (used by jd-008)
for stage in ['jd-002', 'jd-003', 'jd-004', 'jd-006', 'jd-007']:
    cp(NB / 'packages' / stage / 'source' / 'java_worker.cpp', SRC / 'engine' / 'stages' / f'java_worker.{stage}.cpp')
cp(NB / 'packages/jd-007/source/java_worker.cpp', SRC / 'engine' / 'java_worker.cpp')
for stage, names in {'jd-005': ['filesystem_compat.cpp', 'test_filesystem_compat.cpp'], 'jd-006': ['test_metadata_sampler.cpp'],
                     'jd-007': ['own_uid.hpp', 'test_own_uid.cpp'],
                     'jd-008': ['space_compat.cpp', 'test_space_compat.cpp', 'ps5MountSnapshot.h', 'test_mount_snapshot.cpp']}.items():
    for n in names: cp(NB / 'packages' / stage / 'source' / n, SRC / 'engine' / n)
# OpenJDK source changes made by build_space_runtime.py (jd-008), as patches against the pinned tree
for n, rel in {'UnixFileSystem_md.c': 'src/java.base/unix/native/libjava/UnixFileSystem_md.c',
               'UnixNativeDispatcher.c': 'src/java.base/unix/native/libnio/fs/UnixNativeDispatcher.c',
               'BsdNativeDispatcher.c': 'src/java.base/bsd/native/libnio/fs/BsdNativeDispatcher.c'}.items():
    a = (NB / 'packages/jd-008/source' / (n + '.prior')).read_text().splitlines(True)
    b = (NB / 'packages/jd-008/source' / n).read_text().splitlines(True)
    out = SRC / 'openjdk-patches' / (n + '.jd-008.patch'); out.write_text(''.join(difflib.unified_diff(a, b, 'a/' + rel, 'b/' + rel)))
    inv[str(out.relative_to(HERE))] = sha(out)
# Java: provider probe, bridge v4 (installed), adapted upstream MyJDownloaderController
cp(NB / 'packages/jd-002/source/NativeProviderProbe.java', SRC / 'java' / 'NativeProviderProbe.java')
cp(ORIG / 'bridge-diagnostics/bridge-v4-001/OmniJDownloaderBridge.java', SRC / 'java' / 'OmniJDownloaderBridge.java')
cp(ORIG / 'bridge-diagnostics/bridge-v4-001/build-receipt.json', SRC / 'java' / 'bridge-v4-build-receipt.json')
cp(ORIG.parent / 'omni-jdownloader-prototype/java/upstream-adapted/org/jdownloader/api/myjdownloader/MyJDownloaderController.java',
   SRC / 'java' / 'upstream-adapted/org/jdownloader/api/myjdownloader/MyJDownloaderController.java')
# The Java port's own notices, unchanged, from the pinned port archive
with tarfile.open(NB / 'downloads/port.tar.gz') as t:
    for m in t.getmembers():
        base = m.name.split('/', 1)[-1]
        if m.isfile() and (base.upper().startswith(('THIRD_PARTY', 'LICENSE', 'NOTICE', 'COPYING')) or base in ('README.md',)) and base.count('/') == 0:
            data = t.extractfile(m).read(); out = HERE / 'notices' / 'ps5-java25-homebrew' / base
            out.parent.mkdir(parents=True, exist_ok=True); out.write_bytes(data); inv[str(out.relative_to(HERE))] = sha(out)
(HERE / 'source-inventory.json').write_text(json.dumps(inv, indent=1, sort_keys=True) + '\n')
print(len(inv), 'files')
