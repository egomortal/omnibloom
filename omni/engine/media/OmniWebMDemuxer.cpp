// WebM byte-stream parser for Omni's MediaSource path (OMNI_WEBM_V1). See the header.
// SPDX-License-Identifier: GPL-3.0-or-later
// Written for Omni from the Matroska/EBML specifications (RFC 8794, RFC 9559), the W3C
// "WebM Byte Stream Format" and RFC 6716 (Opus TOC); WebKit's Cocoa SourceBufferParserWebM
// was read for its duration rules only. No code copied.
#include "OmniWebMDemuxer.h"
#include <algorithm>
#include <cmath>
#include <cstdio> // OMNI_CODEC_OPUS_V1: decoder probe log
#include <cstring>
#include <limits>
#include <optional>
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavcodec/vorbis_parser.h>
}

namespace OmniMedia {
namespace {
constexpr uint64_t kUnknownSize = ~uint64_t(0);
constexpr int64_t kNsPerSecond = 1000000000;
constexpr int64_t kMaxTicks = int64_t(1) << 62;

enum : uint32_t {
    kEBML = 0x1A45DFA3, kEBMLReadVersion = 0x42F7, kEBMLMaxIDLength = 0x42F2, kEBMLMaxSizeLength = 0x42F3,
    kDocType = 0x4282, kDocTypeReadVersion = 0x4285,
    kSegment = 0x18538067, kSeekHead = 0x114D9B74, kInfo = 0x1549A966, kTracks = 0x1654AE6B,
    kCluster = 0x1F43B675, kCues = 0x1C53BB6B, kChapters = 0x1043A770, kTags = 0x1254C367,
    kAttachments = 0x1941A469, kVoid = 0xEC, kCRC32 = 0xBF,
    kTimecodeScale = 0x2AD7B1, kDuration = 0x4489,
    kTrackEntry = 0xAE, kTrackNumber = 0xD7, kTrackType = 0x83, kCodecID = 0x86, kCodecPrivate = 0x63A2,
    kDefaultDuration = 0x23E383, kCodecDelay = 0x56AA, kSeekPreRoll = 0x56BB, kVideo = 0xE0, kAudio = 0xE1,
    kPixelWidth = 0xB0, kPixelHeight = 0xBA, kSamplingFrequency = 0xB5, kChannels = 0x9F,
    kContentEncodings = 0x6D80,
    kTimecode = 0xE7, kSimpleBlock = 0xA3, kBlockGroup = 0xA0, kBlock = 0xA1, kBlockDuration = 0x9B,
    kReferenceBlock = 0xFB, kDiscardPadding = 0x75A2, kEncryptedBlock = 0xAF,
};

bool topLevel(uint32_t id)
{
    switch (id) {
    case kEBML: case kSegment: case kCluster: case kInfo: case kTracks: case kCues: case kSeekHead:
    case kTags: case kChapters: case kAttachments:
        return true;
    default:
        return false;
    }
}

// Element ID, 1..4 bytes with the length marker kept (as the specification writes IDs).
// Returns the length, 0 when more bytes are needed, -1 when invalid.
int readId(const uint8_t* p, size_t n, uint32_t& id)
{
    if (!n) return 0;
    int len = p[0] & 0x80 ? 1 : p[0] & 0x40 ? 2 : p[0] & 0x20 ? 3 : p[0] & 0x10 ? 4 : -1;
    if (len < 0) return -1;
    if (n < size_t(len)) return 0;
    uint32_t v = 0;
    for (int i = 0; i < len; i++) v = v << 8 | p[i];
    id = v;
    return len;
}
// Variable-size integer, marker removed. `allOnes` = every value bit set (unknown / reserved).
int readVint(const uint8_t* p, size_t n, uint64_t& value, bool& allOnes)
{
    if (!n) return 0;
    int len = 1;
    uint8_t mask = 0x80;
    while (len <= 8 && !(p[0] & mask)) { mask >>= 1; ++len; }
    if (len > 8) return -1;
    if (n < size_t(len)) return 0;
    uint64_t v = p[0] & (mask - 1);
    allOnes = v == uint64_t(mask - 1);
    for (int i = 1; i < len; i++) {
        v = v << 8 | p[i];
        allOnes = allOnes && p[i] == 0xff;
    }
    value = v;
    return len;
}
int readSize(const uint8_t* p, size_t n, uint64_t& size)
{
    bool allOnes = false;
    int len = readVint(p, n, size, allOnes);
    if (len > 0 && allOnes) size = kUnknownSize;
    return len;
}

struct Child { uint32_t id = 0; const uint8_t* data = nullptr; size_t size = 0; };
// Children of a fully buffered master element. Unknown sizes are not allowed inside one.
class Children {
public:
    Children(const uint8_t* p, size_t n) : p_(p), n_(n) { }
    bool next(Child& c)
    {
        if (bad_ || at_ >= n_) return false;
        uint32_t id; uint64_t size;
        int il = readId(p_ + at_, n_ - at_, id);
        int sl = il > 0 ? readSize(p_ + at_ + il, n_ - at_ - size_t(il), size) : 0;
        if (il <= 0 || sl <= 0 || size == kUnknownSize || size > n_ - at_ - size_t(il) - size_t(sl)) { bad_ = true; return false; }
        c.id = id; c.data = p_ + at_ + il + sl; c.size = size_t(size);
        at_ += size_t(il) + size_t(sl) + size_t(size);
        return true;
    }
    bool failed() const { return bad_; }
private:
    const uint8_t* p_; size_t n_; size_t at_ = 0; bool bad_ = false;
};
bool readUint(const Child& c, uint64_t& v)
{
    if (c.size > 8) return false;
    v = 0;
    for (size_t i = 0; i < c.size; i++) v = v << 8 | c.data[i];
    return true;
}
bool readInt(const Child& c, int64_t& v)
{
    if (c.size > 8) return false;
    uint64_t u = 0;
    for (size_t i = 0; i < c.size; i++) u = u << 8 | c.data[i];
    if (c.size && c.size < 8 && (c.data[0] & 0x80)) u |= ~uint64_t(0) << (8 * c.size);
    v = int64_t(u);
    return true;
}
bool readFloat(const Child& c, double& v)
{
    if (c.size == 0) { v = 0; return true; }
    if (c.size == 4) { uint32_t u = uint32_t(c.data[0]) << 24 | uint32_t(c.data[1]) << 16 | uint32_t(c.data[2]) << 8 | c.data[3]; float f; memcpy(&f, &u, 4); v = f; return std::isfinite(v); }
    if (c.size == 8) { uint64_t u; readUint(c, u); memcpy(&v, &u, 8); return std::isfinite(v); }
    return false;
}
std::string readString(const Child& c)
{
    size_t n = c.size;
    while (n && !c.data[n - 1]) --n;
    return std::string(reinterpret_cast<const char*>(c.data), n);
}
// value * num / den rounded to nearest, ties away from zero; nullopt beyond +-2^62.
std::optional<int64_t> scaleRound(__int128 value, __int128 num, __int128 den)
{
    if (den <= 0) return std::nullopt;
    __int128 n = value * num;
    __int128 q = (n >= 0 ? n + den / 2 : n - den / 2) / den;
    if (q > kMaxTicks || q < -kMaxTicks) return std::nullopt;
    return int64_t(q);
}
struct VorbisDeleter { void operator()(AVVorbisParseContext* c) const { av_vorbis_parse_free(&c); } };
}

int opusPacketSamples(const uint8_t* p, size_t n)
{
    if (!n) return -1;
    // RFC 6716 3.1: config = TOC >> 3. SILK 10/20/40/60 ms, hybrid 10/20 ms, CELT 2.5/5/10/20 ms.
    static const int frameSamples[32] = {
        480, 960, 1920, 2880, 480, 960, 1920, 2880, 480, 960, 1920, 2880,
        480, 960, 480, 960,
        120, 240, 480, 960, 120, 240, 480, 960, 120, 240, 480, 960, 120, 240, 480, 960 };
    int code = p[0] & 3;
    int frames = code == 0 ? 1 : code == 3 ? (n < 2 ? -1 : p[1] & 0x3f) : 2;
    if (frames <= 0) return -1;
    int total = frames * frameSamples[p[0] >> 3];
    return total > 5760 ? -1 : total;   // 120 ms per packet at most
}

Caps::Decoders webmDecoders()
{
    static const Caps::Decoders found = [] {
        Caps::Decoders d;
        d.vp9 = avcodec_find_decoder(AV_CODEC_ID_VP9) != nullptr;
        d.opus = avcodec_find_decoder(AV_CODEC_ID_OPUS) != nullptr;
        d.vorbis = avcodec_find_decoder(AV_CODEC_ID_VORBIS) != nullptr;
        d.vp9TenBitHigh = vp9TenBitHighEnabled(); // OMNI_CODEC_VP9_DEFAULT_V1
        d.hevc = hevcEnabled();                    // OMNI_CODEC_HEVC_V1 (hardware decode only)
        // OMNI_CODEC_AV1_V1: by name; avcodec_find_decoder(AV_CODEC_ID_AV1) would return FFmpeg's
        // hwaccel-only "av1" wrapper, which cannot decode anything on the PS5.
        const char* av1 = avcodec_find_decoder_by_name("libdav1d") ? "libdav1d" : avcodec_find_decoder_by_name("libaom-av1") ? "libaom-av1" : nullptr;
        d.av1Software = av1 != nullptr;
        fprintf(stderr, "OMNI MEDIACAPS: av1 software decoder: %s; AV1 %s\n", av1 ? av1 : "none", Caps::av1Offered(d) ? "offered" : "refused");
        fprintf(stderr, "OMNI MEDIACAPS: hevc (hardware only) %s\n", d.hevc ? "on" : "off (hevc-disabled.flag)");
        // OMNI_CODEC_OPUS_V1: once per process, so the console log shows what the table used.
        fprintf(stderr, "OMNI MEDIACAPS: ffmpeg decoders vp9=%d opus=%d vorbis=%d; webm %s; vp9 10-bit above 1080p %s\n",
            d.vp9, d.opus, d.vorbis, webmMseEnabled() ? "offered (default)" : "off (webm-disabled.flag)", d.vp9TenBitHigh ? "on" : "off");
        fflush(stderr);
        return d;
    }();
    return found;
}

bool WebMInitialization::sameTracks(const WebMInitialization& o) const
{
    if (tracks.size() != o.tracks.size() || info.size() != o.info.size()) return false;
    for (size_t i = 0; i < tracks.size(); i++) {
        auto& a = tracks[i];
        auto& b = o.tracks[i];
        if (a.id != b.id || a.codec != b.codec || a.timeBase.numerator != b.timeBase.numerator
            || a.timeBase.denominator != b.timeBase.denominator || a.width != b.width || a.height != b.height
            || a.sampleRate != b.sampleRate || a.channels != b.channels || a.extraData != b.extraData
            || info[i].codecDelayNs != o.info[i].codecDelayNs)
            return false;
    }
    return true;
}

struct WebMParser::State {
    struct Track {
        DemuxTrack demux;
        WebMTrackInfo info;
        bool video = false;
        int64_t codecDelayTicks = 0, defaultDurationTicks = 0, lastDuration = 0;
        std::optional<DemuxPacket> held;   // newest video frame, duration not yet known
        std::unique_ptr<AVVorbisParseContext, VorbisDeleter> vorbis;
    };
    enum class Context { Top, Segment, Cluster };

