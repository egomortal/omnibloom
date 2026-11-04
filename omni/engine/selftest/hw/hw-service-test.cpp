// Two-process host test of hardware decoding: a forked service process runs the
// real OmniHwService + OmniHwBackend against the FFmpeg-backed libSceVideodec2
// stand-in; this process is the "WebProcess" using PacketDecoder / Hw::Client
// with the real fd hand-off (pidfd_getfd stands in for syscall 0x25b).
// SPDX-License-Identifier: GPL-3.0-or-later
#include "../../media/OmniHwClient.h"
#include "../../media/OmniHwService.h"
#include "../../media/OmniPacketDecoder.h"
#include "../../media/OmniMP4Demuxer.h"
#include <cassert>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>
extern "C" {
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <libswscale/swscale.h>
}
using namespace OmniMedia;

static std::vector<uint8_t> readFile(const std::string& p) {
    std::ifstream f(p, std::ios::binary); assert(f); return { std::istreambuf_iterator<char>(f), {} };
}

struct Out { int64_t ts; bool hidden; std::vector<uint8_t> rgba; };

// ---- service process ------------------------------------------------------
static pid_t startService(const char* mockFail) {
    std::string dir = getenv("OMNI_HW_DIR");
    unlink((dir + "/service").c_str());
    pid_t pid = fork();
    if (!pid) {
        if (mockFail) setenv("MOCK_FAIL", mockFail, 1); else unsetenv("MOCK_FAIL");
        std::string detail;
        if (!Hw::serviceStart(detail)) { fprintf(stderr, "service start failed: %s\n", detail.c_str()); _exit(3); }
        for (;;) pause();
    }
    for (int i = 0; i < 200 && access((dir + "/service").c_str(), F_OK); i++) usleep(10000);
    assert(!access((dir + "/service").c_str(), F_OK));
    return pid;
}
static void stopService(pid_t pid) { kill(pid, SIGKILL); waitpid(pid, nullptr, 0); }

// ---- MSE-style decode through PacketDecoder (what OmniMSESource does) -----
struct Run { std::vector<Out> outs; bool hardware = false; };
static Run decodeFixture(const std::string& root, int id, int segments, bool hw, int flushAfter = -1, pid_t killService = 0, int killAfter = -1, int targetW = 0, int targetH = 0) {
    setenv("OMNI_HW_DECODE", hw ? "1" : "0", 1);
    auto init = readFile(root + "/init-" + std::to_string(id) + ".mp4");
    std::vector<DemuxPacket> packets; DemuxTrack track;
    for (int s = 1; s <= segments; s++) {
        MP4DemuxResult r;
        assert(demuxMP4Fragment(init, readFile(root + "/segment-" + std::to_string(id) + "-0000" + std::to_string(s) + ".m4s"), r));
        if (s == 1) track = r.tracks[0];
        for (auto& p : r.packets) packets.push_back(std::move(p));
    }
    // Mark a few packets decode-only, as MSE preroll after a seek would.
    for (size_t i = 3; i < 6 && i < packets.size(); i++) packets[i].nonDisplaying = true;
    PacketDecoder d; d.setVideoPixelOrder(PacketDecoder::PixelOrder::BGRA);
    d.setVideoTargetSize(targetW, targetH); // OMNI_VIDEO_TARGET_V1
    assert(d.configure(track));
    Run run; run.hardware = d.usingHardware();
    auto pull = [&] {
        for (;;) {
            DecodedOutput o; auto r = d.receive(o);
            if (r == PacketDecoder::Receive::Error) { fprintf(stderr, "receive error: %s\n", d.error().c_str()); assert(false); }
            if (r != PacketDecoder::Receive::Output) return r;
            assert(o.kind == DecodedOutput::Kind::Video && o.bgra && o.rgba.size() == size_t(o.width) * o.height * 4);
            if (targetW) assert(o.width == targetW && o.height == targetH && o.sourceWidth == track.width && o.sourceHeight == track.height); // OMNI_VIDEO_TARGET_V1
            run.outs.push_back({ o.timestamp, o.nonDisplaying, std::move(o.rgba) });
        }
    };
    for (size_t i = 0; i < packets.size(); i++) {
        if (int(i) == killAfter && killService) stopService(killService);
        if (int(i) == flushAfter) {
            d.flush(); run.outs.clear();
            // Resume from the next keyframe, as a seek does.
            while (i < packets.size() && !packets[i].keyFrame) i++;
            if (i == packets.size()) break;
        }
        for (int spin = 0;; spin++) {
            auto s = d.submit(packets[i]);
            assert(s != PacketDecoder::Submit::Error);
            if (s == PacketDecoder::Submit::Accepted) break;
            pull(); usleep(200);
            assert(spin < 100000);
        }
        pull();
    }
    for (int spin = 0; d.drain() == PacketDecoder::Submit::NeedOutput; spin++) { pull(); usleep(200); assert(spin < 100000); }
    for (int spin = 0; pull() != PacketDecoder::Receive::End; spin++) { usleep(200); assert(spin < 100000); }
    return run;
}

