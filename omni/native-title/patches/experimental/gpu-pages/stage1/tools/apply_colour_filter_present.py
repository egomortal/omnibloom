#!/usr/bin/env python3
"""OMNI_COLOUR_FILTER_V1, title GPU present side: colour filters for colour-vision deficiency, folded into Night light's
one compute pass over the composed canvas (no second pass).

Patches OmniGpuPresent.cpp AFTER apply_night_light_present.py (r2; its lines are the anchors) and copies
OmniColourMatrixShader.h (SPIR-V of stage1/src-title/omni_colour_matrix.comp) next to it. In the rc6 title recipe
(build-omni-gpupages-rc6-title.sh) that is "$NE/src", one line right after the apply_night_light_present.py step:
    python3 "$S1/tools/apply_colour_filter_present.py" "$NE/src" "$S1/src-title"
apply_magnifier_present.py may run before or after it (none of its anchors is touched here, none of ours is its).
The engine side (the "Colour filter" row, the quick tile, the matrices) is apply_colour_filter.py.

What it changes (in place, on Night light's code)
  - The pass's shader becomes omni_colour_matrix.comp: out = M * rgb + o (Night light's shader with a per-row offset in
    the push constants' unused w; same push layout, same descriptor, same barriers).
  - omni_gpu_present_colour_filter(const float* m): the shell's row-major 3x4 affine (m[4i..4i+2] row i of the 3x3,
    m[4i+3] its offset); nullptr = off. omni_gpu_present_colour_filter_ready(): the same answer as Night light's.
  - nlRecord composes, under nl.lock: N = Night light's matrix (identity while it is off), (F, f) = the filter:
        M = N F, o = N f      (out = N (F c + f): the filter corrects the page's colours, the warmth goes over that)
    The pass is recorded while EITHER is on: one dispatch for both; both off = nothing recorded (no pass, no pipeline).
  - Everything Night light's pass covers is filtered (page, panels, pointer, SDR hole-punch video); HDR10 PQ video runs
    and read-back (verify) frames are not.
  - Host test hook (OMNI_GPU_PRESENT_HOST_TEST only): omni_gpu_present_colour_test_passes() = dispatches recorded.
An OmniGpuPresent.cpp that is already patched (the persistent $NE/src, re-run every build) prints "already" and only
refreshes the shader header when it differs.
Anchors (full lines, each once, all from apply_night_light_present.py r2): its OmniNightLightShader.h include; "} nl;";
nlSetUp's shader-module line; nlRecord's matrix copy (two lines) and its NlPush line; the end of omni_gpu_present_night.
Host test: tools/test_colour_filter_present.cpp (lavapipe).
usage: apply_colour_filter_present.py <src dir holding OmniGpuPresent.cpp> <stage1/src-title>"""
import shutil, sys
from pathlib import Path

MARK = 'OMNI_COLOUR_FILTER_V1'
src, s1 = Path(sys.argv[1]), Path(sys.argv[2])
p = src / 'OmniGpuPresent.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if raw.count('\r\n') * 2 > raw.count('\n') else '\n'
t = raw.replace('\r\n', '\n') if nl == '\r\n' else raw
HDR = 'OmniColourMatrixShader.h'
hdr = (s1 / HDR).read_bytes()


def save(text):
    p.write_bytes((text.replace('\n', '\r\n') if nl == '\r\n' else text).encode('utf-8'))


def shader_header():
    if (src / HDR).exists() and (src / HDR).read_bytes() == hdr:
        return ''
    shutil.copyfile(s1 / HDR, src / HDR)
    return ' (shader header refreshed)'


if MARK in t:
    print('already OmniGpuPresent.cpp' + shader_header()); sys.exit(0)
if 'OMNI_NIGHT_LIGHT_V1_R2' not in t:
    sys.exit('OmniGpuPresent.cpp: OMNI_NIGHT_LIGHT_V1_R2 missing: apply_night_light_present.py first')

