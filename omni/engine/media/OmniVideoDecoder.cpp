// SPDX-License-Identifier: GPL-3.0-or-later
#include "OmniVideoDecoder.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <limits>
extern "C" {
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <libswscale/swscale.h>
#include <libswresample/swresample.h>
#include <libavutil/opt.h>
}

namespace OmniMedia {
struct VideoDecoder::State {
    std::vector<uint8_t> bytes;
    size_t position = 0;
    std::shared_ptr<ByteSource> source; // OMNI_PROGRESSIVE_V1: read as it goes (instead of `bytes`)
    int64_t sourcePosition = 0;
    AVFormatContext* format = nullptr;
    AVIOContext* io = nullptr;
    AVCodecContext* codec = nullptr;
    AVCodecContext* audioCodec = nullptr;
    AVFrame* audioFrame = nullptr;
    SwrContext* resampler = nullptr;
    int audioStream = -1;
    std::vector<int16_t> pcm;
    AVPacket* packet = nullptr;
    AVFrame* frame = nullptr;
    SwsContext* scale = nullptr;
    int stream = -1;
    bool draining = false, audio = false;
    bool wantPackets = false, packets = false; // OMNI_PROGRESSIVE_HOLEPUNCH_V1
    DemuxTrack track;                           // OMNI_PROGRESSIVE_HOLEPUNCH_V1 (packet mode)
    double length = 0;
    double videoDiscardBefore = -1, audioDiscardBefore = -1;
    std::string failure;
    std::chrono::steady_clock::time_point deadline;
    ~State() {
        sws_freeContext(scale);
        swr_free(&resampler);
        av_frame_free(&audioFrame);
        avcodec_free_context(&audioCodec);
        av_frame_free(&frame);
        av_packet_free(&packet);
        avcodec_free_context(&codec);
        avformat_close_input(&format);
        if (io) { av_freep(&io->buffer); avio_context_free(&io); }
    }
    bool fail(const char* reason) { failure = reason; return false; }
    void resetDeadline() { deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3); }
    static int interrupted(void* opaque) {
        return std::chrono::steady_clock::now() >= static_cast<State*>(opaque)->deadline;
    }
    static int read(void* opaque, uint8_t* buffer, int requested) {
        auto& self = *static_cast<State*>(opaque);
        if (requested <= 0) return AVERROR(EINVAL);
        if (self.position == self.bytes.size()) return AVERROR_EOF;
        size_t count = std::min(size_t(requested), self.bytes.size() - self.position);
        memcpy(buffer, self.bytes.data() + self.position, count);
        self.position += count;
        return int(count);
    }
    static int64_t seek(void* opaque, int64_t offset, int whence) {
        auto& self = *static_cast<State*>(opaque);
        if (whence == AVSEEK_SIZE) return int64_t(self.bytes.size());
        whence &= ~AVSEEK_FORCE;
        int64_t base = whence == SEEK_SET ? 0 : whence == SEEK_CUR ? int64_t(self.position)
            : whence == SEEK_END ? int64_t(self.bytes.size()) : -1;
        // Subtraction bounds avoid overflow from a malicious seek offset.
        if (base < 0 || offset < -base || offset > int64_t(self.bytes.size()) - base) return AVERROR(EINVAL);
        self.position = size_t(base + offset);
        return int64_t(self.position);
    }
    // OMNI_PROGRESSIVE_V1: the ByteSource variants; time spent waiting for the network moves the
    // decode deadline on (it bounds decoding work, not downloads).
    static int readSource(void* opaque, uint8_t* buffer, int requested) {
        auto& self = *static_cast<State*>(opaque);
        if (requested <= 0) return AVERROR(EINVAL);
        double waited = 0;
        const int count = self.source->read(self.sourcePosition, buffer, requested, waited);
        if (waited > 0) self.deadline += std::chrono::duration_cast<std::chrono::steady_clock::duration>(std::chrono::duration<double>(waited));
        if (count < 0) return AVERROR(EIO);
        if (count == 0) return AVERROR_EOF;
        self.sourcePosition += count;
        return count;
    }
    static int64_t seekSource(void* opaque, int64_t offset, int whence) {
        auto& self = *static_cast<State*>(opaque);
        const int64_t size = self.source->size();
        if (whence == AVSEEK_SIZE) return size >= 0 ? size : AVERROR(ENOSYS);
        whence &= ~AVSEEK_FORCE;
        int64_t base = whence == SEEK_SET ? 0 : whence == SEEK_CUR ? self.sourcePosition : whence == SEEK_END && size >= 0 ? size : -1;
        if (base < 0 || offset < -base || (size >= 0 && offset > size - base)) return AVERROR(EINVAL);
        self.sourcePosition = base + offset;
        return self.sourcePosition;
    }
    static int denyOpen(AVFormatContext*, AVIOContext**, const char*, int, AVDictionary**) {
        return AVERROR(EACCES); // No external files, URLs, playlists or nested IO.
    }
    bool decodeAudio(AVPacket* input) {
        if (!audioCodec) return true;
        if (avcodec_send_packet(audioCodec, input) < 0) return fail("Audio packet decode failed");
        for (;;) {
            int result = avcodec_receive_frame(audioCodec, audioFrame);
            if (result == AVERROR(EAGAIN) || result == AVERROR_EOF) return true;
            if (result < 0) return fail("Audio frame decode failed");
            int rate = audioFrame->sample_rate, channels = audioFrame->ch_layout.nb_channels;
            if (rate < 8000 || rate > 192000 || channels < 1 || channels > 8
                || audioFrame->nb_samples <= 0 || audioFrame->nb_samples > 16384)
                return fail("Unsupported audio dimensions");
            double audioTime = audioFrame->best_effort_timestamp == AV_NOPTS_VALUE ? -1
                : audioFrame->best_effort_timestamp * av_q2d(format->streams[audioStream]->time_base);
            if (audioDiscardBefore >= 0 && (audioTime < 0 || audioTime + double(audioFrame->nb_samples) / rate <= audioDiscardBefore)) {
                av_frame_unref(audioFrame); continue;
            }
            if (!resampler) {
                AVChannelLayout stereo = AV_CHANNEL_LAYOUT_STEREO;
                if (swr_alloc_set_opts2(&resampler, &stereo, AV_SAMPLE_FMT_S16, 48000,
                    &audioFrame->ch_layout, AVSampleFormat(audioFrame->format), rate, 0, nullptr) < 0
                    || swr_init(resampler) < 0) return fail("Audio resampler initialization failed");
            }
            if (rate != audioCodec->sample_rate || channels != audioCodec->ch_layout.nb_channels
                || audioFrame->format != audioCodec->sample_fmt) return fail("Audio format changed unexpectedly");
            int64_t delay = swr_get_delay(resampler, rate);
            int64_t samples = av_rescale_rnd(delay + audioFrame->nb_samples, 48000, rate, AV_ROUND_UP);
            if (samples < 0 || samples > 32768 || pcm.size() + samples * 2 > 96000)
                return fail("Audio buffer limit exceeded");
            size_t offset = pcm.size(); pcm.resize(offset + samples * 2);
            uint8_t* planes[] = {reinterpret_cast<uint8_t*>(pcm.data() + offset)};
            int converted = swr_convert(resampler, planes, int(samples), const_cast<const uint8_t**>(audioFrame->extended_data), audioFrame->nb_samples);
            if (converted < 0) return fail("Audio conversion failed");
            if (audioDiscardBefore >= 0) {
                int skip = int(std::clamp((audioDiscardBefore - audioTime) * 48000.0, 0.0, double(converted)));
                memmove(pcm.data() + offset, pcm.data() + offset + skip * 2, (converted - skip) * 2 * sizeof(int16_t));
                converted -= skip;
                audioDiscardBefore = -1;
            }
            pcm.resize(offset + converted * 2);
            av_frame_unref(audioFrame);
        }
    }
};
VideoDecoder::VideoDecoder() : state(std::make_unique<State>()) { }
VideoDecoder::~VideoDecoder() = default;
const std::string& VideoDecoder::error() const { return state->failure; }
double VideoDecoder::duration() const { return state->length; }
bool VideoDecoder::hasAudio() const { return state->audio; }
bool VideoDecoder::packetMode() const { return state->packets; } // OMNI_PROGRESSIVE_HOLEPUNCH_V1
const DemuxTrack& VideoDecoder::videoTrack() const { return state->track; }
std::vector<int16_t> VideoDecoder::takeAudio() { std::vector<int16_t> result; result.swap(state->pcm); return result; }

