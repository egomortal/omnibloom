// Native HLS playback for <video src="...m3u8"> (OMNI_HLS_NATIVE_V1). SPDX-License-Identifier: GPL-3.0-or-later
//
// Omni identifies as Safari, and players that see Safari (JW Player, video.js, site code) often
// set an .m3u8 URL straight on the media element. This player plays it the way Safari would:
//   * media/OmniHlsSession: playlists, variants (ABR), renditions, live, AES-128, segments;
//   * every request goes through the element's PlatformMediaResourceLoader, like the file
//     player's single request: cookies, the element's CORS mode, the network process and
//     content blocking (uBlock) apply as to any media load;
//   * decoding: OmniMedia::PacketDecoder per kind (hardware video through the decode service when
//     hw-decode.flag is set, else FFmpeg; FFmpeg audio resampled to 48 kHz stereo), a reconfigure
//     (drain, then configure) whenever the session tags packets with a new configuration;
//   * output: frames painted like the plain file player; PCM into an OmniAudioRing played by the
//     UI-process audio relay (OMNI_HLS_RELAY_V1; this process's own SDL device when the relay is
//     off or full), the audio position being the clock (audioOpen/audioClear/audioHeard/
//     audioRelease are the only places that touch the output).
// Created by OmniMediaFactory (OmniMediaPlayer.cpp) for HLS MIME types and for extension-less
// loads it is asked to try; a response that is not a playlist fails with FormatError so WebKit
// tries the next engine.
#include "config.h"
#include "../media/OmniHlsSession.h"
#include "../media/OmniPacketDecoder.h"
#include "../media/OmniAudioRing.h"
#include "../media/OmniAudioRelay.h" // OMNI_HLS_RELAY_V1
#include "../media/OmniPlaybackRate.h" // OMNI_PLAYBACK_RATE_V1
#include "../media/OmniHwPlatform.h"
#include <WebCore/MediaPlayerPrivate.h>
#include <WebCore/VideoPlaybackQualityMetrics.h> // OMNI_HOLEPUNCH_V7_QUALITY
#include <limits>
#include <WebCore/PlatformMediaResourceLoader.h>
#include <WebCore/ResourceRequest.h>   // HTTPHeaderName (via HTTPHeaderMap.h)
#include <WebCore/ResourceResponse.h>
#include <WebCore/GraphicsContext.h>
#include <WebCore/ColorSpace.h>
#include <WebCore/SecurityOrigin.h>
#include <WebCore/OriginAccessPatterns.h>
#include <WebCore/HTMLMediaElement.h> // OMNI_TAB_MEDIA_RELEASE_V1: the element's document URL
#include <WebCore/Document.h>
#include <WebCore/NodeDocument.h> // Node::document()
#include "../media/OmniTabMediaRelease.h" // OMNI_TAB_MEDIA_RELEASE_V1
#include <skia/core/SkData.h>
#include <skia/core/SkImage.h>
#include <skia/core/SkImageInfo.h>
#include <wtf/MonotonicTime.h>
#include <wtf/RunLoop.h>
#include <wtf/WeakPtr.h>
#include <wtf/text/MakeString.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <deque>
#include <map>
#include <unistd.h>
#include <cstdlib> // OMNI_HOLEPUNCH_V7_REV2: getenv (the kill switch)
#define SDL_MAIN_HANDLED
#include <SDL2/SDL.h>
#ifndef OMNI_HLS_AUDIO_RELEASE_SECONDS
#define OMNI_HLS_AUDIO_RELEASE_SECONDS 60 // OMNI_HLS_RELAY_V1 (host tests build it shorter)
#endif

