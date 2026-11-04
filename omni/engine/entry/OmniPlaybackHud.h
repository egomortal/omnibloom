// Fixed-buffer production HUD. No SDL/font dependency, I/O, clocks or allocation.
#pragma once
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <algorithm>
namespace OmniPlaybackHud {
struct Sample {
    uint64_t completed=0,repeats=0,drops=0,decoderErrors=0;
    int64_t completionUs=0,audio=-1;
    int width=0,height=0,codec=-1;
    bool active=false,decoderFailed=false,hdr=false;
};
class Panel {
public:
    static constexpr int columns=180, rows=112, maxScale=3;
    uint32_t pixels[columns*rows*maxScale*maxScale] {};
    char text[256] {};
    int scale=2;
    uint32_t background=0xff111b24, ink=0xffe8eef4, accent=0xff73e3b0;
    bool enabled=false;
    void reset() { primed=false; rendered=false; }
    int width() const { return columns*scale; }
    int height() const { return rows*scale; }
    // Caller supplies an existing UI-loop timestamp. Unsigned subtraction handles wrap.
    bool due(uint32_t now) const { return enabled && (!rendered || uint32_t(now-updated)>=1000); }
    bool update(uint32_t now,const Sample& s) {
        if (!due(now)) return false;
        char fps[32]; std::strcpy(fps,"-- FPS");
        if (primed && s.completed>=previous.completed && s.completionUs>previous.completionUs) {
            const double rate=double(s.completed-previous.completed)*1000000/double(s.completionUs-previous.completionUs);
            std::snprintf(fps,sizeof fps,"%.2f FPS",rate);
        } else if (primed && s.completed==previous.completed) std::strcpy(fps,"0.00 FPS");
        char resolution[40],audio[32],decoder[32];
        std::snprintf(decoder,sizeof decoder,"%llu",(unsigned long long)s.decoderErrors);
        if(s.active&&s.width>0&&s.height>0)std::snprintf(resolution,sizeof resolution,"%dx%d",s.width,s.height);
        else std::strcpy(resolution,"NO ACTIVE VIDEO");
        if(s.audio>=0)std::snprintf(audio,sizeof audio,"%llu",(unsigned long long)s.audio);
        else std::strcpy(audio,"N/A");
        const char* codec=s.codec==0?"H.264":s.codec==1?"HEVC":s.codec==2?"VP9":"N/A";
        std::snprintf(text,sizeof text,"%s\nHDR: %s\n%s\n\nDROPS: %llu\nREPEATS: %llu\n\nDECODER: %s\nAUDIO: %s\nCODEC: %s",
            resolution,s.hdr?"ON":"OFF",fps,(unsigned long long)s.drops,(unsigned long long)s.repeats,
            decoder,audio,codec);
        previous=s;primed=true;rendered=true;updated=now;
        std::fill(pixels,pixels+width()*height(),background);
        for(int y=0;y<height();++y)for(int x=0;x<2*scale;++x)pixels[y*width()+x]=accent;
        int x=8,y=6;
        for(const char* c=text;*c;++c){if(*c=='\n'){x=8;y+=10;continue;}glyph(*c,x,y);x+=6;}
        return true;
    }
private:
    Sample previous;
    bool primed=false,rendered=false;
    uint32_t updated=0;
    void glyph(char c,int x,int y) {
        // Compact built-in 5x7 bitmap alphabet: no font loading/raster allocation.
        static constexpr unsigned char digits[10][5]={
            {62,81,73,69,62},{0,66,127,64,0},{66,97,81,73,70},{33,65,69,75,49},{24,20,18,127,16},
            {39,69,69,69,57},{60,74,73,73,48},{1,113,9,5,3},{54,73,73,73,54},{6,73,73,41,30}};
        static constexpr unsigned char letters[26][5]={
            {126,17,17,17,126},{127,73,73,73,54},{62,65,65,65,34},{127,65,65,34,28},{127,73,73,73,65},
            {127,9,9,9,1},{62,65,73,73,122},{127,8,8,8,127},{0,65,127,65,0},{32,64,65,63,1},
            {127,8,20,34,65},{127,64,64,64,64},{127,2,12,2,127},{127,4,8,16,127},{62,65,65,65,62},
            {127,9,9,9,6},{62,65,81,33,94},{127,9,25,41,70},{70,73,73,73,49},{1,1,127,1,1},
            {63,64,64,64,63},{31,32,64,32,31},{63,64,56,64,63},{99,20,8,20,99},{7,8,112,8,7},{97,81,73,69,67}};
        static constexpr unsigned char colon[5]={0,54,54,0,0},dot[5]={0,96,96,0,0},slash[5]={32,16,8,4,2},dash[5]={8,8,8,8,8};
        if(c>='a'&&c<='z')c-=32;
        const unsigned char* bits=c>='0'&&c<='9'?digits[c-'0']:c>='A'&&c<='Z'?letters[c-'A']:c==':'?colon:c=='.'?dot:c=='/'?slash:c=='-'?dash:nullptr;
        if(!bits)return;
        for(int col=0;col<5;++col)for(int row=0;row<7;++row)if(bits[col]&(1<<row))
            for(int j=0;j<scale;++j)for(int i=0;i<scale;++i){int px=(x+col)*scale+i,py=(y+row)*scale+j;if(px<width()&&py<height())pixels[py*width()+px]=ink;}
    }
};
}
