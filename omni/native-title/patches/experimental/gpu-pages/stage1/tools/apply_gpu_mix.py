#!/usr/bin/env python3
"""OMNI_GPU_MIX_V1 (2026-11-17): the hole-punch's translucent page pixels over a full-screen video are blended by the
GPU present (one compute dispatch) instead of the CPU, while the GPU present is active and in SDR.

Why (console, 2026-11-17)
  A semi-transparent layer over a full-screen 4K video (a dim layer, letterbox bars, player controls) made the shell's
  main thread take 53-71 ms per page frame (9-10 ms without) and the presenter 4.4-8.5 ms per video frame: the
  record-only compose (OMNI_PERF_B_V1) appended every translucent pixel to rec.mixPos / rec.mixPage (8.3M entries at 4K),
  the hand-off copied them into v7Live, and the presenter blended all of them on the CPU (omniWriteMixSpans) on every
  before-flip and re-flip, even with the GPU present already copying the opaque video runs.

What changes
  engine/media/OmniHwService.cpp (the hole-punch)
    - holePunchCompose, record-only path: when gmChoose() (the GPU present is active, its HDR state is 0, it reports
      omni_gpu_present_mix_ready(), no refusal in the last 250 ms, no kill-switch flag) the row recorder is
      holeRecordRowGpuMix: hole runs exactly as before (runs + 0 placeholders); a translucent run becomes ONE (y, x, n)
      triplet in rec.gmSpans and the page pixel itself is written into the canvas in canvas byte order (the shell had
      put page-over-background there, not the page); no mixPos / mixPage / zeroing for them. rec.gpuMix marks it.
      Caps as before (v7MaxRuns for the triplets, v7MaxMix pixels): past them, the old blend of every row.
    - hand-off (prepare + publish): live.gmSpans / live.gpuMix carried over; live.valid counts them. Hole runs and
      pbMergeExtraMix are unchanged (shell pixels over the 0 placeholders stay CPU mix pixels).
    - presenter (holePunchBeforeFlip -> v8WriteLive, holePunchReflip): gpuStageVideo stages runs + spans with
      omni_gpu_present_stage_video_mix (runs may be empty: a dim layer over the whole video has none). When that is
      refused (or not tried: hand-off re-select, GPU present gone) gmMaterialize turns the live record back into the
      CPU record from the frame's own pixels (the page pixels are still in it: the GPU never writes the surface), so
      that frame and its re-flips are blended on the CPU exactly as before -- no frame shows unblended pixels -- and
      the next composes use the CPU record for 250 ms. v139Direct (SDL tiler, GPU present off) never takes a gpu-mix
      record. holeFillRecordOnly blends the spans in place (from the canvas's page pixels).
  src/OmniGpuPresent.cpp (title, GPU present)
    - omni_gpu_present_mix_ready(), omni_gpu_present_stage_video_mix(...) (C API, weak in OmniHwService.cpp).
    - VideoStage.mix; recordCompose: the layer imported with STORAGE usage too (as OMNI_HDR_PRESENT10_V1's PQ layer),
      then after the video runs are in the canvas and before zero-copy / Night light / colour filter / magnifier /
      SDR->PQ: gmPrepare (span list into a persistent host buffer, grown never per frame; descriptor set rewritten)
      + gmRecord (TRANSFER_DST -> GENERAL, one dispatch of omni_gpu_mix.comp, one workgroup per span, -> TRANSFER_DST).
    - the pass is set up lazily by the first staging (presenter thread, under g.lock); canvases are made with STORAGE
      usage from then on (nl.storage, as Night light), so that first staging is refused (CPU frame) and the next
      present remakes the canvas once. gm.broken (atomic) + gmBreak log line, like nlBreak.
    - read-back (verify) frames: the pass RUNS (the hole-punch cannot know which present verifies, and has no page
      values to CPU-blend with); verifyComposed's expectation applies holeBlendPixel's formula to the spans, within
      1 per channel; a larger difference turns the GPU mix off (gmBreak), never the GPU video path.
    - refused (CPU frame) while HDR output is armed or on, before the canvas has STORAGE usage, when the layer's
      storage import fails, when the pass failed. teardown / host teardown destroy its objects.
  shader/omni_gpu_mix.comp (+ .spv, src/OmniGpuMixShader.h): out = page + div255(video * (255 - a)), clamp 255,
    alpha 255, per byte (canvas and layer have the same byte order on the GPU present: the layer is RGBA like the
    ABGR8888 surface, so swapRB needs no shader work); integer arithmetic, bit-exact with holeBlendPixel.

Kill switch: /data/omni/gpu-mix-off.flag (read once by the hole-punch): exactly the previous behaviour.
Unchanged: the non-record-only compose (partial-screen video), SDL's software present, HDR10 / armed HDR (CPU path).

Patches the eboot workspace in place ("$NE", after apply_gpu_default_on.py). Every anchor is checked before anything is
written; CRLF or LF files; a patched tree prints "already". Backups: <file>.before-gpu-mix (first apply only).
Host test: tools/test_gpu_mix.cpp (lavapipe).
R2 (HDR Auto, state 1, allowed) and V2 (a partly covering paced video, e.g. the layer at 0,120 under the top bar, takes
the record-only path when the GPU mix is chosen) are applied after V1; see OMNI_GPU_MIX_V1_R2 / OMNI_GPU_MIX_V2 below.
usage: apply_gpu_mix.py <eboot workspace root>"""
import shutil
import subprocess
import sys
from pathlib import Path

MARK = 'OMNI_GPU_MIX_V1'
root = Path(sys.argv[1])
present = root / 'src' / 'OmniGpuPresent.cpp'
hw = root / 'engine' / 'media' / 'OmniHwService.cpp'
comp = root / 'shader' / 'omni_gpu_mix.comp'
spv = root / 'shader' / 'omni_gpu_mix.spv'
hdr = root / 'src' / 'OmniGpuMixShader.h'
tool = root / 'tools' / 'spv_to_header.py'


def load(p):
    raw = p.read_bytes().decode('utf-8')
    nl = '\r\n' if raw.count('\r\n') * 2 > raw.count('\n') else '\n'
    return raw.replace('\r\n', '\n'), nl


def save(p, text, nl):
    bak = p.with_name(p.name + '.before-gpu-mix')
    if not bak.exists():
        shutil.copy2(p, bak)
    p.write_bytes(text.replace('\n', nl).encode('utf-8'))


def apply_edits(text, edits, name):
    """edits: (old, new, count). All anchors are checked first; then replaced."""
    for old, new, count in edits:
        if text.count(old) != count:
            sys.exit('%s: anchor found %d times (want %d): %r' % (name, text.count(old), count, old[:100]))
    for old, new, count in edits:
        text = text.replace(old, new)
    return text


SHADER = r'''// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_GPU_MIX_V1 (tools/apply_gpu_mix.py): the hole-punch's translucent page pixels over the video, blended in the
// canvas image by the GPU present. Each workgroup blends one span (one canvas row, consecutive x): the canvas texel is
// the page pixel the shell left there (premultiplied, canvas byte order, with its alpha), the video word comes from the
// staged layer (same byte order), out = page + div255(video * (255 - alpha)) per channel, clamped to 255, alpha 255:
// holeBlendPixel's integer arithmetic (OmniHwService.cpp), so the result is bit-exact with the CPU blend.
#version 450
layout(local_size_x = 64) in;
layout(set = 0, binding = 0, rgba8) uniform image2D canvas;                    // the canvas image (R8G8B8A8_UNORM)
layout(std430, set = 0, binding = 1) readonly buffer Src { uint src[]; };       // the video layer (imported host memory)
layout(std430, set = 0, binding = 2) readonly buffer Spans { uvec4 spans[]; };  // x: source word (layer-relative), y: canvas x, z: canvas y, w: pixels
layout(push_constant) uniform Push { uint count; uint srcBase; uint perRow; uint pad; } pc;
uint div255(uint x) { x += 128u; return (x + (x >> 8u)) >> 8u; }
void main()
{
    const uint s = gl_WorkGroupID.y * pc.perRow + gl_WorkGroupID.x;
    if (s >= pc.count) return;
    const uvec4 sp = spans[s];
    for (uint i = gl_LocalInvocationID.x; i < sp.w; i += 64u) {
        const ivec2 at = ivec2(int(sp.y + i), int(sp.z));
        const uvec4 p = uvec4(round(clamp(imageLoad(canvas, at), 0.0, 1.0) * 255.0));
        const uint v = src[pc.srcBase + sp.x + i];
        const uint k = 255u - p.a;
        const uvec3 o = min(p.rgb + uvec3(div255((v & 255u) * k), div255(((v >> 8u) & 255u) * k), div255(((v >> 16u) & 255u) * k)), uvec3(255u));
        imageStore(canvas, at, vec4(vec3(o), 255.0) / 255.0);
    }
}
'''

