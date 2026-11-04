// Experimental bounded H264/AAC fMP4 bridge; no production capability claim.
// Parsing/decoding currently run on the main dispatcher, not a worker.
#include "config.h"
#if ENABLE(MEDIA_SOURCE)
#include "OmniMSESource.h"
#include "OmniMediaSample.h"
#include "../media/OmniMP4SegmentBuffer.h"
#include "../media/OmniWebMDemuxer.h" // OMNI_WEBM_V1
#include <cmath>
#include <cstdio>
#include <cstdlib> // OMNI_PERF_C_V8: getenv
#include <cstring> // OMNI_PERF_C_V8: strcmp
#include <unistd.h> // OMNI_PERF_C_V8: access
#include <WebCore/AudioTrackPrivate.h>
#include <WebCore/VideoTrackPrivate.h>
#include <WebCore/ContentType.h>
#include <WebCore/MediaDescription.h>
#include <WebCore/MediaPlayerPrivate.h>
#include <WebCore/SharedBuffer.h>
#include <WebCore/SourceBufferPrivate.h>
#include <skia/core/SkImageInfo.h>
#include <wtf/RunLoop.h>
#include <wtf/SetForScope.h>
#include <wtf/MonotonicTime.h> // OMNI_HOLEPUNCH_V3
#include <algorithm>
#include <deque>
#include <map>
#include <optional>

