#!/usr/bin/env python3
"""OMNI_GPUPAGES_ZEROCOPY_V1, title GPU present side (outputs/omni-gpu-pages/ZERO-COPY-DESIGN.md).

Patches OmniGpuPresent.cpp (the copy prep_launch.py put in the title workspace's src/) and copies OmniZcPageShader.h
next to it:
  - omni_gpu_present_zc_ready(): the shell may use GPU pages (device up, HDR canvas armed (storage-capable), pipeline
    built, nothing failed);
  - omni_gpu_present_zc_page(ctl, dx, dy, dw, dh): the shell's page rect and the engine's control page (nullptr: off;
    the engine's buffers are then forgotten);
  - in recordCompose, after the canvas and before it becomes a transfer source: the published frame is imported
    (cachedLayer, storage) and composed under the shell's overlays by omni_zc_page.comp;
  - in layersDone (after every present's fence): the engine is told the frame was consumed.
Any failure (import, rect, no canvas view) sets `broken`: ready() turns 0 and the shell goes back to the CPU page.
usage: apply_zerocopy_present.py <src dir holding OmniGpuPresent.cpp> <stage1/src-title>"""
import shutil, sys
from pathlib import Path

MARK = 'OMNI_GPUPAGES_ZEROCOPY_V1'
src, s1 = Path(sys.argv[1]), Path(sys.argv[2])
p = src / 'OmniGpuPresent.cpp'
t = p.read_text(encoding='utf-8')
if MARK in t:
    print('already OmniGpuPresent.cpp'); sys.exit(0)
shutil.copyfile(s1 / 'OmniZcPageShader.h', src / 'OmniZcPageShader.h')

