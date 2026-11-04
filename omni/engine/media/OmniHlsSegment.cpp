// HLS media segments (OMNI_HLS_NATIVE_V1). SPDX-License-Identifier: GPL-3.0-or-later
#include "OmniHlsSegment.h"
#include "OmniMP4SegmentBuffer.h"
#include <algorithm>
#include <chrono>
#include <cstring>
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/aes.h>
#include <libavutil/mem.h>
}

namespace OmniMedia::Hls {
namespace {
constexpr size_t maxSegmentBytes = 32 * 1024 * 1024;   // as an MSE SourceBuffer
constexpr size_t maxPackets = 16384;

struct Memory {
    const uint8_t* data = nullptr; size_t size = 0, position = 0;
    std::chrono::steady_clock::time_point deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    static int interrupt(void* o) { return std::chrono::steady_clock::now() > static_cast<Memory*>(o)->deadline; }
    static int read(void* o, uint8_t* dest, int n)
    {
        auto& m = *static_cast<Memory*>(o);
        if (interrupt(o)) return AVERROR_EXIT;
        size_t k = std::min(size_t(n > 0 ? n : 0), m.size - m.position);
        if (!k) return AVERROR_EOF;
        memcpy(dest, m.data + m.position, k); m.position += k; return int(k);
    }
    static int64_t seek(void* o, int64_t offset, int whence)
    {
        auto& m = *static_cast<Memory*>(o);
        if (whence == AVSEEK_SIZE) return int64_t(m.size);
        whence &= ~AVSEEK_FORCE;
        int64_t base = whence == SEEK_SET ? 0 : whence == SEEK_CUR ? int64_t(m.position) : whence == SEEK_END ? int64_t(m.size) : -1;
        if (base < 0 || base + offset < 0 || base + offset > int64_t(m.size)) return AVERROR(EINVAL);
        m.position = size_t(base + offset); return int64_t(m.position);
    }
};
int denyOpen(AVFormatContext*, AVIOContext**, const char*, int, AVDictionary**) { return AVERROR(EACCES); }

// Start codes: positions of NAL unit payloads in an Annex B buffer.
struct Nal { size_t offset, size; int type; };
std::vector<Nal> nals(const uint8_t* d, size_t n)
{
    std::vector<Nal> out;
    size_t i = 0, start = SIZE_MAX;
    while (i + 2 < n) {
        if (d[i] == 0 && d[i + 1] == 0 && d[i + 2] == 1) {
            if (start != SIZE_MAX) {
                size_t end = i;
                while (end > start && d[end - 1] == 0) --end;   // trailing zeros of a 4-byte start code
                if (end > start) out.push_back({ start, end - start, d[start] & 0x1f });
            }
            i += 3; start = i;
        } else ++i;
    }
    if (start != SIZE_MAX && start < n) {
        size_t end = n;
        while (end > start && d[end - 1] == 0) --end;
        if (end > start) out.push_back({ start, end - start, d[start] & 0x1f });
    }
    return out;
}
void put32(std::vector<uint8_t>& v, uint32_t x) { v.push_back(uint8_t(x >> 24)); v.push_back(uint8_t(x >> 16)); v.push_back(uint8_t(x >> 8)); v.push_back(uint8_t(x)); }

// Video size from the first SPS of an access unit (libavcodec's h264 parser, complete frames).
bool h264Size(const uint8_t* d, size_t n, int& width, int& height)
{
    AVCodecParserContext* pc = av_parser_init(AV_CODEC_ID_H264);
    AVCodecContext* ctx = avcodec_alloc_context3(nullptr);
    bool ok = false;
    if (pc && ctx) {
        pc->flags |= PARSER_FLAG_COMPLETE_FRAMES;
        std::vector<uint8_t> padded(d, d + n);
        padded.resize(n + AV_INPUT_BUFFER_PADDING_SIZE, 0);
        uint8_t* out = nullptr; int outSize = 0;
        av_parser_parse2(pc, ctx, &out, &outSize, padded.data(), int(n), AV_NOPTS_VALUE, AV_NOPTS_VALUE, 0);
        width = pc->width > 0 ? pc->width : ctx->width;
        height = pc->height > 0 ? pc->height : ctx->height;
        ok = width > 0 && height > 0;
    }
    av_parser_close(pc);
    avcodec_free_context(&ctx);
    return ok;
}
}

Container sniff(const std::vector<uint8_t>& b)
{
    if (b.size() >= 189 && b[0] == 0x47 && b[188] == 0x47) return Container::TransportStream;
    if (b.size() >= 188 && b[0] == 0x47) return Container::TransportStream;
    if (b.size() >= 8) {
        auto type = [&](size_t at) { return std::string(reinterpret_cast<const char*>(b.data() + at), 4); };
        auto t = type(4);
        if (t == "styp" || t == "moof" || t == "sidx" || t == "ftyp" || t == "prft" || t == "emsg" || t == "free") return Container::Fmp4;
    }
    if (b.size() >= 3 && b[0] == 'I' && b[1] == 'D' && b[2] == '3') return Container::PackedAudio;
    if (b.size() >= 2 && b[0] == 0xFF && (b[1] & 0xF6) == 0xF0) return Container::PackedAudio;
    return Container::Unknown;
}

bool parseAdts(const uint8_t* p, size_t n, Adts& a)
{
    if (n < 7 || p[0] != 0xFF || (p[1] & 0xF6) != 0xF0) return false;
    static const int rates[13] = { 96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000, 7350 };
    const bool crc = !(p[1] & 1);
    const int profile = p[2] >> 6, sfi = (p[2] >> 2) & 15, ch = ((p[2] & 1) << 2) | (p[3] >> 6);
    a.frameLength = ((p[3] & 3) << 11) | (p[4] << 3) | (p[5] >> 5);
    a.rawBlocks = (p[6] & 3) + 1;
    a.headerLength = crc ? 9 : 7;
    if (sfi > 12 || ch == 0 || a.frameLength < a.headerLength) return false;   // channel config 0 (PCE): not handled
    a.objectType = profile + 1; a.sampleRate = rates[sfi]; a.channels = ch == 7 ? 8 : ch;
    a.asc = { uint8_t((a.objectType << 3) | (sfi >> 1)), uint8_t(((sfi & 1) << 7) | (ch << 3)) };
    return true;
}

std::vector<uint8_t> annexBToLengthPrefixed(const uint8_t* d, size_t n)
{
    std::vector<uint8_t> out;
    out.reserve(n + 16);
    for (auto& u : nals(d, n)) {
        if (u.type == 9 || u.type == 12) continue;   // access unit delimiter, filler
        put32(out, uint32_t(u.size));
        out.insert(out.end(), d + u.offset, d + u.offset + u.size);
    }
    return out;
}

std::vector<uint8_t> avcCFromAnnexB(const uint8_t* d, size_t n)
{
    const Nal* sps = nullptr;
    std::vector<const Nal*> pps;
    auto units = nals(d, n);
    for (auto& u : units) {
        if (u.type == 7 && !sps && u.size >= 4) sps = &u;
        if (u.type == 8 && pps.size() < 4) pps.push_back(&u);
    }
    if (!sps || pps.empty()) return {};
    std::vector<uint8_t> c = { 1, d[sps->offset + 1], d[sps->offset + 2], d[sps->offset + 3], 0xFF, 0xE1 };
    c.push_back(uint8_t(sps->size >> 8)); c.push_back(uint8_t(sps->size));
    c.insert(c.end(), d + sps->offset, d + sps->offset + sps->size);
    c.push_back(uint8_t(pps.size()));
    for (auto* p : pps) {
        c.push_back(uint8_t(p->size >> 8)); c.push_back(uint8_t(p->size));
        c.insert(c.end(), d + p->offset, d + p->offset + p->size);
    }
    return c;
}

// Durations: the DTS step to the track's next packet; the last packet repeats the previous
// step (or, for audio, its own sample count).
static void fillDurations(Demuxed& out)
{
    for (size_t i = 0; i < out.packets.size(); i++) {
        auto& p = out.packets[i];
        if (p.duration > 0) continue;
        int64_t step = 0;
        for (size_t j = i + 1; j < out.packets.size(); j++)
            if (out.packets[j].trackId == p.trackId) { step = out.packets[j].dts - p.dts; break; }
        if (step <= 0)
            for (size_t j = i; j-- > 0;)
                if (out.packets[j].trackId == p.trackId) { step = out.packets[j].duration; break; }
        p.duration = step > 0 ? step : 3000;   // a lone frame: 1/30 s
        p.durationFromNextDTS = true;
        p.durationSource = DemuxDurationSource::NextTrackDTS;
    }
}

// One ADTS buffer (several frames) -> audio packets from `pts` on ({1,90000}).
static bool addAdtsFrames(const uint8_t* d, size_t n, int64_t pts, Demuxed& out, DemuxTrack*& audio, std::string& error)
{
    size_t at = 0;
    while (at + 7 <= n) {
        Adts a;
        if (!parseAdts(d + at, n - at, a)) {
            if (at == 0) { error = "bad ADTS frame"; return false; }
            break;   // trailing junk (ID3 at the end, padding)
        }
        if (size_t(a.frameLength) > n - at) break;
        if (!audio) {
            DemuxTrack t;
            t.id = 2; t.codec = DemuxCodec::AAC; t.timeBase = { 1, 90000 };
            t.sampleRate = a.sampleRate; t.channels = a.channels; t.extraData = a.asc;
            out.tracks.push_back(t);
            audio = &out.tracks.back();
        } else if (audio->sampleRate != a.sampleRate || audio->channels != a.channels) {
            error = "AAC format changes inside a segment"; return false;
        }
        const int64_t samples = int64_t(a.rawBlocks) * 1024;
        DemuxPacket p;
        p.trackId = 2; p.timeBase = { 1, 90000 }; p.pts = p.dts = pts; p.keyFrame = true;
        p.duration = (samples * 90000 + a.sampleRate / 2) / a.sampleRate;
        p.durationSource = DemuxDurationSource::AudioCodecSamples;
        p.bytes.assign(d + at + a.headerLength, d + at + a.frameLength);
        if (out.packets.size() >= maxPackets) { error = "too many packets in a segment"; return false; }
        out.packets.push_back(std::move(p));
        pts += (samples * 90000 + a.sampleRate / 2) / a.sampleRate;
        at += size_t(a.frameLength);
    }
    return true;
}

bool demuxTransportStream(const std::vector<uint8_t>& bytes, Demuxed& out)
{
    out = {};
    auto fail = [&](const char* why) { out.tracks.clear(); out.packets.clear(); out.error = why; return false; };
    if (bytes.empty() || bytes.size() > maxSegmentBytes) return fail("segment size");
    Memory mem; mem.data = bytes.data(); mem.size = bytes.size();
    auto* buffer = static_cast<uint8_t*>(av_malloc(65536));
    AVIOContext* io = buffer ? avio_alloc_context(buffer, 65536, 0, &mem, Memory::read, nullptr, Memory::seek) : nullptr;
    if (!io) { av_free(buffer); return fail("IO allocation failed"); }
    AVFormatContext* fmt = avformat_alloc_context();
    AVPacket* pkt = av_packet_alloc();
    auto cleanup = [&] {
        av_packet_free(&pkt);
        avformat_close_input(&fmt);
        if (io) { av_freep(&io->buffer); avio_context_free(&io); }
    };
    if (!fmt || !pkt) { cleanup(); return fail("allocation failed"); }
    fmt->pb = io; fmt->flags |= AVFMT_FLAG_CUSTOM_IO; fmt->io_open = denyOpen;
    fmt->interrupt_callback = { Memory::interrupt, &mem };
    fmt->max_streams = 8;
    AVDictionary* options = nullptr;
    av_dict_set(&options, "format_whitelist", "mpegts", 0);
    av_dict_set(&options, "protocol_whitelist", "", 0);
    av_dict_set(&options, "codec_whitelist", "h264,aac", 0);
    int rc = avformat_open_input(&fmt, nullptr, av_find_input_format("mpegts"), &options);
    av_dict_free(&options);
    if (rc < 0) { fmt = nullptr; cleanup(); return fail("MPEG-TS rejected"); }
    int videoIndex = -1, audioIndex = -1;
    DemuxTrack* video = nullptr;
    DemuxTrack* audio = nullptr;
    out.tracks.reserve(2);
    std::string error;
    std::vector<uint8_t> avcc;
    while ((rc = av_read_frame(fmt, pkt)) >= 0) {
        AVStream* st = fmt->streams[pkt->stream_index];
        const auto id = st->codecpar->codec_id;
        if (id == AV_CODEC_ID_H264 && (videoIndex < 0 || videoIndex == pkt->stream_index) && pkt->size > 0) {
            videoIndex = pkt->stream_index;
            if (pkt->pts == AV_NOPTS_VALUE && pkt->dts == AV_NOPTS_VALUE) { av_packet_unref(pkt); continue; }
            if (!video) {
                // The segment must start decodable: drop anything before the first keyframe that
                // carries SPS/PPS (RFC 8216 requires an IDR first; this guards broken encoders).
                avcc = avcCFromAnnexB(pkt->data, size_t(pkt->size));
                if (avcc.empty() || !(pkt->flags & AV_PKT_FLAG_KEY)) { av_packet_unref(pkt); continue; }
                DemuxTrack t;
                t.id = 1; t.codec = DemuxCodec::H264; t.timeBase = { 1, 90000 }; t.extraData = avcc;
                if (!h264Size(pkt->data, size_t(pkt->size), t.width, t.height)) { av_packet_unref(pkt); cleanup(); return fail("H.264 SPS unreadable"); }
                out.tracks.insert(out.tracks.begin(), t);
                video = &out.tracks.front();
                if (audio) audio = &out.tracks.back();
            }
            DemuxPacket p;
            p.trackId = 1; p.timeBase = { 1, 90000 };
            p.dts = pkt->dts != AV_NOPTS_VALUE ? pkt->dts : pkt->pts;
            p.pts = pkt->pts != AV_NOPTS_VALUE ? pkt->pts : p.dts;
            p.keyFrame = pkt->flags & AV_PKT_FLAG_KEY;
            p.bytes = annexBToLengthPrefixed(pkt->data, size_t(pkt->size));
            if (!p.bytes.empty()) {
                if (out.packets.size() >= maxPackets) { av_packet_unref(pkt); cleanup(); return fail("too many packets in a segment"); }
                out.packets.push_back(std::move(p));
            }
        } else if (id == AV_CODEC_ID_AAC && (audioIndex < 0 || audioIndex == pkt->stream_index) && pkt->size > 0) {
            audioIndex = pkt->stream_index;
            int64_t pts = pkt->pts != AV_NOPTS_VALUE ? pkt->pts : pkt->dts;
            if (pts == AV_NOPTS_VALUE) {   // interpolate from the previous audio packet
                for (size_t j = out.packets.size(); j-- > 0;)
                    if (out.packets[j].trackId == 2) { pts = out.packets[j].pts + out.packets[j].duration; break; }
            }
            if (pts != AV_NOPTS_VALUE) {
                const bool hadAudio = audio != nullptr;
                if (!addAdtsFrames(pkt->data, size_t(pkt->size), pts, out, audio, error)) { av_packet_unref(pkt); cleanup(); return fail(error.c_str()); }
                if (!hadAudio && audio && video) video = &out.tracks.front();
            }
        }
        av_packet_unref(pkt);
    }
    cleanup();
    if (rc != AVERROR_EOF) return fail("MPEG-TS read failed");
    if (out.tracks.empty()) return fail("no H.264 or AAC in the segment");
    // Track order: video first.
    std::stable_sort(out.tracks.begin(), out.tracks.end(), [](const DemuxTrack& a, const DemuxTrack& b) { return a.id < b.id; });
    fillDurations(out);
    return true;
}

bool demuxPackedAudio(const std::vector<uint8_t>& bytes, Demuxed& out)
{
    out = {};
    size_t at = 0;
    int64_t pts = 0;
    out.timestamped = false;
    // ID3v2 tag(s) first (RFC 8216 3.4): the PRIV frame com.apple.streaming.transportStreamTimestamp
    // holds the 33-bit MPEG-2 timestamp of the first sample.
    while (bytes.size() - at >= 10 && bytes[at] == 'I' && bytes[at + 1] == 'D' && bytes[at + 2] == '3') {
        const uint8_t* h = bytes.data() + at;
        size_t size = (size_t(h[6] & 0x7f) << 21) | (size_t(h[7] & 0x7f) << 14) | (size_t(h[8] & 0x7f) << 7) | size_t(h[9] & 0x7f);
        if (size > bytes.size() - at - 10) { out.error = "truncated ID3 tag"; return false; }
        const uint8_t* f = h + 10;
        const uint8_t* end = f + size;
        while (end - f >= 10) {
            size_t fs = (size_t(f[4]) << 24) | (size_t(f[5]) << 16) | (size_t(f[6]) << 8) | f[7];
            if (h[3] >= 4) fs = (size_t(f[4] & 0x7f) << 21) | (size_t(f[5] & 0x7f) << 14) | (size_t(f[6] & 0x7f) << 7) | size_t(f[7] & 0x7f);
            if (fs > size_t(end - f - 10)) break;
            static const char owner[] = "com.apple.streaming.transportStreamTimestamp";
            if (!memcmp(f, "PRIV", 4) && fs == sizeof(owner) + 8 && !memcmp(f + 10, owner, sizeof(owner))) {
                const uint8_t* t = f + 10 + sizeof(owner);
                uint64_t v = 0;
                for (int i = 0; i < 8; i++) v = v << 8 | t[i];
                pts = int64_t(v & ((1ull << 33) - 1));
                out.timestamped = true;
            }
            f += 10 + fs;
        }
        at += 10 + size;
    }
    DemuxTrack* audio = nullptr;
    out.tracks.reserve(1);
    std::string error;
    if (!addAdtsFrames(bytes.data() + at, bytes.size() - at, pts, out, audio, error)) { out.error = error; out.tracks.clear(); out.packets.clear(); return false; }
    if (out.packets.empty()) { out.error = "no ADTS frames"; return false; }
    return true;
}

bool demuxFmp4(const std::vector<uint8_t>& init, const std::vector<uint8_t>& segment, Demuxed& out)
{
    out = {};
    MP4SegmentBuffer framer;
    MP4SegmentBuffer::Segment s;
    std::vector<uint8_t> initBytes;
    if (!framer.append(init)) { out.error = "init framing"; return false; }
    if (framer.next(s) != MP4SegmentBuffer::Result::Ready || s.kind != MP4SegmentBuffer::Segment::Kind::Initialization) { out.error = "EXT-X-MAP is not an MP4 initialization segment"; return false; }
    initBytes = std::move(s.bytes);
    MP4DemuxResult info;
    if (!inspectMP4Initialization(initBytes, info)) { out.error = info.error; return false; }
    out.tracks = info.tracks;
    if (!framer.append(segment)) { out.error = "segment framing"; return false; }
    framer.finish();
    for (;;) {
        auto r = framer.next(s);
        if (r == MP4SegmentBuffer::Result::End || r == MP4SegmentBuffer::Result::NeedMore) break;
        if (r == MP4SegmentBuffer::Result::Error) { out.error = "fMP4 framing error"; return false; }
        if (s.kind != MP4SegmentBuffer::Segment::Kind::Media) continue;
        MP4DemuxResult res;
        if (!demuxMP4Fragment(initBytes, s.bytes, res)) { out.error = res.error; return false; }
        for (auto& p : res.packets) out.packets.push_back(std::move(p));
        if (out.packets.size() > maxPackets) { out.error = "too many packets in a segment"; return false; }
    }
    if (out.packets.empty()) { out.error = "fMP4 segment without samples"; return false; }
    return true;
}

bool decryptAes128(std::vector<uint8_t>& data, const uint8_t key[16], const uint8_t iv[16])
{
    if (data.empty() || data.size() % 16) return false;
    AVAES* aes = av_aes_alloc();
    if (!aes || av_aes_init(aes, key, 128, 1) < 0) { av_free(aes); return false; }
    uint8_t chain[16];
    memcpy(chain, iv, 16);
    av_aes_crypt(aes, data.data(), data.data(), int(data.size() / 16), chain, 1);
    av_free(aes);
    const uint8_t pad = data.back();
    if (!pad || pad > 16 || pad > data.size()) return false;
    for (size_t i = data.size() - pad; i < data.size(); i++) if (data[i] != pad) return false;
    data.resize(data.size() - pad);
    return true;
}

}