namespace WebCore {

static std::string omniHlsUtf8(const String& value)
{
    auto utf8 = value.utf8();
    return std::string(reinterpret_cast<const char*>(utf8.data()), utf8.length());
}
static String omniHlsString(const std::string& value)
{
    return String::fromUTF8ReplacingInvalidSequences(std::span<const uint8_t>(reinterpret_cast<const uint8_t*>(value.data()), value.size()));
}
static void omniHlsLog(const std::string& line)
{
    static unsigned lines;
    if (lines++ >= 200) return;
    fprintf(stderr, "OMNI HLS: %s\n", line.c_str());
    fflush(stderr);
}

class OmniHlsPlayer;
class OmniHlsRequest final : public PlatformMediaResourceClient {
public:
    OmniHlsRequest(OmniHlsPlayer& owner, uint64_t id, int64_t offset, int64_t length, bool sniff)
        : m_owner(owner), m_id(id), m_offset(offset), m_length(length), m_sniff(sniff) { }
    void responseReceived(PlatformMediaResource&, const ResourceResponse&, CompletionHandler<void(ShouldContinuePolicyCheck)>&&) final;
    void redirectReceived(PlatformMediaResource&, ResourceRequest&&, const ResourceResponse&, CompletionHandler<void(ResourceRequest&&)>&&) final;
    void dataReceived(PlatformMediaResource&, const SharedBuffer&) final;
    void loadFinished(PlatformMediaResource&, const NetworkLoadMetrics&) final;
    void loadFailed(PlatformMediaResource&, const ResourceError&) final;
    void accessControlCheckFailed(PlatformMediaResource&, const ResourceError&) final;
private:
    void finish(bool ok);
    WeakPtr<OmniHlsPlayer> m_owner;
    uint64_t m_id;
    int64_t m_offset, m_length;
    int m_status = 0;
    bool m_done = false, m_overflow = false;
    bool m_sniff = false, m_notPlaylist = false;   // the first request: stop at once unless it is an M3U8
    std::vector<uint8_t> m_bytes;
    std::string m_finalUrl;
    MonotonicTime m_started { MonotonicTime::now() };
};

class OmniHlsPlayer final : public MediaPlayerPrivateInterface, public RefCounted<OmniHlsPlayer>, public CanMakeWeakPtr<OmniHlsPlayer>, public OmniMedia::Hls::Fetcher {
public:
    static constexpr size_t maxResponseBytes = 32 * 1024 * 1024;
    void ref() const final { RefCounted::ref(); }
    void deref() const final { RefCounted::deref(); }
    explicit OmniHlsPlayer(MediaPlayer& player)
        : m_player(player), m_timer(RunLoop::mainSingleton(), "OmniHlsPlayer::tick"_s, this, &OmniHlsPlayer::tick) { }
    ~OmniHlsPlayer() { cancelLoad(); }
    constexpr MediaPlayerType mediaPlayerType() const final { return MediaPlayerType::OmniFFmpeg; }
    String engineDescription() const final { return "Omni native HLS"_s; }
#if ENABLE(MEDIA_SOURCE)
    void load(const URL&, const LoadOptions&, MediaSourcePrivateClient&) final { fail(MediaPlayer::NetworkState::FormatError); }
#endif
    void load(const URL& url, const LoadOptions&) final
    {
        cancelLoad();
        if (!url.protocolIsInHTTPFamily()) { fail(MediaPlayer::NetworkState::FormatError); return; }
        RefPtr current = m_player.get();
        if (!current) return;
        m_loader = current->mediaResourceLoader();
        m_urls.push_back(url);
        OmniMedia::Hls::Options options;
        // The decoders' limits: H.264 to 1080p (hardware or FFmpeg), HEVC through the hardware;
        // AAC / Opus audio. Variants listing other codecs (AC-3, AV1, ...) are skipped.
        options.playable = [hardware = OmniMedia::Hw::flagEnabled()](const OmniMedia::Hls::Variant& v) { return OmniMedia::Hls::variantPlayable(v, hardware); };
        options.resolve = [](const std::string& base, const std::string& ref) {
            return omniHlsUtf8(URL(URL { omniHlsString(base) }, omniHlsString(ref)).string());
        };
        options.log = omniHlsLog;
        m_session = std::make_unique<OmniMedia::Hls::Session>(*this, std::move(options));
        m_network = MediaPlayer::NetworkState::Loading;
        m_ready = MediaPlayer::ReadyState::HaveNothing;
        m_loadStart = MonotonicTime::now();
        m_pausedAt = m_loadStart; // OMNI_HLS_RELAY_V1: not played yet counts as paused (a preloaded element gives its output back too)
        omniHlsLog("load");
        m_session->start(omniHlsUtf8(url.string()));
        m_timer.startRepeating(16_ms);
        current->networkStateChanged();
    }
    void cancelLoad() final
    {
        m_timer.stop();
        for (auto& [id, resource] : m_requests) shutdownResource(resource);
        m_requests.clear();
        m_session.reset();
        for (auto& t : m_tracks) t = { };
        m_tabMedia = { }; // OMNI_TAB_MEDIA_RELEASE_V1
        m_frames.clear();
        m_image = nullptr;
        audioClose();
        m_audioRetryAt = { }; m_audioRetryMs = 2000; m_audioReleased = false; // OMNI_HLS_RELAY_V1
        m_position = m_anchorPosition = 0;
        m_paused = true; m_ended = false; m_haveMetadata = false; m_corsPassed = false;
        m_urls.clear();
        m_sniffed = false;
        m_network = MediaPlayer::NetworkState::Empty;
        m_ready = MediaPlayer::ReadyState::HaveNothing;
    }
    void play() final
    {
        m_paused = false;
        m_anchor = MonotonicTime::now(); m_anchorPosition = m_position;
        // OMNI_HLS_RELAY_V1: the output went back while paused (60 s): what the ring held is gone,
        // so decode again from the playhead; the output opens again with the first PCM.
        if (m_audioReleased && m_session && m_haveMetadata) restartAt(m_position);
        audioPause(false);
        if (m_session) m_timer.startRepeating(16_ms);
        if (RefPtr current = m_player.get()) current->playbackStateChanged();
    }
    void pause() final
    {
        m_paused = true;
        m_anchorPosition = m_position;
        m_pausedAt = MonotonicTime::now(); // OMNI_HLS_RELAY_V1
        audioPause(true);
        if (RefPtr current = m_player.get()) current->playbackStateChanged();
    }
    bool paused() const final { return m_paused; }
    bool ended() const final { return m_ended; }
    FloatSize naturalSize() const final { return m_size; }
    bool hasVideo() const final { return m_session && m_session->hasVideo(); }
    bool hasAudio() const final { return m_session && m_session->hasAudio(); }
    bool supportsFullscreen() const final { return true; }
    void setVolume(float value) final { m_volume = std::isfinite(value) ? std::clamp(value, 0.0f, 1.0f) : 0; if (m_ring) m_ring->setGain(m_muted ? 0 : m_volume); }
    void setMuted(bool value) final { m_muted = value; if (m_ring) m_ring->setGain(m_muted ? 0 : m_volume); }
    void setPageIsVisible(bool value) final { m_visible = value; }
    MediaTime duration() const final
    {
        if (!m_session || !m_haveMetadata) return MediaTime::zeroTime();
        if (m_session->live()) return MediaTime::positiveInfiniteTime();
        return MediaTime::createWithDouble(m_session->duration());
    }
    MediaTime currentTime() const final { return MediaTime::createWithDouble(m_position); }
    // OMNI_PLAYBACK_RATE_V1: playbackRate 0.25 .. 2.0: the clock (the audio output's, else the wall
    // clock) runs at the rate, frames follow it; the audio is time-stretched (pitch kept).
    double rate() const final { return m_requestedRate; }
    double effectiveRate() const final { return m_rate; }
    void setRate(float requested) final { applyRate(requested); }
    void setRateDouble(double requested) final { applyRate(requested); }
    void setPreservesPitch(bool) final { }   // pitch is always kept
    void applyRate(double requested)
    {
        m_requestedRate = requested;
        const double rate = OmniMedia::Rate::effective(requested);
        if (rate == m_rate) return;
        const double previous = m_rate;
        m_anchor = MonotonicTime::now(); m_anchorPosition = m_position;   // the wall clock: from here at the new rate
        m_rate = rate;
        if (rate > 0 && rate != m_rateAudio.rate()) {
            // What is queued was stretched for the old rate: start again from what is heard now.
            const double heard = audioHeard();
            const double from = std::isfinite(heard) ? heard : m_position;
            if (m_audio && m_ring) {
                m_audio->lock(); m_ring->clear(); m_audio->unlock();
                if (!m_rateAudio.setRate(rate, from)) m_rateAudio.reset();
                rateAudioFlush();
            } else m_rateAudio.setRateNoRefeed(rate);
        }
        audioPause(m_paused || rate <= 0);
        if (m_rateLogs < 8) { ++m_rateLogs; omniHlsLog("rate " + std::to_string(previous) + " -> " + std::to_string(rate)); }
        RunLoop::mainSingleton().dispatch([weak = WeakPtr { *this }] { if (weak) if (RefPtr current = weak->m_player.get()) current->rateChanged(); });
    }
    void rateAudioFlush()
    {
        if (!m_ring) return;
        int16_t buffer[4096 * 2];
        for (int guard = 0; guard < 64; guard++) {
            const size_t room = std::min<size_t>(m_ring->roomFrames(), 4096);
            if (room < size_t(OmniMedia::Rate::TimeStretch::hop)) return;
            double media = 0, speed = 1;
            const size_t n = m_rateAudio.pull(buffer, room, media, speed);
            if (!n || !m_ring->write(buffer, n, media, speed)) return;
        }
    }
    MediaPlayer::NetworkState networkState() const final { return m_network; }
    MediaPlayer::ReadyState readyState() const final { return m_ready; }
    const PlatformTimeRanges& buffered() const final { return m_buffered; }
    const PlatformTimeRanges& seekable() const final { return m_seekable; }
    MediaTime maxTimeSeekable() const final { return m_session && m_haveMetadata ? MediaTime::createWithDouble(m_session->seekableEnd()) : MediaTime::zeroTime(); }
    MediaTime minTimeSeekable() const final { return m_session && m_haveMetadata ? MediaTime::createWithDouble(m_session->seekableStart()) : MediaTime::zeroTime(); }
    bool didLoadingProgress() const final { bool p = m_progress; m_progress = false; return p; }
    bool didPassCORSAccessCheck() const final { return m_corsPassed; }
    std::optional<bool> isCrossOrigin(const SecurityOrigin& origin) const final
    {
        for (const auto& url : m_urls)
            if (!origin.canRequest(url, originAccessPatternsForWebProcessOrEmpty())) return true;
        return false;
    }
    Ref<MediaTimePromise> seekToTarget(const SeekTarget& target) final
    {
        Ref protect { *this };
        if (!m_session || !m_haveMetadata) return MediaTimePromise::createAndReject(PlatformMediaError::Cancelled);
        double t = target.time.toDouble();
        t = std::clamp(t, m_session->seekableStart(), std::max(m_session->seekableStart(), m_session->live() ? m_session->seekableEnd() : m_session->duration()));
        restartAt(t); // OMNI_HLS_RELAY_V1: the body moved there (also used after the output was released)
        if (RefPtr current = m_player.get()) current->timeChanged();
        return MediaTimePromise::createAndResolve(currentTime());
    }
    void restartAt(double t)
    {
        t = std::clamp(t, m_session->seekableStart(), std::max(m_session->seekableStart(), m_session->live() ? m_session->seekableEnd() : m_session->duration())); // live: the window moved on while paused
        m_session->seek(t);
        for (auto& tr : m_tracks) { tr.decoder->flush(); tr.drainSent = tr.draining = false; tr.pendingPcm.clear(); }
        m_frames.clear();
        audioClear();
        m_audioReleased = false;
        m_position = m_anchorPosition = t;
        m_anchor = MonotonicTime::now();
        m_ended = false; m_waitingFirstFrame = true;
        setReady(MediaPlayer::ReadyState::HaveMetadata);
        if (!m_paused) m_timer.startRepeating(16_ms);
    }
    void paint(GraphicsContext& context, const FloatRect& rect) final
    {
        if (!m_image || !m_visible) return;
        // OMNI_VIDEO_TARGET_V1 as in the MSE player: decode/convert straight to the shown size.
        AffineTransform ctm = context.getCTM();
        double sx = ctm.xScale(), sy = ctm.yScale();
        int w = int(std::lround(rect.width() * sx)), h = int(std::lround(rect.height() * sy));
        if (w > 0 && h > 0 && w <= 4096 && h <= 4096)
            for (auto& t : m_tracks) t.decoder->setVideoTargetSize(w, h);
        context.drawNativeImage(*m_image, rect, FloatRect({ }, FloatSize(m_image->size())));
    }
    ColorSpace colorSpace() final { return ColorSpace::SRGB(); }
    RefPtr<NativeImage> nativeImageForCurrentTime() final { return m_image; }
    // OMNI_HOLEPUNCH_V7_QUALITY: getVideoPlaybackQuality() (was not implemented: total=0 dropped=0)
    // OMNI_HOLEPUNCH_V7_REV2: the V7 kill switch (as the engine's): off, the metrics are v90's
    static bool v7QualityOn()
    {
        static const bool on = [] {
            if (const char* env = getenv("OMNI_HOLEPUNCH_V7")) return env[0] != '0';
#ifdef __PROSPERO__
            return access("/data/omni/holepunch-v7-disabled.flag", F_OK) != 0;
#else
            return true;
#endif
        }();
        return on;
    }
    std::optional<VideoPlaybackQualityMetrics> videoPlaybackQualityMetrics() final
    {
        if (!v7QualityOn()) return std::nullopt;   // OMNI_HOLEPUNCH_V7_REV2: v90 had none
        auto bounded = [](uint64_t value) { return uint32_t(std::min<uint64_t>(value, std::numeric_limits<uint32_t>::max())); };
        VideoPlaybackQualityMetrics metrics;
        metrics.totalVideoFrames = bounded(m_v7Decoded);
        metrics.droppedVideoFrames = bounded(m_v7Dropped);
        metrics.displayCompositedVideoFrames = bounded(m_v7Shown);
        return metrics;
    }