# ------------------------------------------------------------------------------------------- OmniGpuPresent.cpp
GP_STATE = r'''// ---------------------------------------------------------------- OMNI_GPU_MIX_V1
// GPU blend of the hole-punch's translucent page pixels over the video (tools/apply_gpu_mix.py). The hole-punch's
// record-only compose leaves the page pixel itself (premultiplied, canvas byte order, with its alpha) in the surface at
// every translucent position over a full-screen video and stages those positions as spans (y, x, n) with the picture
// (omni_gpu_present_stage_video_mix); recordCompose blends them in place in the canvas image right after the video runs:
// out = page + video * (255 - alpha) / 255 per channel (holeBlendPixel's rounding), alpha 255, one workgroup per span
// (omni_gpu_mix.comp). Before zero-copy, Night light, the colour filter, the magnifier and the SDR -> PQ pass.
struct GmPush { uint32_t count, srcBase, perRow, pad; };
static_assert(sizeof(GmPush) == 16, "push constants of omni_gpu_mix.comp");
constexpr uint32_t kGmPerRow = 32768;   // workgroups per dispatch row (<= 65535, Vulkan's minimum)
struct GmState {
    bool tried = false, ready = false;   // set-up done / succeeded (present side, under g.lock)
    std::atomic<bool> broken { false };  // set by gmBreak (present side), read by omni_gpu_present_mix_ready (shell main thread)
    VkShaderModule shader = VK_NULL_HANDLE; VkDescriptorSetLayout setLayout = VK_NULL_HANDLE; VkPipelineLayout layout = VK_NULL_HANDLE;
    VkPipeline pipe = VK_NULL_HANDLE; VkDescriptorPool pool = VK_NULL_HANDLE; VkDescriptorSet set = VK_NULL_HANDLE;
    VkImageView view = VK_NULL_HANDLE; uint64_t viewGen = 0;
    Buf spans; size_t spansCap = 0;      // the span list (one uvec4 per span): persistent, grows, never made per frame
    uint32_t count = 0, srcBase = 0; VkDeviceSize maxRange = 0;
    uint64_t frames = 0, pixels = 0, spanTotal = 0, refused = 0; unsigned refusedLogs = 0; double lastLog = 0;
} gm;
void gmBreak(const char* why)
{
    if (!gm.broken.exchange(true)) plog(true, "OMNI_GPU_MIX_V1 OFF: %s (the hole-punch blends translucent pixels on the CPU again)", why);
}
void gmDropView()
{
    if (gm.view && g.device) g.vk.vkDestroyImageView(g.device, gm.view, nullptr);
    gm.view = VK_NULL_HANDLE; gm.viewGen = 0;
}

'''

