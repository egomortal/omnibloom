#!/usr/bin/env python3
"""OMNI_VIDEO_ENHANCE_V1, video module side: better enlargement of video shown larger than its own size (720p/1080p/
1440p on a 1080p or 4K screen), in the GPU conversion pass (OmniGpuVideo + omni_yuv_to_rgb_v10.comp).

Today an enlargement repeats the nearest source pixel (OMNI_FAST_UPSCALE: brightness and colour both blocky), because
the GPU result must match the CPU path bit for bit while the differential test (verify) runs. This adds an opt-in level:
  0 Off     unchanged (nearest pixel, exactly as before)
  1 Smooth  brightness: Catmull-Rom bicubic (16 taps) clamped to the 4 nearest source samples (no halo / ringing, the
            same anti-ringing idea as FSR 1's EASU); colour: bilinear, centre-sited (no 2x2 colour blocks)
  2 Sharp   Smooth + detail boost: the bicubic result pushed 0.6x further from the bilinear base, same clamp
The verify read-back always uses the old rule (run(..., toReadback = true) never gets the level), so verification and
its thresholds are untouched; HDR pictures (a PQ layer) and the CPU path are unchanged. Cost: 16 + 8 reads per output
pixel instead of 3, only while an enlarged video is on screen and the level is not Off.

How the level travels: the push block is exactly 128 bytes (Vulkan's guaranteed minimum), so no field is added; the
level rides in cpuMode bits 24-25 (the shader masks its other uses: bits 0-1, 4, 8-15). Only shown enlargements get it.
The shell (apply_video_enhance.py) sets it with omni_gpu_video_set_enhance(level).

Patches, in the persistent eboot workspace (the rc6 recipe's "$NE", like apply_video_immersive.py "$NE" media):
  shader/omni_yuv_to_rgb_v10.comp      the enhanced branch (+ glslangValidator -> .spv, spirv-val, header regenerated)
  engine/media/OmniGpuVideo.cpp        g.enhance, the level into cpuMode in run(), omni_gpu_video_set_enhance()
  engine/media/OmniGpuVideoShaderV10.h regenerated from the .spv (tools/spv_to_header.py, the s3.5 recipe's way)
Recipe line (after the video immersive eboot-media line):
    python3 "$S1/tools/apply_video_enhance_media.py" "$NE"
A tree already patched prints "already". Backups: <file>.before-video-enhance (first apply only).
usage: apply_video_enhance_media.py <eboot workspace root>"""
import shutil, subprocess, sys
from pathlib import Path

MARK = 'OMNI_VIDEO_ENHANCE_V1'
root = Path(sys.argv[1])
comp = root / 'shader' / 'omni_yuv_to_rgb_v10.comp'
spv = root / 'shader' / 'omni_yuv_to_rgb_v10.spv'
cpp = root / 'engine' / 'media' / 'OmniGpuVideo.cpp'
hdr = root / 'engine' / 'media' / 'OmniGpuVideoShaderV10.h'


def read(p):
    raw = p.read_bytes().decode('utf-8')
    nl = '\r\n' if raw.count('\r\n') * 2 > raw.count('\n') else '\n'
    return (raw.replace('\r\n', '\n') if nl == '\r\n' else raw), nl


def write(p, text, nl):
    bk = p.with_name(p.name + '.before-video-enhance')
    if not bk.exists():
        shutil.copy2(p, bk)
    p.write_bytes((text.replace('\n', '\r\n') if nl == '\r\n' else text).encode('utf-8'))


def edit(text, edits, what):
    for old, new in edits:
        if text.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (what, text.count(old), old[:70]))
    for old, new in edits:
        text = text.replace(old, new, 1)
    return text


HELPER = '''// OMNI_VIDEO_ENHANCE_V1: enlargement levels (cpuMode bits 24-25; 0 = the nearest-pixel rule below, unchanged).
vec4 omniCatmullRom(float t)
{
    return vec4(t * (-0.5 + t * (1.0 - 0.5 * t)), 1.0 + t * t * (-2.5 + 1.5 * t),
                t * (0.5 + t * (2.0 - 1.5 * t)), t * t * (-0.5 + 0.5 * t));
}
// Bicubic luma, clamped to the 4 nearest samples (no ringing); level 2 adds 0.6x the bicubic-minus-bilinear detail.
float omniEnhanceLuma(uint planeByte, int w, int h, vec2 p, int level)
{
    vec2 f = floor(p), t = p - f;
    int x0 = int(f.x), y0 = int(f.y);
    vec4 wx = omniCatmullRom(t.x), wy = omniCatmullRom(t.y);
    float acc = 0.0, c11 = 0.0, c21 = 0.0, c12 = 0.0, c22 = 0.0;
    for (int j = 0; j < 4; ++j) {
        float row = 0.0;
        for (int i = 0; i < 4; ++i) {
            float s = sampleAt(planeByte, w, h, x0 + i - 1, y0 + j - 1);
            row += wx[i] * s;
            if (j == 1 && i == 1) c11 = s;
            if (j == 1 && i == 2) c21 = s;
            if (j == 2 && i == 1) c12 = s;
            if (j == 2 && i == 2) c22 = s;
        }
        acc += wy[j] * row;
    }
    if (level >= 2) {
        float base = mix(mix(c11, c21, t.x), mix(c12, c22, t.x), t.y);
        acc += 0.6 * (acc - base);
    }
    return clamp(acc, min(min(c11, c21), min(c12, c22)), max(max(c11, c21), max(c12, c22)));
}

void main()
'''