    std::vector<uint8_t> buf;
    size_t pos = 0;
    uint64_t base = 0;      // stream offset of buf[0]
    uint64_t skip = 0;      // bytes of a skipped element still to come
    Context context = Context::Top;
    uint64_t timecodeScale = 1000000;
    double durationUnits = 0;
    bool tracksInSegment = false;
    bool sawEBMLHeader = false;
    bool haveInit = false;
    WebMInitialization init;
    std::vector<Track> tracks;
    bool clusterTimecodeValid = false;
    uint64_t clusterTimecode = 0, clusterEnd = kUnknownSize;
    std::string failure;

    bool fail(const char* why) { if (failure.empty()) failure = why; return false; }
    Track* find(uint64_t number)
    {
        for (auto& t : tracks) if (t.info.number == number) return &t;
        return nullptr;
    }
    int64_t estimate(const Track& t) const
    {
        if (t.defaultDurationTicks > 0) return t.defaultDurationTicks;
        if (t.lastDuration > 0) return t.lastDuration;
        return std::max<int64_t>(1, (t.demux.timeBase.denominator + 15) / 30);
    }
    void release(Track& t, std::optional<int64_t> nextPts, std::vector<WebMEvent>& events)
    {
        if (!t.held) return;
        auto& h = *t.held;
        if (nextPts && *nextPts > h.pts) { h.duration = *nextPts - h.pts; t.lastDuration = h.duration; }
        else h.duration = estimate(t);
        WebMEvent e;
        e.packet = std::move(h);
        t.held.reset();
        events.push_back(std::move(e));
    }
    void endCluster(std::vector<WebMEvent>& events)
    {
        for (auto& t : tracks) release(t, std::nullopt, events);
        context = Context::Segment;
        clusterTimecodeValid = false;
        clusterEnd = kUnknownSize;
    }
    void startSegment()
    {
        timecodeScale = 1000000;
        durationUnits = 0;
        tracksInSegment = false;
    }

