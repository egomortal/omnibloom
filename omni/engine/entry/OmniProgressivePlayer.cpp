// Progressive playback of MP4/WebM files for <video src="file.mp4"> (OMNI_PROGRESSIVE_V1).
// SPDX-License-Identifier: GPL-3.0-or-later
//
// The plain file player (OmniMediaPlayer.cpp) downloads a file whole, up to 32 MiB, before it
// plays. This one reads it as it plays (media/OmniProgressive.h): HTTP range requests of 1 MiB
// through the element's PlatformMediaResourceLoader (cookies, the element's CORS mode, the network
// process and content blocking apply as to the plain player's single request), a 16 MiB block
// cache, FFmpeg (OmniMedia::VideoDecoder, software, as the plain player) on its own thread.
//   * it plays once the moov and the first samples are in (a moov at the end of the file is
//     fetched with its own range request); seeking fetches the new position's range;
//   * a server that ignores Range (200, whole body): the whole file in memory, at most 32 MiB,
//     as the plain player did;
//   * CORS as the plain player: didPassCORSAccessCheck() is the resources' didPassAccessControlCheck()
//     (every range request's, all of them); accessControlCheckFailed fails the load; the URLs of
//     every response and redirect count for isCrossOrigin();
//   * audio: the UI-process relay (OmniAudioRelay.h), this process's SDL device when the relay
//     is off or full; never fatal; playbackRate through RateAudio (OmniPlaybackRate.h);
//   * readyState: HaveEnoughData while frames are queued, HaveCurrentData while the decoder waits
//     for the network (the clock holds), HaveMetadata after a seek until its first frame.
// Kill switch: /data/omni/media-progressive-disabled.flag (the plain whole-file player).
//
// OMNI_PROGRESSIVE_HOLEPUNCH_V1: the shell shows the video, as for MSE (OMNI_HOLEPUNCH_V1..V8).
// Before: every frame was decoded in software (at most 1920x1080) and painted into the page; at
// 4K that page paint costs ~50 ms a frame and hitches. Now, when the decode service is there and
// hole punching is allowed (hw-decode.flag, no holepunch-disabled.flag), a file whose video is
// H.264 or HEVC (avcC/hvcC) or VP9, up to 3840x2160, is demuxed by FFmpeg on the pipeline thread
// (packets, VideoDecoder::nextPacket; audio decoded there as before) and decoded on the console's
// hardware through OmniMedia::PacketDecoder on this (main) thread, as the MSE source does. Its
// pictures go the MSE player's way, with the same pure logic (OmniHwClient.h):
//   * HolePunchController decides hole or paint, claims the shell's video plane for the video's
//     rect (holeGeometry: the MSE player's), and asks the shell to pace (V4: the shell queues the
//     decoded pictures and shows each at the vblank its time is due by the clock this player
//     sends, HoleClockSender; V5's deep queue when the client has it). paint() then clears the
//     rect: the page is transparent there and the shell blends it over its video plane;
//   * before pacing / when the shell refuses pacing: each due picture is presented (V1);
//   * everything else (not rendered, opacity/filter/mask/... on the way up, rotated, another video
//     holds the plane, the safety net tripped, page hidden): hole frames are converted to RGBA and
//     painted as before (the paint path), at the size the video is shown (at most 1920x1080);
//   * canvas readers (drawImage, snapshots) get real pixels: nativeImageForCurrentTime() and
//     paintCurrentFrameInContext() keep m_image current for one second (shell snapshots while
//     paced, a conversion before each present otherwise), never the hole;
//   * the clock is this player's wall clock, as before (audio follows it as before); it holds
//     while paused, after a seek until the shell has pictures for the new position (or 2.5 s),
//     and while the demuxer waits for the network with nothing decoded ahead;
//   * getVideoPlaybackQuality() counts the shell's shown/dropped pictures while it paces.
// Falls back: no service / hole punching not allowed / other codecs: the software player above,
// unchanged. The hardware decoder will not open (no channel free in 2 s, unsupported profile):
// the load starts again on the software player (refused above 1920x1080, as before). H.264
// above 1080p is accepted on the hardware only for this player (omniProgressiveLargeH264).
// Kill switch: /data/omni/progressive-holepunch-disabled.flag (host: OMNI_PROGRESSIVE_HOLEPUNCH=0),
// read at every load: the software player exactly as before.
#include "config.h"
#include "../media/OmniProgressive.h"
#include "../media/OmniAudioRelay.h"
#include "../media/OmniPlaybackRate.h"
#include "OmniMSEClock.h" // OMNI_PERF_C_V4: ClockAudio, DisplayLock, FrameRateEstimator
#include "../media/OmniPacketDecoder.h" // OMNI_PROGRESSIVE_HOLEPUNCH_V1
#include "../media/OmniHwClient.h"      // OMNI_PROGRESSIVE_HOLEPUNCH_V1
#include "../media/OmniDiagnosticMode.h"
#include <WebCore/MediaPlayerPrivate.h>
#include <WebCore/PlatformMediaResourceLoader.h>
#include <WebCore/ResourceRequest.h>
#include <WebCore/ResourceResponse.h>
#include <WebCore/GraphicsContext.h>
#include <WebCore/ColorSpace.h>
#include <WebCore/SecurityOrigin.h>
#include <WebCore/OriginAccessPatterns.h>
#include <WebCore/FloatQuad.h> // OMNI_PROGRESSIVE_HOLEPUNCH_V1: holeGeometry (as OmniMSEPlayer.cpp)
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
#include <WebCore/VideoPlaybackQualityMetrics.h>
#include "../media/OmniHwPlatform.h"   // OMNI_PROGRESSIVE_HOLEPUNCH_V1: holeV5FlagEnabled, nowMs
#include "../media/OmniTabMediaRelease.h" // OMNI_TAB_MEDIA_RELEASE_V1
#include <WebCore/Document.h>          // OMNI_TAB_MEDIA_RELEASE_V1: the element's document URL
#include <WebCore/NodeDocument.h>      // OMNI_TAB_MEDIA_RELEASE_V1: Node::document()
#include <skia/core/SkData.h>
#include <skia/core/SkImage.h>
#include <skia/core/SkPixmap.h>
#include <wtf/RunLoop.h>
#include <wtf/MonotonicTime.h>
#include <wtf/WeakPtr.h>
#include <wtf/text/MakeString.h>
#include <algorithm>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <optional>
#include <unistd.h>
#define SDL_MAIN_HANDLED
#include <SDL2/SDL.h>

namespace OmniMedia { void omniProgressiveLargeH264(bool on); } // OMNI_PROGRESSIVE_HOLEPUNCH_V1 (OmniPacketDecoder.cpp)

