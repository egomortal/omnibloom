// Isolated SDR release candidate: guarded d0648ba converter, no HDR output implementation.
#include "OmniMain10Sdr.h"
#include <cpuid.h>
#include <unistd.h>
static bool cpuReady(){unsigned a,b,c,d,lo,hi;if(!__get_cpuid(1,&a,&b,&c,&d)||!(c&(1u<<27))||!(c&(1u<<28)))return false;__asm__ volatile("xgetbv":"=a"(lo),"=d"(hi):"c"(0));return (lo&6)==6&&__get_cpuid_count(7,0,&a,&b,&c,&d)&&(b&(1u<<5));}
extern "C" int omniMain10SdrConvert(const uint16_t*y,size_t yn,size_t ys,const uint16_t*u,size_t un,size_t us,const uint16_t*v,size_t vn,size_t vs,int w,int h,uint32_t*out,size_t count,size_t stride,uint32_t colour,int rgba){
static const bool enabled=access("/data/omni/main10-sdr-fast-test.flag",F_OK)==0&&cpuReady();
static const bool hdrRequested=access("/data/omni/hdr-presenter-test.flag",F_OK)==0;
if(!enabled||hdrRequested||w<=0||h<=0||!(colour&0x100)||(colour&255)!=1||((colour>>16)&255)!=1||(colour>>24)!=1)return 0;
return OmniMedia::Main10Sdr::convert({y,yn,ys},{u,un,us},{v,vn,vs},size_t(w),size_t(h),out,count,stride,bool(colour&0x200),rgba);
}

