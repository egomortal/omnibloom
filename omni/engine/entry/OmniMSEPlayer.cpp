#include "../media/OmniDiagnosticMode.h"
// Experimental MSE playback adapter. SPDX-License-Identifier: GPL-3.0-or-later
#include "config.h"
#if ENABLE(MEDIA_SOURCE)
#include "OmniMSESource.h"
#include "OmniMSEClock.h"
#include "../media/OmniHwClient.h" // OMNI_HOLEPUNCH_V1
#include "../media/OmniAudioRing.h" // OMNI_HOLEPUNCH_V5
#include "../media/OmniAudioRelay.h" // OMNI_AUDIO_RELAY_V1
#include "../media/OmniPlaybackRate.h" // OMNI_PLAYBACK_RATE_V1
#include <WebCore/FloatQuad.h>
#include <WebCore/HTMLFrameOwnerElement.h>
#include <WebCore/HTMLMediaElement.h>
#include <WebCore/LocalFrameView.h>
#include <WebCore/LocalFrameViewInlines.h>
#include <WebCore/RenderElementStyleInlines.h>
#include <WebCore/RenderMediaInlines.h>
#include <WebCore/RenderObjectDocument.h>
#include <WebCore/RenderObjectInlines.h>
#include <WebCore/RenderVideo.h>
#include <WebCore/RenderView.h>
#include <WebCore/MediaPlayerPrivate.h>
#include <WebCore/MediaSourcePrivateClient.h>
#include <WebCore/GraphicsContext.h>
#include <WebCore/ColorSpace.h>
#include <WebCore/SecurityOrigin.h>
#include <WebCore/VideoPlaybackQualityMetrics.h>
#include <WebCore/PlatformMediaCapabilitiesDecodingInfo.h> // OMNI_MEDIACAPS_V1
#include <WebCore/PlatformMediaDecodingConfiguration.h>
#include <WebCore/PlatformMediaEngineConfigurationFactory.h>
#include "../media/OmniHwPlatform.h"
#include "../media/OmniTabMediaRelease.h" // OMNI_TAB_MEDIA_RELEASE_V1
#include <WebCore/Document.h> // OMNI_TAB_MEDIA_RELEASE_V1: the element's document URL
#include <WebCore/NodeDocument.h> // OMNI_TAB_MEDIA_RELEASE_V1: Node::document()
#include <skia/core/SkData.h>
#include <skia/core/SkImage.h>
#include <skia/core/SkPixmap.h>
#include <wtf/MonotonicTime.h>
#include <wtf/RunLoop.h>
#include <wtf/WeakPtr.h>
#include <wtf/ThreadSafeWeakPtr.h>
#include <algorithm>
#include <atomic>
#include <cmath>
#include <optional>
#include <cstdio>
#include <cstring>
#include <limits>
#include <unistd.h>
#include <cstdlib> // OMNI_HOLEPUNCH_V7_REV2: getenv (the kill switch)
#define SDL_MAIN_HANDLED
#include <SDL2/SDL.h>

// Experimental link wrapper only: expose the native failure SDL's PS5 backend
// otherwise discards. Never reinterpret success or retry initialization here.
extern "C" int __real_sceAudioOutInit(void);
extern "C" int __wrap_sceAudioOutInit(void)
{
    int result = __real_sceAudioOutInit();
    static std::atomic<unsigned> logged { 0 };
    unsigned count = logged.load(std::memory_order_relaxed);
    while (count < 4 && !logged.compare_exchange_weak(count, count + 1, std::memory_order_relaxed)) { }
    if (count < 4) {
        fprintf(stderr, "OMNI AUDIO INIT: result=%d hex=0x%08x\n", result, static_cast<unsigned>(result));
        fflush(stderr);
    }
    return result;
}

