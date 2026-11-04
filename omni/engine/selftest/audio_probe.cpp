#define SDL_MAIN_HANDLED
#include <SDL2/SDL.h>
#include <cstdio>
#include <vector>
#include <unistd.h>
int main() {
    FILE* output = fopen("/data/omni/audio-probe.txt", "w");
    if (!output) return 1;
    auto report = [&](const char* message) { fprintf(output,"%s\n",message); fflush(output); fsync(fileno(output)); };
    SDL_SetMainReady();
    if (SDL_Init(SDL_INIT_AUDIO | SDL_INIT_TIMER)) { report(SDL_GetError()); fclose(output); return 2; }
    SDL_AudioSpec requested {}, actual {};
    requested.freq = 48000; requested.channels = 2; requested.format = AUDIO_S16LSB; requested.samples = 1024;
    auto device = SDL_OpenAudioDevice(nullptr, 0, &requested, &actual, 0);
    if (!device) { report(SDL_GetError()); SDL_Quit(); fclose(output); return 3; }
    fprintf(output,"audio driver=%s rate=%d channels=%d format=%u samples=%u\n",SDL_GetCurrentAudioDriver(),actual.freq,actual.channels,actual.format,actual.samples);
    // Half a second of silence exercises queue submission without waking anyone.
    std::vector<unsigned char> silence(48000 * 2 * 2 / 2, 0);
    if (SDL_QueueAudio(device,silence.data(),silence.size())) { report(SDL_GetError()); SDL_CloseAudioDevice(device); SDL_Quit(); fclose(output); return 4; }
    unsigned before=SDL_GetQueuedAudioSize(device);
    SDL_PauseAudioDevice(device,0); SDL_Delay(800); SDL_PauseAudioDevice(device,1);
    unsigned after=SDL_GetQueuedAudioSize(device);
    fprintf(output,"queued-before=%u queued-after=%u\n",before,after);
    bool passed = before == silence.size() && !after;
    report(passed ? "PASS: silent audio queue drained" : "FAIL: audio queue did not drain");
    SDL_ClearQueuedAudio(device); SDL_CloseAudioDevice(device); SDL_Quit(); fclose(output);
    return passed ? 0 : 5;
}
