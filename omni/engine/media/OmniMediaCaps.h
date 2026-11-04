// What Omni's media engines really play, as one table (OMNI_MEDIACAPS_V1).
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Used by three callers so their answers cannot drift apart:
//   * MediaSource.isTypeSupported / SourceBuffer creation (OmniMSEFactory, OmniMSESource),
//   * navigator.mediaCapabilities.decodingInfo (the factory OmniMSEPlayer.cpp installs).
// HTMLMediaElement.canPlayType stays with the file player's own supportsType; decodingInfo
// for type 'file' requires that answer too and then applies the file limits below.
//
// Every limit names the code that enforces it. Raise them together.
// Pure C++17 with no WebKit types, so the host unit test compiles it directly.
#pragma once
#include <cstdint>
#include <cstdlib>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace OmniMedia::Caps {

// MSE (OmniMP4Demuxer "Video dimensions unsupported", PacketDecoder::maxPixels): 1920x1080
// pixels. The hardware decoder itself goes to 3840x2160 (OmniHwClient), the demuxer does not.
constexpr int64_t kMseMaxPixels = 1920 * 1080;
// File player (VideoDecoder::maxPixels, software FFmpeg, 2 threads).
constexpr int64_t kFileMaxPixels = 1920 * 1080;
constexpr uint32_t kMaxSide = 4096;
// Smooth playback. Hardware: measured >2000 fps decode-only at 1080p; the frame budget is the
// present path (hole-punch convert ~6 ms per 1080p frame on v70). Software: conservative.
constexpr int64_t kHardwareSmoothPixels = 1920 * 1080;
constexpr double kHardwareSmoothFramerate = 60.0;
constexpr int64_t kSoftwareSmoothPixels = 1280 * 720;
constexpr double kSoftwareSmoothFramerate = 30.0;
// Audio decoders (PacketDecoder / AudioDecoder / VideoDecoder): 1..8 channels, 8..192 kHz,
// always mixed down to 48 kHz stereo; no spatial rendering.
constexpr double kMaxAudioChannels = 8;
constexpr uint32_t kMinSampleRate = 8000, kMaxSampleRate = 192000;

enum class Kind : uint8_t { File, MediaSource, Other };
enum class Support : uint8_t { No, Maybe, Yes }; // mirrors MediaPlayer::SupportsType

inline char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c - 'A' + 'a') : c; }
inline std::string lowered(std::string_view s)
{
    std::string out(s);
    for (auto& c : out) c = lower(c);
    return out;
}
inline bool hexDigit(char c, int& v)
{
    c = lower(c);
    if (c >= '0' && c <= '9') { v = c - '0'; return true; }
    if (c >= 'a' && c <= 'f') { v = c - 'a' + 10; return true; }
    return false;
}
inline bool decimal(std::string_view s, int& v)
{
    if (s.empty() || s.size() > 3) return false;
    v = 0;
    for (char c : s) {
        if (c < '0' || c > '9') return false;
        v = v * 10 + (c - '0');
    }
    return true;
}