// OMNI_HDR_PORT_V1: HDR presenter helpers from experiments/omni-hdr (OmniHdrBridge.cpp, commit 6b3e154),
// minus its own Main10 SDR entry point (this file's stays). The HDR SDL archive calls these; output
// is PQ only while /data/omni/hdr-presenter-test.flag is present and the display accepted the format.
#include "OmniHdrSimd.h"
#include "OmniHdrUI.h"
#include <atomic>
#include <algorithm>
static std::atomic<int> omniHdrFormatPQ{0};
static std::atomic<int> omniHdrOutputPQ{0};
extern "C" int omniHDRRequested(){
 static const bool requested=access("/data/omni/hdr-presenter-test.flag",F_OK)==0;
 return requested;
}
extern "C" int omniHDRCpuReady(){ return cpuReady(); }
// OMNI_HDR_AUTO_V1: /data/omni/hdr-auto.flag (without the fixed hdr-presenter-test.flag): the SDL archive registers a PQ buffer
// set beside the SDR one and flips it only while an HDR video is composed directly; everything else stays SDR (the system
// converts SDR buffers to the HDR signal). "Available" = that PQ set exists; FormatPQ stays 0 (no fixed PQ presents).
static std::atomic<int> omniHdrAvailable{0};
extern "C" int omniHDRAutoRequested(){
 static const bool requested=access("/data/omni/hdr-auto.flag",F_OK)==0 && access("/data/omni/hdr-presenter-test.flag",F_OK)!=0;
 return requested;
}
extern "C" void omniHDRSetAvailable(int on){ omniHdrAvailable.store(on,std::memory_order_release); }
extern "C" int omniHDRPQAvailable(){ return omniHdrAvailable.load(std::memory_order_acquire); }
extern "C" void omniHDRFormat(int pq){omniHdrFormatPQ.store(pq,std::memory_order_release);omniHdrOutputPQ.store(0,std::memory_order_release);}
extern "C" int omniHDRFormatPQ(){return omniHdrFormatPQ.load(std::memory_order_acquire);}
extern "C" void omniHDROutputRange(int range){omniHdrOutputPQ.store(range==2 && omniHDRFormatPQ(),std::memory_order_release);}
extern "C" int omniHDROutputPQ(){return omniHdrOutputPQ.load(std::memory_order_acquire);}
// OMNI_HDR_BANDS_V1: the 4K PQ conversion (~7.8 ms on one core) split into row bands on helper threads
// created per frame with PTHREAD_INHERIT_SCHED: they run at the video service thread's own priority (helpers
// at a lower priority starved behind it on the console earlier). Kill switch: hdr-bands-disabled.flag.
#include <pthread.h>
namespace {
struct OmniHdrBand { OmniMedia::Hdr::Signal s; const uint16_t *y,*u,*v; size_t yn,ys,un,us,vn,vs; size_t w,r0,r1; uint32_t* out; size_t count,stride; bool ok; };
static bool omniHdrBandRun(OmniHdrBand& b){
 const size_t h=b.r1-b.r0, c0=b.r0/2;
 return OmniMedia::Hdr::convertAVX2<8>(b.s,{b.y+b.r0*b.ys,b.yn-b.r0*b.ys,b.ys},{b.u+c0*b.us,b.un-c0*b.us,b.us},{b.v+c0*b.vs,b.vn-c0*b.vs,b.vs},
  b.w,h,b.out+b.r0*b.stride,b.count-b.r0*b.stride,b.stride);
}
static void* omniHdrBandThread(void* p){ auto& b=*static_cast<OmniHdrBand*>(p); b.ok=omniHdrBandRun(b); return nullptr; }
}
extern "C" int omniHDRConvert10(const uint16_t* y,size_t yn,size_t ys,const uint16_t* u,size_t un,size_t us,const uint16_t* v,size_t vn,size_t vs,int w,int h,uint32_t* out,size_t count,size_t stride,uint32_t colour){
 if(w<=0 || h<=0 || !(omniHDRFormatPQ() || omniHDRPQAvailable()))return 0;   // OMNI_HDR_AUTO_V1
 OmniMedia::Hdr::Signal s{int((colour>>16)&255),int(colour>>24),int(colour&255),10,bool(colour&0x200)};
 static const bool bands=access("/data/omni/hdr-bands-disabled.flag",F_OK)!=0;
 if(!bands || h<64) return OmniMedia::Hdr::convertAVX2<8>(s,{y,yn,ys},{u,un,us},{v,vn,vs},size_t(w),size_t(h),out,count,stride);
 constexpr int kBands=4;
 OmniHdrBand b[kBands]; pthread_t t[kBands]; bool started[kBands]={};
 const size_t step=(size_t(h)/kBands+1)&~size_t(1);   // even rows: a band starts on a chroma row
 for(int i=0;i<kBands;i++){
  const size_t r0=std::min(size_t(h),i*step), r1=i==kBands-1?size_t(h):std::min(size_t(h),(i+1)*step);
  b[i]={s,y,u,v,yn,ys,un,us,vn,vs,size_t(w),r0,r1,out,count,stride,true};
 }
 pthread_attr_t attr; const bool attrOk=pthread_attr_init(&attr)==0 && pthread_attr_setinheritsched(&attr,PTHREAD_INHERIT_SCHED)==0;
 for(int i=1;i<kBands;i++) if(b[i].r1>b[i].r0) started[i]=attrOk && pthread_create(&t[i],&attr,omniHdrBandThread,&b[i])==0;
 if(attrOk) pthread_attr_destroy(&attr);
 bool ok=b[0].r1>b[0].r0 ? omniHdrBandRun(b[0]) : true;
 for(int i=1;i<kBands;i++){ if(started[i]) pthread_join(t[i],nullptr); else if(b[i].r1>b[i].r0) b[i].ok=omniHdrBandRun(b[i]); ok=ok&&b[i].ok; }
 return ok;
}
extern "C" uint32_t omniHDRUIPixel(uint32_t pixel,int rgba){ return OmniMedia::Hdr::opaqueUI(pixel,rgba); }
extern "C" uint32_t omniHDRMixPixel(uint32_t video,uint32_t bgra){ return OmniMedia::Hdr::uiColour().blend(video,(bgra>>16)&255,(bgra>>8)&255,bgra&255,bgra>>24); }