    bool parseEBMLHeader(const uint8_t* p, size_t n)
    {
        Children it(p, n);
        Child c;
        std::string docType = "matroska";
        uint64_t v;
        while (it.next(c)) {
            switch (c.id) {
            case kDocType: docType = readString(c); break;
            case kEBMLReadVersion: if (!readUint(c, v) || v != 1) return fail("EBML read version unsupported"); break;
            case kEBMLMaxIDLength: if (!readUint(c, v) || v > 4) return fail("EBML ID length unsupported"); break;
            case kEBMLMaxSizeLength: if (!readUint(c, v) || v < 1 || v > 8) return fail("EBML size length unsupported"); break;
            case kDocTypeReadVersion: if (!readUint(c, v) || v > 4) return fail("DocType read version unsupported"); break;
            default: break;
            }
        }
        if (it.failed()) return fail("malformed EBML header");
        if (docType != "webm" && docType != "matroska") return fail("not a WebM stream");
        sawEBMLHeader = true;
        return true;
    }

    bool parseInfo(const uint8_t* p, size_t n)
    {
        Children it(p, n);
        Child c;
        uint64_t scale = 1000000;
        double duration = 0;
        while (it.next(c)) {
            if (c.id == kTimecodeScale && (!readUint(c, scale) || !scale || scale > uint64_t(kNsPerSecond))) return fail("TimecodeScale unsupported");
            if (c.id == kDuration && (!readFloat(c, duration) || duration < 0)) return fail("malformed Duration");
        }
        if (it.failed()) return fail("malformed Info");
        if (tracksInSegment && scale != init.timecodeScale) return fail("Info after Tracks changes TimecodeScale");
        timecodeScale = scale;
        durationUnits = duration;
        if (tracksInSegment) init.durationSeconds = duration * double(scale) / double(kNsPerSecond);
        return true;
    }