// H.264 as "avc1.PPCCLL" (RFC 6381) or the legacy "avc1.PROFILE.LEVEL" (decimal).
// Accepted: 8-bit 4:2:0 baseline (66, incl. constrained), main (77), high (100), level 1b..5.2.
// avc3 (in-band parameter sets) is refused: the demuxer requires avcC extradata.
struct Avc1 { int profile = 0, constraints = 0, level = 0; };
inline std::optional<Avc1> parseAvc1(std::string_view codec)
{
    if (codec.substr(0, 5) != "avc1.") return std::nullopt;
    auto rest = codec.substr(5);
    Avc1 r;
    auto dot = rest.find('.');
    if (dot == std::string_view::npos) {
        if (rest.size() != 6) return std::nullopt;
        int d[6];
        for (int i = 0; i < 6; ++i)
            if (!hexDigit(rest[i], d[i])) return std::nullopt;
        r.profile = d[0] * 16 + d[1];
        r.constraints = d[2] * 16 + d[3];
        r.level = d[4] * 16 + d[5];
    } else if (!decimal(rest.substr(0, dot), r.profile) || !decimal(rest.substr(dot + 1), r.level))
        return std::nullopt;
    return r;
}
inline bool avc1Supported(std::string_view codec)
{
    auto p = parseAvc1(codec);
    if (!p) return false;
    if (p->profile != 66 && p->profile != 77 && p->profile != 100) return false;
    return p->level >= 9 && p->level <= 52; // 9 = level 1b, 52 = level 5.2
}
// AAC-LC (40.2), HE-AAC (40.5, SBR) and HE-AACv2 (40.29, PS): FFmpeg's AAC decoder.
inline bool aacSupported(std::string_view codec)
{
    return codec == "mp4a.40.2" || codec == "mp4a.40.02" || codec == "mp4a.40.5" || codec == "mp4a.40.05"
        || codec == "mp4a.40.29";
}
inline bool mp3InMp4(std::string_view codec) { return codec == "mp4a.6B" || codec == "mp4a.6b" || codec == "mp4a.69" || codec == "mp3"; }
inline bool vp8(std::string_view codec) { return codec == "vp8" || codec.substr(0, 5) == "vp08."; }
inline bool vp9(std::string_view codec) { return codec == "vp9" || codec.substr(0, 5) == "vp09."; }

// ---- OMNI_WEBM_V1: WebM for MediaSource --------------------------------------------------
// FFmpeg software decoders present in this build (OmniWebMDemuxer.cpp webmDecoders(),
// avcodec_find_decoder at run time). VP9 also plays on the hardware without them.
struct Decoders {
    bool vp9 = false, opus = false, vorbis = false;
    // OMNI_CODEC_VP9_DEFAULT_V1: not an FFmpeg decoder: 10-bit VP9 above 1080p on the hardware
    // allowed (kill switch /data/omni/vp9-10bit-4k-disabled.flag, OmniWebMDemuxer.h).
    bool vp9TenBitHigh = false;
    // OMNI_CODEC_HEVC_V1: HEVC in MP4 allowed (decoded by the hardware only; hevc-disabled.flag).
    bool hevc = false;
    // OMNI_CODEC_AV1_V1: a real software AV1 decoder (libdav1d / libaom-av1) is linked. FFmpeg's
    // native "av1" decoder is hwaccel-only and does not count. Informational: see kAv1Ready.
    bool av1Software = false;
};
// ---- OMNI_CODEC_AV1_V1: AV1 -----------------------------------------------------------------
// No route: sceVideodec2 has no AV1, and pacbrew's FFmpeg 7.0.1 has no dav1d/libaom. Even with a
// software decoder, OmniMP4Demuxer / OmniWebMDemuxer / PacketDecoder have no AV1 mapping yet;
// kAv1Ready is the single switch to flip once they do (then offer AV1 only up to the size dav1d
// keeps up with on the console: host measurement says 1080p30 with 2 threads; see the report).
constexpr bool kAv1Ready = false;
inline bool av1Codec(std::string_view codec) { return codec.substr(0, 5) == "av01." || codec == "av01" || codec == "av1"; }
inline bool av1Offered(const Decoders& d) { return kAv1Ready && d.av1Software; }
// VP9 limits (OmniWebMDemuxer -> PacketDecoder):
//   hardware (/data/omni/hw-decode.flag): 3840x2160 (Hw::Client::configure; PacketDecoder::
//     maxHardwarePixels). Console-verified: profile 0 to 4K, profile 2 (10-bit) at 1080p
//     (tools/vdec-probe f1080vp9 / g1080vp9p2 / j2160vp9), so 10-bit stays at 1920x1080.
//   software (FFmpeg vp9, fallback or flag off): 1920x1080 (PacketDecoder::maxPixels).
constexpr int64_t kMseVp9HardwareMaxPixels = int64_t(3840) * 2160;
constexpr uint32_t kMseVp9HardwareMaxWidth = 3840, kMseVp9HardwareMaxHeight = 2160;
// Native 4K SDR presentation (v103 console test): 2160p30 sustained with no steady
// drops; 2160p60 dropped ~23% in the steady measurement. Keep decoding support,
// but do not advertise smooth 60 fps above the existing 1440p threshold.
// Software VP9 uses the software H.264 limits (720p30).
// OMNI_SMOOTH_4K60_V1 (2026-10-26): since v139 reduced-copy presentation, 2160p60 SDR plays without
// scaling at ~1 repeat per 1,000 frames (RC7 30-minute gate; DL2 YouTube 299/300). Advertising it as
// smooth lets sites pick 2160p instead of 1440p, which needed a slow 1.5x CPU scale on a 4K screen.
constexpr int64_t kVp9Smooth60Pixels = int64_t(3840) * 2160;
constexpr double kVp9SmoothFramerateHigh = 60.0, kVp9SmoothFramerateLow = 30.0, kVp9TenBitSmoothFramerate = 30.0;

