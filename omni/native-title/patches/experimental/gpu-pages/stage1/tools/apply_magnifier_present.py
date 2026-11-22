#!/usr/bin/env python3
"""OMNI_MAGNIFIER_V1, title GPU present side: the magnifier lens as one small compute pass over the composed canvas.

Patches OmniGpuPresent.cpp (the copy prep_launch.py put in the title workspace's src/, AFTER apply_zerocopy_present.py)
and copies OmniMagnifierShader.h (SPIR-V of stage1/src-title/omni_magnifier.comp) next to it. In the rc6 title recipe
(build-omni-gpupages-rc6-title.sh) that is "$NE/src", one line after the apply_zerocopy_present.py step (and after
apply_night_light_present.py when that line is there):
    python3 "$S1/tools/apply_magnifier_present.py" "$NE/src" "$S1/src-title"
The engine side (L2 + L3 chord, zoom state, pointer -> lens parameters, hiding the pointer sprite) is apply_magnifier.py.

What it adds
  - omni_gpu_present_lens(const float* p): p[0..1] pointer as fractions of the canvas width / height, p[2] zoom,
    p[3..7] lens half width, half height, corner radius, ring width, crosshair arm (fractions of the canvas HEIGHT);
    nullptr = off. omni_gpu_present_lens_ready(): 1 while the GPU present is active and the pass has not failed.
  - mgRecord (in recordCompose, right before the canvas becomes a transfer source for the read-back / blit / PQ pass,
    so AFTER zcRecord and Night light's nlRecord: the lens shows the tinted page): while a lens is set,
      canvas -> buffer: the source region around the pointer and the lens rectangle (two regions, one copy),
      one dispatch of omni_magnifier.comp over the lens rectangle (the buffer only), buffer -> canvas: the lens rectangle.
    The canvas never needs STORAGE usage (no ensureCanvas change, independent of Night light's canvas remake) and
    stays in transfer layouts. Cost while on: two small copies + a lens-sized dispatch; off: nothing at all (no pass,
    no pipeline, no buffer until the first lens frame).
  - The video: the hole-punch copies the SDR video runs into the canvas before this pass, so video under the lens is
    magnified. HDR10 output: the PQ pass reads the canvas after the lens (page and UI magnified), but the PQ video runs
    (V4 copies / P10 dispatch) are written after it, so in HDR10 the video shows unmagnified over the lens.
  - Read-back (verify) frames are not magnified (the differential check stays exact).
  - One host-visible buffer, grown (x1.25) when a lens needs more; freed at teardown.
Anchors (each once; MARK makes it idempotent; none touches Night light's lines, so the two can run in either order):
  the OmniZcPageShader.h include line (our include goes before it); "bool hdrEnsure(uint32_t w, uint32_t h);\\nbool
  ensureCanvas" (the state block goes before it); the canvas TRANSFER_DST -> TRANSFER_SRC barrier + layout +
  rec.readback lines of recordCompose (the call goes before them); the zero-copy shell API comment (the lens API goes
  before it); zcDestroy() in teardownLocked (ours goes before it); the live-count line of the host test's teardown.
r2 (OMNI_MAGNIFIER_V1_R2): mg.broken became std::atomic<bool> (mgBreak / mgDestroy write it on the present thread,
  omni_gpu_present_lens_ready() reads it on the shell thread without a lock), and the lens buffer is only freed / grown
  once the previous frame's fence has signalled. Checked in the present code: every present waits on g.submitFence
  before it returns (submitAndWait; presentDeferred after the vblank wait), all under g.lock, so the next mgRecord
  normally finds the fence signalled; a failed present switches the GPU present off (kFailed; teardown waits for the
  device to idle) and a hang leaves every object alone. The one path that skips the wait (vkQueuePresentKHR failing
  inside submitAndWait, then bringUp's second first-frame attempt) is covered by mgRecord itself: before it frees the
  old buffer it waits on g.submitFence (returns at once when signalled; only on a grow, a handful of times per run);
  if that frame does not finish within 1 s the buffer is left alone and the lens turns off.
  Also fixed (found by the r2 host test G8c, the first test to grow an existing buffer): r1 rebound the descriptor
  only when the new VkBuffer handle differed from the old one, but a freed handle's value is reused (lavapipe: every
  time), so after a grow the shader wrote through a destroyed buffer (no lens drawn, or a crash). A grow now always
  rebinds (mg.boundBuf is cleared with the free).
  A file with r1 (the persistent $NE/src of the rc6 recipe, re-run every build) is upgraded in place (two edits); a
  fresh apply writes r2 directly; both give the same bytes. Night light's present patch still applies before or after.
Host test: tools/test_magnifier_present.cpp (lavapipe, OMNI_GPU_PRESENT_HOST_TEST).
usage: apply_magnifier_present.py <src dir holding OmniGpuPresent.cpp> <stage1/src-title>"""
import shutil, sys
from pathlib import Path

