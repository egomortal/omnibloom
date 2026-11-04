// SPDX-License-Identifier: GPL-3.0-or-later
// v53: BGRA output must be the RGBA output with R and B exchanged, frame for frame.
#include "../../media/OmniPacketDecoder.h"
#include <cassert>
#include <cstdio>
#include <fstream>
#include <iterator>
using namespace OmniMedia;
static std::vector<uint8_t> read(const std::string& path) {
    std::ifstream f(path,std::ios::binary);assert(f);return {std::istreambuf_iterator<char>(f),{}};
}
static std::vector<DecodedOutput> decodeAll(const DemuxTrack& track,const std::vector<DemuxPacket>& packets,PacketDecoder::PixelOrder order) {
    PacketDecoder d;d.setVideoPixelOrder(order);assert(d.configure(track));
    std::vector<DecodedOutput> frames;
    auto pull=[&]{for(;;){DecodedOutput o;auto r=d.receive(o);assert(r!=PacketDecoder::Receive::Error);
        if(r!=PacketDecoder::Receive::Output)return;frames.push_back(std::move(o));}};
    for(auto& p:packets){while(d.submit(p)==PacketDecoder::Submit::NeedOutput)pull();pull();}
    while(d.drain()==PacketDecoder::Submit::NeedOutput)pull();pull();
    return frames;
}
int main(int,char** argv) {
    std::string root=argv[1];auto init=read(root+"/init-0.mp4");
    std::vector<DemuxPacket> packets;DemuxTrack track;
    for(int s=1;s<=4;++s){MP4DemuxResult r;assert(demuxMP4Fragment(init,read(root+"/segment-0-0000"+std::to_string(s)+".m4s"),r));
        if(s==1)track=r.tracks[0];for(auto& p:r.packets)packets.push_back(std::move(p));}
    auto rgba=decodeAll(track,packets,PacketDecoder::PixelOrder::RGBA);
    auto bgra=decodeAll(track,packets,PacketDecoder::PixelOrder::BGRA);
    assert(!rgba.empty()&&rgba.size()==bgra.size());
    size_t differing=0;
    for(size_t i=0;i<rgba.size();++i){
        auto& a=rgba[i];auto& b=bgra[i];
        assert(!a.bgra&&b.bgra&&a.timestamp==b.timestamp&&a.rgba.size()==b.rgba.size());
        for(size_t p=0;p<a.rgba.size();p+=4){
            assert(a.rgba[p]==b.rgba[p+2]&&a.rgba[p+1]==b.rgba[p+1]&&a.rgba[p+2]==b.rgba[p]&&b.rgba[p+3]==255);
            differing+=a.rgba[p]!=a.rgba[p+2];
        }
    }
    assert(differing>0); // fixture really has colour, so the swap was exercised
    printf("PASS pixel order: %zu frames, BGRA == RGBA with R/B swapped (%zu coloured pixels)\n",rgba.size(),differing);
}