// "vp9" (legacy short form: profile 0, 8-bit) or "vp09.PP.LL.DD[.CC.cp.tc.mc.FF]".
struct Vp9 { int profile = 0, level = 0, bitDepth = 8, chroma = 1, primaries = 1, transfer = 1, matrix = 1, fullRange = 0; };
inline std::optional<Vp9> parseVp9(std::string_view codec)
{
    Vp9 r;
    if (codec == "vp9") return r;
    if (codec.substr(0, 5) != "vp09.") return std::nullopt;
    int* fields[] = { &r.profile, &r.level, &r.bitDepth, &r.chroma, &r.primaries, &r.transfer, &r.matrix, &r.fullRange };
    auto rest = codec.substr(5);
    size_t count = 0;
    for (;;) {
        if (count == 8) return std::nullopt;
        auto dot = rest.find('.');
        auto field = rest.substr(0, dot);
        if (field.size() != 2 || !decimal(field, *fields[count])) return std::nullopt;
        ++count;
        if (dot == std::string_view::npos) break;
        rest = rest.substr(dot + 1);
    }
    if (count < 3) return std::nullopt;   // profile, level and bit depth are mandatory
    return r;
}
inline bool vp9LevelKnown(int level)
{
    switch (level) {
    case 0: case 10: case 11: case 20: case 21: case 30: case 31: case 40: case 41:
    case 50: case 51: case 52: case 60: case 61: case 62:
        return true;
    default:
        return false;
    }
}
// Profile 0 8-bit or profile 2 10-bit, 4:2:0, SDR. Level 5.0/5.1 (1440p/4K) only for 8-bit on
// the hardware; software and 10-bit stop at level 4.1 (1080p60).
inline bool mseVp9Supported(std::string_view codec, bool hardware, const Decoders& decoders)
{
    auto v = parseVp9(codec);
    if (!v || !(hardware || decoders.vp9) || !vp9LevelKnown(v->level)) return false;
    const bool eightBit = v->profile == 0 && v->bitDepth == 8, tenBit = v->profile == 2 && v->bitDepth == 10;
    if (!eightBit && !tenBit) return false;                    // 4:2:2 / 4:4:4 / 12-bit: no route
    if (v->chroma > 1 || v->fullRange > 1) return false;       // 4:2:0 only
    if (v->transfer == 16 || v->transfer == 18) return false;  // PQ / HLG: no HDR output path
    // OMNI_CODEC_VP9_DEFAULT_V1: 10-bit to level 5.1 too, unless vp9-10bit-4k-disabled.flag.
    return v->level <= (hardware && (eightBit || decoders.vp9TenBitHigh) ? 51 : 41);
}
// ---- OMNI_CODEC_HEVC_V1: HEVC in fragmented MP4, hardware decode only ------------------------
// "hvc1" / "hev1" alone, or ISO/IEC 14496-15 E.3: <entry>.<space?><profile>.<compat>.<L|H><level>[.<constraints>...]
// e.g. hvc1.1.6.L93.B0 (Main 3.1), hev1.2.4.L153.B0 (Main10 5.1). Profile space must be 0 (no
// letter), profile 1 (Main) or 2 (Main10), level <= 153 (5.1): what Hw::Backend opens (L5.1,
// 3840x2160; OmniHwBackend.cpp open()). Limits: kMseHevcMaxWidth/Height (Hw::Client::configure).
struct Hevc { int profile = 1, level = 153; bool tierHigh = false; };
inline std::optional<Hevc> parseHevc(std::string_view codec)
{
    if (codec.substr(0, 4) != "hvc1" && codec.substr(0, 4) != "hev1") return std::nullopt;
    Hevc r;
    if (codec.size() == 4) return r;                 // bare entry: Main, level unknown
    if (codec[4] != '.') return std::nullopt;
    auto rest = codec.substr(5);
    std::vector<std::string_view> f;
    while (true) {
        auto dot = rest.find('.');
        f.push_back(rest.substr(0, dot));
        if (dot == std::string_view::npos) break;
        rest = rest.substr(dot + 1);
    }
    if (f.size() < 3 || f[0].empty() || f[1].empty() || f[2].size() < 2) return std::nullopt;
    if (f[0][0] < '0' || f[0][0] > '9') return std::nullopt;   // profile space A/B/C: not decoded
    if (!decimal(f[0], r.profile)) return std::nullopt;
    char tier = lower(f[2][0]);
    if (tier != 'l' && tier != 'h') return std::nullopt;
    r.tierHigh = tier == 'h';
    if (!decimal(f[2].substr(1), r.level)) return std::nullopt;
    return r;
}
inline bool mseHevcSupported(std::string_view codec, bool hardware, const Decoders& decoders)
{
    auto h = parseHevc(codec);
    return h && hardware && decoders.hevc && (h->profile == 1 || h->profile == 2) && h->level > 0 && h->level <= 153;
}
constexpr uint32_t kMseHevcMaxWidth = 3840, kMseHevcMaxHeight = 2160;
inline bool mseWebMAudio(std::string_view codec, const Decoders& decoders)
{
    return (codec == "opus" && decoders.opus) || (codec == "vorbis" && decoders.vorbis);
}
// ---- OMNI_CODEC_OPUS_V1: Opus in fragmented MP4 ('Opus' sample entry + dOps, OmniMP4Demuxer).
// Codec strings: "opus" (what Chrome/Firefox/Safari and YouTube/Shaka use) and "mp4a.ad"
// (MP4 object type indication 0xAD). Only when FFmpeg's opus decoder is linked (probe).
inline bool opusCodec(std::string_view codec) { return codec == "opus" || lowered(codec) == "mp4a.ad"; }
inline bool mseMp4Opus(std::string_view codec, const Decoders& decoders) { return decoders.opus && opusCodec(codec); }