namespace WebCore {
namespace {
constexpr size_t maximumPacket = 1024 * 1024;
constexpr size_t maximumQueued = 2 * 1024 * 1024;
// OMNI_WEBM_V1: WebM buffers: 4K VP9 keyframes reach ~1 MB; a packet may fill one hardware
// input slot (Wire::inputSlotBytes, 4 MiB); the queue admits packets while <= 2 MiB is queued.
// MP4 buffers keep the limits above.
constexpr size_t maximumPacketWebM = 4 * 1024 * 1024;
constexpr size_t maximumQueuedWebM = 6 * 1024 * 1024;
// OMNI_WEBM_V1: decoder configurations (distinct initialization segments) kept per track.
constexpr size_t maximumConfigurations = 16;
constexpr size_t maximumCount = 128;
class Description final : public MediaDescription {
public:
    // OMNI_WEBM_V1: codec four-character code per demuxed codec.
    explicit Description(OmniMedia::DemuxCodec codec)
        : MediaDescription(codec == OmniMedia::DemuxCodec::H264 ? "avc1"_s : codec == OmniMedia::DemuxCodec::AAC ? "mp4a.40.2"_s
            : codec == OmniMedia::DemuxCodec::VP9 ? "vp09"_s : codec == OmniMedia::DemuxCodec::Opus ? "opus"_s
            : codec == OmniMedia::DemuxCodec::HEVC ? "hvc1"_s : "vorb"_s) // OMNI_CODEC_HEVC_V1
        , m_video(OmniMedia::isVideoCodec(codec)) { }
    bool isVideo() const final { return m_video; }
    bool isAudio() const final { return !m_video; }
    bool isText() const final { return false; }
private:
    bool m_video;
};
class AudioTrack final : public AudioTrackPrivate {
public:
    explicit AudioTrack(TrackID id) : m_id(id) { }
    TrackID id() const final { return m_id; }
private:
    TrackID m_id;
};
class VideoTrack final : public VideoTrackPrivate {
public:
    explicit VideoTrack(TrackID id) : m_id(id) { }
    TrackID id() const final { return m_id; }
private:
    TrackID m_id;
};

class Buffer final : public SourceBufferPrivate {
public:
    static Ref<Buffer> create(OmniMSESource& source, uint32_t id, bool webm = false) // OMNI_WEBM_V1
    { return adoptRef(*new Buffer(source, id, webm)); }
    constexpr MediaPlatformType platformType() const final { return MediaPlatformType::OmniFFmpeg; }
    size_t platformMaximumBufferSize() const final { return 32 * 1024 * 1024; }
    void flushPlayback() { for (auto& [id, track] : m_tracks) flush(id); }
    // OMNI_MSE_SWITCH_HANDOFF_V1: the video tracks decode again from the playhead (WebKit re-enqueues
    // them from the random access point before it, as after a renderer flush); audio is untouched.
    void resyncVideo() {
        Vector<TrackID> video;
        for (auto& [id, track] : m_tracks) if (OmniMedia::isVideoCodec(track->info.codec)) video.append(id);
        for (auto id : video) { if (m_detached) return; reenqueSamples(id); }   // flush(id), then from currentTime()
    }
    // OMNI_TAB_MEDIA_RELEASE_V1 (OmniTabMediaRelease.h)
    bool videoUsingHardware() {
        for (auto& [id, track] : m_tracks)
            if (OmniMedia::isVideoCodec(track->info.codec) && (track->decoder.usingHardware() || (track->next && track->next->usingHardware()))) return true;
        return false;
    }
    bool releaseVideoHardware() {
        bool any = false;
        for (auto& [id, track] : m_tracks) {
            if (!OmniMedia::isVideoCodec(track->info.codec)) continue;
            track->output.reset();   // a picture still in its decode slot goes before the stream
            if (track->next) { track->next.reset(); any = true; }   // a stream opened ahead holds a channel too
            track->nextTried = false; track->switchWaitSince.reset();
            if (track->decoder.releaseHardware()) any = true;
        }
        if (any) m_videoHeld = true;
        return any;
    }
    bool reacquireVideoHardware(bool giveUp) {
        bool all = true;
        for (auto& [id, track] : m_tracks) {
            if (!OmniMedia::isVideoCodec(track->info.codec) || !track->decoder.hardwareReleased()) continue;
            if (track->decoder.reacquireHardware()) continue;
            if (giveUp) track->decoder.abandonHardware(); else all = false;
        }
        if (all) m_videoHeld = false;   // fed again from the resync (the caller's resyncVideo)
        return all;
    }
    bool drained() const {
        if (m_tracks.empty()) return false;
        for (auto& [id, track] : m_tracks)
            if (!track->ended || track->output || !track->queue.empty()) return false;
        return true;
    }
    void removedFromMediaSource() final {
        m_detached = true;
        setActive(false);
        flushPlayback(); m_tracks.clear(); m_initialization.clear(); m_parser.reset();
        m_webmParser.clear(); m_webmInitialization = { }; // OMNI_WEBM_V1
        SourceBufferPrivate::removedFromMediaSource();
    }
    bool pump(const Function<bool(OmniMedia::DecodedOutput&)>& consume) {
        Ref protect { *this };
        if (m_detached || m_pumping) return true;
        SetForScope pumping { m_pumping, true };
        auto generation = m_playbackGeneration;
        unsigned outputs = 0, steps = 0;
        int targetWidth = 0, targetHeight = 0; // OMNI_VIDEO_TARGET_V1
        bool holePunch = false; // OMNI_HOLEPUNCH_V1
        unsigned budget = 4;    // OMNI_HOLEPUNCH_V3: outputs per pump (was a fixed 4)
        int waitMs = 0;         // OMNI_HOLEPUNCH_V3: total wait for decode progress (catching up)
        if (RefPtr parent = m_mediaSource.get()) {
            targetWidth = static_cast<OmniMSESource&>(*parent).videoTargetWidth();
            targetHeight = static_cast<OmniMSESource&>(*parent).videoTargetHeight();
            holePunch = static_cast<OmniMSESource&>(*parent).videoHolePunch();
            budget = static_cast<OmniMSESource&>(*parent).videoOutputBudget(); // OMNI_HOLEPUNCH_V3
            waitMs = static_cast<OmniMSESource&>(*parent).videoWaitMs();
        }
        for (auto& [id, owned] : m_tracks) {
            auto& track = *owned;
            if ((m_videoHeld && OmniMedia::isVideoCodec(track.info.codec)) || track.decoder.hardwareReleased()) continue; // OMNI_TAB_MEDIA_RELEASE_V1: not fed while given back
            track.decoder.setVideoTargetSize(targetWidth, targetHeight);
            track.decoder.setHolePunch(holePunch); // OMNI_HOLEPUNCH_V1
            while (outputs < budget && steps++ < 8 * budget) {
                if (track.output) {
                    // Own the offered frame across callbacks: a synchronous
                    // remove/flush may destroy track.output and even m_tracks.
                    auto offered = std::move(*track.output);
                    track.output.reset();
                    bool accepted = consume(offered);
                    // Check before touching track or the range-loop iterator.
                    // Interruption is not a decode failure; stale output dies
                    // locally and the next tick uses the new playback state.
                    if (m_detached || generation != m_playbackGeneration) return true;
                    if (!accepted) { track.output = std::move(offered); break; }
                    ++outputs;
                    if (outputs == budget) break;
                }
                OmniMedia::DecodedOutput output;
                auto received = track.decoder.receive(output);
                if (received == OmniMedia::PacketDecoder::Receive::Error) return fail("packet decode failed");
                if (received == OmniMedia::PacketDecoder::Receive::Output) { track.output = std::move(output); continue; }
                if (received == OmniMedia::PacketDecoder::Receive::End) {
                    // OMNI_WEBM_V1: the old configuration is drained: switch the decoder.
                    // OMNI_MSE_SWITCH_HANDOFF_V1: once the shell has shown the old stream's pictures.
                    if (track.reconfiguring && m_switchHandoff && !switchHandoffReady(track)) {
                        if (!switchPreopen(id, track, targetWidth, targetHeight, holePunch)) return true;
                        if (m_detached || generation != m_playbackGeneration) return true;
                        break;
                    }
                    if (track.reconfiguring) { if (!reconfigure(track)) return fail("decoder reconfiguration failed"); continue; }
                    track.ended = true; break;
                }
                if (!track.queue.empty()) {
                    // OMNI_WEBM_V1: a sample of another initialization segment (ABR switch, or a
                    // seek back into one): drain, then reconfigure on End above. Samples always
                    // switch at a keyframe (WebKit needs a random access point after an init).
                    const uint32_t wanted = track.queue.front().configuration;
                    if (wanted && wanted != track.active && wanted <= track.configs.size()) {
                        if (!track.reconfiguring) {
                            auto sent = track.decoder.drain();
                            if (sent == OmniMedia::PacketDecoder::Submit::Error) return fail("decoder drain for reconfiguration failed");
                            if (sent == OmniMedia::PacketDecoder::Submit::Accepted) { track.reconfiguring = true; track.pending = wanted; }
                        }
                        continue;
                    }
                    auto sent = track.decoder.submit(track.queue.front());
                    if (sent == OmniMedia::PacketDecoder::Submit::Error) return fail("packet submit failed");
                    if (sent == OmniMedia::PacketDecoder::Submit::NeedOutput) { // Retain exact packet.
                        if (waitMs > 0) { // OMNI_HOLEPUNCH_V3: catching up: let the decoder finish one
                            auto waitStart = MonotonicTime::now();
                            track.decoder.waitForProgress(std::min(waitMs, 4));
                            waitMs -= std::max(1, int((MonotonicTime::now() - waitStart).milliseconds()));
                            steps = std::min(steps, 4 * budget);   // waiting turns are not spins
                        }
                        continue;
                    }
                    m_queuedBytes -= track.queue.front().bytes.size() + track.queue.front().skipSamples.size();
                    --m_queuedCount; track.queue.pop_front();
                    provideMediaData(id); // Resume WebKit's bounded coded-frame queue.
                    if (m_detached || generation != m_playbackGeneration) return true;
                    continue;
                }
                provideMediaData(id);
                if (m_detached || generation != m_playbackGeneration) return true;
                if (!track.queue.empty()) continue;
                if (track.allEnqueued && !track.drainSent) {
                    auto sent = track.decoder.drain();
                    if (sent == OmniMedia::PacketDecoder::Submit::Error) return fail("decoder drain failed");
                    if (sent == OmniMedia::PacketDecoder::Submit::Accepted) track.drainSent = true;
                    continue;
                }
                break;
            }
        }
        return true;
    }
private:
    struct Track {
        OmniMedia::DemuxTrack info;
        OmniMedia::PacketDecoder decoder;
        std::deque<OmniMedia::DemuxPacket> queue;
        std::optional<OmniMedia::DecodedOutput> output;
        bool allEnqueued = false, drainSent = false, ended = false;
        // OMNI_WEBM_V1: every decoder configuration this track has had (id = index + 1). New
        // samples carry `latest`; the decoder runs `active`. When the next queued sample needs
        // another one, the decoder drains (old frames still come out) and is reconfigured.
        std::vector<OmniMedia::DemuxTrack> configs;
        uint32_t latest = 1, active = 1, pending = 0;
        bool reconfiguring = false;
        // OMNI_MSE_SWITCH_HANDOFF_V1: drained for a configuration change, waiting for the shell
        std::optional<MonotonicTime> switchWaitSince;
        double switchDrainedAt = 0, switchPoint = -1;   // the playhead then; the new configuration's first sample
        std::unique_ptr<OmniMedia::PacketDecoder> next;   // the new configuration's stream, opened ahead
        bool nextTried = false;
    };
    // OMNI_MSE_SWITCH_HANDOFF_V1: the decoder drained the old configuration. While the shell paces
    // this stream it still has to show the pictures decoded ahead (V5: seconds); configure() would
    // close the stream with them. Configure once they are shown (SwitchHandoff::ready).
    bool switchHandoffReady(Track& track) {
        const auto now = MonotonicTime::now();
        const double playhead = currentTime().toDouble();
        if (!track.switchWaitSince) {
            track.switchWaitSince = now; track.switchDrainedAt = playhead; track.switchPoint = -1;
            if (!track.queue.empty() && track.queue.front().timeBase.denominator > 0)   // the new configuration's first sample (a keyframe)
                track.switchPoint = double(track.queue.front().pts) * track.queue.front().timeBase.numerator / track.queue.front().timeBase.denominator;
        }
        const double switchPoint = track.switchPoint;
        const double waitedMs = (now - *track.switchWaitSince).milliseconds();
        const char* why = nullptr;
        const auto queue = track.decoder.shellQueue();
        bool ready = OmniMedia::SwitchHandoff::ready(queue, playhead, switchPoint, waitedMs, why);
        // OMNI_PERF_C_V8: with the new stream opened ahead (its swap is instant), the old one closes one
        // player tick (16 ms) before the switch point, not SwitchHandoff's 50 ms: closing it drops the
        // pictures the shell still has before the switch point (~3 at 60 fps, shown as a still frame).
        // Kill switch: /data/omni/switch-late-close-disabled.flag (host: OMNI_SWITCH_LATE_CLOSE=0).
        if (ready && track.next && why && !strcmp(why, "the playhead reached the switch point") && queue.waiting
            && switchPoint >= 0 && std::isfinite(playhead) && playhead < switchPoint - switchLateLead && waitedMs < OmniMedia::SwitchHandoff::maxWaitMs
            && switchLateClose())
            ready = false;
        // Another track of this buffer must not starve behind the waiting samples (one queue quota):
        // configure once WebKit is about to stop enqueueing (isReadyForMoreSamples).
        if (!ready && m_tracks.size() > 1 && (m_queuedCount + 8 >= maximumCount || m_queuedBytes + maxPacket() / 4 > maxQueued() - maxPacket())) { ready = true; why = "the buffer's sample queue is full"; }
        if (!waitedMs && !ready && m_switchLogs < 8) {   // the wait has seconds to go: the line costs nothing on screen
            ++m_switchLogs;
            fprintf(stderr, "OMNI MSE: quality switch: configuration %u drained at %.3f s, %.3f s before the switch point; configuration %u waits for the shell to show the %u pictures it still has (SWITCH_HANDOFF)\n",
                track.active, playhead, switchPoint - playhead, track.pending, queue.waiting);
            fflush(stderr);
        }
        if (!ready) return false;
        if (RefPtr parent = m_mediaSource.get()) {   // the player logs it once the new stream plays (no log line here: the new stream starts now)
            OmniMSESource::VideoSwitch info;
            info.from = track.active; info.to = track.pending;
            info.waitedMs = waitedMs; info.drainedAt = track.switchDrainedAt; info.playhead = playhead; info.switchPoint = switchPoint;
            info.why = why; info.waited = waitedMs > 0; info.preopened = !!track.next;
            static_cast<OmniMSESource&>(*parent).videoSwitched(info);
        }
        track.switchWaitSince.reset();
        return true;
    }
    static constexpr double switchLateLead = 0.016; // OMNI_PERF_C_V8
    static bool switchLateClose()
    {
        static const bool on = [] {
            if (const char* env = getenv("OMNI_SWITCH_LATE_CLOSE")) return env[0] != '0';
#ifdef __PROSPERO__
            return access("/data/omni/switch-late-close-disabled.flag", F_OK) != 0;
#else
            return true;
#endif
        }();
        return on;
    }
    // OMNI_MSE_SWITCH_HANDOFF_V1: while the shell shows the old stream's pictures (seconds), the new
    // configuration's stream opens next to it and gets its first sample (a keyframe): the decoder's
    // set-up (~250 ms on the console's service thread, the client waiting for it) and VP9's open at
    // its first keyframe happen now, not at the switch point. Hardware only, and only with a decode
    // channel free now; otherwise the stream is configured at the switch point, as before. False:
    // stop pumping (WebKit's callback detached the buffer or flushed it).
    bool switchPreopen(TrackID id, Track& track, int targetWidth, int targetHeight, bool holePunch) {
        if (track.next || track.nextTried || track.queue.empty() || !track.pending || track.pending > track.configs.size()) return true;
        if (!track.decoder.shellQueue().paced) return true;
        track.nextTried = true;
        auto generation = m_playbackGeneration;
        auto next = std::make_unique<OmniMedia::PacketDecoder>();
        next->setVideoPixelOrder(kN32_SkColorType == kBGRA_8888_SkColorType ? OmniMedia::PacketDecoder::PixelOrder::BGRA : OmniMedia::PacketDecoder::PixelOrder::RGBA);
        next->setVideoTargetSize(targetWidth, targetHeight);
        next->setHolePunch(holePunch);
        next->setHardwareNoWait(true);
        const bool opened = next->configure(track.configs[track.pending - 1]) && next->usingHardware();
        unsigned decoding = 0;
        while (opened && decoding < OmniMedia::SwitchHandoff::prerollSamples && !track.queue.empty() && track.queue.front().configuration == track.pending) {
            if (next->submit(track.queue.front()) != OmniMedia::PacketDecoder::Submit::Accepted || !next->usingHardware()) break;
            m_queuedBytes -= track.queue.front().bytes.size() + track.queue.front().skipSamples.size();
            --m_queuedCount; track.queue.pop_front();
            ++decoding;
        }
        const bool ok = decoding && next->usingHardware();
        if (m_switchLogs < 16) {
            ++m_switchLogs;
            fprintf(stderr, "OMNI MSE: quality switch: configuration %u %s, %u sample(s) decoding (SWITCH_HANDOFF)\n", track.pending,
                ok ? "opened ahead on the hardware" : opened ? "opened ahead, refused its first sample: it opens at the switch point" : "not opened ahead (no free decode channel, or software): it opens at the switch point", decoding);
            fflush(stderr);
        }
        if (decoding) track.next = std::move(next);   // samples went to it: it is the track's next decoder either way
        if (decoding) provideMediaData(id);
        return !m_detached && generation == m_playbackGeneration;
    }
    Buffer(OmniMSESource& source, uint32_t id, bool webm) : SourceBufferPrivate(source), m_namespace(id), m_webm(webm) { } // OMNI_WEBM_V1
    bool fail(const char* error) { if (RefPtr parent = m_mediaSource.get()) static_cast<OmniMSESource&>(*parent).failed(error); return false; }
    TrackID namespaced(int64_t id) const { return (uint64_t(m_namespace) << 32) | uint32_t(id); }
    Ref<MediaPromise> appendInternal(Ref<SharedBuffer>&& bytes) final {
        if (m_detached) return MediaPromise::createAndReject(PlatformMediaError::BufferRemoved);
        if (m_webm) return appendWebM(bytes.get()); // OMNI_WEBM_V1
        if (!m_parser.append(bytes->span())) { fail("fragment framing rejected"); return MediaPromise::createAndReject(PlatformMediaError::ParsingError); }
        OmniMedia::MP4SegmentBuffer::Segment segment;
        while (true) {
            auto result = m_parser.next(segment);
            if (result == OmniMedia::MP4SegmentBuffer::Result::NeedMore || result == OmniMedia::MP4SegmentBuffer::Result::End) break;
            if (result == OmniMedia::MP4SegmentBuffer::Result::Error) { fail("fragment framing error"); return MediaPromise::createAndReject(PlatformMediaError::ParsingError); }
            OmniMedia::MP4DemuxResult demux;
            if (segment.kind == OmniMedia::MP4SegmentBuffer::Segment::Kind::Initialization) {
                // Byte-identical init repeats are legal. Changed codec config
                // remains unsupported rather than reusing a stale decoder.
                if (!m_tracks.empty()) {
                    // OMNI_WEBM_V1: a changed initialization (ABR quality switch) becomes a new
                    // decoder configuration (switchConfiguration); kill switch restores the refusal.
                    if (segment.bytes != m_initialization) {
                        if (!OmniMedia::mseReinitEnabled()) return reject("initialization change unsupported");
                        if (!OmniMedia::inspectMP4Initialization(segment.bytes, demux)) return reject("initialization unsupported");
                        if (auto* why = switchConfiguration(demux.tracks)) return reject(why);
                        m_initialization = std::move(segment.bytes);
                    }
                    didReceiveInitializationSegment(initializationSegment());
                    continue;
                }
                if (!OmniMedia::inspectMP4Initialization(segment.bytes, demux) || demux.tracks.empty() || demux.tracks.size() > 2)
                    return reject("initialization unsupported");
                bool audio = false, video = false;
                for (auto& info : demux.tracks) {
                    if (info.id <= 0 || uint64_t(info.id) > UINT32_MAX) return reject("track id out of range");
                    bool isVideo = OmniMedia::isVideoCodec(info.codec); // OMNI_WEBM_V1
                    if ((isVideo && video) || (!isVideo && audio)) return reject("duplicate track type unsupported");
                    (isVideo ? video : audio) = true;
                    TrackID id = namespaced(info.id);
                    auto track = std::make_unique<Track>(); track->info = info;
                    track->configs = { info }; // OMNI_WEBM_V1
                    // v53: convert straight to the compositor's native channel order.
                    track->decoder.setVideoPixelOrder(kN32_SkColorType == kBGRA_8888_SkColorType
                        ? OmniMedia::PacketDecoder::PixelOrder::BGRA : OmniMedia::PacketDecoder::PixelOrder::RGBA);
                    if (!track->decoder.configure(info)) return reject("decoder configuration failed");
                    m_tracks.emplace(id, std::move(track));
                }
                m_initialization = std::move(segment.bytes);
                didReceiveInitializationSegment(initializationSegment());
            } else {
                if (!OmniMedia::demuxMP4Fragment(m_initialization, segment.bytes, demux)) return reject("fragment demux rejected");
                for (auto& packet : demux.packets) {
                    if (packet.trackId <= 0 || uint64_t(packet.trackId) > UINT32_MAX) return reject("packet track id out of range");
                    auto found = m_tracks.find(namespaced(packet.trackId));
                    if (found == m_tracks.end() || packet.bytes.size() + packet.skipSamples.size() > maxPacket()) return reject("packet unsupported or over quota"); // OMNI_CODEC_HEVC_V1: maxPacket()
                    auto& info = found->second->info;
                    packet.configuration = found->second->latest; // OMNI_WEBM_V1
                    auto sample = OmniMediaSample::create(std::move(packet), found->first, FloatSize(info.width, info.height));
                    if (!sample) return reject("sample timestamps rejected");
                    didReceiveSample(sample.releaseNonNull());
                }
            }
        }
        return MediaPromise::createAndResolve(); // Base waits for init/coded-frame callbacks before updateend.
    }
    Ref<MediaPromise> reject(const char* message) { fail(message); return MediaPromise::createAndReject(PlatformMediaError::ParsingError); }
    // OMNI_WEBM_V1: WebM byte stream (media/OmniWebMDemuxer.h). Same track setup, sample checks
    // and WebKit callbacks as the MP4 path; WebKit's SourceBufferPrivate applies timestampOffset,
    // appendWindow and sequence mode to the samples, as for MP4.
    Ref<MediaPromise> appendWebM(const SharedBuffer& bytes) {
        auto span = bytes.span();
        std::vector<OmniMedia::WebMEvent> events;
        bool parsed = m_webmParser.append(span.data(), span.size(), events);
        if (parsed) m_webmParser.endOfAppend(events);
        for (auto& event : events) {
            if (event.kind == OmniMedia::WebMEvent::Kind::Initialization) {
                auto& init = event.initialization;
                // A repeated initialization is legal; a changed one (ABR switch) becomes a new
                // decoder configuration, as for MP4.
                if (!m_tracks.empty()) {
                    if (!init.sameTracks(m_webmInitialization)) {
                        if (!OmniMedia::mseReinitEnabled()) return reject("initialization change unsupported");
                        if (auto* why = switchConfiguration(init.tracks)) return reject(why);
                        m_webmInitialization = std::move(init);
                    }
                    didReceiveInitializationSegment(initializationSegment());
                    continue;
                }
                if (init.tracks.empty() || init.tracks.size() > 2) return reject("initialization unsupported");
                bool audio = false, video = false;
                for (auto& info : init.tracks) {
                    if (info.id <= 0 || uint64_t(info.id) > UINT32_MAX) return reject("track id out of range");
                    bool isVideo = OmniMedia::isVideoCodec(info.codec);
                    if ((isVideo && video) || (!isVideo && audio)) return reject("duplicate track type unsupported");
                    (isVideo ? video : audio) = true;
                    auto track = std::make_unique<Track>();
                    track->info = info;
                    track->configs = { info };
                    track->decoder.setVideoPixelOrder(kN32_SkColorType == kBGRA_8888_SkColorType
                        ? OmniMedia::PacketDecoder::PixelOrder::BGRA : OmniMedia::PacketDecoder::PixelOrder::RGBA);
                    if (!track->decoder.configure(info)) {
                        fprintf(stderr, "OMNI MSE: WebM track %lld (%dx%d): %s\n", static_cast<long long>(info.id),
                            info.width, info.height, track->decoder.error().c_str());
                        fflush(stderr);
                        return reject("decoder configuration failed");
                    }
                    m_tracks.emplace(namespaced(info.id), std::move(track));
                }
                if (init.durationSeconds > 0 && std::isfinite(init.durationSeconds))
                    m_segmentDuration = MediaTime::createWithDouble(init.durationSeconds);
                m_webmInitialization = std::move(init);
                didReceiveInitializationSegment(initializationSegment());
                continue;
            }
            auto& packet = event.packet;
            if (packet.trackId <= 0 || uint64_t(packet.trackId) > UINT32_MAX) return reject("packet track id out of range");
            auto found = m_tracks.find(namespaced(packet.trackId));
            if (found == m_tracks.end() || packet.bytes.size() + packet.skipSamples.size() > maxPacket()) return reject("packet unsupported or over quota");
            auto& track = *found->second;
            packet.configuration = track.latest;
            auto sample = OmniMediaSample::create(std::move(packet), found->first, FloatSize(track.info.width, track.info.height));
            if (!sample) return reject("sample timestamps rejected");
            didReceiveSample(sample.releaseNonNull());
        }
        if (!parsed) {
            fprintf(stderr, "OMNI MSE: WebM parse error: %s\n", m_webmParser.error().c_str());
            fflush(stderr);
            return reject("WebM parse error");
        }
        return MediaPromise::createAndResolve(); // Base waits for init/coded-frame callbacks before updateend.
    }
    // OMNI_WEBM_V1: a changed initialization segment (ABR quality switch). The tracks must stay
    // the same (count, IDs, video/audio); a track whose decoder configuration changed gets a new
    // configuration id (or an earlier one again), and samples demuxed from now on carry it.
    // Everything is checked before anything changes. Returns the refusal text or nullptr.
    const char* switchConfiguration(const std::vector<OmniMedia::DemuxTrack>& next) {
        if (next.size() != m_tracks.size()) return "initialization change: track count differs";
        for (auto& info : next) {
            if (info.id <= 0 || uint64_t(info.id) > UINT32_MAX) return "track id out of range";
            auto found = m_tracks.find(namespaced(info.id));
            if (found == m_tracks.end()) return "initialization change: track ids differ";
            auto& track = *found->second;
            if (OmniMedia::isVideoCodec(track.info.codec) != OmniMedia::isVideoCodec(info.codec)) return "initialization change: track type differs";
            bool known = false;
            for (auto& c : track.configs) known = known || OmniMedia::sameDecoderConfiguration(c, info);
            if (known) continue;
            if (track.configs.size() >= maximumConfigurations) return "initialization change: too many configurations";
            std::string why;
            if (!OmniMedia::PacketDecoder::acceptable(info, why)) {
                fprintf(stderr, "OMNI MSE: changed initialization refused, track %lld (%dx%d): %s\n", static_cast<long long>(info.id), info.width, info.height, why.c_str());
                fflush(stderr);
                return "initialization change: decoder refuses the new configuration";
            }
        }
        for (auto& info : next) {
            auto& track = *m_tracks.find(namespaced(info.id))->second;
            uint32_t id = 0;
            for (size_t i = 0; i < track.configs.size() && !id; i++)
                if (OmniMedia::sameDecoderConfiguration(track.configs[i], info)) id = uint32_t(i + 1);
            if (!id) {
                track.configs.push_back(info);
                id = uint32_t(track.configs.size());
            }
            if (id != track.latest) {
                fprintf(stderr, "OMNI MSE: track %lld configuration %u -> %u (%dx%d)\n", static_cast<long long>(info.id), track.latest, id, info.width, info.height);
                fflush(stderr);
            }
            track.latest = id;
            track.info = info;
        }
        return nullptr;
    }
    // OMNI_WEBM_V1: after the drain for a configuration change (pump).
    bool reconfigure(Track& track) {
        track.reconfiguring = false;
        track.nextTried = false; // OMNI_MSE_SWITCH_HANDOFF_V1
        if (!track.pending || track.pending > track.configs.size()) return false;
        if (track.next) { // OMNI_MSE_SWITCH_HANDOFF_V1: opened ahead: the old stream closes here (and with it the shell's plane)
            track.decoder.swap(*track.next);
            track.decoder.setHardwareNoWait(false);
            track.next.reset();
        } else if (!track.decoder.configure(track.configs[track.pending - 1])) {
            fprintf(stderr, "OMNI MSE: reconfiguration to %u failed: %s\n", track.pending, track.decoder.error().c_str());
            fflush(stderr);
            return false;
        }
        track.active = track.pending;
        track.pending = 0;
        track.drainSent = track.ended = false;
        return true;
    }
    // OMNI_CODEC_HEVC_V1: an MP4 buffer with an HEVC track (4K keyframes) gets the WebM limits.
    bool largeVideo() const {
        if (m_webm) return true;
        for (auto& [id, track] : m_tracks)
            if (track->info.codec == OmniMedia::DemuxCodec::HEVC) return true;
        return false;
    }
    size_t maxPacket() const { return largeVideo() ? maximumPacketWebM : maximumPacket; }
    size_t maxQueued() const { return largeVideo() ? maximumQueuedWebM : maximumQueued; }
    InitializationSegment initializationSegment() const {
        InitializationSegment init;
        init.duration = m_segmentDuration; // OMNI_WEBM_V1: WebM Info/Duration when given, else +infinity
        for (auto& [id, track] : m_tracks) {
            bool video = OmniMedia::isVideoCodec(track->info.codec);
            RefPtr<MediaDescription> description = adoptRef(*new Description(track->info.codec));
            if (video) init.videoTracks.append({description, adoptRef(*new VideoTrack(id))});
            else init.audioTracks.append({description, adoptRef(*new AudioTrack(id))});
        }
        return init;
    }
    void resetParserStateInternal() final {
        if (m_webm) { m_webmParser.abort(); return; } // OMNI_WEBM_V1: keeps the initialization
        m_parser.reset();
        // abort() drops partial bytes, but a later media append need not repeat
        // the already accepted initialization segment. Prime framing only.
        if (!m_initialization.empty()) {
            OmniMedia::MP4SegmentBuffer::Segment ignored;
            if (!m_parser.append(m_initialization) || m_parser.next(ignored) != OmniMedia::MP4SegmentBuffer::Result::Ready)
                fail("parser reset failed");
        }
    }
    void processInitializationSegment(std::optional<InitializationSegment>&& init) final {
        // Upstream also sends nullopt for an aborted initialization and settles
        // its promise separately. It is not independently a fatal decode error.
        if (!init) return;
        if (RefPtr parent = m_mediaSource.get()) static_cast<OmniMSESource&>(*parent).changed();
    }
    bool isReadyForMoreSamples(TrackID id) final {
        auto found = m_tracks.find(id);
        return found != m_tracks.end() && !found->second->drainSent && m_queuedCount < maximumCount && m_queuedBytes <= maxQueued() - maxPacket(); // OMNI_WEBM_V1
    }
    void notifyClientWhenReadyForMoreSamples(TrackID) final { } // pump calls provideMediaData after each consumed packet.
    void enqueueSample(Ref<MediaSample>&& sample, TrackID id) final {
        auto found = m_tracks.find(id);
        auto* omni = OmniMediaSample::from(sample.get());
        if (found == m_tracks.end() || !omni) { fail("foreign sample"); return; }
        auto packet = omni->copyPacketForDecode();
        if (!packet) { fail("sample time conversion rejected"); return; }
        // OMNI_WEBM_V1: OmniMediaSample must carry DemuxPacket::configuration for reconfiguration.
        static bool loggedMissingConfiguration;
        if (!packet->configuration && found->second->configs.size() > 1 && !loggedMissingConfiguration) {
            loggedMissingConfiguration = true;
            fprintf(stderr, "OMNI MSE: sample without configuration id; decoder reconfiguration disabled\n");
        }
        size_t bytes = packet->bytes.size() + packet->skipSamples.size();
        if (bytes > maxPacket() || m_queuedBytes > maxQueued() - bytes || m_queuedCount >= maximumCount) { fail("encoded queue quota"); return; } // OMNI_WEBM_V1
        m_queuedBytes += bytes; ++m_queuedCount;
        // OMNI_PERF_C_V4: the video's frame rate (display lock), from what WebKit enqueues (decode order)
        if (OmniMedia::isVideoCodec(found->second->info.codec) && packet->timeBase.denominator > 0 && !packet->nonDisplaying)
            if (RefPtr parent = m_mediaSource.get()) {
                const double tick = double(packet->timeBase.numerator) / packet->timeBase.denominator;
                static_cast<OmniMSESource&>(*parent).videoSampleTime(double(packet->pts) * tick, tick);
            }
        found->second->queue.push_back(std::move(*packet));
        found->second->allEnqueued = false;
    }
    void allSamplesInTrackEnqueued(TrackID id) final { auto found = m_tracks.find(id); if (found != m_tracks.end()) found->second->allEnqueued = true; }
    void flush(TrackID id) final {
        auto found = m_tracks.find(id); if (found == m_tracks.end()) return;
        ++m_playbackGeneration;
        auto& track = *found->second;
        for (auto& packet : track.queue) { m_queuedBytes -= packet.bytes.size() + packet.skipSamples.size(); --m_queuedCount; }
        track.queue.clear(); track.output.reset(); track.decoder.flush();
        track.allEnqueued = track.drainSent = track.ended = false;
        track.reconfiguring = false; // OMNI_WEBM_V1: flushed; the next sample decides the configuration
        track.switchWaitSince.reset(); track.next.reset(); track.nextTried = false; // OMNI_MSE_SWITCH_HANDOFF_V1
        if (RefPtr parent = m_mediaSource.get())
            static_cast<OmniMSESource&>(*parent).presentationFlushed(!OmniMedia::isVideoCodec(track.info.codec)); // OMNI_WEBM_V1
    }
    uint32_t m_namespace;
    OmniMedia::MP4SegmentBuffer m_parser;
    bool m_webm = false; // OMNI_WEBM_V1
    OmniMedia::WebMParser m_webmParser;
    OmniMedia::WebMInitialization m_webmInitialization;
    MediaTime m_segmentDuration { MediaTime::positiveInfiniteTime() };
    std::vector<uint8_t> m_initialization;
    std::map<TrackID, std::unique_ptr<Track>> m_tracks;
    size_t m_queuedBytes = 0, m_queuedCount = 0;
    bool m_detached = false;
    bool m_pumping = false;
    uint64_t m_playbackGeneration = 0;
    const bool m_switchHandoff = OmniMedia::SwitchHandoff::enabled(); // OMNI_MSE_SWITCH_HANDOFF_V1
    bool m_videoHeld = false; // OMNI_TAB_MEDIA_RELEASE_V1: video tracks released, not fed until all are back
    unsigned m_switchLogs = 0;
};
}

Ref<OmniMSESource> OmniMSESource::create(MediaSourcePrivateClient& client, Function<RefPtr<MediaPlayerPrivateInterface>()>&& player, Function<void()>&& changed)
{ return adoptRef(*new OmniMSESource(client, std::move(player), std::move(changed))); }
OmniMSESource::OmniMSESource(MediaSourcePrivateClient& client, Function<RefPtr<MediaPlayerPrivateInterface>()>&& player, Function<void()>&& changed)
    : MediaSourcePrivate(client), m_player(std::move(player)), m_changed(std::move(changed)) { }
RefPtr<MediaPlayerPrivateInterface> OmniMSESource::player() const { return m_player ? m_player() : nullptr; }
void OmniMSESource::setPlayer(MediaPlayerPrivateInterface* value) {
    if (!value) {
        m_player = nullptr; m_changed = nullptr;
        for (auto& buffer : sourceBuffers()) buffer->removedFromMediaSource();
    }
}
void OmniMSESource::changed() {
    if (!m_changed || m_changeScheduled) return;
    m_changeScheduled = true;
    // Never reenter player cancellation while append/pump holds track references.
    RunLoop::mainSingleton().dispatch([weak = ThreadSafeWeakPtr { *this }] {
        if (RefPtr source = weak.get()) {
            source->m_changeScheduled = false;
            if (source->m_changed) source->m_changed();
        }
    });
}
void OmniMSESource::failed(const char* message) { if (m_error.empty()) m_error = message; changed(); }
void OmniMSESource::presentationFlushed(bool audio) {
    if (audio) ++m_audioPresentationGeneration;
    else ++m_videoPresentationGeneration;
    // changed() dispatches later, so SDL/player callbacks cannot reenter a
    // SourceBuffer flush while it holds references to track storage.
    changed();
}
MediaSourcePrivate::AddStatus OmniMSESource::addSourceBuffer(const ContentType& type, const MediaSourceConfiguration&, RefPtr<SourceBufferPrivate>& output) {
    // OMNI_MEDIACAPS_V1: same table as OmniMSEFactory::supportsTypeAndCodecs.
    if (omniMSETypeSupport(type) == OmniMedia::Caps::Support::No) return AddStatus::NotSupported;
    if (!player()) return AddStatus::InvalidState;
    uint32_t id;
    {
        Locker locker { m_lock };
        if (m_sourceBuffers.size() >= 2 || !m_nextBufferID) return AddStatus::ReachedIdLimit;
        id = m_nextBufferID++;
    }
    // OMNI_WEBM_V1: WebM byte stream for video/webm and audio/webm, fragmented MP4 otherwise.
    auto container = type.containerType();
    bool webm = equalLettersIgnoringASCIICase(container, "video/webm"_s) || equalLettersIgnoringASCIICase(container, "audio/webm"_s);
    Ref buffer = Buffer::create(*this, id, webm);
    output = buffer.copyRef();
    {
        Locker locker { m_lock };
        m_sourceBuffers.append(buffer.copyRef());
    }
    buffer->setMediaSourceDuration(duration());
    return AddStatus::Ok;
}
void OmniMSESource::notifyActiveSourceBuffersChanged() { changed(); }
void OmniMSESource::durationChanged(const MediaTime& time) { MediaSourcePrivate::durationChanged(time); changed(); }
void OmniMSESource::bufferedChanged(PlatformTimeRanges&& ranges) { MediaSourcePrivate::bufferedChanged(std::move(ranges)); changed(); }
void OmniMSESource::markEndOfStream(EndOfStreamStatus status) { MediaSourcePrivate::markEndOfStream(status); if (status != EndOfStreamStatus::NoError) failed("media source ended with error"); else changed(); }
void OmniMSESource::unmarkEndOfStream() {
    MediaSourcePrivate::unmarkEndOfStream();
    for (auto& buffer : sourceBuffers()) buffer->setMediaSourceEnded(false);
    // A drained codec cannot accept fresh packets. Reopen from the current
    // presentation point using WebKit's existing random-access sample map.
    flushPlayback();
    (void)reenqueueMediaForTime(currentTime());
    changed();
}
bool OmniMSESource::pump(const Function<bool(OmniMedia::DecodedOutput&)>& consume) {
    Ref protect { *this };
    if (!m_error.empty()) return false;
    for (auto& buffer : sourceBuffers()) {
        if (!m_activeSourceBuffers.contains(buffer.ptr())) continue;
        if (!static_cast<Buffer&>(buffer.get()).pump(consume)) return false;
    }
    return m_error.empty();
}
bool OmniMSESource::playbackDrained() const {
    if (!isEnded()) return false;
    if (m_activeSourceBuffers.isEmpty()) return false;
    for (auto& buffer : sourceBuffers()) {
        if (!m_activeSourceBuffers.contains(buffer.ptr())) continue;
        if (!static_cast<const Buffer&>(buffer.get()).drained()) return false;
    }
    return true;
}
void OmniMSESource::flushPlayback() { for (auto& buffer : sourceBuffers()) static_cast<Buffer&>(buffer.get()).flushPlayback(); }
void OmniMSESource::resyncVideo() { for (auto& buffer : sourceBuffers()) static_cast<Buffer&>(buffer.get()).resyncVideo(); } // OMNI_MSE_SWITCH_HANDOFF_V1
bool OmniMSESource::videoUsingHardware() { for (auto& buffer : sourceBuffers()) if (static_cast<Buffer&>(buffer.get()).videoUsingHardware()) return true; return false; } // OMNI_TAB_MEDIA_RELEASE_V1
bool OmniMSESource::releaseVideoHardware() { bool any = false; for (auto& buffer : sourceBuffers()) any = static_cast<Buffer&>(buffer.get()).releaseVideoHardware() || any; return any; } // OMNI_TAB_MEDIA_RELEASE_V1
bool OmniMSESource::reacquireVideoHardware(bool giveUp) { bool all = true; for (auto& buffer : sourceBuffers()) all = static_cast<Buffer&>(buffer.get()).reacquireVideoHardware(giveUp) && all; return all; } // OMNI_TAB_MEDIA_RELEASE_V1
void OmniMSESource::videoSwitched(const VideoSwitch& info) { m_videoSwitch = info; m_videoSwitch.count = ++m_videoSwitches; } // OMNI_MSE_SWITCH_HANDOFF_V1
}
#endif