// OMNI_HDR_UI_FAST_V1: the PQ display's UI conversion for a whole present, called by the HDR SDL archive
// (v3) instead of omniHDRUIPixel per pixel (~18 ms per 4K present). Rows equal to the previous present's
// source are skipped (the converted copy is persistent); changed rows go through the 8-wide converter in
// 4 row bands on threads that inherit the caller's scheduling (as OMNI_HDR_BANDS_V1). Writes the changed
// row range to *dirtyY0 / *dirtyY1 (empty: nothing changed). Kill switch: hdr-ui-fast-disabled.flag.
#include "OmniHdrUIFast.h"
#include <vector>
namespace {
struct OmniUICanvas { std::vector<uint32_t> prev; int w=0,h=0; const void* dst=nullptr; };
struct OmniUIBand { const uint8_t* src; int pitch; uint32_t* dst; uint32_t* prev; int w,r0,r1; bool rgba,force; int lo,hi; };
static void omniUIBandRun(OmniUIBand& b){
 b.lo=b.r1;b.hi=b.r0;
 const auto& f=OmniMedia::Hdr::uiFast();
 for(int y=b.r0;y<b.r1;y++){
  const uint32_t* s=reinterpret_cast<const uint32_t*>(b.src+size_t(y)*size_t(b.pitch));
  uint32_t* p=b.prev+size_t(y)*size_t(b.w);
  if(!b.force && !std::memcmp(s,p,size_t(b.w)*4)) continue;
  f.span(s,b.dst+size_t(y)*size_t(b.w),size_t(b.w),b.rgba);
  std::memcpy(p,s,size_t(b.w)*4);
  b.lo=std::min(b.lo,y);b.hi=std::max(b.hi,y+1);
 }
}
static void* omniUIBandThread(void* p){ omniUIBandRun(*static_cast<OmniUIBand*>(p)); return nullptr; }
}
extern "C" int omniHDRCanvasConvert(const void* src,int pitch,uint32_t* dst,int w,int h,int rgba,int* dirtyY0,int* dirtyY1){
 static const bool disabled=access("/data/omni/hdr-ui-fast-disabled.flag",F_OK)==0;
 if(disabled || !src || !dst || w<=0 || h<=0 || pitch<w*4 || !omniHDRCpuReady()) return 0;
 static OmniUICanvas c;
 bool force=false;
 if(c.w!=w || c.h!=h || c.dst!=dst){ c.prev.assign(size_t(w)*h,0); c.w=w; c.h=h; c.dst=dst; force=true; }
 constexpr int kBands=4;
 OmniUIBand b[kBands]; pthread_t t[kBands]; bool started[kBands]={};
 const int step=(h+kBands-1)/kBands;
 for(int i=0;i<kBands;i++){ const int r0=std::min(h,i*step),r1=std::min(h,(i+1)*step);
  b[i]={static_cast<const uint8_t*>(src),pitch,dst,c.prev.data(),w,r0,r1,bool(rgba),force,r1,r0}; }
 pthread_attr_t attr; const bool attrOk=pthread_attr_init(&attr)==0 && pthread_attr_setinheritsched(&attr,PTHREAD_INHERIT_SCHED)==0;
 for(int i=1;i<kBands;i++) if(b[i].r1>b[i].r0) started[i]=attrOk && pthread_create(&t[i],&attr,omniUIBandThread,&b[i])==0;
 if(attrOk) pthread_attr_destroy(&attr);
 omniUIBandRun(b[0]);
 for(int i=1;i<kBands;i++){ if(started[i]) pthread_join(t[i],nullptr); else if(b[i].r1>b[i].r0) omniUIBandRun(b[i]); }
 int lo=h,hi=0; for(int i=0;i<kBands;i++) if(b[i].lo<b[i].hi){ lo=std::min(lo,b[i].lo); hi=std::max(hi,b[i].hi); }
 if(dirtyY0)*dirtyY0=lo<hi?lo:0; if(dirtyY1)*dirtyY1=lo<hi?hi:0;
 return 1;
}