// MediaSource type check (isTypeSupported, addSourceBuffer). MP4: H.264 + AAC in fragmented
// MP4 (OmniMP4Demuxer codec_whitelist "h264,aac", format "mov"). OMNI_WEBM_V1: WebM with VP9 /
// Opus / Vorbis (OmniWebMDemuxer), each only when something can decode it (`hardware` = the
// hardware decode flag, `decoders` = FFmpeg). The two-argument forms answer as before (no WebM).
inline bool mseCodec(std::string_view container, std::string_view codec, bool hardware, const Decoders& decoders)
{
    if (av1Codec(codec) && !av1Offered(decoders)) return false; // OMNI_CODEC_AV1_V1: explicit refusal
    if (container == "video/webm" || container == "audio/webm")
        return mseWebMAudio(codec, decoders) || (container == "video/webm" && mseVp9Supported(codec, hardware, decoders));
    if (mseMp4Opus(codec, decoders)) return container == "video/mp4" || container == "audio/mp4"; // OMNI_CODEC_OPUS_V1
    if (mseHevcSupported(codec, hardware, decoders)) return container == "video/mp4"; // OMNI_CODEC_HEVC_V1
    if (aacSupported(codec)) return container == "video/mp4" || container == "audio/mp4";
    return container == "video/mp4" && avc1Supported(codec);
}
inline bool mseCodec(std::string_view container, std::string_view codec) { return mseCodec(container, codec, false, {}); }
inline Support mseTypeSupport(std::string_view containerType, const std::vector<std::string>& codecs, bool hardware, const Decoders& decoders)
{
    auto container = lowered(containerType);
    if (container == "video/webm" || container == "audio/webm") {
        bool any = container == "video/webm" ? hardware || decoders.vp9 : decoders.opus || decoders.vorbis;
        if (!any) return Support::No;
    } else if (container != "video/mp4" && container != "audio/mp4")
        return Support::No;
    for (auto& codec : codecs)
        if (!mseCodec(container, codec, hardware, decoders)) return Support::No;
    // MediaSource needs IsSupported for an explicit codec list; "maybe" only for a bare container.
    return codecs.empty() ? Support::Maybe : Support::Yes;
}
inline Support mseTypeSupport(std::string_view containerType, const std::vector<std::string>& codecs)
{
    return mseTypeSupport(containerType, codecs, false, {});
}
// OMNI_CODEC_OPUS_V1: the one MSE entry point (OmniMSESource.h omniMSETypeSupport, which serves
// isTypeSupported, addSourceBuffer and, through MediaPlayer::supportsType, decodingInfo).
// `webm` = WebM byte streams offered (OmniMedia::webmMseEnabled()); `decoders` = the FFmpeg
// probe (OmniMedia::webmDecoders()). MP4 answers use the probe whether or not WebM is offered.
struct Platform { bool hardware = false, webm = false; Decoders decoders; };
inline Support mseTypeSupport(std::string_view containerType, const std::vector<std::string>& codecs, const Platform& p)
{
    auto container = lowered(containerType);
    if (!p.webm && (container == "video/webm" || container == "audio/webm")) return Support::No;
    return mseTypeSupport(containerType, codecs, p.hardware, p.decoders);
}