bool VideoDecoder::open(std::vector<uint8_t> bytes) {
    state = std::make_unique<State>();
    auto& s = *state;
    if (bytes.empty() || bytes.size() > maxInputBytes) return s.fail("Media exceeds the bounded input size");
    s.bytes = std::move(bytes);
    return openStreams();
}
// OMNI_PROGRESSIVE_V1: the same, reading from a ByteSource as it goes.
bool VideoDecoder::openSource(std::shared_ptr<ByteSource> source) {
    state = std::make_unique<State>();
    auto& s = *state;
    if (!source) return s.fail("No media source");
    s.source = std::move(source);
    return openStreams();
}
// OMNI_PROGRESSIVE_HOLEPUNCH_V1: the same, with packet mode when the video can go to the hardware.
bool VideoDecoder::openSourcePackets(std::shared_ptr<ByteSource> source) {
    state = std::make_unique<State>();
    auto& s = *state;
    if (!source) return s.fail("No media source");
    s.source = std::move(source);
    s.wantPackets = true;
    return openStreams();
}
// OMNI_PROGRESSIVE_HOLEPUNCH_V1: the video stream packet mode takes (-1: none).
static int omniPacketCandidate(AVFormatContext* format)
{
    for (unsigned i = 0; i < format->nb_streams; ++i) {
        auto* p = format->streams[i]->codecpar;
        if (p->codec_type != AVMEDIA_TYPE_VIDEO) continue;
        if (p->codec_tag == 0x76636e65u) return -1;   // encv: encrypted, never
        const bool known = p->codec_id == AV_CODEC_ID_H264 || p->codec_id == AV_CODEC_ID_VP9 || (p->codec_id == AV_CODEC_ID_HEVC && hevcEnabled());
        if (!known) return -1;
        if (p->width <= 0 || p->height <= 0 || p->width > 3840 || p->height > 2160) return -1;
        if (p->codec_id != AV_CODEC_ID_VP9 && (p->extradata_size <= 0 || p->extradata_size > 65536)) return -1;   // avcC / hvcC needed
        if (format->streams[i]->time_base.num <= 0 || format->streams[i]->time_base.den <= 0) return -1;
        return int(i);
    }
    return -1;
}
bool VideoDecoder::openStreams() {
    auto& s = *state;
    auto* buffer = static_cast<uint8_t*>(av_malloc(32768));
    if (!buffer) return s.fail("Media IO allocation failed");
    s.io = s.source ? avio_alloc_context(buffer, 32768, 0, &s, State::readSource, nullptr, State::seekSource)
        : avio_alloc_context(buffer, 32768, 0, &s, State::read, nullptr, State::seek);
    if (!s.io) { av_free(buffer); return s.fail("Media IO creation failed"); }
    s.format = avformat_alloc_context();
    if (!s.format) return s.fail("Media context allocation failed");
    s.format->pb = s.io;
    s.format->flags |= AVFMT_FLAG_CUSTOM_IO;
    s.format->io_open = State::denyOpen;
    s.format->interrupt_callback = {State::interrupted, &s};
    s.format->probesize = 1024 * 1024;
    s.format->max_analyze_duration = 3 * AV_TIME_BASE;
    s.format->max_streams = 16;
    AVDictionary* options = nullptr;
    av_dict_set(&options, "format_whitelist", "mov,matroska,webm", 0);
    av_dict_set(&options, "codec_whitelist", s.wantPackets ? "h264,hevc,vp8,vp9,aac,opus,vorbis,mp3" : "h264,vp8,vp9,aac,opus,vorbis,mp3", 0); // OMNI_PROGRESSIVE_HOLEPUNCH_V1: + hevc in packet mode
    av_dict_set(&options, "protocol_whitelist", "", 0);
    s.resetDeadline();
    int result = avformat_open_input(&s.format, nullptr, nullptr, &options);
    av_dict_free(&options);
    if (result < 0) return s.fail("Unsupported or malformed media container");
    const int candidate = s.wantPackets ? omniPacketCandidate(s.format) : -1; // OMNI_PROGRESSIVE_HOLEPUNCH_V1
    s.packets = candidate >= 0;
    for (unsigned i = 0; i < s.format->nb_streams && s.packets; ++i) {   // packet mode: the hardware's limit
        auto* metadata = s.format->streams[i]->codecpar;
        if (metadata->width < 0 || metadata->height < 0 || int64_t(metadata->width) * metadata->height > maxPacketPixels)
            return s.fail("Media metadata dimensions exceed the limit");
    }
    for (unsigned i = 0; i < s.format->nb_streams && !s.packets; ++i) {
        auto* metadata = s.format->streams[i]->codecpar;
        if (metadata->width < 0 || metadata->height < 0
            || int64_t(metadata->width) * metadata->height > maxPixels)
            return s.fail("Media metadata dimensions exceed the limit");
    }
    std::vector<AVDictionary*> probeOptions(s.format->nb_streams, nullptr);
    for (auto& item : probeOptions) {
        av_dict_set(&item, "max_pixels", "2073600", 0);
        // Bound allocations during stream probing as well as normal decoding.
        av_dict_set(&item, "max_samples", "131072", 0);
        av_dict_set(&item, "threads", "2", 0);
    }
    // OMNI_PROGRESSIVE_HOLEPUNCH_V1: packet mode never decodes video here, not even to probe.
    for (unsigned i = 0; i < s.format->nb_streams && s.packets; ++i)
        if (s.format->streams[i]->codecpar->codec_type == AVMEDIA_TYPE_VIDEO) av_dict_set(&probeOptions[i], "skip_frame", "all", 0);
    result = avformat_find_stream_info(s.format, probeOptions.data());
    for (auto& item : probeOptions) av_dict_free(&item);
    if (result < 0) return s.fail("Invalid media stream information");
    s.stream = s.packets ? candidate : av_find_best_stream(s.format, AVMEDIA_TYPE_VIDEO, -1, -1, nullptr, 0); // OMNI_PROGRESSIVE_HOLEPUNCH_V1
    if (s.stream < 0) return s.fail("No video stream");
    s.audioStream = av_find_best_stream(s.format, AVMEDIA_TYPE_AUDIO, -1, -1, nullptr, 0);
    s.audio = s.audioStream >= 0;
    if (s.audio) {
        auto* parameters = s.format->streams[s.audioStream]->codecpar;
        if (parameters->sample_rate < 8000 || parameters->sample_rate > 192000
            || parameters->ch_layout.nb_channels < 1 || parameters->ch_layout.nb_channels > 8)
            return s.fail("Unsupported audio metadata dimensions");
        if (parameters->codec_id != AV_CODEC_ID_AAC && parameters->codec_id != AV_CODEC_ID_OPUS
            && parameters->codec_id != AV_CODEC_ID_VORBIS && parameters->codec_id != AV_CODEC_ID_MP3)
            return s.fail("Unsupported audio codec");
        auto* decoder = avcodec_find_decoder(parameters->codec_id);
        if (!decoder) return s.fail("Audio decoder unavailable");
        s.audioCodec = avcodec_alloc_context3(decoder);
        if (!s.audioCodec || avcodec_parameters_to_context(s.audioCodec, parameters) < 0) return s.fail("Audio context creation failed");
        s.audioCodec->thread_count = 1;
        // FFmpeg checks this before allocating an audio frame. Keep the existing
        // per-channel post-decode check too (16384 samples, up to 8 channels).
        s.audioCodec->max_samples = 16384 * 8;
        if (avcodec_open2(s.audioCodec, decoder, nullptr) < 0) return s.fail("Audio decoder initialization failed");
        s.audioFrame = av_frame_alloc();
        if (!s.audioFrame) return s.fail("Audio frame allocation failed");
    }
    auto* parameters = s.format->streams[s.stream]->codecpar;
    if (s.packets) {   // OMNI_PROGRESSIVE_HOLEPUNCH_V1: the track for PacketDecoder; no video codec here
        auto* stream = s.format->streams[s.stream];
        if (parameters->width <= 0 || parameters->height <= 0 || parameters->width > 3840 || parameters->height > 2160)
            return s.fail("Unsupported video dimensions");
        s.track = { };
        s.track.id = s.stream;
        s.track.codec = parameters->codec_id == AV_CODEC_ID_H264 ? DemuxCodec::H264 : parameters->codec_id == AV_CODEC_ID_HEVC ? DemuxCodec::HEVC : DemuxCodec::VP9;
        s.track.timeBase = { stream->time_base.num, stream->time_base.den };
        s.track.width = parameters->width; s.track.height = parameters->height;
        if (s.track.codec != DemuxCodec::VP9) {
            if (parameters->extradata_size <= 0 || parameters->extradata_size > 65536) return s.fail("Video configuration missing");
            s.track.extraData.assign(parameters->extradata, parameters->extradata + parameters->extradata_size);
        }
        s.packet = av_packet_alloc();
        if (!s.packet) return s.fail("Video packet allocation failed");
        if (s.format->duration != AV_NOPTS_VALUE) s.length = std::max(0.0, double(s.format->duration) / AV_TIME_BASE);
        return true;
    }
    if (parameters->width <= 0 || parameters->height <= 0
        || int64_t(parameters->width) * parameters->height > maxPixels)
        return s.fail("Unsupported video dimensions");
    if (parameters->codec_id != AV_CODEC_ID_H264 && parameters->codec_id != AV_CODEC_ID_VP8
        && parameters->codec_id != AV_CODEC_ID_VP9) return s.fail("Unsupported video codec");
    auto* decoder = avcodec_find_decoder(parameters->codec_id);
    if (!decoder) return s.fail("Video decoder unavailable");
    s.codec = avcodec_alloc_context3(decoder);
    if (!s.codec || avcodec_parameters_to_context(s.codec, parameters) < 0) return s.fail("Video context creation failed");
    s.codec->thread_count = 2;
    s.codec->max_pixels = maxPixels;
    if (avcodec_open2(s.codec, decoder, nullptr) < 0) return s.fail("Video decoder initialization failed");
    s.packet = av_packet_alloc(); s.frame = av_frame_alloc();
    if (!s.packet || !s.frame) return s.fail("Video frame allocation failed");
    if (s.format->duration != AV_NOPTS_VALUE) s.length = std::max(0.0, double(s.format->duration) / AV_TIME_BASE);
    return true;
}