STATE = r'''// ---------------------------------------------------------------- OMNI_COLOUR_FILTER_V1
// Colour filter (tools/apply_colour_filter_present.py): the shell (OmniColourFilterShell.h) sets a row-major 3x4 affine
// map (3x3 + one offset per row); nlRecord composes it with Night light's matrix, so both share Night light's ONE pass.
// Guarded by nl.lock (the shell thread sets it; the present reads it).
struct CfState { float m[12] = { 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0 }; bool want = false; } cf;
const float kCfIdentity[9] = { 1, 0, 0, 0, 1, 0, 0, 0, 1 };
// out = N (F c + f) = (N F) c + N f. n: Night light's 3x3 (identity while it is off); f: the filter's 3x4 or nullptr.
void cfCompose(const float* n, const float* f, float* m, float* o)
{
    for (int i = 0; i < 3; ++i) {
        o[i] = 0;
        for (int j = 0; j < 3; ++j) {
            m[i * 3 + j] = f ? n[i * 3] * f[j] + n[i * 3 + 1] * f[4 + j] + n[i * 3 + 2] * f[8 + j] : n[i * 3 + j];
            if (f) o[i] += n[i * 3 + j] * f[j * 4 + 3];
        }
    }
}
'''

API = r'''// OMNI_COLOUR_FILTER_V1: the shell's side (OmniColourFilterShell.h). m: row-major 3x4 (m[4i..4i+2] row i, m[4i+3] its
// offset) over the canvas's stored RGB; nullptr: off. Composed with Night light into its one pass (nothing while both
// are off). Ready: the same pass, so the same answer as Night light's.
extern "C" int omni_gpu_present_colour_filter_ready(void) { return omni_gpu_present_night_ready(); }
extern "C" int omni_gpu_present_colour_filter(const float* m)
{
    {
        std::lock_guard<std::mutex> l(nl.lock);
        cf.want = m != nullptr;
        if (m) memcpy(cf.m, m, sizeof cf.m);
    }
    return omni_gpu_present_colour_filter_ready();
}
#ifdef OMNI_GPU_PRESENT_HOST_TEST
extern "C" long omni_gpu_present_colour_test_passes(void) { return long(nl.frames); }   // OMNI_COLOUR_FILTER_V1: dispatches recorded
#endif
'''

EDITS = [
    ('#include "OmniNightLightShader.h"   // OMNI_NIGHT_LIGHT_V1: SPIR-V of omni_night_light.comp\n',
     '#include "OmniNightLightShader.h"   // OMNI_NIGHT_LIGHT_V1: SPIR-V of omni_night_light.comp\n'
     '#include "OmniColourMatrixShader.h"   // OMNI_COLOUR_FILTER_V1: SPIR-V of omni_colour_matrix.comp (the pass\'s shader now)\n'),
    ('} nl;\n',
     '} nl;\n' + STATE),
    ('    VkShaderModuleCreateInfo smi { VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO }; smi.codeSize = sizeof kOmniNightLightSpv; smi.pCode = kOmniNightLightSpv;\n',
     '    // OMNI_COLOUR_FILTER_V1: omni_colour_matrix.comp = omni_night_light.comp + a per-row offset (same push layout)\n'
     '    VkShaderModuleCreateInfo smi { VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO }; smi.codeSize = sizeof kOmniColourMatrixSpv; smi.pCode = kOmniColourMatrixSpv;\n'),
    ('    float m[9]; bool want;\n'
     '    { std::lock_guard<std::mutex> l(nl.lock); want = nl.want; memcpy(m, nl.m, sizeof m); }\n',
     '    float m[9], o[3]; bool want;   // OMNI_COLOUR_FILTER_V1: Night light x Colour filter, one affine map, one pass\n'
     '    { std::lock_guard<std::mutex> l(nl.lock); want = nl.want || cf.want; cfCompose(nl.want ? nl.m : kCfIdentity, cf.want ? cf.m : nullptr, m, o); }\n'),
    ('    NlPush pc { { m[0], m[1], m[2], 0 }, { m[3], m[4], m[5], 0 }, { m[6], m[7], m[8], 0 }, w, h, 0, 0 };\n',
     '    NlPush pc { { m[0], m[1], m[2], o[0] }, { m[3], m[4], m[5], o[1] }, { m[6], m[7], m[8], o[2] }, w, h, 0, 0 };   // OMNI_COLOUR_FILTER_V1: w = offset\n'),
    ('    return omni_gpu_present_night_ready();\n}\n',
     '    return omni_gpu_present_night_ready();\n}\n' + API),
]
for old, _ in EDITS:   # every anchor is checked before anything is written
    if t.count(old) != 1:
        sys.exit('OmniGpuPresent.cpp: anchor found %d times: %r' % (t.count(old), old[:90]))
for old, new in EDITS:
    t = t.replace(old, new, 1)
shutil.copyfile(s1 / HDR, src / HDR)
save(t)
print('applied ' + MARK + ' (OmniGpuPresent.cpp + ' + HDR + ')')