GP_FUNCS = r'''// OMNI_GPU_MIX_V1: once (caller holds g.lock): the pass's pipeline; canvases are made with STORAGE usage from then on.
bool gmSetUp()
{
    if (gm.tried) return gm.ready && !gm.broken.load();
    gm.tried = true;
    if (!g.device || !loadHdrFns()) { gmBreak("device entry points missing"); return false; }
    if (g.canvasFormat != VK_FORMAT_R8G8B8A8_UNORM) { gmBreak("the canvas is not R8G8B8A8_UNORM"); return false; }
    VkFormatProperties fp {}; g.vk.vkGetPhysicalDeviceFormatProperties(g.physical, VK_FORMAT_R8G8B8A8_UNORM, &fp);
    if (!(fp.optimalTilingFeatures & VK_FORMAT_FEATURE_STORAGE_IMAGE_BIT)) { gmBreak("no storage-image support for the canvas format"); return false; }
    VkShaderModuleCreateInfo smi { VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO }; smi.codeSize = sizeof kOmniGpuMixSpv; smi.pCode = kOmniGpuMixSpv;
    if (g.vk.vkCreateShaderModule(g.device, &smi, nullptr, &gm.shader) != VK_SUCCESS) { gm.shader = VK_NULL_HANDLE; gmBreak("shader module"); return false; }
    VkDescriptorSetLayoutBinding b[3] {};
    for (uint32_t i = 0; i < 3; ++i) {
        b[i].binding = i; b[i].descriptorType = i ? VK_DESCRIPTOR_TYPE_STORAGE_BUFFER : VK_DESCRIPTOR_TYPE_STORAGE_IMAGE;
        b[i].descriptorCount = 1; b[i].stageFlags = VK_SHADER_STAGE_COMPUTE_BIT;
    }
    VkDescriptorSetLayoutCreateInfo dl { VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO }; dl.bindingCount = 3; dl.pBindings = b;
    if (g.vk.vkCreateDescriptorSetLayout(g.device, &dl, nullptr, &gm.setLayout) != VK_SUCCESS) { gm.setLayout = VK_NULL_HANDLE; gmBreak("set layout"); return false; }
    VkPushConstantRange range { VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof(GmPush) };
    VkPipelineLayoutCreateInfo pl { VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO }; pl.setLayoutCount = 1; pl.pSetLayouts = &gm.setLayout; pl.pushConstantRangeCount = 1; pl.pPushConstantRanges = &range;
    if (g.vk.vkCreatePipelineLayout(g.device, &pl, nullptr, &gm.layout) != VK_SUCCESS) { gm.layout = VK_NULL_HANDLE; gmBreak("pipeline layout"); return false; }
    VkComputePipelineCreateInfo cp { VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO };
    cp.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO; cp.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT; cp.stage.module = gm.shader; cp.stage.pName = "main"; cp.layout = gm.layout;
    if (g.vk.vkCreateComputePipelines(g.device, VK_NULL_HANDLE, 1, &cp, nullptr, &gm.pipe) != VK_SUCCESS) { gm.pipe = VK_NULL_HANDLE; gmBreak("compute pipeline"); return false; }
    const VkDescriptorPoolSize ps[2] = { { VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, 1 }, { VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 2 } };
    VkDescriptorPoolCreateInfo dp { VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO }; dp.maxSets = 1; dp.poolSizeCount = 2; dp.pPoolSizes = ps;
    if (g.vk.vkCreateDescriptorPool(g.device, &dp, nullptr, &gm.pool) != VK_SUCCESS) { gm.pool = VK_NULL_HANDLE; gmBreak("descriptor pool"); return false; }
    VkDescriptorSetAllocateInfo da { VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO }; da.descriptorPool = gm.pool; da.descriptorSetCount = 1; da.pSetLayouts = &gm.setLayout;
    if (g.vk.vkAllocateDescriptorSets(g.device, &da, &gm.set) != VK_SUCCESS) { gm.set = VK_NULL_HANDLE; gmBreak("descriptor set"); return false; }
    VkPhysicalDeviceProperties2 p2 { VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2 };
    if (g.vk.vkGetPhysicalDeviceProperties2) g.vk.vkGetPhysicalDeviceProperties2(g.physical, &p2);
    gm.maxRange = p2.properties.limits.maxStorageBufferRange;
    if (!gm.maxRange) { gmBreak("no storage buffer range reported"); return false; }
    gm.ready = true;
    nl.storage = true;   // ensureCanvas: the next canvas (or this one, remade once) is a storage image too (Night light's switch)
    plog(true, "OMNI_GPU_MIX_V1: armed (translucent page pixels over a full-screen video blended by one compute dispatch; canvas STORAGE usage %s; storage range %.0f MiB)",
         nl.canvasStorage ? "already on" : "from the next present", double(gm.maxRange) / 1048576.0);
    return true;
}
// A staged span (canvas y, x, n) clipped to the canvas and the layer exactly as the video runs are. false: nothing left.
bool gmClip(const VideoStage& v, int w, int h, size_t k, int& y, int& x0, int& n)
{
    y = int(v.mix[k]); x0 = int(v.mix[k + 1]); n = int(v.mix[k + 2]);
    if (y < 0 || y >= h || x0 < 0 || x0 >= w || y - v.ly < 0 || y - v.ly >= v.h || x0 - v.lx < 0) return false;
    n = std::min({ n, w - x0, v.w - (x0 - v.lx) });
    return n > 0;
}
// CPU reference of omni_gpu_mix.comp = holeBlendPixel's arithmetic (page and video in the same byte order): verify frames.
inline unsigned gmDiv255(unsigned x) { x += 128; return (x + (x >> 8)) >> 8; }
void gmReference(const uint8_t* page, const uint8_t* video, uint8_t* out)
{
    const unsigned k = 255u - page[3];
    for (int c = 0; c < 3; ++c) out[c] = uint8_t(std::min(255u, page[c] + gmDiv255(video[c] * k)));
    out[3] = 255;
}
// While recording a frame with staged spans (caller holds g.lock; the previous present's fence has signalled, so nothing
// pending reads the set or the list): the clipped span list into the persistent buffer, the descriptor set at this
// frame's canvas view, layer and list. false: nothing to blend (a failure here turns the pass off, logged).
bool gmPrepare(int w, int h, const Cached* layer)
{
    const VideoStage& v = g.video;
    gm.count = 0;
    if (v.mix.empty() || !layer) return false;
    auto fail = [](const char* why) { gmBreak(why); return false; };
    if (gm.broken.load() || !gmSetUp()) return false;
    if (!layer->storage) return fail("the layer was not imported for shader reads");
    if (!nl.canvasStorage || !g.canvas.image) return fail("the canvas has no STORAGE usage");
    if ((layer->offset & 3) || (v.stride & 3)) return fail("the layer is not word-aligned");
    if (layer->b.size > gm.maxRange || layer->b.size / 4 > 0xffffffffull) return fail("the layer is beyond the storage buffer range");
    const size_t most = v.mix.size() / 3;
    if (most > gm.spansCap) {   // grows rarely (never per frame)
        const size_t cap = std::max<size_t>(8192, most + most / 4);
        freeBuf(gm.spans); gm.spansCap = 0;
        if (!makeHostBuffer(gm.spans, VkDeviceSize(cap) * 16, false, VK_BUFFER_USAGE_STORAGE_BUFFER_BIT)) return fail("no span list buffer");
        gm.spansCap = cap;
        plog(false, "OMNI_GPU_MIX_V1: span list buffer for %zu spans (%.2f MiB, persistent)", cap, cap * 16 / 1048576.0);
    }
    uint32_t* out = static_cast<uint32_t*>(gm.spans.mapped); uint32_t count = 0; uint64_t px = 0;
    const uint64_t rowWords = uint64_t(v.stride) / 4;
    for (size_t k = 0; k + 2 < v.mix.size(); k += 3) {
        int y = 0, x0 = 0, n = 0;
        if (!gmClip(v, w, h, k, y, x0, n)) continue;
        uint32_t* r = out + size_t(count) * 4;
        r[0] = uint32_t(uint64_t(y - v.ly) * rowWords + uint64_t(x0 - v.lx)); r[1] = uint32_t(x0); r[2] = uint32_t(y); r[3] = uint32_t(n);
        ++count; px += uint64_t(n);
    }
    if (!count) return false;
    if (!gm.spans.coherent && g.vk.vkFlushMappedMemoryRanges) {
        VkMappedMemoryRange mr { VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE }; mr.memory = gm.spans.memory; mr.size = VK_WHOLE_SIZE;
        g.vk.vkFlushMappedMemoryRanges(g.device, 1, &mr);
    }
    if (!gm.view || gm.viewGen != nl.canvasGen) {
        gmDropView();
        VkImageViewCreateInfo vi { VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO }; vi.image = g.canvas.image; vi.viewType = VK_IMAGE_VIEW_TYPE_2D;
        vi.format = VK_FORMAT_R8G8B8A8_UNORM; vi.subresourceRange = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1 };
        if (g.vk.vkCreateImageView(g.device, &vi, nullptr, &gm.view) != VK_SUCCESS) { gm.view = VK_NULL_HANDLE; return fail("canvas storage view"); }
        gm.viewGen = nl.canvasGen;
    }
    // rewritten every frame (never created): layer buffers come and go, and a freed handle's value can come back
    const VkDescriptorImageInfo ii { VK_NULL_HANDLE, gm.view, VK_IMAGE_LAYOUT_GENERAL };
    const VkDescriptorBufferInfo bi[2] = { { layer->b.buffer, 0, VK_WHOLE_SIZE }, { gm.spans.buffer, 0, VK_WHOLE_SIZE } };
    VkWriteDescriptorSet wr[3] {};
    for (uint32_t i = 0; i < 3; ++i) { wr[i].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET; wr[i].dstSet = gm.set; wr[i].dstBinding = i; wr[i].descriptorCount = 1; }
    wr[0].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE; wr[0].pImageInfo = &ii;
    wr[1].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; wr[1].pBufferInfo = &bi[0];
    wr[2].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER; wr[2].pBufferInfo = &bi[1];
    g.vk.vkUpdateDescriptorSets(g.device, 3, wr, 0, nullptr);
    gm.count = count; gm.srcBase = uint32_t(layer->offset / 4);
    gm.pixels += px; gm.spanTotal += count;
    return true;
}
// In recordCompose, after the frame and the video runs are in the canvas (TRANSFER_DST), before every later pass.
void gmRecord()
{
    if (!gm.count) return;
    barrier(g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_GENERAL, VK_ACCESS_TRANSFER_WRITE_BIT,
            VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT);
    VkMemoryBarrier mb { VK_STRUCTURE_TYPE_MEMORY_BARRIER }; mb.srcAccessMask = VK_ACCESS_HOST_WRITE_BIT; mb.dstAccessMask = VK_ACCESS_SHADER_READ_BIT;   // the span list, the layer
    g.vk.vkCmdPipelineBarrier(g.cmd, VK_PIPELINE_STAGE_HOST_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, 0, 1, &mb, 0, nullptr, 0, nullptr);
    g.vk.vkCmdBindPipeline(g.cmd, VK_PIPELINE_BIND_POINT_COMPUTE, gm.pipe);
    g.vk.vkCmdBindDescriptorSets(g.cmd, VK_PIPELINE_BIND_POINT_COMPUTE, gm.layout, 0, 1, &gm.set, 0, nullptr);
    const GmPush pc { gm.count, gm.srcBase, kGmPerRow, 0 };
    g.vk.vkCmdPushConstants(g.cmd, gm.layout, VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof pc, &pc);
    g.vk.vkCmdDispatch(g.cmd, std::min(gm.count, kGmPerRow), (gm.count + kGmPerRow - 1) / kGmPerRow, 1);
    barrier(g.canvas.image, VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_ACCESS_SHADER_WRITE_BIT,
            VK_ACCESS_TRANSFER_WRITE_BIT | VK_ACCESS_TRANSFER_READ_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
    gm.frames++;
    if (gm.frames == 1 || nowMs() - gm.lastLog >= 10000) {
        plog(false, "OMNI_GPU_MIX_V1: %llu frames blended on the GPU (this one %u spans), %llu spans / %llu pixels in all, %llu stagings refused",
             (unsigned long long)gm.frames, gm.count, (unsigned long long)gm.spanTotal, (unsigned long long)gm.pixels, (unsigned long long)gm.refused);
        gm.lastLog = nowMs();
    }
}
// Teardown (before the device goes): every object the pass made.
void gmDestroy()
{
    if (g.device) {
        gmDropView();
        freeBuf(gm.spans);
        if (gm.pipe) g.vk.vkDestroyPipeline(g.device, gm.pipe, nullptr);
        if (gm.pool) g.vk.vkDestroyDescriptorPool(g.device, gm.pool, nullptr);
        if (gm.layout) g.vk.vkDestroyPipelineLayout(g.device, gm.layout, nullptr);
        if (gm.setLayout) g.vk.vkDestroyDescriptorSetLayout(g.device, gm.setLayout, nullptr);
        if (gm.shader) g.vk.vkDestroyShaderModule(g.device, gm.shader, nullptr);
    }
    gm.spans = Buf {}; gm.spansCap = 0; gm.count = 0;
    gm.view = VK_NULL_HANDLE; gm.viewGen = 0;
    gm.pipe = VK_NULL_HANDLE; gm.pool = VK_NULL_HANDLE; gm.set = VK_NULL_HANDLE; gm.layout = VK_NULL_HANDLE; gm.setLayout = VK_NULL_HANDLE; gm.shader = VK_NULL_HANDLE;
    gm.tried = gm.ready = false; gm.broken = false;
}

'''

