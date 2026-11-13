#!/usr/bin/env python3
"""OMNI_LAZY_GPUPAGES_V1: add lazy forwarders for the EGL/GL functions stage 1 calls to the title's OmniLazyGraphics.cpp.

Why: the ls1b title (d983581f) imported 6 graphics functions directly (eglGetError, eglGetProcAddress, eglInitialize,
eglTerminate, glCheckFramebufferStatus, glReadPixels) because OmniLazyGraphics.cpp, generated from the s3 engine's import
list, had no forwarders for them. The console has no libEGL/libGLESv2 at start, so the title's start-up import check
refused to run (missing=6, exit 3). With forwarders the title resolves them itself and only dlopens the driver if one is
ever called (never in the title: the stage-1 path runs only in the child, which links static Mesa and not this file).
Same generator logic and format as engine/scripts/generate-lazy-graphics.py; anchored, idempotent.

Usage: add_lazy_graphics.py SDK_INCLUDE OmniLazyGraphics.cpp
"""
import re, sys
from pathlib import Path

NEEDED = ['eglGetError', 'eglGetProcAddress', 'eglInitialize', 'eglTerminate', 'glCheckFramebufferStatus', 'glReadPixels',
          # OMNI_LAZY_GPUPAGES_V2 (2026-11-12): the tile-diff shader (OMNI_GPUPAGES_TILES_V1+) and its state save/restore
          'glColorMask', 'glGetBooleanv', 'glGetProgramInfoLog', 'glGetProgramiv', 'glGetShaderInfoLog', 'glGetShaderiv', 'glUniform2i']
MARK = '// OMNI_LAZY_GPUPAGES_V1'
headers, target = Path(sys.argv[1]), Path(sys.argv[2])
text = target.read_text()
if MARK in text:
    print('already applied'); sys.exit(0)
if 'static void* omniGraphicsSymbol(bool egl, const char* name)' not in text:
    sys.exit('OmniLazyGraphics.cpp is not the generated lazy-graphics file')
have = set(re.findall(r'extern "C" .*?\b(\w+)\(', text))
clash = [n for n in NEEDED if n in have]
if clash:
    sys.exit(f'already forwarded (unexpected): {clash}')
out, found = f'\n{MARK}: forwarders for the stage-1 (GPU pages) calls, so the title does not import them.\n', set()
for header in (headers / 'EGL/egl.h', headers / 'GLES2/gl2.h'):
    for result, name, arguments in re.findall(
            r"(?:EGLAPI|GL_APICALL)\s+(.+?)\s*(?:EGLAPIENTRY|GL_APIENTRY)\s+(\w+)\s*\(([^;]*?)\);", header.read_text()):
        if name not in NEEDED or name in found:
            continue
        params = [] if arguments.strip() == 'void' else arguments.split(',')
        names = [re.search(r'(\w+)\s*$', p).group(1) for p in params]
        out += f'\nextern "C" {result} {name}({arguments})\n{{\n'
        out += f'    static auto function = reinterpret_cast<decltype(&{name})>(omniGraphicsSymbol({str(name.startswith("egl")).lower()}, "{name}"));\n'
        out += f'    return function({", ".join(names)});\n}}\n'
        found.add(name)
missing = sorted(set(NEEDED) - found)
if missing:
    sys.exit(f'no SDK declaration for {missing}')
target.write_text(text.rstrip('\n') + '\n' + out)
print(f'added {len(found)} forwarders: {", ".join(n for n in NEEDED)}')
