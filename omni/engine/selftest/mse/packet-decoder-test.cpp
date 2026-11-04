// SPDX-License-Identifier: GPL-3.0-or-later
#include "../../media/OmniPacketDecoder.h"
#include <cassert>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <iostream>
using namespace OmniMedia;
static std::vector<uint8_t> read(const std::string& path) {
    std::ifstream f(path,std::ios::binary);assert(f);return {std::istreambuf_iterator<char>(f),{}};
}
int main(int argc,char** argv) {
    assert(argc==2||argc==3);std::string root=argv[1];
    for(int id=0;id<2;++id) {
        auto init=read(root+"/init-"+std::to_string(id)+".mp4");
        std::vector<DemuxPacket> packets;DemuxTrack track;
        for(int segment=1;segment<=(id?5:4);++segment) {
            MP4DemuxResult result;
            assert(demuxMP4Fragment(init,read(root+"/segment-"+std::to_string(id)+"-0000"+std::to_string(segment)+".m4s"),result));
            if(segment==1)track=result.tracks[0];
            assert(result.tracks[0].extraData==track.extraData);
            for(auto& p:result.packets)packets.push_back(std::move(p));
        }
        PacketDecoder decoder;assert(decoder.configure(track));
        size_t reordered=0;
        for(const auto& p:packets)reordered+=p.pts!=p.dts;
        if(argc==3&&!id)assert(reordered>0);
        for(int cycle=0;cycle<2;++cycle) {
            size_t outputs=0,audioFrames=0,backpressure=0;int64_t last=-INT64_MAX;
            bool audible=false,sawHiddenTarget=false;size_t hiddenOutputs=0;
            int64_t hiddenStamp=packets.at(10).pts+(cycle?track.timeBase.denominator:0);
            auto receive=[&]() {
                DecodedOutput out;auto r=decoder.receive(out);
                if(r==PacketDecoder::Receive::Error)std::cerr<<decoder.error()<<'\n';
                assert(r!=PacketDecoder::Receive::Error);
                if(r==PacketDecoder::Receive::Output) {
                    assert(out.hasTimestamp&&out.timestamp>=last);last=out.timestamp;++outputs;
                    if(out.nonDisplaying) {
                        ++hiddenOutputs;
                        if(out.timestamp==hiddenStamp)sawHiddenTarget=true;
                        if(!id)assert(out.timestamp==hiddenStamp); // B-frame ownership, not latest packet
                    }
                    if(id) {
                        assert(out.kind==DecodedOutput::Kind::Audio&&!out.pcm.empty()&&out.rgba.empty());
                        assert(out.timeBase.numerator==1&&out.timeBase.denominator==48000);
                        assert(out.pcm.size()<=PacketDecoder::maxAudioFrames*2);
                        audioFrames+=out.pcm.size()/2;
                        for(auto sample:out.pcm)audible|=sample>100||sample< -100;
                        if(outputs==1)assert(out.timestamp==(cycle?48000:0)); // priming removed; offset retained
                    } else {
                        assert(out.kind==DecodedOutput::Kind::Video&&out.pcm.empty());
                        assert(out.rgba.size()==size_t(out.width)*out.height*4);
                        assert(out.opaque); // Both original H264 fixtures lack alpha.
                        for(size_t alpha=3;alpha<out.rgba.size();alpha+=4)
                            assert(out.rgba[alpha]==255); // Metadata matches actual pixels.
                    }
                }
                return r;
            };
            // Deliberately fill codec before receiving to exercise EAGAIN retry.
            size_t packetIndex=0;
            for(const auto& original:packets) {
                auto p=original;
                p.nonDisplaying=packetIndex++==10;
                // WebKit may express adjusted times in a different timescale.
                if(cycle) {
                    p.timeBase.denominator*=2;p.pts*=2;p.dts*=2;p.duration*=2;
                    assert(p.timeBase.numerator==1);
                    p.pts+=p.timeBase.denominator;p.dts+=p.timeBase.denominator;
                }
                for(int attempts=0;;++attempts) {
                    assert(attempts<256);auto r=decoder.submit(p);
                    if(r==PacketDecoder::Submit::Error)std::cerr<<decoder.error()<<'\n';
                    assert(r!=PacketDecoder::Submit::Error);
                    if(r==PacketDecoder::Submit::Accepted)break;
                    ++backpressure;assert(receive()==PacketDecoder::Receive::Output);
                }
            }
            for(int attempts=0;;++attempts) {
                assert(attempts<256);auto r=decoder.drain();
                assert(r!=PacketDecoder::Submit::Error);
                if(r==PacketDecoder::Submit::Accepted)break;
                assert(receive()==PacketDecoder::Receive::Output);
            }
            bool end=false;
            for(int attempts=0;attempts<256;++attempts) {
                auto r=receive();assert(r!=PacketDecoder::Receive::NeedInput);
                if(r==PacketDecoder::Receive::End){end=true;break;}
            }
            assert(end&&backpressure>0);
            assert(sawHiddenTarget&&hiddenOutputs>=1);
            if(!id)assert(hiddenOutputs==1);
            if(id)assert(audioFrames==192512&&audible);else assert(outputs==120);
            assert(receive()==PacketDecoder::Receive::End);
            std::cout<<(id?"audio":"video")<<" cycle="<<cycle<<" outputs="<<outputs<<" frames="<<audioFrames<<" retries="<<backpressure<<'\n';
            decoder.flush();
        }
        auto bad=packets.front();bad.trackId+=1;
        assert(decoder.submit(bad)==PacketDecoder::Submit::Error);
        assert(decoder.configure(track));
        bad=packets.front();bad.skipSamples.resize(9);
        assert(decoder.submit(bad)==PacketDecoder::Submit::Error);
        assert(decoder.configure(track));
        bad=packets.front();bad.bytes.resize(PacketDecoder::maxPacketBytes+1);
        assert(decoder.submit(bad)==PacketDecoder::Submit::Error);
        auto badTrack=track;badTrack.timeBase.denominator=0;
        assert(!decoder.configure(badTrack));
        badTrack=track;badTrack.extraData.resize(65537);
        assert(!decoder.configure(badTrack));
        badTrack=track;
        if(id)badTrack.channels=9;else badTrack.width=INT32_MAX;
        assert(!decoder.configure(badTrack));
    }
    puts("PASS persistent fragment packet decoding, retry, drain, flush and bounds");
}