GP_API = r'''
// OMNI_GPU_MIX_V1: for the hole-punch (OmniHwService.cpp, weak there). 1: a record-only compose may leave translucent
// page pixels for the GPU (the present is active and SDR, the GPU video path is on, the mix pass has not failed).
// Any thread, no lock (as omni_gpu_present_night_ready).
extern "C" int omni_gpu_present_mix_ready(void)
{
    return g.state.load(std::memory_order_acquire) == kActive && !g.hung && g.optVideo && g.hostImport
        && !gm.broken.load(std::memory_order_acquire) && g.hdrState.load(std::memory_order_acquire) == 0 ? 1 : 0;
}
// OMNI_GPU_MIX_V1: omni_gpu_present_stage_video plus the translucent spans (y, x, n triplets in canvas coordinates, each
// inside one row; runs may be empty). 1: both staged for the next present, which blends the spans in the canvas image.
// 0: nothing staged; the caller writes the runs and blends the spans on the CPU (as before). Refused while HDR output is
// armed or on, when the pass failed, before the canvas has STORAGE usage (the first call sets the pass up; the next
// present remakes the canvas once) and when the layer cannot be imported for shader reads. Presenter thread.
extern "C" int omni_gpu_present_stage_video_mix(const void* px, size_t bytes, int stride, int lx, int ly, int w, int h,
                                                const uint32_t* runs, size_t runWords, const uint32_t* spans, size_t spanWords,
                                                void (*release)(void*), void* cookie)
{
    if (!spans || !spanWords) return runWords ? omni_gpu_present_stage_video(px, bytes, stride, lx, ly, w, h, runs, runWords, release, cookie) : 0;
    if (g.state.load(std::memory_order_acquire) != kActive || !g.optVideo || !g.hostImport || !px || stride <= 0 || (stride & 3) || (runWords && !runs)) return 0;
    std::lock_guard<std::mutex> l(g.lock);
    const char* why = nullptr;
    if (!g.optVideo || g.hung || !g.device) why = "the GPU video path is off";
    else if (g.hdr || g.hdrState.load(std::memory_order_acquire) != 0) why = "HDR output is armed or on";
    else if (gm.broken.load() || !gmSetUp()) why = "the mix pass is off";
    else if (!nl.canvasStorage || !g.canvas.image) why = "the canvas gets STORAGE usage at the next present";
    else if (!cachedLayer(px, bytes, true)) why = "the layer's storage import failed";   // kept (in use until layersDone)
    if (why) {
        gm.refused++;
        if (gm.refusedLogs++ < 12) plog(false, "OMNI_GPU_MIX_V1: staging refused (%s): the hole-punch blends this frame on the CPU", why);
        return 0;
    }
    if (g.video.valid) releaseVideo();   // a staged frame that was never presented
    VideoStage& v = g.video;
    v.px = static_cast<const uint8_t*>(px); v.bytes = bytes; v.stride = stride; v.lx = lx; v.ly = ly; v.w = w; v.h = h;
    if (runWords) v.runs.assign(runs, runs + runWords); else v.runs.clear();
    v.mix.assign(spans, spans + spanWords);   // capacity kept between frames
    v.release = release; v.cookie = cookie; v.valid = true;
    v.pq = nullptr; v.pqBytes = 0; v.info = 0;
    return 1;
}
'''

GP_VERIFY_MIX = r'''            videoPx += size_t(n);
        }
    }
    // OMNI_GPU_MIX_V1: the staged translucent spans: the surface holds the page pixel there (canvas byte order, as the
    // canvas image), so expected = gmReference(page, video) (holeBlendPixel's arithmetic). The GPU pass may differ by 1
    // per channel; a larger difference turns the GPU mix off (never the GPU video path: those pixels are not counted).
    std::vector<uint8_t> mixMask; size_t mixPx = 0, mixNear = 0, mixBad = 0;
    if (withVideo && !g.video.mix.empty()) {
        mixMask.assign(size_t(w) * h, 0);
        const VideoStage& v = g.video;
        for (size_t k = 0; k + 2 < v.mix.size(); k += 3) {
            int y = 0, x0 = 0, n = 0;
            if (!gmClip(v, w, h, k, y, x0, n)) continue;
            for (int q = 0; q < n; ++q) {
                uint8_t* e = expect.data() + (size_t(y) * w + x0 + q) * 4;
                gmReference(e, v.px + size_t(y - v.ly) * v.stride + size_t(x0 + q - v.lx) * 4, e);
                mixMask[size_t(y) * w + x0 + q] = 1;
            }
            mixPx += size_t(n);
        }
    }
    size_t bad = 0; int firstX = -1, firstY = -1;
    for (size_t i = 0; i < expect.size(); i += 4) {
        if (!memcmp(&expect[i], got + i, 4)) continue;
        if (!mixMask.empty() && mixMask[i / 4]) {   // OMNI_GPU_MIX_V1
            const bool near = got[i + 3] == expect[i + 3] && std::abs(int(got[i]) - int(expect[i])) <= 1
                && std::abs(int(got[i + 1]) - int(expect[i + 1])) <= 1 && std::abs(int(got[i + 2]) - int(expect[i + 2])) <= 1;
            ++(near ? mixNear : mixBad);
            continue;
        }
        if (!bad) { firstX = int((i / 4) % w); firstY = int((i / 4) / w); }
        ++bad;
    }
'''

GP_EDITS = [
    ('#include "OmniMagnifierShader.h"   // OMNI_MAGNIFIER_V1: SPIR-V of omni_magnifier.comp\n',
     '#include "OmniMagnifierShader.h"   // OMNI_MAGNIFIER_V1: SPIR-V of omni_magnifier.comp\n'
     '#include "OmniGpuMixShader.h"   // OMNI_GPU_MIX_V1: SPIR-V of omni_gpu_mix.comp\n', 1),
    ('    std::vector<uint32_t> runs;   // y, x, n triplets, canvas coordinates\n',
     '    std::vector<uint32_t> runs;   // y, x, n triplets, canvas coordinates\n'
     '    std::vector<uint32_t> mix;    // OMNI_GPU_MIX_V1: translucent page spans (y, x, n), blended over the layer on the GPU\n', 1),
    ('v.valid = false; v.release = nullptr; v.cookie = nullptr; v.px = nullptr; v.runs.clear(); v.pq = nullptr; v.pqBytes = 0; v.info = 0;\n',
     'v.valid = false; v.release = nullptr; v.cookie = nullptr; v.px = nullptr; v.runs.clear(); v.pq = nullptr; v.pqBytes = 0; v.info = 0;\n'
     '    v.mix.clear();   // OMNI_GPU_MIX_V1 (capacity kept)\n', 1),
    ('bool hdrEnsure(uint32_t w, uint32_t h);\nbool ensureCanvas(uint32_t w, uint32_t h)\n',
     GP_STATE + 'bool hdrEnsure(uint32_t w, uint32_t h);\nbool ensureCanvas(uint32_t w, uint32_t h)\n', 1),
    ('        nlDropView();   // OMNI_NIGHT_LIGHT_V1: its storage view too\n',
     '        nlDropView();   // OMNI_NIGHT_LIGHT_V1: its storage view too\n'
     '        gmDropView();   // OMNI_GPU_MIX_V1: its storage view too\n', 1),
    ('// Records: source frame -> canvas image, staged video runs -> canvas image, [canvas -> read-back],\n',
     GP_FUNCS + '// Records: source frame -> canvas image, staged video runs -> canvas image, [canvas -> read-back],\n', 1),
    ('    rec.layer = g.video.valid && g.optVideo && !g.video.runs.empty() ? cachedLayer(g.video.px, g.video.bytes) : nullptr;\n',
     '    // OMNI_GPU_MIX_V1: spans alone (a dim layer over the whole video has no runs) need the layer too, readable by a shader\n'
     '    rec.layer = g.video.valid && g.optVideo && (!g.video.runs.empty() || !g.video.mix.empty()) ? cachedLayer(g.video.px, g.video.bytes, !g.video.mix.empty()) : nullptr;\n', 1),
    ('    if (g.video.valid && g.optVideo && !rec.video && !g.video.runs.empty()) plog(',
     '    if (g.video.valid && g.optVideo && !rec.video && (!g.video.runs.empty() || !g.video.mix.empty())) plog(', 1),
    ('    zcRecord(w, h, wantReadback, rec.video);   // OMNI_GPUPAGES_ZEROCOPY_V1',
     '    if (rec.video && !g.video.mix.empty() && gmPrepare(w, h, rec.layer)) gmRecord();   // OMNI_GPU_MIX_V1: the translucent page pixels over the video (verify frames too)\n'
     '    zcRecord(w, h, wantReadback, rec.video);   // OMNI_GPUPAGES_ZEROCOPY_V1', 1),
    ('            videoPx += size_t(n);\n        }\n    }\n    size_t bad = 0; int firstX = -1, firstY = -1;\n'
     '    for (size_t i = 0; i < expect.size(); i += 4)\n'
     '        if (memcmp(&expect[i], got + i, 4)) { if (!bad) { firstX = int((i / 4) % w); firstY = int((i / 4) / w); } ++bad; }\n',
     GP_VERIFY_MIX, 1),
    ('    if (bad) plog(true, "first difference at %d,%d", firstX, firstY);\n    return bad == 0;\n',
     '    if (bad) plog(true, "first difference at %d,%d", firstX, firstY);\n'
     '    if (mixPx) plog(true, "OMNI_GPU_MIX_V1: verify: %zu translucent pixels blended on the GPU: %zu exact, %zu within 1 per channel, %zu beyond",\n'
     '                    mixPx, mixPx - mixNear - mixBad, mixNear, mixBad);\n'
     '    if (mixBad) gmBreak("the verify frame\'s GPU blend differs from the CPU formula by more than 1");\n'
     '    return bad == 0;\n', 1),
    ('    const bool videoNow = g.video.valid && g.optVideo && !g.video.runs.empty();\n',
     '    const bool videoNow = g.video.valid && g.optVideo && (!g.video.runs.empty() || !g.video.mix.empty());   // OMNI_GPU_MIX_V1: spans too\n', 1),
    ('        nlDestroy();   // OMNI_NIGHT_LIGHT_V1: its pipeline and view too\n',
     '        gmDestroy();   // OMNI_GPU_MIX_V1: its pipeline, view and span list\n'
     '        nlDestroy();   // OMNI_NIGHT_LIGHT_V1: its pipeline and view too\n', 1),
    ('    return omni_gpu_present_stage_video_hdr(px, bytes, stride, lx, ly, w, h, runs, runWords, nullptr, 0, 0, release, cookie);\n}\n',
     '    return omni_gpu_present_stage_video_hdr(px, bytes, stride, lx, ly, w, h, runs, runWords, nullptr, 0, 0, release, cookie);\n}\n' + GP_API, 1),
    # host test
    ('static int s_testReadback = 1;\n',
     'static int s_testReadback = 1;\n'
     '// OMNI_GPU_MIX_V1: spans staged with the next omni_gpu_present_test() videos (the console stage\'s v.mix), set-up, counters.\n'
     'static std::vector<uint32_t> s_testMix;\n'
     'extern "C" int omni_gpu_present_test_mix(const uint32_t* spans, size_t words)\n'
     '{\n'
     '    if (spans && words) s_testMix.assign(spans, spans + words); else s_testMix.clear();\n'
     '    if (!g.device && !hostUp()) return 0;\n'
     '    return gmSetUp() ? 1 : 0;\n'
     '}\n'
     'extern "C" void omni_gpu_present_test_mix_stats(uint64_t* frames, uint64_t* pixels, size_t* spansCap, int* broken)\n'
     '{ *frames = gm.frames; *pixels = gm.pixels; *spansCap = gm.spansCap; *broken = gm.broken.load() ? 1 : 0; }\n', 1),
    ('    if (layer && runWords && released) {\n',
     '    if (layer && (runWords || !s_testMix.empty()) && released) {   // OMNI_GPU_MIX_V1: spans alone too\n', 1),
    ('        v.runs.assign(runs, runs + runWords); v.release = hostRelease; v.cookie = released; v.valid = true;\n',
     '        v.runs.assign(runs, runs + runWords); v.release = hostRelease; v.cookie = released; v.valid = true;\n'
     '        v.mix = s_testMix;   // OMNI_GPU_MIX_V1 (host test)\n', 1),
    ('    nlDestroy();   // OMNI_NIGHT_LIGHT_V1 (host test teardown)\n',
     '    gmDestroy();   // OMNI_GPU_MIX_V1 (host test teardown)\n'
     '    nlDestroy();   // OMNI_NIGHT_LIGHT_V1 (host test teardown)\n', 1),
]

