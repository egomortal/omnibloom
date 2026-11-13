// omni-gpu-pages STAGE 1b (OMNI_GPU_PAGES_ASYNC_V1): async scrolling on the GPU-composited page, default OFF.
// Built only in a tree configured with ENABLE_ASYNC_SCROLLING=ON (which also turns on SCROLLING_THREAD on this
// port: OptionsPlayStation.cmake). At run time it needs ALL of: stage 1 on (/data/omni/gpu-pages-stage1.flag, no
// stage-1 kill switch), /data/omni/gpu-pages-async.flag, and no /data/omni/gpu-pages-async-off.flag. Otherwise the
// drawing area reports no async scrolling, and WebKit falls back to main-thread scrolling. Included once, at the top
// of DrawingAreaCoordinatedGraphics.cpp, after ogp-s1-drawingarea.inc.
#include <cstdio>
#include <unistd.h>
extern "C" int omni_gpu_pages_s1_enabled(void) __attribute__((weak));
namespace OmniGpuPagesS1b {
static bool asyncScrollingAllowed()
{
    static int allowed = -1;
    if (allowed < 0) {
        bool s1 = omni_gpu_pages_s1_enabled && omni_gpu_pages_s1_enabled();
        allowed = s1 && !access("/data/omni/gpu-pages-async.flag", F_OK) && access("/data/omni/gpu-pages-async-off.flag", F_OK);
        fprintf(stderr, "OMNI GPUPAGES async scrolling: %s (stage 1 %s)\n", allowed ? "ON" : "off", s1 ? "on" : "off");
    }
    return allowed;
}
}
