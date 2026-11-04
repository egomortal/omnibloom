// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "OmniHdrColour.h"
#include <cstdint>
#include <cstddef>
#include <cstring>
namespace OmniMedia::Hdr {
enum class Pixels : uint8_t { SDR_RGBA8, PQ_RGB10A2 };
struct View { const uint32_t* pixels=nullptr; size_t width=0,height=0,stride=0,capacity=0; Pixels encoding=Pixels::SDR_RGBA8; uint64_t generation=0; };
struct Target { uint32_t* pixels=nullptr; size_t width=0,height=0,capacity=0; Pixels encoding=Pixels::SDR_RGBA8; uint64_t generation=0; };
// State belongs to the presenter. Changing format invalidates prepared content;
// negotiation is never inferred from codec depth, source transfer, or a flag.
class OutputState {
    bool requested_=false,confirmed_=false,ready_=false;
    Pixels encoding_=Pixels::SDR_RGBA8;
    uint64_t generation_=1;
public:
    explicit OutputState(const char* flag=nullptr):requested_(flag && !std::strcmp(flag,"1")){}
    bool requested() const {return requested_;}
    Pixels encoding() const {return encoding_;}
    uint64_t generation() const {return generation_;}
    bool ready() const {return ready_;}
    bool sdr() const {return ready_ && encoding_==Pixels::SDR_RGBA8;}
    bool hdr() const {return encoding_==Pixels::PQ_RGB10A2 && confirmed_;}
    bool accept(bool registeredPQ,unsigned outputRange) {
        ++generation_;confirmed_=false;ready_=false;encoding_=Pixels::SDR_RGBA8;
        if(requested_ && registeredPQ && outputRange==2){encoding_=Pixels::PQ_RGB10A2;confirmed_=true;ready_=true;return true;}
        // range 2 with an SDR surface is NOT safe SDR fallback. Caller must stop
        // submitting and restore a known matching surface/output combination.
        ready_=!registeredPQ && outputRange==1;return ready_;
    }
    void invalidate(){++generation_;confirmed_=false;ready_=false;encoding_=Pixels::SDR_RGBA8;}
};
inline bool validView(const View& v){return v.pixels && v.width && v.height && v.stride>=v.width && v.capacity>=v.width && (v.height-1)<=(v.capacity-v.width)/v.stride;}
using TileVideo = bool(*)(void*,const uint32_t*,size_t,uint32_t*,size_t,size_t);
using TileIndex = size_t(*)(size_t,size_t,size_t);
// Experimental PQ direct composition. Does not reinterpret PQ as RGBA8 and
// does not borrow input pointers beyond this synchronous call. The caller must
// hold the same ownership used by the v139 helper, never a new long-lived lock.
// SDR is deliberately NOT implemented here: caller keeps its existing v139 path.
inline bool composePQ(const OutputState& state,const View& video,const View& ui,const Target& dst,
 const uint32_t* runs,size_t count,const uint32_t* mix,const uint32_t* pages,size_t mixes,
 bool uiRGBA,TileVideo tile,TileIndex index,void* tileContext)
{
 if(!state.hdr() || !tile || !index || !validView(video) || !validView(ui) || !dst.pixels
   || video.encoding!=Pixels::PQ_RGB10A2 || ui.encoding!=Pixels::SDR_RGBA8 || dst.encoding!=Pixels::PQ_RGB10A2
   || video.generation!=state.generation() || ui.generation!=state.generation() || dst.generation!=state.generation()
   || video.width!=dst.width || video.height!=dst.height || ui.width!=dst.width || ui.height!=dst.height
   || count%3 || (!runs && count) || ((!mix || !pages) && mixes))return false;
 size_t previousY=0,end=0;bool first=true;
 for(size_t i=0;i<count;i+=3){size_t y=runs[i],x=runs[i+1],n=runs[i+2];if(y>=dst.height || x>dst.width || n>dst.width-x || (!first && (y<previousY || (y==previousY && x<end))))return false;previousY=y;end=x+n;first=false;}
 if(dst.width>SIZE_MAX/dst.height)return false;
 for(size_t i=0;i<mixes;i++)if(mix[i]>=dst.width*dst.height)return false;
 // Verify tiled capacity before the first write. This is intentionally reference
 // integration code; replace the scan only with a proven backend extent contract.
 for(size_t y=0;y<dst.height;y++)for(size_t x=0;x<dst.width;x++)if(index(x,y,dst.width)>=dst.capacity)return false;
 if(!tile(tileContext,video.pixels,video.stride,dst.pixels,dst.width,dst.height))return false;
 auto rgba=[uiRGBA](uint32_t p,unsigned& r,unsigned& g,unsigned& b){g=(p>>8)&255;r=(p>>(uiRGBA?0:16))&255;b=(p>>(uiRGBA?16:0))&255;};
 size_t run=0;
 for(size_t y=0;y<dst.height;y++){
  size_t x=0;
  auto paint=[&](size_t col){unsigned r,g,b;rgba(ui.pixels[y*ui.stride+col],r,g,b);dst.pixels[index(col,y,dst.width)]=overlay(0xc0000000u,r,g,b,255);};
  while(run<count && runs[run]==y){for(;x<runs[run+1];x++)paint(x);x=runs[run+1]+runs[run+2];run+=3;}
  for(;x<dst.width;x++)paint(x);
 }
 // Existing mixPage samples are premultiplied BGRA regardless of canvas order.
 for(size_t i=0;i<mixes;i++){
  size_t y=mix[i]/dst.width,x=mix[i]%dst.width;uint32_t p=pages[i];
  dst.pixels[index(x,y,dst.width)]=overlay(video.pixels[y*video.stride+x],(p>>16)&255,(p>>8)&255,p&255,p>>24);
 }
 return true;
}
}
