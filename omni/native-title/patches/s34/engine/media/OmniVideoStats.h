// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_VIDEO_STATS_BRIDGE_V1: output telemetry, not source HDR/codec claims.
#pragma once
#include <cmath>
#include <cstdio>
#include <string>
struct OmniVideoStatsSnapshot {
    double atMs=0, seconds=0, shown=0, dropped=0;
    bool counters=false, gpuPresent=false, hdrOutput=false;
};
extern "C" int omni_video_stats_snapshot(OmniVideoStatsSnapshot*) __attribute__((weak));
static inline std::string omniVideoStatsJson(const OmniVideoStatsSnapshot& s, int width=0, int height=0, int codec=-1)
{
    if (!std::isfinite(s.atMs)||s.atMs<=0||!std::isfinite(s.seconds)||s.seconds<=0||s.seconds>2) return {};
    char shown[48]="null",dropped[48]="null";
    if (s.counters && std::isfinite(s.shown)&&std::isfinite(s.dropped)&&s.shown>=0&&s.dropped>=0
        &&s.shown/s.seconds<=1000&&s.dropped/s.seconds<=1000) {
        snprintf(shown,sizeof shown,"%.3f",s.shown/s.seconds);
        snprintf(dropped,sizeof dropped,"%.3f",s.dropped/s.seconds);
    }
    // Only fresh, active service-thread metadata is supplied by the caller.
    std::string res="null";
    if(width>=10 && width<=16384 && height>=10 && height<=16384)
        res="\""+std::to_string(width)+"x"+std::to_string(height)+"\"";
    const char* name=codec==0?"\"H.264\"":codec==1?"\"HEVC\"":codec==2?"\"VP9\"":"null";
    return std::string("{\"res\":")+res+",\"codec\":"+name+",\"fpsShown\":"+shown+",\"fpsDropped\":"+dropped
        +",\"path\":\""+(s.gpuPresent?"GPU":"SDL")+"\",\"hdr\":"+(s.hdrOutput?"true":"false")+"}";
}