static int maxDiff(const std::vector<uint8_t>& a, const std::vector<uint8_t>& b) {
    if (a.size() != b.size()) return 999;
    int m = 0; for (size_t i = 0; i < a.size(); i++) m = std::max(m, std::abs(int(a[i]) - int(b[i])));
    return m;
}
static void compare(const char* name, const Run& hw, const Run& sw, bool expectHardware, size_t allowMissing = 0) {
    assert(hw.hardware == expectHardware);
    if (hw.outs.size() + allowMissing < sw.outs.size() || hw.outs.size() > sw.outs.size()) {
        fprintf(stderr, "%s: %zu vs %zu outputs\n", name, hw.outs.size(), sw.outs.size()); assert(false);
    }
    // Match by timestamp: after a fallback, frames between the failure and the
    // next keyframe are legitimately missing; everything present must agree.
    int worst = 0; unsigned exact = 0; size_t j = 0;
    for (size_t i = 0; i < hw.outs.size(); i++) {
        const auto& h = hw.outs[i];
        while (j < sw.outs.size() && sw.outs[j].ts != h.ts) j++;
        if (j == sw.outs.size()) { fprintf(stderr, "%s: hw frame %zu ts %lld not in software output (or out of order)\n", name, i, (long long)h.ts); assert(false); }
        const auto& s = sw.outs[j++];
        if (h.hidden != s.hidden) { fprintf(stderr, "%s: frame %zu preroll flag %d/%d\n", name, i, h.hidden, s.hidden); assert(false); }
        int d = maxDiff(h.rgba, s.rgba); worst = std::max(worst, d); exact += d == 0;
    }
    assert(worst <= 2);   // NV12 vs planar 4:2:0 input to swscale may round differently
    printf("OK %-34s %zu frames (%s), timestamps+preroll flags identical, %u bit-identical, max pixel diff %d\n",
           name, hw.outs.size(), expectHardware ? "hardware" : "software", exact, worst);
}

// ---- Hw::Client directly for HEVC / VP9 (not yet routed through MSE) -----
static void clientCodec(const char* path, Hw::Codec codec) {
    setenv("OMNI_HW_DECODE", "1", 1);
    AVFormatContext* fmt = nullptr; assert(avformat_open_input(&fmt, path, nullptr, nullptr) == 0);
    assert(avformat_find_stream_info(fmt, nullptr) >= 0);
    int si = av_find_best_stream(fmt, AVMEDIA_TYPE_VIDEO, -1, -1, nullptr, 0);
    AVStream* st = fmt->streams[si];
    DemuxTrack track; track.width = st->codecpar->width; track.height = st->codecpar->height;
    track.timeBase = { st->time_base.num, st->time_base.den };
    track.extraData.assign(st->codecpar->extradata, st->codecpar->extradata + st->codecpar->extradata_size);
    Hw::Client c; assert(c.configure(codec, track, false));
    // Reference: FFmpeg on the original packets, converted to RGBA.
    const AVCodec* k = avcodec_find_decoder(st->codecpar->codec_id);
    AVCodecContext* ref = avcodec_alloc_context3(k); avcodec_parameters_to_context(ref, st->codecpar);
    ref->thread_count = 1; assert(avcodec_open2(ref, k, nullptr) == 0);
    AVFrame* f = av_frame_alloc(); SwsContext* sws = nullptr; std::vector<std::vector<uint8_t>> refFrames;
    auto refPull = [&] { while (avcodec_receive_frame(ref, f) == 0) {
        sws = sws_getCachedContext(sws, f->width, f->height, AVPixelFormat(f->format), f->width, f->height, AV_PIX_FMT_RGBA, SWS_BILINEAR, 0, 0, 0);
        std::vector<uint8_t> o(size_t(f->width) * f->height * 4); uint8_t* dst[4] = { o.data() }; int ds[4] = { f->width * 4 };
        sws_scale(sws, f->data, f->linesize, 0, f->height, dst, ds); refFrames.push_back(std::move(o)); av_frame_unref(f); } };
    std::vector<std::vector<uint8_t>> got; DecodedOutput o;
    auto pull = [&] { for (;;) { auto r = c.receive(o); assert(r != Hw::Client::Receive::Error); if (r != Hw::Client::Receive::Output) return r; got.push_back(o.rgba); } };
    AVPacket* pk = av_packet_alloc();
    while (av_read_frame(fmt, pk) == 0) {
        if (pk->stream_index == si) {
            AVPacket* rp = av_packet_clone(pk); avcodec_send_packet(ref, rp); av_packet_free(&rp); refPull();
            DemuxPacket dp; dp.pts = pk->pts; dp.dts = pk->dts; dp.timeBase = track.timeBase; dp.keyFrame = pk->flags & AV_PKT_FLAG_KEY;
            dp.bytes.assign(pk->data, pk->data + pk->size);
            for (int spin = 0;; spin++) { auto s = c.submit(dp); assert(s != Hw::Client::Submit::Error); if (s == Hw::Client::Submit::Accepted) break; pull(); usleep(200); assert(spin < 100000); }
            pull();
        }
        av_packet_unref(pk);
    }
    avcodec_send_packet(ref, nullptr); refPull();
    assert(c.drain() == Hw::Client::Submit::Accepted);
    for (int spin = 0; pull() != Hw::Client::Receive::End; spin++) { usleep(200); assert(spin < 100000); }
    assert(got.size() == refFrames.size());
    int worst = 0; for (size_t i = 0; i < got.size(); i++) worst = std::max(worst, maxDiff(got[i], refFrames[i]));
    assert(worst <= 2);
    printf("OK %-34s %zu frames via service, max pixel diff %d\n", path, got.size(), worst);
    av_packet_free(&pk); av_frame_free(&f); avcodec_free_context(&ref); sws_freeContext(sws); avformat_close_input(&fmt);
}