# ------------------------------------------------------------------------------------------- OmniHwService.cpp
HW_DECL = r'''// OMNI_GPU_MIX_V1 (tools/apply_gpu_mix.py): the GPU present blends the translucent page pixels of a record-only compose
// (spans staged with the picture). Weak: absent in the big-app and the child engine (and in titles without the pass).
extern "C" int omni_gpu_present_mix_ready(void) __attribute__((weak));
extern "C" int omni_gpu_present_stage_video_mix(const void*, size_t, int, int, int, int, int, const uint32_t*, size_t,
                                                const uint32_t*, size_t, void (*)(void*), void*) __attribute__((weak));
'''

HW_HELPERS = r'''// ---- OMNI_GPU_MIX_V1 (tools/apply_gpu_mix.py) ------------------------------------------------------------------
// With the GPU present active and SDR, a record-only compose no longer copies every translucent page pixel into the
// record (mixPos / mixPage: 8.3M entries for a full-screen dim layer at 4K) and the presenter no longer blends them on the
// CPU for every video frame: the compose leaves the page pixel itself in the canvas (canvas byte order) and records
// (y, x, n) spans; the presenter stages them with the picture (omni_gpu_present_stage_video_mix) and the GPU present
// blends them in its canvas image (omni_gpu_mix.comp, holeBlendPixel's arithmetic). Hole runs are unchanged.
// A refused staging: the presenter turns the live record back into the CPU one from the frame's own pixels (gmMaterialize:
// the GPU never writes the surface, so the page pixels are still there), and composes use the CPU record for 250 ms.
// Kill switch: /data/omni/gpu-mix-off.flag (read once).
std::atomic<int64_t> gmBackoffUntilUs { 0 };
std::atomic<unsigned> gmComposes { 0 }, gmStaged { 0 }, gmRefusals { 0 }, gmMaterialized { 0 };
bool gmChoose()   // shell main thread, at a record-only compose
{
    static const bool off = access("/data/omni/gpu-mix-off.flag", F_OK) == 0;
    if (off || !omni_gpu_present_mix_ready || !omni_gpu_present_stage_video_mix || !gpuPresentOn()) return false;
    if (gpuHdrState() != 0 || !omni_gpu_present_mix_ready()) return false;
    return v7MonoUs() >= gmBackoffUntilUs.load(std::memory_order_relaxed);
}
// Page order (B,G,R,A) <-> canvas order: R and B exchanged on an R,G,B,A canvas (the same operation both ways). d may be s.
__attribute__((target("avx2"))) static void gmSwapSpan(uint8_t* d, const uint8_t* s, size_t n, bool swapRB)
{
    if (!swapRB) { if (d != s) memmove(d, s, n * 4); return; }
    const __m256i m = _mm256_setr_epi8(2,1,0,3, 6,5,4,7, 10,9,8,11, 14,13,12,15, 2,1,0,3, 6,5,4,7, 10,9,8,11, 14,13,12,15);
    size_t i = 0;
    for (; i + 8 <= n; i += 8)
        _mm256_storeu_si256(reinterpret_cast<__m256i*>(d + 4 * i), _mm256_shuffle_epi8(_mm256_loadu_si256(reinterpret_cast<const __m256i*>(s + 4 * i)), m));
    for (; i < n; ++i) { const uint8_t b0 = s[4 * i], b2 = s[4 * i + 2]; d[4 * i + 1] = s[4 * i + 1]; d[4 * i + 3] = s[4 * i + 3]; d[4 * i] = b2; d[4 * i + 2] = b0; }
}
// holeRecordRowOnly for a gpu-mix record: hole runs exactly as there (run + 0 placeholders); a translucent run is one
// (y, x, n) triplet in rec.gmSpans and its page pixels go into the canvas row in canvas order (the shell left
// page-over-background there). Opaque pixels stay. False when the caps (v7MaxRuns triplets, v7MaxMix pixels) are reached.
bool holeRecordRowGpuMix(uint8_t* d, const uint8_t* p, int n, int y, int x0, V7Record& rec, bool swapRB, size_t& pixels)
{
    for (int i = 0; i < n;) {
        const unsigned a = p[4 * i + 3];
        const int kind = a == 0 ? 0 : a == 255 ? 1 : 2;
        const int j = omniAlphaRunEnd(p, i + 1, n, kind);
        if (kind == 0) {
            if (rec.runs.size() + 3 > v7MaxRuns) return false;
            rec.runs.push_back(uint32_t(y)); rec.runs.push_back(uint32_t(x0 + i)); rec.runs.push_back(uint32_t(j - i));
            memset(d + 4 * size_t(i), 0, size_t(j - i) * 4);
        } else if (kind == 2) {
            const size_t len = size_t(j - i);
            if (rec.gmSpans.size() + 3 > v7MaxRuns || pixels + len > v7MaxMix) return false;
            rec.gmSpans.push_back(uint32_t(y)); rec.gmSpans.push_back(uint32_t(x0 + i)); rec.gmSpans.push_back(uint32_t(len));
            gmSwapSpan(d + 4 * size_t(i), p + 4 * size_t(i), len, swapRB);
            pixels += len;
        }
        i = j;
    }
    return true;
}
// A gpu-mix span blended on the CPU in place: c holds the page pixels (canvas order); layerRow: the picture there.
static void gmBlendInPlace(uint8_t* c, const uint8_t* layerRow, size_t n, bool swapRB)
{
    static thread_local std::vector<uint8_t> pg, vr;
    if (pg.size() < n * 4) { pg.resize(n * 4); vr.resize(n * 4); }
    gmSwapSpan(pg.data(), c, n, swapRB);   // -> page order (omniBlendSpanAvx2's page operand)
    omniReadLayer(vr.data(), layerRow, n * 4);
    omniBlendSpanAvx2(c, pg.data(), vr.data(), n, swapRB);
}
// Presenter (under v7ComposeLock), when the GPU present did not take a gpu-mix record's spans: the CPU record (mixPos /
// mixPage / mixSpans) from the frame's own pixels, kept in raster order with any shell pixels already there.
static void gmMaterialize(V7Live& live, const uint8_t* buf, int pitch)
{
    live.gpuMix = false;
    if (live.gmSpans.empty()) return;
    gmMaterialized.fetch_add(1, std::memory_order_relaxed);
    const bool merge = !live.mixPos.empty();
    const uint32_t width = uint32_t(std::max(1, live.width));
    for (size_t k = 0; k + 2 < live.gmSpans.size(); k += 3) {
        const uint32_t y = live.gmSpans[k], x = live.gmSpans[k + 1], n = live.gmSpans[k + 2];
        if (!n || x + n > width) continue;
        const size_t at = live.mixPos.size();
        live.mixSpans.push_back(uint32_t(at)); live.mixSpans.push_back(n);
        live.mixPos.resize(at + n); live.mixPage.resize(at + n);
        const uint32_t first = y * width + x;
        for (uint32_t q = 0; q < n; ++q) live.mixPos[at + q] = first + q;
        gmSwapSpan(reinterpret_cast<uint8_t*>(live.mixPage.data() + at), buf + size_t(y) * size_t(pitch) + size_t(x) * 4, n, live.swapRB);
    }
    live.gmSpans.clear();
    if (!merge) return;
    static thread_local std::vector<std::pair<uint32_t, uint32_t>> all;
    all.clear(); all.reserve(live.mixPos.size());
    for (size_t i = 0; i < live.mixPos.size(); ++i) all.emplace_back(live.mixPos[i], live.mixPage[i]);
    std::sort(all.begin(), all.end());
    live.mixPos.clear(); live.mixPage.clear(); live.mixSpans.clear();
    for (size_t i = 0; i < all.size(); ++i) {
        const uint32_t pos = all[i].first;
        if (i && pos == all[i - 1].first) continue;
        const size_t ns = live.mixSpans.size();
        if (ns && live.mixPos.back() + 1 == pos && pos % width) live.mixSpans[ns - 1]++;
        else { live.mixSpans.push_back(uint32_t(live.mixPos.size())); live.mixSpans.push_back(1); }
        live.mixPos.push_back(pos); live.mixPage.push_back(all[i].second);
    }
}
'''