namespace WebCore {
class OmniMSEPlayer final : public MediaPlayerPrivateInterface, public RefCounted<OmniMSEPlayer>, public CanMakeWeakPtr<OmniMSEPlayer> {
public:
    explicit OmniMSEPlayer(MediaPlayer& value)
        : m_player(value), m_timer(RunLoop::mainSingleton(), "OmniMSEPlayer::tick"_s, this, &OmniMSEPlayer::tick) { }
    ~OmniMSEPlayer() { cancelLoad(); }
    void ref() const final { RefCounted::ref(); }
    void deref() const final { RefCounted::deref(); }
    constexpr MediaPlayerType mediaPlayerType() const final { return MediaPlayerType::OmniMSE; }
    String engineDescription() const final { return "Omni experimental fragmented MP4"_s; }
    void load(const URL&, const LoadOptions&) final { fail(); }
    void load(const URL&, const LoadOptions&, MediaSourcePrivateClient& client) final
    {
        cancelLoad();
        m_decodedVideoFrames = m_displayedVideoFrames = m_droppedVideoFrames = 0;
        m_replacedUnpaintedFrames = m_discardedPrerollFrames = m_discardedSeekFrames = 0;
        m_v7PacingLink = nullptr; m_v7Pacing = false; m_v7RunShown = m_v7RunDropped = m_v7DoneShown = m_v7DoneDropped = 0; // OMNI_HOLEPUNCH_V7_QUALITY
        m_pcmSubmittedFrames = m_pcmSubmittedChunks = m_errors = 0;
        m_profileTicks = 0;
        m_pumpTotalMilliseconds = m_pumpMaxMilliseconds = m_maxIntertickMilliseconds = 0;
        m_previousProfileTick.reset();
        m_diagnosticLines = 0;
        m_holeAllowed = OmniMedia::Hw::Client::holePunchAllowed(); // OMNI_HOLEPUNCH_V1
        m_holePacingAllowed = OmniMedia::Hw::Client::holePacingAllowed(); // OMNI_HOLEPUNCH_V4
        m_v5 = OmniMedia::Hw::holeV5FlagEnabled(); // OMNI_HOLEPUNCH_V5 (kill switch: holepunch-v5-disabled.flag)
        m_switchHandoff = OmniMedia::SwitchHandoff::enabled(); // OMNI_MSE_SWITCH_HANDOFF_V1 (kill switch: mse-switch-handoff-disabled.flag)
        m_switchSeen = 0; m_switchPending = false; m_switchLogs = m_resyncLogs = 0;
        m_tabMedia = { }; // OMNI_TAB_MEDIA_RELEASE_V1
        m_audioUnderrunsLogged = 0;
        m_lockEnabled = Omni::DisplayLock::enabled(); m_lock = 1; m_lockChanges = 0; m_rateAudio.setLock(1); // OMNI_PERF_C_V4 (kill switch: display-resample-disabled.flag)
        m_holdShort = holdShortEnabled(); // OMNI_PERF_C_T2 (kill switch: startup-hold-short-disabled.flag)
        m_fastSwitch = fastSwitchEnabled(); m_quickTicks = 0; // OMNI_PERF_C_V8 (kill switch: switch-fast-claim-disabled.flag)
        m_v5Hold = false; v5Hold("start"); // OMNI_HOLEPUNCH_V5_REV2: the playhead waits for ~1 s of audio and video
        m_audioInitThisTick = false; m_audioInitNotBeforeMs = 0; m_v5AudioVsWallMs = 0; m_v5DryHoldArmed = true;
        m_v5HoldLogs = m_audioInitSlowLogs = m_audioDeviceLogs = 0; m_audioDeviceLogPending = false; // V5_REV3: m_audioDeviceLogs
        m_audioRelayLogs = m_audioFailLogs = 0; m_audioRetryDelayMs = 2000; // OMNI_AUDIO_RELAY_V1
        m_audioRetryStart = 0; m_audioUnavailable = false; m_audioReleasedPaused = false; m_pausedSince = MonotonicTime::now();
        m_network = MediaPlayer::NetworkState::Loading;
        m_source = OmniMSESource::create(client, [weak = WeakPtr { *this }]() -> RefPtr<MediaPlayerPrivateInterface> {
            return weak ? RefPtr<MediaPlayerPrivateInterface>(weak.get()) : nullptr;
        }, [weak = WeakPtr { *this }] { if (weak) weak->changed(); });
        client.setPrivateAndOpen(Ref { *m_source });
        if (m_v5) m_source->setVideoOutputBudget(48); // OMNI_HOLEPUNCH_V5: the first ticks fill ~1 s of audio (see holeTickV3)
        changed();
        m_anchor = MonotonicTime::now();
        m_timer.startRepeating(16_ms);
    }
    void cancelLoad() final
    {
        ++m_seekGeneration;
        m_timer.stop();
        m_seekPromise.reset();
        holePunchReset(); // OMNI_HOLEPUNCH_V1: before the decoders go
        if (m_source) {
            m_source->setPlayer(nullptr);
            m_source->shutdown();
            m_source = nullptr;
        }
        if (m_audio) { if (!m_audioRing) m_audio->clearQueued(); m_audio = nullptr; } // OMNI_AUDIO_RELAY_V1: Output (SDL device or the relay)
        m_audioRing = nullptr; // OMNI_HOLEPUNCH_V5: after the device (its callback reads the ring)
        if (m_audioInitialized) { SDL_QuitSubSystem(SDL_INIT_AUDIO); m_audioInitialized = false; }
        m_image = nullptr; m_scaled = nullptr;
        m_imageSerial = m_lastPaintedSerial = 0;
        m_size = { };
        m_ranges.clear(); m_seekable.clear();
        m_audioDiscardBefore.reset(); m_videoDiscardBefore.reset();
        m_audioPresentationGeneration = m_videoPresentationGeneration = 0;
        m_position = 0; m_paused = true; m_ended = false;
        m_ready = MediaPlayer::ReadyState::HaveNothing;
        m_network = MediaPlayer::NetworkState::Empty;
    }
    void play() final
    {
        m_paused = false; m_ended = false; m_anchor = MonotonicTime::now();
        m_pausedSince.reset(); // OMNI_AUDIO_RELAY_V1
        if (m_v5Hold) m_v5HoldSince = m_v5HoldProgressAt = m_anchor; // OMNI_HOLEPUNCH_V5_REV2: the hold's time limit counts from play (V5_REV3: and its progress)
        notifyPlayback();
    }
    void pause() final { m_paused = true; m_pausedSince = MonotonicTime::now(); if (m_audio) m_audio->pause(true); notifyPlayback(); } // OMNI_AUDIO_RELAY_V1: m_pausedSince
    bool paused() const final { return m_paused; }
    bool ended() const final { return m_ended; }
    std::optional<VideoPlaybackQualityMetrics> videoPlaybackQualityMetrics() final
    {
        auto bounded = [](uint64_t value) { return uint32_t(std::min<uint64_t>(value, std::numeric_limits<uint32_t>::max())); };
        VideoPlaybackQualityMetrics metrics;
        // OMNI_HOLEPUNCH_V7_QUALITY: while the shell paces this video its pictures never come
        // here: add the shell's own counts (shown, and dropped before or at its vblank).
        if (v7QualityOn()) v7PacingCounts();   // OMNI_HOLEPUNCH_V7_REV2: off, the counts stay 0 (v90)
        const uint64_t shellShown = m_v7DoneShown + m_v7RunShown, shellDropped = m_v7DoneDropped + m_v7RunDropped;
        metrics.totalVideoFrames = bounded(m_decodedVideoFrames + shellShown + shellDropped);
        // v53: report only frames replaced before WebKit painted them. Hidden
        // preroll and seek-discarded frames are expected, not playback loss, and
        // previously inflated this figure (which sites use to lower quality).
        metrics.droppedVideoFrames = bounded(m_replacedUnpaintedFrames + shellDropped);
        metrics.displayCompositedVideoFrames = bounded(m_displayedVideoFrames + shellShown);
        return metrics;
    }
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
    // OMNI_HOLEPUNCH_V7_QUALITY: the shell's counts (HolePacing: the plane's totals) for this video,
    // per pacing run from a baseline at the run's first report, summed over the runs.
    void v7PacingCounts()
    {
        const OmniMedia::Hw::HoleLink* link = m_holeLink.get();
        const bool on = link && link->pacing().state == 1 && link->pacing().atMs > 0;
        if (link != m_v7PacingLink || !on) {
            if (m_v7Pacing) { m_v7DoneShown += m_v7RunShown; m_v7DoneDropped += m_v7RunDropped; m_v7RunShown = m_v7RunDropped = 0; }
            m_v7Pacing = false; m_v7PacingLink = link;
        }
        if (!on) return;
        const auto& pacing = link->pacing();
        if (!m_v7Pacing) { m_v7Pacing = true; m_v7BaseShown = pacing.shown; m_v7BaseDropped = pacing.dropped; }
        m_v7RunShown = pacing.shown >= m_v7BaseShown ? pacing.shown - m_v7BaseShown : 0;
        m_v7RunDropped = pacing.dropped >= m_v7BaseDropped ? pacing.dropped - m_v7BaseDropped : 0;
    }
    bool seeking() const { return m_seekPromise.has_value(); }
    // OMNI_PLAYBACK_RATE_V1: playbackRate 0.25 .. 2.0. The playhead (and the shell's clock for a
    // hole-punched video) advances at the rate; the audio is time-stretched (pitch kept).
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
        m_rate = rate;
        if (rate > 0 && rate != m_rateAudio.rate()) {
            // What is queued was stretched for the old rate: clear it and start again from what is
            // heard now, at the new rate (RateAudio keeps the unstretched input).
            const auto heard = audioPlayhead(m_position + 0.5);
            const double from = heard ? *heard : m_position;
            if (m_audioRing && m_audio) {
                m_audio->lock(); m_audioRing->clear(); m_audio->unlock();
                if (!m_rateAudio.setRate(rate, from)) m_rateAudio.reset();
                rateAudioFlush();
            } else m_rateAudio.setRateNoRefeed(rate);
        }
        if (m_rateLogs < 8) { ++m_rateLogs; fprintf(stderr, "OMNI RATE: MSE player %.2f -> %.2f (requested %.3f)\n", previous, rate, requested); fflush(stderr); }
        RunLoop::mainSingleton().dispatch([weak = WeakPtr { *this }] { if (weak) if (RefPtr player = weak->m_player.get()) player->rateChanged(); });
    }
    // The ring takes what RateAudio has ready (pass-through at rate 1).
    void rateAudioFlush()
    {
        if (!m_audioRing) return;
        int16_t buffer[4096 * 2];
        for (int guard = 0; guard < 64; guard++) {
            const size_t room = std::min<size_t>(m_audioRing->roomFrames(), 4096);
            if (room < size_t(OmniMedia::Rate::TimeStretch::hop)) return;
            double media = 0, speed = 1;
            const size_t n = m_rateAudio.pull(buffer, room, media, speed);
            if (!n || !m_audioRing->write(buffer, n, media, speed)) return;
        }
    }
    MediaTime duration() const final { return m_source ? m_source->duration() : MediaTime::invalidTime(); }
    MediaTime currentTime() const final
    {
        auto position = MediaTime::createWithDouble(m_position);
        auto length = duration();
        // HTMLMediaElement treats currentTime >= duration as EOF, independently
        // of ended(). Keep the terminal position private until both the decoder
        // and queued audio have drained; otherwise script can tear down playback
        // on its ended event while the final audio is still queued.
        return Omni::mseReportedTime(position, length, m_ended, MediaTime(1, 1000000));
    }
    FloatSize naturalSize() const final { return m_size; }
    bool hasVideo() const final { return m_source && m_source->hasVideo(); }
    bool hasAudio() const final { return m_source && m_source->hasAudio(); }
    bool supportsFullscreen() const final { return true; }
    MediaPlayer::NetworkState networkState() const final { return m_network; }
    MediaPlayer::ReadyState readyState() const final { return m_ready; }
    const PlatformTimeRanges& buffered() const final { return m_ranges; }
    const PlatformTimeRanges& seekable() const final { return m_seekable; }
    MediaTime maxTimeSeekable() const final { return duration(); }
    bool didLoadingProgress() const final { return m_network == MediaPlayer::NetworkState::Loading; }
    // Script-visible appended bytes already passed the page's fetch/CORS rules.
    bool didPassCORSAccessCheck() const final { return true; }
    std::optional<bool> isCrossOrigin(const SecurityOrigin&) const final { return false; }
    void setVolume(float value) final
    {
        m_volume = std::isfinite(value) ? std::clamp(value, 0.0f, 1.0f) : 0;
        if (m_audioRing) m_audioRing->setGain(m_muted ? 0 : m_volume); // OMNI_HOLEPUNCH_V5: applied as it plays
    }
    void setMuted(bool value) final
    {
        m_muted = value;
        if (m_audioRing) m_audioRing->setGain(m_muted ? 0 : m_volume); // OMNI_HOLEPUNCH_V5: no need to drop what is queued
        else if (value && m_audio) m_audio->clearQueued();
    }
    void setPageIsVisible(bool value) final { m_visible = value; }
    void readyStateFromMediaSourceChanged() final { changed(); }
    void characteristicsFromMediaSourceChanged() final { changed(); }
    void seekableRangesFromMediaSourceChanged() final { changed(); }
    Ref<MediaTimePromise> seekToTarget(const SeekTarget& target) final
    {
        if (!m_source) return MediaTimePromise::createAndReject(PlatformMediaError::Cancelled);
        m_seekPromise.emplace(PlatformMediaError::Cancelled);
        auto generation = ++m_seekGeneration;
        auto promise = m_seekPromise->promise();
        m_source->flushPlayback();
        if (m_audio) { m_audio->pause(true); clearAudio(); } // OMNI_HOLEPUNCH_V5: clearAudio
        m_image = nullptr; m_scaled = nullptr;
        m_holeDue = nullptr; m_holeHasFrame = false; // OMNI_HOLEPUNCH_V1
        m_audioDiscardBefore.reset(); m_videoDiscardBefore.reset();
        const double from = m_position; // OMNI_HOLEPUNCH_V5_REV3: a small forward step (hls.js's stall nudge) is no full seek hold
        m_source->waitForTarget(target)->whenSettled(RunLoop::mainSingleton(), [weak = WeakPtr { *this }, generation, from](auto&& result) {
            RefPtr self = weak.get();
            if (!self || !self->m_source || !self->m_seekPromise || generation != self->m_seekGeneration) return;
            if (!result) { auto pending = std::exchange(self->m_seekPromise, std::nullopt); pending->reject(result.error()); return; }
            auto time = *result;
            self->m_source->reenqueueMediaForTime(time)->whenSettled(RunLoop::mainSingleton(), [weak, time, generation, from](auto&& requeued) {
                RefPtr self = weak.get();
                if (!self || !self->m_seekPromise || generation != self->m_seekGeneration) return;
                auto pending = std::exchange(self->m_seekPromise, std::nullopt);
                if (!requeued) { pending->reject(PlatformMediaError::Cancelled); return; }
                self->m_position = time.toDouble(); self->m_anchor = MonotonicTime::now(); self->m_ended = false;
                const double step = time.toDouble() - from;
                self->v5Hold(step >= 0 && step < 0.5 ? "nudge" : "seek"); // OMNI_HOLEPUNCH_V5_REV2 (V5_REV3: "nudge": audio only, 0.5 s at most)
                self->m_audioDiscardBefore = self->m_videoDiscardBefore = self->m_position;
                pending->resolve(time);
                if (RefPtr player = self->m_player.get()) player->timeChanged();
            });
        });
        return promise;
    }
    // Video frame scaling quality, from /data/omni/video-quality.txt ("default",
    // "low" = bilinear without mipmaps, "none" = nearest). Read once per process.
    static int videoQuality()
    {
        static int quality = [] {
            int value = 0;
            if (FILE* f = fopen("/data/omni/video-quality.txt", "r")) {
                char word[16] = { };
                if (fscanf(f, "%15s", word) == 1)
                    value = !strcmp(word, "low") ? 1 : !strcmp(word, "none") ? 2 : !strcmp(word, "direct") ? 3 : 0;
                fclose(f);
            }
            fprintf(stderr, "OMNI VIDEO PAINT: quality=%s\n", value == 1 ? "low" : value == 2 ? "none" : value == 3 ? "direct" : "prescaled");
            fflush(stderr);
            return value;
        }();
        return quality;
    }
    // The current frame scaled to w x h (bilinear), built once per frame and size.
    RefPtr<NativeImage> scaledFrame(int w, int h)
    {
        // OMNI_VIDEO_TARGET_V1: the decoder already converted it to this size.
        if (m_image->size() == IntSize(w, h))
            return m_image;
        if (m_scaled && m_scaledSerial == m_imageSerial && m_scaledWidth == w && m_scaledHeight == h)
            return m_scaled;
        m_scaled = nullptr;
        SkPixmap source;
        const auto& platform = m_image->platformImage();
        if (!platform || !platform->peekPixels(&source))
            return nullptr;
        auto info = SkImageInfo::Make(w, h, source.colorType(), source.alphaType());
        size_t rowBytes = size_t(w) * 4;
        auto data = SkData::MakeUninitialized(rowBytes * size_t(h));
        SkPixmap target(info, data->writable_data(), rowBytes);
        if (!source.scalePixels(target, SkSamplingOptions(SkFilterMode::kLinear)))
            return nullptr;
        m_scaled = NativeImage::create(SkImages::RasterFromData(info, std::move(data), rowBytes));
        m_scaledSerial = m_imageSerial; m_scaledWidth = w; m_scaledHeight = h;
        return m_scaled;
    }
    void paint(GraphicsContext& context, const FloatRect& rect) final
    {
        // OMNI_HOLEPUNCH_V1: the shell draws the video under the page. Leave a transparent
        // hole: the page bitmap (and the UI backing store, updated with CompositeOperator::Copy)
        // keeps alpha 0 here, and the shell blends the page over its video plane.
        if (m_holePunch.holeActive()) {
            if (m_visible) { context.clearRect(rect); ++m_holePaintClears; }
            return;
        }
        if (m_image && m_visible) {
            auto paintStart = MonotonicTime::now();
            int quality = videoQuality();
            // Default: scale each frame once (bilinear) to its size in device pixels
            // and keep it; WebKit paints the video several times per frame (one call
            // per dirty rectangle, ~4 measured), and those become 1:1 copies.
            bool drawn = false;
            if (!quality) {
                AffineTransform ctm = context.getCTM();
                double sx = ctm.xScale(), sy = ctm.yScale();
                int w = int(std::lround(rect.width() * sx)), h = int(std::lround(rect.height() * sy));
                if (!ctm.b() && !ctm.c() && sx > 0 && sy > 0 && w > 0 && h > 0 && w <= 4096 && h <= 4096) {
                    if (m_source) m_source->setVideoTargetSize(w, h); // OMNI_VIDEO_TARGET_V1
                    if (RefPtr<NativeImage> scaled = scaledFrame(w, h)) {
                        GraphicsContextStateSaver saver(context);
                        context.translate(rect.x(), rect.y());
                        context.scale(FloatSize(float(1 / sx), float(1 / sy)));
                        context.drawNativeImage(*scaled, FloatRect(0, 0, w, h), FloatRect(0, 0, w, h), ImagePaintingOptions(InterpolationQuality::DoNotInterpolate));
                        drawn = true;
                    }
                }
            }
            if (drawn) { }
            else if (quality == 1)
                context.drawNativeImage(*m_image, rect, FloatRect({ }, FloatSize(m_image->size())), ImagePaintingOptions(InterpolationQuality::Low));
            else if (quality == 2)
                context.drawNativeImage(*m_image, rect, FloatRect({ }, FloatSize(m_image->size())), ImagePaintingOptions(InterpolationQuality::DoNotInterpolate));
            else
                context.drawNativeImage(*m_image, rect, FloatRect({ }, FloatSize(m_image->size())));
            double paintMs = (MonotonicTime::now() - paintStart).seconds() * 1000;
            ++m_paintCalls; m_paintTotalMs += paintMs; m_paintMaxMs = std::max(m_paintMaxMs, paintMs);
            if (!(m_paintCalls % 120) && m_paintCalls <= 1200) {
                fprintf(stderr, "OMNI VIDEO PAINT: calls=%llu avgMs=%.3f maxMs=%.3f dest=%.0fx%.0f source=%.0fx%.0f\n",
                    static_cast<unsigned long long>(m_paintCalls), m_paintTotalMs / m_paintCalls, m_paintMaxMs,
                    rect.width(), rect.height(), m_size.width(), m_size.height());
                fflush(stderr);
            }
            if (m_imageSerial != m_lastPaintedSerial) {
                m_lastPaintedSerial = m_imageSerial;
                ++m_displayedVideoFrames;
                if (m_displayedVideoFrames == 1) diagnostic("first-video-painted");
            }
        }
    }
    ColorSpace colorSpace() final { return ColorSpace::SRGB(); }
    RefPtr<NativeImage> nativeImageForCurrentTime() final
    {
        m_holeCanvasUntil = MonotonicTime::now() + 1_s; // OMNI_HOLEPUNCH_V1: keep m_image current
        return m_image;
    }
    // OMNI_VIDEO_TARGET_V1: canvas drawImage(video) and snapshots draw the current frame
    // without touching the decoder's on-page target size (the default calls paint(), and a
    // small canvas would otherwise make the page's video decode small and blurry).
    void paintCurrentFrameInContext(GraphicsContext& context, const FloatRect& rect) final
    {
        // OMNI_HOLEPUNCH_V1: while the shell shows the video, m_image is converted for every
        // presented frame for the next second, so canvas readers get real pixels, never the hole.
        m_holeCanvasUntil = MonotonicTime::now() + 1_s;
        if (m_image && m_visible)
            context.drawNativeImage(*m_image, rect, FloatRect({ }, FloatSize(m_image->size())));
    }
private:
    void notifyPlayback() { if (RefPtr player = m_player.get()) player->playbackStateChanged(); }
    void fail()
    {
        ++m_errors;
        diagnostic("error", true);
        cancelLoad(); m_network = MediaPlayer::NetworkState::DecodeError;
        if (RefPtr player = m_player.get()) { player->networkStateChanged(); player->readyStateChanged(); }
    }
    void diagnostic(const char* event, bool terminal = false)
    {
        if (m_diagnosticLines >= (terminal ? 16U : 14U)) return;
        ++m_diagnosticLines;
        fprintf(stderr, "OMNI MSE: %s time=%.6f decodedAccepted=%llu painted=%llu dropped=%llu droppedUnpainted=%llu discardedPreroll=%llu discardedSeek=%llu pixelOrder=%s pcmSubmittedFrames=%llu pcmChunks=%llu errors=%llu width=%.0f height=%.0f ticks=%llu pumpTotalMs=%.3f pumpMaxMs=%.3f intertickMaxMs=%.3f source=%.160s sdl=%.160s\n",
            event, m_position, static_cast<unsigned long long>(m_decodedVideoFrames),
            static_cast<unsigned long long>(m_displayedVideoFrames), static_cast<unsigned long long>(m_droppedVideoFrames),
            static_cast<unsigned long long>(m_replacedUnpaintedFrames), static_cast<unsigned long long>(m_discardedPrerollFrames),
            static_cast<unsigned long long>(m_discardedSeekFrames), m_lastFrameBGRA ? "bgra" : "rgba",
            static_cast<unsigned long long>(m_pcmSubmittedFrames), static_cast<unsigned long long>(m_pcmSubmittedChunks),
            static_cast<unsigned long long>(m_errors), double(m_size.width()), double(m_size.height()),
            static_cast<unsigned long long>(m_profileTicks), m_pumpTotalMilliseconds, m_pumpMaxMilliseconds,
            m_maxIntertickMilliseconds, m_source ? m_source->error().c_str() : "none", SDL_GetError());
        fflush(stderr);
    }
    void changed()
    {
        Ref protect { *this };
        RefPtr source = m_source;
        if (!source) return;
        synchronizePresentation(*source);
        if (m_source != source) return;
        m_ranges = source->buffered(); m_seekable = source->seekable();
        m_ready = source->mediaPlayerReadyState();
        m_network = source->isEnded() ? MediaPlayer::NetworkState::Loaded : MediaPlayer::NetworkState::Loading;
        if (RefPtr player = m_player.get()) { player->durationChanged(); player->readyStateChanged(); player->networkStateChanged(); player->characteristicChanged(); }
    }
    void synchronizePresentation(OmniMSESource& source)
    {
        if (m_audioPresentationGeneration != source.audioPresentationGeneration()) {
            m_audioPresentationGeneration = source.audioPresentationGeneration();
            if (m_audio) { m_audio->pause(true); clearAudio(); } // OMNI_HOLEPUNCH_V5: clearAudio
            m_audioDiscardBefore = m_position;
        }
        if (m_videoPresentationGeneration != source.videoPresentationGeneration()) {
            m_videoPresentationGeneration = source.videoPresentationGeneration();
            m_image = nullptr; m_scaled = nullptr;
            m_holeDue = nullptr; m_holeHasFrame = false; // OMNI_HOLEPUNCH_V1
            m_videoDiscardBefore = m_position;
            if (RefPtr player = m_player.get()) player->repaint();
        }
    }
    bool outputFailure(const char* stage, const OmniMedia::DecodedOutput& output)
    {
        // Constant stage labels and numeric frame metadata only; no media URLs,
        // packet bytes, cookies or page text. One detail line per failed tick.
        if (!m_outputError && m_diagnosticLines < 15U) {
            ++m_diagnosticLines;
            fprintf(stderr, "OMNI MSE: output-failure stage=%s kind=%u timestamp-valid=%d timestamp=%lld timebase=%d/%d width=%d height=%d rgba=%zu pcm=%zu device=%u\n",
                stage, static_cast<unsigned>(output.kind), output.hasTimestamp,
                static_cast<long long>(output.timestamp), output.timeBase.numerator, output.timeBase.denominator,
                output.width, output.height, output.rgba.size(), output.pcm.size(), m_audio ? m_audio->id() : 0u);
            fflush(stderr);
        }
        m_outputError = true;
        return false;
    }
    bool consume(OmniMedia::DecodedOutput& output)
    {
        // Decode dependencies must still run, but hidden preroll must never
        // become a poster frame or enter SDL's audio queue.
        if (output.nonDisplaying) {
            if (output.kind == OmniMedia::DecodedOutput::Kind::Video) { ++m_decodedVideoFrames; ++m_droppedVideoFrames; ++m_discardedPrerollFrames; }
            return true;
        }
        if (!output.hasTimestamp) return outputFailure("timestamp-missing", output);
        if (output.timeBase.denominator <= 0) return outputFailure("timebase-denominator", output);
        double time = double(output.timestamp) * output.timeBase.numerator / output.timeBase.denominator;
        if (!std::isfinite(time)) return outputFailure("timestamp-nonfinite", output);
        if (output.kind == OmniMedia::DecodedOutput::Kind::Video) {
            // Decode keyframe preroll, but do not display frames before the
            // resolved seek target. The first target-or-later frame is a poster.
            if (m_videoDiscardBefore && time + 0.000001 < *m_videoDiscardBefore) {
                ++m_decodedVideoFrames; ++m_droppedVideoFrames; ++m_discardedSeekFrames; return true;
            }
            // OMNI_HOLEPUNCH_V5_REV3: while the shell paces, its queue shows this video. A hole frame that
            // still reaches the player (decoded into an output slot before pacing began) and is ahead of
            // the playhead must not stop the pump: refused, it kept the decoder from being fed, the shell's
            // queue stayed empty and the start/seek hold waited 3 s (hls.js nudged meanwhile). Free its slot.
            if (m_v5 && output.hole && m_holePunch.paced() && (m_image || m_holeHasFrame) && time > m_position + 0.005) {
                ++m_decodedVideoFrames; ++m_droppedVideoFrames; ++m_discardedPrerollFrames; return true;
            }
            if ((m_image || m_holeHasFrame) && time > m_position + 0.005) return false;
            if (output.hole) { // OMNI_HOLEPUNCH_V1: hardware frame still in its decode slot
                m_holeLink = output.hole->link();
                if (m_holePunch.presenting()) {
                    // Due: the shell shows it (tick). A newer due frame replaces it unshown.
                    if (m_holeDue) { ++m_droppedVideoFrames; ++m_replacedUnpaintedFrames; }
                    m_holeDue = std::move(output.hole);
                    m_holeDueTime = time; // OMNI_HOLEPUNCH_V3
                    m_holeHasFrame = true;
                    ++m_decodedVideoFrames;
                    m_videoDiscardBefore.reset();
                    FloatSize newSize { float(output.sourceWidth), float(output.sourceHeight) };
                    if (newSize != m_size) { m_size = newSize; if (RefPtr player = m_player.get()) player->sizeChanged(); }
                    return true;
                }
                // Paint path: convert now, then free the slot. A frame of a decoder that has
                // since fallen back to software is gone: drop it, as a seek would.
                if (!output.hole->link()->alive()) { ++m_decodedVideoFrames; ++m_droppedVideoFrames; return true; }
                // OMNI_HOLEPUNCH_V5: after a stall the playhead moves by the whole gap; a frame 100 ms
                // late would be replaced at once: free its slot without converting it.
                if (m_v5 && m_image && time + 0.1 < m_position) { ++m_decodedVideoFrames; ++m_droppedVideoFrames; ++m_replacedUnpaintedFrames; return true; }
                if (!output.hole->convert(output)) return outputFailure("hole-convert", output);
                output.hole = nullptr;
            }
            if (output.width <= 0 || output.height <= 0 || int64_t(output.width) * output.height > OmniMedia::PacketDecoder::maxPixels
                || output.rgba.size() != size_t(output.width) * output.height * 4) return outputFailure("video-layout", output);
            // Opaque decoded video needs neither alpha blending nor unpremultiply
            // handling. Preserve the existing path for alpha/unknown formats.
            auto info = SkImageInfo::Make(output.width, output.height, output.bgra ? kBGRA_8888_SkColorType : kRGBA_8888_SkColorType,
                output.opaque ? kOpaque_SkAlphaType : kUnpremul_SkAlphaType);
            if (m_image && m_imageSerial != m_lastPaintedSerial) { ++m_droppedVideoFrames; ++m_replacedUnpaintedFrames; }
            m_lastFrameBGRA = output.bgra;
            // v53: hand the decoded buffer to Skia instead of copying it again.
            // The pixels are never written after this point; SkData frees them.
            auto* pixels = new std::vector<uint8_t>(std::move(output.rgba));
            auto pixelData = SkData::MakeWithProc(pixels->data(), pixels->size(),
                [](const void*, void* context) { delete static_cast<std::vector<uint8_t>*>(context); }, pixels);
            m_image = NativeImage::create(SkImages::RasterFromData(info, std::move(pixelData), size_t(output.width) * 4));
            m_scaled = nullptr;
            if (!m_image) return outputFailure("video-native-image", output);
            m_imageSerial = ++m_decodedVideoFrames;
            // OMNI_VIDEO_TARGET_V1: pixels may be pre-scaled for display; the natural
            // size (videoWidth/videoHeight, aspect ratio) stays the source picture's.
            FloatSize newSize { float(output.sourceWidth > 0 ? output.sourceWidth : output.width),
                                float(output.sourceHeight > 0 ? output.sourceHeight : output.height) };
            bool sizeChanged = newSize != m_size;
            m_size = newSize;
            m_videoDiscardBefore.reset();
            // WebKit's size callback updates the renderer even when dimensions
            // are unchanged. Report real format-size transitions only, while
            // retaining repaint for every newly accepted frame.
            if (RefPtr player = m_player.get()) {
                if (sizeChanged) player->sizeChanged();
                player->repaint();
            }
            return true;
        }
        if (output.pcm.size() % 2) return outputFailure("audio-channel-alignment", output);
        size_t skippedFrames = 0;
        if (m_audioDiscardBefore) {
            double skip = std::ceil((*m_audioDiscardBefore - time) * 48000.0 - 0.000001);
            skippedFrames = size_t(std::clamp(skip, 0.0, double(output.pcm.size() / 2)));
            if (skippedFrames == output.pcm.size() / 2) return true;
            time += double(skippedFrames) / 48000;
        }
        if (time > m_position + (m_v5 && m_audio ? 3.0 : 0.15)) return false; // OMNI_HOLEPUNCH_V5: ~3 s ahead (V4: 0.15 s); V5_REV2: only with a device
        // OMNI_HOLEPUNCH_V5_REV2: one audio init attempt per tick at most, the next one spaced from when
        // this one ended (audioInitFinish). An attempt can block for seconds (0x80260002: the port
        // is still held); the retry gate below counts from the attempt's start, so in rev 1 every
        // later output of the same pump (48 of them) tried again: a frozen tick.
        if (!m_audio && m_v5) {
            const double t = OmniMedia::Hw::nowMs();
            if (m_audioInitThisTick || t < m_audioInitNotBeforeMs) return m_audioUnavailable;
            m_audioInitThisTick = true; m_audioInitEnteredMs = t;
        }
        if (!m_audio) {
            SDL_SetMainReady();
            // The audio output can still belong to a page process that is exiting
            // (sceAudioOutInit 0x80260002 seen when a player started right after
            // another closed). Retry every 250 ms for up to 5 s before failing.
            uint32_t now = SDL_GetTicks();
            // OMNI_AUDIO_FALLBACK_V1: while audio is unavailable, due audio is dropped (accepted)
            // so video keeps playing on the wall clock; retry the output every 2 s.
            // OMNI_AUDIO_RELAY_V1: never fatal: every failure (relay, init, device open) lands here; the
            // retries back off from 2 s to 16 s.
            if (m_audioRetryStart && now - m_audioLastAttempt < (m_audioUnavailable ? m_audioRetryDelayMs : 250u)) return m_audioUnavailable;
            m_audioLastAttempt = now;
            // OMNI_AUDIO_RELAY_V1: the UI process plays it (the system drops what a WebProcess's own device
            // plays: v83, loud PCM at the device, silence on the TV); this process's own device only
            // when the relay is off or cannot take this player.
            std::string why;
            m_audio = OmniMedia::Audio::Output::openRelay(why);
            if (m_audio) {
                m_audioRing = m_audio->makeRingView();
                m_audioRing->setGain(m_muted ? 0 : m_volume);
                m_rateAudio.reset(); // OMNI_PLAYBACK_RATE_V1
                m_audioDeviceFrames = m_audio->deviceFrames();
                fprintf(stderr, "OMNI AUDIO DEVICE: %s; the player's ring (%s)%s\n", m_audio->describe().c_str(), m_v5 ? "V5, 3 s ahead" : "V4 lead, 0.15 s ahead",
                    m_audioRetryStart ? " after retries" : "");
                fflush(stderr);
            } else {
                if (m_audioRelayLogs < 4) { ++m_audioRelayLogs; fprintf(stderr, "OMNI AUDIO DEVICE: relay unavailable (%s); this process's own SDL output\n", why.c_str()); fflush(stderr); }
                if (!m_audioInitialized && SDL_InitSubSystem(SDL_INIT_AUDIO)) return audioOpenFailed(now, "audio init");
                m_audioInitialized = true;
                SDL_AudioSpec wanted { }, actual { };
                wanted.freq = 48000; wanted.channels = 2; wanted.format = AUDIO_S16LSB; wanted.samples = 1024;
                if (m_v5) { // OMNI_HOLEPUNCH_V5: SDL's audio thread plays from our ring (callback), not SDL's queue
                    m_audioRing = std::make_unique<OmniMedia::AudioRing>(48000 * 7 / 2);
                    m_audioRing->setGain(m_muted ? 0 : m_volume);
                    m_rateAudio.reset(); // OMNI_PLAYBACK_RATE_V1
                    wanted.callback = audioCallback; wanted.userdata = m_audioRing.get();
                }
                m_audio = OmniMedia::Audio::Output::openSdl(&wanted, &actual); // OMNI_AUDIO_RELAY_V1: Output
                if (!m_audio) { m_audioRing = nullptr; return audioOpenFailed(now, "audio device open"); } // V4/V5: a fatal output-failure
                // OMNI_HOLEPUNCH_V5_REV3: what SDL's driver gave (it converts to it when no change is allowed:
                // the ring's callback must see 48 kHz stereo s16); otherwise SDL's own queue, as V4.
                const bool specOk = actual.freq == 48000 && actual.format == AUDIO_S16LSB && actual.channels == 2;
                fprintf(stderr, "OMNI AUDIO DEVICE: driver=%s device=%u obtained freq=%d format=0x%04x channels=%u samples=%u size=%u silence=%u%s; %s\n",
                    SDL_GetCurrentAudioDriver() ? SDL_GetCurrentAudioDriver() : "?", m_audio->id(), actual.freq, unsigned(actual.format), unsigned(actual.channels),
                    unsigned(actual.samples), unsigned(actual.size), unsigned(actual.silence), specOk ? "" : " (NOT 48000/0x8010/2)",
                    m_audioRing ? (specOk ? "ring callback (V5)" : "reopening with SDL's queue") : "SDL's queue (V4)");
                fflush(stderr);
                if (m_audioRing && !specOk) {
                    m_audio = nullptr; m_audioRing = nullptr;
                    wanted.callback = nullptr; wanted.userdata = nullptr;
                    m_audio = OmniMedia::Audio::Output::openSdl(&wanted, &actual);
                    if (!m_audio) return audioOpenFailed(now, "audio device reopen");
                }
                m_audioDeviceFrames = actual.samples ? actual.samples : 1024; // OMNI_HOLEPUNCH_V5
            }
            if (m_audioRetryStart) { fprintf(stderr, "OMNI AUDIO INIT: succeeded after %u ms of retries\n", now - m_audioRetryStart); fflush(stderr); }
            m_audioRetryStart = 0; m_audioUnavailable = false; m_audioRetryDelayMs = 2000;
            m_audioOutputLogMs = 0; m_audioOutputLines = 0;
            // tick controls device state after checking buffering/seeking.
            m_audio->pause(true);
            if (m_v5) { // OMNI_HOLEPUNCH_V5_REV2: the playhead waits for ~1 s in the ring; audio before it is late
                v5Hold("audio device opened");
                if (m_position > 0) { m_audioDiscardBefore = m_position; return false; }
            }
        }
        constexpr size_t audioLimit = 48000 * 2 * sizeof(int16_t) * 2;
        size_t skippedSamples = skippedFrames * 2;
        size_t bytes = (output.pcm.size() - skippedSamples) * sizeof(int16_t);
        if (m_audioRing) { // OMNI_HOLEPUNCH_V5: into the ring; the volume is applied as it plays
            const size_t frames = bytes / (2 * sizeof(int16_t));
            if (bytes > audioLimit) { m_audioDiscardBefore.reset(); return true; } // OMNI_AUDIO_RELAY_V1: dropped, never fatal
            // OMNI_PLAYBACK_RATE_V1: through RateAudio (a pass-through at rate 1, time-stretched otherwise);
            // the ring takes it as it has room (as before: full -> next tick).
            rateAudioFlush();
            if (m_rateAudio.backlogFrames() > 9600) return false; // full: next tick
            m_rateAudio.push(output.pcm.data() + skippedSamples, frames, time);
            rateAudioFlush();
            auto previousSeconds = m_pcmSubmittedFrames / (48000 * 3);
            m_pcmSubmittedFrames += frames;
            ++m_pcmSubmittedChunks;
            if (m_pcmSubmittedChunks == 1 || m_pcmSubmittedFrames / (48000 * 3) != previousSeconds) diagnostic("pcm-submitted-not-audibility-proof");
            m_audioDiscardBefore.reset();
            return true;
        }
        if (bytes > audioLimit) { m_audioDiscardBefore.reset(); return true; } // OMNI_AUDIO_RELAY_V1: dropped, never fatal (was output-failure)
        if (m_rate != 1) { m_audioDiscardBefore.reset(); return true; } // OMNI_PLAYBACK_RATE_V1: V4's queue path (no ring) plays rate 1 only: muted otherwise
        if (m_audio->queuedBytes() > audioLimit - bytes) return false;
        float gain = m_muted ? 0 : m_volume;
        for (size_t i = skippedSamples; i < output.pcm.size(); ++i) output.pcm[i] = int16_t(output.pcm[i] * gain);
        if (m_audio->queue(output.pcm.data() + skippedSamples, unsigned(bytes))) { m_audioDiscardBefore.reset(); return true; } // OMNI_AUDIO_RELAY_V1: dropped, never fatal
        auto previousSeconds = m_pcmSubmittedFrames / (48000 * 3);
        m_pcmSubmittedFrames += bytes / (2 * sizeof(int16_t));
        m_holeAudioQueueEnd = time + double(bytes / (2 * sizeof(int16_t))) / 48000; // OMNI_HOLEPUNCH_V4: end of the queued audio
        ++m_pcmSubmittedChunks;
        if (m_pcmSubmittedChunks == 1 || m_pcmSubmittedFrames / (48000 * 3) != previousSeconds) diagnostic("pcm-submitted-not-audibility-proof");
        m_audioDiscardBefore.reset();
        return true;
    }
    void tick()
    {
        Ref protect { *this };
        RefPtr source = m_source;
        if (!source) return;
        auto profileNow = MonotonicTime::now();
        if (m_previousProfileTick)
            m_maxIntertickMilliseconds = std::max(m_maxIntertickMilliseconds, (profileNow - *m_previousProfileTick).seconds() * 1000);
        m_previousProfileTick = profileNow;
        ++m_profileTicks;
        // OMNI_AUDIO_RELAY_V1: paused for 60 s: the audio output goes back (the relay's channel and ring,
        // or this process's device). On play the media is enqueued again from the playhead (as a seek
        // to it): what the ring held is gone, and the output opens again with the next audio.
        if (m_audio && m_paused && m_pausedSince && (profileNow - *m_pausedSince).seconds() > 60) {
            audioRelease("paused for 60 s");
            m_audioReleasedPaused = true;
        }
        if (m_audioReleasedPaused && !m_paused && !m_seekPromise) {
            m_audioReleasedPaused = false;
            source->flushPlayback();
            (void)source->reenqueueMediaForTime(MediaTime::createWithDouble(m_position));
        }
        synchronizePresentation(*source);
        if (m_source != source) return;
        auto generation = m_seekGeneration;
        auto audioGeneration = source->audioPresentationGeneration();
        auto videoGeneration = source->videoPresentationGeneration();
        auto now = MonotonicTime::now();
        displayLockTick(*source); // OMNI_PERF_C_V4
        // OMNI_HOLEPUNCH_V5: a tick 2-3 s after the previous one (watch page) moves the playhead
        // by the whole gap: the audio ring played on meanwhile. V4 stepped at most 0.25 s and
        // lost the rest of every longer gap (clockDriftMs ~1800 on the console).
        double delta = std::clamp((now - m_anchor).seconds(), 0.0, m_v5 ? 3.0 : 0.25);
        m_anchor = now;
        // Do not run the wall clock through an initial empty buffer or a gap:
        // nextStallTime alone returns duration when currentTime has no range.
        auto internalPosition = MediaTime::createWithDouble(m_position);
        bool bufferedHere = source->buffered().find(internalPosition) != notFound;
        if (!bufferedHere && !m_paused && !m_seekPromise) { // OMNI_MSE_START_GAP_V1: jump a small gap ahead
            const auto& ranges = source->buffered();
            for (unsigned i = 0; i < ranges.length(); ++i) {
                double start = ranges.start(i).toDouble();
                if (start > m_position && start - m_position <= (m_position < 0.1 ? 1.0 : 0.25)) { // OMNI_MSE_START_GAP_V2: 1 s at the start, 0.25 s later (WebKit's allowances)
                    fprintf(stderr, "OMNI MSE: skipped a %.3f s gap at %.3f (buffered from %.3f)\n", start - m_position, m_position, start); fflush(stderr);
                    m_position = start; internalPosition = MediaTime::createWithDouble(m_position); bufferedHere = true;
                    break;
                }
            }
        }
        if (m_audioInitThisTick) audioInitFinish(); // OMNI_HOLEPUNCH_V5_REV2: the previous tick returned early
        if (m_v5 && v5HoldTick(*source)) {
            delta = 0; // Released now: do not advance through the hold.
            // Startup release may block before returning. Anchor the playing
            // clock after that path so held time is not counted as playback.
            if (!strcmp(m_v5HoldReason, "start"))
                m_anchor = MonotonicTime::now();
        }
        m_traceAfterHoldUs = int64_t(MonotonicTime::now().secondsSinceEpoch().milliseconds() * 1000);
        if (!m_paused && !m_seekPromise && bufferedHere && !m_v5Hold) {
            auto stall = source->nextStallTime(internalPosition);
            double target = m_position + delta * clockRate(); // OMNI_PLAYBACK_RATE_V1; OMNI_PERF_C_V4: x the display lock
            if (auto heard = audioPlayhead(target)) { m_v5AudioVsWallMs = std::max(m_v5AudioVsWallMs, std::fabs(*heard - target) * 1000); target = *heard; } // OMNI_HOLEPUNCH_V5: audio is the master while it plays
            if (stall.isValid()) m_position = std::max(m_position, std::min(target, stall.toDouble()));
        }
        m_traceBeforeRingUs = int64_t(MonotonicTime::now().secondsSinceEpoch().milliseconds() * 1000);
        if (m_audioRing) audioRingTick(source->isEnded()); // OMNI_HOLEPUNCH_V5
        if (m_seekPromise) { if (m_audio) m_audio->pause(true); return; }
        if (!tabMediaTick(*source)) return; // OMNI_TAB_MEDIA_RELEASE_V1
        m_outputError = false;
        auto pumpStart = MonotonicTime::now();
        m_tracePumpStartUs = int64_t(pumpStart.secondsSinceEpoch().milliseconds() * 1000);
        bool pumped = source->pump([this, source, generation, audioGeneration, videoGeneration](auto& output) {
            if (m_source != source || m_seekGeneration != generation || m_seekPromise
                || source->audioPresentationGeneration() != audioGeneration
                || source->videoPresentationGeneration() != videoGeneration) return false;
            return consume(output);
        });
        m_tracePumpEndUs = int64_t(MonotonicTime::now().secondsSinceEpoch().milliseconds() * 1000);
        // Consumer callbacks can replace/cancel the source or start a seek.
        if (m_source != source || m_seekGeneration != generation || m_seekPromise) return;
        double pumpMilliseconds = (MonotonicTime::now() - pumpStart).seconds() * 1000;
        if (m_audioInitThisTick) audioInitFinish(); // OMNI_HOLEPUNCH_V5_REV2
        m_pumpTotalMilliseconds += pumpMilliseconds;
        m_pumpMaxMilliseconds = std::max(m_pumpMaxMilliseconds, pumpMilliseconds);
        if (source->audioPresentationGeneration() != audioGeneration || source->videoPresentationGeneration() != videoGeneration) {
            synchronizePresentation(*source);
            return;
        }
        if (!pumped || m_outputError) {
            if (!pumped) diagnostic("source-pump-failed", true);
            fail(); return;
        }
        updateHolePunch(*source); // OMNI_HOLEPUNCH_V1
        auto length = source->duration();
        bool atEnd = source->isEnded() && length.isFinite() && m_position >= length.toDouble();
        if (m_audio) m_audio->pause(m_paused || (!bufferedHere && !atEnd) || m_v5Hold || m_rate <= 0); // OMNI_HOLEPUNCH_V5_REV2: m_v5Hold; OMNI_PLAYBACK_RATE_V1: rate 0
        if (m_audioDeviceLogPending) { // OMNI_HOLEPUNCH_V5_REV3: after a hold, the device must play
            m_audioDeviceLogPending = false; ++m_audioDeviceLogs;
            fprintf(stderr, "OMNI AUDIO DEVICE: after the hold: %s (paused=%d bufferedHere=%d atEnd=%d ring=%d queuedMs=%.0f gain=%.2f callbacks=%llu)\n",
                !m_audio ? "no device" : m_audio->statusName(), m_paused, bufferedHere, atEnd, !!m_audioRing, // OMNI_AUDIO_RELAY_V1: statusName
                m_audioRing ? m_audioRing->fillFrames() / 48.0 : -1.0, m_audioRing ? m_audioRing->gain() : (m_muted ? 0 : m_volume),
                static_cast<unsigned long long>(m_audioRing ? m_audioRing->callbackCalls() : 0));
            fflush(stderr);
        }
        if (!m_paused && atEnd && source->playbackDrained()
            && (!m_audio || !audioQueuedBytes())) { // OMNI_HOLEPUNCH_V5: audioQueuedBytes
            m_ended = m_paused = true;
            if (m_audio) m_audio->pause(true);
            diagnostic("ended", true);
            // HTMLMediaElement queues its finite-resource ended event from
            // mediaPlayerTimeChanged()/handlePlaybackPositionChanged(), not
            // playbackStateChanged(). The ordinary tick notification below is
            // skipped once paused, so explicitly deliver the terminal position.
            if (RefPtr player = m_player.get()) player->timeChanged();
            // A loop/seek/load can reenter through the position callback.
            if (m_source != source || m_seekGeneration != generation || !m_ended) return;
            notifyPlayback();
            return;
        }
        if (!m_paused) if (RefPtr player = m_player.get()) player->timeChanged();
    }
    // ---- OMNI_PERF_C_V4: the media clock locked to the display (OmniMSEClock.h) --------------
    // Content at 60 / 30 / 24 / 120 fps on the 59.94 Hz display plays at 1000/1001: the playhead, the
    // shell's clock and the audio (resampled, ClockAudio) all run at rate x lock, so the presenter never
    // has a picture too many (rateMismatch). Off: the SDL queue path (V4, no ring: no resampling there),
    // no video, the content's rate not known or not within 0.25 % of a display multiple, the flag.
    // Logged in the hold and stats lines (no line of its own: a stderr line can take ~200 ms here).
    double clockRate() const { return m_rate * m_lock; }
    void displayLockTick(OmniMSESource& source)
    {
        double want = 1;
        const bool queuePath = m_audio && !m_audioRing;
        if (m_lockEnabled && m_v5 && !queuePath && hasVideo())
            want = Omni::DisplayLock::factor(source.videoFrameRate(), Omni::DisplayLock::displayHz());
        if (want == m_lock) return;
        m_lock = want;
        m_rateAudio.setLock(want);   // what the ring holds keeps its speed (its runs say it): the clock stays exact
        ++m_lockChanges;
    }
    static bool holdShortEnabled() // OMNI_PERF_C_T2
    {
        if (const char* env = getenv("OMNI_STARTUP_HOLD_SHORT")) return env[0] != '0';
#ifdef __PROSPERO__
        return access("/data/omni/startup-hold-short-disabled.flag", F_OK) != 0;
#else
        return true;
#endif
    }
    static bool fastSwitchEnabled() // OMNI_PERF_C_V8
    {
        if (const char* env = getenv("OMNI_SWITCH_FAST_CLAIM")) return env[0] != '0';
#ifdef __PROSPERO__
        return access("/data/omni/switch-fast-claim-disabled.flag", F_OK) != 0;
#else
        return true;
#endif
    }
    // OMNI_PERF_C_V8: a quality switch's new stream claims the plane and is paced in ticks 3 ms apart
    // (the claim's answer comes from the service in about a millisecond), not 16+ ms apart; at most 6.
    void quickTick()
    {
        if (m_quickTickPending || m_quickTicks >= 6) return;
        m_quickTickPending = true; ++m_quickTicks;
        RunLoop::mainSingleton().dispatchAfter(3_ms, [weak = WeakPtr { *this }] {
            if (!weak) return;
            weak->m_quickTickPending = false;
            weak->tick();
        });
    }
    // ---- OMNI_HOLEPUNCH_V1 -----------------------------------------------------------------
    // The video's paint rect in view pixels (the shell's page buffer coordinates: root view,
    // after every frame's scroll), or false + reason when a hole would not work. Cheap: a
    // walk up the render tree and one quad mapping, once per tick.
    bool holeGeometry(OmniMedia::Hw::HoleLink::Rect& out, bool& onScreen, const char*& why)
    {
        RefPtr player = m_player.get();
        if (!player) { why = "no player"; return false; }
        HTMLMediaElement* element = nullptr;
        for (auto& candidate : HTMLMediaElement::allMediaElements()) {
            if (candidate->player() == player.get()) { element = candidate.ptr(); break; }
        }
        if (!element) { why = "no element"; return false; }
        auto* video = dynamicDowncast<RenderVideo>(element->renderer());
        if (!video) { why = "not rendered"; m_holeLastRect.reset(); return false; }
        if (video->view().frameView().needsLayout()) {   // mid-layout: keep the last answer
            if (!m_holeLastRect) { why = "layout pending"; return false; }
            out = *m_holeLastRect; onScreen = m_holeLastOnScreen;
            return true;
        }
        // A clear inside a transparency layer (opacity, filter, mask, clip-path, blend mode,
        // reflection) does not reach the page bitmap: such videos keep the paint path.
        for (const RenderElement* box = video; box; ) {
            for (const RenderElement* e = box; e; e = e->parent()) {
                if (e->isTransparent() || e->hasFilter() || e->hasBackdropFilter() || e->hasMask()
                    || e->hasClipPath() || e->hasBlendMode() || e->hasReflection()) {
                    why = "opacity, filter, mask, clip-path, blend or reflection on the way up";
                    m_holeLastRect.reset();
                    return false;
                }
            }
            auto* owner = box->document().ownerElement();   // inside an iframe: its ancestors too
            // Node::renderer() is defined in Node.h; ContainerNode::renderer() needs ContainerNodeInlines.h
            // (undefined inline) and a RenderElement->RenderElement downcast is a compile error.
            box = owner ? dynamicDowncast<RenderElement>(owner->Node::renderer()) : nullptr;
        }
        // Same rect RenderVideo::paintReplaced passes to paint() (object-fit, object-view-box).
        auto paintRect = video->computePaintRectForObjectViewBox(LayoutRect(video->videoBox()));
        auto quad = video->localToAbsoluteQuad(FloatQuad(FloatRect(paintRect)));
        if (!quad.isRectilinear()) { why = "rotated or skewed"; m_holeLastRect.reset(); return false; }
        auto& frameView = video->view().frameView();
        auto rect = roundedIntRect(frameView.contentsToRootView(quad).boundingBox());
        if (rect.width() < 2 || rect.height() < 2 || rect.width() > OmniMedia::Hw::Wire::holeMaxSide || rect.height() > OmniMedia::Hw::Wire::holeMaxSide
            || int64_t(rect.width()) * rect.height() > OmniMedia::Hw::Wire::holeMaxPixels) {
            why = "rect empty or larger than the video plane"; m_holeLastRect.reset(); return false;
        }
        out = { rect.x(), rect.y(), rect.width(), rect.height() };
        auto* rootView = frameView.root();
        onScreen = rootView && rect.intersects(IntRect(IntPoint(), rootView->size()));
        m_holeLastRect = out; m_holeLastOnScreen = onScreen;
        return true;
    }
    // m_image from a hole frame. forPage: a due frame the shell does not show, painted the
    // normal way; else only kept for canvas readers (the shell shows this frame).
    void holeImage(OmniMedia::Hw::HoleFrame& frame, bool forPage)
    {
        OmniMedia::DecodedOutput copy;
        if (frame.convert(copy)) holeImageFrom(copy, forPage);
    }
    // OMNI_HOLEPUNCH_V4: shared with the shell's snapshots (FrameSnapshot) of a paced video.
    void holeImageFrom(OmniMedia::DecodedOutput& copy, bool forPage)
    {
        if (copy.width <= 0 || copy.height <= 0 || copy.rgba.size() != size_t(copy.width) * copy.height * 4)
            return;
        auto info = SkImageInfo::Make(copy.width, copy.height, copy.bgra ? kBGRA_8888_SkColorType : kRGBA_8888_SkColorType, kOpaque_SkAlphaType);
        auto* pixels = new std::vector<uint8_t>(std::move(copy.rgba));
        auto pixelData = SkData::MakeWithProc(pixels->data(), pixels->size(),
            [](const void*, void* context) { delete static_cast<std::vector<uint8_t>*>(context); }, pixels);
        m_image = NativeImage::create(SkImages::RasterFromData(info, std::move(pixelData), size_t(copy.width) * 4));
        m_scaled = nullptr;
        m_lastFrameBGRA = copy.bgra;
        if (!forPage) { m_imageSerial = m_lastPaintedSerial; ++m_holeCanvasCopies; return; }
        m_imageSerial = m_decodedVideoFrames;
        if (RefPtr player = m_player.get()) player->repaint();
    }
    // Once per tick after pumping: hole or paint, and the messages to the shell.
    void updateHolePunch(OmniMSESource& source)
    {
        m_traceHoleStartUs = int64_t(MonotonicTime::now().secondsSinceEpoch().milliseconds() * 1000);
        using Controller = OmniMedia::Hw::HolePunchController;
        if (m_holeLink && !m_holeLink->alive()) {
            if (m_v5 && m_holeLink->clientFailed() && !m_paused && !m_seekPromise) holeRecover(source); // OMNI_HOLEPUNCH_V5
            m_holeLink = nullptr;
        }
        if (m_holeLink) m_holeLink->pump();   // OMNI_HOLEPUNCH_V2: acks arrive even while nothing is due
        Controller::Input in;
        in.nowMs = MonotonicTime::now().secondsSinceEpoch().milliseconds();
        in.link = m_holeLink.get();
        in.linkState = m_holeLink ? m_holeLink->state() : 0;
        in.frameDue = !!m_holeDue;
        in.shownCount = m_holeLink ? m_holeLink->shownCount() : 0;   // OMNI_HOLEPUNCH_V2
        in.playing = !m_paused && m_position > m_holeLastPosition;
        m_holeLastPosition = m_position;
        const char* why = !m_holeAllowed ? "disabled" : !m_visible ? "page hidden" : "no video";
        if (m_holeAllowed && m_visible && hasVideo())
            in.eligible = holeGeometry(in.rect, in.onScreen, why);
        if (in.eligible && !in.onScreen) why = "off screen";
        holePacingInput(in); // OMNI_HOLEPUNCH_V4
        const bool wasActive = m_holePunch.holeActive();
        const bool wasPaced = m_holePunch.paced(); // OMNI_MSE_SWITCH_HANDOFF_V1
        m_holePunch.setSwitchHandoff(m_switchHandoff);
        auto act = m_holePunch.tick(in);
        if (m_fastSwitch && m_switchHandoff && m_v5) { // OMNI_PERF_C_V8: until the new stream is paced
            const bool newSwitch = source.videoSwitch().count != m_switchSeen;
            if (newSwitch) m_quickTicks = 0;
            if ((newSwitch || (m_switchPending && !m_switchPacedMs)) && m_holeLink && !m_holePunch.paced() && !m_paused && !m_seekPromise) quickTick();
        }
        if (act.bail) holeBailLog(in);   // OMNI_HOLEPUNCH_V2 (the controller leaves the hole below)
        if (act.claim && !m_holeLink->claim(in.rect)) m_holePunch.claimNotSent();   // OMNI_HOLEPUNCH_V2: retry next tick
        if (act.enterHole) {
            m_image = nullptr; m_scaled = nullptr;   // never paint a stale frame after the hole
            if (RefPtr player = m_player.get()) player->repaint();
        }
        if (act.present) {
            if (MonotonicTime::now() < m_holeCanvasUntil) holeImage(*m_holeDue, false);
            const bool sent = m_holeDue->present(in.rect);
            m_holePunch.presentResult(sent, in.nowMs);   // OMNI_HOLEPUNCH_V2
            if (sent) m_holeLastPresentedTime = m_holeDueTime; // OMNI_HOLEPUNCH_V3
            if (sent) {
                ++m_displayedVideoFrames;
                if (m_displayedVideoFrames == 1) diagnostic("first-video-presented-by-shell");
            }
            m_holeDue = nullptr;
        }
        if (act.paintDue) { holeImage(*m_holeDue, true); m_holeDue = nullptr; }
        if (act.moveRect && !m_holeLink->claim(in.rect)) m_holePunch.rectNotSent();   // OMNI_HOLEPUNCH_V2: socket full, again next tick
        if (act.hide && m_holeLink) m_holeLink->hide();
        if (act.leaveHole) if (RefPtr player = m_player.get()) player->repaint();
        source.setVideoHolePunch(act.decoderHoles);
        // OMNI_MSE_SWITCH_HANDOFF_V1: pacing ended because the video is not seen (tab hidden, scrolled
        // off). V5: the shell's queue and the ~3 s in flight would come back here as converted
        // pictures (one per slot, all of them, before anything new: up to hundreds of MiB and
        // seconds of conversion) and, held ahead of the playhead, keep the decoder unfed once the
        // video is seen again: the shell got no frame, the safety net tripped and pacing stayed
        // off for the load. Decode the video again from the playhead instead: the flush drops the
        // shell's queue before the clock below turns pacing off (the stream still has hole frames on).
        if (m_switchHandoff && m_v5 && wasPaced && !m_holePunch.paced() && !m_seekPromise && (!m_visible || (in.eligible && !in.onScreen))) {
            source.resyncVideo();
            if (m_holeLink) m_holeLink->pacingStopped();   // V4's in-flight depth from now on (the clock below says "pacing off")
            if (m_resyncLogs < 8) {
                ++m_resyncLogs;
                fprintf(stderr, "OMNI HOLEPUNCH: player %s while paced: the video decodes again from the playhead %.3f (the shell's queued pictures were dropped) (SWITCH_HANDOFF)\n",
                    !m_visible ? "page hidden" : "video off screen", m_position);
                fflush(stderr);
            }
        }
        holeSwitchTick(source, in.nowMs); // OMNI_MSE_SWITCH_HANDOFF_V1
        holeTickV3(source, in);   // OMNI_HOLEPUNCH_V3
        holeTickV4(source, in, act);   // OMNI_HOLEPUNCH_V4
        if ((act.enterHole || (wasActive && act.leaveHole)) && m_holeLogLines < 24) {
            ++m_holeLogLines;
            if (m_holePunch.bailReason()) why = m_holePunch.bailReason();   // OMNI_HOLEPUNCH_V2
            else if (in.eligible && in.onScreen) why = m_holeLink ? m_holeLink->reason() : "decoder gone";
            fprintf(stderr, "OMNI HOLEPUNCH: player %s rect=%dx%d at %d,%d reason=%s presented=%llu rectUpdates=%llu refusals=%llu\n",
                act.enterHole ? "hole on" : "hole off, paint path", in.rect.w, in.rect.h, in.rect.x, in.rect.y,
                act.enterHole ? "shown by the shell" : why, static_cast<unsigned long long>(m_holePunch.presented),
                static_cast<unsigned long long>(m_holePunch.rectUpdates), static_cast<unsigned long long>(m_holePunch.refusals));
            fflush(stderr);
        }
    }
    // OMNI_HOLEPUNCH_V2: the safety net tripped. What this process holds tells a stalled
    // decoder (frames held, submits outstanding) from a stalled shell (no acks).
    void holeBailLog(const OmniMedia::Hw::HolePunchController::Input& in)
    {
        if (m_holeLogLines >= 24) return;
        ++m_holeLogLines;
        auto stats = m_holeLink ? m_holeLink->stats() : OmniMedia::Hw::HoleLink::Stats { };
        fprintf(stderr, "OMNI HOLEPUNCH: player safety net: %s; paint path for this video. due=%d held=%u clientReady=%zu submitsOutstanding=%u lastServiceMessageAgoMs=%.0f shown=%llu presented=%llu presentFailures=%llu rectDrops=%llu playing=%d position=%.3f\n",
            m_holePunch.bailReason(), in.frameDue, m_holeLink ? m_holeLink->heldFrames() : 0u, stats.ready, stats.outstanding,
            stats.lastMessageAgoMs, static_cast<unsigned long long>(in.shownCount), static_cast<unsigned long long>(m_holePunch.presented),
            static_cast<unsigned long long>(m_holeLink ? m_holeLink->presentFailures : 0), static_cast<unsigned long long>(m_holeLink ? m_holeLink->rectDrops : 0),
            in.playing, m_position);
        fflush(stderr);
    }
    // OMNI_MSE_SWITCH_HANDOFF_V1: one line per quality switch, written once the new stream plays
    // (1.5 s after the shell showed its first picture, or 5 s after the switch): nothing is written
    // while the new stream starts (a console stderr line can take 200 ms).
    void holeSwitchTick(OmniMSESource& source, double nowMs)
    {
        if (!m_switchHandoff) return;
        const auto& sw = source.videoSwitch();
        if (sw.count != m_switchSeen) {
            m_switchSeen = sw.count; m_switchInfo = sw; m_switchPending = true;
            m_switchAtMs = nowMs; m_switchPacedMs = m_switchShownMs = 0; m_switchLink = nullptr; m_switchShownBase = 0;
        }
        if (!m_switchPending) return;
        const OmniMedia::Hw::HoleLink* link = m_holeLink.get();
        if (!m_switchPacedMs && link && m_holePunch.paced()) { m_switchPacedMs = nowMs; m_switchLink = link; m_switchShownBase = link->pacing().shown; }
        if (m_switchPacedMs && !m_switchShownMs && link && link == m_switchLink && link->pacing().shown > m_switchShownBase) m_switchShownMs = nowMs;
        if (m_switchShownMs ? nowMs - m_switchShownMs < 1500 : nowMs - m_switchAtMs < 5000) return;
        m_switchPending = false;
        if (m_switchLogs >= 12) return;
        ++m_switchLogs;
        const auto& i = m_switchInfo;
        fprintf(stderr, "OMNI HOLEPUNCH: player quality switch %u -> %u: drained at %.3f s, configured at %.3f s (switch point %.3f s) %s %.0f ms (%s); paced again after %.0f ms, first new picture shown by the shell after %.0f ms (-1: not); safety net %s (SWITCH_HANDOFF)\n",
            i.from, i.to, i.drainedAt, i.playhead, i.switchPoint, i.waited ? "after waiting" : "without waiting", i.waitedMs, i.why,
            m_switchPacedMs ? m_switchPacedMs - m_switchAtMs : -1.0, m_switchShownMs ? m_switchShownMs - m_switchAtMs : -1.0,
            m_holePunch.bailReason() ? m_holePunch.bailReason() : m_holePunch.rearms ? "re-armed for the new stream" : "not tripped");
        fflush(stderr);
    }
    // OMNI_HOLEPUNCH_V3: per tick after the controller. (1) While the shell shows the video,
    // late frames cost only a Release: let the pump hand over up to 24 per tick so slow ticks
    // (the watch page measured ~5 Hz) cannot leave the video further behind every tick.
    // (2) Feed the main-thread watchdog. (3) Every 5 s with the hole on, one stats line.
    void holeTickV3(OmniMSESource& source, const OmniMedia::Hw::HolePunchController::Input& in)
    {
        const double lagMs = (m_position - m_holeLastPresentedTime) * 1000;
        const bool catchingUp = m_holePunch.presenting() && !m_paused && m_holeLastPresentedTime > 0 && lagMs > 50;
        unsigned budget = m_holePunch.presenting() ? 24 : 4;
        // OMNI_HOLEPUNCH_V5: while the audio ring holds under 2 s (start, after a stall), take up to
        // 48 outputs per buffer per tick (~1 s of audio): at 4 per tick a 5 Hz page drains it.
        if (m_v5 && (m_audioRing ? m_audioRing->fillFrames() < 2 * 48000 : hasAudio() && !m_audioUnavailable)) budget = std::max(budget, 48u); // V5_REV2: not without a device
        source.setVideoOutputBudget(budget, catchingUp ? std::clamp(int(lagMs / 10), 4, 30) : 0);
        const bool active = m_holePunch.holeActive();
        if (active) {
            OmniMedia::Hw::HoleWatchSnapshot snap;
            auto stats = m_holeLink ? m_holeLink->stats() : OmniMedia::Hw::HoleLink::Stats { };
            snap.positionSeconds = m_position; snap.lastPresentedSeconds = m_holeLastPresentedTime;
            snap.presented = m_holePunch.presented; snap.shown = in.shownCount;
            snap.held = m_holeLink ? m_holeLink->heldFrames() : 0; snap.clientReady = unsigned(stats.ready);
            snap.outstanding = stats.outstanding; snap.due = !!m_holeDue; snap.paused = m_paused;
            OmniMedia::Hw::holeWatchdogTick(&snap);
            m_holeWatchOn = true;
        } else if (m_holeWatchOn) {
            OmniMedia::Hw::holeWatchdogTick(nullptr);
            m_holeWatchOn = false;
        }
        if (!active) { m_holeStatsStartMs = 0; return; }
        if (!m_holeStatsStartMs) {
            m_holeStatsStartMs = m_holeStatsLastTickMs = in.nowMs; m_holeStatsTicks = 0; m_holeStatsMaxGapMs = 0;
            m_holeStatsPresented = m_holePunch.presented; m_holeStatsReplaced = m_replacedUnpaintedFrames;
            return;
        }
        ++m_holeStatsTicks;
        m_holeStatsMaxGapMs = std::max(m_holeStatsMaxGapMs, in.nowMs - m_holeStatsLastTickMs);
        m_holeStatsLastTickMs = in.nowMs;
        const double span = in.nowMs - m_holeStatsStartMs;
        if (span < 5000) return;
        if (m_holeStatsLines < 12) {
            ++m_holeStatsLines;
            const double audioMs = m_audio ? audioQueuedBytes() / (48000.0 * 4) * 1000 : -1; // OMNI_HOLEPUNCH_V5: ring or SDL queue
            if (omniReleaseDiagnostics()) fprintf(stderr, "OMNI HOLEPUNCH: player stats %.1f s: ticks=%llu (%.1f/s) maxTickGapMs=%.0f presented=%llu lateDropped=%llu lagMs=%.0f audioQueuedMs=%.0f shown=%llu held=%u paused=%d audioUnderruns=%llu v5=%d hold=%d audioVsWallMs=%.0f lock=%.6f lockChanges=%u fps=%.3f\n",
                span / 1000, static_cast<unsigned long long>(m_holeStatsTicks), m_holeStatsTicks * 1000.0 / span, m_holeStatsMaxGapMs,
                static_cast<unsigned long long>(m_holePunch.presented - m_holeStatsPresented),
                static_cast<unsigned long long>(m_replacedUnpaintedFrames - m_holeStatsReplaced),
                (m_position - m_holeLastPresentedTime) * 1000, audioMs, static_cast<unsigned long long>(in.shownCount),
                m_holeLink ? m_holeLink->heldFrames() : 0u, m_paused,
                static_cast<unsigned long long>(m_audioRing ? m_audioRing->underruns() : 0), m_v5, m_v5Hold, m_v5AudioVsWallMs, m_lock, m_lockChanges, m_source ? m_source->videoFrameRate() : 0.0); // V5_REV2: hold, audioVsWallMs; OMNI_PERF_C_V4: lock
            m_v5AudioVsWallMs = 0;
            fflush(stderr);
        }
        m_holeStatsStartMs = 0;
    }
    // ---- OMNI_HOLEPUNCH_V4: shell-side pacing ---------------------------------------------
    // The shell (UI process) queues this video's decoded frames and shows each one at its vblank
    // by the clock sent here, so a slow main thread (~5 Hz ticks on the youtube.com watch page)
    // no longer sets the frame rate. The player keeps feeding access units (larger batches per
    // tick: decoder access stays on this thread, see the V4 report) and sends the clock.
    uint32_t holeGeneration() const { return uint32_t(m_seekGeneration + m_videoPresentationGeneration); }
    void holePacingInput(OmniMedia::Hw::HolePunchController::Input& in)
    {
        if (v7QualityOn()) v7PacingCounts(); // OMNI_HOLEPUNCH_V7_QUALITY: every tick, so no pacing run is missed (V7_REV2: V7 on only)
        in.generation = holeGeneration();
        if (!m_holeLink) return;
        const auto& pacing = m_holeLink->pacing();
        in.pacing = m_holePacingAllowed && m_holeLink->pacingAvailable() && pacing.state >= 0;
        in.pacedShown = pacing.shown; in.pacedDecoded = pacing.decoded; in.pacedWaiting = pacing.waiting;
        in.pacingReportAgeMs = m_holeLink->pacingReportAgeMs();
        in.pacedDeep = m_v5; // OMNI_HOLEPUNCH_V5
        in.pacedPosterSelected = pacing.state == 1 && pacing.atMs > 0
            && pacing.startupGeneration == in.generation && (pacing.startupFlags & 8);
        in.pacedReported = pacing.state == 1 && pacing.atMs > 0; // OMNI_MSE_SWITCH_HANDOFF_V1
    }
    void holeTickV4(OmniMSESource& source, const OmniMedia::Hw::HolePunchController::Input& in, const OmniMedia::Hw::HolePunchController::Actions& act)
    {
        if (!m_holeLink) return;
        const bool paced = m_holePunch.paced();
        const auto now = MonotonicTime::now();
        m_holeSnapshotWanted |= act.snapshot;   // the paint path after the hole starts from the frame on screen
        const bool canvasSnapshot = paced && now < m_holeCanvasUntil && now - m_holeSnapshotAt >= 100_ms;
        if (paced || act.pace || m_holeClockOn || m_holeSnapshotWanted) {
            OmniMedia::Hw::HoleClockState clock;
            clock.traceReleaseUs = m_traceReleaseUs; clock.tracePrintedUs = m_tracePrintedUs;
            clock.traceFlushedUs = m_traceFlushedUs; clock.traceAfterHoldUs = m_traceAfterHoldUs;
            clock.traceBeforeRingUs = m_traceBeforeRingUs;
            clock.tracePumpStartUs = m_tracePumpStartUs; clock.tracePumpEndUs = m_tracePumpEndUs;
            clock.traceHoleStartUs = m_traceHoleStartUs;
            clock.traceClockBuildUs = int64_t(MonotonicTime::now().secondsSinceEpoch().milliseconds() * 1000);
            auto internalPosition = MediaTime::createWithDouble(m_position);
            clock.paced = act.pace;
            clock.playing = !m_paused && !m_seekPromise && !m_ended && !m_v5Hold && source.buffered().find(internalPosition) != notFound; // OMNI_HOLEPUNCH_V5_REV2: m_v5Hold
            clock.playing = clock.playing && m_rate > 0; // OMNI_PLAYBACK_RATE_V1
            clock.rate = m_rate > 0 ? clockRate() : 1; // OMNI_PERF_C_V4: the shell's clock runs at rate x lock
            // m_position is the playhead at this tick's start (m_anchor): bring it to now.
            double position = m_position + (clock.playing ? std::clamp((now - m_anchor).seconds(), 0.0, m_v5 ? 3.0 : 0.25) * clockRate() : 0); // OMNI_HOLEPUNCH_V5, OMNI_PLAYBACK_RATE_V1, OMNI_PERF_C_V4
            auto stall = source.nextStallTime(internalPosition);
            if (clock.playing && stall.isValid() && stall.isFinite()) { clock.limit = stall.toDouble(); position = std::min(position, clock.limit); }
            // Audio is the master: where the output is = end of the queued audio - still queued - device buffer.
            std::optional<double> audio;
            if (m_audioRing) { // OMNI_HOLEPUNCH_V5: the ring knows what the device plays
                // OMNI_HOLEPUNCH_V5_REV2: through the same plausibility check as the playhead, so the clock
                // the shell gets and the playhead never follow different sources.
                if (clock.playing) audio = audioPlayhead(position);
            } else if (m_audio && m_holeAudioQueueEnd && clock.playing && m_audio->playing()) {
                if (unsigned queued = m_audio->queuedBytes()) audio = *m_holeAudioQueueEnd - queued / (48000.0 * 4) - 1024 / 48000.0;
            }
            if (holeGeneration() != m_holeClockGeneration) { m_holeClockGeneration = holeGeneration(); m_holeAudioClock.reset(); }
            clock.position = m_holeAudioClock.master(position, audio, in.nowMs);
            clock.generation = m_holeClockGeneration;
            if (m_videoDiscardBefore) clock.discardBefore = *m_videoDiscardBefore;
            clock.snapshot = m_holeSnapshotWanted || canvasSnapshot;
            const bool due = m_holeClockSender.due(clock, in.nowMs);
            const bool sent = due && m_holeLink->sendClock(clock);
            if (sent) {
                m_holeClockSender.sent(clock, in.nowMs);
                if (clock.snapshot) { m_holeSnapshotAt = now; m_holeSnapshotWanted = false; }
            }
            m_holeClockOn = act.pace || (due && !sent);
        }
        OmniMedia::DecodedOutput snapshot;
        if (m_holeLink->takeSnapshot(snapshot)) holeImageFrom(snapshot, !m_holePunch.holeActive());
        // The shell's counts are this player's frame counts while it paces.
        const auto& pacing = m_holeLink->pacing();
        if (m_holePacedLink != m_holeLink.get()) {
            m_holePacedLink = m_holeLink.get();
            m_holePacedShown = pacing.shown; m_holePacedDecoded = pacing.decoded; m_holePacedDropped = pacing.dropped;
        }
        if (pacing.shown >= m_holePacedShown && pacing.decoded >= m_holePacedDecoded && pacing.dropped >= m_holePacedDropped) {
            const bool first = !m_displayedVideoFrames && pacing.shown > m_holePacedShown;
            m_displayedVideoFrames += pacing.shown - m_holePacedShown;
            m_decodedVideoFrames += pacing.decoded - m_holePacedDecoded;
            m_droppedVideoFrames += pacing.dropped - m_holePacedDropped;
            m_replacedUnpaintedFrames += pacing.dropped - m_holePacedDropped;
            if (first) diagnostic("first-video-shown-by-shell-paced");
        }
        m_holePacedShown = pacing.shown; m_holePacedDecoded = pacing.decoded; m_holePacedDropped = pacing.dropped;
        if (!paced) return;
        if (pacing.mediaUs != INT64_MIN) m_holeLastPresentedTime = double(pacing.mediaUs) / 1e6;   // V3 stats and watchdog
        // Feed larger batches: up to 24 outputs, and while the shell's queue runs short, wait for
        // the decoder (V3's catch-up wait) so this tick can submit more access units.
        // OMNI_HOLEPUNCH_V5: no waiting: the client keeps ~3.5 s of access units in flight and the
        // service decodes them on its own. 192 outputs per buffer per tick, so the audio buffer
        // refills ~3 s of audio (~140 chunks) in the first tick after a stall; the video buffer
        // hands its packets over until the client's in-flight limit (paced frames are no outputs).
        if (m_v5) source.setVideoOutputBudget(192, 0);
        else source.setVideoOutputBudget(24, !m_paused && pacing.waiting < 3 ? 30 : 0);
    }
    // ---- OMNI_HOLEPUNCH_V5: audio through the ring ------------------------------------------
    static void audioCallback(void* ring, Uint8* stream, int len)   // SDL's audio thread
    {
        OmniMedia::AudioRing::deviceCallback(ring, stream, len); // OMNI_HOLEPUNCH_V5_REV3: counts bytes and the peak it hands over
    }
    void clearAudio()   // the device is paused by the caller
    {
        if (!m_audio) return;
        m_rateAudio.reset(); // OMNI_PLAYBACK_RATE_V1
        if (!m_audioRing) { m_audio->clearQueued(); return; }
        m_audio->lock();   // the callback is not running while we hold it (OMNI_AUDIO_RELAY_V1: the relay's clear is a request)
        m_audioRing->clear();
        m_audio->unlock();
    }
    size_t audioQueuedBytes() const
    {
        if (m_audioRing) return (m_audioRing->fillFrames() + (m_rateAudio.idle() ? 0 : 1)) * 2 * sizeof(int16_t); // OMNI_PLAYBACK_RATE_V1: + what RateAudio still holds
        return m_audio ? m_audio->queuedBytes() : 0;
    }
    // The media time the device plays now, while it plays from the ring; nullopt otherwise or
    // when it is implausible against the wall-clock target (then the wall clock is used).
    std::optional<double> audioPlayhead(double wallTarget)
    {
        if (!m_audioRing || !m_audio || !m_audio->playing() || !m_audioRing->fillFrames()) return std::nullopt;
        const double heard = m_audioRing->heard(m_audioDeviceFrames, true);
        if (!std::isfinite(heard) || heard > wallTarget + 0.5 || heard < m_position - 4) return std::nullopt;
        return heard;
    }
    // OMNI_HOLEPUNCH_V5_REV3: proof of audible output. Every 5 s (first 12 lines, then every 60 s): what
    // the device callback handed SDL (bytes, calls, largest |sample| after the gain) and what was
    // written into the ring (largest |sample|), the gain, the device's state and what is queued.
    // outPeak=0 with inPeak>0: our gain; both >0 and no sound: SDL / the system's output.
    void audioOutputLog()
    {
        if (!m_audio || !m_audioRing) return;
        const double now = OmniMedia::Hw::nowMs();
        if (!m_audioOutputLogMs) { m_audioOutputLogMs = now; m_audioOutputBytes = m_audioRing->callbackBytes(); m_audioOutputCalls = m_audioRing->callbackCalls(); return; }
        if (now - m_audioOutputLogMs < (m_audioOutputLines < 12 ? 5000 : 60000)) return;
        const uint64_t bytes = m_audioRing->callbackBytes(), calls = m_audioRing->callbackCalls();
        if (omniReleaseDiagnostics()) fprintf(stderr, "OMNI AUDIO OUTPUT: %.1f s: callbackBytes=%llu (%.0f ms of audio) callbacks=%llu outPeak=%d inPeak=%d gain=%.2f muted=%d volume=%.2f device=%s queuedMs=%.0f underruns=%llu hold=%d paused=%d\n",
            (now - m_audioOutputLogMs) / 1000, static_cast<unsigned long long>(bytes - m_audioOutputBytes), double(bytes - m_audioOutputBytes) / (48000.0 * 4) * 1000,
            static_cast<unsigned long long>(calls - m_audioOutputCalls), m_audioRing->takeOutPeak(), m_audioRing->takeInPeak(), m_audioRing->gain(), m_muted, m_volume,
            m_audio->statusName(), m_audioRing->fillFrames() / 48.0,
            static_cast<unsigned long long>(m_audioRing->underruns()), m_v5Hold, m_paused);
        fflush(stderr);
        ++m_audioOutputLines;
        m_audioOutputLogMs = now; m_audioOutputBytes = bytes; m_audioOutputCalls = calls;
    }
    // Once per tick: the end of the stream is not an underrun; log underruns (first 12).
    void audioRingTick(bool ending)
    {
        m_audioRing->setEnding(ending);
        rateAudioFlush(); // OMNI_PLAYBACK_RATE_V1
        m_audioRing->setGain(m_muted ? 0 : m_volume); // OMNI_HOLEPUNCH_V5_REV3: refreshed every tick, as V4 read it per queued chunk
        audioOutputLog();
        const uint64_t underruns = m_audioRing->underruns();
        if (underruns != m_audioUnderrunsLogged && m_audioUnderrunsLogged < 12) {
            fprintf(stderr, "OMNI AUDIO: underrun (%llu so far, %.0f ms of silence in all) position=%.3f queuedMs=%.0f intertickMaxMs=%.0f\n",
                static_cast<unsigned long long>(underruns), m_audioRing->underrunFrames() / 48.0, m_position,
                m_audioRing->fillFrames() / 48.0, m_maxIntertickMilliseconds);
            fflush(stderr);
        }
        m_audioUnderrunsLogged = underruns;
    }
    // ---- OMNI_HOLEPUNCH_V5_REV2: start hold, audio init pacing -------------------------------
    // The playhead waits (does not advance; device paused; the shell's clock stopped) at the start,
    // after a seek, when the audio device opens and when the ring ran dry while playing, until
    // ~1 s of audio is in the ring and, while the shell paces, ~1 s of video is decoded ahead of
    // the clock (HolePacing aheadMs). No device (init failed or still being retried), no audio
    // track, the end of the stream: audio does not wait. At most 3 s; a ran-dry hold that timed
    // out is not taken again until audio plays (no 3 s stutter when an audio track is short).
    // OMNI_HOLEPUNCH_V5_REV3: video is waited for only while the shell's queue grows: not when nothing
    // is in flight to the decoder (150 ms), no decode progress for 500 ms (pictures, queued media or
    // submits in flight), or the queue is full. A forward seek of less than 0.5 s ("nudge", hls.js's
    // answer to a playhead it sees stalled) waits for 250 ms of audio only, 0.5 s at most.
    void v5Hold(const char* why)
    {
        if (!m_v5 || m_v5Hold) return;
        m_v5Hold = true; m_v5HoldSince = MonotonicTime::now(); m_v5HoldReason = why;
        m_v5HoldNudge = !strcmp(why, "nudge"); // OMNI_HOLEPUNCH_V5_REV3
        m_v5HoldProgressAt = m_v5HoldSince; m_v5HoldDecoded = 0; m_v5HoldAheadMs = m_v5HoldInFlight = m_v5HoldChecks = 0;
        m_holdAudioAt = m_holdVideoAt = m_holdStartupAt = -1; // OMNI_PERF_C_T2
    }
    bool v5HoldTick(OmniMSESource& source)   // true: released now (the playhead starts from where it waited)
    {
        if (m_paused || m_seekPromise) return false;
        const bool ended = source.isEnded();
        if (m_audioRing && m_audioRing->fillFrames()) m_v5DryHoldArmed = true;
        if (!m_v5Hold && m_v5DryHoldArmed && !ended && m_audio && m_audioRing && m_audioRing->hasMedia() && !m_audioRing->fillFrames()
            && m_audio->playing()) {
            m_position = std::max(m_position, m_audioRing->endMedia());   // what was heard before it ran dry
            v5Hold("audio ran dry");
        }
        if (!m_v5Hold) return false;
        const double audioMs = m_audioRing ? m_audioRing->fillFrames() / 48.0 : 0;
        const bool noDevice = !m_audio && (m_audioUnavailable || m_audioRetryStart);
        // OMNI_PERF_C_T2: the start hold releases at 500 ms of audio and of video decoded ahead (was 1 s
        // each); the readiness gate (startupFlags) and the queue-full / no-progress exits stay. After it the
        // service keeps decoding to 3 s ahead at several times real time, and the ring refills to 3 s.
        const bool shortStart = m_holdShort && !strcmp(m_v5HoldReason, "start");
        const double audioNeedMs = m_v5HoldNudge ? 250 : shortStart ? 500 : 1000;
        const unsigned videoNeedMs = shortStart ? 500 : 1000;
        const bool audioReady = !hasAudio() || ended || noDevice || audioMs >= audioNeedMs; // V5_REV3: nudge
        // OMNI_HOLEPUNCH_V5_REV3: progress of the shell's queue (see v5Hold)
        const auto now = MonotonicTime::now();
        const char* videoIdle = nullptr;
        if (m_holeLink && m_holePunch.paced()) {
            // Fresh reports (the service reports every 250 ms while it paces); "nothing in flight" only
            // once this hold has seen a tick pump (a seek resolves with nothing submitted yet).
            m_holeLink->pump();
            const auto& pacing = m_holeLink->pacing();
            const unsigned inFlight = m_holeLink->stats().outstanding;
            if (pacing.decoded != m_v5HoldDecoded || pacing.aheadMs != m_v5HoldAheadMs || inFlight != m_v5HoldInFlight) {
                m_v5HoldDecoded = pacing.decoded; m_v5HoldAheadMs = pacing.aheadMs; m_v5HoldInFlight = inFlight; m_v5HoldProgressAt = now;
            }
            if (m_v5HoldChecks < 8) ++m_v5HoldChecks;
            const double stillMs = (now - m_v5HoldProgressAt).milliseconds();
            videoIdle = !inFlight && m_v5HoldChecks >= 3 && stillMs >= 150 ? "nothing in flight to the decoder" : stillMs >= 500 ? "no decode progress for 500 ms"
                : pacing.capacity && pacing.waiting + 1 >= pacing.capacity ? "the shell's queue is full" : nullptr;
        }
        const unsigned videoMs = m_holeLink ? m_holeLink->pacing().aheadMs : 0;
        // V119: not-yet-paced is not ready when video has not produced its first image.
        // Keep audio-only, ended-stream, nudge and existing bounded timeout behavior.
        const bool firstVideoReady = m_image || m_holeHasFrame;
        const bool videoReady = !hasVideo() || ended || m_v5HoldNudge
            || (m_holePunch.paced() ? (videoMs >= videoNeedMs || videoIdle) : firstVideoReady); // OMNI_PERF_C_T2: videoNeedMs
        const bool startupGate = !strcmp(m_v5HoldReason, "start") && hasVideo() && m_holePacingAllowed && !ended;
        const auto startupFlags = m_holeLink ? m_holeLink->pacing().startupFlags : 0;
        const bool startupReady = m_holePunch.paced() && m_holeLink && (startupFlags & 7) == 7
            && m_holeLink->pacing().startupGeneration == holeGeneration();
        { // OMNI_PERF_C_T2: when each gate opened (in the hold's log line)
            const double into = (now - m_v5HoldSince).milliseconds();
            if (audioReady && m_holdAudioAt < 0) m_holdAudioAt = into;
            if (videoReady && m_holdVideoAt < 0) m_holdVideoAt = into;
            if ((!startupGate || startupReady) && m_holdStartupAt < 0) m_holdStartupAt = into;
        }
        // V133 controlled experiment: no timeout may silently bypass the startup gate.
        // Decode, page paint, IPC and held-position presentation keep running in the tick.
        if (startupGate && !startupReady) return false;
        const double heldMs = (now - m_v5HoldSince).milliseconds();
        if (!(audioReady && videoReady) && heldMs < (m_v5HoldNudge ? 500 : 3000)) return false;
        const double releaseTraceUs = MonotonicTime::now().secondsSinceEpoch().milliseconds() * 1000;
        m_traceReleaseUs = int64_t(releaseTraceUs);
        m_v5Hold = false;
        if (m_audioDeviceLogs < 8) m_audioDeviceLogPending = true; // OMNI_HOLEPUNCH_V5_REV3: the device's state at the end of this tick
        if (!(audioReady && videoReady) && !strcmp(m_v5HoldReason, "audio ran dry")) m_v5DryHoldArmed = false;
        if (m_v5HoldLogs < 24) {
            ++m_v5HoldLogs;
            fprintf(stderr, "OMNI HOLEPUNCH: playhead held %.0f ms (%s) at %.3f: audio %.0f ms queued%s, video %u ms decoded ahead%s%s%s%s releaseMonoUs=%.0f holdSinceMonoUs=%.0f startupGate=%d startupFlags=%u startupGeneration=%u; gates open after: audio %.0f video %.0f startup %.0f ms (need %.0f/%u ms); lock %.6f (%.3f fps, measured %.4f, display %.4f Hz)\n", heldMs, m_v5HoldReason,
                m_position, audioMs, noDevice ? " (no audio device)" : "", videoMs, m_holePunch.paced() ? "" : " (not paced)",
                videoIdle && videoMs < videoNeedMs && !m_v5HoldNudge ? "; video not waited for: " : "", videoIdle && videoMs < videoNeedMs && !m_v5HoldNudge ? videoIdle : "", // V5_REV3
                audioReady && videoReady ? "" : m_v5HoldNudge ? "; gave up waiting after 0.5 s" : "; gave up waiting after 3 s", releaseTraceUs, m_v5HoldSince.secondsSinceEpoch().milliseconds() * 1000, startupGate, startupFlags, holeGeneration(),
                m_holdAudioAt, m_holdVideoAt, m_holdStartupAt, audioNeedMs, videoNeedMs, // OMNI_PERF_C_T2
                m_lock, m_source ? m_source->videoFrameRate() : 0.0, m_source ? m_source->videoFrameRateMeasured() : 0.0, Omni::DisplayLock::displayHz()); // OMNI_PERF_C_V4
            m_tracePrintedUs = int64_t(MonotonicTime::now().secondsSinceEpoch().milliseconds() * 1000);
            fflush(stderr);
            m_traceFlushedUs = int64_t(MonotonicTime::now().secondsSinceEpoch().milliseconds() * 1000);
        }
        return true;
    }
    // OMNI_AUDIO_RELAY_V1: give the audio output back now (paused for good); consume() opens it again.
    void audioRelease(const char* why)
    {
        if (m_audio) { m_audio->pause(true); if (!m_audioRing) m_audio->clearQueued(); }
        fprintf(stderr, "OMNI AUDIO DEVICE: released (%s): %s\n", why, m_audio ? m_audio->describe().c_str() : "none");
        fflush(stderr);
        m_audio = nullptr;
        m_audioRing = nullptr; // after the output (a device's callback reads it)
        m_rateAudio.reset(); // OMNI_PLAYBACK_RATE_V1
    }
    // OMNI_AUDIO_RELAY_V1: no audio output now (relay refused or absent, and SDL init or the device open
    // failed: on the console a second device while another player's was open, or a port not yet
    // released). Never fatal: for 5 s audio is kept and retried every 250 ms (OMNI_AUDIO_FALLBACK_V1);
    // then it is dropped (video on the wall clock) and retried after 2, 4, 8, 16, 16... s.
    // Returns consume()'s answer for this output: true dropped, false kept.
    bool audioOpenFailed(uint32_t now, const char* what)
    {
        if (!m_audioRetryStart) m_audioRetryStart = now ? now : 1;
        if (!m_audioUnavailable && now - m_audioRetryStart < 5000) return false;
        if (!m_audioUnavailable) m_audioRetryDelayMs = 2000;
        else m_audioRetryDelayMs = std::min(16000u, m_audioRetryDelayMs * 2);
        m_audioUnavailable = true;
        if (m_audioFailLogs < 12) {
            ++m_audioFailLogs;
            fprintf(stderr, "OMNI AUDIO INIT: %s failed (%s) after %u ms; playing video without sound, next attempt in %u ms\n", what, SDL_GetError(),
                now - m_audioRetryStart, m_audioRetryDelayMs);
            fflush(stderr);
        }
        return true;
    }
    // An audio init attempt was entered this tick: the next one no sooner than 4 x what this tick
    // spent from it on (at least the 250 ms / 2 s of OMNI_AUDIO_FALLBACK_V1, at most 15 s).
    void audioInitFinish()
    {
        m_audioInitThisTick = false;
        if (m_audio) return;
        const double now = OmniMedia::Hw::nowMs(), took = now - m_audioInitEnteredMs;
        const double wait = std::min(16000.0, std::max(m_audioUnavailable ? double(m_audioRetryDelayMs) : 250.0, 4 * took)); // OMNI_AUDIO_RELAY_V1: backoff
        m_audioInitNotBeforeMs = now + wait;
        if (took > 100 && m_audioInitSlowLogs < 8) {
            ++m_audioInitSlowLogs;
            fprintf(stderr, "OMNI AUDIO INIT: attempt failed after ~%.0f ms on the main thread; next attempt in %.0f ms\n", took, wait);
            fflush(stderr);
        }
    }
    // OMNI_HOLEPUNCH_V5: the hardware stream failed while playing (PacketDecoder fell back to
    // software). Seconds of this video were decoded ahead in the service or in flight to it, and
    // are gone: decode again from the keyframe at the playhead, as a seek to the playhead does,
    // instead of holding the last frame until software decoding reaches what came after them.
    void holeRecover(OmniMSESource& source)
    {
        if (m_holeLogLines < 24) {
            ++m_holeLogLines;
            fprintf(stderr, "OMNI HOLEPUNCH: hardware decoding failed while playing; decoding again from the playhead %.3f\n", m_position);
            fflush(stderr);
        }
        source.flushPlayback();
        (void)source.reenqueueMediaForTime(MediaTime::createWithDouble(m_position));
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
    void holePunchReset()
    {
        if (m_holeLink && m_holePunch.claimed()) m_holeLink->hide();
        if (m_holePunch.presented && m_holeLogLines < 24) {
            ++m_holeLogLines;
            fprintf(stderr, "OMNI HOLEPUNCH: player done presented=%llu rectUpdates=%llu claims=%llu refusals=%llu fallbacks=%llu paintClears=%llu canvasCopies=%llu shownByShell=%llu safetyNet=%s\n",
                static_cast<unsigned long long>(m_holePunch.presented), static_cast<unsigned long long>(m_holePunch.rectUpdates),
                static_cast<unsigned long long>(m_holePunch.claims), static_cast<unsigned long long>(m_holePunch.refusals),
                static_cast<unsigned long long>(m_holePunch.leaves), static_cast<unsigned long long>(m_holePaintClears),
                static_cast<unsigned long long>(m_holeCanvasCopies), static_cast<unsigned long long>(m_holeLink ? m_holeLink->shownCount() : 0),
                m_holePunch.bailReason() ? m_holePunch.bailReason() : "not tripped"); // OMNI_HOLEPUNCH_V2
            fflush(stderr);
        }
        m_holeDue = nullptr; m_holeLink = nullptr; m_holeHasFrame = false;
        m_holePunch = { };
        m_holeLastRect.reset();
        m_holePaintClears = m_holeCanvasCopies = 0;
        m_holeLastPosition = 0; // OMNI_HOLEPUNCH_V2
        if (m_holeWatchOn) { OmniMedia::Hw::holeWatchdogTick(nullptr); m_holeWatchOn = false; } // OMNI_HOLEPUNCH_V3
        m_holeStatsStartMs = 0; m_holeDueTime = m_holeLastPresentedTime = 0;
        if (m_source) m_source->setVideoOutputBudget(4);
        if (m_source) m_source->setVideoHolePunch(false);
        m_holeClockSender = { }; m_holeAudioClock.reset(); m_holeAudioQueueEnd.reset(); // OMNI_HOLEPUNCH_V4
        m_holeClockOn = m_holeSnapshotWanted = false; m_holePacedLink = nullptr; m_holeClockGeneration = 0;
    }
    OmniMedia::Hw::HolePunchController m_holePunch;
    std::shared_ptr<OmniMedia::Hw::HoleLink> m_holeLink;
    std::shared_ptr<OmniMedia::Hw::HoleFrame> m_holeDue;   // newest due frame for the shell
    std::optional<OmniMedia::Hw::HoleLink::Rect> m_holeLastRect;
    bool m_holeAllowed = false, m_holeHasFrame = false, m_holeLastOnScreen = false;
    MonotonicTime m_holeCanvasUntil;
    uint64_t m_holePaintClears = 0, m_holeCanvasCopies = 0;
    unsigned m_holeLogLines = 0;
    double m_holeLastPosition = 0; // OMNI_HOLEPUNCH_V2: playback position at the previous tick
    // OMNI_HOLEPUNCH_V3
    double m_holeDueTime = 0, m_holeLastPresentedTime = 0;
    bool m_holeWatchOn = false;
    double m_holeStatsStartMs = 0, m_holeStatsLastTickMs = 0, m_holeStatsMaxGapMs = 0;
    uint64_t m_holeStatsTicks = 0, m_holeStatsPresented = 0, m_holeStatsReplaced = 0;
    unsigned m_holeStatsLines = 0;
    // OMNI_HOLEPUNCH_V4
    bool m_holePacingAllowed = false, m_holeClockOn = false, m_holeSnapshotWanted = false;
    OmniMedia::Hw::HoleClockSender m_holeClockSender;
    OmniMedia::Hw::HoleAudioClock m_holeAudioClock;
    std::optional<double> m_holeAudioQueueEnd;
    uint32_t m_holeClockGeneration = 0;
    // OMNI_HOLEPUNCH_V5
    bool m_v5 = false;
    std::unique_ptr<OmniMedia::AudioRing> m_audioRing;   // the device's callback plays from it
    int m_audioDeviceFrames = 1024;                      // SDL's buffer
    uint64_t m_audioUnderrunsLogged = 0;
    // OMNI_HOLEPUNCH_V5_REV2
    bool m_v5Hold = false, m_v5DryHoldArmed = true, m_audioInitThisTick = false;
    int64_t m_traceReleaseUs = 0, m_tracePrintedUs = 0, m_traceFlushedUs = 0, m_traceAfterHoldUs = 0, m_traceBeforeRingUs = 0;
    int64_t m_tracePumpStartUs = 0, m_tracePumpEndUs = 0, m_traceHoleStartUs = 0; // V135 timing only
    MonotonicTime m_v5HoldSince;
    const char* m_v5HoldReason = "";
    double m_audioInitNotBeforeMs = 0, m_audioInitEnteredMs = 0, m_v5AudioVsWallMs = 0;
    unsigned m_v5HoldLogs = 0, m_audioInitSlowLogs = 0;
    // OMNI_HOLEPUNCH_V5_REV3
    double m_audioOutputLogMs = 0;
    bool m_audioDeviceLogPending = false;
    unsigned m_audioDeviceLogs = 0;
    uint64_t m_audioOutputBytes = 0, m_audioOutputCalls = 0;
    unsigned m_audioOutputLines = 0;
    bool m_v5HoldNudge = false;
    MonotonicTime m_v5HoldProgressAt;
    uint64_t m_v5HoldDecoded = 0;
    unsigned m_v5HoldAheadMs = 0, m_v5HoldInFlight = 0, m_v5HoldChecks = 0;
    MonotonicTime m_holeSnapshotAt;
    const void* m_holePacedLink = nullptr;
    uint64_t m_holePacedShown = 0, m_holePacedDecoded = 0, m_holePacedDropped = 0;
    // OMNI_MSE_SWITCH_HANDOFF_V1
    bool m_switchHandoff = false, m_switchPending = false;
    uint64_t m_switchSeen = 0, m_switchShownBase = 0;
    OmniMSESource::VideoSwitch m_switchInfo;
    double m_switchAtMs = 0, m_switchPacedMs = 0, m_switchShownMs = 0;
    const OmniMedia::Hw::HoleLink* m_switchLink = nullptr;
    unsigned m_switchLogs = 0, m_resyncLogs = 0;
    OmniMedia::TabMedia::Gate m_tabMedia; // OMNI_TAB_MEDIA_RELEASE_V1

    ThreadSafeWeakPtr<MediaPlayer> m_player;
    RefPtr<OmniMSESource> m_source;
    RunLoop::Timer m_timer;
    std::optional<MediaTimePromise::AutoRejectProducer> m_seekPromise;
    std::optional<double> m_audioDiscardBefore, m_videoDiscardBefore;
    RefPtr<NativeImage> m_image;
    FloatSize m_size;
    PlatformTimeRanges m_ranges, m_seekable;
    MonotonicTime m_anchor;
    std::optional<MonotonicTime> m_previousProfileTick;
    uint64_t m_profileTicks = 0;
    double m_pumpTotalMilliseconds = 0, m_pumpMaxMilliseconds = 0, m_maxIntertickMilliseconds = 0;
    std::unique_ptr<OmniMedia::Audio::Output> m_audio; // OMNI_AUDIO_RELAY_V1: was the SDL device id
    uint32_t m_audioRetryDelayMs = 2000; // OMNI_AUDIO_RELAY_V1: backoff while audio is unavailable
    std::optional<MonotonicTime> m_pausedSince;
    bool m_audioReleasedPaused = false;
    unsigned m_audioRelayLogs = 0, m_audioFailLogs = 0;
    double m_position = 0;
    uint64_t m_seekGeneration = 0;
    uint64_t m_audioPresentationGeneration = 0, m_videoPresentationGeneration = 0;
    uint64_t m_decodedVideoFrames = 0, m_displayedVideoFrames = 0, m_droppedVideoFrames = 0;
    // v53 breakdown of m_droppedVideoFrames (legacy total kept for comparison).
    uint64_t m_replacedUnpaintedFrames = 0, m_discardedPrerollFrames = 0, m_discardedSeekFrames = 0;
    // OMNI_HOLEPUNCH_V7_QUALITY: the shell's counts for this video (see v7PacingCounts)
    const OmniMedia::Hw::HoleLink* m_v7PacingLink = nullptr;
    bool m_v7Pacing = false;
    uint64_t m_v7BaseShown = 0, m_v7BaseDropped = 0, m_v7RunShown = 0, m_v7RunDropped = 0, m_v7DoneShown = 0, m_v7DoneDropped = 0;
    bool m_lastFrameBGRA = false;
    uint64_t m_imageSerial = 0, m_lastPaintedSerial = 0;
    uint64_t m_pcmSubmittedFrames = 0, m_pcmSubmittedChunks = 0, m_errors = 0;
    unsigned m_diagnosticLines = 0;
    float m_volume = 1;
    double m_requestedRate = 1, m_rate = 1; // OMNI_PLAYBACK_RATE_V1: asked for, running at
    Omni::ClockAudio m_rateAudio; // OMNI_PERF_C_V4: RateAudio + the display lock's resampler (OmniMSEClock.h)
    unsigned m_rateLogs = 0;
    double m_lock = 1; // OMNI_PERF_C_V4: clock factor (display / content rate), 1 = off
    bool m_lockEnabled = true;
    unsigned m_lockChanges = 0;
    bool m_holdShort = true; // OMNI_PERF_C_T2
    double m_holdAudioAt = -1, m_holdVideoAt = -1, m_holdStartupAt = -1; // OMNI_PERF_C_T2: ms into the hold each gate opened
    bool m_fastSwitch = true, m_quickTickPending = false; // OMNI_PERF_C_V8
    unsigned m_quickTicks = 0;
    uint32_t m_audioRetryStart = 0, m_audioLastAttempt = 0;
    bool m_audioUnavailable = false; // OMNI_AUDIO_FALLBACK_V1
    uint64_t m_paintCalls = 0;
    RefPtr<NativeImage> m_scaled;
    uint64_t m_scaledSerial = 0;
    int m_scaledWidth = 0, m_scaledHeight = 0;
    double m_paintTotalMs = 0, m_paintMaxMs = 0;
    bool m_audioInitialized = false, m_paused = true, m_ended = false, m_muted = false, m_visible = true, m_outputError = false;
    MediaPlayer::ReadyState m_ready = MediaPlayer::ReadyState::HaveNothing;
    MediaPlayer::NetworkState m_network = MediaPlayer::NetworkState::Empty;
};
class OmniMSEFactory final : public MediaPlayerFactory {
public:
    MediaPlayerEnums::MediaEngineIdentifier identifier() const final { return MediaPlayerEnums::MediaEngineIdentifier::OmniMSE; }
    Ref<MediaPlayerPrivateInterface> createMediaEnginePlayer(MediaPlayer& player) const final { return adoptRef(*new OmniMSEPlayer(player)); }
    void getSupportedTypes(HashSet<String>& types) const final { types.add("video/mp4"_s); types.add("audio/mp4"_s); if (OmniMedia::webmMseEnabled()) { types.add("video/webm"_s); types.add("audio/webm"_s); } } // OMNI_WEBM_V1
    MediaPlayer::SupportsType supportsTypeAndCodecs(const MediaEngineSupportParameters& parameters) const final
    {
        if (parameters.platformType != PlatformMediaDecodingType::MediaSource || parameters.requiresRemotePlayback) return MediaPlayer::SupportsType::IsNotSupported;
        // OMNI_MEDIACAPS_V1: media/OmniMediaCaps.h, shared with addSourceBuffer and decodingInfo.
        // MediaSource requires IsSupported for an explicit codec list; "maybe"
        // is accepted only for a container query without codecs.
        switch (omniMSETypeSupport(parameters.type)) {
        case OmniMedia::Caps::Support::Yes: return MediaPlayer::SupportsType::IsSupported;
        case OmniMedia::Caps::Support::Maybe: return MediaPlayer::SupportsType::MayBeSupported;
        case OmniMedia::Caps::Support::No: break;
        }
        return MediaPlayer::SupportsType::IsNotSupported;
    }
};
void registerOmniMSEEngine(MediaEngineRegistrar registrar)
{
    // Experimental build only; never enabled on the validated v37 deployment.
    if (!access("/data/omni/mse-preview.flag", F_OK)) registrar(makeUnique<OmniMSEFactory>());
}
// OMNI_MEDIACAPS_V1 adapter begin
// navigator.mediaCapabilities.decodingInfo. WebKit 539e0189f6 installs decoding factories
// only under PLATFORM(COCOA) / USE(GSTREAMER) (PlatformMediaEngineConfigurationFactory.cpp,
// defaultFactories()); on PlayStation the list is empty and every query says supported:false.
// This factory requires what the engines say (MediaPlayer::supportsType, as isTypeSupported and
// canPlayType do) and then the limits in media/OmniMediaCaps.h.
static bool omniMediaCapsHardware = false;
static std::string omniCapsUtf8(const String& value)
{
    auto utf8 = value.utf8();
    return std::string(reinterpret_cast<const char*>(utf8.data()), utf8.length()); // char8_t data
}
static std::vector<std::string> omniCapsCodecs(const ContentType& type)
{
    std::vector<std::string> codecs;
    for (auto& codec : type.codecs())
        codecs.push_back(omniCapsUtf8(codec));
    return codecs;
}
static bool omniCapsEngineAccepts(const PlatformMediaDecodingConfiguration& configuration, const String& contentType)
{
    MediaEngineSupportParameters parameters {
        .platformType = configuration.type,
        .type = ContentType(contentType),
        .allowedMediaContainerTypes = configuration.allowedMediaContainerTypes,
        .allowedMediaCodecTypes = configuration.allowedMediaCodecTypes,
    };
    auto support = MediaPlayer::supportsType(parameters);
    // MediaSource::isTypeSupported needs IsSupported for a codec list; canPlayType anything but "".
    if (configuration.type == PlatformMediaDecodingType::MediaSource)
        return support == MediaPlayer::SupportsType::IsSupported;
    return support != MediaPlayer::SupportsType::IsNotSupported;
}
static void omniCreateDecodingConfiguration(PlatformMediaDecodingConfiguration&& configuration, PlatformMediaEngineConfigurationFactory::DecodingConfigurationCallback&& callback)
{
    using namespace OmniMedia::Caps;
    Query query;
    query.kind = configuration.type == PlatformMediaDecodingType::MediaSource ? Kind::MediaSource
        : configuration.type == PlatformMediaDecodingType::FileOrHLS ? Kind::File : Kind::Other;
    query.hardwareDecode = omniMediaCapsHardware;
    query.webm = OmniMedia::webmMseEnabled(); // OMNI_WEBM_V1
    query.decoders = OmniMedia::webmDecoders();
    bool enginesAccept = query.kind != Kind::Other;
    std::string videoType, audioType;
    if (configuration.video) {
        auto& video = *configuration.video;
        ContentType type(video.contentType);
        VideoQuery v;
        v.containerType = omniCapsUtf8(type.containerType());
        v.codecs = omniCapsCodecs(type);
        v.width = video.width;
        v.height = video.height;
        v.bitrate = video.bitrate;
        v.framerate = video.framerate;
        v.alpha = video.alphaChannel.value_or(false);
        v.hdr = video.hdrMetadataType.has_value()
            || (video.colorGamut && *video.colorGamut != PlatformMediaCapabilitiesColorGamut::SRGB)
            || (video.transferFunction && *video.transferFunction != PlatformMediaCapabilitiesTransferFunction::SRGB);
        query.video = std::move(v);
        videoType = omniCapsUtf8(video.contentType);
        enginesAccept = enginesAccept && omniCapsEngineAccepts(configuration, video.contentType);
    }
    if (configuration.audio) {
        auto& audio = *configuration.audio;
        ContentType type(audio.contentType);
        AudioQuery a;
        a.containerType = omniCapsUtf8(type.containerType());
        a.codecs = omniCapsCodecs(type);
        a.channels = omniCapsUtf8(audio.channels);
        a.samplerate = audio.samplerate;
        a.bitrate = audio.bitrate;
        a.spatialRendering = audio.spatialRendering.value_or(false);
        query.audio = std::move(a);
        audioType = omniCapsUtf8(audio.contentType);
        enginesAccept = enginesAccept && omniCapsEngineAccepts(configuration, audio.contentType);
    }
    Answer answer = decide(query);
    if (answer.supported && !enginesAccept)
        answer = refuse("engine supportsType refused");
    static unsigned logged;
    if (logged < 48) {
        ++logged;
        fprintf(stderr, "OMNI MEDIACAPS: type=%s video=\"%.80s\" %ux%u@%.3g audio=\"%.60s\" -> supported=%d smooth=%d powerEfficient=%d (%s)\n",
            query.kind == Kind::MediaSource ? "media-source" : query.kind == Kind::File ? "file" : "other",
            videoType.c_str(), query.video ? query.video->width : 0u, query.video ? query.video->height : 0u,
            query.video ? query.video->framerate : 0.0, audioType.c_str(),
            answer.supported, answer.smooth, answer.powerEfficient, answer.reason);
        fflush(stderr);
    }
    PlatformMediaCapabilitiesDecodingInfo info;
    info.supported = answer.supported;
    info.smooth = answer.supported && answer.smooth;
    info.powerEfficient = answer.supported && answer.powerEfficient;
    info.configuration = WTF::move(configuration);
    callback(WTF::move(info));
}
// Called once in each WebProcess before WebProcessMain (OmniMain.cpp runChild).
void omniInstallMediaCapabilities()
{
    static bool installed;
    if (installed)
        return;
    installed = true;
    // OMNI_WEBM_V1: one line per process. OMNI_HLS_RELAY_V1: on by default since OMNI_CODEC_VP9_DEFAULT_V1.
    fprintf(stderr, "OMNI MEDIACAPS: %s\n", OmniMedia::webmMseEnabled() ? "webm offered (default)" : "webm off (webm-disabled.flag)");
    if (!access("/data/omni/mediacaps-disabled.flag", F_OK)) {
        fprintf(stderr, "OMNI MEDIACAPS: disabled by /data/omni/mediacaps-disabled.flag\n");
        return;
    }
    omniMediaCapsHardware = OmniMedia::Hw::flagEnabled();
    PlatformMediaEngineConfigurationFactory::installFactory({ &omniCreateDecodingConfiguration, nullptr });
    fprintf(stderr, "OMNI MEDIACAPS: decodingInfo factory installed (hardware=%d)\n", omniMediaCapsHardware ? 1 : 0);
}
// OMNI_MEDIACAPS_V1 adapter end
}
#endif