MARK = 'OMNI_MAGNIFIER_V1'
REV = 'OMNI_MAGNIFIER_V1_R2'   # r2: mg.broken is atomic; the lens buffer is freed only after the previous frame's fence
src, s1 = Path(sys.argv[1]), Path(sys.argv[2])
p = src / 'OmniGpuPresent.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if raw.count('\r\n') * 2 > raw.count('\n') else '\n'
t = raw.replace('\r\n', '\n') if nl == '\r\n' else raw
if 'OMNI_GPUPAGES_ZEROCOPY_V1' not in t:
    sys.exit('OmniGpuPresent.cpp: OMNI_GPUPAGES_ZEROCOPY_V1 missing: apply_zerocopy_present.py first')
hdr = (s1 / 'OmniMagnifierShader.h').read_bytes()

# r2 (REV): r1's text -> r2's text. A file patched by r1 gets only these; a fresh apply writes the r2 text with STATE.
MG_FLAGS_R1 = ('    float p[8] = {}; bool want = false;\n'
               '    bool tried = false, ready = false, broken = false;\n')
MG_FLAGS_R2 = ('    float p[8] = {}; bool want = false;\n'
               '    bool tried = false, ready = false;\n'
               '    std::atomic<bool> broken { false };   // ' + REV + ': set by mgBreak / mgDestroy (present), read by omni_gpu_present_lens_ready (shell)\n')
MG_GROW_R1 = ('    if (!mg.buf.buffer || mg.buf.size < need) {   // the previous present\'s fence has signalled: the old buffer is idle\n'
              '        freeBuf(mg.buf);\n')
MG_GROW_R2 = ('    if (!mg.buf.buffer || mg.buf.size < need) {\n'
              '        // ' + REV + ': the old buffer goes only once the frame that used it is done. Every present waits on\n'
              '        // g.submitFence before it returns, so this returns at once; it matters only after a present that failed\n'
              '        // before its wait (bringUp\'s second first-frame try). Only on a grow: a handful of times per run.\n'
              '        if (mg.buf.buffer && g.vk.vkWaitForFences(g.device, 1, &g.submitFence, VK_TRUE, 1000ull * 1000 * 1000) != VK_SUCCESS) {\n'
              '            mgBreak("the previous frame did not finish (the lens buffer is left alone)"); return;\n'
              '        }\n'
              '        freeBuf(mg.buf);\n'
              '        mg.boundBuf = VK_NULL_HANDLE;   // ' + REV + ': the new buffer can get the freed one\'s handle value: always rebind\n')
R2_EDITS = [(MG_FLAGS_R1, MG_FLAGS_R2), (MG_GROW_R1, MG_GROW_R2)]


def save(text):
    p.write_bytes((text.replace('\n', '\r\n') if nl == '\r\n' else text).encode('utf-8'))


def shader_header():
    if (src / 'OmniMagnifierShader.h').exists() and (src / 'OmniMagnifierShader.h').read_bytes() == hdr:
        return ''
    shutil.copyfile(s1 / 'OmniMagnifierShader.h', src / 'OmniMagnifierShader.h')
    return ' (shader header refreshed)'


if MARK in t:
    if REV in t:
        # a file from the first r2 draft (2026-11-16 10:22 title build: no rebind line yet) gets that line
        draft = MG_GROW_R2[:MG_GROW_R2.rindex('        mg.boundBuf = VK_NULL_HANDLE;')]
        if MG_GROW_R2 not in t and t.count(draft) == 1:
            save(t.replace(draft, MG_GROW_R2, 1))
            print('upgraded OmniGpuPresent.cpp (r2 draft: the grow rebinds)' + shader_header()); sys.exit(0)
        print('already OmniGpuPresent.cpp' + shader_header()); sys.exit(0)
    for old, _ in R2_EDITS:   # every anchor is checked before anything is written
        if t.count(old) != 1:
            sys.exit('OmniGpuPresent.cpp: r2 anchor found %d times: %r' % (t.count(old), old[:90]))
    for old, new in R2_EDITS:
        t = t.replace(old, new, 1)
    save(t)
    print('upgraded OmniGpuPresent.cpp to ' + REV + shader_header()); sys.exit(0)