HW_RECORD_OLD = ('            for (int y = y0; y < y1 && recorded; y++)\n'
                 '                recorded = holeRecordRowOnly(canvas + size_t(y) * canvasPitch, page + size_t(y - pageY) * pagePitch, x1 - x0, y, x0, rec);\n'
                 '            if (!recorded) { rec.runs.clear(); rec.mixPos.clear(); rec.mixPage.clear(); rec.mixSpans.clear(); }   // caps: blend every row below\n')
HW_RECORD_NEW = ('            const bool gpuMix = gmChoose();   // OMNI_GPU_MIX_V1: translucent pixels left to the GPU present\n'
                 '            size_t gmPixels = 0;\n'
                 '            for (int y = y0; y < y1 && recorded; y++)\n'
                 '                recorded = gpuMix\n'
                 '                    ? holeRecordRowGpuMix(canvas + size_t(y) * canvasPitch, page + size_t(y - pageY) * pagePitch, x1 - x0, y, x0, rec, swapRB, gmPixels)\n'
                 '                    : holeRecordRowOnly(canvas + size_t(y) * canvasPitch, page + size_t(y - pageY) * pagePitch, x1 - x0, y, x0, rec);\n'
                 '            if (!recorded) { rec.runs.clear(); rec.mixPos.clear(); rec.mixPage.clear(); rec.mixSpans.clear(); rec.gmSpans.clear(); }   // caps: blend every row below\n'
                 '            rec.gpuMix = recorded && gpuMix;   // OMNI_GPU_MIX_V1\n'
                 '            if (rec.gpuMix) {\n'
                 '                const unsigned c = gmComposes.fetch_add(1, std::memory_order_relaxed) + 1;\n'
                 '                if (c == 1 || c % 1800 == 0)\n'
                 '                    holeNote("OMNI_GPU_MIX_V1: %u composes left translucent pixels to the GPU present (this one %zu spans, %zu pixels); staged %u, refused %u, back on the CPU %u",\n'
                 '                             c, rec.gmSpans.size() / 3, gmPixels, gmStaged.load(std::memory_order_relaxed), gmRefusals.load(std::memory_order_relaxed), gmMaterialized.load(std::memory_order_relaxed));\n'
                 '            }\n')

HW_FILL_OLD = '    pbRecordFilled.fetch_add(1, std::memory_order_relaxed);\n}\n'
HW_FILL_NEW = ('    for (size_t k = 0; k + 2 < rec.gmSpans.size(); k += 3) {   // OMNI_GPU_MIX_V1: the page pixels the canvas holds there, over the picture\n'
               '        const uint32_t y = rec.gmSpans[k], x = rec.gmSpans[k + 1], len = rec.gmSpans[k + 2];\n'
               '        gmBlendInPlace(canvas + size_t(y) * size_t(pitch) + size_t(x) * 4, px + size_t(int(y) - rec.ly) * stride + size_t(int(x) - rec.lx) * 4, len, rec.swapRB);\n'
               '    }\n'
               '    pbRecordFilled.fetch_add(1, std::memory_order_relaxed);\n}\n')

HW_STAGE_OLD = ('    if (!gpuStageHere || !gpuPresentOn() || !omni_gpu_present_stage_video || live.runs.empty() || !now) return false;\n')
HW_STAGE_NEW = ('    if (!gpuStageHere || !gpuPresentOn() || !omni_gpu_present_stage_video || (live.runs.empty() && !live.gpuMix) || !now) return false;   // OMNI_GPU_MIX_V1: spans alone too\n')
HW_STAGE2_OLD = '    const bool pq = now->gpuHdrValid;\n'
HW_STAGE2_NEW = ('    const bool pq = now->gpuHdrValid;\n'
                 '    if (live.gpuMix) {   // OMNI_GPU_MIX_V1: runs and translucent spans together (SDR present only)\n'
                 '        if (omni_gpu_present_stage_video_mix && omni_gpu_present_stage_video_mix(px, bytes, now->stride, live.lx, live.ly, now->w, now->h,\n'
                 '                live.runs.data(), live.runs.size(), live.gmSpans.data(), live.gmSpans.size(), gpuUnpin, const_cast<HoleLayer*>(now))) {\n'
                 '            gmStaged.fetch_add(1, std::memory_order_relaxed);\n'
                 '            return true;\n'
                 '        }\n'
                 '        gmBackoffUntilUs.store(v7MonoUs() + 250000, std::memory_order_relaxed);   // the next composes: the CPU record\n'
                 '        if (gmRefusals.fetch_add(1, std::memory_order_relaxed) < 8) holeNote("OMNI_GPU_MIX_V1: the GPU present refused the translucent spans: this frame is blended on the CPU");\n'
                 '        gpuUnpin(const_cast<HoleLayer*>(now));\n'
                 '        return false;\n'
                 '    }\n')

HW_WRITE_OLD = ('    if (gpuStageVideo(live, now)) { for (size_t k = 2; k < live.runs.size(); k += 3) written += live.runs[k]; }   // OMNI_GPU_PRESENT_V1\n'
                '    else\n')
HW_WRITE_NEW = ('    const bool onGpu = gpuStageVideo(live, now);   // OMNI_GPU_PRESENT_V1\n'
                '    // OMNI_GPU_MIX_V1: spans the GPU did not take: the CPU record from this frame\'s page pixels (every caller passes v7Live,\n'
                '    // under v7ComposeLock), then the CPU path below as before\n'
                '    if (!onGpu && live.gpuMix) gmMaterialize(const_cast<V7Live&>(live), buf, pitch);\n'
                '    if (onGpu) { for (size_t k = 2; k < live.runs.size(); k += 3) written += live.runs[k]; }   // OMNI_GPU_PRESENT_V1\n'
                '    else\n')

HW_REFLIP_OLD = '    gpuStageHere = true; const bool onGpu = gpuStageVideo(live, now); gpuStageHere = false;   // OMNI_GPU_PRESENT_V1\n'
HW_REFLIP_NEW = (HW_REFLIP_OLD +
                 '    if (!onGpu && live.gpuMix) gmMaterialize(live, frame, pitch);   // OMNI_GPU_MIX_V1: the CPU blends this frame\'s spans\n')

