// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <string>
#include <unistd.h>
#include <vector>
namespace OmniMedia {
// OMNI_CODEC_HEVC_V1: HEVC in MP4 (hardware decode only). Kill switch /data/omni/hevc-disabled.flag:
// the demuxer refuses HEVC tracks and the media table stops offering hvc1/hev1.
// Host tests: OMNI_HEVC=0/1 (default on).
inline bool hevcEnabled()
{
    if (const char* env = getenv("OMNI_HEVC")) return env[0] == '1';
#ifdef __PROSPERO__
    return access("/data/omni/hevc-disabled.flag", F_OK) != 0;
#else
    return true;
#endif
}
struct DemuxTimeBase { int numerator=0, denominator=0; };
// OMNI_WEBM_V1: VP9 / Opus / Vorbis come from OmniWebMDemuxer (MSE WebM byte streams).
// OMNI_CODEC_HEVC_V1: HEVC appended last (existing values unchanged).
enum class DemuxCodec { H264, AAC, VP9, Opus, Vorbis, HEVC };
inline bool isVideoCodec(DemuxCodec codec) { return codec == DemuxCodec::H264 || codec == DemuxCodec::VP9 || codec == DemuxCodec::HEVC; }
enum class DemuxDurationSource { FFmpegPacket, AudioCodecSamples, NextTrackDTS };
struct DemuxTrack {
    int64_t id=0;
    DemuxCodec codec=DemuxCodec::H264;
    DemuxTimeBase timeBase;
    int width=0,height=0,sampleRate=0,channels=0;
    std::vector<uint8_t> extraData;
};
// OMNI_WEBM_V1: same decoder configuration (a repeated or switched-back initialization).
inline bool sameDecoderConfiguration(const DemuxTrack& a, const DemuxTrack& b)
{
    return a.id == b.id && a.codec == b.codec && a.timeBase.numerator == b.timeBase.numerator
        && a.timeBase.denominator == b.timeBase.denominator && a.width == b.width && a.height == b.height
        && a.sampleRate == b.sampleRate && a.channels == b.channels && a.extraData == b.extraData;
}
struct DemuxPacket {
    int64_t trackId=0,pts=0,dts=0,duration=0;
    DemuxTimeBase timeBase;
    bool keyFrame=false;
    // Decode dependency whose output must not be presented (MSE preroll).
    bool nonDisplaying=false;
    bool durationFromNextDTS=false;
    DemuxDurationSource durationSource=DemuxDurationSource::FFmpegPacket;
    // FFmpeg AV_PKT_DATA_SKIP_SAMPLES bytes, retained for AAC encoder priming.
    std::vector<uint8_t> skipSamples;
    std::vector<uint8_t> bytes;
    // OMNI_WEBM_V1: the SourceBuffer initialization (configuration) this sample belongs to,
    // 1, 2, ... (0 = not set). OmniMSESource reconfigures the decoder when it changes.
    uint32_t configuration=0;
};
struct MP4DemuxLimits {
    // OMNI_WEBM_V1 rev3: 32 MiB (SourceBuffer quota): 10 s 1080p HLS fragments are 11-13 MB.
    size_t inputBytes=32*1024*1024,outputBytes=32*1024*1024,extraDataBytes=64*1024;
    size_t packets=8192;
};
struct MP4DemuxResult {
    std::vector<DemuxTrack> tracks;
    std::vector<DemuxPacket> packets;
    std::string error;
};
// Finite init + exactly one moof/mdat fragment. No fetching, decoding or MSE state.
// On failure output is empty apart from error. Limits may only lower hard bounds.
bool demuxMP4Fragment(const std::vector<uint8_t>& init,const std::vector<uint8_t>& fragment,
                      MP4DemuxResult&,MP4DemuxLimits = {});
// Header metadata only: no sample probing and no media fragment required.
bool inspectMP4Initialization(const std::vector<uint8_t>& init,MP4DemuxResult&,MP4DemuxLimits = {});
}