VideoDecoder::Result VideoDecoder::next(VideoFrame& output) {
    auto& s = *state;
    if (!s.codec || !s.failure.empty()) return Result::Error;
    s.resetDeadline();
    for (int budget = 0; budget < 256; ++budget) {
        if (State::interrupted(&s)) { s.fail("Video decode time limit exceeded"); return Result::Error; }
        int result = avcodec_receive_frame(s.codec, s.frame);
        if (result == AVERROR_EOF) return Result::End;
        if (result == 0) {
            int64_t timestamp = s.frame->best_effort_timestamp;
            double seconds = timestamp == AV_NOPTS_VALUE ? 0 : timestamp * av_q2d(s.format->streams[s.stream]->time_base);
            if (s.videoDiscardBefore >= 0 && seconds + 0.000001 < s.videoDiscardBefore) {
                av_frame_unref(s.frame); continue;
            }
            s.videoDiscardBefore = -1;
            int w = s.frame->width, h = s.frame->height;
            if (w <= 0 || h <= 0 || int64_t(w) * h > maxPixels) {
                s.fail("Decoded video dimensions exceed the limit"); return Result::Error;
            }
            s.scale = sws_getCachedContext(s.scale,w,h,AVPixelFormat(s.frame->format),w,h,AV_PIX_FMT_RGBA,SWS_BILINEAR,nullptr,nullptr,nullptr);
            if (!s.scale) { s.fail("Video color conversion failed"); return Result::Error; }
            output.rgba.resize(size_t(w) * h * 4);
            uint8_t* planes[] = {output.rgba.data(), nullptr, nullptr, nullptr};
            int strides[] = {w * 4, 0, 0, 0};
            if (sws_scale(s.scale, s.frame->data, s.frame->linesize, 0, h, planes, strides) != h) {
                s.fail("Incomplete converted frame"); return Result::Error;
            }
            output.width = w; output.height = h;
            output.seconds = seconds;
            av_frame_unref(s.frame);
            return Result::Frame;
        }
        if (result != AVERROR(EAGAIN)) { s.fail("Video frame decode failed"); return Result::Error; }
        if (s.draining) return Result::End;
        result = av_read_frame(s.format, s.packet);
        if (result == AVERROR_EOF) {
            if (!s.decodeAudio(nullptr)) return Result::Error;
            avcodec_send_packet(s.codec, nullptr); s.draining = true; continue;
        }
        if (result < 0) { s.fail("Media packet read failed"); return Result::Error; }
        if (s.packet->stream_index == s.audioStream) {
            bool ok = s.decodeAudio(s.packet); av_packet_unref(s.packet);
            if (!ok) return Result::Error;
            continue;
        }
        if (s.packet->stream_index != s.stream) { av_packet_unref(s.packet); continue; }
        result = avcodec_send_packet(s.codec, s.packet);
        av_packet_unref(s.packet);
        if (result < 0) { s.fail("Media packet decode failed"); return Result::Error; }
    }
    return Result::Again;
}
// OMNI_PROGRESSIVE_HOLEPUNCH_V1: the next video packet; audio packets are decoded on the way.
VideoDecoder::Result VideoDecoder::nextPacket(DemuxPacket& out) {
    auto& s = *state;
    if (!s.packets || !s.packet || !s.failure.empty()) return Result::Error;
    s.resetDeadline();
    for (int budget = 0; budget < 256; ++budget) {
        if (State::interrupted(&s)) { s.fail("Media read time limit exceeded"); return Result::Error; }
        if (s.draining) return Result::End;
        int result = av_read_frame(s.format, s.packet);
        if (result == AVERROR_EOF) {
            if (!s.decodeAudio(nullptr)) return Result::Error;
            s.draining = true;
            return Result::End;
        }
        if (result < 0) { s.fail("Media packet read failed"); return Result::Error; }
        if (av_packet_get_side_data(s.packet, AV_PKT_DATA_ENCRYPTION_INFO, nullptr) || av_packet_get_side_data(s.packet, AV_PKT_DATA_ENCRYPTION_INIT_INFO, nullptr)) {
            av_packet_unref(s.packet); s.fail("Encrypted packet unsupported"); return Result::Error;
        }
        if (s.packet->stream_index == s.audioStream) {
            bool ok = s.decodeAudio(s.packet); av_packet_unref(s.packet);
            if (!ok) return Result::Error;
            return Result::Again;   // the caller takes the PCM now (decodeAudio's buffer is bounded)
        }
        if (s.packet->stream_index != s.stream || s.packet->size <= 0 || (s.packet->flags & AV_PKT_FLAG_CORRUPT)) { av_packet_unref(s.packet); continue; }
        int64_t pts = s.packet->pts != AV_NOPTS_VALUE ? s.packet->pts : s.packet->dts;
        if (pts == AV_NOPTS_VALUE) { av_packet_unref(s.packet); continue; }   // no time: never shown
        out = { };
        out.trackId = s.track.id; out.timeBase = s.track.timeBase;
        out.pts = pts; out.dts = s.packet->dts != AV_NOPTS_VALUE ? s.packet->dts : pts;
        out.duration = std::max<int64_t>(0, s.packet->duration);
        out.keyFrame = (s.packet->flags & AV_PKT_FLAG_KEY) != 0;
        out.bytes.assign(s.packet->data, s.packet->data + s.packet->size);
        av_packet_unref(s.packet);
        return Result::Frame;
    }
    return Result::Again;
}
bool VideoDecoder::seek(double seconds) {
    auto& s = *state;
    if ((!s.codec && !s.packets) || !s.failure.empty() || !std::isfinite(seconds) || seconds < 0 || seconds > s.length) return false;
    double tick = av_q2d(s.format->streams[s.stream]->time_base);
    if (tick <= 0 || seconds / tick >= double(std::numeric_limits<int64_t>::max())) return false;
    s.resetDeadline();
    if (av_seek_frame(s.format, s.stream, int64_t(seconds / tick), AVSEEK_FLAG_BACKWARD) < 0) return false;
    if (s.codec) avcodec_flush_buffers(s.codec); // OMNI_PROGRESSIVE_HOLEPUNCH_V1: none in packet mode
    s.draining = false;
    if (s.audioCodec) avcodec_flush_buffers(s.audioCodec);
    swr_free(&s.resampler); s.pcm.clear();
    s.videoDiscardBefore = s.audioDiscardBefore = seconds;
    return true;
}
}
