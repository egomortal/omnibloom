#!/usr/bin/env python3
"""OMNI_HW_CODEC_SWITCH_V1 (2026-11-26): the hardware decoder refuses a second video format in one Omni run.

Console finding (gates Lnav3iw/Lnav3/Lnav4iw/Lnav5iw/Lnav6iw on gbp10): once Omni has opened a hardware decoder for one
format (VP9 or H.264), CreateDecoder answers 0x811d0100 for the other format, every time, until Omni restarts, even with no
decoder open (hw_decoders=0). Both page engines, 8- and 10-bit, with and without the V5 picture queue. The same format
opens again fine. tools/vdec-probe (a small process) switched H.264/HEVC/VP9 on one compute queue without trouble, so it
is something about Omni's process. H.264 after VP9 falls back to software; VP9 above 1080p after H.264 has no software
route at all (YouTube 1440p then fails to play).

This build tries three remedies, each switchable on the console, and logs what the decoder says:
  retry (default on; off: /data/omni/hw-create-retry-off.flag): CreateDecoder refused -> log the configuration, memory
         and address space, then try the other configurations open() already knows (thread cpus, explicit dpb, depth 1),
         each with fresh memory.
  warm  (/data/omni/hw-codec-warm.flag): when the compute queue is first made, open and close a small H.264, VP9 and HEVC
         decoder once, so every format's code is set up while the process is young.
  pin   (/data/omni/hw-codec-pin.flag): the same, but the three small decoders stay open for the whole run.
usage: apply_hw_codec_switch.py <tree root holding engine/media>"""
import sys
from pathlib import Path

MARK = 'OMNI_HW_CODEC_SWITCH_V1'
p = Path(sys.argv[1]) / 'engine' / 'media' / 'OmniHwBackend.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('OmniHwBackend.cpp: already', MARK)
    sys.exit(0)


def sub(old, new):
    global s
    if s.count(old) != 1:
        sys.exit('anchor found %d times: %r' % (s.count(old), old[:100]))
    s = s.replace(old, new, 1)


# 1. helpers before Backend::open
sub('int Backend::open(Codec codec, int profile, int depth, int w, int h, std::string& stage)\n{\n',
    '// ' + MARK + ' (see tools/apply_hw_codec_switch.py)\n'
    'static bool omniHwFlag(const char* path) { return access(path, F_OK) == 0; }\n'
    'static Backend* omniHwPinned[3] = { nullptr, nullptr, nullptr };\n'
    'static bool omniHwPrimed = false;   // the warm/pin step ran (once per process)\n'
    'static void omniHwPrime()   // just after the compute queue exists: every format once while the process is young\n'
    '{\n'
    '    if (omniHwPrimed) return;\n'
    '    omniHwPrimed = true;\n'
    '    const bool pin = omniHwFlag("/data/omni/hw-codec-pin.flag"), warm = omniHwFlag("/data/omni/hw-codec-warm.flag");\n'
    '    if (!pin && !warm) return;\n'
    '    const Codec codecs[3] = { Codec::H264, Codec::VP9, Codec::HEVC };\n'
    '    const char* names[3] = { "H.264", "VP9", "HEVC" };\n'
    '    for (int i = 0; i < 3; ++i) {\n'
    '        Backend* b = new Backend();\n'
    '        std::string st;\n'
    '        const int rc = b->open(codecs[i], 0, 8, 640, 360, st);\n'
    '        fprintf(stderr, "OMNI HW BACKEND: ' + MARK + ' %s %s 640x360 -> 0x%08x at %s\\n", pin ? "pin" : "warm", names[i], unsigned(rc), st.c_str());\n'
    '        if (!rc && pin) { omniHwPinned[i] = b; continue; }\n'
    '        b->close(); delete b;\n'
    '    }\n'
    '    fflush(stderr);\n'
    '}\n\n'
    'int Backend::open(Codec codec, int profile, int depth, int w, int h, std::string& stage)\n{\n')

# 2. prime right after the queue exists (the nested opens see omniHwPrimed set and skip it)
sub('    if (int rc = ensureQueue()) return rc;\n',
    '    if (int rc = ensureQueue()) return rc;\n'
    '    if (!omniHwPrimed) { omniHwPrime(); stage = "compute queue"; }   // ' + MARK + '\n')

# 3. the allocation + CreateDecoder tail becomes a lambda: the first try as before, then the other configurations
old_tail = (
    '    frameSize_ = align16k(m.max_frame_size);\n'
    '    if (!frameSize_ || m.frame_alignment > 0x4000) { stage = "memory info"; return -1; }\n'
    '    if (m.cpu_size) {\n'
    '        cpuSize_ = align16k(m.cpu_size);\n'
    '        stage = "MapNamedFlexibleMemory";\n'
    '        if (int rc = sceKernelMapNamedFlexibleMemory(&cpu_, cpuSize_, 0x03, 0, "OmniHwDecoder")) { cpu_ = nullptr; cpuSize_ = 0; return rc; }\n'
    '    }\n'
    '    m.cpu = cpu_; m.cpu_size = cpuSize_;\n'
    '    stage = "alloc(gpu)";     if (int rc = allocDirect(gpu_, align16k(m.gpu_size), 0x33)) { close(); return rc; }\n'
    '    stage = "alloc(cpu_gpu)"; if (int rc = allocDirect(cpuGpu_, align16k(m.cpu_gpu_size), 0x33)) { close(); return rc; }\n'
    '    stage = "alloc(input)";   if (int rc = allocDirect(input_, inputBytes * inputSlots, 0x33)) { close(); return rc; }\n'
    '    stage = "alloc(frames)";  if (int rc = allocDirect(frames_, frameSize_ * frameSlots, 0x33)) { close(); return rc; }\n'
    '    m.gpu = gpu_.addr; m.gpu_size = gpu_.size; m.cpu_gpu = cpuGpu_.addr; m.cpu_gpu_size = cpuGpu_.size;\n'
    '    stage = "CreateDecoder";\n'
    '    if (int rc = api.CreateDecoder(&c, &m, &decoder_)) { decoder_ = nullptr; close(); return rc; }\n')
