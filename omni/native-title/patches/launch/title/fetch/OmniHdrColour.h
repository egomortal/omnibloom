// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>

// Experimental CPU HDR color primitives. No display changes or allocations.
// These are deliberately separate from the accepted eight-bit SDR path.
namespace OmniMedia::Hdr {
struct Signal {
    int primaries = -1, transfer = -1, matrix = -1, depth = 0;
    bool fullRange = false;
    // Main10 alone is not HDR. Only explicit BT.2020 NCL + ST2084 is accepted.
    bool isPQ2020() const { return primaries == 9 && transfer == 16 && matrix == 9 && depth == 10; }
};
inline double unit(double x) { return std::isfinite(x) ? std::max(0.0, std::min(1.0, x)) : 0.0; }
inline double pqEncode(double nits)
{
    constexpr double m1=2610.0/16384, m2=2523.0/32, c1=3424.0/4096, c2=2413.0/128, c3=2392.0/128;
    double p=std::pow(unit(nits/10000.0),m1);
    return std::pow((c1+c2*p)/(1+c3*p),m2);
}
inline double pqDecode(double pq)
{
    constexpr double m1=2610.0/16384, m2=2523.0/32, c1=3424.0/4096, c2=2413.0/128, c3=2392.0/128;
    double p=std::pow(unit(pq),1/m2);
    return 10000*std::pow(std::max(p-c1,0.0)/(c2-c3*p),1/m1);
}
inline double srgbLinear(double x) { x=unit(x); return x<=0.04045 ? x/12.92 : std::pow((x+0.055)/1.055,2.4); }
inline unsigned ten(double v) { return unsigned(std::lround(unit(v)*1023)); }
// Matches the tested VideoOut RGB10A2 PQ format; never reinterpret RGBA8 bytes.
inline uint32_t pack(double r,double g,double b) { return ten(r)|(ten(g)<<10)|(ten(b)<<20)|0xc0000000u; }
inline uint32_t yuv10(unsigned y,unsigned u,unsigned v,bool full)
{
    // Decoder samples are LOW-aligned planar ten-bit, not high-aligned P010.
    double yy=(double(y)-(full?0:64))/(full?1023:876);
    double cb=(double(u)-512)/(full?1023:896), cr=(double(v)-512)/(full?1023:896);
    // BT.2020 non-constant luminance yields already PQ-encoded R'G'B'.
    // Encoding PQ again here would destroy the mastered luminance.
    return pack(yy+1.4746*cr,yy-0.16455312684366*cb-0.57135312684366*cr,yy+1.8814*cb);
}
// Q16 conversion keeps the four-byte packed output and avoids per-pixel floating
// point rounding calls. Coefficients are selected once per frame. The double
// precision yuv10() above remains the independent reference for error tests.
struct Matrix10 {
    int32_t y, r, gu, gv, b, offset;
    explicit Matrix10(bool full) :
        y(int32_t(std::lround(65536.0*1023/(full?1023:876)))),
        r(int32_t(std::lround(65536.0*1023*1.4746/(full?1023:896)))),
        gu(int32_t(std::lround(-65536.0*1023*0.16455312684366/(full?1023:896)))),
        gv(int32_t(std::lround(-65536.0*1023*0.57135312684366/(full?1023:896)))),
        b(int32_t(std::lround(65536.0*1023*1.8814/(full?1023:896)))), offset(full?0:64) {}
    static uint32_t quant(int32_t value) {
        return uint32_t(std::max(0,std::min(1023,(value+32768)>>16)));
    }
    uint32_t pixel(unsigned yy,unsigned uu,unsigned vv) const {
        int32_t l=(int32_t(yy)-offset)*y,cb=int32_t(uu)-512,cr=int32_t(vv)-512;
        return quant(l+r*cr)|(quant(l+gu*cb+gv*cr)<<10)|(quant(l+b*cb)<<20)|0xc0000000u;
    }
};
struct Plane10 { const uint16_t* data; size_t samples, stride; };
inline bool valid(Plane10 p,size_t w,size_t h)
{
    return p.data && w && h && p.stride>=w && p.samples>=w && (h-1)<=(p.samples-w)/p.stride;
}
// Callers retain ownership throughout conversion. Validate all extents before writing.
inline bool convert(const Signal& s,Plane10 y,Plane10 u,Plane10 v,
    size_t w,size_t h,uint32_t* out,size_t count,size_t stride)
{
    size_t cw=w/2+w%2,ch=h/2+h%2;
    if(!s.isPQ2020() || !valid(y,w,h) || !valid(u,cw,ch) || !valid(v,cw,ch)
        || !out || stride<w || count<w || (h-1)>(count-w)/stride) return false;
    const Matrix10 matrix(s.fullRange);
    for(size_t row=0;row<h;row++) for(size_t col=0;col<w;col++)
        out[row*stride+col]=matrix.pixel(y.data[row*y.stride+col]&1023,
            u.data[(row/2)*u.stride+col/2]&1023,v.data[(row/2)*v.stride+col/2]&1023);
    return true;
}
// Reference overlay compositor: input bytes are premultiplied sRGB R,G,B,A.
// Alpha must be undone BEFORE transfer decoding. Blend in absolute linear light,
// not PQ code space; paper white is intentionally separate from video peak.
// Reference-only until measured: pow() per mixed pixel is not a 4K60 claim.
inline uint32_t overlay(uint32_t video,unsigned r,unsigned g,unsigned b,unsigned a,double white=203)
{
    if(!a) return video;
    if(a>255 || r>a || g>a || b>a || !std::isfinite(white) || white<=0 || white>10000) return video;
    double alpha=a/255.0, sr=srgbLinear(double(r)/a),sg=srgbLinear(double(g)/a),sb=srgbLinear(double(b)/a);
    double ur=(0.6274038959*sr+0.3292830384*sg+0.0433130657*sb)*white;
    double ug=(0.0690972894*sr+0.9195403951*sg+0.0113623156*sb)*white;
    double ub=(0.0163914389*sr+0.0880133079*sg+0.8955952532*sb)*white;
    return pack(pqEncode(ur*alpha+pqDecode((video&1023)/1023.0)*(1-alpha)),
        pqEncode(ug*alpha+pqDecode(((video>>10)&1023)/1023.0)*(1-alpha)),
        pqEncode(ub*alpha+pqDecode(((video>>20)&1023)/1023.0)*(1-alpha)));
}
} // namespace OmniMedia::Hdr
