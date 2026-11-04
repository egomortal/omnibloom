#include "../../media/OmniMP4Demuxer.h"
#include <cassert>
#include <fstream>
#include <iostream>
#include <iterator>
using namespace OmniMedia;
std::vector<uint8_t> read(const std::string& path){std::ifstream f(path,std::ios::binary);assert(f);return {std::istreambuf_iterator<char>(f),{}};}
int main(int argc,char** argv){
    assert(argc==2);std::string root=argv[1];
    for(int id=0;id<2;++id){
        auto init=read(root+"/init-"+std::to_string(id)+".mp4");
        auto first=read(root+"/segment-"+std::to_string(id)+"-00001.m4s");
        auto second=read(root+"/segment-"+std::to_string(id)+"-00002.m4s");
        MP4DemuxResult a,b;
        assert(inspectMP4Initialization(init,a));assert(a.tracks.size()==1&&a.packets.empty());
        const auto header=a.tracks.front();
        if(!demuxMP4Fragment(init,first,a)){std::cerr<<a.error<<'\n';return 1;}
        if(!demuxMP4Fragment(init,second,b)){std::cerr<<b.error<<'\n';return 1;}
        assert(a.tracks.size()==1&&b.tracks.size()==1);
        assert(header.id==a.tracks[0].id&&header.extraData==a.tracks[0].extraData);
        assert(header.timeBase.denominator==a.tracks[0].timeBase.denominator);
        assert(a.tracks[0].codec==(id?DemuxCodec::AAC:DemuxCodec::H264));
        assert(a.tracks[0].extraData==b.tracks[0].extraData);
        assert(a.packets.front().dts==(id?-1024:0));
        assert(b.packets.front().dts==a.packets.back().dts+a.packets.back().duration);
        for(const auto& packet:a.packets){
            assert(packet.pts==packet.dts&&packet.duration>0&&!packet.bytes.empty());
            assert(packet.trackId==a.tracks[0].id);
            assert(packet.timeBase.denominator==a.tracks[0].timeBase.denominator);
        }
        if(!id)assert(a.packets.front().keyFrame&&a.packets.size()==30);
        else {
            assert(a.tracks[0].sampleRate==48000&&a.tracks[0].channels==2);
            assert(!a.packets.front().durationFromNextDTS);
            assert(a.packets.front().durationSource==DemuxDurationSource::AudioCodecSamples);
            assert(a.packets.front().duration==1024&&a.packets.front().skipSamples.size()==10);
            assert(a.packets.front().skipSamples[0]==0&&a.packets.front().skipSamples[1]==4);
            // Unsupported multi-edit priming must fail closed, not trim each
            // independently opened fragment using a guessed timeline origin.
            auto complex=init;bool foundEdit=false;
            for(size_t n=4;n+12<complex.size();++n)if(complex[n]=='e'&&complex[n+1]=='l'&&complex[n+2]=='s'&&complex[n+3]=='t'){
                complex[n+11]=2;foundEdit=true;break;
            }
            assert(foundEdit);
            MP4DemuxResult rejected;assert(!demuxMP4Fragment(complex,first,rejected));
            assert(rejected.packets.empty()&&!rejected.error.empty());
        }
        std::cout<<(id?"audio":"video")<<" packets="<<a.packets.size()<<" nextDTS="<<b.packets.front().dts<<" timebase="<<a.tracks[0].timeBase.numerator<<'/'<<a.tracks[0].timeBase.denominator<<'\n';
        for(auto limits:{MP4DemuxLimits{16,8*1024*1024,65536,4096},MP4DemuxLimits{8*1024*1024,8,65536,4096},MP4DemuxLimits{8*1024*1024,8*1024*1024,1,4096},MP4DemuxLimits{8*1024*1024,8*1024*1024,65536,1}}){
            assert(!demuxMP4Fragment(init,first,a,limits));assert(a.tracks.empty()&&a.packets.empty()&&!a.error.empty());
        }
        first.pop_back();assert(!demuxMP4Fragment(init,first,a));assert(a.packets.empty());
        assert(!demuxMP4Fragment({},second,a));
        auto malformed=second;malformed[0]=0x7f;assert(!demuxMP4Fragment(init,malformed,a));
        assert(!demuxMP4Fragment(init,init,a));
        auto protectedInit=init;protectedInit.insert(protectedInit.end(),{0,0,0,8,'p','s','s','h'});
        assert(!demuxMP4Fragment(protectedInit,second,a));
        assert(!demuxMP4Fragment(init,second,a,{9*1024*1024,8*1024*1024,65536,4096}));
        int64_t end=0;size_t total=0;
        for(int segment=1;segment<=(id?5:4);++segment){
            auto bytes=read(root+"/segment-"+std::to_string(id)+"-0000"+std::to_string(segment)+".m4s");
            assert(demuxMP4Fragment(init,bytes,a));
            if(segment>1)assert(a.packets.front().dts==end);
            for(const auto& packet:a.packets)assert(packet.duration>0&&!packet.durationFromNextDTS);
            if(id&&segment>1)for(const auto& packet:a.packets)if(!packet.skipSamples.empty())
                assert(!packet.skipSamples[0]&&!packet.skipSamples[1]&&!packet.skipSamples[2]&&!packet.skipSamples[3]);
            end=a.packets.back().dts+a.packets.back().duration;total+=a.packets.size();
            if(id&&segment==5){assert(a.packets.size()==1);assert(a.packets[0].durationSource==DemuxDurationSource::AudioCodecSamples);assert(a.packets[0].duration==1024);}
        }
        assert(total==size_t(id?189:120));
        std::cout<<(id?"audio":"video")<<" all fragments packets="<<total<<" finalEnd="<<end<<'\n';
    }
    std::cout<<"PASS finite video/audio fragment demux, exact timestamps, truncation and quotas\n";
}