HW_EDITS = [
    ('static int gpuHdrState() { return omni_gpu_present_hdr_state ? omni_gpu_present_hdr_state() : 0; }\n',
     'static int gpuHdrState() { return omni_gpu_present_hdr_state ? omni_gpu_present_hdr_state() : 0; }\n' + HW_DECL, 1),
    ('    // OMNI_PERF_B_V1: record only. The canvas holds 0 (B,G,R,A all zero) at every recorded pixel (hole runs and\n',
     '    // OMNI_GPU_MIX_V1: a gpu-mix record (record-only, GPU present blending): the translucent page pixels as (y, x, n)\n'
     '    // spans instead of mixPos / mixPage; the canvas holds the page pixel itself there (canvas byte order), not 0.\n'
     '    std::vector<uint32_t> gmSpans; bool gpuMix = false;\n'
     '    // OMNI_PERF_B_V1: record only. The canvas holds 0 (B,G,R,A all zero) at every recorded pixel (hole runs and\n', 1),
    ('    bool recordOnly = false;          // OMNI_PERF_B_V1: the canvas this describes holds no video pixels\n',
     '    bool recordOnly = false;          // OMNI_PERF_B_V1: the canvas this describes holds no video pixels\n'
     '    std::vector<uint32_t> gmSpans; bool gpuMix = false;   // OMNI_GPU_MIX_V1: spans the GPU present blends (the canvas holds the page pixels there)\n', 1),
    ('    uint32_t out; memcpy(&out, o, 4);\n    return out;\n}\n}\n\nvoid holePunchCompose(',
     '    uint32_t out; memcpy(&out, o, 4);\n    return out;\n}\n' + HW_HELPERS + '}\n\nvoid holePunchCompose(', 1),
    ('v7Record.mixSpans.clear(); v7Record.recordOnly = false; }',
     'v7Record.mixSpans.clear(); v7Record.recordOnly = false; v7Record.gmSpans.clear(); v7Record.gpuMix = false; }', 1),
    (HW_RECORD_OLD, HW_RECORD_NEW, 1),
    (HW_FILL_OLD, HW_FILL_NEW, 1),
    ('    live.valid = !live.runs.empty() || !live.mixPos.empty();\n    live.recordOnly = rec.recordOnly;   // OMNI_PERF_B_V1\n',
     '    live.gmSpans.assign(rec.gmSpans.begin(), rec.gmSpans.end()); live.gpuMix = rec.gpuMix && !live.gmSpans.empty();   // OMNI_GPU_MIX_V1\n'
     '    live.valid = !live.runs.empty() || !live.mixPos.empty() || live.gpuMix;\n    live.recordOnly = rec.recordOnly;   // OMNI_PERF_B_V1\n', 2),
    (HW_STAGE_OLD, HW_STAGE_NEW, 1),
    (HW_STAGE2_OLD, HW_STAGE2_NEW, 1),
    (HW_WRITE_OLD, HW_WRITE_NEW, 1),
    (HW_REFLIP_OLD, HW_REFLIP_NEW, 1),
    ('    if (gpuPresentOn()) return false;   // OMNI_GPU_PRESENT_V1: SDL\'s tiled buffers are not shown; the frame goes to the GPU\n',
     '    if (gpuPresentOn()) return false;   // OMNI_GPU_PRESENT_V1: SDL\'s tiled buffers are not shown; the frame goes to the GPU\n'
     '    if (live.gpuMix) return false;   // OMNI_GPU_MIX_V1: no page values in mixPage: v8WriteLive turns it into the CPU record first\n', 1),
]


