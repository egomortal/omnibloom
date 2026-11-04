// Kenney CC0 controller assets; vectors below serve browser navigation only.
// Included after the browser's fill() and text() helpers.
#include "../resources/controller-icons/OmniControllerAssets.h"

struct ControllerIconCache {
    SDL_Surface* surfaces[OmniControllerAssets::Count] {};
    bool attempted[OmniControllerAssets::Count] {};
    ~ControllerIconCache() { for (auto* surface : surfaces) SDL_FreeSurface(surface); }
    SDL_Surface* get(OmniControllerAssets::Id id) {
        if (attempted[id]) return surfaces[id];
        attempted[id] = true;
        const auto& source = OmniControllerAssets::images[id];
        png_image image {};
        image.version = PNG_IMAGE_VERSION;
        if (!png_image_begin_read_from_memory(&image, source.bytes, source.size)) {
            png_image_free(&image); return nullptr;
        }
        if (!image.width || !image.height || image.width > 256 || image.height > 256) {
            png_image_free(&image); return nullptr;
        }
        image.format = PNG_FORMAT_RGBA;
        auto* surface = SDL_CreateRGBSurfaceWithFormat(0, image.width, image.height, 32, SDL_PIXELFORMAT_RGBA32);
        if (!surface) { png_image_free(&image); return nullptr; }
        if (!png_image_finish_read(&image, nullptr, surface->pixels, surface->pitch, nullptr)) {
            SDL_FreeSurface(surface); png_image_free(&image); return nullptr;
        }
        png_image_free(&image);
        SDL_SetSurfaceBlendMode(surface, SDL_BLENDMODE_BLEND);
        surfaces[id] = surface;
        return surface;
    }
};

void controllerAsset(int x, int y, OmniControllerAssets::Id id, int size = 32) {
    static ControllerIconCache cache;
    auto* surface = cache.get(id);
    if (!surface) return;
    SDL_Rect destination { physical(x - size / 2), physical(y - size / 2), physical(size), physical(size) };
    SDL_BlitScaled(surface, nullptr, canvas, &destination);
}
void iconPixel(int x, int y, SDL_Color color, double coverage) {
    if (x<0 || y<0 || x>=canvas->w || y>=canvas->h || coverage<=0) return;
    auto* row=reinterpret_cast<uint32_t*>(static_cast<unsigned char*>(canvas->pixels)+y*canvas->pitch);
    uint32_t old=row[x]; unsigned a=static_cast<unsigned>(std::min(1.0,coverage)*255);
    auto blend=[&](unsigned foreground,unsigned background){return (foreground*a+background*(255-a)+127)/255;};
    row[x]=0xff000000 | (blend(color.r,(old>>16)&255)<<16) | (blend(color.g,(old>>8)&255)<<8) | blend(color.b,old&255);
}
void iconLine(int x1, int y1, int x2, int y2, SDL_Color color, int thickness = 2) {
    double ax=x1*displayScale,ay=y1*displayScale,bx=x2*displayScale,by=y2*displayScale;
    double dx=bx-ax,dy=by-ay,length=dx*dx+dy*dy,radius=thickness*displayScale/2;
    for(int y=int(std::floor(std::min(ay,by)-radius-1));y<=int(std::ceil(std::max(ay,by)+radius+1));++y)
        for(int x=int(std::floor(std::min(ax,bx)-radius-1));x<=int(std::ceil(std::max(ax,bx)+radius+1));++x){
            double t=length ? std::clamp(((x+0.5-ax)*dx+(y+0.5-ay)*dy)/length,0.0,1.0) : 0;
            double ex=x+0.5-ax-t*dx,ey=y+0.5-ay-t*dy;
            iconPixel(x,y,color,radius+0.5-std::sqrt(ex*ex+ey*ey));
        }
}
void iconCircle(int cx, int cy, int radius, SDL_Color color) {
    double r=radius*displayScale,x=cx*displayScale,y=cy*displayScale;
    for(int py=int(y-r-1);py<=int(y+r+1);++py) for(int px=int(x-r-1);px<=int(x+r+1);++px){
        double dx=px+0.5-x,dy=py+0.5-y;iconPixel(px,py,color,r+0.5-std::sqrt(dx*dx+dy*dy));
    }
}
void faceIcon(int x, int y, int button, bool ps) {
    using namespace OmniControllerAssets;
    const Id xbox[] = { xbox_a, xbox_b, xbox_x, xbox_y };
    const Id playStation[] = { ps_a, ps_b, ps_x, ps_y };
    if (button >= 0 && button < 4) controllerAsset(x, y, ps ? playStation[button] : xbox[button]);
}
void menuIcon(int x, int y, bool view = false) {
    using namespace OmniControllerAssets;
    controllerAsset(x, y, playStationIcons ? (view ? ps_view : ps_menu) : (view ? xbox_view : xbox_menu));
}
void stickIcon(int x, int y, bool right = false) {
    using namespace OmniControllerAssets;
    controllerAsset(x, y, playStationIcons ? (right ? ps_stick_r_press : ps_stick_l) : (right ? xbox_stick_r_press : xbox_stick_l));
}
void controllerHints() {
    const int y = height - 16;
    auto face = [&](int x, int button, const char* label) { faceIcon(x,y,button,playStationIcons); text(label,x+20,y-10,140,true); };
    if (settingsOpen) {
        controllerAsset(39,y,playStationIcons ? OmniControllerAssets::ps_dpad_horizontal : OmniControllerAssets::xbox_dpad_horizontal);
        text("Choose style",70,y-10,180,true); face(280,0,"Done"); face(410,1,"Back");
        return;
    }
    if (editing) {
        stickIcon(26,y); text("Select",48,y-10,120,true);
        face(185,0,"Type"); face(300,2,"Delete"); face(430,3,"Go"); face(535,1,"Cancel");
    } else {
        face(26,0,"Click"); face(155,3,"Address"); face(325,2,"New tab");
        controllerAsset(483,y,playStationIcons ? OmniControllerAssets::ps_lb : OmniControllerAssets::xbox_lb);
        controllerAsset(517,y,playStationIcons ? OmniControllerAssets::ps_rb : OmniControllerAssets::xbox_rb);
        text("Tabs",544,y-10,70,true); stickIcon(640,y,true); text("Close tab",667,y-10,120,true);
        face(800,1,"Back");
    }
    menuIcon(950,y,true); text("Settings",972,y-10,110,true);
    menuIcon(1135,y); text("Exit",1157,y-10,80,true);
}
void settingsPanel() {
    fill(340,220,600,264,{11,18,28,255}); fill(342,222,596,260,{26,37,52,255});
    fill(342,222,596,3,{119,221,94,255});
    text("Controller buttons",370,248,430);
    iconLine(907,248,919,260,{225,232,244,255}); iconLine(919,248,907,260,{225,232,244,255});
    for (int i = 0; i < 2; ++i) {
        int x = i ? 650 : 370;
        fill(x,310,250,120,playStationIcons == bool(i) ? SDL_Color{58,92,66,255} : SDL_Color{39,52,70,255});
        text(i ? "PlayStation" : "Xbox",x+20,326,210);
        for (int b=0;b<4;++b) faceIcon(x+35+b*57,389,b,i);
    }
    text("Left/right to choose a style.",370,451,400,true);
    faceIcon(817,460,0,playStationIcons); text("Done",838,451,70,true);
}
