// SPDX-License-Identifier: GPL-3.0-or-later
#include "OmniMP4Demuxer.h"
#include <algorithm>
#include <chrono>
#include <cstring>
#include <limits>
extern "C" {
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <libavutil/mem.h>
}
namespace OmniMedia {
namespace {
uint32_t be32(const uint8_t* p){return uint32_t(p[0])<<24|uint32_t(p[1])<<16|uint32_t(p[2])<<8|p[3];}
// OMNI_CODEC_OPUS_V1: samples (48 kHz) in one Opus packet from its TOC (RFC 6716 3.1), -1 if
// malformed. Same table as OmniWebMDemuxer's opusPacketSamples, kept here so this file links alone.
int opusSamples(const uint8_t* p,size_t n){
    if(!n)return -1;
    static const int frame[32]={480,960,1920,2880,480,960,1920,2880,480,960,1920,2880,480,960,480,960,
                                120,240,480,960,120,240,480,960,120,240,480,960,120,240,480,960};
    int code=p[0]&3,frames=code==0?1:code==3?(n<2?-1:p[1]&0x3f):2;
    if(frames<=0)return -1;
    int total=frames*frame[p[0]>>3];return total>5760?-1:total;
}
// This finite-fragment adapter supports leading AAC edits only when every edit
// list has a single non-empty, unit-rate entry. Such an edit begins at movie
// time zero. Complex empty/multiple edits require a persistent timeline parser.
bool zeroOriginEdits(const uint8_t* data,size_t length,unsigned depth=0){
    if(depth>4)return false;
    size_t at=0;
    while(at<length){
        if(length-at<8)return false;
        uint64_t size=be32(data+at);size_t header=8;
        if(size==1){if(length-at<16)return false;size=(uint64_t(be32(data+at+8))<<32)|be32(data+at+12);header=16;}
        if(size<header||size>length-at)return false;
        auto type=be32(data+at+4);auto* p=data+at+header;size_t n=size-header;
        if(type==0x656c7374){ // elst
            if(n<8||p[0]>1||be32(p+4)!=1)return false;
            size_t entrySize=p[0]?20:12;
            if(n!=8+entrySize)return false;
            auto* media=p+8+(p[0]?8:4);
            // Negative media_time denotes an empty edit, not encoder priming.
            if(media[0]&0x80)return false;
            auto* rate=p+8+entrySize-4;
            if(be32(rate)!=0x00010000)return false;
        } else if(type==0x6d6f6f76||type==0x7472616b||type==0x65647473){
            if(!zeroOriginEdits(p,n,depth+1))return false;
        }
        at+=size;
    }
    return true;
}
bool boxes(const std::vector<uint8_t>& data,bool initialization){
    size_t at=0;unsigned moov=0,ftyp=0,moof=0,mdat=0;
    while(at<data.size()){
        if(data.size()-at<8)return false;
        uint64_t size=be32(data.data()+at);size_t header=8;
        if(size==1){if(data.size()-at<16)return false;size=uint64_t(be32(data.data()+at+8))<<32|be32(data.data()+at+12);header=16;}
        if(size<header||size>data.size()-at)return false;
        auto type=be32(data.data()+at+4);
        if(type==0x6d6f6f76)++moov; // moov
        if(type==0x66747970)++ftyp;
        if(type==0x6d6f6f66){if(mdat)return false;++moof;}
        if(type==0x6d646174){if(!moof)return false;++mdat;}
        if(type==0x70737368)return false; // pssh: no protected-content support
        at+=size;
    }
    return initialization ? ftyp==1&&moov==1&&!moof&&!mdat : moof==1&&mdat==1&&!moov&&!ftyp;
}
// OMNI_WEBM_V1 rev3: init + fragment are read in place, as one logical stream (no
// concatenated copy; fragments reach 11-13 MB).
struct Input {
    const uint8_t* part[2]={nullptr,nullptr};
    size_t partSize[2]={0,0},total=0;
    size_t position=0;
    std::chrono::steady_clock::time_point deadline=std::chrono::steady_clock::now()+std::chrono::seconds(3);
    void set(const std::vector<uint8_t>& a,const std::vector<uint8_t>& b){
        part[0]=a.data();partSize[0]=a.size();part[1]=b.data();partSize[1]=b.size();total=a.size()+b.size();
    }
    static int interrupt(void* opaque){return std::chrono::steady_clock::now()>static_cast<Input*>(opaque)->deadline;}
    static int read(void* opaque,uint8_t* dest,int size){
        auto& self=*static_cast<Input*>(opaque);if(interrupt(opaque))return AVERROR_EXIT;
        if(size<=0)return AVERROR(EINVAL);
        size_t amount=std::min(size_t(size),self.total-self.position);
        if(!amount)return AVERROR_EOF;
        for(size_t done=0;done<amount;){
            size_t at=self.position+done;int k=at<self.partSize[0]?0:1;size_t from=k?at-self.partSize[0]:at;
            size_t n=std::min(amount-done,self.partSize[k]-from);
            memcpy(dest+done,self.part[k]+from,n);done+=n;
        }
        self.position+=amount;return int(amount);
    }
    static int64_t seek(void* opaque,int64_t offset,int whence){
        auto& self=*static_cast<Input*>(opaque);if(interrupt(opaque))return AVERROR_EXIT;
        if(whence==AVSEEK_SIZE)return int64_t(self.total);
        whence&=~AVSEEK_FORCE;
        int64_t base=whence==SEEK_SET?0:whence==SEEK_CUR?int64_t(self.position):whence==SEEK_END?int64_t(self.total):-1;
        if(base<0||offset < -base || offset > int64_t(self.total)-base)return AVERROR(EINVAL);
        self.position=size_t(base+offset);return int64_t(self.position);
    }
};
int denyOpen(AVFormatContext*,AVIOContext**,const char*,int,AVDictionary**){return AVERROR(EACCES);}
struct Context {
    AVFormatContext* format=nullptr;AVIOContext* io=nullptr;AVPacket* packet=nullptr;
    ~Context(){av_packet_free(&packet);avformat_close_input(&format);if(io){av_freep(&io->buffer);avio_context_free(&io);}}
};
}
static bool demux(const std::vector<uint8_t>& init,const std::vector<uint8_t>& fragment,MP4DemuxResult& out,MP4DemuxLimits limits,bool initializationOnly){
    out={};auto fail=[&](const char* message){out={};out.error=message;return false;};
    // OMNI_WEBM_V1 rev3: hard maxima 32 MiB / 8192 packets (were 8 MiB / 4096).
    if(!limits.inputBytes||limits.inputBytes>32*1024*1024||!limits.outputBytes||limits.outputBytes>32*1024*1024||limits.extraDataBytes>64*1024||!limits.packets||limits.packets>8192)return fail("Invalid demux limits");
    if(init.size()>limits.inputBytes||fragment.size()>limits.inputBytes-init.size())return fail("Input quota exceeded");
    if(!boxes(init,true)||(!initializationOnly&&!boxes(fragment,false)))return fail("Incomplete or unsupported MP4 framing");
    Input input;input.set(init,fragment); // OMNI_WEBM_V1 rev3: no copy
    Context context;auto* buffer=static_cast<uint8_t*>(av_malloc(4096));if(!buffer)return fail("IO allocation failed");
    context.io=avio_alloc_context(buffer,4096,0,&input,Input::read,nullptr,Input::seek);
    if(!context.io){av_free(buffer);return fail("IO allocation failed");}
    context.format=avformat_alloc_context();if(!context.format)return fail("Format allocation failed");
    context.format->pb=context.io;context.format->flags|=AVFMT_FLAG_CUSTOM_IO;
    context.format->io_open=denyOpen;context.format->interrupt_callback={Input::interrupt,&input};
    context.format->max_streams=2;context.format->probesize=limits.inputBytes;context.format->max_analyze_duration=0;
    AVDictionary* options=nullptr;av_dict_set(&options,"format_whitelist","mov",0);av_dict_set(&options,"protocol_whitelist","",0);av_dict_set(&options,"codec_whitelist","h264,aac,opus,hevc",0); // OMNI_CODEC_OPUS_V1: + opus; OMNI_CODEC_HEVC_V1: + hevc (the hevc parser needs it; never decoded, see skip_frame)
    av_dict_set(&options,"enable_drefs","0",0);av_dict_set(&options,"use_absolute_path","0",0);
    int result=avformat_open_input(&context.format,nullptr,av_find_input_format("mov"),&options);av_dict_free(&options);
    if(result<0)return fail("MP4 initialization rejected");
    if(!context.format->nb_streams||context.format->nb_streams>2)return fail("Track count exceeded");
    size_t used=0;
    for(unsigned i=0;i<context.format->nb_streams;++i){
        auto* stream=context.format->streams[i];auto* parameters=stream->codecpar;
        if(parameters->codec_tag==0x76636e65u||parameters->codec_tag==0x61636e65u)return fail("Encrypted sample entry unsupported"); // encv / enca
        if(stream->time_base.num<=0||stream->time_base.den<=0||stream->id<0)return fail("Invalid track timing or ID");
        for(const auto& track:out.tracks)if(track.id==stream->id)return fail("Duplicate track ID");
        DemuxTrack track;track.id=stream->id;track.timeBase={stream->time_base.num,stream->time_base.den};
        if(parameters->codec_type==AVMEDIA_TYPE_VIDEO&&parameters->codec_id==AV_CODEC_ID_H264){
            track.codec=DemuxCodec::H264;track.width=parameters->width;track.height=parameters->height;
            if(track.width<=0||track.height<=0||int64_t(track.width)*track.height>1920*1080)return fail("Video dimensions unsupported");
        }else if(parameters->codec_type==AVMEDIA_TYPE_VIDEO&&parameters->codec_id==AV_CODEC_ID_HEVC){
            // OMNI_CODEC_HEVC_V1: 'hvc1' / 'hev1' (hvcC required), to 3840x2160; hardware decode only
            // (PacketDecoder). The bounded probe skips its frames (skip_frame=all).
            if(!hevcEnabled())return fail("HEVC disabled (hevc-disabled.flag)");
            track.codec=DemuxCodec::HEVC;track.width=parameters->width;track.height=parameters->height;
            if(track.width<=0||track.height<=0||track.width>3840||track.height>2160)return fail("Video dimensions unsupported");
        }else if(parameters->codec_type==AVMEDIA_TYPE_AUDIO&&parameters->codec_id==AV_CODEC_ID_AAC){
            track.codec=DemuxCodec::AAC;track.sampleRate=parameters->sample_rate;track.channels=parameters->ch_layout.nb_channels;
            if(track.sampleRate<8000||track.sampleRate>192000||track.channels<1||track.channels>8)return fail("Audio dimensions unsupported");
        }else if(parameters->codec_type==AVMEDIA_TYPE_AUDIO&&parameters->codec_id==AV_CODEC_ID_OPUS){
            // OMNI_CODEC_OPUS_V1: 'Opus' sample entry; MOV turns dOps into OpusHead extradata.
            track.codec=DemuxCodec::Opus;track.sampleRate=parameters->sample_rate;track.channels=parameters->ch_layout.nb_channels;
            if(track.sampleRate<8000||track.sampleRate>192000||track.channels<1||track.channels>8)return fail("Audio dimensions unsupported");
        }else return fail("Unsupported track codec");
        if(parameters->extradata_size<=0||size_t(parameters->extradata_size)>limits.extraDataBytes||size_t(parameters->extradata_size)>limits.outputBytes-used)return fail("Codec metadata quota or missing configuration");
        track.extraData.assign(parameters->extradata,parameters->extradata+parameters->extradata_size);used+=track.extraData.size();out.tracks.push_back(std::move(track));
    }
    if(initializationOnly)return true;
    // H264-only init headers already supplied validated dimensions/configuration.
    // Avoid decoding probe frames again for each fragment; playback decoding
    // remains in PacketDecoder. AAC still needs the bounded probe to establish
    // codec frame duration, including a final packet lacking container duration.
    bool needsAACProbe=std::any_of(out.tracks.begin(),out.tracks.end(),[](const DemuxTrack& track){return track.codec==DemuxCodec::AAC;});
    if(needsAACProbe){
        std::vector<AVDictionary*> probeOptions(context.format->nb_streams,nullptr);
        for(auto& option:probeOptions){
            av_dict_set(&option,"threads","1",0);
            av_dict_set(&option,"max_pixels","2073600",0);
            av_dict_set(&option,"max_samples","131072",0);
        }
        // OMNI_CODEC_HEVC_V1: HEVC is never decoded in software, not even by the probe (an HEVC +
        // AAC file probes for the AAC frame duration): its frames are skipped there.
        for(unsigned i=0;i<context.format->nb_streams;++i)
            if(context.format->streams[i]->codecpar->codec_id==AV_CODEC_ID_HEVC)av_dict_set(&probeOptions[i],"skip_frame","all",0);
        result=avformat_find_stream_info(context.format,probeOptions.data());
        for(auto& option:probeOptions)av_dict_free(&option);
        if(result<0)return fail("Bounded stream probing failed");
    }
    if(Input::interrupt(&input))return fail("Demux deadline exceeded");
    if(context.format->nb_streams!=out.tracks.size())return fail("Track metadata changed during probe");
    for(unsigned i=0;i<context.format->nb_streams;++i){
        const auto& track=out.tracks[i];auto* stream=context.format->streams[i];auto* p=stream->codecpar;
        if(stream->id!=track.id||stream->time_base.num!=track.timeBase.numerator||stream->time_base.den!=track.timeBase.denominator||
           p->extradata_size<0||size_t(p->extradata_size)!=track.extraData.size()||
           (p->extradata_size&&memcmp(p->extradata,track.extraData.data(),track.extraData.size())))return fail("Track configuration changed during probe");
    }
    context.packet=av_packet_alloc();if(!context.packet)return fail("Packet allocation failed");
    while((result=av_read_frame(context.format,context.packet))>=0){
        auto& packet=*context.packet;
        if(Input::interrupt(&input))return fail("Demux deadline exceeded");
        if(packet.stream_index<0||unsigned(packet.stream_index)>=out.tracks.size())return fail("Invalid packet track");
        if(packet.flags&AV_PKT_FLAG_CORRUPT)return fail("Corrupt packet");
        if(av_packet_get_side_data(&packet,AV_PKT_DATA_ENCRYPTION_INFO,nullptr)||av_packet_get_side_data(&packet,AV_PKT_DATA_ENCRYPTION_INIT_INFO,nullptr))return fail("Encrypted packet unsupported");
        if(packet.pts==AV_NOPTS_VALUE||packet.dts==AV_NOPTS_VALUE||packet.duration<0)return fail("Packet timing missing");
        if(packet.size<=0||size_t(packet.size)>limits.outputBytes-used||out.packets.size()>=limits.packets)return fail("Packet output quota exceeded");
        const auto& track=out.tracks[packet.stream_index];
        DemuxPacket item;item.trackId=track.id;item.timeBase=track.timeBase;item.pts=packet.pts;item.dts=packet.dts;item.duration=packet.duration;item.keyFrame=packet.flags&AV_PKT_FLAG_KEY;
        if(!item.duration&&track.codec==DemuxCodec::AAC){
            auto* parameters=context.format->streams[packet.stream_index]->codecpar;
            int samples=av_get_audio_frame_duration2(parameters,packet.size);
            // Convert codec sample count to track ticks exactly, without rounding
            // or an assumed AAC frame size. Unknown/non-integral results remain
            // missing and must use the explicitly marked next-DTS fallback below.
            if(samples>0&&samples<=131072&&parameters->sample_rate==track.sampleRate){
                int64_t numerator=int64_t(samples)*track.timeBase.denominator;
                int64_t denominator=int64_t(parameters->sample_rate)*track.timeBase.numerator;
                if(denominator>0&&numerator%denominator==0){
                    item.duration=numerator/denominator;
                    item.durationSource=DemuxDurationSource::AudioCodecSamples;
                }
            }
        }
        if(!item.duration&&track.codec==DemuxCodec::Opus){
            // OMNI_CODEC_OPUS_V1: MOV leaves Opus packet durations unset (FFmpeg's own ffprobe shows
            // N/A); the TOC gives the sample count at 48 kHz, exactly.
            int samples=opusSamples(packet.data,size_t(packet.size));
            int64_t numerator=int64_t(samples)*track.timeBase.denominator,denominator=int64_t(48000)*track.timeBase.numerator;
            if(samples>0&&denominator>0&&numerator%denominator==0){item.duration=numerator/denominator;item.durationSource=DemuxDurationSource::AudioCodecSamples;}
        }
        item.bytes.assign(packet.data,packet.data+packet.size);used+=item.bytes.size();
        size_t skipSize=0;const auto* skip=av_packet_get_side_data(&packet,AV_PKT_DATA_SKIP_SAMPLES,&skipSize);
        if(skip){
            if(skipSize!=10||skipSize>limits.outputBytes-used)return fail("Invalid or oversized priming metadata");
            item.skipSamples.assign(skip,skip+skipSize);used+=skipSize;
            // MOV initializes AAC start_pad again whenever init+fragment is
            // reopened. Restrict that leading edit-list trim to samples before
            // the validated edit-list origin, not the first packet of every
            // later fragment. Keep trailing discard and reason bytes intact.
            // OMNI_CODEC_OPUS_V1: Opus pre-skip arrives the same way (edit list / dOps PreSkip).
            if(track.codec==DemuxCodec::AAC||track.codec==DemuxCodec::Opus){
                uint32_t leading=uint32_t(skip[0])|(uint32_t(skip[1])<<8)|(uint32_t(skip[2])<<16)|(uint32_t(skip[3])<<24);
                if(leading){
                    if(!zeroOriginEdits(init.data(),init.size())||track.sampleRate<=0)return fail("AAC complex edit priming unsupported");
                    __int128 before=-static_cast<__int128>(packet.pts)*track.timeBase.numerator*track.sampleRate;
                    if(before<0)before=0;
                    if(before%track.timeBase.denominator)return fail("AAC priming boundary is not sample aligned");
                    before/=track.timeBase.denominator;
                    uint32_t applied=before<leading?static_cast<uint32_t>(before):leading;
                    for(unsigned n=0;n<4;++n)item.skipSamples[n]=uint8_t(applied>>(n*8));
                }
            }
        }
        out.packets.push_back(std::move(item));av_packet_unref(&packet);
    }
    if(result!=AVERROR_EOF)return fail("MP4 packet read failed");
    if(out.packets.empty())return fail("Fragment contains no packets");
    for(size_t i=0;i<out.packets.size();++i){
        auto& packet=out.packets[i];if(packet.duration)continue;
        const auto track=std::find_if(out.tracks.begin(),out.tracks.end(),[&](const DemuxTrack& t){return t.id==packet.trackId;});
        if(track!=out.tracks.end()&&track->codec==DemuxCodec::HEVC){
            // OMNI_CODEC_HEVC_V1: MOV + the hevc parser leave HEVC durations unset when nothing probes
            // the stream (H.264's parser fills them): the DTS step to the track's next sample; the
            // fragment's last sample repeats the previous step.
            auto next=std::find_if(out.packets.begin()+i+1,out.packets.end(),[&](const DemuxPacket& p){return p.trackId==packet.trackId;});
            int64_t step=0;
            if(next!=out.packets.end())step=next->dts-packet.dts;
            else for(size_t j=i;j-->0;)if(out.packets[j].trackId==packet.trackId){step=out.packets[j].duration;break;}
            if(step<=0)return fail("Cannot derive HEVC duration");
            packet.duration=step;packet.durationFromNextDTS=true;packet.durationSource=DemuxDurationSource::NextTrackDTS;
            continue;
        }
        if(track==out.tracks.end()||(track->codec!=DemuxCodec::AAC&&track->codec!=DemuxCodec::Opus))return fail("Packet duration missing"); // OMNI_CODEC_OPUS_V1: + Opus
        auto next=std::find_if(out.packets.begin()+i+1,out.packets.end(),[&](const DemuxPacket& p){return p.trackId==packet.trackId;});
        if(next==out.packets.end()||next->dts<=packet.dts||
           (packet.dts<0&&next->dts>std::numeric_limits<int64_t>::max()+packet.dts))return fail("Cannot derive AAC duration from next DTS");
        packet.duration=next->dts-packet.dts;packet.durationFromNextDTS=true;
        packet.durationSource=DemuxDurationSource::NextTrackDTS;
    }
    return true;
}
bool demuxMP4Fragment(const std::vector<uint8_t>& init,const std::vector<uint8_t>& fragment,MP4DemuxResult& out,MP4DemuxLimits limits){return demux(init,fragment,out,limits,false);}
bool inspectMP4Initialization(const std::vector<uint8_t>& init,MP4DemuxResult& out,MP4DemuxLimits limits){return demux(init,{},out,limits,true);}
}
