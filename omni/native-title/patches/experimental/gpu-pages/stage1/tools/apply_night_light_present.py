#!/usr/bin/env python3
"""OMNI_NIGHT_LIGHT_V1, title GPU present side: Night light's warm tint as one compute pass over the composed canvas.

Patches OmniGpuPresent.cpp (the copy prep_launch.py put in the title workspace's src/, AFTER apply_zerocopy_present.py:
the zcRecord call is an anchor) and copies OmniNightLightShader.h (SPIR-V of stage1/src-title/omni_night_light.comp)
next to it. In the rc6 title recipe (build-omni-gpupages-rc6-title.sh) that is "$NE/src" = the eboot workspace
/home/builder/ogp-ls1b-ews/src (bind-mounted at outputs/omni-gpupages-ls1b-eboot-bind), i.e. one more line right after
the apply_zerocopy_present.py step:
    python3 "$S1/tools/apply_night_light_present.py" "$NE/src" "$S1/src-title"
The engine tree side (settings, quick toggle, schedule, fade) is apply_night_light.py.

What it adds
  - omni_gpu_present_night(const float* m): the shell's row-major 3x3 over the canvas's stored (gamma-encoded) RGB;
    nullptr = off. omni_gpu_present_night_ready(): 1 while the GPU present is active and the pass has not failed.
  - nlRecord (in recordCompose right after zcRecord, before the canvas becomes a transfer source): while a matrix is
    set, one dispatch of omni_night_light.comp over the whole canvas, in place (TRANSFER_DST -> GENERAL -> TRANSFER_DST).
    So the page (CPU or zero-copy), the shell's panels/bars/pointer AND the GPU hole-punch's video runs are tinted; in
    HDR10 output the canvas is tinted before the PQ pass (UI and page), but the PQ video runs (V4 copies / P10 dispatch)
    are written after it and stay untinted. Read-back (verify) frames are not tinted (the differential check stays exact).
  - Off costs nothing: no pass, no pipeline (made on the first tinted frame), and the canvas keeps its usage. The first
    tinted frame turns on STORAGE usage for the canvas (already there when HDR is armed): ensureCanvas remakes it once
    at the next present (that one frame is shown untinted).
  - Needs the R8G8B8A8_UNORM canvas with storage support (an sRGB swapchain's canvas: the pass stays off, logged).
  - teardownLocked destroys its objects before the device (as zcDestroy).
r2 (OMNI_NIGHT_LIGHT_V1_R2): nl.broken became std::atomic<bool>; a file with r1 is upgraded in place (one line pair).
Anchors (each once; MARK makes it idempotent, REV the r2 upgrade): the OmniZcPageShader.h include; "bool hdrEnsure(uint32_t w, uint32_t h);"
(the state block goes before it); ensureCanvas's early return, its "V2 HDR: the view goes first" line and its usage line;
the zcRecord call in recordCompose; the zero-copy shell API comment (the night API goes before it); zcDestroy() in
teardownLocked; the layer-cache clear + hdrDestroy() of the host test's teardown.
Host test: tools/test_night_light_present.cpp (lavapipe, OMNI_GPU_PRESENT_HOST_TEST).
usage: apply_night_light_present.py <src dir holding OmniGpuPresent.cpp> <stage1/src-title>"""
import shutil, sys
from pathlib import Path

MARK = 'OMNI_NIGHT_LIGHT_V1'
REV = 'OMNI_NIGHT_LIGHT_V1_R2'   # r2: nl.broken is atomic (the shell thread reads it in omni_gpu_present_night_ready)
src, s1 = Path(sys.argv[1]), Path(sys.argv[2])
p = src / 'OmniGpuPresent.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if raw.count('\r\n') * 2 > raw.count('\n') else '\n'
t = raw.replace('\r\n', '\n') if nl == '\r\n' else raw
if 'OMNI_GPUPAGES_ZEROCOPY_V1' not in t:
    sys.exit('OmniGpuPresent.cpp: OMNI_GPUPAGES_ZEROCOPY_V1 missing: apply_zerocopy_present.py first')
hdr = (s1 / 'OmniNightLightShader.h').read_bytes()