    // ---- network (OmniMedia::Hls::Fetcher) --------------------------------------------------------
    void fetch(uint64_t id, const std::string& url, int64_t offset, int64_t length) final
    {
        ResourceRequest request { URL { omniHlsString(url) } };
        if (length > 0)
            request.setHTTPHeaderField(HTTPHeaderName::Range, makeString("bytes="_s, offset, '-', offset + length - 1));
        RefPtr<PlatformMediaResource> resource = m_loader ? m_loader->requestResource(WTF::move(request), PlatformMediaResourceLoader::DisallowCaching) : nullptr;
        if (!resource) {   // answered later, never from inside fetch()
            RunLoop::mainSingleton().dispatch([weak = WeakPtr { *this }, id] { if (weak) weak->fetchDone(id, false, { }, { }, 0); });
            return;
        }
        resource->setClient(adoptRef(*new OmniHlsRequest(*this, id, offset, length, !m_sniffed)));
        m_sniffed = true;
        m_requests.emplace(id, resource);
    }
    void cancel(uint64_t id) final
    {
        auto it = m_requests.find(id);
        if (it == m_requests.end()) return;
        shutdownResource(it->second);
        m_requests.erase(it);
    }
    void fetchDone(uint64_t id, bool ok, std::vector<uint8_t>&& bytes, std::string&& finalUrl, double seconds, bool notPlaylist = false)
    {
        Ref protect { *this };
        if (notPlaylist) {   // not HLS at all: let WebKit try the next engine
            omniHlsLog("the resource is not an M3U8 playlist");
            fail(MediaPlayer::NetworkState::FormatError);
            return;
        }
        auto it = m_requests.find(id);
        if (it != m_requests.end()) { shutdownResource(it->second); m_requests.erase(it); }
        m_progress = true;
        if (m_session) m_session->fetched(id, ok, std::move(bytes), finalUrl, seconds);
    }
    void noteURL(const URL& url) { m_urls.push_back(url); }
    void notePassedCORS(bool passed) { m_corsPassed = passed; }

private:
    struct Track {
        std::unique_ptr<OmniMedia::PacketDecoder> decoder = std::make_unique<OmniMedia::PacketDecoder>();
        uint32_t active = 0;
        bool configured = false, draining = false, drainSent = false, ended = false;
        std::optional<OmniMedia::DemuxPacket> retry;      // a packet the decoder asked to resubmit
        std::vector<int16_t> pendingPcm;                  // PCM the ring had no room for
        double pendingPcmTime = 0;
    };
    static void shutdownResource(RefPtr<PlatformMediaResource>& resource)
    {
        if (!resource) return;
        auto previous = std::exchange(resource, nullptr);
        RunLoop::mainSingleton().dispatch([previous = WTF::move(previous)] { previous->setClient(nullptr); previous->shutdown(); });
    }
    void fail(MediaPlayer::NetworkState state)
    {
        Ref protect { *this };
        cancelLoad();
        m_network = state;
        if (RefPtr current = m_player.get()) current->networkStateChanged();
    }
    void setReady(MediaPlayer::ReadyState state)
    {
        if (m_ready == state) return;
        m_ready = state;
        if (RefPtr current = m_player.get()) current->readyStateChanged();
    }