    bool parseTrackEntry(const uint8_t* p, size_t n, std::vector<Track>& out, bool& haveVideo, bool& haveAudio)
    {
        Children it(p, n);
        Child c;
        uint64_t number = 0, type = 0, defaultDuration = 0, codecDelay = 0, seekPreRoll = 0, width = 0, height = 0, channels = 1;
        double rate = 8000;   // Matroska default SamplingFrequency
        std::string codecId;
        const uint8_t* priv = nullptr;
        size_t privSize = 0;
        bool encodings = false;
        while (it.next(c)) {
            switch (c.id) {
            case kTrackNumber: if (!readUint(c, number)) return fail("malformed TrackNumber"); break;
            case kTrackType: if (!readUint(c, type)) return fail("malformed TrackType"); break;
            case kCodecID: codecId = readString(c); break;
            case kCodecPrivate: priv = c.data; privSize = c.size; break;
            case kDefaultDuration: if (!readUint(c, defaultDuration)) return fail("malformed DefaultDuration"); break;
            case kCodecDelay: if (!readUint(c, codecDelay)) return fail("malformed CodecDelay"); break;
            case kSeekPreRoll: if (!readUint(c, seekPreRoll)) return fail("malformed SeekPreRoll"); break;
            case kContentEncodings: encodings = true; break;
            case kVideo: {
                Children v(c.data, c.size);
                Child d;
                while (v.next(d)) {
                    if (d.id == kPixelWidth && !readUint(d, width)) return fail("malformed PixelWidth");
                    if (d.id == kPixelHeight && !readUint(d, height)) return fail("malformed PixelHeight");
                }
                if (v.failed()) return fail("malformed Video element");
                break;
            }
            case kAudio: {
                Children a(c.data, c.size);
                Child d;
                while (a.next(d)) {
                    if (d.id == kSamplingFrequency && !readFloat(d, rate)) return fail("malformed SamplingFrequency");
                    if (d.id == kChannels && !readUint(d, channels)) return fail("malformed Channels");
                }
                if (a.failed()) return fail("malformed Audio element");
                break;
            }
            default: break;
            }
        }
        if (it.failed()) return fail("malformed TrackEntry");
        if (type != 1 && type != 2) return true;   // subtitles, metadata...: not played, blocks dropped
        if (!number || number > UINT32_MAX) return fail("track number out of range");
        for (auto& t : out) if (t.info.number == number) return fail("duplicate track number");
        if (encodings) return fail("encrypted or compressed track unsupported");
        if (privSize > WebMParser::maxCodecPrivateBytes) return fail("CodecPrivate too large");
        if (codecDelay > uint64_t(kNsPerSecond) || defaultDuration > uint64_t(10) * kNsPerSecond) return fail("track timing out of range");
        Track t;
        t.info.number = number; t.info.codecId = codecId;
        t.info.defaultDurationNs = defaultDuration; t.info.codecDelayNs = codecDelay; t.info.seekPreRollNs = seekPreRoll;
        t.demux.id = int64_t(number);
        if (priv) t.demux.extraData.assign(priv, priv + privSize);
        if (type == 1) {
            if (haveVideo) return fail("more than one video track");
            haveVideo = true;
            if (codecId != "V_VP9") return fail("unsupported video codec");
            if (!width || !height || width > 16384 || height > 16384) return fail("video size missing or out of range");
            t.video = true;
            t.demux.codec = DemuxCodec::VP9;
            t.demux.width = int(width); t.demux.height = int(height);
            t.demux.timeBase = { 1, int(kNsPerSecond % int64_t(timecodeScale) ? kNsPerSecond : kNsPerSecond / int64_t(timecodeScale)) };
        } else {
            if (haveAudio) return fail("more than one audio track");
            haveAudio = true;
            if (codecId == "A_OPUS") {
                if (privSize < 19 || memcmp(priv, "OpusHead", 8)) return fail("Opus track without OpusHead");
                if (priv[9] < 1 || priv[9] > 8 || priv[18] > 1) return fail("Opus channel layout unsupported");
                t.demux.codec = DemuxCodec::Opus;
                t.demux.channels = priv[9];
                t.demux.sampleRate = 48000;   // Opus always decodes at 48 kHz
            } else if (codecId == "A_VORBIS") {
                if (!privSize) return fail("Vorbis track without headers");
                t.vorbis.reset(av_vorbis_parse_init(priv, int(privSize)));
                if (!t.vorbis) return fail("malformed Vorbis headers");
                if (!(rate >= 8000 && rate <= 192000) || channels < 1 || channels > 8) return fail("Vorbis rate/channels out of range");
                t.demux.codec = DemuxCodec::Vorbis;
                t.demux.channels = int(channels);
                t.demux.sampleRate = int(std::lround(rate));
            } else {
                return fail("unsupported audio codec");
            }
            t.demux.timeBase = { 1, t.demux.sampleRate };
        }
        auto ticks = [&](uint64_t ns) { return scaleRound(__int128(ns), t.demux.timeBase.denominator, kNsPerSecond).value_or(0); };
        t.defaultDurationTicks = ticks(defaultDuration);
        t.codecDelayTicks = t.video ? 0 : ticks(codecDelay);
        out.push_back(std::move(t));
        return true;
    }

