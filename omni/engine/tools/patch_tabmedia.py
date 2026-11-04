#!/usr/bin/env python3
"""OMNI_TAB_MEDIA_RELEASE_V1: applies the tab media release onto a full copy of dl2-candidate-52
(plus the baseline copies of entry/OmniMSEPlayer.cpp, entry/OmniMSESource.cpp, entry/OmniMSESource.h,
entry/OmniHlsPlayer.cpp and media/OmniPacketDecoder.h). Every anchor must match exactly once.
Line endings: each file keeps its own (CRLF or LF).  Usage: patch_tabmedia.py <overlay folder>"""
import sys
from pathlib import Path
root = Path(sys.argv[1])

GATE = r'''// OMNI_TAB_MEDIA_RELEASE_V1: a background tab's video gives its hardware decoder back.
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
'''

EXEMPT = r'''    // OMNI_TAB_MEDIA_RELEASE_V1: media in a document served from this console (the Media downloads
    // tab, Omni's local pages) is never paused or released.
    bool tabMediaExempt()
    {
        RefPtr player = m_player.get();
        if (!player) return false;
        for (auto& candidate : HTMLMediaElement::allMediaElements()) {
            if (candidate->player() != player.get()) continue;
            const String host = candidate->document().url().host().toString();
            return host == "127.0.0.1"_s || host == "localhost"_s;
        }
        return false;
    }
'''

PROG_TICK = EXEMPT + r'''    // OMNI_TAB_MEDIA_RELEASE_V1 (OmniTabMediaRelease.h): hidden 1.5 s with a hardware stream: paused
    // and the decode channel closed; shown again: open again, a seek to the playhead, play on.
    void tabMediaTick()
    {
        using Act = OmniMedia::TabMedia::Gate::Act;
        if (!m_decoder || !m_cache) return;
        const double now = OmniMedia::TabMedia::nowMs();
        const bool hidden = !m_visible;
        if (hidden && !m_tabMedia.exemptKnown) { m_tabMedia.exemptKnown = true; m_tabMedia.exempt = tabMediaExempt(); }
        const bool hwVideo = hidden && m_haveMetadata && m_decoder->usingHardware() && (m_cache->ranges() || m_cache->wholeComplete());
        const bool audible = hasAudio() && !m_muted && m_volume > 0;
        switch (m_tabMedia.tick(now, m_visible, hwVideo, m_paused, audible)) {
        case Act::None:
            return;
        case Act::Release: {
            const bool wasPlaying = !m_paused;
            if (wasPlaying) pause();
            holeReset();   // the shell's plane and the pictures still in decode slots go before the stream
            m_packet.reset(); m_output.reset(); m_drainSent = false; m_decoderEnded = false;
            const bool released = m_decoder->releaseHardware();
            m_tabMedia.released(wasPlaying);
            OmniMedia::TabMedia::log("progressive %dx%d: page hidden: %s, %s at %.3f s", int(m_size.width()), int(m_size.height()),
                wasPlaying ? "paused" : "already paused", released ? "hardware decoder released" : "no hardware decoder", m_position);
            return;
        }
        case Act::Repause:
            pause(); m_tabMedia.repaused();
            OmniMedia::TabMedia::log("progressive: played while hidden and released: paused again at %.3f s", m_position);
            return;
        case Act::Reacquire: {
            const bool ok = m_decoder->reacquireHardware();
            if (!ok && !m_tabMedia.giveUp(now)) {
                if (!m_tabMedia.retries) OmniMedia::TabMedia::log("progressive: shown again: no decode channel free; trying again every second");
                m_tabMedia.retryLater(now);
                return;
            }
            if (!ok) m_decoder->abandonHardware();
            const bool resume = m_tabMedia.reacquired();
            if (!m_ended && m_pipeline && m_haveMetadata) seekInternal(m_position);   // from a keyframe; pictures before the playhead are dropped
            OmniMedia::TabMedia::log("progressive %dx%d: shown again: %s at %.3f s%s", int(m_size.width()), int(m_size.height()),
                ok ? "hardware decoder open again" : "no channel for 6 s: software decoder", m_position, resume ? ", playing on" : "");
            if (resume) play();
            return;
        }
        }
    }
'''