STATE = r'''// ---------------------------------------------------------------- OMNI_MAGNIFIER_V1
// The magnifier lens (tools/apply_magnifier_present.py): the shell (OmniMagnifierShell.h) sends the pointer and the
// lens size; while one is set, recordCompose copies the source region and the lens rectangle out of the canvas, one
// dispatch of omni_magnifier.comp draws the lens in that buffer, and the lens rectangle is copied back.
struct MgPush { int32_t src[4], dst[4]; float lens[4], look[4], ring[4]; int32_t canvas[4]; };
static_assert(sizeof(MgPush) == 96, "push constants of omni_magnifier.comp");
struct MgState {
    std::mutex lock;                   // the shell thread sets the lens; the present records it
''' + MG_FLAGS_R2 + r'''    VkShaderModule shader = VK_NULL_HANDLE; VkDescriptorSetLayout setLayout = VK_NULL_HANDLE; VkPipelineLayout layout = VK_NULL_HANDLE;
    VkPipeline pipe = VK_NULL_HANDLE; VkDescriptorPool pool = VK_NULL_HANDLE; VkDescriptorSet set = VK_NULL_HANDLE;
    Buf buf; VkBuffer boundBuf = VK_NULL_HANDLE;
    uint64_t frames = 0, skipped = 0, grows = 0; double lastLog = 0;
} mg;
bool loadHdrFns();
void mgBreak(const char* why)
{
    if (!mg.broken) plog(true, "magnifier OFF: %s (no lens is drawn)", why);
    mg.broken = true;
}
bool mgSetUp()   // once, on the first lens frame (caller holds g.lock)
{
    if (mg.tried) return mg.ready;
    mg.tried = true;
    if (!g.device || !loadHdrFns()) { mgBreak("device entry points missing"); return false; }
    VkShaderModuleCreateInfo smi { VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO }; smi.codeSize = sizeof kOmniMagnifierSpv; smi.pCode = kOmniMagnifierSpv;
    if (g.vk.vkCreateShaderModule(g.device, &smi, nullptr, &mg.shader) != VK_SUCCESS) { mg.shader = VK_NULL_HANDLE; mgBreak("shader module"); return false; }
    VkDescriptorSetLayoutBinding b {};
    b.binding = 0; b.descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; b.descriptorCount = 1; b.stageFlags = VK_SHADER_STAGE_COMPUTE_BIT;
    VkDescriptorSetLayoutCreateInfo dl { VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO }; dl.bindingCount = 1; dl.pBindings = &b;
    if (g.vk.vkCreateDescriptorSetLayout(g.device, &dl, nullptr, &mg.setLayout) != VK_SUCCESS) { mg.setLayout = VK_NULL_HANDLE; mgBreak("set layout"); return false; }
    VkPushConstantRange range { VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof(MgPush) };
    VkPipelineLayoutCreateInfo pl { VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO }; pl.setLayoutCount = 1; pl.pSetLayouts = &mg.setLayout; pl.pushConstantRangeCount = 1; pl.pPushConstantRanges = &range;
    if (g.vk.vkCreatePipelineLayout(g.device, &pl, nullptr, &mg.layout) != VK_SUCCESS) { mg.layout = VK_NULL_HANDLE; mgBreak("pipeline layout"); return false; }
    VkComputePipelineCreateInfo cp { VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO };
    cp.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO; cp.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT; cp.stage.module = mg.shader; cp.stage.pName = "main"; cp.layout = mg.layout;
    if (g.vk.vkCreateComputePipelines(g.device, VK_NULL_HANDLE, 1, &cp, nullptr, &mg.pipe) != VK_SUCCESS) { mg.pipe = VK_NULL_HANDLE; mgBreak("compute pipeline"); return false; }
    VkDescriptorPoolSize ps { VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1 };
    VkDescriptorPoolCreateInfo dp { VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO }; dp.maxSets = 1; dp.poolSizeCount = 1; dp.pPoolSizes = &ps;
    if (g.vk.vkCreateDescriptorPool(g.device, &dp, nullptr, &mg.pool) != VK_SUCCESS) { mg.pool = VK_NULL_HANDLE; mgBreak("descriptor pool"); return false; }
    VkDescriptorSetAllocateInfo da { VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO }; da.descriptorPool = mg.pool; da.descriptorSetCount = 1; da.pSetLayouts = &mg.setLayout;
    if (g.vk.vkAllocateDescriptorSets(g.device, &da, &mg.set) != VK_SUCCESS) { mg.set = VK_NULL_HANDLE; mgBreak("descriptor set"); return false; }
    mg.ready = true;
    plog(true, "magnifier: armed (two copies + one dispatch over the lens while it is on)");
    return true;
}
// The lens geometry for a w x h canvas from the shell's fractions (pure; the host test mirrors it).
struct MgGeom { int sx0, sy0, sw, sh, dx0, dy0, dw, dh; float cx, cy, hw, hh, px, py, zoom, corner, ringW, arm, gap, thick; };
bool mgGeometry(const float* q, int w, int h, MgGeom& o)
{
    if (w <= 0 || h <= 0) return false;
    const float H = float(h);
    o.zoom = std::min(std::max(q[2], 1.0f), 8.0f);
    o.hw = std::min(std::max(q[3] * H, 8.0f), w * 0.5f); o.hh = std::min(std::max(q[4] * H, 8.0f), h * 0.5f);
    o.corner = std::min(std::max(q[5] * H, 0.0f), std::min(o.hw, o.hh));
    o.ringW = std::min(std::max(q[6] * H, 0.0f), std::min(o.hw, o.hh) * 0.5f);
    o.arm = std::max(q[7] * H, 0.0f);
    o.gap = std::max(1.0f, std::floor(o.arm * 0.34f)); o.thick = std::max(0.5f, std::floor(o.arm * 0.12f) + 0.5f);
    if (o.arm < 3.0f) o.arm = 0;
    o.px = std::min(std::max(q[0], 0.0f), 1.0f) * float(w); o.py = std::min(std::max(q[1], 0.0f), 1.0f) * float(h);
    o.cx = std::min(std::max(o.px, o.hw), float(w) - o.hw); o.cy = std::min(std::max(o.py, o.hh), float(h) - o.hh);   // the lens stays on the canvas
    o.dx0 = std::max(0, int(std::floor(o.cx - o.hw))); o.dy0 = std::max(0, int(std::floor(o.cy - o.hh)));
    o.dw = std::min(w, int(std::ceil(o.cx + o.hw))) - o.dx0; o.dh = std::min(h, int(std::ceil(o.cy + o.hh))) - o.dy0;
    const float rx = o.hw / o.zoom, ry = o.hh / o.zoom;
    o.sx0 = std::max(0, int(std::floor(o.px - rx)) - 1); o.sy0 = std::max(0, int(std::floor(o.py - ry)) - 1);
    o.sw = std::min(w, int(std::ceil(o.px + rx)) + 2) - o.sx0; o.sh = std::min(h, int(std::ceil(o.py + ry)) + 2) - o.sy0;
    if (o.sw <= 0 || o.sh <= 0) { o.sx0 = std::min(std::max(int(o.px), 0), w - 1); o.sy0 = std::min(std::max(int(o.py), 0), h - 1); o.sw = o.sh = 1; }
    return o.dw > 0 && o.dh > 0;
}
// In recordCompose, after the canvas is complete (frame, video runs, zero-copy page, Night light) and still TRANSFER_DST.
void mgRecord(int w, int h, bool wantReadback)
{
    float q[8]; bool want;
    { std::lock_guard<std::mutex> l(mg.lock); want = mg.want; memcpy(q, mg.p, sizeof q); }
    if (!want || mg.broken) return;                    // Off: nothing recorded
    if (wantReadback) { mg.skipped++; return; }        // the differential check compares with the CPU frame
    if (!g.canvas.image || !mgSetUp()) return;
    MgGeom o {};
    if (!mgGeometry(q, w, h, o)) { mg.skipped++; return; }
    const VkDeviceSize srcWords = VkDeviceSize(o.sw) * VkDeviceSize(o.sh), need = (srcWords + VkDeviceSize(o.dw) * VkDeviceSize(o.dh)) * 4;
''' + MG_GROW_R2 + r'''        if (!makeHostBuffer(mg.buf, need + need / 4, false, VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT | VK_BUFFER_USAGE_STORAGE_BUFFER_BIT)) {
            mg.buf = Buf {}; mgBreak("lens buffer"); return;
        }
        mg.grows++;
    }
    if (mg.boundBuf != mg.buf.buffer) {
        VkDescriptorBufferInfo bi { mg.buf.buffer, 0, VK_WHOLE_SIZE };
        VkWriteDescriptorSet wr { VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET };
        wr.dstSet = mg.set; wr.dstBinding = 0; wr.descriptorCount = 1; wr.descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; wr.pBufferInfo = &bi;
        g.vk.vkUpdateDescriptorSets(g.device, 1, &wr, 0, nullptr);
        mg.boundBuf = mg.buf.buffer;
    }
    barrier(g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, VK_ACCESS_TRANSFER_WRITE_BIT | VK_ACCESS_SHADER_WRITE_BIT,
            VK_ACCESS_TRANSFER_READ_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT | VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
    VkBufferImageCopy out[2] {};
    out[0].bufferOffset = 0; out[0].bufferRowLength = uint32_t(o.sw); out[0].bufferImageHeight = uint32_t(o.sh);
    out[0].imageSubresource = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1 }; out[0].imageOffset = { o.sx0, o.sy0, 0 }; out[0].imageExtent = { uint32_t(o.sw), uint32_t(o.sh), 1 };
    out[1] = out[0];
    out[1].bufferOffset = srcWords * 4; out[1].bufferRowLength = uint32_t(o.dw); out[1].bufferImageHeight = uint32_t(o.dh);
    out[1].imageOffset = { o.dx0, o.dy0, 0 }; out[1].imageExtent = { uint32_t(o.dw), uint32_t(o.dh), 1 };
    g.vk.vkCmdCopyImageToBuffer(g.cmd, g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, mg.buf.buffer, 2, out);
    VkBufferMemoryBarrier bb { VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER };
    bb.srcQueueFamilyIndex = bb.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED; bb.buffer = mg.buf.buffer; bb.offset = 0; bb.size = VK_WHOLE_SIZE;
    bb.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT; bb.dstAccessMask = VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT;
    g.vk.vkCmdPipelineBarrier(g.cmd, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, 0, 0, nullptr, 1, &bb, 0, nullptr);
    g.vk.vkCmdBindPipeline(g.cmd, VK_PIPELINE_BIND_POINT_COMPUTE, mg.pipe);
    g.vk.vkCmdBindDescriptorSets(g.cmd, VK_PIPELINE_BIND_POINT_COMPUTE, mg.layout, 0, 1, &mg.set, 0, nullptr);
    MgPush pc { { o.sx0, o.sy0, o.sw, o.sh }, { o.dx0, o.dy0, o.dw, o.dh }, { o.cx, o.cy, o.hw, o.hh }, { o.px, o.py, o.zoom, o.corner },
                { o.ringW, o.arm, o.gap, o.thick }, { w, h, 0, 0 } };
    g.vk.vkCmdPushConstants(g.cmd, mg.layout, VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof pc, &pc);
    g.vk.vkCmdDispatch(g.cmd, uint32_t(o.dw + 7) / 8, uint32_t(o.dh + 7) / 8, 1);
    bb.srcAccessMask = VK_ACCESS_SHADER_WRITE_BIT; bb.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT;
    g.vk.vkCmdPipelineBarrier(g.cmd, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, nullptr, 1, &bb, 0, nullptr);
    barrier(g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_ACCESS_TRANSFER_READ_BIT, VK_ACCESS_TRANSFER_WRITE_BIT,
            VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
    g.vk.vkCmdCopyBufferToImage(g.cmd, mg.buf.buffer, g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &out[1]);
    mg.frames++;
    if (mg.frames == 1 || nowMs() - mg.lastLog >= 10000) {
        plog(false, "magnifier: %llu lens frames (%llu skipped, buffer %.0f KiB, %llu grows), zoom %.1f lens %dx%d", (unsigned long long)mg.frames,
             (unsigned long long)mg.skipped, double(mg.buf.size) / 1024.0, (unsigned long long)mg.grows, double(o.zoom), o.dw, o.dh);
        mg.lastLog = nowMs();
    }
}
// Teardown (teardownLocked, before the device goes): every object the pass made. The shell's lens is kept.
void mgDestroy()
{
    if (g.device) {
        freeBuf(mg.buf);
        if (mg.pipe) g.vk.vkDestroyPipeline(g.device, mg.pipe, nullptr);
        if (mg.pool) g.vk.vkDestroyDescriptorPool(g.device, mg.pool, nullptr);
        if (mg.layout) g.vk.vkDestroyPipelineLayout(g.device, mg.layout, nullptr);
        if (mg.setLayout) g.vk.vkDestroyDescriptorSetLayout(g.device, mg.setLayout, nullptr);
        if (mg.shader) g.vk.vkDestroyShaderModule(g.device, mg.shader, nullptr);
    }
    mg.buf = Buf {}; mg.boundBuf = VK_NULL_HANDLE;
    mg.pipe = VK_NULL_HANDLE; mg.pool = VK_NULL_HANDLE; mg.set = VK_NULL_HANDLE; mg.layout = VK_NULL_HANDLE; mg.setLayout = VK_NULL_HANDLE; mg.shader = VK_NULL_HANDLE;
    mg.tried = mg.ready = mg.broken = false;
}

'''

