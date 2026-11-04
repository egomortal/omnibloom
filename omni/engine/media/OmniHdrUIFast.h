// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_HDR_UI_FAST_V1: opaque SDR UI pixels (sRGB, BT.709) to packed PQ BT.2020 10:10:10:2, 8 at a time.
// While the display is PQ, every ordinary present converted the whole 4K UI surface through
// omniHDRUIPixel one pixel at a time (~18 ms: a frame's whole budget at 60 Hz, so windowed video and
// SDR video ran at 30 fps and every page update cost a frame). Same tables and the same arithmetic
// as OmniHdrUI.h's UIColour::blend(0xc0000000, r, g, b, 255); multiplies and adds stay separate
// (no fused multiply-add) so results match the scalar path. Checked over all 16.7M colours on the host.
#pragma once
#include "OmniHdrColour.h"
#include <immintrin.h>
#include <array>
#include <cstring>
#include <cstdint>
#include <algorithm>
namespace OmniMedia::Hdr {
class UIFast {
public:
    std::array<float,35904> encode_{};   // 35898 used, padded so i + 1 never leaves the table
    std::array<float,256> linear_{};
    UIFast() {
        for(unsigned i=0;i<35898;i++){uint32_t bits=i<<15;float n;std::memcpy(&n,&bits,4);encode_[i]=float(pqEncode(n));}
        for(unsigned i=35898;i<encode_.size();i++)encode_[i]=encode_[35897];
        for(unsigned c=0;c<256;c++)linear_[c]=float(srgbLinear(double(c)/255));
    }
    __attribute__((target("avx2"))) inline __m256i encode8(__m256 n) const {
        n=_mm256_max_ps(_mm256_setzero_ps(),_mm256_min_ps(_mm256_set1_ps(10000.f),n));
        const __m256i bits=_mm256_castps_si256(n);
        const __m256i i=_mm256_srli_epi32(bits,15);
        const __m256 f=_mm256_mul_ps(_mm256_cvtepi32_ps(_mm256_and_si256(bits,_mm256_set1_epi32(32767))),_mm256_set1_ps(1.f/32768.f));
        const __m256 e0=_mm256_i32gather_ps(encode_.data(),i,4);
        const __m256 e1=_mm256_i32gather_ps(encode_.data()+1,i,4);
        __m256 e=_mm256_add_ps(e0,_mm256_mul_ps(_mm256_sub_ps(e1,e0),f));
        // quant: uint32_t(max(0, min(1023, x * 1023 + .5)))
        e=_mm256_add_ps(_mm256_mul_ps(e,_mm256_set1_ps(1023.f)),_mm256_set1_ps(.5f));
        e=_mm256_max_ps(_mm256_setzero_ps(),_mm256_min_ps(_mm256_set1_ps(1023.f),e));
        return _mm256_cvttps_epi32(e);
    }
    __attribute__((target("avx2"))) static inline __m256 mix8(float a,float b,float c,__m256 sr,__m256 sg,__m256 sb){
        return _mm256_mul_ps(_mm256_add_ps(_mm256_add_ps(_mm256_mul_ps(_mm256_set1_ps(a),sr),_mm256_mul_ps(_mm256_set1_ps(b),sg)),_mm256_mul_ps(_mm256_set1_ps(c),sb)),_mm256_set1_ps(203.f));
    }
    // n pixels, 8-bit channels; rgba: R in the low byte (else B low, R in bits 16-23).
    __attribute__((target("avx2"))) void span(const uint32_t* src,uint32_t* dst,size_t n,bool rgba) const {
        const __m256i m8=_mm256_set1_epi32(255);
        const int rs=rgba?0:16, bs=rgba?16:0;
        const __m128i rshift=_mm_cvtsi32_si128(rs), bshift=_mm_cvtsi32_si128(bs);
        size_t x=0;
        // Flat areas (page backgrounds, black bars) are runs of one colour: 8 equal to the last
        // converted colour cost one compare and one store.
        uint32_t lastSrc=0, lastOut=0; bool have=false;
        for(;n-x>=8;x+=8){
            const __m256i p=_mm256_loadu_si256(reinterpret_cast<const __m256i*>(src+x));
            const uint32_t first=uint32_t(_mm256_cvtsi256_si32(p));
            if(_mm256_movemask_epi8(_mm256_cmpeq_epi32(p,_mm256_set1_epi32(int(first))))==-1){
                if(!have || first!=lastSrc){ lastSrc=first; lastOut=one(first,rgba); have=true; }
                _mm256_storeu_si256(reinterpret_cast<__m256i*>(dst+x),_mm256_set1_epi32(int(lastOut)));
                continue;
            }
            const __m256i r=_mm256_and_si256(_mm256_srl_epi32(p,rshift),m8);
            const __m256i g=_mm256_and_si256(_mm256_srli_epi32(p,8),m8);
            const __m256i b=_mm256_and_si256(_mm256_srl_epi32(p,bshift),m8);
            const __m256 sr=_mm256_i32gather_ps(linear_.data(),r,4), sg=_mm256_i32gather_ps(linear_.data(),g,4), sb=_mm256_i32gather_ps(linear_.data(),b,4);
            const __m256i qr=encode8(mix8(.6274038959f,.3292830384f,.0433130657f,sr,sg,sb));
            const __m256i qg=encode8(mix8(.0690972894f,.9195403951f,.0113623156f,sr,sg,sb));
            const __m256i qb=encode8(mix8(.0163914389f,.0880133079f,.8955952532f,sr,sg,sb));
            const __m256i out=_mm256_or_si256(_mm256_or_si256(qr,_mm256_slli_epi32(qg,10)),_mm256_or_si256(_mm256_slli_epi32(qb,20),_mm256_set1_epi32(int(0xc0000000u))));
            _mm256_storeu_si256(reinterpret_cast<__m256i*>(dst+x),out);
        }
        for(;x<n;x++) dst[x]=one(src[x],rgba);
    }
    uint32_t one(uint32_t p,bool rgba) const {   // scalar, same arithmetic
            const int rs=rgba?0:16, bs=rgba?16:0;
            const unsigned r=(p>>rs)&255,g=(p>>8)&255,b=(p>>bs)&255;
            const float sr=linear_[r],sg=linear_[g],sb=linear_[b];
            auto enc=[&](float v){v=std::max(0.f,std::min(10000.f,v));uint32_t bits;std::memcpy(&bits,&v,4);unsigned i=bits>>15;float f=float(bits&32767)*(1.f/32768.f);
                float e=encode_[i]+(encode_[i+1]-encode_[i])*f; return uint32_t(std::max(0.f,std::min(1023.f,e*1023.f+.5f)));};
            volatile float rr=(.6274038959f*sr+.3292830384f*sg+.0433130657f*sb)*203.f;
            volatile float gg=(.0690972894f*sr+.9195403951f*sg+.0113623156f*sb)*203.f;
            volatile float bb=(.0163914389f*sr+.0880133079f*sg+.8955952532f*sb)*203.f;
            return enc(rr)|(enc(gg)<<10)|(enc(bb)<<20)|0xc0000000u;
    }
};
inline const UIFast& uiFast(){static const UIFast t;return t;}
}