# r2 (REV): `broken` is std::atomic<bool>: nlBreak sets it on the present thread, omni_gpu_present_night_ready() reads
# it on the shell thread without nl.lock. A file patched by r1 (the persistent $NE/src of the rc6 recipe, re-run every
# build) gets only this edit; a fresh apply writes it with STATE. Both give the same bytes.
NL_FLAGS_R1 = ('    float m[9] = { 1, 0, 0, 0, 1, 0, 0, 0, 1 }; bool want = false;\n'
               '    bool tried = false, ready = false, broken = false;\n')
NL_FLAGS_R2 = ('    float m[9] = { 1, 0, 0, 0, 1, 0, 0, 0, 1 }; bool want = false;\n'
               '    bool tried = false, ready = false;\n'
               '    std::atomic<bool> broken { false };   // ' + REV + ': set by nlBreak (present), read by omni_gpu_present_night_ready (shell)\n')


def save(text):
    p.write_bytes((text.replace('\n', '\r\n') if nl == '\r\n' else text).encode('utf-8'))


def shader_header():
    if (src / 'OmniNightLightShader.h').exists() and (src / 'OmniNightLightShader.h').read_bytes() == hdr:
        return ''
    shutil.copyfile(s1 / 'OmniNightLightShader.h', src / 'OmniNightLightShader.h')
    return ' (shader header refreshed)'


if MARK in t:
    if REV in t:
        print('already OmniGpuPresent.cpp' + shader_header()); sys.exit(0)
    if t.count(NL_FLAGS_R1) != 1:
        sys.exit('OmniGpuPresent.cpp: r2 anchor found %d times: %r' % (t.count(NL_FLAGS_R1), NL_FLAGS_R1[:90]))
    save(t.replace(NL_FLAGS_R1, NL_FLAGS_R2, 1))
    print('upgraded OmniGpuPresent.cpp to ' + REV + shader_header()); sys.exit(0)

