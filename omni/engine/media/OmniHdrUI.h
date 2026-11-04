// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "OmniHdrColour.h"
#include <array>
#include <cstring>
// UI only: the first console integration spent 5.74 seconds per full-canvas
// conversion evaluating reference pow() calls. Keep video AVX2 unchanged.
// Tables interpolate PQ in float-bit intervals (dense near black), avoiding the
// large dark-region error of a uniformly spaced absolute-luminance table.
namespace OmniMedia::Hdr {
class UIColour {
    std::array<float,35898> encode_{};
    std::array<float,1024> decode_{};
    std::array<float,65536> linear_{};
public:
    UIColour() {
        for(unsigned i=0;i<encode_.size();i++){uint32_t bits=i<<15;float n;std::memcpy(&n,&bits,4);encode_[i]=float(pqEncode(n));}
        for(unsigned i=0;i<1024;i++)decode_[i]=float(pqDecode(i/1023.0));
        for(unsigned a=1;a<256;a++)for(unsigned c=0;c<=a;c++)linear_[a*256+c]=float(srgbLinear(double(c)/a));
    }
    float encode(float n) const {
        n=std::max(0.f,std::min(10000.f,n));uint32_t bits;std::memcpy(&bits,&n,4);
        unsigned i=bits>>15;float f=float(bits&32767)*(1.f/32768.f);
        return encode_[i]+(encode_[i+1]-encode_[i])*f;
    }
    uint32_t blend(uint32_t video,unsigned r,unsigned g,unsigned b,unsigned a) const {
        if(!a || a>255 || r>a || g>a || b>a)return video;
        float alpha=a/255.f,remain=1-alpha;
        float sr=linear_[a*256+r],sg=linear_[a*256+g],sb=linear_[a*256+b];
        float rr=(.6274038959f*sr+.3292830384f*sg+.0433130657f*sb)*203.f;
        float gg=(.0690972894f*sr+.9195403951f*sg+.0113623156f*sb)*203.f;
        float bb=(.0163914389f*sr+.0880133079f*sg+.8955952532f*sb)*203.f;
        auto quant=[](float x){return uint32_t(std::max(0.f,std::min(1023.f,x*1023.f+.5f)));};
        return quant(encode(rr*alpha+decode_[video&1023]*remain))
            |(quant(encode(gg*alpha+decode_[(video>>10)&1023]*remain))<<10)
            |(quant(encode(bb*alpha+decode_[(video>>20)&1023]*remain))<<20)|0xc0000000u;
    }
};
inline const UIColour& uiColour(){static const UIColour table;return table;}
inline uint32_t opaqueUI(uint32_t pixel,bool rgba){
    unsigned r=(pixel>>(rgba?0:16))&255,g=(pixel>>8)&255,b=(pixel>>(rgba?16:0))&255;
    uint32_t key=0xff000000u|(r<<16)|(g<<8)|b;
    struct Entry{uint32_t key=0,value=0;};
    // Fixed storage, no allocations or locking per pixel. Cache is presenter-
    // thread local; hash collisions only recompute the same color transform.
    static thread_local std::array<Entry,4096> cache{};
    auto& entry=cache[((key^(key>>12))*2654435761u)>>20];
    if(entry.key!=key){entry.value=uiColour().blend(0xc0000000u,r,g,b,255);entry.key=key;}
    return entry.value;
}
}