    bool parseTracks(const uint8_t* p, size_t n, std::vector<WebMEvent>& events)
    {
        Children it(p, n);
        Child c;
        std::vector<Track> next;
        bool haveVideo = false, haveAudio = false;
        while (it.next(c))
            if (c.id == kTrackEntry && !parseTrackEntry(c.data, c.size, next, haveVideo, haveAudio)) return false;
        if (it.failed()) return fail("malformed Tracks");
        if (next.empty()) return fail("no audio or video track");
        for (auto& t : tracks) release(t, std::nullopt, events);
        tracks = std::move(next);
        WebMEvent e;
        e.kind = WebMEvent::Kind::Initialization;
        e.initialization.timecodeScale = timecodeScale;
        e.initialization.durationSeconds = durationUnits * double(timecodeScale) / double(kNsPerSecond);
        for (auto& t : tracks) { e.initialization.tracks.push_back(t.demux); e.initialization.info.push_back(t.info); }
        init = e.initialization;
        haveInit = true;
        tracksInSegment = true;
        events.push_back(std::move(e));
        return true;
    }

    bool parseBlock(const uint8_t* p, size_t n, bool simple, bool groupKey, std::optional<uint64_t> blockDuration,
                    int64_t discardPaddingNs, std::vector<WebMEvent>& events)
    {
        uint64_t number;
        bool allOnes = false;
        int l = readVint(p, n, number, allOnes);
        if (l <= 0 || allOnes) return fail("malformed block track number");
        if (n < size_t(l) + 3) return fail("truncated block header");
        Track* t = find(number);
        if (!t) return true;   // a track that is not played
        if (!clusterTimecodeValid) return fail("block before the cluster timecode");
        const int16_t relative = int16_t(uint16_t(p[l]) << 8 | p[l + 1]);
        const uint8_t flags = p[l + 2];
        size_t at = size_t(l) + 3;
        // Frame layout (lacing, flags bits 1-2).
        std::vector<std::pair<size_t, size_t>> frames;
        const int lacing = (flags >> 1) & 3;
        if (!lacing) {
            frames.emplace_back(at, n - at);
        } else {
            if (at >= n) return fail("truncated lacing header");
            size_t count = size_t(p[at++]) + 1;
            if (count > WebMParser::maxFramesPerBlock) return fail("too many laced frames");
            std::vector<uint64_t> sizes(count, 0);
            if (lacing == 2) {   // fixed size
                if ((n - at) % count) return fail("fixed lacing size mismatch");
                std::fill(sizes.begin(), sizes.end(), uint64_t((n - at) / count));
            } else {
                uint64_t sum = 0;
                for (size_t i = 0; i + 1 < count; i++) {
                    if (lacing == 1) {   // Xiph: 255-continued byte sums
                        uint64_t laced = 0;
                        uint8_t b;
                        do {
                            if (at >= n) return fail("truncated Xiph lacing");
                            b = p[at++];
                            laced += b;
                        } while (b == 255);
                        sizes[i] = laced;
                    } else {             // EBML: first size, then signed differences
                        uint64_t raw;
                        bool ones = false;
                        int len = readVint(p + at, n - at, raw, ones);
                        if (len <= 0 || ones) return fail("malformed EBML lacing");
                        at += size_t(len);
                        if (!i) sizes[i] = raw;
                        else {
                            int64_t delta = int64_t(raw) - ((int64_t(1) << (7 * len - 1)) - 1);
                            int64_t laced = int64_t(sizes[i - 1]) + delta;
                            if (laced < 0) return fail("negative EBML lacing size");
                            sizes[i] = uint64_t(laced);
                        }
                    }
                    sum += sizes[i];
                    if (sum > n) return fail("laced sizes exceed the block");
                }
                if (sum > n - at) return fail("laced sizes exceed the block");
                sizes[count - 1] = (n - at) - sum;
            }
            for (auto laced : sizes) { frames.emplace_back(at, size_t(laced)); at += size_t(laced); }
            if (at != n) return fail("laced sizes do not fill the block");
        }
        for (auto& f : frames)
            if (!f.second) return fail("empty frame");
        const auto& tb = t->demux.timeBase;
        auto start = scaleRound(__int128(clusterTimecode) + relative, __int128(timecodeScale) * tb.denominator, kNsPerSecond);
        if (!start) return fail("block timestamp out of range");
        if (!t->video) {
            int64_t pts = *start - t->codecDelayTicks;
            for (size_t i = 0; i < frames.size(); i++) {
                const uint8_t* data = p + frames[i].first;
                const size_t size = frames[i].second;
                int samples = t->demux.codec == DemuxCodec::Opus ? opusPacketSamples(data, size)
                    : size > size_t(std::numeric_limits<int>::max()) ? -1 : av_vorbis_parse_frame(t->vorbis.get(), data, int(size));
                if (samples <= 0) return fail("audio packet duration unknown");
                WebMEvent e;
                auto& packet = e.packet;
                packet.trackId = t->demux.id; packet.timeBase = tb;
                packet.pts = packet.dts = pts; packet.duration = samples;
                packet.keyFrame = true;   // every Opus/Vorbis packet is a random access point for MSE
                if (i + 1 == frames.size() && discardPaddingNs > 0) {
                    auto trim = scaleRound(discardPaddingNs, tb.denominator, kNsPerSecond).value_or(0);
                    uint32_t trailing = uint32_t(std::clamp<int64_t>(trim, 0, samples));
                    if (trailing) {
                        packet.skipSamples.assign(10, 0);   // FFmpeg AV_PKT_DATA_SKIP_SAMPLES: le32 start, le32 end
                        for (int b = 0; b < 4; b++) packet.skipSamples[4 + b] = uint8_t(trailing >> (8 * b));
                    }
                }
                packet.bytes.assign(data, data + size);
                events.push_back(std::move(e));
                pts += samples;
                if (pts > kMaxTicks) return fail("block timestamp out of range");
            }
            return true;
        }
        if (frames.size() != 1) return fail("laced video unsupported");
        DemuxPacket packet;
        packet.trackId = t->demux.id; packet.timeBase = tb;
        packet.pts = packet.dts = *start;
        packet.keyFrame = simple ? (flags & 0x80) != 0 : groupKey;
        packet.bytes.assign(p + frames[0].first, p + frames[0].first + frames[0].second);
        release(*t, packet.pts, events);
        if (blockDuration) {
            auto d = scaleRound(__int128(*blockDuration), __int128(timecodeScale) * tb.denominator, kNsPerSecond);
            if (!d || *d < 0) return fail("BlockDuration out of range");
            packet.duration = *d;
            if (*d > 0) t->lastDuration = *d;
            WebMEvent e;
            e.packet = std::move(packet);
            events.push_back(std::move(e));
        } else {
            t->held = std::move(packet);
        }
        return true;
    }