// File player (OmniVideoDecoder / OmniAudioDecoder): containers mov / matroska / webm,
// video h264 / vp8 / vp9, audio aac / opus / vorbis / mp3 (whitelists in their open()).
inline bool fileVideoCodec(std::string_view container, std::string_view codec)
{
    if (container == "video/mp4") return avc1Supported(codec) || vp9(codec);
    if (container == "video/webm") return vp8(codec) || vp9(codec);
    return false;
}
inline bool fileAudioCodec(std::string_view container, std::string_view codec)
{
    if (container == "audio/mp4") return aacSupported(codec) || mp3InMp4(codec) || codec == "opus";
    if (container == "audio/webm") return codec == "opus" || codec == "vorbis";
    return false;
}

struct VideoQuery {
    std::string containerType;
    std::vector<std::string> codecs;
    uint32_t width = 0, height = 0;
    uint64_t bitrate = 0;     // not a limit: Omni has no bitrate cap
    double framerate = 0;     // only affects smooth
    bool alpha = false, hdr = false;
};
struct AudioQuery {
    std::string containerType;
    std::vector<std::string> codecs;
    std::string channels;     // "2", "5.1", "" (unknown)
    std::optional<uint32_t> samplerate;
    std::optional<uint64_t> bitrate;
    bool spatialRendering = false;
};
struct Query {
    Kind kind = Kind::Other;
    bool hardwareDecode = false;   // /data/omni/hw-decode.flag (MSE H.264 and VP9)
    bool webm = false;             // OMNI_WEBM_V1: WebM offered (/data/omni/webm-mse.flag)
    Decoders decoders;             // OMNI_WEBM_V1: FFmpeg software decoders (webmDecoders())
    std::optional<VideoQuery> video;
    std::optional<AudioQuery> audio;
};
struct Answer {
    bool supported = false, smooth = false, powerEfficient = false;
    const char* reason = "no media";
};