new_tail = (
    '    // ' + MARK + ': allocation + CreateDecoder for the configuration in c / memory info m (unchanged steps)\n'
    '    auto attempt = [&]() -> int {\n'
    '        frameSize_ = align16k(m.max_frame_size);\n'
    '        if (!frameSize_ || m.frame_alignment > 0x4000) { stage = "memory info"; return -1; }\n'
    '        if (m.cpu_size) {\n'
    '            cpuSize_ = align16k(m.cpu_size);\n'
    '            stage = "MapNamedFlexibleMemory";\n'
    '            if (int rc = sceKernelMapNamedFlexibleMemory(&cpu_, cpuSize_, 0x03, 0, "OmniHwDecoder")) { cpu_ = nullptr; cpuSize_ = 0; return rc; }\n'
    '        }\n'
    '        m.cpu = cpu_; m.cpu_size = cpuSize_;\n'
    '        stage = "alloc(gpu)";     if (int rc = allocDirect(gpu_, align16k(m.gpu_size), 0x33)) { close(); return rc; }\n'
    '        stage = "alloc(cpu_gpu)"; if (int rc = allocDirect(cpuGpu_, align16k(m.cpu_gpu_size), 0x33)) { close(); return rc; }\n'
    '        stage = "alloc(input)";   if (int rc = allocDirect(input_, inputBytes * inputSlots, 0x33)) { close(); return rc; }\n'
    '        stage = "alloc(frames)";  if (int rc = allocDirect(frames_, frameSize_ * frameSlots, 0x33)) { close(); return rc; }\n'
    '        m.gpu = gpu_.addr; m.gpu_size = gpu_.size; m.cpu_gpu = cpuGpu_.addr; m.cpu_gpu_size = cpuGpu_.size;\n'
    '        stage = "CreateDecoder";\n'
    '        if (int rc = api.CreateDecoder(&c, &m, &decoder_)) {\n'
    '            fprintf(stderr, "OMNI HW BACKEND: ' + MARK + ' CreateDecoder 0x%08x codec=%u profile=%u level=%u %ux%u affinity=0x%llx dpb=%d depth=%u "\n'
    '                "gpu=%zu cpu_gpu=%zu cpu=%zu frame=%zu flexible=%zuKiB threads=%d pinned=%d%d%d\\n", unsigned(rc), c.codec_type, c.profile, c.max_level,\n'
    '                c.max_width, c.max_height, (unsigned long long)c.cpu_affinity, c.max_dpb_frames, c.pipeline_depth, gpu_.size, cpuGpu_.size, cpuSize_,\n'
    '                frameSize_, flexibleKiB(), threadCount(), omniHwPinned[0] != nullptr, omniHwPinned[1] != nullptr, omniHwPinned[2] != nullptr);\n'
    '            decoder_ = nullptr; close(); return rc;\n'
    '        }\n'
    '        return 0;\n'
    '    };\n'
    '    rc = attempt();\n'
    '    if (rc && stage == std::string("CreateDecoder") && !omniHwFlag("/data/omni/hw-create-retry-off.flag")) {\n'
    '        dumpVm("create-fail");\n'
    '        const Variant* used = nullptr;\n'
    '        for (const auto& v : variants) if (v.affinity && c.cpu_affinity == v.affinity && c.max_dpb_frames == v.dpb && c.pipeline_depth == v.depth) { used = &v; break; }\n'
    '        for (const auto& v : variants) {\n'
    '            if (!v.affinity || &v == used) continue;\n'
    '            c.cpu_affinity = v.affinity; c.max_dpb_frames = v.dpb; c.pipeline_depth = v.depth;\n'
    '            memset(&m, 0, sizeof m); m.size = sizeof m;\n'
    '            const int q = api.QueryDecoderMemoryInfo(&c, &m);\n'
    '            const int r2 = q ? q : attempt();\n'
    '            fprintf(stderr, "OMNI HW BACKEND: ' + MARK + ' retry %s -> query 0x%08x create 0x%08x\\n", v.why, unsigned(q), unsigned(r2));\n'
    '            if (!r2) { rc = 0; break; }\n'
    '            if (q) stage = "CreateDecoder";\n'
    '        }\n'
    '        fflush(stderr);\n'
    '    }\n'
    '    if (rc) return rc;\n')
sub(old_tail, new_tail)

p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('OmniHwBackend.cpp: applied', MARK)