    bool parseBlockGroup(const uint8_t* p, size_t n, std::vector<WebMEvent>& events)
    {
        Children it(p, n);
        Child c, block;
        bool haveBlock = false, reference = false;
        std::optional<uint64_t> duration;
        int64_t discard = 0;
        uint64_t v;
        while (it.next(c)) {
            switch (c.id) {
            case kBlock: if (haveBlock) return fail("BlockGroup with two Blocks"); block = c; haveBlock = true; break;
            case kBlockDuration: if (!readUint(c, v)) return fail("malformed BlockDuration"); duration = v; break;
            case kReferenceBlock: reference = true; break;
            case kDiscardPadding: if (!readInt(c, discard)) return fail("malformed DiscardPadding"); break;
            default: break;
            }
        }
        if (it.failed()) return fail("malformed BlockGroup");
        if (!haveBlock) return fail("BlockGroup without Block");
        return parseBlock(block.data, block.size, false, !reference, duration, discard, events);
    }

    // Element body ready in the buffer? 1 yes, 0 need more, -1 error.
    int body(uint64_t size, size_t header, size_t limit, const char* what)
    {
        if (size == kUnknownSize || size > limit) { fail(what); return -1; }
        return buf.size() - pos >= header + size_t(size) ? 1 : 0;
    }

