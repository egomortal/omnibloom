// Experimental memory-bounded video backend. SPDX-License-Identifier: GPL-3.0-or-later
#include "config.h"
#include "../media/OmniVideoDecoder.h"
#if ENABLE(MEDIA_SOURCE)
#include "../media/OmniHlsSession.h" // OMNI_HLS_NATIVE_V1
#include "../media/OmniHwPlatform.h"
#endif
#include "../media/OmniAudioRelay.h" // OMNI_AUDIO_RELAY_V1
#include "../media/OmniPlaybackRate.h" // OMNI_PLAYBACK_RATE_V1
#include "../media/OmniProgressive.h" // OMNI_PROGRESSIVE_V1
#include <WebCore/MediaPlayerPrivate.h>
#include <WebCore/PlatformMediaResourceLoader.h>
#include <WebCore/ResourceRequest.h>
#include <WebCore/ResourceResponse.h>
#include <WebCore/GraphicsContext.h>
#include <WebCore/ColorSpace.h>
#include <WebCore/SecurityOrigin.h>
#include <WebCore/OriginAccessPatterns.h>
#include <skia/core/SkImage.h>
#include <skia/core/SkPixmap.h>
#include <wtf/RunLoop.h>
#include <wtf/MonotonicTime.h>
#include <wtf/WeakPtr.h>
#include <unistd.h>
#include <algorithm>
#include <cmath>
#include <cstdarg>
#define SDL_MAIN_HANDLED
#include <SDL2/SDL.h>