EDITS = [
    ('#include "OmniPqOutShader.h"',
     '#include "OmniPqOutShader.h"\n#include "OmniZcPageShader.h"   // OMNI_GPUPAGES_ZEROCOPY_V1: SPIR-V of omni_zc_page.comp'),
    ('// After a present\'s fence: its layer is free again; forgotten ones go now.\nvoid layersDone()\n{\n',
     '// OMNI_GPUPAGES_ZEROCOPY_V1 (defined further down)\nvoid zcAfterFence();\nvoid zcRecord(int w, int h, bool wantReadback, bool video);\n'
     '// After a present\'s fence: its layer is free again; forgotten ones go now.\nvoid layersDone()\n{\n    zcAfterFence();   // OMNI_GPUPAGES_ZEROCOPY_V1: the engine may reuse the frame it read\n'),
    ('    barrier(g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);\n'
     '    g.canvas.layout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;\n    rec.readback = false;\n',
     '    zcRecord(w, h, wantReadback, rec.video);   // OMNI_GPUPAGES_ZEROCOPY_V1: the engine\'s page frame under the shell\'s overlays\n'
     '    barrier(g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);\n'
     '    g.canvas.layout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;\n    rec.readback = false;\n'),
    ('// V4: HDR10 passthrough. The staged picture\'s PQ layer',
     r'''// ---------------------------------------------------------------- OMNI_GPUPAGES_ZEROCOPY_V1
// The engine's control page (layout = ogp-s1-surface.inc's OmniZcCtl).
struct ZcCtl {
    uint32_t magic, version; int32_t pid, consumer; uint32_t seq, slot, width, height, stride, pad;
    uint64_t address, frame, consumed, titleBeat, engineBeat;
};
struct ZcPush { int32_t dx, dy, dw, dh, sw, sh, stride, bgra; };
struct ZcState {
    std::mutex lock;   // the shell thread sets the page; the present records it
    ZcCtl* ctl = nullptr; int dx = 0, dy = 0, dw = 0, dh = 0;
    bool tried = false, ready = false, broken = false;
    VkShaderModule shader = VK_NULL_HANDLE; VkDescriptorSetLayout setLayout = VK_NULL_HANDLE; VkPipelineLayout layout = VK_NULL_HANDLE;
    VkPipeline pipe = VK_NULL_HANDLE; VkDescriptorPool pool = VK_NULL_HANDLE; VkDescriptorSet set = VK_NULL_HANDLE;
    ZcCtl* pendingCtl = nullptr; uint64_t pendingFrame = 0;
    const void* seen[4] = { nullptr, nullptr, nullptr, nullptr }; int seenNext = 0;
    uint64_t composed = 0, skipped = 0, importFails = 0; double lastLog = 0;
} zc;
void zcBreak(const char* why)
{
    if (!zc.broken) plog(true, "zero-copy page OFF: %s (the shell paints the page on the CPU again)", why);
    zc.broken = true;
}
bool zcSetUp()   // once; needs the HDR pass's entry points (loadHdrFns) and the storage-capable canvas
{
    if (zc.tried) return zc.ready;
    zc.tried = true;
    if (!g.device || !g.pqArmed || !loadHdrFns()) { plog(false, "zero-copy page: not available (no HDR-armed canvas)"); return false; }
    VkShaderModuleCreateInfo smi { VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO }; smi.codeSize = sizeof kOmniZcPageSpv; smi.pCode = kOmniZcPageSpv;
    if (g.vk.vkCreateShaderModule(g.device, &smi, nullptr, &zc.shader) != VK_SUCCESS) return false;
    VkDescriptorSetLayoutBinding b[2] {};
    b[0].binding = 0; b[0].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE; b[0].descriptorCount = 1; b[0].stageFlags = VK_SHADER_STAGE_COMPUTE_BIT;
    b[1].binding = 1; b[1].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; b[1].descriptorCount = 1; b[1].stageFlags = VK_SHADER_STAGE_COMPUTE_BIT;
    VkDescriptorSetLayoutCreateInfo dl { VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO }; dl.bindingCount = 2; dl.pBindings = b;
    if (g.vk.vkCreateDescriptorSetLayout(g.device, &dl, nullptr, &zc.setLayout) != VK_SUCCESS) return false;
    VkPushConstantRange range { VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof(ZcPush) };
    VkPipelineLayoutCreateInfo pl { VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO }; pl.setLayoutCount = 1; pl.pSetLayouts = &zc.setLayout; pl.pushConstantRangeCount = 1; pl.pPushConstantRanges = &range;
    if (g.vk.vkCreatePipelineLayout(g.device, &pl, nullptr, &zc.layout) != VK_SUCCESS) return false;
    VkComputePipelineCreateInfo cp { VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO };
    cp.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO; cp.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT; cp.stage.module = zc.shader; cp.stage.pName = "main"; cp.layout = zc.layout;
    if (g.vk.vkCreateComputePipelines(g.device, VK_NULL_HANDLE, 1, &cp, nullptr, &zc.pipe) != VK_SUCCESS) return false;
    VkDescriptorPoolSize ps[2] = { { VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, 1 }, { VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1 } };
    VkDescriptorPoolCreateInfo dp { VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO }; dp.maxSets = 1; dp.poolSizeCount = 2; dp.pPoolSizes = ps;
    if (g.vk.vkCreateDescriptorPool(g.device, &dp, nullptr, &zc.pool) != VK_SUCCESS) return false;
    VkDescriptorSetAllocateInfo da { VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO }; da.descriptorPool = zc.pool; da.descriptorSetCount = 1; da.pSetLayouts = &zc.setLayout;
    if (g.vk.vkAllocateDescriptorSets(g.device, &da, &zc.set) != VK_SUCCESS) return false;
    zc.ready = true;
    plog(true, "zero-copy page: compose pipeline ready (OMNI_GPUPAGES_ZEROCOPY_V1)");
    return true;
}
// Recording, canvas in TRANSFER_DST: the latest published frame (seqlock) composed into the page rect.
void zcRecord(int w, int h, bool wantReadback, bool video)
{
    std::lock_guard<std::mutex> l(zc.lock);
    if (!zc.ctl || zc.broken || !zc.ready) return;
    if (wantReadback || video) { zc.skipped++; return; }   // the differential check compares with the CPU canvas; video: the CPU page path
    if (!g.canvasView) { zcBreak("no canvas view"); return; }
    ZcCtl* c = zc.ctl;
    const uint32_t s1 = __atomic_load_n(&c->seq, __ATOMIC_ACQUIRE);
    const uint64_t frame = c->frame, address = c->address; const uint32_t sw = c->width, sh = c->height, stride = c->stride;
    const uint32_t s2 = __atomic_load_n(&c->seq, __ATOMIC_ACQUIRE);
    if ((s1 & 1) || s1 != s2 || !frame || !address || !sw || !sh || stride < sw * 4 || stride % 4) { zc.skipped++; return; }
    const int dx = std::max(zc.dx, 0), dy = std::max(zc.dy, 0), dw = std::min(zc.dw, w - dx), dh = std::min(zc.dh, h - dy);
    if (dw <= 0 || dh <= 0) { zc.skipped++; return; }
    const size_t bytes = size_t(stride) * sh;
    Cached* layer = cachedLayer(reinterpret_cast<const void*>(uintptr_t(address)), bytes, true);
    if (!layer) { zc.importFails++; zcBreak("the engine's frame buffer could not be imported"); return; }
    bool known = false; for (const void* s : zc.seen) known = known || s == reinterpret_cast<const void*>(uintptr_t(address));
    if (!known) { zc.seen[zc.seenNext] = reinterpret_cast<const void*>(uintptr_t(address)); zc.seenNext = (zc.seenNext + 1) % 4; }
    VkDescriptorImageInfo ii { VK_NULL_HANDLE, g.canvasView, VK_IMAGE_LAYOUT_GENERAL };
    VkDescriptorBufferInfo bo { layer->b.buffer, layer->offset, VkDeviceSize(bytes) };
    VkWriteDescriptorSet wr[2] {};
    wr[0].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET; wr[0].dstSet = zc.set; wr[0].dstBinding = 0; wr[0].descriptorCount = 1; wr[0].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE; wr[0].pImageInfo = &ii;
    wr[1].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET; wr[1].dstSet = zc.set; wr[1].dstBinding = 1; wr[1].descriptorCount = 1; wr[1].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; wr[1].pBufferInfo = &bo;
    g.vk.vkUpdateDescriptorSets(g.device, 2, wr, 0, nullptr);
    barrier(g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_GENERAL, VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT,
            VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT);
    g.vk.vkCmdBindPipeline(g.cmd, VK_PIPELINE_BIND_POINT_COMPUTE, zc.pipe);
    g.vk.vkCmdBindDescriptorSets(g.cmd, VK_PIPELINE_BIND_POINT_COMPUTE, zc.layout, 0, 1, &zc.set, 0, nullptr);
    ZcPush pc { dx, dy, dw, dh, int32_t(sw), int32_t(sh), int32_t(stride / 4), 1 };
    g.vk.vkCmdPushConstants(g.cmd, zc.layout, VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof pc, &pc);
    g.vk.vkCmdDispatch(g.cmd, uint32_t(dw + 7) / 8, uint32_t(dh + 7) / 8, 1);
    barrier(g.canvas.image, VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_ACCESS_SHADER_WRITE_BIT, VK_ACCESS_TRANSFER_WRITE_BIT | VK_ACCESS_TRANSFER_READ_BIT,
            VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
    zc.pendingCtl = c; zc.pendingFrame = frame; zc.composed++;
    if (zc.composed == 1 || nowMs() - zc.lastLog >= 5000) {
        plog(false, "zero-copy page: composed %llu (skipped %llu), frame %llu %ux%u at %p -> %d,%d %dx%d", (unsigned long long)zc.composed,
             (unsigned long long)zc.skipped, (unsigned long long)frame, sw, sh, reinterpret_cast<void*>(uintptr_t(address)), dx, dy, dw, dh);
        zc.lastLog = nowMs();
    }
}
void zcAfterFence()
{
    std::lock_guard<std::mutex> l(zc.lock);
    if (zc.pendingCtl) __atomic_store_n(&zc.pendingCtl->consumed, zc.pendingFrame, __ATOMIC_RELEASE);
    zc.pendingCtl = nullptr; zc.pendingFrame = 0;
}
// Teardown (teardownLocked, device idle, before vkDestroyDevice): every object this pass made. Without it RADV's device
// teardown asserts in vk_pipeline_cache_destroy (console 2026-11-15T02:43Z: abort at title close, night9c).
void zcDestroy()
{
    std::lock_guard<std::mutex> l(zc.lock);
    if (!g.device) return;
    if (zc.pipe) g.vk.vkDestroyPipeline(g.device, zc.pipe, nullptr);
    if (zc.layout) g.vk.vkDestroyPipelineLayout(g.device, zc.layout, nullptr);
    if (zc.pool) g.vk.vkDestroyDescriptorPool(g.device, zc.pool, nullptr);   // frees zc.set
    if (zc.setLayout) g.vk.vkDestroyDescriptorSetLayout(g.device, zc.setLayout, nullptr);
    if (zc.shader) g.vk.vkDestroyShaderModule(g.device, zc.shader, nullptr);
    zc.pipe = VK_NULL_HANDLE; zc.layout = VK_NULL_HANDLE; zc.pool = VK_NULL_HANDLE; zc.set = VK_NULL_HANDLE;
    zc.setLayout = VK_NULL_HANDLE; zc.shader = VK_NULL_HANDLE; zc.ready = false; zc.tried = true; zc.ctl = nullptr; zc.pendingCtl = nullptr;
}

// V4: HDR10 passthrough. The staged picture's PQ layer'''),
    ('        hdrDestroy();   // its views first\n',
     '        zcDestroy();   // OMNI_GPUPAGES_ZEROCOPY_V1: its pipeline before the device (RADV asserts otherwise)\n        hdrDestroy();   // its views first\n'),
    ('\n#ifndef OMNI_GPU_PRESENT_HOST_TEST\n// ================================================================ console: display',
     r'''
// OMNI_GPUPAGES_ZEROCOPY_V1: the shell's side (OmniBrowser.cpp, OMNI_GPUPAGES_ZEROCOPY_V1)
extern "C" int omni_gpu_present_zc_ready(void)
{
    if (!g.device || g.hung || zc.broken) return 0;
    return zcSetUp() ? 1 : 0;
}
extern "C" void omni_gpu_present_zc_page(void* ctl, int dx, int dy, int dw, int dh)
{
    const void* forget[4] = { nullptr, nullptr, nullptr, nullptr };
    {
        std::lock_guard<std::mutex> l(zc.lock);
        if (!ctl && zc.ctl) { for (int i = 0; i < 4; ++i) { forget[i] = zc.seen[i]; zc.seen[i] = nullptr; } }
        zc.ctl = static_cast<ZcCtl*>(ctl); zc.dx = dx; zc.dy = dy; zc.dw = dw; zc.dh = dh;
    }
    for (const void* p : forget) if (p) omni_gpu_present_forget(p);   // the engine's buffers: never kept past their use
}

#ifndef OMNI_GPU_PRESENT_HOST_TEST
// ================================================================ console: display'''),
]
for old, new in EDITS:
    if t.count(old) != 1:
        sys.exit('OmniGpuPresent.cpp: anchor found %d times: %r' % (t.count(old), old[:80]))
    t = t.replace(old, new, 1)
p.write_text(t, encoding='utf-8')
print('patched OmniGpuPresent.cpp (+ OmniZcPageShader.h)')