STATE = r'''// ---------------------------------------------------------------- OMNI_NIGHT_LIGHT_V1
// Night light (tools/apply_night_light_present.py): a warm tint over the composed canvas, one compute pass in place.
// The shell (OmniNightLightShell.h) sets the matrix and fades it; nothing is recorded while it is off.
struct NlPush { float r0[4], r1[4], r2[4]; int32_t w, h, pad0, pad1; };
static_assert(sizeof(NlPush) == 64, "push constants of omni_night_light.comp");
struct NlState {
    std::mutex lock;                   // the shell thread sets the matrix; the present records it
''' + NL_FLAGS_R2 + r'''    bool storage = false;              // canvases are made with STORAGE usage from now on (set by nlSetUp)
    bool canvasStorage = false;        // the current canvas has it
    uint64_t canvasGen = 0, viewGen = 0;
    VkShaderModule shader = VK_NULL_HANDLE; VkDescriptorSetLayout setLayout = VK_NULL_HANDLE; VkPipelineLayout layout = VK_NULL_HANDLE;
    VkPipeline pipe = VK_NULL_HANDLE; VkDescriptorPool pool = VK_NULL_HANDLE; VkDescriptorSet set = VK_NULL_HANDLE;
    VkImageView view = VK_NULL_HANDLE;
    uint64_t frames = 0, skipped = 0; double lastLog = 0;
} nl;
bool loadHdrFns();
void nlBreak(const char* why)
{
    if (!nl.broken) plog(true, "night light OFF: %s (the canvas is shown untinted)", why);
    nl.broken = true;
}
void nlDropView()
{
    if (nl.view) g.vk.vkDestroyImageView(g.device, nl.view, nullptr);
    nl.view = VK_NULL_HANDLE; nl.viewGen = 0;
}
bool nlSetUp()   // once, on the first tinted frame (caller holds g.lock)
{
    if (nl.tried) return nl.ready;
    nl.tried = true;
    if (!g.device || !loadHdrFns()) { nlBreak("device entry points missing"); return false; }
    if (g.canvasFormat != VK_FORMAT_R8G8B8A8_UNORM) { nlBreak("the canvas is not R8G8B8A8_UNORM"); return false; }
    VkFormatProperties fp {}; g.vk.vkGetPhysicalDeviceFormatProperties(g.physical, VK_FORMAT_R8G8B8A8_UNORM, &fp);
    if (!(fp.optimalTilingFeatures & VK_FORMAT_FEATURE_STORAGE_IMAGE_BIT)) { nlBreak("no storage-image support for the canvas format"); return false; }
    VkShaderModuleCreateInfo smi { VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO }; smi.codeSize = sizeof kOmniNightLightSpv; smi.pCode = kOmniNightLightSpv;
    if (g.vk.vkCreateShaderModule(g.device, &smi, nullptr, &nl.shader) != VK_SUCCESS) { nl.shader = VK_NULL_HANDLE; nlBreak("shader module"); return false; }
    VkDescriptorSetLayoutBinding b {};
    b.binding = 0; b.descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE; b.descriptorCount = 1; b.stageFlags = VK_SHADER_STAGE_COMPUTE_BIT;
    VkDescriptorSetLayoutCreateInfo dl { VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO }; dl.bindingCount = 1; dl.pBindings = &b;
    if (g.vk.vkCreateDescriptorSetLayout(g.device, &dl, nullptr, &nl.setLayout) != VK_SUCCESS) { nl.setLayout = VK_NULL_HANDLE; nlBreak("set layout"); return false; }
    VkPushConstantRange range { VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof(NlPush) };
    VkPipelineLayoutCreateInfo pl { VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO }; pl.setLayoutCount = 1; pl.pSetLayouts = &nl.setLayout; pl.pushConstantRangeCount = 1; pl.pPushConstantRanges = &range;
    if (g.vk.vkCreatePipelineLayout(g.device, &pl, nullptr, &nl.layout) != VK_SUCCESS) { nl.layout = VK_NULL_HANDLE; nlBreak("pipeline layout"); return false; }
    VkComputePipelineCreateInfo cp { VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO };
    cp.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO; cp.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT; cp.stage.module = nl.shader; cp.stage.pName = "main"; cp.layout = nl.layout;
    if (g.vk.vkCreateComputePipelines(g.device, VK_NULL_HANDLE, 1, &cp, nullptr, &nl.pipe) != VK_SUCCESS) { nl.pipe = VK_NULL_HANDLE; nlBreak("compute pipeline"); return false; }
    VkDescriptorPoolSize ps { VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, 1 };
    VkDescriptorPoolCreateInfo dp { VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO }; dp.maxSets = 1; dp.poolSizeCount = 1; dp.pPoolSizes = &ps;
    if (g.vk.vkCreateDescriptorPool(g.device, &dp, nullptr, &nl.pool) != VK_SUCCESS) { nl.pool = VK_NULL_HANDLE; nlBreak("descriptor pool"); return false; }
    VkDescriptorSetAllocateInfo da { VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO }; da.descriptorPool = nl.pool; da.descriptorSetCount = 1; da.pSetLayouts = &nl.setLayout;
    if (g.vk.vkAllocateDescriptorSets(g.device, &da, &nl.set) != VK_SUCCESS) { nl.set = VK_NULL_HANDLE; nlBreak("descriptor set"); return false; }
    nl.ready = true;
    nl.storage = true;   // ensureCanvas: the next canvas (or this one, remade once) can be a storage image
    plog(true, "night light: armed (one compute pass over the canvas while a tint is set; canvas STORAGE usage %s)",
         nl.canvasStorage ? "already on" : "from the next present");
    return true;
}
// In recordCompose, after the canvas is complete (frame, video runs, zero-copy page) and still TRANSFER_DST.
void nlRecord(int w, int h, bool wantReadback)
{
    float m[9]; bool want;
    { std::lock_guard<std::mutex> l(nl.lock); want = nl.want; memcpy(m, nl.m, sizeof m); }
    if (!want || nl.broken) return;                    // Off: nothing recorded
    if (wantReadback) { nl.skipped++; return; }        // the differential check compares with the CPU frame
    if (!nlSetUp()) return;
    if (!nl.canvasStorage || !g.canvas.image) { nl.skipped++; return; }   // remade with STORAGE usage at the next present
    if (!nl.view || nl.viewGen != nl.canvasGen) {
        nlDropView();
        VkImageViewCreateInfo vi { VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO }; vi.image = g.canvas.image; vi.viewType = VK_IMAGE_VIEW_TYPE_2D;
        vi.format = VK_FORMAT_R8G8B8A8_UNORM; vi.subresourceRange = { VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1 };
        if (g.vk.vkCreateImageView(g.device, &vi, nullptr, &nl.view) != VK_SUCCESS) { nl.view = VK_NULL_HANDLE; nlBreak("canvas storage view"); return; }
        nl.viewGen = nl.canvasGen;
        VkDescriptorImageInfo ii { VK_NULL_HANDLE, nl.view, VK_IMAGE_LAYOUT_GENERAL };
        VkWriteDescriptorSet wr { VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET };
        wr.dstSet = nl.set; wr.dstBinding = 0; wr.descriptorCount = 1; wr.descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_IMAGE; wr.pImageInfo = &ii;
        g.vk.vkUpdateDescriptorSets(g.device, 1, &wr, 0, nullptr);   // the previous present's fence has signalled
    }
    barrier(g.canvas.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_GENERAL, VK_ACCESS_TRANSFER_WRITE_BIT | VK_ACCESS_SHADER_WRITE_BIT,
            VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT | VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT);
    g.vk.vkCmdBindPipeline(g.cmd, VK_PIPELINE_BIND_POINT_COMPUTE, nl.pipe);
    g.vk.vkCmdBindDescriptorSets(g.cmd, VK_PIPELINE_BIND_POINT_COMPUTE, nl.layout, 0, 1, &nl.set, 0, nullptr);
    NlPush pc { { m[0], m[1], m[2], 0 }, { m[3], m[4], m[5], 0 }, { m[6], m[7], m[8], 0 }, w, h, 0, 0 };
    g.vk.vkCmdPushConstants(g.cmd, nl.layout, VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof pc, &pc);
    g.vk.vkCmdDispatch(g.cmd, uint32_t(w + 7) / 8, uint32_t(h + 7) / 8, 1);
    barrier(g.canvas.image, VK_IMAGE_LAYOUT_GENERAL, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_ACCESS_SHADER_WRITE_BIT, VK_ACCESS_TRANSFER_WRITE_BIT | VK_ACCESS_TRANSFER_READ_BIT,
            VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
    nl.frames++;
    if (nl.frames == 1 || nowMs() - nl.lastLog >= 10000) {
        plog(false, "night light: %llu tinted frames (%llu skipped), gains %.3f %.3f %.3f", (unsigned long long)nl.frames,
             (unsigned long long)nl.skipped, double(m[0]), double(m[4]), double(m[8]));
        nl.lastLog = nowMs();
    }
}
// Teardown (teardownLocked, before the device goes): every object the pass made. The shell's matrix is kept.
void nlDestroy()
{
    if (g.device) {
        nlDropView();
        if (nl.pipe) g.vk.vkDestroyPipeline(g.device, nl.pipe, nullptr);
        if (nl.pool) g.vk.vkDestroyDescriptorPool(g.device, nl.pool, nullptr);
        if (nl.layout) g.vk.vkDestroyPipelineLayout(g.device, nl.layout, nullptr);
        if (nl.setLayout) g.vk.vkDestroyDescriptorSetLayout(g.device, nl.setLayout, nullptr);
        if (nl.shader) g.vk.vkDestroyShaderModule(g.device, nl.shader, nullptr);
    }
    nl.pipe = VK_NULL_HANDLE; nl.pool = VK_NULL_HANDLE; nl.set = VK_NULL_HANDLE; nl.layout = VK_NULL_HANDLE; nl.setLayout = VK_NULL_HANDLE; nl.shader = VK_NULL_HANDLE;
    nl.view = VK_NULL_HANDLE; nl.viewGen = 0;
    nl.tried = nl.ready = nl.broken = nl.storage = nl.canvasStorage = false;
}

'''

