// Experimental main-dispatcher MSE bridge. SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#if ENABLE(MEDIA_SOURCE)
#include "../media/OmniPacketDecoder.h"
#include <WebCore/MediaSourcePrivate.h>
#include <wtf/Function.h>
#include <string>
#include "../media/OmniMediaCaps.h" // OMNI_MEDIACAPS_V1
#include "../media/OmniWebMDemuxer.h" // OMNI_WEBM_V1
#include "../media/OmniHwPlatform.h"
#include <WebCore/ContentType.h>
#include "OmniMSEClock.h" // OMNI_PERF_C_V4: FrameRateEstimator

namespace WebCore {
// OMNI_MEDIACAPS_V1: the one MSE type check (isTypeSupported, addSourceBuffer, decodingInfo).
inline OmniMedia::Caps::Support omniMSETypeSupport(const ContentType& type)
{
    std::vector<std::string> codecs;
    for (auto& codec : type.codecs()) {
        auto utf8 = codec.utf8();
        codecs.emplace_back(reinterpret_cast<const char*>(utf8.data()), utf8.length()); // CString::data() is char8_t here
    }
    auto container = type.containerType().utf8();
    // OMNI_CODEC_OPUS_V1: one table call. WebM only while offered (OmniMedia::webmMseEnabled());
    // the answers depend on the hardware flag and the FFmpeg decoders present (Opus in MP4 too).
    OmniMedia::Caps::Platform platform;
    platform.hardware = OmniMedia::Hw::flagEnabled();
    platform.webm = OmniMedia::webmMseEnabled();
    platform.decoders = OmniMedia::webmDecoders();
    return OmniMedia::Caps::mseTypeSupport(std::string_view(reinterpret_cast<const char*>(container.data()), container.length()), codecs, platform);
}
class OmniMSESource final : public MediaSourcePrivate {
public:
    static Ref<OmniMSESource> create(MediaSourcePrivateClient&,
        Function<RefPtr<MediaPlayerPrivateInterface>()>&&, Function<void()>&&);
    RefPtr<MediaPlayerPrivateInterface> player() const final;
    void setPlayer(MediaPlayerPrivateInterface*) final;
    constexpr MediaPlatformType platformType() const final { return MediaPlatformType::OmniFFmpeg; }
    AddStatus addSourceBuffer(const ContentType&, const MediaSourceConfiguration&, RefPtr<SourceBufferPrivate>&) final;
    void notifyActiveSourceBuffersChanged() final;
    void durationChanged(const MediaTime&) final;
    void bufferedChanged(PlatformTimeRanges&&) final;
    bool supportsTracksTypeChanged() const final { return true; }
    void markEndOfStream(EndOfStreamStatus) final;
    void unmarkEndOfStream() final;
    bool pump(const Function<bool(OmniMedia::DecodedOutput&)>&);
    bool playbackDrained() const;
    void flushPlayback();
    // OMNI_MSE_SWITCH_HANDOFF_V1: the video tracks decode again from the playhead (audio untouched).
    void resyncVideo();
    // OMNI_TAB_MEDIA_RELEASE_V1 (OmniTabMediaRelease.h): a background tab's video gives its hardware
    // decoders back (the tracks' streams and a stream opened ahead). Released video is not fed.
    // reacquireVideoHardware(giveUp) true: every video track decodes again (giveUp: on software,
    // or failing, where no channel came free); the caller then calls resyncVideo().
    bool videoUsingHardware();
    bool releaseVideoHardware();
    bool reacquireVideoHardware(bool giveUp);
    // OMNI_MSE_SWITCH_HANDOFF_V1: the last video configuration change (quality switch), for the
    // player's log once the new stream plays. count: changes so far (0: none).
    struct VideoSwitch {
        uint64_t count = 0;
        uint32_t from = 0, to = 0;
        bool waited = false;           // the shell still had the old stream's pictures
        bool preopened = false;        // the new stream was opened ahead (its decoder set up meanwhile)
        double waitedMs = 0, drainedAt = 0, playhead = 0, switchPoint = 0;   // playhead seconds at the drain / at the configuration
        const char* why = "";
    };
    const VideoSwitch& videoSwitch() const { return m_videoSwitch; }
    void videoSwitched(const VideoSwitch&);
    // Monotonic per-kind generations invalidate already presented/queued data.
    uint64_t audioPresentationGeneration() const { return m_audioPresentationGeneration; }
    uint64_t videoPresentationGeneration() const { return m_videoPresentationGeneration; }
    void presentationFlushed(bool audio);
    const std::string& error() const { return m_error; }
    // OMNI_VIDEO_TARGET_V1: on-screen size of the video in device pixels (0 = unknown).
    void setVideoTargetSize(int width, int height) { m_videoTargetWidth = width; m_videoTargetHeight = height; }
    int videoTargetWidth() const { return m_videoTargetWidth; }
    int videoTargetHeight() const { return m_videoTargetHeight; }
    // OMNI_HOLEPUNCH_V1: hardware video frames stay in their decode slots (DecodedOutput::hole).
    void setVideoHolePunch(bool on) { m_videoHolePunch = on; }
    bool videoHolePunch() const { return m_videoHolePunch; }
    // OMNI_HOLEPUNCH_V3: decoded outputs one pump may hand to the player per buffer (4 =
    // V1 behaviour). While the shell shows the video, late frames cost only a Release, so the
    // player raises it to catch up when its ticks come slowly.
    // waitMs: while the shown frame lags, the pump may also wait this long in total for the
    // hardware decoder when its input slots are full (it starves at slow ticks otherwise).
    void setVideoOutputBudget(unsigned outputs, int waitMs = 0) { m_videoOutputBudget = outputs ? outputs : 4; m_videoWaitMs = waitMs; }
    unsigned videoOutputBudget() const { return m_videoOutputBudget; }
    int videoWaitMs() const { return m_videoWaitMs; }
    void changed();
    void failed(const char*);
    // OMNI_PERF_C_V4: the video's frame rate from the samples enqueued (all video tracks; nominal
    // rate or 0 = not known), for the player's display lock (OmniMSEClock.h).
    void videoSampleTime(double pts, double quantum) { m_videoRate.push(pts, quantum); }
    double videoFrameRate() const { return m_videoRate.fps(); }
    double videoFrameRateMeasured() const { return m_videoRate.measured(); }
private:
    OmniMSESource(MediaSourcePrivateClient&, Function<RefPtr<MediaPlayerPrivateInterface>()>&&, Function<void()>&&);
    Function<RefPtr<MediaPlayerPrivateInterface>()> m_player;
    Function<void()> m_changed;
    std::string m_error;
    uint32_t m_nextBufferID { 1 };
    uint64_t m_audioPresentationGeneration { 0 }, m_videoPresentationGeneration { 0 };
    bool m_changeScheduled { false };
    int m_videoTargetWidth { 0 }, m_videoTargetHeight { 0 };
    bool m_videoHolePunch { false }; // OMNI_HOLEPUNCH_V1
    unsigned m_videoOutputBudget { 4 }; // OMNI_HOLEPUNCH_V3
    int m_videoWaitMs { 0 };
    VideoSwitch m_videoSwitch; // OMNI_MSE_SWITCH_HANDOFF_V1
    uint64_t m_videoSwitches { 0 };
    Omni::FrameRateEstimator m_videoRate; // OMNI_PERF_C_V4
};
}
#endif
