#!/usr/bin/env python3
"""s3: WebKit-side changes on the PRIVATE tree given as argv[1] (default /home/builder/s3). Idempotent (markers).
1. OMNI_JSC_JIT_V3 (omni-jit-fix/apply_jitfix.py, unchanged): the JIT pool is RWX once at reservation, no runtime
   permission flips (the JIT itself stays opt-in: /data/omni/jsc-jit.flag).
2. OMNI_NO_ACCEL_CANVAS_V1 safety net (omni-4k-vp9/patches/webcore-accel-safety-net.diff): with no shared
   PlatformDisplay, never take the Skia GL ImageBuffer backend (it would RELEASE_ASSERT in sharedDisplay()), and the
   WebProcess turns accelerated buffers off at start. Writes unified diffs into ../patches-webkit/."""
import difflib, os, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; N = HERE.parent; OUTS = N.parent
TREE = Path(sys.argv[1] if len(sys.argv) > 1 else '/home/builder/s3'); W = TREE / 'webkit/Source'
D = N / 'patches-webkit'; D.mkdir(exist_ok=True)
env = dict(os.environ, JF_PATCHDIR=str(D))
r = subprocess.run([sys.executable, str(OUTS / 'omni-jit-fix/apply_jitfix.py'), str(TREE)], capture_output=True, text=True, env=env)
print(r.stdout + r.stderr, end='')
if r.returncode: sys.exit('jitfix apply FAILED')
MARK = 'OMNI_NO_ACCEL_CANVAS_V1'
GUARD = '    if (!PlatformDisplay::sharedDisplayIfExists())   // OMNI_NO_ACCEL_CANVAS_V1: sharedDisplay() would RELEASE_ASSERT\n        return nullptr;\n'
def edit(path, fn):
    raw = path.read_bytes().decode('utf-8'); crlf = '\r\n' in raw; t = raw.replace('\r\n', '\n')
    if MARK in t: print('already patched:', path); return
    new = fn(t)
    (D / (path.name + '.diff')).write_text(''.join(difflib.unified_diff(t.splitlines(True), new.splitlines(True), str(path), str(path))))
    path.write_bytes((new.replace('\n', '\r\n') if crlf else new).encode('utf-8')); print('patched:', path)
def skia(t):
    sig = 'std::unique_ptr<ImageBufferSkiaAcceleratedBackend> ImageBufferSkiaAcceleratedBackend::create('
    if t.count(sig) != 2: sys.exit(f'safety net: expected 2 create() overloads, found {t.count(sig)}')
    out, pos = [], 0
    for _ in range(2):
        i = t.index(sig, pos); j = t.index('\n{\n', i) + 3
        out.append(t[pos:j]); out.append(GUARD); pos = j
    out.append(t[pos:]); t = ''.join(out)
    if 'PlatformDisplay.h' not in t:
        k = t.index('#include "ImageBufferSkiaAcceleratedBackend.h"\n') + len('#include "ImageBufferSkiaAcceleratedBackend.h"\n')
        t = t[:k] + '#include "PlatformDisplay.h"   // ' + MARK + '\n' + t[k:]
    return t
def wp(t):
    a = '    applyProcessCreationParameters(WTF::move(parameters.auxiliaryProcessParameters));\n'
    if t.count(a) != 1: sys.exit('safety net: WebProcessPlayStation anchor not found once')
    t = t.replace(a, a + '    if (!WebCore::PlatformDisplay::sharedDisplayIfExists())   // ' + MARK + '\n        WebCore::ProcessCapabilities::setCanUseAcceleratedBuffers(false);\n')
    return wp_includes(t)
def wp_includes(t):
    # the two includes go right after WebProcessCreationParameters.h: NOT inside the file's #if USE(WPE_RENDERER) block
    lines = [l for l in t.split('\n') if not (MARK in l and l.startswith('#include <WebCore/'))]
    t = '\n'.join(lines)
    a = '#include "WebProcessCreationParameters.h"\n'
    if t.count(a) != 1: sys.exit('safety net: include anchor not found once')
    return t.replace(a, a + ''.join(f'#include <WebCore/{h}>   // {MARK}\n' for h in ('PlatformDisplay.h', 'ProcessCapabilities.h')))
def repair_wp(path):
    raw = path.read_bytes().decode('utf-8'); crlf = '\r\n' in raw; t = raw.replace('\r\n', '\n')
    if MARK not in t: return
    fixed = wp_includes(t)
    if fixed != t:
        path.write_bytes((fixed.replace('\n', '\r\n') if crlf else fixed).encode('utf-8')); print('repaired includes:', path)
edit(W / 'WebCore/platform/graphics/skia/ImageBufferSkiaAcceleratedBackend.cpp', skia)
edit(W / 'WebKit/WebProcess/playstation/WebProcessPlayStation.cpp', wp)
repair_wp(W / 'WebKit/WebProcess/playstation/WebProcessPlayStation.cpp')
print('webkit s3 patches done')
