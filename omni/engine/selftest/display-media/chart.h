#pragma once
#include <cstdint>
#include <stdexcept>
#include <cstddef>

// Original diagnostic chart, no third-party fonts or media assets.
inline void omniChart(uint32_t* pixels, int width, int height, int pitchPixels)
{
    if (!pixels || width < 320 || height < 180 || width > 3840 || height > 2160 || pitchPixels < width)
        throw std::invalid_argument("chart geometry");
    // SDL_PIXELFORMAT_ABGR8888: little-endian RGBA bytes.
    const uint32_t white=0xffffffff, black=0xff000000;
    for (int y=0; y<height; ++y)
        for (int x=0; x<width; ++x)
            pixels[size_t(y)*pitchPixels+x] = 0xff20180c;
    auto rect = [&](int x,int y,int w,int h,uint32_t c) {
        for(int j=y;j<y+h && j<height;++j) for(int i=x;i<x+w && i<width;++i)
            if(i>=0 && j>=0) pixels[size_t(j)*pitchPixels+i]=c;
    };
    rect(0,0,width,2,white); rect(0,height-2,width,2,white);
    rect(0,0,2,height,white); rect(width-2,0,2,height,white);
    const uint32_t colors[]={0xff0000ff,0xff00ff00,0xffff0000,0xff00ffff,0xffffff00,0xffff00ff,white,black};
    for(int n=0;n<8;++n) rect(n*width/8,height/3,width/8,height/3,colors[n]);
    // Unique corner markers and inset outlines reveal overscan/cropping.
    rect(8,8,40,40,colors[0]); rect(width-48,8,40,40,colors[1]);
    rect(8,height-48,40,40,colors[2]); rect(width-48,height-48,40,40,white);
    for(int x=width/4;x<3*width/4;++x) rect(x,height/8,1,height/10,(x&1)?white:black);
    for(int y=3*height/4;y<7*height/8;++y) rect(width/4,y,width/2,1,(y&1)?white:black);
    const uint8_t digits[10][7]={{14,17,19,21,25,17,14},{4,12,4,4,4,4,14},{14,17,1,2,4,8,31},{30,1,1,14,1,1,30},{2,6,10,18,31,2,2},{31,16,16,30,1,1,30},{14,16,16,30,17,17,14},{31,1,2,4,8,8,8},{14,17,17,14,17,17,14},{14,17,17,15,1,1,14}};
    int scale=height/180, pen=width/2-27*scale;
    rect(pen-scale,height/2-5*scale,56*scale,10*scale,white);
    auto number=[&](int value) {
        int div=1000;
        for(int n=0;n<4;++n,div/=10) {
            int digit=value/div%10;
            for(int y=0;y<7;++y)for(int x=0;x<5;++x)
                if(digits[digit][y]&(1<<(4-x)))rect(pen+x*scale, height/2-4*scale+y*scale,scale,scale,black);
            pen+=6*scale;
        }
    };
    number(width); pen+=6*scale; number(height);
}