namespace WebCore {

static void omniProgressiveLog(const char* format, ...) __attribute__((format(printf, 1, 2)));
static void omniProgressiveLog(const char* format, ...)
{
    static unsigned lines;
    if (lines++ >= 200) return;
    fprintf(stderr, "OMNI PROGRESSIVE: ");
    va_list args;
    va_start(args, format);
    vfprintf(stderr, format, args);
    va_end(args);
    fputc('\n', stderr);
    fflush(stderr);
}
// OMNI_PROGRESSIVE_HOLEPUNCH_V1: its own bounded log (a console stderr line can take 200 ms: no
// periodic lines unless verbose-diagnostics.flag).
static void omniProgressiveHoleLog(const char* format, ...) __attribute__((format(printf, 1, 2)));
static void omniProgressiveHoleLog(const char* format, ...)
{
    static unsigned lines;
    if (lines++ >= 120) return;
    fprintf(stderr, "OMNI PROGRESSIVE HOLEPUNCH: ");
    va_list args;
    va_start(args, format);
    vfprintf(stderr, format, args);
    va_end(args);
    fputc('\n', stderr);
    fflush(stderr);
}
// OMNI_PROGRESSIVE_HOLEPUNCH_V1: the kill switch, read at every load.
static bool omniProgressiveHoleFlag()
{
    if (const char* env = getenv("OMNI_PROGRESSIVE_HOLEPUNCH")) return env[0] != '0';
#ifdef __PROSPERO__
    return access("/data/omni/progressive-holepunch-disabled.flag", F_OK) != 0;
#else
    return true;
#endif
}
static std::string omniProgressiveUtf8(const String& value)
{
    auto utf8 = value.utf8();
    return std::string(reinterpret_cast<const char*>(utf8.data()), utf8.length());
}

class OmniProgressivePlayer;
class OmniProgressiveRequest final : public PlatformMediaResourceClient {
public:
    OmniProgressiveRequest(OmniProgressivePlayer& owner, uint64_t id) : m_owner(owner), m_id(id) { }
    void responseReceived(PlatformMediaResource&, const ResourceResponse&, CompletionHandler<void(ShouldContinuePolicyCheck)>&&) final;
    void redirectReceived(PlatformMediaResource&, ResourceRequest&&, const ResourceResponse&, CompletionHandler<void(ResourceRequest&&)>&&) final;
    void dataReceived(PlatformMediaResource&, const SharedBuffer&) final;
    void loadFinished(PlatformMediaResource&, const NetworkLoadMetrics&) final;
    void loadFailed(PlatformMediaResource&, const ResourceError&) final;
    void accessControlCheckFailed(PlatformMediaResource&, const ResourceError&) final;
private:
    WeakPtr<OmniProgressivePlayer> m_owner;
    uint64_t m_id;
};

class OmniProgressivePlayer final : public MediaPlayerPrivateInterface, public RefCounted<OmniProgressivePlayer>, public CanMakeWeakPtr<OmniProgressivePlayer> {
public:
    void ref() const final { RefCounted::ref(); }
    void deref() const final { RefCounted::deref(); }
    explicit OmniProgressivePlayer(MediaPlayer& player)
        : m_player(player), m_timer(RunLoop::mainSingleton(), "OmniProgressivePlayer::tick"_s, this, &OmniProgressivePlayer::tick) { }
    ~OmniProgressivePlayer() { cancelLoad(); }
    constexpr MediaPlayerType mediaPlayerType() const final { return MediaPlayerType::OmniFFmpeg; }
    String engineDescription() const final { return "Omni FFmpeg progressive video"_s; }
#if ENABLE(MEDIA_SOURCE)
    void load(const URL&, const LoadOptions&, MediaSourcePrivateClient&) final { fail(MediaPlayer::NetworkState::FormatError); }
#endif
    void load(const URL& url, const LoadOptions&) final
    {
        cancelLoad();
        m_hwRefused = false; // OMNI_PROGRESSIVE_HOLEPUNCH_V1
        startLoad(url);
    }
    void cancelLoad() final
    {
        m_timer.stop();
        dropRequest();
        holeReset(); // OMNI_PROGRESSIVE_HOLEPUNCH_V1: before the decoder goes (its frames release through it)
        m_decoder = nullptr; m_packet.reset(); m_output.reset();
        m_hw = false; m_hasVideoHw = false; m_drainSent = false; m_decoderEnded = false; m_awaitKey = false;
        m_lock = 1; m_rateAudio.setLock(1); m_videoRate.reset(); m_lockChanges = 0; m_lockEnabled = Omni::DisplayLock::enabled(); // OMNI_PERF_C_V4
        m_tabMedia = { }; // OMNI_TAB_MEDIA_RELEASE_V1
        m_videoDiscardBefore = -1; m_size = { };
        m_pipeline = nullptr;   // stops its thread (aborts the cache's reads first)
        m_cache = nullptr;
        audioClose();
        m_image = nullptr; m_frame = OmniMedia::VideoFrame { }; m_framePending = false;
        m_urls.clear(); m_buffered.clear(); m_seekable.clear();
        m_position = m_base = m_length = 0;
        m_paused = true; m_ended = false; m_haveMetadata = false; m_corsPassed = false; m_corsSeen = false;
        m_waitingFirstFrame = false; m_stalled = false; m_progress = false; m_lastReceived = 0;
        m_network = MediaPlayer::NetworkState::Empty;
        m_ready = MediaPlayer::ReadyState::HaveNothing;
    }
    void play() final
    {
        m_paused = false; m_anchor = MonotonicTime::now(); m_base = m_position;
        if (m_audioReleased && m_pipeline && m_haveMetadata) seekInternal(m_position);
        audioPause(false);
        if (m_cache) m_timer.startRepeating(16_ms);
        if (RefPtr current = m_player.get()) current->playbackStateChanged();
    }
    void pause() final
    {
        m_paused = true; m_base = m_position; m_pausedAt = MonotonicTime::now();
        audioPause(true);
        if (RefPtr current = m_player.get()) current->playbackStateChanged();
    }
    bool paused() const final { return m_paused; }
    bool ended() const final { return m_ended; }
    FloatSize naturalSize() const final { return m_hw ? m_size : FloatSize { float(m_frame.width), float(m_frame.height) }; } // OMNI_PROGRESSIVE_HOLEPUNCH_V1: m_size
    bool hasVideo() const final { return m_hw ? m_hasVideoHw : !!m_image; } // OMNI_PROGRESSIVE_HOLEPUNCH_V1: no m_image while the shell shows it
    bool hasAudio() const final { return m_pipeline && m_pipeline->hasAudio(); }
    bool supportsFullscreen() const final { return true; }
    void setVolume(float value) final { m_volume = std::isfinite(value) ? std::clamp(value, 0.0f, 1.0f) : 0; }
    void setMuted(bool value) final { m_muted = value; if (value && m_audio) m_audio->clearQueued(); }
    void setPageIsVisible(bool value) final { m_visible = value; }
    MediaTime duration() const final { return m_haveMetadata ? MediaTime::createWithDouble(m_length) : MediaTime::zeroTime(); }
    MediaTime currentTime() const final { return MediaTime::createWithDouble(m_position); }
    // OMNI_PLAYBACK_RATE_V1
    double rate() const final { return m_requestedRate; }
    double effectiveRate() const final { return m_rate; }
    void setRate(float requested) final { applyRate(requested); }
    void setRateDouble(double requested) final { applyRate(requested); }
    void setPreservesPitch(bool) final { }
    MediaPlayer::NetworkState networkState() const final { return m_network; }
    MediaPlayer::ReadyState readyState() const final { return m_ready; }
    const PlatformTimeRanges& buffered() const final { return m_buffered; }
    const PlatformTimeRanges& seekable() const final { return m_seekable; }
    MediaTime maxTimeSeekable() const final { return duration(); }
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
        if (!m_pipeline || !m_haveMetadata) return MediaTimePromise::createAndReject(PlatformMediaError::Cancelled);
        if (!m_cache->ranges() && !m_cache->wholeComplete()) return MediaTimePromise::createAndReject(PlatformMediaError::Cancelled);
        seekInternal(std::clamp(target.time.toDouble(), 0.0, m_length));
        if (RefPtr current = m_player.get()) current->timeChanged();
        return MediaTimePromise::createAndResolve(currentTime());
    }
    void paint(GraphicsContext& context, const FloatRect& rect) final
    {
        if (!m_hw) {
            if (m_image && m_visible) context.drawNativeImage(*m_image, rect, FloatRect(0, 0, m_frame.width, m_frame.height));
            return;
        }
        // OMNI_PROGRESSIVE_HOLEPUNCH_V1: the shell draws the video under the page: a transparent hole.
        if (m_holePunch.holeActive()) {
            if (m_visible) { context.clearRect(rect); ++m_holePaintClears; }
            return;
        }
        // The paint path: frames converted at the size they are shown (device pixels; the
        // conversion keeps them within 1920x1080), as the MSE player.
        AffineTransform ctm = context.getCTM();
        const double sx = ctm.xScale(), sy = ctm.yScale();
        const int w = int(std::lround(rect.width() * sx)), h = int(std::lround(rect.height() * sy));
        if (!ctm.b() && !ctm.c() && sx > 0 && sy > 0 && w > 0 && h > 0 && w <= 4096 && h <= 4096 && (w != m_targetWidth || h != m_targetHeight)) {
            m_targetWidth = w; m_targetHeight = h;
            if (m_decoder) m_decoder->setVideoTargetSize(w, h);
        }
        if (m_image && m_visible) {
            context.drawNativeImage(*m_image, rect, FloatRect({ }, FloatSize(m_image->size())));
            if (m_imageSerial != m_lastPaintedSerial) { m_lastPaintedSerial = m_imageSerial; ++m_shownFrames; }
        }
    }
    ColorSpace colorSpace() final { return ColorSpace::SRGB(); }
    RefPtr<NativeImage> nativeImageForCurrentTime() final
    {
        m_holeCanvasUntil = MonotonicTime::now() + 1_s; // OMNI_PROGRESSIVE_HOLEPUNCH_V1: keep m_image current
        return m_image;
    }
    // OMNI_PROGRESSIVE_HOLEPUNCH_V1: canvas drawImage(video) and snapshots draw the current frame,
    // never the hole, and do not change the paint path's conversion size. Software player: paint().
    void paintCurrentFrameInContext(GraphicsContext& context, const FloatRect& rect) final
    {
        if (!m_hw) { paint(context, rect); return; }
        m_holeCanvasUntil = MonotonicTime::now() + 1_s;
        if (m_image && m_visible)
            context.drawNativeImage(*m_image, rect, FloatRect({ }, FloatSize(m_image->size())));
    }
    // OMNI_PROGRESSIVE_HOLEPUNCH_V1: with the shell's counts while it paces (as OMNI_HOLEPUNCH_V7_QUALITY).
    std::optional<VideoPlaybackQualityMetrics> videoPlaybackQualityMetrics() final
    {
        if (!m_hw) return std::nullopt;   // the software player had none
        auto bounded = [](uint64_t value) { return uint32_t(std::min<uint64_t>(value, std::numeric_limits<uint32_t>::max())); };
        qualityPacingCounts();
        const uint64_t shellShown = m_qDoneShown + m_qRunShown, shellDropped = m_qDoneDropped + m_qRunDropped;
        VideoPlaybackQualityMetrics metrics;
        metrics.totalVideoFrames = bounded(m_decodedFrames + shellShown + shellDropped);
        metrics.droppedVideoFrames = bounded(m_replacedFrames + shellDropped);
        metrics.displayCompositedVideoFrames = bounded(m_shownFrames + shellShown);
        return metrics;
    }