inline Answer refuse(const char* why) { Answer a; a.reason = why; return a; }

// OMNI_WEBM_V1: MSE VP9 in WebM. Limits and smooth rule: see kMseVp9HardwareMaxPixels.
inline Answer decideMseVp9(bool hardware, const VideoQuery& v, const Decoders& decoders)
{
    const auto& codec = v.codecs[0];
    if (!mseVp9Supported(codec, hardware, decoders)) return refuse("video: codec/container not played");
    if (v.alpha) return refuse("video: alpha");
    if (v.hdr) return refuse("video: HDR");
    if (v.width > kMaxSide || v.height > kMaxSide) return refuse("video: side > 4096");
    const bool tenBit = parseVp9(codec)->bitDepth > 8;
    const int64_t pixels = int64_t(v.width) * v.height;
    if (pixels > kMseMaxPixels) {
        if (!hardware) return refuse("video: VP9 above 1920x1080 needs hardware decode");
        if (tenBit && !decoders.vp9TenBitHigh) return refuse("video: 10-bit VP9 above 1920x1080 (vp9-10bit-4k-disabled.flag)");
        if (pixels > kMseVp9HardwareMaxPixels || v.width > kMseVp9HardwareMaxWidth || v.height > kMseVp9HardwareMaxHeight)
            return refuse("video: above 3840x2160");
    }
    Answer a;
    a.supported = true;
    a.powerEfficient = hardware;
    if (!hardware)
        a.smooth = pixels <= kSoftwareSmoothPixels && v.framerate <= kSoftwareSmoothFramerate;
    else if (tenBit)
        a.smooth = v.framerate <= kVp9TenBitSmoothFramerate;
    else
        a.smooth = v.framerate <= (pixels <= kVp9Smooth60Pixels ? kVp9SmoothFramerateHigh : kVp9SmoothFramerateLow);
    a.reason = a.smooth ? "ok" : "ok, not smooth";
    return a;
}

// MSE HEVC uses the same presentation budget as VP9. Conservative smoothness
// above 1440p is 30 fps; this is not a separate HEVC playback benchmark.
inline Answer decideMseHevc(bool hardware, const VideoQuery& v, const Decoders& decoders)
{
    const auto& codec = v.codecs[0];
    if (!parseHevc(codec)) return refuse("video: codec/container not played");
    if (!decoders.hevc) return refuse("video: HEVC disabled (hevc-disabled.flag)");
    if (!hardware) return refuse("video: HEVC needs hardware decode");
    if (!mseHevcSupported(codec, hardware, decoders)) return refuse("video: HEVC profile/level not decoded");
    if (v.alpha) return refuse("video: alpha");
    if (v.hdr) return refuse("video: HDR");
    if (v.width > kMseHevcMaxWidth || v.height > kMseHevcMaxHeight) return refuse("video: above 3840x2160");
    Answer a;
    a.supported = a.powerEfficient = true;
    a.smooth = v.framerate <= (parseHevc(codec)->profile == 2 || int64_t(v.width) * v.height > kVp9Smooth60Pixels ? kVp9TenBitSmoothFramerate : kVp9SmoothFramerateHigh);
    a.reason = a.smooth ? "ok" : "ok, not smooth";
    return a;
}

