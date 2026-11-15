#!/usr/bin/env python3
"""OMNI_GPUPAGES_ZEROCOPY_V1, shell side (OmniBrowser.cpp; outputs/omni-gpu-pages/ZERO-COPY-DESIGN.md).

GPU page mode, while ALL hold: /data/omni/gpu-pages-zerocopy.flag (no -off flag), the title's GPU present says ready
(HDR-armed canvas, compose pipeline, nothing failed), a half-resolution page (omniPageScale < 1), no hole-punched video,
and the active tab's engine has published a frame of exactly the half-size page through its control page
(/data/omni/gpu-pages/zc-<pid>.ctl). Then:
  - tick(): a newly published frame is a full-page change (omniDrPageFull + page damage): the usual draw + present run;
  - omniPageToCanvasRows(): the page rows are filled transparent (0) instead of copied; bars, toasts and the pointer still
    draw over them; the present composes the engine's frame under them (OmniGpuPresent.cpp);
  - omniPaintPage / omniPaintPagePartial: no WKPagePaint (the engine sends no bitmaps in this mode).
Leaving (any condition gone, tab switch, size change): the engine is told to send bitmaps again (consumer = 0), the
present forgets the engine's buffers, and WKPageForceRepaint brings the UI process's copy up to date; a size mismatch
backs off for 2 s. Idempotent; each anchor must be found exactly once.
usage: apply_zerocopy_shell.py <OmniBrowser.cpp>"""
import sys
from pathlib import Path

MARK = 'OMNI_GPUPAGES_ZEROCOPY_V1'
p = Path(sys.argv[1])
t = p.read_text(encoding='utf-8')
if MARK in t:
    print('already OmniBrowser.cpp'); sys.exit(0)

HELPERS = r'''// OMNI_GPUPAGES_ZEROCOPY_V1 (outputs/omni-gpu-pages/ZERO-COPY-DESIGN.md): the page's frames straight from the engine's GPU.
#include <fcntl.h>
#include <sys/mman.h>
struct OmniZcCtl {   // = ogp-s1-surface.inc's OmniZcCtl
    uint32_t magic, version; int32_t pid, consumer; uint32_t seq, slot, width, height, stride, pad;
    uint64_t address, frame, consumed, titleBeat, engineBeat;
};
extern "C" int omni_gpu_present_zc_ready(void) __attribute__((weak));
extern "C" void omni_gpu_present_zc_page(void* ctl, int dx, int dy, int dw, int dh) __attribute__((weak));
static struct {
    int pid = 0; OmniZcCtl* ctl = nullptr; bool active = false; uint64_t lastFrame = 0;
    uint32_t retryAt = 0; uint64_t enters = 0, leaves = 0, frames = 0;
} omniZc;
static bool omniZcWanted()
{
    static const bool on = !access("/data/omni/gpu-pages-zerocopy.flag", F_OK) && access("/data/omni/gpu-pages-zerocopy-off.flag", F_OK);
    return on;
}
static OmniZcCtl* omniZcOpen(int pid)
{
    char path[96]; snprintf(path, sizeof path, "/data/omni/gpu-pages/zc-%d.ctl", pid);
    const int fd = open(path, O_RDWR);
    if (fd < 0) return nullptr;
    void* m = mmap(nullptr, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    close(fd);
    if (m == MAP_FAILED) return nullptr;
    OmniZcCtl* c = static_cast<OmniZcCtl*>(m);
    if (__atomic_load_n(&c->magic, __ATOMIC_ACQUIRE) != 0x5a43504fu || c->pid != pid) { munmap(m, 4096); return nullptr; }
    return c;
}
static void omniZcRelease(const char* why, bool repaint)
{
    if (omniZc.ctl) __atomic_store_n(&omniZc.ctl->consumer, 0, __ATOMIC_RELEASE);   // the engine sends bitmaps again
    if (omni_gpu_present_zc_page) omni_gpu_present_zc_page(nullptr, 0, 0, 0, 0);
    if (omniZc.active) {
        omniZc.active = false; ++omniZc.leaves;
        char line[160]; snprintf(line, sizeof line, "zero-copy page OFF (%s): %llu frames in, %llu on / %llu off", why,
            (unsigned long long)omniZc.frames, (unsigned long long)omniZc.enters, (unsigned long long)omniZc.leaves);
        log(line);
        if (repaint && active() && active()->page) WKPageForceRepaint(active()->page, nullptr, [](WKErrorRef, void*) { });
    }
}
static bool omniZcActive() { return omniZc.active; }
// Each tick: true when the engine published a new page frame (draw the page rows: transparent, the GPU fills them).
static bool omniZcTick()
{
    const bool ok = omniZcWanted() && omni_gpu_present_zc_ready && omni_gpu_present_zc_ready() && active() && !active()->crashed
        && active()->page && omniPageScale < 1 && !OmniMedia::Hw::holePunchActive();
    if (!ok) { if (omniZc.active || omniZc.ctl) omniZcRelease("conditions", true); if (omniZc.ctl) { munmap(omniZc.ctl, 4096); omniZc.ctl = nullptr; omniZc.pid = 0; } return false; }
    const int pid = int(WKPageGetProcessIdentifier(active()->page));
    if (pid != omniZc.pid) {
        if (omniZc.ctl) { omniZcRelease("tab or engine changed", true); munmap(omniZc.ctl, 4096); omniZc.ctl = nullptr; }
        omniZc.pid = pid; omniZc.lastFrame = 0;
    }
    if (pid <= 0 || SDL_GetTicks() < omniZc.retryAt) return false;
    if (!omniZc.ctl) {
        omniZc.ctl = omniZcOpen(pid);
        if (!omniZc.ctl) { omniZc.retryAt = SDL_GetTicks() + 1000; return false; }
        __atomic_store_n(&omniZc.ctl->consumer, 1, __ATOMIC_RELEASE);   // the engine publishes frames from its next one on
        WKPageForceRepaint(active()->page, nullptr, [](WKErrorRef, void*) { });   // so the first one comes now
    }
    OmniZcCtl* c = omniZc.ctl;
    __atomic_store_n(&c->titleBeat, c->titleBeat + 1, __ATOMIC_RELAXED);
    const uint32_t s1 = __atomic_load_n(&c->seq, __ATOMIC_ACQUIRE);
    const uint64_t frame = c->frame; const uint32_t w = c->width, h = c->height;
    const uint32_t s2 = __atomic_load_n(&c->seq, __ATOMIC_ACQUIRE);
    if ((s1 & 1) || s1 != s2 || !frame) return false;
    if (int(w) != (renderWidth + 1) / 2 || int(h) != (renderPageHeight + 1) / 2) {   // not the half-size page: the CPU path, retry in 2 s
        omniZcRelease("frame size differs from the page", true); munmap(omniZc.ctl, 4096); omniZc.ctl = nullptr;
        omniZc.retryAt = SDL_GetTicks() + 2000;
        return false;
    }
    if (!omniZc.active) { omniZc.active = true; ++omniZc.enters; log("zero-copy page ON (OMNI_GPUPAGES_ZEROCOPY_V1): the engine's frames go to the GPU directly"); }
    if (frame == omniZc.lastFrame) return false;
    omniZc.lastFrame = frame; ++omniZc.frames;
    return true;
}
'''