    // ---- network ----------------------------------------------------------------------------------
    bool owns(uint64_t id) const { return id == m_requestId && m_resource; }
    void noteURL(const URL& url) { m_urls.push_back(url); }
    void responseReceived(uint64_t id, const ResourceResponse& response, bool& accept)
    {
        accept = false;
        if (!owns(id) || !m_cache) return;
        const int status = response.httpStatusCode();
        int64_t start = -1, end = -1, total = -1;
        if (status == 206) OmniMedia::Progressive::parseContentRange(omniProgressiveUtf8(response.httpHeaderField(HTTPHeaderName::ContentRange)), start, end, total);
        std::string why;
        const std::string validator = omniProgressiveUtf8(response.httpHeaderField(HTTPHeaderName::ETag));
        if ((status != 200 && status != 206) || !m_cache->response(status, start, total, response.expectedContentLength(), validator, why)) {
            omniProgressiveLog("response %d refused: %s", status, why.empty() ? "not 200/206" : why.c_str());
            failSoon(status == 200 || status == 206 ? MediaPlayer::NetworkState::FormatError : MediaPlayer::NetworkState::NetworkError);
            return;
        }
        noteURL(response.url());
        accept = true;
        if (!m_pipeline && m_cache->ranges()) {
            omniProgressiveLog("%lld bytes, byte ranges: playing as it loads", static_cast<long long>(total));
            startPipeline();
        } else if (!m_pipeline && m_cache->whole())
            omniProgressiveLog("the server sends no byte ranges: the whole file first (up to 32 MiB)");
    }
    void dataReceived(uint64_t id, const SharedBuffer& data)
    {
        if (!owns(id) || !m_cache) return;
        auto span = data.span();
        m_cache->data(span.data(), span.size());
        m_progress = true;
    }
    void loadFinished(uint64_t id, PlatformMediaResource& resource)
    {
        if (!owns(id) || !m_cache) return;
        // CORS: every range request must pass (as the plain player's single request had to).
        const bool passed = resource.didPassAccessControlCheck();
        m_corsPassed = m_corsSeen ? (m_corsPassed && passed) : passed;
        m_corsSeen = true;
        m_cache->finished();
        dropRequest();
        if (!m_pipeline && m_cache->wholeComplete()) startPipeline();
        RunLoop::mainSingleton().dispatch([weak = WeakPtr { *this }] { if (weak) weak->serviceNetwork(); });
    }
    void loadFailed(uint64_t id, bool cors)
    {
        if (!owns(id)) return;
        omniProgressiveLog("request failed%s", cors ? " (access control)" : "");
        if (m_cache) m_cache->fail(cors ? "access control check failed" : "network error");
        failSoon(MediaPlayer::NetworkState::NetworkError);
    }

private:
    // The body of load() (OMNI_PROGRESSIVE_HOLEPUNCH_V1: shared with reloadSoftware()).
    void startLoad(const URL& url)
    {
        if (!url.protocolIsInHTTPFamily()) { fail(MediaPlayer::NetworkState::FormatError); return; }
        RefPtr current = m_player.get();
        if (!current) return;
        m_loader = current->mediaResourceLoader();
        m_url = url;
        m_urls.push_back(url);
        m_cache = std::make_shared<OmniMedia::Progressive::RangeCache>();
        m_network = MediaPlayer::NetworkState::Loading;
        m_ready = MediaPlayer::ReadyState::HaveNothing;
        m_started = MonotonicTime::now();
        // OMNI_PROGRESSIVE_HOLEPUNCH_V1: the hardware / shell path when the service is there.
        const bool flag = omniProgressiveHoleFlag(), allowed = OmniMedia::Hw::Client::holePunchAllowed();
        m_hwWanted = flag && allowed && !m_hwRefused;
        static unsigned modeLogs;
        if (modeLogs < 4) {
            ++modeLogs;
            omniProgressiveHoleLog("%s", m_hwWanted ? "on: H.264/HEVC/VP9 files decode on the hardware and are shown by the shell (kill switch progressive-holepunch-disabled.flag)"
                : !flag ? "off: progressive-holepunch-disabled.flag (software player)" : !allowed ? "off: no hardware decoding or hole punching (hw-decode.flag, holepunch-disabled.flag): software player"
                : "off for this load: the hardware decoder did not open (software player)");
        }
        auto first = m_cache->firstRequest();
        if (!request(first.offset, first.length)) { fail(MediaPlayer::NetworkState::NetworkError); return; }
        m_timer.startRepeating(16_ms);
        current->networkStateChanged();
    }
    bool request(int64_t offset, int64_t length)
    {
        if (!m_loader) return false;
        ResourceRequest request { URL(m_url) };
        request.setHTTPHeaderField(HTTPHeaderName::Range, makeString("bytes="_s, offset, '-', offset + length - 1));
        m_resource = m_loader->requestResource(WTF::move(request), PlatformMediaResourceLoader::DisallowCaching);
        if (!m_resource) return false;
        m_requestId = ++m_requestCounter;
        m_resource->setClient(adoptRef(*new OmniProgressiveRequest(*this, m_requestId)));
        return true;
    }
    void dropRequest()
    {
        if (!m_resource) return;
        // A loader callback may hold checked references to itself: shut it down after it unwinds.
        auto previous = std::exchange(m_resource, nullptr);
        m_requestId = 0;
        RunLoop::mainSingleton().dispatch([previous = WTF::move(previous)] { previous->setClient(nullptr); previous->shutdown(); });
    }
    void serviceNetwork()
    {
        if (!m_cache || !m_cache->ranges()) return;
        if (m_resource && m_cache->shouldCancel()) { dropRequest(); m_cache->cancelled(); }
        if (m_resource) return;
        if (auto next = m_cache->nextRequest()) {
            if (!request(next->offset, next->length)) { m_cache->fail("request failed"); failSoon(MediaPlayer::NetworkState::NetworkError); }
        }
    }
    void startPipeline()
    {
        m_pipeline = std::make_unique<OmniMedia::Progressive::Pipeline>(m_cache);
        m_pipeline->requestPackets(m_hwWanted); // OMNI_PROGRESSIVE_HOLEPUNCH_V1
        m_pipeline->start();
    }
    void failSoon(MediaPlayer::NetworkState state)
    {
        RunLoop::mainSingleton().dispatch([weak = WeakPtr { *this }, state] { if (weak) weak->fail(state); });
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
    void seekInternal(double t)
    {
        m_pipeline->seek(t);
        m_position = m_base = t; m_anchor = MonotonicTime::now();
        m_framePending = false; m_ended = false; m_waitingFirstFrame = true; m_audioReleased = false;
        audioClear();
        m_rateAudio.reset();
        if (m_hw) hwSeek(t); // OMNI_PROGRESSIVE_HOLEPUNCH_V1
        if (m_haveMetadata) setReady(MediaPlayer::ReadyState::HaveMetadata);
        if (!m_paused) m_timer.startRepeating(16_ms);
    }
    void applyRate(double requested)   // OMNI_PLAYBACK_RATE_V1
    {
        m_requestedRate = requested;
        const double rate = OmniMedia::Rate::effective(requested);
        if (rate == m_rate) return;
        m_base = m_position; m_anchor = MonotonicTime::now();
        m_rate = rate;
        if (rate > 0 && rate != m_rateAudio.rate()) {
            if (m_audio) m_audio->clearQueued();
            if (!m_rateAudio.setRate(rate, m_position)) m_rateAudio.reset();
        }
        audioPause(m_paused || rate <= 0);
        omniProgressiveLog("rate %.2f (requested %.3f)", rate, requested);
        RunLoop::mainSingleton().dispatch([weak = WeakPtr { *this }] { if (weak) if (RefPtr current = weak->m_player.get()) current->rateChanged(); });
    }
    // ---- audio: the relay first, this process's SDL device otherwise; never fatal ---------------
    void audioOpen()
    {
        if (m_audio || m_audioReleased || MonotonicTime::now() < m_audioRetryAt) return;
        std::string why;
        m_audio = OmniMedia::Audio::Output::openRelay(why);
        if (!m_audio) {
            if (m_audioLogs < 4) { ++m_audioLogs; omniProgressiveLog("audio: relay unavailable (%s); this process's own SDL output", why.c_str()); }
            SDL_SetMainReady();
            if (!m_audioInitialized && !SDL_InitSubSystem(SDL_INIT_AUDIO)) m_audioInitialized = true;
            if (m_audioInitialized) {
                SDL_AudioSpec wanted { }, actual { };
                wanted.freq = 48000; wanted.channels = 2; wanted.format = AUDIO_S16LSB; wanted.samples = 1024;
                m_audio = OmniMedia::Audio::Output::openSdl(&wanted, &actual);
            }
        }
        if (!m_audio) {
            omniProgressiveLog("audio: no output; video plays on, next attempt in %.0f s", m_audioRetryMs / 1000);
            m_audioRetryAt = MonotonicTime::now() + Seconds::fromMilliseconds(m_audioRetryMs);
            m_audioRetryMs = std::min(16000.0, m_audioRetryMs * 2);
            return;
        }
        m_audioRetryMs = 2000;
        m_audio->pause(m_paused || m_rate <= 0);
        omniProgressiveLog("audio: %s", m_audio->describe().c_str());
    }
    void audioPause(bool paused) { if (m_audio) m_audio->pause(paused); }
    void audioClear() { if (m_audio) m_audio->clearQueued(); }
    void audioClose()
    {
        if (m_audio) { m_audio->clearQueued(); m_audio = nullptr; }
        if (m_audioInitialized) { SDL_QuitSubSystem(SDL_INIT_AUDIO); m_audioInitialized = false; }
        m_rateAudio.reset();
        m_audioReleased = false; m_audioRetryAt = { }; m_audioRetryMs = 2000;
    }
    void pumpAudio()
    {
        std::vector<int16_t> pcm;
        double media = 0;
        // OMNI_PROGRESSIVE_HOLEPUNCH_V1: in packet mode the demuxer can run seconds ahead (the hardware
        // keeps up to ~3.5 s in flight): take PCM only while under 0.5 s waits here, so the pipeline's
        // 2 s PCM limit holds the demuxer back instead of RateAudio's 1 s backlog dropping audio.
        if ((!m_hw || m_rateAudio.backlogFrames() < 24000) && m_pipeline->takePcm(pcm, media)) {
            if (!m_haveAudioTime || std::fabs(media - m_audioNext) > 0.002) m_audioNext = media;
            m_rateAudio.push(pcm.data(), pcm.size() / 2, m_audioNext);
            m_audioNext += double(pcm.size() / 2) / 48000; m_haveAudioTime = true;
        }
        if (m_pipeline->ended()) m_rateAudio.endOfStream();
        if (!m_audio) { audioOpen(); if (!m_audio) { m_rateAudio.reset(); return; } }
        constexpr unsigned limit = 48000 * 2 * sizeof(int16_t);   // up to 1 s queued
        const float gain = m_muted ? 0 : m_volume;
        int16_t out[4096 * 2];
        for (int guard = 0; guard < 64; guard++) {
            const size_t room = (limit - std::min(limit, m_audio->queuedBytes())) / (2 * sizeof(int16_t));
            if (room < size_t(OmniMedia::Rate::TimeStretch::hop)) break;
            double start = 0, speed = 1;
            const size_t n = m_rateAudio.pull(out, std::min<size_t>(room, 4096), start, speed);
            if (!n) break;
            for (size_t i = 0; i < n * 2; i++) out[i] = int16_t(out[i] * gain);
            (void)m_audio->queue(out, unsigned(n * 2 * sizeof(int16_t)));
        }
        if (m_rateAudio.backlogFrames() > 48000) m_rateAudio.reset();   // over 1 s waiting: dropped
    }
    void publish()
    {
        auto info = SkImageInfo::Make(m_frame.width, m_frame.height, kRGBA_8888_SkColorType, kUnpremul_SkAlphaType);
        m_image = NativeImage::create(SkImages::RasterFromPixmapCopy(SkPixmap(info, m_frame.rgba.data(), m_frame.width * 4)));
        if (RefPtr current = m_player.get()) current->repaint();
    }
    void updateRanges()
    {
        m_buffered.clear(); m_seekable.clear();
        if (!m_haveMetadata || m_length <= 0) return;
        m_seekable.add(MediaTime::zeroTime(), MediaTime::createWithDouble(m_length));
        // What is cached contiguously from the decoder's read position, as media time (bytes are
        // spread evenly enough over a file for an estimate).
        const int64_t total = m_cache->size();
        if (total > 0) {
            const int64_t at = m_cache->readPosition();
            const double end = std::min(m_length, m_length * double(at + m_cache->contiguousFrom(at)) / double(total));
            if (end > m_position) m_buffered.add(MediaTime::createWithDouble(m_position), MediaTime::createWithDouble(end));
        }
    }
    void tick()
    {
        Ref protect { *this };
        if (!m_cache) return;
        serviceNetwork();
        if (!m_pipeline) {
            if (MonotonicTime::now() - m_started > 30_s) fail(MediaPlayer::NetworkState::NetworkError);
            return;
        }
        RefPtr current = m_player.get();
        if (!current) return;
        if (m_pipeline->state() == OmniMedia::Progressive::Pipeline::State::Failed) {
            omniProgressiveLog("failed: %s", m_pipeline->error().c_str());
            fail(m_cache->error().empty() ? MediaPlayer::NetworkState::FormatError : MediaPlayer::NetworkState::NetworkError);
            return;
        }
        if (m_pipeline->state() == OmniMedia::Progressive::Pipeline::State::Opening) {
            if (MonotonicTime::now() - m_started > 60_s) fail(MediaPlayer::NetworkState::NetworkError);
            return;
        }
        // Paused for 60 s: the output goes back (the relay's channels are few); play() decodes again.
        if (m_paused && m_audio && (MonotonicTime::now() - m_pausedAt).seconds() > 60) {
            omniProgressiveLog("audio: released its output (paused for 60 s)");
            m_audio->clearQueued(); m_audio = nullptr; m_audioReleased = true;
        }
        if (!m_haveMetadata && m_pipeline->packetMode()) { // OMNI_PROGRESSIVE_HOLEPUNCH_V1
            if (!hwStart(*current)) return;
        } else if (!m_haveMetadata) {
            double first = 0;
            if (!m_pipeline->frontTime(first)) return;   // the first frame is not decoded yet
            m_haveMetadata = true; m_length = m_pipeline->duration();
            m_pipeline->popFrame(m_frame); publish();
            m_position = m_base = 0; m_anchor = MonotonicTime::now();
            omniProgressiveLog("first frame after %.2f s (%llu requests, %llu bytes)", (MonotonicTime::now() - m_started).seconds(),
                static_cast<unsigned long long>(m_cache->requests()), static_cast<unsigned long long>(m_cache->receivedBytes()));
            current->durationChanged(); current->sizeChanged();
            setReady(MediaPlayer::ReadyState::HaveEnoughData);
            m_network = MediaPlayer::NetworkState::Loading; current->networkStateChanged();
        }
        if (m_hw) { tabMediaTick(); if (m_hw && m_decoder) tickHw(*current); return; } // OMNI_PROGRESSIVE_HOLEPUNCH_V1; OMNI_TAB_MEDIA_RELEASE_V1: tabMediaTick
        if (m_pipeline->hasAudio()) pumpAudio();
        // The clock runs while frames are there; it holds while the decoder waits for the network.
        double next = 0;
        const bool have = m_pipeline->frontTime(next);
        const bool end = m_pipeline->ended();
        const bool stalled = !have && !end && !m_pipeline->seeking() && m_cache->readerWaiting();
        if (stalled != m_stalled) { m_stalled = stalled; if (stalled) omniProgressiveLog("waiting for the network at %.2f s", m_position); }
        if (!m_paused && !stalled && !m_waitingFirstFrame && m_rate > 0) m_position = std::min(m_length, m_base + (MonotonicTime::now() - m_anchor).seconds() * clockRate()); // OMNI_PERF_C_V4: x lock
        else { m_base = m_position; m_anchor = MonotonicTime::now(); }
        // Frames: the newest one that is due (the first one at once after a seek).
        bool shown = false;
        while (m_pipeline->frontTime(next) && (m_waitingFirstFrame || next <= m_position + 0.008)) {
            m_pipeline->popFrame(m_frame); shown = true;
            if (m_waitingFirstFrame) { m_waitingFirstFrame = false; m_base = m_position; m_anchor = MonotonicTime::now(); break; }
        }
        if (shown) publish();
        updateRanges();
        setReady(m_waitingFirstFrame ? MediaPlayer::ReadyState::HaveMetadata : stalled ? MediaPlayer::ReadyState::HaveCurrentData : MediaPlayer::ReadyState::HaveEnoughData);
        if (!m_ended && end && m_position >= m_length - 0.05 && (!m_audio || !m_audio->queuedBytes())) {
            m_ended = true; m_paused = true; audioPause(true);
            omniProgressiveLog("ended (%llu requests, %.1f MiB received, cache peak %.1f MiB, queues peak %.1f MiB)",
                static_cast<unsigned long long>(m_cache->requests()), double(m_cache->receivedBytes()) / 1048576,
                double(m_cache->peakCachedBytes()) / 1048576, double(m_pipeline->peakQueuedBytes()) / 1048576);
            current->timeChanged(); current->playbackStateChanged();
            return;
        }
        if (!m_paused) current->timeChanged();
    }

    // ---- OMNI_PROGRESSIVE_HOLEPUNCH_V1: hardware decoding, shown by the shell -------------------
    static const char* codecName(OmniMedia::DemuxCodec codec)
    {
        return codec == OmniMedia::DemuxCodec::H264 ? "H.264" : codec == OmniMedia::DemuxCodec::HEVC ? "HEVC" : codec == OmniMedia::DemuxCodec::VP9 ? "VP9" : "?";
    }
    // The pipeline opened in packet mode: open the hardware decoder. False: the load started again
    // on the software player (this call's caller returns at once).
    bool hwStart(MediaPlayer& current)
    {
        const auto track = m_pipeline->videoTrack();
        m_decoder = std::make_unique<OmniMedia::PacketDecoder>();
        m_decoder->setVideoPixelOrder(kN32_SkColorType == kBGRA_8888_SkColorType ? OmniMedia::PacketDecoder::PixelOrder::BGRA : OmniMedia::PacketDecoder::PixelOrder::RGBA);
        m_decoder->setVideoTargetSize(m_targetWidth, m_targetHeight);
        m_decoder->setHolePunch(false);   // the controller turns it on (decoderHoles)
        OmniMedia::omniProgressiveLargeH264(true);
        const bool configured = m_decoder->configure(track);
        OmniMedia::omniProgressiveLargeH264(false);
        if (!configured || !m_decoder->usingHardware()) {
            const std::string why = configured ? "decode service busy or unavailable" : m_decoder->error();
            omniProgressiveHoleLog("%s %dx%d: the hardware decoder did not open (%s); the load starts again on the software player",
                codecName(track.codec), track.width, track.height, why.c_str());
            reloadSoftware();
            return false;
        }
        m_hw = true; m_hasVideoHw = true;
        m_holeAllowed = OmniMedia::Hw::Client::holePunchAllowed();
        m_holePacingAllowed = OmniMedia::Hw::Client::holePacingAllowed();
        m_holeDeep = OmniMedia::Hw::holeV5FlagEnabled();
        m_switchHandoff = OmniMedia::SwitchHandoff::enabled();
        m_haveMetadata = true; m_length = m_pipeline->duration();
        m_size = { float(track.width), float(track.height) };
        m_position = m_base = 0; m_anchor = MonotonicTime::now();
        m_waitingFirstFrame = true; m_waitSinceMs = OmniMedia::Hw::nowMs(); m_genReports = 0;
        m_videoDiscardBefore = -1;
        omniProgressiveHoleLog("%s %dx%d on the hardware decoder after %.2f s (%llu requests, %llu bytes); pacing %s, deep queue %s",
            codecName(track.codec), track.width, track.height, (MonotonicTime::now() - m_started).seconds(),
            static_cast<unsigned long long>(m_cache->requests()), static_cast<unsigned long long>(m_cache->receivedBytes()),
            m_holePacingAllowed ? "allowed" : "off (holepunch-pacing-disabled.flag)", m_holeDeep ? "on" : "off (holepunch-v5-disabled.flag)");
        current.durationChanged(); current.sizeChanged();
        setReady(MediaPlayer::ReadyState::HaveMetadata);
        m_network = MediaPlayer::NetworkState::Loading; current.networkStateChanged();
        return true;
    }
    void reloadSoftware()
    {
        const URL url = m_url;
        const bool paused = m_paused;   // play() may have come before the metadata: keep it
        cancelLoad();
        m_paused = paused;
        m_hwRefused = true;
        startLoad(url);
    }
    void hwSeek(double t)
    {
        ++m_generation;
        if (m_decoder) m_decoder->flush();
        m_packet.reset(); m_output.reset();
        m_holeDue = nullptr; m_holeHasFrame = false;
        m_drainSent = false; m_decoderEnded = false; m_awaitKey = false;
        m_videoDiscardBefore = t;
        m_waitSinceMs = OmniMedia::Hw::nowMs(); m_genReports = 0;
    }
    // OMNI_PERF_C_V4 (OmniMSEClock.h): the wall clock, the shell's clock and the audio (resampled) run at
    // rate x lock: 60 / 30 / 24 fps files on the 59.94 Hz display play at 1000/1001, no picture too many.
    // Hardware (paced) path only; a change re-anchors the wall clock (what is queued, <= 1 s, keeps its speed).
    double clockRate() const { return m_rate * m_lock; }
    void displayLockTick()
    {
        const double want = m_lockEnabled && m_hasVideoHw ? Omni::DisplayLock::factor(m_videoRate.fps(), Omni::DisplayLock::displayHz()) : 1;
        if (want == m_lock) return;
        m_base = m_position; m_anchor = MonotonicTime::now();
        m_lock = want; m_rateAudio.setLock(want); ++m_lockChanges;
    }
    void tickHw(MediaPlayer& current)
    {
        displayLockTick(); // OMNI_PERF_C_V4
        if (m_pipeline->hasAudio()) pumpAudio();
        const double nowMs = OmniMedia::Hw::nowMs();
        if (m_waitingFirstFrame) firstPictureFromShell(nowMs);
        // The clock holds while the demuxer waits for the network with nothing decoded ahead.
        const bool demuxEnded = m_pipeline->demuxEnded();
        const bool starving = !demuxEnded && !m_packet && !m_pipeline->queuedPackets() && !m_pipeline->seeking() && m_cache->readerWaiting();
        bool stalled = false;
        if (starving) stalled = m_holePunch.paced() && m_holeLink ? m_holeLink->pacing().aheadMs < 150 : !m_output;
        if (stalled != m_stalled) { m_stalled = stalled; if (stalled) omniProgressiveLog("waiting for the network at %.2f s", m_position); }
        if (!m_paused && !stalled && !m_waitingFirstFrame && m_rate > 0) m_position = std::min(m_length, m_base + (MonotonicTime::now() - m_anchor).seconds() * clockRate()); // OMNI_PERF_C_V4: x lock
        else { m_base = m_position; m_anchor = MonotonicTime::now(); }
        if (!pumpVideo()) return;   // failed: the load is gone
        updateHolePunch(nowMs);
        updateRanges();
        setReady(m_waitingFirstFrame ? MediaPlayer::ReadyState::HaveMetadata : stalled ? MediaPlayer::ReadyState::HaveCurrentData : MediaPlayer::ReadyState::HaveEnoughData);
        const bool drained = m_decoderEnded || (m_drainSent && nowMs - m_drainSentMs > 2000);
        if (!m_ended && demuxEnded && m_pipeline->ended() && drained && !m_output && m_position >= m_length - 0.05 && (!m_audio || !m_audio->queuedBytes())) {
            m_ended = true; m_paused = true; audioPause(true);
            omniProgressiveLog("ended (%llu requests, %.1f MiB received, cache peak %.1f MiB, queues peak %.1f MiB; hardware video)",
                static_cast<unsigned long long>(m_cache->requests()), double(m_cache->receivedBytes()) / 1048576,
                double(m_cache->peakCachedBytes()) / 1048576, double(m_pipeline->peakQueuedBytes()) / 1048576);
            current.timeChanged(); current.playbackStateChanged();
            return;
        }
        if (!m_paused) current.timeChanged();
    }
    // After the start or a seek while the shell paces: its pictures for the new position never
    // come here; the clock starts once the shell reports pictures queued ahead of it (two reports
    // after the new clock went out), at most 2.5 s after the seek.
    void firstPictureFromShell(double nowMs)
    {
        if (!m_holePunch.paced() || !m_holeLink) return;   // the paint path: the first picture comes to consumeVideo()
        const auto& pacing = m_holeLink->pacing();
        if (pacing.atMs != m_genLastReportAt) { m_genLastReportAt = pacing.atMs; if (m_genClockSent == m_generation && m_genClockSentValid) ++m_genReports; }
        const bool timedOut = nowMs - m_waitSinceMs > 2500;
        if (!timedOut && !(m_genReports >= 2 && pacing.aheadMs >= 120)) return;
        if (timedOut) omniProgressiveHoleLog("no first picture 2.5 s after the start or seek at %.3f s: the clock starts anyway", m_position);
        firstPictureShown();
    }
    void firstPictureShown()
    {
        m_waitingFirstFrame = false;
        m_base = m_position; m_anchor = MonotonicTime::now();
    }
    // Feed the decoder and take its pictures (as OmniMSESource::pump). False: the load failed.
    bool pumpVideo()
    {
        if (!m_decoder || m_decoder->hardwareReleased()) return true; // OMNI_TAB_MEDIA_RELEASE_V1: not fed while given back
        unsigned outputs = 0;
        for (unsigned steps = 0; steps < 96 && outputs < 24; ++steps) {
            if (m_output) {
                if (!consumeVideo(*m_output)) break;   // not due yet
                m_output.reset(); ++outputs;
                continue;
            }
            OmniMedia::DecodedOutput output;
            const auto received = m_decoder->receive(output);
            if (received == OmniMedia::PacketDecoder::Receive::Error) return decoderFailed("decode");
            if (received == OmniMedia::PacketDecoder::Receive::Output) { m_output = std::move(output); continue; }
            if (received == OmniMedia::PacketDecoder::Receive::End) { m_decoderEnded = true; break; }
            if (!m_packet) {
                OmniMedia::DemuxPacket packet;
                while (m_pipeline->popPacket(packet)) {
                    if (m_awaitKey && !packet.keyFrame) continue;   // after a resync: from the next keyframe
                    m_awaitKey = false;
                    if (packet.timeBase.denominator > 0 && !packet.nonDisplaying) { // OMNI_PERF_C_V4: the content's frame rate
                        const double tick = double(packet.timeBase.numerator) / packet.timeBase.denominator;
                        m_videoRate.push(double(packet.pts) * tick, tick);
                    }
                    m_packet = std::move(packet);
                    break;
                }
            }
            if (m_packet) {
                const auto sent = m_decoder->submit(*m_packet);
                if (sent == OmniMedia::PacketDecoder::Submit::Error) return decoderFailed("submit");
                if (sent == OmniMedia::PacketDecoder::Submit::NeedOutput) break;   // in flight to the decoder: next tick
                m_packet.reset();
                continue;
            }
            if (m_pipeline->demuxEnded() && !m_drainSent) {
                const auto sent = m_decoder->drain();
                if (sent == OmniMedia::PacketDecoder::Submit::Error) return decoderFailed("drain");
                if (sent == OmniMedia::PacketDecoder::Submit::Accepted) { m_drainSent = true; m_drainSentMs = OmniMedia::Hw::nowMs(); }
                continue;
            }
            break;
        }
        return true;
    }
    bool decoderFailed(const char* stage)
    {
        omniProgressiveHoleLog("hardware video %s failed (%s) at %.3f s", stage, m_decoder ? m_decoder->error().c_str() : "?", m_position);
        fail(MediaPlayer::NetworkState::DecodeError);
        return false;
    }
    // One decoded picture: shown (presented by the shell, or painted) or dropped: true; not due yet: false.
    bool consumeVideo(OmniMedia::DecodedOutput& output)
    {
        if (output.kind != OmniMedia::DecodedOutput::Kind::Video) return true;
        if (output.nonDisplaying || !output.hasTimestamp || output.timeBase.denominator <= 0) { ++m_decodedFrames; return true; }
        const double time = double(output.timestamp) * output.timeBase.numerator / output.timeBase.denominator;
        if (!std::isfinite(time)) { ++m_decodedFrames; return true; }
        if (m_videoDiscardBefore >= 0 && time + 0.000001 < m_videoDiscardBefore) { ++m_decodedFrames; return true; }   // before the seek target
        const bool haveFrame = m_image || m_holeHasFrame;
        if (!m_waitingFirstFrame) {
            // OMNI_HOLEPUNCH_V5_REV3, as the MSE player: while the shell paces, a hole frame decoded into an
            // output slot before pacing began and ahead of the playhead is freed, not held (it would keep the
            // decoder from being fed).
            if (m_holeDeep && output.hole && m_holePunch.paced() && haveFrame && time > m_position + 0.005) { ++m_decodedFrames; ++m_replacedFrames; return true; }
            if (haveFrame && time > m_position + 0.008) return false;
        }
        if (m_waitingFirstFrame) firstPictureShown();   // the first picture at once (a poster), the clock from here
        m_videoDiscardBefore = -1;
        if (output.sourceWidth > 0 && output.sourceHeight > 0) {
            const FloatSize size { float(output.sourceWidth), float(output.sourceHeight) };
            if (size != m_size) { m_size = size; if (RefPtr current = m_player.get()) current->sizeChanged(); }
        }
        if (output.hole) {   // still in the decoder's output slot
            m_holeLink = output.hole->link();
            if (m_holePunch.presenting()) {   // due: the shell shows it (updateHolePunch); a newer one replaces it unshown
                if (m_holeDue) ++m_replacedFrames;
                m_holeDue = std::move(output.hole);
                m_holeDueTime = time; m_holeHasFrame = true;
                ++m_decodedFrames;
                return true;
            }
            if (!m_holeLink->alive()) { ++m_decodedFrames; return true; }
            if (m_image && time + 0.1 < m_position) { ++m_decodedFrames; ++m_replacedFrames; return true; }   // late: freed unconverted
            if (!output.hole->convert(output)) { ++m_decodedFrames; return true; }
            output.hole = nullptr;
        }
        publishOutput(output);
        return true;
    }
    void publishOutput(OmniMedia::DecodedOutput& output)
    {
        ++m_decodedFrames;
        if (output.width <= 0 || output.height <= 0 || output.rgba.size() != size_t(output.width) * output.height * 4) return;
        auto info = SkImageInfo::Make(output.width, output.height, output.bgra ? kBGRA_8888_SkColorType : kRGBA_8888_SkColorType,
            output.opaque ? kOpaque_SkAlphaType : kUnpremul_SkAlphaType);
        if (m_image && m_imageSerial != m_lastPaintedSerial) ++m_replacedFrames;
        auto* pixels = new std::vector<uint8_t>(std::move(output.rgba));
        auto pixelData = SkData::MakeWithProc(pixels->data(), pixels->size(),
            [](const void*, void* context) { delete static_cast<std::vector<uint8_t>*>(context); }, pixels);
        m_image = NativeImage::create(SkImages::RasterFromData(info, std::move(pixelData), size_t(output.width) * 4));
        m_imageSerial = m_decodedFrames;
        if (RefPtr current = m_player.get()) current->repaint();
    }
    // The video's paint rect in view pixels (OmniMSEPlayer::holeGeometry, unchanged).
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
            box = owner ? dynamicDowncast<RenderElement>(owner->Node::renderer()) : nullptr;
        }
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
    void holeImage(OmniMedia::Hw::HoleFrame& frame, bool forPage)
    {
        OmniMedia::DecodedOutput copy;
        if (frame.convert(copy)) holeImageFrom(copy, forPage);
    }
    // forPage: painted the normal way (a due frame the shell does not show); else kept for canvas readers.
    void holeImageFrom(OmniMedia::DecodedOutput& copy, bool forPage)
    {
        if (copy.width <= 0 || copy.height <= 0 || copy.rgba.size() != size_t(copy.width) * copy.height * 4) return;
        auto info = SkImageInfo::Make(copy.width, copy.height, copy.bgra ? kBGRA_8888_SkColorType : kRGBA_8888_SkColorType, kOpaque_SkAlphaType);
        auto* pixels = new std::vector<uint8_t>(std::move(copy.rgba));
        auto pixelData = SkData::MakeWithProc(pixels->data(), pixels->size(),
            [](const void*, void* context) { delete static_cast<std::vector<uint8_t>*>(context); }, pixels);
        m_image = NativeImage::create(SkImages::RasterFromData(info, std::move(pixelData), size_t(copy.width) * 4));
        if (!forPage) { m_imageSerial = m_lastPaintedSerial; ++m_holeCanvasCopies; return; }
        m_imageSerial = ++m_decodedFrames;
        if (RefPtr current = m_player.get()) current->repaint();
    }
    // Once per tick after pumping: hole or paint, and the messages to the shell (OmniMSEPlayer::updateHolePunch).
    void updateHolePunch(double nowMs)
    {
        using Controller = OmniMedia::Hw::HolePunchController;
        if (m_holeLink && !m_holeLink->alive()) m_holeLink = nullptr;
        if (m_holeLink) m_holeLink->pump();   // acks arrive even while nothing is due
        Controller::Input in;
        in.nowMs = nowMs;
        in.link = m_holeLink.get();
        in.linkState = m_holeLink ? m_holeLink->state() : 0;
        in.frameDue = !!m_holeDue;
        in.shownCount = m_holeLink ? m_holeLink->shownCount() : 0;
        in.playing = !m_paused && m_position > m_holeLastPosition;
        m_holeLastPosition = m_position;
        const char* why = !m_holeAllowed ? "disabled" : !m_visible ? "page hidden" : "no video";
        if (m_holeAllowed && m_visible && hasVideo())
            in.eligible = holeGeometry(in.rect, in.onScreen, why);
        if (in.eligible && !in.onScreen) why = "off screen";
        holePacingInput(in);
        const bool wasActive = m_holePunch.holeActive();
        const bool wasPaced = m_holePunch.paced();
        m_holePunch.setSwitchHandoff(m_switchHandoff);
        auto act = m_holePunch.tick(in);
        if (act.bail) holeBailLog(in);
        if (act.claim && !m_holeLink->claim(in.rect)) m_holePunch.claimNotSent();   // socket full: next tick
        if (act.enterHole) {
            m_image = nullptr;   // never paint a stale frame after the hole
            if (RefPtr current = m_player.get()) current->repaint();
        }
        if (act.present) {
            if (MonotonicTime::now() < m_holeCanvasUntil) holeImage(*m_holeDue, false);
            const bool sent = m_holeDue->present(in.rect);
            m_holePunch.presentResult(sent, in.nowMs);
            if (sent) ++m_shownFrames;
            m_holeDue = nullptr;
        }
        if (act.paintDue) { holeImage(*m_holeDue, true); m_holeDue = nullptr; }
        if (act.moveRect && !m_holeLink->claim(in.rect)) m_holePunch.rectNotSent();
        if (act.hide && m_holeLink) m_holeLink->hide();
        if (act.leaveHole) if (RefPtr current = m_player.get()) current->repaint();
        if (m_decoder) m_decoder->setHolePunch(act.decoderHoles);
        // Pacing ended because the video is not seen (page hidden, scrolled off): the pictures queued
        // in the shell and the ~3 s in flight would come back here to be converted. Drop them (the
        // flush) and decode again from the next keyframe; the audio plays on (OMNI_MSE_SWITCH_HANDOFF_V1's
        // resync, video only).
        if (m_switchHandoff && m_holeDeep && wasPaced && !m_holePunch.paced() && m_decoder && (!m_visible || (in.eligible && !in.onScreen))) {
            ++m_generation;
            m_decoder->flush();
            m_packet.reset(); m_output.reset(); m_holeDue = nullptr; m_holeHasFrame = false;
            m_drainSent = false; m_decoderEnded = false; m_awaitKey = true;
            m_videoDiscardBefore = m_position;
            if (m_holeLink) m_holeLink->pacingStopped();
            omniProgressiveHoleLog("player %s while paced: the video decodes again from the next keyframe after %.3f s (the shell's queued pictures were dropped)",
                !m_visible ? "page hidden" : "video off screen", m_position);
        }
        holeClockTick(in, act);
        holeStatsTick(in);
        if ((act.enterHole || (wasActive && act.leaveHole)) && m_holeLogLines < 24) {
            ++m_holeLogLines;
            if (m_holePunch.bailReason()) why = m_holePunch.bailReason();
            else if (in.eligible && in.onScreen) why = m_holeLink ? m_holeLink->reason() : "decoder gone";
            omniProgressiveHoleLog("player %s rect=%dx%d at %d,%d reason=%s presented=%llu rectUpdates=%llu refusals=%llu paced=%d",
                act.enterHole ? "hole on" : "hole off, paint path", in.rect.w, in.rect.h, in.rect.x, in.rect.y,
                act.enterHole ? "shown by the shell" : why, static_cast<unsigned long long>(m_holePunch.presented),
                static_cast<unsigned long long>(m_holePunch.rectUpdates), static_cast<unsigned long long>(m_holePunch.refusals), m_holePunch.paced());
        }
    }
    void holeBailLog(const OmniMedia::Hw::HolePunchController::Input& in)
    {
        if (m_holeLogLines >= 24) return;
        ++m_holeLogLines;
        auto stats = m_holeLink ? m_holeLink->stats() : OmniMedia::Hw::HoleLink::Stats { };
        omniProgressiveHoleLog("player safety net: %s; paint path for this video. due=%d held=%u clientReady=%zu submitsOutstanding=%u lastServiceMessageAgoMs=%.0f shown=%llu presented=%llu playing=%d position=%.3f",
            m_holePunch.bailReason(), in.frameDue, m_holeLink ? m_holeLink->heldFrames() : 0u, stats.ready, stats.outstanding,
            stats.lastMessageAgoMs, static_cast<unsigned long long>(in.shownCount), static_cast<unsigned long long>(m_holePunch.presented),
            in.playing, m_position);
    }
    void holePacingInput(OmniMedia::Hw::HolePunchController::Input& in)
    {
        qualityPacingCounts();
        in.generation = m_generation;
        if (!m_holeLink) return;
        const auto& pacing = m_holeLink->pacing();
        in.pacing = m_holePacingAllowed && m_holeLink->pacingAvailable() && pacing.state >= 0;
        in.pacedShown = pacing.shown; in.pacedDecoded = pacing.decoded; in.pacedWaiting = pacing.waiting;
        in.pacingReportAgeMs = m_holeLink->pacingReportAgeMs();
        in.pacedDeep = m_holeDeep;
        in.pacedPosterSelected = pacing.state == 1 && pacing.atMs > 0 && pacing.startupGeneration == in.generation && (pacing.startupFlags & 8);
        in.pacedReported = pacing.state == 1 && pacing.atMs > 0;
    }
    // The shell's clock (OmniMSEPlayer::holeTickV4): this player's playhead, valid now.
    void holeClockTick(const OmniMedia::Hw::HolePunchController::Input& in, const OmniMedia::Hw::HolePunchController::Actions& act)
    {
        if (!m_holeLink) return;
        const bool paced = m_holePunch.paced();
        const auto now = MonotonicTime::now();
        m_holeSnapshotWanted |= act.snapshot;   // the paint path after the hole starts from the frame on screen
        const bool canvasSnapshot = paced && now < m_holeCanvasUntil && now - m_holeSnapshotAt >= 100_ms;
        if (paced || act.pace || m_holeClockOn || m_holeSnapshotWanted) {
            OmniMedia::Hw::HoleClockState clock;
            clock.paced = act.pace;
            clock.playing = !m_paused && !m_ended && !m_waitingFirstFrame && !m_stalled && m_rate > 0 && !m_pipeline->seeking();
            clock.rate = m_rate > 0 ? clockRate() : 1; // OMNI_PERF_C_V4: rate x lock
            double position = m_position;
            if (clock.playing) position = m_base + (now - m_anchor).seconds() * clockRate();
            if (m_length > 0) { position = std::min(position, m_length); if (clock.playing) clock.limit = m_length; }
            clock.position = position;
            clock.generation = m_generation;
            if (m_videoDiscardBefore >= 0) clock.discardBefore = m_videoDiscardBefore;
            clock.snapshot = m_holeSnapshotWanted || canvasSnapshot;
            const bool due = m_holeClockSender.due(clock, in.nowMs);
            const bool sent = due && m_holeLink->sendClock(clock);
            if (sent) {
                m_holeClockSender.sent(clock, in.nowMs);
                if (clock.snapshot) { m_holeSnapshotAt = now; m_holeSnapshotWanted = false; }
                if (clock.paced && (!m_genClockSentValid || m_genClockSent != m_generation)) { m_genClockSent = m_generation; m_genClockSentValid = true; m_genReports = 0; }
            }
            m_holeClockOn = act.pace || (due && !sent);
        }
        OmniMedia::DecodedOutput snapshot;
        if (m_holeLink->takeSnapshot(snapshot)) holeImageFrom(snapshot, !m_holePunch.holeActive());
    }
    // The shell's counts (HolePacing: the plane's totals) for this video, per pacing run from a
    // baseline at its first report, summed over the runs (as OMNI_HOLEPUNCH_V7_QUALITY).
    void qualityPacingCounts()
    {
        const OmniMedia::Hw::HoleLink* link = m_holeLink.get();
        const bool on = link && link->pacing().state == 1 && link->pacing().atMs > 0;
        if (link != m_qLink || !on) {
            if (m_qOn) { m_qDoneShown += m_qRunShown; m_qDoneDropped += m_qRunDropped; m_qRunShown = m_qRunDropped = 0; }
            m_qOn = false; m_qLink = link;
        }
        if (!on) return;
        const auto& pacing = link->pacing();
        if (!m_qOn) { m_qOn = true; m_qBaseShown = pacing.shown; m_qBaseDropped = pacing.dropped; }
        m_qRunShown = pacing.shown >= m_qBaseShown ? pacing.shown - m_qBaseShown : 0;
        m_qRunDropped = pacing.dropped >= m_qBaseDropped ? pacing.dropped - m_qBaseDropped : 0;
    }
    // Every 5 s with the hole on, one line (verbose-diagnostics.flag only): what the shell showed.
    void holeStatsTick(const OmniMedia::Hw::HolePunchController::Input& in)
    {
        if (!m_holePunch.holeActive() || !m_holeLink) { m_statsStartMs = 0; return; }
        const auto& pacing = m_holeLink->pacing();
        if (!m_statsStartMs) {
            m_statsStartMs = m_statsLastTickMs = in.nowMs; m_statsTicks = 0; m_statsMaxGapMs = 0;
            m_statsShown = pacing.shown; m_statsDropped = pacing.dropped; m_statsLate = pacing.late; m_statsPresented = m_holePunch.presented;
            return;
        }
        ++m_statsTicks;
        m_statsMaxGapMs = std::max(m_statsMaxGapMs, in.nowMs - m_statsLastTickMs);
        m_statsLastTickMs = in.nowMs;
        const double span = in.nowMs - m_statsStartMs;
        if (span < 5000) return;
        if (m_statsLines < 60 && omniReleaseDiagnostics()) {
            ++m_statsLines;
            auto delta = [](uint64_t now, uint64_t then) { return static_cast<unsigned long long>(now >= then ? now - then : 0); };
            omniProgressiveHoleLog("player stats %.1f s: paced=%d shown=%llu dropped=%llu late=%llu presented=%llu waiting=%u aheadMs=%u ticks=%llu maxTickGapMs=%.0f position=%.3f paused=%d lock=%.6f lockChanges=%u fps=%.3f",
                span / 1000, m_holePunch.paced(), delta(pacing.shown, m_statsShown), delta(pacing.dropped, m_statsDropped), delta(pacing.late, m_statsLate),
                delta(m_holePunch.presented, m_statsPresented), pacing.waiting, pacing.aheadMs, static_cast<unsigned long long>(m_statsTicks), m_statsMaxGapMs, m_position, m_paused, m_lock, m_lockChanges, m_videoRate.fps()); // OMNI_PERF_C_V4
        }
        m_statsStartMs = 0;
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
    // OMNI_TAB_MEDIA_RELEASE_V1 (OmniTabMediaRelease.h): hidden 1.5 s with a hardware stream: paused
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
    void holeReset()
    {
        if (m_holeLink && m_holePunch.claimed()) m_holeLink->hide();
        if ((m_holePunch.presented || m_holePunch.paced() || m_holePunch.holeActive()) && m_holeLogLines < 24) {
            ++m_holeLogLines;
            qualityPacingCounts();
            omniProgressiveHoleLog("player done presented=%llu shownByShellPaced=%llu droppedByShell=%llu rectUpdates=%llu claims=%llu refusals=%llu paintClears=%llu canvasCopies=%llu safetyNet=%s",
                static_cast<unsigned long long>(m_holePunch.presented), static_cast<unsigned long long>(m_qDoneShown + m_qRunShown),
                static_cast<unsigned long long>(m_qDoneDropped + m_qRunDropped), static_cast<unsigned long long>(m_holePunch.rectUpdates),
                static_cast<unsigned long long>(m_holePunch.claims), static_cast<unsigned long long>(m_holePunch.refusals),
                static_cast<unsigned long long>(m_holePaintClears), static_cast<unsigned long long>(m_holeCanvasCopies),
                m_holePunch.bailReason() ? m_holePunch.bailReason() : "not tripped");
        }
        m_holeDue = nullptr; m_holeLink = nullptr; m_holeHasFrame = false;
        m_holePunch = { };
        m_holeLastRect.reset(); m_holeLastOnScreen = false;
        m_holePaintClears = m_holeCanvasCopies = 0;
        m_holeLastPosition = 0; m_holeDueTime = 0;
        m_holeClockSender = { }; m_holeClockOn = false; m_holeSnapshotWanted = false;
        m_generation = 0; m_genClockSent = 0; m_genClockSentValid = false; m_genReports = 0; m_genLastReportAt = 0;
        m_qLink = nullptr; m_qOn = false; m_qBaseShown = m_qBaseDropped = m_qRunShown = m_qRunDropped = m_qDoneShown = m_qDoneDropped = 0;
        m_decodedFrames = m_shownFrames = m_replacedFrames = 0;
        m_imageSerial = m_lastPaintedSerial = 0;
        m_statsStartMs = 0;
    }

    ThreadSafeWeakPtr<MediaPlayer> m_player;
    RunLoop::Timer m_timer;
    RefPtr<PlatformMediaResourceLoader> m_loader;
    RefPtr<PlatformMediaResource> m_resource;
    uint64_t m_requestId = 0, m_requestCounter = 0;
    URL m_url;
    std::vector<URL> m_urls;
    std::shared_ptr<OmniMedia::Progressive::RangeCache> m_cache;
    std::unique_ptr<OmniMedia::Progressive::Pipeline> m_pipeline;
    OmniMedia::VideoFrame m_frame;
    RefPtr<NativeImage> m_image;
    PlatformTimeRanges m_buffered, m_seekable;
    MonotonicTime m_started, m_anchor, m_pausedAt, m_audioRetryAt;
    double m_position = 0, m_base = 0, m_length = 0;
    double m_requestedRate = 1, m_rate = 1;
    double m_audioRetryMs = 2000, m_audioNext = 0;
    bool m_paused = true, m_ended = false, m_visible = true, m_haveMetadata = false, m_waitingFirstFrame = false, m_stalled = false;
    bool m_corsPassed = false, m_corsSeen = false, m_framePending = false, m_haveAudioTime = false;
    mutable bool m_progress = false;
    uint64_t m_lastReceived = 0;
    std::unique_ptr<OmniMedia::Audio::Output> m_audio;
    Omni::ClockAudio m_rateAudio; // OMNI_PERF_C_V4: RateAudio + the display lock's resampler
    double m_lock = 1; // OMNI_PERF_C_V4: clock factor (display / content rate), 1 = off
    bool m_lockEnabled = true;
    unsigned m_lockChanges = 0;
    Omni::FrameRateEstimator m_videoRate; // OMNI_PERF_C_V4: from the video packets
    bool m_audioInitialized = false, m_audioReleased = false, m_muted = false;
    unsigned m_audioLogs = 0;
    float m_volume = 1;
    MediaPlayer::NetworkState m_network = MediaPlayer::NetworkState::Empty;
    MediaPlayer::ReadyState m_ready = MediaPlayer::ReadyState::HaveNothing;
    // ---- OMNI_PROGRESSIVE_HOLEPUNCH_V1 ----
    bool m_hwWanted = false, m_hwRefused = false, m_hw = false, m_hasVideoHw = false;
    std::unique_ptr<OmniMedia::PacketDecoder> m_decoder;
    std::optional<OmniMedia::DemuxPacket> m_packet;     // retained after NeedOutput
    std::optional<OmniMedia::DecodedOutput> m_output;   // decoded, not due yet
    bool m_drainSent = false, m_decoderEnded = false, m_awaitKey = false;
    double m_drainSentMs = 0, m_videoDiscardBefore = -1;
    FloatSize m_size;
    int m_targetWidth = 0, m_targetHeight = 0;
    OmniMedia::Hw::HolePunchController m_holePunch;
    std::shared_ptr<OmniMedia::Hw::HoleLink> m_holeLink;
    std::shared_ptr<OmniMedia::Hw::HoleFrame> m_holeDue;
    double m_holeDueTime = 0, m_holeLastPosition = 0;
    bool m_holeHasFrame = false, m_holeAllowed = false, m_holePacingAllowed = false, m_holeDeep = false, m_switchHandoff = false;
    std::optional<OmniMedia::Hw::HoleLink::Rect> m_holeLastRect;
    bool m_holeLastOnScreen = false;
    MonotonicTime m_holeCanvasUntil, m_holeSnapshotAt;
    bool m_holeSnapshotWanted = false, m_holeClockOn = false;
    OmniMedia::Hw::HoleClockSender m_holeClockSender;
    uint32_t m_generation = 0, m_genClockSent = 0;
    bool m_genClockSentValid = false;
    unsigned m_genReports = 0;
    double m_genLastReportAt = 0, m_waitSinceMs = 0;
    unsigned m_holeLogLines = 0;
    uint64_t m_holePaintClears = 0, m_holeCanvasCopies = 0;
    uint64_t m_decodedFrames = 0, m_shownFrames = 0, m_replacedFrames = 0, m_imageSerial = 0, m_lastPaintedSerial = 0;
    const OmniMedia::Hw::HoleLink* m_qLink = nullptr;
    bool m_qOn = false;
    uint64_t m_qBaseShown = 0, m_qBaseDropped = 0, m_qRunShown = 0, m_qRunDropped = 0, m_qDoneShown = 0, m_qDoneDropped = 0;
    double m_statsStartMs = 0, m_statsLastTickMs = 0, m_statsMaxGapMs = 0;
    uint64_t m_statsTicks = 0, m_statsShown = 0, m_statsDropped = 0, m_statsLate = 0, m_statsPresented = 0;
    unsigned m_statsLines = 0;
    OmniMedia::TabMedia::Gate m_tabMedia; // OMNI_TAB_MEDIA_RELEASE_V1
};

void OmniProgressiveRequest::redirectReceived(PlatformMediaResource&, ResourceRequest&& request, const ResourceResponse&, CompletionHandler<void(ResourceRequest&&)>&& completion)
{
    Ref protect { *this };
    if (!m_owner || !m_owner->owns(m_id) || !request.url().protocolIsInHTTPFamily()) {
        completion(ResourceRequest { });
        if (m_owner && m_owner->owns(m_id)) m_owner->loadFailed(m_id, false);
        return;
    }
    m_owner->noteURL(request.url());
    completion(WTF::move(request));
}
void OmniProgressiveRequest::responseReceived(PlatformMediaResource&, const ResourceResponse& response, CompletionHandler<void(ShouldContinuePolicyCheck)>&& completion)
{
    Ref protect { *this };
    bool accept = false;
    if (m_owner) m_owner->responseReceived(m_id, response, accept);
    completion(accept ? ShouldContinuePolicyCheck::Yes : ShouldContinuePolicyCheck::No);
}
void OmniProgressiveRequest::dataReceived(PlatformMediaResource&, const SharedBuffer& data) { Ref protect { *this }; if (m_owner) m_owner->dataReceived(m_id, data); }
void OmniProgressiveRequest::loadFinished(PlatformMediaResource& resource, const NetworkLoadMetrics&) { Ref protect { *this }; if (m_owner) m_owner->loadFinished(m_id, resource); }
void OmniProgressiveRequest::loadFailed(PlatformMediaResource&, const ResourceError&) { Ref protect { *this }; if (m_owner) m_owner->loadFailed(m_id, false); }
void OmniProgressiveRequest::accessControlCheckFailed(PlatformMediaResource&, const ResourceError&) { Ref protect { *this }; if (m_owner) m_owner->loadFailed(m_id, true); }

Ref<MediaPlayerPrivateInterface> createOmniProgressivePlayer(MediaPlayer& player)
{
    return adoptRef(*new OmniProgressivePlayer(player));
}

}