API = r'''// OMNI_MAGNIFIER_V1: the shell's side (OmniMagnifierShell.h). p: pointer x, y (fractions of the canvas width / height),
// zoom, then half width, half height, corner radius, ring width, crosshair arm (fractions of the canvas height);
// nullptr: off (nothing is recorded from the next present on). 1: the present can draw it (active, the pass not failed).
extern "C" int omni_gpu_present_lens_ready(void)
{
    return g.state.load(std::memory_order_acquire) == kActive && !g.hung && !mg.broken ? 1 : 0;
}
extern "C" int omni_gpu_present_lens(const float* p)
{
    {
        std::lock_guard<std::mutex> l(mg.lock);
        mg.want = p != nullptr;
        if (p) memcpy(mg.p, p, sizeof mg.p);
    }
    return omni_gpu_present_lens_ready();
}
'''

CANVAS_TO_SRC = ('    barrier(g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, VK_ACCESS_TRANSFER_WRITE_BIT, '
                 'VK_ACCESS_TRANSFER_READ_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);\n'
                 '    g.canvas.layout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;\n    rec.readback = false;\n')
EDITS = [
    ('#include "OmniZcPageShader.h"',
     '#include "OmniMagnifierShader.h"   // OMNI_MAGNIFIER_V1: SPIR-V of omni_magnifier.comp\n#include "OmniZcPageShader.h"'),
    ('bool hdrEnsure(uint32_t w, uint32_t h);\nbool ensureCanvas(uint32_t w, uint32_t h)\n{\n',
     STATE + 'bool hdrEnsure(uint32_t w, uint32_t h);\nbool ensureCanvas(uint32_t w, uint32_t h)\n{\n'),
    (CANVAS_TO_SRC,
     '    mgRecord(w, h, wantReadback);   // OMNI_MAGNIFIER_V1: the lens over everything composed above, tint included (nothing while off)\n'
     + CANVAS_TO_SRC),
    ('// OMNI_GPUPAGES_ZEROCOPY_V1: the shell\'s side (OmniBrowser.cpp, OMNI_GPUPAGES_ZEROCOPY_V1)\n',
     API + '// OMNI_GPUPAGES_ZEROCOPY_V1: the shell\'s side (OmniBrowser.cpp, OMNI_GPUPAGES_ZEROCOPY_V1)\n'),
    ('        zcDestroy();   // OMNI_GPUPAGES_ZEROCOPY_V1: its pipeline before the device (RADV asserts otherwise)\n',
     '        mgDestroy();   // OMNI_MAGNIFIER_V1: its pipeline and buffer before the device\n'
     '        zcDestroy();   // OMNI_GPUPAGES_ZEROCOPY_V1: its pipeline before the device (RADV asserts otherwise)\n'),
    ('    *buffers = g.liveBuffers.load(); *images = g.liveImages.load(); *memory = g.liveMemory.load();\n    if (g.queries)',
     '    mgDestroy();   // OMNI_MAGNIFIER_V1 (host test teardown)\n'
     '    *buffers = g.liveBuffers.load(); *images = g.liveImages.load(); *memory = g.liveMemory.load();\n    if (g.queries)'),
]
for old, _ in EDITS:   # every anchor is checked before anything is written
    if t.count(old) != 1:
        sys.exit('OmniGpuPresent.cpp: anchor found %d times: %r' % (t.count(old), old[:90]))
for old, new in EDITS:
    t = t.replace(old, new, 1)
shutil.copyfile(s1 / 'OmniMagnifierShader.h', src / 'OmniMagnifierShader.h')
save(t)
print('applied ' + REV + ' (OmniGpuPresent.cpp + OmniMagnifierShader.h)')