BRANCH_OLD = '    if ((pc.srcW == pc.dstW && pc.srcH == pc.dstH) || enlarge) {   // 1:1 (or its nearest-pixel enlargement): block chroma\n'
BRANCH_NEW = ('    int enhanceLevel = (pc.cpuMode >> 24) & 3;   // OMNI_VIDEO_ENHANCE_V1 (set only for shown enlargements)\n'
              '    if (enlarge && enhanceLevel != 0) {\n'
              '        vec2 lp = (vec2(o) + 0.5) * ratio - 0.5;   // luma pixel-centre coordinates\n'
              '        vec2 cp = (lp + 0.5) * 0.5 - 0.5;          // centre-sited chroma\n'
              '        Y = omniEnhanceLuma(yPlane, pc.srcW, pc.srcH, lp, enhanceLevel);\n'
              '        U = bilinear(uPlane, cw, ch, cp);\n'
              '        V = bilinear(vPlane, cw, ch, cp);\n'
              '        n = ivec2(1);\n'
              '    } else\n' + BRANCH_OLD)

CPP_EDITS = [
    ('    bool optV10 = true;   // OMNI_GPU_VERIFY10_V1: the flag word v4colour turns it off\n',
     '    bool optV10 = true;   // OMNI_GPU_VERIFY10_V1: the flag word v4colour turns it off\n'
     '    std::atomic<int> enhance { 0 };   // OMNI_VIDEO_ENHANCE_V1: 0 off, 1 smooth, 2 sharp (shown enlargements only)\n'),
    ('    colourFor(j, pc);\n    if (hdrLayer) { pc.hdrMode = j.hdrMode; pc.hdrBase = hdrOff / 4; }\n',
     '    colourFor(j, pc);\n    if (hdrLayer) { pc.hdrMode = j.hdrMode; pc.hdrBase = hdrOff / 4; }\n'
     '#ifdef OMNI_GPU_VERIFY10_V1\n'
     '    {   // OMNI_VIDEO_ENHANCE_V1: the level rides in cpuMode bits 24-25; never for a verify read-back or an HDR picture\n'
     '        const int e = g.enhance.load(std::memory_order_relaxed);\n'
     '        const bool enl = j.dstW >= j.srcW && j.dstH >= j.srcH && (j.dstW > j.srcW || j.dstH > j.srcH);\n'
     '        if (e > 0 && enl && !toReadback && !hdrLayer) pc.cpuMode = (pc.cpuMode & 0x00ffffff) | ((e > 2 ? 2 : e) << 24);\n'
     '    }\n'
     '#endif\n'),
    ('extern "C" void omni_gpu_video_stats3(uint64_t* hdrPictures) { OmniGpuVideo::stats3(*hdrPictures); }   // V4\n',
     'extern "C" void omni_gpu_video_stats3(uint64_t* hdrPictures) { OmniGpuVideo::stats3(*hdrPictures); }   // V4\n'
     '// OMNI_VIDEO_ENHANCE_V1: the shell\'s "Video upscaling" (0 off, 1 smooth, 2 sharp). Any thread; read per picture.\n'
     'extern "C" void omni_gpu_video_set_enhance(int level) { OmniGpuVideo::g.enhance.store(level < 0 ? 0 : level > 2 ? 2 : level, std::memory_order_relaxed); }\n'
     'extern "C" int omni_gpu_video_get_enhance(void) { return OmniGpuVideo::g.enhance.load(std::memory_order_relaxed); }\n'),
]


def build_header():
    """glslangValidator -> .spv -> spirv-val -> header, the same command and header line as the s3.5 V10 recipe."""
    subprocess.run(['glslangValidator', '-V', '--target-env', 'vulkan1.1', '-o', str(spv), str(comp)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    subprocess.run(['spirv-val', '--target-env', 'vulkan1.1', str(spv)], check=True)
    tmp = hdr.with_name(hdr.name + '.tmp')
    subprocess.run([sys.executable, str(root / 'tools' / 'spv_to_header.py'), str(spv), str(tmp), 'kOmniYuvToRgbSpv',
                    'omni_yuv_to_rgb_v10.comp'], check=True)
    text = tmp.read_text('utf-8').replace('// Generated from omni_yuv_to_rgb_v10.comp',
                                          '// OMNI_GPU_VERIFY10_V1. Generated from omni_yuv_to_rgb_v10.comp', 1)   # the s3.5 recipe's exact form (its check compares)
    tmp.unlink()
    if not hdr.exists() or hdr.read_text('utf-8') != text:
        if hdr.exists():
            bk = hdr.with_name(hdr.name + '.before-video-enhance')
            if not bk.exists():
                shutil.copy2(hdr, bk)
        hdr.write_text(text, 'utf-8')
        return 'header regenerated'
    return 'header current'


def main():
    for p in (comp, cpp, hdr, root / 'tools' / 'spv_to_header.py'):
        if not p.exists():
            sys.exit('missing %s' % p)
    c, cnl = read(comp)
    v, vnl = read(cpp)
    done = []
    if MARK not in c:
        if 'OMNI_GPU_VERIFY10' not in c and 'cpuMode' not in c:
            sys.exit('omni_yuv_to_rgb_v10.comp: not the V10 shader')
        c = edit(c, [('void main()\n', HELPER), (BRANCH_OLD, BRANCH_NEW)], comp.name)
        write(comp, c, cnl); done.append('shader')
    if MARK not in v:
        if 'OMNI_GPU_VERIFY10_V1' not in v:
            sys.exit('OmniGpuVideo.cpp: OMNI_GPU_VERIFY10_V1 missing (the enhance level needs the V10 push block)')
        v = edit(v, CPP_EDITS, cpp.name)
        write(cpp, v, vnl); done.append('OmniGpuVideo.cpp')
    h = build_header()
    print(('applied ' + MARK + ' (' + ', '.join(done) + '; ' + h + ')') if done else ('already ' + MARK + ' (' + h + ')'))


main()