    // ---- audio sink (OMNI_HLS_RELAY_V1: the only place that touches the output) ---------------
    // The UI-process relay first (the console plays nothing a WebProcess's own device plays); this
    // process's SDL device when the relay is off or cannot take this player. Never fatal: without
    // an output the video plays on the wall clock and the PCM is dropped; retried after 2, 4, 8,
    // 16 s (the PCM that arrives meanwhile asks again, cheaply).
    bool audioOpen()
    {
        if (m_audio) return true;
        if (m_audioReleased || MonotonicTime::now() < m_audioRetryAt) return false;   // released: play() opens it again
        std::string why;
        m_audio = OmniMedia::Audio::Output::openRelay(why);
        m_rateAudio.reset(); // OMNI_PLAYBACK_RATE_V1: a new output starts with what comes next
        if (m_audio) m_ring = m_audio->makeRingView();   // the relay's shared ring (the Output owns its memory)
        else {
            if (m_audioLogs < 4) { ++m_audioLogs; omniHlsLog("audio: relay unavailable (" + why + "); this process's own SDL output"); }
            SDL_SetMainReady();
            if (!m_audioInitialized && !SDL_InitSubSystem(SDL_INIT_AUDIO)) m_audioInitialized = true;
            if (m_audioInitialized) {
                m_ring = std::make_unique<OmniMedia::AudioRing>(48000 * 3);
                SDL_AudioSpec wanted { }, actual { };
                wanted.freq = 48000; wanted.channels = 2; wanted.format = AUDIO_S16LSB; wanted.samples = 1024;
                wanted.callback = [](void* ring, Uint8* stream, int length) { OmniMedia::AudioRing::deviceCallback(ring, stream, length); };
                wanted.userdata = m_ring.get();
                m_audio = OmniMedia::Audio::Output::openSdl(&wanted, &actual);
                if (m_audio && (actual.freq != 48000 || actual.channels != 2 || actual.format != AUDIO_S16LSB)) m_audio = nullptr;   // no format changes allowed
                if (!m_audio) m_ring = nullptr;
            }
        }
        if (!m_audio || !m_ring) {
            m_audio = nullptr; m_ring = nullptr;   // the device (if any) before the ring its callback reads
            omniHlsLog(std::string("audio: no output (") + (m_audioInitialized ? SDL_GetError() : "SDL audio init failed") + "); video plays on, next attempt in "
                + std::to_string(int(m_audioRetryMs / 1000)) + " s");
            m_audioRetryAt = MonotonicTime::now() + Seconds::fromMilliseconds(m_audioRetryMs);
            m_audioRetryMs = std::min(16000.0, m_audioRetryMs * 2);
            return false;
        }
        m_audioRetryMs = 2000;
        m_ring->setGain(m_muted ? 0 : m_volume);
        m_audio->pause(m_paused);
        omniHlsLog("audio: " + m_audio->describe());
        return true;
    }
    void audioPause(bool paused) { if (m_audio) m_audio->pause(paused); }
    void audioClear()   // relay: clear() is a request the UI process carries out at its next callback
    {
        m_rateAudio.reset(); // OMNI_PLAYBACK_RATE_V1
        if (!m_audio || !m_ring) return;
        m_audio->lock();
        m_ring->clear();
        m_audio->unlock();
    }
    void audioClose()
    {
        if (m_audio && m_audio->relay()) { m_ring = nullptr; m_audio = nullptr; }   // the view first: the Output owns its memory
        else { m_audio = nullptr; m_ring = nullptr; }                             // the device first: its callback reads the ring
        if (m_audioInitialized) { SDL_QuitSubSystem(SDL_INIT_AUDIO); m_audioInitialized = false; }
    }
    // Paused for good: the output goes back (relay channels are few); play() decodes again from here.
    void audioRelease(const char* why)
    {
        if (!m_audio) return;
        omniHlsLog(std::string("audio: released its output (") + why + ")");
        audioClose();
        m_audioReleased = true;
    }
    // Media time heard now (NaN when the output has not played anything since the last clear, or
    // does not play: then the wall clock runs).
    double audioHeard() { return m_ring && m_audio && m_audio->playing() ? m_ring->heard(m_audio->deviceFrames(), !m_paused) : NAN; }