def build_shader():
    """omni_gpu_mix.comp -> .spv (glslangValidator, vulkan1.1) -> spirv-val -> src/OmniGpuMixShader.h. Returns notes."""
    notes = []
    if not comp.exists() or comp.read_text('utf-8') != SHADER:
        comp.write_text(SHADER, 'utf-8'); notes.append('shader written')
    tmp_spv = spv.with_name(spv.name + '.tmp')
    subprocess.run(['glslangValidator', '-V', '--target-env', 'vulkan1.1', '-o', str(tmp_spv), str(comp)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    subprocess.run(['spirv-val', '--target-env', 'vulkan1.1', str(tmp_spv)], check=True)
    if not spv.exists() or spv.read_bytes() != tmp_spv.read_bytes():
        shutil.move(str(tmp_spv), str(spv)); notes.append('spv regenerated')
    else:
        tmp_spv.unlink()
    tmp = hdr.with_name(hdr.name + '.tmp')
    subprocess.run([sys.executable, str(tool), str(spv), str(tmp), 'kOmniGpuMixSpv', 'omni_gpu_mix.comp'], check=True)
    text = tmp.read_text('utf-8').replace('#pragma once\n', '// OMNI_GPU_MIX_V1: SPIR-V of omni_gpu_mix.comp (the GPU blend of translucent page pixels over the video).\n#pragma once\n', 1)
    tmp.unlink()
    if not hdr.exists() or hdr.read_text('utf-8') != text:
        hdr.write_text(text, 'utf-8'); notes.append('header regenerated')
    return notes


def main():
    for p in (present, hw, tool, comp.parent):
        if not p.exists():
            sys.exit('missing %s' % p)
    gp, gnl = load(present)
    hs, hnl = load(hw)
    if MARK not in gp and 'OMNI_NIGHT_LIGHT_V1' not in gp:
        sys.exit('OmniGpuPresent.cpp: OMNI_NIGHT_LIGHT_V1 missing (the mix pass shares its canvas STORAGE switch)')
    if MARK not in hs and 'OMNI_PERF_B_V1' not in hs:
        sys.exit('OmniHwService.cpp: OMNI_PERF_B_V1 missing (gpu-mix is a record-only compose)')
    # every anchor of both files is checked before anything is written
    new_gp = None if MARK in gp else apply_edits(gp, GP_EDITS, present.name)
    new_hs = None if MARK in hs else apply_edits(hs, HW_EDITS, hw.name)
    done = []
    notes = build_shader()
    if new_gp is not None:
        save(present, new_gp, gnl); done.append('OmniGpuPresent.cpp')
    if new_hs is not None:
        save(hw, new_hs, hnl); done.append('OmniHwService.cpp')
    done += r2_hdr_auto()
    done += v2_partial()
    done += r3_hdr_output()
    done += d1_diag()
    if done or notes:
        print('applied %s (%s)' % (MARK, ', '.join(done + notes)))
    else:
        print('already ' + MARK + ' + R2 + V2 (OmniGpuPresent.cpp, OmniHwService.cpp, shader and header current)')


# OMNI_GPU_MIX_V1_R2 (2026-11-17): V1 used the GPU mix only with HDR state 0 (SDR only). On an HDR TV with Omni's HDR
# setting on Auto (the owner's console: "HDR: armed"), the state is 1 (armed, SDR output now), so the mix never ran
# (g2 overlay bench: CPU re-flip 4.3-8.7 ms, page-frame accept 64-75 ms, no OMNI_GPU_MIX line). The pass runs on the
# SDR canvas before the SDR -> PQ pass, so state 1 is plain SDR output; only state 2 (HDR10 output now) keeps the CPU
# blend (the refusal there falls back cleanly, as V1 documents).
R2_EDITS = [
    ('OmniGpuPresent.cpp',
     '&& !gm.broken.load(std::memory_order_acquire) && g.hdrState.load(std::memory_order_acquire) == 0 ? 1 : 0;',
     '&& !gm.broken.load(std::memory_order_acquire) && g.hdrState.load(std::memory_order_acquire) != 2 ? 1 : 0;   // OMNI_GPU_MIX_V1_R2: HDR Auto too'),
    ('OmniGpuPresent.cpp',
     'else if (g.hdr || g.hdrState.load(std::memory_order_acquire) != 0) why = "HDR output is armed or on";',
     'else if (g.hdr || g.hdrState.load(std::memory_order_acquire) == 2) why = "HDR10 output is on";   // OMNI_GPU_MIX_V1_R2'),
    ('OmniHwService.cpp',
     'if (gpuHdrState() != 0 || !omni_gpu_present_mix_ready()) return false;',
     'if (gpuHdrState() == 2 || !omni_gpu_present_mix_ready()) return false;   // OMNI_GPU_MIX_V1_R2: HDR Auto (armed, SDR now) too'),
]


def r2_hdr_auto():
    out = []
    for name, path in (('OmniGpuPresent.cpp', present), ('OmniHwService.cpp', hw)):
        t, nl = load(path)
        if 'OMNI_GPU_MIX_V1_R2' in t or 'OMNI_GPU_MIX_V1_R3' in t:   # R3 replaces R2's lines
            continue
        for fname, old, new in R2_EDITS:
            if fname != name:
                continue
            if t.count(old) != 1:
                sys.exit('%s: R2 anchor found %d times: %r' % (name, t.count(old), old[:80]))
            t = t.replace(old, new, 1)
        save(path, t, nl)
        out.append(name + ' R2')
    return out


# OMNI_GPU_MIX_V2 (2026-11-17): V1 (and R2) never engaged on the console: holePunchCompose takes the record-only path only
# for a layer covering the WHOLE canvas, and a page-fullscreen video sits under Omni's top bar ("rect 3840x1920 at
# 0,120", layer 3840x2160), so every real case went through the blending V7 compose (holeBlendRowRecord on the main
# thread, CPU re-flips: page-frame accept 64-75 ms, re-flip 4.3-8.8 ms for 8.3M translucent pixels). V2: when the
# GPU mix is chosen (gmChoose: GPU present active, HDR10 output not on, no refusal in the last 250 ms, no
# gpu-mix-off.flag), a paced video that covers only part of the canvas (any lx, ly; the layer clipped to the page area
# and the canvas, possibly larger than its visible part) takes the record-only path too. Everything downstream already
# works in layer coordinates (live.lx / live.ly, live.w / live.h = the layer's size, the GPU's clip to the layer):
# v8WriteLive's runs, omniWriteMixSpans after gmMaterialize, holeFillRecordOnly, the GPU stage and the present's clip.
# The row recorder now gets row pointers offset by x0 / x0 - pageX (identical for a full-canvas layer: both 0).
# Unchanged: the full-canvas condition for the CPU record-only path (gpu-mix not chosen: the blending compose, as
# before), pbOwnsVideo (still full-canvas only), v139Direct (never takes a gpu-mix record).
MARK2 = 'OMNI_GPU_MIX_V2'
V2_OLD = (
    '        const bool recordOnly = v1On() && v8On() && v8BeforeFlipSeen.load(std::memory_order_relaxed) && pacing\n'
    '            && lx == 0 && ly == 0 && x0 == 0 && y0 == 0 && x1 == canvasWidth && y1 == canvasHeight\n'
    '            && layer->w == canvasWidth && layer->h == canvasHeight && int64_t(canvasWidth) * canvasHeight > int64_t(2560) * 1440;\n'
    '        bool recorded = false;\n'
    '        if (recordOnly) {\n'
    '            recorded = true;\n'
    '            const bool gpuMix = gmChoose();   // OMNI_GPU_MIX_V1: translucent pixels left to the GPU present\n'
    '            size_t gmPixels = 0;\n'
    '            for (int y = y0; y < y1 && recorded; y++)\n'
    '                recorded = gpuMix\n'
    '                    ? holeRecordRowGpuMix(canvas + size_t(y) * canvasPitch, page + size_t(y - pageY) * pagePitch, x1 - x0, y, x0, rec, swapRB, gmPixels)\n'
    '                    : holeRecordRowOnly(canvas + size_t(y) * canvasPitch, page + size_t(y - pageY) * pagePitch, x1 - x0, y, x0, rec);\n')
V2_NEW = (
    '        const bool recordBase = v1On() && v8On() && v8BeforeFlipSeen.load(std::memory_order_relaxed) && pacing\n'
    '            && int64_t(canvasWidth) * canvasHeight > int64_t(2560) * 1440;\n'
    '        const bool fullCanvas = lx == 0 && ly == 0 && x0 == 0 && y0 == 0 && x1 == canvasWidth && y1 == canvasHeight\n'
    '            && layer->w == canvasWidth && layer->h == canvasHeight;\n'
    '        // OMNI_GPU_MIX_V2: a paced video covering only part of the canvas (under the top bar: layer at 0,120) is recorded\n'
    '        // too when the GPU present blends its translucent pixels (the presenter writes runs / stages spans in layer coordinates)\n'
    '        const bool partialGm = recordBase && !fullCanvas && x1 > x0 && y1 > y0 && int64_t(layer->w) * layer->h > int64_t(2560) * 1440 && gmChoose();\n'
    '        const bool recordOnly = recordBase && (fullCanvas || partialGm);\n'
    '        bool recorded = false;\n'
    '        if (recordOnly) {\n'
    '            recorded = true;\n'
    '            const bool gpuMix = partialGm || gmChoose();   // OMNI_GPU_MIX_V1: translucent pixels left to the GPU present\n'
    '            size_t gmPixels = 0;\n'
    '            for (int y = y0; y < y1 && recorded; y++) {   // OMNI_GPU_MIX_V2: rows from column x0 (0 for a full-canvas layer)\n'
    '                uint8_t* const cr = canvas + size_t(y) * canvasPitch + size_t(x0) * 4;\n'
    '                const uint8_t* const pr = page + size_t(y - pageY) * pagePitch + size_t(x0 - pageX) * 4;\n'
    '                recorded = gpuMix ? holeRecordRowGpuMix(cr, pr, x1 - x0, y, x0, rec, swapRB, gmPixels) : holeRecordRowOnly(cr, pr, x1 - x0, y, x0, rec);\n'
    '            }\n')


def v2_partial():
    t, nl = load(hw)
    if MARK2 in t:
        return []
    if t.count(V2_OLD) != 1:
        sys.exit('OmniHwService.cpp: V2 anchor found %d times: %r' % (t.count(V2_OLD), V2_OLD[:90]))
    save(hw, t.replace(V2_OLD, V2_NEW, 1), nl)
    return ['OmniHwService.cpp V2']



# OMNI_GPU_MIX_V1_R3 (2026-11-17): the owner's HDR setting is On, so the GPU present runs HDR10 output all the time
# (state 2: "OMNI_HDR_PRESENT10_V1 10 s (HDR output)"), and R2 still refused the mix there (g4 overlay bench: no mix,
# accept 64-73 ms). The mix pass runs on the SDR canvas BEFORE the SDR -> PQ pass, so for an SDR picture the result is
# exactly what the CPU blend gives (SDR mix, then the whole canvas to PQ). Only HDR pictures (a PQ layer:
# hdrValid / gpuHdrValid) keep the CPU path, decided at the compose; the present no longer refuses on the HDR state.
R3_EDITS = [
    ('OmniGpuPresent.cpp',
     '&& !gm.broken.load(std::memory_order_acquire) && g.hdrState.load(std::memory_order_acquire) != 2 ? 1 : 0;   // OMNI_GPU_MIX_V1_R2: HDR Auto too',
     '&& !gm.broken.load(std::memory_order_acquire) ? 1 : 0;   // OMNI_GPU_MIX_V1_R3: any HDR state (HDR pictures are excluded at the compose)'),
    ('OmniGpuPresent.cpp',
     '    else if (g.hdr || g.hdrState.load(std::memory_order_acquire) == 2) why = "HDR10 output is on";   // OMNI_GPU_MIX_V1_R2\n',
     '    // OMNI_GPU_MIX_V1_R3: no HDR refusal here (the pass runs on the SDR canvas before the SDR -> PQ pass)\n'),
    ('OmniHwService.cpp',
     '    if (gpuHdrState() == 2 || !omni_gpu_present_mix_ready()) return false;   // OMNI_GPU_MIX_V1_R2: HDR Auto (armed, SDR now) too',
     '    if (!omni_gpu_present_mix_ready()) return false;   // OMNI_GPU_MIX_V1_R3: any HDR state; HDR pictures excluded at the call sites'),
    ('OmniHwService.cpp',
     '&& int64_t(layer->w) * layer->h > int64_t(2560) * 1440 && gmChoose();',
     '&& int64_t(layer->w) * layer->h > int64_t(2560) * 1440 && !layer->hdrValid && !layer->gpuHdrValid && gmChoose();   // OMNI_GPU_MIX_V1_R3: SDR pictures only'),
    ('OmniHwService.cpp',
     'const bool gpuMix = partialGm || gmChoose();',
     'const bool gpuMix = partialGm || (!layer->hdrValid && !layer->gpuHdrValid && gmChoose());   // OMNI_GPU_MIX_V1_R3: SDR pictures only'),
]


def r3_hdr_output():
    out = []
    for name, path in (('OmniGpuPresent.cpp', present), ('OmniHwService.cpp', hw)):
        t, nl = load(path)
        if 'OMNI_GPU_MIX_V1_R3' in t:
            continue
        for fname, old, new in R3_EDITS:
            if fname != name:
                continue
            if t.count(old) != 1:
                sys.exit('%s: R3 anchor found %d times: %r' % (name, t.count(old), old[:80]))
            t = t.replace(old, new, 1)
        save(path, t, nl)
        out.append(name + ' R3')
    return out


# OMNI_GPU_MIX_D1 (2026-11-17): g2/g4/g5 never used the GPU mix on the console and no refusal was logged, so the compose
# never chose it. One line every 5 s at a V7 compose with every input of that decision, to see which one is false.
D1_ANCHOR = '        const bool recordOnly = recordBase && (fullCanvas || partialGm);\n'
D1_CODE = (
    '        { static int64_t gmDiagAt = 0; const int64_t gmNowUs = v7MonoUs();   // OMNI_GPU_MIX_D1: why the GPU mix is (not) used, every 5 s\n'
    '          if (gmNowUs - gmDiagAt >= 5000000) { gmDiagAt = gmNowUs;\n'
    '            holeNote("gpu mix check: v1=%d v8=%d beforeFlip=%d pacing=%d canvas=%dx%d layer=%dx%d at %d,%d vis=%d,%d-%d,%d full=%d hdrPx=%d/%d '
    'gpuPresent=%d mixReady=%d recordBase=%d partialGm=%d recordOnly=%d", int(v1On()), int(v8On()), int(v8BeforeFlipSeen.load(std::memory_order_relaxed)), '
    'int(pacing), canvasWidth, canvasHeight, layer->w, layer->h, lx, ly, x0, y0, x1, y1, int(fullCanvas), int(layer->hdrValid), int(layer->gpuHdrValid), '
    'int(gpuPresentOn()), int(omni_gpu_present_mix_ready && omni_gpu_present_mix_ready()), int(recordBase), int(partialGm), int(recordOnly)); } }\n')


def d1_diag():
    t, nl = load(hw)
    if 'OMNI_GPU_MIX_D1' in t:
        return []
    if t.count(D1_ANCHOR) != 1:
        sys.exit('OmniHwService.cpp: D1 anchor found %d times' % t.count(D1_ANCHOR))
    save(hw, t.replace(D1_ANCHOR, D1_ANCHOR + D1_CODE, 1), nl)
    return ['OmniHwService.cpp D1']

main()
