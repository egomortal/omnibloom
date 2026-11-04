#define SDL_MAIN_HANDLED
#include <SDL2/SDL.h>
#include <stdio.h>
#include <unistd.h>
int main()
{
    FILE* log = fopen("/data/omni/display-probe.txt", "w");
    if (!log) return 1;
    auto report = [&](const char* text) { fprintf(log, "%s\n", text); fflush(log); fsync(fileno(log)); };
    SDL_SetMainReady();
#ifdef OMNI_DISPLAY_PREVIEW
    // Only this separate diagnostic binary reads the test mode selector.
    char requested[16] = {};
    if (FILE* mode = fopen("/data/omni/display-test-mode.txt", "r")) {
        if (fscanf(mode, "%15s", requested) == 1) SDL_setenv("OMNI_SDL_HEIGHT", requested, 1);
        fclose(mode);
    }
#endif
    report("Minimal SDL framebuffer test, no WebKit or GPU libraries");
    if (SDL_Init(SDL_INIT_VIDEO)) { report(SDL_GetError()); fclose(log); return 2; }
    SDL_DisplayMode desktop {};
    if (SDL_GetDesktopDisplayMode(0, &desktop)) { report(SDL_GetError()); SDL_Quit(); fclose(log); return 3; }
    fprintf(log, "backend=%s desktop=%dx%d refresh=%d\n", SDL_GetCurrentVideoDriver(), desktop.w, desktop.h, desktop.refresh_rate);
    int count = SDL_GetNumDisplayModes(0);
    fprintf(log, "mode-count=%d\n", count);
    for (int i = 0; i < count; ++i) {
        SDL_DisplayMode mode {};
        if (!SDL_GetDisplayMode(0, i, &mode)) fprintf(log, "mode[%d]=%dx%d@%d\n", i, mode.w, mode.h, mode.refresh_rate);
    }
    fflush(log); fsync(fileno(log));
    SDL_Window* window = SDL_CreateWindow("Omni display test", 0, 0, desktop.w, desktop.h, SDL_WINDOW_SHOWN | SDL_WINDOW_FULLSCREEN_DESKTOP);
    SDL_Surface* screen = window ? SDL_GetWindowSurface(window) : nullptr;
    if (!screen) { report(SDL_GetError()); SDL_Quit(); fclose(log); return 3; }
    SDL_FillRect(screen, nullptr, SDL_MapRGB(screen->format, 20, 80, 110));
    if (SDL_UpdateWindowSurface(window)) report(SDL_GetError());
    else { report("PASS: display surface presented; test exits after three seconds"); SDL_Delay(3000); }
    SDL_DestroyWindow(window); SDL_Quit(); fclose(log);
    return 0;
}
