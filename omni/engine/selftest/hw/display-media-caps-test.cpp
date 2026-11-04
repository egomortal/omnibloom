// Regression: native 4K presentation limits must not disable supported decoding.
#include "../../media/OmniMediaCaps.h"
#include <cassert>
#include <cstdio>
using namespace OmniMedia::Caps;
int main() {
    Decoders d; d.vp9=d.opus=d.hevc=d.vp9TenBitHigh=true;
    for (bool hevc : {false,true}) {
        VideoQuery q; q.containerType=hevc?"video/mp4":"video/webm";
        q.codecs={hevc?"hvc1.1.6.L153.B0":"vp09.00.51.08"};
        q.width=3840;q.height=2160;q.framerate=30;
        auto answer=[&]{return decideVideo(Kind::MediaSource,true,q,&d,&d);};
        assert(answer().supported && answer().smooth);
        q.framerate=60;assert(answer().supported && !answer().smooth);
        assert(mseTypeSupport(q.containerType,q.codecs,true,d)==Support::Yes);
        q.width=1920;q.height=1080;assert(answer().supported && answer().smooth);
        q.hdr=true;assert(!answer().supported);q.hdr=false;
        q.width=7680;q.height=4320;assert(!answer().supported);
    }
    puts("PASS: 4K30 smooth, 4K60 supported but not smooth, 1080p60 retained, HDR/8K refused");
}
