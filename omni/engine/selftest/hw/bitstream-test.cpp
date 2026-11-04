// Host test for OmniHwBitstream: MP4 (avcC/hvcC) -> Annex-B and VP9 splitting
// must decode bit-identically to FFmpeg decoding the original container, and
// the parsers must survive corrupted input. SPDX-License-Identifier: GPL-3.0-or-later
#include "../../media/OmniHwBitstream.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <random>
#include <string>
#include <vector>
extern "C" {
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
}
using namespace OmniMedia::Hw;
static uint64_t fnv(uint64_t x, const uint8_t* p, size_t n) { for (size_t i = 0; i < n; i++) { x ^= p[i]; x *= 0x100000001b3ULL; } return x; }
static uint64_t frameHash(const AVFrame* f) {
    uint64_t x = 0xcbf29ce484222325ULL;
    int bps = f->format == AV_PIX_FMT_YUV420P10LE ? 2 : 1;
    for (int pl = 0; pl < 3; pl++) {
        int w = (pl ? f->width / 2 : f->width) * bps, h = pl ? f->height / 2 : f->height;
        for (int y = 0; y < h; y++) x = fnv(x, f->data[pl] + (size_t)f->linesize[pl] * y, (size_t)w);
    }
    return x;
}
struct Decoder {
    AVCodecContext* c = nullptr; AVFrame* f = av_frame_alloc(); std::vector<uint64_t> hashes;
    explicit Decoder(AVCodecID id, const AVCodecParameters* par = nullptr) {
        const AVCodec* k = avcodec_find_decoder(id); c = avcodec_alloc_context3(k);
        if (par) avcodec_parameters_to_context(c, par);
        c->thread_count = 1; assert(avcodec_open2(c, k, nullptr) == 0);
    }
    void send(const uint8_t* d, size_t n) {
        AVPacket* p = av_packet_alloc();
        if (d) { assert(av_new_packet(p, (int)n) == 0); memcpy(p->data, d, n); }
        int r = avcodec_send_packet(c, d ? p : nullptr); assert(r == 0 || r == AVERROR_EOF);
        av_packet_free(&p);
        while (avcodec_receive_frame(c, f) == 0) { hashes.push_back(frameHash(f)); av_frame_unref(f); }
    }
    ~Decoder() { avcodec_free_context(&c); av_frame_free(&f); }
};
static void checkFile(const char* path) {
    AVFormatContext* fmt = nullptr;
    assert(avformat_open_input(&fmt, path, nullptr, nullptr) == 0);
    assert(avformat_find_stream_info(fmt, nullptr) >= 0);
    int si = av_find_best_stream(fmt, AVMEDIA_TYPE_VIDEO, -1, -1, nullptr, 0); assert(si >= 0);
    const AVCodecParameters* par = fmt->streams[si]->codecpar;
    Codec codec = par->codec_id == AV_CODEC_ID_H264 ? Codec::H264 : par->codec_id == AV_CODEC_ID_HEVC ? Codec::HEVC : Codec::VP9;
    Decoder reference(par->codec_id, par);        // FFmpeg on the original samples + extradata
    Decoder adapted(par->codec_id);               // FFmpeg on exactly what the hardware would receive
    NalConfig cfg; std::string err;
    if (codec == Codec::H264) assert(parseAvcC(par->extradata, (size_t)par->extradata_size, cfg, err));
    if (codec == Codec::HEVC) assert(parseHvcC(par->extradata, (size_t)par->extradata_size, cfg, err));
    AVPacket* pk = av_packet_alloc(); std::vector<uint8_t> annexb; unsigned packets = 0, hidden = 0, keyframes = 0;
    while (av_read_frame(fmt, pk) == 0) {
        if (pk->stream_index == si) {
            reference.send(pk->data, (size_t)pk->size);
            if (codec == Codec::VP9) {
                std::vector<Vp9Frame> frames; assert(splitVp9(pk->data, (size_t)pk->size, frames, err));
                for (auto& fr : frames) { hidden += !fr.shown; adapted.send(pk->data + fr.offset, fr.size); }
            } else {
                bool key = pk->flags & AV_PKT_FLAG_KEY; keyframes += key;
                assert(lengthPrefixedToAnnexB(codec, cfg, pk->data, (size_t)pk->size, key, annexb, err));
                assert(looksLikeAnnexB(annexb.data(), annexb.size()));
                adapted.send(annexb.data(), annexb.size());
            }
            packets++;
        }
        av_packet_unref(pk);
    }
    reference.send(nullptr, 0); adapted.send(nullptr, 0);
    av_packet_free(&pk); avformat_close_input(&fmt);
    assert(!reference.hashes.empty());
    if (codec == Codec::VP9) assert(hidden > 0); // the split + hidden path must really be exercised
    if (reference.hashes != adapted.hashes) { fprintf(stderr, "FAIL %s: %zu vs %zu frames\n", path, reference.hashes.size(), adapted.hashes.size()); assert(false); }
    printf("OK %s: %u packets, %zu frames identical, keyframes=%u hidden=%u profile=%d level=%d depth=%d\n",
           path, packets, reference.hashes.size(), keyframes, hidden, cfg.profile, cfg.level, cfg.bitDepth);
}
static void fuzz() {
    std::mt19937 rng(1234); std::string err; NalConfig cfg; std::vector<uint8_t> out; std::vector<Vp9Frame> fr;
    cfg.lengthSize = 4; cfg.parameterSets = { 0, 0, 0, 1, 0x67, 1 };
    for (int i = 0; i < 200000; i++) {
        std::vector<uint8_t> b(rng() % 64); for (auto& x : b) x = (uint8_t)rng();
        parseAvcC(b.data(), b.size(), cfg, err); parseHvcC(b.data(), b.size(), cfg, err);
        cfg.lengthSize = 1 + (int)(rng() % 2) * (1 + (int)(rng() % 2) * 2); // 1, 2 or 4
        lengthPrefixedToAnnexB(i & 1 ? Codec::H264 : Codec::HEVC, cfg, b.data(), b.size(), rng() & 1, out, err);
        splitVp9(b.data(), b.size(), fr, err);
    }
    // explicit edge cases
    assert(!parseAvcC(nullptr, 0, cfg, err)); assert(!splitVp9(nullptr, 0, fr, err));
    uint8_t bad[] = { 0, 0, 0, 9, 0x65 }; cfg.lengthSize = 4;
    assert(!lengthPrefixedToAnnexB(Codec::H264, cfg, bad, sizeof bad, true, out, err));
    printf("OK fuzz: 200000 random inputs, no crash\n");
}
int main(int argc, char** argv) { for (int i = 1; i < argc; i++) checkFile(argv[i]); fuzz(); }