    // ---- decode -----------------------------------------------------------------------------
    // Pulls this kind's packets into its decoder until the decoder or the output side is full.
    bool pump(OmniMedia::Hls::Kind kind)
    {
        auto& t = m_tracks[kind == OmniMedia::Hls::Kind::Video ? 0 : 1];
        const bool video = kind == OmniMedia::Hls::Kind::Video;
        if (video && t.decoder->hardwareReleased()) return true; // OMNI_TAB_MEDIA_RELEASE_V1: not fed while given back
        for (int steps = 0; steps < 64; steps++) {
            if (video ? m_frames.size() >= 3 : !flushPcm(t)) return true;   // output side full
            if (t.configured && !collect(t, video)) return false;
            if (t.draining) {   // configuration change: wait for the old decoder's End
                if (!t.ended) {
                    if (!t.drainSent) {
                        auto rc = t.decoder->drain();
                        if (rc == OmniMedia::PacketDecoder::Submit::Error) return false;
                        if (rc == OmniMedia::PacketDecoder::Submit::Accepted) t.drainSent = true;
                    }
                    return true;
                }
                t.draining = t.drainSent = t.ended = t.configured = false;
            }
            const OmniMedia::DemuxPacket* next = t.retry ? &*t.retry : m_session->peek(kind);
            if (!next) return true;
            if (!t.configured || next->configuration != t.active) {
                if (t.configured) { t.draining = true; continue; }
                const auto* config = m_session->configuration(kind, next->configuration);
                t.decoder->setVideoPixelOrder(kN32_SkColorType == kBGRA_8888_SkColorType ? OmniMedia::PacketDecoder::PixelOrder::BGRA : OmniMedia::PacketDecoder::PixelOrder::RGBA);
                if (!config || !t.decoder->configure(*config)) { omniHlsLog("configure failed: " + t.decoder->error()); return false; }
                t.active = next->configuration; t.configured = true;
            }
            OmniMedia::DemuxPacket packet;
            if (t.retry) { packet = std::move(*t.retry); t.retry.reset(); }
            else m_session->next(kind, packet);
            auto rc = t.decoder->submit(packet);
            if (rc == OmniMedia::PacketDecoder::Submit::Error) { omniHlsLog("decode failed: " + t.decoder->error()); return false; }
            if (rc == OmniMedia::PacketDecoder::Submit::NeedOutput) { t.retry = std::move(packet); if (!collect(t, video)) return false; if (t.retry && steps > 8) return true; }
        }
        return true;
    }
    bool collect(Track& t, bool video)
    {
        for (int n = 0; n < 16; n++) {
            if (video && m_frames.size() >= 3) return true;
            if (!video && !t.pendingPcm.empty() && !flushPcm(t)) return true;
            OmniMedia::DecodedOutput out;
            auto rc = t.decoder->receive(out);
            if (rc == OmniMedia::PacketDecoder::Receive::NeedInput) return true;
            if (rc == OmniMedia::PacketDecoder::Receive::End) { t.ended = true; return true; }
            if (rc == OmniMedia::PacketDecoder::Receive::Error) { omniHlsLog("decode failed: " + t.decoder->error()); return false; }
            if (out.nonDisplaying) continue;
            const double time = out.hasTimestamp ? double(out.timestamp) * out.timeBase.numerator / out.timeBase.denominator : m_position;
            if (out.kind == OmniMedia::DecodedOutput::Kind::Video) {
                if (out.rgba.empty() || out.width <= 0 || out.height <= 0) continue;
                m_frames.push_back({ time, std::move(out) });
                ++m_v7Decoded; // OMNI_HOLEPUNCH_V7_QUALITY
            } else if (!out.pcm.empty()) {
                audioOpen();   // OMNI_HLS_RELAY_V1: without an output, flushPcm drops the PCM once it is due
                t.pendingPcm = std::move(out.pcm);
                t.pendingPcmTime = time;
                flushPcm(t);
            }
        }
        return true;
    }
    bool flushPcm(Track& t)
    {
        if (t.pendingPcm.empty()) return true;
        // OMNI_HLS_RELAY_V1: no output (yet): hold the PCM until the playhead reaches it, then drop
        // it. Audio decoding stays paced by the clock (it ran to the end of the stream at once), and
        // an output that opens later (retry, or the relay after a release) gets audio from about
        // the playhead on.
        if (!m_ring && t.pendingPcmTime > m_position + 0.5 && !audioOpen()) return false;
        if (!m_ring) { t.pendingPcm.clear(); return true; }
        // OMNI_PLAYBACK_RATE_V1: through RateAudio (a pass-through at rate 1); full -> later, as before.
        rateAudioFlush();
        if (m_rateAudio.backlogFrames() > 9600) return false;
        m_rateAudio.push(t.pendingPcm.data(), t.pendingPcm.size() / 2, t.pendingPcmTime);
        rateAudioFlush();
        t.pendingPcm.clear();
        return true;
    }
    void publish(OmniMedia::DecodedOutput& output)
    {
        auto info = SkImageInfo::Make(output.width, output.height, output.bgra ? kBGRA_8888_SkColorType : kRGBA_8888_SkColorType,
            output.opaque ? kOpaque_SkAlphaType : kUnpremul_SkAlphaType);
        auto* pixels = new std::vector<uint8_t>(std::move(output.rgba));
        auto data = SkData::MakeWithProc(pixels->data(), pixels->size(), [](const void*, void* context) { delete static_cast<std::vector<uint8_t>*>(context); }, pixels);
        m_image = NativeImage::create(SkImages::RasterFromData(info, std::move(data), size_t(output.width) * 4));
        FloatSize size { float(output.sourceWidth > 0 ? output.sourceWidth : output.width), float(output.sourceHeight > 0 ? output.sourceHeight : output.height) };
        if (size != m_size) { m_size = size; if (RefPtr current = m_player.get()) current->sizeChanged(); }
        if (RefPtr current = m_player.get()) current->repaint();
    }
    void updateRanges()
    {
        m_buffered.clear();
        m_seekable.clear();
        if (!m_session || !m_haveMetadata) return;
        double from = std::max(m_session->seekableStart(), std::min(m_position, m_session->bufferedEnd()));
        if (m_session->bufferedEnd() > from) m_buffered.add(MediaTime::createWithDouble(from), MediaTime::createWithDouble(m_session->bufferedEnd()));
        if (m_session->seekableEnd() > m_session->seekableStart())
            m_seekable.add(MediaTime::createWithDouble(m_session->seekableStart()), MediaTime::createWithDouble(m_session->seekableEnd()));
    }

