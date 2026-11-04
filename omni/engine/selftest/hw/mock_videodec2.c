// Host stand-in for libSceVideodec2, decoding with FFmpeg and writing the PS5
// layout the references document: NV12 (or low-aligned 16-bit two-plane for
// 10-bit), luma pitch 256-byte aligned, UV after a 32-row-aligned coded height,
// pictures emitted in display order with decoder lag. Test only.
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <libavcodec/avcodec.h>
#include "../../media/OmniSceVideodec2.h"
#include <unistd.h>
static int mode(const char*m){const char*e=getenv("MOCK_FAIL");return e&&!strncmp(e,m,strlen(m));}
static long modeArg(void){const char*e=getenv("MOCK_FAIL");const char*a=e?strchr(e,'@'):0;return a?atol(a+1):0;}
static long decodes;
typedef struct { AVCodecContext*c; AVPacket*pk; AVFrame*f; uint32_t type; int failnext; int hiddenPending; int bps; } mdec;
int32_t sceVideodec2QueryComputeMemoryInfo(SceVideodec2ComputeMemoryInfo*m){ if(m->size!=sizeof*m)return -1; m->cpu_gpu_size=12345; return 0; }
int32_t sceVideodec2AllocateComputeQueue(const SceVideodec2ComputeConfigInfo*c,const SceVideodec2ComputeMemoryInfo*m,void**q){ if(c->size!=sizeof*c||!m->cpu_gpu)return -1; *q=(void*)1; return 0; }
int32_t sceVideodec2ReleaseComputeQueue(void*q){ return q?0:-1; }
int32_t sceVideodec2QueryDecoderMemoryInfo(const SceVideodec2DecoderConfigInfo*c,SceVideodec2DecoderMemoryInfo*m){
  if(c->size!=sizeof*c||m->size!=sizeof*m||!c->compute_queue)return -1;
  int bps=c->profile==2&&c->codec_type!=1?2:1; uint64_t pitch=((uint64_t)c->max_width*bps+255)&~255ull;
  m->cpu_size=1<<20; m->gpu_size=1<<20; m->cpu_gpu_size=1<<16; m->max_frame_size=pitch*c->max_height*3/2; m->frame_alignment=256; return 0; }
int32_t sceVideodec2CreateDecoder(const SceVideodec2DecoderConfigInfo*c,const SceVideodec2DecoderMemoryInfo*m,void**d){
  if(!m->cpu||!m->gpu||!m->cpu_gpu)return -1;
  if(mode("create"))return (int32_t)0x811d0111;
  enum AVCodecID id=c->codec_type==SCE_VIDEODEC2_CODEC_AVC?AV_CODEC_ID_H264:c->codec_type==SCE_VIDEODEC2_CODEC_HEVC?AV_CODEC_ID_HEVC:c->codec_type==SCE_VIDEODEC2_CODEC_VP9?AV_CODEC_ID_VP9:AV_CODEC_ID_NONE;
  const AVCodec*k=avcodec_find_decoder(id); if(!k)return -2;
  mdec*x=calloc(1,sizeof*x); x->c=avcodec_alloc_context3(k); x->c->thread_count=1; x->type=c->codec_type; x->bps=(c->profile==2&&c->codec_type!=1)?2:1;
  if(avcodec_open2(x->c,k,0)<0)return -3; x->pk=av_packet_alloc(); x->f=av_frame_alloc(); *d=x; return 0; }