MSE_TICK = EXEMPT + r'''    // OMNI_TAB_MEDIA_RELEASE_V1 (OmniTabMediaRelease.h): hidden 1.5 s with a hardware video stream:
    // paused and the video tracks' decode channels closed; shown again: open again, the video decodes
    // again from the playhead (resyncVideo, as after a hidden paced stream), play on. False: this
    // tick stops (the presentation changed).
    bool tabMediaTick(OmniMSESource& source)
    {
        using Act = OmniMedia::TabMedia::Gate::Act;
        const double now = OmniMedia::TabMedia::nowMs();
        const bool hidden = !m_visible;
        if (hidden && !m_tabMedia.exemptKnown) { m_tabMedia.exemptKnown = true; m_tabMedia.exempt = tabMediaExempt(); }
        const bool hwVideo = hidden && !m_tabMedia.isReleased && source.videoUsingHardware();
        const bool audible = hasAudio() && !m_muted && m_volume > 0;
        switch (m_tabMedia.tick(now, m_visible, hwVideo, m_paused, audible)) {
        case Act::None:
            return true;
        case Act::Release: {
            const bool wasPlaying = !m_paused;
            if (wasPlaying) pause();
            holePunchReset();   // the shell's plane and the hole pictures go before the streams
            const bool released = source.releaseVideoHardware();
            m_tabMedia.released(wasPlaying);
            OmniMedia::TabMedia::log("MSE %dx%d: page hidden: %s, %s at %.3f s", int(m_size.width()), int(m_size.height()),
                wasPlaying ? "paused" : "already paused", released ? "hardware decoder(s) released" : "no hardware decoder", m_position);
            return true;
        }
        case Act::Repause:
            pause(); m_tabMedia.repaused();
            OmniMedia::TabMedia::log("MSE: played while hidden and released: paused again at %.3f s", m_position);
            return true;
        case Act::Reacquire: {
            const bool giveUp = m_tabMedia.giveUp(now);
            if (!source.reacquireVideoHardware(giveUp)) {
                if (!m_tabMedia.retries) OmniMedia::TabMedia::log("MSE: shown again: no decode channel free; trying again every second");
                m_tabMedia.retryLater(now);
                return true;
            }
            const bool resume = m_tabMedia.reacquired();
            source.resyncVideo();
            OmniMedia::TabMedia::log("MSE %dx%d: shown again: %s at %.3f s%s", int(m_size.width()), int(m_size.height()),
                giveUp ? "decoders back (a track without a free channel for 6 s went to software)" : "hardware decoder(s) open again", m_position, resume ? ", playing on" : "");
            if (resume) play();
            return false;
        }
        }
        return true;
    }
'''

HLS_TICK = EXEMPT + r'''    // OMNI_TAB_MEDIA_RELEASE_V1 (OmniTabMediaRelease.h): hidden 1.5 s with a hardware video stream:
    // paused and its decode channel closed; shown again: open again, restartAt(playhead), play on.
    // False: this tick stops.
    bool tabMediaTick()
    {
        using Act = OmniMedia::TabMedia::Gate::Act;
        auto& v = m_tracks[0];
        const double now = OmniMedia::TabMedia::nowMs();
        const bool hidden = !m_visible;
        if (hidden && !m_tabMedia.exemptKnown) { m_tabMedia.exemptKnown = true; m_tabMedia.exempt = tabMediaExempt(); }
        const bool hwVideo = hidden && v.configured && v.decoder->usingHardware();
        const bool audible = hasAudio() && !m_muted && m_volume > 0;
        switch (m_tabMedia.tick(now, m_visible, hwVideo, m_paused, audible)) {
        case Act::None:
            return true;
        case Act::Release: {
            const bool wasPlaying = !m_paused;
            if (wasPlaying) pause();
            v.retry.reset(); v.ended = false;
            const bool released = v.decoder->releaseHardware();
            m_tabMedia.released(wasPlaying);
            OmniMedia::TabMedia::log("HLS %dx%d: page hidden: %s, %s at %.3f s", int(m_size.width()), int(m_size.height()),
                wasPlaying ? "paused" : "already paused", released ? "hardware decoder released" : "no hardware decoder", m_position);
            return true;
        }
        case Act::Repause:
            pause(); m_tabMedia.repaused();
            OmniMedia::TabMedia::log("HLS: played while hidden and released: paused again at %.3f s", m_position);
            return true;
        case Act::Reacquire: {
            const bool ok = v.decoder->reacquireHardware();
            if (!ok && !m_tabMedia.giveUp(now)) {
                if (!m_tabMedia.retries) OmniMedia::TabMedia::log("HLS: shown again: no decode channel free; trying again every second");
                m_tabMedia.retryLater(now);
                return true;
            }
            if (!ok) v.decoder->abandonHardware();
            const bool resume = m_tabMedia.reacquired();
            if (m_session && m_haveMetadata) restartAt(m_position);
            OmniMedia::TabMedia::log("HLS %dx%d: shown again: %s at %.3f s%s", int(m_size.width()), int(m_size.height()),
                ok ? "hardware decoder open again" : "no channel for 6 s: software decoder", m_position, resume ? ", playing on" : "");
            if (resume) play();
            return false;
        }
        }
        return true;
    }
'''

