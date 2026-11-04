// WebM byte-stream parser for Omni's MediaSource path (OMNI_WEBM_V1).
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Implements the subset of Matroska that the W3C "WebM Byte Stream Format" for MSE uses:
//   initialization segment = EBML header + Segment header + Info + Tracks (+ SeekHead/Void)
//   media segment          = one Cluster (known or unknown size, as YouTube live sends)
// Codecs: V_VP9, A_OPUS, A_VORBIS. Blocks: SimpleBlock and BlockGroup/Block (+BlockDuration,
// ReferenceBlock, DiscardPadding); Xiph, EBML and fixed-size lacing for audio.
// Input may be split at any byte. No I/O, no decoding; every length is bounds-checked.
//
// Output uses the MP4 demuxer's structures (DemuxTrack / DemuxPacket), so OmniMSESource
// feeds both formats through the same OmniMediaSample / PacketDecoder path.
// Time bases (numerator always 1):
//   video  {1, 1e9 / TimecodeScale} (1/1000 for the usual 1 ms scale), else {1, 1e9}
//   Opus   {1, 48000}; pts = block time - CodecDelay, as FFmpeg's matroska demuxer does.
//          The decoder itself drops OpusHead pre-skip (FFmpeg avctx->delay), so no leading
//          skip side data is attached; DiscardPadding becomes trailing SKIP_SAMPLES.
//   Vorbis {1, SamplingFrequency}
// Durations: video = next frame's time minus this one's (WebKit's Cocoa WebM parser does the
// same), so the newest frame of each track is held until the next frame or the cluster end;
// at the cluster end it gets DefaultDuration, else the previous duration, else 1/30 s.
// Unknown-size clusters have no visible end: endOfAppend() releases held frames when an
// append stops on an element boundary inside one (WebKit's Cocoa parser does so after every
// append).
// BlockDuration, when present, is used directly. Audio durations come from the packets
// (Opus TOC, RFC 6716 3.1; Vorbis via libavcodec's public av_vorbis_parse_*).
// Not supported (refused with an error): ContentEncoding (encryption / compression),
// laced video, EncryptedBlock, more than one video or audio track, other A/V codecs.
// Revision: OMNI_WEBM_V1 rev2 (opt-in flag, changed initialization segments).
#pragma once
#include "OmniMP4Demuxer.h"
#include "OmniMediaCaps.h"
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <memory>
#include <string>
#include <unistd.h>
#include <vector>

namespace OmniMedia {

// OMNI_CODEC_VP9_DEFAULT_V1: WebM (VP9 / Opus / Vorbis) is offered to pages (isTypeSupported,
// decodingInfo, addSourceBuffer, getSupportedTypes) by default. Kill switch, checked on every
// query: /data/omni/webm-disabled.flag -> Omni answers exactly as before OMNI_WEBM_V1 (MP4 only).
// The old opt-in /data/omni/webm-mse.flag is not read any more. Host tests: OMNI_WEBM_MSE=0/1.
inline bool webmMseEnabled()
{
    if (const char* env = getenv("OMNI_WEBM_MSE")) return env[0] == '1';
#ifdef __PROSPERO__
    return access("/data/omni/webm-disabled.flag", F_OK) != 0;
#else
    return true;
#endif
}
// OMNI_CODEC_VP9_DEFAULT_V1: 10-bit VP9 (profile 2) above 1920x1080 on the hardware. Kill switch
// /data/omni/vp9-10bit-4k-disabled.flag (read once per process). Host tests: OMNI_VP9_10BIT_4K=0/1.
inline bool vp9TenBitHighEnabled()
{
    if (const char* env = getenv("OMNI_VP9_10BIT_4K")) return env[0] == '1';
#ifdef __PROSPERO__
    return access("/data/omni/vp9-10bit-4k-disabled.flag", F_OK) != 0;
#else
    return true;
#endif
}
// Changed initialization segments (ABR quality switches) are followed by a decoder
// reconfiguration (OmniMSESource). Kill switch: /data/omni/mse-reinit-disabled.flag restores
// the old refusal. Host tests: OMNI_MSE_REINIT=0.
inline bool mseReinitEnabled()
{
    if (const char* env = getenv("OMNI_MSE_REINIT")) return env[0] != '0';
#ifdef __PROSPERO__
    return access("/data/omni/mse-reinit-disabled.flag", F_OK) != 0;
#else
    return true;
#endif
}

struct WebMTrackInfo {
    uint64_t number = 0;
    std::string codecId;
    uint64_t defaultDurationNs = 0, codecDelayNs = 0, seekPreRollNs = 0;
};

struct WebMInitialization {
    std::vector<DemuxTrack> tracks;     // audio/video tracks in TrackEntry order
    std::vector<WebMTrackInfo> info;    // same order
    uint64_t timecodeScale = 1000000;   // ns per cluster/block tick
    double durationSeconds = 0;         // Info/Duration, 0 when absent
    // A repeated initialization segment with the same decoder configuration (codec, track
    // number, size, rate, channels, CodecPrivate, time base). Duration/SeekHead may differ.
    bool sameTracks(const WebMInitialization&) const;
};

struct WebMEvent {
    enum class Kind { Initialization, Packet };
    Kind kind = Kind::Packet;
    WebMInitialization initialization;  // Kind::Initialization
    DemuxPacket packet;                 // Kind::Packet
};

class WebMParser {
public:
    static constexpr size_t maxHeaderElementBytes = 1024 * 1024;     // EBML header, Info, Tracks
    static constexpr size_t maxBlockElementBytes = 8 * 1024 * 1024;  // SimpleBlock, BlockGroup
    static constexpr size_t maxCodecPrivateBytes = 64 * 1024;        // as MP4DemuxLimits
    static constexpr size_t maxFramesPerBlock = 256;

    WebMParser();
    ~WebMParser();
    WebMParser(const WebMParser&) = delete;
    WebMParser& operator=(const WebMParser&) = delete;

    // Parses as far as the bytes allow; complete results are appended to `events` in stream
    // order. False on malformed or unsupported input (error()); events emitted before the
    // error stay valid. After an error every append fails until abort() or clear().
    bool append(const uint8_t* data, size_t size, std::vector<WebMEvent>& events);
    // End of one SourceBuffer.appendBuffer(). Inside an unknown-size cluster, with no partial
    // element pending, the append most likely ended a media segment: release the held
    // frames now (estimated durations) instead of waiting for the next cluster, so buffered
    // ranges are complete at updateend and the final frame of a stream is not lost.
    void endOfAppend(std::vector<WebMEvent>& events);
    // SourceBuffer.abort() / resetParserState: drop partial input and held frames; the last
    // initialization stays, so the next append may start with a Cluster.
    void abort();
    // Forget everything (SourceBuffer removed).
    void clear();
    bool initialized() const;
    const std::string& error() const;
    size_t bufferedBytes() const;   // unparsed input held (at most one incomplete element)

private:
    struct State;
    std::unique_ptr<State> s;
};

// Samples (at 48 kHz) in one Opus packet, from its TOC byte(s); -1 if malformed.
int opusPacketSamples(const uint8_t* data, size_t size);

// FFmpeg software decoders present in this build (avcodec_find_decoder), probed once.
Caps::Decoders webmDecoders();

}
