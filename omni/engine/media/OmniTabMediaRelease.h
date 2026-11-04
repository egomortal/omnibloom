// OMNI_TAB_MEDIA_RELEASE_V1: a background tab's video gives its hardware decoder back.
// SPDX-License-Identifier: GPL-3.0-or-later
//
// The console test (tabmem-1: 16 real sites in tabs) found the shell's free memory going from 646
// to 179 MiB at the fifth tab: autoplaying videos on a page (CNN) held all four channels of the UI
// process's decode service, ~117 MiB each (decoder + shared slots), and kept them after the tab
// went to the background. The pages themselves cost the shell almost nothing.
//
// Who holds a decoder: every OmniMedia::PacketDecoder that decodes video on the hardware owns one
// Hw::Client, i.e. one channel of the service (Wire::maxChannels = 4); the service creates the
// decoder and its shared memory when the client configures and deletes both when the client goes
// (releaseStream). Players own the PacketDecoders: OmniProgressivePlayer (one), the MSE source (one
// per video track, plus one opened ahead for a quality switch) and OmniHlsPlayer (one). So the
// release is done by the players, in the web process, at the stream level.
//
// When: the shell hides a background tab's view (WKViewSetVisible false in activate()), WebKit
// tells each media player (setPageIsVisible(false)). A player with a hardware video stream that
// stays hidden for graceMs (a quick flick through the tabs touches nothing):
//   * pauses itself (playbackStateChanged: the element pauses too, with its pause event), unless
//     it plays audibly and /data/omni/tab-media-keep-audible.flag exists;
//   * releases the hardware stream (PacketDecoder::releaseHardware): the shell gets the memory
//     back at once. Its frames still in decode slots and the shell's video plane go first.
// Audio-only media has no video decoder and is never touched: music keeps playing in the
// background. Video in a background tab is paused (as mobile Safari/Chrome do), because a paused
// stream can be released and restarted exactly (a seek to the playhead); playing its audio on
// without a video decoder would need a video-less clock path in the MSE player that has never run.
// Shown again: the hardware stream opens again (only if a channel is free now; else once a second,
// and after giveUpMs the software decoder takes over, as when the hardware fails), the stream
// restarts at the playhead from a keyframe, and a video this gate paused plays on.
// If the page starts a released video again while hidden, it is paused again.
// Never touched: the visible tab (so the tab in fullscreen, too: switching tabs leaves fullscreen
// first), media in documents served from 127.0.0.1 / localhost (the Media downloads tab, Omni's
// local test pages), software-decoded media.
// Kill switch: /data/omni/tab-media-release-disabled.flag (host: OMNI_TAB_MEDIA_RELEASE=0), read at
// most every 2 s: nothing is released any more (released streams still come back when shown).
// Log lines: "OMNI TABMEDIA: ..." (at most 200 per process).
#pragma once
#include <chrono>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <unistd.h>

namespace OmniMedia::TabMedia {
inline double nowMs()
{
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
inline bool flagFile(const char* path)
{
#ifdef __PROSPERO__
    return access(path, F_OK) == 0;
#else
    (void)path; return false;
#endif
}
inline bool enabled()
{
    static double at = -1e12; static bool value = true;
    const double now = nowMs();
    if (now - at < 2000) return value;
    at = now;
    if (const char* env = getenv("OMNI_TAB_MEDIA_RELEASE")) value = env[0] != '0';
    else value = !flagFile("/data/omni/tab-media-release-disabled.flag");
    return value;
}
inline bool keepAudible()
{
    static double at = -1e12; static bool value = false;
    const double now = nowMs();
    if (now - at < 2000) return value;
    at = now;
    value = flagFile("/data/omni/tab-media-keep-audible.flag");
    return value;
}
inline void log(const char* format, ...) __attribute__((format(printf, 1, 2)));
inline void log(const char* format, ...)
{
    static unsigned lines;
    if (lines++ >= 200) return;
    fprintf(stderr, "OMNI TABMEDIA: ");
    va_list args;
    va_start(args, format);
    vfprintf(stderr, format, args);
    va_end(args);
    fputc('\n', stderr);
    fflush(stderr);
}
// Pure state, one per player (reset with each load). The player calls tick() once per tick and
// acts on the answer; released()/repaused()/retryLater()/reacquired() report what it did.
struct Gate {
    static constexpr double graceMs = 1500;
    static constexpr double retryMs = 1000;
    static constexpr double giveUpMs = 6000;
    enum class Act { None, Release, Repause, Reacquire };
    double hiddenSince = -1, visibleSince = -1, retryAt = 0;
    bool isReleased = false, pausedByUs = false, exempt = false, exemptKnown = false;
    unsigned releases = 0, retries = 0;
    // hwVideo: a hardware video stream is open (and the media can restart at the playhead).
    // audible: has audio, not muted, volume above 0.
    Act tick(double now, bool visible, bool hwVideo, bool paused, bool audible)
    {
        if (visible) {
            hiddenSince = -1;
            if (!isReleased) { visibleSince = -1; return Act::None; }
            if (visibleSince < 0) visibleSince = now;
            return now >= retryAt ? Act::Reacquire : Act::None;
        }
        visibleSince = -1;
        if (hiddenSince < 0) hiddenSince = now;
        if (isReleased) return paused ? Act::None : Act::Repause;
        if (!hwVideo || exempt || now - hiddenSince < graceMs || !enabled()) return Act::None;
        if (!paused && audible && keepAudible()) return Act::None;
        return Act::Release;
    }
    void released(bool wasPlaying) { isReleased = true; pausedByUs = wasPlaying; retryAt = 0; retries = 0; ++releases; }
    void repaused() { pausedByUs = true; }
    bool giveUp(double now) const { return visibleSince >= 0 && now - visibleSince >= giveUpMs; }
    void retryLater(double now) { retryAt = now + retryMs; ++retries; }
    // The stream decodes again: true when it should play on (this gate paused it).
    bool reacquired() { const bool resume = pausedByUs; isReleased = false; pausedByUs = false; visibleSince = -1; retryAt = 0; retries = 0; return resume; }
};
}
