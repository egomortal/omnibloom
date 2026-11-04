#include "chart.h"
#include <vector>
#include <cassert>
#include <cstdio>
#include <utility>
int main(int argc,char** argv) {
    for(auto size : {std::pair<int,int>{1920,1080},{2560,1440},{3840,2160}}) {
        int pitch=size.first+8;
        std::vector<uint32_t> data(size_t(pitch)*size.second+16,0x12345678);
        omniChart(data.data(),size.first,size.second,pitch);
        assert(data[0]==0xffffffff);
        assert(data[size_t(size.second-1)*pitch+size.first-1]==0xffffffff);
        for(int y=0;y<size.second;++y) for(int x=size.first;x<pitch;++x) assert(data[size_t(y)*pitch+x]==0x12345678);
        for(size_t i=size_t(pitch)*size.second;i<data.size();++i)assert(data[i]==0x12345678);
        if(argc==2 && size.first==3840) {
            FILE* file=fopen(argv[1],"wb"); assert(file);
            fprintf(file,"P6\n%d %d\n255\n",size.first,size.second);
            for(int y=0;y<size.second;++y)for(int x=0;x<size.first;++x) {
                auto pixel=data[size_t(y)*pitch+x];
                unsigned char rgb[]={static_cast<unsigned char>(pixel),static_cast<unsigned char>(pixel>>8),static_cast<unsigned char>(pixel>>16)};
                assert(fwrite(rgb,1,3,file)==3);
            }
            assert(!fclose(file));
        }
    }
    bool rejected=false; try {omniChart(nullptr,3840,2160,3840);} catch(const std::invalid_argument&){rejected=true;}
    assert(rejected); puts("PASS chart geometry, corner markers and pitch guards: 1080/1440/2160");
}