int main(int argc, char** argv) {
    assert(argc >= 3);
    const std::string mse = argv[1], bframes = argv[2];
    signal(SIGPIPE, SIG_IGN);
    setvbuf(stdout, nullptr, _IOLBF, 0);
    Run swA = decodeFixture(mse, 0, 4, false), swB = decodeFixture(bframes, 0, 1, false);

    pid_t svc = startService(nullptr);
    compare("H.264 MSE fixture", decodeFixture(mse, 0, 4, true), swA, true);
    compare("H.264 B-frames fixture", decodeFixture(bframes, 0, 1, true), swB, true);
    // Seek: flush mid-stream and resume at a keyframe, both paths.
    compare("H.264 flush + resume at keyframe", decodeFixture(mse, 0, 4, true, 40), decodeFixture(mse, 0, 4, false, 40), true);
    // OMNI_VIDEO_TARGET_V1: converted straight to the shown size, up and down.
    compare("H.264 target 1920x1080 (one pass)", decodeFixture(mse, 0, 4, true, -1, 0, -1, 1920, 1080), decodeFixture(mse, 0, 4, false, -1, 0, -1, 1920, 1080), true);
    compare("H.264 target 160x90 (one pass)", decodeFixture(mse, 0, 4, true, -1, 0, -1, 160, 90), decodeFixture(mse, 0, 4, false, -1, 0, -1, 160, 90), true);
    for (int i = 3; i < argc; i++) clientCodec(argv[i], strstr(argv[i], "vp9") ? Hw::Codec::VP9 : Hw::Codec::HEVC);
    // A dead client frees its channel: run more streams than channels exist.
    for (int i = 0; i < 6; i++) { pid_t p = fork(); if (!p) { decodeFixture(mse, 0, 1, true); _exit(0); } int st; waitpid(p, &st, 0); assert(WIFEXITED(st) && !WEXITSTATUS(st)); }
    printf("OK channel recycling: 6 client processes in sequence over %u channels\n", 4u);
    stopService(svc);

    // Fault injection: every failure must end in correct software output.
    svc = startService("create");
    compare("fault: decoder refused at create", decodeFixture(mse, 0, 4, true), swA, false);
    stopService(svc);
    svc = startService("decode@30");
    { Run r = decodeFixture(mse, 0, 4, true); compare("fault: decode error after 30 AUs", r, swA, true, 60); }
    stopService(svc);
    svc = startService("hang@20");
    { Run r = decodeFixture(mse, 0, 4, true); compare("fault: decoder hang at AU 20", r, swA, true, 60); }
    stopService(svc);
    svc = startService(nullptr);
    { Run r = decodeFixture(mse, 0, 4, true, -1, svc, 25); compare("fault: service killed mid-stream", r, swA, true, 60); }
    { Run r = decodeFixture(mse, 0, 4, true); compare("no service: software only", r, swA, false); }
    printf("PASS hw-service-test\n");
}
