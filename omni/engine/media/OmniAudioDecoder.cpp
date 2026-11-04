// SPDX-License-Identifier: GPL-3.0-or-later
#include "OmniAudioDecoder.h"
#include <algorithm>
#include <chrono>
#include <cstring>
extern "C" {
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <libswresample/swresample.h>
}
namespace OmniMedia {
struct AudioDecoder::State {
    std::vector<uint8_t> bytes;
    size_t position = 0;
    AVFormatContext* format = nullptr;
    AVIOContext* io = nullptr;
    AVCodecContext* codec = nullptr;
    AVPacket* packet = nullptr;
    AVFrame* frame = nullptr;
    SwrContext* resampler = nullptr;
    AVChannelLayout layout {};
    int rate = 0, sampleFormat = -1;
    bool draining = false, finished = false, clockStarted = false;
    double clock = 0;
    std::string failure;
    std::chrono::steady_clock::time_point deadline;
    ~State() { releaseResources(); }
    void releaseResources() {
        swr_free(&resampler); av_channel_layout_uninit(&layout);
        av_frame_free(&frame); av_packet_free(&packet);
        avcodec_free_context(&codec); avformat_close_input(&format);
        if (io) { av_freep(&io->buffer); avio_context_free(&io); }
        std::vector<uint8_t>().swap(bytes);
        position = 0;
    }
    // All callers are outside FFmpeg callbacks, after the active operation
    // returns. A retained failed decoder must not pin its input/codec storage.
    bool fail(const char* text) { failure = text; releaseResources(); return false; }
    void resetDeadline() { deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3); }
    static int interrupted(void* p) { return std::chrono::steady_clock::now() >= static_cast<State*>(p)->deadline; }
    static int denyOpen(AVFormatContext*, AVIOContext**, const char*, int, AVDictionary**) { return AVERROR(EACCES); }
    static int read(void* p, uint8_t* out, int requested) {
        auto& s = *static_cast<State*>(p);
        if (requested <= 0) return AVERROR(EINVAL);
        if (s.position == s.bytes.size()) return AVERROR_EOF;
        size_t n = std::min(size_t(requested), s.bytes.size() - s.position);
        memcpy(out, s.bytes.data() + s.position, n); s.position += n; return int(n);
    }
    static int64_t seek(void* p, int64_t offset, int whence) {
        auto& s = *static_cast<State*>(p);
        if (whence == AVSEEK_SIZE) return int64_t(s.bytes.size());
        whence &= ~AVSEEK_FORCE;
        int64_t base = whence == SEEK_SET ? 0 : whence == SEEK_CUR ? int64_t(s.position)
            : whence == SEEK_END ? int64_t(s.bytes.size()) : -1;
        if (base < 0 || offset < -base || offset > int64_t(s.bytes.size()) - base) return AVERROR(EINVAL);
        s.position = size_t(base + offset); return int64_t(s.position);
    }
};
AudioDecoder::AudioDecoder() : state(std::make_unique<State>()) { }
AudioDecoder::~AudioDecoder() = default;
const std::string& AudioDecoder::error() const { return state->failure; }
bool AudioDecoder::open(std::vector<uint8_t> bytes) {
    state = std::make_unique<State>(); auto& s = *state;
    if (bytes.empty() || bytes.size() > maxInputBytes) return s.fail("Audio input size limit");
    s.bytes = std::move(bytes);
    auto* buffer = static_cast<uint8_t*>(av_malloc(32768));
    if (!buffer) return s.fail("Audio IO allocation failed");
    s.io = avio_alloc_context(buffer, 32768, 0, &s, State::read, nullptr, State::seek);
    if (!s.io) { av_free(buffer); return s.fail("Audio IO creation failed"); }
    s.format = avformat_alloc_context();
    if (!s.format) return s.fail("Audio format allocation failed");
    s.format->pb = s.io; s.format->flags |= AVFMT_FLAG_CUSTOM_IO;
    s.format->io_open = State::denyOpen; s.format->interrupt_callback = { State::interrupted, &s };
    s.format->probesize = 1024 * 1024; s.format->max_analyze_duration = 3 * AV_TIME_BASE;
    s.format->max_streams = 1;
    AVDictionary* options = nullptr;
    av_dict_set(&options, "format_whitelist", "mov,matroska,webm", 0);
    av_dict_set(&options, "codec_whitelist", "aac,opus,vorbis,mp3", 0);
    av_dict_set(&options, "protocol_whitelist", "", 0);
    s.resetDeadline();
    int rc = avformat_open_input(&s.format, nullptr, nullptr, &options);
    av_dict_free(&options);
    if (rc < 0) return s.fail("Unsupported audio container");
    // These supported containers declare their track before probing. Reject
    // video/multiple tracks before stream probing can allocate a video decoder.
    if (s.format->nb_streams != 1 || s.format->streams[0]->codecpar->codec_type != AVMEDIA_TYPE_AUDIO)
        return s.fail("Exactly one audio track required");
    av_dict_set(&options, "max_samples", "131072", 0);
    av_dict_set(&options, "threads", "1", 0);
    rc = avformat_find_stream_info(s.format, &options); av_dict_free(&options);
    if (rc < 0 || s.format->nb_streams != 1) return s.fail("Invalid audio stream information");
    auto* p = s.format->streams[0]->codecpar;
    if (p->sample_rate < 8000 || p->sample_rate > 192000 || p->ch_layout.nb_channels < 1 || p->ch_layout.nb_channels > 8)
        return s.fail("Unsupported audio dimensions");
    if (p->codec_id != AV_CODEC_ID_AAC && p->codec_id != AV_CODEC_ID_OPUS
        && p->codec_id != AV_CODEC_ID_VORBIS && p->codec_id != AV_CODEC_ID_MP3)
        return s.fail("Unsupported audio codec");
    auto* decoder = avcodec_find_decoder(p->codec_id);
    if (!decoder) return s.fail("Audio decoder unavailable");
    s.codec = avcodec_alloc_context3(decoder);
    if (!s.codec || avcodec_parameters_to_context(s.codec, p) < 0) return s.fail("Audio context failed");
    s.codec->thread_count = 1; s.codec->max_samples = 131072;
    if (avcodec_open2(s.codec, decoder, nullptr) < 0) return s.fail("Audio decoder initialization failed");
    s.frame = av_frame_alloc(); s.packet = av_packet_alloc();
    if (!s.frame || !s.packet) return s.fail("Audio frame allocation failed");
    return true;
}
AudioDecoder::Result AudioDecoder::next(AudioChunk& out) {
    out.samples.clear(); out.seconds = 0;
    auto& s = *state;
    auto fail = [&](const char* text) { s.fail(text); out.samples.clear(); return Result::Error; };
    if (!s.codec || !s.failure.empty()) return Result::Error;
    if (s.finished) return Result::End;
    s.resetDeadline();
    for (int budget = 0; budget < 256; ++budget) {
        if (State::interrupted(&s)) return fail("Audio decode time limit");
        int rc = avcodec_receive_frame(s.codec, s.frame);
        if (rc == 0 || rc == AVERROR_EOF) {
            bool flush = rc == AVERROR_EOF;
            if (flush && !s.resampler) { s.finished = true; return Result::End; }
            if (!flush) {
                auto* f = s.frame;
                if (f->sample_rate < 8000 || f->sample_rate > 192000 || f->ch_layout.nb_channels < 1
                    || f->ch_layout.nb_channels > 8 || f->nb_samples <= 0 || f->nb_samples > 16384)
                    return fail("Audio frame dimensions exceed limit");
                if (!s.resampler) {
                    s.rate = f->sample_rate; s.sampleFormat = f->format;
                    AVChannelLayout stereo = AV_CHANNEL_LAYOUT_STEREO;
                    if (av_channel_layout_copy(&s.layout, &f->ch_layout) < 0
                        || swr_alloc_set_opts2(&s.resampler, &stereo, AV_SAMPLE_FMT_S16, 48000,
                            &f->ch_layout, AVSampleFormat(f->format), f->sample_rate, 0, nullptr) < 0
                        || swr_init(s.resampler) < 0) return fail("Audio resampler initialization failed");
                } else if (s.rate != f->sample_rate || s.sampleFormat != f->format
                    || av_channel_layout_compare(&s.layout, &f->ch_layout)) return fail("Audio format changed");
                double delay = double(swr_get_delay(s.resampler, s.rate)) / s.rate;
                if (f->best_effort_timestamp != AV_NOPTS_VALUE) {
                    s.clock = f->best_effort_timestamp * av_q2d(s.format->streams[0]->time_base) - delay;
                    s.clockStarted = true;
                } else if (!s.clockStarted) { s.clock = 0; s.clockStarted = true; }
            }
            int capacity = swr_get_out_samples(s.resampler, flush ? 0 : s.frame->nb_samples);
            if (capacity < 0 || capacity > maxChunkFrames) return fail("Audio output size limit");
            out.samples.resize(size_t(capacity) * 2);
            uint8_t* planes[] = { reinterpret_cast<uint8_t*>(out.samples.data()) };
            int n = swr_convert(s.resampler, planes, capacity,
                flush ? nullptr : const_cast<const uint8_t**>(s.frame->extended_data), flush ? 0 : s.frame->nb_samples);
            if (!flush) av_frame_unref(s.frame);
            if (n < 0) return fail("Audio conversion failed");
            out.samples.resize(size_t(n) * 2); out.seconds = s.clock; s.clock += double(n) / 48000;
            if (n) return Result::Chunk;
            if (flush) { s.finished = true; return Result::End; }
            continue;
        }
        if (rc != AVERROR(EAGAIN)) return fail("Audio decode failed");
        if (s.draining) return fail("Audio decoder requested input after drain");
        rc = av_read_frame(s.format, s.packet);
        if (rc == AVERROR_EOF) {
            if (avcodec_send_packet(s.codec, nullptr) < 0) return fail("Audio drain failed");
            s.draining = true; continue;
        }
        if (rc < 0) return fail("Audio packet read failed");
        if (s.packet->stream_index != 0) { av_packet_unref(s.packet); return fail("Unexpected audio track"); }
        rc = avcodec_send_packet(s.codec, s.packet); av_packet_unref(s.packet);
        if (rc < 0) return fail("Audio packet decode failed");
    }
    return Result::Again;
}
}