    // OMNI_TAB_MEDIA_RELEASE_V1: media in a document served from this console (the Media downloads
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
    // OMNI_TAB_MEDIA_RELEASE_V1 (OmniTabMediaRelease.h): hidden 1.5 s with a hardware video stream:
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
    void tick()
    {
        Ref protect { *this };
        if (!m_session) return;
        const double now = (MonotonicTime::now() - m_loadStart).seconds();
        m_session->tick(now, m_position);
        if (m_session->failed()) {
            const auto& why = m_session->error();
            omniHlsLog("failed: " + why);
            fail(why == "not an HLS playlist" || why.find("decode") != std::string::npos || why.find("variant") != std::string::npos
                ? MediaPlayer::NetworkState::FormatError : MediaPlayer::NetworkState::NetworkError);
            return;
        }
        RefPtr current = m_player.get();
        if (!current) return;
        if (m_paused && m_audio && (MonotonicTime::now() - m_pausedAt).seconds() > OMNI_HLS_AUDIO_RELEASE_SECONDS) audioRelease("paused for 60 s"); // OMNI_HLS_RELAY_V1
        if (!m_haveMetadata && m_session->ready()) {
            m_haveMetadata = true;
            m_position = m_anchorPosition = m_session->startPosition();
            m_anchor = MonotonicTime::now();
            m_waitingFirstFrame = m_session->hasVideo();
            current->durationChanged();
            setReady(MediaPlayer::ReadyState::HaveMetadata);
            m_network = MediaPlayer::NetworkState::Loading;
            current->networkStateChanged();
        }
        if (!m_haveMetadata) {
            if (now > 30) fail(MediaPlayer::NetworkState::NetworkError);   // nothing playable within 30 s
            return;
        }
        if (!tabMediaTick()) return; // OMNI_TAB_MEDIA_RELEASE_V1
        if (!pump(OmniMedia::Hls::Kind::Video) || !pump(OmniMedia::Hls::Kind::Audio)) { fail(MediaPlayer::NetworkState::DecodeError); return; }
        // The clock: what the audio device plays when it plays, else the wall clock.
        const bool canPlay = !m_waitingFirstFrame && (m_session->bufferedEnd() > m_position + 0.05 || m_session->ended());
        rateAudioFlush(); // OMNI_PLAYBACK_RATE_V1
        if (!m_paused && canPlay && m_rate > 0) { // OMNI_PLAYBACK_RATE_V1: rate 0 holds the clock
            double heard = audioHeard();
            if (std::isfinite(heard) && m_session->hasAudio()) {
                m_position = std::max(m_position, heard);
                m_anchor = MonotonicTime::now(); m_anchorPosition = m_position; // OMNI_HLS_RELAY_V1: the wall clock goes on from here if the output stops
                ++m_audioClockTicks;
            } else { m_position = m_anchorPosition + (MonotonicTime::now() - m_anchor).seconds() * m_rate; ++m_wallClockTicks; } // OMNI_PLAYBACK_RATE_V1: * m_rate
        } else { m_anchor = MonotonicTime::now(); m_anchorPosition = m_position; }
        // Frames: show the newest one that is due (the first one at once after a load or seek).
        while (!m_frames.empty() && (m_waitingFirstFrame || m_frames.front().first <= m_position + 0.008)) {
            const bool more = m_frames.size() > 1 && m_frames[1].first <= m_position + 0.008;
            if (!more || m_waitingFirstFrame) { publish(m_frames.front().second); m_waitingFirstFrame = false; ++m_v7Shown; } // OMNI_HOLEPUNCH_V7_QUALITY
            else ++m_v7Dropped;   // a newer frame is due: this one is never shown
            m_frames.pop_front();
            if (!more) break;
        }
        updateRanges();
        // Ready state: enough data while the buffer reaches 2 s ahead (or the end), else waiting.
        const double ahead = m_session->bufferedEnd() - m_position;
        if (!m_waitingFirstFrame || !m_session->hasVideo())
            setReady(ahead > 2 || m_session->ended() ? MediaPlayer::ReadyState::HaveEnoughData : ahead > 0.1 ? MediaPlayer::ReadyState::HaveFutureData : MediaPlayer::ReadyState::HaveCurrentData);
        if (m_session->ended() && m_network != MediaPlayer::NetworkState::Loaded) { m_network = MediaPlayer::NetworkState::Loaded; current->networkStateChanged(); }
        // End: everything fetched, decoded and shown, and the audio played out.
        if (!m_ended && m_session->ended() && !m_session->peek(OmniMedia::Hls::Kind::Video) && !m_session->peek(OmniMedia::Hls::Kind::Audio)
            && m_frames.empty() && m_position >= m_session->bufferedEnd() - 0.05) {
            m_ended = true; m_paused = true;
            omniHlsLog("ended; clock from the audio output in " + std::to_string(m_audioClockTicks) + " of " + std::to_string(m_audioClockTicks + m_wallClockTicks) + " playing ticks"); // OMNI_HLS_RELAY_V1
            audioPause(true);
            current->timeChanged();
            current->playbackStateChanged();
            return;
        }
        if (!m_paused) current->timeChanged();
    }