int32_t sceVideodec2DeleteDecoder(void*d){ mdec*x=d; avcodec_free_context(&x->c); av_packet_free(&x->pk); av_frame_free(&x->f); free(x); return 0; }
int32_t sceVideodec2Reset(void*d){ mdec*x=d; avcodec_flush_buffers(x->c); return 0; }
static void emit(mdec*x,SceVideodec2FrameBuffer*fb,SceVideodec2OutputInfo*o){
  AVFrame*f=x->f; int hi=f->format==AV_PIX_FMT_YUV420P10LE, bps=hi?2:1;
  uint32_t pitchB=((uint32_t)f->width*bps+255)&~255u, coded=(f->height+31)&~31;
  uint8_t*b=fb->buffer; memset(b,0x5a,(size_t)pitchB*coded*3/2); uint8_t*uv=b+(size_t)pitchB*coded;
  for(int y=0;y<f->height;y++) memcpy(b+(size_t)pitchB*y,f->data[0]+(size_t)f->linesize[0]*y,(size_t)f->width*bps);
  for(int y=0;y<f->height/2;y++) for(int i=0;i<f->width/2;i++){
    if(hi){ uint16_t*d=(uint16_t*)(uv+(size_t)pitchB*y); d[2*i]=((uint16_t*)(f->data[1]+f->linesize[1]*y))[i]; d[2*i+1]=((uint16_t*)(f->data[2]+f->linesize[2]*y))[i]; }
    else { uint8_t*d=uv+(size_t)pitchB*y; d[2*i]=f->data[mode("swapuv")?2:1][f->linesize[1]*y+i]; d[2*i+1]=f->data[mode("swapuv")?1:2][f->linesize[2]*y+i]; } }
  o->valid=1; o->picture_count=1; o->codec=x->type; o->width=f->width; o->height=coded; o->pitch=pitchB/bps; o->pitch_bytes=pitchB;
  o->buffer=b; o->buffer_size=(uint64_t)pitchB*coded*3/2; fb->accepted=1; av_frame_unref(f); }
int32_t sceVideodec2Decode(void*d,SceVideodec2InputData*in,SceVideodec2FrameBuffer*fb,SceVideodec2OutputInfo*o){
  if(mode("hang")&&in->pts==5)sleep(10);
  if(mode("decode"))return (int32_t)0x80020000|5200;
  decodes++;
  if(mode("decode@") && decodes>modeArg()) return (int32_t)0x811d0001;
  if(mode("hang@") && decodes==modeArg()) sleep(10);
  mdec*x=d; if(in->size!=sizeof*in||fb->size!=sizeof*fb||o->size!=sizeof*o)return -1;
  if(av_new_packet(x->pk,(int)in->au_size)<0)return -2; memcpy(x->pk->data,in->au,in->au_size); x->pk->pts=(int64_t)in->pts;
  int r=avcodec_send_packet(x->c,x->pk); av_packet_unref(x->pk); if(r<0&&r!=AVERROR(EAGAIN))return 0x811d0001;
  int hidden=0;
  if(x->type==SCE_VIDEODEC2_CODEC_VP9){ const uint8_t*b=in->au; unsigned bits=(b[0]<<8)|(in->au_size>1?b[1]:0); int i=15;
    i-=2; int prof=((bits>>i)&1)|(((bits>>(i-1))&1)<<1); i-=2; if(prof==3)i--; int se=(bits>>i)&1; i--; if(!se){ i--; hidden=!((bits>>i)&1);} }
  if(avcodec_receive_frame(x->c,x->f)==0) emit(x,fb,o);
  else if(hidden){ /* console behaviour: a picture flagged not_displayed (garbage content) */
    uint8_t*b=fb->buffer; memset(b,0x7f,4096); o->valid=1; o->picture_count=1; o->not_displayed=1; o->codec=x->type;
    o->width=x->c->width; o->height=(x->c->height+31)&~31; o->pitch_bytes=((unsigned)x->c->width*x->bps+255)&~255u; o->pitch=o->pitch_bytes/x->bps;
    o->buffer=b; o->buffer_size=(uint64_t)o->pitch_bytes*o->height*3/2; fb->accepted=1; }
  return 0; }
int32_t sceVideodec2Flush(void*d,SceVideodec2FrameBuffer*fb,SceVideodec2OutputInfo*o){
  mdec*x=d; avcodec_send_packet(x->c,NULL); if(avcodec_receive_frame(x->c,x->f)==0) emit(x,fb,o); return 0; }