namespace WebCore {
// Bounded development diagnostics; never log URLs, headers, or media bytes.
static void mediaDiagnostic(const char* format, ...)
{
    static const bool enabled = !access("/data/omni/staged-media-selftest.flag", F_OK);
    static unsigned lines = 0;
    if (!enabled || lines++ >= 64) return;
    fprintf(stderr, "MEDIA DIAG: ");
    va_list args;
    va_start(args, format);
    vfprintf(stderr, format, args);
    va_end(args);
    fputc('\n', stderr);
    fflush(stderr);
}
class OmniMediaPlayer;
class OmniMediaClient final : public PlatformMediaResourceClient {
public:
    explicit OmniMediaClient(OmniMediaPlayer&);
    void responseReceived(PlatformMediaResource&, const ResourceResponse&, CompletionHandler<void(ShouldContinuePolicyCheck)>&&) final;
    void redirectReceived(PlatformMediaResource&, ResourceRequest&&, const ResourceResponse&, CompletionHandler<void(ResourceRequest&&)>&&) final;
    void dataReceived(PlatformMediaResource&, const SharedBuffer&) final;
    void loadFinished(PlatformMediaResource&, const NetworkLoadMetrics&) final;
    void loadFailed(PlatformMediaResource&, const ResourceError&) final;
    void accessControlCheckFailed(PlatformMediaResource&, const ResourceError&) final;
private:
    WeakPtr<OmniMediaPlayer> owner;
};

class OmniMediaPlayer final : public MediaPlayerPrivateInterface, public RefCounted<OmniMediaPlayer>, public CanMakeWeakPtr<OmniMediaPlayer> {
public:
    void ref() const final { RefCounted::ref(); }
    void deref() const final { RefCounted::deref(); }
    explicit OmniMediaPlayer(MediaPlayer& value)
        : player(value), timer(RunLoop::mainSingleton(), "OmniMediaPlayer::tick"_s, this, &OmniMediaPlayer::tick) { }
    ~OmniMediaPlayer() { cancelLoad(); }
    constexpr MediaPlayerType mediaPlayerType() const final { return MediaPlayerType::OmniFFmpeg; }
    String engineDescription() const final { return "Omni FFmpeg bounded video preview"_s; }
#if ENABLE(MEDIA_SOURCE)
    // Segmented media uses the separately registered experimental MSE engine.
    void load(const URL&, const LoadOptions&, MediaSourcePrivateClient&) final { fail(MediaPlayer::NetworkState::FormatError); }
#endif
    void load(const URL& url, const LoadOptions&) final {
        mediaDiagnostic("load requested");
        cancelLoad();
        if (!url.protocolIsInHTTPFamily()) { fail(MediaPlayer::NetworkState::FormatError); return; }
        RefPtr current = player.get();
        if (!current) return;
        network = MediaPlayer::NetworkState::Loading;
        ready = MediaPlayer::ReadyState::HaveNothing;
        mediaURLs.push_back(url);
        auto loader = current->mediaResourceLoader();
        ResourceRequest request { URL(url) };
        resource = loader->requestResource(WTF::move(request), PlatformMediaResourceLoader::DisallowCaching);
        mediaDiagnostic("resource created=%d", !!resource);
        if (!resource) { fail(MediaPlayer::NetworkState::NetworkError); return; }
        resource->setClient(adoptRef(*new OmniMediaClient(*this)));
        started = MonotonicTime::now(); timer.startRepeating(16_ms);
        current->networkStateChanged();
    }
    void cancelLoad() final {
        stopTransportAndAudio();
        audioReleased = false; audioRetryAt = { }; audioRetryMs = 2000; // OMNI_AUDIO_RELAY_V1
        // A cancelled/failed element may remain alive in the document. Release
        // owned storage now instead of retaining the last load until destruction.
        image = nullptr;
        decoder.reset();
        frame = OmniMedia::VideoFrame { };
        std::vector<uint8_t>().swap(input);
        std::vector<URL>().swap(mediaURLs);
        ranges.clear();
        position = base = length = 0;
        pending = finished = corsPassed = false;
        stopped = true;
        network = MediaPlayer::NetworkState::Empty;
        ready = MediaPlayer::ReadyState::HaveNothing;
        mediaDiagnostic("cancel storage: input-capacity=%zu frame-capacity=%zu decoder=%d image=%d",
            input.capacity(), frame.rgba.capacity(), !!decoder, !!image);
    }
    bool ownsResource(const PlatformMediaResource& source) const { return resource.get() == &source; }
    void fail(MediaPlayer::NetworkState value) {
        mediaDiagnostic("failure state=%d bytes=%zu", static_cast<int>(value), input.size());
        Ref protect { *this };
        cancelLoad(); network = value;
        if (RefPtr current = player.get()) current->networkStateChanged();
    }
    void append(const SharedBuffer& buffer) {
        auto span = buffer.span();
        if (input.empty()) mediaDiagnostic("first data bytes=%zu", span.size());
        if (span.size() > OmniMedia::VideoDecoder::maxInputBytes - input.size()) { fail(MediaPlayer::NetworkState::FormatError); return; }
        input.insert(input.end(), span.begin(), span.end());
    }
    void loaded(PlatformMediaResource& source) {
        mediaDiagnostic("resource finished bytes=%zu; opening decoder", input.size());
        Ref protect { *this };
        corsPassed = source.didPassAccessControlCheck();
        // Completion ends transport, not the player's load. Keep input, origin
        // checks and any play() request made while the resource was loading.
        mediaDiagnostic("completion before transport stop playing=%d", !stopped);
        stopTransportAndAudio();
        mediaDiagnostic("completion transport stopped; decoder open begin bytes=%zu", input.size());
        decoder = std::make_unique<OmniMedia::VideoDecoder>();
        bool opened = decoder->open(std::move(input));
        mediaDiagnostic("decoder open end ok=%d audio=%d error=%.160s", opened, decoder->hasAudio(), decoder->error().c_str());
        if (!opened) {
            fprintf(stderr, "media: unsupported input: %s (audio=%d)\n", decoder->error().c_str(), decoder->hasAudio());
            fail(MediaPlayer::NetworkState::FormatError); return;
        }
        if (decoder->hasAudio()) openAudio(); // OMNI_AUDIO_RELAY_V1: never fatal (was DecodeError when init or open failed)
        rateAudio.reset(); audioMedia = 0; // OMNI_PLAYBACK_RATE_V1
        length = decoder->duration();
        mediaDiagnostic("initial decoder next begin");
        auto initialFrameResult = decoder->next(frame);
        mediaDiagnostic("initial decoder next end result=%d error=%.160s", static_cast<int>(initialFrameResult), decoder->error().c_str());
        if (initialFrameResult != OmniMedia::VideoDecoder::Result::Frame) { fail(MediaPlayer::NetworkState::DecodeError); return; }
        mediaDiagnostic("first decoded frame ready");
        if (!queueAudio()) { fail(MediaPlayer::NetworkState::DecodeError); return; }
        publishFrame();
        ranges.clear(); ranges.add(MediaTime::zeroTime(), MediaTime::createWithDouble(length));
        ready = MediaPlayer::ReadyState::HaveEnoughData; network = MediaPlayer::NetworkState::Loaded;
        if (RefPtr current = player.get()) {
            current->durationChanged(); current->sizeChanged(); current->networkStateChanged(); current->readyStateChanged(); current->repaint();
        }
        if (!stopped) { anchor = MonotonicTime::now(); if (audioDevice) audioDevice->pause(false); timer.startRepeating(16_ms); }
    }
    void play() final {
        stopped = false; anchor = MonotonicTime::now(); base = position;
        if (audioReleased && decoder) { // OMNI_AUDIO_RELAY_V1: released while paused: open again, decode again from here
            audioReleased = false; audioRetryAt = { };
            openAudio();
            rateAudio.reset(); audioMedia = position; // OMNI_PLAYBACK_RATE_V1
            if (decoder->seek(position) && decoder->next(frame) == OmniMedia::VideoDecoder::Result::Frame) { queueAudio(); publishFrame(); pending = false; }
        }
        if (audioDevice) audioDevice->pause(false);
        if (decoder && ready == MediaPlayer::ReadyState::HaveEnoughData) timer.startRepeating(16_ms);
        if (RefPtr current = player.get()) current->playbackStateChanged();
    }
    void pause() final {
        stopped = true;
        if (audioDevice) audioDevice->pause(true);
        // OMNI_AUDIO_RELAY_V1: paused for good (60 s): give the output back (the relay's channel or this
        // process's device); play() opens it again.
        pausedAt = MonotonicTime::now();
        RunLoop::mainSingleton().dispatchAfter(60_s, [weak = WeakPtr { *this }, at = pausedAt] {
            if (weak && weak->stopped && weak->pausedAt == at && weak->audioDevice) {
                fprintf(stderr, "OMNI AUDIO DEVICE: <video> player released its output (paused for 60 s)\n");
                fflush(stderr);
                weak->audioDevice->clearQueued(); weak->audioDevice = nullptr; weak->audioReleased = true;
            }
        });
        if (network != MediaPlayer::NetworkState::Loading) timer.stop();
        if (RefPtr current = player.get()) current->playbackStateChanged();
    }
    bool paused() const final { return stopped; }
    bool ended() const final { return finished; }
    FloatSize naturalSize() const final { return {float(frame.width), float(frame.height)}; }
    bool hasVideo() const final { return !!image; }
    bool supportsFullscreen() const final { return true; }
    bool hasAudio() const final { return decoder && decoder->hasAudio(); }
    void setVolume(float value) final { volume = std::isfinite(value) ? std::clamp(value,0.0f,1.0f) : 0; }
    void setMuted(bool value) final { muted = value; if (value && audioDevice) audioDevice->clearQueued(); }
    void setPageIsVisible(bool value) final { visible = value; }
    MediaTime duration() const final { return MediaTime::createWithDouble(length); }
    MediaTime currentTime() const final { return MediaTime::createWithDouble(position); }
    // OMNI_PLAYBACK_RATE_V1: playbackRate 0.25 .. 2.0: the clock runs at the rate, the audio is
    // time-stretched (pitch kept).
    double rate() const final { return requestedRate; }
    double effectiveRate() const final { return playRate; }
    void setRate(float requested) final { applyRate(requested); }
    void setRateDouble(double requested) final { applyRate(requested); }
    void setPreservesPitch(bool) final { }
    void applyRate(double requested)
    {
        requestedRate = requested;
        const double value = OmniMedia::Rate::effective(requested);
        if (value == playRate) return;
        base = position; anchor = MonotonicTime::now();
        const double previous = playRate;
        playRate = value;
        if (value > 0 && value != rateAudio.rate()) {
            if (audioDevice) audioDevice->clearQueued();
            if (!rateAudio.setRate(value, position)) rateAudio.reset();
        }
        if (audioDevice) audioDevice->pause(stopped || value <= 0);
        fprintf(stderr, "OMNI RATE: <video> player %.2f -> %.2f\n", previous, value); fflush(stderr);
        RunLoop::mainSingleton().dispatch([weak = WeakPtr { *this }] { if (weak) if (RefPtr current = weak->player.get()) current->rateChanged(); });
    }
    MediaPlayer::NetworkState networkState() const final { return network; }
    MediaPlayer::ReadyState readyState() const final { return ready; }
    const PlatformTimeRanges& buffered() const final { return ranges; }
    const PlatformTimeRanges& seekable() const final { return ranges; }
    MediaTime maxTimeSeekable() const final { return duration(); }
    bool didLoadingProgress() const final { return network == MediaPlayer::NetworkState::Loading; }
    bool didPassCORSAccessCheck() const final { return corsPassed; }
    std::optional<bool> isCrossOrigin(const SecurityOrigin& origin) const final {
        for (const auto& url : mediaURLs)
            if (!origin.canRequest(url, originAccessPatternsForWebProcessOrEmpty())) return true;
        return false;
    }
    void noteURL(const URL& url) { mediaURLs.push_back(url); }
    Ref<MediaTimePromise> seekToTarget(const SeekTarget& target) final {
        Ref protect { *this };
        if (!decoder || !decoder->seek(target.time.toDouble())) return MediaTimePromise::createAndReject(PlatformMediaError::Cancelled);
        position = base = target.time.toDouble(); anchor = MonotonicTime::now(); finished = false; pending = false;
        if (audioDevice) audioDevice->clearQueued();
        rateAudio.reset(); audioMedia = position; // OMNI_PLAYBACK_RATE_V1
        if (decoder->next(frame) != OmniMedia::VideoDecoder::Result::Frame) return MediaTimePromise::createAndReject(PlatformMediaError::Cancelled);
        if (!queueAudio()) return MediaTimePromise::createAndReject(PlatformMediaError::Cancelled);
        publishFrame();
        if (!stopped) { if (audioDevice) audioDevice->pause(false); timer.startRepeating(16_ms); }
        if (RefPtr current = player.get()) { current->timeChanged(); current->repaint(); }
        return MediaTimePromise::createAndResolve(currentTime());
    }
    void paint(GraphicsContext& context, const FloatRect& rect) final {
        if (image && visible) context.drawNativeImage(*image, rect, FloatRect(0, 0, frame.width, frame.height));
    }
    ColorSpace colorSpace() final { return ColorSpace::SRGB(); }
    RefPtr<NativeImage> nativeImageForCurrentTime() final { return image; }
private:
    void stopTransportAndAudio() {
        timer.stop();
        if (resource) {
            // A loader callback may hold checked references to itself. Keep the
            // resource alive until that callback unwinds before shutting it down.
            auto previous = std::exchange(resource, nullptr);
            RunLoop::mainSingleton().dispatch([previous = WTF::move(previous)] {
                previous->setClient(nullptr); previous->shutdown();
            });
        }
        if (audioDevice) {
            mediaDiagnostic("audio device close begin device=%u", audioDevice->id());
            audioDevice->clearQueued(); audioDevice = nullptr; // OMNI_AUDIO_RELAY_V1: closes the device or leaves the relay
            mediaDiagnostic("audio device close end");
        }
        if (audioInitialized) {
            mediaDiagnostic("audio subsystem quit begin");
            SDL_QuitSubSystem(SDL_INIT_AUDIO); audioInitialized = false;
            mediaDiagnostic("audio subsystem quit end");
        }
    }
    // OMNI_AUDIO_RELAY_V1: the relay first (the system drops what this process's own device plays), this
    // process's own SDL device when the relay is off or cannot take this player. Never fatal: without
    // an output the video plays on (its own clock) and audio is dropped; retried after 2, 4, 8, 16 s.
    void openAudio() {
        if (audioDevice) return;
        std::string why;
        audioDevice = OmniMedia::Audio::Output::openRelay(why);
        if (!audioDevice) {
            if (audioLogs < 4) { ++audioLogs; fprintf(stderr, "OMNI AUDIO DEVICE: <video> player: relay unavailable (%s); this process's own SDL output\n", why.c_str()); }
            SDL_SetMainReady();
            mediaDiagnostic("audio subsystem init begin");
            int audioInitResult = audioInitialized ? 0 : SDL_InitSubSystem(SDL_INIT_AUDIO);
            mediaDiagnostic("audio subsystem init end result=%d error=%.160s", audioInitResult, audioInitResult ? SDL_GetError() : "none");
            if (!audioInitResult) {
                audioInitialized = true;
                SDL_AudioSpec wanted {}, actual {};
                wanted.freq = 48000; wanted.channels = 2; wanted.format = AUDIO_S16LSB; wanted.samples = 1024;
                mediaDiagnostic("audio device open begin");
                audioDevice = OmniMedia::Audio::Output::openSdl(&wanted, &actual);
                mediaDiagnostic("audio device open end device=%u error=%.160s", audioDevice ? audioDevice->id() : 0u, audioDevice ? "none" : SDL_GetError());
            }
        }
        if (audioDevice) {
            fprintf(stderr, "OMNI AUDIO DEVICE: <video> player: %s\n", audioDevice->describe().c_str());
            audioRetryMs = 2000;
        } else {
            fprintf(stderr, "OMNI AUDIO INIT: <video> player has no audio output (%s); video plays on, next attempt in %.0f ms\n", SDL_GetError(), audioRetryMs);
            audioRetryAt = MonotonicTime::now() + Seconds::fromMilliseconds(audioRetryMs);
            audioRetryMs = std::min(16000.0, audioRetryMs * 2);
        }
        fflush(stderr);
    }
    bool queueAudio() {
        auto samples = decoder->takeAudio();
        // OMNI_PLAYBACK_RATE_V1: through RateAudio (a pass-through at rate 1, time-stretched otherwise);
        // the device takes up to 1 s, as before; what does not fit is dropped (as before).
        if (!samples.empty()) { rateAudio.push(samples.data(), samples.size() / 2, audioMedia); audioMedia += double(samples.size() / 2) / 48000; }
        if (!audioDevice) { rateAudio.reset(); return true; }
        constexpr unsigned limit = 48000 * 2 * sizeof(int16_t);
        float gain = muted ? 0 : volume;
        std::vector<int16_t> out(4096 * 2);
        for (int guard = 0; guard < 64; guard++) {
            const size_t room = (limit - std::min(limit, audioDevice->queuedBytes())) / (2 * sizeof(int16_t));
            if (room < size_t(OmniMedia::Rate::TimeStretch::hop)) break;
            double media = 0, speed = 1;
            const size_t n = rateAudio.pull(out.data(), std::min<size_t>(room, 4096), media, speed);
            if (!n) break;
            for (size_t i = 0; i < n * 2; i++) out[i] = int16_t(out[i] * gain);
            (void)audioDevice->queue(out.data(), unsigned(n * 2 * sizeof(int16_t))); // OMNI_AUDIO_RELAY_V1: a failure drops it (was fatal)
        }
        if (rateAudio.backlogFrames() > 48000) rateAudio.reset();   // more than 1 s waiting: dropped (OMNI_AUDIO_RELAY_V1: was fatal)
        return true;
    }
    void publishFrame() {
        auto info = SkImageInfo::Make(frame.width, frame.height, kRGBA_8888_SkColorType, kUnpremul_SkAlphaType);
        image = NativeImage::create(SkImages::RasterFromPixmapCopy(SkPixmap(info, frame.rgba.data(), frame.width * 4)));
    }
    void tick() {
        Ref protect { *this };
        if (network == MediaPlayer::NetworkState::Loading) {
            if (MonotonicTime::now() - started > 30_s) fail(MediaPlayer::NetworkState::NetworkError);
            return;
        }
        if (stopped || !decoder) return;
        if (decoder->hasAudio() && !audioDevice && MonotonicTime::now() >= audioRetryAt) { openAudio(); if (audioDevice) audioDevice->pause(false); } // OMNI_AUDIO_RELAY_V1
        position = std::min(length, base + (MonotonicTime::now() - anchor).seconds() * playRate); // OMNI_PLAYBACK_RATE_V1
        if (!pending) {
            auto result = decoder->next(frame);
            if (!queueAudio()) { fail(MediaPlayer::NetworkState::DecodeError); return; }
            if (result == OmniMedia::VideoDecoder::Result::Again) return;
            if (result == OmniMedia::VideoDecoder::Result::Error) { fail(MediaPlayer::NetworkState::DecodeError); return; }
            if (result == OmniMedia::VideoDecoder::Result::End) {
                rateAudio.endOfStream(); // OMNI_PLAYBACK_RATE_V1: what the stretcher holds back comes out
                if (position < length || (audioDevice && audioDevice->queuedBytes())) return;
                finished = true; stopped = true; timer.stop();
                if (audioDevice) audioDevice->pause(true);
                if (RefPtr current = player.get()) { current->timeChanged(); current->playbackStateChanged(); }
                return;
            }
            pending = true;
        }
        if (frame.seconds > position) return;
        publishFrame(); pending = false;
        if (RefPtr current = player.get()) { current->timeChanged(); current->repaint(); }
    }
    ThreadSafeWeakPtr<MediaPlayer> player;
    RefPtr<PlatformMediaResource> resource;
    std::unique_ptr<OmniMedia::VideoDecoder> decoder;
    std::vector<uint8_t> input;
    std::vector<URL> mediaURLs;
    OmniMedia::VideoFrame frame;
    RefPtr<NativeImage> image;
    PlatformTimeRanges ranges;
    RunLoop::Timer timer;
    MonotonicTime started, anchor;
    double position = 0, base = 0, length = 0;
    bool stopped = true, visible = true, pending = false, finished = false, corsPassed = false;
    std::unique_ptr<OmniMedia::Audio::Output> audioDevice; // OMNI_AUDIO_RELAY_V1: was the SDL device id
    MonotonicTime audioRetryAt, pausedAt;
    double audioRetryMs = 2000;
    unsigned audioLogs = 0;
    bool audioReleased = false;
    double requestedRate = 1, playRate = 1, audioMedia = 0; // OMNI_PLAYBACK_RATE_V1
    OmniMedia::Rate::RateAudio rateAudio;
    bool audioInitialized = false, muted = false;
    float volume = 1;
    MediaPlayer::NetworkState network = MediaPlayer::NetworkState::Empty;
    MediaPlayer::ReadyState ready = MediaPlayer::ReadyState::HaveNothing;
};
OmniMediaClient::OmniMediaClient(OmniMediaPlayer& value) : owner(value) { }
void OmniMediaClient::redirectReceived(PlatformMediaResource& source, ResourceRequest&& request, const ResourceResponse&, CompletionHandler<void(ResourceRequest&&)>&& completion) {
    Ref protect { *this };
    if (!owner || !owner->ownsResource(source) || !request.url().protocolIsInHTTPFamily()) {
        completion(ResourceRequest { });
        if (owner && owner->ownsResource(source)) owner->fail(MediaPlayer::NetworkState::NetworkError);
        return;
    }
    owner->noteURL(request.url());
    completion(WTF::move(request));
}
void OmniMediaClient::responseReceived(PlatformMediaResource& source, const ResourceResponse& response, CompletionHandler<void(ShouldContinuePolicyCheck)>&& completion) {
    mediaDiagnostic("response status=%d expected-bytes=%lld", response.httpStatusCode(), static_cast<long long>(response.expectedContentLength()));
    Ref protect { *this };
    bool valid = owner && owner->ownsResource(source) && response.httpStatusCode() >= 200 && response.httpStatusCode() < 300
        && response.expectedContentLength() <= int64_t(OmniMedia::VideoDecoder::maxInputBytes);
    if (valid) owner->noteURL(response.url());
    completion(valid ? ShouldContinuePolicyCheck::Yes : ShouldContinuePolicyCheck::No);
    if (!valid && owner && owner->ownsResource(source)) owner->fail(MediaPlayer::NetworkState::NetworkError);
}
void OmniMediaClient::dataReceived(PlatformMediaResource& source, const SharedBuffer& data) { Ref protect { *this }; if (owner && owner->ownsResource(source)) owner->append(data); }
void OmniMediaClient::loadFinished(PlatformMediaResource& source, const NetworkLoadMetrics&) { Ref protect { *this }; if (owner && owner->ownsResource(source)) owner->loaded(source); }
void OmniMediaClient::loadFailed(PlatformMediaResource& source, const ResourceError&) { Ref protect { *this }; if (owner && owner->ownsResource(source)) owner->fail(MediaPlayer::NetworkState::NetworkError); }
void OmniMediaClient::accessControlCheckFailed(PlatformMediaResource& source, const ResourceError&) { Ref protect { *this }; if (owner && owner->ownsResource(source)) owner->fail(MediaPlayer::NetworkState::NetworkError); }

#if ENABLE(MEDIA_SOURCE)
Ref<MediaPlayerPrivateInterface> createOmniHlsPlayer(MediaPlayer&); // OMNI_HLS_NATIVE_V1 (OmniHlsPlayer.cpp)
#endif
Ref<MediaPlayerPrivateInterface> createOmniProgressivePlayer(MediaPlayer&); // OMNI_PROGRESSIVE_V1 (OmniProgressivePlayer.cpp)
#if ENABLE(MEDIA_SOURCE)
static bool omniIsHlsType(const String& type)
{
    auto lower = type.convertToASCIILowercase().utf8();
    return OmniMedia::Hls::isHlsMimeType(std::string_view(reinterpret_cast<const char*>(lower.data()), lower.length()));
}
#endif
// OMNI_HLS_NATIVE_V1: one factory, two kinds of load: files (opt-in media-preview.flag, as before)
// and native HLS (on unless /data/omni/hls-native-disabled.flag).
class OmniMediaFactory final : public MediaPlayerFactory {
public:
    OmniMediaFactory(bool files, bool hls) : m_files(files), m_hls(hls) { }
    MediaPlayerEnums::MediaEngineIdentifier identifier() const final { return MediaPlayerEnums::MediaEngineIdentifier::OmniFFmpeg; }
    Ref<MediaPlayerPrivateInterface> createMediaEnginePlayer(MediaPlayer& player) const final {
#if ENABLE(MEDIA_SOURCE)
        // An HLS type, or an untyped load while files are off: the HLS player (it stops after the
        // first bytes and reports FormatError unless they are #EXTM3U).
        if (m_hls && (omniIsHlsType(player.contentMIMEType()) || !m_files)) return createOmniHlsPlayer(player);
#endif
        if (OmniMedia::Progressive::enabled()) return createOmniProgressivePlayer(player); // OMNI_PROGRESSIVE_V1 (kill switch: media-progressive-disabled.flag)
        return adoptRef(*new OmniMediaPlayer(player));
    }
    void getSupportedTypes(HashSet<String>& types) const final {
        if (m_files) { types.add("video/mp4"_s); types.add("video/webm"_s); }
        if (m_hls) { types.add("application/vnd.apple.mpegurl"_s); types.add("application/x-mpegurl"_s); types.add("audio/mpegurl"_s); }
    }
    MediaPlayer::SupportsType supportsTypeAndCodecs(const MediaEngineSupportParameters& parameters) const final {
        if (parameters.platformType != PlatformMediaDecodingType::FileOrHLS || parameters.requiresRemotePlayback) return MediaPlayer::SupportsType::IsNotSupported;
        auto type = parameters.type.containerType();
#if ENABLE(MEDIA_SOURCE)
        if (omniIsHlsType(type)) {
            if (!m_hls) return MediaPlayer::SupportsType::IsNotSupported;
            // canPlayType (no URL) only when advertised (default; OMNI_HLS_RELAY_V1); loads always.
            if (parameters.url.isEmpty() && !OmniMedia::Hls::nativeAdvertised()) return MediaPlayer::SupportsType::IsNotSupported;
            const bool hardware = OmniMedia::Hw::flagEnabled();
            for (auto& codec : parameters.type.codecs()) {
                auto utf8 = codec.utf8();
                if (!OmniMedia::Hls::codecPlayable(std::string(reinterpret_cast<const char*>(utf8.data()), utf8.length()), hardware))
                    return MediaPlayer::SupportsType::IsNotSupported;
            }
            return MediaPlayer::SupportsType::MayBeSupported;   // Safari's answer too
        }
#endif
        if (!m_files) return MediaPlayer::SupportsType::IsNotSupported;
        if (type != "video/mp4"_s && type != "video/webm"_s) return MediaPlayer::SupportsType::IsNotSupported;
        // Decode validation remains authoritative. Never advertise DRM or MSE.
        auto codecs = parameters.type.codecs();
        for (auto& codec : codecs) {
            if (!codec.startsWith("avc1"_s) && !codec.startsWith("vp8"_s) && !codec.startsWith("vp9"_s) && !codec.startsWith("vp09"_s)
                && !codec.startsWith("mp4a"_s) && codec != "opus"_s && codec != "vorbis"_s) return MediaPlayer::SupportsType::IsNotSupported;
        }
        return MediaPlayer::SupportsType::MayBeSupported;
    }
private:
    bool m_files, m_hls;   // OMNI_HLS_NATIVE_V1
};
void registerOmniMediaEngine(MediaEngineRegistrar registrar) {
    // Opt-in development build until playback, resource isolation and teardown pass.
    // OMNI_HLS_NATIVE_V1: also registered for native HLS (on by default).
    const bool files = !access("/data/omni/media-preview.flag", F_OK);
#if ENABLE(MEDIA_SOURCE)
    const bool hls = OmniMedia::Hls::nativeEnabled();
#else
    const bool hls = false;
#endif
    fprintf(stderr, "OMNI HLS: native HLS %s (canPlayType %s), files %s\n", hls ? "on" : "off (hls-native-disabled.flag)",
#if ENABLE(MEDIA_SOURCE)
        OmniMedia::Hls::nativeAdvertised() ? "\"maybe\", audio through the relay" : "\"\": hls-native-advertise-disabled.flag", // OMNI_HLS_RELAY_V1
#else
        "\"\"",
#endif
        files ? (OmniMedia::Progressive::enabled() ? "on (media-preview.flag), progressive with byte ranges" : "on (media-preview.flag), whole files up to 32 MiB (media-progressive-disabled.flag)") : "off"); // OMNI_PROGRESSIVE_V1
    if (files || hls) registrar(makeUnique<OmniMediaFactory>(files, hls));
}
}
