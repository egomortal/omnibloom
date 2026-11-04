// SPDX-License-Identifier: GPL-3.0-or-later
#include "OmniPacketDecoder.h"
#include "OmniHwClient.h"
#include <cstdio>
#include <algorithm>
#include <cstring>
#include <limits>
#include <cstdlib>  // OMNI_MSE_SWITCH_HANDOFF_V1: getenv
#include <unistd.h> // access
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavutil/pixdesc.h>
#include <libswscale/swscale.h>
#include <libswresample/swresample.h>
}
#ifndef AV_CODEC_FLAG_COPY_OPAQUE
#error "Omni packet decoder requires FFmpeg AV_CODEC_FLAG_COPY_OPAQUE"
#endif
namespace OmniMedia {
struct PacketDecoder::State {
    DemuxTrack track;
    AVCodecContext* codec = nullptr;
    AVFrame* frame = nullptr;
    SwsContext* scaler = nullptr;
    SwrContext* resampler = nullptr;
    AVChannelLayout layout {};
    int rate = 0, sampleFormat = -1;
    int64_t audioClock = 0;
    int64_t hiddenAudioRemaining = 0;
    bool clockValid = false, draining = false, codecEnded = false, ended = false;
    std::string failure;
    // Hardware path (UI-process decode service). Null = FFmpeg software.
    std::unique_ptr<Hw::Client> hw;
    // After a hardware failure the software decoder restarts at a keyframe.
    bool awaitKeyFrame = false;
    // OMNI_WEBM_V1: VP9 above maxPixels (or no FFmpeg vp9 decoder): no software decoder is
    // opened, nothing to fall back to.
    bool hardwareOnly = false;
    bool released = false; // OMNI_TAB_MEDIA_RELEASE_V1: the hardware stream was given back (releaseHardware)
    // OMNI_PACKETDECODER_COLOUR_V1: the conversion's colour, resolved exactly as Hw::Client does
    // (same inputs: avcC, or the first VP9 keyframe; same height default), so the software path
    // and the hardware path give the same pixels and a fallback does not change colour.
    uint32_t colour = 0;
    bool colourFromKeyFrame = false;   // VP9: not known before its first keyframe
    int scalerKey[7] = {};             // what `scaler` was made for (sizes, formats, colour)
    ~State() {
        sws_freeContext(scaler); swr_free(&resampler); av_channel_layout_uninit(&layout);
        av_frame_free(&frame); avcodec_free_context(&codec);
    }
    bool fail(const char* message) { failure = message; return false; }
    void clearResampler() {
        swr_free(&resampler); av_channel_layout_uninit(&layout);
        rate = 0; sampleFormat = -1; audioClock = 0; clockValid = false; hiddenAudioRemaining = 0;
    }
};
PacketDecoder::PacketDecoder() : state(std::make_unique<State>()) { }
// OMNI_WEBM_V1 ---------------------------------------------------------------------------
static AVCodecID omniCodecId(DemuxCodec codec)
{
    switch (codec) {
    case DemuxCodec::H264: return AV_CODEC_ID_H264;
    case DemuxCodec::AAC: return AV_CODEC_ID_AAC;
    case DemuxCodec::VP9: return AV_CODEC_ID_VP9;
    case DemuxCodec::Opus: return AV_CODEC_ID_OPUS;
    case DemuxCodec::Vorbis: return AV_CODEC_ID_VORBIS;
    case DemuxCodec::HEVC: return AV_CODEC_ID_HEVC; // OMNI_CODEC_HEVC_V1 (hardware only; never opened)
    }
    return AV_CODEC_ID_NONE;
}
// OMNI_PROGRESSIVE_HOLEPUNCH_V1: H.264 above 1920x1080 (to 3840x2160) on the hardware only, for the
// progressive file player. Set around its configure() call on the calling thread (no member: the
// class layout, used by every MSE file, stays as it is). Off everywhere else: MSE is unchanged.
static thread_local bool omniLargeH264Hardware = false;
void omniProgressiveLargeH264(bool on) { omniLargeH264Hardware = on; }
static bool omniLargeH264(const DemuxTrack& track)
{
    return omniLargeH264Hardware && track.codec == DemuxCodec::H264 && int64_t(track.width) * track.height > PacketDecoder::maxPixels;
}
bool PacketDecoder::acceptable(const DemuxTrack& track, std::string& why)
{
    auto no = [&](const char* text) { why = text; return false; };
    // VP9 (WebM) needs no CodecPrivate; every other codec does.
    if (track.timeBase.numerator <= 0 || track.timeBase.denominator <= 0
        || (track.extraData.empty() && track.codec != DemuxCodec::VP9) || track.extraData.size() > 65536)
        return no("Invalid track configuration");
    const bool video = isVideoCodec(track.codec);
    const int64_t pixels = int64_t(track.width) * track.height;
    // OMNI_CODEC_HEVC_V1: HEVC is hardware-only at every size.
    const bool hardwareOnly = (track.codec == DemuxCodec::VP9 && pixels > maxPixels) || track.codec == DemuxCodec::HEVC
        || omniLargeH264(track); // OMNI_PROGRESSIVE_HOLEPUNCH_V1
    if (video && (track.width <= 0 || track.height <= 0 || pixels > (hardwareOnly ? maxHardwarePixels : maxPixels)))
        return no("Video metadata exceeds limit");
    if (track.codec == DemuxCodec::HEVC && (track.width > 3840 || track.height > 2160 || !Hw::Client::serviceAvailable()))
        return no("HEVC needs hardware decoding (hw-decode.flag and the decode service)");
    if (hardwareOnly && (track.width > 3840 || track.height > 2160 || !Hw::Client::serviceAvailable()))
        return no("VP9 above 1920x1080 needs hardware decoding (hw-decode.flag and the decode service)");
    if (!video && (track.sampleRate < 8000 || track.sampleRate > 192000 || track.channels < 1 || track.channels > 8))
        return no("Audio metadata exceeds limit");
    if (!hardwareOnly && !avcodec_find_decoder(omniCodecId(track.codec))
        && !(track.codec == DemuxCodec::VP9 && Hw::Client::serviceAvailable()))
        return no("Packet decoder unavailable");
    return true;
}
PacketDecoder::~PacketDecoder() = default;
const std::string& PacketDecoder::error() const { return state->failure; }
// OMNI_AAC_FORCED_SBR_V1: hls.js (all but Firefox/Android user agents) writes every AAC-LC track's
// AudioSpecificConfig as explicit HE-AAC (object type 5) with the extension rate equal to the core
// rate. FFmpeg's decoder takes that literally and turns the LC stream into noise (measured:
// correlation 0.07 with the real track; 1.00 once rewritten). Rewrite exactly that shape to plain
// AAC-LC. Real HE-AAC (extension rate above the core rate) is left alone.
static bool omniAacUnforceSbr(std::vector<uint8_t>& asc)
{
    if (asc.size() < 4) return false;
    size_t bit = 0;
    auto take = [&](int n) { unsigned v = 0; for (int i = 0; i < n; ++i, ++bit) v = (v << 1) | ((asc[bit >> 3] >> (7 - (bit & 7))) & 1); return v; };
    const unsigned aot = take(5), rate = take(4);
    if (aot != 5 || rate == 15) return false;
    const unsigned channels = take(4), extRate = take(4);
    if (extRate == 15 || extRate != rate) return false;
    if (take(5) != 2) return false;   // the core must be AAC-LC
    const unsigned lc = (2u << 11) | (rate << 7) | (channels << 3);
    asc = { uint8_t(lc >> 8), uint8_t(lc & 0xff) };
    return true;
}
bool PacketDecoder::configure(const DemuxTrack& track) {
    state = std::make_unique<State>(); auto& s = *state;
    // OMNI_WEBM_V1: H.264 / AAC (MP4) and VP9 / Opus / Vorbis (WebM); limits in acceptable().
    if (std::string why; !acceptable(track, why)) { s.failure = why; return false; }
    bool video = isVideoCodec(track.codec);
    s.hardwareOnly = (track.codec == DemuxCodec::VP9 && int64_t(track.width) * track.height > maxPixels)
        || track.codec == DemuxCodec::HEVC // OMNI_CODEC_HEVC_V1
        || omniLargeH264(track); // OMNI_PROGRESSIVE_HOLEPUNCH_V1
    s.track = track;
    if (video) {   // OMNI_PACKETDECODER_COLOUR_V1
        Hw::NalConfig nal; std::string ignored;
        if (track.codec == DemuxCodec::H264) Hw::parseAvcC(track.extraData.data(), track.extraData.size(), nal, ignored);
        else if (track.codec == DemuxCodec::HEVC) Hw::parseHvcC(track.extraData.data(), track.extraData.size(), nal, ignored);
        s.colour = Hw::colourWord(nal.colour, track.height);
        s.colourFromKeyFrame = track.codec == DemuxCodec::VP9;
    }
    if (s.hardwareOnly) return configureHardware(video);
    auto* codec = avcodec_find_decoder(omniCodecId(track.codec));
    // A build without FFmpeg's vp9 decoder still plays VP9 on the hardware (no fallback then).
    if (!codec && track.codec == DemuxCodec::VP9) { s.hardwareOnly = true; return configureHardware(video); }
    if (!codec) return s.fail("Packet decoder unavailable");
    s.codec = avcodec_alloc_context3(codec); s.frame = av_frame_alloc();
    if (!s.codec || !s.frame) return s.fail("Packet decoder allocation failed");
    s.codec->pkt_timebase = {track.timeBase.numerator, track.timeBase.denominator};
    s.codec->thread_count = video ? 2 : 1;
    s.codec->flags |= AV_CODEC_FLAG_COPY_OPAQUE;
    s.codec->max_pixels = maxPixels; s.codec->max_samples = 131072;
    if (video) { s.codec->width = track.width; s.codec->height = track.height; }
    else { s.codec->sample_rate = track.sampleRate; av_channel_layout_default(&s.codec->ch_layout, track.channels); }
    std::vector<uint8_t> extraData = track.extraData;   // OMNI_AAC_FORCED_SBR_V1
    if (track.codec == DemuxCodec::AAC && omniAacUnforceSbr(extraData))
        fprintf(stderr, "OMNI DECODE: AAC config signals SBR at the core rate (hls.js style); decoding as AAC-LC\n");
    s.codec->extradata = static_cast<uint8_t*>(av_mallocz(extraData.size() + AV_INPUT_BUFFER_PADDING_SIZE));
    if (!s.codec->extradata) return s.fail("Codec configuration allocation failed");
    s.codec->extradata_size = int(extraData.size());
    if (!extraData.empty()) memcpy(s.codec->extradata, extraData.data(), extraData.size()); // OMNI_WEBM_V1: VP9 may have none
    if (avcodec_open2(s.codec, codec, nullptr) < 0) return s.fail("Packet decoder initialization failed");
    return configureHardware(video);
}
// OMNI_WEBM_V1: the hardware half of configure(), shared by the hardware-only VP9 path.
bool PacketDecoder::configureHardware(bool video) {
    auto& s = *state; const auto& track = s.track;
    // The software decoder stays open either way: it is the instant fallback.
    if (video && Hw::Client::serviceAvailable()) {
        s.hw = std::make_unique<Hw::Client>();
        s.hw->setTargetSize(targetWidth, targetHeight); // OMNI_VIDEO_TARGET_V1
        s.hw->setHolePunch(holePunch);                  // OMNI_HOLEPUNCH_V1
        s.hw->setConnectNoWait(hardwareNoWait);         // OMNI_MSE_SWITCH_HANDOFF_V1
        // OMNI_CODEC_HEVC_V1: three codecs.
        const Hw::Codec hwCodec = track.codec == DemuxCodec::VP9 ? Hw::Codec::VP9 : track.codec == DemuxCodec::HEVC ? Hw::Codec::HEVC : Hw::Codec::H264;
        if (s.hw->configure(hwCodec, track, pixelOrder == PixelOrder::BGRA)) {
            fprintf(stderr, "OMNI DECODE: hardware %s %dx%d\n", hwCodec == Hw::Codec::VP9 ? "VP9" : hwCodec == Hw::Codec::HEVC ? "HEVC" : "H.264", track.width, track.height);
        } else {
            fprintf(stderr, "OMNI DECODE: hardware unavailable (%s); using software\n", s.hw->error().c_str());
            s.hw.reset();
        }
    }
    if (s.hardwareOnly && !s.hw)   // OMNI_CODEC_HEVC_V1: VP9 above 1080p or HEVC
        return s.fail(track.codec == DemuxCodec::HEVC ? "HEVC: hardware decoder unavailable (no software route)" : "VP9: hardware decoder unavailable and no software route");
    return true;
}
void PacketDecoder::hwFallback() {
    auto& s = *state;
    fprintf(stderr, "OMNI DECODE: hardware failed (%s); switching to software at next keyframe\n",
            s.hw ? s.hw->error().c_str() : "?");
    s.hw.reset();
    // OMNI_WEBM_V1: above maxPixels (or without FFmpeg vp9) there is no software decoder.
    if (s.hardwareOnly || !s.codec) { s.fail("hardware decoding failed; no software decoder for this stream"); return; }
    avcodec_flush_buffers(s.codec); av_frame_unref(s.frame);
    s.draining = s.codecEnded = s.ended = false;
    s.awaitKeyFrame = true;
}
bool PacketDecoder::usingHardware() const { return state && state->hw; }
ShellQueue PacketDecoder::shellQueue() const { // OMNI_MSE_SWITCH_HANDOFF_V1
    ShellQueue q;
    const Hw::HoleLink* link = state && state->hw ? state->hw->holeLink() : nullptr;
    if (!link || !link->alive() || link->state() != 1 || link->pacing().state != 1 || !link->pacing().atMs) return q;
    q.paced = true;
    q.waiting = link->pacing().waiting;
    q.reportAgeMs = link->pacingReportAgeMs();
    return q;
}
void PacketDecoder::swap(PacketDecoder& other) { // OMNI_MSE_SWITCH_HANDOFF_V1
    std::swap(state, other.state);
    std::swap(pixelOrder, other.pixelOrder);
    std::swap(targetWidth, other.targetWidth); std::swap(targetHeight, other.targetHeight);
    std::swap(holePunch, other.holePunch);
    std::swap(hardwareNoWait, other.hardwareNoWait);
}
bool PacketDecoder::releaseHardware() { // OMNI_TAB_MEDIA_RELEASE_V1
    if (!state || !state->hw) return false;
    auto& s = *state;
    s.hw.reset();   // ~Client: the channel closes; the service deletes the decoder and frees its memory
    if (s.codec) { avcodec_flush_buffers(s.codec); av_frame_unref(s.frame); }
    s.draining = s.codecEnded = s.ended = false;
    s.awaitKeyFrame = false;
    s.released = true;
    return true;
}
bool PacketDecoder::hardwareReleased() const { return state && state->released; } // OMNI_TAB_MEDIA_RELEASE_V1
bool PacketDecoder::reacquireHardware() { // OMNI_TAB_MEDIA_RELEASE_V1
    if (!state || !state->released) return true;
    auto& s = *state;
    if (!Hw::Client::serviceAvailable()) return false;
    auto hw = std::make_unique<Hw::Client>();
    hw->setTargetSize(targetWidth, targetHeight);
    hw->setHolePunch(holePunch);
    hw->setConnectNoWait(true);   // a free channel now, or try again later (never the 2 s wait on this thread)
    const Hw::Codec hwCodec = s.track.codec == DemuxCodec::VP9 ? Hw::Codec::VP9 : s.track.codec == DemuxCodec::HEVC ? Hw::Codec::HEVC : Hw::Codec::H264;
    if (!hw->configure(hwCodec, s.track, pixelOrder == PixelOrder::BGRA)) return false;
    s.hw = std::move(hw);
    s.released = false;
    s.draining = s.codecEnded = s.ended = false;
    return true;
}
void PacketDecoder::abandonHardware() { // OMNI_TAB_MEDIA_RELEASE_V1
    if (!state || !state->released) return;
    auto& s = *state;
    s.released = false;
    if (s.hardwareOnly || !s.codec) { s.fail("hardware decoder not available again; no software decoder for this stream"); return; }
    avcodec_flush_buffers(s.codec); av_frame_unref(s.frame);
    s.draining = s.codecEnded = s.ended = false;
    s.awaitKeyFrame = true;
    fprintf(stderr, "OMNI DECODE: no decode channel came free; software decoder from the next keyframe\n");
}
bool SwitchHandoff::enabled() { // OMNI_MSE_SWITCH_HANDOFF_V1
    if (const char* env = getenv("OMNI_MSE_SWITCH_HANDOFF")) return env[0] != '0';
#ifdef __PROSPERO__
    return access("/data/omni/mse-switch-handoff-disabled.flag", F_OK) != 0;
#else
    return true;
#endif
}
void PacketDecoder::setVideoTargetSize(int width, int height) { // OMNI_VIDEO_TARGET_V1
    targetWidth = width; targetHeight = height;
    if (state && state->hw) state->hw->setTargetSize(width, height);
}
void PacketDecoder::waitForProgress(int ms) { // OMNI_HOLEPUNCH_V3
    if (state && state->hw) state->hw->waitForProgress(ms);
}
void PacketDecoder::setHolePunch(bool on) { // OMNI_HOLEPUNCH_V1
    holePunch = on;
    if (state && state->hw) state->hw->setHolePunch(on);
}
PacketDecoder::Submit PacketDecoder::submit(const DemuxPacket& input) {
    auto& s = *state;
    if (s.colourFromKeyFrame && input.keyFrame) {   // OMNI_PACKETDECODER_COLOUR_V1: as Hw::Client's first keyframe
        Hw::VideoColour vc;
        if (Hw::vp9KeyFrameColour(input.bytes.data(), input.bytes.size(), vc)) s.colour = Hw::colourWord(vc, s.track.height);
        s.colourFromKeyFrame = false;
    }
    if (s.hw) {
        auto r = s.hw->submit(input);
        if (r == Hw::Client::Submit::Accepted) return Submit::Accepted;
        if (r == Hw::Client::Submit::NeedOutput) return Submit::NeedOutput;
        hwFallback();
        if (s.hardwareOnly) return Submit::Error; // OMNI_WEBM_V1: hwFallback recorded why
    }
    if (s.awaitKeyFrame) {
        if (!input.keyFrame) return Submit::Accepted;   // undecodable without its references
        s.awaitKeyFrame = false;
    }
    auto fail = [&](const char* text) { s.fail(text); return Submit::Error; };
    if (!s.codec || !s.failure.empty() || s.draining) return fail("Decoder not accepting packets");
    if (input.trackId != s.track.id || input.timeBase.numerator <= 0
        || input.timeBase.denominator <= 0 || input.bytes.empty()
        || input.bytes.size() > maxPacketBytes || input.duration < 0
        || (!input.skipSamples.empty() && input.skipSamples.size() != 10)) return fail("Invalid packet metadata");
    // WebKit timestampOffset/sequence processing can return a different rational
    // scale. Keep those adjusted values, rounding to the nearest codec tick;
    // never restore the original demux timestamp or silently overflow.
    AVRational inputBase {input.timeBase.numerator, input.timeBase.denominator};
    auto rescale = [&](int64_t value, bool timestamp, int64_t& result) {
        if (timestamp && value == AV_NOPTS_VALUE) { result = AV_NOPTS_VALUE; return true; }
        result = av_rescale_q_rnd(value, inputBase, s.codec->pkt_timebase, AV_ROUND_NEAR_INF);
        return result != INT64_MIN && result != INT64_MAX;
    };
    int64_t pts, dts, duration;
    if (!rescale(input.pts, true, pts) || !rescale(input.dts, true, dts)
        || !rescale(input.duration, false, duration) || (input.duration > 0 && duration <= 0))
        return fail("Packet timestamp cannot fit codec timebase");
    AVPacket* packet = av_packet_alloc();
    if (!packet) return fail("Packet allocation failed");
    if (av_new_packet(packet, int(input.bytes.size())) < 0) { av_packet_free(&packet); return fail("Packet data allocation failed"); }
    memcpy(packet->data, input.bytes.data(), input.bytes.size());
    packet->opaque_ref = av_buffer_alloc(2);
    if (!packet->opaque_ref) { av_packet_free(&packet); return fail("Packet provenance allocation failed"); }
    packet->opaque_ref->data[0] = 0x4f;
    packet->opaque_ref->data[1] = input.nonDisplaying ? 1 : 0;
    packet->pts = pts; packet->dts = dts; packet->duration = duration;
    packet->time_base = s.codec->pkt_timebase;
    if (input.keyFrame) packet->flags |= AV_PKT_FLAG_KEY;
    if (!input.skipSamples.empty()) {
        auto* skip = av_packet_new_side_data(packet, AV_PKT_DATA_SKIP_SAMPLES, 10);
        if (!skip) { av_packet_free(&packet); return fail("Packet side data allocation failed"); }
        memcpy(skip, input.skipSamples.data(), 10);
    }
    int result = avcodec_send_packet(s.codec, packet); av_packet_free(&packet);
    if (result == AVERROR(EAGAIN)) return Submit::NeedOutput;
    if (result < 0) return fail("Packet decode submission failed");
    return Submit::Accepted;
}
PacketDecoder::Submit PacketDecoder::drain() {
    auto& s = *state;
    if (s.hw) {
        auto r = s.hw->drain();
        if (r == Hw::Client::Submit::Accepted) return Submit::Accepted;
        if (r == Hw::Client::Submit::NeedOutput) return Submit::NeedOutput;
        hwFallback();
    }
    if (!s.codec || !s.failure.empty()) return Submit::Error;
    if (s.draining) return Submit::Accepted;
    int rc = avcodec_send_packet(s.codec, nullptr);
    if (rc == AVERROR(EAGAIN)) return Submit::NeedOutput;
    if (rc < 0 && rc != AVERROR_EOF) { s.fail("Packet decoder drain failed"); return Submit::Error; }
    s.draining = true; return Submit::Accepted;
}
PacketDecoder::Receive PacketDecoder::receive(DecodedOutput& out) {
    out = {}; auto& s = *state;
    if (s.hw) {
        auto r = s.hw->receive(out);
        if (r == Hw::Client::Receive::Output) return Receive::Output;
        if (r == Hw::Client::Receive::NeedInput) return Receive::NeedInput;
        if (r == Hw::Client::Receive::End) return Receive::End;
        out = {};
        hwFallback();
        if (s.hardwareOnly) return Receive::Error; // OMNI_WEBM_V1
        return Receive::NeedInput;
    }
    auto fail = [&](const char* text) { s.fail(text); av_frame_unref(s.frame); out = {}; return Receive::Error; };
    if (!s.codec || !s.failure.empty()) return Receive::Error;
    if (s.ended) return Receive::End;
    // Some input frames can be completely removed by priming/trimming or kept
    // in the resampler. Bound these iterations without inventing output.
    for (int budget = 0; budget < 256; ++budget) {
        int rc = s.codecEnded ? AVERROR_EOF : avcodec_receive_frame(s.codec, s.frame);
        if (rc == AVERROR(EAGAIN)) return Receive::NeedInput;
        if (rc < 0 && rc != AVERROR_EOF) return fail("Packet frame decode failed");
        bool tail = rc == AVERROR_EOF;
        s.codecEnded = tail;
        bool hidden = false;
        if (!tail) {
            auto* opaque = s.frame->opaque_ref;
            if (!opaque || opaque->size != 2 || opaque->data[0] != 0x4f || opaque->data[1] > 1)
                return fail("Decoder did not preserve packet provenance");
            hidden = opaque->data[1];
        }
        if (isVideoCodec(s.track.codec)) { // OMNI_WEBM_V1: H.264 or VP9
            if (tail) { s.ended = true; return Receive::End; }
            int w = s.frame->width, h = s.frame->height;
            if (w <= 0 || h <= 0 || int64_t(w) * h > maxPixels) return fail("Decoded video exceeds limit");
            bool bgra = pixelOrder == PixelOrder::BGRA;
            // OMNI_VIDEO_TARGET_V1: convert and scale to the shown size in one pass.
            int ow = w, oh = h;
            videoOutputSize(w, h, targetWidth, targetHeight, ow, oh);
            // OMNI_PACKETDECODER_COLOUR_V1: the stream's matrix and range (swscale's default is
            // BT.601 limited), set once per context, as the hardware path does; the deprecated
            // full-range YUVJ formats are taken as their YUV layouts (the range is set
            // explicitly). Rows of whole 16-pixel groups: swscale's unscaled 4:2:0 -> RGB path
            // leaves the last width % 8 pixels of a row unwritten at a stride of exactly
            // width * 4; the rows are packed again afterwards.
            int format = s.frame->format;
            if (format == AV_PIX_FMT_YUVJ420P) format = AV_PIX_FMT_YUV420P;
            else if (format == AV_PIX_FMT_YUVJ422P) format = AV_PIX_FMT_YUV422P;
            else if (format == AV_PIX_FMT_YUVJ444P) format = AV_PIX_FMT_YUV444P;
            const int dstFormat = bgra ? AV_PIX_FMT_BGRA : AV_PIX_FMT_RGBA;
            const int key[7] = { w, h, format, ow, oh, dstFormat, int(s.colour) };
            if (!s.scaler || memcmp(key, s.scalerKey, sizeof key)) {
                sws_freeContext(s.scaler);
                s.scaler = sws_getContext(w, h, AVPixelFormat(format), ow, oh, AVPixelFormat(dstFormat), SWS_BILINEAR, nullptr, nullptr, nullptr);
                if (!s.scaler) { memset(s.scalerKey, 0, sizeof s.scalerKey); return fail("Video converter allocation failed"); }
                sws_setColorspaceDetails(s.scaler, sws_getCoefficients(Hw::colourMatrix(s.colour, s.track.height)), Hw::colourFullRange(s.colour),
                    sws_getCoefficients(SWS_CS_DEFAULT), 1, 0, 1 << 16, 1 << 16);
                memcpy(s.scalerKey, key, sizeof key);
            }
            const size_t row = size_t(ow) * 4, stride = (size_t(ow) + 15) / 16 * 16 * 4;
            out.width=ow; out.height=oh; out.sourceWidth=w; out.sourceHeight=h; out.bgra=bgra; out.rgba.resize(stride*size_t(oh));
            uint8_t* planes[] = {out.rgba.data(),nullptr,nullptr,nullptr}; int strides[] = {int(stride),0,0,0};
            if (sws_scale(s.scaler,s.frame->data,s.frame->linesize,0,h,planes,strides) != oh) return fail("Video conversion failed");
            if (stride != row) {
                for (int r = 1; r < oh; r++) memmove(out.rgba.data() + size_t(r) * row, out.rgba.data() + size_t(r) * stride, row);
                out.rgba.resize(row * size_t(oh));
            }
            const auto* pixelFormat = av_pix_fmt_desc_get(AVPixelFormat(s.frame->format));
            out.opaque = pixelFormat && !(pixelFormat->flags & AV_PIX_FMT_FLAG_ALPHA);
            out.timeBase=s.track.timeBase; out.timestamp=s.frame->best_effort_timestamp;
            out.hasTimestamp=out.timestamp != AV_NOPTS_VALUE;
            out.nonDisplaying=hidden;
            av_frame_unref(s.frame); return Receive::Output;
        }
        if (tail && !s.resampler) { s.ended=true; return Receive::End; }
        if (!tail) {
            auto* f=s.frame;
            if (f->sample_rate<8000 || f->sample_rate>192000 || f->ch_layout.nb_channels<1
                || f->ch_layout.nb_channels>8 || f->nb_samples<=0 || f->nb_samples>16384)
                return fail("Decoded audio exceeds limit");
            if (!s.resampler) {
                s.rate=f->sample_rate; s.sampleFormat=f->format;
                AVChannelLayout stereo=AV_CHANNEL_LAYOUT_STEREO;
                if (av_channel_layout_copy(&s.layout,&f->ch_layout)<0
                    || swr_alloc_set_opts2(&s.resampler,&stereo,AV_SAMPLE_FMT_S16,48000,&f->ch_layout,
                        AVSampleFormat(f->format),f->sample_rate,0,nullptr)<0 || swr_init(s.resampler)<0)
                    return fail("Packet audio resampler failed");
            } else if (s.rate!=f->sample_rate || s.sampleFormat!=f->format || av_channel_layout_compare(&s.layout,&f->ch_layout))
                return fail("Audio format changed; reconfiguration required");
            if (f->best_effort_timestamp != AV_NOPTS_VALUE) {
                int64_t stamp=av_rescale_q(f->best_effort_timestamp,s.codec->pkt_timebase,AVRational{1,48000});
                int64_t delay=av_rescale_rnd(swr_get_delay(s.resampler,s.rate),48000,s.rate,AV_ROUND_NEAR_INF);
                if (stamp==INT64_MIN || stamp==INT64_MAX || delay<0 || stamp<INT64_MIN+delay)
                    return fail("Audio timestamp overflow");
                s.audioClock=stamp-delay; s.clockValid=true;
            }
        }
        int capacity=swr_get_out_samples(s.resampler,tail?0:s.frame->nb_samples);
        if (capacity<0 || capacity>maxAudioFrames) return fail("PCM chunk exceeds limit");
        // swr's upper output bound includes its buffered samples. A chunk that
        // might contain any hidden input is wholly hidden, including the drain
        // tail. Retain the unused bound across later frames, rather than losing
        // provenance when a short/trimmed frame spans several conversions.
        if (hidden) s.hiddenAudioRemaining = std::max(s.hiddenAudioRemaining, int64_t(capacity));
        bool hiddenOutput = hidden || s.hiddenAudioRemaining > 0;
        out.kind=DecodedOutput::Kind::Audio; out.pcm.resize(size_t(capacity)*2);
        uint8_t* planes[]={reinterpret_cast<uint8_t*>(out.pcm.data())};
        int count=swr_convert(s.resampler,planes,capacity,tail?nullptr:const_cast<const uint8_t**>(s.frame->extended_data),tail?0:s.frame->nb_samples);
        if (!tail) av_frame_unref(s.frame);
        if (count<0) return fail("PCM conversion failed");
        out.pcm.resize(size_t(count)*2); out.timestamp=s.audioClock; out.timeBase={1,48000}; out.hasTimestamp=s.clockValid;
        out.nonDisplaying=hiddenOutput;
        s.hiddenAudioRemaining=std::max<int64_t>(0,s.hiddenAudioRemaining-count);
        if (s.audioClock>INT64_MAX-count) return fail("PCM clock overflow");
        s.audioClock+=count;
        if (count) return Receive::Output;
        if (tail) { s.ended=true; out={}; return Receive::End; }
    }
    return Receive::NeedInput;
}
void PacketDecoder::flush() {
    auto& s=*state;
    s.awaitKeyFrame = false;
    if (s.hw) { s.hw->flush(); if (!s.hw->error().empty()) hwFallback(); }
    if (!s.codec) return;
    avcodec_flush_buffers(s.codec); av_frame_unref(s.frame); s.clearResampler();
    s.draining=s.codecEnded=s.ended=false;
    // Fatal malformed-data/configuration errors require configure(), not flush.
}
}
