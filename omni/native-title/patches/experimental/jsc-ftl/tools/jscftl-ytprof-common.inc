// OMNI_YTPROF_V1: diagnostic main-thread category timers (Omni ytprof, 2026-11-05). Every hook is a no-op unless
// /data/omni/ytprof.flag exists when the process first asks (checked once, raw open()). Sink: WTF/wtf/MainThread.cpp.
#ifndef OMNI_YTPROF_COMMON
#define OMNI_YTPROF_COMMON 1
#include <stdint.h>
extern "C" int omni_ytprof_on(void);
extern "C" int omni_ytprof_push(int);
extern "C" void omni_ytprof_pop(int);
extern "C" uint64_t omni_ytprof_now(void);
extern "C" void omni_ytprof_offmain(int, uint64_t);
extern "C" void omni_ytprof_gc(int);
extern "C" void omni_ytprof_mark(const char*, double);
enum { OMNI_YP_TASK, OMNI_YP_JS, OMNI_YP_COMPILE, OMNI_YP_GC, OMNI_YP_SWEEP, OMNI_YP_STYLE, OMNI_YP_LAYOUT, OMNI_YP_PAINT,
    OMNI_YP_RASTER, OMNI_YP_DECODE, OMNI_YP_PARSE, OMNI_YP_CSSPARSE, OMNI_YP_RUPD, OMNI_YP_COUNT };
struct OmniYtprofScope {
    int cat; int mode; uint64_t t0;
    explicit OmniYtprofScope(int c) : cat(c), mode(0), t0(0)
    {
        if (omni_ytprof_on()) {
            mode = omni_ytprof_push(c) ? 1 : 2;
            if (mode == 2)
                t0 = omni_ytprof_now();
        }
    }
    ~OmniYtprofScope()
    {
        if (mode == 1)
            omni_ytprof_pop(cat);
        else if (mode == 2)
            omni_ytprof_offmain(cat, omni_ytprof_now() - t0);
    }
    OmniYtprofScope(const OmniYtprofScope&) = delete;
    OmniYtprofScope& operator=(const OmniYtprofScope&) = delete;
};
#define OMNI_YTPROF_SCOPE(c) OmniYtprofScope omniYtprofScope(c)
#endif