EDITS = [
    ('// One row of the page (ARGB8888 as WKPagePaint writes it: memory B,G,R,A) into the canvas (ABGR8888: R,G,B,A),\n',
     HELPERS + '// One row of the page (ARGB8888 as WKPagePaint writes it: memory B,G,R,A) into the canvas (ABGR8888: R,G,B,A),\n'),
    # after the title's OMNI_PAINT_HOLD_V1 block (a held page keeps its background fill)
    ('    const bool fast = omniSmoothDrawOn() && dst.x == 0 && canvas->format->format == SDL_PIXELFORMAT_ABGR8888 && renderWidth <= canvas->w;\n',
     '    if (omniZcActive() && dst.x == 0 && renderWidth <= canvas->w && canvas->format->format == SDL_PIXELFORMAT_ABGR8888) {   // OMNI_GPUPAGES_ZEROCOPY_V1\n'
     '        if (omni_gpu_present_zc_page) omni_gpu_present_zc_page(omniZc.ctl, 0, dst.y, renderWidth, renderPageHeight);\n'
     '        for (int y = ra; y < rb; ++y) memset(static_cast<uint8_t*>(canvas->pixels) + size_t(y) * canvas->pitch, 0, size_t(renderWidth) * 4);   // the GPU fills these\n'
     '        if (renderWidth < canvas->w) { SDL_Rect r { renderWidth, ra, canvas->w - renderWidth, rb - ra }; SDL_FillRect(canvas, &r, bgPixel); }\n'
     '        return;\n    }\n'
     '    const bool fast = omniSmoothDrawOn() && dst.x == 0 && canvas->format->format == SDL_PIXELFORMAT_ABGR8888 && renderWidth <= canvas->w;\n'),
    ('static int omniPaintPagePartial(int rows, const OmniViewDirty& r)\n{\n',
     'static int omniPaintPagePartial(int rows, const OmniViewDirty& r)\n{\n    if (omniZcActive()) return 0;   // OMNI_GPUPAGES_ZEROCOPY_V1: the engine sends no bitmaps; its frames reach the GPU\n'),
    ('static void omniPaintPage(int rows)\n{\n',
     'static void omniPaintPage(int rows)\n{\n    if (omniZcActive()) { omniPageDamage.add(0, renderPageHeight); return; }   // OMNI_GPUPAGES_ZEROCOPY_V1: no WKPagePaint\n'),
    # Just before tick() decides whether to draw at all (it skips the draw unless omniPageCopied, omniShellDirty or the 1 s
    # refresh): after the page-paint section, whose safety-net compare could otherwise clear the page damage again (the CPU
    # page buffer does not change in zero-copy mode). V1 had this before that section and set no omniPageCopied: the
    # screen then changed only on the 1 s refresh (0.99 fps, console 2026-11-15T02:4xZ).
    ('    if (!firstFrame && !omniPageCopied && !omniShellDirty && !omniRefreshDue) {\n',
     '    if (omniZcTick()) { omniDrawReasons |= omniDrPageFull; omniPageDamage.add(0, renderPageHeight); omniPageCopied = true; }   // OMNI_GPUPAGES_ZEROCOPY_V1: a new engine frame\n'
     '    if (!firstFrame && !omniPageCopied && !omniShellDirty && !omniRefreshDue) {\n'),
]
for old, new in EDITS:
    if t.count(old) != 1:
        sys.exit('OmniBrowser.cpp: anchor found %d times: %r' % (t.count(old), old[:80]))
    t = t.replace(old, new, 1)
p.write_text(t, encoding='utf-8')
print('patched OmniBrowser.cpp')