// `webm`: the FFmpeg decoders when WebM is offered, nullptr when not (answers as before).
// OMNI_CODEC_HEVC_V1: `decoders` = the probe whether or not WebM is offered (HEVC in MP4).
inline Answer decideVideo(Kind kind, bool hardware, const VideoQuery& v, const Decoders* webm = nullptr, const Decoders* decoders = nullptr)
{
    if (v.codecs.size() != 1) return refuse("video: need exactly one codec");
    auto container = lowered(v.containerType);
    const auto& codec = v.codecs[0];
    bool mse = kind == Kind::MediaSource;
    if (mse && decoders && container == "video/mp4" && parseHevc(codec)) return decideMseHevc(hardware, v, *decoders); // OMNI_CODEC_HEVC_V1
    if (av1Codec(codec) && !(decoders && av1Offered(*decoders))) return refuse("video: AV1 has no decoder in this build"); // OMNI_CODEC_AV1_V1
    if (mse && webm && container == "video/webm") return decideMseVp9(hardware, v, *webm); // OMNI_WEBM_V1
    if (mse ? container != "video/mp4" || !avc1Supported(codec) : !fileVideoCodec(container, codec))
        return refuse("video: codec/container not played");
    if (v.alpha) return refuse("video: alpha");
    if (v.hdr) return refuse("video: HDR");
    if (v.width > kMaxSide || v.height > kMaxSide) return refuse("video: side > 4096");
    int64_t pixels = int64_t(v.width) * v.height;
    if (pixels > (mse ? kMseMaxPixels : kFileMaxPixels)) return refuse("video: above 1920x1080 pixels");
    bool hw = mse && hardware; // the file player and VP8/VP9 are software
    Answer a;
    a.supported = true;
    a.powerEfficient = hw;
    a.smooth = hw ? pixels <= kHardwareSmoothPixels && v.framerate <= kHardwareSmoothFramerate
                  : pixels <= kSoftwareSmoothPixels && v.framerate <= kSoftwareSmoothFramerate;
    a.reason = a.smooth ? "ok" : "ok, not smooth";
    return a;
}

// OMNI_CODEC_OPUS_V1: `decoders` = the FFmpeg probe (Opus in MP4), given whether or not WebM is.
inline Answer decideAudio(Kind kind, const AudioQuery& q, const Decoders* webm = nullptr, const Decoders* decoders = nullptr)
{
    if (q.codecs.size() != 1) return refuse("audio: need exactly one codec");
    auto container = lowered(q.containerType);
    const auto& codec = q.codecs[0];
    // OMNI_WEBM_V1: MSE audio is AAC in MP4, or Opus / Vorbis in WebM when FFmpeg decodes them.
    bool played = kind == Kind::MediaSource
        ? (container == "audio/mp4" && (aacSupported(codec) || (decoders && mseMp4Opus(codec, *decoders))))
            || (webm && (container == "audio/webm" || container == "video/webm") && mseWebMAudio(codec, *webm))
        : fileAudioCodec(container, codec);
    if (!played)
        return refuse("audio: codec/container not played");
    if (q.spatialRendering) return refuse("audio: spatial rendering");
    if (!q.channels.empty()) {
        char* end = nullptr;
        double channels = std::strtod(q.channels.c_str(), &end);
        if (end == q.channels.c_str() || !(channels > 0) || channels > kMaxAudioChannels)
            return refuse("audio: channels");
    }
    if (q.samplerate && (*q.samplerate < kMinSampleRate || *q.samplerate > kMaxSampleRate))
        return refuse("audio: sample rate");
    Answer a;
    a.supported = a.smooth = a.powerEfficient = true;
    a.reason = "ok";
    return a;
}

inline Answer decide(const Query& q)
{
    if (q.kind == Kind::Other) return refuse("type not handled (webrtc)");
    if (!q.video && !q.audio) return refuse("no media");
    Answer result;
    result.supported = result.smooth = result.powerEfficient = true;
    result.reason = "ok";
    for (int part = 0; part < 2; ++part) {
        if (part == 0 && !q.video) continue;
        if (part == 1 && !q.audio) continue;
        const Decoders* webm = q.webm ? &q.decoders : nullptr; // OMNI_WEBM_V1
        Answer a = part == 0 ? decideVideo(q.kind, q.hardwareDecode, *q.video, webm, &q.decoders) // OMNI_CODEC_HEVC_V1
                             : decideAudio(q.kind, *q.audio, webm, &q.decoders);
        if (!a.supported) return a;
        result.smooth = result.smooth && a.smooth;
        result.powerEfficient = result.powerEfficient && a.powerEfficient;
        if (!a.smooth) result.reason = a.reason;
    }
    return result;
}

} // namespace OmniMedia::Caps