    bool run(std::vector<WebMEvent>& events)
    {
        for (;;) {
            if (skip) {
                uint64_t k = std::min<uint64_t>(skip, buf.size() - pos);
                pos += size_t(k); skip -= k;
                if (skip) return true;
                continue;
            }
            const uint64_t at = base + pos;
            if (context == Context::Cluster && clusterEnd != kUnknownSize) {
                if (at == clusterEnd) { endCluster(events); continue; }
                if (at > clusterEnd) return fail("element crosses the cluster end");
            }
            const uint8_t* p = buf.data() + pos;
            const size_t avail = buf.size() - pos;
            if (!avail) return true;
            uint32_t id;
            uint64_t size;
            int il = readId(p, avail, id);
            if (il < 0) return fail("invalid element ID");
            if (!il) return true;
            int sl = readSize(p + il, avail - size_t(il), size);
            if (sl < 0) return fail("invalid element size");
            if (!sl) return true;
            const size_t header = size_t(il) + size_t(sl);
            const uint8_t* data = p + header;
            auto skipElement = [&]() {
                if (size == kUnknownSize) return fail("unknown-size element cannot be skipped");
                pos += header; skip = size;
                return true;
            };
            if (context == Context::Top) {
                if (id == kEBML) {
                    int r = body(size, header, WebMParser::maxHeaderElementBytes, "EBML header too large");
                    if (r <= 0) return r == 0;
                    if (!parseEBMLHeader(data, size_t(size))) return false;
                    pos += header + size_t(size);
                } else if (id == kSegment) {
                    if (!sawEBMLHeader) return fail("WebM stream must start with an EBML header");
                    pos += header;
                    startSegment();
                    context = Context::Segment;
                } else if (id == kVoid || id == kCRC32) {
                    if (!skipElement()) return false;
                } else if (haveInit) {
                    context = Context::Segment;   // after abort(): a media segment may follow
                } else {
                    return fail("WebM stream must start with an EBML header");
                }
                continue;
            }
            if (context == Context::Cluster) {
                if (topLevel(id)) { endCluster(events); continue; }   // ends an unknown-size cluster
                if (size == kUnknownSize) return fail("unknown-size element inside a cluster");
                if (clusterEnd != kUnknownSize && (header > clusterEnd - at || size > clusterEnd - at - header)) return fail("element crosses the cluster end");
                if (id == kTimecode) {
                    int r = body(size, header, 8, "malformed cluster Timecode");
                    if (r <= 0) return r == 0;
                    uint64_t v = 0;
                    for (size_t i = 0; i < size_t(size); i++) v = v << 8 | data[i];
                    if (v > uint64_t(kMaxTicks)) return fail("cluster Timecode out of range");
                    clusterTimecode = v; clusterTimecodeValid = true;
                    pos += header + size_t(size);
                } else if (id == kSimpleBlock || id == kBlockGroup) {
                    int r = body(size, header, WebMParser::maxBlockElementBytes, "block too large");
                    if (r <= 0) return r == 0;
                    bool ok = id == kSimpleBlock ? parseBlock(data, size_t(size), true, false, std::nullopt, 0, events)
                                                 : parseBlockGroup(data, size_t(size), events);
                    if (!ok) return false;
                    pos += header + size_t(size);
                } else if (id == kEncryptedBlock) {
                    return fail("encrypted block unsupported");
                } else if (!skipElement()) {
                    return false;
                }
                continue;
            }
            // Segment level.
            switch (id) {
            case kEBML: {
                int r = body(size, header, WebMParser::maxHeaderElementBytes, "EBML header too large");
                if (r <= 0) return r == 0;
                if (!parseEBMLHeader(data, size_t(size))) return false;
                pos += header + size_t(size);
                context = Context::Top;
                break;
            }
            case kSegment:
                pos += header;
                startSegment();
                break;
            case kInfo: {
                int r = body(size, header, WebMParser::maxHeaderElementBytes, "Info too large");
                if (r <= 0) return r == 0;
                if (!parseInfo(data, size_t(size))) return false;
                pos += header + size_t(size);
                break;
            }
            case kTracks: {
                int r = body(size, header, WebMParser::maxHeaderElementBytes, "Tracks too large");
                if (r <= 0) return r == 0;
                if (!parseTracks(data, size_t(size), events)) return false;
                pos += header + size_t(size);
                break;
            }
            case kCluster:
                if (!haveInit) return fail("media segment before the initialization segment");
                pos += header;
                context = Context::Cluster;
                clusterTimecodeValid = false;
                clusterEnd = size == kUnknownSize ? kUnknownSize : at + header + size;
                break;
            default:   // SeekHead, Cues, Tags, Chapters, Attachments, Void, CRC-32, unknown
                if (!skipElement()) return false;
                break;
            }
        }
    }
};

WebMParser::WebMParser() : s(std::make_unique<State>()) { }
WebMParser::~WebMParser() = default;
const std::string& WebMParser::error() const { return s->failure; }
bool WebMParser::initialized() const { return s->haveInit; }
size_t WebMParser::bufferedBytes() const { return s->buf.size() - s->pos; }
void WebMParser::clear() { s = std::make_unique<State>(); }
void WebMParser::abort()
{
    auto& st = *s;
    st.buf.clear(); st.buf.shrink_to_fit();
    st.pos = 0; st.base = 0; st.skip = 0;
    st.context = st.haveInit ? State::Context::Segment : State::Context::Top;
    st.clusterTimecodeValid = false; st.clusterEnd = kUnknownSize;
    for (auto& t : st.tracks) {
        t.held.reset();
        if (t.vorbis) av_vorbis_parse_reset(t.vorbis.get());
    }
    st.failure.clear();
}

void WebMParser::endOfAppend(std::vector<WebMEvent>& events)
{
    auto& st = *s;
    if (!st.failure.empty() || st.context != State::Context::Cluster || st.clusterEnd != kUnknownSize
        || st.skip || st.pos != st.buf.size())
        return;
    for (auto& t : st.tracks) st.release(t, std::nullopt, events);
}

bool WebMParser::append(const uint8_t* data, size_t size, std::vector<WebMEvent>& events)
{
    auto& st = *s;
    if (!st.failure.empty()) return false;
    if (st.pos) {
        st.buf.erase(st.buf.begin(), st.buf.begin() + std::ptrdiff_t(st.pos));
        st.base += st.pos; st.pos = 0;
    }
    if (size) st.buf.insert(st.buf.end(), data, data + size);
    bool ok = st.run(events);
    if (st.pos == st.buf.size()) { st.base += st.pos; st.pos = 0; st.buf.clear(); }
    if (st.buf.capacity() > 2 * maxBlockElementBytes && st.buf.size() < maxBlockElementBytes) st.buf.shrink_to_fit();
    return ok;
}

}