EDITS = {
 'media/OmniPacketDecoder.h': [
  ('    void swap(PacketDecoder&);\n',
   '    void swap(PacketDecoder&);\n'
   '    // OMNI_TAB_MEDIA_RELEASE_V1 (OmniTabMediaRelease.h): a background tab\'s video gives its hardware\n'
   '    // decoder back. releaseHardware(): closes this stream\'s decode channel (the UI process deletes the\n'
   '    // decoder and its shared memory at once); the configuration and the software decoder (if any)\n'
   '    // stay. True: a hardware stream was open. While released the caller must not submit, drain or\n'
   '    // receive (flush() is safe).\n'
   '    bool releaseHardware();\n'
   '    bool hardwareReleased() const;\n'
   '    // Opens the hardware stream again, only if a decode channel is free now. True: hardware again (or\n'
   '    // nothing was released); the caller restarts the stream at a keyframe (a seek). False: nothing changed.\n'
   '    bool reacquireHardware();\n'
   '    // No channel came free: the software decoder from the next keyframe (a hardware-only stream fails).\n'
   '    void abandonHardware();\n'),
 ],
 'media/OmniPacketDecoder.cpp': [
  ('    bool hardwareOnly = false;\n',
   '    bool hardwareOnly = false;\n'
   '    bool released = false; // OMNI_TAB_MEDIA_RELEASE_V1: the hardware stream was given back (releaseHardware)\n'),
  ('bool SwitchHandoff::enabled() { // OMNI_MSE_SWITCH_HANDOFF_V1\n',
   'bool PacketDecoder::releaseHardware() { // OMNI_TAB_MEDIA_RELEASE_V1\n'
   '    if (!state || !state->hw) return false;\n'
   '    auto& s = *state;\n'
   '    s.hw.reset();   // ~Client: the channel closes; the service deletes the decoder and frees its memory\n'
   '    if (s.codec) { avcodec_flush_buffers(s.codec); av_frame_unref(s.frame); }\n'
   '    s.draining = s.codecEnded = s.ended = false;\n'
   '    s.awaitKeyFrame = false;\n'
   '    s.released = true;\n'
   '    return true;\n'
   '}\n'
   'bool PacketDecoder::hardwareReleased() const { return state && state->released; } // OMNI_TAB_MEDIA_RELEASE_V1\n'
   'bool PacketDecoder::reacquireHardware() { // OMNI_TAB_MEDIA_RELEASE_V1\n'
   '    if (!state || !state->released) return true;\n'
   '    auto& s = *state;\n'
   '    if (!Hw::Client::serviceAvailable()) return false;\n'
   '    auto hw = std::make_unique<Hw::Client>();\n'
   '    hw->setTargetSize(targetWidth, targetHeight);\n'
   '    hw->setHolePunch(holePunch);\n'
   '    hw->setConnectNoWait(true);   // a free channel now, or try again later (never the 2 s wait on this thread)\n'
   '    const Hw::Codec hwCodec = s.track.codec == DemuxCodec::VP9 ? Hw::Codec::VP9 : s.track.codec == DemuxCodec::HEVC ? Hw::Codec::HEVC : Hw::Codec::H264;\n'
   '    if (!hw->configure(hwCodec, s.track, pixelOrder == PixelOrder::BGRA)) return false;\n'
   '    s.hw = std::move(hw);\n'
   '    s.released = false;\n'
   '    s.draining = s.codecEnded = s.ended = false;\n'
   '    return true;\n'
   '}\n'
   'void PacketDecoder::abandonHardware() { // OMNI_TAB_MEDIA_RELEASE_V1\n'
   '    if (!state || !state->released) return;\n'
   '    auto& s = *state;\n'
   '    s.released = false;\n'
   '    if (s.hardwareOnly || !s.codec) { s.fail("hardware decoder not available again; no software decoder for this stream"); return; }\n'
   '    avcodec_flush_buffers(s.codec); av_frame_unref(s.frame);\n'
   '    s.draining = s.codecEnded = s.ended = false;\n'
   '    s.awaitKeyFrame = true;\n'
   '    fprintf(stderr, "OMNI DECODE: no decode channel came free; software decoder from the next keyframe\\n");\n'
   '}\n'
   'bool SwitchHandoff::enabled() { // OMNI_MSE_SWITCH_HANDOFF_V1\n'),
 ],
 'media/OmniHwService.h': [
  ('void diagnosticTraceDump();\n',
   'void diagnosticTraceDump();\n'
   '\n'
   '// OMNI_TAB_MEDIA_RELEASE_V1 (any shell thread): hardware decoders open now (channels with a stream)\n'
   '// and, in sharedBytes when given, the shared memory their slots use. Diagnostics (tab memory log).\n'
   'int openDecoderCount(size_t* sharedBytes = nullptr);\n'),
 ],
 'media/OmniHwService.cpp': [
  ('Channel channels[Wire::maxChannels];\n',
   'Channel channels[Wire::maxChannels];\n'
   'std::atomic<size_t> liveStreamBytes[Wire::maxChannels]; // OMNI_TAB_MEDIA_RELEASE_V1: shared memory of each open stream (0: none), for openDecoderCount\n'),
  ('void releaseStream(Channel& c)\n{\n',
   'void releaseStream(Channel& c)\n{\n'
   '    if (c.index >= 0 && unsigned(c.index) < unsigned(Wire::maxChannels)) liveStreamBytes[c.index].store(0, std::memory_order_relaxed); // OMNI_TAB_MEDIA_RELEASE_V1\n'),
  ('    note("channel %d open %dx%d %d-bit codec %u, shm %zu bytes", c.index, w, h, depth, in.a, c.shmSize);\n',
   '    if (c.index >= 0 && unsigned(c.index) < unsigned(Wire::maxChannels)) liveStreamBytes[c.index].store(c.shmSize, std::memory_order_relaxed); // OMNI_TAB_MEDIA_RELEASE_V1\n'
   '    note("channel %d open %dx%d %d-bit codec %u, shm %zu bytes", c.index, w, h, depth, in.a, c.shmSize);\n'),
  ('void shellLog(const char* message)\n{\n',
   'int openDecoderCount(size_t* sharedBytes) // OMNI_TAB_MEDIA_RELEASE_V1\n'
   '{\n'
   '    int open = 0; size_t bytes = 0;\n'
   '    for (auto& live : liveStreamBytes) { const size_t b = live.load(std::memory_order_relaxed); if (b) { ++open; bytes += b; } }\n'
   '    if (sharedBytes) *sharedBytes = bytes;\n'
   '    return open;\n'
   '}\n'
   '\n'
   'void shellLog(const char* message)\n{\n'),
 ],
 'entry/OmniTabMemory.h': [
  ('static void omniTmLog(const char* why)\n{\n'
   '    fprintf(stderr, "OMNI TABMEM: %s tabs=%zu loaded=%d limit=%d keep=%d shell_free=%lld MiB (refuse<%d unload<%d)\\n", why, tabs.size(),\n'
   '        omniTmLoadedCount(), omniF3Set.tabLimit, omniF3Set.keepLoaded, omniTmFree, omniF3Set.refuseMiB, omniF3Set.unloadMiB);\n',
   'static void omniTmLog(const char* why)\n{\n'
   '    size_t shm = 0; const int decoders = OmniMedia::Hw::openDecoderCount(&shm); // OMNI_TAB_MEDIA_RELEASE_V1\n'
   '    fprintf(stderr, "OMNI TABMEM: %s tabs=%zu loaded=%d limit=%d keep=%d shell_free=%lld MiB (refuse<%d unload<%d) hw_decoders=%d hw_shm=%zu MiB\\n", why, tabs.size(),\n'
   '        omniTmLoadedCount(), omniF3Set.tabLimit, omniF3Set.keepLoaded, omniTmFree, omniF3Set.refuseMiB, omniF3Set.unloadMiB, decoders, shm >> 20);\n'),
 ],
 'entry/OmniProgressivePlayer.cpp': [
  ('#include "../media/OmniHwPlatform.h"   // OMNI_PROGRESSIVE_HOLEPUNCH_V1: holeV5FlagEnabled, nowMs\n',
   '#include "../media/OmniHwPlatform.h"   // OMNI_PROGRESSIVE_HOLEPUNCH_V1: holeV5FlagEnabled, nowMs\n'
   '#include "../media/OmniTabMediaRelease.h" // OMNI_TAB_MEDIA_RELEASE_V1\n'
   '#include <WebCore/Document.h>          // OMNI_TAB_MEDIA_RELEASE_V1: the element\'s document URL\n'
   '#include <WebCore/NodeDocument.h>      // OMNI_TAB_MEDIA_RELEASE_V1: Node::document()\n'),
  ('        m_hw = false; m_hasVideoHw = false; m_drainSent = false; m_decoderEnded = false; m_awaitKey = false;\n',
   '        m_hw = false; m_hasVideoHw = false; m_drainSent = false; m_decoderEnded = false; m_awaitKey = false;\n'
   '        m_tabMedia = { }; // OMNI_TAB_MEDIA_RELEASE_V1\n'),
  ('        if (m_hw) { tickHw(*current); return; } // OMNI_PROGRESSIVE_HOLEPUNCH_V1\n',
   '        if (m_hw) { tabMediaTick(); if (m_hw && m_decoder) tickHw(*current); return; } // OMNI_PROGRESSIVE_HOLEPUNCH_V1; OMNI_TAB_MEDIA_RELEASE_V1: tabMediaTick\n'),
  ('        if (!m_decoder) return true;\n        unsigned outputs = 0;\n',
   '        if (!m_decoder || m_decoder->hardwareReleased()) return true; // OMNI_TAB_MEDIA_RELEASE_V1: not fed while given back\n        unsigned outputs = 0;\n'),
  ('    void holeReset()\n    {\n', PROG_TICK + '    void holeReset()\n    {\n'),
  ('    unsigned m_statsLines = 0;\n};\n',
   '    unsigned m_statsLines = 0;\n    OmniMedia::TabMedia::Gate m_tabMedia; // OMNI_TAB_MEDIA_RELEASE_V1\n};\n'),
 ],
 'entry/OmniMSEPlayer.cpp': [
  ('#include "../media/OmniHwPlatform.h"\n',
   '#include "../media/OmniHwPlatform.h"\n'
   '#include "../media/OmniTabMediaRelease.h" // OMNI_TAB_MEDIA_RELEASE_V1\n'
   '#include <WebCore/Document.h> // OMNI_TAB_MEDIA_RELEASE_V1: the element\'s document URL\n'
   '#include <WebCore/NodeDocument.h> // OMNI_TAB_MEDIA_RELEASE_V1: Node::document()\n'),
  ('        m_switchSeen = 0; m_switchPending = false; m_switchLogs = m_resyncLogs = 0;\n',
   '        m_switchSeen = 0; m_switchPending = false; m_switchLogs = m_resyncLogs = 0;\n'
   '        m_tabMedia = { }; // OMNI_TAB_MEDIA_RELEASE_V1\n'),
  ('        m_outputError = false;\n        auto pumpStart = MonotonicTime::now();\n',
   '        if (!tabMediaTick(*source)) return; // OMNI_TAB_MEDIA_RELEASE_V1\n'
   '        m_outputError = false;\n        auto pumpStart = MonotonicTime::now();\n'),
  ('    void holePunchReset()\n', MSE_TICK + '    void holePunchReset()\n'),
  ('    unsigned m_switchLogs = 0, m_resyncLogs = 0;\n',
   '    unsigned m_switchLogs = 0, m_resyncLogs = 0;\n'
   '    OmniMedia::TabMedia::Gate m_tabMedia; // OMNI_TAB_MEDIA_RELEASE_V1\n'),
 ],
 'entry/OmniMSESource.h': [
  ('    void resyncVideo();\n',
   '    void resyncVideo();\n'
   '    // OMNI_TAB_MEDIA_RELEASE_V1 (OmniTabMediaRelease.h): a background tab\'s video gives its hardware\n'
   '    // decoders back (the tracks\' streams and a stream opened ahead). Released video is not fed.\n'
   '    // reacquireVideoHardware(giveUp) true: every video track decodes again (giveUp: on software,\n'
   '    // or failing, where no channel came free); the caller then calls resyncVideo().\n'
   '    bool videoUsingHardware();\n'
   '    bool releaseVideoHardware();\n'
   '    bool reacquireVideoHardware(bool giveUp);\n'),
 ],
 'entry/OmniMSESource.cpp': [
  ('        for (auto id : video) { if (m_detached) return; reenqueSamples(id); }   // flush(id), then from currentTime()\n    }\n',
   '        for (auto id : video) { if (m_detached) return; reenqueSamples(id); }   // flush(id), then from currentTime()\n    }\n'
   '    // OMNI_TAB_MEDIA_RELEASE_V1 (OmniTabMediaRelease.h)\n'
   '    bool videoUsingHardware() {\n'
   '        for (auto& [id, track] : m_tracks)\n'
   '            if (OmniMedia::isVideoCodec(track->info.codec) && (track->decoder.usingHardware() || (track->next && track->next->usingHardware()))) return true;\n'
   '        return false;\n'
   '    }\n'
   '    bool releaseVideoHardware() {\n'
   '        bool any = false;\n'
   '        for (auto& [id, track] : m_tracks) {\n'
   '            if (!OmniMedia::isVideoCodec(track->info.codec)) continue;\n'
   '            track->output.reset();   // a picture still in its decode slot goes before the stream\n'
   '            if (track->next) { track->next.reset(); any = true; }   // a stream opened ahead holds a channel too\n'
   '            track->nextTried = false; track->switchWaitSince.reset();\n'
   '            if (track->decoder.releaseHardware()) any = true;\n'
   '        }\n'
   '        if (any) m_videoHeld = true;\n'
   '        return any;\n'
   '    }\n'
   '    bool reacquireVideoHardware(bool giveUp) {\n'
   '        bool all = true;\n'
   '        for (auto& [id, track] : m_tracks) {\n'
   '            if (!OmniMedia::isVideoCodec(track->info.codec) || !track->decoder.hardwareReleased()) continue;\n'
   '            if (track->decoder.reacquireHardware()) continue;\n'
   '            if (giveUp) track->decoder.abandonHardware(); else all = false;\n'
   '        }\n'
   '        if (all) m_videoHeld = false;   // fed again from the resync (the caller\'s resyncVideo)\n'
   '        return all;\n'
   '    }\n'),
  ('            auto& track = *owned;\n            track.decoder.setVideoTargetSize(targetWidth, targetHeight);\n',
   '            auto& track = *owned;\n'
   '            if ((m_videoHeld && OmniMedia::isVideoCodec(track.info.codec)) || track.decoder.hardwareReleased()) continue; // OMNI_TAB_MEDIA_RELEASE_V1: not fed while given back\n'
   '            track.decoder.setVideoTargetSize(targetWidth, targetHeight);\n'),
  ('    const bool m_switchHandoff = OmniMedia::SwitchHandoff::enabled(); // OMNI_MSE_SWITCH_HANDOFF_V1\n',
   '    const bool m_switchHandoff = OmniMedia::SwitchHandoff::enabled(); // OMNI_MSE_SWITCH_HANDOFF_V1\n'
   '    bool m_videoHeld = false; // OMNI_TAB_MEDIA_RELEASE_V1: video tracks released, not fed until all are back\n'),
  ('void OmniMSESource::resyncVideo() { for (auto& buffer : sourceBuffers()) static_cast<Buffer&>(buffer.get()).resyncVideo(); } // OMNI_MSE_SWITCH_HANDOFF_V1\n',
   'void OmniMSESource::resyncVideo() { for (auto& buffer : sourceBuffers()) static_cast<Buffer&>(buffer.get()).resyncVideo(); } // OMNI_MSE_SWITCH_HANDOFF_V1\n'
   'bool OmniMSESource::videoUsingHardware() { for (auto& buffer : sourceBuffers()) if (static_cast<Buffer&>(buffer.get()).videoUsingHardware()) return true; return false; } // OMNI_TAB_MEDIA_RELEASE_V1\n'
   'bool OmniMSESource::releaseVideoHardware() { bool any = false; for (auto& buffer : sourceBuffers()) any = static_cast<Buffer&>(buffer.get()).releaseVideoHardware() || any; return any; } // OMNI_TAB_MEDIA_RELEASE_V1\n'
   'bool OmniMSESource::reacquireVideoHardware(bool giveUp) { bool all = true; for (auto& buffer : sourceBuffers()) all = static_cast<Buffer&>(buffer.get()).reacquireVideoHardware(giveUp) && all; return all; } // OMNI_TAB_MEDIA_RELEASE_V1\n'),
 ],
 'entry/OmniHlsPlayer.cpp': [
  ('#include <WebCore/OriginAccessPatterns.h>\n',
   '#include <WebCore/OriginAccessPatterns.h>\n'
   '#include <WebCore/HTMLMediaElement.h> // OMNI_TAB_MEDIA_RELEASE_V1: the element\'s document URL\n'
   '#include <WebCore/Document.h>\n'
   '#include <WebCore/NodeDocument.h> // Node::document()\n'
   '#include "../media/OmniTabMediaRelease.h" // OMNI_TAB_MEDIA_RELEASE_V1\n'),
  ('        for (auto& t : m_tracks) t = { };\n        m_frames.clear();\n',
   '        for (auto& t : m_tracks) t = { };\n        m_tabMedia = { }; // OMNI_TAB_MEDIA_RELEASE_V1\n        m_frames.clear();\n'),
  ('        const bool video = kind == OmniMedia::Hls::Kind::Video;\n        for (int steps = 0; steps < 64; steps++) {\n',
   '        const bool video = kind == OmniMedia::Hls::Kind::Video;\n'
   '        if (video && t.decoder->hardwareReleased()) return true; // OMNI_TAB_MEDIA_RELEASE_V1: not fed while given back\n'
   '        for (int steps = 0; steps < 64; steps++) {\n'),
  ('        if (!pump(OmniMedia::Hls::Kind::Video) || !pump(OmniMedia::Hls::Kind::Audio)) { fail(MediaPlayer::NetworkState::DecodeError); return; }\n',
   '        if (!tabMediaTick()) return; // OMNI_TAB_MEDIA_RELEASE_V1\n'
   '        if (!pump(OmniMedia::Hls::Kind::Video) || !pump(OmniMedia::Hls::Kind::Audio)) { fail(MediaPlayer::NetworkState::DecodeError); return; }\n'),
  ('    void tick()\n    {\n        Ref protect { *this };\n        if (!m_session) return;\n',
   HLS_TICK + '    void tick()\n    {\n        Ref protect { *this };\n        if (!m_session) return;\n'),
  ('    uint64_t m_v7Decoded = 0, m_v7Shown = 0, m_v7Dropped = 0;   // OMNI_HOLEPUNCH_V7_QUALITY: video frames for getVideoPlaybackQuality()\n',
   '    uint64_t m_v7Decoded = 0, m_v7Shown = 0, m_v7Dropped = 0;   // OMNI_HOLEPUNCH_V7_QUALITY: video frames for getVideoPlaybackQuality()\n'
   '    OmniMedia::TabMedia::Gate m_tabMedia; // OMNI_TAB_MEDIA_RELEASE_V1\n'),
 ],
}

def apply(rel, edits):
    p = root / rel; raw = p.read_bytes().decode('utf-8')
    crlf = '\r\n' in raw
    text = raw.replace('\r\n', '\n')
    if 'OMNI_TAB_MEDIA_RELEASE_V1' in text: sys.exit(f'{rel}: already patched')
    for old, new in edits:
        n = text.count(old)
        if n != 1: sys.exit(f'{rel}: anchor matches {n} times: {old[:90]!r}')
        text = text.replace(old, new)
    p.write_bytes((text.replace('\n', '\r\n') if crlf else text).encode('utf-8'))
    print(f'patched {rel} ({len(edits)} edits, {"CRLF" if crlf else "LF"})')

for rel, edits in EDITS.items(): apply(rel, edits)
g = root / 'media/OmniTabMediaRelease.h'
if g.exists(): sys.exit('media/OmniTabMediaRelease.h exists')
g.write_bytes(GATE.replace('\n', '\r\n').encode('utf-8')); print('wrote media/OmniTabMediaRelease.h (CRLF)')
