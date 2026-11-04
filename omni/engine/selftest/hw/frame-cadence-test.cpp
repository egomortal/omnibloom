#include "../../media/OmniFrameCadence.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <initializer_list>
using OmniMedia::Hw::FrameCadence;
static long long pts(int n, double fps) { return llround(n * 1000.0 / fps) * 1000; }
static int simulate(double fps, double hz, double phase, bool legacy) {
    FrameCadence c; int head=0, drops=0, maxWindow=0, window=0;
    for(int tick=0; tick<3600; ++tick) {
        double target=phase+tick*1000.0/hz;
        auto due=(int64_t)llround((target+500.0/hz)*1000);
        for(int caller=0;caller<4;++caller) {
            auto stamp=[&](size_t i){return pts(head+(int)i,fps);};
            size_t pick=FrameCadence::none;
            if(legacy) { for(size_t i=0;i<100 && stamp(i)<=due;++i) pick=i; }
            else pick=c.select(target,1000.0/hz,due,100,stamp);
            if(pick==FrameCadence::none) continue;
            if(tick>0){ drops+=(int)pick; window+=(int)pick; }
            head+=(int)pick+1;
        }
        if(tick%300==299){if(window>maxWindow)maxWindow=window;window=0;}
    }
    if(!legacy && fps<=hz+0.1){assert(drops<=5);assert(maxWindow<=2);}
    return drops;
}
int main() {
    assert(simulate(60,59.94,0,true)>40); // Reproduces the old repeated burst.
    for(double phase: {0., 0.5, 5., 8., 16.}) {
        simulate(60,59.94,phase,false); simulate(60,60,phase,false);
        simulate(30,59.94,phase,false); simulate(24,59.94,phase,false);
        simulate(60000.0/1001,59.94,phase,false);
    }
    FrameCadence c;
    auto stamp=[](size_t i){return (int64_t)i*16667;};
    assert(c.select(0,16.683,8000,100,stamp)==0);
    assert(c.select(0.01,16.683,8000,100,stamp)==FrameCadence::none);
    assert(c.select(-16,16.683,8000,100,stamp)==FrameCadence::none);
    // A real 250 ms stall must still catch up; never hide real frame drops.
    assert(c.select(250,16.683,258000,100,stamp)>=14);
    c.reset(); // Seek/generation change allows a backwards target immediately.
    assert(c.select(-100,16.683,-100000,100,stamp,true)==0);
    c.reset();
    assert(c.select(0,16.683,0,0,stamp)==FrameCadence::none);
    // A variable-rate gap must not invent frames before their timestamp.
    auto future=[](size_t){return int64_t(1000000);};
    assert(c.select(1,16.683,1000,1,future)==FrameCadence::none);
    puts("PASS: quantized 24/30/59.94/60 fps, phases, repeated callers, real stall, seek, empty queue, timestamp gap");
}