    ThreadSafeWeakPtr<MediaPlayer> m_player;
    RunLoop::Timer m_timer;
    RefPtr<PlatformMediaResourceLoader> m_loader;
    std::unique_ptr<OmniMedia::Hls::Session> m_session;
    std::map<uint64_t, RefPtr<PlatformMediaResource>> m_requests;
    Track m_tracks[2];
    std::deque<std::pair<double, OmniMedia::DecodedOutput>> m_frames;
    RefPtr<NativeImage> m_image;
    FloatSize m_size;
    PlatformTimeRanges m_buffered, m_seekable;
    std::vector<URL> m_urls;
    bool m_sniffed = false;
    MonotonicTime m_loadStart, m_anchor;
    double m_position = 0, m_anchorPosition = 0;
    bool m_paused = true, m_ended = false, m_visible = true, m_haveMetadata = false, m_waitingFirstFrame = false, m_corsPassed = false;
    mutable bool m_progress = false;
    float m_volume = 1;
    bool m_muted = false, m_audioInitialized = false;
    // OMNI_HLS_RELAY_V1: the output (relay channel or SDL device) and the ring the PCM goes into
    // (relay: a view of its shared ring; SDL: this player's, read by the device callback).
    std::unique_ptr<OmniMedia::Audio::Output> m_audio;
    std::unique_ptr<OmniMedia::AudioRing> m_ring;
    MonotonicTime m_audioRetryAt, m_pausedAt;
    double m_audioRetryMs = 2000;
    unsigned m_audioLogs = 0;
    bool m_audioReleased = false;
    double m_requestedRate = 1, m_rate = 1; // OMNI_PLAYBACK_RATE_V1: asked for, running at
    OmniMedia::Rate::RateAudio m_rateAudio;
    unsigned m_rateLogs = 0;
    uint64_t m_audioClockTicks = 0, m_wallClockTicks = 0;   // playing ticks timed by the output / the wall clock
    uint64_t m_v7Decoded = 0, m_v7Shown = 0, m_v7Dropped = 0;   // OMNI_HOLEPUNCH_V7_QUALITY: video frames for getVideoPlaybackQuality()
    OmniMedia::TabMedia::Gate m_tabMedia; // OMNI_TAB_MEDIA_RELEASE_V1
    MediaPlayer::NetworkState m_network = MediaPlayer::NetworkState::Empty;
    MediaPlayer::ReadyState m_ready = MediaPlayer::ReadyState::HaveNothing;
};

void OmniHlsRequest::redirectReceived(PlatformMediaResource&, ResourceRequest&& request, const ResourceResponse&, CompletionHandler<void(ResourceRequest&&)>&& completion)
{
    Ref protect { *this };
    if (!request.url().protocolIsInHTTPFamily()) { completion(ResourceRequest { }); finish(false); return; }
    if (m_owner) m_owner->noteURL(request.url());
    completion(WTF::move(request));
}
void OmniHlsRequest::responseReceived(PlatformMediaResource&, const ResourceResponse& response, CompletionHandler<void(ShouldContinuePolicyCheck)>&& completion)
{
    Ref protect { *this };
    m_status = response.httpStatusCode();
    m_finalUrl = omniHlsUtf8(response.url().string());
    const bool ok = m_status >= 200 && m_status < 300 && response.expectedContentLength() <= int64_t(OmniHlsPlayer::maxResponseBytes);
    completion(ok ? ShouldContinuePolicyCheck::Yes : ShouldContinuePolicyCheck::No);
    if (!ok) finish(false);
}
void OmniHlsRequest::dataReceived(PlatformMediaResource& resource, const SharedBuffer& data)
{
    auto span = data.span();
    if (m_done || m_overflow) return;
    if (span.size() > OmniHlsPlayer::maxResponseBytes - m_bytes.size()) { m_overflow = true; finish(false); return; }
    m_bytes.insert(m_bytes.end(), span.begin(), span.end());
    if (m_sniff && m_bytes.size() >= 7) {   // an M3U8 starts with #EXTM3U (after an optional BOM / blank lines)
        m_sniff = false;
        size_t at = m_bytes.size() >= 3 && m_bytes[0] == 0xEF && m_bytes[1] == 0xBB && m_bytes[2] == 0xBF ? 3 : 0;
        while (at < m_bytes.size() && (m_bytes[at] == '\r' || m_bytes[at] == '\n' || m_bytes[at] == ' ' || m_bytes[at] == '\t')) ++at;
        if (m_bytes.size() - at >= 7 && memcmp(m_bytes.data() + at, "#EXTM3U", 7)) {
            m_notPlaylist = true;
            finish(false);
            // Stop the transfer now (after this callback unwinds, as the file player does).
            RunLoop::mainSingleton().dispatch([resource = RefPtr { &resource }] { resource->setClient(nullptr); resource->shutdown(); });
        }
        else if (m_bytes.size() - at < 7) m_sniff = true;
    }
}
void OmniHlsRequest::loadFinished(PlatformMediaResource& resource, const NetworkLoadMetrics&)
{
    Ref protect { *this };
    if (m_owner) m_owner->notePassedCORS(resource.didPassAccessControlCheck());
    // A server that ignored the Range header (200 with the whole resource): take the range here.
    if (m_length > 0 && m_status == 200 && m_offset >= 0 && size_t(m_offset + m_length) <= m_bytes.size() && m_bytes.size() > size_t(m_length))
        m_bytes = std::vector<uint8_t>(m_bytes.begin() + m_offset, m_bytes.begin() + m_offset + m_length);
    finish(true);
}
void OmniHlsRequest::loadFailed(PlatformMediaResource&, const ResourceError&) { Ref protect { *this }; finish(false); }
void OmniHlsRequest::accessControlCheckFailed(PlatformMediaResource&, const ResourceError&) { Ref protect { *this }; finish(false); }
void OmniHlsRequest::finish(bool ok)
{
    if (m_done) return;
    m_done = true;
    if (!m_owner) return;
    const double seconds = (MonotonicTime::now() - m_started).seconds();
    // Never call into the session from inside a loader callback: next turn of the run loop.
    RunLoop::mainSingleton().dispatch([owner = m_owner, id = m_id, ok, bytes = std::move(m_bytes), url = std::move(m_finalUrl), seconds, notPlaylist = m_notPlaylist]() mutable {
        if (owner) owner->fetchDone(id, ok, std::move(bytes), std::move(url), seconds, notPlaylist);
    });
}

Ref<MediaPlayerPrivateInterface> createOmniHlsPlayer(MediaPlayer& player)
{
    return adoptRef(*new OmniHlsPlayer(player));
}

}