API = r'''// OMNI_NIGHT_LIGHT_V1: the shell's side (OmniNightLightShell.h). m: row-major 3x3 over the canvas's stored RGB; nullptr: off
// (nothing is recorded from the next present on). 1: the present can apply it (GPU present active, the pass not failed).
extern "C" int omni_gpu_present_night_ready(void)
{
    return g.state.load(std::memory_order_acquire) == kActive && !g.hung && !nl.broken ? 1 : 0;
}
extern "C" int omni_gpu_present_night(const float* m)
{
    {
        std::lock_guard<std::mutex> l(nl.lock);
        nl.want = m != nullptr;
        if (m) memcpy(nl.m, m, sizeof nl.m);
    }
    return omni_gpu_present_night_ready();
}
'''

EDITS = [
    ('#include "OmniZcPageShader.h"',
     '#include "OmniNightLightShader.h"   // OMNI_NIGHT_LIGHT_V1: SPIR-V of omni_night_light.comp\n#include "OmniZcPageShader.h"'),
    ('bool hdrEnsure(uint32_t w, uint32_t h);\nbool ensureCanvas(uint32_t w, uint32_t h)\n{\n',
     STATE + 'bool hdrEnsure(uint32_t w, uint32_t h);\nbool ensureCanvas(uint32_t w, uint32_t h)\n{\n'),
    ('    if (g.canvas.image && g.canvas.w == w && g.canvas.h == h) return true;\n',
     '    if (g.canvas.image && g.canvas.w == w && g.canvas.h == h && (!nl.storage || nl.canvasStorage)) return true;   // OMNI_NIGHT_LIGHT_V1: remade once with STORAGE usage\n'),
    ('        if (g.canvasView) { g.vk.vkDestroyImageView(g.device, g.canvasView, nullptr); g.canvasView = VK_NULL_HANDLE; }   // V2 HDR: the view goes first\n',
     '        if (g.canvasView) { g.vk.vkDestroyImageView(g.device, g.canvasView, nullptr); g.canvasView = VK_NULL_HANDLE; }   // V2 HDR: the view goes first\n'
     '        nlDropView();   // OMNI_NIGHT_LIGHT_V1: its storage view too\n'),
    ('(g.pqArmed ? VK_IMAGE_USAGE_STORAGE_BIT : 0u);   // V2: the PQ pass reads it (V4: armed)\n',
     '(g.pqArmed || nl.storage ? VK_IMAGE_USAGE_STORAGE_BIT : 0u);   // V2: the PQ pass reads it (V4: armed); OMNI_NIGHT_LIGHT_V1: its pass too\n'
     '    nl.canvasStorage = g.pqArmed || nl.storage; nl.canvasGen++;   // OMNI_NIGHT_LIGHT_V1\n'),
    ('    zcRecord(w, h, wantReadback, rec.video);   // OMNI_GPUPAGES_ZEROCOPY_V1: the engine\'s page frame under the shell\'s overlays\n',
     '    zcRecord(w, h, wantReadback, rec.video);   // OMNI_GPUPAGES_ZEROCOPY_V1: the engine\'s page frame under the shell\'s overlays\n'
     '    nlRecord(w, h, wantReadback);   // OMNI_NIGHT_LIGHT_V1: the warm tint over everything composed above (nothing while off)\n'),
    ('// OMNI_GPUPAGES_ZEROCOPY_V1: the shell\'s side (OmniBrowser.cpp, OMNI_GPUPAGES_ZEROCOPY_V1)\n',
     API + '// OMNI_GPUPAGES_ZEROCOPY_V1: the shell\'s side (OmniBrowser.cpp, OMNI_GPUPAGES_ZEROCOPY_V1)\n'),
    ('        zcDestroy();   // OMNI_GPUPAGES_ZEROCOPY_V1: its pipeline before the device (RADV asserts otherwise)\n',
     '        zcDestroy();   // OMNI_GPUPAGES_ZEROCOPY_V1: its pipeline before the device (RADV asserts otherwise)\n'
     '        nlDestroy();   // OMNI_NIGHT_LIGHT_V1: its pipeline and view too\n'),
    ('    { std::lock_guard<std::mutex> c(g.cacheLock); for (Cached& e : g.layers) freeBuf(e.b); g.layers.clear(); }\n    hdrDestroy();\n',
     '    { std::lock_guard<std::mutex> c(g.cacheLock); for (Cached& e : g.layers) freeBuf(e.b); g.layers.clear(); }\n'
     '    nlDestroy();   // OMNI_NIGHT_LIGHT_V1 (host test teardown)\n    hdrDestroy();\n'),
]
for old, _ in EDITS:   # every anchor is checked before anything is written
    if t.count(old) != 1:
        sys.exit('OmniGpuPresent.cpp: anchor found %d times: %r' % (t.count(old), old[:90]))
for old, new in EDITS:
    t = t.replace(old, new, 1)
shutil.copyfile(s1 / 'OmniNightLightShader.h', src / 'OmniNightLightShader.h')
save(t)
print('applied ' + REV + ' (OmniGpuPresent.cpp + OmniNightLightShader.h)')
