#define SDL_MAIN_HANDLED
#include <SDL2/SDL.h>
#include "chart.h"
#include <cstdio>
#include <initializer_list>
#include <unistd.h>
extern "C" int sceSystemServiceLoadExec(const char*, const char* const*);

int main() {
    FILE* log=fopen("/data/omni/display-chart.txt","w"); if(!log)return 1;
    SDL_SetMainReady(); int status=0;
    // Fixed isolated sequence; no production selector or system setting changes.
    for(const char* mode : {"2160","1080"}) {
        SDL_setenv("OMNI_SDL_HEIGHT",mode,1);
        if(SDL_Init(SDL_INIT_VIDEO)) {fprintf(log,"INIT FAIL %s\n",SDL_GetError());status=2;break;}
        SDL_DisplayMode desktop{};
        if(SDL_GetDesktopDisplayMode(0,&desktop)) {status=3;SDL_Quit();break;}
        fprintf(log,"requested=%s SDL=%dx%d nominalHz=%d HDMI timing=NOT QUERIED\n",mode,desktop.w,desktop.h,desktop.refresh_rate);
        SDL_Window* window=SDL_CreateWindow("Omni isolated display chart",0,0,desktop.w,desktop.h,SDL_WINDOW_SHOWN|SDL_WINDOW_FULLSCREEN_DESKTOP);
        SDL_Surface* surface=window?SDL_GetWindowSurface(window):nullptr;
        if(!surface || surface->format->format!=SDL_PIXELFORMAT_ABGR8888) status=4;
        else if(SDL_LockSurface(surface)) status=5;
        else {
            omniChart(static_cast<uint32_t*>(surface->pixels),surface->w,surface->h,surface->pitch/4);
            SDL_UnlockSurface(surface);
            if(SDL_UpdateWindowSurface(window)) {
                // A failed flip does not establish that scanout released buffers.
                // Exit through the foreground service without manually freeing them.
                fprintf(log,"FLIP FAIL %s; retaining buffers until process exit\n",SDL_GetError());
                fflush(log);fsync(fileno(log));fclose(log);
                sceSystemServiceLoadExec("exit",nullptr);
                _exit(6);
            }
            else {fprintf(log,"SUBMITTED %dx%d visual correctness=UNVERIFIED\n",surface->w,surface->h);fflush(log);fsync(fileno(log));SDL_Delay(2000);}
        }
        if(status)fprintf(log,"FAIL %d %s\n",status,SDL_GetError());
        if(window)SDL_DestroyWindow(window);
        SDL_Quit();
        if(status)break;
    }
    fprintf(log,"sequence complete status=%d; 1080 reinitialization is not proof of original HDMI restoration\n",status);
    fflush(log);fsync(fileno(log));fclose(log);
    // Same foreground exit route as Omni; no daemon execution intended.
    sceSystemServiceLoadExec("exit",nullptr);
    return status;
}
